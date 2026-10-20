# UnverifiedAccounts - Eliminación de cuentas locales no verificadas vencidas
#
# Una cuenta local registrada queda en estado PENDIENTE (equivalente a "pendiente de verificación";
# es el valor que admite CK_Usuario_estado) y tiene un plazo fijo desde Usuario.fechaCreacion para
# verificar el correo. Los reenvíos no extienden ese plazo. Vencido el plazo, la cuenta nunca llegó a
# ser operativa y se eliminan sus estructuras del módulo Cuenta/Auth. La fila del Usuario se borra si no
# dejó eventos de auditoría; si los dejó, queda como baja anónima (estado ELIMINADO, sin datos personales,
# igual que una baja pedida por el titular) y los eventos la siguen apuntando: la aplicación nunca
# modifica ni borra la auditoría (GL-03; solo la política de conservación, con su propia cuenta de base).
#
# Pensado para ejecutarse desde un job programado (ver backend/app/jobs/cleanupUnverifiedAccounts.py)
# y también desde las operaciones sensibles (login, verificación, reenvío, registro), para no depender
# de que el job haya corrido a tiempo.

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import getSettings
from app.models.accountToken import AccountToken
from app.models.audit import Audit
from app.models.consent import Consent
from app.models.externalIdentity import ExternalIdentity
from app.models.localCredential import LocalCredential
from app.models.mfaFactor import MfaFactor
from app.models.mfaRecoveryCode import MfaRecoveryCode
from app.models.user import User
from app.models.userSession import UserSession
from app.services.audit import registerEvent
from app.utils.timeZone import nowForDb

logger = logging.getLogger(__name__)

ESTADO_PENDIENTE = "PENDIENTE"
DEFAULT_BATCH_SIZE = 500


def verificationWindow() -> timedelta:
    return timedelta(hours=getSettings().EMAIL_VERIFICATION_EXPIRE_HOURS)


def verificationDeadline(user: User) -> datetime:
    """Límite para verificar (hora de Argentina): fechaCreacion + plazo. No depende de tokens ni reenvíos."""
    return user.fechaCreacion + verificationWindow()


# Solo los registros públicos pueden vencer por no verificar el correo. Una cuenta de plataforma (moderador/administrador) re-invitada también
# queda PENDIENTE con su credencial y su fechaCreacion original, pero su plazo es el de la invitación: no se purga como un registro sin verificar.
PUBLIC_ACCOUNT_TYPES = ("CONSUMIDOR_FINAL", "USUARIO_INSTITUCIONAL")


def isVerificationExpired(user: User, now: datetime | None = None) -> bool:
    return (user.estado == ESTADO_PENDIENTE and user.tipoCuenta in PUBLIC_ACCOUNT_TYPES
            and verificationDeadline(user) <= (now or nowForDb()))


def _isLocalOnly():
    """Condición SQL: cuenta de registro público con CredencialLocal y sin identidad externa (Google)."""
    return (
        User.tipoCuenta.in_(PUBLIC_ACCOUNT_TYPES),
        exists().where(LocalCredential.idUsuario == User.idUsuario),
        ~exists().where(ExternalIdentity.idUsuario == User.idUsuario),
    )


def deleteExpiredAccount(db: Session, idUsuario: uuid.UUID, now: datetime | None = None) -> bool:
    """Elimina una cuenta local pendiente y vencida en una sola transacción. Devuelve True si la eliminó.

    Bloquea la fila del Usuario y vuelve a comprobar las condiciones dentro de la transacción: si en
    paralelo la cuenta se verificó, no se elimina. Si otra entidad (de otro módulo) la referencia, la
    FK impide el borrado: se revierte todo y la cuenta queda para revisión.
    """
    now = now or nowForDb()
    cutoff = now - verificationWindow()
    db.rollback()  # partir de una transacción limpia
    try:
        user = db.scalar(
            select(User)
            .where(
                User.idUsuario == idUsuario,
                User.estado == ESTADO_PENDIENTE,
                User.fechaCreacion <= cutoff,
                *_isLocalOnly(),
            )
            # Bloqueo de la fila hasta el commit: una verificación simultánea espera y luego no
            # encuentra la cuenta (o la limpieza no la encuentra si la verificación ganó).
            .with_hint(User, "WITH (UPDLOCK, ROWLOCK)", "mssql")
            .with_for_update()
        )
        if user is None:
            db.rollback()
            return False

        factorIds = select(MfaFactor.idFactorMfa).where(MfaFactor.idUsuario == idUsuario)
        db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.idFactorMfa.in_(factorIds)))
        db.execute(delete(MfaFactor).where(MfaFactor.idUsuario == idUsuario))
        db.execute(delete(AccountToken).where(AccountToken.idUsuario == idUsuario))
        db.execute(delete(UserSession).where(UserSession.idUsuario == idUsuario))
        db.execute(delete(LocalCredential).where(LocalCredential.idUsuario == idUsuario))
        db.execute(delete(Consent).where(Consent.idUsuario == idUsuario))  # su registro se elimina con la cuenta
        # Auditoría: nunca se modifica (GL-03). Con eventos propios, la fila queda como baja anónima y la FK sigue siendo válida.
        if db.scalar(select(Audit.idAuditoria).where(Audit.idUsuario == idUsuario).limit(1)) is not None:  # SQL Server no admite SELECT EXISTS
            from app.services.accountDeletion import _anonymizeUser  # import diferido: accountDeletion importa auth

            _anonymizeUser(user, now)
        else:
            db.delete(user)
        db.flush()
        registerEvent(
            db, "CRUD", "ELIMINAR_CUENTA_NO_VERIFICADA_EXPIRADA", True, None, "Usuario", idUsuario,
            observacion="Cuenta local eliminada por no verificar el correo dentro del plazo (sin datos personales).",
        )
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        logger.warning("Cuenta no verificada idUsuario=%s referenciada por otro módulo; no se eliminó.", idUsuario)
        return False


def deleteExpiredAccounts(db: Session, now: datetime | None = None, batchSize: int = DEFAULT_BATCH_SIZE) -> int:
    """Elimina las cuentas locales pendientes cuyo plazo de verificación venció. Devuelve la cantidad."""
    now = now or nowForDb()
    cutoff = now - verificationWindow()
    candidates = db.scalars(
        select(User.idUsuario)
        .where(User.estado == ESTADO_PENDIENTE, User.fechaCreacion <= cutoff, *_isLocalOnly())
        .order_by(User.fechaCreacion)
        .limit(batchSize)
    ).all()
    return sum(deleteExpiredAccount(db, idUsuario, now) for idUsuario in candidates)
