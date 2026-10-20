# Algoritmo de oximetría (SpO₂ y frecuencia cardíaca) sobre señal RED/IR.
#
# Las señales son sintéticas y existen solo en las pruebas (tests/ppg.py): verifican que el algoritmo recupera los valores
# con que se generan y que rechaza señales inservibles. No validan la calibración clínica, que este prototipo no tiene.

import pytest

from app.acquisition import oximetry
from tests.ppg import ppgSamples


def run(**kwargs):
    bits = kwargs.pop("bits", 18)
    return oximetry.analyze([(t, red, ir) for _, t, red, ir in ppgSamples(**kwargs)], bits=bits)


@pytest.mark.parametrize("heartRate", range(45, 181, 15))
@pytest.mark.parametrize("spo2", [90, 95, 99])
def test_recupera_frecuencia_cardiaca_y_spo2(heartRate, spo2):
    result = run(heartRate=heartRate, spo2=spo2, seed=heartRate)
    assert result.ok and abs(result.heartRate - heartRate) <= 2 and abs(result.spo2 - spo2) <= 0.7
    assert 0.5 <= result.quality <= 1 and result.version == "oximetria-ppg-v1"


def test_funciona_con_el_rango_de_16_bits_del_max30100():
    result = run(dcIr=30000, dcRed=25000, bits=16)
    assert result.ok and result.heartRate == 72


@pytest.mark.parametrize(("kwargs", "fragment"), [
    ({"finger": False}, "dedo"),
    ({"seconds": 5}, "corta"),
    ({"noise": 0.08}, "calidad"),
    ({"dcIr": 400000, "dcRed": 400000}, "saturada"),
])
def test_rechaza_senales_inservibles_con_su_motivo(kwargs, fragment):
    result = run(**kwargs)
    assert not result.ok and result.spo2 is None and result.heartRate is None
    assert fragment in result.reason.lower()


def test_pocas_muestras_o_sin_tiempos():
    assert not oximetry.analyze([(i * 50, 1000, 2000) for i in range(5)]).ok
    assert "tiempos" in oximetry.analyze([(None, 50000, 60000)] * 400).reason


def test_una_senal_plana_no_produce_resultados():
    result = oximetry.analyze([(i * 50, 100000, 120000) for i in range(400)], bits=18)
    assert not result.ok and result.spo2 is None
