# Mfa - Segundo factor TOTP opcional (ampliación del diseño; tablas FactorMfa y CodigoRecuperacionMfa)
#
# Un usuario tiene MFA habilitado cuando su FactorMfa tiene habilitado = 1. El factor se aplica
# después de cualquier autenticación primaria (local o Google) y es independiente del MFA que
# pueda tener la cuenta de Google.

from datetime import timedelta

from sqlalchemy import and_, case, delete, null, or_, select, update
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from app.core import security
from app.core.config import getSettings
from app.core.exceptions import AuthError
from app.emails.eventTypes import EmailEventType
from app.models.mfaFactor import MfaFactor
from app.models.mfaRecoveryCode import MfaRecoveryCode
from app.models.user import User
from app.services import email as emailService
from app.services import auditClassification, userNotifications
from app.services.audit import registerEvent, singleInstitutionOf
from app.utils.timeZone import nowForDb

# Límite de CK_FactorMfa_intentos.
MAX_FAILED_MFA_ATTEMPTS = 5


def _notify(eventType: EmailEventType, user: User, **context) -> None:
    """Aviso de seguridad al titular, en segundo plano."""
    emailService.sendEmailEventInBackground(
        eventType,
        user.correoElectronico,
        {"nombre": user.nombre, "urlSeguridad": emailService.frontendUrl("seguridad"), **context},
    )


def _mfaNotice(db: Session, user: User, mensaje: str, when) -> None:
    """Alerta crítica en la página (no se puede apagar); el correo MFA_ACTIVADO / MFA_DESACTIVADO ya salió por su propio flujo."""
    userNotifications.notifySecurity(
        db, user, userNotifications.CAMBIO_MFA, "Cambio en la verificación en dos pasos",
        f"{mensaje} Si no fuiste vos, revisá tu seguridad.", f"{when:%Y-%m-%dT%H:%M:%S.%f}")


def getFactor(db: Session, user: User) -> MfaFactor | None:
    return db.scalar(select(MfaFactor).where(MfaFactor.idUsuario == user.idUsuario))


def isEnabled(db: Session, user: User) -> bool:
    factor = getFactor(db, user)
    return factor is not None and factor.habilitado


def _requireMfaAvailable() -> None:
    if not getSettings().mfaEnabled:
        raise AuthError("MFA_NO_DISPONIBLE", "MFA no está disponible en este servidor.")


def startSetup(db: Session, user: User) -> tuple[str, str]:
    """Genera (o regenera) un secreto pendiente de confirmación. Devuelve (secreto, otpauthUri)."""
    _requireMfaAvailable()
    factor = getFactor(db, user)
    if factor is not None and factor.habilitado:
        raise AuthError("MFA_YA_HABILITADO", "MFA ya está habilitado.")

    secret = security.generateTotpSecret()
    if factor is None:
        factor = MfaFactor(idUsuario=user.idUsuario)
        db.add(factor)
    factor.secretoCifrado = security.encryptTotpSecret(secret)
    factor.ultimoPasoUsado = None
    factor.intentosFallidosConsecutivos = 0
    factor.bloqueadoHasta = None
    db.commit()

    accountName = user.correoElectronico or user.usuario or str(user.idUsuario)
    return secret, security.totpProvisioningUri(secret, accountName)


def enable(db: Session, user: User, codigo: str) -> list[str]:
    """Confirma el alta con un código TOTP válido y devuelve los códigos de recuperación."""
    _requireMfaAvailable()
    factor = getFactor(db, user)
    if factor is None:
        raise AuthError("MFA_NO_CONFIGURADO", "Primero hay que iniciar la configuración de MFA.")
    if factor.habilitado:
        raise AuthError("MFA_YA_HABILITADO", "MFA ya está habilitado.")

    verifyFactor(db, factor, codigo=codigo, codigoRecuperacion=None)

    now = nowForDb()
    factor.habilitado = True
    factor.fechaConfirmacion = now
    codes = _replaceRecoveryCodes(db, factor)
    registerEvent(db, "PERMISO", "MFA_HABILITADO", True, user.idUsuario, "FactorMfa", factor.idFactorMfa)
    db.commit()
    _notify(EmailEventType.MFA_ACTIVADO, user, fechaEvento=now, metodo=factor.tipo)
    _mfaNotice(db, user, "Activaste la verificación en dos pasos en tu cuenta.", now)
    return codes


def disable(db: Session, user: User, codigo: str | None, codigoRecuperacion: str | None) -> None:
    """Deshabilita MFA; exige un código TOTP o de recuperación válido."""
    _requireMfaAvailable()
    factor = getFactor(db, user)
    if factor is None or not factor.habilitado:
        raise AuthError("MFA_NO_CONFIGURADO", "MFA no está habilitado.")

    verifyFactor(db, factor, codigo=codigo, codigoRecuperacion=codigoRecuperacion)

    db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.idFactorMfa == factor.idFactorMfa))
    db.delete(factor)
    registerEvent(db, "PERMISO", "MFA_DESHABILITADO", True, user.idUsuario, "FactorMfa", factor.idFactorMfa)
    db.commit()
    now = nowForDb()
    _notify(EmailEventType.MFA_DESACTIVADO, user, fechaEvento=now)
    _mfaNotice(db, user, "Se desactivó la verificación en dos pasos de tu cuenta.", now)


def _noActiveLock(now):
    """Condición SQL: el factor no tiene un bloqueo vigente (nunca bloqueado o bloqueo vencido)."""
    return or_(MfaFactor.bloqueadoHasta.is_(None), MfaFactor.bloqueadoHasta <= now)


def registerFailedAttempt(db: Session, factor: MfaFactor, now) -> bool | None:
    """Suma un código inválido de forma ATÓMICA y, al llegar a MAX_FAILED_MFA_ATTEMPTS, activa el bloqueo temporal.

    Es un único UPDATE condicionado en la base (como el contador de contraseña del login): solicitudes simultáneas no se pisan el
    contador, así que el límite de intentos vale aunque lleguen en paralelo. Devuelve True si ESTE intento activó el bloqueo, False
    si solo se contó, y None si otra solicitud ya había bloqueado el factor (el intento no se cuenta). Un contador que quedó de un
    bloqueo vencido o en el máximo sin bloqueo vigente se reinicia. No confirma: quien llama hace commit."""
    lockUntil = now + timedelta(minutes=getSettings().AUTH_LOCKOUT_MINUTES)
    restart = or_(
        and_(MfaFactor.bloqueadoHasta.is_not(None), MfaFactor.bloqueadoHasta <= now),
        MfaFactor.intentosFallidosConsecutivos >= MAX_FAILED_MFA_ATTEMPTS,
    )
    newCount = case((restart, 1), else_=MfaFactor.intentosFallidosConsecutivos + 1)
    row = db.execute(
        update(MfaFactor)
        .where(MfaFactor.idFactorMfa == factor.idFactorMfa, _noActiveLock(now))
        .values(
            intentosFallidosConsecutivos=newCount,
            bloqueadoHasta=case((newCount >= MAX_FAILED_MFA_ATTEMPTS, lockUntil), else_=null()),
        )
        .returning(MfaFactor.intentosFallidosConsecutivos, MfaFactor.bloqueadoHasta)
        .execution_options(synchronize_session=False)
    ).first()
    if row is None:
        return None
    set_committed_value(factor, "intentosFallidosConsecutivos", row[0])
    set_committed_value(factor, "bloqueadoHasta", row[1])
    return row[1] is not None


def verifyFactor(db: Session, factor: MfaFactor, codigo: str | None, codigoRecuperacion: str | None) -> None:
    """Valida un código TOTP o de recuperación.

    Aplica bloqueo temporal tras MAX_FAILED_MFA_ATTEMPTS fallos y rechaza reutilizar un código
    TOTP ya aceptado. En caso de fallo confirma el contador y lanza AuthError; en caso de éxito
    deja los cambios pendientes para que quien llama haga commit.
    """
    _requireMfaAvailable()
    now = nowForDb()
    if factor.bloqueadoHasta is not None:
        if factor.bloqueadoHasta > now:
            # Intento durante el bloqueo: no se procesa el código, pero queda constancia de que ocurrió.
            registerEvent(db, "LOGIN", "MFA_CODIGO_INVALIDO", False, factor.idUsuario, "FactorMfa", factor.idFactorMfa,
                          motivo="MFA_BLOQUEADO", idInstitucion=singleInstitutionOf(db, factor.idUsuario),
                          observacion="Intento con el segundo factor bloqueado")
            db.commit()
            raise AuthError("MFA_BLOQUEADO", "Demasiados códigos inválidos. Intentá más tarde.")
        # Bloqueo vencido: el contador se reinicia en SQL (registerFailedAttempt) o al aceptar un código; no se toca acá para no
        # pisar con un valor viejo lo que escriba una solicitud simultánea.

    accepted = False
    if codigo is not None:
        step = security.matchTotpStep(security.decryptTotpSecret(factor.secretoCifrado), codigo)
        if step is not None:
            # Actualización condicional: un mismo intervalo solo se acepta una vez, incluso con
            # requests concurrentes.
            result = db.execute(
                update(MfaFactor)
                .where(
                    MfaFactor.idFactorMfa == factor.idFactorMfa,
                    or_(MfaFactor.ultimoPasoUsado.is_(None), MfaFactor.ultimoPasoUsado < step),
                    _noActiveLock(now),  # un factor bloqueado (también por una solicitud simultánea) no acepta ningún código
                )
                .values(ultimoPasoUsado=step)
            )
            accepted = result.rowcount == 1
    elif codigoRecuperacion is not None and factor.habilitado:
        result = db.execute(
            update(MfaRecoveryCode)
            .where(
                MfaRecoveryCode.idFactorMfa == factor.idFactorMfa,
                MfaRecoveryCode.codigoHash == security.hashRecoveryCode(codigoRecuperacion),
                MfaRecoveryCode.fechaUso.is_(None),
                MfaRecoveryCode.idFactorMfa.in_(select(MfaFactor.idFactorMfa).where(
                    MfaFactor.idFactorMfa == factor.idFactorMfa, _noActiveLock(now))),
            )
            .values(fechaUso=now)
        )
        accepted = result.rowcount == 1

    if accepted:
        factor.intentosFallidosConsecutivos = 0
        factor.bloqueadoHasta = None
        return

    counted = registerFailedAttempt(db, factor, now)
    if counted is None:  # otra solicitud bloqueó el factor mientras tanto: este intento no se cuenta
        db.rollback()
        raise AuthError("MFA_BLOQUEADO", "Demasiados códigos inválidos. Intentá más tarde.")
    locked = counted
    institution = singleInstitutionOf(db, factor.idUsuario)
    registerEvent(db, "LOGIN", "MFA_CODIGO_INVALIDO", False, factor.idUsuario, "FactorMfa", factor.idFactorMfa,
                  motivo="CODIGO_RECUPERACION_INVALIDO" if codigo is None else "CODIGO_MFA_INVALIDO", idInstitucion=institution)
    if locked:
        registerEvent(db, "LOGIN", auditClassification.ACCION_BLOQUEO_CUENTA, False, factor.idUsuario, "FactorMfa", factor.idFactorMfa,
                      motivo="MFA_BLOQUEADO", idInstitucion=institution, modulo="SEGURIDAD",
                      observacion="Bloqueo temporal del segundo factor por códigos incorrectos seguidos")
    db.commit()
    if locked:
        user = db.get(User, factor.idUsuario)
        if user is not None:
            _notify(
                EmailEventType.INTENTO_ACCESO_INUSUAL, user, fechaEvento=now,
                motivo="Se ingresaron varios códigos de verificación incorrectos al intentar acceder a tu cuenta.",
                bloqueadoHasta=factor.bloqueadoHasta,
            )
            userNotifications.notifySecurity(
                db, user, userNotifications.ACTIVIDAD_SOSPECHOSA, "Códigos de verificación incorrectos",
                "Se ingresaron varios códigos de verificación incorrectos al intentar entrar a tu cuenta y la bloqueamos unos minutos. "
                "Si no fuiste vos, revisá tu seguridad.",
                f"BLOQUEO_MFA:{factor.bloqueadoHasta}",  # sin formato: nunca puede romper el rechazo del acceso
            )
        raise AuthError("MFA_BLOQUEADO", "Demasiados códigos inválidos. Intentá más tarde.")
    raise AuthError("CODIGO_INVALIDO", "Código inválido.")


def _replaceRecoveryCodes(db: Session, factor: MfaFactor) -> list[str]:
    db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.idFactorMfa == factor.idFactorMfa))
    codes = [security.generateRecoveryCode() for _ in range(security.RECOVERY_CODE_COUNT)]
    db.add_all(
        MfaRecoveryCode(idFactorMfa=factor.idFactorMfa, codigoHash=security.hashRecoveryCode(code))
        for code in codes
    )
    return codes
