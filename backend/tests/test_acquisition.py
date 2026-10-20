# Adquisición con el Arduino: protocolo, enlace serie, permisos, persistencia y procesamiento en el servidor.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_acquisition.py -v
#
# NO hay hardware en las pruebas: FakeArduino es un puerto serie falso que habla el protocolo de
# acquisition/PROTOCOLO_SERIE.md y entrega una señal PPG sintética (tests/ppg.py). Prueba el puente (hilo lector, lotes,
# SQL Server/SQLite, cálculo en el servidor, errores), no el firmware ni el sensor reales.

import threading
import time
import uuid
from collections import deque

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.acquisition import link as linkModule
from app.acquisition import protocol
from app.acquisition.link import link
from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.sensorSample import SensorSample
from app.schemas.acquisition import ConnectRequest
from app.services import acquisition as acquisitionService
from app.services import measurement as measurements
from tests.ppg import ppgSamples
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_institution_patients import patientData
from tests.test_institutions import freshLookupLimiter, institutional, team  # noqa: F401
from tests.test_measurements import consumer, device, oximetry as startOximetry  # noqa: F401 - fixtures
from app.services import institutionPatients as patients


class FakeArduino:
    """Puerto serie falso (solo pruebas) con el comportamiento del protocolo."""

    def __init__(self, code="ARD-001", sensor="MAX30102", hr=72, spo2=97.0, seconds=20, garbage=0, cutAfter=None,
                 sensorLostAt=None, silent=False, finger=True):
        self.code, self.sensor, self.silent = code, sensor, silent
        dc = (120000, 100000) if sensor == "MAX30102" else (30000, 25000)
        self.samples = ppgSamples(hr, spo2, seconds, dcIr=dc[0], dcRed=dc[1], seed=int(hr), finger=finger)
        self.garbage, self.cutAfter, self.sensorLostAt = garbage, cutAfter, sensorLostAt
        self.lines, self.written, self.closed, self.fail = deque(), [], False, None

    def write(self, data: bytes):
        if self.closed:
            raise OSError("port closed")
        command = data.decode().strip()
        self.written.append(command)
        if self.silent:
            return
        if command == "ID?":
            self.lines.append(f"GLUCOLUME,ID={self.code},SENSOR={self.sensor},FW=1.0.0,SR=20")
        elif command == "PING":
            self.lines.append("PONG")
        elif command == "START":
            self.lines.append("ST,ADQUIRIENDO")
            for index, (n, t, red, ir) in enumerate(self.samples):
                if self.cutAfter is not None and index == self.cutAfter:
                    self.fail = OSError("device removed")
                    return
                if self.sensorLostAt is not None and index == self.sensorLostAt:
                    self.lines.append("ST,ERROR_SENSOR")
                    return
                self.lines.append(f"S,{n},{t},{red},{ir}")
            for _ in range(self.garbage):
                self.lines.append("@@##garbage##@@")
            self.lines.append("ST,FINALIZADA")
        elif command == "STOP":
            self.lines = deque(line for line in self.lines if not line.startswith("S,"))
            self.lines.append("ST,FINALIZADA")

    def readline(self) -> bytes:
        if self.closed:
            raise OSError("port closed")
        try:
            return (self.lines.popleft() + "\n").encode()
        except IndexError:
            if self.fail is not None:
                raise self.fail
            time.sleep(0.003)
            return b""

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def cleanLink(engine, monkeypatch):
    monkeypatch.setattr(acquisitionService, "sessionFactory",
                        lambda: sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))
    monkeypatch.setattr(linkModule, "RESPONSE_TIMEOUT", 0.6)
    yield
    link.disconnect()
    link.session = None
    link.onLost = acquisitionService._onLost


def connectUser(db, user, fake, medio="USB", port="COM9"):
    return acquisitionService.connect(db, user, ConnectRequest(puerto=port, medio=medio), opener=lambda p, b: fake)


def started(db, user, profileId, code="ARD-001"):
    return startOximetry(db, user, profileId, device(db, codigo=code))


def waitUntil(condition, seconds=10.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


# --- Protocolo --------------------------------------------------------------------------------------------------


def test_protocolo_interpreta_cada_mensaje_y_rechaza_el_ruido():
    assert protocol.parse("S,5,250,123456,234567") == protocol.Sample(5, 250, 123456, 234567)
    assert protocol.parse("ST,ADQUIRIENDO") == protocol.Status("ADQUIRIENDO")
    assert protocol.parse("GLUCOLUME,ID=ARD-1,SENSOR=MAX30100,FW=1.0.0,SR=20") == protocol.Identification("ARD-1", "MAX30100", "1.0.0", 20)
    assert protocol.parse("PONG") == protocol.Pong() and protocol.parse("ERR,I2C") == protocol.DeviceError("I2C")
    assert protocol.parse("   ") is None
    for bad in ("S,1,2,3", "S,a,b,c,d", "S,1,2,-3,4", "S,1,2,9999999,4", "ST,OTRO", "GLUCOLUME,ID=x,SENSOR=MAX99999,FW=1", "xyz"):
        with pytest.raises(protocol.ProtocolError):
            protocol.parse(bad)


# --- Puertos y conexión -----------------------------------------------------------------------------------------


def test_lista_puertos_y_distingue_bluetooth(monkeypatch):
    class Port:
        def __init__(self, device, description, hwid, manufacturer=None):
            self.device, self.description, self.hwid, self.manufacturer = device, description, hwid, manufacturer

    monkeypatch.setattr("serial.tools.list_ports.comports", lambda: [
        Port("COM7", "Enlace estándar sobre Bluetooth (COM7)", r"BTHENUM\{00001101}"),
        Port("COM4", "Arduino Uno (COM4)", "USB VID:PID=2341:0043", "Arduino LLC")])
    ports = {p["puerto"]: p for p in link.listPorts()}
    assert ports["COM7"]["esBluetooth"] and not ports["COM7"]["esArduino"]
    assert ports["COM4"]["esArduino"] and not ports["COM4"]["esBluetooth"]


def test_la_busqueda_de_puertos_usa_pyserial_real():
    assert isinstance(link.listPorts(), list)  # en este equipo puede no haber ningún Arduino


@pytest.mark.parametrize(("error", "code"), [(PermissionError("Access is denied"), "PUERTO_OCUPADO"),
                                             (FileNotFoundError("could not open port 'COM9'"), "PUERTO_NO_ENCONTRADO")])
def test_errores_de_conexion_se_informan_y_se_auditan(db, mails, consumer, error, code):
    user, _ = consumer

    def opener(port, baud):
        raise error

    with pytest.raises(AuthError) as raised:
        acquisitionService.connect(db, user, ConnectRequest(puerto="COM9", medio="USB"), opener=opener)
    assert raised.value.code == code and not link.connected()
    assert any(a.resultado == "FALLO" and a.observacion == code for a in audits(db, "CONECTAR_DISPOSITIVO"))


def test_conectar_identificar_probar_y_desconectar(db, mails, consumer):
    user, _ = consumer
    fake = FakeArduino(code="ARD-007", sensor="MAX30100")
    state = connectUser(db, user, fake, medio="BLUETOOTH", port="COM12")
    assert state["conectado"] and state["medio"] == "BLUETOOTH" and state["baudios"] == 9600 and state["puerto"] == "COM12"
    assert acquisitionService.probe(db, user) >= 0
    identified = acquisitionService.identify(db, user)["dispositivo"]
    assert identified == {"codigo": "ARD-007", "sensor": "MAX30100", "firmware": "1.0.0", "frecuenciaMuestreo": 20}
    assert acquisitionService.disconnect(db, user)["conectado"] is False and fake.closed  # puerto liberado
    assert connectUser(db, user, FakeArduino(), medio="USB")["baudios"] == 115200


def test_sin_respuesta_del_dispositivo(db, mails, consumer):
    user, _ = consumer
    connectUser(db, user, FakeArduino(silent=True))
    for call in (acquisitionService.probe, acquisitionService.identify):
        with pytest.raises(AuthError) as raised:
            call(db, user)
        assert raised.value.code == "SIN_RESPUESTA_DISPOSITIVO"


def test_otra_cuenta_no_opera_el_enlace(db, mails, consumer):
    user, _ = consumer
    other = makeUser(db, email="otra@example.com", usuario="otra")
    connectUser(db, user, FakeArduino())
    with pytest.raises(AuthError) as raised:
        connectUser(db, other, FakeArduino(), port="COM10")
    assert raised.value.code == "DISPOSITIVO_EN_USO"
    for call in (acquisitionService.probe, acquisitionService.identify, acquisitionService.disconnect):
        with pytest.raises(AuthError) as denied:
            call(db, other)
        assert denied.value.code == "DISPOSITIVO_EN_USO"
    seen = acquisitionService.status(other)
    assert seen["ocupado"] and seen["puerto"] is None and seen["dispositivo"] is None


def test_un_operador_sin_vinculo_activo_no_puede_conectar(db, mails, team):
    admin = makeUser(db, tipoCuenta="ADMINISTRADOR_PLATAFORMA", email="adm@example.com", usuario="adm")
    with pytest.raises(AuthError) as raised:
        connectUser(db, admin, FakeArduino())
    assert raised.value.code == "PERMISO_INSUFICIENTE"
    connectUser(db, team.operator, FakeArduino())  # un operador activo sí


# --- Medición completa por USB / Bluetooth ---------------------------------------------------------------------


@pytest.mark.parametrize(("medio", "baudios"), [("USB", 115200), ("BLUETOOTH", 9600)])
def test_adquisicion_completa_guarda_muestras_y_calcula_en_el_servidor(db, mails, consumer, medio, baudios):
    user, profileId = consumer
    fake = FakeArduino(code="ARD-001", hr=72, spo2=97.0)
    assert connectUser(db, user, fake, medio=medio)["baudios"] == baudios
    measurement = started(db, user, profileId)
    state = acquisitionService.start(db, user, measurement.idMedicion)
    assert state["adquisicion"]["estado"] == "ADQUIRIENDO" and "START" in fake.written
    assert waitUntil(lambda: link.session is not None and link.session.count == 400 and link.deviceState == "FINALIZADA")
    live = acquisitionService.status(user)["adquisicion"]["indicadores"]
    assert live["provisorio"] and live["spo2"] == pytest.approx(97.0, abs=0.5) and live["frecuenciaCardiaca"] == 72

    done = acquisitionService.finish(db, user)
    assert done.estadoMedicion == "COMPLETADA" and done.cantidadMuestras == 400
    assert float(done.spo2) == pytest.approx(97.0, abs=0.5) and done.frecuenciaCardiaca == 72
    assert done.glucosaEstimada is None and done.versionAlgoritmo == "oximetria-ppg-v1"
    assert db.scalar(select(SensorSample).where(SensorSample.idMedicion == measurement.idMedicion).limit(1)) is not None
    assert link.session is None and link.connected()  # la sesión terminó; el puerto sigue conectado
    assert [a.resultado for a in audits(db, "INICIAR_ADQUISICION")] == ["EXITO"]
    assert audits(db, "FINALIZAR_MEDICION")
    # El resultado se refleja de inmediato en las estadísticas y el historial propios.
    assert measurements.ownStatistics(db, user, 7).cantidadMediciones == 1
    assert measurements.listOwnHistory(db, user).total == 1


def test_el_resultado_siempre_sale_de_la_senal_y_no_del_cliente(db, mails, consumer):
    user, profileId = consumer
    connectUser(db, user, FakeArduino(finger=False))  # sin dedo sobre el sensor
    measurement = started(db, user, profileId)
    acquisitionService.start(db, user, measurement.idMedicion)
    assert waitUntil(lambda: link.session.count == 400)
    done = acquisitionService.finish(db, user)
    assert done.estadoMedicion == "INVALIDA" and done.spo2 is None and "dedo" in done.observacion
    assert measurements.ownStatistics(db, user, 7).cantidadMediciones == 0


def test_cancelar_descarta_y_deja_el_puerto_libre_para_otra_medicion(db, mails, consumer):
    user, profileId = consumer
    connectUser(db, user, FakeArduino())
    measurement = started(db, user, profileId)
    acquisitionService.start(db, user, measurement.idMedicion)
    waitUntil(lambda: link.session.count > 0)
    assert acquisitionService.cancel(db, user).estadoMedicion == "CANCELADA"
    assert link.session is None and link.connected()
    with pytest.raises(AuthError) as raised:
        acquisitionService.finish(db, user)
    assert raised.value.code == "ADQUISICION_NO_ACTIVA"


def test_no_se_desconecta_durante_una_adquisicion(db, mails, consumer):
    user, profileId = consumer
    connectUser(db, user, FakeArduino())
    acquisitionService.start(db, user, started(db, user, profileId).idMedicion)
    with pytest.raises(AuthError) as raised:
        acquisitionService.disconnect(db, user)
    assert raised.value.code == "ADQUISICION_ACTIVA"


# --- Validaciones al iniciar -----------------------------------------------------------------------------------


def test_el_arduino_debe_ser_el_dispositivo_elegido(db, mails, consumer):
    user, profileId = consumer
    connectUser(db, user, FakeArduino(code="OTRO-ARDUINO"))
    with pytest.raises(AuthError) as raised:
        acquisitionService.start(db, user, started(db, user, profileId, code="ARD-001").idMedicion)
    assert raised.value.code == "DISPOSITIVO_NO_COINCIDE"


def test_el_sensor_debe_coincidir_con_el_inventario(db, mails, consumer):
    user, profileId = consumer
    connectUser(db, user, FakeArduino(code="ARD-001", sensor="MAX30100"))
    with pytest.raises(AuthError) as raised:
        acquisitionService.start(db, user, started(db, user, profileId).idMedicion)  # el inventario dice MAX30102
    assert raised.value.code == "DISPOSITIVO_INCONSISTENTE"


def test_un_dispositivo_fuera_de_servicio_no_inicia(db, mails, consumer):
    user, profileId = consumer
    connectUser(db, user, FakeArduino())
    measurement = started(db, user, profileId)
    from app.models.device import Device
    row = db.scalars(select(Device)).first()
    row.estado = "EN_MANTENIMIENTO"
    db.commit()
    with pytest.raises(AuthError) as raised:
        acquisitionService.start(db, user, measurement.idMedicion)
    assert raised.value.code == "DISPOSITIVO_NO_DISPONIBLE"


def test_perfil_no_autorizado_no_puede_iniciar_la_medicion_de_otro(db, mails, consumer):
    user, profileId = consumer
    other = makeUser(db, email="intrusa@example.com", usuario="intrusa")
    measurement = started(db, user, profileId)
    connectUser(db, other, FakeArduino())
    with pytest.raises(AuthError) as raised:
        acquisitionService.start(db, other, measurement.idMedicion)
    assert raised.value.code == "MEDICION_NO_ENCONTRADA"


def test_el_operador_mide_solo_pacientes_a_su_cargo(db, mails, team):
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    other = patients.createPatient(db, team.operator, team.id, patientData(dni="30111222"))
    code = "ARD-INST"
    dev = device(db, institucion=team.id, codigo=code)
    from app.schemas.measurement import MeasurementStart
    measurement = measurements.startMeasurement(db, team.operator, MeasurementStart(
        idPerfilMedicion=patient.idPerfilMedicion, idDispositivo=dev.idDispositivo))
    connectUser(db, team.operator, FakeArduino(code=code))
    acquisitionService.start(db, team.operator, measurement.idMedicion)
    assert waitUntil(lambda: link.session.count == 400)
    done = acquisitionService.finish(db, team.operator)
    assert done.estadoMedicion == "COMPLETADA" and done.idPerfilMedicion == patient.idPerfilMedicion
    assert other.idPerfilMedicion != done.idPerfilMedicion


# --- Fallos del enlace -------------------------------------------------------------------------------------------


def test_sensor_desconectado_se_informa_y_se_conservan_las_muestras(db, mails, consumer):
    user, profileId = consumer
    connectUser(db, user, FakeArduino(sensorLostAt=150))
    measurement = started(db, user, profileId)
    acquisitionService.start(db, user, measurement.idMedicion)
    assert waitUntil(lambda: link.session.state == "ERROR")
    status = acquisitionService.status(user)["adquisicion"]
    assert status["codigoError"] == "SENSOR_DESCONECTADO" and status["muestras"] == 150
    done = acquisitionService.finish(db, user)
    assert done.estadoMedicion == "INVALIDA" and done.cantidadMuestras == 150 and "sensor" in done.observacion.lower()
    assert link.connected()  # el puerto sigue disponible para reintentar


def test_perdida_de_comunicacion_libera_el_puerto_y_audita(db, mails, consumer):
    user, profileId = consumer
    fake = FakeArduino(cutAfter=130)
    connectUser(db, user, fake)
    measurement = started(db, user, profileId)
    acquisitionService.start(db, user, measurement.idMedicion)
    assert waitUntil(lambda: not link.connected())
    assert fake.closed  # puerto liberado
    assert waitUntil(lambda: measurements.getMeasurement(db, user, measurement.idMedicion).estadoMedicion in ("INVALIDA", "CANCELADA"))
    detail = measurements.getMeasurement(db, user, measurement.idMedicion)
    assert detail.cantidadMuestras == 130  # lo recibido se conserva
    failures = [a for a in audits(db, "ERROR_COMUNICACION_DISPOSITIVO")]
    assert failures and failures[0].resultado == "FALLO"
    assert acquisitionService.status(user)["conectado"] is False


def test_datos_ilegibles_cortan_el_enlace(db, mails, consumer):
    user, profileId = consumer
    connectUser(db, user, FakeArduino(garbage=60, seconds=12))
    acquisitionService.start(db, user, started(db, user, profileId).idMedicion)
    assert waitUntil(lambda: not link.connected())
    assert "ilegibles" in (link.lastError or "")


# --- HTTP -----------------------------------------------------------------------------------------------------


def test_rutas_http_estado_conexion_fallida_y_acceso(db, mails, consumer, api):
    user, _ = consumer
    assert api(user).get("/api/v1/acquisition/status").json()["conectado"] is False
    assert api(user).get("/api/v1/acquisition/ports").status_code == 200
    missing = api(user).post("/api/v1/acquisition/connect", json={"puerto": "COM98", "medio": "USB"})
    assert missing.status_code in (404, 409) and missing.json()["codigo"] in ("PUERTO_NO_ENCONTRADO", "PUERTO_OCUPADO")
    assert api(user).post("/api/v1/acquisition/probe").status_code == 409  # sin dispositivo conectado
    assert api(user).post("/api/v1/acquisition/start", json={"idMedicion": str(uuid.uuid4())}).status_code == 409
    assert api(user).post("/api/v1/acquisition/connect", json={"puerto": "COM98", "medio": "WIFI"}).status_code == 422
    # Cuentas que no miden (administrador): sin acceso.
    admin = makeUser(db, tipoCuenta="ADMINISTRADOR_PLATAFORMA", email="adm2@example.com", usuario="adm2")
    assert api(admin).get("/api/v1/acquisition/ports").status_code == 403
