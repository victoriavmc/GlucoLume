import json, sys
from app.main import app
spec = app.openapi()
comps = spec.get("components", {}).get("schemas", {})
PEOR = "é"  # carácter no ASCII: JSON lo escapa a 6 bytes (é)
def inst(s, worst, depth=0):
    if depth > 8: return None
    if "$ref" in s: return inst(comps[s["$ref"].split("/")[-1]], worst, depth + 1)
    if "allOf" in s:
        out = {}
        for x in s["allOf"]:
            v = inst(x, worst, depth + 1)
            if isinstance(v, dict): out.update(v)
        return out
    for k in ("anyOf", "oneOf"):
        if k in s:
            opts = [o for o in s[k] if o.get("type") != "null"]
            if not opts: return None
            # elige la rama más larga (string con pattern sin max -> 32 chars de ceros)
            cands = [inst(o, worst, depth + 1) for o in opts]
            return max(cands, key=lambda v: len(json.dumps(v)))
    t = s.get("type")
    if "enum" in s: return max(s["enum"], key=lambda e: len(str(e)))
    if t == "string":
        if "pattern" in s and "maxLength" not in s: return "0" * 32  # patrón numérico: caso razonable
        n = s.get("maxLength", 40)
        return (PEOR if worst else "x") * min(n, 4096)
    if t == "integer": return 1234567
    if t == "number": return 1234.5
    if t == "boolean": return True
    if t == "array":
        n = s.get("maxItems", 3)
        return [inst(s.get("items", {}), worst, depth + 1) for _ in range(min(n, 2000))]
    if t == "object" or "properties" in s:
        return {k: inst(v, worst, depth + 1) for k, v in s.get("properties", {}).items() if k in s.get("required", [])} | {k: inst(v, worst, depth + 1) for k, v in list(s.get("properties", {}).items())[:40] if k not in s.get("required", [])}
    return None
print("OPERACION\tTIPO\tBYTES_TIPICO_MAX\tBYTES_PEOR_CARACTER")
for path, ops in spec["paths"].items():
    for m, op in ops.items():
        if m not in ("post", "put", "patch"): continue
        rb = op.get("requestBody")
        if not rb: continue
        sch = rb["content"]["application/json"]["schema"]
        a = len(json.dumps(inst(sch, False), ensure_ascii=True).encode())
        b = len(json.dumps(inst(sch, True), ensure_ascii=True).encode())
        print(f"{m.upper()} {path}\tjson\t{a}\t{b}")
