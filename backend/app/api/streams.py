# Streams - Control de los flujos SSE de larga duración (/acquisition/stream, /acquisition/telemetry/stream)
#
# Un stream dura minutos u horas. Dos riesgos que esta capa acota:
#   - Recursos: cada suscriptor despierta cada 0,2 s y el hub los recorre bajo un candado. Hay un tope por cuenta y uno global; superado,
#     la apertura responde 429 (DEMASIADAS_SOLICITUDES). El tope es del proceso (como los límites de rateLimit.py).
#   - Autorización vencida: la sesión se valida solo al abrir. Cada STREAM_REVALIDATE_SECONDS se vuelve a comprobar que la sesión siga
#     vigente (no revocada, no vencida, cuenta ACTIVA) con una sesión de base propia y breve; si ya no lo está, el stream termina.
# La conexión de base de la petición se libera antes de empezar a transmitir (deps.getStreamAuthContext).

import threading
import time
import uuid

from starlette.concurrency import run_in_threadpool

from app.core.exceptions import AuthError
from app.db import session as dbSession
from app.services import auth as authService

MAX_STREAMS_PER_USER = 6  # varias pestañas × (adquisición + telemetría)
MAX_STREAMS_TOTAL = 300
STREAM_REVALIDATE_SECONDS = 30
TOO_MANY_STREAMS = "Hay demasiadas conexiones en tiempo real abiertas. Cerrá otras pestañas o esperá unos minutos."


class StreamSlot:
    """Cupo de un stream abierto. `release` es idempotente."""

    def __init__(self, registry: "StreamRegistry", userId: uuid.UUID):
        self._registry, self._userId, self._released = registry, userId, False

    def release(self) -> None:
        if not self._released:
            self._released = True
            self._registry._release(self._userId)


class StreamRegistry:
    def __init__(self, perUser: int = MAX_STREAMS_PER_USER, total: int = MAX_STREAMS_TOTAL):
        self.perUser, self.total = perUser, total
        self._counts: dict[uuid.UUID, int] = {}
        self._lock = threading.Lock()

    def acquire(self, userId: uuid.UUID) -> StreamSlot:
        with self._lock:
            if self._counts.get(userId, 0) >= self.perUser or sum(self._counts.values()) >= self.total:
                raise AuthError("DEMASIADAS_SOLICITUDES", TOO_MANY_STREAMS, retryAfterSeconds=30)
            self._counts[userId] = self._counts.get(userId, 0) + 1
        return StreamSlot(self, userId)

    def _release(self, userId: uuid.UUID) -> None:
        with self._lock:
            remaining = self._counts.get(userId, 0) - 1
            if remaining > 0:
                self._counts[userId] = remaining
            else:
                self._counts.pop(userId, None)

    def active(self) -> int:
        with self._lock:
            return sum(self._counts.values())


registry = StreamRegistry()


def openStreamSlot(userId: uuid.UUID) -> StreamSlot:
    return registry.acquire(userId)


def _sessionStillValid(userId: uuid.UUID, sessionId: uuid.UUID) -> bool:
    db = dbSession.getSessionFactory()()
    try:
        authService.resolveAccessSession(db, {"sub": str(userId), "sid": str(sessionId)})
        return True
    except AuthError:
        return False
    finally:
        db.close()


async def sessionStillValid(userId: uuid.UUID, sessionId: uuid.UUID) -> bool:
    return await run_in_threadpool(_sessionStillValid, userId, sessionId)


class Revalidator:
    """Decide cuándo volver a comprobar la sesión de un stream (una vez cada STREAM_REVALIDATE_SECONDS)."""

    def __init__(self, userId: uuid.UUID, sessionId: uuid.UUID):
        self.userId, self.sessionId, self._last = userId, sessionId, time.monotonic()

    async def stillAuthorized(self) -> bool:
        if time.monotonic() - self._last < STREAM_REVALIDATE_SECONDS:
            return True
        self._last = time.monotonic()
        return await sessionStillValid(self.userId, self.sessionId)
