# Persistencia de la medición del dispositivo en SQL Server REAL (esquema consolidado v5).
#
# El resto de las pruebas usan un esquema SQLite temporal generado desde los modelos. Esta prueba ejecuta el mismo flujo
# (puente -> sesión -> guardar -> historial -> eliminar DEMO) contra SQL Server, para comprobar los CHECK
# y los tipos DECIMAL. Es OPCIONAL y solo corre contra una base DESCARTABLE:
#
#   1. SQL Server descartable con GlucoLume_DB_v5.sql en la base GlucoLume_Descartable (procedimiento en docs/BASE_DE_DATOS.md §6).
#   2. TEST_SQLSERVER_URL="mssql+pyodbc://sa:<clave>@localhost:14333/GlucoLume_Descartable?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
#      TEST_SQLSERVER_CONFIRM=DESCARTABLE
#   3. python -m pytest tests/test_telemetry_sqlserver.py -v
#
# Sin esas variables se omite. Nunca apuntar a la base real: la prueba inserta usuarios y mediciones de prueba.

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

URL = os.environ.get("TEST_SQLSERVER_URL")
pytestmark = pytest.mark.skipif(
    not URL or os.environ.get("TEST_SQLSERVER_CONFIRM") != "DESCARTABLE" or not any(h in URL for h in ("@localhost", "@127.0.0.1")),
    reason="Prueba opcional con SQL Server descartable: ver el encabezado del archivo.",
)

from app.acquisition.telemetry import hub  # noqa: E402
from app.core.config import getSettings  # noqa: E402
from app.core.exceptions import AuthError  # noqa: E402
from app.integrations.email import sender  # noqa: E402
from app.models.measurement import Measurement  # noqa: E402
from app.schemas.acquisition import TelemetrySessionStart  # noqa: E402
from app.services import email as emailService  # noqa: E402
from app.services import measurement as measurements  # noqa: E402
from app.services import telemetry as telemetryService  # noqa: E402
from tests.test_account_deletion import makeUser  # noqa: E402
from tests.test_measurements import device  # noqa: E402
from tests.test_telemetry import Clock, FakeBridge  # noqa: E402


@pytest.fixture
def sql(monkeypatch):
    for key, value in {"API_ENV": "test", "DB_HOST": "localhost", "DB_NAME": "x", "DB_USER": "x", "DB_PASSWORD": "x",
                       "JWT_SECRET": "x" * 40, "FRONTEND_URL": "http://localhost:5173"}.items():
        monkeypatch.setenv(key, value)
    getSettings.cache_clear()

    class Inline:
        def submit(self, fn, *args, **kwargs):
            return fn(*args, **kwargs)

    monkeypatch.setattr(sender, "sendHtmlEmail", lambda *a, **k: None)
    monkeypatch.setattr(emailService, "_executor", Inline())
    engine = create_engine(URL)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    clock = Clock()
    hub.reset()
    hub.clock = clock
    yield session, clock, engine
    session.close()
    engine.dispose()
    hub.reset()
    getSettings.cache_clear()


def test_flujo_completo_en_sql_server(sql):
    db, clock, engine = sql
    tag = uuid.uuid4().hex[:8]
    user = makeUser(db, email=f"telemetria-{tag}@example.com", usuario=f"tel{tag}")
    profileId = measurements.getOwnProfile(db, user).idPerfilMedicion
    code = f"ARD-{tag}"
    dev = device(db, codigo=code)
    bridge = FakeBridge(db, clock, code=code)

    # Una medición anterior al cambio (sin ninguna columna nueva) sigue siendo válida: la migración es compatible.
    legacy = Measurement(idPerfilMedicion=profileId, idDispositivo=dev.idDispositivo, modoMedicion="OXIMETRIA",
                         estadoMedicion="CANCELADA", edadAlMomento=36, sexoModelo="FEMENINO")
    db.add(legacy)
    db.commit()

    bridge.seconds(1)
    started = telemetryService.startSession(db, user, TelemetrySessionStart(idPerfilMedicion=profileId, idDispositivo=dev.idDispositivo))
    assert started.estadoMedicion == "ADQUIRIENDO"
    bridge.seconds(9)
    demo = telemetryService.saveSession(db, user)
    assert demo.estadoMedicion == "COMPLETADA" and demo.esDemo and demo.origenGlucosa == "DEMO"

    # Se relee con una conexión nueva: lo confirmado quedó en la base, con sus tipos y unidades.
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT estadoMedicion, origenGlucosa, glucosaDispositivo, unidadGlucosa, indiceOptico, lecturasEstabilizadas, "
            "spo2, frecuenciaCardiaca, glucosaEstimada, versionAlgoritmo FROM dbo.Medicion WHERE idMedicion = :id"),
            {"id": demo.idMedicion}).one()
    assert row.estadoMedicion == "COMPLETADA" and row.origenGlucosa == "DEMO" and row.unidadGlucosa == "mg/dL"
    assert float(row.glucosaDispositivo) == 117.0 and float(row.indiceOptico) == 2.41492 and row.lecturasEstabilizadas == 8
    assert float(row.spo2) == 98.0 and row.frecuenciaCardiaca == 72 and row.glucosaEstimada is None
    assert row.versionAlgoritmo == telemetryService.FIRMWARE_ALGORITHM

    # Historial del usuario, con el origen; los indicadores no incluyen los datos DEMO.
    page = measurements.listOwnHistory(db, user)
    assert page.total == 2 and {i.idMedicion for i in page.items} == {legacy.idMedicion, demo.idMedicion}
    assert next(i for i in page.items if i.idMedicion == demo.idMedicion).origenGlucosa == "DEMO"
    assert measurements.ownStatistics(db, user, 7).cantidadMediciones == 0

    # Una medición sin calibrar (no DEMO) sí cuenta; el dispositivo sin glucosa guarda NULL, no cero.
    telemetryService.startSession(db, user, TelemetrySessionStart(idPerfilMedicion=profileId, idDispositivo=dev.idDispositivo))
    bridge.seconds(9, origen="SIN_CALIBRAR", glu="NA")
    real = telemetryService.saveSession(db, user)
    assert real.origenGlucosa == "SIN_CALIBRAR" and real.glucosaDispositivo is None and real.unidadGlucosa is None
    assert measurements.ownStatistics(db, user, 7).cantidadMediciones == 1

    # Los CHECK de la migración rechazan combinaciones imposibles.
    for values in ({"origenGlucosa": None, "glucosaDispositivo": 100, "unidadGlucosa": "mg/dL"},  # valor sin origen
                   {"origenGlucosa": "DEMO", "glucosaDispositivo": None},  # DEMO sin valor
                   {"origenGlucosa": "DEMO", "glucosaDispositivo": 100, "unidadGlucosa": "mmol/L"},  # unidad desconocida
                   {"origenGlucosa": "OTRO"}, {"indiceOptico": -1}, {"lecturasEstabilizadas": 0}):
        with pytest.raises(IntegrityError):
            db.execute(text(
                "UPDATE dbo.Medicion SET " + ", ".join(f"{k} = :{k}" for k in values) + " WHERE idMedicion = :id"),
                {**values, "id": legacy.idMedicion})
        db.rollback()

    # Guardar dos veces la misma sesión no duplica nada; los DEMO se eliminan sin tocar lo real.
    with pytest.raises(AuthError):
        telemetryService.saveSession(db, user)
    assert measurements.deleteOwnDemoMeasurements(db, user) == 1
    with pytest.raises(AuthError) as protected:
        measurements.deleteDemoMeasurement(db, user, real.idMedicion)
    assert protected.value.code == "DATO_NO_ELIMINABLE"
    remaining = {i.idMedicion for i in measurements.listOwnHistory(db, user).items}
    assert remaining == {legacy.idMedicion, real.idMedicion}
    assert measurements.listOwnHistory(db, user, origen="DEMO").total == 0


def test_modo_glucosa_experimental_se_guarda_y_se_recupera_con_su_modo_en_sql_server(sql):
    """Una medición iniciada como GLUCOSA_EXPERIMENTAL con el dispositivo conserva ese modo hasta la base y la API (migración 025)."""
    db, clock, engine = sql
    tag = uuid.uuid4().hex[:8]
    user = makeUser(db, email=f"glucosa-{tag}@example.com", usuario=f"glu{tag}")
    profileId = measurements.getOwnProfile(db, user).idPerfilMedicion
    code = f"ARD-{tag}"
    dev = device(db, codigo=code)
    bridge = FakeBridge(db, clock, code=code)
    bridge.seconds(1)
    started = telemetryService.startSession(db, user, TelemetrySessionStart(
        idPerfilMedicion=profileId, idDispositivo=dev.idDispositivo, modoMedicion="GLUCOSA_EXPERIMENTAL"))
    assert started.modoMedicion == "GLUCOSA_EXPERIMENTAL"
    bridge.seconds(9)
    saved = telemetryService.saveSession(db, user)
    assert saved.modoMedicion == "GLUCOSA_EXPERIMENTAL" and saved.estadoMedicion == "COMPLETADA"
    with engine.connect() as connection:  # conexión nueva: lo confirmado
        row = connection.execute(text(
            "SELECT modoMedicion, estadoMedicion, origenGlucosa, glucosaDispositivo, glucosaEstimada, idReglaMatriz "
            "FROM dbo.Medicion WHERE idMedicion = :id"), {"id": saved.idMedicion}).one()
    assert (row.modoMedicion, row.estadoMedicion, row.origenGlucosa) == ("GLUCOSA_EXPERIMENTAL", "COMPLETADA", "DEMO")
    assert float(row.glucosaDispositivo) == 117.0 and row.glucosaEstimada is None and row.idReglaMatriz is None  # DEMO no es una estimación
    assert measurements.getMeasurement(db, user, saved.idMedicion).modoMedicion == "GLUCOSA_EXPERIMENTAL"
    assert [i.modoMedicion for i in measurements.listOwnHistory(db, user, modo="GLUCOSA_EXPERIMENTAL").items] == ["GLUCOSA_EXPERIMENTAL"]
    # Las restricciones de la migración: sin resultado no se completa, y un DEMO no se copia a la estimación.
    for values in ({"glucosaDispositivo": None, "origenGlucosa": None, "unidadGlucosa": None},
                   {"glucosaEstimada": 117, "idMatriz": None}):
        with pytest.raises(IntegrityError):
            db.execute(text("UPDATE dbo.Medicion SET " + ", ".join(f"{k} = :{k}" for k in values) + " WHERE idMedicion = :id"),
                       {**values, "id": saved.idMedicion})
        db.rollback()
