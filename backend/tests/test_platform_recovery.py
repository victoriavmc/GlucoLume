# Administración de la plataforma: activación inicial, intentos de escalada y recuperación controlada del administrador (servidor, sin contraseña
# maestra). Reutiliza los ayudantes de test_platform.py (MFA real, cliente HTTP con la autenticación real).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_platform_recovery.py -v

import re
import threading
from datetime import timedelta
from pathlib import Path

import pyotp
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import sessionmaker

from app.cli import recoverAdmin
from app.models.accountToken import AccountToken
from app.models.mfaFactor import MfaFactor
from app.models.platformTransfer import PlatformTransfer
from app.models.user import User
from app.models.userSession import UserSession
from app.services import platform
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_institutions import expectError, freshLookupLimiter, team  # noqa: F401 - fixtures
from tests.test_platform import (  # noqa: F401 - fixtures y ayudantes
    ADMIN, MOD, NEW_PASSWORD, PASSWORD, admin, login, moderator, platformUser, reauth, strictPolicy, tokenIn, web,
)


def admins(db):
    db.expire_all()
    return list(db.scalars(select(User).where(User.tipoCuenta == ADMIN, User.estado != "ELIMINADO")))


def activeSessions(db, user):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(UserSession).where(UserSession.idUsuario == user.idUsuario, UserSession.fechaRevocacion.is_(None))) or 0


# --- Activación inicial: código incorrecto, vencido, reutilizado y segundo administrador ------------------------------------------


def test_el_enlace_de_activacion_incorrecto_vencido_o_reutilizado_no_activa_nada(db, mails):
    user, link, _, _ = platform.initializeFirstAdmin(db, "Ana", "Pérez", "ana@example.com")
    token = link.split("codigo=")[1]
    expectError("TOKEN_INVALIDO", platform.completeActivation, db, "no-es-el-codigo", "anaadmin", NEW_PASSWORD)
    # Vencido: la persona no se activa y el estado sigue PENDIENTE.
    db.execute(update(AccountToken).where(AccountToken.idUsuario == user.idUsuario).values(fechaCreacion=nowForDb() - timedelta(hours=3), fechaExpiracion=nowForDb() - timedelta(minutes=1)))
    db.commit()
    expectError("TOKEN_VENCIDO", platform.completeActivation, db, token, "anaadmin", NEW_PASSWORD)
    assert reload(db, User, user.idUsuario).estado == "PENDIENTE"
    # Renovado y usado una vez: la segunda vez ya no sirve y no hay un segundo administrador.
    fresh = platform.initializeFirstAdmin(db, "Ana", "Pérez", "ana@example.com")[1].split("codigo=")[1]
    platform.completeActivation(db, fresh, "anaadmin", NEW_PASSWORD)
    expectError("TOKEN_INVALIDO", platform.completeActivation, db, fresh, "otroadmin", NEW_PASSWORD)
    assert len(admins(db)) == 1 and reload(db, User, user.idUsuario).usuario == "anaadmin"


def test_con_un_administrador_bloqueado_la_inicializacion_no_crea_otro_y_apunta_a_la_recuperacion(db, mails, admin):
    user, _ = admin
    user.estado = "BLOQUEADO"
    db.commit()
    error = expectError("ADMINISTRADOR_NO_ACTIVO", platform.initializeFirstAdmin, db, "Otra", "Persona", "otra@example.com")
    assert "recoverAdmin" in error.message and len(admins(db)) == 1


def test_dos_activaciones_simultaneas_del_mismo_enlace_activan_una_sola(engine, db, mails):
    _, link, _, _ = platform.initializeFirstAdmin(db, "Ana", "Pérez", "ana@example.com")
    token = link.split("codigo=")[1]
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    results, barrier = [], threading.Barrier(2)

    def activate(username):
        session = factory()
        try:
            barrier.wait()
            platform.completeActivation(session, token, username, NEW_PASSWORD)
            results.append("ok")
        except Exception as error:  # noqa: BLE001 - se clasifica abajo
            results.append(getattr(error, "code", type(error).__name__))
        finally:
            session.close()

    threads = [threading.Thread(target=activate, args=(name,)) for name in ("anauno", "anados")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count("ok") == 1, results  # solo una activación; la otra recibe un error de enlace o de bloqueo
    assert len(admins(db)) == 1 and admins(db)[0].estado == "ACTIVO"


# --- Escalada de privilegios --------------------------------------------------------------------------------------------------


def test_nadie_obtiene_un_rol_de_plataforma_enviando_el_rol_en_una_solicitud(db, mails, web, moderator):
    # Registro público: el tipo de cuenta de plataforma no es un valor aceptado.
    body = {"nombre": "Eva", "apellido": "Ruiz", "correoElectronico": "eva@example.com", "usuario": "evaruiz", "password": NEW_PASSWORD,
            "tipoCuenta": ADMIN, "aceptaPolitica": True}
    response = web.post("/api/v1/auth/register", json=body)
    assert response.status_code in (400, 422)
    assert db.scalar(select(User.idUsuario).where(User.correoElectronico == "eva@example.com")) is None
    # Un moderador no puede crear un administrador ni cambiarse el rol: no hay rutas para eso y las de gestión le responden 403.
    user, secret = moderator
    headers = login(web, user, secret)
    for method, path, payload in (("post", "/platform/moderators", {"nombre": "A", "apellido": "B", "correoElectronico": "x@example.com", "rol": ADMIN}),
                                  ("post", "/platform/transfer", {"idDestino": str(user.idUsuario)}),
                                  ("patch", "/users/me", {"tipoCuenta": ADMIN})):
        response = getattr(web, method)(f"/api/v1{path}", headers=headers, json=payload)
        assert response.status_code in (403, 404, 405, 422), (path, response.status_code)
    assert reload(db, User, user.idUsuario).tipoCuenta == MOD and len(admins(db)) == 0


def test_el_moderador_de_plataforma_inicia_sesion_con_su_segundo_factor_y_no_ve_lo_del_administrador(db, mails, web, admin, moderator):
    user, secret = moderator
    headers = login(web, user, secret)
    me = web.get("/api/v1/platform/me", headers=headers).json()
    assert me["rol"] == MOD and "GESTIONAR_MODERADORES" not in me["permisos"]
    assert web.get("/api/v1/platform/moderators", headers=headers).status_code == 403
    assert "DASHBOARD_GLOBAL" not in me["permisos"] and "TRANSFERIR_ADMINISTRACION" not in me["permisos"]  # su dashboard es el técnico


# --- Recuperación: reemplazar al administrador ----------------------------------------------------------------------------------


def test_reemplazar_al_administrador_cambia_ambos_roles_en_una_transaccion_y_cierra_sus_sesiones(db, mails, web, admin, moderator):
    old, oldSecret = admin
    new, newSecret = moderator
    oldHeaders = login(web, old, oldSecret)
    assert activeSessions(db, old) >= 1
    previous, promoted = platform.replaceAdministrator(db, new.correoElectronico, "Pérdida del dispositivo del administrador")
    assert [u.idUsuario for u in admins(db)] == [new.idUsuario]  # exactamente uno vigente
    assert (reload(db, User, old.idUsuario).tipoCuenta, reload(db, User, old.idUsuario).estado) == (MOD, "BLOQUEADO")
    assert activeSessions(db, old) == 0
    assert web.get("/api/v1/platform/me", headers=oldHeaders).status_code in (401, 403)  # su sesión ya no sirve
    event = audits(db, "RECUPERAR_ADMINISTRACION_PLATAFORMA")[-1]
    assert event.modulo == "PLATAFORMA" and "Pérdida del dispositivo" in event.observacion and event.idUsuario is None
    assert "password" not in (event.datosNuevos or "").lower() and "token" not in (event.datosNuevos or "").lower()
    # La persona nueva entra con su MFA y ya es la administradora; la anterior no puede volver a entrar.
    me = web.get("/api/v1/platform/me", headers=login(web, new, newSecret)).json()
    assert me["rol"] == ADMIN and "GESTIONAR_MODERADORES" in me["permisos"]
    blocked = web.post("/api/v1/auth/login", json={"identificador": old.usuario, "acceso": "PLATAFORMA", "password": PASSWORD})
    assert blocked.status_code >= 400 or blocked.json().get("estado") != "AUTENTICADO"


def test_el_anterior_puede_quedar_como_moderador_y_las_transferencias_pendientes_se_cancelan(db, mails, admin, moderator):
    old, oldSecret = admin
    new, _ = moderator
    other, _ = platformUser(db, MOD, "otro@example.com", "otromod")
    platform.startTransfer(db, old, other.idUsuario, reauth(db, old, oldSecret))
    platform.replaceAdministrator(db, new.correoElectronico, "Reemplazo planificado", keepPreviousAsModerator=True)
    assert (reload(db, User, old.idUsuario).tipoCuenta, reload(db, User, old.idUsuario).estado) == (MOD, "ACTIVO")
    assert db.scalar(select(func.count()).select_from(PlatformTransfer).where(PlatformTransfer.estado == "PENDIENTE")) == 0
    assert len(admins(db)) == 1


@pytest.mark.parametrize("case", ["no_moderador", "sin_mfa", "inactivo", "mismo", "inexistente"])
def test_el_reemplazo_exige_un_moderador_activo_con_mfa_y_no_cambia_nada_si_no_lo_es(db, mails, admin, case):
    old, _ = admin
    target = {
        "no_moderador": makeUser(db, email="comun@example.com", usuario="comun").correoElectronico,
        "sin_mfa": platformUser(db, MOD, "sinmfa@example.com", "sinmfa", mfa=False)[0].correoElectronico,
        "inactivo": None, "mismo": old.correoElectronico, "inexistente": "nadie@example.com",
    }[case]
    if case == "inactivo":
        user, _ = platformUser(db, MOD, "inactivo@example.com", "inactivo")
        user.estado = "BLOQUEADO"
        db.commit()
        target = user.correoElectronico
    with pytest.raises(Exception) as error:
        platform.replaceAdministrator(db, target, "motivo")
    assert getattr(error.value, "code", "") in ("DESTINATARIO_INVALIDO", "DESTINATARIO_INACTIVO", "DESTINATARIO_SIN_MFA")
    assert [u.idUsuario for u in admins(db)] == [old.idUsuario] and reload(db, User, old.idUsuario).estado == "ACTIVO"


def test_el_reemplazo_exige_motivo_y_un_administrador_existente(db, mails, admin, moderator):
    expectError("MOTIVO_REQUERIDO", platform.replaceAdministrator, db, moderator[0].correoElectronico, "  ")
    gone = reload(db, User, admin[0].idUsuario)
    gone.estado, gone.fechaEliminacion = "ELIMINADO", nowForDb()
    db.commit()
    expectError("SIN_ADMINISTRADOR", platform.replaceAdministrator, db, moderator[0].correoElectronico, "motivo")


def test_dos_recuperaciones_simultaneas_no_dejan_dos_administradores(db, mails, admin, moderator):
    """La segunda recuperación parte de un estado ya viejo (la primera ganó): sus cambios condicionados no alcanzan ninguna fila y se revierten."""
    first, _ = moderator
    second, _ = platformUser(db, MOD, "segundo@example.com", "segundomod")
    stale = platform._currentAdministrator(db)
    platform.replaceAdministrator(db, first.correoElectronico, "Primera recuperación")
    original = platform._currentAdministrator
    try:
        platform._currentAdministrator = lambda _db: stale
        expectError("RECUPERACION_OBSOLETA", platform.replaceAdministrator, db, second.correoElectronico, "Segunda recuperación")
    finally:
        platform._currentAdministrator = original
    assert [u.idUsuario for u in admins(db)] == [first.idUsuario]
    assert reload(db, User, second.idUsuario).tipoCuenta == MOD


# --- Recuperación: la misma persona recupera su acceso --------------------------------------------------------------------------


def test_reinvitar_al_administrador_cierra_sus_sesiones_y_el_enlace_anterior_deja_de_servir(db, mails, web, admin):
    user, secret = admin
    login(web, user, secret)
    stale = platform.initializeFirstAdmin  # no se usa: solo documenta que la inicialización sigue cerrada
    expectError("ADMINISTRADOR_EXISTENTE", stale, db, "X", "Y", "x@example.com")
    _, link, expires, sent = platform.reinviteAdministrator(db, "Perdió el segundo factor", resetMfa=True)
    assert sent and expires > nowForDb() and mails[-1]["to"] == user.correoElectronico
    assert reload(db, User, user.idUsuario).estado == "PENDIENTE" and activeSessions(db, user) == 0
    assert db.scalar(select(func.count()).select_from(MfaFactor).where(MfaFactor.idUsuario == user.idUsuario)) == 0
    assert [u.idUsuario for u in admins(db)] == [user.idUsuario]
    token = link.split("codigo=")[1]
    platform.completeActivation(db, token, user.usuario, NEW_PASSWORD)  # elige contraseña nueva; sin MFA solo puede configurarla
    me = platform.me(db, reload(db, User, user.idUsuario))
    assert me.requiereConfigurarMfa is True
    expectError("TOKEN_INVALIDO", platform.completeActivation, db, token, user.usuario, NEW_PASSWORD)  # un solo uso
    assert audits(db, "REINVITAR_ADMINISTRADOR_PLATAFORMA")[-1].observacion.startswith("Motivo:")


def test_reinvitar_conservando_el_mfa_exige_el_segundo_factor_al_volver(db, mails, web, admin):
    user, secret = admin
    _, link, _, _ = platform.reinviteAdministrator(db, "Olvidó la contraseña")
    platform.completeActivation(db, link.split("codigo=")[1], user.usuario, NEW_PASSWORD)
    response = web.post("/api/v1/auth/login", json={"identificador": user.usuario, "acceso": "PLATAFORMA", "password": NEW_PASSWORD}).json()
    assert response["estado"] == "MFA_REQUERIDO"  # la contraseña sola no alcanza


# --- Comando de servidor ---------------------------------------------------------------------------------------------------------


def test_el_comando_pide_motivo_y_confirmacion_y_se_niega_con_datos_invalidos(db, mails, engine, admin, moderator, monkeypatch):
    monkeypatch.setenv(recoverAdmin.AUTHORIZATION_ENV, "SI")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    out = []
    destino = moderator[0].correoElectronico
    with pytest.raises(SystemExit):
        recoverAdmin.run(["reemplazar", "--destino", destino], factory, out.append)  # sin --motivo
    assert [u.idUsuario for u in admins(db)] == [admin[0].idUsuario]
    assert recoverAdmin.run(["reemplazar", "--destino", "comun-inexistente@example.com", "--motivo", "x", "--confirmar"], factory, out.append) == 1
    assert "No se recuperó" in out[-1]
    assert recoverAdmin.run(["reemplazar", "--destino", destino, "--motivo", "Reemplazo", "--confirmar"], factory, out.append) == 0
    assert [u.idUsuario for u in admins(db)] == [moderator[0].idUsuario]
    assert recoverAdmin.run(["reinvitar", "--motivo", "Olvidó la contraseña", "--confirmar", "--mostrar-enlace"], factory, out.append) == 0
    assert any("administracion/activar#codigo=" in line for line in out)


# --- Pendientes de seguridad: aviso, contexto del servidor, auditoría, MFA y sesiones ---------------------------------------------


def loginTokens(web, user, secret):
    body = web.post("/api/v1/auth/login", json={"identificador": user.usuario, "acceso": "PLATAFORMA", "password": PASSWORD}).json()
    factor = platform.mfa.getFactor(web.testDb, user)
    factor.ultimoPasoUsado = None
    web.testDb.commit()
    return web.post("/api/v1/auth/mfa/verify", json={"challengeToken": body["challengeToken"], "codigo": pyotp.TOTP(secret).now()}).json()["tokens"]


def test_quien_pasa_a_ser_administrador_recibe_un_aviso_con_el_cambio_sin_secretos(db, mails, admin, moderator):
    new, _ = moderator
    mails.clear()
    platform.replaceAdministrator(db, new.correoElectronico, "Reemplazo por pérdida de acceso")
    notice = [m for m in mails if m["to"] == new.correoElectronico]
    assert len(notice) == 1 and notice[0]["subject"] == "Ahora sos el administrador de GlucoLume"
    body = notice[0]["html"] + notice[0]["text"]
    assert "administrador del sistema" in body and "Moderador del sistema" in body  # el cambio de rol
    assert re.search(r"\d{2}/\d{2}/\d{4}", body)  # la fecha
    assert "/plataforma/login" in body  # la acción: volver a ingresar
    assert "token=" not in body and "Reemplazo por pérdida" not in body  # ni enlaces con secretos ni el motivo interno
    assert [m["to"] for m in mails if m["subject"] == "Ahora sos el administrador de GlucoLume"] == [new.correoElectronico]  # solo a esa persona


def test_la_recuperacion_solo_existe_en_el_servidor_ninguna_ruta_http_la_expone():
    api = Path(__file__).resolve().parents[1] / "app" / "api"
    sources = "\n".join(path.read_text(encoding="utf-8") for path in api.rglob("*.py"))
    for name in ("recoverAdmin", "replaceAdministrator", "reinviteAdministrator", "initializeFirstAdmin"):
        assert name not in sources, name


def test_la_automatizacion_exige_declarar_la_autorizacion_y_sin_ella_no_cambia_nada(db, mails, engine, admin, moderator, monkeypatch):
    monkeypatch.delenv(recoverAdmin.AUTHORIZATION_ENV, raising=False)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    out = []
    assert recoverAdmin.run(["reemplazar", "--destino", moderator[0].correoElectronico, "--motivo", "x", "--confirmar"], factory, out.append) == 1
    assert recoverAdmin.AUTHORIZATION_ENV in out[-1]
    assert recoverAdmin.run(["reinvitar", "--motivo", "x", "--confirmar"], factory, out.append) == 1
    assert [u.idUsuario for u in admins(db)] == [admin[0].idUsuario] and reload(db, User, admin[0].idUsuario).estado == "ACTIVO"
    monkeypatch.setenv(recoverAdmin.AUTHORIZATION_ENV, "SI")
    assert recoverAdmin.run(["reemplazar", "--destino", moderator[0].correoElectronico, "--motivo", "x", "--confirmar"], factory, out.append) == 0


def test_cada_recuperacion_deja_auditoria_con_motivo_y_contexto_del_servidor_tambien_si_se_rechaza(db, mails, admin, moderator):
    old, _ = admin
    expectError("DESTINATARIO_INVALIDO", platform.replaceAdministrator, db, "nadie@example.com", "Intento con un correo inexistente")
    denied = audits(db, "RECUPERAR_ADMINISTRACION_PLATAFORMA")[-1]
    assert denied.resultado == "FALLO" and "DESTINATARIO_INVALIDO" in denied.observacion and "Intento con un correo" in denied.observacion
    assert "usuarioSistema" in denied.datosNuevos and "equipo" in denied.datosNuevos
    assert [u.idUsuario for u in admins(db)] == [old.idUsuario]
    platform.replaceAdministrator(db, moderator[0].correoElectronico, "Reemplazo")
    done = audits(db, "RECUPERAR_ADMINISTRACION_PLATAFORMA")[-1]
    assert done.resultado == "EXITO" and "usuarioSistema" in done.datosNuevos and "SERVIDOR" in done.datosNuevos
    assert str(old.idUsuario) in done.datosPrevios and str(moderator[0].idUsuario) in done.datosNuevos  # quién dejó y quién asumió
    for blob in (done.datosNuevos, done.datosPrevios, done.observacion, denied.datosNuevos):
        assert not re.search(r"token|password|secret|codigo", (blob or "").lower())


def test_conocer_el_correo_del_administrador_no_alcanza_para_tomar_su_cuenta_ni_resetear_su_mfa(db, mails, web, admin):
    user, secret = admin
    mails.clear()
    # Un tercero que solo sabe el correo: pide recuperar la contraseña por la vía pública. No obtiene nada y nada cambia.
    response = web.post("/api/v1/platform/password/forgot", json={"correoElectronico": user.correoElectronico})
    assert response.status_code in (200, 202, 204)  # respuesta genérica: no revela nada
    assert platform.mfa.isEnabled(db, user) and reload(db, User, user.idUsuario).estado == "ACTIVO"
    assert db.scalar(select(func.count()).select_from(AccountToken).where(AccountToken.idUsuario == user.idUsuario, AccountToken.tipo == "ACTIVACION_CUENTA")) == 0
    assert all(m["to"] == user.correoElectronico for m in mails)  # el enlace solo viaja al correo registrado; nada se muestra en la respuesta
    # Aun si alguien con acceso a ese correo restablece la contraseña, el segundo factor sigue siendo obligatorio.
    reset = web.post("/api/v1/platform/password/reset", json={"token": tokenIn(mails), "password": NEW_PASSWORD})
    assert reset.status_code in (200, 204)
    entered = web.post("/api/v1/auth/login", json={"identificador": user.usuario, "acceso": "PLATAFORMA", "password": NEW_PASSWORD}).json()
    assert entered["estado"] == "MFA_REQUERIDO" and not entered.get("tokens")
    # Ninguna ruta HTTP resetea el MFA del administrador a partir del correo.
    for path in ("/platform/mfa/reset", "/platform/administrator/recover", "/platform/recover"):
        assert web.post(f"/api/v1{path}", json={"correoElectronico": user.correoElectronico}).status_code in (401, 404, 405, 422)


def test_reinvitar_con_reinicio_de_mfa_solo_sirve_a_quien_recibe_el_enlace_y_no_habilita_el_panel_sin_mfa(db, mails, web, admin):
    user, secret = admin
    mails.clear()
    _, link, _, _ = platform.reinviteAdministrator(db, "Perdió el segundo factor", resetMfa=True)
    assert [m["to"] for m in mails] == [user.correoElectronico]  # el enlace va solo al correo registrado de la cuenta
    assert web.post("/api/v1/auth/login", json={"identificador": user.usuario, "acceso": "PLATAFORMA", "password": PASSWORD}).status_code >= 400  # sin el enlace nadie entra
    session = platform.completeActivation(db, link.split("codigo=")[1], user.usuario, NEW_PASSWORD)
    headers = {"Authorization": f"Bearer {session.tokens.accessToken}"}
    assert web.get("/api/v1/platform/me", headers=headers).json()["requiereConfigurarMfa"] is True
    for path in ("/platform/moderators", "/audit", "/platform/transfer"):
        response = web.get(f"/api/v1{path}", headers=headers)
        assert response.status_code == 403, (path, response.status_code)  # hasta activar el MFA solo puede configurarlo


def test_al_reemplazar_se_revocan_las_sesiones_anteriores_incluido_el_token_de_renovacion(db, mails, web, admin, moderator):
    old, oldSecret = admin
    new, newSecret = moderator
    oldTokens = loginTokens(web, old, oldSecret)
    newTokens = loginTokens(web, new, newSecret)
    assert activeSessions(db, old) >= 1 and activeSessions(db, new) >= 1
    platform.replaceAdministrator(db, new.correoElectronico, "Reemplazo")
    assert activeSessions(db, old) == 0 and activeSessions(db, new) == 0  # la persona nueva vuelve a iniciar sesión con su rol vigente
    for tokens in (oldTokens, newTokens):
        assert web.get("/api/v1/platform/me", headers={"Authorization": f"Bearer {tokens['accessToken']}"}).status_code in (401, 403)
        assert web.post("/api/v1/auth/refresh", json={"refreshToken": tokens["refreshToken"]}).status_code == 401


def test_el_enlace_de_recuperacion_se_envia_despues_de_guardarse(db, mails, web, admin):
    # Antes el correo salía (SMTP síncrono) con la fila de TokenCuenta bloqueada y sin confirmar: en SQL Server eso bloqueaba y, si el
    # commit fallaba, el enlace enviado no servía. Ahora se confirma y después se envía.
    user, _ = admin
    mails.clear()
    assert web.post("/api/v1/platform/password/forgot", json={"correoElectronico": user.correoElectronico}).status_code == 204
    [mail] = mails
    assert any(tipo == "RECUPERACION_PASSWORD" for tipo, _ in mail["committed"]["tokens"])
