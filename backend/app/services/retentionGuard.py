# RetentionGuard - Salvaguardas de las depuraciones por política (H-04)
#
# Las depuraciones que ELIMINAN o suprimen datos son irreversibles. Tres salvaguardas, todas comunes:
#   1. APROBACIÓN. Un plazo de AUDIT_RETENTION_MONTHS o PERSONNEL_RETENTION_MONTHS solo tiene efecto si RETENTION_APPROVAL_REFERENCE está
#      definida. Esos plazos están sin aprobar (docs/PRIVACIDAD_Y_RETENCION.md): este código no inventa ninguno ni los activa solo.
#   2. TOPE DE VOLUMEN. Una pasada automática que alcance más de RETENTION_MAX_DELETE_FRACTION de la tabla (y más de RETENTION_GUARD_MIN_ROWS
#      filas) no corre: es lo que produciría un plazo mal tipeado. Se resuelve a mano: `python -m app.jobs.retention previsualizar` informa la
#      cantidad y `ejecutar` exige confirmarla exactamente.
#   3. TRAZABILIDAD. Cada pasada destructiva deja un evento al empezar, otro al terminar (o al fallar) y, si el tope la frena, uno de omisión.
# La minimización de IP/cliente (90 días) y la depuración de intentos sin cuenta (12 meses) son política ya publicada y no pasan por (1).

import logging
import time

from app.core.config import getSettings

logger = logging.getLogger("glucolume.retention")

SKIP_EVENT_INTERVAL_SECONDS = 24 * 3600.0
_lastSkipEvent: dict[str, float] = {}
_warned: set[str] = set()


def reset() -> None:
    _lastSkipEvent.clear()
    _warned.clear()


def approvalReference() -> str | None:
    return getSettings().RETENTION_APPROVAL_REFERENCE or None


def approvedMonths(policy: str, months: int) -> int:
    """Los meses efectivos de una política destructiva: los configurados si hay aprobación, 0 si no (se avisa una vez por proceso)."""
    if months <= 0:
        return 0
    if approvalReference():
        return months
    if policy not in _warned:
        _warned.add(policy)
        logger.warning("%s=%s no se aplica: falta RETENTION_APPROVAL_REFERENCE (aprobación legal del plazo).", policy, months)
    return 0


def blockedByVolume(candidates: int, total: int) -> bool:
    """¿Esta pasada borraría demasiado de golpe? Pocas filas nunca se frenan (es ruido de una tabla chica)."""
    settings = getSettings()
    if candidates <= settings.RETENTION_GUARD_MIN_ROWS:
        return False
    return candidates > total * settings.RETENTION_MAX_DELETE_FRACTION


def shouldRecordSkip(policy: str) -> bool:
    """A lo sumo un evento de omisión por política cada 24 h por proceso (el servicio revisa cada hora: no se inunda la auditoría)."""
    now = time.monotonic()
    last = _lastSkipEvent.get(policy)
    if last is not None and now - last < SKIP_EVENT_INTERVAL_SECONDS:
        return False
    _lastSkipEvent[policy] = now
    return True
