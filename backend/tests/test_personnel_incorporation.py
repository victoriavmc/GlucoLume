# Módulo Personal: solo figura quien se incorporó de verdad (o tiene una invitación pendiente vigente). Una invitación cancelada,
# rechazada o vencida, o una cuenta invitada que nunca se incorporó, NO es personal ni una «baja»: «BAJA» es solo para quien se
# incorporó y después fue desvinculado. Caso real: invitar a una cuenta con un correo equivocado y cancelar la invitación.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_personnel_incorporation.py -v

from datetime import timedelta

from sqlalchemy import select

from app.models.audit import Audit
from app.models.institutionUser import InstitutionUser
from app.models.user import User
from app.services import institution as institutions
from app.services import personnel
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import admin, api  # noqa: F401 - fixtures
from tests.test_institutions import expectError, freshLookupLimiter, institutional, relationOf, team  # noqa: F401


def listing(db, team, **filters):
    return personnel.listPersonnel(db, team.owner, team.id, **filters)


def emails(page):
    return {p.correoElectronico for p in page.items}


def invitationOf(db, team, email):
    return db.scalar(select(InstitutionUser).join(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
                     .where(InstitutionUser.idInstitucion == team.id, User.correoElectronico == email))


def invite(db, team, email, name="invitada", role="OPERADOR"):
    guest = institutional(db, email, name)
    return guest, institutions.invite(db, team.moderator if role == "OPERADOR" else team.owner, team.id, role, email)


def assertNotPersonnel(db, team, email, relationId):
    """La persona no está en ninguna vista de Personal: ni lista, ni filtros, ni indicadores, ni perfil."""
    for filters in ({}, {"rol": "OPERADOR"}, {"rol": "MODERADOR"}, {"estado": "BAJA"}, {"estado": "ACTIVO"}, {"estado": "PENDIENTE"},
                    {"busqueda": email}):
        assert email not in emails(listing(db, team, **filters)), filters
    expectError("MIEMBRO_NO_ENCONTRADO", personnel.getProfile, db, team.owner, team.id, relationId)


def test_invitacion_pendiente_aparece_como_pendiente_y_no_cuenta_como_activa(db, mails, team):
    guest, invitation = invite(db, team, "pendiente@example.com")
    page = listing(db, team, estado="PENDIENTE")
    assert [p.correoElectronico for p in page.items] == ["pendiente@example.com"]
    assert page.items[0].estadoRelacion == "PENDIENTE" and page.items[0].fechaIncorporacion is None
    summary = page.resumen
    assert (summary.totalActivos, summary.bajas, summary.invitacionesPendientes) == (3, 0, 1)


def test_invitacion_cancelada_sin_aceptar_no_es_personal_ni_baja(db, mails, team):
    """Caso de Nanami Kento: se invitó, nunca aceptó y se canceló por tener el correo equivocado."""
    guest, invitation = invite(db, team, "nanami@example.com", "nanami")
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", invitation.idInstitucionUsuario)
    relation = reload(db, InstitutionUser, invitation.idInstitucionUsuario)
    # En la base queda BAJA con fechaBaja (lo exige CK_InstitucionUsuario_baja), pero nunca se incorporó.
    assert relation.estadoRelacion == "BAJA" and relation.fechaBaja is not None and relation.fechaIncorporacion is None
    assertNotPersonnel(db, team, "nanami@example.com", invitation.idInstitucionUsuario)
    summary = listing(db, team).resumen
    assert (summary.totalActivos, summary.bajas, summary.invitacionesPendientes) == (3, 0, 0)
    assert listing(db, team).total == 3
    # La auditoría de la cancelación se conserva (trazabilidad).
    assert db.scalar(select(Audit).where(Audit.accion == "CANCELAR_INVITACION_INSTITUCION",
                                         Audit.idRegistro == invitation.idInstitucionUsuario)) is not None


def test_invitacion_rechazada_no_es_personal(db, mails, team):
    guest, invitation = invite(db, team, "rechaza@example.com", "rechaza")
    institutions.respondInvitation(db, guest, invitation.idInstitucionUsuario, accept=False)
    assert reload(db, InstitutionUser, invitation.idInstitucionUsuario).fechaIncorporacion is None
    assertNotPersonnel(db, team, "rechaza@example.com", invitation.idInstitucionUsuario)
    assert listing(db, team).resumen.bajas == 0


def test_invitacion_vencida_no_es_personal_pero_se_puede_reenviar_desde_invitaciones(db, mails, team):
    guest, invitation = invite(db, team, "vencida@example.com", "vencida")
    relation = reload(db, InstitutionUser, invitation.idInstitucionUsuario)
    relation.fechaInvitacion = nowForDb() - timedelta(days=institutions.INVITATION_VALIDITY_DAYS + 1)
    db.commit()
    assertNotPersonnel(db, team, "vencida@example.com", invitation.idInstitucionUsuario)
    summary = listing(db, team).resumen
    assert (summary.invitacionesPendientes, summary.bajas) == (0, 0)
    vencida = personnel.listSentInvitations(db, team.moderator, team.id, estado="VENCIDA")  # los operadores los invita un moderador
    assert [i.correoElectronico for i in vencida.items] == ["vencida@example.com"] and vencida.items[0].puedeReenviar
    # Reenviar la renueva: vuelve a ser una invitación pendiente vigente.
    institutions.resendInvitation(db, team.moderator, team.id, "OPERADOR", invitation.idInstitucionUsuario)
    assert listing(db, team, estado="PENDIENTE").total == 1


def test_cuenta_invitada_creada_pero_nunca_incorporada_no_es_personal(db, mails, team):
    """Cuenta nueva creada por la invitación (queda pendiente de activación) y cancelada antes de activarse."""
    invitation = institutions.invite(db, team.moderator, team.id, "OPERADOR", "nueva@example.com", "Nueva", "Cuenta")
    assert invitation.cuentaPendiente
    assert listing(db, team, estado="PENDIENTE").items[0].cuentaPendiente
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", invitation.idInstitucionUsuario)
    assertNotPersonnel(db, team, "nueva@example.com", invitation.idInstitucionUsuario)


def test_invitacion_aceptada_aparece_como_integrante_activo(db, mails, team):
    guest, invitation = invite(db, team, "acepta@example.com", "acepta")
    institutions.respondInvitation(db, guest, invitation.idInstitucionUsuario, accept=True)
    page = listing(db, team, estado="ACTIVO")
    person = next(p for p in page.items if p.correoElectronico == "acepta@example.com")
    assert person.fechaIncorporacion is not None and page.resumen.operadoresActivos == 2
    assert personnel.getProfile(db, team.owner, team.id, invitation.idInstitucionUsuario).estadoRelacion == "ACTIVO"


def test_integrante_activo_desvinculado_figura_como_baja_con_su_historial(db, mails, team):
    operator = relationOf(db, team, team.operator).idInstitucionUsuario
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", operator)
    baja = listing(db, team, estado="BAJA")
    assert [p.idInstitucionUsuario for p in baja.items] == [operator] and baja.resumen.bajas == 1
    profile = personnel.getProfile(db, team.owner, team.id, operator)
    assert profile.estadoRelacion == "BAJA" and profile.fechaBaja and profile.fechaIncorporacion
    kinds = [event.tipo for event in profile.historial]
    assert "DESVINCULACION" in kinds and "INCORPORACION" in kinds
    assert profile.matriculaProfesional == "MP-123"  # conserva la información histórica permitida


def test_el_historial_de_quien_fue_baja_no_incluye_invitaciones_canceladas_posteriores(db, mails, team):
    """Se desvinculó, se la invitó de nuevo, y esa segunda invitación se canceló: sigue siendo una baja real; la cancelada no suma."""
    operator = relationOf(db, team, team.operator).idInstitucionUsuario
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", operator)
    again = institutions.invite(db, team.moderator, team.id, "OPERADOR", team.operator.correoElectronico)
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", again.idInstitucionUsuario)
    page = listing(db, team, estado="BAJA")
    assert [p.estadoRelacion for p in page.items] == ["BAJA"] and page.items[0].periodos == 1
    assert page.items[0].idInstitucionUsuario == operator  # el vínculo mostrado es el que realmente se incorporó
    profile = personnel.getProfile(db, team.owner, team.id, again.idInstitucionUsuario)  # abrir la cancelada muestra a la persona real
    assert profile.idInstitucionUsuario == operator and profile.periodosAnteriores == []
    assert all(event.tipo != "INVITACION_CANCELADA" for event in profile.historial)


def test_revocar_a_un_moderador_cancela_sus_invitaciones_y_no_las_convierte_en_bajas(db, mails, team):
    guest, invitation = invite(db, team, "huerfana@example.com", "huerfana")  # invitada por el moderador
    institutions.revokeMember(db, team.owner, team.id, "MODERADOR", relationOf(db, team, team.moderator).idInstitucionUsuario)
    assert reload(db, InstitutionUser, invitation.idInstitucionUsuario).estadoRelacion == "BAJA"
    assert listing(db, team).resumen.bajas == 1  # solo el moderador (se incorporó): la invitación huérfana no cuenta
    assert "huerfana@example.com" not in emails(listing(db, team, estado="BAJA"))


def test_invitaciones_enviadas_clasifica_cada_estado_y_no_toca_al_personal(db, mails, team):
    pending = invite(db, team, "p@example.com", "p")[1]
    cancelled = invite(db, team, "c@example.com", "c")[1]
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", cancelled.idInstitucionUsuario)
    guestR, rejected = invite(db, team, "r@example.com", "r")
    institutions.respondInvitation(db, guestR, rejected.idInstitucionUsuario, accept=False)
    guestA, accepted = invite(db, team, "a@example.com", "a")
    institutions.respondInvitation(db, guestA, accepted.idInstitucionUsuario, accept=True)
    expired = invite(db, team, "e@example.com", "e")[1]
    reload(db, InstitutionUser, expired.idInstitucionUsuario).fechaInvitacion = nowForDb() - timedelta(days=institutions.INVITATION_VALIDITY_DAYS + 1)
    db.commit()
    page = personnel.listSentInvitations(db, team.moderator, team.id)
    byEmail = {i.correoElectronico: i for i in page.items}
    assert {k: v.estado for k, v in byEmail.items() if k.split("@")[0] in "pcrae" and len(k.split("@")[0]) == 1} == {
        "p@example.com": "PENDIENTE", "c@example.com": "CANCELADA", "r@example.com": "RECHAZADA", "a@example.com": "ACEPTADA",
        "e@example.com": "VENCIDA"}
    assert byEmail["a@example.com"].idPersonal == accepted.idInstitucionUsuario and byEmail["c@example.com"].idPersonal is None
    assert byEmail["p@example.com"].puedeReenviar and byEmail["p@example.com"].puedeCancelar
    assert not byEmail["c@example.com"].puedeReenviar and not byEmail["a@example.com"].puedeCancelar
    assert page.resumen["PENDIENTE"] == 1 and page.resumen["VENCIDA"] == 1 and page.resumen["CANCELADA"] == 1
    assert [i.estado for i in personnel.listSentInvitations(db, team.owner, team.id, estado="RECHAZADA").items] == ["RECHAZADA"]
    expectError("DATOS_INVALIDOS", personnel.listSentInvitations, db, team.owner, team.id, estado="X")
    # El propietario (que creó la institución) no es una invitación.
    assert "duenia@example.com" not in byEmail
    assert pending is not None


def test_invitaciones_enviadas_exige_ser_del_equipo(db, mails, team):
    expectError("PERMISO_INSUFICIENTE", personnel.listSentInvitations, db, team.operator, team.id)


def test_el_endpoint_antiguo_de_miembros_no_lista_invitaciones_canceladas_como_bajas(db, mails, team):
    guest, invitation = invite(db, team, "vieja@example.com", "vieja")
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", invitation.idInstitucionUsuario)
    operator = relationOf(db, team, team.operator).idInstitucionUsuario
    institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", operator)
    listed = institutions.listMembers(db, team.owner, team.id, "OPERADOR", incluirBajas=True)
    assert [m.idInstitucionUsuario for m in listed] == [operator]
