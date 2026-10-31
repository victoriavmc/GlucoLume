# Puente serie de Windows en modo AUTO (acquisition/bridge/glucolume_bridge.py): busca el GlucoLume entre los puertos USB y
# Bluetooth, lo identifica por su línea GLUCOLUME,ID=<uuid>, se reconecta solo y nunca abre dos puertos a la vez.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_bridge_auto.py -v
#
# Sin hardware: `World` simula los COM del equipo (presentes o desconectados, con líneas de firmware o mudos) y registra
# cuántos puertos quedaron abiertos a la vez. Lo que depende de Windows real se prueba aparte (docs/DISPOSITIVOS_Y_ADQUISICION.md).

import threading

import pytest

from tests.test_bridge import FakePort, bridgeModule, config, waitUntil  # noqa: F401 - fixtures y helpers compartidos
from tests.test_bridge_runtime import Rig

ID_A = "3f2a9c10-7b4e-4d2a-9c1e-5a6b7c8d9e0f"
ID_B = "00000000-1111-4222-8333-444455556666"


def idLine(uuid):
    return f"GLUCOLUME,ID={uuid},SENSOR=MAX30100,FW=1.2.0,SR=50"


class Link(FakePort):
    """Un puerto abierto en el mundo simulado: se corta cuando el COM se desconecta."""

    def __init__(self, world, port, lines):
        super().__init__(lines)
        self.world, self.port = world, port

    def readline(self):
        if not self.world.present.get(self.port, False):
            raise OSError("El dispositivo ya no está conectado.")
        return super().readline()

    def close(self):
        super().close()
        self.world.release(self.port)


class World:
    """Los COM del equipo. `feeds[port]` es lo que el firmware escribe al abrirse el puerto (cada apertura empieza de cero)."""

    def __init__(self):
        self.present, self.feeds, self.open = {}, {}, set()
        self.maxOpen, self.opens = 0, []
        self.lock = threading.Lock()
        self.scanner = bridgeModule.PortScanner(lister=self.listed, windows=lambda: {})

    def add(self, port, feed, present=True):
        self.feeds[port], self.present[port] = feed, present
        self.refresh()

    def plug(self, port, present):
        self.present[port] = present
        self.refresh()

    def refresh(self):
        self.scanner.scan()

    def listed(self):
        return [{"puerto": port, "descripcion": "USB-SERIAL CH340", "esBluetooth": False, "esArduino": True, "estadoWindows": None}
                for port, here in self.present.items() if here]

    def opener(self, port, baud):
        with self.lock:
            if not self.present.get(port, False):
                raise FileNotFoundError(2, "El sistema no puede encontrar el archivo especificado.")
            if port in self.open:
                raise PermissionError(13, "Acceso denegado.")
            self.open.add(port)
            self.maxOpen = max(self.maxOpen, len(self.open))
            self.opens.append((port, baud))
        return Link(self, port, self.feeds[port]())

    def release(self, port):
        with self.lock:
            self.open.discard(port)


def autoReader(world, buffer=None, stop=None, probe=0.3):
    buffer = buffer or bridgeModule.LineBuffer()
    stop = stop or threading.Event()
    reader = bridgeModule.SerialReader(config(port="", medium="AUTO", baud=0), buffer, opener=world.opener, stop=stop,
                                       backoff=bridgeModule.Backoff(0.01, 0.02), scanner=world.scanner, probeSeconds=probe,
                                       discoveryEvery=0.05)
    return reader, buffer, stop


def stopReader(reader, stop):
    stop.set()
    reader.join(3)


# --- Configuración -----------------------------------------------------------------------------------------------------------------


def test_auto_no_exige_puerto_y_la_velocidad_la_pone_el_medio_hallado():
    cfg = bridgeModule.readConfig({"SERIAL_MEDIUM": "auto", "SERIAL_BAUDRATE": "9600", "BRIDGE_TOKEN": "k" * 40,
                                   "BRIDGE_DEVICE_CODE": "GL-0001"})
    assert cfg.medium == "AUTO" and cfg.port == "" and cfg.baud == 0


def test_medio_desconocido_se_rechaza_con_el_nuevo_listado():
    with pytest.raises(bridgeModule.ConfigError, match="BLUETOOTH, USB o AUTO"):
        bridgeModule.readConfig({"SERIAL_MEDIUM": "WIFI", "SERIAL_PORT": "COM4", "BRIDGE_TOKEN": "k" * 40, "BRIDGE_DEVICE_CODE": "GL-0001"})


def test_el_payload_en_auto_sin_dispositivo_no_inventa_puerto_ni_velocidad():
    reader, buffer, stop = autoReader(World())
    uplink = bridgeModule.Uplink(config(port="", medium="AUTO", baud=0), reader, buffer)
    body = uplink.payload([])
    assert body["medio"] == "AUTO" and body["puerto"] is None and body["baudios"] is None


# --- Búsqueda e identificación -----------------------------------------------------------------------------------------------------


def test_sin_arduino_permanece_en_dispositivo_desconectado_sin_error_ni_puerto():
    world = World()
    reader, buffer, stop = autoReader(world)
    reader.start()
    try:
        assert waitUntil(lambda: reader.diagnostic()[0] == bridgeModule.NO_DEVICE)
        state, attempt, error, code = reader.diagnostic()
        assert state == "DISPOSITIVO_DESCONECTADO" and code is None and error == bridgeModule.NO_DEVICE_MESSAGE
        assert world.opens == [] and len(buffer) == 0  # no se abrió nada y no hubo nada que reenviar
    finally:
        stopReader(reader, stop)


def test_identifica_al_glucolume_entre_puertos_ajenos_y_no_abre_dos_a_la_vez():
    world = World()
    world.add("COM3", lambda: [b"Hola, soy otro adaptador\r\n"] * 1)  # un COM cualquiera: no se asume válido
    world.add("COM5", lambda: [idLine(ID_A), "AAA", "BBB"])
    reader, buffer, stop = autoReader(world)
    reader.start()
    try:
        assert waitUntil(lambda: reader.diagnostic()[0] == "CONECTADO" and len(buffer) == 2)
        assert (reader.cfg.port, reader.cfg.medium, reader.cfg.baud) == ("COM5", "USB", 115200)
        assert reader.deviceId == ID_A
        assert [l.text for l in buffer.items] == ["AAA", "BBB"]  # la línea de identificación no es una medición
        assert "COM3" in reader.rejected  # abrió pero no informó GlucoLume: se saltea
        assert world.maxOpen == 1
    finally:
        stopReader(reader, stop)


def test_un_puerto_que_no_responde_no_bloquea_al_que_si():
    world = World()
    world.add("COM4", lambda: [])  # Bluetooth mudo: abre, pero nunca informa
    world.add("COM5", lambda: [idLine(ID_A), "XYZ"])
    reader, buffer, stop = autoReader(world, probe=0.2)
    reader.start()
    try:
        assert waitUntil(lambda: len(buffer) == 1)
        assert reader.cfg.port == "COM5" and world.maxOpen == 1
    finally:
        stopReader(reader, stop)


# --- Reconexión sin duplicar -------------------------------------------------------------------------------------------------------


def test_se_reconecta_cuando_el_arduino_vuelve_sin_repetir_lineas():
    world = World()
    world.add("COM5", lambda: [idLine(ID_A), "PRIMERA"])
    reader, buffer, stop = autoReader(world)
    reader.start()
    try:
        assert waitUntil(lambda: len(buffer) == 1)
        world.plug("COM5", False)  # se desenchufa: el enlace se corta
        assert waitUntil(lambda: reader.diagnostic()[0] == bridgeModule.NO_DEVICE)
        world.feeds["COM5"] = lambda: [idLine(ID_A), "SEGUNDA"]
        world.plug("COM5", True)  # vuelve a aparecer
        assert waitUntil(lambda: len(buffer) == 2)
        seqs = [l.seq for l in buffer.items]
        assert seqs == sorted(set(seqs)) and [l.text for l in buffer.items] == ["PRIMERA", "SEGUNDA"]
        assert world.maxOpen == 1 and reader.cfg.port == "COM5"
    finally:
        stopReader(reader, stop)


def test_si_aparece_otro_glucolume_no_se_mezclan_los_dos_puertos():
    world = World()
    world.add("COM5", lambda: [idLine(ID_A), "A1"])
    world.add("COM6", lambda: [idLine(ID_B), "B1"], present=False)
    reader, buffer, stop = autoReader(world)
    reader.start()
    try:
        assert waitUntil(lambda: len(buffer) == 1)
        world.plug("COM6", True)  # un segundo GlucoLume conectado no se lee en paralelo
        assert waitUntil(lambda: len(buffer) == 1 and reader.cfg.port == "COM5")
        assert world.maxOpen == 1 and [l.text for l in buffer.items] == ["A1"]
    finally:
        stopReader(reader, stop)


# --- Orden de la web ----------------------------------------------------------------------------------------------------------------


def test_configurar_auto_desde_la_web_quita_el_puerto_fijo_y_se_conserva(tmp_path):
    rig = Rig(tmp_path)
    try:
        result = rig.command("auto1", "CONFIGURAR", medio="AUTO")
        assert result["ok"] is True and rig.reader.auto is True and rig.reader.cfg.medium == "AUTO"
        text = rig.envFile.read_text(encoding="utf-8")
        assert "SERIAL_MEDIUM=AUTO" in text and "SERIAL_PORT" not in text and "SERIAL_BAUDRATE" not in text
        back = rig.command("usb1", "CONFIGURAR", puerto="COM3", medio="USB")
        assert back["ok"] is True and rig.reader.auto is False and (rig.reader.cfg.port, rig.reader.cfg.baud) == ("COM3", 115200)
    finally:
        rig.stop.set()  # el lector no se arrancó: solo se prueba el manejador de órdenes
