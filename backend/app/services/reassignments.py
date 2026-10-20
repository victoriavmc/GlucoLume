# Reassignments - Pacientes pendientes de reasignación cuando se desvincula a un operador (capa de datos)
#
# Cuando un OPERADOR deja de pertenecer a una institución, el sistema:
#   1. le revoca el acceso en el mismo momento (su vínculo pasa a BAJA; nada de esto depende de la tarea);
#   2. identifica a los pacientes ACTIVOS que tenía a su cargo y crea UNA tarea ReasignacionPaciente PENDIENTE por paciente;
#   3. cancela las solicitudes de transferencia pendientes de esos pacientes (ya no hay quien las atienda);
#   4. avisa por correo a los moderadores activos —y al propietario solo si no hay moderador activo—.
# La selección del nuevo responsable NUNCA es automática: la hace un moderador o el propietario (services/institutionReassignments.py).
# Mientras la tarea está pendiente, PerfilMedicion.idInstitucionUsuarioResponsable sigue apuntando al operador anterior (la columna es NOT
# NULL para pacientes institucionales), pero como su vínculo está en BAJA no tiene ningún acceso: el control de acceso exige un vínculo
# ACTIVO (services/patientAccess.py). La reasignación es independiente de la eliminación de la cuenta global del operador: no la bloquea.
#
# Pacientes ya dados de baja (aunque sigan en conservación) o ya desidentificados no necesitan responsable operativo y no generan tarea.
# La autoría de las mediciones no se toca: vive en Auditoria (INICIAR_MEDICION + vínculo del operador).
#
# Este módulo no importa services/institution.py (lo usa); los permisos se resuelven por rol con constantes locales.

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.emails.eventTypes import EmailEventType
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.measurementProfile import MeasurementProfile
from app.models.patientReassignment import PatientReassignment
from app.models.profileTransfer import ProfileTransfer
from app.models.user import User
from app.services import email as emailService
from app.services.audit import registerEvent

PENDIENTE = "PENDIENTE"
COMPLETADA = "COMPLETADA"
CANCELADA = "CANCELADA"
MOTIVO_BAJA_OPERADOR = "BAJA_OPERADOR"
RESULTADO_REASIGNADO = "REASIGNADO"
RESULTADO_PACIENTE_BAJA = "PACIENTE_DADO_DE_BAJA"
RESULTADO_INSTITUCION_CERRADA = "INSTITUCION_CERRADA"

ACCION_PENDIENTES = "PACIENTES_PENDIENTES_REASIGNACION"
ACCION_CANCELAR = "CANCELAR_REASIGNACION_PACIENTES"


def activeProfilesOf(idInstitucionUsuario: uuid.UUID):
    """Pacientes institucionales ACTIVOS (sin baja administrativa ni desidentificación) a cargo del vínculo."""
    return select(MeasurementProfile.idPerfilMedicion).where(
        MeasurementProfile.tipoPerfil == "INSTITUCIONAL",
        MeasurementProfile.idInstitucionUsuarioResponsable == idInstitucionUsuario,
        MeasurementProfile.fechaExpiracionDatosPersonales.is_(None),
        MeasurementProfile.fechaDepuracionDatosPersonales.is_(None),
    )


def activeProfileCount(db: Session, idInstitucionUsuario: uuid.UUID) -> int:
    """Cantidad de pacientes activos que el vínculo tiene hoy a su cargo (los que impiden desvincularlo)."""
    return db.scalar(select(func.count()).select_from(activeProfilesOf(idInstitucionUsuario).subquery())) or 0


def openForOperator(db: Session, relation: InstitutionUser, idActor: uuid.UUID | None, now: datetime) -> int:
    """Marca como pendientes de reasignación a los pacientes activos del operador desvinculado. Sin commit; devuelve la cantidad.
    Idempotente: un paciente que ya tiene su tarea pendiente no se duplica (índice único filtrado)."""
    profileIds = list(db.scalars(activeProfilesOf(relation.idInstitucionUsuario)))
    if not profileIds:
        return 0
    alreadyOpen = set(db.scalars(select(PatientReassignment.idPerfilMedicion).where(
        PatientReassignment.idPerfilMedicion.in_(profileIds), PatientReassignment.estado == PENDIENTE)))
    created = 0
    for idPerfil in profileIds:
        if idPerfil in alreadyOpen:
            continue
        db.add(PatientReassignment(
            idInstitucion=relation.idInstitucion, idPerfilMedicion=idPerfil, idOperadorAnterior=relation.idInstitucionUsuario,
            estado=PENDIENTE, motivo=MOTIVO_BAJA_OPERADOR, fechaCreacion=now))
        created += 1
    db.execute(
        update(ProfileTransfer)
        .where(ProfileTransfer.idPerfilMedicion.in_(profileIds), ProfileTransfer.estado == "PENDIENTE")
        .values(estado="CANCELADA").execution_options(synchronize_session=False)
    )
    db.flush()
    if created:
        registerEvent(db, "CRUD", ACCION_PENDIENTES, True, idActor, "InstitucionUsuario", relation.idInstitucionUsuario,
                      datosNuevos={"pacientesPendientes": created, "motivo": MOTIVO_BAJA_OPERADOR})
    return created


def resolveForProfile(db: Session, idPerfilMedicion: uuid.UUID, target: InstitutionUser, idActor: uuid.UUID,
                      observacion: str | None, now: datetime) -> uuid.UUID | None:
    """Si el paciente tenía una tarea pendiente, la completa con el operador nuevo. Condicionado al estado: dos reasignaciones
    simultáneas no completan la misma tarea dos veces. Devuelve el id de la tarea resuelta o None si no había."""
    task = db.scalar(select(PatientReassignment).where(
        PatientReassignment.idPerfilMedicion == idPerfilMedicion, PatientReassignment.estado == PENDIENTE))
    if task is None:
        return None
    result = db.execute(
        update(PatientReassignment)
        .where(PatientReassignment.idReasignacionPaciente == task.idReasignacionPaciente, PatientReassignment.estado == PENDIENTE)
        .values(estado=COMPLETADA, idOperadorNuevo=target.idInstitucionUsuario, fechaResolucion=now, idUsuarioResolutor=idActor,
                resultado=RESULTADO_REASIGNADO, observacion=observacion)
        .execution_options(synchronize_session=False)
    )
    return task.idReasignacionPaciente if result.rowcount == 1 else None


def cancelForProfile(db: Session, idPerfilMedicion: uuid.UUID, resultado: str, now: datetime, idActor: uuid.UUID | None = None) -> int:
    """El paciente ya no necesita responsable (baja administrativa): su tarea pendiente se cancela y queda en el historial."""
    return db.execute(
        update(PatientReassignment)
        .where(PatientReassignment.idPerfilMedicion == idPerfilMedicion, PatientReassignment.estado == PENDIENTE)
        .values(estado=CANCELADA, fechaResolucion=now, resultado=resultado, idUsuarioResolutor=idActor)
        .execution_options(synchronize_session=False)
    ).rowcount


def cancelForInstitution(db: Session, idInstitucion: uuid.UUID, now: datetime) -> int:
    """La institución se cierra: sus pacientes pasan a conservación sin acceso operativo, así que nada queda por reasignar."""
    return db.execute(
        update(PatientReassignment)
        .where(PatientReassignment.idInstitucion == idInstitucion, PatientReassignment.estado == PENDIENTE)
        .values(estado=CANCELADA, fechaResolucion=now, resultado=RESULTADO_INSTITUCION_CERRADA)
        .execution_options(synchronize_session=False)
    ).rowcount


def pendingCount(db: Session, idInstitucion: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(PatientReassignment).where(
        PatientReassignment.idInstitucion == idInstitucion, PatientReassignment.estado == PENDIENTE)) or 0


def managersToNotify(db: Session, idInstitucion: uuid.UUID) -> list[User]:
    """Moderadores activos y, solo si no hay ninguno, propietarios activos. Cuentas ACTIVAS con correo."""
    def usersWith(role: str) -> list[User]:
        return list(db.scalars(
            select(User).join(InstitutionUser, InstitutionUser.idUsuarioInvitado == User.idUsuario).where(
                InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.rolInstitucion == role,
                InstitutionUser.estadoRelacion == "ACTIVO", User.estado == "ACTIVO", User.correoElectronico.is_not(None))))
    return usersWith("MODERADOR") or usersWith("PROPIETARIO")


def notifyManagers(db: Session, institution: Institution, operatorName: str, count: int, now: datetime) -> int:
    """Aviso por correo (después del commit). Solo cantidad y nombre del operador: nunca datos de los pacientes."""
    sent = 0
    for manager in managersToNotify(db, institution.idInstitucion):
        emailService.sendEmailEventInBackground(
            EmailEventType.PACIENTES_PENDIENTES_REASIGNACION, manager.correoElectronico,
            {"nombre": manager.nombre, "nombreOperador": operatorName, "nombreInstitucion": institution.nombre, "cantidad": count,
             "urlGestion": emailService.frontendUrl(f"/app/instituciones/{institution.idInstitucion}/pacientes/reasignaciones"),
             "fechaEvento": now})
        sent += 1
    return sent
