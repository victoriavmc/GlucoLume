# Recordatorios de medición por correo y por la página (horarios de «Notificaciones») y conservación de los avisos
#
#     python -m app.jobs.reminders --loop       servicio «notifications» de Compose: una pasada cada NOTIFICATIONS_INTERVAL_SECONDS, sin terminar
#     python -m app.jobs.reminders --health     healthcheck del contenedor (0 = sano)
#     python -m app.jobs.reminders ejecutar     una pasada: recordatorios vencidos y reintento del correo de los que fallaron
#     python -m app.jobs.reminders depurar      elimina avisos vencidos de la bandeja (NOTIFICATION_*_RETENTION_DAYS; no toca la auditoría)
#     python -m app.jobs.reminders previsualizar  solo lectura: cuántos avisos eliminaría «depurar»
#
# «ejecutar» recorre las cuentas con horario de medición y envía el recordatorio vencido por los canales que eligieron
# (services/userNotifications.py). Es idempotente: cada ocurrencia se reserva con un UPDATE condicional sobre ultimoAviso y el aviso lleva una
# clave de unicidad, así que puede correr cada pocos segundos, en varios procesos a la vez y mientras se abre la bandeja sin repetir nada.
# Un correo que falló se reintenta (hasta 3 intentos, dentro de las 6 horas) sin crear un aviso nuevo.
#
# «--loop» es lo que hace que un recordatorio llegue a su hora aunque nadie tenga la aplicación abierta: sin este servicio solo se procesa al
# abrir la bandeja. Una vez por hora, en el mismo ciclo, depura los avisos vencidos. NO es el servicio «lifecycle» (que elimina cuentas
# institucionales y puede estar apagado): este solo genera y depura avisos. Un fallo de una pasada se registra y el ciclo sigue.
# Usa la cuenta de procesos (DB_JOBS_USER) si está configurada, igual que el resto de los procesos de conservación; «depurar» la necesita
# (es la única con DELETE sobre NotificacionUsuario). Sin ella, los recordatorios funcionan y la depuración se registra como fallida.

import argparse
import json
import logging
import sys
import tempfile
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import getSettings
from app.db.session import getJobsSessionFactory
from app.models.reminderSchedule import ReminderSchedule
from app.models.user import User
from app.services import notificationRetention, userNotifications
from app.utils.timeZone import nowForDb


logger = logging.getLogger("glucolume.notifications")
HEARTBEAT = Path(tempfile.gettempdir()) / "glucolume-notifications.heartbeat"
HEALTH_MARGIN_SECONDS = 120
PURGE_EVERY_SECONDS = 3600


def run(db: Session, now=None) -> dict:
    """Una pasada: envía los recordatorios vencidos. Devuelve cuántas cuentas se revisaron y cuántas recibieron aviso."""
    if not userNotifications.ready(db):
        return {"revisadas": 0, "avisadas": 0, "reintentos": 0, "motivo": userNotifications.ESQUEMA_PENDIENTE}
    now = now or nowForDb()
    # Primero los reintentos de correos que fallaron en una pasada anterior: uno que falla ahora espera a la próxima.
    retried = userNotifications.retryFailedReminderEmails(db, now)
    schedules = db.scalars(select(ReminderSchedule).where(ReminderSchedule.modo != userNotifications.MODO_NINGUNO)).all()
    reviewed = notified = 0
    for schedule in schedules:
        reviewed += 1
        user = db.get(User, schedule.idUsuario)
        if user is None or user.estado != userNotifications.ESTADO_ACTIVO:
            continue
        if userNotifications.processReminders(db, user, schedule, now):
            notified += 1
    return {"revisadas": reviewed, "avisadas": notified, "reintentos": retried}


def beat() -> None:
    """Marca de vida: la pasada terminó (con o sin novedades). El healthcheck del contenedor la mira."""
    try:
        HEARTBEAT.touch()
    except OSError:
        logger.warning("No se pudo escribir la marca de vida del servicio de notificaciones.")


def healthy() -> bool:
    """Sano si completó una pasada hace menos de dos intervalos (más un margen)."""
    try:
        return time.time() - HEARTBEAT.stat().st_mtime < 2 * getSettings().NOTIFICATIONS_INTERVAL_SECONDS + HEALTH_MARGIN_SECONDS
    except OSError:
        return False


def onePass(purge: bool) -> dict:
    """Una pasada del servicio. Cada parte tiene su sesión y su manejo de errores: una no frena a la otra ni al ciclo."""
    result: dict = {}
    try:
        with getJobsSessionFactory()() as db:
            result["recordatorios"] = run(db)
    except Exception:  # noqa: BLE001
        logger.exception("Falló la pasada de recordatorios")
        result["recordatorios"] = None
    if purge:
        try:
            with getJobsSessionFactory()() as db:
                result["avisosEliminados"] = notificationRetention.purge(db)
        except Exception as error:  # noqa: BLE001
            # Sin DB_JOBS_USER (o sin el DELETE de GlucoLume_permisos.sql) la depuración no puede borrar: los recordatorios siguen funcionando.
            logger.warning("No se pudo depurar la bandeja (%s): ¿DB_JOBS_USER tiene DELETE sobre NotificacionUsuario? Se reintenta en una hora.",
                           type(error).__name__)
            result["avisosEliminados"] = None
    return result


def loop() -> None:
    interval = getSettings().NOTIFICATIONS_INTERVAL_SECONDS
    logger.info("Servicio de notificaciones activo (recordatorios cada %s s, depuración cada %s s).", interval, PURGE_EVERY_SECONDS)
    beat()
    lastPurge = 0.0  # la primera pasada también depura
    while True:
        purge = time.monotonic() - lastPurge >= PURGE_EVERY_SECONDS
        result = onePass(purge)
        if purge:
            lastPurge = time.monotonic()
        found = result.get("recordatorios") or {}
        if found.get("avisadas") or found.get("reintentos") or result.get("avisosEliminados"):  # sin novedades no se llena el registro
            logger.info("Notificaciones: %s", result)
        beat()
        time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if "--health" in argv:
        return 0 if healthy() else 1
    if "--loop" in argv:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
        loop()
        return 0
    parser = argparse.ArgumentParser(description="Recordatorios de medición (página y correo) y conservación de los avisos.")
    parser.add_argument("orden", choices=["ejecutar", "depurar", "previsualizar"])
    args = parser.parse_args(argv)
    with getJobsSessionFactory()() as db:
        if args.orden == "ejecutar":
            result = run(db)
        elif args.orden == "previsualizar":
            result = notificationRetention.plan(db)
        else:
            result = {"avisosEliminados": notificationRetention.purge(db)}
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
