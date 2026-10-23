# UnhandledErrors - Errores 500 inesperados: respuesta genérica y evento de auditoría
#
# Starlette responde a una excepción sin manejar con un 500 de texto plano desde su capa más externa, ya sin el contexto de la solicitud ni las
# cabeceras de seguridad, y sin dejar nada en la auditoría (H-15, sección 5 del informe de auditoría de ciberseguridad). Este middleware ASGI va
# en la capa MÁS INTERNA: atrapa lo que ninguna ruta ni manejador resolvió, lo deja en el registro técnico con su traza, registra un evento de
# auditoría y responde un 500 JSON genérico que todavía pasa por CORS, las cabeceras de seguridad y la correlación (X-Request-ID).
#
# El evento guarda solo la clase de la excepción, el método y la ruta: nunca el mensaje de la excepción (puede traer valores de la solicitud,
# SQL o datos personales). Si la respuesta ya empezó (flujos SSE) no se puede reemplazar: se registra y se vuelve a lanzar.
# Middleware ASGI puro (no BaseHTTPMiddleware): no interfiere con los flujos SSE.

import logging

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.db.session import getSessionFactory
from app.services import auditClassification as classification
from app.services.audit import registerEvent

logger = logging.getLogger("glucolume.errors")

CODE = "ERROR_SERVIDOR"
MESSAGE = "El servidor no pudo procesar la solicitud. Intentá de nuevo más tarde."


def sessionFactory():
    """Fábrica de sesiones para persistir (las pruebas la reemplazan por su base). Siempre una sesión propia: la de la solicitud pudo quedar rota."""
    return getSessionFactory()()


def recordUnhandled(error: BaseException, method: str, path: str) -> None:
    """Un evento de auditoría por error inesperado (la IP, el cliente y la correlación salen del contexto de la solicitud). No lanza nunca."""
    try:
        with sessionFactory() as db:
            registerEvent(
                db, "ACCESO", classification.ACCION_ERROR_INESPERADO, False, modulo="SISTEMA", motivo="ERROR_INTERNO",
                observacion=f"{type(error).__name__} en {method} {path}"[:1000],
            )
            db.commit()
    except Exception:  # noqa: BLE001 - registrar el error nunca debe agravarlo
        logger.exception("No se pudo registrar el error inesperado en la auditoría")


class UnhandledErrorMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def trackedSend(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, trackedSend)
        except Exception as error:  # noqa: BLE001 - es justamente lo que nadie más atrapó
            logger.exception("Error no controlado en %s %s", scope.get("method"), scope.get("path"))
            route = scope.get("route")  # plantilla de la ruta (sin identificadores) cuando el enrutador ya la resolvió
            await run_in_threadpool(recordUnhandled, error, scope.get("method", ""), getattr(route, "path", None) or scope.get("path", ""))
            if started:
                raise
            await JSONResponse({"codigo": CODE, "detail": MESSAGE}, status_code=500)(scope, receive, send)
