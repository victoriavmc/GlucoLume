"""Genera las tablas «antes / después» de docs/RENDIMIENTO.md a partir de los JSON de resultados/ (no se transcribe ningún número a mano).
    python comparar.py frontend      # frontend_base.json vs frontend_perf.json
    python comparar.py http          # http_final-baseline.json vs http_final-perf.json
    python comparar.py consultas     # consultas_base.txt vs consultas_perf.txt
"""
import json
import sys as _s
_s.stdout.reconfigure(encoding="utf-8")
import sys
from pathlib import Path

R = Path(__file__).resolve().parent / "resultados"


def pct(a, b):
    return f"{(b - a) / a * 100:+.0f} %" if a else "—"


def frontend():
    base = json.loads((R / "frontend_base.json").read_text(encoding="utf-8"))["resultados"]
    new = json.loads((R / "frontend_perf.json").read_text(encoding="utf-8"))["resultados"]
    print("| Pantalla | Red / caché | JS inicial (KB gzip) | FCP ms | LCP ms | TBT ms | CLS | Carga ms | Solicitudes (API) |")
    print("|---|---|---|---|---|---|---|---|---|")
    for key in base:
        if key not in new or "error" in base[key] or "error" in new[key]:
            continue
        a, b = base[key], new[key]
        screen, net, cache = [part.strip() for part in key.split("|")]
        cell = lambda f, fmt="{:.0f}": f"{fmt.format(a[f])} → {fmt.format(b[f])}"  # noqa: E731
        print(f"| {screen} | {net} · {cache} | {cell('jsKB')} | {cell('fcp')} | {cell('lcp')} | {cell('tbt')} | {a['cls']} → {b['cls']} | {cell('loadMs')} | {a['solicitudes']:.0f} ({a['api']:.0f}) → {b['solicitudes']:.0f} ({b['api']:.0f}) |")


def http():
    base = json.loads((R / "http_final-baseline.json").read_text(encoding="utf-8"))
    new = json.loads((R / "http_final-perf.json").read_text(encoding="utf-8"))
    print("| Endpoint (secuencial, 100 pedidos) | p50 ms | p95 ms | p99 ms |\n|---|---|---|---|")
    for name, a in base["secuencial"].items():
        b = new["secuencial"][name]
        print(f"| {name} | {a['p50']} → {b['p50']} | {a['p95']} → {b['p95']} | {a['p99']} → {b['p99']} |")
    print("\n| Clientes simultáneos (mezcla de 5 endpoints, 15 s) | req/s | p50 ms | p95 ms | p99 ms |\n|---|---|---|---|---|")
    for key, a in base["concurrencia"].items():
        b = new["concurrencia"][key]
        print(f"| {key} | {a['pedidosPorSegundo']} → {b['pedidosPorSegundo']} | {a['p50']} → {b['p50']} | {a['p95']} → {b['p95']} | {a['p99']} → {b['p99']} |")
    print("\n| Ingesta de muestras (400 por medición) | ms por solicitud p50 | p95 | ms por medición p50 | errores |\n|---|---|---|---|---|")
    for key, a in base["muestras"].items():
        b = new["muestras"][key]
        print(f"| {key} | {a['porLote']['p50']} → {b['porLote']['p50']} | {a['porLote']['p95']} → {b['porLote']['p95']} | {a['medicion400MuestrasMsP50']} → {b['medicion400MuestrasMsP50']} | {a['errores']} → {b['errores']} |")


def consultas():
    def load(name):
        rows = {}
        for line in (R / name).read_text(encoding="utf-8").splitlines():
            if line.startswith("{"):
                d = json.loads(line)
                rows[d["operacion"]] = d
        return rows
    base, new = load("consultas_base.txt"), load("consultas_perf.txt")
    print("| Operación | Sentencias SQL | Escrituras | Commits | Tiempo de base p50 ms | Total p50 ms |\n|---|---|---|---|---|---|")
    for name, a in base.items():
        b = new.get(name)
        if not b or a.get("estado") not in ([200], None):
            continue
        if "muestras" in a:
            for part in ("iniciar", "muestras", "cerrar"):
                x, y = a[part], b[part]
                sent = lambda d: d.get("sentencias", d.get("sentenciasTotal"))  # noqa: E731
                writes = lambda d: d.get("escrituras", d.get("escriturasTotal"))  # noqa: E731
                commits = lambda d: d.get("commits", d.get("commitsTotal"))  # noqa: E731
                ms = lambda d: d.get("msP50", d.get("msTotalP50"))  # noqa: E731
                print(f"| {name} · {part} | {sent(x)} → {sent(y)} | {writes(x)} → {writes(y)} | {commits(x)} → {commits(y)} | — | {ms(x)} → {ms(y)} |")
            continue
        print(f"| {name} | {a['sentencias']} → {b['sentencias']} | {a['escrituras']} → {b['escrituras']} | {a['commits']} → {b['commits']} | {a['msBase_p50']} → {b['msBase_p50']} | {a['msTotal_p50']} → {b['msTotal_p50']} |")


{"frontend": frontend, "http": http, "consultas": consultas}[sys.argv[1]]()
