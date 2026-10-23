# SessionCookie - Refresh token en una cookie HttpOnly (H-09)
#
# El refresh token dura días: en localStorage/sessionStorage cualquier XSS lo lee y lo lleva afuera. En una cookie HttpOnly el JavaScript de la
# página no puede leerlo; solo el navegador lo manda, y únicamente a /api/v1/auth. El access token (30 min) sigue en memoria.
#
# Modo cookie (lo usa el frontend): el cliente manda la cabecera X-GlucoLume-CSRF: 1 y la respuesta NO lleva el refresh token en el cuerpo.
# Defensas contra CSRF (cualquiera de las tres alcanza; están las tres):
#   1. SameSite=Strict: el navegador no manda la cookie desde otro sitio.
#   2. Cabecera personalizada obligatoria: un formulario o <img> de otro sitio no la puede poner, y fetch() cross-origin la somete a preflight CORS,
#      que solo aprueba el origen del frontend.
#   3. Si el navegador manda Origin, tiene que ser uno de los orígenes de GlucoLume.
# Modo heredado (sin la cabecera: puentes, scripts, pruebas): el refresh token viaja en el cuerpo como siempre. Nunca se usa la cookie sin
# la cabecera. REFRESH_TOKEN_IN_BODY=false lo apaga (cada sesión pasa a exigir cookie).
#
# El valor de la cookie lleva un prefijo: «p.» (recordarme: cookie persistente, vence con la sesión) o «s.» (cookie de sesión del navegador,
# se descarta al cerrarlo). Así la rotación en /refresh conserva lo elegido en el login sin que el cliente lo repita.

from fastapi import Request, Response

from app.core.config import getSettings
from app.core.exceptions import AuthError

COOKIE_NAME = "glucolume_refresh"
COOKIE_PATH = "/api/v1/auth"
CSRF_HEADER = "X-GlucoLume-CSRF"
CSRF_VALUE = "1"
REMEMBER_HEADER = "X-GlucoLume-Recordarme"
PERSISTENT_PREFIX = "p."
SESSION_PREFIX = "s."


def cookieModeRequested(request: Request) -> bool:
    return request.headers.get(CSRF_HEADER) == CSRF_VALUE


def allowedOrigins() -> set[str]:
    settings = getSettings()
    origins = {settings.frontendOrigin}
    if settings.googleOrigin:  # el login con Google corre en el origen del callback (localhost) y después transfiere la sesión
        origins.add(settings.googleOrigin)
    return origins


def requireAllowedOrigin(request: Request) -> None:
    """Rechaza el pedido con cookie si el navegador informa un Origin que no es de GlucoLume."""
    origin = request.headers.get("origin")
    if origin is not None and origin not in allowedOrigins():
        raise AuthError("TOKEN_INVALIDO", "Sesión inválida.", motivo="CSRF_ORIGEN_NO_PERMITIDO")


def _secure() -> bool:
    settings = getSettings()
    if settings.REFRESH_COOKIE_SECURE is not None:
        return settings.REFRESH_COOKIE_SECURE
    return settings.API_ENV == "production" or settings.frontendOrigin.startswith("https://")


def issue(request: Request, response: Response, refreshToken: str, *, remember: bool | None = None) -> None:
    """Pone la cookie con el refresh token. `remember=None` conserva la elección con la que se abrió la sesión (rotación)."""
    settings = getSettings()
    if remember is None:
        remember = _current(request)[1]
    value = (PERSISTENT_PREFIX if remember else SESSION_PREFIX) + refreshToken
    maxAge = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400 if remember else None
    response.set_cookie(COOKIE_NAME, value, max_age=maxAge, path=COOKIE_PATH, httponly=True, secure=_secure(), samesite="strict")


def clear(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH, httponly=True, secure=_secure(), samesite="strict")


def _current(request: Request) -> tuple[str | None, bool]:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None, False
    if raw.startswith(PERSISTENT_PREFIX):
        return raw[len(PERSISTENT_PREFIX):] or None, True
    if raw.startswith(SESSION_PREFIX):
        return raw[len(SESSION_PREFIX):] or None, False
    return None, False


def readRefreshToken(request: Request) -> str | None:
    """El refresh token de la cookie. Solo se lee en modo cookie (cabecera personalizada presente) y con un Origin permitido; si no, None."""
    if not cookieModeRequested(request):
        return None
    requireAllowedOrigin(request)
    return _current(request)[0]


def requireDeliveryMode(request: Request) -> None:
    """Dependencia de las rutas que abren sesión: sin cookie y con REFRESH_TOKEN_IN_BODY=false no habría cómo entregar el refresh token."""
    if not cookieModeRequested(request) and not getSettings().REFRESH_TOKEN_IN_BODY:
        raise AuthError("CLIENTE_NO_SOPORTADO", "Este cliente no puede abrir sesión: usá la aplicación web.")


def deliver(request: Request, response: Response, result, *, rotate: bool = False):
    """En modo cookie mueve el refresh token del cuerpo de la respuesta a la cookie HttpOnly; si no, deja el cuerpo como estaba.
    `rotate` (renovación): conserva la elección «recordarme» con la que se abrió la sesión en vez de leerla de la cabecera."""
    if result.tokens is not None and cookieModeRequested(request):
        requireAllowedOrigin(request)
        issue(request, response, result.tokens.refreshToken, remember=None if rotate else rememberRequested(request))
        result.tokens.refreshToken = None
    return result


def rememberRequested(request: Request) -> bool:
    return request.headers.get(REMEMBER_HEADER) == "1"
