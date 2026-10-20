# Consentimientos (prototipo académico): confirmación de la Política de Privacidad en cada registro y autorización
# expresa para almacenar mediciones experimentales. Todo se valida en el backend.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_consents.py -v

import pytest
from sqlalchemy import select

from app.core.exceptions import AuthError
from app.integrations.google.oauth import GoogleIdentity
from app.models.consent import Consent
from app.schemas.auth import RegisterRequest
from app.services import accountActivation
from app.services import auth as authService
from app.services import consent as consentService
from app.services import measurement as measurements
from app.services.consent import CURRENT_VERSIONS
from tests.test_account_deletion import PASSWORD, db, engine, makeUser, mails  # noqa: F401 - fixtures
from tests.test_measurements import completeOximetry, device, noEstimator, oximetry  # noqa: F401
from tests.test_institution_staff import team  # noqa: F401
from tests.test_platform import login, web  # noqa: F401

NEW = "Zorro#Lento-2027"
GOOGLE = GoogleIdentity(subject="g-1", email="nueva@example.com", emailVerified=True, givenName="Nueva", familyName="Persona")


def rows(db, user):
    db.expire_all()
    return db.scalars(select(Consent).where(Consent.idUsuario == user.idUsuario).order_by(Consent.fechaHora)).all()


def expectError(code, fn, *args, **kwargs):
    with pytest.raises(AuthError) as error:
        fn(*args, **kwargs)
    assert error.value.code == code, error.value.message


def registration(**overrides):
    return RegisterRequest(**{"nombre": "Ana", "apellido": "Gómez", "usuario": "anagomez",
                              "correoElectronico": "ana@example.com", "password": NEW, **overrides})


# --- Registro: confirmación de la Política de Privacidad ---------------------------------------


def test_registro_local_sin_confirmar_la_politica_se_rechaza_y_no_crea_la_cuenta(db, mails):
    expectError("POLITICA_NO_ACEPTADA", authService.registerLocal, db, registration())
    assert authService._findUserByEmail(db, "ana@example.com") is None


def test_registro_local_registra_usuario_fecha_version_y_estado(db, mails):
    user = authService.registerLocal(db, registration(aceptaPoliticaPrivacidad=True))
    [row] = rows(db, user)
    assert (row.tipo, row.estado, row.version) == ("POLITICA_PRIVACIDAD", "ACEPTADO", CURRENT_VERSIONS["POLITICA_PRIVACIDAD"])
    assert row.fechaHora is not None and row.idUsuario == user.idUsuario


def test_registro_local_via_api_exige_la_confirmacion(db, mails, web):
    body = {"nombre": "Ana", "apellido": "Gómez", "usuario": "anagomez", "correoElectronico": "ana@example.com",
            "password": NEW}
    refused = web.post("/api/v1/auth/register", json=body)
    assert refused.status_code == 400 and refused.json()["codigo"] == "POLITICA_NO_ACEPTADA"
    assert web.post("/api/v1/auth/register", json={**body, "aceptaPoliticaPrivacidad": True}).status_code == 201


def test_registro_con_google_exige_la_confirmacion_y_la_registra(db, mails):
    expectError("POLITICA_NO_ACEPTADA", authService.identifyGoogleUser, db, GOOGLE, "CONSUMIDOR_FINAL")
    assert authService._findUserByEmail(db, "nueva@example.com") is None
    user = authService.identifyGoogleUser(db, GOOGLE, "CONSUMIDOR_FINAL", True)
    assert [(r.tipo, r.estado) for r in rows(db, user)] == [("POLITICA_PRIVACIDAD", "ACEPTADO")]


def test_google_sin_confirmar_ni_siquiera_inicia_oauth(db, mails, monkeypatch):
    import asyncio

    from starlette.requests import Request

    from app.api.v1 import auth as authRoutes
    from app.core.config import getSettings

    for key, value in {"GOOGLE_CLIENT_ID": "id", "GOOGLE_CLIENT_SECRET": "secret", "SESSION_SECRET": "s" * 40,
                       "GOOGLE_REDIRECT_URI": "http://localhost:8000/api/v1/auth/google/callback"}.items():
        monkeypatch.setenv(key, value)
    getSettings.cache_clear()
    request = Request({"type": "http", "method": "GET", "path": "/api/v1/auth/google/login", "headers": [],
                       "query_string": b"", "scheme": "http", "server": ("localhost", 8000), "session": {}})
    response = asyncio.run(authRoutes.googleLogin(request, registro="usuario", recordar=False, acepta=False))
    assert response.status_code == 302 and response.headers["location"].endswith("#error=POLITICA_NO_ACEPTADA")
    assert request.session == {}


def test_activar_cuenta_invitada_exige_y_registra_la_confirmacion(db, mails, team):
    from app.models.user import User
    from tests.test_institution_staff import NEW_PASSWORD, addNewModerator

    member, token = addNewModerator(db, team, mails)
    expectError("POLITICA_NO_ACEPTADA", accountActivation.completeActivation, db, token, "luciasosa", NEW_PASSWORD)
    accountActivation.completeActivation(db, token, "luciasosa", NEW_PASSWORD, aceptaPolitica=True)
    user = db.scalar(select(User).where(User.correoElectronico == "nueva@example.com"))
    assert [(r.tipo, r.estado) for r in rows(db, user)] == [("POLITICA_PRIVACIDAD", "ACEPTADO")]


# --- Mediciones experimentales: autorización expresa ---------------------------------------------


@pytest.fixture
def person(db, mails):
    user = makeUser(db, email="persona@example.com", usuario="persona", consent=False)
    return user, measurements.getOwnProfile(db, user).idPerfilMedicion


def test_sin_autorizacion_no_se_inicia_ninguna_medicion(db, mails, person):
    user, profileId = person
    assert consentService.status(db, user)["DATOS_EXPERIMENTALES"]["aceptado"] is False
    expectError("CONSENTIMIENTO_REQUERIDO", oximetry, db, user, profileId, device(db))


def test_autorizar_registra_y_permite_medir_revocar_frena_nuevas_recolecciones(db, mails, person):
    user, profileId = person
    consentService.setExperimentalConsent(db, user, True)
    first = completeOximetry(db, user, profileId, device(db))
    assert first.estadoMedicion == "COMPLETADA"

    consentService.setExperimentalConsent(db, user, False)
    expectError("CONSENTIMIENTO_REQUERIDO", oximetry, db, user, profileId, device(db))
    # Lo ya medido sigue disponible: revocar frena nuevas recolecciones, no borra el historial.
    assert measurements.getMeasurement(db, user, first.idMedicion).idMedicion == first.idMedicion
    assert [(r.estado) for r in rows(db, user)] == ["ACEPTADO", "REVOCADO"], "Historial de solo agregado."


def test_revocar_corta_tambien_las_muestras_de_una_medicion_en_curso(db, mails, person):
    from tests.test_measurements import samples

    user, profileId = person
    consentService.setExperimentalConsent(db, user, True)
    started = oximetry(db, user, profileId, device(db))
    consentService.setExperimentalConsent(db, user, False)
    expectError("CONSENTIMIENTO_REQUERIDO", measurements.addSamples, db, user, started.idMedicion, samples())


def test_una_version_anterior_del_texto_no_cuenta_como_vigente(db, mails, person, monkeypatch):
    user, profileId = person
    consentService.setExperimentalConsent(db, user, True)
    monkeypatch.setitem(CURRENT_VERSIONS, consentService.TipoConsentimiento.DATOS_EXPERIMENTALES, "2.0")
    assert consentService.status(db, user)["DATOS_EXPERIMENTALES"]["aceptado"] is False
    expectError("CONSENTIMIENTO_REQUERIDO", oximetry, db, user, profileId, device(db))


def test_repetir_la_misma_decision_no_agrega_filas(db, mails, person):
    user, _ = person
    consentService.setExperimentalConsent(db, user, True)
    consentService.setExperimentalConsent(db, user, True)
    assert len(rows(db, user)) == 1


def test_endpoints_de_consentimiento(db, mails, web):
    user = makeUser(db, email="persona@example.com", usuario="persona", consent=False)
    headers = login(web, user)
    before = web.get("/api/v1/auth/consents", headers=headers).json()
    assert before["DATOS_EXPERIMENTALES"]["aceptado"] is False and before["POLITICA_PRIVACIDAD"]["aceptado"] is False
    accepted = web.put("/api/v1/auth/consents/datos-experimentales", headers=headers, json={"acepta": True})
    assert accepted.status_code == 200 and accepted.json()["DATOS_EXPERIMENTALES"]["aceptado"] is True
    revoked = web.put("/api/v1/auth/consents/datos-experimentales", headers=headers, json={"acepta": False})
    assert revoked.json()["DATOS_EXPERIMENTALES"]["estado"] == "REVOCADO"
    assert web.get("/api/v1/auth/consents").status_code == 401
