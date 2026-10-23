# AuditQuery - Consulta de la auditoría con control de acceso por ámbito
#
# Quién consulta (se verifica siempre contra la base, nunca con datos que envíe el cliente):
#   - ADMINISTRADOR_PLATAFORMA (administrador del sistema): la auditoría general, de todos los módulos y de todas las
#     instituciones, con filtro opcional por institución.
#   - PROPIETARIO de una institución ACTIVA (permiso CONSULTAR_AUDITORIA): únicamente los eventos de ESA institución. El
#     filtro `idInstitucion = X` lo aplica la consulta SQL, donde X sale de la ruta ya validada contra su vínculo; no
#     existe parámetro para cambiarlo. Con varias instituciones elige una en la ruta, y solo puede elegir aquellas de las
#     que es propietario.
#   - Nadie más: moderador y operador institucional, integrantes de grupos, cuentas individuales y moderación de
#     plataforma reciben 403. Ellos generan eventos, pero no los consultan.
# Los intentos no autorizados quedan registrados (acción CONSULTAR_AUDITORIA, resultado FALLO) con un único alta, sin
# volver a consultar la auditoría: no hay recursión. Las consultas exitosas no se auditan (no generan ruido), salvo abrir la ficha de una
# CUENTA individual (CONSULTAR_AUDITORIA_CUENTA): es la consulta que más expone a una persona y queda a nombre de quien la hizo.
# Paginación, filtros y conteos se resuelven en SQL Server.
#
# Tres ámbitos de consulta (la administración los recorre desde una sola pantalla):
#   - Plataforma general: listGlobal / summaryGlobal sin filtro de institución ni de cuenta.
#   - Institución: la misma consulta con idInstitucion (administración) o la ruta de la institución (propietario).
#   - Cuenta individual: listGlobal con idCuenta (la cuenta como autora O como afectada), más accountHeader/searchAccounts.
# La IP de origen, el cliente y el identificador de correlación SOLO los devuelve la administración de la plataforma. La auditoría de una
# institución nunca los incluye, ni los eventos del módulo PLATAFORMA (registros internos de la administración).

import json
import re
import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import Select, and_, case, false, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.emails.formatting import maskEmail
from app.models.audit import Audit
from app.models.auditContext import AuditContext
from app.models.device import Device
from app.models.group import Group
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.localCredential import LocalCredential
from app.models.matrix import Matrix
from app.models.matrixRule import MatrixRule
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.profileTransfer import ProfileTransfer
from app.models.user import User
from app.schemas.auditLog import (
    AuditAccountHeader,
    AuditAccountMembership,
    AuditAccountOption,
    AuditAttribute,
    AuditChange,
    AuditCount,
    AuditEventDetail,
    AuditEventItem,
    AuditPage,
    AuditPatient,
    AuditReference,
    AuditSummary,
    AuditTransfer,
    AuditValue,
)
from app.services import auditClassification as classification
from app.services import institution as institutions
from app.services import mfa, schemaCompat, securityDetection
from app.services.audit import (
    ACCIONES_CRITICAS,
    MODULOS,
    PLATFORM_ACCOUNTS,
    RELATION_FIELDS,
    _referencedRelations,
    hashIdentifier,
    personName,
    registerEvent,
    sanitize,
)
from app.utils.normalizers import normalizeEmail
from app.utils.timeZone import nowForDb

ADMIN_ACCOUNT = "ADMINISTRADOR_PLATAFORMA"
MAX_PAGE_SIZE = 100
DENIED = "No tenés permiso para consultar la auditoría."
NOT_FOUND = "No encontramos ese evento."


def _error(code: str, message: str) -> AuthError:
    return AuthError(code, message)


# --- Autorización ------------------------------------------------------------------------------------------


def _denied(db: Session, actor: User, idInstitucion: uuid.UUID | None = None) -> AuthError:
    """Registra el intento no autorizado (un solo alta, sin recursión) y devuelve el 403."""
    registerEvent(db, "ACCESO", "CONSULTAR_AUDITORIA", False, actor.idUsuario, modulo="AUDITORIA",
                  idInstitucion=idInstitucion, observacion="Motivo: PERMISO_INSUFICIENTE", motivo="PERMISO_INSUFICIENTE")
    db.commit()
    return _error("PERMISO_INSUFICIENTE", DENIED)


def requireAdministrator(db: Session, actor: User) -> None:
    if actor.tipoCuenta != ADMIN_ACCOUNT or actor.estado != "ACTIVO":
        raise _denied(db, actor)


def requireOwner(db: Session, actor: User, idInstitucion: uuid.UUID) -> None:
    """Propietario ACTIVO de una institución ACTIVA. Quien no pertenece recibe 404 (no se revela qué existe); quien
    pertenece sin ser propietario (moderador u operador) recibe 403 y el intento queda en la auditoría de esa institución."""
    try:
        membership = institutions.requireMembership(db, actor, idInstitucion)
    except AuthError as error:
        if error.code == "PERMISO_INSUFICIENTE":  # cuenta que no es institucional (individual, plataforma)
            raise _denied(db, actor) from error
        raise
    if not membership.can(institutions.P_AUDITORIA):
        raise _denied(db, actor, idInstitucion)


# --- Consulta ------------------------------------------------------------------------------------------------


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


# Módulos de uso exclusivo de la administración: nunca aparecen en la auditoría de una institución.
ADMIN_ONLY_MODULES = ("PLATAFORMA",)
ORIGENES_ACTOR = ("PLATAFORMA", "USUARIO", "SISTEMA")
# Filtros que dependen de datos que solo ve la administración (IP, correlación, huella de un identificador): la auditoría de una institución
# no los admite.
ADMIN_ONLY_FILTERS = frozenset({"idInstitucion", "ip", "idCorrelacion", "identificador", "refIdentificador", "idCuenta"})
FILTER_DEFAULTS = dict(
    idInstitucion=None, idUsuario=None, usuario=None, modulo=None, accion=None, resultado=None, desde=None, hasta=None, critica=None,
    categoria=None, clasificacion=None, idCuenta=None, identificador=None, idCorrelacion=None, ip=None, motivo=None, origenActor=None,
    refIdentificador=None,
)
CONTEXT_FILTERS = ("idCorrelacion", "ip", "motivo", "refIdentificador")
_IP_TEXT = re.compile(r"^[0-9A-Fa-f.:*]{1,45}$")


def _contextWhere(*conditions):
    return Audit.idAuditoria.in_(select(AuditContext.idAuditoria).where(*conditions))


def _filtered(query: Select, **given) -> Select:
    f = {**FILTER_DEFAULTS, **given}
    if f["idInstitucion"] is not None:
        query = query.where(Audit.idInstitucion == f["idInstitucion"])
    if f["idUsuario"] is not None:
        query = query.where(Audit.idUsuario == f["idUsuario"])
    if f["idCuenta"] is not None:
        # La cuenta involucrada: la que obró o sobre la que se obró (alta, baja, bloqueo, invitación...).
        account = f["idCuenta"]
        query = query.where(or_(
            Audit.idUsuario == account,
            and_(Audit.tablaAfectada == "Usuario", Audit.idRegistro == account),
            and_(Audit.tablaRelacionada == "Usuario", Audit.idRelacionado == account),
        ))
    if f["usuario"] and f["usuario"].strip():
        term = _like(f["usuario"].strip())
        query = query.where(Audit.idUsuario.in_(
            select(User.idUsuario).where(
                (func.coalesce(User.nombre, "") + " " + func.coalesce(User.apellido, "") + " "
                 + func.coalesce(User.usuario, "")).ilike(term, escape="\\"))))
    if f["identificador"] and f["identificador"].strip():
        # Correo o nombre de usuario EXACTO: las cuentas que lo tienen y los intentos sobre ese identificador cuando no existía (por su huella).
        raw = f["identificador"].strip()
        accounts = select(User.idUsuario).where(or_(User.correoElectronico == normalizeEmail(raw) if "@" in raw else false(), User.usuario == raw))
        query = query.where(or_(Audit.idUsuario.in_(accounts), _contextWhere(AuditContext.identificadorHash.in_((hashIdentifier(raw), hashIdentifier(raw, legacy=True))))))
    if f["modulo"]:
        query = query.where(Audit.modulo == f["modulo"])
    if f["accion"] and f["accion"].strip():
        query = query.where(Audit.accion.ilike(_like(f["accion"].strip()), escape="\\"))
    if f["categoria"]:
        query = query.where(classification.categoryFilter(f["categoria"]))
    if f["clasificacion"]:
        query = query.where(classification.classificationFilter(f["clasificacion"]))
    if f["resultado"]:
        query = query.where(Audit.resultado == f["resultado"])
    if f["origenActor"]:
        platform = select(User.idUsuario).where(User.tipoCuenta.in_(PLATFORM_ACCOUNTS))
        if f["origenActor"] == "PLATAFORMA":
            query = query.where(Audit.idUsuario.in_(platform))
        elif f["origenActor"] == "SISTEMA":
            query = query.where(Audit.idUsuario.is_(None))
        else:
            query = query.where(Audit.idUsuario.is_not(None), Audit.idUsuario.not_in(platform))
    if f["desde"]:
        query = query.where(Audit.fechaHora >= datetime.combine(f["desde"], time.min))
    if f["hasta"]:
        query = query.where(Audit.fechaHora < datetime.combine(f["hasta"] + timedelta(days=1), time.min))
    if f["critica"] is True:
        query = query.where(Audit.accion.in_(ACCIONES_CRITICAS))
    if f["motivo"]:
        query = query.where(_contextWhere(AuditContext.motivo == f["motivo"]))
    if f["idCorrelacion"]:
        query = query.where(_contextWhere(AuditContext.idCorrelacion == f["idCorrelacion"].strip()))
    if f["refIdentificador"]:
        query = query.where(_contextWhere(AuditContext.identificadorHash == f["refIdentificador"].strip().lower()))
    if f["ip"]:
        ip = f["ip"].strip()
        condition = AuditContext.ipOrigen.like(ip[:-1].replace("%", "").replace("_", "") + "%") if ip.endswith("*") else AuditContext.ipOrigen == ip
        query = query.where(_contextWhere(condition))
    return query


def _scoped(query: Select, scope: uuid.UUID | None) -> Select:
    """Restricciones del ámbito. Institución: solo sus eventos y nunca los registros internos de la administración."""
    if scope is None:
        return query
    return query.where(Audit.idInstitucion == scope, or_(Audit.modulo.is_(None), Audit.modulo.not_in(ADMIN_ONLY_MODULES)))


def _validate(db: Session, filters: dict) -> dict:
    """Valida los filtros y devuelve los normalizados. Un filtro de red sin la tabla de contexto (AuditoriaContexto, esquema v5) se informa, no se ignora."""
    unknown = set(filters) - set(FILTER_DEFAULTS)
    if unknown:
        raise TypeError(f"Filtros de auditoría desconocidos: {sorted(unknown)}")
    f = {**FILTER_DEFAULTS, **filters}
    if f["modulo"] is not None and f["modulo"] not in MODULOS:
        raise _error("DATOS_INVALIDOS", "El módulo indicado no es válido.")
    if f["resultado"] is not None and f["resultado"] not in ("EXITO", "FALLO"):
        raise _error("DATOS_INVALIDOS", "El resultado indicado no es válido.")
    if f["categoria"] is not None and f["categoria"] not in classification.CATEGORIAS:
        raise _error("DATOS_INVALIDOS", "La categoría indicada no es válida.")
    if f["clasificacion"] is not None and f["clasificacion"] not in classification.CLASIFICACIONES:
        raise _error("DATOS_INVALIDOS", "La clasificación indicada no es válida.")
    if f["origenActor"] is not None and f["origenActor"] not in ORIGENES_ACTOR:
        raise _error("DATOS_INVALIDOS", "El origen indicado no es válido.")
    if f["ip"] is not None and not _IP_TEXT.match(f["ip"].strip()):
        raise _error("DATOS_INVALIDOS", "La dirección IP indicada no es válida.")
    if f["desde"] and f["hasta"] and f["hasta"] < f["desde"]:
        raise _error("PERIODO_INVALIDO", "La fecha final no puede ser anterior a la inicial.")
    if any(f[name] for name in CONTEXT_FILTERS) and not schemaCompat.auditContextReady(db):
        raise _error("ESQUEMA_DESACTUALIZADO", "La base de datos instalada no tiene la tabla que registra el origen de los eventos (AuditoriaContexto, esquema v5). Consultá a la administración del sistema.")
    return f


# --- Resolución de nombres (agrupada: sin una consulta por fila) ---------------------------------------------

UNAVAILABLE = "Usuario institucional no disponible"
DELETED_USER = "Usuario eliminado"
PLATFORM_LABEL = "Administración de GlucoLume"
FIELD_LABELS = {
    **RELATION_FIELDS, "estado": "Estado", "estadoRelacion": "Estado de la relación", "rolInstitucion": "Rol institucional",
    "rolRegistrante": "Rol de quien registró", "usuariosActivos": "Cuentas activas",
    "pacientesPendientes": "Pacientes pendientes de reasignación", "cuentaConservaOtrasInstituciones": "La cuenta conserva otras instituciones",
    "cuentasEnPeriodoGracia": "Cuentas en período de gracia", "fechaVencimiento": "Vencimiento", "fechaInicio": "Inicio", "dias": "Días",
    "fechaVencimientoGracia": "Vencimiento del período de gracia", "estabaEnPeriodoGracia": "Estaba en período de gracia",
    "vinculosConservados": "Vínculos institucionales conservados", "invitacionesPendientesCanceladas": "Invitaciones pendientes canceladas",
    "relacionesMinimizadas": "Relaciones minimizadas", "plazoMeses": "Plazo (meses)", "idReasignacionPaciente": "Tarea de reasignación",
    "origen": "Origen",
    "capacidadMaximaUsuarios": "Capacidad máxima", "reincorporacion": "Reincorporación", "campos": "Campos modificados", "versionFirmware": "Versión de firmware", "modeloSensor": "Modelo del sensor",
    "idInstitucion": "Institución", "motivo": "Motivo", "registroAutomatico": "Registro automático", "ambito": "Ámbito",
    "version": "Versión", "estadoAnterior": "Estado anterior", "mediciones": "Mediciones",
    "nombre": "Nombre", "descripcion": "Descripción", "tipoInstitucion": "Tipo de institución", "rolResponsable": "Rol del responsable",
    "cantidadReaperturas": "Cantidad de reaperturas", "idResponsable": "Responsable del dispositivo", "origen": "Origen",
    "apellido": "Apellido", "correoElectronico": "Correo electrónico", "funcionProfesional": "Función profesional",
    "tipoCuenta": "Tipo de cuenta", "cuenta": "Cuenta",
}
# Nombre funcional de las acciones que el nombre técnico no deja claras: distingue la asignación inicial, la solicitud, la
# aceptación con cambio efectivo, el rechazo y la cancelación de una transferencia.
ACTION_LABELS = {
    # Cuenta y acceso
    "LOGIN_LOCAL": "Inicio de sesión", "LOGIN_GOOGLE": "Inicio de sesión con Google", "REGISTRO_LOCAL": "Registro de cuenta",
    "REGISTRO_GOOGLE": "Registro de cuenta con Google", "VINCULACION_GOOGLE": "Vinculación de cuenta de Google",
    "CORREO_VERIFICADO": "Verificación de correo", "VERIFICACION_REENVIADA": "Reenvío de la verificación de correo",
    "CAMBIAR_PASSWORD": "Cambio de contraseña", "SOLICITAR_RECUPERACION_PASSWORD": "Solicitud de recuperación de contraseña",
    "RESTABLECER_PASSWORD": "Restablecimiento de contraseña", "CREDENCIAL_LOCAL_AGREGADA": "Contraseña agregada a la cuenta",
    "ACTUALIZAR_PERFIL": "Actualización del perfil", "PREFERENCIA_NOTIFICACION": "Cambio de preferencias de notificación",
    "MFA_HABILITADO": "Verificación en dos pasos activada", "MFA_DESHABILITADO": "Verificación en dos pasos desactivada",
    "MFA_CODIGO_INVALIDO": "Código de verificación incorrecto", "MFA_RECUPERACION_SOLICITADA": "Recuperación de verificación en dos pasos solicitada",
    "MFA_RECUPERACION_CODIGO_ENVIADO": "Código de recuperación enviado", "MFA_RECUPERACION_CODIGO_INVALIDO": "Código de recuperación incorrecto",
    "MFA_RECUPERACION_COMPLETADA": "Recuperación de verificación en dos pasos completada",
    "LOGIN_ACTIVACION_CUENTA": "Inicio de sesión al activar la cuenta",
    "LOGIN_RECUPERACION_MFA": "Inicio de sesión por recuperación de la verificación en dos pasos",
    "MFA_DESHABILITADO_POR_RECUPERACION": "Verificación en dos pasos desactivada por recuperación",
    "REFRESH_REUTILIZADO": "Sesión reutilizada (posible uso indebido)", "ACTIVAR_CUENTA_INVITADA": "Activación de cuenta invitada",
    "CREAR_CUENTA_INVITADA": "Creación de cuenta invitada", "ELIMINAR_CUENTA_NO_VERIFICADA_EXPIRADA": "Eliminación de cuenta sin verificar",
    # Instituciones
    "CREAR_INSTITUCION": "Creación de la institución", "NOTIFICAR_CREACION_INSTITUCION": "Aviso de creación de la institución",
    "MODIFICAR_INSTITUCION": "Modificación de datos de la institución", "ELIMINAR_INSTITUCION": "Eliminación de la institución",
    "REABRIR_INSTITUCION": "Reapertura de la institución", "INVITAR_MIEMBRO_INSTITUCION": "Invitación a la institución",
    "REENVIAR_INVITACION_INSTITUCION": "Reenvío de invitación a la institución",
    "RESPONDER_INVITACION_INSTITUCION": "Respuesta a una invitación institucional",
    "ACEPTAR_INVITACION_INSTITUCION": "Aceptar invitación institucional", "RECHAZAR_INVITACION_INSTITUCION": "Rechazar invitación institucional",
    "CANCELAR_INVITACION_INSTITUCION": "Cancelación de invitación institucional",
    "MODIFICAR_MIEMBRO_INSTITUCION": "Modificación de un integrante", "REVOCAR_MIEMBRO_INSTITUCION": "Baja de un integrante",
    "INICIAR_PERIODO_GRACIA": "Inicio del período de gracia de la cuenta", "CANCELAR_PERIODO_GRACIA": "Cancelación del período de gracia",
    "ELIMINACION_AUTOMATICA_CUENTA": "Eliminación automática de la cuenta", "MINIMIZAR_DATOS_PERSONAL_HISTORICO": "Minimización de datos históricos del personal",
    "ELIMINAR_DATOS_PERSONAL_HISTORICO": "Eliminación de datos históricos de una persona del personal",
    "PACIENTES_PENDIENTES_REASIGNACION": "Pacientes pendientes de reasignación", "CONSULTAR_REASIGNACIONES_PACIENTES": "Consulta de reasignaciones de pacientes",
    # Pacientes y transferencias
    "CREAR_PACIENTE": "Alta de paciente y asignación inicial de responsable", "MODIFICAR_PACIENTE": "Modificación de datos de un paciente",
    "BAJA_PACIENTE": "Baja de un paciente", "DEPURAR_DATOS_PACIENTES": "Depuración de datos personales de pacientes",
    "ANONIMIZAR_PACIENTES": "Anonimización de pacientes", "DEPURAR_MEDICIONES_RETENCION": "Eliminación de mediciones por fin de conservación",
    "CREAR_PERFIL_MEDICION": "Creación de perfil de medición", "CONSULTAR_PACIENTE": "Consulta de un paciente",
    "ASIGNAR_RESPONSABLE_ORIGEN": "Reasignación directa de responsable: operador anterior",
    "ASIGNAR_RESPONSABLE_PACIENTE": "Reasignación directa de responsable",
    "SOLICITAR_TRANSFERENCIA_PERFIL": "Solicitud de transferencia", "ACEPTAR_TRANSFERENCIA_PERFIL": "Transferencia aceptada",
    "RECHAZAR_TRANSFERENCIA_PERFIL": "Transferencia rechazada", "CANCELAR_TRANSFERENCIA_PERFIL": "Transferencia cancelada",
    "VENCER_TRANSFERENCIA_PERFIL": "Solicitud de transferencia vencida", "CAMBIAR_RESPONSABLE_PERFIL": "Responsable del paciente actualizado",
    # Mediciones
    "INICIAR_MEDICION": "Inicio de medición", "FINALIZAR_MEDICION": "Finalización de medición", "CANCELAR_MEDICION": "Cancelación de medición",
    "CAMBIAR_ESTADO_MEDICION": "Cambio de estado de una medición", "CANCELAR_SESION_ABANDONADA": "Cancelación de una sesión abandonada",
    "INVALIDAR_MEDICION_TIEMPO_AGOTADO": "Medición invalidada por tiempo agotado", "ENVIAR_RESULTADO_MEDICION": "Envío de resultado de medición",
    "ELIMINAR_DATOS_DEMO": "Eliminación de datos de demostración", "REGISTRAR_REFERENCIA_CAPILAR": "Registro de referencia capilar",
    "GUARDAR_MEDICION_DISPOSITIVO": "Medición guardada desde el dispositivo", "INICIAR_SESION_DISPOSITIVO": "Sesión de medición iniciada desde el dispositivo",
    # Dispositivos
    "REGISTRAR_DISPOSITIVO": "Registro de dispositivo", "MODIFICAR_DISPOSITIVO": "Modificación de dispositivo",
    "CAMBIAR_ESTADO_DISPOSITIVO": "Cambio de estado de dispositivo", "CAMBIAR_RESPONSABLE_DISPOSITIVO": "Cambio de responsable de dispositivo",
    "ASIGNAR_DISPOSITIVO": "Asignación de dispositivo a una institución", "DESVINCULAR_DISPOSITIVO": "Desvinculación de dispositivo",
    "DESCOMISIONAR_DISPOSITIVO": "Descomisión de dispositivo", "CONECTAR_DISPOSITIVO": "Conexión de dispositivo",
    "INICIAR_ADQUISICION": "Inicio de adquisición", "ERROR_COMUNICACION_DISPOSITIVO": "Error de comunicación con el dispositivo",
    "ACCEDER_INVENTARIO_DISPOSITIVOS": "Acceso al inventario de dispositivos", "CONSULTAR_DISPOSITIVO": "Consulta de dispositivo",
    "CONSULTAR_INVENTARIO_DISPOSITIVOS": "Consulta del inventario de dispositivos", "ORDEN_PUENTE_SERIE": "Orden al puente serie",
    "TOMAR_CONTROL_DISPOSITIVO": "Toma del control temporal del dispositivo", "SOLTAR_CONTROL_DISPOSITIVO": "Liberación del control del dispositivo",
    # Matrices
    "CREAR_MATRIZ": "Creación de matriz", "CREAR_VERSION_MATRIZ": "Nueva versión de matriz", "MODIFICAR_MATRIZ": "Modificación de matriz",
    "ACTIVAR_MATRIZ": "Activación de matriz", "DESACTIVAR_MATRIZ": "Desactivación de matriz", "ARCHIVAR_MATRIZ": "Archivo de matriz",
    "CREAR_REGLA_MATRIZ": "Creación de regla de matriz", "MODIFICAR_REGLA_MATRIZ": "Modificación de regla de matriz",
    "ELIMINAR_REGLA_MATRIZ": "Eliminación de regla de matriz", "ACCEDER_MATRIZ": "Acceso a una matriz",
    # Grupos
    "CREAR_GRUPO": "Creación de grupo familiar", "MODIFICAR_GRUPO": "Modificación de grupo familiar", "ELIMINAR_GRUPO": "Eliminación de grupo familiar",
    "INVITAR_GRUPO": "Invitación al grupo", "RESPONDER_INVITACION_GRUPO": "Respuesta a invitación al grupo",
    "ACEPTAR_INVITACION_GRUPO": "Invitación al grupo aceptada", "RECHAZAR_INVITACION_GRUPO": "Invitación al grupo rechazada",
    "CANCELAR_INVITACION_GRUPO": "Invitación al grupo cancelada", "ABANDONAR_GRUPO": "Salida del grupo",
    "DESVINCULAR_INTEGRANTE_GRUPO": "Integrante quitado del grupo", "TRANSFERIR_ADMINISTRACION_GRUPO": "Transferencia de la administración del grupo",
    "CONSULTAR_DATOS_GRUPO": "Consulta de datos del grupo", "CONSULTAR_DASHBOARD_GRUPO": "Consulta del dashboard del grupo",
    # Plataforma y auditoría
    "CONSULTAR_AUDITORIA": "Consulta de la auditoría", "CONSULTAR_MEDICIONES_PACIENTE": "Consulta de las mediciones de un paciente", "CONSULTAR_AUDITORIA_GLOBAL": "Consulta de la auditoría general",
    "INICIALIZAR_ADMINISTRADOR": "Inicialización del administrador", "INVITAR_MODERADOR_PLATAFORMA": "Invitación a moderación de plataforma",
    "REENVIAR_INVITACION_PLATAFORMA": "Reenvío de invitación a la plataforma", "REVOCAR_MODERADOR_PLATAFORMA": "Baja de moderación de plataforma",
    "ACTIVAR_CUENTA_PLATAFORMA": "Activación de cuenta de plataforma", "CAMBIAR_PASSWORD_PLATAFORMA": "Cambio de contraseña de plataforma",
    "RESTABLECER_PASSWORD_PLATAFORMA": "Restablecimiento de contraseña de plataforma", "RESTABLECER_PASSWORD_MODERADOR": "Restablecimiento de contraseña de moderación",
    "ACCESO_PLATAFORMA_DENEGADO": "Acceso a la plataforma denegado", "OPERACION_PLATAFORMA_DENEGADA": "Operación de plataforma denegada",
    "REAUTENTICACION_FALLIDA": "Reautenticación fallida",
    # Seguridad y exportaciones
    classification.ACCION_BLOQUEO_CUENTA: "Bloqueo temporal por intentos fallidos",
    classification.ACCION_LIMITE_SOLICITUDES: "Límite de solicitudes superado",
    classification.ACCION_RAFAGA_AUTORIZACION: "Ráfaga de solicitudes rechazadas (401/403)",
    classification.ACCION_RAFAGA_VALIDACION: "Ráfaga de entradas rechazadas por validación",
    classification.ACCION_EXPORT_SOLICITADA: "Exportación de datos solicitada",
    classification.ACCION_EXPORT_COMPLETADA: "Exportación de datos completada",
    classification.ACCION_EXPORT_FALLIDA: "Exportación de datos fallida o rechazada",
    classification.ACCION_CAMBIAR_LIMITE: "Cambio del límite de cuentas de la institución",
    classification.ACCION_CAMBIAR_VIGENCIA: "Cambio de la vigencia de la institución",
    classification.ACCION_DEPURAR_AUDITORIA: "Depuración de la auditoría por política de conservación",
    "CONSULTAR_AUDITORIA_CUENTA": "Consulta de la auditoría de una cuenta",
    "SOLICITAR_TRANSFERENCIA_ADMINISTRACION": "Solicitud de transferencia de la administración",
    "ACEPTAR_TRANSFERENCIA_ADMINISTRACION": "Transferencia de la administración aceptada",
    "RECHAZAR_TRANSFERENCIA_ADMINISTRACION": "Transferencia de la administración rechazada",
    "CANCELAR_TRANSFERENCIA_ADMINISTRACION": "Transferencia de la administración cancelada",
}
# Nombres de valores (estados, roles) por campo: la auditoría guarda los códigos; acá se muestran como los entiende una persona.
ROLE_VALUES = {"PROPIETARIO": "Propietario/a", "MODERADOR": "Moderador/a", "OPERADOR": "Operador/a"}
STATE_VALUES = {
    "ACTIVO": "Activo", "ACTIVA": "Activa", "PENDIENTE": "Pendiente", "BAJA": "Baja", "SUSPENDIDO": "Suspendido", "INACTIVA": "Inactiva",
    "CERRADA": "Cerrada", "ELIMINADA": "Eliminada", "OPERATIVO": "Operativo", "EN_MANTENIMIENTO": "En mantenimiento",
    "FUERA_DE_SERVICIO": "Fuera de servicio", "ACEPTADA": "Aceptada", "RECHAZADA": "Rechazada", "CANCELADA": "Cancelada",
    "VENCIDA": "Vencida", "COMPLETADA": "Completada", "INVALIDA": "Inválida", "ADQUIRIENDO": "Adquiriendo", "PROCESANDO": "Procesando",
    "ARCHIVADA": "Archivada", "BORRADOR": "Borrador", "ELIMINADO": "Eliminado",
}
# Cómo se nombra un campo SIN valor (NULL o inexistente en el registro anterior); distinto de un texto vacío.
NULL_LABELS = {"rolInstitucion": "Sin rol", "rolResponsable": "Sin rol", "estadoRelacion": "Sin estado", "estado": "Sin estado",
               "estadoAnterior": "Sin estado"}
VALUE_LABELS = {
    "rolInstitucion": ROLE_VALUES, "rolResponsable": ROLE_VALUES, "estadoRelacion": STATE_VALUES, "estado": STATE_VALUES,
    "estadoAnterior": STATE_VALUES, "rolRegistrante": ROLE_VALUES,
    "tipoCuenta": {"USUARIO_INSTITUCIONAL": "Cuenta institucional", "CONSUMIDOR_FINAL": "Cuenta individual",
                   "ADMINISTRADOR_PLATAFORMA": "Administración de plataforma", "MODERADOR_PLATAFORMA": "Moderación de plataforma"},
    "cuenta": {"NUEVA": "Nueva", "EXISTENTE": "Existente"},
    "tipoInstitucion": {"CONSULTORIO": "Consultorio", "CLINICA": "Clínica", "HOSPITAL": "Hospital", "LABORATORIO": "Laboratorio", "OTRO": "Otro"},
}
# Motivos técnicos normalizados (AuditoriaContexto.motivo): el sistema guarda el código; acá se muestra como lo entiende una persona.
MOTIVO_LABELS = {
    "PASSWORD_INCORRECTA": "Contraseña incorrecta", "CUENTA_INEXISTENTE": "Cuenta inexistente", "CUENTA_INACTIVA": "Cuenta inactiva o suspendida",
    "CORREO_NO_VERIFICADO": "Correo sin verificar", "CUENTA_BLOQUEADA": "Cuenta bloqueada temporalmente",
    "INTENTOS_EXCEDIDOS": "Intentos fallidos consecutivos", "SIN_CREDENCIAL_LOCAL": "Cuenta sin contraseña local",
    "CODIGO_MFA_INVALIDO": "Código de verificación incorrecto", "CODIGO_RECUPERACION_INVALIDO": "Código de recuperación incorrecto",
    "MFA_BLOQUEADO": "Segundo factor bloqueado temporalmente", "LIMITE_POR_ORIGEN": "Límite de solicitudes por origen",
    "RECHAZOS_REITERADOS": "Rechazos reiterados desde un mismo origen", "PERMISO_INSUFICIENTE": "Permiso insuficiente",
    "SIN_ROL_PLATAFORMA": "Cuenta sin rol de plataforma", "REAUTENTICACION_INVALIDA": "Reautenticación inválida",
    "CODIGO_ACTIVACION_INVALIDO": "Código de activación inválido", "CORREO_PROVEEDOR_NO_VERIFICADO": "Correo de Google sin verificar",
    "VINCULACION_RECHAZADA": "Vinculación rechazada", "CUENTA_NO_REGISTRADA": "Cuenta no registrada", "ERROR_INTERNO": "Error interno",
}
ENTITY_LABELS = {
    "Institucion": "Institución", "InstitucionUsuario": "Integrante de la institución", "PerfilMedicion": "Paciente",
    "TransferenciaPerfil": "Transferencia de paciente", "Medicion": "Medición", "Dispositivo": "Dispositivo", "Matriz": "Matriz",
    "Grupo": "Grupo familiar", "Usuario": "Cuenta", "ReglaMatriz": "Regla de matriz",
}


def _uuid(value):
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def _json(value) -> dict:
    try:
        parsed = json.loads(value) if value else {}
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class Resolver:
    """Resuelve, para una lista de eventos y en pocas consultas, los nombres de las personas y de las entidades.

    Reglas: solo se resuelven los campos de tipo conocido (relaciones institucionales, institución y entidades listadas);
    en la auditoría institucional solo se toman datos de relaciones de ESA institución. Orden de nombres: referencia
    guardada con el evento (`detalle`, identidad al momento de la operación) → identidad registrada en el vínculo
    (nombre/apellido profesional histórico) → nombre de la cuenta si sigue vigente → «Usuario institucional no disponible».
    """

    def __init__(self, db: Session, scope: uuid.UUID | None, identify: bool = False, maskMeasurements: bool = False):
        # identify: quien consulta puede ver datos identificativos de los pacientes de `scope` (el propietario de la
        # institución, que ya los consulta como paciente). La auditoría global nunca los muestra.
        # maskMeasurements: en los eventos de MEDICIÓN (la medición misma o un intento de consultar las de un paciente) no se dice de
        # qué paciente son ni se expone su identificador: el propietario audita que se midió y quién lo hizo, pero la medición individual
        # es dato de salud al que solo accede el operador responsable (patientAccess).
        self.db, self.scope, self.identify = db, scope, identify and scope is not None
        self.maskMeasurements = maskMeasurements and scope is not None
        self.identities: dict[uuid.UUID, tuple[str | None, bool]] = {}
        self.relations: dict[uuid.UUID, tuple[InstitutionUser, User | None]] = {}
        self.actors: dict[uuid.UUID, User] = {}
        self.actorLinks: dict[uuid.UUID, tuple[InstitutionUser, User | None]] = {}
        self.labels: dict[tuple[str, uuid.UUID], str] = {}
        self.institutions: dict[uuid.UUID, str] = {}
        # Transferencias de perfiles: id -> (perfil, destino, origen); el perfil se nombra por su identificador.
        self.transfers: dict[uuid.UUID, tuple] = {}
        self.profiles: dict[uuid.UUID, str] = {}

    def prepare(self, audits: list[Audit]) -> None:
        relationIds, actorIds, entities = set(), set(), {}
        for audit in audits:
            if audit.idUsuario:
                actorIds.add(audit.idUsuario)
            blobs = (_json(audit.datosPrevios), _json(audit.datosNuevos))
            relationIds |= _referencedRelations(audit.tablaAfectada, audit.idRegistro, audit.tablaRelacionada,
                                                audit.idRelacionado, *blobs)
            if audit.idInstitucion:
                self.institutions[audit.idInstitucion] = ""
            for blob in blobs:
                institution = _uuid(blob.get("idInstitucion"))
                if institution:
                    self.institutions[institution] = ""
            if audit.tablaAfectada and audit.idRegistro:
                entities.setdefault(audit.tablaAfectada, set()).add(audit.idRegistro)
        self._loadTransfers(entities.get("TransferenciaPerfil", ()), relationIds)
        if relationIds:
            query = (select(InstitutionUser, User).outerjoin(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
                     .where(InstitutionUser.idInstitucionUsuario.in_(relationIds)))
            if self.scope is not None:  # un UUID de otra institución no se resuelve
                query = query.where(InstitutionUser.idInstitucion == self.scope)
            for relation, user in self.db.execute(query).all():
                self.relations[relation.idInstitucionUsuario] = (relation, user)
                self.institutions[relation.idInstitucion] = ""  # institución de cada integrante, en la misma resolución agrupada
        if actorIds:
            self.actors = {u.idUsuario: u for u in self.db.scalars(select(User).where(User.idUsuario.in_(actorIds)))}
            if self.scope is not None:
                links = self.db.execute(
                    select(InstitutionUser, User).outerjoin(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
                    .where(InstitutionUser.idInstitucion == self.scope, InstitutionUser.idUsuarioInvitado.in_(actorIds))
                    .order_by(InstitutionUser.fechaInvitacion)
                ).all()
                for relation, user in links:  # el vínculo más reciente de cada persona en esta institución
                    self.actorLinks[relation.idUsuarioInvitado] = (relation, user)
        self._loadEntities(entities)
        names = self.institutions
        if names:
            for institution in self.db.scalars(select(Institution).where(Institution.idInstitucion.in_(set(names)))):
                names[institution.idInstitucion] = institution.nombre

    def _loadTransfers(self, ids, relationIds: set) -> None:
        """Perfil, destino y origen de cada transferencia, en dos consultas (también para eventos anteriores que solo
        guardaron el id de la transferencia). El origen sale del evento que la solicitó."""
        if not ids:
            return
        db = self.db
        rows = db.execute(
            select(ProfileTransfer.idTransferenciaPerfil, ProfileTransfer.idPerfilMedicion, ProfileTransfer.idOperadorDestino,
                   MeasurementProfile.identificadorPseudonimo, MeasurementProfile.nombre, MeasurementProfile.apellido,
                   MeasurementProfile.fechaDepuracionDatosPersonales, InstitutionUser.idInstitucion)
            .join(MeasurementProfile, MeasurementProfile.idPerfilMedicion == ProfileTransfer.idPerfilMedicion)
            .outerjoin(InstitutionUser, InstitutionUser.idInstitucionUsuario == MeasurementProfile.idInstitucionUsuarioResponsable)
            .where(ProfileTransfer.idTransferenciaPerfil.in_(ids))
        ).all()
        origins = dict(db.execute(
            select(Audit.idRegistro, Audit.idRelacionado)
            .where(Audit.tablaAfectada == "TransferenciaPerfil", Audit.idRegistro.in_(ids),
                   Audit.accion == "SOLICITAR_TRANSFERENCIA_PERFIL", Audit.idRelacionado.is_not(None))
        ).all())
        for transferId, profileId, destId, pseudonym, first, last, purged, profileInstitution in rows:
            self.transfers[transferId] = (profileId, destId, origins.get(transferId))
            if pseudonym:
                self.profiles[profileId] = pseudonym
            # Nombre y apellido solo con autorización y si el perfil pertenece a la institución consultada.
            if self.identify and profileInstitution == self.scope:
                name = None if purged is not None else (f"{first or ''} {last or ''}".strip() or None)
                self.identities[profileId] = (name, name is not None)
            relationIds |= {destId, origins.get(transferId)} - {None}

    def transfer(self, audit: Audit, snapshot: dict) -> AuditTransfer | None:
        """Paciente, operador de origen y operador destinatario de un evento de transferencia."""
        if audit.tablaAfectada != "TransferenciaPerfil":
            return None
        saved = self.transfers.get(audit.idRegistro, (None, None, None))
        data = {**_json(audit.datosPrevios), **_json(audit.datosNuevos)}
        profileId = _uuid(data.get("idPerfilMedicion")) or saved[0]
        destId = _uuid(data.get("idOperadorDestino")) or saved[1]
        originId = audit.idRelacionado if audit.tablaRelacionada == "InstitucionUsuario" and audit.idRelacionado else saved[2]
        name, available = self.identities.get(profileId, (None, None))
        return AuditTransfer(
            paciente=AuditPatient(id=str(profileId) if profileId else None, identificador=self.profiles.get(profileId),
                                  nombreCompleto=name, datosIdentificativos=available),
            origen=self.person(originId, snapshot) if originId else AuditValue(texto=UNAVAILABLE, disponible=False),
            destino=self.person(destId, snapshot) if destId else AuditValue(texto=UNAVAILABLE, disponible=False),
        )

    def _loadEntities(self, entities: dict) -> None:
        db = self.db
        for tabla, ids in entities.items():
            if tabla == "Dispositivo":
                for row in db.execute(select(Device.idDispositivo, Device.codigoDispositivo).where(Device.idDispositivo.in_(ids))):
                    self.labels[(tabla, row[0])] = f"Dispositivo {row[1]}"
            elif tabla == "PerfilMedicion":
                for row in db.execute(select(MeasurementProfile.idPerfilMedicion, MeasurementProfile.identificadorPseudonimo)
                                      .where(MeasurementProfile.idPerfilMedicion.in_(ids))):
                    self.labels[(tabla, row[0])] = f"Paciente {row[1]}" if row[1] else "Perfil de medición"
                    if row[1]:
                        self.profiles[row[0]] = row[1]
            elif tabla == "TransferenciaPerfil":
                rows = db.execute(
                    select(ProfileTransfer.idTransferenciaPerfil, MeasurementProfile.identificadorPseudonimo)
                    .join(MeasurementProfile, MeasurementProfile.idPerfilMedicion == ProfileTransfer.idPerfilMedicion)
                    .where(ProfileTransfer.idTransferenciaPerfil.in_(ids)))
                for row in rows:
                    self.labels[(tabla, row[0])] = f"Transferencia del paciente {row[1]}" if row[1] else "Transferencia de paciente"
            elif tabla == "Matriz":
                for row in db.execute(select(Matrix.idMatriz, Matrix.nombre, Matrix.version).where(Matrix.idMatriz.in_(ids))):
                    self.labels[(tabla, row[0])] = f"Matriz {row[1]}, versión {row[2]}"
            elif tabla == "Institucion":
                for row in db.execute(select(Institution.idInstitucion, Institution.nombre).where(Institution.idInstitucion.in_(ids))):
                    self.labels[(tabla, row[0])] = f"Institución {row[1]}"
            elif tabla == "Grupo":
                for row in db.execute(select(Group.idGrupo, Group.nombre).where(Group.idGrupo.in_(ids))):
                    self.labels[(tabla, row[0])] = f"Grupo {row[1]}"
            elif tabla == "ReglaMatriz":
                rows = db.execute(select(MatrixRule.idReglaMatriz, MatrixRule.codigoRegla, Matrix.nombre, Matrix.version)
                                  .join(Matrix, Matrix.idMatriz == MatrixRule.idMatriz).where(MatrixRule.idReglaMatriz.in_(ids)))
                for row in rows:
                    self.labels[(tabla, row[0])] = f"Regla {row[1]} de la matriz {row[2]}, versión {row[3]}"
            elif tabla == "Medicion":
                # Una medición no tiene nombre propio: se la identifica por fecha, modo y el seudónimo del paciente (nunca su nombre).
                rows = db.execute(select(Measurement.idMedicion, Measurement.fechaHoraInicio, Measurement.modoMedicion,
                                         MeasurementProfile.identificadorPseudonimo)
                                  .join(MeasurementProfile, MeasurementProfile.idPerfilMedicion == Measurement.idPerfilMedicion)
                                  .where(Measurement.idMedicion.in_(ids)))
                for row in rows:
                    who = f" del paciente {row[3]}" if row[3] and not self.maskMeasurements else ""
                    self.labels[(tabla, row[0])] = f"Medición {row[2].lower().replace('_', ' ')}{who}, {row[1]:%d/%m/%Y %H:%M}"
            elif tabla == "Usuario":
                self._loadAccounts(ids)

    def _loadAccounts(self, ids) -> None:
        """Cuenta afectada por un evento. En la auditoría de una institución solo se nombra si es integrante de ESA institución
        (por la identidad registrada en su vínculo); en la general, por el nombre de la cuenta mientras siga vigente. Una cuenta
        eliminada o anonimizada no se recupera: se indica como eliminada."""
        db = self.db
        users = {u.idUsuario: u for u in db.scalars(select(User).where(User.idUsuario.in_(ids)))}
        links = {}
        if self.scope is not None:
            for relation in db.scalars(select(InstitutionUser).where(
                    InstitutionUser.idInstitucion == self.scope, InstitutionUser.idUsuarioInvitado.in_(ids))
                    .order_by(InstitutionUser.fechaInvitacion)):
                links[relation.idUsuarioInvitado] = relation
        for userId in ids:
            user = users.get(userId)
            name = personName(links.get(userId), user) if self.scope is not None else (_fullName(user) if user and user.estado != "ELIMINADO" else None)
            if name:
                self.labels[("Usuario", userId)] = f"Cuenta de {name}"
            elif user is not None and user.estado == "ELIMINADO":
                self.labels[("Usuario", userId)] = "Cuenta eliminada"

    # -- personas --------------------------------------------------------------------------------------------

    def person(self, relationId, snapshot: dict) -> AuditValue:
        key = _uuid(relationId)
        saved = (snapshot.get("personas") or {}).get(str(key)) if key else None
        found = self.relations.get(key) if key else None
        savedName = (saved or {}).get("nombreCompleto")
        if found and found[0].fechaMinimizacionDatos is not None:
            savedName = None  # vencido el plazo de conservación: tampoco el nombre guardado en el evento identifica a la persona
        currentName = personName(*found) if found else None
        name = savedName or currentName
        role = (saved or {}).get("rol") or (found[0].rolInstitucion if found else None)
        # Lo registrado en el evento manda sobre lo vigente hoy; si solo hay dato vigente, se marca como tal.
        origin = "EVENTO" if savedName else ("ACTUAL" if currentName else None)
        return AuditValue(id=str(relationId) if relationId else None, texto=name or self._unavailable(found), rol=role,
                          disponible=bool(name), origen=origin)

    @staticmethod
    def _unavailable(found) -> str:
        """Sin nombre recuperable: si la cuenta fue eliminada se dice; si no, que la información no está disponible."""
        return DELETED_USER if found and found[1] is not None and found[1].estado == "ELIMINADO" else UNAVAILABLE

    def actor(self, audit: Audit, snapshot: dict) -> str | None:
        if audit.idUsuario is None:
            return None
        saved = snapshot.get("actor") or {}
        user = self.actors.get(audit.idUsuario)
        if saved.get("rol") == "PLATAFORMA" or (self.scope is not None and user is not None
                                                 and user.tipoCuenta in PLATFORM_ACCOUNTS):
            return PLATFORM_LABEL if self.scope is not None else (_fullName(user) or PLATFORM_LABEL)
        if self.scope is not None:
            link = self.actorLinks.get(audit.idUsuario)
            if link and link[0].fechaMinimizacionDatos is not None:
                return UNAVAILABLE  # datos del personal suprimidos: ni el nombre guardado en el evento se muestra
        if saved.get("nombreCompleto"):
            return saved["nombreCompleto"]
        if self.scope is not None:
            return (personName(*link) if link else None) or UNAVAILABLE
        if user is not None and user.estado == "ELIMINADO":
            return DELETED_USER
        return _fullName(user) if user else UNAVAILABLE

    def origin(self, audit: Audit, snapshot: dict) -> str:
        """PLATAFORMA (administración de GlucoLume), USUARIO (cuenta de una institución o individual) o SISTEMA (sin cuenta)."""
        if audit.idUsuario is None:
            return "SISTEMA"
        user = self.actors.get(audit.idUsuario)
        if (snapshot.get("actor") or {}).get("rol") == "PLATAFORMA" or (user is not None and user.tipoCuenta in PLATFORM_ACCOUNTS):
            return "PLATAFORMA"
        return "USUARIO"

    def hidesPatient(self, audit: Audit) -> bool:
        """Evento de medición visto por quien no puede identificar al paciente (ver maskMeasurements)."""
        return self.maskMeasurements and (audit.tablaAfectada == "Medicion" or audit.accion in MEASUREMENT_ACCESS_ACTIONS)

    def entityId(self, audit: Audit) -> uuid.UUID | None:
        """Id de la entidad afectada; en un acceso a mediciones es el del paciente, que no se expone."""
        return None if self.hidesPatient(audit) and audit.tablaAfectada == "PerfilMedicion" else audit.idRegistro

    def _patient(self, audit: Audit, snapshot: dict) -> str | None:
        if self.hidesPatient(audit):
            return None
        if audit.tablaAfectada == "TransferenciaPerfil":
            info = self.transfer(audit, snapshot)
            return info.paciente.identificador if info else None
        if audit.tablaAfectada == "PerfilMedicion":
            return self.profiles.get(audit.idRegistro)
        return None

    def summary(self, audit: Audit, snapshot: dict) -> str | None:
        """Frase funcional de la operación (quién hizo qué, con qué paciente y entre qué operadores)."""
        patient = self._patient(audit, snapshot)
        if patient is None:
            return None
        action, who = audit.accion, self.actor(audit, snapshot) or "El sistema"
        if audit.tablaAfectada == "TransferenciaPerfil":
            info = self.transfer(audit, snapshot)
            origin, dest = info.origen.texto, info.destino.texto
            patient = _phrase(info.paciente) or patient  # con nombre y apellido si está autorizado
            return {
                "SOLICITAR_TRANSFERENCIA_PERFIL": f"{who} solicitó transferir al paciente {patient}{"," if info.paciente.nombreCompleto else ""} a {dest}. "
                                                  f"La responsabilidad permanecerá con {origin} hasta que {dest} acepte la solicitud.",
                "ACEPTAR_TRANSFERENCIA_PERFIL": f"{who} aceptó la transferencia del paciente {patient}. "
                                                f"El responsable cambió de {origin} a {dest}.",
                "RECHAZAR_TRANSFERENCIA_PERFIL": f"{who} rechazó la solicitud de transferencia del paciente {patient}. "
                                                 f"El responsable continúa siendo {origin}.",
                "CANCELAR_TRANSFERENCIA_PERFIL": f"{who} canceló la solicitud de transferencia del paciente {patient}. "
                                                 f"El responsable continúa siendo {origin}.",
                "VENCER_TRANSFERENCIA_PERFIL": f"La solicitud de transferencia del paciente {patient} perdió vigencia "
                                               f"porque el responsable cambió o dejó de estar activo.",
                "ASIGNAR_RESPONSABLE_ORIGEN": (f"{who} reasignó el paciente {patient} de {origin} a {dest}." if info.origen.id
                                               else f"Se asignó el paciente {patient} al operador {dest}."),
            }.get(action)
        new, old = _json(audit.datosNuevos), _json(audit.datosPrevios)
        target = new.get("idInstitucionUsuarioResponsable")
        if target is None:
            return None
        dest = self.person(target, snapshot).texto
        if action == "CREAR_PACIENTE":
            return f"Se asignó el paciente {patient} al operador {dest}."
        origin = self.person(old["idInstitucionUsuarioResponsable"], snapshot).texto if old.get("idInstitucionUsuarioResponsable") else None
        if action == "CAMBIAR_RESPONSABLE_PERFIL" and new.get("idTransferenciaPerfil") and origin:
            return f"El responsable del paciente {patient} cambió de {origin} a {dest} por una transferencia aceptada."
        if action in ("CAMBIAR_RESPONSABLE_PERFIL", "ASIGNAR_RESPONSABLE_PACIENTE") and origin:
            return f"{who} cambió el responsable del paciente {patient} de {origin} a {dest}."
        return None

    def entity(self, audit: Audit, snapshot: dict) -> AuditValue | None:
        """La entidad afectada con su tipo, su nombre y sus datos descriptivos. Un dato registrado en el evento se presenta como
        tal (EVENTO); uno que solo se conoce por el registro vigente se marca ACTUAL. No se confunde con quien realizó la operación."""
        tabla = audit.tablaAfectada
        if not tabla:
            return None
        text = self.entityLabel(audit, snapshot) or tabla
        entityId = self.entityId(audit)
        value = AuditValue(id=str(entityId) if entityId else None, texto=text, tipo=ENTITY_LABELS.get(tabla, tabla))
        if tabla != "InstitucionUsuario" or not audit.idRegistro:
            if tabla in ("Institucion", "Grupo", "Usuario") and (tabla, audit.idRegistro) in self.labels:
                value.origen = "ACTUAL"  # nombre que puede cambiar: es el vigente hoy, no necesariamente el del momento del evento
            return value
        person = self.person(audit.idRegistro, snapshot)
        found = self.relations.get(audit.idRegistro)
        new, old = _json(audit.datosNuevos), _json(audit.datosPrevios)
        attributes = []
        # Rol: el que el evento asignó (registrado) o, si no lo informa, el vigente.
        if new.get("rolInstitucion"):
            attributes.append(AuditAttribute(etiqueta="Rol asignado", texto=ROLE_VALUES.get(new["rolInstitucion"], str(new["rolInstitucion"])), origen="EVENTO"))
        elif person.rol:
            attributes.append(AuditAttribute(etiqueta="Rol", texto=ROLE_VALUES.get(person.rol, person.rol),
                                             origen="EVENTO" if (snapshot.get("personas") or {}).get(str(audit.idRegistro), {}).get("rol") else "ACTUAL"))
        if new.get("estadoRelacion") or old.get("estadoRelacion"):
            state = new.get("estadoRelacion") or old.get("estadoRelacion")
            attributes.append(AuditAttribute(etiqueta="Estado de la relación", texto=STATE_VALUES.get(state, str(state)), origen="EVENTO"))
        elif found:
            attributes.append(AuditAttribute(etiqueta="Estado de la relación (actual)",
                                             texto=STATE_VALUES.get(found[0].estadoRelacion, found[0].estadoRelacion), origen="ACTUAL"))
        if found:
            institution = self.institutions.get(found[0].idInstitucion)
            if institution:
                attributes.append(AuditAttribute(etiqueta="Pertenece a", texto=institution))
            # El usuario de la cuenta solo lo ve la auditoría general y mientras la cuenta siga vigente.
            if self.scope is None and found[1] is not None and found[1].estado != "ELIMINADO" and found[1].usuario:
                attributes.append(AuditAttribute(etiqueta="Cuenta de usuario", texto=f"@{found[1].usuario}", origen="ACTUAL"))
        value.texto, value.rol, value.origen, value.disponible = person.texto, person.rol, person.origen, person.disponible
        value.atributos = attributes
        return value

    def references(self, audit: Audit, snapshot: dict, entity: AuditValue | None, related: AuditValue | None) -> list[AuditReference]:
        """Identificadores internos para trazabilidad, cada uno con el nombre resuelto al lado (el UUID no se reemplaza)."""
        refs = [AuditReference(etiqueta="Identificador del evento", id=str(audit.idAuditoria))]
        if audit.idInstitucion:
            name = self.institutions.get(audit.idInstitucion)
            refs.append(AuditReference(etiqueta="Institución (identificador interno)", id=str(audit.idInstitucion), nombre=name or None,
                                       origen="ACTUAL" if name else None, disponible=bool(name)))
        if entity and entity.id:
            refs.append(AuditReference(etiqueta="Entidad afectada", id=entity.id, nombre=entity.texto, origen=entity.origen,
                                       disponible=entity.disponible))
        if related and related.id:
            refs.append(AuditReference(etiqueta="Persona relacionada", id=related.id, nombre=related.texto, origen=related.origen,
                                       disponible=related.disponible))
        if audit.idUsuario:
            actor = self.actor(audit, snapshot)
            saved = (snapshot.get("actor") or {}).get("nombreCompleto")
            if self.scope is not None:
                link = self.actorLinks.get(audit.idUsuario)  # en la institución: su vínculo; la cuenta no se expone
                refs.append(AuditReference(etiqueta="Responsable de la operación (vínculo)", id=str(link[0].idInstitucionUsuario) if link else None,
                                           nombre=actor, origen="EVENTO" if saved else "ACTUAL", disponible=actor not in (UNAVAILABLE, DELETED_USER)))
            else:
                refs.append(AuditReference(etiqueta="Responsable de la operación (cuenta)", id=str(audit.idUsuario), nombre=actor,
                                           origen="EVENTO" if saved else "ACTUAL", disponible=actor not in (UNAVAILABLE, DELETED_USER)))
        return refs

    def entityLabel(self, audit: Audit, snapshot: dict) -> str | None:
        tabla = audit.tablaAfectada
        if tabla is None:
            return None
        if tabla == "InstitucionUsuario" and audit.idRegistro:
            person = self.person(audit.idRegistro, snapshot)
            return f"{person.texto}" + (f" ({ROLE_LABELS.get(person.rol, person.rol)})" if person.rol and person.disponible else "")
        if tabla == "TransferenciaPerfil":
            info = self.transfer(audit, snapshot)  # el paciente; origen y destino van en campos propios
            return f"Paciente {info.paciente.identificador}" if info and info.paciente.identificador else ENTITY_LABELS[tabla]
        if tabla == "PerfilMedicion" and self.hidesPatient(audit):
            return "Paciente sin identificar"
        return self.labels.get((tabla, audit.idRegistro)) or ENTITY_LABELS.get(tabla, tabla)


ROLE_LABELS = {"PROPIETARIO": "propietario/a", "MODERADOR": "moderador/a", "OPERADOR": "operador/a"}


def _phrase(patient: AuditPatient) -> str | None:
    """«Ana Paz, identificado como PAC-…» si el nombre está autorizado; si no, el identificador."""
    if patient.nombreCompleto:
        return f"{patient.nombreCompleto}, identificado como {patient.identificador}"
    return patient.identificador


def _fullName(user: User | None) -> str | None:
    if user is None:
        return None
    return (f"{user.nombre or ''} {user.apellido or ''}".strip()) or user.usuario


def _item(audit: Audit, resolver: Resolver, institution: Institution | None, *, showInstitution: bool,
          context: AuditContext | None = None, network: bool = False) -> dict:
    """`network`: solo la administración de la plataforma recibe IP, cliente, correlación y referencia del identificador."""
    snapshot = _json(audit.detalle)
    motivo = context.motivo if context is not None else None
    kind = classification.classify(audit.accion, audit.resultado)
    user = resolver.actor(audit, snapshot)
    if user is None and motivo == "CUENTA_INEXISTENTE":
        user = "Cuenta no registrada"
    return dict(
        idAuditoria=audit.idAuditoria, fechaHora=audit.fechaHora, usuario=user, modulo=audit.modulo,
        accion=audit.accion, tipoEntidad=audit.tablaAfectada, idEntidad=resolver.entityId(audit),
        idInstitucion=audit.idInstitucion,
        nombreInstitucion=institution.nombre if (showInstitution and institution) else None,
        resultado=audit.resultado, descripcion=audit.observacion, critica=audit.accion in ACCIONES_CRITICAS,
        rechazado=audit.resultado == "FALLO" and audit.tipoEvento in ("PERMISO", "ACCESO"),
        entidadEtiqueta=resolver.entityLabel(audit, snapshot), accionEtiqueta=ACTION_LABELS.get(audit.accion),
        resumen=resolver.summary(audit, snapshot),
        severidad=classification.severity(audit.accion, audit.resultado, audit.tipoEvento, kind), clasificacion=kind,
        origenActor=resolver.origin(audit, snapshot), motivo=motivo, motivoEtiqueta=MOTIVO_LABELS.get(motivo) if motivo else None,
        ipOrigen=context.ipOrigen if (network and context) else None,
        agenteUsuario=context.agenteUsuario if (network and context) else None,
        idCorrelacion=context.idCorrelacion if (network and context) else None,
        referenciaIdentificador=context.identificadorHash[:8] if (network and context and context.identificadorHash) else None,
    )


def _contexts(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, AuditContext]:
    """Contexto de seguridad de los eventos de la página, en una sola consulta. Vacío si la tabla todavía no existe."""
    if not ids or not schemaCompat.auditContextReady(db):
        return {}
    return {c.idAuditoria: c for c in db.scalars(select(AuditContext).where(AuditContext.idAuditoria.in_(ids)))}


def _rows(query: Select):
    return query.add_columns(Institution).outerjoin(Institution, Institution.idInstitucion == Audit.idInstitucion)


TECHNICAL_ONLY = {"idPerfilMedicion", "idTransferenciaPerfil"}
MEASUREMENT_ACCESS_ACTIONS = {"CONSULTAR_MEDICIONES_PACIENTE"}


def _changes(previous: dict, new: dict, resolver: Resolver, snapshot: dict, scope,
             transfer: bool = False) -> list[AuditChange]:
    changes = []
    for key in list(dict.fromkeys([*previous, *new])):
        if key in TECHNICAL_ONLY or (transfer and key in RELATION_FIELDS):  # origen y destino van en `transferencia`
            continue  # ids sin significado para quien lee: quedan en los detalles técnicos
        before, after = previous.get(key), new.get(key)
        label = FIELD_LABELS.get(key) or _humanize(key)
        if key in RELATION_FIELDS:
            kind, convert = "PERSONA", lambda value: resolver.person(value, snapshot) if value else None
        elif key == "idInstitucion":
            kind, convert = "INSTITUCION", lambda value: _institutionValue(value, resolver, scope)
        else:
            kind, convert = "VALOR", lambda value, key=key: _plainValue(key, value)
        changes.append(AuditChange(campo=key, etiqueta=label, tipo=kind, anterior=convert(before), nuevo=convert(after)))
    return changes


def _humanize(key: str) -> str:
    """Nombre de un campo sin etiqueta propia: «tipoInstitucion» -> «Tipo institucion». Es solo presentación."""
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(key)).strip().lower()
    return words[:1].upper() + words[1:]


def _plainValue(key: str, value) -> AuditValue | None:
    """Valor legible: roles y estados con su nombre, sí/no, listas separadas por comas. Un valor desconocido se muestra tal
    cual (nunca se inventa ni se oculta); el registro original no se altera."""
    if value is None:  # sin valor (NULL o campo inexistente): no es lo mismo que un texto vacío
        return AuditValue(texto=NULL_LABELS.get(key, "Sin valor"), ausente=True)
    if isinstance(value, bool):
        return AuditValue(texto="Sí" if value else "No")
    if isinstance(value, list):
        return AuditValue(texto=", ".join(str(v) for v in value) if value else "Vacío", ausente=not value)
    text = str(value)
    if not text.strip():
        return AuditValue(texto="Vacío", ausente=True)
    return AuditValue(texto=VALUE_LABELS.get(key, {}).get(text, text))


def _institutionValue(value, resolver: Resolver, scope) -> AuditValue | None:
    key = _uuid(value)
    if key is None:
        return None
    # La institución solo se nombra si es la del ámbito consultado: la auditoría de una no revela datos de otra.
    if scope is not None and key != scope:
        return AuditValue(id=None, texto="Otra institución", disponible=False)
    name = resolver.institutions.get(key)
    return AuditValue(id=str(key), texto=name or "Institución no disponible", disponible=bool(name))


def _list(db: Session, scope: uuid.UUID | None, *, showInstitution: bool, filters: dict, pagina: int,
          tamanioPagina: int) -> AuditPage:
    f = _validate(db, filters)
    tamanioPagina = max(1, min(tamanioPagina, MAX_PAGE_SIZE))
    pagina = max(1, pagina)
    base = _filtered(_scoped(select(Audit), scope), **{**f, "idInstitucion": scope if scope is not None else f["idInstitucion"]})
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.execute(
        _rows(base).order_by(Audit.fechaHora.desc(), Audit.idAuditoria).offset((pagina - 1) * tamanioPagina).limit(tamanioPagina)
    ).all()
    resolver = Resolver(db, scope, identify=scope is not None, maskMeasurements=True)
    resolver.prepare([audit for audit, _ in rows])  # una sola resolución agrupada para toda la página
    contexts = _contexts(db, [audit.idAuditoria for audit, _ in rows])
    return AuditPage(items=[AuditEventItem(**_item(a, resolver, i, showInstitution=showInstitution, context=contexts.get(a.idAuditoria),
                                                   network=scope is None)) for a, i in rows],
                     total=total, pagina=pagina, tamanioPagina=tamanioPagina)


def _moduleCountsQuery(base) -> Select:
    """Eventos por módulo. Se agrupa por la columna sola: SQL Server rechaza (error 8120) un GROUP BY con una expresión que
    lleva un parámetro (COALESCE(modulo, ?)), porque no la reconoce igual a la de la lista de selección. El «sin módulo»
    se resuelve después, en Python."""
    return select(base.c.modulo, func.count()).select_from(base).group_by(base.c.modulo)


def _moduleCounts(db: Session, base) -> list[tuple[str, int]]:
    merged: dict[str, int] = {}
    for module, total in db.execute(_moduleCountsQuery(base)).all():
        merged[module or "SISTEMA"] = merged.get(module or "SISTEMA", 0) + total
    return sorted(merged.items(), key=lambda item: (-item[1], item[0]))


def _summary(db: Session, scope: uuid.UUID | None, *, filters: dict, byInstitution: bool) -> AuditSummary:
    f = _validate(db, filters)
    base = _filtered(
        _scoped(select(Audit.resultado, Audit.accion, Audit.modulo, Audit.idInstitucion), scope),
        **{**f, "idInstitucion": scope if scope is not None else f["idInstitucion"]},
    ).subquery()
    failedAccessNames = sorted(classification.ACCESOS_FALLIDOS[0])
    total, failed, critical, failedAccess, suspicious, confirmed = db.execute(select(
        func.count(),
        func.coalesce(func.sum(case((base.c.resultado == "FALLO", 1), else_=0)), 0),
        func.coalesce(func.sum(case((base.c.accion.in_(ACCIONES_CRITICAS), 1), else_=0)), 0),
        func.coalesce(func.sum(case((and_(base.c.resultado == "FALLO", or_(base.c.accion.like("LOGIN%"), base.c.accion.in_(failedAccessNames))), 1),
                                    else_=0)), 0),
        func.coalesce(func.sum(case((base.c.accion.in_(sorted(classification.SOSPECHOSOS)), 1), else_=0)), 0),
        func.coalesce(func.sum(case((base.c.accion.in_(sorted(classification.CONFIRMADOS)), 1), else_=0)), 0),
    ).select_from(base)).one()
    byModule = _moduleCounts(db, base)
    institutionsCount: list[AuditCount] = []
    if byInstitution:
        rows = db.execute(
            select(base.c.idInstitucion, Institution.nombre, func.count()).select_from(base)
            .join(Institution, Institution.idInstitucion == base.c.idInstitucion)
            .group_by(base.c.idInstitucion, Institution.nombre).order_by(func.count().desc()).limit(50)
        ).all()
        institutionsCount = [AuditCount(clave=str(r[0]), nombre=r[1], total=r[2]) for r in rows]
    return AuditSummary(
        total=total, exitosos=total - failed, fallidos=failed, criticas=critical, accesosFallidos=failedAccess, sospechosos=suspicious,
        confirmados=confirmed,
        porModulo=[AuditCount(clave=m, total=n) for m, n in byModule], porInstitucion=institutionsCount,
    )


def _detail(db: Session, idAuditoria: uuid.UUID, scope: uuid.UUID | None, *, showInstitution: bool) -> AuditEventDetail:
    query = _scoped(select(Audit).where(Audit.idAuditoria == idAuditoria), scope)  # un evento de otra institución (o interno) no existe para este ámbito
    row = db.execute(_rows(query)).first()
    if row is None:
        raise _error("EVENTO_NO_ENCONTRADO", NOT_FOUND)
    audit, institution = row
    resolver = Resolver(db, scope, identify=scope is not None, maskMeasurements=True)
    resolver.prepare([audit])
    snapshot = _json(audit.detalle)

    def parse(value):
        if value is None:
            return None
        try:
            data = sanitize(json.loads(value))
        except ValueError:
            return None
        if isinstance(data, dict) and resolver.hidesPatient(audit):
            data.pop("idPerfilMedicion", None)  # el paciente de una medición no se expone
        return data

    previous, new = _json(audit.datosPrevios), _json(audit.datosNuevos)
    related = None
    if audit.tablaRelacionada == "InstitucionUsuario" and audit.idRelacionado and audit.tablaAfectada != "TransferenciaPerfil":
        related = resolver.person(audit.idRelacionado, snapshot)  # en una transferencia ya figura como origen
    entity = resolver.entity(audit, snapshot)
    return AuditEventDetail(
        **_item(audit, resolver, institution, showInstitution=showInstitution, context=_contexts(db, [audit.idAuditoria]).get(audit.idAuditoria),
                network=scope is None), tipoEvento=audit.tipoEvento,
        tablaRelacionada=audit.tablaRelacionada, idRelacionado=audit.idRelacionado,
        valoresPrevios=parse(audit.datosPrevios), valoresNuevos=parse(audit.datosNuevos),
        cambios=_changes(sanitize(previous), sanitize(new), resolver, snapshot, scope,
                         transfer=audit.tablaAfectada == "TransferenciaPerfil"),
        relacionada=related, entidad=entity,
        transferencia=resolver.transfer(audit, snapshot),
        referencias=resolver.references(audit, snapshot, entity, related),
    )


# --- API de servicio: auditoría general (administrador) --------------------------------------------------------


def listGlobal(db: Session, actor: User, *, pagina=1, tamanioPagina=25, **filters) -> AuditPage:
    requireAdministrator(db, actor)
    return _list(db, None, showInstitution=True, filters=filters, pagina=pagina, tamanioPagina=tamanioPagina)


def summaryGlobal(db: Session, actor: User, **filters) -> AuditSummary:
    requireAdministrator(db, actor)
    return _summary(db, None, filters=filters, byInstitution=True)


def detailGlobal(db: Session, actor: User, idAuditoria: uuid.UUID) -> AuditEventDetail:
    requireAdministrator(db, actor)
    return _detail(db, idAuditoria, None, showInstitution=True)


# --- Auditoría de una institución (propietario) ------------------------------------------------------------


def _institutionFilters(filters: dict) -> dict:
    forbidden = set(filters) & ADMIN_ONLY_FILTERS
    if forbidden:
        raise TypeError(f"La auditoría de una institución no admite los filtros {sorted(forbidden)}")
    return filters


def listInstitution(db: Session, actor: User, idInstitucion: uuid.UUID, *, pagina=1, tamanioPagina=25, **filters) -> AuditPage:
    requireOwner(db, actor, idInstitucion)
    return _list(db, idInstitucion, showInstitution=False, filters=_institutionFilters(filters), pagina=pagina, tamanioPagina=tamanioPagina)


def summaryInstitution(db: Session, actor: User, idInstitucion: uuid.UUID, **filters) -> AuditSummary:
    requireOwner(db, actor, idInstitucion)
    return _summary(db, idInstitucion, filters=_institutionFilters(filters), byInstitution=False)


def detailInstitution(db: Session, actor: User, idInstitucion: uuid.UUID, idAuditoria: uuid.UUID) -> AuditEventDetail:
    requireOwner(db, actor, idInstitucion)
    return _detail(db, idAuditoria, idInstitucion, showInstitution=True)  # es la institución consultada: no revela otra


# --- Cuentas individuales y selector de instituciones (administración) ---------------------------------------------------


def searchInstitutions(db: Session, actor: User, q: str | None = None, limit: int = 20) -> list[AuditCount]:
    """Instituciones para el selector (clave = id, nombre). Todas, tengan o no eventos."""
    requireAdministrator(db, actor)
    query = select(Institution.idInstitucion, Institution.nombre).order_by(Institution.nombre).limit(max(1, min(limit, 50)))
    if q and q.strip():
        query = query.where(Institution.nombre.ilike(_like(q.strip()), escape="\\"))
    return [AuditCount(clave=str(row[0]), nombre=row[1], total=0) for row in db.execute(query)]


def _accountOption(user: User) -> dict:
    deleted = user.estado == "ELIMINADO"
    return dict(idUsuario=user.idUsuario, nombre=None if deleted else _fullName(user), usuario=None if deleted else user.usuario,
                correo=maskEmail(user.correoElectronico) if user.correoElectronico else None, tipoCuenta=user.tipoCuenta, estado=user.estado)


def searchAccounts(db: Session, actor: User, q: str, limit: int = 10) -> list[AuditAccountOption]:
    """Busca cuentas por nombre, apellido, usuario o correo (mínimo 3 caracteres). Devuelve el correo enmascarado."""
    requireAdministrator(db, actor)
    term = (q or "").strip()
    if len(term) < 3:
        raise _error("DATOS_INVALIDOS", "Escribí al menos 3 caracteres para buscar una cuenta.")
    like = _like(term)
    haystack = (func.coalesce(User.nombre, "") + " " + func.coalesce(User.apellido, "") + " " + func.coalesce(User.usuario, "") + " "
                + func.coalesce(User.correoElectronico, ""))
    users = db.scalars(select(User).where(User.estado != "ELIMINADO", haystack.ilike(like, escape="\\"))
                       .order_by(User.apellido, User.nombre).limit(max(1, min(limit, 25))))
    return [AuditAccountOption(**_accountOption(user)) for user in users]


def accountHeader(db: Session, actor: User, idUsuario: uuid.UUID) -> AuditAccountHeader:
    """Ficha de una cuenta para su auditoría. Abrirla deja un evento a nombre de quien la consultó."""
    requireAdministrator(db, actor)
    user = db.get(User, idUsuario)
    if user is None:
        raise _error("USUARIO_NO_ENCONTRADO", "No encontramos esa cuenta.")
    now = nowForDb()
    credential = db.scalar(select(LocalCredential).where(LocalCredential.idUsuario == idUsuario))
    recentFailures = db.scalar(select(func.count()).select_from(Audit).where(
        Audit.idUsuario == idUsuario, Audit.resultado == "FALLO", classification.categoryFilter("ACCESOS_FALLIDOS"),
        Audit.fechaHora >= now - timedelta(hours=24)))
    lastAccess = db.scalar(select(func.max(Audit.fechaHora)).where(
        Audit.idUsuario == idUsuario, Audit.resultado == "EXITO", Audit.accion.like("LOGIN%"), Audit.accion.not_like("%MFA_PENDIENTE")))
    memberships = db.execute(
        select(InstitutionUser, Institution.nombre).join(Institution, Institution.idInstitucion == InstitutionUser.idInstitucion)
        .where(InstitutionUser.idUsuarioInvitado == idUsuario).order_by(InstitutionUser.fechaInvitacion.desc()).limit(20)).all()
    registerEvent(db, "ACCESO", "CONSULTAR_AUDITORIA_CUENTA", True, actor.idUsuario, "Usuario", idUsuario, modulo="AUDITORIA")
    db.commit()
    return AuditAccountHeader(
        **_accountOption(user), fechaCreacion=user.fechaCreacion, mfaHabilitado=mfa.isEnabled(db, user),
        bloqueadaHasta=credential.bloqueadoHasta if credential is not None and credential.bloqueadoHasta and credential.bloqueadoHasta > now else None,
        fallosAcceso24h=recentFailures or 0, ultimoAccesoExitoso=lastAccess,
        instituciones=[AuditAccountMembership(idInstitucion=r.idInstitucion, institucion=name, rol=r.rolInstitucion, estado=r.estadoRelacion)
                       for r, name in memberships],
    )


# --- Señales de seguridad (administración) --------------------------------------------------------------------------------

MAX_SIGNAL_DAYS = 31


def securitySignals(db: Session, actor: User, *, desde: date | None = None, hasta: date | None = None, idInstitucion: uuid.UUID | None = None,
                    **thresholdOverrides):
    """Patrones sospechosos y controles activados en el período (por omisión, ayer y hoy), con los umbrales de la configuración o los indicados."""
    requireAdministrator(db, actor)
    defaultFrom, defaultTo = securityDetection.defaultPeriod()
    desde, hasta = desde or defaultFrom, hasta or defaultTo
    if hasta < desde:
        raise _error("PERIODO_INVALIDO", "La fecha final no puede ser anterior a la inicial.")
    if (hasta - desde).days > MAX_SIGNAL_DAYS:
        raise _error("PERIODO_INVALIDO", f"El análisis de seguridad admite hasta {MAX_SIGNAL_DAYS} días por consulta.")
    return securityDetection.analyze(db, desde, hasta, securityDetection.thresholds(**thresholdOverrides), idInstitucion=idInstitucion)
