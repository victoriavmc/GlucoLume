# «Resultados de salud agregados» de los dashboards de moderador y propietario: separados por origen (DEMO sintético y experimental, nunca en un
# mismo promedio), con los filtros de período, modo y origen aplicados de verdad, DEMO desde una sola medición, y los experimentales con un mínimo
# de pacientes distintos evaluado sobre el conjunto filtrado (y su complemento) para que ningún filtro reconstruya resultados individuales.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_health_aggregates.py -v

from datetime import timedelta

import pytest
from sqlalchemy import update

from app.models.measurement import Measurement
from app.services import dashboard as dashboards
from app.services import institutionPatients as patients
from app.services import measurement as measurements
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import audits, db, engine, mails, reload  # noqa: F401
from tests.test_dashboards import institutionData, measure
from tests.test_institution_patients import patientData
from tests.test_institutions import expectError, freshLookupLimiter, relationOf, team  # noqa: F401
from tests.test_measurements import device  # noqa: F401


def tune(db, measurement, **values):
    db.execute(update(Measurement).where(Measurement.idMedicion == measurement.idMedicion).values(**values))
    db.commit()


def health(db, actor, team, **filters):
    return dashboards.institutionDashboard(db, actor, team.id, 30, **filters).saludAgregada


def newPatients(db, team, count, owner=None):
    return [patients.createPatient(db, owner or team.operator, team.id, patientData(nombre=f"p{n}", apellido=f"x{n}", dni=f"2011{n:04d}")) for n in range(count)]


def experimental(db, team, dev, patient, signal, hr, **values):
    m = measure(db, team.operator, patient.idPerfilMedicion, dev, str(signal), hr)
    if values:
        tune(db, m, **values)
    return m


def demo(db, team, dev, patient, spo2, hr, glucose=110, **values):
    m = measure(db, team.operator, patient.idPerfilMedicion, dev, str(spo2), hr)
    tune(db, m, origenGlucosa="DEMO", glucosaDispositivo=glucose, unidadGlucosa="mg/dL", **values)  # una DEMO siempre trae glucosa simulada
    return m


def withGlucose(db, measurement, value):
    tune(db, measurement, origenGlucosa="EXPERIMENTAL", glucosaDispositivo=value, unidadGlucosa="mg/dL")


@pytest.fixture
def scene(db, team):
    second, secondUser, dev = institutionData(db, team)
    return {"team": team, "dev": dev, "second": second, "secondUser": secondUser}


# --- DEMO: desde una sola medición, identificado y sin mezclar --------------------------------------------------------------------


def test_una_sola_medicion_demo_muestra_sus_estadisticas_sinteticas_sin_tarjeta_experimental_vacia(db, scene):
    team, dev = scene["team"], scene["dev"]
    [patient] = newPatients(db, team, 1)
    demo(db, team, dev, patient, 97, 81, glucose=118)
    result = health(db, team.moderator, team)
    assert (result.demo.estado, result.demo.mediciones, result.demo.pacientes) == ("DISPONIBLE", 1, 1)
    assert (result.demo.spo2.promedio, result.demo.frecuenciaCardiaca.promedio, result.demo.glucosa.promedio) == (97.0, 81.0, 118.0)
    assert result.experimentales.estado == "SIN_DATOS" and result.experimentales.spo2 is None  # mensaje breve: no hay nada que promediar


def test_experimental_y_demo_nunca_comparten_promedio(db, scene):
    team, dev = scene["team"], scene["dev"]
    people = newPatients(db, team, 6)
    for patient in people[:5]:
        withGlucose(db, experimental(db, team, dev, patient, 94, 70), 100)
    demo(db, team, dev, people[5], 99, 100, glucose=200)
    result = health(db, team.owner, team)
    assert result.experimentales.estado == "DISPONIBLE" and result.experimentales.mediciones == 5
    assert (result.experimentales.spo2.promedio, result.experimentales.frecuenciaCardiaca.promedio, result.experimentales.glucosa.promedio) == (94.0, 70.0, 100.0)
    assert (result.demo.spo2.promedio, result.demo.glucosa.promedio) == (99.0, 200.0)  # cada origen con lo suyo


# --- Experimentales: mínimo de pacientes sobre el conjunto filtrado -----------------------------------------------------------------


def test_los_experimentales_con_menos_de_cinco_pacientes_quedan_protegidos_aunque_haya_datos(db, scene):
    team, dev = scene["team"], scene["dev"]
    people = newPatients(db, team, 5)
    for patient in people[:4]:
        experimental(db, team, dev, patient, 95, 70)
    group = health(db, team.moderator, team).experimentales
    assert group.estado == "PROTEGIDO" and "al menos 5 pacientes distintos" in group.motivo
    assert group.spo2 is None and group.mediciones == 0 and group.serieDiaria == []  # ningún valor, mínimo ni máximo
    experimental(db, team, dev, people[4], 96, 72)  # el quinto paciente distinto habilita el resultado
    assert health(db, team.moderator, team).experimentales.estado == "DISPONIBLE"


def test_cinco_mediciones_de_un_mismo_paciente_no_alcanzan_el_minimo(db, scene):
    team, dev = scene["team"], scene["dev"]
    [patient] = newPatients(db, team, 1)
    for _ in range(6):
        experimental(db, team, dev, patient, 95, 70)
    assert health(db, team.moderator, team).experimentales.estado == "PROTEGIDO"  # el mínimo es de pacientes distintos, no de mediciones


def test_el_minimo_se_evalua_sobre_el_conjunto_filtrado_y_su_complemento(db, scene):
    team, dev = scene["team"], scene["dev"]
    people = newPatients(db, team, 6)
    for patient in people[:5]:
        experimental(db, team, dev, patient, 95, 70)  # oximetría
    glucose = experimental(db, team, dev, people[5], 96, 72, modoMedicion="GLUCOSA_EXPERIMENTAL", origenGlucosa="EXPERIMENTAL", glucosaDispositivo=110, unidadGlucosa="mg/dL")
    assert glucose is not None
    assert health(db, team.moderator, team).experimentales.estado == "DISPONIBLE"  # 6 pacientes en total
    # Con el filtro de modo, cada parte quedaría con 5 y 1 pacientes: restar una de otra revelaría al sexto, así que ninguna se informa.
    assert health(db, team.moderator, team, modo="OXIMETRIA").experimentales.estado == "PROTEGIDO"
    assert health(db, team.moderator, team, modo="GLUCOSA_EXPERIMENTAL").experimentales.estado == "PROTEGIDO"


def test_el_periodo_se_aplica_a_los_resultados(db, scene):
    team, dev = scene["team"], scene["dev"]
    people = newPatients(db, team, 5)
    for patient in people:
        experimental(db, team, dev, patient, 95, 70, spo2=95)
    old = nowForDb() - timedelta(days=60)
    for patient in people:
        experimental(db, team, dev, patient, 80, 50, spo2=80, fechaHoraInicio=old, fechaHoraFin=old + timedelta(minutes=1))
    month = dashboards.institutionDashboard(db, team.owner, team.id, 30).saludAgregada.experimentales
    assert month.mediciones == 5 and month.spo2.promedio == 95.0
    quarter = dashboards.institutionDashboard(db, team.owner, team.id, 90).saludAgregada.experimentales
    assert quarter.mediciones == 10 and quarter.spo2.promedio == 87.5


# --- Filtros de origen, estado y operador --------------------------------------------------------------------------------------


def test_el_filtro_de_origen_deja_solo_el_grupo_pedido(db, scene):
    team, dev = scene["team"], scene["dev"]
    [patient] = newPatients(db, team, 1)
    demo(db, team, dev, patient, 97, 81)
    only = health(db, team.moderator, team, origen="DEMO")
    assert only.experimentales is None and only.demo.estado == "DISPONIBLE"
    assert health(db, team.moderator, team, origen="EXPERIMENTAL").demo is None


def test_un_filtro_de_estado_sin_resultados_se_explica_y_no_se_ignora(db, scene):
    team, dev = scene["team"], scene["dev"]
    [patient] = newPatients(db, team, 1)
    demo(db, team, dev, patient, 97, 81)
    result = health(db, team.moderator, team, estado="CANCELADA")
    for group in (result.experimentales, result.demo):
        assert group.estado == "NO_APLICA" and "solo con mediciones completadas" in group.motivo and group.spo2 is None
    assert result.filtros.estado == "CANCELADA"
    assert health(db, team.moderator, team, estado="COMPLETADA").demo.estado == "DISPONIBLE"


def test_con_filtro_de_operador_los_experimentales_no_se_desagregan_y_los_demo_si(db, scene):
    team, dev, second = scene["team"], scene["dev"], scene["second"]
    people = newPatients(db, team, 5)
    for patient in people:
        experimental(db, team, dev, patient, 95, 70)
    demo(db, team, dev, people[0], 97, 81)
    mine = relationOf(db, team, team.operator).idInstitucionUsuario
    result = health(db, team.moderator, team, operador=mine)
    assert result.experimentales.estado == "NO_APLICA" and "no se desagregan por operador" in result.experimentales.motivo
    assert result.demo.mediciones == 1  # sintético: sí se puede mirar por operador
    assert health(db, team.moderator, team, operador=second.idInstitucionUsuario).demo.estado == "SIN_DATOS"


# --- Campos registrados y «Sin informar» -----------------------------------------------------------------------------------------


def test_los_valores_faltantes_se_cuentan_como_sin_informar_y_no_como_cero(db, scene):
    team, dev = scene["team"], scene["dev"]
    people = newPatients(db, team, 5)
    for n, patient in enumerate(people):
        m = experimental(db, team, dev, patient, 95, 70)
        if n == 0:
            tune(db, m, spo2=None)
        if n >= 3:
            withGlucose(db, m, 100 + n)
    group = health(db, team.owner, team).experimentales
    assert group.sinInformar == {"spo2": 1, "frecuenciaCardiaca": 0, "glucosa": 3, "calidadSenal": 0}
    assert (group.spo2.cantidad, group.glucosa.cantidad, group.glucosa.promedio) == (4, 2, 103.5)  # solo los que registraron el valor


# --- Sin acceso individual ----------------------------------------------------------------------------------------------------------


def test_el_resultado_no_trae_pacientes_ni_valores_individuales_de_experimentales(db, scene):
    team, dev = scene["team"], scene["dev"]
    people = newPatients(db, team, 5)
    for patient in people:
        experimental(db, team, dev, patient, 95, 70)
    dumped = health(db, team.owner, team).model_dump_json()
    for secret in ("p0", "x0", "20110000", str(people[0].idPerfilMedicion), people[0].identificadorPseudonimo):
        assert secret not in dumped


def test_moderador_y_propietario_siguen_sin_acceso_a_mediciones_individuales_y_el_operador_conserva_el_suyo(db, scene):
    team, dev = scene["team"], scene["dev"]
    [patient] = newPatients(db, team, 1)
    experimental(db, team, dev, patient, 95, 70)
    for actor in (team.moderator, team.owner):
        expectError("MEDICIONES_NO_AUTORIZADAS", measurements.listPatientHistory, db, actor, team.id, patient.idPerfilMedicion)
    assert measurements.listPatientHistory(db, team.operator, team.id, patient.idPerfilMedicion).total == 1  # el operador responsable, sí


def test_un_filtro_invalido_se_rechaza(db, scene):
    team = scene["team"]
    expectError("DATOS_INVALIDOS", dashboards.institutionDashboard, db, team.moderator, team.id, 30, modo="OTRO")
    expectError("DATOS_INVALIDOS", dashboards.institutionDashboard, db, team.moderator, team.id, 30, origen="OTRO")
