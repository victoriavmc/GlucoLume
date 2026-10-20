# Administración de la plataforma: roles globales, primer administrador, moderadores, seguridad de cuentas, transferencia del
# control, dashboard global y accesos. Usa el esquema SQLite temporal de test_account_deletion.py, TOTP reales (pyotp) y
# el cliente HTTP con la autenticación REAL (tokens de sesión), no solo llamadas a servicios.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_platform.py -v

import re
import uuid

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.cli import initAdmin
from app.core import security
from app.core.exceptions import AuthError
from app.db.session import getDb
from app.main import app
from app.models.audit import Audit
from app.models.device import Device
from app.models.localCredential import LocalCredential
from app.models.platformTransfer import PlatformTransfer
from app.models.user import User
from app.models.userSession import UserSession
from app.schemas.device import DeviceRegisterRequest
from app.schemas.group import FamilyGroupCreateRequest
from app.schemas.matrix import MatrixCreateRequest
from app.schemas.platform import ModeratorInvite, Reauthentication
from app.services import auditQuery
from app.services import device as devices
from app.services import group as groups
from app.services import matrix as matrices
from app.services import platform as platform
from app.services import platformDashboard
from app.models.mfaRecoveryCode import MfaRecoveryCode
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import PASSWORD, audits, db, engine, mails, makeSession, makeUser, reload  # noqa: F401
from tests.test_institutions import expectError, freshLookupLimiter, institutional, team  # noqa: F401

ADMIN, MOD = platform.ADMIN, platform.MOD
NEW_PASSWORD = "Zorro#Lento-2027"


def enableMfa(db, user) -> str:
    """MFA habilitado con secreto conocido y un código de recuperación propio (único por usuario)."""
    secret, _ = platform.mfa.startSetup(db, user)
    factor = platform.mfa.getFactor(db, user)
    factor.habilitado = True
    factor.fechaConfirmacion = nowForDb()
    db.add(MfaRecoveryCode(idFactorMfa=factor.idFactorMfa, codigoHash=security.hashRecoveryCode(uuid.uuid4().hex)))
    db.commit()
    return secret


def platformUser(db, tipo, email, usuario, mfa=True):
    user = makeUser(db, tipoCuenta=tipo, email=email, usuario=usuario)
    secret = enableMfa(db, user) if mfa else None
    return user, secret


def code(db, user, secret) -> str:
    """Código TOTP vigente; se libera el 'paso usado' para poder reautenticar varias veces en una prueba."""
    factor = platform.mfa.getFactor(db, user)
    factor.ultimoPasoUsado = None
    db.commit()
    return pyotp.TOTP(secret).now()


def reauth(db, user, secret, password=PASSWORD) -> Reauthentication:
    return Reauthentication(password=password, codigo=code(db, user, secret))


def tokenIn(mails, index=-1) -> str:
    return re.search(r"(?:token=|#codigo=)([A-Za-z0-9_\-]+)", mails[index]["html"]).group(1)


@pytest.fixture(autouse=True)
def strictPolicy(engine, monkeypatch):
    """En estas pruebas rige la política real: las cuentas administrativas exigen MFA."""
    monkeypatch.setattr(platform, "mfaRequired", lambda: True)


@pytest.fixture
def admin(db, mails):
    return platformUser(db, ADMIN, "admin@example.com", "adminsys")


@pytest.fixture
def moderator(db, mails):
    return platformUser(db, MOD, "modsistema@example.com", "modsys")


@pytest.fixture
def web(engine, db):
    """Cliente HTTP con la autenticación real: login, MFA y tokens de sesión (solo se reemplaza la sesión de base)."""
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def getTestDb():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[getDb] = getTestDb
    client = TestClient(app, raise_server_exceptions=False)
    client.testDb = db
    yield client
    app.dependency_overrides.clear()


def login(web, user, secret=None, password=PASSWORD):
    response = web.post("/api/v1/auth/login", json={"identificador": user.usuario, "password": password})
    assert response.status_code == 200, response.text
    body = response.json()
    if body["estado"] == "MFA_REQUERIDO":
        factor = platform.mfa.getFactor(web.testDb, user)
        factor.ultimoPasoUsado = None  # permite varios inicios de sesión en el mismo intervalo de 30 s
        web.testDb.commit()
        verified = web.post("/api/v1/auth/mfa/verify", json={"challengeToken": body["challengeToken"], "codigo": pyotp.TOTP(secret).now()})
        assert verified.status_code == 200, verified.text
        body = verified.json()
    return {"Authorization": f"Bearer {body['tokens']['accessToken']}"}


# --- 1. Inicialización segura del primer administrador ----------------------------------------------------------------


def test_el_primer_administrador_se_inicializa_una_sola_vez_sin_contrasenas(db, mails):
    user, link, expires, sent = platform.initializeFirstAdmin(db, "Ana", "Pérez", "ana@example.com")
    assert sent and user.tipoCuenta == ADMIN and user.estado == "PENDIENTE" and user.usuario is None
    assert db.scalar(select(LocalCredential).where(LocalCredential.idUsuario == user.idUsuario)) is None  # sin contraseña
    assert "#codigo=" in link and mails[-1]["to"] == "ana@example.com"
    assert audits(db, "INICIALIZAR_ADMINISTRADOR")[0].modulo == "PLATAFORMA"
    # Una invitación pendiente para otro correo, o una cuenta existente, no permite crear otra.
    expectError("ADMINISTRADOR_PENDIENTE", platform.initializeFirstAdmin, db, "Otro", "Admin", "otro@example.com")
    renewed = platform.initializeFirstAdmin(db, "Ana", "Pérez", "ana@example.com")
    assert renewed[0].idUsuario == user.idUsuario and renewed[1] != link  # renueva el enlace, no duplica
    expectError("TOKEN_INVALIDO", platform._loadInvitation, db, link.split("codigo=")[1])  # el anterior dejó de servir
    # Activación: la persona define sus credenciales; con el administrador activo no se inicializa otro.
    token = renewed[1].split("codigo=")[1]
    platform.completeActivation(db, token, "anaadmin", NEW_PASSWORD)
    assert reload(db, User, user.idUsuario).estado == "ACTIVO"
    expectError("ADMINISTRADOR_EXISTENTE", platform.initializeFirstAdmin, db, "Otra", "Persona", "otra@example.com")
    assert db.scalar(select(func.count()).select_from(User).where(User.tipoCuenta == ADMIN)) == 1


def test_el_comando_de_inicializacion_pide_confirmacion_y_se_niega_si_ya_hay_administrador(db, mails, engine):
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    out = []
    base = ["--nombre", "Ana", "--apellido", "Pérez", "--correo", "ana@example.com"]
    assert initAdmin.run(base + ["--confirmar", "--mostrar-enlace"], factory, out.append) == 0
    assert any("administracion/activar#codigo=" in line for line in out)
    assert initAdmin.run(base + ["--confirmar"], factory, out.append) == 0  # renueva la invitación pendiente
    admin = reload(db, User, db.scalar(select(User.idUsuario).where(User.tipoCuenta == ADMIN)))
    admin.estado = "ACTIVO"
    db.commit()
    assert initAdmin.run(["--nombre", "X", "--apellido", "Y", "--correo", "x@example.com", "--confirmar"], factory, out.append) == 1
    assert "Ya existe un administrador" in out[-1]


def test_la_base_impide_dos_administradores_vigentes(db, mails, admin):
    other = makeUser(db, tipoCuenta=MOD, email="m2@example.com", usuario="m2")
    with pytest.raises(IntegrityError):
        db.execute(update(User).where(User.idUsuario == other.idUsuario).values(tipoCuenta=ADMIN))
        db.commit()
    db.rollback()


# --- 2-3. Acceso administrativo ------------------------------------------------------------------------------------


def test_el_administrador_inicia_sesion_con_mfa_y_entra_al_panel(db, mails, web, admin):
    user, secret = admin
    login_response = web.post("/api/v1/auth/login", json={"identificador": "adminsys", "password": PASSWORD}).json()
    assert login_response["estado"] == "MFA_REQUERIDO"  # la política administrativa exige MFA
    headers = login(web, user, secret)
    me = web.get("/api/v1/platform/me", headers=headers).json()
    assert me["rol"] == ADMIN and me["rolEtiqueta"] == "Administrador del sistema" and me["mfaHabilitado"]
    assert "GESTIONAR_MODERADORES" in me["permisos"] and "TRANSFERIR_ADMINISTRACION" in me["permisos"]
    assert web.get("/api/v1/platform/dashboard", headers=headers).status_code == 200


def test_un_usuario_normal_recibe_403_y_queda_registrado(db, mails, web, team):
    individual = makeUser(db, email="persona@example.com", usuario="persona")
    for user, name in ((individual, "persona"), (team.owner, team.owner.usuario)):
        headers = login(web, user)
        for path in ("/platform/me", "/platform/dashboard", "/platform/moderators", "/platform/transfer", "/platform/system"):
            response = web.get(f"/api/v1{path}", headers=headers)
            assert response.status_code == 403 and response.json()["codigo"] == "ACCESO_PLATAFORMA_DENEGADO", (name, path)
        assert web.post("/api/v1/platform/moderators", headers=headers, json={}).status_code in (403, 422)
    assert web.get("/api/v1/platform/me").status_code == 401  # sin sesión
    assert len(audits(db, "ACCESO_PLATAFORMA_DENEGADO")) >= 10


def test_sin_mfa_una_cuenta_administrativa_tampoco_opera_las_rutas_globales_existentes(db, mails, web):
    user, _ = platformUser(db, ADMIN, "sinmfa-admin@example.com", "adminsinmfa", mfa=False)
    headers = login(web, user)
    for path in ("/audit", "/devices", "/matrices/global"):
        response = web.get(f"/api/v1{path}", headers=headers)
        assert response.status_code == 403 and response.json()["codigo"] == "MFA_REQUERIDA_PLATAFORMA", path
    assert web.get("/api/v1/platform/me", headers=headers).json()["requiereConfigurarMfa"] is True


def test_el_rol_no_se_deduce_del_usuario_ni_del_correo(db, mails, web):
    fake = makeUser(db, email="admin@glucolume.com", usuario="administrador")  # nombre y dominio "de administrador"
    assert web.get("/api/v1/platform/me", headers=login(web, fake)).status_code == 403


# --- 4-7. Moderadores ---------------------------------------------------------------------------------------------


def test_incorporar_un_moderador_nuevo_activarlo_y_configurar_mfa(db, mails, web, admin):
    user, secret = admin
    data = ModeratorInvite(nombre="luis", apellido="gómez", correoElectronico="luis@example.com", reautenticacion=reauth(db, user, secret))
    moderator, sent, _ = platform.inviteModerator(db, user, data)
    assert sent and moderator.estadoAcceso == "INVITADO" and moderator.estadoCuenta == "PENDIENTE"
    created = reload(db, User, moderator.idUsuario)
    assert created.tipoCuenta == MOD and created.usuario is None  # el rol lo fija el servidor; sin credenciales
    assert db.scalar(select(LocalCredential).where(LocalCredential.idUsuario == created.idUsuario)) is None
    assert "Moderador del sistema" in mails[-1]["html"] and platform.PERMISSIONS[MOD]
    token = tokenIn(mails)
    # Mientras no acepte, no puede iniciar sesión.
    with pytest.raises(AuthError):
        platform.authService.loginLocal(db, "luis@example.com", PASSWORD)
    assert platform._loadInvitation(db, token)[1].idUsuario == created.idUsuario  # el código identifica su invitación
    response = platform.completeActivation(db, token, "luismod", NEW_PASSWORD)
    assert response.estado == "AUTENTICADO"
    expectError("TOKEN_INVALIDO", platform.completeActivation, db, token, "otro", NEW_PASSWORD)  # un solo uso
    # Sin MFA: puede entrar a configurar su seguridad, pero no operar el panel.
    headers = login(web, created, password=NEW_PASSWORD)
    me = web.get("/api/v1/platform/me", headers=headers).json()
    assert me["rol"] == MOD and me["requiereConfigurarMfa"] is True
    blocked = web.get("/api/v1/platform/dashboard", headers=headers)
    assert blocked.status_code == 403 and blocked.json()["codigo"] == "MFA_REQUERIDA_PLATAFORMA"
    secret = enableMfa(db, created)  # configurar MFA
    headers = login(web, created, secret, NEW_PASSWORD)
    assert web.get("/api/v1/platform/me", headers=headers).json()["requiereConfigurarMfa"] is False
    assert web.get("/api/v1/platform/dashboard", headers=headers).json()["alcance"] == "TECNICO"
    assert audits(db, "INVITAR_MODERADOR_PLATAFORMA") and audits(db, "ACTIVAR_CUENTA_PLATAFORMA")


def test_la_invitacion_exige_reautenticacion_y_no_acepta_un_rol_del_cliente(db, mails, admin):
    user, secret = admin
    bad = ModeratorInvite(nombre="a", apellido="b", correoElectronico="x@example.com",
                          reautenticacion=Reauthentication(password="incorrecta", codigo=code(db, user, secret)))
    expectError("REAUTENTICACION_INVALIDA", platform.inviteModerator, db, user, bad)
    noCode = ModeratorInvite(nombre="a", apellido="b", correoElectronico="x@example.com", reautenticacion=Reauthentication(password=PASSWORD))
    expectError("REAUTENTICACION_INVALIDA", platform.inviteModerator, db, user, noCode)
    with pytest.raises(Exception):
        ModeratorInvite(nombre="a", apellido="b", correoElectronico="x@example.com", rol=ADMIN, reautenticacion=reauth(db, user, secret))
    assert db.scalar(select(func.count()).select_from(User).where(User.correoElectronico == "x@example.com")) == 0


def test_cuentas_existentes_solo_se_reinvitan_si_ya_son_de_plataforma(db, mails, admin, team):
    user, secret = admin
    for existing in (makeUser(db, email="indiv@example.com", usuario="indiv"), team.owner):
        data = ModeratorInvite(nombre="x", apellido="y", correoElectronico=existing.correoElectronico, reautenticacion=reauth(db, user, secret))
        expectError("CUENTA_NO_CONVERTIBLE", platform.inviteModerator, db, user, data)  # no se altera su tipo ni sus vínculos
        assert reload(db, User, existing.idUsuario).tipoCuenta != MOD
    mod, modSecret = platformUser(db, MOD, "ya@example.com", "yamod")
    expectError("MODERADOR_YA_ACTIVO", platform.inviteModerator, db, user, ModeratorInvite(
        nombre="x", apellido="y", correoElectronico="ya@example.com", reautenticacion=reauth(db, user, secret)))
    # Tras revocarle el acceso se lo puede invitar de nuevo: requiere aceptación y vuelve a empezar desde cero.
    platform.revokeModerator(db, user, mod.idUsuario, reauth(db, user, secret))
    again, sent, _ = platform.inviteModerator(db, user, ModeratorInvite(
        nombre="x", apellido="y", correoElectronico="ya@example.com", reautenticacion=reauth(db, user, secret)))
    assert sent and again.estadoCuenta == "PENDIENTE" and again.idUsuario == mod.idUsuario  # sin duplicar el Usuario
    with pytest.raises(AuthError):
        platform.authService.loginLocal(db, "yamod", PASSWORD)  # hasta aceptar no entra
    platform.completeActivation(db, tokenIn(mails), "yamod2", NEW_PASSWORD)
    assert reload(db, User, mod.idUsuario).estado == "ACTIVO"


def test_revocar_cierra_sesiones_y_el_acceso(db, mails, web, admin, moderator):
    user, secret = admin
    mod, modSecret = moderator
    headers = login(web, mod, modSecret)
    assert web.get("/api/v1/platform/dashboard", headers=headers).status_code == 200
    revoked = platform.revokeModerator(db, user, mod.idUsuario, reauth(db, user, secret))
    assert revoked.estadoAcceso == "REVOCADO"
    assert web.get("/api/v1/platform/me", headers=headers).status_code == 401  # la sesión ya no existe
    assert "revocado" in mails[-1]["subject"].lower()
    listed = {m.idUsuario: m for m in platform.listModerators(db, user)}
    assert listed[mod.idUsuario].estadoAcceso == "REVOCADO"


def test_el_moderador_no_gestiona_moderadores_ni_transfiere_el_control(db, mails, web, admin, moderator):
    mod, modSecret = moderator
    headers = login(web, mod, modSecret)
    assert web.get("/api/v1/platform/moderators", headers=headers).status_code == 403
    invite = {"nombre": "a", "apellido": "b", "correoElectronico": "n@example.com",
              "reautenticacion": {"password": PASSWORD, "codigo": code(db, mod, modSecret)}}
    assert web.post("/api/v1/platform/moderators", headers=headers, json=invite).status_code == 403
    other = makeUser(db, tipoCuenta=MOD, email="otro@example.com", usuario="otromod")
    start = {"idUsuarioDestino": str(other.idUsuario), "reautenticacion": {"password": PASSWORD, "codigo": code(db, mod, modSecret)}}
    assert web.post("/api/v1/platform/transfer", headers=headers, json=start).status_code == 403
    expectError("PERMISO_INSUFICIENTE", platform.inviteModerator, db, mod, ModeratorInvite(
        nombre="a", apellido="b", correoElectronico="n@example.com", reautenticacion=reauth(db, mod, modSecret)))
    assert db.scalar(select(func.count()).select_from(PlatformTransfer)) == 0
    assert reload(db, User, mod.idUsuario).tipoCuenta == MOD  # no puede cambiarse el rol


# --- 8-12. Auditoría, dashboard, inventario y funciones técnicas -------------------------------------------------


def test_auditoria_global_solo_para_el_administrador(db, mails, web, admin, moderator, team):
    user, secret = admin
    mod, modSecret = moderator
    assert web.get("/api/v1/audit", headers=login(web, user, secret)).status_code == 200
    assert web.get("/api/v1/audit", headers=login(web, mod, modSecret)).status_code == 403
    assert auditQuery.listGlobal(db, user).total > 0
    expectError("PERMISO_INSUFICIENTE", auditQuery.listGlobal, db, mod)
    # El propietario de la institución sigue viendo solo la suya.
    assert auditQuery.listInstitution(db, team.owner, team.id).total > 0


def test_dashboard_global_con_datos_reales_y_sin_datos_personales(db, mails, admin, moderator, team):
    user, secret = admin
    mod, _ = moderator
    makeUser(db, email="i1@example.com", usuario="i1")
    groups.createGroup(db, makeUser(db, email="g1@example.com", usuario="g1"), FamilyGroupCreateRequest(nombre="Familia"))
    scope = devices.platformScope(db, user)
    for index, sensor in enumerate(("MAX30102", "MAX30100", "MAX30102")):
        devices.registerDevice(db, scope, DeviceRegisterRequest(codigoDispositivo=f"DASH-{index}", modeloSensor=sensor, nombre="Oxímetro"))
    db.execute(update(Device).where(Device.codigoDispositivo == "DASH-2").values(estado="EN_MANTENIMIENTO"))
    db.commit()

    data = platformDashboard.dashboard(db, user, 30)
    assert data.alcance == "ADMINISTRADOR"
    assert data.usuarios.total == db.scalar(select(func.count()).select_from(User)) and data.usuarios.individuales == 2
    assert data.usuarios.institucionales >= 3 and data.usuarios.activas == data.usuarios.total
    assert data.instituciones.total == 1 and data.instituciones.activas == 1
    assert (data.instituciones.moderadores, data.instituciones.operadores) == (1, 1)
    assert (data.grupos.total, data.grupos.activos, data.grupos.usuariosAgrupados) == (1, 1, 1)
    assert (data.dispositivos.total, data.dispositivos.operativos, data.dispositivos.enMantenimiento) == (3, 2, 1)
    assert data.dispositivos.sinAsignar == 3 and data.dispositivos.asignados == 0
    assert data.mediciones.total == 0 and data.mediciones.serie == []
    assert any(m.modulo == "INSTITUCIONES" for m in data.actividadPorModulo) and data.eventosRecientes
    dumped = data.model_dump_json()
    for secret_value in ("@example.com", "Victoria", "Cortés", "persona"):
        assert secret_value not in dumped  # nada personal
    # El moderador solo ve la parte técnica.
    technical = platformDashboard.dashboard(db, mod, 30)
    assert technical.alcance == "TECNICO" and technical.usuarios is None and technical.eventosRecientes == []
    assert technical.dispositivos.total == 3
    expectError("PERIODO_INVALIDO", platformDashboard.dashboard, db, user, 15)
    status_ = platformDashboard.systemStatus(db, mod)
    assert {c.nombre for c in status_.componentes} >= {"Base de datos", "Correo (SMTP)"}


def test_inventario_global_y_funciones_tecnicas_del_moderador(db, mails, web, admin, moderator):
    user, secret = admin
    mod, modSecret = moderator
    devices.registerDevice(db, devices.platformScope(db, user), DeviceRegisterRequest(codigoDispositivo="INV-1", modeloSensor="MAX30102"))
    for who, who_secret in ((user, secret), (mod, modSecret)):
        listing = web.get("/api/v1/devices", headers=login(web, who, who_secret))
        assert listing.status_code == 200 and [d["codigoDispositivo"] for d in listing.json()["items"]] == ["INV-1"]
    # El moderador administra las matrices globales (versiones y reglas), no las privadas de una institución.
    created = matrices.createMatrix(db, mod, MatrixCreateRequest(ambito="GLOBAL", nombre="Matriz técnica"))
    assert created.ambito == "GLOBAL"
    assert web.get("/api/v1/matrices/global", headers=login(web, mod, modSecret)).status_code == 200


# --- 13-21. Transferencia del control ----------------------------------------------------------------------------


def test_transferencia_con_aceptacion_cambia_los_roles_en_una_transaccion(db, mails, web, admin, moderator):
    user, secret = admin
    mod, modSecret = moderator
    oldHeaders, newHeaders = login(web, user, secret), login(web, mod, modSecret)
    overview = platform.transferOverview(db, user)
    assert [e.idUsuario for e in overview.elegibles] == [mod.idUsuario] and overview.pendiente is None
    transfer = platform.startTransfer(db, user, mod.idUsuario, reauth(db, user, secret))
    assert transfer.estado == "PENDIENTE" and transfer.esOrigen and "Te ofrecen la administración" in mails[-1]["subject"]
    # Hasta aceptar no cambia ningún privilegio; el destinatario no puede autoproclamarse.
    assert reload(db, User, user.idUsuario).tipoCuenta == ADMIN and reload(db, User, mod.idUsuario).tipoCuenta == MOD
    assert web.get("/api/v1/platform/me", headers=newHeaders).json()["transferenciaPendiente"]["esDestino"] is True
    assert web.get("/api/v1/platform/moderators", headers=newHeaders).status_code == 403
    expectError("TRANSFERENCIA_PENDIENTE", platform.startTransfer, db, user, mod.idUsuario, reauth(db, user, secret))  # sin concurrentes
    expectError("TRANSFERENCIA_NO_ENCONTRADA", platform.respondTransfer, db, user, True, reauth(db, user, secret))  # el origen no acepta
    accepted = platform.respondTransfer(db, mod, True, reauth(db, mod, modSecret))
    assert accepted.estado == "ACEPTADA"
    assert reload(db, User, mod.idUsuario).tipoCuenta == ADMIN and reload(db, User, user.idUsuario).tipoCuenta == MOD
    assert db.scalar(select(func.count()).select_from(User).where(User.tipoCuenta == ADMIN, User.estado != "ELIMINADO")) == 1
    # Las sesiones abiertas reflejan el cambio de inmediato (el rol se lee de SQL Server en cada pedido).
    assert web.get("/api/v1/platform/me", headers=newHeaders).json()["rol"] == ADMIN
    assert web.get("/api/v1/platform/moderators", headers=newHeaders).status_code == 200
    assert web.get("/api/v1/platform/me", headers=oldHeaders).json()["rol"] == MOD
    assert web.get("/api/v1/platform/moderators", headers=oldHeaders).status_code == 403
    assert web.get("/api/v1/audit", headers=oldHeaders).status_code == 403
    assert web.get("/api/v1/audit", headers=newHeaders).status_code == 200
    # Auditoría: solicitud y aceptación quedan en el módulo PLATAFORMA con ambos protagonistas.
    page = auditQuery.listGlobal(db, reload(db, User, mod.idUsuario), modulo="PLATAFORMA", tamanioPagina=100)
    assert {"SOLICITAR_TRANSFERENCIA_ADMINISTRACION", "ACEPTAR_TRANSFERENCIA_ADMINISTRACION"} <= {i.accion for i in page.items}


def test_rechazar_cancelar_y_restricciones_de_la_transferencia(db, mails, admin, moderator):
    user, secret = admin
    mod, modSecret = moderator
    transfer = platform.startTransfer(db, user, mod.idUsuario, reauth(db, user, secret))
    assert platform.respondTransfer(db, mod, False, reauth(db, mod, modSecret)).estado == "RECHAZADA"
    assert reload(db, User, user.idUsuario).tipoCuenta == ADMIN  # sigue el administrador original
    assert "rechazó" in mails[-1]["html"]
    platform.startTransfer(db, user, mod.idUsuario, reauth(db, user, secret))
    assert platform.cancelTransfer(db, user, reauth(db, user, secret)).estado == "CANCELADA"
    expectError("TRANSFERENCIA_NO_ENCONTRADA", platform.respondTransfer, db, mod, True, reauth(db, mod, modSecret))
    # Destinatarios inválidos.
    expectError("DESTINATARIO_INVALIDO", platform.startTransfer, db, user, uuid.uuid4(), reauth(db, user, secret))
    expectError("DESTINATARIO_INVALIDO", platform.startTransfer, db, user, user.idUsuario, reauth(db, user, secret))
    plain = makeUser(db, email="plain@example.com", usuario="plain")
    expectError("DESTINATARIO_INVALIDO", platform.startTransfer, db, user, plain.idUsuario, reauth(db, user, secret))
    noMfa, _ = platformUser(db, MOD, "sinmfa@example.com", "sinmfa", mfa=False)
    expectError("DESTINATARIO_SIN_MFA", platform.startTransfer, db, user, noMfa.idUsuario, reauth(db, user, secret))
    inactive, _ = platformUser(db, MOD, "inactivo@example.com", "inactivo")
    inactive.estado = "BLOQUEADO"
    db.commit()
    expectError("DESTINATARIO_INACTIVO", platform.startTransfer, db, user, inactive.idUsuario, reauth(db, user, secret))
    expectError("REAUTENTICACION_INVALIDA", platform.startTransfer, db, user, mod.idUsuario, Reauthentication(password="mala", codigo=code(db, user, secret)))
    assert transfer.estado == "PENDIENTE" and db.scalar(select(func.count()).select_from(PlatformTransfer).where(PlatformTransfer.estado == "PENDIENTE")) == 0


def test_nunca_queda_la_plataforma_sin_administrador(db, mails, admin, moderator):
    user, secret = admin
    mod, modSecret = moderator
    platform.startTransfer(db, user, mod.idUsuario, reauth(db, user, secret))
    # El administrador deja de estar activo antes de que el destinatario acepte: la transferencia se anula.
    reload(db, User, user.idUsuario).estado = "BLOQUEADO"
    db.commit()
    expectError("TRANSFERENCIA_OBSOLETA", platform.respondTransfer, db, mod, True, reauth(db, mod, modSecret))
    assert reload(db, User, mod.idUsuario).tipoCuenta == MOD and reload(db, User, user.idUsuario).tipoCuenta == ADMIN
    assert db.scalar(select(PlatformTransfer.estado)) == "CANCELADA"


def test_revocar_al_destinatario_cancela_la_transferencia(db, mails, admin, moderator):
    user, secret = admin
    mod, _ = moderator
    platform.startTransfer(db, user, mod.idUsuario, reauth(db, user, secret))
    platform.revokeModerator(db, user, mod.idUsuario, reauth(db, user, secret))
    assert db.scalar(select(PlatformTransfer.estado)) == "CANCELADA"


# --- 22. Contraseñas --------------------------------------------------------------------------------------------


def test_restablecer_la_contrasena_de_un_moderador_no_expone_credenciales(db, mails, web, admin, moderator):
    user, secret = admin
    mod, modSecret = moderator
    oldHeaders = login(web, mod, modSecret)
    moderatorRead, sent, message = platform.startModeratorPasswordReset(db, user, mod.idUsuario, reauth(db, user, secret))
    assert sent and "password" not in moderatorRead.model_dump_json().lower() and "token" not in message.lower()
    link = mails[-1]["html"]
    assert mails[-1]["to"] == "modsistema@example.com" and "plataforma/restablecer?token=" in link
    token = tokenIn(mails)
    platform.resetPassword(db, token, NEW_PASSWORD)
    expectError("TOKEN_INVALIDO", platform.resetPassword, db, token, "Otra#Clave-2028")  # un solo uso
    assert web.get("/api/v1/platform/me", headers=oldHeaders).status_code == 401  # sesiones cerradas
    assert web.post("/api/v1/auth/login", json={"identificador": "modsys", "password": PASSWORD}).status_code == 401
    assert login(web, mod, modSecret, NEW_PASSWORD)
    assert audits(db, "RESTABLECER_PASSWORD_MODERADOR") and audits(db, "RESTABLECER_PASSWORD_PLATAFORMA")
    stored = " ".join(filter(None, db.scalars(select(Audit.datosNuevos))))
    assert NEW_PASSWORD not in stored and token not in stored


def test_recuperar_contrasena_desde_el_acceso_administrativo_no_revela_si_existe(db, mails, web, moderator):
    mod, modSecret = moderator
    assert web.post("/api/v1/platform/password/forgot", json={"correoElectronico": "nadie@example.com"}).status_code == 204
    assert not mails
    assert web.post("/api/v1/platform/password/forgot", json={"correoElectronico": "modsistema@example.com"}).status_code == 204
    assert len(mails) == 1
    normal = makeUser(db, email="normal@example.com", usuario="normal")
    assert web.post("/api/v1/platform/password/forgot", json={"correoElectronico": normal.correoElectronico}).status_code == 204
    assert len(mails) == 1  # una cuenta común no usa este flujo
    done = web.post("/api/v1/platform/password/reset", json={"token": tokenIn(mails), "password": NEW_PASSWORD})
    assert done.status_code == 200 and NEW_PASSWORD not in done.text
    old = web.post("/api/v1/platform/password/reset", json={"token": "inexistente", "password": NEW_PASSWORD})
    assert old.status_code == 401


def test_cuentas_solo_google_no_tienen_contrasena_que_restablecer(db, mails, admin):
    user, secret = admin
    googleMod = makeUser(db, tipoCuenta=MOD, local=False, google=True, email="g@example.com", usuario="gmod")
    enableMfa(db, googleMod)
    expectError("CUENTA_SOLO_GOOGLE", platform.startModeratorPasswordReset, db, user, googleMod.idUsuario, reauth(db, user, secret))


def test_cambiar_la_propia_contrasena_exige_la_actual_y_mfa(db, mails, moderator):
    mod, modSecret = moderator
    current = makeSession(db, mod)
    other = makeSession(db, mod)
    expectError("REAUTENTICACION_INVALIDA", platform.changeOwnPassword, db, mod, current, "mala", NEW_PASSWORD, NEW_PASSWORD, code(db, mod, modSecret), None)
    expectError("CONFIRMACION_INVALIDA", platform.changeOwnPassword, db, mod, current, PASSWORD, NEW_PASSWORD, "otra", code(db, mod, modSecret), None)
    platform.changeOwnPassword(db, mod, current, PASSWORD, NEW_PASSWORD, NEW_PASSWORD, code(db, mod, modSecret), None)
    assert reload(db, UserSession, other.idSesion).fechaRevocacion is not None  # las demás sesiones se cierran
    assert reload(db, UserSession, current.idSesion).fechaRevocacion is None
    assert security.verifyPassword(NEW_PASSWORD, db.scalar(select(LocalCredential.passwordHash).where(LocalCredential.idUsuario == mod.idUsuario)))[0]


# --- 24. Suscripciones y pagos: nada comercial -------------------------------------------------------------------


def test_no_hay_operaciones_comerciales_en_la_administracion():
    paths = [path for path in app.openapi()["paths"] if path.startswith("/api/v1/platform")]
    assert paths and not any(word in path.lower() for path in paths for word in ("subscri", "pago", "payment", "factur", "billing"))
