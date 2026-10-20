# POST /acquisition/connect solo abre puertos que el servidor enumera.
#
#     python -m pytest tests/test_acquisition_port_validation.py -v
#
# Hallazgo de la auditoría Cloudflare (run-1): `puerto` era texto libre pasado a pySerial: cualquier cuenta que mide abría nodos arbitrarios del servidor
# (p. ej. /dev/ptmx), quedaba como dueña del único enlace y los códigos de error revelaban qué rutas existen.

import pytest

from app.acquisition.link import link
from app.core.exceptions import AuthError
from app.schemas.acquisition import ConnectRequest
from app.services import acquisition as acquisitionService
from tests.test_account_deletion import db, engine, mails, makeUser  # noqa: F401 - fixtures
from tests.test_measurements import consumer  # noqa: F401


@pytest.fixture(autouse=True)
def freshLink():
    link.disconnect()
    yield
    link.disconnect()


class OpensAnything:
    """pySerial falso que «abre» cualquier ruta (como /dev/ptmx en un contenedor Linux)."""

    def __init__(self, *args, **kwargs):
        self.args = args

    def __getattr__(self, name):
        return lambda *a, **k: b""


@pytest.fixture
def anyPathOpens(monkeypatch):
    import serial

    monkeypatch.setattr(serial, "Serial", OpensAnything)


@pytest.mark.parametrize("path", ["/etc/passwd", "/dev/ptmx", "/dev/null", "/nonexistent/x", "../../etc/shadow", "COM99"])
def test_una_ruta_que_el_equipo_no_enumera_se_rechaza_con_un_error_uniforme(db, mails, consumer, anyPathOpens, monkeypatch, path):
    user, _ = consumer
    monkeypatch.setattr(link, "listPorts", staticmethod(lambda: [{"puerto": "COM3"}, {"puerto": "COM4"}]))
    with pytest.raises(AuthError) as error:
        acquisitionService.connect(db, user, ConnectRequest(puerto=path, medio="USB"))
    assert error.value.code == "PUERTO_NO_ENCONTRADO"  # el mismo error exista o no la ruta: no hay oráculo
    assert not link.connected() and link.owner is None


def test_un_puerto_enumerado_se_abre_normalmente(db, mails, consumer, monkeypatch):
    user, _ = consumer
    monkeypatch.setattr(link, "listPorts", staticmethod(lambda: [{"puerto": "COM3"}]))
    seen = {}

    class Fake:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

        def __getattr__(self, name):
            return lambda *a, **k: b""

    def opener(path, baud):
        seen["path"] = path
        return Fake()

    # Con apertura inyectada (pruebas) no hay validación; con la real, «com3» (otra capitalización de Windows) sí es el puerto enumerado.
    monkeypatch.setattr(link, "connect", lambda owner, port, medium, baud=None, opener=None, start=True: seen.setdefault("real", port))
    acquisitionService.connect(db, user, ConnectRequest(puerto="com3", medio="USB"))
    assert seen["real"] == "com3"
