# Readiness - ¿el backend puede atender solicitudes ahora? (B-6, auditoría 07/11/2026)
#
# Liveness (/healthz) y readiness (/readyz) miden cosas distintas:
#   - liveness: el proceso responde. No toca la base: si SQL Server cae, el contenedor no se reinicia en bucle.
#   - readiness: además, la base responde y la tabla de sesiones existe (sin ella no hay inicio de sesión). Si falla, el backend sigue
#     vivo, pero no conviene enrutarle tráfico.
#
# Costo: la comprobación es un SELECT 1 y un SELECT TOP 1 sobre SesionUsuario. Se cachea CACHE_SECONDS, así los sondeos frecuentes
# (healthchecks, monitoreo) no generan una consulta por sondeo. Solo corre una comprobación a la vez: si la anterior no terminó
# (base colgada), las demás reciben TIEMPO_AGOTADO sin lanzar otro hilo. Va por el mismo semáforo de DB_MAX_CONCURRENT_CALLS que el
# resto de la API, con tope de tiempo: un readiness nunca espera más que PROBE_TIMEOUT_SECONDS.
#
# Seguridad: el resultado son solo valores enumerados. No incluye versiones, nombres de servidor, cadenas de conexión ni mensajes de
# excepción (esos van al log del servidor, no a la respuesta).

import logging
import threading
import time

from sqlalchemy import select, text

from app.db.session import getSessionFactory
from app.models.userSession import UserSession

logger = logging.getLogger("glucolume.readiness")

OK = "ok"
NO_DISPONIBLE = "no_disponible"
NO_VERIFICADO = "no_verificado"  # la tabla no se comprobó porque la base no respondió
TIEMPO_AGOTADO = "tiempo_agotado"

PROBE_TIMEOUT_SECONDS = 3.0
CACHE_SECONDS = 5.0
RETRY_AFTER_SECONDS = 5

def newSession():
    """Una sesión nueva de la base de la API (la misma que usan los endpoints). Inyectable en pruebas."""
    return getSessionFactory()()

_lock = threading.Lock()
_cached: tuple[float, dict[str, str]] | None = None  # (momento monotónico, dependencias)
_probing = False


def _resultado(dependencias: dict[str, str]) -> dict:
    listo = all(valor == OK for valor in dependencias.values())
    return {"listo": listo, "dependencias": dependencias}


def _probe() -> dict[str, str]:
    """Una comprobación real. Nunca lanza: cualquier fallo queda como valor enumerado y se registra en el log."""
    dependencias = {"baseDeDatos": NO_DISPONIBLE, "tablaSesiones": NO_VERIFICADO}
    try:
        session = newSession()
    except Exception as error:  # noqa: BLE001 - la respuesta no revela nada: solo el log
        logger.warning("Readiness: no se pudo crear la sesión de base (%s)", type(error).__name__)
        return dependencias
    try:
        session.execute(text("SELECT 1"))
        dependencias["baseDeDatos"] = OK
        session.execute(select(UserSession.idSesion).limit(1)).first()
        dependencias["tablaSesiones"] = OK
    except Exception as error:  # noqa: BLE001
        logger.warning("Readiness: falla de dependencia (%s)", type(error).__name__)
        if dependencias["baseDeDatos"] == OK:
            dependencias["tablaSesiones"] = NO_DISPONIBLE
    finally:
        session.close()  # devuelve la conexión al pool: no queda ocupada entre sondeos
    return dependencias


def _worker() -> None:
    global _cached, _probing
    try:
        dependencias = _probe()
    except Exception:  # noqa: BLE001 - _probe ya no lanza; esto es una red de seguridad
        logger.exception("Readiness: error inesperado en la comprobación")
        dependencias = {"baseDeDatos": NO_DISPONIBLE, "tablaSesiones": NO_VERIFICADO}
    with _lock:
        _cached = (time.monotonic(), dependencias)
        _probing = False


def snapshot() -> dict:
    """Estado de readiness: usa el resultado cacheado si es reciente; si no, comprueba con tope de tiempo."""
    global _probing
    ahora = time.monotonic()
    with _lock:
        if _cached is not None and ahora - _cached[0] < CACHE_SECONDS:
            return _resultado(_cached[1])
        if _probing:
            # Hay una comprobación que no terminó (la base está lenta o colgada): no se lanza otra.
            return _resultado({"baseDeDatos": TIEMPO_AGOTADO, "tablaSesiones": NO_VERIFICADO})
        _probing = True
    hilo = threading.Thread(target=_worker, name="readiness-probe", daemon=True)
    hilo.start()
    hilo.join(PROBE_TIMEOUT_SECONDS)
    with _lock:
        if _cached is not None and _cached[0] >= ahora:
            return _resultado(_cached[1])
        return _resultado({"baseDeDatos": TIEMPO_AGOTADO, "tablaSesiones": NO_VERIFICADO})


def reset() -> None:
    """Olvida el resultado cacheado (pruebas)."""
    global _cached
    with _lock:
        _cached = None
