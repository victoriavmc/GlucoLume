# Registro, consulta, edición y vinculación de dispositivos desde la conexión de un operador, en SQL Server REAL.
#
# Reutiliza TODAS las pruebas de tests/test_device_connection.py (mismos escenarios) pero con un `engine` de SQL Server en lugar del
# esquema SQLite temporal: comprueba las consultas, los tipos, los CHECK, la UNIQUE del código y la asignación atómica contra el motor
# real. Es OPCIONAL y solo corre contra una base DESCARTABLE (se VACÍAN todas sus tablas antes de cada prueba):
#
#   1. Crear GlucoLume_Descartable con database/reference/GlucoLume_DB_v5.sql (`USE` apuntando a ella; docs/BASE_DE_DATOS.md §6).
#   2. TEST_SQLSERVER_URL="mssql+pyodbc://@localhost/GlucoLume_Descartable?driver=ODBC+Driver+18+for+SQL+Server&Trusted_Connection=yes&TrustServerCertificate=yes"
#      TEST_SQLSERVER_CONFIRM=DESCARTABLE
#   3. python -m pytest tests/test_device_connection_sqlserver.py -v
#
# Sin esas variables se omite. NUNCA apuntar a la base real: borra los datos de todas las tablas.

import os
import re

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text

from app.core.config import getSettings

URL = os.environ.get("TEST_SQLSERVER_URL")
pytestmark = pytest.mark.skipif(
    not URL or os.environ.get("TEST_SQLSERVER_CONFIRM") != "DESCARTABLE" or not any(h in URL for h in ("@localhost", "@127.0.0.1"))
    or re.search(r"/GlucoLume\?", URL or "") is not None,
    reason="Prueba opcional con SQL Server descartable: ver el encabezado del archivo.",
)

from tests.test_account_deletion import audits, db, mails, makeUser, reload  # noqa: E402, F401 - fixtures
from tests.test_audit import api  # noqa: E402, F401 - fixture
from tests.test_device_connection import *  # noqa: E402, F403 - las mismas pruebas, contra SQL Server
from tests.test_institutions import freshLookupLimiter, team  # noqa: E402, F401 - fixtures
from tests.test_measurements import consumer  # noqa: E402, F401 - fixture
from tests.test_telemetry import bridge, clock, freshHub  # noqa: E402, F401 - fixtures

def wipe(engine) -> None:
    """Vacía TODAS las tablas de la base descartable (restricciones y disparadores apagados durante el borrado)."""
    with engine.begin() as connection:
        tables = [f"[{schema}].[{name}]" for schema, name in connection.execute(text(
            "SELECT s.name, t.name FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id WHERE t.is_ms_shipped = 0")).all()]
        connection.execute(text("SET QUOTED_IDENTIFIER ON; SET ANSI_NULLS ON"))
        for table in tables:
            connection.execute(text(f"ALTER TABLE {table} NOCHECK CONSTRAINT ALL; ALTER TABLE {table} DISABLE TRIGGER ALL"))
        for table in tables:
            connection.execute(text(f"SET QUOTED_IDENTIFIER ON; DELETE FROM {table}"))
        for table in tables:
            connection.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER ALL; ALTER TABLE {table} WITH CHECK CHECK CONSTRAINT ALL"))


@pytest.fixture
def engine(monkeypatch):
    """Sustituye al `engine` SQLite de las demás pruebas: misma configuración, base SQL Server descartable y vacía."""
    for key, value in {"API_ENV": "test", "DB_HOST": "localhost", "DB_NAME": "GlucoLumeTest", "DB_USER": "test", "DB_PASSWORD": "test",
                       "JWT_SECRET": "x" * 40, "MFA_ENCRYPTION_KEY": Fernet.generate_key().decode(), "FRONTEND_URL": "http://localhost:5173",
                       "PLATFORM_MFA_REQUIRED": "false", "API_BASE_URL": "http://localhost:8000"}.items():
        monkeypatch.setenv(key, value)
    getSettings.cache_clear()
    engine = create_engine(URL)
    wipe(engine)
    yield engine
    engine.dispose()
