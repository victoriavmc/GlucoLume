# El correo «Nuevo inicio de sesión» no incluye la dirección IP (ni completa ni parcial): solo fecha, método, navegador, sistema y dispositivo.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_login_email_no_ip.py -v

import re

from app.emails.eventTypes import EmailEventType
from app.emails.renderer import renderEmail
from tests.email_preview.sampleData import sampleContexts


def test_el_correo_de_nuevo_inicio_no_muestra_ninguna_ip():
    context = dict(sampleContexts()[EmailEventType.NUEVO_INICIO_SESION])
    context["ipParcial"] = "190.12.x.x"  # aunque algún llamador la enviara, la plantilla no la muestra
    context["ip"] = "190.12.34.56"
    mail = renderEmail(EmailEventType.NUEVO_INICIO_SESION, context)
    for text in (mail.html, mail.text):
        assert "IP aproximada" not in text and "190.12" not in text
        assert not re.search(r"\b\d{1,3}\.\d{1,3}\.(\d{1,3}|x)\.(\d{1,3}|x)\b", text)
    assert "Navegador" in mail.text and "Sistema operativo" in mail.text  # el resto de los datos se conserva
