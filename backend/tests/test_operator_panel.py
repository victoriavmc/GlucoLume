# Panel del operador: última medición de cada paciente (incluye DEMO), medición DEMO identificada y gráficos del propio operador
# (serie, modos, calidad de señal y demografía) coherentes con sus indicadores y con el alcance que puede consultar.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_operator_panel.py -v

from datetime import timedelta

import pytest
from sqlalchemy import update

from app.models.measurement import Measurement
from app.services import dashboard as dashboards
from app.services import institutionPatients as patients
from app.services import profileTransfers as transfers
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import audits, db, engine, mails, reload  # noqa: F401
from tests.test_dashboards import institutionData, measure
from tests.test_institution_patients import patientData
from tests.test_institutions import expectError, freshLookupLimiter, team  # noqa: F401
from tests.test_measurements import device  # noqa: F401


def tune(db, measurement, **values):
    db.execute(update(Measurement).where(Measurement.idMedicion == measurement.idMedicion).values(**values))
    db.commit()


@pytest.fixture
def scene(db, team):
    """Juan: Rosa (mujer, 1990; una experimental y una DEMO), Luis (sin sexo ni nacimiento; solo DEMO) y Ana (sin mediciones)."""
    second, secondUser, dev = institutionData(db, team)
    rosa = patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz", dni="20111001", fechaNacimiento="1990-03-14", sexoModelo="femenino"))
    luis = patients.createPatient(db, team.operator, team.id, patientData(nombre="luis", apellido="paz", dni="20111002", fechaNacimiento=None, sexoModelo=None))
    ana = patients.createPatient(db, team.operator, team.id, patientData(nombre="ana", apellido="gil", dni="20111003", fechaNacimiento="2015-01-01", sexoModelo="femenino"))
    now = nowForDb()
    a = measure(db, team.operator, rosa.idPerfilMedicion, dev, "96", 70)
    tune(db, a, calidadSenal=0.5, fechaHoraInicio=now - timedelta(days=3))
    b = measure(db, team.operator, rosa.idPerfilMedicion, dev, "98", 80)
    tune(db, b, origenGlucosa="DEMO", glucosaDispositivo=118, unidadGlucosa="mg/dL", modoMedicion="GLUCOSA_EXPERIMENTAL", calidadSenal=0.9, fechaHoraInicio=now - timedelta(hours=2))
    c = measure(db, team.operator, luis.idPerfilMedicion, dev, "94", 75)
    tune(db, c, origenGlucosa="DEMO", glucosaDispositivo=110, unidadGlucosa="mg/dL", calidadSenal=None, fechaHoraInicio=now - timedelta(days=1))
    return {"team": team, "second": second, "secondUser": secondUser, "dev": dev, "rosa": rosa, "luis": luis, "ana": ana, "b": b}


def panel(db, scene, **kwargs):
    return dashboards.operatorDashboard(db, scene["team"].operator, scene["team"].id, "me", **kwargs)


def test_un_paciente_con_solo_demo_muestra_su_ultima_medicion_identificada(db, scene):
    rows = {p.identificadorPseudonimo: p for p in panel(db, scene).pacientes}
    luis = rows[scene["luis"].identificadorPseudonimo]
    assert luis.ultimaMedicion is not None and luis.ultimaEsDemo is True and luis.ultimaModo == "OXIMETRIA"  # no «Sin mediciones»
    rosa = rows[scene["rosa"].identificadorPseudonimo]
    assert rosa.ultimaEsDemo is True and rosa.ultimaModo == "GLUCOSA_EXPERIMENTAL"  # la más reciente es la DEMO de hace 2 h
    ana = rows[scene["ana"].identificadorPseudonimo]
    assert ana.ultimaMedicion is None and ana.ultimaModo is None  # sin registros: sin inventar nada


def test_las_listas_incluyen_demo_identificada_y_los_contadores_historicos_la_informan_aparte(db, scene):
    data = panel(db, scene)
    assert (data.medicionesRealizadas, data.medicionesRealizadasDemo) == (1, 2)  # el contador histórico no mezcla DEMO
    assert (data.medicionesEnPeriodo, data.medicionesEnPeriodoDemo) == (1, 2)
    assert sorted(r.esDemo for r in data.realizadas) == [False, True, True]
    assert sorted(r.esDemo for r in data.ultimasDePacientes) == [False, True, True]


def test_los_graficos_coinciden_con_los_indicadores_y_separan_demo(db, scene):
    charts = panel(db, scene).graficos
    assert sum(d.experimentales for d in charts.serie) == 1 and sum(d.demo for d in charts.serie) == 2
    modes = {m.modo: (m.experimentales, m.demo) for m in charts.porModo}
    assert modes == {"OXIMETRIA": (1, 1), "GLUCOSA_EXPERIMENTAL": (0, 1)}
    assert sum(a + b for a, b in modes.values()) == 3 == sum(d.experimentales + d.demo for d in charts.serie)
    week = panel(db, scene, dias=7).graficos
    assert sum(d.experimentales + d.demo for d in week.serie) == 3


def test_la_calidad_de_senal_usa_solo_valores_registrados_sin_umbrales(db, scene):
    quality = panel(db, scene).graficos.calidadSenal
    assert (quality.conValor, quality.sinDato, quality.fueraDeAlcance) == (2, 1, 0)  # Luis no registró calidad: no cuenta como 0
    assert (quality.minimo, quality.maximo) == (0.5, 0.9)
    assert sum(b.experimentales + b.demo for b in quality.rangos) == quality.conValor
    assert [b.demo for b in quality.rangos][-1] == 1 and [b.experimentales for b in quality.rangos][0] == 1  # DEMO y experimental en columnas propias


def test_la_demografia_cuenta_pacientes_unicos_con_sin_informar(db, scene):
    charts = panel(db, scene).graficos
    assert charts.pacientesDemografia == 3
    rows = {r.rango: r for r in charts.demografia}
    assert (rows["18-39"].femenino, rows["0-17"].femenino, rows["SIN_INFORMAR"].sinInformar) == (1, 1, 1)  # Rosa, Ana y Luis (sin fecha ni sexo)
    assert sum(r.masculino + r.femenino + r.sinInformar for r in charts.demografia) == 3
    dumped = charts.model_dump_json()
    for secret in ("Rosa", "Díaz", "20111001", scene["rosa"].identificadorPseudonimo):
        assert secret not in dumped  # sin nombres ni documentos


def test_un_paciente_transferido_conserva_la_autoria_pero_sale_de_la_calidad_y_del_alcance(db, scene):
    team, second, secondUser = scene["team"], scene["second"], scene["secondUser"]
    sent = transfers.requestTransfer(db, team.operator, team.id, scene["rosa"].idPerfilMedicion, second.idInstitucionUsuario, None)
    transfers.acceptTransfer(db, secondUser, team.id, sent.idTransferenciaPerfil)
    juan = panel(db, scene)
    assert (juan.medicionesRealizadas, juan.medicionesRealizadasDemo) == (1, 2)  # la autoría histórica se conserva
    assert sum(d.experimentales + d.demo for d in juan.graficos.serie) == 3  # y los conteos del gráfico coinciden con ella
    assert juan.graficos.calidadSenal.conValor == 0 and juan.graficos.calidadSenal.fueraDeAlcance == 2  # pero sus valores ya no son legibles
    assert juan.graficos.pacientesDemografia == 2 and all(p.identificadorPseudonimo != scene["rosa"].identificadorPseudonimo for p in juan.pacientes)


def test_quien_supervisa_no_recibe_graficos_ni_valores(db, scene):
    team = scene["team"]
    own = dashboards.operatorDashboard(db, team.operator, team.id, "me")
    supervised = dashboards.operatorDashboard(db, team.owner, team.id, str(own.operador.idInstitucionUsuario))
    assert supervised.graficos is None and supervised.pacientes == [] and supervised.realizadas == [] and not supervised.esPropio
    assert supervised.medicionesRealizadas == 1 and supervised.medicionesRealizadasDemo == 2  # solo contadores


def test_las_mediciones_del_equipo_sin_calidad_informan_sus_lecturas_estabilizadas_aparte(db, scene):
    """El equipo guarda `calidadSenal` en null y registra las lecturas estabilizadas: el panel no inventa calidad y muestra esas lecturas."""
    ids = [m.idMedicion for m in db.scalars(__import__("sqlalchemy").select(Measurement)).all()]
    db.execute(update(Measurement).where(Measurement.idMedicion.in_(ids)).values(calidadSenal=None))
    db.execute(update(Measurement).where(Measurement.idMedicion == scene["b"].idMedicion).values(lecturasEstabilizadas=5))
    db.commit()
    quality = panel(db, scene).graficos.calidadSenal
    assert quality.conValor == 0 and quality.rangos == [] and quality.sinDato == 3  # nada de calidad inventada
    assert quality.conLecturas == 1 and [(b.lecturas, b.experimentales, b.demo) for b in quality.lecturas] == [(5, 0, 1)]


def test_una_cancelada_sin_origen_se_informa_como_sin_resultado_y_no_como_experimental(db, scene):
    team = scene["team"]
    cancelled = measure(db, team.operator, scene["luis"].idPerfilMedicion, scene["dev"], "90", 60)
    tune(db, cancelled, estadoMedicion="CANCELADA", fechaHoraInicio=nowForDb() - timedelta(hours=4), fechaHoraFin=nowForDb() - timedelta(hours=3), spo2=None, frecuenciaCardiaca=None)
    data = panel(db, scene)
    assert data.medicionesEnPeriodo == 2 and data.medicionesEnPeriodoSinResultado == 1  # 1 experimental completada + 1 cancelada; la cancelada no es experimental
    assert data.medicionesSinResultado == 1 and data.medicionesEnPeriodoDemo == 2
    charts = data.graficos
    assert charts.sinResultado == 1 and sum(d.experimentales for d in charts.serie) == 1 and sum(d.demo for d in charts.serie) == 2  # serie y modos sin ella
    assert sum(m.experimentales + m.demo for m in charts.porModo) == 3
