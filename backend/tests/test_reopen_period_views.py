# Tras cerrar y reabrir una institución, las vistas de transferencias y reasignaciones no muestran a los pacientes archivados del período anterior.
#
#     python -m pytest tests/test_reopen_period_views.py -v
#
# Hallazgo de la auditoría Cloudflare (run-1): el padrón ya ocultaba a esos pacientes (institutionPatients._patientsOf), pero listTransfers/getTransfer
# y reassignments.listItems/overview devolvían nombre, apellido, edad y sexo a una moderadora incorporada DESPUÉS de la reapertura.

from app.core.exceptions import AuthError
from app.services import institution as institutions
from app.services import institutionPatients as patients
from app.services import institutionReassignments as reassignmentViews
from app.services import profileTransfers as transfers
from tests.legacy_offboarding import legacyRevoke
from tests.test_account_deletion import db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_institution_patients import addOperator, patientData
from tests.test_institution_reopen import close, reopenData
from tests.test_institutions import institutional, relationOf, team  # noqa: F401


def closedAndReopened(db, team):
    """Período 1: la operadora A tiene a Ana; solicita pasarla a B (pendiente) y luego se la desvincula (tarea de reasignación). Cierre y reapertura."""
    patient = patients.createPatient(db, team.operator, team.id, patientData(nombre="Ana", apellido="Paz", dni="30111222"))
    other = addOperator(db, team)
    sent = transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, other.idInstitucionUsuario, "obs")
    legacyRevoke(db, team.moderator, team.id, relationOf(db, team, team.operator).idInstitucionUsuario)
    before = reassignmentViews.listItems(db, team.moderator, team.id, estado=None)
    assert [i.nombre for i in before.items] == ["Ana"], "durante el período 1 la tarea sí se ve"
    close(db, team.owner, team.id)
    institutions.reopenInstitution(db, team.owner, reopenData())
    newcomer = institutional(db, "mod2@example.com", "mod2")  # moderadora incorporada DESPUÉS de la reapertura
    invitation = institutions.invite(db, team.owner, team.id, "MODERADOR", newcomer.correoElectronico)
    institutions.respondInvitation(db, newcomer, invitation.idInstitucionUsuario, accept=True)
    return patient, sent, newcomer


def test_las_reasignaciones_del_periodo_anterior_no_se_muestran(db, mails, team):
    patient, _, newcomer = closedAndReopened(db, team)
    assert patients.listPatients(db, newcomer, team.id).total == 0  # control: el padrón ya lo ocultaba
    page = reassignmentViews.listItems(db, newcomer, team.id, estado=None)
    assert page.total == 0 and page.items == []
    assert reassignmentViews.overview(db, newcomer, team.id).grupos == []


def test_las_transferencias_del_periodo_anterior_no_se_muestran(db, mails, team):
    _, sent, newcomer = closedAndReopened(db, team)
    page = transfers.listTransfers(db, newcomer, team.id)
    assert page.items == []
    try:
        transfers.getTransfer(db, newcomer, team.id, sent.idTransferenciaPerfil)
    except AuthError as error:
        assert error.code == "TRANSFERENCIA_NO_ENCONTRADA"
    else:
        raise AssertionError("el detalle de una transferencia archivada no debe mostrarse")


def test_en_el_periodo_vigente_todo_se_sigue_viendo(db, mails, team):
    """Sin cierre ni reapertura nada cambia: la tarea y la transferencia del período en curso siguen visibles."""
    patient = patients.createPatient(db, team.operator, team.id, patientData(nombre="Eva", apellido="Sosa", dni="30222333"))
    other = addOperator(db, team)
    transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, other.idInstitucionUsuario, None)
    assert len(transfers.listTransfers(db, team.moderator, team.id).items) == 1
    legacyRevoke(db, team.moderator, team.id, relationOf(db, team, team.operator).idInstitucionUsuario)
    assert reassignmentViews.listItems(db, team.moderator, team.id, estado=None).total >= 1
