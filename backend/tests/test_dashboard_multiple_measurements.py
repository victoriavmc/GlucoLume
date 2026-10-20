# El dashboard institucional (moderador y propietario) cuenta TODAS las mediciones y los pacientes ÚNICOS por separado: cinco pacientes con tres
# mediciones cada uno son cinco pacientes y quince mediciones; varias mediciones de una persona el mismo día no se pisan ni se pierden; las DEMO
# alimentan sus propios resultados; las canceladas no generan resultados de salud; los permisos no cambian.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_dashboard_multiple_measurements.py -v

from datetime import timedelta

from sqlalchemy import func, select, update

from app.models.measurement import Measurement
from app.models.user import User
from app.services import dashboard as dashboards
from app.services import institutionPatients as patients
from app.services import measurement as measurements
from app.services import profileTransfers as transfers
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import audits, db, engine, mails, reload  # noqa: F401
from tests.test_dashboards import institutionData, measure
from tests.test_health_aggregates import demo, experimental, health, newPatients, tune, withGlucose
from tests.test_institution_patients import patientData
from tests.test_institutions import expectError, freshLookupLimiter, relationOf, team  # noqa: F401
from tests.test_measurements import device  # noqa: F401


def stats(db, actor, team, **filters):
    return dashboards.institutionDashboard(db, actor, team.id, 30, **filters).administrativo


def bands(result):
    return {(b.desde, b.hasta): b.pacientes for b in result.pacientesPorCantidad}


def today(hour):
    return nowForDb().replace(hour=hour, minute=0, second=0, microsecond=0)


def scene(db, team):
    _, _, dev = institutionData(db, team)
    return dev


# --- 1-3. Pacientes únicos y mediciones ------------------------------------------------------------------------------------------


def test_cinco_pacientes_con_tres_mediciones_cada_uno_son_cinco_pacientes_y_quince_mediciones(db, team):
    dev = scene(db, team)
    people = newPatients(db, team, 5)
    for patient in people:
        for hour in (10, 14, 20):  # tres mediciones el MISMO día
            m = experimental(db, team, dev, patient, 95, 70)
            tune(db, m, fechaHoraInicio=today(hour), fechaHoraFin=today(hour) + timedelta(minutes=1))
    kpis = stats(db, team.moderator, team).kpis
    assert (kpis.total, kpis.completadas, kpis.pacientesActivos, kpis.pacientesConMediciones) == (15, 15, 5, 5)
    assert bands(stats(db, team.moderator, team))[(2, 3)] == 5  # cinco pacientes aportan 2 o 3 mediciones
    [day] = stats(db, team.moderator, team).serie
    assert day.completadas == 15  # el mismo día no pisa nada: las 15 suman en esa fecha
    assert health(db, team.moderator, team).experimentales.mediciones == 15


def test_un_paciente_con_tres_mediciones_el_mismo_dia_conserva_las_tres(db, team):
    dev = scene(db, team)
    [patient] = newPatients(db, team, 1)
    for hour, mode in ((10, "OXIMETRIA"), (14, "GLUCOSA_EXPERIMENTAL"), (20, "OXIMETRIA")):
        m = experimental(db, team, dev, patient, 95, 70)
        extra = {"origenGlucosa": "EXPERIMENTAL", "glucosaDispositivo": 105, "unidadGlucosa": "mg/dL"} if mode == "GLUCOSA_EXPERIMENTAL" else {}
        tune(db, m, fechaHoraInicio=today(hour), fechaHoraFin=today(hour) + timedelta(minutes=1), modoMedicion=mode, **extra)
    result = stats(db, team.owner, team)
    assert (result.kpis.total, result.kpis.pacientesConMediciones) == (3, 1)
    assert [(d.completadas, d.experimentales) for d in result.serie] == [(3, 3)]
    assert {m.modo: m.total for m in result.porModo} == {"OXIMETRIA": 2, "GLUCOSA_EXPERIMENTAL": 1}
    # El total coincide con el historial del paciente (que ve su operador responsable) y con los registros guardados.
    assert measurements.listPatientHistory(db, team.operator, team.id, patient.idPerfilMedicion).total == 3
    assert db.scalar(select(func.count()).select_from(Measurement).where(Measurement.idPerfilMedicion == patient.idPerfilMedicion)) == 3


def test_cinco_pacientes_con_cantidades_distintas_y_un_activo_sin_mediciones(db, team):
    dev = scene(db, team)
    people = newPatients(db, team, 6)
    for patient, amount in zip(people[:5], (1, 2, 3, 4, 6)):
        for _ in range(amount):
            experimental(db, team, dev, patient, 95, 70)
    result = stats(db, team.moderator, team)
    assert (result.kpis.total, result.kpis.pacientesConMediciones, result.kpis.pacientesActivos) == (16, 5, 6)
    assert bands(result) == {(0, 0): 1, (1, 1): 1, (2, 3): 2, (4, 5): 1, (6, None): 1}  # el sexto paciente activo no tiene mediciones
    total = sum(measurements.listPatientHistory(db, team.operator, team.id, p.idPerfilMedicion).total for p in people)
    assert total == result.kpis.total  # el dashboard coincide con la suma de los historiales


# --- 4-5. DEMO y experimentales --------------------------------------------------------------------------------------------------


def test_solo_demo_alimenta_sus_propios_resultados_con_alimentacion_y_calidad(db, team):
    dev = scene(db, team)
    people = newPatients(db, team, 5)
    for n, patient in enumerate(people):
        m = demo(db, team, dev, patient, 97, 80, glucose=100 + n)
        tune(db, m, condicionComida="AYUNO" if n < 3 else "NO_INFORMADA", calidadSenal=0.8 if n < 4 else None)
    result = health(db, team.moderator, team)
    assert result.experimentales.estado == "SIN_DATOS"  # ningún experimental…
    group = result.demo  # …pero las DEMO muestran sus estadísticas sintéticas
    assert (group.estado, group.mediciones, group.pacientes) == ("DISPONIBLE", 5, 5)
    assert (group.glucosa.promedio, group.glucosa.cantidad) == (102.0, 5)
    assert group.alimentacion == {"AYUNO": 3, "NO_INFORMADA": 2}
    assert (group.calidadSenal.cantidad, group.calidadSenal.promedio, group.sinInformar["calidadSenal"]) == (4, 0.8, 1)
    assert group.spo2.cantidad == 5 and group.frecuenciaCardiaca.cantidad == 5  # la falta de calidadSenal en una no impide las demás variables
    admin = stats(db, team.moderator, team)
    assert (admin.kpis.demo, admin.kpis.experimentales) == (5, 0)
    assert {f.condicion: f.total for f in admin.porAlimentacion} == {"AYUNO": 3, "NO_INFORMADA": 2}


def test_demo_y_experimentales_mezcladas_se_cuentan_juntas_pero_se_promedian_por_separado(db, team):
    dev = scene(db, team)
    people = newPatients(db, team, 5)
    for patient in people:
        withGlucose(db, experimental(db, team, dev, patient, 94, 70), 90)
        demo(db, team, dev, patient, 99, 100, glucose=200)
    admin = stats(db, team.owner, team)
    assert (admin.kpis.total, admin.kpis.experimentales, admin.kpis.demo, admin.kpis.pacientesConMediciones) == (10, 5, 5, 5)  # 5 pacientes, 10 mediciones
    result = health(db, team.owner, team)
    assert (result.experimentales.glucosa.promedio, result.demo.glucosa.promedio) == (90.0, 200.0)
    assert result.experimentales.mediciones == 5 and result.demo.mediciones == 5


# --- 6-7. Canceladas y valores faltantes ------------------------------------------------------------------------------------------


def test_las_canceladas_cuentan_como_actividad_pero_no_generan_resultados_de_salud(db, team):
    dev = scene(db, team)
    patient, other = newPatients(db, team, 2)
    demo(db, team, dev, other, 97, 80)
    cancelled = measure(db, team.operator, patient.idPerfilMedicion, dev, "90", 60)
    tune(db, cancelled, estadoMedicion="CANCELADA", fechaHoraFin=nowForDb() + timedelta(minutes=1), spo2=None, frecuenciaCardiaca=None)
    admin = stats(db, team.moderator, team)
    assert (admin.kpis.total, admin.kpis.canceladas, admin.kpis.sinResultado, admin.kpis.pacientesConMediciones) == (2, 1, 1, 2)
    result = health(db, team.moderator, team)
    assert result.demo.mediciones == 1 and result.experimentales.estado == "SIN_DATOS"  # la cancelada no aporta ni un valor


def test_registros_sin_ciertos_valores_no_se_cuentan_como_cero(db, team):
    dev = scene(db, team)
    [patient] = newPatients(db, team, 1)
    m = demo(db, team, dev, patient, 97, 80)
    tune(db, m, spo2=None, frecuenciaCardiaca=None, condicionComida="NO_INFORMADA", calidadSenal=None)
    group = health(db, team.moderator, team).demo
    assert group.spo2.cantidad == 0 and group.spo2.promedio is None and group.glucosa.cantidad == 1
    assert group.sinInformar == {"spo2": 1, "frecuenciaCardiaca": 1, "glucosa": 0, "calidadSenal": 1}


# --- 8. Pacientes transferidos --------------------------------------------------------------------------------------------------


def test_las_mediciones_de_un_paciente_transferido_siguen_contando_una_vez_y_con_su_autor(db, team):
    second, secondUser, dev = institutionData(db, team)
    [patient] = newPatients(db, team, 1)
    experimental(db, team, dev, patient, 95, 70)
    experimental(db, team, dev, patient, 96, 72)
    before = stats(db, team.moderator, team)
    patients.assignResponsible(db, team.moderator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario)  # propuesta
    from app.models.profileTransfer import ProfileTransfer
    transfer = db.scalar(select(ProfileTransfer).where(ProfileTransfer.estado == "PENDIENTE"))
    transfers.acceptTransfer(db, secondUser, team.id, transfer.idTransferenciaPerfil)
    experimental_ = measure(db, secondUser, patient.idPerfilMedicion, dev, "97", 75)  # el nuevo responsable mide
    assert experimental_ is not None
    after = stats(db, team.moderator, team)
    assert (before.kpis.total, before.kpis.pacientesConMediciones) == (2, 1)
    assert (after.kpis.total, after.kpis.pacientesConMediciones) == (3, 1)  # un paciente, tres mediciones
    byOperator = {o.idInstitucionUsuario: o.total for o in after.porOperador}
    assert byOperator[relationOf(db, team, team.operator).idInstitucionUsuario] == 2  # lo anterior sigue siendo del primer operador
    assert byOperator[second.idInstitucionUsuario] == 1


# --- 9-10. Pacientes sin mediciones y permisos -----------------------------------------------------------------------------------


def test_pacientes_sin_mediciones_no_inventan_actividad(db, team):
    scene(db, team)
    newPatients(db, team, 3)
    admin = stats(db, team.moderator, team)
    assert (admin.kpis.total, admin.kpis.pacientesActivos, admin.kpis.pacientesConMediciones) == (0, 3, 0)
    assert bands(admin)[(0, 0)] == 3 and admin.porAlimentacion == [] and admin.serie == []
    group = health(db, team.moderator, team)
    assert group.experimentales.estado == "SIN_DATOS" and group.demo.estado == "SIN_DATOS"


def test_permisos_y_privacidad_del_dashboard_institucional(db, team):
    dev = scene(db, team)
    [patient] = newPatients(db, team, 1)
    demo(db, team, dev, patient, 97, 80)
    for actor in (team.moderator, team.owner):
        dumped = dashboards.institutionDashboard(db, actor, team.id, 30).model_dump_json()
        for secret in ("p0", "x0", "20110000", str(patient.idPerfilMedicion), patient.identificadorPseudonimo):
            assert secret not in dumped  # ningún dato de pacientes en los agregados
        expectError("MEDICIONES_NO_AUTORIZADAS", measurements.listPatientHistory, db, actor, team.id, patient.idPerfilMedicion)
    expectError("PERMISO_INSUFICIENTE", dashboards.institutionDashboard, db, team.operator, team.id, 30)  # el operador usa su propia vista
    assert measurements.listPatientHistory(db, team.operator, team.id, patient.idPerfilMedicion).total == 1


# --- Resultados DEMO agregados: puntos por medición y promedio diario con sus observaciones ----------------------------------------


def _thirteen(db, team, dev):
    """13 mediciones DEMO de 5 pacientes (3, 3, 3, 2, 2) repartidas en dos días, varias del mismo paciente el mismo día."""
    people = newPatients(db, team, 5)
    plan = [(0, 0, 9, 100, 96, 70), (0, 0, 13, 110, 97, 72), (0, 1, 10, 120, 95, 80), (1, 0, 11, 105, 98, 75), (1, 1, 12, 115, 94, 78),
            (1, 1, 18, 125, 96, 82), (2, 0, 14, 130, 97, 68), (2, 1, 9, 95, 99, 66), (2, 1, 15, 90, 98, 71), (3, 0, 16, 108, 95, 90),
            (3, 1, 17, 112, 96, 88), (4, 0, 19, 118, 97, 76), (4, 1, 20, 122, 93, 84)]
    day0 = (nowForDb() - timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    for who, offset, hour, glucose, spo2, rate in plan:
        m = demo(db, team, dev, people[who], 97, 80, glucose=glucose)
        moment = (day0 + timedelta(days=offset)).replace(hour=hour)
        tune(db, m, spo2=spo2, frecuenciaCardiaca=rate, fechaHoraInicio=moment, fechaHoraFin=moment + timedelta(minutes=1))
    return plan


def test_trece_mediciones_demo_de_cinco_pacientes_conservan_cada_punto_y_los_promedios_diarios_cuentan_todo(db, team):
    dev = scene(db, team)
    plan = _thirteen(db, team, dev)
    group = health(db, team.moderator, team).demo
    assert (group.mediciones, group.pacientes, len(group.puntos)) == (13, 5, 13)  # nada se deduplica por paciente y fecha
    assert [p.fecha for p in group.puntos] == sorted(p.fecha for p in group.puntos)
    assert sorted(p.glucosa for p in group.puntos) == sorted(float(g) for _, _, _, g, _, _ in plan)  # cada valor tal cual, sin promediar
    assert len(group.serieDiaria) == 2 and sum(d.mediciones for d in group.serieDiaria) == 13
    first, second = group.serieDiaria
    expected = [g for _, off, _, g, _, _ in plan if off == 0]
    assert (first.glucosaN, first.glucosaPromedio) == (len(expected), round(sum(expected) / len(expected), 1))
    assert first.glucosaN + second.glucosaN == 13 and first.spo2N + second.spo2N == 13
    assert (group.glucosa.promedio, group.glucosa.minimo, group.glucosa.maximo, group.glucosa.cantidad) == (
        round(sum(g for _, _, _, g, _, _ in plan) / 13, 1), 90.0, 130.0, 13)
    assert group.porModo == {"OXIMETRIA": 13}


def test_una_sola_medicion_demo_da_un_punto_y_un_dia_con_una_observacion(db, team):
    dev = scene(db, team)
    [patient] = newPatients(db, team, 1)
    demo(db, team, dev, patient, 97, 81, glucose=118)
    group = health(db, team.moderator, team).demo
    assert len(group.puntos) == 1 and group.puntos[0].glucosa == 118.0
    assert [(d.mediciones, d.glucosaN, d.glucosaPromedio) for d in group.serieDiaria] == [(1, 1, 118.0)]


def test_los_valores_ausentes_no_se_vuelven_cero_en_puntos_ni_en_promedios_diarios(db, team):
    dev = scene(db, team)
    a, b = newPatients(db, team, 2)
    tune(db, demo(db, team, dev, a, 97, 80, glucose=100), spo2=None)
    tune(db, demo(db, team, dev, b, 97, 80, glucose=120), spo2=96, frecuenciaCardiaca=None)
    group = health(db, team.moderator, team).demo
    assert sorted(p.spo2 for p in group.puntos if p.spo2 is not None) == [96.0] and sum(p.spo2 is None for p in group.puntos) == 1
    [day] = group.serieDiaria
    assert (day.mediciones, day.spo2N, day.spo2Promedio, day.frecuenciaN) == (2, 1, 96.0, 1)  # el promedio solo usa lo registrado


def test_demo_y_experimentales_mezclados_solo_exponen_puntos_individuales_de_las_demo(db, team):
    dev = scene(db, team)
    people = newPatients(db, team, 5)
    for patient in people:
        withGlucose(db, experimental(db, team, dev, patient, 94, 70), 90)
    demo(db, team, dev, people[0], 99, 100, glucose=200)
    result = health(db, team.owner, team)
    assert result.experimentales.puntos == []  # un punto experimental sería el resultado de salud de una persona
    assert [p.glucosa for p in result.demo.puntos] == [200.0]
    assert result.experimentales.glucosa.promedio == 90.0 and result.demo.glucosa.promedio == 200.0
    assert result.experimentales.porModo == {"OXIMETRIA": 5}


def test_los_puntos_demo_no_identifican_paciente_operador_ni_medicion(db, team):
    dev = scene(db, team)
    [patient] = newPatients(db, team, 1)
    m = demo(db, team, dev, patient, 97, 81, glucose=118)
    dumped = health(db, team.moderator, team).demo.model_dump_json()
    for secret in (str(m.idMedicion), str(patient.idPerfilMedicion), patient.identificadorPseudonimo):
        assert secret not in dumped
    assert set(health(db, team.moderator, team).demo.puntos[0].model_dump()) == {"fecha", "glucosa", "spo2", "frecuenciaCardiaca"}
