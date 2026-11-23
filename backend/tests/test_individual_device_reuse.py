# Cuentas individuales de prueba: cada cuenta tiene SU dispositivo lógico vinculado, que se reutiliza (sin duplicar por conexión o medición),
# y el Arduino físico (siempre el mismo en las pruebas) se asocia a ese dispositivo lógico sin comparar el código físico con el UUID.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_individual_device_reuse.py -v

import threading
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import AuthError
from app.models.accountDeviceLink import AccountDeviceLink
from app.models.device import Device
from app.models.user import User
from app.services import individualDevice
from app.services import measurement as measurements
from tests.test_account_deletion import db, engine, mails, makeUser  # noqa: F401 - fixtures
from tests.test_telemetry import CODE, FakeBridge, clock, freshHub, startFor  # noqa: F401 - fixtures
from tests.test_telemetry import bridge as bridgeFixture  # noqa: F401 - fixture
from app.acquisition.telemetry import hub


def _account(db, email, usuario):
    user = makeUser(db, email=email, usuario=usuario)
    return user, measurements.getOwnProfile(db, user).idPerfilMedicion


def _logicalDevices(db):
    return db.scalars(select(Device).where(Device.modelo == individualDevice.MODELO_PRUEBA)).all()


@pytest.fixture
def cuentaA(db, mails):
    return _account(db, "a@example.com", "cuentaa")


@pytest.fixture
def cuentaB(db, mails):
    return _account(db, "b@example.com", "cuentab")


def test_primera_conexion_registra_un_dispositivo_logico_y_lo_vincula(db, cuentaA, bridgeFixture):
    user, _ = cuentaA
    bridgeFixture.seconds(1)
    device = individualDevice.connectTestDevice(db, user)
    link = db.scalar(select(AccountDeviceLink).where(AccountDeviceLink.idUsuario == user.idUsuario))
    assert link is not None and link.idDispositivo == device.idDispositivo and device.estado == "OPERATIVO"
    assert hub.isConfirmed(user.idUsuario, device.idDispositivo)


def test_reconectar_reutiliza_el_mismo_dispositivo_sin_duplicar(db, cuentaA, bridgeFixture):
    user, _ = cuentaA
    bridgeFixture.seconds(1)
    first = individualDevice.connectTestDevice(db, user)
    for _ in range(3):  # cada conexión (incluso repetida) reutiliza el registro operativo de la cuenta
        assert individualDevice.connectTestDevice(db, user).idDispositivo == first.idDispositivo
    assert len(_logicalDevices(db)) == 1


def test_cada_cuenta_tiene_su_propio_dispositivo_y_no_reutiliza_el_de_otra(db, cuentaA, cuentaB, bridgeFixture):
    (userA, _), (userB, _) = cuentaA, cuentaB
    bridgeFixture.seconds(1)
    devA = individualDevice.connectTestDevice(db, userA)
    devB = individualDevice.connectTestDevice(db, userB)
    assert devA.idDispositivo != devB.idDispositivo
    assert len(_logicalDevices(db)) == 2


def test_la_seleccion_solo_muestra_el_dispositivo_propio(db, cuentaA, cuentaB, bridgeFixture):
    (userA, profileA), (userB, profileB) = cuentaA, cuentaB
    bridgeFixture.seconds(1)
    devA = individualDevice.connectTestDevice(db, userA)
    individualDevice.connectTestDevice(db, userB)
    listed = measurements.listDevices(db, userA, profileA)
    assert [d.idDispositivo for d in listed] == [devA.idDispositivo]
    assert all(d.idDispositivo != individualDevice.ownLinkedDevice(db, userB).idDispositivo for d in listed)


def test_sin_vinculo_la_lista_esta_vacia_y_no_muestra_dispositivos_ajenos(db, cuentaA, cuentaB, bridgeFixture):
    (userA, profileA), (userB, _) = cuentaA, cuentaB
    bridgeFixture.seconds(1)
    individualDevice.connectTestDevice(db, userB)  # otra cuenta tiene su dispositivo; A todavía no
    assert measurements.listDevices(db, userA, profileA) == []


def test_dispositivo_no_operativo_se_reemplaza_y_el_anterior_queda_intacto(db, cuentaA, bridgeFixture):
    user, _ = cuentaA
    bridgeFixture.seconds(1)
    old = individualDevice.connectTestDevice(db, user)
    old.estado = "FUERA_DE_SERVICIO"
    db.commit()
    new = individualDevice.connectTestDevice(db, user)
    assert new.idDispositivo != old.idDispositivo and new.estado == "OPERATIVO"
    kept = db.get(Device, old.idDispositivo)
    assert kept is not None and kept.estado == "FUERA_DE_SERVICIO"  # historial del anterior conservado
    assert individualDevice.ownLinkedDevice(db, user).idDispositivo == new.idDispositivo


def test_medir_con_el_dispositivo_propio_no_compara_el_codigo_fisico(db, cuentaA, bridgeFixture, demoOn):
    user, profileId = cuentaA
    bridgeFixture.seconds(1)
    own = individualDevice.connectTestDevice(db, user)
    hub.reset()  # la conexión cambió: la confirmación de «Conectar» ya no vale
    bridgeFixture.seconds(1)  # el Arduino físico sigue conectado con su código CODE
    started = startFor(db, user, profileId, own)
    assert started.dispositivo.codigoDispositivo == own.codigoDispositivo and hub.session is not None


def test_no_se_puede_medir_con_el_dispositivo_de_otra_cuenta(db, cuentaA, cuentaB, bridgeFixture):
    (userA, profileA), (userB, _) = cuentaA, cuentaB
    bridgeFixture.seconds(1)
    individualDevice.connectTestDevice(db, userA)
    devB = individualDevice.connectTestDevice(db, userB)
    hub.reset()
    bridgeFixture.seconds(1)
    with pytest.raises(AuthError):
        startFor(db, userA, profileA, devB)
    assert hub.session is None


def test_conexiones_simultaneas_de_una_cuenta_no_duplican(db, cuentaA, bridgeFixture):
    # Dos pedidos que llegan con el vínculo todavía vacío: el segundo ve el primero y reutiliza el mismo dispositivo.
    user, _ = cuentaA
    bridgeFixture.seconds(1)
    first = individualDevice.connectTestDevice(db, user)
    second = individualDevice.connectTestDevice(db, user)
    assert first.idDispositivo == second.idDispositivo
    count = db.scalar(select(func.count()).select_from(AccountDeviceLink).where(AccountDeviceLink.idUsuario == user.idUsuario))
    assert count == 1


# --- Simulación de un Arduino compartido (DEMO_SHARED_PHYSICAL_DEVICE) ---------------------------------------------------------


@pytest.fixture
def demoOn(monkeypatch):
    from app.core.config import getSettings
    monkeypatch.setenv("DEMO_SHARED_PHYSICAL_DEVICE", "true")
    getSettings.cache_clear()
    yield
    getSettings.cache_clear()


def test_sin_simulacion_el_codigo_fisico_sigue_siendo_obligatorio(db, cuentaA, bridgeFixture):
    user, profileId = cuentaA
    bridgeFixture.seconds(1)
    own = individualDevice.connectTestDevice(db, user)
    hub.reset()
    bridgeFixture.seconds(1)
    with pytest.raises(AuthError) as raised:
        startFor(db, user, profileId, own)
    assert raised.value.code == "DISPOSITIVO_NO_COINCIDE" and hub.session is None


def test_con_simulacion_cada_cuenta_mide_con_su_registro_y_el_mismo_arduino(db, cuentaA, cuentaB, bridgeFixture, demoOn):
    (userA, profileA), (userB, profileB) = cuentaA, cuentaB
    bridgeFixture.seconds(1)
    devA = individualDevice.connectTestDevice(db, userA)
    devB = individualDevice.connectTestDevice(db, userB)
    hub.reset()
    bridgeFixture.seconds(1)  # un solo Arduino físico, con el código CODE
    startedA = startFor(db, userA, profileA, devA)
    assert startedA.dispositivo.codigoDispositivo == devA.codigoDispositivo
    hub.reset()
    bridgeFixture.seconds(1)
    startedB = startFor(db, userB, profileB, devB)
    assert startedB.dispositivo.codigoDispositivo == devB.codigoDispositivo
    assert devA.idDispositivo != devB.idDispositivo


def test_con_simulacion_no_se_usa_el_dispositivo_de_otra_cuenta(db, cuentaA, cuentaB, bridgeFixture, demoOn):
    (userA, profileA), (userB, _) = cuentaA, cuentaB
    bridgeFixture.seconds(1)
    individualDevice.connectTestDevice(db, userA)
    devB = individualDevice.connectTestDevice(db, userB)
    hub.reset()
    bridgeFixture.seconds(1)
    with pytest.raises(AuthError):
        startFor(db, userA, profileA, devB)
    assert hub.session is None


def test_la_simulacion_no_se_puede_activar_en_produccion():
    from pydantic import ValidationError

    from app.core.config import Settings
    with pytest.raises(ValidationError) as raised:
        Settings(_env_file=None, API_ENV="production", DEMO_SHARED_PHYSICAL_DEVICE=True)
    assert "DEMO_SHARED_PHYSICAL_DEVICE" in str(raised.value)


def test_el_bloqueo_de_la_cuenta_se_compila_como_updlock_en_sql_server():
    from sqlalchemy.dialects import mssql

    from app.models.user import User
    sql = str(individualDevice.lockAccountQuery(uuid.uuid4()).compile(dialect=mssql.dialect()))
    assert "WITH (UPDLOCK, ROWLOCK)" in sql


def test_dos_solicitudes_simultaneas_de_una_cuenta_no_duplican(db, engine, cuentaA, bridgeFixture):
    """Dos «Conectar dispositivo» a la vez para la misma cuenta: un solo registro lógico y un solo vínculo."""
    user, _ = cuentaA
    userId = user.idUsuario
    bridgeFixture.seconds(1)
    barrier = threading.Barrier(2)
    results, errors = [], []

    def connect():
        session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
        try:
            account = session.get(User, userId)
            barrier.wait()
            results.append(individualDevice.connectTestDevice(session, account).idDispositivo)
        except Exception as error:  # noqa: BLE001 - se verifica abajo
            errors.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=connect) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert not errors, errors
    assert len(set(results)) == 1
    links = db.scalars(select(AccountDeviceLink).where(AccountDeviceLink.idUsuario == userId)).all()
    assert len(links) == 1
    assert len(_logicalDevices(db)) == 1


# --- Revisión de seguridad de «Conectar dispositivo» y de la simulación -----------------------------------------------------


def test_la_confirmacion_no_sirve_si_cambia_el_arduino_conectado(db, cuentaA, bridgeFixture):
    """Lo confirmado con «Conectar» vale solo para el Arduino que estaba conectado: si la conexión informa otro código, se rechaza."""
    user, profileId = cuentaA
    bridgeFixture.seconds(1)
    own = individualDevice.connectTestDevice(db, user)
    bridgeFixture.code = "OTRO-ARDUINO"  # otro Arduino en la misma conexión
    bridgeFixture.seconds(1)
    with pytest.raises(AuthError) as raised:
        startFor(db, user, profileId, own)
    assert raised.value.code == "DISPOSITIVO_NO_COINCIDE" and hub.session is None


def test_un_dispositivo_vinculado_no_operativo_no_inicia_medicion(db, cuentaA, bridgeFixture):
    user, profileId = cuentaA
    bridgeFixture.seconds(1)
    own = individualDevice.connectTestDevice(db, user)
    own.estado = "FUERA_DE_SERVICIO"
    db.commit()
    with pytest.raises(AuthError) as raised:
        startFor(db, user, profileId, own)
    assert raised.value.code == "DISPOSITIVO_NO_DISPONIBLE" and hub.session is None


def test_el_cliente_no_puede_inyectar_la_simulacion_en_el_inicio_de_medicion():
    from pydantic import ValidationError

    from app.schemas.acquisition import TelemetrySessionStart
    with pytest.raises(ValidationError):
        TelemetrySessionStart(idPerfilMedicion=uuid.uuid4(), idDispositivo=uuid.uuid4(), DEMO_SHARED_PHYSICAL_DEVICE=True)
    with pytest.raises(ValidationError):
        TelemetrySessionStart(idPerfilMedicion=uuid.uuid4(), idDispositivo=uuid.uuid4(), simulacionCompartida=True)


def test_con_simulacion_la_medicion_queda_con_su_cuenta_y_su_dispositivo_logico(db, cuentaA, cuentaB, bridgeFixture, demoOn):
    from app.models.measurement import Measurement
    (userA, profileA), (userB, profileB) = cuentaA, cuentaB
    bridgeFixture.seconds(1)
    devA = individualDevice.connectTestDevice(db, userA)
    devB = individualDevice.connectTestDevice(db, userB)
    hub.reset()
    bridgeFixture.seconds(1)
    startedA = startFor(db, userA, profileA, devA)
    hub.reset()
    bridgeFixture.seconds(1)
    startedB = startFor(db, userB, profileB, devB)
    rowA = db.get(Measurement, startedA.idMedicion)
    rowB = db.get(Measurement, startedB.idMedicion)
    assert (rowA.idPerfilMedicion, rowA.idDispositivo) == (profileA, devA.idDispositivo)
    assert (rowB.idPerfilMedicion, rowB.idDispositivo) == (profileB, devB.idDispositivo)
