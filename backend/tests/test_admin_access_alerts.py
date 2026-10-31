# Alertas de intentos rechazados contra la administración (services/adminAccessAlerts.py): límite de correos por ventana, resumen de lo
# acumulado, segundo factor y Google. La auditoría de cada intento no depende del límite ni de que el correo salga.

import pyotp
import pytest

from app.core.config import getSettings
from app.core.exceptions import AuthError
from app.models.externalIdentity import ExternalIdentity
from app.services import adminAccessAlerts as alerts
from app.services import auth as authService
from app.services import email as emailService
from app.services import mfaRecovery as recovery
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import PASSWORD, audits, db, engine, mails, makeUser  # noqa: F401 - fixtures
from tests.test_google_exchange import IDENTITY, googleEnv, runCallback  # noqa: F401 - fixtures
from tests.test_mfa_recovery import emailedCode
from tests.test_platform import admin, web  # noqa: F401 - fixtures

ALERTA = "Intento de ingreso a la administración de GlucoLume"
WRONG_PASSWORD = "ClaveIncorrecta-999"


@pytest.fixture
def minutos(monkeypatch):
    """Fija SECURITY_ALERT_EMAIL_MINUTES para la prueba y restablece la configuración al terminar."""
    def set_(value: int) -> None:
        monkeypatch.setenv("SECURITY_ALERT_EMAIL_MINUTES", str(value))
        getSettings.cache_clear()
    yield set_
    monkeypatch.undo()
    getSettings.cache_clear()


def alertas(mails):
    return [m for m in mails if m["subject"] == ALERTA]


def rechazar(web, usuario, acceso="PLATAFORMA"):
    return web.post("/api/v1/auth/login", json={"identificador": usuario, "acceso": acceso, "password": WRONG_PASSWORD})


def test_un_incidente_envia_un_aviso_y_despues_un_resumen_con_lo_acumulado(db, mails, web, admin, minutos):
    minutos(60)
    for _ in range(4):
        assert rechazar(web, admin[0].usuario).status_code in (401, 429)  # 429: la cuenta queda bloqueada tras tres intentos
    assert len(alertas(mails)) == 1  # el primer intento del incidente; los demás esperan la ventana
    assert len(audits(db, "INTENTO_ACCESO_ADMINISTRACION")) == 4  # cada intento queda auditado

    alerts.flush(db)  # cierra la ventana
    summary = alertas(mails)
    assert len(summary) == 2 and "Resumen de los intentos" in summary[1]["html"]
    assert "admin@example.com (3)" in summary[1]["html"]  # los tres intentos acumulados
    assert WRONG_PASSWORD not in summary[1]["html"]  # nunca se envía lo escrito


def test_pasada_la_ventana_el_siguiente_intento_abre_un_incidente_nuevo(db, mails, admin, minutos):
    minutos(60)

    def intento():
        return alerts.Attempt(correo=admin[0].correoElectronico, tipoAutenticacion=alerts.TIPO_CONTRASENA,
                              motivo="CREDENCIALES_INVALIDAS", ip="203.0.113.5", fecha=nowForDb())

    alerts.record(db, intento(), now=0)
    alerts.record(db, intento(), now=100)
    assert len(alertas(mails)) == 1
    alerts.record(db, intento(), now=3600)  # ventana cerrada: lo acumulado sale con el nuevo incidente
    assert len(alertas(mails)) == 2
    assert "admin@example.com (2)" in alertas(mails)[1]["html"]


def test_con_el_aviso_desactivado_la_auditoria_sigue(db, mails, web, admin, minutos):
    minutos(0)
    rechazar(web, admin[0].usuario)
    assert alertas(mails) == []
    assert len(audits(db, "INTENTO_ACCESO_ADMINISTRACION")) == 1


def test_un_codigo_mfa_incorrecto_de_un_administrador_avisa(db, mails, web, admin, minutos):
    minutos(60)
    body = web.post("/api/v1/auth/login", json={"identificador": admin[0].usuario, "acceso": "PLATAFORMA", "password": PASSWORD}).json()
    assert body["estado"] == "MFA_REQUERIDO"
    actual = pyotp.TOTP(admin[1]).now()
    wrong = "111111" if actual != "111111" else "222222"

    response = web.post("/api/v1/auth/mfa/verify", json={"challengeToken": body["challengeToken"], "codigo": wrong})
    assert response.status_code != 200 and response.json()["codigo"] == "CODIGO_INVALIDO"

    alerts_ = alertas(mails)
    assert len(alerts_) == 1 and "Segundo factor" in alerts_[0]["html"]
    assert len(audits(db, "INTENTO_ACCESO_ADMINISTRACION")) == 1


def test_un_ingreso_google_rechazado_contra_la_administracion_avisa(db, mails, googleEnv, monkeypatch, minutos, admin):
    minutos(60)
    individual = makeUser(db, email=IDENTITY.email, usuario="nuevapersona", local=False)
    db.add(ExternalIdentity(idUsuario=individual.idUsuario, proveedor="GOOGLE", subjectProveedor=IDENTITY.subject,
                            emailProveedor=IDENTITY.email, emailVerificado=True))
    db.commit()

    async def fetchIdentity(request):
        return IDENTITY

    fragment = runCallback(db, monkeypatch, fetchIdentity, session={"glucolume_acceso": "PLATAFORMA"})
    assert fragment == "error=ACCESO_PLATAFORMA_DENEGADO"
    alerts_ = alertas(mails)
    assert len(alerts_) == 1 and "Cuenta de Google" in alerts_[0]["html"]


def test_cancelar_el_ingreso_con_google_no_cuenta_como_ataque(db, mails, googleEnv, monkeypatch, minutos, admin):
    minutos(60)

    async def cancelled(request):
        raise RuntimeError("access_denied")  # el usuario canceló el consentimiento en Google

    fragment = runCallback(db, monkeypatch, cancelled, session={"glucolume_acceso": "PLATAFORMA"})
    assert fragment == "error=TOKEN_INVALIDO"
    assert alertas(mails) == []
    assert audits(db, "INTENTO_ACCESO_ADMINISTRACION") == []


def test_una_falla_de_smtp_no_cambia_la_respuesta_del_ingreso(db, mails, web, admin, monkeypatch, minutos):
    minutos(60)

    def broken(*args, **kwargs):
        raise OSError("SMTP no disponible")

    monkeypatch.setattr(emailService, "sendEmailEventInBackground", broken)
    response = rechazar(web, admin[0].usuario)
    assert response.status_code == 401 and response.json()["codigo"] == "CREDENCIALES_INVALIDAS"
    assert len(audits(db, "INTENTO_ACCESO_ADMINISTRACION")) == 1


def test_un_codigo_de_recuperacion_incorrecto_de_un_administrador_avisa(db, mails, admin, minutos):
    minutos(60)
    challengeToken = authService.loginLocal(db, admin[0].correoElectronico, PASSWORD, acceso="PLATAFORMA").challengeToken
    started = recovery.startRecovery(db, challengeToken, PASSWORD)
    code = emailedCode(mails)
    wrong = "000000" if code != "000000" else "111111"

    with pytest.raises(AuthError) as error:
        recovery.verifyRecovery(db, started.recoveryToken, wrong)
    assert error.value.code == "CODIGO_INVALIDO"
    alerts_ = alertas(mails)
    assert len(alerts_) == 1 and "Segundo factor" in alerts_[0]["html"]
