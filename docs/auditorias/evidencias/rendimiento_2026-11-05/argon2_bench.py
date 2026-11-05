# Costo de CPU y memoria del hash de contraseñas (Argon2id, parámetros del código: m=64 MiB, t=3, p=4). Entorno de laboratorio.
import _env  # noqa: F401
import json, statistics, subprocess, sys, threading, time
from app.core import security

def pct(vals, p):
    s = sorted(vals); k = (len(s) - 1) * p; lo = int(k); hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)

def child(k):
    """Un proceso por nivel de concurrencia: pico de RSS real (VmHWM) y tiempo de pared."""
    stored = security.hashPassword("Clave-de-prueba-1!")
    barrier = threading.Barrier(k)
    times = []
    def work():
        barrier.wait()
        t = time.perf_counter(); security.verifyPassword("Clave-de-prueba-2!", stored); times.append((time.perf_counter() - t) * 1000)
    threads = [threading.Thread(target=work) for _ in range(k)]
    t0 = time.perf_counter()
    [t.start() for t in threads]; [t.join() for t in threads]
    wall = (time.perf_counter() - t0) * 1000
    hwm = [l for l in open("/proc/self/status") if l.startswith("VmHWM")][0].split()[1]
    print(json.dumps({"k": k, "wallMs": round(wall, 1), "perVerifyMsP50": round(pct(times, 0.5), 1),
                      "perVerifyMsP95": round(pct(times, 0.95), 1), "peakRssMB": round(int(hwm) / 1024, 1)}))

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "child":
        child(int(sys.argv[2])); sys.exit(0)
    # 1) Un solo hilo: hash y verificación (30 repeticiones) y el patrón de «cambiar contraseña» (vigente + 3 del historial + hash nuevo).
    hashes, verifies = [], []
    for _ in range(30):
        t = time.perf_counter(); h = security.hashPassword("Clave-de-prueba-1!"); hashes.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter(); security.verifyPassword("Clave-de-prueba-1!", h); verifies.append((time.perf_counter() - t) * 1000)
    stored = [security.hashPassword(f"Vieja-{i}-x!") for i in range(3)]
    changes = []
    for _ in range(15):
        t = time.perf_counter()
        security.verifyPassword("Nueva-clave-9!", stored[0])
        for h in stored:
            security.verifyPassword("Nueva-clave-9!", h)
        security.hashPassword("Nueva-clave-9!")
        changes.append((time.perf_counter() - t) * 1000)
    print(json.dumps({"hashMs": {"p50": round(pct(hashes, .5), 1), "p95": round(pct(hashes, .95), 1)},
                      "verifyMs": {"p50": round(pct(verifies, .5), 1), "p95": round(pct(verifies, .95), 1)},
                      "cambioContrasenaMs": {"p50": round(pct(changes, .5), 1), "p95": round(pct(changes, .95), 1), "n": len(changes),
                                             "verificacionesArgon2": 5}}))
    # 2) Concurrencia: procesos separados (pico de memoria limpio).
    for k in (1, 2, 4, 8):
        out = subprocess.run([sys.executable, __file__, "child", str(k)], capture_output=True, text=True, timeout=600)
        print(out.stdout.strip() or out.stderr[-300:])
