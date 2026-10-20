# RealData - Datos reales de un usuario para los envíos de prueba
#
# Solo lectura: no crea tokens ni modifica la base. Para cada evento se parte de los datos de muestra
# (sampleData.py) y se reemplazan los campos para los que existe un dato real del usuario. Lo que no
# existe en la base (o una tabla que todavía no se creó) queda con el dato genérico de muestra.
#
# Uso exclusivo de pruebas: los flujos reales nunca completan correos con datos de muestra.

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.emails.eventTypes import (
    CATEGORIA_GRUPO,
    CATEGORIA_INSTITUCION,
    CATEGORIA_MEDICIONES,
    EMAIL_EVENTS,
)
from app.emails.eventTypes import EmailEventType as E
from app.emails.formatting import maskEmail
from app.models.device import Device
from app.models.externalIdentity import ExternalIdentity
from app.models.group import Group
from app.models.groupUser import GroupUser
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.localCredential import LocalCredential
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.mfaFactor import MfaFactor
from app.models.user import User
from app.models.userSession import UserSession

logger = logging.getLogger(__name__)

ESTADOS_MEDICION = {
    "PENDIENTE": "Pendiente", "ADQUIRIENDO": "En adquisición", "PROCESANDO": "En procesamiento",
    "COMPLETADA": "Completada", "INVALIDA": "Inválida", "CANCELADA": "Cancelada",
}
CONDICIONES_COMIDA = {"AYUNO": "Ayuno", "POSTPRANDIAL": "Después de comer", "NO_INFORMADA": "No informada"}


@dataclass
class RealData:
    user: User
    credential: LocalCredential | None = None
    google: ExternalIdentity | None = None
    mfaFactor: MfaFactor | None = None
    lastSession: UserSession | None = None
    group: Group | None = None
    groupMembership: GroupUser | None = None
    groupOtherMember: str | None = None
    groupOwner: str | None = None
    institution: Institution | None = None
    institutionMembership: InstitutionUser | None = None
    institutionInviter: str | None = None
    institutionOtherOperator: str | None = None
    lastMeasurement: Measurement | None = None
    device: Device | None = None
    unavailable: list[str] = field(default_factory=list)


def fullName(user: User | None) -> str | None:
    if user is None:
        return None
    return " ".join(part for part in (user.nombre, user.apellido) if part) or user.usuario


def findUser(db: Session, identificador: str) -> User | None:
    identificador = identificador.strip()
    column = User.correoElectronico if "@" in identificador else User.usuario
    return db.scalar(select(User).where(column == identificador))


def _section(db: Session, data: RealData, name: str, loader) -> None:
    """Carga una sección; si falla (p. ej. tabla inexistente) se usa la muestra para esos datos."""
    try:
        loader()
    except SQLAlchemyError as error:
        db.rollback()
        data.unavailable.append(name)
        logger.warning("Datos reales de %s no disponibles (%s); se usan datos de muestra.", name, type(error).__name__)


def loadRealData(db: Session, user: User) -> RealData:
    data = RealData(user=user)
    uid = user.idUsuario

    def account():
        data.credential = db.scalar(select(LocalCredential).where(LocalCredential.idUsuario == uid))
        data.google = db.scalar(select(ExternalIdentity).where(ExternalIdentity.idUsuario == uid))
        data.lastSession = db.scalar(
            select(UserSession).where(UserSession.idUsuario == uid).order_by(UserSession.fechaCreacion.desc())
        )

    def mfa():
        data.mfaFactor = db.scalar(select(MfaFactor).where(MfaFactor.idUsuario == uid))

    def groups():
        data.groupMembership = db.scalar(
            select(GroupUser).where(GroupUser.idUsuario == uid).order_by(GroupUser.fechaInvitacion.desc())
        )
        if data.groupMembership is None:
            return
        data.group = db.get(Group, data.groupMembership.idGrupo)
        members = db.scalars(select(GroupUser).where(GroupUser.idGrupo == data.groupMembership.idGrupo)).all()
        other = next((m for m in members if m.idUsuario != uid), None)
        owner = next((m for m in members if m.rolGrupo == "PROPIETARIO"), None)
        data.groupOtherMember = fullName(db.get(User, other.idUsuario)) if other else None
        data.groupOwner = fullName(db.get(User, owner.idUsuario)) if owner else None

    def institutions():
        data.institutionMembership = db.scalar(
            select(InstitutionUser)
            .where(InstitutionUser.idUsuarioInvitado == uid)
            .order_by(InstitutionUser.fechaInvitacion.desc())
        )
        if data.institutionMembership is None:
            return
        membership = data.institutionMembership
        data.institution = db.get(Institution, membership.idInstitucion)
        if membership.idUsuarioInvitador:
            data.institutionInviter = fullName(db.get(User, membership.idUsuarioInvitador))
        other = db.scalar(
            select(InstitutionUser).where(
                InstitutionUser.idInstitucion == membership.idInstitucion,
                InstitutionUser.rolInstitucion == "OPERADOR",
                InstitutionUser.idUsuarioInvitado != uid,
            )
        )
        data.institutionOtherOperator = fullName(db.get(User, other.idUsuarioInvitado)) if other else None

    def measurements():
        data.lastMeasurement = db.scalar(
            select(Measurement)
            .join(MeasurementProfile, MeasurementProfile.idPerfilMedicion == Measurement.idPerfilMedicion)
            .where(MeasurementProfile.idUsuario == uid)
            .order_by(Measurement.fechaHoraInicio.desc())
        )
        if data.lastMeasurement is not None:
            data.device = db.get(Device, data.lastMeasurement.idDispositivo)

    for name, loader in (("cuenta", account), ("MFA", mfa), ("grupos", groups),
                         ("instituciones", institutions), ("mediciones", measurements)):
        _section(db, data, name, loader)
    return data


def _realValues(event: E, data: RealData) -> dict:
    """Valores reales disponibles para cada evento (None = no existe en la base)."""
    user, cred, google, factor = data.user, data.credential, data.google, data.mfaFactor
    values = {"nombre": user.nombre, "apellido": user.apellido}

    if event == E.CUENTA_CREADA:
        values["fechaCreacion"] = user.fechaCreacion
    elif event == E.EMAIL_CAMBIADO:
        values["correoNuevoEnmascarado"] = maskEmail(user.correoElectronico) or None
    elif event == E.PASSWORD_CAMBIADA:
        values["fechaEvento"] = cred.fechaUltimoCambioPassword if cred else None
    elif event == E.NUEVO_INICIO_SESION:
        values["fechaEvento"] = data.lastSession.fechaCreacion if data.lastSession else None
    elif event == E.INTENTO_ACCESO_INUSUAL and cred is not None:
        values["fechaEvento"] = cred.fechaUltimoIntentoFallido
        values["cantidadIntentos"] = cred.intentosFallidosConsecutivos or None
        values["bloqueadoHasta"] = cred.bloqueadoHasta
    elif event == E.MFA_ACTIVADO and factor is not None:
        values["metodo"] = factor.tipo
        values["fechaEvento"] = factor.fechaConfirmacion
    elif event == E.METODO_MFA_CAMBIADO and factor is not None:
        values["metodoNuevo"] = factor.tipo
    elif event == E.GOOGLE_VINCULADO and google is not None:
        values["correoGoogle"] = google.emailProveedor
        values["fechaEvento"] = google.fechaVinculacion
    elif event == E.GOOGLE_DESVINCULADO:
        values["tieneContrasenaLocal"] = cred is not None

    category = EMAIL_EVENTS[event].category
    membership = data.groupMembership
    if data.group is not None and category == CATEGORIA_GRUPO:
        values["nombreGrupo"] = data.group.nombre
        values["rol"] = membership.rolGrupo if event == E.AGREGADO_GRUPO else values.get("rol")
        values["fechaEvento"] = values.get("fechaEvento") or membership.fechaIncorporacion
        values["nombreIntegrante"] = data.groupOtherMember
        values["nombreInvitante"] = data.groupOwner
        values["nombreNuevoAdministrador"] = data.groupOwner

    inst = data.institutionMembership
    if data.institution is not None and category == CATEGORIA_INSTITUCION:
        values["nombreInstitucion"] = data.institution.nombre
        if event in (E.INVITACION_INSTITUCION, E.INVITACION_ACEPTADA, E.AGREGADO_INSTITUCION):
            values["rol"] = inst.rolInstitucion
        if event == E.ROL_INSTITUCIONAL_CAMBIADO:
            values["rolNuevo"] = inst.rolInstitucion
        if event == E.INVITACION_ACEPTADA:
            values["nombreInvitado"] = fullName(user)
        values["nombreInvitante"] = values.get("nombreInvitante") or data.institutionInviter
        values["nombreOperador"] = data.institutionOtherOperator
        values["fechaEvento"] = values.get("fechaEvento") or inst.fechaIncorporacion or inst.fechaInvitacion

    measurement = data.lastMeasurement
    if measurement is not None and category == CATEGORIA_MEDICIONES:
        values.update(
            fechaMedicion=measurement.fechaHoraInicio,
            dispositivo=(data.device.nombre or data.device.codigoDispositivo) if data.device else None,
            estadoRegistro=ESTADOS_MEDICION.get(measurement.estadoMedicion, measurement.estadoMedicion),
            valorGlucosa=str(measurement.glucosaEstimada) if measurement.glucosaEstimada is not None else None,
            spo2=str(measurement.spo2) if measurement.spo2 is not None else None,
            frecuenciaCardiaca=measurement.frecuenciaCardiaca,
            condicionComida=CONDICIONES_COMIDA.get(measurement.condicionComida),
            fechaUltimaComida=measurement.fechaHoraUltimaComida,
        )
        if event == E.ERROR_MEDICION:
            values["fechaEvento"] = measurement.fechaHoraInicio
    return values


def buildContext(event: E, sample: dict, data: RealData | None) -> tuple[dict, list[str], list[str]]:
    """Combina la muestra con los datos reales. Devuelve (contexto, camposReales, camposDeMuestra).

    Solo se reemplazan variables que el correo usa (las presentes en la muestra del evento).
    """
    context = dict(sample)
    real = _realValues(event, data) if data is not None else {}
    realKeys = []
    for key in sample:
        value = real.get(key)
        if value is not None and value != "":
            context[key] = value
            realKeys.append(key)
    sampleKeys = [key for key in sample if key not in realKeys and not key.startswith("url")]
    return context, realKeys, sampleKeys
