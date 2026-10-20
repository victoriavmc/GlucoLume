# Administrador local del puente (acquisition/bridge/bridge_ctl.py): configuración, estado, inicio automático y seguridad.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_bridge_ctl.py -v
#
# No toca el Programador de tareas ni el registro de Windows ni abre puertos: esas operaciones se reemplazan por dobles de
# prueba (lo que sí se hizo con Windows real se documenta en docs/PUENTE.md).

import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BRIDGE_DIR = Path(__file__).resolve().parents[2] / "acquisition" / "bridge"
sys.path.insert(0, str(BRIDGE_DIR))
spec = importlib.util.spec_from_file_location("bridge_ctl", BRIDGE_DIR / "bridge_ctl.py")
ctl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ctl)

TOKEN = "T" * 48


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Carpeta de configuración y de estado aisladas: nada del equipo real."""
    monkeypatch.setenv("GLUCOLUME_BRIDGE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(ctl, "ENV_PATH", tmp_path / "bridge.env")
    monkeypatch.setattr(ctl, "protectFile", lambda path: True)
    monkeypatch.delenv("BRIDGE_TOKEN", raising=False)
    return tmp_path


def now(offset=0):
    return (datetime.now(timezone.utc) - timedelta(seconds=offset)).isoformat(timespec="seconds")


# --- Configuración -----------------------------------------------------------------------------------------------------------


def test_renderEnv_escribe_las_claves_del_puente_conserva_las_del_usuario_y_omite_vacias():
    text = ctl.renderEnv({"SERIAL_PORT": "COM5", "SERIAL_MEDIUM": "USB", "BRIDGE_API_URL": "http://localhost", "BRIDGE_TOKEN": TOKEN,
                          "BRIDGE_DEVICE_CODE": "GL-0001", "SERIAL_BAUDRATE": ""}, {"BRIDGE_LOCK_PORT": "50000", "OTRA": "ajena", "SERIAL_PORT": "COM1"})
    lines = text.splitlines()
    assert lines[0].startswith("# Puente serie de GlucoLume") and "SERIAL_BAUDRATE" not in text and "OTRA" not in text
    assert "SERIAL_PORT=COM5" in lines and "BRIDGE_LOCK_PORT=50000" in lines and f"BRIDGE_TOKEN={TOKEN}" in lines
    assert [line.split("=")[0] for line in lines if "=" in line and not line.startswith("#")][:5] == [
        "SERIAL_PORT", "SERIAL_MEDIUM", "BRIDGE_API_URL", "BRIDGE_TOKEN", "BRIDGE_DEVICE_CODE"]


def test_el_token_del_proyecto_se_lee_solo_si_es_valido(tmp_path):
    envFile = tmp_path / ".env"
    envFile.write_text("DB_PASSWORD=x\nBRIDGE_TOKEN=corto\n", encoding="utf-8")
    assert ctl.projectToken(envFile) is None
    envFile.write_text(f"BRIDGE_TOKEN={TOKEN}\n", encoding="utf-8")
    assert ctl.projectToken(envFile) == TOKEN
    assert ctl.projectToken(tmp_path / "no-existe") is None


def test_setup_sin_preguntas_guarda_la_configuracion_sin_mostrar_el_token_ni_activar_el_inicio_automatico(home, capsys, monkeypatch):
    projectEnv = home / "project.env"
    projectEnv.write_text(f"BRIDGE_TOKEN={TOKEN}\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(ctl, "enableAutostart", lambda: calls.append("enable") or 0)
    monkeypatch.setattr(ctl, "startBridge", lambda *a, **k: calls.append("start") or 0)
    code = ctl.main(["setup", "--yes", "--medium", "usb", "--port", "com7", "--token-file", str(projectEnv), "--api-url", "http://localhost",
                     "--device-code", "GL-0001", "--no-check"])
    out = capsys.readouterr().out
    saved = ctl.readEnv(ctl.ENV_PATH)
    assert code == 0
    assert saved["SERIAL_PORT"] == "COM7" and saved["SERIAL_MEDIUM"] == "USB" and saved["BRIDGE_TOKEN"] == TOKEN
    assert "115200 baudios" in out and TOKEN not in out  # la velocidad sale del medio; el token nunca se imprime
    assert "enable" not in calls  # el inicio automático requiere habilitación explícita


def test_setup_habilita_el_inicio_automatico_solo_si_se_pide(home, monkeypatch):
    projectEnv = home / "project.env"
    projectEnv.write_text(f"BRIDGE_TOKEN={TOKEN}\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(ctl, "enableAutostart", lambda: calls.append("enable") or 0)
    monkeypatch.setattr(ctl, "disableAutostart", lambda: calls.append("disable") or 0)
    monkeypatch.setattr(ctl, "startBridge", lambda *a, **k: 0)
    base = ["setup", "--yes", "--medium", "BLUETOOTH", "--port", "COM4", "--token-file", str(projectEnv), "--no-check", "--no-start"]
    ctl.main(base + ["--autostart", "yes"])
    ctl.main(base + ["--autostart", "no"])
    assert calls == ["enable", "disable"]


def test_setup_rechaza_un_token_corto_y_un_medio_o_url_invalidos(home, capsys, monkeypatch):
    short = home / "short.env"
    short.write_text("BRIDGE_TOKEN=corto\n", encoding="utf-8")
    assert ctl.main(["setup", "--yes", "--medium", "USB", "--port", "COM3", "--token-file", str(short), "--no-check", "--no-start"]) == 2
    assert not ctl.ENV_PATH.exists()
    long = home / "long.env"
    long.write_text(f"BRIDGE_TOKEN={TOKEN}\n", encoding="utf-8")
    code = ctl.main(["setup", "--yes", "--medium", "USB", "--port", "COM3", "--token-file", str(long), "--api-url", "http://192.168.1.9:8000",
                     "--no-check", "--no-start"])
    assert code == 2 and not ctl.ENV_PATH.exists()  # HTTP hacia otra máquina: el token viajaría sin cifrar


def test_setup_valida_el_backend_y_no_guarda_si_el_token_no_coincide(home, monkeypatch):
    long = home / "long.env"
    long.write_text(f"BRIDGE_TOKEN={TOKEN}\n", encoding="utf-8")
    monkeypatch.setattr(ctl, "checkBackend", lambda *a: ("error", "El token no coincide con BRIDGE_TOKEN del backend."))
    code = ctl.main(["setup", "--yes", "--medium", "USB", "--port", "COM3", "--token-file", str(long), "--no-start"])
    assert code == 1 and not ctl.ENV_PATH.exists()


# --- Comprobación contra el backend ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("status,body,level,fragment", [
    (403, {}, "error", "no coincide"),
    (503, {}, "error", "no tiene BRIDGE_TOKEN"),
    (404, {}, "error", "anterior a esta versión"),
    (500, {}, "error", "respondió 500"),
    (200, {"registrado": False}, "ok", "lo registra solo la primera vez"),
    (200, {"registrado": True, "operativo": False}, "warn", "no operativo"),
    (200, {"registrado": True, "operativo": True, "sensor": "MAX30100"}, "ok", "registrado y operativo (MAX30100)"),
])
def test_interpreta_la_comprobacion_del_backend(status, body, level, fragment):
    got = ctl.interpretCheck(status, body, "GL-0001")
    assert got[0] == level and fragment in got[1]


def test_backend_inaccesible_se_explica(monkeypatch):
    def fail(*args, **kwargs):
        raise ConnectionRefusedError("rechazada")

    monkeypatch.setattr(ctl, "post", fail)
    level, message = ctl.checkBackend("http://localhost", TOKEN, "GL-0001")
    assert level == "error" and "docker compose up -d" in message and TOKEN not in message


# --- Estado -----------------------------------------------------------------------------------------------------------------------


def test_interpreta_cada_estado_del_puente(monkeypatch):
    monkeypatch.setattr(ctl, "pidAlive", lambda pid: pid == 1)
    base = {"pid": 1, "estado": "EJECUTANDO", "estadoEnlace": "CONECTADO", "backendOk": True, "puerto": "COM4"}
    assert ctl.interpretStatus(False, None, None)["estado"] == "NO_CONFIGURADO"
    assert ctl.interpretStatus(True, None, None)["estado"] == "DETENIDO"
    assert ctl.interpretStatus(True, {**base, "pid": 2}, 1)["estado"] == "DETENIDO"  # el proceso ya no existe
    assert ctl.interpretStatus(True, base, 60)["estado"] == "DETENIDO"  # estado viejo: nadie lo está escribiendo
    assert ctl.interpretStatus(True, {**base, "estado": "DETENIDO"}, 1)["estado"] == "DETENIDO"
    assert ctl.interpretStatus(True, {**base, "estado": "ERROR", "error": "token rechazado"}, 1) == {
        "estado": "ERROR", "titulo": "Error", "detalle": "token rechazado"}
    assert ctl.interpretStatus(True, {**base, "estadoEnlace": "PAUSADO", "pausado": True}, 1)["estado"] == "PAUSADO"
    reconnecting = ctl.interpretStatus(True, {**base, "estadoEnlace": "REINTENTANDO", "error": "ocupado"}, 1)
    assert reconnecting["estado"] == "RECONECTANDO" and reconnecting["detalle"] == "ocupado"
    assert ctl.interpretStatus(True, {**base, "backendOk": False, "errorBackend": "sin respuesta"}, 1)["estado"] == "SIN_BACKEND"
    assert ctl.interpretStatus(True, base, 1)["estado"] == "TRANSMITIENDO"


def test_status_json_no_expone_el_token(home, capsys, monkeypatch):
    ctl.ENV_PATH.write_text(f"SERIAL_PORT=COM4\nBRIDGE_TOKEN={TOKEN}\n", encoding="utf-8")
    state = Path(os.environ["GLUCOLUME_BRIDGE_HOME"])
    state.mkdir(parents=True)
    (state / "status.json").write_text(json.dumps({"pid": os.getpid(), "estado": "EJECUTANDO", "estadoEnlace": "CONECTADO", "backendOk": True,
                                                    "actualizado": now(), "puerto": "COM4", "medio": "BLUETOOTH", "baudios": 9600}), encoding="utf-8")
    monkeypatch.setattr(ctl, "autostartState", lambda: "desactivado")
    assert ctl.showStatus(asJson=True) == 0
    out = capsys.readouterr().out
    assert json.loads(out)["estado"] == "TRANSMITIENDO" and TOKEN not in out and "BRIDGE_TOKEN" not in out


def test_pidAlive_distingue_procesos_vivos_sin_matarlos():
    assert ctl.pidAlive(os.getpid()) is True
    assert ctl.pidAlive(None) is False and ctl.pidAlive(0) is False and ctl.pidAlive("x") is False
    assert ctl.pidAlive(os.getpid()) is True  # consultarlo no lo termina (en Windows os.kill(pid, 0) sí lo haría)


def test_detener_sin_puente_no_hace_nada_y_iniciar_sin_configurar_lo_explica(home, capsys):
    assert ctl.stopBridge() == 0
    assert ctl.startBridge() == 2
    out = capsys.readouterr().out
    assert "ya está detenido" in out and "Todavía no está configurado" in out
    assert not (Path(os.environ["GLUCOLUME_BRIDGE_HOME"]) / "stop.flag").exists()


# --- Inicio automático ------------------------------------------------------------------------------------------------------------


def test_la_tarea_programada_es_de_usuario_sin_ventana_ni_privilegios_y_sin_limites_de_bateria():
    xml = ctl.taskXml("PC\\Victoria & Co", "C:\\Program Files\\Python\\pythonw.exe", "C:\\gl\\glucolume_bridge.py", "C:\\gl\\bridge.env", "C:\\gl")
    assert "<LogonTrigger>" in xml and "<RunLevel>LeastPrivilege</RunLevel>" in xml and "<LogonType>InteractiveToken</LogonType>" in xml
    assert "<DisallowStartIfOnBatteries>false" in xml and "<StopIfGoingOnBatteries>false" in xml
    assert "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>" in xml  # nunca dos instancias
    assert "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>" in xml and "<RestartOnFailure>" in xml
    assert "pythonw.exe" in xml and "--service" in xml and '--env-file "C:\\gl\\bridge.env"' in xml
    assert "Victoria &amp; Co" in xml and "Victoria & Co" not in xml  # el XML escapa el usuario
    assert "BRIDGE_TOKEN" not in xml and TOKEN not in xml


def test_el_inicio_automatico_exige_la_configuracion_previa(home, capsys):
    assert ctl.enableAutostart() == 2 or os.name != "nt"


def test_el_comando_de_inicio_usa_pythonw_sin_consola_y_el_archivo_de_configuracion():
    command = ctl.commandLine()
    assert command[1].endswith("glucolume_bridge.py") and "--service" in command and "--env-file" in command
    assert Path(command[0]).name.lower() in ("pythonw.exe", "python.exe", "python", "python3")


# --- Puertos ----------------------------------------------------------------------------------------------------------------------


def test_describePort_marca_bluetooth_arduino_y_estado_de_windows():
    text = ctl.describePort({"puerto": "COM3", "descripcion": "USB-SERIAL CH340 (COM3)", "esBluetooth": False, "esArduino": True, "estadoWindows": "Unknown"})
    assert "COM3" in text and "Arduino/USB-serial" in text and "Unknown" in text
    plain = ctl.describePort({"puerto": "COM1", "descripcion": None, "esBluetooth": False, "esArduino": False, "estadoWindows": "OK"})
    assert "sin descripción" in plain and "⚠" not in plain


def test_las_sugerencias_priorizan_el_medio_pero_nunca_ocultan_los_demas_si_no_hay_coincidencia():
    ports = [{"puerto": "COM1", "esBluetooth": False, "esArduino": False}, {"puerto": "COM4", "esBluetooth": True, "esArduino": False},
             {"puerto": "COM3", "esBluetooth": False, "esArduino": True}]
    assert [p["puerto"] for p in ctl.suggestedPorts(ports, "BLUETOOTH")] == ["COM4"]
    assert [p["puerto"] for p in ctl.suggestedPorts(ports, "USB")] == ["COM3"]
    assert len(ctl.suggestedPorts([ports[0]], "USB")) == 1  # sin candidatos del medio: se muestran todos
