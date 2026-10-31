# Acquisition - Contratos de la conexión con el Arduino (/api/v1/acquisition)

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.utils.normalizers import normalizeDateTime, normalizeUpper

Medio = Literal["USB", "BLUETOOTH"]
# AUTO: el puente busca el GlucoLume por USB y Bluetooth y todavía no lo encontró (o no tiene puerto fijo).
MedioPuente = Literal["USB", "BLUETOOTH", "AUTO"]


class PortRead(BaseModel):
    puerto: str
    descripcion: str | None
    fabricante: str | None
    identificador: str | None
    esBluetooth: bool
    esArduino: bool


class ConnectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    puerto: Annotated[str, Field(min_length=3, max_length=100)]
    medio: Medio
    baudios: Annotated[int, Field(ge=1200, le=921600)] | None = None

    @field_validator("medio", mode="before")
    @classmethod
    def normalizarMedio(cls, value):
        return normalizeUpper(value)


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idMedicion: uuid.UUID


class IdentifiedDevice(BaseModel):
    codigo: str
    sensor: str
    firmware: str
    frecuenciaMuestreo: int | None


class AcquisitionState(BaseModel):
    idMedicion: uuid.UUID
    estado: str
    muestras: int
    guardadas: int
    segundos: float
    error: str | None
    codigoError: str | None
    indicadores: dict[str, Any] | None


class LinkStatus(BaseModel):
    conectado: bool
    ocupado: bool = False
    puerto: str | None
    medio: str | None
    baudios: int | None
    estadoDispositivo: str | None
    ultimoError: str | None
    lineasInvalidas: int
    dispositivo: IdentifiedDevice | None
    adquisicion: AcquisitionState | None


class ProbeRead(BaseModel):
    latenciaMs: float


# --- Telemetría procesada del firmware (puente serie) -----------------------------------------------------------------
#
# El puente (acquisition/bridge) envía las líneas tal como las escribe el Arduino; el backend las interpreta. Ningún
# valor clínico lo calcula el cliente ni el puente.

EstadoEnlace = Literal["CONECTADO", "DESCONECTADO", "REINTENTANDO", "PAUSADO", "DISPOSITIVO_DESCONECTADO"]
# DISPOSITIVO_DESCONECTADO: modo AUTO sin ningún GlucoLume a la vista. No es un fallo del puente ni del puerto.

# Causa técnica del último fallo del puerto, para explicarla con precisión (no es texto libre del equipo local):
#   PUERTO_OCUPADO        otra aplicación tiene abierto el COM (Monitor Serie, PuTTY, otro puente...)
#   PUERTO_INEXISTENTE    el COM no existe: dispositivo desconectado, driver sin instalar o puerto equivocado
#   DISPOSITIVO_SIN_RESPUESTA  el COM existe pero no responde (Bluetooth apagado o fuera de alcance, Arduino sin energía)
#   SIN_DATOS             el puerto abre y no llegan datos
#   ERROR_PUERTO          cualquier otro error del puerto
CodigoErrorPuerto = Literal["PUERTO_OCUPADO", "PUERTO_INEXISTENTE", "DISPOSITIVO_SIN_RESPUESTA", "SIN_DATOS", "ERROR_PUERTO"]
AccionPuente = Literal["CONFIGURAR", "PAUSAR", "REANUDAR", "DETENER", "REINICIAR"]


class BridgePort(BaseModel):
    """Puerto serie que el PROPIO puente ve en su equipo (solo lectura). El navegador nunca los enumera."""

    model_config = ConfigDict(extra="forbid")

    puerto: Annotated[str, Field(min_length=3, max_length=20, pattern=r"^[A-Za-z0-9_./-]+$")]
    descripcion: Annotated[str, Field(max_length=120)] | None = None
    esBluetooth: bool = False
    esArduino: bool = False
    # Estado que Windows informa para ese dispositivo (OK, Unknown, Error...): un «Unknown» indica un controlador sin cargar.
    estadoWindows: Annotated[str, Field(max_length=30)] | None = None


class BridgeCommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Annotated[str, Field(min_length=1, max_length=40)]
    ok: bool
    mensaje: Annotated[str, Field(max_length=200)] | None = None


class BridgeCommand(BaseModel):
    """Orden acotada que el backend entrega al puente en la respuesta del latido (el puente nunca recibe otra cosa)."""

    id: str
    accion: AccionPuente
    puerto: str | None = None
    medio: MedioPuente | None = None


class BridgeCommandRequest(BaseModel):
    """Pedido de un usuario autenticado. Solo acciones de la lista; el puerto debe ser uno que el puente informó."""

    model_config = ConfigDict(extra="forbid")

    accion: AccionPuente
    puerto: Annotated[str, Field(min_length=3, max_length=20)] | None = None
    medio: MedioPuente | None = None

    @field_validator("medio", mode="before")
    @classmethod
    def normalizarMedio(cls, value):
        return normalizeUpper(value) if value is not None else None


class BridgeLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: Annotated[int, Field(ge=0, le=2**53)]  # creciente por puente: permite reenviar un lote sin duplicar lecturas
    edadMs: Annotated[int, Field(ge=0, le=86_400_000)]  # ms transcurridos desde que el puente leyó la línea
    texto: Annotated[str, Field(max_length=512)]


class BridgeIngest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idPuente: uuid.UUID  # identifica la ejecución del puente (cambia al reiniciarlo)
    codigoDispositivo: Annotated[str, Field(min_length=1, max_length=100)]  # código del inventario al que está atado el puerto
    puerto: Annotated[str, Field(max_length=100)] | None = None
    medio: MedioPuente
    baudios: Annotated[int, Field(ge=1200, le=921600)] | None = None
    estadoEnlace: EstadoEnlace
    intento: Annotated[int, Field(ge=0, le=1_000_000)] = 0
    error: Annotated[str, Field(max_length=200)] | None = None
    detenido: bool = False  # el puente se cierra a propósito: libera su lugar de inmediato
    lineas: Annotated[list[BridgeLine], Field(max_length=200)] = []
    # Diagnóstico del equipo local (todos opcionales: un puente anterior sigue funcionando).
    codigoError: CodigoErrorPuerto | None = None
    puertos: Annotated[list[BridgePort], Field(max_length=32)] | None = None
    versionPuente: Annotated[str, Field(max_length=20)] | None = None
    comando: BridgeCommandResult | None = None  # resultado de la última orden recibida

    @field_validator("medio", mode="before")
    @classmethod
    def normalizarMedio(cls, value):
        return normalizeUpper(value)


class BridgeIngestRead(BaseModel):
    aceptadas: int
    duplicadas: int
    invalidas: int
    estado: str
    comando: BridgeCommand | None = None  # orden pendiente para este puente (una sola a la vez)


class BridgeCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigoDispositivo: Annotated[str, Field(min_length=1, max_length=100)]


class BridgeCheckRead(BaseModel):
    """Qué sabe el inventario de este código (para la instalación del puente): sin datos de personas."""

    registrado: bool
    operativo: bool = False
    sensor: str | None = None
    nombre: str | None = None
    asignadoAInstitucion: bool = False


class DeviceReading(BaseModel):
    bpm: float | None
    spo2: float | None
    glucosa: float | None
    unidadGlucosa: str | None
    origen: str
    esDemo: bool
    indiceOptico: float | None
    senalValida: bool
    dedo: bool
    muestras: int
    instante: str
    edadSegundos: float | None = None


class TelemetryBridge(BaseModel):
    puerto: str | None
    medio: str
    baudios: int | None
    codigoDispositivo: str
    estadoEnlace: str
    reintento: int
    ultimoError: str | None
    codigoError: str | None = None
    versionPuente: str | None = None
    puertosDisponibles: list[BridgePort] | None = None
    comandoPendiente: str | None = None  # acción esperando que el puente la tome
    ultimoComando: BridgeCommandResult | None = None


class TelemetryStability(BaseModel):
    estable: bool
    motivo: str | None
    mensaje: str | None
    lecturasValidas: int
    lecturasRequeridas: int


class TelemetryPpg(BaseModel):
    """Señal PPG real de la sesión (muestras ópticas del MAX30100 sin componente continua). `valores` puede traer null = hueco sin señal."""

    hz: int
    inicio: int  # índice absoluto de valores[0]
    valores: list[int | None]
    latidos: list[int]  # índices absolutos de los latidos detectados por el firmware
    edadSegundos: float  # antigüedad del último bloque recibido


class TelemetrySessionState(BaseModel):
    idMedicion: uuid.UUID
    iniciada: str
    enlacePerdido: bool
    estabilidad: TelemetryStability | None
    ppg: TelemetryPpg | None = None
    modo: str | None = None  # modo de la medición en curso (OXIMETRIA | GLUCOSA_EXPERIMENTAL)


class DeviceNotice(BaseModel):
    texto: str
    error: bool


class TelemetryStatus(BaseModel):
    # SIN_PUENTE | PUERTO_DESCONECTADO | SIN_DATOS | CONECTADO
    estado: str
    ocupado: bool  # otra cuenta tiene el control del dispositivo
    controlPropio: bool = False  # quien consulta tiene el control (DEC-01): solo entonces recibe la lectura y puede dar órdenes
    edadUltimaLectura: float | None = None  # antigüedad de la última lectura, sin valores (para el diagnóstico de cualquier cuenta)
    puente: TelemetryBridge | None
    lectura: DeviceReading | None
    avisoDispositivo: DeviceNotice | None
    lineasInvalidas: int
    lecturasRecibidas: int
    sesion: TelemetrySessionState | None


class ReadinessStep(BaseModel):
    id: str  # PUENTE | PUERTO | TELEMETRIA | SENSOR | REGISTRADO | ASOCIADO | DISPONIBLE
    titulo: str
    estado: Literal["OK", "PENDIENTE", "ERROR"]
    detalle: str
    solucion: str | None = None


class ReadinessDevice(BaseModel):
    idDispositivo: uuid.UUID
    codigoDispositivo: str
    nombre: str | None
    modeloSensor: str


# --- Identificación del dispositivo en la conexión de un operador -------------------------------------------------------------
# Separa tres cosas que no se confunden: la IDENTIDAD (qué Arduino es: su ID persistente, nunca el puerto COM), el INVENTARIO (a qué
# institución pertenece y en qué estado administrativo está) y la COMUNICACIÓN (si responde ahora). Registrar un dispositivo no
# implica que esté conectado, ni que esté conectado que se pueda medir con él.


class IdentificationInstitution(BaseModel):
    idInstitucion: uuid.UUID
    nombre: str


class IdentificationDevice(BaseModel):
    idDispositivo: uuid.UUID
    codigoDispositivo: str
    nombre: str | None
    modeloSensor: str
    versionFirmware: str | None = None
    estado: str  # estado ADMINISTRATIVO (OPERATIVO, EN_MANTENIMIENTO, FUERA_DE_SERVICIO, BAJA)


class IdentificationCandidate(BaseModel):
    idDispositivo: uuid.UUID
    codigoDispositivo: str
    nombre: str | None
    sugerido: bool = False  # coincide con el código configurado en el puente (no prueba que sea ese Arduino)


class DeviceIdentification(BaseModel):
    """Qué dispositivo hay conectado y cómo se relaciona con la institución activa del operador."""

    nivel: Literal["FISICA", "DECLARADA", "NINGUNA"]  # FISICA: ID propio del Arduino · DECLARADA: solo el código del puente · NINGUNA
    codigo: str | None
    firmware: str | None = None
    medio: str | None = None
    institucion: IdentificationInstitution
    # SIN_COMUNICACION · NO_REGISTRADO · DE_LA_INSTITUCION · SIN_INSTITUCION · DE_OTRA_INSTITUCION · IDENTIDAD_NO_CONFIRMADA
    situacion: str
    confirmada: bool  # la identidad quedó establecida (FISICA, o confirmada a mano por este operador)
    dispositivo: IdentificationDevice | None
    usable: bool
    motivoNoDisponible: str | None = None
    puedeRegistrar: bool
    # Vincular a la institución un dispositivo existente SIN institución (se pide una confirmación explícita): ver deviceConnection.link.
    puedeVincular: bool = False
    # Identidad solo declarada (firmware sin ID propio): registrar o vincular exige confirmar explícitamente que ESE es el Arduino conectado.
    requiereConfirmacion: bool = False
    # El dispositivo que corresponde al código configurado en el puente (solo identidad declarada y todavía sin confirmar).
    dispositivoDeclarado: IdentificationDevice | None = None
    candidatos: list[IdentificationCandidate] = []


class BridgeAuthority(BaseModel):
    """¿Puede quien consulta dar órdenes al puente? Lo resuelve el backend según el contexto del dispositivo que el puente atiende."""

    contexto: Literal["SIN_DISPOSITIVO", "PERSONAL", "INSTITUCIONAL_PROPIA", "INSTITUCIONAL_AJENA"]
    permitido: bool
    motivo: str | None = None


class TelemetryReadiness(BaseModel):
    listo: bool
    bloqueo: str | None  # id del primer paso que no está OK
    pasos: list[ReadinessStep]
    dispositivo: ReadinessDevice | None
    # Solo cuando un operador consulta en el contexto de una institución.
    identificacion: DeviceIdentification | None = None
    ordenesPuente: BridgeAuthority | None = None


class DeviceConnectRegister(BaseModel):
    """«Registrar nuevo dispositivo» desde la conexión. El código, el sensor y el firmware salen de lo que informa el Arduino: la
    persona solo pone un nombre. La institución es la que eligió al entrar (el servidor comprueba que pertenezca a ella)."""

    model_config = ConfigDict(extra="forbid")

    idInstitucion: uuid.UUID
    nombre: Annotated[str, Field(max_length=100)] | None = None
    # Solo con identidad declarada (firmware sin ID propio): la persona confirma que el Arduino conectado es el que está registrando.
    confirmaIdentidad: bool = False

    @field_validator("nombre", mode="before")
    @classmethod
    def recortar(cls, value):
        return (value.strip() or None) if isinstance(value, str) else value


class DeviceConnectLink(BaseModel):
    """«Vincular a la institución» un dispositivo existente que todavía no pertenece a ninguna. Requiere la confirmación explícita
    (`confirmaVinculacion: true`): deja de estar disponible para las cuentas individuales y pasa al inventario de la institución."""

    model_config = ConfigDict(extra="forbid")

    idInstitucion: uuid.UUID
    idDispositivo: uuid.UUID
    nombre: Annotated[str, Field(max_length=100)] | None = None
    confirmaVinculacion: bool = False
    confirmaIdentidad: bool = False

    @field_validator("nombre", mode="before")
    @classmethod
    def recortar(cls, value):
        return (value.strip() or None) if isinstance(value, str) else value


class DeviceConnectConfirm(BaseModel):
    """Seleccionar y confirmar un dispositivo existente de la institución para la conexión actual."""

    model_config = ConfigDict(extra="forbid")

    idInstitucion: uuid.UUID
    idDispositivo: uuid.UUID


class DeviceConnectResult(BaseModel):
    creado: bool
    vinculado: bool = False  # un dispositivo que existía sin institución pasó al inventario de la institución
    identificacion: DeviceIdentification


class TelemetrySessionStart(BaseModel):
    """Inicio de una sesión de medición con el dispositivo: el cliente solo elige perfil, dispositivo y contexto."""

    model_config = ConfigDict(extra="forbid")

    idPerfilMedicion: uuid.UUID
    idDispositivo: uuid.UUID
    # Modo elegido por la persona: se conserva en todo el ciclo (inicio, adquisición, guardado, historial y detalle).
    modoMedicion: Literal["OXIMETRIA", "GLUCOSA_EXPERIMENTAL"] = "OXIMETRIA"
    condicionComida: Literal["AYUNO", "POSTPRANDIAL", "NO_INFORMADA"] = "NO_INFORMADA"
    fechaHoraUltimaComida: datetime | None = None
    observacion: Annotated[str, Field(max_length=500)] | None = None
    # OPCIONALES y solo de esta medición (ver MeasurementStart): edad en años y sexo del modelo.
    edadAlMomento: Annotated[int, Field(ge=0, le=130)] | None = Field(default=None, validation_alias=AliasChoices("edadAlMomento", "edadInformada"))
    sexoModelo: Literal["MASCULINO", "FEMENINO"] | None = Field(default=None, validation_alias=AliasChoices("sexoModelo", "sexoInformado"))

    @field_validator("edadAlMomento", mode="before")
    @classmethod
    def edadVaciaEsNula(cls, value):
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("sexoModelo", mode="before")
    @classmethod
    def sexoVacioEsNulo(cls, value):
        return None if isinstance(value, str) and not value.strip() else normalizeUpper(value)

    @field_validator("condicionComida", "modoMedicion", mode="before")
    @classmethod
    def normalizarCondicion(cls, value):
        return normalizeUpper(value)

    @field_validator("fechaHoraUltimaComida", mode="before")
    @classmethod
    def normalizarFecha(cls, value):
        # «Última comida» es opcional: vacío o en blanco es NULL (no un error de formato).
        if isinstance(value, str) and not value.strip():
            return None
        return normalizeDateTime(value)
