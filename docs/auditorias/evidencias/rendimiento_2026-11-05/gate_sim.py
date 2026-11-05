# Simulación con el código REAL del tope de llamadas (app/db/gate.py: limitDriverCalls) sobre SQLite.
# Mide: (A) techo de consultas/s con y sin tope; (B) efecto de una consulta lenta sobre consultas rápidas.
# No representa SQL Server: el objetivo es medir el comportamiento del semáforo del código, no el motor real.
import _env  # noqa: F401
import os, statistics, sys, tempfile, threading, time, json
from sqlalchemy import create_engine, text
from app.db.gate import limitDriverCalls

def pct(vals, p):
    s = sorted(vals); k = (len(s) - 1) * p; lo = int(k); hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)

def engine(limit):
    path = os.path.join(tempfile.mkdtemp(prefix="gate-"), "g.db")
    e = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False}, pool_size=50, max_overflow=50)
    return limitDriverCalls(e, limit)

def calibrate(e, targetMs):
    with e.connect() as c:
        for n in (10_000, 50_000, 100_000, 200_000, 400_000, 2_000_000, 4_000_000, 8_000_000):
            t = time.perf_counter(); c.execute(text(f"WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c WHERE x<{n}) SELECT count(*) FROM c")).scalar()
            ms = (time.perf_counter() - t) * 1000
            if ms >= targetMs: return n, round(ms, 1)
    return 8_000_000, None

def query(e, n):
    t = time.perf_counter()
    with e.connect() as c:
        c.execute(text(f"WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c WHERE x<{n}) SELECT count(*) FROM c")).scalar()
    return (time.perf_counter() - t) * 1000

def throughput(limit, threads, perThread, n, e):
    lat = []; lock = threading.Lock()
    def work():
        for _ in range(perThread):
            ms = query(e, n)
            with lock: lat.append(ms)
    ts = [threading.Thread(target=work) for _ in range(threads)]
    t0 = time.perf_counter(); [t.start() for t in ts]; [t.join() for t in ts]
    wall = time.perf_counter() - t0
    return {"limite": limit, "hilos": threads, "consultas": len(lat), "consultasPorS": round(len(lat) / wall, 1),
            "latenciaP50Ms": round(pct(lat, .5), 1), "latenciaP95Ms": round(pct(lat, .95), 1)}

if __name__ == "__main__":
    base = engine(0)
    n, ms = calibrate(base, 20)
    out = {"consultaCalibrada": {"n": n, "msAprox": ms}, "A_techo": [], "B_cabeza_de_linea": []}
    for limit in (0, 2):
        e = engine(limit)
        out["A_techo"].append(throughput(limit, 40, 15, n, e))
    # B: una consulta lenta (~1 s) y 200 consultas rápidas desde 10 hilos, con tope 2 (como la API).
    nSlow, msSlow = calibrate(base, 1000)
    nFast, msFast = calibrate(base, 2)
    for scenario in ("sinConsultaLenta", "conConsultaLenta", "dosConsultasLentas"):
        e = engine(2)
        fast = []; lock = threading.Lock()
        def fastWork():
            for _ in range(20):
                ms_ = query(e, nFast)
                with lock: fast.append(ms_)
        slow = None; slows = []
        if scenario == "conConsultaLenta":
            slow = threading.Thread(target=lambda: query(e, nSlow)); slow.start(); time.sleep(0.05)
        if scenario == "dosConsultasLentas":
            slows = [threading.Thread(target=lambda: query(e, nSlow)) for _ in range(2)]
            [t.start() for t in slows]; time.sleep(0.05)
        ts = [threading.Thread(target=fastWork) for _ in range(10)]
        [t.start() for t in ts]; [t.join() for t in ts]
        if slow: slow.join()
        [t.join() for t in slows]
        out["B_cabeza_de_linea"].append({"escenario": scenario, "consultasRapidas": len(fast),
            "rapidaP50Ms": round(pct(fast, .5), 1), "rapidaP95Ms": round(pct(fast, .95), 1), "consultasLentas": (1 if slow else 2 if slows else 0), "consultaLentaMs": msSlow if (slow or slows) else None})
    print(json.dumps(out, ensure_ascii=False, indent=1))
