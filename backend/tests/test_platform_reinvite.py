# Re-invitación de un moderador de plataforma que conserva su MFA.
#
#     python -m pytest tests/test_platform_reinvite.py -v
#
# Hallazgos de la auditoría Cloudflare (run-1):
#  1) completeActivation entregaba sesión completa con solo el enlace del correo, sin pedir el MFA que la cuenta ya tenía.
#  2) La cuenta re-invitada queda PENDIENTE con credencial local, que es el filtro de la purga de cuentas sin verificar: un login anónimo con
#     su correo (o el job) la eliminaba junto con su MFA y su enlace de invitación.

from datetime import timedelta

from sqlalchemy import select

from app.models.mfaFactor import MfaFactor
from app.models.user import User
from app.schemas.platform import ModeratorInvite
from app.services import platform
from app.services import unverifiedAccounts
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import PASSWORD, audits, db, engine, mails, makeSession, makeUser, reload  # noqa: F401
from tests.test_institutions import expectError, freshLookupLimiter, institutional, team  # noqa: F401
from tests.test_platform import (  # noqa: F401
    ADMIN, MOD, NEW_PASSWORD, admin, code, enableMfa, login, moderator, platformUser, reauth, strictPolicy, tokenIn, web,
)


def reinvite(db, mails, admin, moderator):
    user, secret = admin
    mod, _ = moderator
    platform.revokeModerator(db, user, mod.idUsuario, reauth(db, user, secret))
    mod = reload(db, User, mod.idUsuario)
    mod.fechaCreacion = nowForDb() - timedelta(days=60)  # cuenta creada hace tiempo (ya fue activada antes)
    db.commit()
    again, sent, _ = platform.inviteModerator(db, user, ModeratorInvite(
        nombre="x", apellido="y", correoElectronico=mod.correoElectronico, reautenticacion=reauth(db, user, secret)))
    assert sent and again.estadoCuenta == "PENDIENTE"
    return mod


def test_activar_una_reinvitacion_con_mfa_exige_el_segundo_factor(db, mails, web, admin, moderator):
    mod = reinvite(db, mails, admin, moderator)
    assert platform.mfa.isEnabled(db, mod)
    response = platform.completeActivation(db, tokenIn(mails), "modreinv", NEW_PASSWORD)
    assert response.estado == "MFA_REQUERIDO" and response.tokens is None and response.challengeToken
    # El panel no se abre con el enlace del correo solo: ni siquiera existe un access token.
    assert web.post("/api/v1/auth/login", json={"identificador": "modreinv", "acceso": "PLATAFORMA", "password": NEW_PASSWORD}).json()["estado"] == "MFA_REQUERIDO"


def test_un_login_anonimo_no_elimina_a_un_moderador_reinvitado(db, mails, web, admin, moderator):
    mod = reinvite(db, mails, admin, moderator)
    token = tokenIn(mails)
    response = web.post("/api/v1/auth/login", json={"identificador": mod.correoElectronico, "password": "cualquiera-incorrecta"})
    assert response.status_code == 401
    db.expire_all()
    assert db.get(User, mod.idUsuario) is not None
    assert len(db.scalars(select(MfaFactor).where(MfaFactor.idUsuario == mod.idUsuario)).all()) == 1
    assert platform._loadInvitation(db, token) is not None  # el enlace del administrador sigue vigente


def test_el_job_de_limpieza_tampoco_elimina_cuentas_de_plataforma(db, mails, web, admin, moderator):
    mod = reinvite(db, mails, admin, moderator)
    assert unverifiedAccounts.deleteExpiredAccounts(db) == 0
    assert db.get(User, mod.idUsuario) is not None


def test_un_registro_publico_sin_verificar_sigue_venciendo(db, mails):
    from app.schemas.auth import RegisterRequest
    from app.services import auth as authService

    user = authService.registerLocal(db, RegisterRequest(
        nombre="Lia", apellido="Mora", correoElectronico="lia@example.com", password="Zafiro#Montana2026", usuario="liamora",
        tipoCuenta="CONSUMIDOR_FINAL", aceptaPoliticaPrivacidad=True))
    user.fechaCreacion = nowForDb() - timedelta(days=3)
    db.commit()
    assert unverifiedAccounts.deleteExpiredAccounts(db) == 1


def test_una_cuenta_vencida_no_toca_la_auditoria_y_libera_el_correo(db, mails):
    # GL-03: ni la API (registro, login, verificación) ni el job emiten UPDATE/DELETE sobre Auditoria/AuditoriaContexto.
    from sqlalchemy import event

    from app.models.audit import Audit
    from app.schemas.auth import RegisterRequest
    from app.services import auth as authService

    def register():
        return authService.registerLocal(db, RegisterRequest(
            nombre="Lia", apellido="Mora", correoElectronico="lia@example.com", password="Zafiro#Montana2026", usuario="liamora",
            tipoCuenta="CONSUMIDOR_FINAL", aceptaPoliticaPrivacidad=True))

    first = register()
    idUsuario = first.idUsuario
    first.fechaCreacion = nowForDb() - timedelta(days=3)
    db.commit()
    assert db.scalars(select(Audit).where(Audit.idUsuario == idUsuario)).first() is not None  # el registro dejó eventos
    statements = []
    engine = db.get_bind()
    listener = lambda conn, cursor, statement, *args: statements.append(statement.upper())  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        second = register()  # la API encuentra la cuenta vencida, la da de baja y registra la nueva con el mismo correo
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    assert second.idUsuario != idUsuario and second.correoElectronico == "lia@example.com"
    touched = [s for s in statements if s.lstrip().startswith(("UPDATE", "DELETE")) and "AUDITORIA" in s.split("WHERE")[0]]
    assert touched == []
    old = db.get(User, idUsuario)
    assert old.estado == "ELIMINADO" and old.correoElectronico is None and old.nombre is None and old.usuario is None
    assert db.scalars(select(Audit).where(Audit.idUsuario == idUsuario)).first() is not None  # la trazabilidad sigue

