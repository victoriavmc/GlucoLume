# PendingAccounts - Depuración de cuentas invitadas que nunca se activaron y ya no tienen salida
#
# Una invitación a una persona sin cuenta crea un Usuario USUARIO_INSTITUCIONAL PENDIENTE sin credenciales y un enlace de activación de 7 días.
# Esa cuenta todavía NO existe operativamente (no inicia sesión, no tiene permisos, no tiene plazo de gracia). Queda «sin salida» cuando
#   - no le queda ninguna invitación que pueda aceptar (cancelada, rechazada, vencida o de una institución cerrada) Y
#   - su enlace de activación ya venció (o no tiene).
# Entonces se depura: se anonimiza como cualquier cuenta eliminada (sin borrarla: la referencian InstitucionUsuario y Auditoria), lo que además
# libera el correo para un registro propio. Una cuenta con una invitación vigente o un enlace vigente NUNCA se toca, ni una cuenta ya
# habilitada, ni una PENDIENTE con credenciales (esa la gobierna la verificación de correo de unverifiedAccounts.py).
#
# Seguro ante concurrencia: la cuenta se bloquea, se revalida y se «reclama» con un UPDATE condicionado a que siga PENDIENTE; si la persona se
# activa o la institución la vuelve a invitar antes de que se complete, la depuración se retira. Auditoría: un evento por cuenta, sin datos personales.

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session

from app.models.accountToken import AccountToken
from app.models.externalIdentity import ExternalIdentity
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.localCredential import LocalCredential
from app.models.user import User
from app.services import accountDeletion, accountGrace
from app.services.audit import registerEvent
from app.services.invitedAccounts import INVITATION_VALIDITY_DAYS, TIPO_INSTITUCIONAL, TOKEN_ACTIVACION
from app.utils.dbRetry import retryOnDeadlock
from app.utils.timeZone import nowForDb

logger = logging.getLogger("glucolume.lifecycle")
ACCION = "DEPURAR_CUENTA_INVITADA_VENCIDA"
BATCH = 100


def _deadFilters(now: datetime):
    live = exists().where(
        InstitutionUser.idUsuarioInvitado == User.idUsuario, InstitutionUser.estadoRelacion == "PENDIENTE",
        InstitutionUser.fechaInvitacion > now - timedelta(days=INVITATION_VALIDITY_DAYS),
        InstitutionUser.idInstitucion == Institution.idInstitucion, Institution.estado == "ACTIVA")
    validLink = exists().where(AccountToken.idUsuario == User.idUsuario, AccountToken.tipo == TOKEN_ACTIVACION,
                               AccountToken.fechaUso.is_(None), AccountToken.fechaExpiracion > now)
    return (
        User.estado == "PENDIENTE", User.tipoCuenta == TIPO_INSTITUCIONAL,
        ~exists().where(LocalCredential.idUsuario == User.idUsuario), ~exists().where(ExternalIdentity.idUsuario == User.idUsuario),
        ~live, ~validLink,
    )


def candidates(db: Session, now: datetime, limit: int = BATCH) -> list[uuid.UUID]:
    return list(db.scalars(select(User.idUsuario).where(*_deadFilters(now)).order_by(User.fechaCreacion).limit(limit)))


@retryOnDeadlock
def purgeOne(db: Session, idUsuario: uuid.UUID, now: datetime) -> bool:
    user = accountGrace.lockUser(db, idUsuario)
    if user is None or idUsuario not in db.scalars(select(User.idUsuario).where(User.idUsuario == idUsuario, *_deadFilters(now))).all():
        db.rollback()
        return False  # se activó, la volvieron a invitar o ya fue depurada
    # Reclamo atómico: el UPDATE vuelve a exigir TODAS las condiciones (sin invitación vigente ni enlace vigente) en el momento de escribir. Si una
    # invitación nueva se confirmó entre la revalidación y este UPDATE, no actualiza nada y la depuración se retira.
    claimed = db.execute(
        update(User).where(User.idUsuario == idUsuario, *_deadFilters(now))
        .values(estado=accountDeletion.ESTADO_ELIMINADO, fechaEliminacion=now, fechaActualizacion=now)
        .execution_options(synchronize_session=False)).rowcount
    if claimed != 1:
        db.rollback()
        return False
    result = accountDeletion.anonymizeAccount(db, user, now)
    registerEvent(db, "CRUD", ACCION, True, None, "Usuario", idUsuario, datosPrevios={"estado": "PENDIENTE"},
                  datosNuevos={"estado": accountDeletion.ESTADO_ELIMINADO, "motivo": "INVITACION_Y_ENLACE_VENCIDOS",
                               "datosPersonales": "ANONIMIZADOS", "invitacionesCerradas": result.invitacionesCanceladas})
    db.commit()
    return True


def purgeDead(db: Session, now: datetime | None = None, limit: int = BATCH) -> int:
    """Depura las cuentas invitadas sin salida. Devuelve la cantidad. Un error en una cuenta no frena a las demás."""
    now = now or nowForDb()
    purged = 0
    for idUsuario in candidates(db, now, limit):
        try:
            purged += purgeOne(db, idUsuario, now)
        except Exception:  # noqa: BLE001 - se reintenta en la próxima pasada
            db.rollback()
            logger.exception("No se pudo depurar la cuenta invitada vencida idUsuario=%s", idUsuario)
    return purged
