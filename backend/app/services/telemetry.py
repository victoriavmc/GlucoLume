# Telemetry - Medición con el dispositivo a partir de la telemetría ya procesada por el firmware
#
# Flujo (Arduino + MAX30100 → Bluetooth HC-05/HC-06 → COM de Windows → puente pySerial → FastAPI → SQL Server → React):
#   1. El puente (acquisition/bridge) envía las líneas del firmware a ingest(); el estado vive en memoria
#      (app/acquisition/telemetry.py). Los mensajes periódicos NO se guardan.
#   2. Una persona autenticada abre una SESIÓN de medición (startSession): se crea la Medicion (misma regla de acceso
#      que cualquier medición: perfil propio, o paciente a cargo del operador; dispositivo operativo, utilizable por ese
#      perfil y que sea el que atiende el puente) y el dispositivo queda reservado a esa cuenta. Solo las lecturas
#      POSTERIORES al inicio de la sesión se le atribuyen. Otra cuenta no ve las lecturas ni abre otra sesión.
#   3. «Guardar medición» (saveSession) toma una lectura estabilizada de la sesión (criterio en telemetry.evaluateStability)
#      y completa la Medicion en UNA transacción: UPDATE condicionado al estado + auditoría + commit. Recién entonces se
#      libera la sesión y se confirma. Dos pedidos simultáneos no pueden guardar dos veces (bandera `saving` y UPDATE
#      condicionado al estado).
#   4. Los datos DEMO (glucosa sintética) se guardan con origenGlucosa='DEMO': quedan fuera de estadísticas, dashboards,
#      avisos y correos, y se pueden consultar y eliminar (measurement.deleteDemoMeasurement).
#
# No se calcula BPM, SpO₂, glucosa ni índice óptico aquí: se guardan los que informó el firmware, identificados con
# versionAlgoritmo = FIRMWARE_ALGORITHM. Este servicio no escribe nunca en el Arduino (ni DEMO,ON/OFF ni CAL).

import logging
from decimal import Decimal

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.acquisition.link import link
from app.acquisition.telemetry import (
    REGISTRATION_RECHECK_SECONDS, UNSTABLE_MESSAGES, BridgeConflict, CommandRejected, Stable, Unstable, hub,
)
from app.core.exceptions import AuthError
from app.models.device import Device
from app.models.measurement import Measurement
from app.models.institutionUser import InstitutionUser
from app.models.measurementProfile import MeasurementProfile
from app.models.user import User
from app.schemas.acquisition import (
    BridgeCheckRead,
    BridgeCheckRequest,
    BridgeCommandRequest,
    BridgeIngest,
    BridgeIngestRead,
    TelemetrySessionStart,
)
from app.schemas.measurement import MeasurementDetail, MeasurementStart
from app.services import device as deviceService
from app.services import deviceConnection
from app.services import institution as institutions
from app.services import measurement as measurements
from app.services import schemaCompat
from app.services import notifications
from app.services.acquisition import TIPO_INSTITUCIONAL, _requireMeasurer
from app.services.audit import registerEvent

logger = logging.getLogger(__name__)

FIRMWARE_ALGORITHM = "firmware-glucolume-max30100-v1"
DEMO_NOTE = "Datos de prueba (DEMO): la glucosa es un valor sintético del firmware, no una medición."

_NOT_CONNECTED = {
    "SIN_PUENTE": "El puente serie no está en ejecución en el equipo del dispositivo. Iniciá el puente y volvé a intentar.",
    "PUERTO_DESCONECTADO": "El dispositivo no está conectado al equipo del puente. Encendé el Arduino y revisá el cable USB o el emparejamiento Bluetooth.",
    "SIN_DATOS": "El dispositivo está conectado pero no envía datos todavía. Esperá unos segundos.",
}


def _notConnected(state: str) -> AuthError:
    return AuthError("DISPOSITIVO_NO_CONECTADO", _NOT_CONNECTED.get(state, "No hay un dispositivo conectado."))


# --- Puente ---------------------------------------------------------------------------------------------------------------


def ingest(db: Session, data: BridgeIngest) -> BridgeIngestRead:
    """Latido y líneas del puente. Autenticado por token en la capa HTTP; idempotente por `seq`."""
    try:
        result = hub.ingest(str(data.idPuente), data.codigoDispositivo.strip(), data.puerto, data.medio, data.baudios,
                            data.estadoEnlace, data.intento, data.error, [(l.seq, l.edadMs, l.texto) for l in data.lineas],
                            stopped=data.detenido, errorCode=data.codigoError,
                            ports=None if data.puertos is None else [p.model_dump() for p in data.puertos],
                            version=data.versionPuente,
                            commandResult=None if data.comando is None else data.comando.model_dump())
    except BridgeConflict as error:
        raise AuthError("PUENTE_DUPLICADO", str(error)) from error
    if hub.identity()["nivel"] == "DECLARADA" and hub.registrationAllowed():
        # Firmware sin ID propio (anterior): el código configurado en el puente se da de alta solo, sin institución, pero SOLO con telemetría
        # llegando y pasado el margen sin ID (nunca con un Arduino que no responde). Con ID propio NO: el alta la hace un operador desde su
        # conexión (queda en su institución) o la cuenta individual al verificar.
        _ensureRegistered(db, data.codigoDispositivo.strip())
    if result.linkLostDuringSession:
        session = hub.session
        if session is not None and session.idMedicion is not None:
            registerEvent(db, "CRUD", "ERROR_COMUNICACION_DISPOSITIVO", False, session.userId, "Medicion", session.idMedicion,
                          observacion="Se perdió la conexión con el dispositivo durante la sesión de medición.")
            db.commit()
    return BridgeIngestRead(aceptadas=result.accepted, duplicadas=result.duplicated, invalidas=result.invalid,
                            estado=hub.deviceState(), comando=result.command)


def _ensureRegistered(db: Session, code: str) -> None:
    """Si el puente informa un código que no está en el inventario, se da de alta solo (ver device.registerFromBridge).
    Una falla nunca impide recibir lecturas: se vuelve a intentar en el próximo latido."""
    key = code.lower()
    checked = hub.registeredCodes.get(key)
    if checked is not None and hub.clock() - checked < REGISTRATION_RECHECK_SECONDS:
        return
    try:
        if deviceService.registerFromBridge(db, code) is not None:
            hub.registeredCodes[key] = hub.clock()
    except Exception:  # noqa: BLE001 - el alta automática es un auxilio, no condiciona la recepción
        db.rollback()
        logger.exception("No se pudo registrar automáticamente el dispositivo informado por el puente")


def check(db: Session, data: BridgeCheckRequest) -> BridgeCheckRead:
    """Para la instalación del puente (autenticada por token): ¿el código existe en el inventario y está operativo?
    No devuelve datos de personas ni de otras instituciones."""
    device = db.scalar(select(Device).where(func.lower(Device.codigoDispositivo) == data.codigoDispositivo.strip().lower()))
    if device is None:
        return BridgeCheckRead(registrado=False)
    return BridgeCheckRead(registrado=True, operativo=device.estado == measurements.DEVICE_OPERATIVO,
                           sensor=device.modeloSensor, nombre=device.nombre,
                           asignadoAInstitucion=device.idInstitucionAsignada is not None)


_OUTSIDER_INDIVIDUAL = ("El dispositivo conectado está registrado en una institución, y una cuenta individual no puede darle órdenes al puente "
                        "ni medir con él. Con tu propio Arduino (sin institución) no hace falta ningún operador. Si este es tu dispositivo, "
                        "pedí a esa institución que lo libere; no se reasigna automáticamente.")
_OUTSIDER_INSTITUTIONAL = "Solo un operador de la institución a la que pertenece el dispositivo puede dar órdenes al puente."


def bridgeAuthority(db: Session, actor: User) -> tuple[dict, Device | None]:
    """¿Puede `actor` dar órdenes al puente, según a qué contexto pertenece el dispositivo que ese puente atiende? Fuente única: la usan
    el rechazo de `command` y el diagnóstico `readiness` (el frontend no decide nada por su cuenta).

    PERSONAL: sin institución (el pool de cuentas individuales y sus grupos) o aún no inventariado → rige la regla general de quien puede
    medir, sin ningún operador. COMPARTIDO: uso compartido habilitado (DEC-01) → cualquier cuenta que puede medir, sin importar a qué
    institución esté asignado. INSTITUCIONAL_PROPIA: asignado a una institución donde `actor` es OPERADOR ACTIVO. INSTITUCIONAL_AJENA:
    asignado a una institución donde no lo es (cuenta individual u operador de otra): bloqueado. SIN_DISPOSITIVO: no hay puente activo.
    Esto decide QUIÉN PUEDE usar el equipo; QUIÉN LO USA AHORA lo decide el control temporal (takeControl / hub.reserve)."""
    code = hub.effectiveCode()
    if not code:
        return {"contexto": "SIN_DISPOSITIVO", "permitido": True, "motivo": None}, None  # el hub responde PUENTE_NO_ACTIVO
    device = db.scalar(select(Device).where(func.lower(Device.codigoDispositivo) == code.strip().lower()))
    if device is None or device.idInstitucionAsignada is None:
        return {"contexto": "PERSONAL", "permitido": True, "motivo": None}, device
    if deviceService.sharedDeviceMode():  # DEC-01: la asignación administrativa (ni su pausa) no restringe el uso del único equipo
        return {"contexto": "COMPARTIDO", "permitido": True, "motivo": None}, device
    if not institutions.isOperating(db, device.idInstitucionAsignada):  # institución pausada (o cerrada): nadie opera con sus dispositivos
        return {"contexto": "INSTITUCIONAL_PAUSADA", "permitido": False, "motivo": institutions.PAUSED_MESSAGE}, device
    isOperator = actor.tipoCuenta == TIPO_INSTITUCIONAL and db.scalar(
        select(InstitutionUser.idInstitucionUsuario).where(
            InstitutionUser.idUsuarioInvitado == actor.idUsuario, InstitutionUser.idInstitucion == device.idInstitucionAsignada,
            InstitutionUser.rolInstitucion == "OPERADOR", InstitutionUser.estadoRelacion == "ACTIVO").limit(1)) is not None
    if isOperator:
        return {"contexto": "INSTITUCIONAL_PROPIA", "permitido": True, "motivo": None}, device
    reason = _OUTSIDER_INSTITUTIONAL if actor.tipoCuenta == TIPO_INSTITUCIONAL else _OUTSIDER_INDIVIDUAL
    return {"contexto": "INSTITUCIONAL_AJENA", "permitido": False, "motivo": reason}, device


def _requireBridgeAuthority(db: Session, actor: User) -> None:
    """Las órdenes (detener, pausar, reiniciar, cambiar puerto/medio) actúan sobre el equipo que ejecuta el puente: solo las da quien
    tiene autoridad sobre el dispositivo que ese puente atiende (ver `bridgeAuthority`). El rechazo queda auditado."""
    authority, device = bridgeAuthority(db, actor)
    if authority["permitido"]:
        return
    registerEvent(db, "PERMISO", "ORDEN_PUENTE_SERIE", False, actor.idUsuario, "Dispositivo", device.idDispositivo,
                  observacion="Sin autoridad sobre el dispositivo que atiende el puente")
    db.commit()
    raise AuthError("PERMISO_INSUFICIENTE", authority["motivo"])


def takeControl(db: Session, actor: User) -> dict:
    """«Usar dispositivo»: toma el control temporal del equipo (DEC-01). Acción explícita y atómica (hub.reserve bajo su candado): con el
    equipo libre lo obtiene una sola cuenta; si otra lo controla, DISPOSITIVO_EN_USO. Quién PUEDE tomarlo lo decide bridgeAuthority (modo
    compartido o asignación). Sin medición, el control vence a los 5 min de la última acción explícita o a los 30 s sin consultar el estado;
    volver a tomarlo lo renueva. Iniciar una medición también lo toma (startSession) y la medición no vence por esos 5 min."""
    _requireMeasurer(db, actor)
    settleExpired(db)
    if hub.deviceState() == "SIN_PUENTE":
        raise AuthError("PUENTE_NO_ACTIVO", "El puente de GlucoLume no está ejecutándose: no hay dispositivo para usar.")
    _requireBridgeAuthority(db, actor)
    try:
        hub.reserve(actor.idUsuario)
    except PermissionError as error:
        raise AuthError("DISPOSITIVO_EN_USO", str(error)) from error
    except ValueError:
        return hub.snapshot(actor.idUsuario)  # ya lo controla con una medición en curso
    code = hub.effectiveCode()
    device = deviceService.findByCode(db, code) if code else None
    registerEvent(db, "ACCESO", "TOMAR_CONTROL_DISPOSITIVO", True, actor.idUsuario, "Dispositivo",
                  device.idDispositivo if device is not None else None)
    db.commit()
    return hub.snapshot(actor.idUsuario)


def releaseControl(db: Session, actor: User) -> dict:
    """«Dejar de usar»: libera el control sin medición para que otra cuenta habilitada pueda tomarlo. Una medición en curso se guarda o se
    cancela (su cierre ya libera el equipo)."""
    _requireMeasurer(db, actor)
    settleExpired(db)
    with hub.lock:
        session = hub.session
        if session is None or session.userId != actor.idUsuario:
            return hub.snapshot(actor.idUsuario)
        if session.idMedicion is not None or session.saving:
            raise AuthError("SESION_EN_CURSO", "Tenés una medición en curso: guardala o cancelala para liberar el dispositivo.")
        hub.release(session)
    registerEvent(db, "ACCESO", "SOLTAR_CONTROL_DISPOSITIVO", True, actor.idUsuario)
    db.commit()
    return hub.snapshot(actor.idUsuario)


def command(db: Session, actor: User, data: BridgeCommandRequest) -> dict:
    """Pedido de una orden al puente por un usuario autenticado. La lista de acciones permitidas y el estado del puente se
    validan en el hub (hub.requestCommand); acá se autoriza a quien pide (puede medir y tiene autoridad sobre el dispositivo
    del puente) y se deja constancia. Solo da órdenes quien tiene el control temporal (lo verifica el hub): una orden nunca lo toma."""
    _requireMeasurer(db, actor)
    _requireBridgeAuthority(db, actor)
    try:
        pending = hub.requestCommand(actor.idUsuario, data.accion, data.puerto, data.medio)
    except CommandRejected as error:
        raise AuthError(error.code, error.message) from error
    registerEvent(db, "PERMISO", "ORDEN_PUENTE_SERIE", True, actor.idUsuario,
                  datosNuevos={"accion": pending["accion"], "puerto": pending["puerto"], "medio": pending["medio"]})
    db.commit()
    return hub.snapshot(actor.idUsuario)


# --- Diagnóstico: ¿qué falta para poder medir? ----------------------------------------------------------------------------

_PORT_PROBLEMS = {
    "PUERTO_OCUPADO": ("Puerto {port} ocupado por otra aplicación.",
                       "Cerrá el Monitor Serie del Arduino IDE, PuTTY, miniterm u otro programa que use {port} y esperá unos segundos."),
    "PUERTO_INEXISTENTE": ("El puerto {port} no existe en este equipo.",
                           "Conectá el Arduino (o emparejá el Bluetooth), revisá el controlador y elegí el puerto que Windows le asignó."),
    "DISPOSITIVO_SIN_RESPUESTA": ("El puerto {port} existe pero el dispositivo no responde.",
                                  "Encendé el Arduino, comprobá la alimentación del módulo Bluetooth y acercalo al equipo."),
    "SIN_DATOS": ("El puerto {port} abrió pero no llegan datos.",
                  "Verificá que el Arduino tenga cargado el firmware de GlucoLume y que la velocidad coincida (9600 Bluetooth, 115200 USB)."),
    "ERROR_PUERTO": ("No se pudo usar el puerto {port}.", "Revisá la conexión y volvé a intentar."),
}


def _step(identifier: str, title: str, state: str, detail: str, solution: str | None = None) -> dict:
    return {"id": identifier, "titulo": title, "estado": state, "detalle": detail, "solucion": solution}


def readiness(db: Session, actor: User, idPerfilMedicion=None, idInstitucion=None) -> dict:
    """Lista ordenada de comprobaciones REALES (puente, puerto, telemetría, sensor, identidad, inventario, asociación al perfil) y si el
    dispositivo está disponible para medir. Un puerto COM abierto no alcanza: hace falta también telemetría reciente, que
    el dispositivo esté identificado y registrado y que el perfil pueda usarlo.

    `idInstitucion`: contexto de un operador (la institución donde entró). Con él se reconoce el dispositivo en SU inventario, se informa
    si es nuevo (se puede registrar desde la conexión) y la asociación se comprueba para esa institución, sin necesitar un paciente."""
    _requireMeasurer(db, actor)
    membership = deviceService.operatorMembership(db, actor, idInstitucion) if idInstitucion is not None else None
    snap = hub.snapshot(actor.idUsuario)
    # La lectura con valores solo la recibe quien controla el equipo; el diagnóstico usa su antigüedad y si hay dedo, sin valores.
    state, bridge, reading = snap["estado"], snap["puente"], hub.diagnosticReading()
    steps: list[dict] = []

    if state == "SIN_PUENTE" or bridge is None:
        steps.append(_step("PUENTE", "Servicio puente", "ERROR", "El puente de GlucoLume no está ejecutándose.",
                           "Abrí «Puente GlucoLume» (menú del puente en esta computadora) y elegí «Iniciar», o activá el inicio automático."))
        for identifier, title in (("PUERTO", "Puerto abierto"), ("TELEMETRIA", "Telemetría reciente"), ("SENSOR", "Sensor")):
            steps.append(_step(identifier, title, "PENDIENTE", "Se comprueba cuando el puente esté en ejecución."))
        code = None
    else:
        code = bridge["codigoDispositivo"]
        version = f" (versión {bridge['versionPuente']})" if bridge.get("versionPuente") else ""
        steps.append(_step("PUENTE", "Servicio puente", "OK", f"El puente está ejecutándose{version}."))
        link, port = bridge["estadoEnlace"], bridge.get("puerto") or "seleccionado"
        if link == "CONECTADO":
            steps.append(_step("PUERTO", "Puerto abierto", "OK", f"Puerto {port} abierto a {bridge['baudios']} baudios ({bridge['medio'].lower()})."))
        elif link == "PAUSADO":
            steps.append(_step("PUERTO", "Puerto abierto", "PENDIENTE", "La lectura está pausada: el puerto está libre.", "Reanudá la lectura desde esta pantalla."))
        else:
            problem = _PORT_PROBLEMS.get(bridge.get("codigoError") or "")
            detail, solution = ((problem[0].format(port=port), problem[1].format(port=port)) if problem else
                                (f"Intentando abrir el puerto {port} (intento {bridge['reintento']}).", "Si no se resuelve, revisá la conexión del dispositivo."))
            steps.append(_step("PUERTO", "Puerto abierto", "ERROR", detail, solution))
        if state == "CONECTADO" and reading is not None:
            steps.append(_step("TELEMETRIA", "Telemetría reciente", "OK", f"Última lectura hace {reading['edadSegundos']:.0f} s."))
        elif link == "CONECTADO":
            steps.append(_step("TELEMETRIA", "Telemetría reciente", "PENDIENTE", "El puerto abrió pero todavía no llegan lecturas.", _PORT_PROBLEMS["SIN_DATOS"][1].format(port=port)))
        else:
            steps.append(_step("TELEMETRIA", "Telemetría reciente", "PENDIENTE", "Sin puerto abierto no hay telemetría."))
        notice = snap.get("avisoDispositivo")
        if notice and notice["error"]:
            steps.append(_step("SENSOR", "Sensor", "ERROR", notice["texto"], "Revisá el cableado I2C del MAX30100 y reiniciá el Arduino."))
        elif reading is not None:
            note = "" if reading["dedo"] else " Colocá el dedo sobre el sensor para medir."
            steps.append(_step("SENSOR", "Sensor", "OK", f"El sensor responde.{note}"))
        else:
            steps.append(_step("SENSOR", "Sensor", "PENDIENTE", "Se comprueba cuando llegue telemetría."))

    device = None
    identification = None
    if membership is not None:
        # Contexto de operador: la identidad y el registro se resuelven contra el inventario de SU institución.
        identification = deviceConnection.identification(db, actor, idInstitucion, membership)
        _institutionSteps(steps, identification)
        device = None if identification["dispositivo"] is None else db.get(Device, identification["dispositivo"]["idDispositivo"])
    elif code is None:
        steps.append(_step("REGISTRADO", "Dispositivo registrado", "PENDIENTE", "Se comprueba cuando el puente informe el código de su dispositivo."))
    else:
        device = db.scalar(select(Device).where(func.lower(Device.codigoDispositivo) == code.strip().lower()))
        waiting = False
        if device is None and not hub.registrationAllowed():
            waiting = True  # todavía no hay comunicación verificada, o el firmware aún puede informar su ID propio
        if device is None and not waiting:
            # Normalmente el puente lo registra solo; si no está (p. ej. se borró), se intenta de nuevo ahora. Solo un código inválido falla.
            try:
                device = deviceService.registerFromBridge(db, code.strip())
            except Exception:  # noqa: BLE001
                db.rollback()
                logger.exception("No se pudo registrar automáticamente el dispositivo informado por el puente")
        if device is None and waiting:
            steps.append(_step("REGISTRADO", "Dispositivo registrado", "PENDIENTE",
                               "Se está identificando el dispositivo: se espera su identificador propio antes de registrarlo.",
                               "Esperá unos segundos con el Arduino encendido y transmitiendo."))
        elif device is None:
            steps.append(_step("REGISTRADO", "Dispositivo registrado", "ERROR",
                               f"El dispositivo «{code}» no se pudo registrar automáticamente en el inventario.",
                               "Revisá BRIDGE_DEVICE_CODE: tiene que tener entre 3 y 100 caracteres (letras, números y . _ : -, sin espacios)."))
        else:
            steps.append(_step("REGISTRADO", "Dispositivo registrado", "OK", f"«{device.codigoDispositivo}» figura en el inventario ({device.modeloSensor})."))

    access = None
    operatorContext = False
    if idPerfilMedicion is None and membership is not None:
        # El paciente se elige al medir; acá se comprueba que la institución del operador pueda usar el dispositivo identificado.
        usable = identification is not None and identification["dispositivo"] is not None and identification["usable"]
        if device is None:
            steps.append(_step("ASOCIADO", "Dispositivo asociado al perfil", "PENDIENTE", "Primero tiene que estar identificado y registrado."))
        elif usable:
            operatorContext = True
            steps.append(_step("ASOCIADO", "Dispositivo asociado al perfil", "OK",
                               "Tu institución puede usar este dispositivo; el paciente se elige al iniciar la medición."))
        elif identification["situacion"] == "SIN_INSTITUCION":
            steps.append(_step("ASOCIADO", "Dispositivo asociado al perfil", "PENDIENTE",
                               "El dispositivo todavía no pertenece al inventario de tu institución, y un paciente se mide solo con los de su institución.",
                               "Vinculalo a tu institución en «Dispositivo de esta conexión»."))
        else:
            steps.append(_step("ASOCIADO", "Dispositivo asociado al perfil", "ERROR",
                               f"El dispositivo está conectado, pero todavía no está asociado a tu institución: {identification['motivoNoDisponible']}",
                               "Pedí a la administración que lo deje operativo y sin asignar a otra institución."))
    elif idPerfilMedicion is None and actor.tipoCuenta == TIPO_INSTITUCIONAL:
        # El operador no tiene un perfil propio: el paciente se elige al medir. Acá se comprueba lo que sí se sabe de antemano,
        # que alguna de sus instituciones pueda usar el dispositivo (sin asignar, de su institución o en custodia del propietario).
        if device is None:
            steps.append(_step("ASOCIADO", "Dispositivo asociado al perfil", "PENDIENTE", "Primero tiene que estar registrado."))
        else:
            relations = db.scalars(select(InstitutionUser).where(
                InstitutionUser.idUsuarioInvitado == actor.idUsuario, InstitutionUser.rolInstitucion == "OPERADOR",
                InstitutionUser.estadoRelacion == "ACTIVO",
                InstitutionUser.idInstitucion.in_(institutions.operatingInstitutionIds(db, actor)))).all()
            results = [deviceService.usableBy(device, r.idInstitucion, r.idInstitucionUsuario) for r in relations]
            if any(usable for usable, _ in results):
                operatorContext = True
                steps.append(_step("ASOCIADO", "Dispositivo asociado al perfil", "OK",
                                   "Tu institución puede usar este dispositivo; el paciente se elige al iniciar la medición."))
            else:
                reason = next((why for _, why in results if why), "El dispositivo no está disponible para tu institución.")
                steps.append(_step("ASOCIADO", "Dispositivo asociado al perfil", "ERROR",
                                   f"El dispositivo está conectado, pero todavía no está asociado a tu institución: {reason}",
                                   "Pedí a la administración que lo deje operativo y sin asignar a otra institución."))
    elif idPerfilMedicion is None:
        steps.append(_step("ASOCIADO", "Dispositivo asociado al perfil", "PENDIENTE", "Elegí un perfil para comprobarlo."))
    else:
        access = measurements._access(db, actor, db.get(MeasurementProfile, idPerfilMedicion), "PERFIL_NO_ENCONTRADO", measurements.PROFILE_NOT_FOUND)
        measurements._requireOperate(access)
        if device is None:
            steps.append(_step("ASOCIADO", "Dispositivo asociado al perfil", "PENDIENTE", "Primero tiene que estar registrado."))
        else:
            usable, reason = measurements.deviceService.usableBy(device, access.idInstitucion, measurements._operatorRelation(access))
            if usable:
                steps.append(_step("ASOCIADO", "Dispositivo asociado al perfil", "OK", "El perfil puede usar este dispositivo."))
            elif access.idInstitucion is None and device.idInstitucionAsignada is not None and device.estado == measurements.DEVICE_OPERATIVO:
                # Cuenta individual frente a un dispositivo de una institución: no se pide ningún operador ni «administración» para ella.
                steps.append(_step("ASOCIADO", "Dispositivo asociado al perfil", "ERROR",
                                   "El dispositivo conectado está registrado en una institución: una cuenta individual no puede medir con él.",
                                   "Conectá tu propio Arduino (sin institución). Si este es tu dispositivo, pedí a esa institución que lo libere."))
            else:
                steps.append(_step("ASOCIADO", "Dispositivo asociado al perfil", "ERROR",
                                   f"El dispositivo está conectado, pero todavía no está asociado a este perfil: {reason}",
                                   "Pedí a la administración que lo deje operativo y sin asignar a otra institución."))

    busy = snap["ocupado"]
    blocker = next((s for s in steps if s["estado"] != "OK"), None)
    ready = blocker is None and (idPerfilMedicion is not None or operatorContext) and not busy
    if busy:
        steps.append(_step("DISPONIBLE", "Disponible para medir", "ERROR", "Otra cuenta está midiendo con este dispositivo.", "Esperá a que termine."))
    elif ready:
        steps.append(_step("DISPONIBLE", "Disponible para medir", "OK", "Dispositivo listo para medir."))
    else:
        steps.append(_step("DISPONIBLE", "Disponible para medir", "PENDIENTE", "Todavía no: resolvé el primer paso pendiente."))
    return {
        "listo": ready, "bloqueo": next((s["id"] for s in steps if s["estado"] != "OK"), None), "pasos": steps,
        "dispositivo": None if device is None else {"idDispositivo": str(device.idDispositivo), "codigoDispositivo": device.codigoDispositivo,
                                                    "nombre": device.nombre, "modeloSensor": device.modeloSensor},
        "identificacion": identification,
        "ordenesPuente": bridgeAuthority(db, actor)[0],
    }


def _institutionSteps(steps: list[dict], identification: dict) -> None:
    """Pasos de identidad y registro para un operador (reemplazan al «registrado» genérico: acá se mira SU inventario)."""
    level, situation = identification["nivel"], identification["situacion"]
    if situation == "SIN_COMUNICACION":
        pending = "Se comprueba cuando haya comunicación verificada con el Arduino."
        steps.append(_step("IDENTIDAD", "Dispositivo identificado", "PENDIENTE", pending))
        steps.append(_step("REGISTRADO", "Dispositivo registrado", "PENDIENTE", pending))
        return
    if level == "FISICA":
        steps.append(_step("IDENTIDAD", "Dispositivo identificado", "OK",
                           "El Arduino informó su identificador propio: no depende del puerto COM ni del medio de conexión."))
    elif identification["confirmada"]:
        steps.append(_step("IDENTIDAD", "Dispositivo identificado", "OK", "Confirmaste manualmente qué dispositivo es (este firmware no informa un identificador propio)."))
    else:
        steps.append(_step("IDENTIDAD", "Dispositivo identificado", "PENDIENTE",
                           "No se pudo confirmar qué Arduino es: este firmware no informa un identificador propio.",
                           "Confirmá explícitamente cuál es en «Dispositivo de esta conexión» (o cargá el firmware actualizado)."))
        steps.append(_step("REGISTRADO", "Dispositivo registrado", "PENDIENTE", "Se comprueba cuando confirmes cuál es."))
        return
    device = identification["dispositivo"]
    if situation == "NO_REGISTRADO":
        steps.append(_step("REGISTRADO", "Dispositivo registrado", "PENDIENTE", "Es un dispositivo nuevo: todavía no está en el inventario.",
                           "Usá «Registrar nuevo dispositivo» en «Dispositivo de esta conexión»."))
    elif situation in ("DE_OTRA_INSTITUCION", "SIN_INSTITUCION") and identification.get("compartido") and device is not None:
        label = device["nombre"] or device["codigoDispositivo"]
        steps.append(_step("REGISTRADO", "Dispositivo registrado", "OK",
                           f"«{label}» es el equipo de uso compartido: se puede medir sin cambiar su titularidad."))
    elif situation == "DE_OTRA_INSTITUCION":
        steps.append(_step("REGISTRADO", "Dispositivo registrado", "ERROR", "El dispositivo está registrado en otra institución.",
                           "No se transfiere automáticamente: pedí a la administración de GlucoLume su reasignación."))
    elif situation == "SIN_INSTITUCION" and device is not None:
        steps.append(_step("REGISTRADO", "Dispositivo registrado", "PENDIENTE",
                           f"«{device['nombre'] or device['codigoDispositivo']}» existe, pero todavía no está en el inventario de tu institución.",
                           "Vinculalo a tu institución en «Dispositivo de esta conexión» (pide una confirmación explícita)."))
    elif device is not None:
        where = "figura en el inventario de tu institución" if situation == "DE_LA_INSTITUCION" else "figura en el inventario, sin institución asignada"
        label = device["nombre"] or device["codigoDispositivo"]
        steps.append(_step("REGISTRADO", "Dispositivo registrado", "OK", f"«{label}» {where}."))


def settleExpired(db: Session) -> None:
    """Libera la reserva vencida o abandonada y cierra su medición (CANCELADA, con auditoría). Idempotente y segura: no toca una sesión
    viva, ni una que se está guardando, ni mediciones ya guardadas."""
    hub.expireSession()
    for session in hub.takeExpired():
        try:
            measurements.cancelAbandoned(db, session.idMedicion, session.userId, session.reason or "ABANDONADA")
        except Exception:  # noqa: BLE001 - liberar el equipo no puede fallar por un problema de auditoría
            db.rollback()
            logger.exception("No se pudo cerrar la medición de una sesión abandonada (%s)", session.idMedicion)


def releaseOnLogout(db: Session, actor: User) -> None:
    """Al cerrar sesión, la adquisición pendiente de esa cuenta se cancela y el dispositivo queda libre. No afecta lo ya guardado."""
    settleExpired(db)
    with hub.lock:
        session = hub.session
        if session is None or session.userId != actor.idUsuario or session.saving:
            return
        hub.release(session)
    if session.idMedicion is not None:
        measurements.cancelAbandoned(db, session.idMedicion, actor.idUsuario, "CIERRE_DE_SESION")


def status(db: Session, actor: User) -> dict:
    """Estado del dispositivo y última lectura. Solo cuentas que pueden medir; si otra cuenta tiene la sesión, solo
    se informa que está ocupado (sin lecturas)."""
    _requireMeasurer(db, actor)
    settleExpired(db)
    return hub.snapshot(actor.idUsuario)


# --- Sesión ---------------------------------------------------------------------------------------------------------------


def _ownSession(actor: User):
    session = hub.session
    if session is None or session.idMedicion is None:
        raise AuthError("ADQUISICION_NO_ACTIVA", "No hay una sesión de medición en curso.")
    if session.userId != actor.idUsuario:
        raise AuthError("DISPOSITIVO_EN_USO", "El dispositivo está siendo usado por otra cuenta.")
    return session


def _requireGlucoseSchema(db: Session) -> None:
    """Medir glucosa con el dispositivo necesita las restricciones de origen de la glucosa del esquema v5 (el origen del dato y el valor del firmware ya no se limitan a
    OXIMETRIA). Con el esquema viejo la base rechazaría el guardado AL FINAL de la sesión: se avisa antes de empezar."""
    if not schemaCompat.glucoseDeviceModeReady(db):
        raise AuthError("ESQUEMA_DESACTUALIZADO", "La base de datos instalada todavía no admite medir glucosa con el dispositivo (falta actualizarla al "
                        "esquema vigente). Mientras tanto podés medir en modo Oximetría.")


def _requireSameDevice(actor: User, access, device: Device, bridge, which: str) -> dict:
    """El Arduino que está conectado ahora es el dispositivo `device`. Con ID propio se compara ese ID (nunca el puerto). Si el
    firmware no informa uno, un operador solo puede medir con el dispositivo que confirmó a mano para esta conexión; las cuentas
    individuales siguen usando el código configurado en el puente, como siempre."""
    identity = hub.identity()
    if bridge is None or identity["codigo"] is None:
        raise AuthError("DISPOSITIVO_NO_COINCIDE", f"El dispositivo conectado por el puente no es el {which}.")
    if identity["nivel"] == "DECLARADA" and access.relation is not None:
        if not hub.isConfirmed(actor.idUsuario, device.idDispositivo):
            raise AuthError("IDENTIDAD_NO_CONFIRMADA", "No se pudo confirmar qué Arduino está conectado: confirmá el dispositivo en «Conectar dispositivo».")
        return identity
    if device.codigoDispositivo.strip().lower() != identity["codigo"].strip().lower():
        raise AuthError("DISPOSITIVO_NO_COINCIDE", f"El dispositivo conectado por el puente no es el {which}.")
    return identity


def startSession(db: Session, actor: User, data: TelemetrySessionStart) -> MeasurementDetail:
    _requireMeasurer(db, actor)
    if data.modoMedicion == "GLUCOSA_EXPERIMENTAL":
        _requireGlucoseSchema(db)
    settleExpired(db)  # una reserva vencida o abandonada no bloquea el equipo
    if link.session is not None and link.session.state in ("ADQUIRIENDO", "FINALIZANDO"):
        raise AuthError("ADQUISICION_ACTIVA", "Hay una adquisición con muestras crudas en curso: finalizala o cancelala antes.")
    state = hub.deviceState()
    if state != "CONECTADO":
        raise _notConnected(state)
    bridge = hub.bridge
    access = measurements._access(db, actor, db.get(MeasurementProfile, data.idPerfilMedicion), "PERFIL_NO_ENCONTRADO",
                                  measurements.PROFILE_NOT_FOUND)
    measurements._requireOperate(access)
    device = db.get(Device, data.idDispositivo)
    if device is None or not measurements._deviceUsable(device, access.idInstitucion, measurements._operatorRelation(access)):
        raise AuthError("DISPOSITIVO_NO_DISPONIBLE", "El dispositivo no está disponible para medir este perfil.")
    identity = _requireSameDevice(actor, access, device, bridge, "elegido para esta medición")
    if identity["nivel"] == "FISICA":
        deviceService.syncConnection(db, actor, device, firmware=identity["firmware"], medio=bridge.medium, identidad="FISICA")
    try:
        session = hub.reserve(actor.idUsuario)
    except PermissionError as error:
        raise AuthError("DISPOSITIVO_EN_USO", str(error)) from error
    except ValueError as error:
        raise AuthError("ADQUISICION_ACTIVA", "Ya tenés una sesión de medición en curso con el dispositivo.") from error
    try:
        started = measurements.startMeasurement(db, actor, MeasurementStart(
            idPerfilMedicion=data.idPerfilMedicion, idDispositivo=data.idDispositivo, modoMedicion=data.modoMedicion,
            fechaHoraUltimaComida=data.fechaHoraUltimaComida, condicionComida=data.condicionComida,
            observacion=data.observacion, edadAlMomento=data.edadAlMomento, sexoModelo=data.sexoModelo), deviceSession=True)
        if not measurements._transition(db, started.idMedicion, (measurements.PENDIENTE,), measurements.ADQUIRIENDO):
            db.rollback()
            raise measurements._stateError(db.get(Measurement, started.idMedicion))
        registerEvent(db, "CRUD", "INICIAR_SESION_DISPOSITIVO", True, actor.idUsuario, "Medicion", started.idMedicion,
                      datosPrevios={"estadoMedicion": measurements.PENDIENTE},
                      datosNuevos={"estadoMedicion": measurements.ADQUIRIENDO, "medio": bridge.medium})
        db.commit()
    except BaseException:
        hub.release(session)
        raise
    hub.bind(session, started.idMedicion, device.codigoDispositivo, data.modoMedicion)
    db.expire_all()
    return measurements.getMeasurement(db, actor, started.idMedicion)


def saveSession(db: Session, actor: User) -> MeasurementDetail:
    """Guarda la medición con una lectura estabilizada. La sesión se libera SOLO después del commit."""
    _requireMeasurer(db, actor)
    settleExpired(db)
    with hub.lock:
        session = _ownSession(actor)
        if session.saving:
            raise AuthError("GUARDADO_EN_CURSO", "Ya se está guardando esta medición.")
        session.saving = True
    try:
        return _persist(db, actor, session)
    except BaseException:
        db.rollback()
        session.saving = False
        raise


def _persist(db: Session, actor: User, session) -> MeasurementDetail:
    measurement, access = measurements._measurementAccess(db, actor, session.idMedicion)
    measurements._requireOperate(access)
    measurements._requireExperimentalConsent(db, actor, access.profile)  # revocar frena también el guardado de una sesión en curso
    previous = measurement.estadoMedicion
    if previous not in (measurements.PENDIENTE, measurements.ADQUIRIENDO):
        raise measurements._stateError(measurement)
    device = db.get(Device, measurement.idDispositivo)
    if device is None or device.estado != measurements.DEVICE_OPERATIVO:
        raise AuthError("DISPOSITIVO_NO_DISPONIBLE", "El dispositivo ya no está operativo: no se puede guardar la medición.")
    state = hub.deviceState()
    if state != "CONECTADO":
        raise _notConnected(state)
    _requireSameDevice(actor, access, device, hub.bridge, "de esta medición")
    verdict = hub.stability()
    if isinstance(verdict, Unstable):
        raise AuthError("LECTURA_NO_ESTABLE", verdict.message)
    stable: Stable = verdict
    if measurement.modoMedicion == measurements.GLUCOSA and stable.glucosa is None:  # defensa: nunca se completa sin el resultado de su modo
        raise AuthError("LECTURA_NO_ESTABLE", UNSTABLE_MESSAGES["GLUCOSA_NO_DISPONIBLE"])

    demo = stable.origen == "DEMO"
    note = " ".join(part for part in (measurement.observacion, DEMO_NOTE if demo else None) if part)[:500] or None
    end = measurements._endTime(measurement)
    glucose = Decimal(str(stable.glucosa)) if stable.glucosa is not None else None
    if not measurements._transition(
        db, session.idMedicion, (measurements.PENDIENTE, measurements.ADQUIRIENDO), measurements.COMPLETADA,
        fechaHoraFin=end, spo2=Decimal(str(stable.spo2)), frecuenciaCardiaca=stable.bpm, calidadSenal=None,
        versionAlgoritmo=FIRMWARE_ALGORITHM, observacion=note, origenGlucosa=stable.origen, glucosaDispositivo=glucose,
        unidadGlucosa="mg/dL" if glucose is not None else None, indiceOptico=Decimal(str(stable.indiceOptico)),
        lecturasEstabilizadas=stable.lecturas,
    ):
        db.rollback()
        raise measurements._stateError(measurement)
    if not demo:  # una prueba no cuenta como «última medición» del perfil
        db.execute(update(MeasurementProfile).where(
            MeasurementProfile.idPerfilMedicion == measurement.idPerfilMedicion,
            or_(MeasurementProfile.fechaUltimaMedicion.is_(None), MeasurementProfile.fechaUltimaMedicion < end),
        ).values(fechaUltimaMedicion=end).execution_options(synchronize_session=False))
    registerEvent(
        db, "CRUD", "GUARDAR_MEDICION_DISPOSITIVO", True, actor.idUsuario, "Medicion", session.idMedicion,
        datosPrevios={"estadoMedicion": previous},
        datosNuevos={"estadoMedicion": measurements.COMPLETADA, "origenGlucosa": stable.origen,
                     "lecturasEstabilizadas": stable.lecturas, "versionAlgoritmo": FIRMWARE_ALGORITHM},
        tablaRelacionada="InstitucionUsuario" if access.relation else None,
        idRelacionado=access.relation.idInstitucionUsuario if access.relation else None)
    db.commit()  # la medición queda confirmada solo si llega hasta aquí
    hub.release(session)  # la sesión se libera recién ahora: una falla anterior deja la sesión para reintentar

    if not demo:
        try:
            owner = db.get(MeasurementProfile, measurement.idPerfilMedicion).idUsuario
            ownerUser = db.get(User, owner) if owner is not None else None
            if ownerUser is not None:
                notifications.notifyGroupMeasurement(db, ownerUser, end)
        except Exception:  # noqa: BLE001 - el aviso al grupo nunca deshace una medición ya confirmada
            logger.exception("No se pudo enviar el aviso de medición al grupo (medición %s)", session.idMedicion)
    autoSend = None
    try:
        autoSend = measurements.autoSendResult(db, actor, session.idMedicion)  # también las pruebas DEMO (identificadas como simuladas)
    except Exception:  # noqa: BLE001 - el correo nunca deshace una medición ya confirmada
        logger.exception("No se pudo enviar el resultado automático (medición %s)", session.idMedicion)
        db.rollback()
        autoSend = "FALLIDO"
    db.expire_all()
    detail = measurements.getMeasurement(db, actor, session.idMedicion)
    detail.envioAutomatico = autoSend
    return detail


def cancelSession(db: Session, actor: User) -> MeasurementDetail:
    _requireMeasurer(db, actor)
    settleExpired(db)
    session = _ownSession(actor)
    if session.saving:
        raise AuthError("GUARDADO_EN_CURSO", "Se está guardando la medición: esperá a que termine.")
    try:
        detail = measurements.cancelMeasurement(db, actor, session.idMedicion, operation="SESION_DISPOSITIVO")
    except AuthError as error:
        if error.code == "MEDICION_ESTADO_INVALIDO":
            hub.release(session)  # la medición ya no está en curso: la sesión quedó huérfana
        raise
    hub.release(session)
    return detail
