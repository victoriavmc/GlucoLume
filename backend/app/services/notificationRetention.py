# NotificationRetention - Conservación de los avisos de la bandeja de «Notificaciones» (RN-NOT-05)
#
# Qué se elimina: filas de NotificacionUsuario, que son solo el texto del aviso y el rastro de su entrega. Qué NO se toca: la auditoría
# (Auditoria, AuditoriaContexto), ni los hechos que originaron el aviso, ni nada de otras tablas. Los plazos son parámetros:
#   NOTIFICATION_READ_RETENTION_DAYS    avisos ya leídos (y los que la cuenta no quiso ver en la página, que solo son rastro de correo)
#   NOTIFICATION_UNREAD_RETENTION_DAYS  avisos que nunca se leyeron
# 0 desactiva cada parte. Se ejecuta con `python -m app.jobs.reminders depurar` (cuenta de procesos de conservación, la única con DELETE
# sobre esta tabla; ver database/reference/GlucoLume_permisos.sql). Nada la programa sola: la agenda quien administra el servidor.

from datetime import datetime, timedelta

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import getSettings
from app.models.userNotification import UserNotification
from app.utils.timeZone import nowForDb


def _conditions(now: datetime):
    settings = getSettings()
    parts = []
    if settings.NOTIFICATION_READ_RETENTION_DAYS > 0:
        cutoff = now - timedelta(days=settings.NOTIFICATION_READ_RETENTION_DAYS)
        parts.append(and_(UserNotification.fechaCreacion < cutoff,
                          or_(UserNotification.fechaLectura.is_not(None),
                              UserNotification.visible == False)))  # noqa: E712 - BIT: se compara con =, no con IS
    if settings.NOTIFICATION_UNREAD_RETENTION_DAYS > 0:
        cutoff = now - timedelta(days=settings.NOTIFICATION_UNREAD_RETENTION_DAYS)
        parts.append(and_(UserNotification.fechaCreacion < cutoff, UserNotification.fechaLectura.is_(None)))
    return or_(*parts) if parts else None


def plan(db: Session, now: datetime | None = None) -> dict:
    """Solo lectura: cuántos avisos eliminaría una pasada ahora."""
    settings = getSettings()
    condition = _conditions(now or nowForDb())
    count = 0 if condition is None else db.scalar(select(func.count(UserNotification.idNotificacion)).where(condition)) or 0
    return {"avisosVencidos": count, "diasLeidos": settings.NOTIFICATION_READ_RETENTION_DAYS,
            "diasNoLeidos": settings.NOTIFICATION_UNREAD_RETENTION_DAYS}


def purge(db: Session, now: datetime | None = None) -> int:
    """Elimina los avisos vencidos y devuelve cuántos. Sin plazos configurados no hace nada."""
    condition = _conditions(now or nowForDb())
    if condition is None:
        return 0
    deleted = db.execute(delete(UserNotification).where(condition)).rowcount
    db.commit()
    return deleted
