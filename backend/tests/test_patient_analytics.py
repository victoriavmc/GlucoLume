# Dashboard analítico de pacientes y mediciones del operador (services/patientAnalytics.py).
#
# Se prueba con datos sintéticos: alcance estricto del operador, aislamiento entre instituciones, DEMO vs experimental sin mezclar, datos
# ausentes («Sin informar», nunca 0), pacientes únicos vs mediciones, filtros combinados y coherencia entre KPIs, tablas y gráficos.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_patient_analytics.py -v

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import update

from app.models.measurement import Measurement
from app.schemas.patientAnalytics import SIN_INFORMAR
from app.services import institutionPatients as patients
from app.services import measurement as measurements
from app.services import patientAnalytics as analytics
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import audits, db, engine, mails, reload  # noqa: F401
from tests.test_dashboards import institutionData, measure
from tests.test_institution_patients import otherInstitution, patientData
from tests.test_institutions import expectError, freshLookupLimiter, team  # noqa: F401
from tests.test_measurements import device  # noqa: F401


def tune(db, idMedicion, **values):
    db.execute(update(Measurement).where(Measurement.idMedicion == idMedicion).values(**values))
    db.commit()


def demo(db, idMedicion, glucose=114):
    tune(db, idMedicion, origenGlucosa="DEMO", glucosaDispositivo=glucose, unidadGlucosa="mg/dL")


def glucoseMode(db, idMedicion, glucose=118):
    tune(db, idMedicion, modoMedicion="GLUCOSA_EXPERIMENTAL", origenGlucosa="EXPERIMENTAL", glucosaDispositivo=glucose, unidadGlucosa="mg/dL")


def get(db, actor, team, **filters):
    """Las pruebas heredadas parten de «solo experimentales, solo completadas»; los valores por defecto reales se prueban aparte."""
    filters.setdefault("origen", "EXPERIMENTAL")
    filters.setdefault("estado", "COMPLETADA")
    return analytics.analyze(db, actor, team.id, **filters)


def by(items, key="categoria"):
    return {getattr(item, key): item for item in items}


@pytest.fixture
def scene(db, mails, team):
    """Operador Juan (team.operator) con tres pacientes y María (segunda operadora) con uno; todos con mediciones sintéticas."""
    second, secondUser, dev = institutionData(db, team)
    full = patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz", dni="20111222", fechaNacimiento="1990-06-01", sexoModelo="femenino"))
    noData = patients.createPatient(db, team.operator, team.id, patientData(nombre="luis", apellido="paz", dni="30111222", fechaNacimiento=None, sexoModelo=None))
    idle = patients.createPatient(db, team.operator, team.id, patientData(nombre="ana", apellido="gil", dni="40111222", fechaNacimiento="2015-01-01", sexoModelo="femenino"))
    foreign = patients.createPatient(db, secondUser, team.id, patientData(nombre="beto", apellido="ríos", dni="50111222"))
    ids = {}
    ids["full1"] = measure(db, team.operator, full.idPerfilMedicion, dev, "96", 70).idMedicion
    ids["full2"] = measure(db, team.operator, full.idPerfilMedicion, dev, "98", 80).idMedicion
    ids["full3"] = measure(db, team.operator, full.idPerfilMedicion, dev, "94", 90).idMedicion
    ids["nodata"] = measure(db, team.operator, noData.idPerfilMedicion, dev, "92", 60).idMedicion
    ids["foreign"] = measure(db, secondUser, foreign.idPerfilMedicion, dev, "85", 100).idMedicion
    # full1: oximetría con glucosa del dispositivo (experimental), en ayunas; full2: modo glucosa experimental, postprandial;
    # full3: DEMO; nodata: sin alimentación informada, sin edad al momento y con la glucosa ausente.
    tune(db, ids["full1"], condicionComida="AYUNO", edadAlMomento=35, calidadSenal=2.5, origenGlucosa="EXPERIMENTAL", glucosaDispositivo=101, unidadGlucosa="mg/dL")
    glucoseMode(db, ids["full2"], 118)
    tune(db, ids["full2"], condicionComida="POSTPRANDIAL", edadAlMomento=35, calidadSenal=4.5)
    demo(db, ids["full3"], 130)
    tune(db, ids["full3"], edadAlMomento=35)
    tune(db, ids["nodata"], edadAlMomento=None, spo2=None, calidadSenal=None)
    return {"team": team, "second": secondUser, "dev": dev, "patients": {"full": full, "nodata": noData, "idle": idle, "foreign": foreign}, "ids": ids}


# --- Alcance y permisos -----------------------------------------------------------------------------------------------------------


def test_el_operador_solo_ve_sus_pacientes_activos_y_sus_mediciones(db, scene):
    data = get(db, scene["team"].operator, scene["team"])
    assert data.kpis.pacientesEnAlcance == 3 and data.pacientes.total == 3  # el de María no aparece
    assert data.kpis.pacientesConMediciones == 2  # Rosa y Luis; Ana no tiene mediciones
    assert data.kpis.totalMediciones == 3  # por defecto sin DEMO: full1, full2, nodata
    names = {row.identificadorPseudonimo for row in data.pacientes.items}
    assert scene["patients"]["foreign"].identificadorPseudonimo not in names


def test_propietario_y_moderador_no_acceden_a_mediciones_individuales_por_su_rol(db, scene):
    for actor in (scene["team"].owner, scene["team"].moderator):
        expectError("MEDICIONES_NO_AUTORIZADAS", get, db, actor, scene["team"])
    assert [a for a in audits(db, "CONSULTAR_ANALISIS_PACIENTES") if a.resultado != "EXITO"]  # el intento queda auditado, sin valores


def test_un_operador_no_puede_elegir_a_un_paciente_de_otro_operador(db, scene):
    foreign = scene["patients"]["foreign"].idPerfilMedicion
    expectError("MEDICIONES_NO_AUTORIZADAS", get, db, scene["team"].operator, scene["team"], idPerfilMedicion=foreign)
    mine = get(db, scene["second"], scene["team"])
    assert mine.kpis.pacientesEnAlcance == 1 and mine.kpis.totalMediciones == 1  # María ve solo lo suyo


def test_aislamiento_entre_instituciones(db, scene):
    other, otherOperator, _ = otherInstitution(db)
    expectError("INSTITUCION_NO_ENCONTRADA", analytics.analyze, db, scene["team"].operator, other.idInstitucion)
    own = analytics.analyze(db, otherOperator, other.idInstitucion)
    assert own.kpis.pacientesEnAlcance == 0 and own.kpis.totalMediciones == 0  # nada de la otra institución


def test_un_paciente_dado_de_baja_sale_del_alcance(db, scene):
    patients.dischargePatient(db, scene["team"].owner, scene["team"].id, scene["patients"]["nodata"].idPerfilMedicion)
    data = get(db, scene["team"].operator, scene["team"])
    assert data.kpis.pacientesEnAlcance == 2 and data.kpis.totalMediciones == 2
    expectError("MEDICIONES_NO_AUTORIZADAS", get, db, scene["team"].owner, scene["team"])


# --- DEMO vs experimental ---------------------------------------------------------------------------------------------------------


def test_por_defecto_excluye_demo_y_todas_las_fuentes_separa_los_subtotales(db, scene):
    team = scene["team"]
    default = get(db, team.operator, team)
    assert default.kpis.demo == 0 and default.kpis.experimentales == 3 and [s.origen for s in default.variable.series] == ["EXPERIMENTAL"]
    only = get(db, team.operator, team, origen="DEMO")
    assert only.kpis.totalMediciones == 1 and only.kpis.demo == 1 and only.kpis.experimentales == 0
    both = get(db, team.operator, team, origen="TODOS")
    assert both.kpis.totalMediciones == 4 and both.kpis.experimentales == 3 and both.kpis.demo == 1
    assert [s.origen for s in both.variable.series] == ["EXPERIMENTAL", "DEMO"]  # series separadas, nunca una población mezclada
    assert sum(item.mediciones for item in both.porModoOrigen) == both.kpis.totalMediciones


def test_el_promedio_no_mezcla_demo_con_experimental(db, scene):
    data = get(db, scene["team"].operator, scene["team"], origen="TODOS", variable="glucosaDispositivo")
    series = {s.origen: s for s in data.variable.series}
    assert series["EXPERIMENTAL"].resumen.n == 2 and series["EXPERIMENTAL"].resumen.promedio == pytest.approx((101 + 118) / 2)
    assert series["DEMO"].resumen.n == 1 and series["DEMO"].resumen.promedio == 130  # el valor sintético queda aparte


# --- Datos incompletos ------------------------------------------------------------------------------------------------------------


def test_los_pacientes_sin_datos_siguen_contando_como_sin_informar(db, scene):
    data = get(db, scene["team"].operator, scene["team"])
    sexes = by(data.sexo)
    assert sexes["FEMENINO"].pacientes == 2 and sexes["MASCULINO"].pacientes == 0 and sexes[SIN_INFORMAR].pacientes == 1
    assert sum(b.pacientes for b in data.sexo) == data.kpis.pacientesEnAlcance  # nadie desaparece
    ages = by(data.edades)
    assert (ages["31-50"].pacientes, ages["0-12"].pacientes, ages[SIN_INFORMAR].pacientes) == (1, 1, 1)  # Rosa (36), Ana (11) y Luis (sin fecha)
    assert sum(b.pacientes for b in data.edades) == data.kpis.pacientesEnAlcance
    assert sexes[SIN_INFORMAR].conMediciones == 1 and sexes["FEMENINO"].conMediciones == 1  # Ana no tiene mediciones


def test_los_valores_ausentes_no_son_cero_y_no_entran_en_el_promedio(db, scene):
    data = get(db, scene["team"].operator, scene["team"], variable="spo2")
    summary = data.variable.series[0].resumen
    assert summary.n == 2  # la medición de Luis no tiene SpO₂: no aporta ni como 0
    assert summary.promedio == pytest.approx((96 + 98) / 2, abs=0.3) and summary.minimo > 90
    missing = {m.campo: m for m in data.kpis.faltantes}
    assert missing["spo2"].sinDato == 1 and missing["spo2"].sobre == 3
    assert missing["glucosa"].sinDato == 1 and missing["alimentacion"].sinDato == 1 and missing["edadAlMomento"].sinDato == 1
    # Una medición sin glucosa (la de Luis) sigue aportando a la frecuencia cardíaca.
    assert get(db, scene["team"].operator, scene["team"], variable="frecuenciaCardiaca").variable.series[0].resumen.n == 3


def test_alimentacion_desconocida_no_se_interpreta_como_ayuno(db, scene):
    foods = {c.categoria: c.mediciones for c in get(db, scene["team"].operator, scene["team"]).alimentacion}
    assert foods == {"AYUNO": 1, "POSTPRANDIAL": 1, "NO_INFORMADA": 1}
    fasting = get(db, scene["team"].operator, scene["team"], alimentacion="AYUNO")
    assert fasting.kpis.totalMediciones == 1  # «no informada» no entra al filtro de ayuno


def test_oximetria_y_glucosa_traen_todas_sus_variables(db, scene):
    team = scene["team"]
    glucose = get(db, team.operator, team, variable="glucosaDispositivo")
    assert glucose.variable.series[0].resumen.n == 2  # una oximetría CON glucosa y una medición de glucosa
    spo2 = get(db, team.operator, team, variable="spo2")
    assert spo2.variable.series[0].resumen.n == 2 and any(m == "GLUCOSA_EXPERIMENTAL" for m in [p.modo for p in get(db, team.operator, team, idPerfilMedicion=scene["patients"]["full"].idPerfilMedicion).paciente.puntos])
    assert get(db, team.operator, team, modo="GLUCOSA_EXPERIMENTAL").kpis.totalMediciones == 1  # el modo se diferencia siempre


# --- Pacientes únicos vs mediciones, filtros y coherencia -------------------------------------------------------------------------


def test_pacientes_unicos_no_se_confunden_con_mediciones(db, scene):
    data = get(db, scene["team"].operator, scene["team"], origen="TODOS")
    assert data.kpis.totalMediciones == 4 and data.kpis.pacientesConMediciones == 2
    rows = by(data.pacientes.items, "identificadorPseudonimo")
    rosa = rows[scene["patients"]["full"].identificadorPseudonimo]
    assert rosa.medicionesExperimentales == 2 and rosa.medicionesDemo == 1
    assert sum(r.medicionesExperimentales + r.medicionesDemo for r in data.pacientes.items) == data.kpis.totalMediciones


def test_filtros_combinados_y_coherencia_entre_kpis_tablas_y_graficos(db, scene):
    team = scene["team"]
    data = get(db, team.operator, team, sexo="FEMENINO", modo="GLUCOSA_EXPERIMENTAL", alimentacion="POSTPRANDIAL", origen="TODOS")
    assert data.kpis.totalMediciones == 1 and data.kpis.pacientesEnAlcance == 2  # Rosa y Ana son FEMENINO; solo Rosa mide así
    assert sum(point.experimentales + point.demo for point in data.evolucion) == data.kpis.totalMediciones
    assert data.kpis.porModo == {"OXIMETRIA": 0, "GLUCOSA_EXPERIMENTAL": 1}
    none = get(db, team.operator, team, sexo="MASCULINO")
    assert none.kpis.pacientesEnAlcance == 0 and none.kpis.totalMediciones == 0 and none.pacientes.total == 0  # sin pacientes: vacío, no error
    unknown = get(db, team.operator, team, sexo=SIN_INFORMAR)
    assert unknown.kpis.pacientesEnAlcance == 1 and unknown.kpis.totalMediciones == 1


def test_edad_actual_y_edad_al_momento_son_filtros_distintos(db, scene):
    team = scene["team"]
    today = get(db, team.operator, team, edad="0-12", edadBase="ACTUAL")  # Ana (2015) tiene hoy menos de 13 años y no tiene mediciones
    assert today.kpis.pacientesEnAlcance == 1 and today.kpis.totalMediciones == 0
    atMeasurement = get(db, team.operator, team, edad="31-50", edadBase="MEDICION")  # Rosa tenía 35 al medir
    assert atMeasurement.kpis.totalMediciones == 2
    unknownAge = get(db, team.operator, team, edad=SIN_INFORMAR, edadBase="MEDICION")
    assert unknownAge.kpis.totalMediciones == 1  # la de Luis, sin edad al momento


def test_periodo_y_calidad_de_senal(db, scene):
    team = scene["team"]
    tune(db, scene["ids"]["full1"], fechaHoraInicio=nowForDb() - timedelta(days=60))
    assert get(db, team.operator, team, dias=30).kpis.totalMediciones == 2
    assert get(db, team.operator, team, dias=90).kpis.totalMediciones == 3
    quality = get(db, team.operator, team, dias=90).calidad
    assert quality.conValor == 2 and quality.sinInformar == 1  # la de Luis no registró calidad
    assert sum(r.mediciones for r in quality.rangos) == quality.conValor  # rangos del valor observado, sin umbrales inventados
    assert get(db, team.operator, team, dias=90, calidad="CON_DATO").kpis.totalMediciones == 2


def test_evolucion_por_semana_y_mes_suma_lo_mismo(db, scene):
    team = scene["team"]
    totals = {g: sum(p.experimentales + p.demo for p in get(db, team.operator, team, granularidad=g, origen="TODOS").evolucion) for g in ("dia", "semana", "mes")}
    assert set(totals.values()) == {4}


def test_el_detalle_de_un_paciente_trae_sus_puntos_reales_y_la_matriz_es_opcional(db, scene):
    team = scene["team"]
    rosa = scene["patients"]["full"]
    data = get(db, team.operator, team, idPerfilMedicion=rosa.idPerfilMedicion, origen="TODOS", variable="glucosaDispositivo")
    detail = data.paciente
    assert detail.identificadorPseudonimo == rosa.identificadorPseudonimo and detail.nombre == "Rosa" and detail.sexoModelo == "FEMENINO"
    assert len(detail.puntos) == 3 and [p.origen for p in detail.puntos].count("DEMO") == 1
    assert all(p.referencia is None for p in detail.puntos)  # la matriz solo se compara si se pide
    assert data.kpis.pacientesEnAlcance == 1
    compared = get(db, team.operator, team, idPerfilMedicion=rosa.idPerfilMedicion, variable="glucosaDispositivo", compararMatriz=True).paciente
    assert next(p for p in compared.puntos if p.modo == "GLUCOSA_EXPERIMENTAL").referencia is not None  # solo la medición de glucosa
    assert all(p.referencia is None for p in compared.puntos if p.modo == "OXIMETRIA")  # nunca a las oximetrías


def test_la_tabla_se_pagina_y_filtros_invalidos_se_rechazan(db, scene):
    page = get(db, scene["team"].operator, scene["team"], pagina=2, tamanioPagina=2)
    assert page.pacientes.total == 3 and len(page.pacientes.items) == 1 and page.pacientes.pagina == 2
    for bad in ({"sexo": "X"}, {"edad": "200"}, {"origen": "OTRO"}, {"variable": "peso"}, {"estado": "NADA"}, {"granularidad": "hora"}):
        expectError("DATOS_INVALIDOS", get, db, scene["team"].operator, scene["team"], **bad)
    expectError("PACIENTE_NO_ENCONTRADO", get, db, scene["team"].operator, scene["team"], idPerfilMedicion=uuid.uuid4())


# --- Segmentación, rangos de edad configurables y comparación con la matriz -------------------------------------------------------


def test_la_segmentacion_separa_origen_y_cuenta_observaciones_validas(db, scene):
    team = scene["team"]
    rows = get(db, team.operator, team, segmentar="MODO", origen="TODOS", variable="glucosaDispositivo").segmentacion
    table = {(r.categoria, r.origen): r for r in rows}
    assert table[("OXIMETRIA", "EXPERIMENTAL")].mediciones == 2 and table[("OXIMETRIA", "EXPERIMENTAL")].n == 1  # Luis no tiene glucosa
    assert table[("GLUCOSA_EXPERIMENTAL", "EXPERIMENTAL")].promedio == 118
    assert sum(r.mediciones for r in rows) == 4  # coincide con el KPI: DEMO queda en su propia fila
    sex = get(db, team.operator, team, segmentar="SEXO").segmentacion
    assert {r.categoria for r in sex} == {"FEMENINO", SIN_INFORMAR} and sum(r.mediciones for r in sex) == 3
    food = {r.categoria: r.mediciones for r in get(db, team.operator, team, segmentar="ALIMENTACION").segmentacion}
    assert food == {"AYUNO": 1, "POSTPRANDIAL": 1, SIN_INFORMAR: 1}  # desconocida ≠ ayuno
    assert get(db, team.operator, team).segmentacion == []
    expectError("DATOS_INVALIDOS", get, db, team.operator, team, segmentar="PESO")


def test_segmentar_por_dispositivo_y_origen(db, scene):
    team = scene["team"]
    devices = get(db, team.operator, team, segmentar="DISPOSITIVO").segmentacion
    assert sum(r.mediciones for r in devices) == 3 and all(r.origen == "EXPERIMENTAL" for r in devices)
    origin = {(r.categoria, r.origen): r.mediciones for r in get(db, team.operator, team, segmentar="ORIGEN", origen="TODOS").segmentacion}
    assert origin == {("EXPERIMENTAL", "EXPERIMENTAL"): 3, ("DEMO", "DEMO"): 1}


def test_rangos_de_edad_configurables(db, scene):
    team = scene["team"]
    custom = get(db, team.operator, team, edadCortes="40", edad="0-40", edadBase="MEDICION")
    assert custom.rangosEdad == ["0-40", "41+", SIN_INFORMAR] and custom.kpis.totalMediciones == 2  # Rosa tenía 35 al medir
    assert [b.categoria for b in custom.edades] == ["0-40", "41+", SIN_INFORMAR] and sum(b.pacientes for b in custom.edades) == custom.kpis.pacientesEnAlcance
    byAge = {r.categoria for r in get(db, team.operator, team, segmentar="EDAD", edadBase="MEDICION").segmentacion}
    assert byAge == {"31-50", SIN_INFORMAR}  # edad AL MOMENTO de cada medición
    for bad in ("30,20", "a,b", "200", ",".join(str(n) for n in range(1, 10))):
        expectError("DATOS_INVALIDOS", get, db, team.operator, team, edadCortes=bad)
    expectError("DATOS_INVALIDOS", get, db, team.operator, team, edadCortes="40", edad="31-50")  # el rango no existe con esos cortes


def test_calidad_minima_solo_cuenta_las_que_registraron_calidad(db, scene):
    data = get(db, scene["team"].operator, scene["team"], calidadMinima=3)
    assert data.kpis.totalMediciones == 1  # full2 (4.5); full1 (2.5) y la sin calidad quedan fuera, la ausente no se asume


def test_comparacion_con_matriz_excluye_demo_y_exige_glucosa_de_un_paciente(db, scene):
    team, rosa = scene["team"], scene["patients"]["full"]
    tune(db, scene["ids"]["full3"], modoMedicion="GLUCOSA_EXPERIMENTAL")  # ahora la DEMO también es de modo glucosa, y aun así no se compara
    summary = get(db, team.operator, team, idPerfilMedicion=rosa.idPerfilMedicion, origen="TODOS", variable="glucosaDispositivo", compararMatriz=True).paciente
    assert summary.resumenMatriz.comparadas == 1 and summary.resumenMatriz.sinReferencia == 1  # sin matriz cargada: no se inventa referencia
    assert [p.referencia.motivo for p in summary.puntos if p.referencia is not None and p.origen == "EXPERIMENTAL"][0]  # explica por qué no hay intervalo
    assert [p.origen for p in summary.puntos if p.referencia is not None] == ["EXPERIMENTAL"]  # la medición DEMO nunca se compara
    assert get(db, team.operator, team, idPerfilMedicion=rosa.idPerfilMedicion, variable="glucosaDispositivo").paciente.resumenMatriz is None
    expectError("DATOS_INVALIDOS", get, db, team.operator, team, variable="glucosaDispositivo", compararMatriz=True)  # exige paciente
    expectError("DATOS_INVALIDOS", get, db, team.operator, team, idPerfilMedicion=rosa.idPerfilMedicion, variable="spo2", compararMatriz=True)


# --- Origen por defecto, totales por origen y calidad de señal ---------------------------------------------------------------------


def test_por_defecto_el_analisis_incluye_todos_los_origenes_y_los_separa(db, scene):
    data = analytics.analyze(db, scene["team"].operator, scene["team"].id)  # sin ningún filtro elegido
    assert data.filtros.origen == "TODOS" and data.filtros.estado == "TODOS"
    assert (data.kpis.experimentales, data.kpis.demo, data.kpis.totalMediciones) == (3, 1, 4)  # nada de DEMO excluido en silencio
    assert [s.origen for s in data.variable.series] == ["EXPERIMENTAL", "DEMO"]  # pero nunca en un mismo promedio
    assert (data.origenes.experimentales, data.origenes.demo) == (3, 1)


def test_con_experimental_y_solo_demo_los_totales_por_origen_explican_el_vacio(db, scene):
    team = scene["team"]
    only = get(db, team.operator, team, origen="EXPERIMENTAL", modo="OXIMETRIA", alimentacion="NO_INFORMADA")
    assert only.kpis.totalMediciones == 1  # control: hay una experimental
    demoOnly = get(db, team.operator, team, origen="EXPERIMENTAL", sexo="FEMENINO", edad="31-50", edadBase="MEDICION", alimentacion="AYUNO", estado="TODOS")
    assert demoOnly.kpis.totalMediciones == 1
    for ids in ("full1", "full2", "nodata"):
        tune(db, scene["ids"][ids], origenGlucosa="DEMO", glucosaDispositivo=100, unidadGlucosa="mg/dL")
    empty = get(db, team.operator, team, origen="EXPERIMENTAL")
    assert empty.kpis.totalMediciones == 0
    assert (empty.origenes.experimentales, empty.origenes.demo) == (0, 4)  # los registros no desaparecieron: son DEMO
    both = get(db, team.operator, team, origen="TODOS")
    assert both.kpis.totalMediciones == 4 and (both.origenes.experimentales, both.origenes.demo) == (0, 4)


def test_los_totales_por_origen_respetan_los_demas_filtros_y_el_alcance(db, scene):
    team = scene["team"]
    data = get(db, team.operator, team, origen="DEMO", modo="OXIMETRIA")
    assert (data.origenes.experimentales, data.origenes.demo) == (2, 1)  # oximetrías del período: full1 y Luis (experimentales) y full3 (DEMO)
    assert get(db, scene["second"], team).origenes.experimentales == 1  # María ve solo lo suyo, nunca lo de Juan


def test_la_calidad_de_senal_solo_cuenta_completadas_y_las_lecturas_del_equipo_se_informan_aparte(db, scene):
    team = scene["team"]
    tune(db, scene["ids"]["nodata"], estadoMedicion="INVALIDA", calidadSenal=0.3)
    tune(db, scene["ids"]["full1"], lecturasEstabilizadas=3)
    tune(db, scene["ids"]["full3"], lecturasEstabilizadas=3)
    data = analytics.analyze(db, team.operator, team.id)
    assert data.calidad.conValor == 3 and data.calidad.sinInformar == 0  # la inválida (0,3) no entra en la calidad: solo completadas
    assert [(b.lecturas, b.experimentales, b.demo) for b in data.calidad.lecturas] == [(3, 1, 1)] and data.calidad.conLecturas == 2


# --- Coherencia con el historial del mismo paciente ---------------------------------------------------------------------------------


def test_el_historial_y_el_analisis_reconocen_las_mismas_mediciones_elegibles(db, scene):
    """Mismo alcance, mismos filtros: el historial del paciente (listPatientHistory) y el análisis cuentan las mismas mediciones. Las únicas
    diferencias son las que se piden (período, origen, modo, estado) y están a la vista en los filtros."""
    team, dev = scene["team"], scene["dev"]
    rosa = scene["patients"]["full"].idPerfilMedicion
    cancelled = measure(db, team.operator, rosa, dev, "90", 60)  # cancelada hace horas: el historial institucional la conserva
    tune(db, cancelled.idMedicion, estadoMedicion="CANCELADA", fechaHoraInicio=nowForDb() - timedelta(hours=4), fechaHoraFin=nowForDb() - timedelta(hours=3), spo2=None, frecuenciaCardiaca=None)
    old = measure(db, team.operator, rosa, dev, "93", 66)  # fuera del período de 30 días
    tune(db, old.idMedicion, fechaHoraInicio=nowForDb() - timedelta(days=60))

    def history(pid, **filters):
        return measurements.listPatientHistory(db, team.operator, team.id, pid, tamanioPagina=50, **filters)

    def analysis(pid=None, **filters):
        filters.setdefault("dias", 365)
        return analytics.analyze(db, team.operator, team.id, idPerfilMedicion=pid, **filters)

    pids = [p.idPerfilMedicion for p in scene["patients"].values() if p is not scene["patients"]["foreign"]]
    for pid in pids:
        assert analysis(pid).kpis.totalMediciones == history(pid).total  # sin ningún filtro: todas, DEMO incluidas
        # «Sin resultado»: canceladas/inválidas/en curso, que no son DEMO pero tampoco experimentales (no tienen origen). El historial las
        # llama «REAL» (todo lo que no es DEMO); el análisis las cuenta aparte, así que la diferencia es exactamente esa cantidad.
        noResult = sum(history(pid, estado=state).total for state in ("INVALIDA", "CANCELADA", "PENDIENTE", "ADQUIRIENDO", "PROCESANDO"))
        full = analysis(pid).kpis
        assert (full.experimentales, full.demo, full.sinResultado) == (analysis(pid, origen="EXPERIMENTAL").kpis.totalMediciones, history(pid, origen="DEMO").total, noResult)
        assert full.experimentales + full.demo + full.sinResultado == full.totalMediciones
        assert analysis(pid, origen="DEMO").kpis.totalMediciones == history(pid, origen="DEMO").total
        assert analysis(pid, origen="EXPERIMENTAL").kpis.totalMediciones == history(pid, origen="REAL").total - noResult
        for state in ("COMPLETADA", "INVALIDA", "CANCELADA"):
            assert analysis(pid, estado=state).kpis.totalMediciones == history(pid, estado=state).total
        for mode in ("OXIMETRIA", "GLUCOSA_EXPERIMENTAL"):
            assert analysis(pid, modo=mode).kpis.totalMediciones == history(pid, modo=mode).total
    assert analysis().kpis.totalMediciones == sum(history(pid).total for pid in pids)  # el total del alcance es la suma de sus pacientes

    # Valores válidos: una medición con SpO₂ y frecuencia cardíaca los aporta aunque no tenga glucosa ni calidad.
    items = history(rosa, estado="COMPLETADA").items
    spo2 = sum(s.resumen.n for s in analysis(rosa, origen="TODOS", variable="spo2").variable.series)
    heart = sum(s.resumen.n for s in analysis(rosa, origen="TODOS", variable="frecuenciaCardiaca").variable.series)
    assert spo2 == sum(1 for item in items if item.spo2 is not None) and heart == sum(1 for item in items if item.frecuenciaCardiaca is not None)

    # La única diferencia con el período por defecto (30 días) es la medición de hace 60 días, y se ve en el filtro de período.
    assert history(rosa).total - analytics.analyze(db, team.operator, team.id, idPerfilMedicion=rosa).kpis.totalMediciones == 1


def test_un_paciente_con_solo_demo_aparece_con_sus_mediciones_en_el_analisis_por_defecto(db, scene):
    team = scene["team"]
    luis = scene["patients"]["nodata"].idPerfilMedicion
    tune(db, scene["ids"]["nodata"], origenGlucosa="DEMO", glucosaDispositivo=105, unidadGlucosa="mg/dL")
    data = analytics.analyze(db, team.operator, team.id, idPerfilMedicion=luis)  # sin ningún filtro elegido
    assert data.kpis.totalMediciones == 1 and data.kpis.demo == 1 and data.kpis.experimentales == 0
    assert data.kpis.pacientesConMediciones == 1 and len(data.paciente.puntos) == 1 and data.paciente.puntos[0].origen == "DEMO"
    heart = analytics.analyze(db, team.operator, team.id, idPerfilMedicion=luis, variable="frecuenciaCardiaca")
    assert {s.origen: s.resumen.n for s in heart.variable.series}["DEMO"] == 1  # una sola medición DEMO alcanza para graficar


def test_los_periodos_largos_que_ofrece_la_pantalla_se_aceptan(db, scene):
    team = scene["team"]
    for days in (7, 30, 90, 180, 365):  # la pantalla ofrece estos cinco; antes 180 y 365 fallaban con «El período debe ser de 7, 30 o 90 días»
        assert analytics.analyze(db, team.operator, team.id, dias=days).periodo.dias == days
    expectError("PERIODO_INVALIDO", analytics.analyze, db, team.operator, team.id, dias=45)


def test_una_medicion_cancelada_sin_origen_no_se_rotula_experimental(db, scene):
    team = scene["team"]
    luis = scene["patients"]["nodata"].idPerfilMedicion
    cancelled = measure(db, team.operator, luis, scene["dev"], "90", 60)
    tune(db, cancelled.idMedicion, estadoMedicion="CANCELADA", fechaHoraInicio=nowForDb() - timedelta(hours=4), fechaHoraFin=nowForDb() - timedelta(hours=3), spo2=None, frecuenciaCardiaca=None)
    data = analytics.analyze(db, team.operator, team.id)
    assert (data.kpis.totalMediciones, data.kpis.experimentales, data.kpis.demo, data.kpis.sinResultado) == (5, 3, 1, 1)
    assert sum(item.mediciones for item in data.porModoOrigen) == 4 and sum(data.kpis.porModo.values()) == 4  # los desgloses solo cuentan las con resultado
    assert sum(point.experimentales + point.demo for point in data.evolucion) == 4
    assert (data.origenes.experimentales, data.origenes.demo, data.origenes.sinResultado) == (3, 1, 1)
    only = analytics.analyze(db, team.operator, team.id, origen="EXPERIMENTAL")
    assert only.kpis.totalMediciones == 3 and only.kpis.sinResultado == 0 and only.origenes.sinResultado == 1  # el filtro la deja afuera y lo dice
