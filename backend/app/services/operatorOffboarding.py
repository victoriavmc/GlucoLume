# OperatorOffboarding - Desvincular a un operador reasignando antes a sus pacientes (propietario y moderador)
#
# Un operador con pacientes a su cargo NO puede desvincularse: primero se reasignan. La regla vive en institution.revokeMember (cualquier ruta
# de baja la aplica); este módulo es el camino que la cumple:
#   plan()      consulta quiénes son sus pacientes, qué operadores activos pueden recibirlos y si algo lo impide;
#   offboard()  reasigna TODOS sus pacientes y lo desvincula en UNA transacción: o queda todo hecho o no cambia nada.
#
# El destinatario lo elige siempre quien gestiona (nunca el sistema) y debe ser un OPERADOR ACTIVO de la misma institución. Un paciente con una
# transferencia pendiente de aceptación sigue a cargo del operador hasta que esa solicitud se resuelva: no se reasigna por encima de ella y
# mientras exista no se puede desvincular. Reasignar cambia solo el responsable vigente: la autoría de las mediciones anteriores no se toca.

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.measurementProfile import MeasurementProfile
from app.models.profileTransfer import ProfileTransfer
from app.models.user import User
from app.schemas.offboarding import (
    OffboardDestination,
    OffboardPatient,
    OffboardPlan,
    OffboardRequest,
    OffboardResult,
    OffboardTarget,
)
from app.services import institution as institutions
from app.services import institutionPatients as patients
from app.services import reassignments
from app.services.audit import personName, registerEvent

DEFAULT_NOTE = "Reasignación previa a la desvinculación del operador anterior."


def _operator(db: Session, actor: User, idInstitucion: uuid.UUID,
              idInstitucionUsuario: uuid.UUID) -> tuple[institutions.Membership, InstitutionUser]:
    membership = institutions.requireMembership(db, actor, idInstitucion)
    if not membership.can(institutions.P_ADMINISTRAR_OPERADORES):
        registerEvent(db, "PERMISO", "CONSULTAR_DESVINCULACION_OPERADOR", False, actor.idUsuario, "Institucion", idInstitucion,
                      observacion="Motivo: PERMISO_INSUFICIENTE")
        db.commit()
        raise AuthError("PERMISO_INSUFICIENTE", "Tu rol en esta institución no permite realizar esta operación.")
    relation = db.get(InstitutionUser, idInstitucionUsuario)
    if (relation is None or relation.idInstitucion != idInstitucion or relation.rolInstitucion != institutions.ROL_OPERADOR
            or relation.estadoRelacion != institutions.RELACION_ACTIVO or relation.idUsuarioInvitado == actor.idUsuario):
        raise AuthError("MIEMBRO_NO_ENCONTRADO", "No encontramos ese integrante en la institución.")
    return membership, relation


def _patientsOf(relation: InstitutionUser):
    return (select(MeasurementProfile)
            .where(MeasurementProfile.idPerfilMedicion.in_(reassignments.activeProfilesOf(relation.idInstitucionUsuario)))
            .order_by(MeasurementProfile.apellido, MeasurementProfile.nombre, MeasurementProfile.identificadorPseudonimo))


def _pendingTransfers(db: Session, profileIds) -> set[uuid.UUID]:
    if not profileIds:
        return set()
    return set(db.scalars(select(ProfileTransfer.idPerfilMedicion).where(
        ProfileTransfer.idPerfilMedicion.in_(list(profileIds)), ProfileTransfer.estado == institutions.TRANSFERENCIA_PENDIENTE)))


def _targets(db: Session, idInstitucion: uuid.UUID, excluding: uuid.UUID) -> list[OffboardTarget]:
    load = dict(db.execute(
        select(MeasurementProfile.idInstitucionUsuarioResponsable, func.count()).where(
            MeasurementProfile.tipoPerfil == "INSTITUCIONAL", MeasurementProfile.fechaExpiracionDatosPersonales.is_(None),
            MeasurementProfile.fechaDepuracionDatosPersonales.is_(None),
            MeasurementProfile.idInstitucionUsuarioResponsable.in_(
                select(InstitutionUser.idInstitucionUsuario).where(InstitutionUser.idInstitucion == idInstitucion)))
        .group_by(MeasurementProfile.idInstitucionUsuarioResponsable)).all())
    rows = db.execute(
        select(InstitutionUser, User).outerjoin(User, User.idUsuario == InstitutionUser.idUsuarioInvitado).where(
            InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.rolInstitucion == institutions.ROL_OPERADOR,
            InstitutionUser.estadoRelacion == institutions.RELACION_ACTIVO, InstitutionUser.idInstitucionUsuario != excluding)).all()
    result = [OffboardTarget(idInstitucionUsuario=rel.idInstitucionUsuario, operador=personName(rel, user),
                             pacientesActuales=load.get(rel.idInstitucionUsuario, 0)) for rel, user in rows]
    result.sort(key=lambda t: ((t.operador or "").casefold(), str(t.idInstitucionUsuario)))
    return result


def plan(db: Session, actor: User, idInstitucion: uuid.UUID, idInstitucionUsuario: uuid.UUID) -> OffboardPlan:
    """Qué hay que resolver antes de desvincular al operador. Solo lectura."""
    _, relation = _operator(db, actor, idInstitucion, idInstitucionUsuario)
    profiles = list(db.scalars(_patientsOf(relation)))
    inTransfer = _pendingTransfers(db, [p.idPerfilMedicion for p in profiles])
    targets = _targets(db, idInstitucion, relation.idInstitucionUsuario)
    blocked = None
    if profiles and inTransfer:
        blocked = "TRANSFERENCIAS_PENDIENTES"
    elif profiles and not targets:
        blocked = "SIN_OPERADOR_DISPONIBLE"
    return OffboardPlan(
        idInstitucionUsuario=relation.idInstitucionUsuario, operador=personName(relation, db.get(User, relation.idUsuarioInvitado)),
        cantidadPacientes=len(profiles), transferenciasPendientes=len(inTransfer),
        pacientes=[OffboardPatient(idPerfilMedicion=p.idPerfilMedicion, identificadorPseudonimo=p.identificadorPseudonimo, nombre=p.nombre,
                                   apellido=p.apellido, transferenciaPendiente=p.idPerfilMedicion in inTransfer) for p in profiles],
        destinos=targets, bloqueo=blocked)


def offboard(db: Session, actor: User, idInstitucion: uuid.UUID, idInstitucionUsuario: uuid.UUID, data: OffboardRequest) -> OffboardResult:
    """Reasigna los pacientes del operador y lo desvincula en una sola transacción (institution.revokeMember la confirma al final)."""
    applied: list[tuple[MeasurementProfile, InstitutionUser, uuid.UUID, datetime]] = []
    names: dict[uuid.UUID, str | None] = {}

    def reassign(session: Session, source: InstitutionUser, now: datetime) -> None:
        # Con el vínculo del operador ya bloqueado: lo que se lea acá es lo que se desvincula.
        profiles = {p.idPerfilMedicion: p for p in session.execute(
            _patientsOf(source).with_hint(MeasurementProfile, "WITH (UPDLOCK, ROWLOCK)", "mssql").with_for_update()
            .execution_options(populate_existing=True)).scalars()}
        requested = [a.idPerfilMedicion for a in data.asignaciones]
        if len(set(requested)) != len(requested):
            raise AuthError("REASIGNACION_DESACTUALIZADA", "La reasignación repite pacientes. Actualizá la pantalla e intentá de nuevo.")
        if profiles and _pendingTransfers(session, profiles):
            raise AuthError("PACIENTE_EN_TRANSFERENCIA",
                            "Hay pacientes con una transferencia pendiente de aceptación: hasta que se resuelva siguen a cargo de este "
                            "operador. Esperá la respuesta del destinatario o pedí que se cancele la solicitud.")
        if profiles and not _targets(session, idInstitucion, source.idInstitucionUsuario):
            raise AuthError("SIN_OPERADOR_DISPONIBLE",
                            "No hay otro operador habilitado que pueda recibir a los pacientes. Primero incorporá o habilitá un responsable.")
        if set(requested) - set(profiles):
            raise AuthError("REASIGNACION_DESACTUALIZADA",
                            "Los pacientes del operador cambiaron mientras reasignabas. Actualizá la pantalla e intentá de nuevo.")
        if set(profiles) - set(requested):
            raise AuthError("REASIGNACION_INCOMPLETA", "Faltan pacientes por reasignar: todos deben tener un nuevo responsable.")
        targets = {}
        for targetId in sorted({a.idOperadorNuevo for a in data.asignaciones}, key=str):  # orden fijo: sin bloqueos cruzados
            if targetId == source.idInstitucionUsuario:
                raise AuthError("OPERADOR_NO_DISPONIBLE", "El nuevo responsable no puede ser el operador que se desvincula.")
            targets[targetId] = patients._activeOperator(session, idInstitucion, targetId)
        for assignment in data.asignaciones:
            target = targets[assignment.idOperadorNuevo]
            profile = profiles[assignment.idPerfilMedicion]
            changed = patients.applyAssignment(session, actor, profile, target, data.observacion or DEFAULT_NOTE)
            if changed is not None:
                applied.append((profile, target, *changed))
        for target in targets.values():
            names[target.idInstitucionUsuario] = personName(target, session.get(User, target.idUsuarioInvitado))
        if applied:
            registerEvent(session, "CRUD", "REASIGNAR_PACIENTES_DESVINCULACION", True, actor.idUsuario, "InstitucionUsuario",
                          source.idInstitucionUsuario,
                          datosNuevos={"pacientesReasignados": len(applied), "operadoresDestino": len(targets)})

    institutions.revokeMember(db, actor, idInstitucion, institutions.ROL_OPERADOR, idInstitucionUsuario, prepare=reassign)

    # Ya confirmado (reasignación + desvinculación): los avisos se envían después y un fallo de correo nunca los deshace.
    institution = db.get(Institution, idInstitucion)
    for profile, target, previous, moment in applied:
        patients.notifyAssignment(db, actor, institution, profile, target, previous, moment)
    counts: dict[uuid.UUID, int] = {}
    for _, target, _, _ in applied:
        counts[target.idInstitucionUsuario] = counts.get(target.idInstitucionUsuario, 0) + 1
    return OffboardResult(reasignados=len(applied), destinos=[
        OffboardDestination(idOperadorNuevo=targetId, operador=names.get(targetId), cantidad=count) for targetId, count in counts.items()])
