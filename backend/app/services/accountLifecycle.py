# AccountLifecycle - Eliminación automática de cuentas institucionales al vencer el período de gracia
#
# Lo ejecuta el job app/jobs/accountLifecycle.py (un servicio aparte de Docker Compose, sin depender de que alguien inicie sesión).
# Para cada cuenta con Usuario.fechaVencimientoGracia vencida, EN SU PROPIA TRANSACCIÓN y con la fila de Usuario bloqueada (UPDLOCK):
#   1. vuelve a verificar: cuenta institucional, ACTIVA, plazo vencido, ninguna vinculación ACTIVA (ni reincorporación posterior) y sin
#      impedimentos de grupo;
#   2. aplica la misma anonimización que la eliminación voluntaria (accountDeletion.anonymizeAccount): Usuario ELIMINADO y anonimizado,
#      credenciales, MFA, Google, sesiones y tokens revocados, InstitucionUsuario conservada, invitaciones pendientes canceladas;
#   3. audita UN evento (ELIMINACION_AUTOMATICA_CUENTA) y, después del commit, avisa por correo con la dirección que tenía.
# Idempotente y seguro ante concurrencia: la cuenta ya eliminada deja de ser candidata, y una incorporación que gane la carrera (acepta la
# invitación bajo el mismo bloqueo de fila) cancela el plazo, así que la segunda verificación la descarta. Varias ejecuciones simultáneas
# no pueden eliminar dos veces ni enviar dos correos. Un error en una cuenta no frena a las demás y se reintenta en la próxima pasada; el
# FALLO se audita una vez por motivo y por día, sin repetirse en cada pasada.

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.emails.eventTypes import EmailEventType
from app.emails.formatting import maskEmail
from app.models.audit import Audit
from app.models.user import User
from app.services import accountDeletion, accountGrace, pendingAccounts
from app.services import email as emailService
from app.services.audit import registerEvent
from app.utils.dbRetry import retryOnDeadlock
from app.utils.timeZone import nowForDb

logger = logging.getLogger("glucolume.lifecycle")

ACCION_AUTOMATICA = "ELIMINACION_AUTOMATICA_CUENTA"
ORIGEN = "VENCIMIENTO_PERIODO_GRACIA"
BATCH = 100
AUTOMATIC_REASON = "Tu período de gracia de 30 días venció sin que te incorporaras a una institución, así que tu cuenta de GlucoLume se eliminó."

ELIMINADA = "ELIMINADA"
OMITIDA = "OMITIDA"
ERROR = "ERROR"


def candidates(db: Session, now: datetime, limit: int = BATCH) -> list[uuid.UUID]:
    """Cuentas institucionales ACTIVAS con un plazo REAL vencido (inicio y vencimiento cargados), las más antiguas primero. Una cuenta sin
    plazo nunca es candidata, aunque no tenga instituciones. Es solo una preselección: cada una se revalida."""
    return list(db.scalars(
        select(User.idUsuario).where(
            User.tipoCuenta == accountGrace.TIPO_INSTITUCIONAL, User.estado == accountGrace.ESTADO_ACTIVO,
            User.fechaInicioGracia.is_not(None), User.fechaVencimientoGracia.is_not(None), User.fechaVencimientoGracia <= now,
        ).order_by(User.fechaVencimientoGracia).limit(limit)))


def fullTermElapsed(user: User, now: datetime) -> bool:
    """El plazo es válido y se cumplieron los GRACE_DAYS días completos desde su inicio. Una fecha de vencimiento adelantada o inconsistente
    (menos de 30 días desde el inicio) no autoriza a eliminar la cuenta."""
    if user.fechaInicioGracia is None or user.fechaVencimientoGracia is None:
        return False
    minimum = user.fechaInicioGracia + timedelta(days=accountGrace.GRACE_DAYS)
    return user.fechaVencimientoGracia >= minimum and now >= minimum


def _failureAlreadyAudited(db: Session, idUsuario: uuid.UUID, reason: str, now: datetime) -> bool:
    return db.scalar(select(Audit.idAuditoria).where(
        Audit.accion == ACCION_AUTOMATICA, Audit.resultado == "FALLO", Audit.idRegistro == idUsuario,
        Audit.observacion == f"Motivo: {reason}", Audit.fechaHora >= now - timedelta(days=1)).limit(1)) is not None


def _auditFailure(db: Session, idUsuario: uuid.UUID, reason: str, now: datetime) -> None:
    if not _failureAlreadyAudited(db, idUsuario, reason, now):
        registerEvent(db, "CRUD", ACCION_AUTOMATICA, False, None, "Usuario", idUsuario, observacion=f"Motivo: {reason}",
                      datosNuevos={"origen": ORIGEN, "motivo": reason})
    db.commit()


@retryOnDeadlock
def deleteExpired(db: Session, idUsuario: uuid.UUID, now: datetime) -> tuple[str, str]:
    """Elimina y anonimiza UNA cuenta si, con la fila bloqueada, sigue cumpliendo todo. Devuelve (resultado, motivo)."""
    user = accountGrace.lockUser(db, idUsuario)
    if user is None or user.estado != accountGrace.ESTADO_ACTIVO:
        db.rollback()
        return OMITIDA, "YA_PROCESADA"
    if user.tipoCuenta != accountGrace.TIPO_INSTITUCIONAL:
        db.rollback()
        return OMITIDA, "TIPO_CUENTA"
    if user.fechaVencimientoGracia is None or user.fechaVencimientoGracia > now:
        db.rollback()
        return OMITIDA, "SIN_VENCIMIENTO"
    if not fullTermElapsed(user, now):
        db.rollback()
        _auditFailure(db, idUsuario, "PLAZO_INVALIDO", now)
        return OMITIDA, "PLAZO_INVALIDO"
    if accountGrace.activeBondCount(db, idUsuario) > 0:
        # Hay una vinculación efectiva y el plazo quedó sin cancelar (no debería ocurrir: se cancela al incorporarse): se corrige y no se elimina.
        accountGrace.cancelOnIncorporation(db, user, now)
        db.commit()
        return OMITIDA, "REINCORPORADA"
    blocker = accountDeletion.findBlocker(db, user)
    if blocker is not None:
        db.rollback()
        _auditFailure(db, idUsuario, blocker.code, now)
        return OMITIDA, blocker.code

    recipient, nombre = user.correoElectronico, user.nombre
    expired = user.fechaVencimientoGracia
    # Reclamo atómico: UPDATE condicionado al estado. Aunque el motor no bloquee la fila (o dos procesos lleguen a la vez), solo uno lo gana;
    # el otro ve 0 filas y se retira sin tocar nada ni enviar otro correo.
    claimed = db.execute(
        update(User)
        .where(User.idUsuario == idUsuario, User.estado == accountGrace.ESTADO_ACTIVO, User.fechaInicioGracia.is_not(None),
               User.fechaVencimientoGracia.is_not(None), User.fechaVencimientoGracia <= now)
        .values(estado=accountDeletion.ESTADO_ELIMINADO, fechaEliminacion=now, fechaActualizacion=now)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        return OMITIDA, "YA_PROCESADA"
    result = accountDeletion.anonymizeAccount(db, user, now)
    registerEvent(
        db, "CRUD", ACCION_AUTOMATICA, True, None, "Usuario", idUsuario,
        datosPrevios={"estado": accountDeletion.ESTADO_ACTIVO},
        datosNuevos={"estado": accountDeletion.ESTADO_ELIMINADO, "origen": ORIGEN, "fechaVencimientoGracia": expired.isoformat(),
                     "datosPersonales": "ANONIMIZADOS", "autenticacion": "REVOCADA", "vinculosConservados": result.vinculosConservados,
                     "invitacionesPendientesCanceladas": result.invitacionesCanceladas,
                     "gruposAbandonados": result.gruposAbandonados, "perfilesMedicionAnonimizados": result.perfilesAnonimizados},
    )
    db.commit()
    emailService.sendEmailEventInBackground(
        EmailEventType.CUENTA_ELIMINADA, recipient,
        {"nombre": nombre, "fechaEvento": now, "datosEliminados": accountDeletion.DELETED_DATA,
         "datosConservados": accountDeletion.RETAINED_MEASUREMENT_DATA if result.perfilesAnonimizados else None,
         "motivoEliminacion": AUTOMATIC_REASON},
    )
    return ELIMINADA, ORIGEN


def _label(user: User) -> str | None:
    return maskEmail(user.correoElectronico) if user.correoElectronico else None


def dryRun(db: Session, now: datetime | None = None) -> dict:
    """Qué haría una pasada ahora, SIN modificar nada (solo consultas; no bloquea filas, no audita, no envía correos).

    plazoVigente: cuentas con plazo en curso (con los días que les quedan). plazoVencido: las vencidas. seEliminarian: las vencidas que
    cumplen TODAS las condiciones (30 días completos, ningún vínculo activo, sin impedimentos). seOmitirian: las vencidas que no se
    eliminarían y por qué. sinPlazo: cuentas institucionales activas sin ninguna institución y SIN plazo: el servicio no las toca.
    """
    now = now or nowForDb()
    accounts = db.scalars(select(User).where(
        User.tipoCuenta == accountGrace.TIPO_INSTITUCIONAL, User.estado == accountGrace.ESTADO_ACTIVO)).all()
    valid, expired, would, skipped, noTerm = [], [], [], [], []
    for user in accounts:
        bonds = accountGrace.activeBondCount(db, user.idUsuario)
        if user.fechaVencimientoGracia is None:
            if bonds == 0:
                noTerm.append({"idUsuario": str(user.idUsuario), "correo": _label(user)})
            continue
        item = {"idUsuario": str(user.idUsuario), "correo": _label(user), "inicio": user.fechaInicioGracia.isoformat() if user.fechaInicioGracia else None,
                "vence": user.fechaVencimientoGracia.isoformat()}
        if user.fechaVencimientoGracia > now:
            valid.append({**item, "diasRestantes": accountGrace.graceOf(user, now).diasRestantes})
            continue
        expired.append(item)
        if bonds > 0:
            skipped.append({**item, "motivo": "REINCORPORADA"})
        elif not fullTermElapsed(user, now):
            skipped.append({**item, "motivo": "PLAZO_INVALIDO"})
        elif (blocker := accountDeletion.findBlocker(db, user)) is not None:
            skipped.append({**item, "motivo": blocker.code})
        else:
            would.append(item)
    dead = [{"idUsuario": str(i), "correo": _label(db.get(User, i))} for i in pendingAccounts.candidates(db, now, 10_000)]
    return {"plazoVigente": valid, "plazoVencido": expired, "seEliminarian": would, "seOmitirian": skipped, "sinPlazoNoSeTocan": noTerm,
            "pendientesSinSalidaSeDepurarian": dead}


def legacyAccounts(db: Session) -> list[User]:
    """Cuentas institucionales ACTIVAS sin ninguna vinculación activa y sin plazo (anteriores a la política de 30 días)."""
    return [user for user in db.scalars(select(User).where(
        User.tipoCuenta == accountGrace.TIPO_INSTITUCIONAL, User.estado == accountGrace.ESTADO_ACTIVO,
        User.fechaVencimientoGracia.is_(None)).order_by(User.fechaCreacion))
        if accountGrace.activeBondCount(db, user.idUsuario) == 0]


ORIGEN_REGULARIZACION = "REGULARIZACION_CUENTA_ANTERIOR"


def regularize(db: Session, now: datetime | None = None, apply: bool = False, only: uuid.UUID | None = None) -> list[dict]:
    """Otorga el período de gracia de 30 días a las cuentas anteriores a la política, contado desde AHORA (sin vencimientos retroactivos).

    Con apply=False solo informa el cambio exacto que se haría. Con apply=True escribe el plazo (un evento de auditoría por cuenta, origen
    REGULARIZACION_CUENTA_ANTERIOR) y envía el correo del plazo después del commit. Es idempotente: una cuenta que ya tiene plazo, o que
    se incorporó entre tanto, no se modifica.
    """
    now = now or nowForDb()
    report = []
    for candidate in legacyAccounts(db):
        if only is not None and candidate.idUsuario != only:
            continue  # autorización acotada a una sola cuenta: ninguna otra se modifica
        change = {"idUsuario": str(candidate.idUsuario), "correo": _label(candidate), "fechaInicioGracia": now.isoformat(),
                  "fechaVencimientoGracia": (now + timedelta(days=accountGrace.GRACE_DAYS)).isoformat()}
        if apply:
            started = accountGrace.startIfOrphaned(db, candidate.idUsuario, now, None, ORIGEN_REGULARIZACION)
            if started is None:
                db.rollback()
                change["aplicado"] = False
            else:
                db.commit()
                accountGrace.notifyStarted(started, now)
                change["aplicado"] = True
        report.append(change)
    return report


def sweep(db: Session, now: datetime | None = None, batch: int = BATCH) -> dict:
    """Una pasada. Nunca propaga el error de una cuenta: lo registra y sigue con las demás."""
    now = now or nowForDb()
    summary = {"revisadas": 0, "eliminadas": 0, "omitidas": 0, "errores": 0}
    for idUsuario in candidates(db, now, batch):
        summary["revisadas"] += 1
        try:
            outcome, _ = deleteExpired(db, idUsuario, now)
        except Exception:  # noqa: BLE001 - se reintenta en la próxima pasada
            db.rollback()
            logger.exception("No se pudo eliminar la cuenta vencida idUsuario=%s", idUsuario)
            summary["errores"] += 1
            try:
                _auditFailure(db, idUsuario, "ERROR_INTERNO", now)
            except Exception:  # noqa: BLE001
                db.rollback()
            continue
        summary["eliminadas" if outcome == ELIMINADA else "omitidas"] += 1
    return summary
