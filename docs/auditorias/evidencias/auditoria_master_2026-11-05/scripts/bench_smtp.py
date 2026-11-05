"""Medición del camino de correo de GlucoLume contra el sumidero local (smtp_sink.py). NO envía correo real:
el destino es @example.com (dominio reservado) y el servidor SMTP es 127.0.0.1.

Escenarios (argumento 1):
  render                 -> CPU de validación + render Jinja + construcción del MIME (sin red)
  phases:<puerto>        -> tiempo por fase de sendEmailEvent (apertura TCP/STARTTLS/AUTH, DATA, QUIT)
  delay:<puerto>:<n>     -> n envíos sincrónicos completos (conexión nueva por correo) y n envíos con conexión compartida
  blackhole:<puerto>     -> duración de sendEmailEvent cuando el servidor no responde (debe cortar por timeout de 20 s)
  queue:<puerto>:<n>     -> encola n avisos con sendEmailEventInBackground y mide cola y tiempo de vaciado
"""
import json
import os
import smtplib
import statistics
import sys
import time

sys.path.insert(0, ".")
PORT = None
os.environ.setdefault("API_ENV", "development")

scenario = sys.argv[1]
parts = scenario.split(":")
kind = parts[0]
PORT = int(parts[1]) if len(parts) > 1 else 8025
N = int(parts[2]) if len(parts) > 2 else 5

PKI = os.path.join(os.environ["SCR"], "pki")
os.environ.update({
    "SMTP_HOST": "localhost",
    "SMTP_PORT": str(PORT),
    "SMTP_USERNAME": "laboratorio@example.com",
    "SMTP_PASSWORD": "laboratorio-no-real",
    "SMTP_FROM": "laboratorio@example.com",
    "FRONTEND_URL": "http://localhost:5173",
    "API_BASE_URL": "http://localhost:8000",
    "DB_HOST": "localhost", "DB_USER": "lab", "DB_PASSWORD": "lab-no-real", "DB_NAME": "lab",
    "JWT_SECRET": "laboratorio-jwt-secreto-de-prueba-0123456789",
    "SSL_CERT_FILE": os.path.join(PKI, "ca.pem"),  # confía solo en la CA de laboratorio; la verificación sigue activa
})

from app.emails.eventTypes import EmailEventType as E  # noqa: E402
from app.services import email as emailService  # noqa: E402
from app.integrations.email import sender  # noqa: E402

CONTEXTS = {
    E.EMAIL_VERIFICACION: {"urlVerificacion": "http://localhost:5173/verificar-correo?token=lab", "fechaExpiracion": "mañana", "plazoHoras": 24, "nombre": "Ana"},
    E.CODIGO_CAMBIO_PASSWORD: {"nombre": "Ana", "codigoSeguridad": "123456", "minutosValidez": 10},
}
EVENT = E.EMAIL_VERIFICACION
DEST = "laboratorio+1@example.com"


def pct(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p * (len(values) - 1))))]


def stats(values):
    return {"n": len(values), "p50_ms": round(statistics.median(values), 1), "p95_ms": round(pct(values, 0.95), 1),
            "max_ms": round(max(values), 1)}


def ms(fn, *args, **kwargs):
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, (time.perf_counter() - t0) * 1000


def scenarioRender():
    out = {}
    for event, context in CONTEXTS.items():
        renders, builds = [], []
        for _ in range(40):
            _, dt = ms(emailService.renderEmailEvent, event, DEST, dict(context))
            renders.append(dt)
            _, dt = ms(emailService.buildEmailMessage, event, DEST, dict(context))
            builds.append(dt)
        out[event.value] = {"render_jinja_validacion": stats(renders), "construccion_mime_con_banner": stats(builds)}
    return out


class Phases:
    """Envuelve métodos de smtplib (sin tocar el repositorio) para separar las fases de un envío."""

    def __init__(self):
        self.t = {}
        orig_init = smtplib.SMTP.__init__
        orig_starttls, orig_login = smtplib.SMTP.starttls, smtplib.SMTP.login
        orig_send, orig_quit = smtplib.SMTP.send_message, smtplib.SMTP.quit
        self._orig = (orig_init, orig_starttls, orig_login, orig_send, orig_quit)
        phases = self

        def init(obj, *a, **k):
            t0 = time.perf_counter(); orig_init(obj, *a, **k); phases.t["tcp_ehlo_ms"] = (time.perf_counter() - t0) * 1000
        def starttls(obj, *a, **k):
            t0 = time.perf_counter(); r = orig_starttls(obj, *a, **k); phases.t["starttls_ms"] = (time.perf_counter() - t0) * 1000; return r
        def login(obj, *a, **k):
            t0 = time.perf_counter(); r = orig_login(obj, *a, **k); phases.t["auth_ms"] = (time.perf_counter() - t0) * 1000; return r
        def send(obj, *a, **k):
            t0 = time.perf_counter(); r = orig_send(obj, *a, **k); phases.t["mail_rcpt_data_ms"] = (time.perf_counter() - t0) * 1000; return r
        def quit_(obj, *a, **k):
            t0 = time.perf_counter(); r = orig_quit(obj, *a, **k); phases.t["quit_ms"] = (time.perf_counter() - t0) * 1000; return r
        smtplib.SMTP.__init__, smtplib.SMTP.starttls, smtplib.SMTP.login = init, starttls, login
        smtplib.SMTP.send_message, smtplib.SMTP.quit = send, quit_

    def restore(self):
        smtplib.SMTP.__init__, smtplib.SMTP.starttls, smtplib.SMTP.login, smtplib.SMTP.send_message, smtplib.SMTP.quit = self._orig


def scenarioPhases():
    phases = Phases()
    rows = []
    try:
        for _ in range(N):
            phases.t.clear()
            ok, total = ms(emailService.sendEmailEvent, EVENT, DEST, dict(CONTEXTS[EVENT]))
            assert ok, "el envío de laboratorio falló"
            rows.append({"total_ms": total, **phases.t})
    finally:
        phases.restore()
    keys = sorted({k for r in rows for k in r})
    return {"sink_puerto": PORT, "n": N, "fases": {k: stats([r[k] for r in rows if k in r]) for k in keys}}


def scenarioDelay():
    totals = []
    for _ in range(N):
        ok, dt = ms(emailService.sendEmailEvent, EVENT, DEST, dict(CONTEXTS[EVENT]))
        assert ok
        totals.append(dt)
    # Dos correos del mismo flujo: con conexión propia cada uno, y con una sola conexión compartida (patrón de contacto).
    pairs_separate, pairs_shared = [], []
    for _ in range(N):
        _, a = ms(emailService.sendEmailEvent, EVENT, DEST, dict(CONTEXTS[EVENT]))
        _, b = ms(emailService.sendEmailEvent, EVENT, DEST, dict(CONTEXTS[EVENT]))
        pairs_separate.append(a + b)
        t0 = time.perf_counter()
        with emailService.smtpSession() as session:
            assert emailService.sendEmailEvent(EVENT, DEST, dict(CONTEXTS[EVENT]), session=session)
            assert emailService.sendEmailEvent(EVENT, DEST, dict(CONTEXTS[EVENT]), session=session)
        pairs_shared.append((time.perf_counter() - t0) * 1000)
    return {"sink_puerto": PORT, "envio_unico_sincronico": stats(totals), "dos_correos_conexion_propia": stats(pairs_separate),
            "dos_correos_conexion_compartida": stats(pairs_shared)}


def scenarioBlackhole():
    ok, dt = ms(emailService.sendEmailEvent, EVENT, DEST, dict(CONTEXTS[EVENT]))
    return {"sink_puerto": PORT, "devuelve_enviado": ok, "duracion_ms": round(dt, 1),
            "nota": "tiempo que el hilo de la petición queda bloqueado antes de recibir False"}


def scenarioQueue():
    executor = emailService._executor
    samples = []
    t0 = time.perf_counter()
    for _ in range(N):
        emailService.sendEmailEventInBackground(EVENT, DEST, dict(CONTEXTS[EVENT]))
    enqueue_ms = (time.perf_counter() - t0) * 1000
    queued_at_enqueue = executor._work_queue.qsize()
    while True:
        q = executor._work_queue.qsize()
        samples.append(q)
        if q == 0 and not any(getattr(t, "_running", False) for t in []):
            # esperar a que los trabajos en curso terminen
            time.sleep(0.2)
            if executor._work_queue.qsize() == 0:
                # margen para el último trabajo en curso
                break
        time.sleep(0.25)
        if time.perf_counter() - t0 > 600:
            break
    drain_ms = (time.perf_counter() - t0) * 1000
    return {"sink_puerto": PORT, "encolados": N, "tiempo_encolar_ms": round(enqueue_ms, 2),
            "cola_justo_al_encolar": queued_at_enqueue, "tiempo_hasta_vaciar_ms": round(drain_ms, 1),
            "workers": executor._max_workers}


if __name__ == "__main__":
    fn = {"render": scenarioRender, "phases": scenarioPhases, "delay": scenarioDelay,
          "blackhole": scenarioBlackhole, "queue": scenarioQueue}[kind]
    result = fn()
    print(json.dumps({"escenario": scenario, "resultado": result}, ensure_ascii=False, indent=1))
