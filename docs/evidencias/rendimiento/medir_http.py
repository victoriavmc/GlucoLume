"""Latencia p50/p95/p99 y comportamiento bajo concurrencia, por HTTP real, contra el stack de medición (compose.rendimiento.yaml).

Sin dependencias (solo biblioteca estándar). Conexiones persistentes por hilo, como un navegador o el puente.
    python medir_http.py --base http://127.0.0.1:18000 --etiqueta base      # API directa (sin Nginx)
    python medir_http.py --base http://127.0.0.1:18080 --etiqueta base-nginx
Salida: resultados/http_<etiqueta>.json y un resumen en pantalla.
"""

import argparse
import http.client
import json
import statistics
import sys
import threading
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
IDS = json.loads((HERE / "resultados" / "seed_ids.json").read_text(encoding="utf-8"))
PASSWORD = IDS["password"]


class Conn:
    def __init__(self, base):
        parts = urllib.parse.urlsplit(base)
        self.host, self.port = parts.hostname, parts.port
        self.conn = http.client.HTTPConnection(self.host, self.port, timeout=60)

    def call(self, method, path, token=None, body=None):
        headers = {"Accept": "application/json", "X-GlucoLume-CSRF": "1"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        for attempt in range(2):
            try:
                started = time.perf_counter()
                self.conn.request(method, path, body=data, headers=headers)
                response = self.conn.getresponse()
                payload = response.read()
                return response.status, (time.perf_counter() - started) * 1000, len(payload), payload
            except (http.client.HTTPException, ConnectionError, OSError):
                self.conn.close()
                self.conn = http.client.HTTPConnection(self.host, self.port, timeout=60)
                if attempt:
                    raise


def login(base, user):
    status, _, _, payload = Conn(base).call("POST", "/api/v1/auth/login", body={"identificador": user, "password": PASSWORD})
    assert status == 200, (user, status, payload[:200])
    return json.loads(payload)["tokens"]["accessToken"]


def pct(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(round(q * len(ordered))) - 1))]


def summary(times):
    return {"n": len(times), "p50": round(pct(times, 0.5), 1), "p95": round(pct(times, 0.95), 1), "p99": round(pct(times, 0.99), 1),
            "max": round(max(times), 1), "media": round(statistics.mean(times), 1)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:18000")
    parser.add_argument("--etiqueta", default="base")
    parser.add_argument("--n", type=int, default=100, help="pedidos secuenciales por endpoint")
    parser.add_argument("--concurrencia", default="1,8,32")
    parser.add_argument("--segundos", type=float, default=15.0)
    args = parser.parse_args()
    base = args.base
    inst, pid, op = IDS["idInstitucion"], IDS["pacientes"][0], IDS["operadores"][0]
    tokens = {"consumidor": login(base, "perfconsumidor"), "operador": login(base, op["usuario"]), "propietaria": login(base, "perfduenia")}
    scenarios = [
        ("evolution 7d", "consumidor", "/api/v1/measurements/evolution?dias=7&origen=TODOS"),
        ("evolution 90d", "consumidor", "/api/v1/measurements/evolution?dias=90&origen=TODOS"),
        ("historial pág.1", "consumidor", "/api/v1/measurements?pagina=1&tamanioPagina=10&orden=desc"),
        ("dashboard personal", "consumidor", "/api/v1/measurements/dashboard?dias=30"),
        ("pacientes pág.1", "operador", f"/api/v1/institutions/{inst}/patients?estado=ACTIVO&pagina=1&tamanioPagina=20"),
        ("operadores asignables", "operador", f"/api/v1/institutions/{inst}/patients/assignable-operators"),
        ("dashboard institución", "propietaria", f"/api/v1/institutions/{inst}/dashboard?dias=30"),
        ("dashboard operador", "operador", f"/api/v1/institutions/{inst}/operators/{op['idInstitucionUsuario']}/dashboard?dias=30"),
        ("indicadores institución", "propietaria", f"/api/v1/institutions/{inst}/indicators"),
    ]
    out = {"base": base, "etiqueta": args.etiqueta, "secuencial": {}, "concurrencia": {}, "muestras": {}}

    conn = Conn(base)
    print(f"\n== Secuencial ({args.n} pedidos por endpoint) {base}")
    for name, who, path in scenarios:
        conn.call("GET", path, tokens[who])  # calentamiento
        times, sizes, bad = [], 0, 0
        for _ in range(args.n):
            status, ms, size, _ = conn.call("GET", path, tokens[who])
            bad += status != 200
            times.append(ms)
            sizes = size
        out["secuencial"][name] = {**summary(times), "bytes": sizes, "noOK": bad}
        print(f"{name:28} p50 {out['secuencial'][name]['p50']:7.1f}  p95 {out['secuencial'][name]['p95']:7.1f}  p99 {out['secuencial'][name]['p99']:7.1f} ms  {sizes:>7} B  no-200: {bad}")

    mix = [s for s in scenarios if s[0] in ("evolution 7d", "historial pág.1", "pacientes pág.1", "dashboard personal", "dashboard institución")]
    for workers in (int(w) for w in args.concurrencia.split(",")):
        times, errors, count = [], [0], [0]
        lock, stop = threading.Lock(), time.perf_counter() + args.segundos

        def worker(seed):
            c = Conn(base)
            index = seed
            while time.perf_counter() < stop:
                _, who, path = mix[index % len(mix)]
                index += 1
                try:
                    status, ms, _, _ = c.call("GET", path, tokens[who])
                except Exception:  # noqa: BLE001
                    with lock:
                        errors[0] += 1
                    continue
                with lock:
                    count[0] += 1
                    times.append(ms)
                    errors[0] += status != 200

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(workers)]
        t0 = time.perf_counter()
        [t.start() for t in threads]
        [t.join() for t in threads]
        wall = time.perf_counter() - t0
        out["concurrencia"][str(workers)] = {**summary(times), "pedidosPorSegundo": round(count[0] / wall, 1), "errores": errors[0]}
        print(f"concurrencia {workers:>3}: {count[0] / wall:7.1f} req/s  p50 {out['concurrencia'][str(workers)]['p50']:7.1f}  p95 {out['concurrencia'][str(workers)]['p95']:7.1f}  p99 {out['concurrencia'][str(workers)]['p99']:7.1f} ms  errores {errors[0]}")

    # Ingesta de muestras: N mediciones simultáneas, cada una con 400 muestras en lotes de 20 (como el puente) o de 200 (tope del puente).
    sys.path.insert(0, str(HERE))
    from ppg import ppgSamples
    samples = [{"numeroMuestra": i, "tiempoRelativoMs": t, "valorRed": red, "valorIR": ir} for i, t, red, ir in ppgSamples(72, 96.0, 20, dcIr=120000, dcRed=100000)]
    for parallel, batch in ((1, 20), (1, 200), (8, 20), (16, 20)):
        # cada medición necesita su propia cuenta (una medición en curso por perfil): se usan las cuentas del consumidor en serie por medición
        perBatch, totals, errs = [], [], [0]
        lock = threading.Lock()

        def one(_):
            c = Conn(base)
            token = tokens["consumidor"]
            status, _, _, payload = c.call("POST", "/api/v1/measurements", token, {"idPerfilMedicion": IDS["consumidor"]["idPerfilMedicion"], "idDispositivo": IDS["idDispositivo"]})
            if status not in (200, 201):
                with lock:
                    errs[0] += 1
                return
            idMedicion = json.loads(payload)["idMedicion"]
            t0 = time.perf_counter()
            for index in range(0, len(samples), batch):
                st, ms, _, _ = c.call("POST", f"/api/v1/measurements/{idMedicion}/samples", token, {"muestras": samples[index:index + batch]})
                with lock:
                    perBatch.append(ms)
                    errs[0] += st != 200
            with lock:
                totals.append((time.perf_counter() - t0) * 1000)
            c.call("POST", f"/api/v1/measurements/{idMedicion}/cancel", token)

        # El backend admite una medición en curso por perfil y dispositivo: las 'paralelas' son secuenciales por perfil salvo que se creen más perfiles.
        runs = 6 if parallel == 1 else 1
        for _ in range(runs):
            threads = [threading.Thread(target=one, args=(i,)) for i in range(parallel)]
            [t.start() for t in threads]
            [t.join() for t in threads]
        key = f"{parallel} en paralelo, lotes de {batch}"
        out["muestras"][key] = {"porLote": summary(perBatch) if perBatch else None, "medicion400MuestrasMsP50": round(statistics.median(totals), 1) if totals else None, "errores": errs[0]}
        print(f"muestras {key:28}: {out['muestras'][key]}")

    (HERE / "resultados" / f"http_{args.etiqueta}.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")


main()
