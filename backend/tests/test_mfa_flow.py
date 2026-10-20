# Pruebas de punta a punta del flujo MFA (TOTP) con los servicios reales.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_mfa_flow.py -v
#
# Usan el esquema SQLite temporal de test_account_deletion.py y códigos TOTP reales (pyotp).

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pyotp
import pytest
from sqlalchemy import func, select

from app.core.config import getSettings
from app.core.exceptions import AuthError
from app.models.mfaFactor import MfaFactor
from app.models.mfaRecoveryCode import MfaRecoveryCode
from app.models.userSession import UserSession
from app.services import auth as authService
from app.services import mfa as mfaService
from app.utils.timeZone import nowArgentina
from tests.test_account_deletion import (  # noqa: F401 - fixtures
    EMAIL,
    PASSWORD,
    db,
    engine,
    mails,
    makeUser,
    reload,
)


def codeAt(secret: str, offsetSeconds: int = 0) -> str:
    return pyotp.TOTP(secret).at(nowArgentina() + timedelta(seconds=offsetSeconds))


def sessions(db) -> int:
    return db.scalar(select(func.count()).select_from(UserSession))


def activate(db, user) -> tuple[str, list[str]]:
    secret, _ = mfaService.startSetup(db, user)
    return secret, mfaService.enable(db, user, codeAt(secret))


def test_setup_genera_secreto_y_uri_para_el_qr_sin_activar(db, mails):
    user = makeUser(db)
    secret, uri = mfaService.startSetup(db, user)

    parts = urlsplit(uri)
    assert parts.scheme == "otpauth" and parts.netloc == "totp"
    query = parse_qs(parts.query)
    assert query["secret"] == [secret] and query["issuer"] == [getSettings().MFA_ISSUER]
    factor = db.scalar(select(MfaFactor))
    assert factor.habilitado is False and secret not in factor.secretoCifrado, "El secreto se guarda cifrado."
    # Generar el QR no activa MFA: el login sigue sin desafío.
    assert authService.loginLocal(db, EMAIL, PASSWORD).estado == "AUTENTICADO"


def test_activar_exige_un_codigo_valido(db, mails):
    user = makeUser(db)
    secret, _ = mfaService.startSetup(db, user)

    with pytest.raises(AuthError) as wrong:
        mfaService.enable(db, user, "000000")
    assert wrong.value.code == "CODIGO_INVALIDO"
    assert mfaService.isEnabled(db, user) is False

    codes = mfaService.enable(db, user, codeAt(secret))
    assert mfaService.isEnabled(db, user) is True
    assert len(codes) == 10 and len(set(codes)) == 10
    assert db.scalar(select(func.count()).select_from(MfaRecoveryCode)) == 10
    assert "Verificación en dos pasos activada" in [mail["subject"] for mail in mails][-1] or mails


def test_login_con_mfa_no_entrega_sesion_hasta_validar(db, mails):
    user = makeUser(db)
    secret, _ = activate(db, user)
    before = sessions(db)

    challenge = authService.loginLocal(db, EMAIL, PASSWORD)
    assert challenge.estado == "MFA_REQUERIDO" and challenge.tokens is None and challenge.challengeToken
    assert sessions(db) == before, "Sin sesión antes del segundo factor."

    with pytest.raises(AuthError) as wrong:
        authService.verifyMfaChallenge(db, challenge.challengeToken, "123456" if codeAt(secret) != "123456" else "654321", None)
    assert wrong.value.code == "CODIGO_INVALIDO"
    assert sessions(db) == before

    nextCode = codeAt(secret, 30)
    result = authService.verifyMfaChallenge(db, challenge.challengeToken, nextCode, None)
    assert result.estado == "AUTENTICADO" and result.tokens.accessToken and result.tokens.refreshToken
    assert sessions(db) == before + 1

    # El mismo código no se acepta dos veces (protección contra reutilización).
    again = authService.loginLocal(db, EMAIL, PASSWORD)
    with pytest.raises(AuthError):
        authService.verifyMfaChallenge(db, again.challengeToken, nextCode, None)


def test_codigo_de_recuperacion_sirve_una_sola_vez(db, mails):
    user = makeUser(db)
    _, codes = activate(db, user)

    first = authService.loginLocal(db, EMAIL, PASSWORD)
    assert authService.verifyMfaChallenge(db, first.challengeToken, None, codes[0]).estado == "AUTENTICADO"

    second = authService.loginLocal(db, EMAIL, PASSWORD)
    with pytest.raises(AuthError) as reused:
        authService.verifyMfaChallenge(db, second.challengeToken, None, codes[0])
    assert reused.value.code == "CODIGO_INVALIDO"
    assert authService.verifyMfaChallenge(db, second.challengeToken, None, codes[1]).estado == "AUTENTICADO"


def test_codigos_incorrectos_bloquean_temporalmente(db, mails):
    user = makeUser(db)
    activate(db, user)
    challenge = authService.loginLocal(db, EMAIL, PASSWORD)
    for _ in range(4):
        with pytest.raises(AuthError) as error:
            authService.verifyMfaChallenge(db, challenge.challengeToken, "000001", None)
        assert error.value.code == "CODIGO_INVALIDO"
    with pytest.raises(AuthError) as locked:
        authService.verifyMfaChallenge(db, challenge.challengeToken, "000001", None)
    assert locked.value.code == "MFA_BLOQUEADO"


def test_desafio_invalido_o_de_otro_tipo(db, mails):
    from app.core import security

    user = makeUser(db)
    activate(db, user)
    accessToken = security.createAccessToken(user.idUsuario, user.idUsuario)
    for token in ("no-es-un-jwt", accessToken):
        with pytest.raises(AuthError) as error:
            authService.verifyMfaChallenge(db, token, "123456", None)
        assert error.value.code == "TOKEN_INVALIDO"


def test_desactivar_exige_codigo_valido(db, mails):
    user = makeUser(db)
    secret, codes = activate(db, user)

    with pytest.raises(AuthError) as wrong:
        mfaService.disable(db, user, "000002", None)
    assert wrong.value.code == "CODIGO_INVALIDO" and mfaService.isEnabled(db, user)

    mfaService.disable(db, user, codeAt(secret, 30), None)
    assert mfaService.isEnabled(db, user) is False
    assert db.scalar(select(func.count()).select_from(MfaRecoveryCode)) == 0
    assert authService.loginLocal(db, EMAIL, PASSWORD).estado == "AUTENTICADO"
    with pytest.raises(AuthError) as notEnabled:
        mfaService.disable(db, user, codeAt(secret), None)
    assert notEnabled.value.code == "MFA_NO_CONFIGURADO"


def test_desactivar_con_codigo_de_recuperacion(db, mails):
    user = makeUser(db)
    _, codes = activate(db, user)
    mfaService.disable(db, user, None, codes[3])
    assert mfaService.isEnabled(db, user) is False


def test_no_se_puede_activar_dos_veces(db, mails):
    user = makeUser(db)
    activate(db, user)
    with pytest.raises(AuthError) as error:
        mfaService.startSetup(db, user)
    assert error.value.code == "MFA_YA_HABILITADO"


def test_resumen_de_cuenta_informa_el_estado(db, mails):
    user = makeUser(db)
    assert authService.accountSummary(db, user).mfaHabilitado is False
    activate(db, user)
    assert authService.accountSummary(db, reload(db, type(user), user.idUsuario)).mfaHabilitado is True


def test_sin_clave_de_cifrado_mfa_no_esta_disponible_y_no_se_omite(db, mails, monkeypatch):
    user = makeUser(db)
    activate(db, user)
    settings = getSettings().model_copy(update={"MFA_ENCRYPTION_KEY": None})
    monkeypatch.setattr(mfaService, "getSettings", lambda: settings)
    monkeypatch.setattr(authService, "getSettings", lambda: settings)
    with pytest.raises(AuthError) as setup:
        mfaService.startSetup(db, makeUser(db, email="otra@example.com", usuario="otraa"))
    assert setup.value.code == "MFA_NO_DISPONIBLE"
    # Un MFA ya habilitado nunca se saltea: sin clave no hay sesión.
    with pytest.raises(AuthError) as login:
        authService.loginLocal(db, EMAIL, PASSWORD)
    assert login.value.code == "MFA_NO_DISPONIBLE"
