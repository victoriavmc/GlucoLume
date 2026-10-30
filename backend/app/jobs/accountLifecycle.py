# AccountLifecycle - Job del ciclo de vida de las cuentas institucionales
#
#   1. Elimina y anonimiza las cuentas institucionales cuyo período de gracia de 30 días venció (services/accountLifecycle.py).
#   2. Depura las cuentas invitadas que nunca se activaron y ya no tienen invitación ni enlace vigentes (services/pendingAccounts.py).
#   3. Minimiza los datos personales históricos de las relaciones cuyo plazo de conservación venció (services/personnelRetention.py).
#   4. Aplica la política de conservación de la auditoría: IP y cliente de eventos viejos, intentos sin cuenta y, si se configuró, todo evento
#      vencido (services/auditRetention.py).
#
# Corre en el servicio «lifecycle» de Docker Compose (UN solo proceso programador, aparte de la API: las réplicas de FastAPI no lo
# ejecutan, así que no se duplica). Aun así es seguro ante ejecuciones simultáneas: cada cuenta se revalida con su fila bloqueada.
#
# Desde backend/:
#   python -m app.jobs.accountLifecycle           # una pasada y termina (manual, o un programador externo)
#   python -m app.jobs.accountLifecycle --loop    # pasadas cada ACCOUNT_LIFECYCLE_INTERVAL_SECONDS (por defecto 3600), sin terminar
#   python -m app.jobs.accountLifecycle --health  # healthcheck del contenedor (0 = sano)
#   python -m app.jobs.accountLifecycle --dry-run # informa plazos vigentes/vencidos y qué procesaría AHORA, sin modificar nada
#   python -m app.jobs.accountLifecycle --regularize                       # muestra el cambio exacto para las cuentas anteriores a la política
#   python -m app.jobs.accountLifecycle --regularize --apply --solo <idUsuario> --confirmo-actualizar-cuentas-reales   # lo aplica a UNA cuenta (requiere autorización)

import json
import logging
import sys
import tempfile
import uuid
import time
from pathlib import Path

from app.core.config import getSettings
from app.db.session import getJobsSessionFactory
from app.services import accountLifecycle, auditRetention, pendingAccounts, personnelRetention

logger = logging.getLogger("glucolume.lifecycle")
HEARTBEAT = Path(tempfile.gettempdir()) / "glucolume-lifecycle.heartbeat"
HEALTH_MARGIN_SECONDS = 600


def run() -> dict:
    """Una pasada completa. Cada parte tiene su sesión y su manejo de errores: una no frena a la otra."""
    settings = getSettings()
    result: dict = {}
    try:
        with getJobsSessionFactory()() as db:
            result["cuentas"] = accountLifecycle.sweep(db)
    except Exception:  # noqa: BLE001
        logger.exception("Falló la pasada de eliminación automática de cuentas")
        result["cuentas"] = None
    try:
        with getJobsSessionFactory()() as db:
            result["pendientesDepuradas"] = pendingAccounts.purgeDead(db)
    except Exception:  # noqa: BLE001
        logger.exception("Falló la depuración de cuentas invitadas vencidas")
        result["pendientesDepuradas"] = None
    try:
        with getJobsSessionFactory()() as db:
            result["relacionesMinimizadas"] = personnelRetention.minimizeExpired(db, settings.PERSONNEL_RETENTION_MONTHS, guarded=True)
    except Exception:  # noqa: BLE001
        logger.exception("Falló la minimización de datos históricos del personal")
        result["relacionesMinimizadas"] = None
    try:
        with getJobsSessionFactory()() as db:
            result["auditoria"] = auditRetention.run(db)
    except Exception:  # noqa: BLE001
        logger.exception("Falló la aplicación de la política de conservación de la auditoría")
        result["auditoria"] = None
    logger.info("Ciclo de vida de cuentas: %s", result)
    return result


def beat() -> None:
    """Marca de vida para el healthcheck del contenedor (la pasada terminó, con o sin novedades)."""
    try:
        HEARTBEAT.touch()
    except OSError:
        logger.warning("No se pudo escribir la marca de vida del ciclo de vida de cuentas.")


def healthy() -> bool:
    """El proceso está vivo si completó una pasada hace menos de dos intervalos (más un margen). Desactivado = siempre sano."""
    interval = getSettings().ACCOUNT_LIFECYCLE_INTERVAL_SECONDS
    if interval <= 0:
        return True
    try:
        return time.time() - HEARTBEAT.stat().st_mtime < 2 * interval + HEALTH_MARGIN_SECONDS
    except OSError:
        return False


def loop() -> None:
    interval = getSettings().ACCOUNT_LIFECYCLE_INTERVAL_SECONDS
    if interval <= 0:
        logger.warning("ACCOUNT_LIFECYCLE_INTERVAL_SECONDS=%s: el ciclo de vida automático está desactivado.", interval)
        while True:  # el contenedor se mantiene sano y sin actividad (restart: unless-stopped no lo reinicia en bucle)
            time.sleep(3600)
    logger.info("Ciclo de vida de cuentas activo (cada %s s).", interval)
    beat()  # arranca sano; si una pasada tarda demasiado el healthcheck lo advierte
    while True:
        run()
        beat()
        time.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if "--dry-run" in sys.argv[1:]:
        with getJobsSessionFactory()() as session:
            print(json.dumps(accountLifecycle.dryRun(session), indent=2, ensure_ascii=False))
        sys.exit(0)
    if "--regularize" in sys.argv[1:]:
        applying = "--apply" in sys.argv[1:]
        if applying and "--confirmo-actualizar-cuentas-reales" not in sys.argv[1:]:
            sys.exit("Para aplicar se necesita --confirmo-actualizar-cuentas-reales (modifica cuentas reales).")
        only = None
        if "--solo" in sys.argv[1:]:
            only = uuid.UUID(sys.argv[sys.argv.index("--solo") + 1])
        if applying and only is None:
            sys.exit("Para aplicar se necesita --solo <idUsuario>: la autorización es por cuenta.")
        with getJobsSessionFactory()() as session:
            print(json.dumps(accountLifecycle.regularize(session, apply=applying, only=only), indent=2, ensure_ascii=False))
        sys.exit(0)
    if "--health" in sys.argv[1:]:
        sys.exit(0 if healthy() else 1)
    if "--loop" in sys.argv[1:]:
        loop()
    else:
        print(run())
