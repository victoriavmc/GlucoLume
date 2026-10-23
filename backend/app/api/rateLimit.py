# RateLimit - Límite de solicitudes por IP para los endpoints públicos (sin sesión)
#
# Complementa, no reemplaza, los controles por cuenta: el bloqueo por intentos fallidos de contraseña/MFA y el intervalo mínimo
# entre correos de una misma cuenta. Frena a un cliente que prueba muchas cuentas distintas (fuerza bruta distribuida entre
# cuentas, registro masivo, enumeración, correo masivo a terceros).
#
# La IP es request.client.host. Detrás de Nginx, uvicorn la toma de X-Forwarded-For, que Nginx fija con la IP real del cliente
# (docker/nginx/default.conf.template): un cliente no puede elegirla.
#
# Los contadores viven en la memoria de ESTE proceso (RateLimiter de services/contact.py). Con una sola réplica del backend, que es
# la configuración actual, el límite es exacto. Con varias réplicas cada una cuenta por separado (el límite efectivo se multiplica
# por el número de réplicas); para repartirlo hace falta un almacén compartido (Redis), que se agrega solo con autorización.

import ipaddress

from fastapi import Depends, Request

from app.core.exceptions import AuthError
from app.services.contact import RateLimiter

# nombre -> (solicitudes máximas, ventana en segundos) por IP. Holgados para no afectar a una institución que sale con una IP
# compartida (NAT), pero lejos de lo que necesita un ataque automatizado.
LIMITS: dict[str, tuple[int, int]] = {
    "login": (60, 10 * 60),
    "register": (10, 60 * 60),
    "verification": (30, 60 * 60),
    "resend": (5, 15 * 60),
    "passwordForgot": (5, 15 * 60),
    "passwordReset": (10, 15 * 60),
    "mfa": (30, 10 * 60),
    "mfaRecovery": (10, 15 * 60),
    "googleExchange": (30, 10 * 60),
    "activation": (20, 10 * 60),
    "activationCode": (10, 15 * 60),  # activación administrativa con código: muy por debajo de lo que necesitaría adivinar un código de 256 bits
    "accountDeletion": (10, 15 * 60),
    "refresh": (120, 10 * 60),
    "unsubscribe": (20, 10 * 60),
    "resultEmailConfirm": (20, 10 * 60),  # confirmación del correo de resultados por el paciente (enlace del correo)
    "bridgeCheck": (60, 10 * 60),  # instalación del puente: unas pocas consultas por equipo
    # Endpoints con sesión (H-11): ~30 pedidos por segundo desde una misma IP. Muy por encima de lo que hace una institución entera detrás de
    # un NAT (la telemetría va por SSE, una conexión por pantalla) y muy por debajo de lo que necesita extraer datos con un token robado.
    "authenticated": (1800, 60),
}

# Puente serie (GL-11): /bridge/ingest no tiene límite de pedidos válidos (el puente envía cada segundo y, tras un corte, descarga su
# cola sin pausa), pero una IP que falla el token BRIDGE_FAILURES veces en la ventana queda bloqueada aunque después acierte.
BRIDGE_FAILURES = (20, 10 * 60)
bridgeFailures = RateLimiter(*BRIDGE_FAILURES)

TOO_MANY_REQUESTS = "Hiciste demasiadas solicitudes seguidas. Esperá unos minutos e intentá de nuevo."

_limiters = {name: RateLimiter(maximum, window) for name, (maximum, window) in LIMITS.items()}


def clientIp(request: Request) -> str:
    return normalizeIp(request.client.host if request.client else None)


def normalizeIp(host: str | None) -> str:
    """Clave de límite por cliente: IPv4 exacta; IPv6 agrupada por prefijo /64 (una conexión doméstica o un servidor recibe un /64
    entero: contar por dirección exacta permitiría rotar la dirección en cada pedido para esquivar el límite)."""
    if not host:
        return "desconocido"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if address.version == 6:
        if address.ipv4_mapped is not None:  # ::ffff:a.b.c.d es un cliente IPv4
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


def resetLimits() -> None:
    """Vacía los contadores (pruebas)."""
    for limiter in _limiters.values():
        limiter.clear()
    bridgeFailures.clear()


def checkAuthenticated(request: Request) -> None:
    """Límite por IP de los endpoints con sesión: se evalúa antes de resolver la sesión, sobre pedidos que traen credenciales."""
    limiter = _limiters["authenticated"]
    if not limiter.allow(clientIp(request)):
        raise AuthError("DEMASIADAS_SOLICITUDES", TOO_MANY_REQUESTS, retryAfterSeconds=int(limiter.windowSeconds), motivo="authenticated")


def rateLimit(name: str):
    """Dependencia de FastAPI: responde 429 (DEMASIADAS_SOLICITUDES, con Retry-After) al superar el límite de `name` por IP."""
    limiter = _limiters[name]

    def check(request: Request) -> None:
        if not limiter.allow(clientIp(request)):
            raise AuthError("DEMASIADAS_SOLICITUDES", TOO_MANY_REQUESTS, retryAfterSeconds=int(limiter.windowSeconds), motivo=name)

    return Depends(check)
