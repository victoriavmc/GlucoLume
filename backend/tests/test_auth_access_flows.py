# Todos los flujos de autenticación frente al tablero de accesos (services/authAccess.py): un ingreso correcto es una sesión realmente abierta,
# cada intento cuenta una sola vez y lo que no es un intento de acceso no distorsiona los conteos.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_auth_access_flows.py -v
#
# Datos sintéticos sobre el esquema SQLite temporal de test_account_deletion.py: no tocan SQL Server.

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.userSession import UserSession
from app.services import accountActivation, authAccess, platform
from app.services import auth as authService
from app.services import dashboard as dashboards
from app.services import mfa as mfaService
from app.services import mfaRecovery as recovery
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import PASSWORD, db, enableMfa, engine, makeSession, makeUser, mails, totpCode  # noqa: F401 - fixtures
from tests.test_institution_staff import NEW_PASSWORD, addNewModerator
from tests.test_institutions import team  # noqa: F401 - fixtures
from tests.test_mfa_recovery import accountCode, activate, challenge, emailedCode
from tests.test_platform import admin, strictPolicy  # noqa: F401 - fixtures

WRONG = "OtraClave#2026"


def pair(segment):
    return segment.fallidos, segment.exitosos


def individual(db):
    start, end, _ = dashboards._range(30, None, None)
    return pair(authAccess.breakdown(db, start, end).individual)


def breakdown(db):
    start, end, _ = dashboards._range(30, None, None)
    return authAccess.breakdown(db, start, end)


def sessions(db):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(UserSession))


def actions(db):
    db.expire_all()
    return [e.accion for e in db.scalars(select(Audit).where(Audit.tipoEvento == "LOGIN").order_by(Audit.fechaHora, Audit.idAuditoria)).all()]


def wrongCode(secret):
    return "123456" if totpCode(secret) != "123456" else "654321"


def plant(db, accion, user, resultado="FALLO"):
    db.add(Audit(idUsuario=user.idUsuario, tipoEvento="LOGIN", modulo="CUENTA", accion=accion, resultado=resultado, fechaHora=nowForDb() - timedelta(minutes=1)))
    db.commit()


# --- Sin MFA / con MFA ---------------------------------------------------------------------------------------------------------------


def test_inicio_de_sesion_sin_mfa_abre_una_sesion_y_cuenta_una_vez(db, mails):
    makeUser(db)
    assert authService.loginLocal(db, "victoria", PASSWORD).estado == "AUTENTICADO"
    assert sessions(db) == 1 and individual(db) == (0, 1)  # una sesión, un ingreso


def test_mfa_pendiente_correcto_incorrecto_y_con_codigo_de_recuperacion_guardado(db, mails):
    user = makeUser(db)
    secret = enableMfa(db, user)  # con un código de recuperación guardado: ABCD-EFGH

    def newChallenge():
        response = authService.loginLocal(db, "victoria", PASSWORD)
        assert response.estado == "MFA_REQUERIDO"
        return response.challengeToken

    first = newChallenge()
    assert individual(db) == (0, 0) and sessions(db) == 0  # primer factor correcto: todavía sin sesión, no es un ingreso
    with pytest.raises(AuthError):
        authService.verifyMfaChallenge(db, first, wrongCode(secret), None)
    assert individual(db) == (1, 0)  # código incorrecto: un fallido
    assert authService.verifyMfaChallenge(db, first, totpCode(secret), None).estado == "AUTENTICADO"
    assert individual(db) == (1, 1) and sessions(db) == 1  # MFA completado: un único ingreso aunque haya dos eventos de auditoría
    assert authService.verifyMfaChallenge(db, newChallenge(), None, "ABCD-EFGH").estado == "AUTENTICADO"  # código de recuperación guardado
    assert individual(db) == (1, 2) and sessions(db) == 2
    with pytest.raises(AuthError):
        authService.loginLocal(db, "victoria", WRONG)
    assert individual(db) == (2, 2)
    assert actions(db).count("LOGIN_PWD_MFA") == 2 and sum(name.endswith("_MFA_PENDIENTE") for name in actions(db)) == 2


# --- Recuperación de MFA ---------------------------------------------------------------------------------------------------------------


def test_la_recuperacion_por_correo_desde_el_login_abre_sesion_y_es_un_ingreso_correcto(db, mails):
    user = makeUser(db)
    activate(db, user)
    started = recovery.startRecovery(db, challenge(db), PASSWORD)
    wrong = "000000" if emailedCode(mails) != "000000" else "111111"
    with pytest.raises(AuthError):
        recovery.verifyRecovery(db, started.recoveryToken, wrong)
    assert individual(db) == (1, 0) and sessions(db) == 0  # código de recuperación incorrecto: fallido; el primer factor no es un ingreso
    assert recovery.verifyRecovery(db, started.recoveryToken, emailedCode(mails)).estado == "AUTENTICADO"
    assert sessions(db) == 1 and individual(db) == (1, 1)  # la sesión que abrió la recuperación cuenta, una sola vez
    assert "LOGIN_RECUPERACION_MFA" in actions(db) and "MFA_RECUPERACION_COMPLETADA" in actions(db)


def test_la_recuperacion_hecha_desde_seguridad_no_abre_sesion_y_no_es_un_ingreso(db, mails):
    user = makeUser(db)
    activate(db, user)
    current = makeSession(db, user)  # la sesión desde la que se hace la recuperación ya existía
    recovery.startAccountRecovery(db, user, PASSWORD)
    recovery.completeAccountRecovery(db, user, current.idSesion, accountCode(mails))
    assert "MFA_RECUPERACION_COMPLETADA" in actions(db)
    assert sessions(db) == 1 and individual(db) == (0, 0)  # no abrió otra sesión: no es un ingreso


# --- Sesiones denegadas o bloqueadas ---------------------------------------------------------------------------------------------------


def test_sesiones_denegadas_o_bloqueadas_son_fallidas_y_no_abren_sesion(db, mails):
    blocked = makeUser(db, email="bloqueada@example.com", usuario="bloqueada")
    blocked.estado = "BLOQUEADO"
    db.commit()
    with pytest.raises(AuthError):
        authService.loginLocal(db, "bloqueada", PASSWORD)  # contraseña correcta, cuenta que no puede entrar
    makeUser(db, email="otra@example.com", usuario="otra")
    for _ in range(3):
        with pytest.raises(AuthError):
            authService.loginLocal(db, "otra", WRONG)  # el tercero bloquea temporalmente: sigue siendo un intento, no dos
    with pytest.raises(AuthError):
        authService.loginLocal(db, "otra", PASSWORD)  # durante el bloqueo ni la contraseña correcta sirve
    assert sessions(db) == 0 and individual(db) == (5, 0)


def test_el_segundo_factor_bloqueado_cuenta_cada_intento_una_vez(db, mails):
    user = makeUser(db)
    secret = enableMfa(db, user)
    token = authService.loginLocal(db, "victoria", PASSWORD).challengeToken
    for _ in range(mfaService.MAX_FAILED_MFA_ATTEMPTS):
        with pytest.raises(AuthError):
            authService.verifyMfaChallenge(db, token, wrongCode(secret), None)
    with pytest.raises(AuthError) as locked:
        authService.verifyMfaChallenge(db, token, totpCode(secret), None)  # bloqueado: ni el código correcto sirve
    assert locked.value.code == "MFA_BLOQUEADO"
    assert individual(db) == (mfaService.MAX_FAILED_MFA_ATTEMPTS + 1, 0) and sessions(db) == 0


def test_rotar_el_refresh_token_no_es_un_ingreso_y_reutilizarlo_no_es_un_intento_de_acceso(db, mails):
    makeUser(db)
    tokens = authService.loginLocal(db, "victoria", PASSWORD).tokens
    authService.refreshSession(db, tokens.refreshToken)  # rota: otra sesión, pero no otro ingreso
    with pytest.raises(AuthError):
        authService.refreshSession(db, tokens.refreshToken)  # reutilizado: control de seguridad, no se presentó ninguna credencial
    assert "REFRESH_REUTILIZADO" in actions(db)
    assert individual(db) == (0, 1)


# --- Activaciones y eventos que no son intentos --------------------------------------------------------------------------------------


def test_activar_una_cuenta_invitada_o_la_administrativa_abre_sesion_y_es_un_ingreso(db, mails, team):
    _, token = addNewModerator(db, team, mails)
    accountActivation.completeActivation(db, token, "luciasosa", NEW_PASSWORD, aceptaPolitica=True)
    assert pair(breakdown(db).institucional) == (0, 1)
    _, link, _, _ = platform.initializeFirstAdmin(db, "Ana", "Pérez", "ana@example.com")
    assert platform.completeActivation(db, link.split("codigo=")[1], "anaadmin", NEW_PASSWORD).estado == "AUTENTICADO"
    data = breakdown(db)
    assert pair(data.plataforma) == (0, 1) and pair(data.institucional) == (0, 1) and pair(data.sinClasificar) == (0, 0)
    assert sessions(db) == 2  # una sesión por ingreso contado


def test_las_acciones_que_no_son_intentos_de_acceso_no_distorsionan_los_conteos(db, mails):
    ana = makeUser(db)
    plant(db, "REFRESH_REUTILIZADO", ana)
    plant(db, "MFA_RECUPERACION_CODIGO_ENVIADO", ana)  # falla el envío del correo: no es un intento
    plant(db, "MFA_RECUPERACION_SOLICITADA", ana)  # revalidar la contraseña para pedir un código: no es un intento de ingreso
    plant(db, "MFA_RECUPERACION_COMPLETADA", ana, "EXITO")  # también la deja la recuperación de Seguridad, que no abre sesión
    plant(db, "LOGIN_PWD_MFA_PENDIENTE", ana, "EXITO")
    plant(db, "VINCULACION_GOOGLE", ana)  # ingreso con Google rechazado: sí es un intento fallido
    plant(db, "MFA_CODIGO_INVALIDO", ana)
    plant(db, "MFA_RECUPERACION_CODIGO_INVALIDO", ana)
    assert individual(db) == (3, 0)
