# LoginThrottle - Límite de intentos fallidos de inicio de sesión por cuenta y origen (auditoría 07/11/2026, M-2)
#
# Qué hace:
#   - Cada contraseña rechazada (cuenta existente, inexistente o sin contraseña local) cuenta para el par (identificador, origen). El origen
#     es la IP real del cliente normalizada (app/api/rateLimit.normalizeIp). Nginx la fija desde el proxy de confianza
#     (docker/nginx/default.conf.template): la cabecera X-Forwarded-For que manda el cliente no se usa.
#   - Dos ventanas deslizantes (de la más corta a la más larga): 5 fallos en 15 min y 15 fallos en 1 h. Superada una, los intentos de ESE
#     par se rechazan con CUENTA_BLOQUEADA y Retry-After. El límite se libera solo cuando vence el fallo más antiguo: nunca es permanente.
#   - Se evalúa ANTES de buscar la cuenta y el contador es el mismo para identificadores existentes e inexistentes: la respuesta no revela
#     si una cuenta existe (sin enumeración) y los intentos bloqueados no consumen Argon2.
#
# Qué NO hace, a propósito:
#   - No bloquea la cuenta para todos los orígenes. Un tercero desde otra IP no puede dejar fuera a la víctima. (El bloqueo global de
#     15 min que existía antes permitía exactamente eso, y renovarlo con tres intentos cada 15 min lo volvía indefinido.)
#   - Trade-off conocido: un atacante con muchas IPs puede probar hasta 15 contraseñas por hora por IP contra una cuenta. Las cuentas con
#     MFA no quedan expuestas por eso. Ver docs/auditorias/CORRECCIONES_AUDITORIA_SEGURIDAD_2026-11-07.md, M-2.
#
# Los contadores usan RateLimiter: en memoria por proceso, o compartidos entre réplicas si está RATE_LIMIT_REDIS_URL (H-06).
# Las claves no se guardan en claro cuando se comparten en Redis (RateLimiter aplica HMAC).

import math
import threading
import zlib
from contextlib import contextmanager

from app.api.rateLimit import normalizeIp
from app.services.rateLimiter import RateLimiter

# (nombre, fallos máximos, ventana en segundos). Orden de la más corta a la más larga.
LIMITES = (
    ("login:fallos:15m", 5, 15 * 60),
    ("login:fallos:1h", 15, 60 * 60),
)
_limitadores = tuple(RateLimiter(maximo, ventana, name=nombre) for nombre, maximo, ventana in LIMITES)


# Serialización de la decisión por par (identificador, origen): comprobar el límite, verificar la contraseña y registrar el fallo ocurren
# juntos. Sin esto, una ráfaga de pedidos simultáneos pasa toda la comprobación antes de que se registre ningún fallo (la verificación con
# Argon2 es lenta, así que la carrera es real). Cerrojos fijos (no uno por clave) para que la memoria no crezca con los identificadores.
_BANDAS = 256
_cerrojos = tuple(threading.Lock() for _ in range(_BANDAS))


@contextmanager
def exclusivo(identificador: str, origen: str):
    indice = zlib.crc32(_clave(identificador, origen).encode("utf-8")) % _BANDAS
    with _cerrojos[indice]:
        yield


def origenDe(clientInfo) -> str:
    """Origen del intento: la IP real del cliente tal como la informa la capa HTTP (ya detrás del proxy de confianza)."""
    return normalizeIp(getattr(clientInfo, "ip", None))


def _clave(identificador: str, origen: str) -> str:
    # El identificador se normaliza como en el correo/usuario (sin mayúsculas ni espacios de los bordes). El origen no contiene «|».
    return f"{identificador.strip().casefold()}|{origen}"


def retryAfter(identificador: str, origen: str, now: float | None = None) -> int | None:
    """Segundos hasta poder volver a intentar (el mayor de los límites alcanzados), o None si el par no está limitado."""
    clave = _clave(identificador, origen)
    esperas = [limitador.retryAfter(clave, now) for limitador in _limitadores]
    limitadas = [espera for espera in esperas if espera > 0]
    return math.ceil(max(limitadas)) if limitadas else None


def registrarFallo(identificador: str, origen: str) -> bool:
    """Cuenta un fallo. Devuelve True si con este fallo el par alcanzó un límite (para avisar al titular)."""
    clave = _clave(identificador, origen)
    for limitador in _limitadores:
        limitador.allow(clave)  # registra el fallo; si el límite ya estaba alcanzado, no suma (el intento ya se rechazó antes)
    return any(limitador.exceeded(clave) for limitador in _limitadores)


def reset() -> None:
    """Vacía los contadores de ESTE proceso (pruebas)."""
    for limitador in _limitadores:
        limitador.clear()
