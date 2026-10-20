# AccountActivation - Activación de una cuenta creada por una invitación institucional
#
# La persona abre el enlace del correo (/activar-cuenta?token=...), ve quién la invitó y elige su nombre de usuario
# y su contraseña (con la misma política que el registro). Al activar: CredencialLocal nueva, Usuario ACTIVO (el
# enlace prueba que controla el correo), token consumido y sesión abierta. La invitación institucional sigue
# PENDIENTE: la acepta o rechaza después, desde Instituciones. Alternativa: ingresar con Google con ese mismo correo
# verificado (app/services/auth.py, _linkOrCreateGoogleUser).

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.exceptions import AuthError
from app.emails.formatting import maskEmail
from app.models.accountToken import AccountToken
from app.models.consent import TipoConsentimiento
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.localCredential import LocalCredential
from app.models.user import User
from app.schemas.auth import ActivationInfo, ActivationInvitation, LoginResponse
from app.services import accountGrace
from app.services import auth as authService
from app.services import consent as consentService
from app.services.audit import registerEvent
from app.services.invitedAccounts import findActivationToken, hasLiveInvitation, isInvitedPendingAccount
from app.utils.timeZone import nowForDb
from app.utils.userAgent import ClientInfo

INVALID_MESSAGE = "El enlace de activación es inválido o ya fue usado."
NOT_LIVE_MESSAGE = "La invitación ya no está vigente. Pedí a la institución que te envíe una nueva."
EXPIRED_MESSAGE = "El enlace de activación venció. Pedí a la institución que te reenvíe la invitación."


def _load(db: Session, token: str) -> tuple[AccountToken, User]:
    accountToken = findActivationToken(db, token)
    user = db.get(User, accountToken.idUsuario) if accountToken else None
    if user is None or not isInvitedPendingAccount(db, user):
        raise AuthError("TOKEN_INVALIDO", INVALID_MESSAGE)
    now = nowForDb()
    if accountToken.fechaExpiracion <= now:
        raise AuthError("TOKEN_VENCIDO", EXPIRED_MESSAGE)
    if not hasLiveInvitation(db, user, now):
        # Invitación cancelada, rechazada o vencida: el enlace no activa la cuenta ni otorga nada de la institución. Si la institución vuelve a
        # invitar, recibe un enlace nuevo; si no, la cuenta pendiente se depura al vencer el enlace (services/pendingAccounts.py).
        raise AuthError("INVITACION_NO_VIGENTE", NOT_LIVE_MESSAGE)
    return accountToken, user


def checkActivation(db: Session, token: str) -> ActivationInfo:
    """Datos para la pantalla de activación: nombre, correo enmascarado e invitaciones pendientes."""
    _, user = _load(db, token)
    rows = db.execute(
        select(Institution.nombre, InstitutionUser.rolInstitucion)
        .join(InstitutionUser, InstitutionUser.idInstitucion == Institution.idInstitucion)
        .where(InstitutionUser.idUsuarioInvitado == user.idUsuario, InstitutionUser.estadoRelacion == "PENDIENTE",
               Institution.estado == "ACTIVA")
    ).all()
    return ActivationInfo(
        nombre=user.nombre, apellido=user.apellido, correoEnmascarado=maskEmail(user.correoElectronico),
        invitaciones=[ActivationInvitation(nombreInstitucion=row[0], rolInstitucion=row[1]) for row in rows],
    )


def completeActivation(
    db: Session, token: str, usuario: str, password: str, clientInfo: ClientInfo | None = None,
    aceptaPolitica: bool = False,
) -> LoginResponse:
    """Activa la cuenta con las credenciales elegidas por la persona y abre su sesión. Una sola transacción.

    Activar una cuenta invitada equivale a registrarse: exige confirmar la Política de Privacidad (queda registrado)."""
    accountToken, user = _load(db, token)
    consentService.requirePolicyAccepted(aceptaPolitica)
    usuario = usuario.strip()
    authService._requirePasswordPolicy(password, usuario, user.correoElectronico, user.nombre, user.apellido)
    if db.scalar(select(User.idUsuario).where(User.usuario == usuario, User.idUsuario != user.idUsuario)):
        raise AuthError("USUARIO_REGISTRADO", "El nombre de usuario ya está registrado.")
    now = nowForDb()
    try:
        # Condicionado: si el enlace se usó en paralelo o la cuenta ya se activó (p. ej. con Google), no se aplica.
        used = db.execute(
            update(AccountToken)
            .where(AccountToken.idTokenCuenta == accountToken.idTokenCuenta, AccountToken.fechaUso.is_(None))
            .values(fechaUso=now).execution_options(synchronize_session=False)
        ).rowcount
        activated = db.execute(
            update(User)
            .where(User.idUsuario == user.idUsuario, User.estado == "PENDIENTE")
            .values(estado="ACTIVO", usuario=usuario, fechaActualizacion=now).execution_options(synchronize_session=False)
        ).rowcount
        if used != 1 or activated != 1:
            db.rollback()
            raise AuthError("TOKEN_INVALIDO", INVALID_MESSAGE)
        db.add(LocalCredential(idUsuario=user.idUsuario, passwordHash=security.hashPassword(password)))
        consentService.record(db, user, TipoConsentimiento.POLITICA_PRIVACIDAD, True)
        registerEvent(db, "CRUD", "ACTIVAR_CUENTA_INVITADA", True, user.idUsuario, "Usuario", user.idUsuario,
                      datosNuevos={"estado": "ACTIVO", "metodo": "CONTRASENA"})
        # Habilitada sin ninguna vinculación activa (la invitación sigue pendiente hasta que la acepte): empieza el período de gracia.
        accountGrace.startIfOrphaned(db, user.idUsuario, now, user.idUsuario, accountGrace.ORIGEN_ACTIVACION)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise AuthError("USUARIO_REGISTRADO", "El nombre de usuario ya está registrado.") from error
    db.refresh(user)
    registerEvent(db, "LOGIN", authService.ACCION_LOGIN_ACTIVACION, True, user.idUsuario, datosNuevos={"primerFactor": "enlace"})  # abre sesión: es un ingreso
    return authService.issueSession(db, user, "Activación de la cuenta", clientInfo)
