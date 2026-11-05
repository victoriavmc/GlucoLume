# Harness de medición SMTP para la remediación de rendimiento (5/11/2026).
#
# Ejecuta el código REAL de la aplicación (backend de GlucoLume indicado por --backend) contra un servidor SMTP de PRUEBAS local
# (aiosmtpd con STARTTLS y AUTH). Ningún correo sale de la máquina: el sumidero es local y el proxy TCP simula RTT y ancho de banda de
# subida. Cuenta conexiones TCP abiertas al servidor y mensajes DATA recibidos, y mide la duración de cada flujo.
#
# Uso (el certificado de prueba se genera con openssl; ver README de la remediación):
#   python smtp_bench.py --certs CARPETA_CERT --backend RUTA_BACKEND --escenario flujo_contacto --rtt-ms 50 --subida-mbps 2 --n 10 --salida out.json
#   escenarios:
#     flujo_contacto   : contactService.sendContactMessage (consulta + confirmación), código del backend indicado
#     par_sin_sesion   : dos sendEmailEvent seguidos, cada uno con su conexión (código previo y actual)
#     par_con_sesion   : dos sendEmailEvent seguidos sobre una smtpSession (requiere el código con smtpSession)
#
# Requiere: aiosmtpd (solo para esta medición, fuera de requirements.txt) y openssl para generar cert.pem / key.pem.

import argparse
import asyncio
import json
import os
import ssl
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult

HERE = Path(__file__).resolve().parent
SINK_PORT, PROXY_PORT = 8025, 8026  # el código habla con el PROXY (que simula la red); el proxy reenvía al sumidero


class Counters:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.connections = 0  # contador monotónico: id() de objetos recolectables puede reutilizarse
        self.messages = 0

    def snapshot(self) -> tuple[int, int]:
        with self.lock:
            return self.connections, self.messages


COUNTERS = Counters()


class Sink:
    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        with COUNTERS.lock:
            COUNTERS.messages += 1
        return "250 OK"


def authenticator(server, session, envelope, mechanism, auth_data):
    return AuthResult(success=True)


def startSink(certDir: Path) -> Controller:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certDir / "cert.pem", certDir / "key.pem")
    controller = Controller(Sink(), hostname="127.0.0.1", port=SINK_PORT, tls_context=context, require_starttls=True,
                            authenticator=authenticator, auth_required=True, auth_require_tls=True)
    controller.start()
    return controller


async def _pump(reader, writer, oneWay: float, bps: float | None) -> None:
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    async def read():
        nextFree = 0.0
        while True:
            data = await reader.read(65536)
            now = loop.time()
            start = max(now, nextFree)
            serial = (len(data) * 8 / bps) if (bps and data) else 0.0
            nextFree = start + serial
            await queue.put((start + serial + oneWay, data))
            if not data:
                break

    async def write():
        while True:
            at, data = await queue.get()
            wait = at - loop.time()
            if wait > 0:
                await asyncio.sleep(wait)
            if not data:
                writer.close()
                break
            writer.write(data)
            await writer.drain()

    await asyncio.gather(read(), write(), return_exceptions=True)


def startProxy(oneWay: float, bps: float | None) -> threading.Thread:
    async def handle(clientReader, clientWriter):
        with COUNTERS.lock:  # una conexión TCP del cliente = una conexión SMTP (el proxy ve cada una)
            COUNTERS.connections += 1
        try:
            upReader, upWriter = await asyncio.open_connection("127.0.0.1", SINK_PORT)
        except OSError:
            clientWriter.close()
            return
        await asyncio.gather(_pump(clientReader, upWriter, oneWay, bps), _pump(upReader, clientWriter, oneWay, None),
                             return_exceptions=True)

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def serve():
            server = await asyncio.start_server(handle, "127.0.0.1", PROXY_PORT)
            async with server:
                await server.serve_forever()

        loop.run_until_complete(serve())

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    time.sleep(0.3)
    return thread


CHILD = r"""
import json, sys, time, statistics
backend, escenario, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
sys.path.insert(0, backend)
import os
os.chdir(backend)
from app.services import contact as contactService, email as emailService
from app.emails.eventTypes import EmailEventType
from app.schemas.contact import ContactRequest

def contact(i):
    return ContactRequest(nombre="Ana Pérez", email=f"ana{i}@example.com", tipoConsulta="INSTITUCIONES",
                          asunto="Uso en un consultorio", mensaje="Queremos usar GlucoLume en nuestro consultorio.", sitioWeb="")

results = []
for i in range(n):
    t0 = time.perf_counter()
    outcome = None
    try:
        if escenario == "flujo_contacto":
            outcome = contactService.sendContactMessage(contact(i), f"10.{i // 250}.0.{i % 250}")
        elif escenario == "par_sin_sesion":
            ctx = {"nombreRemitente": "Ana", "correoRemitente": f"ana{i}@example.com", "tipoConsulta": "Consulta",
                   "asuntoConsulta": "Asunto", "mensaje": "Hola", "fechaEvento": "2026-11-05 10:00"}
            outcome = [emailService.sendEmailEvent(EmailEventType.CONTACTO_RECIBIDO, "contacto@example.com", ctx, replyTo=f"ana{i}@example.com"),
                       emailService.sendEmailEvent(EmailEventType.CONTACTO_RECIBIDO, "contacto@example.com", ctx, replyTo=f"ana{i}@example.com")]
        elif escenario == "par_con_sesion":
            ctx = {"nombreRemitente": "Ana", "correoRemitente": f"ana{i}@example.com", "tipoConsulta": "Consulta",
                   "asuntoConsulta": "Asunto", "mensaje": "Hola", "fechaEvento": "2026-11-05 10:00"}
            with emailService.smtpSession() as s:
                outcome = [emailService.sendEmailEvent(EmailEventType.CONTACTO_RECIBIDO, "contacto@example.com", ctx, replyTo=f"ana{i}@example.com", session=s),
                           emailService.sendEmailEvent(EmailEventType.CONTACTO_RECIBIDO, "contacto@example.com", ctx, replyTo=f"ana{i}@example.com", session=s)]
    except Exception as error:  # se registra, no se oculta
        outcome = f"EXC {type(error).__name__}:{getattr(error, 'code', None)}"
    results.append({"ms": (time.perf_counter() - t0) * 1000, "resultado": outcome if isinstance(outcome, (bool, list, type(None))) else str(outcome)})
print(json.dumps(results))
print("LOG-ENVIADOS", file=sys.stderr)
"""


def writeEnv(path: Path) -> None:
    values = {
        "API_ENV": "development", "DB_HOST": "sin-conexion.invalid", "DB_NAME": "GlucoLume_Pruebas_SinConexion", "DB_USER": "lab",
        "DB_PASSWORD": "lab-no-real", "JWT_SECRET": "lab-jwt-secret-no-real-0123456789abcdef0123456789",
        "MFA_ENCRYPTION_KEY": os.environ["MFA_KEY_BENCH"], "FRONTEND_URL": "https://glucolume.example",
        "API_BASE_URL": "https://glucolume.example", "SMTP_HOST": "127.0.0.1", "SMTP_PORT": str(PROXY_PORT),
        "SMTP_USERNAME": "glucolume@example.com", "SMTP_PASSWORD": "lab-no-real", "SMTP_FROM": "glucolume@example.com",
        "CONTACT_EMAIL": "contacto@example.com",
    }
    path.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", required=True)
    parser.add_argument("--escenario", required=True, choices=["flujo_contacto", "par_sin_sesion", "par_con_sesion"])
    parser.add_argument("--rtt-ms", type=float, default=0.0)
    parser.add_argument("--subida-mbps", type=float, default=0.0, help="0 = sin límite")
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--salida", required=True)
    parser.add_argument("--certs", required=True, help="carpeta con cert.pem y key.pem de PRUEBA (fuera del repositorio)")
    args = parser.parse_args()

    certDir = Path(args.certs)
    envFile = Path(os.environ.get("TMPDIR", "/tmp")) / f"bench_{os.getpid()}.env"
    writeEnv(envFile)
    controller = startSink(certDir)
    startProxy(args.rtt_ms / 2000.0, (args.subida_mbps * 1_000_000) if args.subida_mbps else None)
    env = dict(os.environ, GLUCOLUME_ENV_FILE=str(envFile), SSL_CERT_FILE=str(certDir / "cert.pem"))
    try:
        before = COUNTERS.snapshot()
        proc = subprocess.run([sys.executable, "-c", CHILD, args.backend, args.escenario, str(args.n)],
                              capture_output=True, text=True, env=env, timeout=900)
        after = COUNTERS.snapshot()
    finally:
        controller.stop()
        envFile.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise SystemExit(f"Falló el proceso hijo:\n{proc.stderr[-3000:]}")
    if proc.stderr.strip():
        print("[log hijo] " + proc.stderr.strip()[-800:], file=sys.stderr)
    rows = json.loads(proc.stdout.strip().splitlines()[-1])
    ms = [r["ms"] for r in rows]
    summary = {
        "backend": args.backend, "escenario": args.escenario, "rttMs": args.rtt_ms, "subidaMbps": args.subida_mbps, "n": args.n,
        "p50Ms": round(statistics.median(ms), 1), "p95Ms": round(sorted(ms)[max(0, int(round(0.95 * len(ms))) - 1)], 1),
        "conexionesSmtp": after[0] - before[0], "mensajesDataRecibidos": after[1] - before[1],
        "resultados": [r["resultado"] for r in rows],
    }
    Path(args.salida).write_text(json.dumps({"resumen": summary, "muestras": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
