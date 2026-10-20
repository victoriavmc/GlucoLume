# Activación administrativa con el código de un solo uso (/platform/activation/with-code): sin código no hay rol de plataforma; el rol lo fija la
# invitación y no la solicitud; el código es el de la invitación (solo su hash), vence, se usa una vez y se anula con intentos fallidos.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_platform_code_activation.py -v

import re
from datetime import timedelta

from sqlalchemy import func, select, update

from app.models.accountToken import AccountToken
from app.models.user import User
from app.services import auth as authService
from app.services import platform
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import audits, db, engine, makeUser, mails, reload  # noqa: F401 - fixtures
from tests.test_institutions import expectError, freshLookupLimiter, team  # noqa: F401 - fixtures
from tests.test_platform import (  # noqa: F401 - fixtures y ayudantes
    ADMIN, MOD, NEW_PASSWORD, PASSWORD, admin, code, enableMfa, login, platformUser, reauth, strictPolicy, tokenIn, web,
)

URL = "/api/v1/platform/activation/with-code"
GENERIC = "CODIGO_ACTIVACION_INVALIDO"


def body(user, code, **overrides):
    data = {"codigo": code, "usuario": "elegido", "password": NEW_PASSWORD, "confirmacion": NEW_PASSWORD}  # la identidad ya está en la invitación
    data.update(overrides)
    return data


def firstAdmin(db):
    user, link, _, _ = platform.initializeFirstAdmin(db, "Ana", "Pérez", "ana@example.com")
    return user, link.split("codigo=")[1]


def tokens(db, user):
    return db.scalar(select(func.count()).select_from(AccountToken).where(AccountToken.idUsuario == user.idUsuario, AccountToken.fechaUso.is_(None)))


# --- 1-4. Sin código, incorrecto, vencido, reutilizado ---------------------------------------------------------------------------


def test_sin_codigo_no_se_activa_nada_ni_se_acepta_un_rol_en_la_solicitud(db, mails, web):
    user, code = firstAdmin(db)
    data = body(user, code)
    data.pop("codigo")
    assert web.post(URL, json=data).status_code == 422  # el código es obligatorio
    assert web.post(URL, json=body(user, code, codigo="")).status_code == 422
    for extra in ({"rol": ADMIN}, {"tipoCuenta": ADMIN}, {"estado": "ACTIVO"}):
        assert web.post(URL, json={**body(user, code), **extra}).status_code == 422  # ningún campo de más: el rol no se elige desde el cliente
    assert reload(db, User, user.idUsuario).estado == "PENDIENTE"


def test_un_codigo_incorrecto_o_inexistente_recibe_siempre_la_misma_respuesta_y_queda_auditado(db, mails, web):
    user, code = firstAdmin(db)
    responses = [web.post(URL, json=body(user, "x" * 43)), web.post(URL, json=body(user, code[:-3] + "abc"))]  # inventado / casi correcto
    for response in responses:
        assert response.status_code == 400 and response.json()["codigo"] == GENERIC
    assert len({response.json()["detail"] for response in responses}) == 1  # no revela nada más
    assert reload(db, User, user.idUsuario).estado == "PENDIENTE" and len(audits(db, "ACTIVAR_CUENTA_PLATAFORMA_CODIGO")) == 2


def test_un_codigo_vencido_o_ya_usado_se_rechaza_igual(db, mails, web):
    user, code = firstAdmin(db)
    db.execute(update(AccountToken).where(AccountToken.idUsuario == user.idUsuario)
               .values(fechaCreacion=nowForDb() - timedelta(hours=3), fechaExpiracion=nowForDb() - timedelta(minutes=1)))
    db.commit()
    expired = web.post(URL, json=body(user, code))
    assert expired.status_code == 400 and expired.json()["codigo"] == GENERIC
    renewed = platform.initializeFirstAdmin(db, "Ana", "Pérez", "ana@example.com")[1].split("codigo=")[1]
    assert web.post(URL, json=body(user, renewed)).status_code == 200
    reused = web.post(URL, json=body(user, renewed, usuario="otro"))
    assert reused.status_code == 400 and reused.json()["codigo"] == GENERIC


def test_cada_codigo_activa_solo_su_propia_invitacion(db, mails, web, admin):
    first, firstCode = invitedModerator(db, mails, admin)
    second = platform.inviteModerator(db, admin[0], ModeratorInvite(nombre="Mario", apellido="Gil", correoElectronico="mario@example.com",
                                                                    reautenticacion=reauth(db, admin[0], admin[1])))
    secondUser = db.scalar(select(User).where(User.correoElectronico == "mario@example.com"))
    secondCode = tokenIn(mails)
    assert second and firstCode != secondCode
    assert web.post(URL, json=body(first, firstCode)).status_code == 200
    assert reload(db, User, first.idUsuario).estado == "ACTIVO" and reload(db, User, secondUser.idUsuario).estado == "PENDIENTE"  # el otro no se toca
    assert web.post(URL, json=body(secondUser, firstCode, usuario="otro")).json()["codigo"] == GENERIC  # el código usado no sirve para nadie más
    assert web.post(URL, json=body(secondUser, secondCode, usuario="mariogil")).status_code == 200


def test_el_endpoint_tiene_limite_de_solicitudes_por_ip(db, mails, web):
    user, _ = firstAdmin(db)
    statuses = [web.post(URL, json=body(user, "y" * 43)).status_code for _ in range(12)]
    assert 429 in statuses and statuses[0] == 400


# --- 5. Activación correcta y estados ---------------------------------------------------------------------------------------------


def test_el_codigo_valido_activa_al_administrador_inicial_y_queda_invalidado_sin_guardar_el_codigo(db, mails, web):
    user, code = firstAdmin(db)
    stored = db.scalars(select(AccountToken.tokenHash).where(AccountToken.idUsuario == user.idUsuario)).all()
    assert code not in stored and all(len(h) >= 32 for h in stored)  # solo el hash
    response = web.post(URL, json=body(user, code))
    assert response.status_code == 200, response.text
    session = response.json()
    assert session["estado"] == "AUTENTICADO"
    fresh = reload(db, User, user.idUsuario)
    assert (fresh.tipoCuenta, fresh.estado, fresh.usuario) == (ADMIN, "ACTIVO", "elegido")
    assert tokens(db, user) == 0  # invalidado
    headers = {"Authorization": f"Bearer {session['tokens']['accessToken']}"}
    me = web.get("/api/v1/platform/me", headers=headers).json()
    assert me["rol"] == ADMIN and me["requiereConfigurarMfa"] is True  # MFA pendiente: solo puede configurarla
    assert web.get("/api/v1/platform/moderators", headers=headers).status_code == 403
    assert audits(db, "ACTIVAR_CUENTA_PLATAFORMA")[-1].modulo == "PLATAFORMA"


def test_la_confirmacion_de_contrasena_y_la_politica_se_validan(db, mails, web):
    user, code = firstAdmin(db)
    assert web.post(URL, json=body(user, code, confirmacion="Otra#Clave-2027")).status_code in (400, 422)
    assert web.post(URL, json=body(user, code, password="corta", confirmacion="corta")).status_code in (400, 422)
    assert reload(db, User, user.idUsuario).estado == "PENDIENTE"


# --- 6-8. Segundo administrador, moderadores y escalada ------------------------------------------------------------------------------


def test_con_un_administrador_vigente_no_se_registra_otro_ni_se_inicializa(db, mails, web, admin):
    expectError("ADMINISTRADOR_EXISTENTE", platform.initializeFirstAdmin, db, "Otra", "Persona", "otra@example.com")
    # Un código de moderador no convierte a nadie en administrador, aunque se manipule la solicitud.
    moderator, _ = platformUser(db, MOD, "pendiente-mod@example.com", "pendmod")
    moderator.estado = "PENDIENTE"
    db.commit()
    code = platform._newActivationToken(db, moderator)[0]
    db.commit()
    assert web.post(URL, json={**body(moderator, code), "rol": ADMIN}).status_code == 422
    assert web.post(URL, json=body(moderator, code)).status_code == 200
    assert reload(db, User, moderator.idUsuario).tipoCuenta == MOD  # sigue siendo moderador
    assert [u.tipoCuenta for u in db.scalars(select(User).where(User.tipoCuenta == ADMIN))] == [ADMIN]


def test_el_administrador_invita_a_un_moderador_que_se_activa_con_su_codigo_individual(db, mails, web, admin):
    user, secret = admin
    headers = login(web, user, secret)
    invited = web.post("/api/v1/platform/moderators", headers=headers, json={
        "nombre": "Laura", "apellido": "Díaz", "correoElectronico": "laura@example.com",
        "reautenticacion": {"password": PASSWORD, "codigo": code(db, user, secret)}})
    assert invited.status_code in (200, 201), invited.text
    invitation = tokenIn(mails)
    pending = db.scalar(select(User).where(User.correoElectronico == "laura@example.com"))
    assert (pending.tipoCuenta, pending.estado) == (MOD, "PENDIENTE")
    other_code = web.post(URL, json=body(pending, invitation))
    assert other_code.status_code == 200, other_code.text
    assert (reload(db, User, pending.idUsuario).tipoCuenta, reload(db, User, pending.idUsuario).estado) == (MOD, "ACTIVO")


def test_un_usuario_comun_no_obtiene_un_rol_administrativo_por_ninguna_via(db, mails, web, team):
    common = makeUser(db, email="comun@example.com", usuario="comun")
    headers = login(web, common)
    assert web.post("/api/v1/platform/moderators", headers=headers, json={}).status_code in (403, 422)
    assert web.post(URL, json=body(common, "z" * 43)).status_code == 400  # su correo no tiene ninguna invitación
    registration = {"nombre": "Eva", "apellido": "Ruiz", "correoElectronico": "eva@example.com", "usuario": "evaruiz", "password": NEW_PASSWORD,
                    "tipoCuenta": ADMIN, "aceptaPolitica": True}
    assert web.post("/api/v1/auth/register", json=registration).status_code in (400, 422)
    assert reload(db, User, common.idUsuario).tipoCuenta != ADMIN and web.get("/api/v1/platform/me", headers=headers).status_code == 403


# --- 9-10. Login posterior y Google ----------------------------------------------------------------------------------------------------


def test_despues_de_activar_se_ingresa_con_contrasena_y_mfa_sin_volver_a_pedir_el_codigo(db, mails, web):
    user, code = firstAdmin(db)
    assert web.post(URL, json=body(user, code)).status_code == 200
    account = reload(db, User, user.idUsuario)
    secret = enableMfa(db, account)  # la persona configura su segundo factor
    first = web.post("/api/v1/auth/login", json={"identificador": "elegido", "password": NEW_PASSWORD}).json()
    assert first["estado"] == "MFA_REQUERIDO" and not first.get("tokens")  # la contraseña sola no alcanza, y no se pide ningún código de activación
    account.usuario = "elegido"
    headers = login(web, account, secret, password=NEW_PASSWORD)
    me = web.get("/api/v1/platform/me", headers=headers).json()
    assert me["rol"] == ADMIN and "GESTIONAR_MODERADORES" in me["permisos"] and me["requiereConfigurarMfa"] is False


def test_una_cuenta_con_google_pero_sin_rol_administrativo_recibe_acceso_denegado(db, mails, web, team):
    from app.models.externalIdentity import ExternalIdentity

    common = makeUser(db, email="google@example.com", usuario="googleuser")
    db.add(ExternalIdentity(idUsuario=common.idUsuario, proveedor="GOOGLE", subjectProveedor="google-sub-123"))
    db.commit()
    session = authService.issueSession(db, common, "Google")
    headers = {"Authorization": f"Bearer {session.tokens.accessToken}"}
    for path in ("/platform/me", "/platform/dashboard", "/platform/moderators"):
        response = web.get(f"/api/v1{path}", headers=headers)
        assert response.status_code == 403 and response.json()["codigo"] == "ACCESO_PLATAFORMA_DENEGADO", path


# --- Ruta principal /administracion/activar: enlaces, un solo camino y códigos sin exposición -------------------------------------------


import logging  # noqa: E402

import pytest  # noqa: E402

from app.models.audit import Audit  # noqa: E402
from app.schemas.platform import ModeratorInvite  # noqa: E402


def invitedModerator(db, mails, admin):
    user, secret = admin
    invite = ModeratorInvite(nombre="Laura", apellido="Díaz", correoElectronico="laura@example.com", reautenticacion=reauth(db, user, secret))
    platform.inviteModerator(db, user, invite)
    return db.scalar(select(User).where(User.correoElectronico == "laura@example.com")), tokenIn(mails)


def test_los_correos_nuevos_apuntan_a_la_ruta_principal_con_el_codigo_en_el_fragmento(db, mails, admin):
    mails.clear()
    platform.inviteModerator(db, admin[0], ModeratorInvite(nombre="Laura", apellido="Díaz", correoElectronico="laura@example.com",
                                                           reautenticacion=reauth(db, admin[0], admin[1])))
    link = re.search(r"https?://[^\s\"'<>]*administracion/activar[^\s\"'<>]*", mails[-1]["html"]).group(0)
    assert "/administracion/activar#codigo=" in link and "?" not in link  # el fragmento nunca llega a Nginx ni al Referer
    assert "/plataforma/activar" not in mails[-1]["html"]
    assert platform.activationLink("abc").endswith("/administracion/activar#codigo=abc")


@pytest.mark.parametrize("kind", ["administrador", "moderador"])
def test_ambos_caminos_exigen_un_codigo_valido_unico_vigente_y_de_su_invitacion(db, mails, web, admin, kind):
    # La cuenta del administrador solo existe pendiente si todavía no hay uno activo: en ese caso se usa un escenario sin administrador activo.
    if kind == "administrador":
        db.execute(update(User).where(User.idUsuario == admin[0].idUsuario).values(estado="ELIMINADO", fechaEliminacion=nowForDb()))
        db.commit()
        user, code = firstAdmin(db)
    else:
        user, code = invitedModerator(db, mails, admin)
    # Código de otra invitación o inventado, con datos que no son los de la invitación: siempre el mismo rechazo.
    assert web.post(URL, json=body(user, "q" * 43)).json()["codigo"] == GENERIC
    # Vencido.
    db.execute(update(AccountToken).where(AccountToken.idUsuario == user.idUsuario)
               .values(fechaCreacion=nowForDb() - timedelta(hours=3), fechaExpiracion=nowForDb() - timedelta(minutes=1)))
    db.commit()
    assert web.post(URL, json=body(user, code)).json()["codigo"] == GENERIC
    # Vigente y único: reinvitar anula el anterior; el nuevo sirve una sola vez.
    if kind == "administrador":
        fresh = platform.initializeFirstAdmin(db, "Ana", "Pérez", "ana@example.com")[1].split("codigo=")[1]
    else:
        fresh = platform._newActivationToken(db, user)[0]
        db.commit()
    assert fresh != code
    ok = web.post(URL, json=body(user, fresh))
    assert ok.status_code == 200, ok.text
    assert reload(db, User, user.idUsuario).estado == "ACTIVO"
    assert web.post(URL, json=body(user, fresh, usuario="segundo")).json()["codigo"] == GENERIC  # un solo uso
    assert reload(db, User, user.idUsuario).tipoCuenta == (ADMIN if kind == "administrador" else MOD)


def test_los_endpoints_anteriores_de_activacion_sin_identidad_ya_no_existen(db, mails, web):
    user, code = firstAdmin(db)
    for path, payload in (("/platform/activation/check", {"token": code}),
                          ("/platform/activation/complete", {"token": code, "usuario": "x" * 6, "password": NEW_PASSWORD})):
        assert web.post(f"/api/v1{path}", json=payload).status_code in (404, 405)
    assert reload(db, User, user.idUsuario).estado == "PENDIENTE"  # el único camino es el que valida también la identidad


def test_el_codigo_no_aparece_en_logs_respuestas_ni_auditoria_y_en_la_base_solo_su_hash(db, mails, web, caplog):
    caplog.set_level(logging.DEBUG)
    user, code = firstAdmin(db)
    responses = [
        web.post(URL, json=body(user, "w" * 43)),                                      # fallo: código inexistente
        web.post(URL, json=body(user, code, confirmacion="Otra#Clave-2027")),          # fallo de validación
        web.post(URL, json={**body(user, code), "rol": ADMIN}),                        # 422 por campo de más
    ]
    ok = web.post(URL, json=body(user, code))
    assert ok.status_code == 200
    surfaces = [caplog.text, *[r.text for r in responses], ok.text]
    for blob in surfaces:
        assert code not in blob
    db.expire_all()
    for row in db.scalars(select(Audit)):
        assert code not in " ".join(str(getattr(row, field) or "") for field in ("observacion", "datosPrevios", "datosNuevos", "detalle"))
    assert code not in " ".join(db.scalars(select(AccountToken.tokenHash)).all())  # solo el hash
    assert all(f"{code[:8]}" not in line for line in caplog.text.splitlines()), "ni siquiera un prefijo del código"
