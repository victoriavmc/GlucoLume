# La alerta de intento de acceso administrativo NO incluye direcciones IP en el correo: ese correo queda fuera del mecanismo de conservación de
# la base. Solo informa cuántos orígenes distintos hubo; las IP se consultan en la auditoría de la consola administrativa.
from datetime import timedelta

from app.services import adminAccessAlerts as alerts
from app.utils.timeZone import nowForDb
from app.emails import renderer
from app.emails.eventTypes import EmailEventType
from tests.test_account_deletion import db, mails, makeUser  # noqa: F401 - fixtures

IPS = ("203.0.113.5", "198.51.100.77", "2001:db8::abcd")


def attempts(now):
    return [alerts.Attempt(correo="admin@example.com", tipoAutenticacion=alerts.TIPO_CONTRASENA, motivo="CREDENCIALES_INVALIDAS",
                           ip=ip, fecha=now - timedelta(minutes=i)) for i, ip in enumerate(IPS)]


def test_el_contexto_del_correo_no_contiene_ninguna_ip():
    context = alerts._context(attempts(nowForDb()), 0, True)
    serialized = repr(context)
    for ip in IPS:
        assert ip not in serialized
    assert "origenes" in context and context["origenes"] == "3 distinto(s)"
    assert "ips" not in context


def test_la_plantilla_renderizada_no_muestra_ninguna_ip():
    context = alerts._context(attempts(nowForDb()), 0, True)
    body = renderer.renderEmail(EmailEventType.ALERTA_INTENTO_ACCESO_ADMIN, context).html
    for ip in IPS:
        assert ip not in body
    assert "Orígenes distintos" in body
