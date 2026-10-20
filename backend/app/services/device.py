# Device - Inventario de dispositivos (RF35, RF36, RF37; RN43, RN44, RN45)
#
# Reutiliza dbo.Dispositivo: no hay otra tabla de inventario. Separación de responsabilidades:
#   - Inventario (este módulo): registrar, consultar, modificar, asignar y retirar dispositivos físicos;
#   - Adquisición: la comunicación con el Arduino (USB/Bluetooth) vive en el servicio de adquisición, no acá. Solo
#     le ofrece `resolveDevice` para traducir el identificador que informa el firmware en un registro de inventario;
#   - Medición: guarda Medicion.idDispositivo y el firmware y sensor de ESE momento, por lo que modificar o reasignar
#     el dispositivo no altera lo ya medido.
#
# Estados (CK_Dispositivo_estado): OPERATIVO, EN_MANTENIMIENTO, FUERA_DE_SERVICIO y BAJA (= «descomisionado»). Solo
# OPERATIVO permite iniciar y continuar adquisiciones. «Operativo» no es «conectado»: no se guarda ni se infiere la
# conexión. BAJA es terminal: conserva la institución de origen y la referencia histórica del responsable (el
# inventario institucional lo sigue mostrando como «Descomisionado», sin acciones) y nunca vuelve a usarse.
#
# Quién puede qué (cada permiso se verifica acá, con el rol real y el contexto institucional de la ruta):
#   Administrador del sistema  todo el inventario global, incluida la asignación a instituciones y el retiro;
#   Moderación de plataforma   consulta, alta, edición de datos técnicos y cambio de estado; NO asigna a instituciones
#                              ni descomisiona (no se equipara con el administrador);
#   Propietario institucional  su inventario: alta (queda asignado a su institución y a su PROPIETARIO vigente), cambio
#                              de estado y descomisionar;
#   Moderador institucional    su inventario: alta (igual que el propietario) y cambio de estado;
#   Operador institucional     solo consulta los dispositivos operativos que puede usar (los sin responsable o a su
#                              cargo), con datos técnicos mínimos.
# Alta: el flujo normal es la PRIMERA CONEXIÓN de un operador (registerFromConnection): al confirmarse la comunicación con el
# Arduino, el operador lo registra con un nombre y queda en el inventario de su institución, a cargo del propietario vigente
# (el operador no adquiere la titularidad ni puede cambiarla; el alta lo deja en la auditoría con su identidad y la fecha).
# El alta manual (registerDevice) se conserva para el administrador y para propietario/moderador, que registran un equipo
# que todavía no se conectó (o con firmware sin identificador): comparte el código único, así que nunca duplica.
# La institución NO elige responsable ni desvincula: el alta lo asigna al propietario vigente (se rechaza si no se puede
# determinar con certeza). Propietario y moderador editan el nombre y el modelo; el sensor y el firmware los informa la
# conexión (o los corrige la plataforma). El responsable que es el propietario es custodia institucional, no exclusiva: no
# impide que los operadores usen el equipo.
# Una institución solo ve y administra los dispositivos asignados a ella; los demás responden como inexistentes.
# Retirar o desvincular un dispositivo con mediciones en curso se rechaza. Nunca se borran dispositivos ni mediciones.
# Fechas: UTC, igual que fechaRegistro (sysutcdatetime()).

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session

from app.core.config import getSettings
from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.device import Device
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.user import User
from app.schemas.device import (
    ESTADO_ALIAS,
    DeviceAssignRequest,
    DeviceDetail,
    DeviceEditRequest,
    DeviceInstitutionOption,
    DeviceItem,
    DeviceMeasurementItem,
    DeviceMeasurementPage,
    DevicePage,
    DevicePermissions,
    DeviceRegisterRequest,
    DeviceRegistration,
    DeviceResolveRequest,
    DeviceResolveResult,
    DeviceResponsible,
    DeviceSummaryCounts,
)
from app.services import institution as institutions
from app.services.audit import registerEvent

OPERATIVO, EN_MANTENIMIENTO, FUERA_DE_SERVICIO, BAJA = "OPERATIVO", "EN_MANTENIMIENTO", "FUERA_DE_SERVICIO", "BAJA"
ESTADOS = (OPERATIVO, EN_MANTENIMIENTO, FUERA_DE_SERVICIO, BAJA)
ACTIVE_MEASUREMENTS = ("PENDIENTE", "ADQUIRIENDO", "PROCESANDO")
PLATFORM_ADMIN = "ADMINISTRADOR_PLATAFORMA"
PLATFORM_MODERATOR = "MODERADOR_PLATAFORMA"
MAX_PAGE_SIZE = 100
INSTITUTION_EDITABLE = {"nombre", "modelo"}
BRIDGE_MODEL = "Arduino UNO + MAX30100"

NOT_FOUND = "No encontramos ese dispositivo."
DENIED = "No tenés permiso para realizar esta operación sobre los dispositivos."
DUPLICATE = "Ya hay un dispositivo registrado con ese código."
IN_USE = "El dispositivo tiene mediciones en curso: finalizalas o cancelalas antes de continuar."
RETIRED = "El dispositivo está descomisionado: ya no admite cambios."


def _error(code: str, message: str) -> AuthError:
    return AuthError(code, message)


def _utcNow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --- Alcance y capacidades ------------------------------------------------------------------------------------

CAPABILITIES = {
    PLATFORM_ADMIN: {"ver", "registrar", "editar", "estado", "asignar", "responsable", "desvincular", "descomisionar", "mediciones"},
    PLATFORM_MODERATOR: {"ver", "registrar", "editar", "estado", "mediciones"},
}


@dataclass(frozen=True)
class Scope:
    actor: User
    capabilities: frozenset
    idInstitucion: uuid.UUID | None = None  # None: inventario global (plataforma)
    membership: institutions.Membership | None = None

    @property
    def isOperator(self) -> bool:
        return self.membership is not None and self.membership.role == institutions.ROL_OPERADOR

    def can(self, capability: str) -> bool:
        return capability in self.capabilities


def _institutionCapabilities(membership: institutions.Membership) -> frozenset:
    caps = set()
    if membership.can(institutions.P_DISPOSITIVOS):
        caps.add("ver")
    if membership.can(institutions.P_DISPOSITIVOS_GESTIONAR):
        caps |= {"registrar", "editar", "estado", "mediciones"}
    if membership.can(institutions.P_DISPOSITIVOS_RETIRAR):
        caps.add("descomisionar")
    return frozenset(caps)


def _denied(db: Session, scope_or_actor, action: str, device: Device | None = None, idInstitucion=None) -> AuthError:
    """Registra el intento rechazado (resultado FALLO, con un único alta) y devuelve el 403."""
    actor = scope_or_actor.actor if isinstance(scope_or_actor, Scope) else scope_or_actor
    registerEvent(db, "PERMISO", action, False, actor.idUsuario, "Dispositivo" if device else None,
                  device.idDispositivo if device else None, "Motivo: PERMISO_INSUFICIENTE", modulo="DISPOSITIVOS",
                  idInstitucion=idInstitucion)
    db.commit()
    return _error("PERMISO_INSUFICIENTE", DENIED)


def platformScope(db: Session, actor: User) -> Scope:
    caps = CAPABILITIES.get(actor.tipoCuenta)
    if caps is None or actor.estado != "ACTIVO":
        raise _denied(db, actor, "ACCEDER_INVENTARIO_DISPOSITIVOS")
    return Scope(actor, frozenset(caps))


def institutionScope(db: Session, actor: User, idInstitucion: uuid.UUID) -> Scope:
    """Vínculo ACTIVO con la institución ACTIVA (404 si no pertenece; 403 si la cuenta no es institucional)."""
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_DISPOSITIVOS)
    return Scope(actor, _institutionCapabilities(membership), idInstitucion, membership)


def _require(db: Session, scope: Scope, capability: str, action: str, device: Device | None = None) -> None:
    if not scope.can(capability):
        raise _denied(db, scope, action, device, scope.idInstitucion or (device.idInstitucionAsignada if device else None))


def _load(db: Session, scope: Scope, idDispositivo: uuid.UUID) -> Device:
    device = db.get(Device, idDispositivo)
    if device is None or (scope.idInstitucion is not None and device.idInstitucionAsignada != scope.idInstitucion):
        raise _error("DISPOSITIVO_NO_ENCONTRADO", NOT_FOUND)  # el de otra institución no existe para este ámbito
    if scope.isOperator and not _operatorSees(device, scope.membership.relation.idInstitucionUsuario):
        raise _error("DISPOSITIVO_NO_ENCONTRADO", NOT_FOUND)
    return device


def _operatorSees(device: Device, relationId: uuid.UUID) -> bool:
    return device.estado == OPERATIVO and (device.idInstitucionUsuarioResponsable in (None, relationId) or _heldByOwner(device))


def _heldByOwner(device: Device) -> bool:
    """¿El responsable es el PROPIETARIO de la institución? Esa custodia es institucional y no excluye a los operadores
    (el alta asigna todo al propietario: si lo excluyera, nadie más podría medir con los dispositivos de la institución)."""
    session = object_session(device)
    if session is None or device.idInstitucionUsuarioResponsable is None:
        return False
    return session.scalar(select(InstitutionUser.rolInstitucion).where(
        InstitutionUser.idInstitucionUsuario == device.idInstitucionUsuarioResponsable)) == institutions.ROL_PROPIETARIO


def _ownerRelations():
    """Vínculos de PROPIETARIO (subconsulta para filtrar en SQL los dispositivos en custodia del propietario)."""
    return select(InstitutionUser.idInstitucionUsuario).where(InstitutionUser.rolInstitucion == institutions.ROL_PROPIETARIO)


def currentOwner(db: Session, idInstitucion: uuid.UUID) -> InstitutionUser:
    """El PROPIETARIO vigente de la institución. Si no hay exactamente uno ACTIVO, no se adivina: se rechaza."""
    owners = db.scalars(select(InstitutionUser).where(
        InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.rolInstitucion == institutions.ROL_PROPIETARIO,
        InstitutionUser.estadoRelacion == institutions.RELACION_ACTIVO)).all()
    if len(owners) != 1:
        raise _error("PROPIETARIO_NO_DETERMINADO",
                     "No se pudo determinar el propietario vigente de la institución: el dispositivo no se registró.")
    return owners[0]


# --- Lectura ----------------------------------------------------------------------------------------------------


def _responsible(db: Session, device: Device) -> DeviceResponsible | None:
    if device.idInstitucionUsuarioResponsable is None:
        return None
    relation = db.get(InstitutionUser, device.idInstitucionUsuarioResponsable)
    user = db.get(User, relation.idUsuarioInvitado) if relation else None
    if relation is None:
        return None
    return DeviceResponsible(
        idInstitucionUsuario=relation.idInstitucionUsuario,
        nombre=(user.nombre if user else None) or relation.nombreProfesionalHistorico,
        apellido=(user.apellido if user else None) or relation.apellidoProfesionalHistorico,
        activo=relation.estadoRelacion == institutions.RELACION_ACTIVO,
    )


def _item(db: Session, device: Device, scope: Scope) -> DeviceItem:
    mine = bool(scope.membership and device.idInstitucionUsuarioResponsable == scope.membership.relation.idInstitucionUsuario)
    institution = db.get(Institution, device.idInstitucionAsignada) if (scope.idInstitucion is None and device.idInstitucionAsignada) else None
    operator = scope.isOperator
    return DeviceItem(
        idDispositivo=device.idDispositivo, codigoDispositivo=device.codigoDispositivo, nombre=device.nombre,
        modelo=device.modelo, modeloSensor=device.modeloSensor, versionFirmware=device.versionFirmware, estado=device.estado,
        idInstitucionAsignada=device.idInstitucionAsignada, nombreInstitucion=institution.nombre if institution else None,
        # El operador ve solo lo mínimo: su propia responsabilidad, sin datos administrativos.
        responsable=None if operator and not mine else _responsible(db, device),
        fechaRegistro=device.fechaRegistro, fechaAsignacionInstitucional=None if operator else device.fechaAsignacionInstitucional,
        disponibleParaMedir=device.estado == OPERATIVO, esMio=mine,
    )


def _permissions(device: Device, scope: Scope) -> DevicePermissions:
    active = device.estado != BAJA
    assigned = device.idInstitucionAsignada is not None
    return DevicePermissions(
        puedeEditar=scope.can("editar") and active, puedeCambiarEstado=scope.can("estado") and active,
        puedeAsignarInstitucion=scope.can("asignar") and active, puedeCambiarResponsable=scope.can("responsable") and active and assigned,
        puedeDesvincular=scope.can("desvincular") and active and assigned, puedeDescomisionar=scope.can("descomisionar") and active,
        puedeVerMediciones=scope.can("mediciones"),
    )


def _usage(db: Session, device: Device, idInstitucion: uuid.UUID | None = None) -> int:
    """Mediciones hechas con el dispositivo. Una institución no cuenta las de pacientes de OTRA (si el dispositivo se reasignó): coincide con lo
    que listMeasurements le deja ver. Las de cuentas individuales previas a la vinculación sí se cuentan (el historial no se pierde)."""
    query = select(func.count()).select_from(Measurement).where(Measurement.idDispositivo == device.idDispositivo)
    if idInstitucion is not None:
        foreign = (select(MeasurementProfile.idPerfilMedicion)
                   .join(InstitutionUser, InstitutionUser.idInstitucionUsuario == MeasurementProfile.idInstitucionUsuarioResponsable)
                   .where(InstitutionUser.idInstitucion != idInstitucion))
        query = query.where(Measurement.idPerfilMedicion.not_in(foreign))
    return db.scalar(query)


def getDevice(db: Session, scope: Scope, idDispositivo: uuid.UUID) -> DeviceDetail:
    _require(db, scope, "ver", "CONSULTAR_DISPOSITIVO")
    device = _load(db, scope, idDispositivo)
    return DeviceDetail(**_item(db, device, scope).model_dump(), permisos=_permissions(device, scope),
                        medicionesRegistradas=_usage(db, device, scope.idInstitucion) if scope.can("mediciones") else None,
                        # Quién lo registró: dato administrativo, no se informa al operador.
                        registro=registration(db, device, scope.idInstitucion) if scope.can("ver") and not scope.isOperator else None)


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _filtered(query, scope: Scope, *, busqueda, estado, asignado, idInstitucion):
    if scope.idInstitucion is not None:
        query = query.where(Device.idInstitucionAsignada == scope.idInstitucion)
        if scope.isOperator:
            query = query.where(Device.estado == OPERATIVO,
                                or_(Device.idInstitucionUsuarioResponsable.is_(None),
                                    Device.idInstitucionUsuarioResponsable == scope.membership.relation.idInstitucionUsuario,
                                    Device.idInstitucionUsuarioResponsable.in_(_ownerRelations())))
    elif idInstitucion is not None:
        query = query.where(Device.idInstitucionAsignada == idInstitucion)
    if estado:
        query = query.where(Device.estado == ESTADO_ALIAS.get(estado, estado))
    if asignado is True:
        query = query.where(Device.idInstitucionAsignada.is_not(None))
    elif asignado is False:
        query = query.where(Device.idInstitucionAsignada.is_(None))
    if busqueda and busqueda.strip():
        term = _like(busqueda.strip())
        query = query.where(or_(Device.codigoDispositivo.ilike(term, escape="\\"), Device.nombre.ilike(term, escape="\\"),
                                Device.modelo.ilike(term, escape="\\")))
    return query


def _checkFilters(estado) -> None:
    if estado is not None and ESTADO_ALIAS.get(estado, estado) not in ESTADOS:
        raise _error("DATOS_INVALIDOS", "El estado indicado no es válido.")


def listDevices(db: Session, scope: Scope, *, busqueda=None, estado=None, asignado=None, idInstitucion=None, pagina=1,
                tamanioPagina=20) -> DevicePage:
    _require(db, scope, "ver", "CONSULTAR_INVENTARIO_DISPOSITIVOS")
    _checkFilters(estado)
    tamanioPagina = max(1, min(tamanioPagina, MAX_PAGE_SIZE))
    pagina = max(1, pagina)
    base = _filtered(select(Device), scope, busqueda=busqueda, estado=estado, asignado=asignado, idInstitucion=idInstitucion)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.scalars(base.order_by(Device.fechaRegistro.desc(), Device.codigoDispositivo)
                      .offset((pagina - 1) * tamanioPagina).limit(tamanioPagina)).all()
    return DevicePage(items=[_item(db, d, scope) for d in rows], total=total, pagina=pagina, tamanioPagina=tamanioPagina)


def summary(db: Session, scope: Scope, *, idInstitucion=None) -> DeviceSummaryCounts:
    _require(db, scope, "ver", "CONSULTAR_INVENTARIO_DISPOSITIVOS")
    base = _filtered(select(Device.estado, Device.idInstitucionAsignada), scope, busqueda=None, estado=None, asignado=None,
                     idInstitucion=idInstitucion).subquery()

    def count(*conditions):
        return db.scalar(select(func.count()).select_from(base).where(*conditions))

    return DeviceSummaryCounts(
        total=count(), operativos=count(base.c.estado == OPERATIVO), enMantenimiento=count(base.c.estado == EN_MANTENIMIENTO),
        fueraDeServicio=count(base.c.estado == FUERA_DE_SERVICIO), descomisionados=count(base.c.estado == BAJA),
        asignados=count(base.c.idInstitucionAsignada.is_not(None)), sinAsignar=count(base.c.idInstitucionAsignada.is_(None)),
    )


def _members(db: Session, idInstitucion: uuid.UUID) -> list[DeviceResponsible]:
    rows = db.execute(
        select(InstitutionUser, User).join(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
        .where(InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.estadoRelacion == institutions.RELACION_ACTIVO)
        .order_by(User.apellido, User.nombre)
    ).all()
    return [DeviceResponsible(idInstitucionUsuario=r.idInstitucionUsuario, nombre=u.nombre, apellido=u.apellido, activo=True)
            for r, u in rows]


def listResponsibles(db: Session, scope: Scope) -> list[DeviceResponsible]:
    """Integrantes ACTIVOS de la institución que pueden ser responsables de un dispositivo (solo para quien administra)."""
    _require(db, scope, "responsable", "CONSULTAR_RESPONSABLES_DISPOSITIVO")
    return _members(db, scope.idInstitucion)


def institutionOptions(db: Session, scope: Scope, busqueda: str | None = None) -> list[DeviceInstitutionOption]:
    """Instituciones activas donde se puede asignar un dispositivo (solo quien tiene la capacidad de asignar)."""
    _require(db, scope, "asignar", "CONSULTAR_INSTITUCIONES_ASIGNABLES")
    query = select(Institution).where(Institution.estado == institutions.INSTITUCION_ACTIVA)
    if busqueda and busqueda.strip():
        query = query.where(Institution.nombre.ilike(_like(busqueda.strip()), escape="\\"))
    rows = db.scalars(query.order_by(Institution.nombre).limit(50)).all()
    return [DeviceInstitutionOption(idInstitucion=i.idInstitucion, nombre=i.nombre) for i in rows]


def responsiblesOf(db: Session, scope: Scope, idInstitucion: uuid.UUID) -> list[DeviceResponsible]:
    """Integrantes activos de una institución elegible para asignarle un dispositivo (solo administrador del sistema)."""
    _require(db, scope, "asignar", "CONSULTAR_RESPONSABLES_DISPOSITIVO")
    _activeInstitution(db, idInstitucion)
    return _members(db, idInstitucion)


def listMeasurements(db: Session, scope: Scope, idDispositivo: uuid.UUID, pagina: int = 1, tamanioPagina: int = 20) -> DeviceMeasurementPage:
    """Mediciones hechas con el dispositivo SIN datos del paciente. En el inventario institucional solo se ven las de
    pacientes de esa institución: si el dispositivo se reasigna, la nueva institución no accede a lo medido antes."""
    _require(db, scope, "mediciones", "CONSULTAR_MEDICIONES_DISPOSITIVO")
    device = _load(db, scope, idDispositivo)
    tamanioPagina = max(1, min(tamanioPagina, MAX_PAGE_SIZE))
    pagina = max(1, pagina)
    query = (
        select(Measurement, Institution.nombre)
        .join(MeasurementProfile, MeasurementProfile.idPerfilMedicion == Measurement.idPerfilMedicion)
        .outerjoin(InstitutionUser, InstitutionUser.idInstitucionUsuario == MeasurementProfile.idInstitucionUsuarioResponsable)
        .outerjoin(Institution, Institution.idInstitucion == InstitutionUser.idInstitucion)
        .where(Measurement.idDispositivo == device.idDispositivo)
    )
    if scope.idInstitucion is not None:
        query = query.where(InstitutionUser.idInstitucion == scope.idInstitucion)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(Measurement.fechaHoraInicio.desc(), Measurement.idMedicion)
                      .offset((pagina - 1) * tamanioPagina).limit(tamanioPagina)).all()
    return DeviceMeasurementPage(
        items=[DeviceMeasurementItem(
            idMedicion=m.idMedicion, fechaHoraInicio=m.fechaHoraInicio, modoMedicion=m.modoMedicion, estadoMedicion=m.estadoMedicion,
            versionFirmwareAlMomento=m.versionFirmwareAlMomento, modeloSensorAlMomento=m.modeloSensorAlMomento,
            nombreInstitucion=name if scope.idInstitucion is None else None) for m, name in rows],
        total=total, pagina=pagina, tamanioPagina=tamanioPagina)


# --- Validaciones comunes ----------------------------------------------------------------------------------------


def _activeInstitution(db: Session, idInstitucion: uuid.UUID) -> Institution:
    institution = db.get(Institution, idInstitucion)
    if institution is None or institution.estado != institutions.INSTITUCION_ACTIVA:
        raise _error("INSTITUCION_NO_ENCONTRADA", "La institución no existe o no está activa.")
    return institution


def _activeMember(db: Session, idInstitucion: uuid.UUID, idRelacion: uuid.UUID) -> InstitutionUser:
    """El responsable debe ser integrante ACTIVO de LA MISMA institución del dispositivo (nunca de otra)."""
    relation = db.get(InstitutionUser, idRelacion)
    if relation is None or relation.idInstitucion != idInstitucion or relation.estadoRelacion != institutions.RELACION_ACTIVO:
        raise _error("RESPONSABLE_DISPOSITIVO_INVALIDO", "El responsable debe ser un integrante activo de la institución del dispositivo.")
    return relation


def _codeTaken(db: Session, code: str) -> bool:
    return db.scalar(select(Device.idDispositivo).where(func.lower(Device.codigoDispositivo) == code.lower())) is not None


def _requireIdle(db: Session, device: Device) -> None:
    busy = db.scalar(select(func.count()).select_from(Measurement).where(
        Measurement.idDispositivo == device.idDispositivo, Measurement.estadoMedicion.in_(ACTIVE_MEASUREMENTS)))
    if busy:
        raise _error("DISPOSITIVO_EN_USO", IN_USE)


def _requireActive(device: Device) -> None:
    if device.estado == BAJA:
        raise _error("DISPOSITIVO_DESCOMISIONADO", RETIRED)


def _audit(db: Session, actor: User, action: str, device: Device, *, previous=None, new=None, idInstitucion=None,
           observacion=None, success=True) -> None:
    registerEvent(db, "CRUD", action, success, actor.idUsuario, "Dispositivo", device.idDispositivo,
                  observacion=observacion, datosPrevios=previous, datosNuevos=new, idInstitucion=idInstitucion, modulo="DISPOSITIVOS")


# --- Alta ---------------------------------------------------------------------------------------------------------


def _create(db: Session, actor: User, data: DeviceRegisterRequest, idInstitucion: uuid.UUID | None, *, auto: bool = False,
            origin: dict | None = None) -> Device:
    if _codeTaken(db, data.codigoDispositivo):
        raise _error("DISPOSITIVO_DUPLICADO", DUPLICATE)
    if idInstitucion is not None:
        _activeInstitution(db, idInstitucion)
    if data.idInstitucionUsuarioResponsable is not None:
        _activeMember(db, idInstitucion, data.idInstitucionUsuarioResponsable)
    device = Device(
        codigoDispositivo=data.codigoDispositivo, nombre=data.nombre, modelo=data.modelo, modeloSensor=data.modeloSensor,
        versionFirmware=data.versionFirmware, estado=data.estado, idInstitucionAsignada=idInstitucion,
        idInstitucionUsuarioResponsable=data.idInstitucionUsuarioResponsable,
        fechaAsignacionInstitucional=_utcNow() if idInstitucion else None,
    )
    try:
        db.add(device)
        db.flush()
        _audit(db, actor, "REGISTRAR_DISPOSITIVO", device,
               new={"modeloSensor": data.modeloSensor, "estado": data.estado, "registroAutomatico": auto,
                    "idInstitucion": str(idInstitucion) if idInstitucion else None,
                    "idResponsable": str(data.idInstitucionUsuarioResponsable) if data.idInstitucionUsuarioResponsable else None,
                    **(origin or {})},
               idInstitucion=idInstitucion)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _error("DISPOSITIVO_DUPLICADO", DUPLICATE) from error
    return device


# Sensor del firmware que habla con el puente serie (GlucoLume_MAX30100.ino).
BRIDGE_DEVICE_SENSOR = "MAX30100"


def registerFromBridge(db: Session, code: str) -> Device | None:
    """Alta AUTOMÁTICA de un dispositivo que el puente serie informa y que todavía no está en el inventario.

    Lo dispara la recepción del puente, que ya se autenticó con BRIDGE_TOKEN (nadie sin ese token puede crear
    dispositivos). Queda OPERATIVO y sin asignar a ninguna institución (lo pueden usar las cuentas individuales) y la
    auditoría lo identifica como registro automático (no hay una persona que lo haya dado de alta). Idempotente: si el
    código ya existe —también retirado o en mantenimiento— se devuelve ese y no se modifica. Un código inválido no se
    registra (devuelve None). Nunca cambia el estado ni la institución de un dispositivo existente.
    """
    try:
        data = DeviceRegisterRequest(
            codigoDispositivo=code, nombre="Arduino GlucoLume (registro automático)", modelo="Arduino UNO + MAX30100",
            modeloSensor=BRIDGE_DEVICE_SENSOR)
    except ValueError:
        return None
    existing = db.scalar(select(Device).where(func.lower(Device.codigoDispositivo) == data.codigoDispositivo.lower()))
    if existing is not None:
        return existing
    device = Device(codigoDispositivo=data.codigoDispositivo, nombre=data.nombre, modelo=data.modelo,
                    modeloSensor=data.modeloSensor, estado=OPERATIVO)
    try:
        db.add(device)
        db.flush()
        registerEvent(db, "CRUD", "REGISTRAR_DISPOSITIVO", True, None, "Dispositivo", device.idDispositivo, modulo="DISPOSITIVOS",
                      datosNuevos={"modeloSensor": data.modeloSensor, "estado": OPERATIVO, "registroAutomatico": True,
                                   "origen": "PUENTE_SERIE", "idInstitucion": None})
        db.commit()
    except IntegrityError:  # carrera: otro latido lo creó primero
        db.rollback()
        return db.scalar(select(Device).where(func.lower(Device.codigoDispositivo) == data.codigoDispositivo.lower()))
    return device


def registerDevice(db: Session, scope: Scope, data: DeviceRegisterRequest) -> DeviceDetail:
    """Alta manual. Global: plataforma (la asignación a una institución es solo del administrador). Institucional:
    siempre queda asignado a la institución de la ruta."""
    _require(db, scope, "registrar", "REGISTRAR_DISPOSITIVO")
    if scope.idInstitucion is not None:
        if data.idInstitucionAsignada not in (None, scope.idInstitucion):
            raise _denied(db, scope, "REGISTRAR_DISPOSITIVO", idInstitucion=scope.idInstitucion)
        idInstitucion = scope.idInstitucion
        # La asignación la decide el backend: siempre el propietario vigente. El cuerpo no puede elegir a otra persona.
        owner = currentOwner(db, idInstitucion)
        if data.idInstitucionUsuarioResponsable not in (None, owner.idInstitucionUsuario):
            raise _denied(db, scope, "REGISTRAR_DISPOSITIVO", idInstitucion=idInstitucion)
        data = data.model_copy(update={"idInstitucionUsuarioResponsable": owner.idInstitucionUsuario})
    else:
        if data.idInstitucionAsignada is not None and not scope.can("asignar"):
            raise _denied(db, scope, "REGISTRAR_DISPOSITIVO")
        idInstitucion = data.idInstitucionAsignada
    if data.idInstitucionUsuarioResponsable is not None and idInstitucion is None:
        raise _error("RESPONSABLE_DISPOSITIVO_INVALIDO", "Un responsable requiere una institución asignada.")
    device = _create(db, scope.actor, data, idInstitucion)
    return getDevice(db, scope, device.idDispositivo)


# --- Alta y reconocimiento desde la conexión de un operador -----------------------------------------------------


def findByCode(db: Session, code: str) -> Device | None:
    return db.scalar(select(Device).where(func.lower(Device.codigoDispositivo) == code.strip().lower()))


def operatorMembership(db: Session, actor: User, idInstitucion: uuid.UUID) -> institutions.Membership:
    """El actor es OPERADOR activo de la institución activa (404 si no pertenece, 403 si pertenece con otro rol).
    Solo el operador conecta y mide: propietario y moderador administran el inventario por su pantalla."""
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_DISPOSITIVOS)
    if membership.role != institutions.ROL_OPERADOR:
        raise _denied(db, actor, "REGISTRAR_DISPOSITIVO", None, idInstitucion)
    return membership


def standing(device: Device | None, idInstitucion: uuid.UUID, relationId: uuid.UUID | None) -> dict:
    """Cómo está un código conocido respecto de ESTA institución. No revela datos de otra institución."""
    if device is None:
        return {"situacion": "NO_REGISTRADO", "usable": False, "motivo": None}
    if device.idInstitucionAsignada == idInstitucion:
        situation = "DE_LA_INSTITUCION"
    elif device.idInstitucionAsignada is None:
        situation = "SIN_INSTITUCION"
    else:
        situation = "DE_OTRA_INSTITUCION"
    usable, reason = usableBy(device, idInstitucion, relationId)
    return {"situacion": situation, "usable": usable, "motivo": reason}


def registerFromConnection(db: Session, actor: User, idInstitucion: uuid.UUID, code: str, *, nombre: str | None, sensor: str,
                           firmware: str | None, medio: str | None, identidad: str) -> tuple[Device, bool]:
    """Alta del dispositivo en la PRIMERA conexión efectiva de un operador de la institución (la comunicación con el Arduino ya la
    comprobó el servicio de adquisición). Devuelve (dispositivo, creado).

    - Queda asignado a la institución activa y a cargo de su propietario vigente; el operador no adquiere la titularidad.
    - Idempotente y sin duplicados: el código es único; si otro operador lo registró un instante antes, se devuelve ese mismo registro.
    - Nunca se apropia de un dispositivo ya registrado en otra institución ni de uno sin institución (lo pueden estar usando cuentas
      individuales): eso requiere el procedimiento administrativo (asignación por el administrador del sistema).
    - La auditoría deja quién lo registró (el operador), cuándo, por qué medio y con qué nivel de identificación."""
    membership = operatorMembership(db, actor, idInstitucion)
    relationId = membership.relation.idInstitucionUsuario
    owner = currentOwner(db, idInstitucion)
    existing = findByCode(db, code)
    if existing is None:
        try:
            data = DeviceRegisterRequest(codigoDispositivo=code, nombre=(nombre or "").strip() or None, modelo=BRIDGE_MODEL,
                                         modeloSensor=sensor, versionFirmware=firmware,
                                         idInstitucionUsuarioResponsable=owner.idInstitucionUsuario)
            origin = {"origen": "CONEXION_OPERADOR", "idOperador": str(relationId), "medio": medio, "identificacion": identidad}
            return _create(db, actor, data, idInstitucion, auto=False, origin=origin), True
        except AuthError as error:
            if error.code != "DISPOSITIVO_DUPLICADO":
                raise
            db.rollback()
            existing = findByCode(db, code)  # carrera: otro operador lo registró primero
    if existing is not None and existing.idInstitucionAsignada == idInstitucion:
        return existing, False
    if existing is not None and existing.idInstitucionAsignada is None:
        raise _error("DISPOSITIVO_NO_DISPONIBLE",
                     "El dispositivo ya está registrado, sin institución: no se duplica. Vinculalo a tu institución con la confirmación explícita.")
    raise _error("DISPOSITIVO_NO_DISPONIBLE",
                 "El dispositivo ya está registrado y no pertenece al inventario de esta institución. No se transfiere automáticamente: "
                 "pedí a la administración de GlucoLume el procedimiento de reasignación.")


def linkToInstitution(db: Session, actor: User, idInstitucion: uuid.UUID, device: Device, *, nombre: str | None, medio: str | None,
                      identidad: str) -> tuple[Device, bool]:
    """Vincula al inventario de la institución un dispositivo que NO pertenece a ninguna (p. ej. el que dio de alta el puente o usó una cuenta
    individual). Devuelve (dispositivo, vinculado_ahora). Lo llama un OPERADOR activo con la comunicación ya verificada y la confirmación explícita
    (ver deviceConnection.link: acá se aplican las reglas de datos).

    - Nunca toca uno de OTRA institución ni uno descomisionado; uno que ya es de esta institución se devuelve tal cual (idempotente).
    - La asignación es atómica (`UPDATE … WHERE idInstitucionAsignada IS NULL`): si dos instituciones lo intentan a la vez, solo una lo obtiene.
    - Queda a cargo del propietario vigente; el operador no adquiere la titularidad. Las mediciones anteriores se conservan intactas.
    - La auditoría deja el estado previo, quién lo vinculó, cuándo y cuántas mediciones previas tenía el dispositivo."""
    membership = operatorMembership(db, actor, idInstitucion)
    owner = currentOwner(db, idInstitucion)
    _activeInstitution(db, idInstitucion)
    _requireActive(device)
    if device.idInstitucionAsignada == idInstitucion:
        return device, False
    if device.idInstitucionAsignada is not None:
        raise _error("DISPOSITIVO_NO_DISPONIBLE",
                     "El dispositivo pertenece a otra institución. No se transfiere automáticamente: requiere el procedimiento administrativo.")
    _requireIdle(db, device)
    previousUses = _usage(db, device)
    changes = {"idInstitucionAsignada": idInstitucion, "idInstitucionUsuarioResponsable": owner.idInstitucionUsuario,
               "fechaAsignacionInstitucional": _utcNow()}
    if nombre:
        changes["nombre"] = nombre
    claimed = db.execute(update(Device).where(Device.idDispositivo == device.idDispositivo, Device.idInstitucionAsignada.is_(None),
                                              Device.estado != BAJA).values(**changes).execution_options(synchronize_session=False))
    if claimed.rowcount != 1:  # otra institución (u otro operador) se adelantó
        db.rollback()
        db.expire_all()
        current = db.get(Device, device.idDispositivo)
        if current is not None and current.idInstitucionAsignada == idInstitucion:
            return current, False
        raise _error("DISPOSITIVO_NO_DISPONIBLE", "El dispositivo ya no está disponible para vincularlo a esta institución.")
    db.expire(device)
    _audit(db, actor, "VINCULAR_DISPOSITIVO_INSTITUCION", device, previous={"idInstitucion": None},
           new={"idInstitucion": str(idInstitucion), "idResponsable": str(owner.idInstitucionUsuario), "origen": "CONEXION_OPERADOR",
                "idOperador": str(membership.relation.idInstitucionUsuario), "medio": medio, "identificacion": identidad,
                "confirmacionExplicita": True, "medicionesPrevias": previousUses},
           idInstitucion=idInstitucion)
    db.commit()
    return db.get(Device, device.idDispositivo), True


def syncConnection(db: Session, actor: User, device: Device, *, firmware: str | None, medio: str | None, identidad: str) -> None:
    """Información de la conexión actual de un dispositivo existente: el firmware que informa se actualiza hacia adelante (las mediciones
    anteriores conservan el suyo). No cambia ni el estado ni la institución ni la titularidad. Auditoría solo si algo cambió."""
    if device.estado == BAJA or not firmware or device.versionFirmware == firmware:
        return
    previous = device.versionFirmware
    device.versionFirmware = firmware
    _audit(db, actor, "MODIFICAR_DISPOSITIVO", device, previous={"versionFirmware": previous},
           new={"campos": ["versionFirmware"], "versionFirmware": firmware, "origen": "Conexión del dispositivo", "medio": medio,
                "identificacion": identidad}, idInstitucion=device.idInstitucionAsignada)
    db.commit()


def registration(db: Session, device: Device, idInstitucion: uuid.UUID | None = None) -> DeviceRegistration | None:
    """Quién y cuándo dio de alta el dispositivo (de la auditoría; no hay una columna aparte). Una institución solo ve el alta o la vinculación
    hecha EN ELLA: si el dispositivo se reasignó desde otra, quién lo registró allá es dato de la anterior y no se informa (queda sin origen)."""
    # El evento que lo dejó en su institución actual: el alta, o la vinculación posterior de un dispositivo que no tenía institución.
    query = select(Audit).where(
        Audit.tablaAfectada == "Dispositivo", Audit.idRegistro == device.idDispositivo,
        Audit.accion.in_(("REGISTRAR_DISPOSITIVO", "VINCULAR_DISPOSITIVO_INSTITUCION")), Audit.resultado == "EXITO")
    if idInstitucion is not None:
        query = query.where(Audit.idInstitucion == idInstitucion)
    event = db.scalar(query.order_by(Audit.fechaHora.desc()).limit(1))
    if event is None:
        return None
    try:
        data = json.loads(event.datosNuevos) if event.datosNuevos else {}
    except ValueError:
        data = {}
    origin = data.get("origen") or ("AUTOMATICO_PUENTE" if data.get("registroAutomatico") else "MANUAL")
    if event.accion == "VINCULAR_DISPOSITIVO_INSTITUCION":
        origin = "VINCULACION_OPERADOR"
    user = db.get(User, event.idUsuario) if event.idUsuario else None
    return DeviceRegistration(origen=origin, nombre=user.nombre if user else None, apellido=user.apellido if user else None,
                              fecha=event.fechaHora, medio=data.get("medio"))


# --- Modificación -----------------------------------------------------------------------------------------------


def editDevice(db: Session, scope: Scope, idDispositivo: uuid.UUID, data: DeviceEditRequest) -> DeviceDetail:
    _require(db, scope, "editar", "MODIFICAR_DISPOSITIVO", db.get(Device, idDispositivo))
    device = _load(db, scope, idDispositivo)
    _requireActive(device)
    changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if k != "modeloSensor" or v is not None}
    changed = {k: v for k, v in changes.items() if getattr(device, k) != v}
    if scope.idInstitucion is not None and set(changed) - INSTITUTION_EDITABLE:
        # El sensor y el firmware los informa la conexión del Arduino: una institución no los reescribe.
        raise _denied(db, scope, "MODIFICAR_DISPOSITIVO", device, scope.idInstitucion)
    if changed:
        previous = {k: getattr(device, k) for k in changed if k in ("versionFirmware", "modeloSensor")}
        for key, value in changed.items():
            setattr(device, key, value)
        _audit(db, scope.actor, "MODIFICAR_DISPOSITIVO", device, previous=previous or None,
               new={"campos": sorted(changed), **{k: changed[k] for k in changed if k in ("versionFirmware", "modeloSensor")}},
               idInstitucion=device.idInstitucionAsignada)
        db.commit()
    return getDevice(db, scope, idDispositivo)


def changeState(db: Session, scope: Scope, idDispositivo: uuid.UUID, estado: str, motivo: str | None) -> DeviceDetail:
    _require(db, scope, "estado", "CAMBIAR_ESTADO_DISPOSITIVO", db.get(Device, idDispositivo))
    device = _load(db, scope, idDispositivo)
    _requireActive(device)
    if device.estado != estado:
        previous = device.estado
        device.estado = estado
        _audit(db, scope.actor, "CAMBIAR_ESTADO_DISPOSITIVO", device, previous={"estado": previous}, new={"estado": estado},
               idInstitucion=device.idInstitucionAsignada, observacion=motivo)
        db.commit()
    return getDevice(db, scope, idDispositivo)


# --- Asignación ---------------------------------------------------------------------------------------------------


def assignInstitution(db: Session, scope: Scope, idDispositivo: uuid.UUID, data: DeviceAssignRequest) -> DeviceDetail:
    """Asigna (o mueve) el dispositivo a una institución, con responsable opcional. Solo el administrador de plataforma."""
    _require(db, scope, "asignar", "ASIGNAR_DISPOSITIVO", db.get(Device, idDispositivo))
    device = _load(db, scope, idDispositivo)
    _requireActive(device)
    _activeInstitution(db, data.idInstitucion)
    if data.idInstitucionUsuarioResponsable is not None:
        _activeMember(db, data.idInstitucion, data.idInstitucionUsuarioResponsable)
    previousInstitution = device.idInstitucionAsignada
    if previousInstitution == data.idInstitucion and device.idInstitucionUsuarioResponsable == data.idInstitucionUsuarioResponsable:
        return getDevice(db, scope, idDispositivo)
    if previousInstitution not in (None, data.idInstitucion):
        _requireIdle(db, device)
        # La institución anterior pierde el dispositivo: queda constancia en SU auditoría.
        _audit(db, scope.actor, "DESVINCULAR_DISPOSITIVO", device, previous={"idInstitucion": str(previousInstitution)},
               new={"motivo": "Reasignado a otra institución"}, idInstitucion=previousInstitution)
    previousResponsible = device.idInstitucionUsuarioResponsable
    device.idInstitucionAsignada = data.idInstitucion
    device.idInstitucionUsuarioResponsable = data.idInstitucionUsuarioResponsable
    if previousInstitution != data.idInstitucion:
        device.fechaAsignacionInstitucional = _utcNow()
    _audit(db, scope.actor, "ASIGNAR_DISPOSITIVO", device,
           previous={"idInstitucion": str(previousInstitution) if previousInstitution else None,
                     "idResponsable": str(previousResponsible) if previousResponsible else None},
           new={"idInstitucion": str(data.idInstitucion),
                "idResponsable": str(data.idInstitucionUsuarioResponsable) if data.idInstitucionUsuarioResponsable else None},
           idInstitucion=data.idInstitucion)
    db.commit()
    return getDevice(db, scope, idDispositivo)


def changeResponsible(db: Session, scope: Scope, idDispositivo: uuid.UUID, idRelacion: uuid.UUID | None) -> DeviceDetail:
    _require(db, scope, "responsable", "CAMBIAR_RESPONSABLE_DISPOSITIVO", db.get(Device, idDispositivo))
    device = _load(db, scope, idDispositivo)
    _requireActive(device)
    if device.idInstitucionAsignada is None:
        raise _error("DISPOSITIVO_SIN_INSTITUCION", "El dispositivo no está asignado a una institución.")
    if idRelacion is not None:
        _activeMember(db, device.idInstitucionAsignada, idRelacion)
    if device.idInstitucionUsuarioResponsable != idRelacion:
        previous = device.idInstitucionUsuarioResponsable
        device.idInstitucionUsuarioResponsable = idRelacion
        _audit(db, scope.actor, "CAMBIAR_RESPONSABLE_DISPOSITIVO", device,
               previous={"idResponsable": str(previous) if previous else None},
               new={"idResponsable": str(idRelacion) if idRelacion else None}, idInstitucion=device.idInstitucionAsignada)
        db.commit()
    return getDevice(db, scope, idDispositivo)


def _unlink(db: Session, actor: User, device: Device, motivo: str) -> uuid.UUID | None:
    previous = device.idInstitucionAsignada
    responsible = device.idInstitucionUsuarioResponsable
    device.idInstitucionAsignada = None
    device.idInstitucionUsuarioResponsable = None
    device.fechaAsignacionInstitucional = None
    _audit(db, actor, "DESVINCULAR_DISPOSITIVO", device,
           previous={"idInstitucion": str(previous) if previous else None, "idResponsable": str(responsible) if responsible else None},
           new={"motivo": motivo}, idInstitucion=previous)
    return previous


def unassign(db: Session, scope: Scope, idDispositivo: uuid.UUID) -> DeviceDetail:
    """Quita la asignación y el responsable. El dispositivo y las mediciones anteriores se conservan."""
    _require(db, scope, "desvincular", "DESVINCULAR_DISPOSITIVO", db.get(Device, idDispositivo))
    device = db.get(Device, idDispositivo)
    if device is None or (scope.idInstitucion is not None and device.idInstitucionAsignada != scope.idInstitucion):
        raise _error("DISPOSITIVO_NO_ENCONTRADO", NOT_FOUND)
    _requireActive(device)
    if device.idInstitucionAsignada is None:
        raise _error("DISPOSITIVO_SIN_INSTITUCION", "El dispositivo no está asignado a una institución.")
    _requireIdle(db, device)
    _unlink(db, scope.actor, device, "Desvinculado del inventario institucional")
    db.commit()
    if scope.idInstitucion is not None:  # la institución ya no lo ve: se informa el resultado sin leer el detalle
        db.refresh(device)
        return DeviceDetail(**_item(db, device, Scope(scope.actor, scope.capabilities)).model_dump(),
                            permisos=DevicePermissions(**dict.fromkeys(DevicePermissions.model_fields, False)))
    return getDevice(db, scope, idDispositivo)


def decommission(db: Session, scope: Scope, idDispositivo: uuid.UUID) -> DeviceDetail:
    """Retiro definitivo (estado BAJA), en una sola operación transaccional y sin desvinculaciones intermedias: el
    dispositivo conserva su institución de origen y su responsable (referencia histórica) y queda terminal. El
    registro y las mediciones se conservan; nunca se elimina físicamente."""
    _require(db, scope, "descomisionar", "DESCOMISIONAR_DISPOSITIVO", db.get(Device, idDispositivo))
    device = db.get(Device, idDispositivo)
    if device is None or (scope.idInstitucion is not None and device.idInstitucionAsignada != scope.idInstitucion):
        raise _error("DISPOSITIVO_NO_ENCONTRADO", NOT_FOUND)
    _requireActive(device)
    _requireIdle(db, device)
    previousState = device.estado
    institution = device.idInstitucionAsignada
    device.estado = BAJA
    _audit(db, scope.actor, "DESCOMISIONAR_DISPOSITIVO", device, previous={"estado": previousState},
           new={"estado": BAJA, "mediciones": "CONSERVADAS", "idInstitucion": str(institution) if institution else None,
                "idResponsable": str(device.idInstitucionUsuarioResponsable) if device.idInstitucionUsuarioResponsable else None},
           idInstitucion=institution)
    db.commit()
    return getDevice(db, scope, idDispositivo)


# --- Identificación durante la adquisición -----------------------------------------------------------------------


def sharedDeviceMode() -> bool:
    """DEC-01: con ALLOW_INDIVIDUAL_ON_INSTITUTIONAL_DEVICE=true el único equipo experimental lo usan todas las cuentas habilitadas
    (individuales, de grupos familiares y operadores de cualquier institución), sin importar su asignación administrativa, que no cambia.
    Con false rige la asignación. Compartir el hardware no comparte mediciones, datos ni el control de una sesión ajena."""
    return getSettings().ALLOW_INDIVIDUAL_ON_INSTITUTIONAL_DEVICE


def usableBy(device: Device, idInstitucion: uuid.UUID | None, relationId: uuid.UUID | None = None) -> tuple[bool, str | None]:
    """¿Se puede iniciar una adquisición con este dispositivo en este contexto? (estado, institución y responsable)."""
    if device.estado == BAJA:
        return False, "El dispositivo está descomisionado."
    if device.estado != OPERATIVO:
        return False, "El dispositivo no está operativo (mantenimiento o fuera de servicio)."
    if sharedDeviceMode():  # uso compartido: la institución asignada y el responsable no restringen el uso del hardware
        return True, None
    if device.idInstitucionAsignada not in (None, idInstitucion):
        return False, "El dispositivo pertenece a otra institución."
    if (device.idInstitucionUsuarioResponsable is not None and relationId is not None
            and device.idInstitucionUsuarioResponsable != relationId and not _heldByOwner(device)):
        return False, "El dispositivo está a cargo de otro responsable."
    return True, None


def resolveDevice(db: Session, actor: User, data: DeviceResolveRequest) -> DeviceResolveResult:
    """Traduce el identificador que informa el firmware en un dispositivo del inventario.

    - Existente: se reutiliza (jamás se duplica por reconectar); si informa otro firmware se actualiza hacia adelante,
      y si informa otro sensor se rechaza (no se reescribe en silencio).
    - Inexistente: se registra solo si el contexto autoriza (propietario/moderador en su institución, o la plataforma);
      un operador o una cuenta individual debe pedir el alta desde el inventario.
    No consulta ni afirma la conexión: eso lo determina la adquisición con la comunicación efectiva.
    """
    scope = None
    relationId = None
    if data.idInstitucion is not None:
        scope = institutionScope(db, actor, data.idInstitucion)
        relationId = scope.membership.relation.idInstitucionUsuario
    elif actor.tipoCuenta in CAPABILITIES:
        scope = platformScope(db, actor)
    device = db.scalar(select(Device).where(func.lower(Device.codigoDispositivo) == data.codigoDispositivo.lower()))
    created = False
    if device is None:
        if scope is None or not scope.can("registrar"):
            registerEvent(db, "PERMISO", "REGISTRAR_DISPOSITIVO", False, actor.idUsuario, modulo="DISPOSITIVOS",
                          idInstitucion=data.idInstitucion,
                          observacion="Motivo: dispositivo no registrado y sin permiso de alta (identificación automática)")
            db.commit()
            raise _error("DISPOSITIVO_NO_REGISTRADO",
                         "El dispositivo no está registrado. Pedí que lo registre quien administra el inventario.")
        try:
            owner = currentOwner(db, data.idInstitucion) if data.idInstitucion is not None else None
            device = _create(db, actor, DeviceRegisterRequest(
                codigoDispositivo=data.codigoDispositivo, modeloSensor=data.modeloSensor, versionFirmware=data.versionFirmware,
                idInstitucionUsuarioResponsable=owner.idInstitucionUsuario if owner else None),
                data.idInstitucion, auto=True)
            created = True
        except AuthError as error:
            if error.code != "DISPOSITIVO_DUPLICADO":
                raise
            device = db.scalar(select(Device).where(func.lower(Device.codigoDispositivo) == data.codigoDispositivo.lower()))
    if not created:
        if device.idInstitucionAsignada not in (None, data.idInstitucion):
            # No se revela a qué institución pertenece.
            raise _error("DISPOSITIVO_NO_DISPONIBLE", "El dispositivo no está disponible en este contexto.")
        if device.modeloSensor != data.modeloSensor:
            raise _error("DISPOSITIVO_INCONSISTENTE",
                         "El modelo de sensor informado no coincide con el registrado para este dispositivo.")
    firmwareUpdated = False
    # El firmware identificado solo lo registra quien administra el inventario (capacidad «registrar»: plataforma o propietario/moderador) y solo
    # sobre dispositivos de su ámbito: una cuenta individual, un operador o una institución sobre un dispositivo del pool compartido o de otra
    # institución identifican el dispositivo pero NO reescriben su firmware (el valor se copia a las mediciones posteriores de otras cuentas).
    canRecordFirmware = scope is not None and scope.can("registrar") and (
        scope.idInstitucion is None or device.idInstitucionAsignada == scope.idInstitucion)
    if (not created and canRecordFirmware and device.estado != BAJA and data.versionFirmware
            and device.versionFirmware != data.versionFirmware):
        previous = device.versionFirmware
        device.versionFirmware = data.versionFirmware
        _audit(db, actor, "MODIFICAR_DISPOSITIVO", device, previous={"versionFirmware": previous},
               new={"campos": ["versionFirmware"], "versionFirmware": data.versionFirmware,
                    "origen": "Identificación automática"}, idInstitucion=device.idInstitucionAsignada)
        db.commit()
        firmwareUpdated = True
    usable, reason = usableBy(device, data.idInstitucion, relationId)
    view = scope or Scope(actor, frozenset({"ver"}))
    return DeviceResolveResult(dispositivo=_item(db, device, view), creado=created, firmwareActualizado=firmwareUpdated,
                               disponibleParaMedir=usable, motivoNoDisponible=reason)
