import os
import sys, time
sys.path.insert(0, os.environ["BACKEND_DIR"])
import hostenv  # noqa
import pyotp
from sqlalchemy import text
from app.db.session import getEngine
from e2e_lib import *
import e2e_lib

SMTP = os.path.join(os.environ["IT_DIR"], "smtp_out.jsonl")


def q(sql, **params):
    with getEngine().connect() as c:
        return [tuple(r) for r in c.execute(text(sql), params)]


def inbox(token, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return call("GET", "/notificaciones" + ("?" + qs if qs else ""), token=token, expect=200)[1]


def eventos(token):
    return [n["evento"] for n in inbox(token, limite=50)["notificaciones"]]


ana_id = q("select idUsuario from dbo.Usuario where usuario='ana'")[0][0]

# --- Inicio de sesión: auditado siempre, aviso solo de equipo nuevo -------------------------------------------------
base_login_audit = q("select count(*) from dbo.Auditoria where accion='LOGIN_PWD' and idUsuario=:u", u=ana_id)[0][0]
base_inicio = eventos(login("ana")).count("INICIO_SESION")  # (el login de arriba fue el primero con User-Agent conocido)
t = login("ana", CHROME_WIN)
t = login("ana", CHROME_WIN)
check("login habitual (mismo equipo) no genera aviso nuevo", eventos(t).count("INICIO_SESION") == base_inicio, f"INICIO_SESION={eventos(t).count('INICIO_SESION')} base={base_inicio}")
t = login("ana", FIREFOX_LINUX)
t = login("ana", FIREFOX_LINUX)
n_inicio = eventos(t).count("INICIO_SESION")
check("equipo nuevo (Firefox/Linux) genera UN aviso y repetirlo no duplica", n_inicio == base_inicio + 1, f"INICIO_SESION={n_inicio} base={base_inicio}")
msg = [n for n in inbox(t, limite=50)["notificaciones"] if n["evento"] == "INICIO_SESION"][0]
check("el aviso describe el equipo y no incluye la IP", "Firefox" in msg["mensaje"] and "Linux" in msg["mensaje"] and "172." not in msg["mensaje"] and "127.0" not in msg["mensaje"], msg["mensaje"][:90])
after_login_audit = q("select count(*) from dbo.Auditoria where accion='LOGIN_PWD' and idUsuario=:u", u=ana_id)[0][0]
check("cada inicio de sesión sigue auditado en SQL Server (LOGIN_PWD)", after_login_audit - base_login_audit == 5, f"nuevos eventos de auditoría={after_login_audit - base_login_audit} (5 logins)")
known = q("select count(*) from dbo.AccesoConocido where idUsuario=:u", u=ana_id)[0][0]
check("AccesoConocido guarda un registro por equipo distinto (sin IP)", known == 2, f"filas={known}")

# --- Cambio de contraseña ---------------------------------------------------------------------------------------------
before = len(mails(SMTP))
st, _ = call("POST", "/auth/password/change", token=t, body={"passwordActual": PW, "passwordNueva": "Nueva#Clave2026xy"})
check("cambio de contraseña responde 2xx", st in (200, 201, 204), st)
t2 = None
status, payload = call("POST", "/auth/login", body={"identificador": "ana", "password": "Nueva#Clave2026xy"}, ua=CHROME_WIN)
t2 = payload["tokens"]["accessToken"]
check("avisa CAMBIO_CONTRASENA en la página (obligatorio)", "CAMBIO_CONTRASENA" in eventos(t2), "")
time.sleep(2)
new_mails = mails(SMTP)[before:]
check("y sale el correo existente PASSWORD_CAMBIADA", any("ana.sintetica" in str(m["to"]) and "contraseña" in m["subject"].lower() for m in new_mails), [m["subject"] for m in new_mails])
call("POST", "/auth/password/change", token=t2, body={"passwordActual": "Nueva#Clave2026xy", "passwordNueva": "Otra#Clave2026zq"}, expect=200)
t = login("ana", CHROME_WIN, password="Otra#Clave2026zq")
check("segundo cambio de contraseña crea un segundo aviso (otro hecho)", eventos(t).count("CAMBIO_CONTRASENA") == 2, eventos(t).count("CAMBIO_CONTRASENA"))

# --- MFA ------------------------------------------------------------------------------------------------------------------
setup = call("POST", "/auth/mfa/setup", token=t, expect=200)[1]
totp = pyotp.TOTP(setup["secreto"])
call("POST", "/auth/mfa/enable", token=t, body={"codigo": totp.now()}, expect=200)
check("activar MFA avisa CAMBIO_MFA", eventos(t).count("CAMBIO_MFA") == 1, eventos(t).count("CAMBIO_MFA"))
time.sleep(31)
call("POST", "/auth/mfa/disable", token=t, body={"codigo": totp.now()}, expect=200)
check("desactivar MFA avisa CAMBIO_MFA (2 avisos en total)", eventos(t).count("CAMBIO_MFA") == 2, eventos(t).count("CAMBIO_MFA"))

# --- Actividad sospechosa -------------------------------------------------------------------------------------------------
for _ in range(3):
    call("POST", "/auth/login", body={"identificador": "carla", "password": "mala-clave-1A#"})
st, body = call("POST", "/auth/login", body={"identificador": "carla", "password": "mala-clave-1A#"})
tc = None
carla_pw_ok = call("POST", "/auth/login", body={"identificador": "carla", "password": PW})
check("la cuenta queda bloqueada tras los intentos fallidos", carla_pw_ok[0] in (423, 429, 401, 403), carla_pw_ok[0])
q_carla = q("select count(*) from dbo.NotificacionUsuario n join dbo.Usuario u on u.idUsuario=n.idUsuario where u.usuario='carla' and n.evento='ACTIVIDAD_SOSPECHOSA'")[0][0]
check("el bloqueo genera UN aviso ACTIVIDAD_SOSPECHOSA (aunque se siga intentando)", q_carla == 1, f"filas={q_carla}")

# --- Preferencias reales en la base ---------------------------------------------------------------------------------------
st, body = call("PUT", "/notificaciones/preferencias/CAMBIO_CONTRASENA", token=t, body={"enPagina": False})
check("apagar una alerta obligatoria se rechaza (409)", st == 409 and body["codigo"] == "AVISO_OBLIGATORIO", f"{st} {body}")
call("PUT", "/notificaciones/preferencias/INVITACION_GRUPO", token=t, body={"enPagina": True, "porCorreo": False}, expect=200)
row = q("select enPagina, porCorreo from dbo.PreferenciaNotificacion where idUsuario=:u and evento='INVITACION_GRUPO'", u=ana_id)
check("la preferencia queda guardada en SQL Server (no solo en el estado de React)", row == [(True, False)], row)
prefs = call("GET", "/notificaciones/preferencias", token=t, expect=200)[1]["preferencias"]
check("GET devuelve 9 preferencias con categoría y obligatoria", len(prefs) == 9 and {p["evento"] for p in prefs if p["obligatoria"]} == {"CAMBIO_CONTRASENA", "CAMBIO_MFA", "ACTIVIDAD_SOSPECHOSA"}, len(prefs))

# --- Autorización y lectura ---------------------------------------------------------------------------------------------------
tb = login("beto", CHROME_WIN)
ajeno = inbox(t, limite=50)["notificaciones"][0]["idNotificacion"]
st, body = call("POST", f"/notificaciones/{ajeno}/leer", token=tb)
check("beto no puede marcar un aviso de ana (404 NOTIFICACION_NO_ENCONTRADA)", st == 404 and body["codigo"] == "NOTIFICACION_NO_ENCONTRADA", f"{st}")
check("beto no ve avisos de ana", all(n["idNotificacion"] != ajeno for n in inbox(tb, limite=50)["notificaciones"]))
antes = inbox(t)["noLeidas"]
call("POST", f"/notificaciones/{ajeno}/leer", token=t, expect=200)
check("marcar uno baja el contador en 1", inbox(t)["noLeidas"] == antes - 1, f"{antes} -> {inbox(t)['noLeidas']}")
beto_unread = inbox(tb)["noLeidas"]
res = call("POST", "/notificaciones/leer-todas", token=t, expect=200)[1]
check("marcar todas deja 0 en ana y no toca a beto", res["noLeidas"] == 0 and inbox(t)["noLeidas"] == 0 and inbox(tb)["noLeidas"] == beto_unread, f"ana=0 beto={beto_unread}")

ok = sum(1 for _, c, _ in RESULTS if c)
print(f"\nRESUMEN: {ok}/{len(RESULTS)} comprobaciones")
sys.exit(0 if ok == len(RESULTS) else 1)
