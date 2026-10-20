# Evolución de las mediciones de UN paciente (services/measurement.patientEvolution): incluye DEMO identificado y separado de lo
# experimental, todos los valores de cada medición sin importar el modo, resumen con conteos y última medición, y acceso solo del operador.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_patient_evolution.py -v

from datetime import timedelta

import pytest
from sqlalchemy import update

from app.models.measurement import Measurement
from app.services import institutionPatients as patients
from app.services import measurement as measurements
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import audits, db, engine, mails, reload  # noqa: F401
from tests.test_dashboards import measure
from tests.test_institution_patients import addOperator, patientData
from tests.test_institutions import expectError, freshLookupLimiter, team  # noqa: F401
from tests.test_measurements import device  # noqa: F401


def tune(db, idMedicion, **values):
    db.execute(update(Measurement).where(Measurement.idMedicion == idMedicion).values(**values))
    db.commit()


def evolution(db, actor, team, patient, **kwargs):
    return measurements.patientEvolution(db, actor, team.id, patient.idPerfilMedicion, **kwargs)


@pytest.fixture
def demoOnly(db, team):
    """Paciente cuyo historial tiene SOLO dos mediciones DEMO completadas (una de cada modo), la más reciente de glucosa."""
    dev = device(db, institucion=team.id)
    patient = patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz", dni="20111222"))
    old = measure(db, team.operator, patient.idPerfilMedicion, dev, "95", 70)
    new = measure(db, team.operator, patient.idPerfilMedicion, dev, "97", 80)
    now = nowForDb()
    tune(db, old.idMedicion, origenGlucosa="DEMO", glucosaDispositivo=110, unidadGlucosa="mg/dL", calidadSenal=0.5, fechaHoraInicio=now - timedelta(days=2))
    tune(db, new.idMedicion, origenGlucosa="DEMO", glucosaDispositivo=120, unidadGlucosa="mg/dL", modoMedicion="GLUCOSA_EXPERIMENTAL", calidadSenal=None,
         fechaHoraInicio=now - timedelta(hours=3))
    return patient, old, new, dev


def test_un_paciente_con_solo_demo_grafica_sus_valores_identificados(db, team, demoOnly):
    patient, old, new, _ = demoOnly
    data = evolution(db, team.operator, team, patient)  # origen TODOS por defecto
    assert [p.idMedicion for p in data.puntos] == [old.idMedicion, new.idMedicion] and all(p.esDemo for p in data.puntos)
    assert data.estadisticas.experimental.mediciones == 0 and data.estadisticas.demo.mediciones == 2  # promedios SEPARADOS por origen
    demo = data.estadisticas.demo
    assert demo.spo2.cantidad == 2 and demo.frecuenciaCardiaca.cantidad == 2 and demo.glucosa.cantidad == 2  # ambos modos aportan todo lo registrado
    assert demo.glucosa.promedio == 115 and demo.glucosa.ultimo.valor == 120  # la última es la más reciente
    assert demo.calidadSenal.cantidad == 1 and demo.calidadSenal.promedio == 0.5  # la ausente no entra ni como 0
    assert data.estadisticas.experimental.glucosa.promedio is None  # sin datos: null, nunca 0
    only = evolution(db, team.operator, team, patient, origen="EXPERIMENTAL")
    assert only.puntos == [] and only.resumen.demo == 2  # el resumen cuenta DEMO aunque el filtro pida solo experimentales


def test_el_resumen_cuenta_por_origen_y_modo_y_trae_la_ultima(db, team, demoOnly):
    patient, old, new, dev = demoOnly
    exp = measure(db, team.operator, patient.idPerfilMedicion, dev, "98", 66)
    tune(db, exp.idMedicion, fechaHoraInicio=nowForDb() - timedelta(days=10))
    summary = evolution(db, team.operator, team, patient, dias=30).resumen
    assert (summary.total, summary.experimentales, summary.demo) == (3, 1, 2)
    assert summary.porModo == {"OXIMETRIA": 2, "GLUCOSA_EXPERIMENTAL": 1}
    assert summary.ultima.esDemo and summary.ultima.modoMedicion == "GLUCOSA_EXPERIMENTAL"  # el registro más reciente (la DEMO de hace 3 h)
    week = evolution(db, team.operator, team, patient, dias=7)
    assert week.resumen.total == 2 and week.resumen.experimentales == 0  # el período acota el conteo, no la «última»
    assert week.resumen.ultima.fecha == summary.ultima.fecha
    byMode = evolution(db, team.operator, team, patient, modo="GLUCOSA_EXPERIMENTAL")
    assert [p.idMedicion for p in byMode.puntos] == [new.idMedicion] and byMode.resumen.total == 1


def test_estados_distintos_de_completada_no_se_grafican_ni_se_cuentan(db, team, demoOnly):
    patient, old, new, dev = demoOnly
    tune(db, old.idMedicion, estadoMedicion="INVALIDA")
    data = evolution(db, team.operator, team, patient)
    assert [p.idMedicion for p in data.puntos] == [new.idMedicion] and data.resumen.total == 1


def test_sin_mediciones_todo_queda_vacio(db, team):
    patient = patients.createPatient(db, team.operator, team.id, patientData(nombre="ana", apellido="gil", dni="40111222"))
    data = evolution(db, team.operator, team, patient)
    assert data.puntos == [] and data.resumen.total == 0 and data.resumen.ultima is None
    assert data.estadisticas.demo.spo2.promedio is None


def test_solo_el_operador_responsable_accede_y_los_filtros_se_validan(db, team, demoOnly):
    patient, *_ = demoOnly
    for actor in (team.owner, team.moderator):
        expectError("MEDICIONES_NO_AUTORIZADAS", evolution, db, actor, team, patient)
    other = addOperator(db, team)
    expectError("MEDICIONES_NO_AUTORIZADAS", evolution, db, db.get(type(team.operator), other.idUsuarioInvitado), team, patient)
    expectError("DATOS_INVALIDOS", evolution, db, team.operator, team, patient, origen="OTRO")
    expectError("DATOS_INVALIDOS", evolution, db, team.operator, team, patient, modo="PESO")
    expectError("PERIODO_INVALIDO", evolution, db, team.operator, team, patient, dias=5)
