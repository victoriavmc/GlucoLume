import os
import sys, time
sys.path.insert(0, os.environ["BACKEND_DIR"])
import hostenv  # noqa
from sqlalchemy import select, text
from app.db.session import getSessionFactory, getEngine
from app.models.user import User
from app.services import notifications
from app.utils.timeZone import nowForDb
from e2e_lib import *

SMTP = os.path.join(os.environ["IT_DIR"], "smtp_out.jsonl")


def q(sql, **params):
    with getEngine().connect() as c:
        return [tuple(r) for r in c.execute(text(sql), params)]


def inbox(token, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return call("GET", "/notificaciones" + ("?" + qs if qs else ""), token=token, expect=200)[1]["notificaciones"]


def textos(token, evento=None):
    return [n["mensaje"] for n in inbox(token, limite=50) if evento is None or n["evento"] == evento]


def mails_to(correo, desde=0):
    return [m["subject"] for m in mails(SMTP)[desde:] if correo in str(m["to"])]


ana = login("ana", CHROME_WIN)
beto = login("beto", CHROME_WIN)
carla = login("carla", CHROME_WIN)
time.sleep(1)
m0 = len(mails(SMTP))
grupo = call("POST", "/groups", token=ana, body={"nombre": "Familia Prueba", "descripcion": "grupo sintético"}, expect=201)[1]
gid = grupo["idGrupo"]

# invitaciones recibidas
call("POST", f"/groups/{gid}/invitations", token=ana, body={"correoElectronico": "beto.sintetico@example.com"}, expect=201)
call("POST", f"/groups/{gid}/invitations", token=ana, body={"correoElectronico": "carla.sintetica@example.com"}, expect=201)
time.sleep(2)
check("invitación recibida: beto la ve en la página (GRUPO) y le llega el correo", any("te invitó" in t for t in textos(beto, "INVITACION_GRUPO")) and any("invitaron" in s.lower() for s in mails_to("beto.sintetico", m0)), mails_to("beto.sintetico", m0))
check("invitación recibida: carla igual, y a nadie más", any("te invitó" in t for t in textos(carla, "INVITACION_GRUPO")) and textos(ana, "INVITACION_GRUPO") == [])

# carla rechaza: el administrador se entera
inv_carla = call("GET", "/groups/invitations", token=carla, expect=200)[1][0]["idGrupoUsuario"]
call("POST", f"/groups/invitations/{inv_carla}/reject", token=carla, expect=204)
check("invitación rechazada: ana (quien invitó) recibe UN aviso", len([t for t in textos(ana) if "rechazó" in t]) == 1, textos(ana)[:2])

# beto acepta
inv_beto = call("GET", "/groups/invitations", token=beto, expect=200)[1][0]["idGrupoUsuario"]
m1 = len(mails(SMTP))
call("POST", f"/groups/invitations/{inv_beto}/accept", token=beto, expect=200)
time.sleep(2)
check("invitación aceptada: beto recibe AGREGADO_GRUPO", len(textos(beto, "AGREGADO_GRUPO")) == 1, textos(beto, "AGREGADO_GRUPO"))
check("invitación aceptada: ana recibe la novedad 'se sumó' en la página y el correo al administrador", any("se sumó" in t for t in textos(ana, "NUEVA_ACCION_GRUPO")) and len(mails_to("ana.sintetica", m1)) >= 1, mails_to("ana.sintetica", m1))
check("beto no recibe novedad de su propia incorporación", not any("se sumó" in t for t in textos(beto, "NUEVA_ACCION_GRUPO")))

# carla vuelve a ser invitada y acepta: nuevo integrante -> beto y ana se enteran
call("POST", f"/groups/{gid}/invitations", token=ana, body={"correoElectronico": "carla.sintetica@example.com"}, expect=201)
inv_carla2 = call("GET", "/groups/invitations", token=carla, expect=200)[1][0]["idGrupoUsuario"]
m2 = len(mails(SMTP))
call("POST", f"/groups/invitations/{inv_carla2}/accept", token=carla, expect=200)
time.sleep(2)
check("nuevo integrante: beto recibe la novedad en la página y por correo", any("Carla" in t and "se sumó" in t for t in textos(beto, "NUEVA_ACCION_GRUPO")) and any("novedades" in s.lower() for s in mails_to("beto.sintetico", m2)), mails_to("beto.sintetico", m2))

# mediciones compartidas: solo si beto lo permitió
members = call("GET", f"/groups/{gid}/members", token=ana, expect=200)[1]
id_beto_rel = [m for m in members if m["nombre"] == "Beto"][0]["idGrupoUsuario"]
with getSessionFactory()() as db:
    beto_user = db.scalar(select(User).where(User.usuario == "beto"))
    when = nowForDb()
    sin_permiso = notifications.notifyGroupMeasurement(db, beto_user, when)
check("medición compartida SIN permiso individual: no avisa a nadie", sin_permiso == 0 and textos(ana, "MEDICION_GRUPO") == [], sin_permiso)
call("PUT", f"/groups/{gid}/sharing/me", token=beto, body={"compartePerfil": False, "comparteUltimaMedicion": False, "comparteHistorial": False, "notificaMedicion": True}, expect=200)
m3 = len(mails(SMTP))
with getSessionFactory()() as db:
    beto_user = db.scalar(select(User).where(User.usuario == "beto"))
    first = notifications.notifyGroupMeasurement(db, beto_user, when)
    second = notifications.notifyGroupMeasurement(db, beto_user, when)
time.sleep(2)
check("medición compartida CON permiso: avisa a ana y carla (no a beto) una sola vez aunque se procese dos veces (el correo solo a carla: la preferencia migrada de ana tiene el correo apagado)", first == 1 and second == 0 and len(textos(ana, "MEDICION_GRUPO")) == 1 and len(textos(carla, "MEDICION_GRUPO")) == 1 and textos(beto, "MEDICION_GRUPO") == [], f"primera={first} segunda={second}")
check("el aviso de medición no incluye valores de salud", all("mg" not in t.lower() and "glucosa" not in t.lower() for t in textos(ana, "MEDICION_GRUPO")), textos(ana, "MEDICION_GRUPO"))

# carla abandona
call("POST", f"/groups/{gid}/leave", token=carla, expect=204)
check("desvinculación voluntaria: ana y beto reciben 'abandonó el grupo'", any("abandonó" in t for t in textos(ana, "NUEVA_ACCION_GRUPO")) and any("abandonó" in t for t in textos(beto, "NUEVA_ACCION_GRUPO")))

# ana desvincula a beto
m4 = len(mails(SMTP))
call("DELETE", f"/groups/{gid}/members/{id_beto_rel}", token=ana, expect=204)
time.sleep(2)
check("desvinculación por el administrador: beto recibe el aviso en la página y el correo", any("desvincularon" in n["titulo"].lower() for n in inbox(beto, limite=50)) and len(mails_to("beto.sintetico", m4)) >= 1, mails_to("beto.sintetico", m4))

# sin duplicados en toda la base
dups = q("select idUsuario, claveEvento, count(*) from dbo.NotificacionUsuario where claveEvento is not null group by idUsuario, claveEvento having count(*) > 1")
check("ninguna cuenta tiene dos avisos con la misma clave de evento", dups == [], dups)
por_usuario = q("select u.usuario, n.evento, count(*) from dbo.NotificacionUsuario n join dbo.Usuario u on u.idUsuario=n.idUsuario where n.claveEvento not like 'LEGADO:%' group by u.usuario, n.evento order by u.usuario, n.evento")
print("avisos por cuenta y evento:", por_usuario)
ajenos = q("select count(*) from dbo.NotificacionUsuario n join dbo.Usuario u on u.idUsuario=n.idUsuario where u.usuario='carla' and n.evento='AGREGADO_GRUPO' and n.claveEvento like '%'")[0][0]

ok = sum(1 for _, c, _ in RESULTS if c)
print(f"\nRESUMEN: {ok}/{len(RESULTS)} comprobaciones")
sys.exit(0 if ok == len(RESULTS) else 1)
