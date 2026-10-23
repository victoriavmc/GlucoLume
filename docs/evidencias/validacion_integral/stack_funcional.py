"""Validación funcional de la versión INTEGRADA sobre el stack Docker (db + backend + frontend[Nginx] + redis), solo por HTTP desde el anfitrión.

Todo pasa por Nginx -> backend (contenedor, sistema de archivos de solo lectura) -> SQL Server con la cuenta de mínimo privilegio. Datos sintéticos.
Variables: STACK_URL (http://localhost:18080), STACK_DIR (proyecto compose temporal), MAILS (JSONL del SMTP falso), GLUCOLUME_VERSION.
Exige haber levantado el stack con `stack_docker.sh`. No ejecuta purgas ni toca el servicio «lifecycle».
"""
import json, os, re, subprocess, sys, time, urllib.error, urllib.request, http.cookiejar
from pathlib import Path

URL = os.environ.get("STACK_URL", "http://localhost:18080")
STACK = os.environ["STACK_DIR"]
MAILS = Path(os.environ["MAILS"])
SECRETS = dict(l.strip().split("=", 1) for l in Path(STACK, "..", "stack_secrets.txt").read_text().splitlines() if "=" in l)
FILES = os.environ.get("STACK_COMPOSE_FILES", "compose.yaml,compose.redis.yaml,compose.ensayo-smtp.yaml").split(",")
PROFILES = os.environ.get("STACK_PROFILES", "db,redis").split(",")
COMPOSE = ["docker", "compose"] + [x for p in PROFILES for x in ("--profile", p)] + [x for f in FILES for x in ("-f", f)]
SERVICES = os.environ.get("STACK_SERVICES", "db,backend,frontend,redis").split(",")
INSECURE = os.environ.get("STACK_INSECURE") == "1"  # HTTPS con la CA interna de Caddy (certificado de prueba): no se verifica
ENVC = {**os.environ, "GLUCOLUME_VERSION": os.environ.get("GLUCOLUME_VERSION", "validacion")}
results = []
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))
import pyotp  # noqa: E402


def check(name, ok, extra=""):
    results.append(bool(ok))
    print(("OK    " if ok else "FALLA ") + name + (f"  [{extra}]" if extra else ""), flush=True)


class Client:
    """Cliente HTTP con su propia jarra de cookies (como un navegador): envía la cabecera anti-CSRF del frontend y recuerda el access token."""
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        import ssl
        handlers = [urllib.request.HTTPCookieProcessor(self.jar)]
        if INSECURE:
            ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
            handlers.append(urllib.request.HTTPSHandler(context=ctx))
        self.opener = urllib.request.build_opener(*handlers)
        self.token = None

    def req(self, method, path, body=None, headers=None, cookie_mode=True, raw=False):
        h = {"Accept": "application/json", **(headers or {})}
        if cookie_mode and path.startswith("/api/v1/auth/"):
            h["X-GlucoLume-CSRF"] = "1"
        if self.token and "Authorization" not in h:
            h["Authorization"] = f"Bearer {self.token}"
        data = json.dumps(body).encode() if body is not None else None
        if data is not None:
            h["Content-Type"] = "application/json"
        r = urllib.request.Request(URL + path, data=data, method=method.upper(), headers=h)
        try:
            resp = self.opener.open(r, timeout=20)
            code, text, hdrs = resp.status, resp.read().decode(), resp.headers
        except urllib.error.HTTPError as e:
            code, text, hdrs = e.code, e.read().decode(), e.headers
        try:
            js = json.loads(text) if text and not raw else None
        except ValueError:
            js = None
        return code, js, text, hdrs

    def cookie(self, name="glucolume_refresh"):
        return next((c for c in self.jar if c.name == name), None)


def sa(query, db="GlucoLume"):
    r = subprocess.run(["docker", "exec", "-e", f"SQLCMDPASSWORD={SECRETS['SA']}", "glucolume-db-1", "/opt/mssql-tools18/bin/sqlcmd", "-C", "-I", "-S", "localhost", "-U", "sa",
                        "-d", db, "-h", "-1", "-W", "-b", "-Q", "SET NOCOUNT ON; " + query], capture_output=True, text=True)
    return r.stdout.strip()


def last_mail(to, subject_part, since):
    for _ in range(40):
        lines = MAILS.read_text().splitlines()[since:]
        for line in reversed(lines):
            m = json.loads(line)
            if to in m["to"] and subject_part.lower() in m["subject"].lower():
                return m
        time.sleep(0.5)
    return None


def token_of(mail):
    return re.search(r"token=([A-Za-z0-9_\-]+)", mail["body"]).group(1)


def register_and_verify(c, email, usuario, tipo="CONSUMIDOR_FINAL", nombre="Persona", apellido="Sintetica"):
    since = len(MAILS.read_text().splitlines())
    code, js, text, _ = c.req("post", "/api/v1/auth/register", {"nombre": nombre, "apellido": apellido, "correoElectronico": email, "password": PWD, "tipoCuenta": tipo,
                                                                 "aceptaPoliticaPrivacidad": True, "usuario": usuario})
    mail = last_mail(email, "verific", since)
    ok = code == 201 and mail is not None
    if ok:
        vcode, _, _, _ = c.req("get", f"/api/v1/auth/verify-email?token={token_of(mail)}")
        ok = vcode == 200
    return ok, code


def login(c, ident, remember=False):
    h = {"X-GlucoLume-Recordarme": "1"} if remember else {}
    code, js, text, hdrs = c.req("post", "/api/v1/auth/login", {"identificador": ident, "password": PWD}, headers=h)
    if code == 200 and js["estado"] == "AUTENTICADO":
        c.token = js["tokens"]["accessToken"]
    return code, js, hdrs


PWD = "Zafiro#Cobalto2026"
RUN = str(int(time.time()))[-6:]  # sufijo único: el script se puede repetir sobre la misma base


def cuit(prefix="30", number="71234567"):
    body = prefix + number
    remainder = 11 - sum(int(d) * w for d, w in zip(body, (5, 4, 3, 2, 7, 6, 5, 4, 3, 2))) % 11
    return body + str({11: 0, 10: 9}.get(remainder, remainder))


c0 = Client()

print("== 1. Infraestructura: Nginx -> backend -> SQL Server")
code, _, text, h = c0.req("get", "/", raw=True)
check("SPA servida por Nginx (index.html)", code == 200 and "<div id=\"root\">" in text, str(code))
check("encabezados de seguridad de Nginx (CSP estricta, DENY, nosniff, sin versión)", "default-src 'self'" in (h.get("Content-Security-Policy") or "") and "unsafe-inline" not in (h.get("Content-Security-Policy") or "")
      and h.get("X-Frame-Options") == "DENY" and h.get("X-Content-Type-Options") == "nosniff" and "/" not in (h.get("Server") or "nginx/"))
code, _, text, h = c0.req("get", "/nginx-health", raw=True)
check("/nginx-health", code == 200)
code, js, _, h = c0.req("get", "/api/v1/auth/me")
check("la API responde a través del proxy (sin sesión: 401)", code == 401, str(code))
tablas = sa("SELECT COUNT(*) FROM sys.tables")
check("SQL Server del contenedor con el esquema v5", tablas == "34", tablas)
who = subprocess.run(["docker", "exec", "glucolume-backend-1", "python", "-c",
                      "from app.db.session import getEngine;from sqlalchemy import text;c=getEngine().connect();print(c.execute(text('SELECT SUSER_NAME()')).scalar(), c.execute(text('SELECT IS_ROLEMEMBER(\\'db_datawriter\\')')).scalar(), c.execute(text('SELECT IS_ROLEMEMBER(\\'rol_glucolume_api\\')')).scalar())"],
                     capture_output=True, text=True).stdout.split()
check("el backend en contenedor se conecta a SQL Server como glucolume_app, sin roles fijos y con rol_glucolume_api", who[:1] == ["glucolume_app"] and who[1:] in (["0", "1"], ["None", "1"]) , " ".join(who))

print("== 2. Rol individual: registro, verificación, sesión, MFA, cookies")
ok, code = register_and_verify(c0, f"ana.individual{RUN}@example.com", f"anaindividual{RUN}")
check("registro + correo de verificación (SMTP falso con STARTTLS) + verificación", ok, str(code))
c = Client()
code, js, h = login(c, f"anaindividual{RUN}")
ck = c.cookie()
check("login: cookie HttpOnly, sin refresh token en el cuerpo", code == 200 and js["tokens"]["refreshToken"] is None and ck is not None and "HttpOnly" in (h.get("Set-Cookie") or "") and "samesite=strict" in (h.get("Set-Cookie") or "").lower(), (h.get("Set-Cookie") or "")[:90])
if URL.startswith("https"):
    check("HTTPS: la cookie lleva el atributo Secure y HSTS llega desde el proxy", "; secure" in (h.get("Set-Cookie") or "").lower() and "max-age=31536000" in (h.get("Strict-Transport-Security") or ""), (h.get("Set-Cookie") or "")[-60:])
code, js, _, _ = c.req("get", "/api/v1/auth/me")
check("/auth/me con el access token", code == 200 and js["usuario"]["usuario"] == f"anaindividual{RUN}")
code, js, _, _ = c.req("post", "/api/v1/auth/refresh")
check("refresh por cookie rota el token", code == 200 and js["refreshToken"] is None)
c.token = js["accessToken"]  # la rotación abre una sesión nueva: el access token anterior queda atado a la sesión vieja
code, js, text, _ = c.req("post", "/api/v1/auth/mfa/setup")
print("   mfa/setup:", code, text[:120])
secret = js["secreto"]
code, js, _, _ = c.req("post", "/api/v1/auth/mfa/enable", {"codigo": pyotp.TOTP(secret).now()})
recovery = js["codigosRecuperacion"]
check("MFA: activación con TOTP y 10 códigos de recuperación", code == 200 and len(recovery) == 10)
c2 = Client()
code, js, _ = login(c2, f"anaindividual{RUN}")
check("con MFA el login devuelve un desafío y ninguna cookie", js["estado"] == "MFA_REQUERIDO" and c2.cookie() is None)
code, js, _, _ = c2.req("post", "/api/v1/auth/mfa/verify", {"challengeToken": js["challengeToken"], "codigo": pyotp.TOTP(secret).at(time.time() + 30)}, headers={"X-GlucoLume-Recordarme": "1"})
c2.token = js["tokens"]["accessToken"] if code == 200 else None
ck = c2.cookie()
check("MFA: verificación y sesión «recordarme» (cookie persistente)", code == 200 and ck is not None and ck.expires is not None, str(code))
code, _, _, _ = c2.req("post", "/api/v1/auth/logout")
check("cierre de sesión: 204 y la cookie se borra", code == 204 and c2.cookie() is None, str(code))
code, _, _, _ = c2.req("get", "/api/v1/auth/me")
check("tras el cierre, el access token ya no sirve", code == 401)
code, _, _, _ = c.req("post", "/api/v1/auth/refresh", headers={"Origin": "https://sitio-malicioso.example"})
check("refresh con Origin ajeno: rechazado", code == 401)

print("== 3. Rol institucional: propietario, moderador, operador y límites entre cuentas")
okb, _ = register_and_verify(c0, f"beto.propietario{RUN}@example.com", f"betopropietario{RUN}", "USUARIO_INSTITUCIONAL", "Beto")
okc, _ = register_and_verify(c0, f"clara.moderadora{RUN}@example.com", f"claramoderadora{RUN}", "USUARIO_INSTITUCIONAL", "Clara")
oke, _ = register_and_verify(c0, f"erik.operador{RUN}@example.com", f"erikoperador{RUN}", "USUARIO_INSTITUCIONAL", "Erik")
check("registro de tres cuentas institucionales", okb and okc and oke)
owner, mod, oper = Client(), Client(), Client()
login(owner, f"betopropietario{RUN}"); login(mod, f"claramoderadora{RUN}"); login(oper, f"erikoperador{RUN}")
code, js, text, _ = owner.req("post", "/api/v1/institutions", {"nombre": f"Clínica Sintética {RUN}", "tipoInstitucion": "CLINICA", "identificadorLegal": cuit("30", RUN.zfill(8)), "tipoIdentificadorLegal": "CUIT"})
inst = js.get("idInstitucion") if js else None
check("el propietario crea una institución", code in (200, 201) and inst, f"{code} {text[:100]}")


def pending_invitation(client):
    code, js, _, _ = client.req("get", "/api/v1/institutions/invitations")
    items = js if isinstance(js, list) else (js or {}).get("items", [])
    return items[0].get("idInstitucionUsuario") if items else None


since = len(MAILS.read_text().splitlines())
code, js, text, _ = owner.req("post", f"/api/v1/institutions/{inst}/operators", {"correoElectronico": f"erik.operador{RUN}@example.com"})
check("el PROPIETARIO no invita operadores directamente (rol: solo moderadores)", code == 403, f"{code} {text[:90]}")
code, js, text, _ = owner.req("post", f"/api/v1/institutions/{inst}/moderators", {"correoElectronico": f"clara.moderadora{RUN}@example.com", "funcionProfesional": "MEDICO"})
check("el propietario invita a una moderadora (se envía el correo)", code in (200, 201, 202) and last_mail(f"clara.moderadora{RUN}@example.com", "invit", since) is not None, f"{code} {text[:100]}")
inv = pending_invitation(mod)
code, _, text, _ = mod.req("post", f"/api/v1/institutions/invitations/{inv}/accept") if inv else (0, None, "sin invitación", None)
check("la moderadora acepta la invitación", code in (200, 204), f"{code} {text[:100]}")
code, js, text, _ = mod.req("post", f"/api/v1/institutions/{inst}/operators", {"correoElectronico": f"erik.operador{RUN}@example.com", "funcionProfesional": "ENFERMERO"})
check("la moderadora invita a un operador", code in (200, 201, 202), f"{code} {text[:100]}")
inv = pending_invitation(oper)
code, _, text, _ = oper.req("post", f"/api/v1/institutions/invitations/{inv}/accept") if inv else (0, None, "sin invitación", None)
check("el operador acepta la invitación", code in (200, 204), f"{code} {text[:100]}")
code, js, text, _ = owner.req("get", f"/api/v1/institutions/{inst}/members")
members = js if isinstance(js, list) else (js or {}).get("items", [])
roles = sorted({m.get("rol") or m.get("rolInstitucional") for m in members if isinstance(m, dict)})
check("el propietario ve a las tres personas con sus roles", code == 200 and len(members) >= 3, f"{len(members)} miembros, roles {roles}")
code, js, text, _ = oper.req("post", f"/api/v1/institutions/{inst}/moderators", {"correoElectronico": "otro@example.com"})
check("rol operador: NO puede invitar moderadores (403)", code == 403, f"{code} {text[:80]}")
code, js, text, _ = oper.req("post", f"/api/v1/institutions/{inst}/operators", {"correoElectronico": "otro@example.com"})
check("rol operador: NO puede invitar operadores (403)", code == 403, f"{code} {text[:80]}")
oper_member = next((m for m in members if isinstance(m, dict) and "erik.operador" in json.dumps(m).lower()), {})
code, js, text, _ = mod.req("post", f"/api/v1/institutions/{inst}/patients", {"nombre": "Paciente", "apellido": "Sintetico", "sexoModelo": "FEMENINO", "idInstitucionUsuarioResponsable": oper_member.get("idInstitucionUsuario")})
check("la moderadora da de alta un paciente SINTÉTICO con el operador como responsable", code in (200, 201), f"{code} {text[:110]}")
code, js, text, _ = oper.req("get", f"/api/v1/institutions/{inst}/patients")
check("el operador ve su paciente asignado", code == 200, str(code))
code, js, text, _ = c.req("get", f"/api/v1/institutions/{inst}/members")
check("una cuenta individual ajena no ve la institución (403/404)", code in (403, 404), str(code))
code, _, _, _ = c.req("get", "/api/v1/platform/me")
check("cuenta común: /platform/me rechazado", code in (401, 403))

print("== 4. Rol grupal")
okd, _ = register_and_verify(c0, f"dario.familia{RUN}@example.com", f"dariofamilia{RUN}", "CONSUMIDOR_FINAL", "Dario")
dario = Client(); login(dario, f"dariofamilia{RUN}")
code, js, text, _ = c.req("post", "/api/v1/groups", {"nombre": "Familia Sintética"})
grp = js.get("idGrupo") if js else None
check("la cuenta individual crea un grupo familiar", code in (200, 201) and grp, f"{code} {text[:100]}")
since = len(MAILS.read_text().splitlines())
code, js, text, _ = c.req("post", f"/api/v1/groups/{grp}/invitations", {"correoElectronico": f"dario.familia{RUN}@example.com"})
check("invita a otra persona", code in (200, 201, 202), f"{code} {text[:100]}")
code, js, _, _ = dario.req("get", "/api/v1/groups/invitations")
gi = (js or [{}])[0].get("idGrupoUsuario") if isinstance(js, list) and js else None
code, _, text, _ = dario.req("post", f"/api/v1/groups/invitations/{gi}/accept") if gi else (0, None, "sin invitación", None)
check("la persona invitada acepta", code in (200, 204), f"{code} {text[:80]}")
code, js, _, _ = dario.req("get", f"/api/v1/groups/{grp}/members")
check("ambos son miembros del grupo", code == 200 and len(js if isinstance(js, list) else js.get("items", [])) >= 2, str(code))
code, _, _, _ = owner.req("get", f"/api/v1/groups/{grp}/members")
check("una cuenta ajena al grupo no lo ve (403/404)", code in (403, 404), str(code))

print("== 5. Puentes: credencial individual (CLI con la cuenta de conservación) y autenticación por HTTP")
sa(f"INSERT INTO dbo.Dispositivo (codigoDispositivo, modeloSensor) VALUES (N'GLUCOLUME-STACK-{RUN}-01', N'MAX30100'), (N'GLUCOLUME-STACK-{RUN}-02', N'MAX30100')")
r = subprocess.run(COMPOSE + ["run", "--rm", "--no-deps", "-T", "--entrypoint", "python", "lifecycle", "-m", "app.cli.bridgeTokens", "crear", "--nombre", "Puente stack", "--dispositivo",
                              f"GLUCOLUME-STACK-{RUN}-01", "--dias", "30", "--confirmo-base", "GlucoLume"], cwd=STACK, env=ENVC, capture_output=True, text=True)
tok = r.stdout.strip().splitlines()[-1] if r.returncode == 0 else ""
check("la CLI (contenedor one-off con la cuenta de conservación; el servicio lifecycle NO se levanta) crea la credencial", r.returncode == 0 and len(tok) > 30, (r.stdout + r.stderr)[-150:])
b = Client(); b.token = None
code, js, text, _ = b.req("post", "/api/v1/acquisition/bridge/check", {"codigoDispositivo": f"GLUCOLUME-STACK-{RUN}-01"}, headers={"X-Bridge-Token": tok})
check("el puente se autentica en su dispositivo a través del proxy", code == 200, f"{code} {text[:80]}")
code, _, _, _ = b.req("post", "/api/v1/acquisition/bridge/check", {"codigoDispositivo": f"GLUCOLUME-STACK-{RUN}-02"}, headers={"X-Bridge-Token": tok})
check("fuera del alcance de su dispositivo: 403", code == 403)
code, _, _, _ = b.req("post", "/api/v1/acquisition/bridge/check", {"codigoDispositivo": f"GLUCOLUME-STACK-{RUN}-01"}, headers={"X-Bridge-Token": "x" * 40})
check("token inventado: rechazado", code in (401, 403))
usado = sa(f"SELECT COUNT(*) FROM dbo.PuenteCredencial WHERE fechaUltimoUso IS NOT NULL AND codigoDispositivo = N'GLUCOLUME-STACK-{RUN}-01'")
check("la API (cuenta restringida) anotó fechaUltimoUso", usado == "1", usado)
lc = subprocess.run(["docker", "ps", "-a", "--format", "{{.Names}}"], capture_output=True, text=True).stdout
check("el servicio «lifecycle» NO está en ejecución (no hay purgas)", "glucolume-lifecycle-1" not in lc)

print("== 6. Redis y límites de solicitudes")
rcli = lambda *a: subprocess.run(["docker", "exec", "glucolume-redis-1", "redis-cli", "-a", SECRETS["REDIS"], "--no-auth-warning", *a], capture_output=True, text=True).stdout.strip()
codes = []
for i in range(75):
    cc = Client()
    code, _, _, hh = cc.req("post", "/api/v1/auth/login", {"identificador": "nadie.sintetico", "password": "Clave#Falsa2026"})
    codes.append(code); time.sleep(0.04)
check("el límite de /login por IP responde 429 al pasar la cuota (60 por 10 min)", codes.count(429) >= 10 and codes.count(401) <= 60, f"401={codes.count(401)} 429={codes.count(429)}")
keys = rcli("--scan").split()
check("las cuentas del límite están en Redis, sin IP ni identificadores en claro", len(keys) > 0 and not any("nadie" in k or "127.0.0.1" in k or "172." in k for k in keys), f"{len(keys)} claves")
subprocess.run(["docker", "stop", "glucolume-redis-1"], capture_output=True)
t0 = time.time(); cc = Client(); code, _, _, _ = cc.req("get", "/api/v1/auth/me")
check("con Redis detenido la API sigue respondiendo (política local)", code == 401 and time.time() - t0 < 5, f"{code} en {time.time()-t0:.1f}s")
subprocess.run(["docker", "start", "glucolume-redis-1"], capture_output=True); time.sleep(8)
check("Redis vuelve", rcli("ping") == "PONG")

print("== 7. Persistencia de la base y reinicio del stack (sin perder datos)")
antes = sa("SELECT COUNT(*) FROM dbo.Usuario")
subprocess.run(COMPOSE + ["down"], cwd=STACK, env=ENVC, capture_output=True)
vols = subprocess.run(["docker", "volume", "ls", "--format", "{{.Name}}"], capture_output=True, text=True).stdout
check("`compose down` (sin -v) conserva el volumen mssql-data", "glucolume_mssql-data" in vols)
r = subprocess.run(COMPOSE + ["up", "-d", "--no-build"] + SERVICES, cwd=STACK, env=ENVC, capture_output=True, text=True)
for _ in range(60):
    st = subprocess.run(["docker", "ps", "--format", "{{.Names}}={{.Status}}"], capture_output=True, text=True).stdout
    if st.count("(healthy)") >= 4 and "starting" not in st:
        break
    time.sleep(5)
despues = sa("SELECT COUNT(*) FROM dbo.Usuario")
check("los servicios con healthcheck vuelven healthy y los datos siguen (usuarios)", st.count("(healthy)") >= 4 and antes == despues and int(despues) >= 4, f"{antes} -> {despues}")
cc = Client(); code, js, _ = login(cc, f"anaindividual{RUN}")
check("login después del reinicio (la base persistente y el backend se recuperaron)", code == 200 or (js and js.get("estado") == "MFA_REQUERIDO"), str(code))

print("== 8. Logs")
bad = {}
for name in ("glucolume-backend-1", "glucolume-frontend-1", "glucolume-redis-1", "glucolume-db-1"):
    out = subprocess.run(["docker", "logs", name], capture_output=True, text=True)
    txt = out.stdout + out.stderr
    hits = [l for l in txt.splitlines() if re.search(r"Traceback|CRITICAL|\bERROR\b| 500 |\[error\]|\[emerg\]|\[crit\]", l) and "Login failed" not in l]
    bad[name] = hits
    print(f"   {name}: {len(txt.splitlines())} líneas, {len(hits)} con error", ("→ " + hits[0][:140]) if hits else "")
check("sin Traceback, 500 ni errores de Nginx en backend/frontend/redis", not bad["glucolume-backend-1"] and not bad["glucolume-frontend-1"] and not bad["glucolume-redis-1"])
print(f"\nRESUMEN: {sum(results)} correctas, {len(results) - sum(results)} con falla")
sys.exit(0 if all(results) else 1)
