# Dos accesos separados (AccesoLogin): el general (localhost:8080/login) no admite cuentas de administración de GlucoLume y el
# administrativo (/plataforma/login) solo las admite. El rechazo ocurre con la contraseña ya verificada, antes de abrir la sesión o
# pedir MFA, y queda en la auditoría.

from tests.test_account_deletion import PASSWORD, audits, db, engine, mails, makeUser  # noqa: F401 - fixtures
from tests.test_institutions import team  # noqa: F401 - fixture
from tests.test_platform import admin, login, moderator, strictPolicy, web  # noqa: F401 - fixtures


def test_el_acceso_general_es_el_por_omision_y_no_admite_administracion(db, mails, web, admin, moderator):
    for user in (admin[0], moderator[0]):
        response = web.post("/api/v1/auth/login", json={"identificador": user.usuario, "password": PASSWORD})
        assert response.status_code == 403, response.text
        assert response.json()["codigo"] == "ACCESO_PLATAFORMA_REQUERIDO"
        assert "challengeToken" not in response.text and "accessToken" not in response.text  # ni desafío MFA ni sesión


def test_el_acceso_administrativo_no_admite_cuentas_comunes(db, mails, web, team):
    individual = makeUser(db, email="persona@example.com", usuario="persona")
    for user in (individual, team.owner):
        response = web.post("/api/v1/auth/login", json={"identificador": user.usuario, "acceso": "PLATAFORMA", "password": PASSWORD})
        assert response.status_code == 403, response.text
        assert response.json()["codigo"] == "ACCESO_PLATAFORMA_DENEGADO"
        assert "accessToken" not in response.text


def test_cada_acceso_entra_con_su_tipo_de_cuenta(db, mails, web, moderator, team):
    headers = login(web, moderator[0], moderator[1])  # acceso administrativo (por omisión del helper)
    assert web.get("/api/v1/platform/me", headers=headers).status_code == 200

    ownerHeaders = login(web, team.owner, acceso="GENERAL")
    assert web.get("/api/v1/auth/me", headers=ownerHeaders).status_code == 200


def test_los_rechazos_de_acceso_quedan_auditados(db, mails, web, admin, team):
    individual = makeUser(db, email="persona@example.com", usuario="persona")
    web.post("/api/v1/auth/login", json={"identificador": admin[0].usuario, "password": PASSWORD})
    web.post("/api/v1/auth/login", json={"identificador": individual.usuario, "acceso": "PLATAFORMA", "password": PASSWORD})

    observaciones = {event.observacion for event in audits(db, "LOGIN_LOCAL")}
    assert {
        "Cuenta de administración de GlucoLume en el acceso general",
        "Acceso administrativo con una cuenta sin rol de plataforma",
    } <= observaciones


ALERTA_ASUNTO = "Intento de ingreso a la administración de GlucoLume"


def test_un_intento_fallido_contra_un_administrador_avisa_y_queda_auditado(db, mails, web, admin):
    response = web.post("/api/v1/auth/login", json={"identificador": admin[0].usuario, "password": "ClaveIncorrecta-999"})
    assert response.status_code == 401, response.text

    alerts = [m for m in mails if m["subject"] == ALERTA_ASUNTO]
    assert [m["to"] for m in alerts] == [admin[0].correoElectronico]
    assert admin[0].correoElectronico in alerts[0]["html"]  # el correo de la cuenta intentada
    events = audits(db, "INTENTO_ACCESO_ADMINISTRACION")
    assert len(events) == 1 and events[0].idUsuario == admin[0].idUsuario and events[0].resultado == "FALLO"


def test_una_cuenta_comun_que_intenta_la_administracion_avisa_con_su_correo(db, mails, web, admin):
    individual = makeUser(db, email="persona@example.com", usuario="persona")
    response = web.post("/api/v1/auth/login", json={"identificador": individual.usuario, "acceso": "PLATAFORMA", "password": PASSWORD})
    assert response.status_code == 403 and response.json()["codigo"] == "ACCESO_PLATAFORMA_DENEGADO"

    alerts = [m for m in mails if m["subject"] == ALERTA_ASUNTO]
    assert [m["to"] for m in alerts] == [admin[0].correoElectronico]
    assert "persona@example.com" in alerts[0]["html"]
    assert len(audits(db, "INTENTO_ACCESO_ADMINISTRACION")) == 1


def test_un_ingreso_correcto_a_la_administracion_no_avisa(db, mails, web, admin):
    login(web, admin[0], admin[1])
    assert [m for m in mails if m["subject"] == ALERTA_ASUNTO] == []
    assert audits(db, "INTENTO_ACCESO_ADMINISTRACION") == []


def test_un_identificador_inexistente_no_avisa_ni_guarda_lo_escrito(db, mails, web, admin):
    response = web.post("/api/v1/auth/login", json={"identificador": "nadie@example.com", "acceso": "PLATAFORMA", "password": PASSWORD})
    assert response.status_code == 401, response.text
    assert [m for m in mails if m["subject"] == ALERTA_ASUNTO] == []
    assert audits(db, "INTENTO_ACCESO_ADMINISTRACION") == []
