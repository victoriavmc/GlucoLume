# Estadísticas ADMINISTRATIVAS del dashboard institucional (moderador y propietario): cantidades de actividad desde el primer registro, con
# DEMO, todos los estados y filtros, sin valores de salud ni identificación de pacientes.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_admin_dashboard.py -v

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from app.models.institutionUser import InstitutionUser
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


def admin(db, actor, team, **filters):
    return dashboards.institutionDashboard(db, actor, team.id, 30, **filters).administrativo


def counts(item):
    return (item.total, item.completadas, item.canceladas, item.invalidas, item.enCurso, item.experimentales, item.demo, item.sinResultado)


def test_una_sola_medicion_cancelada_cuenta_como_actividad_y_no_oculta_nada(db, team):
    dev = device(db, institucion=team.id)
    patient = patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz"))
    cancelled = measure(db, team.operator, patient.idPerfilMedicion, dev, "90", 60)
    tune(db, cancelled, estadoMedicion="CANCELADA", fechaHoraFin=nowForDb() + timedelta(minutes=1), spo2=None, frecuenciaCardiaca=None)
    data = dashboards.institutionDashboard(db, team.owner, team.id, 30)
    stats = data.administrativo
    assert counts(stats.kpis) == (1, 0, 1, 0, 0, 0, 0, 1)  # una cancelada: ni experimental ni DEMO, pero sí actividad
    assert [(d.canceladas, d.completadas) for d in stats.serie] == [(1, 0)]  # el gráfico por fecha NO queda vacío
    assert stats.kpis.pacientesRegistrados == 1 and stats.kpis.pacientesActivos == 1  # N = 1: se muestra
    assert [(s.estado, s.total) for s in stats.porEstado if s.total] == [("CANCELADA", 1)]
    assert data.agregadosProtegidos  # los resultados de salud siguen protegidos con menos de 5 pacientes…
    assert data.estadisticas.cantidadMediciones == 0  # …y la cancelada no genera promedios falsos


@pytest.fixture
def scene(db, team):
    """Juan (operador): Rosa con una experimental completada, una DEMO completada y una inválida; Luis sin datos demográficos con una DEMO.
    María (otra operadora): un paciente con una experimental y una cancelada."""
    second, secondUser, dev = institutionData(db, team)
    rosa = patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz", dni="20111001"))
    luis = patients.createPatient(db, team.operator, team.id, patientData(nombre="luis", apellido="paz", dni="20111002", fechaNacimiento=None, sexoModelo=None))
    beto = patients.createPatient(db, secondUser, team.id, patientData(nombre="beto", apellido="ríos", dni="20111003"))
    now = nowForDb()
    a = measure(db, team.operator, rosa.idPerfilMedicion, dev, "96", 70)
    tune(db, a, fechaHoraInicio=now - timedelta(days=2))
    b = measure(db, team.operator, rosa.idPerfilMedicion, dev, "98", 80)
    tune(db, b, origenGlucosa="DEMO", glucosaDispositivo=118, unidadGlucosa="mg/dL", modoMedicion="GLUCOSA_EXPERIMENTAL", fechaHoraInicio=now - timedelta(days=1))
    c = measure(db, team.operator, rosa.idPerfilMedicion, dev, "90", 60)
    tune(db, c, estadoMedicion="INVALIDA", fechaHoraInicio=now - timedelta(days=1, hours=1), fechaHoraFin=now - timedelta(days=1), spo2=None, frecuenciaCardiaca=None)
    d = measure(db, team.operator, luis.idPerfilMedicion, dev, "94", 75)
    tune(db, d, origenGlucosa="DEMO", glucosaDispositivo=105, unidadGlucosa="mg/dL")
    e = measure(db, secondUser, beto.idPerfilMedicion, dev, "97", 72)
    f = measure(db, secondUser, beto.idPerfilMedicion, dev, "91", 61)
    tune(db, f, estadoMedicion="CANCELADA", fechaHoraFin=nowForDb() + timedelta(minutes=1), spo2=None, frecuenciaCardiaca=None)
    return {"team": team, "second": second, "secondUser": secondUser, "dev": dev, "rosa": rosa, "luis": luis, "beto": beto}


def test_mezcla_de_estados_y_origenes_con_totales_que_cierran(db, scene):
    team = scene["team"]
    kpis = admin(db, team.moderator, team).kpis
    assert counts(kpis) == (6, 4, 1, 1, 0, 2, 2, 2)  # 6 = 4 completadas + 1 cancelada + 1 inválida = 2 exp. + 2 DEMO + 2 sin resultado
    assert kpis.experimentales + kpis.demo + kpis.sinResultado == kpis.total == kpis.completadas + kpis.canceladas + kpis.invalidas + kpis.enCurso
    assert (kpis.pacientesRegistrados, kpis.pacientesActivos, kpis.operadoresActivos) == (3, 3, 2)
    stats = admin(db, team.moderator, team)
    assert sum(d.completadas + d.canceladas + d.invalidas + d.enCurso for d in stats.serie) == 6  # la serie suma lo mismo que los KPIs
    modes = {m.modo: counts(m) for m in stats.porModo}
    assert modes == {"OXIMETRIA": (5, 3, 1, 1, 0, 2, 1, 2), "GLUCOSA_EXPERIMENTAL": (1, 1, 0, 0, 0, 0, 1, 0)}
    assert sum(m.total for m in stats.porModo) == 6 and sum(s.total for s in stats.porEstado) == 6


def test_los_filtros_de_modo_estado_origen_y_operador_se_combinan(db, scene):
    team = scene["team"]
    assert admin(db, team.moderator, team, origen="DEMO").kpis.total == 2
    assert admin(db, team.moderator, team, origen="EXPERIMENTAL").kpis.total == 2  # las sin resultado no son experimentales
    assert admin(db, team.moderator, team, estado="CANCELADA").kpis.canceladas == 1
    assert admin(db, team.moderator, team, modo="GLUCOSA_EXPERIMENTAL").kpis.total == 1
    juan = relationOf(db, team, team.operator).idInstitucionUsuario
    maria = scene["second"].idInstitucionUsuario
    assert counts(admin(db, team.moderator, team, operador=juan).kpis) == (4, 3, 0, 1, 0, 1, 2, 1)
    assert counts(admin(db, team.moderator, team, operador=maria).kpis) == (2, 1, 1, 0, 0, 1, 0, 1)
    both = admin(db, team.moderator, team, operador=juan, origen="DEMO", modo="OXIMETRIA")
    assert both.kpis.total == 1 and [o.idInstitucionUsuario for o in both.porOperador] == [juan]
    assert admin(db, team.moderator, team, operador=juan).kpis.pacientesAsignadosOperador == 2


def test_dos_operadores_con_cantidades_distintas_y_un_operador_desvinculado_con_actividad_se_conserva(db, scene):
    team = scene["team"]
    stats = admin(db, team.owner, team)
    byId = {o.idInstitucionUsuario: o for o in stats.porOperador}
    juan = relationOf(db, team, team.operator).idInstitucionUsuario
    maria = scene["second"].idInstitucionUsuario
    assert (byId[juan].total, byId[juan].pacientesAsignados) == (4, 2) and (byId[maria].total, byId[maria].pacientesAsignados) == (2, 1)
    # María se desvincula pero tuvo actividad en el período: sigue en la tabla con su identificación histórica y sus cantidades.
    relation = db.get(InstitutionUser, maria)
    relation.estadoRelacion = "BAJA"
    relation.fechaBaja = nowForDb()
    db.commit()
    after = admin(db, team.owner, team)
    row = {o.idInstitucionUsuario: o for o in after.porOperador}[maria]
    assert (row.activo, row.total, row.canceladas, row.completadas, row.experimentales, row.demo) == (False, 2, 1, 1, 1, 0)
    assert maria in {o.idInstitucionUsuario for o in after.operadores}  # y se puede elegir como filtro mientras tenga actividad
    assert after.kpis.total == 6 and after.kpis.operadoresActivos == 1 and after.kpis.pacientesSinOperador == 1
    # Con el filtro de DEMO ella no tiene actividad (todo cero): la fila vacía de un desvinculado no se muestra.
    demo = admin(db, team.owner, team, origen="DEMO")
    assert maria not in {o.idInstitucionUsuario for o in demo.porOperador} and maria not in {o.idInstitucionUsuario for o in demo.operadores}
    assert juan in {o.idInstitucionUsuario for o in demo.porOperador}  # el operador vinculado se conserva aunque haya poco movimiento


def test_un_operador_desvinculado_sin_actividad_en_el_periodo_no_aparece_pero_su_historia_se_conserva(db, scene):
    team = scene["team"]
    maria = scene["second"].idInstitucionUsuario
    relation = db.get(InstitutionUser, maria)
    relation.estadoRelacion = "BAJA"
    relation.fechaBaja = nowForDb()
    db.commit()
    # Toda la actividad de María pasa a hace 60 días: fuera del período de 30 días, dentro de uno de 90.
    old = nowForDb() - timedelta(days=60)
    db.execute(update(Measurement).where(Measurement.idPerfilMedicion == scene["beto"].idPerfilMedicion)
               .values(fechaHoraInicio=old, fechaHoraFin=old + timedelta(minutes=1)))
    db.commit()
    month = admin(db, team.owner, team)
    assert maria not in {o.idInstitucionUsuario for o in month.porOperador}  # sin actividad en el período: no se lista
    assert maria not in {o.idInstitucionUsuario for o in month.operadores}
    assert month.kpis.total == 4  # los totales del período no cambian por ocultar una fila vacía
    wide = dashboards.institutionDashboard(db, team.owner, team.id, 90).administrativo
    row = {o.idInstitucionUsuario: o for o in wide.porOperador}[maria]  # al cambiar el período se recalcula: ahí sí tuvo actividad
    assert row.total == 2 and not row.activo and wide.kpis.total == 6
    # Elegirla explícitamente la muestra aunque no tenga actividad; nada se borró.
    explicit = admin(db, team.owner, team, operador=maria)
    assert [o.idInstitucionUsuario for o in explicit.porOperador] == [maria] and explicit.porOperador[0].total == 0
    assert db.scalar(select(func.count()).select_from(Measurement).where(Measurement.idPerfilMedicion == scene["beto"].idPerfilMedicion)) == 2


def test_un_operador_desvinculado_con_la_cuenta_eliminada_se_muestra_sin_datos_personales(db, scene):
    team = scene["team"]
    maria = scene["second"].idInstitucionUsuario
    relation = db.get(InstitutionUser, maria)
    relation.estadoRelacion = "BAJA"
    relation.fechaBaja = nowForDb()
    relation.fechaMinimizacionDatos = nowForDb()  # vencida la conservación de sus datos históricos
    db.commit()
    row = {o.idInstitucionUsuario: o for o in admin(db, team.owner, team).porOperador}[maria]
    assert (row.nombre, row.apellido, row.total) == ("Operador desvinculado", None, 2)  # rótulo neutro: la cifra histórica se conserva
    assert "María" not in admin(db, team.owner, team).model_dump_json()


def test_los_conteos_administrativos_no_traen_valores_de_salud_ni_pacientes(db, scene):
    team = scene["team"]
    dumped = admin(db, team.owner, team).model_dump_json()
    for secret in ("Rosa", "Díaz", "20111001", str(scene["rosa"].idPerfilMedicion), scene["rosa"].identificadorPseudonimo, "spo2", "glucosa", "frecuencia"):
        assert secret not in dumped  # solo cantidades de trabajo: ni nombres de pacientes ni SpO₂, frecuencia o glucosa


def test_permisos_filtros_invalidos_y_acceso_individual(db, scene):
    team = scene["team"]
    for actor in (team.owner, team.moderator):
        assert dashboards.institutionDashboard(db, actor, team.id, 30).administrativo.kpis.total == 6  # ambos roles ven el mismo agregado
    expectError("PERMISO_INSUFICIENTE", dashboards.institutionDashboard, db, team.operator, team.id, 30)  # el operador no lo pide
    expectError("MIEMBRO_NO_ENCONTRADO", dashboards.institutionDashboard, db, team.owner, team.id, 30, operador=uuid.uuid4())
    moderator = relationOf(db, team, team.moderator).idInstitucionUsuario
    expectError("MIEMBRO_NO_ENCONTRADO", dashboards.institutionDashboard, db, team.owner, team.id, 30, operador=moderator)  # solo operadores
    for bad in ({"modo": "PESO"}, {"estado": "NADA"}, {"origen": "OTRO"}):
        expectError("DATOS_INVALIDOS", dashboards.institutionDashboard, db, team.owner, team.id, 30, **bad)
    # Ningún rol administrativo accede a mediciones individuales por UUID o filtros.
    for actor in (team.owner, team.moderator):
        expectError("MEDICIONES_NO_AUTORIZADAS", measurements.listPatientHistory, db, actor, team.id, scene["rosa"].idPerfilMedicion)
        expectError("MEDICIONES_NO_AUTORIZADAS", measurements.patientEvolution, db, actor, team.id, scene["rosa"].idPerfilMedicion)
