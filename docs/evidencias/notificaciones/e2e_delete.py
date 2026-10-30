import os
import sys
import time

sys.path.insert(0, os.environ["BACKEND_DIR"])
import hostenv  # noqa
from sqlalchemy import select, text
from app.db.session import getEngine, getSessionFactory
from app.models.user import User
from app.services import userNotifications as service
from e2e_lib import *


def q(sql, **params):
    with getEngine().connect() as c:
        return [tuple(r) for r in c.execute(text(sql), params)]


def run(sql, **params):
    with getEngine().begin() as c:
        c.execute(text(sql), params)


def inbox(token, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return call("GET", "/notificaciones" + ("?" + qs if qs else ""), token=token, expect=200)[1]


def titulos(token):
    return [n["titulo"] for n in inbox(token, limite=50)["notificaciones"]]


ana_id = q("select idUsuario from dbo.Usuario where usuario='ana'")[0][0]
beto_id = q("select idUsuario from dbo.Usuario where usuario='beto'")[0][0]

# --- datos: avisos reales generados por eventos reales ------------------------------------------------------------------
ana = login("ana", CHROME_WIN)
beto = login("beto", CHROME_WIN)
login("ana", FIREFOX_LINUX)  # equipo nuevo -> INICIO_SESION
call("POST", "/auth/password/change", token=ana, body={"passwordActual": PW, "passwordNueva": "Nueva#Clave2026xy"}, expect=200)  # -> CAMBIO_CONTRASENA
ana = login("ana", CHROME_WIN, password="Nueva#Clave2026xy")
gid = call("POST", "/groups", token=ana, body={"nombre": "Familia Prueba", "descripcion": "x"}, expect=201)[1]["idGrupo"]
call("POST", f"/groups/{gid}/invitations", token=ana, body={"correoElectronico": "beto.sintetico@example.com"}, expect=201)
inv = call("GET", "/groups/invitations", token=beto, expect=200)[1][0]["idGrupoUsuario"]
call("POST", f"/groups/invitations/{inv}/reject", token=beto, expect=204)  # -> aviso al administrador
before = inbox(ana, limite=50)
check("punto de partida: ana tiene avisos de varios eventos", before["total"] >= 5, [n["evento"] for n in before["notificaciones"]])
audit_logins_before = q("select count(*) from dbo.Auditoria where accion like 'LOGIN%'")[0][0]

# --- 1. eliminar un aviso (sin leer) ----------------------------------------------------------------------------------------
target = [n for n in before["notificaciones"] if n["evento"] == "CAMBIO_CONTRASENA"][0]
read_one = [n for n in before["notificaciones"] if n["evento"] == "INICIO_SESION" and n["idNotificacion"] != target["idNotificacion"]][0]
call("POST", f"/notificaciones/{read_one['idNotificacion']}/leer", token=ana, expect=200)
unread0 = inbox(ana)["noLeidas"]
st, body = call("DELETE", f"/notificaciones/{target['idNotificacion']}", token=ana)
check("DELETE de un aviso propio responde con el contador actualizado", st == 200 and body == {"noLeidas": unread0 - 1, "eliminadas": 1}, body)
after = inbox(ana, limite=50)
check("el aviso desaparece de la bandeja y del total", all(n["idNotificacion"] != target["idNotificacion"] for n in after["notificaciones"]) and after["total"] == before["total"] - 1, after["total"])
row = q("select fechaEliminacion, fechaLectura, visible from dbo.NotificacionUsuario where idNotificacion=:i", i=target["idNotificacion"])[0]
check("SQL Server: la fila sigue, con fechaEliminacion y SIN fechaLectura (eliminar no es leer)", row[0] is not None and row[1] is None and row[2] in (1, True), row)
ana2 = login("ana", CHROME_WIN, password="Nueva#Clave2026xy")  # sesión nueva
check("tras iniciar una sesión nueva sigue eliminado", target["titulo"] not in titulos(ana2) or all(n["idNotificacion"] != target["idNotificacion"] for n in inbox(ana2, limite=50)["notificaciones"]))
check("el contador no cuenta el eliminado", inbox(ana2)["noLeidas"] == unread0 - 1, inbox(ana2)["noLeidas"])
check("el eliminado no se puede marcar como leído (404)", call("POST", f"/notificaciones/{target['idNotificacion']}/leer", token=ana2)[0] == 404)
check("eliminar dos veces el mismo aviso responde 404", call("DELETE", f"/notificaciones/{target['idNotificacion']}", token=ana2)[0] == 404)

# --- 2. aislamiento entre usuarios ----------------------------------------------------------------------------------------------
beto_before = inbox(beto, limite=50)["total"]
pick = after["notificaciones"][0]["idNotificacion"]
st, body = call("DELETE", f"/notificaciones/{pick}", token=beto)
check("beto no puede eliminar un aviso de ana (404, igual que uno inexistente)", st == 404 and body["codigo"] == "NOTIFICACION_NO_ENCONTRADA", st)
check("el aviso de ana sigue sin eliminar en SQL Server", q("select fechaEliminacion from dbo.NotificacionUsuario where idNotificacion=:i", i=pick)[0][0] is None)
call("DELETE", "/notificaciones?alcance=todas", token=beto, expect=200)
check("vaciar la bandeja de beto no toca la de ana", inbox(ana2, limite=50)["total"] == after["total"], inbox(ana2)["total"])
check("beto quedó con la bandeja vacía", inbox(beto)["total"] == 0 and beto_before >= 1)
st, body = call("DELETE", "/notificaciones", token=ana2)
check("sin alcance no se vacía nada (422)", st == 422, st)
check("alcance inválido (422)", call("DELETE", "/notificaciones?alcance=otro", token=ana2)[0] == 422)

# --- 3. eliminar las leídas -------------------------------------------------------------------------------------------------------------
n_before = inbox(ana2, limite=50)
leidas = [n for n in n_before["notificaciones"] if n["leida"]]
sin_leer = [n for n in n_before["notificaciones"] if not n["leida"]]
st, body = call("DELETE", "/notificaciones?alcance=leidas", token=ana2)
check("eliminar las leídas: solo esas, y el contador de no leídas no cambia", st == 200 and body["eliminadas"] == len(leidas) and body["noLeidas"] == len(sin_leer), body)
now_titles = {n["idNotificacion"] for n in inbox(ana2, limite=50)["notificaciones"]}
check("las sin leer siguen y las leídas no", now_titles == {n["idNotificacion"] for n in sin_leer}, len(now_titles))
check("auditoría: queda UN evento ELIMINAR_NOTIFICACIONES con la cantidad", q("select count(*) from dbo.Auditoria where accion='ELIMINAR_NOTIFICACIONES' and idUsuario=:u", u=ana_id)[0][0] == 1)

# --- 4. el mismo hecho no resucita; un hecho nuevo sí -------------------------------------------------------------------
clave_eliminada = q("select claveEvento from dbo.NotificacionUsuario where idNotificacion=:i", i=target["idNotificacion"])[0][0]
with getSessionFactory()() as db:
    user = db.scalar(select(User).where(User.usuario == "ana"))
    again = service.notify(db, user, "CAMBIO_CONTRASENA", "Cambio de contraseña", "otra vez", clave=clave_eliminada)
check("reprocesar el MISMO hecho no vuelve a crear el aviso eliminado", again is False and all(n["idNotificacion"] != target["idNotificacion"] for n in inbox(ana2, limite=50)["notificaciones"]) and q("select count(*) from dbo.NotificacionUsuario where claveEvento=:k", k=clave_eliminada)[0][0] == 1)
n_visible = inbox(ana2)["total"]
login("ana", SAFARI_IPHONE, password="Nueva#Clave2026xy")  # equipo nuevo distinto: hecho nuevo e independiente
check("un hecho nuevo e independiente SÍ crea un aviso nuevo", inbox(ana2)["total"] == n_visible + 1, f"{n_visible} -> {inbox(ana2)['total']}")

# --- 5. vaciar la bandeja ---------------------------------------------------------------------------------------------------------------------
st, body = call("DELETE", "/notificaciones?alcance=todas", token=ana2)
vacia = inbox(ana2, limite=50)
check("vaciar: bandeja y contador en cero", st == 200 and body["noLeidas"] == 0 and vacia == {"noLeidas": 0, "total": 0, "hayMas": False, "notificaciones": []}, body)
check("las filas siguen en SQL Server (eliminación lógica)", q("select count(*) from dbo.NotificacionUsuario where idUsuario=:u and fechaEliminacion is not null", u=ana_id)[0][0] >= 5)
check("la auditoría de autenticación no se tocó", q("select count(*) from dbo.Auditoria where accion like 'LOGIN%'")[0][0] >= audit_logins_before)
check("vaciar de nuevo no hace nada ni audita otra vez", call("DELETE", "/notificaciones?alcance=todas", token=ana2)[1]["eliminadas"] == 0 and q("select count(*) from dbo.Auditoria where accion='ELIMINAR_NOTIFICACIONES' and idUsuario=:u", u=ana_id)[0][0] == 2)

# --- 6. eficiencia y atomicidad de las acciones masivas ------------------------------------------------------------------------------
run("SET NOCOUNT ON; INSERT INTO dbo.NotificacionUsuario (idUsuario, evento, titulo, mensaje, claveEvento, fechaCreacion, fechaLectura) "
    "SELECT TOP (5000) :u, N'CAMBIO_MFA', N'masivo', N'm', N'masivo:' + CONVERT(nvarchar(10), ROW_NUMBER() OVER (ORDER BY (SELECT NULL))), SYSDATETIME(), "
    "CASE WHEN ABS(CHECKSUM(NEWID())) % 2 = 0 THEN SYSDATETIME() END FROM sys.all_objects a CROSS JOIN sys.all_objects b", u=beto_id)
tot = q("select count(*) from dbo.NotificacionUsuario where idUsuario=:u and fechaEliminacion is null and claveEvento like 'masivo:%'", u=beto_id)[0][0]
beto = login("beto", CHROME_WIN)
t0 = time.perf_counter()
body = call("DELETE", "/notificaciones?alcance=todas", token=beto, expect=200)[1]
ms = (time.perf_counter() - t0) * 1000
left = q("select count(*) from dbo.NotificacionUsuario where idUsuario=:u and fechaEliminacion is null", u=beto_id)[0][0]
check(f"vaciar {tot} avisos de una vez: todo o nada, en una transacción", body["eliminadas"] == tot and left == 0, f"{tot} avisos en {ms:.0f} ms")

ok = sum(1 for _, c, _ in RESULTS if c)
print(f"\nRESUMEN: {ok}/{len(RESULTS)} comprobaciones")
sys.exit(0 if ok == len(RESULTS) else 1)
