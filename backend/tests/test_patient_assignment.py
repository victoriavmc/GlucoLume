# Alta y asignación de pacientes según el rol: el OPERADOR que registra queda siempre como responsable (se resuelve con su sesión y su vínculo
# activo; si la solicitud trae a otro operador se rechaza); el MODERADOR (y el propietario) designan al responsable entre los operadores ACTIVOS
# de la institución. «Quién registró» y «quién es responsable» son datos distintos y los dos quedan auditados.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_patient_assignment.py -v

import json

from sqlalchemy import select

from app.models.audit import Audit
from app.models.measurementProfile import MeasurementProfile
from app.models.profileTransfer import ProfileTransfer
from app.models.user import User
from app.services import auditQuery
from app.services import institution as institutions
from app.services import institutionPatients as patients
from app.services import measurement as measurements
from app.services import profileTransfers as transfers
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_institution_patients import addOperator, otherInstitution, patientData
from tests.test_institutions import expectError, freshLookupLimiter, institutional, relationOf, team  # noqa: F401
from tests.test_measurements import completeOximetry, device


def second(db, team, email="op2@example.com", usuario="opdos"):
    relation = addOperator(db, team, email, usuario)
    return relation, db.get(User, relation.idUsuarioInvitado)


def responsibleOf(db, created):
    return reload(db, MeasurementProfile, created.idPerfilMedicion).idInstitucionUsuarioResponsable


def creationEvent(db, created):
    return db.scalars(select(Audit).where(Audit.accion == "CREAR_PACIENTE", Audit.idRegistro == created.idPerfilMedicion)).one()


# --- 1-2. Operador: asignación automática ---------------------------------------------------------------------------------


def test_el_operador_que_registra_queda_automaticamente_como_responsable(db, mails, team):
    mine = relationOf(db, team, team.operator).idInstitucionUsuario
    created = patients.createPatient(db, team.operator, team.id, patientData(nombre="paciente", apellido="tres"))
    assert created.responsable.idInstitucionUsuario == mine and created.esMio and created.medicionesAutorizadas
    assert responsibleOf(db, created) == mine
    assert (created.registradoPor.nombre, created.registradoPor.rolInstitucion) == (team.operator.nombre, "OPERADOR")  # registrado por él
    # Puede indicar su propio vínculo (equivale a no indicar nada); la asignación nunca depende de lo enviado.
    explicit = patients.createPatient(db, team.operator, team.id, patientData(dni="30.111.111"))
    assert responsibleOf(db, explicit) == mine


def test_el_operador_no_puede_registrar_pacientes_a_nombre_de_otro_operador(db, mails, team, api):
    other, otherUser = second(db, team)
    base = patientData(dni="40.222.333")
    forged = base.model_copy(update={"idInstitucionUsuarioResponsable": other.idInstitucionUsuario})
    expectError("PERMISO_INSUFICIENTE", patients.createPatient, db, team.operator, team.id, forged)
    assert patients.listPatients(db, team.operator, team.id).total == 0  # no se creó nada
    # Igual por HTTP: modificar la solicitud para asignar al compañero se rechaza.
    body = {"nombre": "Ana", "apellido": "Paz", "idInstitucionUsuarioResponsable": str(other.idInstitucionUsuario)}
    denied = api(team.operator).post(f"/api/v1/institutions/{team.id}/patients", json=body)
    assert denied.status_code == 403
    assert api(team.operator).post(f"/api/v1/institutions/{team.id}/patients", json={"nombre": "Ana", "apellido": "Paz"}).status_code == 201
    assert patients.listPatients(db, team.operator, team.id).total == 1 and patients.listPatients(db, otherUser, team.id, soloMios=True).total == 0
    # El intento rechazado queda auditado con quién lo hizo y el motivo.
    attempt = [a for a in audits(db, "CREAR_PACIENTE") if a.resultado == "FALLO"]
    assert attempt and all(a.idUsuario == team.operator.idUsuario and "ASIGNACION_A_OTRO_OPERADOR" in a.observacion for a in attempt)


# --- 3-5. Moderador: asignación manual --------------------------------------------------------------------------------------


def test_el_moderador_registra_y_elige_un_operador_activo(db, mails, team, api):
    other, otherUser = second(db, team)
    request = patientData(nombre="paciente", apellido="cuatro", dni="50.111.222").model_copy(update={"idInstitucionUsuarioResponsable": other.idInstitucionUsuario})
    created = patients.createPatient(db, team.moderator, team.id, request)
    assert created.responsable.idInstitucionUsuario == other.idInstitucionUsuario and responsibleOf(db, created) == other.idInstitucionUsuario
    # Registrado por el moderador (autor del alta), responsable el operador elegido: no se confunden.
    assert created.registradoPor.rolInstitucion == "MODERADOR" and created.registradoPor.nombre == team.moderator.nombre
    assert not created.esMio and not created.medicionesAutorizadas
    # Las opciones del selector: solo operadores activos de la institución, con nombre y apellido.
    options = patients.assignableOperators(db, team.moderator, team.id)
    assert {o.idInstitucionUsuario for o in options} == {relationOf(db, team, team.operator).idInstitucionUsuario, other.idInstitucionUsuario}
    assert all(o.nombre and o.apellido for o in options)
    # El moderador debe elegir (no hay asignación implícita para él).
    expectError("RESPONSABLE_REQUERIDO", patients.createPatient, db, team.moderator, team.id, patientData(dni="50.111.999"))
    assert api(team.moderator).post(f"/api/v1/institutions/{team.id}/patients", json={"nombre": "Eva", "apellido": "Gil"}).status_code == 422


def test_el_moderador_no_puede_elegir_operadores_de_otra_institucion_inactivos_o_dados_de_baja(db, mails, team):
    foreignInstitution, foreignOperator, foreignRelation = otherInstitution(db)
    pending = second(db, team, "baja@example.com", "bajaop")
    inactive = relationOf(db, team, pending[1])
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", inactive.idInstitucionUsuario)  # dado de baja
    owner = relationOf(db, team, team.owner)
    for target in (foreignRelation.idInstitucionUsuario, inactive.idInstitucionUsuario, owner.idInstitucionUsuario,
                   relationOf(db, team, team.moderator).idInstitucionUsuario):  # otra institución, de baja, propietario, moderador
        request = patientData(dni="60.111.222").model_copy(update={"idInstitucionUsuarioResponsable": target})
        expectError("OPERADOR_NO_DISPONIBLE", patients.createPatient, db, team.moderator, team.id, request)
    assert patients.listPatients(db, team.moderator, team.id).total == 0
    # Los dados de baja y los de otra institución no se ofrecen en el selector.
    assert {o.idInstitucionUsuario for o in patients.assignableOperators(db, team.moderator, team.id)} == {
        relationOf(db, team, team.operator).idInstitucionUsuario}


def test_sin_operadores_activos_no_se_puede_completar_una_asignacion(db, mails, team):
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", relationOf(db, team, team.operator).idInstitucionUsuario)
    assert patients.assignableOperators(db, team.moderator, team.id) == []
    expectError("RESPONSABLE_REQUERIDO", patients.createPatient, db, team.moderator, team.id, patientData())


# --- 6-9. Registro, responsable, mediciones y auditoría --------------------------------------------------------------------


def test_se_conserva_quien_registro_y_quien_es_responsable_y_ambos_quedan_auditados(db, mails, team):
    other, otherUser = second(db, team)
    byOperator = patients.createPatient(db, team.operator, team.id, patientData(dni="70.111.111", nombre="op", apellido="alta"))
    byModerator = patients.createPatient(db, team.moderator, team.id, patientData(dni="70.222.222", nombre="mod", apellido="alta").model_copy(
        update={"idInstitucionUsuarioResponsable": other.idInstitucionUsuario}))
    for created, author, responsible, role in ((byOperator, team.operator, relationOf(db, team, team.operator), "OPERADOR"),
                                               (byModerator, team.moderator, other, "MODERADOR")):
        event = creationEvent(db, created)
        data = json.loads(event.datosNuevos)
        assert event.idUsuario == author.idUsuario and event.idInstitucion == team.id  # quién realizó el alta
        assert data["idInstitucionUsuarioResponsable"] == str(responsible.idInstitucionUsuario) and data["rolRegistrante"] == role
        assert data["idInstitucionUsuarioRegistrante"] == str(relationOf(db, team, author).idInstitucionUsuario)
    # El padrón lo muestra: registrado por / operador responsable (datos administrativos, para todo el personal).
    page = patients.listPatients(db, otherUser, team.id)
    by = {p.nombre: p for p in page.items}
    assert by["Mod"].registradoPor.rolInstitucion == "MODERADOR" and by["Mod"].esMio and by["Op"].registradoPor.rolInstitucion == "OPERADOR"
    # El detalle de auditoría del propietario muestra a ambos con nombre.
    detail = auditQuery.detailInstitution(db, team.owner, team.id, creationEvent(db, byModerator).idAuditoria)
    labels = {c.etiqueta: c for c in detail.cambios}
    assert "Responsable institucional" in labels and "Registrado por" in labels
    assert labels["Registrado por"].nuevo.texto and labels["Responsable institucional"].nuevo.texto
    assert detail.usuario and team.moderator.nombre in detail.usuario  # quién realizó el alta


def test_el_responsable_consulta_las_mediciones_y_el_resto_solo_los_datos_administrativos(db, mails, team):
    other, otherUser = second(db, team)
    request = patientData(dni="80.111.222").model_copy(update={"idInstitucionUsuarioResponsable": other.idInstitucionUsuario})
    created = patients.createPatient(db, team.moderator, team.id, request)  # lo registra el moderador, responde otherUser
    done = completeOximetry(db, otherUser, created.idPerfilMedicion, device(db, institucion=team.id), spo2="96")
    assert measurements.listPatientHistory(db, otherUser, team.id, created.idPerfilMedicion).total == 1  # el responsable
    expectError("MEDICIONES_NO_AUTORIZADAS", measurements.listPatientHistory, db, team.moderator, team.id, created.idPerfilMedicion)  # quien lo registró no
    expectError("MEDICIONES_NO_AUTORIZADAS", measurements.listPatientHistory, db, team.operator, team.id, created.idPerfilMedicion)
    seen = patients.getPatient(db, team.operator, team.id, created.idPerfilMedicion)
    assert (seen.nombre, seen.dni, seen.fechaUltimaMedicion) == ("Juan", None, None) and seen.responsable.idInstitucionUsuario == other.idInstitucionUsuario
    assert done.idMedicion is not None


def test_los_cambios_de_responsable_conservan_historial_autoria_y_mediciones(db, mails, team):
    other, otherUser = second(db, team)
    created = patients.createPatient(db, team.operator, team.id, patientData(dni="90.111.222"))
    done = completeOximetry(db, team.operator, created.idPerfilMedicion, device(db, institucion=team.id), spo2="95")
    # El operador no reasigna por su cuenta: usa la transferencia, que el destinatario acepta.
    expectError("PERMISO_INSUFICIENTE", patients.assignResponsible, db, team.operator, team.id, created.idPerfilMedicion, other.idInstitucionUsuario)
    # El moderador gestiona la asignación, pero con un responsable ACTIVO no la impone: propone y el operador destino acepta.
    mine = relationOf(db, team, team.operator).idInstitucionUsuario
    patients.assignResponsible(db, team.moderator, team.id, created.idPerfilMedicion, other.idInstitucionUsuario)
    assert responsibleOf(db, created) == mine  # nada cambió todavía
    pending = db.scalar(select(ProfileTransfer).where(ProfileTransfer.idPerfilMedicion == created.idPerfilMedicion))
    assert pending.estado == "PENDIENTE" and pending.idOperadorDestino == other.idInstitucionUsuario
    proposal = [a for a in audits(db, "SOLICITAR_TRANSFERENCIA_PERFIL") if a.idRegistro == pending.idTransferenciaPerfil][0]
    assert proposal.idUsuario == team.moderator.idUsuario and proposal.idRelacionado == mine  # quién propuso y de quién sale
    transfers.acceptTransfer(db, otherUser, team.id, pending.idTransferenciaPerfil)
    assert responsibleOf(db, created) == other.idInstitucionUsuario
    row = db.scalar(select(ProfileTransfer).where(ProfileTransfer.idPerfilMedicion == created.idPerfilMedicion))
    assert row.estado == "ACEPTADA" and row.idOperadorDestino == other.idInstitucionUsuario and row.fechaTransferencia is not None
    change = [a for a in audits(db, "CAMBIAR_RESPONSABLE_PERFIL") if a.idRegistro == created.idPerfilMedicion][0]
    old, new = json.loads(change.datosPrevios), json.loads(change.datosNuevos)
    assert old["idInstitucionUsuarioResponsable"] == str(mine)  # responsable anterior
    assert new["idInstitucionUsuarioResponsable"] == str(other.idInstitucionUsuario)  # responsable nuevo
    assert change.idUsuario == otherUser.idUsuario and change.fechaHora is not None  # quién (el destino que aceptó) y cuándo
    # La autoría de las mediciones y quién registró al paciente no cambian.
    first = [a for a in audits(db, "INICIAR_MEDICION") if a.idRegistro == done.idMedicion][0]
    assert first.idUsuario == team.operator.idUsuario
    assert patients.getPatient(db, otherUser, team.id, created.idPerfilMedicion).registradoPor.rolInstitucion == "OPERADOR"
    # Una transferencia pedida por el operador anterior también deja el historial.
    item = transfers.requestTransfer(db, otherUser, team.id, created.idPerfilMedicion, relationOf(db, team, team.operator).idInstitucionUsuario, None)
    transfers.acceptTransfer(db, team.operator, team.id, item.idTransferenciaPerfil)
    assert db.scalar(select(ProfileTransfer).where(ProfileTransfer.idPerfilMedicion == created.idPerfilMedicion).order_by(ProfileTransfer.fechaPeticion.desc())) is not None
    assert len(db.scalars(select(ProfileTransfer).where(ProfileTransfer.idPerfilMedicion == created.idPerfilMedicion)).all()) == 2
