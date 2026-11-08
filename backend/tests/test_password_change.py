# Cambio de contraseña con sesión (POST /api/v1/auth/password/change): contraseña actual, MFA si corresponde, sesiones y aviso.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_password_change.py -v

import pyotp
from sqlalchemy import select

from app.core import security
from app.models.audit import Audit
from app.models.localCredential import LocalCredential
from app.services.auth import PASSWORD_HISTORY_SIZE
from app.models.userSession import UserSession
from tests.test_account_deletion import PASSWORD, db, engine, makeUser, mails  # noqa: F401
from tests.test_platform import enableMfa, login, otraSesion, web  # noqa: F401

URL = "/api/v1/auth/password/change"
NEW = "Zorro#Lento-2027"


def hash_of(db, user):
    db.expire_all()
    return db.scalar(select(LocalCredential.passwordHash).where(LocalCredential.idUsuario == user.idUsuario))


def test_cambia_la_contrasena_avisa_por_correo_y_cierra_las_otras_sesiones(db, mails, web):
    user = makeUser(db, email="persona@example.com", usuario="persona")
    current = login(web, user)
    other = otraSesion(db, user)  # otra sesión abierta (otro dispositivo)
    before = hash_of(db, user)
    response = web.post(URL, headers=current, json={"passwordActual": PASSWORD, "passwordNueva": NEW})
    assert response.status_code == 200, response.text
    assert hash_of(db, user) != before
    # La sesión actual sigue; la otra queda cerrada.
    assert web.get("/api/v1/auth/me", headers=current).status_code == 200
    assert web.get("/api/v1/auth/me", headers=other).status_code == 401
    # Con la contraseña vieja ya no entra; con la nueva sí.
    assert web.post("/api/v1/auth/login", json={"identificador": "persona", "password": PASSWORD}).status_code == 401
    assert login(web, user, password=NEW)
    # Correo: "Cambiaste tu contraseña con éxito", sin contraseñas.
    sent = [m for m in mails if "Cambiaste tu contraseña con éxito" in m["subject"]]
    assert len(sent) == 1 and sent[0]["to"] == "persona@example.com"
    assert NEW not in sent[0]["html"] and PASSWORD not in sent[0]["html"]
    # Auditoría sin datos sensibles.
    entry = db.scalar(select(Audit).where(Audit.accion == "CAMBIAR_PASSWORD", Audit.resultado == "EXITO"))
    assert entry is not None and NEW not in f"{entry.datosNuevos}{entry.datosPrevios}{entry.observacion}"


def test_contrasena_actual_incorrecta_se_rechaza_y_cuenta_para_el_bloqueo(db, mails, web):
    user = makeUser(db, email="persona@example.com", usuario="persona")
    headers = login(web, user)
    before = hash_of(db, user)
    response = web.post(URL, headers=headers, json={"passwordActual": "Incorrecta#1234", "passwordNueva": NEW})
    assert response.status_code == 403 and response.json()["codigo"] == "PASSWORD_INCORRECTA"
    assert hash_of(db, user) == before and not [m for m in mails if "Cambiaste" in m["subject"]]
    # Regla aprobada (M-2): un fallo no bloquea la operación; el intento con la contraseña correcta sigue disponible.
    ok = web.post(URL, headers=headers, json={"passwordActual": PASSWORD, "passwordNueva": NEW})
    assert ok.status_code == 200
    assert db.scalar(select(Audit).where(Audit.accion == "CAMBIAR_PASSWORD", Audit.resultado != "EXITO")) is not None


def test_la_nueva_debe_cumplir_la_politica_y_ser_distinta(db, mails, web):
    user = makeUser(db, email="persona@example.com", usuario="persona")
    headers = login(web, user)
    weak = web.post(URL, headers=headers, json={"passwordActual": PASSWORD, "passwordNueva": "corta"})
    assert weak.status_code == 422
    same = web.post(URL, headers=headers, json={"passwordActual": PASSWORD, "passwordNueva": PASSWORD})
    assert same.status_code == 422 and same.json()["codigo"] == "PASSWORD_REPETIDA"
    personal = web.post(URL, headers=headers, json={"passwordActual": PASSWORD, "passwordNueva": "Persona#2027-abc"})
    assert personal.status_code == 422 and personal.json()["codigo"] == "PASSWORD_DEBIL"  # contiene su usuario


def test_con_mfa_exige_un_codigo_valido(db, mails, web):
    user = makeUser(db, email="persona@example.com", usuario="persona")
    secret = enableMfa(db, user)
    headers = login(web, user, secret)
    before = hash_of(db, user)
    missing = web.post(URL, headers=headers, json={"passwordActual": PASSWORD, "passwordNueva": NEW})
    assert missing.status_code == 422 and missing.json()["codigo"] == "CODIGO_MFA_REQUERIDO"
    wrong = web.post(URL, headers=headers, json={"passwordActual": PASSWORD, "passwordNueva": NEW, "codigo": "000000"})
    assert wrong.status_code in (401, 403, 422) and hash_of(db, user) == before
    from app.services import mfa
    factor = mfa.getFactor(db, user)
    factor.ultimoPasoUsado = None
    db.commit()
    ok = web.post(URL, headers=headers, json={"passwordActual": PASSWORD, "passwordNueva": NEW, "codigo": pyotp.TOTP(secret).now()})
    assert ok.status_code == 200, ok.text
    assert hash_of(db, user) != before


def test_una_cuenta_solo_google_debe_crear_primero_su_contrasena(db, mails):
    import pytest

    from app.core.exceptions import AuthError
    from app.services import auth as authService
    from tests.test_account_deletion import makeSession

    user = makeUser(db, email="persona@example.com", usuario="persona", local=False, google=True)
    with pytest.raises(AuthError) as error:
        authService.changeLocalPassword(db, user, makeSession(db, user), PASSWORD, NEW, None, None)
    assert error.value.code == "CREDENCIAL_LOCAL_INEXISTENTE"


def test_no_admite_la_contrasena_anterior_y_lo_dice_sin_mas(db, mails, web):
    user = makeUser(db, email="persona@example.com", usuario="persona")
    headers = login(web, user)
    assert web.post(URL, headers=headers, json={"passwordActual": PASSWORD, "passwordNueva": NEW}).status_code == 200
    back = web.post(URL, headers=headers, json={"passwordActual": NEW, "passwordNueva": PASSWORD})
    assert back.status_code == 422 and back.json()["codigo"] == "PASSWORD_ANTERIOR"
    assert "contraseña vieja" in back.text
    assert security.verifyPassword(NEW, hash_of(db, user))[0]  # la vigente sigue siendo NEW
    assert login(web, user, password=NEW)  # el helper cierra la sesión anterior antes de entrar


def test_recuerda_solo_las_ultimas_cinco_anteriores(db, mails, web):
    user = makeUser(db, email="persona@example.com", usuario="persona")
    headers = login(web, user)
    chain = [PASSWORD] + [f"Zorro#Lento-{year}" for year in range(2027, 2027 + PASSWORD_HISTORY_SIZE + 1)]  # una más que el historial: la primera queda fuera
    for actual, nueva in zip(chain, chain[1:]):
        assert web.post(URL, headers=headers, json={"passwordActual": actual, "passwordNueva": nueva}).status_code == 200
    rejected = web.post(URL, headers=headers, json={"passwordActual": chain[-1], "passwordNueva": chain[1]})
    assert rejected.status_code == 422 and rejected.json()["codigo"] == "PASSWORD_ANTERIOR"
    back = web.post(URL, headers=headers, json={"passwordActual": chain[-1], "passwordNueva": PASSWORD})
    assert back.status_code == 200, back.text
