import json, os, subprocess, sys, time
from datetime import timedelta
sys.path.insert(0, os.environ["BACKEND_DIR"])
import hostenv  # noqa
from sqlalchemy import text
from app.db.session import getEngine
from app.utils.timeZone import nowForDb
from e2e_lib import *

SP = os.environ["IT_DIR"]
SMTP = os.path.join(SP, "smtp_out.jsonl")
WT = os.environ["REPO_DIR"].replace("\\", "/")
ENV = {**os.environ, "MSYS_NO_PATHCONV": "1"}


def q(sql, **params):
    with getEngine().connect() as c:
        return [tuple(r) for r in c.execute(text(sql), params)]


def sh(*args):
    return subprocess.run(args, capture_output=True, text=True, env=ENV)


def start_notifications(name="glucolume-notiftest-notifications", interval="10"):
    sh("docker", "rm", "-f", name)
    r = sh("docker", "run", "-d", "--name", name, "--env-file", os.path.join(SP, "backend.env"), "-e", f"NOTIFICATIONS_INTERVAL_SECONDS={interval}",
           "--add-host", "host.docker.internal:host-gateway", "-v", f"{WT}/backend:/srv/backend:ro", "-v", f"{SP}\\smtp_cert.pem:/run/smtp_cert.pem:ro",
           "glucolume/backend:dev", "python", "-m", "app.jobs.reminders", "--loop")
    assert r.returncode == 0, r.stderr
    return name


def inbox(token, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return call("GET", "/notificaciones" + ("?" + qs if qs else ""), token=token, expect=200)[1]


def reminders_of(usuario):
    return q("select n.claveEvento, n.estadoCorreo, n.intentosCorreo, n.visible, n.fechaLectura from dbo.NotificacionUsuario n join dbo.Usuario u on u.idUsuario=n.idUsuario "
             "where u.usuario=:u and n.evento='RECORDATORIO_MEDICION' and n.claveEvento not like 'LEGADO:%' order by n.fechaCreacion", u=usuario)


ana = "ana"
tok = login(ana, password=None)
# prueba de «sin job»: el horario vence y NADIE abre la bandeja ni corre el servicio
due = nowForDb() + timedelta(minutes=1)
hhmm = due.strftime("%H:%M")
call("PUT", "/notificaciones/recordatorio", token=tok, body={"modo": "HORARIOS", "horarios": [hhmm]}, expect=200)
call("PUT", "/notificaciones/preferencias/RECORDATORIO_MEDICION", token=tok, body={"enPagina": True, "porCorreo": True}, expect=200)
print(f"horario configurado a las {hhmm} (hora de Argentina); espero a que pase sin abrir la bandeja ni correr el servicio…", flush=True)
while nowForDb() < due + timedelta(seconds=75):
    time.sleep(5)
check("SIN el servicio 'notifications' el recordatorio NO se genera aunque el horario venció (causa del 'no llegan')", reminders_of(ana) == [], reminders_of(ana))

# con el servicio: llega solo, con aviso en la página y correo
mail_before = len(mails(SMTP))
start_notifications()
time.sleep(25)
rows = reminders_of(ana)
check("CON el servicio, el recordatorio vencido se genera solo (1 aviso)", len(rows) == 1, rows)
check("su clave identifica la ocurrencia (horario configurado)", rows and rows[0][0].startswith("RECORDATORIO_MEDICION:") and rows[0][0].endswith(hhmm + ":00"), rows[0][0] if rows else None)
check("el correo salió por SMTP y quedó ENVIADO", rows and rows[0][1] == "ENVIADO" and rows[0][2] == 1, rows)
new = mails(SMTP)[mail_before:]
check("el correo llegó al buzón de ana (SMTP de prueba)", any("ana.sintetica" in str(m["to"]) and "medirte" in m["subject"].lower() for m in new), [m["subject"] for m in new])
tok = login(ana, ua=CHROME_WIN)
bandeja = inbox(tok, categoria="RECORDATORIO", limite=5)
check("la API lo devuelve en la bandeja (categoría RECORDATORIO, sin leer)", bandeja["notificaciones"] and bandeja["notificaciones"][0]["leida"] is False and bandeja["notificaciones"][0]["url"] == "/app/mediciones", bandeja["total"])
# idempotencia: otro servicio simultáneo + 3 aperturas de la bandeja + más pasadas
start_notifications("glucolume-notiftest-notifications2", "10")
for _ in range(3):
    inbox(tok)
time.sleep(25)
check("dos servicios simultáneos + aperturas de bandeja NO duplican el recordatorio", len(reminders_of(ana)) == 1 and len([m for m in mails(SMTP)[mail_before:] if "medirte" in m["subject"].lower()]) == 1, reminders_of(ana))
sh("docker", "rm", "-f", "glucolume-notiftest-notifications2")

# cambio de horario y desactivación / eliminación
call("PUT", "/notificaciones/recordatorio", token=tok, body={"modo": "HORARIOS", "horarios": ["03:15", "21:40"]}, expect=200)
check("cambiar el horario se guarda en SQL Server", q("select modo, horarios from dbo.RecordatorioMedicion r join dbo.Usuario u on u.idUsuario=r.idUsuario where u.usuario='ana'") == [("HORARIOS", "03:15,21:40")])
call("PUT", "/notificaciones/recordatorio", token=tok, body={"modo": "INTERVALO", "intervaloHoras": 1}, expect=200)
q_before = len(reminders_of(ana))
with getEngine().begin() as c:  # simula que pasó más de una hora desde el último aviso del periodo
    c.execute(text("update r set ultimoAviso = dateadd(minute, -61, :now) from dbo.RecordatorioMedicion r join dbo.Usuario u on u.idUsuario=r.idUsuario where u.usuario='ana'"), {"now": nowForDb()})
time.sleep(25)
check("recordatorio periódico (cada 1 h): se genera cuando vence", len(reminders_of(ana)) == q_before + 1, reminders_of(ana)[-1])
n_now = len(reminders_of(ana))
call("PUT", "/notificaciones/recordatorio", token=tok, body={"modo": "NINGUNO"}, expect=200)
with getEngine().begin() as c:
    c.execute(text("update r set ultimoAviso = dateadd(hour, -5, :now) from dbo.RecordatorioMedicion r join dbo.Usuario u on u.idUsuario=r.idUsuario where u.usuario='ana'"), {"now": nowForDb()})
time.sleep(25)
check("desactivar/eliminar la programación: no se generan más recordatorios", len(reminders_of(ana)) == n_now, len(reminders_of(ana)))

# falla SMTP: el aviso se guarda igual; al volver el SMTP se reintenta SIN duplicar
call("PUT", "/notificaciones/recordatorio", token=tok, body={"modo": "INTERVALO", "intervaloHoras": 1}, expect=200)
smtp_pid = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-NetTCPConnection -LocalPort 2525 -State Listen).OwningProcess"], capture_output=True, text=True).stdout.strip()
subprocess.run(["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {smtp_pid} -Force"])
time.sleep(2)
with getEngine().begin() as c:
    c.execute(text("update r set ultimoAviso = dateadd(minute, -61, :now) from dbo.RecordatorioMedicion r join dbo.Usuario u on u.idUsuario=r.idUsuario where u.usuario='ana'"), {"now": nowForDb()})
time.sleep(25)
rows = reminders_of(ana)
check("SMTP caído: el aviso de la página se guardó igual y el correo quedó FALLIDO (1 intento; los siguientes esperan)", rows[-1][1] == "FALLIDO" and rows[-1][2] == 1 and rows[-1][3], rows[-1])
total_with_fail = len(rows)
env = dict(os.environ, PYTHONPATH=os.path.join(SP, "..", "site_smtp") + ";" + os.path.join(SP, "..", "site"))
subprocess.Popen(["python", os.path.join(SP, "fake_smtp.py"), os.path.join(SP, "smtp_cert.pem"), os.path.join(SP, "smtp_key.pem"), SMTP, "2525"],
                 env=env, stdout=open(os.path.join(SP, "smtp.log"), "w"), stderr=subprocess.STDOUT)
time.sleep(100)  # espera creciente: el 2.º intento no se hace antes de 1 min desde la creación del aviso
rows = reminders_of(ana)
check("al volver el SMTP el servicio reintenta el correo y queda ENVIADO", rows[-1][1] == "ENVIADO" and rows[-1][2] == 2, rows[-1])
check("el reintento NO creó otro aviso", len(rows) == total_with_fail, f"{len(rows)} avisos")

ok = sum(1 for _, c, _ in RESULTS if c)
print(f"\nRESUMEN: {ok}/{len(RESULTS)} comprobaciones")
sys.exit(0 if ok == len(RESULTS) else 1)
