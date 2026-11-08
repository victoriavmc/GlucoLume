import json, sys
base = json.load(open(sys.argv[1])); head = json.load(open(sys.argv[2]))
def ops(doc):
    out = {}
    for ruta, metodos in doc["paths"].items():
        for m, op in metodos.items():
            out[(m.upper(), ruta)] = op
    return out
ob, oh = ops(base), ops(head)
print("operaciones base:", len(ob), "head:", len(oh))
print("solo en base:", sorted(set(ob) - set(oh)))
print("solo en head:", sorted(set(oh) - set(ob)))
def resp_codes(op): return sorted(op.get("responses", {}).keys())
def params(op): return sorted((p["name"], p["in"], p.get("required", False)) for p in op.get("parameters", []))
def body_req(op):
    return op.get("requestBody", {}).get("required", False)
cambios_respuesta, cambios_param, cambios_body = [], [], []
for k in sorted(set(ob) & set(oh)):
    if resp_codes(ob[k]) != resp_codes(oh[k]): cambios_respuesta.append((k, resp_codes(ob[k]), resp_codes(oh[k])))
    if params(ob[k]) != params(oh[k]): cambios_param.append((k, params(ob[k]), params(oh[k])))
    if body_req(ob[k]) != body_req(oh[k]): cambios_body.append((k, body_req(ob[k]), body_req(oh[k])))
print("cambios de códigos de respuesta:", len(cambios_respuesta))
for c in cambios_respuesta: print("  ", c)
print("cambios de parámetros:", len(cambios_param))
for c in cambios_param: print("  ", c)
print("cambios de requestBody.required:", len(cambios_body))
for c in cambios_body: print("  ", c)
# Restricciones de esquema: comparar cada componente por nombre
def restricciones(schema):
    keys = ("maxLength","minLength","maxItems","minItems","pattern","minimum","maximum","enum","format")
    return {k: schema[k] for k in keys if k in schema}
cs, ce = base.get("components", {}).get("schemas", {}), head.get("components", {}).get("schemas", {})
print("componentes solo en base:", sorted(set(cs)-set(ce)))
print("componentes solo en head:", sorted(set(ce)-set(cs)))
cambios_restr = []
for nombre in sorted(set(cs) & set(ce)):
    pb = cs[nombre].get("properties", {}); ph = ce[nombre].get("properties", {})
    if sorted(pb) != sorted(ph): cambios_restr.append((nombre, "campos", sorted(set(pb)^set(ph))))
    for campo in sorted(set(pb) & set(ph)):
        rb, rh = restricciones(pb[campo]), restricciones(ph[campo])
        if rb != rh: cambios_restr.append((nombre, campo, rb, rh))
        if pb[campo].get("type") != ph[campo].get("type"): cambios_restr.append((nombre, campo, "tipo", pb[campo].get("type"), ph[campo].get("type")))
    if cs[nombre].get("required", []) != ce[nombre].get("required", []): cambios_restr.append((nombre, "required", cs[nombre].get("required", []), ce[nombre].get("required", [])))
print("cambios de restricciones o campos en esquemas:", len(cambios_restr))
for c in cambios_restr: print("  ", c)
