# Correos del módulo institucional: alta de paciente, asignación de responsable, baja, incorporación a la
# institución y altas/bajas de operadores. Cada aviso sale después del commit, al destinatario correcto y sin datos
# personales del paciente (solo su identificador seudónimo).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_patient_mails.py -v

import pytest

from app.models.user import User
from app.services import institution as institutions
from app.services import institutionPatients as patients
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_institution_patients import addOperator, patientData
from tests.test_institutions import (  # noqa: F401 - fixtures
    expectError,
    freshLookupLimiter,
    institutional,
    newInstitution,
    relationOf,
    team,
)


def sentTo(mails, email):
    return [mail for mail in mails if mail["to"] == email]


def subjects(mails, email):
    return [mail["subject"] for mail in sentTo(mails, email)]


def noPersonalData(mails):
    for mail in mails:
        for secret in ("Juan", "Pérez", "20111222", "1980-01-02"):
            assert secret not in mail["html"] and secret not in mail["text"]


def test_alta_de_paciente_confirma_al_operador_que_lo_registra(db, mails, team):
    created = patients.createPatient(db, team.operator, team.id, patientData())
    [mail] = mails
    assert mail["to"] == team.operator.correoElectronico and mail["subject"] == "Registraste un paciente"
    assert created.identificadorPseudonimo in mail["html"]
    assert f"/app/instituciones/{team.id}/pacientes/{created.idPerfilMedicion}" in mail["html"]
    noPersonalData(mails)


def test_alta_por_un_moderador_avisa_tambien_al_operador_responsable(db, mails, team):
    created = patients.createPatient(db, team.moderator, team.id, patientData(
        idInstitucionUsuarioResponsable=relationOf(db, team, team.operator).idInstitucionUsuario))
    assert subjects(mails, team.moderator.correoElectronico) == ["Registraste un paciente"]
    assert subjects(mails, team.operator.correoElectronico) == ["Tenés un paciente nuevo a tu cargo"]
    assert created.identificadorPseudonimo in sentTo(mails, team.operator.correoElectronico)[0]["html"]
    noPersonalData(mails)


def test_reasignar_avisa_al_nuevo_responsable_y_al_anterior(db, mails, team):
    created = patients.createPatient(db, team.operator, team.id, patientData())
    second = addOperator(db, team)
    secondUser = db.get(User, second.idUsuarioInvitado)
    mails.clear()
    # Con un responsable activo el moderador propone: el destino recibe la solicitud y el propietario el aviso de gestión; el origen no recibe nada aún.
    patients.assignResponsible(db, team.moderator, team.id, created.idPerfilMedicion, second.idInstitucionUsuario)
    assert subjects(mails, secondUser.correoElectronico) == ["Tenés una transferencia de paciente pendiente"]
    assert subjects(mails, team.owner.correoElectronico) == ["Un moderador cambió el responsable de un paciente"]
    assert subjects(mails, team.operator.correoElectronico) == [] and subjects(mails, team.moderator.correoElectronico) == []
    assert len(mails) == 2
    noPersonalData(mails)
    # Reasignar al responsable actual no manda nada.
    mails.clear()
    patients.assignResponsible(db, team.moderator, team.id, created.idPerfilMedicion, relationOf(db, team, team.operator).idInstitucionUsuario)
    assert mails == []


def test_baja_avisa_al_responsable_salvo_que_la_haga_el_mismo(db, mails, team):
    created = patients.createPatient(db, team.operator, team.id, patientData())
    mails.clear()
    patients.dischargePatient(db, team.moderator, team.id, created.idPerfilMedicion)
    [mail] = mails
    assert mail["to"] == team.operator.correoElectronico and mail["subject"] == "Un paciente a tu cargo fue dado de baja"
    noPersonalData(mails)


def test_los_avisos_no_se_envian_si_la_operacion_falla(db, mails, team):
    created = patients.createPatient(db, team.operator, team.id, patientData())
    mails.clear()
    expectError("PERMISO_INSUFICIENTE", patients.assignResponsible, db, team.operator, team.id,
                created.idPerfilMedicion, relationOf(db, team, team.operator).idInstitucionUsuario)
    expectError("PACIENTE_NO_ENCONTRADO", patients.dischargePatient, db, team.moderator, team.id,
                __import__("uuid").uuid4())
    assert mails == []


def test_al_incorporar_a_alguien_recibe_la_confirmacion_y_el_propietario_se_entera_del_operador(db, mails, team):
    newcomer = institutional(db, "nuevo@example.com", "nuevo")
    invitation = institutions.invite(db, team.moderator, team.id, "OPERADOR", "nuevo@example.com")
    mails.clear()
    institutions.respondInvitation(db, newcomer, invitation.idInstitucionUsuario, accept=True)
    assert subjects(mails, "nuevo@example.com") == ["Tu cuenta fue vinculada a una institución"]
    assert f"/app/instituciones/{team.id}" in sentTo(mails, "nuevo@example.com")[0]["html"]
    assert subjects(mails, team.moderator.correoElectronico) == ["Tu invitación institucional fue aceptada"]
    assert subjects(mails, team.owner.correoElectronico) == ["Se agregó un nuevo operador"]


def test_al_desvincular_un_operador_se_avisa_a_el_y_al_propietario(db, mails, team):
    mails.clear()
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR",
                              relationOf(db, team, team.operator).idInstitucionUsuario)
    # Era su única institución: además del aviso de la baja recibe el del período de gracia de 30 días.
    assert subjects(mails, team.operator.correoElectronico) == ["Ya no pertenecés a la institución", "Tu cuenta no tiene instituciones: tenés 30 días"]
    assert subjects(mails, team.owner.correoElectronico) == ["Se eliminó un operador"]
    # El moderador que hizo el cambio no recibe un aviso de lo que él mismo hizo.
    assert sentTo(mails, team.moderator.correoElectronico) == []


def test_un_propietario_que_desvincula_no_se_avisa_a_si_mismo(db, mails, team):
    mails.clear()
    institutions.revokeMember(db, team.owner, team.id, "OPERADOR", relationOf(db, team, team.operator).idInstitucionUsuario)
    assert sentTo(mails, team.owner.correoElectronico) == []
    # Era su única institución: además del aviso de la baja recibe el del período de gracia de 30 días.
    assert subjects(mails, team.operator.correoElectronico) == ["Ya no pertenecés a la institución", "Tu cuenta no tiene instituciones: tenés 30 días"]


def test_al_rechazar_la_invitacion_se_avisa_a_quien_invito_y_no_se_crea_vinculo(db, mails, team):
    guest = institutional(db, "invitada@example.com", "invitada")
    invitation = institutions.invite(db, team.moderator, team.id, "OPERADOR", "invitada@example.com")
    mails.clear()
    assert institutions.respondInvitation(db, guest, invitation.idInstitucionUsuario, accept=False) is None
    [mail] = mails
    assert mail["to"] == team.moderator.correoElectronico
    assert mail["subject"] == "Tu invitación institucional fue rechazada"
    assert "Hospital X" in mail["html"] and "Operador/a" in mail["html"]
    assert relationOf(db, team, guest) is None  # el vínculo queda en BAJA: no hay relación vigente
    # La persona que rechazó no recibe la confirmación de «vinculada» ni se avisa al propietario de un operador nuevo.
    assert sentTo(mails, "invitada@example.com") == [] and sentTo(mails, team.owner.correoElectronico) == []
    # Una invitación ya respondida no vuelve a generar correos.
    mails.clear()
    expectError("INVITACION_NO_ENCONTRADA", institutions.respondInvitation, db, guest, invitation.idInstitucionUsuario,
                accept=False)
    assert mails == []
