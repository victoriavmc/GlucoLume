# Email - Servicio central de correos de GlucoLume
#
# La lógica de negocio solo indica el evento, el destinatario y los datos; este servicio:
#   1. identifica plantilla y asunto (app/emails/eventTypes.py);
#   2. valida destinatario, variables requeridas y URLs de acción;
#   3. renderiza la plantilla Jinja (HTML + texto plano);
#   4. adjunta bannerCorreoGlucoLume como imagen embebida (cid:bannerCorreoGlucoLume);
#   5. envía por SMTP y registra solo información técnica no sensible.
#
# Nunca se registran en logs el contexto del correo, tokens, códigos OTP ni contraseñas.

import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import EmailStr, TypeAdapter, ValidationError

from app.core.config import getSettings
from app.emails.eventTypes import EMAIL_EVENTS, MEASUREMENT_DETAIL_KEYS, MEASUREMENT_EVENTS, EmailEventType
from app.emails.formatting import maskEmail
from app.emails.renderer import BANNER_CID, EMAILS_DIR, RenderedEmail, renderEmail
from app.integrations.email import sender
from app.integrations.email.sender import InlineImage
from app.utils.normalizers import normalizeEmail

logger = logging.getLogger(__name__)

BANNER_NAME = "bannerCorreoGlucoLume"
_IMAGE_SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": "png",
    b"\xff\xd8\xff": "jpeg",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
}
# Nombres de variables que nunca deben llegar a una plantilla.
FORBIDDEN_CONTEXT_KEYS = frozenset(
    {"password", "contrasena", "passwordHash", "token", "tokenHash", "refreshToken", "accessToken",
     "refreshTokenHash", "secreto", "secretoCifrado", "secretoTotp", "codigoRecuperacion"}
)

# Rutas del frontend a las que apuntan los botones (las implementa el frontend).
FRONTEND_ROUTES = {
    "ingreso": "/login",
    "seguridad": "/cuenta/seguridad",
    # Pantalla que confirma la eliminación con POST /api/v1/auth/account-deletion/confirm.
    "eliminarCuenta": "/cuenta/eliminar/confirmar",
    # Pantalla que desactiva el aviso con POST /api/v1/auth/notifications/new-login/unsubscribe.
    "desuscribirInicioSesion": "/cuenta/notificaciones/desuscribir",
    # Destino del callback de Google: canjea el código con POST /api/v1/auth/google/exchange.
    "googleCallback": "/auth/google/callback",
    # Pantalla que verifica el correo con GET /api/v1/auth/verify-email?token=...
    "verificarCorreo": "/verificar-correo",
    # Invitaciones institucionales: se aceptan o rechazan con la sesión de la cuenta invitada.
    "invitacionesInstitucion": "/app/instituciones",
    # Grupo familiar: invitaciones recibidas y panel del grupo (se responden con la sesión de la cuenta invitada).
    "grupoFamiliar": "/app/grupo",
    # Activación de una cuenta creada por una invitación institucional (POST /api/v1/auth/account-activation/*).
    "activarCuenta": "/activar-cuenta",
    # Administración de la plataforma: activar la cuenta administrativa, restablecer la contraseña y ver la transferencia.
    # Recuperación de contraseña de las cuentas comunes (POST /api/v1/auth/password/reset).
    "restablecerPassword": "/restablecer-contrasena",
    "plataformaActivar": "/administracion/activar",  # ruta principal de la activación administrativa (la anterior /plataforma/activar la redirige)
    "plataformaLogin": "/plataforma/login",
    "plataformaRestablecer": "/plataforma/restablecer",
    "plataformaTransferencia": "/plataforma/transferencia",
}

_emailAdapter = TypeAdapter(EmailStr)
# Envíos en segundo plano para avisos que no deben demorar la respuesta (p. ej. inicio de sesión).
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="glucolume-email")


class EmailContextError(ValueError):
    """Datos inválidos para un correo (error de programación del llamador)."""


def frontendUrl(route: str) -> str:
    return getSettings().FRONTEND_URL.rstrip("/") + FRONTEND_ROUTES.get(route, route)


def apiUrl(path: str) -> str:
    return getSettings().API_BASE_URL.rstrip("/") + path


@lru_cache
def loadBanner() -> InlineImage:
    """Busca bannerCorreoGlucoLume.* en app/emails y detecta su formato real por la firma del archivo."""
    for path in sorted(Path(EMAILS_DIR).glob(f"{BANNER_NAME}.*")):
        content = path.read_bytes()
        for signature, subtype in _IMAGE_SIGNATURES.items():
            if content.startswith(signature):
                return InlineImage(cid=BANNER_CID, content=content, subtype=subtype, filename=path.name)
    raise FileNotFoundError(f"No se encontró una imagen válida {BANNER_NAME}.* en {EMAILS_DIR}.")


def _allowedOrigins() -> set[str]:
    settings = getSettings()
    return {
        "{0.scheme}://{0.netloc}".format(urlsplit(url)) for url in (settings.FRONTEND_URL, settings.API_BASE_URL)
    }


def _validate(eventType: EmailEventType, destinatario: str, context: dict) -> str:
    if eventType not in EMAIL_EVENTS:
        raise EmailContextError(f"Evento de correo desconocido: {eventType}")
    try:
        recipient = _emailAdapter.validate_python(normalizeEmail(destinatario))
    except (ValidationError, ValueError, TypeError) as error:
        raise EmailContextError("Destinatario de correo inválido.") from error

    spec = EMAIL_EVENTS[eventType]
    forbidden = FORBIDDEN_CONTEXT_KEYS & set(context)
    if forbidden:
        raise EmailContextError(f"Variables no permitidas en un correo: {sorted(forbidden)}")
    missing = [key for key in spec.requiredContext if context.get(key) is None]
    if missing:
        raise EmailContextError(f"Faltan variables para {eventType}: {missing}")
    origins = _allowedOrigins()
    for key in spec.actionUrls:
        if context.get(key) is None:
            continue  # las obligatorias ya se verificaron arriba; una URL opcional ausente no se valida
        url = urlsplit(str(context[key]))
        if url.scheme not in ("http", "https") or f"{url.scheme}://{url.netloc}" not in origins:
            raise EmailContextError(f"La URL de acción {key} no pertenece a GlucoLume.")
    return recipient


def _prepareContext(eventType: EmailEventType, context: dict, incluirDetalleMedicion: bool) -> dict:
    prepared = {key: value for key, value in context.items() if value is not None}
    if eventType in MEASUREMENT_EVENTS:
        # Los datos de una medición solo se incluyen con autorización explícita del destinatario.
        if not incluirDetalleMedicion:
            for key in MEASUREMENT_DETAIL_KEYS:
                prepared.pop(key, None)
        prepared["mostrarDetalle"] = incluirDetalleMedicion and any(key in prepared for key in MEASUREMENT_DETAIL_KEYS)
    return prepared


def renderEmailEvent(
    eventType: EmailEventType, destinatario: str, context: dict, *, incluirDetalleMedicion: bool = False
) -> tuple[str, RenderedEmail]:
    """Valida y renderiza sin enviar. Devuelve (destinatario normalizado, correo renderizado)."""
    recipient = _validate(eventType, destinatario, context)
    return recipient, renderEmail(eventType, _prepareContext(eventType, context, incluirDetalleMedicion))


def _validReplyTo(replyTo: str | None) -> str | None:
    if replyTo is None:
        return None
    try:
        return _emailAdapter.validate_python(normalizeEmail(replyTo))
    except (ValidationError, ValueError, TypeError) as error:
        raise EmailContextError("Dirección de respuesta (Reply-To) inválida.") from error


def buildEmailMessage(
    eventType: EmailEventType,
    destinatario: str,
    context: dict,
    *,
    incluirDetalleMedicion: bool = False,
    replyTo: str | None = None,
):
    """Construye el EmailMessage completo (HTML + texto + banner embebido) sin enviarlo."""
    recipient, rendered = renderEmailEvent(eventType, destinatario, context, incluirDetalleMedicion=incluirDetalleMedicion)
    return sender.buildHtmlMessage(
        recipient, rendered.subject, rendered.html, rendered.text, (loadBanner(),), _validReplyTo(replyTo)
    )


def sendEmailEvent(
    eventType: EmailEventType,
    destinatario: str,
    context: dict,
    *,
    incluirDetalleMedicion: bool = False,
    replyTo: str | None = None,
) -> bool:
    """Envía el correo del evento. Devuelve True si se envió.

    Un error de datos (EmailContextError) se propaga porque es un error de programación; un fallo de
    envío (SMTP, red) se registra con su causa técnica y devuelve False para que el flujo de negocio
    decida qué hacer.
    """
    recipient, rendered = renderEmailEvent(eventType, destinatario, context, incluirDetalleMedicion=incluirDetalleMedicion)
    try:
        sender.sendHtmlEmail(
            recipient, rendered.subject, rendered.html, rendered.text, (loadBanner(),), _validReplyTo(replyTo)
        )
    except (OSError, RuntimeError) as error:
        # OSError cubre smtplib.SMTPException, SSL y red; RuntimeError, SMTP sin configurar.
        logger.warning(
            "No se pudo enviar el correo %s a %s. Causa: %s",
            eventType, maskEmail(recipient), sender.describeSmtpError(error),
        )
        return False
    logger.info("Correo %s enviado a %s.", eventType, maskEmail(recipient))
    return True


def _sendSafely(eventType: EmailEventType, destinatario: str, context: dict, incluirDetalleMedicion: bool) -> None:
    try:
        sendEmailEvent(eventType, destinatario, context, incluirDetalleMedicion=incluirDetalleMedicion)
    except Exception as error:  # noqa: BLE001 - un aviso en segundo plano nunca debe terminar el hilo
        logger.error("Correo %s no generado (%s).", eventType, type(error).__name__)


def sendEmailEventInBackground(
    eventType: EmailEventType, destinatario: str | None, context: dict, *, incluirDetalleMedicion: bool = False
) -> None:
    """Envía un aviso sin bloquear la respuesta HTTP. Si no hay destinatario, no hace nada."""
    if not destinatario:
        return
    _executor.submit(_sendSafely, eventType, destinatario, dict(context), incluirDetalleMedicion)


def runInBackground(task, *args) -> None:
    """Ejecuta `task(*args)` en el mismo hilo auxiliar de los avisos, sin bloquear la respuesta HTTP.

    Para quien necesita el resultado del envío (p. ej. registrar si el correo salió): `task` llama a sendEmailEvent y anota el resultado.
    """
    _executor.submit(task, *args)
