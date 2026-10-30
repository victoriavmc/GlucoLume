# «Notificaciones» en SQL Server REAL: reutiliza TODAS las pruebas de tests/test_user_notifications.py (mismos escenarios: unicidad, concurrencia,
# recordatorios, reintentos de correo, bandeja, permisos entre cuentas, equipos nuevos, retención y rutas) pero con un `engine` de SQL Server
# en lugar del esquema SQLite. Comprueba contra el motor real los tipos BIT, el índice único filtrado, la paginación con OFFSET, el borrado por
# tandas y la reserva atómica de cada ocurrencia con hilos que usan conexiones distintas.
#
# Es OPCIONAL y solo corre contra una base DESCARTABLE (se VACÍAN todas sus tablas antes de cada prueba):
#
#   1. Crear GlucoLume_Descartable con database/reference/GlucoLume_DB_v5.sql (`USE` apuntando a ella; docs/BASE_DE_DATOS.md §6).
#   2. TEST_SQLSERVER_URL="mssql+pyodbc://<cuenta>:<clave>@127.0.0.1,<puerto>/GlucoLume_Descartable?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
#      TEST_SQLSERVER_CONFIRM=DESCARTABLE
#   3. python -m pytest tests/test_user_notifications_sqlserver.py -v
#
# La cuenta debe poder vaciar las tablas (en la instancia descartable, sa). Sin esas variables se omite. NUNCA apuntar a la base real.

import os
import re

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine

from app.core.config import getSettings

URL = os.environ.get("TEST_SQLSERVER_URL")
pytestmark = pytest.mark.skipif(
    not URL or os.environ.get("TEST_SQLSERVER_CONFIRM") != "DESCARTABLE" or not any(h in URL for h in ("@localhost", "@127.0.0.1"))
    or re.search(r"/GlucoLume\?", URL or "") is not None,
    reason="Prueba opcional con SQL Server descartable: ver el encabezado del archivo.",
)

from tests.test_device_connection_sqlserver import wipe  # noqa: E402
from tests.test_account_deletion import audits, db, mails, makeUser  # noqa: E402, F401 - fixtures
from tests.test_user_notifications import *  # noqa: E402, F401, F403 - las mismas pruebas, contra SQL Server
from tests.test_user_notifications import http  # noqa: E402, F401 - fixture


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
