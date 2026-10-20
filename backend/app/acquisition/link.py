# Link - Enlace serie con el Arduino (pySerial) y estado de la adquisición en curso
#
# Se ejecuta en el equipo que tiene acceso físico al dispositivo (USB o puerto COM virtual del HC-06). React nunca abre
# un puerto: todo pasa por FastAPI. Un único enlace por proceso; quien lo abre es su dueño y los demás no lo operan.
#
# Este módulo NO conoce la base de datos: guarda las muestras mediante el `sink` que se le inyecta
# (app/services/acquisition.py), que valida permisos y persiste en MuestraSensor. No genera datos: si el dispositivo
# no responde o se desconecta, se informa el error.
#
# El hilo lector solo llama a `pumpOnce()`; las pruebas lo invocan directamente con un puerto simulado.

import logging
import queue
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.acquisition import oximetry, protocol
from app.core.exceptions import AuthError

BAUD = {"USB": 115200, "BLUETOOTH": 9600}  # HC-06: 9600 baudios de fábrica
BATCH = 40  # muestras por escritura en SQL Server
MAX_SAMPLES = 6000  # tope de seguridad por adquisición (5 min a 20 Hz)
LIVE_EVERY = 20  # recalcula los indicadores provisorios cada N muestras
LIVE_WINDOW = 20.0  # s de señal usados en los indicadores provisorios
MAX_INVALID_LINES = 25  # líneas ilegibles seguidas antes de dar el enlace por dañado
RESPONSE_TIMEOUT = 3.0

logger = logging.getLogger(__name__)

Sink = Callable[["AcquisitionSession", list[protocol.Sample]], None]


def _error(code: str, message: str) -> AuthError:
    return AuthError(code, message)


@dataclass
class AcquisitionSession:
    idMedicion: Any
    userId: Any
    sensor: str
    startedAt: float = field(default_factory=time.monotonic)
    state: str = "ADQUIRIENDO"  # ADQUIRIENDO | FINALIZANDO | ERROR | FIN
    count: int = 0
    persisted: int = 0
    lastTimeMs: int = 0
    deviceDone: bool = False
    error: str | None = None
    errorCode: str | None = None
    buffer: list = field(default_factory=list)
    window: deque = field(default_factory=lambda: deque(maxlen=int(LIVE_WINDOW * 100)))
    live: dict | None = None


class DeviceLink:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.cond = threading.Condition(self.lock)
        self.serial: Any = None
        self.owner: Any = None
        self.port: str | None = None
        self.medium: str | None = None
        self.baud: int | None = None
        self.identification: protocol.Identification | None = None
        self.deviceState: str | None = None
        self.session: AcquisitionSession | None = None
        self.lastError: str | None = None
        self.invalidLines = 0
        self.consecutiveInvalid = 0
        self.pongs = 0
        self.thread: threading.Thread | None = None
        self.stopping = False
        self.subscribers: list[queue.Queue] = []
        self.sink: Sink | None = None
        self.onLost: Callable[[AcquisitionSession | None, str], None] | None = None

    # -- puertos ---------------------------------------------------------------------------------------------

    @staticmethod
    def listPorts() -> list[dict]:
        try:
            from serial.tools import list_ports
        except ImportError as error:
            raise _error("PYSERIAL_NO_DISPONIBLE", "El servidor no tiene instalado pySerial: no puede buscar puertos.") from error
        ports = []
        for item in sorted(list_ports.comports(), key=lambda p: p.device):
            text = f"{item.description or ''} {item.hwid or ''} {item.manufacturer or ''}".lower()
            ports.append({
                "puerto": item.device, "descripcion": item.description or None, "fabricante": item.manufacturer or None,
                "identificador": item.hwid or None,
                "esBluetooth": any(word in text for word in ("bluetooth", "bthenum", "rfcomm")),
                "esArduino": any(word in text for word in ("arduino", "ch340", "ch341", "ftdi", "usb serial", "2341:")),
            })
        return ports

    # -- conexión --------------------------------------------------------------------------------------------

    def connected(self) -> bool:
        return self.serial is not None

    def connect(self, owner: Any, port: str, medium: str, baud: int | None = None,
                opener: Callable[[str, int], Any] | None = None, start: bool = True) -> None:
        with self.lock:
            if self.serial is not None:
                raise _error("DISPOSITIVO_EN_USO", "Ya hay un dispositivo conectado en este equipo: desconectalo primero.")
            speed = baud or BAUD[medium]
            try:
                if opener is None:
                    try:
                        import serial
                    except ImportError as error:
                        raise _error("PYSERIAL_NO_DISPONIBLE", "El servidor no tiene instalado pySerial.") from error

                    def opener(device: str, rate: int):  # noqa: ANN202
                        return serial.Serial(device, rate, timeout=0.5, write_timeout=1.0)

                handle = opener(port, speed)
            except AuthError:
                raise
            except Exception as error:  # SerialException, PermissionError, FileNotFoundError, ...
                raise self._openError(port, error) from error
            self.serial, self.owner, self.port, self.medium, self.baud = handle, owner, port, medium, speed
            self.identification = self.deviceState = self.lastError = None
            self.invalidLines = self.consecutiveInvalid = self.pongs = 0
            self.stopping = False
            if start:
                self.thread = threading.Thread(target=self._run, name="glucolume-serial", daemon=True)
                self.thread.start()
            self._emit({"tipo": "conexion", "conectado": True, "puerto": port, "medio": medium})

    @staticmethod
    def _openError(port: str, error: Exception) -> AuthError:
        text = str(error).lower()
        if isinstance(error, PermissionError) or "access is denied" in text or "permission" in text or "busy" in text:
            return _error("PUERTO_OCUPADO", f"El puerto {port} está en uso por otro programa. Cerralo e intentá de nuevo.")
        if isinstance(error, FileNotFoundError) or "could not open port" in text or "no such file" in text or "cannot find" in text:
            return _error("PUERTO_NO_ENCONTRADO", f"No se encontró el puerto {port}. Verificá la conexión y volvé a buscar puertos.")
        return _error("ERROR_PUERTO", f"No se pudo abrir el puerto {port}.")

    def disconnect(self) -> None:
        with self.lock:
            self.stopping = True
            handle, self.serial = self.serial, None
            self.owner = self.port = self.medium = self.baud = None
            self.identification = self.deviceState = None
            self.cond.notify_all()
        if handle is not None:
            try:
                handle.close()
            except Exception:  # noqa: BLE001 - liberar el puerto nunca debe fallar hacia afuera
                pass
        self._emit({"tipo": "conexion", "conectado": False})

    # -- hilo lector -----------------------------------------------------------------------------------------

    def _run(self) -> None:
        while not self.stopping and self.serial is not None:
            if not self.pumpOnce():
                break

    def pumpOnce(self) -> bool:
        """Lee y procesa una línea. False si el enlace se perdió."""
        handle = self.serial
        if handle is None:
            return False
        try:
            raw = handle.readline()
        except Exception as error:  # noqa: BLE001 - desconexión física del cable o del HC-06
            self._lost(f"Se perdió la comunicación con el dispositivo ({type(error).__name__}).")
            return False
        if not raw:
            return True
        self.feed(raw.decode("ascii", errors="replace") if isinstance(raw, bytes) else raw)
        return True

    def feed(self, line: str) -> None:
        try:
            message = protocol.parse(line)
        except protocol.ProtocolError:
            with self.lock:
                self.invalidLines += 1
                self.consecutiveInvalid += 1
                tooMany = self.consecutiveInvalid >= MAX_INVALID_LINES and self.session is not None
            if tooMany:
                self._lost("Los datos recibidos del dispositivo son ilegibles: revisá el cable, el baud rate y el firmware.",
                           code="DATOS_INVALIDOS")
            return
        if message is None:
            return
        with self.cond:
            self.consecutiveInvalid = 0
            if isinstance(message, protocol.Identification):
                self.identification = message
            elif isinstance(message, protocol.Pong):
                self.pongs += 1
            elif isinstance(message, protocol.Status):
                self.deviceState = message.state
                self._onState(message.state)
            elif isinstance(message, protocol.DeviceError):
                self.lastError = message.code
                self._emit({"tipo": "error", "codigo": message.code})
            elif isinstance(message, protocol.Sample):
                self._onSample(message)
            self.cond.notify_all()

    # -- adquisición -----------------------------------------------------------------------------------------

    def _onState(self, state: str) -> None:
        self._emit({"tipo": "estadoDispositivo", "estado": state})
        session = self.session
        if session is None:
            return
        if state == "FINALIZADA":
            session.deviceDone = True
            self._emit({"tipo": "fin", "muestras": session.count})
        elif state == "ERROR_SENSOR" and session.state == "ADQUIRIENDO":
            self._fail(session, "SENSOR_DESCONECTADO", "El dispositivo informó que perdió el sensor MAX30100/MAX30102.")

    def _onSample(self, sample: protocol.Sample) -> None:
        session = self.session
        if session is None or session.state != "ADQUIRIENDO":
            return
        if session.count >= MAX_SAMPLES:
            self._send("STOP")
            session.deviceDone = True
            return
        session.count += 1
        session.lastTimeMs = sample.timeMs
        session.buffer.append(sample)
        session.window.append((sample.timeMs, sample.red, sample.ir))
        self._emit({"tipo": "muestra", "n": sample.number, "t": sample.timeMs, "red": sample.red, "ir": sample.ir})
        if session.count % LIVE_EVERY == 0:
            self._liveIndicators(session)
        if len(session.buffer) >= BATCH:
            self.flush(session)

    def _liveIndicators(self, session: AcquisitionSession) -> None:
        bits = {"MAX30100": 16, "MAX30102": 18}.get(session.sensor)
        result = oximetry.analyze(list(session.window), defaultRate=None, bits=bits)
        session.live = {"spo2": result.spo2, "frecuenciaCardiaca": result.heartRate, "calidad": result.quality,
                        "motivo": None if result.ok else result.reason, "provisorio": True}
        self._emit({"tipo": "indicadores", **session.live})

    def flush(self, session: AcquisitionSession) -> None:
        """Guarda las muestras pendientes en SQL Server mediante el sink."""
        with self.lock:
            batch, session.buffer = session.buffer, []
        if not batch or self.sink is None:
            return
        try:
            self.sink(session, batch)
            session.persisted += len(batch)
        except AuthError as error:
            self._fail(session, error.code, error.message, flushed=True)
        except Exception:  # noqa: BLE001
            logger.exception("No se pudo guardar un lote de muestras de la medición %s", session.idMedicion)
            self._fail(session, "ERROR_GUARDADO", "No se pudieron guardar las muestras de la adquisición.", flushed=True)

    def _fail(self, session: AcquisitionSession, code: str, message: str, flushed: bool = False) -> None:
        if session.state in ("ERROR", "FIN"):
            return
        session.state, session.errorCode, session.error = "ERROR", code, message
        self._send("STOP")
        self._emit({"tipo": "error", "codigo": code, "mensaje": message})
        if not flushed:
            self.flush(session)

    def beginSession(self, session: AcquisitionSession, sendStart: bool = True) -> None:
        with self.lock:
            if self.serial is None:
                raise _error("DISPOSITIVO_NO_CONECTADO", "No hay un dispositivo conectado.")
            if self.session is not None and self.session.state in ("ADQUIRIENDO", "FINALIZANDO"):
                raise _error("ADQUISICION_ACTIVA", "Ya hay una adquisición en curso.")
            self.session = session
            self.deviceState = None
        if sendStart:
            self._send("START")
            if not self.waitFor(lambda: self.deviceState == "ADQUIRIENDO" or session.count > 0, RESPONSE_TIMEOUT):
                with self.lock:
                    self.session = None
                raise _error("SIN_RESPUESTA_DISPOSITIVO", "El dispositivo no confirmó el inicio de la adquisición.")

    def endSession(self) -> AcquisitionSession | None:
        """Detiene el dispositivo, guarda lo pendiente y cierra la sesión."""
        session = self.session
        if session is None:
            return None
        if session.state == "ADQUIRIENDO":
            session.state = "FINALIZANDO"
        self._send("STOP")
        self.waitFor(lambda: self.deviceState in ("FINALIZADA", "LISTO") or self.serial is None, 1.0)
        return session

    def clearSession(self) -> None:
        with self.lock:
            if self.session is not None:
                self.session.state = "FIN" if self.session.state != "ERROR" else "ERROR"
            self.session = None

    # -- comunicación ----------------------------------------------------------------------------------------

    def _send(self, command: str) -> bool:
        handle = self.serial
        if handle is None:
            return False
        try:
            handle.write((command + "\n").encode("ascii"))
            return True
        except Exception as error:  # noqa: BLE001
            self._lost(f"No se pudo escribir en el dispositivo ({type(error).__name__}).")
            return False

    def waitFor(self, condition: Callable[[], bool], timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self.cond:
            while not condition():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self.cond.wait(min(remaining, 0.1))
        return True

    def probe(self) -> float:
        """PING → PONG; devuelve la latencia en ms."""
        with self.lock:
            before = self.pongs
        started = time.monotonic()
        if not self._send("PING"):
            raise _error("DISPOSITIVO_NO_CONECTADO", "No hay un dispositivo conectado.")
        if not self.waitFor(lambda: self.pongs > before, RESPONSE_TIMEOUT):
            raise _error("SIN_RESPUESTA_DISPOSITIVO", "El dispositivo no respondió. Revisá el cable, el baud rate y el firmware.")
        return round((time.monotonic() - started) * 1000, 1)

    def identify(self) -> protocol.Identification:
        with self.lock:
            self.identification = None
        if not self._send("ID?"):
            raise _error("DISPOSITIVO_NO_CONECTADO", "No hay un dispositivo conectado.")
        if not self.waitFor(lambda: self.identification is not None, RESPONSE_TIMEOUT):
            raise _error("SIN_RESPUESTA_DISPOSITIVO",
                         "El dispositivo no se identificó. Verificá que tenga el firmware de GlucoLume y el baud rate correcto.")
        return self.identification

    # -- pérdida del enlace ----------------------------------------------------------------------------------

    def _lost(self, message: str, code: str = "DISPOSITIVO_DESCONECTADO") -> None:
        with self.lock:
            if self.serial is None:
                return
            session = self.session
            if session is not None and session.state in ("ADQUIRIENDO", "FINALIZANDO"):
                session.state, session.errorCode, session.error = "ERROR", code, message
            self.lastError = message
        self._emit({"tipo": "error", "codigo": code, "mensaje": message})
        if session is not None:
            self.flush(session)  # conserva lo recibido
        self.disconnect()  # libera el puerto
        if self.onLost is not None:
            self.onLost(session, message)

    # -- eventos ---------------------------------------------------------------------------------------------

    def subscribe(self) -> queue.Queue:
        channel: queue.Queue = queue.Queue(maxsize=5000)
        with self.lock:
            self.subscribers.append(channel)
        return channel

    def unsubscribe(self, channel: queue.Queue) -> None:
        with self.lock:
            if channel in self.subscribers:
                self.subscribers.remove(channel)

    def _emit(self, event: dict) -> None:
        event = {**event, "instante": datetime.now(timezone.utc).isoformat()}
        for channel in list(self.subscribers):
            try:
                channel.put_nowait(event)
            except queue.Full:
                pass  # un cliente lento no frena la adquisición

    def snapshot(self) -> dict:
        with self.lock:
            ident, session = self.identification, self.session
            return {
                "conectado": self.serial is not None, "puerto": self.port, "medio": self.medium, "baudios": self.baud,
                "estadoDispositivo": self.deviceState, "ultimoError": self.lastError, "lineasInvalidas": self.invalidLines,
                "dispositivo": None if ident is None else {
                    "codigo": ident.id, "sensor": ident.sensor, "firmware": ident.firmware, "frecuenciaMuestreo": ident.sampleRate},
                "adquisicion": None if session is None else {
                    "idMedicion": str(session.idMedicion), "estado": session.state, "muestras": session.count,
                    "guardadas": session.persisted, "segundos": round(session.lastTimeMs / 1000, 1),
                    "error": session.error, "codigoError": session.errorCode, "indicadores": session.live},
            }


link = DeviceLink()
