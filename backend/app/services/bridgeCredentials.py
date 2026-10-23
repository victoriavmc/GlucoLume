# BridgeCredentials - Credenciales individuales de los puentes serie (H-16)
#
# Cada puente tiene su propio token: atado a un código de dispositivo, con vencimiento obligatorio, revocable por separado y rotable con una
# superposición acotada. El BRIDGE_TOKEN compartido sigue valiendo mientras BRIDGE_ALLOW_SHARED_TOKEN lo permita (compatibilidad), sin alcance.
#
# - Del token solo se guarda su SHA-256 (alta entropía, como el refresh token); el valor en claro se muestra UNA vez al crearlo y no se registra
#   en ninguna parte (ni en la auditoría ni en los logs). Las huellas (8 primeros caracteres del hash) identifican una credencial sin revelarla.
# - authenticate() rechaza con un motivo estable: DESCONOCIDA, REVOCADA, VENCIDA. El alcance (código de dispositivo) lo comprueba enforceScope().
# - Auditoría: alta, rotación, revocación (desde la línea de comandos, sin cuenta de usuario) y los rechazos de una credencial RECONOCIDA
#   (revocada, vencida o fuera de alcance), como máximo uno cada REJECTION_AUDIT_SECONDS por credencial y motivo. Los intentos con un token
#   desconocido no se registran uno por uno: los frena el bloqueo por IP del puente (api/rateLimit.py) y la ráfaga de rechazos.

import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core import security
from app.core.exceptions import AuthError
from app.models.bridgeCredential import BridgeCredential
from app.services import schemaCompat
from app.services.audit import registerEvent
from app.utils.timeZone import nowForDb

DEFAULT_VALID_DAYS = 180
MAX_VALID_DAYS = 365
DEFAULT_OVERLAP_HOURS = 24
MAX_OVERLAP_HOURS = 72
LAST_USE_INTERVAL_SECONDS = 300.0
REJECTION_AUDIT_SECONDS = 600.0

ACTION_CREATED = "CREAR_CREDENCIAL_PUENTE"
ACTION_ROTATED = "ROTAR_CREDENCIAL_PUENTE"
ACTION_REVOKED = "REVOCAR_CREDENCIAL_PUENTE"
ACTION_REJECTED = "CREDENCIAL_PUENTE_RECHAZADA"

_lastUse: dict[str, float] = {}
_lastRejection: dict[tuple[str, str], float] = {}


def reset() -> None:
    """Olvida los controles de frecuencia (pruebas)."""
    _lastUse.clear()
    _lastRejection.clear()


@dataclass(frozen=True)
class BridgeIdentity:
    """Quién se autenticó. `credentialId` es None con el token compartido (sin alcance por dispositivo)."""

    credentialId: object | None
    deviceCode: str | None
    shared: bool = False


def fingerprint(tokenHash: str) -> str:
    return tokenHash[:8]


def _normalizeCode(code: str) -> str:
    return code.strip().lower()


def available(db: Session) -> bool:
    return schemaCompat.hasTable(db, "PuenteCredencial")


def anyActive(db: Session) -> bool:
    if not available(db):
        return False
    now = nowForDb()
    return db.scalar(select(func.count()).select_from(BridgeCredential).where(
        BridgeCredential.fechaRevocacion.is_(None), BridgeCredential.fechaExpiracion > now)) > 0


def create(db: Session, name: str, deviceCode: str, validDays: int = DEFAULT_VALID_DAYS, *, event: str = ACTION_CREATED,
           note: str | None = None) -> tuple[BridgeCredential, str]:
    """Crea una credencial y devuelve (fila, token en claro). El token en claro solo existe en el valor devuelto."""
    name, deviceCode = name.strip(), deviceCode.strip()
    if not name or not deviceCode:
        raise ValueError("El nombre y el código de dispositivo son obligatorios.")
    if not 1 <= validDays <= MAX_VALID_DAYS:
        raise ValueError(f"La vigencia debe estar entre 1 y {MAX_VALID_DAYS} días.")
    token = security.generateOpaqueToken()
    now = nowForDb()
    credential = BridgeCredential(
        nombre=name[:100], tokenHash=security.hashOpaqueToken(token), codigoDispositivo=deviceCode[:100],
        fechaCreacion=now, fechaExpiracion=now + timedelta(days=validDays))
    db.add(credential)
    db.flush()
    registerEvent(db, "PERMISO", event, True, tablaAfectada="PuenteCredencial", idRegistro=credential.idPuenteCredencial, modulo="SEGURIDAD",
                  observacion=note or f"Credencial de puente «{credential.nombre}» ({fingerprint(credential.tokenHash)}) para el dispositivo "
                                      f"{credential.codigoDispositivo}, vigente {validDays} días.",
                  datosNuevos={"huella": fingerprint(credential.tokenHash), "dispositivo": credential.codigoDispositivo,
                               "vence": credential.fechaExpiracion.isoformat(timespec="seconds")})
    db.commit()
    return credential, token


def find(db: Session, reference: str) -> BridgeCredential:
    """Busca por huella (prefijo del hash, mínimo 6 caracteres) o por identificador. Una referencia ambigua o inexistente es un error."""
    reference = reference.strip().lower()
    rows = [row for row in db.scalars(select(BridgeCredential)).all()
            if str(row.idPuenteCredencial).lower() == reference or (len(reference) >= 6 and row.tokenHash.startswith(reference))]
    if len(rows) != 1:
        raise ValueError("No hay una credencial que coincida con esa referencia." if not rows else "La referencia es ambigua: usá más caracteres.")
    return rows[0]


def revoke(db: Session, reference: str) -> BridgeCredential:
    credential = find(db, reference)
    if credential.fechaRevocacion is not None:
        return credential
    credential.fechaRevocacion = nowForDb()
    registerEvent(db, "PERMISO", ACTION_REVOKED, True, tablaAfectada="PuenteCredencial", idRegistro=credential.idPuenteCredencial,
                  modulo="SEGURIDAD", observacion=f"Credencial de puente «{credential.nombre}» ({fingerprint(credential.tokenHash)}) revocada.")
    db.commit()
    return credential


def rotate(db: Session, reference: str, overlapHours: int = DEFAULT_OVERLAP_HOURS, validDays: int = DEFAULT_VALID_DAYS) -> tuple[BridgeCredential, str]:
    """Emite una credencial nueva para el mismo puente y acorta la anterior: sigue valiendo solo `overlapHours` (máximo 72) para dar tiempo a
    actualizar el equipo, nunca más allá de su propio vencimiento. Una credencial revocada o vencida no se rota."""
    if not 1 <= overlapHours <= MAX_OVERLAP_HOURS:
        raise ValueError(f"La superposición debe estar entre 1 y {MAX_OVERLAP_HOURS} horas.")
    old = find(db, reference)
    now = nowForDb()
    if old.fechaRevocacion is not None or old.fechaExpiracion <= now:
        raise ValueError("La credencial está revocada o vencida: creá una nueva.")
    new, token = create(db, old.nombre, old.codigoDispositivo, validDays, event=ACTION_ROTATED,
                        note=f"Rotación de «{old.nombre}»: la anterior ({fingerprint(old.tokenHash)}) vale {overlapHours} h más.")
    old.fechaExpiracion = min(old.fechaExpiracion, now + timedelta(hours=overlapHours))
    db.commit()
    return new, token


def status(credential: BridgeCredential, now: datetime | None = None) -> str:
    now = now or nowForDb()
    if credential.fechaRevocacion is not None:
        return "REVOCADA"
    return "VENCIDA" if credential.fechaExpiracion <= now else "ACTIVA"


def listAll(db: Session) -> list[dict]:
    """Para el listado de la línea de comandos: nunca el token ni el hash completo."""
    now = nowForDb()
    rows = db.scalars(select(BridgeCredential).order_by(BridgeCredential.fechaCreacion)).all()
    return [{"huella": fingerprint(row.tokenHash), "nombre": row.nombre, "dispositivo": row.codigoDispositivo, "estado": status(row, now),
             "vence": row.fechaExpiracion, "ultimoUso": row.fechaUltimoUso} for row in rows]


def _auditRejection(db: Session, credential: BridgeCredential, reason: str, detail: str) -> None:
    key = (fingerprint(credential.tokenHash), reason)
    now = time.monotonic()
    last = _lastRejection.get(key)
    if last is not None and now - last < REJECTION_AUDIT_SECONDS:
        return
    _lastRejection[key] = now
    try:
        registerEvent(db, "ACCESO", ACTION_REJECTED, False, tablaAfectada="PuenteCredencial", idRegistro=credential.idPuenteCredencial,
                      modulo="SEGURIDAD", motivo=reason,
                      observacion=f"Credencial de puente «{credential.nombre}» ({fingerprint(credential.tokenHash)}) rechazada: {detail}")
        db.commit()
    except Exception:  # noqa: BLE001 - la auditoría de un rechazo nunca cambia la respuesta
        db.rollback()


def authenticate(db: Session, token: str) -> BridgeIdentity | None:
    """Identidad de un token individual, o None si no corresponde a ninguna credencial (el llamador prueba entonces el token compartido).
    Una credencial reconocida pero revocada o vencida lanza PUENTE_NO_AUTORIZADO y queda auditada."""
    if not available(db):
        return None
    credential = db.scalar(select(BridgeCredential).where(BridgeCredential.tokenHash == security.hashOpaqueToken(token)))
    if credential is None:
        return None
    state = status(credential)
    if state != "ACTIVA":
        _auditRejection(db, credential, state, "está revocada." if state == "REVOCADA" else "está vencida.")
        raise AuthError("PUENTE_NO_AUTORIZADO", "El puente serie no está autorizado.", motivo=f"CREDENCIAL_{state}")
    _touch(db, credential)
    return BridgeIdentity(credentialId=credential.idPuenteCredencial, deviceCode=credential.codigoDispositivo)


def _touch(db: Session, credential: BridgeCredential) -> None:
    """Registra el último uso, a lo sumo una vez cada LAST_USE_INTERVAL_SECONDS por credencial (el puente envía cada segundo)."""
    key = str(credential.idPuenteCredencial)
    now = time.monotonic()
    last = _lastUse.get(key)
    if last is not None and now - last < LAST_USE_INTERVAL_SECONDS:
        return
    _lastUse[key] = now
    try:
        db.execute(update(BridgeCredential).where(BridgeCredential.idPuenteCredencial == credential.idPuenteCredencial)
                   .values(fechaUltimoUso=nowForDb()))
        db.commit()
    except Exception:  # noqa: BLE001 - el último uso es informativo; la base puede no permitir este UPDATE a la cuenta de la API
        db.rollback()


def enforceScope(db: Session, identity: BridgeIdentity | None, deviceCode: str) -> None:
    """Una credencial individual solo sirve para su dispositivo. Con el token compartido (identity.shared) no hay alcance."""
    if identity is None or identity.shared or identity.deviceCode is None:
        return
    if _normalizeCode(identity.deviceCode) != _normalizeCode(deviceCode):
        credential = db.get(BridgeCredential, identity.credentialId)
        if credential is not None:
            _auditRejection(db, credential, "FUERA_DE_ALCANCE", "intentó informar o consultar otro dispositivo.")
        raise AuthError("PUENTE_FUERA_DE_ALCANCE", "Esta credencial del puente no corresponde a ese dispositivo.",
                        motivo="DISPOSITIVO_NO_AUTORIZADO")
