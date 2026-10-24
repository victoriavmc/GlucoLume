"""Carga por endpoint: N clientes simultáneos pidiendo SIEMPRE el mismo endpoint durante S segundos. Aísla qué operación se degrada con concurrencia.
    python carga_endpoint.py --base http://127.0.0.1:18000 --clientes 8 --segundos 6 [--solo evolution]
"""
import argparse, json, sys, threading, time
from pathlib import Path
sys.argv_backup = sys.argv
HERE = Path(__file__).resolve().parent
IDS = json.loads((HERE / "resultados" / "seed_ids.json").read_text(encoding="utf-8"))
import http.client, urllib.parse

def conn(base):
    p = urllib.parse.urlsplit(base); return http.client.HTTPConnection(p.hostname, p.port, timeout=60)

def call(c, method, path, token=None, body=None):
    h = {"Accept": "application/json", "X-GlucoLume-CSRF": "1"}
    if token: h["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None: data = json.dumps(body).encode(); h["Content-Type"] = "application/json"
    t = time.perf_counter(); c.request(method, path, body=data, headers=h); r = c.getresponse(); b = r.read()
    return r.status, (time.perf_counter() - t) * 1000, b

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--base", default="http://127.0.0.1:18000"); ap.add_argument("--clientes", type=int, default=8)
    ap.add_argument("--segundos", type=float, default=6); ap.add_argument("--solo", default=""); a = ap.parse_args()
    inst, pid, op = IDS["idInstitucion"], IDS["pacientes"][0], IDS["operadores"][0]
    def login(u):
        s, _, b = call(conn(a.base), "POST", "/api/v1/auth/login", body={"identificador": u, "password": IDS["password"]}); return json.loads(b)["tokens"]["accessToken"]
    tk = {"c": login("perfconsumidor"), "o": login(op["usuario"]), "p": login("perfduenia")}
    eps = [("GET /auth/me", "c", "/api/v1/auth/me"), ("evolution 7d", "c", "/api/v1/measurements/evolution?dias=7&origen=TODOS"),
           ("historial", "c", "/api/v1/measurements?pagina=1&tamanioPagina=10&orden=desc"), ("dashboard personal", "c", "/api/v1/measurements/dashboard?dias=30"),
           ("pacientes", "o", f"/api/v1/institutions/{inst}/patients?estado=ACTIVO&pagina=1&tamanioPagina=20"),
           ("dashboard institución", "p", f"/api/v1/institutions/{inst}/dashboard?dias=30"),
           ("dashboard operador", "o", f"/api/v1/institutions/{inst}/operators/{op['idInstitucionUsuario']}/dashboard?dias=30"),
           ("healthz", None, "/healthz")]
    for name, who, path in eps:
        if a.solo and a.solo not in name: continue
        times, bad, lock, codes = [], [0], threading.Lock(), {}; stop = time.perf_counter() + a.segundos
        def w():
            c = conn(a.base)
            while time.perf_counter() < stop:
                s, ms, _ = call(c, "GET", path, tk.get(who))
                with lock: times.append(ms); bad[0] += s != 200; codes[s] = codes.get(s, 0) + 1
        ts = [threading.Thread(target=w) for _ in range(a.clientes)]; t0 = time.perf_counter(); [t.start() for t in ts]; [t.join() for t in ts]; wall = time.perf_counter() - t0
        times.sort(); n = len(times)
        print(f"{name:24} clientes {a.clientes:>2}: {n/wall:7.1f} req/s  p50 {times[n//2]:8.1f}  p95 {times[int(n*.95)-1]:8.1f}  max {times[-1]:8.1f} ms  códigos {codes}")
main()
