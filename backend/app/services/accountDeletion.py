# AccountDeletion - Eliminación de la cuenta propia (módulo Auth)
#
# Dos pasos:
#   1. Solicitud (usuario autenticado, sin datos adicionales): reglas de Grupo/Institución,
#      TokenCuenta ELIMINAR_CUENTA de 30 minutos (solo el hash, un solo uso; invalida el pendiente) y,
#      después del commit, correo ELIMINACION_SOLICITADA con el enlace. Todavía no elimina nada.
#   2. Confirmación (pantalla del enlace): se valida el token y la reautenticación (contraseña si tiene
#      CredencialLocal, MFA si lo tiene habilitado), y se vuelven a comprobar el estado de la cuenta y las
#      reglas de Grupo/Institución. El token se consume solo si todo eso es correcto, en la misma
#      transacción que la baja. Después del commit se envía CUENTA_ELIMINADA; un fallo de envío no
#      revierte la eliminación.
#
# La baja no borra el Usuario: conserva idUsuario, pasa a estado ELIMINADO (el valor de baja que
# admite CK_Usuario_estado) con fechaEliminacion, anonimiza sus datos personales y revoca toda forma
# de autenticación. Las mediciones se conservan desidentificadas (Medicion guarda edadAlMomento,
# sexoModelo y el contexto propio de cada medición).
#
# Una cuenta institucional solo puede usar este camino cuando NO tiene ninguna vinculación ACTIVA con una institución (en período de gracia
# o sin plazo): con una o más instituciones activas se rechaza y la persona debe finalizar primero sus vinculaciones. Ese caso no impide una
# solicitud formal de supresión de datos personales, que se trata por separado. La misma anonimización (anonymizeAccount) la usa la
# eliminación automática al vencer el período de gracia (services/accountLifecycle.py).
#
# Qué queda en cada tabla: Usuario conserva idUsuario (clave de las relaciones históricas) y se anonimiza; InstitucionUsuario NO se borra
# (solo se completan los nombres profesionales históricos y se cierran las invitaciones que seguían pendientes); Auditoria no se modifica;
# las mediciones y su autoría (Auditoria INICIAR_MEDICION + el vínculo del operador) no cambian.
#
# Auth solo detecta, bloquea e informa las dependencias de Grupo e Institución; la transferencia de
# propiedad, el cierre de grupos y la desvinculación institucional pertenecen a esos módulos. La única
# excepción es la salida automática de los grupos donde la persona no es PROPIETARIO.
#
# Auditoría: solo SOLICITUD_ELIMINACION_CUENTA (solicitud válida) y ELIMINACION_CUENTA (EXITO o FALLO
# con un motivo técnico), sin datos personales ni secretos. Sin job propio para tokens vencidos: un
# token vencido se audita una sola vez, cuando se intenta usar.

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core import security
from app.core.exceptions import AuthError
from app.emails.eventTypes import EmailEventType
from app.models.accountToken import AccountToken, TipoTokenCuenta
from app.models.externalIdentity import ExternalIdentity
from app.models.group import Group
from app.models.groupUser import GroupUser
from app.models.institutionUser import InstitutionUser
from app.models.localCredential import LocalCredential
from app.models.measurementProfile import MeasurementProfile
from app.models.mfaFactor import MfaFactor
from app.models.mfaRecoveryCode import MfaRecoveryCode
from app.models.user import User
from app.models.userSession import UserSession
from app.services import email as emailService
from app.services import mfa
from app.services import accountGrace
from app.services.audit import registerEvent
from app.services.auth import verifyCurrentPassword
from app.utils.timeZone import nowForDb

logger = logging.getLogger(__name__)

TOKEN_ELIMINAR_CUENTA = TipoTokenCuenta.ELIMINAR_CUENTA
TOKEN_VALIDITY_MINUTES = 30

ACCION_SOLICITUD = "SOLICITUD_ELIMINACION_CUENTA"
ACCION_ELIMINACION = "ELIMINACION_CUENTA"
ETAPA_SOLICITUD = "SOLICITUD"
ETAPA_CONFIRMACION = "CONFIRMACION"

ESTADO_ACTIVO = "ACTIVO"
# Valor de baja de Usuario admitido por CK_Usuario_estado / CK_Usuario_eliminacion.
ESTADO_ELIMINADO = "ELIMINADO"
ESTADO_RELACION_ACTIVO = "ACTIVO"
ESTADO_RELACION_BAJA = "BAJA"
GRUPO_CERRADO = "CERRADO"

TIPO_CONSUMIDOR_FINAL = "CONSUMIDOR_FINAL"
TIPO_INSTITUCIONAL = "USUARIO_INSTITUCIONAL"
SELF_DELETABLE_ACCOUNT_TYPES = frozenset({TIPO_CONSUMIDOR_FINAL, TIPO_INSTITUCIONAL})

ROL_PROPIETARIO = "PROPIETARIO"
ROL_OPERADOR = "OPERADOR"

# Motivos de FALLO (también son los códigos de error de la API).
MOTIVO_TOKEN_INVALIDO = "TOKEN_INVALIDO"  # nosec B105
MOTIVO_TOKEN_VENCIDO = "TOKEN_VENCIDO"  # nosec B105
MOTIVO_TOKEN_YA_UTILIZADO = "TOKEN_YA_UTILIZADO"  # nosec B105
MOTIVO_CUENTA_NO_ACTIVA = "CUENTA_NO_ACTIVA"
MOTIVO_PASSWORD_INCORRECTA = "PASSWORD_INCORRECTA"  # nosec B105
MOTIVO_PROPIETARIO_GRUPO = "PROPIETARIO_GRUPO_ACTIVO"
MOTIVO_VINCULO_INSTITUCIONAL = "VINCULO_INSTITUCIONAL_ACTIVO"
MOTIVO_PROPIETARIO_INSTITUCION = "PROPIETARIO_INSTITUCION_ACTIVA"
MOTIVO_TIPO_CUENTA = "TIPO_CUENTA_NO_ELIMINABLE"

ACTIVE_BONDS_MESSAGE = (
    "Tu cuenta está vinculada a una o más instituciones. Para eliminarla, primero debés finalizar tus vinculaciones institucionales."
)

# Listas que se muestran en CUENTA_ELIMINADA (descripciones, nunca valores).
DELETED_DATA = ["Nombre y apellido", "Correo electrónico", "Nombre de usuario", "Fecha de nacimiento", "Sexo",
                "Contraseña, acceso con Google y verificación en dos pasos"]
RETAINED_MEASUREMENT_DATA = ["Edad al momento de cada medición", "Sexo usado por el modelo de cada medición",
                             "Valores, fecha y contexto de cada medición (comida, dispositivo y sensor)"]


@dataclass(frozen=True)
class Blocker:
    code: str
    message: str


@dataclass(frozen=True)
class DeletionRequest:
    fechaExpiracion: datetime
    vigenciaMinutos: int = TOKEN_VALIDITY_MINUTES


# --- Reglas de Grupo / Institución ------------------------------------------------------


def findBlocker(db: Session, user: User) -> Blocker | None:
    """Primera condición que impide eliminar la cuenta, o None si puede eliminarse.

    Solo consulta: nunca modifica relaciones de Grupo ni de Institución.
    """
    if user.tipoCuenta not in SELF_DELETABLE_ACCOUNT_TYPES:
        # Las cuentas de plataforma no se crean por registro público ni se eliminan por autoservicio.
        return Blocker(MOTIVO_TIPO_CUENTA, "Este tipo de cuenta no puede eliminarse desde la cuenta propia.")

    # Un solo vínculo institucional ACTIVO bloquea, aunque las demás instituciones ya lo hayan dado de baja.
    activeRoles = set(
        db.scalars(
            select(InstitutionUser.rolInstitucion).where(
                InstitutionUser.idUsuarioInvitado == user.idUsuario,
                InstitutionUser.estadoRelacion == ESTADO_RELACION_ACTIVO,
            )
        )
    )
    if ROL_PROPIETARIO in activeRoles:
        return Blocker(MOTIVO_PROPIETARIO_INSTITUCION, ACTIVE_BONDS_MESSAGE)
    if activeRoles:
        return Blocker(MOTIVO_VINCULO_INSTITUCIONAL, ACTIVE_BONDS_MESSAGE)

    ownsActiveGroup = db.scalar(
        select(func.count())
        .select_from(GroupUser)
        .join(Group, Group.idGrupo == GroupUser.idGrupo)
        .where(
            GroupUser.idUsuario == user.idUsuario,
            GroupUser.rolGrupo == ROL_PROPIETARIO,
            GroupUser.estadoRelacion != ESTADO_RELACION_BAJA,
            Group.estado != GRUPO_CERRADO,
        )
    )
    if ownsActiveGroup:
        return Blocker(
            MOTIVO_PROPIETARIO_GRUPO,
            "No puede eliminar su cuenta mientras sea responsable de un grupo activo. "
            "Debe transferir la administración del grupo o darlo de baja.",
        )
    return None


# --- Auditoría ---------------------------------------------------------------------------


def _fail(db: Session, idUsuario: uuid.UUID | None, etapa: str, error: AuthError) -> AuthError:
    """Audita ELIMINACION_CUENTA FALLO con el código del error como motivo, confirma y devuelve el error."""
    registerEvent(
        db, "CRUD", ACCION_ELIMINACION, False, idUsuario, "Usuario", idUsuario,
        observacion=f"Motivo: {error.code}",
        datosNuevos={"etapa": etapa, "motivo": error.code},
    )
    db.commit()
    return error


# --- Reautenticación (paso 2) ---------------------------------------------------------------


def _verifyCurrentPassword(db: Session, user: User, credential: LocalCredential, password: str | None) -> None:
    """Reautenticación local. Comparte el contador y el bloqueo temporal de CredencialLocal con el login."""
    if password is None:
        raise AuthError("PASSWORD_REQUERIDA", "Ingresá tu contraseña actual para eliminar la cuenta.")
    if verifyCurrentPassword(db, credential, password):
        return
    raise _fail(
        db, user.idUsuario, ETAPA_CONFIRMACION, AuthError(MOTIVO_PASSWORD_INCORRECTA, "La contraseña es incorrecta.")
    )


def _verifyMfa(db: Session, user: User, codigo: str | None, codigoRecuperacion: str | None) -> None:
    if codigo is not None and codigoRecuperacion is not None:
        # Segunda barrera (además del schema).
        raise AuthError("FACTOR_MFA_DUPLICADO", "Indicá solo uno: codigo o codigoRecuperacion.")
    factor = mfa.getFactor(db, user)
    if factor is None or not factor.habilitado:
        return
    if codigo is None and codigoRecuperacion is None:
        raise AuthError("CODIGO_MFA_REQUERIDO", "Ingresá el código de verificación en dos pasos.")
    # verifyFactor aplica el bloqueo y audita los códigos inválidos (MFA_CODIGO_INVALIDO).
    mfa.verifyFactor(db, factor, codigo, codigoRecuperacion)


# --- Paso 1: solicitud --------------------------------------------------------------------


def requestDeletion(db: Session, user: User) -> DeletionRequest:
    """Paso 1. Valida las reglas de Grupo/Institución, genera el token y envía ELIMINACION_SOLICITADA.

    No pide contraseña ni MFA: la reautenticación se hace al confirmar (paso 2).
    """
    blocker = findBlocker(db, user)
    if blocker is not None:
        # Sin token mientras exista una condición que bloquee la baja.
        raise _fail(db, user.idUsuario, ETAPA_SOLICITUD, AuthError(blocker.code, blocker.message))

    now = nowForDb()
    expiration = now + timedelta(minutes=TOKEN_VALIDITY_MINUTES)
    # Una nueva solicitud invalida cualquier token de eliminación todavía pendiente.
    db.execute(
        delete(AccountToken).where(
            AccountToken.idUsuario == user.idUsuario,
            AccountToken.tipo == TOKEN_ELIMINAR_CUENTA,
            AccountToken.fechaUso.is_(None),
        )
    )
    token = security.generateOpaqueToken()
    db.add(
        AccountToken(
            idUsuario=user.idUsuario,
            tipo=TOKEN_ELIMINAR_CUENTA,
            tokenHash=security.hashOpaqueToken(token),
            fechaCreacion=now,
            fechaExpiracion=expiration,
        )
    )
    registerEvent(
        db, "CRUD", ACCION_SOLICITUD, True, user.idUsuario, "Usuario", user.idUsuario,
        datosNuevos={"solicitud": "GENERADA", "confirmacionRequerida": True, "vigenciaMinutos": TOKEN_VALIDITY_MINUTES},
    )
    db.commit()

    sent = emailService.sendEmailEvent(
        EmailEventType.ELIMINACION_SOLICITADA,
        user.correoElectronico,
        {
            "nombre": user.nombre,
            "fechaEvento": now,
            "fechaExpiracion": expiration,
            "urlConfirmacion": f"{emailService.frontendUrl('eliminarCuenta')}?token={token}",
            "urlProteccion": emailService.frontendUrl("seguridad"),
        },
    )
    if not sent:
        # El token queda generado pero sin enlace entregado; una nueva solicitud lo reemplaza.
        raise AuthError("CORREO_NO_ENVIADO", "No se pudo enviar el correo de confirmación. Intentá más tarde.")
    return DeletionRequest(fechaExpiracion=expiration)


# --- Paso 2: confirmación -----------------------------------------------------------------


def _consumeToken(db: Session, accountToken: AccountToken, now: datetime) -> bool:
    """Marca el token como usado solo si nadie lo usó antes (un solo uso, también en paralelo)."""
    result = db.execute(
        update(AccountToken)
        .where(AccountToken.idTokenCuenta == accountToken.idTokenCuenta, AccountToken.fechaUso.is_(None))
        .values(fechaUso=now)
    )
    return result.rowcount == 1


_USED_TOKEN_MESSAGE = "El enlace de eliminación ya fue utilizado."


def _validateToken(db: Session, token: str, now: datetime) -> AccountToken:
    """Valida el token sin consumirlo. Ante un token inválido, vencido o usado audita el FALLO y lanza AuthError.

    Un token reemplazado por una solicitud posterior ya no existe (se borra al pedir uno nuevo): es inválido.
    """
    accountToken = db.scalar(
        select(AccountToken).where(
            AccountToken.tokenHash == security.hashOpaqueToken(token),
            AccountToken.tipo == TOKEN_ELIMINAR_CUENTA,
        )
    )
    invalid = AuthError(MOTIVO_TOKEN_INVALIDO, "El enlace de eliminación es inválido.")
    expired = AuthError(MOTIVO_TOKEN_VENCIDO, "El enlace de eliminación venció. Solicitá la eliminación nuevamente.")
    used = AuthError(MOTIVO_TOKEN_YA_UTILIZADO, _USED_TOKEN_MESSAGE)
    if accountToken is None:
        raise _fail(db, None, ETAPA_CONFIRMACION, invalid)

    idUsuario = accountToken.idUsuario
    if accountToken.fechaUso is not None:
        if accountToken.fechaUso >= accountToken.fechaExpiracion:
            # Ya se auditó TOKEN_VENCIDO al primer intento posterior al vencimiento: no se duplica.
            raise expired
        raise _fail(db, idUsuario, ETAPA_CONFIRMACION, used)

    if accountToken.fechaExpiracion <= now:
        # Se inutiliza con fechaUso >= fechaExpiracion, lo que marca "consumido por vencimiento".
        if _consumeToken(db, accountToken, now):
            raise _fail(db, idUsuario, ETAPA_CONFIRMACION, expired)
        db.rollback()
        raise expired
    return accountToken


def _lockUser(db: Session, idUsuario: uuid.UUID) -> User | None:
    """Relee el Usuario con bloqueo de fila hasta el commit (evita bajas o cambios simultáneos)."""
    return accountGrace.lockUser(db, idUsuario)


def _leaveGroups(db: Session, idUsuario: uuid.UUID, now: datetime) -> int:
    """Salida automática de los grupos donde no es PROPIETARIO (ya validado). No borra la relación."""
    result = db.execute(
        update(GroupUser)
        .where(GroupUser.idUsuario == idUsuario, GroupUser.estadoRelacion != ESTADO_RELACION_BAJA)
        .values(estadoRelacion=ESTADO_RELACION_BAJA, fechaBaja=now)
    )
    return result.rowcount


def _preserveStaffIdentity(db: Session, user: User) -> int:
    """Copia nombre y apellido a las relaciones en las que la persona estuvo efectivamente incorporada (cualquier rol) y que aún no los
    tienen: la institución debe poder saber quién estuvo vinculado aunque la cuenta se anonimice. Una invitación que nunca se aceptó no
    conserva nada. Solo se completan los NULL: un valor histórico ya registrado no se pisa. Antes de anonimizar."""
    incorporated = (InstitutionUser.idUsuarioInvitado == user.idUsuario, InstitutionUser.fechaIncorporacion.is_not(None))
    db.execute(
        update(InstitutionUser)
        .where(*incorporated, InstitutionUser.nombreProfesionalHistorico.is_(None))
        .values(nombreProfesionalHistorico=user.nombre)
    )
    db.execute(
        update(InstitutionUser)
        .where(*incorporated, InstitutionUser.apellidoProfesionalHistorico.is_(None))
        .values(apellidoProfesionalHistorico=user.apellido)
    )
    return db.scalar(select(func.count()).select_from(InstitutionUser).where(*incorporated)) or 0


def _closePendingInvitations(db: Session, idUsuario: uuid.UUID, now: datetime) -> int:
    """Las invitaciones que seguían pendientes no pueden aceptarse más (la cuenta ya no existe operativamente): quedan canceladas, como
    una invitación que nunca se aceptó (BAJA sin incorporación). La relación se conserva."""
    result = db.execute(
        update(InstitutionUser)
        .where(InstitutionUser.idUsuarioInvitado == idUsuario, InstitutionUser.estadoRelacion == "PENDIENTE")
        .values(estadoRelacion=ESTADO_RELACION_BAJA, fechaBaja=now)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount


def _anonymizeMeasurementProfiles(db: Session, idUsuario: uuid.UUID, now: datetime) -> int:
    """Quita los datos identificativos del PerfilMedicion propio, sin borrarlo (lo referencian las mediciones).

    sexoModelo se conserva: es el parámetro del modelo (NOT NULL), igual que Medicion.sexoModelo.
    fechaDepuracionDatosPersonales cumple CK_PerfilMedicion_datoEdad al quitar la fecha de nacimiento.
    """
    result = db.execute(
        update(MeasurementProfile)
        .where(MeasurementProfile.idUsuario == idUsuario)
        .values(
            nombre=None, apellido=None, dni=None, fechaNacimiento=None, edadDeclarada=None,
            fechaDepuracionDatosPersonales=now,
        )
    )
    return result.rowcount


def _revokeAuthentication(db: Session, idUsuario: uuid.UUID, idTokenActual: uuid.UUID | None, now: datetime) -> None:
    factorIds = select(MfaFactor.idFactorMfa).where(MfaFactor.idUsuario == idUsuario)
    db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.idFactorMfa.in_(factorIds)))
    db.execute(delete(MfaFactor).where(MfaFactor.idUsuario == idUsuario))
    db.execute(delete(LocalCredential).where(LocalCredential.idUsuario == idUsuario))
    db.execute(delete(ExternalIdentity).where(ExternalIdentity.idUsuario == idUsuario))
    # El token de esta eliminación se conserva consumido para detectar su reutilización. Sin token (eliminación automática) caen todos.
    tokenFilter = [AccountToken.idTokenCuenta != idTokenActual] if idTokenActual is not None else []
    db.execute(delete(AccountToken).where(AccountToken.idUsuario == idUsuario, *tokenFilter))
    db.execute(
        update(UserSession)
        .where(UserSession.idUsuario == idUsuario, UserSession.fechaRevocacion.is_(None))
        .values(fechaRevocacion=now)
    )


def _anonymizeUser(user: User, now: datetime) -> None:
    # Todas las columnas personales admiten NULL; CK_Usuario_correo admite correo NULL en ELIMINADO.
    user.nombre = None
    user.apellido = None
    user.correoElectronico = None
    user.usuario = None
    user.fechaNacimiento = None
    user.sexo = None
    user.estado = ESTADO_ELIMINADO
    user.fechaEliminacion = now
    user.fechaActualizacion = now
    # El período de gracia (si lo había) termina con la eliminación: queda la fecha de eliminación.
    user.fechaInicioGracia = None
    user.fechaVencimientoGracia = None


@dataclass(frozen=True)
class Anonymization:
    gruposAbandonados: int
    vinculosConservados: int
    invitacionesCanceladas: int
    perfilesAnonimizados: int


def anonymizeAccount(db: Session, user: User, now: datetime, idTokenActual: uuid.UUID | None = None) -> Anonymization:
    """Núcleo común de la eliminación (voluntaria y automática). Sin commit: quien llama lo confirma junto con su auditoría.

    Usuario: se conserva idUsuario (lo referencian InstitucionUsuario, Auditoria, PerfilMedicion y otras tablas) y se ANONIMIZA —nombre,
    apellido, correo, nombre de usuario, fecha de nacimiento y sexo pasan a NULL—; estado ELIMINADO; sin contraseña, Google ni MFA, sin
    sesiones ni tokens. Los índices únicos de correo y usuario son filtrados (WHERE IS NOT NULL): varios NULL no chocan, por eso no se
    inventan valores «anonimizados» que podrían repetirse. notificarNuevoInicioSesion y las fechas técnicas se conservan (sin dato personal).
    """
    left = _leaveGroups(db, user.idUsuario, now)
    kept = _preserveStaffIdentity(db, user)
    closed = _closePendingInvitations(db, user.idUsuario, now)
    profiles = _anonymizeMeasurementProfiles(db, user.idUsuario, now)
    _revokeAuthentication(db, user.idUsuario, idTokenActual, now)
    _anonymizeUser(user, now)
    return Anonymization(left, kept, closed, profiles)


def describeDeletion(db: Session, user: User, now: datetime) -> dict:
    """Consecuencias de eliminar la cuenta, para mostrarlas antes de pedir la confirmación. Solo consulta."""
    blocker = findBlocker(db, user)
    pending = db.scalar(select(func.count()).select_from(InstitutionUser).where(
        InstitutionUser.idUsuarioInvitado == user.idUsuario, InstitutionUser.estadoRelacion == "PENDIENTE")) or 0
    incorporated = db.scalar(select(func.count()).select_from(InstitutionUser).where(
        InstitutionUser.idUsuarioInvitado == user.idUsuario, InstitutionUser.fechaIncorporacion.is_not(None))) or 0
    grace = accountGrace.graceOf(user, now)
    return {
        "puedeEliminar": blocker is None,
        "codigoBloqueo": blocker.code if blocker else None,
        "mensajeBloqueo": blocker.message if blocker else None,
        "datosEliminados": DELETED_DATA,
        "datosConservados": [
            "Las relaciones históricas con instituciones (rol, fechas, legajo, matrícula y nombre profesional), como parte de la nómina "
            "de cada institución y a disposición solo de su personal autorizado. No se eliminan por tiempo: la institución decide hasta "
            "cuándo conservarlas (la documentación de personal suele guardarse 10 años)",
            "La autoría de las mediciones que realizaste, sin tu cuenta ni tus datos de acceso",
            "El registro de auditoría de las operaciones",
        ] if incorporated else [],
        "invitacionesPendientes": pending,
        "periodoGracia": None if grace is None else {
            "fechaInicio": grace.fechaInicio, "fechaVencimiento": grace.fechaVencimiento, "diasRestantes": grace.diasRestantes},
        "reautenticacion": "Te vamos a pedir tu contraseña y, si lo activaste, el código de verificación en dos pasos.",
    }


def confirmDeletion(
    db: Session,
    token: str,
    password: str | None = None,
    codigo: str | None = None,
    codigoRecuperacion: str | None = None,
) -> None:
    """Paso 2. Token, reautenticación y reglas; luego la baja en una sola transacción y CUENTA_ELIMINADA.

    El token identifica la cuenta. Mientras no se confirme correctamente sigue vigente (hasta su
    vencimiento): una contraseña o un código equivocados, o un bloqueo de Grupo/Institución, permiten
    reintentar. Los reintentos comparten el bloqueo temporal del login y de MFA.
    """
    now = nowForDb()
    accountToken = _validateToken(db, token, now)
    user = _lockUser(db, accountToken.idUsuario)
    if user is None or user.estado != ESTADO_ACTIVO:
        raise _fail(
            db, accountToken.idUsuario, ETAPA_CONFIRMACION,
            AuthError(MOTIVO_CUENTA_NO_ACTIVA, "La cuenta no está activa."),
        )

    # Reautenticación antes de informar reglas: quien solo tiene el enlace no conoce los vínculos de la cuenta.
    credential = db.scalar(select(LocalCredential).where(LocalCredential.idUsuario == user.idUsuario))
    if credential is not None:
        _verifyCurrentPassword(db, user, credential, password)
    # Una cuenta solo Google no tiene contraseña local: no se pide.
    _verifyMfa(db, user, codigo, codigoRecuperacion)

    # La situación pudo cambiar desde la solicitud.
    blocker = findBlocker(db, user)
    if blocker is not None:
        raise _fail(db, user.idUsuario, ETAPA_CONFIRMACION, AuthError(blocker.code, blocker.message))

    if not _consumeToken(db, accountToken, now):
        # Otra confirmación consumió el mismo token entre la lectura y la escritura.
        db.rollback()
        raise _fail(
            db, accountToken.idUsuario, ETAPA_CONFIRMACION, AuthError(MOTIVO_TOKEN_YA_UTILIZADO, _USED_TOKEN_MESSAGE)
        )

    # Solo en memoria, para el aviso posterior al commit.
    recipient, nombre = user.correoElectronico, user.nombre
    try:
        hadGrace = user.fechaVencimientoGracia is not None
        result = anonymizeAccount(db, user, now, accountToken.idTokenCuenta)
        gruposAbandonados, vinculosOperador, perfiles = result.gruposAbandonados, result.vinculosConservados, result.perfilesAnonimizados
        registerEvent(
            db, "CRUD", ACCION_ELIMINACION, True, user.idUsuario, "Usuario", user.idUsuario,
            datosNuevos={
                "estadoAnterior": ESTADO_ACTIVO,
                "estadoNuevo": ESTADO_ELIMINADO,
                "datosPersonales": "ANONIMIZADOS",
                "autenticacion": "REVOCADA",
                "gruposAbandonados": gruposAbandonados,
                "perfilesMedicionAnonimizados": perfiles,
                "vinculosConservados": vinculosOperador,
                "invitacionesPendientesCanceladas": result.invitacionesCanceladas,
                "estabaEnPeriodoGracia": hadGrace,
            },
        )
        db.commit()
    except SQLAlchemyError:
        # Nada queda a medias: ni la baja, ni la salida de grupos, ni el consumo del token.
        db.rollback()
        logger.error("No se pudo completar la eliminación de la cuenta idUsuario=%s.", accountToken.idUsuario)
        raise

    # Después del commit. El envío en segundo plano nunca lanza: un fallo SMTP solo queda en el log.
    emailService.sendEmailEventInBackground(
        EmailEventType.CUENTA_ELIMINADA,
        recipient,
        {
            "nombre": nombre,
            "fechaEvento": now,
            "datosEliminados": DELETED_DATA,
            "datosConservados": RETAINED_MEASUREMENT_DATA if perfiles else None,
        },
    )
