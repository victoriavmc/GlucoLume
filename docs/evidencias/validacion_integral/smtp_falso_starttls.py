"""SMTP falso con STARTTLS para el ENSAYO (127.0.0.1/0.0.0.0, datos sintéticos): acepta cualquier credencial y guarda cada correo recibido en un archivo
JSONL, para poder completar la verificación de correo y las confirmaciones sin enviar nada real. Uso: smtp_falso_starttls.py <cert.pem> <key.pem> <salida.jsonl> [puerto]
El backend verifica el certificado y el nombre del servidor (GL-04): el certificado de prueba se le entrega como autoridad con SSL_CERT_FILE."""
import email, json, ssl, sys
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult

cert, key, out = sys.argv[1:4]
port = int(sys.argv[4]) if len(sys.argv) > 4 else 2525


class Handler:
    async def handle_DATA(self, server, session, envelope):
        message = email.message_from_bytes(envelope.content)
        body = ""
        for part in message.walk():
            if part.get_content_type() in ("text/plain", "text/html"):
                body += part.get_payload(decode=True).decode("utf-8", "replace") + "\n"
        with open(out, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"to": envelope.rcpt_tos, "subject": str(email.header.make_header(email.header.decode_header(message["Subject"] or ""))), "body": body}) + "\n")
        return "250 OK"


context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(cert, key)
controller = Controller(Handler(), hostname="0.0.0.0", port=port, tls_context=context, require_starttls=True,
                        authenticator=lambda server, session, envelope, mechanism, auth_data: AuthResult(success=True), auth_required=False,
                        auth_require_tls=True)
controller.start()
print("SMTP falso listo en", port, flush=True)
import threading
threading.Event().wait()
