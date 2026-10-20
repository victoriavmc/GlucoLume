# Señal PPG real del MAX30100: protocolo del firmware, buffer por sesión, huecos y aislamiento entre sesiones.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_ppg.py -v

import pytest

from app.acquisition.telemetry import PPG_HZ, PPG_WINDOW, PpgChunk, TelemetryError, hub, parseLine, parsePpg
from app.services import telemetry as telemetryService
from tests.test_account_deletion import db, engine, mails, makeUser  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_measurements import device  # noqa: F401
from tests.test_telemetry import CODE, bridge, clock, consumer, freshHub, line, startFor  # noqa: F401


def chunk(seq, values, mask=0):
    return "PPG," + ",".join(str(x) for x in (seq, mask, *values))


# --- Protocolo -----------------------------------------------------------------------------------------------------------------


def test_interpreta_un_bloque_ppg_del_firmware():
    parsed = parseLine("PPG,7,5,-12,30,45,2,-8")
    assert parsed == PpgChunk(seq=7, mask=5, values=(-12, 30, 45, 2, -8))
    assert [i for i in range(5) if parsed.mask >> i & 1] == [0, 2]  # latidos en las muestras 0 y 2


@pytest.mark.parametrize("text", [
    "PPG", "PPG,1,0", "PPG,1,0,", "PPG,256,0,1,2", "PPG,x,0,1", "PPG,1,0,1.5", "PPG,1,0,99999", "PPG,1,0,abc",
    "PPG,1,8,1,2,3",  # máscara con un bit fuera de las muestras del bloque
    "PPG,1,0," + ",".join(["1"] * 33),  # bloque demasiado largo
])
def test_un_bloque_corrupto_o_truncado_se_rechaza(text):
    with pytest.raises(TelemetryError):
        parseLine(text)


def test_las_lineas_de_metricas_siguen_funcionando_igual():
    assert parseLine(line()).bpm == 72.0
    assert parsePpg("PPG,0,0,1").values == (1,)


# --- Buffer de la sesión --------------------------------------------------------------------------------------------------------


def session(db, consumer, bridge):
    user, profileId = consumer
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    return user, startFor(db, user, profileId, dev)


def test_no_se_guarda_ppg_sin_una_sesion_en_curso(db, mails, consumer, bridge, clock):
    user, profileId = consumer
    device(db, codigo=CODE)
    bridge.send([chunk(0, [1, 2, 3])])
    assert hub.session is None and telemetryService.status(db, user)["sesion"] is None


def test_los_bloques_de_la_sesion_forman_una_ventana_con_sus_latidos(db, mails, consumer, bridge, clock):
    user, started = session(db, consumer, bridge)
    bridge.send([chunk(0, range(10), mask=0b0000100001)])
    clock.advance(0.4)
    bridge.send([chunk(1, range(10, 20), mask=0b1000000000)])
    ppg = telemetryService.status(db, user)["sesion"]["ppg"]
    assert ppg["hz"] == PPG_HZ and ppg["inicio"] == 0 and ppg["valores"] == list(range(20))
    assert ppg["latidos"] == [0, 5, 19]  # índices absolutos de las muestras con latido
    assert ppg["edadSegundos"] == 0.0


def test_un_bloque_repetido_no_duplica_muestras(db, mails, consumer, bridge, clock):
    user, started = session(db, consumer, bridge)
    bridge.send([chunk(3, [1, 2, 3])])
    bridge.send([chunk(3, [1, 2, 3])], seqs=[10_000])
    assert telemetryService.status(db, user)["sesion"]["ppg"]["valores"] == [1, 2, 3]


def test_un_corte_de_senal_deja_un_hueco_sin_interpolar(db, mails, consumer, bridge, clock):
    user, started = session(db, consumer, bridge)
    bridge.send([chunk(0, [10] * 10)])
    clock.advance(2.0)  # dedo retirado: el firmware no envía bloques
    bridge.send([chunk(1, [20] * 10)])
    values = telemetryService.status(db, user)["sesion"]["ppg"]["valores"]
    assert values[:10] == [10] * 10 and values[-10:] == [20] * 10
    holes = values[10:-10]
    assert holes and all(v is None for v in holes)  # hueco real, no valores inventados
    assert abs(len(holes) - round((2.0 - 10 / PPG_HZ) * PPG_HZ)) <= 1


def test_la_ventana_es_deslizante_y_acotada(db, mails, consumer, bridge, clock):
    user, started = session(db, consumer, bridge)
    for n in range(40):
        bridge.send([chunk(n % 256, [n] * 10)])
        clock.advance(10 / PPG_HZ)
    ppg = telemetryService.status(db, user)["sesion"]["ppg"]
    assert len(ppg["valores"]) == PPG_WINDOW and ppg["inicio"] == 400 - PPG_WINDOW


def test_lo_anterior_al_inicio_de_la_sesion_no_se_mezcla(db, mails, consumer, bridge, clock):
    user, profileId = consumer
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    bridge.send([chunk(0, [99] * 10)], ageMs=0)
    clock.advance(1)
    startFor(db, user, profileId, dev)
    bridge.send([chunk(1, [5] * 10)], ageMs=3000)  # leído por el puente ANTES de que empezara la sesión
    assert telemetryService.status(db, user)["sesion"]["ppg"] is None
    bridge.send([chunk(2, [7] * 10)])
    assert telemetryService.status(db, user)["sesion"]["ppg"]["valores"] == [7] * 10


def test_la_senal_de_una_sesion_no_pasa_a_la_siguiente(db, mails, consumer, bridge, clock):
    user, started = session(db, consumer, bridge)
    bridge.send([chunk(0, [1] * 10)])
    telemetryService.cancelSession(db, user)
    _, profileId = consumer
    startFor(db, user, profileId, device(db, codigo=CODE))
    assert telemetryService.status(db, user)["sesion"]["ppg"] is None


def test_otra_cuenta_no_ve_la_senal_ni_recibe_su_evento(db, mails, consumer, bridge, clock):
    user, started = session(db, consumer, bridge)
    other = makeUser(db, email="otra@example.com", usuario="otra")
    channel = hub.subscribe(other.idUsuario)
    bridge.send([chunk(0, [1] * 10)])
    snapshot = telemetryService.status(db, other)
    assert snapshot["ocupado"] is True and snapshot["sesion"] is None  # sin datos de la sesión ajena
    assert channel.empty()  # el evento de PPG tampoco le llega


def test_un_bloque_corrupto_se_cuenta_como_linea_invalida(db, mails, consumer, bridge, clock):
    user, started = session(db, consumer, bridge)
    result = bridge.send(["PPG,1,0,abc"])
    assert result.invalidas == 1


def test_el_endpoint_de_estado_entrega_la_ventana_ppg_de_la_sesion(api, db, mails, consumer, bridge, clock):
    user, started = session(db, consumer, bridge)
    bridge.send([chunk(0, [4, -3, 9], mask=0b100)])
    body = api(user).get("/api/v1/acquisition/telemetry/status").json()
    assert body["sesion"]["ppg"] == {"hz": 25, "inicio": 0, "valores": [4, -3, 9], "latidos": [2], "edadSegundos": 0.0}
