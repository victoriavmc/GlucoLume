"""Servidor SMTP de LABORATORIO (sumidero). Escucha solo en 127.0.0.1, exige STARTTLS y AUTH, descarta los mensajes
y no reenvía nada a ningún lado. Sirve para medir el camino de envío de app/integrations/email/sender.py sin enviar
correos reales.

Uso: python smtp_sink.py <puerto> <retardo_ms_por_comando> [blackhole_cmd_segundos]
  - retardo_ms_por_comando: pausa artificial antes de responder cada comando SMTP (simula RTT + procesamiento).
  - blackhole_cmd_segundos: si se indica, EHLO (el primer comando del cliente) se demora esa cantidad de segundos
    (simula un servidor que no responde; el cliente aplica su timeout de 20 s).
"""
import asyncio
import logging
import os
import sys
import time

from aiosmtpd import smtp as smtpmod
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult

PKI = os.environ.get("SINK_PKI", os.path.join(os.path.dirname(__file__), "pki"))
port = int(sys.argv[1])
delay = float(sys.argv[2]) / 1000.0
blackhole = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0

logging.basicConfig(level=logging.WARNING)
DELAYED = ("smtp_EHLO", "smtp_HELO", "smtp_STARTTLS", "smtp_AUTH", "smtp_MAIL", "smtp_RCPT", "smtp_DATA", "smtp_QUIT", "smtp_RSET")
STATS = {"mensajes": 0, "conexiones": 0, "comandos": 0}


def _wrap(name):
    original = getattr(smtpmod.SMTP, name)

    async def wrapped(self, *args, **kwargs):
        STATS["comandos"] += 1
        if name == "smtp_EHLO" and blackhole:
            await asyncio.sleep(blackhole)
        elif delay:
            await asyncio.sleep(delay)
        return await original(self, *args, **kwargs)

    setattr(smtpmod.SMTP, name, wrapped)


for _name in DELAYED:
    if hasattr(smtpmod.SMTP, _name):
        _wrap(_name)


class Handler:
    async def handle_DATA(self, server, session, envelope):
        STATS["mensajes"] += 1  # se descarta: nada sale de este proceso
        return "250 OK (laboratorio)"


def authenticator(server, session, envelope, mechanism, auth_data):
    # Credenciales de laboratorio (no son reales).
    return AuthResult(success=True)


import ssl  # noqa: E402

context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
context.load_cert_chain(os.path.join(PKI, "srv.pem"), os.path.join(PKI, "srv.key"))

controller = Controller(
    Handler(), hostname="127.0.0.1", port=port, authenticator=authenticator,
    tls_context=context, require_starttls=True, auth_require_tls=True,
    auth_exclude_mechanism=["DIGEST-MD5"],
)
controller.start()
print(f"SINK listo en 127.0.0.1:{port} retardo={delay*1000:.0f}ms blackhole={blackhole}s", flush=True)
try:
    while True:
        time.sleep(1)
        if os.environ.get("SINK_STATS"):
            print(STATS, flush=True)
except KeyboardInterrupt:
    pass
finally:
    controller.stop()
