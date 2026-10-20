# GoogleOAuth - Cliente OAuth 2.0 / OpenID Connect de Google (Authlib)
#
# Flujo authorization code con state, nonce y PKCE (S256). Authlib valida el id_token
# (firma con las claves publicadas por Google, issuer, audience, expiración y nonce).

from dataclasses import dataclass
from functools import lru_cache

from authlib.integrations.starlette_client import OAuth
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.core.config import getSettings

GOOGLE_PROVIDER = "GOOGLE"
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str | None
    emailVerified: bool
    givenName: str | None
    familyName: str | None


@lru_cache
def _client():
    settings = getSettings()
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET.get_secret_value(),
        server_metadata_url=GOOGLE_DISCOVERY_URL,
        client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
    )
    return oauth.google


async def prepareAuthorization(request: Request) -> str:
    """Genera state, nonce y PKCE, los guarda en la sesión temporal firmada y devuelve la URL de Google.

    Es el mismo procedimiento que authorize_redirect de Authlib, sin construir la respuesta HTTP.
    """
    client = _client()
    redirectUri = getSettings().GOOGLE_REDIRECT_URI
    authorization = await client.create_authorization_url(redirectUri)
    await client.save_authorize_data(request, redirect_uri=redirectUri, **authorization)
    return authorization["url"]


async def authorizeRedirect(request: Request) -> RedirectResponse:
    return RedirectResponse(await prepareAuthorization(request), status_code=302)


async def fetchIdentity(request: Request) -> GoogleIdentity:
    """Intercambia el code por tokens y devuelve los datos del id_token ya validado."""
    token = await _client().authorize_access_token(request)
    claims = token["userinfo"]
    return GoogleIdentity(
        subject=str(claims["sub"]),
        email=claims.get("email"),
        emailVerified=claims.get("email_verified") is True,
        givenName=claims.get("given_name"),
        familyName=claims.get("family_name"),
    )
