# AuditRetention - Política técnica de conservación de la auditoría
#
# La conservación y la depuración las decide ESTA política (valores en Settings, documentados en docs/AUDITORIA_ADMINISTRATIVA.md), no la
# interfaz: ninguna ruta de la API ni pantalla elimina o edita eventos. La corre el servicio «lifecycle» (app/jobs/accountLifecycle.py).
#
#   1. IP y cliente (AuditoriaContexto.ipOrigen / agenteUsuario): se anulan pasados AUDIT_CONTEXT_RETENTION_DAYS (90 por defecto). El evento, su
#      correlación y su motivo siguen: lo que se pierde es el dato personal, no la trazabilidad. 0 lo desactiva.
#   2. Intentos de acceso sin cuenta identificable (cuenta inexistente, límite de solicitudes, ráfagas): se eliminan pasados
#      AUDIT_ANONYMOUS_RETENTION_MONTHS (12 por defecto). Son ruido sin valor administrativo y crecen sin control si alguien los provoca. 0 lo desactiva.
#   3. Toda la auditoría: se elimina pasados AUDIT_RETENTION_MONTHS. 0 (por defecto) la conserva sin límite: el plazo legal todavía no fue aprobado.
# Cada pasada que depura algo deja UN evento (DEPURAR_AUDITORIA) con las cantidades y la política aplicada, sin identificar a nadie.
# Es idempotente y segura ante ejecuciones simultáneas: depura por lotes y solo toca lo vencido.

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import getSettings
from app.models.audit import Audit
from app.models.auditContext import AuditContext
from app.services import auditClassification as classification
from app.services import schemaCompat
from app.services.audit import registerEvent
from app.utils.timeZone import nowForDb

logger = logging.getLogger("glucolume.audit")

BATCH = 1000  # por debajo del límite de 2100 parámetros de SQL Server
# Acciones sin cuenta identificable que entran en el punto 2.
ANONYMOUS_ACTIONS = ("LOGIN_LOCAL", "LOGIN_GOOGLE", classification.ACCION_LIMITE_SOLICITUDES, classification.ACCION_RAFAGA_AUTORIZACION,
                     classification.ACCION_RAFAGA_VALIDACION)


def _monthsAgo(now: datetime, months: int) -> datetime:
    total = now.year * 12 + (now.month - 1) - months
    year, month = divmod(total, 12)
    day = min(now.day, [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month])
    return now.replace(year=year, month=month + 1, day=day)


def _deleteBatches(db: Session, *conditions) -> int:
    deleted = 0
    while True:
        ids = db.scalars(select(Audit.idAuditoria).where(*conditions).limit(BATCH)).all()
        if not ids:
            return deleted
        db.execute(delete(Audit).where(Audit.idAuditoria.in_(ids)))
        db.commit()
        deleted += len(ids)


def minimizeContext(db: Session, now: datetime, days: int) -> int:
    """Anula la IP y el cliente de los eventos más viejos que `days`. Devuelve cuántos contextos se modificaron."""
    if days <= 0 or not schemaCompat.auditContextReady(db):
        return 0
    cutoff = now - timedelta(days=days)
    result = db.execute(
        update(AuditContext)
        .where(AuditContext.idAuditoria.in_(select(Audit.idAuditoria).where(Audit.fechaHora < cutoff)),
               or_(AuditContext.ipOrigen.is_not(None), AuditContext.agenteUsuario.is_not(None)))
        .values(ipOrigen=None, agenteUsuario=None)
        .execution_options(synchronize_session=False))
    db.commit()
    return result.rowcount or 0


def purgeAnonymous(db: Session, now: datetime, months: int) -> int:
    if months <= 0:
        return 0
    return _deleteBatches(db, Audit.idUsuario.is_(None), Audit.idInstitucion.is_(None), Audit.resultado == "FALLO",
                          Audit.accion.in_(ANONYMOUS_ACTIONS), Audit.fechaHora < _monthsAgo(now, months))


def purgeAll(db: Session, now: datetime, months: int) -> int:
    if months <= 0:
        return 0
    return _deleteBatches(db, Audit.fechaHora < _monthsAgo(now, months))


def run(db: Session, now: datetime | None = None) -> dict[str, int]:
    settings = getSettings()
    now = now or nowForDb()
    result = {
        "contextosMinimizados": minimizeContext(db, now, settings.AUDIT_CONTEXT_RETENTION_DAYS),
        "intentosSinCuentaEliminados": purgeAnonymous(db, now, settings.AUDIT_ANONYMOUS_RETENTION_MONTHS),
        "eventosEliminados": purgeAll(db, now, settings.AUDIT_RETENTION_MONTHS),
    }
    if result["intentosSinCuentaEliminados"] or result["eventosEliminados"]:
        # Se deja constancia de la depuración de eventos (la minimización de IP es rutina diaria y no genera un evento por pasada).
        registerEvent(
            db, "CRUD", classification.ACCION_DEPURAR_AUDITORIA, True, modulo="AUDITORIA",
            observacion="Depuración automática por política de conservación",
            datosNuevos={**result, "politica": {
                "contextoDias": settings.AUDIT_CONTEXT_RETENTION_DAYS, "sinCuentaMeses": settings.AUDIT_ANONYMOUS_RETENTION_MONTHS,
                "totalMeses": settings.AUDIT_RETENTION_MONTHS}})
        db.commit()
    logger.info("Conservación de la auditoría: %s", result)
    return result
