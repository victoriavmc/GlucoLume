# Pruebas del callback de Google con código de intercambio y de CORS para el frontend.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_google_exchange.py -v
#
# Usan el esquema SQLite temporal de test_account_deletion.py. No contactan a Google.

import asyncio
import logging
from datetime import timedelta
from urllib.parse import urlsplit

import pytest
from sqlalchemy import func, select
from starlette.requests import Request

from app.core import security
from app.core.config import getSettings
from app.core.exceptions import AuthError
from app.integrations.google.oauth import GoogleIdentity
from app.models.accountToken import AccountToken
from app.models.user import User
from app.models.userSession import UserSession
from app.services import auth as authService
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import (  # noqa: F401 - fixtures
    EMAIL,
    db,
    enableMfa,
    engine,
    mails,
    makeUser,
    reload,
    totpCode,
)

IDENTITY = GoogleIdentity(subject="google-sub-1", email="nueva.persona@example.com", emailVerified=True,
                          givenName="Nueva", familyName="Persona")


def exchangeRow(db) -> AccountToken:
    db.expire_all()
    return db.scalar(select(AccountToken).where(AccountToken.tipo == "INTERCAMBIO_GOOGLE"))


def test_codigo_de_un_solo_uso_entrega_la_sesion(db, mails):
    user = authService.identifyGoogleUser(db, IDENTITY, "CONSUMIDOR_FINAL", True)
    code = authService.createGoogleExchangeCode(db, user)

    stored = exchangeRow(db)
    assert stored.tokenHash == security.hashOpaqueToken(code) and stored.tokenHash != code
    assert stored.fechaExpiracion - stored.fechaCreacion == timedelta(seconds=120)

    response = authService.exchangeGoogleCode(db, code)
    assert response.estado == "AUTENTICADO" and response.tokens.accessToken and response.tokens.refreshToken
    assert db.scalar(select(UserSession).where(UserSession.idUsuario == user.idUsuario)) is not None

    with pytest.raises(AuthError) as reused:
        authService.exchangeGoogleCode(db, code)
    assert reused.value.code == "TOKEN_INVALIDO"


def test_codigo_vencido_o_inexistente(db, mails):
    user = authService.identifyGoogleUser(db, IDENTITY, "CONSUMIDOR_FINAL", True)
    code = authService.createGoogleExchangeCode(db, user)
    stored = exchangeRow(db)
    stored.fechaCreacion = nowForDb() - timedelta(minutes=5)
    stored.fechaExpiracion = nowForDb() - timedelta(minutes=1)
    db.commit()

    for value in (code, "no-existe"):
        with pytest.raises(AuthError) as error:
            authService.exchangeGoogleCode(db, value)
        assert error.value.code == "TOKEN_INVALIDO"


def test_nuevo_codigo_descarta_el_anterior(db, mails):
    user = authService.identifyGoogleUser(db, IDENTITY, "CONSUMIDOR_FINAL", True)
    first = authService.createGoogleExchangeCode(db, user)
    second = authService.createGoogleExchangeCode(db, user)
    with pytest.raises(AuthError):
        authService.exchangeGoogleCode(db, first)
    assert authService.exchangeGoogleCode(db, second).estado == "AUTENTICADO"


def test_canje_con_mfa_devuelve_desafio(db, mails):
    user = makeUser(db, local=False, google=True)
    secret = enableMfa(db, user)
    identity = GoogleIdentity(subject=f"sub-{user.idUsuario}", email=EMAIL, emailVerified=True,
                              givenName=None, familyName=None)
    code = authService.createGoogleExchangeCode(db, authService.identifyGoogleUser(db, identity, "CONSUMIDOR_FINAL", True))

    response = authService.exchangeGoogleCode(db, code)
    assert response.estado == "MFA_REQUERIDO" and response.tokens is None and response.challengeToken
    final = authService.verifyMfaChallenge(db, response.challengeToken, totpCode(secret), None)
    assert final.estado == "AUTENTICADO"


# --- Ruta del callback ---------------------------------------------------------------------


@pytest.fixture
def googleEnv(engine, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/auth/google/callback")
    monkeypatch.setenv("SESSION_SECRET", "s" * 40)
    getSettings.cache_clear()


def runCallback(db, monkeypatch, fetchIdentity, session=None):
    from app.api.v1 import auth as authRoutes

    monkeypatch.setattr(authRoutes.googleOAuth, "fetchIdentity", fetchIdentity)
    request = Request({"type": "http", "method": "GET", "path": "/api/v1/auth/google/callback", "headers": [],
                       "query_string": b"", "scheme": "http", "server": ("localhost", 8000), "session": session or {}})
    response = asyncio.run(authRoutes.googleCallback(request, db))
    assert response.status_code == 302
    location = response.headers["location"]
    url = urlsplit(location)
    assert f"{url.scheme}://{url.netloc}{url.path}" == "http://localhost:5173/auth/google/callback"
    assert not url.query, "Nada sensible en la query string."
    return url.fragment


def test_callback_redirige_al_frontend_con_codigo_sin_tokens(db, mails, googleEnv, monkeypatch):
    async def fetchIdentity(request):
        return IDENTITY

    # Registro (la intención viaja en la cookie de sesión): crea la cuenta y entrega el código.
    fragment = runCallback(db, monkeypatch, fetchIdentity, session={"glucolume_registro": "usuario", "glucolume_politica": True})
    assert fragment.startswith("code=") and "recordar" not in fragment
    code = fragment.removeprefix("code=")
    assert authService.exchangeGoogleCode(db, code).estado == "AUTENTICADO"


def test_callback_de_inicio_de_sesion_no_crea_cuenta_y_pide_registrarse(db, mails, googleEnv, monkeypatch):
    async def fetchIdentity(request):
        return IDENTITY

    assert runCallback(db, monkeypatch, fetchIdentity) == "error=CUENTA_NO_REGISTRADA"
    assert db.scalar(select(func.count()).select_from(User)) == 0


def test_callback_devuelve_recordarme_en_el_fragmento(db, mails, googleEnv, monkeypatch):
    authService.identifyGoogleUser(db, IDENTITY, "CONSUMIDOR_FINAL", True)

    async def fetchIdentity(request):
        return IDENTITY

    fragment = runCallback(db, monkeypatch, fetchIdentity, session={"glucolume_recordar": True})
    assert fragment.endswith("&recordar=1")


def test_callback_con_error_de_google_redirige_con_codigo_de_error(db, mails, googleEnv, monkeypatch):
    async def fetchIdentity(request):
        raise RuntimeError("state inválido")

    assert runCallback(db, monkeypatch, fetchIdentity) == "error=TOKEN_INVALIDO"


def test_callback_con_correo_no_verificado_redirige_con_error(db, mails, googleEnv, monkeypatch):
    async def fetchIdentity(request):
        return GoogleIdentity(subject="x", email="x@example.com", emailVerified=False, givenName=None,
                              familyName=None)

    assert runCallback(db, monkeypatch, fetchIdentity) == "error=VINCULACION_RECHAZADA"


# --- CORS ----------------------------------------------------------------------------------


def test_cors_solo_admite_el_origen_del_frontend(engine):
    from fastapi.middleware.cors import CORSMiddleware

    from app.main import app, settings

    [cors] = [m for m in app.user_middleware if m.cls is CORSMiddleware]
    assert cors.kwargs["allow_origins"] == [settings.frontendOrigin]
    assert cors.kwargs["allow_credentials"] is False
    assert "Authorization" in cors.kwargs["allow_headers"]


# --- Tipos de TokenCuenta: Python y SQL Server sincronizados -------------------------------


def test_tipos_de_token_coinciden_con_el_esquema_consolidado(referenceSchema):
    import re

    from app.models.accountToken import TipoTokenCuenta

    # DEC-02: el CHECK vigente está en GlucoLume_DB_v5.sql y debe tener exactamente los tipos del Enum.
    check = re.search(r"CONSTRAINT \[CK_TokenCuenta_tipo\] CHECK\s+\(([^\n]*)", referenceSchema).group(1)
    assert set(re.findall(r"N'([A-Z_]+)'", check)) == {tipo.value for tipo in TipoTokenCuenta}

    [constraint] = [c for c in AccountToken.__table__.constraints if getattr(c, "name", None) == "CK_TokenCuenta_tipo"]
    assert all(f"N'{tipo}'" in str(constraint.sqltext) for tipo in TipoTokenCuenta)


def test_check_rechazado_hace_rollback_y_registra_la_causa(db, mails, monkeypatch, caplog):
    from sqlalchemy.exc import IntegrityError

    user = authService.identifyGoogleUser(db, IDENTITY, "CONSUMIDOR_FINAL", True)
    original = db.commit

    def failingCommit():
        raise IntegrityError("INSERT INTO dbo.TokenCuenta", {}, Exception(
            'The INSERT statement conflicted with the CHECK constraint "CK_TokenCuenta_tipo".'))

    monkeypatch.setattr(db, "commit", failingCommit)
    with caplog.at_level(logging.ERROR), pytest.raises(IntegrityError):
        authService.createGoogleExchangeCode(db, user)
    assert "GlucoLume_DB_v5.sql" in caplog.text  # indica el esquema vigente, no un script retirado

    # La sesión quedó usable (rollback hecho) y no se guardó ningún código.
    monkeypatch.setattr(db, "commit", original)
    assert exchangeRow(db) is None
    assert authService.exchangeGoogleCode(db, authService.createGoogleExchangeCode(db, user)).estado == "AUTENTICADO"


def test_callback_con_error_de_base_redirige_sin_500(db, mails, googleEnv, monkeypatch):
    from sqlalchemy.exc import IntegrityError

    async def fetchIdentity(request):
        return IDENTITY

    def broken(*args, **kwargs):
        raise IntegrityError("INSERT", {}, Exception("CK_TokenCuenta_tipo"))

    monkeypatch.setattr(authService, "createGoogleExchangeCode", broken)
    assert runCallback(db, monkeypatch, fetchIdentity, session={"glucolume_registro": "usuario", "glucolume_politica": True}) == "error=ERROR_SERVIDOR"


def test_get_db_hace_rollback_si_el_request_falla(monkeypatch):
    from app.db import session as sessionModule

    calls = []

    class FakeSession:
        def rollback(self):
            calls.append("rollback")

        def close(self):
            calls.append("close")

    monkeypatch.setattr(sessionModule, "getSessionFactory", lambda: FakeSession)
    generator = sessionModule.getDb()
    next(generator)
    with pytest.raises(RuntimeError):
        generator.throw(RuntimeError("falla del endpoint"))
    assert calls == ["rollback", "close"]


# --- Un único OAuth para registro e inicio de sesión ---------------------------------------


def test_refresh_token_tras_el_canje(db, mails):
    code = authService.createGoogleExchangeCode(db, authService.identifyGoogleUser(db, IDENTITY, "CONSUMIDOR_FINAL", True))
    tokens = authService.exchangeGoogleCode(db, code).tokens
    renewed = authService.refreshSession(db, tokens.refreshToken)
    assert renewed.accessToken and renewed.refreshToken != tokens.refreshToken


def test_usuario_google_existente_inicia_sesion_sin_duplicar(db, mails):
    first = authService.identifyGoogleUser(db, IDENTITY, "CONSUMIDOR_FINAL", True)
    # Mismo tipo: entra con la cuenta existente, sin duplicar.
    again = authService.identifyGoogleUser(db, IDENTITY, "CONSUMIDOR_FINAL", True)
    assert again.idUsuario == first.idUsuario
    # Otro tipo: no se registra y no se entra en silencio; la cuenta existente no cambia.
    with pytest.raises(AuthError) as other:
        authService.identifyGoogleUser(db, IDENTITY, "USUARIO_INSTITUCIONAL", True)
    assert other.value.code == "CUENTA_OTRO_TIPO"
    assert reload(db, User, first.idUsuario).tipoCuenta == "CONSUMIDOR_FINAL"
    assert db.scalar(select(func.count()).select_from(User)) == 1
    # Iniciar sesión (sin intención de registro) sigue entrando con el tipo que ya tiene.
    assert authService.identifyGoogleUser(db, IDENTITY).idUsuario == first.idUsuario


def test_registro_local_con_correo_ya_registrado_en_otro_tipo_no_crea_otra_cuenta(db, mails):
    from app.schemas.auth import RegisterRequest

    makeUser(db, email="ana@example.com", usuario="anaexistente", tipoCuenta="CONSUMIDOR_FINAL")
    with pytest.raises(AuthError) as error:
        authService.registerLocal(db, RegisterRequest(
            aceptaPoliticaPrivacidad=True, nombre="Ana", apellido="Gómez", usuario="anainst",
            correoElectronico="ana@example.com", password="Zorro#Lento-2027", tipoCuenta="USUARIO_INSTITUCIONAL"))
    assert error.value.code == "CORREO_REGISTRADO"
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_cuenta_local_no_verificada_no_se_vincula_automaticamente(db, mails):
    local = makeUser(db, email="nueva.persona@example.com", usuario="nueva")
    local.estado = "PENDIENTE"
    db.commit()
    with pytest.raises(AuthError) as error:
        authService.identifyGoogleUser(db, IDENTITY, "CONSUMIDOR_FINAL", True)
    assert error.value.code == "VINCULACION_RECHAZADA"


def test_cuenta_local_activa_se_vincula_segun_la_regla_existente(db, mails):
    local = makeUser(db, email="nueva.persona@example.com", usuario="nueva")
    user = authService.identifyGoogleUser(db, IDENTITY, "CONSUMIDOR_FINAL", True)
    assert user.idUsuario == local.idUsuario
    assert "Google" in mails[-1]["subject"]


def test_registro_institucional_con_google_conserva_el_tipo(db, mails, googleEnv, monkeypatch):
    async def fetchIdentity(request):
        return IDENTITY

    session = {"glucolume_registro": "institucion", "glucolume_politica": True}
    fragment = runCallback(db, monkeypatch, fetchIdentity, session)
    assert fragment.startswith("code=")
    assert "glucolume_registro" not in session, "La intención se consume en el callback."
    assert db.scalar(select(User)).tipoCuenta == "USUARIO_INSTITUCIONAL"


def test_google_login_guarda_la_intencion_y_la_conserva_al_redirigir(googleEnv, monkeypatch):
    from app.api.v1 import auth as authRoutes

    async def fakeRedirect(request):
        return "redirigido"

    monkeypatch.setattr(authRoutes.googleOAuth, "authorizeRedirect", fakeRedirect)
    session = {}
    request = Request({"type": "http", "method": "GET", "path": "/api/v1/auth/google/login", "headers": [],
                       "query_string": b"registro=institucion&acepta=true", "scheme": "http",
                       "server": ("localhost", 8000), "session": session})
    assert asyncio.run(authRoutes.googleLogin(request, "institucion", False, True)) == "redirigido"
    assert session == {"glucolume_registro": "institucion", "glucolume_politica": True}

    # Iniciar sesión (sin registro) descarta una intención anterior.
    assert asyncio.run(authRoutes.googleLogin(request, None)) == "redirigido"
    assert session == {}

    other = Request({"type": "http", "method": "GET", "path": "/api/v1/auth/google/login", "headers": [],
                     "query_string": b"registro=institucion&acepta=true", "scheme": "http",
                     "server": ("127.0.0.1", 8000), "session": {}})
    response = asyncio.run(authRoutes.googleLogin(other, "institucion", False, True))
    assert response.status_code == 307
    assert response.headers["location"] == "http://localhost:8000/api/v1/auth/google/login?registro=institucion&acepta=true"


# --- Inicio de sesión sin registro y transferencia de sesión -------------------------------


def test_login_con_google_no_crea_cuentas(db, mails):
    with pytest.raises(AuthError) as error:
        authService.identifyGoogleUser(db, IDENTITY)
    assert error.value.code == "CUENTA_NO_REGISTRADA"
    assert db.scalar(select(func.count()).select_from(User)) == 0


def test_login_con_google_entra_con_cuenta_ya_vinculada_o_registrada(db, mails):
    registered = authService.identifyGoogleUser(db, IDENTITY, "CONSUMIDOR_FINAL", True)
    assert authService.identifyGoogleUser(db, IDENTITY).idUsuario == registered.idUsuario

    local = makeUser(db, email="otra.persona@example.com", usuario="otra")
    other = GoogleIdentity(subject="google-sub-2", email="otra.persona@example.com", emailVerified=True,
                           givenName=None, familyName=None)
    assert authService.identifyGoogleUser(db, other).idUsuario == local.idUsuario


def test_transferencia_de_sesion_no_repite_mfa_y_es_de_un_solo_uso(db, mails):
    user = makeUser(db, local=False, google=True)
    enableMfa(db, user)
    code = authService.createSessionTransferCode(db, user)
    assert code.startswith(authService.SESSION_TRANSFER_PREFIX)

    response = authService.exchangeGoogleCode(db, code)
    assert response.estado == "AUTENTICADO" and response.tokens.refreshToken
    with pytest.raises(AuthError) as reused:
        authService.exchangeGoogleCode(db, code)
    assert reused.value.code == "TOKEN_INVALIDO"


def test_codigo_de_google_con_mfa_no_se_confunde_con_transferencia(db, mails):
    user = makeUser(db, local=False, google=True)
    enableMfa(db, user)
    identity = GoogleIdentity(subject=f"sub-{user.idUsuario}", email=EMAIL, emailVerified=True,
                              givenName=None, familyName=None)
    code = authService.createGoogleExchangeCode(db, authService.identifyGoogleUser(db, identity, "CONSUMIDOR_FINAL", True))
    assert not code.startswith(authService.SESSION_TRANSFER_PREFIX)
    assert authService.exchangeGoogleCode(db, code).estado == "MFA_REQUERIDO"
