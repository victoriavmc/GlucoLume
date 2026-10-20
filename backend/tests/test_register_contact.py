# Pruebas del formulario de contacto.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_register_contact.py -v
#
# Usan el esquema SQLite temporal y el SMTP simulado de test_account_deletion.py.

import json
import logging
import re
from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.exceptions import AuthError
from app.schemas.contact import ContactRequest
from app.services import contact as contactService
from tests.test_account_deletion import (  # noqa: F401 - fixtures
    db,
    engine,
    mails,
    reload,
)

PASSWORD = "Glucolume#Prueba2026"  # nosec B105 - contraseña de prueba


# --- Contacto ------------------------------------------------------------------------------


@pytest.fixture
def contactEnabled(engine, monkeypatch):
    from app.core.config import getSettings

    monkeypatch.setenv("CONTACT_EMAIL", "contacto@glucolume.example")
    monkeypatch.setenv("SMTP_HOST", "smtp.example")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "glucolume@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secreto-smtp")
    getSettings.cache_clear()
    monkeypatch.setattr(contactService, "_limiter", contactService.RateLimiter(5, 900))
    monkeypatch.setattr(contactService, "_confirmationLimiter", contactService.RateLimiter(3, 3600))


def contact(**overrides) -> ContactRequest:
    data = {"nombre": "ana pérez", "email": "ana@example.com", "tipoConsulta": "INSTITUCIONES",
            "asunto": "Uso en un consultorio", "mensaje": "Queremos usar GlucoLume en <b>nuestro</b> consultorio."}
    return ContactRequest(**{**data, **overrides})


def test_contacto_envia_a_la_casilla_configurada_con_reply_to(mails, contactEnabled, caplog):
    with caplog.at_level(logging.INFO):
        assert contactService.sendContactMessage(contact(), "10.0.0.1") is True

    mail, confirmation = mails
    assert mail["to"] == "contacto@glucolume.example"
    assert mail["replyTo"] == "ana@example.com"
    assert mail["subject"] == "Nueva consulta desde GlucoLume"
    for text in ("Ana Pérez", "ana@example.com", "Instituciones", "Uso en un consultorio", "Fecha/hora"):
        assert text in mail["html"]
    # Contenido escapado: el mensaje no puede inyectar HTML.
    assert "&lt;b&gt;nuestro&lt;/b&gt;" in mail["html"] and "<b>nuestro</b>" not in mail["html"]
    # Log técnico: sin el correo del remitente ni el mensaje.
    assert "ana@example.com" not in caplog.text and "consultorio" not in caplog.text

    # Confirmación: al remitente, después de la consulta, sin Reply-To y sin el mensaje.
    assert confirmation["to"] == "ana@example.com" and confirmation["replyTo"] is None
    assert confirmation["subject"] == "Recibimos tu consulta - GlucoLume"
    for text in ("Hola Ana Pérez", "Recibimos correctamente tu consulta", "Instituciones", "Uso en un consultorio",
                 "No es necesario volver a enviar la consulta"):
        assert text in confirmation["html"]
    assert "nuestro" not in confirmation["html"], "La confirmación no repite el mensaje de la consulta."


def test_confirmacion_escapa_el_contenido_del_usuario(mails, contactEnabled):
    contactService.sendContactMessage(
        contact(nombre="Ana", asunto='<a href="http://phishing.example">Hacé clic</a>'), "10.0.0.1"
    )
    confirmation = mails[1]
    assert '<a href="http://phishing.example">' not in confirmation["html"]
    assert "&lt;a href=&#34;http://phishing.example&#34;&gt;" in confirmation["html"]


def test_confirmacion_from_es_la_cuenta_smtp(contactEnabled):
    from app.emails.eventTypes import EmailEventType
    from app.services import email as emailService

    message = emailService.buildEmailMessage(
        EmailEventType.CONTACTO_CONFIRMACION, "ana@example.com",
        {"nombre": "Ana", "tipoConsulta": "Otro", "asuntoConsulta": "Hola"},
    )
    assert "glucolume@example.com" in message["From"] and message["To"] == "ana@example.com"
    assert message["Reply-To"] is None


def test_falla_la_consulta_interna_503_y_sin_confirmacion(mails, contactEnabled, monkeypatch):
    from app.integrations.email import sender

    def internalDown(recipient, *args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(sender, "sendHtmlEmail", internalDown)
    with pytest.raises(AuthError) as error:
        contactService.sendContactMessage(contact(), "10.0.0.1")
    assert error.value.code == "CORREO_NO_ENVIADO"
    assert not mails, "Sin consulta recibida no se confirma nada."


def test_falla_solo_la_confirmacion_respuesta_exitosa_sin_duplicar(mails, contactEnabled, monkeypatch, caplog):
    from app.integrations.email import sender

    delivered = []
    original = sender.sendHtmlEmail

    def confirmationDown(recipient, *args, **kwargs):
        if recipient == "ana@example.com":
            raise __import__("smtplib").SMTPRecipientsRefused({recipient: (550, b"mailbox unavailable")})
        delivered.append(recipient)
        return original(recipient, *args, **kwargs)

    monkeypatch.setattr(sender, "sendHtmlEmail", confirmationDown)
    with caplog.at_level(logging.WARNING):
        assert contactService.sendContactMessage(contact(), "10.0.0.1") is False

    assert delivered == ["contacto@glucolume.example"], "La consulta interna se envía una sola vez."
    assert [mail["to"] for mail in mails] == ["contacto@glucolume.example"]
    assert "No fue posible enviar la confirmación automática al remitente" in caplog.text
    assert "ana@example.com" not in caplog.text


def test_confirmacion_que_lanza_una_excepcion_inesperada_no_afecta_la_consulta(mails, contactEnabled, monkeypatch, caplog):
    from app.services import email as emailService

    original = emailService.sendEmailEvent

    def explodeOnConfirmation(eventType, *args, **kwargs):
        if eventType == "CONTACTO_CONFIRMACION":
            raise ValueError("plantilla rota")
        return original(eventType, *args, **kwargs)

    monkeypatch.setattr(contactService.emailService, "sendEmailEvent", explodeOnConfirmation)
    with caplog.at_level(logging.ERROR):
        assert contactService.sendContactMessage(contact(), "10.0.0.1") is False
    assert len(mails) == 1 and "No fue posible enviar la confirmación" in caplog.text


def test_mensaje_from_es_la_cuenta_smtp_y_reply_to_el_usuario(contactEnabled):
    from app.emails.eventTypes import EmailEventType
    from app.services import email as emailService

    message = emailService.buildEmailMessage(
        EmailEventType.CONTACTO_RECIBIDO, "contacto@glucolume.example",
        {"fechaEvento": datetime_now(), "nombreRemitente": "Ana", "correoRemitente": "ana@example.com",
         "tipoConsulta": "Otro", "asuntoConsulta": "Hola", "mensaje": "Mensaje de prueba."},
        replyTo="ana@example.com",
    )
    assert "glucolume@example.com" in message["From"] and "ana@example.com" not in message["From"]
    assert message["To"] == "contacto@glucolume.example"
    assert message["Reply-To"] == "ana@example.com"


def datetime_now():
    from app.utils.timeZone import nowForDb

    return nowForDb()


def test_contacto_no_disponible_sin_casilla(mails, engine, monkeypatch, caplog):
    from app.core.config import getSettings

    # Independiente del .env real: sin casilla configurada.
    settings = getSettings().model_copy(update={"CONTACT_EMAIL": None})
    monkeypatch.setattr(contactService, "getSettings", lambda: settings)
    with caplog.at_level(logging.ERROR), pytest.raises(AuthError) as error:
        contactService.sendContactMessage(contact(), "10.0.0.1")
    assert error.value.code == "CONTACTO_NO_DISPONIBLE"
    assert error.value.message == "El formulario de contacto no está disponible en este momento."
    assert "falta CONTACT_EMAIL" in caplog.text and not mails


def test_contacto_descarta_envios_automatizados(mails, contactEnabled):
    contactService.sendContactMessage(contact(sitioWeb="http://spam.example"), "10.0.0.1")
    assert not mails, "Ni consulta ni confirmación para envíos automatizados."


def test_contacto_limita_envios_por_ip_y_confirmaciones_por_destinatario(mails, contactEnabled):
    results = [contactService.sendContactMessage(contact(), "10.0.0.1") for _ in range(5)]
    with pytest.raises(AuthError) as error:
        contactService.sendContactMessage(contact(), "10.0.0.1")
    assert error.value.code == "DEMASIADAS_SOLICITUDES"
    results.append(contactService.sendContactMessage(contact(), "10.0.0.2"))

    internal = [mail for mail in mails if mail["to"] == "contacto@glucolume.example"]
    confirmations = [mail for mail in mails if mail["to"] == "ana@example.com"]
    assert len(internal) == 6, "Todas las consultas aceptadas llegan a GlucoLume."
    assert len(confirmations) == 3, "Máximo 3 confirmaciones por hora a una misma dirección."
    assert results == [True, True, True, False, False, False]


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (lambda: __import__("smtplib").SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted"),
         "autenticación rechazada"),
        (lambda: TimeoutError("timed out"), "timeout"),
        (lambda: __import__("socket").gaierror(11001, "getaddrinfo failed"), "host SMTP no encontrado"),
        (lambda: ConnectionRefusedError(10061, "refused"), "conexión rechazada"),
        (lambda: __import__("ssl").SSLError("wrong version number"), "TLS/STARTTLS"),
        (lambda: __import__("smtplib").SMTPRecipientsRefused({"x@y.com": (550, b"no such user x@y.com")}),
         "destinatario rechazado"),
    ],
)
def test_fallo_smtp_503_controlado_y_causa_en_el_log(mails, contactEnabled, monkeypatch, caplog, failure, expected):
    from app.api.errors import AUTH_ERROR_STATUS
    from app.integrations.email import sender

    def down(*args, **kwargs):
        raise failure()

    monkeypatch.setattr(sender, "sendHtmlEmail", down)
    with caplog.at_level(logging.WARNING), pytest.raises(AuthError) as error:
        contactService.sendContactMessage(contact(), "10.0.0.1")
    assert error.value.code == "CORREO_NO_ENVIADO" and AUTH_ERROR_STATUS[error.value.code] == 503
    assert error.value.message == "El formulario de contacto no está disponible en este momento."
    assert expected in caplog.text
    assert "secreto-smtp" not in caplog.text and "ana@example.com" not in caplog.text
    assert "x@y.com" not in caplog.text


@pytest.mark.parametrize(
    "overrides",
    [
        {"mensaje": "corto"},
        {"email": "no-es-correo"},
        {"tipoConsulta": "VENTAS"},
        {"nombre": "A"},
        {"asunto": ""},
        {"asunto": "x" * 151},
        {"mensaje": "x" * 2001},
    ],
)
def test_contacto_valida_datos_422(overrides):
    with pytest.raises(ValidationError):
        contact(**overrides)


def test_contacto_rechaza_campos_con_nombres_viejos():
    with pytest.raises(ValidationError):
        ContactRequest(nombre="Ana", correoElectronico="ana@example.com", motivo="OTRO", asunto="Hola",
                       mensaje="Mensaje de prueba largo.")


def test_asunto_en_una_sola_linea():
    assert contact(asunto="  Hola\r\nBcc: x@y.com  ").asunto == "Hola Bcc: x@y.com"


def test_ventana_del_limitador():
    limiter = contactService.RateLimiter(2, 60)
    assert limiter.allow("ip", 0) and limiter.allow("ip", 1)
    assert not limiter.allow("ip", 2)
    assert limiter.allow("ip", 61)
