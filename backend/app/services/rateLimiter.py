# RateLimiter - Ventana deslizante por clave, en memoria o compartida entre réplicas (H-06)
#
# Por defecto los contadores viven en la memoria de ESTE proceso: exactos con una réplica, que es la configuración actual y la única que exige
# el hub de telemetría. Si RATE_LIMIT_REDIS_URL está configurada, los limitadores que tienen `name` cuentan en Redis, de modo que varias réplicas
# comparten la cuota en lugar de multiplicarla. Sin esa variable (desarrollo, una réplica) no se necesita Redis ni se importa su cliente.
#
# Diseño del modo compartido:
#   - Ventana deslizante en un conjunto ordenado por clave: se agrega el evento, se cuenta y, si excede, se retira (los intentos rechazados no
#     alargan el bloqueo, igual que en memoria). Un solo viaje por pedido (MULTI/EXEC). Con pedidos simultáneos puede rechazar de más por un
#     instante, nunca permitir de más.
#   - La clave en Redis es un HMAC de la clave lógica (IP, usuario, correo): Redis no guarda direcciones ni correos en claro.
#   - Los eventos llevan la hora del proceso que los registra: las réplicas deben tener la hora sincronizada (NTP).
#   - Falla de Redis (RATE_LIMIT_ON_FAILURE): "local" (por defecto) cuenta en memoria mientras dure la falla — nunca más débil que sin Redis;
#     "deny" rechaza todo lo que pasa por un limitador (más seguro contra abuso, pero una caída de Redis deja sin acceso a los endpoints
#     protegidos, incluido el inicio de sesión). Tras una falla se deja de consultar Redis RATE_LIMIT_REDIS_RETRY_SECONDS (evita demorar cada pedido).
#   - Un limitador SIN `name` nunca es compartido. Dos limitadores con el mismo `name` y distintos parámetros son un error de programación.

import hashlib
import hmac
import logging
import secrets
import threading
import time
from collections import deque

from app.core.config import getSettings

logger = logging.getLogger(__name__)

_registry: dict[str, tuple[int, float]] = {}
_registryLock = threading.Lock()


class _SharedBackend:
    """Cliente de Redis con un corte de circuito simple. `hit`/`count` devuelven None cuando Redis no respondió."""

    def __init__(self, url: str, timeout: float, retrySeconds: float) -> None:
        import redis  # importación diferida: sin RATE_LIMIT_REDIS_URL el cliente no se usa

        self._client = redis.Redis.from_url(url, socket_timeout=timeout, socket_connect_timeout=timeout, decode_responses=False)
        self._retry = retrySeconds
        self._openUntil = 0.0
        self._lock = threading.Lock()

    def _digest(self, key: str) -> str:
        from app.core.security import derivedKey

        return hmac.new(derivedKey("limite-solicitudes"), key.encode("utf-8"), hashlib.sha256).hexdigest()[:32]

    def _redisKey(self, name: str, key: str) -> str:
        return f"glucolume:rl:{name}:{self._digest(key)}"

    def _usable(self) -> bool:
        return time.monotonic() >= self._openUntil

    def _fail(self, error: Exception) -> None:
        with self._lock:
            first = time.monotonic() >= self._openUntil
            self._openUntil = time.monotonic() + self._retry
        if first:
            logger.warning("Redis de límites de solicitudes no responde (%s): se reintenta en %.0f s.", type(error).__name__, self._retry)

    def hit(self, name: str, key: str, limit: int, window: float) -> bool | None:
        if not self._usable():
            return None
        redisKey, now = self._redisKey(name, key), time.time()
        member = f"{now:.6f}:{secrets.token_hex(4)}"
        try:
            pipe = self._client.pipeline(transaction=True)
            pipe.zremrangebyscore(redisKey, 0, now - window)
            pipe.zadd(redisKey, {member: now})
            pipe.zcard(redisKey)
            pipe.pexpire(redisKey, int(window * 1000) + 1000)
            count = pipe.execute()[2]
            if count > limit:
                self._client.zrem(redisKey, member)
                return False
            return True
        except Exception as error:  # noqa: BLE001 - cualquier falla del almacén aplica la política de falla
            self._fail(error)
            return None

    def exceeded(self, name: str, key: str, limit: int, window: float) -> bool | None:
        if not self._usable():
            return None
        redisKey, now = self._redisKey(name, key), time.time()
        try:
            pipe = self._client.pipeline(transaction=True)
            pipe.zremrangebyscore(redisKey, 0, now - window)
            pipe.zcard(redisKey)
            return pipe.execute()[1] >= limit
        except Exception as error:  # noqa: BLE001
            self._fail(error)
            return None


_backend: _SharedBackend | None = None
_backendConfig: tuple | None = None
_backendLock = threading.Lock()


def sharedBackend() -> tuple[_SharedBackend | None, str]:
    """(almacén compartido o None, política ante falla). Se reconstruye si cambió la configuración (pruebas, recarga)."""
    global _backend, _backendConfig
    settings = getSettings()
    url = settings.RATE_LIMIT_REDIS_URL.get_secret_value() if settings.RATE_LIMIT_REDIS_URL is not None else None
    config = (url, settings.RATE_LIMIT_REDIS_TIMEOUT_SECONDS, settings.RATE_LIMIT_REDIS_RETRY_SECONDS)
    if config != _backendConfig:
        with _backendLock:
            if config != _backendConfig:
                _backend = _SharedBackend(url, config[1], config[2]) if url else None
                _backendConfig = config
    return _backend, settings.RATE_LIMIT_ON_FAILURE


class RateLimiter:
    """Ventana deslizante por clave. En memoria, o compartida si tiene `name` y hay RATE_LIMIT_REDIS_URL."""

    def __init__(self, maxEvents: int, windowSeconds: float, name: str | None = None):
        self.maxEvents = maxEvents
        self.windowSeconds = windowSeconds
        self.name = name
        if name is not None:
            with _registryLock:
                known = _registry.setdefault(name, (maxEvents, windowSeconds))
            if known != (maxEvents, windowSeconds):
                raise ValueError(f"Hay dos limitadores llamados «{name}» con parámetros distintos.")
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._lastPurge = float("-inf")

    # Memoria acotada: a partir de PURGE_THRESHOLD claves se descartan las vencidas, a lo sumo una vez cada PURGE_INTERVAL_SECONDS (no
    # en cada llamada: con muchas claves vigentes recorrerlas todas bajo el candado por pedido saturaría el proceso). Con MAX_KEYS claves
    # vigentes, las claves NUEVAS comparten un único cubo de desborde (límite conjunto) en lugar de crecer sin tope.
    PURGE_THRESHOLD = 5000
    PURGE_INTERVAL_SECONDS = 30.0
    MAX_KEYS = 50_000
    OVERFLOW_KEY = "__desborde__"

    def allow(self, key: str, now: float | None = None) -> bool:
        if self.name is not None and now is None:
            backend, onFailure = sharedBackend()
            if backend is not None:
                outcome = backend.hit(self.name, key, self.maxEvents, self.windowSeconds)
                if outcome is not None:
                    return outcome
                if onFailure == "deny":
                    return False
        return self._allowLocal(key, now)

    def exceeded(self, key: str, now: float | None = None) -> bool:
        """Si `key` ya alcanzó el máximo en la ventana, sin registrar un evento nuevo."""
        if self.name is not None and now is None:
            backend, onFailure = sharedBackend()
            if backend is not None:
                outcome = backend.exceeded(self.name, key, self.maxEvents, self.windowSeconds)
                if outcome is not None:
                    return outcome
                if onFailure == "deny":
                    return True
        return self._exceededLocal(key, now)

    def _allowLocal(self, key: str, now: float | None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            if len(self._events) > self.PURGE_THRESHOLD and now - self._lastPurge >= self.PURGE_INTERVAL_SECONDS:
                self._purge(now)
            if key not in self._events and len(self._events) >= self.MAX_KEYS:
                key = self.OVERFLOW_KEY
            events = self._events.setdefault(key, deque())
            while events and now - events[0] >= self.windowSeconds:
                events.popleft()
            if len(events) >= self.maxEvents:
                return False
            events.append(now)
            return True

    def _exceededLocal(self, key: str, now: float | None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            events = self._events.get(key)
            return bool(events) and sum(1 for moment in events if now - moment < self.windowSeconds) >= self.maxEvents

    def _purge(self, now: float) -> None:
        self._lastPurge = now
        for key in [k for k, events in self._events.items() if not events or now - events[-1] >= self.windowSeconds]:
            del self._events[key]

    def clear(self) -> None:
        """Vacía los contadores de ESTE proceso (pruebas); no toca Redis."""
        with self._lock:
            self._events.clear()
