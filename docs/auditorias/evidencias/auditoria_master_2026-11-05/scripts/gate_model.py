"""Modelo: throughput de llamadas al driver con el semáforo REAL de app/db/gate.py (GatedCursor/gateFor), usando un
cursor simulado que tarda LAT ms por llamada (time.sleep libera el GIL). NO mide pyodbc ni SQL Server."""
import sys, time, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/home/user/GlucoLume/backend")
from app.db.gate import GatedCursor, gateFor
LAT = 0.005
class FakeCursor:
    def execute(self, *a, **k):
        time.sleep(LAT); return self
    def fetchall(self):
        return []
def worker(gate, calls):
    cur = GatedCursor(FakeCursor(), gate) if gate is not None else FakeCursor()
    for _ in range(calls):
        cur.execute("select 1")
        cur.fetchall()
def run(limit, threads=8, calls=200):
    gate = gateFor(limit) if limit > 0 else None
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=threads) as pool:
        list(pool.map(lambda _: worker(gate, calls), range(threads)))
    wall = time.perf_counter() - t0
    total_driver_calls = threads * calls * 2
    return round(total_driver_calls / wall), round(wall, 2)
if __name__ == "__main__":
    for limit in [0, 2, 4, 8]:
        cps, wall = run(limit)
        print(f"DB_MAX_CONCURRENT_CALLS={limit or 'sin tope'}: llamadas/s={cps} (8 hilos, LAT={LAT*1000:.0f} ms, wall={wall}s)")
