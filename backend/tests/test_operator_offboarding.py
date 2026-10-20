# Desvinculación de operadores con reasignación obligatoria de sus pacientes: el backend no permite dar de baja a un operador que conserva
# pacientes; el camino válido reasigna a TODOS (elegidos por quien gestiona) y desvincula en una sola transacción; las transferencias
# pendientes se respetan; los operadores desvinculados antes del control se regularizan a pedido; la autoría de las mediciones no cambia.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_operator_offboarding.py -v

from sqlalchemy import func, select

from app.models.audit import Audit
from app.models.institutionUser import InstitutionUser
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.patientReassignment import PatientReassignment
from app.models.profileTransfer import ProfileTransfer
from app.models.user import User
from app.schemas.offboarding import OffboardAssignment, OffboardRequest
from app.services import dashboard as dashboards
from app.services import institution as institutions
from app.services import institutionPatients as patients
from app.services import measurement as measurements
from app.services import operatorOffboarding as offboarding
from tests.legacy_offboarding import legacyRevoke
from tests.test_account_deletion import audits, db, engine, mails, reload  # noqa: F401 - fixtures
from tests.test_account_lifecycle import newPatient, tasks
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_institution_patients import addOperator
from tests.test_institutions import expectError, freshLookupLimiter, relationOf, team  # noqa: F401
from tests.test_measurements import completeOximetry, device


def request(*pairs, note=None):
    return OffboardRequest(asignaciones=[OffboardAssignment(idPerfilMedicion=p.idPerfilMedicion, idOperadorNuevo=t.idInstitucionUsuario)
                                         for p, t in pairs], observacion=note)


def stateOf(db, relation):
    db.expire_all()
    return db.get(InstitutionUser, relation.idInstitucionUsuario).estadoRelacion


def responsibleOf(db, patient):
    db.expire_all()
    return db.get(MeasurementProfile, patient.idPerfilMedicion).idInstitucionUsuarioResponsable


def accepted(db):
    db.expire_all()
    return list(db.scalars(select(ProfileTransfer).where(ProfileTransfer.estado == "ACEPTADA")))


# --- 1. Sin pacientes -----------------------------------------------------------------------------------------------------------


def test_un_operador_sin_pacientes_se_desvincula_sin_reasignar(db, mails, team):
    operator = relationOf(db, team, team.operator)
    plan = offboarding.plan(db, team.moderator, team.id, operator.idInstitucionUsuario)
    assert plan.cantidadPacientes == 0 and plan.bloqueo is None
    result = offboarding.offboard(db, team.moderator, team.id, operator.idInstitucionUsuario, OffboardRequest())
    assert result.reasignados == 0 and stateOf(db, operator) == "BAJA"


def test_la_baja_directa_de_un_operador_sin_pacientes_sigue_funcionando(db, mails, team):
    operator = relationOf(db, team, team.operator)
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", operator.idInstitucionUsuario)
    assert stateOf(db, operator) == "BAJA"


# --- 2. Un paciente / varios ----------------------------------------------------------------------------------------------------


def test_no_se_puede_desvincular_a_un_operador_con_un_paciente_y_conserva_su_responsabilidad(db, mails, team):
    patient = newPatient(db, team, team.operator)
    operator = relationOf(db, team, team.operator)
    error = expectError("PACIENTES_ASIGNADOS", institutions.revokeMember, db, team.moderator, team.id, "OPERADOR", operator.idInstitucionUsuario)
    assert "Antes de desvincularlo, debés reasignarlos" in error.message and "1 paciente asignado" in error.message
    assert stateOf(db, operator) == "ACTIVO" and responsibleOf(db, patient) == operator.idInstitucionUsuario
    assert tasks(db) == []  # y no queda ninguna tarea pendiente a medias
    assert audits(db, "REVOCAR_MIEMBRO_INSTITUCION")[-1].resultado == "FALLO"  # el intento rechazado queda auditado


def test_desvincular_con_un_paciente_lo_reasigna_y_recien_entonces_da_la_baja(db, mails, team):
    patient = newPatient(db, team, team.operator)
    operator = relationOf(db, team, team.operator)
    target = addOperator(db, team)
    plan = offboarding.plan(db, team.owner, team.id, operator.idInstitucionUsuario)
    assert (plan.cantidadPacientes, plan.bloqueo, [d.idInstitucionUsuario for d in plan.destinos]) == (1, None, [target.idInstitucionUsuario])
    mails.clear()
    result = offboarding.offboard(db, team.owner, team.id, operator.idInstitucionUsuario, request((patient, target), note="cobertura"))
    assert result.reasignados == 1 and result.destinos[0].idOperadorNuevo == target.idInstitucionUsuario and result.destinos[0].cantidad == 1
    assert stateOf(db, operator) == "BAJA" and responsibleOf(db, patient) == target.idInstitucionUsuario
    assert tasks(db) == []  # reasignado en el acto: no queda nada pendiente
    [transfer] = accepted(db)
    assert transfer.idOperadorDestino == target.idInstitucionUsuario and transfer.observacion == "Cobertura"
    assert len(audits(db, "REASIGNAR_PACIENTES_DESVINCULACION")) == 1 and len(audits(db, "ASIGNAR_RESPONSABLE_PACIENTE")) == 1
    assert any(m["to"] == "segundo@example.com" for m in mails)  # el nuevo operador se entera


def test_desvincular_con_varios_pacientes_a_un_mismo_operador(db, mails, team):
    patientsList = [newPatient(db, team, team.operator, dni=f"20.1{n}.222", nombre=f"p{n}", apellido="x") for n in range(3)]
    operator = relationOf(db, team, team.operator)
    target = addOperator(db, team)
    result = offboarding.offboard(db, team.moderator, team.id, operator.idInstitucionUsuario, request(*[(p, target) for p in patientsList]))
    assert result.reasignados == 3 and stateOf(db, operator) == "BAJA"
    assert {responsibleOf(db, p) for p in patientsList} == {target.idInstitucionUsuario} and len(accepted(db)) == 3


def test_distribuir_los_pacientes_entre_varios_operadores(db, mails, team):
    a, b, c = (newPatient(db, team, team.operator, dni=f"20.1{n}.222", nombre=f"p{n}", apellido="x") for n in range(3))
    operator = relationOf(db, team, team.operator)
    first = addOperator(db, team, "uno@example.com", "unouno")
    second = addOperator(db, team, "dos@example.com", "dostres")
    plan = offboarding.plan(db, team.moderator, team.id, operator.idInstitucionUsuario)
    assert {d.idInstitucionUsuario for d in plan.destinos} == {first.idInstitucionUsuario, second.idInstitucionUsuario}
    result = offboarding.offboard(db, team.moderator, team.id, operator.idInstitucionUsuario, request((a, first), (b, second), (c, first)))
    assert {d.idOperadorNuevo: d.cantidad for d in result.destinos} == {first.idInstitucionUsuario: 2, second.idInstitucionUsuario: 1}
    assert (responsibleOf(db, a), responsibleOf(db, b), responsibleOf(db, c)) == (
        first.idInstitucionUsuario, second.idInstitucionUsuario, first.idInstitucionUsuario)
    assert stateOf(db, operator) == "BAJA"


# --- 3. Sin operadores disponibles ----------------------------------------------------------------------------------------------


def test_sin_otro_operador_habilitado_se_bloquea_la_desvinculacion(db, mails, team):
    patient = newPatient(db, team, team.operator)
    operator = relationOf(db, team, team.operator)
    plan = offboarding.plan(db, team.moderator, team.id, operator.idInstitucionUsuario)
    assert plan.bloqueo == "SIN_OPERADOR_DISPONIBLE" and plan.destinos == [] and plan.cantidadPacientes == 1
    expectError("SIN_OPERADOR_DISPONIBLE", offboarding.offboard, db, team.moderator, team.id, operator.idInstitucionUsuario, OffboardRequest())
    assert stateOf(db, operator) == "ACTIVO" and responsibleOf(db, patient) == operator.idInstitucionUsuario


def test_un_operador_dado_de_baja_o_de_otra_institucion_no_es_un_destino_valido(db, mails, team):
    patient = newPatient(db, team, team.operator)
    operator = relationOf(db, team, team.operator)
    gone = addOperator(db, team, "ido@example.com", "idoido")
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", gone.idInstitucionUsuario)
    expectError("SIN_OPERADOR_DISPONIBLE", offboarding.offboard, db, team.moderator, team.id, operator.idInstitucionUsuario, request((patient, gone)))
    other = addOperator(db, team, "valido@example.com", "validovalido")
    expectError("OPERADOR_NO_DISPONIBLE", offboarding.offboard, db, team.moderator, team.id, operator.idInstitucionUsuario, request((patient, gone)))
    expectError("OPERADOR_NO_DISPONIBLE", offboarding.offboard, db, team.moderator, team.id, operator.idInstitucionUsuario, request((patient, operator)))
    assert stateOf(db, operator) == "ACTIVO" and responsibleOf(db, patient) == operator.idInstitucionUsuario
    offboarding.offboard(db, team.moderator, team.id, operator.idInstitucionUsuario, request((patient, other)))
    assert stateOf(db, operator) == "BAJA"


# --- 4. Transferencias pendientes -----------------------------------------------------------------------------------------------


def test_una_transferencia_pendiente_de_aceptacion_no_cuenta_como_reasignada(db, mails, team):
    pending = newPatient(db, team, team.operator, dni="20.111.222", nombre="pendiente", apellido="x")
    free = newPatient(db, team, team.operator, dni="20.333.444", nombre="libre", apellido="y")
    operator = relationOf(db, team, team.operator)
    destination = addOperator(db, team)
    other = addOperator(db, team, "tres@example.com", "trestres")
    patients.assignResponsible(db, team.moderator, team.id, pending.idPerfilMedicion, destination.idInstitucionUsuario)  # propuesta pendiente
    plan = offboarding.plan(db, team.moderator, team.id, operator.idInstitucionUsuario)
    assert plan.bloqueo == "TRANSFERENCIAS_PENDIENTES" and plan.transferenciasPendientes == 1
    assert {p.idPerfilMedicion: p.transferenciaPendiente for p in plan.pacientes} == {pending.idPerfilMedicion: True, free.idPerfilMedicion: False}
    expectError("PACIENTE_EN_TRANSFERENCIA", offboarding.offboard, db, team.moderator, team.id, operator.idInstitucionUsuario,
                request((pending, other), (free, other)))
    # Nada cambió: ni el responsable de ninguno ni la solicitud, que sigue esperando la respuesta del destinatario.
    assert stateOf(db, operator) == "ACTIVO"
    assert responsibleOf(db, pending) == responsibleOf(db, free) == operator.idInstitucionUsuario
    assert db.scalar(select(func.count()).select_from(ProfileTransfer).where(ProfileTransfer.estado == "PENDIENTE")) == 1
    # Cuando el destinatario acepta, ese paciente ya es suyo y el resto se reasigna sin problema.
    from app.services import profileTransfers as transfers
    transfer = db.scalar(select(ProfileTransfer).where(ProfileTransfer.estado == "PENDIENTE"))
    transfers.acceptTransfer(db, db.get(User, destination.idUsuarioInvitado), team.id, transfer.idTransferenciaPerfil)
    result = offboarding.offboard(db, team.moderator, team.id, operator.idInstitucionUsuario, request((free, other)))
    assert result.reasignados == 1 and stateOf(db, operator) == "BAJA"
    assert responsibleOf(db, pending) == destination.idInstitucionUsuario and responsibleOf(db, free) == other.idInstitucionUsuario


# --- 5. Intentos directos por la API --------------------------------------------------------------------------------------------


def test_la_api_rechaza_la_baja_directa_y_las_reasignaciones_incompletas_o_desactualizadas(db, mails, team, api):
    a = newPatient(db, team, team.operator, dni="20.111.222", nombre="a", apellido="x")
    b = newPatient(db, team, team.operator, dni="20.333.444", nombre="b", apellido="y")
    operator = relationOf(db, team, team.operator)
    target = addOperator(db, team)
    base = f"/api/v1/institutions/{team.id}/operators/{operator.idInstitucionUsuario}"

    direct = api(team.moderator).delete(base)
    assert direct.status_code == 409 and direct.json()["codigo"] == "PACIENTES_ASIGNADOS"
    incomplete = api(team.moderator).post(f"{base}/offboard", json={"asignaciones": [
        {"idPerfilMedicion": str(a.idPerfilMedicion), "idOperadorNuevo": str(target.idInstitucionUsuario)}]})
    assert incomplete.status_code == 409 and incomplete.json()["codigo"] == "REASIGNACION_INCOMPLETA"
    nothing = api(team.moderator).post(f"{base}/offboard", json={})
    assert nothing.status_code == 409 and nothing.json()["codigo"] == "REASIGNACION_INCOMPLETA"
    stale = api(team.moderator).post(f"{base}/offboard", json={"asignaciones": [
        {"idPerfilMedicion": str(p), "idOperadorNuevo": str(target.idInstitucionUsuario)}
        for p in (a.idPerfilMedicion, b.idPerfilMedicion, "00000000-0000-4000-8000-000000000000")]})
    assert stale.status_code == 409 and stale.json()["codigo"] == "REASIGNACION_DESACTUALIZADA"
    repeated = api(team.moderator).post(f"{base}/offboard", json={"asignaciones": [
        {"idPerfilMedicion": str(a.idPerfilMedicion), "idOperadorNuevo": str(target.idInstitucionUsuario)}] * 2})
    assert repeated.status_code == 409 and repeated.json()["codigo"] == "REASIGNACION_DESACTUALIZADA"
    assert stateOf(db, operator) == "ACTIVO"

    # Un paciente que cambió de responsable mientras se armaba la lista, o uno nuevo, también se detecta.
    c = newPatient(db, team, team.operator, dni="20.555.666", nombre="c", apellido="z")
    late = api(team.moderator).post(f"{base}/offboard", json={"asignaciones": [
        {"idPerfilMedicion": str(p.idPerfilMedicion), "idOperadorNuevo": str(target.idInstitucionUsuario)} for p in (a, b)]})
    assert late.status_code == 409 and late.json()["codigo"] == "REASIGNACION_INCOMPLETA" and stateOf(db, operator) == "ACTIVO"

    ok = api(team.moderator).post(f"{base}/offboard", json={"asignaciones": [
        {"idPerfilMedicion": str(p.idPerfilMedicion), "idOperadorNuevo": str(target.idInstitucionUsuario)} for p in (a, b, c)]})
    assert ok.status_code == 200 and ok.json()["reasignados"] == 3 and stateOf(db, operator) == "BAJA"
    retry = api(team.moderator).post(f"{base}/offboard", json={})  # un reintento tras el éxito no hace nada más
    assert retry.status_code == 404


def test_la_consulta_y_la_desvinculacion_exigen_permiso_de_gestion(db, mails, team, api):
    newPatient(db, team, team.operator)
    operator = relationOf(db, team, team.operator)
    other = addOperator(db, team)
    base = f"/api/v1/institutions/{team.id}/operators"
    assert api(team.operator).get(f"{base}/{other.idInstitucionUsuario}/offboarding").status_code == 403
    assert api(team.operator).post(f"{base}/{other.idInstitucionUsuario}/offboard", json={}).status_code == 403
    assert api(team.operator).delete(f"{base}/{other.idInstitucionUsuario}").status_code == 403
    plan = api(team.owner).get(f"{base}/{operator.idInstitucionUsuario}/offboarding")
    assert plan.status_code == 200 and plan.json()["cantidadPacientes"] == 1
    dumped = plan.json()
    assert not any(key in str(dumped) for key in ("dni", "fechaNacimiento", "sexo"))  # solo identificación administrativa


# --- 6. Fallo durante la reasignación -------------------------------------------------------------------------------------------


def test_un_fallo_durante_la_reasignacion_no_deja_nada_a_medias_y_se_puede_reintentar(db, mails, team, monkeypatch):
    a = newPatient(db, team, team.operator, dni="20.111.222", nombre="a", apellido="x")
    b = newPatient(db, team, team.operator, dni="20.333.444", nombre="b", apellido="y")
    operator = relationOf(db, team, team.operator)
    target = addOperator(db, team)
    original = patients.applyAssignment
    calls = []

    def failing(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("falla simulada a mitad de la reasignación")
        return original(*args, **kwargs)

    monkeypatch.setattr(patients, "applyAssignment", failing)
    try:
        offboarding.offboard(db, team.moderator, team.id, operator.idInstitucionUsuario, request((a, target), (b, target)))
    except RuntimeError:
        pass
    else:
        raise AssertionError("tenía que fallar")
    assert stateOf(db, operator) == "ACTIVO"  # sigue vinculado…
    assert responsibleOf(db, a) == responsibleOf(db, b) == operator.idInstitucionUsuario  # …y con la responsabilidad intacta (el primer cambio se deshizo)
    assert accepted(db) == [] and audits(db, "REASIGNAR_PACIENTES_DESVINCULACION") == [] and audits(db, "ASIGNAR_RESPONSABLE_PACIENTE") == []
    monkeypatch.setattr(patients, "applyAssignment", original)
    result = offboarding.offboard(db, team.moderator, team.id, operator.idInstitucionUsuario, request((a, target), (b, target)))  # el reintento funciona
    assert result.reasignados == 2 and stateOf(db, operator) == "BAJA"


# --- 7. Operadores desvinculados antes del control ---------------------------------------------------------------------------------


def test_un_operador_ya_desvinculado_con_pacientes_se_detecta_y_se_regulariza_sin_reasignar_nada(db, mails, team, api):
    patientsList = [newPatient(db, team, team.operator, dni=f"20.1{n}.222", nombre=f"p{n}", apellido="x") for n in range(2)]
    operator = relationOf(db, team, team.operator)
    target = addOperator(db, team)
    legacyRevoke(db, team.moderator, team.id, operator.idInstitucionUsuario, openTasks=False)  # baja heredada: pacientes a cargo y sin tarea
    path = f"/api/v1/institutions/{team.id}/reassignments"

    overview = api(team.moderator).get(path).json()
    assert overview["pendientes"] == 0 and overview["sinRegularizar"] == 2
    [group] = overview["gruposSinRegularizar"]
    assert group["pacientes"] == 2 and group["idOperadorAnterior"] == str(operator.idInstitucionUsuario) and group["operadorAnterior"]
    assert tasks(db) == [] and all(responsibleOf(db, p) == operator.idInstitucionUsuario for p in patientsList)  # detectar no cambia nada

    # El operador no regulariza; una persona de gestión sí, y solo a pedido: crea las tareas, no reasigna.
    assert api(team.operator).post(f"{path}/regularize", json={"idOperadorAnterior": str(operator.idInstitucionUsuario)}).status_code in (401, 403, 404)
    assert api(team.moderator).post(f"{path}/regularize", json={"idOperadorAnterior": str(target.idInstitucionUsuario)}).status_code == 404  # activo
    done = api(team.moderator).post(f"{path}/regularize", json={"idOperadorAnterior": str(operator.idInstitucionUsuario)})
    assert done.status_code == 200 and done.json()["pacientesPendientes"] == 2
    assert len(tasks(db, "PENDIENTE")) == 2 and all(responsibleOf(db, p) == operator.idInstitucionUsuario for p in patientsList)
    assert len(audits(db, "REGULARIZAR_REASIGNACIONES")) == 1
    again = api(team.moderator).post(f"{path}/regularize", json={"idOperadorAnterior": str(operator.idInstitucionUsuario)}).json()
    assert again["pacientesPendientes"] == 0  # idempotente
    overview = api(team.moderator).get(path).json()
    assert overview["pendientes"] == 2 and overview["sinRegularizar"] == 0

    # Y se resuelven con el flujo habitual, eligiendo un operador activo.
    items = api(team.moderator).get(f"{path}/items").json()["items"]
    resolved = api(team.moderator).post(f"{path}/assign", json={"idsReasignacion": [i["idReasignacionPaciente"] for i in items],
                                                                "idOperadorNuevo": str(target.idInstitucionUsuario)})
    assert resolved.json()["reasignados"] == 2
    assert api(team.moderator).get(path).json()["sinRegularizar"] == 0
    assert all(responsibleOf(db, p) == target.idInstitucionUsuario for p in patientsList)


def test_un_operador_desvinculado_con_tareas_pendientes_no_figura_como_inconsistente(db, mails, team, api):
    newPatient(db, team, team.operator)
    operator = relationOf(db, team, team.operator)
    legacyRevoke(db, team.moderator, team.id, operator.idInstitucionUsuario)  # baja heredada CON sus tareas pendientes
    overview = api(team.moderator).get(f"/api/v1/institutions/{team.id}/reassignments").json()
    assert overview["pendientes"] == 1 and overview["sinRegularizar"] == 0 and overview["gruposSinRegularizar"] == []


# --- 8. Autoría e historiales ---------------------------------------------------------------------------------------------------


def test_reasignar_no_cambia_la_autoria_de_las_mediciones_ni_el_historial(db, mails, team):
    patient = newPatient(db, team, team.operator)
    operator = relationOf(db, team, team.operator)
    target = addOperator(db, team)
    targetUser = db.get(User, target.idUsuarioInvitado)
    dev = device(db, institucion=team.id)
    done = completeOximetry(db, team.operator, patient.idPerfilMedicion, dev, spo2="95")

    def authors():
        db.expire_all()
        return sorted((a.idRegistro, a.idRelacionado) for a in db.scalars(select(Audit).where(Audit.accion == "INICIAR_MEDICION")))

    before = authors()
    assert before == [(done.idMedicion, operator.idInstitucionUsuario)]
    offboarding.offboard(db, team.moderator, team.id, operator.idInstitucionUsuario, request((patient, target)))
    assert authors() == before  # el operador histórico sigue siendo el autor
    assert db.scalar(select(func.count()).select_from(Measurement).where(Measurement.idPerfilMedicion == patient.idPerfilMedicion)) == 1
    assert measurements.listPatientHistory(db, targetUser, team.id, patient.idPerfilMedicion).total == 1  # el nuevo responsable ve el historial
    # En las estadísticas, esa medición sigue atribuida al operador desvinculado y no al nuevo.
    stats = dashboards.institutionDashboard(db, team.owner, team.id, 30).administrativo
    byId = {o.idInstitucionUsuario: o for o in stats.porOperador}
    assert byId[operator.idInstitucionUsuario].total == 1 and not byId[operator.idInstitucionUsuario].activo
    assert byId[target.idInstitucionUsuario].total == 0 and byId[target.idInstitucionUsuario].pacientesAsignados == 1
    assert db.scalar(select(func.count()).select_from(PatientReassignment)) == 0
