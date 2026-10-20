# Platform - Contratos de la administración de la plataforma (/api/v1/platform)
#
# Los roles globales son Usuario.tipoCuenta: ADMINISTRADOR_PLATAFORMA (administrador del sistema) y MODERADOR_PLATAFORMA
# (moderador del sistema). El rol que se asigna al invitar nunca llega del cliente.

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator

from app.schemas.auth import NewPassword
from app.schemas.user import validateUsername
from app.schemas.dashboard import DayCount
from app.schemas.group import MetricSummary  # noqa: F401 - reexportado para el dashboard
from app.utils.normalizers import normalizeEmail, normalizeSentence


class Reauthentication(BaseModel):
    """Reautenticación reforzada para acciones sensibles: contraseña (si la cuenta tiene credencial local) y código MFA."""

    model_config = ConfigDict(extra="forbid")

    password: Annotated[SecretStr, Field(min_length=1, max_length=256)] | None = None
    codigo: Annotated[str, Field(min_length=6, max_length=10)] | None = None
    codigoRecuperacion: Annotated[str, Field(min_length=4, max_length=40)] | None = None


class ReauthenticatedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reautenticacion: Reauthentication


class CodeActivation(BaseModel):
    """Activación con el código de un solo uso que entrega el servidor (inicialización) o el administrador (invitación de un moderador).
    La identidad (nombre y correo) ya está en la invitación que el código identifica: no se vuelve a pedir. El rol NO viaja acá: lo fija esa invitación. `extra=forbid` rechaza cualquier campo de más (rol, tipoCuenta…)."""

    model_config = ConfigDict(extra="forbid")

    codigo: Annotated[str, Field(min_length=20, max_length=200)]
    usuario: Annotated[str, Field(max_length=50)]
    password: NewPassword
    confirmacion: SecretStr

    @field_validator("usuario")
    @classmethod
    def validarUsuario(cls, value: str) -> str:
        return validateUsername(value)

    @field_validator("codigo")
    @classmethod
    def limpiarCodigo(cls, value: str) -> str:
        return value.strip()


class ModeratorInvite(ReauthenticatedAction):
    nombre: Annotated[str, Field(min_length=1, max_length=100)]
    apellido: Annotated[str, Field(min_length=1, max_length=100)]
    correoElectronico: Annotated[EmailStr, Field(max_length=254)]

    @field_validator("nombre", "apellido", mode="before")
    @classmethod
    def normalizarNombre(cls, value):
        return normalizeSentence(value)

    @field_validator("correoElectronico", mode="before")
    @classmethod
    def normalizarCorreo(cls, value):
        return normalizeEmail(value)


class TransferStart(ReauthenticatedAction):
    idUsuarioDestino: uuid.UUID


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passwordActual: Annotated[SecretStr, Field(min_length=1, max_length=256)] | None = None
    passwordNueva: NewPassword
    confirmacion: Annotated[SecretStr, Field(min_length=1, max_length=256)]
    codigo: Annotated[str, Field(min_length=6, max_length=10)] | None = None
    codigoRecuperacion: Annotated[str, Field(min_length=4, max_length=40)] | None = None


class ForgotPassword(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correoElectronico: Annotated[EmailStr, Field(max_length=254)]

    @field_validator("correoElectronico", mode="before")
    @classmethod
    def normalizarCorreo(cls, value):
        return normalizeEmail(value)


class ResetPassword(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: Annotated[str, Field(min_length=1, max_length=512)]
    password: NewPassword


class PlatformMe(BaseModel):
    idUsuario: uuid.UUID
    nombre: str | None
    apellido: str | None
    correoElectronico: str | None
    rol: str  # ADMINISTRADOR_PLATAFORMA | MODERADOR_PLATAFORMA
    rolEtiqueta: str
    permisos: list[str]
    mfaHabilitado: bool
    mfaRequerida: bool
    # True cuando falta activar MFA: el panel solo permite configurarla hasta entonces.
    requiereConfigurarMfa: bool
    tieneCredencialLocal: bool
    tieneGoogle: bool
    transferenciaPendiente: "TransferRead | None" = None


class ModeratorRead(BaseModel):
    idUsuario: uuid.UUID
    nombre: str | None
    apellido: str | None
    correoElectronico: str | None
    usuario: str | None
    estadoCuenta: str
    # INVITADO | INVITACION_VENCIDA | ACTIVO | ACTIVO_SIN_MFA | REVOCADO
    estadoAcceso: str
    mfaHabilitado: bool
    tieneCredencialLocal: bool
    tieneGoogle: bool
    fechaCreacion: datetime
    ultimoAcceso: datetime | None
    invitacionVence: datetime | None


class ModeratorActionResult(BaseModel):
    moderador: ModeratorRead
    correoEnviado: bool | None = None
    mensaje: str


class TransferRead(BaseModel):
    idTransferenciaAdministracion: uuid.UUID
    estado: str
    fechaSolicitud: datetime
    fechaRespuesta: datetime | None
    origenNombre: str | None
    destinoNombre: str | None
    idUsuarioOrigen: uuid.UUID
    idUsuarioDestino: uuid.UUID
    esOrigen: bool
    esDestino: bool


class EligibleModerator(BaseModel):
    idUsuario: uuid.UUID
    nombre: str | None
    apellido: str | None


class TransferOverview(BaseModel):
    pendiente: TransferRead | None
    elegibles: list[EligibleModerator]
    historial: list[TransferRead]


class DeviceCounters(BaseModel):
    """Estado TÉCNICO de los dispositivos (no el resultado de las mediciones: una lectura cancelada no implica un equipo averiado)."""

    total: int
    operativos: int
    enMantenimiento: int
    fueraDeServicio: int
    descomisionados: int
    asignados: int
    sinAsignar: int
    # Dispositivos con al menos una lectura INVÁLIDA en los últimos 7 días: una señal para revisarlos, no un diagnóstico de avería.
    conLecturasInvalidasRecientes: int = 0
    # El sistema no registra la conexión de cada dispositivo (la telemetría vive en memoria): «desconectados» solo se informa si hay datos verificables.
    desconectados: int | None = None
    conexionVerificable: bool = False


class CountBy(BaseModel):
    clave: str
    total: int


class MeasurementCounters(BaseModel):
    """Solo volumen operativo agregado (sin valores clínicos). Excluye las mediciones DEMO, que se cuentan aparte en `demo`."""

    demo: int = 0
    erroresTecnicos: int = 0  # eventos de la auditoría técnica anonimizada en el período (lecturas no válidas, sesiones expiradas o abandonadas…)
    motivosTecnicos: list[CountBy] = []
    total: int
    enPeriodo: int
    oximetria: int
    glucosaExperimental: int
    completadas: int
    canceladas: int
    invalidas: int
    porEstado: dict[str, int]
    serie: list[DayCount]


class UserCounters(BaseModel):
    """Cada cuenta cuenta UNA vez según su tipo: total = individuales + institucionales + plataforma."""

    total: int
    individuales: int
    institucionales: int
    activas: int
    inactivas: int
    plataforma: int = 0  # administrador y moderadores del sistema
    # Cuentas institucionales con al menos un vínculo ACTIVO con una institución («cuentas internas»), sin repetir a quien tiene varios roles.
    conVinculoInstitucional: int = 0
    institucionalesSinVinculo: int = 0
    registradasPeriodo: int = 0
    registradas7Dias: int = 0


class InstitutionCounters(BaseModel):
    total: int
    activas: int
    cerradas: int
    inactivas: int = 0  # INACTIVA: inhabilitadas
    moderadores: int
    operadores: int


class GroupCounters(BaseModel):
    total: int
    activos: int
    usuariosAgrupados: int


class ActivityEvent(BaseModel):
    idAuditoria: uuid.UUID
    fechaHora: datetime
    modulo: str | None
    accion: str
    resultado: str


class ModuleActivity(BaseModel):
    modulo: str
    total: int
    fallidos: int


class AccessCount(BaseModel):
    fallidos: int
    exitosos: int  # ingresos correctos


class AccessBreakdown(BaseModel):
    """Intentos de autenticación del período por tipo de cuenta (services/authAccess.py). Cada intento figura en una sola categoría.

    `sinClasificar`: intentos sin cuenta identificable o con contexto contradictorio; nunca se reparten en las otras tres."""

    individual: AccessCount
    institucional: AccessCount
    plataforma: AccessCount
    sinClasificar: AccessCount

    @property
    def fallidos(self) -> int:
        return self.individual.fallidos + self.institucional.fallidos + self.plataforma.fallidos + self.sinClasificar.fallidos

    @property
    def exitosos(self) -> int:
        return self.individual.exitosos + self.institucional.exitosos + self.plataforma.exitosos + self.sinClasificar.exitosos


class SecuritySummary(BaseModel):
    """Resumen de seguridad del período, solo conteos (sin quién, sin IP, sin correos)."""

    loginsFallidos: int  # == accesosPorTipo.fallidos
    loginsExitosos: int  # == accesosPorTipo.exitosos
    accesosPorTipo: AccessBreakdown
    motivosFallo: list[CountBy] = []
    cuentasBloqueadas: int  # estado BLOQUEADO (incluye accesos de plataforma revocados)
    bloqueosTemporales: int  # bloqueo por intentos fallidos vigente ahora
    cuentasConFallosRepetidos: int  # cuentas con 3 o más contraseñas incorrectas en el período
    eventosCriticos: int
    operacionesAdministrativas: int
    exportaciones: int  # exportaciones COMPLETADAS (services/exportAudit.py); hoy GlucoLume no tiene ninguna función de exportación: 0


class PlatformDashboard(BaseModel):
    """Indicadores globales y agregados: sin datos personales ni resultados clínicos identificables.

    El administrador ve todo; el moderador, solo la parte técnica (dispositivos, mediciones agregadas, estado del sistema)."""

    alcance: str  # ADMINISTRADOR | TECNICO
    periodo: dict[str, Any]
    usuarios: UserCounters | None = None
    instituciones: InstitutionCounters | None = None
    grupos: GroupCounters | None = None
    dispositivos: DeviceCounters
    mediciones: MeasurementCounters
    actividadPorModulo: list[ModuleActivity] = []
    eventosRecientes: list[ActivityEvent] = []
    erroresRecientes: list[ActivityEvent] = []
    operacionesAdministrativas: list[ActivityEvent] = []
    seguridad: SecuritySummary | None = None
    generadoEn: datetime | None = None


class SystemComponent(BaseModel):
    nombre: str
    # OPERATIVO | DEGRADADO | NO_DISPONIBLE | DESCONOCIDO: el resultado de una verificación real hecha al consultar (ver `verificacion`).
    estado: str
    detalle: str | None = None
    verificacion: str | None = None  # qué se comprobó de verdad
    latenciaMs: int | None = None


class InstitutionRow(BaseModel):
    idInstitucion: uuid.UUID
    nombre: str
    tipoInstitucion: str
    estado: str  # ACTIVA | INACTIVA | CERRADA
    fechaInicio: datetime
    fechaFin: datetime | None = None  # cierre (solo CERRADA); GlucoLume no tiene un vencimiento programado
    propietarios: int
    moderadores: int
    operadores: int
    cuentasInternas: int  # cuentas distintas con vínculo activo (no repite a quien tiene varios roles)
    limiteCuentas: int | None = None
    dispositivos: int = 0


class InstitutionPage(BaseModel):
    items: list[InstitutionRow]
    total: int
    pagina: int
    tamanioPagina: int
    porEstado: dict[str, int]


class InstitutionDevice(BaseModel):
    idDispositivo: uuid.UUID
    codigoDispositivo: str
    nombre: str | None = None
    modelo: str | None = None
    modeloSensor: str
    versionFirmware: str | None = None
    estado: str
    fechaAsignacion: datetime | None = None
    lecturasInvalidasRecientes: int = 0


class InstitutionAction(BaseModel):
    """Pausa o reactivación: el motivo es obligatorio y queda en la auditoría junto con el actor y el estado anterior y nuevo."""

    model_config = ConfigDict(extra="forbid")

    motivo: Annotated[str, Field(min_length=10, max_length=300)]

    @field_validator("motivo", mode="before")
    @classmethod
    def normalizarMotivo(cls, value):
        return normalizeSentence(value)


class CapacityChange(InstitutionAction):
    """Nuevo máximo de cuentas internas. Puede ser menor que las cuentas activas: se conservan y la institución queda excedida."""

    capacidadMaxima: Annotated[int, Field(strict=True, ge=1, le=100000)]


class InstitutionDeletion(InstitutionAction):
    """Eliminación administrativa (cierre lógico con marca de cierre administrativo). Exige el nombre exacto de la institución y la reautenticación
    reforzada (contraseña y código MFA) en la misma solicitud."""

    confirmacionNombre: Annotated[str, Field(min_length=1, max_length=150)]
    reautenticacion: Reauthentication


class AdministrativeClosure(BaseModel):
    """Cierre hecho por la plataforma (no por el propietario): no se puede reabrir desde la cuenta de la institución."""

    motivo: str
    fecha: datetime
    rolActor: str | None = None


class Suspension(BaseModel):
    """Pausa vigente, leída de la auditoría de la transición (se registra en la misma transacción que el cambio de estado)."""

    motivo: str | None = None
    fecha: datetime
    rolActor: str | None = None


class InstitutionAuditItem(BaseModel):
    """Evento administrativo o de seguridad de una institución, sin datos clínicos, contraseñas, tokens ni códigos. Los atributos salen de una lista
    cerrada de claves (estado, límite, motivo…); el actor se identifica solo por su tipo."""

    idAuditoria: uuid.UUID
    fechaHora: datetime
    categoria: str
    accion: str
    etiqueta: str
    resultado: str
    actor: str
    motivo: str | None = None
    estadoAnterior: str | None = None
    estadoNuevo: str | None = None
    limiteAnterior: int | None = None
    limiteNuevo: int | None = None
    cuentasActivas: int | None = None
    excedente: int | None = None


class InstitutionAuditPage(BaseModel):
    items: list[InstitutionAuditItem]
    total: int
    pagina: int
    tamanioPagina: int
    categorias: dict[str, str]


class InstitutionDetail(BaseModel):
    """Detalle ADMINISTRATIVO de una institución: conteos y estado técnico; nunca pacientes, personas ni valores clínicos."""

    fila: InstitutionRow
    suspension: Suspension | None = None
    estadoSinEvidencia: bool = False  # INACTIVA sin un evento de pausa en la auditoría (se cambió por fuera de la aplicación)
    excedente: int = 0  # cuentas activas por encima del límite
    cierreAdministrativo: AdministrativeClosure | None = None  # solo si la eliminó la plataforma
    eliminacionDisponible: bool = True  # False si la base instalada no tiene el cierre administrativo (esquema v5)
    identificador: str
    tipoIdentificador: str
    reaperturas: int
    cupoUtilizado: int
    cuposDisponibles: int | None = None
    porcentajeUtilizacion: float | None = None
    invitacionesPendientes: int
    pacientesActivos: int
    pacientesRegistrados: int
    dispositivosAsignados: list[InstitutionDevice]
    medicionesTotal: int
    medicionesPeriodo: int
    completadas: int
    canceladas: int
    invalidas: int
    ultimaActividad: datetime | None = None


class SystemStatus(BaseModel):
    componentes: list[SystemComponent]
    fecha: datetime
    desde: date | None = None
