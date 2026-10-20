"""Resume la salida de `docker scout cves --format packages` por paquete: cuántas críticas/altas y si tienen versión corregida.

Uso:  docker scout cves --only-severity critical,high --format packages <imagen> > salida.txt
      python docs/evidencias/scan_summary.py salida.txt
"""
import re
import sys
from collections import defaultdict

text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
packages = []
current = None
for line in text.splitlines():
    m = re.match(r"\s*(\d+)C\s+(\d+)H\s+\d+M\s+\d+L\s+(\S+)\s+(\S+)", line)
    if m:
        current = {"name": m.group(3), "version": m.group(4), "crit": int(m.group(1)), "high": int(m.group(2)), "fixed": set(), "unfixed": 0, "cves": []}
        packages.append(current)
        continue
    m = re.match(r"\s*x (CRITICAL|HIGH) (CVE-[\d-]+|GHSA-[\w-]+)", line)
    if m and current is not None:
        current["cves"].append(m.group(2))
    m = re.match(r"\s*Fixed version\s*:\s*(.+)", line)
    if m and current is not None:
        value = m.group(1).strip()
        if value.startswith("not fixed"):
            current["unfixed"] += 1
        else:
            current["fixed"].add(value)

packages.sort(key=lambda p: (-p["crit"], -p["high"], p["name"]))
print(f"{'paquete':28} {'versión':28} {'C':>3} {'H':>3} {'sin fix':>8}  corregida en")
for p in packages:
    print(f"{p['name'][:28]:28} {p['version'][:28]:28} {p['crit']:>3} {p['high']:>3} {p['unfixed']:>8}  {', '.join(sorted(p['fixed']))[:60]}")
print(f"\nTotal: {sum(p['crit'] for p in packages)} críticas, {sum(p['high'] for p in packages)} altas, "
      f"{sum(p['unfixed'] for p in packages)} sin corrección upstream, {len(packages)} paquetes")
