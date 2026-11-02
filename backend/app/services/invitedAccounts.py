# InvitedAccounts - Cuentas creadas por una invitación institucional y todavía sin activar
#
# Una institución o un grupo familiar puede invitar a una persona sin cuenta: se crea un Usuario PENDIENTE sin
# credenciales (ni contraseña ni identidad de Google) y un TokenCuenta ACTIVACION_CUENTA de un solo uso. Institucional:
# USUARIO_INSTITUCIONAL. Grupo familiar: CONSUMIDOR_FINAL. Mientras no se active no puede iniciar sesión ni ejercer
# permisos (el vínculo, institucional o de grupo, sigue PENDIENTE).
#
# Módulo sin dependencias de servicios: lo usan institution.py (al invitar), auth.py (registro y Google) y
# accountActivation.py (activación), sin importaciones circulares.

from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core import security
from app.models.accountToken import AccountToken, TipoTokenCuenta
from app.models.externalIdentity import ExternalIdentity
from app.models.group import Group
from app.models.groupUser import GroupUser
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.localCredential import LocalCredential
from app.models.user import User

TIPO_INSTITUCIONAL = "USUARIO_INSTITUCIONAL"
TIPO_INDIVIDUAL = "CONSUMIDOR_FINAL"  # cuenta individual (grupo familiar)
TIPOS_INVITABLES = (TIPO_INSTITUCIONAL, TIPO_INDIVIDUAL)
ESTADO_PENDIENTE = "PENDIENTE"
TOKEN_ACTIVACION = TipoTokenCuenta.ACTIVACION_CUENTA
INVITATION_VALIDITY_DAYS = 7  # vigencia de una invitación (institucional y de grupo; la usan institution.py y group.py)

INVITED_ACCOUNT_MESSAGE = (
    "Ya hay una invitación a GlucoLume para este correo. Activá tu cuenta desde el enlace que te enviamos por correo."
)


def isInvitedPendingAccount(db: Session, user: User) -> bool:
    """PENDIENTE, de un tipo que una invitación puede crear y sin credencial local ni identidad externa (la creó una invitación)."""
    return (
        user.estado == ESTADO_PENDIENTE
        and user.tipoCuenta in TIPOS_INVITABLES
        and db.scalar(select(LocalCredential.idCredencialLocal).where(LocalCredential.idUsuario == user.idUsuario)) is None
        and db.scalar(select(ExternalIdentity.idIdentidadExterna).where(ExternalIdentity.idUsuario == user.idUsuario)) is None
    )


def hasLiveInvitation(db: Session, user: User, now: datetime) -> bool:
    """Queda al menos UNA invitación (institucional o de grupo) que se puede aceptar: PENDIENTE, sin vencer y de una institución o un
    grupo ACTIVO. El enlace de activación existe para responder a esa invitación: si fue cancelada, rechazada o venció, el enlace no
    habilita la cuenta ni le da ningún permiso."""
    institutional = db.scalar(
        select(InstitutionUser.idInstitucionUsuario)
        .join(Institution, Institution.idInstitucion == InstitutionUser.idInstitucion)
        .where(InstitutionUser.idUsuarioInvitado == user.idUsuario, InstitutionUser.estadoRelacion == "PENDIENTE",
               InstitutionUser.fechaInvitacion > now - timedelta(days=INVITATION_VALIDITY_DAYS), Institution.estado == "ACTIVA")
        .limit(1)
    )
    if institutional is not None:
        return True
    return db.scalar(
        select(GroupUser.idGrupoUsuario)
        .join(Group, Group.idGrupo == GroupUser.idGrupo)
        .where(GroupUser.idUsuario == user.idUsuario, GroupUser.estadoRelacion == "PENDIENTE",
               GroupUser.fechaInvitacion > now - timedelta(days=INVITATION_VALIDITY_DAYS), Group.estado == "ACTIVO")
        .limit(1)
    ) is not None


def issueActivationToken(db: Session, user: User, expiresAt: datetime) -> str:
    """Token de activación nuevo (solo se guarda su hash); invalida los anteriores sin usar. Lo confirma quien llama."""
    db.execute(delete(AccountToken).where(AccountToken.idUsuario == user.idUsuario, AccountToken.tipo == TOKEN_ACTIVACION,
                                          AccountToken.fechaUso.is_(None)))
    token = security.generateOpaqueToken()
    db.add(AccountToken(idUsuario=user.idUsuario, tipo=TOKEN_ACTIVACION, tokenHash=security.hashOpaqueToken(token),
                        fechaExpiracion=expiresAt))
    return token


def findActivationToken(db: Session, token: str) -> AccountToken | None:
    """Token de activación sin usar (vigente o no) a partir del valor recibido; solo se compara su hash."""
    return db.scalar(
        select(AccountToken).where(
            AccountToken.tokenHash == security.hashOpaqueToken(token),
            AccountToken.tipo == TOKEN_ACTIVACION,
            AccountToken.fechaUso.is_(None),
        )
    )


def hasValidActivationToken(db: Session, user: User, now: datetime) -> bool:
    """La cuenta tiene una invitación vigente (enlace de activación sin usar y sin vencer)."""
    return db.scalar(
        select(AccountToken.idTokenCuenta).where(
            AccountToken.idUsuario == user.idUsuario,
            AccountToken.tipo == TOKEN_ACTIVACION,
            AccountToken.fechaUso.is_(None),
            AccountToken.fechaExpiracion > now,
        )
    ) is not None
