# UserNotifications - Rutas de «Notificaciones» (/api/v1/notificaciones)
#
# Solo traduce HTTP <-> servicio (services/userNotifications.py). La identidad sale siempre de la sesión.
# El correo de inicio de sesión se guarda en authService (es el mismo interruptor del correo de nuevo acceso).

import logging
import uuid

from fastapi import APIRouter, Query

from app.api.deps import CurrentAuth, DbSession
from app.schemas.userNotification import (
    AlcanceEliminacion,
    CategoriaAviso,
    EventoAviso,
    NotificationPreferenceUpdate,
    NotificationSettingsRead,
    ReminderScheduleUpdate,
    UserNotificationDeleteResult,
    UserNotificationInbox,
    UserNotificationReadResult,
)
from app.services import auth as authService
from app.services import userNotifications as notificationService

router = APIRouter(prefix="/notificaciones", tags=["notificaciones"])
logger = logging.getLogger(__name__)


@router.get("/preferencias", response_model=NotificationSettingsRead, summary="Avisos y horario de medición de la cuenta")
def getSettings(auth: CurrentAuth, db: DbSession):
    return notificationService.settings(db, auth.user)


@router.put(
    "/preferencias/{evento}", response_model=NotificationSettingsRead,
    summary="Elegir en qué canales recibir un aviso",
    description="`enPagina` muestra el aviso en la sección; `porCorreo` envía un correo. Los campos omitidos no cambian.",
)
def updatePreference(evento: EventoAviso, data: NotificationPreferenceUpdate, auth: CurrentAuth, db: DbSession):
    if evento == notificationService.INICIO_SESION and data.porCorreo is not None:
        authService.setNewLoginNotification(db, auth.user, data.porCorreo)
    notificationService.updatePreference(db, auth.user, evento, enPagina=data.enPagina, porCorreo=data.porCorreo)
    return notificationService.settings(db, auth.user)


@router.put(
    "/recordatorio", response_model=NotificationSettingsRead, summary="Horario para recordarme medirme",
    description=(
        "`INTERVALO` recuerda cada `intervaloHoras` (1, 2, 3, 4, 6, 8, 12 o 24). `HORARIOS` recuerda a horas fijas "
        "(hasta 6, formato HH:MM). `NINGUNO` apaga los recordatorios. Solo cuentas individuales. Los canales se eligen en "
        "`/preferencias/RECORDATORIO_MEDICION`."
    ),
)
def updateReminder(data: ReminderScheduleUpdate, auth: CurrentAuth, db: DbSession):
    notificationService.updateSchedule(db, auth.user, data)
    return notificationService.settings(db, auth.user)


@router.get(
    "", response_model=UserNotificationInbox, summary="Avisos de la página",
    description=(
        "Una página de los avisos propios, del más nuevo al más viejo. `categoria` (SEGURIDAD, GRUPO o RECORDATORIO) y `soloNoLeidas` "
        "filtran; `limite` (1 a 50, 20 por omisión) y `desplazamiento` paginan: `hayMas` indica que quedan más. `noLeidas` cuenta todos "
        "los propios sin leer, sin importar el filtro."
    ),
)
def inbox(
    auth: CurrentAuth, db: DbSession,
    categoria: CategoriaAviso | None = None,
    soloNoLeidas: bool = False,
    limite: int = Query(notificationService.INBOX_LIMIT, ge=1, le=notificationService.INBOX_MAX_LIMIT),
    desplazamiento: int = Query(0, ge=0, le=100_000),
):
    if desplazamiento == 0:
        # Respaldo del proceso programado (app/jobs/reminders.py): la reserva de la ocurrencia evita repetir un recordatorio ya enviado.
        try:
            notificationService.processOwnReminder(db, auth.user)
        except Exception as error:  # noqa: BLE001 - un recordatorio fallido no impide ver la bandeja
            db.rollback()
            logger.error("Recordatorio no procesado al abrir la bandeja (%s).", type(error).__name__)
    return notificationService.inbox(db, auth.user, categoria=categoria, soloNoLeidas=soloNoLeidas, limite=limite,
                                     desplazamiento=desplazamiento)


@router.delete(
    "", response_model=UserNotificationDeleteResult, summary="Quitar avisos propios de la bandeja",
    description=(
        "`alcance=leidas` quita los avisos ya leídos y `alcance=todas`, todos los de la bandeja de la cuenta autenticada (eliminación lógica, en una sola "
        "transacción). Es obligatorio: no hay un valor por omisión que vacíe la bandeja. Queda un evento de auditoría con la cantidad."
    ),
)
def deleteMany(alcance: AlcanceEliminacion, auth: CurrentAuth, db: DbSession):
    deleted = notificationService.deleteMany(db, auth.user, alcance)
    return UserNotificationDeleteResult(noLeidas=notificationService.unreadCount(db, auth.user), eliminadas=deleted)


@router.delete(
    "/{idNotificacion}", response_model=UserNotificationDeleteResult, summary="Quitar un aviso propio de la bandeja",
    description="Eliminación lógica. Un aviso de otra cuenta, inexistente o ya eliminado responde 404 NOTIFICACION_NO_ENCONTRADA.",
)
def deleteOne(idNotificacion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    deleted = notificationService.deleteNotification(db, auth.user, idNotificacion)
    return UserNotificationDeleteResult(noLeidas=notificationService.unreadCount(db, auth.user), eliminadas=deleted)


@router.post("/leer-todas", response_model=UserNotificationReadResult, summary="Marcar todos los avisos propios como leídos")
def markAllRead(auth: CurrentAuth, db: DbSession):
    marked = notificationService.markRead(db, auth.user)
    return UserNotificationReadResult(noLeidas=notificationService.unreadCount(db, auth.user), marcadas=marked)


@router.post(
    "/{idNotificacion}/leer", response_model=UserNotificationReadResult, summary="Marcar un aviso propio como leído",
    description="Un aviso de otra cuenta o inexistente responde 404 NOTIFICACION_NO_ENCONTRADA, sin distinguir cuál de los dos es.",
)
def markRead(idNotificacion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    marked = notificationService.markRead(db, auth.user, idNotificacion)
    return UserNotificationReadResult(noLeidas=notificationService.unreadCount(db, auth.user), marcadas=marked)
