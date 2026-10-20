# Group - Grupo

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.utils.normalizers import normalizeEmail, normalizeSentence, normalizeStatus

EstadoGrupo = Literal["ACTIVO", "INACTIVO", "CERRADO"]


class GroupBase(BaseModel):
    # Nombre del grupo: no es nombre de persona, se conserva tal cual.
    nombre: Annotated[str, Field(max_length=100)]
    descripcion: Annotated[str, Field(max_length=500)] | None = None

    @field_validator("descripcion", mode="before")
    @classmethod
    def normalizarDescripcion(cls, value):
        return normalizeSentence(value)


class GroupCreate(GroupBase):
    model_config = ConfigDict(extra="forbid")


class GroupUpdate(GroupBase):
    model_config = ConfigDict(extra="forbid")

    nombre: Annotated[str, Field(max_length=100)] | None = None
    estado: EstadoGrupo | None = None

    @field_validator("estado", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)


class GroupRead(GroupBase):
    model_config = ConfigDict(from_attributes=True)

    idGrupo: uuid.UUID
    estado: EstadoGrupo
    fechaCreacion: datetime
    fechaActualizacion: datetime

    @field_validator("estado", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)


# --- Contratos del módulo Grupo familiar ---------------------------------------------------
#
# Solo cuentas CONSUMIDOR_FINAL. Roles: ADMINISTRADOR (rolGrupo PROPIETARIO) y MIEMBRO. Los permisos de
# compartición son de cada integrante sobre sus propios datos: el backend toma la identidad de la sesión.

RolGrupoFamiliar = Literal["ADMINISTRADOR", "MIEMBRO"]


def _trimText(value):
    if isinstance(value, str):
        value = " ".join(value.split())
        return value or None
    return value


class FamilyGroupCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: Annotated[str, Field(min_length=2, max_length=100)]
    descripcion: Annotated[str, Field(max_length=500)] | None = None

    @field_validator("nombre", "descripcion", mode="before")
    @classmethod
    def recortar(cls, value):
        return _trimText(value)


class FamilyGroupUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: Annotated[str, Field(min_length=2, max_length=100)] | None = None
    descripcion: Annotated[str, Field(max_length=500)] | None = None

    @field_validator("nombre", "descripcion", mode="before")
    @classmethod
    def recortar(cls, value):
        return _trimText(value)


class SharingSettings(BaseModel):
    """Permisos personales e independientes: activar uno no habilita ningún otro. comparteHistorial incluye los
    gráficos y estadísticas calculados sobre ese historial (no hay un permiso separado para ellos)."""

    model_config = ConfigDict(extra="forbid")

    compartePerfil: bool = False
    comparteUltimaMedicion: bool = False
    comparteHistorial: bool = False
    # Aviso a los demás integrantes cuando completás una medición: dice quién y cuándo (correo y vista del grupo), nunca el valor.
    notificaMedicion: bool = False


class MySharingRead(SharingSettings):
    model_config = ConfigDict(extra="ignore")

    # Perfil propio que se comparte (cada cuenta individual tiene uno); null si todavía no lo creó.
    idPerfilMedicion: uuid.UUID | None
    perfilDisponible: bool


class GroupMemberRead(BaseModel):
    """Integrante: solo nombre visible, rol y fechas (sin correo ni datos de salud)."""

    idGrupoUsuario: uuid.UUID
    nombre: str | None
    apellido: str | None
    rol: RolGrupoFamiliar
    estado: str
    fechaIncorporacion: datetime | None
    esVos: bool
    # Permisos de compartición vigentes de esa persona (qué decidió compartir, nunca los datos).
    compartePerfil: bool = False
    comparteUltimaMedicion: bool = False
    comparteHistorial: bool = False
    notificaMedicion: bool = False
    tienePerfil: bool = False


class GroupInvitationRead(BaseModel):
    """Invitación enviada (vista del administrador)."""

    idGrupoUsuario: uuid.UUID
    nombre: str | None
    apellido: str | None
    fechaInvitacion: datetime
    fechaVencimiento: datetime
    vencida: bool


class ReceivedGroupInvitation(BaseModel):
    idGrupoUsuario: uuid.UUID
    idGrupo: uuid.UUID
    nombreGrupo: str
    nombreAdministrador: str | None
    fechaInvitacion: datetime
    fechaVencimiento: datetime
    estado: Literal["PENDIENTE", "VENCIDA"]


class FamilyGroupDetail(BaseModel):
    idGrupo: uuid.UUID
    nombre: str
    descripcion: str | None
    estado: str
    fechaCreacion: datetime
    administrador: str | None
    cantidadIntegrantes: int
    miRol: RolGrupoFamiliar
    idGrupoUsuario: uuid.UUID
    fechaIncorporacion: datetime | None


class MyGroupResponse(BaseModel):
    """Grupo ACTIVO de la cuenta (como máximo uno) o null."""

    grupo: FamilyGroupDetail | None


class GroupCandidate(BaseModel):
    nombre: str | None
    apellido: str | None


class GroupEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correoElectronico: Annotated[EmailStr, Field(max_length=254)]

    @field_validator("correoElectronico", mode="before")
    @classmethod
    def normalizarCorreo(cls, value):
        return normalizeEmail(value)


class TransferAdminRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idGrupoUsuario: uuid.UUID


class GroupDeletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmacionNombre: Annotated[str, Field(min_length=1, max_length=100)]


# --- Datos compartidos ----------------------------------------------------------------------


class SharedMemberSummary(BaseModel):
    """Qué autorizó compartir cada integrante (no incluye los datos)."""

    idGrupoUsuario: uuid.UUID
    nombre: str | None
    apellido: str | None
    rol: RolGrupoFamiliar
    compartePerfil: bool
    comparteUltimaMedicion: bool
    comparteHistorial: bool
    notificaMedicion: bool
    tienePerfil: bool


class SharedProfileRead(BaseModel):
    """Datos básicos del perfil de medición: solo los que usa el modelo (sin documento ni fecha de nacimiento)."""

    edad: int | None
    sexoModelo: str | None  # opcional: puede no estar informado


class SharedMeasurementRead(BaseModel):
    """Una medición COMPLETADA que su dueño autorizó compartir. `glucosaEstimada` (cálculo del servidor con matriz) y `glucosaDispositivo`
    (valor que informa el firmware, con su `origenGlucosa`) son conceptos distintos y nunca se mezclan. `esDemo`: prueba, no una medición clínica."""

    idMedicion: uuid.UUID
    fechaHoraInicio: datetime
    modoMedicion: str
    estadoMedicion: str = "COMPLETADA"
    condicionComida: str
    glucosaEstimada: Decimal | None
    # Glucosa a mostrar en modo GLUCOSA_EXPERIMENTAL: la estimada o la que informa el dispositivo (DEMO / EXPERIMENTAL).
    # En OXIMETRIA es null. `origenGlucosa` / `esDemo` identifican el carácter experimental o de prueba de la medición.
    glucosa: Decimal | None = None
    glucosaDispositivo: Decimal | None = None
    unidadGlucosa: str | None = None
    origenGlucosa: str | None = None
    esDemo: bool = False
    spo2: Decimal | None
    frecuenciaCardiaca: int | None


class SharedMeasurementDetail(SharedMeasurementRead):
    """Vista ampliada de una medición compartida: solo resultados y contexto técnico. No incluye observaciones, dispositivo, edad ni sexo
    (eso lo cubre `compartePerfil` o es privado de su dueño)."""

    fechaHoraFin: datetime | None
    indiceOptico: Decimal | None
    duracionMs: int | None
    lecturasEstabilizadas: int | None
    esUltima: bool


class SharedDemoPoint(BaseModel):
    """Punto de la evolución de PRUEBAS (DEMO) de un integrante que comparte su historial. Nunca entra en promedios experimentales."""

    idMedicion: uuid.UUID
    fecha: datetime
    frecuenciaCardiaca: int | None
    spo2: float | None
    glucosa: float | None  # valor sintético del firmware
    indiceOptico: float | None = None


class SharedEvolutionPoint(BaseModel):
    """Una medición EXPERIMENTAL completada de un integrante que comparte su historial, con su fecha y hora completas (para graficarla)."""

    idMedicion: uuid.UUID
    fecha: datetime
    modoMedicion: str
    origen: str | None
    frecuenciaCardiaca: int | None
    spo2: float | None
    glucosa: float | None  # estimada (matriz) o experimental; nunca una prueba DEMO ni SIN_CALIBRAR
    indiceOptico: float | None = None


class SharedLatestRead(BaseModel):
    medicion: SharedMeasurementRead | None


class SharedHistoryPage(BaseModel):
    items: list[SharedMeasurementRead]
    total: int
    pagina: int
    tamanioPagina: int


class SharedNoticeRead(BaseModel):
    """Aviso de medición: SOLO cuándo se midió. Sin modo, estado, valores ni identificadores de la medición."""

    fechaHoraInicio: datetime


class SharedNoticesRead(BaseModel):
    items: list[SharedNoticeRead]
    total: int


class MetricSummary(BaseModel):
    cantidad: int
    promedio: float | None
    minimo: float | None
    maximo: float | None


class DailyPoint(BaseModel):
    fecha: date
    mediciones: int
    glucosaPromedio: float | None
    spo2Promedio: float | None
    frecuenciaPromedio: float | None


class SharedStatisticsRead(BaseModel):
    """Solo agregados del período (sin registros individuales)."""

    dias: int
    cantidadMediciones: int
    glucosa: MetricSummary
    spo2: MetricSummary
    frecuenciaCardiaca: MetricSummary
    serieDiaria: list[DailyPoint]
    # Solo en la consulta de UN integrante con historial compartido: pruebas DEMO del período, aparte y sin promediar con las experimentales.
    pruebasDemo: int = 0
    puntosDemo: list[SharedDemoPoint] = []
    # Solo en la consulta de UN integrante con historial compartido: cada medición experimental del período (más recientes), con fecha y hora.
    puntos: list[SharedEvolutionPoint] = []
