# Tarea periódica del backend (arranca con la aplicación, también tras reiniciar los contenedores).
#
# Corre una pasada de measurementLifecycle.sweep() cada MAINTENANCE_INTERVAL_SECONDS (por defecto 60 s; 0 la desactiva) en un hilo aparte, para no
# bloquear las peticiones. No depende de que un usuario tenga la página abierta. Con varias réplicas es seguro: las transiciones son
# UPDATE condicionales y una medición ya invalidada no se vuelve a procesar.

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from app.core.config import getSettings
from app.db.session import getSessionFactory
from app.services import measurementLifecycle

logger = logging.getLogger("glucolume.maintenance")
FIRST_RUN_DELAY_SECONDS = 15


def runOnce() -> dict | None:
    """Una pasada con su propia sesión de base. Nunca propaga errores (se registran y se reintenta en la próxima)."""
    try:
        with getSessionFactory()() as db:
            result = measurementLifecycle.sweep(db)
        if result["invalidadas"] or result["purgadas"]:
            logger.info("Mantenimiento de mediciones: %s", result)
        return result
    except Exception:  # noqa: BLE001
        logger.exception("Falló una pasada de mantenimiento de mediciones")
        return None


async def _loop(interval: float) -> None:
    await asyncio.sleep(min(FIRST_RUN_DELAY_SECONDS, interval))
    while True:
        await run_in_threadpool(runOnce)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    interval = getSettings().MAINTENANCE_INTERVAL_SECONDS
    task = asyncio.create_task(_loop(interval)) if interval > 0 else None
    if task is not None:
        logger.info("Mantenimiento de mediciones activo (cada %s s).", interval)
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
