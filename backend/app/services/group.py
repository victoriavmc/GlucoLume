# Group - Grupos familiares de cuentas individuales (CONSUMIDOR_FINAL)
#
# Separado del módulo institucional: no usa propietarios, moderadores ni operadores de instituciones.
#
# Modelo (tablas existentes Grupo y GrupoUsuario, ampliadas por 010_grupo_familiar.sql):
#   Grupo.estado ACTIVO | CERRADO (eliminación lógica).
#   GrupoUsuario.rolGrupo PROPIETARIO = ADMINISTRADOR del grupo; MIEMBRO. (MODERADOR no se usa en grupos familiares.)
#   GrupoUsuario.estadoRelacion PENDIENTE = invitación (vence a los INVITATION_VALIDITY_DAYS), ACTIVO = integrante,
#   BAJA = historial (rechazo, cancelación, salida, desvinculación o grupo eliminado).
#   Índices filtrados: un grupo ACTIVO por cuenta, un vínculo vigente por cuenta y grupo, un administrador por grupo.
#   Garantizan las reglas aun ante solicitudes simultáneas; el servicio traduce las violaciones a conflictos.
#
# Compartición: cada integrante decide, sobre su propio perfil de medición, cuatro permisos independientes
# (compartePerfil, comparteUltimaMedicion, comparteHistorial, notificaMedicion), todos en 0 al incorporarse. El historial
# autoriza también los gráficos y estadísticas calculados sobre él (012 eliminó el permiso separado de estadísticas).
# notificaMedicion autoriza el aviso (solo fecha y hora de cada medición; ver sharedNotices). Las mediciones del dueño
# se leen de su perfil individual, también las de prueba (DEMO) y las anteriores a ingresar al grupo.
# Solo la propia cuenta los modifica (la identidad sale de la sesión; nunca se aceptan ids de usuario). Pertenecer
# al grupo o ser su administrador no da acceso a datos ajenos. Cada consulta de datos compartidos verifica en el
# momento: grupo ACTIVO, vínculo ACTIVO de quien consulta y de quien comparte en el mismo grupo, permiso específico
# vigente y perfil propio (CONSUMIDOR_FINAL, no depurado). Revocar, salir, ser desvinculado o eliminar el grupo
# corta el acceso en la consulta siguiente, también en sesiones abiertas. Las mediciones no se copian ni cambian
# de dueño. Consentimientos y accesos quedan en Auditoria (sin datos de salud).

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.emails.eventTypes import EmailEventType
from app.models.group import Group
from app.models.groupUser import GroupUser
from app.models.measurement import NOT_DEMO, ORIGEN_DEMO, Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.user import User
from app.schemas.group import (
    FamilyGroupCreateRequest,
    FamilyGroupDetail,
    FamilyGroupUpdateRequest,
    GroupCandidate,
    GroupInvitationRead,
    GroupMemberRead,
    MySharingRead,
    ReceivedGroupInvitation,
    SharedHistoryPage,
    SharedLatestRead,
    SharedDemoPoint,
    SharedEvolutionPoint,
    SharedMeasurementDetail,
    SharedMeasurementRead,
    SharedMemberSummary,
    SharedNoticeRead,
    SharedNoticesRead,
    SharedProfileRead,
    SharedStatisticsRead,
    SharingSettings,
)
from app.services import email as emailService
from app.services import measurement as measurementService
from app.services import notifications
from app.services.audit import registerEvent
from app.services.rateLimiter import RateLimiter
from app.services.measurementProfile import calculateAge
from app.utils.timeZone import nowForDb

TIPO_INDIVIDUAL = "CONSUMIDOR_FINAL"
GRUPO_ACTIVO = "ACTIVO"
GRUPO_ELIMINADO = "CERRADO"
ROL_ADMIN = "PROPIETARIO"  # ADMINISTRADOR del grupo familiar
ROL_MIEMBRO = "MIEMBRO"
PENDIENTE = "PENDIENTE"
ACTIVO = "ACTIVO"
BAJA = "BAJA"
MEDICION_COMPLETADA = "COMPLETADA"
INVITATION_VALIDITY_DAYS = 7
MAX_PAGE_SIZE = 50
MAX_DEMO_POINTS = 200
MAX_SHARED_POINTS = 500
STATISTICS_DAYS = (7, 30, 90)

SHARING_FIELDS = ("compartePerfil", "comparteUltimaMedicion", "comparteHistorial", "notificaMedicion")

ACTIVE_GROUP_INDEX = "UX_GrupoUsuario_grupoActivo"
LINK_INDEX = "UX_GrupoUsuario_vinculoVigente"
ADMIN_INDEX = "UX_GrupoUsuario_administrador"

ALREADY_IN_GROUP_MESSAGE = "Ya pertenecés a un grupo. Para crear otro, primero debés abandonar el grupo actual."
NOT_FOUND_ACCOUNT_MESSAGE = (
    "No existe una cuenta individual registrada con este correo. La persona deberá registrarse en GlucoLume antes "
    "de incorporarse."
)
INSTITUTIONAL_ACCOUNT_MESSAGE = (
    "El correo corresponde a una cuenta institucional: solo las cuentas individuales pueden formar parte de grupos "
    "familiares."
)
IN_OTHER_GROUP_MESSAGE = "El usuario no puede incorporarse porque ya pertenece a otro grupo."
OWN_OTHER_GROUP_MESSAGE = "No podés incorporarte porque ya pertenecés a otro grupo. Primero tenés que abandonarlo."
ALREADY_MEMBER_MESSAGE = "Esta persona ya forma parte del grupo."
PENDING_INVITATION_MESSAGE = "Ya hay una invitación pendiente para esta persona."

_lookupLimiter = RateLimiter(20, 10 * 60, name="grupo:consulta")


@dataclass(frozen=True)
class GroupMembership:
    group: Group
    relation: GroupUser

    @property
    def isAdmin(self) -> bool:
        return self.relation.rolGrupo == ROL_ADMIN


def _role(relation: GroupUser) -> str:
    return "ADMINISTRADOR" if relation.rolGrupo == ROL_ADMIN else "MIEMBRO"


def _fullName(user: User | None) -> str | None:
    if user is None:
        return None
    return " ".join(part for part in (user.nombre, user.apellido) if part) or user.usuario


def _violates(error: IntegrityError, name: str) -> bool:
    message = str(error.orig).lower()
    return name.lower() in message or "unique constraint failed" in message


def _requireIndividual(user: User) -> None:
    if user.tipoCuenta != TIPO_INDIVIDUAL:
        raise AuthError("PERMISO_INSUFICIENTE", "Los grupos familiares son solo para cuentas individuales.")


def _expiry(relation: GroupUser) -> datetime:
    return relation.fechaInvitacion + timedelta(days=INVITATION_VALIDITY_DAYS)


def _isExpired(relation: GroupUser, now: datetime) -> bool:
    return relation.estadoRelacion == PENDIENTE and _expiry(relation) <= now


def _end(relation: GroupUser, now: datetime) -> None:
    relation.estadoRelacion = BAJA
    relation.fechaBaja = now
    for field in SHARING_FIELDS:  # al terminar el vínculo, se revoca todo lo compartido
        setattr(relation, field, False)


def activeRelation(db: Session, user: User) -> GroupUser | None:
    return db.scalar(
        select(GroupUser)
        .join(Group, Group.idGrupo == GroupUser.idGrupo)
        .where(GroupUser.idUsuario == user.idUsuario, GroupUser.estadoRelacion == ACTIVO, Group.estado == GRUPO_ACTIVO)
        .execution_options(populate_existing=True)
    )


def requireMembership(db: Session, actor: User, idGrupo: uuid.UUID, admin: bool = False) -> GroupMembership:
    """Vínculo ACTIVO de la cuenta autenticada con el grupo ACTIVO. Ajenos: 404 (no se revela qué grupos existen)."""
    _requireIndividual(actor)
    row = db.execute(
        select(Group, GroupUser)
        .join(GroupUser, GroupUser.idGrupo == Group.idGrupo)
        .where(
            Group.idGrupo == idGrupo, Group.estado == GRUPO_ACTIVO,
            GroupUser.idUsuario == actor.idUsuario, GroupUser.estadoRelacion == ACTIVO,
        )
        .execution_options(populate_existing=True)
    ).first()
    if row is None:
        raise AuthError("GRUPO_NO_ENCONTRADO", "No encontramos ese grupo entre los tuyos.")
    membership = GroupMembership(*row)
    if admin and not membership.isAdmin:
        raise AuthError("PERMISO_INSUFICIENTE", "Solo el administrador del grupo puede realizar esta operación.")
    return membership


def _admin(db: Session, idGrupo: uuid.UUID) -> User | None:
    return db.scalar(
        select(User)
        .join(GroupUser, GroupUser.idUsuario == User.idUsuario)
        .where(GroupUser.idGrupo == idGrupo, GroupUser.rolGrupo == ROL_ADMIN, GroupUser.estadoRelacion == ACTIVO)
    )


def _activeCount(db: Session, idGrupo: uuid.UUID) -> int:
    return db.scalar(
        select(func.count()).select_from(GroupUser).where(GroupUser.idGrupo == idGrupo, GroupUser.estadoRelacion == ACTIVO)
    )


def _detail(db: Session, membership: GroupMembership) -> FamilyGroupDetail:
    group, relation = membership.group, membership.relation
    return FamilyGroupDetail(
        idGrupo=group.idGrupo, nombre=group.nombre, descripcion=group.descripcion, estado=group.estado,
        fechaCreacion=group.fechaCreacion, administrador=_fullName(_admin(db, group.idGrupo)),
        cantidadIntegrantes=_activeCount(db, group.idGrupo), miRol=_role(relation),
        idGrupoUsuario=relation.idGrupoUsuario, fechaIncorporacion=relation.fechaIncorporacion,
    )


def _notify(eventType: EmailEventType, user: User | None, **context) -> None:
    if user is not None and user.correoElectronico:
        emailService.sendEmailEventInBackground(eventType, user.correoElectronico, {"nombre": user.nombre, **context})


# --- Mi grupo, crear, modificar ---------------------------------------------------------------


def getMine(db: Session, user: User) -> FamilyGroupDetail | None:
    if user.tipoCuenta != TIPO_INDIVIDUAL:
        return None
    relation = activeRelation(db, user)
    if relation is None:
        return None
    return _detail(db, GroupMembership(db.get(Group, relation.idGrupo), relation))


def getDetail(db: Session, actor: User, idGrupo: uuid.UUID) -> FamilyGroupDetail:
    return _detail(db, requireMembership(db, actor, idGrupo))


def createGroup(db: Session, user: User, data: FamilyGroupCreateRequest) -> FamilyGroupDetail:
    """Crea el grupo ACTIVO y el vínculo ADMINISTRADOR del creador en una transacción (permisos en 0)."""
    _requireIndividual(user)
    if activeRelation(db, user) is not None:
        raise AuthError("YA_PERTENECE_A_GRUPO", ALREADY_IN_GROUP_MESSAGE)
    now = nowForDb()
    group = Group(nombre=data.nombre, descripcion=data.descripcion, estado=GRUPO_ACTIVO)
    try:
        db.add(group)
        db.flush()
        relation = GroupUser(
            idGrupo=group.idGrupo, idUsuario=user.idUsuario, rolGrupo=ROL_ADMIN, estadoRelacion=ACTIVO,
            fechaInvitacion=now, fechaIncorporacion=now,
        )
        db.add(relation)
        db.flush()
        registerEvent(db, "CRUD", "CREAR_GRUPO", True, user.idUsuario, "Grupo", group.idGrupo,
                      datosNuevos={"rolGrupo": "ADMINISTRADOR", "comparticion": "NINGUNA"})
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if _violates(error, ACTIVE_GROUP_INDEX):
            raise AuthError("YA_PERTENECE_A_GRUPO", ALREADY_IN_GROUP_MESSAGE) from error
        raise
    # Después del commit: un fallo de SMTP queda auditado y no revierte el grupo.
    notifications.notifyGroupCreated(db, user, group, fecha=now)
    return _detail(db, GroupMembership(group, relation))


def resendCreationNotice(db: Session, actor: User, idGrupo: uuid.UUID) -> None:
    """Reintenta la confirmación de creación (solo el administrador, solo si no se envió)."""
    membership = requireMembership(db, actor, idGrupo, admin=True)
    if not notifications.resend(db, actor, notifications.ACCION_GRUPO, idGrupo,
                                notifications.notifyGroupCreated, membership.group):
        raise AuthError("NOTIFICACION_NO_ENVIADA", notifications.NOT_SENT_MESSAGE)


def updateGroup(db: Session, actor: User, idGrupo: uuid.UUID, data: FamilyGroupUpdateRequest) -> FamilyGroupDetail:
    membership = requireMembership(db, actor, idGrupo, admin=True)
    changes = data.model_dump(exclude_unset=True)
    if "nombre" in changes and not changes["nombre"]:
        raise AuthError("NOMBRE_REQUERIDO", "Ingresá el nombre del grupo.")
    group = membership.group
    changed = {field: value for field, value in changes.items() if getattr(group, field) != value}
    if changed:
        for field, value in changed.items():
            setattr(group, field, value)
        group.fechaActualizacion = nowForDb()
        registerEvent(db, "CRUD", "MODIFICAR_GRUPO", True, actor.idUsuario, "Grupo", idGrupo,
                      datosNuevos={"campos": sorted(changed)})
        db.commit()
    return _detail(db, membership)


# --- Integrantes e invitaciones ---------------------------------------------------------------


def listMembers(db: Session, actor: User, idGrupo: uuid.UUID) -> list[GroupMemberRead]:
    requireMembership(db, actor, idGrupo)
    rows = db.execute(
        select(GroupUser, User)
        .join(User, User.idUsuario == GroupUser.idUsuario)
        .where(GroupUser.idGrupo == idGrupo, GroupUser.estadoRelacion == ACTIVO)
        .order_by(GroupUser.rolGrupo.desc(), GroupUser.fechaIncorporacion)
    ).all()
    # Todos los integrantes activos ven qué decidió compartir cada uno (solo los permisos, nunca los datos).
    return [
        GroupMemberRead(
            idGrupoUsuario=relation.idGrupoUsuario, nombre=user.nombre, apellido=user.apellido, rol=_role(relation),
            estado=relation.estadoRelacion, fechaIncorporacion=relation.fechaIncorporacion,
            esVos=user.idUsuario == actor.idUsuario,
            **{field: bool(getattr(relation, field)) for field in SHARING_FIELDS},
            tienePerfil=_ownProfile(db, user.idUsuario) is not None,
        )
        for relation, user in rows
    ]


def listSentInvitations(db: Session, actor: User, idGrupo: uuid.UUID) -> list[GroupInvitationRead]:
    requireMembership(db, actor, idGrupo, admin=True)
    now = nowForDb()
    rows = db.execute(
        select(GroupUser, User)
        .join(User, User.idUsuario == GroupUser.idUsuario)
        .where(GroupUser.idGrupo == idGrupo, GroupUser.estadoRelacion == PENDIENTE)
        .order_by(GroupUser.fechaInvitacion.desc())
    ).all()
    return [
        GroupInvitationRead(
            idGrupoUsuario=relation.idGrupoUsuario, nombre=user.nombre, apellido=user.apellido,
            fechaInvitacion=relation.fechaInvitacion, fechaVencimiento=_expiry(relation),
            vencida=_isExpired(relation, now),
        )
        for relation, user in rows
    ]


def _eligibleTarget(db: Session, idGrupo: uuid.UUID, correoElectronico: str, now: datetime) -> User:
    target = db.scalar(select(User).where(User.correoElectronico == correoElectronico))
    if target is None or target.estado != "ACTIVO":
        # Inexistente, con el correo sin verificar, bloqueada o eliminada: mismo mensaje.
        raise AuthError("USUARIO_NO_ENCONTRADO", NOT_FOUND_ACCOUNT_MESSAGE)
    if target.tipoCuenta != TIPO_INDIVIDUAL:
        raise AuthError("CUENTA_NO_INDIVIDUAL", INSTITUTIONAL_ACCOUNT_MESSAGE)
    current = db.scalar(
        select(GroupUser).where(GroupUser.idGrupo == idGrupo, GroupUser.idUsuario == target.idUsuario,
                                GroupUser.estadoRelacion != BAJA)
    )
    if current is not None and _isExpired(current, now):
        _end(current, now)
        db.flush()
        current = None
    if current is not None and current.estadoRelacion == ACTIVO:
        raise AuthError("VINCULO_EXISTENTE", ALREADY_MEMBER_MESSAGE)
    if current is not None:
        raise AuthError("INVITACION_PENDIENTE", PENDING_INVITATION_MESSAGE)
    if activeRelation(db, target) is not None:
        raise AuthError("YA_PERTENECE_A_GRUPO", IN_OTHER_GROUP_MESSAGE)
    return target


def _limit(actor: User) -> None:
    if not _lookupLimiter.allow(str(actor.idUsuario)):
        raise AuthError("DEMASIADAS_SOLICITUDES", "Hiciste demasiadas búsquedas. Esperá unos minutos e intentá de nuevo.")


def lookupCandidate(db: Session, actor: User, idGrupo: uuid.UUID, correoElectronico: str) -> GroupCandidate:
    requireMembership(db, actor, idGrupo, admin=True)
    _limit(actor)
    target = _eligibleTarget(db, idGrupo, correoElectronico, nowForDb())
    db.rollback()  # la búsqueda no persiste nada
    return GroupCandidate(nombre=target.nombre, apellido=target.apellido)


def invite(db: Session, actor: User, idGrupo: uuid.UUID, correoElectronico: str) -> GroupInvitationRead:
    """Registra la invitación PENDIENTE y avisa por correo. No incorpora a nadie hasta que acepte."""
    membership = requireMembership(db, actor, idGrupo, admin=True)
    _limit(actor)
    now = nowForDb()
    try:
        target = _eligibleTarget(db, idGrupo, correoElectronico, now)
    except AuthError as error:
        registerEvent(db, "PERMISO", "INVITAR_GRUPO", False, actor.idUsuario, "Grupo", idGrupo,
                      observacion=f"Motivo: {error.code}")
        db.commit()
        raise
    relation = GroupUser(idGrupo=idGrupo, idUsuario=target.idUsuario, rolGrupo=ROL_MIEMBRO, estadoRelacion=PENDIENTE,
                         fechaInvitacion=now)
    try:
        db.add(relation)
        db.flush()
        registerEvent(db, "PERMISO", "INVITAR_GRUPO", True, actor.idUsuario, "GrupoUsuario", relation.idGrupoUsuario)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if _violates(error, LINK_INDEX):
            raise AuthError("INVITACION_PENDIENTE", PENDING_INVITATION_MESSAGE) from error
        raise
    url = emailService.frontendUrl("grupoFamiliar")
    _notify(EmailEventType.INVITACION_GRUPO, target, nombreGrupo=membership.group.nombre,
            nombreInvitante=_fullName(actor), fechaEvento=now, fechaExpiracion=_expiry(relation),
            urlAceptar=url, urlRechazar=url)
    return GroupInvitationRead(idGrupoUsuario=relation.idGrupoUsuario, nombre=target.nombre, apellido=target.apellido,
                               fechaInvitacion=now, fechaVencimiento=_expiry(relation), vencida=False)


def cancelInvitation(db: Session, actor: User, idGrupo: uuid.UUID, idGrupoUsuario: uuid.UUID) -> None:
    requireMembership(db, actor, idGrupo, admin=True)
    relation = db.get(GroupUser, idGrupoUsuario)
    if relation is None or relation.idGrupo != idGrupo or relation.estadoRelacion != PENDIENTE:
        raise AuthError("INVITACION_NO_ENCONTRADA", "No encontramos esa invitación pendiente.")
    _end(relation, nowForDb())
    registerEvent(db, "PERMISO", "CANCELAR_INVITACION_GRUPO", True, actor.idUsuario, "GrupoUsuario", idGrupoUsuario)
    db.commit()


def listReceivedInvitations(db: Session, user: User) -> list[ReceivedGroupInvitation]:
    if user.tipoCuenta != TIPO_INDIVIDUAL:
        return []
    now = nowForDb()
    rows = db.execute(
        select(GroupUser, Group)
        .join(Group, Group.idGrupo == GroupUser.idGrupo)
        .where(GroupUser.idUsuario == user.idUsuario, GroupUser.estadoRelacion == PENDIENTE, Group.estado == GRUPO_ACTIVO)
        .order_by(GroupUser.fechaInvitacion.desc())
    ).all()
    return [
        ReceivedGroupInvitation(
            idGrupoUsuario=relation.idGrupoUsuario, idGrupo=group.idGrupo, nombreGrupo=group.nombre,
            nombreAdministrador=_fullName(_admin(db, group.idGrupo)), fechaInvitacion=relation.fechaInvitacion,
            fechaVencimiento=_expiry(relation), estado="VENCIDA" if _isExpired(relation, now) else "PENDIENTE",
        )
        for relation, group in rows
    ]


def respondInvitation(db: Session, user: User, idGrupoUsuario: uuid.UUID, accept: bool) -> FamilyGroupDetail | None:
    """La propia cuenta invitada acepta (queda MIEMBRO ACTIVO, sin compartir nada) o rechaza.

    Aceptar es una transacción: UPDATE condicionado a PENDIENTE y, por UX_GrupoUsuario_grupoActivo, si otro proceso
    la incorporó antes a otro grupo, la base lo rechaza y se responde un conflicto controlado. Al aceptar se dan de
    baja sus otras invitaciones pendientes (incompatibles con pertenecer a un grupo).
    """
    _requireIndividual(user)
    now = nowForDb()
    relation = db.get(GroupUser, idGrupoUsuario)
    if relation is None or relation.idUsuario != user.idUsuario or relation.estadoRelacion != PENDIENTE:
        raise AuthError("INVITACION_NO_ENCONTRADA", "No encontramos esa invitación o ya fue respondida.")
    group = db.get(Group, relation.idGrupo)
    if _isExpired(relation, now) or group.estado != GRUPO_ACTIVO:
        _end(relation, now)
        registerEvent(db, "PERMISO", "RESPONDER_INVITACION_GRUPO", False, user.idUsuario, "GrupoUsuario",
                      idGrupoUsuario, observacion="Invitación no vigente")
        db.commit()
        raise AuthError("INVITACION_VENCIDA", "La invitación ya no está vigente. Pedí que te envíen una nueva.")

    if not accept:
        _end(relation, now)
        registerEvent(db, "PERMISO", "RECHAZAR_INVITACION_GRUPO", True, user.idUsuario, "GrupoUsuario", idGrupoUsuario)
        db.commit()
        return None

    if activeRelation(db, user) is not None:
        raise AuthError("YA_PERTENECE_A_GRUPO", OWN_OTHER_GROUP_MESSAGE)
    try:
        result = db.execute(
            update(GroupUser)
            .where(GroupUser.idGrupoUsuario == idGrupoUsuario, GroupUser.estadoRelacion == PENDIENTE)
            .values(estadoRelacion=ACTIVO, fechaIncorporacion=now, rolGrupo=ROL_MIEMBRO,
                    **{field: False for field in SHARING_FIELDS})
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 0:
            db.rollback()
            raise AuthError("INVITACION_NO_ENCONTRADA", "No encontramos esa invitación o ya fue respondida.")
        others = db.scalars(
            select(GroupUser).where(GroupUser.idUsuario == user.idUsuario, GroupUser.estadoRelacion == PENDIENTE,
                                    GroupUser.idGrupoUsuario != idGrupoUsuario)
        ).all()
        for other in others:
            _end(other, now)
        registerEvent(db, "PERMISO", "ACEPTAR_INVITACION_GRUPO", True, user.idUsuario, "GrupoUsuario", idGrupoUsuario,
                      datosNuevos={"rolGrupo": "MIEMBRO", "comparticion": "NINGUNA",
                                   "invitacionesInvalidadas": len(others)})
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if _violates(error, ACTIVE_GROUP_INDEX):
            raise AuthError("YA_PERTENECE_A_GRUPO", OWN_OTHER_GROUP_MESSAGE) from error
        raise
    membership = requireMembership(db, user, group.idGrupo)
    _notify(EmailEventType.AGREGADO_GRUPO, user, nombreGrupo=group.nombre, fechaEvento=now)
    _notify(EmailEventType.MIEMBRO_AGREGADO, _admin(db, group.idGrupo), nombreIntegrante=_fullName(user),
            nombreGrupo=group.nombre, fechaEvento=now)
    return _detail(db, membership)


# --- Salir, desvincular, transferir, eliminar --------------------------------------------------


def removeMember(db: Session, actor: User, idGrupo: uuid.UUID, idGrupoUsuario: uuid.UUID) -> None:
    membership = requireMembership(db, actor, idGrupo, admin=True)
    relation = db.get(GroupUser, idGrupoUsuario)
    if (relation is None or relation.idGrupo != idGrupo or relation.estadoRelacion != ACTIVO
            or relation.idGrupoUsuario == membership.relation.idGrupoUsuario):
        raise AuthError("MIEMBRO_NO_ENCONTRADO", "No encontramos ese integrante en el grupo.")
    now = nowForDb()
    _end(relation, now)
    registerEvent(db, "PERMISO", "DESVINCULAR_INTEGRANTE_GRUPO", True, actor.idUsuario, "GrupoUsuario", idGrupoUsuario)
    db.commit()
    _notify(EmailEventType.ELIMINADO_GRUPO, relation.usuario, nombreGrupo=membership.group.nombre, fechaEvento=now)


def leaveGroup(db: Session, actor: User, idGrupo: uuid.UUID) -> None:
    """Salida voluntaria. El administrador debe transferir antes el rol si hay otros integrantes; si es el único,
    corresponde eliminar el grupo. Sus perfiles y mediciones no se tocan."""
    membership = requireMembership(db, actor, idGrupo)
    if membership.isAdmin:
        if _activeCount(db, idGrupo) > 1:
            raise AuthError("TRANSFERENCIA_REQUERIDA",
                            "Antes de abandonar el grupo designá a otro integrante como administrador.")
        raise AuthError("ELIMINACION_REQUERIDA", "Sos el único integrante: en lugar de abandonarlo, eliminá el grupo.")
    now = nowForDb()
    _end(membership.relation, now)
    registerEvent(db, "PERMISO", "ABANDONAR_GRUPO", True, actor.idUsuario, "GrupoUsuario",
                  membership.relation.idGrupoUsuario)
    db.commit()
    _notify(EmailEventType.MIEMBRO_ABANDONO_GRUPO, _admin(db, idGrupo), nombreIntegrante=_fullName(actor),
            nombreGrupo=membership.group.nombre, fechaEvento=now)


def transferAdmin(db: Session, actor: User, idGrupo: uuid.UUID, idGrupoUsuario: uuid.UUID) -> FamilyGroupDetail:
    """Designa otro integrante ACTIVO como administrador en una transacción: nunca queda el grupo sin administrador
    (UX_GrupoUsuario_administrador impide además que queden dos)."""
    membership = requireMembership(db, actor, idGrupo, admin=True)
    target = db.get(GroupUser, idGrupoUsuario)
    if (target is None or target.idGrupo != idGrupo or target.estadoRelacion != ACTIVO
            or target.idGrupoUsuario == membership.relation.idGrupoUsuario):
        raise AuthError("MIEMBRO_NO_ENCONTRADO", "Elegí un integrante activo del grupo.")
    now = nowForDb()
    try:
        # Primero se libera el rol actual y después se asigna: el índice filtrado admite un solo administrador.
        demoted = db.execute(
            update(GroupUser)
            .where(GroupUser.idGrupoUsuario == membership.relation.idGrupoUsuario, GroupUser.rolGrupo == ROL_ADMIN,
                   GroupUser.estadoRelacion == ACTIVO)
            .values(rolGrupo=ROL_MIEMBRO).execution_options(synchronize_session=False)
        ).rowcount
        promoted = db.execute(
            update(GroupUser)
            .where(GroupUser.idGrupoUsuario == idGrupoUsuario, GroupUser.estadoRelacion == ACTIVO)
            .values(rolGrupo=ROL_ADMIN).execution_options(synchronize_session=False)
        ).rowcount
        if demoted != 1 or promoted != 1:
            db.rollback()
            raise AuthError("MIEMBRO_NO_ENCONTRADO", "La administración cambió mientras tanto. Volvé a intentarlo.")
        registerEvent(db, "PERMISO", "TRANSFERIR_ADMINISTRACION_GRUPO", True, actor.idUsuario, "GrupoUsuario",
                      idGrupoUsuario)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise AuthError("MIEMBRO_NO_ENCONTRADO", "La administración cambió mientras tanto. Volvé a intentarlo.") from error
    db.expire_all()
    newAdmin = db.get(User, target.idUsuario)
    _notify(EmailEventType.ADMIN_GRUPO_ASIGNADO, newAdmin, nombreGrupo=membership.group.nombre, fechaEvento=now)
    return getDetail(db, actor, idGrupo)


def deleteGroup(db: Session, actor: User, idGrupo: uuid.UUID, confirmacionNombre: str) -> None:
    """Baja lógica (CERRADO): vínculos e invitaciones a BAJA y compartición revocada. Cuentas, perfiles y mediciones
    de los integrantes no se modifican (el grupo no es dueño de ningún dato)."""
    membership = requireMembership(db, actor, idGrupo, admin=True)
    group = membership.group
    if confirmacionNombre.strip().casefold() != group.nombre.strip().casefold():
        raise AuthError("CONFIRMACION_INVALIDA", "Escribí el nombre exacto del grupo para confirmar.")
    now = nowForDb()
    members = db.scalars(
        select(User).join(GroupUser, GroupUser.idUsuario == User.idUsuario)
        .where(GroupUser.idGrupo == idGrupo, GroupUser.estadoRelacion == ACTIVO, User.idUsuario != actor.idUsuario)
    ).all()
    result = db.execute(
        update(Group).where(Group.idGrupo == idGrupo, Group.estado == GRUPO_ACTIVO)
        .values(estado=GRUPO_ELIMINADO, fechaActualizacion=now).execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        db.rollback()
        raise AuthError("GRUPO_NO_ENCONTRADO", "No encontramos ese grupo entre los tuyos.")
    ended = db.execute(
        update(GroupUser).where(GroupUser.idGrupo == idGrupo, GroupUser.estadoRelacion != BAJA)
        .values(estadoRelacion=BAJA, fechaBaja=now, **{field: False for field in SHARING_FIELDS})
        .execution_options(synchronize_session=False)
    ).rowcount
    registerEvent(db, "CRUD", "ELIMINAR_GRUPO", True, actor.idUsuario, "Grupo", idGrupo,
                  datosPrevios={"estado": GRUPO_ACTIVO}, datosNuevos={"estado": GRUPO_ELIMINADO, "vinculosDadosDeBaja": ended})
    db.commit()
    for member in members:
        _notify(EmailEventType.GRUPO_ELIMINADO, member, nombreGrupo=group.nombre, fechaEvento=now)
    # Quien eliminó el grupo recibe su propia confirmación (no el aviso que reciben los demás integrantes).
    _notify(EmailEventType.GRUPO_ELIMINADO_CONFIRMACION, actor, nombreGrupo=group.nombre,
            cantidadIntegrantes=len(members), fechaEvento=now)


# --- Mis permisos de compartición --------------------------------------------------------------


def _ownProfile(db: Session, idUsuario: uuid.UUID) -> MeasurementProfile | None:
    """Único perfil propio de la cuenta individual (nunca perfiles institucionales), si no fue depurado."""
    return db.scalar(
        select(MeasurementProfile).where(
            MeasurementProfile.idUsuario == idUsuario, MeasurementProfile.tipoPerfil == TIPO_INDIVIDUAL,
            MeasurementProfile.fechaDepuracionDatosPersonales.is_(None),
        )
    )


def getMySharing(db: Session, actor: User, idGrupo: uuid.UUID) -> MySharingRead:
    relation = requireMembership(db, actor, idGrupo).relation
    profile = _ownProfile(db, actor.idUsuario)
    return MySharingRead(
        **{field: getattr(relation, field) for field in SHARING_FIELDS},
        idPerfilMedicion=profile.idPerfilMedicion if profile else None, perfilDisponible=profile is not None,
    )


def updateMySharing(db: Session, actor: User, idGrupo: uuid.UUID, data: SharingSettings) -> MySharingRead:
    """Solo la propia cuenta, sobre su propio vínculo (no se acepta ningún id): nadie cambia permisos ajenos.
    Cada cambio queda como consentimiento en Auditoria (qué, cuándo); revocar rige en la consulta siguiente."""
    relation = requireMembership(db, actor, idGrupo).relation
    previous = {field: bool(getattr(relation, field)) for field in SHARING_FIELDS}
    new = data.model_dump()
    if previous != new:
        for field, value in new.items():
            setattr(relation, field, value)
        accion = "REVOCAR_COMPARTICION_GRUPO" if not any(new.values()) else "CONSENTIMIENTO_COMPARTICION_GRUPO"
        registerEvent(db, "PERMISO", accion, True, actor.idUsuario, "GrupoUsuario", relation.idGrupoUsuario,
                      datosPrevios=previous, datosNuevos=new)
        db.commit()
    return getMySharing(db, actor, idGrupo)


# --- Datos compartidos -------------------------------------------------------------------------


def sharedMembers(db: Session, actor: User, idGrupo: uuid.UUID) -> list[SharedMemberSummary]:
    """Otros integrantes ACTIVOS y qué autorizó cada uno (sin los datos)."""
    membership = requireMembership(db, actor, idGrupo)
    rows = db.execute(
        select(GroupUser, User)
        .join(User, User.idUsuario == GroupUser.idUsuario)
        .where(GroupUser.idGrupo == idGrupo, GroupUser.estadoRelacion == ACTIVO,
               GroupUser.idGrupoUsuario != membership.relation.idGrupoUsuario)
        .order_by(User.nombre, User.apellido)
    ).all()
    return [
        SharedMemberSummary(
            idGrupoUsuario=relation.idGrupoUsuario, nombre=user.nombre, apellido=user.apellido, rol=_role(relation),
            **{field: bool(getattr(relation, field)) for field in SHARING_FIELDS},
            tienePerfil=_ownProfile(db, user.idUsuario) is not None,
        )
        for relation, user in rows
    ]


def _authorize(
    db: Session, actor: User, idGrupo: uuid.UUID, idGrupoUsuario: uuid.UUID, permisos: tuple[str, ...]
) -> tuple[MeasurementProfile, GroupUser]:
    """Verifica en cada consulta: grupo ACTIVO, ambos vínculos ACTIVOS en el mismo grupo y permiso específico vigente
    del dueño de los datos. Sin autorización no se devuelve nada (403); ajenos al grupo: 404."""
    membership = requireMembership(db, actor, idGrupo)
    owner = db.scalar(
        select(GroupUser).where(GroupUser.idGrupoUsuario == idGrupoUsuario).execution_options(populate_existing=True)
    )
    if owner is None or owner.idGrupo != idGrupo or owner.estadoRelacion != ACTIVO:
        raise AuthError("MIEMBRO_NO_ENCONTRADO", "No encontramos ese integrante en el grupo.")
    if owner.idGrupoUsuario == membership.relation.idGrupoUsuario:
        raise AuthError("MIEMBRO_NO_ENCONTRADO", "Tus propios datos se consultan desde tu perfil.")
    permiso = next((name for name in permisos if getattr(owner, name)), None)
    if permiso is None:
        registerEvent(db, "ACCESO", "CONSULTAR_DATOS_GRUPO", False, actor.idUsuario, "GrupoUsuario", idGrupoUsuario,
                      observacion=f"Sin autorización: {permisos[0]}")
        db.commit()
        raise AuthError("DATOS_NO_COMPARTIDOS", "Esta persona no autorizó compartir esta información con el grupo.")
    profile = _ownProfile(db, owner.idUsuario)
    if profile is None:
        raise AuthError("PERFIL_NO_DISPONIBLE", "Esta persona todavía no tiene un perfil de medición.")
    registerEvent(db, "ACCESO", "CONSULTAR_DATOS_GRUPO", True, actor.idUsuario, "GrupoUsuario", idGrupoUsuario,
                  datosNuevos={"permiso": permiso})
    db.commit()
    return profile, owner


def _authorizedProfile(
    db: Session, actor: User, idGrupo: uuid.UUID, idGrupoUsuario: uuid.UUID, permiso: str
) -> MeasurementProfile:
    return _authorize(db, actor, idGrupo, idGrupoUsuario, (permiso,))[0]


def _measurement(row: Measurement) -> SharedMeasurementRead:
    glucose = None
    if row.modoMedicion != measurementService.OXIMETRIA:  # la oximetría no informa glucosa
        glucose = measurementService._evolutionGlucose(row)
    return SharedMeasurementRead(
        idMedicion=row.idMedicion, fechaHoraInicio=row.fechaHoraInicio, modoMedicion=row.modoMedicion, estadoMedicion=row.estadoMedicion,
        condicionComida=row.condicionComida, glucosaEstimada=row.glucosaEstimada, glucosa=glucose,
        glucosaDispositivo=row.glucosaDispositivo, unidadGlucosa=row.unidadGlucosa,
        origenGlucosa=row.origenGlucosa, esDemo=row.origenGlucosa == ORIGEN_DEMO, spo2=row.spo2,
        frecuenciaCardiaca=row.frecuenciaCardiaca,
    )


def _completed(profile: MeasurementProfile, *, experimentalOnly: bool = False):
    """Mediciones COMPLETADAS del perfil del dueño, hayan sido antes o después de crear el grupo (pertenecen a su perfil, no al grupo).
    VISIBILIDAD: incluye las pruebas DEMO (identificadas por `esDemo`). ELEGIBILIDAD estadística: `experimentalOnly=True` las excluye."""
    query = select(Measurement).where(Measurement.idPerfilMedicion == profile.idPerfilMedicion,
                                      Measurement.estadoMedicion == MEDICION_COMPLETADA)
    return query.where(NOT_DEMO) if experimentalOnly else query


def sharedProfile(db: Session, actor: User, idGrupo: uuid.UUID, idGrupoUsuario: uuid.UUID) -> SharedProfileRead:
    profile = _authorizedProfile(db, actor, idGrupo, idGrupoUsuario, "compartePerfil")
    edad = calculateAge(profile.fechaNacimiento, nowForDb().date()) if profile.fechaNacimiento else profile.edadDeclarada
    return SharedProfileRead(edad=edad, sexoModelo=profile.sexoModelo)


def sharedLatest(db: Session, actor: User, idGrupo: uuid.UUID, idGrupoUsuario: uuid.UUID) -> SharedLatestRead:
    """Solo la última medición completada: no habilita el historial."""
    profile = _authorizedProfile(db, actor, idGrupo, idGrupoUsuario, "comparteUltimaMedicion")
    row = db.scalar(_completed(profile).order_by(Measurement.fechaHoraInicio.desc()).limit(1))
    return SharedLatestRead(medicion=_measurement(row) if row else None)


def sharedHistory(
    db: Session, actor: User, idGrupo: uuid.UUID, idGrupoUsuario: uuid.UUID, pagina: int = 1, tamanioPagina: int = 20
) -> SharedHistoryPage:
    profile = _authorizedProfile(db, actor, idGrupo, idGrupoUsuario, "comparteHistorial")
    tamanioPagina = max(1, min(tamanioPagina, MAX_PAGE_SIZE))
    pagina = max(1, pagina)
    query = _completed(profile)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Measurement.fechaHoraInicio.desc())
                      .offset((pagina - 1) * tamanioPagina).limit(tamanioPagina)).all()
    return SharedHistoryPage(items=[_measurement(row) for row in rows], total=total, pagina=pagina,
                             tamanioPagina=tamanioPagina)


def sharedNotices(
    db: Session, actor: User, idGrupo: uuid.UUID, idGrupoUsuario: uuid.UUID, limite: int = 10, pagina: int = 1
) -> SharedNoticesRead:
    """Aviso de medición: solo fecha y hora de las mediciones completadas. Lo autoriza ÚNICAMENTE `notificaMedicion`
    (independiente de «última medición» e «historial»); nunca devuelve valores, modo, estado ni identificadores."""
    profile = _authorizedProfile(db, actor, idGrupo, idGrupoUsuario, "notificaMedicion")
    limite = max(1, min(limite, MAX_PAGE_SIZE))
    pagina = max(1, pagina)
    where = (Measurement.idPerfilMedicion == profile.idPerfilMedicion, Measurement.estadoMedicion == MEDICION_COMPLETADA)
    total = db.scalar(select(func.count()).select_from(Measurement).where(*where)) or 0
    moments = db.scalars(select(Measurement.fechaHoraInicio).where(*where)
                         .order_by(Measurement.fechaHoraInicio.desc()).offset((pagina - 1) * limite).limit(limite)).all()
    return SharedNoticesRead(items=[SharedNoticeRead(fechaHoraInicio=moment) for moment in moments], total=total)


def sharedStatistics(
    db: Session, actor: User, idGrupo: uuid.UUID, idGrupoUsuario: uuid.UUID, dias: int = 30
) -> SharedStatisticsRead:
    """Solo agregados del período (promedios, mínimos, máximos y serie diaria): no expone registros individuales."""
    if dias not in STATISTICS_DAYS:
        raise AuthError("PERIODO_INVALIDO", "El período debe ser de 7, 30 o 90 días.")
    # Agregados del historial: los autoriza el mismo permiso que los registros. Sin historial, no hay estadísticas.
    profile = _authorizedProfile(db, actor, idGrupo, idGrupoUsuario, "comparteHistorial")
    statistics = measurementService.buildStatistics(db, profile.idPerfilMedicion, dias)  # solo experimentales: sin DEMO
    # Las pruebas DEMO se informan APARTE (conteo y puntos identificados), nunca dentro de los promedios.
    demo = db.scalars(_completed(profile).where(Measurement.origenGlucosa == ORIGEN_DEMO,
                                                Measurement.fechaHoraInicio >= nowForDb() - timedelta(days=dias))
                      .order_by(Measurement.fechaHoraInicio.desc()).limit(MAX_DEMO_POINTS)).all()
    # Cada medición experimental del período con su fecha y hora completas: el mismo permiso (historial) que autoriza los agregados.
    recent = db.scalars(_completed(profile, experimentalOnly=True)
                        .where(Measurement.fechaHoraInicio >= nowForDb() - timedelta(days=dias))
                        .order_by(Measurement.fechaHoraInicio.desc()).limit(MAX_SHARED_POINTS)).all()
    statistics.puntos = [SharedEvolutionPoint(
        idMedicion=row.idMedicion, fecha=row.fechaHoraInicio, modoMedicion=row.modoMedicion, origen=row.origenGlucosa,
        frecuenciaCardiaca=row.frecuenciaCardiaca, spo2=float(row.spo2) if row.spo2 is not None else None,
        glucosa=measurementService._evolutionGlucose(row) if row.modoMedicion != measurementService.OXIMETRIA else None,
        indiceOptico=float(row.indiceOptico) if row.indiceOptico is not None else None)
        for row in reversed(recent)]
    statistics.pruebasDemo = len(demo)
    statistics.puntosDemo = [SharedDemoPoint(
        idMedicion=row.idMedicion, fecha=row.fechaHoraInicio, frecuenciaCardiaca=row.frecuenciaCardiaca,
        spo2=float(row.spo2) if row.spo2 is not None else None,
        glucosa=float(row.glucosaDispositivo) if row.glucosaDispositivo is not None else None,
        indiceOptico=float(row.indiceOptico) if row.indiceOptico is not None else None) for row in reversed(demo)]
    return statistics


def sharedMeasurement(db: Session, actor: User, idGrupo: uuid.UUID, idGrupoUsuario: uuid.UUID,
                      idMedicion: uuid.UUID) -> SharedMeasurementDetail:
    """Vista ampliada de UNA medición compartida. Vuelve a verificar la autorización en cada consulta: con `comparteHistorial` cualquier medición
    completada del dueño; con solo `comparteUltimaMedicion`, únicamente la última. Una medición de otra persona, no completada o ajena al
    perfil responde como inexistente; nunca se reutiliza la ruta privada del dueño."""
    profile, owner = _authorize(db, actor, idGrupo, idGrupoUsuario, ("comparteHistorial", "comparteUltimaMedicion"))
    row = db.scalar(_completed(profile).where(Measurement.idMedicion == idMedicion))
    if row is None:
        raise AuthError("MEDICION_NO_ENCONTRADA", "No encontramos esa medición entre las compartidas.")
    latest = db.scalar(_completed(profile).order_by(Measurement.fechaHoraInicio.desc()).limit(1))
    isLatest = latest is not None and latest.idMedicion == row.idMedicion
    if not owner.comparteHistorial and not isLatest:
        raise AuthError("DATOS_NO_COMPARTIDOS", "Esta persona no autorizó compartir esta información con el grupo.")
    return SharedMeasurementDetail(**_measurement(row).model_dump(), fechaHoraFin=row.fechaHoraFin, indiceOptico=row.indiceOptico,
                                   duracionMs=row.duracionMs, lecturasEstabilizadas=row.lecturasEstabilizadas, esUltima=isLatest)
