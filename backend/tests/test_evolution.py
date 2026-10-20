# Evolución histórica de las mediciones propias (GET /measurements/evolution): cada medición guardada es un punto, DEMO separado.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_evolution.py -v

from datetime import date, timedelta

import pytest
from sqlalchemy import update

from app.models.measurement import Measurement
from app.services import measurement as measurements
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import db, engine, mails, makeUser  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_measurements import completeOximetry, consumer, device, expectError  # noqa: F401


def mark(db, idMedicion, **values):
    db.execute(update(Measurement).where(Measurement.idMedicion == idMedicion).values(**values))
    db.commit()


def hoursAgo(db, idMedicion, hours):
    mark(db, idMedicion, fechaHoraInicio=nowForDb() - timedelta(hours=hours))


def demo(db, idMedicion, glucose=114):
    mark(db, idMedicion, origenGlucosa="DEMO", glucosaDispositivo=glucose, unidadGlucosa="mg/dL")


def experimental(db, idMedicion, glucose=101):
    mark(db, idMedicion, origenGlucosa="EXPERIMENTAL", glucosaDispositivo=glucose, unidadGlucosa="mg/dL")


@pytest.fixture
def history(db, mails, consumer):
    user, profileId = consumer
    dev = device(db)
    rows = {}
    for key, (spo2, hr, hours) in {"a": ("97", 78, 30), "b": ("98", 86, 5), "c": ("96", 108, 2)}.items():
        rows[key] = completeOximetry(db, user, profileId, dev, spo2=spo2, hr=hr)
        hoursAgo(db, rows[key].idMedicion, hours)
    experimental(db, rows["b"].idMedicion, 101)
    d = completeOximetry(db, user, profileId, dev, spo2="99", hr=70)
    demo(db, d.idMedicion, 117)
    hoursAgo(db, d.idMedicion, 1)
    rows["demo"] = d
    return user, profileId, rows


def test_cada_medicion_guardada_es_un_punto_en_orden_cronologico(db, history):
    user, _, rows = history
    data = measurements.ownEvolution(db, user, 7, origen="EXPERIMENTAL")
    assert [p.idMedicion for p in data.puntos] == [rows["a"].idMedicion, rows["b"].idMedicion, rows["c"].idMedicion]
    assert [p.frecuenciaCardiaca for p in data.puntos] == [78, 86, 108]
    assert all(not p.esDemo for p in data.puntos) and not data.truncado
    assert data.puntos[1].glucosa == 101.0 and data.puntos[1].origen == "EXPERIMENTAL"
    assert data.puntos[0].glucosa is None  # sin glucosa: nunca un cero ni un valor intermedio inventado


def test_las_estadisticas_experimentales_no_incluyen_demo(db, history):
    user, *_ = history
    stats = measurements.ownEvolution(db, user, 7).estadisticas
    assert stats.demo is None and stats.experimental.mediciones == 3
    assert stats.experimental.frecuenciaCardiaca.promedio == pytest.approx((78 + 86 + 108) / 3, abs=0.01)
    assert stats.experimental.frecuenciaCardiaca.minimo == 78 and stats.experimental.frecuenciaCardiaca.maximo == 108
    assert stats.experimental.frecuenciaCardiaca.ultimo.valor == 108
    assert stats.experimental.glucosa.cantidad == 1 and stats.experimental.glucosa.promedio == 101.0


def test_demo_se_ve_aparte_y_con_estadisticas_propias(db, history):
    user, _, rows = history
    data = measurements.ownEvolution(db, user, 7, origen="DEMO")
    assert [p.idMedicion for p in data.puntos] == [rows["demo"].idMedicion] and data.puntos[0].esDemo and data.puntos[0].origen == "DEMO"
    assert data.estadisticas.experimental is None and data.estadisticas.demo.glucosa.promedio == 117.0


def test_todos_distingue_los_puntos_y_no_mezcla_promedios(db, history):
    user, *_ = history
    data = measurements.ownEvolution(db, user, 7, origen="TODOS")
    assert len(data.puntos) == 4 and sum(p.esDemo for p in data.puntos) == 1
    assert data.estadisticas.experimental.mediciones == 3 and data.estadisticas.demo.mediciones == 1
    # El promedio experimental sigue siendo el de las tres reales (la DEMO no lo mueve).
    assert data.estadisticas.experimental.frecuenciaCardiaca.promedio == pytest.approx((78 + 86 + 108) / 3, abs=0.01)


def test_sin_calibrar_no_es_una_glucosa(db, mails, consumer):
    user, profileId = consumer
    row = completeOximetry(db, user, profileId, device(db))
    mark(db, row.idMedicion, origenGlucosa="SIN_CALIBRAR")
    point = measurements.ownEvolution(db, user, 7).puntos[0]
    assert point.origen == "SIN_CALIBRAR" and point.glucosa is None
    assert measurements.ownEvolution(db, user, 7).estadisticas.experimental.glucosa.cantidad == 0


@pytest.mark.parametrize(("dias", "expected"), [(1, 2), (7, 3), (14, 3), (30, 3)])
def test_el_periodo_filtra_las_mediciones(db, history, dias, expected):
    user, *_ = history
    assert len(measurements.ownEvolution(db, user, dias).puntos) == expected  # la de hace 30 h queda fuera de «24 horas»


def test_periodo_personalizado_y_validaciones(db, history):
    user, *_ = history
    today = date.today()
    custom = measurements.ownEvolution(db, user, 30, desde=today - timedelta(days=3), hasta=today)
    assert len(custom.puntos) == 3
    expectError("PERIODO_INVALIDO", measurements.ownEvolution, db, user, 15)
    expectError("PERIODO_INVALIDO", measurements.ownEvolution, db, user, 30, today, today - timedelta(days=2))
    expectError("DATOS_INVALIDOS", measurements.ownEvolution, db, user, 7, None, None, "OTRO")


def test_sin_datos_hay_estado_vacio_sin_ceros(db, mails, consumer):
    user, _ = consumer
    data = measurements.ownEvolution(db, user, 30)
    assert data.puntos == [] and data.estadisticas.experimental.mediciones == 0
    stat = data.estadisticas.experimental.frecuenciaCardiaca
    assert (stat.cantidad, stat.ultimo, stat.promedio, stat.minimo, stat.maximo) == (0, None, None, None, None)


def test_las_canceladas_no_son_puntos(db, mails, consumer):
    from tests.test_measurements import oximetry

    user, profileId = consumer
    started = oximetry(db, user, profileId, device(db))
    measurements.cancelMeasurement(db, user, started.idMedicion)
    assert measurements.ownEvolution(db, user, 7).puntos == []


def test_otra_cuenta_no_ve_mis_puntos_ni_por_http(api, db, history):
    user, *_ = history
    other = makeUser(db, email="otra@example.com", usuario="otra")
    assert api(other).get("/api/v1/measurements/evolution?dias=7").json()["puntos"] == []
    own = api(user).get("/api/v1/measurements/evolution?dias=7&origen=TODOS")
    assert own.status_code == 200 and len(own.json()["puntos"]) == 4
    assert api(user).get("/api/v1/measurements/evolution?dias=9").status_code == 422


def test_24_horas_con_origen_demo_trae_solo_las_pruebas_de_la_ventana_e_informa_el_inicio(db, history):
    user, _, rows = history
    data = measurements.ownEvolution(db, user, 1, origen="DEMO")
    assert [p.idMedicion for p in data.puntos] == [rows["demo"].idMedicion] and all(p.esDemo for p in data.puntos)
    # `desde` es el inicio real de la ventana (ahora − 24 h): el frontend lo usa para graficar el eje del período.
    assert abs((nowForDb() - timedelta(hours=24)) - data.desde) < timedelta(minutes=1) and data.hasta is None
