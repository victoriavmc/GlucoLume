# UserNotifications - Avisos de la cuenta que la persona elige en «Notificaciones»
#
# Cada aviso tiene dos canales: la página (NotificacionUsuario, la lista de avisos de la sección) y el correo (services/email.py).
# Los eventos son: inicio de sesión, alta en un grupo, recordatorio de medición y novedades del grupo. El correo de inicio de sesión
# sigue en Usuario.notificarNuevoInicioSesion (lo cambia authService.setNewLoginNotification); aquí solo se decide la página.
#
# Los recordatorios de horario (RecordatorioMedicion) se revisan con processReminders(): desde la sección (al abrirla) y desde
# app/jobs/recordatorios.py para que lleguen también por correo. ultimoAviso evita repetir un recordatorio.
#
# Un aviso nunca revierte el hecho que lo causa (ya está confirmado): sus errores se registran y se siguen. Ningún texto incluye datos
# de salud ni valores de medición. Mientras el esquema nuevo no esté aplicado en la base (services/schemaCompat.py), los avisos se omiten
# en silencio y la sección responde que todavía no está disponible.

import logging
import uuid
from datetime import datetime, time, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.emails.eventTypes import EmailEventType
from app.models.groupUser import GroupUser
from app.models.notificationPreference import NotificationPreference
from app.models.reminderSchedule import ReminderSchedule
from app.models.user import User
from app.models.userNotification import UserNotification
from app.schemas.userNotification import (
    NotificationPreferenceRead,
    NotificationSettingsRead,
    ReminderScheduleRead,
    ReminderScheduleUpdate,
    UserNotificationInbox,
    UserNotificationRead,
)
from app.services import email as emailService
from app.services import schemaCompat
from app.services.audit import registerEvent
from app.utils.timeZone import nowForDb, withArgentinaZone

logger = logging.getLogger(__name__)

INICIO_SESION = "INICIO_SESION"
AGREGADO_GRUPO = "AGREGADO_GRUPO"
RECORDATORIO_MEDICION = "RECORDATORIO_MEDICION"
NUEVA_ACCION_GRUPO = "NUEVA_ACCION_GRUPO"
EVENTOS = (INICIO_SESION, AGREGADO_GRUPO, RECORDATORIO_MEDICION, NUEVA_ACCION_GRUPO)
# (en la página, por correo) mientras la cuenta no elija otra cosa. INICIO_SESION por correo se lee de Usuario.notificarNuevoInicioSesion.
DEFAULTS = {
    INICIO_SESION: (True, True),
    AGREGADO_GRUPO: (True, True),
    RECORDATORIO_MEDICION: (True, False),
    NUEVA_ACCION_GRUPO: (True, True),
}
MODO_NINGUNO = "NINGUNO"
MODO_INTERVALO = "INTERVALO"
MODO_HORARIOS = "HORARIOS"
ESTADO_ACTIVO = "ACTIVO"
ESTADO_RELACION_ACTIVO = "ACTIVO"
ROL_PROPIETARIO = "PROPIETARIO"
TIPO_INDIVIDUAL = "CONSUMIDOR_FINAL"
URL_MEDICIONES = "/app/mediciones"
URL_GRUPO = "/app/grupo"
URL_SEGURIDAD = "/app/seguridad"
INBOX_LIMIT = 50
ESQUEMA_PENDIENTE = "NOTIFICACIONES_NO_DISPONIBLES"
ESQUEMA_PENDIENTE_MESSAGE = "Las notificaciones todavía no están disponibles en esta instalación. Avisá al administrador."


def ready(db: Session) -> bool:
    """¿Tiene la base las tablas de «Notificaciones»? Sin ellas, los avisos se omiten y la sección no escribe."""
    return all(schemaCompat.hasTable(db, table) for table in ("PreferenciaNotificacion", "RecordatorioMedicion",
                                                              "NotificacionUsuario"))


def requireReady(db: Session) -> None:
    if not ready(db):
        raise AuthError(ESQUEMA_PENDIENTE, ESQUEMA_PENDIENTE_MESSAGE)


# --- Canales y preferencias ----------------------------------------------------------------------


def _channels(user: User, row: NotificationPreference | None, evento: str) -> tuple[bool, bool]:
    enPagina, porCorreo = DEFAULTS[evento]
    if row is not None:
        enPagina, porCorreo = row.enPagina, row.porCorreo
    if evento == INICIO_SESION:
        porCorreo = user.notificarNuevoInicioSesion
    return bool(enPagina), bool(porCorreo)


def _preferenceRow(db: Session, user: User, evento: str) -> NotificationPreference | None:
    return db.scalar(select(NotificationPreference).where(
        NotificationPreference.idUsuario == user.idUsuario, NotificationPreference.evento == evento))


def settings(db: Session, user: User) -> NotificationSettingsRead:
    """Estado actual. Sin el esquema nuevo muestra los valores por omisión (no hay nada guardado)."""
    rows: dict[str, NotificationPreference] = {}
    schedule = None
    if ready(db):
        rows = {row.evento: row for row in db.scalars(
            select(NotificationPreference).where(NotificationPreference.idUsuario == user.idUsuario)).all()}
        schedule = db.get(ReminderSchedule, user.idUsuario)
    preferencias = []
    for evento in EVENTOS:
        enPagina, porCorreo = _channels(user, rows.get(evento), evento)
        preferencias.append(NotificationPreferenceRead(evento=evento, enPagina=enPagina, porCorreo=porCorreo))
    return NotificationSettingsRead(preferencias=preferencias, recordatorio=_scheduleRead(schedule))


def updatePreference(db: Session, user: User, evento: str, *, enPagina: bool | None = None,
                     porCorreo: bool | None = None) -> None:
    """Cambia los canales de un aviso. El correo de INICIO_SESION lo guarda authService (ver api/v1/userNotifications.py).

    Sin cambio no se audita. Solo se registra qué canal cambió, no datos personales.
    """
    if evento not in EVENTOS:
        raise AuthError("EVENTO_NO_VALIDO", "Ese aviso no existe.")
    requireReady(db)
    row = _preferenceRow(db, user, evento)
    previousPagina, previousCorreo = _channels(user, row, evento)
    newPagina = previousPagina if enPagina is None else enPagina
    newCorreo = previousCorreo if porCorreo is None or evento == INICIO_SESION else porCorreo
    if (newPagina, newCorreo) == (previousPagina, previousCorreo):
        return
    if row is None:
        row = NotificationPreference(idUsuario=user.idUsuario, evento=evento)
        db.add(row)
    row.enPagina = newPagina
    # El correo de INICIO_SESION vive en Usuario.notificarNuevoInicioSesion: esta fila solo guarda la página para ese aviso.
    row.porCorreo = DEFAULTS[evento][1] if evento == INICIO_SESION else newCorreo
    row.fechaActualizacion = nowForDb()
    registerEvent(db, "CRUD", "PREFERENCIA_NOTIFICACION", True, user.idUsuario, "Usuario", user.idUsuario,
                  datosPrevios={"evento": evento, "enPagina": previousPagina, "porCorreo": previousCorreo},
                  datosNuevos={"evento": evento, "enPagina": newPagina, "porCorreo": newCorreo})
    db.commit()


# --- Horario de medición -------------------------------------------------------------------------


def _parseHorarios(value: str | None) -> list[time]:
    return [time.fromisoformat(part) for part in (value or "").split(",") if part]


def _scheduleRead(schedule: ReminderSchedule | None) -> ReminderScheduleRead:
    if schedule is None or schedule.modo == MODO_NINGUNO:
        return ReminderScheduleRead(modo=MODO_NINGUNO)
    horarios = [hora.strftime("%H:%M") for hora in _parseHorarios(schedule.horarios)]
    return ReminderScheduleRead(modo=schedule.modo, intervaloHoras=schedule.intervaloHoras, horarios=horarios)


def updateSchedule(db: Session, user: User, data: ReminderScheduleUpdate) -> None:
    if user.tipoCuenta != TIPO_INDIVIDUAL:
        raise AuthError("RECORDATORIO_NO_DISPONIBLE", "Los horarios de medición son para cuentas individuales.")
    requireReady(db)
    schedule = db.get(ReminderSchedule, user.idUsuario)
    if schedule is None:
        schedule = ReminderSchedule(idUsuario=user.idUsuario)
        db.add(schedule)
    schedule.modo = data.modo
    schedule.intervaloHoras = data.intervaloHoras if data.modo == MODO_INTERVALO else None
    schedule.horarios = ",".join(data.horarios) if data.modo == MODO_HORARIOS else None
    # El primer recordatorio cuenta desde ahora: nunca dispara por horarios anteriores a guardar la configuración.
    now = nowForDb()
    schedule.ultimoAviso = now
    schedule.fechaActualizacion = now
    registerEvent(db, "CRUD", "PREFERENCIA_NOTIFICACION", True, user.idUsuario, "Usuario", user.idUsuario,
                  datosNuevos={"evento": RECORDATORIO_MEDICION, "modo": data.modo,
                               "cantidadHorarios": len(data.horarios)})
    db.commit()


def dueReminderAt(schedule: ReminderSchedule, now: datetime) -> datetime | None:
    """Hora del recordatorio vencido y todavía no enviado (la que correspondía), o None.

    Por intervalo, el último vencimiento alineado con la cadencia. Por horarios, el horario más reciente de hoy o de ayer ya
    cumplido: si el proceso estuvo apagado, se envía uno solo, no uno por cada horario perdido.
    """
    last = schedule.ultimoAviso or now
    if schedule.modo == MODO_INTERVALO and schedule.intervaloHoras:
        step = timedelta(hours=schedule.intervaloHoras)
        if now - last < step:
            return None
        return last + ((now - last) // step) * step
    if schedule.modo == MODO_HORARIOS:
        days = (now.date() - timedelta(days=1), now.date())
        candidates = [datetime.combine(day, hora) for day in days for hora in _parseHorarios(schedule.horarios)]
        return max((c for c in candidates if last < c <= now), default=None)
    return None


def processReminders(db: Session, user: User, schedule: ReminderSchedule, now: datetime | None = None) -> bool:
    """Envía el recordatorio vencido de esta cuenta por los canales que eligió. Devuelve True si hubo recordatorio."""
    now = now or nowForDb()
    due = dueReminderAt(schedule, now)
    if due is None:
        return False
    schedule.ultimoAviso = due
    db.commit()
    notify(db, user, RECORDATORIO_MEDICION, "Es hora de medirte",
           "Conectá tu dispositivo y registrá una medición cuando puedas.", url=URL_MEDICIONES,
           email=(EmailEventType.RECORDATORIO_MEDICION,
                  {"urlMediciones": emailService.frontendUrl(URL_MEDICIONES)}))
    return True


# --- Envío -----------------------------------------------------------------------------------------


def notify(db: Session, user: User, evento: str, titulo: str, mensaje: str, *, url: str | None = None,
           email: tuple[EmailEventType, dict] | None = None) -> bool:
    """Avisa a `user` por la página y/o por correo según sus preferencias. Devuelve True si encoló un correo.

    `email` es (evento de correo, contexto). Nunca propaga errores: el hecho que avisa ya está confirmado.
    """
    try:
        if not ready(db):
            return False
        enPagina, porCorreo = _channels(user, _preferenceRow(db, user, evento), evento)
        if enPagina:
            db.add(UserNotification(idUsuario=user.idUsuario, evento=evento, titulo=titulo, mensaje=mensaje, url=url))
            db.commit()
        if porCorreo and email is not None and user.correoElectronico:
            eventType, context = email
            emailService.sendEmailEventInBackground(eventType, user.correoElectronico, {"nombre": user.nombre, **context})
            return True
        return False
    except Exception as error:  # noqa: BLE001 - un aviso fallido nunca deshace el hecho que avisa
        db.rollback()
        logger.error("Aviso %s no registrado (%s).", evento, type(error).__name__)
        return False


def notifyGroupNews(db: Session, idGrupo: uuid.UUID, idActor: uuid.UUID, texto: str, context: dict) -> None:
    """Novedad del grupo para los demás integrantes ACTIVOS (página y correo según sus preferencias).

    El administrador ya recibe el correo de MIEMBRO_AGREGADO / MIEMBRO_ABANDONO_GRUPO: a él solo se le avisa en la página.
    """
    idAdministrador = db.scalar(select(GroupUser.idUsuario).where(
        GroupUser.idGrupo == idGrupo, GroupUser.rolGrupo == ROL_PROPIETARIO,
        GroupUser.estadoRelacion == ESTADO_RELACION_ACTIVO))
    members = db.scalars(
        select(User).join(GroupUser, GroupUser.idUsuario == User.idUsuario).where(
            GroupUser.idGrupo == idGrupo, GroupUser.estadoRelacion == ESTADO_RELACION_ACTIVO,
            User.idUsuario != idActor, User.estado == ESTADO_ACTIVO)
    ).all()
    for member in members:
        email = None if member.idUsuario == idAdministrador else (EmailEventType.NOVEDAD_GRUPO,
                                                                 {"descripcion": texto, **context})
        notify(db, member, NUEVA_ACCION_GRUPO, "Novedad en tu grupo", texto, url=URL_GRUPO, email=email)


# --- Bandeja de avisos ----------------------------------------------------------------------------


def _readRow(row: UserNotification) -> UserNotificationRead:
    return UserNotificationRead(
        idNotificacion=row.idNotificacion, evento=row.evento, titulo=row.titulo, mensaje=row.mensaje, url=row.url,
        fechaCreacion=withArgentinaZone(row.fechaCreacion), leida=row.fechaLectura is not None,
    )


def inbox(db: Session, user: User) -> UserNotificationInbox:
    if not ready(db):
        return UserNotificationInbox(noLeidas=0, notificaciones=[])
    schedule = db.get(ReminderSchedule, user.idUsuario)
    if schedule is not None and schedule.modo != MODO_NINGUNO:
        processReminders(db, user, schedule)
    rows = db.scalars(
        select(UserNotification).where(UserNotification.idUsuario == user.idUsuario)
        .order_by(UserNotification.fechaCreacion.desc()).limit(INBOX_LIMIT)
    ).all()
    noLeidas = db.scalar(select(func.count(UserNotification.idNotificacion)).where(
        UserNotification.idUsuario == user.idUsuario, UserNotification.fechaLectura.is_(None))) or 0
    return UserNotificationInbox(noLeidas=noLeidas, notificaciones=[_readRow(row) for row in rows])


def markRead(db: Session, user: User, idNotificacion: uuid.UUID | None = None) -> None:
    """Marca como leído un aviso propio, o todos si no se indica ninguno."""
    requireReady(db)
    query = update(UserNotification).where(
        UserNotification.idUsuario == user.idUsuario, UserNotification.fechaLectura.is_(None))
    if idNotificacion is not None:
        query = query.where(UserNotification.idNotificacion == idNotificacion)
    db.execute(query.values(fechaLectura=nowForDb()).execution_options(synchronize_session=False))
    db.commit()
