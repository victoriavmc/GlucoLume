# Ciclo de vida de las cuentas institucionales: varias instituciones a la vez, baja institucional que solo afecta a esa relación,
# período de gracia de 30 días, eliminación voluntaria y automática con anonimización de Usuario, conservación de InstitucionUsuario y
# de la autoría de las mediciones, y reasignación de los pacientes de un operador desvinculado.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_account_lifecycle.py -v

import json
import threading
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import AuthError
from app.models.accountToken import AccountToken
from app.models.audit import Audit
from app.models.institutionUser import InstitutionUser
from app.models.localCredential import LocalCredential
from app.models.measurementProfile import MeasurementProfile
from app.models.patientReassignment import PatientReassignment
from app.models.profileTransfer import ProfileTransfer
from app.models.user import User
from app.models.userSession import UserSession
from app.schemas.reassignment import ReassignmentAssignRequest
from app.services import accountDeletion as deletion
from app.services import accountGrace, accountLifecycle, personnelRetention, quota, reassignments
from app.services import auth as authService
from app.services import institution as institutions
from app.services import institutionPatients as patients
from app.services import institutionReassignments as manager
from app.services.audit import personName
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import audits, confirm, db, engine, mails, makeSession, reload, requestAndGetToken  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_institution_patients import addOperator, patientData
from tests.test_institutions import expectError, freshLookupLimiter, institutional, newInstitution, relationOf, team  # noqa: F401
from tests.legacy_offboarding import legacyRevoke
from tests.test_measurements import completeOximetry, device

GRACE_SUBJECT = "Tu cuenta no tiene instituciones: tenés 30 días"
PENDING_SUBJECT = "Hay pacientes pendientes de reasignación"


# --- Ayudas ----------------------------------------------------------------------------------------------------------------------


def secondInstitution(db, user, cuit="87654321", nombre="Laboratorio Norte"):
    """Otra institución que incorpora a `user` (como moderador). Devuelve (institución, propietario)."""
    owner = institutional(db, f"owner-{cuit}@example.com", f"owner{cuit}")
    institution = newInstitution(db, owner, cuit, nombre)
    invitation = institutions.invite(db, owner, institution.idInstitucion, "MODERADOR", user.correoElectronico)
    institutions.respondInvitation(db, user, invitation.idInstitucionUsuario, accept=True)
    return institution, owner


def revokeOperator(db, team, user):
    """Baja de un operador. Si conserva pacientes, la baja actual se rechaza (hay que reasignarlos antes: tests/test_operator_offboarding.py);
    estas pruebas ejercitan lo que pasa DESPUÉS de una baja heredada con pacientes a cargo, así que la reproducen (tests/legacy_offboarding.py)."""
    relation = relationOf(db, team, user)
    if reassignments.activeProfileCount(db, relation.idInstitucionUsuario):
        return legacyRevoke(db, team.moderator, team.id, relation.idInstitucionUsuario)
    return institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", relation.idInstitucionUsuario)


def forceExpiry(db, user, daysAgo=31):
    db.execute(update(User).where(User.idUsuario == user.idUsuario).values(
        fechaInicioGracia=nowForDb() - timedelta(days=daysAgo), fechaVencimientoGracia=nowForDb() - timedelta(hours=1)))
    db.commit()


def mailsWith(mails, subject):
    return [m for m in mails if m["subject"] == subject]


def lastRelation(db, team, user):
    db.expire_all()
    return db.scalars(select(InstitutionUser).where(
        InstitutionUser.idInstitucion == team.id, InstitutionUser.idUsuarioInvitado == user.idUsuario)
        .order_by(InstitutionUser.fechaInvitacion.desc())).first()


def newPatient(db, team, actor, responsible=None, **overrides):
    data = patientData(**overrides)
    if responsible is not None:
        data = data.model_copy(update={"idInstitucionUsuarioResponsable": responsible.idInstitucionUsuario})
    return patients.createPatient(db, actor, team.id, data)


def tasks(db, estado=None):
    db.expire_all()
    query = select(PatientReassignment)
    if estado:
        query = query.where(PatientReassignment.estado == estado)
    return list(db.scalars(query))


# --- 1-2. Varias instituciones: la baja afecta solo a una relación ---------------------------------------------------------------


def test_la_baja_de_una_institucion_conserva_las_demas_y_no_inicia_el_plazo(db, mails, team):
    operator = team.operator
    other, _ = secondInstitution(db, operator)
    otherBefore = db.scalar(select(InstitutionUser).where(InstitutionUser.idInstitucion == other.idInstitucion,
                                                          InstitutionUser.idUsuarioInvitado == operator.idUsuario))
    snapshot = (otherBefore.rolInstitucion, otherBefore.estadoRelacion, otherBefore.fechaIncorporacion, otherBefore.fechaBaja)
    mails.clear()
    revokeOperator(db, team, operator)

    user = reload(db, User, operator.idUsuario)
    assert user.estado == "ACTIVO" and user.fechaInicioGracia is None and user.fechaVencimientoGracia is None
    assert accountGrace.activeBondCount(db, operator.idUsuario) == 1
    otherAfter = reload(db, InstitutionUser, otherBefore.idInstitucionUsuario)
    assert (otherAfter.rolInstitucion, otherAfter.estadoRelacion, otherAfter.fechaIncorporacion, otherAfter.fechaBaja) == snapshot
    assert mailsWith(mails, GRACE_SUBJECT) == [] and audits(db, "INICIAR_PERIODO_GRACIA") == []
    # El evento de la baja informa que la cuenta conserva otras instituciones.
    event = json.loads(audits(db, "REVOCAR_MIEMBRO_INSTITUCION")[-1].datosNuevos)
    assert event["cuentaConservaOtrasInstituciones"] is True
    # Con una institución activa no puede eliminarse por autoservicio.
    error = expectError("VINCULO_INSTITUCIONAL_ACTIVO", deletion.requestDeletion, db, user)
    assert error.message == "Tu cuenta está vinculada a una o más instituciones. Para eliminarla, primero debés finalizar tus vinculaciones institucionales."


def test_el_operador_dado_de_baja_pierde_el_acceso_a_esa_institucion_y_la_cuenta_global_no_cambia(db, mails, team):
    operator = team.operator
    secondInstitution(db, operator)
    before = reload(db, User, operator.idUsuario)
    profileData = (before.nombre, before.apellido, before.correoElectronico, before.usuario, before.tipoCuenta)
    revokeOperator(db, team, operator)
    expectError("INSTITUCION_NO_ENCONTRADA", institutions.getDetail, db, operator, team.id)
    after = reload(db, User, operator.idUsuario)
    assert (after.nombre, after.apellido, after.correoElectronico, after.usuario, after.tipoCuenta) == profileData
    assert len(institutions.listMine(db, operator)) == 1  # sigue viendo la otra institución


# --- 3-5. Última baja: período de gracia -----------------------------------------------------------------------------------------


def test_la_baja_de_la_ultima_institucion_inicia_el_periodo_de_gracia_de_30_dias(db, mails, team):
    operator = team.operator
    revokeOperator(db, team, operator)
    user = reload(db, User, operator.idUsuario)
    assert user.estado == "ACTIVO"  # la cuenta existe
    assert user.fechaVencimientoGracia - user.fechaInicioGracia == timedelta(days=30)
    grace = authService.accountSummary(db, user).periodoGracia
    assert (grace.diasRestantes, grace.fechaVencimiento) == (30, user.fechaVencimientoGracia)
    [mail] = mailsWith(mails, GRACE_SUBJECT)
    assert mail["to"] == "operadora@example.com" and "30" in mail["text"]
    [event] = audits(db, "INICIAR_PERIODO_GRACIA")
    assert json.loads(event.datosNuevos)["origen"] == "BAJA_INSTITUCIONAL" and event.idRegistro == operator.idUsuario
    # Sin instituciones no consume cupo en ninguna.
    assert quota.usage(db, team.id).usuariosActivos == 2
    # Los días restantes bajan con el tiempo; el plazo no se reinicia.
    db.execute(update(User).where(User.idUsuario == operator.idUsuario).values(
        fechaInicioGracia=nowForDb() - timedelta(days=10), fechaVencimientoGracia=nowForDb() + timedelta(days=19, hours=5)))
    db.commit()
    assert authService.accountSummary(db, reload(db, User, operator.idUsuario)).periodoGracia.diasRestantes == 20
    assert accountGrace.startIfOrphaned(db, operator.idUsuario, nowForDb(), None, "OTRO") is None  # un plazo en curso no se reinicia
    assert len(audits(db, "INICIAR_PERIODO_GRACIA")) == 1


def test_una_invitacion_pendiente_no_cancela_el_plazo_pero_aceptarla_si_y_conserva_la_cuenta(db, mails, team):
    operator = team.operator
    revokeOperator(db, team, operator)
    started = reload(db, User, operator.idUsuario).fechaVencimientoGracia
    invitation = institutions.invite(db, team.moderator, team.id, "OPERADOR", operator.correoElectronico)
    user = reload(db, User, operator.idUsuario)
    assert user.fechaVencimientoGracia == started  # pendiente: no cancela
    # Una cuenta en gracia puede rechazar una invitación sin alterar el plazo.
    institutions.respondInvitation(db, user, invitation.idInstitucionUsuario, accept=False)
    assert reload(db, User, operator.idUsuario).fechaVencimientoGracia == started
    again = institutions.invite(db, team.moderator, team.id, "OPERADOR", operator.correoElectronico)
    institutions.respondInvitation(db, reload(db, User, operator.idUsuario), again.idInstitucionUsuario, accept=True)

    user = reload(db, User, operator.idUsuario)
    assert user.idUsuario == operator.idUsuario and user.estado == "ACTIVO"
    assert user.fechaInicioGracia is None and user.fechaVencimientoGracia is None
    assert authService.accountSummary(db, user).periodoGracia is None
    [event] = audits(db, "CANCELAR_PERIODO_GRACIA")
    assert json.loads(event.datosNuevos)["motivo"] == "INCORPORACION_A_INSTITUCION" and event.datosPrevios
    # Solo recupera los accesos de la nueva vinculación (la vieja relación sigue en BAJA).
    states = sorted(r.estadoRelacion for r in db.scalars(select(InstitutionUser).where(
        InstitutionUser.idUsuarioInvitado == operator.idUsuario, InstitutionUser.idInstitucion == team.id,
        InstitutionUser.fechaIncorporacion.is_not(None))))
    assert states == ["ACTIVO", "BAJA"]
    # Si vuelve a quedar sin instituciones empieza un plazo nuevo.
    revokeOperator(db, team, operator)
    assert reload(db, User, operator.idUsuario).fechaInicioGracia is not None
    assert len(audits(db, "INICIAR_PERIODO_GRACIA")) == 2


def test_la_invitacion_pendiente_o_la_nunca_incorporada_no_inicia_gracia(db, mails, team):
    invited = institutional(db, "nunca@example.com", "nunca")
    invitation = institutions.invite(db, team.moderator, team.id, "OPERADOR", invited.correoElectronico)
    institutions.respondInvitation(db, invited, invitation.idInstitucionUsuario, accept=False)  # rechaza: BAJA sin incorporación
    assert reload(db, User, invited.idUsuario).fechaVencimientoGracia is None and audits(db, "INICIAR_PERIODO_GRACIA") == []


def test_cerrar_la_institucion_inicia_el_plazo_solo_de_quienes_no_tienen_otra(db, mails, team):
    secondInstitution(db, team.moderator)  # el moderador conserva otra institución
    mails.clear()
    from app.schemas.institution import InstitutionDeletionRequest
    from tests.test_account_deletion import PASSWORD
    institutions.deleteInstitution(db, team.owner, team.id, InstitutionDeletionRequest(
        confirmacionNombre=team.institution.nombre, password=PASSWORD))
    states = {name: reload(db, User, user.idUsuario) for name, user in
              (("owner", team.owner), ("moderator", team.moderator), ("operator", team.operator))}
    assert states["moderator"].fechaVencimientoGracia is None
    assert states["owner"].fechaVencimientoGracia is not None and states["operator"].fechaVencimientoGracia is not None
    assert {m["to"] for m in mailsWith(mails, GRACE_SUBJECT)} == {"duenia@example.com", "operadora@example.com"}
    assert json.loads(audits(db, "ELIMINAR_INSTITUCION")[-1].datosNuevos)["cuentasEnPeriodoGracia"] == 2


# --- 6-7. Eliminación voluntaria -------------------------------------------------------------------------------------------------


def test_eliminacion_voluntaria_sin_instituciones_activas_no_espera_los_30_dias(db, mails, team):
    operator = team.operator
    revokeOperator(db, team, operator)
    session = makeSession(db, operator)
    preview = deletion.describeDeletion(db, reload(db, User, operator.idUsuario), nowForDb())
    assert preview["puedeEliminar"] and preview["periodoGracia"]["diasRestantes"] == 30 and preview["datosEliminados"]
    assert preview["datosConservados"]  # estuvo incorporada: sus relaciones históricas se conservan
    confirm(db, requestAndGetToken(db, operator, mails))  # reautenticada con contraseña, sin esperar el vencimiento
    user = reload(db, User, operator.idUsuario)
    assert user.estado == "ELIMINADO" and user.fechaEliminacion and user.fechaVencimientoGracia is None
    # Una sesión anterior no sigue operando.
    assert reload(db, UserSession, session.idSesion).fechaRevocacion is not None
    with pytest.raises(AuthError):
        authService.resolveAccessSession(db, {"sub": str(operator.idUsuario), "sid": str(session.idSesion)})


def test_con_instituciones_activas_no_hay_autoservicio_ni_en_la_confirmacion(db, mails, team):
    operator = team.operator
    preview = deletion.describeDeletion(db, operator, nowForDb())
    assert preview["puedeEliminar"] is False and preview["codigoBloqueo"] == "VINCULO_INSTITUCIONAL_ACTIVO"
    expectError("VINCULO_INSTITUCIONAL_ACTIVO", deletion.requestDeletion, db, operator)
    assert db.scalar(select(func.count()).select_from(AccountToken)) == 0 and not mails
    owner_preview = deletion.describeDeletion(db, team.owner, nowForDb())
    assert owner_preview["puedeEliminar"] is False


# --- 8-9. Eliminación automática y anonimización ---------------------------------------------------------------------------------


def test_la_eliminacion_automatica_solo_alcanza_a_los_planes_vencidos(db, mails, team):
    operator = team.operator
    revokeOperator(db, team, operator)
    assert accountLifecycle.sweep(db) == {"revisadas": 0, "eliminadas": 0, "omitidas": 0, "errores": 0}  # el plazo corre todavía
    assert reload(db, User, operator.idUsuario).estado == "ACTIVO"
    forceExpiry(db, operator)
    mails.clear()
    assert accountLifecycle.sweep(db) == {"revisadas": 1, "eliminadas": 1, "omitidas": 0, "errores": 0}
    user = reload(db, User, operator.idUsuario)
    assert user.estado == "ELIMINADO" and user.fechaEliminacion is not None
    [mail] = [m for m in mails if m["to"] == "operadora@example.com"]
    assert "se eliminó" in mail["text"]
    [event] = audits(db, "ELIMINACION_AUTOMATICA_CUENTA")
    data = json.loads(event.datosNuevos)
    assert event.idRegistro == operator.idUsuario and event.resultado == "EXITO" and data["origen"] == "VENCIMIENTO_PERIODO_GRACIA"
    assert "operadora@example.com" not in event.datosNuevos and "Victoria" not in event.datosNuevos  # sin datos personales en el JSON
    # Idempotente: una segunda pasada no vuelve a procesarla ni a enviar otro correo.
    mails.clear()
    assert accountLifecycle.sweep(db)["revisadas"] == 0 and not mails
    assert len(audits(db, "ELIMINACION_AUTOMATICA_CUENTA")) == 1


def test_la_anonimizacion_deja_la_cuenta_inutilizable_y_conserva_la_estructura_historica(db, mails, team):
    operator = team.operator
    op2 = addOperator(db, team, "otro@example.com", "otro")  # otra cuenta que también se anonimizará (índices únicos filtrados)
    other = db.get(User, op2.idUsuarioInvitado)
    session = makeSession(db, operator)
    relationBefore = relationOf(db, team, operator)
    expected = {c: getattr(relationBefore, c) for c in ("idInstitucionUsuario", "idInstitucion", "idUsuarioInvitado", "rolInstitucion",
                "matriculaProfesional", "legajoInstitucional", "funcionProfesional", "origenVinculo", "idUsuarioInvitador",
                "fechaInvitacion", "fechaIncorporacion")}
    auditsBefore = len(audits(db))
    for user in (operator, other):
        institutions.revokeMember(db, team.moderator, team.id, "OPERADOR", relationOf(db, team, user).idInstitucionUsuario)
        forceExpiry(db, user)
    accountLifecycle.sweep(db)

    for user in (operator, other):
        row = reload(db, User, user.idUsuario)
        assert (row.nombre, row.apellido, row.correoElectronico, row.usuario, row.fechaNacimiento, row.sexo) == (None,) * 6
        assert row.estado == "ELIMINADO" and row.idUsuario == user.idUsuario  # el identificador técnico se conserva
        assert db.scalar(select(func.count()).select_from(LocalCredential).where(LocalCredential.idUsuario == user.idUsuario)) == 0
        assert db.scalar(select(func.count()).select_from(AccountToken).where(AccountToken.idUsuario == user.idUsuario)) == 0
    assert reload(db, UserSession, session.idSesion).fechaRevocacion is not None
    # InstitucionUsuario: todos los campos históricos siguen, más el nombre profesional histórico.
    kept = reload(db, InstitutionUser, expected["idInstitucionUsuario"])
    assert {c: getattr(kept, c) for c in expected} == expected
    assert kept.estadoRelacion == "BAJA" and kept.fechaBaja is not None
    assert (kept.nombreProfesionalHistorico, kept.apellidoProfesionalHistorico) == ("Victoria", "Cortés")
    assert personName(kept, reload(db, User, operator.idUsuario)) == "Victoria Cortés"
    # La auditoría no se pierde: solo se agregan eventos.
    assert len(audits(db)) > auditsBefore
    # Una cuenta anonimizada no puede autenticarse ni recuperar permisos.
    with pytest.raises(AuthError):
        authService.resolveAccessSession(db, {"sub": str(operator.idUsuario), "sid": str(session.idSesion)})
    expectError("INSTITUCION_NO_ENCONTRADA", institutions.getDetail, db, reload(db, User, operator.idUsuario), team.id)


def test_la_historia_de_moderadores_tambien_conserva_el_nombre_y_las_invitaciones_pendientes_se_cancelan(db, mails, team):
    moderator = team.moderator
    pending = institutional(db, "pendiente@example.com", "pendiente")
    institutions.invite(db, moderator, team.id, "OPERADOR", pending.correoElectronico)
    institutions.revokeMember(db, team.owner, team.id, "MODERADOR", relationOf(db, team, moderator).idInstitucionUsuario)
    forceExpiry(db, moderator)
    accountLifecycle.sweep(db)
    relation = lastRelation(db, team, moderator)
    assert relation.estadoRelacion == "BAJA" and (relation.nombreProfesionalHistorico, relation.apellidoProfesionalHistorico) == ("Victoria", "Cortés")
    # La invitación que había emitido el moderador cayó al darlo de baja (no queda pendiente a su nombre).
    assert db.scalar(select(InstitutionUser.estadoRelacion).where(InstitutionUser.idUsuarioInvitado == pending.idUsuario)) == "BAJA"


def test_idUsuarioInvitado_e_idUsuarioInvitador_siguen_validos_cuando_el_usuario_se_anonimiza(db, mails, team):
    operator = team.operator
    relation = relationOf(db, team, operator)
    inviter = reload(db, User, relation.idUsuarioInvitador)  # el moderador que lo invitó
    revokeOperator(db, team, operator)
    institutions.revokeMember(db, team.owner, team.id, "MODERADOR", relationOf(db, team, inviter).idInstitucionUsuario)
    for user in (operator, inviter):
        forceExpiry(db, user)
    accountLifecycle.sweep(db)
    assert reload(db, User, inviter.idUsuario).estado == "ELIMINADO" and reload(db, User, operator.idUsuario).estado == "ELIMINADO"
    kept = reload(db, InstitutionUser, relation.idInstitucionUsuario)
    assert kept.idUsuarioInvitado == operator.idUsuario and kept.idUsuarioInvitador == inviter.idUsuario  # sin NULL ni reemplazos
    # Los JOIN históricos siguen resolviendo (la clave foránea no quedó huérfana).
    joined = db.execute(select(InstitutionUser.idInstitucionUsuario).join(User, User.idUsuario == InstitutionUser.idUsuarioInvitador)
                        .where(InstitutionUser.idInstitucionUsuario == relation.idInstitucionUsuario)).all()
    assert len(joined) == 1


# --- 12. Autoría de las mediciones -------------------------------------------------------------------------------------------------


def authorOf(db, measurementId):
    return db.scalar(select(Audit.idRelacionado).where(Audit.accion == "INICIAR_MEDICION", Audit.idRegistro == measurementId))


def test_la_autoria_de_las_mediciones_sobrevive_a_la_baja_la_transferencia_y_la_anonimizacion(db, mails, team):
    operator = team.operator
    op1 = relationOf(db, team, operator)
    created = newPatient(db, team, operator)
    dev = device(db, institucion=team.id)
    old = [completeOximetry(db, operator, created.idPerfilMedicion, dev).idMedicion for _ in range(3)]
    assert {authorOf(db, m) for m in old} == {op1.idInstitucionUsuario}

    op2, op2User = addOperator(db, team, "dos@example.com", "dostres"), None
    op2User = db.get(User, op2.idUsuarioInvitado)
    revokeOperator(db, team, operator)
    [task] = tasks(db, "PENDIENTE")
    manager.assign(db, team.moderator, team.id, ReassignmentAssignRequest(idsReasignacion=[task.idReasignacionPaciente], idOperadorNuevo=op2.idInstitucionUsuario))
    forceExpiry(db, operator)
    accountLifecycle.sweep(db)
    assert reload(db, User, operator.idUsuario).estado == "ELIMINADO"

    assert {authorOf(db, m) for m in old} == {op1.idInstitucionUsuario}  # el operador 2 no pasa a ser autor de lo anterior
    new = completeOximetry(db, op2User, created.idPerfilMedicion, dev)  # las nuevas mediciones se atribuyen a quien las hace
    assert authorOf(db, new.idMedicion) == op2.idInstitucionUsuario
    # La referencia sigue resolviendo a la persona con su nombre histórico, sin cuenta autenticable.
    kept = reload(db, InstitutionUser, op1.idInstitucionUsuario)
    assert personName(kept, reload(db, User, operator.idUsuario)) == "Victoria Cortés"
    assert reload(db, MeasurementProfile, created.idPerfilMedicion).idInstitucionUsuarioResponsable == op2.idInstitucionUsuario


# --- 13-14. Baja de un operador con pacientes --------------------------------------------------------------------------------------


def test_sin_pacientes_la_baja_se_completa_sin_tareas_ni_avisos(db, mails, team):
    revokeOperator(db, team, team.operator)
    assert tasks(db) == [] and mailsWith(mails, PENDING_SUBJECT) == []
    assert audits(db, "PACIENTES_PENDIENTES_REASIGNACION") == []


def test_con_pacientes_activos_quedan_pendientes_se_revoca_el_acceso_y_se_avisa_a_los_moderadores(db, mails, team):
    operator = team.operator
    first = newPatient(db, team, operator, dni="20.111.222")
    second = newPatient(db, team, operator, dni="20.333.444", nombre="ana", apellido="paz")
    discharged = newPatient(db, team, operator, dni="20.555.666", nombre="luis", apellido="gil")
    patients.dischargePatient(db, team.owner, team.id, discharged.idPerfilMedicion)
    relation = relationOf(db, team, operator)
    mails.clear()
    revokeOperator(db, team, operator)

    pending = tasks(db, "PENDIENTE")
    assert {t.idPerfilMedicion for t in pending} == {first.idPerfilMedicion, second.idPerfilMedicion}  # el dado de baja no se reasigna
    assert all(t.idOperadorAnterior == relation.idInstitucionUsuario and t.idOperadorNuevo is None and t.motivo == "BAJA_OPERADOR" for t in pending)
    # El operador ya no es responsable vigente: no tiene acceso a nada de la institución, ni a sus antiguos pacientes.
    expectError("INSTITUCION_NO_ENCONTRADA", patients.getPatient, db, operator, team.id, first.idPerfilMedicion)
    expectError("INSTITUCION_NO_ENCONTRADA", patients.listPatients, db, operator, team.id)
    # Aviso a los moderadores (el propietario no, porque hay un moderador activo); sin datos de los pacientes.
    [mail] = mailsWith(mails, PENDING_SUBJECT)
    assert mail["to"] == "moderador@example.com" and "2" in mail["text"] and "20.111.222" not in mail["text"]
    event = audits(db, "PACIENTES_PENDIENTES_REASIGNACION")
    assert len(event) == 1 and json.loads(event[0].datosNuevos)["pacientesPendientes"] == 2
    assert reassignments.pendingCount(db, team.id) == 2


def test_sin_moderador_activo_el_aviso_va_al_propietario(db, mails, team):
    patient = newPatient(db, team, team.operator)
    institutions.revokeMember(db, team.owner, team.id, "MODERADOR", relationOf(db, team, team.moderator).idInstitucionUsuario)
    mails.clear()
    expectError("PACIENTES_ASIGNADOS", institutions.revokeMember, db, team.owner, team.id, "OPERADOR", relationOf(db, team, team.operator).idInstitucionUsuario)
    legacyRevoke(db, team.owner, team.id, relationOf(db, team, team.operator).idInstitucionUsuario)  # baja heredada: sin moderador avisa al propietario
    assert patient is not None
    assert [m["to"] for m in mailsWith(mails, PENDING_SUBJECT)] == ["duenia@example.com"]


def test_la_eliminacion_de_la_cuenta_no_espera_la_transferencia_de_pacientes(db, mails, team):
    operator = team.operator
    newPatient(db, team, operator)
    revokeOperator(db, team, operator)
    forceExpiry(db, operator)
    accountLifecycle.sweep(db)
    assert reload(db, User, operator.idUsuario).estado == "ELIMINADO"
    assert len(tasks(db, "PENDIENTE")) == 1  # la tarea sigue ahí para el moderador


# --- 15-17. Gestión de transferencias ---------------------------------------------------------------------------------------------


def test_reasignacion_individual_y_masiva_conserva_el_historial(db, mails, team, api):
    operator = team.operator
    ids = [newPatient(db, team, operator, dni=f"20.1{n}.222", nombre=f"p{n}", apellido="x") for n in range(3)]
    op2 = addOperator(db, team, "dos@example.com", "dostres")
    previous = relationOf(db, team, operator).idInstitucionUsuario
    revokeOperator(db, team, operator)
    path = f"/api/v1/institutions/{team.id}/reassignments"

    overview = api(team.moderator).get(path).json()
    assert overview["pendientes"] == 3 and overview["operadoresDisponibles"] == 1
    [group] = overview["grupos"]
    assert group["pendientes"] == 3 and group["estado"] == "PENDIENTE" and group["operadorAnterior"] == "Victoria Cortés"
    assert group["fechaDesvinculacion"] and group["idOperadorAnterior"] == str(previous)
    items = api(team.owner).get(f"{path}/items").json()["items"]
    assert len(items) == 3 and all(set(i) >= {"identificadorPseudonimo", "operadorAnterior", "estado"} for i in items)
    assert not any("dni" in i or "fechaNacimiento" in i for i in items)

    # Individual.
    response = api(team.moderator).post(f"{path}/assign", json={"idsReasignacion": [items[0]["idReasignacionPaciente"]],
                                                                "idOperadorNuevo": str(op2.idInstitucionUsuario), "observacion": "cobertura"})
    assert response.status_code == 200 and response.json()["reasignados"] == 1
    # Masiva (los dos restantes + una ya resuelta + una inexistente).
    rest = [i["idReasignacionPaciente"] for i in items[1:]]
    body = {"idsReasignacion": [items[0]["idReasignacionPaciente"], *rest, "00000000-0000-4000-8000-000000000000"],
            "idOperadorNuevo": str(op2.idInstitucionUsuario)}
    result = api(team.moderator).post(f"{path}/assign", json=body).json()
    assert result["reasignados"] == 2
    assert [r["resultado"] for r in result["resultados"]] == ["YA_RESUELTA", "REASIGNADO", "REASIGNADO", "NO_ENCONTRADA"]

    done = tasks(db, "COMPLETADA")
    assert len(done) == 3 and all(t.idOperadorNuevo == op2.idInstitucionUsuario and t.idUsuarioResolutor == team.moderator.idUsuario
                                  and t.fechaResolucion and t.resultado == "REASIGNADO" for t in done)
    assert {t.observacion for t in done} == {"Cobertura", None}
    for created in ids:
        assert reload(db, MeasurementProfile, created.idPerfilMedicion).idInstitucionUsuarioResponsable == op2.idInstitucionUsuario
    transfers = db.scalars(select(ProfileTransfer).where(ProfileTransfer.estado == "ACEPTADA")).all()
    assert len(transfers) == 3 and all(t.idOperadorDestino == op2.idInstitucionUsuario for t in transfers)
    assert len(audits(db, "ASIGNAR_RESPONSABLE_PACIENTE")) == 3
    assert all(json.loads(a.datosNuevos).get("idReasignacionPaciente") for a in audits(db, "ASIGNAR_RESPONSABLE_PACIENTE"))
    assert api(team.moderator).get(path).json()["pendientes"] == 0
    # El historial queda consultable.
    history = api(team.moderator).get(f"{path}/items", params={"estado": "COMPLETADA"}).json()
    assert history["total"] == 3 and history["items"][0]["operadorNuevo"] and history["items"][0]["resueltoPor"]
    # Y el operador nuevo recibe los avisos (uno por paciente, sin datos del paciente).
    assert len([m for m in mails if m["to"] == "dos@example.com" and m["subject"] == "Tenés un paciente nuevo a tu cargo"]) >= 1


def test_el_operador_no_ve_ni_gestiona_las_reasignaciones(db, mails, team, api):
    newPatient(db, team, team.operator)
    op2 = addOperator(db, team, "dos@example.com", "dostres")
    op2User = db.get(User, op2.idUsuarioInvitado)
    revokeOperator(db, team, team.operator)
    path = f"/api/v1/institutions/{team.id}/reassignments"
    assert api(op2User).get(path).status_code == 403 and api(op2User).get(f"{path}/items").status_code == 403
    [task] = tasks(db, "PENDIENTE")
    body = {"idsReasignacion": [str(task.idReasignacionPaciente)], "idOperadorNuevo": str(op2.idInstitucionUsuario)}
    assert api(op2User).post(f"{path}/assign", json=body).status_code == 403
    assert len(tasks(db, "PENDIENTE")) == 1
    assert api(team.moderator).get(f"/api/v1/institutions/{team.id}/dashboard").json()["pacientesPendientesReasignacion"] == 1


def test_solo_se_asigna_a_operadores_activos_de_la_misma_institucion_y_sin_candidatos_la_tarea_sigue(db, mails, team):
    newPatient(db, team, team.operator)
    from tests.test_institution_patients import otherInstitution
    _, _, foreign = otherInstitution(db)
    revokeOperator(db, team, team.operator)
    [task] = tasks(db, "PENDIENTE")
    ids = [task.idReasignacionPaciente]
    # No hay operadores activos: no se elige a nadie automáticamente.
    assert manager.overview(db, team.moderator, team.id).operadoresDisponibles == 0
    moderatorRelation, ownerRelation = relationOf(db, team, team.moderator), relationOf(db, team, team.owner)
    for target in (foreign.idInstitucionUsuario, moderatorRelation.idInstitucionUsuario, ownerRelation.idInstitucionUsuario, task.idOperadorAnterior):
        expectError("OPERADOR_NO_DISPONIBLE", manager.assign, db, team.moderator, team.id,
                    ReassignmentAssignRequest(idsReasignacion=ids, idOperadorNuevo=target))
    assert len(tasks(db, "PENDIENTE")) == 1
    # Un operador invitado pero todavía pendiente tampoco sirve.
    pending = institutional(db, "pendop@example.com", "pendop")
    invitation = institutions.invite(db, team.moderator, team.id, "OPERADOR", pending.correoElectronico)
    expectError("OPERADOR_NO_DISPONIBLE", manager.assign, db, team.moderator, team.id,
                ReassignmentAssignRequest(idsReasignacion=ids, idOperadorNuevo=invitation.idInstitucionUsuario))
    # Al aparecer un operador activo se puede resolver.
    institutions.respondInvitation(db, pending, invitation.idInstitucionUsuario, accept=True)
    assert manager.assign(db, team.moderator, team.id, ReassignmentAssignRequest(
        idsReasignacion=ids, idOperadorNuevo=invitation.idInstitucionUsuario)).reasignados == 1


def test_una_tarea_de_otra_institucion_no_se_puede_resolver_con_su_uuid(db, mails, team):
    from tests.test_institution_patients import otherInstitution
    newPatient(db, team, team.operator)
    revokeOperator(db, team, team.operator)
    [task] = tasks(db, "PENDIENTE")
    foreign, _, foreignRelation = otherInstitution(db)
    foreignModerator = db.scalar(select(User).where(User.correoElectronico == "otro-moderador@example.com"))
    result = manager.assign(db, foreignModerator, foreign.idInstitucion, ReassignmentAssignRequest(
        idsReasignacion=[task.idReasignacionPaciente], idOperadorNuevo=foreignRelation.idInstitucionUsuario))
    assert result.reasignados == 0 and result.resultados[0].resultado == "NO_ENCONTRADA"
    assert len(tasks(db, "PENDIENTE")) == 1


def test_reasignar_desde_la_ficha_del_paciente_tambien_completa_la_tarea(db, mails, team):
    created = newPatient(db, team, team.operator)
    op2 = addOperator(db, team, "dos@example.com", "dostres")
    revokeOperator(db, team, team.operator)
    patients.assignResponsible(db, team.moderator, team.id, created.idPerfilMedicion, op2.idInstitucionUsuario)
    assert tasks(db, "PENDIENTE") == [] and len(tasks(db, "COMPLETADA")) == 1


# --- 18. Pacientes históricos -------------------------------------------------------------------------------------------------------


def test_los_pacientes_dados_de_baja_o_desidentificados_no_generan_ni_conservan_tareas(db, mails, team):
    active = newPatient(db, team, team.operator, dni="20.111.111")
    gone = newPatient(db, team, team.operator, dni="20.222.222", nombre="ana", apellido="gil")
    purged = newPatient(db, team, team.operator, dni="20.333.333", nombre="eva", apellido="paz")
    patients.dischargePatient(db, team.owner, team.id, gone.idPerfilMedicion)
    patients.dischargePatient(db, team.owner, team.id, purged.idPerfilMedicion)
    db.execute(update(MeasurementProfile).where(MeasurementProfile.idPerfilMedicion == purged.idPerfilMedicion).values(
        nombre=None, apellido=None, dni=None, fechaNacimiento=None, edadDeclarada=None, fechaDepuracionDatosPersonales=nowForDb()))
    db.commit()
    revokeOperator(db, team, team.operator)
    assert [t.idPerfilMedicion for t in tasks(db, "PENDIENTE")] == [active.idPerfilMedicion]
    # Si el paciente pendiente se da de baja después, su tarea se cancela y queda en el historial.
    patients.dischargePatient(db, team.owner, team.id, active.idPerfilMedicion)
    [task] = tasks(db)
    assert task.estado == "CANCELADA" and task.resultado == "PACIENTE_DADO_DE_BAJA" and task.fechaResolucion
    # Ya no reaparece como paciente activo ni como pendiente.
    assert manager.overview(db, team.moderator, team.id).pendientes == 0


# --- 20-21. Auditoría y cupos --------------------------------------------------------------------------------------------------------


def test_la_baja_libera_el_cupo_y_conserva_todos_los_registros(db, mails, team):
    assert quota.usage(db, team.id).usuariosActivos == 3
    relationsBefore = db.scalar(select(func.count()).select_from(InstitutionUser))
    revokeOperator(db, team, team.operator)
    assert quota.usage(db, team.id).usuariosActivos == 2
    event = json.loads(audits(db, "REVOCAR_MIEMBRO_INSTITUCION")[-1].datosNuevos)
    assert event["usuariosActivos"] == 2 and event["capacidadMaximaUsuarios"] == 1000
    assert db.scalar(select(func.count()).select_from(InstitutionUser)) == relationsBefore  # nada se borra
    # Reincorporada en otra institución, consume un cupo allí y ninguno en la anterior.
    other, _ = secondInstitution(db, reload(db, User, team.operator.idUsuario))
    assert quota.usage(db, other.idInstitucion).usuariosActivos == 2 and quota.usage(db, team.id).usuariosActivos == 2


# --- 22. Concurrencia -------------------------------------------------------------------------------------------------------------------


def test_ejecuciones_simultaneas_eliminan_una_sola_vez(db, mails, engine, team):
    operator = team.operator
    revokeOperator(db, team, operator)
    forceExpiry(db, operator)
    mails.clear()
    makeSession_ = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    barrier = threading.Barrier(3)
    outcomes, failures = [], []

    def run():
        session = makeSession_()
        try:
            barrier.wait()
            outcomes.append(accountLifecycle.deleteExpired(session, operator.idUsuario, nowForDb())[0])
        except Exception as error:  # SQLite serializa las escrituras con un bloqueo de base: el perdedor puede ver «locked»
            failures.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=run) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    accountLifecycle.sweep(db)  # un reintento posterior tampoco duplica nada
    assert outcomes.count(accountLifecycle.ELIMINADA) <= 1
    assert reload(db, User, operator.idUsuario).estado == "ELIMINADO"
    assert len(audits(db, "ELIMINACION_AUTOMATICA_CUENTA")) == 1, (outcomes, failures)
    assert len([m for m in mails if m["to"] == "operadora@example.com"]) == 1


def test_si_la_incorporacion_gana_la_carrera_no_se_elimina_y_si_la_eliminacion_gana_no_se_incorpora(db, mails, team):
    operator = team.operator
    revokeOperator(db, team, operator)
    invitation = institutions.invite(db, team.moderator, team.id, "OPERADOR", operator.correoElectronico)
    forceExpiry(db, operator)
    # La incorporación se confirma antes: la revalidación bajo bloqueo la detecta aunque el candidato ya estaba preseleccionado.
    candidate = accountLifecycle.candidates(db, nowForDb())
    assert candidate == [operator.idUsuario]
    institutions.respondInvitation(db, reload(db, User, operator.idUsuario), invitation.idInstitucionUsuario, accept=True)
    assert accountLifecycle.deleteExpired(db, operator.idUsuario, nowForDb()) == (accountLifecycle.OMITIDA, "SIN_VENCIMIENTO")
    assert reload(db, User, operator.idUsuario).estado == "ACTIVO"
    # Caso inverso: la cuenta ya fue eliminada cuando intenta aceptar.
    other = institutional(db, "venc@example.com", "venc")
    forceExpiryTarget = institutions.invite(db, team.moderator, team.id, "OPERADOR", other.correoElectronico)
    db.execute(update(User).where(User.idUsuario == other.idUsuario).values(
        fechaInicioGracia=nowForDb() - timedelta(days=31), fechaVencimientoGracia=nowForDb() - timedelta(hours=1)))
    db.commit()
    assert accountLifecycle.deleteExpired(db, other.idUsuario, nowForDb())[0] == accountLifecycle.ELIMINADA
    # La invitación pendiente se canceló al eliminar la cuenta: no puede aceptarse más.
    expectError("INVITACION_NO_ENCONTRADA", institutions.respondInvitation, db, reload(db, User, other.idUsuario),
                forceExpiryTarget.idInstitucionUsuario, accept=True)
    assert lastRelation(db, team, other).estadoRelacion == "BAJA"


def test_un_impedimento_de_grupo_no_elimina_y_se_audita_una_sola_vez_por_dia(db, mails, team):
    from tests.test_account_deletion import addInstitution  # noqa: F401
    from app.models.group import Group
    from app.models.groupUser import GroupUser
    operator = team.operator
    revokeOperator(db, team, operator)
    group = Group(nombre="Familia", estado="ACTIVO")
    db.add(group)
    db.flush()
    db.add(GroupUser(idGrupo=group.idGrupo, idUsuario=operator.idUsuario, rolGrupo="PROPIETARIO", estadoRelacion="ACTIVO",
                     fechaIncorporacion=nowForDb()))
    db.commit()
    forceExpiry(db, operator)
    for _ in range(3):
        accountLifecycle.sweep(db)
    assert reload(db, User, operator.idUsuario).estado == "ACTIVO"
    failures = [a for a in audits(db, "ELIMINACION_AUTOMATICA_CUENTA") if a.resultado == "FALLO"]
    assert len(failures) == 1 and "PROPIETARIO_GRUPO_ACTIVO" in failures[0].observacion


# --- Retención / minimización de InstitucionUsuario --------------------------------------------------------------------------------------


def test_vencido_el_plazo_se_minimizan_los_datos_personales_historicos_sin_borrar_la_relacion(db, mails, team):
    operator = team.operator
    revokeOperator(db, team, operator)
    forceExpiry(db, operator)
    accountLifecycle.sweep(db)
    relation = lastRelation(db, team, operator)
    assert relation.matriculaProfesional == "MP-123" and relation.nombreProfesionalHistorico == "Victoria"
    assert personnelRetention.minimizeExpired(db, 120) == 0  # todavía dentro del plazo
    db.execute(update(InstitutionUser).where(InstitutionUser.idInstitucionUsuario == relation.idInstitucionUsuario).values(
        fechaBaja=nowForDb() - timedelta(days=366 * 11)))
    db.commit()
    assert personnelRetention.minimizeExpired(db, 120) == 1
    kept = reload(db, InstitutionUser, relation.idInstitucionUsuario)
    assert (kept.nombreProfesionalHistorico, kept.apellidoProfesionalHistorico, kept.legajoInstitucional, kept.matriculaProfesional) == (None,) * 4
    assert kept.fechaMinimizacionDatos is not None
    assert (kept.rolInstitucion, kept.estadoRelacion, kept.fechaIncorporacion, kept.idUsuarioInvitador) == (
        "OPERADOR", "BAJA", relation.fechaIncorporacion, relation.idUsuarioInvitador)
    assert personName(kept, reload(db, User, operator.idUsuario)) is None
    assert personnelRetention.minimizeExpired(db, 120) == 0  # idempotente
    assert personnelRetention.minimizeExpired(db, 0) == 0  # 0 = desactivado
    assert len(audits(db, "MINIMIZAR_DATOS_PERSONAL_HISTORICO")) == 1


def test_la_minimizacion_tampoco_expone_el_nombre_de_una_cuenta_que_sigue_activa(db, mails, team):
    operator = team.operator
    secondInstitution(db, operator)
    relation = relationOf(db, team, operator)
    revokeOperator(db, team, operator)
    db.execute(update(InstitutionUser).where(InstitutionUser.idInstitucionUsuario == relation.idInstitucionUsuario).values(
        fechaBaja=nowForDb() - timedelta(days=366 * 11)))
    db.commit()
    personnelRetention.minimizeExpired(db, 120)
    assert personName(reload(db, InstitutionUser, relation.idInstitucionUsuario), reload(db, User, operator.idUsuario)) is None


# --- Eliminación de los datos históricos por la institución ----------------------------------------------------------------------------


def test_el_moderador_elimina_los_datos_historicos_de_un_operador_desvinculado(db, mails, team):
    from app.services import personnel
    operator = team.operator
    secondInstitution(db, operator, cuit="72222222", nombre="Centro Este")  # la cuenta sigue activa en otra institución
    relation = relationOf(db, team, operator)
    assert relation.matriculaProfesional == "MP-123"
    revokeOperator(db, team, operator)
    db.expire_all()
    assert personnel.getProfile(db, team.moderator, team.id, relation.idInstitucionUsuario).acciones.puedeEliminarDatos is True

    personnel.erasePersonalData(db, team.moderator, team.id, relation.idInstitucionUsuario)

    kept = reload(db, InstitutionUser, relation.idInstitucionUsuario)
    assert (kept.nombreProfesionalHistorico, kept.apellidoProfesionalHistorico, kept.legajoInstitucional, kept.matriculaProfesional) == (None,) * 4
    assert kept.fechaMinimizacionDatos is not None
    assert (kept.rolInstitucion, kept.estadoRelacion, kept.fechaIncorporacion, kept.idUsuarioInvitador) == (
        "OPERADOR", "BAJA", relation.fechaIncorporacion, relation.idUsuarioInvitador)
    assert personName(kept, reload(db, User, operator.idUsuario)) is None
    row = next(i for i in personnel.listPersonnel(db, team.owner, team.id, estado="BAJA").items if i.idInstitucionUsuario == relation.idInstitucionUsuario)
    assert not row.nombre and row.correoElectronico is None and row.nombreCompleto == "Usuario eliminado" and row.datosEliminados is True
    assert personnel.listPersonnel(db, team.owner, team.id, busqueda="MP-123").total == 0  # ni el dato borrado ni la cuenta vigente lo encuentran
    assert personnel.listPersonnel(db, team.owner, team.id, busqueda=operator.correoElectronico).total == 0
    assert personnel.getProfile(db, team.moderator, team.id, relation.idInstitucionUsuario).acciones.puedeEliminarDatos is False
    event = audits(db, "ELIMINAR_DATOS_PERSONAL_HISTORICO")[-1]
    assert event.resultado == "EXITO" and "MP-123" not in (event.datosNuevos or "") and "Victoria" not in (event.datosNuevos or "")
    expectError("DATOS_YA_ELIMINADOS", personnel.erasePersonalData, db, team.moderator, team.id, relation.idInstitucionUsuario)


def test_no_se_eliminan_datos_de_quien_sigue_vinculado_ni_sin_permiso_ni_de_otra_institucion(db, mails, team):
    from app.services import personnel
    from tests.test_institution_patients import otherInstitution
    operator, moderator = team.operator, team.moderator
    operatorRelation, moderatorRelation = relationOf(db, team, operator), relationOf(db, team, moderator)
    expectError("PERSONA_VIGENTE", personnel.erasePersonalData, db, team.owner, team.id, operatorRelation.idInstitucionUsuario)
    assert reload(db, InstitutionUser, operatorRelation.idInstitucionUsuario).matriculaProfesional == "MP-123"
    revokeOperator(db, team, operator)
    expectError("INSTITUCION_NO_ENCONTRADA", personnel.erasePersonalData, db, operator, team.id, operatorRelation.idInstitucionUsuario)  # sin acceso
    otherOperator = addOperator(db, team)  # un operador activo consulta menos que el equipo
    otherUser = reload(db, User, otherOperator.idUsuarioInvitado)
    expectError("PERMISO_INSUFICIENTE", personnel.erasePersonalData, db, otherUser, team.id, operatorRelation.idInstitucionUsuario)
    # Los moderadores los gestiona solo el propietario: un moderador no elimina datos de otro moderador.
    secondModerator = institutional(db, "moderador2@example.com", "moderador2")
    invitation = institutions.invite(db, team.owner, team.id, "MODERADOR", secondModerator.correoElectronico)
    institutions.respondInvitation(db, secondModerator, invitation.idInstitucionUsuario, accept=True)
    institutions.revokeMember(db, team.owner, team.id, "MODERADOR", moderatorRelation.idInstitucionUsuario)
    expectError("PERMISO_INSUFICIENTE", personnel.erasePersonalData, db, secondModerator, team.id, moderatorRelation.idInstitucionUsuario)
    # El propietario no tiene permiso de baja sobre su propio rol: nunca se le eliminan los datos (ni existe baja para él).
    ownerRelation = relationOf(db, team, team.owner)
    expectError("MIEMBRO_NO_ENCONTRADO", personnel.erasePersonalData, db, team.owner, team.id, ownerRelation.idInstitucionUsuario)
    personnel.erasePersonalData(db, team.owner, team.id, moderatorRelation.idInstitucionUsuario)  # el propietario sí
    foreign, _, _ = otherInstitution(db)
    foreignOwner = db.scalar(select(User).where(User.correoElectronico == "otra-duenia@example.com"))
    expectError("MIEMBRO_NO_ENCONTRADO", personnel.erasePersonalData, db, foreignOwner, foreign.idInstitucion, operatorRelation.idInstitucionUsuario)
    assert reload(db, InstitutionUser, operatorRelation.idInstitucionUsuario).matriculaProfesional == "MP-123"


def test_la_api_elimina_los_datos_historicos_con_204_y_la_segunda_vez_responde_409(db, mails, team, api):
    operator = team.operator
    relation = relationOf(db, team, operator)
    revokeOperator(db, team, operator)
    url = f"/api/v1/institutions/{team.id}/personnel/{relation.idInstitucionUsuario}/personal-data"
    assert api(operator).delete(url).status_code == 404  # desvinculado: la institución ya no existe para él
    assert api(team.moderator).delete(url).status_code == 204
    again = api(team.moderator).delete(url)
    assert again.status_code == 409 and again.json()["codigo"] == "DATOS_YA_ELIMINADOS"


# --- API ------------------------------------------------------------------------------------------------------------------------------


def test_la_api_informa_el_periodo_de_gracia_y_las_consecuencias(db, mails, team, api):
    operator = team.operator
    assert api(operator).get("/api/v1/auth/me").json()["periodoGracia"] is None
    blocked = api(operator).get("/api/v1/auth/account-deletion/preview").json()
    assert blocked["puedeEliminar"] is False and blocked["mensajeBloqueo"].startswith("Tu cuenta está vinculada")
    revokeOperator(db, team, operator)
    me = api(operator).get("/api/v1/auth/me").json()
    assert me["periodoGracia"]["diasRestantes"] == 30 and me["periodoGracia"]["fechaVencimiento"]
    preview = api(operator).get("/api/v1/auth/account-deletion/preview").json()
    assert preview["puedeEliminar"] is True and preview["periodoGracia"]["diasRestantes"] == 30 and preview["datosEliminados"]


def test_el_listado_de_personal_no_identifica_a_la_persona_de_un_vinculo_minimizado(db, mails, team):
    from app.services import personnel
    operator = team.operator
    secondInstitution(db, operator, cuit="71111111", nombre="Centro Sur")  # la cuenta sigue activa en otra institución
    relation = relationOf(db, team, operator)
    revokeOperator(db, team, operator)
    db.execute(update(InstitutionUser).where(InstitutionUser.idInstitucionUsuario == relation.idInstitucionUsuario).values(
        fechaBaja=nowForDb() - timedelta(days=366 * 11)))
    db.commit()
    personnelRetention.minimizeExpired(db, 120)
    db.expire_all()
    page = personnel.listPersonnel(db, team.owner, team.id, estado="BAJA")
    row = next(item for item in page.items if item.idInstitucionUsuario == relation.idInstitucionUsuario)
    assert not row.nombre and not row.apellido and row.correoElectronico is None and row.nombreCompleto == "Usuario eliminado"
    assert row.rolInstitucion == "OPERADOR" and row.fechaBaja is not None and row.fechaIncorporacion is not None  # lo demás se conserva
    # Una institución que no es la dueña del vínculo no lo ve con su UUID.
    from tests.test_institution_patients import otherInstitution
    foreign, _, _ = otherInstitution(db)
    foreignOwner = db.scalar(select(User).where(User.correoElectronico == "otra-duenia@example.com"))
    expectError("MIEMBRO_NO_ENCONTRADO", personnel.getProfile, db, foreignOwner, foreign.idInstitucion, relation.idInstitucionUsuario)


def test_dry_run_informa_plazos_vigentes_vencidos_y_que_procesaria_sin_modificar_nada(db, mails, team):
    operator = team.operator
    legacy = institutional(db, "antigua@example.com", "antigua")  # cuenta anterior a la regla: sin vínculos y sin plazo
    revokeOperator(db, team, operator)
    report = accountLifecycle.dryRun(db)
    assert [a["idUsuario"] for a in report["plazoVigente"]] == [str(operator.idUsuario)] and report["plazoVigente"][0]["diasRestantes"] == 30
    assert report["plazoVencido"] == [] and report["seEliminarian"] == [] and report["seOmitirian"] == []
    assert [a["idUsuario"] for a in report["sinPlazoNoSeTocan"]] == [str(legacy.idUsuario)]
    forceExpiry(db, operator)
    mails.clear()
    report = accountLifecycle.dryRun(db)
    assert [a["idUsuario"] for a in report["seEliminarian"]] == [str(operator.idUsuario)] and report["plazoVigente"] == []
    assert reload(db, User, operator.idUsuario).estado == "ACTIVO" and not mails and audits(db, "ELIMINACION_AUTOMATICA_CUENTA") == []
    # La cuenta sin plazo nunca es candidata, aunque no tenga instituciones.
    assert str(legacy.idUsuario) not in json.dumps(report["seEliminarian"]) and reload(db, User, legacy.idUsuario).fechaVencimientoGracia is None


def test_un_vencimiento_adelantado_no_autoriza_a_eliminar_y_sin_plazo_nunca_se_elimina(db, mails, team):
    operator = team.operator
    revokeOperator(db, team, operator)
    # Vencimiento a solo 5 días del inicio (la restricción de la base lo admite): no se cumplieron los 30 días completos.
    db.execute(update(User).where(User.idUsuario == operator.idUsuario).values(
        fechaInicioGracia=nowForDb() - timedelta(days=6), fechaVencimientoGracia=nowForDb() - timedelta(days=1)))
    db.commit()
    assert accountLifecycle.deleteExpired(db, operator.idUsuario, nowForDb()) == (accountLifecycle.OMITIDA, "PLAZO_INVALIDO")
    assert accountLifecycle.dryRun(db)["seOmitirian"][0]["motivo"] == "PLAZO_INVALIDO"
    assert reload(db, User, operator.idUsuario).estado == "ACTIVO"
    # Sin inicio cargado tampoco es candidata.
    db.execute(update(User).where(User.idUsuario == operator.idUsuario).values(fechaInicioGracia=None, fechaVencimientoGracia=None))
    db.commit()
    assert accountLifecycle.candidates(db, nowForDb()) == [] and accountLifecycle.sweep(db)["revisadas"] == 0
    assert reload(db, User, operator.idUsuario).estado == "ACTIVO"


def test_la_minimizacion_esta_desactivada_por_defecto(engine):
    from app.core.config import getSettings
    assert getSettings().PERSONNEL_RETENTION_MONTHS == 0


# --- Plazo desde el alta de la cuenta y correo de bienvenida ---------------------------------------------------------------------------

WELCOME = "Bienvenido/a a GlucoLume"


def registerAndVerify(db, mails, **overrides):
    import re
    from tests.test_institutions import registration
    authService.registerLocal(db, registration(**overrides))
    token = re.search(r"verificar-correo\?token=([A-Za-z0-9_\-]+)", mails[0]["html"]).group(1)
    authService.verifyEmail(db, token)
    return db.scalar(select(User).where(User.correoElectronico == overrides.get("correoElectronico", "maria@example.com")))


def test_la_bienvenida_institucional_explica_las_opciones_y_la_fecha_exacta(db, mails):
    from app.emails.formatting import formatDateTime
    user = registerAndVerify(db, mails)
    assert user.estado == "ACTIVO" and user.fechaVencimientoGracia - user.fechaInicioGracia == timedelta(days=30)
    [welcome] = mailsWith(mails, WELCOME)  # un solo correo de bienvenida
    text = welcome["text"]
    assert formatDateTime(user.fechaVencimientoGracia) in text  # fecha exacta
    for phrase in ("propietario", "operador/a o moderador/a", "30 días corridos", "se eliminará automáticamente", "anonimizarán"):
        assert phrase in text, phrase
    assert mailsWith(mails, GRACE_SUBJECT) == []  # no se duplica con el aviso de plazo
    [event] = audits(db, "INICIAR_PERIODO_GRACIA")
    assert json.loads(event.datosNuevos)["origen"] == "ALTA_DE_CUENTA"
    # Crear la institución (quedar como propietario) cancela el plazo.
    newInstitution(db, user)
    assert reload(db, User, user.idUsuario).fechaVencimientoGracia is None and len(audits(db, "CANCELAR_PERIODO_GRACIA")) == 1


def test_la_bienvenida_no_muestra_un_vencimiento_inexistente_a_quien_ya_esta_incorporado(db, mails):
    from app.emails.eventTypes import EmailEventType
    from app.services import email as emailService
    owner = institutional(db, "ya@example.com", "yaesta")
    newInstitution(db, owner)
    assert accountGrace.startIfOrphaned(db, owner.idUsuario, nowForDb(), None, "ALTA_DE_CUENTA") is None  # tiene un vínculo activo
    context = accountGrace.welcomeContext(reload(db, User, owner.idUsuario))
    assert context["fechaVencimiento"] is None
    mails.clear()
    emailService.sendEmailEvent(EmailEventType.CUENTA_CREADA, owner.correoElectronico, {
        "nombre": "Ya", "apellido": "Está", "fechaCreacion": nowForDb(), "urlIngreso": emailService.frontendUrl("ingreso"), **context})
    text = mailsWith(mails, WELCOME)[-1]["text"]
    assert "30 días corridos" not in text and "eliminará automáticamente" not in text and "propietario" in text


def test_una_cuenta_pendiente_de_verificar_no_tiene_plazo_hasta_que_se_habilita(db, mails):
    from tests.test_institutions import registration
    authService.registerLocal(db, registration())
    user = db.scalar(select(User))
    assert user.estado == "PENDIENTE" and user.fechaVencimientoGracia is None and audits(db, "INICIAR_PERIODO_GRACIA") == []
    assert accountLifecycle.dryRun(db)["sinPlazoNoSeTocan"] == [] and accountLifecycle.legacyAccounts(db) == []  # no habilitada: fuera de la política
    assert mailsWith(mails, WELCOME) == []


def test_la_bienvenida_de_un_consumidor_no_habla_de_instituciones(db, mails):
    user = registerAndVerify(db, mails, tipoCuenta="CONSUMIDOR_FINAL", correoElectronico="consumidor@example.com", usuario="consumidor")
    assert user.fechaVencimientoGracia is None
    [welcome] = mailsWith(mails, WELCOME)
    assert "30 días" not in welcome["text"] and "institución" not in welcome["text"].lower()


@pytest.mark.parametrize(("intencion", "institucional"), [("institucion", True), ("usuario", False)])
def test_registro_con_google_inicia_el_plazo_solo_en_cuentas_institucionales(db, mails, monkeypatch, intencion, institucional):
    from app.core.config import getSettings
    from app.integrations.google.oauth import GoogleIdentity
    from tests.test_google_exchange import runCallback
    for key, value in (("GOOGLE_CLIENT_ID", "client-id"), ("GOOGLE_CLIENT_SECRET", "client-secret"), ("SESSION_SECRET", "s" * 40),
                       ("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/auth/google/callback")):
        monkeypatch.setenv(key, value)
    getSettings.cache_clear()
    identity = GoogleIdentity(subject=f"g-{intencion}", email=f"{intencion}@example.com", emailVerified=True, givenName="Ana", familyName="Pérez")

    async def fetchIdentity(request):
        return identity

    runCallback(db, monkeypatch, fetchIdentity, {"glucolume_registro": intencion, "glucolume_politica": True})
    user = db.scalar(select(User).where(User.correoElectronico == identity.email))
    assert (user.fechaVencimientoGracia is not None) is institucional
    [welcome] = mailsWith(mails, WELCOME)
    assert ("30 días corridos" in welcome["text"]) is institucional


def test_una_cuenta_invitada_empieza_el_plazo_al_activarse_y_aceptar_lo_cancela(db, mails, team):
    from app.services import accountActivation
    from tests.test_institution_staff import NEW_PASSWORD, addNewModerator
    member, token = addNewModerator(db, team, mails)
    user = db.scalar(select(User).where(User.correoElectronico == "nueva@example.com"))
    assert user.estado == "PENDIENTE" and user.fechaVencimientoGracia is None  # sin activar: todavía no hay plazo
    mails.clear()
    accountActivation.completeActivation(db, token, "luciasosa", NEW_PASSWORD, aceptaPolitica=True)
    user = reload(db, User, user.idUsuario)
    assert user.estado == "ACTIVO" and user.fechaVencimientoGracia - user.fechaInicioGracia == timedelta(days=30)
    assert json.loads(audits(db, "INICIAR_PERIODO_GRACIA")[-1].datosNuevos)["origen"] == "ACTIVACION_DE_CUENTA"
    assert mailsWith(mails, WELCOME) == []  # esta persona ya recibió su invitación; no se le manda otra bienvenida
    institutions.respondInvitation(db, user, member.idInstitucionUsuario, accept=True)
    assert reload(db, User, user.idUsuario).fechaVencimientoGracia is None


# --- Regularización de cuentas anteriores a la política ------------------------------------------------------------------------------------


def makeUserPending(db):
    user = institutional(db, "pendiente-act@example.com", "pendienteact")
    user.estado = "PENDIENTE"
    db.commit()
    return user


def test_regularizacion_muestra_el_cambio_exacto_y_solo_aplica_con_apply(db, mails, team):
    legacy = institutional(db, "antigua@example.com", "antigua")           # activa, sin instituciones y sin plazo
    withBond = team.operator                                               # tiene vínculo activo
    pending = makeUserPending(db)                                          # pendiente de activar: no se toca
    consumer = institutional(db, "otra@example.com", "otraa")
    consumer.tipoCuenta = "CONSUMIDOR_FINAL"
    db.commit()
    now = nowForDb()
    plan = accountLifecycle.regularize(db, now)
    assert plan == [{"idUsuario": str(legacy.idUsuario), "correo": plan[0]["correo"], "fechaInicioGracia": now.isoformat(),
                     "fechaVencimientoGracia": (now + timedelta(days=30)).isoformat()}]
    assert reload(db, User, legacy.idUsuario).fechaVencimientoGracia is None and not mails  # solo simulación
    applied = accountLifecycle.regularize(db, now, apply=True)
    assert applied[0]["aplicado"] is True
    row = reload(db, User, legacy.idUsuario)
    assert (row.fechaInicioGracia, row.fechaVencimientoGracia) == (now, now + timedelta(days=30))  # 30 días desde hoy, nada retroactivo
    [mail] = mailsWith(mails, GRACE_SUBJECT)
    assert mail["to"] == "antigua@example.com"
    for phrase in ("Crear tu propia institución", "Incorporarte a una institución existente", "Eliminar tu cuenta voluntariamente"):
        assert phrase in mail["text"], phrase
    assert json.loads(audits(db, "INICIAR_PERIODO_GRACIA")[-1].datosNuevos)["origen"] == "REGULARIZACION_CUENTA_ANTERIOR"
    for untouched in (withBond, pending, consumer):
        assert reload(db, User, untouched.idUsuario).fechaVencimientoGracia is None
    assert accountLifecycle.regularize(db, now, apply=True) == []  # idempotente
    assert accountLifecycle.sweep(db)["revisadas"] == 0 and reload(db, User, legacy.idUsuario).estado == "ACTIVO"  # nada vence todavía


# --- Invitación cancelada con enlace de activación vigente / depuración de pendientes sin salida --------------------------------------------------


def invitedModerator(db, team, mails, email="nueva@example.com"):
    from tests.test_institution_staff import addNewModerator
    member, token = addNewModerator(db, team, mails, email)
    return member, token, db.scalar(select(User).where(User.correoElectronico == email))


def expireLinks(db, user):
    from app.models.accountToken import AccountToken
    db.execute(update(AccountToken).where(AccountToken.idUsuario == user.idUsuario).values(fechaCreacion=nowForDb() - timedelta(days=8), fechaExpiracion=nowForDb() - timedelta(hours=1)))
    db.commit()


def test_un_enlace_vigente_no_activa_la_cuenta_si_la_invitacion_fue_cancelada(db, mails, team):
    from app.services import accountActivation
    from tests.test_institution_staff import NEW_PASSWORD
    member, token, user = invitedModerator(db, team, mails)
    institutions.revokeMember(db, team.owner, team.id, "MODERADOR", member.idInstitucionUsuario)  # la institución cancela la invitación
    for call in (lambda: accountActivation.checkActivation(db, token),
                 lambda: accountActivation.completeActivation(db, token, "luciasosa", NEW_PASSWORD, aceptaPolitica=True)):
        with pytest.raises(AuthError) as error:
            call()
        assert error.value.code == "INVITACION_NO_VIGENTE"
    row = reload(db, User, user.idUsuario)
    assert row.estado == "PENDIENTE" and row.fechaVencimientoGracia is None  # sigue sin habilitar: ni sesión ni plazo
    assert db.scalar(select(func.count()).select_from(LocalCredential).where(LocalCredential.idUsuario == user.idUsuario)) == 0
    assert lastRelation(db, team, user).estadoRelacion == "BAJA" and lastRelation(db, team, user).fechaIncorporacion is None  # nunca se incorporó
    expectError("INVITACION_NO_ENCONTRADA", institutions.respondInvitation, db, row, member.idInstitucionUsuario, accept=True)


def test_una_invitacion_vencida_tampoco_permite_activar_y_una_nueva_invitacion_si(db, mails, team):
    from app.services import accountActivation
    from tests.test_institution_staff import NEW_PASSWORD
    member, token, user = invitedModerator(db, team, mails)
    db.execute(update(InstitutionUser).where(InstitutionUser.idInstitucionUsuario == member.idInstitucionUsuario).values(
        fechaInvitacion=nowForDb() - timedelta(days=8)))
    db.commit()
    with pytest.raises(AuthError) as error:
        accountActivation.completeActivation(db, token, "luciasosa", NEW_PASSWORD, aceptaPolitica=True)
    assert error.value.code == "INVITACION_NO_VIGENTE"
    # La institución vuelve a invitar a la misma persona: recibe un enlace nuevo y esta vez se puede activar.
    institutions.invite(db, team.owner, team.id, "MODERADOR", "nueva@example.com", nombre="lucía", apellido="sosa")
    from tests.test_institution_staff import tokenFrom
    session = accountActivation.completeActivation(db, tokenFrom(mails[-1]), "luciasosa", NEW_PASSWORD, aceptaPolitica=True)
    assert session.estado == "AUTENTICADO" and reload(db, User, user.idUsuario).estado == "ACTIVO"


def test_google_tampoco_activa_una_cuenta_cuya_invitacion_fue_cancelada(db, mails, team, monkeypatch):
    from app.core.config import getSettings
    from app.integrations.google.oauth import GoogleIdentity
    from tests.test_google_exchange import runCallback
    member, token, user = invitedModerator(db, team, mails)
    institutions.revokeMember(db, team.owner, team.id, "MODERADOR", member.idInstitucionUsuario)
    for key, value in (("GOOGLE_CLIENT_ID", "client-id"), ("GOOGLE_CLIENT_SECRET", "client-secret"), ("SESSION_SECRET", "s" * 40),
                       ("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/auth/google/callback")):
        monkeypatch.setenv(key, value)
    getSettings.cache_clear()
    identity = GoogleIdentity(subject="g-cancelada", email="nueva@example.com", emailVerified=True, givenName="Lucía", familyName="Sosa")

    async def fetchIdentity(request):
        return identity

    fragment = runCallback(db, monkeypatch, fetchIdentity, {"glucolume_registro": "institucion", "glucolume_politica": True})
    assert not fragment.startswith("code=")  # no se entrega ninguna sesión: no se vincula ni se activa
    assert reload(db, User, user.idUsuario).estado == "PENDIENTE"


def test_las_pendientes_sin_salida_se_depuran_y_las_validas_no_se_tocan(db, mails, team):
    from app.models.accountToken import AccountToken
    from app.services import pendingAccounts
    # 1. Sin salida: invitación cancelada y enlace vencido.
    memberDead, _, dead = invitedModerator(db, team, mails, "muerta@example.com")
    institutions.revokeMember(db, team.owner, team.id, "MODERADOR", memberDead.idInstitucionUsuario)
    expireLinks(db, dead)
    # 2. Invitación cancelada pero enlace todavía vigente: se espera a que venza (podrían volver a invitarla).
    memberWait, _, waiting = invitedModerator(db, team, mails, "espera@example.com")
    institutions.revokeMember(db, team.owner, team.id, "MODERADOR", memberWait.idInstitucionUsuario)
    # 3. Invitación vigente: no se toca.
    _, _, live = invitedModerator(db, team, mails, "vigente@example.com")
    # 4. Cuenta local sin verificar (la gobierna otra regla) y 5. cuenta ya habilitada sin vínculos.
    unverified = institutional(db, "sinverificar@example.com", "sinverificar")
    unverified.estado = "PENDIENTE"
    enabled = institutional(db, "habilitada@example.com", "habilitada")
    db.commit()

    now = nowForDb()
    assert pendingAccounts.candidates(db, now) == [dead.idUsuario]
    assert [item["idUsuario"] for item in accountLifecycle.dryRun(db)["pendientesSinSalidaSeDepurarian"]] == [str(dead.idUsuario)]
    assert reload(db, User, dead.idUsuario).estado == "PENDIENTE"  # el dry-run no modifica
    assert pendingAccounts.purgeDead(db, now) == 1 and pendingAccounts.purgeDead(db, now) == 0  # idempotente
    row = reload(db, User, dead.idUsuario)
    assert row.estado == "ELIMINADO" and (row.nombre, row.apellido, row.correoElectronico, row.usuario) == (None,) * 4
    relation = lastRelation(db, team, dead)
    assert relation.estadoRelacion == "BAJA" and relation.fechaIncorporacion is None  # la relación histórica se conserva
    [event] = audits(db, "DEPURAR_CUENTA_INVITADA_VENCIDA")
    assert event.idRegistro == dead.idUsuario and "muerta@example.com" not in event.datosNuevos
    for kept, state in ((waiting, "PENDIENTE"), (live, "PENDIENTE"), (unverified, "PENDIENTE"), (enabled, "ACTIVO")):
        assert reload(db, User, kept.idUsuario).estado == state
    # El correo queda libre: la misma persona puede registrarse por su cuenta.
    from tests.test_institutions import registration
    assert authService.registerLocal(db, registration(correoElectronico="muerta@example.com", usuario="muertaa")).estado == "PENDIENTE"
    # Al vencer el enlace de la que esperaba, también se depura; la vigente sigue intacta.
    expireLinks(db, waiting)
    assert pendingAccounts.purgeDead(db, nowForDb()) == 1 and reload(db, User, waiting.idUsuario).estado == "ELIMINADO"
    assert reload(db, User, live.idUsuario).estado == "PENDIENTE" and db.scalar(select(func.count()).select_from(AccountToken).where(AccountToken.idUsuario == live.idUsuario)) == 1


def test_la_regularizacion_acotada_a_una_cuenta_no_toca_a_las_demas(db, mails):
    first = institutional(db, "primera@example.com", "primera")
    second = institutional(db, "segunda@example.com", "segunda")
    now = nowForDb()
    assert [item["idUsuario"] for item in accountLifecycle.regularize(db, now, only=first.idUsuario)] == [str(first.idUsuario)]
    assert [item["aplicado"] for item in accountLifecycle.regularize(db, now, apply=True, only=first.idUsuario)] == [True]
    assert reload(db, User, first.idUsuario).fechaVencimientoGracia == now + timedelta(days=30)
    assert reload(db, User, second.idUsuario).fechaVencimientoGracia is None  # la otra cuenta sin plazo no se modificó
    assert len(mailsWith(mails, GRACE_SUBJECT)) == 1  # un único correo
    assert accountLifecycle.regularize(db, now, apply=True, only=first.idUsuario) == []  # idempotente: ya tiene plazo
