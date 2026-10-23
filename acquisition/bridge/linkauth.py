"""LinkAuth - Autenticación de las líneas que envía el firmware (H-05).

El enlace Bluetooth clásico (HC-05/HC-06) no autentica quién envía ni protege lo enviado: quien esté al alcance podría falsificar lecturas, repetir
líneas viejas o reordenarlas. Con una clave por dispositivo (BRIDGE_DEVICE_KEY, 128 bits, nunca en el repositorio) cada línea del firmware lleva una
etiqueta y el puente descarta lo que no verifica:

    <línea original>*<arranque>.<contador>.<etiqueta de 16 hexadecimales>

  - etiqueta = SipHash-2-4(clave, "GL1|<arranque>.<contador>|<línea original>") en 64 bits. Autentica e impide modificar la línea; NO cifra: las
    lecturas siguen viajando en claro (la confidencialidad del enlace Bluetooth clásico queda sin resolver). Es la misma función que compila el
    firmware (firmware/*/GlucoLumeSipHash.h); las pruebas comprueban que ambas dan la misma etiqueta.
  - <arranque> es un contador que el Arduino guarda en su EEPROM y sube en cada reinicio; <contador> cuenta líneas desde ese arranque. Una línea solo
    se acepta si (arranque, contador) es MAYOR que el de la última aceptada: repetir o reordenar líneas capturadas falla (REPETIDA). El último valor
    aceptado se guarda en un archivo local para que reiniciar el puente no reabra la ventana de repetición.

Qué NO resuelve (ver docs/SEGURIDAD.md): quien capture y bloquee líneas reales puede entregarlas más tarde, una sola vez y en orden (llegan retrasadas, pero
auténticas); la clave vive en claro en el bridge.env y en la EEPROM del Arduino (quien tenga el equipo o el USB la obtiene); no hay confidencialidad.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("glucolume.bridge.auth")

MASK64 = (1 << 64) - 1
KEY_HEX_LENGTH = 32
LINE_PATTERN = re.compile(r"^(?P<payload>.*)\*(?P<boot>\d{1,10})\.(?P<counter>\d{1,10})\.(?P<tag>[0-9a-f]{16})$", re.S)
REASON_UNSIGNED, REASON_BAD_TAG, REASON_REPLAY = "SIN_FIRMA", "FIRMA_INVALIDA", "REPETIDA"
LOG_EVERY_SECONDS = 30.0


class KeyError_(ValueError):
    """Clave de dispositivo inválida (formato)."""


def parseKey(text: str) -> bytes:
    """32 caracteres hexadecimales (128 bits). Se rechazan formatos erróneos y claves triviales (todo igual); la entropía no se puede comprobar."""
    text = (text or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{%d}" % KEY_HEX_LENGTH, text):
        raise KeyError_(f"BRIDGE_DEVICE_KEY debe tener exactamente {KEY_HEX_LENGTH} caracteres hexadecimales (128 bits).")
    key = bytes.fromhex(text)
    if len(set(key)) < 4:
        raise KeyError_("BRIDGE_DEVICE_KEY es demasiado regular: generá una aleatoria (python -c \"import secrets; print(secrets.token_hex(16))\").")
    return key


def _rotl(value: int, bits: int) -> int:
    return ((value << bits) | (value >> (64 - bits))) & MASK64


def siphash24(key: bytes, data: bytes) -> int:
    """SipHash-2-4 con clave de 128 bits (Aumasson y Bernstein). Vectores oficiales en tests/test_link_auth.py."""
    if len(key) != 16:
        raise ValueError("La clave de SipHash tiene 16 bytes.")
    k0, k1 = int.from_bytes(key[:8], "little"), int.from_bytes(key[8:], "little")
    v = [k0 ^ 0x736F6D6570736575, k1 ^ 0x646F72616E646F6D, k0 ^ 0x6C7967656E657261, k1 ^ 0x7465646279746573]

    def rounds(count: int) -> None:
        for _ in range(count):
            v[0] = (v[0] + v[1]) & MASK64
            v[1] = _rotl(v[1], 13) ^ v[0]
            v[0] = _rotl(v[0], 32)
            v[2] = (v[2] + v[3]) & MASK64
            v[3] = _rotl(v[3], 16) ^ v[2]
            v[0] = (v[0] + v[3]) & MASK64
            v[3] = _rotl(v[3], 21) ^ v[0]
            v[2] = (v[2] + v[1]) & MASK64
            v[1] = _rotl(v[1], 17) ^ v[2]
            v[2] = _rotl(v[2], 32)

    whole = len(data) - len(data) % 8
    for offset in range(0, whole, 8):
        word = int.from_bytes(data[offset:offset + 8], "little")
        v[3] ^= word
        rounds(2)
        v[0] ^= word
    last = (len(data) & 0xFF) << 56 | int.from_bytes(data[whole:], "little")
    v[3] ^= last
    rounds(2)
    v[0] ^= last
    v[2] ^= 0xFF
    rounds(4)
    return v[0] ^ v[1] ^ v[2] ^ v[3]


def tagFor(key: bytes, boot: int, counter: int, payload: str) -> str:
    return f"{siphash24(key, f'GL1|{boot}.{counter}|{payload}'.encode('ascii', errors='strict')):016x}"


def sign(key: bytes, boot: int, counter: int, payload: str) -> str:
    """Lo que escribe el firmware: la línea original más su firma. Se usa en las pruebas para simular un Arduino con clave."""
    return f"{payload}*{boot}.{counter}.{tagFor(key, boot, counter, payload)}"


@dataclass(frozen=True)
class Verdict:
    payload: str | None
    reason: str | None


class LineAuthenticator:
    """Verifica y quita la firma de cada línea. Hilo único (el lector serie). Con `statePath` recuerda el último (arranque, contador) aceptado."""

    def __init__(self, key: bytes, statePath: Path | None = None, saveInterval: float = 5.0, clock=time.monotonic) -> None:
        self.key, self.statePath, self.saveInterval, self.clock = key, statePath, saveInterval, clock
        self.accepted = 0
        self.rejected: dict[str, int] = {REASON_UNSIGNED: 0, REASON_BAD_TAG: 0, REASON_REPLAY: 0}
        self.last: tuple[int, int] = self._load()
        self._lastSave = clock()
        self._dirty = False
        self._lastLog: dict[str, float] = {}

    def _load(self) -> tuple[int, int]:
        if self.statePath is None:
            return (-1, -1)
        try:
            data = json.loads(self.statePath.read_text(encoding="utf-8"))
            return (int(data["boot"]), int(data["counter"]))
        except FileNotFoundError:
            return (-1, -1)
        except (OSError, ValueError, KeyError, TypeError):
            log.warning("El estado de la autenticación del enlace no se pudo leer: se empieza sin memoria (primera línea válida).")
            return (-1, -1)

    def flush(self) -> None:
        """Guarda el último (arranque, contador) aceptado. Escritura atómica; un fallo se informa y no detiene el puente."""
        if self.statePath is None or not self._dirty:
            return
        try:
            self.statePath.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.statePath.with_suffix(".tmp")
            temporary.write_text(json.dumps({"boot": self.last[0], "counter": self.last[1]}), encoding="utf-8")
            os.replace(temporary, self.statePath)
            self._dirty = False
        except OSError as error:
            log.warning("No se pudo guardar el estado de la autenticación del enlace: %s", type(error).__name__)
        self._lastSave = self.clock()

    def reset(self) -> None:
        """Olvida el último valor aceptado (p. ej. tras reprovisionar el Arduino, cuyo contador de arranques vuelve a empezar)."""
        self.last = (-1, -1)
        self._dirty = True
        self.flush()

    def verify(self, text: str) -> Verdict:
        match = LINE_PATTERN.match(text)
        if match is None:
            return self._reject(REASON_UNSIGNED)
        boot, counter, payload = int(match["boot"]), int(match["counter"]), match["payload"]
        try:
            expected = tagFor(self.key, boot, counter, payload)
        except UnicodeEncodeError:
            return self._reject(REASON_BAD_TAG)
        if not hmac.compare_digest(expected, match["tag"]):
            return self._reject(REASON_BAD_TAG)
        if (boot, counter) <= self.last:
            return self._reject(REASON_REPLAY)
        self.last = (boot, counter)
        self.accepted += 1
        self._dirty = True
        if self.clock() - self._lastSave >= self.saveInterval:
            self.flush()
        return Verdict(payload, None)

    def _reject(self, reason: str) -> Verdict:
        self.rejected[reason] += 1
        now = self.clock()
        if now - self._lastLog.get(reason, float("-inf")) >= LOG_EVERY_SECONDS:
            self._lastLog[reason] = now
            log.warning("Línea del dispositivo descartada (%s); descartadas hasta ahora: %s. No se registra su contenido.", reason, dict(self.rejected))
        return Verdict(None, reason)

    def summary(self) -> dict:
        return {"aceptadas": self.accepted, "descartadas": dict(self.rejected), "ultimo": {"arranque": self.last[0], "contador": self.last[1]}}
