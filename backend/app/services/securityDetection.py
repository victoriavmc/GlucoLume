# SecurityDetection - Señales de actividad sospechosa a partir de los eventos de auditoría
#
# Qué hace: analiza los accesos fallidos que YA están auditados y busca patrones con umbrales configurables
# (Settings.AUDIT_ALERT_*, o los que la consola indique para una consulta). Qué NO hace:
#   - no escribe nada ni inventa registros: cada señal se calcula en el momento y trae los filtros que muestran los eventos que la originan;
#   - no bloquea a nadie (el bloqueo por cuenta y el límite por IP ya existen y son otro mecanismo);
#   - no llama «ataque» a un error de autenticación: un fallo aislado es OPERATIVO. Los patrones son SOSPECHOSOS (para investigar) y la
#     activación de un control (bloqueo, límite) es CONFIRMADA como hecho, no como intención.
#
# Patrones:
#   FALLOS_REPETIDOS_CUENTA   N o más accesos fallidos contra una misma cuenta (o un mismo identificador inexistente) dentro de la ventana.
#   MULTIPLES_CUENTAS_ORIGEN  M o más cuentas/identificadores distintos probados desde un mismo origen dentro de la ventana.
#   ORIGEN_INUSUAL            fallos contra una cuenta desde un origen que nunca tuvo un acceso exitoso, solo si la cuenta tiene historia
#                             suficiente (AUDIT_UNUSUAL_ORIGIN_MIN_HISTORY accesos exitosos con IP): con menos no se afirma nada.
#   y, ya registrados por los controles: bloqueos de cuenta, límites de solicitudes superados, ráfagas de 401/403 o de validación y
#   reutilización de tokens de sesión.
# Límite de alcance: se analizan como máximo MAX_ROWS intentos del período (se informa si se alcanzó). Una IP compartida (NAT, una institución)
# o una IPv6 rotativa pueden dar falsos positivos o negativos: por eso son señales, no veredictos.

import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.rateLimit import normalizeIp
from app.core.config import getSettings
from app.models.audit import Audit
from app.models.auditContext import AuditContext
from app.models.user import User
from app.schemas.auditLog import SecurityIndicators, SecuritySignal, SecuritySignals, SecurityThresholds
from app.services import auditClassification as classification
from app.services import schemaCompat
from app.utils.timeZone import nowForDb

MAX_ROWS = 5000
# Fallos de un cuenta que quiere entrar pero no puede por su estado, no por un intento de adivinar: no suman a los patrones.
NOT_GUESSING = frozenset({"CUENTA_INACTIVA", "CORREO_NO_VERIFICADO", "VINCULACION_RECHAZADA", "CORREO_PROVEEDOR_NO_VERIFICADO", "CUENTA_NO_REGISTRADA"})
SUCCESSFUL_LOGINS = ("LOGIN_PWD", "LOGIN_GOOGLE", "LOGIN_PWD_MFA", "LOGIN_GOOGLE_MFA")
LOOKBACK_DAYS = 90


def thresholds(**overrides) -> SecurityThresholds:
    """Umbrales de la configuración; una consulta puede indicar otros (acotados) sin cambiar la configuración."""
    settings = getSettings()
    values = dict(
        ventanaMinutos=settings.AUDIT_ALERT_WINDOW_MINUTES, fallosPorCuenta=settings.AUDIT_ALERT_FAILURES_PER_ACCOUNT,
        cuentasPorOrigen=settings.AUDIT_ALERT_ACCOUNTS_PER_ORIGIN, historialOrigenInusual=settings.AUDIT_UNUSUAL_ORIGIN_MIN_HISTORY,
    )
    values.update({key: value for key, value in overrides.items() if value is not None})
    return SecurityThresholds(
        ventanaMinutos=min(max(values["ventanaMinutos"], 1), 1440), fallosPorCuenta=min(max(values["fallosPorCuenta"], 2), 1000),
        cuentasPorOrigen=min(max(values["cuentasPorOrigen"], 2), 1000), historialOrigenInusual=min(max(values["historialOrigenInusual"], 1), 1000),
    )


def densestWindow(stamps: list[datetime], minutes: int) -> tuple[int, datetime, datetime]:
    """Mayor cantidad de instantes dentro de una ventana de `minutes` (ventana deslizante exacta). `stamps` ordenado ascendente."""
    width = timedelta(minutes=minutes)
    best, start = (0, stamps[0], stamps[0]), 0
    for end, stamp in enumerate(stamps):
        while stamp - stamps[start] > width:
            start += 1
        if end - start + 1 > best[0]:
            best = (end - start + 1, stamps[start], stamp)
    return best


def distinctWindow(events: list[tuple[datetime, str]], minutes: int) -> tuple[int, datetime, datetime]:
    """Mayor cantidad de claves DISTINTAS dentro de una ventana deslizante. `events` ordenado por instante."""
    width = timedelta(minutes=minutes)
    inside: dict[str, int] = {}
    best, start = (0, events[0][0], events[0][0]), 0
    for end, (stamp, key) in enumerate(events):
        inside[key] = inside.get(key, 0) + 1
        while stamp - events[start][0] > width:
            old = events[start][1]
            inside[old] -= 1
            if not inside[old]:
                del inside[old]
            start += 1
        if len(inside) > best[0]:
            best = (len(inside), events[start][0], stamp)
    return best


def _isAttempt(accion: str, motivo: str | None) -> bool:
    if accion == classification.ACCION_BLOQUEO_CUENTA or motivo in NOT_GUESSING:
        return False
    return accion.startswith("LOGIN") or accion in ("MFA_CODIGO_INVALIDO", "MFA_RECUPERACION_CODIGO_INVALIDO")


def analyze(db: Session, desde: date, hasta: date, umbrales: SecurityThresholds, *, idInstitucion: uuid.UUID | None = None) -> SecuritySignals:
    since = datetime.combine(desde, time.min)
    until = datetime.combine(hasta + timedelta(days=1), time.min)
    ready = schemaCompat.auditContextReady(db)
    columns = [Audit.fechaHora, Audit.idUsuario, Audit.accion]
    if ready:
        columns += [AuditContext.ipOrigen, AuditContext.motivo, AuditContext.identificadorHash]
    query = select(*columns).where(Audit.resultado == "FALLO", Audit.fechaHora >= since, Audit.fechaHora < until,
                                   classification.categoryFilter("ACCESOS_FALLIDOS"))
    if ready:
        query = query.outerjoin(AuditContext, AuditContext.idAuditoria == Audit.idAuditoria)
    if idInstitucion is not None:
        query = query.where(Audit.idInstitucion == idInstitucion)
    rows = db.execute(query.order_by(Audit.fechaHora.desc()).limit(MAX_ROWS)).all()
    attempts = []  # (instante, clave de la cuenta, ip agrupada, ip exacta, idUsuario, huella)
    for row in rows:
        accion, ip, motivo, fingerprint = row[2], (row[3] if ready else None), (row[4] if ready else None), (row[5] if ready else None)
        if not _isAttempt(accion, motivo):
            continue
        account = str(row[1]) if row[1] else (f"hash:{fingerprint}" if fingerprint else None)
        attempts.append((row[0], account, normalizeIp(ip) if ip else None, ip, row[1], fingerprint))
    attempts.sort(key=lambda item: item[0])

    signals: list[SecuritySignal] = []
    names = _accountNames(db, {a[4] for a in attempts if a[4]})

    # 1. Fallos repetidos contra una cuenta (o un mismo identificador inexistente).
    byAccount: dict[str, list] = defaultdict(list)
    for attempt in attempts:
        if attempt[1]:
            byAccount[attempt[1]].append(attempt)
    for account, items in byAccount.items():
        count, first, last = densestWindow([i[0] for i in items], umbrales.ventanaMinutos)
        if count >= umbrales.fallosPorCuenta:
            origins = {i[2] for i in items if i[2]}
            known = items[0][4]
            filters = {"idCuenta": str(known)} if known else {"refIdentificador": items[0][5]}
            signals.append(SecuritySignal(
                tipo="FALLOS_REPETIDOS_CUENTA", clasificacion=classification.SOSPECHOSO,
                titulo="Accesos fallidos repetidos contra una cuenta" if known else "Accesos repetidos sobre un identificador inexistente",
                descripcion=f"{count} accesos fallidos en {umbrales.ventanaMinutos} minutos"
                            + (f" desde {len(origins)} origen(es) distinto(s)" if origins else "") + ".",
                cantidad=count, umbral=umbrales.fallosPorCuenta, desde=first, hasta=last,
                cuenta=names.get(known, "Cuenta") if known else f"Identificador inexistente (ref. {items[0][5][:8]})" if items[0][5] else None,
                filtros={**filters, "categoria": "ACCESOS_FALLIDOS"}))

    # 2. Muchas cuentas distintas desde un mismo origen.
    byOrigin: dict[str, list] = defaultdict(list)
    for attempt in attempts:
        if attempt[2] and attempt[1]:
            byOrigin[attempt[2]].append(attempt)
    for origin, items in byOrigin.items():
        count, first, last = distinctWindow([(i[0], i[1]) for i in items], umbrales.ventanaMinutos)
        if count >= umbrales.cuentasPorOrigen:
            signals.append(SecuritySignal(
                tipo="MULTIPLES_CUENTAS_ORIGEN", clasificacion=classification.SOSPECHOSO, titulo="Un mismo origen probó muchas cuentas",
                descripcion=f"{count} cuentas o identificadores distintos en {umbrales.ventanaMinutos} minutos desde un mismo origen.",
                cantidad=count, umbral=umbrales.cuentasPorOrigen, desde=first, hasta=last, ipOrigen=origin,
                filtros={"ip": items[0][3], "categoria": "ACCESOS_FALLIDOS"}))

    # 3. Origen inusual para la cuenta (solo con historia suficiente).
    if ready:
        signals += _unusualOrigins(db, attempts, since, until, umbrales)

    # 4. Controles que ya actuaron y ráfagas ya registradas.
    signals += _recordedControls(db, since, until, idInstitucion, ready)

    signals.sort(key=lambda s: (s.clasificacion != classification.CONFIRMADO, -s.cantidad))
    indicators = _indicators(db, since, until, idInstitucion, attempts)
    return SecuritySignals(
        desde=desde, hasta=hasta, umbrales=umbrales, indicadores=indicators, senales=signals,
        truncado=len(rows) >= MAX_ROWS, contextoDisponible=ready,
    )


def _accountNames(db: Session, ids: set) -> dict:
    if not ids:
        return {}
    users = db.scalars(select(User).where(User.idUsuario.in_(ids)))
    return {u.idUsuario: ("Cuenta eliminada" if u.estado == "ELIMINADO" else (f"{u.nombre or ''} {u.apellido or ''}".strip() or u.usuario or "Cuenta"))
            for u in users}


def _unusualOrigins(db: Session, attempts: list, since: datetime, until: datetime, umbrales: SecurityThresholds) -> list[SecuritySignal]:
    candidates: dict[tuple, list] = defaultdict(list)
    for item in attempts:
        if item[4] and item[2]:
            candidates[(item[4], item[2])].append(item)
    if not candidates:
        return []
    names = _accountNames(db, {key[0] for key in candidates})
    signals = []
    history_since = since - timedelta(days=LOOKBACK_DAYS)
    for (account, origin), items in list(candidates.items())[:200]:
        successful = db.execute(
            select(AuditContext.ipOrigen).join(Audit, Audit.idAuditoria == AuditContext.idAuditoria)
            .where(Audit.idUsuario == account, Audit.resultado == "EXITO", Audit.accion.in_(SUCCESSFUL_LOGINS),
                   AuditContext.ipOrigen.is_not(None), Audit.fechaHora >= history_since, Audit.fechaHora < until)
        ).scalars().all()
        if len(successful) < umbrales.historialOrigenInusual:
            continue  # sin historia suficiente no se puede decir que un origen sea inusual
        if origin in {normalizeIp(ip) for ip in successful}:
            continue  # la cuenta ya entró bien desde ahí (antes o después): un descuido, no un origen ajeno
        signals.append(SecuritySignal(
            tipo="ORIGEN_INUSUAL", clasificacion=classification.SOSPECHOSO, titulo="Fallos desde un origen nunca usado por la cuenta",
            descripcion=f"{len(items)} acceso(s) fallido(s) desde un origen sin accesos exitosos previos; la cuenta tiene {len(successful)} accesos "
                        f"exitosos con origen registrado en los últimos {LOOKBACK_DAYS} días. Es un indicio débil: puede ser un viaje o una red nueva.",
            cantidad=len(items), umbral=umbrales.historialOrigenInusual, desde=items[0][0], hasta=items[-1][0], ipOrigen=origin,
            cuenta=names.get(account, "Cuenta"), filtros={"idCuenta": str(account), "ip": items[0][3] or origin, "categoria": "ACCESOS_FALLIDOS"}))
    return signals


RECORDED = (
    (classification.ACCION_BLOQUEO_CUENTA, "BLOQUEOS_CUENTA", "Cuentas bloqueadas temporalmente", classification.CONFIRMADO),
    ("REFRESH_REUTILIZADO", "SESION_REUTILIZADA", "Reutilización de una sesión ya renovada", classification.CONFIRMADO),
    (classification.ACCION_LIMITE_SOLICITUDES, "LIMITE_SOLICITUDES", "Límite de solicitudes por origen superado", classification.CONFIRMADO),
    (classification.ACCION_RAFAGA_AUTORIZACION, "RAFAGA_RECHAZOS", "Ráfagas de respuestas 401/403 desde un origen", classification.SOSPECHOSO),
    (classification.ACCION_RAFAGA_VALIDACION, "RAFAGA_VALIDACION", "Ráfagas de entradas rechazadas por validación", classification.SOSPECHOSO),
)


def _recordedControls(db: Session, since: datetime, until: datetime, idInstitucion, ready: bool) -> list[SecuritySignal]:
    signals = []
    for accion, tipo, titulo, kind in RECORDED:
        query = select(func.count(), func.min(Audit.fechaHora), func.max(Audit.fechaHora)).where(
            Audit.accion == accion, Audit.fechaHora >= since, Audit.fechaHora < until)
        if idInstitucion is not None:
            query = query.where(Audit.idInstitucion == idInstitucion)
        count, first, last = db.execute(query).one()
        if not count:
            continue
        confirmed = kind == classification.CONFIRMADO
        signals.append(SecuritySignal(
            tipo=tipo, clasificacion=kind, titulo=titulo, cantidad=count, desde=first, hasta=last,
            descripcion=("El sistema aplicó el control %d vez/veces. Es un hecho comprobado; no indica por sí solo que alguien atacara la cuenta."
                         if confirmed else "Registrado %d vez/veces por el monitor de solicitudes rechazadas. Conviene revisar el origen.") % count,
            filtros={"accion": accion}))
    return signals


def _indicators(db: Session, since: datetime, until: datetime, idInstitucion, attempts: list) -> SecurityIndicators:
    def count(accion: str) -> int:
        query = select(func.count()).where(Audit.accion == accion, Audit.fechaHora >= since, Audit.fechaHora < until)
        if idInstitucion is not None:
            query = query.where(Audit.idInstitucion == idInstitucion)
        return db.scalar(query) or 0

    return SecurityIndicators(
        intentosFallidos=len(attempts), cuentasAfectadas=len({a[1] for a in attempts if a[1]}), origenesDistintos=len({a[2] for a in attempts if a[2]}),
        bloqueos=count(classification.ACCION_BLOQUEO_CUENTA), limitesExcedidos=count(classification.ACCION_LIMITE_SOLICITUDES),
        rafagasRechazos=count(classification.ACCION_RAFAGA_AUTORIZACION) + count(classification.ACCION_RAFAGA_VALIDACION),
    )


def defaultPeriod() -> tuple[date, date]:
    today = nowForDb().date()
    return today - timedelta(days=1), today
