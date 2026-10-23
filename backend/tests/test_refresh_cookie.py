# Pruebas de H-09: el refresh token viaja en una cookie HttpOnly y no en el cuerpo ni en el almacenamiento del navegador.
#
# Ejecutar desde backend/:  python -m pytest tests/test_refresh_cookie.py -v
# Usan el esquema SQLite temporal de test_account_deletion.py: no tocan SQL Server real.

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import sessionCookie
from app.api.deps import getDb
from app.core.config import getSettings
from app.models.userSession import UserSession
from tests.test_account_deletion import PASSWORD, db, engine, makeUser, mails  # noqa: F401 - fixtures

CSRF = {sessionCookie.CSRF_HEADER: "1"}
LOGIN = {"identificador": "victoria", "password": PASSWORD}


@pytest.fixture
def web(db, engine):  # noqa: F811
    from app.main import app

    def testDb():
        yield db

    app.dependency_overrides[getDb] = testDb
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def user(db):  # noqa: F811
    return makeUser(db)


def setCookies(response) -> list[str]:
    return response.headers.get_list("set-cookie")


def refreshCookie(response) -> str:
    [cookie] = [c for c in setCookies(response) if c.startswith(f"{sessionCookie.COOKIE_NAME}=")]
    return cookie


def test_el_login_del_navegador_no_devuelve_el_refresh_token_y_lo_pone_en_una_cookie_httponly(web, user):
    response = web.post("/api/v1/auth/login", json=LOGIN, headers=CSRF)
    assert response.status_code == 200, response.text
    tokens = response.json()["tokens"]
    assert tokens["accessToken"] and tokens["refreshToken"] is None
    assert "refreshToken\":\"" not in response.text
    cookie = refreshCookie(response)
    lowered = cookie.lower()
    assert "httponly" in lowered and "samesite=strict" in lowered and "path=/api/v1/auth" in lowered
    # Sin «recordarme»: cookie de sesión del navegador (se descarta al cerrarlo), sin Max-Age ni Expires.
    assert "max-age" not in lowered and "expires" not in lowered
    assert cookie.split("=", 1)[1].startswith(sessionCookie.SESSION_PREFIX)


def test_recordarme_hace_la_cookie_persistente_con_el_plazo_de_la_sesion(web, user):
    response = web.post("/api/v1/auth/login", json=LOGIN, headers={**CSRF, sessionCookie.REMEMBER_HEADER: "1"})
    cookie = refreshCookie(response)
    assert f"Max-Age={getSettings().REFRESH_TOKEN_EXPIRE_DAYS * 86400}" in cookie
    assert cookie.split("=", 1)[1].startswith(sessionCookie.PERSISTENT_PREFIX)


def test_el_valor_de_la_cookie_no_se_guarda_en_claro_y_el_cuerpo_nunca_lo_repite(web, db, user):
    response = web.post("/api/v1/auth/login", json=LOGIN, headers=CSRF)
    value = refreshCookie(response).split("=", 1)[1].split(";", 1)[0][2:]
    [session] = db.scalars(select(UserSession)).all()
    assert value not in response.text and session.refreshTokenHash != value


def test_refresh_con_cookie_rota_el_token_conserva_el_modo_y_no_lo_devuelve_en_el_cuerpo(web, user):
    first = web.post("/api/v1/auth/login", json=LOGIN, headers={**CSRF, sessionCookie.REMEMBER_HEADER: "1"})
    old = refreshCookie(first)
    response = web.post("/api/v1/auth/refresh", headers=CSRF)  # sin cuerpo: la cookie la manda el navegador
    assert response.status_code == 200, response.text
    assert response.json()["accessToken"] and response.json()["refreshToken"] is None
    new = refreshCookie(response)
    assert new != old and "Max-Age" in new and new.split("=", 1)[1].startswith("p.")  # sigue siendo «recordarme»


def test_el_token_rotado_no_sirve_y_reutilizarlo_revoca_todas_las_sesiones(web, db, user):
    web.post("/api/v1/auth/login", json=LOGIN, headers=CSRF)
    stolen = web.cookies.get(sessionCookie.COOKIE_NAME, path=sessionCookie.COOKIE_PATH)
    assert web.post("/api/v1/auth/refresh", headers=CSRF).status_code == 200
    web.cookies.clear()
    web.cookies.set(sessionCookie.COOKIE_NAME, stolen, path=sessionCookie.COOKIE_PATH)
    response = web.post("/api/v1/auth/refresh", headers=CSRF)
    assert response.status_code == 401
    assert all(s.fechaRevocacion is not None for s in db.scalars(select(UserSession)).all())
    assert f"{sessionCookie.COOKIE_NAME}=" in "".join(setCookies(response))  # y se pide al navegador que la borre
    assert "max-age=0" in refreshCookie(response).lower()


def test_sin_la_cabecera_personalizada_la_cookie_no_se_usa(web, user):
    web.post("/api/v1/auth/login", json=LOGIN, headers=CSRF)
    assert web.cookies.get(sessionCookie.COOKIE_NAME, path=sessionCookie.COOKIE_PATH)
    # Un formulario o <img> de otro sitio no puede poner la cabecera: aunque el navegador mande la cookie, no es un pedido válido.
    assert web.post("/api/v1/auth/refresh").status_code in (401, 422)
    assert web.post("/api/v1/auth/refresh", json={}).status_code in (401, 422)


def test_un_origin_ajeno_se_rechaza_aunque_lleve_la_cabecera_y_no_borra_la_cookie(web, user):
    web.post("/api/v1/auth/login", json=LOGIN, headers=CSRF)
    response = web.post("/api/v1/auth/refresh", headers={**CSRF, "Origin": "https://sitio-malicioso.example"})
    assert response.status_code == 401
    assert not setCookies(response)  # un tercero no puede provocar el cierre de la sesión de otra persona
    ok = web.post("/api/v1/auth/refresh", headers={**CSRF, "Origin": getSettings().frontendOrigin})
    assert ok.status_code == 200


def test_el_login_con_un_origin_ajeno_no_entrega_sesion_en_cookie(web, user):
    response = web.post("/api/v1/auth/login", json=LOGIN, headers={**CSRF, "Origin": "https://sitio-malicioso.example"})
    assert response.status_code == 401 and not setCookies(response)


def test_logout_revoca_la_sesion_y_borra_la_cookie(web, db, user):
    tokens = web.post("/api/v1/auth/login", json=LOGIN, headers=CSRF).json()["tokens"]
    response = web.post("/api/v1/auth/logout", headers={**CSRF, "Authorization": f"Bearer {tokens['accessToken']}"})
    assert response.status_code == 204
    assert "max-age=0" in refreshCookie(response).lower()
    assert all(s.fechaRevocacion is not None for s in db.scalars(select(UserSession)).all())
    web.cookies.clear()
    assert web.post("/api/v1/auth/refresh", headers=CSRF).status_code == 401


def test_una_cookie_manipulada_o_sin_prefijo_es_invalida(web, user):
    for value in ("basura", "p.", "s.", "x.abc"):
        web.cookies.clear()
        web.cookies.set(sessionCookie.COOKIE_NAME, value, path=sessionCookie.COOKIE_PATH)
        assert web.post("/api/v1/auth/refresh", headers=CSRF).status_code == 401, value


def test_la_cookie_va_con_secure_en_produccion_o_con_frontend_https(monkeypatch, web, user):
    settings = getSettings()
    monkeypatch.setattr(settings, "API_ENV", "production")
    assert "; secure" in refreshCookie(web.post("/api/v1/auth/login", json=LOGIN, headers=CSRF)).lower()
    monkeypatch.setattr(settings, "API_ENV", "development")
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://glucolume.example")
    assert "; secure" in refreshCookie(web.post("/api/v1/auth/login", json=LOGIN, headers=CSRF)).lower()
    monkeypatch.setattr(settings, "FRONTEND_URL", "http://localhost:5173")
    assert "; secure" not in refreshCookie(web.post("/api/v1/auth/login", json=LOGIN, headers=CSRF)).lower()
    monkeypatch.setattr(settings, "REFRESH_COOKIE_SECURE", True)
    assert "; secure" in refreshCookie(web.post("/api/v1/auth/login", json=LOGIN, headers=CSRF)).lower()


def test_el_modo_heredado_sigue_funcionando_para_clientes_que_no_son_el_navegador(web, user):
    response = web.post("/api/v1/auth/login", json=LOGIN)
    assert response.status_code == 200 and not setCookies(response)
    tokens = response.json()["tokens"]
    assert tokens["refreshToken"]
    renewed = web.post("/api/v1/auth/refresh", json={"refreshToken": tokens["refreshToken"]})
    assert renewed.status_code == 200 and renewed.json()["refreshToken"] and not setCookies(renewed)


def test_con_refresh_token_in_body_apagado_no_hay_modo_heredado(monkeypatch, web, user):
    monkeypatch.setattr(getSettings(), "REFRESH_TOKEN_IN_BODY", False)
    legacy = web.post("/api/v1/auth/login", json=LOGIN)
    assert legacy.status_code == 400 and legacy.json()["codigo"] == "CLIENTE_NO_SOPORTADO"
    assert web.post("/api/v1/auth/login", json=LOGIN, headers=CSRF).status_code == 200
    token = web.cookies.get(sessionCookie.COOKIE_NAME, path=sessionCookie.COOKIE_PATH)[2:]
    web.cookies.clear()
    assert web.post("/api/v1/auth/refresh", json={"refreshToken": token}).status_code == 401  # tampoco por el cuerpo


def test_el_modo_cookie_no_acepta_el_cuerpo_aunque_haya_modo_heredado(web, user):
    token = web.post("/api/v1/auth/login", json=LOGIN).json()["tokens"]["refreshToken"]
    assert web.post("/api/v1/auth/refresh", json={"refreshToken": token}, headers=CSRF).status_code == 401


def test_las_cuentas_con_mfa_reciben_la_cookie_recien_al_completar_el_segundo_factor(web, db, user):
    import pyotp

    from app.models.mfaFactor import MfaFactor  # noqa: F401
    from app.services import mfa as mfaService

    secret, _ = mfaService.startSetup(db, user)
    mfaService.enable(db, user, pyotp.TOTP(secret).now())
    nextCode = pyotp.TOTP(secret).at(__import__('time').time() + 30)  # otro paso: el código de activación ya se consumió
    challenge = web.post("/api/v1/auth/login", json=LOGIN, headers=CSRF)
    assert challenge.json()["estado"] == "MFA_REQUERIDO" and not setCookies(challenge)
    done = web.post("/api/v1/auth/mfa/verify", headers={**CSRF, sessionCookie.REMEMBER_HEADER: "1"},
                    json={"challengeToken": challenge.json()["challengeToken"], "codigo": nextCode})
    assert done.status_code == 200, done.text
    assert done.json()["tokens"]["refreshToken"] is None and "httponly" in refreshCookie(done).lower()


def test_no_hay_ninguna_ruta_que_devuelva_el_refresh_token_en_el_cuerpo_en_modo_cookie(web, user):
    for response in (web.post("/api/v1/auth/login", json=LOGIN, headers=CSRF), web.post("/api/v1/auth/refresh", headers=CSRF)):
        assert "refreshToken\": \"" not in response.text and "refreshToken\":\"" not in response.text


def test_la_configuracion_avisa_de_los_ajustes_que_debilitan_la_cookie(monkeypatch, tmp_path):
    settings = getSettings()
    monkeypatch.setattr(settings, "API_ENV", "production")
    monkeypatch.setattr(settings, "REFRESH_TOKEN_IN_BODY", True)
    monkeypatch.setattr(settings, "REFRESH_COOKIE_SECURE", False)
    warnings = " ".join(settings.securityWarnings(tmp_path / ".env"))
    assert "REFRESH_COOKIE_SECURE=false" in warnings and "REFRESH_TOKEN_IN_BODY=true" in warnings
    monkeypatch.setattr(settings, "REFRESH_TOKEN_IN_BODY", False)
    monkeypatch.setattr(settings, "REFRESH_COOKIE_SECURE", None)
    warnings = " ".join(settings.securityWarnings(tmp_path / ".env"))
    assert "REFRESH_COOKIE_SECURE" not in warnings and "REFRESH_TOKEN_IN_BODY" not in warnings
