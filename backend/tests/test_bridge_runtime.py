# Puente serie de Windows: causas de error, enumeración de puertos, órdenes acotadas, configuración persistente,
# parada limpia y registro sin secretos.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_bridge_runtime.py -v
#
# Sin hardware: `FakePort` (de test_bridge.py) hace de puerto y se prueba el comportamiento del puente. Lo que depende de
# Windows real (COM, Bluetooth, Programador de tareas) se prueba aparte, a mano (docs/PUENTE.md).

import json
import threading
import time

import pytest

from tests.test_bridge import FakePort, bridgeModule, config, waitUntil  # noqa: F401
from tests.test_telemetry import CODE, line

SAMPLE = line()


# --- Causa del error ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("error,code", [
    (PermissionError(13, "Acceso denegado."), "PUERTO_OCUPADO"),
    (OSError("could not open port 'COM4': PermissionError(13, 'Access is denied.', None, 5)"), "PUERTO_OCUPADO"),
    (FileNotFoundError(2, "El sistema no puede encontrar el archivo especificado."), "PUERTO_INEXISTENTE"),
    (OSError("could not open port 'COM9': FileNotFoundError(2, 'The system cannot find the file specified.', None, 2)"), "PUERTO_INEXISTENTE"),
    (OSError("could not open port 'COM4': OSError(22, 'A device attached to the system is not functioning.', None, 31)"), "DISPOSITIVO_SIN_RESPUESTA"),
    (OSError("WinError 121 The semaphore timeout period has expired"), "DISPOSITIVO_SIN_RESPUESTA"),
    (ValueError("cualquier otra cosa"), "ERROR_PUERTO"),
])
def test_clasifica_la_causa_del_fallo_del_puerto(error, code):
    assert bridgeModule.classifyError(error)[0] == code
    assert bridgeModule.classifyError(error)[1]  # siempre hay una explicación


def test_el_lector_informa_la_causa_al_no_poder_abrir():
    stop = threading.Event()
    buffer = bridgeModule.LineBuffer()

    def deny(port, baud):
        raise PermissionError(13, "Acceso denegado.")

    reader = bridgeModule.SerialReader(config(), buffer, opener=deny, stop=stop, backoff=bridgeModule.Backoff(0.01, 0.02))
    reader.start()
    try:
        assert waitUntil(lambda: reader.diagnostic()[3] == "PUERTO_OCUPADO")
        state, attempt, error, code = reader.diagnostic()
        assert state == "REINTENTANDO" and attempt >= 1 and "ocupado por otra aplicación" in error
    finally:
        stop.set()
        reader.join(2)


# --- Puertos que ve el equipo --------------------------------------------------------------------------------------------------


def test_clasifica_bluetooth_y_arduino_por_la_descripcion_de_windows():
    assert bridgeModule.classifyPort("Serie estándar sobre el vínculo Bluetooth (COM4)", r"BTHENUM\{00001101}_LOCALMFG&0002\7&1", None) == (True, False)
    assert bridgeModule.classifyPort("USB-SERIAL CH340 (COM3)", r"USB VID:PID=1A86:7523", "wch.cn", 0x1A86) == (False, True)
    assert bridgeModule.classifyPort("Arduino Uno (COM6)", None, "Arduino LLC", 0x2341) == (False, True)
    assert bridgeModule.classifyPort("Puerto de comunicaciones (COM1)", "ACPI\\PNP0501", None) == (False, False)


def test_interpreta_el_estado_que_informa_windows():
    text = json.dumps([
        {"Name": "USB-SERIAL CH340 (COM3)", "Status": "Unknown", "ConfigManagerErrorCode": 0},
        {"Name": "Serie estándar sobre el vínculo Bluetooth (COM4)", "Status": "OK", "ConfigManagerErrorCode": 0},
        {"Name": "Controlador roto (COM7)", "Status": "Error", "ConfigManagerErrorCode": 28},
        {"Name": "Sin puerto", "Status": "OK", "ConfigManagerErrorCode": 0},
    ])
    parsed = bridgeModule.parsePnp(text)
    assert parsed["COM3"]["estado"] == "Unknown" and parsed["COM4"]["estado"] == "OK" and parsed["COM7"]["estado"] == "Error 28"
    assert set(parsed) == {"COM3", "COM4", "COM7"}
    assert bridgeModule.parsePnp(json.dumps({"Name": "X (COM5)", "Status": "OK"}))["COM5"]["estado"] == "OK"  # un solo objeto
    assert bridgeModule.parsePnp("") == {} and bridgeModule.parsePnp("no es json") == {}


def test_el_escaner_combina_pyserial_y_windows_sin_asumir_ningun_puerto():
    listed = [{"puerto": "COM4", "descripcion": "Bluetooth", "esBluetooth": True, "esArduino": False, "estadoWindows": None}]
    windows = {"COM4": {"descripcion": "Bluetooth (COM4)", "estado": "OK"},
               "COM3": {"descripcion": "USB-SERIAL CH340 (COM3)", "estado": "Unknown"}}  # Windows lo ve, pyserial no
    scanner = bridgeModule.PortScanner(lister=lambda: listed, windows=lambda: windows)
    ports = {p["puerto"]: p for p in scanner.scan()}
    assert ports["COM4"]["estadoWindows"] == "OK"
    assert ports["COM3"]["estadoWindows"] == "Unknown" and ports["COM3"]["esArduino"] is True
    assert scanner.has("com3") and not scanner.has("COM99")


# --- Órdenes -----------------------------------------------------------------------------------------------------------------------


class Rig:
    """Lector con puertos falsos que registran cómo se abrieron, más el manejador de órdenes."""

    def __init__(self, tmp_path, ports=("COM3", "COM4")):
        self.opened, self.stop = [], threading.Event()
        self.envFile = tmp_path / "bridge.env"
        self.envFile.write_text("# mi configuración\nSERIAL_PORT=COM4\nSERIAL_MEDIUM=BLUETOOTH\nSERIAL_BAUDRATE=9600\nBRIDGE_TOKEN=" + "k" * 40
                                + "\nBRIDGE_DEVICE_CODE=" + CODE + "\n", encoding="utf-8")
        self.scanner = bridgeModule.PortScanner(
            lister=lambda: [{"puerto": p, "descripcion": None, "esBluetooth": False, "esArduino": False, "estadoWindows": None} for p in ports],
            windows=lambda: {})
        self.scanner.scan()
        self.buffer = bridgeModule.LineBuffer()

        def opener(port, baud):
            self.opened.append((port, baud))
            return FakePort([SAMPLE])

        self.reader = bridgeModule.SerialReader(config(), self.buffer, opener=opener, stop=self.stop,
                                                backoff=bridgeModule.Backoff(0.01, 0.02))
        self.commands = bridgeModule.CommandHandler(self.reader, self.scanner, self.stop, str(self.envFile))

    def command(self, identifier, action, **extra):
        self.commands.handle({"id": identifier, "accion": action, **extra})
        return self.commands.result

    def close(self):
        self.stop.set()
        self.reader.join(2)


def test_configurar_cambia_de_puerto_y_medio_y_lo_conserva(tmp_path):
    rig = Rig(tmp_path)
    rig.reader.start()
    try:
        assert waitUntil(lambda: ("COM4", 9600) in rig.opened)
        result = rig.command("a1", "CONFIGURAR", puerto="COM3", medio="USB")
        assert result == {"id": "a1", "ok": True, "mensaje": "Ahora lee COM3 a 115200 baudios (usb)."}
        assert waitUntil(lambda: ("COM3", 115200) in rig.opened)  # el lector reabrió con la nueva configuración
        saved = rig.envFile.read_text(encoding="utf-8")
        assert "SERIAL_PORT=COM3" in saved and "SERIAL_MEDIUM=USB" in saved and "SERIAL_BAUDRATE" not in saved
        assert "# mi configuración" in saved and "BRIDGE_DEVICE_CODE=" + CODE in saved  # conserva lo demás
    finally:
        rig.close()


@pytest.mark.parametrize("extra,message", [
    ({"puerto": "COM99", "medio": "USB"}, "no existe en este equipo"),
    ({"puerto": "COM3", "medio": "WIFI"}, "USB, BLUETOOTH o AUTO"),
    ({"puerto": "", "medio": "USB"}, "no existe en este equipo"),
])
def test_configurar_rechaza_puertos_no_enumerados_y_medios_invalidos(tmp_path, extra, message):
    rig = Rig(tmp_path)
    before = rig.envFile.read_text(encoding="utf-8")
    result = rig.command("a2", "CONFIGURAR", **extra)
    assert result["ok"] is False and message in result["mensaje"]
    assert rig.envFile.read_text(encoding="utf-8") == before and rig.reader.cfg.port == "COM4"


def test_pausar_libera_el_puerto_y_reanudar_lo_reabre(tmp_path):
    rig = Rig(tmp_path)
    rig.reader.start()
    try:
        assert waitUntil(lambda: len(rig.opened) == 1)
        assert rig.command("p1", "PAUSAR")["ok"] is True
        assert waitUntil(lambda: rig.reader.diagnostic()[0] == "PAUSADO")
        time.sleep(0.15)
        assert len(rig.opened) == 1  # pausado: no se reabre
        assert rig.command("p2", "REANUDAR")["ok"] is True
        assert waitUntil(lambda: len(rig.opened) == 2 and rig.reader.diagnostic()[0] == "CONECTADO")
    finally:
        rig.close()


def test_detener_y_reiniciar_marcan_la_salida(tmp_path):
    rig = Rig(tmp_path)
    assert rig.command("d1", "DETENER")["ok"] and rig.stop.is_set() and rig.commands.restart is False
    again = Rig(tmp_path)
    assert again.command("r1", "REINICIAR")["ok"] and again.stop.is_set() and again.commands.restart is True


def test_acciones_desconocidas_o_repetidas_no_hacen_nada(tmp_path):
    rig = Rig(tmp_path)
    for action in ("ESCRIBIR", "FORMATEAR", "EJECUTAR", None):
        assert rig.command(f"x-{action}", action)["ok"] is False
    assert not rig.stop.is_set()
    rig.command("same", "PAUSAR")
    rig.reader.paused.clear()
    rig.command("same", "PAUSAR")  # misma orden ya aplicada (el backend la sigue mostrando hasta la confirmación)
    assert not rig.reader.paused.is_set()


# --- Latido ------------------------------------------------------------------------------------------------------------------------


def test_el_latido_informa_causa_puertos_version_y_resultado_de_la_orden(tmp_path):
    rig = Rig(tmp_path)
    rig.reader._set("REINTENTANDO", 2, "El puerto está ocupado por otra aplicación (PermissionError).", "PUERTO_OCUPADO")
    uplink = bridgeModule.Uplink(config(), rig.reader, rig.buffer, post=lambda p: (200, {}), scanner=rig.scanner, commands=rig.commands)
    body = uplink.payload([])
    assert body["codigoError"] == "PUERTO_OCUPADO" and body["versionPuente"] == bridgeModule.VERSION
    assert [p["puerto"] for p in body["puertos"]] == ["COM3", "COM4"] and "comando" not in body
    assert "puertos" not in uplink.payload([])  # sin cambios y sin vencer el intervalo: no se reenvía
    rig.command("c1", "PAUSAR")
    assert uplink.payload([])["comando"]["id"] == "c1"
    assert "k" * 40 not in json.dumps(body)  # el token jamás viaja en el cuerpo (va en el encabezado)


def test_el_latido_entrega_la_orden_del_backend_al_manejador(tmp_path):
    rig = Rig(tmp_path)
    answers = [(200, {"comando": {"id": "z9", "accion": "PAUSAR", "puerto": None, "medio": None}}), (200, {})]
    uplink = bridgeModule.Uplink(config(), rig.reader, rig.buffer, post=lambda payload: answers.pop(0), scanner=rig.scanner, commands=rig.commands)
    uplink.flush()
    assert rig.reader.paused.is_set() and rig.commands.result["id"] == "z9"


# --- Parada, estado y registro ---------------------------------------------------------------------------------------------------


def test_se_detiene_por_archivo_libera_el_puerto_y_deja_el_estado(tmp_path):
    folder = tmp_path / "home"
    folder.mkdir()
    flag, statusPath = folder / "stop.flag", folder / "status.json"
    sent, ports = [], []

    def opener(port, baud):
        ports.append(FakePort([SAMPLE]))
        return ports[-1]

    def post(payload):
        sent.append(payload)
        return 200, {}

    stop = threading.Event()
    result = []
    thread = threading.Thread(target=lambda: result.append(bridgeModule.run(
        config(lockPort=47998), stop, opener=opener, post=post, status=bridgeModule.StatusFile(statusPath), stopFlag=flag)))
    thread.start()
    assert waitUntil(lambda: statusPath.exists() and json.loads(statusPath.read_text("utf-8")).get("estado") == "EJECUTANDO")
    flag.write_text("stop", encoding="utf-8")
    thread.join(10)
    assert not thread.is_alive() and result == [0]
    assert ports[-1].closed is True  # el COM quedó libre
    assert sent[-1]["detenido"] is True  # el último latido avisa al backend
    state = json.loads(statusPath.read_text("utf-8"))
    assert state["estado"] == "DETENIDO" and "token" not in json.dumps(state).lower()
    assert not flag.exists()


def test_reiniciar_devuelve_el_codigo_de_reinicio(tmp_path):
    stop = threading.Event()
    reader_ports = bridgeModule.PortScanner(lister=lambda: [], windows=lambda: {}, stop=stop)
    answers = [(200, {"comando": {"id": "r1", "accion": "REINICIAR"}})]

    def post(payload):
        return answers.pop(0) if answers else (200, {})

    code = bridgeModule.run(config(lockPort=47997), stop, opener=lambda p, b: FakePort([SAMPLE]), post=post, scanner=reader_ports)
    assert code == bridgeModule.EXIT_RESTART


def test_el_registro_no_contiene_el_token(tmp_path, monkeypatch):
    monkeypatch.setenv("GLUCOLUME_BRIDGE_HOME", str(tmp_path))
    secret = "s3cr3t-" + "x" * 40
    logFile = bridgeModule.setupLogging(service=True, secrets=(secret,))
    bridgeModule.log.info("conectando con el token %s al servidor", secret)
    bridgeModule.log.error("error: %s", RuntimeError(f"falló con {secret}"))
    for handler in bridgeModule.logging.getLogger("glucolume").handlers:
        handler.flush()
    text = logFile.read_text(encoding="utf-8")
    assert "conectando con el token" in text and secret not in text and "***" in text
    assert logFile.parent == tmp_path


def test_persistir_la_configuracion_nunca_escribe_el_token(tmp_path):
    path = tmp_path / "bridge.env"
    path.write_text("BRIDGE_TOKEN=" + "k" * 40 + "\nSERIAL_PORT=COM4\n", encoding="utf-8")
    bridgeModule.persistConfig(str(path), {"SERIAL_PORT": "COM5", "BRIDGE_TOKEN": "otro", "NOMBRE_AJENO": "x", "SERIAL_MEDIUM": "USB"})
    text = path.read_text(encoding="utf-8")
    assert "SERIAL_PORT=COM5" in text and "SERIAL_MEDIUM=USB" in text
    assert text.count("BRIDGE_TOKEN=") == 1 and "k" * 40 in text and "otro" not in text and "NOMBRE_AJENO" not in text


def test_el_candado_espera_el_relevo_de_un_reinicio():
    first, second = bridgeModule.SingleInstance(47996), bridgeModule.SingleInstance(47996)
    assert first.acquire()
    assert second.acquire() is False
    threading.Timer(0.3, first.release).start()
    assert second.acquire(wait=3.0) is True
    second.release()
