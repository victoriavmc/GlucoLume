# Pruebas de los datos que se completan al registrarse con Google (usuario, sexo y fecha de nacimiento) y de quitar
# la fecha de nacimiento y el sexo desde el perfil.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_google_registro_datos.py -v
#
# Usan el esquema SQLite temporal de test_account_deletion.py. No contactan a Google.

import asyncio
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.exceptions import AuthError
from app.integrations.google import oauth as googleOAuth
from app.integrations.google.oauth import GoogleIdentity
from app.models.audit import Audit
from app.models.user import User
from app.schemas.user import UserProfileUpdate
from app.services import auth as authService
from app.services import user as userService
from app.utils.timeZone import nowArgentina
from tests.test_account_deletion import (  # noqa: F401 - fixtures
    db,
    engine,
    makeUser,
    mails,
    reload,
)


def identidad(email="juanp2@gmail.com", givenName="Juan", familyName="Perez", **datos):
    return GoogleIdentity(subject=f"sub-{email}", email=email, emailVerified=True,
                          givenName=givenName, familyName=familyName, **datos)


# --- Nombre de usuario sugerido desde el correo ----------------------------------------------


def test_registro_con_google_sugiere_el_usuario_desde_el_correo(db, mails):
    user = authService.identifyGoogleUser(db, identidad(), "CONSUMIDOR_FINAL", True)
    assert user.usuario == "juanp2"
    assert reload(db, User, user.idUsuario).usuario == "juanp2"


def test_usuario_sugerido_ignora_la_etiqueta_mas(db, mails):
    user = authService.identifyGoogleUser(db, identidad(email="juan.perez+salud@gmail.com"), "CONSUMIDOR_FINAL", True)
    assert user.usuario == "juan.perez"


def test_usuario_sugerido_repetido_agrega_un_numero(db, mails):
    makeUser(db, email="otra.persona@example.com", usuario="juanp2")
    user = authService.identifyGoogleUser(db, identidad(), "CONSUMIDOR_FINAL", True)
    assert user.usuario == "juanp22"


def test_usuario_sugerido_muy_corto_usa_un_respaldo(db, mails):
    user = authService.identifyGoogleUser(db, identidad(email="jo@gmail.com"), "CONSUMIDOR_FINAL", True)
    assert user.usuario == "usuario"


def test_la_persona_puede_cambiar_el_usuario_sugerido(db, mails):
    user = authService.identifyGoogleUser(db, identidad(), "CONSUMIDOR_FINAL", True)
    changed = userService.updateProfile(db, user, UserProfileUpdate(usuario="juan_cortes"))
    assert changed is True
    assert reload(db, User, user.idUsuario).usuario == "juan_cortes"


def test_no_se_puede_elegir_un_usuario_de_otra_cuenta(db, mails):
    makeUser(db, email="otra.persona@example.com", usuario="ocupado")
    user = authService.identifyGoogleUser(db, identidad(), "CONSUMIDOR_FINAL", True)
    with pytest.raises(AuthError) as error:
        userService.updateProfile(db, user, UserProfileUpdate(usuario="ocupado"))
    assert error.value.code == "USUARIO_NO_DISPONIBLE"


# --- Sexo y fecha de nacimiento que informa Google --------------------------------------------


def test_registro_con_google_guarda_sexo_y_fecha_de_nacimiento(db, mails):
    identity = identidad(sexo="FEMENINO", fechaNacimiento=date(1992, 3, 4))
    user = authService.identifyGoogleUser(db, identity, "CONSUMIDOR_FINAL", True)
    stored = reload(db, User, user.idUsuario)
    assert stored.sexo == "FEMENINO"
    assert stored.fechaNacimiento == date(1992, 3, 4)


def test_registro_con_google_sin_datos_los_deja_sin_informar(db, mails):
    user = authService.identifyGoogleUser(db, identidad(), "CONSUMIDOR_FINAL", True)
    stored = reload(db, User, user.idUsuario)
    assert stored.sexo is None and stored.fechaNacimiento is None


def test_iniciar_sesion_con_google_no_modifica_sexo_ni_fecha(db, mails):
    user = makeUser(db, email="juanp2@gmail.com", usuario="juanp2")
    # El correo ya tiene cuenta: iniciar sesión no toma datos de Google (el perfil lo decide la persona).
    authService.identifyGoogleUser(db, identidad(sexo="MASCULINO", fechaNacimiento=date(1980, 1, 1)))
    stored = reload(db, User, user.idUsuario)
    assert stored.sexo == "FEMENINO" and stored.fechaNacimiento == date(1990, 5, 17)


def test_sexo_y_fecha_de_google_se_mapean_o_se_omiten():
    assert googleOAuth.sexoFromGoogle("male") == "MASCULINO"
    assert googleOAuth.sexoFromGoogle(" Female ") == "FEMENINO"
    assert googleOAuth.sexoFromGoogle("other") is None
    assert googleOAuth.sexoFromGoogle("unspecified") is None
    assert googleOAuth.sexoFromGoogle(None) is None

    today = date(2026, 11, 3)
    birthday = {"date": {"year": 1990, "month": 5, "day": 17}}
    assert googleOAuth.fechaNacimientoFromGoogle([birthday], today) == date(1990, 5, 17)
    # Sin año no alcanza para una fecha de nacimiento; se prueba la siguiente entrada completa.
    assert googleOAuth.fechaNacimientoFromGoogle([{"date": {"month": 5, "day": 17}}], today) is None
    assert googleOAuth.fechaNacimientoFromGoogle([{"date": {"year": 1990, "month": 2, "day": 31}}, birthday], today) == date(1990, 5, 17)
    assert googleOAuth.fechaNacimientoFromGoogle([{"date": {"year": 2030, "month": 1, "day": 1}}], today) is None
    assert googleOAuth.fechaNacimientoFromGoogle([{"date": {"year": 1800, "month": 1, "day": 1}}], today) is None
    assert googleOAuth.fechaNacimientoFromGoogle(None, today) is None


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def fakeGoogleClient(monkeypatch, payload=None, error=None):
    """Cliente falso: registra la última petición a la People API."""
    calls = []

    class FakeClient:
        async def get(self, url, token=None, params=None):
            calls.append({"url": url, "token": token, "params": params})
            if error is not None:
                raise error
            # Como la People API real: solo devuelve los campos pedidos en personFields.
            fields = (params or {}).get("personFields", "").split(",")
            return FakeResponse({key: value for key, value in (payload or {}).items() if key in fields})

    monkeypatch.setattr(googleOAuth, "_client", lambda: FakeClient())
    return calls


def test_datos_personales_solo_se_piden_si_la_persona_los_concedio(monkeypatch):
    payload = {"genders": [{"value": "male"}], "birthdays": [{"date": {"year": 1990, "month": 5, "day": 17}}]}
    calls = fakeGoogleClient(monkeypatch, payload)
    token = {"access_token": "abc"}

    both = googleOAuth.GOOGLE_GENDER_SCOPE + " " + googleOAuth.GOOGLE_BIRTHDAY_SCOPE
    assert asyncio.run(googleOAuth._fetchPersonalData(token, both)) == ("MASCULINO", date(1990, 5, 17))
    assert calls[-1]["params"] == {"personFields": "genders,birthdays"}

    # Solo cumpleaños concedido: no se pide el sexo.
    assert asyncio.run(googleOAuth._fetchPersonalData(token, googleOAuth.GOOGLE_BIRTHDAY_SCOPE)) == (None, date(1990, 5, 17))
    assert calls[-1]["params"] == {"personFields": "birthdays"}

    # Sin permisos: ni siquiera se llama a Google.
    before = len(calls)
    assert asyncio.run(googleOAuth._fetchPersonalData(token, "openid email profile")) == (None, None)
    assert len(calls) == before


def test_si_la_people_api_falla_el_registro_sigue_sin_esos_datos(monkeypatch):
    fakeGoogleClient(monkeypatch, error=RuntimeError("sin conexión"))
    scopes = googleOAuth.GOOGLE_GENDER_SCOPE + " " + googleOAuth.GOOGLE_BIRTHDAY_SCOPE
    assert asyncio.run(googleOAuth._fetchPersonalData({"access_token": "abc"}, scopes)) == (None, None)


def test_registro_pide_datos_personales_y_el_login_no(monkeypatch):
    scopes = []

    class FakeClient:
        async def create_authorization_url(self, redirectUri, **kwargs):
            scopes.append(kwargs.get("scope"))
            return {"url": "https://accounts.google.com/o/oauth2/v2/auth", "state": "s", "code_verifier": "v"}

        async def save_authorize_data(self, request, **kwargs):
            return None

    monkeypatch.setattr(googleOAuth, "_client", lambda: FakeClient())
    monkeypatch.setattr(googleOAuth, "getSettings", lambda: SimpleNamespace(GOOGLE_REDIRECT_URI="http://localhost/cb"))

    asyncio.run(googleOAuth.prepareAuthorization(SimpleNamespace(), datosPersonales=False))
    asyncio.run(googleOAuth.prepareAuthorization(SimpleNamespace(), datosPersonales=True))
    assert scopes[0] == googleOAuth.GOOGLE_BASE_SCOPE
    assert googleOAuth.GOOGLE_GENDER_SCOPE in scopes[1] and googleOAuth.GOOGLE_BIRTHDAY_SCOPE in scopes[1]


# --- Quitar fecha de nacimiento y sexo -------------------------------------------------------


def test_se_puede_quitar_la_fecha_de_nacimiento_y_el_sexo(db, mails):
    user = makeUser(db)
    changed = userService.updateProfile(db, user, UserProfileUpdate(fechaNacimiento=None, sexo=None))
    assert changed is True
    stored = reload(db, User, user.idUsuario)
    assert stored.fechaNacimiento is None and stored.sexo is None
    audit = db.scalar(select(Audit).where(Audit.accion == "ACTUALIZAR_PERFIL"))
    assert "quitaron los campos" in (audit.observacion or "")
    assert "fechaNacimiento" in (audit.observacion or "") and "sexo" in (audit.observacion or "")


def test_quitar_un_dato_que_ya_no_existe_no_cuenta_como_cambio(db, mails):
    user = makeUser(db)
    userService.updateProfile(db, user, UserProfileUpdate(fechaNacimiento=None, sexo=None))
    assert userService.updateProfile(db, user, UserProfileUpdate(fechaNacimiento=None)) is False


def test_null_se_acepta_solo_en_fecha_y_sexo():
    assert UserProfileUpdate(sexo=None).sexo is None
    assert UserProfileUpdate(fechaNacimiento=None).fechaNacimiento is None
    with pytest.raises(ValidationError):
        UserProfileUpdate(nombre=None)
    with pytest.raises(ValidationError):
        UserProfileUpdate(usuario=None)
    with pytest.raises(ValidationError):
        UserProfileUpdate(fechaNacimiento=(nowArgentina().date() + timedelta(days=1)))
