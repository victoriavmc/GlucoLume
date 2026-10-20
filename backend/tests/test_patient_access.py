# Control de acceso a pacientes institucionales (Ley 25.326 y Ley 26.529): la visibilidad ADMINISTRATIVA de los pacientes (nombre, apellido,
# operador responsable, fecha de registro y estado) es del personal de la institución; el acceso a las MEDICIONES individuales (última
# medición, historial, gráficos, estadísticas, detalle, registro y resultados) es solo del operador responsable vigente. Moderador y
# propietario supervisan con datos administrativos y estadísticas agregadas (con un mínimo de pacientes para no identificar a nadie).
# Escenario: Operador 1 (P1, P2), Operador 2 (P3), Operador 3 (P4) y Operador 5 sin pacientes; propietario y moderador.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_patient_access.py -v

import pytest
from sqlalchemy import select

from app.models.audit import Audit
from app.models.user import User
from app.services import dashboard as dashboards
from app.services import institutionPatients as patients
from app.services import measurement as measurements
from app.services import patientAccess
from app.services import profileTransfers as transfers
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_institution_patients import addOperator, otherInstitution, patientData
from tests.test_institutions import expectError, freshLookupLimiter, institutional, relationOf, team  # noqa: F401
from tests.test_measurements import completeOximetry, device, oximetry

DENIED = "MEDICIONES_NO_AUTORIZADAS"


def operator(db, team, email, usuario):
    relation = addOperator(db, team, email, usuario)
    return relation, db.get(User, relation.idUsuarioInvitado)


@pytest.fixture
def scene(db, mails, team):
    """Operador 1 = team.operator (P1 y P2); Operador 2 (P3); Operador 3 (P4); Operador 5 sin pacientes. P1 y P3 con mediciones."""
    op2, user2 = operator(db, team, "op2@example.com", "opdos")
    op3, user3 = operator(db, team, "op3@example.com", "optres")
    op5, user5 = operator(db, team, "op5@example.com", "opcinco")
    p1 = patients.createPatient(db, team.operator, team.id, patientData(nombre="paciente", apellido="uno", dni="11.111.111"))
    p2 = patients.createPatient(db, team.operator, team.id, patientData(nombre="paciente", apellido="dos", dni="22.222.222"))
    p3 = patients.createPatient(db, user2, team.id, patientData(nombre="paciente", apellido="tres", dni="33.333.333"))
    p4 = patients.createPatient(db, user3, team.id, patientData(nombre="paciente", apellido="cuatro", dni="44.444.444"))
    dev = device(db, institucion=team.id)
    m1 = completeOximetry(db, team.operator, p1.idPerfilMedicion, dev, spo2="95")
    m3 = completeOximetry(db, user2, p3.idPerfilMedicion, dev, spo2="97")

    class Scene:
        pass

    s = Scene()
    s.team, s.dev = team, dev
    s.op1, s.op2, s.op3, s.op5 = team.operator, user2, user3, user5
    s.rel2 = op2
    s.p1, s.p2, s.p3, s.p4, s.m1, s.m3 = p1, p2, p3, p4, m1, m3
    return s


# --- 1-2. Visibilidad administrativa para todos los operadores -------------------------------------------------------------


def test_operador_1_consulta_su_paciente_1_con_acceso_autorizado(db, scene):
    t = scene.team
    read = patients.getPatient(db, scene.op1, t.id, scene.p1.idPerfilMedicion)
    assert read.esMio and read.medicionesAutorizadas and read.puedeModificar and read.dni and read.fechaUltimaMedicion is not None
    assert measurements.listPatientHistory(db, scene.op1, t.id, scene.p1.idPerfilMedicion).total == 1
    assert measurements.patientStatistics(db, scene.op1, t.id, scene.p1.idPerfilMedicion, 30).cantidadMediciones == 1
    assert dashboards.patientDashboard(db, scene.op1, t.id, scene.p1.idPerfilMedicion).resumen.total == 1
    assert measurements.getMeasurement(db, scene.op1, scene.m1.idMedicion).idMedicion == scene.m1.idMedicion
    assert oximetry(db, scene.op1, scene.p1.idPerfilMedicion, scene.dev).puedeOperar  # registra una nueva medición


def test_operador_1_consulta_el_nombre_del_paciente_3_y_solo_su_identificacion_administrativa(db, scene):
    read = patients.getPatient(db, scene.op1, scene.team.id, scene.p3.idPerfilMedicion)
    assert (read.nombre, read.apellido) == ("Paciente", "Tres")
    assert read.responsable.idInstitucionUsuario == scene.rel2.idInstitucionUsuario  # operador responsable
    assert read.fechaCreacion is not None and read.estado == "ACTIVO"  # fecha de registro y estado administrativo
    # Nada más: ni documento, nacimiento, edad, sexo ni la fecha de la última medición (el paciente tiene una).
    assert (read.dni, read.fechaNacimiento, read.edad, read.sexoModelo, read.fechaUltimaMedicion) == (None, None, None, None, None)
    assert not read.esMio and not read.medicionesAutorizadas and not read.puedeModificar
    assert "33333333" not in read.model_dump_json() and "33.333.333" not in read.model_dump_json()


def test_operador_5_ve_el_listado_institucional_completo_sin_datos_de_salud(db, scene):
    page = patients.listPatients(db, scene.op5, scene.team.id)
    assert page.total == 4  # sin pacientes propios, ve los registrados en la institución
    assert {p.apellido for p in page.items} == {"Uno", "Dos", "Tres", "Cuatro"}
    assert all(p.dni is None and p.fechaUltimaMedicion is None and not p.medicionesAutorizadas and not p.esMio for p in page.items)
    assert patients.listPatients(db, scene.op5, scene.team.id, soloMios=True).total == 0  # «Mis pacientes»: vacío
    assert {p.apellido for p in patients.listPatients(db, scene.op1, scene.team.id, soloMios=True).items} == {"Uno", "Dos"}
    byOperator = patients.listPatients(db, scene.op5, scene.team.id, idResponsable=scene.rel2.idInstitucionUsuario)
    assert [p.apellido for p in byOperator.items] == ["Tres"]  # filtro por operador responsable


# --- 3-5. Las mediciones ajenas se rechazan en todos los endpoints ---------------------------------------------------------


def test_operador_1_no_accede_a_las_mediciones_del_paciente_3(db, scene, api):
    t, p3 = scene.team, scene.p3
    for call, args in ((measurements.listPatientHistory, ()), (measurements.patientStatistics, (30,)), (dashboards.patientDashboard, ())):
        expectError(DENIED, call, db, scene.op1, t.id, p3.idPerfilMedicion, *args)
    expectError(DENIED, measurements.getMeasurement, db, scene.op1, scene.m3.idMedicion)
    expectError(DENIED, oximetry, db, scene.op1, p3.idPerfilMedicion, scene.dev)  # tampoco registra mediciones ajenas
    expectError(DENIED, measurements.cancelMeasurement, db, scene.op1, scene.m3.idMedicion)
    expectError(DENIED, measurements.registerCapillaryReference, db, scene.op1, scene.m3.idMedicion, None)
    base = f"/api/v1/institutions/{t.id}/patients/{p3.idPerfilMedicion}"
    for path in ("/measurements", "/measurements/statistics", "/dashboard"):
        denied = api(scene.op1).get(base + path)
        assert denied.status_code == 403 and denied.json()["codigo"] == DENIED, path
        assert "disponibles únicamente para su operador responsable autorizado" in denied.json()["detail"]
    assert api(scene.op1).get(f"/api/v1/measurements/{scene.m3.idMedicion}").status_code == 403


def test_operador_5_no_abre_graficos_ni_estadisticas_ajenas_ni_el_mensaje_filtra_valores(db, scene, api):
    t = scene.team
    for patient in (scene.p1, scene.p3):
        for path in ("/measurements/statistics", "/dashboard", "/measurements"):
            response = api(scene.op5).get(f"/api/v1/institutions/{t.id}/patients/{patient.idPerfilMedicion}{path}")
            assert response.status_code == 403 and "95" not in response.text and "97" not in response.text


# --- 6-8. Moderador y propietario: administración sí, salud individual no ---------------------------------------------------


@pytest.mark.parametrize("role", ["moderator", "owner"])
def test_moderador_y_propietario_listan_pacientes_pero_no_consultan_mediciones_individuales(db, scene, api, role):
    actor = getattr(scene.team, role)
    t = scene.team
    page = patients.listPatients(db, actor, t.id)
    assert page.total == 4 and all(p.responsable.nombre and p.fechaCreacion for p in page.items)
    assert all(p.fechaUltimaMedicion is None and not p.medicionesAutorizadas for p in page.items)  # ni la última medición
    assert patients.getPatient(db, actor, t.id, scene.p3.idPerfilMedicion).dni  # información administrativa para gestionar
    for patient in (scene.p1, scene.p3):
        for call, args in ((measurements.listPatientHistory, ()), (measurements.patientStatistics, (30,)), (dashboards.patientDashboard, ())):
            expectError(DENIED, call, db, actor, t.id, patient.idPerfilMedicion, *args)
    expectError(DENIED, measurements.getMeasurement, db, actor, scene.m1.idMedicion)
    expectError(DENIED, oximetry, db, actor, scene.p1.idPerfilMedicion, scene.dev)
    assert api(actor).get(f"/api/v1/institutions/{t.id}/patients/{scene.p1.idPerfilMedicion}/measurements").status_code == 403
    assert api(actor).get(f"/api/v1/institutions/{t.id}/patients").status_code == 200


def test_el_operador_supervisado_se_ve_como_carga_de_trabajo_no_como_pacientes_ni_mediciones(db, scene):
    view = dashboards.operatorDashboard(db, scene.team.moderator, scene.team.id, str(relationOf(db, scene.team, scene.op1).idInstitucionUsuario))
    assert view.pacientesAsignados == 2 and view.medicionesRealizadas == 1
    assert view.pacientes == [] and view.realizadas == [] and view.ultimasDePacientes == []


# --- 9. Estadísticas agregadas anonimizadas ----------------------------------------------------------------------------------


def test_las_estadisticas_agregadas_exigen_un_minimo_de_pacientes_distintos(db, scene):
    t = scene.team
    # Hoy hay dos pacientes medidos (P1 y P3): menos que el mínimo.
    small = dashboards.institutionDashboard(db, t.owner, t.id, 30)
    assert small.agregadosProtegidos and small.minimoPacientesAgregados == patientAccess.MIN_AGGREGATE_PATIENTS
    assert small.estadisticas.cantidadMediciones == 0 and small.estadisticas.spo2.promedio is None and small.serie == []
    assert small.medicionesTotal == 2 and small.pacientesActivos == 4  # los conteos administrativos se informan
    assert measurements.institutionIndicators(db, t.moderator, t.id).completadas["spo2"].promedio is None
    # Con cinco pacientes distintos sí se informa.
    for patient in (scene.p2, scene.p4, patients.createPatient(db, scene.op5, t.id, patientData(nombre="paciente", apellido="cinco", dni="55.555.555"))):
        completeOximetry(db, db.get(User, relationOfPatientUser(db, patient)), patient.idPerfilMedicion, scene.dev, spo2="96")
    full = dashboards.institutionDashboard(db, t.owner, t.id, 30)
    assert not full.agregadosProtegidos and full.estadisticas.cantidadMediciones == 5 and full.estadisticas.spo2.promedio is not None
    # Un filtro de período que deja pocos pacientes vuelve a proteger el agregado.
    narrowed = dashboards.institutionDashboard(db, t.owner, t.id, 30, desde=__import__("datetime").date(2020, 1, 1), hasta=__import__("datetime").date(2020, 1, 2))
    assert narrowed.agregadosProtegidos and narrowed.estadisticas.cantidadMediciones == 0
    # Lo agregado no identifica a nadie.
    dumped = full.model_dump_json()
    for secret in ("Uno", "Tres", "Cuatro", "11111111", scene.p1.identificadorPseudonimo, str(scene.p1.idPerfilMedicion)):
        assert secret not in dumped


def relationOfPatientUser(db, patient):
    """Cuenta del operador responsable de un paciente."""
    from app.models.institutionUser import InstitutionUser
    relation = db.get(InstitutionUser, patient.responsable.idInstitucionUsuario)
    return relation.idUsuarioInvitado


# --- 10. Transferencia -------------------------------------------------------------------------------------------------------


def test_paciente_transferido_el_operador_anterior_pierde_el_acceso_sensible_y_la_autoria_se_conserva(db, scene):
    t = scene.team
    item = transfers.requestTransfer(db, scene.op1, t.id, scene.p1.idPerfilMedicion, scene.rel2.idInstitucionUsuario, None)
    transfers.acceptTransfer(db, scene.op2, t.id, item.idTransferenciaPerfil)
    expectError(DENIED, measurements.listPatientHistory, db, scene.op1, t.id, scene.p1.idPerfilMedicion)
    expectError(DENIED, measurements.getMeasurement, db, scene.op1, scene.m1.idMedicion)
    assert patients.getPatient(db, scene.op1, t.id, scene.p1.idPerfilMedicion).dni is None
    assert measurements.listPatientHistory(db, scene.op2, t.id, scene.p1.idPerfilMedicion).total == 1  # el nuevo responsable, sí
    first = [a for a in audits(db, "INICIAR_MEDICION") if a.idRegistro == scene.m1.idMedicion][0]
    assert first.idUsuario == scene.op1.idUsuario  # la autoría histórica no cambia
    assert dashboards.operatorDashboard(db, scene.op1, t.id, "me").medicionesRealizadas == 1


# --- 11. Otra institución y API directa --------------------------------------------------------------------------------------


def test_un_usuario_de_otra_institucion_no_consulta_pacientes_ni_mediciones(db, scene, api):
    foreign, foreignOperator, _ = otherInstitution(db)
    t = scene.team
    expectError("INSTITUCION_NO_ENCONTRADA", patients.getPatient, db, foreignOperator, t.id, scene.p1.idPerfilMedicion)
    expectError("INSTITUCION_NO_ENCONTRADA", patients.listPatients, db, foreignOperator, t.id)
    expectError("PACIENTE_NO_ENCONTRADO", patients.getPatient, db, foreignOperator, foreign.idInstitucion, scene.p1.idPerfilMedicion)
    expectError("PACIENTE_NO_ENCONTRADO", measurements.listPatientHistory, db, foreignOperator, foreign.idInstitucion, scene.p1.idPerfilMedicion)
    expectError("MEDICION_NO_ENCONTRADA", measurements.getMeasurement, db, foreignOperator, scene.m1.idMedicion)
    assert api(foreignOperator).get(f"/api/v1/institutions/{t.id}/patients/{scene.p1.idPerfilMedicion}").status_code == 404
    assert api(foreignOperator).get(f"/api/v1/institutions/{foreign.idInstitucion}/patients/{scene.p1.idPerfilMedicion}/measurements").status_code == 404


def test_la_api_directa_sin_autenticacion_es_rechazada(db, scene, client_without_login=None):
    from fastapi.testclient import TestClient

    from app.main import app
    anonymous = TestClient(app)
    base = f"/api/v1/institutions/{scene.team.id}/patients/{scene.p1.idPerfilMedicion}"
    for path in ("", "/measurements", "/measurements/statistics", "/dashboard"):
        assert anonymous.get(base + path).status_code in (401, 403), path
    assert anonymous.get(f"/api/v1/measurements/{scene.m1.idMedicion}").status_code in (401, 403)


# --- 12. Auditoría de los intentos rechazados --------------------------------------------------------------------------------


def test_el_intento_rechazado_queda_auditado_sin_valores_de_salud(db, scene):
    expectError(DENIED, measurements.listPatientHistory, db, scene.op1, scene.team.id, scene.p3.idPerfilMedicion)
    expectError(DENIED, measurements.getMeasurement, db, scene.team.moderator, scene.m3.idMedicion)
    rows = db.scalars(select(Audit).where(Audit.accion == "CONSULTAR_MEDICIONES_PACIENTE")).all()
    assert len(rows) == 2 and all(r.resultado == "FALLO" and r.tipoEvento == "ACCESO" for r in rows)
    assert {r.idUsuario for r in rows} == {scene.op1.idUsuario, scene.team.moderator.idUsuario}  # quién
    assert all(r.idRegistro == scene.p3.idPerfilMedicion and r.idInstitucion == scene.team.id for r in rows)  # sobre qué paciente
    assert any("HISTORIAL" in r.observacion for r in rows) and any("MEDICION" in r.observacion for r in rows)  # qué operación
    assert all(r.datosNuevos is None and r.datosPrevios is None and "97" not in (r.observacion or "") for r in rows)  # sin valores
