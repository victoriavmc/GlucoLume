# Recuperación de contraseña de cuentas comunes: POST /auth/password/forgot y /auth/password/reset.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_password_recovery.py -v

import re
from datetime import timedelta

from sqlalchemy import select

from app.models.accountToken import AccountToken
from app.models.localCredential import LocalCredential
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import PASSWORD, db, engine, makeUser, mails  # noqa: F401
from tests.test_platform import login, web  # noqa: F401

FORGOT = "/api/v1/auth/password/forgot"
RESET = "/api/v1/auth/password/reset"
NEW = "Zorro#Lento-2027"
SAME_ANSWER = "Si el correo corresponde a una cuenta"


def forgot(web, email):
    return web.post(FORGOT, json={"correoElectronico": email})


def linkToken(mails) -> str:
    sent = [m for m in mails if "Restablecé tu contraseña" in m["subject"]]
    assert len(sent) == 1
    return re.search(r"/restablecer-contrasena\?token=([\w-]+)", sent[-1]["text"]).group(1)


def test_flujo_completo_cambia_la_contrasena_cierra_sesiones_y_avisa(db, mails, web):
    user = makeUser(db, email="persona@example.com", usuario="persona")
    session = login(web, user)
    response = forgot(web, "persona@example.com")
    assert response.status_code == 202 and SAME_ANSWER in response.json()["mensaje"]
    token = linkToken(mails)

    assert web.post(RESET, json={"token": token, "password": NEW}).status_code == 200
    assert web.get("/api/v1/auth/me", headers=session).status_code == 401, "Las sesiones abiertas se cierran."
    assert web.post("/api/v1/auth/login", json={"identificador": "persona", "password": PASSWORD}).status_code != 200
    assert web.post("/api/v1/auth/login", json={"identificador": "persona", "password": NEW}).status_code == 200
    assert any("Cambiaste tu contraseña con éxito" in m["subject"] for m in mails)

    # Un solo uso.
    again = web.post(RESET, json={"token": token, "password": "Otra#Clave-2028"})
    assert again.status_code == 401 and again.json()["codigo"] == "TOKEN_INVALIDO"


def test_la_respuesta_no_revela_si_la_cuenta_existe(db, mails, web):
    makeUser(db, email="persona@example.com", usuario="persona")
    known = forgot(web, "persona@example.com")
    unknown = forgot(web, "nadie@example.com")
    assert (known.status_code, known.json()) == (unknown.status_code, unknown.json())
    assert len(mails) == 1, "Solo la cuenta real recibe correo."


def test_cuenta_solo_google_o_pendiente_o_de_plataforma_no_recibe_enlace(db, mails, web):
    makeUser(db, email="google@example.com", usuario="goo", local=False, google=True)
    pending = makeUser(db, email="pendiente@example.com", usuario="pend")
    pending.estado = "PENDIENTE"
    makeUser(db, tipoCuenta="ADMINISTRADOR_PLATAFORMA", email="admin@example.com", usuario="adm")
    db.commit()
    for email in ("google@example.com", "pendiente@example.com", "admin@example.com"):
        assert forgot(web, email).status_code == 202
    assert mails == []


def test_no_se_emiten_enlaces_en_rafaga(db, mails, web):
    makeUser(db, email="persona@example.com", usuario="persona")
    forgot(web, "persona@example.com")
    forgot(web, "persona@example.com")
    assert len(mails) == 1


def test_enlace_vencido_o_inexistente_se_rechaza(db, mails, web):
    user = makeUser(db, email="persona@example.com", usuario="persona")
    forgot(web, "persona@example.com")
    token = linkToken(mails)
    row = db.scalar(select(AccountToken).where(AccountToken.idUsuario == user.idUsuario))
    row.fechaCreacion = nowForDb() - timedelta(hours=2)
    row.fechaExpiracion = nowForDb() - timedelta(hours=1)
    db.commit()

    expired = web.post(RESET, json={"token": token, "password": NEW})
    assert expired.status_code == 410 and expired.json()["codigo"] == "TOKEN_VENCIDO"
    missing = web.post(RESET, json={"token": "no-existe", "password": NEW})
    assert missing.status_code == 401 and missing.json()["codigo"] == "TOKEN_INVALIDO"


def test_la_contrasena_nueva_debe_cumplir_la_politica_y_el_enlace_sigue_vivo(db, mails, web):
    user = makeUser(db, email="persona@example.com", usuario="persona")
    forgot(web, "persona@example.com")
    token = linkToken(mails)
    assert web.post(RESET, json={"token": token, "password": "corta"}).status_code == 422
    db.expire_all()
    before = db.scalar(select(LocalCredential.passwordHash).where(LocalCredential.idUsuario == user.idUsuario))
    assert web.post(RESET, json={"token": token, "password": NEW}).status_code == 200
    db.expire_all()
    assert db.scalar(select(LocalCredential.passwordHash).where(LocalCredential.idUsuario == user.idUsuario)) != before


def test_restablecer_desbloquea_la_cuenta(db, mails, web):
    user = makeUser(db, email="persona@example.com", usuario="persona")
    credential = db.scalar(select(LocalCredential).where(LocalCredential.idUsuario == user.idUsuario))
    credential.intentosFallidosConsecutivos = 3
    credential.bloqueadoHasta = nowForDb() + timedelta(minutes=10)
    db.commit()
    forgot(web, "persona@example.com")
    assert web.post(RESET, json={"token": linkToken(mails), "password": NEW}).status_code == 200
    assert web.post("/api/v1/auth/login", json={"identificador": "persona", "password": NEW}).status_code == 200
