# RequestContext - Contexto de la solicitud HTTP en curso (correlación, origen y cliente)
#
# El middleware (app/api/requestContext.py) lo fija al empezar cada solicitud y registerEvent (services/audit.py) lo lee para completar
# solo los datos de contexto de cada evento de auditoría: identificador de correlación, IP de origen y cliente acotado. Así los más de
# cien puntos que auditan no tienen que repetirlo ni pueden olvidarlo. Fuera de una solicitud (jobs, scripts, pruebas de servicio) no hay
# contexto y esos campos quedan vacíos: nunca se inventan.
#
# Se usa contextvars: el contexto se copia a los hilos del pool de FastAPI (endpoints síncronos) sin compartirse entre solicitudes.

import re
import uuid
from contextvars import ContextVar
from dataclasses import dataclass

from app.utils.userAgent import describeClient

# Identificador de correlación aceptado desde afuera (p. ej. el que fija Nginx con $request_id): corto y sin caracteres de control. Un
# valor que no lo cumple se descarta y se genera uno propio: el cliente no puede inyectar texto arbitrario en los registros.
_SAFE_CORRELATION = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
MAX_AGENT_LENGTH = 100


@dataclass(frozen=True)
class RequestContext:
    correlationId: str
    ip: str | None = None
    agent: str | None = None


_current: ContextVar[RequestContext | None] = ContextVar("glucolume_request_context", default=None)


def newCorrelationId() -> str:
    return uuid.uuid4().hex


def acceptCorrelationId(candidate: str | None) -> str:
    """El identificador que envió el proxy si es seguro; si no, uno nuevo."""
    if candidate and _SAFE_CORRELATION.match(candidate):
        return candidate
    return newCorrelationId()


def describeAgent(userAgent: str | None) -> str | None:
    """Cliente acotado para la auditoría. Un navegador reconocido se resume («Chrome · Windows · Computadora»); un cliente que no lo es
    (curl, scripts, escáneres) conserva su identificación, truncada y sin caracteres de control, porque justamente eso es lo que sirve
    para distinguir un navegador real de una herramienta automática. Nunca se guarda más que eso."""
    if not userAgent:
        return None
    info = describeClient(userAgent)
    if info.navegador:
        parts = [part for part in (info.navegador, info.sistemaOperativo, info.dispositivo) if part]
        return " · ".join(parts)[:MAX_AGENT_LENGTH]
    cleaned = "".join(char for char in userAgent if char.isprintable()).strip()
    return cleaned[:MAX_AGENT_LENGTH] or None


def bind(context: RequestContext):
    """Fija el contexto de la solicitud actual; devuelve el token para restaurar el anterior."""
    return _current.set(context)


def unbind(token) -> None:
    _current.reset(token)


def current() -> RequestContext | None:
    return _current.get()


def correlationId() -> str | None:
    context = _current.get()
    return context.correlationId if context else None
