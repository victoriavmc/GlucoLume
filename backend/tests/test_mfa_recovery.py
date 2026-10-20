# Pruebas de "perdí acceso a mi aplicación autenticadora" (app/services/mfaRecovery.py).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_mfa_recovery.py -v
#
# Usan el esquema SQLite temporal y el SMTP simulado de test_account_deletion.py, con TOTP reales.

import json
import re
from datetime import timedelta

import pyotp
import pytest
from sqlalchemy import func, select

from app.core import security
from app.core.exceptions import AuthError
from app.emails.formatting import maskEmail
from app.integrations.google.oauth import GoogleIdentity
from app.models.accountToken import AccountToken
from app.models.audit import Audit
from app.models.localCredential import LocalCredential
from app.models.mfaFactor import MfaFactor
from app.models.mfaRecoveryCode import MfaRecoveryCode
from app.models.userSession import UserSession
from app.services import auth as authService
from app.services import mfa as mfaService
from app.services import mfaRecovery as recovery
from app.utils.timeZone import nowArgentina, nowForDb
from tests.test_account_deletion import (  # noqa: F401 - fixtures
    EMAIL,
    PASSWORD,
    db,
    engine,
    mails,
    makeSession,
    makeUser,
)

SUBJECT = "Código para recuperar tu acceso - GlucoLume"


def activate(db, user) -> str:
    secret, _ = mfaService.startSetup(db, user)
    mfaService.enable(db, user, pyotp.TOTP(secret).now())
    return secret


def challenge(db) -> str:
    response = authService.loginLocal(db, EMAIL, PASSWORD)
    assert response.estado == "MFA_REQUERIDO"
    return response.challengeToken


def emailedCode(mails) -> str:
    mail = [m for m in mails if m["subject"] == SUBJECT][-1]
    return re.search(r"\b(\d{6})\b", mail["text"]).group(1)


def tokens(db) -> list[AccountToken]:
    db.expire_all()
    return list(db.scalars(select(AccountToken).where(AccountToken.tipo == "RECUPERACION_MFA")))


def allowNewCode(db):
    """Simula que pasó el minuto de espera entre códigos."""
    for token in tokens(db):
        token.fechaCreacion = token.fechaCreacion - timedelta(minutes=2)
        token.fechaExpiracion = token.fechaExpiracion - timedelta(minutes=2)
    db.commit()


@pytest.fixture
def mfaUser(db, mails):
    user = makeUser(db)
    secret = activate(db, user)
    return user, secret


# --- Paso 1: identidad + código al correo --------------------------------------------------


def test_password_incorrecta_rechaza_la_recuperacion(db, mails, mfaUser):
    with pytest.raises(AuthError) as error:
        recovery.startRecovery(db, challenge(db), "OtraClave#2026")
    assert error.value.code == "PASSWORD_INCORRECTA"
    assert error.value.message == "La contraseña ingresada no es correcta."
    assert tokens(db) == [] and not [m for m in mails if m["subject"] == SUBJECT]
    assert db.scalar(select(LocalCredential)).intentosFallidosConsecutivos == 1


def test_password_requerida_para_cuentas_con_credencial_local(db, mails, mfaUser):
    with pytest.raises(AuthError) as error:
        recovery.startRecovery(db, challenge(db), None)
    assert error.value.code == "PASSWORD_REQUERIDA"


def test_password_correcta_envia_codigo_al_correo_registrado(db, mails, mfaUser):
    user, _ = mfaUser
    result = recovery.startRecovery(db, challenge(db), PASSWORD)

    assert result.correoEnmascarado == maskEmail(EMAIL) and result.correoEnmascarado.startswith("vi*")
    assert EMAIL not in result.correoEnmascarado and result.vigenciaMinutos == 10
    [mail] = [m for m in mails if m["subject"] == SUBJECT]
    assert mail["to"] == EMAIL
    code = emailedCode(mails)
    for secret in (PASSWORD, mfaService.getFactor(db, user).secretoCifrado):
        assert secret not in mail["html"]

    [stored] = tokens(db)
    assert stored.fechaExpiracion - stored.fechaCreacion == timedelta(minutes=10)
    assert code not in stored.tokenHash and stored.tokenHash != security.hashOpaqueToken(code), "Solo un HMAC del código."
    assert mfaService.isEnabled(db, user), "Pedir el código todavía no desactiva nada."


def test_desafio_invalido_o_usuario_sin_mfa(db, mails):
    makeUser(db)
    with pytest.raises(AuthError) as error:
        recovery.startRecovery(db, "no-es-un-jwt", PASSWORD)
    assert error.value.code == "TOKEN_INVALIDO"
    # Un access token no sirve como desafío.
    user = db.scalar(select(LocalCredential)).usuario
    with pytest.raises(AuthError):
        recovery.startRecovery(db, security.createAccessToken(user.idUsuario, user.idUsuario), PASSWORD)
    # Un desafío de un usuario sin MFA no inicia nada.
    with pytest.raises(AuthError) as noMfa:
        recovery.startRecovery(db, security.createMfaChallengeToken(user.idUsuario, "pwd"), PASSWORD)
    assert noMfa.value.code == "TOKEN_INVALIDO"


def test_limite_de_solicitudes(db, mails, mfaUser):
    recovery.startRecovery(db, challenge(db), PASSWORD)
    with pytest.raises(AuthError) as tooSoon:
        recovery.startRecovery(db, challenge(db), PASSWORD)
    assert tooSoon.value.code == "DEMASIADAS_SOLICITUDES"

    for _ in range(2):
        allowNewCode(db)
        recovery.startRecovery(db, challenge(db), PASSWORD)
    allowNewCode(db)
    with pytest.raises(AuthError) as perHour:
        recovery.startRecovery(db, challenge(db), PASSWORD)
    assert perHour.value.code == "DEMASIADAS_SOLICITUDES"
    assert len([m for m in mails if m["subject"] == SUBJECT]) == 3


def test_un_codigo_nuevo_invalida_el_anterior(db, mails, mfaUser):
    first = recovery.startRecovery(db, challenge(db), PASSWORD)
    oldCode = emailedCode(mails)
    allowNewCode(db)
    second = recovery.startRecovery(db, challenge(db), PASSWORD)
    newCode = emailedCode(mails)
    assert recovery.pendingCount(db, mfaUser[0].idUsuario) == 1
    if oldCode != newCode:
        with pytest.raises(AuthError) as error:
            recovery.verifyRecovery(db, first.recoveryToken, oldCode)
        assert error.value.code == "CODIGO_INVALIDO"
    assert recovery.verifyRecovery(db, second.recoveryToken, newCode).estado == "AUTENTICADO"


# --- Paso 2: código + desvinculación ---------------------------------------------------------


def test_codigo_incorrecto_rechazado_y_bloqueo_por_intentos(db, mails, mfaUser):
    started = recovery.startRecovery(db, challenge(db), PASSWORD)
    code = emailedCode(mails)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(4):
        with pytest.raises(AuthError) as error:
            recovery.verifyRecovery(db, started.recoveryToken, wrong)
        assert error.value.code == "CODIGO_INVALIDO" and error.value.message.startswith("El código ingresado no es válido")
    with pytest.raises(AuthError) as locked:
        recovery.verifyRecovery(db, started.recoveryToken, wrong)
    assert locked.value.code == "MFA_BLOQUEADO"
    # Bloqueado: ni siquiera el código correcto sirve y MFA sigue activo.
    with pytest.raises(AuthError):
        recovery.verifyRecovery(db, started.recoveryToken, code)
    assert mfaService.isEnabled(db, mfaUser[0])


def test_codigo_vencido(db, mails, mfaUser):
    started = recovery.startRecovery(db, challenge(db), PASSWORD)
    code = emailedCode(mails)
    [stored] = tokens(db)
    stored.fechaCreacion = nowForDb() - timedelta(minutes=20)
    stored.fechaExpiracion = nowForDb() - timedelta(minutes=10)
    db.commit()
    with pytest.raises(AuthError) as error:
        recovery.verifyRecovery(db, started.recoveryToken, code)
    assert error.value.code == "CODIGO_VENCIDO" and error.value.message == "El código venció. Solicitá uno nuevo."
    assert mfaService.isEnabled(db, mfaUser[0])


def test_recuperacion_completa_desactiva_mfa_y_revoca_sesiones(db, mails, mfaUser):
    user, secret = mfaUser
    old = makeSession(db, user)
    started = recovery.startRecovery(db, challenge(db), PASSWORD)
    code = emailedCode(mails)

    response = recovery.verifyRecovery(db, started.recoveryToken, code)

    assert response.estado == "AUTENTICADO" and response.tokens.accessToken
    db.expire_all()
    assert db.scalars(select(MfaFactor)).all() == [], "Sin secreto TOTP reutilizable."
    assert db.scalars(select(MfaRecoveryCode)).all() == []
    assert db.get(UserSession, old.idSesion).fechaRevocacion is not None, "Las sesiones anteriores se revocan."
    active = db.scalars(select(UserSession).where(UserSession.fechaRevocacion.is_(None))).all()
    assert len(active) == 1, "Solo queda la sesión nueva."
    assert all(t.fechaUso is not None for t in tokens(db)), "El código quedó consumido."

    # El código no se puede reutilizar.
    with pytest.raises(AuthError):
        recovery.verifyRecovery(db, started.recoveryToken, code)
    # El login ya no pide el MFA anterior.
    assert authService.loginLocal(db, EMAIL, PASSWORD).estado == "AUTENTICADO"
    # Aviso posterior de seguridad, sin secretos.
    notice = [m for m in mails if m["subject"] == "La verificación en dos pasos fue desactivada"][-1]
    assert "proceso de recuperación" in notice["html"] and code not in notice["html"]

    # Auditoría sin contraseña, código ni secreto.
    actions = [a.accion for a in db.scalars(select(Audit))]
    for action in ("MFA_RECUPERACION_SOLICITADA", "MFA_RECUPERACION_CODIGO_ENVIADO", "MFA_RECUPERACION_COMPLETADA",
                   "MFA_DESHABILITADO_POR_RECUPERACION"):
        assert action in actions
    for audit in db.scalars(select(Audit)):
        dump = json.dumps([audit.datosPrevios, audit.datosNuevos, audit.observacion])
        assert PASSWORD not in dump and code not in dump and secret not in dump


def test_activar_de_nuevo_genera_un_secreto_nuevo(db, mails, mfaUser):
    user, oldSecret = mfaUser
    started = recovery.startRecovery(db, challenge(db), PASSWORD)
    recovery.verifyRecovery(db, started.recoveryToken, emailedCode(mails))

    newSecret, _ = mfaService.startSetup(db, user)
    assert newSecret != oldSecret
    mfaService.enable(db, user, pyotp.TOTP(newSecret).now())
    assert authService.loginLocal(db, EMAIL, PASSWORD).estado == "MFA_REQUERIDO"
    # El autenticador perdido ya no sirve.
    with pytest.raises(AuthError):
        mfaService.disable(db, user, pyotp.TOTP(oldSecret).at(nowArgentina() + timedelta(seconds=30)), None)


def test_rollback_si_falla_la_transaccion(db, mails, mfaUser, monkeypatch):
    from sqlalchemy.exc import OperationalError

    user, _ = mfaUser
    started = recovery.startRecovery(db, challenge(db), PASSWORD)
    code = emailedCode(mails)
    original = db.commit
    calls = {"n": 0}

    def failingCommit():
        calls["n"] += 1
        raise OperationalError("COMMIT", {}, Exception("falla simulada"))

    monkeypatch.setattr(db, "commit", failingCommit)
    with pytest.raises(OperationalError):
        recovery.verifyRecovery(db, started.recoveryToken, code)
    monkeypatch.setattr(db, "commit", original)

    db.expire_all()
    assert mfaService.isEnabled(db, user), "MFA no queda desactivado a medias."
    assert recovery.pendingCount(db, user.idUsuario) == 1, "El código no queda consumido."
    assert recovery.verifyRecovery(db, started.recoveryToken, code).estado == "AUTENTICADO"


def test_token_de_flujo_no_sirve_como_desafio_ni_al_reves(db, mails, mfaUser):
    started = recovery.startRecovery(db, challenge(db), PASSWORD)
    with pytest.raises(AuthError):
        authService.verifyMfaChallenge(db, started.recoveryToken, "123456", None)
    with pytest.raises(AuthError):
        recovery.verifyRecovery(db, challenge(db), emailedCode(mails))


# --- Cuentas solo Google ------------------------------------------------------------------


def test_cuenta_solo_google_usa_el_ingreso_con_google_mas_correo(db, mails):
    user = makeUser(db, local=False, google=True)
    activate(db, user)
    identity = GoogleIdentity(subject=f"sub-{user.idUsuario}", email=EMAIL, emailVerified=True, givenName=None,
                              familyName=None)
    code = authService.createGoogleExchangeCode(db, authService.identifyGoogleUser(db, identity, "CONSUMIDOR_FINAL", True))
    googleChallenge = authService.exchangeGoogleCode(db, code).challengeToken

    started = recovery.startRecovery(db, googleChallenge, None)
    assert recovery.verifyRecovery(db, started.recoveryToken, emailedCode(mails)).estado == "AUTENTICADO"
    assert not mfaService.isEnabled(db, user)


def test_cuenta_solo_google_no_acepta_un_desafio_de_contrasena(db, mails):
    user = makeUser(db, local=False, google=True)
    activate(db, user)
    with pytest.raises(AuthError) as error:
        recovery.startRecovery(db, security.createMfaChallengeToken(user.idUsuario, "pwd"), None)
    assert error.value.code == "REAUTENTICACION_REQUERIDA"


def test_cuenta_con_password_que_ingreso_con_google_igual_exige_password(db, mails):
    user = makeUser(db, google=True)
    activate(db, user)
    googleChallenge = security.createMfaChallengeToken(user.idUsuario, "google")
    with pytest.raises(AuthError) as error:
        recovery.startRecovery(db, googleChallenge, None)
    assert error.value.code == "PASSWORD_REQUERIDA"
    assert recovery.startRecovery(db, googleChallenge, PASSWORD).correoEnmascarado
    assert db.scalar(select(func.count()).select_from(AccountToken)) >= 1


# --- Desde Seguridad (con sesión): perdió la aplicación y los códigos de recuperación ---------

DESVINCULAR_SUBJECT = "Código para recuperar la verificación en dos pasos - GlucoLume"


def accountCode(mails) -> str:
    mail = [m for m in mails if m["subject"] == DESVINCULAR_SUBJECT][-1]
    return re.search(r"\b(\d{6})\b", mail["text"]).group(1)


def test_desactivacion_normal_sigue_funcionando(db, mails, mfaUser):
    user, secret = mfaUser
    mfaService.disable(db, user, pyotp.TOTP(secret).at(nowArgentina() + timedelta(seconds=30)), None)
    assert not mfaService.isEnabled(db, user)


def test_seguridad_password_incorrecta_no_envia_codigo(db, mails, mfaUser):
    user, _ = mfaUser
    with pytest.raises(AuthError) as error:
        recovery.startAccountRecovery(db, user, "OtraClave#2026")
    assert error.value.code == "PASSWORD_INCORRECTA" and error.value.message == "La contraseña ingresada no es correcta."
    assert tokens(db) == [] and not [m for m in mails if m["subject"] == DESVINCULAR_SUBJECT]


def test_seguridad_recuperacion_completa_conserva_la_sesion_actual(db, mails, mfaUser):
    user, secret = mfaUser
    current = makeSession(db, user)
    other = makeSession(db, user)

    masked, minutes = recovery.startAccountRecovery(db, user, PASSWORD)
    assert masked == maskEmail(EMAIL) and minutes == 10
    mail = [m for m in mails if m["subject"] == DESVINCULAR_SUBJECT][-1]
    assert mail["to"] == EMAIL and "ni a tus códigos de recuperación" in mail["html"]
    code = accountCode(mails)

    wrong = "000000" if code != "000000" else "111111"
    with pytest.raises(AuthError) as bad:
        recovery.completeAccountRecovery(db, user, current.idSesion, wrong)
    assert bad.value.code == "CODIGO_INVALIDO"
    assert mfaService.isEnabled(db, user)

    recovery.completeAccountRecovery(db, user, current.idSesion, code)

    db.expire_all()
    assert db.scalars(select(MfaFactor)).all() == [] and db.scalars(select(MfaRecoveryCode)).all() == []
    assert db.get(UserSession, current.idSesion).fechaRevocacion is None, "La sesión actual se conserva."
    assert db.get(UserSession, other.idSesion).fechaRevocacion is not None, "Las demás se revocan."
    assert all(t.fechaUso is not None for t in tokens(db))
    with pytest.raises(AuthError) as reused:
        recovery.completeAccountRecovery(db, user, current.idSesion, code)
    assert reused.value.code == "MFA_NO_CONFIGURADO"
    # El TOTP anterior ya no sirve: el login no pide MFA y el secreto viejo no desactiva nada.
    assert authService.loginLocal(db, EMAIL, PASSWORD).estado == "AUTENTICADO"
    newSecret, _ = mfaService.startSetup(db, user)
    assert newSecret != secret
    with pytest.raises(AuthError):
        mfaService.enable(db, user, pyotp.TOTP(secret).now())
    codes = mfaService.enable(db, user, pyotp.TOTP(newSecret).now())
    assert len(codes) == 10


def test_seguridad_codigo_vencido_y_usado(db, mails, mfaUser):
    user, _ = mfaUser
    session = makeSession(db, user)
    recovery.startAccountRecovery(db, user, PASSWORD)
    code = accountCode(mails)
    [stored] = tokens(db)
    stored.fechaCreacion = nowForDb() - timedelta(minutes=20)
    stored.fechaExpiracion = nowForDb() - timedelta(minutes=10)
    db.commit()
    with pytest.raises(AuthError) as expired:
        recovery.completeAccountRecovery(db, user, session.idSesion, code)
    assert expired.value.code == "CODIGO_VENCIDO"

    allowNewCode(db)
    recovery.startAccountRecovery(db, user, PASSWORD)
    newCode = accountCode(mails)
    if newCode != code:
        with pytest.raises(AuthError) as old:
            recovery.completeAccountRecovery(db, user, session.idSesion, code)
        assert old.value.code == "CODIGO_INVALIDO"
    recovery.completeAccountRecovery(db, user, session.idSesion, newCode)
    assert not mfaService.isEnabled(db, user)


def test_seguridad_limites_compartidos_con_el_login(db, mails, mfaUser):
    user, _ = mfaUser
    recovery.startAccountRecovery(db, user, PASSWORD)
    with pytest.raises(AuthError) as tooSoon:
        recovery.startAccountRecovery(db, user, PASSWORD)
    assert tooSoon.value.code == "DEMASIADAS_SOLICITUDES"
    with pytest.raises(AuthError):
        recovery.startRecovery(db, challenge(db), PASSWORD)


def test_seguridad_cuenta_solo_google_debe_reautenticarse(db, mails):
    user = makeUser(db, local=False, google=True)
    activate(db, user)
    with pytest.raises(AuthError) as error:
        recovery.startAccountRecovery(db, user, None)
    assert error.value.code == "REAUTENTICACION_REQUERIDA" and "Google" in error.value.message
    assert tokens(db) == []


def test_seguridad_sin_mfa_activo(db, mails):
    user = makeUser(db)
    with pytest.raises(AuthError) as error:
        recovery.startAccountRecovery(db, user, PASSWORD)
    assert error.value.code == "MFA_NO_CONFIGURADO"
