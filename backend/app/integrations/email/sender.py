# EmailSender - Envío de correo por SMTP con STARTTLS
#
# Transporte únicamente: no arma contenidos. El HTML de los eventos lo construye
# app/services/email.py a partir de las plantillas de app/emails.

import re
import smtplib
import socket
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from app.core.config import getSettings

SMTP_TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class InlineImage:
    """Imagen embebida referenciada desde el HTML como cid:<cid>."""

    cid: str
    content: bytes
    subtype: str  # png, jpeg, gif...
    filename: str


def _sender() -> str:
    settings = getSettings()
    return formataddr((settings.SMTP_FROM_NAME, settings.SMTP_FROM or settings.SMTP_USERNAME))


def tlsContext() -> ssl.SSLContext:
    """Contexto de STARTTLS que verifica el certificado y el nombre del servidor SMTP (GL-04). Sin contexto, smtplib usa uno que no
    verifica nada: un intermediario podría leer la credencial y los correos (incluidos los resultados de mediciones)."""
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def _send(message: EmailMessage) -> None:
    settings = getSettings()
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as server:
        server.starttls(context=tlsContext())
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD.get_secret_value())
        server.send_message(message)


def buildHtmlMessage(
    to: str,
    subject: str,
    html: str,
    text: str,
    inlineImages: tuple[InlineImage, ...] = (),
    replyTo: str | None = None,
) -> EmailMessage:
    """multipart/alternative (texto + HTML); las imágenes van como multipart/related del HTML.

    From es siempre la cuenta SMTP de GlucoLume (nunca un correo ingresado por terceros: SPF/DMARC).
    replyTo permite responder a otra dirección sin falsificar el remitente.
    """
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = _sender()
    message["To"] = to
    if replyTo:
        message["Reply-To"] = replyTo
    message["Message-ID"] = make_msgid(domain="glucolume")
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    htmlPart = message.get_payload()[1]
    for image in inlineImages:
        htmlPart.add_related(
            image.content,
            maintype="image",
            subtype=image.subtype,
            cid=f"<{image.cid}>",
            filename=image.filename,
            disposition="inline",
        )
    return message


def sendHtmlEmail(
    to: str,
    subject: str,
    html: str,
    text: str,
    inlineImages: tuple[InlineImage, ...] = (),
    replyTo: str | None = None,
) -> None:
    """Envía un correo HTML con alternativa de texto. Lanza RuntimeError si SMTP no está configurado."""
    if not getSettings().smtpEnabled:
        raise RuntimeError("SMTP no está configurado.")
    _send(buildHtmlMessage(to, subject, html, text, inlineImages, replyTo))


_EMAIL_IN_TEXT = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


def describeSmtpError(error: BaseException) -> str:
    """Causa técnica de un fallo de envío, apta para el log: categoría + clase + respuesta del servidor.

    Nunca incluye la contraseña; las direcciones de correo de la respuesta se ocultan.
    """
    settings = getSettings()
    server = f"{settings.SMTP_HOST}:{settings.SMTP_PORT}"
    if isinstance(error, RuntimeError):
        category = "configuración (faltan SMTP_HOST, SMTP_USERNAME o SMTP_PASSWORD)"
    elif isinstance(error, smtplib.SMTPAuthenticationError):
        category = f"autenticación rechazada por {server} (revisar SMTP_USERNAME / SMTP_PASSWORD o contraseña de aplicación)"
    elif isinstance(error, smtplib.SMTPNotSupportedError) or isinstance(error, ssl.SSLError):
        category = f"TLS/STARTTLS con {server} (revisar SMTP_PORT: 587 usa STARTTLS)"
    elif isinstance(error, smtplib.SMTPRecipientsRefused):
        category = "destinatario rechazado por el servidor"
    elif isinstance(error, smtplib.SMTPSenderRefused):
        category = "remitente rechazado (revisar SMTP_FROM)"
    elif isinstance(error, (TimeoutError, socket.timeout)):
        category = f"timeout conectando a {server}"
    elif isinstance(error, socket.gaierror):
        category = f"host SMTP no encontrado ({settings.SMTP_HOST})"
    elif isinstance(error, ConnectionRefusedError):
        category = f"conexión rechazada en {server} (revisar SMTP_PORT)"
    elif isinstance(error, smtplib.SMTPServerDisconnected):
        category = f"el servidor {server} cerró la conexión"
    elif isinstance(error, smtplib.SMTPException):
        category = "error SMTP"
    else:
        category = "error de red"
    # Detalle solo de fuentes conocidas (respuesta del servidor SMTP o error de red/TLS del sistema): un
    # OSError arbitrario podría traer contenido del correo en su mensaje.
    detail = ""
    code = getattr(error, "smtp_code", None)
    if code is not None:
        message = getattr(error, "smtp_error", b"")
        message = message.decode("utf-8", "replace") if isinstance(message, bytes) else str(message)
        detail = f" [{code} {message[:200]}]"
    elif isinstance(error, smtplib.SMTPRecipientsRefused):
        detail = f" [{', '.join(str(code) for code, _ in error.recipients.values())}]"
    elif isinstance(error, (socket.gaierror, ConnectionError, TimeoutError, ssl.SSLError)) and str(error):
        detail = f" [{str(error)[:200]}]"
    return f"{category}: {type(error).__name__}{_EMAIL_IN_TEXT.sub('***@***', detail)}"


def sendEmail(to: str, subject: str, body: str) -> None:
    """Envía un correo de texto plano. Lanza RuntimeError si SMTP no está configurado."""
    if not getSettings().smtpEnabled:
        raise RuntimeError("SMTP no está configurado.")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = _sender()
    message["To"] = to
    message.set_content(body)
    _send(message)
