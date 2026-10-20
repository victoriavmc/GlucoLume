# Mantenimiento periódico del ciclo de vida de las mediciones (lo ejecuta app/services/maintenance.py desde el backend, no el navegador).
#
#   1. Libera las sesiones del dispositivo abandonadas o vencidas y cierra su medición (telemetry.settleExpired): el Arduino compartido
#      nunca queda bloqueado por una sesión sin dueño.
#   2. Pasa a INVALIDA (motivo TIEMPO_AGOTADO) las mediciones PENDIENTE / ADQUIRIENDO / PROCESANDO que llevan VISIBLE_MINUTES sin actividad real
#      y NO pertenecen a una adquisición viva. `fechaHoraFin` = fin de su actividad (su inicio), así que quedan ocultas del historial
#      personal de inmediato (measurementVisibility). Nunca se borra nada: queda el registro y su evento de auditoría.
#   3. Purga la auditoría técnica anonimizada más vieja que su plazo de conservación.
# Seguro ante concurrencia y repeticiones: cada transición es un UPDATE condicional por estado (si el usuario guardó o canceló justo
# antes, no se toca) y una medición ya invalidada deja de ser candidata. Se confirma de a una: un error no frena a las demás.

import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.acquisition.link import link
from app.acquisition.telemetry import hub
from app.models.measurement import Measurement
from app.services import measurement as measurements
from app.services import technicalAudit
from app.services import telemetry as telemetryService
from app.services.audit import registerEvent
from app.services.measurementVisibility import ACTIVE_STATES, VISIBLE_MINUTES
from app.utils.timeZone import nowForDb

logger = logging.getLogger(__name__)

BATCH = 200
TIMEOUT_REASON = "TIEMPO_AGOTADO"


def _liveIds() -> set:
    """Mediciones con una adquisición realmente en curso (sesión del dispositivo o adquisición de muestras del puente)."""
    live = set()
    session = hub.session
    if session is not None and session.idMedicion is not None:
        live.add(session.idMedicion)
    raw = link.session
    if raw is not None and getattr(raw, "idMedicion", None) is not None:
        live.add(raw.idMedicion)
    return live


def invalidateStale(db: Session, limit: int = BATCH) -> int:
    """PENDIENTE/ADQUIRIENDO/PROCESANDO sin actividad por VISIBLE_MINUTES → INVALIDA (TIEMPO_AGOTADO). Devuelve cuántas."""
    now = nowForDb()
    cutoff = now - timedelta(minutes=VISIBLE_MINUTES)
    candidates = db.scalars(select(Measurement).where(
        Measurement.estadoMedicion.in_(ACTIVE_STATES), Measurement.fechaHoraInicio < cutoff)
        .order_by(Measurement.fechaHoraInicio).limit(limit)).all()
    live = _liveIds()
    changed = 0
    for measurement in candidates:
        if measurement.idMedicion in live:
            continue  # hay una adquisición viva: no se toca
        previous = measurement.estadoMedicion
        try:
            if not measurements._transition(db, measurement.idMedicion, ACTIVE_STATES, measurements.INVALIDA,
                                            fechaHoraFin=measurement.fechaHoraInicio,
                                            observacion="Medición vencida por falta de actividad."):
                db.rollback()  # otro proceso la completó o canceló justo antes
                continue
            registerEvent(db, "CRUD", "INVALIDAR_MEDICION_TIEMPO_AGOTADO", True, None, "Medicion", measurement.idMedicion,
                          datosPrevios={"estadoMedicion": previous},
                          datosNuevos={"estadoMedicion": measurements.INVALIDA, "motivo": TIMEOUT_REASON}, modulo="MEDICIONES")
            technicalAudit.record(db, measurement, "INVALIDA", TIMEOUT_REASON, operation="MANTENIMIENTO",
                                  end=now)
            db.commit()
            changed += 1
        except Exception:  # noqa: BLE001 - una falla no frena al resto ni deja la sesión sucia
            db.rollback()
            logger.exception("No se pudo vencer la medición %s", measurement.idMedicion)
    return changed


def sweep(db: Session) -> dict:
    """Una pasada completa de mantenimiento."""
    telemetryService.settleExpired(db)
    invalidated = invalidateStale(db)
    try:
        with db.begin_nested():
            purged = technicalAudit.purgeExpired(db)
    except Exception:  # noqa: BLE001 - p. ej. la base instalada no tiene AuditoriaTecnica: no frena el resto del mantenimiento
        logger.warning("No se pudo depurar la auditoría técnica (¿la base instalada tiene la tabla AuditoriaTecnica del esquema v5?).", exc_info=True)
        purged = 0
    db.commit()
    return {"invalidadas": invalidated, "purgadas": purged}
