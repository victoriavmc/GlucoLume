# Notifications - Confirmaciones por correo de la creación de grupos e instituciones
#
# Se envían después del commit de la creación (nunca antes: si la transacción falla, no hay correo) con el
# servicio central de correos (misma configuración SMTP y plantillas). El resultado queda en Auditoria
# (NOTIFICAR_CREACION_GRUPO / NOTIFICAR_CREACION_INSTITUCION, EXITO o FALLO, idRegistro = la entidad):
#   - un fallo de SMTP no revierte el grupo ni la institución: se registra y la creación responde normalmente;
#   - el reenvío solo procede si no hay un envío exitoso registrado, así un reintento no duplica el correo.
# En logs y auditoría no se guardan direcciones completas ni datos personales.

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.emails.eventTypes import EmailEventType
from app.models.audit import Audit
from app.models.group import Group
from app.models.groupUser import GroupUser
from app.models.institution import Institution
from app.models.user import User
from app.services import email as emailService
from app.services import userNotifications
from app.services.audit import registerEvent
from app.utils.timeZone import toDbTime

logger = logging.getLogger(__name__)

ACCION_GRUPO = "NOTIFICAR_CREACION_GRUPO"
ACCION_INSTITUCION = "NOTIFICAR_CREACION_INSTITUCION"
ALREADY_SENT_MESSAGE = "La confirmación de creación ya fue enviada."
NOT_SENT_MESSAGE = "No pudimos enviar el correo de confirmación. Intentá de nuevo más tarde."
ROL_PROPIETARIO = "PROPIETARIO"
INSTITUTION_TYPE_LABELS = {
    "HOSPITAL": "Hospital",
    "CLINICA": "Clínica",
    "CONSULTORIO": "Consultorio",
    "LABORATORIO": "Laboratorio",
    "OTRO": "Otro",
}


def _createdAt(entity) -> datetime:
    """fechaCreacion la completa SQL Server con sysutcdatetime() (UTC): se informa en hora de Argentina."""
    return toDbTime(entity.fechaCreacion.replace(tzinfo=timezone.utc))


def wasSent(db: Session, accion: str, idRegistro: uuid.UUID) -> bool:
    """True si la auditoría registra un envío exitoso de la confirmación de esta entidad."""
    return db.scalar(
        select(Audit.idAuditoria).where(
            Audit.accion == accion, Audit.idRegistro == idRegistro, Audit.resultado == "EXITO"
        ).limit(1)
    ) is not None


def _send(db: Session, user: User, accion: str, tabla: str, idRegistro: uuid.UUID,
          eventType: EmailEventType, context: dict) -> bool:
    """Envía y registra el resultado en una transacción propia (la entidad ya está confirmada)."""
    try:
        sent = emailService.sendEmailEvent(eventType, user.correoElectronico, context)
    except Exception as error:  # noqa: BLE001 - un error del correo nunca deshace una creación confirmada
        logger.error("Confirmación %s no generada (%s).", eventType, type(error).__name__)
        sent = False
    try:
        registerEvent(db, "CRUD", accion, sent, user.idUsuario, tabla, idRegistro,
                      observacion=None if sent else "No se pudo enviar el correo; se puede reintentar.")
        db.commit()
    except Exception as error:  # noqa: BLE001 - la creación ya respondió bien; solo se pierde el registro
        db.rollback()
        logger.error("No se pudo registrar el resultado de %s (%s).", accion, type(error).__name__)
    return sent


def notifyGroupCreated(db: Session, user: User, group: Group, *, fecha=None) -> bool:
    context = {
        "nombre": user.nombre,
        "nombreGrupo": group.nombre,
        "nombreCreador": f"{user.nombre} {user.apellido}".strip(),
        "rol": ROL_PROPIETARIO,
        "fechaEvento": fecha or _createdAt(group),
        "urlGrupo": emailService.frontendUrl(f"/app/grupo/{group.idGrupo}"),
    }
    return _send(db, user, ACCION_GRUPO, "Grupo", group.idGrupo, EmailEventType.GRUPO_CREADO, context)


def notifyGroupMeasurement(db: Session, user: User, when: datetime) -> int:
    """Avisa a los demás integrantes ACTIVOS del grupo de `user` que se midió (quién y cuándo, NUNCA el valor).

    Solo si esa persona activó `notificaMedicion` en su vínculo (permiso personal, apagado por defecto). Devuelve
    cuántos avisos se encolaron. Nunca propaga errores: la medición ya está completada y confirmada.
    """
    try:
        own = db.scalar(select(GroupUser).where(GroupUser.idUsuario == user.idUsuario,
                                                GroupUser.estadoRelacion == "ACTIVO",
                                                GroupUser.notificaMedicion == True))  # noqa: E712 - SQL Server recibe «IS 1» (error 102) si se usa el operador IS con un BIT: se compara con =
        if own is None:
            return 0
        group = db.get(Group, own.idGrupo)
        if group is None or group.estado != "ACTIVO":
            return 0
        recipients = db.scalars(
            select(User).join(GroupUser, GroupUser.idUsuario == User.idUsuario)
            .where(GroupUser.idGrupo == own.idGrupo, GroupUser.estadoRelacion == "ACTIVO",
                   GroupUser.idUsuario != user.idUsuario, User.estado == "ACTIVO")
        ).all()
        who = f"{user.nombre or ''} {user.apellido or ''}".strip() or "Un integrante"
        sent = 0
        for recipient in recipients:
            context = {"nombreIntegrante": who, "nombreGrupo": group.nombre,
                       "fechaMedicion": when, "urlGrupo": emailService.frontendUrl(f"/app/grupo/{group.idGrupo}")}
            # Página y correo según las preferencias de NUEVA_ACCION_GRUPO del destinatario. El correo se encola en segundo plano: el aviso no puede
            # demorar el cierre de la medición (cada envío SMTP bloquea la respuesta entre 1 y 20 s). Nadie espera su resultado.
            if userNotifications.notify(db, recipient, userNotifications.NUEVA_ACCION_GRUPO, "Novedad en tu grupo",
                                        f"{who} se midió.", url=userNotifications.URL_GRUPO,
                                        email=(EmailEventType.MEDICION_MIEMBRO_GRUPO, context)):
                sent += 1
        return sent
    except Exception as error:  # noqa: BLE001 - un fallo de correo o de consulta no deshace la medición
        logger.error("Aviso de medición al grupo no enviado (%s).", type(error).__name__)
        return 0


def notifyInstitutionCreated(db: Session, user: User, institution: Institution, *, fecha=None) -> bool:
    context = {
        "nombre": user.nombre,
        "nombreInstitucion": institution.nombre,
        "tipoInstitucion": INSTITUTION_TYPE_LABELS.get(institution.tipoInstitucion, institution.tipoInstitucion),
        "cuit": institution.identificadorLegal,
        "rol": ROL_PROPIETARIO,
        "fechaEvento": fecha or _createdAt(institution),
        "urlPanel": emailService.frontendUrl(f"/app/instituciones/{institution.idInstitucion}"),
    }
    return _send(db, user, ACCION_INSTITUCION, "Institucion", institution.idInstitucion,
                 EmailEventType.INSTITUCION_CREADA, context)


def resend(db: Session, user: User, accion: str, idRegistro: uuid.UUID, notify, entity) -> bool:
    """Reintento manual: solo si no hay un envío exitoso registrado (evita duplicados)."""
    if wasSent(db, accion, idRegistro):
        raise AuthError("NOTIFICACION_YA_ENVIADA", ALREADY_SENT_MESSAGE)
    return notify(db, user, entity)
