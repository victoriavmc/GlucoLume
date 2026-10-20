# Contador de intentos fallidos de MFA ATÓMICO (mfa.verifyFactor y mfaRecovery): el límite de 5 vale aunque las solicitudes lleguen en paralelo.
#
#     python -m pytest tests/test_mfa_attempts_atomic.py -v
#
# Hallazgo de la auditoría Cloudflare (run-1): el contador se leía, se sumaba en memoria y se escribía como valor absoluto; N solicitudes que
# leían el mismo factor antes de que alguna confirmara dejaban el contador en 1, sin bloqueo, y el TOTP correcto siguiente se aceptaba.
# Cada «solicitud» es una Session distinta que lee el factor antes de que otra confirme (lecturas obsoletas, como READ COMMITTED).

import pyotp
import pytest
from sqlalchemy import update
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import AuthError
from app.models.mfaFactor import MfaFactor
from app.services import mfa as mfaService
from app.utils.timeZone import nowArgentina, nowForDb
from tests.test_account_deletion import db, enableMfa, engine, mails, makeUser, totpCode  # noqa: F401 - fixtures


def wrongCode(secret: str) -> str:
    totp = pyotp.TOTP(secret)
    step = totp.timecode(nowArgentina())
    valid = {totp.generate_otp(step + offset) for offset in (-1, 0, 1)}
    return next(f"{n:06d}" for n in range(1_000_000) if f"{n:06d}" not in valid)


def concurrentFailures(engine, user, code, n):
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    sessions = [maker() for _ in range(n)]
    factors = [mfaService.getFactor(s, user) for s in sessions]  # todas leen el factor ANTES de que alguna confirme
    results = []
    for session, factor in zip(sessions, factors):
        try:
            mfaService.verifyFactor(session, factor, code, None)
            results.append("ACEPTADO")
        except AuthError as error:
            results.append(error.code)
        session.close()
    return results


def test_lecturas_simultaneas_no_superan_el_limite_de_intentos(db, engine, mails):
    user = makeUser(db)
    secret = enableMfa(db, user)
    results = concurrentFailures(engine, user, wrongCode(secret), 12)
    assert results.count("CODIGO_INVALIDO") == 4 and results.count("MFA_BLOQUEADO") == 8, results  # 4 contados; el 5.º bloquea; el resto, rechazado
    db.expire_all()
    factor = mfaService.getFactor(db, user)
    assert factor.intentosFallidosConsecutivos == mfaService.MAX_FAILED_MFA_ATTEMPTS and factor.bloqueadoHasta is not None
    with pytest.raises(AuthError) as late:  # bloqueado: ni siquiera el código correcto se acepta
        mfaService.verifyFactor(db, factor, totpCode(secret), None)
    assert late.value.code == "MFA_BLOQUEADO"


def test_un_totp_correcto_no_se_acepta_si_otra_solicitud_bloqueo_el_factor(db, engine, mails):
    """Carrera: la solicitud B leyó el factor sin bloqueo; A lo bloquea; B llega con un TOTP correcto y debe ser rechazada."""
    user = makeUser(db)
    secret = enableMfa(db, user)
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    late, stale = maker(), maker()
    staleFactor = mfaService.getFactor(stale, user)  # lectura anterior al bloqueo
    for _ in range(mfaService.MAX_FAILED_MFA_ATTEMPTS):
        with pytest.raises(AuthError):
            mfaService.verifyFactor(late, mfaService.getFactor(late, user), wrongCode(secret), None)
    assert staleFactor.bloqueadoHasta is None  # su vista está obsoleta
    with pytest.raises(AuthError) as error:
        mfaService.verifyFactor(stale, staleFactor, totpCode(secret), None)
    assert error.value.code == "MFA_BLOQUEADO"


def test_el_contador_se_reinicia_tras_un_bloqueo_vencido_y_con_un_exito(db, engine, mails):
    user = makeUser(db)
    secret = enableMfa(db, user)
    for _ in range(mfaService.MAX_FAILED_MFA_ATTEMPTS):
        with pytest.raises(AuthError):
            mfaService.verifyFactor(db, mfaService.getFactor(db, user), wrongCode(secret), None)
    db.execute(update(MfaFactor).where(MfaFactor.idUsuario == user.idUsuario).values(bloqueadoHasta=nowForDb()))  # el bloqueo venció
    db.commit()
    db.expire_all()
    with pytest.raises(AuthError) as again:  # un nuevo fallo empieza de 1, no bloquea de inmediato
        mfaService.verifyFactor(db, mfaService.getFactor(db, user), wrongCode(secret), None)
    assert again.value.code == "CODIGO_INVALIDO"
    db.expire_all()
    assert mfaService.getFactor(db, user).intentosFallidosConsecutivos == 1
    mfaService.verifyFactor(db, mfaService.getFactor(db, user), totpCode(secret), None)  # éxito: reinicia el contador
    db.commit()
    db.expire_all()
    assert mfaService.getFactor(db, user).intentosFallidosConsecutivos == 0
