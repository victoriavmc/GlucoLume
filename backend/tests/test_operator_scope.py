# Separación de roles en la institución: el OPERADOR trabaja solo con SUS pacientes y ve solo SU actividad; el moderador y el operador no
# consultan la auditoría (exclusiva del propietario); el operador no administra personal ni matrices. Todo se resuelve en FastAPI (por
# identificador del usuario autenticado y de su vínculo, dentro de la institución de la ruta), nunca ocultando datos en React.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_operator_scope.py -v

from sqlalchemy import select

from app.models.user import User
from app.schemas.matrix import MatrixCreateRequest
from app.schemas.measurementProfile import PatientUpdateRequest
from app.services import dashboard as dashboards
from app.services import institution as institutions
from app.services import institutionActivity as activity
from app.services import institutionPatients as patients
from app.services import matrix as matrices
from app.services import measurement as measurements
from app.services import profileTransfers as transfers
from tests.legacy_offboarding import legacyRevoke
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_institution_patients import addOperator, otherInstitution, patientData
from tests.test_institutions import expectError, freshLookupLimiter, institutional, relationOf, team  # noqa: F401
from tests.test_measurements import completeOximetry, device, oximetry


def second(db, team):
    """Segunda operadora de la institución (relación y cuenta)."""
    relation = addOperator(db, team)
    return relation, db.get(User, relation.idUsuarioInvitado)


def titles(page):
    return [i.titulo for i in page.items]


# --- Auditoría: solo el propietario -----------------------------------------------------------------------------------


def test_auditoria_institucional_propietario_si_moderador_y_operador_no(db, mails, team, api):
    paths = (f"/api/v1/institutions/{team.id}/audit", f"/api/v1/institutions/{team.id}/audit/summary")
    assert all(api(team.owner).get(path).status_code == 200 for path in paths)
    for user in (team.moderator, team.operator):
        assert all(api(user).get(path).status_code == 403 for path in paths), user.usuario
    stranger = institutional(db, "ajeno-op@example.com", "ajenoop")
    assert all(api(stranger).get(path).status_code == 404 for path in paths)  # otra institución: ni se sabe que existe


# --- Pacientes: el operador, solo los suyos -----------------------------------------------------------------------------


def test_el_operador_lista_toda_la_institucion_pero_solo_abre_con_datos_completos_los_suyos(db, mails, team, api):
    other, otherUser = second(db, team)
    mine = patients.createPatient(db, team.operator, team.id, patientData())
    theirs = patients.createPatient(db, otherUser, team.id, patientData(dni="30.222.333", nombre="ana", apellido="paz"))
    page = patients.listPatients(db, team.operator, team.id)
    assert {p.idPerfilMedicion for p in page.items} == {mine.idPerfilMedicion, theirs.idPerfilMedicion} and page.total == 2
    # «Mis pacientes» es un filtro, no una restricción: el operador puede acotar a los suyos.
    assert [p.idPerfilMedicion for p in patients.listPatients(db, team.operator, team.id, soloMios=True).items] == [mine.idPerfilMedicion]
    assert patients.listPatients(db, team.operator, team.id, idResponsable=other.idInstitucionUsuario).total == 1
    ownRead = patients.getPatient(db, team.operator, team.id, mine.idPerfilMedicion)
    assert ownRead.puedeModificar and ownRead.esMio and ownRead.medicionesAutorizadas and ownRead.dni
    # El paciente ajeno: solo identificación administrativa; sin documento, nacimiento, edad, sexo ni salud.
    foreign = patients.getPatient(db, team.operator, team.id, theirs.idPerfilMedicion)
    assert (foreign.nombre, foreign.apellido) == ("Ana", "Paz") and foreign.responsable.idInstitucionUsuario == other.idInstitucionUsuario
    assert foreign.estado == "ACTIVO" and foreign.fechaCreacion is not None
    assert (foreign.dni, foreign.fechaNacimiento, foreign.edad, foreign.sexoModelo, foreign.fechaUltimaMedicion) == (None, None, None, None, None)
    assert foreign.esMio is False and foreign.medicionesAutorizadas is False and foreign.puedeModificar is False
    # Ni siquiera la búsqueda por documento revela a un paciente ajeno.
    assert patients.listPatients(db, team.operator, team.id, busqueda="30222333").total == 0
    assert patients.listPatients(db, team.operator, team.id, busqueda="20111222").total == 1
    http = api(team.operator).get(f"/api/v1/institutions/{team.id}/patients/{theirs.idPerfilMedicion}").json()
    assert http["dni"] is None and http["medicionesAutorizadas"] is False and http["nombre"] == "Ana"
    assert "Paz" in str(http) and "30.222.333" not in str(http)
    # Propietario y moderador conservan la gestión administrativa completa del listado.
    assert patients.listPatients(db, team.moderator, team.id).total == 2
    assert patients.getPatient(db, team.moderator, team.id, theirs.idPerfilMedicion).dni


def test_el_operador_no_accede_a_mediciones_dashboard_ni_estadisticas_de_un_paciente_ajeno(db, mails, team):
    other, otherUser = second(db, team)
    theirs = patients.createPatient(db, otherUser, team.id, patientData())
    dev = device(db, institucion=team.id)
    done = completeOximetry(db, otherUser, theirs.idPerfilMedicion, dev)
    expectError("MEDICIONES_NO_AUTORIZADAS", oximetry, db, team.operator, theirs.idPerfilMedicion, dev)
    expectError("MEDICIONES_NO_AUTORIZADAS", measurements.getMeasurement, db, team.operator, done.idMedicion)
    for call in (measurements.listPatientHistory, measurements.patientStatistics, dashboards.patientDashboard):
        expectError("MEDICIONES_NO_AUTORIZADAS", call, db, team.operator, team.id, theirs.idPerfilMedicion)
    expectError("PERMISO_INSUFICIENTE", patients.updatePatient, db, team.operator, team.id, theirs.idPerfilMedicion,
                PatientUpdateRequest(nombre="Otro"))


def test_el_operador_no_ve_pacientes_de_otra_institucion(db, mails, team):
    foreignInstitution, foreignOperator, _ = otherInstitution(db)
    foreign = patients.createPatient(db, foreignOperator, foreignInstitution.idInstitucion, patientData(dni="50.444.555"))
    expectError("INSTITUCION_NO_ENCONTRADA", patients.getPatient, db, team.operator, foreignInstitution.idInstitucion, foreign.idPerfilMedicion)
    expectError("PACIENTE_NO_ENCONTRADO", patients.getPatient, db, team.operator, team.id, foreign.idPerfilMedicion)  # id de otra institución con la ruta propia


def test_el_operador_registra_una_medicion_autorizada_de_su_paciente(db, mails, team):
    mine = patients.createPatient(db, team.operator, team.id, patientData())
    detail = oximetry(db, team.operator, mine.idPerfilMedicion, device(db, institucion=team.id))
    assert detail.puedeOperar and detail.idPerfilMedicion == mine.idPerfilMedicion


def test_el_paciente_transferido_deja_de_ser_consultable_para_el_operador_anterior(db, mails, team):
    other, otherUser = second(db, team)
    created = patients.createPatient(db, team.operator, team.id, patientData())
    dev = device(db, institucion=team.id)
    done = completeOximetry(db, team.operator, created.idPerfilMedicion, dev)
    item = transfers.requestTransfer(db, team.operator, team.id, created.idPerfilMedicion, other.idInstitucionUsuario, None)
    transfers.acceptTransfer(db, otherUser, team.id, item.idTransferenciaPerfil)
    newer = completeOximetry(db, otherUser, created.idPerfilMedicion, dev)
    # El anterior solo conserva la identificación administrativa; no accede a datos sensibles ni a mediciones (ni las propias ni las nuevas).
    seen = patients.getPatient(db, team.operator, team.id, created.idPerfilMedicion)
    assert seen.nombre == "Juan" and seen.dni is None and seen.fechaUltimaMedicion is None and not seen.medicionesAutorizadas
    assert patients.listPatients(db, team.operator, team.id).total == 1 and patients.listPatients(db, team.operator, team.id, soloMios=True).total == 0
    for measurement in (done, newer):
        expectError("MEDICIONES_NO_AUTORIZADAS", measurements.getMeasurement, db, team.operator, measurement.idMedicion)
    expectError("MEDICIONES_NO_AUTORIZADAS", measurements.listPatientHistory, db, team.operator, team.id, created.idPerfilMedicion)
    # La trazabilidad de lo que hizo se conserva en su dashboard y en su actividad (sin abrir el paciente).
    mineDashboard = dashboards.operatorDashboard(db, team.operator, team.id, "me")
    assert mineDashboard.pacientesAsignados == 0 and mineDashboard.medicionesRealizadas == 1
    assert "Medición realizada" in titles(activity.listActivity(db, team.operator, team.id, limit=20))
    # El nuevo responsable atribuye solo las suyas: las anteriores siguen siendo del operador original.
    assert dashboards.operatorDashboard(db, otherUser, team.id, "me").medicionesRealizadas == 1
    # Y el nuevo sí consulta al paciente y todo su historial.
    assert patients.getPatient(db, otherUser, team.id, created.idPerfilMedicion).puedeModificar
    assert measurements.getMeasurement(db, otherUser, done.idMedicion).idMedicion == done.idMedicion


# --- Actividad propia ---------------------------------------------------------------------------------------------------


def test_el_operador_ve_solo_su_propia_actividad(db, mails, team, api):
    other, otherUser = second(db, team)
    dev = device(db, institucion=team.id)
    mine = patients.createPatient(db, team.operator, team.id, patientData())
    theirs = patients.createPatient(db, otherUser, team.id, patientData(dni="30.222.333", nombre="ana", apellido="paz"))
    completeOximetry(db, team.operator, mine.idPerfilMedicion, dev)
    completeOximetry(db, otherUser, theirs.idPerfilMedicion, dev)  # de otro operador
    matrices.createMatrix(db, team.owner, MatrixCreateRequest(ambito="INSTITUCION", idInstitucion=team.id, nombre="Del propietario"))
    institutional(db, "nuevo-mod@example.com", "nuevomod")
    institutions.invite(db, team.owner, team.id, "MODERADOR", "nuevo-mod@example.com")  # administrativa del propietario

    own = activity.listActivity(db, team.operator, team.id, limit=20)
    assert titles(own).count("Medición realizada") == 1 and "Paciente registrado" in titles(own)
    assert {i.usuario for i in own.items} == {own.items[0].usuario}  # todo lo hizo la misma persona: él
    assert not any(i.categoria in ("MATRICES", "MODERADORES", "SEGURIDAD") for i in own.items)
    assert all(i.idAuditoria is None and not i.rechazado for i in own.items)
    # Su actividad no depende de parámetros: el endpoint ignora cualquier intento de pedir la de otro.
    http = api(team.operator).get(f"/api/v1/institutions/{team.id}/activity?limite=20&idUsuario={otherUser.idUsuario}&usuario={otherUser.usuario}")
    assert http.status_code == 200 and [i["titulo"] for i in http.json()["items"]] == titles(own)
    # El otro operador tiene la suya, con su propia medición, y propietario y moderador no ven cada medición.
    assert titles(activity.listActivity(db, otherUser, team.id, limit=20)).count("Medición realizada") == 1
    for viewer in (team.owner, team.moderator):
        assert "Medición realizada" not in titles(activity.listActivity(db, viewer, team.id, limit=20))
    # Solo se ofrece abrir la medición de un paciente que sigue a su cargo.
    measurementItem = next(i for i in own.items if i.categoria == "MEDICIONES")
    assert measurementItem.ruta and measurementItem.ruta.startswith(f"pacientes/{mine.idPerfilMedicion}/mediciones/")


def test_la_actividad_del_operador_incluye_transferencias_recibidas_e_iniciadas_y_pacientes_asignados(db, mails, team):
    other, otherUser = second(db, team)
    created = patients.createPatient(db, team.operator, team.id, patientData())
    transfers.requestTransfer(db, team.operator, team.id, created.idPerfilMedicion, other.idInstitucionUsuario, None)
    initiated = activity.listActivity(db, team.operator, team.id, limit=20)
    received = activity.listActivity(db, otherUser, team.id, limit=20)
    assert "Transferencia de paciente solicitada" in titles(initiated)   # la inició él
    assert "Transferencia de paciente solicitada" in titles(received)    # la recibió el otro operador
    # Un tercer operador no ve esa transferencia.
    third, thirdUser = second_with(db, team, "tercero@example.com", "tercero")
    assert "Transferencia de paciente solicitada" not in titles(activity.listActivity(db, thirdUser, team.id, limit=20))
    # Pacientes que otro (moderador) le asigna a su cargo.
    leaving, leavingUser = second_with(db, team, "saliente@example.com", "saliente")
    reassigned = patients.createPatient(db, leavingUser, team.id, patientData(dni="40.333.444", nombre="eva", apellido="luna"))
    legacyRevoke(db, team.moderator, team.id, leaving.idInstitucionUsuario)  # paciente huérfano: asignación directa
    patients.assignResponsible(db, team.moderator, team.id, reassigned.idPerfilMedicion, third.idInstitucionUsuario)
    assert "Responsable de un paciente reasignado" in titles(activity.listActivity(db, thirdUser, team.id, limit=20))
    assert "Responsable de un paciente reasignado" not in titles(activity.listActivity(db, otherUser, team.id, limit=20))


def second_with(db, team, email, usuario):
    relation = addOperator(db, team, email, usuario)
    return relation, db.get(User, relation.idUsuarioInvitado)


def test_un_operador_no_consulta_el_dashboard_de_otro_operador(db, mails, team, api):
    other, otherUser = second(db, team)
    mine = relationOf(db, team, team.operator)
    expectError("PERMISO_INSUFICIENTE", dashboards.operatorDashboard, db, team.operator, team.id, str(other.idInstitucionUsuario))
    assert dashboards.operatorDashboard(db, team.operator, team.id, str(mine.idInstitucionUsuario)).esPropio  # el propio por su id: sí
    assert api(team.operator).get(f"/api/v1/institutions/{team.id}/operators/{other.idInstitucionUsuario}/dashboard").status_code == 403
    assert api(team.operator).get(f"/api/v1/institutions/{team.id}/operators/me/dashboard").status_code == 200
    assert api(team.moderator).get(f"/api/v1/institutions/{team.id}/operators/{other.idInstitucionUsuario}/dashboard").status_code == 200
    # El dashboard general de la institución no es del operador.
    assert api(team.operator).get(f"/api/v1/institutions/{team.id}/dashboard").status_code == 403


def test_el_detalle_de_la_institucion_no_entrega_estadisticas_generales_al_operador(db, mails, team):
    other, otherUser = second(db, team)
    patients.createPatient(db, team.operator, team.id, patientData())
    patients.createPatient(db, otherUser, team.id, patientData(dni="30.222.333", nombre="ana", apellido="paz"))
    own = institutions.getDetail(db, team.operator, team.id)
    assert (own.cantidadModeradores, own.cantidadOperadores, own.cantidadPacientes) == (0, 0, 1)  # solo sus pacientes
    general = institutions.getDetail(db, team.moderator, team.id)
    assert (general.cantidadModeradores, general.cantidadOperadores, general.cantidadPacientes) == (1, 2, 2)


# --- Lo que el operador no administra -----------------------------------------------------------------------------------


def test_el_operador_no_administra_matrices_ni_personal(db, mails, team, api):
    created = matrices.createMatrix(db, team.owner, MatrixCreateRequest(ambito="INSTITUCION", idInstitucion=team.id, nombre="Hospital X"))
    expectError("PERMISO_INSUFICIENTE", matrices.createMatrix, db, team.operator,
                MatrixCreateRequest(ambito="INSTITUCION", idInstitucion=team.id, nombre="Mía"))
    for action in (matrices.activate, matrices.deactivate, matrices.archive, matrices.newVersion, matrices.validateMatrix):
        expectError("MATRIZ_NO_ENCONTRADA", action, db, team.operator, created.idMatriz)  # para él, la matriz no existe
    assert api(team.operator).get(f"/api/v1/institutions/{team.id}/matrices").status_code == 403
    institutional(db, "nueva-op@example.com", "nuevaop")
    for call, args in ((institutions.invite, ("OPERADOR", "nueva-op@example.com")), (institutions.listMembers, ())):
        expectError("PERMISO_INSUFICIENTE", call, db, team.operator, team.id, *args)
    assert api(team.operator).get(f"/api/v1/institutions/{team.id}/personnel").status_code == 403
    assert api(team.operator).get(f"/api/v1/institutions/{team.id}/invitations").status_code == 403
    # La matriz que se aplica a sus mediciones sí la consulta (sin reglas ni administración).
    assert institutions.ROLE_PERMISSIONS[institutions.ROL_OPERADOR].count("CONSULTAR_MATRIZ") == 1
