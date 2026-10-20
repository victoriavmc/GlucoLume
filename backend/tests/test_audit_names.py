# Pruebas de la auditoría con nombres y apellidos: las referencias a relaciones institucionales se muestran como personas,
# sin tocar los UUID guardados, y respetando el ámbito de la consulta.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_audit_names.py -v

import json
import uuid

from sqlalchemy import event, select

from app.models.audit import Audit
from app.models.institutionUser import InstitutionUser
from app.models.user import User
from app.services import accountDeletion
from app.services import audit as auditService
from app.services import auditQuery
from app.services import institution as institutions
from app.services import institutionPatients as patients
from app.services import profileTransfers as transfers
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import admin, api  # noqa: F401 - fixtures
from tests.test_institution_patients import addOperator, otherInstitution, patientData
from tests.test_institutions import expectError, freshLookupLimiter, institutional, relationOf, team  # noqa: F401


def named(db, user, nombre, apellido):
    """Fija el nombre de la cuenta y la identidad registrada en sus vínculos (la que usa la auditoría)."""
    user.nombre, user.apellido = nombre, apellido
    for relation in db.scalars(select(InstitutionUser).where(InstitutionUser.idUsuarioInvitado == user.idUsuario)):
        if relation.nombreProfesionalHistorico is not None:
            relation.nombreProfesionalHistorico, relation.apellidoProfesionalHistorico = nombre, apellido
    db.commit()
    return user


def anonymize(db, user):
    """Baja lógica de la cuenta con la anonimización real del módulo de eliminación."""
    accountDeletion._anonymizeUser(reload(db, User, user.idUsuario), nowForDb())
    db.commit()


def responsibleChange(db, team):
    """Juan Pérez (operador del equipo) le transfiere un paciente a María González (segundo operador)."""
    named(db, team.operator, "Juan", "Pérez")
    second = addOperator(db, team)
    secondUser = named(db, db.get(User, second.idUsuarioInvitado), "María", "González")
    patient = patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz"))
    sent = transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario, None)
    transfers.acceptTransfer(db, secondUser, team.id, sent.idTransferenciaPerfil)
    return second, secondUser


def eventOf(db, team, action):
    page = auditQuery.listInstitution(db, team.owner, team.id, accion=action, tamanioPagina=100)
    assert page.items, action
    return auditQuery.detailInstitution(db, team.owner, team.id, page.items[0].idAuditoria)


def change(detail, field):
    return next(c for c in detail.cambios if c.campo == field)


# 1. Transferencia entre dos operadores activos --------------------------------------------------------------


def test_transferencia_entre_operadores_muestra_responsable_anterior_y_nuevo_por_nombre(db, mails, team):
    second, _ = responsibleChange(db, team)
    detail = eventOf(db, team, "CAMBIAR_RESPONSABLE_PERFIL")
    responsible = change(detail, "idInstitucionUsuarioResponsable")
    assert responsible.tipo == "PERSONA" and responsible.etiqueta == "Responsable institucional"
    assert responsible.anterior.texto == "Juan Pérez" and responsible.anterior.rol == "OPERADOR"
    assert responsible.nuevo.texto == "María González"
    assert responsible.nuevo.id == str(second.idInstitucionUsuario)  # el UUID original sigue disponible
    assert detail.usuario == "María González" or detail.usuario == "Juan Pérez"  # actor identificado por nombre


# 2. Operador desvinculado -----------------------------------------------------------------------------------


def test_el_historial_sigue_legible_si_el_operador_fue_desvinculado_y_elimino_su_cuenta(db, mails, team):
    responsibleChange(db, team)
    operator = team.operator
    institutions.revokeMember(db, team.owner, team.id, "OPERADOR", relationOf(db, team, operator).idInstitucionUsuario)
    anonymize(db, operator)
    detail = eventOf(db, team, "CAMBIAR_RESPONSABLE_PERFIL")
    assert change(detail, "idInstitucionUsuarioResponsable").anterior.texto == "Juan Pérez"  # referencia guardada
    assert detail.usuario in ("Juan Pérez", "María González")


# 3. Cambio de nombre posterior ------------------------------------------------------------------------------


def test_un_cambio_de_nombre_posterior_no_reescribe_lo_que_ocurrio(db, mails, team):
    responsibleChange(db, team)
    named(db, team.operator, "Juana", "Pérez Gómez")
    detail = eventOf(db, team, "CAMBIAR_RESPONSABLE_PERFIL")
    assert change(detail, "idInstitucionUsuarioResponsable").anterior.texto == "Juan Pérez"  # nombre al momento del evento


# 4. Consulta del propietario --------------------------------------------------------------------------------


def test_el_propietario_ve_los_nombres_en_la_lista_y_en_el_detalle(db, mails, team):
    responsibleChange(db, team)
    page = auditQuery.listInstitution(db, team.owner, team.id, tamanioPagina=100)
    labels = {i.accion: i.entidadEtiqueta for i in page.items}
    assert labels["CREAR_PACIENTE"] and "Paciente" in labels["CREAR_PACIENTE"]
    assert any(i.usuario in ("Juan Pérez", "María González") for i in page.items)
    assert all(i.usuario != str(team.operator.idUsuario) for i in page.items)


def test_la_administracion_de_plataforma_se_muestra_sin_nombre_al_propietario(db, mails, team, admin):
    auditService.registerEvent(db, "CRUD", "EDITAR_INSTITUCION", True, admin.idUsuario, "Institucion", team.id,
                               idInstitucion=team.id)
    db.commit()
    page = auditQuery.listInstitution(db, team.owner, team.id, accion="EDITAR_INSTITUCION")
    assert page.items[0].usuario == auditQuery.PLATFORM_LABEL


# 5. Otra institución ----------------------------------------------------------------------------------------


def test_un_uuid_de_otra_institucion_no_revela_a_sus_empleados(db, mails, team):
    _, foreignOperator, foreignRelation = otherInstitution(db)
    named(db, foreignOperator, "Rosa", "Ajena")
    auditService.registerEvent(db, "CRUD", "SOLICITAR_TRANSFERENCIA_PERFIL", True, team.owner.idUsuario, "Institucion", team.id,
                               datosNuevos={"idOperadorDestino": str(foreignRelation.idInstitucionUsuario)},
                               idInstitucion=team.id)
    db.commit()
    detail = eventOf(db, team, "SOLICITAR_TRANSFERENCIA_PERFIL")
    target = change(detail, "idOperadorDestino").nuevo
    assert target.texto == auditQuery.UNAVAILABLE and not target.disponible
    assert "Rosa" not in json.dumps(detail.model_dump(mode="json"), ensure_ascii=False)
    stored = db.scalar(select(Audit.detalle).where(Audit.idAuditoria == detail.idAuditoria))
    assert not stored or "Rosa" not in stored  # tampoco se guardó el nombre ajeno


def test_el_propietario_no_consulta_eventos_de_otra_institucion(db, mails, team):
    other, _, _ = otherInstitution(db)
    foreign = db.scalar(select(Audit).where(Audit.idInstitucion == other.idInstitucion))
    expectError("EVENTO_NO_ENCONTRADO", auditQuery.detailInstitution, db, team.owner, team.id, foreign.idAuditoria)


def test_moderador_y_operador_no_consultan_la_auditoria(db, mails, team):
    for user in (team.moderator, team.operator):
        expectError("PERMISO_INSUFICIENTE", auditQuery.listInstitution, db, user, team.id)


# 6. UUID visibles en el detalle técnico ---------------------------------------------------------------------


def test_el_detalle_conserva_los_uuid_originales_como_referencia_tecnica(db, mails, team):
    second, _ = responsibleChange(db, team)
    detail = eventOf(db, team, "CAMBIAR_RESPONSABLE_PERFIL")
    assert detail.valoresNuevos["idInstitucionUsuarioResponsable"] == str(second.idInstitucionUsuario)
    assert uuid.UUID(detail.valoresPrevios["idInstitucionUsuarioResponsable"])
    stored = db.scalar(select(Audit.datosNuevos).where(Audit.idAuditoria == detail.idAuditoria))
    assert str(second.idInstitucionUsuario) in stored  # lo guardado no se modifica


# 7. Registros antiguos sin información nominal --------------------------------------------------------------


def test_registros_antiguos_de_una_cuenta_eliminada_sin_nombre_muestran_usuario_eliminado(db, mails, team):
    ghost = institutional(db, "fantasma@example.com", "fantasma")
    invitation = institutions.invite(db, team.moderator, team.id, "OPERADOR", ghost.correoElectronico)
    institutions.respondInvitation(db, ghost, invitation.idInstitucionUsuario, accept=True)
    relation = relationOf(db, team, ghost)
    old = Audit(idUsuario=team.owner.idUsuario, tipoEvento="CRUD", accion="CAMBIAR_RESPONSABLE_PERFIL", tablaAfectada="Institucion",
                idRegistro=team.id, resultado="EXITO", idInstitucion=team.id, modulo="PERFILES",
                datosNuevos=json.dumps({"idInstitucionUsuarioResponsable": str(relation.idInstitucionUsuario)}))
    db.add(old)
    db.commit()
    relation.nombreProfesionalHistorico = relation.apellidoProfesionalHistorico = None  # vínculo sin identidad registrada
    db.commit()
    anonymize(db, ghost)
    detail = auditQuery.detailInstitution(db, team.owner, team.id, old.idAuditoria)
    value = change(detail, "idInstitucionUsuarioResponsable").nuevo
    assert value.texto == "Usuario eliminado" and not value.disponible  # cuenta anonimizada: no se recupera ningún dato
    assert value.id == str(relation.idInstitucionUsuario)  # el UUID queda como referencia técnica


# Rendimiento y privacidad -----------------------------------------------------------------------------------


def test_la_lista_resuelve_nombres_sin_una_consulta_por_fila(db, mails, team):
    responsibleChange(db, team)
    for _ in range(6):
        patients.createPatient(db, team.operator, team.id, patientData(dni=None))
    statements = []

    def count(conn, cursor, statement, *rest):
        statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", count)
    try:
        small = auditQuery.listInstitution(db, team.owner, team.id, tamanioPagina=3)
        statements_small = len(statements)
        statements.clear()
        large = auditQuery.listInstitution(db, team.owner, team.id, tamanioPagina=100)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", count)
    assert len(large.items) > len(small.items) + 5
    assert len(statements) <= statements_small + 3  # no crece con la cantidad de filas


def test_la_auditoria_no_expone_documento_ni_matricula(db, mails, team):
    responsibleChange(db, team)
    page = auditQuery.listInstitution(db, team.owner, team.id, tamanioPagina=100)
    dump = json.dumps([auditQuery.detailInstitution(db, team.owner, team.id, i.idAuditoria).model_dump(mode="json")
                       for i in page.items], ensure_ascii=False)
    stored = " ".join(filter(None, db.scalars(select(Audit.detalle))))
    for secret in ("20.111.222", "20111222", "MP-123"):
        assert secret not in dump and secret not in stored


# Transferencias de pacientes: paciente, operador de origen y operador destinatario -------------------------------


def transferEvents(db, team, action):
    page = auditQuery.listInstitution(db, team.owner, team.id, accion=action, tamanioPagina=100)
    return [auditQuery.detailInstitution(db, team.owner, team.id, i.idAuditoria) for i in page.items], page.items


def test_cada_evento_de_transferencia_dice_paciente_origen_y_destino(db, mails, team):
    named(db, team.operator, "Juan", "Pérez")
    second = addOperator(db, team)
    secondUser = named(db, db.get(User, second.idUsuarioInvitado), "María", "González")
    patient = patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz"))
    rejected = transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario, None)
    transfers.rejectTransfer(db, secondUser, team.id, rejected.idTransferenciaPerfil)
    cancelled = transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario, None)
    transfers.cancelTransfer(db, team.operator, team.id, cancelled.idTransferenciaPerfil)
    accepted = transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario, None)
    transfers.acceptTransfer(db, secondUser, team.id, accepted.idTransferenciaPerfil)
    for action in ("SOLICITAR_TRANSFERENCIA_PERFIL", "RECHAZAR_TRANSFERENCIA_PERFIL", "CANCELAR_TRANSFERENCIA_PERFIL",
                   "ACEPTAR_TRANSFERENCIA_PERFIL"):
        details, items = transferEvents(db, team, action)
        for detail, item in zip(details, items):
            info = detail.transferencia
            assert info.paciente.identificador == patient.identificadorPseudonimo, action
            assert info.paciente.nombreCompleto == "Rosa Díaz" and info.paciente.datosIdentificativos, action
            assert info.origen.texto == "Juan Pérez" and info.destino.texto == "María González", action
            assert item.entidadEtiqueta == f"Paciente {patient.identificadorPseudonimo}"


def test_eventos_de_transferencia_anteriores_se_resuelven_por_la_transferencia(db, mails, team):
    named(db, team.operator, "Juan", "Pérez")
    second = addOperator(db, team)
    secondUser = named(db, db.get(User, second.idUsuarioInvitado), "María", "González")
    patient = patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz"))
    sent = transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario, None)
    transfers.acceptTransfer(db, secondUser, team.id, sent.idTransferenciaPerfil)
    # Evento con el formato anterior: solo el estado y sin referencia nominal guardada.
    old = Audit(idUsuario=secondUser.idUsuario, tipoEvento="CRUD", accion="ACEPTAR_TRANSFERENCIA_PERFIL", resultado="EXITO",
                tablaAfectada="TransferenciaPerfil", idRegistro=sent.idTransferenciaPerfil, idInstitucion=team.id,
                modulo="PERFILES", datosNuevos=json.dumps({"estado": "ACEPTADA"}))
    db.add(old)
    db.commit()
    info = auditQuery.detailInstitution(db, team.owner, team.id, old.idAuditoria).transferencia
    assert (info.paciente.identificador, info.origen.texto, info.destino.texto) == (patient.identificadorPseudonimo, "Juan Pérez", "María González")
    assert info.paciente.nombreCompleto == "Rosa Díaz"


def test_http_la_auditoria_institucional_es_solo_del_propietario_en_todos_sus_endpoints(db, mails, team, api):
    """La restricción no depende del menú de React: listado, resumen y detalle responden 403 a moderador y operador (aun con la
    URL directa), 404 a quien no pertenece a la institución y 200 al propietario."""
    base = f"/api/v1/institutions/{team.id}/audit"
    event = db.scalar(select(Audit).where(Audit.idInstitucion == team.id))
    paths = (base, f"{base}/summary", f"{base}/events/{event.idAuditoria}")
    for user in (team.moderator, team.operator):
        for path in paths:
            denied = api(user).get(path)
            assert denied.status_code == 403 and denied.json()["codigo"] == "PERMISO_INSUFICIENTE", (user.usuario, path)
    stranger = institutional(db, "ajeno-audit@example.com", "ajenoaudit")
    assert all(api(stranger).get(path).status_code == 404 for path in paths)
    assert all(api(team.owner).get(path).status_code == 200 for path in paths)
    # Cada intento no autorizado queda registrado, sin revelar eventos.
    assert db.scalar(select(Audit).where(Audit.accion == "CONSULTAR_AUDITORIA", Audit.resultado == "FALLO", Audit.idInstitucion == team.id)) is not None
