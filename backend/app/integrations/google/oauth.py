# GoogleOAuth - Cliente OAuth 2.0 / OpenID Connect de Google (Authlib)
#
# Flujo authorization code con state, nonce y PKCE (S256). Authlib valida el id_token
# (firma con las claves publicadas por Google, issuer, audience, expiración y nonce).

import logging
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from authlib.integrations.starlette_client import OAuth
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.core.config import getSettings
from app.schemas.user import EDAD_MAXIMA
from app.utils.timeZone import nowArgentina

logger = logging.getLogger(__name__)

GOOGLE_PROVIDER = "GOOGLE"
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
GOOGLE_BASE_SCOPE = "openid email profile"

# Datos personales que Google no entrega en el id_token: se piden a la People API y solo al registrarse con Google.
# Sensibles para Google: el usuario puede negar cada uno en la pantalla de consentimiento y el registro sigue igual.
GOOGLE_GENDER_SCOPE = "https://www.googleapis.com/auth/user.gender.read"
GOOGLE_BIRTHDAY_SCOPE = "https://www.googleapis.com/auth/user.birthday.read"
GOOGLE_PERSONAL_SCOPES = f"{GOOGLE_GENDER_SCOPE} {GOOGLE_BIRTHDAY_SCOPE}"
GOOGLE_PEOPLE_ME_URL = "https://people.googleapis.com/v1/people/me"

# Valores de Google -> valores de Usuario.sexo (CK_Usuario_sexo). "other", "unspecified" o un texto propio no se guardan.
_GOOGLE_GENDER_TO_SEXO = {"male": "MASCULINO", "female": "FEMENINO"}


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str | None
    emailVerified: bool
    givenName: str | None
    familyName: str | None
    # Solo se completan al registrarse con Google y si la persona concedió el permiso correspondiente.
    sexo: str | None = None
    fechaNacimiento: date | None = None


@lru_cache
def _client():
    settings = getSettings()
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET.get_secret_value(),
        server_metadata_url=GOOGLE_DISCOVERY_URL,
        client_kwargs={"scope": GOOGLE_BASE_SCOPE, "code_challenge_method": "S256"},
    )
    return oauth.google


async def prepareAuthorization(request: Request, datosPersonales: bool = False) -> str:
    """Genera state, nonce y PKCE, los guarda en la sesión temporal firmada y devuelve la URL de Google.

    Es el mismo procedimiento que authorize_redirect de Authlib, sin construir la respuesta HTTP.
    `datosPersonales` pide además sexo y fecha de nacimiento (solo en el registro con Google).
    """
    client = _client()
    redirectUri = getSettings().GOOGLE_REDIRECT_URI
    scope = f"{GOOGLE_BASE_SCOPE} {GOOGLE_PERSONAL_SCOPES}" if datosPersonales else GOOGLE_BASE_SCOPE
    authorization = await client.create_authorization_url(redirectUri, scope=scope)
    await client.save_authorize_data(request, redirect_uri=redirectUri, **authorization)
    return authorization["url"]


async def authorizeRedirect(request: Request, datosPersonales: bool = False) -> RedirectResponse:
    return RedirectResponse(await prepareAuthorization(request, datosPersonales), status_code=302)


def sexoFromGoogle(value: str | None) -> str | None:
    """Sexo de Google ("male"/"female") -> MASCULINO/FEMENINO; cualquier otro valor queda sin informar."""
    if not value:
        return None
    return _GOOGLE_GENDER_TO_SEXO.get(str(value).strip().lower())


def fechaNacimientoFromGoogle(birthdays: list | None, today: date | None = None) -> date | None:
    """Primera fecha de nacimiento completa (con año) de la People API; sin año o inválida no se guarda."""
    today = today or nowArgentina().date()
    for entry in birthdays or []:
        parts = (entry or {}).get("date") or {}
        year, month, day = parts.get("year"), parts.get("month"), parts.get("day")
        if not (year and month and day):
            continue
        try:
            value = date(int(year), int(month), int(day))
        except (TypeError, ValueError):
            continue
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if value <= today and age <= EDAD_MAXIMA:
            return value
    return None


async def _fetchPersonalData(token: dict, scopes: str) -> tuple[str | None, date | None]:
    """Sexo y fecha de nacimiento desde la People API. Un fallo no impide el registro: solo deja los datos sin informar."""
    fields = [name for name, scope in (("genders", GOOGLE_GENDER_SCOPE), ("birthdays", GOOGLE_BIRTHDAY_SCOPE))
              if scope in scopes]
    if not fields:
        return None, None
    try:
        response = await _client().get(
            GOOGLE_PEOPLE_ME_URL, token=token, params={"personFields": ",".join(fields)}
        )
        response.raise_for_status()
        data = response.json()
    except Exception as error:  # noqa: BLE001 - la falta de estos datos nunca debe frenar el registro
        logger.warning("No se pudieron leer sexo y fecha de nacimiento de Google (%s).", type(error).__name__)
        return None, None
    genders = data.get("genders") or []
    gender = genders[0].get("value") if genders else None
    return sexoFromGoogle(gender), fechaNacimientoFromGoogle(data.get("birthdays"))


async def fetchIdentity(request: Request) -> GoogleIdentity:
    """Intercambia el code por tokens y devuelve los datos del id_token ya validado."""
    token = await _client().authorize_access_token(request)
    claims = token["userinfo"]
    sexo, fechaNacimiento = await _fetchPersonalData(token, str(token.get("scope") or ""))
    return GoogleIdentity(
        subject=str(claims["sub"]),
        email=claims.get("email"),
        emailVerified=claims.get("email_verified") is True,
        givenName=claims.get("given_name"),
        familyName=claims.get("family_name"),
        sexo=sexo,
        fechaNacimiento=fechaNacimiento,
    )
