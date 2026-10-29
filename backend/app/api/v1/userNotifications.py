# UserNotifications - Rutas de «Notificaciones» (/api/v1/notificaciones)
#
# Solo traduce HTTP <-> servicio (services/userNotifications.py). La identidad sale siempre de la sesión.
# El correo de inicio de sesión se guarda en authService (es el mismo interruptor del correo de nuevo acceso).

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentAuth, DbSession
from app.schemas.userNotification import (
    EventoAviso,
    NotificationPreferenceUpdate,
    NotificationSettingsRead,
    ReminderScheduleUpdate,
    UserNotificationInbox,
)
from app.services import auth as authService
from app.services import userNotifications as notificationService

router = APIRouter(prefix="/notificaciones", tags=["notificaciones"])


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


@router.get("", response_model=UserNotificationInbox, summary="Avisos de la página")
def inbox(auth: CurrentAuth, db: DbSession):
    return notificationService.inbox(db, auth.user)


@router.post("/leer-todas", response_model=UserNotificationInbox, summary="Marcar todos los avisos como leídos")
def markAllRead(auth: CurrentAuth, db: DbSession):
    notificationService.markRead(db, auth.user)
    return notificationService.inbox(db, auth.user)


@router.post("/{idNotificacion}/leer", response_model=UserNotificationInbox, summary="Marcar un aviso como leído")
def markRead(idNotificacion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    notificationService.markRead(db, auth.user, idNotificacion)
    return notificationService.inbox(db, auth.user)
