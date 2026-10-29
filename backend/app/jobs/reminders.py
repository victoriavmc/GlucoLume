# Recordatorios de medición por correo y por la página (horarios de «Notificaciones»)
#
#     python -m app.jobs.reminders ejecutar
#
# Recorre las cuentas con horario de medición y envía el recordatorio vencido por los canales que eligieron
# (services/userNotifications.py). Es idempotente: ultimoAviso evita repetirlo, así que puede correr cada pocos minutos.
# No programa nada: lo agenda quien administra el servidor (cron, Tareas programadas de Windows o el contenedor).
# Usa la cuenta de procesos (DB_JOBS_USER) si está configurada, igual que el resto de los procesos de conservación.

import argparse
import json
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import getJobsSessionFactory
from app.models.reminderSchedule import ReminderSchedule
from app.models.user import User
from app.services import userNotifications
from app.utils.timeZone import nowForDb


def run(db: Session, now=None) -> dict:
    """Una pasada: envía los recordatorios vencidos. Devuelve cuántas cuentas se revisaron y cuántas recibieron aviso."""
    if not userNotifications.ready(db):
        return {"revisadas": 0, "avisadas": 0, "motivo": userNotifications.ESQUEMA_PENDIENTE}
    now = now or nowForDb()
    schedules = db.scalars(select(ReminderSchedule).where(ReminderSchedule.modo != userNotifications.MODO_NINGUNO)).all()
    reviewed = notified = 0
    for schedule in schedules:
        reviewed += 1
        user = db.get(User, schedule.idUsuario)
        if user is None or user.estado != userNotifications.ESTADO_ACTIVO:
            continue
        if userNotifications.processReminders(db, user, schedule, now):
            notified += 1
    return {"revisadas": reviewed, "avisadas": notified}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Envía los recordatorios de medición vencidos (página y correo).")
    parser.add_argument("orden", choices=["ejecutar"])
    parser.parse_args(argv)
    with getJobsSessionFactory()() as db:
        print(json.dumps(run(db), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
