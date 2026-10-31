# Telemetry - Telemetría ya procesada del firmware (GlucoLume_MAX30100) y estado en vivo del puente serie
#
# El firmware calcula BPM, SpO₂, el índice óptico (Beer-Lambert) y, en modo DEMO, un valor SINTÉTICO de glucosa, y
# transmite una línea por segundo (USB 115200 / Bluetooth HC-05/HC-06 9600):
#
#   BPM:76.43,SpO2:99.65,GluExp_mgdl:117.0,Origen:DEMO,IndiceOptico:2.41492,SenalValida:1,Dedo:1,Muestras:58
#
# Este módulo NO calcula nada de eso: solo interpreta la línea, valida el formato y conserva el estado en memoria.
#   - `NA` es «sin valor» (None). Nunca se convierte en cero. El firmware imprime 0.00 en BPM / SpO₂ cuando no tiene
#     valor (sin dedo o sin latidos): también se interpreta como «sin valor», porque 0 no es una medición posible.
#   - Una línea mal formada, truncada o con valores imposibles lanza TelemetryError y se cuenta como corrupta.
#   - Los mensajes periódicos son TELEMETRÍA: viven en memoria y no se guardan. Solo «Guardar medición» persiste una
#     medición (app/services/telemetry.py), con una lectura estabilizada de la sesión.
#
# El puerto COM lo abre SIEMPRE el puente (acquisition/bridge/glucolume_bridge.py), que corre en el equipo con acceso
# físico al dispositivo (Windows) y envía las líneas a POST /acquisition/bridge/ingest con un token compartido. Aquí se
# decide qué estado se muestra y quién ve las lecturas; no se escribe nunca hacia el Arduino.

import math
import queue
import re
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any

from app.acquisition import protocol

ORIGINS = ("DEMO", "EXPERIMENTAL", "SIN_CALIBRAR")

# Señal PPG (fotopletismografía): además de la línea de métricas (1 por segundo) el firmware envía bloques compactos de muestras
# ópticas reales del canal IR, ya sin su componente continua:
#     PPG,<seq>,<máscara>,<v0>,<v1>,...,<vn>
#   seq      contador del bloque (0..255, da la vuelta): permite detectar bloques perdidos.
#   máscara  bit i = 1 si en la muestra i se detectó un latido (detección del propio firmware, no un pico validado).
#   vi       muestra entera (cuentas del sensor, con signo), a PPG_HZ muestras por segundo.
# No es un ECG ni un valor clínico: es la señal óptica que capta el MAX30100. Un hueco (dedo retirado, bloques perdidos) queda como
# hueco: nunca se interpola. Solo se guarda mientras hay una sesión de medición y solo lo posterior a su inicio.
PPG_HZ = 25
PPG_WINDOW = 300  # muestras conservadas por sesión (12 s)
PPG_MAX_CHUNK = 32
PPG_GAP_TOLERANCE = 0.3  # s: más que esto entre bloques se registra como hueco
_PPG_INT = re.compile(r"^-?\d{1,5}$")
REQUIRED_KEYS = ("BPM", "SpO2", "GluExp_mgdl", "Origen", "IndiceOptico", "SenalValida", "Dedo", "Muestras")
# Líneas informativas que el firmware escribe al arrancar o al recibir comandos: no son lecturas ni datos corruptos.
# Identificación persistente del Arduino (EEPROM), con el mismo formato del protocolo GlucoLume (acquisition/protocol.py):
#   GLUCOLUME,ID=<uuid>,SENSOR=MAX30100,FW=<versión>,SR=<Hz>
# El firmware la repite cada ~10 s (por Bluetooth no hay reinicio al abrir el puerto): vence a los IDENTITY_FRESH_SECONDS.
IDENTITY_FRESH_SECONDS = 45.0
# Alta automática del código CONFIGURADO en el puente (firmware sin ID propio): solo si el Arduino nunca informó un ID y la conexión
# lleva más que el período de repetición del ID (10 s) con margen. Evita dar de alta un dispositivo «fantasma» con el código del puente
# mientras un Arduino con ID propio todavía no repitió el suyo (p. ej. tras cambiar de puerto o al iniciar el puente por Bluetooth).
LEGACY_REGISTRATION_GRACE_SECONDS = 15.0
_IDENTITY_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{2,99}$")
INFO_PREFIXES = ("Sistema listo", "Comandos:", "AVISO:", "Indice experimental", "ADVERTENCIA:", "MODO:", "CAL:")

# Frescura y estados -------------------------------------------------------------------------------------------------
BRIDGE_STALE_SECONDS = 10.0  # sin latidos del puente: se considera detenido
DATA_STALE_SECONDS = 5.0  # sin una lectura en este tiempo: el dispositivo no está enviando (≈1 por segundo)

# Criterio de estabilidad de la lectura que se guarda ------------------------------------------------------------------
# Las últimas STABLE_READINGS lecturas CONSECUTIVAS (sin huecos de más de MAX_GAP_SECONDS) deben ser utilizables (dedo
# colocado, señal válida, BPM, SpO₂ e índice óptico con valor, y al menos MIN_SAMPLES muestras procesadas en el segundo:
# el firmware muestrea a 50 Hz), con el mismo Origen, y varían poco entre sí. El valor guardado es la MEDIANA de cada
# magnitud (robusta ante un latido mal detectado). Con datos DEMO no se exige estabilidad de la glucosa (el firmware la
# cambia cada 10 s a propósito).
STABLE_READINGS = 8
MAX_READING_AGE_SECONDS = 5.0
MAX_GAP_SECONDS = 3.0
MAX_VALID_WINDOW_SECONDS = 120.0  # antigüedad máxima de la última lectura válida para guardar tras retirar el dedo
MIN_SAMPLES = 25
MIN_BPM, MAX_BPM = 20.0, 250.0  # fuera de este rango es ruido, no un pulso
MAX_BPM_RANGE = 8.0  # lpm
MAX_SPO2_RANGE = 2.0  # puntos porcentuales
MAX_GLUCOSE_RANGE = 15.0  # mg/dL (solo origen EXPERIMENTAL)
SESSION_MAX_SECONDS = 30 * 60
# El dispositivo es COMPARTIDO (DEC-01): una sola cuenta lo controla a la vez. El control es la reserva de la sesión (`session`): se toma
# con una acción explícita («Usar dispositivo», o «Iniciar medición») y sigue vivo mientras su dueño consulta el estado (la pantalla lo
# hace cada pocos segundos); sin esa señal se da por abandonado y se libera.
ABANDON_SECONDS = 120.0
RESERVATION_SECONDS = 30.0  # control sin medición: se libera si su dueño deja de consultar el estado (cerró la pantalla o perdió la conexión)
PREVIEW_MAX_SECONDS = 5 * 60  # control sin medición: dura a lo sumo 5 min desde la última acción explícita; una medición activa no vence por esto
REGISTRATION_RECHECK_SECONDS = 30.0

_NUMBER = re.compile(r"^\d{1,9}(\.\d{1,9})?$")


class TelemetryError(ValueError):
    """Línea corrupta, truncada o fuera del protocolo."""


@dataclass(frozen=True)
class Reading:
    bpm: float | None
    spo2: float | None
    glucosa: float | None
    origen: str
    indiceOptico: float | None
    senalValida: bool
    dedo: bool
    muestras: int
    at: float = 0.0  # reloj monotónico del servidor al que corresponde la lectura (ya corregido por la edad que informa el puente)
    when: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def usable(self) -> bool:
        """Lectura que puede formar parte de una medición guardada."""
        return (self.dedo and self.senalValida and self.bpm is not None and MIN_BPM <= self.bpm <= MAX_BPM
                and self.spo2 is not None and self.indiceOptico is not None and self.muestras >= MIN_SAMPLES)

    def asDict(self) -> dict:
        return {"bpm": self.bpm, "spo2": self.spo2, "glucosa": self.glucosa, "unidadGlucosa": "mg/dL" if self.glucosa is not None else None,
                "origen": self.origen, "esDemo": self.origen == "DEMO", "indiceOptico": self.indiceOptico,
                "senalValida": self.senalValida, "dedo": self.dedo, "muestras": self.muestras,
                "instante": self.when.isoformat()}


@dataclass(frozen=True)
class PpgChunk:
    seq: int
    mask: int
    values: tuple[int, ...]


@dataclass(frozen=True)
class Identity:
    """Identificador PROPIO del Arduino (persistente en su EEPROM): no es el puerto COM, el medio ni la computadora."""

    code: str
    sensor: str
    firmware: str


@dataclass(frozen=True)
class Notice:
    """Línea de texto del firmware que no es una lectura. `error` solo para «ERROR: …» (p. ej. sensor no detectado)."""

    text: str
    error: bool = False


def _number(key: str, raw: str, maximum: float) -> float:
    if not _NUMBER.match(raw):
        raise TelemetryError(f"{key}: valor numérico inválido")
    value = float(raw)
    if not math.isfinite(value) or value > maximum:
        raise TelemetryError(f"{key}: fuera de rango")
    return value


def parsePpg(text: str) -> PpgChunk:
    """`PPG,<seq>,<máscara>,<v0>,...`. Lanza TelemetryError ante un bloque corrupto o truncado."""
    parts = text.split(",")
    if len(parts) < 4 or len(parts) - 3 > PPG_MAX_CHUNK:
        raise TelemetryError("PPG: cantidad de campos inválida")
    seq, mask = parts[1], parts[2]
    if not seq.isdigit() or not mask.isdigit() or int(seq) > 255:
        raise TelemetryError("PPG: encabezado inválido")
    values = parts[3:]
    if any(not _PPG_INT.match(value) or abs(int(value)) > 32767 for value in values):
        raise TelemetryError("PPG: muestra inválida")
    if int(mask) >= 2 ** len(values):
        raise TelemetryError("PPG: máscara de latidos inválida")
    return PpgChunk(int(seq), int(mask), tuple(int(value) for value in values))


def parseLine(line: str) -> Reading | Notice | PpgChunk | Identity | None:
    """Interpreta una línea del firmware. None si está vacía; Notice si es texto informativo o un error del
    dispositivo; Reading si es telemetría. Lanza TelemetryError ante cualquier otra cosa (ruido del enlace)."""
    text = line.strip()
    if not text:
        return None
    if text.startswith("ERROR:"):
        return Notice(text[:200], error=True)
    if text.startswith(INFO_PREFIXES):
        return Notice(text[:200])
    if text.startswith("PPG,"):
        return parsePpg(text)
    if text.startswith("GLUCOLUME,"):
        try:
            message = protocol.parse(text)
        except protocol.ProtocolError as error:
            raise TelemetryError(f"identificación inválida: {error}") from error
        if not isinstance(message, protocol.Identification) or not _IDENTITY_CODE.fullmatch(message.id):
            raise TelemetryError("identificación inválida")
        return Identity(message.id, message.sensor, message.firmware)
    if not text.startswith("BPM:"):
        raise TelemetryError("línea desconocida")
    fields: dict[str, str] = {}
    for part in text.split(","):
        key, separator, value = part.partition(":")
        if not separator or not key or key in fields:
            raise TelemetryError("campo mal formado o repetido")
        fields[key] = value
    missing = [key for key in REQUIRED_KEYS if key not in fields]
    if missing:
        raise TelemetryError(f"faltan campos: {', '.join(missing)}")

    def optional(key: str, maximum: float, zeroIsMissing: bool = False) -> float | None:
        raw = fields[key]
        if raw == "NA":
            return None
        value = _number(key, raw, maximum)
        return None if zeroIsMissing and value == 0 else value

    origen = fields["Origen"]
    if origen not in ORIGINS:
        raise TelemetryError("Origen desconocido")
    for flag in ("SenalValida", "Dedo"):
        if fields[flag] not in ("0", "1"):
            raise TelemetryError(f"{flag}: debe ser 0 o 1")
    samples = fields["Muestras"]
    if not samples.isdigit() or int(samples) > 65535:
        raise TelemetryError("Muestras: valor inválido")
    bpm = optional("BPM", 300, zeroIsMissing=True)
    spo2 = optional("SpO2", 100, zeroIsMissing=True)
    return Reading(bpm=bpm, spo2=spo2, glucosa=optional("GluExp_mgdl", 1000), origen=origen,
                   indiceOptico=optional("IndiceOptico", 10000), senalValida=fields["SenalValida"] == "1",
                   dedo=fields["Dedo"] == "1", muestras=int(samples))


# --- Estabilidad -------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Stable:
    bpm: int
    spo2: float
    glucosa: float | None
    origen: str
    indiceOptico: float
    lecturas: int


@dataclass(frozen=True)
class Unstable:
    code: str  # DATOS_DESACTUALIZADOS | SIN_LECTURAS | DEDO_NO_DETECTADO | SENAL_NO_VALIDA | LECTURAS_INSUFICIENTES | VARIACION_EXCESIVA
    message: str
    valid: int = 0


UNSTABLE_MESSAGES = {
    "SIN_LECTURAS": "Todavía no llegaron lecturas del dispositivo en esta sesión.",
    "DATOS_DESACTUALIZADOS": "El dispositivo dejó de enviar datos: revisá la conexión Bluetooth.",
    "DEDO_NO_DETECTADO": "El dedo no está colocado sobre el sensor.",
    "SENAL_NO_VALIDA": "La señal del sensor no es válida: mantené el dedo quieto, sin presionar de más.",
    "LECTURAS_INSUFICIENTES": "Todavía no hay suficientes lecturas válidas seguidas: mantené el dedo quieto.",
    "VARIACION_EXCESIVA": "Las lecturas varían demasiado: mantené el dedo quieto unos segundos más.",
    "GLUCOSA_NO_DISPONIBLE": "Estimación de glucosa no disponible: el dispositivo no informa un valor de glucosa (sin calibrar). Esta medición es de "
                             "Glucosa experimental y no se guarda sin un valor de glucosa; cancelala y medí en modo Oximetría.",
}


def evaluateStability(readings: list[Reading], now: float, requireGlucose: bool = False) -> Stable | Unstable:
    """Criterio documentado arriba. Función pura: no toca ningún estado ni la base. `requireGlucose`: la medición es de GLUCOSA_EXPERIMENTAL
    y solo se puede guardar con un valor de glucosa informado por el dispositivo (DEMO o EXPERIMENTAL); sin él no hay resultado válido para ese modo."""
    if not readings:
        return Unstable("SIN_LECTURAS", UNSTABLE_MESSAGES["SIN_LECTURAS"])
    newest = readings[-1]
    if now - newest.at > MAX_READING_AGE_SECONDS:
        return Unstable("DATOS_DESACTUALIZADOS", UNSTABLE_MESSAGES["DATOS_DESACTUALIZADOS"])
    # Rachas de lecturas utilizables seguidas, de la más reciente a la más antigua. Cuenta la última racha COMPLETA
    # (STABLE_READINGS o más) cuya última lectura sea reciente (MAX_VALID_WINDOW_SECONDS): se puede guardar aunque después se haya
    # retirado el dedo o se haya vuelto a apoyar (una racha nueva e incompleta no descarta la ventana que ya se midió). Si no hay
    # ninguna completa, cuenta la última, para informar el avance.
    # Un hueco sin ninguna lectura (corte del enlace) descarta lo anterior; retirar el dedo no lo produce: el dispositivo sigue enviando.
    streaks: list[list[Reading]] = []
    current: list[Reading] = []
    previous: Reading | None = None
    for reading in readings:
        if previous is not None and reading.at - previous.at > MAX_GAP_SECONDS:
            streaks, current = [], []
        previous = reading
        if reading.usable and (not current or reading.at - current[-1].at <= MAX_GAP_SECONDS):
            current.append(reading)
            continue
        if current:
            streaks.append(current)
        current = [reading] if reading.usable else []
    if current:
        streaks.append(current)
    recent = [s for s in streaks if now - s[-1].at <= MAX_VALID_WINDOW_SECONDS]
    run: list[Reading] = next((s for s in reversed(recent) if len(s) >= STABLE_READINGS), recent[-1] if recent else [])
    if len(run) < STABLE_READINGS:
        if not newest.dedo:
            return Unstable("DEDO_NO_DETECTADO", UNSTABLE_MESSAGES["DEDO_NO_DETECTADO"])
        if not newest.senalValida or not newest.usable:
            return Unstable("SENAL_NO_VALIDA", UNSTABLE_MESSAGES["SENAL_NO_VALIDA"])
        return Unstable("LECTURAS_INSUFICIENTES", UNSTABLE_MESSAGES["LECTURAS_INSUFICIENTES"], valid=len(run))
    window = run[-STABLE_READINGS:]
    origen = window[-1].origen
    spread = lambda values: max(values) - min(values)  # noqa: E731
    glucoses = [r.glucosa for r in window]
    glucoseUnstable = origen == "EXPERIMENTAL" and (
        any(g is None for g in glucoses) or spread([g for g in glucoses if g is not None]) > MAX_GLUCOSE_RANGE)
    if (any(r.origen != origen for r in window) or spread([r.bpm for r in window]) > MAX_BPM_RANGE
            or spread([r.spo2 for r in window]) > MAX_SPO2_RANGE or glucoseUnstable):
        return Unstable("VARIACION_EXCESIVA", UNSTABLE_MESSAGES["VARIACION_EXCESIVA"], valid=len(run))
    known = [g for g in glucoses if g is not None]
    keepsGlucose = origen in ("DEMO", "EXPERIMENTAL") and bool(known)
    if requireGlucose and not keepsGlucose:
        return Unstable("GLUCOSA_NO_DISPONIBLE", UNSTABLE_MESSAGES["GLUCOSA_NO_DISPONIBLE"], valid=len(run))
    return Stable(
        bpm=int(round(median(r.bpm for r in window))), spo2=round(median(r.spo2 for r in window), 2),
        glucosa=round(median(known), 2) if keepsGlucose else None, origen=origen,
        indiceOptico=round(median(r.indiceOptico for r in window), 5), lecturas=len(window))


# --- Estado en vivo ----------------------------------------------------------------------------------------------------


BUSY_MESSAGE = "Dispositivo temporalmente ocupado: otra cuenta está midiendo ahora. Reintentá en unos instantes."
CONTROL_REQUIRED_MESSAGE = "Tomá el control del dispositivo («Usar dispositivo») antes de darle órdenes al puente."


class BridgeConflict(Exception):
    """Otro puente activo ya es dueño del dispositivo."""


@dataclass
class BridgeInfo:
    bridgeId: str
    deviceCode: str
    port: str | None
    medium: str
    baud: int | None
    linkState: str = "DESCONECTADO"  # CONECTADO | DESCONECTADO | REINTENTANDO | PAUSADO | DISPOSITIVO_DESCONECTADO (AUTO)
    attempt: int = 0
    error: str | None = None
    lastBeat: float = 0.0
    lastSeq: int = -1
    since: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    errorCode: str | None = None  # causa técnica del último fallo del puerto (ver schemas.acquisition.CodigoErrorPuerto)
    version: str | None = None
    ports: list[dict] | None = None  # puertos que el PROPIO puente ve en su equipo (nunca los enumera el navegador)
    pending: dict | None = None  # única orden esperando que el puente la tome: {id, accion, puerto, medio}
    lastResult: dict | None = None  # resultado de la última orden: {id, ok, mensaje}
    # Identidad FÍSICA informada por el propio Arduino (ver Identity). Se descarta cuando cambia la conexión (puerto, medio, velocidad) o se
    # corta el enlace: dos conexiones no son «el mismo Arduino» por usar el mismo puerto, modelo o velocidad; lo confirma el ID que informa.
    hardware: Identity | None = None
    hardwareAt: float = 0.0
    idSeen: bool = False  # este puente ya vio al menos un ID propio: su firmware lo informa, así que el código configurado no es la identidad
    connectedAt: float = 0.0  # desde cuándo está estable la conexión actual (puerto, medio y velocidad sin cambios)


class CommandRejected(Exception):
    """El pedido de orden al puente no cumple las reglas. `code` es un código de error de la API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


# Órdenes que un usuario autenticado puede pedirle al puente. No existe ninguna que escriba en el Arduino, ejecute
# programas o abra puertos que el propio puente no haya informado.
COMMAND_ACTIONS = ("CONFIGURAR", "PAUSAR", "REANUDAR", "DETENER", "REINICIAR")
COMMAND_MEDIA = ("USB", "BLUETOOTH", "AUTO")


@dataclass
class Session:
    userId: Any
    startedAt: float
    idMedicion: Any = None
    deviceCode: str | None = None
    readings: deque = field(default_factory=lambda: deque(maxlen=240))  # ~1 lectura/s: cubre MAX_VALID_WINDOW_SECONDS (120 s) con margen tras retirar el dedo
    saving: bool = False
    linkLost: bool = False
    lastSeen: float = 0.0  # último instante en que su dueño consultó el estado
    # Señal PPG de ESTA sesión: muestras (None = hueco), latidos detectados por el firmware (índices absolutos) y su continuidad.
    ppg: deque = field(default_factory=lambda: deque(maxlen=PPG_WINDOW))
    ppgBeats: deque = field(default_factory=lambda: deque(maxlen=64))
    ppgNext: int = 0  # índice absoluto de la próxima muestra
    ppgSeq: int | None = None
    ppgAt: float | None = None  # instante en que terminó el último bloque
    modo: str = "OXIMETRIA"  # modo elegido para esta medición

    def addPpg(self, chunk: "PpgChunk", at: float) -> bool:
        """Agrega un bloque. Un bloque repetido se ignora; un salto en el tiempo (dedo retirado, bloques perdidos) deja un hueco."""
        if self.ppgSeq is not None and chunk.seq == self.ppgSeq:
            return False
        if self.ppgAt is not None:
            gap = (at - len(chunk.values) / PPG_HZ) - self.ppgAt
            if gap > PPG_GAP_TOLERANCE:
                missing = min(PPG_WINDOW, int(round(gap * PPG_HZ)))
                self.ppg.extend([None] * missing)
                self.ppgNext += missing
        base = self.ppgNext
        for index, value in enumerate(chunk.values):
            self.ppg.append(value)
            if chunk.mask >> index & 1:
                self.ppgBeats.append(base + index)
        self.ppgNext += len(chunk.values)
        self.ppgSeq, self.ppgAt = chunk.seq, at
        return True
    reason: str | None = None  # por qué terminó sin guardarse (EXPIRADA | ABANDONADA)
    since: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class IngestResult:
    accepted: int = 0
    duplicated: int = 0
    invalid: int = 0
    linkLostDuringSession: bool = False
    command: dict | None = None  # orden pendiente para este puente


class TelemetryHub:
    """Estado en memoria del dispositivo compartido del equipo anfitrión. Un único puente activo y una única sesión
    de medición a la vez: las lecturas solo se atribuyen a quien abrió la sesión y solo las posteriores a su inicio."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.lock = threading.RLock()
        self.reset()

    def reset(self) -> None:
        with self.lock:
            self.bridge: BridgeInfo | None = None
            self.latest: Reading | None = None
            self.notice: Notice | None = None
            self.session: Session | None = None
            self.expired: list[Session] = []  # sesiones con medición que se liberaron solas: el servicio cierra su medición
            self.invalidLines = 0
            self.readingsReceived = 0
            self.subscribers: list[tuple[queue.Queue, Any]] = []
            # Códigos (en minúsculas) cuyo alta automática en el inventario se comprobó, con el instante de la comprobación: evita una
            # consulta por latido pero se revalida cada REGISTRATION_RECHECK_SECONDS (si el dispositivo se borró o la base se recreó, se da de alta de nuevo).
            self.registeredCodes: dict[str, float] = {}
            # Confirmación MANUAL de un operador cuando la identidad física no se pudo comprobar (firmware anterior, sin ID):
            # {userId, idDispositivo, code}. Vale solo para esta conexión: se descarta al cambiar de puente, puerto o Arduino.
            self.confirmation: dict | None = None

    # -- estado derivado ---------------------------------------------------------------------------------------------

    def deviceState(self) -> str:
        with self.lock:
            bridge, now = self.bridge, self.clock()
            if bridge is None or now - bridge.lastBeat > BRIDGE_STALE_SECONDS:
                return "SIN_PUENTE"
            if bridge.linkState != "CONECTADO":  # también en AUTO sin dispositivo: no hay enlace que usar
                return "PUERTO_DESCONECTADO"
            if self.latest is None or now - self.latest.at > DATA_STALE_SECONDS:
                return "SIN_DATOS"
            return "CONECTADO"

    def _forgetIdentity(self, bridge: BridgeInfo) -> None:
        bridge.hardware, bridge.hardwareAt = None, 0.0
        self.confirmation = None

    def identity(self) -> dict:
        """Cómo se identifica el dispositivo conectado ahora.
        FISICA: el Arduino informó su ID persistente (reciente). DECLARADA: solo se conoce el código que se configuró en el puente
        (`BRIDGE_DEVICE_CODE`), que NO prueba qué Arduino es. NINGUNA: no hay un puente que informe nada."""
        with self.lock:
            bridge = self.bridge
            if bridge is None or self.deviceState() == "SIN_PUENTE":
                return {"nivel": "NINGUNA", "codigo": None, "firmware": None, "sensor": None}
            hardware = bridge.hardware
            if hardware is not None and self.clock() - bridge.hardwareAt <= IDENTITY_FRESH_SECONDS:
                return {"nivel": "FISICA", "codigo": hardware.code, "firmware": hardware.firmware, "sensor": hardware.sensor}
            return {"nivel": "DECLARADA", "codigo": bridge.deviceCode, "firmware": None, "sensor": None}

    def registrationAllowed(self) -> bool:
        """¿Se puede dar de alta (sin institución) el dispositivo conectado, de forma AUTOMÁTICA? Siempre exige comunicación verificada (telemetría
        llegando ahora): un puente en marcha con un puerto abierto, o un Arduino que no responde, no registran nada.
        Con ID propio, sí. Con solo el código configurado en el puente (firmware sin ID), únicamente si este puente nunca informó un ID y la
        conexión lleva más que el período de repetición del ID: si lo informó, lo que falta es que lo repita, y no se inventa otro dispositivo."""
        with self.lock:
            bridge = self.bridge
            if bridge is None or self.deviceState() != "CONECTADO":
                return False
            level = self.identity()["nivel"]
            if level == "FISICA":
                return True
            return level == "DECLARADA" and not bridge.idSeen and self.clock() - bridge.connectedAt >= LEGACY_REGISTRATION_GRACE_SECONDS

    def effectiveCode(self) -> str | None:
        return self.identity()["codigo"]

    def confirm(self, userId: Any, idDispositivo: Any) -> None:
        with self.lock:
            self.confirmation = {"userId": userId, "idDispositivo": idDispositivo, "code": (self.effectiveCode() or "").lower()}

    def confirmedDevice(self, userId: Any) -> Any:
        """El dispositivo que `userId` confirmó a mano para la conexión actual (None si no hay o si la conexión cambió)."""
        with self.lock:
            confirmation = self.confirmation
            if confirmation is None or confirmation["userId"] != userId or confirmation["code"] != (self.effectiveCode() or "").lower():
                return None
            return confirmation["idDispositivo"]

    def isConfirmed(self, userId: Any, idDispositivo: Any) -> bool:
        with self.lock:
            confirmation = self.confirmation
            return (confirmation is not None and confirmation["userId"] == userId and confirmation["idDispositivo"] == idDispositivo
                    and confirmation["code"] == (self.effectiveCode() or "").lower())

    def bridgeActive(self) -> bool:
        return self.deviceState() != "SIN_PUENTE"

    def ownsPort(self, port: str) -> bool:
        """El puente activo tiene abierto ese puerto: nadie más debe abrirlo."""
        with self.lock:
            return self.bridgeActive() and self.bridge is not None and (self.bridge.port or "").lower() == port.strip().lower()

    # -- puente ------------------------------------------------------------------------------------------------------

    def ingest(self, bridgeId: str, deviceCode: str, port: str | None, medium: str, baud: int | None, linkState: str,
               attempt: int, error: str | None, lines: list[tuple[int, int, str]], stopped: bool = False,
               errorCode: str | None = None, ports: list[dict] | None = None, version: str | None = None,
               commandResult: dict | None = None) -> IngestResult:
        """Latido y líneas del puente. `lines`: (seq, edad en ms al enviar, texto). Idempotente: un seq ya recibido se ignora.
        `stopped`: el puente se está cerrando a propósito; libera su lugar para que otro (o el mismo, reiniciado) tome el relevo.
        `commandResult`: resultado de la última orden que el puente recibió (cierra la orden pendiente)."""
        result = IngestResult()
        events: list[dict] = []
        with self.lock:
            now = self.clock()
            current = self.bridge
            if current is not None and current.bridgeId != bridgeId and now - current.lastBeat <= BRIDGE_STALE_SECONDS:
                raise BridgeConflict("Ya hay otro puente serie activo para este dispositivo.")
            if current is None or current.bridgeId != bridgeId:
                previous = current
                current = self.bridge = BridgeInfo(bridgeId, deviceCode, port, medium, baud, connectedAt=now)
                self.latest = self.notice = None
                self.confirmation = None
                if previous is not None and previous.pending and previous.pending.get("accion") == "REINICIAR":
                    current.lastResult = {"id": previous.pending["id"], "ok": True, "mensaje": "El puente se reinició."}
                events.append({"tipo": "puente", "activo": True})
            previousState = current.linkState
            if (current.port, current.medium, current.baud) != (port, medium, baud) or linkState != "CONECTADO":
                self._forgetIdentity(current)  # otra conexión (o ninguna): el ID se vuelve a aprender de lo que informe
                current.connectedAt = now
            current.deviceCode, current.port, current.medium, current.baud = deviceCode, port, medium, baud
            current.linkState, current.attempt, current.error, current.lastBeat = linkState, attempt, error, now
            current.errorCode = errorCode if linkState != "CONECTADO" else None
            if version:
                current.version = version
            if ports is not None:
                current.ports = ports
            if commandResult is not None:
                current.lastResult = commandResult
                if current.pending is not None and current.pending["id"] == commandResult["id"]:
                    current.pending = None
            result.command = current.pending
            if previousState == "CONECTADO" and linkState != "CONECTADO":
                self.latest = None
                if self.session is not None and not self.session.linkLost:
                    self.session.linkLost = True
                    result.linkLostDuringSession = True
            for seq, ageMs, text in lines:
                if seq <= current.lastSeq:
                    result.duplicated += 1
                    continue
                current.lastSeq = seq
                try:
                    parsed = parseLine(text)
                except TelemetryError:
                    self.invalidLines += 1
                    result.invalid += 1
                    continue
                if isinstance(parsed, Identity):
                    if current.hardware is not None and current.hardware.code != parsed.code:
                        self.confirmation = None  # otro Arduino en la misma conexión: lo confirmado antes ya no vale
                    current.hardware, current.hardwareAt, current.idSeen = parsed, now, True
                elif isinstance(parsed, Notice):
                    self.notice = parsed
                elif isinstance(parsed, PpgChunk):
                    session = self.session
                    chunkAt = now - ageMs / 1000.0
                    # Solo lo posterior al inicio de la sesión en curso (nada anterior se mezcla con esta medición).
                    if session is not None and session.idMedicion is not None and chunkAt >= session.startedAt:
                        if session.addPpg(parsed, chunkAt):
                            events.append({"tipo": "ppg"})
                elif isinstance(parsed, Reading):
                    reading = Reading(**{**parsed.__dict__, "at": now - ageMs / 1000.0,
                                         "when": datetime.now(timezone.utc) - timedelta(milliseconds=ageMs)})
                    if self.latest is None or reading.at >= self.latest.at:
                        self.latest = reading
                    self.readingsReceived += 1
                    result.accepted += 1
                    session = self.session
                    if session is not None and session.idMedicion is not None and reading.at >= session.startedAt:
                        session.readings.append(reading)
                    events.append({"tipo": "lectura", **reading.asDict()})
            if stopped:
                current.lastBeat = now - BRIDGE_STALE_SECONDS - 1
                if current.pending is not None and current.pending["accion"] == "DETENER":
                    current.lastResult = {"id": current.pending["id"], "ok": True, "mensaje": "El puente se detuvo."}
                    current.pending = None
                events.append({"tipo": "puente", "activo": False})
            if previousState != linkState or stopped:
                events.append({"tipo": "conexion", "estado": self.deviceState()})
        for event in events:
            self._emit(event)
        return result

    # -- órdenes al puente ---------------------------------------------------------------------------------------------

    def requestCommand(self, userId: Any, action: str, port: str | None = None, medium: str | None = None) -> dict:
        """Deja UNA orden pendiente que el puente toma en su próximo latido. Reglas (el backend nunca ejecuta nada local):
        solo acciones de COMMAND_ACTIONS; el puente debe estar activo; CONFIGURAR solo con un puerto que el propio puente
        informó y un medio USB/BLUETOOTH; nada que interrumpa una sesión de medición en curso (propia o ajena). Solo da órdenes la cuenta que
        tiene el control del dispositivo (su reserva): una orden nunca toma el control por su cuenta (DEC-01)."""
        with self.lock:
            self.expireSession()
            bridge = self.bridge
            if action not in COMMAND_ACTIONS:
                raise CommandRejected("COMANDO_INVALIDO", "Acción no permitida.")
            if bridge is None or self.deviceState() == "SIN_PUENTE":
                raise CommandRejected("PUENTE_NO_ACTIVO", "El puente de GlucoLume no está ejecutándose: no hay a quién enviarle la orden.")
            if self.session is None:
                raise CommandRejected("CONTROL_REQUERIDO", CONTROL_REQUIRED_MESSAGE)
            if self.session.userId != userId:
                raise CommandRejected("DISPOSITIVO_EN_USO", BUSY_MESSAGE)
            if self.session.idMedicion is not None and action != "REANUDAR":
                raise CommandRejected("SESION_EN_CURSO", "Tenés una sesión de medición en curso: guardala o cancelala antes.")
            chosen = None
            if action == "CONFIGURAR":
                known = {(p["puerto"] or "").lower(): p for p in (bridge.ports or [])}
                if medium not in COMMAND_MEDIA:
                    raise CommandRejected("MEDIO_INVALIDO", "El medio debe ser USB, BLUETOOTH o AUTO.")
                if medium == "AUTO":  # el puente elige el puerto solo: no se admite uno fijo
                    if port is not None:
                        raise CommandRejected("COMANDO_INVALIDO", "El modo automático no admite un puerto fijo.")
                else:
                    chosen = known.get((port or "").strip().lower())
                    if chosen is None:
                        raise CommandRejected("PUERTO_NO_DISPONIBLE", "Ese puerto no figura entre los que ve el puente en su equipo.")
            elif port is not None or medium is not None:
                raise CommandRejected("COMANDO_INVALIDO", "Esta acción no admite puerto ni medio.")
            if bridge.pending is not None:
                raise CommandRejected("COMANDO_PENDIENTE", "Hay otra orden esperando al puente: aguardá unos segundos.")
            bridge.pending = {"id": uuid.uuid4().hex[:12], "accion": action,
                              "puerto": chosen["puerto"] if chosen else None, "medio": medium if action == "CONFIGURAR" else None}
            if self.session.idMedicion is None:  # una orden es una acción explícita de quien controla: renueva su control sin medición
                self.session.startedAt = self.session.lastSeen = self.clock()
            bridge.lastResult = None
            pending = dict(bridge.pending)
        self._emit({"tipo": "puente", "activo": True})
        return pending

    # -- sesión de medición --------------------------------------------------------------------------------------------

    def expireSession(self) -> None:
        """Libera una sesión vencida o abandonada. Nunca toca una que se está guardando ni una cuyo dueño sigue consultando."""
        with self.lock:
            session, now = self.session, self.clock()
            if session is None or session.saving:
                return
            measuring = session.idMedicion is not None
            maxAge, idle = (SESSION_MAX_SECONDS, ABANDON_SECONDS) if measuring else (PREVIEW_MAX_SECONDS, RESERVATION_SECONDS)
            reason = ("EXPIRADA" if now - session.startedAt > maxAge
                      else "ABANDONADA" if now - session.lastSeen > idle else None)
            if reason is None:
                return
            session.reason = reason
            self.session = None
            if session.idMedicion is not None:
                self.expired.append(session)
            self._emit({"tipo": "sesion", "activa": False, "motivo": reason})

    def takeExpired(self) -> list[Session]:
        with self.lock:
            taken, self.expired = self.expired, []
            return taken

    def touch(self, userId: Any) -> None:
        """El dueño de la sesión sigue ahí (consultó el estado)."""
        with self.lock:
            if self.session is not None and self.session.userId == userId:
                self.session.lastSeen = self.clock()

    def reserve(self, userId: Any) -> Session:
        """Reserva el dispositivo para `userId` (aún sin medición). Idempotente para el mismo usuario."""
        with self.lock:
            self.expireSession()
            if self.session is not None:
                if self.session.userId != userId:
                    raise PermissionError(BUSY_MESSAGE)
                if self.session.idMedicion is not None:
                    raise ValueError("Ya hay una sesión de medición en curso.")
                self.session.startedAt = self.session.lastSeen = self.clock()  # volver a tomarlo es una acción explícita: renueva el plazo
                return self.session
            self.session = Session(userId=userId, startedAt=self.clock(), lastSeen=self.clock())
            return self.session

    def bind(self, session: Session, idMedicion: Any, deviceCode: str, mode: str = "OXIMETRIA") -> None:
        with self.lock:
            session.idMedicion, session.deviceCode, session.modo = idMedicion, deviceCode, mode
            session.startedAt = session.lastSeen = self.clock()
            session.readings.clear()
        self._emit({"tipo": "sesion", "activa": True})

    def release(self, session: Session | None = None) -> None:
        with self.lock:
            if self.session is not None and (session is None or self.session is session):
                self.session = None
        self._emit({"tipo": "sesion", "activa": False})

    def canView(self, userId: Any) -> bool:
        """Las señales en vivo (valores y PPG) solo las ve quien controla el dispositivo; con el equipo libre no las ve nadie (DEC-01)."""
        with self.lock:
            return self.session is not None and self.session.userId == userId

    def diagnosticReading(self) -> dict | None:
        """Antigüedad de la última lectura y si había un dedo, sin ningún valor: alcanza para el diagnóstico «¿qué falta para medir?»."""
        with self.lock:
            if self.latest is None or self.deviceState() != "CONECTADO":
                return None
            return {"edadSegundos": round(max(0.0, self.clock() - self.latest.at), 1), "dedo": self.latest.dedo}

    def stability(self) -> Stable | Unstable:
        with self.lock:
            session = self.session
            return evaluateStability(list(session.readings) if session else [], self.clock(),
                                     requireGlucose=bool(session and session.modo == "GLUCOSA_EXPERIMENTAL"))

    # -- consulta y eventos --------------------------------------------------------------------------------------------

    def snapshot(self, viewerId: Any) -> dict:
        with self.lock:
            self.touch(viewerId)  # consultar el estado es la señal de que el dueño sigue activo
            self.expireSession()
            now, bridge, session = self.clock(), self.bridge, self.session
            state = self.deviceState()
            busy = session is not None and session.userId != viewerId
            controlling = session is not None and session.userId == viewerId
            latest = self.latest if (controlling and state == "CONECTADO") else None  # valores solo para quien controla (DEC-01)
            age = round(max(0.0, now - self.latest.at), 1) if (self.latest is not None and state == "CONECTADO") else None
            stability = None
            if session is not None and not busy and session.idMedicion is not None:
                verdict = evaluateStability(list(session.readings), now, requireGlucose=session.modo == "GLUCOSA_EXPERIMENTAL")
                stability = ({"estable": True, "motivo": None, "mensaje": None, "lecturasValidas": verdict.lecturas}
                             if isinstance(verdict, Stable)
                             else {"estable": False, "motivo": verdict.code, "mensaje": verdict.message, "lecturasValidas": verdict.valid})
                stability["lecturasRequeridas"] = STABLE_READINGS
            return {
                "estado": state, "ocupado": busy, "controlPropio": controlling, "edadUltimaLectura": age,
                "puente": None if bridge is None or state == "SIN_PUENTE" else {
                    "puerto": None if busy else bridge.port, "medio": bridge.medium, "baudios": bridge.baud,
                    "codigoDispositivo": self.effectiveCode() or bridge.deviceCode, "identidad": self.identity()["nivel"],
                    "estadoEnlace": bridge.linkState, "reintento": bridge.attempt,
                    "ultimoError": None if busy else bridge.error, "codigoError": None if busy else bridge.errorCode,
                    "versionPuente": bridge.version,
                    "puertosDisponibles": None if busy else bridge.ports,
                    "comandoPendiente": None if busy or bridge.pending is None else bridge.pending["accion"],
                    "ultimoComando": None if busy else bridge.lastResult},
                "lectura": None if latest is None else {**latest.asDict(), "edadSegundos": round(max(0.0, now - latest.at), 1)},
                "avisoDispositivo": None if busy or self.notice is None else {"texto": self.notice.text, "error": self.notice.error},
                "lineasInvalidas": self.invalidLines, "lecturasRecibidas": self.readingsReceived,
                "sesion": None if session is None or busy or session.idMedicion is None else {
                    "idMedicion": str(session.idMedicion), "iniciada": session.since.isoformat(), "enlacePerdido": session.linkLost,
                    "estabilidad": stability, "ppg": self._ppgSnapshot(session, now), "modo": session.modo},
            }

    @staticmethod
    def _ppgSnapshot(session: Session, now: float) -> dict | None:
        """Ventana deslizante de la señal PPG de la sesión (índices absolutos para que la pantalla desplace sin saltos)."""
        if session.ppgSeq is None:
            return None
        start = session.ppgNext - len(session.ppg)
        return {"hz": PPG_HZ, "inicio": start, "valores": list(session.ppg),
                "latidos": [index for index in session.ppgBeats if index >= start],
                "edadSegundos": round(max(0.0, now - (session.ppgAt or now)), 1)}

    def subscribe(self, userId: Any) -> queue.Queue:
        channel: queue.Queue = queue.Queue(maxsize=500)
        with self.lock:
            self.subscribers.append((channel, userId))
        return channel

    def unsubscribe(self, channel: queue.Queue) -> None:
        with self.lock:
            self.subscribers = [(c, u) for c, u in self.subscribers if c is not channel]

    def _emit(self, event: dict) -> None:
        event = {**event, "id": uuid.uuid4().hex[:8]}
        with self.lock:
            targets = list(self.subscribers)
            for channel, userId in targets:
                # Las lecturas con valores solo van a quien puede verlas (sin sesión ajena activa).
                if event["tipo"] in ("lectura", "ppg") and not self.canView(userId):
                    continue
                try:
                    channel.put_nowait(event)
                except queue.Full:
                    pass  # un cliente lento no frena la recepción


hub = TelemetryHub()
