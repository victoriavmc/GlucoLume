# AuditLog - Contratos de consulta de la auditoría (solo lectura)
#
# Nada de lo que se devuelve incluye contraseñas, tokens, secretos ni datos clínicos: los valores previos y nuevos
# guardados por cada módulo son identificadores y nombres de campos, y además se redactan las claves sensibles.

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, field_serializer

from app.utils.timeZone import withArgentinaZone

Resultado = Literal["EXITO", "FALLO"]
Severidad = Literal["EXITO", "ADVERTENCIA", "CRITICO", "INFO"]
Clasificacion = Literal["INFORMATIVO", "OPERATIVO", "SOSPECHOSO", "CONFIRMADO"]
OrigenActor = Literal["PLATAFORMA", "USUARIO", "SISTEMA"]


class AuditEventItem(BaseModel):
    idAuditoria: uuid.UUID
    fechaHora: datetime  # UTC
    usuario: str | None
    modulo: str | None
    accion: str
    tipoEntidad: str | None
    idEntidad: uuid.UUID | None
    idInstitucion: uuid.UUID | None
    # Solo en la auditoría global (la institucional ya está acotada a una institución).
    nombreInstitucion: str | None = None
    resultado: Resultado
    descripcion: str | None
    critica: bool
    # Operación rechazada por falta de permiso o de acceso (resultado FALLO de un evento de permiso/acceso).
    rechazado: bool = False
    # Descripción legible de la entidad afectada (p. ej. «Dispositivo GL-0001»); los UUID siguen en idEntidad.
    entidadEtiqueta: str | None = None
    # Nombre funcional de la acción y frase que describe la operación (None si no hay una más precisa que `accion`).
    accionEtiqueta: str | None = None
    resumen: str | None = None
    # Color/significado del evento (EXITO verde, ADVERTENCIA naranja, CRITICO rojo, INFO gris) y su clasificación de seguridad
    # (INFORMATIVO, OPERATIVO, SOSPECHOSO, CONFIRMADO): ver services/auditClassification.py. Las calcula el backend a partir de la acción
    # y el resultado; la interfaz no las infiere.
    severidad: Severidad = "INFO"
    clasificacion: Clasificacion = "INFORMATIVO"
    # Quién obró: PLATAFORMA (administración de GlucoLume), USUARIO (cuenta de la institución o individual) o SISTEMA (sin cuenta: tareas
    # automáticas o intentos sin cuenta identificable).
    origenActor: OrigenActor = "SISTEMA"
    # Motivo técnico normalizado (código estable y su descripción). Nunca texto libre ni lo que escribió la persona.
    motivo: str | None = None
    motivoEtiqueta: str | None = None
    # Solo para la administración de la plataforma (None en la auditoría institucional): origen y cliente de la solicitud, identificador de
    # correlación y, en un intento sobre una cuenta inexistente, una referencia corta (no reversible) del identificador probado.
    ipOrigen: str | None = None
    agenteUsuario: str | None = None
    idCorrelacion: str | None = None
    referenciaIdentificador: str | None = None

    @field_serializer("fechaHora")
    def _withZone(self, value: datetime) -> str:
        """El backend persiste hora de Argentina sin zona (app/db/base.py reemplaza el default UTC de la base): se
        informa con su zona (UTC-03:00) para que el cliente la convierta a su hora local sin ambigüedad."""
        return withArgentinaZone(value).isoformat()


Origen = Literal["EVENTO", "ACTUAL"]


class AuditAttribute(BaseModel):
    """Dato descriptivo de una entidad (rol, estado, institución...). `origen`: EVENTO = lo que el evento registró al
    momento de la operación; ACTUAL = lo que figura hoy en el registro (puede haber cambiado desde entonces)."""

    etiqueta: str
    texto: str
    origen: Origen | None = None


class AuditReference(BaseModel):
    """Identificador interno con el nombre que se pudo resolver (trazabilidad técnica). El UUID nunca se reemplaza."""

    etiqueta: str
    id: str | None = None
    nombre: str | None = None
    origen: Origen | None = None
    disponible: bool = True


class AuditValue(BaseModel):
    """Un valor de un cambio. Si referencia a una persona o institución conocida, `id` conserva el UUID original."""

    id: str | None = None
    texto: str
    rol: str | None = None
    # False cuando la referencia no se pudo resolver («Usuario institucional no disponible»).
    disponible: bool = True
    # True cuando no hay un valor real: el campo era NULL o no existía («Sin rol», «Sin estado») o estaba vacío («Vacío»).
    ausente: bool = False
    # Origen del dato: EVENTO (registrado al momento de la operación) o ACTUAL (valor vigente hoy, que puede haber cambiado).
    origen: Origen | None = None
    # Solo en la entidad afectada: tipo de entidad en palabras («Integrante de la institución») y sus datos descriptivos.
    tipo: str | None = None
    atributos: list[AuditAttribute] = []


class AuditPatient(BaseModel):
    """Paciente de un evento. `nombreCompleto` solo si quien consulta puede ver datos identificativos de ese paciente."""

    id: str | None = None
    identificador: str | None = None
    nombreCompleto: str | None = None
    # None: sin autorización para ver datos identificativos. False: autorizado, pero depurados o no registrados.
    datosIdentificativos: bool | None = None


class AuditTransfer(BaseModel):
    """Quién se transfiere (paciente), de qué operador sale y a cuál llega."""

    paciente: AuditPatient | None = None
    origen: AuditValue | None = None
    destino: AuditValue | None = None


class AuditChange(BaseModel):
    campo: str
    etiqueta: str
    tipo: Literal["PERSONA", "INSTITUCION", "VALOR"]
    anterior: AuditValue | None = None
    nuevo: AuditValue | None = None


class AuditEventDetail(AuditEventItem):
    tipoEvento: str
    tablaRelacionada: str | None
    idRelacionado: uuid.UUID | None
    # Valores crudos tal como se guardaron (con los UUID originales): detalle técnico para diagnóstico.
    valoresPrevios: Any | None
    valoresNuevos: Any | None
    # Representación legible de lo que cambió y de la persona asociada al evento.
    cambios: list[AuditChange] = []
    relacionada: AuditValue | None = None
    entidad: AuditValue | None = None
    transferencia: AuditTransfer | None = None
    # Identificadores internos con el nombre resuelto (evento, institución, entidad, relacionada y responsable).
    referencias: list[AuditReference] = []


# --- Auditoría técnica anonimizada de mediciones (solo ADMINISTRADOR_PLATAFORMA) ----------------------------------------------
# Sin ningún identificador de usuario, perfil ni medición; la hora va redondeada a la hora en punto.


class TechnicalEvent(BaseModel):
    idEvento: uuid.UUID  # aleatorio: no se relaciona con ninguna medición ni persona
    fechaHora: datetime
    tipoOperacion: str
    estadoFinal: str
    motivo: str
    modeloSensor: str | None
    duracionSegundos: int | None
    codigoError: str | None


class TechnicalPage(BaseModel):
    items: list[TechnicalEvent]
    total: int
    pagina: int
    tamanioPagina: int


class TechnicalSummary(BaseModel):
    total: int
    porEstado: dict[str, int]
    porMotivo: dict[str, int]
    porSensor: dict[str, int]
    duracionPromedioSegundos: float | None


class AuditPage(BaseModel):
    items: list[AuditEventItem]
    total: int
    pagina: int
    tamanioPagina: int


class AuditCount(BaseModel):
    clave: str
    nombre: str | None = None
    total: int


class AuditSummary(BaseModel):
    total: int
    exitosos: int
    fallidos: int
    criticas: int
    # Eventos de seguridad dentro de los filtros: accesos fallidos (login, segundo factor, bloqueos), patrones sospechosos y controles activados.
    accesosFallidos: int = 0
    sospechosos: int = 0
    confirmados: int = 0
    porModulo: list[AuditCount]
    # Solo en la auditoría global.
    porInstitucion: list[AuditCount] = []


# --- Cuentas individuales y señales de seguridad (solo la administración de la plataforma) ------------------------------------------


class AuditAccountOption(BaseModel):
    idUsuario: uuid.UUID
    nombre: str | None
    usuario: str | None
    correo: str | None  # enmascarado
    tipoCuenta: str
    estado: str


class AuditAccountMembership(BaseModel):
    idInstitucion: uuid.UUID
    institucion: str | None
    rol: str
    estado: str


class AuditAccountHeader(AuditAccountOption):
    fechaCreacion: datetime
    mfaHabilitado: bool
    bloqueadaHasta: datetime | None = None
    fallosAcceso24h: int
    ultimoAccesoExitoso: datetime | None = None
    instituciones: list[AuditAccountMembership] = []

    @field_serializer("fechaCreacion", "bloqueadaHasta", "ultimoAccesoExitoso")
    def _withZone(self, value: datetime | None) -> str | None:
        return withArgentinaZone(value).isoformat() if value else None


class SecurityThresholds(BaseModel):
    ventanaMinutos: int
    fallosPorCuenta: int
    cuentasPorOrigen: int
    historialOrigenInusual: int


class SecuritySignal(BaseModel):
    """Un patrón detectado o un control activado en el período. NO es un registro de auditoría: es el resultado de analizar los eventos
    que sí existen, con los umbrales indicados. `filtros` son los parámetros del listado de eventos que muestran lo que originó la señal."""

    tipo: str
    clasificacion: Clasificacion
    titulo: str
    descripcion: str
    cantidad: int
    umbral: int | None = None
    desde: datetime
    hasta: datetime
    ipOrigen: str | None = None
    cuenta: str | None = None
    filtros: dict[str, str] = {}

    @field_serializer("desde", "hasta")
    def _withZone(self, value: datetime) -> str:
        return withArgentinaZone(value).isoformat()


class SecurityIndicators(BaseModel):
    intentosFallidos: int
    cuentasAfectadas: int
    origenesDistintos: int
    bloqueos: int
    limitesExcedidos: int
    rafagasRechazos: int


class SecuritySignals(BaseModel):
    desde: date
    hasta: date
    umbrales: SecurityThresholds
    indicadores: SecurityIndicators
    senales: list[SecuritySignal]
    # El análisis mira como máximo este tanto de intentos fallidos del período; si se alcanzó, las cuentas y los orígenes pueden estar subestimados.
    truncado: bool = False
    # Sin la tabla de contexto (AuditoriaContexto) no hay IP ni motivo: se indica en lugar de afirmar que no hubo patrones.
    contextoDisponible: bool = True
