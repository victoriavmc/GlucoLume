# Generación del correo (plantilla Jinja + MIME con banner embebido), SIN enviar. Entorno de laboratorio.
import _env  # noqa: F401
import datetime as dt, json, statistics, sys
from app.emails import eventTypes
from app.services import email as emailService
from app.emails.renderer import renderEmail

def pct(vals, p):
    s = sorted(vals); k = (len(s) - 1) * p; lo = int(k); hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)

def valueFor(key: str):
    low = key.lower()
    if "fecha" in low: return dt.datetime(2026, 11, 5, 12, 0, 0)
    if "url" in low: return "https://glucolume.example/ruta?token=prueba"
    if low.startswith("plazo") or low.startswith("cantidad") or low.startswith("numero"): return 3
    if key in ("correoRemitente", "email"): return "remitente@example.com"
    return "Dato de prueba"

results = []
for event in eventTypes.EmailEventType:
    spec = eventTypes.EMAIL_EVENTS.get(event)
    if spec is None:
        continue
    ctx = {k: valueFor(k) for k in spec.requiredContext}
    for url_key in spec.actionUrls:
        ctx.setdefault(url_key, "https://glucolume.example/ruta")
    try:
        emailService.buildEmailMessage(event, "destino@example.com", ctx, incluirDetalleMedicion=True)
    except Exception as error:
        results.append({"evento": event.value, "error": f"{type(error).__name__}: {str(error)[:120]}"}); continue
    renderTimes, buildTimes = [], []
    for _ in range(20):
        import time
        t = time.perf_counter(); emailService.renderEmailEvent(event, "destino@example.com", ctx, incluirDetalleMedicion=True)
        renderTimes.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter(); msg = emailService.buildEmailMessage(event, "destino@example.com", ctx, incluirDetalleMedicion=True)
        buildTimes.append((time.perf_counter() - t) * 1000)
    raw = len(msg.as_bytes())
    results.append({"evento": event.value, "renderMsP50": round(pct(renderTimes, .5), 2), "renderMsP95": round(pct(renderTimes, .95), 2),
                    "buildMsP50": round(pct(buildTimes, .5), 2), "buildMsP95": round(pct(buildTimes, .95), 2), "mensajeBytes": raw})
print(json.dumps(results, ensure_ascii=False))
