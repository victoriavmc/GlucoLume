"""Medición local: verificación Argon2id (parámetros reales de app/core/security.py) con concurrencia creciente.

Mide latencia por operación (p50/p95), throughput y pico de RSS del proceso. No usa base de datos ni red.
Se ejecuta desde backend/ con el Python de la venv de requirements.txt.
"""
import json
import resource
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, ".")
from app.core import security  # noqa: E402

PASSWORD = "Contrasena-de-prueba-1"
HASH = security.hashPassword(PASSWORD)
REPS_PER_WORKER = 4


def rss_mb() -> float:
    # ru_maxrss en KiB (Linux): pico histórico del proceso.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def run(concurrency: int) -> dict:
    latencies: list[float] = []
    lock = threading.Lock()

    def one(_):
        t0 = time.perf_counter()
        ok = security.verifyPassword(PASSWORD, HASH)[0]
        dt = (time.perf_counter() - t0) * 1000
        assert ok
        with lock:
            latencies.append(dt)

    total = concurrency * REPS_PER_WORKER
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(one, range(total)))
    wall = time.perf_counter() - start
    latencies.sort()
    p95 = latencies[min(len(latencies) - 1, int(round(0.95 * (len(latencies) - 1))))]
    return {
        "concurrencia": concurrency,
        "operaciones": total,
        "p50_ms": round(statistics.median(latencies), 1),
        "p95_ms": round(p95, 1),
        "max_ms": round(latencies[-1], 1),
        "throughput_ops_s": round(total / wall, 2),
        "rss_pico_mb": round(rss_mb(), 1),
    }


if __name__ == "__main__":
    base = rss_mb()
    results = {"rss_inicial_mb": round(base, 1), "parametros": "m=64MiB,t=3,p=4 (security.py)", "escenarios": []}
    for c in [1, 2, 4, 8, 16, 32]:
        results["escenarios"].append(run(c))
        print(json.dumps(results["escenarios"][-1]), flush=True)
    print(json.dumps(results, ensure_ascii=False, indent=2))
