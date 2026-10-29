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
INVITACION_GRUPO = "INVITACION_GRUPO"
AGREGADO_GRUPO = "AGREGADO_GRUPO"
NUEVA_ACCION_GRUPO = "NUEVA_ACCION_GRUPO"
MEDICION_GRUPO = "MEDICION_GRUPO"
RECORDATORIO_MEDICION = "RECORDATORIO_MEDICION"

CATEGORIA_SEGURIDAD = "SEGURIDAD"
CATEGORIA_GRUPO = "GRUPO"
CATEGORIA_RECORDATORIO = "RECORDATORIO"
CATEGORIAS = (CATEGORIA_SEGURIDAD, CATEGORIA_GRUPO, CATEGORIA_RECORDATORIO)


@dataclass(frozen=True)
class EventSpec:
    categoria: str
    enPagina: bool = True  # valor por omisión mientras la cuenta no elija otra cosa
    porCorreo: bool = True
    obligatorio: bool = False  # alerta crítica: siempre en la página, la cuenta no puede apagarla


CATALOGO: dict[str, EventSpec] = {
    INICIO_SESION: EventSpec(CATEGORIA_SEGURIDAD),
    CAMBIO_CONTRASENA: EventSpec(CATEGORIA_SEGURIDAD, obligatorio=True),
    CAMBIO_MFA: EventSpec(CATEGORIA_SEGURIDAD, obligatorio=True),
    ACTIVIDAD_SOSPECHOSA: EventSpec(CATEGORIA_SEGURIDAD, obligatorio=True),
    INVITACION_GRUPO: EventSpec(CATEGORIA_GRUPO),
    AGREGADO_GRUPO: EventSpec(CATEGORIA_GRUPO),
    NUEVA_ACCION_GRUPO: EventSpec(CATEGORIA_GRUPO),
    MEDICION_GRUPO: EventSpec(CATEGORIA_GRUPO),
    RECORDATORIO_MEDICION: EventSpec(CATEGORIA_RECORDATORIO, porCorreo=False),
}
EVENTOS = tuple(CATALOGO)


def eventsOf(categoria: str) -> tuple[str, ...]:
    return tuple(evento for evento, spec in CATALOGO.items() if spec.categoria == categoria)


def eventCheck() -> str:
    """Condición del CHECK de `evento` (misma redacción que usa SQL Server al guardar la restricción)."""
    return " OR ".join(f"[evento]=N'{evento}'" for evento in EVENTOS)
