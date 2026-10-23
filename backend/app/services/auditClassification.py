# AuditClassification - Categorías, clasificación y severidad de los eventos de auditoría
#
# Es presentación y filtrado: NO modifica ni inventa registros. Todo sale de dos datos que el evento ya guarda (acción y resultado) más, para
# la severidad, su tipo.
#
# Clasificación (qué significa el evento para la seguridad):
#   INFORMATIVO  operación exitosa o consulta normal.
#   OPERATIVO    fallo o rechazo individual que ocurre en el uso normal (contraseña mal escrita, cuenta sin verificar, permiso insuficiente). Un
#                error de autenticación aislado NO es un ataque y no se presenta como tal.
#   SOSPECHOSO   patrón anómalo detectado por un control técnico (ráfaga de rechazos de un mismo origen, acceso a la administración sin ser
#                administrador). Es una señal para investigar, no una conclusión.
#   CONFIRMADO   el sistema aplicó un control de seguridad (bloqueo temporal de cuenta, límite de solicitudes, reutilización de un token de
#                sesión ya usado). El hecho está comprobado; que haya una persona atacando no lo está.
#
# Severidad (color en la interfaz): EXITO (verde), ADVERTENCIA (naranja), CRITICO (rojo), INFO (gris).

from sqlalchemy import and_, false, or_

from app.models.audit import Audit
from app.services.audit import ACCIONES_CRITICAS

INFORMATIVO, OPERATIVO, SOSPECHOSO, CONFIRMADO = "INFORMATIVO", "OPERATIVO", "SOSPECHOSO", "CONFIRMADO"
CLASIFICACIONES = (INFORMATIVO, OPERATIVO, SOSPECHOSO, CONFIRMADO)
EXITO, ADVERTENCIA, CRITICO, INFO = "EXITO", "ADVERTENCIA", "CRITICO", "INFO"

# --- Acciones de seguridad propias de este módulo ------------------------------------------------------------------------------------
ACCION_BLOQUEO_CUENTA = "BLOQUEO_TEMPORAL_CUENTA"
ACCION_LIMITE_SOLICITUDES = "LIMITE_SOLICITUDES_EXCEDIDO"
ACCION_RAFAGA_AUTORIZACION = "RAFAGA_RECHAZOS_HTTP"
ACCION_RAFAGA_VALIDACION = "RAFAGA_VALIDACION_HTTP"
ACCION_EXPORT_SOLICITADA = "EXPORTACION_SOLICITADA"
ACCION_EXPORT_COMPLETADA = "EXPORTACION_COMPLETADA"
ACCION_EXPORT_FALLIDA = "EXPORTACION_FALLIDA"
ACCION_DEPURAR_AUDITORIA = "DEPURAR_AUDITORIA"
ACCION_ERROR_INESPERADO = "ERROR_SERVIDOR_INESPERADO"
# Previstas para cuando exista la operación (hoy el límite y la vigencia de una institución los fija el administrador de la base).
ACCION_CAMBIAR_LIMITE = "CAMBIAR_LIMITE_INSTITUCION"
ACCION_CAMBIAR_VIGENCIA = "CAMBIAR_VIGENCIA_INSTITUCION"

CONFIRMADOS = frozenset({ACCION_BLOQUEO_CUENTA, ACCION_LIMITE_SOLICITUDES, "REFRESH_REUTILIZADO"})
SOSPECHOSOS = frozenset({ACCION_RAFAGA_AUTORIZACION, ACCION_RAFAGA_VALIDACION, "ACCESO_PLATAFORMA_DENEGADO", "OPERACION_PLATAFORMA_DENEGADA",
                         "CREDENCIAL_PUENTE_RECHAZADA"})

# Operaciones exitosas que son lectura o pasos intermedios: se muestran en gris, sin el verde de «algo cambió».
_INFO_PREFIXES = ("CONSULTAR_", "ACCEDER_", "ACCESO_")
_INFO_SUFFIXES = ("_MFA_PENDIENTE",)

# --- Categorías (filtro «tipo de evento») ---------------------------------------------------------------------------------------------
# (nombres exactos, prefijos). Una acción puede estar en más de una categoría.
CATEGORIAS: dict[str, tuple[frozenset[str], tuple[str, ...]]] = {
    "AUTENTICACION": (frozenset({
        "VINCULACION_GOOGLE", "REAUTENTICACION_FALLIDA", "CAMBIAR_PASSWORD", "CAMBIAR_PASSWORD_PLATAFORMA", "RESTABLECER_PASSWORD",
        "RESTABLECER_PASSWORD_PLATAFORMA", "RESTABLECER_PASSWORD_MODERADOR", "SOLICITAR_RECUPERACION_PASSWORD", "CREDENCIAL_LOCAL_AGREGADA",
        "REFRESH_REUTILIZADO", ACCION_BLOQUEO_CUENTA,
    }), ("LOGIN", "MFA_")),
    "CUENTAS": (frozenset({
        "REGISTRO_LOCAL", "REGISTRO_GOOGLE", "CORREO_VERIFICADO", "VERIFICACION_REENVIADA", "ACTIVAR_CUENTA_INVITADA", "CREAR_CUENTA_INVITADA",
        "ELIMINACION_CUENTA", "ELIMINACION_AUTOMATICA_CUENTA", "ELIMINAR_CUENTA_NO_VERIFICADA_EXPIRADA", "INICIAR_PERIODO_GRACIA",
        "CANCELAR_PERIODO_GRACIA", "REVOCAR_MIEMBRO_INSTITUCION", "INVITAR_MIEMBRO_INSTITUCION", "ACEPTAR_INVITACION_INSTITUCION",
        "RESPONDER_INVITACION_INSTITUCION", "INVITAR_MODERADOR_PLATAFORMA", "REVOCAR_MODERADOR_PLATAFORMA", "ACTIVAR_CUENTA_PLATAFORMA",
        "INICIALIZAR_ADMINISTRADOR", "RECUPERAR_ADMINISTRACION_PLATAFORMA", "REINVITAR_ADMINISTRADOR_PLATAFORMA",
        "ELIMINAR_DATOS_PERSONAL_HISTORICO", "MINIMIZAR_DATOS_PERSONAL_HISTORICO",
    }), ()),
    "INSTITUCIONES": (frozenset({
        "CREAR_INSTITUCION", "MODIFICAR_INSTITUCION", "ELIMINAR_INSTITUCION", "REABRIR_INSTITUCION", "NOTIFICAR_CREACION_INSTITUCION",
        ACCION_CAMBIAR_LIMITE, ACCION_CAMBIAR_VIGENCIA, "REVOCAR_MIEMBRO_INSTITUCION", "INVITAR_MIEMBRO_INSTITUCION",
        "MODIFICAR_MIEMBRO_INSTITUCION", "ACEPTAR_INVITACION_INSTITUCION", "PACIENTES_PENDIENTES_REASIGNACION",
    }), ()),
    "PERMISOS": (frozenset({
        "MODIFICAR_MIEMBRO_INSTITUCION", "TRANSFERIR_ADMINISTRACION_GRUPO", "MFA_DESHABILITADO", "MFA_DESHABILITADO_POR_RECUPERACION",
        "OPERACION_PLATAFORMA_DENEGADA", "ACCESO_PLATAFORMA_DENEGADO", "CONSULTAR_AUDITORIA", "INVITAR_MODERADOR_PLATAFORMA",
        "REVOCAR_MODERADOR_PLATAFORMA", "SOLICITAR_TRANSFERENCIA_ADMINISTRACION", "ACEPTAR_TRANSFERENCIA_ADMINISTRACION",
    }), ()),
    "EXPORTACIONES": (frozenset(), ("EXPORTACION",)),
    "SEGURIDAD": (frozenset({
        ACCION_RAFAGA_AUTORIZACION, ACCION_RAFAGA_VALIDACION, ACCION_LIMITE_SOLICITUDES, ACCION_BLOQUEO_CUENTA, "REFRESH_REUTILIZADO",
        "ACCESO_PLATAFORMA_DENEGADO", "OPERACION_PLATAFORMA_DENEGADA", "REAUTENTICACION_FALLIDA", "MFA_CODIGO_INVALIDO",
        "MFA_RECUPERACION_CODIGO_INVALIDO", "CONSULTAR_AUDITORIA", ACCION_ERROR_INESPERADO, "CREDENCIAL_PUENTE_RECHAZADA",
        "CREAR_CREDENCIAL_PUENTE", "ROTAR_CREDENCIAL_PUENTE", "REVOCAR_CREDENCIAL_PUENTE",
    }), ()),
}
# La categoría de intentos de acceso fallidos es un filtro propio: login fallido, MFA fallido, bloqueos.
ACCESOS_FALLIDOS = (frozenset({"MFA_CODIGO_INVALIDO", "MFA_RECUPERACION_CODIGO_INVALIDO", ACCION_BLOQUEO_CUENTA, "REAUTENTICACION_FALLIDA"}), ("LOGIN",))
CATEGORIAS["ACCESOS_FALLIDOS"] = ACCESOS_FALLIDOS


def categoryFilter(categoria: str):
    """Condición SQL de una categoría. ACCESOS_FALLIDOS exige además resultado FALLO."""
    names, prefixes = CATEGORIAS[categoria]
    parts = [Audit.accion.in_(sorted(names))] if names else []
    parts += [Audit.accion.like(prefix + "%") for prefix in prefixes]
    condition = or_(*parts) if parts else false()
    return and_(condition, Audit.resultado == "FALLO") if categoria == "ACCESOS_FALLIDOS" else condition


def inCategory(accion: str, categoria: str) -> bool:
    names, prefixes = CATEGORIAS[categoria]
    return accion in names or accion.startswith(prefixes)


def classificationFilter(clasificacion: str):
    """Condición SQL equivalente a classify(): los filtros del listado y la etiqueta de cada fila no pueden diferir."""
    if clasificacion == CONFIRMADO:
        return Audit.accion.in_(sorted(CONFIRMADOS))
    if clasificacion == SOSPECHOSO:
        return Audit.accion.in_(sorted(SOSPECHOSOS))
    special = sorted(CONFIRMADOS | SOSPECHOSOS)
    if clasificacion == OPERATIVO:
        return and_(Audit.resultado == "FALLO", Audit.accion.not_in(special))
    return and_(Audit.resultado == "EXITO", Audit.accion.not_in(special))


def classify(accion: str, resultado: str) -> str:
    if accion in CONFIRMADOS:
        return CONFIRMADO
    if accion in SOSPECHOSOS:
        return SOSPECHOSO
    return OPERATIVO if resultado == "FALLO" else INFORMATIVO


def severity(accion: str, resultado: str, tipoEvento: str, clasificacion: str) -> str:
    if resultado == "EXITO":
        return INFO if accion.startswith(_INFO_PREFIXES) or accion.endswith(_INFO_SUFFIXES) else EXITO
    if clasificacion == CONFIRMADO or accion in ACCIONES_CRITICAS:
        return CRITICO
    if clasificacion == SOSPECHOSO or tipoEvento in ("LOGIN", "PERMISO", "ACCESO"):
        return ADVERTENCIA
    return CRITICO  # una operación que falló por un error (no por un rechazo de acceso)
