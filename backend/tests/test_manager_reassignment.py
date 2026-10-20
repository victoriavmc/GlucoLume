# Reasignación de pacientes por la gestión (propietario/moderador) y auditoría del propietario sin identificar al paciente en las mediciones.
#
#     python -m pytest tests/test_manager_reassignment.py -v
#
# Decisión de producto: un moderador/propietario no accede a mediciones individuales (patientAccess). Si pudiera designar unilateralmente a
# cualquier operador como responsable de un paciente AJENO, bastaría invitar a una cuenta propia, reasignarle pacientes y leer sus mediciones.
#   1. Con un responsable ACTIVO el cambio no es unilateral: la gestión PROPONE una transferencia, la acepta el operador destino y el origen
#      puede cancelarla. Hasta entonces el responsable no cambia ni el destino ve mediciones.
#   2. Los propietarios reciben un aviso, con una marca si el destino fue invitado por quien propone/asigna.
#   3. Un paciente sin responsable activo (operador desvinculado) sí se asigna directo: no hay a quién pedirle la aceptación.
#   4. La auditoría del propietario muestra QUÉ medición ocurrió y quién la hizo, pero no de qué paciente es.

import json

from sqlalchemy import select

from app.models.measurementProfile import MeasurementProfile
from app.models.profileTransfer import ProfileTransfer
from app.models.user import User
from app.services import auditQuery
from app.services import institution as institutions
from app.services import institutionActivity
from app.services import institutionPatients as patients
from app.services import measurement as measurements
from app.services import profileTransfers as transfers
from tests.legacy_offboarding import legacyRevoke
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_institution_patients import addOperator, patientData
from tests.test_institutions import expectError, freshLookupLimiter, institutional, relationOf, team  # noqa: F401
from tests.test_measurements import completeOximetry, device
from tests.test_patient_mails import sentTo, subjects


def responsibleOf(db, profile):
    db.expire_all()
    return db.get(MeasurementProfile, profile.idPerfilMedicion).idInstitucionUsuarioResponsable


def pendingOf(db, profile):
    return db.scalar(select(ProfileTransfer).where(ProfileTransfer.idPerfilMedicion == profile.idPerfilMedicion,
                                                   ProfileTransfer.estado == "PENDIENTE"))


# --- 1. El responsable activo no se cambia unilateralmente --------------------------------------------------------------------


def test_el_moderador_con_una_cuenta_propia_no_se_procura_pacientes_ajenos(db, mails, team):
    """El ataque: el moderador invita a una cuenta suya, le reasigna un paciente ajeno y lee sus mediciones. No debe poder."""
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    dev = device(db, institucion=team.id)
    completeOximetry(db, team.operator, patient.idPerfilMedicion, dev, spo2="95")
    accomplice = addOperator(db, team, "complice@example.com", "complice")  # invitado por el moderador
    accompliceUser = db.get(User, accomplice.idUsuarioInvitado)
    mine = relationOf(db, team, team.operator).idInstitucionUsuario

    patients.assignResponsible(db, team.moderator, team.id, patient.idPerfilMedicion, accomplice.idInstitucionUsuario)

    assert responsibleOf(db, patient) == mine, "el responsable activo no cambia por decisión de la gestión"
    expectError("MEDICIONES_NO_AUTORIZADAS", measurements.listPatientHistory, db, accompliceUser, team.id, patient.idPerfilMedicion)
    pending = pendingOf(db, patient)
    assert pending is not None and pending.idOperadorDestino == accomplice.idInstitucionUsuario


def test_el_operador_destino_acepta_y_recien_entonces_cambia_el_responsable(db, mails, team):
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    second = addOperator(db, team)
    secondUser = db.get(User, second.idUsuarioInvitado)
    patients.assignResponsible(db, team.moderator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario)
    pending = pendingOf(db, patient)
    # Solo el destino acepta: ni el moderador que propuso ni un tercero.
    expectError("PERMISO_INSUFICIENTE", transfers.acceptTransfer, db, team.moderator, team.id, pending.idTransferenciaPerfil)
    assert responsibleOf(db, patient) == relationOf(db, team, team.operator).idInstitucionUsuario
    transfers.acceptTransfer(db, secondUser, team.id, pending.idTransferenciaPerfil)
    assert responsibleOf(db, patient) == second.idInstitucionUsuario
    assert measurements.listPatientHistory(db, secondUser, team.id, patient.idPerfilMedicion).total == 0  # ya es su paciente


def test_el_operador_de_origen_puede_cancelar_la_propuesta(db, mails, team):
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    second = addOperator(db, team)
    patients.assignResponsible(db, team.moderator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario)
    pending = pendingOf(db, patient)
    transfers.cancelTransfer(db, team.operator, team.id, pending.idTransferenciaPerfil)
    assert pendingOf(db, patient) is None
    assert responsibleOf(db, patient) == relationOf(db, team, team.operator).idInstitucionUsuario


def test_el_destino_puede_rechazar_la_propuesta(db, mails, team):
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    second = addOperator(db, team)
    secondUser = db.get(User, second.idUsuarioInvitado)
    patients.assignResponsible(db, team.moderator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario)
    transfers.rejectTransfer(db, secondUser, team.id, pendingOf(db, patient).idTransferenciaPerfil)
    assert responsibleOf(db, patient) == relationOf(db, team, team.operator).idInstitucionUsuario


def test_el_propietario_tampoco_reasigna_unilateralmente(db, mails, team):
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    second = addOperator(db, team)
    patients.assignResponsible(db, team.owner, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario)
    assert responsibleOf(db, patient) == relationOf(db, team, team.operator).idInstitucionUsuario
    assert pendingOf(db, patient) is not None


def test_la_propuesta_deja_constancia_de_quien_la_hizo_y_de_su_origen(db, mails, team):
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    second = addOperator(db, team)
    patients.assignResponsible(db, team.moderator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario)
    event = [a for a in audits(db, "SOLICITAR_TRANSFERENCIA_PERFIL")][-1]
    data = json.loads(event.datosNuevos)
    assert event.idUsuario == team.moderator.idUsuario
    assert event.idRelacionado == relationOf(db, team, team.operator).idInstitucionUsuario  # de quién sale
    assert data["propuestaPorGestion"] == "MODERADOR" and data["destinoInvitadoPorElGestor"] is True


def test_una_propuesta_no_se_apila_sobre_otra_pendiente(db, mails, team):
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    second = addOperator(db, team)
    third = addOperator(db, team, "tercero@example.com", "tercero")
    patients.assignResponsible(db, team.moderator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario)
    expectError("TRANSFERENCIA_PENDIENTE", patients.assignResponsible, db, team.moderator, team.id, patient.idPerfilMedicion,
                third.idInstitucionUsuario)


# --- 2. Aviso al propietario con marca ---------------------------------------------------------------------------------------


def test_el_propietario_recibe_aviso_con_marca_si_el_destino_lo_invito_el_mismo_gestor(db, mails, team):
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    second = addOperator(db, team)  # invitado por el moderador
    mails.clear()
    patients.assignResponsible(db, team.moderator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario)
    [notice] = [m for m in sentTo(mails, team.owner.correoElectronico)]
    assert notice["subject"] == "Un moderador cambió el responsable de un paciente"
    assert "Atención" in notice["html"] and "misma persona" in notice["html"]
    assert patient.identificadorPseudonimo in notice["html"]
    for secret in ("Juan", "20111222", "1980-01-02"):  # nada del paciente más allá del seudónimo
        assert secret not in notice["html"] and secret not in notice["text"]
    assert "propuso" in notice["html"]  # es una propuesta: aún no se concretó


def test_sin_marca_si_el_destino_lo_invito_otra_persona(db, mails, team):
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    otherManager = institutional(db, "otro-moderador-eq@example.com", "otromoderadoreq")
    invitation = institutions.invite(db, team.owner, team.id, "MODERADOR", otherManager.correoElectronico)
    institutions.respondInvitation(db, otherManager, invitation.idInstitucionUsuario, accept=True)
    outsider = institutional(db, "invitado-por-otro@example.com", "invitadoporotro")
    invitation = institutions.invite(db, otherManager, team.id, "OPERADOR", outsider.correoElectronico)  # lo invitó OTRO moderador
    institutions.respondInvitation(db, outsider, invitation.idInstitucionUsuario, accept=True)
    target = relationOf(db, team, outsider)
    mails.clear()
    patients.assignResponsible(db, team.moderator, team.id, patient.idPerfilMedicion, target.idInstitucionUsuario)
    [notice] = sentTo(mails, team.owner.correoElectronico)
    assert "Atención" not in notice["html"]
    event = [a for a in audits(db, "SOLICITAR_TRANSFERENCIA_PERFIL")][-1]
    assert json.loads(event.datosNuevos)["destinoInvitadoPorElGestor"] is False


def test_el_gestor_que_es_propietario_no_se_avisa_a_si_mismo(db, mails, team):
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    second = addOperator(db, team)
    mails.clear()
    patients.assignResponsible(db, team.owner, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario)
    assert subjects(mails, team.owner.correoElectronico) == []


# --- 3. Paciente huérfano: asignación directa --------------------------------------------------------------------------------


def test_un_paciente_sin_responsable_activo_se_asigna_directamente_y_avisa_al_propietario(db, mails, team):
    leaving = addOperator(db, team, "saliente@example.com", "saliente")
    leavingUser = db.get(User, leaving.idUsuarioInvitado)
    patient = patients.createPatient(db, leavingUser, team.id, patientData())
    target = addOperator(db, team, "nuevo@example.com", "nuevo")
    legacyRevoke(db, team.moderator, team.id, leaving.idInstitucionUsuario)
    mails.clear()
    patients.assignResponsible(db, team.moderator, team.id, patient.idPerfilMedicion, target.idInstitucionUsuario)
    assert responsibleOf(db, patient) == target.idInstitucionUsuario
    assert pendingOf(db, patient) is None
    assert subjects(mails, team.owner.correoElectronico) == ["Un moderador cambió el responsable de un paciente"]
    change = [a for a in audits(db, "ASIGNAR_RESPONSABLE_PACIENTE") if a.idRegistro == patient.idPerfilMedicion][-1]
    assert json.loads(change.datosNuevos)["destinoInvitadoPorElGestor"] is True


# --- 4. Auditoría del propietario sin identificar al paciente en las mediciones -----------------------------------------------


def measured(db, team):
    patient = patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz"))
    dev = device(db, institucion=team.id)
    done = completeOximetry(db, team.operator, patient.idPerfilMedicion, dev, spo2="95")
    return patient, done


def test_la_auditoria_del_propietario_no_identifica_al_paciente_en_eventos_de_medicion(db, mails, team):
    patient, done = measured(db, team)
    pseudonym = patient.identificadorPseudonimo
    page = auditQuery.listInstitution(db, team.owner, team.id, modulo="MEDICIONES", tamanioPagina=100)
    assert page.items, "el propietario sigue viendo que hubo mediciones"
    for item in page.items:
        assert pseudonym not in json.dumps(item.model_dump(mode="json"), default=str), item.accion
        assert item.usuario  # sí se sabe quién la hizo
    for item in page.items:
        detail = auditQuery.detailInstitution(db, team.owner, team.id, item.idAuditoria)
        dump = json.dumps(detail.model_dump(mode="json"), default=str)
        assert pseudonym not in dump and str(patient.idPerfilMedicion) not in dump, item.accion


def test_el_intento_rechazado_de_leer_mediciones_se_audita_sin_nombrar_al_paciente(db, mails, team):
    patient, _ = measured(db, team)
    stranger = addOperator(db, team)
    expectError("MEDICIONES_NO_AUTORIZADAS", measurements.listPatientHistory, db, db.get(User, stranger.idUsuarioInvitado), team.id,
                patient.idPerfilMedicion)
    [item] = auditQuery.listInstitution(db, team.owner, team.id, accion="CONSULTAR_MEDICIONES_PACIENTE", tamanioPagina=100).items
    assert item.resultado == "FALLO" and item.rechazado and item.usuario  # el propietario ve el intento y quién lo hizo
    assert item.idEntidad is None
    detail = auditQuery.detailInstitution(db, team.owner, team.id, item.idAuditoria)
    dump = json.dumps(detail.model_dump(mode="json"), default=str)
    assert patient.identificadorPseudonimo not in dump and str(patient.idPerfilMedicion) not in dump


def test_otros_eventos_del_paciente_siguen_mostrando_su_seudonimo_al_propietario(db, mails, team):
    """El enmascarado es solo de las mediciones: el alta y la gestión administrativa del paciente se siguen auditando con su seudónimo."""
    patient, _ = measured(db, team)
    [created] = auditQuery.listInstitution(db, team.owner, team.id, accion="CREAR_PACIENTE", tamanioPagina=100).items
    assert patient.identificadorPseudonimo in (created.entidadEtiqueta or "") + (created.resumen or "")


def test_la_actividad_reciente_del_propietario_tampoco_nombra_al_paciente_de_un_acceso_rechazado(db, mails, team):
    patient, _ = measured(db, team)
    stranger = addOperator(db, team)
    expectError("MEDICIONES_NO_AUTORIZADAS", measurements.listPatientHistory, db, db.get(User, stranger.idUsuarioInvitado), team.id,
                patient.idPerfilMedicion)
    page = institutionActivity.listActivity(db, team.owner, team.id, limit=20)
    rejected = [i for i in page.items if i.rechazado]
    assert rejected, "el propietario ve el intento rechazado"
    for item in rejected:
        assert patient.identificadorPseudonimo not in (item.entidad or "")
