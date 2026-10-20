# CleanupUnverifiedAccounts - Job de limpieza de cuentas locales no verificadas vencidas
#
# Ejecución manual controlada (desde backend/), sin endpoint HTTP:
#   python -m app.jobs.cleanupUnverifiedAccounts
#
# Preparado para un programador de tareas (cron / Programador de tareas de Windows / job futuro).

import logging

from app.db.session import getJobsSessionFactory
from app.services.unverifiedAccounts import deleteExpiredAccounts

logger = logging.getLogger("glucolume.jobs")


def run() -> int:
    with getJobsSessionFactory()() as db:
        deleted = deleteExpiredAccounts(db)
    logger.info("Cuentas no verificadas eliminadas: %s", deleted)
    return deleted


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"Cuentas no verificadas eliminadas: {run()}")
