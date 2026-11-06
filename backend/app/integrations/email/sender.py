# EmailSender - Envío de correo por SMTP con STARTTLS
#
# Transporte únicamente: no arma contenidos. El HTML de los eventos lo construye
# app/services/email.py a partir de las plantillas de app/emails.

import re
import smtplib
import socket
import ssl
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Self

from app.core.config import getSettings

# Timeout por operación de socket (conexión, cada comando SMTP).
SMTP_TIMEOUT_SECONDS = 20
# Tiempo total de un envío desde STARTTLS hasta DATA. Un servidor que responde de a poco no puede retener la conexión más allá de
# este límite, aunque cada operación esté dentro de su timeout. El saludo inicial se rige por SMTP_TIMEOUT_SECONDS (ver _connect).
SMTP_TOTAL_TIMEOUT_SECONDS = 30
# Conexiones SMTP abiertas a la vez. Cada envío sincrónico ocupa un hilo de la API mientras dura; el límite evita que un servidor
# lento agote el threadpool y deje sin responder a endpoints que no envían correo.
SMTP_MAX_CONCURRENT = 4
# Espera máxima por un lugar libre. Pasado este tiempo el envío falla como cualquier otro fallo SMTP (mismo mensaje al usuario).
SMTP_SLOT_WAIT_SECONDS = 10

_slots = threading.BoundedSemaphore(SMTP_MAX_CONCURRENT)


class SmtpBusyError(RuntimeError):
    """No hubo lugar entre las conexiones SMTP simultáneas dentro de SMTP_SLOT_WAIT_SECONDS."""


class SmtpDeadlineError(TimeoutError):
    """El envío superó SMTP_TOTAL_TIMEOUT_SECONDS."""


@contextmanager
def _slot() -> Iterator[None]:
    if not _slots.acquire(timeout=SMTP_SLOT_WAIT_SECONDS):
        raise SmtpBusyError(f"Hay {SMTP_MAX_CONCURRENT} envíos SMTP en curso.")
    try:
        yield
    finally:
        _slots.release()


class _Deadline:
    """Tiempo total de un envío. Al vencer, cierra el socket desde un hilo auxiliar: las lecturas bloqueadas despiertan con error y
    la operación en curso falla. Si el vencimiento ocurre antes de que exista el socket, `attach` lo corta en cuanto se crea."""

    def __init__(self, seconds: float) -> None:
        self._expired = threading.Event()
        self._server: smtplib.SMTP | None = None
        self._timer = threading.Timer(seconds, self._expire)
        self._timer.daemon = True

    def __enter__(self) -> Self:
        self._timer.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self._timer.cancel()

    def attach(self, server: smtplib.SMTP) -> None:
        self._server = server
        if self._expired.is_set():
            self._abort()

    def check(self) -> None:
        if self._expired.is_set():
            raise SmtpDeadlineError(f"El envío superó {SMTP_TOTAL_TIMEOUT_SECONDS} s.")

    def raiseIfExpired(self, error: BaseException) -> None:
        """Ante un fallo con el plazo vencido, lanza SmtpDeadlineError (la causa real) en lugar del error genérico del socket cerrado."""
        if self._expired.is_set() and not isinstance(error, SmtpDeadlineError):
            raise SmtpDeadlineError(f"El envío superó {SMTP_TOTAL_TIMEOUT_SECONDS} s.") from error

    def _expire(self) -> None:
        self._expired.set()
        self._abort()

    def _abort(self) -> None:
        sock = getattr(self._server, "sock", None)
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass  # ya cerrado: la operación en curso falla igual


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


def _secure(server: smtplib.SMTP) -> None:
    """STARTTLS verificado y autenticación con la cuenta SMTP de GlucoLume."""
    settings = getSettings()
    server.starttls(context=tlsContext())
    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD.get_secret_value())


class SmtpSession:
    """Conexión SMTP (TCP + STARTTLS + AUTH) que se reutiliza para varios correos seguidos del mismo flujo.

    Se abre con el primer envío. Ante CUALQUIER fallo se descarta la conexión: el envío siguiente abre otra, así que
    cada correo fallido o exitoso se comporta igual que con una conexión propia (no se reintenta ningún envío).
    Quien la usa debe cerrarla con close() (o con `with`), que termina con QUIT.
    """

    def __init__(self) -> None:
        self._server: smtplib.SMTP | None = None

    def send(self, message: EmailMessage) -> None:
        with _slot(), _Deadline(SMTP_TOTAL_TIMEOUT_SECONDS) as deadline:
            try:
                if self._server is None:
                    self._server = _connect(deadline)
                _deliver(self._server, message, deadline)
            except BaseException:
                self._discard()
                raise

    def _discard(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            server.close()

    def close(self) -> None:
        server, self._server = self._server, None
        if server is None:
            return
        try:
            server.quit()
        except Exception:  # noqa: BLE001 - cerrar nunca debe ocultar el resultado de los envíos
            server.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def _connect(deadline: _Deadline) -> smtplib.SMTP:
    """Conexión TCP + saludo + STARTTLS + AUTH. Ante un fallo la conexión se cierra.

    El saludo inicial lo lee el propio constructor de smtplib, antes de que exista un socket que el plazo pueda cortar: ese tramo
    se rige por SMTP_TIMEOUT_SECONDS. Desde STARTTLS en adelante, el plazo total corta cualquier espera."""
    settings = getSettings()
    server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS)
    try:
        deadline.attach(server)
        deadline.check()
        _secure(server)
        deadline.check()
    except BaseException as error:
        server.close()
        deadline.raiseIfExpired(error)
        raise
    return server


def _deliver(server: smtplib.SMTP, message: EmailMessage, deadline: _Deadline) -> None:
    try:
        server.send_message(message)
    except BaseException as error:
        deadline.raiseIfExpired(error)
        raise


def _send(message: EmailMessage) -> None:
    with _slot(), _Deadline(SMTP_TOTAL_TIMEOUT_SECONDS) as deadline:
        with _connect(deadline) as server:
            _deliver(server, message, deadline)


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
    *,
    session: SmtpSession | None = None,
) -> None:
    """Envía un correo HTML con alternativa de texto. Lanza RuntimeError si SMTP no está configurado.

    `session`: envía por una conexión ya abierta (varios correos del mismo flujo). Sin ella, abre y cierra una conexión propia.
    """
    if not getSettings().smtpEnabled:
        raise RuntimeError("SMTP no está configurado.")
    message = buildHtmlMessage(to, subject, html, text, inlineImages, replyTo)
    if session is None:
        _send(message)
    else:
        session.send(message)


_EMAIL_IN_TEXT = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


def describeSmtpError(error: BaseException) -> str:
    """Causa técnica de un fallo de envío, apta para el log: categoría + clase + respuesta del servidor.

    Nunca incluye la contraseña; las direcciones de correo de la respuesta se ocultan.
    """
    settings = getSettings()
    server = f"{settings.SMTP_HOST}:{settings.SMTP_PORT}"
    if isinstance(error, SmtpBusyError):
        category = f"demasiados envíos SMTP en curso (límite {SMTP_MAX_CONCURRENT}); el servidor puede estar lento"
    elif isinstance(error, SmtpDeadlineError):
        category = f"tiempo total del envío agotado con {server} (más de {SMTP_TOTAL_TIMEOUT_SECONDS} s)"
    elif isinstance(error, RuntimeError):
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
