# Lectura del Arduino desde el NAVEGADOR (Web Serial), sin instalar el puente: el enlace lo abre una cuenta con su sesión, queda atado a ella,
# no recibe órdenes del servidor y cede ante un puente instalado.
#
#     python -m pytest tests/test_browser_link.py -v
#
# Datos sintéticos, SQLite temporal y reloj falso (los de test_telemetry). `Browser` hace lo que hace la pantalla: envía a ingestBrowser() las líneas
# del firmware con el formato real.

import uuid

import pytest
from sqlalchemy import select

from app.acquisition.telemetry import hub
from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.schemas.acquisition import BridgeCommandRequest, BridgeLine, BrowserIngest
from app.services import telemetry as telemetryService
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_measurements import consumer, device  # noqa: F401 - fixtures
from tests.test_telemetry import CODE, bridge, clock, freshHub, line, startFor  # noqa: F401 - fixtures

IDENTITY = f"GLUCOLUME,ID={CODE},SENSOR=MAX30100,FW=1.2.0,SR=100"
SIGNED = "*3.17.0123456789abcdef"


class Browser:
    def __init__(self, db, user, clock, medium="USB") -> None:
        self.db, self.user, self.clock, self.medium = db, user, clock, medium
        self.id, self.seq = uuid.uuid4(), 0

    def send(self, lines=(), state="CONECTADO", stopped=False, error=None):
        entries = []
        for text in lines:
            entries.append(BridgeLine(seq=self.seq, edadMs=0, texto=text))
            self.seq += 1
        return telemetryService.ingestBrowser(self.db, self.user, BrowserIngest(
            idEnlace=self.id, medio=self.medium, baudios=115200 if self.medium == "USB" else 9600, estadoEnlace=state,
            nombrePuerto="USB 2341:0043", error=error, detenido=stopped, lineas=entries))

    def seconds(self, count):
        for _ in range(count):
            self.send([IDENTITY, line()])
            self.clock.advance(1)


@pytest.fixture
def browser(db, clock, consumer) -> Browser:
    return Browser(db, consumer[0], clock)


@pytest.fixture
def other(db, mails):
    return makeUser(db, email="otra@example.com", usuario="otra")


def code(fn, *args):
    try:
        fn(*args)
    except AuthError as error:
        return error.code
    return "OK"


def test_el_navegador_conecta_identifica_el_arduino_y_deja_medir_sin_puente(db, browser, consumer, clock):
    user, profileId = consumer
    dev = device(db, codigo=CODE)
    result = browser.send([IDENTITY, line()])
    assert (result.aceptadas, result.invalidas) == (1, 0) and result.estado == "CONECTADO" and result.comando is None
    snapshot = telemetryService.status(db, user)
    assert snapshot["puente"]["origen"] == "NAVEGADOR" and snapshot["puente"]["propio"] is True
    assert snapshot["puente"]["identidad"] == "FISICA" and snapshot["puente"]["codigoDispositivo"] == CODE
    browser.seconds(1)
    session = startFor(db, user, profileId, dev)
    assert session.estadoMedicion == "ADQUIRIENDO"


def test_no_se_da_de_alta_ningun_dispositivo_con_el_marcador_del_navegador(db, browser):
    for _ in range(15):  # más que el margen del firmware sin ID: un puente sí daría de alta el código declarado
        browser.send([line()])
        browser.clock.advance(5)
    from app.models.device import Device
    assert db.scalars(select(Device)).all() == []


def test_se_quita_la_firma_de_la_linea_porque_el_navegador_no_guarda_la_clave(db, browser):
    result = browser.send([IDENTITY + SIGNED, line() + SIGNED])
    assert (result.aceptadas, result.invalidas) == (1, 0)
    assert hub.identity()["nivel"] == "FISICA"


def test_una_linea_corrupta_se_cuenta_como_invalida(db, browser):
    result = browser.send(["@@##garbage##@@", line()])
    assert (result.aceptadas, result.invalidas) == (1, 1)


def test_reenviar_un_lote_no_duplica_lecturas(db, browser):
    browser.send([line()])
    again = telemetryService.ingestBrowser(db, browser.user, BrowserIngest(
        idEnlace=browser.id, medio="USB", estadoEnlace="CONECTADO", lineas=[BridgeLine(seq=0, edadMs=0, texto=line())]))
    assert (again.aceptadas, again.duplicadas) == (0, 1)


def test_solo_la_cuenta_que_abrio_el_enlace_puede_usar_el_dispositivo(db, browser, other):
    browser.seconds(1)
    assert code(telemetryService.takeControl, db, other) == "DISPOSITIVO_EN_USO"
    assert telemetryService.takeControl(db, browser.user)["controlPropio"] is True
    # Otra cuenta lo ve conectado pero no puede iniciar una sesión sobre él.
    assert telemetryService.status(db, other)["puente"]["propio"] is False


def test_otra_cuenta_no_puede_usar_el_identificador_de_un_enlace_ajeno(db, browser, other, clock):
    browser.seconds(1)
    hijack = Browser(db, other, clock)
    hijack.id = browser.id
    assert code(hijack.send, [line()]) == "PUENTE_DUPLICADO"


def test_un_segundo_navegador_activo_recibe_conflicto_y_uno_viejo_cede(db, browser, other, clock):
    browser.seconds(1)
    second = Browser(db, other, clock)
    assert code(second.send, [line()]) == "PUENTE_DUPLICADO"
    clock.advance(60)  # el primero dejó de latir: el lugar queda libre
    assert second.send([line()]).estado == "CONECTADO"
    assert telemetryService.status(db, other)["puente"]["propio"] is True


def test_el_servidor_no_le_da_ordenes_al_enlace_del_navegador(db, browser):
    browser.seconds(1)
    telemetryService.takeControl(db, browser.user)
    assert code(telemetryService.command, db, browser.user, BridgeCommandRequest(accion="PAUSAR")) == "ORDEN_NO_APLICABLE"


def test_un_puente_instalado_no_comparte_el_dispositivo_con_el_navegador(db, browser, bridge, clock):
    browser.seconds(1)
    with pytest.raises(AuthError) as conflict:
        bridge.send([line()])
    assert conflict.value.code == "PUENTE_DUPLICADO"


def test_cerrar_la_conexion_libera_el_lugar_de_inmediato(db, browser, bridge):
    browser.seconds(1)
    browser.send([], state="DESCONECTADO", stopped=True)
    assert hub.deviceState() == "SIN_PUENTE"
    assert bridge.send([line()]).estado == "CONECTADO"


def test_la_conexion_queda_auditada_una_sola_vez(db, browser):
    browser.seconds(3)
    events = [row for row in db.scalars(select(Audit)).all() if row.accion == "CONECTAR_DISPOSITIVO_NAVEGADOR"]
    assert len(events) == 1 and events[0].resultado == "EXITO" and events[0].idUsuario == browser.user.idUsuario


BROWSER_INGEST = "/api/v1/acquisition/browser/ingest"


def test_el_endpoint_http_recibe_lineas_con_la_sesion_de_la_cuenta(api, consumer):
    user, _ = consumer
    body = {"idEnlace": str(uuid.uuid4()), "medio": "usb", "baudios": 115200, "estadoEnlace": "CONECTADO", "nombrePuerto": "USB 2341:0043",
            "lineas": [{"seq": 0, "edadMs": 0, "texto": IDENTITY}, {"seq": 1, "edadMs": 0, "texto": line()}]}
    response = api(user).post(BROWSER_INGEST, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["aceptadas"] == 1 and response.json()["estado"] == "CONECTADO"


@pytest.mark.parametrize("change", [{"medio": "AUTO"}, {"baudios": 10}, {"codigoDispositivo": "ARD-001"}, {"lineas": [{"seq": 0, "edadMs": 0, "texto": "x" * 513}]}])
def test_el_endpoint_http_rechaza_pedidos_fuera_del_contrato(api, consumer, change):
    body = {"idEnlace": str(uuid.uuid4()), "medio": "USB", "estadoEnlace": "CONECTADO", **change}
    assert api(consumer[0]).post(BROWSER_INGEST, json=body).status_code == 422
