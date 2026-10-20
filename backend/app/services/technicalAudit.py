# Auditoría técnica ANONIMIZADA de mediciones fallidas (ver models/technicalAudit.py).
#
# Se escribe en la MISMA transacción que el cierre de la medición (cancelación, invalidación, abandono o vencimiento) pero dentro de un
# SAVEPOINT: un problema acá nunca impide cerrar la medición. Solo guarda datos técnicos: tipo de operación, estado final, motivo, sensor,
# duración y código de error. Nunca ids de usuario, perfil o medición, nombres, correos ni señales fisiológicas, y la hora va redondeada a
# la hora en punto: no sirve para reconstruir el historial de una persona. Consulta solo para ADMINISTRADOR_PLATAFORMA.

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.measurement import Measurement
from app.models.technicalAudit import TechnicalAudit
from app.models.user import User
from app.schemas.auditLog import TechnicalEvent, TechnicalPage, TechnicalSummary
from app.utils.timeZone import nowForDb

logger = logging.getLogger(__name__)

RETENTION_DAYS = 180  # plazo de conservación de la auditoría técnica anonimizada
MAX_PAGE_SIZE = 100


def _hour(moment: datetime) -> datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


def record(db: Session, measurement: Measurement, finalState: str, reason: str, *, operation: str = "MEDICION",
           end: datetime | None = None, errorCode: str | None = None) -> None:
    """Agrega el evento técnico anonimizado de una medición que terminó sin completarse. No identifica a nadie."""
    try:
        finished = end or measurement.fechaHoraFin or nowForDb()
        seconds = max(0, int((finished - measurement.fechaHoraInicio).total_seconds()))
        with db.begin_nested():
            db.add(TechnicalAudit(
                idEvento=uuid.uuid4(), fechaHora=_hour(nowForDb()), tipoOperacion=operation, estadoFinal=finalState, motivo=reason,
                modeloSensor=measurement.modeloSensorAlMomento, duracionSegundos=seconds, codigoError=errorCode))
    except Exception:  # noqa: BLE001 - la auditoría técnica nunca impide cerrar una medición
        logger.exception("No se pudo registrar el evento técnico anonimizado (%s)", reason)


def purgeExpired(db: Session, now: datetime | None = None) -> int:
    """Elimina eventos técnicos más viejos que el plazo de conservación. Devuelve cuántos."""
    cutoff = (now or nowForDb()) - timedelta(days=RETENTION_DAYS)
    result = db.execute(delete(TechnicalAudit).where(TechnicalAudit.fechaHora < cutoff))
    return result.rowcount or 0


def _filters(desde, hasta, estado, motivo):
    conditions = []
    if desde:
        conditions.append(TechnicalAudit.fechaHora >= datetime.combine(desde, datetime.min.time()))
    if hasta:
        conditions.append(TechnicalAudit.fechaHora < datetime.combine(hasta + timedelta(days=1), datetime.min.time()))
    if estado:
        conditions.append(TechnicalAudit.estadoFinal == estado)
    if motivo:
        conditions.append(TechnicalAudit.motivo == motivo)
    return conditions


def listTechnical(db: Session, actor: User, *, desde=None, hasta=None, estado=None, motivo=None, pagina=1,
                  tamanioPagina=25) -> TechnicalPage:
    from app.services import auditQuery

    auditQuery.requireAdministrator(db, actor)
    tamanioPagina = max(1, min(tamanioPagina, MAX_PAGE_SIZE))
    pagina = max(1, pagina)
    conditions = _filters(desde, hasta, estado, motivo)
    total = db.scalar(select(func.count()).select_from(TechnicalAudit).where(*conditions)) or 0
    rows = db.scalars(select(TechnicalAudit).where(*conditions).order_by(TechnicalAudit.fechaHora.desc(), TechnicalAudit.idEvento)
                      .offset((pagina - 1) * tamanioPagina).limit(tamanioPagina)).all()
    return TechnicalPage(items=[TechnicalEvent.model_validate(row, from_attributes=True) for row in rows], total=total, pagina=pagina,
                         tamanioPagina=tamanioPagina)


def summaryTechnical(db: Session, actor: User, *, desde=None, hasta=None) -> TechnicalSummary:
    from app.services import auditQuery

    auditQuery.requireAdministrator(db, actor)
    conditions = _filters(desde, hasta, None, None)

    def grouped(column):
        rows = db.execute(select(column, func.count()).where(*conditions).group_by(column)).all()
        return {key if key is not None else "SIN_DATO": count for key, count in rows}

    average = db.scalar(select(func.avg(TechnicalAudit.duracionSegundos)).where(*conditions))
    return TechnicalSummary(
        total=db.scalar(select(func.count()).select_from(TechnicalAudit).where(*conditions)) or 0,
        porEstado=grouped(TechnicalAudit.estadoFinal), porMotivo=grouped(TechnicalAudit.motivo),
        porSensor=grouped(TechnicalAudit.modeloSensor), duracionPromedioSegundos=round(float(average), 1) if average is not None else None)
