# Contact - Consultas del formulario público de la landing
#
# Reutiliza el servicio central de correos (app/services/email.py: sendEmailEvent), con dos envíos separados:
#   1. CONTACTO_RECIBIDO (principal): From la cuenta SMTP de GlucoLume, To CONTACT_EMAIL, Reply-To el correo de
#      la persona. Si falla, la consulta no llegó: 503.
#   2. CONTACTO_CONFIRMACION (secundario): From la cuenta SMTP de GlucoLume, To el correo de la persona. Si falla,
#      la consulta ya llegó: se registra en el log y la respuesta sigue siendo exitosa. Nunca reenvía el 1.
# El From nunca es el correo ingresado (SPF/DMARC). No se guarda nada en la base. El log técnico registra la
# causa real de un fallo, nunca el mensaje ni el correo completo del remitente.

import logging

from app.core.config import getSettings
from app.core.exceptions import AuthError
from app.emails.formatting import maskEmail
from app.emails.eventTypes import EmailEventType
from app.schemas.contact import TIPO_CONSULTA_LABELS, ContactRequest
from app.services import email as emailService
from app.services.rateLimiter import RateLimiter  # noqa: F401 - se reexporta: otros módulos y pruebas lo importan desde acá
from app.utils.timeZone import nowForDb

logger = logging.getLogger(__name__)

# Límite por IP: protege la casilla de destino y el SMTP de envíos masivos.
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW_SECONDS = 15 * 60
# Límite de confirmaciones por dirección: el formulario no debe servir para enviar correos en masa a un
# tercero. Superado, la consulta se recibe igual y solo se omite la confirmación.
CONFIRMATION_LIMIT_MAX = 3
CONFIRMATION_LIMIT_WINDOW_SECONDS = 60 * 60

UNAVAILABLE_MESSAGE = "El formulario de contacto no está disponible en este momento."


_limiter = RateLimiter(RATE_LIMIT_MAX, RATE_LIMIT_WINDOW_SECONDS, name="contacto:ip")
_confirmationLimiter = RateLimiter(CONFIRMATION_LIMIT_MAX, CONFIRMATION_LIMIT_WINDOW_SECONDS, name="contacto:confirmacion")


def _sendConfirmation(data: ContactRequest, tipoConsulta: str) -> bool:
    """Confirmación automática al remitente. Nunca lanza: un fallo se registra y no afecta a la consulta."""
    if not _confirmationLimiter.allow(data.email.lower()):
        logger.warning("Confirmación de contacto omitida: límite de confirmaciones para %s.", maskEmail(data.email))
        return False
    try:
        sent = emailService.sendEmailEvent(
            EmailEventType.CONTACTO_CONFIRMACION,
            data.email,
            {"nombre": data.nombre, "tipoConsulta": tipoConsulta, "asuntoConsulta": data.asunto},
        )
    except Exception:  # noqa: BLE001 - la consulta ya fue recibida: este envío nunca debe fallar el request
        logger.exception("No fue posible enviar la confirmación automática al remitente %s.", maskEmail(data.email))
        return False
    if not sent:
        # La causa técnica (credenciales, host, TLS, destinatario...) ya quedó en el log del servicio de email.
        logger.warning("No fue posible enviar la confirmación automática al remitente %s.", maskEmail(data.email))
    return sent


def sendContactMessage(data: ContactRequest, clientIp: str | None) -> bool:
    """Envía la consulta a CONTACT_EMAIL y luego la confirmación al remitente.

    Devuelve si se envió la confirmación. Lanza AuthError (503) solo si falla el envío principal.
    Un envío automatizado (honeypot) se descarta en silencio.
    """
    if data.sitioWeb.strip():
        return True
    settings = getSettings()
    recipient = settings.CONTACT_EMAIL
    if not recipient:
        logger.error("Formulario de contacto: falta CONTACT_EMAIL en el .env (casilla que recibe las consultas).")
        raise AuthError("CONTACTO_NO_DISPONIBLE", UNAVAILABLE_MESSAGE)
    if not settings.smtpEnabled:
        logger.error("Formulario de contacto: SMTP sin configurar (SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD).")
        raise AuthError("CONTACTO_NO_DISPONIBLE", UNAVAILABLE_MESSAGE)
    if not _limiter.allow(clientIp or "desconocido"):
        raise AuthError("DEMASIADAS_SOLICITUDES", "Enviaste varias consultas seguidas. Probá de nuevo en unos minutos.")
    tipoConsulta = TIPO_CONSULTA_LABELS[data.tipoConsulta]
    sent = emailService.sendEmailEvent(
        EmailEventType.CONTACTO_RECIBIDO,
        recipient,
        {
            "fechaEvento": nowForDb(),
            "nombreRemitente": data.nombre,
            "correoRemitente": data.email,
            "tipoConsulta": tipoConsulta,
            # "asunto" es una variable reservada de las plantillas (asunto del correo).
            "asuntoConsulta": data.asunto,
            "mensaje": data.mensaje,
        },
        replyTo=data.email,
    )
    if not sent:
        # La causa técnica (credenciales, host, puerto, TLS, timeout...) ya quedó en el log de email.
        raise AuthError("CORREO_NO_ENVIADO", UNAVAILABLE_MESSAGE)
    # A partir de acá la consulta ya llegó: la confirmación es independiente y nunca reenvía la consulta.
    return _sendConfirmation(data, tipoConsulta)
