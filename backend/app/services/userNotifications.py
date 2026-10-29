# UserNotifications - Avisos de la cuenta que la persona elige en «Notificaciones»
#
# Cada aviso tiene dos canales que se respetan por separado: la página (NotificacionUsuario, la bandeja de la sección) y el correo
# (services/email.py). El catálogo de avisos, sus categorías y cuáles son obligatorios está en app/models/notificationEvents.py. El correo
# de inicio de sesión sigue en Usuario.notificarNuevoInicioSesion (lo cambia authService.setNewLoginNotification); aquí solo se decide la página.
#
# Unicidad (RN-NOT-01): todo aviso lleva una `clave` que identifica el hecho que lo origina para esa cuenta (p. ej.
# «RECORDATORIO_MEDICION:2026-10-29T08:00:00» o «AGREGADO_GRUPO:<idGrupoUsuario>»). La fila de NotificacionUsuario es a la vez el aviso y el
# registro de su entrega, y un índice único (idUsuario, claveEvento) lo respalda en la base: procesar dos veces el mismo hecho, también
# en paralelo, deja una sola fila y un solo correo.
#
# Recordatorios (RN-NOT-02): los horarios (RecordatorioMedicion) se revisan con processReminders(), desde app/jobs/reminders.py (recomendado,
# llega también por correo) y como respaldo al abrir la bandeja. Cada ocurrencia se RESERVA antes de enviar con un UPDATE condicional sobre
# ultimoAviso: solo quien lo cambia envía, así que dos solicitudes o procesos simultáneos no repiten el recordatorio.
#
# Correo (RN-NOT-07): el aviso de la página se confirma ANTES de intentar el correo; una falla SMTP queda en estadoCorreo = FALLIDO y no lo
# quita. Reintentar el mismo hecho solo reenvía el correo, nunca crea otro aviso.
#
# Un aviso nunca revierte el hecho que lo causa (ya está confirmado): sus errores se registran y se siguen. Ningún texto incluye datos
# de salud ni valores de medición. Mientras el esquema nuevo no esté aplicado en la base (services/schemaCompat.py), los avisos se omiten
# en silencio y la sección responde que todavía no está disponible.

import logging
import uuid
from datetime import datetime, time, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.emails.eventTypes import EmailEventType
from app.models.groupUser import GroupUser
from app.models.notificationEvents import (  # noqa: F401 - los avisos se reexportan: los demás servicios los usan como userNotifications.X
    ACTIVIDAD_SOSPECHOSA,
    AGREGADO_GRUPO,
    CAMBIO_CONTRASENA,
    CAMBIO_MFA,
    CATALOGO,
    CATEGORIAS,
    EVENTOS,
    INICIO_SESION,
    INVITACION_GRUPO,
    MEDICION_GRUPO,
    NUEVA_ACCION_GRUPO,
    RECORDATORIO_MEDICION,
    eventsOf,
)
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
# Destinos que un aviso puede abrir: rutas que existen en la aplicación (frontend/src/App.jsx). Cualquier otra se descarta al guardar.
URLS_PERMITIDAS = (URL_MEDICIONES, URL_GRUPO, URL_SEGURIDAD)
INBOX_LIMIT = 20
INBOX_MAX_LIMIT = 50
ENVIO_PENDIENTE = "PENDIENTE"
ENVIO_ENVIADO = "ENVIADO"
ENVIO_FALLIDO = "FALLIDO"
# Intentos totales de un correo (el primero más los reintentos). Más allá queda FALLIDO: el aviso de la página no depende de él.
MAX_INTENTOS_CORREO = 3
REINTENTO_VENTANA = timedelta(hours=6)
ESQUEMA_PENDIENTE = "NOTIFICACIONES_NO_DISPONIBLES"
ESQUEMA_PENDIENTE_MESSAGE = "Las notificaciones todavía no están disponibles en esta instalación. Avisá al administrador."


def ready(db: Session) -> bool:
    """¿Tiene la base el esquema de «Notificaciones» (tablas y claves de unicidad)? Sin él, los avisos se omiten y la sección no escribe."""
    return all(schemaCompat.hasTable(db, table) for table in ("PreferenciaNotificacion", "RecordatorioMedicion",
                                                              "NotificacionUsuario")) \
        and schemaCompat.hasColumn(db, "NotificacionUsuario", "claveEvento")


def requireReady(db: Session) -> None:
    if not ready(db):
        raise AuthError(ESQUEMA_PENDIENTE, ESQUEMA_PENDIENTE_MESSAGE)


def safeUrl(url: str | None) -> str | None:
    """Solo rutas internas conocidas (o debajo de ellas): nunca un enlace externo ni una ruta inventada."""
    if not url or "//" in url or "\\" in url or ":" in url or "?" in url:
        return None
    return url if any(url == base or url.startswith(base + "/") for base in URLS_PERMITIDAS) else None


# --- Canales y preferencias ----------------------------------------------------------------------


def _channels(user: User, row: NotificationPreference | None, evento: str) -> tuple[bool, bool]:
    spec = CATALOGO[evento]
    if spec.obligatorio:
        return True, True  # alerta crítica: la página siempre; el correo lo envía el flujo de seguridad que la origina
    enPagina, porCorreo = spec.enPagina, spec.porCorreo
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
        preferencias.append(NotificationPreferenceRead(
            evento=evento, categoria=CATALOGO[evento].categoria, enPagina=enPagina, porCorreo=porCorreo,
            obligatoria=CATALOGO[evento].obligatorio))
    return NotificationSettingsRead(preferencias=preferencias, recordatorio=_scheduleRead(schedule))


def updatePreference(db: Session, user: User, evento: str, *, enPagina: bool | None = None,
                     porCorreo: bool | None = None) -> None:
    """Cambia los canales de un aviso. El correo de INICIO_SESION lo guarda authService (ver api/v1/userNotifications.py).

    Las alertas críticas de seguridad no se pueden apagar. Sin cambio no se audita. Solo se registra qué canal cambió, no datos personales.
    """
    if evento not in CATALOGO:
        raise AuthError("EVENTO_NO_VALIDO", "Ese aviso no existe.")
    if CATALOGO[evento].obligatorio:
        raise AuthError("AVISO_OBLIGATORIO", "Es una alerta de seguridad: se entrega siempre y no se puede desactivar.")
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
    row.porCorreo = CATALOGO[evento].porCorreo if evento == INICIO_SESION else newCorreo
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
    """Guarda (o apaga, con modo NINGUNO) el horario. La API no borra filas: «eliminar» la programación es apagarla."""
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


def _claimOccurrence(db: Session, schedule: ReminderSchedule, due: datetime) -> bool:
    """Reserva la ocurrencia `due`: solo UNA ejecución puede mover ultimoAviso hasta ese instante y, por lo tanto, enviar."""
    claimed = db.execute(
        update(ReminderSchedule)
        .where(ReminderSchedule.idUsuario == schedule.idUsuario,
               or_(ReminderSchedule.ultimoAviso.is_(None), ReminderSchedule.ultimoAviso < due))
        .values(ultimoAviso=due).execution_options(synchronize_session=False)
    ).rowcount == 1
    db.commit()
    if claimed:
        schedule.ultimoAviso = due
    return claimed


def _reminderEmail() -> tuple[EmailEventType, dict]:
    return EmailEventType.RECORDATORIO_MEDICION, {"urlMediciones": emailService.frontendUrl(URL_MEDICIONES)}


def reminderKey(due: datetime) -> str:
    return f"{RECORDATORIO_MEDICION}:{due:%Y-%m-%dT%H:%M:%S}"


def processReminders(db: Session, user: User, schedule: ReminderSchedule, now: datetime | None = None) -> bool:
    """Envía el recordatorio vencido de esta cuenta por los canales que eligió. Devuelve True si esta ejecución lo reservó y emitió."""
    now = now or nowForDb()
    due = dueReminderAt(schedule, now)
    if due is None or not _claimOccurrence(db, schedule, due):
        return False
    notify(db, user, RECORDATORIO_MEDICION, "Es hora de medirte",
           "Conectá tu dispositivo y registrá una medición cuando puedas.", url=URL_MEDICIONES,
           email=_reminderEmail(), clave=reminderKey(due))
    return True


def processOwnReminder(db: Session, user: User) -> bool:
    """Respaldo al abrir la bandeja: revisa solo el horario de esta cuenta (la reserva evita repetir lo que ya hizo el proceso programado)."""
    if not ready(db):
        return False
    schedule = db.get(ReminderSchedule, user.idUsuario)
    if schedule is None or schedule.modo == MODO_NINGUNO:
        return False
    return processReminders(db, user, schedule)


def retryFailedReminderEmails(db: Session, now: datetime | None = None) -> int:
    """Reenvía solo el CORREO de recordatorios recientes que fallaron (hasta MAX_INTENTOS_CORREO). No crea avisos nuevos."""
    if not ready(db):
        return 0
    now = now or nowForDb()
    rows = db.scalars(select(UserNotification).where(
        UserNotification.evento == RECORDATORIO_MEDICION, UserNotification.estadoCorreo == ENVIO_FALLIDO,
        UserNotification.intentosCorreo < MAX_INTENTOS_CORREO, UserNotification.fechaCreacion >= now - REINTENTO_VENTANA
    ).execution_options(populate_existing=True)).all()
    retried = 0
    for row in rows:
        user = db.get(User, row.idUsuario)
        if user is None or user.estado != ESTADO_ACTIVO or not user.correoElectronico:
            continue
        if not _channels(user, _preferenceRow(db, user, RECORDATORIO_MEDICION), RECORDATORIO_MEDICION)[1]:
            continue  # la cuenta apagó el correo después: se respeta
        if _resendEmail(db, row, user, _reminderEmail()):
            retried += 1
    return retried


# --- Envío -----------------------------------------------------------------------------------------


def _sendAndRecord(bind, idNotificacion: uuid.UUID, eventType: EmailEventType, to: str, context: dict) -> None:
    """Envía el correo y anota el resultado en el aviso, con una sesión propia (el hilo no comparte la de la solicitud)."""
    try:
        sent = emailService.sendEmailEvent(eventType, to, context)
    except Exception as error:  # noqa: BLE001 - un error del correo nunca debe terminar el hilo ni tocar el aviso
        logger.error("Correo %s no generado (%s).", eventType, type(error).__name__)
        sent = False
    try:
        with Session(bind) as session:
            session.execute(update(UserNotification).where(UserNotification.idNotificacion == idNotificacion).values(
                estadoCorreo=ENVIO_ENVIADO if sent else ENVIO_FALLIDO,
                intentosCorreo=UserNotification.intentosCorreo + 1).execution_options(synchronize_session=False))
            session.commit()
    except Exception as error:  # noqa: BLE001 - el correo ya salió o falló; solo se pierde el rastro
        logger.error("No se pudo anotar el resultado del correo %s (%s).", eventType, type(error).__name__)


def _queueEmail(db: Session, row: UserNotification, user: User, email: tuple[EmailEventType, dict]) -> None:
    eventType, context = email
    emailService.runInBackground(_sendAndRecord, db.get_bind(), row.idNotificacion, eventType, user.correoElectronico,
                                 {"nombre": user.nombre, **context})


def _resendEmail(db: Session, row: UserNotification, user: User, email: tuple[EmailEventType, dict]) -> bool:
    """Vuelve a intentar SOLO el correo de un aviso cuyo envío falló. El aviso de la página no se toca."""
    if row.estadoCorreo != ENVIO_FALLIDO or row.intentosCorreo >= MAX_INTENTOS_CORREO:
        return False
    row.estadoCorreo = ENVIO_PENDIENTE
    db.commit()
    _queueEmail(db, row, user, email)
    return True


def notify(db: Session, user: User, evento: str, titulo: str, mensaje: str, *, url: str | None = None,
           email: tuple[EmailEventType, dict] | None = None, clave: str | None = None) -> bool:
    """Avisa a `user` por la página y/o por correo según sus preferencias. Devuelve True si encoló un correo.

    `email` es (evento de correo, contexto); sin él el aviso es solo de la página (las alertas críticas ya envían su correo por su flujo).
    `clave` identifica el hecho de origen para esta cuenta: un segundo aviso con la misma clave no crea otra fila ni otro correo (solo,
    si el correo falló antes, lo reintenta). Sin clave el aviso se trata como un hecho único. Nunca propaga errores: el hecho que avisa
    ya está confirmado.
    """
    try:
        if not ready(db):
            return False
        enPagina, porCorreo = _channels(user, _preferenceRow(db, user, evento), evento)
        sendMail = bool(porCorreo and email is not None and user.correoElectronico)
        if not enPagina and not sendMail:
            return False
        clave = clave or f"{evento}:{uuid.uuid4()}"
        existing = db.scalar(select(UserNotification).where(
            UserNotification.idUsuario == user.idUsuario, UserNotification.claveEvento == clave
        ).execution_options(populate_existing=True))  # el estado del correo lo anota otro hilo: se lee el vigente
        if existing is not None:
            return bool(sendMail and _resendEmail(db, existing, user, email))
        row = UserNotification(
            idUsuario=user.idUsuario, evento=evento, titulo=titulo, mensaje=mensaje, url=safeUrl(url), claveEvento=clave,
            fechaCreacion=nowForDb(), visible=enPagina, estadoCorreo=ENVIO_PENDIENTE if sendMail else None, intentosCorreo=0)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # otro proceso registró el mismo hecho un instante antes: ya hay un aviso
            return False
        if sendMail:
            _queueEmail(db, row, user, email)
        return sendMail
    except Exception as error:  # noqa: BLE001 - un aviso fallido nunca deshace el hecho que avisa
        db.rollback()
        logger.error("Aviso %s no registrado (%s).", evento, type(error).__name__)
        return False


def notifyGroupNews(db: Session, idGrupo: uuid.UUID, idActor: uuid.UUID, texto: str, context: dict, origen: str) -> None:
    """Novedad del grupo para los demás integrantes ACTIVOS (página y correo según sus preferencias).

    `origen` identifica el hecho (p. ej. el idGrupoUsuario de quien se sumó o salió): junto con cada destinatario forma la clave de unicidad.
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
        notify(db, member, NUEVA_ACCION_GRUPO, "Novedad en tu grupo", texto, url=URL_GRUPO, email=email,
               clave=f"{NUEVA_ACCION_GRUPO}:{origen}")


# --- Bandeja de avisos ----------------------------------------------------------------------------


def _readRow(row: UserNotification) -> UserNotificationRead:
    return UserNotificationRead(
        idNotificacion=row.idNotificacion, evento=row.evento, categoria=CATALOGO[row.evento].categoria, titulo=row.titulo,
        mensaje=row.mensaje, url=safeUrl(row.url), fechaCreacion=withArgentinaZone(row.fechaCreacion),
        leida=row.fechaLectura is not None,
    )


def _ownVisible(user: User):
    # BIT: se compara con = (SQL Server no admite «IS 1»).
    return (UserNotification.idUsuario == user.idUsuario, UserNotification.visible == True)  # noqa: E712


def unreadCount(db: Session, user: User) -> int:
    return db.scalar(select(func.count(UserNotification.idNotificacion)).where(
        *_ownVisible(user), UserNotification.fechaLectura.is_(None))) or 0


def inbox(db: Session, user: User, *, categoria: str | None = None, soloNoLeidas: bool = False,
          limite: int = INBOX_LIMIT, desplazamiento: int = 0) -> UserNotificationInbox:
    """Una página de los avisos propios, del más nuevo al más viejo, con el filtro pedido. `noLeidas` ignora el filtro."""
    if not ready(db):
        return UserNotificationInbox(noLeidas=0, notificaciones=[])
    if categoria is not None and categoria not in CATEGORIAS:
        raise AuthError("CATEGORIA_NO_VALIDA", "Esa categoría de avisos no existe.")
    limite = min(max(limite, 1), INBOX_MAX_LIMIT)
    desplazamiento = max(desplazamiento, 0)
    filters = list(_ownVisible(user))
    if categoria is not None:
        filters.append(UserNotification.evento.in_(eventsOf(categoria)))
    if soloNoLeidas:
        filters.append(UserNotification.fechaLectura.is_(None))
    total = db.scalar(select(func.count(UserNotification.idNotificacion)).where(*filters)) or 0
    rows = db.scalars(
        select(UserNotification).where(*filters)
        .order_by(UserNotification.fechaCreacion.desc(), UserNotification.idNotificacion)
        .limit(limite).offset(desplazamiento)
    ).all()
    return UserNotificationInbox(noLeidas=unreadCount(db, user), total=total,
                                 hayMas=desplazamiento + len(rows) < total,
                                 notificaciones=[_readRow(row) for row in rows])


def markRead(db: Session, user: User, idNotificacion: uuid.UUID | None = None) -> int:
    """Marca como leído un aviso propio, o todos los propios si no se indica ninguno. Devuelve cuántos cambió.

    Un aviso ajeno o inexistente responde igual (NOTIFICACION_NO_ENCONTRADA): no revela si existe.
    """
    requireReady(db)
    query = update(UserNotification).where(*_ownVisible(user), UserNotification.fechaLectura.is_(None))
    if idNotificacion is not None:
        exists = db.scalar(select(UserNotification.idNotificacion).where(
            UserNotification.idNotificacion == idNotificacion, *_ownVisible(user)))
        if exists is None:
            raise AuthError("NOTIFICACION_NO_ENCONTRADA", "No encontramos ese aviso.")
        query = query.where(UserNotification.idNotificacion == idNotificacion)
    marked = db.execute(query.values(fechaLectura=nowForDb()).execution_options(synchronize_session=False)).rowcount
    db.commit()
    return marked


# --- Alertas de seguridad ---------------------------------------------------------------------------


def notifySecurity(db: Session, user: User, evento: str, titulo: str, mensaje: str, hecho: str) -> bool:
    """Alerta crítica de seguridad en la página (cambio de contraseña o de MFA, actividad sospechosa). No se puede apagar.

    El correo de estas alertas lo envía el flujo que las origina; aquí solo se guarda el aviso. `hecho` identifica el suceso (p. ej. el
    instante del cambio o el fin del bloqueo): repetir el mismo suceso no crea otro aviso.
    """
    return notify(db, user, evento, titulo, mensaje, url=URL_SEGURIDAD, clave=f"{evento}:{hecho}")
