# Oximetry - SpO₂ y frecuencia cardíaca calculadas por el servidor sobre las muestras RED/IR guardadas en MuestraSensor
#
# Es el único origen de estos resultados: ni el cliente ni el dispositivo los informan. Sin señal suficiente o de
# calidad aceptable no se devuelve ningún valor (la medición queda INVALIDA con el motivo).
#
# Método (PPG reflectivo, MAX30100/MAX30102):
#   - Componente continua (DC): media móvil de ~1,5 s de cada canal; alterna (AC): señal - DC, suavizada.
#   - Frecuencia cardíaca: autocorrelación del AC infrarrojo (independiente de la polaridad de la señal) buscando el
#     primer máximo en el rango fisiológico 40-200 lpm; la altura de ese máximo es el índice de calidad (0-1).
#   - SpO₂: razón de razones R = (AC_rojo/DC_rojo) / (AC_IR/DC_IR) y la recta empírica SpO₂ = 110 - 25·R, de uso común en
#     oxímetros de referencia de bajo costo. NO es una calibración clínica: el prototipo es experimental y estos valores
#     no son un resultado médico validado.
#
# Python puro (sin dependencias nuevas).

import math
from dataclasses import dataclass

VERSION = "oximetria-ppg-v1"
MIN_SECONDS = 10.0  # ventana útil mínima para una medición válida
SETTLE_SECONDS = 2.0  # se descarta el arranque (asentamiento del LED y del dedo)
MIN_IR_DC = 3000  # por debajo se considera que no hay dedo sobre el sensor
SATURATION = {16: 65535, 18: 262143}
MIN_QUALITY = 0.5
MIN_PERFUSION = 0.0005  # AC/DC infrarrojo mínimo


@dataclass(frozen=True)
class OximetryResult:
    ok: bool
    spo2: float | None = None
    heartRate: int | None = None
    quality: float | None = None
    reason: str | None = None
    sampleRate: float | None = None
    version: str = VERSION


def _fail(reason: str, rate: float | None = None, quality: float | None = None) -> OximetryResult:
    return OximetryResult(False, reason=reason, sampleRate=rate, quality=quality)


def _movingAverage(values: list[float], window: int) -> list[float]:
    """Media móvil centrada (los bordes usan la ventana disponible)."""
    n, half, out = len(values), window // 2, []
    prefix = [0.0]
    for value in values:
        prefix.append(prefix[-1] + value)
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        out.append((prefix[hi] - prefix[lo]) / (hi - lo))
    return out


def _ac(values: list[float], rate: float) -> tuple[list[float], float]:
    window = max(3, int(round(1.5 * rate)) | 1)
    dc = _movingAverage(values, window)
    ac = _movingAverage([v - d for v, d in zip(values, dc)], 3)
    return ac, sum(values) / len(values)


def _rms(values: list[float]) -> float:
    return math.sqrt(sum(v * v for v in values) / len(values))


def _heartRate(ac: list[float], rate: float) -> tuple[float, float] | None:
    """(lpm, calidad) por autocorrelación normalizada, o None si no hay periodicidad."""
    n = len(ac)
    energy = sum(v * v for v in ac)
    if energy <= 0:
        return None
    minLag, maxLag = int(math.floor(rate * 60 / 200)), int(math.ceil(rate * 60 / 40))
    maxLag = min(maxLag, n // 2)
    if maxLag <= minLag + 2:
        return None
    corr = {}
    for lag in range(max(1, minLag - 1), maxLag + 2):
        corr[lag] = sum(ac[i] * ac[i + lag] for i in range(n - lag)) / energy * (n / (n - lag))
    peaks = []
    for lag in range(max(1, minLag), maxLag + 1):
        value = corr.get(lag)
        if value is not None and corr.get(lag - 1) is not None and corr.get(lag + 1) is not None                 and value >= corr[lag - 1] and value >= corr[lag + 1] and value > 0:
            peaks.append((lag, value))
    if not peaks:
        return None
    top = max(value for _, value in peaks)
    # El primer máximo fuerte es el período fundamental; los múltiplos del período (subarmónicos) también correlacionan.
    bestLag, best = next((lag, value) for lag, value in peaks if value >= 0.8 * top)
    a, b, c = corr[bestLag - 1], corr[bestLag], corr[bestLag + 1]
    shift = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0  # interpolación parabólica
    return 60.0 * rate / (bestLag + shift), min(1.0, best)


def analyze(samples: list[tuple[int | None, int, int]], defaultRate: float | None = None, bits: int | None = None) -> OximetryResult:
    """`samples`: (tiempoRelativoMs | None, valorRed, valorIR) en orden de adquisición."""
    if len(samples) < 20:
        return _fail("Se recibieron muy pocas muestras para calcular SpO₂ y frecuencia cardíaca.")
    times = [s[0] for s in samples]
    if all(t is not None for t in times) and times[-1] > times[0] and all(b >= a for a, b in zip(times, times[1:])):
        rate = (len(samples) - 1) / ((times[-1] - times[0]) / 1000.0)
    elif defaultRate:
        rate = float(defaultRate)
    else:
        return _fail("Las muestras no traen tiempos ni frecuencia de muestreo: no se puede analizar la señal.")
    if not 5 <= rate <= 500:
        return _fail("La frecuencia de muestreo de la adquisición no es válida.", rate)

    skip = int(SETTLE_SECONDS * rate) if len(samples) / rate > MIN_SECONDS + SETTLE_SECONDS else 0
    window = samples[skip:]
    if len(window) / rate < MIN_SECONDS:
        return _fail(f"La adquisición fue demasiado corta: se necesitan al menos {int(MIN_SECONDS)} s de señal estable.", rate)
    red = [float(s[1]) for s in window]
    ir = [float(s[2]) for s in window]

    if sum(ir) / len(ir) < MIN_IR_DC:
        return _fail("No se detectó un dedo sobre el sensor (señal infrarroja demasiado baja).", rate)
    limit = SATURATION.get(bits) or (SATURATION[16] if max(ir + red) <= SATURATION[16] else SATURATION[18])
    if sum(1 for v in ir + red if v >= limit) / (2 * len(ir)) > 0.02:
        return _fail("La señal del sensor está saturada: reducí la presión o la luz ambiente.", rate)

    acRed, dcRed = _ac(red, rate)
    acIr, dcIr = _ac(ir, rate)
    rmsIr, rmsRed = _rms(acIr), _rms(acRed)
    if dcIr <= 0 or dcRed <= 0 or rmsIr / dcIr < MIN_PERFUSION:
        return _fail("La señal pulsátil es demasiado débil.", rate)
    rate_hr = _heartRate(acIr, rate)
    if rate_hr is None:
        return _fail("No se encontró un pulso periódico en la señal.", rate)
    heart, quality = rate_hr
    if quality < MIN_QUALITY:
        return _fail("La calidad de la señal es insuficiente (movimiento o mal contacto).", rate, round(quality, 3))
    ratio = (rmsRed / dcRed) / (rmsIr / dcIr)
    spo2 = 110.0 - 25.0 * ratio
    if spo2 < 70.0 or spo2 > 110.0:
        return _fail("La relación entre los canales rojo e infrarrojo no es fisiológica.", rate, round(quality, 3))
    return OximetryResult(True, spo2=round(min(spo2, 100.0), 2), heartRate=int(round(heart)), quality=round(quality, 3),
                          sampleRate=round(rate, 2))
