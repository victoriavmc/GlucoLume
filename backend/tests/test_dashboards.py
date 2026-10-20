# Dashboards por ámbito: personal, familiar, institucional (general, por operador y por paciente).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_dashboards.py -v
#
# Todo se calcula sobre Medicion; las mediciones de prueba se completan con señal PPG sintética (tests/ppg.py) por el
# mismo camino que usa el Arduino (addSamples + finishMeasurement), nunca con resultados escritos a mano.

import json
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import update

from app.models.measurement import Measurement
from app.models.user import User
from app.schemas.measurement import MeasurementFinish, MeasurementStart
from app.services import dashboard as dashboards
from app.services import group as groups
from app.services import institutionPatients as patients
from app.services import measurement as measurements
from app.services import profileTransfers as transfers
from app.utils.timeZone import nowForDb
from tests.legacy_offboarding import legacyRevoke
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_audit_names import named
from tests.test_groups import create as createGroup
from tests.test_groups import join, person, share
from tests.test_institution_patients import addOperator, otherInstitution, patientData
from tests.test_institutions import expectError, freshLookupLimiter, institutional, relationOf, team  # noqa: F401
from tests.test_measurements import completeOximetry, consumer, device, oximetry, samples, signalSamples  # noqa: F401


def backdate(db, idMedicion, days):
    db.execute(update(Measurement).where(Measurement.idMedicion == idMedicion).values(
        fechaHoraInicio=nowForDb() - timedelta(days=days)))
    db.commit()


# --- Personal ---------------------------------------------------------------------------------------------------


def test_dashboard_personal_solo_muestra_mediciones_propias_y_estadisticas_reales(db, mails, consumer):
    user, profileId = consumer
    other = person(db, "otra")
    otherProfile = measurements.getOwnProfile(db, other).idPerfilMedicion
    completeOximetry(db, other, otherProfile, device(db), spo2="88", hr=100)  # ajena: no debe aparecer
    first = completeOximetry(db, user, profileId, device(db), spo2="96", hr=60)
    second = completeOximetry(db, user, profileId, device(db), spo2="98", hr=80)
    backdate(db, first.idMedicion, 40)  # fuera del período de 30 días
    cancelled = oximetry(db, user, profileId, device(db))
    measurements.cancelMeasurement(db, user, cancelled.idMedicion)

    data = dashboards.personalDashboard(db, user, 30)
    assert data.perfilDisponible and data.resumen.total == 3 and data.resumen.completadas == 2
    assert data.resumen.enPeriodo == 1  # solo la de hace menos de 30 días
    assert data.resumen.ultimaSpo2.valor == pytest.approx(98.0, abs=0.3) and data.resumen.ultimaFrecuencia.valor == 80
    assert data.resumen.ultimaGlucosa is None  # oximetría: sin glucosa, no un cero
    assert data.estadisticas.cantidadMediciones == 1 and data.estadisticas.spo2.promedio == pytest.approx(98.0, abs=0.3)
    assert 88 not in [m.spo2 for m in data.recientes if m.spo2] and len(data.recientes) == 2  # solo guardadas (la cancelada no)
    wide = dashboards.personalDashboard(db, user, 90)
    assert wide.estadisticas.cantidadMediciones == 2 and wide.estadisticas.spo2.minimo == pytest.approx(96.0, abs=0.3)
    custom = dashboards.personalDashboard(db, user, 30, desde=date.today() - timedelta(days=45), hasta=date.today() - timedelta(days=35))
    assert custom.estadisticas.cantidadMediciones == 1 and custom.periodo.desde is not None
    expectError("PERIODO_INVALIDO", dashboards.personalDashboard, db, user, 15)
    assert second.idMedicion  # la más reciente


def test_dashboard_personal_lista_las_pruebas_demo_pero_no_las_suma_a_los_indicadores(db, mails, consumer):
    user, profileId = consumer
    real = completeOximetry(db, user, profileId, device(db), spo2="97", hr=70)
    demo = completeOximetry(db, user, profileId, device(db), spo2="99", hr=76)
    db.execute(update(Measurement).where(Measurement.idMedicion == demo.idMedicion).values(
        origenGlucosa="DEMO", glucosaDispositivo=114, unidadGlucosa="mg/dL"))
    db.commit()
    data = dashboards.personalDashboard(db, user, 30)
    # La última guardada es la DEMO (más reciente) y está identificada; los indicadores experimentales no la incluyen.
    assert data.ultimaGuardada.idMedicion == demo.idMedicion and data.ultimaGuardada.esDemo is True
    assert {m.idMedicion: m.esDemo for m in data.recientes} == {demo.idMedicion: True, real.idMedicion: False}
    assert data.pruebasDemo == 1 and data.resumen.completadas == 1
    assert data.resumen.ultimaSpo2.valor == pytest.approx(97.0, abs=0.3) and data.resumen.ultimaGlucosa is None
    assert data.estadisticas.cantidadMediciones == 1 and data.estadisticas.glucosa.cantidad == 0


def test_dashboard_personal_con_solo_pruebas_demo_distingue_ambas_situaciones(db, mails, consumer):
    user, profileId = consumer
    demo = completeOximetry(db, user, profileId, device(db), spo2="99", hr=76)
    db.execute(update(Measurement).where(Measurement.idMedicion == demo.idMedicion).values(
        origenGlucosa="DEMO", glucosaDispositivo=114, unidadGlucosa="mg/dL"))
    db.commit()
    data = dashboards.personalDashboard(db, user, 30)
    assert data.resumen.completadas == 0 and data.resumen.ultimaSpo2 is None  # nada experimental
    assert data.pruebasDemo == 1 and data.ultimaGuardada.esDemo and len(data.recientes) == 1  # pero sí hay pruebas


def test_dashboard_personal_sin_mediciones_no_muestra_ceros(db, mails, consumer):
    user, _ = consumer
    data = dashboards.personalDashboard(db, user, 30)
    assert data.resumen.total == 0 and data.resumen.ultimaMedicion is None and data.resumen.ultimaSpo2 is None
    assert data.estadisticas.cantidadMediciones == 0 and data.estadisticas.spo2.promedio is None and data.recientes == []


def test_una_cuenta_sin_perfil_o_institucional_recibe_un_dashboard_vacio(db, mails, team):
    data = dashboards.personalDashboard(db, team.owner, 30)
    assert not data.perfilDisponible and data.resumen is None


def test_el_dashboard_personal_se_actualiza_al_completar_una_medicion(db, mails, consumer):
    user, profileId = consumer
    assert dashboards.personalDashboard(db, user).resumen.completadas == 0
    completeOximetry(db, user, profileId, device(db), spo2="97", hr=72)
    after = dashboards.personalDashboard(db, user)
    assert after.resumen.completadas == 1 and after.resumen.ultimaMedicion is not None and len(after.recientes) == 1


# --- Familiar ---------------------------------------------------------------------------------------------------


def test_dashboard_familiar_muestra_a_todos_con_sus_permisos_y_solo_lo_autorizado(db, mails):
    ana, beto, carla = person(db, "ana"), person(db, "beto"), person(db, "carla")
    group = createGroup(db, ana)
    join(db, ana, group.idGrupo, beto)
    join(db, ana, group.idGrupo, carla)
    for user, spo2 in ((beto, "96"), (carla, "99"), (ana, "92")):
        completeOximetry(db, user, measurements.getOwnProfile(db, user).idPerfilMedicion, device(db), spo2=spo2)
    share(db, beto, group.idGrupo, compartePerfil=True)  # solo datos básicos
    share(db, carla, group.idGrupo, comparteUltimaMedicion=True, comparteHistorial=True)

    data = dashboards.groupDashboard(db, ana, group.idGrupo, 30)
    assert data.integrantesActivos == 3 and data.administradores == 1 and data.miembros == 2
    names = {(m.compartePerfil, m.comparteUltimaMedicion, m.comparteHistorial) for m in data.integrantes}
    assert names == {(False, False, False), (True, False, False), (False, True, True)}
    # Solo Carla autorizó mostrar mediciones: la actividad no incluye a Beto (solo perfil) ni a Ana (no comparte).
    assert len(data.actividadReciente) == 1 and float(data.actividadReciente[0].medicion.spo2) == pytest.approx(99.0, abs=0.3)
    assert data.comparteUltimaMedicion == 1 and data.comparteHistorial == 1
    # Con un solo integrante compartiendo historial no hay estadística grupal (expondría a una persona).
    assert data.agregado is None and "al menos 2" in data.motivoSinAgregado
    assert audits(db, "CONSULTAR_DASHBOARD_GRUPO")

    share(db, beto, group.idGrupo, comparteHistorial=True)
    both = dashboards.groupDashboard(db, ana, group.idGrupo, 30)
    assert sorted(both.agregado.participantes) == ["Victoria Cortés", "Victoria Cortés"]
    assert both.agregado.estadisticas.cantidadMediciones == 2
    assert both.agregado.estadisticas.spo2.promedio == pytest.approx(97.5, abs=0.5)  # (96 + 99) / 2, sin Ana (no comparte)

    # Revocar corta las consultas siguientes de inmediato.
    share(db, carla, group.idGrupo)
    revoked = dashboards.groupDashboard(db, ana, group.idGrupo, 30)
    assert revoked.agregado is None and revoked.comparteHistorial == 1 and len(revoked.actividadReciente) == 1


def test_dashboard_familiar_exige_ser_integrante_activo(db, mails):
    ana, intruso = person(db, "ana"), person(db, "intruso")
    group = createGroup(db, ana)
    expectError("GRUPO_NO_ENCONTRADO", dashboards.groupDashboard, db, intruso, group.idGrupo, 30)


# --- Institucional ----------------------------------------------------------------------------------------------


def institutionData(db, team):
    named(db, team.operator, "Juan", "Pérez")
    second = addOperator(db, team)
    secondUser = named(db, db.get(User, second.idUsuarioInvitado), "María", "González")
    dev = device(db, institucion=team.id)
    return second, secondUser, dev


def measure(db, operator, profileId, dev, spo2="97", hr=72):
    started = measurements.startMeasurement(db, operator, MeasurementStart(idPerfilMedicion=profileId, idDispositivo=dev.idDispositivo))
    measurements.addSamples(db, operator, started.idMedicion, signalSamples(hr, spo2))
    return measurements.finishMeasurement(db, operator, started.idMedicion, MeasurementFinish())


def test_dashboard_institucional_agrega_solo_su_institucion_y_no_identifica_pacientes(db, mails, team):
    second, secondUser, dev = institutionData(db, team)
    mine = patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz"))
    measure(db, team.operator, mine.idPerfilMedicion, dev, "96", 70)
    measure(db, team.operator, mine.idPerfilMedicion, dev, "98", 80)
    bad = measurements.startMeasurement(db, team.operator, MeasurementStart(idPerfilMedicion=mine.idPerfilMedicion, idDispositivo=dev.idDispositivo))
    measurements.cancelMeasurement(db, team.operator, bad.idMedicion)
    # Otra institución con su propia actividad: no se mezcla.
    foreign, foreignOperator, _ = otherInstitution(db)
    other = patients.createPatient(db, foreignOperator, foreign.idInstitucion, patientData(dni="99888777"))
    measure(db, foreignOperator, other.idPerfilMedicion, device(db, institucion=foreign.idInstitucion), "85", 110)

    data = dashboards.institutionDashboard(db, team.owner, team.id, 30)
    assert (data.pacientesActivos, data.operadoresActivos, data.moderadoresActivos) == (1, 2, 1)
    assert (data.dispositivosRegistrados, data.dispositivosOperativos) == (1, 1)
    assert data.medicionesTotal == 3 and data.porEstado == {"COMPLETADA": 2, "CANCELADA": 1} and data.porModo == {"OXIMETRIA": 3}
    assert data.medicionesHoy == 3 and data.medicionesEnPeriodo == 3 and data.ultimaActividad is not None
    # Un solo paciente medido (menos del mínimo): no se informan estadísticas de salud ni serie diaria que lo identifiquen.
    assert data.agregadosProtegidos and data.estadisticas.cantidadMediciones == 0 and data.serie == []
    assert data.estadisticas.spo2.promedio is None
    loads = {f"{o.nombre} {o.apellido}": o for o in data.porOperador}
    assert loads["Juan Pérez"].mediciones == 3 and loads["Juan Pérez"].pacientesAsignados == 1
    assert loads["María González"].mediciones == 0
    dumped = data.model_dump_json()
    for secret in ("Rosa", "Díaz", str(mine.idPerfilMedicion), mine.identificadorPseudonimo, "20.111.222"):
        assert secret not in dumped
    # Con el mínimo de pacientes distintos, las estadísticas sí se informan (y siguen siendo solo de esta institución).
    for number in range(4):
        more = patients.createPatient(db, team.operator, team.id, patientData(dni=f"3011133{number}", nombre=f"q{number}", apellido="y"))
        measure(db, team.operator, more.idPerfilMedicion, dev, "97", 75)
    full = dashboards.institutionDashboard(db, team.owner, team.id, 30)
    assert not full.agregadosProtegidos and full.estadisticas.cantidadMediciones == 6 and sum(d.total for d in full.serie) == 7
    assert 85 not in [full.estadisticas.spo2.minimo]  # nada de la otra institución
    assert dashboards.institutionDashboard(db, team.moderator, team.id).medicionesTotal == 7
    expectError("PERMISO_INSUFICIENTE", dashboards.institutionDashboard, db, team.operator, team.id)
    expectError("INSTITUCION_NO_ENCONTRADA", dashboards.institutionDashboard, db, team.owner, foreign.idInstitucion)


def test_la_actividad_historica_del_operador_no_pasa_al_nuevo_responsable_tras_una_transferencia(db, mails, team):
    second, secondUser, dev = institutionData(db, team)
    patient = patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz"))
    measure(db, team.operator, patient.idPerfilMedicion, dev)
    measure(db, team.operator, patient.idPerfilMedicion, dev)
    sent = transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario, None)
    pendingBefore = dashboards.operatorDashboard(db, team.owner, team.id, str(second.idInstitucionUsuario))
    assert pendingBefore.transferencias.recibidasPendientes == 1 and pendingBefore.pacientesAsignados == 0
    transfers.acceptTransfer(db, secondUser, team.id, sent.idTransferenciaPerfil)
    measure(db, secondUser, patient.idPerfilMedicion, dev)

    juan = dashboards.operatorDashboard(db, team.operator, team.id, "me")
    maria = dashboards.operatorDashboard(db, secondUser, team.id, "me")
    # Quien supervisa (propietario) ve solo la carga de trabajo del operador: sin pacientes ni mediciones individuales.
    supervised = dashboards.operatorDashboard(db, team.owner, team.id, str(second.idInstitucionUsuario))
    assert (supervised.pacientesAsignados, supervised.medicionesRealizadas) == (1, 1)
    assert supervised.pacientes == [] and supervised.realizadas == [] and supervised.ultimasDePacientes == [] and not supervised.esPropio
    # El paciente es de María ahora, pero las dos primeras mediciones siguen siendo de Juan.
    assert juan.pacientesAsignados == 0 and juan.pacientes == [] and maria.pacientesAsignados == 1
    assert juan.medicionesRealizadas == 2 and maria.medicionesRealizadas == 1
    assert (juan.transferencias.enviadas, juan.transferencias.enviadasPendientes) == (1, 0)
    assert (maria.transferencias.recibidas, maria.transferencias.recibidasPendientes) == (1, 0)
    assert [p.identificadorPseudonimo for p in maria.pacientes] == [patient.identificadorPseudonimo]
    assert maria.pacientes[0].nombre == "Rosa"  # su paciente: datos identificativos
    # La autoría histórica no autoriza leer valores de salud (patientAccess.py): sin paciente a cargo no hay filas con resultados;
    # los conteos históricos (medicionesRealizadas) se conservan.
    assert juan.realizadas == []
    assert {r.operador for r in maria.ultimasDePacientes} == {"Juan Pérez", "María González"}  # trazabilidad por medición
    assert maria.dispositivosDisponibles == 1 and maria.ultimaActividad is not None and maria.esPropio


def test_permisos_del_dashboard_de_operador(db, mails, team):
    second, secondUser, dev = institutionData(db, team)
    mine = dashboards.operatorDashboard(db, team.operator, team.id, "me")
    assert mine.esPropio and mine.operador.nombre == "Juan"
    expectError("PERMISO_INSUFICIENTE", dashboards.operatorDashboard, db, team.operator, team.id, str(second.idInstitucionUsuario))
    assert dashboards.operatorDashboard(db, team.moderator, team.id, str(second.idInstitucionUsuario)).operador.apellido == "González"
    expectError("MIEMBRO_NO_ENCONTRADO", dashboards.operatorDashboard, db, team.owner, team.id, str(uuid.uuid4()))
    expectError("MIEMBRO_NO_ENCONTRADO", dashboards.operatorDashboard, db, team.owner, team.id, "no-es-un-uuid")
    expectError("MIEMBRO_NO_ENCONTRADO", dashboards.operatorDashboard, db, team.owner, team.id, str(relationOf(db, team, team.moderator).idInstitucionUsuario))
    foreign, foreignOperator, foreignRelation = otherInstitution(db)
    expectError("MIEMBRO_NO_ENCONTRADO", dashboards.operatorDashboard, db, team.owner, team.id, str(foreignRelation.idInstitucionUsuario))
    expectError("INSTITUCION_NO_ENCONTRADA", dashboards.operatorDashboard, db, foreignOperator, team.id, "me")


def test_dashboard_de_un_operador_desvinculado_conserva_su_actividad(db, mails, team):
    from app.services import institution as institutions

    second, secondUser, dev = institutionData(db, team)
    patient = patients.createPatient(db, secondUser, team.id, patientData())
    measure(db, secondUser, patient.idPerfilMedicion, dev)
    patients.assignResponsible(db, team.moderator, team.id, patient.idPerfilMedicion, relationOf(db, team, team.operator).idInstitucionUsuario)
    legacyRevoke(db, team.owner, team.id, second.idInstitucionUsuario)
    data = dashboards.operatorDashboard(db, team.owner, team.id, str(second.idInstitucionUsuario))
    assert not data.operador.activo and data.operador.nombre == "María" and data.medicionesRealizadas == 1
    general = dashboards.institutionDashboard(db, team.owner, team.id, 30)
    assert any(o.nombre == "María" and not o.activo and o.mediciones == 1 for o in general.porOperador)


def test_dashboard_del_paciente_perfil_historial_operador_y_transferencias(db, mails, team):
    second, secondUser, dev = institutionData(db, team)
    patient = patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz"))
    measure(db, team.operator, patient.idPerfilMedicion, dev, "95", 66)
    measure(db, team.operator, patient.idPerfilMedicion, dev, "99", 84)
    sent = transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario, None)
    transfers.acceptTransfer(db, secondUser, team.id, sent.idTransferenciaPerfil)
    measure(db, secondUser, patient.idPerfilMedicion, dev, "97", 72)

    # Información de salud individual: solo el operador responsable vigente (María); ni el propietario ni el operador anterior.
    for actor in (team.owner, team.moderator, team.operator):
        expectError("MEDICIONES_NO_AUTORIZADAS", dashboards.patientDashboard, db, actor, team.id, patient.idPerfilMedicion, 30)
    data = dashboards.patientDashboard(db, secondUser, team.id, patient.idPerfilMedicion, 30)
    assert (data.perfil.nombre, data.perfil.apellido, data.perfil.identificadorPseudonimo) == ("Rosa", "Díaz", patient.identificadorPseudonimo)
    assert data.perfil.responsable.nombre == "María" and data.perfil.fechaNacimiento is not None
    assert data.resumen.total == 3 and data.resumen.completadas == 3 and data.resumen.ultimaSpo2.valor == pytest.approx(97.0, abs=0.3)
    assert data.estadisticas.cantidadMediciones == 3 and data.estadisticas.spo2.minimo == pytest.approx(95.0, abs=0.3)
    assert [h.operador for h in data.historial] == ["María González", "Juan Pérez", "Juan Pérez"]  # más reciente primero
    assert all(h.dispositivo == dev.codigoDispositivo for h in data.historial)
    assert [(t.estado, t.tipo) for t in data.transferencias] == [("ACEPTADA", "TRANSFERENCIA")]
    assert (data.transferencias[0].origen.nombre, data.transferencias[0].destino.nombre) == ("Juan", "María")
    assert audits(db, "CONSULTAR_PACIENTE")  # acceso a datos identificativos auditado, sin los datos
    # Medición de otro paciente: no aparece.
    third = patients.createPatient(db, secondUser, team.id, patientData(dni="30111222"))
    measure(db, secondUser, third.idPerfilMedicion, dev, "90", 100)
    assert dashboards.patientDashboard(db, secondUser, team.id, patient.idPerfilMedicion, 30).resumen.total == 3


def test_el_paciente_de_otro_operador_y_de_otra_institucion_no_se_consulta(db, mails, team):
    second, secondUser, dev = institutionData(db, team)
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    # Solo el responsable vigente accede (y ve el nombre); moderador, propietario y otro operador, no.
    assert dashboards.patientDashboard(db, team.operator, team.id, patient.idPerfilMedicion).perfil.nombre == "Juan"
    for actor in (team.moderator, team.owner, secondUser):
        expectError("MEDICIONES_NO_AUTORIZADAS", dashboards.patientDashboard, db, actor, team.id, patient.idPerfilMedicion)
    foreign, foreignOperator, _ = otherInstitution(db)
    expectError("PACIENTE_NO_ENCONTRADO", dashboards.patientDashboard, db, foreignOperator, foreign.idInstitucion, patient.idPerfilMedicion)
    expectError("INSTITUCION_NO_ENCONTRADA", dashboards.patientDashboard, db, team.owner, foreign.idInstitucion, patient.idPerfilMedicion)
    expectError("PACIENTE_NO_ENCONTRADO", dashboards.patientDashboard, db, team.owner, team.id, uuid.uuid4())


def test_rutas_http_dashboards(db, mails, team, api):
    second, secondUser, dev = institutionData(db, team)
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    measure(db, team.operator, patient.idPerfilMedicion, dev)
    base = f"/api/v1/institutions/{team.id}"
    assert api(team.owner).get(f"{base}/dashboard").json()["medicionesTotal"] == 1
    assert api(team.moderator).get(f"{base}/dashboard").status_code == 200
    assert api(team.operator).get(f"{base}/dashboard").status_code == 403
    assert api(team.operator).get(f"{base}/operators/me/dashboard").json()["pacientesAsignados"] == 1
    assert api(team.operator).get(f"{base}/operators/{second.idInstitucionUsuario}/dashboard").status_code == 403
    assert api(team.operator).get(f"{base}/patients/{patient.idPerfilMedicion}/dashboard").json()["perfil"]["nombre"] == "Juan"
    for actor in (team.owner, team.moderator, secondUser):
        denied = api(actor).get(f"{base}/patients/{patient.idPerfilMedicion}/dashboard")
        assert denied.status_code == 403 and denied.json()["codigo"] == "MEDICIONES_NO_AUTORIZADAS"
    assert api(team.owner).get(f"{base}/dashboard", params={"dias": 15}).status_code == 422
    own = makeUser(db, email="solo@example.com", usuario="solo")
    assert api(own).get("/api/v1/measurements/dashboard").json()["resumen"]["total"] == 0
    assert json.dumps(api(own).get("/api/v1/measurements/dashboard").json())
