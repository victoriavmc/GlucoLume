# InstitutionPatients - Pacientes institucionales (PerfilMedicion INSTITUCIONAL)
#
# Un paciente institucional no es una cuenta de GlucoLume: es un PerfilMedicion que administra una institución y al
# que después se asocian mediciones. Pertenece a la institución a través de su único operador responsable
# (idInstitucionUsuarioResponsable -> InstitucionUsuario.idInstitucion), aunque ese vínculo luego quede de baja.
#
# Autorización (app/services/institution.py, ROLE_PERMISSIONS), resuelta en cada operación desde la base:
#   CONSULTAR_PACIENTES: propietario, moderador y operador ven el listado de los pacientes de su institución con su información
#                        ADMINISTRATIVA (nombre, apellido, responsable, fecha de registro y estado). Un operador que consulta un
#                        paciente de OTRO operador no recibe documento, fecha de nacimiento, edad, sexo ni datos de salud. La
#                        información de salud (mediciones) la autoriza app/services/patientAccess.py: solo el operador responsable.
#   GESTIONAR_PACIENTES: alta, modificación y asignación del responsable. Un operador solo modifica o reasigna
#                        los pacientes a su cargo; propietario y moderador, cualquiera de la institución.
#   BAJA_PACIENTES:      propietario y moderador.
# Toda consulta filtra por institución en SQL; un identificador de otra institución se informa como inexistente.
#
# Estado sin columnas nuevas (columnas existentes de PerfilMedicion):
#   ACTIVO: fechaExpiracionDatosPersonales IS NULL.
#   BAJA:   fechaExpiracionDatosPersonales informada = fin del período de conservación de 12 meses (por la baja
#           administrativa del paciente o por el cierre de la institución). Solo lectura.
#   Depurado: fechaDepuracionDatosPersonales informada (app/services/institutionalRetention.py); deja de listarse.
# La fecha exacta de la baja y quién la hizo quedan en Auditoria (BAJA_PACIENTE). Las mediciones no se tocan.
# Auditoría sin datos personales: solo identificadores y nombres de campos.

import json
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.profileTransfer import ProfileTransfer
from app.models.user import User
from app.schemas.measurementProfile import (
    AssignableOperator,
    PatientCreateRequest,
    PatientPage,
    PatientRead,
    PatientRegistrant,
    PatientResponsible,
    PatientUpdateRequest,
    normalizeDocument,
)
from app.emails.eventTypes import EmailEventType
from app.services import email as emailService
from app.services import institution as institutions
from app.services import measurementRetention, patientAccess, reassignments, resultEmailStore
from app.services.audit import registerEvent
from app.services.measurementProfile import EDAD_MAXIMA, buildInstitutionalProfile, calculateAge
from app.services.measurementVisibility import ACTIVE_STATES, VISIBLE_MINUTES
from app.utils.timeZone import nowForDb

TIPO_INSTITUCIONAL = "INSTITUCIONAL"
PACIENTE_ACTIVO = "ACTIVO"
PACIENTE_BAJA = "BAJA"


def patientState(profile: MeasurementProfile) -> str:
    return PACIENTE_ACTIVO if profile.fechaExpiracionDatosPersonales is None else PACIENTE_BAJA


_IS_ACTIVE = MeasurementProfile.fechaExpiracionDatosPersonales.is_(None)
_IS_DISCHARGED = MeasurementProfile.fechaExpiracionDatosPersonales.is_not(None)
TRANSFERENCIA_ACEPTADA = "ACEPTADA"
TRANSFERENCIA_PENDIENTE = "PENDIENTE"
TRANSFERENCIA_CANCELADA = "CANCELADA"
# Marca de origen de una asignación directa en Auditoria (la misma consulta que las solicitudes de transferencia).
ACCION_ORIGEN_DIRECTA = "ASIGNAR_RESPONSABLE_ORIGEN"
MAX_PAGE_SIZE = 50

PATIENT_NOT_FOUND = "No encontramos ese paciente en la institución."
DUPLICATE_DOCUMENT = "Ya hay un paciente activo con ese documento en la institución."


def _notFound() -> AuthError:
    return AuthError("PACIENTE_NO_ENCONTRADO", PATIENT_NOT_FOUND)


def _ownsPatient(membership: institutions.Membership, profile: MeasurementProfile) -> bool:
    return profile.idInstitucionUsuarioResponsable == membership.relation.idInstitucionUsuario


def _canModify(membership: institutions.Membership, profile: MeasurementProfile) -> bool:
    if patientState(profile) != PACIENTE_ACTIVO or not membership.can(institutions.P_GESTIONAR_PACIENTES):
        return False
    return membership.role != institutions.ROL_OPERADOR or _ownsPatient(membership, profile)


def _patientsOf(idInstitucion: uuid.UUID):
    """Pacientes del período operativo vigente de la institución, con su responsable.

    Excluye los ya desidentificados por retención y los archivados de períodos anteriores a la última reapertura
    (su responsable dejó de estar vinculado antes de reabrirse): la reapertura no devuelve el acceso a esos datos.
    """
    return (
        select(MeasurementProfile, InstitutionUser, User)
        .join(InstitutionUser, InstitutionUser.idInstitucionUsuario == MeasurementProfile.idInstitucionUsuarioResponsable)
        .join(Institution, Institution.idInstitucion == InstitutionUser.idInstitucion)
        .join(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
        .where(
            MeasurementProfile.tipoPerfil == TIPO_INSTITUCIONAL,
            InstitutionUser.idInstitucion == idInstitucion,
            MeasurementProfile.fechaDepuracionDatosPersonales.is_(None),
            or_(
                Institution.fechaUltimaReapertura.is_(None),
                InstitutionUser.fechaBaja.is_(None),
                InstitutionUser.fechaBaja > Institution.fechaUltimaReapertura,
            ),
        )
    )


def _registrants(db: Session, profileIds: list[uuid.UUID]) -> dict[uuid.UUID, PatientRegistrant]:
    """Quién dio de alta a cada paciente, desde el evento de auditoría CREAR_PACIENTE (una consulta para todos). El responsable de las
    mediciones es otra cosa: figura en el perfil (idInstitucionUsuarioResponsable)."""
    if not profileIds:
        return {}
    rows = db.execute(
        select(Audit.idRegistro, Audit.datosNuevos, User.nombre, User.apellido)
        .outerjoin(User, User.idUsuario == Audit.idUsuario)
        .where(Audit.accion == "CREAR_PACIENTE", Audit.resultado == "EXITO", Audit.tablaAfectada == "PerfilMedicion",
               Audit.idRegistro.in_(profileIds))
        .order_by(Audit.fechaHora)).all()
    result: dict[uuid.UUID, PatientRegistrant] = {}
    for idRegistro, newData, name, surname in rows:
        try:
            role = (json.loads(newData) if newData else {}).get("rolRegistrante")
        except ValueError:
            role = None
        result.setdefault(idRegistro, PatientRegistrant(nombre=name, apellido=surname, rolInstitucion=role))
    return result


def _read(membership, profile: MeasurementProfile, relation: InstitutionUser, operator: User, now: datetime,
          registrant: PatientRegistrant | None = None) -> PatientRead:
    foreign = membership.role == institutions.ROL_OPERADOR and not _ownsPatient(membership, profile)  # administrativa solamente
    authorized = patientAccess.canViewMeasurements(membership, profile)
    return PatientRead(
        idPerfilMedicion=profile.idPerfilMedicion,
        identificadorPseudonimo=profile.identificadorPseudonimo,
        nombre=profile.nombre,
        apellido=profile.apellido,
        dni=None if foreign else profile.dni,
        fechaNacimiento=None if foreign else profile.fechaNacimiento,
        edad=None if foreign else (calculateAge(profile.fechaNacimiento, now.date()) if profile.fechaNacimiento else profile.edadDeclarada),
        sexoModelo=None if foreign else profile.sexoModelo,
        estado=patientState(profile),
        fechaCreacion=profile.fechaCreacion,
        fechaUltimaMedicion=profile.fechaUltimaMedicion if authorized else None,
        esMio=_ownsPatient(membership, profile),
        medicionesAutorizadas=authorized,
        registradoPor=registrant,
        fechaExpiracionDatosPersonales=profile.fechaExpiracionDatosPersonales,
        responsable=PatientResponsible(
            idInstitucionUsuario=relation.idInstitucionUsuario,
            # Nombre de la cuenta o, si se eliminó, la identidad profesional conservada.
            nombre=operator.nombre or relation.nombreProfesionalHistorico,
            apellido=operator.apellido or relation.apellidoProfesionalHistorico,
            activo=relation.estadoRelacion == institutions.RELACION_ACTIVO,
        ),
        puedeModificar=_canModify(membership, profile),
    )


def _load(db: Session, idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID):
    row = db.execute(_patientsOf(idInstitucion).where(MeasurementProfile.idPerfilMedicion == idPerfilMedicion)).first()
    if row is None:
        raise _notFound()
    return row


def _activeOperator(db: Session, idInstitucion: uuid.UUID, idInstitucionUsuario: uuid.UUID) -> InstitutionUser:
    """El responsable debe ser un OPERADOR ACTIVO de la misma institución (nunca de otra). Bloquea el vínculo hasta el commit: una baja
    simultánea del operador espera a que este alta o reasignación termine y recién entonces cuenta sus pacientes."""
    relation = institutions.lockRelation(db, idInstitucionUsuario)
    if (
        relation is None
        or relation.idInstitucion != idInstitucion
        or relation.rolInstitucion != institutions.ROL_OPERADOR
        or relation.estadoRelacion != institutions.RELACION_ACTIVO
    ):
        raise AuthError("OPERADOR_NO_DISPONIBLE", "El responsable debe ser un operador activo de esta institución.")
    return relation


def _requireUniqueDocument(db: Session, idInstitucion: uuid.UUID, dni: str | None, exclude: uuid.UUID | None = None):
    """Un solo paciente ACTIVO por documento dentro de la institución (el mismo documento puede existir en otra). Sin documento no hay
    nada que comparar. Es la comprobación amable; la garantía ante altas simultáneas es el índice UX_PerfilMedicion_dniInstitucion,
    cuyo choque se traduce al mismo error (_duplicateOnConflict)."""
    dni = normalizeDocument(dni)
    if not dni:
        return
    query = _patientsOf(idInstitucion).where(MeasurementProfile.dni == dni, _IS_ACTIVE)
    if exclude is not None:
        query = query.where(MeasurementProfile.idPerfilMedicion != exclude)
    if db.execute(query).first() is not None:
        raise AuthError("PACIENTE_REGISTRADO", DUPLICATE_DOCUMENT)


def _duplicateOnConflict(db: Session, error: IntegrityError) -> AuthError:
    """Dos altas (o ediciones) simultáneas del mismo documento: gana una y la otra recibe el mismo error que la comprobación previa."""
    db.rollback()
    return AuthError("PACIENTE_REGISTRADO", DUPLICATE_DOCUMENT)


def _fullName(user: User | None) -> str:
    return f"{user.nombre or ''} {user.apellido or ''}".strip() if user else "Operador"


def _notifyPatient(event: EmailEventType, to: User | None, institution: Institution, profile: MeasurementProfile,
                   who: str, now: datetime, *, toList: bool = False) -> None:
    """Aviso por correo (después del commit; un fallo de SMTP nunca revierte la operación). Sin datos personales del
    paciente: solo su identificador seudónimo."""
    if to is None or not to.correoElectronico:
        return
    path = f"/app/instituciones/{institution.idInstitucion}/pacientes"
    emailService.sendEmailEventInBackground(
        event, to.correoElectronico,
        {"nombre": to.nombre, "nombreInstitucion": institution.nombre,
         "identificadorPseudonimo": profile.identificadorPseudonimo or "Paciente sin identificador",
         "nombreOperador": who, "fechaEvento": now,
         "urlPaciente": emailService.frontendUrl(path if toList else f"{path}/{profile.idPerfilMedicion}")},
    )


def cancelPendingTransfers(db: Session, idPerfilMedicion: uuid.UUID) -> None:
    """Las solicitudes pendientes de un perfil pierden vigencia si su responsable cambia o el paciente se da de baja."""
    db.execute(
        update(ProfileTransfer)
        .where(ProfileTransfer.idPerfilMedicion == idPerfilMedicion,
               ProfileTransfer.estado == TRANSFERENCIA_PENDIENTE)
        .values(estado=TRANSFERENCIA_CANCELADA).execution_options(synchronize_session=False)
    )


def _escapeLike(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# --- Consultas ------------------------------------------------------------------------------


def listPatients(
    db: Session, actor: User, idInstitucion: uuid.UUID, *, busqueda: str | None = None,
    idResponsable: uuid.UUID | None = None, estado: str = PACIENTE_ACTIVO, soloMios: bool = False,
    pagina: int = 1, tamanioPagina: int = 20,
) -> PatientPage:
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_PACIENTES)
    tamanioPagina = max(1, min(tamanioPagina, MAX_PAGE_SIZE))
    pagina = max(1, pagina)
    query = _patientsOf(idInstitucion).where(_IS_ACTIVE if estado == PACIENTE_ACTIVO else _IS_DISCHARGED)
    if busqueda and busqueda.strip():
        term = f"%{_escapeLike(busqueda.strip())}%"
        byDocument = MeasurementProfile.dni.ilike(term, escape="\\")
        if membership.role == institutions.ROL_OPERADOR:
            # El documento de un paciente ajeno no se expone ni por búsqueda: un operador solo busca por documento a los suyos.
            byDocument = and_(byDocument, MeasurementProfile.idInstitucionUsuarioResponsable == membership.relation.idInstitucionUsuario)
        query = query.where(or_(
            MeasurementProfile.nombre.ilike(term, escape="\\"),
            MeasurementProfile.apellido.ilike(term, escape="\\"),
            byDocument,
            MeasurementProfile.identificadorPseudonimo.ilike(term, escape="\\"),
        ))
    if soloMios:
        query = query.where(MeasurementProfile.idInstitucionUsuarioResponsable == membership.relation.idInstitucionUsuario)
    elif idResponsable is not None:
        query = query.where(MeasurementProfile.idInstitucionUsuarioResponsable == idResponsable)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(
        query.order_by(MeasurementProfile.apellido, MeasurementProfile.nombre, MeasurementProfile.idPerfilMedicion)
        .offset((pagina - 1) * tamanioPagina)
        .limit(tamanioPagina)
    ).all()
    now = nowForDb()
    registrants = _registrants(db, [row[0].idPerfilMedicion for row in rows])
    return PatientPage(
        items=[_read(membership, *row, now, registrants.get(row[0].idPerfilMedicion)) for row in rows], total=total, pagina=pagina,
        tamanioPagina=tamanioPagina,
    )


def getPatient(db: Session, actor: User, idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID) -> PatientRead:
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_PACIENTES)
    row = _load(db, idInstitucion, idPerfilMedicion)
    # Acceso a datos personales de un paciente: queda registrado (sin los datos).
    registerEvent(db, "ACCESO", "CONSULTAR_PACIENTE", True, actor.idUsuario, "PerfilMedicion", idPerfilMedicion)
    db.commit()
    return _read(membership, *row, nowForDb(), _registrants(db, [idPerfilMedicion]).get(idPerfilMedicion))


def assignableOperators(db: Session, actor: User, idInstitucion: uuid.UUID) -> list[AssignableOperator]:
    """Operadores activos de la institución, solo para elegir responsable. No da acceso a administrar operadores."""
    institutions.requireMembership(db, actor, idInstitucion, institutions.P_GESTIONAR_PACIENTES)
    rows = db.execute(
        select(InstitutionUser.idInstitucionUsuario, User.nombre, User.apellido)
        .join(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
        .where(
            InstitutionUser.idInstitucion == idInstitucion,
            InstitutionUser.rolInstitucion == institutions.ROL_OPERADOR,
            InstitutionUser.estadoRelacion == institutions.RELACION_ACTIVO,
        )
        .order_by(User.apellido, User.nombre)
    ).all()
    return [AssignableOperator(idInstitucionUsuario=row[0], nombre=row[1], apellido=row[2]) for row in rows]


# --- Alta, modificación, asignación y baja --------------------------------------------------


def createPatient(db: Session, actor: User, idInstitucion: uuid.UUID, data: PatientCreateRequest) -> PatientRead:
    """Alta de un paciente. QUIÉN REGISTRA y QUIÉN ES RESPONSABLE son datos distintos y los dos quedan auditados:
      - OPERADOR: el paciente queda SIEMPRE a su cargo. El responsable sale de su sesión y de su vínculo activo, nunca de lo que
        envíe el cliente: si la solicitud trae a otro operador se rechaza (y el intento queda auditado).
      - PROPIETARIO o MODERADOR: designan al responsable, que debe ser un OPERADOR ACTIVO de esta institución (otra institución,
        inactivo o dado de baja se rechaza). Quien da el alta queda como autor del registro (Auditoria CREAR_PACIENTE.idUsuario)."""
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_GESTIONAR_PACIENTES)
    requested = data.idInstitucionUsuarioResponsable
    if membership.role == institutions.ROL_OPERADOR:
        if requested is not None and requested != membership.relation.idInstitucionUsuario:
            registerEvent(db, "PERMISO", "CREAR_PACIENTE", False, actor.idUsuario, "Institucion", idInstitucion,
                          observacion="Motivo: ASIGNACION_A_OTRO_OPERADOR")
            db.commit()
            raise AuthError("PERMISO_INSUFICIENTE", "Los pacientes que registrás quedan a tu cargo: no podés asignarlos a otro operador.")
        idResponsable = membership.relation.idInstitucionUsuario
    else:
        if requested is None:
            raise AuthError("RESPONSABLE_REQUERIDO", "Elegí el operador responsable del paciente.")
        idResponsable = requested
    responsable = _activeOperator(db, idInstitucion, idResponsable)
    _requireUniqueDocument(db, idInstitucion, data.dni)
    # Reutiliza el constructor del perfil institucional: valida operador activo, institución ACTIVA y edad.
    profile = buildInstitutionalProfile(responsable, data)
    try:
        db.add(profile)
        db.flush()
        measurementRetention.stampInstitution(db, profile.idPerfilMedicion, idInstitucion)  # activa el índice de documento único
        db.flush()
    except IntegrityError as error:
        if not data.dni:
            raise
        raise _duplicateOnConflict(db, error) from error
    registerEvent(
        db, "CRUD", "CREAR_PACIENTE", True, actor.idUsuario, "PerfilMedicion", profile.idPerfilMedicion,
        datosNuevos={"idInstitucion": str(idInstitucion), "idInstitucionUsuarioResponsable": str(idResponsable),
                     "idInstitucionUsuarioRegistrante": str(membership.relation.idInstitucionUsuario),
                     "rolRegistrante": membership.role},
    )
    db.commit()
    now = nowForDb()
    responsibleUser = db.get(User, responsable.idUsuarioInvitado)
    # Quien registra recibe la confirmación; si lo dejó a cargo de otro operador, ese operador también se entera.
    _notifyPatient(EmailEventType.PACIENTE_REGISTRADO, actor, membership.institution, profile,
                   _fullName(responsibleUser), now)
    if responsable.idUsuarioInvitado != actor.idUsuario:
        _notifyPatient(EmailEventType.PACIENTE_ASIGNADO, responsibleUser, membership.institution, profile,
                       _fullName(actor), now)
    return _read(membership, *_load(db, idInstitucion, profile.idPerfilMedicion), now,
                 _registrants(db, [profile.idPerfilMedicion]).get(profile.idPerfilMedicion))


def _requireModifiable(membership, profile: MeasurementProfile) -> None:
    if patientState(profile) != PACIENTE_ACTIVO:
        raise AuthError("PACIENTE_DADO_DE_BAJA", "El paciente está dado de baja: sus datos ya no se pueden modificar.")
    if not _canModify(membership, profile):
        raise AuthError("PERMISO_INSUFICIENTE", "Solo podés modificar los pacientes a tu cargo.")


def updatePatient(
    db: Session, actor: User, idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, data: PatientUpdateRequest
) -> PatientRead:
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_GESTIONAR_PACIENTES)
    profile, _, _ = _load(db, idInstitucion, idPerfilMedicion)
    _requireModifiable(membership, profile)
    changes = {field: value for field, value in data.model_dump(exclude_unset=True).items() if value is not None}
    if "fechaNacimiento" in changes and calculateAge(changes["fechaNacimiento"], nowForDb().date()) > EDAD_MAXIMA:
        raise AuthError("EDAD_FUERA_DE_RANGO", f"La edad debe estar entre 0 y {EDAD_MAXIMA} años.")
    if "dni" in changes:
        _requireUniqueDocument(db, idInstitucion, changes["dni"], exclude=idPerfilMedicion)
    changed = [field for field, value in changes.items() if getattr(profile, field) != value]
    if changed:
        for field in changed:
            setattr(profile, field, changes[field])
        registerEvent(db, "CRUD", "MODIFICAR_PACIENTE", True, actor.idUsuario, "PerfilMedicion", idPerfilMedicion,
                      datosNuevos={"campos": sorted(changed)})
        try:
            db.commit()
        except IntegrityError as error:
            if "dni" not in changed:
                raise
            raise _duplicateOnConflict(db, error) from error
    return _read(membership, *_load(db, idInstitucion, idPerfilMedicion), nowForDb())


def applyAssignment(db: Session, actor: User, profile: MeasurementProfile, target: InstitutionUser, observacion: str | None = None
                    ) -> tuple[uuid.UUID, datetime] | None:
    """Cambia el responsable de un paciente ACTIVO a un operador ya validado. Sin commit (lo confirma quien llama, que también envía los
    avisos con notifyAssignment). Si el paciente estaba pendiente de reasignación (operador desvinculado) completa esa tarea. Cada cambio
    deja una TransferenciaPerfil ACEPTADA (destino, fecha, observación) y la auditoría (anterior, nuevo y quién). Las mediciones previas
    no se tocan: su autoría vive en Auditoria. Devuelve (responsable anterior, momento) o None si ya era el responsable."""
    previous = profile.idInstitucionUsuarioResponsable
    if previous == target.idInstitucionUsuario:
        return None
    now = nowForDb()
    cancelPendingTransfers(db, profile.idPerfilMedicion)
    profile.idInstitucionUsuarioResponsable = target.idInstitucionUsuario
    taskId = reassignments.resolveForProfile(db, profile.idPerfilMedicion, target, actor.idUsuario, observacion, now)
    transfer = ProfileTransfer(
        idPerfilMedicion=profile.idPerfilMedicion, idOperadorDestino=target.idInstitucionUsuario,
        estado=TRANSFERENCIA_ACEPTADA, fechaPeticion=now, fechaTransferencia=now,
        observacion=observacion or ("Reasignación por la desvinculación del operador anterior." if taskId
                                    else "Asignación de responsable desde la gestión de pacientes."),
    )
    db.add(transfer)
    db.flush()
    # Operador anterior, consultable en el historial de transferencias.
    registerEvent(db, "CRUD", ACCION_ORIGEN_DIRECTA, True, actor.idUsuario, "TransferenciaPerfil",
                  transfer.idTransferenciaPerfil, tablaRelacionada="InstitucionUsuario", idRelacionado=previous)
    registerEvent(
        db, "CRUD", "ASIGNAR_RESPONSABLE_PACIENTE", True, actor.idUsuario, "PerfilMedicion", profile.idPerfilMedicion,
        datosPrevios={"idInstitucionUsuarioResponsable": str(previous)},
        datosNuevos={"idInstitucionUsuarioResponsable": str(target.idInstitucionUsuario),
                     "destinoInvitadoPorElGestor": target.idUsuarioInvitador == actor.idUsuario,
                     **({"idReasignacionPaciente": str(taskId)} if taskId else {})},
    )
    return previous, now


def notifyAssignment(db: Session, actor: User, institution: Institution, profile: MeasurementProfile, target: InstitutionUser,
                     previous: uuid.UUID, now: datetime) -> None:
    """Después del commit: avisa al operador nuevo y, si seguía vinculado, al anterior."""
    newUser = db.get(User, target.idUsuarioInvitado)
    previousRelation = db.get(InstitutionUser, previous)
    previousUser = db.get(User, previousRelation.idUsuarioInvitado) if previousRelation else None
    _notifyPatient(EmailEventType.PACIENTE_ASIGNADO, newUser, institution, profile, _fullName(actor), now)
    if previousRelation is not None and previousRelation.estadoRelacion == institutions.RELACION_ACTIVO:
        _notifyPatient(EmailEventType.PACIENTE_REASIGNADO, previousUser, institution, profile, _fullName(newUser), now, toList=True)
    notifyOwners(db, actor, institution, profile, target, now, proposal=False)


def notifyOwners(db: Session, actor: User, institution: Institution, profile: MeasurementProfile, target: InstitutionUser, now: datetime,
                 *, proposal: bool) -> None:
    """Avisa a los propietarios (menos a quien hizo el cambio) de que un gestor asignó o propuso un responsable de paciente, y marca si el
    operador destino fue incorporado por la misma persona: es la forma de detectar a un gestor que se procura acceso a mediciones. Sin
    datos del paciente (solo su seudónimo). Después del commit; un fallo de SMTP nunca revierte la operación."""
    owners = db.scalars(
        select(User).join(InstitutionUser, InstitutionUser.idUsuarioInvitado == User.idUsuario).where(
            InstitutionUser.idInstitucion == institution.idInstitucion, InstitutionUser.rolInstitucion == institutions.ROL_PROPIETARIO,
            InstitutionUser.estadoRelacion == institutions.RELACION_ACTIVO)).all()
    targetUser = db.get(User, target.idUsuarioInvitado)
    invitedByActor = target.idUsuarioInvitador == actor.idUsuario
    path = f"/app/instituciones/{institution.idInstitucion}/pacientes/{profile.idPerfilMedicion}"
    for owner in owners:
        if owner.idUsuario == actor.idUsuario or not owner.correoElectronico:
            continue
        emailService.sendEmailEventInBackground(
            EmailEventType.ASIGNACION_PACIENTE_GESTION, owner.correoElectronico,
            {"nombre": owner.nombre, "nombreInstitucion": institution.nombre,
             "identificadorPseudonimo": profile.identificadorPseudonimo or "Paciente sin identificador",
             "nombreOperador": _fullName(targetUser), "nombreGestor": _fullName(actor), "propuesta": proposal,
             "invitadoPorGestor": invitedByActor, "fechaEvento": now, "urlPaciente": emailService.frontendUrl(path)})


def assignResponsible(
    db: Session, actor: User, idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, idInstitucionUsuario: uuid.UUID
) -> PatientRead:
    """Cambia el operador responsable (propietario o moderador; el operador usa una transferencia). Queda registrado en TransferenciaPerfil (ACEPTADA) y en la auditoría."""
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_GESTIONAR_PACIENTES)
    if membership.role == institutions.ROL_OPERADOR:
        # Un operador no reasigna: pide una transferencia que el otro operador acepta (profileTransfers).
        raise AuthError("PERMISO_INSUFICIENTE", "Para pasar un paciente a otro operador, solicitá una transferencia.")
    profile, _, _ = _load(db, idInstitucion, idPerfilMedicion)
    _requireModifiable(membership, profile)
    target = _activeOperator(db, idInstitucion, idInstitucionUsuario)
    current = db.get(InstitutionUser, profile.idInstitucionUsuarioResponsable) if profile.idInstitucionUsuarioResponsable else None
    if (current is not None and current.idInstitucionUsuario != target.idInstitucionUsuario
            and current.estadoRelacion == institutions.RELACION_ACTIVO and current.rolInstitucion == institutions.ROL_OPERADOR):
        # El responsable sigue activo: el cambio NO es unilateral. Se propone una transferencia que el operador destino debe aceptar (el de
        # origen puede cancelarla) y se avisa a los propietarios. Solo un paciente sin responsable activo (operador desvinculado) se asigna directo.
        from app.services import profileTransfers

        profileTransfers.proposeTransfer(db, actor, membership, profile, current, target)
        notifyOwners(db, actor, membership.institution, profile, target, nowForDb(), proposal=True)
        return _read(membership, *_load(db, idInstitucion, idPerfilMedicion), nowForDb())
    changed = applyAssignment(db, actor, profile, target)
    if changed is not None:
        db.commit()
        notifyAssignment(db, actor, membership.institution, profile, target, *changed)
    return _read(membership, *_load(db, idInstitucion, idPerfilMedicion), nowForDb())


def dischargePatient(db: Session, actor: User, idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID) -> PatientRead:
    """Baja administrativa. Con la migración 031 la baja ANONIMIZA al paciente en el acto (measurementRetention.anonymizeProfile): se borran sus
    datos personales y sus mediciones quedan sin persona, en la cohorte anónima de la institución, hasta 12 meses después de su última
    medición. Sin la 031 se conserva lo de siempre: período de 12 meses (fechaExpiracionDatosPersonales) y desidentificación por el job."""
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_BAJA_PACIENTES)
    profile, _, _ = _load(db, idInstitucion, idPerfilMedicion)
    if patientState(profile) != PACIENTE_ACTIVO:
        raise AuthError("PACIENTE_DADO_DE_BAJA", "El paciente ya está dado de baja.")
    now = nowForDb()
    anonymize = measurementRetention.ready(db)
    if anonymize and db.scalar(
            select(func.count()).select_from(Measurement).where(
                Measurement.idPerfilMedicion == idPerfilMedicion, Measurement.estadoMedicion.in_(ACTIVE_STATES),
                Measurement.fechaHoraInicio >= now - timedelta(minutes=VISIBLE_MINUTES))):
        # Anonimizar separa las mediciones del paciente: una adquisición en curso quedaría sin dueño al guardarse.
        raise AuthError("MEDICION_EN_CURSO", "El paciente tiene una medición en curso: esperá a que termine para darlo de baja.")
    pseudonym = profile.identificadorPseudonimo  # el aviso al operador usa el que él conoce; el perfil recibe uno nuevo al anonimizar
    retentionEnd = institutions.addMonths(now, institutions.RETENTION_MONTHS)
    profile.fechaExpiracionDatosPersonales = retentionEnd
    resultEmailStore.clear(db, idPerfilMedicion)  # sin acceso operativo, el paciente deja de recibir resultados
    cancelPendingTransfers(db, idPerfilMedicion)
    # Un paciente dado de baja ya no necesita responsable: si estaba pendiente de reasignación, la tarea se cancela y queda en el historial.
    reassignments.cancelForProfile(db, idPerfilMedicion, reassignments.RESULTADO_PACIENTE_BAJA, now, actor.idUsuario)
    registerEvent(db, "CRUD", "BAJA_PACIENTE", True, actor.idUsuario, "PerfilMedicion", idPerfilMedicion,
                  datosNuevos={"estado": PACIENTE_BAJA, "finConservacionDatos": retentionEnd.isoformat(), "anonimizado": anonymize})
    if anonymize:
        db.flush()
        measurementRetention.anonymizeProfile(db, idPerfilMedicion, now)
        registerEvent(db, "CRUD", measurementRetention.ACCION_ANONIMIZAR, True, actor.idUsuario, "PerfilMedicion", idPerfilMedicion,
                      datosNuevos={"perfilesAnonimizados": 1, "origen": "BAJA_PACIENTE"})
    db.commit()
    responsibleRelation = db.get(InstitutionUser, profile.idInstitucionUsuarioResponsable)
    if (responsibleRelation is not None and responsibleRelation.estadoRelacion == institutions.RELACION_ACTIVO
            and responsibleRelation.idUsuarioInvitado != actor.idUsuario):
        notified = SimpleNamespace(idPerfilMedicion=idPerfilMedicion, identificadorPseudonimo=pseudonym)
        _notifyPatient(EmailEventType.PACIENTE_BAJA, db.get(User, responsibleRelation.idUsuarioInvitado),
                       membership.institution, notified, _fullName(actor), now, toList=anonymize)  # type: ignore[arg-type]
    if anonymize:  # el paciente ya no figura en los listados: la respuesta sale del perfil ya anonimizado
        db.refresh(profile)
        row = db.execute(select(MeasurementProfile, InstitutionUser, User)
                         .join(InstitutionUser, InstitutionUser.idInstitucionUsuario == MeasurementProfile.idInstitucionUsuarioResponsable)
                         .join(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
                         .where(MeasurementProfile.idPerfilMedicion == idPerfilMedicion)).one()
        return _read(membership, *row, now)
    return _read(membership, *_load(db, idInstitucion, idPerfilMedicion), now)
