# TimeZone - Política temporal única de GlucoLume
#
# Las fechas y horas que genera el backend se persisten en hora de Argentina (America/Argentina/
# Buenos_Aires, UTC-03:00), independientemente de la zona horaria configurada en el servidor.
#
# Las columnas son DATETIME2 (sin zona): se guardan como datetime naive que representa la hora de
# Argentina. Todo el backend debe obtener la hora desde este módulo; no usar datetime.now(),
# datetime.utcnow() ni datetime.now(timezone.utc) directamente.

from datetime import datetime
from zoneinfo import ZoneInfo

ARGENTINA_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def nowArgentina() -> datetime:
    """Instante actual con zona de Argentina (aware). Para cálculos que necesitan el instante real
    (expiración de JWT, ventanas TOTP)."""
    return datetime.now(ARGENTINA_TZ)


def nowForDb() -> datetime:
    """Hora actual de Argentina sin zona (naive), lista para persistir en columnas DATETIME2 y para
    compararla con valores leídos de la base."""
    return nowArgentina().replace(tzinfo=None)


def withArgentinaZone(value: datetime) -> datetime:
    """Marca como hora de Argentina (UTC-03:00) un valor naive persistido, para que el cliente lo convierta bien."""
    return value if value.tzinfo else value.replace(tzinfo=ARGENTINA_TZ)


def toDbTime(value: datetime) -> datetime:
    """Convierte un datetime al formato persistido: hora de Argentina naive.

    Un datetime con zona se convierte a Argentina; uno naive se asume ya expresado en hora de Argentina.
    """
    if value.tzinfo is None:
        return value
    return value.astimezone(ARGENTINA_TZ).replace(tzinfo=None)
