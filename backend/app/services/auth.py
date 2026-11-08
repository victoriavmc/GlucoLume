# Auth - Autenticación de GlucoLume
#
# Casos de identidad:
#   1. Solo local:   Usuario + CredencialLocal          -> correo/username + contraseña.
#   2. Solo Google:  Usuario + IdentidadExterna(GOOGLE) -> sin contraseña local.
#   3. Unificada:    Usuario + CredencialLocal + IdentidadExterna -> ambos accesos, mismo idUsuario.
#
# Vinculación automática con Google (RF04 / RN05): solo si Google informa email_verified y el
# correo coincide con el correoElectronico del Usuario. Además se exige que el Usuario esté ACTIVO
# (su correo ya fue verificado en GlucoLume) para evitar la apropiación de una cuenta creada con
# un correo ajeno sin verificar.
#
# Después de la autenticación primaria se aplica MFA si el usuario lo tiene habilitado.

import logging
import math
import re
import uuid
from datetime import datetime, timedelta
from typing import get_args

import jwt
from sqlalchemy import and_, delete, desc, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from app.core import requestContext, security
from app.core.config import getSettings
from app.core.exceptions import AuthError
from app.emails.eventTypes import EmailEventType
from app.integrations.google.oauth import GOOGLE_PROVIDER, GoogleIdentity
from app.models.accountToken import TOKEN_TYPE_CHECK_NAME, AccountToken, TipoTokenCuenta
from app.models.externalIdentity import ExternalIdentity
from app.models.localCredential import LocalCredential
from app.models.localCredentialHistory import LocalCredentialHistory
from app.models.user import User
from app.models.userSession import UserSession
from app.schemas.auth import (
    PASSWORD_PERSONAL_DATA_ERROR,
    AccountResponse,
    GracePeriodRead,
    LoginResponse,
    RegisterRequest,
    TokenPair,
)
from app.schemas.user import USERNAME_MIN_LENGTH, TipoCuentaPublica, UserRead
from app.services import email as emailService
from app.services.rateLimiter import RateLimiter
from app.models.consent import TipoConsentimiento
from app.services import accountGrace
from app.services import consent as consentService
from app.services import invitedAccounts, knownAccess, loginThrottle, mfa, unverifiedAccounts
from app.services import user as userService
from app.services import userNotifications
from app.services import adminAccessAlerts, auditClassification, schemaCompat
from app.services.adminAccessAlerts import TIPO_CONTRASENA, TIPO_GOOGLE, TIPO_SEGUNDO_FACTOR
from app.services.audit import hashIdentifier, registerEvent, singleInstitutionOf
from app.utils.normalizers import normalizeEmail, normalizeProperName
from app.utils.timeZone import nowForDb
from app.utils.userAgent import ClientInfo

logger = logging.getLogger(__name__)

# Límite de CK_CredencialLocal_intentos.
ACCOUNT_LOCKED_MESSAGE = "Demasiados intentos fallidos. Intentá más tarde."
# Contraseñas anteriores (además de la vigente) que no se pueden volver a usar al cambiarla.
PASSWORD_HISTORY_SIZE = 3

ESTADO_ACTIVO = "ACTIVO"
ESTADO_PENDIENTE = "PENDIENTE"
ESTADO_ELIMINADO = "ELIMINADO"
# Constantes de tipo y método (no son secretos; falsos positivos de bandit B105).
TOKEN_VERIFICACION_EMAIL = TipoTokenCuenta.VERIFICACION_EMAIL
# Código de un solo uso que entrega el callback de Google al frontend (006_intercambio_google.sql).
TOKEN_INTERCAMBIO_GOOGLE = TipoTokenCuenta.INTERCAMBIO_GOOGLE
GOOGLE_EXCHANGE_CODE_SECONDS = 120

# Tipos de cuenta del registro público (mismos valores que CK_Usuario_tipoCuenta).
PUBLIC_ACCOUNT_TYPES = frozenset(get_args(TipoCuentaPublica))
# Una cuenta nueva creada con Google es siempre CONSUMIDOR_FINAL; nunca un tipo de plataforma.

ACCION_LOGIN_RECUPERACION_MFA = "LOGIN_RECUPERACION_MFA"  # ingreso por la recuperación del segundo factor (services/mfaRecovery.py)
ACCION_LOGIN_ACTIVACION = "LOGIN_ACTIVACION_CUENTA"  # primera sesión al activar la cuenta con el enlace del correo (accountActivation.py, platform.py)
METHOD_PASSWORD = "pwd"  # nosec B105
METHOD_GOOGLE = "google"
_METHOD_LABELS = {METHOD_PASSWORD: "Correo o usuario y contraseña", METHOD_GOOGLE: "Cuenta de Google"}


def _notify(eventType: EmailEventType, user: User, **context) -> None:
    """Aviso por correo al titular de la cuenta, en segundo plano (no demora ni rompe el flujo)."""
    emailService.sendEmailEventInBackground(
        eventType, user.correoElectronico, {"nombre": user.nombre, **context}
    )


def _securityUrl(user: User) -> str:
    return emailService.urlSeguridad(user.tipoCuenta)


def _passwordNotice(db: Session, user: User, mensaje: str, when: datetime) -> None:
    """Aviso de seguridad en la página. El correo PASSWORD_CAMBIADA sale por su propio flujo, si la cuenta lo eligió."""
    userNotifications.notifySecurity(
        db, user, userNotifications.CAMBIO_CONTRASENA, "Cambio de contraseña",
        f"{mensaje} Si no fuiste vos, recuperá el acceso y revisá tu seguridad.", f"{when:%Y-%m-%dT%H:%M:%S.%f}")


# --- Consultas ---------------------------------------------------------------------------


def _findUserByEmail(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.correoElectronico == email))


def _findUserByIdentifier(db: Session, identificador: str) -> User | None:
    identificador = identificador.strip()
    if "@" in identificador:
        return _findUserByEmail(db, normalizeEmail(identificador))
    return db.scalar(select(User).where(User.usuario == identificador))


def _getLocalCredential(db: Session, user: User) -> LocalCredential | None:
    return db.scalar(select(LocalCredential).where(LocalCredential.idUsuario == user.idUsuario))


def _getGoogleIdentity(db: Session, user: User) -> ExternalIdentity | None:
    return db.scalar(
        select(ExternalIdentity).where(
            ExternalIdentity.idUsuario == user.idUsuario, ExternalIdentity.proveedor == GOOGLE_PROVIDER
        )
    )


def _ensureActive(user: User) -> None:
    if user.estado == ESTADO_PENDIENTE:
        raise AuthError("CORREO_NO_VERIFICADO", "Verificá tu correo electrónico para iniciar sesión.")
    if user.estado != ESTADO_ACTIVO:
        raise AuthError("CUENTA_NO_ACTIVA", "La cuenta no está activa.")


# --- Registro y verificación de correo --------------------------------------------------


def _requirePublicAccountType(tipoCuenta: str) -> str:
    """Segunda barrera (además del schema): el registro público nunca crea cuentas de plataforma."""
    if tipoCuenta not in PUBLIC_ACCOUNT_TYPES:
        raise AuthError("TIPO_CUENTA_INVALIDO", "Tipo de cuenta no permitido.")
    return tipoCuenta


def _requirePasswordPolicy(password: str, *identifiers: str | None) -> None:
    """Segunda barrera (además del schema) para toda contraseña nueva."""
    errors = security.passwordPolicyErrors(password)
    if errors:
        raise AuthError("PASSWORD_DEBIL", "La contraseña debe tener " + ", ".join(errors) + ".")
    if security.isCommonPassword(password):
        raise AuthError("PASSWORD_DEBIL", security.COMMON_PASSWORD_ERROR)
    if security.passwordContainsPersonalData(password, *identifiers):
        raise AuthError("PASSWORD_DEBIL", PASSWORD_PERSONAL_DATA_ERROR)


def registerLocal(db: Session, data: RegisterRequest) -> User:
    """Caso 1: crea Usuario PENDIENTE + CredencialLocal y envía el correo de verificación.

    tipoCuenta USUARIO_INSTITUCIONAL solo marca la cuenta: no crea instituciones ni vínculos. Una cuenta
    institucional crea una institución o es incorporada a una existente después (app/services/institution.py).
    """
    tipoCuenta = _requirePublicAccountType(data.tipoCuenta)
    consentService.requirePolicyAccepted(data.aceptaPoliticaPrivacidad)  # validación de backend, no solo del frontend
    _requirePasswordPolicy(
        data.password.get_secret_value(), data.usuario, data.correoElectronico, data.nombre, data.apellido
    )
    # Una cuenta pendiente vencida no retiene el correo ni el username: se elimina y se liberan.
    existingByEmail = _findUserByEmail(db, data.correoElectronico)
    if existingByEmail is not None and invitedAccounts.isInvitedPendingAccount(db, existingByEmail):
        raise AuthError("CORREO_REGISTRADO", invitedAccounts.INVITED_ACCOUNT_MESSAGE)
    if existingByEmail is not None and not _purgeIfExpired(db, existingByEmail):
        raise AuthError("CORREO_REGISTRADO", "El correo electrónico ya está registrado.")
    if data.usuario is not None:
        existingByUsername = db.scalar(select(User).where(User.usuario == data.usuario))
        if existingByUsername is not None and not _purgeIfExpired(db, existingByUsername):
            raise AuthError("USUARIO_REGISTRADO", "El nombre de usuario ya está registrado.")
    # El correo debe existir antes de crear nada: sin buzón no hay forma de verificar la cuenta.
    emailService.requireMailboxExists(data.correoElectronico)

    user = User(
        nombre=data.nombre,
        apellido=data.apellido,
        usuario=data.usuario,
        correoElectronico=data.correoElectronico,
        tipoCuenta=tipoCuenta,
        estado=ESTADO_PENDIENTE,
    )
    db.add(user)
    try:
        db.flush()
        db.add(
            LocalCredential(
                idUsuario=user.idUsuario,
                passwordHash=security.hashPassword(data.password.get_secret_value()),
            )
        )
        consentService.record(db, user, TipoConsentimiento.POLITICA_PRIVACIDAD, True)
        registerEvent(
            db, "CRUD", "REGISTRO_LOCAL", True, user.idUsuario, "Usuario", user.idUsuario,
            observacion=f"Tipo de cuenta: {tipoCuenta}",
        )
        db.commit()
    except IntegrityError as error:
        # Carrera contra los índices únicos de correo/usuario.
        db.rollback()
        raise AuthError("CORREO_REGISTRADO", "El correo electrónico o el usuario ya están registrados.") from error

    _sendVerificationEmail(db, user)
    return user


def _purgeIfExpired(db: Session, user: User) -> bool:
    """Si la cuenta es local, pendiente y venció su plazo de verificación, la elimina. True si la eliminó."""
    if not unverifiedAccounts.isVerificationExpired(user):
        return False
    return unverifiedAccounts.deleteExpiredAccount(db, user.idUsuario)


def _verificationExpiredError() -> AuthError:
    return AuthError(
        "VERIFICACION_EXPIRADA",
        "El plazo para verificar la cuenta venció y la cuenta fue eliminada. Registrate nuevamente.",
    )


def _sendVerificationEmail(db: Session, user: User) -> tuple[AccountToken, bool]:
    """Genera un token de verificación nuevo, invalida los anteriores y envía el correo.

    El token vence en el límite de la cuenta (fechaCreacion + plazo): reenviar no extiende el plazo.
    Devuelve (token, enviado).
    """
    settings = getSettings()
    deadline = unverifiedAccounts.verificationDeadline(user)
    db.execute(
        delete(AccountToken).where(
            AccountToken.idUsuario == user.idUsuario,
            AccountToken.tipo == TOKEN_VERIFICACION_EMAIL,
            AccountToken.fechaUso.is_(None),
        )
    )
    token = security.generateOpaqueToken()
    accountToken = AccountToken(
        idUsuario=user.idUsuario,
        tipo=TOKEN_VERIFICACION_EMAIL,
        tokenHash=security.hashOpaqueToken(token),
        fechaCreacion=nowForDb(),  # hora de Argentina: la usa el intervalo mínimo entre reenvíos (el DEFAULT de la columna es UTC)
        fechaExpiracion=deadline,
    )
    db.add(accountToken)
    commitAccountToken(db, accountToken.tipo)

    sent = emailService.sendEmailEvent(
        EmailEventType.EMAIL_VERIFICACION,
        user.correoElectronico,
        {
            "nombre": user.nombre,
            "urlVerificacion": f"{emailService.frontendUrl('verificarCorreo')}?token={token}",
            "fechaExpiracion": deadline,
            "plazoHoras": settings.EMAIL_VERIFICATION_EXPIRE_HOURS,
        },
    )
    # Si el envío falla, el registro no se revierte: el usuario puede pedir un nuevo correo.
    return accountToken, sent


def commitAccountToken(db: Session, tipo: str) -> None:
    """Confirma la creación de un TokenCuenta. Ante un error hace rollback y registra la causa real.

    Si SQL Server rechaza el tipo por CK_TokenCuenta_tipo, la base instalada no tiene el CHECK vigente de
    database/reference/GlucoLume_DB_v5.sql (ver TipoTokenCuenta en app/models/accountToken.py).
    """
    try:
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        if TOKEN_TYPE_CHECK_NAME.lower() in str(getattr(error, "orig", error)).lower():
            logger.error(
                "SQL Server rechazó TokenCuenta.tipo=%s por %s: la base instalada no tiene el CHECK vigente "
                "de database/reference/GlucoLume_DB_v5.sql; recrearlo con la lista completa.",
                tipo, TOKEN_TYPE_CHECK_NAME,
            )
        else:
            logger.error("No se pudo guardar TokenCuenta.tipo=%s (%s).", tipo, type(error).__name__)
        raise


# Un correo de verificación nuevo no se emite antes de este plazo (el primero lo envía el registro).
VERIFICATION_RESEND_MIN_INTERVAL_SECONDS = 60


def resendVerification(db: Session, email: str) -> None:
    """Reenvía el correo de verificación a una cuenta local pendiente.

    La respuesta es idéntica exista o no la cuenta, esté verificada, inactiva o vencida (no revela qué correos están registrados),
    igual que «Olvidé mi contraseña»; solo una cuenta pendiente recibe correo. Un nuevo correo no sale antes de
    VERIFICATION_RESEND_MIN_INTERVAL_SECONDS: el formulario no sirve para inundar de correos a un tercero que no pidió nada. La
    cuenta creada por una invitación institucional sigue recibiendo la indicación de activarla (ACTIVACION_PENDIENTE).
    """
    user = _findUserByEmail(db, email)
    if user is None or user.estado != ESTADO_PENDIENTE:
        return
    if invitedAccounts.isInvitedPendingAccount(db, user):
        raise AuthError("ACTIVACION_PENDIENTE", invitedAccounts.INVITED_ACCOUNT_MESSAGE)
    if _purgeIfExpired(db, user):
        return
    recent = db.scalar(
        select(AccountToken.idTokenCuenta).where(
            AccountToken.idUsuario == user.idUsuario,
            AccountToken.tipo == TOKEN_VERIFICACION_EMAIL,
            AccountToken.fechaUso.is_(None),
            AccountToken.fechaCreacion > nowForDb() - timedelta(seconds=VERIFICATION_RESEND_MIN_INTERVAL_SECONDS),
        )
    )
    if recent is not None:
        return

    accountToken, sent = _sendVerificationEmail(db, user)
    registerEvent(
        db, "CRUD", "VERIFICACION_REENVIADA", sent, user.idUsuario, "TokenCuenta", accountToken.idTokenCuenta,
        observacion=None if sent else "Fallo en el envío del correo",
    )
    db.commit()
    if not sent:
        raise AuthError("CORREO_NO_ENVIADO", "No se pudo enviar el correo de verificación. Intentá más tarde.")


def verifyEmail(db: Session, token: str) -> None:
    now = nowForDb()
    invalid = AuthError("TOKEN_INVALIDO", "El enlace de verificación es inválido o venció.")
    accountToken = db.scalar(
        select(AccountToken).where(
            AccountToken.tokenHash == security.hashOpaqueToken(token),
            AccountToken.tipo == TOKEN_VERIFICACION_EMAIL,
            AccountToken.fechaUso.is_(None),
        )
    )
    user = db.get(User, accountToken.idUsuario) if accountToken else None
    if user is None or user.estado not in (ESTADO_PENDIENTE, ESTADO_ACTIVO):
        raise invalid
    if _purgeIfExpired(db, user):
        raise _verificationExpiredError()
    if accountToken.fechaExpiracion <= now:
        raise invalid

    accountToken.fechaUso = now
    if user.estado == ESTADO_PENDIENTE:
        # Activación condicional en la misma transacción: si la limpieza eliminó la cuenta en paralelo,
        # o el plazo venció entre la lectura y la escritura, no se activa.
        activated = db.execute(
            update(User)
            .where(
                User.idUsuario == user.idUsuario,
                User.estado == ESTADO_PENDIENTE,
                User.fechaCreacion > now - unverifiedAccounts.verificationWindow(),
            )
            .values(estado=ESTADO_ACTIVO, fechaActualizacion=now)
        )
        if activated.rowcount != 1:
            db.rollback()
            raise invalid
        registerEvent(db, "CRUD", "CORREO_VERIFICADO", True, user.idUsuario, "Usuario", user.idUsuario)
        # Una cuenta institucional habilitada sin ninguna institución empieza su período de gracia: el correo de bienvenida informa la fecha.
        accountGrace.startIfOrphaned(db, user.idUsuario, now, user.idUsuario, accountGrace.ORIGEN_ALTA)
        db.commit()
        # La cuenta local queda creada recién al verificar el correo.
        _notify(
            EmailEventType.CUENTA_CREADA, user, apellido=user.apellido, fechaCreacion=user.fechaCreacion,
            urlIngreso=emailService.frontendUrl("ingreso"), **accountGrace.welcomeContext(user),
        )
        return
    db.commit()


# --- Autenticación primaria -------------------------------------------------------------


# Accesos de inicio de sesión (AccesoLogin en schemas/auth.py). Las cuentas de administración de GlucoLume solo entran por PLATAFORMA;
# el resto solo por GENERAL. Los roles de plataforma son los de platform.PLATFORM_ROLES; no se importan porque platform importa este módulo.
ACCESO_GENERAL = "GENERAL"
ACCESO_PLATAFORMA = "PLATAFORMA"
_CUENTAS_PLATAFORMA = ("ADMINISTRADOR_PLATAFORMA", "MODERADOR_PLATAFORMA")


def requireAccesoLogin(db: Session, user: User, acceso: str, accion: str) -> None:
    """La contraseña (o la identidad de Google) ya fue verificada, pero la cuenta solo entra por su acceso. Se audita y se rechaza antes de
    abrir la sesión o el desafío MFA: la regla no depende de lo que haga el cliente."""
    esPlataforma = user.tipoCuenta in _CUENTAS_PLATAFORMA
    if (acceso == ACCESO_PLATAFORMA) == esPlataforma:
        return
    if acceso == ACCESO_PLATAFORMA:
        _auditFailedLogin(db, accion, user, "SIN_ROL_PLATAFORMA", "Acceso administrativo con una cuenta sin rol de plataforma")
        db.commit()
        raise AuthError("ACCESO_PLATAFORMA_DENEGADO", "Esta cuenta no tiene acceso a la administración de la plataforma.")
    _auditFailedLogin(db, accion, user, "CUENTA_DE_PLATAFORMA", "Cuenta de administración de GlucoLume en el acceso general")
    db.commit()
    raise AuthError("ACCESO_PLATAFORMA_REQUERIDO", "Esta cuenta administra GlucoLume: ingresá por el acceso administrativo.")


def _auditFailedLogin(db: Session, accion: str, user: User | None, motivo: str, observacion: str | None = None,
                      identificador: str | None = None) -> None:
    """Deja constancia de un acceso fallido (el llamador confirma). `motivo` es un código estable, nunca texto libre ni lo que escribió la
    persona. Sin cuenta identificable (identificador inexistente) NO se guarda el identificador: solo un HMAC con clave del servidor, que
    permite ver que se repite sin conservar lo escrito. Con cuenta identificable y vinculada a UNA sola institución, el evento queda también en
    la auditoría de esa institución (el intento sobre una cuenta de su personal); la IP y el cliente nunca salen de la administración."""
    registerEvent(
        db, "LOGIN", accion, False, user.idUsuario if user is not None else None, observacion=observacion, motivo=motivo,
        idInstitucion=singleInstitutionOf(db, user.idUsuario) if user is not None else None,
        identificadorHash=hashIdentifier(identificador) if user is None and identificador else None,
    )


def _requireActive(db: Session, user: User, accion: str) -> None:
    """_ensureActive que además deja constancia: la contraseña (o la identidad de Google) fue correcta, pero la cuenta no puede entrar."""
    try:
        _ensureActive(user)
    except AuthError as error:
        db.rollback()
        _auditFailedLogin(db, accion, user, "CORREO_NO_VERIFICADO" if error.code == "CORREO_NO_VERIFICADO" else "CUENTA_INACTIVA",
                          observacion=f"Estado de la cuenta: {user.estado}")
        db.commit()
        raise


def _isLocked(credential: LocalCredential, now: datetime) -> bool:
    return credential.bloqueadoHasta is not None and credential.bloqueadoHasta > now


def _lockedError(bloqueadoHasta: datetime | None, now: datetime) -> AuthError:
    retryAfter = None
    if bloqueadoHasta is not None:
        retryAfter = max(1, math.ceil((bloqueadoHasta - now).total_seconds()))
    return AuthError("CUENTA_BLOQUEADA", ACCOUNT_LOCKED_MESSAGE, retryAfterSeconds=retryAfter)


def _withoutActiveLock(now: datetime):
    """Condición SQL: la credencial no tiene un bloqueo vigente (nunca bloqueada o bloqueo vencido)."""
    return or_(LocalCredential.bloqueadoHasta.is_(None), LocalCredential.bloqueadoHasta <= now)


def _setCommitted(credential: LocalCredential, **values) -> None:
    """Refleja en la instancia lo que ya escribió un UPDATE atómico (sin volver a marcarlo como cambio)."""
    for name, value in values.items():
        set_committed_value(credential, name, value)


# El contador y el bloqueo se modifican siempre con UPDATE condicionados ejecutados en la base: cada
# UPDATE toma el lock de la fila y evalúa la condición sobre el valor vigente, así dos solicitudes
# simultáneas no pisan el contador ni permiten superar el máximo de fallos.


def _unlockIfExpired(db: Session, credential: LocalCredential, now: datetime) -> None:
    """Desbloqueo lógico: si el bloqueo venció, el contador vuelve a 0 antes de evaluar el intento.

    No requiere un proceso programado: se aplica en el próximo intento. Deja el cambio pendiente de commit.
    """
    if credential.bloqueadoHasta is None or credential.bloqueadoHasta > now:
        return
    db.execute(
        update(LocalCredential)
        .where(
            LocalCredential.idCredencialLocal == credential.idCredencialLocal,
            LocalCredential.bloqueadoHasta.is_not(None),
            LocalCredential.bloqueadoHasta <= now,
        )
        .values(intentosFallidosConsecutivos=0, bloqueadoHasta=None, fechaActualizacion=now)
        .execution_options(synchronize_session=False)
    )
    _setCommitted(credential, intentosFallidosConsecutivos=0, bloqueadoHasta=None, fechaActualizacion=now)


def _raiseConcurrentLock(db: Session, credential: LocalCredential, now: datetime) -> None:
    db.refresh(credential)
    raise _lockedError(credential.bloqueadoHasta, now)


def _registerSuccessfulPassword(
    db: Session, credential: LocalCredential, now: datetime, newHash: str | None
) -> None:
    """Contraseña correcta: el contador vuelve a 0 (y se rehashea si corresponde).

    Si otra solicitud bloqueó la cuenta mientras tanto, el acceso se rechaza con CUENTA_BLOQUEADA.
    """
    values = {"intentosFallidosConsecutivos": 0, "bloqueadoHasta": None}
    if newHash:
        values["passwordHash"] = newHash
    if newHash or credential.intentosFallidosConsecutivos:
        values["fechaActualizacion"] = now
    result = db.execute(
        update(LocalCredential)
        .where(LocalCredential.idCredencialLocal == credential.idCredencialLocal, _withoutActiveLock(now))
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        _raiseConcurrentLock(db, credential, now)
    _setCommitted(credential, **values)


def previousPasswordError(db: Session, credential: LocalCredential, password: str) -> AuthError | None:
    """Por qué la contraseña nueva no sirve: es la vigente (PASSWORD_REPETIDA) o una de las últimas PASSWORD_HISTORY_SIZE
    anteriores (PASSWORD_ANTERIOR). Nunca se guarda ni se muestra la contraseña."""
    if security.verifyPassword(password, credential.passwordHash)[0]:
        return AuthError("PASSWORD_REPETIDA", "La contraseña nueva tiene que ser distinta de la actual.")
    previous = db.scalars(
        select(LocalCredentialHistory.passwordHash)
        .where(LocalCredentialHistory.idCredencialLocal == credential.idCredencialLocal)
        .order_by(desc(LocalCredentialHistory.fechaCreacion))
        .limit(PASSWORD_HISTORY_SIZE)
    ).all()
    if any(security.verifyPassword(password, oldHash)[0] for oldHash in previous):
        return AuthError("PASSWORD_ANTERIOR", "Es una contraseña vieja. Elegí una distinta.")
    return None


def replacePassword(db: Session, credential: LocalCredential, password: str, now: datetime) -> None:
    """Guarda el hash de la nueva contraseña y pasa la vigente al historial, del que se descartan las más antiguas.
    Deja los cambios pendientes de commit, como el resto de los cambios de CredencialLocal."""
    db.add(LocalCredentialHistory(
        idCredencialLocal=credential.idCredencialLocal, passwordHash=credential.passwordHash, fechaCreacion=now,
    ))
    db.flush()
    stale = db.scalars(
        select(LocalCredentialHistory.idCredencialLocalHistorial)
        .where(LocalCredentialHistory.idCredencialLocal == credential.idCredencialLocal)
        .order_by(desc(LocalCredentialHistory.fechaCreacion))
        .offset(PASSWORD_HISTORY_SIZE)
    ).all()
    if stale:
        db.execute(delete(LocalCredentialHistory).where(LocalCredentialHistory.idCredencialLocalHistorial.in_(stale)))
    credential.passwordHash = security.hashPassword(password)


# Reconfirmación de la contraseña dentro de una sesión o de un desafío ya abierto (verifyCurrentPassword). M-2, decisión aprobada:
# 3 fallos en 15 min bloquean SOLO esa operación para ese usuario. No escribe en la credencial, así que no afecta al login ni a las
# demás operaciones, y un tercero no puede dejar fuera a la cuenta. El contador vive en memoria (por proceso, o compartido con Redis).
MAX_FAILED_REAUTH_ATTEMPTS = 3
REAUTH_WINDOW_SECONDS = 15 * 60
REAUTH_LOCKED_MESSAGE = "Demasiados intentos de confirmar tu contraseña. Esperá unos minutos antes de intentarlo de nuevo."
_reautenticacion = RateLimiter(MAX_FAILED_REAUTH_ATTEMPTS, REAUTH_WINDOW_SECONDS, name="reautenticacion")


def _claveReautenticacion(credential: LocalCredential, operacion: str) -> str:
    return f"{credential.idUsuario}|{operacion}"


def verifyCurrentPassword(db: Session, credential: LocalCredential, password: str, operacion: str = "reautenticacion") -> bool:
    """Reautenticación con la contraseña actual para una operación sensible (dentro de la sesión o del desafío ya abiertos).

    Lanza CUENTA_BLOQUEADA si ESA operación para ESE usuario superó los fallos permitidos. Devuelve si la contraseña es correcta y deja
    los cambios pendientes: quien llama audita y confirma (también en el fallo, para que cuente el intento).
    """
    now = nowForDb()
    if _isLocked(credential, now):  # bloqueo heredado de la versión anterior (vence en 15 min como máximo): solo se respeta hasta vencer
        raise _lockedError(credential.bloqueadoHasta, now)
    _unlockIfExpired(db, credential, now)
    clave = _claveReautenticacion(credential, operacion)
    espera = _reautenticacion.retryAfter(clave)
    if espera > 0:
        raise AuthError("CUENTA_BLOQUEADA", REAUTH_LOCKED_MESSAGE, retryAfterSeconds=max(1, math.ceil(espera)))
    valid, newHash = security.verifyPassword(password, credential.passwordHash)
    if valid:
        _registerSuccessfulPassword(db, credential, now, newHash)
        return True
    _reautenticacion.allow(clave)  # cuenta el fallo en memoria: no depende de que la transacción del llamador confirme
    return False


def loginLocal(
    db: Session, identificador: str, password: str, clientInfo: ClientInfo | None = None, acceso: str = ACCESO_GENERAL
) -> LoginResponse:
    """Casos 1 y 3: correo o username + contraseña. Un ingreso rechazado que intenta entrar a la administración queda como alerta
    (_alertAdministratorAttempt); el rechazo llega igual al cliente."""
    try:
        return _loginLocal(db, identificador, password, clientInfo, acceso)
    except AuthError as error:
        if error.code != "SERVIDOR_OCUPADO":  # saturación del servidor (M-3): no es un intento contra la cuenta, no se alerta
            _alertAdministratorAttempt(db, _identifiedUser(db, identificador), acceso == ACCESO_PLATAFORMA, TIPO_CONTRASENA, error.code)
        raise


def reportSecondFactorRejection(db: Session, user: User, motivo: str) -> None:
    """Un código de recuperación rechazado (services/mfaRecovery.py) cuenta como intento de segundo factor contra la cuenta."""
    _alertAdministratorAttempt(db, user, False, TIPO_SEGUNDO_FACTOR, motivo)


def requireAccesoGoogle(db: Session, user: User, acceso: str) -> None:
    """requireAccesoLogin para el ingreso con Google. Un rechazo queda como intento de administración (si corresponde); una cancelación
    del flujo en Google no llega acá, así que no cuenta como ataque."""
    try:
        requireAccesoLogin(db, user, acceso, "LOGIN_GOOGLE")
    except AuthError as error:
        _alertAdministratorAttempt(db, user, acceso == ACCESO_PLATAFORMA, TIPO_GOOGLE, error.code)
        raise


def _identifiedUser(db: Session, identificador: str) -> User | None:
    """Usuario del identificador, o None si no existe o no se pudo consultar: la alerta nunca debe cambiar la respuesta del login."""
    try:
        return _findUserByIdentifier(db, identificador)
    except SQLAlchemyError:
        logger.exception("No se pudo identificar la cuenta de un intento rechazado")
        return None


def _alertAdministratorAttempt(db: Session, user: User | None, administrativo: bool, tipoAutenticacion: str, motivo: str) -> None:
    """Un ingreso rechazado es un intento contra la administración si la cuenta es de administrador o si el acceso pedido fue PLATAFORMA.
    Primero queda en la auditoría (SOSPECHOSO, salvo el acceso general de una cuenta de administración: ver abajo); después adminAccessAlerts
    decide si sale correo, con límite por ventana. Las cuentas inexistentes no se alertan: el identificador escrito no se guarda ni se envía
    (ver _auditFailedLogin). Nunca lanza."""
    try:
        if user is None or not (administrativo or user.tipoCuenta == "ADMINISTRADOR_PLATAFORMA"):
            return
        if motivo != "ACCESO_PLATAFORMA_REQUERIDO":
            # Una cuenta de administración que entra por el acceso general ya quedó auditada por requireAccesoLogin como un rechazo
            # operativo (LOGIN_*). No se repite como intento sospechoso: el aviso por correo sale igual.
            registerEvent(
                db, "LOGIN", auditClassification.ACCION_INTENTO_ACCESO_ADMIN, False, user.idUsuario, modulo="SEGURIDAD", motivo=motivo,
                observacion=f"Intento de ingreso a la administración de GlucoLume rechazado ({tipoAutenticacion})",
            )
            db.commit()
        context = requestContext.current()
        adminAccessAlerts.record(db, adminAccessAlerts.Attempt(
            correo=user.correoElectronico, tipoAutenticacion=tipoAutenticacion, motivo=motivo,
            ip=context.ip if context else None, fecha=nowForDb(),
        ))
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("No se pudo registrar el intento de ingreso a la administración")


def _loginLocal(
    db: Session, identificador: str, password: str, clientInfo: ClientInfo | None, acceso: str
) -> LoginResponse:
    """Cuerpo de loginLocal. `acceso` separa el login general del administrativo (requireAccesoLogin).

    Límite de intentos (M-2, auditoría 07/11/2026): la decisión (comprobar el límite, verificar la contraseña y registrar el fallo) se toma
    con exclusión mutua por (identificador, origen) (loginThrottle.exclusivo), para que una ráfaga simultánea no se salte el límite.
    """
    origen = loginThrottle.origenDe(clientInfo)
    with loginThrottle.exclusivo(identificador, origen):
        return _loginLocalBajoLimite(db, identificador, password, origen, acceso, clientInfo)


def _programarAviso(db: Session, tarea, *args) -> None:
    """Ejecuta un aviso al titular en segundo plano, con su propia sesión (ver emailService.runInBackground)."""
    emailService.runInBackground(tarea, db.get_bind(), *args)


def _sesionDeAviso(bind) -> Session:
    return Session(bind=bind, autoflush=False, expire_on_commit=False)


def _tareaFalloDeContrasena(bind, identificador: str, instante: datetime) -> None:
    """Aviso en la página por una contraseña incorrecta. Si no hay cuenta con ese identificador, no hace nada."""
    session = _sesionDeAviso(bind)
    try:
        user = _findUserByIdentifier(session, identificador)
        if user is not None:
            userNotifications.notifyRejectedAccess(session, user, instante)
    except Exception:  # noqa: BLE001 - un aviso que falla no cambia la respuesta ni deshace nada
        session.rollback()
        logger.exception("No se pudo registrar el aviso de contraseña incorrecta")
    finally:
        session.close()


def _tareaIntentoLimitado(bind, identificador: str, origen: str, instante: datetime) -> None:
    """Traza de un intento rechazado por el límite (M-2). Distinta de una contraseña incorrecta (título propio) y acotada: como mucho un
    aviso por cuenta, por origen y por ventana del límite, así un atacante no puede generar registros sin fin. El origen se guarda como HMAC."""
    session = _sesionDeAviso(bind)
    try:
        user = _findUserByIdentifier(session, identificador)
        if user is None:
            return
        segundos = int((instante - datetime(1970, 1, 1)).total_seconds())
        ventana = segundos // loginThrottle.LIMITES[0][2]
        clave = f"{userNotifications.INTENTO_INGRESO}:limite:{hashIdentifier(origen)}:{ventana}"
        userNotifications.notify(
            session, user, userNotifications.INTENTO_INGRESO,
            "Intento de ingreso bloqueado por seguridad",
            "Hubo intentos de entrar a tu cuenta desde un mismo lugar y los bloqueamos unos minutos. Si no fuiste vos, revisá tu seguridad.",
            url=userNotifications.URL_SEGURIDAD, clave=clave,
        )
    except Exception:  # noqa: BLE001
        session.rollback()
        logger.exception("No se pudo registrar el intento bloqueado por el límite")
    finally:
        session.close()


def _tareaAuditarIntentoLimitado(bind, identificador: str, origen: str) -> None:
    """Auditoría de CADA intento rechazado por el límite por origen: una fila LOGIN_LOCAL / CUENTA_BLOQUEADA por intento, como antes de
    M-2. No se descarta por rechazarse antes de validar la contraseña. Se escribe fuera de la solicitud, igual que los avisos, para que
    cuentas existentes e inexistentes tengan el mismo trabajo y la respuesta no revele si la cuenta existe. Sin cuenta identificable se
    guarda solo el HMAC del identificador (como CUENTA_INEXISTENTE); el origen se guarda siempre como HMAC, nunca en claro."""
    session = _sesionDeAviso(bind)
    try:
        user = _findUserByIdentifier(session, identificador)
        _auditFailedLogin(
            session, "LOGIN_LOCAL", user, "CUENTA_BLOQUEADA",
            f"Límite temporal por origen (origen {hashIdentifier(origen)})", identificador,
        )
        session.commit()
    except Exception:  # noqa: BLE001 - la auditoría fuera de la solicitud no cambia la respuesta; el fallo queda en el log
        session.rollback()
        logger.exception("No se pudo auditar el intento bloqueado por el límite")
    finally:
        session.close()


def _tareaBloqueoRecien(bind, identificador: str, origen: str, instante: datetime, espera: int) -> None:
    """Un fallo que activó el límite: auditoría, aviso en la página y correo al titular (como antes de M-2, pero fuera de la solicitud)."""
    session = _sesionDeAviso(bind)
    try:
        user = _findUserByIdentifier(session, identificador)
        if user is None:
            return
        registerEvent(
            session, "LOGIN", auditClassification.ACCION_BLOQUEO_CUENTA, False, user.idUsuario, motivo="INTENTOS_EXCEDIDOS",
            idInstitucion=singleInstitutionOf(session, user.idUsuario), modulo="SEGURIDAD",
            observacion=f"Límite temporal de intentos fallidos desde un mismo origen (hasta {espera} s)",
            datosNuevos={"segundos": espera},
        )
        session.commit()
        if userNotifications.correoActivo(session, user, userNotifications.ACTIVIDAD_SOSPECHOSA):
            _notify(
                EmailEventType.INTENTO_ACCESO_INUSUAL, user, fechaEvento=instante,
                cantidadIntentos=loginThrottle.LIMITES[0][1], bloqueadoHasta=instante + timedelta(seconds=espera),
                urlSeguridad=_securityUrl(user),
            )
        userNotifications.notifySecurity(
            session, user, userNotifications.ACTIVIDAD_SOSPECHOSA, "Intentos de acceso fallidos",
            "Hubo varios intentos fallidos de entrar a tu cuenta desde un mismo lugar y los limitamos unos minutos. Si no fuiste vos, revisá tu seguridad.",
            f"BLOQUEO:{instante + timedelta(seconds=espera)}",  # sin formato: nunca puede romper el rechazo del acceso
        )
    except Exception:  # noqa: BLE001
        session.rollback()
        logger.exception("No se pudo registrar el bloqueo por intentos fallidos")
    finally:
        session.close()


def _rechazarFallo(db: Session, identificador: str, origen: str, now: datetime) -> None:
    """Cuenta un fallo de contraseña y programa sus avisos. Es el mismo trabajo en la solicitud para cuentas existentes e inexistentes:
    la respuesta y su costo no revelan si el identificador corresponde a una cuenta (protección contra enumeración por tiempo)."""
    alcanzado = loginThrottle.registrarFallo(identificador, origen)
    _programarAviso(db, _tareaFalloDeContrasena, identificador, now)
    if alcanzado:
        espera = loginThrottle.retryAfter(identificador, origen) or 0
        _programarAviso(db, _tareaBloqueoRecien, identificador, origen, now, espera)


def _loginLocalBajoLimite(
    db: Session, identificador: str, password: str, origen: str, acceso: str, clientInfo: ClientInfo | None
) -> LoginResponse:
    """Se controla por (identificador, origen) en loginThrottle ANTES de buscar la cuenta. La respuesta es la misma para una cuenta
    existente y una inexistente (sin enumeración), un tercero desde otra IP no bloquea a la víctima, y el límite no consulta la base ni
    verifica la contraseña. Los avisos al titular se escriben en segundo plano para todas las cuentas (ver _rechazarFallo)."""
    now = nowForDb()
    espera = loginThrottle.retryAfter(identificador, origen)
    if espera is not None:
        # Mismo rechazo para cualquier identificador, exista o no: no se consulta la base ni se verifica la contraseña.
        _programarAviso(db, _tareaIntentoLimitado, identificador, origen, now)
        _programarAviso(db, _tareaAuditarIntentoLimitado, identificador, origen)
        raise AuthError("CUENTA_BLOQUEADA", ACCOUNT_LOCKED_MESSAGE, retryAfterSeconds=espera)

    user = _findUserByIdentifier(db, identificador)

    if user is None or _purgeIfExpired(db, user):
        # Cuenta inexistente (o pendiente vencida, que se elimina): la misma respuesta y el mismo costo que una contraseña incorrecta.
        db.commit()  # cierra la lectura antes de Argon2: la conexión no queda ocupada mientras el hash espera un lugar (M-3)
        security.verifyDummyPassword(password)
        _auditFailedLogin(db, "LOGIN_LOCAL", None, "CUENTA_INEXISTENTE", "Cuenta inexistente", identificador)
        db.commit()
        _rechazarFallo(db, identificador, origen, now)
        raise AuthError("CREDENCIALES_INVALIDAS", "Credenciales inválidas.")

    # A partir de acá el Usuario está identificado: los eventos relevantes se auditan.
    credential = _getLocalCredential(db, user)
    if credential is None:
        # Cuenta solo Google: respuesta genérica (no hay CredencialLocal que verificar).
        db.commit()  # ver arriba: no se verifica con la transacción abierta
        security.verifyDummyPassword(password)
        _auditFailedLogin(db, "LOGIN_LOCAL", user, "SIN_CREDENCIAL_LOCAL", "Cuenta sin credencial local")
        db.commit()
        _rechazarFallo(db, identificador, origen, now)
        raise AuthError("CREDENCIALES_INVALIDAS", "Credenciales inválidas.")

    db.commit()  # cierra la lectura antes de Argon2 (M-3): la conexión no queda ocupada mientras el hash espera un lugar
    valid, newHash = security.verifyPassword(password, credential.passwordHash)
    if valid:
        try:
            _registerSuccessfulPassword(db, credential, now, newHash)
        except AuthError:
            # Bloqueo heredado de la versión anterior que venció mientras tanto: el acceso se rechaza como antes.
            _auditFailedLogin(db, "LOGIN_LOCAL", user, "CUENTA_BLOQUEADA", "Cuenta bloqueada")
            db.commit()
            raise
        db.commit()
        _requireActive(db, user, "LOGIN_LOCAL")
        requireAccesoLogin(db, user, acceso, "LOGIN_LOCAL")
        return _completePrimaryAuthentication(db, user, METHOD_PASSWORD, clientInfo)

    _auditFailedLogin(db, "LOGIN_LOCAL", user, "PASSWORD_INCORRECTA", "Contraseña inválida")
    db.commit()
    _rechazarFallo(db, identificador, origen, now)
    # Mismo rechazo que una contraseña incorrecta, también al alcanzar el límite: el siguiente intento ya recibe CUENTA_BLOQUEADA.
    raise AuthError("CREDENCIALES_INVALIDAS", "Credenciales inválidas.")


def loginGoogle(db: Session, identity: GoogleIdentity, clientInfo: ClientInfo | None = None) -> LoginResponse:
    """Casos 2 y 3 en un solo paso (identificación + sesión o desafío MFA)."""
    user = identifyGoogleUser(db, identity)
    return _completePrimaryAuthentication(db, user, METHOD_GOOGLE, clientInfo)


def identifyGoogleUser(
    db: Session, identity: GoogleIdentity, tipoCuentaNueva: str | None = None, aceptaPolitica: bool = False
) -> User:
    """Casos 2 y 3: identifica por proveedor + subjectProveedor; vincula o crea según RF04/RN05.

    Registrarse con Google (tipoCuentaNueva) crea una cuenta nueva del tipo pedido; si el correo o la identidad ya
    tienen cuenta, se rechaza (CUENTA_YA_EXISTE / CUENTA_OTRO_TIPO) antes de cualquier sesión o desafío MFA, para que
    la persona vaya a iniciar sesión. Excepción: la activación de una cuenta invitada (no es un registro nuevo).
    Sin tipoCuentaNueva (inicio de sesión) NUNCA se crea una cuenta: solo entra una identidad ya vinculada o un correo
    ya registrado (vinculación segura); si no existe, CUENTA_NO_REGISTRADA.
    No entrega sesión: eso lo hace _completePrimaryAuthentication.
    """
    now = nowForDb()
    external = db.scalar(
        select(ExternalIdentity).where(
            ExternalIdentity.proveedor == GOOGLE_PROVIDER, ExternalIdentity.subjectProveedor == identity.subject
        )
    )

    outcome = None
    if external is not None:
        user = db.get(User, external.idUsuario)
        if tipoCuentaNueva:
            _rechazarRegistroConCuentaExistente(db, user, tipoCuentaNueva)
        external.ultimoAcceso = now
        external.emailProveedor = identity.email
        external.emailVerificado = identity.emailVerified
    else:
        tipoCuenta = _requirePublicAccountType(tipoCuentaNueva) if tipoCuentaNueva else None
        user, outcome = _linkOrCreateGoogleUser(db, identity, now, tipoCuenta, aceptaPolitica)

    _requireActive(db, user, "LOGIN_GOOGLE")
    if tipoCuentaNueva and outcome != GOOGLE_ACCOUNT_CREATED and user.tipoCuenta != tipoCuentaNueva:
        # Registro con Google de un tipo distinto al de una cuenta que ya existe con ese correo: no se registra otra
        # (un correo, una cuenta) y tampoco se entra en silencio con el tipo equivocado. No se cambia nada.
        db.rollback()
        raise AuthError(
            "CUENTA_OTRO_TIPO",
            "Ese correo ya está registrado con otro tipo de cuenta, por lo que no podés registrarte de nuevo. "
            "Iniciá sesión con tu cuenta existente.",
        )
    try:
        db.commit()
    except IntegrityError as error:
        # Carrera: la misma identidad Google se vinculó en paralelo.
        db.rollback()
        raise AuthError("VINCULACION_RECHAZADA", "No se pudo vincular la cuenta de Google.") from error

    if outcome == GOOGLE_ACCOUNT_CREATED:
        _notify(
            EmailEventType.CUENTA_CREADA, user, apellido=user.apellido, fechaCreacion=user.fechaCreacion,
            urlIngreso=emailService.frontendUrl("ingreso"), **accountGrace.welcomeContext(user),
        )
    elif outcome == GOOGLE_ACCOUNT_LINKED:
        _notify(
            EmailEventType.GOOGLE_VINCULADO, user, fechaEvento=now, correoGoogle=identity.email,
            urlSeguridad=_securityUrl(user),
        )
    return user


# Prefijo de los códigos de transferencia de sesión (login con contraseña hecho en otro origen, p. ej. localhost).
SESSION_TRANSFER_PREFIX = "t."


def createGoogleExchangeCode(db: Session, user: User, transfer: bool = False) -> str:
    """Código de un solo uso y vida corta que el callback entrega al frontend en lugar de los tokens.

    Así los tokens nunca viajan en la URL: el frontend canjea el código con exchangeGoogleCode.
    Solo se guarda el hash; los códigos anteriores sin usar del usuario se descartan.
    """
    now = nowForDb()
    db.execute(
        delete(AccountToken).where(
            AccountToken.idUsuario == user.idUsuario,
            AccountToken.tipo == TOKEN_INTERCAMBIO_GOOGLE,
            AccountToken.fechaUso.is_(None),
        )
    )
    code = (SESSION_TRANSFER_PREFIX if transfer else "") + security.generateOpaqueToken()
    db.add(
        AccountToken(
            idUsuario=user.idUsuario,
            tipo=TOKEN_INTERCAMBIO_GOOGLE,
            tokenHash=security.hashOpaqueToken(code),
            fechaCreacion=now,
            fechaExpiracion=now + timedelta(seconds=GOOGLE_EXCHANGE_CODE_SECONDS),
        )
    )
    commitAccountToken(db, TOKEN_INTERCAMBIO_GOOGLE)
    return code


def exchangeGoogleCode(db: Session, code: str, clientInfo: ClientInfo | None = None) -> LoginResponse:
    """Canjea el código del callback por la sesión (o el desafío MFA). Un solo uso, vence en 2 minutos."""
    now = nowForDb()
    invalid = AuthError("TOKEN_INVALIDO", "El acceso con Google venció o ya fue utilizado. Intentá nuevamente.")
    accountToken = db.scalar(
        select(AccountToken).where(
            AccountToken.tokenHash == security.hashOpaqueToken(code),
            AccountToken.tipo == TOKEN_INTERCAMBIO_GOOGLE,
        )
    )
    if accountToken is None or accountToken.fechaUso is not None or accountToken.fechaExpiracion <= now:
        raise invalid
    consumed = db.execute(
        update(AccountToken)
        .where(AccountToken.idTokenCuenta == accountToken.idTokenCuenta, AccountToken.fechaUso.is_(None))
        .values(fechaUso=now)
    )
    user = db.get(User, accountToken.idUsuario)
    if consumed.rowcount != 1 or user is None:
        db.rollback()
        raise invalid
    db.commit()
    _requireActive(db, user, "LOGIN_GOOGLE")
    if code.startswith(SESSION_TRANSFER_PREFIX):
        # Solo lo emite createSessionTransferCode a quien ya tiene una sesión completa (MFA incluido): no se repite.
        # El inicio de sesión original ya quedó auditado.
        return _authenticatedResponse(db, user, None, clientInfo)
    return _completePrimaryAuthentication(db, user, METHOD_GOOGLE, clientInfo)


def createSessionTransferCode(db: Session, user: User) -> str:
    """Código de un solo uso (2 min) para continuar una sesión ya autenticada en otro origen (localhost -> web).

    La pantalla de login vive en localhost (Google no admite .local) y la aplicación en otro host: el navegador no
    comparte almacenamiento entre ambos, así que la sesión se entrega canjeando este código en /google/exchange.
    """
    return createGoogleExchangeCode(db, user, transfer=True)


GOOGLE_ACCOUNT_CREATED = "CREADA"
GOOGLE_ACCOUNT_LINKED = "VINCULADA"


def _rechazarRegistroConCuentaExistente(db: Session, user: User, tipoCuenta: str) -> None:
    """Registro con Google de un correo que ya tiene cuenta: no se crea otra ni se entra desde el registro."""
    if user.tipoCuenta != tipoCuenta:
        code = "CUENTA_OTRO_TIPO"
        message = (
            "Ese correo ya está registrado con otro tipo de cuenta, por lo que no podés registrarte de nuevo. "
            "Iniciá sesión con tu cuenta existente."
        )
    else:
        code = "CUENTA_YA_EXISTE"
        message = "Ya tenés una cuenta con ese correo, por lo que no podés registrarte de nuevo. Iniciá sesión."
    registerEvent(db, "LOGIN", "REGISTRO_GOOGLE", False, user.idUsuario, observacion="Correo ya registrado", motivo=code)
    db.commit()
    raise AuthError(code, message)


GOOGLE_USERNAME_FALLBACK = "usuario"
USERNAME_MAX_LENGTH = 50


def _usernameFromGoogleEmail(db: Session, email: str) -> str:
    """Nombre de usuario sugerido al registrarse con Google: la parte del correo antes del "@" (sin etiqueta "+...").

    Si otra cuenta ya lo usa, se agrega un número (juanp2, juanp22, ...). La persona puede cambiarlo después desde su
    perfil, siempre que no coincida con el de otra cuenta.
    """
    local = email.split("@", 1)[0].split("+", 1)[0]
    base = re.sub(r"[^\w.-]", "", local)[:USERNAME_MAX_LENGTH]
    if len(base) < USERNAME_MIN_LENGTH:
        base = GOOGLE_USERNAME_FALLBACK
    candidate = base
    number = 2
    while userService.findUserByUsername(db, candidate) is not None:
        suffix = str(number)
        candidate = f"{base[:USERNAME_MAX_LENGTH - len(suffix)]}{suffix}"
        number += 1
    return candidate


def _linkOrCreateGoogleUser(
    db: Session, identity: GoogleIdentity, now, tipoCuenta: str | None, aceptaPolitica: bool = False
) -> tuple[User, str]:
    if not identity.emailVerified or not identity.email:
        registerEvent(db, "LOGIN", "LOGIN_GOOGLE", False, observacion="Correo de Google no verificado",
                      motivo="CORREO_PROVEEDOR_NO_VERIFICADO")
        db.commit()
        raise AuthError("VINCULACION_RECHAZADA", "El correo de la cuenta de Google no está verificado.")

    email = normalizeEmail(identity.email)
    user = _findUserByEmail(db, email)
    activada = False

    if (user is not None and invitedAccounts.isInvitedPendingAccount(db, user) and invitedAccounts.hasValidActivationToken(db, user, now)
            and invitedAccounts.hasLiveInvitation(db, user, now)):
        # Cuenta creada por una invitación institucional vigente: Google verificó que la persona controla ese correo
        # (lo mismo que prueba el enlace de activación). Se activa, se vincula y se consumen sus enlaces.
        # Activar equivale a registrarse: exige haber confirmado la Política de Privacidad (queda registrado).
        consentService.requirePolicyAccepted(aceptaPolitica)
        consentService.record(db, user, TipoConsentimiento.POLITICA_PRIVACIDAD, True)
        user.estado = ESTADO_ACTIVO
        user.fechaActualizacion = now
        db.execute(
            update(AccountToken)
            .where(AccountToken.idUsuario == user.idUsuario, AccountToken.tipo == invitedAccounts.TOKEN_ACTIVACION,
                   AccountToken.fechaUso.is_(None))
            .values(fechaUso=now)
        )
        registerEvent(db, "CRUD", "ACTIVAR_CUENTA_INVITADA", True, user.idUsuario, "Usuario", user.idUsuario,
                      datosNuevos={"estado": ESTADO_ACTIVO, "metodo": "GOOGLE"})
        accountGrace.startIfOrphaned(db, user.idUsuario, now, user.idUsuario, accountGrace.ORIGEN_ACTIVACION)  # habilitada sin vínculo activo
        activada = True
    if user is not None:
        # Caso 3: vinculación automática a la cuenta existente.
        if user.estado != ESTADO_ACTIVO or _getGoogleIdentity(db, user) is not None:
            registerEvent(db, "LOGIN", "VINCULACION_GOOGLE", False, user.idUsuario, motivo="VINCULACION_RECHAZADA")
            db.commit()
            raise AuthError(
                "VINCULACION_RECHAZADA",
                "Existe una cuenta con este correo que no puede vincularse automáticamente.",
            )
        if tipoCuenta is not None and not activada:
            _rechazarRegistroConCuentaExistente(db, user, tipoCuenta)
        registerEvent(db, "PERMISO", "VINCULACION_GOOGLE", True, user.idUsuario, "Usuario", user.idUsuario)
        outcome = GOOGLE_ACCOUNT_LINKED
    elif tipoCuenta is None:
        # Inicio de sesión (no registro): Google no crea cuentas.
        registerEvent(db, "LOGIN", "LOGIN_GOOGLE", False, observacion="Cuenta no registrada", motivo="CUENTA_NO_REGISTRADA")
        db.commit()
        raise AuthError(
            "CUENTA_NO_REGISTRADA", "No hay una cuenta registrada con ese correo de Google. Registrate primero."
        )
    else:
        # Caso 2: cuenta nueva solo Google, sin CredencialLocal. Es un registro: exige la Política de Privacidad.
        consentService.requirePolicyAccepted(aceptaPolitica)
        user = User(
            nombre=normalizeProperName(identity.givenName[:100]) if identity.givenName else None,
            apellido=normalizeProperName(identity.familyName[:100]) if identity.familyName else None,
            correoElectronico=email,
            usuario=_usernameFromGoogleEmail(db, email),
            tipoCuenta=tipoCuenta,
            estado=ESTADO_ACTIVO,
            # Datos que Google informa al registrarse (None si no los entregó o la persona no los compartió).
            sexo=identity.sexo,
            fechaNacimiento=identity.fechaNacimiento,
        )
        db.add(user)
        db.flush()
        consentService.record(db, user, TipoConsentimiento.POLITICA_PRIVACIDAD, True)
        registerEvent(
            db, "CRUD", "REGISTRO_GOOGLE", True, user.idUsuario, "Usuario", user.idUsuario,
            observacion=f"Tipo de cuenta: {tipoCuenta}",
        )
        accountGrace.startIfOrphaned(db, user.idUsuario, now, user.idUsuario, accountGrace.ORIGEN_ALTA)  # solo cuentas institucionales
        outcome = GOOGLE_ACCOUNT_CREATED

    db.add(
        ExternalIdentity(
            idUsuario=user.idUsuario,
            proveedor=GOOGLE_PROVIDER,
            subjectProveedor=identity.subject,
            emailProveedor=identity.email,
            emailVerificado=True,
            ultimoAcceso=now,
        )
    )
    return user, outcome


# --- Una sola sesión activa por cuenta ---------------------------------------------------

SESION_ACTIVA = "SESION_ACTIVA"
MENSAJE_SESION_ACTIVA = (
    "Tu cuenta ya tiene una sesión iniciada en otro dispositivo. Cerrala para ingresar desde acá. "
    "Te enviamos un aviso por correo y en tu cuenta."
)


def _requireNoOtherActiveSession(db: Session, user: User, clientInfo: ClientInfo | None) -> None:
    """Una cuenta tiene una sola sesión activa: si ya hay una vigente, el inicio nuevo se rechaza y el titular recibe un aviso por correo y
    en la página (aunque tenga apagados esos canales).

    Se llama antes de registrar el inicio exitoso, así el intento rechazado no queda auditado como LOGIN correcto. La fila del usuario queda
    bloqueada hasta el commit de la sesión: dos inicios simultáneos no pueden abrir dos sesiones."""
    now = nowForDb()
    db.scalar(
        select(User.idUsuario).where(User.idUsuario == user.idUsuario)
        .with_hint(User, "WITH (UPDLOCK, HOLDLOCK, ROWLOCK)", "mssql")
    )
    filtros = [
        UserSession.idUsuario == user.idUsuario,
        UserSession.fechaRevocacion.is_(None),
        UserSession.fechaExpiracion > now,
    ]
    if schemaCompat.sessionActivityReady(db):
        # Una sesión sin actividad dentro de SESION_INACTIVIDAD_MINUTOS ya no cuenta como abierta: la cuenta puede entrar desde otro equipo.
        # Sin valor de última actividad (sesión anterior a la migración) se usa la fecha de creación.
        limite = now - timedelta(minutes=getSettings().SESION_INACTIVIDAD_MINUTOS)
        filtros.append(or_(
            UserSession.ultimaActividad > limite,
            and_(UserSession.ultimaActividad.is_(None), UserSession.fechaCreacion > limite),
        ))
    activa = db.scalar(select(UserSession.idSesion).where(*filtros).limit(1))
    if activa is None:
        # Sin sesión en uso, las abiertas que quedan son inactivas: se cierran de verdad (no solo dejan de contar). Va en la misma
        # transacción que el inicio nuevo (lo confirma _createSession), así que el bloqueo sigue vigente hasta entonces.
        db.execute(
            update(UserSession)
            .where(UserSession.idUsuario == user.idUsuario, UserSession.fechaRevocacion.is_(None))
            .values(fechaRevocacion=now)
        )
        return
    registerEvent(
        db, "LOGIN", "LOGIN_SESION_ACTIVA", False, user.idUsuario, "SesionUsuario", activa, motivo=SESION_ACTIVA,
        observacion="Ya había una sesión vigente en la cuenta",
    )
    db.commit()
    client = clientInfo or ClientInfo()
    _notify(
        EmailEventType.INICIO_BLOQUEADO_SESION_ACTIVA, user, fechaEvento=now, navegador=client.navegador,
        sistemaOperativo=client.sistemaOperativo, dispositivo=client.dispositivo, urlSeguridad=_securityUrl(user),
    )
    userNotifications.notify(
        db, user, userNotifications.ACTIVIDAD_SOSPECHOSA, "Inicio de sesión bloqueado",
        "Alguien intentó iniciar sesión en tu cuenta desde otro dispositivo mientras ya había una sesión iniciada, y no lo permitimos. "
        "Si no fuiste vos, restablecé tu contraseña.",
        url=userNotifications.URL_SEGURIDAD,
        clave=f"{userNotifications.ACTIVIDAD_SOSPECHOSA}:{SESION_ACTIVA}:{now:%Y-%m-%dT%H:%M:%S.%f}",
        siempreEnPagina=True,
    )
    raise AuthError(SESION_ACTIVA, MENSAJE_SESION_ACTIVA, motivo=SESION_ACTIVA)


def _completePrimaryAuthentication(
    db: Session, user: User, method: str, clientInfo: ClientInfo | None = None
) -> LoginResponse:
    """Entrega la sesión, o solo un desafío MFA si el usuario tiene MFA habilitado."""
    _requireNoOtherActiveSession(db, user, clientInfo)
    if mfa.isEnabled(db, user):
        if not getSettings().mfaEnabled:
            # Nunca se omite un MFA habilitado: si no puede verificarse, no hay sesión.
            raise AuthError("MFA_NO_DISPONIBLE", "MFA no está disponible en este servidor.")
        registerEvent(db, "LOGIN", f"LOGIN_{method.upper()}_MFA_PENDIENTE", True, user.idUsuario)
        db.commit()
        return LoginResponse(
            estado="MFA_REQUERIDO",
            challengeToken=security.createMfaChallengeToken(user.idUsuario, method),
            challengeExpiresIn=getSettings().MFA_CHALLENGE_EXPIRE_MINUTES * 60,
        )

    registerEvent(db, "LOGIN", f"LOGIN_{method.upper()}", True, user.idUsuario)
    return _authenticatedResponse(db, user, _METHOD_LABELS.get(method), clientInfo)


def _authenticatedResponse(
    db: Session, user: User, methodLabel: str | None = None, clientInfo: ClientInfo | None = None
) -> LoginResponse:
    """Sesión definitiva más la indicación de perfil incompleto (no bloquea el acceso)."""
    tokens = _createSession(db, user)
    if user.notificarNuevoInicioSesion:
        client = clientInfo or ClientInfo()
        _notify(
            EmailEventType.NUEVO_INICIO_SESION, user, fechaEvento=nowForDb(), metodo=methodLabel,
            navegador=client.navegador, sistemaOperativo=client.sistemaOperativo, dispositivo=client.dispositivo,
            urlSeguridad=_securityUrl(user), urlDesuscribir=_newLoginUnsubscribeUrl(user),
        )
    # El inicio de sesión ya quedó auditado (LOGIN_*). Aviso visible solo si viene de un equipo que la cuenta nunca había usado
    # (services/knownAccess.py); el correo sigue arriba, con su propio enlace de desuscripción.
    newAccess = knownAccess.registerAccess(db, user, clientInfo)
    if newAccess is not None:
        userNotifications.notify(
            db, user, userNotifications.INICIO_SESION, "Inicio de sesión desde un equipo nuevo",
            f"Se inició sesión en tu cuenta desde {newAccess.description}. Si no fuiste vos, cambiá tu contraseña y revisá la seguridad de tu cuenta.",
            url=userNotifications.URL_SEGURIDAD, clave=f"{userNotifications.INICIO_SESION}:{newAccess.huella}",
        )
    missing = userService.missingRequiredFields(user)
    return LoginResponse(
        estado="AUTENTICADO", tokens=tokens, requiereCompletarPerfil=bool(missing), camposFaltantes=missing
    )


def issueSession(
    db: Session, user: User, methodLabel: str | None = None, clientInfo: ClientInfo | None = None
) -> LoginResponse:
    """Sesión definitiva para un usuario ya autenticado por un flujo propio (p. ej. recuperación de MFA)."""
    _requireNoOtherActiveSession(db, user, clientInfo)
    return _authenticatedResponse(db, user, methodLabel, clientInfo)


def verifyMfaChallenge(
    db: Session,
    challengeToken: str,
    codigo: str | None,
    codigoRecuperacion: str | None,
    clientInfo: ClientInfo | None = None,
) -> LoginResponse:
    try:
        claims = security.decodeMfaChallengeToken(challengeToken)
        user = db.get(User, uuid.UUID(claims["sub"]))
    except jwt.ExpiredSignatureError as error:
        raise AuthError("TOKEN_INVALIDO", "El desafío MFA es inválido o venció.", motivo="TOKEN_VENCIDO") from error
    except (jwt.InvalidTokenError, ValueError) as error:
        raise AuthError("TOKEN_INVALIDO", "El desafío MFA es inválido o venció.", motivo="TOKEN_MALFORMADO") from error

    factor = mfa.getFactor(db, user) if user is not None else None
    if factor is None or not factor.habilitado:
        raise AuthError("TOKEN_INVALIDO", "El desafío MFA es inválido o venció.")
    _requireActive(db, user, "LOGIN_" + claims.get("amr", [METHOD_PASSWORD])[0].upper() + "_MFA")

    try:
        mfa.verifyFactor(db, factor, codigo, codigoRecuperacion)
    except AuthError as error:
        _alertAdministratorAttempt(db, user, False, TIPO_SEGUNDO_FACTOR, error.code)
        raise
    # Otro dispositivo pudo iniciar sesión mientras se esperaba el código: se vuelve a exigir la sesión única.
    _requireNoOtherActiveSession(db, user, clientInfo)
    method = claims.get("amr", [METHOD_PASSWORD])[0]
    registerEvent(db, "LOGIN", f"LOGIN_{method.upper()}_MFA", True, user.idUsuario)
    methodLabel = _METHOD_LABELS.get(method)
    return _authenticatedResponse(
        db, user, f"{methodLabel} + verificación en dos pasos" if methodLabel else None, clientInfo
    )


# --- Sesiones ----------------------------------------------------------------------------


# --- Cierre por inactividad --------------------------------------------------------------

ACTIVIDAD_INTERVALO_ESCRITURA = timedelta(seconds=60)  # la última actividad se guarda como mucho una vez por minuto y sesión


def _enforceInactivity(db: Session, session: UserSession, now: datetime, renovar: bool = True) -> bool:
    """Cierra la sesión si lleva más de SESION_INACTIVIDAD_MINUTOS sin usarse (olvido en un equipo compartido). Devuelve True si la cerró:
    quien llama rechaza el pedido. Sin la columna (base sin migrar) no hace nada.

    Una sesión sin valor (creada antes de la migración) queda activa desde este pedido: no se cierran todas de golpe al actualizar."""
    if not schemaCompat.sessionActivityReady(db):
        return False
    last = session.ultimaActividad
    if last is not None and now - last > timedelta(minutes=getSettings().SESION_INACTIVIDAD_MINUTOS):
        db.execute(
            update(UserSession)
            .where(UserSession.idSesion == session.idSesion, UserSession.fechaRevocacion.is_(None))
            .values(fechaRevocacion=now)
        )
        db.commit()
        return True
    if renovar and (last is None or now - last > ACTIVIDAD_INTERVALO_ESCRITURA):
        db.execute(update(UserSession).where(UserSession.idSesion == session.idSesion).values(ultimaActividad=now))
        db.commit()
    return False


def _createSession(db: Session, user: User) -> TokenPair:
    settings = getSettings()
    refreshToken = security.generateOpaqueToken()
    now = nowForDb()
    session = UserSession(
        idUsuario=user.idUsuario,
        refreshTokenHash=security.hashOpaqueToken(refreshToken),
        fechaExpiracion=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    if schemaCompat.sessionActivityReady(db):
        session.ultimaActividad = now  # el cierre por inactividad cuenta desde el inicio
    db.add(session)
    db.flush()
    db.commit()
    return TokenPair(
        accessToken=security.createAccessToken(user.idUsuario, session.idSesion),
        refreshToken=refreshToken,
        expiresIn=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def refreshSession(db: Session, refreshToken: str) -> TokenPair:
    """Rota el refresh token. Reutilizar uno ya rotado o revocado revoca todas las sesiones."""
    now = nowForDb()
    session = db.scalar(
        select(UserSession).where(UserSession.refreshTokenHash == security.hashOpaqueToken(refreshToken))
    )
    if session is None:
        raise AuthError("TOKEN_INVALIDO", "Sesión inválida.", motivo="SESION_INVALIDA")
    # Una sesión inactiva se cierra: su renovación no es una reutilización (por eso no alerta ni revoca el resto).
    if session.fechaRevocacion is None and _enforceInactivity(db, session, now):
        raise AuthError("TOKEN_INVALIDO", "Sesión inválida.", motivo="SESION_INACTIVA")

    revoked = db.execute(
        update(UserSession)
        .where(UserSession.idSesion == session.idSesion, UserSession.fechaRevocacion.is_(None))
        .values(fechaRevocacion=now)
    )
    if revoked.rowcount != 1:
        user = db.get(User, session.idUsuario)
        if user is not None and user.estado == ESTADO_ELIMINADO:
            # La baja revoca todas las sesiones de la cuenta: un refresh posterior (p. ej. el navegador que todavía tiene la cookie) no es una
            # reutilización ni un indicio de robo. Se rechaza sin alertar.
            raise AuthError("TOKEN_INVALIDO", "Sesión inválida.", motivo="SESION_INVALIDA")
        _revokeAllSessions(db, session.idUsuario, now)
        registerEvent(db, "LOGIN", "REFRESH_REUTILIZADO", False, session.idUsuario, "SesionUsuario", session.idSesion)
        db.commit()
        raise AuthError("TOKEN_INVALIDO", "Sesión inválida.", motivo="REFRESH_REUTILIZADO")

    user = db.get(User, session.idUsuario)
    if session.fechaExpiracion <= now or user is None or user.estado != ESTADO_ACTIVO:
        db.commit()
        raise AuthError("TOKEN_INVALIDO", "Sesión inválida.", motivo="SESION_INVALIDA")
    return _createSession(db, user)


# --- Recuperación de contraseña (cuentas comunes) ------------------------------------------------------------

# Un enlace nuevo no se emite antes de este plazo: evita usar el formulario para inundar de correos a una persona.
PASSWORD_RESET_MIN_INTERVAL_SECONDS = 60
_RESET_LINK_INVALID = ("TOKEN_INVALIDO", "El enlace es inválido o ya fue usado. Pedí uno nuevo.")


def requestPasswordReset(db: Session, correo: str) -> None:
    """Envía el enlace de un solo uso para elegir una contraseña nueva.

    La respuesta es idéntica exista o no la cuenta (no revela qué correos están registrados): sin cuenta activa con
    contraseña local, o de plataforma (que tiene su propio flujo, /platform/password/forgot), no se envía nada.
    """
    from app.services import platform as platformService  # import diferido: platform importa este módulo

    user = _findUserByEmail(db, normalizeEmail(correo))
    if user is None or user.estado != ESTADO_ACTIVO or platformService.isPlatformAccount(user):
        return
    if db.scalar(select(LocalCredential.idCredencialLocal).where(LocalCredential.idUsuario == user.idUsuario)) is None:
        return
    now = nowForDb()
    recent = db.scalar(
        select(AccountToken.idTokenCuenta).where(
            AccountToken.idUsuario == user.idUsuario,
            AccountToken.tipo == TipoTokenCuenta.RECUPERACION_PASSWORD,
            AccountToken.fechaUso.is_(None),
            AccountToken.fechaCreacion > now - timedelta(seconds=PASSWORD_RESET_MIN_INTERVAL_SECONDS),
        )
    )
    if recent is not None:
        return
    db.execute(
        delete(AccountToken).where(
            AccountToken.idUsuario == user.idUsuario,
            AccountToken.tipo == TipoTokenCuenta.RECUPERACION_PASSWORD,
            AccountToken.fechaUso.is_(None),
        )
    )
    token = security.generateOpaqueToken()
    expires = now + timedelta(minutes=getSettings().PASSWORD_RESET_EXPIRE_MINUTES)
    db.add(
        AccountToken(
            idUsuario=user.idUsuario,
            tipo=TipoTokenCuenta.RECUPERACION_PASSWORD,
            tokenHash=security.hashOpaqueToken(token),
            fechaCreacion=now,
            fechaExpiracion=expires,
        )
    )
    registerEvent(db, "PERMISO", "SOLICITAR_RECUPERACION_PASSWORD", True, user.idUsuario, "Usuario", user.idUsuario)
    commitAccountToken(db, TipoTokenCuenta.RECUPERACION_PASSWORD)
    _notify(
        EmailEventType.RECUPERACION_PASSWORD, user, fechaExpiracion=expires,
        urlRestablecer=f"{emailService.frontendUrl('restablecerPassword')}?token={token}",
    )


def resetPassword(db: Session, token: str, password: str) -> None:
    """Completa la recuperación con el enlace del correo: un solo uso, vence, cierra todas las sesiones de la cuenta."""
    from app.services import platform as platformService

    invalid = AuthError(*_RESET_LINK_INVALID)
    accountToken = db.scalar(
        select(AccountToken).where(
            AccountToken.tokenHash == security.hashOpaqueToken(token),
            AccountToken.tipo == TipoTokenCuenta.RECUPERACION_PASSWORD,
            AccountToken.fechaUso.is_(None),
        )
    )
    user = db.get(User, accountToken.idUsuario) if accountToken else None
    if user is None or user.estado != ESTADO_ACTIVO or platformService.isPlatformAccount(user):
        raise invalid
    now = nowForDb()
    if accountToken.fechaExpiracion <= now:
        raise AuthError("TOKEN_VENCIDO", "El enlace venció. Pedí uno nuevo.")
    credential = db.scalar(select(LocalCredential).where(LocalCredential.idUsuario == user.idUsuario))
    if credential is None:
        raise invalid
    _requirePasswordPolicy(password, user.usuario, user.correoElectronico, user.nombre, user.apellido)
    if (error := previousPasswordError(db, credential, password)) is not None:
        raise error
    used = db.execute(
        update(AccountToken)
        .where(AccountToken.idTokenCuenta == accountToken.idTokenCuenta, AccountToken.fechaUso.is_(None))
        .values(fechaUso=now)
        .execution_options(synchronize_session=False)
    ).rowcount
    if used != 1:
        db.rollback()
        raise invalid
    replacePassword(db, credential, password, now)
    credential.intentosFallidosConsecutivos = 0
    credential.bloqueadoHasta = None
    credential.fechaUltimoCambioPassword = now
    _revokeAllSessions(db, user.idUsuario, now)
    registerEvent(db, "PERMISO", "RESTABLECER_PASSWORD", True, user.idUsuario, "CredencialLocal", credential.idCredencialLocal)
    db.commit()
    if userNotifications.correoActivo(db, user, userNotifications.CAMBIO_CONTRASENA):
        _notify(EmailEventType.PASSWORD_CAMBIADA, user, fechaEvento=now, urlSeguridad=_securityUrl(user))
    _passwordNotice(db, user, "Se restableció la contraseña de tu cuenta.", now)


def _revokeAllSessions(db: Session, idUsuario: uuid.UUID, now) -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.idUsuario == idUsuario, UserSession.fechaRevocacion.is_(None))
        .values(fechaRevocacion=now)
    )


def logout(db: Session, session: UserSession) -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.idSesion == session.idSesion, UserSession.fechaRevocacion.is_(None))
        .values(fechaRevocacion=nowForDb())
    )
    db.commit()


def resolveAccessSession(db: Session, claims: dict, renovarActividad: bool = True) -> tuple[User, UserSession]:
    """Valida que la sesión del access token siga vigente y el usuario activo. `renovarActividad=False` (sondeo de fondo, streams) no
    renueva el plazo del cierre por inactividad, pero sí lo aplica."""
    try:
        idUsuario = uuid.UUID(claims["sub"])
        session = db.get(UserSession, uuid.UUID(claims["sid"]))
    except ValueError as error:
        raise AuthError("TOKEN_INVALIDO", "Token inválido.", motivo="TOKEN_MALFORMADO") from error
    now = nowForDb()
    if (
        session is None
        or session.idUsuario != idUsuario
        or session.fechaRevocacion is not None
        or session.fechaExpiracion <= now
    ):
        raise AuthError("TOKEN_INVALIDO", "Token inválido.", motivo="SESION_INVALIDA")
    if _enforceInactivity(db, session, now, renovar=renovarActividad):
        raise AuthError("TOKEN_INVALIDO", "Token inválido.", motivo="SESION_INACTIVA")
    user = db.get(User, idUsuario)
    if user is None or user.estado != ESTADO_ACTIVO:
        raise AuthError("TOKEN_INVALIDO", "Token inválido.", motivo="SESION_INVALIDA")
    return user, session


# --- Cuenta ------------------------------------------------------------------------------


def setLocalPassword(db: Session, user: User, password: str) -> None:
    """Agrega una contraseña local a una cuenta solo Google (pasa al caso 3)."""
    if _getLocalCredential(db, user) is not None:
        raise AuthError("CREDENCIAL_EXISTENTE", "La cuenta ya tiene una contraseña local.")
    _requirePasswordPolicy(password, user.usuario, user.correoElectronico, user.nombre, user.apellido)
    db.add(LocalCredential(idUsuario=user.idUsuario, passwordHash=security.hashPassword(password)))
    registerEvent(db, "PERMISO", "CREDENCIAL_LOCAL_AGREGADA", True, user.idUsuario, "CredencialLocal")
    db.commit()
    now = nowForDb()
    if userNotifications.correoActivo(db, user, userNotifications.CAMBIO_CONTRASENA):
        _notify(EmailEventType.PASSWORD_CAMBIADA, user, fechaEvento=now, urlSeguridad=_securityUrl(user))
    _passwordNotice(db, user, "Se agregó una contraseña a tu cuenta.", now)


def changeLocalPassword(db: Session, user: User, currentSession: UserSession, actual: str, new: str,
                        codigo: str | None, codigoRecuperacion: str | None) -> None:
    """Cambia la contraseña local con la sesión abierta: exige la contraseña actual (mismo contador y bloqueo que el
    login) y, si la cuenta tiene MFA, un código. Cierra las demás sesiones y conserva la actual. Nunca registra ni
    envía contraseñas; el aviso por correo informa el cambio."""
    credential = _getLocalCredential(db, user)
    if credential is None:
        raise AuthError("CREDENCIAL_LOCAL_INEXISTENTE", "Tu cuenta no tiene contraseña local: creala primero.")
    if not verifyCurrentPassword(db, credential, actual, "cambio_contrasena"):
        registerEvent(db, "PERMISO", "CAMBIAR_PASSWORD", False, user.idUsuario, "CredencialLocal",
                      credential.idCredencialLocal, observacion="Contraseña actual incorrecta")
        db.commit()  # el intento fallido cuenta para el bloqueo
        raise AuthError("PASSWORD_INCORRECTA", "La contraseña actual no es correcta.")
    factor = mfa.getFactor(db, user)
    if factor is not None and factor.habilitado:
        if not (codigo or codigoRecuperacion):
            db.commit()
            raise AuthError("CODIGO_MFA_REQUERIDO", "Ingresá el código de verificación en dos pasos.")
        mfa.verifyFactor(db, factor, codigo, codigoRecuperacion)
    if (error := previousPasswordError(db, credential, new)) is not None:
        db.commit()
        raise error
    _requirePasswordPolicy(new, user.usuario, user.correoElectronico, user.nombre, user.apellido)
    now = nowForDb()
    replacePassword(db, credential, new, now)
    credential.fechaUltimoCambioPassword = now
    db.execute(update(UserSession).where(
        UserSession.idUsuario == user.idUsuario, UserSession.idSesion != currentSession.idSesion,
        UserSession.fechaRevocacion.is_(None)).values(fechaRevocacion=now).execution_options(synchronize_session=False))
    registerEvent(db, "PERMISO", "CAMBIAR_PASSWORD", True, user.idUsuario, "CredencialLocal", credential.idCredencialLocal)
    db.commit()
    if userNotifications.correoActivo(db, user, userNotifications.CAMBIO_CONTRASENA):
        _notify(EmailEventType.PASSWORD_CAMBIADA, user, fechaEvento=now, urlSeguridad=_securityUrl(user))
    _passwordNotice(db, user, "Se cambió la contraseña de tu cuenta.", now)


# --- Aviso de nuevo inicio de sesión ----------------------------------------------------
#
# Llega en cada acceso y la cuenta lo desactiva cuando quiere. Los correos de actividad sospechosa (INTENTO_ACCESO_INUSUAL) y de cambios
# en la cuenta también son opcionales (userNotifications.correoActivo).

ORIGEN_ENLACE_CORREO = "ENLACE_CORREO"
ORIGEN_CUENTA = "CUENTA"


def _newLoginUnsubscribeUrl(user: User) -> str:
    token = security.createUnsubscribeToken(user.idUsuario, EmailEventType.NUEVO_INICIO_SESION.value)
    return f"{emailService.frontendUrl('desuscribirInicioSesion')}?token={token}"


def setNewLoginNotification(db: Session, user: User, habilitada: bool, origen: str = ORIGEN_CUENTA) -> bool:
    """Activa o desactiva el aviso NUEVO_INICIO_SESION. Devuelve True si cambió; sin cambio no se audita."""
    if user.notificarNuevoInicioSesion == habilitada:
        return False
    user.notificarNuevoInicioSesion = habilitada
    user.fechaActualizacion = nowForDb()
    registerEvent(
        db, "CRUD", "PREFERENCIA_NOTIFICACION", True, user.idUsuario, "Usuario", user.idUsuario,
        datosPrevios={"evento": EmailEventType.NUEVO_INICIO_SESION.value, "habilitada": not habilitada},
        datosNuevos={"evento": EmailEventType.NUEVO_INICIO_SESION.value, "habilitada": habilitada, "origen": origen},
    )
    db.commit()
    return True


def unsubscribeNewLogin(db: Session, token: str) -> None:
    """Desactiva el aviso desde el enlace del correo (sin sesión: el enlace firmado identifica la cuenta)."""
    invalid = AuthError("TOKEN_INVALIDO", "El enlace para dejar de recibir el aviso es inválido o venció.")
    try:
        claims = security.decodeUnsubscribeToken(token, EmailEventType.NUEVO_INICIO_SESION.value)
        user = db.get(User, uuid.UUID(claims["sub"]))
    except (jwt.InvalidTokenError, ValueError) as error:
        raise invalid from error
    if user is None or user.estado != ESTADO_ACTIVO:
        raise invalid
    setNewLoginNotification(db, user, False, ORIGEN_ENLACE_CORREO)


def accountSummary(db: Session, user: User) -> AccountResponse:
    missing = userService.missingRequiredFields(user)
    return AccountResponse(
        usuario=UserRead.model_validate(user),
        tieneCredencialLocal=_getLocalCredential(db, user) is not None,
        tieneGoogle=_getGoogleIdentity(db, user) is not None,
        mfaHabilitado=mfa.isEnabled(db, user),
        notificarNuevoInicioSesion=user.notificarNuevoInicioSesion,
        requiereCompletarPerfil=bool(missing),
        camposFaltantes=missing,
        periodoGracia=GracePeriodRead.model_validate(grace, from_attributes=True) if (
            grace := accountGrace.graceOf(user, nowForDb())) is not None else None,
    )
