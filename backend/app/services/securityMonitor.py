# SecurityMonitor - Detección de ráfagas de rechazos HTTP de un mismo origen
#
# Cuenta, por IP, las respuestas rechazadas de la API y deja UN evento de auditoría cuando un origen supera el umbral dentro de la ventana
# (no uno por solicitud: un escáner que pide mil rutas no puede llenar la base). Detecta lo que no se puede ver desde un solo evento:
#   - ráfagas de 401/403 (credenciales ausentes o mal formadas, permisos insuficientes), AUDIT_ALERT_AUTH_REJECTIONS;
#   - ráfagas de entradas rechazadas por validación (400/422), AUDIT_ALERT_VALIDATION_REJECTIONS;
#   - el límite de solicitudes por IP (429 de app/api/rateLimit.py), un evento por origen y ventana.
# No cuenta lo que ya queda registrado de a uno (inicio de sesión fallido, MFA, bloqueo) ni el uso normal: tokens vencidos o sesiones ya
# cerradas. No bloquea a nadie ni clasifica ataques: es una señal para la administración (ver services/auditClassification.py).
#
# Los contadores viven en la memoria de ESTE proceso, igual que app/api/rateLimit.py: con varias réplicas cada una cuenta por separado.
# Para contar entre réplicas hace falta un almacén compartido (Redis) o el registro del perímetro (Nginx/WAF); ver docs/AUDITORIA_ADMINISTRATIVA.md.

import logging
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field

from app.core.config import getSettings
from app.db.session import getSessionFactory
from app.services import auditClassification as classification
from app.services.audit import registerEvent

logger = logging.getLogger("glucolume.security")

KIND_AUTH = "AUTORIZACION"
KIND_VALIDATION = "VALIDACION"
MAX_KEYS = 20_000

# Rechazos que ya quedan registrados de a uno por el servicio que los produce, o que son parte del uso normal: no suman a la ráfaga.
IGNORED_CODES = frozenset({
    "CREDENCIALES_INVALIDAS", "CUENTA_BLOQUEADA", "MFA_BLOQUEADO", "CODIGO_INVALIDO", "CORREO_NO_VERIFICADO", "CUENTA_NO_ACTIVA",
    "DEMASIADAS_SOLICITUDES",
})
IGNORED_MOTIVOS = frozenset({"TOKEN_VENCIDO", "SESION_INVALIDA", "REFRESH_REUTILIZADO"})


@dataclass
class Burst:
    kind: str
    ip: str
    count: int
    threshold: int
    windowMinutes: int
    codes: dict[str, int] = field(default_factory=dict)


class SecurityMonitor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[tuple[str, str], deque] = {}
        self._reported: dict[tuple, float] = {}
        self._lastPurge = 0.0

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()
            self._reported.clear()

    def _purge(self, now: float, window: float) -> None:
        if now - self._lastPurge < 30 and len(self._hits) < MAX_KEYS:
            return
        self._lastPurge = now
        for key in [key for key, hits in self._hits.items() if not hits or now - hits[-1][0] > window]:
            del self._hits[key]
        for key in [key for key, at in self._reported.items() if now - at > window]:
            del self._reported[key]
        while len(self._hits) >= MAX_KEYS:  # tope duro: se descartan las claves más viejas
            self._hits.pop(next(iter(self._hits)))

    def observe(self, kind: str, ip: str, code: str, now: float | None = None) -> Burst | None:
        """Registra un rechazo. Devuelve la ráfaga la PRIMERA vez que el origen supera el umbral en la ventana."""
        settings = getSettings()
        threshold = (settings.AUDIT_ALERT_AUTH_REJECTIONS if kind == KIND_AUTH else settings.AUDIT_ALERT_VALIDATION_REJECTIONS)
        windowMinutes = max(1, settings.AUDIT_ALERT_WINDOW_MINUTES)
        window = windowMinutes * 60.0
        now = time.monotonic() if now is None else now
        with self._lock:
            self._purge(now, window)
            # Tope por origen: un cliente que manda millones de rechazos no puede crecer la memoria (alcanza con superar el umbral).
            hits = self._hits.setdefault((kind, ip), deque(maxlen=max(2000, threshold + 10)))
            hits.append((now, code))
            while hits and now - hits[0][0] > window:
                hits.popleft()
            if threshold <= 0 or len(hits) < threshold or (kind, ip) in self._reported:
                return None
            self._reported[(kind, ip)] = now
            return Burst(kind, ip, len(hits), threshold, windowMinutes, dict(Counter(code for _, code in hits)))

    def firstRateLimit(self, ip: str, limit: str, now: float | None = None) -> bool:
        """True la primera vez que un origen excede un límite de solicitudes dentro de la ventana (los siguientes 429 no se vuelven a registrar)."""
        window = max(1, getSettings().AUDIT_ALERT_WINDOW_MINUTES) * 60.0
        now = time.monotonic() if now is None else now
        with self._lock:
            self._purge(now, window)
            key = ("limite", ip, limit)
            last = self._reported.get(key)
            if last is not None and now - last < window:
                return False
            self._reported[key] = now
            return True


monitor = SecurityMonitor()


def classifyRejection(status: int, rejection: tuple[str | None, str | None] | None) -> tuple[str, str] | None:
    """(tipo de ráfaga, código) si el rechazo debe contarse; None si es uso normal o ya se registra de a uno."""
    code, motivo = rejection or (None, None)
    if status in (401, 403):
        if code in IGNORED_CODES or motivo in IGNORED_MOTIVOS:
            return None
        return KIND_AUTH, code or str(status)
    if status in (400, 422) and code == "VALIDACION_ENTRADA":
        return KIND_VALIDATION, code
    return None


def sessionFactory():
    """Fábrica de sesiones para persistir (las pruebas la reemplazan por su base)."""
    return getSessionFactory()()


_lastAlert: dict[str, float] = {}
_alertLock = threading.Lock()


def resetAlerts() -> None:
    with _alertLock:
        _lastAlert.clear()


def alertAdministrator(burst: Burst, now: float | None = None) -> bool:
    """Alerta activa (GL-15): avisa por correo al administrador vigente de la plataforma, como máximo una vez por patrón en
    SECURITY_ALERT_EMAIL_MINUTES. El correo no lleva la IP ni datos de cuentas. Devuelve si se pidió el envío."""
    minutes = getSettings().SECURITY_ALERT_EMAIL_MINUTES
    if minutes <= 0:
        return False
    now = time.monotonic() if now is None else now
    with _alertLock:
        last = _lastAlert.get(burst.kind)
        if last is not None and now - last < minutes * 60:
            return False
        _lastAlert[burst.kind] = now
    from sqlalchemy import select

    from app.emails.eventTypes import EmailEventType
    from app.models.user import User
    from app.services import email as emailService
    from app.utils.timeZone import nowForDb

    with sessionFactory() as db:
        recipients = db.scalars(select(User.correoElectronico).where(
            User.tipoCuenta == "ADMINISTRADOR_PLATAFORMA", User.estado == "ACTIVO", User.correoElectronico.is_not(None))).all()
    what = "respuestas 401/403" if burst.kind == KIND_AUTH else "entradas rechazadas por validación"
    context = {"descripcion": f"{burst.count} {what} desde un mismo origen en {burst.windowMinutes} minutos",
               "patron": "Rechazos de autorización" if burst.kind == KIND_AUTH else "Entradas rechazadas por validación",
               "cantidad": burst.count, "ventanaMinutos": burst.windowMinutes, "fechaEvento": nowForDb(),
               "urlAuditoria": emailService.frontendUrl("/plataforma/auditoria")}
    for recipient in recipients:
        emailService.sendEmailEventInBackground(EmailEventType.ALERTA_SEGURIDAD_PLATAFORMA, recipient, context)
    return bool(recipients)


def persistBurst(burst: Burst) -> None:
    """Un único evento de auditoría por ráfaga (la IP, el cliente y la correlación salen del contexto de la solicitud que cruzó el umbral)."""
    action = classification.ACCION_RAFAGA_AUTORIZACION if burst.kind == KIND_AUTH else classification.ACCION_RAFAGA_VALIDACION
    what = "respuestas 401/403" if burst.kind == KIND_AUTH else "entradas rechazadas por validación"
    with sessionFactory() as db:
        registerEvent(
            db, "ACCESO", action, False, modulo="SEGURIDAD", motivo="RECHAZOS_REITERADOS",
            observacion=f"{burst.count} {what} desde un mismo origen en {burst.windowMinutes} minutos (umbral {burst.threshold})",
            datosNuevos={"cantidad": burst.count, "umbral": burst.threshold, "ventanaMinutos": burst.windowMinutes,
                         # lista y no diccionario: sanitize() redacta toda CLAVE que parezca un secreto (TOKEN_INVALIDO lo parece)
                         "respuestas": [{"respuesta": code, "cantidad": count} for code, count in sorted(burst.codes.items())]},
        )
        db.commit()


def persistRateLimit(limit: str) -> None:
    with sessionFactory() as db:
        registerEvent(
            db, "ACCESO", classification.ACCION_LIMITE_SOLICITUDES, False, modulo="SEGURIDAD", motivo="LIMITE_POR_ORIGEN",
            observacion=f"Un mismo origen superó el límite de solicitudes «{limit}»", datosNuevos={"limite": limit},
        )
        db.commit()


def record(status: int, rejection: tuple[str | None, str | None] | None, ip: str | None) -> None:
    """Punto de entrada del middleware. Nunca lanza: un fallo del monitor no puede afectar la respuesta que ya se envió."""
    try:
        if ip is None:
            return
        code, motivo = rejection or (None, None)
        if status == 429 and code == "DEMASIADAS_SOLICITUDES":
            limit = motivo or "general"
            if monitor.firstRateLimit(ip, limit):
                persistRateLimit(limit)
            return
        counted = classifyRejection(status, rejection)
        if counted is None:
            return
        burst = monitor.observe(counted[0], ip, counted[1])
        if burst is not None:
            persistBurst(burst)
            alertAdministrator(burst)
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo registrar un evento de seguridad")
