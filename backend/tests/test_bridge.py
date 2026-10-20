# Puente serie de Windows (acquisition/bridge/glucolume_bridge.py): lectura, reconexión, envío y seguridad.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_bridge.py -v
#
# NO hay puerto COM ni Arduino: `FakePort` entrega líneas con el formato del firmware y puede fallar a pedido. El
# transporte HTTP del puente se reemplaza por un cliente de prueba de FastAPI (integración puente -> backend sin red).
# Es un mecanismo de prueba, separado de la conexión real: el puente de producción solo usa pyserial.

import importlib.util
import threading
import time
from pathlib import Path

import pytest

from app.acquisition.telemetry import hub
from app.core.config import getSettings
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_measurements import consumer, device  # noqa: F401 - fixtures
from tests.test_telemetry import CODE, TOKEN, line

BRIDGE_PATH = Path(__file__).resolve().parents[2] / "acquisition" / "bridge" / "glucolume_bridge.py"
spec = importlib.util.spec_from_file_location("glucolume_bridge", BRIDGE_PATH)
bridgeModule = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridgeModule)

TOKEN_VALID = "k" * 40


def config(**changes):
    values = dict(port="COM4", medium="BLUETOOTH", baud=9600, apiUrl="http://localhost:8000", token=TOKEN_VALID,
                  deviceCode=CODE, lockPort=47999)
    return bridgeModule.Config(**{**values, **changes})


class FakePort:
    """Puerto serie falso. Si alguien intenta escribir, la prueba falla: el puente es de solo lectura."""

    def __init__(self, lines=(), failAfter=None, silent=False):
        self.lines = [f"{text}\r\n".encode() for text in lines]
        self.failAfter, self.silent, self.reads, self.closed = failAfter, silent, 0, False

    def readline(self):
        if self.closed:
            raise OSError("closed")
        self.reads += 1
        if self.failAfter is not None and self.reads > self.failAfter:
            raise OSError("The device does not recognize the command / se perdió el Bluetooth")
        if self.lines and not self.silent:
            return self.lines.pop(0)
        time.sleep(0.002)
        return b""

    def write(self, data):  # pragma: no cover - no debe ejecutarse nunca
        raise AssertionError("El puente no debe escribir en el Arduino")

    def close(self):
        self.closed = True


def waitUntil(condition, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


# --- Configuración ------------------------------------------------------------------------------------------------------


def env(**extra):
    base = {"SERIAL_PORT": "COM4", "BRIDGE_TOKEN": TOKEN_VALID, "BRIDGE_DEVICE_CODE": CODE}
    return {**base, **extra}


def test_el_puerto_se_configura_por_entorno_y_no_esta_en_el_codigo():
    cfg = bridgeModule.readConfig(env())
    assert (cfg.port, cfg.medium, cfg.baud, cfg.deviceCode) == ("COM4", "BLUETOOTH", 9600, CODE)
    assert bridgeModule.readConfig(env(SERIAL_MEDIUM="usb")).baud == 115200
    assert bridgeModule.readConfig(env(SERIAL_BAUDRATE="38400")).baud == 38400
    assert "COM4" not in BRIDGE_PATH.read_text(encoding="utf-8").replace("p. ej. COM4", "")  # solo en la documentación
    assert cfg.ingestUrl == "http://localhost:8000/api/v1/acquisition/bridge/ingest"


@pytest.mark.parametrize("bad", [
    env(SERIAL_PORT="<CONFIGURAR_PUERTO_LOCAL>"),  # marcador de .env.example
    {k: v for k, v in env().items() if k != "SERIAL_PORT"},
    env(BRIDGE_TOKEN="corto"), {k: v for k, v in env().items() if k != "BRIDGE_DEVICE_CODE"},
    env(SERIAL_MEDIUM="WIFI"), env(SERIAL_BAUDRATE="rapido"), env(BRIDGE_API_URL="ftp://servidor"),
    env(BRIDGE_API_URL="http://192.168.1.50:8000"),  # HTTP hacia otra máquina: el token viajaría sin cifrar
])
def test_configuracion_invalida_se_rechaza(bad):
    with pytest.raises(bridgeModule.ConfigError):
        bridgeModule.readConfig(bad)


def test_https_y_localhost_estan_permitidos():
    assert bridgeModule.readConfig(env(BRIDGE_API_URL="https://glucolume.example.com")).apiUrl.startswith("https://")
    assert bridgeModule.readConfig(env(BRIDGE_API_URL="http://127.0.0.1:8000")).apiUrl
    assert bridgeModule.readConfig(env(BRIDGE_API_URL="http://192.168.1.50:8000", BRIDGE_ALLOW_INSECURE="1")).apiUrl


def test_el_archivo_de_entorno_solo_aporta_las_variables_del_puente(tmp_path, monkeypatch):
    envFile = tmp_path / ".env"
    envFile.write_text("DB_PASSWORD=secreto\nJWT_SECRET=otro\nSERIAL_PORT=COM7\n# comentario\nBRIDGE_DEVICE_CODE=GL-9\n", encoding="utf-8")
    for key in ("SERIAL_PORT", "BRIDGE_DEVICE_CODE", "DB_PASSWORD", "JWT_SECRET"):
        monkeypatch.delenv(key, raising=False)
    bridgeModule.loadEnvFile(str(envFile))
    import os
    assert os.environ["SERIAL_PORT"] == "COM7" and os.environ["BRIDGE_DEVICE_CODE"] == "GL-9"
    assert "DB_PASSWORD" not in os.environ and "JWT_SECRET" not in os.environ
    with pytest.raises(bridgeModule.ConfigError):
        bridgeModule.loadEnvFile(str(tmp_path / "no-existe.env"))


# --- Lectura y reconexión ----------------------------------------------------------------------------------------------


def test_espera_progresiva_y_reinicio():
    backoff = bridgeModule.Backoff(1, 30)
    assert [backoff.next() for _ in range(8)] == [1, 2, 4, 8, 16, 30, 30, 30]
    backoff.reset()
    assert backoff.next() == 1


def reader(opener, **kwargs):
    buffer = bridgeModule.LineBuffer()
    stop = threading.Event()
    instance = bridgeModule.SerialReader(config(), buffer, opener=opener, stop=stop,
                                         backoff=bridgeModule.Backoff(0.01, 0.02), **kwargs)
    return instance, buffer, stop


def test_lee_lineas_y_las_numera(consumer):
    port = FakePort([line(), "Sistema listo.", line(bpm="73.00")])
    instance, buffer, stop = reader(lambda p, b: port)
    instance.start()
    assert waitUntil(lambda: len(buffer) == 3)
    stop.set()
    instance.join(2)
    assert [item.seq for item in buffer.peek()] == [0, 1, 2] and buffer.peek()[1].text == "Sistema listo."
    assert port.closed  # el COM queda libre al detenerse


def test_reintenta_hasta_que_el_bluetooth_vuelve():
    attempts = []

    def opener(port, baud):
        attempts.append((port, baud))
        if len(attempts) < 4:
            raise FileNotFoundError("could not open port 'COM4': FileNotFoundError(2, 'El sistema no puede encontrar el archivo')")
        return FakePort([line()])

    instance, buffer, stop = reader(opener)
    instance.start()
    assert waitUntil(lambda: len(buffer) == 1)
    assert attempts == [("COM4", 9600)] * 4  # el puerto y la velocidad salen de la configuración
    assert instance.snapshot()[0] == "CONECTADO" and instance.snapshot()[1] == 0
    stop.set()
    instance.join(2)


def test_informa_el_estado_mientras_reintenta():
    gate = threading.Event()

    def opener(port, baud):
        if not gate.is_set():
            raise PermissionError("Access is denied")
        return FakePort([line()])

    instance, buffer, stop = reader(opener)
    instance.start()
    assert waitUntil(lambda: instance.snapshot()[1] >= 2)
    state, attempt, error = instance.snapshot()
    assert state == "REINTENTANDO" and attempt >= 2 and "ocupado" in error
    gate.set()
    assert waitUntil(lambda: instance.snapshot()[0] == "CONECTADO")
    stop.set()
    instance.join(2)


def test_pierde_el_enlace_y_se_reconecta_sin_perder_la_numeracion():
    ports = [FakePort([line(), line()], failAfter=3), FakePort([line(bpm="80.00")])]
    opened = []

    def opener(port, baud):
        opened.append(len(opened))
        return ports[len(opened) - 1] if len(opened) <= 2 else FakePort(silent=True)

    instance, buffer, stop = reader(opener)
    instance.start()
    assert waitUntil(lambda: len(buffer) == 3)
    assert [item.seq for item in buffer.peek()] == [0, 1, 2]  # el seq sigue creciendo tras reconectar
    assert ports[0].closed and instance.opens >= 2
    stop.set()
    instance.join(2)


def test_un_puerto_mudo_se_reabre():
    ports = [FakePort(silent=True), FakePort([line()])]
    opened = []

    def opener(port, baud):
        opened.append(1)
        return ports[min(len(opened), 2) - 1]

    instance, buffer, stop = reader(opener, silenceSeconds=0.05)
    instance.start()
    assert waitUntil(lambda: len(buffer) == 1)
    assert len(opened) >= 2 and ports[0].closed
    stop.set()
    instance.join(2)


def test_el_buffer_es_acotado_y_descarta_lo_confirmado():
    buffer = bridgeModule.LineBuffer(maxlen=5)
    for index in range(8):
        buffer.add(f"l{index}", float(index))
    assert len(buffer) == 5 and buffer.dropped == 3 and buffer.peek()[0].text == "l3"
    buffer.discard(5)
    assert [item.text for item in buffer.peek()] == ["l6", "l7"]


def test_instancia_unica():
    first, second = bridgeModule.SingleInstance(47998), bridgeModule.SingleInstance(47998)
    assert first.acquire() and not second.acquire()
    first.release()
    assert second.acquire()
    second.release()


# --- Envío al backend -------------------------------------------------------------------------------------------------------


def uplink(post, port=None, lines=()):
    buffer = bridgeModule.LineBuffer()
    instance = bridgeModule.SerialReader(config(), buffer, opener=lambda p, b: port or FakePort())
    for text in lines:
        buffer.add(text, time.monotonic())
    instance._set("CONECTADO")
    return bridgeModule.Uplink(config(), instance, buffer, post=post), buffer


def test_el_formato_del_pedido():
    sent = []
    link, buffer = uplink(lambda payload: (sent.append(payload) or (200, {})), lines=[line()])
    link.flush()
    body = sent[0]
    assert body["codigoDispositivo"] == CODE and body["puerto"] == "COM4" and body["medio"] == "BLUETOOTH"
    assert body["baudios"] == 9600 and body["estadoEnlace"] == "CONECTADO"
    assert body["lineas"][0]["texto"] == line() and body["lineas"][0]["seq"] == 0 and body["lineas"][0]["edadMs"] >= 0
    assert "token" not in str(body).lower()  # el token viaja en el encabezado, nunca en el cuerpo
    assert len(buffer) == 0


def test_servidor_caido_conserva_las_lineas_y_las_reenvia_sin_duplicar():
    state = {"up": False, "received": []}

    def post(payload):
        if not state["up"]:
            raise ConnectionRefusedError("backend caído")
        state["received"].extend(l["seq"] for l in payload["lineas"])
        return 200, {}

    link, buffer = uplink(post, lines=[line(), line(), line()])
    waits = [link.flush() for _ in range(3)]
    assert waits == [1.0, 2.0, 4.0] and len(buffer) == 3 and link.failures == 3  # espera progresiva, nada se pierde
    state["up"] = True
    link.flush()
    assert state["received"] == [0, 1, 2] and len(buffer) == 0
    link.flush()
    assert state["received"] == [0, 1, 2]  # lo confirmado no se vuelve a enviar


@pytest.mark.parametrize(("status", "body", "code"), [
    (403, {"codigo": "PUENTE_NO_AUTORIZADO"}, bridgeModule.EXIT_REJECTED),
    (409, {"codigo": "PUENTE_DUPLICADO"}, bridgeModule.EXIT_DUPLICATE),
])
def test_rechazos_definitivos_detienen_el_puente(status, body, code):
    link, _ = uplink(lambda payload: (status, body), lines=[line()])
    with pytest.raises(bridgeModule.Fatal) as raised:
        link.flush()
    assert raised.value.code == code


def test_servidor_sin_puente_habilitado_se_reintenta_y_un_lote_invalido_no_bloquea():
    link, buffer = uplink(lambda payload: (503, {"codigo": "PUENTE_NO_CONFIGURADO"}), lines=[line()])
    assert link.flush() == 1.0 and len(buffer) == 1
    link, buffer = uplink(lambda payload: (422, {}), lines=[line()])
    link.flush()
    assert len(buffer) == 0  # un lote que el servidor nunca va a aceptar se descarta


def test_run_integra_lectura_envio_y_cierre_limpio():
    sent, stop = [], threading.Event()
    port = FakePort([line(), line(bpm="73.00")])

    def post(payload):
        sent.append(payload)
        if sum(len(p["lineas"]) for p in sent) >= 2:
            stop.set()
        return 200, {}

    code = bridgeModule.run(config(lockPort=47997), stop, opener=lambda p, b: port, post=post)
    assert code == 0 and port.closed
    assert sent[-1]["estadoEnlace"] == "DESCONECTADO"  # último latido al cerrar: el backend sabe que el puerto quedó libre
    assert sent[-1]["detenido"] is True and all(p["detenido"] is False for p in sent[:-1])


# --- Integración puente -> FastAPI -> estado y guardado ------------------------------------------------------------------------


@pytest.fixture
def liveBackend(engine, monkeypatch):
    monkeypatch.setenv("BRIDGE_TOKEN", TOKEN)
    getSettings.cache_clear()
    hub.reset()
    yield
    hub.reset()


def test_el_puente_alimenta_al_backend_por_http(db, mails, consumer, api, liveBackend):
    user, _ = consumer
    client = api(user)

    def post(payload, token=TOKEN):
        response = client.post("/api/v1/acquisition/bridge/ingest", json=payload, headers={"X-Bridge-Token": token})
        return response.status_code, response.json()

    link, buffer = uplink(post)
    for text in [line(), "Sistema listo.", "@@basura@@"] + [line()] * 10:
        buffer.add(text, time.monotonic())
    assert link.flush() == 1.0 and len(buffer) == 0
    status = client.post("/api/v1/acquisition/telemetry/control").json()  # «Usar dispositivo»: solo quien controla ve los valores
    assert status["estado"] == "CONECTADO" and status["lectura"]["esDemo"] is True
    assert status["lineasInvalidas"] == 1 and status["lecturasRecibidas"] == 11
    assert status["puente"]["medio"] == "BLUETOOTH" and status["puente"]["puerto"] == "COM4"
    # Un token distinto detiene al puente.
    wrong, _ = uplink(lambda payload: post(payload, token="x" * 40), lines=[line()])
    with pytest.raises(bridgeModule.Fatal):
        wrong.flush()
