# NotificationEvents - Catálogo de avisos de «Notificaciones» (compartido por los modelos, el servicio y los contratos)
#
# Cada aviso pertenece a una categoría (la bandeja filtra por ella) y puede ser obligatorio: las alertas críticas de seguridad se
# entregan siempre en la página, sin depender de una preferencia opcional. El CHECK de la base se arma desde esta misma lista, así que
# agregar un aviso es un cambio aquí más la migración database/reference/GlucoLume_notificaciones_v2.sql.

from dataclasses import dataclass

INICIO_SESION = "INICIO_SESION"
CAMBIO_CONTRASENA = "CAMBIO_CONTRASENA"  # nosec B105 - nombre de evento, no un secreto
CAMBIO_MFA = "CAMBIO_MFA"
ACTIVIDAD_SOSPECHOSA = "ACTIVIDAD_SOSPECHOSA"
INTENTO_INGRESO = "INTENTO_INGRESO"  # cada contraseña, código o intento rechazado contra la cuenta (no un bloqueo)
INVITACION_GRUPO = "INVITACION_GRUPO"
AGREGADO_GRUPO = "AGREGADO_GRUPO"
NUEVA_ACCION_GRUPO = "NUEVA_ACCION_GRUPO"
MEDICION_GRUPO = "MEDICION_GRUPO"
RECORDATORIO_MEDICION = "RECORDATORIO_MEDICION"
# Invitación de una institución a una cuenta institucional existente. El correo ya lo envía su flujo (institution.py).
INSTITUCION_INVITACION = "INSTITUCION_INVITACION"
# Gestión de la institución: según el rol de quien recibe (propietario, moderador u operador). El correo de cada hecho ya lo envía su
# flujo (institution.py, institutionPatients.py, profileTransfers.py): estos avisos solo agregan la bandeja.
INSTITUCION_OPERADOR_NUEVO = "INSTITUCION_OPERADOR_NUEVO"
INSTITUCION_OPERADOR_BAJA = "INSTITUCION_OPERADOR_BAJA"
INSTITUCION_MODERADOR_NUEVO = "INSTITUCION_MODERADOR_NUEVO"
INSTITUCION_MODERADOR_BAJA = "INSTITUCION_MODERADOR_BAJA"
INSTITUCION_PACIENTE_NUEVO = "INSTITUCION_PACIENTE_NUEVO"
INSTITUCION_PACIENTE_A_CARGO = "INSTITUCION_PACIENTE_A_CARGO"
INSTITUCION_SOLICITUD_NUEVA = "INSTITUCION_SOLICITUD_NUEVA"
INSTITUCION_SOLICITUD_ACEPTADA = "INSTITUCION_SOLICITUD_ACEPTADA"
INSTITUCION_SOLICITUD_RECHAZADA = "INSTITUCION_SOLICITUD_RECHAZADA"
# Envío del resultado de una medición por correo (lo manda el flujo de medición): el aviso de la bandeja llega cuando termina.
RESULTADO_ENVIADO = "RESULTADO_ENVIADO"
# Administración de la plataforma (solo para cuentas ADMINISTRADOR_PLATAFORMA y MODERADOR_PLATAFORMA). Los correos de estos hechos ya los
# envía services/platform.py: aquí solo se agrega la bandeja de la página.
PLATAFORMA_TRANSFERENCIA_SOLICITADA = "PLATAFORMA_TRANSFERENCIA_SOLICITADA"  # al moderador a quien se ofrece la administración
PLATAFORMA_TRANSFERENCIA_RESPONDIDA = "PLATAFORMA_TRANSFERENCIA_RESPONDIDA"  # al administrador: aceptada o rechazada
PLATAFORMA_MODERADOR_ACTIVO = "PLATAFORMA_MODERADOR_ACTIVO"  # al administrador: un moderador activó su cuenta

CATEGORIA_SEGURIDAD = "SEGURIDAD"
CATEGORIA_GRUPO = "GRUPO"
CATEGORIA_RECORDATORIO = "RECORDATORIO"
CATEGORIA_INSTITUCION = "INSTITUCION"
CATEGORIA_MEDICION = "MEDICION"
CATEGORIA_PLATAFORMA = "PLATAFORMA"
CATEGORIAS = (CATEGORIA_SEGURIDAD, CATEGORIA_GRUPO, CATEGORIA_RECORDATORIO, CATEGORIA_INSTITUCION, CATEGORIA_MEDICION, CATEGORIA_PLATAFORMA)


@dataclass(frozen=True)
class EventSpec:
    categoria: str
    enPagina: bool = True  # valor por omisión mientras la cuenta no elija otra cosa
    porCorreo: bool = True
    obligatorio: bool = False  # alerta crítica: siempre en la página, la cuenta no puede apagarla
    correo: bool = True  # tiene canal de correo propio; si no, el aviso solo llega a la página
    plataforma: bool = False  # solo lo reciben las cuentas de la administración de la plataforma


CATALOGO: dict[str, EventSpec] = {
    INICIO_SESION: EventSpec(CATEGORIA_SEGURIDAD),
    CAMBIO_CONTRASENA: EventSpec(CATEGORIA_SEGURIDAD, obligatorio=True),
    CAMBIO_MFA: EventSpec(CATEGORIA_SEGURIDAD, obligatorio=True),
    ACTIVIDAD_SOSPECHOSA: EventSpec(CATEGORIA_SEGURIDAD, obligatorio=True),
    INTENTO_INGRESO: EventSpec(CATEGORIA_SEGURIDAD, obligatorio=True, correo=False),
    INVITACION_GRUPO: EventSpec(CATEGORIA_GRUPO),
    AGREGADO_GRUPO: EventSpec(CATEGORIA_GRUPO),
    NUEVA_ACCION_GRUPO: EventSpec(CATEGORIA_GRUPO),
    MEDICION_GRUPO: EventSpec(CATEGORIA_GRUPO),
    RECORDATORIO_MEDICION: EventSpec(CATEGORIA_RECORDATORIO, porCorreo=False),
    INSTITUCION_INVITACION: EventSpec(CATEGORIA_INSTITUCION, porCorreo=False, correo=False),
    INSTITUCION_OPERADOR_NUEVO: EventSpec(CATEGORIA_INSTITUCION, porCorreo=False, correo=False),
    INSTITUCION_OPERADOR_BAJA: EventSpec(CATEGORIA_INSTITUCION, porCorreo=False, correo=False),
    INSTITUCION_MODERADOR_NUEVO: EventSpec(CATEGORIA_INSTITUCION, porCorreo=False, correo=False),
    INSTITUCION_MODERADOR_BAJA: EventSpec(CATEGORIA_INSTITUCION, porCorreo=False, correo=False),
    INSTITUCION_PACIENTE_NUEVO: EventSpec(CATEGORIA_INSTITUCION, porCorreo=False, correo=False),
    INSTITUCION_PACIENTE_A_CARGO: EventSpec(CATEGORIA_INSTITUCION, porCorreo=False, correo=False),
    INSTITUCION_SOLICITUD_NUEVA: EventSpec(CATEGORIA_INSTITUCION, porCorreo=False, correo=False),
    INSTITUCION_SOLICITUD_ACEPTADA: EventSpec(CATEGORIA_INSTITUCION, porCorreo=False, correo=False),
    INSTITUCION_SOLICITUD_RECHAZADA: EventSpec(CATEGORIA_INSTITUCION, porCorreo=False, correo=False),
    RESULTADO_ENVIADO: EventSpec(CATEGORIA_MEDICION, porCorreo=False, correo=False),
    PLATAFORMA_TRANSFERENCIA_SOLICITADA: EventSpec(CATEGORIA_PLATAFORMA, porCorreo=False, correo=False, plataforma=True),
    PLATAFORMA_TRANSFERENCIA_RESPONDIDA: EventSpec(CATEGORIA_PLATAFORMA, porCorreo=False, correo=False, plataforma=True),
    PLATAFORMA_MODERADOR_ACTIVO: EventSpec(CATEGORIA_PLATAFORMA, porCorreo=False, correo=False, plataforma=True),
}
EVENTOS = tuple(CATALOGO)


def eventsOf(categoria: str) -> tuple[str, ...]:
    return tuple(evento for evento, spec in CATALOGO.items() if spec.categoria == categoria)


def eventCheck() -> str:
    """Condición del CHECK de `evento` (misma redacción que usa SQL Server al guardar la restricción)."""
    return " OR ".join(f"[evento]=N'{evento}'" for evento in EVENTOS)
