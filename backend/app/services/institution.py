# Institution - Instituciones, roles institucionales e invitaciones
#
# Tipo de cuenta y rol institucional son conceptos distintos:
#   Usuario.tipoCuenta = USUARIO_INSTITUCIONAL          -> la cuenta puede trabajar con instituciones;
#   InstitucionUsuario.rolInstitucion (por institución) -> PROPIETARIO | MODERADOR | OPERADOR.
# Una cuenta institucional puede tener 0..N instituciones y una institución, 0..N cuentas: una fila de
# InstitucionUsuario por vínculo, con su rol. No se crea una tabla por tipo de miembro.
#
# Jerarquía:
#   PROPIETARIO: crea la institución, modifica sus datos, invita y revoca moderadores, supervisa y
#                desvincula operadores, elimina (lógicamente) la institución.
#   MODERADOR:   designado por el propietario; invita, consulta y desvincula operadores.
#   OPERADOR:    incorporado por un moderador; usa los módulos institucionales autorizados.
#
# Incorporación por invitación con aceptación del destinatario (InstitucionUsuario.estadoRelacion):
#   PENDIENTE (invitación, vence a los INVITATION_VALIDITY_DAYS) -> ACTIVO (la acepta la propia cuenta
#   invitada, autenticada) o BAJA (rechazo, cancelación, revocación, vencimiento o institución eliminada).
# Solo se invitan cuentas USUARIO_INSTITUCIONAL ACTIVAS (correo verificado), buscadas por correo exacto.
# Nunca se cambia el tipo de una cuenta. UX_InstitucionUsuario_vinculoVigente impide vínculos duplicados.
#
# Autorización: en cada operación se resuelve el vínculo ACTIVO de la cuenta autenticada con una institución
# ACTIVA; el rol sale de la base, nunca del cliente. Como no viaja en el token, un cambio de rol, una baja o la
# eliminación de la institución rigen de inmediato también para sesiones ya iniciadas.
#
# Eliminación lógica (solo PROPIETARIO, con reautenticación): Institucion.estado = CERRADA (con fechaActualizacion;
# fecha y responsable también en Auditoria ELIMINAR_INSTITUCION). El CUIT queda reservado por
# UQ_Institucion_identificadorLegal. Todos los vínculos e invitaciones pasan a BAJA, se cancelan las transferencias
# pendientes y se liberan los dispositivos a cargo de sus miembros. Los perfiles de pacientes quedan sin acceso
# operativo y con PerfilMedicion.fechaExpiracionDatosPersonales = cierre + 12 meses: el fin de la conservación vive
# en cada perfil (no se duplica en Institucion) y al vencer los desidentifica app/jobs/purgeInstitutionalRetention.py.
# Las cuentas personales de los miembros no se modifican.

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.exceptions import AuthError
from app.emails.eventTypes import EmailEventType
from app.models.accountToken import AccountToken, TipoTokenCuenta
from app.models.device import Device
from app.models.externalIdentity import ExternalIdentity
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.localCredential import LocalCredential
from app.models.measurementProfile import MeasurementProfile
from app.models.profileTransfer import ProfileTransfer
from app.models.user import User
from app.schemas.institution import (
    MEMBER_ADMIN_FIELDS,
    InstitutionCreateRequest,
    InstitutionDeletionRequest,
    InstitutionDetail,
    InstitutionReopenRequest,
    InstitutionUpdateRequest,
    InvitationRead,
    QuotaRead,
    LegalIdStatus,
    MemberCandidate,
    MemberRead,
    MyInstitutionRead,
    PersonSummary,
    ReopenPreview,
)
from app.services import accountGrace, reassignments
from app.services import auth as authService
from app.services import email as emailService
from app.services import mfa
from app.services import notifications
from app.services import quota, schemaCompat
from app.services.audit import registerEvent
from app.services.rateLimiter import RateLimiter
from app.services import invitedAccounts
from app.services.invitedAccounts import isInvitedPendingAccount
from app.utils.dbRetry import retryOnDeadlock
from app.utils.normalizers import normalizeProperName
from app.utils.timeZone import nowForDb

logger = logging.getLogger(__name__)

TIPO_INSTITUCIONAL = "USUARIO_INSTITUCIONAL"
ROL_PROPIETARIO = "PROPIETARIO"
ROL_MODERADOR = "MODERADOR"
ROL_OPERADOR = "OPERADOR"
RELACION_PENDIENTE = "PENDIENTE"
RELACION_ACTIVO = "ACTIVO"
RELACION_BAJA = "BAJA"
INSTITUCION_ACTIVA = "ACTIVA"
# Valor de CK_Institucion_estado que representa la eliminación lógica.
INSTITUCION_ELIMINADA = "CERRADA"
ORIGEN_CREACION_INSTITUCION = "CREACION_INSTITUCION"
ORIGEN_INVITACION = "INVITACION"
TRANSFERENCIA_PENDIENTE = "PENDIENTE"
TRANSFERENCIA_CANCELADA = "CANCELADA"

INVITATION_VALIDITY_DAYS = invitedAccounts.INVITATION_VALIDITY_DAYS

# --- Matriz de permisos --------------------------------------------------------------------

P_CONSULTAR = "CONSULTAR_INSTITUCION"
P_MODIFICAR = "MODIFICAR_INSTITUCION"
P_MODERADORES = "GESTIONAR_MODERADORES"
P_INCORPORAR_OPERADORES = "INCORPORAR_OPERADORES"
P_ADMINISTRAR_OPERADORES = "ADMINISTRAR_OPERADORES"
P_EQUIPO = "CONSULTAR_EQUIPO"
P_ELIMINAR = "ELIMINAR_INSTITUCION"
# Pacientes (app/services/institutionPatients.py). GESTIONAR: alta, modificación y asignación de responsable
# (un operador solo modifica los pacientes a su cargo); BAJA: baja lógica del paciente.
P_PACIENTES = "CONSULTAR_PACIENTES"
P_GESTIONAR_PACIENTES = "GESTIONAR_PACIENTES"
P_BAJA_PACIENTES = "BAJA_PACIENTES"
# Matrices de estimación (app/services/matrix.py). GESTIONAR: crear versiones, editar borradores y activar la matriz
# institucional (propietario y moderador); CONSULTAR: ver cuál matriz se aplica (todos los integrantes).
P_MATRICES = "GESTIONAR_MATRICES"
# Auditoría de la institución: solo el PROPIETARIO la consulta (app/services/auditQuery.py).
P_AUDITORIA = "CONSULTAR_AUDITORIA"
# Inventario de dispositivos (app/services/device.py). CONSULTAR: todos los integrantes (el operador, con datos mínimos);
# GESTIONAR: alta, edición, estados y responsable (propietario y moderador); RETIRAR: desvincular y descomisionar
# (solo el propietario).
P_DISPOSITIVOS = "CONSULTAR_DISPOSITIVOS"
P_DISPOSITIVOS_GESTIONAR = "GESTIONAR_DISPOSITIVOS"
P_DISPOSITIVOS_RETIRAR = "RETIRAR_DISPOSITIVOS"
P_MATRIZ = "CONSULTAR_MATRIZ"

_PATIENTS_ALL = (P_PACIENTES, P_GESTIONAR_PACIENTES, P_BAJA_PACIENTES)
ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    ROL_PROPIETARIO: (P_CONSULTAR, P_MODIFICAR, P_MODERADORES, P_ADMINISTRAR_OPERADORES, P_EQUIPO, P_ELIMINAR,
                      *_PATIENTS_ALL, P_MATRICES, P_MATRIZ, P_AUDITORIA, P_DISPOSITIVOS, P_DISPOSITIVOS_GESTIONAR,
                      P_DISPOSITIVOS_RETIRAR),
    ROL_MODERADOR: (P_CONSULTAR, P_INCORPORAR_OPERADORES, P_ADMINISTRAR_OPERADORES, P_EQUIPO, *_PATIENTS_ALL,
                    P_MATRICES, P_MATRIZ, P_DISPOSITIVOS, P_DISPOSITIVOS_GESTIONAR),
    # El operador no administra personal: consulta la institución y gestiona pacientes.
    ROL_OPERADOR: (P_CONSULTAR, P_PACIENTES, P_GESTIONAR_PACIENTES, P_MATRIZ, P_DISPOSITIVOS),
}

RETENTION_MONTHS = 12
# Rol que invita cada rol (el propietario designa moderadores; los moderadores incorporan operadores).
INVITE_PERMISSION = {ROL_MODERADOR: P_MODERADORES, ROL_OPERADOR: P_INCORPORAR_OPERADORES}
# Permiso para revocar o cancelar vínculos de cada rol.
REVOKE_PERMISSION = {ROL_MODERADOR: P_MODERADORES, ROL_OPERADOR: P_ADMINISTRAR_OPERADORES}

INSTITUTION_LEGAL_ID_UNIQUE = "UQ_Institucion_identificadorLegal"
MEMBER_UNIQUE_INDEX = "UX_InstitucionUsuario_vinculoVigente"  # 008_vinculo_institucional_unico.sql
USER_EMAIL_UNIQUE_INDEX = "UX_Usuario_correoElectronico"

LEGAL_ID_TAKEN_MESSAGE = "Ya existe una institución activa registrada con este CUIT."
CLOSED_REOPENABLE_MESSAGE = "Esta institución se encuentra cerrada. Completá sus nuevos datos para reabrirla."
ADMIN_CLOSED_MESSAGE = (
    "La administración de GlucoLume cerró esta institución. No se puede reabrir desde la cuenta: comunicate con el soporte de GlucoLume."
)
CLOSED_NOT_AUTHORIZED_MESSAGE = (
    "Hay una institución cerrada registrada con este CUIT. Solo quien fue su último propietario puede solicitar "
    "la reapertura; conocer el CUIT no alcanza para representarla."
)
NOT_FOUND_ACCOUNT_MESSAGE = (
    "No existe actualmente una cuenta institucional registrada con este correo en GlucoLume. "
    "Para incorporarse, la persona primero debe crear su cuenta institucional."
)
PERSONAL_ACCOUNT_MESSAGE = (
    "El correo ingresado no corresponde a una cuenta institucional. "
    "Para ser incorporado, el usuario debe contar con una cuenta institucional válida, no personal."
)
EXISTING_MEMBER_MESSAGE = "Este usuario ya se encuentra vinculado a la institución."
PENDING_INVITATION_MESSAGE = "Este usuario ya tiene una invitación pendiente de esta institución."

# Búsquedas e invitaciones por cuenta: evita usar la búsqueda para recorrer correos.
LOOKUP_LIMIT_MAX = 20
LOOKUP_LIMIT_WINDOW_SECONDS = 10 * 60
_lookupLimiter = RateLimiter(LOOKUP_LIMIT_MAX, LOOKUP_LIMIT_WINDOW_SECONDS, name="institucion:consulta")


@dataclass(frozen=True)
class Membership:
    institution: Institution
    relation: InstitutionUser

    @property
    def role(self) -> str:
        return self.relation.rolInstitucion

    @property
    def permissions(self) -> tuple[str, ...]:
        return ROLE_PERMISSIONS.get(self.role, ())

    def can(self, permission: str) -> bool:
        return permission in self.permissions


def _violates(error: IntegrityError, constraint: str, column: str) -> bool:
    """SQL Server informa el nombre de la restricción; SQLite, la columna (pruebas)."""
    message = str(error.orig).lower()
    return constraint.lower() in message or ("unique constraint failed" in message and column.lower() in message)


_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def addMonths(value: datetime, months: int) -> datetime:
    """Suma meses calendario (29/02 + 12 meses -> 28/02), igual que DATEADD(MONTH, ...) de SQL Server."""
    index = value.month - 1 + months
    year, month = value.year + index // 12, index % 12 + 1
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    lastDay = 29 if month == 2 and leap else _MONTH_DAYS[month - 1]
    return value.replace(year=year, month=month, day=min(value.day, lastDay))


def _legalIdTaken() -> AuthError:
    return AuthError("INSTITUCION_REGISTRADA", LEGAL_ID_TAKEN_MESSAGE)


def _forbidden(message: str = "Tu rol en esta institución no permite realizar esta operación.") -> AuthError:
    return AuthError("PERMISO_INSUFICIENTE", message)


def _requireInstitutionalAccount(user: User) -> None:
    if user.tipoCuenta != TIPO_INSTITUCIONAL:
        raise _forbidden("Solo una cuenta institucional puede crear o gestionar instituciones.")


def _fullName(user: User | None) -> str | None:
    if user is None:
        return None
    return " ".join(part for part in (user.nombre, user.apellido) if part) or user.usuario


def _invitationExpiry(relation: InstitutionUser) -> datetime:
    return relation.fechaInvitacion + timedelta(days=INVITATION_VALIDITY_DAYS)


def _isExpiredInvitation(relation: InstitutionUser, now: datetime) -> bool:
    return relation.estadoRelacion == RELACION_PENDIENTE and _invitationExpiry(relation) <= now


def lockRelation(db: Session, idInstitucionUsuario: uuid.UUID) -> InstitutionUser | None:
    """Relee el vínculo con bloqueo de fila hasta el commit: serializa la desvinculación de un operador con las altas y reasignaciones que lo
    eligen como responsable (así no queda un paciente asignado a un operador que se está yendo). SQLAlchemy ignora with_for_update en SQL
    Server: se usa el hint de tabla. Con populate_existing el objeto ya cargado se actualiza (la sesión no expira al confirmar)."""
    return db.execute(
        select(InstitutionUser)
        .where(InstitutionUser.idInstitucionUsuario == idInstitucionUsuario)
        .with_hint(InstitutionUser, "WITH (UPDLOCK, ROWLOCK)", "mssql")
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalars().first()


def _endRelation(relation: InstitutionUser, now: datetime) -> None:
    relation.estadoRelacion = RELACION_BAJA
    relation.fechaBaja = now


INSTITUCION_PAUSADA = "INACTIVA"
PAUSED_MESSAGE = ("La institución está pausada por la administración de GlucoLume: sus funciones no están disponibles hasta que se reactive. "
                  "Comunicate con el soporte de GlucoLume.")


def requireMembership(db: Session, actor: User, idInstitucion: uuid.UUID, permission: str | None = None) -> Membership:
    """Vínculo ACTIVO de la cuenta autenticada con una institución ACTIVA y, opcionalmente, un permiso.

    Para quien no pertenece (o si la institución fue eliminada) responde como inexistente: no revela qué
    instituciones existen. Sin el permiso pedido: PERMISO_INSUFICIENTE (403). Punto único de autorización
    para los módulos institucionales.

    Una institución PAUSADA (INACTIVA) rechaza TODO contexto institucional de sus integrantes con INSTITUCION_PAUSADA (403), en cada pedido y
    con cualquier token ya emitido: el estado se lee de la base, no de la sesión. Quien no pertenece sigue recibiendo «inexistente».
    Solo se bloquea esa institución: las demás de la misma persona no se tocan.
    """
    _requireInstitutionalAccount(actor)
    row = db.execute(
        select(Institution, InstitutionUser)
        .join(InstitutionUser, InstitutionUser.idInstitucion == Institution.idInstitucion)
        .where(
            Institution.idInstitucion == idInstitucion,
            Institution.estado.in_((INSTITUCION_ACTIVA, INSTITUCION_PAUSADA)),
            InstitutionUser.idUsuarioInvitado == actor.idUsuario,
            InstitutionUser.estadoRelacion == RELACION_ACTIVO,
        )
    ).first()
    if row is None:
        raise AuthError("INSTITUCION_NO_ENCONTRADA", "No encontramos esa institución entre las tuyas.")
    if row[0].estado == INSTITUCION_PAUSADA:
        raise AuthError("INSTITUCION_PAUSADA", PAUSED_MESSAGE)
    membership = Membership(*row)
    if permission is not None and not membership.can(permission):
        raise _forbidden()
    return membership


# --- Crear, consultar y modificar -----------------------------------------------------------


def _byLegalId(db: Session, identificadorLegal: str) -> Institution | None:
    # populate_existing: el estado se lee siempre de la base, aunque la sesión ya tenga la instancia (los cierres y
    # reaperturas se aplican con UPDATE directos que no sincronizan la sesión).
    return db.scalar(
        select(Institution)
        .where(Institution.identificadorLegal == identificadorLegal)
        .execution_options(populate_existing=True)
    )


def _lastOwnerId(db: Session, idInstitucion: uuid.UUID) -> uuid.UUID | None:
    """Cuenta del último PROPIETARIO de la institución (su vínculo queda en BAJA al cerrarla)."""
    return db.scalar(
        select(InstitutionUser.idUsuarioInvitado)
        .where(InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.rolInstitucion == ROL_PROPIETARIO)
        .order_by(InstitutionUser.fechaIncorporacion.desc(), InstitutionUser.fechaInvitacion.desc())
        .limit(1)
    )


def isAdministrativeClosure(db: Session, institution: Institution) -> bool:
    """¿La institución CERRADA fue eliminada por la administración de la plataforma? Se lee de la fila, que es la fuente
    de verdad (no de la auditoría, que la política de conservación puede depurar). Sin la migración no puede haber cierres administrativos."""
    if institution.estado != INSTITUCION_ELIMINADA or not schemaCompat.administrativeClosureReady(db):
        return False
    table = Institution.__table__
    return bool(db.scalar(select(table.c.cierreAdministrativo).where(table.c.idInstitucion == institution.idInstitucion)))


def canReopen(db: Session, user: User, institution: Institution) -> bool:
    """Autorización de representación, verificada automáticamente en la misma operación (sin solicitudes ni
    aprobaciones): solo la cuenta institucional que fue el último PROPIETARIO de la institución CERRADA puede
    reabrirla. Es la representación que consta en los registros de GlucoLume (InstitucionUsuario); conocer el CUIT no
    la prueba. Cualquier otra cuenta se rechaza sin generar nada pendiente.

    Una institución eliminada por la administración de la plataforma NO se puede reabrir desde la cuenta, ni siquiera por su último propietario.
    El cierre pedido por el propietario no cambia en nada.
    """
    return (
        user.tipoCuenta == TIPO_INSTITUCIONAL
        and institution.estado == INSTITUCION_ELIMINADA
        and _lastOwnerId(db, institution.idInstitucion) == user.idUsuario
        and not isAdministrativeClosure(db, institution)
    )


def _administrativeClosureFor(db: Session, user: User, institution: Institution) -> bool:
    """El cierre administrativo solo se le explica a quien la representaba (último propietario); a cualquier otra cuenta se le responde lo mismo
    que ante cualquier institución cerrada ajena, sin revelar nada."""
    return (user.tipoCuenta == TIPO_INSTITUCIONAL and _lastOwnerId(db, institution.idInstitucion) == user.idUsuario
            and isAdministrativeClosure(db, institution))


def _existingLegalIdError(db: Session, user: User, institution: Institution) -> AuthError:
    if institution.estado != INSTITUCION_ELIMINADA:
        return _legalIdTaken()
    if canReopen(db, user, institution):
        return AuthError("INSTITUCION_CERRADA", CLOSED_REOPENABLE_MESSAGE)
    if _administrativeClosureFor(db, user, institution):
        return AuthError("INSTITUCION_CERRADA_ADMINISTRATIVAMENTE", ADMIN_CLOSED_MESSAGE)
    return AuthError("INSTITUCION_CERRADA", CLOSED_NOT_AUTHORIZED_MESSAGE)


def checkLegalId(db: Session, user: User, tipoIdentificadorLegal: str, identificadorLegal: str) -> LegalIdStatus:
    """Estado de un CUIT antes de crear: DISPONIBLE, ACTIVA o CERRADA (y si la cuenta puede reabrirla).

    Solo revela los datos de una institución cerrada a quien está autorizado a reabrirla. Limitado por cuenta.
    """
    _requireInstitutionalAccount(user)
    _limitLookups(user)
    institution = _byLegalId(db, identificadorLegal)
    if institution is None:
        return LegalIdStatus(estado="DISPONIBLE")
    if institution.estado != INSTITUCION_ELIMINADA:
        return LegalIdStatus(estado="ACTIVA", mensaje=LEGAL_ID_TAKEN_MESSAGE)
    if not canReopen(db, user, institution):
        message = ADMIN_CLOSED_MESSAGE if _administrativeClosureFor(db, user, institution) else CLOSED_NOT_AUTHORIZED_MESSAGE
        return LegalIdStatus(estado="CERRADA", mensaje=message)
    return LegalIdStatus(
        estado="CERRADA", puedeReabrir=True, mensaje=CLOSED_REOPENABLE_MESSAGE,
        institucion=ReopenPreview(
            nombre=institution.nombre, tipoInstitucion=institution.tipoInstitucion,
            descripcion=institution.descripcion, cantidadReaperturas=institution.cantidadReaperturas,
        ),
    )


def createInstitution(db: Session, user: User, data: InstitutionCreateRequest) -> Institution:
    """La cuenta institucional autenticada crea una institución y queda como su PROPIETARIO (una transacción).

    El nombre puede repetirse; el CUIT no: si ya existe una institución ACTIVA se rechaza, y si existe una CERRADA
    no se crea otra (se informa que corresponde reabrirla). Ante dos solicitudes simultáneas con el mismo CUIT, la
    restricción de SQL Server rechaza la segunda.
    """
    _requireInstitutionalAccount(user)
    existing = _byLegalId(db, data.identificadorLegal)
    if existing is not None:
        raise _existingLegalIdError(db, user, existing)
    now = nowForDb()
    locked = accountGrace.lockUser(db, user.idUsuario)  # serializa con la eliminación automática de la cuenta
    if locked is None or locked.estado != "ACTIVO":
        db.rollback()
        raise AuthError("CUENTA_NO_ACTIVA", "La cuenta no está activa.")
    institution = Institution(
        tipoIdentificadorLegal=data.tipoIdentificadorLegal,
        identificadorLegal=data.identificadorLegal,
        nombre=data.nombre,
        tipoInstitucion=data.tipoInstitucion,
        descripcion=data.descripcion,
        estado=INSTITUCION_ACTIVA,
    )
    try:
        db.add(institution)
        db.flush()
        db.add(
            InstitutionUser(
                idInstitucion=institution.idInstitucion,
                idUsuarioInvitado=user.idUsuario,
                rolInstitucion=ROL_PROPIETARIO,
                estadoRelacion=RELACION_ACTIVO,
                origenVinculo=ORIGEN_CREACION_INSTITUCION,
                fechaInvitacion=now,
                fechaIncorporacion=now,
            )
        )
        registerEvent(
            db, "CRUD", "CREAR_INSTITUCION", True, user.idUsuario, "Institucion", institution.idInstitucion,
            datosNuevos={"estado": INSTITUCION_ACTIVA, "rolResponsable": ROL_PROPIETARIO, "cantidadReaperturas": 0},
        )
        accountGrace.cancelOnIncorporation(db, user, now)  # quedó como propietario: vinculación efectiva
        accountGrace.confirmStillActive(db, user.idUsuario, now)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if _violates(error, INSTITUTION_LEGAL_ID_UNIQUE, "identificadorLegal"):
            existing = _byLegalId(db, data.identificadorLegal)
            raise (_existingLegalIdError(db, user, existing) if existing else _legalIdTaken()) from error
        raise
    # Después del commit: un fallo de SMTP queda auditado y no revierte la institución.
    notifications.notifyInstitutionCreated(db, user, institution, fecha=now)
    return institution


def resendCreationNotice(db: Session, actor: User, idInstitucion: uuid.UUID) -> None:
    """Reintenta la confirmación de registro (solo el propietario, solo si no se envió)."""
    membership = requireMembership(db, actor, idInstitucion, "ELIMINAR_INSTITUCION")
    if not notifications.resend(db, actor, notifications.ACCION_INSTITUCION, idInstitucion,
                                notifications.notifyInstitutionCreated, membership.institution):
        raise AuthError("NOTIFICACION_NO_ENVIADA", notifications.NOT_SENT_MESSAGE)


def reopenInstitution(db: Session, user: User, data: InstitutionReopenRequest) -> Institution:
    """Reabre la institución CERRADA del CUIT indicado, en una sola transacción, conservando su registro.

    Mantiene idInstitucion, CUIT, fechaCreacion, auditoría, vínculos dados de baja y perfiles archivados (con su
    retención). Actualiza los datos administrativos, pasa a ACTIVA, incrementa cantidadReaperturas y fija
    fechaUltimaReapertura (inicio del período operativo vigente). Crea un vínculo PROPIETARIO nuevo para el período;
    no restaura moderadores, operadores, invitaciones ni permisos anteriores.
    """
    _requireInstitutionalAccount(user)
    institution = _byLegalId(db, data.identificadorLegal)
    if institution is None:
        raise AuthError("INSTITUCION_NO_ENCONTRADA", "No hay una institución cerrada registrada con este CUIT.")
    if institution.estado != INSTITUCION_ELIMINADA:
        raise _legalIdTaken()
    if not canReopen(db, user, institution):
        administrative = _administrativeClosureFor(db, user, institution)
        registerEvent(db, "PERMISO", "REABRIR_INSTITUCION", False, user.idUsuario, "Institucion",
                      institution.idInstitucion, idInstitucion=institution.idInstitucion,
                      observacion="Motivo: CIERRE_ADMINISTRATIVO" if administrative else "Motivo: REPRESENTACION_NO_VERIFICADA")
        db.commit()
        if administrative:
            raise AuthError("INSTITUCION_CERRADA_ADMINISTRATIVAMENTE", ADMIN_CLOSED_MESSAGE)
        raise AuthError("REPRESENTACION_NO_VERIFICADA", CLOSED_NOT_AUTHORIZED_MESSAGE)
    _reauthenticate(db, user, institution.idInstitucion, data, "REABRIR_INSTITUCION")

    idInstitucion = institution.idInstitucion
    previousCount = institution.cantidadReaperturas
    now = nowForDb()
    locked = accountGrace.lockUser(db, user.idUsuario)
    if locked is None or locked.estado != "ACTIVO":
        db.rollback()
        raise AuthError("CUENTA_NO_ACTIVA", "La cuenta no está activa.")
    try:
        # Condicionado al estado: toma el lock de la fila y vuelve a verificar CERRADA. De dos solicitudes
        # simultáneas, la segunda encuentra la institución ya ACTIVA y no incrementa el contador otra vez.
        result = db.execute(
            update(Institution)
            .where(Institution.idInstitucion == idInstitucion, Institution.estado == INSTITUCION_ELIMINADA)
            .values(
                estado=INSTITUCION_ACTIVA, nombre=data.nombre, tipoInstitucion=data.tipoInstitucion,
                descripcion=data.descripcion, cantidadReaperturas=Institution.cantidadReaperturas + 1,
                fechaUltimaReapertura=now, fechaActualizacion=now,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 0:
            db.rollback()
            raise AuthError("INSTITUCION_REGISTRADA", "La institución ya fue reabierta.")
        db.add(InstitutionUser(
            idInstitucion=idInstitucion, idUsuarioInvitado=user.idUsuario, rolInstitucion=ROL_PROPIETARIO,
            estadoRelacion=RELACION_ACTIVO, origenVinculo=ORIGEN_CREACION_INSTITUCION, fechaInvitacion=now,
            fechaIncorporacion=now,
        ))
        db.flush()
        registerEvent(
            db, "CRUD", "REABRIR_INSTITUCION", True, user.idUsuario, "Institucion", idInstitucion,
            datosPrevios={"estado": INSTITUCION_ELIMINADA, "cantidadReaperturas": previousCount},
            datosNuevos={"estado": INSTITUCION_ACTIVA, "cantidadReaperturas": previousCount + 1,
                         "rolResponsable": ROL_PROPIETARIO},
        )
        accountGrace.cancelOnIncorporation(db, user, now)  # vuelve a ser propietario: vinculación efectiva
        accountGrace.confirmStillActive(db, user.idUsuario, now)
        db.commit()
    except AuthError:
        raise
    except Exception:
        # Cualquier error deshace todo: estado, contador, datos y vínculo nuevo.
        db.rollback()
        raise
    db.refresh(institution)
    return institution


def operatingInstitutionIds(db: Session, user: User) -> set[uuid.UUID]:
    """Instituciones ACTIVAS (no pausadas ni cerradas) donde la cuenta tiene un vínculo ACTIVO: las únicas donde puede operar."""
    return set(db.scalars(
        select(InstitutionUser.idInstitucion).join(Institution, Institution.idInstitucion == InstitutionUser.idInstitucion)
        .where(InstitutionUser.idUsuarioInvitado == user.idUsuario, InstitutionUser.estadoRelacion == RELACION_ACTIVO,
               Institution.estado == INSTITUCION_ACTIVA)))


def isOperating(db: Session, idInstitucion: uuid.UUID) -> bool:
    return db.scalar(select(Institution.idInstitucion).where(Institution.idInstitucion == idInstitucion,
                                                              Institution.estado == INSTITUCION_ACTIVA)) is not None


def listMine(db: Session, user: User, includePaused: bool = False) -> list[MyInstitutionRead]:
    """Instituciones ACTIVAS con las que la cuenta tiene un vínculo ACTIVO, con su rol y permisos en cada una. Con `includePaused` también las
    PAUSADAS (solo para mostrarlas como no disponibles: no se puede operar en ellas)."""
    if user.tipoCuenta != TIPO_INSTITUCIONAL:
        return []
    rows = db.execute(
        select(Institution, InstitutionUser)
        .join(InstitutionUser, InstitutionUser.idInstitucion == Institution.idInstitucion)
        .where(
            InstitutionUser.idUsuarioInvitado == user.idUsuario,
            InstitutionUser.estadoRelacion == RELACION_ACTIVO,
            Institution.estado.in_((INSTITUCION_ACTIVA, INSTITUCION_PAUSADA) if includePaused else (INSTITUCION_ACTIVA,)),
        )
        .order_by(Institution.nombre)
    ).all()
    return [_summary(Membership(institution, relation)) for institution, relation in rows]


def _summary(membership: Membership) -> MyInstitutionRead:
    institution = membership.institution
    return MyInstitutionRead(
        idInstitucion=institution.idInstitucion,
        nombre=institution.nombre,
        tipoInstitucion=institution.tipoInstitucion,
        estado=institution.estado,
        rolInstitucion=membership.role,
        estadoRelacion=membership.relation.estadoRelacion,
        permisos=list(membership.permissions),
    )


def _activeCount(db: Session, idInstitucion: uuid.UUID, rol: str) -> int:
    return db.scalar(
        select(func.count())
        .select_from(InstitutionUser)
        .where(
            InstitutionUser.idInstitucion == idInstitucion,
            InstitutionUser.rolInstitucion == rol,
            InstitutionUser.estadoRelacion == RELACION_ACTIVO,
        )
    )


def institutionRelationIds(idInstitucion: uuid.UUID):
    """Subconsulta de todos los vínculos (cualquier estado) de una institución: los pacientes pertenecen a la
    institución a través de su operador responsable, aunque ese vínculo ya esté de baja."""
    return select(InstitutionUser.idInstitucionUsuario).where(InstitutionUser.idInstitucion == idInstitucion)


def _activePatientCount(db: Session, idInstitucion: uuid.UUID, idResponsable: uuid.UUID | None = None) -> int:
    """Pacientes activos de la institución o, con `idResponsable`, solo los de ese vínculo (el operador cuenta los suyos)."""
    query = (
        select(func.count())
        .select_from(MeasurementProfile)
        .where(
            MeasurementProfile.tipoPerfil == "INSTITUCIONAL",
            MeasurementProfile.idInstitucionUsuarioResponsable.in_(institutionRelationIds(idInstitucion)),
            # Activo: sin período de conservación iniciado (ver app/services/institutionPatients.py).
            MeasurementProfile.fechaExpiracionDatosPersonales.is_(None),
        )
    )
    if idResponsable is not None:
        query = query.where(MeasurementProfile.idInstitucionUsuarioResponsable == idResponsable)
    return db.scalar(query)


def _owner(db: Session, idInstitucion: uuid.UUID) -> PersonSummary | None:
    owner = db.scalar(
        select(User)
        .join(InstitutionUser, InstitutionUser.idUsuarioInvitado == User.idUsuario)
        .where(
            InstitutionUser.idInstitucion == idInstitucion,
            InstitutionUser.rolInstitucion == ROL_PROPIETARIO,
            InstitutionUser.estadoRelacion == RELACION_ACTIVO,
        )
    )
    return PersonSummary(nombre=owner.nombre, apellido=owner.apellido) if owner is not None else None


def getDetail(db: Session, actor: User, idInstitucion: uuid.UUID) -> InstitutionDetail:
    membership = requireMembership(db, actor, idInstitucion, P_CONSULTAR)
    institution = membership.institution
    cupos = quota.usage(db, idInstitucion) if membership.can(P_EQUIPO) else None  # administración: propietario y moderador
    return InstitutionDetail(
        capacidadMaximaUsuarios=cupos.capacidadMaximaUsuarios if cupos else None, usuariosActivos=cupos.usuariosActivos if cupos else None,
        cuposDisponibles=cupos.cuposDisponibles if cupos else None, porcentajeUtilizacion=cupos.porcentajeUtilizacion if cupos else None,
        **_summary(membership).model_dump(),
        tipoIdentificadorLegal=institution.tipoIdentificadorLegal,
        identificadorLegal=institution.identificadorLegal,
        descripcion=institution.descripcion,
        fechaCreacion=institution.fechaCreacion,
        fechaActualizacion=institution.fechaActualizacion,
        propietario=_owner(db, idInstitucion),
        # El operador no recibe estadísticas generales de la institución: solo sus propios pacientes; el equipo lo ve quien lo consulta.
        cantidadModeradores=_activeCount(db, idInstitucion, ROL_MODERADOR) if membership.can(P_EQUIPO) else 0,
        cantidadOperadores=_activeCount(db, idInstitucion, ROL_OPERADOR) if membership.can(P_EQUIPO) else 0,
        cantidadPacientes=(_activePatientCount(db, idInstitucion, None if membership.role != ROL_OPERADOR else membership.relation.idInstitucionUsuario)
                           if membership.can(P_PACIENTES) else 0),
        cantidadReaperturas=institution.cantidadReaperturas,
        fechaUltimaReapertura=institution.fechaUltimaReapertura,
    )


def getQuota(db: Session, actor: User, idInstitucion: uuid.UUID) -> QuotaRead:
    """Cupos de cuentas institucionales de la institución del usuario autenticado (propietario o moderador; el operador, 403)."""
    requireMembership(db, actor, idInstitucion, P_EQUIPO)
    return quota.usage(db, idInstitucion)


def updateInstitution(
    db: Session, actor: User, idInstitucion: uuid.UUID, data: InstitutionUpdateRequest
) -> InstitutionDetail:
    """Solo el PROPIETARIO. Nombre, tipo y descripción; el CUIT no se modifica."""
    institution = requireMembership(db, actor, idInstitucion, P_MODIFICAR).institution
    changes = data.model_dump(exclude_unset=True)
    if "nombre" in changes and not changes["nombre"]:
        raise AuthError("NOMBRE_REQUERIDO", "Ingresá el nombre de la institución.")
    if "tipoInstitucion" in changes and changes["tipoInstitucion"] is None:
        changes.pop("tipoInstitucion")
    previous = {field: getattr(institution, field) for field in changes}
    changed = {field: value for field, value in changes.items() if previous[field] != value}
    if changed:
        for field, value in changed.items():
            setattr(institution, field, value)
        institution.fechaActualizacion = nowForDb()
        registerEvent(
            db, "CRUD", "MODIFICAR_INSTITUCION", True, actor.idUsuario, "Institucion", idInstitucion,
            datosPrevios={field: previous[field] for field in changed}, datosNuevos=changed,
        )
        db.commit()
    return getDetail(db, actor, idInstitucion)


# --- Equipo ---------------------------------------------------------------------------------


_ROLE_ORDER = case(
    (InstitutionUser.rolInstitucion == ROL_PROPIETARIO, 0), (InstitutionUser.rolInstitucion == ROL_MODERADOR, 1), else_=2
)


def listMembers(
    db: Session, actor: User, idInstitucion: uuid.UUID, rol: str | None = None, incluirBajas: bool = False
) -> list[MemberRead]:
    """Equipo ACTIVO e invitaciones PENDIENTES (y, si se pide, el historial dado de BAJA), opcionalmente de un rol.
    PROPIETARIO o MODERADOR."""
    requireMembership(db, actor, idInstitucion, P_EQUIPO)
    query = (
        select(InstitutionUser, User)
        .join(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
        .where(InstitutionUser.idInstitucion == idInstitucion)
        .order_by(_ROLE_ORDER, InstitutionUser.estadoRelacion, User.apellido, User.nombre)
    )
    if not incluirBajas:
        query = query.where(InstitutionUser.estadoRelacion != RELACION_BAJA)
    else:
        # Una BAJA sin incorporación es una invitación cancelada o rechazada, no una desvinculación: no es historial de personal.
        query = query.where(or_(InstitutionUser.estadoRelacion != RELACION_BAJA, InstitutionUser.fechaIncorporacion.is_not(None)))
    if rol is not None:
        query = query.where(InstitutionUser.rolInstitucion == rol)
    now = nowForDb()
    return [_memberRead(relation, user, now) for relation, user in db.execute(query).all()]


def _memberRead(relation: InstitutionUser, user: User, now: datetime) -> MemberRead:
    pending = relation.estadoRelacion == RELACION_PENDIENTE
    return MemberRead(
        idInstitucionUsuario=relation.idInstitucionUsuario,
        nombre=user.nombre or relation.nombreProfesionalHistorico,
        apellido=user.apellido or relation.apellidoProfesionalHistorico,
        usuario=user.usuario,
        correoElectronico=user.correoElectronico,
        rolInstitucion=relation.rolInstitucion,
        estadoRelacion=relation.estadoRelacion,
        cuentaPendiente=user.estado == ESTADO_CUENTA_PENDIENTE,
        matriculaProfesional=relation.matriculaProfesional,
        legajoInstitucional=relation.legajoInstitucional,
        funcionProfesional=relation.funcionProfesional,
        nombreProfesionalHistorico=relation.nombreProfesionalHistorico,
        apellidoProfesionalHistorico=relation.apellidoProfesionalHistorico,
        fechaInvitacion=relation.fechaInvitacion,
        fechaIncorporacion=relation.fechaIncorporacion,
        fechaBaja=relation.fechaBaja,
        fechaVencimientoInvitacion=_invitationExpiry(relation) if pending else None,
        invitacionVencida=_isExpiredInvitation(relation, now),
    )


# --- Búsqueda, incorporación e invitación -------------------------------------------------------
#
# Una sola operación para moderadores (los incorpora el PROPIETARIO) y operadores (los incorpora un MODERADOR):
#   A. Correo sin cuenta: se crea un Usuario USUARIO_INSTITUCIONAL PENDIENTE, sin credenciales, y su vínculo
#      PENDIENTE, en una transacción; el correo trae un enlace de activación de un solo uso (TokenCuenta
#      ACTIVACION_CUENTA). La persona elige su usuario y contraseña (o usa Google con ese correo) y después
#      acepta la invitación. Nadie define ni conoce su contraseña; sin activar no tiene acceso.
#   B. Cuenta institucional ACTIVA: se reutiliza (no se tocan sus datos) y se crea la invitación PENDIENTE.
#      Una cuenta invitada que todavía no se activó también se reutiliza (no se duplica).
#   C. Cuenta individual: se rechaza sin cambiar su tipo.
#   D. Ya vinculada a la institución (pendiente o activa): no se duplica ni se cambia su rol.

ACCOUNT_KIND_EXISTING = "EXISTENTE"
ACCOUNT_KIND_INVITED = "INVITADA_PENDIENTE"
ACCOUNT_KIND_NEW = "NUEVA"
ESTADO_CUENTA_PENDIENTE = "PENDIENTE"
TOKEN_ACTIVACION = TipoTokenCuenta.ACTIVACION_CUENTA

NEW_ACCOUNT_MESSAGE = (
    "No existe una cuenta con este correo. Completá nombre y apellido: se va a crear una cuenta institucional "
    "pendiente de activación y la persona va a recibir el enlace para activarla."
)
UNVERIFIED_ACCOUNT_MESSAGE = (
    "La cuenta de este correo todavía no confirmó su correo electrónico. Pedile que lo confirme y volvé a intentarlo."
)
UNAVAILABLE_ACCOUNT_MESSAGE = "La cuenta asociada a este correo no está disponible."
_ROLE_NAMES = {ROL_PROPIETARIO: "propietario/a", ROL_MODERADOR: "moderador/a", ROL_OPERADOR: "operador/a"}


def _requireInvitePermission(db: Session, actor: User, idInstitucion: uuid.UUID, rol: str) -> Membership:
    permission = INVITE_PERMISSION.get(rol)
    if permission is None:
        raise _forbidden("Ese rol no se puede asignar por invitación.")
    membership = requireMembership(db, actor, idInstitucion)
    if not membership.can(permission):
        registerEvent(db, "PERMISO", "INVITAR_MIEMBRO_INSTITUCION", False, actor.idUsuario, "Institucion",
                      idInstitucion, observacion=f"Sin permiso para invitar {rol}")
        db.commit()
        raise _forbidden()
    return membership


def _limitLookups(actor: User) -> None:
    if not _lookupLimiter.allow(str(actor.idUsuario)):
        raise AuthError("DEMASIADAS_SOLICITUDES", "Hiciste demasiadas búsquedas. Esperá unos minutos e intentá de nuevo.")


def _classifyTarget(
    db: Session, idInstitucion: uuid.UUID, rol: str, correoElectronico: str, now: datetime
) -> tuple[User | None, str]:
    """Clasifica el correo (casos A-D). Devuelve (cuenta o None, tipo). Cierra una invitación vencida anterior."""
    target = db.scalar(select(User).where(User.correoElectronico == correoElectronico))
    if target is None:
        return None, ACCOUNT_KIND_NEW
    if target.tipoCuenta != TIPO_INSTITUCIONAL:
        raise AuthError("CUENTA_PERSONAL_NO_INCORPORABLE", PERSONAL_ACCOUNT_MESSAGE)
    if target.estado == ESTADO_CUENTA_PENDIENTE:
        if not isInvitedPendingAccount(db, target):
            raise AuthError("CUENTA_SIN_VERIFICAR", UNVERIFIED_ACCOUNT_MESSAGE)
        kind = ACCOUNT_KIND_INVITED
    elif target.estado != "ACTIVO":
        raise AuthError("CUENTA_NO_ACTIVA", UNAVAILABLE_ACCOUNT_MESSAGE)
    else:
        kind = ACCOUNT_KIND_EXISTING
    current = db.scalar(
        select(InstitutionUser).where(
            InstitutionUser.idInstitucion == idInstitucion,
            InstitutionUser.idUsuarioInvitado == target.idUsuario,
            InstitutionUser.estadoRelacion != RELACION_BAJA,
        )
    )
    if current is not None and _isExpiredInvitation(current, now):
        _endRelation(current, now)
        db.flush()
        current = None
    if current is not None:
        sameRole = current.rolInstitucion == rol
        roleName = _ROLE_NAMES.get(current.rolInstitucion, current.rolInstitucion.lower())
        if current.estadoRelacion == RELACION_PENDIENTE:
            message = (PENDING_INVITATION_MESSAGE + " Podés reenviarla desde el listado." if sameRole else
                       f"Esta persona ya tiene una invitación pendiente como {roleName} de la institución.")
            raise AuthError("INVITACION_PENDIENTE", message)
        message = (f"Esta persona ya es {roleName} de la institución." if sameRole else
                   f"Esta persona ya pertenece a la institución como {roleName}: su rol no se cambia automáticamente.")
        raise AuthError("VINCULO_EXISTENTE", message)
    return target, kind


def lookupCandidate(
    db: Session, actor: User, idInstitucion: uuid.UUID, rol: str, correoElectronico: str
) -> MemberCandidate:
    """Estado del correo antes de incorporar: cuenta existente (nombre y apellido para confirmar) o 404 si no existe
    (el formulario pide entonces nombre y apellido para crearla). Las demás situaciones responden su motivo."""
    _requireInvitePermission(db, actor, idInstitucion, rol)
    _limitLookups(actor)
    target, kind = _classifyTarget(db, idInstitucion, rol, correoElectronico, nowForDb())
    db.rollback()  # la búsqueda no persiste nada (ni el cierre de una invitación vencida)
    if target is None:
        raise AuthError("USUARIO_NO_ENCONTRADO", NEW_ACCOUNT_MESSAGE)
    return MemberCandidate(nombre=target.nombre, apellido=target.apellido, rolPropuesto=rol,
                           cuentaPendiente=kind == ACCOUNT_KIND_INVITED)


def _issueActivationToken(db: Session, user: User, expiresAt: datetime) -> str:
    """Token de activación nuevo (solo se guarda su hash); invalida los anteriores sin usar. Lo confirma quien llama."""
    db.execute(delete(AccountToken).where(AccountToken.idUsuario == user.idUsuario, AccountToken.tipo == TOKEN_ACTIVACION,
                                          AccountToken.fechaUso.is_(None)))
    token = security.generateOpaqueToken()
    db.add(AccountToken(idUsuario=user.idUsuario, tipo=TOKEN_ACTIVACION, tokenHash=security.hashOpaqueToken(token),
                        fechaExpiracion=expiresAt))
    return token


def _sendInvitation(institution: Institution, actor: User, target: User, relation: InstitutionUser,
                    activationToken: str | None) -> None:
    expiry = _invitationExpiry(relation)
    if activationToken is not None:
        emailService.sendEmailEventInBackground(
            EmailEventType.INVITACION_INSTITUCION_NUEVA_CUENTA, target.correoElectronico,
            {"nombre": target.nombre, "nombreInstitucion": institution.nombre, "rol": relation.rolInstitucion,
             "nombreInvitante": _fullName(actor), "fechaExpiracion": expiry,
             "urlActivar": f"{emailService.frontendUrl('activarCuenta')}?token={activationToken}"},
        )
        return
    invitationsUrl = emailService.frontendUrl("invitacionesInstitucion")
    emailService.sendEmailEventInBackground(
        EmailEventType.INVITACION_INSTITUCION, target.correoElectronico,
        {"nombre": target.nombre, "nombreInstitucion": institution.nombre, "rol": relation.rolInstitucion,
         "nombreInvitante": _fullName(actor), "fechaExpiracion": expiry,
         "urlAceptar": invitationsUrl, "urlRechazar": invitationsUrl},
    )


@retryOnDeadlock
def invite(
    db: Session, actor: User, idInstitucion: uuid.UUID, rol: str, correoElectronico: str,
    nombre: str | None = None, apellido: str | None = None, datos: dict | None = None, _retry: bool = True,
) -> MemberRead:
    """Incorpora por invitación (casos A-D). Cuenta nueva y vínculo se crean en una sola transacción; el vínculo
    queda PENDIENTE hasta que la persona lo acepte. Nunca crea registros en PerfilMedicion.

    `datos`: matriculaProfesional, legajoInstitucional y nombre/apellido profesional histórico del vínculo (iguales
    para moderadores y operadores). El nombre y apellido histórico, si faltan, se toman de la persona; en una
    cuenta existente nunca se modifican el nombre ni el apellido de Usuario."""
    datos = {field: (datos or {}).get(field) for field in MEMBER_ADMIN_FIELDS}
    institution = _requireInvitePermission(db, actor, idInstitucion, rol).institution
    _limitLookups(actor)
    now = nowForDb()
    try:
        target, kind = _classifyTarget(db, idInstitucion, rol, correoElectronico, now)
        if target is not None:
            # Se toma la fila de la cuenta invitada ANTES de crear el vínculo y se mantiene hasta el commit: la depuración de cuentas invitadas
            # sin salida y la eliminación automática usan el mismo bloqueo, así que una invitación nueva nunca queda cancelada por ellas. Si
            # esas tareas ganaron la carrera (la cuenta ya está ELIMINADA y su correo liberado), se invita como a una cuenta nueva.
            locked = accountGrace.lockUser(db, target.idUsuario)
            if locked is None or locked.estado == "ELIMINADO":
                target, kind = None, ACCOUNT_KIND_NEW
        if kind == ACCOUNT_KIND_NEW and not (nombre and apellido):
            raise AuthError("DATOS_REQUERIDOS", "Ingresá nombre y apellido para crear la cuenta de la persona.")
    except AuthError as error:
        registerEvent(db, "PERMISO", "INVITAR_MIEMBRO_INSTITUCION", False, actor.idUsuario, "Institucion",
                      idInstitucion, observacion=f"Motivo: {error.code}")
        db.commit()
        raise

    activationToken = None
    try:
        if kind == ACCOUNT_KIND_NEW:
            # Segunda barrera (además del schema): nombres normalizados como en el registro.
            nombre, apellido = normalizeProperName(nombre), normalizeProperName(apellido)
            target = User(nombre=nombre, apellido=apellido, correoElectronico=correoElectronico,
                          tipoCuenta=TIPO_INSTITUCIONAL, estado=ESTADO_CUENTA_PENDIENTE)
            db.add(target)
            db.flush()
            registerEvent(db, "CRUD", "CREAR_CUENTA_INVITADA", True, actor.idUsuario, "Usuario", target.idUsuario,
                          datosNuevos={"tipoCuenta": TIPO_INSTITUCIONAL, "estado": ESTADO_CUENTA_PENDIENTE,
                                       "idInstitucion": str(idInstitucion)},
                          idInstitucion=idInstitucion, modulo="INSTITUCIONES")
        relation = InstitutionUser(
            idInstitucion=idInstitucion, idUsuarioInvitado=target.idUsuario, rolInstitucion=rol,
            matriculaProfesional=datos["matriculaProfesional"],
            legajoInstitucional=datos["legajoInstitucional"],
            funcionProfesional=datos["funcionProfesional"],
            nombreProfesionalHistorico=datos["nombreProfesionalHistorico"] or target.nombre,
            apellidoProfesionalHistorico=datos["apellidoProfesionalHistorico"] or target.apellido,
            estadoRelacion=RELACION_PENDIENTE, origenVinculo=ORIGEN_INVITACION, idUsuarioInvitador=actor.idUsuario,
            fechaInvitacion=now,
        )
        db.add(relation)
        db.flush()
        if kind != ACCOUNT_KIND_NEW and not accountGrace.confirmNotDeleted(db, target.idUsuario, now):
            # La cuenta se eliminó o depuró justo ahora (la tarea automática ganó): se deshace y se invita de nuevo como a una cuenta nueva.
            db.rollback()
            if _retry:
                return invite(db, actor, idInstitucion, rol, correoElectronico, nombre, apellido, datos, _retry=False)
            raise AuthError("INVITACION_PENDIENTE", "Otra solicitud acaba de modificar esta cuenta. Volvé a intentarlo.")
        if kind in (ACCOUNT_KIND_NEW, ACCOUNT_KIND_INVITED):
            activationToken = _issueActivationToken(db, target, _invitationExpiry(relation))
        registerEvent(
            db, "PERMISO", "INVITAR_MIEMBRO_INSTITUCION", True, actor.idUsuario, "InstitucionUsuario",
            relation.idInstitucionUsuario,
            datosNuevos={"rolInstitucion": rol, "estadoRelacion": RELACION_PENDIENTE, "cuenta": kind},
        )
        db.commit()
    except IntegrityError as error:
        # Se revierte todo: no queda una cuenta sin vínculo ni un vínculo duplicado.
        db.rollback()
        if _violates(error, MEMBER_UNIQUE_INDEX, "idUsuarioInvitado"):
            raise AuthError("INVITACION_PENDIENTE", PENDING_INVITATION_MESSAGE) from error
        if _violates(error, USER_EMAIL_UNIQUE_INDEX, "correoElectronico"):
            # Carrera: otra solicitud creó la cuenta de este correo en paralelo.
            raise AuthError("INVITACION_PENDIENTE", "Otra solicitud acaba de registrar este correo. Volvé a intentarlo.") from error
        # Otro CHECK (p. ej. CK_TokenCuenta_tipo desactualizado en la base instalada): error de servidor, con la causa
        # en el log y sin exponerla al usuario.
        message = str(getattr(error, "orig", error))
        hint = " Recrear CK_TokenCuenta_tipo según database/reference/GlucoLume_DB_v5.sql." if "CK_TokenCuenta_tipo".lower() in message.lower() else ""
        logger.error("No se pudo incorporar personal en la institución %s: %s.%s", idInstitucion, type(error).__name__, hint)
        raise AuthError("ERROR_SERVIDOR", "No pudimos completar la incorporación. Intentá de nuevo más tarde.") from error

    _sendInvitation(institution, actor, target, relation, activationToken)
    return _memberRead(relation, target, now)


def resendInvitation(
    db: Session, actor: User, idInstitucion: uuid.UUID, rol: str, idInstitucionUsuario: uuid.UUID
) -> MemberRead:
    """Reenvía una invitación PENDIENTE (también si el envío anterior falló): renueva su vencimiento y, si la cuenta
    todavía no se activó, genera un enlace de activación nuevo. No duplica cuentas ni vínculos."""
    institution = _requireInvitePermission(db, actor, idInstitucion, rol).institution
    _limitLookups(actor)
    relation = db.get(InstitutionUser, idInstitucionUsuario)
    if (relation is None or relation.idInstitucion != idInstitucion or relation.rolInstitucion != rol
            or relation.estadoRelacion != RELACION_PENDIENTE):
        raise AuthError("INVITACION_NO_ENCONTRADA", "No encontramos esa invitación pendiente.")
    target = accountGrace.lockUser(db, relation.idUsuarioInvitado)  # misma sincronización que invite(): ver ese comentario
    db.refresh(relation)
    if target is None or target.estado == "ELIMINADO" or relation.estadoRelacion != RELACION_PENDIENTE:
        db.rollback()
        raise AuthError("INVITACION_NO_ENCONTRADA", "No encontramos esa invitación pendiente.")
    now = nowForDb()
    if not accountGrace.confirmNotDeleted(db, target.idUsuario, now):
        db.rollback()
        raise AuthError("INVITACION_NO_ENCONTRADA", "No encontramos esa invitación pendiente.")
    relation.fechaInvitacion = now
    relation.idUsuarioInvitador = actor.idUsuario
    activationToken = _issueActivationToken(db, target, _invitationExpiry(relation)) \
        if isInvitedPendingAccount(db, target) else None
    registerEvent(db, "PERMISO", "REENVIAR_INVITACION_INSTITUCION", True, actor.idUsuario, "InstitucionUsuario",
                  idInstitucionUsuario)
    db.commit()
    _sendInvitation(institution, actor, target, relation, activationToken)
    return _memberRead(relation, target, now)


def updateMemberAdmin(
    db: Session, actor: User, idInstitucion: uuid.UUID, rol: str, idInstitucionUsuario: uuid.UUID, changes: dict
) -> MemberRead:
    """Edita los datos administrativos de un vínculo vigente (activo o pendiente): moderadores, solo el PROPIETARIO;
    operadores, el PROPIETARIO o un MODERADOR. No cambia el rol ni los datos de la cuenta Usuario. Auditado con los
    nombres de los campos modificados (sin sus valores)."""
    permission = REVOKE_PERMISSION.get(rol)
    membership = requireMembership(db, actor, idInstitucion)
    if permission is None or not membership.can(permission):
        registerEvent(db, "PERMISO", "MODIFICAR_MIEMBRO_INSTITUCION", False, actor.idUsuario, "Institucion",
                      idInstitucion, observacion=f"Sin permiso para modificar {rol}")
        db.commit()
        raise _forbidden()
    relation = db.get(InstitutionUser, idInstitucionUsuario)
    if (relation is None or relation.idInstitucion != idInstitucion or relation.rolInstitucion != rol
            or relation.estadoRelacion == RELACION_BAJA):
        raise AuthError("MIEMBRO_NO_ENCONTRADO", "No encontramos ese integrante en la institución.")
    changed = sorted(field for field in MEMBER_ADMIN_FIELDS
                     if field in changes and getattr(relation, field) != changes[field])
    if changed:
        for field in changed:
            setattr(relation, field, changes[field])
        registerEvent(db, "CRUD", "MODIFICAR_MIEMBRO_INSTITUCION", True, actor.idUsuario, "InstitucionUsuario",
                      idInstitucionUsuario, datosNuevos={"rolInstitucion": rol, "campos": changed})
        db.commit()
    return _memberRead(relation, db.get(User, relation.idUsuarioInvitado), nowForDb())


# --- Invitaciones recibidas -----------------------------------------------------------------


def _inviterStillAuthorized(db: Session, relation: InstitutionUser) -> bool:
    """Quien invitó debe conservar el permiso para invitar ese rol (si lo revocaron, la invitación cae)."""
    permission = INVITE_PERMISSION.get(relation.rolInstitucion)
    inviterRole = db.scalar(
        select(InstitutionUser.rolInstitucion).where(
            InstitutionUser.idInstitucion == relation.idInstitucion,
            InstitutionUser.idUsuarioInvitado == relation.idUsuarioInvitador,
            InstitutionUser.estadoRelacion == RELACION_ACTIVO,
        )
    )
    return permission is not None and permission in ROLE_PERMISSIONS.get(inviterRole, ())


def listInvitations(db: Session, user: User) -> list[InvitationRead]:
    """Invitaciones PENDIENTES de la cuenta autenticada en instituciones ACTIVAS: vigentes (se pueden responder) y
    vencidas (solo informativas). Las canceladas, rechazadas o de instituciones cerradas pasan a BAJA y no se listan."""
    if user.tipoCuenta != TIPO_INSTITUCIONAL:
        return []
    now = nowForDb()
    rows = db.execute(
        select(InstitutionUser, Institution)
        .join(Institution, Institution.idInstitucion == InstitutionUser.idInstitucion)
        .where(
            InstitutionUser.idUsuarioInvitado == user.idUsuario,
            InstitutionUser.estadoRelacion == RELACION_PENDIENTE,
            Institution.estado == INSTITUCION_ACTIVA,
        )
        .order_by(InstitutionUser.fechaInvitacion.desc())
    ).all()
    return [
        InvitationRead(
            idInstitucionUsuario=relation.idInstitucionUsuario,
            idInstitucion=institution.idInstitucion,
            nombreInstitucion=institution.nombre,
            tipoInstitucion=institution.tipoInstitucion,
            rolInstitucion=relation.rolInstitucion,
            nombreInvitante=_fullName(relation.usuarioInvitador),
            fechaInvitacion=relation.fechaInvitacion,
            fechaVencimiento=_invitationExpiry(relation),
            estado="VENCIDA" if _isExpiredInvitation(relation, now) else "PENDIENTE",
        )
        for relation, institution in rows
    ]


def _auditCapacityRejection(db: Session, user: User, relation: InstitutionUser) -> None:
    """Incorporación rechazada por capacidad completa: queda registrada (la invitación sigue PENDIENTE, nada se activó a medias)."""
    registerEvent(db, "PERMISO", "ACEPTAR_INVITACION_INSTITUCION", False, user.idUsuario, "InstitucionUsuario", relation.idInstitucionUsuario,
                  observacion="Motivo: CAPACIDAD_COMPLETA")
    db.commit()


def respondInvitation(db: Session, user: User, idInstitucionUsuario: uuid.UUID, accept: bool) -> MyInstitutionRead | None:
    """La propia cuenta invitada (autenticada) acepta o rechaza. Devuelve la institución si la aceptó."""
    _requireInstitutionalAccount(user)
    now = nowForDb()
    relation = db.get(InstitutionUser, idInstitucionUsuario)
    if relation is None or relation.idUsuarioInvitado != user.idUsuario or relation.estadoRelacion != RELACION_PENDIENTE:
        raise AuthError("INVITACION_NO_ENCONTRADA", "No encontramos esa invitación o ya fue respondida.")
    institution = db.get(Institution, relation.idInstitucion)
    if (
        _isExpiredInvitation(relation, now)
        or institution.estado != INSTITUCION_ACTIVA
        or not _inviterStillAuthorized(db, relation)
    ):
        _endRelation(relation, now)
        registerEvent(db, "PERMISO", "RESPONDER_INVITACION_INSTITUCION", False, user.idUsuario,
                      "InstitucionUsuario", relation.idInstitucionUsuario, observacion="Invitación no vigente")
        db.commit()
        raise AuthError("INVITACION_VENCIDA", "La invitación ya no está vigente. Pedí que te envíen una nueva.")

    reincorporation = False
    if accept:
        # Serializa con la eliminación automática de la cuenta: o se incorpora (y el plazo se cancela) o la cuenta ya fue eliminada.
        locked = accountGrace.lockUser(db, user.idUsuario)
        if locked is None or locked.estado != "ACTIVO":
            db.rollback()
            raise AuthError("CUENTA_NO_ACTIVA", "La cuenta no está activa.")
        # Incorporación efectiva = consume un cupo. Se comprueba AHORA, con la institución bloqueada, y no cuando se envió la invitación.
        try:
            quota.requireSlot(db, relation.idInstitucion)
        except AuthError:
            db.rollback()
            _auditCapacityRejection(db, user, relation)
            raise
        reincorporation = bool(db.scalar(select(func.count()).select_from(InstitutionUser).where(
            InstitutionUser.idInstitucion == relation.idInstitucion, InstitutionUser.idUsuarioInvitado == user.idUsuario,
            InstitutionUser.fechaIncorporacion.is_not(None), InstitutionUser.idInstitucionUsuario != relation.idInstitucionUsuario)))
    newState = RELACION_ACTIVO if accept else RELACION_BAJA
    values = {"estadoRelacion": newState}
    values["fechaIncorporacion" if accept else "fechaBaja"] = now
    # Condicionado al estado: dos respuestas simultáneas no pueden aplicarse ambas.
    result = db.execute(
        update(InstitutionUser)
        .where(
            InstitutionUser.idInstitucionUsuario == relation.idInstitucionUsuario,
            InstitutionUser.estadoRelacion == RELACION_PENDIENTE,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        db.rollback()
        raise AuthError("INVITACION_NO_ENCONTRADA", "No encontramos esa invitación o ya fue respondida.")
    details = {"rolInstitucion": relation.rolInstitucion, "estadoRelacion": newState}
    if accept:
        try:
            after = quota.verifyNotExceeded(db, relation.idInstitucion)  # misma transacción: si se pasó, se revierte
        except AuthError:
            db.rollback()
            _auditCapacityRejection(db, user, relation)
            raise
        details.update({"usuariosActivos": after.usuariosActivos, "capacidadMaximaUsuarios": after.capacidadMaximaUsuarios,
                        "reincorporacion": reincorporation})  # el mismo evento de la incorporación informa el cupo consumido
        # Vinculación efectiva: si la cuenta estaba en período de gracia, el vencimiento se cancela (misma transacción, mismo idUsuario).
        accountGrace.cancelOnIncorporation(db, user, now)
        accountGrace.confirmStillActive(db, user.idUsuario, now)
    registerEvent(
        db, "PERMISO", "ACEPTAR_INVITACION_INSTITUCION" if accept else "RECHAZAR_INVITACION_INSTITUCION", True,
        user.idUsuario, "InstitucionUsuario", relation.idInstitucionUsuario, datosNuevos=details,
    )
    db.commit()
    db.refresh(relation)
    inviter = relation.usuarioInvitador
    if not accept:
        # Quien invitó se entera de que la invitación no fue aceptada (para poder reinvitar o elegir a otra persona).
        if inviter is not None and inviter.correoElectronico:
            emailService.sendEmailEventInBackground(
                EmailEventType.INVITACION_RECHAZADA,
                inviter.correoElectronico,
                {"nombre": inviter.nombre, "nombreInvitado": _fullName(user), "nombreInstitucion": institution.nombre,
                 "rol": relation.rolInstitucion, "fechaEvento": now},
            )
        return None

    if inviter is not None and inviter.correoElectronico:
        emailService.sendEmailEventInBackground(
            EmailEventType.INVITACION_ACEPTADA,
            inviter.correoElectronico,
            {"nombre": inviter.nombre, "nombreInvitado": _fullName(user), "nombreInstitucion": institution.nombre,
             "rol": relation.rolInstitucion, "fechaEvento": now},
        )
    # Confirmación a la persona incorporada, con acceso directo a la institución.
    if user.correoElectronico:
        emailService.sendEmailEventInBackground(
            EmailEventType.AGREGADO_INSTITUCION, user.correoElectronico,
            {"nombre": user.nombre, "nombreInstitucion": institution.nombre, "rol": relation.rolInstitucion,
             "fechaEvento": now,
             "urlIngreso": emailService.frontendUrl(f"/app/instituciones/{institution.idInstitucion}")},
        )
    # El propietario se entera de los operadores que se suman (si no fue quien los invitó).
    if relation.rolInstitucion == ROL_OPERADOR:
        _notifyOwners(db, institution.idInstitucion, EmailEventType.OPERADOR_AGREGADO, institution.nombre,
                      _fullName(user), now, {user.idUsuario, relation.idUsuarioInvitador})
    return _summary(Membership(institution, relation))


def _notifyOwners(db: Session, idInstitucion: uuid.UUID, event: EmailEventType, institutionName: str,
                  operatorName: str, now: datetime, exclude: set) -> None:
    """Avisa a los propietarios activos (menos quien hizo el cambio) de una novedad en el equipo de operadores."""
    owners = db.scalars(
        select(User).join(InstitutionUser, InstitutionUser.idUsuarioInvitado == User.idUsuario).where(
            InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.rolInstitucion == ROL_PROPIETARIO,
            InstitutionUser.estadoRelacion == RELACION_ACTIVO,
        )
    ).all()
    for owner in owners:
        if owner.idUsuario not in exclude and owner.correoElectronico:
            emailService.sendEmailEventInBackground(
                event, owner.correoElectronico,
                {"nombre": owner.nombre, "nombreOperador": operatorName, "nombreInstitucion": institutionName,
                 "fechaEvento": now},
            )


# --- Revocar vínculos o cancelar invitaciones ----------------------------------------------


def _releaseMemberResources(db: Session, relationIds) -> None:
    """Lo que dependía de vínculos que terminan: dispositivos a su cargo y transferencias pendientes."""
    db.execute(
        update(Device)
        # Un dispositivo descomisionado conserva su responsable como referencia histórica.
        .where(Device.idInstitucionUsuarioResponsable.in_(relationIds), Device.estado != "BAJA")
        .values(idInstitucionUsuarioResponsable=None)
        .execution_options(synchronize_session=False)
    )
    db.execute(
        update(ProfileTransfer)
        .where(ProfileTransfer.idOperadorDestino.in_(relationIds), ProfileTransfer.estado == TRANSFERENCIA_PENDIENTE)
        .values(estado=TRANSFERENCIA_CANCELADA)
        .execution_options(synchronize_session=False)
    )


def revokeMember(db: Session, actor: User, idInstitucion: uuid.UUID, rol: str, idInstitucionUsuario: uuid.UUID,
                 prepare: Callable[[Session, InstitutionUser, datetime], None] | None = None) -> None:
    """Revoca un vínculo ACTIVO o cancela una invitación PENDIENTE de un MODERADOR (propietario) o de un
    OPERADOR (propietario o moderador). Al revocar un moderador caen también las invitaciones que emitió.

    Un OPERADOR ACTIVO no puede desvincularse mientras tenga pacientes a su cargo: primero hay que reasignarlos (services/
    operatorOffboarding.py). `prepare` es ese paso: se ejecuta con el vínculo bloqueado y dentro de la MISMA transacción que la baja, de modo
    que o se reasigna y se desvincula todo, o no cambia nada. La validación vive acá (no en el cliente) y cubre cualquier ruta de baja."""
    permission = REVOKE_PERMISSION.get(rol)
    membership = requireMembership(db, actor, idInstitucion)
    if permission is None or not membership.can(permission):
        registerEvent(db, "PERMISO", "REVOCAR_MIEMBRO_INSTITUCION", False, actor.idUsuario, "Institucion",
                      idInstitucion, observacion=f"Sin permiso para revocar {rol}")
        db.commit()
        raise _forbidden()
    relation = db.get(InstitutionUser, idInstitucionUsuario)
    if (
        relation is None
        or relation.idInstitucion != idInstitucion
        or relation.rolInstitucion != rol
        or relation.estadoRelacion == RELACION_BAJA
        or relation.idUsuarioInvitado == actor.idUsuario
    ):
        raise AuthError("MIEMBRO_NO_ENCONTRADO", "No encontramos ese integrante en la institución.")

    now = nowForDb()
    wasActive = relation.estadoRelacion == RELACION_ACTIVO
    if rol == ROL_OPERADOR and wasActive:
        relation = lockRelation(db, idInstitucionUsuario)
        if relation is None or relation.estadoRelacion != RELACION_ACTIVO:  # otra baja simultánea ganó
            db.rollback()
            raise AuthError("MIEMBRO_NO_ENCONTRADO", "No encontramos ese integrante en la institución.")
        if prepare is not None:
            try:
                prepare(db, relation, now)
            except BaseException:
                db.rollback()  # nada de la reasignación queda a medias
                raise
        assigned = reassignments.activeProfileCount(db, relation.idInstitucionUsuario)
        if assigned:
            db.rollback()  # descarta también lo que haya hecho `prepare`: el operador conserva su responsabilidad
            registerEvent(db, "PERMISO", "REVOCAR_MIEMBRO_INSTITUCION", False, actor.idUsuario, "InstitucionUsuario",
                          idInstitucionUsuario, observacion="Motivo: PACIENTES_ASIGNADOS")
            db.commit()
            raise AuthError("PACIENTES_ASIGNADOS",
                            f"Este operador tiene {assigned} {'paciente asignado' if assigned == 1 else 'pacientes asignados'}. "
                            "Antes de desvincularlo, debés reasignarlos.")
    ended = [relation.idInstitucionUsuario]
    _endRelation(relation, now)
    if rol == ROL_MODERADOR:
        issued = db.scalars(
            select(InstitutionUser).where(
                InstitutionUser.idInstitucion == idInstitucion,
                InstitutionUser.idUsuarioInvitador == relation.idUsuarioInvitado,
                InstitutionUser.estadoRelacion == RELACION_PENDIENTE,
            )
        ).all()
        for pending in issued:
            _endRelation(pending, now)
    db.flush()
    _releaseMemberResources(db, ended)
    graceUser = None
    if wasActive:
        # Si era su última vinculación activa, comienza el período de gracia de la cuenta; si no, la cuenta no se toca. Sus pacientes ya
        # fueron reasignados (o no tenía): el operador no deja a nadie sin responsable.
        graceUser = accountGrace.startIfOrphaned(db, relation.idUsuarioInvitado, now, actor.idUsuario, "BAJA_INSTITUCIONAL")
    released = {"usuariosActivos": quota.activeCount(db, idInstitucion), "capacidadMaximaUsuarios": quota.capacityOf(db, idInstitucion),
                "cuentaConservaOtrasInstituciones": accountGrace.activeBondCount(db, relation.idUsuarioInvitado) > 0} if wasActive else {}
    registerEvent(
        db, "PERMISO", "REVOCAR_MIEMBRO_INSTITUCION" if wasActive else "CANCELAR_INVITACION_INSTITUCION", True,
        actor.idUsuario, "InstitucionUsuario", relation.idInstitucionUsuario,
        datosPrevios={"estadoRelacion": RELACION_ACTIVO if wasActive else RELACION_PENDIENTE},
        datosNuevos={"rolInstitucion": rol, "estadoRelacion": RELACION_BAJA, **released},  # una baja activa libera un cupo; una invitación, no
    )
    db.commit()

    member = relation.usuarioInvitado
    if wasActive and rol == ROL_OPERADOR:
        _notifyOwners(db, idInstitucion, EmailEventType.OPERADOR_ELIMINADO, membership.institution.nombre,
                      _fullName(member), now, {actor.idUsuario})
    if wasActive and member.correoElectronico:
        emailService.sendEmailEventInBackground(
            EmailEventType.ELIMINADO_INSTITUCION,
            member.correoElectronico,
            {"nombre": member.nombre, "nombreInstitucion": membership.institution.nombre, "fechaEvento": now},
        )
    if graceUser is not None:  # después del aviso de la baja: la persona se entera primero de lo que pasó y luego del plazo
        accountGrace.notifyStarted(graceUser, now)


# --- Eliminación lógica ---------------------------------------------------------------------


def _reauthenticate(
    db: Session, actor: User, idInstitucion: uuid.UUID, data, accion: str = "ELIMINAR_INSTITUCION"
) -> None:
    """Misma reautenticación que las operaciones sensibles de la cuenta: contraseña si tiene credencial local
    (con el contador y bloqueo compartidos con el login) y MFA si lo tiene habilitado.

    Una cuenta solo Google no tiene contraseña (no se le pide) y la sesión no prueba un ingreso reciente con Google
    (el refresh crea sesiones nuevas): confirma con la verificación en dos pasos de GlucoLume. Sin MFA activado no
    puede confirmar esta operación.
    """
    credential = db.scalar(select(LocalCredential).where(LocalCredential.idUsuario == actor.idUsuario))
    factor = mfa.getFactor(db, actor)
    mfaEnabled = factor is not None and factor.habilitado
    if credential is None and not mfaEnabled:
        raise AuthError(
            "REAUTENTICACION_REQUERIDA",
            "Tu cuenta usa Google: para confirmar operaciones sensibles activá la verificación en dos pasos en "
            "Seguridad y volvé a intentarlo.",
        )
    if credential is not None:
        if data.password is None:
            raise AuthError("PASSWORD_REQUERIDA", "Ingresá tu contraseña actual para confirmar la operación.")
        if not authService.verifyCurrentPassword(db, credential, data.password.get_secret_value()):
            registerEvent(db, "CRUD", accion, False, actor.idUsuario, "Institucion", idInstitucion,
                          observacion="Motivo: PASSWORD_INCORRECTA")
            db.commit()
            raise AuthError("PASSWORD_INCORRECTA", "La contraseña es incorrecta.")
    if mfaEnabled:
        if data.codigo is None and data.codigoRecuperacion is None:
            raise AuthError("CODIGO_MFA_REQUERIDO", "Ingresá el código de verificación en dos pasos.")
        mfa.verifyFactor(db, factor, data.codigo, data.codigoRecuperacion)


class ClosureResult:
    """Resultado del cierre lógico (cuántos vínculos y perfiles alcanzó y a quién hay que avisar después del commit)."""

    def __init__(self, members: list[User], ended: int, profiles: int, retentionEnd: datetime, graced: list[User]):
        self.members, self.ended, self.profiles, self.retentionEnd, self.graced = members, ended, profiles, retentionEnd, graced


def applyLogicalClosure(db: Session, idInstitucion: uuid.UUID, actorId: uuid.UUID, now: datetime, *, fromStates: tuple[str, ...],
                        extraValues: dict | None = None) -> ClosureResult | None:
    """Cierre LÓGICO (nunca un DELETE físico), compartido por el cierre del propietario y la eliminación administrativa de la plataforma. No hace
    commit ni registra el evento: lo hace quien llama, para que estado y evidencia vayan en UNA transacción. Devuelve None (sin tocar nada) si la
    institución ya no está en alguno de `fromStates` (dos cierres simultáneos no se aplican dos veces).

    Da de baja los vínculos, libera los recursos de los integrantes, cancela reasignaciones, inicia el período de gracia de quien se queda sin
    otra institución y fija la conservación de los pacientes (RETENTION_MONTHS): los datos clínicos no se destruyen."""
    retentionEnd = addMonths(now, RETENTION_MONTHS)
    # Condicionado al estado: dos eliminaciones simultáneas no se aplican dos veces.
    table = Institution.__table__  # Core: extraValues puede nombrar columnas que el ORM no mapea (cierre administrativo)
    result = db.execute(
        update(table)
        .where(table.c.idInstitucion == idInstitucion, table.c.estado.in_(fromStates))
        .values(estado=INSTITUCION_ELIMINADA, fechaActualizacion=now, **(extraValues or {}))
    )
    if result.rowcount == 0:
        return None

    notify = db.scalars(
        select(User)
        .join(InstitutionUser, InstitutionUser.idUsuarioInvitado == User.idUsuario)
        .where(InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.estadoRelacion == RELACION_ACTIVO)
    ).all()
    relationIds = institutionRelationIds(idInstitucion)
    ended = db.execute(
        update(InstitutionUser)
        .where(InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.estadoRelacion != RELACION_BAJA)
        .values(estadoRelacion=RELACION_BAJA, fechaBaja=now)
        .execution_options(synchronize_session=False)
    ).rowcount
    _releaseMemberResources(db, relationIds)
    reassignments.cancelForInstitution(db, idInstitucion, now)  # los pacientes pasan a conservación: nada queda por reasignar
    # Quien se quedó sin ninguna otra institución activa comienza su período de gracia; el resto de las cuentas no se modifica.
    graced = [user for user in (accountGrace.startIfOrphaned(db, member.idUsuario, now, actorId, "INSTITUCION_ELIMINADA")
                                for member in notify) if user is not None]
    # Pacientes: se conservan RETENTION_MONTHS meses desde el cierre (fechaExpiracionDatosPersonales), sin acceso
    # operativo (ya no hay vínculos activos ni la institución está ACTIVA). Al vencer, el job de retención los
    # desidentifica de forma irreversible. Un vencimiento anterior (por una baja previa) se respeta.
    profiles = db.execute(
        update(MeasurementProfile)
        .where(
            MeasurementProfile.idInstitucionUsuarioResponsable.in_(relationIds),
            MeasurementProfile.fechaDepuracionDatosPersonales.is_(None),
            or_(
                MeasurementProfile.fechaExpiracionDatosPersonales.is_(None),
                MeasurementProfile.fechaExpiracionDatosPersonales > retentionEnd,
            ),
        )
        .values(fechaExpiracionDatosPersonales=retentionEnd)
        .execution_options(synchronize_session=False)
    ).rowcount
    return ClosureResult(list(notify), ended, profiles, retentionEnd, graced)


def deleteInstitution(db: Session, actor: User, idInstitucion: uuid.UUID, data: InstitutionDeletionRequest) -> None:
    """Eliminación lógica, exclusiva del PROPIETARIO, en una sola transacción. Nunca un DELETE físico."""
    membership = requireMembership(db, actor, idInstitucion)
    if not membership.can(P_ELIMINAR):
        registerEvent(db, "CRUD", "ELIMINAR_INSTITUCION", False, actor.idUsuario, "Institucion", idInstitucion,
                      observacion="Motivo: PERMISO_INSUFICIENTE")
        db.commit()
        raise _forbidden("Solo el propietario puede eliminar la institución.")
    institution = membership.institution
    if data.confirmacionNombre.strip().casefold() != institution.nombre.strip().casefold():
        raise AuthError("CONFIRMACION_INVALIDA", "Escribí el nombre exacto de la institución para confirmar.")
    _reauthenticate(db, actor, idInstitucion, data)

    now = nowForDb()
    closure = applyLogicalClosure(db, idInstitucion, actor.idUsuario, now, fromStates=(INSTITUCION_ACTIVA,))
    if closure is None:
        db.rollback()
        raise AuthError("INSTITUCION_NO_ENCONTRADA", "No encontramos esa institución entre las tuyas.")
    registerEvent(
        db, "CRUD", "ELIMINAR_INSTITUCION", True, actor.idUsuario, "Institucion", idInstitucion,
        datosPrevios={"estado": INSTITUCION_ACTIVA},
        datosNuevos={"estado": INSTITUCION_ELIMINADA, "vinculosDadosDeBaja": closure.ended,
                     "perfilesEnConservacion": closure.profiles, "finConservacionDatos": closure.retentionEnd.isoformat(),
                     "cuentasEnPeriodoGracia": len(closure.graced)},
    )
    db.commit()
    for user in closure.graced:
        accountGrace.notifyStarted(user, now)

    for member in closure.members:
        if member.correoElectronico:
            emailService.sendEmailEventInBackground(
                EmailEventType.INSTITUCION_ELIMINADA,
                member.correoElectronico,
                {"nombre": member.nombre, "nombreInstitucion": institution.nombre, "fechaEvento": now},
            )
