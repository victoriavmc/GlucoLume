# Avisos de la bandeja sobre la gestión de una institución (INSTITUCION_*), según el rol de quien los recibe: altas y bajas de operadores y
# moderadores, pacientes nuevos y a cargo, y solicitudes de paciente (nueva, aceptada o rechazada).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_institution_notifications.py -v

import pytest
from sqlalchemy import select

from app.core.exceptions import AuthError
from app.models import notificationEvents as events
from app.models.measurementProfile import MeasurementProfile
from app.models.profileTransfer import ProfileTransfer
from app.models.user import User
from app.schemas.measurementProfile import PatientCreateRequest
from app.services import institution as institutions
from app.services import institutionNotifications
from app.services import institutionPatients as patients
from app.services import profileTransfers as transfers
from app.services import userNotifications as service
from tests.test_account_deletion import db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_institution_patients import addOperator, patientData
from tests.test_institutions import institutional, relationOf, team  # noqa: F401 - fixtures


def avisos(db, user, evento):
    return [n for n in service.inbox(db, user, limite=50).notificaciones if n.evento == evento]


def eventosDe(db, user):
    return {n.evento for n in service.inbox(db, user, limite=50).notificaciones}


def crearPaciente(db, actor, team, idResponsable=None, nombre="rosa"):
    data = patientData(nombre=nombre, apellido="díaz")
    if idResponsable is not None:
        data = PatientCreateRequest(**{**data.model_dump(), "idInstitucionUsuarioResponsable": idResponsable})
    return patients.createPatient(db, actor, team.id, data)


def ultimaTransferencia(db, idPerfilMedicion):
    return db.scalar(select(ProfileTransfer.idTransferenciaPerfil).where(ProfileTransfer.idPerfilMedicion == idPerfilMedicion)
                     .order_by(ProfileTransfer.fechaPeticion.desc()))


def test_alta_de_operador_avisa_al_propietario_pero_no_a_quien_lo_invito(db, mails, team):
    # La fixture incorporó al operador por invitación del moderador: el propietario se entera; el moderador que lo invitó no.
    assert events.INSTITUCION_OPERADOR_NUEVO in eventosDe(db, team.owner)
    assert events.INSTITUCION_OPERADOR_NUEVO not in eventosDe(db, team.moderator)
    assert events.INSTITUCION_OPERADOR_NUEVO not in eventosDe(db, team.operator)


def test_alta_de_moderador_avisa_a_los_demas_moderadores_y_no_a_quien_la_envio(db, mails, team):
    nuevo = institutional(db, "moderadora2@example.com", "moderadora2")
    invitation = institutions.invite(db, team.owner, team.id, "MODERADOR", nuevo.correoElectronico)
    institutions.respondInvitation(db, nuevo, invitation.idInstitucionUsuario, accept=True)

    # El moderador que ya estaba se entera; el propietario que la invitó y la persona incorporada no reciben el aviso.
    assert avisos(db, team.moderator, events.INSTITUCION_MODERADOR_NUEVO)
    assert events.INSTITUCION_MODERADOR_NUEVO not in eventosDe(db, team.owner)
    assert events.INSTITUCION_MODERADOR_NUEVO not in eventosDe(db, nuevo)


def test_baja_de_operador_avisa_a_gestion_menos_a_quien_la_hizo(db, mails, team):
    relation = relationOf(db, team, team.operator)
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", relation.idInstitucionUsuario)

    assert avisos(db, team.owner, events.INSTITUCION_OPERADOR_BAJA)
    assert events.INSTITUCION_OPERADOR_BAJA not in eventosDe(db, team.moderator)  # quien hizo la baja
    assert events.INSTITUCION_OPERADOR_BAJA not in eventosDe(db, team.operator)  # la persona dada de baja


def test_baja_de_moderador_avisa_a_los_moderadores_que_siguen(db, mails, team):
    otro = institutional(db, "moderadora3@example.com", "moderadora3")
    invitation = institutions.invite(db, team.owner, team.id, "MODERADOR", otro.correoElectronico)
    institutions.respondInvitation(db, otro, invitation.idInstitucionUsuario, accept=True)
    relation = relationOf(db, team, otro)

    institutions.revokeMember(db, team.owner, team.id, "MODERADOR", relation.idInstitucionUsuario)

    assert avisos(db, team.moderator, events.INSTITUCION_MODERADOR_BAJA)
    assert events.INSTITUCION_MODERADOR_BAJA not in eventosDe(db, team.owner)  # quien hizo la baja
    assert events.INSTITUCION_MODERADOR_BAJA not in eventosDe(db, otro)  # la persona dada de baja


def test_paciente_nuevo_avisa_a_gestion_y_paciente_a_cargo_solo_a_su_operador(db, mails, team):
    responsable = relationOf(db, team, team.operator).idInstitucionUsuario
    crearPaciente(db, team.moderator, team, idResponsable=responsable)

    assert len(avisos(db, team.owner, events.INSTITUCION_PACIENTE_NUEVO)) == 1
    assert events.INSTITUCION_PACIENTE_NUEVO not in eventosDe(db, team.moderator)  # quien lo registró
    assert events.INSTITUCION_PACIENTE_NUEVO not in eventosDe(db, team.operator)  # los operadores no son gestión

    [aCargo] = avisos(db, team.operator, events.INSTITUCION_PACIENTE_A_CARGO)
    assert aCargo.url.startswith(f"/app/instituciones/{team.id}/pacientes/")
    assert events.INSTITUCION_PACIENTE_A_CARGO not in eventosDe(db, team.owner)


def test_los_avisos_del_paciente_no_incluyen_su_nombre(db, mails, team):
    responsable = relationOf(db, team, team.operator).idInstitucionUsuario
    crearPaciente(db, team.moderator, team, idResponsable=responsable, nombre="rosaeliana")

    for user, evento in ((team.owner, events.INSTITUCION_PACIENTE_NUEVO), (team.operator, events.INSTITUCION_PACIENTE_A_CARGO)):
        [aviso] = avisos(db, user, evento)
        assert "rosaeliana" not in f"{aviso.titulo} {aviso.mensaje}".lower()  # solo el identificador seudónimo


def test_el_operador_que_registra_su_paciente_no_se_avisa_a_si_mismo(db, mails, team):
    crearPaciente(db, team.operator, team)

    assert avisos(db, team.owner, events.INSTITUCION_PACIENTE_NUEVO)
    assert events.INSTITUCION_PACIENTE_A_CARGO not in eventosDe(db, team.operator)  # ya lo tiene a su cargo


def test_solicitud_de_paciente_llega_al_destino_y_su_respuesta_al_origen(db, mails, team):
    responsable = relationOf(db, team, team.operator).idInstitucionUsuario
    paciente = crearPaciente(db, team.moderator, team, idResponsable=responsable)
    segundo = addOperator(db, team)
    segundoUser = db.get(User, segundo.idUsuarioInvitado)

    transfers.requestTransfer(db, team.operator, team.id, paciente.idPerfilMedicion, segundo.idInstitucionUsuario, None)
    [nueva] = avisos(db, segundoUser, events.INSTITUCION_SOLICITUD_NUEVA)
    assert nueva.url == f"/app/instituciones/{team.id}/transferencias"

    transfers.acceptTransfer(db, segundoUser, team.id, ultimaTransferencia(db, paciente.idPerfilMedicion))
    assert avisos(db, team.operator, events.INSTITUCION_SOLICITUD_ACEPTADA)

    # Ahora el segundo tiene el paciente: se lo pide de vuelta al original, que lo rechaza.
    transfers.requestTransfer(db, segundoUser, team.id, paciente.idPerfilMedicion, responsable, None)
    transfers.rejectTransfer(db, team.operator, team.id, ultimaTransferencia(db, paciente.idPerfilMedicion))
    assert avisos(db, segundoUser, events.INSTITUCION_SOLICITUD_RECHAZADA)


def test_la_preferencia_apaga_el_aviso_de_institucion_y_no_ofrece_correo(db, mails, team):
    preferencia = next(p for p in service.settings(db, team.owner).preferencias if p.evento == events.INSTITUCION_PACIENTE_NUEVO)
    assert preferencia.categoria == "INSTITUCION" and preferencia.correoDisponible is False and preferencia.porCorreo is False

    service.updatePreference(db, team.owner, events.INSTITUCION_PACIENTE_NUEVO, enPagina=False)
    crearPaciente(db, team.operator, team)
    assert events.INSTITUCION_PACIENTE_NUEVO not in eventosDe(db, team.owner)


def test_no_se_puede_pedir_correo_para_un_aviso_que_solo_va_a_la_pagina(db, mails, team):
    with pytest.raises(AuthError) as error:  # el aviso no tiene canal de correo
        service.updatePreference(db, team.owner, events.INSTITUCION_PACIENTE_NUEVO, porCorreo=True)
    assert error.value.code == "CANAL_NO_DISPONIBLE"


def test_la_bandeja_filtra_los_avisos_de_institucion(db, mails, team):
    crearPaciente(db, team.operator, team)
    page = service.inbox(db, team.owner, categoria="INSTITUCION", limite=50)
    assert page.notificaciones and {n.categoria for n in page.notificaciones} == {"INSTITUCION"}


def test_el_mismo_hecho_procesado_dos_veces_no_duplica_el_aviso(db, mails, team):
    paciente = crearPaciente(db, team.operator, team)
    profile = reload(db, MeasurementProfile, paciente.idPerfilMedicion)
    institutionNotifications.patientCreated(db, team.institution, profile, {team.operator.idUsuario})  # reproceso del mismo alta

    assert len(avisos(db, team.owner, events.INSTITUCION_PACIENTE_NUEVO)) == 1
