"""Genera el DER de GlucoLume a partir de database/reference/GlucoLume_DB_v5.sql.

Salidas (en esta misma carpeta): der.svg, der.png y der.html (página con zoom, desplazamiento y tablas movibles).
Si existe posiciones.json (se guarda desde der.html con «Guardar posiciones»), se usa en lugar del acomodo automático.
Uso:  python docs/der/generar_der.py
"""
import html
import json
import math
import random
import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SQL = RAIZ / "database" / "reference" / "GlucoLume_DB_v5.sql"
SALIDA = Path(__file__).resolve().parent

GRUPOS = {
    "Cuenta y seguridad": ("#2f6fed", [
        "Usuario", "CredencialLocal", "IdentidadExterna", "FactorMfa", "CodigoRecuperacionMfa",
        "SesionUsuario", "TokenCuenta", "ConsentimientoUsuario", "ConfiguracionNotificacion"]),
    "Instituciones y grupos": ("#16a085", [
        "Institucion", "InstitucionUsuario", "Grupo", "GrupoUsuario", "ReasignacionPaciente",
        "TransferenciaPerfil", "TransferenciaAdministracion"]),
    "Mediciones": ("#d9822b", [
        "PerfilMedicion", "Medicion", "MedicionReferenciaCapilar", "MuestraSensor", "Dispositivo",
        "Matriz", "ReglaMatriz", "EnvioResultado"]),
    "Suscripción y pagos": ("#8e44ad", [
        "PlanSuscripcion", "Suscripcion", "SuscripcionUsuario", "PeriodoPrueba", "ProveedorPago",
        "TransaccionPago"]),
    "Auditoría": ("#6c7a89", ["Auditoria", "AuditoriaContexto", "AuditoriaTecnicaMedicion"]),
}
# Posición inicial aproximada de cada grupo (sólo semilla del acomodo automático).
SEMILLA = {
    "Cuenta y seguridad": (0, 0), "Instituciones y grupos": (1400, 300), "Mediciones": (2800, 0),
    "Suscripción y pagos": (0, 1500), "Auditoría": (2800, 1500),
}


def leer_sql():
    crudo = SQL.read_bytes()
    texto = crudo.decode("utf-16") if crudo[:2] in (b"\xff\xfe", b"\xfe\xff") else crudo.decode("utf-8-sig")
    return texto.replace("\r\n", "\n")


def parsear(texto):
    tablas = {}
    for m in re.finditer(r"CREATE TABLE \[dbo\]\.\[(\w+)\]\((.*?)\n\)\s*ON \[PRIMARY\]", texto, re.S):
        nombre, cuerpo = m.group(1), m.group(2)
        columnas, pk, unicos = [], [], []
        for linea in cuerpo.split("\n"):
            c = re.match(r"\s*\[(\w+)\]\s+(?:\[(\w+)\](\([^)]*\))?|AS\b.*)\s*(.*?),?\s*$", linea)
            if c and not linea.strip().startswith("CONSTRAINT"):
                if c.group(2):
                    tipo = c.group(2) + (c.group(3) or "").replace(" ", "")
                    resto = c.group(4)
                    columnas.append({"n": c.group(1), "t": tipo, "null": "NOT NULL" not in resto})
                else:
                    columnas.append({"n": c.group(1), "t": "calculada", "null": True})
        for cons in re.finditer(r"CONSTRAINT \[\w+\]\s+(PRIMARY KEY|UNIQUE)[^(]*\((.*?)\)\s*WITH", cuerpo, re.S):
            cols = re.findall(r"\[(\w+)\]", cons.group(2))
            (pk if cons.group(1) == "PRIMARY KEY" else unicos).append(cols)
        tablas[nombre] = {"cols": columnas, "pk": pk[0] if pk else [], "uq": unicos}
    relaciones = []
    patron = (r"ALTER TABLE \[dbo\]\.\[(\w+)\]\s+WITH (?:NO)?CHECK ADD\s+CONSTRAINT \[(\w+)\] FOREIGN KEY\(([^)]*)\)\s*"
              r"REFERENCES \[dbo\]\.\[(\w+)\]\s*\(([^)]*)\)")
    for m in re.finditer(patron, texto):
        hija, nombre, cols, padre, pcols = m.groups()
        cols = re.findall(r"\[(\w+)\]", cols)
        relaciones.append({"hija": hija, "fk": nombre, "cols": cols, "padre": padre,
                           "pcols": re.findall(r"\[(\w+)\]", pcols)})
    for r in relaciones:
        t = tablas[r["hija"]]
        nulos = [next(c["null"] for c in t["cols"] if c["n"] == x) for x in r["cols"]]
        r["opcional"] = any(nulos)
        r["uno"] = r["cols"] == t["pk"] or r["cols"] in t["uq"]
    return tablas, relaciones


ALTO_CAB, ALTO_FILA, ANCHO_CHAR = 30, 18, 6.9


def medir(tablas, relaciones):
    fks = {(r["hija"], c) for r in relaciones for c in r["cols"]}
    for nombre, t in tablas.items():
        t["fks"] = {c for (h, c) in fks if h == nombre}
        ancho = len(nombre) * 8.2 + 40
        for c in t["cols"]:
            ancho = max(ancho, 34 + (len(c["n"]) + len(c["t"]) + 3) * ANCHO_CHAR + 30)
        t["w"] = round(ancho)
        t["h"] = ALTO_CAB + ALTO_FILA * len(t["cols"]) + 8
        for g, (_, miembros) in GRUPOS.items():
            if nombre in miembros:
                t["grupo"] = g


def acomodar(tablas, relaciones):
    """Acomodo por fuerzas, consciente del tamaño de las cajas."""
    rnd = random.Random(7)
    pos = {}
    for n, t in tablas.items():
        sx, sy = SEMILLA[t["grupo"]]
        pos[n] = [sx + rnd.uniform(-500, 500), sy + rnd.uniform(-500, 500)]
    nombres = list(tablas)
    pares = {tuple(sorted((r["hija"], r["padre"]))) for r in relaciones if r["hija"] != r["padre"]}
    # Tablas sin FK (p. ej. AuditoriaTecnicaMedicion): sólo para el acomodo, se acercan a otra de su grupo.
    con_fk = {x for par in pares for x in par}
    for n in nombres:
        if n not in con_fk:
            vecina = next(m for m in GRUPOS[tablas[n]["grupo"]][1] if m != n and m in con_fk)
            pares.add(tuple(sorted((n, vecina))))
    for it in range(1800):
        paso = 1 - it / 1800
        fuerza = {n: [0.0, 0.0] for n in nombres}
        for i, a in enumerate(nombres):
            for b in nombres[i + 1:]:
                dx, dy = pos[b][0] - pos[a][0], pos[b][1] - pos[a][1]
                ox = (tablas[a]["w"] + tablas[b]["w"]) / 2 + 90 - abs(dx)
                oy = (tablas[a]["h"] + tablas[b]["h"]) / 2 + 90 - abs(dy)
                if ox > 0 and oy > 0:
                    if ox < oy:
                        f = (ox * 0.35) * (1 if dx >= 0 else -1)
                        fuerza[a][0] -= f; fuerza[b][0] += f
                    else:
                        f = (oy * 0.35) * (1 if dy >= 0 else -1)
                        fuerza[a][1] -= f; fuerza[b][1] += f
                d = math.hypot(dx, dy) or 1
                rep = 90000 / (d * d)
                fuerza[a][0] -= rep * dx / d; fuerza[a][1] -= rep * dy / d
                fuerza[b][0] += rep * dx / d; fuerza[b][1] += rep * dy / d
        for a, b in pares:
            dx, dy = pos[b][0] - pos[a][0], pos[b][1] - pos[a][1]
            d = math.hypot(dx, dy) or 1
            ideal = (math.hypot(tablas[a]["w"], tablas[a]["h"]) + math.hypot(tablas[b]["w"], tablas[b]["h"])) / 3.2 + 110
            f = 0.045 * (d - ideal)
            fuerza[a][0] += f * dx / d; fuerza[a][1] += f * dy / d
            fuerza[b][0] -= f * dx / d; fuerza[b][1] -= f * dy / d
        for n in nombres:
            sx, sy = SEMILLA[tablas[n]["grupo"]]
            fuerza[n][0] += (sx - pos[n][0]) * 0.004
            fuerza[n][1] += (sy - pos[n][1]) * 0.004
            m = max(math.hypot(*fuerza[n]), 1)
            tope = 40 * paso + 2
            k = min(1, tope / m)
            pos[n][0] += fuerza[n][0] * k
            pos[n][1] += fuerza[n][1] * k
    for _ in range(2000):  # separación final estricta: ninguna caja puede tocar a otra
        moved = False
        for i, a in enumerate(nombres):
            for b in nombres[i + 1:]:
                dx, dy = pos[b][0] - pos[a][0], pos[b][1] - pos[a][1]
                ox = (tablas[a]["w"] + tablas[b]["w"]) / 2 + 70 - abs(dx)
                oy = (tablas[a]["h"] + tablas[b]["h"]) / 2 + 70 - abs(dy)
                if ox > 0 and oy > 0:
                    moved = True
                    if ox < oy:
                        f = ox / 2 + 1; sg = 1 if dx >= 0 else -1
                        pos[a][0] -= f * sg; pos[b][0] += f * sg
                    else:
                        f = oy / 2 + 1; sg = 1 if dy >= 0 else -1
                        pos[a][1] -= f * sg; pos[b][1] += f * sg
        if not moved:
            break
    minx = min(pos[n][0] - tablas[n]["w"] / 2 for n in nombres)
    miny = min(pos[n][1] - tablas[n]["h"] / 2 for n in nombres)
    for n in nombres:
        tablas[n]["x"] = round(pos[n][0] - tablas[n]["w"] / 2 - minx) + 60
        tablas[n]["y"] = round(pos[n][1] - tablas[n]["h"] / 2 - miny) + 120


def borde(t, hacia):
    """Punto donde el segmento centro→hacia sale del rectángulo de t."""
    cx, cy = t["x"] + t["w"] / 2, t["y"] + t["h"] / 2
    dx, dy = hacia[0] - cx, hacia[1] - cy
    if dx == 0 and dy == 0:
        return cx, cy
    k = min((t["w"] / 2) / abs(dx) if dx else 1e9, (t["h"] / 2) / abs(dy) if dy else 1e9)
    return cx + dx * k, cy + dy * k


def glifo_padre(p, u, opcional):
    """Lado «uno»: barra (y círculo si es opcional). p = punto en el borde, u = vector unitario hacia fuera."""
    nx, ny = -u[1], u[0]
    out = []
    d = 12
    bx, by = p[0] + u[0] * d, p[1] + u[1] * d
    out.append(f'<line x1="{bx + nx * 6:.1f}" y1="{by + ny * 6:.1f}" x2="{bx - nx * 6:.1f}" y2="{by - ny * 6:.1f}"/>')
    if opcional:
        cx, cy = p[0] + u[0] * 21, p[1] + u[1] * 21
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" class="hueco"/>')
    else:
        bx, by = p[0] + u[0] * 17, p[1] + u[1] * 17
        out.append(f'<line x1="{bx + nx * 6:.1f}" y1="{by + ny * 6:.1f}" x2="{bx - nx * 6:.1f}" y2="{by - ny * 6:.1f}"/>')
    return "".join(out)


def glifo_hija(p, u, opcional, uno):
    nx, ny = -u[1], u[0]
    out = []
    if uno:
        bx, by = p[0] + u[0] * 12, p[1] + u[1] * 12
        out.append(f'<line x1="{bx + nx * 6:.1f}" y1="{by + ny * 6:.1f}" x2="{bx - nx * 6:.1f}" y2="{by - ny * 6:.1f}"/>')
        return "".join(out)
    bx, by = p[0] + u[0] * 14, p[1] + u[1] * 14
    for s in (-7, 0, 7):
        out.append(f'<line x1="{bx + nx * s * 0:.1f}" y1="{by:.1f}" x2="{p[0] + nx * s:.1f}" y2="{p[1] + ny * s:.1f}"/>')
    if opcional:
        cx, cy = p[0] + u[0] * 22, p[1] + u[1] * 22
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" class="hueco"/>')
    else:
        bx, by = p[0] + u[0] * 19, p[1] + u[1] * 19
        out.append(f'<line x1="{bx + nx * 6:.1f}" y1="{by + ny * 6:.1f}" x2="{bx - nx * 6:.1f}" y2="{by - ny * 6:.1f}"/>')
    return "".join(out)


def dibujar(tablas, relaciones):
    ancho = max(t["x"] + t["w"] for t in tablas.values()) + 80
    alto = max(t["y"] + t["h"] for t in tablas.values()) + 80
    # Relaciones entre el mismo par de tablas se curvan con distinto desvío.
    por_par = {}
    for r in relaciones:
        por_par.setdefault(tuple(sorted((r["hija"], r["padre"]))), []).append(r)
    aristas = []
    for par, lista in por_par.items():
        for i, r in enumerate(lista):
            desvio = (i - (len(lista) - 1) / 2) * 46
            r["desvio"] = desvio
            h, p = tablas[r["hija"]], tablas[r["padre"]]
            if r["hija"] == r["padre"]:
                x, y = h["x"] + h["w"], h["y"] + 50 + i * 40
                aristas.append((r, f"M{x} {y} C{x + 90} {y - 25},{x + 90} {y + 45},{x} {y + 20}",
                                (x, y, 1, 0), (x, y + 20, 1, 0)))
                continue
            ch, cp = (h["x"] + h["w"] / 2, h["y"] + h["h"] / 2), (p["x"] + p["w"] / 2, p["y"] + p["h"] / 2)
            mx, my = (ch[0] + cp[0]) / 2, (ch[1] + cp[1]) / 2
            dx, dy = cp[0] - ch[0], cp[1] - ch[1]
            d = math.hypot(dx, dy) or 1
            ctrl = (mx - dy / d * desvio * 2, my + dx / d * desvio * 2)
            a = borde(h, ctrl)
            b = borde(p, ctrl)
            ua = (ctrl[0] - a[0], ctrl[1] - a[1]); la = math.hypot(*ua) or 1; ua = (ua[0] / la, ua[1] / la)
            ub = (ctrl[0] - b[0], ctrl[1] - b[1]); lb = math.hypot(*ub) or 1; ub = (ub[0] / lb, ub[1] / lb)
            aristas.append((r, f"M{a[0]:.1f} {a[1]:.1f} Q{ctrl[0]:.1f} {ctrl[1]:.1f} {b[0]:.1f} {b[1]:.1f}", (*a, *ua), (*b, *ub)))
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho} {alto}" width="{ancho}" height="{alto}" '
         f'font-family="Segoe UI, Arial, sans-serif">']
    s.append("""<style>
.fondo{fill:#fafbfc}
.rel path{fill:none;stroke:#5b6676;stroke-width:1.4}
.rel line,.rel circle{stroke:#5b6676;stroke-width:1.4;fill:none}
.rel circle.hueco{fill:#fff}
.rel{cursor:pointer}
.rel .area{stroke:transparent;stroke-width:14}
.rel:hover path.vis,.rel.on path.vis{stroke:#e0301e;stroke-width:2.4}
.rel:hover line,.rel:hover circle,.rel.on line,.rel.on circle{stroke:#e0301e;stroke-width:2.2}
.tabla rect.caja{fill:#fff;stroke:#c5ccd6;stroke-width:1.2}
.tabla text{font-size:12px;fill:#222}
.tabla .tipo{fill:#7a8594;font-size:11px}
.tabla .pk{font-weight:700}
.tabla .sep{stroke:#e5e8ec}
.tabla.dim{opacity:.25}.rel.dim{opacity:.12}
.titulo{font-size:30px;font-weight:700;fill:#1b2430}.sub{font-size:14px;fill:#5b6676}
.leyenda text{font-size:13px;fill:#222}
</style>""")
    s.append(f'<rect class="fondo" width="{ancho}" height="{alto}"/>')
    s.append('<text class="titulo" x="60" y="52">GlucoLume — Diagrama entidad-relación</text>')
    s.append(f'<text class="sub" x="60" y="78">{len(tablas)} tablas · {len(relaciones)} claves foráneas · generado desde GlucoLume_DB_v5.sql</text>')
    lx = 60
    s.append('<g class="leyenda">')
    for g, (color, _) in GRUPOS.items():
        s.append(f'<rect x="{lx}" y="92" width="14" height="14" rx="3" fill="{color}"/>'
                 f'<text x="{lx + 20}" y="104">{g}</text>')
        lx += 46 + len(g) * 7.2
    s.append('</g>')
    s.append('<g id="relaciones">')
    for r, camino, a, b in aristas:
        nota = f'{r["fk"]}: {r["hija"]}({", ".join(r["cols"])}) → {r["padre"]}({", ".join(r["pcols"])})'
        s.append(f'<g class="rel" data-h="{r["hija"]}" data-p="{r["padre"]}" data-d="{r["desvio"]}" '
                 f'data-o="{int(r["opcional"])}" data-u="{int(r["uno"])}"><title>{html.escape(nota)}</title>'
                 f'<path class="area" d="{camino}"/><path class="vis" d="{camino}"/>'
                 f'{glifo_hija((a[0], a[1]), (a[2], a[3]), r["opcional"], r["uno"])}'
                 f'{glifo_padre((b[0], b[1]), (b[2], b[3]), r["opcional"])}</g>')
    s.append('</g><g id="tablas">')
    for n, t in tablas.items():
        color = GRUPOS[t["grupo"]][0]
        x, y, w, h = t["x"], t["y"], t["w"], t["h"]
        s.append(f'<g class="tabla" data-n="{n}" data-x="{x}" data-y="{y}" data-w="{w}" data-h="{h}"><rect class="caja" x="{x}" y="{y}" width="{w}" height="{h}" rx="6"/>'
                 f'<path d="M{x} {y + 30} V{y + 6} a6 6 0 0 1 6 -6 H{x + w - 6} a6 6 0 0 1 6 6 V{y + 30} Z" fill="{color}"/>'
                 f'<text x="{x + 10}" y="{y + 20}" style="fill:#fff;font-weight:700;font-size:14px">{n}</text>')
        for i, c in enumerate(t["cols"]):
            fy = y + ALTO_CAB + 4 + i * ALTO_FILA
            es_pk, es_fk = c["n"] in t["pk"], c["n"] in t["fks"]
            marca = "PK" if es_pk and es_fk else "PK" if es_pk else "FK" if es_fk else ""
            clase = ' class="pk"' if es_pk else ""
            if marca:
                col = "#c18401" if es_pk else "#2f6fed"
                s.append(f'<text x="{x + 8}" y="{fy + 13}" style="font-size:9.5px;font-weight:700;fill:{col}">{marca}</text>')
            nulo = "" if not c["null"] else " ?"
            s.append(f'<text x="{x + 30}" y="{fy + 13}"{clase}>{c["n"]}</text>'
                     f'<text class="tipo" x="{x + w - 8}" y="{fy + 13}" text-anchor="end">{c["t"]}{nulo}</text>')
        s.append('</g>')
    s.append('</g></svg>')
    return "\n".join(s), ancho, alto


PAGINA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DER GlucoLume</title>
<style>
html,body{margin:0;height:100%;background:#fafbfc;font-family:"Segoe UI",Arial,sans-serif;overflow:hidden}
#lienzo{position:absolute;inset:0;cursor:grab;touch-action:none}
#lienzo.arrastrando{cursor:grabbing}
svg{overflow:visible}
.tabla{cursor:move}.tabla.moviendo{filter:drop-shadow(0 6px 10px rgba(0,0,0,.25))}
#mundo{transform-origin:0 0;position:absolute;left:0;top:0}
#barra{position:fixed;top:12px;right:12px;display:flex;gap:6px;align-items:center;background:#fff;border:1px solid #d6dbe2;
 border-radius:10px;padding:6px 8px;box-shadow:0 2px 8px rgba(0,0,0,.08);z-index:2;font-size:13px;color:#333}
#barra button{border:1px solid #d6dbe2;background:#f4f6f8;border-radius:6px;padding:4px 10px;font-size:14px;cursor:pointer}
#barra button:hover{background:#e8ecf0}
#buscar{border:1px solid #d6dbe2;border-radius:6px;padding:4px 8px;font-size:13px;width:150px}
#msg{color:#16794c;font-weight:600}
#ayuda{position:fixed;left:12px;bottom:10px;font-size:12px;color:#6b7686;z-index:2}
</style></head><body>
<div id="barra">
 <input id="buscar" placeholder="Buscar tabla…" list="lista">
 <datalist id="lista"></datalist>
 <button id="mas" title="Acercar">+</button><button id="menos" title="Alejar">−</button>
 <button id="ajustar" title="Ver todo">Ver todo</button><button id="uno" title="Tamaño real">100%</button>
 <button id="reset" title="Volver las tablas a su lugar original">Restablecer</button>
 <button id="guardarPos" title="Guardar la posición de las tablas en posiciones.json">Guardar posiciones</button>
 <button id="png" title="Descargar la imagen con el acomodo actual">PNG</button>
 <button id="svg" title="Descargar el SVG con el acomodo actual">SVG</button>
 <span id="msg"></span>
 <span id="pct">100%</span>
</div>
<div id="ayuda">Rueda: zoom · Arrastrar el fondo: mover la vista · Arrastrar una tabla: moverla · Clic en una tabla: resalta sus relaciones · Pasar sobre una línea: nombre de la FK</div>
<div id="lienzo"><div id="mundo">@@SVG@@</div></div>
<script>
const lienzo = document.getElementById('lienzo'), mundo = document.getElementById('mundo');
const W = @@W@@, H = @@H@@;
let k = 1, tx = 0, ty = 0, sel = null;
const tablas = [...document.querySelectorAll('.tabla')], rels = [...document.querySelectorAll('.rel')];
const T = {};
tablas.forEach(t => { const d = t.dataset; T[d.n] = {n:d.n, el:t, x0:+d.x, y0:+d.y, x:+d.x, y:+d.y, w:+d.w, h:+d.h}; });
const CLAVE = 'der-glucolume-posiciones';
// --- geometría de las relaciones (misma que genera generar_der.py) ---
function borde(t, a){ const cx = t.x+t.w/2, cy = t.y+t.h/2, dx = a[0]-cx, dy = a[1]-cy; if(!dx && !dy) return [cx,cy];
  const kk = Math.min(dx ? (t.w/2)/Math.abs(dx) : 1e9, dy ? (t.h/2)/Math.abs(dy) : 1e9); return [cx+dx*kk, cy+dy*kk]; }
const ln = (x1,y1,x2,y2) => `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}"/>`;
const circ = (x,y) => `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4" class="hueco"/>`;
function barra(p,u,d){ const nx=-u[1], ny=u[0], bx=p[0]+u[0]*d, by=p[1]+u[1]*d; return ln(bx+nx*6,by+ny*6,bx-nx*6,by-ny*6); }
function glifoPadre(p,u,op){ return barra(p,u,12) + (op ? circ(p[0]+u[0]*21,p[1]+u[1]*21) : barra(p,u,17)); }
function glifoHija(p,u,op,uno){ if(uno) return barra(p,u,12);
  const nx=-u[1], ny=u[0], bx=p[0]+u[0]*14, by=p[1]+u[1]*14; let o = '';
  for(const s of [-7,0,7]) o += ln(bx,by,p[0]+nx*s,p[1]+ny*s);
  return o + (op ? circ(p[0]+u[0]*22,p[1]+u[1]*22) : barra(p,u,19)); }
function dibujarRel(r){
  const h = T[r.dataset.h], p = T[r.dataset.p], d = +r.dataset.d, op = r.dataset.o==='1', uno = r.dataset.u==='1';
  const ch = [h.x+h.w/2, h.y+h.h/2], cp = [p.x+p.w/2, p.y+p.h/2];
  const dx = cp[0]-ch[0], dy = cp[1]-ch[1], dd = Math.hypot(dx,dy) || 1;
  const c = [(ch[0]+cp[0])/2 - dy/dd*d*2, (ch[1]+cp[1])/2 + dx/dd*d*2];
  const a = borde(h,c), b = borde(p,c);
  const un = (q) => { const v = [c[0]-q[0], c[1]-q[1]], l = Math.hypot(v[0],v[1]) || 1; return [v[0]/l, v[1]/l]; };
  const camino = `M${a[0].toFixed(1)} ${a[1].toFixed(1)} Q${c[0].toFixed(1)} ${c[1].toFixed(1)} ${b[0].toFixed(1)} ${b[1].toFixed(1)}`;
  const titulo = r.querySelector('title').outerHTML;
  r.innerHTML = titulo + `<path class="area" d="${camino}"/><path class="vis" d="${camino}"/>` + glifoHija(a,un(a),op,uno) + glifoPadre(b,un(b),op);
}
function ubicar(g){ g.el.setAttribute('transform', `translate(${g.x-g.x0},${g.y-g.y0})`);
  rels.forEach(r => { if(r.dataset.h===g.n || r.dataset.p===g.n) dibujarRel(r); }); }
function guardar(){ try{ const o = {}; for(const n in T) if(T[n].x!==T[n].x0 || T[n].y!==T[n].y0) o[n] = [T[n].x, T[n].y]; localStorage.setItem(CLAVE, JSON.stringify(o)); }catch(_){} }
function restaurar(){ try{ const o = JSON.parse(localStorage.getItem(CLAVE) || '{}'); for(const n in o) if(T[n]){ T[n].x = o[n][0]; T[n].y = o[n][1]; ubicar(T[n]); } }catch(_){} }
document.getElementById('reset').onclick = () => { for(const n in T){ T[n].x = T[n].x0; T[n].y = T[n].y0; ubicar(T[n]); } guardar(); };
function aplicar(){ mundo.style.transform = `translate(${tx}px,${ty}px) scale(${k})`; document.getElementById('pct').textContent = Math.round(k*100)+'%'; }
function zoomEn(f, cx, cy){ const n = Math.min(4, Math.max(0.05, k*f)); f = n/k; tx = cx - (cx-tx)*f; ty = cy - (cy-ty)*f; k = n; aplicar(); }
function ajustar(){ const a = lienzo.clientWidth, b = lienzo.clientHeight; k = Math.min(a/W, b/H); tx = (a-W*k)/2; ty = (b-H*k)/2; aplicar(); }
lienzo.addEventListener('wheel', e => { e.preventDefault(); zoomEn(e.deltaY < 0 ? 1.15 : 1/1.15, e.clientX, e.clientY); }, {passive:false});
let arr = null, movido = false, dragT = null, bajoT = null;
lienzo.addEventListener('pointerdown', e => {
  movido = false; bajoT = e.target.closest('.tabla');
  if(bajoT){ const g = T[bajoT.dataset.n]; dragT = {g, ex:e.clientX, ey:e.clientY, x:g.x, y:g.y}; }
  else { arr = {x:e.clientX, y:e.clientY, tx, ty}; lienzo.classList.add('arrastrando'); }
  lienzo.setPointerCapture(e.pointerId);
});
lienzo.addEventListener('pointermove', e => {
  if(dragT){
    const dx = e.clientX-dragT.ex, dy = e.clientY-dragT.ey;
    if(!movido && Math.abs(dx)+Math.abs(dy) <= 4) return;
    movido = true; bajoT.classList.add('moviendo');
    dragT.g.x = dragT.x + dx/k; dragT.g.y = dragT.y + dy/k; ubicar(dragT.g);
  } else if(arr){
    const dx = e.clientX-arr.x, dy = e.clientY-arr.y; if(Math.abs(dx)+Math.abs(dy)>3) movido = true;
    tx = arr.tx+dx; ty = arr.ty+dy; aplicar();
  }
});
lienzo.addEventListener('pointerup', () => {
  if(dragT && movido){ guardar(); }
  else if(!movido){ sel = bajoT && sel!==bajoT.dataset.n ? bajoT.dataset.n : null; resaltar(sel); }
  if(bajoT) bajoT.classList.remove('moviendo');
  arr = null; dragT = null; bajoT = null; lienzo.classList.remove('arrastrando');
});
document.getElementById('mas').onclick = () => zoomEn(1.3, lienzo.clientWidth/2, lienzo.clientHeight/2);
document.getElementById('menos').onclick = () => zoomEn(1/1.3, lienzo.clientWidth/2, lienzo.clientHeight/2);
document.getElementById('ajustar').onclick = ajustar;
document.getElementById('uno').onclick = () => { k = 1; tx = 20; ty = 20; aplicar(); };
document.getElementById('lista').innerHTML = tablas.map(t => `<option value="${t.dataset.n}">`).join('');
function resaltar(n){
  tablas.forEach(t => t.classList.remove('dim')); rels.forEach(r => r.classList.remove('dim','on'));
  if(!n) return;
  const vec = new Set([n]);
  rels.forEach(r => { if(r.dataset.h===n || r.dataset.p===n){ r.classList.add('on'); vec.add(r.dataset.h); vec.add(r.dataset.p); } else r.classList.add('dim'); });
  tablas.forEach(t => { if(!vec.has(t.dataset.n)) t.classList.add('dim'); });
}
document.getElementById('buscar').addEventListener('change', e => {
  const t = tablas.find(x => x.dataset.n.toLowerCase() === e.target.value.toLowerCase()); if(!t) return;
  sel = t.dataset.n; resaltar(sel);
  const g = T[t.dataset.n], r = {x:g.x, y:g.y, width:g.w, height:g.h}; k = Math.min(1.6, Math.min(lienzo.clientWidth/(r.width*2.2), lienzo.clientHeight/(r.height*2.2)));
  tx = lienzo.clientWidth/2 - (r.x+r.width/2)*k; ty = lienzo.clientHeight/2 - (r.y+r.height/2)*k; aplicar();
});
const msg = t => { const m = document.getElementById('msg'); m.textContent = t; clearTimeout(msg.t); msg.t = setTimeout(() => m.textContent = '', 4000); };
async function guardarArchivo(nombre, blob, desc, ext){
  if(window.showSaveFilePicker){
    try{ const h = await showSaveFilePicker({suggestedName:nombre, types:[{description:desc, accept:{[blob.type]:[ext]}}]});
      const w = await h.createWritable(); await w.write(blob); await w.close(); return true; }
    catch(e){ if(e.name === 'AbortError') return false; }
  }
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = nombre; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); return true;
}
document.getElementById('guardarPos').onclick = async () => {
  const o = {}; for(const n in T) o[n] = [Math.round(T[n].x), Math.round(T[n].y)];
  const ok = await guardarArchivo('posiciones.json', new Blob([JSON.stringify(o, null, 1)], {type:'application/json'}), 'Posiciones del DER', '.json');
  if(ok) msg('Guardado. Dejá posiciones.json en docs/der/ y corré generar_der.py para fijarlo.');
};
function svgActual(){
  const svg = mundo.querySelector('svg').cloneNode(true);
  svg.querySelectorAll('.dim,.on,.moviendo').forEach(e => e.classList.remove('dim','on','moviendo'));
  let x0 = 0, y0 = 0, x1 = W, y1 = H;
  for(const n in T){ const t = T[n]; x0 = Math.min(x0, t.x-60); y0 = Math.min(y0, t.y-60); x1 = Math.max(x1, t.x+t.w+60); y1 = Math.max(y1, t.y+t.h+60); }
  const ancho = Math.ceil(x1-x0), alto = Math.ceil(y1-y0);
  svg.setAttribute('viewBox', `${x0} ${y0} ${ancho} ${alto}`); svg.setAttribute('width', ancho); svg.setAttribute('height', alto);
  const fondo = svg.querySelector('.fondo'); fondo.setAttribute('x', x0); fondo.setAttribute('y', y0); fondo.setAttribute('width', ancho); fondo.setAttribute('height', alto);
  return {texto: new XMLSerializer().serializeToString(svg), ancho, alto};
}
document.getElementById('svg').onclick = async () => {
  const {texto} = svgActual();
  if(await guardarArchivo('der.svg', new Blob([texto], {type:'image/svg+xml'}), 'Imagen SVG', '.svg')) msg('SVG guardado');
};
document.getElementById('png').onclick = () => {
  const {texto, ancho, alto} = svgActual(), img = new Image();
  img.onload = () => {
    const c = document.createElement('canvas'); c.width = ancho; c.height = alto; c.getContext('2d').drawImage(img, 0, 0);
    c.toBlob(async b => { if(b && await guardarArchivo('der.png', b, 'Imagen PNG', '.png')) msg('PNG guardado'); }, 'image/png');
  };
  img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(texto);
};
addEventListener('resize', ajustar); restaurar(); ajustar();
</script></body></html>"""


def aplicar_posiciones(tablas):
    """Si existe posiciones.json (guardado desde der.html), esas posiciones mandan sobre el acomodo automático."""
    archivo = SALIDA / "posiciones.json"
    if not archivo.exists():
        return 0
    guardadas = json.loads(archivo.read_text(encoding="utf-8"))
    usadas = 0
    for n, (x, y) in guardadas.items():
        if n in tablas:
            tablas[n]["x"], tablas[n]["y"] = round(x), round(y)
            usadas += 1
    minx = min(t["x"] for t in tablas.values())
    miny = min(t["y"] for t in tablas.values())
    if minx < 60 or miny < 120:  # el título ocupa la parte de arriba
        dx, dy = max(0, 60 - minx), max(0, 120 - miny)
        for t in tablas.values():
            t["x"] += dx
            t["y"] += dy
    return usadas


def generar_png(ancho, alto):
    for exe in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if Path(exe).exists():
            subprocess.run([exe, "--headless", "--disable-gpu", "--hide-scrollbars", f"--window-size={ancho},{alto}",
                            f"--screenshot={SALIDA / 'der.png'}", (SALIDA / "der.svg").as_uri()],
                           capture_output=True, timeout=120)
            return True
    return False


def main():
    tablas, relaciones = parsear(leer_sql())
    medir(tablas, relaciones)
    acomodar(tablas, relaciones)
    usadas = aplicar_posiciones(tablas)
    svg, w, h = dibujar(tablas, relaciones)
    (SALIDA / "der.svg").write_text(svg, encoding="utf-8")
    (SALIDA / "der.html").write_text(
        PAGINA.replace("@@SVG@@", svg).replace("@@W@@", str(w)).replace("@@H@@", str(h)), encoding="utf-8")
    sin_grupo = [n for n, t in tablas.items() if "grupo" not in t]
    png = generar_png(w, h)
    print(f"{len(tablas)} tablas, {len(relaciones)} FK, lienzo {w}x{h}; posiciones guardadas aplicadas: {usadas}; "
          f"der.png {'regenerado' if png else 'NO regenerado (no se encontró Edge/Chrome)'}", "SIN GRUPO:" if sin_grupo else "", sin_grupo or "")


if __name__ == "__main__":
    main()
