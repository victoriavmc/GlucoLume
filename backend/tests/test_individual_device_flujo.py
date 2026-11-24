# Flujo de conexión de cuentas individuales (CP-04, CP-05, CP-08, CP-14, CP-15, CP-16, CP-17). Ejecutar desde backend/:
#     python -m pytest tests/test_individual_device_flujo.py -v
# Las cuentas demo NO tienen reglas especiales: su única diferencia son los datos generados (dispositivo y vínculo ya existentes).

import pytest
from sqlalchemy import func, select

from app.acquisition.telemetry import hub
from app.core.exceptions import AuthError
from app.demo import seeder
from app.models.accountDeviceLink import AccountDeviceLink
from app.models.device import Device
from app.models.measurement import Measurement
from app.services import individualDevice
from app.services import telemetry as telemetryService
from tests.test_account_deletion import db, engine, mails, makeUser  # noqa: F401 - fixtures
from tests.test_demo_seed import actor, seeded  # noqa: F401 - fixtures y helpers del generador demo
from tests.test_individual_device_reuse import _logicalDevices, cuentaA  # noqa: F401 - fixture
from tests.test_telemetry import FakeBridge, clock, freshHub, startFor  # noqa: F401 - fixtures
from tests.test_telemetry import bridge as bridgeFixture  # noqa: F401 - fixture


def _linkOf(db, user):
    return db.scalar(select(AccountDeviceLink).where(AccountDeviceLink.idUsuario == user.idUsuario))


def _deviceCount(db) -> int:
    return db.scalar(select(func.count()).select_from(Device)) or 0


def _demoIndividuals():
    return [a for a in seeder.ACCOUNTS if a.individual]


def _failingAudit(*args, **kwargs):
    raise RuntimeError("fallo simulado de auditoría")


# --- CP-04 / CP-05: cuenta demo reutiliza el dispositivo generado (también tras reconectar) ---------------------------------

def test_cp04_el_generador_demo_vincula_un_dispositivo_operativo_a_cada_cuenta_individual(db, seeded):  # noqa: F811
    for a in _demoIndividuals():
        link = _linkOf(db, actor(db, a.key))
        device = db.get(Device, link.idDispositivo)
        assert device is not None and device.estado == "OPERATIVO", a.key


def test_cp04_conectar_una_cuenta_demo_reutiliza_el_dispositivo_generado(db, seeded, bridgeFixture):  # noqa: F811
    user = actor(db, _demoIndividuals()[0].key)
    before = _deviceCount(db)
    expected = _linkOf(db, user).idDispositivo
    bridgeFixture.seconds(1)
    device = individualDevice.connectTestDevice(db, user)
    assert device.idDispositivo == expected
    assert _deviceCount(db) == before and _linkOf(db, user).idDispositivo == expected


def test_cp05_reconectar_despues_de_cerrar_sesion_conserva_el_identificador(db, seeded, bridgeFixture):  # noqa: F811
    user = actor(db, _demoIndividuals()[0].key)
    expected = _linkOf(db, user).idDispositivo
    for _ in range(2):  # cierre de sesión: la conexión se libera y se vuelve a establecer
        hub.reset()
        bridgeFixture.seconds(1)
        assert individualDevice.connectTestDevice(db, user).idDispositivo == expected


# --- CP-08: el administrador deja fuera de servicio el dispositivo demo ------------------------------------------------------

def test_cp08_dispositivo_demo_fuera_de_servicio_se_sustituye_y_luego_se_reutiliza(db, seeded, bridgeFixture):  # noqa: F811
    user = actor(db, _demoIndividuals()[0].key)
    old = db.get(Device, _linkOf(db, user).idDispositivo)
    old.estado = "FUERA_DE_SERVICIO"
    db.commit()
    bridgeFixture.seconds(1)
    replacement = individualDevice.connectTestDevice(db, user)
    assert replacement.idDispositivo != old.idDispositivo and replacement.estado == "OPERATIVO"
    assert _linkOf(db, user).idDispositivo == replacement.idDispositivo
    assert db.get(Device, old.idDispositivo).estado == "FUERA_DE_SERVICIO"  # el anterior queda intacto
    hub.reset()
    bridgeFixture.seconds(1)
    assert individualDevice.connectTestDevice(db, user).idDispositivo == replacement.idDispositivo


# --- CP-14: mismo dispositivo lógico al cambiar USB ↔ Bluetooth, puerto o nombre de conexión ---------------------------------

def test_cp14_cambiar_de_usb_a_bluetooth_y_de_puerto_reutiliza_el_mismo_dispositivo(db, cuentaA, clock):  # noqa: F811
    user, _ = cuentaA
    usb = FakeBridge(db, clock, port="COM3", medium="USB", baud=115200)
    usb.seconds(1)
    first = individualDevice.connectTestDevice(db, user)
    hub.reset()
    bt = FakeBridge(db, clock, port="COM9", medium="BLUETOOTH", baud=9600)  # otro puerto y otro medio
    bt.seconds(1)
    assert individualDevice.connectTestDevice(db, user).idDispositivo == first.idDispositivo
    assert len(_logicalDevices(db)) == 1


# --- CP-15: fallo durante el registro o la vinculación no deja registros parciales -------------------------------------

def test_cp15_fallo_al_registrar_no_deja_dispositivo_ni_vinculo(db, cuentaA, bridgeFixture, monkeypatch):  # noqa: F811
    user, _ = cuentaA
    bridgeFixture.seconds(1)
    monkeypatch.setattr(individualDevice, "registerEvent", _failingAudit)
    with pytest.raises(RuntimeError):
        individualDevice.connectTestDevice(db, user)
    db.rollback()
    assert _logicalDevices(db) == [] and _linkOf(db, user) is None


def test_cp15_fallo_al_reemplazar_deja_el_vinculo_anterior_intacto(db, cuentaA, bridgeFixture, monkeypatch):  # noqa: F811
    user, _ = cuentaA
    bridgeFixture.seconds(1)
    old = individualDevice.connectTestDevice(db, user)
    old.estado = "EN_MANTENIMIENTO"
    db.commit()
    hub.reset()
    bridgeFixture.seconds(1)
    monkeypatch.setattr(individualDevice, "registerEvent", _failingAudit)
    with pytest.raises(RuntimeError):
        individualDevice.connectTestDevice(db, user)
    db.rollback()
    assert _linkOf(db, user).idDispositivo == old.idDispositivo
    assert len(_logicalDevices(db)) == 1  # no quedó el dispositivo sustituto


# --- CP-16: cambio administrativo durante una sesión activa ------------------------------------------------------------------

def test_cp16_si_el_dispositivo_deja_de_estar_operativo_en_plena_medicion_no_se_guarda(db, cuentaA, bridgeFixture):  # noqa: F811
    user, profileId = cuentaA
    bridgeFixture.seconds(1)
    device = individualDevice.connectTestDevice(db, user)
    started = startFor(db, user, profileId, device)
    device.estado = "FUERA_DE_SERVICIO"
    db.commit()
    with pytest.raises(AuthError) as raised:
        telemetryService.saveSession(db, user)
    assert raised.value.code == "DISPOSITIVO_NO_DISPONIBLE"
    db.rollback()
    assert db.get(Measurement, started.idMedicion).estadoMedicion != "COMPLETADA"  # no queda como medición válida


def test_cp16_tras_el_cambio_la_siguiente_conexion_sustituye_el_dispositivo(db, cuentaA, bridgeFixture):  # noqa: F811
    user, _ = cuentaA
    bridgeFixture.seconds(1)
    device = individualDevice.connectTestDevice(db, user)
    device.estado = "FUERA_DE_SERVICIO"
    db.commit()
    hub.reset()
    bridgeFixture.seconds(1)
    replacement = individualDevice.connectTestDevice(db, user)
    assert replacement.idDispositivo != device.idDispositivo
    assert _linkOf(db, user).idDispositivo == replacement.idDispositivo


# --- CP-17: integridad del generador demo (no una condición en producción) ---------------------------------------------------

def test_cp17_el_generador_demo_no_deja_cuentas_individuales_sin_dispositivo(db, seeded):  # noqa: F811
    linked = {row.idUsuario for row in db.scalars(select(AccountDeviceLink)).all()}
    missing = [a.key for a in _demoIndividuals() if actor(db, a.key).idUsuario not in linked]
    assert missing == [], f"cuentas demo sin dispositivo vinculado: {missing}"


def test_cp16_la_comprobacion_avisa_que_el_dispositivo_ya_no_esta_operativo_y_no_registra_otro(db, cuentaA, bridgeFixture):  # noqa: F811
    from app.services import telemetry as telemetry_service

    user, profileId = cuentaA
    bridgeFixture.seconds(1)
    device = individualDevice.connectTestDevice(db, user)
    device.estado = "FUERA_DE_SERVICIO"
    db.commit()
    before = _deviceCount(db)
    readiness = telemetry_service.readiness(db, user, profileId)
    step = next(item for item in readiness["pasos"] if item["id"] == "REGISTRADO")
    assert step["estado"] == "ERROR" and "ya no está operativo" in step["detalle"]
    assert readiness["listo"] is False
    assert _deviceCount(db) == before  # la comprobación no registra un dispositivo nuevo


def test_confirmacion_hecha_antes_de_identificar_el_arduino_se_completa_al_medir(db, cuentaA, bridgeFixture):  # noqa: F811
    user, profileId = cuentaA
    bridgeFixture.seconds(1)
    device = individualDevice.connectTestDevice(db, user)
    hub.confirmation = {"userId": user.idUsuario, "idDispositivo": device.idDispositivo, "code": ""}  # confirmado sin identidad
    started = startFor(db, user, profileId, device)
    assert started is not None and hub.confirmation["code"] != ""
