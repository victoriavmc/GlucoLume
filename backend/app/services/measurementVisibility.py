# Visibilidad de las mediciones según su estado (hoja: solo depende de los modelos).
#
#   COMPLETADA                      permanece en el historial hasta que la persona o las políticas de datos la eliminen.
#   CANCELADA / INVALIDA            visibles VISIBLE_MINUTES minutos desde su cierre (`fechaHoraFin`) y después se OCULTAN del historial
#                                   personal. No se borran: el registro queda en la base y su evento en la auditoría.
#   PENDIENTE / ADQUIRIENDO / PROCESANDO   temporales: si pasan VISIBLE_MINUTES sin actividad real el mantenimiento las pasa a INVALIDA
#                                   (TIEMPO_AGOTADO) con `fechaHoraFin` = fin de su actividad, por lo que quedan ocultas al instante.
# El esquema actual alcanza (estadoMedicion + fechaHoraFin como fecha de transición): no hace falta una columna de «oculta».
# Esto aplica a la vista PERSONAL de una cuenta individual; el panel clínico de una institución conserva su propia política.

from datetime import datetime, timedelta

from sqlalchemy import and_

from app.models.measurement import Measurement

VISIBLE_MINUTES = 30
TERMINAL_HIDEABLE = ("CANCELADA", "INVALIDA")
ACTIVE_STATES = ("PENDIENTE", "ADQUIRIENDO", "PROCESANDO")


def hiddenCondition(now: datetime):
    """Expresión SQL: la medición ya venció su plazo de visibilidad (se usa negada en las consultas personales)."""
    cutoff = now - timedelta(minutes=VISIBLE_MINUTES)
    return and_(Measurement.estadoMedicion.in_(TERMINAL_HIDEABLE), Measurement.fechaHoraFin.is_not(None), Measurement.fechaHoraFin <= cutoff)


def isHidden(measurement: Measurement, now: datetime) -> bool:
    return (measurement.estadoMedicion in TERMINAL_HIDEABLE and measurement.fechaHoraFin is not None
            and measurement.fechaHoraFin <= now - timedelta(minutes=VISIBLE_MINUTES))


def visibleUntil(measurement: Measurement) -> datetime | None:
    """Hasta cuándo se ve una medición cancelada o inválida (None si no aplica)."""
    if measurement.estadoMedicion in TERMINAL_HIDEABLE and measurement.fechaHoraFin is not None:
        return measurement.fechaHoraFin + timedelta(minutes=VISIBLE_MINUTES)
    return None
