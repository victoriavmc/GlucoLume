# AdminAccessAlerts - Aviso por correo de los intentos rechazados contra la administración de GlucoLume
#
# Quién llama: services/auth.py (contraseña, Google y segundo factor) y services/mfaRecovery.py, solo cuando el ingreso fue RECHAZADO y la
# cuenta es administrativa o el acceso pedido fue el PLATAFORMA. Cada intento ya quedó en la auditoría antes de llegar acá: este módulo
# decide solo el correo, así que limitar los envíos nunca borra un registro.
#
# Regla de envío (SECURITY_ALERT_EMAIL_MINUTES, 60 por omisión; 0 lo desactiva):
#   - el primer intento de un incidente sale enseguida;
#   - mientras dura la ventana no sale otro correo: los intentos se acumulan;
#   - al cerrarse la ventana sale UN resumen de lo acumulado, y el siguiente intento abre una ventana nueva.
# Así un atacante no puede provocar un correo por intento, aunque cambie de cuenta. Como securityMonitor, el estado vive en la memoria de
# este proceso: con varias réplicas, cada una avisa por separado.
#
# El envío corre en segundo plano y nunca lanza: un fallo de SMTP no cambia la respuesta de la autenticación.

import logging
import threading
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import getSettings
from app.db.session import getSessionFactory
from app.emails.eventTypes import EmailEventType
from app.models.user import User
from app.services import email as emailService

logger = logging.getLogger(__name__)

# Tipos de autenticación que aparecen en el correo (presentación; nunca credenciales).
TIPO_CONTRASENA = "Contraseña"
TIPO_GOOGLE = "Cuenta de Google"
TIPO_SEGUNDO_FACTOR = "Segundo factor"

# Motivo general por código estable de AuthError. Cualquier otro código se presenta como «Ingreso rechazado».
_MOTIVOS = {
    "CREDENCIALES_INVALIDAS": "Credenciales rechazadas",
    "CUENTA_BLOQUEADA": "Cuenta bloqueada por intentos fallidos",
    "CODIGO_INVALIDO": "Segundo factor incorrecto",
    "MFA_BLOQUEADO": "Segundo factor bloqueado por códigos incorrectos",
    "ACCESO_PLATAFORMA_DENEGADO": "Cuenta sin permiso para la administración",
    "ACCESO_PLATAFORMA_REQUERIDO": "Cuenta de administración usada en el acceso general",
}

MAX_PENDING = 200  # intentos guardados para el resumen; los que excedan solo se cuentan
MAX_SHOWN_IPS = 5


@dataclass(frozen=True)
class Attempt:
    correo: str
    tipoAutenticacion: str
    motivo: str  # código estable (AuthError.code)
    ip: str | None
    fecha: datetime


class _State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.lastSent: float | None = None
        self.pending: list[Attempt] = []
        self.omitted = 0
        self.timer: threading.Timer | None = None


_state = _State()


def reset() -> None:
    """Olvida la ventana, lo acumulado y el temporizador (las pruebas lo usan entre casos)."""
    with _state.lock:
        if _state.timer is not None:
            _state.timer.cancel()
        _state.lastSent, _state.pending, _state.omitted, _state.timer = None, [], 0, None


def _startTimer(delay: float, task) -> threading.Timer:
    timer = threading.Timer(delay, task)
    timer.daemon = True
    timer.start()
    return timer


def record(db: Session, attempt: Attempt, now: float | None = None) -> None:
    """Registra un intento ya auditado y decide si el correo sale ahora, al cerrarse la ventana, o no sale."""
    minutes = getSettings().SECURITY_ALERT_EMAIL_MINUTES
    if minutes <= 0:
        return
    window = minutes * 60.0
    now = time.monotonic() if now is None else now
    with _state.lock:
        if _state.lastSent is None or now - _state.lastSent >= window:
            batch, omitted = _state.pending + [attempt], _state.omitted
            _state.pending, _state.omitted = [], 0
            _state.lastSent = now
            if _state.timer is not None:
                _state.timer.cancel()
                _state.timer = None
            primer = True
        else:
            if len(_state.pending) < MAX_PENDING:
                _state.pending.append(attempt)
            else:
                _state.omitted += 1
            if _state.timer is None:
                _state.timer = _startTimer(_state.lastSent + window - now, _onWindowEnd)
            return
    _send(db, batch, omitted, primer)


def flush(db: Session, now: float | None = None) -> None:
    """Cierra la ventana: envía el resumen de lo acumulado (si hay algo) y abre una ventana nueva desde ahora."""
    now = time.monotonic() if now is None else now
    with _state.lock:
        _state.timer = None
        if not _state.pending:
            return
        batch, omitted = _state.pending, _state.omitted
        _state.pending, _state.omitted = [], 0
        _state.lastSent = now
    _send(db, batch, omitted, primer=False)


def _onWindowEnd() -> None:
    try:
        with getSessionFactory()() as db:
            flush(db)
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo enviar el resumen de intentos de ingreso a la administración")


def _send(db: Session, batch: list[Attempt], omitted: int, primer: bool) -> None:
    try:
        recipients = db.scalars(select(User.correoElectronico).where(
            User.tipoCuenta == "ADMINISTRADOR_PLATAFORMA", User.estado == "ACTIVO", User.correoElectronico.is_not(None))).all()
        context = _context(batch, omitted, primer)
        for recipient in recipients:
            emailService.sendEmailEventInBackground(EmailEventType.ALERTA_INTENTO_ACCESO_ADMIN, recipient, context)
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo avisar a los administradores de un intento de ingreso")


def _context(batch: list[Attempt], omitted: int, primer: bool) -> dict:
    cuentas = Counter(attempt.correo for attempt in batch)
    motivos = Counter(_MOTIVOS.get(attempt.motivo, "Ingreso rechazado") for attempt in batch)
    ips = sorted({attempt.ip for attempt in batch if attempt.ip})
    ipText = ", ".join(ips[:MAX_SHOWN_IPS]) or "No disponible"
    if len(ips) > MAX_SHOWN_IPS:
        ipText += f" y {len(ips) - MAX_SHOWN_IPS} más"
    return {
        "alcance": ("Primer intento de un incidente. Los siguientes se resumen en un aviso por hora como máximo." if primer
                    else "Resumen de los intentos rechazados desde el aviso anterior."),
        "cuentas": "; ".join(f"{correo} ({count})" for correo, count in cuentas.most_common()),
        "tipos": ", ".join(sorted({attempt.tipoAutenticacion for attempt in batch})),
        "motivos": "; ".join(f"{motivo} ({count})" for motivo, count in motivos.most_common()),
        "ips": ipText,
        "cantidad": len(batch) + omitted,
        "primerIntento": min(attempt.fecha for attempt in batch),
        "fechaEvento": max(attempt.fecha for attempt in batch),
        "urlAuditoria": emailService.frontendUrl("/plataforma/auditoria"),
    }
