# Telemetría procesada del firmware GlucoLume_MAX30100: protocolo, estado del dispositivo, sesión de medición, guardado
# en la base, datos DEMO y aislamiento entre cuentas.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_telemetry.py -v
#
# NO hay Arduino ni puerto serie en estas pruebas. `FakeBridge` hace lo que hace el puente real
# (acquisition/bridge/glucolume_bridge.py): envía a ingest() las líneas con el MISMO formato que escribe el firmware.
# Es un mecanismo de prueba separado de la conexión real: el servidor no tiene ningún modo «simulado». El reloj del
# estado en vivo (hub.clock) es falso para probar plazos sin esperar. La base es la SQLite temporal del resto de las
# pruebas (esquema generado desde los modelos): ver docs/DOCKER.md para la validación de la migración en SQL Server.

import threading
import time
import uuid
from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.acquisition import telemetry
from app.acquisition.telemetry import Notice, Reading, TelemetryError, hub, parseLine
from app.core.config import Settings, getSettings
from app.core.exceptions import AuthError
from app.models.measurement import Measurement
from app.schemas.acquisition import BridgeIngest, BridgeLine, ConnectRequest, DeviceConnectConfirm, TelemetrySessionStart
from app.schemas.resultDelivery import ResultSendRequest
from app.services import acquisition as acquisitionService
from app.utils.timeZone import nowArgentina
from app.services import deviceConnection
from app.services import institutionPatients as patients
from app.services import measurement as measurements
from app.services import telemetry as telemetryService
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_institution_patients import patientData
from tests.test_institutions import freshLookupLimiter, institutional, team  # noqa: F401
from tests.test_measurements import consumer, device  # noqa: F401 - fixtures

TOKEN = "t" * 40
CODE = "ARD-001"
# Línea EXACTA del ejemplo del firmware.
FIRMWARE_LINE = "BPM:76.43,SpO2:99.65,GluExp_mgdl:117.0,Origen:DEMO,IndiceOptico:2.41492,SenalValida:1,Dedo:1,Muestras:58"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture(autouse=True)
def freshHub(engine, monkeypatch):
    clock = Clock()
    hub.reset()
    hub.clock = clock
    monkeypatch.setenv("BRIDGE_TOKEN", TOKEN)
    getSettings.cache_clear()
    yield clock
    hub.reset()
    hub.clock = time.monotonic


@pytest.fixture
def clock(freshHub) -> Clock:
    return freshHub


def line(bpm="72.00", spo2="98.00", glu="117.0", origen="DEMO", index="2.41492", valid=1, finger=1, samples=50) -> str:
    """Una línea con el formato exacto que imprime el firmware (print(float) usa 2 decimales)."""
    return (f"BPM:{bpm},SpO2:{spo2},GluExp_mgdl:{glu},Origen:{origen},IndiceOptico:{index},"
            f"SenalValida:{valid},Dedo:{finger},Muestras:{samples}")


class FakeBridge:
    """Hace lo que el puente real: latidos y líneas hacia ingest(). Solo pruebas."""

    def __init__(self, db, clock, code=CODE, port="COM4", medium="BLUETOOTH", baud=9600) -> None:
        self.db, self.clock, self.code, self.port, self.medium, self.baud = db, clock, code, port, medium, baud
        self.id, self.seq = uuid.uuid4(), 0

    def send(self, lines=(), state="CONECTADO", attempt=0, error=None, ageMs=0, seqs=None):
        entries = []
        for index, text in enumerate(lines):
            if seqs is not None:
                number = seqs[index]
            else:
                number, self.seq = self.seq, self.seq + 1
            entries.append(BridgeLine(seq=number, edadMs=ageMs, texto=text))
        return telemetryService.ingest(self.db, BridgeIngest(
            idPuente=self.id, codigoDispositivo=self.code, puerto=self.port, medio=self.medium, baudios=self.baud,
            estadoEnlace=state, intento=attempt, error=error, lineas=entries))

    def seconds(self, count, **fields):
        """`count` segundos de telemetría (una línea por segundo)."""
        for _ in range(count):
            self.send([line(**fields)])
            self.clock.advance(1)


@pytest.fixture
def bridge(db, clock) -> FakeBridge:
    return FakeBridge(db, clock)


def startFor(db, user, profileId, dev, **extra):
    return telemetryService.startSession(db, user, TelemetrySessionStart(
        idPerfilMedicion=profileId, idDispositivo=dev.idDispositivo, **extra))


def measuring(db, consumer, bridge, readings=1):
    """Cuenta individual con el dispositivo conectado y una sesión abierta."""
    user, profileId = consumer
    dev = device(db, codigo=CODE)
    bridge.seconds(readings)
    return user, profileId, dev, startFor(db, user, profileId, dev)


# --- Protocolo ----------------------------------------------------------------------------------------------------


def test_interpreta_la_linea_del_firmware():
    reading = parseLine(FIRMWARE_LINE)
    assert isinstance(reading, Reading)
    assert (reading.bpm, reading.spo2, reading.glucosa, reading.origen) == (76.43, 99.65, 117.0, "DEMO")
    assert (reading.indiceOptico, reading.senalValida, reading.dedo, reading.muestras) == (2.41492, True, True, 58)
    assert reading.usable and reading.asDict()["esDemo"] is True and reading.asDict()["unidadGlucosa"] == "mg/dL"


def test_na_es_ausencia_de_valor_nunca_cero():
    reading = parseLine(line(glu="NA", origen="SIN_CALIBRAR", index="NA", valid=0))
    assert reading.glucosa is None and reading.indiceOptico is None and reading.origen == "SIN_CALIBRAR"
    assert reading.asDict()["unidadGlucosa"] is None
    assert not reading.usable
    # El firmware escribe 0.00 en BPM / SpO2 cuando no tiene valor (sin dedo o sin latidos): tampoco es una medición.
    empty = parseLine(line(bpm="0.00", spo2="0.00", glu="NA", origen="SIN_CALIBRAR", index="NA", valid=0, finger=0, samples=0))
    assert empty.bpm is None and empty.spo2 is None and empty.dedo is False
    # Un cero legítimo en otro campo (glucosa) se conserva.
    assert parseLine(line(glu="0.0")).glucosa == 0.0


@pytest.mark.parametrize("bad", [
    "BPM:76.43,SpO2:99.65,GluExp_mgdl:117.0,Origen:DEMO,IndiceOptico:2.4",  # truncada: faltan campos
    "BPM:76.4?,SpO2:99.65,GluExp_mgdl:117.0,Origen:DEMO,IndiceOptico:2.4,SenalValida:1,Dedo:1,Muestras:5",  # ruido
    line(origen="OTRO"), line(valid=2), line(finger="x"), line(samples="-3"), line(samples=70000),
    line(bpm="nan"), line(spo2="inf"), line(bpm="1e3"), line(bpm="999"), line(spo2="101"),
    line() + ",BPM:80.00",  # campo repetido
    "BPM:76.43;SpO2:99.65", "@@##garbage##@@", "76.43,99.65",
])
def test_lineas_corruptas_se_rechazan(bad):
    with pytest.raises(TelemetryError):
        parseLine(bad)


def test_textos_informativos_del_firmware_no_son_lecturas_ni_ruido():
    for text in ("Sistema listo.", "Comandos: DEMO,ON | DEMO,OFF | CAL,<mg/dL> | CALCLR", "MODO:DEMO_ACTIVO",
                 "AVISO: GLUCOSA DEMO SINTETICA. NO ES MEDICION.", "CAL:OK,puntos=3,ajuste=SI"):
        assert parseLine(text) == Notice(text)
    error = parseLine("ERROR: MAX30100 no detectado por I2C (0x57). Revisar cableado/alimentacion.")
    assert isinstance(error, Notice) and error.error
    assert parseLine("   ") is None


def test_campos_desconocidos_sin_los_obligatorios_no_alcanzan():
    assert isinstance(parseLine(line() + ",Extra:1"), Reading)  # un campo nuevo del firmware no rompe la lectura
    with pytest.raises(TelemetryError):
        parseLine("BPM:76.43,Extra:1")


# --- Estado del dispositivo y del Bluetooth ---------------------------------------------------------------------------


def test_estado_sin_puente_conectado_sin_datos_y_pérdida_del_puente(db, bridge, clock, consumer):
    user, _ = consumer
    assert hub.deviceState() == "SIN_PUENTE"
    assert telemetryService.status(db, user)["estado"] == "SIN_PUENTE"
    bridge.seconds(1)
    snapshot = telemetryService.status(db, user)
    assert snapshot["estado"] == "CONECTADO" and snapshot["puente"]["medio"] == "BLUETOOTH"
    # Sin el control del dispositivo no se reciben valores, solo la antigüedad de la última lectura (DEC-01).
    assert snapshot["lectura"] is None and snapshot["edadUltimaLectura"] is not None and snapshot["controlPropio"] is False
    snapshot = telemetryService.takeControl(db, user)
    assert snapshot["controlPropio"] is True
    assert snapshot["puente"]["puerto"] == "COM4" and snapshot["lectura"]["bpm"] == 72.0
    assert snapshot["lectura"]["esDemo"] is True and snapshot["lectura"]["glucosa"] == 117.0
    clock.advance(6)  # el puente sigue vivo pero el Arduino no envía
    bridge.send([])
    assert hub.deviceState() == "SIN_DATOS" and telemetryService.status(db, user)["lectura"] is None
    clock.advance(11)  # el puente dejó de enviar latidos
    assert hub.deviceState() == "SIN_PUENTE"


def test_perdida_de_bluetooth_y_reconexion(db, bridge, clock, consumer):
    user, _ = consumer
    bridge.seconds(2)
    bridge.send([], state="DESCONECTADO", error="could not open port 'COM4'")
    assert hub.deviceState() == "PUERTO_DESCONECTADO"
    assert telemetryService.status(db, user)["lectura"] is None  # no se muestra una lectura vieja como si fuera actual
    for attempt in (1, 2, 3):
        clock.advance(2)
        bridge.send([], state="REINTENTANDO", attempt=attempt, error="reintentando")
    assert telemetryService.status(db, user)["puente"]["reintento"] == 3 and hub.deviceState() == "PUERTO_DESCONECTADO"
    bridge.send([], state="CONECTADO")
    assert hub.deviceState() == "SIN_DATOS"  # enlace abierto, todavía sin lecturas
    bridge.seconds(1)
    assert hub.deviceState() == "CONECTADO"


def test_lineas_corruptas_se_cuentan_y_no_cortan_el_flujo(bridge):
    result = bridge.send(["@@garbage@@", line(), "BPM:1,2", "Sistema listo."])
    assert (result.aceptadas, result.invalidas) == (1, 2) and hub.invalidLines == 2
    assert hub.notice.text == "Sistema listo." and hub.deviceState() == "CONECTADO"


def test_las_lecturas_reenviadas_no_se_duplican(bridge):
    first = bridge.send([line(), line(bpm="73.00")], seqs=[10, 11])
    again = bridge.send([line(), line(bpm="73.00"), line(bpm="74.00")], seqs=[10, 11, 12])  # reintento del lote
    assert (first.aceptadas, again.aceptadas, again.duplicadas) == (2, 1, 2)
    assert hub.readingsReceived == 3 and hub.latest.bpm == 74.0


def test_un_lote_viejo_no_parece_actual(bridge, clock):
    """Tras una caída del servidor, el puente reenvía líneas viejas: su edad se respeta."""
    bridge.send([line()], ageMs=20_000)
    assert hub.deviceState() == "SIN_DATOS"


def test_un_segundo_puente_activo_se_rechaza(db, bridge, clock):
    bridge.seconds(1)
    other = FakeBridge(db, clock, port="COM9")
    with pytest.raises(AuthError) as raised:
        other.send([line()])
    assert raised.value.code == "PUENTE_DUPLICADO"
    assert hub.bridge.bridgeId == str(bridge.id)
    clock.advance(11)  # el primero murió: el nuevo toma el relevo
    other.send([line()])
    assert hub.bridge.bridgeId == str(other.id)


def test_un_puente_que_se_cierra_a_proposito_libera_su_lugar(db, bridge, clock):
    bridge.seconds(2)
    telemetryService.ingest(db, BridgeIngest(idPuente=bridge.id, codigoDispositivo=CODE, medio="BLUETOOTH",
                                             estadoEnlace="DESCONECTADO", detenido=True))
    assert hub.deviceState() == "SIN_PUENTE"
    other = FakeBridge(db, clock, port="COM9")  # el reinicio del puente no espera a que venza el latido
    other.send([line()])
    assert hub.bridge.bridgeId == str(other.id) and hub.deviceState() == "CONECTADO"


def test_el_puerto_del_puente_no_se_abre_desde_el_enlace_anterior(db, bridge, consumer):
    user, _ = consumer
    bridge.seconds(1)
    with pytest.raises(AuthError) as raised:
        acquisitionService.connect(db, user, ConnectRequest(puerto="com4", medio="BLUETOOTH"), opener=lambda p, b: None)
    assert raised.value.code == "PUERTO_EN_USO_PUENTE"


def test_validacion_del_pedido_del_puente():
    base = dict(idPuente=uuid.uuid4(), codigoDispositivo=CODE, medio="BLUETOOTH", estadoEnlace="CONECTADO")
    with pytest.raises(ValidationError):
        BridgeIngest(**base, lineas=[BridgeLine(seq=i, edadMs=0, texto="x") for i in range(201)])
    with pytest.raises(ValidationError):
        BridgeIngest(**base, lineas=[BridgeLine(seq=1, edadMs=0, texto="x" * 513)])
    with pytest.raises(ValidationError):
        BridgeIngest(**{**base, "estadoEnlace": "OTRO"})


# --- HTTP ---------------------------------------------------------------------------------------------------------------


def payload(bridge, lines=()):
    return {"idPuente": str(bridge.id), "codigoDispositivo": CODE, "puerto": "COM4", "medio": "BLUETOOTH", "baudios": 9600,
            "estadoEnlace": "CONECTADO", "lineas": [{"seq": i, "edadMs": 0, "texto": t} for i, t in enumerate(lines)]}


def test_el_puente_se_autentica_con_token(api, consumer, bridge, monkeypatch):
    user, _ = consumer
    client = api(user)
    body = payload(bridge, [line()])
    assert client.post("/api/v1/acquisition/bridge/ingest", json=body).status_code == 403
    assert client.post("/api/v1/acquisition/bridge/ingest", json=body, headers={"X-Bridge-Token": "x" * 40}).status_code == 403
    ok = client.post("/api/v1/acquisition/bridge/ingest", json=body, headers={"X-Bridge-Token": TOKEN})
    assert ok.status_code == 200 and ok.json() == {"aceptadas": 1, "duplicadas": 0, "invalidas": 0, "estado": "CONECTADO", "comando": None}
    # El token de un usuario (JWT) no sirve para el puente y viceversa: el puente no tiene sesión de usuario.
    monkeypatch.delenv("BRIDGE_TOKEN")
    getSettings.cache_clear()
    # Sin token en el entorno el valor podría venir del .env real del equipo: se fuerza «no configurado» en la configuración cargada.
    monkeypatch.setattr(getSettings(), "BRIDGE_TOKEN", None)
    disabled = client.post("/api/v1/acquisition/bridge/ingest", json=body, headers={"X-Bridge-Token": TOKEN})
    assert disabled.status_code == 503 and disabled.json()["codigo"] == "PUENTE_NO_CONFIGURADO"


def test_el_puente_bloquea_la_ip_que_falla_el_token_y_acepta_el_anterior_al_rotar(api, consumer, bridge, monkeypatch):
    # GL-11: rotación sin corte (BRIDGE_PREVIOUS_TOKEN) y bloqueo por IP tras fallar el token, aunque después acierte.
    from app.api import rateLimit

    user, _ = consumer
    client = api(user)
    url, body = "/api/v1/acquisition/bridge/ingest", payload(bridge, [line()])
    previous = "p" * 40
    monkeypatch.setenv("BRIDGE_PREVIOUS_TOKEN", previous)
    monkeypatch.setenv("BRIDGE_PREVIOUS_TOKEN_UNTIL", (nowArgentina() + timedelta(hours=2)).replace(tzinfo=None).isoformat(timespec="seconds"))
    getSettings.cache_clear()
    assert client.post(url, json=body, headers={"X-Bridge-Token": previous}).status_code == 200
    for _ in range(rateLimit.BRIDGE_FAILURES[0]):
        assert client.post(url, json=body, headers={"X-Bridge-Token": "x" * 40}).status_code == 403
    blocked = client.post(url, json=body, headers={"X-Bridge-Token": TOKEN})
    assert blocked.status_code == 429 and blocked.json()["codigo"] == "DEMASIADAS_SOLICITUDES"
    rateLimit.resetLimits()
    assert client.post(url, json=body, headers={"X-Bridge-Token": TOKEN}).status_code == 200
    monkeypatch.setattr(rateLimit._limiters["bridgeCheck"], "maxEvents", 2)
    check = lambda: client.post("/api/v1/acquisition/bridge/check", json={"codigoDispositivo": CODE}, headers={"X-Bridge-Token": TOKEN})  # noqa: E731
    assert [check().status_code for _ in range(3)] == [200, 200, 429]


def test_el_token_anterior_del_puente_vence_en_su_plazo(api, consumer, bridge, monkeypatch):
    # H-16: BRIDGE_PREVIOUS_TOKEN_UNTIL es obligatorio con el token anterior, está acotado y, vencido, el token anterior deja de valer.
    from app.api import rateLimit

    user, _ = consumer
    client = api(user)
    url, body = "/api/v1/acquisition/bridge/ingest", payload(bridge, [line()])
    previous = "p" * 40
    monkeypatch.setenv("BRIDGE_PREVIOUS_TOKEN", previous)
    for hours, expected in ((2, 200), (-1, 403)):
        monkeypatch.setenv("BRIDGE_PREVIOUS_TOKEN_UNTIL", (nowArgentina() + timedelta(hours=hours)).replace(tzinfo=None).isoformat(timespec="seconds"))
        getSettings.cache_clear()
        rateLimit.resetLimits()
        assert client.post(url, json=body, headers={"X-Bridge-Token": previous}).status_code == expected
        assert client.post(url, json=body, headers={"X-Bridge-Token": TOKEN}).status_code == 200
    monkeypatch.delenv("BRIDGE_PREVIOUS_TOKEN_UNTIL")
    monkeypatch.delenv("BRIDGE_PREVIOUS_TOKEN")
    base = {"_env_file": None, "DB_HOST": "h", "DB_NAME": "n", "DB_USER": "u", "DB_PASSWORD": "p", "JWT_SECRET": "j" * 40, "BRIDGE_TOKEN": TOKEN}
    with pytest.raises(ValidationError, match="BRIDGE_PREVIOUS_TOKEN_UNTIL"):  # sin plazo, el token anterior no se acepta
        Settings(**base, BRIDGE_PREVIOUS_TOKEN=previous)
    with pytest.raises(ValidationError, match="horas"):
        Settings(**base, BRIDGE_PREVIOUS_TOKEN=previous, BRIDGE_PREVIOUS_TOKEN_UNTIL=(nowArgentina() + timedelta(days=30)).replace(tzinfo=None))
    with pytest.raises(ValidationError, match="igual"):
        Settings(**base, BRIDGE_PREVIOUS_TOKEN=TOKEN, BRIDGE_PREVIOUS_TOKEN_UNTIL=(nowArgentina() + timedelta(hours=2)).replace(tzinfo=None))


def test_estado_http_solo_para_cuentas_que_miden(api, db, mails, consumer, bridge):
    user, _ = consumer
    bridge.seconds(1)
    body = api(user).get("/api/v1/acquisition/telemetry/status").json()
    assert body["estado"] == "CONECTADO" and body["lectura"] is None and body["controlPropio"] is False
    body = api(user).post("/api/v1/acquisition/telemetry/control").json()
    assert body["controlPropio"] is True and body["lectura"]["origen"] == "DEMO" and body["sesion"] is None
    admin = makeUser(db, tipoCuenta="ADMINISTRADOR_PLATAFORMA", email="adm@example.com", usuario="adm")
    assert api(admin).get("/api/v1/acquisition/telemetry/status").status_code == 403


# --- Estabilidad (criterio de la lectura que se guarda) ---------------------------------------------------------------


def readings(*items, step=1.0, start=100.0):
    return [Reading(**{**dict(bpm=72.0, spo2=98.0, glucosa=117.0, origen="DEMO", indiceOptico=2.4, senalValida=True,
                              dedo=True, muestras=50), **item}, at=start + index * step) for index, item in enumerate(items)]


def test_criterio_de_estabilidad():
    good = readings(*[{}] * 8)
    stable = telemetry.evaluateStability(good, now=108.0)
    assert isinstance(stable, telemetry.Stable) and stable.lecturas == 8 and stable.bpm == 72 and stable.spo2 == 98.0
    # La mediana ignora una lectura atípica dentro del margen.
    mixed = telemetry.evaluateStability(readings(*[{"bpm": 70.0}] * 3, *[{"bpm": 74.0}] * 3, {"bpm": 71.0}, {"bpm": 72.0}), 108.0)
    assert mixed.bpm == 72
    for items, now, code in [
        ([], 100.0, "SIN_LECTURAS"),
        (good, 120.0, "DATOS_DESACTUALIZADOS"),
        (readings(*[{}] * 7, {"dedo": False}), 108.0, "DEDO_NO_DETECTADO"),
        (readings(*[{}] * 7, {"senalValida": False}), 108.0, "SENAL_NO_VALIDA"),
        (readings(*[{}] * 7, {"indiceOptico": None}), 108.0, "SENAL_NO_VALIDA"),
        (readings(*[{}] * 7, {"muestras": 10}), 108.0, "SENAL_NO_VALIDA"),
        (readings(*[{}] * 7), 107.0, "LECTURAS_INSUFICIENTES"),
        (readings(*[{}] * 4, {"dedo": False}, *[{}] * 3), 108.0, "LECTURAS_INSUFICIENTES"),  # el dedo se retiró en el medio
        (readings(*[{"bpm": 60.0}] * 4, *[{"bpm": 90.0}] * 4), 108.0, "VARIACION_EXCESIVA"),
        (readings(*[{"spo2": 90.0}] * 4, *[{"spo2": 98.0}] * 4), 108.0, "VARIACION_EXCESIVA"),
        (readings(*[{"origen": "DEMO"}] * 4, *[{"origen": "SIN_CALIBRAR", "glucosa": None}] * 4), 108.0, "VARIACION_EXCESIVA"),
    ]:
        verdict = telemetry.evaluateStability(items, now)
        assert isinstance(verdict, telemetry.Unstable) and verdict.code == code, (code, verdict)
    gap = readings(*[{}] * 8)
    gap = gap[:4] + [Reading(**{**r.__dict__, "at": r.at + 10}) for r in gap[4:]]
    assert telemetry.evaluateStability(gap, 118.0).code == "LECTURAS_INSUFICIENTES"  # hueco: se perdieron lecturas


def test_se_puede_guardar_la_ultima_ventana_valida_aunque_se_retire_el_dedo():
    items = readings(*[{}] * 8, *[{"dedo": False, "senalValida": False, "bpm": None, "spo2": None}] * 3)
    stable = telemetry.evaluateStability(items, now=111.0)
    assert isinstance(stable, telemetry.Stable) and stable.lecturas == 8 and stable.bpm == 72  # las 8 válidas, no las vacías
    # Dentro de los 2 minutos (MAX_VALID_WINDOW_SECONDS) todavía se puede guardar; pasado ese plazo, hay que volver a medir.
    # El dispositivo sigue enviando lecturas sin dedo (1 por segundo): la última válida tiene 100 s o 130 s.
    removed = {"dedo": False, "senalValida": False, "bpm": None, "spo2": None}
    recent = telemetry.evaluateStability(readings(*[{}] * 8, *[removed] * 100), now=100.0 + 108 + 1)
    assert isinstance(recent, telemetry.Stable) and recent.lecturas == 8
    old = telemetry.evaluateStability(readings(*[{}] * 8, *[removed] * 130), now=100.0 + 138 + 1)
    assert isinstance(old, telemetry.Unstable)
    # Retirar el dedo y volver a apoyarlo (racha nueva de 5 lecturas) no descarta la ventana completa ya medida.
    again = telemetry.evaluateStability(readings(*[{}] * 8, *[removed] * 3, *[{}] * 5), now=100.0 + 16 + 1)
    assert isinstance(again, telemetry.Stable) and again.lecturas == 8
    # Con el dedo retirado y SIN 8 válidas antes, sigue sin poder guardar.
    assert telemetry.evaluateStability(readings(*[{}] * 5, *[{"dedo": False}] * 3), 108.0).code == "DEDO_NO_DETECTADO"


def test_la_glucosa_demo_cambia_a_proposito_y_no_desestabiliza():
    items = readings(*[{"glucosa": 105.0 + 2 * i} for i in range(8)])
    stable = telemetry.evaluateStability(items, 108.0)
    assert isinstance(stable, telemetry.Stable) and stable.glucosa == 112.0  # mediana de 105…119
    experimental = readings(*[{"origen": "EXPERIMENTAL", "glucosa": 100.0 + 8 * i} for i in range(8)])
    assert telemetry.evaluateStability(experimental, 108.0).code == "VARIACION_EXCESIVA"  # 56 mg/dL de variación


# --- Sesión y guardado -----------------------------------------------------------------------------------------------------


def test_guardar_sin_dispositivo_ni_sesion(db, consumer, bridge):
    user, profileId = consumer
    dev = device(db, codigo=CODE)
    with pytest.raises(AuthError) as raised:  # no hay puente
        startFor(db, user, profileId, dev)
    assert raised.value.code == "DISPOSITIVO_NO_CONECTADO" and "puente" in raised.value.message
    with pytest.raises(AuthError) as noSession:  # guardar sin haber abierto una sesión
        telemetryService.saveSession(db, user)
    assert noSession.value.code == "ADQUISICION_NO_ACTIVA"
    assert db.scalar(select(Measurement).limit(1)) is None  # no se creó ninguna medición
    bridge.send([], state="DESCONECTADO", error="could not open port")
    with pytest.raises(AuthError) as bluetooth:
        startFor(db, user, profileId, dev)
    assert bluetooth.value.code == "DISPOSITIVO_NO_CONECTADO" and "Bluetooth" in bluetooth.value.message


def test_el_dispositivo_debe_ser_el_que_atiende_el_puente(db, consumer, bridge):
    user, profileId = consumer
    other = device(db, codigo="OTRO-ARDUINO")
    bridge.seconds(1)
    with pytest.raises(AuthError) as raised:
        startFor(db, user, profileId, other)
    assert raised.value.code == "DISPOSITIVO_NO_COINCIDE" and hub.session is None


def test_un_dispositivo_fuera_de_servicio_no_inicia(db, consumer, bridge):
    user, profileId = consumer
    dev = device(db, codigo=CODE, estado="EN_MANTENIMIENTO")
    bridge.seconds(1)
    with pytest.raises(AuthError) as raised:
        startFor(db, user, profileId, dev)
    assert raised.value.code == "DISPOSITIVO_NO_DISPONIBLE" and hub.session is None


def test_flujo_completo_demo_se_guarda_y_aparece_en_el_historial_correcto(db, mails, consumer, bridge):
    user, profileId, dev, started = measuring(db, consumer, bridge)
    assert started.estadoMedicion == "ADQUIRIENDO" and started.modoMedicion == "OXIMETRIA"
    assert started.dispositivo.codigoDispositivo == CODE and audits(db, "INICIAR_SESION_DISPOSITIVO")
    sessionState = telemetryService.status(db, user)["sesion"]
    assert sessionState["idMedicion"] == str(started.idMedicion) and not sessionState["estabilidad"]["estable"]

    glucose = iter(range(105, 123, 2))
    for _ in range(9):  # el firmware cambia el valor DEMO a propósito
        bridge.send([line(bpm="76.43", spo2="99.65", glu=f"{next(glucose)}.0", index="2.41492")])
        bridge.clock.advance(1)
    assert telemetryService.status(db, user)["sesion"]["estabilidad"]["estable"] is True

    saved = telemetryService.saveSession(db, user)
    assert saved.estadoMedicion == "COMPLETADA" and saved.esDemo and saved.origenGlucosa == "DEMO"
    assert float(saved.spo2) == 99.65 and saved.frecuenciaCardiaca == 76
    assert float(saved.glucosaDispositivo) == 114.0 and saved.unidadGlucosa == "mg/dL"  # mediana de las últimas 8: 107…121
    assert float(saved.indiceOptico) == 2.41492 and saved.lecturasEstabilizadas == 8
    assert saved.versionAlgoritmo == telemetryService.FIRMWARE_ALGORITHM and "DEMO" in saved.observacion
    assert saved.unidades["glucosa"] == "mg/dL" and saved.glucosaEstimada is None  # la estimación con matriz sigue aparte
    assert saved.fechaHoraFin is not None and hub.session is None  # sesión liberada tras el commit
    assert [a.resultado for a in audits(db, "GUARDAR_MEDICION_DISPOSITIVO")] == ["EXITO"]

    # Historial del usuario correcto, conservando el origen.
    page = measurements.listOwnHistory(db, user)
    assert page.total == 1 and page.items[0].origenGlucosa == "DEMO" and page.items[0].esDemo
    assert page.items[0].idMedicion == started.idMedicion


def test_demo_no_entra_en_indicadores_ni_en_el_perfil(db, mails, consumer, bridge):
    user, profileId, *_ = measuring(db, consumer, bridge)
    bridge.seconds(9)
    telemetryService.saveSession(db, user)
    assert measurements.ownStatistics(db, user, 30).cantidadMediciones == 0
    from app.services import dashboard
    summary = dashboard.personalDashboard(db, user, 30)
    assert summary.resumen.completadas == 0 and summary.resumen.ultimaSpo2 is None  # los indicadores no la cuentan
    assert [m.esDemo for m in summary.recientes] == [True] and summary.pruebasDemo == 1  # pero figura, identificada, entre las guardadas
    assert measurements.getOwnProfile(db, user).fechaUltimaMedicion is None  # una prueba no es «la última medición»
    # Con el filtro de origen se consulta aparte.
    assert measurements.listOwnHistory(db, user, origen="DEMO").total == 1
    assert measurements.listOwnHistory(db, user, origen="REAL").total == 0
    with pytest.raises(AuthError) as invalid:
        measurements.listOwnHistory(db, user, origen="OTRO")
    assert invalid.value.code == "DATOS_INVALIDOS"


def test_no_se_envia_por_correo_un_resultado_demo(db, mails, consumer, bridge):
    user, *_ = measuring(db, consumer, bridge)
    bridge.seconds(9)
    saved = telemetryService.saveSession(db, user)
    assert saved.envioResultado is None and saved.puedeEliminar
    with pytest.raises(AuthError) as raised:
        measurements.sendResultByEmail(db, user, saved.idMedicion, ResultSendRequest())
    assert raised.value.code == "RESULTADO_DEMO_NO_ENVIABLE"


def test_sin_calibrar_y_experimental_se_guardan_con_su_origen(db, mails, consumer, bridge):
    user, profileId = consumer
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    startFor(db, user, profileId, dev)
    bridge.seconds(9, origen="SIN_CALIBRAR", glu="NA")
    uncalibrated = telemetryService.saveSession(db, user)
    assert uncalibrated.origenGlucosa == "SIN_CALIBRAR" and uncalibrated.glucosaDispositivo is None
    assert uncalibrated.unidadGlucosa is None and not uncalibrated.esDemo and uncalibrated.envioResultado == "CUENTA_PROPIA"
    startFor(db, user, profileId, dev)
    bridge.seconds(9, origen="EXPERIMENTAL", glu="131.4")
    experimental = telemetryService.saveSession(db, user)
    assert experimental.origenGlucosa == "EXPERIMENTAL" and float(experimental.glucosaDispositivo) == 131.4
    assert "DEMO" not in (experimental.observacion or "")
    # Distintos de DEMO: sí cuentan como mediciones reales (SpO₂ y BPM); la glucosa del firmware queda aparte de glucosaEstimada.
    stats = measurements.ownStatistics(db, user, 30)
    assert stats.cantidadMediciones == 2 and stats.glucosa.cantidad == 0 and stats.spo2.cantidad == 2
    assert measurements.getOwnProfile(db, user).fechaUltimaMedicion is not None


@pytest.mark.parametrize(("fields", "code"), [
    ({"finger": 0, "valid": 0, "index": "NA", "bpm": "0.00", "spo2": "0.00", "samples": 0}, "DEDO_NO_DETECTADO"),
    ({"valid": 0, "index": "NA"}, "SENAL_NO_VALIDA"),
])
def test_dedo_retirado_o_senal_invalida_impide_guardar(db, consumer, bridge, fields, code):
    user, *_ = measuring(db, consumer, bridge)
    bridge.seconds(5)  # todavía no hay 8 lecturas válidas
    bridge.seconds(1, **fields)
    with pytest.raises(AuthError) as raised:
        telemetryService.saveSession(db, user)
    assert raised.value.code == "LECTURA_NO_ESTABLE" and hub.session is not None  # la sesión sigue: se puede reintentar
    assert hub.stability().code == code
    assert db.scalar(select(Measurement.estadoMedicion)) == "ADQUIRIENDO"
    bridge.seconds(8)  # el dedo vuelve y la señal se estabiliza
    assert telemetryService.saveSession(db, user).estadoMedicion == "COMPLETADA"


@pytest.mark.parametrize("fields", [
    {"finger": 0, "valid": 0, "index": "NA", "bpm": "0.00", "spo2": "0.00", "samples": 0},
    {"valid": 0, "index": "NA"},
])
def test_con_las_ultimas_lecturas_validas_se_guarda_aunque_se_retire_el_dedo(db, consumer, bridge, fields):
    user, *_ = measuring(db, consumer, bridge)
    bridge.seconds(9)  # ya hay 8 lecturas válidas seguidas
    bridge.seconds(2, **fields)  # y se retira el dedo
    assert telemetryService.saveSession(db, user).estadoMedicion == "COMPLETADA"


def test_revocar_la_autorizacion_durante_la_sesion_impide_guardar(db, consumer, bridge):
    from app.services import consent as consentService

    user, *_ = measuring(db, consumer, bridge)
    bridge.seconds(9)
    consentService.setExperimentalConsent(db, user, False)
    with pytest.raises(AuthError) as raised:
        telemetryService.saveSession(db, user)
    assert raised.value.code == "CONSENTIMIENTO_REQUERIDO"
    assert db.scalar(select(Measurement.estadoMedicion)) == "ADQUIRIENDO"  # nada se persistió


def test_pocas_lecturas_o_variacion_impiden_guardar(db, consumer, bridge):
    user, *_ = measuring(db, consumer, bridge)
    bridge.seconds(3)
    with pytest.raises(AuthError) as few:
        telemetryService.saveSession(db, user)
    assert few.value.code == "LECTURA_NO_ESTABLE" and "suficientes" in few.value.message
    for bpm in ("60.00", "95.00") * 4:
        bridge.seconds(1, bpm=bpm)
    with pytest.raises(AuthError) as noisy:
        telemetryService.saveSession(db, user)
    assert noisy.value.code == "LECTURA_NO_ESTABLE" and "varían" in noisy.value.message


def test_las_lecturas_previas_a_la_sesion_no_se_atribuyen(db, consumer, bridge):
    """Una persona previa tenía el dedo en el sensor: esas lecturas no pertenecen a quien abre la sesión."""
    user, profileId = consumer
    dev = device(db, codigo=CODE)
    bridge.seconds(20)
    startFor(db, user, profileId, dev)
    with pytest.raises(AuthError) as raised:
        telemetryService.saveSession(db, user)
    assert raised.value.code == "LECTURA_NO_ESTABLE" and "Todavía no llegaron" in raised.value.message
    bridge.seconds(9)
    assert telemetryService.saveSession(db, user).lecturasEstabilizadas == 8


def test_perdida_de_bluetooth_durante_la_sesion_se_audita_y_se_recupera(db, consumer, bridge, clock):
    user, *_ = measuring(db, consumer, bridge)
    bridge.seconds(9)
    bridge.send([], state="DESCONECTADO", error="se perdió el enlace")
    failures = audits(db, "ERROR_COMUNICACION_DISPOSITIVO")
    assert len(failures) == 1 and failures[0].resultado == "FALLO"
    for attempt in range(1, 11):  # 30 s sin enlace; el puente sigue enviando latidos mientras reintenta
        clock.advance(3)
        bridge.send([], state="REINTENTANDO", attempt=attempt)
    assert len(audits(db, "ERROR_COMUNICACION_DISPOSITIVO")) == 1  # una sola entrada por corte
    with pytest.raises(AuthError) as raised:
        telemetryService.saveSession(db, user)
    assert raised.value.code == "DISPOSITIVO_NO_CONECTADO" and hub.session is not None
    assert telemetryService.status(db, user)["sesion"]["enlacePerdido"] is True
    bridge.send([], state="CONECTADO")
    bridge.seconds(3)
    with pytest.raises(AuthError) as insufficient:  # lo anterior al corte no completa una lectura estable
        telemetryService.saveSession(db, user)
    assert insufficient.value.code == "LECTURA_NO_ESTABLE"
    bridge.seconds(6)
    assert telemetryService.saveSession(db, user).estadoMedicion == "COMPLETADA"


def test_otra_cuenta_no_ve_ni_opera_la_sesion(db, mails, consumer, bridge):
    user, profileId, dev, started = measuring(db, consumer, bridge)
    bridge.seconds(9)
    other = makeUser(db, email="otra@example.com", usuario="otra")
    seen = telemetryService.status(db, other)
    assert seen["ocupado"] and seen["lectura"] is None and seen["sesion"] is None and seen["puente"]["puerto"] is None
    otherProfile = measurements.getOwnProfile(db, other).idPerfilMedicion
    for call in (lambda: startFor(db, other, otherProfile, dev), lambda: telemetryService.saveSession(db, other),
                 lambda: telemetryService.cancelSession(db, other)):
        with pytest.raises(AuthError) as raised:
            call()
        assert raised.value.code == "DISPOSITIVO_EN_USO"
    # Tampoco puede usar el perfil de otra persona.
    with pytest.raises(AuthError) as profileDenied:
        telemetry_start = TelemetrySessionStart(idPerfilMedicion=profileId, idDispositivo=dev.idDispositivo)
        telemetryService.startSession(db, other, telemetry_start)
    assert profileDenied.value.code in ("DISPOSITIVO_EN_USO", "PERFIL_NO_ENCONTRADO")
    assert telemetryService.saveSession(db, user).estadoMedicion == "COMPLETADA"  # el dueño sigue pudiendo guardar
    freed = telemetryService.status(db, other)  # liberado: la otra cuenta vuelve a ver el estado
    assert not freed["ocupado"]


def test_otra_cuenta_no_puede_medir_sobre_un_perfil_ajeno(db, mails, consumer, bridge):
    user, profileId = consumer
    other = makeUser(db, email="otra@example.com", usuario="otra")
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    with pytest.raises(AuthError) as raised:
        startFor(db, other, profileId, dev)
    assert raised.value.code == "PERFIL_NO_ENCONTRADO" and hub.session is None


def test_no_se_guarda_dos_veces(db, mails, consumer, bridge, engine):
    user, profileId, dev, started = measuring(db, consumer, bridge)
    bridge.seconds(9)
    session = hub.session
    first = telemetryService.saveSession(db, user)
    with pytest.raises(AuthError) as second:  # la sesión ya no existe
        telemetryService.saveSession(db, user)
    assert second.value.code == "ADQUISICION_NO_ACTIVA"
    # Aun si una sesión quedara colgada, la transición condicionada al estado impide completar dos veces.
    with pytest.raises(AuthError) as stale:
        telemetryService._persist(db, user, session)
    assert stale.value.code == "MEDICION_ESTADO_INVALIDO"
    assert len(audits(db, "GUARDAR_MEDICION_DISPOSITIVO")) == 1 and first.estadoMedicion == "COMPLETADA"
    assert len(list(db.scalars(select(Measurement)))) == 1


def test_guardados_simultaneos_producen_una_sola_medicion(db, mails, consumer, bridge, engine):
    user, *_ = measuring(db, consumer, bridge)
    bridge.seconds(9)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    results, barrier = [], threading.Barrier(4)

    def attempt():
        session = factory()
        try:
            barrier.wait()
            results.append(telemetryService.saveSession(session, session.merge(user)))
        except AuthError as error:
            results.append(error.code)
        finally:
            session.close()

    threads = [threading.Thread(target=attempt) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    successes = [r for r in results if not isinstance(r, str)]
    assert len(successes) == 1 and set(r for r in results if isinstance(r, str)) <= {"GUARDADO_EN_CURSO", "ADQUISICION_NO_ACTIVA"}
    assert len(list(db.scalars(select(Measurement)))) == 1


def test_cancelar_la_sesion_libera_el_dispositivo_sin_guardar(db, consumer, bridge):
    user, profileId, dev, started = measuring(db, consumer, bridge)
    bridge.seconds(9)
    cancelled = telemetryService.cancelSession(db, user)
    assert cancelled.estadoMedicion == "CANCELADA" and cancelled.origenGlucosa is None and hub.session is None
    startFor(db, user, profileId, dev)  # se puede abrir otra
    assert hub.session is not None


def test_la_sesion_vence_y_libera_el_dispositivo(db, consumer, bridge, clock):
    user, profileId, dev, started = measuring(db, consumer, bridge)
    clock.advance(telemetry.SESSION_MAX_SECONDS + 1)
    bridge.send([line()])
    assert telemetryService.status(db, user)["sesion"] is None and hub.session is None
    with pytest.raises(AuthError) as raised:
        telemetryService.saveSession(db, user)
    assert raised.value.code == "ADQUISICION_NO_ACTIVA"


def test_una_sesion_por_vez_por_cuenta(db, consumer, bridge):
    user, profileId, dev, _ = measuring(db, consumer, bridge)
    with pytest.raises(AuthError) as raised:
        startFor(db, user, profileId, dev)
    assert raised.value.code == "ADQUISICION_ACTIVA"
    assert len(list(db.scalars(select(Measurement)))) == 1  # no se creó otra medición


# --- Instituciones ---------------------------------------------------------------------------------------------------------


def test_el_operador_mide_a_su_paciente_y_queda_trazado(db, mails, team, bridge):
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    dev = device(db, institucion=team.id, codigo=CODE)
    bridge.seconds(1)
    # Firmware sin ID propio (como este puente de prueba): el operador confirma a mano qué dispositivo es antes de medir.
    deviceConnection.confirm(db, team.operator, DeviceConnectConfirm(idInstitucion=team.id, idDispositivo=dev.idDispositivo))
    started = startFor(db, team.operator, patient.idPerfilMedicion, dev)
    bridge.seconds(9)
    saved = telemetryService.saveSession(db, team.operator)
    assert saved.estadoMedicion == "COMPLETADA" and saved.idPerfilMedicion == patient.idPerfilMedicion
    trace = audits(db, "GUARDAR_MEDICION_DISPOSITIVO")[0]
    assert trace.idUsuario == team.operator.idUsuario and trace.idRelacionado is not None
    # El historial institucional del paciente muestra el origen; los indicadores de la institución no lo cuentan.
    page = measurements.listPatientHistory(db, team.operator, team.id, patient.idPerfilMedicion)
    assert page.items[0].origenGlucosa == "DEMO"
    assert measurements.patientStatistics(db, team.operator, team.id, patient.idPerfilMedicion).cantidadMediciones == 0
    assert measurements.institutionIndicators(db, team.owner, team.id).completadas["spo2"].cantidad == 0
    assert started.idMedicion == saved.idMedicion


def test_un_operador_no_mide_pacientes_de_otro(db, mails, team, bridge):
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    dev = device(db, institucion=team.id, codigo=CODE)
    bridge.seconds(1)
    with pytest.raises(AuthError) as raised:
        startFor(db, team.owner, patient.idPerfilMedicion, dev)  # el propietario no es el operador a cargo
    assert raised.value.code in ("PERMISO_INSUFICIENTE", "PERFIL_NO_ENCONTRADO") and hub.session is None


def test_un_dispositivo_de_otra_institucion_no_se_puede_usar(db, mails, team, consumer, bridge, deviceMode):
    deviceMode(False)  # modo restringido por asignación (DEC-01)
    user, profileId = consumer
    dev = device(db, institucion=team.id, codigo=CODE)  # asignado a una institución: una cuenta individual no lo usa
    bridge.seconds(1)
    with pytest.raises(AuthError) as raised:
        startFor(db, user, profileId, dev)
    assert raised.value.code == "DISPOSITIVO_NO_DISPONIBLE"


# --- Datos de prueba: consultar y eliminar -------------------------------------------------------------------------------------


def saveWith(db, user, profileId, dev, bridge, origen, glu):
    startFor(db, user, profileId, dev)
    bridge.seconds(9, origen=origen, glu=glu)
    return telemetryService.saveSession(db, user)


def test_los_datos_demo_se_eliminan_sin_afectar_las_mediciones_reales(db, mails, consumer, bridge):
    user, profileId = consumer
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    demoA = saveWith(db, user, profileId, dev, bridge, "DEMO", "117.0")
    demoB = saveWith(db, user, profileId, dev, bridge, "DEMO", "109.0")
    real = saveWith(db, user, profileId, dev, bridge, "SIN_CALIBRAR", "NA")
    assert measurements.listOwnHistory(db, user).total == 3
    assert measurements.listOwnHistory(db, user, origen="DEMO").total == 2
    with pytest.raises(AuthError) as protected:  # una medición real no se elimina
        measurements.deleteDemoMeasurement(db, user, real.idMedicion)
    assert protected.value.code == "DATO_NO_ELIMINABLE"
    assert measurements.deleteDemoMeasurement(db, user, demoA.idMedicion) == 1
    assert measurements.listOwnHistory(db, user, origen="DEMO").total == 1
    assert measurements.deleteOwnDemoMeasurements(db, user) == 1
    page = measurements.listOwnHistory(db, user)
    assert page.total == 1 and page.items[0].idMedicion == real.idMedicion  # la real sigue intacta
    assert measurements.getMeasurement(db, user, real.idMedicion).origenGlucosa == "SIN_CALIBRAR"
    assert len(audits(db, "ELIMINAR_DATOS_DEMO")) == 2
    with pytest.raises(AuthError) as gone:
        measurements.getMeasurement(db, user, demoB.idMedicion)
    assert gone.value.code == "MEDICION_NO_ENCONTRADA"


def test_no_se_eliminan_los_datos_demo_de_otra_cuenta(db, mails, consumer, bridge):
    user, profileId = consumer
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    demo = saveWith(db, user, profileId, dev, bridge, "DEMO", "117.0")
    other = makeUser(db, email="otra@example.com", usuario="otra")
    measurements.getOwnProfile(db, other)
    with pytest.raises(AuthError) as raised:
        measurements.deleteDemoMeasurement(db, other, demo.idMedicion)
    assert raised.value.code == "MEDICION_NO_ENCONTRADA"
    assert measurements.deleteOwnDemoMeasurements(db, other) == 0
    assert measurements.listOwnHistory(db, user, origen="DEMO").total == 1


def test_eliminar_demo_por_http(db, mails, consumer, bridge, api):
    user, profileId = consumer
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    demo = saveWith(db, user, profileId, dev, bridge, "DEMO", "117.0")
    real = saveWith(db, user, profileId, dev, bridge, "SIN_CALIBRAR", "NA")
    client = api(user)
    assert client.get("/api/v1/measurements?origen=DEMO").json()["total"] == 1
    assert client.get("/api/v1/measurements?origen=REAL").json()["total"] == 1
    assert client.get("/api/v1/measurements?origen=XXX").status_code == 422
    assert client.delete(f"/api/v1/measurements/{real.idMedicion}").status_code == 409
    assert client.delete(f"/api/v1/measurements/{demo.idMedicion}").json() == {"eliminadas": 1}
    assert client.delete("/api/v1/measurements/demo").json() == {"eliminadas": 0}
    detail = client.get(f"/api/v1/measurements/{real.idMedicion}").json()
    assert detail["origenGlucosa"] == "SIN_CALIBRAR" and detail["unidades"]["frecuenciaCardiaca"] == "lpm"


def test_persistencia_y_consulta_en_la_base(db, mails, consumer, bridge, engine):
    """El registro guardado se relee desde otra sesión (no desde la caché de la que guardó)."""
    user, profileId, dev, started = measuring(db, consumer, bridge)
    bridge.seconds(9)
    telemetryService.saveSession(db, user)
    fresh = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        row = fresh.get(Measurement, started.idMedicion)
        assert row.estadoMedicion == "COMPLETADA" and row.idPerfilMedicion == profileId and row.idDispositivo == dev.idDispositivo
        assert (row.origenGlucosa, row.unidadGlucosa, row.lecturasEstabilizadas) == ("DEMO", "mg/dL", 8)
        assert float(row.spo2) == 98.0 and row.frecuenciaCardiaca == 72 and float(row.indiceOptico) == 2.41492
        assert float(row.glucosaDispositivo) == 117.0 and row.glucosaEstimada is None
        assert row.fechaHoraFin >= row.fechaHoraInicio and row.versionFirmwareAlMomento == dev.versionFirmware
    finally:
        fresh.close()
