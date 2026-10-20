# PurgeInstitutionalRetention - Job de fin del período de conservación de pacientes institucionales
#
# Desidentifica los pacientes cuyo período de conservación de 12 meses (cierre de la institución o baja del
# paciente) ya venció. Ver app/services/institutionalRetention.py.
#
# Ejecución manual controlada (desde backend/), sin endpoint HTTP. BORRA y desidentifica datos: exige nombrar la base a propósito, para que
# no corra por error contra la base real (hacerlo sobre datos reales requiere autorización expresa):
#   python -m app.jobs.purgeInstitutionalRetention --confirmo-base <DB_NAME configurado>
#
# Preparado para un programador de tareas (cron / Programador de tareas de Windows), por ejemplo una vez por día, con el mismo argumento.
# Usa la cuenta de base de los procesos de conservación (DB_JOBS_USER) si está configurada.

import argparse
import logging
import sys

from app.core.config import getSettings
from app.db.session import getJobsSessionFactory
from app.services import resultEmailStore
from app.services.institutionalRetention import purgeExpiredPatientData
from app.services.measurementRetention import purgeExpiredMeasurements
from app.utils.timeZone import nowForDb

logger = logging.getLogger("glucolume.jobs")


def run() -> int:
    with getJobsSessionFactory()() as db:
        # Primero se borran las mediciones vencidas (12 meses desde la última), después se anonimiza (que sella el vencimiento de las
        # restantes) y por último se borran las que ya nacieron vencidas.
        deleted = purgeExpiredMeasurements(db)
        purged = purgeExpiredPatientData(db)
        deleted += purgeExpiredMeasurements(db)
        emails = resultEmailStore.purgeExpired(db, nowForDb())
    logger.info("Mediciones eliminadas por fin de conservación (12 meses desde la última): %s", deleted)
    logger.info("Correos de pacientes borrados por vencimiento o baja: %s", emails)
    logger.info("Perfiles de pacientes desidentificados por fin de conservación: %s", purged)
    return purged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fin del período de conservación de pacientes institucionales (borra y desidentifica).")
    parser.add_argument("--confirmo-base", default=None, help="Nombre exacto de la base configurada (DB_NAME) sobre la que se autoriza correr.")
    args = parser.parse_args(argv)
    if args.confirmo_base != getSettings().DB_NAME:
        print("No se modificó nada: --confirmo-base debe ser el nombre exacto de la base configurada.", file=sys.stderr)
        return 2
    logging.basicConfig(level=logging.INFO)
    print(f"Perfiles de pacientes desidentificados por fin de conservación: {run()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
