# Accesos del dashboard de la plataforma segmentados por tipo de cuenta (services/authAccess.py).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_auth_access.py -v
#
# Datos sintéticos sobre el esquema SQLite temporal de test_account_deletion.py: no tocan SQL Server. Los intentos se generan con los
# servicios reales de autenticación (login, MFA) o, cuando hace falta elegir la fecha o un contexto raro, plantando el evento de auditoría.

from datetime import timedelta

import pytest
from sqlalchemy import event, select, update

from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.institutionUser import InstitutionUser
from app.models.user import User
from app.services import auditClassification as classification
from app.services import authAccess
from app.services import auth as authService
from app.services import dashboard as dashboards
from app.services import platformDashboard
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import db, engine, makeUser, mails  # noqa: F401 - fixtures
from tests.test_account_lifecycle import secondInstitution
from tests.test_groups import create as createGroup
from tests.test_groups import person
from tests.test_institutions import institutional, team  # noqa: F401 - fixtures
from tests.test_platform import PASSWORD, admin, login, moderator, strictPolicy, web  # noqa: F401 - fixtures

WRONG = "OtraClave#2026"


def plant(db, accion, *, resultado="FALLO", user=None, institution=None, days=0, hours=0):
    """Un evento de acceso con fecha elegida (`days` y `hours` hacia atrás)."""
    db.add(Audit(idUsuario=user.idUsuario if user is not None else None, tipoEvento="LOGIN", modulo="CUENTA", idInstitucion=institution, accion=accion,
                 resultado=resultado, fechaHora=nowForDb() - timedelta(days=days, hours=hours)))
    db.commit()


def fail(db, user, **kwargs):
    plant(db, "LOGIN_PWD", user=user, **kwargs)


def ok(db, user, **kwargs):
    plant(db, "LOGIN_PWD", resultado="EXITO", user=user, **kwargs)


def access(db, actor, dias=30, **kwargs):
    return platformDashboard.dashboard(db, actor, dias, **kwargs).seguridad


def pair(segment):
    return segment.fallidos, segment.exitosos


def snapshot(breakdown):
    return {name: pair(getattr(breakdown, name)) for name in ("individual", "institucional", "plataforma", "sinClasificar")}


# --- Clasificación ------------------------------------------------------------------------------------------------------------


def test_cada_tipo_de_cuenta_muestra_sus_accesos_correctos_y_fallidos(db, mails, admin, moderator, team):
    ana = person(db, "ana")
    for _ in range(2):
        fail(db, ana)
    ok(db, ana)
    for member in (team.owner, team.moderator, team.operator):  # propietario, moderador y operadora de una institución
        fail(db, member)
        ok(db, member)
    ok(db, team.owner)
    fail(db, admin[0])
    ok(db, admin[0])
    ok(db, moderator[0])
    ok(db, moderator[0])
    data = access(db, admin[0]).accesosPorTipo
    assert snapshot(data) == {"individual": (2, 1), "institucional": (3, 4), "plataforma": (1, 3), "sinClasificar": (0, 0)}


def test_un_administrador_institucional_no_es_administrador_de_la_plataforma(db, mails, admin, moderator, team):
    # «Moderador» es un rol institucional Y una cuenta de plataforma: solo el tipo de cuenta decide, no el nombre del rol.
    fail(db, team.moderator)
    fail(db, team.owner)
    fail(db, moderator[0])
    data = access(db, admin[0]).accesosPorTipo
    assert pair(data.institucional) == (2, 0) and pair(data.plataforma) == (1, 0)


def test_una_cuenta_con_varias_instituciones_o_pertenencias_cuenta_una_vez_en_su_tipo(db, mails, admin, team):
    secondInstitution(db, team.moderator)  # el moderador institucional pasa a tener un segundo vínculo
    group = createGroup(db, person(db, "beto"))  # una cuenta individual en un grupo familiar sigue siendo individual
    assert group is not None
    fail(db, team.moderator)
    ok(db, team.moderator)
    beto = db.scalar(select(User).where(User.usuario == "beto"))
    fail(db, beto)
    data = access(db, admin[0]).accesosPorTipo
    assert snapshot(data) == {"individual": (1, 0), "institucional": (1, 1), "plataforma": (0, 0), "sinClasificar": (0, 0)}


def test_una_cuenta_eliminada_sigue_en_su_tipo(db, mails, admin):
    gone = person(db, "gone")
    fail(db, gone)
    db.execute(update(User).where(User.idUsuario == gone.idUsuario).values(estado="ELIMINADO", fechaEliminacion=nowForDb(), correoElectronico=None))
    db.commit()
    assert pair(access(db, admin[0]).accesosPorTipo.individual) == (1, 0)


def test_el_relevo_de_la_administracion_no_cambia_la_categoria_de_los_eventos(db, mails, admin, moderator):
    fail(db, admin[0])
    fail(db, moderator[0])
    before = snapshot(access(db, admin[0]).accesosPorTipo)
    db.execute(update(User).where(User.idUsuario == admin[0].idUsuario).values(tipoCuenta="MODERADOR_PLATAFORMA"))  # como platform.py: primero baja
    db.execute(update(User).where(User.idUsuario == moderator[0].idUsuario).values(tipoCuenta="ADMINISTRADOR_PLATAFORMA"))
    db.commit()
    db.expire_all()
    assert snapshot(access(db, moderator[0]).accesosPorTipo) == before == {
        "individual": (0, 0), "institucional": (0, 0), "plataforma": (2, 0), "sinClasificar": (0, 0)}


# --- Sin clasificar ------------------------------------------------------------------------------------------------------------


def test_un_identificador_inexistente_queda_sin_clasificar_y_no_se_reparte(db, mails, admin):
    with pytest.raises(AuthError):
        authService.loginLocal(db, "nadie-existe", WRONG)  # el evento no guarda ninguna cuenta
    person(db, "ana")
    with pytest.raises(AuthError):
        authService.loginLocal(db, "ana", WRONG)
    data = access(db, admin[0]).accesosPorTipo
    assert snapshot(data) == {"individual": (1, 0), "institucional": (0, 0), "plataforma": (0, 0), "sinClasificar": (1, 0)}


def test_un_contexto_contradictorio_no_se_asigna_a_ninguna_categoria(db, mails, admin, team):
    clean = person(db, "limpia")
    linked = person(db, "vinculada")  # cuenta individual con un vínculo institucional: no debería existir
    db.add(InstitutionUser(idInstitucion=team.id, idUsuarioInvitado=linked.idUsuario, rolInstitucion="OPERADOR", estadoRelacion="BAJA",
                           fechaBaja=nowForDb(), origenVinculo="INVITACION", idUsuarioInvitador=team.owner.idUsuario))
    db.commit()
    fail(db, clean)
    fail(db, linked)
    fail(db, clean, institution=team.id)  # evento de una cuenta individual anotado en una institución
    fail(db, admin[0], institution=team.id)  # y uno de plataforma
    data = access(db, admin[0]).accesosPorTipo
    assert snapshot(data) == {"individual": (1, 0), "institucional": (0, 0), "plataforma": (0, 0), "sinClasificar": (3, 0)}


def test_un_acceso_fallido_de_personal_institucional_con_su_institucion_anotada_sigue_siendo_institucional(db, mails, admin, team):
    with pytest.raises(AuthError):
        authService.loginLocal(db, "operadora", WRONG)  # el servicio anota la institución cuando la cuenta pertenece a una sola
    [event] = db.scalars(select(Audit).where(Audit.accion == "LOGIN_LOCAL")).all()
    assert event.idInstitucion == team.id
    assert pair(access(db, admin[0]).accesosPorTipo.institucional) == (1, 0)


# --- Un intento, una vez --------------------------------------------------------------------------------------------------------


def test_el_ingreso_con_mfa_cuenta_una_vez_y_el_paso_intermedio_no_es_un_ingreso(db, mails, web, admin):
    user, secret = admin
    login(web, user, secret)
    events = [e.accion for e in db.scalars(select(Audit).where(Audit.tipoEvento == "LOGIN").order_by(Audit.fechaHora)).all()]
    assert any(name.endswith("_MFA_PENDIENTE") for name in events) and any(name.endswith("_MFA") for name in events)
    data = access(db, user).accesosPorTipo
    assert pair(data.plataforma) == (0, 1)  # dos eventos de auditoría, un único ingreso
    assert data.exitosos == 1 and data.fallidos == 0


def test_un_inicio_de_sesion_con_mfa_pendiente_no_es_un_ingreso_correcto(db, mails, admin):
    authService.loginLocal(db, "adminsys", PASSWORD, acceso=authService.ACCESO_PLATAFORMA)  # solo el primer factor
    assert pair(access(db, admin[0]).accesosPorTipo.plataforma) == (0, 0)


def test_el_bloqueo_temporal_no_es_otro_intento_y_la_recuperacion_de_mfa_no_es_un_ingreso(db, mails, admin):
    target = person(db, "objetivo")
    for _ in range(3):
        with pytest.raises(AuthError):
            authService.loginLocal(db, "objetivo", WRONG)
    plant(db, classification.ACCION_BLOQUEO_CUENTA, user=target)
    plant(db, "MFA_RECUPERACION_SOLICITADA", resultado="EXITO", user=target)
    plant(db, "MFA_RECUPERACION_CODIGO_ENVIADO", resultado="EXITO", user=target)
    plant(db, "MFA_RECUPERACION_COMPLETADA", resultado="EXITO", user=target)
    plant(db, "CAMBIAR_PASSWORD", resultado="EXITO", user=target)
    data = access(db, admin[0]).accesosPorTipo
    assert pair(data.individual) == (3, 0)


# --- Consistencia con los totales y filtros temporales ---------------------------------------------------------------------------


def test_los_tipos_suman_exactamente_los_totales_generales(db, mails, admin, team):
    with pytest.raises(AuthError):
        authService.loginLocal(db, "nadie-existe", WRONG)
    ana = person(db, "ana")
    fail(db, ana)
    ok(db, ana)
    fail(db, team.owner)
    ok(db, admin[0])
    ok(db, team.operator)
    fail(db, team.operator)
    security = access(db, admin[0])
    breakdown = security.accesosPorTipo
    assert security.loginsFallidos == breakdown.fallidos == sum(getattr(breakdown, name).fallidos for name in snapshot(breakdown))
    assert security.loginsExitosos == breakdown.exitosos == sum(getattr(breakdown, name).exitosos for name in snapshot(breakdown))
    assert (security.loginsFallidos, security.loginsExitosos) == (4, 3)
    # El total sale de los mismos eventos que el desglose de motivos del tablero.
    assert sum(reason.total for reason in security.motivosFallo) == security.loginsFallidos


def test_el_periodo_se_aplica_igual_a_los_tres_tipos_y_a_los_sin_clasificar(db, mails, admin, team):
    ana = person(db, "ana")
    for days in (0, 3, 20, 60):  # hoy, hace 3 días, hace 20 y hace 60
        fail(db, ana, days=days)
        fail(db, team.owner, days=days)
        fail(db, admin[0], days=days)
        plant(db, "LOGIN_PWD", user=None, days=days)
        ok(db, ana, days=days)
    for dias, expected in ((7, 2), (30, 3), (90, 4)):
        data = access(db, admin[0], dias=dias).accesosPorTipo
        assert snapshot(data) == {
            "individual": (expected, expected), "institucional": (expected, 0), "plataforma": (expected, 0), "sinClasificar": (expected, 0)}, dias


def test_el_rango_por_fechas_respeta_los_dos_extremos(db, mails, admin, team):
    ana = person(db, "ana")
    for days in (0, 2, 4, 6):
        fail(db, ana, days=days)
        fail(db, team.owner, days=days)
    today = nowForDb().date()
    data = access(db, admin[0], desde=today - timedelta(days=5), hasta=today - timedelta(days=1)).accesosPorTipo
    assert snapshot(data) == {"individual": (2, 0), "institucional": (2, 0), "plataforma": (0, 0), "sinClasificar": (0, 0)}
    start, end, _ = dashboards._range(30, today - timedelta(days=5), today - timedelta(days=1))
    assert snapshot(authAccess.breakdown(db, start, end)) == snapshot(data)


def test_sin_eventos_todo_es_cero_y_no_se_inventan_valores(db, mails, admin):
    security = access(db, admin[0])
    assert snapshot(security.accesosPorTipo) == {name: (0, 0) for name in ("individual", "institucional", "plataforma", "sinClasificar")}
    assert (security.loginsFallidos, security.loginsExitosos) == (0, 0)


# --- API ---------------------------------------------------------------------------------------------------------------------------


def test_el_endpoint_del_dashboard_entrega_el_desglose_y_el_moderador_no_lo_recibe(db, mails, web, admin, moderator):
    ana = person(db, "ana")
    fail(db, ana)
    ok(db, ana)
    headers = login(web, admin[0], admin[1])
    body = web.get("/api/v1/platform/dashboard", headers=headers).json()
    by = body["seguridad"]["accesosPorTipo"]
    assert set(by) == {"individual", "institucional", "plataforma", "sinClasificar"}
    assert by["individual"] == {"fallidos": 1, "exitosos": 1}
    assert body["seguridad"]["loginsFallidos"] == sum(segment["fallidos"] for segment in by.values())
    assert body["seguridad"]["loginsExitosos"] == sum(segment["exitosos"] for segment in by.values())
    technical = web.get("/api/v1/platform/dashboard", headers=login(web, moderator[0], moderator[1])).json()
    assert technical["alcance"] == "TECNICO" and technical["seguridad"] is None


def test_el_desglose_es_una_sola_consulta(db, mails, admin):
    """Total y tipos salen de una consulta con tabla derivada (SQL Server no agrupa por expresiones con subconsultas)."""
    compiled = []

    @event.listens_for(db.get_bind(), "before_cursor_execute")
    def capture(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        compiled.append(statement)

    start, end, _ = dashboards._range(30, None, None)
    before = len(compiled)
    authAccess.breakdown(db, start, end)
    event.remove(db.get_bind(), "before_cursor_execute", capture)
    assert len(compiled) - before == 1  # una sola consulta para total y tipos
