# SecurityHeaders - Cabeceras de seguridad de las respuestas de la API
#
# Segunda barrera: Nginx (docker/nginx/default.conf.template) ya agrega sus cabeceras delante, pero la API también se alcanza sin
# Nginx (desarrollo, otro proxy, red interna). Es un middleware ASGI puro (no BaseHTTPMiddleware) para no interferir con los flujos
# SSE (/acquisition/stream, /acquisition/telemetry/stream).
#
#   - X-Content-Type-Options: nosniff en todo.
#   - En /api/: Cache-Control no-store (las respuestas llevan datos personales y de salud: no deben quedar en cachés del navegador ni
#     de proxies), Referrer-Policy no-referrer y una CSP que no permite cargar nada (la API solo devuelve JSON/SSE).
#   - HSTS solo en producción y solo si el pedido llegó por HTTPS (esquema que informa el proxy de confianza): nunca sobre HTTP ni en
#     localhost, para no romper el entorno local.
# Los encabezados que ya puso la ruta (p. ej. Cache-Control: no-cache del SSE) se respetan.

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HSTS_VALUE = "max-age=31536000; includeSubDomains"
API_CSP = "default-src 'none'; frame-ancestors 'none'"


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, hsts: bool = False) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        isApi = scope.get("path", "").startswith("/api/")
        secure = scope.get("scheme") == "https"

        async def sendWithHeaders(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                if isApi:
                    headers.setdefault("Cache-Control", "no-store")
                    headers.setdefault("Referrer-Policy", "no-referrer")
                    headers.setdefault("Content-Security-Policy", API_CSP)
                if self.hsts and secure:
                    headers.setdefault("Strict-Transport-Security", HSTS_VALUE)
            await send(message)

        await self.app(scope, receive, sendWithHeaders)
