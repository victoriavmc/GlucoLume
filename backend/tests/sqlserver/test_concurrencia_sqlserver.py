# Concurrencia REAL sobre SQL Server: dos «Conectar dispositivo» simultáneos de la MISMA cuenta individual no pueden crear dos dispositivos
# lógicos ni dos vínculos. Opt-in: sin las variables GLUCOLUME_CONCURRENCIA_* la prueba se omite. Ver tests/sqlserver/README.md.
#
# Seguridad: la base debe llamarse «..._Concurrencia_Prueba». Si no, la prueba FALLA (no se omite) para no tocar ninguna base real.

import os
import threading
import uuid
from datetime import date
from urllib.parse import quote_plus

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

from app.acquisition.telemetry import hub
from app.models.accountDeviceLink import AccountDeviceLink
from app.models.audit import Audit
from app.models.device import Device
from app.models.user import User
from app.services import individualDevice

PREFIJO = "GLUCOLUME_CONCURRENCIA_"
BASES_PROHIBIDAS = ("GlucoLume", "GlucoLume_Copia")


def _engine():
    values = {k: os.environ.get(PREFIJO + k) for k in ("HOST", "PORT", "NAME", "USER", "PASSWORD", "DRIVER")}
    if not all(values.values()):
        pytest.skip(f"Definir {PREFIJO}HOST, _PORT, _NAME, _USER, _PASSWORD y _DRIVER (ver tests/sqlserver/README.md).")
    name = values["NAME"]
    if name in BASES_PROHIBIDAS or not name.endswith("_Concurrencia_Prueba"):
        pytest.fail(f"Base no permitida para esta prueba: {name!r}. Debe terminar en _Concurrencia_Prueba.")
    cadena = (f"DRIVER={{{values['DRIVER']}}};SERVER={values['HOST']},{values['PORT']};DATABASE={name};"
              f"UID={values['USER']};PWD={values['PASSWORD']};TrustServerCertificate=yes")
    engine = create_engine("mssql+pyodbc:///?odbc_connect=" + quote_plus(cadena))
    if not inspect(engine).has_table("VinculoCuentaDispositivo", schema="dbo"):
        pytest.skip("La base de prueba no tiene el esquema: ejecutar preparar_base_prueba.ps1 (ver README).")
    return engine


@pytest.fixture
def engineSql():
    engine = _engine()
    yield engine
    engine.dispose()


@pytest.fixture
def hubConectado(monkeypatch):
    """Conexión de Arduino simulada a nivel del hub (sin puerto): identidad declarada, conectada."""
    monkeypatch.setattr(hub, "deviceState", lambda: "CONECTADO")
    monkeypatch.setattr(hub, "identity", lambda: {"nivel": "DECLARADA", "codigo": "ARD-CONCURRENCIA", "firmware": None, "sensor": None})


def _cuenta(session):
    token = uuid.uuid4().hex[:10]
    user = User(idUsuario=uuid.uuid4(), nombre="Concurrencia", apellido="Prueba", correoElectronico=f"conc-{token}@example.invalid",
                usuario=f"conc{token}", tipoCuenta="CONSUMIDOR_FINAL", estado="ACTIVO", fechaNacimiento=date(1990, 1, 1), sexo="FEMENINO")
    session.add(user)
    session.commit()
    return user.idUsuario


def test_dos_conectar_simultaneos_de_la_misma_cuenta_no_duplican(engineSql, hubConectado):
    Session = sessionmaker(bind=engineSql, autoflush=False, expire_on_commit=False)
    setup = Session()
    userId = _cuenta(setup)
    setup.close()

    barrera = threading.Barrier(2)
    resultados, errores = [], []

    def conectar():
        session = Session()
        try:
            cuenta = session.get(User, userId)
            barrera.wait(timeout=30)
            resultados.append(individualDevice.connectTestDevice(session, cuenta).idDispositivo)
        except Exception as error:  # noqa: BLE001 - se verifica abajo
            errores.append(error)
        finally:
            session.close()

    hilos = [threading.Thread(target=conectar) for _ in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(120)

    check = Session()
    try:
        assert not errores, errores
        assert len(set(resultados)) == 1, "las dos conexiones devolvieron dispositivos distintos"
        vinculos = check.scalars(select(AccountDeviceLink).where(AccountDeviceLink.idUsuario == userId)).all()
        assert len(vinculos) == 1 and vinculos[0].idDispositivo == resultados[0]
        creados = check.scalars(select(Audit).where(Audit.accion == "REGISTRAR_DISPOSITIVO", Audit.idUsuario == userId)).all()
        assert len(creados) == 1, f"se registraron {len(creados)} dispositivos lógicos para una sola cuenta"
        dispositivo = check.get(Device, resultados[0])
        assert dispositivo is not None and dispositivo.estado == "OPERATIVO"
    finally:
        check.close()
