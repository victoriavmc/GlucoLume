# InstitutionReassignments - Gestión de los pacientes pendientes de reasignación (propietario y moderador)
#
# Los pacientes activos de un operador desvinculado quedan pendientes (services/reassignments.py). Acá el propietario o un moderador:
#   - consulta quiénes son, de qué operador y desde cuándo;
#   - elige UN operador destinatario y reasigna uno o varios pacientes juntos, con un motivo opcional.
# El sistema nunca elige al destinatario. El destinatario debe ser un OPERADOR ACTIVO de la MISMA institución (nunca de baja, pendiente,
# de otra institución, moderador ni propietario): lo valida el backend con el vínculo, no el selector del navegador.
# El operador NO ve esta sección ni puede reasignar: solo pide transferencias entre operadores (services/profileTransfers.py).
#
# Reasignar cambia únicamente el responsable VIGENTE del paciente. La autoría de las mediciones anteriores se conserva (Auditoria
# INICIAR_MEDICION + vínculo del operador que las hizo) y el nuevo operador solo opera lo que sus reglas de acceso le permiten.
# El lote es una sola transacción; una tarea que otra persona ya resolvió se informa como YA_RESUELTA y no frena a las demás.

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.core.exceptions import AuthError
from app.models.institutionUser import InstitutionUser
from app.models.measurementProfile import MeasurementProfile
from app.models.patientReassignment import PatientReassignment
from app.models.user import User
from app.schemas.reassignment import (
    ReassignmentAssignRequest,
    ReassignmentAssignResult,
    ReassignmentGroup,
    ReassignmentItem,
    ReassignmentOutcome,
    ReassignmentOverview,
    ReassignmentPage,
    ReassignmentRegularizeRequest,
    ReassignmentRegularizeResult,
    ReassignmentUnregistered,
)
from app.services import institution as institutions
from app.services import institutionPatients as patients
from app.services import patientAccess
from app.services import reassignments
from app.services.audit import personName, registerEvent
from app.utils.timeZone import nowForDb

MAX_PAGE_SIZE = 100


def _requireManager(db: Session, actor: User, idInstitucion: uuid.UUID) -> institutions.Membership:
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_GESTIONAR_PACIENTES)
    if membership.role == institutions.ROL_OPERADOR:
        registerEvent(db, "PERMISO", "CONSULTAR_REASIGNACIONES_PACIENTES", False, actor.idUsuario, "Institucion", idInstitucion,
                      observacion="Motivo: PERMISO_INSUFICIENTE")
        db.commit()
        raise AuthError("PERMISO_INSUFICIENTE", "Solo el propietario y los moderadores gestionan la reasignación de pacientes.")
    return membership


def overview(db: Session, actor: User, idInstitucion: uuid.UUID) -> ReassignmentOverview:
    _requireManager(db, actor, idInstitucion)
    counts: dict[uuid.UUID, dict[str, int]] = {}
    previousOf = aliased(InstitutionUser)
    for previous, state, total in db.execute(
            select(PatientReassignment.idOperadorAnterior, PatientReassignment.estado, func.count())
            .join(previousOf, previousOf.idInstitucionUsuario == PatientReassignment.idOperadorAnterior)
            .where(PatientReassignment.idInstitucion == idInstitucion, patientAccess.currentPeriod(previousOf, idInstitucion))
            .group_by(PatientReassignment.idOperadorAnterior, PatientReassignment.estado)):
        counts.setdefault(previous, {})[state] = total
    people = {}
    if counts:
        people = {rel.idInstitucionUsuario: (rel, user) for rel, user in db.execute(
            select(InstitutionUser, User).outerjoin(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
            .where(InstitutionUser.idInstitucionUsuario.in_(counts)))}
    groups = []
    for previous, byState in counts.items():
        relation, user = people.get(previous, (None, None))
        pending = byState.get(reassignments.PENDIENTE, 0)
        groups.append(ReassignmentGroup(
            idOperadorAnterior=previous, operadorAnterior=personName(relation, user),
            fechaDesvinculacion=relation.fechaBaja if relation else None, pendientes=pending,
            completadas=byState.get(reassignments.COMPLETADA, 0), canceladas=byState.get(reassignments.CANCELADA, 0),
            estado="PENDIENTE" if pending else "RESUELTA"))
    # Primero lo que falta resolver; dentro de cada grupo, la baja más reciente arriba.
    groups.sort(key=lambda g: (g.estado != "PENDIENTE", -(g.fechaDesvinculacion.timestamp() if g.fechaDesvinculacion else 0)))
    available = db.scalar(select(func.count()).select_from(InstitutionUser).where(
        InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.rolInstitucion == institutions.ROL_OPERADOR,
        InstitutionUser.estadoRelacion == institutions.RELACION_ACTIVO)) or 0
    orphans = _unregistered(db, idInstitucion)
    return ReassignmentOverview(pendientes=sum(g.pendientes for g in groups), operadoresDisponibles=available, grupos=groups[:50],
                                sinRegularizar=sum(o.pacientes for o in orphans), gruposSinRegularizar=orphans)


def _unregistered(db: Session, idInstitucion: uuid.UUID) -> list[ReassignmentUnregistered]:
    """Pacientes activos cuyo responsable ya no es un operador activo y que no tienen tarea de reasignación pendiente."""
    responsible = aliased(InstitutionUser)
    hasTask = select(PatientReassignment.idReasignacionPaciente).where(
        PatientReassignment.idPerfilMedicion == MeasurementProfile.idPerfilMedicion, PatientReassignment.estado == reassignments.PENDIENTE).exists()
    rows = db.execute(
        select(responsible, User, func.count())
        .select_from(MeasurementProfile)
        .join(responsible, responsible.idInstitucionUsuario == MeasurementProfile.idInstitucionUsuarioResponsable)
        .outerjoin(User, User.idUsuario == responsible.idUsuarioInvitado)
        .where(MeasurementProfile.tipoPerfil == "INSTITUCIONAL", MeasurementProfile.fechaExpiracionDatosPersonales.is_(None),
               MeasurementProfile.fechaDepuracionDatosPersonales.is_(None),
               responsible.idInstitucion == idInstitucion, responsible.rolInstitucion == institutions.ROL_OPERADOR,
               responsible.estadoRelacion != institutions.RELACION_ACTIVO, patientAccess.currentPeriod(responsible, idInstitucion),
               ~hasTask)
        .group_by(responsible, User)).all()
    result = [ReassignmentUnregistered(idOperadorAnterior=rel.idInstitucionUsuario, operadorAnterior=personName(rel, user),
                                       fechaDesvinculacion=rel.fechaBaja, pacientes=total) for rel, user, total in rows]
    result.sort(key=lambda o: -(o.fechaDesvinculacion.timestamp() if o.fechaDesvinculacion else 0))
    return result


def regularize(db: Session, actor: User, idInstitucion: uuid.UUID, data: ReassignmentRegularizeRequest) -> ReassignmentRegularizeResult:
    """Regulariza UN operador ya desvinculado que figura como responsable de pacientes: crea sus tareas de reasignación pendientes (una por
    paciente, idempotente) para que se resuelvan con el flujo habitual. No elige destinatarios ni toca el responsable de ningún paciente."""
    _requireManager(db, actor, idInstitucion)
    relation = db.get(InstitutionUser, data.idOperadorAnterior)
    if (relation is None or relation.idInstitucion != idInstitucion or relation.rolInstitucion != institutions.ROL_OPERADOR
            or relation.estadoRelacion == institutions.RELACION_ACTIVO):
        raise AuthError("MIEMBRO_NO_ENCONTRADO", "No encontramos un operador desvinculado con pacientes sin responsable en esta institución.")
    now = nowForDb()
    created = reassignments.openForOperator(db, relation, actor.idUsuario, now)
    registerEvent(db, "CRUD", "REGULARIZAR_REASIGNACIONES", True, actor.idUsuario, "InstitucionUsuario", relation.idInstitucionUsuario,
                  datosNuevos={"pacientesPendientes": created})
    db.commit()
    return ReassignmentRegularizeResult(pacientesPendientes=created)


def listItems(db: Session, actor: User, idInstitucion: uuid.UUID, estado: str | None = reassignments.PENDIENTE,
              idOperadorAnterior: uuid.UUID | None = None, page: int = 1, pageSize: int = 50) -> ReassignmentPage:
    _requireManager(db, actor, idInstitucion)
    pageSize = max(1, min(pageSize, MAX_PAGE_SIZE))
    previousRel, previousUser = aliased(InstitutionUser), aliased(User)
    newRel, newUser = aliased(InstitutionUser), aliased(User)
    resolver = aliased(User)
    filters = [PatientReassignment.idInstitucion == idInstitucion,
               patientAccess.currentPeriod(previousRel, idInstitucion)]  # las tareas de un período anterior a la reapertura no se muestran
    if estado:
        filters.append(PatientReassignment.estado == estado)
    if idOperadorAnterior is not None:
        filters.append(PatientReassignment.idOperadorAnterior == idOperadorAnterior)
    total = db.scalar(select(func.count()).select_from(PatientReassignment).join(
        previousRel, previousRel.idInstitucionUsuario == PatientReassignment.idOperadorAnterior).where(*filters)) or 0
    rows = db.execute(
        select(PatientReassignment, MeasurementProfile, previousRel, previousUser, newRel, newUser, resolver)
        .join(MeasurementProfile, MeasurementProfile.idPerfilMedicion == PatientReassignment.idPerfilMedicion)
        .join(previousRel, previousRel.idInstitucionUsuario == PatientReassignment.idOperadorAnterior)
        .outerjoin(previousUser, previousUser.idUsuario == previousRel.idUsuarioInvitado)
        .outerjoin(newRel, newRel.idInstitucionUsuario == PatientReassignment.idOperadorNuevo)
        .outerjoin(newUser, newUser.idUsuario == newRel.idUsuarioInvitado)
        .outerjoin(resolver, resolver.idUsuario == PatientReassignment.idUsuarioResolutor)
        .where(*filters)
        .order_by(PatientReassignment.fechaCreacion.desc(), MeasurementProfile.identificadorPseudonimo)
        .offset((max(page, 1) - 1) * pageSize).limit(pageSize)
    ).all()
    items = [
        ReassignmentItem(
            idReasignacionPaciente=task.idReasignacionPaciente, idPerfilMedicion=task.idPerfilMedicion,
            identificadorPseudonimo=profile.identificadorPseudonimo, nombre=profile.nombre, apellido=profile.apellido,
            idOperadorAnterior=task.idOperadorAnterior, operadorAnterior=personName(prevRel, prevUser),
            estado=task.estado, resultado=task.resultado, fechaCreacion=task.fechaCreacion, fechaResolucion=task.fechaResolucion,
            idOperadorNuevo=task.idOperadorNuevo, operadorNuevo=personName(nRel, nUser) if nRel is not None else None,
            resueltoPor=personName(None, resolverUser) if resolverUser is not None else None, observacion=task.observacion)
        for task, profile, prevRel, prevUser, nRel, nUser, resolverUser in rows
    ]
    return ReassignmentPage(items=items, total=total)


def assign(db: Session, actor: User, idInstitucion: uuid.UUID, data: ReassignmentAssignRequest) -> ReassignmentAssignResult:
    membership = _requireManager(db, actor, idInstitucion)
    # Destinatario: operador ACTIVO de esta institución. Se valida antes de tocar nada.
    target = patients._activeOperator(db, idInstitucion, data.idOperadorNuevo)
    ids = list(dict.fromkeys(data.idsReasignacion))
    tasks = {task.idReasignacionPaciente: task for task in db.scalars(
        select(PatientReassignment).where(PatientReassignment.idReasignacionPaciente.in_(ids),
                                          PatientReassignment.idInstitucion == idInstitucion))}
    outcomes: list[ReassignmentOutcome] = []
    done: list[tuple[MeasurementProfile, uuid.UUID, datetime]] = []
    now = nowForDb()
    for taskId in ids:
        task = tasks.get(taskId)
        if task is None:
            outcomes.append(ReassignmentOutcome(idReasignacionPaciente=taskId, resultado="NO_ENCONTRADA"))
            continue
        db.refresh(task)
        if task.estado != reassignments.PENDIENTE:
            outcomes.append(ReassignmentOutcome(idReasignacionPaciente=taskId, resultado="YA_RESUELTA"))
            continue
        profile = db.get(MeasurementProfile, task.idPerfilMedicion)
        if profile is None or patients.patientState(profile) != patients.PACIENTE_ACTIVO or profile.fechaDepuracionDatosPersonales is not None:
            reassignments.cancelForProfile(db, task.idPerfilMedicion, reassignments.RESULTADO_PACIENTE_BAJA, now, actor.idUsuario)
            outcomes.append(ReassignmentOutcome(idReasignacionPaciente=taskId, resultado="PACIENTE_DADO_DE_BAJA"))
            continue
        changed = patients.applyAssignment(db, actor, profile, target, data.observacion)
        if changed is None:  # el paciente ya estaba a cargo de ese operador: la tarea se completa igual
            reassignments.resolveForProfile(db, profile.idPerfilMedicion, target, actor.idUsuario, data.observacion, now)
            outcomes.append(ReassignmentOutcome(idReasignacionPaciente=taskId, resultado="REASIGNADO"))
            continue
        done.append((profile, *changed))
        outcomes.append(ReassignmentOutcome(idReasignacionPaciente=taskId, resultado="REASIGNADO"))
    if done:
        db.commit()
        for profile, previous, moment in done:
            patients.notifyAssignment(db, actor, membership.institution, profile, target, previous, moment)
    else:
        db.commit()  # confirma las tareas canceladas por baja del paciente, si las hubo
    return ReassignmentAssignResult(reasignados=sum(1 for o in outcomes if o.resultado == "REASIGNADO"), resultados=outcomes)
