# MfaRecovery - "Perdí acceso a mi aplicación autenticadora"
#
# Recuperación controlada (no es un atajo para desactivar MFA): parte del desafío MFA del login, es decir, de
# un primer factor recién validado, y exige además un código enviado al correo registrado de la cuenta.
#
#   1. start(challengeToken, password?)
#        - cuenta con CredencialLocal: vuelve a validar la contraseña actual (mismo bloqueo que el login);
#        - cuenta solo Google (sin CredencialLocal): el desafío debe venir de un ingreso con Google recién hecho;
#        - genera un código de 6 dígitos, TokenCuenta RECUPERACION_MFA (10 min, un solo uso, solo su HMAC),
#          invalida el pendiente anterior y lo envía al correo registrado (nunca a uno ingresado);
#        - devuelve un token de flujo (JWT de 15 min) y el correo enmascarado.
#   (Desde Seguridad, con sesión: startAccountRecovery / completeAccountRecovery, mismo código y mismas reglas;
#    se conserva la sesión actual y se revocan las demás.)
#   2. verify(recoveryToken, codigo)
#        - los códigos incorrectos usan el contador y bloqueo de FactorMfa (5 intentos);
#        - en una sola transacción: consume el token, borra FactorMfa y sus códigos de recuperación (no queda
#          ningún secreto TOTP reutilizable) y revoca todas las sesiones anteriores;
#        - después del commit crea la sesión nueva y avisa por correo (MFA_DESACTIVADO, porRecuperacion).
#
# Límites: un código por minuto y como máximo 3 por hora por cuenta (contados en TokenCuenta).

import hmac
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import jwt
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import getSettings
from app.core.exceptions import AuthError
from app.emails.eventTypes import EmailEventType
from app.emails.formatting import maskEmail
from app.models.accountToken import AccountToken, TipoTokenCuenta
from app.models.localCredential import LocalCredential
from app.models.mfaFactor import MfaFactor
from app.models.mfaRecoveryCode import MfaRecoveryCode
from app.models.user import User
from app.models.userSession import UserSession
from app.schemas.auth import LoginResponse
from app.services import auth as authService
from app.services import email as emailService
from app.services import mfa, userNotifications
from app.services.audit import registerEvent
from app.utils.timeZone import nowForDb
from app.utils.userAgent import ClientInfo

logger = logging.getLogger(__name__)

TOKEN_RECUPERACION_MFA = TipoTokenCuenta.RECUPERACION_MFA
CODE_VALIDITY_MINUTES = 10
RESEND_COOLDOWN_SECONDS = 60
MAX_CODES_PER_HOUR = 3

METHOD_PASSWORD = "pwd"  # nosec B105 - método del desafío, no una contraseña
METHOD_GOOGLE = "google"


@dataclass(frozen=True)
class RecoveryStart:
    recoveryToken: str
    correoEnmascarado: str
    vigenciaMinutos: int = CODE_VALIDITY_MINUTES


def _invalidFlow() -> AuthError:
    return AuthError("TOKEN_INVALIDO", "La recuperación venció o no es válida. Volvé a iniciar sesión.")


def _userWithMfa(db: Session, idUsuario: uuid.UUID) -> tuple[User, MfaFactor]:
    user = db.get(User, idUsuario)
    factor = mfa.getFactor(db, user) if user is not None else None
    if user is None or user.estado != "ACTIVO" or factor is None or not factor.habilitado:
        # Sin MFA activo no hay nada que recuperar (y no se revela el estado de la cuenta).
        raise _invalidFlow()
    return user, factor


def _decode(decoder, token: str) -> tuple[uuid.UUID, str]:
    try:
        claims = decoder(token)
        return uuid.UUID(claims["sub"]), claims.get("amr", [METHOD_PASSWORD])[0]
    except (jwt.InvalidTokenError, ValueError, KeyError) as error:
        raise _invalidFlow() from error


def _requireCodeAllowed(db: Session, idUsuario: uuid.UUID, now: datetime) -> None:
    recent = db.scalars(
        select(AccountToken.fechaCreacion).where(
            AccountToken.idUsuario == idUsuario,
            AccountToken.tipo == TOKEN_RECUPERACION_MFA,
            AccountToken.fechaCreacion > now - timedelta(hours=1),
        )
    ).all()
    if len(recent) >= MAX_CODES_PER_HOUR:
        raise AuthError("DEMASIADAS_SOLICITUDES", "Pediste varios códigos seguidos. Probá de nuevo en una hora.")
    if recent and max(recent) > now - timedelta(seconds=RESEND_COOLDOWN_SECONDS):
        raise AuthError("DEMASIADAS_SOLICITUDES", "Esperá un minuto antes de pedir un código nuevo.")


def _requireNotLocked(factor: MfaFactor) -> None:
    if factor.bloqueadoHasta is not None and factor.bloqueadoHasta > nowForDb():
        raise AuthError("MFA_BLOQUEADO", "Demasiados códigos inválidos. Intentá más tarde.")


def _revalidatePassword(db: Session, user: User, credential: LocalCredential, password: str | None) -> None:
    """Contraseña actual (mismo contador y bloqueo que el login). Un fallo se audita y no envía nada."""
    if not password:
        raise AuthError("PASSWORD_REQUERIDA", "Confirmá tu contraseña actual para continuar.")
    if not authService.verifyCurrentPassword(db, credential, password):
        registerEvent(db, "LOGIN", "MFA_RECUPERACION_SOLICITADA", False, user.idUsuario,
                      observacion="Contraseña incorrecta", motivo="PASSWORD_INCORRECTA")
        db.commit()
        raise AuthError("PASSWORD_INCORRECTA", "La contraseña ingresada no es correcta.")


def _issueAndSendCode(db: Session, user: User, verification: str, eventType: EmailEventType) -> str:
    """Genera el código (invalida el pendiente), lo envía al correo registrado y devuelve el correo enmascarado."""
    now = nowForDb()
    _requireCodeAllowed(db, user.idUsuario, now)
    # Un código nuevo invalida el pendiente anterior (se marca usado: sigue contando para el límite por hora).
    db.execute(
        update(AccountToken)
        .where(
            AccountToken.idUsuario == user.idUsuario,
            AccountToken.tipo == TOKEN_RECUPERACION_MFA,
            AccountToken.fechaUso.is_(None),
        )
        .values(fechaUso=now)
    )
    code = security.generateNumericCode()
    idToken = uuid.uuid4()
    db.add(
        AccountToken(
            idTokenCuenta=idToken,
            idUsuario=user.idUsuario,
            tipo=TOKEN_RECUPERACION_MFA,
            tokenHash=security.hashShortCode(TOKEN_RECUPERACION_MFA, user.idUsuario, idToken, code),
            fechaCreacion=now,
            fechaExpiracion=now + timedelta(minutes=CODE_VALIDITY_MINUTES),
        )
    )
    registerEvent(db, "LOGIN", "MFA_RECUPERACION_SOLICITADA", True, user.idUsuario, "Usuario", user.idUsuario,
                  datosNuevos={"verificacion": verification})
    authService.commitAccountToken(db, TOKEN_RECUPERACION_MFA)

    # Destinatario: siempre el correo registrado de la cuenta, nunca uno ingresado en el formulario.
    sent = emailService.sendEmailEvent(
        eventType,
        user.correoElectronico,
        {
            "nombre": user.nombre,
            "codigoSeguridad": code,
            "minutosValidez": CODE_VALIDITY_MINUTES,
            "urlSeguridad": emailService.frontendUrl("seguridad"),
            # Pedido desde Seguridad: perdió también los códigos de recuperación (cambia el texto del correo).
            "desvincular": eventType == EmailEventType.RECUPERACION_MFA_DESVINCULAR,
        },
    )
    registerEvent(db, "LOGIN", "MFA_RECUPERACION_CODIGO_ENVIADO", sent, user.idUsuario, "TokenCuenta", idToken,
                  observacion=None if sent else "Fallo en el envío del correo")
    db.commit()
    if not sent:
        raise AuthError("CORREO_NO_ENVIADO", "No pudimos enviarte el código. Intentá más tarde.")
    return maskEmail(user.correoElectronico)


def _localCredential(db: Session, user: User) -> LocalCredential | None:
    return db.scalar(select(LocalCredential).where(LocalCredential.idUsuario == user.idUsuario))


def startRecovery(db: Session, challengeToken: str, password: str | None) -> RecoveryStart:
    """Desde el paso MFA del login: revalida la identidad y envía el código al correo registrado."""
    idUsuario, method = _decode(security.decodeMfaChallengeToken, challengeToken)
    user, factor = _userWithMfa(db, idUsuario)
    _requireNotLocked(factor)

    credential = _localCredential(db, user)
    if credential is not None:
        # Cuenta con contraseña local: siempre contraseña actual + correo, aunque haya ingresado con Google.
        _revalidatePassword(db, user, credential, password)
    elif method != METHOD_GOOGLE:
        # Cuenta solo Google: el primer factor válido es un ingreso con Google recién hecho (el desafío).
        raise AuthError("REAUTENTICACION_REQUERIDA", "Volvé a ingresar con Google para recuperar el acceso.")

    masked = _issueAndSendCode(
        db, user, "PASSWORD" if credential is not None else "GOOGLE", EmailEventType.RECUPERACION_MFA_CODIGO
    )
    return RecoveryStart(recoveryToken=security.createMfaRecoveryToken(user.idUsuario, method), correoEnmascarado=masked)


def startAccountRecovery(db: Session, user: User, password: str | None) -> tuple[str, int]:
    """Desde Seguridad (con sesión): perdió la aplicación y los códigos de recuperación.

    Exige la contraseña actual. Una cuenta solo Google no tiene contraseña y la sesión no prueba un ingreso
    reciente con Google: debe volver a ingresar con Google y recuperar desde el paso MFA del login.
    Devuelve (correo enmascarado, minutos de validez).
    """
    factor = mfa.getFactor(db, user)
    if factor is None or not factor.habilitado:
        raise AuthError("MFA_NO_CONFIGURADO", "La verificación en dos pasos no está activada.")
    _requireNotLocked(factor)
    credential = _localCredential(db, user)
    if credential is None:
        raise AuthError(
            "REAUTENTICACION_REQUERIDA",
            "Tu cuenta usa Google: cerrá sesión, volvé a ingresar con Google y elegí "
            "«¿Perdiste acceso a tu aplicación autenticadora?».",
        )
    _revalidatePassword(db, user, credential, password)
    return _issueAndSendCode(db, user, "PASSWORD", EmailEventType.RECUPERACION_MFA_DESVINCULAR), CODE_VALIDITY_MINUTES


def _registerWrongCode(db: Session, factor: MfaFactor, now: datetime) -> AuthError:
    """Mismo contador y bloqueo que los códigos TOTP (CK_FactorMfa_intentos: máximo 5)."""
    counted = mfa.registerFailedAttempt(db, factor, now)  # atómico: ver mfa.registerFailedAttempt
    if counted is None:  # otra solicitud ya bloqueó el factor: este intento no se cuenta
        db.rollback()
        return AuthError("MFA_BLOQUEADO", "Demasiados códigos inválidos. Intentá más tarde.")
    locked = counted
    if locked:
        # Bloqueado: el código pendiente deja de servir (hay que pedir otro después del bloqueo).
        db.execute(
            update(AccountToken)
            .where(
                AccountToken.idUsuario == factor.idUsuario,
                AccountToken.tipo == TOKEN_RECUPERACION_MFA,
                AccountToken.fechaUso.is_(None),
            )
            .values(fechaUso=now)
        )
    registerEvent(db, "LOGIN", "MFA_RECUPERACION_CODIGO_INVALIDO", False, factor.idUsuario, "FactorMfa",
                  factor.idFactorMfa, motivo="MFA_BLOQUEADO" if locked else "CODIGO_RECUPERACION_INVALIDO")
    db.commit()
    if locked:
        return AuthError("MFA_BLOQUEADO", "Demasiados códigos inválidos. Intentá más tarde.")
    return AuthError("CODIGO_INVALIDO", "El código ingresado no es válido.")


def _verifyCodeAndUnlink(db: Session, user: User, factor: MfaFactor, codigo: str, keepSessionId=None) -> None:
    """Valida el código y desvincula el MFA en una sola transacción; después envía el aviso de seguridad.

    Revoca todas las sesiones del usuario salvo keepSessionId (la sesión desde la que se hizo, si la hay).
    """
    now = nowForDb()
    _requireNotLocked(factor)
    pending = db.scalar(
        select(AccountToken)
        .where(
            AccountToken.idUsuario == user.idUsuario,
            AccountToken.tipo == TOKEN_RECUPERACION_MFA,
            AccountToken.fechaUso.is_(None),
        )
        .order_by(AccountToken.fechaCreacion.desc())
    )
    if pending is None:
        raise AuthError("CODIGO_INVALIDO", "El código ingresado no es válido. Solicitá uno nuevo.")
    if pending.fechaExpiracion <= now:
        raise AuthError("CODIGO_VENCIDO", "El código venció. Solicitá uno nuevo.")
    expected = security.hashShortCode(TOKEN_RECUPERACION_MFA, user.idUsuario, pending.idTokenCuenta, codigo.strip())
    legacy = security.hashShortCode(TOKEN_RECUPERACION_MFA, user.idUsuario, pending.idTokenCuenta, codigo.strip(), legacy=True)
    if not (hmac.compare_digest(expected, pending.tokenHash) | hmac.compare_digest(legacy, pending.tokenHash)):
        raise _registerWrongCode(db, factor, now)

    try:
        consumed = db.execute(
            update(AccountToken)
            .where(AccountToken.idTokenCuenta == pending.idTokenCuenta, AccountToken.fechaUso.is_(None))
            .values(fechaUso=now)
        )
        if consumed.rowcount != 1:
            db.rollback()
            raise AuthError("CODIGO_INVALIDO", "El código ingresado no es válido. Solicitá uno nuevo.")
        idFactor = factor.idFactorMfa
        # Sin secreto TOTP reutilizable: se borran el factor (secreto cifrado) y sus códigos de recuperación.
        db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.idFactorMfa == idFactor))
        db.execute(delete(MfaFactor).where(MfaFactor.idFactorMfa == idFactor))
        # Operación sensible: ninguna otra sesión sigue siendo válida.
        sessions = update(UserSession).where(UserSession.idUsuario == user.idUsuario, UserSession.fechaRevocacion.is_(None))
        if keepSessionId is not None:
            sessions = sessions.where(UserSession.idSesion != keepSessionId)
        revoked = db.execute(sessions.values(fechaRevocacion=now)).rowcount
        registerEvent(db, "LOGIN", "MFA_RECUPERACION_COMPLETADA", True, user.idUsuario, "TokenCuenta",
                      pending.idTokenCuenta)
        registerEvent(db, "PERMISO", "MFA_DESHABILITADO_POR_RECUPERACION", True, user.idUsuario, "FactorMfa", idFactor,
                      datosNuevos={"mfa": "DESACTIVADO", "sesionesRevocadas": revoked})
        db.commit()
    except SQLAlchemyError:
        # Nada a medias: ni token consumido con MFA activo, ni MFA desactivado sin consumir el token.
        db.rollback()
        logger.error("No se pudo completar la recuperación de MFA de idUsuario=%s.", user.idUsuario)
        raise

    emailService.sendEmailEventInBackground(
        EmailEventType.MFA_DESACTIVADO,
        user.correoElectronico,
        {"nombre": user.nombre, "fechaEvento": now, "urlSeguridad": emailService.frontendUrl("seguridad"),
         "porRecuperacion": True},
    )
    userNotifications.notifySecurity(
        db, user, userNotifications.CAMBIO_MFA, "Cambio en la verificación en dos pasos",
        "Se desactivó la verificación en dos pasos de tu cuenta con un código de recuperación. Si no fuiste vos, revisá tu seguridad.",
        f"{now:%Y-%m-%dT%H:%M:%S.%f}")


def verifyRecovery(
    db: Session, recoveryToken: str, codigo: str, clientInfo: ClientInfo | None = None
) -> LoginResponse:
    """Desde el login: valida el código, desvincula el MFA perdido y abre una sesión nueva."""
    idUsuario, method = _decode(security.decodeMfaRecoveryToken, recoveryToken)
    user, factor = _userWithMfa(db, idUsuario)
    _verifyCodeAndUnlink(db, user, factor, codigo)
    label = "Recuperación de acceso (correo + " + ("contraseña" if method == METHOD_PASSWORD else "Google") + ")"
    # Este camino SÍ abre una sesión (MFA_RECUPERACION_COMPLETADA, en cambio, también la deja la recuperación hecha desde Seguridad, que no abre ninguna):
    # el ingreso queda como su propio evento, el mismo criterio que LOGIN_<método>_MFA, y lo cuenta el tablero de accesos (services/authAccess.py).
    registerEvent(db, "LOGIN", authService.ACCION_LOGIN_RECUPERACION_MFA, True, user.idUsuario, datosNuevos={"primerFactor": method})
    return authService.issueSession(db, user, label, clientInfo)


def completeAccountRecovery(db: Session, user: User, idSesion: uuid.UUID, codigo: str) -> None:
    """Desde Seguridad: valida el código y desvincula el MFA. Conserva la sesión actual y revoca las demás."""
    factor = mfa.getFactor(db, user)
    if factor is None or not factor.habilitado:
        raise AuthError("MFA_NO_CONFIGURADO", "La verificación en dos pasos no está activada.")
    _verifyCodeAndUnlink(db, user, factor, codigo, keepSessionId=idSesion)


def pendingCount(db: Session, idUsuario: uuid.UUID) -> int:
    """Códigos de recuperación pendientes (uso en pruebas y diagnóstico)."""
    return db.scalar(
        select(func.count())
        .select_from(AccountToken)
        .where(
            AccountToken.idUsuario == idUsuario,
            AccountToken.tipo == TOKEN_RECUPERACION_MFA,
            AccountToken.fechaUso.is_(None),
        )
    )
