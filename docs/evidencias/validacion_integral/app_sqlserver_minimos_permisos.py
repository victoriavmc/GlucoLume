"""H-02 + H-16 + H-09 + H-04 de punta a punta: la API REAL y las herramientas REALES contra un SQL Server 2022 DESCARTABLE (Docker), usando las
cuentas de mínimo privilegio que crean los scripts del proyecto (glucolume_app sin roles fijos; glucolume_jobs para conservación). Datos sintéticos.

Variables: GL_MSSQL_CONTAINER (nombre del contenedor descartable), GL_MSSQL_PORT (publicado en 127.0.0.1), GL_MSSQL_SA_PW.
Falla si alguna operación de negocio recibe un error de permisos (229/230/262), que sería un permiso faltante en GlucoLume_permisos.sql.
"""
import json, os, re, subprocess, sys, secrets
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
C, PORT, SA = os.environ["GL_MSSQL_CONTAINER"], os.environ.get("GL_MSSQL_PORT", "14331"), os.environ["GL_MSSQL_SA_PW"]
DB = "GlucoLume_Minimos"
API_PW, JOBS_PW = "Api" + secrets.token_hex(8) + "#1", "Job" + secrets.token_hex(8) + "#1"
results = []


def check(name, ok, extra=""):
    results.append(ok)
    print(("OK    " if ok else "FALLA ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def sa(query=None, db="master", file=None, **kw):
    cmd = ["docker", "exec", C, "/opt/mssql-tools18/bin/sqlcmd", "-C", "-I", "-S", "localhost", "-U", "sa", "-P", SA, "-d", db, "-b"]
    cmd += (["-i", file] if file else ["-Q", query])
    for k, v in kw.items():
        cmd += []
    return subprocess.run(cmd, capture_output=True, text=True)


# --- Preparación de la base descartable --------------------------------------------------------------------------------------------------
sa(f"IF DB_ID('{DB}') IS NOT NULL BEGIN ALTER DATABASE [{DB}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{DB}] END")
assert sa(f"CREATE DATABASE [{DB}] COLLATE Modern_Spanish_CI_AS").returncode == 0
v5 = subprocess.run(["iconv", "-f", "UTF-16LE", "-t", "UTF-8", str(REPO / "database/reference/GlucoLume_DB_v5.sql")], capture_output=True, text=True).stdout
v5 = v5.lstrip("﻿").replace("[GlucoLume]", f"[{DB}]", 1)
Path("/tmp/v5_min.sql").write_text(v5)
subprocess.run(["docker", "exec", C, "mkdir", "-p", "/tmp/sql"])
for name, src in (("v5_min.sql", "/tmp/v5_min.sql"), ("perm.sql", REPO / "database/reference/GlucoLume_permisos.sql"),
                  ("quitar.sql", REPO / "database/reference/GlucoLume_permisos_quitar_roles_fijos.sql"), ("matriz.sql", REPO / "database/reference/MATRIZ.SQL")):
    subprocess.run(["docker", "cp", str(src), f"{C}:/tmp/sql/{name}"], check=True)
check("esquema v5 cargado", sa(db=DB, file="/tmp/sql/v5_min.sql").returncode == 0)
sa(db=DB, file="/tmp/sql/matriz.sql")
sa(f"IF SUSER_ID('glucolume_app') IS NOT NULL DROP LOGIN glucolume_app; IF SUSER_ID('glucolume_jobs') IS NOT NULL DROP LOGIN glucolume_jobs; "
   f"CREATE LOGIN glucolume_app WITH PASSWORD='{API_PW}', CHECK_POLICY=OFF; CREATE LOGIN glucolume_jobs WITH PASSWORD='{JOBS_PW}', CHECK_POLICY=OFF;")
r = subprocess.run(["docker", "exec", C, "/opt/mssql-tools18/bin/sqlcmd", "-C", "-I", "-S", "localhost", "-U", "sa", "-P", SA, "-d", DB, "-b", "-i", "/tmp/sql/perm.sql",
                    "-v", "API_LOGIN=glucolume_app", "JOBS_LOGIN=glucolume_jobs", "CONFIRMAR=APLICAR_PERMISOS_GLUCOLUME"], capture_output=True, text=True)
check("permisos mínimos aplicados (GlucoLume_permisos.sql)", r.returncode == 0, r.stderr[:100])
roles = sa("SET NOCOUNT ON; SELECT r.name FROM sys.database_role_members rm JOIN sys.database_principals r ON r.principal_id=rm.role_principal_id "
           "JOIN sys.database_principals m ON m.principal_id=rm.member_principal_id WHERE m.name='glucolume_app'", db=DB).stdout
check("la API es miembro solo de rol_glucolume_api (sin db_datareader/db_datawriter)", "rol_glucolume_api" in roles and "db_data" not in roles)
# Un dispositivo del inventario al que atar el puente
assert sa("INSERT INTO dbo.Dispositivo (codigoDispositivo, modeloSensor) VALUES (N'GLUCOLUME-SINT-01', N'MAX30100'), (N'GLUCOLUME-SINT-02', N'MAX30100')", db=DB).returncode == 0

# --- Entorno de la API con las cuentas restringidas ---------------------------------------------------------------------------------------
from cryptography.fernet import Fernet
ENV = {**os.environ, "API_ENV": "development", "DB_HOST": "localhost", "DB_PORT": PORT, "DB_NAME": DB, "DB_USER": "glucolume_app", "DB_PASSWORD": API_PW,
       "DB_JOBS_USER": "glucolume_jobs", "DB_JOBS_PASSWORD": JOBS_PW, "DB_TRUST_SERVER_CERTIFICATE": "true", "JWT_SECRET": secrets.token_urlsafe(48),
       "SESSION_SECRET": secrets.token_urlsafe(48), "MFA_ENCRYPTION_KEY": Fernet.generate_key().decode(), "FRONTEND_URL": "http://localhost:5173",
       "API_BASE_URL": "http://localhost:8000", "GLUCOLUME_ENV_FILE": str(BACKEND / "tests" / "nonexistent.env"),
       "BRIDGE_ALLOW_SHARED_TOKEN": "false", "PYTHONPATH": str(BACKEND), "SMTP_HOST": "127.0.0.1", "SMTP_PORT": "2525", "SMTP_USERNAME": "sint", "SMTP_PASSWORD": "sint",
       "AUDIT_RETENTION_MONTHS": "0", "PERSONNEL_RETENTION_MONTHS": "0"}
for k in ("TEST_SQLSERVER_URL", "TEST_SQLSERVER_CONFIRM"):
    ENV.pop(k, None)
os.environ.update({k: v for k, v in ENV.items() if k.startswith(("DB_", "JWT", "SESSION", "MFA", "FRONTEND", "API_", "BRIDGE", "SMTP", "GLUCOLUME", "AUDIT", "PERSONNEL"))})
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))
from fastapi.testclient import TestClient
from app.main import app
from app.integrations.email import sender
from app.services import email as emailService

mails = []


class Inline:
    def submit(self, fn, *a, **k):
        return fn(*a, **k)


sender.sendHtmlEmail = lambda recipient, subject, html, plainText, inlineImages=(), replyTo=None: mails.append({"to": recipient, "subject": subject, "html": html, "text": plainText})
emailService._executor = Inline()
CSRF = {"X-GlucoLume-CSRF": "1"}
web = TestClient(app, raise_server_exceptions=False)
permission_errors = []


def call(method, path, **kw):
    r = getattr(web, method)(path, **kw)
    if r.status_code >= 500:
        permission_errors.append((method, path, r.status_code))
    return r


def token_from_mail(index=-1):
    m = re.search(r"token=([A-Za-z0-9_\-]+)", mails[index]["html"] + mails[index]["text"])
    return m.group(1)


# --- Registro, verificación, sesión -----------------------------------------------------------------------------------------------------
PWD = "Zafiro#Cobalto2026"
r = call("post", "/api/v1/auth/register", json={"nombre": "Ana", "apellido": "Sintética", "correoElectronico": "ana.sintetica@example.com", "password": PWD,
                                                 "tipoCuenta": "CONSUMIDOR_FINAL", "aceptaPoliticaPrivacidad": True, "usuario": "anasintetica"})
check("registro (INSERT Usuario, CredencialLocal, TokenCuenta, Consentimiento, Auditoria)", r.status_code == 201, f"{r.status_code} {r.text[:80]}")
check("llegó el correo de verificación (simulado)", len(mails) >= 1)
r = call("get", "/api/v1/auth/verify-email", params={"token": token_from_mail()})
check("verificación del correo (UPDATE Usuario/TokenCuenta)", r.status_code == 200, f"{r.status_code} {r.text[:80]}")
r = call("post", "/api/v1/auth/login", json={"identificador": "anasintetica", "password": PWD}, headers=CSRF)
check("login con cookie HttpOnly (INSERT SesionUsuario)", r.status_code == 200 and r.json()["estado"] == "AUTENTICADO" and r.json()["tokens"]["refreshToken"] is None, f"{r.status_code}")
check("cookie glucolume_refresh HttpOnly + SameSite=strict", any("glucolume_refresh" in h and "HttpOnly" in h and "samesite=strict" in h.lower() for h in r.headers.get_list("set-cookie")))
access = r.json()["tokens"]["accessToken"]
auth = {"Authorization": f"Bearer {access}"}
check("GET /auth/me", call("get", "/api/v1/auth/me", headers=auth).status_code == 200)
stale = web.cookies.get("glucolume_refresh", path="/api/v1/auth")  # el que va a rotarse: después queda «ya usado»
r = call("post", "/api/v1/auth/refresh", headers=CSRF)
check("refresh por cookie rota el token (UPDATE+INSERT SesionUsuario)", r.status_code == 200 and r.json()["refreshToken"] is None, f"{r.status_code}")
auth = {"Authorization": f"Bearer {r.json()['accessToken']}"}

# --- MFA ----------------------------------------------------------------------------------------------------------------------------------
import pyotp, time
r = call("post", "/api/v1/auth/mfa/setup", headers=auth)
secret = r.json().get("secreto")
check("MFA: setup (INSERT FactorMfa cifrado)", r.status_code == 200 and bool(secret), f"{r.status_code}")
r = call("post", "/api/v1/auth/mfa/enable", headers=auth, json={"codigo": pyotp.TOTP(secret).now()})
recovery = r.json().get("codigosRecuperacion", [])
check("MFA: activación (INSERT CodigoRecuperacionMfa)", r.status_code == 200 and len(recovery) == 10, f"{r.status_code}")
r = call("post", "/api/v1/auth/login", json={"identificador": "anasintetica", "password": PWD}, headers=CSRF)
check("login con MFA devuelve desafío y ninguna cookie", r.json()["estado"] == "MFA_REQUERIDO" and not r.headers.get_list("set-cookie"))
challenge = r.json()["challengeToken"]
r = call("post", "/api/v1/auth/mfa/verify", headers=CSRF, json={"challengeToken": challenge, "codigo": pyotp.TOTP(secret).at(time.time() + 30)})
check("MFA: verificación y sesión con cookie", r.status_code == 200 and r.json()["estado"] == "AUTENTICADO", f"{r.status_code} {r.text[:80]}")
auth = {"Authorization": f"Bearer {r.json()['tokens']['accessToken']}"}

# --- Reutilización de un refresh token (revoca todas las sesiones) --------------------------------------------------------------------------
web.cookies.clear()
web.cookies.set("glucolume_refresh", stale, path="/api/v1/auth")
r = call("post", "/api/v1/auth/refresh", headers=CSRF)
check("reutilizar un refresh token ya rotado se rechaza y revoca las sesiones", r.status_code == 401)
check("la sesión anterior quedó revocada", call("get", "/api/v1/auth/me", headers=auth).status_code == 401)

# --- Recuperación de contraseña y eliminación de cuenta (DELETE por tabla) ----------------------------------------------------------------
r = call("post", "/api/v1/auth/login", json={"identificador": "anasintetica", "password": PWD}, headers=CSRF)
challenge = r.json()["challengeToken"]
codes = None
r = call("post", "/api/v1/auth/mfa/verify", headers=CSRF, json={"challengeToken": challenge, "codigoRecuperacion": recovery[0]})
check("nuevo login con MFA (código de recuperación, un solo uso)", r.status_code == 200, f"{r.status_code} {r.text[:60]}")
auth = {"Authorization": f"Bearer {r.json()['tokens']['accessToken']}"}
before = len(mails)
r = call("post", "/api/v1/auth/account-deletion/request", headers=auth)
check("eliminación de cuenta: solicitud", r.status_code == 202, f"{r.status_code} {r.text[:80]}")
tok = token_from_mail()
r = call("post", "/api/v1/auth/account-deletion/confirm", json={"token": tok, "password": PWD, "codigoRecuperacion": recovery[1]})
check("eliminación de cuenta: confirmación (DELETE FactorMfa, CodigoRecuperacionMfa, CredencialLocal, SesionUsuario, TokenCuenta…)", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
left = sa("SET NOCOUNT ON; SELECT (SELECT COUNT(*) FROM dbo.FactorMfa)+(SELECT COUNT(*) FROM dbo.CredencialLocal)+(SELECT COUNT(*) FROM dbo.CodigoRecuperacionMfa)", db=DB).stdout.split()[-1]
check("tras la baja no quedan credenciales, factores ni códigos", left == "0", left)
aud = sa("SET NOCOUNT ON; SELECT COUNT(*) FROM dbo.Auditoria", db=DB).stdout.split()[-1]
check("la auditoría se conserva y creció (solo INSERT)", int(aud) > 8, aud)

# --- Google OAuth SIMULADO (sin salir a Google): identidad sintética -> código de canje -> /google/exchange con cookie ---------------------------
from app.db.session import getSessionFactory
from app.integrations.google.oauth import GoogleIdentity
from app.services import auth as authService

with getSessionFactory()() as gdb:
    guser = authService.identifyGoogleUser(gdb, GoogleIdentity(subject="google-sub-sintetico-1", email="gabi.google@example.com", emailVerified=True,
                                                               givenName="Gabi", familyName="Google"), "CONSUMIDOR_FINAL", True)
    gcode = authService.createGoogleExchangeCode(gdb, guser)
check("Google (simulado): cuenta creada con la cuenta restringida de la API", guser is not None and bool(gcode))
r = call("post", "/api/v1/auth/google/exchange", json={"code": gcode}, headers={**CSRF, "X-GlucoLume-Recordarme": "1"})
ck = r.headers.get_list("set-cookie")
check("Google (simulado): el canje abre sesión con cookie persistente HttpOnly y sin refresh token en el cuerpo",
      r.status_code == 200 and r.json()["estado"] == "AUTENTICADO" and r.json()["tokens"]["refreshToken"] is None and any("Max-Age" in c and "HttpOnly" in c for c in ck), f"{r.status_code}")
gauth = {"Authorization": f"Bearer {r.json()['tokens']['accessToken']}"}
check("Google (simulado): el código es de un solo uso", call("post", "/api/v1/auth/google/exchange", json={"code": gcode}, headers=CSRF).status_code == 401)
tcode = call("post", "/api/v1/auth/session-transfer", headers=gauth).json().get("code")
check("session-transfer entrega un código de un solo uso", bool(tcode))
r2 = call("post", "/api/v1/auth/google/exchange", json={"code": tcode}, headers=CSRF)
check("el canje del session-transfer abre una sesión nueva sin repetir MFA", r2.status_code == 200 and r2.json()["estado"] == "AUTENTICADO")

# --- Permisos de la aplicación: una cuenta común no entra a lo administrativo ni a lo ajeno ---------------------------------------------------
gauth = {"Authorization": f"Bearer {r2.json()['tokens']['accessToken']}"}
for path in ("/api/v1/platform/me", "/api/v1/platform/institutions", "/api/v1/audit"):
    st = call("get", path, headers=gauth).status_code
    check(f"cuenta común: {path} rechazado", st in (401, 403, 404), str(st))
check("sin sesión: /auth/me exige autenticación", call("get", "/api/v1/auth/me").status_code == 401)
check("cerrar sesión (Google) revoca y borra la cookie", call("post", "/api/v1/auth/logout", headers={**gauth, **CSRF}).status_code == 204
      and call("get", "/api/v1/auth/me", headers=gauth).status_code == 401)

# --- H-16: credenciales individuales de puente con las cuentas reales ---------------------------------------------------------------------
def cli(*args):
    return subprocess.run([sys.executable, "-m", "app.cli.bridgeTokens", *args], capture_output=True, text=True, env=ENV, cwd=str(BACKEND))


r = cli("crear", "--nombre", "Puente sintético 1", "--dispositivo", "GLUCOLUME-SINT-01", "--dias", "30", "--confirmo-base", DB)
check("CLI crear credencial con la cuenta de conservación (INSERT PuenteCredencial + auditoría)", r.returncode == 0, (r.stdout + r.stderr)[-200:])
token = r.stdout.strip().splitlines()[-1]
fp = re.search(r"huella ([0-9a-f]+)", r.stdout).group(1)
check("el token en claro NO queda en la base (solo su hash)", token not in sa("SET NOCOUNT ON; SELECT tokenHash FROM dbo.PuenteCredencial", db=DB).stdout and len(token) > 30)
bh = {"X-Bridge-Token": token}
r = call("post", "/api/v1/acquisition/bridge/check", json={"codigoDispositivo": "GLUCOLUME-SINT-01"}, headers=bh)
check("el puente se autentica en su dispositivo (la API LEE y anota fechaUltimoUso)", r.status_code == 200, f"{r.status_code} {r.text[:100]}")
used = sa("SET NOCOUNT ON; SELECT COUNT(*) FROM dbo.PuenteCredencial WHERE fechaUltimoUso IS NOT NULL", db=DB).stdout.split()[-1]
check("fechaUltimoUso actualizado con la cuenta de la API (GRANT de columna)", used == "1", used)
r = call("post", "/api/v1/acquisition/bridge/check", json={"codigoDispositivo": "GLUCOLUME-SINT-02"}, headers=bh)
check("fuera del alcance de su dispositivo: 403", r.status_code == 403, f"{r.status_code}")
r = call("post", "/api/v1/acquisition/bridge/check", json={"codigoDispositivo": "GLUCOLUME-SINT-01"}, headers={"X-Bridge-Token": "x" * 40})
check("token inventado: rechazado", r.status_code in (401, 403), f"{r.status_code} {r.text[:100]}")
r = cli("rotar", "--huella", fp, "--superposicion-horas", "1", "--dias", "30", "--confirmo-base", DB)
check("CLI rotar (UPDATE + INSERT)", r.returncode == 0, (r.stdout + r.stderr)[-200:])
newtoken = r.stdout.strip().splitlines()[-1]
check("ambos tokens valen durante la superposición", all(call("post", "/api/v1/acquisition/bridge/check", json={"codigoDispositivo": "GLUCOLUME-SINT-01"}, headers={"X-Bridge-Token": t}).status_code == 200 for t in (token, newtoken)))
print("   salida de rotar:", r.stdout.replace(newtoken, "<token>").strip().replace("\n", " | ")[:400])
fp2 = [h for h in re.findall(r"huella ([0-9a-f]+)", r.stdout)][-1] if "nueva" not in r.stdout.lower() else re.search(r"[Nn]ueva[^\n]*huella ([0-9a-f]+)", r.stdout).group(1)
r = cli("revocar", "--huella", fp2, "--confirmo-base", DB)
check("CLI revocar (UPDATE)", r.returncode == 0, (r.stdout + r.stderr)[-150:])
r = call("post", "/api/v1/acquisition/bridge/check", json={"codigoDispositivo": "GLUCOLUME-SINT-01"}, headers={"X-Bridge-Token": newtoken})
check("el token revocado deja de valer de inmediato", r.status_code in (401, 403), f"{r.status_code} {r.text[:100]}")
r = cli("crear", "--nombre", "x", "--dispositivo", "GLUCOLUME-SINT-01", "--confirmo-base", "OtraBase")
check("sin nombrar la base exacta no modifica nada", r.returncode == 2)
check("CLI listar", "HUELLA" in cli("listar").stdout)
n_events = sa("SET NOCOUNT ON; SELECT COUNT(*) FROM dbo.Auditoria WHERE tablaAfectada=N'PuenteCredencial'", db=DB).stdout.split()[-1]
check("alta, rotación y revocación quedaron auditadas", int(n_events) >= 4, n_events)

# --- H-04: simulación de retención con la cuenta de conservación; nada se elimina ---------------------------------------------------------
snap = lambda: sa("SET NOCOUNT ON; SELECT (SELECT COUNT(*) FROM dbo.Auditoria),(SELECT COUNT(*) FROM dbo.AuditoriaContexto),(SELECT COUNT(*) FROM dbo.InstitucionUsuario),(SELECT COUNT(*) FROM dbo.PerfilMedicion)", db=DB).stdout.split("\n")[-3:]
# Auditoría y personal viejos sintéticos para que la simulación tenga qué contar (se insertan como sa)
sa("INSERT INTO dbo.Auditoria (idAuditoria,tipoEvento,accion,resultado,fechaHora) VALUES (NEWID(),N'CRUD',N'SINTETICO_VIEJO',N'EXITO',DATEADD(year,-6,SYSDATETIME()))", db=DB)
ENV_RET = {**ENV, "AUDIT_RETENTION_MONTHS": "24"}
before = sa("SET NOCOUNT ON; SELECT COUNT(*) FROM dbo.Auditoria", db=DB).stdout.split()[-1]
r = subprocess.run([sys.executable, "-m", "app.jobs.retention", "previsualizar"], capture_output=True, text=True, env=ENV_RET, cwd=str(BACKEND))
check("retention previsualizar (cuenta de conservación)", r.returncode == 0, (r.stdout + r.stderr)[-200:])
try:
    rep = json.loads(r.stdout[r.stdout.index("{"):])
    check("sin RETENTION_APPROVAL_REFERENCE el plazo efectivo es 0: no se eliminaría nada", rep["auditoria"].get("plazoTotalMesesEfectivo") == 0 and rep["auditoria"].get("eventosAEliminar", 0) == 0, str(rep["auditoria"])[:160])
except Exception as e:  # noqa: BLE001
    check("salida JSON de previsualizar", False, f"{e}: {r.stdout[:200]}")
ENV_RET2 = {**ENV_RET, "RETENTION_APPROVAL_REFERENCE": "SINTETICA-NO-REAL-0000"}
r = subprocess.run([sys.executable, "-m", "app.jobs.retention", "previsualizar"], capture_output=True, text=True, env=ENV_RET2, cwd=str(BACKEND))
try:
    rep = json.loads(r.stdout[r.stdout.index("{"):])
    check("con una aprobación SINTÉTICA la simulación cuenta el evento viejo sin borrarlo", rep["auditoria"].get("eventosAEliminar", 0) >= 1, str(rep["auditoria"])[:160])
except Exception as e:  # noqa: BLE001
    check("salida JSON de previsualizar (aprobada)", False, f"{e}: {r.stdout[:200]}")
r = subprocess.run([sys.executable, "-m", "app.jobs.retention", "ejecutar", "--confirmo-base", DB, "--confirmo-eventos", "999", "--confirmo-personal", "0"], capture_output=True, text=True, env=ENV_RET2, cwd=str(BACKEND))
check("ejecutar con una cantidad confirmada que NO coincide no borra nada", r.returncode != 0, (r.stdout + r.stderr)[-160:])
r = subprocess.run([sys.executable, "-m", "app.jobs.purgeInstitutionalRetention", "--simular"], capture_output=True, text=True, env=ENV_RET2, cwd=str(BACKEND))
check("purgeInstitutionalRetention --simular", r.returncode == 0, (r.stdout + r.stderr)[-200:])
after = sa("SET NOCOUNT ON; SELECT COUNT(*) FROM dbo.Auditoria WHERE accion=N'SINTETICO_VIEJO'", db=DB).stdout.split()[-1]
check("el evento viejo sigue en la base: ninguna simulación eliminó datos", after == "1", after)

# --- Resumen ------------------------------------------------------------------------------------------------------------------------------
check("ninguna operación recibió un error 5xx (que sería un permiso faltante)", not permission_errors, str(permission_errors))
log = sa("SET NOCOUNT ON; SELECT COUNT(*) FROM sys.dm_exec_requests", db=DB)
print(f"\nRESUMEN: {sum(results)} correctas, {len(results) - sum(results)} con falla")
sys.exit(0 if all(results) else 1)
