# Anulación técnica de IP contra SQL Server 2022 REAL, descartable (migración database/reference/GlucoLume_retencion_ip_tecnica.sql):
# permisos efectivos de la cuenta de mantenimiento, applock de sp_getapplock, pasadas simultáneas, errores parciales en lotes, preservación de
# eventos y cuentas, y vencimiento con fechas UTC. Es OPCIONAL: solo corre con una base DESCARTABLE localhost (se VACÍAN sus tablas).
#
#   TEST_SQLSERVER_URL="mssql+pyodbc://sa:<clave>@localhost:1433/GlucoLume_Descartable?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
#   TEST_SQLSERVER_RET_URL="mssql+pyodbc://glu_ret_test:<clave>@localhost:1433/GlucoLume_Descartable?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
#   TEST_SQLSERVER_CONFIRM=DESCARTABLE
#   python -m pytest tests/test_technical_retention_sqlserver.py -v

import os
import re
import threading
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.db.session import getRetentionEngine
from app.jobs import technicalRetention
from app.models.audit import Audit
from app.models.auditContext import AuditContext
from app.services import auditRetention
from app.utils.timeZone import argentinaToUtc, nowForDb
from tests.test_account_deletion import db, mails, makeUser  # noqa: F401 - fixtures
from tests.test_device_connection_sqlserver import engine, pytestmark as _omitirSinBaseDescartable  # noqa: F401 - base descartable

URL = os.environ.get("TEST_SQLSERVER_URL")
RET_URL = os.environ.get("TEST_SQLSERVER_RET_URL")
pytestmark = pytest.mark.skipif(
    not RET_URL or not URL or os.environ.get("TEST_SQLSERVER_CONFIRM") != "DESCARTABLE" or not any(h in RET_URL for h in ("@localhost", "@127.0.0.1"))
    or re.search(r"/GlucoLume\?", RET_URL or "") is not None,
    reason="Prueba opcional: requiere TEST_SQLSERVER_RET_URL (cuenta de mantenimiento) en una base descartable localhost.",
)

NOW = nowForDb()


@pytest.fixture
def retEngine():
    engine = create_engine(RET_URL, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture
def retSession(retEngine, monkeypatch):
    """Redirige el mantenimiento técnico a la cuenta de mantenimiento real (no a la de la prueba)."""
    maker = sessionmaker(bind=retEngine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(technicalRetention, "getRetentionEngine", lambda: retEngine)
    monkeypatch.setattr(technicalRetention, "getRetentionSessionFactory", lambda: maker)
    return maker


def event(db, *, when, user=None, ip="203.0.113.7", accion="LOGIN_LOCAL", tipo="LOGIN", resultado="FALLO"):
    row = Audit(idAuditoria=uuid.uuid4(), idUsuario=user.idUsuario if user is not None else None, tipoEvento=tipo,
                accion=accion, resultado=resultado, fechaHora=argentinaToUtc(when), modulo="AUTENTICACION")  # UTC, como el servidor
    db.add(row)
    db.flush()
    db.add(AuditContext(idAuditoria=row.idAuditoria, ipOrigen=ip, agenteUsuario="Mozilla/5.0 (prueba)", idCorrelacion="corr-sql"))
    db.commit()
    return row


def denied(sql: str, engine) -> bool:
    """True si la cuenta de mantenimiento NO puede ejecutar la sentencia (permiso denegado)."""
    try:
        with engine.begin() as connection:
            connection.execute(text(sql))
    except DBAPIError as error:
        return "permission" in str(error).lower() or "229" in str(error) or "230" in str(error)
    return False


def allowed(sql: str, engine) -> bool:
    with engine.begin() as connection:
        connection.execute(text(sql))
    return True


# --- Permisos efectivos de la cuenta de mantenimiento ------------------------------------------------------------

def test_update_permitido_solo_sobre_ip_y_agente(retEngine):
    assert allowed("UPDATE dbo.AuditoriaContexto SET ipOrigen = ipOrigen WHERE 1 = 0", retEngine)
    assert allowed("UPDATE dbo.AuditoriaContexto SET agenteUsuario = agenteUsuario WHERE 1 = 0", retEngine)
    assert denied("UPDATE dbo.AuditoriaContexto SET motivo = motivo WHERE 1 = 0", retEngine)
    assert denied("UPDATE dbo.AuditoriaContexto SET idCorrelacion = idCorrelacion WHERE 1 = 0", retEngine)
    assert denied("UPDATE dbo.AuditoriaContexto SET identificadorHash = identificadorHash WHERE 1 = 0", retEngine)


def test_rechaza_delete_y_modificacion_de_auditoria(retEngine):
    assert denied("DELETE FROM dbo.Auditoria WHERE 1 = 0", retEngine)
    assert denied("DELETE FROM dbo.AuditoriaContexto WHERE 1 = 0", retEngine)
    assert denied("UPDATE dbo.Auditoria SET accion = accion WHERE 1 = 0", retEngine)


def test_no_puede_tocar_cuentas_mediciones_ni_matrices(retEngine):
    assert denied("DELETE FROM dbo.Usuario WHERE 1 = 0", retEngine)
    assert denied("UPDATE dbo.Usuario SET nombre = nombre WHERE 1 = 0", retEngine)
    assert denied("SELECT COUNT(*) FROM dbo.Medicion", retEngine)  # ni siquiera puede leer mediciones
    assert denied("DELETE FROM dbo.Matriz WHERE 1 = 0", retEngine)
    assert denied("DELETE FROM dbo.ReglaMatriz WHERE 1 = 0", retEngine)


def test_puede_agregar_evento_de_mantenimiento(retEngine):
    assert allowed(
        "INSERT INTO dbo.Auditoria (idAuditoria, tipoEvento, accion, resultado, fechaHora, modulo) "
        "VALUES (NEWID(), 'CRUD', 'PRUEBA_PERMISO_RET', 'EXITO', SYSUTCDATETIME(), 'AUDITORIA')", retEngine)


# --- Applock de sp_getapplock ------------------------------------------------------------------------------------

def test_applock_exclusivo_entre_dos_conexiones(retEngine):
    first = technicalRetention._acquireLock(retEngine)
    assert first is not None
    try:
        assert technicalRetention._acquireLock(retEngine) is None  # otra pasada no entra mientras la primera tiene el lock
    finally:
        technicalRetention._releaseLock(first, retEngine)
    again = technicalRetention._acquireLock(retEngine)  # liberado: se puede volver a tomar
    assert again is not None
    technicalRetention._releaseLock(again, retEngine)


def test_pasadas_simultaneas_no_duplican_y_una_se_omite(db, mails, retSession, retEngine):
    user = makeUser(db)
    for days in range(120, 130):
        event(db, when=NOW - timedelta(days=days), user=user)
    results, barrier = [], threading.Barrier(2)

    def worker():
        barrier.wait()
        results.append(technicalRetention.run(NOW))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    anonymized = sum(r.get("contextosAnonimizados", 0) for r in results)
    assert anonymized == 10  # cada contexto se anula una sola vez entre las dos pasadas
    assert all("error" not in r for r in results)
    check = db.scalar(select(func.count()).select_from(AuditContext).where(AuditContext.ipOrigen.is_not(None)))
    assert check == 0


# --- Lotes: errores parciales, registros ya anonimizados y cortes -----------------------------------------------

def test_error_en_un_lote_conserva_los_confirmados_y_completa_al_reintentar(db, mails, retEngine):
    user = makeUser(db)
    for days in range(120, 125):  # 5 contextos vencidos
        event(db, when=NOW - timedelta(days=days), user=user)
    maker = sessionmaker(bind=retEngine, autoflush=False, expire_on_commit=False)
    session = maker()
    original = session.execute
    calls = {"updates": 0}

    def failingSecondUpdate(statement, *args, **kwargs):
        if "UPDATE" in str(statement).upper():
            calls["updates"] += 1
            if calls["updates"] == 2:
                raise RuntimeError("fallo simulado en el segundo lote")
        return original(statement, *args, **kwargs)

    session.execute = failingSecondUpdate
    try:
        with pytest.raises(RuntimeError):
            auditRetention.anonymizeDueContext(session, NOW, batch=2)
    finally:
        session.close()
    cleared = db.scalar(select(func.count()).select_from(AuditContext).where(AuditContext.ipOrigen.is_(None)))
    assert cleared == 2  # solo el primer lote quedó confirmado; el segundo se revirtió completo
    with maker() as retry:
        assert auditRetention.anonymizeDueContext(retry, NOW, batch=2) == 3  # el reintento completa el resto
    assert db.scalar(select(func.count()).select_from(AuditContext).where(AuditContext.ipOrigen.is_not(None))) == 0


def test_registros_ya_anonimizados_no_se_recuperan_ni_se_vuelven_a_contar(db, mails, retEngine):
    user = makeUser(db)
    row = event(db, when=NOW - timedelta(days=130), user=user)
    maker = sessionmaker(bind=retEngine, autoflush=False, expire_on_commit=False)
    with maker() as session:
        assert auditRetention.anonymizeDueContext(session, NOW) == 1
    with maker() as session:
        assert auditRetention.anonymizeDueContext(session, NOW) == 0
        assert auditRetention.countDueContext(session, NOW) == 0
    db.expire_all()
    assert db.get(AuditContext, row.idAuditoria).ipOrigen is None


# --- Vencimiento con fechas UTC y preservación de la evidencia ----------------------------------------------------

def test_fechas_almacenadas_son_utc(db):
    server = db.scalar(text("SELECT SYSUTCDATETIME()"))
    assert abs((server - argentinaToUtc(NOW)).total_seconds()) < 300  # la base guarda en UTC; la aplicación compara en UTC


def test_la_pasada_conserva_eventos_contexto_y_cuentas(db, mails, retSession, retEngine):
    user = makeUser(db)
    row = event(db, when=NOW - timedelta(days=200), user=user)
    before = db.scalar(select(func.count()).select_from(Audit))
    users = db.scalar(select(func.count()).select_from(type(user)))
    technicalRetention.run(NOW)
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Audit)) == before + 1  # + el evento del resultado del mantenimiento, nunca menos
    kept = db.get(Audit, row.idAuditoria)
    assert (kept.accion, kept.resultado, kept.idUsuario) == ("LOGIN_LOCAL", "FALLO", user.idUsuario)
    assert db.get(AuditContext, row.idAuditoria).idCorrelacion == "corr-sql"
    assert db.scalar(select(func.count()).select_from(type(user))) == users


def test_extension_de_baja_solo_con_la_version_vigente_aceptada_en_sql_server(db, mails, retEngine):
    """Con la cuenta de mantenimiento real: la extensión de la baja solo protege a quien aceptó la versión vigente de la política."""
    from app.models.consent import Consent
    from app.services.consent import POLICY_VERSION
    conAceptacion = makeUser(db, email="acepta@example.test", usuario="acepta", consent=False)
    sinAceptacion = makeUser(db, email="antigua@example.test", usuario="antigua", consent=False)
    db.add(Consent(idUsuario=conAceptacion.idUsuario, tipo="POLITICA_PRIVACIDAD", version=POLICY_VERSION, estado="ACEPTADO", fechaHora=NOW - timedelta(days=30)))
    db.add(Consent(idUsuario=sinAceptacion.idUsuario, tipo="POLITICA_PRIVACIDAD", version="1.1", estado="ACEPTADO", fechaHora=NOW - timedelta(days=30)))
    db.commit()
    for user in (conAceptacion, sinAceptacion):
        user.estado = "ELIMINADO"
        user.fechaEliminacion = NOW - timedelta(days=10)
    db.commit()
    rowAceptada = event(db, when=NOW - timedelta(days=120), accion="MFA_CODIGO_INVALIDO", tipo="LOGIN", resultado="FALLO", user=conAceptacion)
    rowAntigua = event(db, when=NOW - timedelta(days=120), accion="MFA_CODIGO_INVALIDO", tipo="LOGIN", resultado="FALLO", user=sinAceptacion)
    maker = sessionmaker(bind=retEngine, autoflush=False, expire_on_commit=False)
    with maker() as session:
        auditRetention.anonymizeDueContext(session, NOW)
    db.expire_all()
    assert db.get(AuditContext, rowAceptada.idAuditoria).ipOrigen is not None  # protegida por la baja reciente (aceptó la vigente)
    assert db.get(AuditContext, rowAntigua.idAuditoria).ipOrigen is None  # sin aceptación de la versión vigente: sin extensión
    assert POLICY_VERSION == "1.2"

