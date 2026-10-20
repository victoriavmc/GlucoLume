# Acquisition - Orquestación de la adquisición física: permisos, persistencia y auditoría
#
# El enlace serie (pySerial) vive en app/acquisition/link.py; aquí se decide quién puede usarlo y qué se guarda:
#   - Pueden conectar y medir las cuentas individuales y los operadores activos de una institución. El primero que
#     conecta es el dueño del enlace; los demás reciben DISPOSITIVO_EN_USO.
#   - Iniciar exige poder operar la medición (perfil propio o paciente a cargo), que esté PENDIENTE, que el dispositivo
#     siga OPERATIVO y que el Arduino identificado coincida con el Dispositivo elegido (código y sensor).
#   - Las muestras se guardan en MuestraSensor por lotes (measurement.addSamples); finalizar procesa la señal en el
#     servidor (measurement.finishMeasurement). Cancelar descarta lo pendiente y cancela la medición.
#   - Auditoría: INICIAR_ADQUISICION, y FALLO ante fallos relevantes de comunicación. Nunca una entrada por muestra.

import uuid
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.acquisition import protocol
from app.acquisition.link import AcquisitionSession, link
from app.acquisition.telemetry import hub
from app.core.exceptions import AuthError
from app.db.session import getSessionFactory
from app.models.device import Device
from app.models.institutionUser import InstitutionUser
from app.models.user import User
from app.schemas.acquisition import ConnectRequest
from app.schemas.measurement import MeasurementDetail, MeasurementFinish, SampleItem, SamplesRequest
from app.services import institution as institutions
from app.services import measurement as measurements
from app.services.audit import registerEvent

TIPO_INDIVIDUAL, TIPO_INSTITUCIONAL = "CONSUMIDOR_FINAL", "USUARIO_INSTITUCIONAL"

# Fábrica de sesiones del hilo lector (las pruebas la reemplazan por la de su base temporal).
sessionFactory: Callable[[], sessionmaker[Session]] = getSessionFactory


def _requireMeasurer(db: Session, actor: User) -> None:
    if actor.tipoCuenta == TIPO_INDIVIDUAL:
        return
    if actor.tipoCuenta == TIPO_INSTITUCIONAL and db.scalar(
        select(InstitutionUser.idInstitucionUsuario).where(
            InstitutionUser.idUsuarioInvitado == actor.idUsuario, InstitutionUser.rolInstitucion == "OPERADOR",
            InstitutionUser.estadoRelacion == "ACTIVO", InstitutionUser.idInstitucion.in_(institutions.operatingInstitutionIds(db, actor))).limit(1)
    ):  # solo cuenta un vínculo en una institución ACTIVA: una pausada no habilita nuevas sesiones de dispositivo
        return
    raise AuthError("PERMISO_INSUFICIENTE", "Solo las cuentas individuales y los operadores pueden conectar un dispositivo de medición.")


def _requireOwner(actor: User) -> None:
    if not link.connected():
        raise AuthError("DISPOSITIVO_NO_CONECTADO", "No hay un dispositivo conectado.")
    if link.owner != actor.idUsuario:
        raise AuthError("DISPOSITIVO_EN_USO", "El dispositivo está siendo usado por otra cuenta.")


# --- Hooks del enlace ---------------------------------------------------------------------------------------------


def _sink(session: AcquisitionSession, samples: list[protocol.Sample]) -> None:
    """Guarda un lote de muestras con una sesión propia (corre en el hilo lector)."""
    db = sessionFactory()()
    try:
        actor = db.get(User, session.userId)
        measurements.addSamples(db, actor, session.idMedicion, SamplesRequest(muestras=[
            SampleItem(numeroMuestra=s.number, tiempoRelativoMs=s.timeMs, valorRed=s.red, valorIR=s.ir) for s in samples]))
    finally:
        db.close()


def _onLost(session: AcquisitionSession | None, message: str) -> None:
    """El Arduino se desconectó: se audita, se conservan las muestras recibidas y se cierra la medición."""
    if session is None:
        return
    db = sessionFactory()()
    try:
        actor = db.get(User, session.userId)
        registerEvent(db, "CRUD", "ERROR_COMUNICACION_DISPOSITIVO", False, session.userId, "Medicion", session.idMedicion,
                      observacion=message[:300])
        db.commit()
        try:
            measurements.finishMeasurement(db, actor, session.idMedicion, MeasurementFinish(
                observacion="Adquisición interrumpida: se perdió la comunicación con el dispositivo."))
        except AuthError:
            try:
                measurements.cancelMeasurement(db, actor, session.idMedicion)
            except AuthError:
                pass
    finally:
        db.close()
        link.clearSession()


link.sink = _sink
link.onLost = _onLost


# --- Operaciones --------------------------------------------------------------------------------------------------


def listPorts(db: Session, actor: User) -> list[dict]:
    _requireMeasurer(db, actor)
    return link.listPorts()


def status(actor: User) -> dict:
    """Estado del enlace. Quien no es el dueño solo ve que está ocupado."""
    snapshot = link.snapshot()
    if snapshot["conectado"] and link.owner != actor.idUsuario:
        return {"conectado": True, "ocupado": True, "puerto": None, "medio": None, "baudios": None, "estadoDispositivo": None,
                "ultimoError": None, "lineasInvalidas": 0, "dispositivo": None, "adquisicion": None}
    return {**snapshot, "ocupado": False}


def connect(db: Session, actor: User, data: ConnectRequest, opener=None) -> dict:
    _requireMeasurer(db, actor)
    if hub.ownsPort(data.puerto):  # el puente serie ya tiene abierto ese puerto: nunca dos lectores sobre el mismo COM
        raise AuthError("PUERTO_EN_USO_PUENTE", f"El puerto {data.puerto} lo está usando el puente serie de GlucoLume.")
    if opener is None:  # apertura real: solo puertos que este equipo enumera (jamás una ruta arbitraria del servidor)
        known = {port["puerto"].lower() for port in link.listPorts()}
        if data.puerto.lower() not in known:
            raise AuthError("PUERTO_NO_ENCONTRADO", "El puerto no existe en este equipo. Actualizá la lista de puertos.")
    try:
        link.connect(actor.idUsuario, data.puerto, data.medio, data.baudios, opener=opener)
    except AuthError as error:
        if error.code != "DISPOSITIVO_EN_USO":
            registerEvent(db, "ACCESO", "CONECTAR_DISPOSITIVO", False, actor.idUsuario, observacion=error.code)
            db.commit()
        raise
    return status(actor)


def disconnect(db: Session, actor: User) -> dict:
    _requireMeasurer(db, actor)
    if link.connected():
        _requireOwner(actor)
        if link.session is not None and link.session.state in ("ADQUIRIENDO", "FINALIZANDO"):
            raise AuthError("ADQUISICION_ACTIVA", "Hay una adquisición en curso: finalizala o cancelala antes de desconectar.")
    link.disconnect()
    return status(actor)


def probe(db: Session, actor: User) -> float:
    _requireMeasurer(db, actor)
    _requireOwner(actor)
    return link.probe()


def identify(db: Session, actor: User) -> dict:
    _requireMeasurer(db, actor)
    _requireOwner(actor)
    link.identify()
    return status(actor)


def start(db: Session, actor: User, idMedicion: uuid.UUID) -> dict:
    _requireMeasurer(db, actor)
    _requireOwner(actor)
    measurement, access = measurements._measurementAccess(db, actor, idMedicion)
    measurements._requireOperate(access)
    if measurement.estadoMedicion != measurements.PENDIENTE:
        raise measurements._stateError(measurement)
    device = db.get(Device, measurement.idDispositivo)
    if device is None or device.estado != measurements.DEVICE_OPERATIVO:
        raise AuthError("DISPOSITIVO_NO_DISPONIBLE", "El dispositivo elegido no está operativo.")
    ident = link.identification or link.identify()
    if ident.id.strip().lower() != device.codigoDispositivo.strip().lower():
        raise AuthError("DISPOSITIVO_NO_COINCIDE", "El Arduino conectado no es el dispositivo elegido para esta medición.")
    if ident.sensor != device.modeloSensor:
        raise AuthError("DISPOSITIVO_INCONSISTENTE", "El sensor informado por el Arduino no coincide con el del inventario.")
    # La auditoría se escribe antes de abrir el flujo de muestras; si el dispositivo no confirma, queda el fallo.
    registerEvent(db, "CRUD", "INICIAR_ADQUISICION", True, actor.idUsuario, "Medicion", idMedicion)
    db.commit()
    try:
        link.beginSession(AcquisitionSession(idMedicion=idMedicion, userId=actor.idUsuario, sensor=ident.sensor))
    except AuthError as error:
        registerEvent(db, "CRUD", "INICIAR_ADQUISICION", False, actor.idUsuario, "Medicion", idMedicion, observacion=error.code)
        db.commit()
        raise
    return status(actor)


def _activeSession(actor: User) -> AcquisitionSession:
    _requireOwner(actor)
    session = link.session
    if session is None or session.userId != actor.idUsuario:
        raise AuthError("ADQUISICION_NO_ACTIVA", "No hay una adquisición en curso.")
    return session


def finish(db: Session, actor: User) -> MeasurementDetail:
    """Detiene el Arduino, guarda lo pendiente y procesa la señal en el servidor."""
    session = _activeSession(actor)
    link.endSession()
    link.flush(session)
    note = session.error
    detail = measurements.finishMeasurement(db, actor, session.idMedicion, MeasurementFinish(observacion=note))
    link.clearSession()
    link._emit({"tipo": "resultado", "estado": detail.estadoMedicion, "spo2": float(detail.spo2) if detail.spo2 is not None else None,
                "frecuenciaCardiaca": detail.frecuenciaCardiaca, "motivo": detail.observacion})
    return detail


def cancel(db: Session, actor: User) -> MeasurementDetail:
    session = _activeSession(actor)
    link.endSession()
    with link.lock:
        session.buffer = []  # lo no guardado se descarta
    detail = measurements.cancelMeasurement(db, actor, session.idMedicion)
    link.clearSession()
    link._emit({"tipo": "resultado", "estado": detail.estadoMedicion})
    return detail
