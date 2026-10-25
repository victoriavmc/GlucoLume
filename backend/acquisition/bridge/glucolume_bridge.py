#!/usr/bin/env python3
"""GlucoLume - Puente serie (Arduino -> puerto COM -> FastAPI).

Corre en el equipo que tiene acceso físico al dispositivo (Windows: el puerto COM saliente del HC-05/HC-06 emparejado, o
el USB del Arduino). Es el ÚNICO proceso que abre ese puerto. Lee las líneas que escribe el firmware
(GlucoLume_MAX30100.ino) y las envía TAL CUAL, con su antigüedad, a POST /api/v1/acquisition/bridge/ingest del backend
(que puede estar en Docker). No interpreta BPM, SpO2 ni glucosa: el firmware los calcula y el backend los valida.

  * No escribe NUNCA en el Arduino (el firmware acepta DEMO,ON/OFF y CAL,<mg/dL>: esos comandos no salen de aquí).
  * Reconexión automática con espera progresiva (1, 2, 4 ... 30 s) ante puerto ocupado, Bluetooth caído o cable retirado.
  * Si el servidor no responde, conserva las líneas (hasta MAX_BUFFER) y las reenvía; cada línea lleva un `seq` creciente,
    así que un reenvío no duplica lecturas.
  * Una sola instancia por equipo (candado local) y el backend rechaza un segundo puente activo.
  * Autenticación: encabezado X-Bridge-Token con BRIDGE_TOKEN (el mismo valor que el backend). El servidor debe ser
    localhost o HTTPS; con HTTP en otra máquina se rechaza salvo BRIDGE_ALLOW_INSECURE=1.
  * Informa al backend los puertos que VE en este equipo y la causa técnica de un fallo del puerto, y acepta solo órdenes de
    una lista cerrada (CONFIGURAR puerto/medio entre los que él mismo informó, PAUSAR, REANUDAR, DETENER, REINICIAR). Ninguna
    escribe en el Arduino ni ejecuta programas.
  * Autenticación del enlace con el dispositivo (H-05, opcional): con BRIDGE_DEVICE_KEY el puente exige que cada línea del firmware lleve una
    firma (SipHash-2-4, contador anti-repetición) y descarta lo que no verifica. Ver linkauth.py y docs/SEGURIDAD.md; NO cifra el enlace.
  * Registro en %LOCALAPPDATA%\\GlucoLume\\bridge\\bridge.log (rotativo) y estado en status.json. El token y la clave nunca se registran.

Configuración por variables de entorno o archivo (bridge.env junto a este script se carga solo; --env-file lo cambia):
  SERIAL_PORT          puerto COM, p. ej. COM4 (NO está en el código)           [obligatoria]
  SERIAL_MEDIUM        BLUETOOTH (9600 baudios) | USB (115200)                  [BLUETOOTH]
  SERIAL_BAUDRATE      anula la velocidad por defecto del medio
  BRIDGE_API_URL       URL del backend                                          [http://localhost:8000]
  BRIDGE_TOKEN         token compartido con el backend (>= 32 caracteres)       [obligatoria]
  BRIDGE_DEVICE_CODE   código del dispositivo en el inventario de GlucoLume     [obligatoria]
  BRIDGE_DEVICE_KEY    clave de 128 bits (32 hex) que firma las líneas del Arduino [opcional; sin ella el enlace NO está autenticado]
  BRIDGE_LOCK_PORT     puerto TCP local usado como candado de instancia única   [47831]
  GLUCOLUME_BRIDGE_HOME carpeta de registro y estado                            [%LOCALAPPDATA%\\GlucoLume\\bridge]
Requiere pyserial (acquisition/requirements.txt). Detener con Ctrl+C, con `bridge_ctl.py stop` o desde GlucoLume.
"""

import argparse
import collections
import json
import logging
import logging.handlers
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))  # linkauth.py vive junto a este script
import linkauth  # noqa: E402

VERSION = "1.3.0"
BAUD = {"USB": 115200, "BLUETOOTH": 9600}  # los del firmware: USB 115200, Bluetooth HC-05/HC-06 9600
ENV_KEYS = ("SERIAL_PORT", "SERIAL_MEDIUM", "SERIAL_BAUDRATE", "BRIDGE_API_URL", "BRIDGE_TOKEN", "BRIDGE_DEVICE_CODE", "BRIDGE_DEVICE_KEY",
            "BRIDGE_LOCK_PORT", "BRIDGE_ALLOW_INSECURE", "GLUCOLUME_BRIDGE_HOME")
INGEST_PATH = "/api/v1/acquisition/bridge/ingest"
MAX_BUFFER = 1000  # líneas conservadas si el servidor no responde (~16 minutos a 1 por segundo)
MAX_BATCH = 200  # tope del backend por pedido
SEND_INTERVAL = 1.0  # latido y envío cada segundo
SILENCE_REOPEN_SECONDS = 60.0  # un puerto abierto pero mudo por tanto tiempo se reabre (Bluetooth que quedó colgado)
HTTP_TIMEOUT = 5.0
PORTS_EVERY = 10.0  # cada cuánto se reenvía la lista de puertos si no cambió
LOOPBACK = ("localhost", "127.0.0.1", "::1")
EXIT_CONFIG, EXIT_REJECTED, EXIT_DUPLICATE, EXIT_RESTART = 2, 3, 4, 10
COMMAND_ACTIONS = ("CONFIGURAR", "PAUSAR", "REANUDAR", "DETENER", "REINICIAR")

log = logging.getLogger("glucolume.bridge")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    port: str
    medium: str
    baud: int
    apiUrl: str
    token: str
    deviceCode: str
    lockPort: int
    deviceKey: bytes | None = None  # clave que firma las líneas del Arduino (H-05); None = enlace sin autenticar

    @property
    def ingestUrl(self) -> str:
        return self.apiUrl.rstrip("/") + INGEST_PATH


# --- Carpeta local, registro y estado ----------------------------------------------------------------------------------------


def dataDir() -> Path:
    """Carpeta de registro y estado (fuera del repositorio, nunca versionada)."""
    override = os.environ.get("GLUCOLUME_BRIDGE_HOME")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "GlucoLume" / "bridge"


class RedactFilter(logging.Filter):
    """Ningún secreto llega al registro, ni siquiera dentro de un mensaje de error de una librería."""

    def __init__(self, secrets) -> None:
        super().__init__()
        self.secrets = [s for s in secrets if s and len(s) >= 8]

    def filter(self, record: logging.LogRecord) -> bool:
        if self.secrets:
            message = record.getMessage()
            for secret in self.secrets:
                message = message.replace(secret, "***")
            record.msg, record.args = message, ()
        return True


def setupLogging(service: bool = False, verbose: bool = False, secrets=()) -> Path:
    """Registro rotativo en archivo; con consola salvo en modo servicio (pythonw no tiene consola)."""
    folder = dataDir()
    folder.mkdir(parents=True, exist_ok=True)
    logFile = folder / "bridge.log"
    root = logging.getLogger("glucolume")
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    redact = RedactFilter(secrets)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handlers: list[logging.Handler] = [logging.handlers.RotatingFileHandler(logFile, maxBytes=1_000_000, backupCount=3, encoding="utf-8")]
    if not service and sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(redact)
        root.addHandler(handler)
    root.propagate = False
    return logFile


def isoNow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StatusFile:
    """status.json: lo que `bridge_ctl status` y el diagnóstico local leen. Escritura atómica; jamás contiene el token."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.started = isoNow()

    def write(self, data: dict) -> None:
        payload = {"pid": os.getpid(), "version": VERSION, "iniciado": self.started, "actualizado": isoNow(), **data}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(temp, self.path)
        except OSError:
            pass  # el estado local es un auxilio: nunca debe detener la lectura


# --- Configuración -------------------------------------------------------------------------------------------------------------


def loadEnvFile(path: str) -> None:
    """Carga KEY=VALUE de un archivo (como el .env del proyecto) SOLO para las variables del puente. No pisa las que ya
    están en el entorno. Ignora el resto del archivo (contraseñas de base, claves JWT...)."""
    try:
        with open(path, encoding="utf-8") as handle:
            for raw in handle:
                text = raw.strip()
                if not text or text.startswith("#") or "=" not in text:
                    continue
                key, _, value = text.partition("=")
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if key in ENV_KEYS and value and key not in os.environ:
                    os.environ[key] = value
    except FileNotFoundError:
        raise ConfigError(f"No existe el archivo de configuración: {path}") from None


def persistConfig(path: str, values: dict[str, str | None]) -> None:
    """Actualiza solo claves del puente en el archivo de configuración conservando el resto (None borra la clave). Se usa
    cuando el usuario elige otro puerto o medio desde GlucoLume, para que el cambio sobreviva al reinicio."""
    allowed = {key: value for key, value in values.items() if key in ENV_KEYS and key not in ("BRIDGE_TOKEN", "BRIDGE_DEVICE_KEY")}
    lines = Path(path).read_text(encoding="utf-8").splitlines() if Path(path).exists() else []
    seen: set[str] = set()
    output: list[str] = []
    for raw in lines:
        key = raw.partition("=")[0].strip()
        if key in allowed and not raw.lstrip().startswith("#"):
            seen.add(key)
            if allowed[key] is not None:
                output.append(f"{key}={allowed[key]}")
        else:
            output.append(raw)
    output.extend(f"{key}={value}" for key, value in allowed.items() if key not in seen and value is not None)
    Path(path).write_text("\n".join(output) + "\n", encoding="utf-8")


def readConfig(env: dict[str, str] | None = None) -> Config:
    env = dict(os.environ) if env is None else env

    def need(key: str) -> str:
        value = (env.get(key) or "").strip()
        if not value or value.startswith("<"):  # vacío o el marcador "<CONFIGURAR_...>" de .env.example
            raise ConfigError(f"Falta configurar {key}.")
        return value

    medium = (env.get("SERIAL_MEDIUM") or "BLUETOOTH").strip().upper()
    if medium not in BAUD:
        raise ConfigError("SERIAL_MEDIUM debe ser BLUETOOTH o USB.")
    try:
        baud = int(env.get("SERIAL_BAUDRATE") or BAUD[medium])
        lockPort = int(env.get("BRIDGE_LOCK_PORT") or 47831)
    except ValueError:
        raise ConfigError("SERIAL_BAUDRATE y BRIDGE_LOCK_PORT deben ser números.") from None
    token = need("BRIDGE_TOKEN")
    if len(token) < 32:
        raise ConfigError("BRIDGE_TOKEN debe tener al menos 32 caracteres.")
    apiUrl = (env.get("BRIDGE_API_URL") or "http://localhost:8000").strip()
    parts = urlsplit(apiUrl)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ConfigError("BRIDGE_API_URL no es una URL http(s) válida.")
    if parts.scheme == "http" and parts.hostname not in LOOPBACK and env.get("BRIDGE_ALLOW_INSECURE") != "1":
        raise ConfigError("BRIDGE_API_URL usa HTTP hacia otra máquina: el token viajaría sin cifrar. Usá HTTPS "
                          "(o BRIDGE_ALLOW_INSECURE=1 solo en una red local de confianza).")
    deviceKey = None
    if (env.get("BRIDGE_DEVICE_KEY") or "").strip():
        try:
            deviceKey = linkauth.parseKey(env["BRIDGE_DEVICE_KEY"])
        except linkauth.KeyError_ as error:
            raise ConfigError(str(error)) from None
    return Config(need("SERIAL_PORT"), medium, baud, apiUrl, token, need("BRIDGE_DEVICE_CODE"), lockPort, deviceKey)


class SingleInstance:
    """Candado local: un segundo puente no arranca (el sistema operativo ya impide abrir dos veces el mismo COM, pero
    el candado da un mensaje claro y también cubre dos puertos distintos hacia el mismo backend)."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.sock: socket.socket | None = None

    def acquire(self, wait: float = 0.0) -> bool:
        """`wait`: segundos de espera si otro lo tiene (un reinicio espera a que el anterior suelte el candado)."""
        deadline = time.monotonic() + wait
        while True:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows: bind exclusivo
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                sock.bind(("127.0.0.1", self.port))
            except OSError:
                sock.close()
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.2)
                continue
            self.sock = sock
            return True

    def release(self) -> None:
        if self.sock is not None:
            self.sock.close()
            self.sock = None


class Backoff:
    """Espera progresiva: 1, 2, 4, 8, 16, 30, 30 ... segundos."""

    def __init__(self, first: float = 1.0, cap: float = 30.0) -> None:
        self.first, self.cap, self.current = first, cap, first

    def next(self) -> float:
        value = self.current
        self.current = min(self.cap, self.current * 2)
        return value

    def reset(self) -> None:
        self.current = self.first


@dataclass(frozen=True)
class Line:
    seq: int
    at: float  # reloj monotónico del puente al leerla
    text: str


class LineBuffer:
    """Cola acotada compartida entre el hilo lector y el que envía. El `seq` crece durante toda la vida del proceso."""

    def __init__(self, maxlen: int = MAX_BUFFER) -> None:
        self.items: collections.deque[Line] = collections.deque()
        self.maxlen, self.seq, self.dropped = maxlen, 0, 0
        self.lastLineAt: str | None = None  # instante (UTC) de la última línea leída del Arduino
        self.lock = threading.Lock()

    def add(self, text: str, now: float) -> None:
        with self.lock:
            if len(self.items) >= self.maxlen:
                self.items.popleft()
                self.dropped += 1
            self.items.append(Line(self.seq, now, text))
            self.seq += 1
            self.lastLineAt = isoNow()

    def peek(self, count: int = MAX_BATCH) -> list[Line]:
        with self.lock:
            return list(self.items)[:count]

    def discard(self, upToSeq: int) -> None:
        """Quita lo ya confirmado por el servidor (seq <= upToSeq)."""
        with self.lock:
            while self.items and self.items[0].seq <= upToSeq:
                self.items.popleft()

    def __len__(self) -> int:
        return len(self.items)


# --- Puertos que ve este equipo ---------------------------------------------------------------------------------------------------

ARDUINO_VIDS = {0x2341, 0x2A03, 0x1A86, 0x0403, 0x10C4}  # Arduino, CH340/CH341, FTDI, CP210x
ARDUINO_WORDS = ("arduino", "ch340", "ch341", "usb-serial", "ftdi", "cp210")
PNP_COMMAND = ("Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -match '\\(COM\\d+\\)' } | "
               "Select-Object Name,Status,ConfigManagerErrorCode | ConvertTo-Json -Compress")
_COM_IN_NAME = re.compile(r"\((COM\d+)\)", re.IGNORECASE)


def classifyPort(description: str | None, hwid: str | None, manufacturer: str | None, vid: int | None = None) -> tuple[bool, bool]:
    """(esBluetooth, esArduino) según la descripción y el identificador de hardware que informa el sistema."""
    text = f"{description or ''} {hwid or ''} {manufacturer or ''}".lower()
    bluetooth = "bthenum" in text or "bluetooth" in text
    arduino = (vid in ARDUINO_VIDS) or any(word in text for word in ARDUINO_WORDS)
    return bluetooth, arduino and not bluetooth


def parsePnp(text: str) -> dict[str, dict]:
    """Salida JSON de PNP_COMMAND -> {COMx: {descripcion, estado}}. Un dispositivo con error de controlador no figura «OK»."""
    try:
        data = json.loads(text) if text.strip() else []
    except ValueError:
        return {}
    if isinstance(data, dict):
        data = [data]
    found: dict[str, dict] = {}
    for item in data if isinstance(data, list) else []:
        name = str(item.get("Name") or "")
        match = _COM_IN_NAME.search(name)
        if not match:
            continue
        code = item.get("ConfigManagerErrorCode")
        status = str(item.get("Status") or "")
        state = status if not code else f"Error {code}"
        found[match.group(1).upper()] = {"descripcion": name[:120], "estado": state[:30] or None}
    return found


def readWindowsPorts(run=subprocess.run) -> dict[str, dict]:
    """Estado que Windows informa para cada puerto COM (solo en Windows; si falla, no se informa y no se bloquea nada)."""
    if os.name != "nt":
        return {}
    try:
        done = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", PNP_COMMAND], capture_output=True, text=True,
                   timeout=15, creationflags=0x08000000)  # CREATE_NO_WINDOW
        return parsePnp(done.stdout)
    except Exception:  # noqa: BLE001 - PowerShell ausente, bloqueado o lento
        return {}


def listSerialPorts() -> list[dict]:
    try:
        from serial.tools import list_ports
    except Exception:  # noqa: BLE001 - pyserial ausente
        return []
    ports = []
    for item in list_ports.comports():
        bluetooth, arduino = classifyPort(item.description, item.hwid, item.manufacturer, item.vid)
        ports.append({"puerto": item.device, "descripcion": (item.description or "")[:120] or None,
                      "esBluetooth": bluetooth, "esArduino": arduino, "estadoWindows": None})
    return ports


class PortScanner(threading.Thread):
    """Enumera cada pocos segundos los puertos del equipo (y el estado de Windows cada ~20 s). Solo lee."""

    def __init__(self, lister=None, windows=None, stop: threading.Event | None = None, interval: float = 5.0,
                 windowsEvery: float = 20.0) -> None:
        super().__init__(name="glucolume-ports", daemon=True)
        self.lister, self.windows = lister or listSerialPorts, windows or readWindowsPorts
        self.stop, self.interval, self.windowsEvery = stop or threading.Event(), interval, windowsEvery
        self.ports: list[dict] = []
        self.changes = 0
        self.lock = threading.Lock()
        self._windowsAt = -1e9
        self._windows: dict[str, dict] = {}

    def scan(self) -> list[dict]:
        if time.monotonic() - self._windowsAt >= self.windowsEvery:
            self._windows, self._windowsAt = self.windows(), time.monotonic()
        merged: dict[str, dict] = {}
        for port in self.lister():
            merged[port["puerto"].upper()] = dict(port)
        for name, info in self._windows.items():
            known = merged.get(name)
            if known is not None:
                known["estadoWindows"] = info["estado"]
            else:  # Windows lo conoce pero pyserial no lo enumera: típico de un controlador con problemas
                bluetooth, arduino = classifyPort(info["descripcion"], None, None)
                merged[name] = {"puerto": name, "descripcion": info["descripcion"], "esBluetooth": bluetooth, "esArduino": arduino,
                                "estadoWindows": info["estado"]}
        ports = sorted(merged.values(), key=lambda p: (len(p["puerto"]), p["puerto"]))[:32]
        with self.lock:
            if ports != self.ports:
                self.changes += 1
            self.ports = ports
        return ports

    def snapshot(self) -> list[dict]:
        with self.lock:
            return [dict(p) for p in self.ports]

    def has(self, port: str) -> bool:
        return any(p["puerto"].lower() == port.strip().lower() for p in self.snapshot())

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                self.scan()
            except Exception:  # noqa: BLE001 - una enumeración fallida no detiene el puente
                log.debug("No se pudieron enumerar los puertos.", exc_info=True)
            self.stop.wait(self.interval)


# --- Lectura del puerto -----------------------------------------------------------------------------------------------------------


def classifyError(error: BaseException) -> tuple[str, str]:
    """(código técnico, explicación en castellano) de un fallo al abrir o leer el puerto."""
    text = str(error).lower()
    kind = type(error).__name__
    if (isinstance(error, PermissionError) or "access is denied" in text or "acceso denegado" in text
            or "permission" in text or "busy" in text):
        return "PUERTO_OCUPADO", f"El puerto está ocupado por otra aplicación ({kind})."
    if (isinstance(error, FileNotFoundError) or "cannot find" in text or "no puede encontrar" in text
            or "no such file" in text or "filenotfound" in text):
        return "PUERTO_INEXISTENTE", f"El puerto no existe: ¿dispositivo desconectado o controlador sin instalar? ({kind})."
    if ("semaphore" in text or "semáforo" in text or "not functioning" in text or "no funciona" in text
            or "winerror 121" in text or "winerror 1167" in text or "oserror(22" in text):
        return "DISPOSITIVO_SIN_RESPUESTA", f"El puerto existe pero el dispositivo no responde: ¿Bluetooth apagado o fuera de alcance? ({kind})."
    return "ERROR_PUERTO", f"Error de puerto serie ({kind})."


class SerialReader(threading.Thread):
    """Único dueño del puerto. Abre, lee líneas y, si algo falla, cierra y reintenta con espera progresiva.

    Estados que informa al backend: CONECTADO | REINTENTANDO (intentando abrir) | DESCONECTADO (se perdió el enlace) | PAUSADO
    (el usuario liberó el puerto)."""

    def __init__(self, cfg: Config, buffer: LineBuffer, opener=None, clock=time.monotonic, stop: threading.Event | None = None,
                 silenceSeconds: float = SILENCE_REOPEN_SECONDS, backoff: Backoff | None = None,
                 authenticator: "linkauth.LineAuthenticator | None" = None) -> None:
        super().__init__(name="glucolume-serial", daemon=True)
        self.cfg, self.buffer, self.clock = cfg, buffer, clock
        self.authenticator = authenticator  # con clave de dispositivo: solo pasan las líneas con firma válida y contador nuevo (H-05)
        self.stop = stop or threading.Event()
        self.silenceSeconds = silenceSeconds
        self.backoff = backoff or Backoff()
        self.opener = opener or self._openSerial
        self.state, self.attempt, self.error, self.code = "DESCONECTADO", 0, None, None
        self.opens = 0
        self.stateLock = threading.Lock()
        self.paused = threading.Event()
        self.reopen = threading.Event()

    def _openSerial(self, port: str, baud: int):
        import serial  # pyserial

        handle = serial.Serial()
        handle.port, handle.baudrate, handle.timeout = port, baud, 0.5
        handle.dtr = handle.rts = False  # no reiniciar el Arduino UNO al abrir el USB
        handle.open()
        return handle

    def snapshot(self) -> tuple[str, int, str | None]:
        with self.stateLock:
            return self.state, self.attempt, self.error

    def diagnostic(self) -> tuple[str, int, str | None, str | None]:
        with self.stateLock:
            return self.state, self.attempt, self.error, self.code

    def _set(self, state: str, attempt: int | None = None, error: str | None = None, code: str | None = None) -> None:
        with self.stateLock:
            self.state = state
            if attempt is not None:
                self.attempt = attempt
            self.error, self.code = error, code

    # -- órdenes del usuario (siempre a través del backend autenticado) --------------------------------------------------

    def reconfigure(self, port: str, medium: str, baud: int) -> None:
        self.cfg = replace(self.cfg, port=port, medium=medium, baud=baud)
        self.paused.clear()
        self.reopen.set()
        self.backoff.reset()

    def pause(self) -> None:
        self.paused.set()
        self.reopen.set()

    def resume(self) -> None:
        self.paused.clear()
        self.reopen.set()
        self.backoff.reset()

    def _sleep(self, seconds: float) -> None:
        """Espera interrumpible: una reconfiguración, una pausa o una detención cortan la espera."""
        deadline = time.monotonic() + seconds
        while not self.stop.is_set() and not self.reopen.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self.stop.wait(min(0.2, remaining))

    @staticmethod
    def describe(error: BaseException) -> str:
        return classifyError(error)[1]

    def run(self) -> None:
        attempt = 0
        while not self.stop.is_set():
            if self.paused.is_set():
                self._set("PAUSADO", 0, "Lectura pausada: el puerto está libre.")
                self.reopen.clear()
                self.stop.wait(0.2)
                continue
            self.reopen.clear()
            cfg = self.cfg
            try:
                handle = self.opener(cfg.port, cfg.baud)
            except Exception as error:  # noqa: BLE001 - SerialException, PermissionError, OSError...
                attempt += 1
                code, message = classifyError(error)
                self._set("REINTENTANDO", attempt, message, code)
                wait = self.backoff.next()
                log.warning("No se pudo abrir %s (intento %d): %s Reintento en %.0f s.", cfg.port, attempt, message, wait)
                self._sleep(wait)
                continue
            self.opens += 1
            attempt = 0
            self.backoff.reset()
            self._set("CONECTADO", 0, None, None)
            log.info("Puerto %s abierto a %d baudios.", cfg.port, cfg.baud)
            try:
                self._pump(handle)
            finally:
                try:
                    handle.close()  # libera el COM siempre
                except Exception:  # noqa: BLE001
                    pass

    def _pump(self, handle) -> None:
        lastData = self.clock()
        while not self.stop.is_set():
            if self.reopen.is_set() or self.paused.is_set():
                return  # se cierra el puerto (el bucle exterior lo reabre con la nueva configuración o lo deja pausado)
            try:
                raw = handle.readline()
            except Exception as error:  # noqa: BLE001 - desconexión física o caída del Bluetooth
                code, message = classifyError(error)
                self._set("DESCONECTADO", 0, message, code)
                log.warning("Se perdió el enlace con el dispositivo: %s", message)
                self._sleep(self.backoff.next())
                return
            now = self.clock()
            if raw:
                lastData = now
                text = (raw.decode("ascii", errors="replace") if isinstance(raw, bytes) else str(raw)).strip()
                if text and self.authenticator is not None:
                    verdict = self.authenticator.verify(text[:512])
                    text = verdict.payload or ""  # descartada: no llega al backend (se cuenta y se registra sin su contenido)
                if text:
                    self.buffer.add(text[:512], now)
            elif now - lastData > self.silenceSeconds:
                self._set("DESCONECTADO", 0, "El puerto está abierto pero no llegan datos: se reabre.", "SIN_DATOS")
                log.warning("Sin datos en %s por %.0f s: se reabre el puerto.", self.cfg.port, self.silenceSeconds)
                return


class Fatal(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def httpPost(url: str, token: str, payload: dict, timeout: float = HTTP_TIMEOUT) -> tuple[int, dict]:
    """POST JSON. Devuelve (status, cuerpo). Las respuestas HTTP de error no son excepciones; las fallas de red sí."""
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "X-Bridge-Token": token})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - esquema validado en readConfig
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        try:
            body = json.loads(error.read() or b"{}")
        except ValueError:
            body = {}
        return error.code, body


# --- Órdenes -------------------------------------------------------------------------------------------------------------------------


class CommandHandler:
    """Aplica las órdenes que el backend entrega en la respuesta del latido. Lista cerrada: nada escribe en el Arduino ni
    ejecuta programas, y un puerto solo se acepta si este mismo equipo lo enumera."""

    def __init__(self, reader: SerialReader, scanner: PortScanner | None, stop: threading.Event, envFile: str | None = None) -> None:
        self.reader, self.scanner, self.stop, self.envFile = reader, scanner, stop, envFile
        self.lastId: str | None = None
        self.result: dict | None = None
        self.restart = False

    def handle(self, command: dict) -> None:
        identifier = str(command.get("id") or "")
        if not identifier or identifier == self.lastId:
            return  # ya aplicada: el backend la sigue mostrando hasta recibir la confirmación
        self.lastId = identifier
        action = command.get("accion")
        try:
            ok, message = self._apply(action, command)
        except Exception as error:  # noqa: BLE001 - la orden falló: se informa, el puente sigue
            log.warning("No se pudo aplicar la orden %s (%s).", action, type(error).__name__)
            ok, message = False, f"No se pudo aplicar la orden ({type(error).__name__})."
        log.info("Orden %s: %s", action, message)
        self.result = {"id": identifier, "ok": ok, "mensaje": message[:200]}

    def _apply(self, action, command: dict) -> tuple[bool, str]:
        if action not in COMMAND_ACTIONS:
            return False, "Acción no permitida."
        if action == "CONFIGURAR":
            port, medium = str(command.get("puerto") or ""), str(command.get("medio") or "").upper()
            if medium not in BAUD:
                return False, "El medio debe ser USB o BLUETOOTH."
            if self.scanner is None or not self.scanner.has(port):
                return False, f"El puerto {port or '(vacío)'} no existe en este equipo."
            self.reader.reconfigure(port, medium, BAUD[medium])
            if self.envFile:
                persistConfig(self.envFile, {"SERIAL_PORT": port, "SERIAL_MEDIUM": medium, "SERIAL_BAUDRATE": None})
            return True, f"Ahora lee {port} a {BAUD[medium]} baudios ({medium.lower()})."
        if action == "PAUSAR":
            self.reader.pause()
            return True, "Lectura pausada: el puerto quedó libre."
        if action == "REANUDAR":
            self.reader.resume()
            return True, "Lectura reanudada."
        if action == "DETENER":
            self.stop.set()
            return True, "El puente se detuvo."
        self.restart = True  # REINICIAR
        self.stop.set()
        return True, "El puente se reinicia."


class Uplink:
    """Envía latidos y lotes al backend. Conserva lo no confirmado y reintenta con espera progresiva."""

    def __init__(self, cfg: Config, reader: SerialReader, buffer: LineBuffer, post=None, clock=time.monotonic,
                 bridgeId: str | None = None, scanner: PortScanner | None = None, commands: CommandHandler | None = None) -> None:
        self.cfg, self.reader, self.buffer, self.clock = cfg, reader, buffer, clock
        self.post = post or (lambda payload: httpPost(cfg.ingestUrl, cfg.token, payload))
        self.bridgeId = bridgeId or str(uuid.uuid4())
        self.backoff = Backoff(1.0, 30.0)
        self.sent = self.failures = 0
        self.serverDown = False
        self.lastBackendError: str | None = None
        self.scanner, self.commands = scanner, commands
        self._portsKey: list | None = None
        self._portsAt = -1e9

    def payload(self, lines: list[Line], stopping: bool = False) -> dict:
        state, attempt, error, code = self.reader.diagnostic()
        cfg = self.reader.cfg
        now = self.clock()
        body = {
            "idPuente": self.bridgeId, "codigoDispositivo": cfg.deviceCode, "puerto": cfg.port,
            "medio": cfg.medium, "baudios": cfg.baud, "estadoEnlace": state, "intento": attempt,
            "error": (error or None) and error[:200], "detenido": stopping, "versionPuente": VERSION,
            "lineas": [{"seq": l.seq, "edadMs": max(0, int((now - l.at) * 1000)), "texto": l.text} for l in lines],
        }
        if code:
            body["codigoError"] = code
        if self.scanner is not None:
            ports = self.scanner.snapshot()
            if ports != self._portsKey or now - self._portsAt >= PORTS_EVERY:
                body["puertos"] = ports
                self._portsKey, self._portsAt = ports, now
        if self.commands is not None and self.commands.result is not None:
            body["comando"] = self.commands.result
        return body

    def flush(self, stopping: bool = False) -> float:
        """Un envío (latido + lote). Devuelve cuánto esperar antes del siguiente. Lanza Fatal ante rechazos definitivos.
        `stopping`: último envío al cerrar; el backend libera el lugar del puente sin esperar el vencimiento del latido."""
        lines = self.buffer.peek()
        try:
            status, body = self.post(self.payload(lines, stopping))
        except Exception as error:  # noqa: BLE001 - red caída, timeout, DNS
            self.failures += 1
            wait = self.backoff.next()
            self.lastBackendError = f"Sin respuesta del servidor ({type(error).__name__})."
            if not self.serverDown:
                log.warning("No se pudo contactar al servidor (%s). Se conservan %d líneas; reintento en %.0f s.",
                            type(error).__name__, len(self.buffer), wait)
            self.serverDown = True
            return wait
        if status == 200:
            if self.serverDown:
                log.info("Conexión con el servidor restablecida.")
            self.serverDown = False
            self.lastBackendError = None
            self.backoff.reset()
            if lines:
                self.buffer.discard(lines[-1].seq)
                self.sent += len(lines)
            if self.commands is not None and (body or {}).get("comando"):
                self.commands.handle(body["comando"])
            return 0.0 if len(self.buffer) >= MAX_BATCH else SEND_INTERVAL
        code = (body or {}).get("codigo")
        if code == "PUENTE_FUERA_DE_ALCANCE":
            raise Fatal(EXIT_REJECTED, "La credencial de este puente no corresponde al dispositivo configurado (BRIDGE_DEVICE_CODE).")
        if status == 403 or code in ("PUENTE_NO_AUTORIZADO",):
            raise Fatal(EXIT_REJECTED, "El servidor rechazó el token del puente (distinto del vigente, revocado o vencido): pedí uno nuevo "
                                       "a quien administra GlucoLume.")
        if status == 409 and code == "PUENTE_DUPLICADO":
            raise Fatal(EXIT_DUPLICATE, "Ya hay otro puente activo para este dispositivo: este se detiene.")
        if status == 422 and lines:
            self.buffer.discard(lines[-1].seq)  # un lote que el servidor no acepta nunca se reintenta en bucle
            log.error("El servidor rechazó un lote (422): se descartó para no bloquear el envío.")
            return SEND_INTERVAL
        wait = self.backoff.next()  # 503 (puente deshabilitado en el servidor), 5xx...
        self.lastBackendError = f"El servidor respondió {status} {code or ''}".strip()
        log.warning("El servidor respondió %s %s. Reintento en %.0f s.", status, code or "", wait)
        self.serverDown = True
        return wait


def waitInterruptible(stop: threading.Event, seconds: float, flag: Path | None) -> None:
    """Espera `seconds` en tramos cortos para reaccionar a una detención pedida por archivo (bridge_ctl stop)."""
    deadline = time.monotonic() + seconds
    while not stop.is_set():
        if flag is not None and flag.exists():
            try:
                flag.unlink()
            except OSError:
                pass
            log.info("Detención solicitada desde el administrador local.")
            stop.set()
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        stop.wait(min(0.5, remaining))


def publishStatus(status: StatusFile | None, cfg: Config, reader: SerialReader, uplink: Uplink, buffer: LineBuffer, scanner) -> None:
    if status is None:
        return
    state, attempt, error, code = reader.diagnostic()
    current = reader.cfg
    status.write({
        "estado": "EJECUTANDO", "estadoEnlace": state, "intento": attempt, "error": error, "codigoError": code,
        "puerto": current.port, "medio": current.medium, "baudios": current.baud, "dispositivo": cfg.deviceCode,
        "backend": cfg.apiUrl, "backendOk": not uplink.serverDown, "errorBackend": uplink.lastBackendError,
        "lineasEnviadas": uplink.sent, "lineasEnCola": len(buffer), "ultimaLinea": buffer.lastLineAt,
        "pausado": reader.paused.is_set(), "puertosVistos": len(scanner.snapshot()) if scanner is not None else None,
        "enlaceAutenticado": reader.authenticator is not None,
        "autenticacionEnlace": reader.authenticator.summary() if reader.authenticator is not None else None,
    })


def run(cfg: Config, stop: threading.Event, opener=None, post=None, envFile: str | None = None, scanner: PortScanner | None = None,
        status: StatusFile | None = None, stopFlag: Path | None = None, lockWait: float = 0.0) -> int:
    lock = SingleInstance(cfg.lockPort)
    if not lock.acquire(lockWait):
        log.error("Ya hay un puente de GlucoLume en ejecución en este equipo.")
        return EXIT_DUPLICATE
    buffer = LineBuffer()
    authenticator = linkauth.LineAuthenticator(cfg.deviceKey, dataDir() / "linkauth.json") if cfg.deviceKey is not None else None
    if authenticator is None:
        log.warning("Sin BRIDGE_DEVICE_KEY: el enlace con el dispositivo NO está autenticado (las líneas pueden ser falsificadas o repetidas).")
    reader = SerialReader(cfg, buffer, opener=opener, stop=stop, authenticator=authenticator)
    commands = CommandHandler(reader, scanner, stop, envFile)
    uplink = Uplink(cfg, reader, buffer, post=post, scanner=scanner, commands=commands)
    log.info("Puente %s v%s: %s (%s) -> %s, dispositivo %s", uplink.bridgeId[:8], VERSION, cfg.port, cfg.medium, cfg.ingestUrl, cfg.deviceCode)
    if scanner is not None:
        scanner.start()
    reader.start()
    code = 0
    try:
        while not stop.is_set():
            try:
                wait = uplink.flush()
            except Fatal as fatal:
                log.error("%s", fatal)
                publishStatus(status, cfg, reader, uplink, buffer, scanner)
                if status is not None:
                    status.write({"estado": "ERROR", "error": str(fatal)})
                code = fatal.code
                break
            publishStatus(status, cfg, reader, uplink, buffer, scanner)
            waitInterruptible(stop, wait, stopFlag)
    finally:
        stop.set()
        reader.join(timeout=3)  # cierra el COM antes del último latido
        if authenticator is not None:
            authenticator.flush()
        reader._set("DESCONECTADO", 0, "Puente detenido.")
        try:
            uplink.flush(stopping=True)  # último latido: el backend sabe enseguida que el puerto quedó libre
        except Exception:  # noqa: BLE001 - al cerrar no importa si el servidor no responde
            pass
        if status is not None:
            status.write({"estado": "REINICIANDO" if commands.restart else "DETENIDO", "estadoEnlace": "DESCONECTADO",
                          "puerto": reader.cfg.port, "medio": reader.cfg.medium, "baudios": reader.cfg.baud,
                          "dispositivo": cfg.deviceCode, "lineasEnviadas": uplink.sent})
        lock.release()
    return EXIT_RESTART if commands.restart and code == 0 else code


def defaultEnvFile() -> str | None:
    """bridge.env junto al script (configurado por bridge_ctl) o un .env en la carpeta actual: sin variables manuales."""
    own = os.environ.get("GLUCOLUME_BRIDGE_ENV")
    if own:
        return own
    beside = Path(__file__).resolve().parent / "bridge.env"
    if beside.exists():
        return str(beside)
    return ".env" if os.path.exists(".env") else None


def respawn(envFile: str | None, service: bool) -> None:
    """Lanza una instancia nueva e independiente (REINICIAR): espera el candado mientras esta termina de liberarlo."""
    command = [sys.executable, str(Path(__file__).resolve())]
    if envFile:
        command += ["--env-file", envFile]
    if service:
        command.append("--service")
    command.append("--after-restart")
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    subprocess.Popen(command, creationflags=flags, close_fds=True, stdin=subprocess.DEVNULL,  # noqa: S603
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=os.name != "nt")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Puente serie de GlucoLume (Arduino -> FastAPI).")
    parser.add_argument("--env-file", help="archivo de configuración (por defecto bridge.env junto a este script)")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--service", action="store_true", help="sin consola: solo registro en archivo (inicio automático)")
    parser.add_argument("--after-restart", action="store_true", help="uso interno de REINICIAR")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args(argv)
    if args.version:
        print(VERSION)
        return 0
    envFile = args.env_file or defaultEnvFile()
    try:
        if envFile:
            loadEnvFile(envFile)
        cfg = readConfig()
    except ConfigError as error:
        setupLogging(args.service, args.verbose)
        log.error("%s Ver acquisition/bridge/README.md o ejecutá bridge_ctl.py setup.", error)
        return EXIT_CONFIG
    setupLogging(args.service, args.verbose, secrets=tuple(s for s in (cfg.token, cfg.deviceKey.hex() if cfg.deviceKey else None) if s))
    stop = threading.Event()
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: stop.set())
    folder = dataDir()
    folder.mkdir(parents=True, exist_ok=True)
    code = run(cfg, stop, envFile=envFile, scanner=PortScanner(stop=stop), status=StatusFile(folder / "status.json"),
               stopFlag=folder / "stop.flag", lockWait=15.0 if args.after_restart else 0.0)
    if code == EXIT_RESTART:
        log.info("Reiniciando el puente.")
        respawn(envFile, args.service)
        code = 0
    log.info("Puente detenido.")
    return code


if __name__ == "__main__":
    sys.exit(main())
