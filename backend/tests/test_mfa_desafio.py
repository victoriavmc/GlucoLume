# Desafío MFA del inicio de sesión (hallazgo A-2, auditoría 2): límite de intentos, vigencia y uso único, con servicios reales.
#
# Ejecutar desde backend/:  python -m pytest tests/test_mfa_desafio.py -v
#
# Modelo vigente: el challengeToken es un JWT sin estado (5 min, typ=mfa_challenge). El contador de códigos incorrectos es del FACTOR
# (por cuenta), no del desafío: pedir un desafío nuevo no lo reinicia. Al llegar a 5 fallos, bloqueo temporal de AUTH_LOCKOUT_MINUTES.
# Las pruebas fijan ese comportamiento y los casos que pide la auditoría (válido, inválido, vencido, reutilizado, bloqueado) sin
# depender del reloj: el tiempo se simula con tokens de vigencia negativa y con bloqueos vencidos en la base.

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core import security
from app.core.config import getSettings
from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.mfaFactor import MfaFactor
from app.models.mfaRecoveryCode import MfaRecoveryCode
from app.services import auth as authService
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import EMAIL, PASSWORD, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_mfa_flow import activate, cerrarSesiones, codeAt, sessions  # noqa: F401 - helpers del flujo MFA


def factorOf(db, user) -> MfaFactor:
    db.expire_all()
    return db.scalar(select(MfaFactor).where(MfaFactor.idUsuario == user.idUsuario))


def wrongTotp(secret: str) -> str:
    return "000000" if codeAt(secret) != "000000" else "111111"


def failFive(db, challengeToken: str, secret: str) -> None:
    """Cinco códigos incorrectos con el desafío dado: el quinto activa el bloqueo (MFA_BLOQUEADO)."""
    for _ in range(4):
        with pytest.raises(AuthError) as error:
            authService.verifyMfaChallenge(db, challengeToken, wrongTotp(secret), None)
        assert error.value.code == "CODIGO_INVALIDO"
    with pytest.raises(AuthError) as locked:
        authService.verifyMfaChallenge(db, challengeToken, wrongTotp(secret), None)
    assert locked.value.code == "MFA_BLOQUEADO"


# --- Válido y bloqueado: el contador es de la cuenta, no del desafío --------------------------------------------------------------


def test_desafio_valido_con_codigo_correcto_abre_sesion(db, mails):
    user = makeUser(db)
    secret, _ = activate(db, user)
    challenge = authService.loginLocal(db, EMAIL, PASSWORD)
    assert authService.verifyMfaChallenge(db, challenge.challengeToken, codeAt(secret, 30), None).estado == "AUTENTICADO"


def test_un_desafio_nuevo_no_reinicia_el_contador_de_la_cuenta(db, mails):
    """A-2: el auditor pidió un límite por desafío. Si el contador fuera del desafío, pedir otro (con la contraseña) volvería a 0.
    Aquí el segundo desafío, con el código correcto, debe rechazarse porque la cuenta ya está bloqueada."""
    user = makeUser(db)
    secret, _ = activate(db, user)
    first = authService.loginLocal(db, EMAIL, PASSWORD)
    failFive(db, first.challengeToken, secret)

    cerrarSesiones(db)
    second = authService.loginLocal(db, EMAIL, PASSWORD)
    with pytest.raises(AuthError) as error:
        authService.verifyMfaChallenge(db, second.challengeToken, codeAt(secret, 30), None)
    assert error.value.code == "MFA_BLOQUEADO"
    assert sessions(db) == 0, "Ningún intento bloqueado abre sesión."


def test_los_fallos_repartidos_entre_desafios_distintos_tambien_bloquean(db, mails):
    user = makeUser(db)
    secret, _ = activate(db, user)
    first = authService.loginLocal(db, EMAIL, PASSWORD)
    for _ in range(3):
        with pytest.raises(AuthError):
            authService.verifyMfaChallenge(db, first.challengeToken, wrongTotp(secret), None)
    cerrarSesiones(db)
    second = authService.loginLocal(db, EMAIL, PASSWORD)
    with pytest.raises(AuthError) as error:
        authService.verifyMfaChallenge(db, second.challengeToken, wrongTotp(secret), None)
    assert error.value.code == "CODIGO_INVALIDO"  # cuarto fallo de la cuenta
    cerrarSesiones(db)
    third = authService.loginLocal(db, EMAIL, PASSWORD)
    with pytest.raises(AuthError) as locked:
        authService.verifyMfaChallenge(db, third.challengeToken, wrongTotp(secret), None)
    assert locked.value.code == "MFA_BLOQUEADO"


def test_bloqueo_vencido_devuelve_el_acceso_legitimo(db, mails):
    """Sin DoS permanente: cuando vence el bloqueo, el titular vuelve a entrar con su código; el contador empieza de nuevo."""
    user = makeUser(db)
    secret, _ = activate(db, user)
    challenge = authService.loginLocal(db, EMAIL, PASSWORD)
    failFive(db, challenge.challengeToken, secret)

    factor = factorOf(db, user)
    factor.bloqueadoHasta = nowForDb() - timedelta(seconds=1)  # el bloqueo venció
    db.commit()
    cerrarSesiones(db)
    again = authService.loginLocal(db, EMAIL, PASSWORD)
    assert authService.verifyMfaChallenge(db, again.challengeToken, codeAt(secret, 30), None).estado == "AUTENTICADO"


def test_el_bloqueo_dura_mas_que_la_vigencia_del_desafio():
    """Un desafío emitido antes del bloqueo vence antes de que termine el bloqueo: ningún desafío previo puede volver a usarse
    cuando el bloqueo se levanta. Invariante de configuración (si alguien acorta el bloqueo, esta prueba avisa)."""
    settings = getSettings()
    assert settings.MFA_CHALLENGE_EXPIRE_MINUTES < settings.AUTH_LOCKOUT_MINUTES


# --- Inválido, vencido y reutilizado ---------------------------------------------------------------------------------------------


def test_desafio_vencido_no_se_acepta_y_no_cuenta_contra_la_cuenta(db, mails):
    user = makeUser(db)
    secret, _ = activate(db, user)
    expired = security._encodeJwt(
        {"sub": str(user.idUsuario), "typ": security.TOKEN_TYPE_MFA_CHALLENGE, "amr": [authService.METHOD_PASSWORD]},
        timedelta(minutes=-1),
    )
    before = factorOf(db, user).intentosFallidosConsecutivos
    with pytest.raises(AuthError) as error:
        authService.verifyMfaChallenge(db, expired, codeAt(secret, 30), None)
    assert error.value.code == "TOKEN_INVALIDO"
    assert factorOf(db, user).intentosFallidosConsecutivos == before


def test_desafio_invalido_no_cuenta_contra_la_cuenta(db, mails):
    user = makeUser(db)
    activate(db, user)
    with pytest.raises(AuthError) as error:
        authService.verifyMfaChallenge(db, "no-es-un-jwt", "123456", None)
    assert error.value.code == "TOKEN_INVALIDO"
    assert factorOf(db, user).intentosFallidosConsecutivos == 0


def test_codigo_totp_ya_aceptado_no_se_vuelve_a_aceptar(db, mails):
    user = makeUser(db)
    secret, _ = activate(db, user)
    code = codeAt(secret, 30)
    first = authService.loginLocal(db, EMAIL, PASSWORD)
    assert authService.verifyMfaChallenge(db, first.challengeToken, code, None).estado == "AUTENTICADO"
    cerrarSesiones(db)
    second = authService.loginLocal(db, EMAIL, PASSWORD)
    with pytest.raises(AuthError) as reused:
        authService.verifyMfaChallenge(db, second.challengeToken, code, None)
    assert reused.value.code == "CODIGO_INVALIDO"


def test_codigos_de_recuperacion_cuentan_en_el_mismo_contador_y_son_de_uso_unico(db, mails):
    user = makeUser(db)
    _, codes = activate(db, user)
    challenge = authService.loginLocal(db, EMAIL, PASSWORD)
    for _ in range(4):
        with pytest.raises(AuthError) as error:
            authService.verifyMfaChallenge(db, challenge.challengeToken, None, "ZZZZZZZZZZ")
        assert error.value.code == "CODIGO_INVALIDO"
    with pytest.raises(AuthError) as locked:  # quinto fallo: activa el bloqueo
        authService.verifyMfaChallenge(db, challenge.challengeToken, None, "ZZZZZZZZZZ")
    assert locked.value.code == "MFA_BLOQUEADO"
    with pytest.raises(AuthError) as blocked:  # un código de recuperación válido tampoco entra durante el bloqueo
        authService.verifyMfaChallenge(db, challenge.challengeToken, None, codes[0])
    assert blocked.value.code == "MFA_BLOQUEADO"
    assert db.scalar(select(MfaRecoveryCode).where(MfaRecoveryCode.fechaUso.is_not(None))) is None, "El bloqueo no consume el código."

    factor = factorOf(db, user)
    factor.bloqueadoHasta = nowForDb() - timedelta(seconds=1)
    db.commit()
    cerrarSesiones(db)
    again = authService.loginLocal(db, EMAIL, PASSWORD)
    assert authService.verifyMfaChallenge(db, again.challengeToken, None, codes[0]).estado == "AUTENTICADO"
    cerrarSesiones(db)
    reuse = authService.loginLocal(db, EMAIL, PASSWORD)
    with pytest.raises(AuthError) as used:
        authService.verifyMfaChallenge(db, reuse.challengeToken, None, codes[0])
    assert used.value.code == "CODIGO_INVALIDO"
    usados = db.scalars(select(MfaRecoveryCode).where(MfaRecoveryCode.fechaUso.is_not(None))).all()
    assert len(usados) == 1, "Un solo código de recuperación consumido."


# --- Auditoría: se registra el intento, nunca el código ----------------------------------------------------------------------------


def test_la_auditoria_registra_el_intento_sin_guardar_el_codigo(db, mails):
    user = makeUser(db)
    secret, codes = activate(db, user)
    challenge = authService.loginLocal(db, EMAIL, PASSWORD)
    wrong = wrongTotp(secret)
    with pytest.raises(AuthError):
        authService.verifyMfaChallenge(db, challenge.challengeToken, wrong, None)
    with pytest.raises(AuthError):
        authService.verifyMfaChallenge(db, challenge.challengeToken, None, "ZZZZZZZZZZ")

    db.expire_all()
    rows = db.scalars(select(Audit).where(Audit.accion == "MFA_CODIGO_INVALIDO")).all()
    assert len(rows) == 2, "Cada código incorrecto queda en la auditoría."
    stored = " ".join(str(value) for row in db.scalars(select(Audit)).all() for value in row.__dict__.values() if value is not None)
    assert wrong not in stored and "ZZZZZZZZZZ" not in stored
    assert all(code not in stored for code in codes), "Ningún código de recuperación queda en la auditoría."
    assert secret not in stored, "El secreto TOTP nunca va a la auditoría."

