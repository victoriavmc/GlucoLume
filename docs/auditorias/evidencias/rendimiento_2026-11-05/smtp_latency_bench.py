# Latencia del envío SMTP REAL del código (integrations/email/sender._send) contra un sumidero LOCAL (aiosmtpd con STARTTLS).
# No sale ningún correo de la máquina: el servidor es local y el proxy simula RTT y ancho de banda de subida.
import _env  # noqa: F401  (carga la configuración de prueba y el path del backend)
import os as _os
_os.environ["SMTP_PORT"] = "8026"  # el código habla con el PROXY (que simula la red), no directo con el sumidero
import asyncio, json, os, smtplib, ssl, statistics, sys, threading, time
os.environ["SSL_CERT_FILE"] = os.path.join(os.path.dirname(__file__), "cert.pem")  # confía en el certificado de prueba
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult
from app.integrations.email import sender
from app.services import email as emailService
from app.emails.eventTypes import EmailEventType

HERE = os.path.dirname(__file__)
SINK_PORT, PROXY_PORT = 8025, 8026
CONFIG = {"oneWayS": 0.0, "uploadBps": None}

class Sink:
    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        envelope.rcpt_tos.append(address); return "250 OK"
    async def handle_DATA(self, server, session, envelope):
        return "250 OK"

def authenticator(server, session, envelope, mechanism, auth_data):
    return AuthResult(success=True)

async def pump(reader, writer, oneWay, bps):
    queue = asyncio.Queue(); loop = asyncio.get_running_loop()
    async def read():
        nextFree = 0.0
        while True:
            data = await reader.read(65536)
            now = loop.time(); start = max(now, nextFree)
            serial = (len(data) * 8 / bps) if (bps and data) else 0.0
            nextFree = start + serial
            await queue.put((start + serial + oneWay, data))
            if not data: break
    async def write():
        while True:
            at, data = await queue.get()
            wait = at - loop.time()
            if wait > 0: await asyncio.sleep(wait)
            if not data:
                writer.close(); break
            writer.write(data); await writer.drain()
    await asyncio.gather(read(), write(), return_exceptions=True)

async def handle(client_reader, client_writer):
    try:
        up_reader, up_writer = await asyncio.open_connection("127.0.0.1", SINK_PORT)
    except OSError:
        client_writer.close(); return
    await asyncio.gather(
        pump(client_reader, up_writer, CONFIG["oneWayS"], CONFIG["uploadBps"]),
        pump(up_reader, client_writer, CONFIG["oneWayS"], None),
        return_exceptions=True)

def startProxy(loop):
    async def serve():
        server = await asyncio.start_server(handle, "127.0.0.1", PROXY_PORT)
        async with server: await server.serve_forever()
    asyncio.run_coroutine_threadsafe(serve(), loop)

class CountingSMTP(smtplib.SMTP):
    commands = 0
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.set_debuglevel(1)  # activa el registro de smtplib para contar cada comando enviado
    def _print_debug(self, *args):
        if args and args[0] == "send:": CountingSMTP.commands += 1
smtplib.SMTP = CountingSMTP  # solo en este proceso: contar comandos SMTP por envío

def pct(vals, p):
    s = sorted(vals); k = (len(s) - 1) * p; lo = int(k); hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)

if __name__ == "__main__":
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(os.path.join(HERE, "cert.pem"), os.path.join(HERE, "key.pem"))
    controller = Controller(Sink(), hostname="127.0.0.1", port=SINK_PORT, tls_context=ctx, require_starttls=True,
                            authenticator=authenticator, auth_require_tls=True)
    controller.start()
    loop = asyncio.new_event_loop(); threading.Thread(target=loop.run_forever, daemon=True).start(); startProxy(loop)
    time.sleep(0.5)
    # Mensaje real de verificación de correo (con banner) y el mismo texto sin banner, para medir su peso.
    ctxMail = {"nombre": "Prueba", "urlVerificacion": "https://glucolume.example/verificar-correo?token=prueba",
               "fechaExpiracion": __import__("datetime").datetime(2026, 11, 5, 12, 0), "plazoHoras": 24}
    msgBanner = emailService.buildEmailMessage(EmailEventType.EMAIL_VERIFICACION, "destino@example.com", ctxMail)
    rendered = emailService.renderEmailEvent(EmailEventType.EMAIL_VERIFICACION, "destino@example.com", ctxMail)[1]
    msgSinBanner = sender.buildHtmlMessage("destino@example.com", rendered.subject, rendered.html, rendered.text, ())
    sizes = {"conBanner": len(msgBanner.as_bytes()), "sinBanner": len(msgSinBanner.as_bytes())}
    print(json.dumps({"tamanioMensaje": sizes}))
    grid = [(0, None, 10), (50, None, 10), (150, None, 10), (50, 10_000_000, 5), (50, 2_000_000, 5)]
    rows = []
    for rttMs, bps, n in grid:
        CONFIG["oneWayS"] = rttMs / 2000.0; CONFIG["uploadBps"] = bps
        times, cmds, fails = [], [], 0
        for _ in range(n):
            CountingSMTP.commands = 0
            t = time.perf_counter()
            try:
                sender._send(msgBanner)
                times.append((time.perf_counter() - t) * 1000)
            except Exception as error:
                fails += 1; print("FALLO", type(error).__name__, str(error)[:120], file=sys.stderr)
            cmds.append(CountingSMTP.commands)
        rows.append({"rttMs": rttMs, "subidaMbps": None if bps is None else bps / 1e6, "n": len(times), "fallos": fails,
                     "envioMsP50": round(pct(times, .5), 1) if times else None, "envioMsP95": round(pct(times, .95), 1) if times else None,
                     "comandosSmtpP50": pct(cmds, .5) if cmds else None})
        print(json.dumps(rows[-1]), flush=True)
    controller.stop()
    print(json.dumps({"resumen": rows, "tamanioMensaje": sizes}))
