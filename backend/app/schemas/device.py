# Device - Dispositivo
#
# La asignación institucional (idInstitucionAsignada, idInstitucionUsuarioResponsable,
# fechaAsignacionInstitucional) es una operación de negocio: solo lectura aquí.

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.normalizers import normalizeStatus, normalizeUpper

ModeloSensor = Literal["MAX30100", "MAX30102"]
EstadoDispositivo = Literal["OPERATIVO", "EN_MANTENIMIENTO", "FUERA_DE_SERVICIO", "BAJA"]


class DeviceBase(BaseModel):
    # Nombre, modelo y firmware: textos técnicos/comerciales, se conservan tal cual.
    nombre: Annotated[str, Field(max_length=100)] | None = None
    modelo: Annotated[str, Field(max_length=100)] | None = None
    versionFirmware: Annotated[str, Field(max_length=50)] | None = None


class DeviceCreate(DeviceBase):
    model_config = ConfigDict(extra="forbid")

    # Código técnico único del dispositivo: no se normaliza.
    codigoDispositivo: Annotated[str, Field(max_length=100)]
    modeloSensor: ModeloSensor

    @field_validator("modeloSensor", mode="before")
    @classmethod
    def normalizarModeloSensor(cls, value):
        return normalizeUpper(value)


class DeviceUpdate(DeviceBase):
    model_config = ConfigDict(extra="forbid")

    estado: EstadoDispositivo | None = None

    @field_validator("estado", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)


class DeviceRead(DeviceBase):
    model_config = ConfigDict(from_attributes=True)

    idDispositivo: uuid.UUID
    codigoDispositivo: str
    modeloSensor: ModeloSensor
    estado: EstadoDispositivo
    idInstitucionAsignada: uuid.UUID | None = None
    idInstitucionUsuarioResponsable: uuid.UUID | None = None
    fechaRegistro: datetime
    fechaAsignacionInstitucional: datetime | None = None

    @field_validator("modeloSensor", mode="before")
    @classmethod
    def normalizarModeloSensor(cls, value):
        return normalizeUpper(value)

    @field_validator("estado", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)


# --- Contratos del inventario de dispositivos (/devices e /institutions/{id}/devices) ----------------------------
#
# Estados (CK_Dispositivo_estado): OPERATIVO, EN_MANTENIMIENTO, FUERA_DE_SERVICIO y BAJA. BAJA es el
# «descomisionado»: retiro definitivo y terminal. Conserva su institución de origen y la referencia histórica del
# responsable: sigue en el inventario de esa institución, sin acciones. El estado operativo NO es el
# estado de conexión: la base no guarda conectividad.

import re as _re  # noqa: E402

from pydantic import model_validator  # noqa: E402

EstadoOperativo = Literal["OPERATIVO", "EN_MANTENIMIENTO", "FUERA_DE_SERVICIO"]
DEVICE_CODE = _re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{2,99}$")
ESTADO_ALIAS = {"DESCOMISIONADO": "BAJA"}


def _code(value):
    if not isinstance(value, str):
        return value
    value = value.strip()
    if not DEVICE_CODE.fullmatch(value):
        raise ValueError(
            "El código debe tener entre 3 y 100 caracteres: letras, números y . _ : - (sin espacios). Es el "
            "identificador del dispositivo, no el puerto COM."
        )
    return value


def _text(value):
    return (value.strip() or None) if isinstance(value, str) else value


class DeviceRegisterRequest(BaseModel):
    """Alta manual. La institución y el responsable solo los fija la plataforma (administrador); un propietario o
    moderador de institución registra siempre dentro de la suya (viene de la ruta, no del cuerpo)."""

    model_config = ConfigDict(extra="forbid")

    codigoDispositivo: str
    nombre: Annotated[str, Field(max_length=100)] | None = None
    modelo: Annotated[str, Field(max_length=100)] | None = None
    modeloSensor: ModeloSensor
    versionFirmware: Annotated[str, Field(max_length=50)] | None = None
    estado: EstadoOperativo = "OPERATIVO"
    idInstitucionAsignada: uuid.UUID | None = None
    idInstitucionUsuarioResponsable: uuid.UUID | None = None

    @field_validator("codigoDispositivo", mode="before")
    @classmethod
    def validarCodigo(cls, value):
        return _code(value)

    @field_validator("nombre", "modelo", "versionFirmware", mode="before")
    @classmethod
    def recortar(cls, value):
        return _text(value)

    @field_validator("modeloSensor", "estado", mode="before")
    @classmethod
    def normalizarCodigo(cls, value):
        return normalizeUpper(value)


class DeviceEditRequest(BaseModel):
    """Datos que se pueden modificar. El código identifica al dispositivo y no cambia; el firmware cambia hacia
    adelante: cada medición conserva el que tenía el dispositivo cuando se hizo."""

    model_config = ConfigDict(extra="forbid")

    nombre: Annotated[str, Field(max_length=100)] | None = None
    modelo: Annotated[str, Field(max_length=100)] | None = None
    modeloSensor: ModeloSensor | None = None
    versionFirmware: Annotated[str, Field(max_length=50)] | None = None

    @field_validator("nombre", "modelo", "versionFirmware", mode="before")
    @classmethod
    def recortar(cls, value):
        return _text(value)

    @field_validator("modeloSensor", mode="before")
    @classmethod
    def normalizarSensor(cls, value):
        return normalizeUpper(value) if isinstance(value, str) and value.strip() else None


class DeviceStateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: EstadoOperativo
    motivo: Annotated[str, Field(max_length=300)] | None = None

    @field_validator("estado", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeUpper(value)

    @field_validator("motivo", mode="before")
    @classmethod
    def recortarMotivo(cls, value):
        return _text(value)


class DeviceAssignRequest(BaseModel):
    """Asignación a una institución (solo administrador de plataforma), con responsable opcional."""

    model_config = ConfigDict(extra="forbid")

    idInstitucion: uuid.UUID
    idInstitucionUsuarioResponsable: uuid.UUID | None = None


class DeviceResponsibleRequest(BaseModel):
    """Responsable institucional del dispositivo; null lo deja sin responsable."""

    model_config = ConfigDict(extra="forbid")

    idInstitucionUsuarioResponsable: uuid.UUID | None = None


class DeviceResolveRequest(BaseModel):
    """Identificación al conectarse (la envía el servicio de adquisición con lo que informa el firmware).

    `codigoDispositivo` es el identificador propio del dispositivo; NUNCA el puerto COM, que cambia entre conexiones.
    `idInstitucion` es el contexto de trabajo cuando quien mide es personal institucional.
    """

    model_config = ConfigDict(extra="forbid")

    codigoDispositivo: str
    modeloSensor: ModeloSensor
    versionFirmware: Annotated[str, Field(max_length=50)] | None = None
    idInstitucion: uuid.UUID | None = None

    @field_validator("codigoDispositivo", mode="before")
    @classmethod
    def validarCodigo(cls, value):
        return _code(value)

    @field_validator("modeloSensor", mode="before")
    @classmethod
    def normalizarSensor(cls, value):
        return normalizeUpper(value)

    @field_validator("versionFirmware", mode="before")
    @classmethod
    def recortar(cls, value):
        return _text(value)


class DeviceResponsible(BaseModel):
    idInstitucionUsuario: uuid.UUID
    nombre: str | None
    apellido: str | None
    activo: bool


class DeviceInstitutionOption(BaseModel):
    """Institución elegible al asignar un dispositivo (solo administrador del sistema)."""

    idInstitucion: uuid.UUID
    nombre: str


class DevicePermissions(BaseModel):
    puedeEditar: bool
    puedeCambiarEstado: bool
    puedeAsignarInstitucion: bool
    puedeCambiarResponsable: bool
    puedeDesvincular: bool
    puedeDescomisionar: bool
    puedeVerMediciones: bool


class DeviceItem(BaseModel):
    idDispositivo: uuid.UUID
    codigoDispositivo: str
    nombre: str | None
    modelo: str | None
    modeloSensor: str
    versionFirmware: str | None
    estado: EstadoDispositivo
    idInstitucionAsignada: uuid.UUID | None
    # Solo en el inventario global (el institucional ya está acotado a una institución).
    nombreInstitucion: str | None = None
    responsable: DeviceResponsible | None
    fechaRegistro: datetime
    fechaAsignacionInstitucional: datetime | None
    # Operativo (estado OPERATIVO) no significa conectado: la conectividad real la informa la adquisición.
    disponibleParaMedir: bool
    esMio: bool = False


class DeviceRegistration(BaseModel):
    """Cómo y cuándo se dio de alta (de la auditoría). origen: CONEXION_OPERADOR (primera conexión de un operador),
    AUTOMATICO_PUENTE (alta automática del puente), MANUAL (alta administrativa desde el inventario) o VINCULACION_OPERADOR (un operador
    vinculó a la institución un dispositivo que existía sin institución)."""

    origen: str
    nombre: str | None = None
    apellido: str | None = None
    fecha: datetime
    medio: str | None = None


class DeviceDetail(DeviceItem):
    permisos: DevicePermissions
    medicionesRegistradas: int | None = None
    registro: DeviceRegistration | None = None


class DevicePage(BaseModel):
    items: list[DeviceItem]
    total: int
    pagina: int
    tamanioPagina: int


class DeviceSummaryCounts(BaseModel):
    total: int
    operativos: int
    enMantenimiento: int
    fueraDeServicio: int
    descomisionados: int
    asignados: int
    sinAsignar: int
    # La base no guarda conectividad: no se informan conectados/desconectados hasta que exista ese dato real.
    conectividadDisponible: bool = False


class DeviceMeasurementItem(BaseModel):
    """Medición hecha con el dispositivo, sin datos del paciente: el firmware y el sensor son los de ese momento."""

    idMedicion: uuid.UUID
    fechaHoraInicio: datetime
    modoMedicion: str
    estadoMedicion: str
    versionFirmwareAlMomento: str | None
    modeloSensorAlMomento: str | None
    nombreInstitucion: str | None = None


class DeviceMeasurementPage(BaseModel):
    items: list[DeviceMeasurementItem]
    total: int
    pagina: int
    tamanioPagina: int


class DeviceResolveResult(BaseModel):
    dispositivo: DeviceItem
    creado: bool
    firmwareActualizado: bool
    disponibleParaMedir: bool
    motivoNoDisponible: str | None = None
    # No se afirma que esté conectado: eso lo determina el servicio de adquisición con la comunicación efectiva.
    conexionVerificada: bool = False
