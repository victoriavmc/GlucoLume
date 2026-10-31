# ProfileTransfers - Transferencia de pacientes institucionales entre operadores (RF32)
#
# Un paciente es un PerfilMedicion INSTITUCIONAL cuyo responsable es un InstitucionUsuario OPERADOR. Transferirlo
# NO cambia el responsable al solicitarlo: se crea una solicitud (TransferenciaPerfil PENDIENTE) que el operador
# destinatario acepta o rechaza, y que el solicitante puede cancelar mientras siga pendiente.
#
# Operador de origen: la tabla no lo tiene; se registra en Auditoria al solicitar (accion SOLICITAR_TRANSFERENCIA_PERFIL,
# tablaAfectada TransferenciaPerfil, idRelacionado = InstitucionUsuario de origen) y de ahí se consulta. Las
# asignaciones directas del propietario/moderador (institutionPatients.assignResponsible) registran el mismo dato.
#
# Concurrencia y atomicidad:
#   - UX_TransferenciaPerfil_pendiente: una sola solicitud PENDIENTE por perfil.
#   - Aceptar = UPDATE condicionado de la solicitud (PENDIENTE -> ACEPTADA) + UPDATE condicionado del perfil
#     (responsable = origen -> destino) en UNA transacción. Si el perfil ya no pertenece al origen, la solicitud
#     está obsoleta: se cancela, no se sobrescribe al responsable actual.
#   - Las mediciones no se tocan: Medicion cuelga de idPerfilMedicion, que no cambia.
#
# Autorización: toda operación exige vínculo ACTIVO en una institución ACTIVA (requireMembership). Solo el
# responsable actual solicita, solo el destino responde y solo el solicitante cancela. Quien no participa recibe 404.
# Fechas: hora de Argentina sin zona (política única de app/utils/timeZone.py) en TransferenciaPerfil y Auditoria. El
# detalle las devuelve con su zona explícita (UTC-03:00) para que el cliente las convierta a su hora local.

import uuid
from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.core.exceptions import AuthError
from app.emails.eventTypes import EmailEventType
from app.models.audit import Audit
from app.models.institutionUser import InstitutionUser
from app.models.measurementProfile import MeasurementProfile
from app.models.profileTransfer import ProfileTransfer
from app.models.user import User
from app.schemas.profileTransfer import (
    TransferActor,
    TransferDetail,
    TransferInstitution,
    TransferItem,
    TransferPage,
    TransferParty,
    TransferPatient,
    TransferStep,
    TransferTechnical,
)
from app.services import email as emailService
from app.services import institution as institutions
from app.services import institutionNotifications
from app.services import institutionPatients as patients
from app.services import patientAccess
from app.services.audit import personName, registerEvent, sanitize
from app.services.measurementProfile import calculateAge
from app.utils.timeZone import nowForDb, withArgentinaZone

PENDIENTE, ACEPTADA, RECHAZADA, CANCELADA = "PENDIENTE", "ACEPTADA", "RECHAZADA", "CANCELADA"
ACCION_SOLICITAR = "SOLICITAR_TRANSFERENCIA_PERFIL"
ORIGIN_ACTIONS = (ACCION_SOLICITAR, patients.ACCION_ORIGEN_DIRECTA)
PENDING_UNIQUE_INDEX = "UX_TransferenciaPerfil_pendiente"
MAX_PAGE_SIZE = 50

NOT_FOUND = "No encontramos esa transferencia."
NOT_PENDING = "Esta transferencia ya fue respondida o cancelada."
OBSOLETE = "El paciente ya no está a cargo de quien lo transfería, por lo que la solicitud perdió vigencia."
ALREADY_PENDING = "Este paciente ya tiene una transferencia pendiente de respuesta."


def _error(code: str, message: str) -> AuthError:
    return AuthError(code, message)


def _transferData(idPerfil, destId, **extra) -> dict:
    """Datos de auditoría de una transferencia: paciente y operador destinatario (el origen va como relacionado)."""
    return {"idPerfilMedicion": str(idPerfil), "idOperadorDestino": str(destId), **extra}


def _violates(error: IntegrityError, name: str) -> bool:
    return name in str(getattr(error, "orig", error))


def _fullName(user: User | None) -> str:
    return f"{user.nombre or ''} {user.apellido or ''}".strip() if user else "Operador"


def _party(relation: InstitutionUser | None, user: User | None) -> TransferParty | None:
    if relation is None:
        return None
    return TransferParty(
        idInstitucionUsuario=relation.idInstitucionUsuario,
        nombre=(user.nombre if user else None) or relation.nombreProfesionalHistorico,
        apellido=(user.apellido if user else None) or relation.apellidoProfesionalHistorico,
        activo=relation.estadoRelacion == institutions.RELACION_ACTIVO,
        rolInstitucion=relation.rolInstitucion,
        estadoRelacion=relation.estadoRelacion,
    )


def _requireOperator(membership: institutions.Membership) -> None:
    if membership.role != institutions.ROL_OPERADOR:
        raise _error("PERMISO_INSUFICIENTE", "Solo un operador puede solicitar o responder transferencias de pacientes.")


# --- Consulta ------------------------------------------------------------------------------------------------


def _baseQuery(idInstitucion: uuid.UUID):
    """Transferencias de la institución (por la relación de destino), con perfil, destino y origen (auditoría)."""
    destRel, originRel, profileRel = aliased(InstitutionUser), aliased(InstitutionUser), aliased(InstitutionUser)
    destUser, originUser = aliased(User), aliased(User)
    originAudit = aliased(Audit)
    query = (
        select(ProfileTransfer, MeasurementProfile, destRel, destUser, originRel, originUser)
        .join(MeasurementProfile, MeasurementProfile.idPerfilMedicion == ProfileTransfer.idPerfilMedicion)
        # El perfil debe pertenecer a la institución consultada (por el vínculo de su responsable).
        .join(profileRel, profileRel.idInstitucionUsuario == MeasurementProfile.idInstitucionUsuarioResponsable)
        .join(destRel, destRel.idInstitucionUsuario == ProfileTransfer.idOperadorDestino)
        .join(destUser, destUser.idUsuario == destRel.idUsuarioInvitado)
        .outerjoin(
            originAudit,
            (originAudit.idRegistro == ProfileTransfer.idTransferenciaPerfil)
            & (originAudit.tablaAfectada == "TransferenciaPerfil")
            & (originAudit.accion.in_(ORIGIN_ACTIONS)),
        )
        .outerjoin(originRel, originRel.idInstitucionUsuario == originAudit.idRelacionado)
        .outerjoin(originUser, originUser.idUsuario == originRel.idUsuarioInvitado)
        .where(destRel.idInstitucion == idInstitucion, profileRel.idInstitucion == idInstitucion,
               patientAccess.currentPeriod(profileRel, idInstitucion))  # no los pacientes archivados de un período anterior
    )
    return query, destRel, originRel


def canSeeIdentity(membership: institutions.Membership, profile: MeasurementProfile) -> bool:
    """Datos identificativos del paciente dentro de una TRANSFERENCIA o un dashboard individual: propietario y moderador, o el operador
    que lo tiene a cargo, mientras no hayan sido depurados. Las transferencias son más reservadas que el listado de pacientes (donde
    todo el personal ve nombre y apellido): ver una transferencia no amplía esta regla. No otorga acceso a mediciones."""
    if profile.fechaDepuracionDatosPersonales is not None:
        return False
    return (membership.role != institutions.ROL_OPERADOR
            or profile.idInstitucionUsuarioResponsable == membership.relation.idInstitucionUsuario)


def patientPhrase(patient: TransferPatient) -> str:
    """«Ana Paz, identificado como PAC-…» si hay nombre autorizado; si no, solo el identificador."""
    code = patient.identificadorPseudonimo or "sin identificador"
    name = f"{patient.nombre or ''} {patient.apellido or ''}".strip()
    return f"{name}, identificado como {code}" if name else code


def _patient(membership: institutions.Membership, profile: MeasurementProfile, age) -> TransferPatient:
    allowed = canSeeIdentity(membership, profile)
    return TransferPatient(
        idPerfilMedicion=profile.idPerfilMedicion, identificadorPseudonimo=profile.identificadorPseudonimo, edad=age,
        sexoModelo=profile.sexoModelo, puedeVerPerfil=allowed,
        nombre=profile.nombre if allowed else None, apellido=profile.apellido if allowed else None,
        datosIdentificativos=bool(profile.nombre or profile.apellido) if allowed else None,
    )


def _item(row, membership: institutions.Membership, now: datetime, kind: str = "TRANSFERENCIA") -> TransferItem:
    transfer, profile, destRel, destUser, originRel, originUser = row
    me = membership.relation.idInstitucionUsuario
    isOperator = membership.role == institutions.ROL_OPERADOR
    isRecipient = destRel.idInstitucionUsuario == me
    isSender = originRel is not None and originRel.idInstitucionUsuario == me
    pending = transfer.estado == PENDIENTE
    age = calculateAge(profile.fechaNacimiento, now.date()) if profile.fechaNacimiento else profile.edadDeclarada
    return TransferItem(
        idTransferenciaPerfil=transfer.idTransferenciaPerfil,
        estado=transfer.estado,
        fechaPeticion=transfer.fechaPeticion,
        fechaTransferencia=transfer.fechaTransferencia,
        observacion=transfer.observacion,
        paciente=_patient(membership, profile, age),
        origen=_party(originRel, originUser),
        destino=_party(destRel, destUser),
        esRecibida=isRecipient,
        esEnviada=isSender,
        puedeAceptar=pending and isOperator and isRecipient,
        puedeRechazar=pending and isOperator and isRecipient,
        puedeCancelar=pending and isOperator and isSender,
        tipo=kind,
    )


def listTransfers(
    db: Session, actor: User, idInstitucion: uuid.UUID, *, direccion: str = "todas", estado: str | None = None,
    pagina: int = 1, tamanioPagina: int = 20,
) -> TransferPage:
    """Un operador ve las transferencias en las que participa (recibidas, enviadas o ambas); propietario y moderador,
    el historial de la institución. Nunca incluye nombre ni documento del paciente."""
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_PACIENTES)
    if direccion not in ("recibidas", "enviadas", "todas"):
        raise _error("DATOS_INVALIDOS", "La dirección debe ser recibidas, enviadas o todas.")
    if estado is not None and estado not in (PENDIENTE, ACEPTADA, RECHAZADA, CANCELADA):
        raise _error("DATOS_INVALIDOS", "El estado indicado no es válido.")
    query, destRel, originRel = _baseQuery(idInstitucion)
    me = membership.relation.idInstitucionUsuario
    if direccion == "recibidas":
        query = query.where(destRel.idInstitucionUsuario == me)
    elif direccion == "enviadas":
        query = query.where(originRel.idInstitucionUsuario == me)
    elif membership.role == institutions.ROL_OPERADOR:
        query = query.where(or_(destRel.idInstitucionUsuario == me, originRel.idInstitucionUsuario == me))
    if estado is not None:
        query = query.where(ProfileTransfer.estado == estado)
    tamanioPagina = max(1, min(tamanioPagina, MAX_PAGE_SIZE))
    pagina = max(1, pagina)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(
        query.order_by(ProfileTransfer.fechaPeticion.desc(), ProfileTransfer.idTransferenciaPerfil)
        .offset((pagina - 1) * tamanioPagina).limit(tamanioPagina)
    ).all()
    now = nowForDb()
    kinds = _kinds(db, [row[0].idTransferenciaPerfil for row in rows])  # una consulta para toda la página
    return TransferPage(items=[_item(row, membership, now, kinds.get(row[0].idTransferenciaPerfil, "TRANSFERENCIA"))
                               for row in rows], total=total, pagina=pagina, tamanioPagina=tamanioPagina)


def _kinds(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """REASIGNACION para las filas creadas por una asignación directa; el resto son solicitudes entre operadores."""
    if not ids:
        return {}
    direct = db.scalars(select(Audit.idRegistro).where(
        Audit.tablaAfectada == "TransferenciaPerfil", Audit.idRegistro.in_(ids), Audit.accion == patients.ACCION_ORIGEN_DIRECTA))
    return {transferId: "REASIGNACION" for transferId in direct}


# --- Detalle ---------------------------------------------------------------------------------------------------

STEP_LABELS = {
    ACCION_SOLICITAR: ("SOLICITADA", "Solicitada"),
    patients.ACCION_ORIGEN_DIRECTA: ("REASIGNADA", "Responsable reasignado"),
    "ACEPTAR_TRANSFERENCIA_PERFIL": ("ACEPTADA", "Aceptada"),
    "RECHAZAR_TRANSFERENCIA_PERFIL": ("RECHAZADA", "Rechazada"),
    "CANCELAR_TRANSFERENCIA_PERFIL": ("CANCELADA", "Cancelada"),
    "VENCER_TRANSFERENCIA_PERFIL": ("VENCIDA", "Vencida: el responsable cambió"),
}


def _name(party: TransferParty | None, fallback: str = "operador no disponible") -> str:
    if party is None:
        return fallback
    return f"{party.nombre or ''} {party.apellido or ''}".strip() or fallback


def _describe(estado: str, kind: str, patient: str, origin: TransferParty | None, dest: TransferParty,
              requester: TransferActor | None) -> str:
    originName, destName = _name(origin), _name(dest)
    if kind == "REASIGNACION":
        if origin is None:
            return f"Se asignó el paciente {patient} al operador {destName}."
        return f"El paciente {patient} fue reasignado de {originName} a {destName}."
    if estado == ACEPTADA:
        return f"El paciente {patient} fue transferido de {originName} a {destName}."
    if estado == RECHAZADA:
        return f"{destName} rechazó la solicitud de transferencia del paciente {patient}. El responsable continúa siendo {originName}."
    if estado == CANCELADA:
        return f"{originName} canceló la solicitud de transferencia del paciente {patient}. El responsable continúa siendo {originName}."
    return (f"{originName} solicitó transferir al paciente {patient}{"," if "identificado como" in patient else ""} a {destName}. "
            f"La responsabilidad permanecerá con {originName} hasta que {destName} acepte la solicitud.")


def getTransfer(db: Session, actor: User, idInstitucion: uuid.UUID, idTransferencia: uuid.UUID) -> TransferDetail:
    """Detalle de una transferencia de la institución. Mismo alcance que el listado: un operador solo ve las suyas y
    cualquier transferencia de otra institución es 404."""
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_PACIENTES)
    row = _load(db, membership, idInstitucion, idTransferencia)
    transfer, profile, dest, destUser, origin, originUser = row
    now = nowForDb()
    events = list(db.scalars(
        select(Audit).where(Audit.tablaAfectada == "TransferenciaPerfil", Audit.idRegistro == idTransferencia)
        .order_by(Audit.fechaHora, Audit.idAuditoria)))
    request = next((e for e in events if e.accion in ORIGIN_ACTIONS), None)
    kind = "REASIGNACION" if request is not None and request.accion == patients.ACCION_ORIGEN_DIRECTA else "TRANSFERENCIA"

    # Personas que ejecutaron cada paso: una consulta de cuentas y otra de vínculos para todo el historial.
    actorIds = {e.idUsuario for e in events if e.idUsuario}
    users = {u.idUsuario: u for u in db.scalars(select(User).where(User.idUsuario.in_(actorIds)))} if actorIds else {}
    links: dict[uuid.UUID, InstitutionUser] = {}
    if actorIds:
        for link in db.scalars(select(InstitutionUser).where(
                InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.idUsuarioInvitado.in_(actorIds))
                .order_by(InstitutionUser.fechaInvitacion)):
            links[link.idUsuarioInvitado] = link

    def person(idUsuario) -> tuple[str | None, str | None, str | None]:
        link, user = links.get(idUsuario), users.get(idUsuario)
        full = personName(link, user)
        first, _, last = (full or "").partition(" ")
        return (first or None, last or None, link.rolInstitucion if link else None)

    requester = None
    if request is not None and request.idUsuario:
        first, last, role = person(request.idUsuario)
        requester = TransferActor(nombre=first, apellido=last, rolInstitucion=role)

    def when(event: Audit) -> datetime:
        return withArgentinaZone(event.fechaHora)  # Auditoria también guarda hora de Argentina

    steps = []
    for event in events:
        key = STEP_LABELS.get(event.accion)
        if key is None:
            continue
        first, last, _ = person(event.idUsuario) if event.idUsuario else (None, None, None)
        steps.append(TransferStep(clave=key[0], etiqueta=key[1], fechaHora=when(event),
                                  usuario=" ".join(p for p in (first, last) if p) or None))
        if key[0] == "ACEPTADA":
            steps.append(TransferStep(clave="RESPONSABLE_ACTUALIZADO", etiqueta="Responsable actualizado",
                                      fechaHora=withArgentinaZone(transfer.fechaTransferencia) if transfer.fechaTransferencia
                                      else when(event), usuario=None))
    answer = next((e for e in events if e.accion in ("RECHAZAR_TRANSFERENCIA_PERFIL", "CANCELAR_TRANSFERENCIA_PERFIL")), None)
    responded = None
    if transfer.estado == ACEPTADA and kind == "TRANSFERENCIA":
        responded = withArgentinaZone(transfer.fechaTransferencia) if transfer.fechaTransferencia else None
    elif answer is not None:
        responded = when(answer)

    base = _item(row, membership, now, kind)
    patient = patientPhrase(base.paciente)
    originParty, destParty = base.origen, base.destino
    data = base.model_dump()
    data.update(
        fechaPeticion=withArgentinaZone(transfer.fechaPeticion),
        fechaTransferencia=withArgentinaZone(transfer.fechaTransferencia) if transfer.fechaTransferencia else None,
    )
    return TransferDetail(
        **data,
        institucion=TransferInstitution(idInstitucion=idInstitucion, nombre=membership.institution.nombre),
        solicitante=requester,
        fechaRespuesta=responded,
        descripcion=_describe(transfer.estado, kind, patient, originParty, destParty, requester),
        historial=steps,
        tecnico=None if membership.role == institutions.ROL_OPERADOR else TransferTechnical(  # el operador no recibe detalles técnicos
            idTransferenciaPerfil=transfer.idTransferenciaPerfil, idPerfilMedicion=profile.idPerfilMedicion,
            idOperadorOrigen=origin.idInstitucionUsuario if origin is not None else None,
            idOperadorDestino=dest.idInstitucionUsuario, idInstitucion=idInstitucion,
            eventos=[{"idAuditoria": str(e.idAuditoria), "accion": e.accion, "resultado": e.resultado,
                      "datosPrevios": sanitize(_loads(e.datosPrevios)), "datosNuevos": sanitize(_loads(e.datosNuevos))}
                     for e in events]),
    )


def _loads(value):
    import json

    try:
        return json.loads(value) if value else None
    except ValueError:
        return None


def _load(db: Session, membership: institutions.Membership, idInstitucion: uuid.UUID, idTransferencia: uuid.UUID):
    """La transferencia debe ser de la institución y, para un operador, de la que participa (si no, 404)."""
    query, _, _ = _baseQuery(idInstitucion)
    row = db.execute(query.where(ProfileTransfer.idTransferenciaPerfil == idTransferencia)).first()
    if row is None:
        raise _error("TRANSFERENCIA_NO_ENCONTRADA", NOT_FOUND)
    me = membership.relation.idInstitucionUsuario
    _, _, dest, _, origin, _ = row
    if membership.role == institutions.ROL_OPERADOR and me != dest.idInstitucionUsuario and (
            origin is None or me != origin.idInstitucionUsuario):
        raise _error("TRANSFERENCIA_NO_ENCONTRADA", NOT_FOUND)
    return row


# --- Notificaciones (después del commit; un fallo de SMTP nunca revierte la operación) --------------------------


def _notify(event: EmailEventType, to: User | None, institutionName: str, profile: MeasurementProfile,
            counterpart: str, idInstitucion: uuid.UUID, now: datetime) -> None:
    if to is None or not to.correoElectronico:
        return
    emailService.sendEmailEventInBackground(
        event, to.correoElectronico,
        {"nombre": to.nombre, "nombreInstitucion": institutionName,
         "identificadorPseudonimo": profile.identificadorPseudonimo or "Paciente sin identificador",
         "nombreOperador": counterpart, "fechaEvento": now,
         "urlTransferencias": emailService.frontendUrl(f"/app/instituciones/{idInstitucion}/transferencias")},
    )


# --- Solicitar -----------------------------------------------------------------------------------------------


def requestTransfer(
    db: Session, actor: User, idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, idOperadorDestino: uuid.UUID,
    observacion: str | None,
) -> TransferItem:
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_GESTIONAR_PACIENTES)
    _requireOperator(membership)
    profile, _, _ = patients._load(db, idInstitucion, idPerfilMedicion)  # solo pacientes de esta institución
    if patients.patientState(profile) != patients.PACIENTE_ACTIVO:
        raise _error("PACIENTE_DADO_DE_BAJA", "El paciente está dado de baja: no se puede transferir.")
    me = membership.relation
    if profile.idInstitucionUsuarioResponsable != me.idInstitucionUsuario:
        raise _error("PERMISO_INSUFICIENTE", "Solo podés transferir los pacientes que tenés a cargo.")
    target = patients._activeOperator(db, idInstitucion, idOperadorDestino)
    if target.idInstitucionUsuario == me.idInstitucionUsuario:
        raise _error("TRANSFERENCIA_MISMO_RESPONSABLE", "El paciente ya está a tu cargo: elegí a otro operador.")
    pending = db.scalar(select(ProfileTransfer.idTransferenciaPerfil).where(
        ProfileTransfer.idPerfilMedicion == idPerfilMedicion, ProfileTransfer.estado == PENDIENTE))
    if pending is not None:
        raise _error("TRANSFERENCIA_PENDIENTE", ALREADY_PENDING)

    now = nowForDb()
    transfer = ProfileTransfer(idPerfilMedicion=idPerfilMedicion, idOperadorDestino=target.idInstitucionUsuario,
                               estado=PENDIENTE, fechaPeticion=now, observacion=observacion)
    try:
        db.add(transfer)
        db.flush()
        registerEvent(
            db, "CRUD", ACCION_SOLICITAR, True, actor.idUsuario, "TransferenciaPerfil", transfer.idTransferenciaPerfil,
            datosNuevos={"idPerfilMedicion": str(idPerfilMedicion), "idOperadorDestino": str(target.idInstitucionUsuario)},
            tablaRelacionada="InstitucionUsuario", idRelacionado=me.idInstitucionUsuario,
        )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if _violates(error, PENDING_UNIQUE_INDEX) or "idPerfilMedicion" in str(getattr(error, "orig", error)):
            raise _error("TRANSFERENCIA_PENDIENTE", ALREADY_PENDING) from error
        raise

    _notify(EmailEventType.TRANSFERENCIA_SOLICITADA, db.get(User, target.idUsuarioInvitado),
            membership.institution.nombre, profile, _fullName(actor), idInstitucion, now)
    institutionNotifications.transferRequested(db, membership.institution, profile, transfer.idTransferenciaPerfil, target, actor)
    return _item(_load(db, membership, idInstitucion, transfer.idTransferenciaPerfil), membership, now)


def proposeTransfer(db: Session, actor: User, membership: institutions.Membership, profile: MeasurementProfile,
                    origin: InstitutionUser, target: InstitutionUser) -> ProfileTransfer:
    """Propuesta de un propietario o moderador para pasar un paciente con responsable ACTIVO a otro operador. No cambia nada por sí sola: crea
    una transferencia PENDIENTE que el operador DESTINO debe aceptar (acceptTransfer); el operador de origen puede cancelarla o dejarla vencer.
    Así un rol sin acceso a mediciones individuales no se las procura designando unilateralmente a un operador que él mismo controla. El
    origen es el responsable actual (idRelacionado del evento de solicitud), como en una transferencia pedida por ese operador."""
    if patients.patientState(profile) != patients.PACIENTE_ACTIVO:
        raise _error("PACIENTE_DADO_DE_BAJA", "El paciente está dado de baja: no se puede transferir.")
    if db.scalar(select(ProfileTransfer.idTransferenciaPerfil).where(
            ProfileTransfer.idPerfilMedicion == profile.idPerfilMedicion, ProfileTransfer.estado == PENDIENTE)) is not None:
        raise _error("TRANSFERENCIA_PENDIENTE", ALREADY_PENDING)
    now = nowForDb()
    transfer = ProfileTransfer(idPerfilMedicion=profile.idPerfilMedicion, idOperadorDestino=target.idInstitucionUsuario,
                               estado=PENDIENTE, fechaPeticion=now, observacion="Propuesta por la gestión de pacientes.")
    try:
        db.add(transfer)
        db.flush()
        registerEvent(
            db, "CRUD", ACCION_SOLICITAR, True, actor.idUsuario, "TransferenciaPerfil", transfer.idTransferenciaPerfil,
            datosNuevos={"idPerfilMedicion": str(profile.idPerfilMedicion), "idOperadorDestino": str(target.idInstitucionUsuario),
                         "propuestaPorGestion": membership.role,
                         "destinoInvitadoPorElGestor": target.idUsuarioInvitador == actor.idUsuario},
            tablaRelacionada="InstitucionUsuario", idRelacionado=origin.idInstitucionUsuario,
        )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if _violates(error, PENDING_UNIQUE_INDEX) or "idPerfilMedicion" in str(getattr(error, "orig", error)):
            raise _error("TRANSFERENCIA_PENDIENTE", ALREADY_PENDING) from error
        raise
    _notify(EmailEventType.TRANSFERENCIA_SOLICITADA, db.get(User, target.idUsuarioInvitado), membership.institution.nombre, profile,
            _fullName(actor), membership.institution.idInstitucion, now)
    institutionNotifications.transferRequested(db, membership.institution, profile, transfer.idTransferenciaPerfil, target, actor)
    return transfer


# --- Responder y cancelar ------------------------------------------------------------------------------------


def _conditionalState(db: Session, idTransferencia: uuid.UUID, new: str, now: datetime | None = None) -> bool:
    """PENDIENTE -> nuevo estado solo si sigue pendiente (toma el lock de la fila: gana una sola solicitud)."""
    values = {"estado": new}
    if new == ACEPTADA:
        values["fechaTransferencia"] = now
    result = db.execute(
        update(ProfileTransfer)
        .where(ProfileTransfer.idTransferenciaPerfil == idTransferencia, ProfileTransfer.estado == PENDIENTE)
        .values(**values).execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def acceptTransfer(db: Session, actor: User, idInstitucion: uuid.UUID, idTransferencia: uuid.UUID) -> TransferItem:
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_GESTIONAR_PACIENTES)
    _requireOperator(membership)
    transfer, profile, dest, destUser, origin, originUser = _load(db, membership, idInstitucion, idTransferencia)
    if dest.idInstitucionUsuario != membership.relation.idInstitucionUsuario:
        raise _error("PERMISO_INSUFICIENTE", "Solo el operador destinatario puede aceptar esta transferencia.")
    if transfer.estado != PENDIENTE:
        raise _error("TRANSFERENCIA_NO_PENDIENTE", NOT_PENDING)

    originId = origin.idInstitucionUsuario if origin is not None else None
    # Antes de tocar nada: ambos operadores activos, perfil activo y todavía a cargo del origen.
    stale = (
        origin is None or origin.estadoRelacion != institutions.RELACION_ACTIVO
        or origin.rolInstitucion != institutions.ROL_OPERADOR or origin.idInstitucion != idInstitucion
        or dest.estadoRelacion != institutions.RELACION_ACTIVO or dest.rolInstitucion != institutions.ROL_OPERADOR
        or patients.patientState(profile) != patients.PACIENTE_ACTIVO
        or profile.idInstitucionUsuarioResponsable != originId
    )
    if stale:
        _expire(db, actor, idTransferencia)

    now = nowForDb()
    idProfile = profile.idPerfilMedicion
    destId = dest.idInstitucionUsuario
    institutionName = membership.institution.nombre
    if not _conditionalState(db, idTransferencia, ACEPTADA, now):
        db.rollback()
        raise _error("TRANSFERENCIA_NO_PENDIENTE", NOT_PENDING)
    changed = db.execute(
        update(MeasurementProfile)
        .where(MeasurementProfile.idPerfilMedicion == idProfile,
               MeasurementProfile.idInstitucionUsuarioResponsable == originId,
               MeasurementProfile.fechaExpiracionDatosPersonales.is_(None))
        .values(idInstitucionUsuarioResponsable=destId).execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        # Otro cambio de responsable ganó la carrera: se deshace la aceptación y la solicitud se da por vencida.
        db.rollback()
        _expire(db, actor, idTransferencia)
    registerEvent(
        db, "CRUD", "CAMBIAR_RESPONSABLE_PERFIL", True, actor.idUsuario, "PerfilMedicion", idProfile,
        datosPrevios={"idInstitucionUsuarioResponsable": str(originId)},
        datosNuevos={"idInstitucionUsuarioResponsable": str(destId), "idTransferenciaPerfil": str(idTransferencia)},
    )
    registerEvent(db, "CRUD", "ACEPTAR_TRANSFERENCIA_PERFIL", True, actor.idUsuario, "TransferenciaPerfil",
                  idTransferencia, datosNuevos=_transferData(idProfile, destId, estado=ACEPTADA),
                  tablaRelacionada="InstitucionUsuario", idRelacionado=originId)
    db.commit()

    db.expire_all()
    row = _load(db, membership, idInstitucion, idTransferencia)
    _notify(EmailEventType.TRANSFERENCIA_ACEPTADA, originUser, institutionName, row[1], _fullName(actor),
            idInstitucion, now)
    institutionNotifications.transferAnswered(db, membership.institution, row[1], idTransferencia, originUser, actor, accepted=True)
    return _item(row, membership, now)


def _expire(db: Session, actor: User, idTransferencia: uuid.UUID):
    """Cierra una solicitud que perdió vigencia (CANCELADA) y lo informa; el responsable actual no se toca."""
    if _conditionalState(db, idTransferencia, CANCELADA):
        registerEvent(db, "CRUD", "VENCER_TRANSFERENCIA_PERFIL", True, actor.idUsuario, "TransferenciaPerfil",
                      idTransferencia, observacion="Motivo: el responsable del perfil cambió o dejó de estar activo.")
    db.commit()
    raise _error("TRANSFERENCIA_OBSOLETA", OBSOLETE)


def rejectTransfer(db: Session, actor: User, idInstitucion: uuid.UUID, idTransferencia: uuid.UUID) -> TransferItem:
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_GESTIONAR_PACIENTES)
    _requireOperator(membership)
    _, profile, dest, _, origin, originUser = _load(db, membership, idInstitucion, idTransferencia)
    if dest.idInstitucionUsuario != membership.relation.idInstitucionUsuario:
        raise _error("PERMISO_INSUFICIENTE", "Solo el operador destinatario puede rechazar esta transferencia.")
    if not _conditionalState(db, idTransferencia, RECHAZADA):
        db.rollback()
        raise _error("TRANSFERENCIA_NO_PENDIENTE", NOT_PENDING)
    registerEvent(db, "CRUD", "RECHAZAR_TRANSFERENCIA_PERFIL", True, actor.idUsuario, "TransferenciaPerfil",
                  idTransferencia, datosNuevos=_transferData(profile.idPerfilMedicion, dest.idInstitucionUsuario, estado=RECHAZADA),
                  tablaRelacionada="InstitucionUsuario", idRelacionado=origin.idInstitucionUsuario if origin else None)
    institutionName = membership.institution.nombre
    db.commit()
    now = nowForDb()
    db.expire_all()
    row = _load(db, membership, idInstitucion, idTransferencia)
    _notify(EmailEventType.TRANSFERENCIA_RECHAZADA, originUser, institutionName, row[1], _fullName(actor),
            idInstitucion, now)
    institutionNotifications.transferAnswered(db, membership.institution, row[1], idTransferencia, originUser, actor, accepted=False)
    return _item(row, membership, now)


def cancelTransfer(db: Session, actor: User, idInstitucion: uuid.UUID, idTransferencia: uuid.UUID) -> TransferItem:
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_GESTIONAR_PACIENTES)
    _requireOperator(membership)
    _, profile, dest, destUser, origin, _ = _load(db, membership, idInstitucion, idTransferencia)
    if origin is None or origin.idInstitucionUsuario != membership.relation.idInstitucionUsuario:
        raise _error("PERMISO_INSUFICIENTE", "Solo quien solicitó la transferencia puede cancelarla.")
    if not _conditionalState(db, idTransferencia, CANCELADA):
        db.rollback()
        raise _error("TRANSFERENCIA_NO_PENDIENTE", "Solo se puede cancelar una transferencia pendiente.")
    registerEvent(db, "CRUD", "CANCELAR_TRANSFERENCIA_PERFIL", True, actor.idUsuario, "TransferenciaPerfil",
                  idTransferencia, datosNuevos=_transferData(profile.idPerfilMedicion, dest.idInstitucionUsuario, estado=CANCELADA),
                  tablaRelacionada="InstitucionUsuario", idRelacionado=origin.idInstitucionUsuario)
    institutionName = membership.institution.nombre
    db.commit()
    now = nowForDb()
    db.expire_all()
    row = _load(db, membership, idInstitucion, idTransferencia)
    _notify(EmailEventType.TRANSFERENCIA_CANCELADA, destUser, institutionName, row[1], _fullName(actor),
            idInstitucion, now)
    return _item(row, membership, now)
