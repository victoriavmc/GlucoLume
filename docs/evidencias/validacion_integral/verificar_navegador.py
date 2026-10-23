import json, sys
from playwright.sync_api import sync_playwright

import os
APP = os.environ.get("APP", "http://localhost:5173")
EVIL = os.environ.get("EVIL", "http://sitio-malicioso.example")  # otro *site*; su página se sirve con route(), sin CSP ni servidor real
API = os.environ.get("API", "http://localhost:8000")
PWD = "Glucolume#Prueba2026"
results = []
def check(name, ok, extra=""):
    results.append((name, ok, extra)); print(("OK   " if ok else "FALLA"), name, extra)

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome", args=["--no-sandbox"])
    def session(remember):
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(f"{APP}/login")
        page.get_by_label("Correo electrónico o usuario").fill("victoria")
        page.get_by_label("Contraseña", exact=True).fill(PWD)
        if remember: page.get_by_role("checkbox", name="Recordarme").check()
        with page.expect_response(lambda r: r.url.endswith("/auth/login")) as info:
            page.get_by_role("button", name="Iniciar sesión").first.click()
        return ctx, page, info.value

    for remember in (False, True):
        tag = "con Recordarme" if remember else "sin Recordarme"
        ctx, page, resp = session(remember)
        page.get_by_role("heading", name="Hola, Victoria").wait_for(timeout=15000)
        body = resp.text()
        check(f"[{tag}] el cuerpo del login no trae el refresh token", '"refreshToken":null' in body.replace(" ", ""), body[:120])
        cookies = [c for c in ctx.cookies() if c["name"] == "glucolume_refresh"]
        check(f"[{tag}] existe la cookie glucolume_refresh", len(cookies) == 1)
        c = cookies[0]
        check(f"[{tag}] HttpOnly, SameSite=Strict, Path=/api/v1/auth", c["httpOnly"] and c["sameSite"] == "Strict" and c["path"] == "/api/v1/auth", str({k: c[k] for k in ("httpOnly","sameSite","path","secure","expires")}))
        check(f"[{tag}] {'persistente' if remember else 'de sesión'}", (c["expires"] > 0) == remember, f"expires={c['expires']}")
        check(f"[{tag}] document.cookie no la ve", "glucolume_refresh" not in page.evaluate("document.cookie"))
        stored = page.evaluate("JSON.stringify([{...localStorage},{...sessionStorage}])")
        secret = c["value"][2:]
        check(f"[{tag}] el valor de la cookie no está en Web Storage", secret not in stored and "refreshToken" not in stored, stored)
        # Recargar: la sesión se recupera con la cookie (si es de sesión, sessionStorage de la pestaña conserva la marca).
        page.reload()
        page.get_by_role("heading", name="Hola, Victoria").wait_for(timeout=15000)
        check(f"[{tag}] al recargar sigue la sesión", True)
        new = [x for x in ctx.cookies() if x["name"] == "glucolume_refresh"][0]
        check(f"[{tag}] la cookie se rotó al recargar", new["value"] != c["value"] and new["value"][:2] == c["value"][:2])
        # Cierre de sesión
        with page.expect_response(lambda r: r.url.endswith("/auth/logout")):
            page.get_by_role("button", name="Cerrar sesión").click()
        page.get_by_role("heading", name="Iniciar sesión").wait_for(timeout=15000)
        check(f"[{tag}] el cierre de sesión borra la cookie", not [x for x in ctx.cookies() if x["name"] == "glucolume_refresh"])
        page.reload()
        page.get_by_role("heading", name="Iniciar sesión").wait_for(timeout=15000)
        check(f"[{tag}] tras cerrar sesión, recargar no la recupera", True)
        ctx.close()

    # CSRF desde otro sitio (127.0.0.1 es otro *site* que localhost; si EVIL y APP comparten host, la prueba no es válida)
    ctx, page, _ = session(True)
    page.get_by_role("heading", name="Hola, Victoria").wait_for(timeout=15000)
    evil = ctx.new_page()
    ctx.route(EVIL + "/**", lambda route: route.fulfill(status=200, content_type="text/html",
              body="<html><body><form id=f method=POST action='" + API + "/api/v1/auth/refresh'><input name=x value=1></form></body></html>"))
    evil.goto(EVIL + "/pagina")
    r = evil.evaluate("""async () => { try { const x = await fetch('__API__/api/v1/auth/refresh', {method:'POST', credentials:'include', headers:{'X-GlucoLume-CSRF':'1'}}); return 'status ' + x.status; } catch (e) { return 'bloqueado: ' + e.message; } }""".replace("__API__", API))
    check("[CSRF] fetch con credenciales desde otro sitio queda bloqueado por CORS", r.startswith("bloqueado"), r)
    # Formulario cross-site (sin la cabecera): el navegador no manda la cookie (SameSite=Strict) y el backend rechaza
    seen = []
    ctx.on("request", lambda rq: seen.append(rq))
    with evil.expect_navigation():
        evil.evaluate("document.getElementById('f').submit()")
    req = [rq for rq in seen if rq.url.endswith("/auth/refresh")][-1]
    hdrs = req.all_headers()
    check("[CSRF] el formulario de otro sitio no lleva la cookie", "cookie" not in hdrs, str(list(hdrs)))
    resp = req.response()
    check("[CSRF] y el backend lo rechaza (sin sesión)", resp.status in (401, 415, 422), f"status {resp.status}")
    # La sesión legítima sigue viva tras el intento
    page.reload()
    page.get_by_role("heading", name="Hola, Victoria").wait_for(timeout=15000)
    check("[CSRF] la sesión legítima no se vio afectada", True)
    browser.close()

bad = [r for r in results if not r[1]]
print("\nRESUMEN:", len(results) - len(bad), "ok /", len(results), "; fallas:", len(bad))
sys.exit(1 if bad else 0)
