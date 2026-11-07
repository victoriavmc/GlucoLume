#!/usr/bin/env python3
"""Medición de coste de Argon2id en el login (M-3, auditoría 07/11/2026). Solo local, sin base de datos.

Uso (desde la raíz del repo, con el entorno del backend):
    python docs/auditorias/evidencias/auditoria_seguridad_2026-11-07/bench_argon2.py all

Secciones:
  coste      tiempo de hash/verificación (mediana de 5), CPU frente a reloj (¿usa varios hilos?)
  longitud   tiempo de verificar una contraseña errónea de 8 a 100 000 caracteres
  concurrencia  k verificaciones simultáneas (k=1,2,4,8,16): latencia p50/p95, pico de memoria y códigos de error (proceso aparte por k)
  loop       máximo retraso del event loop de asyncio mientras k verificaciones corren en hilos

Usa las funciones REALES de app.core.security: si se agrega un control de concurrencia allí, esta medición lo incluye.
No hace fuerza bruta: son unas pocas verificaciones controladas en la máquina de prueba.
"""

import asyncio
import json
import os
import resource
import subprocess
import sys
import threading
import time
from pathlib import Path
from statistics import median

BACKEND = Path(__file__).resolve().parents[4] / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("GLUCOLUME_ENV_FILE", str(BACKEND / "tests" / "test.env"))

from app.core import security  # noqa: E402

PASSWORD = "Glucolume#Prueba2026"
HASH = security.hashPassword(PASSWORD)


def percentile(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def coste():
    timings, cpu = [], []
    for _ in range(5):
        t0, c0 = time.perf_counter(), time.process_time()
        security.verifyPassword(PASSWORD, HASH)
        timings.append((time.perf_counter() - t0) * 1000)
        cpu.append((time.process_time() - c0) * 1000)
    return {
        "verificacion_ms_mediana": round(median(timings), 1),
        "cpu_ms_mediana": round(median(cpu), 1),
        "ratio_cpu_sobre_reloj": round(median(cpu) / median(timings), 2),
    }


def longitud():
    resultados = {}
    for n in (8, 128, 256, 4000, 100_000):
        tiempos = []
        for _ in range(3):
            t0 = time.perf_counter()
            valid, _ = security.verifyPassword("A" * n, HASH)
            tiempos.append((time.perf_counter() - t0) * 1000)
            assert valid is False
        resultados[str(n)] = round(median(tiempos), 1)
    return resultados


def concurrencia(k: int, operaciones_por_hilo: int = 2):
    """k hilos verifican a la vez, cada uno `operaciones_por_hilo` veces. Corre en un proceso propio para medir su pico de memoria."""
    latencias, errores = [], []
    lock = threading.Lock()
    barrera = threading.Barrier(k)

    def trabajo():
        barrera.wait()
        for _ in range(operaciones_por_hilo):
            t0 = time.perf_counter()
            try:
                security.verifyPassword(PASSWORD, HASH)
            except Exception as error:  # noqa: BLE001 - se reporta, no se oculta
                with lock:
                    errores.append(getattr(error, "code", type(error).__name__))
                continue
            with lock:
                latencias.append((time.perf_counter() - t0) * 1000)

    hilos = [threading.Thread(target=trabajo) for _ in range(k)]
    t0 = time.perf_counter()
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    wall = (time.perf_counter() - t0) * 1000
    return {
        "k": k,
        "ops": len(latencias),
        "errores": errores,
        "pared_ms": round(wall, 1),
        "latencia_p50_ms": round(percentile(latencias, 0.5), 1) if latencias else None,
        "latencia_p95_ms": round(percentile(latencias, 0.95), 1) if latencias else None,
        "pico_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
    }


def concurrencia_driver():
    resultados = []
    for k in (1, 2, 4, 8, 16):
        salida = subprocess.run([sys.executable, __file__, "concurrencia-un-caso", str(k)], capture_output=True, text=True, check=True)
        resultados.append(json.loads(salida.stdout.strip().splitlines()[-1]))
    return resultados


async def loop_lag(k: int):
    """Retraso máximo del event loop (tic cada 2 ms) mientras k verificaciones corren en hilos (como el threadpool de FastAPI)."""
    marcas = []
    parar = asyncio.Event()

    async def tic():
        while not parar.is_set():
            t0 = time.perf_counter()
            await asyncio.sleep(0.002)
            marcas.append((time.perf_counter() - t0) * 1000 - 2)

    tarea = asyncio.create_task(tic())
    await asyncio.gather(*(asyncio.to_thread(security.verifyPassword, PASSWORD, HASH) for _ in range(k)))
    parar.set()
    await tarea
    return {"k": k, "retraso_max_ms": round(max(marcas), 1), "retraso_p95_ms": round(percentile(marcas, 0.95), 1)}


def main(seccion: str):
    if seccion == "concurrencia-un-caso":
        print(json.dumps(concurrencia(int(sys.argv[2]))))
        return
    salida = {}
    if seccion in ("coste", "all"):
        salida["coste"] = coste()
    if seccion in ("longitud", "all"):
        salida["longitud_ms_por_tamano_de_contrasena"] = longitud()
    if seccion in ("concurrencia", "all"):
        salida["concurrencia"] = concurrencia_driver()
    if seccion in ("loop", "all"):
        salida["loop"] = [asyncio.run(loop_lag(k)) for k in (1, 8)]
    print(json.dumps(salida, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
