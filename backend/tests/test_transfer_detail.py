# Transferencias de pacientes: detalle enriquecido, auditoría que distingue asignación inicial, solicitud, aceptación,
# rechazo y cancelación, y rutas de detalle independientes (HTTP).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_transfer_detail.py -v

import json

from app.models.measurementProfile import MeasurementProfile
from app.models.user import User
from app.services import auditQuery
from app.services import institution as institutions
from app.services import institutionPatients as patients
from app.services import profileTransfers as transfers
from tests.legacy_offboarding import legacyRevoke
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_audit_names import named
from tests.test_institution_patients import addOperator, otherInstitution, patientData
from tests.test_institutions import expectError, freshLookupLimiter, institutional, relationOf, team  # noqa: F401


def scenario(db, team):
    """Juan Pérez (operador del equipo) y María González (segundo operador); un paciente a cargo de Juan."""
    named(db, team.operator, "Juan", "Pérez")
    second = addOperator(db, team)
    secondUser = named(db, db.get(User, second.idUsuarioInvitado), "María", "González")
    patient = patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz"))
    return second, secondUser, patient


def responsible(db, patient):
    db.expire_all()
    return db.get(MeasurementProfile, patient.idPerfilMedicion).idInstitucionUsuarioResponsable


def auditItems(db, team, action):
    return auditQuery.listInstitution(db, team.owner, team.id, accion=action, tamanioPagina=100).items


def test_el_alta_con_asignacion_inicial_no_se_presenta_como_transferencia(db, mails, team):
    _, _, patient = scenario(db, team)
    item = auditItems(db, team, "CREAR_PACIENTE")[0]
    assert "asignación inicial" in item.accionEtiqueta
    assert item.resumen == f"Se asignó el paciente {patient.identificadorPseudonimo} al operador Juan Pérez."
    assert not auditItems(db, team, "ACEPTAR_TRANSFERENCIA_PERFIL")
    assert not auditItems(db, team, "SOLICITAR_TRANSFERENCIA_PERFIL")


def test_ciclo_completo_solicitud_aceptacion_rechazo_y_cancelacion(db, mails, team):
    second, secondUser, patient = scenario(db, team)
    pseudonym = patient.identificadorPseudonimo
    juan = relationOf(db, team, team.operator).idInstitucionUsuario
    sent = transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario, "Cambio de turno")

    # Pendiente: el responsable todavía no cambia y no hay cambio efectivo registrado.
    assert responsible(db, patient) == juan
    request = auditItems(db, team, "SOLICITAR_TRANSFERENCIA_PERFIL")[0]
    assert request.accionEtiqueta == "Solicitud de transferencia"
    assert request.resumen == (f"Juan Pérez solicitó transferir al paciente Rosa Díaz, identificado como {pseudonym}, a María González. "
                               f"La responsabilidad permanecerá con Juan Pérez hasta que María González acepte la solicitud.")
    assert not auditItems(db, team, "CAMBIAR_RESPONSABLE_PERFIL")
    pending = transfers.getTransfer(db, team.operator, team.id, sent.idTransferenciaPerfil)
    assert pending.estado == "PENDIENTE" and pending.fechaRespuesta is None and pending.fechaTransferencia is None
    assert [step.clave for step in pending.historial] == ["SOLICITADA"]

    transfers.acceptTransfer(db, secondUser, team.id, sent.idTransferenciaPerfil)
    assert responsible(db, patient) == second.idInstitucionUsuario
    accepted = auditItems(db, team, "ACEPTAR_TRANSFERENCIA_PERFIL")[0]
    assert accepted.accionEtiqueta == "Transferencia aceptada"
    assert accepted.resumen == (f"María González aceptó la transferencia del paciente Rosa Díaz, identificado como {pseudonym}. "
                                f"El responsable cambió de Juan Pérez a María González.")
    assert auditItems(db, team, "CAMBIAR_RESPONSABLE_PERFIL")

    detail = transfers.getTransfer(db, team.owner, team.id, sent.idTransferenciaPerfil)
    assert detail.estado == "ACEPTADA" and detail.tipo == "TRANSFERENCIA"
    assert detail.paciente.identificadorPseudonimo == pseudonym and detail.paciente.puedeVerPerfil
    assert (detail.paciente.nombre, detail.paciente.apellido) == ("Rosa", "Díaz")  # PerfilMedicion.nombre/apellido, no el del operador
    assert (detail.origen.nombre, detail.origen.apellido, detail.origen.rolInstitucion) == ("Juan", "Pérez", "OPERADOR")
    assert (detail.destino.nombre, detail.destino.apellido) == ("María", "González")
    assert (detail.solicitante.nombre, detail.solicitante.rolInstitucion) == ("Juan", "OPERADOR")
    assert detail.institucion.nombre == team.institution.nombre and detail.observacion == "Cambio de turno"
    assert detail.fechaPeticion.utcoffset().total_seconds() == -3 * 3600  # hora de Argentina con su zona
    assert detail.fechaRespuesta and detail.fechaTransferencia
    assert [step.clave for step in detail.historial] == ["SOLICITADA", "ACEPTADA", "RESPONSABLE_ACTUALIZADO"]
    assert detail.descripcion == f"El paciente Rosa Díaz, identificado como {pseudonym} fue transferido de Juan Pérez a María González."

    # Una nueva solicitud rechazada no cambia al responsable ni el origen histórico de la anterior.
    back = transfers.requestTransfer(db, secondUser, team.id, patient.idPerfilMedicion, juan, None)
    transfers.rejectTransfer(db, team.operator, team.id, back.idTransferenciaPerfil)
    assert responsible(db, patient) == second.idInstitucionUsuario
    rejected = auditItems(db, team, "RECHAZAR_TRANSFERENCIA_PERFIL")[0]
    assert rejected.resumen == (f"Juan Pérez rechazó la solicitud de transferencia del paciente Rosa Díaz, identificado como {pseudonym}. "
                                f"El responsable continúa siendo María González.")
    again = transfers.getTransfer(db, team.owner, team.id, sent.idTransferenciaPerfil)
    assert again.origen.idInstitucionUsuario == juan and again.destino.idInstitucionUsuario == second.idInstitucionUsuario
    assert {t.estado for t in transfers.listTransfers(db, team.owner, team.id).items} == {"ACEPTADA", "RECHAZADA"}
    rejectedDetail = transfers.getTransfer(db, team.owner, team.id, back.idTransferenciaPerfil)
    assert rejectedDetail.fechaRespuesta and rejectedDetail.descripcion.startswith("Juan Pérez rechazó")

    cancelled = transfers.requestTransfer(db, secondUser, team.id, patient.idPerfilMedicion, juan, None)
    transfers.cancelTransfer(db, secondUser, team.id, cancelled.idTransferenciaPerfil)
    assert auditItems(db, team, "CANCELAR_TRANSFERENCIA_PERFIL")[0].resumen.startswith(
        f"María González canceló la solicitud de transferencia del paciente Rosa Díaz, identificado como {pseudonym}.")


def test_el_nombre_del_paciente_solo_lo_ve_quien_puede_consultar_el_perfil(db, mails, team):
    second, secondUser, patient = scenario(db, team)
    sent = transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario, None)
    asDestination = transfers.getTransfer(db, secondUser, team.id, sent.idTransferenciaPerfil)
    assert asDestination.paciente.nombre is None and not asDestination.paciente.puedeVerPerfil  # todavía no es suyo
    assert asDestination.paciente.datosIdentificativos is None and "Rosa" not in asDestination.descripcion
    asOrigin = transfers.getTransfer(db, team.operator, team.id, sent.idTransferenciaPerfil)
    assert asOrigin.paciente.puedeVerPerfil and asOrigin.paciente.nombre


def test_alcance_del_detalle_de_transferencia(db, mails, team):
    second, secondUser, patient = scenario(db, team)
    sent = transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario, None)
    other, otherOperator, _ = otherInstitution(db)
    expectError("INSTITUCION_NO_ENCONTRADA", transfers.getTransfer, db, team.owner, other.idInstitucion, sent.idTransferenciaPerfil)
    expectError("INSTITUCION_NO_ENCONTRADA", transfers.getTransfer, db, otherOperator, team.id, sent.idTransferenciaPerfil)
    expectError("TRANSFERENCIA_NO_ENCONTRADA", transfers.getTransfer, db, otherOperator, other.idInstitucion, sent.idTransferenciaPerfil)
    third = addOperator(db, team, "tercero@example.com", "tercero")
    thirdUser = db.get(User, third.idUsuarioInvitado)
    expectError("TRANSFERENCIA_NO_ENCONTRADA", transfers.getTransfer, db, thirdUser, team.id, sent.idTransferenciaPerfil)


def test_el_origen_desvinculado_sigue_identificado_en_el_detalle_y_la_auditoria(db, mails, team):
    second, secondUser, patient = scenario(db, team)
    sent = transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario, None)
    transfers.acceptTransfer(db, secondUser, team.id, sent.idTransferenciaPerfil)
    legacyRevoke(db, team.owner, team.id, relationOf(db, team, team.operator).idInstitucionUsuario)
    detail = transfers.getTransfer(db, team.owner, team.id, sent.idTransferenciaPerfil)
    assert (detail.origen.nombre, detail.origen.apellido) == ("Juan", "Pérez")
    assert detail.origen.estadoRelacion == "BAJA" and not detail.origen.activo
    assert "Juan Pérez" in auditItems(db, team, "ACEPTAR_TRANSFERENCIA_PERFIL")[0].resumen


def test_la_reasignacion_directa_se_distingue_de_una_transferencia(db, mails, team):
    second, _, patient = scenario(db, team)
    # Reasignación directa: solo para un paciente cuyo responsable dejó de estar activo.
    legacyRevoke(db, team.moderator, team.id, relationOf(db, team, team.operator).idInstitucionUsuario)
    patients.assignResponsible(db, team.moderator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario)
    listed = transfers.listTransfers(db, team.owner, team.id).items
    assert [t.tipo for t in listed] == ["REASIGNACION"]
    detail = transfers.getTransfer(db, team.owner, team.id, listed[0].idTransferenciaPerfil)
    assert detail.tipo == "REASIGNACION" and detail.descripcion.endswith("de Juan Pérez a María González.")
    assert [s.clave for s in detail.historial] == ["REASIGNADA"]
    item = auditItems(db, team, "ASIGNAR_RESPONSABLE_ORIGEN")[0]
    assert item.accionEtiqueta.startswith("Reasignación directa") and "reasignó el paciente" in item.resumen


def test_rutas_http_de_detalle_y_fechas_con_zona(db, mails, team, api):
    second, secondUser, patient = scenario(db, team)
    sent = transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario, None)
    transfers.acceptTransfer(db, secondUser, team.id, sent.idTransferenciaPerfil)
    response = api(team.operator).get(f"/api/v1/institutions/{team.id}/transfers/{sent.idTransferenciaPerfil}")
    assert response.status_code == 200
    body = response.json()
    assert body["origen"]["nombre"] == "Juan" and body["destino"]["nombre"] == "María"
    assert body["fechaPeticion"].endswith("-03:00")
    # Los detalles técnicos (identificadores y eventos originales) no se envían al operador, aunque participe: la respuesta no los contiene.
    assert body["tecnico"] is None and str(sent.idTransferenciaPerfil) not in str(body.get("tecnico"))
    assert "datosNuevos" not in response.text and "idAuditoria" not in response.text
    # Quien supervisa (propietario y moderador) sí los recibe.
    for supervisor in (team.owner, team.moderator):
        technical = api(supervisor).get(f"/api/v1/institutions/{team.id}/transfers/{sent.idTransferenciaPerfil}").json()["tecnico"]
        assert technical["idTransferenciaPerfil"] == str(sent.idTransferenciaPerfil) and technical["eventos"]
    # Auditoría: el propietario abre el detalle por id; el operador, aunque participe, no consulta auditoría.
    event = api(team.owner).get(f"/api/v1/institutions/{team.id}/audit",
                                params={"accion": "ACEPTAR_TRANSFERENCIA_PERFIL"}).json()["items"][0]
    assert event["fechaHora"].endswith("-03:00")
    full = api(team.owner).get(f"/api/v1/institutions/{team.id}/audit/events/{event['idAuditoria']}")
    assert full.status_code == 200 and full.json()["nombreInstitucion"] == team.institution.nombre
    assert api(team.operator).get(f"/api/v1/institutions/{team.id}/audit/events/{event['idAuditoria']}").status_code in (403, 404)
    other, _, _ = otherInstitution(db)
    assert api(team.owner).get(f"/api/v1/institutions/{other.idInstitucion}/audit/events/{event['idAuditoria']}").status_code in (403, 404)


def test_la_vista_funcional_no_expone_uuid_ni_datos_sensibles(db, mails, team):
    second, secondUser, patient = scenario(db, team)
    sent = transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario, None)
    transfers.acceptTransfer(db, secondUser, team.id, sent.idTransferenciaPerfil)
    eventId = auditItems(db, team, "ACEPTAR_TRANSFERENCIA_PERFIL")[0].idAuditoria
    detail = auditQuery.detailInstitution(db, team.owner, team.id, eventId)
    assert detail.entidadEtiqueta == f"Paciente {patient.identificadorPseudonimo}"
    assert detail.relacionada is None and detail.nombreInstitucion == team.institution.nombre
    visible = json.dumps({"resumen": detail.resumen, "accion": detail.accionEtiqueta, "etiqueta": detail.entidadEtiqueta,
                          "origen": detail.transferencia.origen.texto, "destino": detail.transferencia.destino.texto})
    assert str(sent.idTransferenciaPerfil) not in visible and "20.111.222" not in visible
