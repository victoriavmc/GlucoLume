# Recordatorios de medición por correo y por la página (horarios de «Notificaciones») y conservación de los avisos
#
#     python -m app.jobs.reminders ejecutar     una pasada: recordatorios vencidos y reintento del correo de los que fallaron
#     python -m app.jobs.reminders depurar      elimina avisos vencidos de la bandeja (NOTIFICATION_*_RETENTION_DAYS; no toca la auditoría)
#     python -m app.jobs.reminders previsualizar  solo lectura: cuántos avisos eliminaría «depurar»
#
# «ejecutar» recorre las cuentas con horario de medición y envía el recordatorio vencido por los canales que eligieron
# (services/userNotifications.py). Es idempotente: cada ocurrencia se reserva con un UPDATE condicional sobre ultimoAviso y el aviso lleva una
# clave de unicidad, así que puede correr cada pocos minutos, en varios procesos a la vez y mientras se abre la bandeja sin repetir nada.
# Un correo que falló se reintenta (hasta 3 intentos, dentro de las 6 horas) sin crear un aviso nuevo.
# No programa nada: lo agenda quien administra el servidor (cron, Tareas programadas de Windows o el contenedor).
# Usa la cuenta de procesos (DB_JOBS_USER) si está configurada, igual que el resto de los procesos de conservación; «depurar» la necesita
# (es la única con DELETE sobre NotificacionUsuario).

import argparse
import json
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import getJobsSessionFactory
from app.models.reminderSchedule import ReminderSchedule
from app.models.user import User
from app.services import notificationRetention, userNotifications
from app.utils.timeZone import nowForDb


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


def main(argv: list[str] | None = None) -> int:
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
