# Señal PPG sintética SOLO para probar el algoritmo y la canalización en las pruebas automáticas (nunca se usa en la
# aplicación): onda pulsátil con frecuencia cardíaca y razón R conocidas, más un ruido determinista.

import math
import random


def ppgSamples(heartRate=72.0, spo2=97.0, seconds=20.0, rate=20.0, dcIr=120000, dcRed=100000, noise=0.0004, seed=7,
               finger=True, startIndex=0):
    """Lista de (numeroMuestra, tiempoRelativoMs, red, ir). R = (110 - spo2) / 25 fija la razón de modulaciones."""
    rng = random.Random(seed)
    ratio = (110.0 - spo2) / 25.0
    modIr = 0.012
    modRed = modIr * ratio
    freq = heartRate / 60.0
    out = []
    for i in range(int(seconds * rate)):
        t = i / rate
        wave = math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(4 * math.pi * freq * t + 0.6)
        scale = 1.0 if finger else 0.01
        ir = dcIr * scale * (1 + modIr * wave + rng.gauss(0, noise))
        red = dcRed * scale * (1 + modRed * wave + rng.gauss(0, noise))
        out.append((startIndex + i, int(round(t * 1000)), int(red), int(ir)))
    return out
