# RequestContextMiddleware - Correlación y origen de cada solicitud, y observación de los rechazos
#
# 1. Fija el contexto de la solicitud (core/requestContext.py): identificador de correlación, IP de origen y cliente acotado. Los eventos de
#    auditoría que se registren durante la solicitud los guardan (services/audit.py). El identificador viaja de vuelta en la cabecera
#    X-Request-ID: con él, una persona que reporta un error y la auditoría hablan del mismo pedido.
#    Detrás de Nginx el identificador es el $request_id que fija el proxy; un valor enviado por el cliente se acepta solo si tiene un formato
#    seguro (el contenido nunca es de confianza) y sin proxy se genera uno.
# 2. Al terminar, entrega al monitor de seguridad (services/securityMonitor.py) las respuestas rechazadas para detectar ráfagas.
# Middleware ASGI puro (no BaseHTTPMiddleware): no interfiere con los flujos SSE.
#
# La IP es la que informa el servidor ASGI (request.client): detrás de Nginx, uvicorn la toma de X-Forwarded-For, que Nginx sobrescribe con
# la IP real (docker/nginx/default.conf.template). Un cliente no puede elegirla.

import ipaddress

from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core import requestContext
from app.services import securityMonitor


def storedIp(host: str | None) -> str | None:
    """IP en su forma canónica (IPv4 exacta; un IPv4 mapeado en IPv6 se guarda como IPv4). Algo que no es una IP no se guarda."""
    if not host:
        return None
    try:
        address = ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return None
    if address.version == 6 and address.ipv4_mapped is not None:
        return str(address.ipv4_mapped)
    return str(address)


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        client = scope.get("client")
        context = requestContext.RequestContext(
            correlationId=requestContext.acceptCorrelationId(headers.get("x-request-id")),
            ip=storedIp(client[0] if client else None),
            agent=requestContext.describeAgent(headers.get("user-agent")),
        )
        token = requestContext.bind(context)
        status = 0

        async def sendWithCorrelation(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = context.correlationId
            await send(message)

        try:
            await self.app(scope, receive, sendWithCorrelation)
        finally:
            try:
                if status in (400, 401, 403, 422, 429) and scope.get("path", "").startswith("/api/"):
                    rejection = scope.get("state", {}).get("rejection") if isinstance(scope.get("state"), dict) else None
                    await run_in_threadpool(securityMonitor.record, status, rejection, context.ip)
            finally:
                requestContext.unbind(token)
