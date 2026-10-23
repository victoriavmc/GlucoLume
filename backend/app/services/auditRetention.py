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
#      Aun con un plazo mayor que 0 NO corre sin RETENTION_APPROVAL_REFERENCE (H-04, services/retentionGuard.py).
# Cada pasada que depura algo deja un evento al empezar (DEPURAR_AUDITORIA_INICIADA, antes de borrar), otro al terminar (DEPURAR_AUDITORIA) o al
# fallar (DEPURAR_AUDITORIA_FALLIDA) con las cantidades y la política aplicada, sin identificar a nadie. Si el tope de volumen la frena deja
# DEPURAR_AUDITORIA_OMITIDA (a lo sumo uno por día). `plan()`/`dryRun` simulan sin modificar nada.
# Es idempotente y segura ante ejecuciones simultáneas: depura por lotes y solo toca lo vencido.

import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import getSettings
from app.models.audit import Audit
from app.models.auditContext import AuditContext
from app.services import auditClassification as classification
from app.services import retentionGuard, schemaCompat
from app.services.audit import registerEvent
from app.utils.timeZone import nowForDb

logger = logging.getLogger("glucolume.audit")

BATCH = 1000  # por debajo del límite de 2100 parámetros de SQL Server
ACCION_INICIO = "DEPURAR_AUDITORIA_INICIADA"
ACCION_FALLA = "DEPURAR_AUDITORIA_FALLIDA"
ACCION_OMITIDA = "DEPURAR_AUDITORIA_OMITIDA"
# Acciones sin cuenta identificable que entran en el punto 2.
ANONYMOUS_ACTIONS = ("LOGIN_LOCAL", "LOGIN_GOOGLE", classification.ACCION_LIMITE_SOLICITUDES, classification.ACCION_RAFAGA_AUTORIZACION,
                     classification.ACCION_RAFAGA_VALIDACION)


def _monthsAgo(now: datetime, months: int) -> datetime:
    total = now.year * 12 + (now.month - 1) - months
    year, month = divmod(total, 12)
    day = min(now.day, [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month])
    return now.replace(year=year, month=month + 1, day=day)


def _deleteBatches(db: Session, *conditions, progress: dict | None = None, key: str = "") -> int:
    deleted = 0
    while True:
        ids = db.scalars(select(Audit.idAuditoria).where(*conditions).limit(BATCH)).all()
        if not ids:
            return deleted
        db.execute(delete(Audit).where(Audit.idAuditoria.in_(ids)))
        db.commit()
        deleted += len(ids)
        if progress is not None:
            progress[key] = deleted  # visible si una falla posterior interrumpe la pasada


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


def _anonymousConditions(now: datetime, months: int) -> tuple:
    return (Audit.idUsuario.is_(None), Audit.idInstitucion.is_(None), Audit.resultado == "FALLO",
            Audit.accion.in_(ANONYMOUS_ACTIONS), Audit.fechaHora < _monthsAgo(now, months))


def purgeAnonymous(db: Session, now: datetime, months: int) -> int:
    if months <= 0:
        return 0
    return _deleteBatches(db, *_anonymousConditions(now, months))


def purgeAll(db: Session, now: datetime, months: int) -> int:
    if months <= 0:
        return 0
    return _deleteBatches(db, Audit.fechaHora < _monthsAgo(now, months))


def plan(db: Session, now: datetime | None = None) -> dict:
    """Qué haría una pasada ahora, SIN modificar nada: cantidades, plazos efectivos, aprobación y si el tope la frenaría. Sirve de simulación
    (`python -m app.jobs.retention previsualizar`) y la usa la propia pasada para decidir."""
    settings = getSettings()
    now = now or nowForDb()
    allMonths = retentionGuard.approvedMonths("AUDIT_RETENTION_MONTHS", settings.AUDIT_RETENTION_MONTHS)
    anonymousMonths = settings.AUDIT_ANONYMOUS_RETENTION_MONTHS
    conditions = []
    if anonymousMonths > 0:
        conditions.append(and_(*_anonymousConditions(now, anonymousMonths)))
    if allMonths > 0:
        conditions.append(Audit.fechaHora < _monthsAgo(now, allMonths))
    total = db.scalar(select(func.count()).select_from(Audit)) or 0
    candidates = (db.scalar(select(func.count()).select_from(Audit).where(or_(*conditions))) or 0) if conditions else 0
    anonymous = (db.scalar(select(func.count()).select_from(Audit).where(*_anonymousConditions(now, anonymousMonths))) or 0) if anonymousMonths > 0 else 0
    return {
        "eventosTotales": total, "eventosAEliminar": candidates, "intentosSinCuentaAEliminar": anonymous,
        "plazoTotalMesesEfectivo": allMonths, "plazoTotalMesesConfigurado": settings.AUDIT_RETENTION_MONTHS,
        "plazoSinCuentaMeses": anonymousMonths, "aprobacion": retentionGuard.approvalReference(),
        "bloqueadaPorVolumen": retentionGuard.blockedByVolume(candidates, total),
    }


def run(db: Session, now: datetime | None = None, *, dryRun: bool = False, confirmedDeletions: int | None = None) -> dict:
    """Una pasada de conservación. `dryRun`: solo informa (no modifica ni registra eventos). `confirmedDeletions`: ejecución manual que acepta
    pasar el tope de volumen confirmando la cantidad EXACTA que la simulación informó; si ya no coincide, no se borra nada."""
    settings = getSettings()
    now = now or nowForDb()
    planned = plan(db, now)
    if dryRun:
        return {"simulacion": True, **planned}
    result = {"contextosMinimizados": minimizeContext(db, now, settings.AUDIT_CONTEXT_RETENTION_DAYS),
              "intentosSinCuentaEliminados": 0, "eventosEliminados": 0}
    if planned["eventosAEliminar"] == 0:
        logger.info("Conservación de la auditoría: %s", result)
        return result
    if planned["bloqueadaPorVolumen"]:
        if confirmedDeletions is None:
            _recordSkip(db, planned)
            result["omitidaPorVolumen"] = planned["eventosAEliminar"]
            logger.warning("Depuración de la auditoría omitida: alcanzaría %s de %s eventos. Revisala con «python -m app.jobs.retention previsualizar».",
                           planned["eventosAEliminar"], planned["eventosTotales"])
            return result
        if confirmedDeletions != planned["eventosAEliminar"]:
            raise ValueError(f"La cantidad confirmada ({confirmedDeletions}) no coincide con la actual ({planned['eventosAEliminar']}): "
                             "no se eliminó nada. Volvé a previsualizar.")
    policy = {"contextoDias": settings.AUDIT_CONTEXT_RETENTION_DAYS, "sinCuentaMeses": settings.AUDIT_ANONYMOUS_RETENTION_MONTHS,
              "totalMeses": planned["plazoTotalMesesEfectivo"], "aprobacion": planned["aprobacion"], "confirmadaALaMano": confirmedDeletions is not None}
    registerEvent(db, "CRUD", ACCION_INICIO, True, modulo="AUDITORIA", observacion="Inicia la depuración por política de conservación",
                  datosNuevos={"previstos": planned["eventosAEliminar"], "politica": policy})
    db.commit()  # el inicio queda registrado ANTES de borrar: si algo interrumpe la pasada, la auditoría lo muestra
    progress: dict = {}
    try:
        result["intentosSinCuentaEliminados"] = _deleteBatches(
            db, *_anonymousConditions(now, settings.AUDIT_ANONYMOUS_RETENTION_MONTHS), progress=progress, key="intentosSinCuentaEliminados"
        ) if settings.AUDIT_ANONYMOUS_RETENTION_MONTHS > 0 else 0
        result["eventosEliminados"] = purgeAll(db, now, planned["plazoTotalMesesEfectivo"])
    except Exception as error:
        db.rollback()
        registerEvent(db, "CRUD", ACCION_FALLA, False, modulo="AUDITORIA", motivo="ERROR_INTERNO",
                      observacion=f"La depuración se interrumpió ({type(error).__name__}); lo ya eliminado no se revierte.",
                      datosNuevos={**{**result, **progress}, "politica": policy})
        db.commit()
        raise
    if result["intentosSinCuentaEliminados"] or result["eventosEliminados"]:
        # Se deja constancia de la depuración de eventos (la minimización de IP es rutina diaria y no genera un evento por pasada).
        registerEvent(db, "CRUD", classification.ACCION_DEPURAR_AUDITORIA, True, modulo="AUDITORIA",
                      observacion="Depuración por política de conservación", datosNuevos={**result, "politica": policy})
        db.commit()
    logger.info("Conservación de la auditoría: %s", result)
    return result


def _recordSkip(db: Session, planned: dict) -> None:
    if not retentionGuard.shouldRecordSkip("auditoria"):
        return
    registerEvent(db, "CRUD", ACCION_OMITIDA, False, modulo="AUDITORIA", motivo="LIMITE_DE_VOLUMEN",
                  observacion="La depuración se omitió: alcanzaría más del tope de la tabla; requiere ejecución manual confirmada.",
                  datosNuevos={"previstos": planned["eventosAEliminar"], "totales": planned["eventosTotales"],
                               "fraccionMaxima": getSettings().RETENTION_MAX_DELETE_FRACTION})
    db.commit()
