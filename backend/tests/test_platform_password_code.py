# Cambio de contraseña de una cuenta administrativa SIN MFA con el código que llega al correo registrado
# (POST /platform/password/code y POST /platform/password/change con codigoCorreo).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_platform_password_code.py -v

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core import security
from app.models.accountToken import AccountToken
from app.services import platform
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import PASSWORD, db, engine, mails  # noqa: F401
from tests.test_platform import ADMIN, NEW_PASSWORD, login, otraSesion, platformUser, web  # noqa: F401

URL_CODE = "/api/v1/platform/password/code"
URL_CHANGE = "/api/v1/platform/password/change"
CODE = "482913"
ASUNTO = "Tu código para cambiar la contraseña"


@pytest.fixture(autouse=True)
def politicaReal(monkeypatch):
    """Rige la política real: las cuentas administrativas exigen MFA (sin MFA, el código llega por correo)."""
    monkeypatch.setattr(platform, "mfaRequired", lambda: True)
    monkeypatch.setattr(security, "generateNumericCode", lambda digits=6: CODE)


@pytest.fixture
def adminSinMfa(db, mails):
    user, _ = platformUser(db, ADMIN, "admin-sinmfa@example.com", "adminsinmfa", mfa=False)
    return user


def envejecer(db, user, minutos: int = 2, vencer: bool = False) -> None:
    """Simula el paso del tiempo sobre los TokenCuenta del usuario (cooldown de 1 minuto, o código vencido)."""
    now = nowForDb()
    for token in db.scalars(select(AccountToken).where(AccountToken.idUsuario == user.idUsuario)):
        if vencer:  # la base exige fechaCreacion < fechaExpiracion
            token.fechaCreacion = now - timedelta(minutes=11)
            token.fechaExpiracion = now - timedelta(minutes=1)
        else:
            token.fechaCreacion -= timedelta(minutes=minutos)
            token.fechaExpiracion -= timedelta(minutes=minutos)
    db.commit()


def loginAdmin(password: str) -> dict:
    """Las cuentas administrativas entran por el acceso de plataforma."""
    return {"identificador": "adminsinmfa", "acceso": "PLATAFORMA", "password": password}


def cambio(actual=PASSWORD, nueva=NEW_PASSWORD, codigo=None):
    body = {"passwordActual": actual, "passwordNueva": nueva, "confirmacion": nueva}
    if codigo is not None:
        body["codigoCorreo"] = codigo
    return body


def test_pide_el_codigo_con_la_contrasena_actual_y_lo_envia_al_correo_registrado(db, mails, web, adminSinMfa):
    headers = login(web, adminSinMfa)
    wrong = web.post(URL_CODE, headers=headers, json={"passwordActual": "Incorrecta#1234"})
    assert wrong.status_code == 403 and wrong.json()["codigo"] == "PASSWORD_INCORRECTA"
    assert not [m for m in mails if ASUNTO in m["subject"]]

    response = web.post(URL_CODE, headers=headers, json={"passwordActual": PASSWORD})
    assert response.status_code == 200, response.text
    assert response.json()["vigenciaMinutos"] == 10 and response.json()["correoEnmascarado"].endswith("@example.com")
    sent = [m for m in mails if ASUNTO in m["subject"]]
    assert len(sent) == 1 and sent[0]["to"] == "admin-sinmfa@example.com" and CODE in sent[0]["html"]
    # Solo se guarda el HMAC del código, nunca el código.
    stored = db.scalars(select(AccountToken.tokenHash).where(AccountToken.idUsuario == adminSinMfa.idUsuario)).all()
    assert stored and CODE not in stored


def test_cambia_la_contrasena_con_el_codigo_y_cierra_las_otras_sesiones(db, mails, web, adminSinMfa):
    current = login(web, adminSinMfa)
    other = otraSesion(db, adminSinMfa)  # otra sesión abierta (otro dispositivo)
    assert web.post(URL_CODE, headers=current, json={"passwordActual": PASSWORD}).status_code == 200
    response = web.post(URL_CHANGE, headers=current, json=cambio(codigo=CODE))
    assert response.status_code == 200, response.text
    assert web.get("/api/v1/platform/me", headers=current).status_code == 200
    assert web.get("/api/v1/platform/me", headers=other).status_code == 401
    assert web.post("/api/v1/auth/login", json=loginAdmin(PASSWORD)).status_code == 401  # la vieja ya no entra
    assert login(web, adminSinMfa, password=NEW_PASSWORD)  # entra con la nueva
    assert [m for m in mails if "Cambiaste tu contraseña con éxito" in m["subject"]]


def test_sin_codigo_no_cambia_la_contrasena(db, mails, web, adminSinMfa):
    headers = login(web, adminSinMfa)
    response = web.post(URL_CHANGE, headers=headers, json=cambio())
    assert response.status_code == 400 and response.json()["codigo"] == "CODIGO_CORREO_REQUERIDO"
    assert login(web, adminSinMfa)  # la contraseña sigue igual (el helper cierra la sesión anterior antes de entrar)


def test_un_codigo_incorrecto_queda_invalidado_y_el_siguiente_se_pide_tras_esperar(db, mails, web, adminSinMfa):
    headers = login(web, adminSinMfa)
    web.post(URL_CODE, headers=headers, json={"passwordActual": PASSWORD})
    wrong = web.post(URL_CHANGE, headers=headers, json=cambio(codigo="111111"))
    assert wrong.status_code == 401 and wrong.json()["codigo"] == "CODIGO_INVALIDO"
    # Un solo intento por código: ni siquiera el correcto sirve ya.
    again = web.post(URL_CHANGE, headers=headers, json=cambio(codigo=CODE))
    assert again.status_code == 401 and again.json()["codigo"] == "CODIGO_INVALIDO"

    envejecer(db, adminSinMfa)
    assert web.post(URL_CODE, headers=headers, json={"passwordActual": PASSWORD}).status_code == 200
    assert web.post(URL_CHANGE, headers=headers, json=cambio(codigo=CODE)).status_code == 200


def test_el_codigo_vence_a_los_diez_minutos(db, mails, web, adminSinMfa):
    headers = login(web, adminSinMfa)
    web.post(URL_CODE, headers=headers, json={"passwordActual": PASSWORD})
    envejecer(db, adminSinMfa, vencer=True)
    response = web.post(URL_CHANGE, headers=headers, json=cambio(codigo=CODE))
    assert response.status_code == 410 and response.json()["codigo"] == "CODIGO_VENCIDO"


def test_un_codigo_por_minuto_y_como_maximo_tres_por_hora(db, mails, web, adminSinMfa):
    headers = login(web, adminSinMfa)
    assert web.post(URL_CODE, headers=headers, json={"passwordActual": PASSWORD}).status_code == 200
    blocked = web.post(URL_CODE, headers=headers, json={"passwordActual": PASSWORD})
    assert blocked.status_code == 429 and blocked.json()["codigo"] == "DEMASIADAS_SOLICITUDES"
    for _ in range(2):  # tercer y cuarto código dentro de la hora
        envejecer(db, adminSinMfa)
        assert web.post(URL_CODE, headers=headers, json={"passwordActual": PASSWORD}).status_code == 200
    envejecer(db, adminSinMfa)
    capped = web.post(URL_CODE, headers=headers, json={"passwordActual": PASSWORD})
    assert capped.status_code == 429 and capped.json()["codigo"] == "DEMASIADAS_SOLICITUDES"


def test_con_mfa_activo_el_codigo_por_correo_no_aplica(db, mails, web):
    user, secret = platformUser(db, ADMIN, "admin-conmfa@example.com", "adminconmfa")
    headers = login(web, user, secret)
    response = web.post(URL_CODE, headers=headers, json={"passwordActual": PASSWORD})
    assert response.status_code == 400 and response.json()["codigo"] == "CODIGO_CORREO_NO_APLICA"
    assert not [m for m in mails if ASUNTO in m["subject"]]
