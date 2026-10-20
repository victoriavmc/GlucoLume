# InvitedAccounts - Cuentas creadas por una invitación institucional y todavía sin activar
#
# Una institución puede incorporar a una persona sin cuenta: se crea un Usuario USUARIO_INSTITUCIONAL PENDIENTE sin
# credenciales (ni contraseña ni identidad de Google) y un TokenCuenta ACTIVACION_CUENTA de un solo uso. Mientras
# no se active no puede iniciar sesión ni ejercer permisos (el vínculo institucional sigue PENDIENTE).
#
# Módulo sin dependencias de servicios: lo usan institution.py (al invitar), auth.py (registro y Google) y
# accountActivation.py (activación), sin importaciones circulares.

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.models.accountToken import AccountToken, TipoTokenCuenta
from app.models.externalIdentity import ExternalIdentity
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.localCredential import LocalCredential
from app.models.user import User

TIPO_INSTITUCIONAL = "USUARIO_INSTITUCIONAL"
ESTADO_PENDIENTE = "PENDIENTE"
TOKEN_ACTIVACION = TipoTokenCuenta.ACTIVACION_CUENTA
INVITATION_VALIDITY_DAYS = 7  # vigencia de una invitación institucional (la usa institution.py)

INVITED_ACCOUNT_MESSAGE = (
    "Ya hay una invitación a GlucoLume para este correo. Activá tu cuenta desde el enlace que te enviamos por correo."
)


def isInvitedPendingAccount(db: Session, user: User) -> bool:
    """PENDIENTE, institucional y sin credencial local ni identidad externa (la creó una invitación)."""
    return (
        user.estado == ESTADO_PENDIENTE
        and user.tipoCuenta == TIPO_INSTITUCIONAL
        and db.scalar(select(LocalCredential.idCredencialLocal).where(LocalCredential.idUsuario == user.idUsuario)) is None
        and db.scalar(select(ExternalIdentity.idIdentidadExterna).where(ExternalIdentity.idUsuario == user.idUsuario)) is None
    )


def hasLiveInvitation(db: Session, user: User, now: datetime) -> bool:
    """Queda al menos UNA invitación institucional que se puede aceptar: PENDIENTE, sin vencer y de una institución ACTIVA. El enlace de
    activación existe para responder a esa invitación: si fue cancelada, rechazada o venció, el enlace no habilita la cuenta ni le da ningún
    permiso de la institución."""
    return db.scalar(
        select(InstitutionUser.idInstitucionUsuario)
        .join(Institution, Institution.idInstitucion == InstitutionUser.idInstitucion)
        .where(InstitutionUser.idUsuarioInvitado == user.idUsuario, InstitutionUser.estadoRelacion == "PENDIENTE",
               InstitutionUser.fechaInvitacion > now - timedelta(days=INVITATION_VALIDITY_DAYS), Institution.estado == "ACTIVA")
        .limit(1)
    ) is not None


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
