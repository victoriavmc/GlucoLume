# PurgeInstitutionalRetention - Job de fin del período de conservación de pacientes institucionales
#
# Desidentifica los pacientes cuyo período de conservación de 12 meses (cierre de la institución o baja del
# paciente) ya venció. Ver app/services/institutionalRetention.py.
#
# Ejecución manual controlada (desde backend/), sin endpoint HTTP, en DOS pasos. BORRA y desidentifica datos de forma irreversible; no se programa
# solo y nunca corre contra la base real sin que alguien lo autorice expresamente:
#   1. Simulación (no modifica nada ni requiere confirmar):
#        python -m app.jobs.purgeInstitutionalRetention --simular
#      informa cuántos perfiles se anonimizarían y cuántas mediciones se eliminarían.
#   2. Ejecución, nombrando la base y confirmando EXACTAMENTE esas cantidades (si cambiaron desde la simulación, no se hace nada):
#        python -m app.jobs.purgeInstitutionalRetention --confirmo-base <DB_NAME> --confirmo-perfiles <A> --confirmo-mediciones <B>
#
# Usa la cuenta de base de los procesos de conservación (DB_JOBS_USER) si está configurada.

import argparse
import json
import logging
import sys

from app.core.config import getSettings
from app.db.session import getJobsSessionFactory
from app.services import resultEmailStore
from app.services.institutionalRetention import plan, purgeExpiredPatientData
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
    parser.add_argument("--simular", action="store_true", help="Solo informa qué haría; no modifica nada.")
    parser.add_argument("--confirmo-base", default=None, help="Nombre exacto de la base configurada (DB_NAME) sobre la que se autoriza correr.")
    parser.add_argument("--confirmo-perfiles", type=int, default=None, help="Perfiles a anonimizar, tal como los informó --simular.")
    parser.add_argument("--confirmo-mediciones", type=int, default=None, help="Mediciones a eliminar, tal como las informó --simular.")
    args = parser.parse_args(argv)
    if not args.simular and args.confirmo_base != getSettings().DB_NAME:
        print("No se modificó nada: --confirmo-base debe ser el nombre exacto de la base configurada.", file=sys.stderr)
        return 2  # antes de abrir ninguna sesión de base
    with getJobsSessionFactory()() as db:
        planned = plan(db)
    if args.simular:
        print(json.dumps({"simulacion": True, **planned}, indent=2, ensure_ascii=False))
        return 0
    if (args.confirmo_perfiles, args.confirmo_mediciones) != (planned["perfilesAAnonimizar"], planned["medicionesAEliminar"]):
        print("No se modificó nada: --confirmo-perfiles y --confirmo-mediciones deben coincidir con las cantidades actuales "
              f"({planned['perfilesAAnonimizar']} perfiles, {planned['medicionesAEliminar']} mediciones). Corré --simular y revisá.", file=sys.stderr)
        return 2
    logging.basicConfig(level=logging.INFO)
    print(f"Perfiles de pacientes desidentificados por fin de conservación: {run()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
