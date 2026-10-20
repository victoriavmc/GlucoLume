# Pruebas del módulo de correos:
# - catálogo de eventos
# - renderizado de plantillas
# - validaciones de seguridad
# - banner embebido por CID
# - servicio de envío simulado
# - previsualizaciones
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_emails.py -v
#
# Estas pruebas:
# - NO leen el .env real
# - NO envían correos reales
# - NO requieren base de datos

import logging
import re
from pathlib import Path

import pytest

from app.emails.eventTypes import EMAIL_EVENTS, MEASUREMENT_EVENTS, EmailEventType
from app.emails.renderer import BANNER_CID, TEMPLATES_DIR
from app.integrations.email import sender
from app.services import email as emailService
from tests.email_preview import render as preview
from tests.email_preview.sampleData import SAMPLE_RECIPIENT, sampleContexts


CONTEXTS = sampleContexts()
ALL_EVENTS = list(EmailEventType)


def test_catalogo_completo():
    assert set(EMAIL_EVENTS) == set(EmailEventType)
    assert set(CONTEXTS) == set(EmailEventType)

    for event, spec in EMAIL_EVENTS.items():
        assert (TEMPLATES_DIR / spec.template).is_file(), event
        assert spec.subject.strip(), event


@pytest.mark.parametrize("event", ALL_EVENTS, ids=str)
def test_renderiza_sin_variables_pendientes(event):
    recipient, rendered = emailService.renderEmailEvent(
        event,
        SAMPLE_RECIPIENT,
        CONTEXTS[event],
    )

    spec = EMAIL_EVENTS[event]

    assert recipient == SAMPLE_RECIPIENT
    assert rendered.subject == spec.subject

    for leftover in ("{{", "}}", "{%", "%}", "{#"):
        assert leftover not in rendered.html, f"{event}: quedó {leftover} en HTML"
        assert leftover not in rendered.text, f"{event}: quedó {leftover} en texto"

    assert f'src="cid:{BANNER_CID}"' in rendered.html

    assert (
        "Este es un mensaje automático enviado por GlucoLume."
        in rendered.html
    )

    assert "Por favor, no respondas a este correo." in rendered.text
    assert rendered.text.strip()

    for key in spec.actionUrls:
        url = CONTEXTS[event][key]

        assert url in rendered.html, f"{event}: falta {key} en HTML"
        assert url in rendered.text, f"{event}: falta {key} en texto"

    assert (
        "prototipo tecnológico de monitoreo experimental" in rendered.html
    ) == spec.clinicalDisclaimer

    assert (
        "Si no reconocés esta actividad" in rendered.html
    ) == spec.securityNotice


@pytest.mark.parametrize("event", ALL_EVENTS, ids=str)
def test_banner_adjunto_como_cid(event):
    message = emailService.buildEmailMessage(
        event,
        SAMPLE_RECIPIENT,
        CONTEXTS[event],
    )

    assert message["To"] == SAMPLE_RECIPIENT
    assert message["Subject"] == EMAIL_EVENTS[event].subject

    types = [part.get_content_type() for part in message.walk()]

    assert "text/plain" in types
    assert "text/html" in types

    images = [
        part
        for part in message.walk()
        if part.get_content_maintype() == "image"
    ]

    assert len(images) == 1

    image = images[0]
    banner = emailService.loadBanner()

    assert image["Content-ID"] == f"<{BANNER_CID}>"
    assert image.get_content_disposition() == "inline"
    assert image.get_content_type() == f"image/{banner.subtype}"
    assert image.get_payload(decode=True) == banner.content


def test_banner_detecta_extension_real():
    banner = emailService.loadBanner()
    path = Path(emailService.EMAILS_DIR) / banner.filename

    assert path.stem == "bannerCorreoGlucoLume"
    assert path.is_file()
    assert banner.subtype in ("png", "jpeg", "gif")


def test_faltan_variables_requeridas():
    context = dict(CONTEXTS[EmailEventType.PASSWORD_CAMBIADA])
    del context["urlSeguridad"]

    with pytest.raises(emailService.EmailContextError):
        emailService.renderEmailEvent(
            EmailEventType.PASSWORD_CAMBIADA,
            SAMPLE_RECIPIENT,
            context,
        )


@pytest.mark.parametrize(
    "invalid",
    [
        "",
        "sin-arroba",
        "a b@example.com",
        None,
    ],
)
def test_destinatario_obligatorio_y_valido(invalid):
    with pytest.raises(emailService.EmailContextError):
        emailService.renderEmailEvent(
            EmailEventType.MFA_DESACTIVADO,
            invalid,
            CONTEXTS[EmailEventType.MFA_DESACTIVADO],
        )


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "contrasena",
        "token",
        "refreshToken",
        "secretoTotp",
    ],
)
def test_no_se_aceptan_secretos_en_el_contexto(key):
    context = {
        **CONTEXTS[EmailEventType.PASSWORD_CAMBIADA],
        key: "Secreta123!",
    }

    with pytest.raises(emailService.EmailContextError):
        emailService.renderEmailEvent(
            EmailEventType.PASSWORD_CAMBIADA,
            SAMPLE_RECIPIENT,
            context,
        )


def test_no_se_expone_password_en_correos_de_contrasena():
    eventos = (
        EmailEventType.PASSWORD_CAMBIADA,
        EmailEventType.RECUPERACION_PASSWORD,
    )

    for event in eventos:
        _, rendered = emailService.renderEmailEvent(
            event,
            SAMPLE_RECIPIENT,
            CONTEXTS[event],
        )

        assert not re.search(
            r"contraseña\s*(nueva|anterior)?\s*:",
            rendered.text,
            re.IGNORECASE,
        )


def test_urls_de_accion_solo_de_glucolume():
    context = {
        **CONTEXTS[EmailEventType.RECUPERACION_PASSWORD],
        "urlRestablecer": "https://phishing.example.com/reset",
    }

    with pytest.raises(emailService.EmailContextError):
        emailService.renderEmailEvent(
            EmailEventType.RECUPERACION_PASSWORD,
            SAMPLE_RECIPIENT,
            context,
        )

    context["urlRestablecer"] = "javascript:alert(1)"

    with pytest.raises(emailService.EmailContextError):
        emailService.renderEmailEvent(
            EmailEventType.RECUPERACION_PASSWORD,
            SAMPLE_RECIPIENT,
            context,
        )


def test_autoescape_html():
    context = {
        **CONTEXTS[EmailEventType.MIEMBRO_AGREGADO],
        "nombreIntegrante": "<script>alert(1)</script>",
    }

    _, rendered = emailService.renderEmailEvent(
        EmailEventType.MIEMBRO_AGREGADO,
        SAMPLE_RECIPIENT,
        context,
    )

    assert "<script>" not in rendered.html
    assert "&lt;script&gt;" in rendered.html


@pytest.mark.parametrize(
    "event",
    sorted(
        MEASUREMENT_EVENTS - {EmailEventType.ERROR_MEDICION, EmailEventType.CONFIRMAR_CORREO_RESULTADOS},
        key=lambda e: e.value,
    ),
    ids=str,
)
def test_detalle_de_medicion_solo_con_autorizacion(event):
    context = CONTEXTS[event]

    _, sinDetalle = emailService.renderEmailEvent(
        event,
        SAMPLE_RECIPIENT,
        context,
    )

    _, conDetalle = emailService.renderEmailEvent(
        event,
        SAMPLE_RECIPIENT,
        context,
        incluirDetalleMedicion=True,
    )

    assert "112.40" not in sinDetalle.html
    assert "Detalle de la medición" not in sinDetalle.html

    assert "112.40 mg/dL" in conDetalle.html

    assert "112" not in conDetalle.subject
    assert "mg/dL" not in conDetalle.subject


def test_el_pedido_de_confirmacion_nunca_lleva_el_resultado():
    # GL-08: la dirección todavía no está confirmada, así que el correo no puede llevar datos de salud aunque se pida el detalle.
    context = {**CONTEXTS[EmailEventType.CONFIRMAR_CORREO_RESULTADOS], "valorGlucosa": "112.40"}
    _, rendered = emailService.renderEmailEvent(EmailEventType.CONFIRMAR_CORREO_RESULTADOS, SAMPLE_RECIPIENT, context,
                                                incluirDetalleMedicion=True)
    assert "112.40" not in rendered.html and "Detalle de la medición" not in rendered.html


def test_medicion_fuera_umbral_sin_lenguaje_diagnostico():
    _, rendered = emailService.renderEmailEvent(
        EmailEventType.MEDICION_FUERA_UMBRAL,
        SAMPLE_RECIPIENT,
        CONTEXTS[EmailEventType.MEDICION_FUERA_UMBRAL],
        incluirDetalleMedicion=True,
    )

    for forbidden in (
        "hiperglucemia",
        "hipoglucemia",
        "peligro",
        "insulina",
        "diagnóstico de",
    ):
        assert forbidden not in rendered.text.lower()

    assert (
        "fuera del rango configurado para las notificaciones de tu cuenta"
        in rendered.text
    )


def test_retencion_no_afirma_anonimizacion():
    _, rendered = emailService.renderEmailEvent(
        EmailEventType.INFORMACION_RETENCION_DATOS,
        SAMPLE_RECIPIENT,
        CONTEXTS[EmailEventType.INFORMACION_RETENCION_DATOS],
    )

    assert "desidentificada" in rendered.text

    text_lower = rendered.text.lower()

    assert "son anonimizad" not in text_lower
    assert "quedan anonimizad" not in text_lower


@pytest.mark.parametrize("smtpOk", [True, False])
def test_otp_y_destinatario_no_se_registran_en_logs(
    monkeypatch,
    caplog,
    smtpOk,
):
    def fakeSend(*args, **kwargs):
        if not smtpOk:
            raise OSError("fallo simulado 123456")

    monkeypatch.setattr(
        sender,
        "sendHtmlEmail",
        fakeSend,
    )

    context = {
        **CONTEXTS[EmailEventType.CODIGO_MFA_EMAIL],
        "codigoMfa": "123456",
    }

    with caplog.at_level(logging.DEBUG):
        result = emailService.sendEmailEvent(
            EmailEventType.CODIGO_MFA_EMAIL,
            SAMPLE_RECIPIENT,
            context,
        )

    assert result is smtpOk

    assert caplog.records, "Debe registrar el resultado técnico."

    assert "123456" not in caplog.text
    assert SAMPLE_RECIPIENT not in caplog.text


def test_envio_en_segundo_plano_no_propaga_errores(
    monkeypatch,
    caplog,
):
    """Un aviso en segundo plano nunca propaga errores: un fallo de envío se registra con su causa (devuelve False) y un
    error al generar el correo se registra como «no generado». Sin destinatario no hace nada."""

    class InlineExecutor:
        def submit(self, fn, *args, **kwargs):
            return fn(*args, **kwargs)

    monkeypatch.setattr(emailService, "_executor", InlineExecutor())

    with caplog.at_level(logging.DEBUG):
        # 1) Falla el SMTP (el arnés lo bloquea como una red caída): se registra el fallo de envío y no se propaga.
        emailService.sendEmailEventInBackground(
            EmailEventType.MFA_DESACTIVADO, SAMPLE_RECIPIENT, CONTEXTS[EmailEventType.MFA_DESACTIVADO]
        )
        assert "no se pudo enviar el correo" in caplog.text.lower()

        # 2) Falla la generación (contexto incompleto): se registra como «no generado» y no se propaga.
        emailService.sendEmailEventInBackground(EmailEventType.MFA_DESACTIVADO, SAMPLE_RECIPIENT, {})
        assert "no generado" in caplog.text.lower()

        # 3) Sin destinatario no se hace nada.
        before = len(caplog.records)
        emailService.sendEmailEventInBackground(EmailEventType.MFA_DESACTIVADO, None, CONTEXTS[EmailEventType.MFA_DESACTIVADO])
        assert len(caplog.records) == before


def test_previsualizacion_genera_archivos(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        preview,
        "OUTPUT_DIR",
        tmp_path,
    )

    written = preview.renderPreviews(ALL_EVENTS)

    assert len(written) == len(ALL_EVENTS)

    html = (
        tmp_path / "CUENTA_CREADA.html"
    ).read_text(encoding="utf-8")

    assert f"cid:{BANNER_CID}" not in html
    assert emailService.loadBanner().filename in html
    assert (tmp_path / "index.html").is_file()