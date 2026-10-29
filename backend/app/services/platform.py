# Platform - Administración de la plataforma GlucoLume (roles globales, moderadores, seguridad y transferencia del control)
#
# Roles globales: Usuario.tipoCuenta = ADMINISTRADOR_PLATAFORMA (administrador del sistema, a lo sumo UNO vigente:
# UX_Usuario_administradorUnico) o MODERADOR_PLATAFORMA (moderador del sistema). NO se usa InstitucionUsuario ni ningún
# permiso institucional. El rol se lee de SQL Server en cada pedido (resolveAccessSession), así que un cambio rige de
# inmediato para las sesiones abiertas. Una cuenta individual o institucional NO se convierte en moderador: un Usuario
# tiene un único tipo de cuenta y cambiarlo alteraría sus vínculos; para eso hay que invitar otro correo.
#
# Seguridad de las cuentas administrativas:
#   - Todo el panel (salvo /platform/me y la configuración de MFA) exige MFA habilitado (PLATFORM_MFA_REQUIRED).
#   - Las acciones sensibles piden reautenticación: contraseña (si hay credencial local) + código MFA.
#   - Las invitaciones son enlaces de un solo uso (TokenCuenta ACTIVACION_CUENTA): nadie define ni conoce la contraseña.
#   - Restablecer contraseña: enlace de un solo uso (RECUPERACION_PASSWORD) enviado al correo; no se muestra nada.
#   - Todo queda en Auditoria con módulo PLATAFORMA (sin contraseñas, tokens ni códigos).

import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import getSettings
from app.core.exceptions import AuthError
from app.emails.eventTypes import EmailEventType
from app.models.accountToken import AccountToken, TipoTokenCuenta
from app.models.audit import Audit
from app.models.externalIdentity import ExternalIdentity
from app.models.localCredential import LocalCredential
from app.models.mfaFactor import MfaFactor
from app.models.mfaRecoveryCode import MfaRecoveryCode
from app.models.platformTransfer import PlatformTransfer
from app.models.user import User
from app.models.userSession import UserSession
from app.schemas.auth import LoginResponse
from app.schemas.platform import (
    EligibleModerator,
    ModeratorInvite,
    CodeActivation,
    ModeratorRead,
    PlatformMe,
    Reauthentication,
    TransferOverview,
    TransferRead,
)
from app.services import auth as authService
from app.services import email as emailService
from app.services import mfa
from app.services.audit import registerEvent
from app.utils.timeZone import nowForDb
from app.utils.userAgent import ClientInfo

ADMIN, MOD = "ADMINISTRADOR_PLATAFORMA", "MODERADOR_PLATAFORMA"
PLATFORM_ROLES = (ADMIN, MOD)
ROLE_LABELS = {ADMIN: "Administrador del sistema", MOD: "Moderador del sistema"}
MODULE = "PLATAFORMA"

# Permisos por operación. La autorización real se aplica en FastAPI con estos nombres; React solo los usa para mostrar.
PERMISSIONS = {
    ADMIN: (
        "DASHBOARD_GLOBAL", "GESTIONAR_MODERADORES", "TRANSFERIR_ADMINISTRACION", "CONSULTAR_AUDITORIA_GLOBAL",
        "CONSULTAR_DISPOSITIVOS_GLOBALES", "GESTIONAR_DISPOSITIVOS_GLOBALES", "GESTIONAR_MATRICES_GLOBALES",
        "CONSULTAR_ESTADO_SISTEMA", "SUSCRIPCIONES_Y_PAGOS",
        # Control de instituciones (compartido con el moderador, salvo lo reservado):
        "SUPERVISAR_INSTITUCIONES", "AUDITAR_INSTITUCIONES", "GESTIONAR_ESTADO_INSTITUCIONES", "GESTIONAR_CUPOS_INSTITUCIONES",
        # Reservado al administrador: eliminar instituciones (con MFA). El desbloqueo manual de cuentas se descartó (19/10/2026): el bloqueo
        # por intentos vence solo y la recuperación de contraseña lo resuelve.
        "ELIMINAR_INSTITUCIONES",
    ),
    MOD: (
        "DASHBOARD_TECNICO", "CONSULTAR_DISPOSITIVOS_GLOBALES", "GESTIONAR_MATRICES_GLOBALES", "CONSULTAR_ESTADO_SISTEMA",
        "SUPERVISAR_INSTITUCIONES", "AUDITAR_INSTITUCIONES", "GESTIONAR_ESTADO_INSTITUCIONES", "GESTIONAR_CUPOS_INSTITUCIONES",
    ),
}

DENIED = "No tenés acceso a la administración de la plataforma."


def _error(code: str, message: str) -> AuthError:
    return AuthError(code, message)


def mfaRequired() -> bool:
    return getSettings().PLATFORM_MFA_REQUIRED


# --- Roles y acceso --------------------------------------------------------------------------------------------


def isPlatformAccount(user: User) -> bool:
    return user.tipoCuenta in PLATFORM_ROLES


def permissionsOf(user: User) -> tuple[str, ...]:
    return PERMISSIONS.get(user.tipoCuenta, ())


def requirePlatformAccount(db: Session, user: User) -> None:
    """Solo cuentas con un rol global vigente (el rol sale de SQL Server). Cualquier otra recibe 403 y queda registrado."""
    if not isPlatformAccount(user):
        registerEvent(db, "ACCESO", "ACCESO_PLATAFORMA_DENEGADO", False, user.idUsuario, "Usuario", user.idUsuario,
                      modulo=MODULE, observacion="Cuenta sin rol de plataforma", motivo="SIN_ROL_PLATAFORMA")
        db.commit()
        raise _error("ACCESO_PLATAFORMA_DENEGADO", DENIED)


def requireMfaEnabled(db: Session, user: User) -> None:
    if mfaRequired() and not mfa.isEnabled(db, user):
        raise _error("MFA_REQUERIDA_PLATAFORMA",
                     "Activá la verificación en dos pasos (MFA) para usar las funciones de administración.")


def requirePermission(db: Session, user: User, permission: str) -> None:
    requirePlatformAccount(db, user)
    if permission not in permissionsOf(user):
        registerEvent(db, "PERMISO", "OPERACION_PLATAFORMA_DENEGADA", False, user.idUsuario, "Usuario", user.idUsuario,
                      modulo=MODULE, observacion=f"Sin permiso: {permission}", motivo="PERMISO_INSUFICIENTE")
        db.commit()
        raise _error("PERMISO_INSUFICIENTE", "Tu rol no permite esta operación.")


def reauthenticate(db: Session, user: User, data: Reauthentication, action: str) -> None:
    """Reautenticación reforzada: contraseña (si hay credencial local) y código MFA. Cualquier fallo se registra."""
    credential = db.scalar(select(LocalCredential).where(LocalCredential.idUsuario == user.idUsuario))
    ok = True
    if credential is not None:
        password = data.password.get_secret_value() if data.password else None
        ok = bool(password) and authService.verifyCurrentPassword(db, credential, password)
    if ok:
        factor = mfa.getFactor(db, user)
        if factor is not None and factor.habilitado:
            if not (data.codigo or data.codigoRecuperacion):
                ok = False
            else:
                try:
                    mfa.verifyFactor(db, factor, data.codigo, data.codigoRecuperacion)
                except AuthError:
                    ok = False
                    raise
        elif mfaRequired():
            raise _error("MFA_REQUERIDA_PLATAFORMA", "Activá la verificación en dos pasos para confirmar esta acción.")
    if not ok:
        registerEvent(db, "PERMISO", "REAUTENTICACION_FALLIDA", False, user.idUsuario, "Usuario", user.idUsuario,
                      modulo=MODULE, observacion=action, motivo="REAUTENTICACION_INVALIDA")
        db.commit()
        raise _error("REAUTENTICACION_INVALIDA", "No pudimos confirmar tu identidad: revisá la contraseña y el código.")
    db.commit()


def me(db: Session, user: User) -> PlatformMe:
    requirePlatformAccount(db, user)
    enabled = mfa.isEnabled(db, user)
    return PlatformMe(
        idUsuario=user.idUsuario, nombre=user.nombre, apellido=user.apellido, correoElectronico=user.correoElectronico,
        rol=user.tipoCuenta, rolEtiqueta=ROLE_LABELS[user.tipoCuenta], permisos=list(permissionsOf(user)),
        mfaHabilitado=enabled, mfaRequerida=mfaRequired(), requiereConfigurarMfa=mfaRequired() and not enabled,
        tieneCredencialLocal=db.scalar(select(LocalCredential.idCredencialLocal).where(LocalCredential.idUsuario == user.idUsuario)) is not None,
        tieneGoogle=db.scalar(select(ExternalIdentity.idIdentidadExterna).where(ExternalIdentity.idUsuario == user.idUsuario)) is not None,
        transferenciaPendiente=_pendingFor(db, user),
    )


def _fullName(user: User | None) -> str | None:
    return " ".join(part for part in (user.nombre, user.apellido) if part) or user.usuario if user else None


def _revokeSessions(db: Session, idUsuario: uuid.UUID) -> None:
    db.execute(update(UserSession).where(UserSession.idUsuario == idUsuario, UserSession.fechaRevocacion.is_(None))
               .values(fechaRevocacion=nowForDb()).execution_options(synchronize_session=False))


# --- Invitaciones de moderadores (y del primer administrador) -------------------------------------------------


def _newActivationToken(db: Session, user: User) -> tuple[str, datetime]:
    """Invalida los enlaces anteriores sin usar y crea uno nuevo (un solo uso)."""
    db.execute(delete(AccountToken).where(
        AccountToken.idUsuario == user.idUsuario, AccountToken.tipo == TipoTokenCuenta.ACTIVACION_CUENTA,
        AccountToken.fechaUso.is_(None)))
    token = security.generateOpaqueToken()
    expires = nowForDb() + timedelta(hours=getSettings().PLATFORM_INVITATION_EXPIRE_HOURS)
    db.add(AccountToken(idUsuario=user.idUsuario, tipo=TipoTokenCuenta.ACTIVACION_CUENTA,
                        tokenHash=security.hashOpaqueToken(token), fechaExpiracion=expires))
    return token, expires


def _sendInvitation(user: User, token: str, expires: datetime) -> bool:
    return emailService.sendEmailEvent(
        EmailEventType.INVITACION_PLATAFORMA, user.correoElectronico,
        {"nombre": user.nombre, "rolPlataforma": ROLE_LABELS[user.tipoCuenta], "fechaExpiracion": expires, "urlActivar": activationLink(token)})


def activationLink(token: str) -> str:
    """Enlace de activación: el código va en el FRAGMENTO (#codigo=…), que el navegador nunca envía al servidor, así que no queda en los
    registros de acceso de Nginx ni en el Referer. La pantalla lo lee y lo borra de la barra de direcciones."""
    return f"{emailService.frontendUrl('plataformaActivar')}#codigo={token}"


def _lastAccess(db: Session, idUsuario: uuid.UUID) -> datetime | None:
    return db.scalar(select(func.max(UserSession.fechaCreacion)).where(UserSession.idUsuario == idUsuario))


def _moderatorRead(db: Session, user: User) -> ModeratorRead:
    now = nowForDb()
    token = db.scalar(select(func.max(AccountToken.fechaExpiracion)).where(
        AccountToken.idUsuario == user.idUsuario, AccountToken.tipo == TipoTokenCuenta.ACTIVACION_CUENTA,
        AccountToken.fechaUso.is_(None)))
    mfaOn = mfa.isEnabled(db, user)
    if user.estado == "PENDIENTE":
        access = "INVITADO" if token is not None and token > now else "INVITACION_VENCIDA"
    elif user.estado == "ACTIVO":
        access = "ACTIVO" if mfaOn or not mfaRequired() else "ACTIVO_SIN_MFA"
    else:
        access = "REVOCADO"
    return ModeratorRead(
        idUsuario=user.idUsuario, nombre=user.nombre, apellido=user.apellido, correoElectronico=user.correoElectronico,
        usuario=user.usuario, estadoCuenta=user.estado, estadoAcceso=access, mfaHabilitado=mfaOn,
        tieneCredencialLocal=db.scalar(select(LocalCredential.idCredencialLocal).where(LocalCredential.idUsuario == user.idUsuario)) is not None,
        tieneGoogle=db.scalar(select(ExternalIdentity.idIdentidadExterna).where(ExternalIdentity.idUsuario == user.idUsuario)) is not None,
        fechaCreacion=user.fechaCreacion, ultimoAcceso=_lastAccess(db, user.idUsuario),
        invitacionVence=token if user.estado == "PENDIENTE" else None,
    )


def listModerators(db: Session, actor: User) -> list[ModeratorRead]:
    requirePermission(db, actor, "GESTIONAR_MODERADORES")
    users = db.scalars(select(User).where(User.tipoCuenta == MOD, User.estado != "ELIMINADO")
                       .order_by(User.apellido, User.nombre)).all()
    return [_moderatorRead(db, user) for user in users]


def _moderator(db: Session, idUsuario: uuid.UUID) -> User:
    user = db.get(User, idUsuario)
    if user is None or user.tipoCuenta != MOD or user.estado == "ELIMINADO":
        raise _error("MODERADOR_NO_ENCONTRADO", "No encontramos a ese moderador del sistema.")
    return user


def getModerator(db: Session, actor: User, idUsuario: uuid.UUID) -> ModeratorRead:
    requirePermission(db, actor, "GESTIONAR_MODERADORES")
    return _moderatorRead(db, _moderator(db, idUsuario))


def inviteModerator(db: Session, actor: User, data: ModeratorInvite) -> tuple[ModeratorRead, bool, str]:
    """Alta controlada: cuenta PENDIENTE sin credenciales + enlace de activación. Devuelve (moderador, enviado, mensaje).

    Una persona que ya tiene cuenta puede ser (re)invitada solo si ya es MODERADOR_PLATAFORMA (pendiente o con el acceso
    revocado). Una cuenta individual o institucional no se convierte: tiene vínculos propios y un único tipo de cuenta."""
    requirePermission(db, actor, "GESTIONAR_MODERADORES")
    requireMfaEnabled(db, actor)
    reauthenticate(db, actor, data.reautenticacion, "INVITAR_MODERADOR")
    existing = db.scalar(select(User).where(User.correoElectronico == data.correoElectronico, User.estado != "ELIMINADO"))
    if existing is None:
        user = User(nombre=data.nombre, apellido=data.apellido, correoElectronico=data.correoElectronico,
                    tipoCuenta=MOD, estado="PENDIENTE")
        db.add(user)
        db.flush()
        outcome = "INVITADO"
    elif existing.tipoCuenta != MOD:
        registerEvent(db, "PERMISO", "INVITAR_MODERADOR_PLATAFORMA", False, actor.idUsuario, "Usuario", existing.idUsuario,
                      modulo=MODULE, observacion="Cuenta existente de otro tipo: no se convierte")
        db.commit()
        raise _error(
            "CUENTA_NO_CONVERTIBLE",
            "Ese correo ya pertenece a una cuenta de GlucoLume que no es de plataforma. Para no alterar sus vínculos "
            "actuales no se la convierte en moderador del sistema: invitá otro correo.")
    elif existing.estado == "ACTIVO":
        raise _error("MODERADOR_YA_ACTIVO", "Esa persona ya es moderadora activa del sistema.")
    else:
        user = existing
        user.estado = "PENDIENTE"  # acceso cerrado hasta que acepte (re-invitación tras una revocación)
        user.fechaActualizacion = nowForDb()
        _revokeSessions(db, user.idUsuario)
        outcome = "REINVITADO"
    token, expires = _newActivationToken(db, user)
    registerEvent(db, "PERMISO", "INVITAR_MODERADOR_PLATAFORMA", True, actor.idUsuario, "Usuario", user.idUsuario,
                  modulo=MODULE, datosNuevos={"rol": MOD, "resultado": outcome})
    db.commit()
    sent = _sendInvitation(user, token, expires)
    if sent:
        _notifyInvitationSent(actor, user, expires)
    message = ("Enviamos la invitación al correo indicado." if sent
               else "La invitación se creó, pero no pudimos enviar el correo. Reenviala más tarde.")
    return _moderatorRead(db, user), sent, message


def _notifyInvitationSent(actor: User, invitee: User, expires: datetime) -> None:
    """Avisa a quien invitó que la invitación salió hacia el correo del moderador (el moderador recibe la suya aparte)."""
    emailService.sendEmailEventInBackground(
        EmailEventType.INVITACION_PLATAFORMA_ENVIADA, actor.correoElectronico,
        {"nombre": actor.nombre, "nombreInvitado": _fullName(invitee) or invitee.correoElectronico,
         "correoInvitado": invitee.correoElectronico, "rolPlataforma": ROLE_LABELS[invitee.tipoCuenta], "fechaExpiracion": expires})


def resendInvitation(db: Session, actor: User, idUsuario: uuid.UUID, reauth: Reauthentication) -> tuple[ModeratorRead, bool, str]:
    requirePermission(db, actor, "GESTIONAR_MODERADORES")
    requireMfaEnabled(db, actor)
    reauthenticate(db, actor, reauth, "REENVIAR_INVITACION")
    user = _moderator(db, idUsuario)
    if user.estado != "PENDIENTE":
        raise _error("INVITACION_NO_PENDIENTE", "Solo se reenvía la invitación a quien todavía no activó su cuenta.")
    token, expires = _newActivationToken(db, user)
    registerEvent(db, "PERMISO", "REENVIAR_INVITACION_PLATAFORMA", True, actor.idUsuario, "Usuario", user.idUsuario, modulo=MODULE)
    db.commit()
    sent = _sendInvitation(user, token, expires)
    return _moderatorRead(db, user), sent, "Reenviamos la invitación." if sent else "No pudimos enviar el correo."


def revokeModerator(db: Session, actor: User, idUsuario: uuid.UUID, reauth: Reauthentication) -> ModeratorRead:
    """Revoca el acceso: cuenta BLOQUEADA, sesiones cerradas y cualquier transferencia pendiente hacia esa persona cancelada."""
    requirePermission(db, actor, "GESTIONAR_MODERADORES")
    requireMfaEnabled(db, actor)
    reauthenticate(db, actor, reauth, "REVOCAR_MODERADOR")
    user = _moderator(db, idUsuario)
    if user.estado == "BLOQUEADO":
        raise _error("MODERADOR_YA_REVOCADO", "El acceso de ese moderador ya estaba revocado.")
    now = nowForDb()
    user.estado = "BLOQUEADO"
    user.fechaActualizacion = now
    _revokeSessions(db, user.idUsuario)
    db.execute(delete(AccountToken).where(AccountToken.idUsuario == user.idUsuario, AccountToken.fechaUso.is_(None),
                                          AccountToken.tipo.in_([TipoTokenCuenta.ACTIVACION_CUENTA, TipoTokenCuenta.RECUPERACION_PASSWORD])))
    db.execute(update(PlatformTransfer).where(PlatformTransfer.idUsuarioDestino == user.idUsuario, PlatformTransfer.estado == "PENDIENTE")
               .values(estado="CANCELADA", fechaRespuesta=now))
    registerEvent(db, "PERMISO", "REVOCAR_MODERADOR_PLATAFORMA", True, actor.idUsuario, "Usuario", user.idUsuario,
                  modulo=MODULE, datosPrevios={"estado": "ACTIVO"}, datosNuevos={"estado": "BLOQUEADO"})
    db.commit()
    emailService.sendEmailEventInBackground(EmailEventType.ACCESO_PLATAFORMA_REVOCADO, user.correoElectronico,
                                            {"nombre": user.nombre, "fechaEvento": now})
    return _moderatorRead(db, user)


def startModeratorPasswordReset(db: Session, actor: User, idUsuario: uuid.UUID, reauth: Reauthentication) -> tuple[ModeratorRead, bool, str]:
    """El administrador pide el restablecimiento: se envía un enlace al correo del moderador; nadie ve ni define la contraseña."""
    requirePermission(db, actor, "GESTIONAR_MODERADORES")
    requireMfaEnabled(db, actor)
    reauthenticate(db, actor, reauth, "RESTABLECER_PASSWORD_MODERADOR")
    user = _moderator(db, idUsuario)
    if user.estado != "ACTIVO":
        raise _error("MODERADOR_NO_ACTIVO", "Solo se restablece la contraseña de un moderador con la cuenta activa.")
    credential = db.scalar(select(LocalCredential).where(LocalCredential.idUsuario == user.idUsuario))
    if credential is None:
        raise _error("CUENTA_SOLO_GOOGLE",
                     "Esta cuenta ingresa solo con Google y no tiene contraseña local: se recupera desde su cuenta de Google.")
    token, expires = _newResetLink(db, user)
    registerEvent(db, "PERMISO", "RESTABLECER_PASSWORD_MODERADOR", True, actor.idUsuario, "Usuario", user.idUsuario, modulo=MODULE)
    db.commit()
    sent = _sendResetLink(user, token, expires)
    return _moderatorRead(db, user), sent, "Enviamos el enlace de restablecimiento al correo del moderador."


# --- Activación de la cuenta invitada ---------------------------------------------------------------------------


def _loadInvitation(db: Session, token: str) -> tuple[AccountToken, User]:
    accountToken = db.scalar(select(AccountToken).where(
        AccountToken.tokenHash == security.hashOpaqueToken(token), AccountToken.tipo == TipoTokenCuenta.ACTIVACION_CUENTA,
        AccountToken.fechaUso.is_(None)))
    user = db.get(User, accountToken.idUsuario) if accountToken else None
    if user is None or user.tipoCuenta not in PLATFORM_ROLES or user.estado != "PENDIENTE":
        raise _error("TOKEN_INVALIDO", "El enlace de activación es inválido o ya fue usado.")
    if accountToken.fechaExpiracion <= nowForDb():
        raise _error("TOKEN_VENCIDO", "El enlace de activación venció. Pedí que te reenvíen la invitación.")
    return accountToken, user


def completeActivation(db: Session, token: str, usuario: str, password: str, clientInfo: ClientInfo | None = None) -> LoginResponse:
    """Acepta la invitación: la persona elige usuario y contraseña, la cuenta pasa a ACTIVO y se abre su sesión.

    Los permisos administrativos recién funcionan cuando activa MFA (el panel la guía); hasta entonces solo puede
    configurarla."""
    accountToken, user = _loadInvitation(db, token)
    usuario = usuario.strip()
    authService._requirePasswordPolicy(password, usuario, user.correoElectronico, user.nombre, user.apellido)
    if db.scalar(select(User.idUsuario).where(User.usuario == usuario, User.idUsuario != user.idUsuario)):
        raise _error("USUARIO_REGISTRADO", "El nombre de usuario ya está registrado.")
    now = nowForDb()
    try:
        used = db.execute(update(AccountToken).where(AccountToken.idTokenCuenta == accountToken.idTokenCuenta, AccountToken.fechaUso.is_(None))
                          .values(fechaUso=now).execution_options(synchronize_session=False)).rowcount
        activated = db.execute(update(User).where(User.idUsuario == user.idUsuario, User.estado == "PENDIENTE")
                               .values(estado="ACTIVO", usuario=usuario, fechaActualizacion=now)
                               .execution_options(synchronize_session=False)).rowcount
        if used != 1 or activated != 1:
            db.rollback()
            raise _error("TOKEN_INVALIDO", "El enlace de activación es inválido o ya fue usado.")
        credential = db.scalar(select(LocalCredential).where(LocalCredential.idUsuario == user.idUsuario))
        if credential is None:
            db.add(LocalCredential(idUsuario=user.idUsuario, passwordHash=security.hashPassword(password)))
        else:  # re-invitación: la contraseña anterior deja de servir
            credential.passwordHash = security.hashPassword(password)
            credential.intentosFallidosConsecutivos = 0
            credential.bloqueadoHasta = None
            credential.fechaUltimoCambioPassword = now
        registerEvent(db, "PERMISO", "ACTIVAR_CUENTA_PLATAFORMA", True, user.idUsuario, "Usuario", user.idUsuario,
                      modulo=MODULE, datosNuevos={"rol": user.tipoCuenta, "estado": "ACTIVO"})
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _error("USUARIO_REGISTRADO", "El nombre de usuario ya está registrado.") from error
    db.refresh(user)
    if mfa.isEnabled(db, user):
        # Re-invitación de una cuenta que conserva su MFA: el enlace del correo fija la contraseña, pero la sesión exige el segundo factor
        # (igual que el inicio de sesión y el restablecimiento de contraseña). Una cuenta nueva, sin MFA, recibe la sesión para configurarlo.
        return authService._completePrimaryAuthentication(db, user, authService.METHOD_PASSWORD, clientInfo)
    registerEvent(db, "LOGIN", authService.ACCION_LOGIN_ACTIVACION, True, user.idUsuario, datosNuevos={"primerFactor": "enlace"})  # abre sesión: es un ingreso
    return authService.issueSession(db, user, "Activación de la cuenta administrativa", clientInfo)


CODE_ACTIVATION_ACTION = "ACTIVAR_CUENTA_PLATAFORMA_CODIGO"


def _invalidCode() -> AuthError:
    # Un solo mensaje para código inexistente, vencido o ya usado: no revela cuál fue ni si existe la invitación.
    return _error("CODIGO_ACTIVACION_INVALIDO", "El código no es válido, venció o ya fue usado.")


def _failedCodeAttempt(db: Session, user: User | None, reason: str) -> None:
    registerEvent(db, "PERMISO", CODE_ACTIVATION_ACTION, False, user.idUsuario if user is not None else None, "Usuario",
                  user.idUsuario if user is not None else None, modulo=MODULE, observacion=f"Rechazada: {reason}",
                  motivo="CODIGO_ACTIVACION_INVALIDO")
    db.commit()


def activateWithCode(db: Session, data: CodeActivation, clientInfo: ClientInfo | None = None) -> LoginResponse:
    """Activación administrativa con el código de un solo uso: ES la invitación (TokenCuenta ACTIVACION_CUENTA, solo su hash; 256 bits, vence y
    se usa una vez), que ya identifica a la persona (nombre y correo los registró quien invitó). El rol sale de la cuenta invitada
    —ADMINISTRADOR solo desde initAdmin en el servidor, MODERADOR solo desde la invitación del administrador— y nunca de la solicitud. Adivinar un
    código no es viable (límite por IP y espacio de 2^256); los intentos con códigos desconocidos quedan auditados. La activación en sí es
    la de siempre (atómica y de un solo uso) y la sesión resultante solo puede configurar MFA."""
    if data.password.get_secret_value() != data.confirmacion.get_secret_value():
        raise _error("CONFIRMACION_DISTINTA", "Las contraseñas no coinciden.")
    try:
        accountToken, user = _loadInvitation(db, data.codigo)
    except AuthError:
        _failedCodeAttempt(db, None, "CODIGO_INEXISTENTE_O_NO_VIGENTE")
        raise _invalidCode() from None
    if user.tipoCuenta == ADMIN and db.scalar(select(User.idUsuario).where(
            User.tipoCuenta == ADMIN, User.estado == "ACTIVO", User.idUsuario != user.idUsuario)) is not None:
        _failedCodeAttempt(db, user, "REGISTRO_NO_PERMITIDO")  # ya hay un administrador vigente: no se activa otro aunque el código exista
        raise _invalidCode()
    try:
        return completeActivation(db, data.codigo, data.usuario, data.password.get_secret_value(), clientInfo)
    except AuthError as error:
        if error.code in ("TOKEN_INVALIDO", "TOKEN_VENCIDO"):
            raise _invalidCode() from None
        raise


# --- Contraseñas ----------------------------------------------------------------------------------------------


def _newResetLink(db: Session, user: User) -> tuple[str, datetime]:
    """Invalida los enlaces anteriores sin usar y crea uno nuevo. Se envía con _sendResetLink DESPUÉS del commit: un correo nunca lleva un
    enlace que no quedó guardado, y el envío SMTP no se hace con la fila de TokenCuenta bloqueada."""
    db.execute(delete(AccountToken).where(AccountToken.idUsuario == user.idUsuario,
                                          AccountToken.tipo == TipoTokenCuenta.RECUPERACION_PASSWORD, AccountToken.fechaUso.is_(None)))
    token = security.generateOpaqueToken()
    expires = nowForDb() + timedelta(minutes=getSettings().PLATFORM_RESET_EXPIRE_MINUTES)
    db.add(AccountToken(idUsuario=user.idUsuario, tipo=TipoTokenCuenta.RECUPERACION_PASSWORD,
                        tokenHash=security.hashOpaqueToken(token), fechaExpiracion=expires))
    return token, expires


def _sendResetLink(user: User, token: str, expires: datetime) -> bool:
    return emailService.sendEmailEvent(
        EmailEventType.RECUPERACION_PASSWORD, user.correoElectronico,
        {"nombre": user.nombre, "fechaExpiracion": expires,
         "urlRestablecer": f"{emailService.frontendUrl('plataformaRestablecer')}?token={token}"})


def requestPasswordReset(db: Session, correo: str) -> None:
    """Recuperar contraseña desde el acceso administrativo. Respuesta idéntica exista o no la cuenta (no revela nada)."""
    user = db.scalar(select(User).where(User.correoElectronico == correo))
    if (user is None or not isPlatformAccount(user) or user.estado != "ACTIVO"
            or db.scalar(select(LocalCredential.idCredencialLocal).where(LocalCredential.idUsuario == user.idUsuario)) is None):
        return
    token, expires = _newResetLink(db, user)
    registerEvent(db, "PERMISO", "SOLICITAR_RECUPERACION_PASSWORD", True, user.idUsuario, "Usuario", user.idUsuario, modulo=MODULE)
    db.commit()
    _sendResetLink(user, token, expires)


def resetPassword(db: Session, token: str, password: str) -> None:
    """Completa el restablecimiento con el enlace de un solo uso; cierra todas las sesiones de la cuenta."""
    accountToken = db.scalar(select(AccountToken).where(
        AccountToken.tokenHash == security.hashOpaqueToken(token), AccountToken.tipo == TipoTokenCuenta.RECUPERACION_PASSWORD,
        AccountToken.fechaUso.is_(None)))
    user = db.get(User, accountToken.idUsuario) if accountToken else None
    if user is None or not isPlatformAccount(user) or user.estado != "ACTIVO":
        raise _error("TOKEN_INVALIDO", "El enlace es inválido o ya fue usado.")
    if accountToken.fechaExpiracion <= nowForDb():
        raise _error("TOKEN_VENCIDO", "El enlace venció. Pedí uno nuevo.")
    authService._requirePasswordPolicy(password, user.usuario, user.correoElectronico, user.nombre, user.apellido)
    credential = db.scalar(select(LocalCredential).where(LocalCredential.idUsuario == user.idUsuario))
    if credential is None:
        raise _error("TOKEN_INVALIDO", "El enlace es inválido o ya fue usado.")
    now = nowForDb()
    used = db.execute(update(AccountToken).where(AccountToken.idTokenCuenta == accountToken.idTokenCuenta, AccountToken.fechaUso.is_(None))
                      .values(fechaUso=now).execution_options(synchronize_session=False)).rowcount
    if used != 1:
        db.rollback()
        raise _error("TOKEN_INVALIDO", "El enlace es inválido o ya fue usado.")
    credential.passwordHash = security.hashPassword(password)
    credential.intentosFallidosConsecutivos = 0
    credential.bloqueadoHasta = None
    credential.fechaUltimoCambioPassword = now
    _revokeSessions(db, user.idUsuario)
    registerEvent(db, "PERMISO", "RESTABLECER_PASSWORD_PLATAFORMA", True, user.idUsuario, "CredencialLocal",
                  credential.idCredencialLocal, modulo=MODULE)
    db.commit()
    emailService.sendEmailEventInBackground(EmailEventType.PASSWORD_CAMBIADA, user.correoElectronico,
                                            {"nombre": user.nombre, "fechaEvento": now, "urlSeguridad": emailService.frontendUrl("seguridad")})


def changeOwnPassword(db: Session, user: User, currentSession: UserSession, actual: str | None, new: str,
                      confirmation: str, codigo: str | None, codigoRecuperacion: str | None) -> None:
    """Cambia la propia contraseña: contraseña actual + MFA. Cierra las demás sesiones y conserva la actual."""
    requirePlatformAccount(db, user)
    if new != confirmation:
        raise _error("CONFIRMACION_INVALIDA", "La confirmación no coincide con la nueva contraseña.")
    credential = db.scalar(select(LocalCredential).where(LocalCredential.idUsuario == user.idUsuario))
    if credential is None:
        raise _error("CUENTA_SOLO_GOOGLE", "Tu cuenta ingresa con Google y no tiene contraseña local.")
    reauthenticate(db, user, Reauthentication(password=actual, codigo=codigo, codigoRecuperacion=codigoRecuperacion), "CAMBIAR_PASSWORD")
    authService._requirePasswordPolicy(new, user.usuario, user.correoElectronico, user.nombre, user.apellido)
    now = nowForDb()
    credential.passwordHash = security.hashPassword(new)
    credential.fechaUltimoCambioPassword = now
    db.execute(update(UserSession).where(UserSession.idUsuario == user.idUsuario, UserSession.idSesion != currentSession.idSesion,
                                         UserSession.fechaRevocacion.is_(None)).values(fechaRevocacion=now)
               .execution_options(synchronize_session=False))
    registerEvent(db, "PERMISO", "CAMBIAR_PASSWORD_PLATAFORMA", True, user.idUsuario, "CredencialLocal",
                  credential.idCredencialLocal, modulo=MODULE)
    db.commit()
    emailService.sendEmailEventInBackground(EmailEventType.PASSWORD_CAMBIADA, user.correoElectronico,
                                            {"nombre": user.nombre, "fechaEvento": now, "urlSeguridad": emailService.frontendUrl("seguridad")})


# --- Transferencia del control principal ----------------------------------------------------------------------


def _transferRead(db: Session, transfer: PlatformTransfer, viewer: User) -> TransferRead:
    return TransferRead(
        idTransferenciaAdministracion=transfer.idTransferenciaAdministracion, estado=transfer.estado,
        fechaSolicitud=transfer.fechaSolicitud, fechaRespuesta=transfer.fechaRespuesta,
        origenNombre=_fullName(db.get(User, transfer.idUsuarioOrigen)), destinoNombre=_fullName(db.get(User, transfer.idUsuarioDestino)),
        idUsuarioOrigen=transfer.idUsuarioOrigen, idUsuarioDestino=transfer.idUsuarioDestino,
        esOrigen=transfer.idUsuarioOrigen == viewer.idUsuario, esDestino=transfer.idUsuarioDestino == viewer.idUsuario)


def _pendingFor(db: Session, user: User) -> TransferRead | None:
    transfer = db.scalar(select(PlatformTransfer).where(
        PlatformTransfer.estado == "PENDIENTE",
        or_(PlatformTransfer.idUsuarioOrigen == user.idUsuario, PlatformTransfer.idUsuarioDestino == user.idUsuario)))
    return _transferRead(db, transfer, user) if transfer else None


def transferOverview(db: Session, actor: User) -> TransferOverview:
    requirePlatformAccount(db, actor)
    pending = _pendingFor(db, actor)
    eligible: list[EligibleModerator] = []
    history: list[TransferRead] = []
    if actor.tipoCuenta == ADMIN:
        for candidate in db.scalars(select(User).where(User.tipoCuenta == MOD, User.estado == "ACTIVO").order_by(User.apellido, User.nombre)):
            if mfa.isEnabled(db, candidate):
                eligible.append(EligibleModerator(idUsuario=candidate.idUsuario, nombre=candidate.nombre, apellido=candidate.apellido))
        history = [_transferRead(db, t, actor) for t in db.scalars(
            select(PlatformTransfer).order_by(PlatformTransfer.fechaSolicitud.desc()).limit(20))]
    return TransferOverview(pendiente=pending, elegibles=eligible, historial=history)


def startTransfer(db: Session, actor: User, idDestino: uuid.UUID, reauth: Reauthentication) -> TransferRead:
    requirePermission(db, actor, "TRANSFERIR_ADMINISTRACION")
    requireMfaEnabled(db, actor)
    reauthenticate(db, actor, reauth, "TRANSFERIR_ADMINISTRACION")
    target = db.get(User, idDestino)
    if target is None or target.tipoCuenta != MOD or target.idUsuario == actor.idUsuario:
        raise _error("DESTINATARIO_INVALIDO", "Elegí un moderador del sistema existente.")
    if target.estado != "ACTIVO":
        raise _error("DESTINATARIO_INACTIVO", "El moderador elegido no tiene la cuenta activa.")
    if not mfa.isEnabled(db, target):
        raise _error("DESTINATARIO_SIN_MFA", "El moderador elegido todavía no activó la verificación en dos pasos.")
    transfer = PlatformTransfer(idUsuarioOrigen=actor.idUsuario, idUsuarioDestino=target.idUsuario, estado="PENDIENTE",
                                fechaSolicitud=nowForDb())
    try:
        db.add(transfer)
        db.flush()
        registerEvent(db, "PERMISO", "SOLICITAR_TRANSFERENCIA_ADMINISTRACION", True, actor.idUsuario, "TransferenciaAdministracion",
                      transfer.idTransferenciaAdministracion, modulo=MODULE,
                      datosNuevos={"idUsuarioDestino": str(target.idUsuario)})
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _error("TRANSFERENCIA_PENDIENTE", "Ya hay una transferencia de administración pendiente de respuesta.") from error
    emailService.sendEmailEventInBackground(
        EmailEventType.TRANSFERENCIA_ADMIN_SOLICITADA, target.correoElectronico,
        {"nombre": target.nombre, "nombreAdministrador": _fullName(actor) or "El administrador", "fechaEvento": nowForDb(),
         "urlTransferencia": emailService.frontendUrl("plataformaTransferencia")})
    return _transferRead(db, transfer, actor)


def cancelTransfer(db: Session, actor: User, reauth: Reauthentication) -> TransferRead:
    requirePermission(db, actor, "TRANSFERIR_ADMINISTRACION")
    requireMfaEnabled(db, actor)
    reauthenticate(db, actor, reauth, "CANCELAR_TRANSFERENCIA_ADMINISTRACION")
    transfer = db.scalar(select(PlatformTransfer).where(PlatformTransfer.estado == "PENDIENTE", PlatformTransfer.idUsuarioOrigen == actor.idUsuario))
    if transfer is None:
        raise _error("TRANSFERENCIA_NO_ENCONTRADA", "No hay una transferencia pendiente para cancelar.")
    if not _close(db, transfer, "CANCELADA"):
        db.rollback()
        raise _error("TRANSFERENCIA_NO_PENDIENTE", "La transferencia ya fue respondida.")
    registerEvent(db, "PERMISO", "CANCELAR_TRANSFERENCIA_ADMINISTRACION", True, actor.idUsuario, "TransferenciaAdministracion",
                  transfer.idTransferenciaAdministracion, modulo=MODULE)
    db.commit()
    db.refresh(transfer)
    return _transferRead(db, transfer, actor)


def _close(db: Session, transfer: PlatformTransfer, state: str) -> bool:
    """Cierra la solicitud solo si sigue PENDIENTE (dos respuestas simultáneas no se aplican dos veces)."""
    return db.execute(update(PlatformTransfer).where(
        PlatformTransfer.idTransferenciaAdministracion == transfer.idTransferenciaAdministracion, PlatformTransfer.estado == "PENDIENTE")
        .values(estado=state, fechaRespuesta=nowForDb()).execution_options(synchronize_session=False)).rowcount == 1


def respondTransfer(db: Session, actor: User, accept: bool, reauth: Reauthentication) -> TransferRead:
    """El destinatario acepta o rechaza. Aceptar cambia ambos roles en UNA transacción; nunca queda la plataforma sin
    administrador ni con dos (el índice único filtrado lo garantiza)."""
    requirePlatformAccount(db, actor)
    requireMfaEnabled(db, actor)
    transfer = db.scalar(select(PlatformTransfer).where(PlatformTransfer.estado == "PENDIENTE", PlatformTransfer.idUsuarioDestino == actor.idUsuario))
    if transfer is None:
        raise _error("TRANSFERENCIA_NO_ENCONTRADA", "No tenés una transferencia de administración pendiente.")
    reauthenticate(db, actor, reauth, "RESPONDER_TRANSFERENCIA_ADMINISTRACION")
    origin = db.get(User, transfer.idUsuarioOrigen)
    now = nowForDb()
    if not accept:
        if not _close(db, transfer, "RECHAZADA"):
            db.rollback()
            raise _error("TRANSFERENCIA_NO_PENDIENTE", "La transferencia ya fue respondida.")
        registerEvent(db, "PERMISO", "RECHAZAR_TRANSFERENCIA_ADMINISTRACION", True, actor.idUsuario, "TransferenciaAdministracion",
                      transfer.idTransferenciaAdministracion, modulo=MODULE)
        db.commit()
        _notifyResponse(origin, actor, False, now)
        db.refresh(transfer)
        return _transferRead(db, transfer, actor)

    if origin is None or origin.tipoCuenta != ADMIN or origin.estado != "ACTIVO":
        _close(db, transfer, "CANCELADA")
        db.commit()
        raise _error("TRANSFERENCIA_OBSOLETA", "Quien te la ofreció ya no es el administrador del sistema.")
    if actor.tipoCuenta != MOD or actor.estado != "ACTIVO":
        raise _error("PERMISO_INSUFICIENTE", "Tu cuenta ya no puede recibir la administración.")
    try:
        if not _close(db, transfer, "ACEPTADA"):
            db.rollback()
            raise _error("TRANSFERENCIA_NO_PENDIENTE", "La transferencia ya fue respondida.")
        # Primero se baja al administrador actual y luego se sube al destinatario: el índice único nunca se viola
        # y, si algo falla, la transacción completa se revierte (queda el administrador original).
        demoted = db.execute(update(User).where(User.idUsuario == origin.idUsuario, User.tipoCuenta == ADMIN)
                             .values(tipoCuenta=MOD, fechaActualizacion=now).execution_options(synchronize_session=False)).rowcount
        promoted = db.execute(update(User).where(User.idUsuario == actor.idUsuario, User.tipoCuenta == MOD, User.estado == "ACTIVO")
                              .values(tipoCuenta=ADMIN, fechaActualizacion=now).execution_options(synchronize_session=False)).rowcount
        if demoted != 1 or promoted != 1:
            db.rollback()
            raise _error("TRANSFERENCIA_OBSOLETA", "Los roles cambiaron mientras tanto: la transferencia no se aplicó.")
        registerEvent(db, "PERMISO", "ACEPTAR_TRANSFERENCIA_ADMINISTRACION", True, actor.idUsuario, "TransferenciaAdministracion",
                      transfer.idTransferenciaAdministracion, modulo=MODULE,
                      datosPrevios={"administrador": str(origin.idUsuario)}, datosNuevos={"administrador": str(actor.idUsuario)})
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _error("TRANSFERENCIA_OBSOLETA", "Ya existe otro administrador del sistema: la transferencia no se aplicó.") from error
    db.expire_all()
    _notifyResponse(origin, actor, True, now)
    transfer = db.get(PlatformTransfer, transfer.idTransferenciaAdministracion)
    return _transferRead(db, transfer, db.get(User, actor.idUsuario))


def _notifyResponse(origin: User | None, actor: User, accepted: bool, now: datetime) -> None:
    if origin is not None:
        emailService.sendEmailEventInBackground(
            EmailEventType.TRANSFERENCIA_ADMIN_RESPONDIDA, origin.correoElectronico,
            {"nombre": origin.nombre, "aceptada": accepted, "nombreDestinatario": _fullName(actor) or "El moderador", "fechaEvento": now})


# --- Inicialización segura del primer administrador ------------------------------------------------------------


def initializeFirstAdmin(db: Session, nombre: str, apellido: str, correo: str) -> tuple[User, str, datetime, bool]:
    """Crea (o reenvía la invitación de) el PRIMER administrador. Solo se ejecuta desde el servidor (comando
    app/cli/initAdmin.py): no existe ninguna ruta pública. Sin contraseñas ni secretos en el código: la persona
    define la suya con el enlace de un solo uso y activa MFA antes de operar.

    Devuelve (usuario, enlace, vencimiento, correoEnviado). Se niega si ya hay un administrador activo, si hay otra
    invitación de administrador pendiente a un correo distinto o si el correo pertenece a una cuenta existente."""
    active = db.scalar(select(User).where(User.tipoCuenta == ADMIN, User.estado == "ACTIVO"))
    if active is not None:
        raise _error("ADMINISTRADOR_EXISTENTE", "Ya existe un administrador del sistema activo: la inicialización no se repite.")
    pending = db.scalar(select(User).where(User.tipoCuenta == ADMIN, User.estado == "PENDIENTE"))
    if pending is None and db.scalar(select(User.idUsuario).where(User.tipoCuenta == ADMIN, User.estado != "ELIMINADO")) is not None:
        # Hay un administrador no activo (p. ej. con el acceso bloqueado): UX_Usuario_administradorUnico lo cuenta como vigente.
        raise _error("ADMINISTRADOR_NO_ACTIVO", "Existe un administrador del sistema sin acceso. Para recuperarlo o reemplazarlo usá "
                                                 "app.cli.recoverAdmin; la inicialización solo sirve cuando no hay ninguno.")
    existing = db.scalar(select(User).where(User.correoElectronico == correo, User.estado != "ELIMINADO"))
    if pending is not None and pending.correoElectronico != correo:
        raise _error("ADMINISTRADOR_PENDIENTE", "Hay una invitación de administrador pendiente para otro correo.")
    if existing is not None and existing.idUsuario != (pending.idUsuario if pending else None):
        raise _error("CORREO_REGISTRADO", "Ese correo ya pertenece a una cuenta de GlucoLume.")
    user = pending
    try:
        if user is None:
            user = User(nombre=nombre, apellido=apellido, correoElectronico=correo, tipoCuenta=ADMIN, estado="PENDIENTE")
            db.add(user)
            db.flush()
        token, expires = _newActivationToken(db, user)
        registerEvent(db, "PERMISO", "INICIALIZAR_ADMINISTRADOR", True, user.idUsuario, "Usuario", user.idUsuario, modulo=MODULE,
                      datosNuevos={"rol": ADMIN, "reinvitacion": pending is not None})
        db.commit()
    except IntegrityError as error:  # otra inicialización simultánea ganó: el índice único deja un solo administrador vigente
        db.rollback()
        raise _error("ADMINISTRADOR_EXISTENTE", "Otra inicialización se adelantó: ya existe un administrador del sistema.") from error
    sent = _sendInvitation(user, token, expires)
    return user, activationLink(token), expires, sent


# --- Recuperación controlada de la administración --------------------------------------------------------------
#
# Solo desde el servidor (app/cli/recoverAdmin.py), nunca por HTTP ni con una contraseña maestra: quien la ejecuta ya controla el entorno
# (como en initAdmin), debe indicar el motivo y confirmar escribiendo el correo, y todo queda en Auditoria (módulo PLATAFORMA) sin secretos.
# No usa tablas nuevas: reutiliza el rol, el índice único UX_Usuario_administradorUnico y los enlaces de un solo uso de la invitación.
#   - replaceAdministrator: otra persona pasa a ser la ÚNICA administradora. Debe ser moderadora del sistema ACTIVA y con MFA habilitada. En una
#     sola transacción baja al administrador anterior y sube a la persona elegida (UPDATE condicionados al rol y al estado vigentes): dos
#     recuperaciones simultáneas no pueden dejar dos administradores, y si algo falla no cambia nada. El anterior queda sin acceso (BLOQUEADO,
#     sesiones cerradas) o, a pedido, como moderador.
#   - reinviteAdministrator: la MISMA persona recupera el acceso a su cuenta (pérdida de contraseña o del segundo factor sin otra vía): la cuenta
#     vuelve a PENDIENTE, se cierran sus sesiones y recibe un enlace de un solo uso para elegir una contraseña nueva; con `resetMfa` se elimina su
#     factor TOTP y deberá configurarlo de nuevo antes de operar.


def _serverContext() -> dict:
    """Desde dónde se ejecutó: usuario del sistema operativo y equipo del servidor. Sin secretos ni datos de la persona afectada."""
    try:
        import getpass
        import socket
        return {"origen": "SERVIDOR", "usuarioSistema": getpass.getuser()[:60], "equipo": socket.gethostname()[:60]}
    except Exception:  # noqa: BLE001 - la auditoría nunca debe impedir una recuperación legítima
        return {"origen": "SERVIDOR"}


def _denyRecovery(db: Session, action: str, motivo: str | None, error: AuthError, target: User | None = None) -> AuthError:
    """Un intento de recuperación rechazado también queda auditado (con el motivo del rechazo y el contexto del servidor)."""
    db.rollback()
    registerEvent(db, "PERMISO", action, False, None, "Usuario", target.idUsuario if target is not None else None, modulo=MODULE,
                  observacion=f"Rechazada: {error.code}. Motivo declarado: {(motivo or '').strip()[:200]}", datosNuevos=_serverContext())
    db.commit()
    return error


def _currentAdministrator(db: Session) -> User:
    admin = db.scalar(select(User).where(User.tipoCuenta == ADMIN, User.estado != "ELIMINADO"))
    if admin is None:
        raise _error("SIN_ADMINISTRADOR", "No hay un administrador del sistema para recuperar: usá app.cli.initAdmin.")
    if admin.estado == "PENDIENTE":
        raise _error("ADMINISTRADOR_PENDIENTE", "El administrador todavía no activó su cuenta: renová la invitación con app.cli.initAdmin.")
    return admin


def replaceAdministrator(db: Session, destinoCorreo: str, motivo: str, keepPreviousAsModerator: bool = False) -> tuple[User, User]:
    """Hace administrador a una moderadora/un moderador del sistema elegible y retira al administrador anterior. Devuelve (anterior, nuevo)."""
    if not motivo or not motivo.strip():
        raise _error("MOTIVO_REQUERIDO", "Indicá el motivo de la recuperación.")
    ACTION = "RECUPERAR_ADMINISTRACION_PLATAFORMA"
    try:
        previous = _currentAdministrator(db)
    except AuthError as error:
        raise _denyRecovery(db, ACTION, motivo, error) from error
    target = db.scalar(select(User).where(User.correoElectronico == destinoCorreo, User.estado != "ELIMINADO"))
    invalid = None
    if target is None or target.tipoCuenta != MOD:
        invalid = _error("DESTINATARIO_INVALIDO", "El reemplazo debe ser un moderador del sistema existente.")
    elif target.estado != "ACTIVO":
        invalid = _error("DESTINATARIO_INACTIVO", "El moderador elegido no tiene la cuenta activa.")
    elif not mfa.isEnabled(db, target):
        invalid = _error("DESTINATARIO_SIN_MFA", "El moderador elegido todavía no activó la verificación en dos pasos.")
    elif target.idUsuario == previous.idUsuario:
        invalid = _error("DESTINATARIO_INVALIDO", "La persona elegida ya es el administrador.")
    if invalid is not None:
        raise _denyRecovery(db, ACTION, motivo, invalid, target)
    now = nowForDb()
    previousState = previous.estado
    try:
        # Primero se baja al anterior y recién después se sube al nuevo: el índice único nunca ve dos y, si un UPDATE no alcanza exactamente una
        # fila (otra recuperación o transferencia ganó la carrera), se revierte todo.
        demoted = db.execute(update(User).where(User.idUsuario == previous.idUsuario, User.tipoCuenta == ADMIN)
                             .values(tipoCuenta=MOD, estado="ACTIVO" if keepPreviousAsModerator and previousState == "ACTIVO" else "BLOQUEADO",
                                     fechaActualizacion=now).execution_options(synchronize_session=False)).rowcount
        promoted = db.execute(update(User).where(User.idUsuario == target.idUsuario, User.tipoCuenta == MOD, User.estado == "ACTIVO")
                              .values(tipoCuenta=ADMIN, fechaActualizacion=now).execution_options(synchronize_session=False)).rowcount
        if demoted != 1 or promoted != 1:
            raise _denyRecovery(db, ACTION, motivo, _error(
                "RECUPERACION_OBSOLETA", "Los roles cambiaron mientras tanto: no se aplicó ningún cambio. Revisá el estado e intentá de nuevo."))
        _revokeSessions(db, previous.idUsuario)
        _revokeSessions(db, target.idUsuario)  # la sesión del nuevo administrador se abre de nuevo con su rol vigente
        db.execute(update(PlatformTransfer).where(PlatformTransfer.estado == "PENDIENTE").values(estado="CANCELADA", fechaRespuesta=now)
                   .execution_options(synchronize_session=False))
        registerEvent(db, "PERMISO", "RECUPERAR_ADMINISTRACION_PLATAFORMA", True, None, "Usuario", target.idUsuario, modulo=MODULE,
                      observacion=f"Motivo: {motivo.strip()[:300]}",
                      datosPrevios={"administrador": str(previous.idUsuario)},
                      datosNuevos={"administrador": str(target.idUsuario), "anteriorComoModerador": keepPreviousAsModerator, **_serverContext()})
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _error("RECUPERACION_OBSOLETA", "Ya existe otro administrador del sistema: no se aplicó ningún cambio.") from error
    db.expire_all()
    previous, target = db.get(User, previous.idUsuario), db.get(User, target.idUsuario)
    if previous.estado == "BLOQUEADO" and previous.correoElectronico:
        emailService.sendEmailEventInBackground(EmailEventType.ACCESO_PLATAFORMA_REVOCADO, previous.correoElectronico,
                                                {"nombre": previous.nombre, "fechaEvento": now})
    if target.correoElectronico:  # quien pasa a ser administrador se entera del cambio (rol, fecha y qué hacer); sin secretos
        emailService.sendEmailEventInBackground(EmailEventType.ADMINISTRACION_ASIGNADA, target.correoElectronico,
                                                {"nombre": target.nombre, "fechaEvento": now, "urlAcceso": emailService.frontendUrl("plataformaLogin")})
    return previous, target


def reinviteAdministrator(db: Session, motivo: str, resetMfa: bool = False) -> tuple[User, str, datetime, bool]:
    """La persona administradora recupera su acceso con un enlace de un solo uso (y, si lo pide, empezando de nuevo con el segundo factor).
    Devuelve (usuario, enlace, vencimiento, correoEnviado)."""
    if not motivo or not motivo.strip():
        raise _error("MOTIVO_REQUERIDO", "Indicá el motivo de la recuperación.")
    try:
        admin = _currentAdministrator(db)
    except AuthError as error:
        raise _denyRecovery(db, "REINVITAR_ADMINISTRADOR_PLATAFORMA", motivo, error) from error
    now = nowForDb()
    if db.execute(update(User).where(User.idUsuario == admin.idUsuario, User.tipoCuenta == ADMIN, User.estado.in_(("ACTIVO", "BLOQUEADO")))
                  .values(estado="PENDIENTE", fechaActualizacion=now).execution_options(synchronize_session=False)).rowcount != 1:
        raise _denyRecovery(db, "REINVITAR_ADMINISTRADOR_PLATAFORMA", motivo,
                            _error("RECUPERACION_OBSOLETA", "El estado del administrador cambió mientras tanto: intentá de nuevo."), admin)
    _revokeSessions(db, admin.idUsuario)
    if resetMfa:
        factors = select(MfaFactor.idFactorMfa).where(MfaFactor.idUsuario == admin.idUsuario)
        db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.idFactorMfa.in_(factors)))
        db.execute(delete(MfaFactor).where(MfaFactor.idUsuario == admin.idUsuario))
    db.execute(delete(AccountToken).where(AccountToken.idUsuario == admin.idUsuario, AccountToken.fechaUso.is_(None),
                                          AccountToken.tipo == TipoTokenCuenta.RECUPERACION_PASSWORD))
    token, expires = _newActivationToken(db, admin)
    registerEvent(db, "PERMISO", "REINVITAR_ADMINISTRADOR_PLATAFORMA", True, None, "Usuario", admin.idUsuario, modulo=MODULE,
                  observacion=f"Motivo: {motivo.strip()[:300]}", datosNuevos={"reinicioMfa": resetMfa, **_serverContext()})
    db.commit()
    db.refresh(admin)
    sent = _sendInvitation(admin, token, expires)
    return admin, activationLink(token), expires, sent
