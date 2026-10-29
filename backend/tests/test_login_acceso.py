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
