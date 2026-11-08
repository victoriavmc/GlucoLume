# Medición de M-3 en el banco: ráfagas simultáneas de verificaciones Argon2 reales con el control de concurrencia activo.
# Mide: cuántas pasan, cuántas reciben SERVIDOR_OCUPADO (503), latencia de las que pasan, y la recuperación posterior.
import os, sys, threading, time, statistics, json
# Ruta relativa a la raíz del repo (esta carpeta está en docs/auditorias/evidencias/...): sirve en cualquier copia del repositorio.
RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
BACKEND = os.path.join(RAIZ, "backend")
os.environ["GLUCOLUME_ENV_FILE"] = os.path.join(BACKEND, "tests", "test.env")  # configuración sintética de pruebas
sys.path.insert(0, BACKEND)
from app.core import security
from app.core.exceptions import AuthError

PW = "Clave#Prueba2026"
H = security.hashPassword(PW)

def una_vez():
    t = time.perf_counter()
    valido, _ = security.verifyPassword(PW, H)
    assert valido
    return time.perf_counter() - t

ref = [una_vez() for _ in range(3)]
print(json.dumps({"verificacion_secuencial_s": [round(x, 3) for x in ref], "mediana_s": round(statistics.median(ref), 3),
                  "ARGON2_MAX_CONCURRENT": security._argonSlots._initial_value, "MAX_WAITING": 8, "WAIT_S": security.ARGON2_WAIT_SECONDS}))

def rafaga(n):
    barrera = threading.Barrier(n)
    resultados = []
    lock = threading.Lock()
    def worker():
        barrera.wait()
        t = time.perf_counter()
        try:
            security.verifyPassword(PW, H)
            r = ("ok", time.perf_counter() - t)
        except AuthError as e:
            r = (e.code, time.perf_counter() - t, e.retryAfterSeconds)
        with lock:
            resultados.append(r)
    hilos = [threading.Thread(target=worker) for _ in range(n)]
    for h in hilos: h.start()
    for h in hilos: h.join()
    oks = [r[1] for r in resultados if r[0] == "ok"]
    busy = [r for r in resultados if r[0] == "SERVIDOR_OCUPADO"]
    return {"n": n, "ok": len(oks), "503": len(busy),
            "latencia_ok_p50_s": round(statistics.median(oks), 3) if oks else None,
            "latencia_ok_max_s": round(max(oks), 3) if oks else None,
            "retry_after_503": sorted({r[2] for r in busy}) if busy else None,
            "otros": [r[0] for r in resultados if r[0] not in ("ok", "SERVIDOR_OCUPADO")]}

for n in [1, 2, 4, 8, 10, 12, 16, 24]:
    print(json.dumps(rafaga(n)))
    # Recuperación: tras cada ráfaga, el control debe quedar libre.
    espera_libre = security._argonWaiting
    print(json.dumps({"tras_rafaga_en_espera": espera_libre, "verificacion_posterior_s": round(una_vez(), 3)}))
