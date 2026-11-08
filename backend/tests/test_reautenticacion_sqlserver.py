# Reautenticación contra SQL Server REAL, descartable: el límite de 3 fallos en 15 min por operación y usuario NO debe superarse aunque
# lleguen intentos simultáneos desde varias sesiones (bloqueo UPDLOCK sobre la fila de CredencialLocal). Es OPCIONAL: solo corre con una
# base DESCARTABLE localhost (se VACÍAN sus tablas), como las demás pruebas *_sqlserver.
#
#   TEST_SQLSERVER_URL="mssql+pyodbc://sa:<clave>@127.0.0.1:<puerto>/GlucoLume_Descartable?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
#   TEST_SQLSERVER_CONFIRM=DESCARTABLE
#   python -m pytest tests/test_reautenticacion_sqlserver.py -v

import os
import re
import threading

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import getSettings
from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.localCredential import LocalCredential
from app.services import auth as authService

URL = os.environ.get("TEST_SQLSERVER_URL")
pytestmark = pytest.mark.skipif(
    not URL or os.environ.get("TEST_SQLSERVER_CONFIRM") != "DESCARTABLE" or not any(h in URL for h in ("@localhost", "@127.0.0.1"))
    or re.search(r"/GlucoLume\?", URL or "") is not None,
    reason="Prueba opcional con SQL Server descartable: ver el encabezado del archivo.",
)

from tests.test_device_connection_sqlserver import wipe  # noqa: E402
from tests.test_account_deletion import PASSWORD, makeUser  # noqa: E402

WRONG = "OtraClave#2026"
HILOS = 8


@pytest.fixture
def engine(monkeypatch):
    for key, value in {"API_ENV": "test", "DB_HOST": "localhost", "DB_NAME": "GlucoLumeTest", "DB_USER": "test", "DB_PASSWORD": "test",
                       "JWT_SECRET": "x" * 40, "MFA_ENCRYPTION_KEY": Fernet.generate_key().decode(), "FRONTEND_URL": "http://localhost:5173",
                       "PLATFORM_MFA_REQUIRED": "false", "API_BASE_URL": "http://localhost:8000"}.items():
        monkeypatch.setenv(key, value)
    getSettings.cache_clear()
    engine = create_engine(URL)
    wipe(engine)
    yield engine
    engine.dispose()


def test_intentos_simultaneos_de_reautenticacion_no_superan_el_limite_en_sqlserver(engine):
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as db:
        makeUser(db)
        db.commit()
        idCredencial = db.scalar(select(LocalCredential.idCredencialLocal))

    resultados: list[str] = []
    lock = threading.Lock()
    barrera = threading.Barrier(HILOS)

    def intento():
        barrera.wait()  # todos arrancan a la vez
        with Session() as session:
            row = session.get(LocalCredential, idCredencial)
            try:
                ok = authService.verifyCurrentPassword(session, row, WRONG, "cambio_contrasena")
                session.commit()  # quien llama confirma el fallo (como en los servicios reales)
                marca = "CONTRASENA_CORRECTA" if ok else "FALLO_REGISTRADO"
            except AuthError as error:
                session.rollback()
                marca = error.code
        with lock:
            resultados.append(marca)

    hilos = [threading.Thread(target=intento) for _ in range(HILOS)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert resultados.count("FALLO_REGISTRADO") == 3, resultados  # exactamente el límite: ni uno más por la carrera
    assert resultados.count("CUENTA_BLOQUEADA") == HILOS - 3, resultados
    with Session() as db:
        filas = db.scalars(select(Audit).where(Audit.accion == "REAUTENTICACION_CONTADOR", Audit.observacion == "cambio_contrasena")).all()
        assert len(filas) == 3  # una fila por fallo registrado, sin duplicados
