import json, sys, statistics, collections
path = sys.argv[1]
rows = [json.loads(l) for l in open(path, encoding='utf8')]
errs = [r for r in rows if 'error' in r]
ok = [r for r in rows if 'error' not in r]
groups = collections.OrderedDict()
for r in ok:
    groups.setdefault((r['profile'], r['control']), []).append(r)
def q(vals, p):
    vals = sorted(v for v in vals if v is not None)
    if not vals: return None
    k = (len(vals) - 1) * p
    lo = int(k); hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)
metrics = [
    ('openFigureMs', 'Apertura hasta primera figura (ms)'),
    ('fcpMs', 'FCP (ms)'),
    ('lcpMs', 'LCP (ms)'),
    ('longTaskMs', 'Tareas largas al abrir (ms)'),
    ('pngOpenCount', 'PNG pedidos al abrir'),
    ('pngOpenBytes', 'Bytes PNG al abrir'),
    ('tabToInstitucional.ms', 'Cambio de pestaña a Institucional (ms, hasta 2 cuadros)'),
    ('tabToInstitucional.longTaskMs', 'Tarea larga en el cambio de pestaña (ms)'),
    ('tabBackToCliente.ms', 'Cambio de pestaña a Cliente (ms)'),
    ('scrollFrameP95', 'Cuadro p95 al desplazar (ms)'),
    ('scrollJank50', 'Cuadros >50 ms al desplazar (nº)'),
    ('scrollLongTaskMs', 'Tareas largas al desplazar (ms)'),
    ('scrollPngCount', 'PNG pedidos durante el desplazamiento'),
    ('visorMs', 'Visor ampliado: abrir y decodificar (ms)'),
    ('nodes', 'Nodos DOM al abrir'),
    ('decodedImgMB', 'Píxeles decodificados estimados (MB)'),
    ('heapMB', 'Heap JS (MB)'),
]
def get(r, dotted):
    cur = r
    for part in dotted.split('.'):
        if not isinstance(cur, dict) or part not in cur: return None
        cur = cur[part]
    return cur
print(f"errores: {len(errs)}  corridas válidas: {len(ok)}")
for (prof, ctl), rs in groups.items():
    print(f"\n## {prof} / {ctl}  (n={len(rs)})")
    for key, label in metrics:
        vals = [get(r, key) for r in rs]
        vals = [v for v in vals if v is not None]
        if not vals: continue
        print(f"  {label:58s} p50={q(vals,0.5):10.1f}  p95={q(vals,0.95):10.1f}  min={min(vals):9.1f}  max={max(vals):9.1f}")
