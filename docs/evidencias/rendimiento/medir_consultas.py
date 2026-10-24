"""Cuenta las sentencias SQL y el tiempo de base de cada operación, en proceso, contra SQL Server REAL (base descartable GlucoLume_perf).

Usa TestClient sobre la app (mismo código, mismos servicios, ODBC 18 y pool reales) y un contador SQLAlchemy (before/after_cursor_execute).
No mide la red ni Nginx: para eso está medir_http.py. Salida: JSON por operación {sentencias, msBase, msTotal(p50 de N)}.

    docker compose -f compose.yaml -f docs/evidencias/rendimiento/compose.rendimiento.yaml --profile db --profile perf run --rm --no-deps \
        -v ./docs/evidencias/rendimiento:/perf:ro backend-perf python /perf/medir_consultas.py [--repeticiones 15] [--solo evolution]
"""

import argparse
import json
import os
import statistics
import sys
import time
import uuid

sys.path.insert(0, os.getcwd())
assert os.environ.get("DB_NAME") == "GlucoLume_perf", "Solo contra la base descartable GlucoLume_perf."

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

from app.main import app  # noqa: E402

PASSWORD = "Glucolume#Perf2026"  # nosec B105 - contraseña sintética de la base descartable


class Counter:
    def __init__(self):
        self.reset()

    def reset(self):
        self.statements = 0
        self.dbSeconds = 0.0
        self.writes = 0
        self.commits = 0
        self.samples: list[str] = []

    def before(self, conn, cursor, statement, parameters, context, executemany):
        context._glucolume_t0 = time.perf_counter()

    def after(self, conn, cursor, statement, parameters, context, executemany):
        elapsed = time.perf_counter() - getattr(context, "_glucolume_t0", time.perf_counter())
        self.dbSeconds += elapsed
        self.statements += 1
        head = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
        if head in ("INSERT", "UPDATE", "DELETE"):
            self.writes += 1
        if len(self.samples) < 400:
            self.samples.append(f"{elapsed * 1000:6.1f} ms {'x' + str(len(parameters)) if executemany and isinstance(parameters, list) else ''} {' '.join(statement.split())[:150]}".strip())

    def commit(self, conn):
        self.commits += 1


counter = Counter()
event.listen(Engine, "before_cursor_execute", counter.before)
event.listen(Engine, "after_cursor_execute", counter.after)
event.listen(Engine, "commit", counter.commit)

client = TestClient(app, base_url="http://localhost")


def login(usuario: str) -> dict:
    response = client.post("/api/v1/auth/login", json={"identificador": usuario, "password": PASSWORD},
                           headers={"X-GlucoLume-CSRF": "1"})
    assert response.status_code == 200, (usuario, response.status_code, response.text[:300])
    return {"Authorization": f"Bearer {response.json()['tokens']['accessToken']}"}


def run(name, method, path, headers, repetitions, **kwargs):
    results, statuses = [], set()
    first = None
    for index in range(repetitions):
        counter.reset()
        started = time.perf_counter()
        response = client.request(method, path, headers=headers, **kwargs)
        elapsed = (time.perf_counter() - started) * 1000
        statuses.add(response.status_code)
        results.append((elapsed, counter.statements, counter.dbSeconds * 1000, counter.writes, counter.commits))
        if index == 0:
            first = list(counter.samples)
    ms = sorted(r[0] for r in results)
    out = {
        "operacion": name, "estado": sorted(statuses), "sentencias": results[-1][1], "escrituras": results[-1][3], "commits": results[-1][4],
        "msBase_p50": round(statistics.median(r[2] for r in results), 1), "msTotal_p50": round(statistics.median(ms), 1),
        "msTotal_p95": round(ms[min(len(ms) - 1, int(len(ms) * 0.95))], 1), "msTotal_min": round(ms[0], 1),
    }
    if os.environ.get("VER_SQL") == name:
        out["sql"] = first
    print(json.dumps(out, ensure_ascii=False), flush=True)
    return response


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeticiones", type=int, default=15)
    parser.add_argument("--solo", default="")
    parser.add_argument("--ids", default="/perf/resultados/seed_ids.json")
    args = parser.parse_args()
    ids = json.load(open(args.ids, encoding="utf-8"))
    n = args.repeticiones
    want = lambda name: not args.solo or args.solo in name  # noqa: E731
    inst = ids["idInstitucion"]
    pid = ids["pacientes"][0]
    op = ids["operadores"][0]

    counter.reset()
    login("perfconsumidor")  # primer login: calienta pool, Argon2 y el import perezoso
    counter.reset()
    started = time.perf_counter()
    consumer = login("perfconsumidor")
    print(json.dumps({"operacion": "POST /auth/login (consumidor)", "sentencias": counter.statements, "escrituras": counter.writes, "commits": counter.commits,
                      "msTotal_p50": round((time.perf_counter() - started) * 1000, 1), "msBase_p50": round(counter.dbSeconds * 1000, 1)}), flush=True)
    operator = login(op["usuario"])

    ops = [
        ("GET /measurements/profile", "GET", "/api/v1/measurements/profile", consumer, {}),
        ("GET /measurements/evolution?dias=7", "GET", "/api/v1/measurements/evolution?dias=7&origen=TODOS", consumer, {}),
        ("GET /measurements/evolution?dias=90", "GET", "/api/v1/measurements/evolution?dias=90&origen=TODOS", consumer, {}),
        ("GET /measurements/evolution?dias=30", "GET", "/api/v1/measurements/evolution?dias=30&origen=TODOS", consumer, {}),
        ("GET /measurements (historial, pág. 1)", "GET", "/api/v1/measurements?pagina=1&tamanioPagina=10&orden=desc", consumer, {}),
        ("GET /measurements/dashboard?dias=30", "GET", "/api/v1/measurements/dashboard?dias=30", consumer, {}),
        ("GET /measurements/statistics?dias=30", "GET", "/api/v1/measurements/statistics?dias=30", consumer, {}),
        ("GET /institutions (mis instituciones)", "GET", "/api/v1/institutions", operator, {}),
        ("GET /institutions/{id}/patients (pág. 1, 20)", "GET", f"/api/v1/institutions/{inst}/patients?estado=ACTIVO&pagina=1&tamanioPagina=20", operator, {}),
        ("GET /institutions/{id}/patients?busqueda=", "GET", f"/api/v1/institutions/{inst}/patients?estado=ACTIVO&busqueda=Garc&pagina=1&tamanioPagina=20", operator, {}),
        ("GET /institutions/{id}/patients/assignable-operators", "GET", f"/api/v1/institutions/{inst}/patients/assignable-operators", operator, {}),
        ("GET /institutions/{id}/patients/{pid}", "GET", f"/api/v1/institutions/{inst}/patients/{pid}", operator, {}),
        ("GET /institutions/{id}/patients/{pid}/measurements", "GET", f"/api/v1/institutions/{inst}/patients/{pid}/measurements?pagina=1&tamanioPagina=10", operator, {}),
        ("GET /institutions/{id}/patients/{pid}/measurements/evolution", "GET", f"/api/v1/institutions/{inst}/patients/{pid}/measurements/evolution?dias=30&origen=TODOS", operator, {}),
        ("GET /institutions/{id}/patients/{pid}/dashboard", "GET", f"/api/v1/institutions/{inst}/patients/{pid}/dashboard?dias=30", operator, {}),
        ("GET /institutions/{id}/dashboard", "GET", f"/api/v1/institutions/{inst}/dashboard?dias=30", login("perfduenia"), {}),
        ("GET /institutions/{id}/operators/{op}/dashboard", "GET", f"/api/v1/institutions/{inst}/operators/{op['idInstitucionUsuario']}/dashboard?dias=30", operator, {}),
        ("GET /institutions/{id}/analytics/patients", "GET", f"/api/v1/institutions/{inst}/analytics/patients?dias=90", login("perfduenia"), {}),
        ("GET /institutions/{id}/indicators", "GET", f"/api/v1/institutions/{inst}/indicators", login("perfduenia"), {}),
    ]
    for name, method, path, headers, kwargs in ops:
        if want(name):
            response = run(name, method, path, headers, n, **kwargs)
            if response.status_code != 200:
                print("   ↳", response.status_code, response.text[:160], flush=True)

    if want("escritura"):
        measureWrites(consumer, ids, n)


def measureWrites(consumer, ids, n):
    """Flujo de una medición: iniciar → muestras (lotes del puente o una sola tanda) → cerrar. Cuenta sentencias y escrituras."""
    sys.path.insert(0, "/perf")
    from ppg import ppgSamples

    profile, device = ids["consumidor"]["idPerfilMedicion"], ids["idDispositivo"]
    samples = [{"numeroMuestra": i, "tiempoRelativoMs": t, "valorRed": red, "valorIR": ir} for i, t, red, ir in ppgSamples(72, 96.0, 20, dcIr=120000, dcRed=100000)]
    for batch, label in ((len(samples), "una tanda de 400"), (20, "lotes de 20 (puente)")):
        starts, sampleRuns, finishes = [], [], []
        for _ in range(max(3, n // 3)):
            counter.reset()
            t0 = time.perf_counter()
            response = client.post("/api/v1/measurements", headers=consumer, json={"idPerfilMedicion": profile, "idDispositivo": device})
            assert response.status_code in (200, 201), response.text[:200]
            starts.append((time.perf_counter() - t0) * 1000)
            idMedicion = response.json()["idMedicion"]
            startStats = (counter.statements, counter.writes, counter.commits)
            sampleStats = [0, 0, 0]
            t0 = time.perf_counter()
            per = []
            for index in range(0, len(samples), batch):
                counter.reset()
                t1 = time.perf_counter()
                r = client.post(f"/api/v1/measurements/{idMedicion}/samples", headers=consumer, json={"muestras": samples[index:index + batch]})
                assert r.status_code == 200, r.text[:200]
                per.append((time.perf_counter() - t1) * 1000)
                for slot, value in enumerate((counter.statements, counter.writes, counter.commits)):
                    sampleStats[slot] += value
            sampleRuns.append((sum(per), statistics.median(per), sampleStats, len(per)))
            counter.reset()
            t0 = time.perf_counter()
            r = client.post(f"/api/v1/measurements/{idMedicion}/finish", headers=consumer, json={})
            assert r.status_code == 200, r.text[:200]
            finishes.append(((time.perf_counter() - t0) * 1000, counter.statements, counter.writes, counter.commits))
        print(json.dumps({
            "operacion": f"escritura: medición con 400 muestras en {label}",
            "iniciar": {"msP50": round(statistics.median(starts), 1), "sentencias": startStats[0], "escrituras": startStats[1], "commits": startStats[2]},
            "muestras": {"solicitudes": sampleRuns[-1][3], "msTotalP50": round(statistics.median(r[0] for r in sampleRuns), 1),
                         "msPorSolicitudP50": round(statistics.median(r[1] for r in sampleRuns), 1),
                         "sentenciasTotal": sampleRuns[-1][2][0], "escriturasTotal": sampleRuns[-1][2][1], "commitsTotal": sampleRuns[-1][2][2]},
            "cerrar": {"msP50": round(statistics.median(f[0] for f in finishes), 1), "sentencias": finishes[-1][1], "escrituras": finishes[-1][2], "commits": finishes[-1][3]},
        }, ensure_ascii=False), flush=True)


main()
