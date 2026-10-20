# Registro del tipo de cuenta en el evento de acceso (Auditoria.tipoCuentaActor, incluida en el esquema consolidado GlucoLume_DB_v5.sql; ver DEC-02):
# el backend lo guarda y lo usa cuando la columna existe en la base instalada y sigue funcionando igual (infiriendo el tipo) cuando no existe.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_auth_access_account_type.py -v

from datetime import timedelta

import pytest
from sqlalchemy import FetchedValue, event, select, update
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.user import User
from app.services import authAccess, platformDashboard, schemaCompat
from app.services import auth as authService
from app.services import dashboard as dashboards
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import PASSWORD, db, engine, makeUser, mails  # noqa: F401 - fixtures
from tests.test_institutions import team  # noqa: F401 - fixtures
from tests.test_platform import admin, strictPolicy  # noqa: F401 - fixtures

WRONG = "OtraClave#2026"


def pair(segment):
    return segment.fallidos, segment.exitosos


def snapshot(db):
    start, end, _ = dashboards._range(30, None, None)
    data = authAccess.breakdown(db, start, end)
    return {name: pair(getattr(data, name)) for name in ("individual", "institucional", "plataforma", "sinClasificar")}


def plant(db, accion, user, *, recorded=None, resultado="FALLO", institution=None):
    audit = Audit(idUsuario=user.idUsuario if user is not None else None, tipoEvento="LOGIN", modulo="CUENTA", idInstitucion=institution, accion=accion,
                  resultado=resultado, fechaHora=nowForDb() - timedelta(minutes=1))
    if recorded is not None:
        audit.tipoCuentaActor = recorded  # viaja en el INSERT del evento (models/audit.py)
    db.add(audit)
    db.commit()


def recorded(db, **where):
    """{(accion, resultado, sin cuenta): tipoCuentaActor} de los eventos de acceso (lectura con Core: en el ORM la columna es diferida)."""
    table = Audit.__table__
    rows = db.execute(select(table.c.accion, table.c.resultado, table.c.idUsuario, table.c.tipoCuentaActor).where(table.c.tipoEvento == "LOGIN")).all()
    return {(r[0], r[1], r[2] is None): r[3] for r in rows}


# --- registerEvent ---------------------------------------------------------------------------------------------------------------------


def test_los_eventos_de_acceso_nuevos_registran_el_tipo_de_cuenta_de_quien_se_autentico(db, mails, team, admin):
    makeUser(db, email="ana@example.com", usuario="ana")
    authService.loginLocal(db, "ana", PASSWORD)  # individual, correcto
    with pytest.raises(AuthError):
        authService.loginLocal(db, "duenia", WRONG)  # institucional, fallido
    authService.loginLocal(db, "adminsys", PASSWORD)  # plataforma: primer factor
    with pytest.raises(AuthError):
        authService.loginLocal(db, "nadie-existe", WRONG)  # sin cuenta identificable
    db.expire_all()
    by = recorded(db)
    assert by[("LOGIN_PWD", "EXITO", False)] == "CONSUMIDOR_FINAL"
    assert by[("LOGIN_LOCAL", "FALLO", False)] == "USUARIO_INSTITUCIONAL"
    assert by[("LOGIN_PWD_MFA_PENDIENTE", "EXITO", False)] == "ADMINISTRADOR_PLATAFORMA"
    assert by[("LOGIN_LOCAL", "FALLO", True)] is None  # sin cuenta: no se inventa un tipo


def test_el_login_registra_el_tipo_en_el_insert_sin_update_ni_delete_sobre_la_auditoria(db, engine, mails, team):
    """GL-02: la auditoría es de solo inserción también para tipoCuentaActor. Ningún inicio de sesión (correcto, fallido o sin cuenta)
    emite UPDATE ni DELETE sobre Auditoria: la cuenta de la aplicación solo necesita INSERT y SELECT para registrarlos."""
    makeUser(db, email="ana@example.com", usuario="ana")
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(" ".join(statement.split()))

    event.listen(engine, "before_cursor_execute", capture)
    try:
        authService.loginLocal(db, "ana", PASSWORD)
        with pytest.raises(AuthError):
            authService.loginLocal(db, "duenia", WRONG)
        with pytest.raises(AuthError):
            authService.loginLocal(db, "nadie-existe", WRONG)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    audit = [s for s in statements if '"Auditoria"' in s or "[Auditoria]" in s or " Auditoria " in s]
    assert not [s for s in audit if s.upper().startswith(("UPDATE", "DELETE"))]
    inserts = [s for s in audit if s.upper().startswith("INSERT")]
    assert any("tipoCuentaActor" in s for s in inserts)  # el valor viaja en el INSERT del propio evento
    assert any("tipoCuentaActor" not in s for s in inserts)  # el evento sin cuenta identificable no nombra la columna
    db.expire_all()
    by = recorded(db)
    assert by[("LOGIN_PWD", "EXITO", False)] == "CONSUMIDOR_FINAL" and by[("LOGIN_LOCAL", "FALLO", True)] is None


def test_solo_los_eventos_de_acceso_registran_el_tipo(db, mails, team):
    table = Audit.__table__
    others = db.execute(select(table.c.accion, table.c.tipoCuentaActor).where(table.c.tipoEvento != "LOGIN")).all()
    assert others and all(row[1] is None for row in others)  # las altas de la institución del escenario, por ejemplo


def test_el_tipo_registrado_es_el_del_momento_aunque_la_cuenta_cambie_despues(db, mails, admin):
    ana = makeUser(db, email="ana@example.com", usuario="ana")
    authService.loginLocal(db, "ana", PASSWORD)
    db.execute(update(User).where(User.idUsuario == ana.idUsuario).values(tipoCuenta="USUARIO_INSTITUCIONAL"))  # edición manual de la base
    db.commit()
    db.expire_all()
    assert snapshot(db)["individual"] == (0, 1)  # manda lo que registró el evento, no el tipo de hoy


# --- Clasificación con el tipo registrado ------------------------------------------------------------------------------------------


def test_el_tipo_registrado_manda_y_los_eventos_sin_el_se_siguen_infiriendo(db, mails, team):
    ana = makeUser(db, email="ana@example.com", usuario="ana")
    plant(db, "LOGIN_PWD", ana, recorded="USUARIO_INSTITUCIONAL", resultado="EXITO")  # registrado: institucional (aunque hoy sea individual)
    plant(db, "LOGIN_PWD", ana, resultado="EXITO")  # anterior a la migración: sin registro, se infiere individual
    plant(db, "LOGIN_LOCAL", team.owner, recorded="CONSUMIDOR_FINAL")  # registrado: individual
    plant(db, "LOGIN_LOCAL", team.owner)  # sin registro: se infiere institucional
    plant(db, "LOGIN_LOCAL", None)  # sin cuenta: sin clasificar
    assert snapshot(db) == {"individual": (1, 1), "institucional": (1, 1), "plataforma": (0, 0), "sinClasificar": (1, 0)}


def test_un_tipo_registrado_contradictorio_con_la_institucion_del_evento_no_se_asigna(db, mails, team):
    ana = makeUser(db, email="ana@example.com", usuario="ana")
    plant(db, "LOGIN_LOCAL", ana, recorded="CONSUMIDOR_FINAL", institution=team.id)
    plant(db, "LOGIN_LOCAL", team.owner, recorded="USUARIO_INSTITUCIONAL", institution=team.id)
    assert snapshot(db) == {"individual": (0, 0), "institucional": (1, 0), "plataforma": (0, 0), "sinClasificar": (1, 0)}


def test_la_base_rechaza_un_tipo_que_no_es_de_cuenta(db, mails):
    ana = makeUser(db, email="ana@example.com", usuario="ana")
    plant_args = dict(accion="LOGIN_PWD", user=ana)
    with pytest.raises(IntegrityError):
        plant(db, plant_args["accion"], plant_args["user"], recorded="SUPERUSUARIO")
    db.rollback()


# --- Base instalada sin la columna---------------------------------------------------------------------------------------------------------


def test_sin_el_script_034_el_backend_no_nombra_la_columna_y_el_tablero_infiere_como_siempre(db, engine, mails, team, admin, monkeypatch):
    monkeypatch.setattr(schemaCompat, "auditAccountTypeReady", lambda session: False)
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        makeUser(db, email="ana@example.com", usuario="ana")
        authService.loginLocal(db, "ana", PASSWORD)
        with pytest.raises(AuthError):
            authService.loginLocal(db, "duenia", WRONG)
        db.expire_all()
        db.scalars(select(Audit)).all()  # SELECT de la entidad
        data = platformDashboard.dashboard(db, admin[0]).seguridad.accesosPorTipo
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert [s[:200] for s in statements if "tipoCuentaActor" in s] == []  # ni INSERT, ni SELECT de Auditoria, ni la consulta del tablero
    assert pair(data.individual) == (0, 1) and pair(data.institucional) == (1, 0)
    assert all(value is None for value in recorded(db).values())  # nada se escribió en la columna


def test_con_la_columna_los_select_de_la_entidad_no_la_piden(db, engine, mails):
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    makeUser(db, email="ana@example.com", usuario="ana")
    authService.loginLocal(db, "ana", PASSWORD)
    event.listen(engine, "before_cursor_execute", capture)
    try:
        db.expire_all()
        db.scalars(select(Audit)).all()
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert [s for s in statements if "Auditoria" in s] and not any("tipoCuentaActor" in s for s in statements)  # sí se leyó Auditoria, sin la columna


# --- Esquema consolidado -------------------------------------------------------------------------------------------------------------------


def test_el_esquema_consolidado_define_tipoCuentaActor_como_el_modelo_sin_valor_predeterminado(referenceSchema):
    """DEC-02: la regla del antiguo script 034 vive en database/reference/GlucoLume_DB_v5.sql. Columna anulable de 40, sin DEFAULT (los
    eventos anteriores y los que no tienen cuenta quedan en NULL: nunca se inventa un valor) y CHECK con los mismos cuatro tipos que el
    tablero. Que el esquema la incluya no prueba que una base ya instalada la tenga: eso lo resuelve schemaCompat en tiempo de ejecución."""
    import re

    table = Audit.__table__
    assert "tipoCuentaActor" in table.c and table.c.tipoCuentaActor.nullable and table.c.tipoCuentaActor.type.length == 40
    assert type(table.c.tipoCuentaActor.server_default) is FetchedValue  # marcador del ORM: no genera DEFAULT en la base
    assert re.search(r"^\t\[tipoCuentaActor\] \[nvarchar\]\(40\) NULL,$", referenceSchema, re.M)
    assert "FOR [tipoCuentaActor]" not in referenceSchema  # sin DEFAULT en el esquema
    assert "CK_Auditoria_tipoCuentaActor" in {constraint.name for constraint in table.constraints}
    check = re.search(r"CONSTRAINT \[CK_Auditoria_tipoCuentaActor\] CHECK\s+\((.*)\)\s*$", referenceSchema, re.M).group(1)
    assert "[tipoCuentaActor] IS NULL" in check
    assert set(re.findall(r"N'([A-Z_]+)'", check)) == {authAccess.ACCOUNT_INDIVIDUAL, authAccess.ACCOUNT_INSTITUTIONAL, *authAccess.ACCOUNTS_PLATFORM}
