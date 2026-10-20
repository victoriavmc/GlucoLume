# Measurement - Medicion
#
# El cliente solo informa el contexto de la medición. Los datos instantáneos del perfil y del
# dispositivo (edadAlMomento, sexoModelo, versionFirmwareAlMomento, modeloSensorAlMomento),
# los resultados (spo2, frecuenciaCardiaca, glucosaEstimada, calidadSenal, versionAlgoritmo,
# idMatriz), el estado y las fechas los establece el servidor.
# minutosDesdeUltimaComida y duracionMs son columnas calculadas por SQL Server.

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.schemas.device import ModeloSensor
from app.schemas.measurementProfile import SexoModelo
from app.utils.normalizers import normalizeDateTime, normalizeSentence, normalizeStatus, normalizeUpper

ModoMedicion = Literal["OXIMETRIA", "GLUCOSA_EXPERIMENTAL"]
EstadoMedicion = Literal["PENDIENTE", "ADQUIRIENDO", "PROCESANDO", "COMPLETADA", "INVALIDA", "CANCELADA"]
CondicionComida = Literal["AYUNO", "POSTPRANDIAL", "NO_INFORMADA"]


class MeasurementBase(BaseModel):
    observacion: Annotated[str, Field(max_length=500)] | None = None

    @field_validator("observacion", mode="before")
    @classmethod
    def normalizarObservacion(cls, value):
        return normalizeSentence(value)


class MeasurementCreate(MeasurementBase):
    model_config = ConfigDict(extra="forbid")

    idPerfilMedicion: uuid.UUID
    idDispositivo: uuid.UUID
    modoMedicion: ModoMedicion = "OXIMETRIA"
    fechaHoraUltimaComida: datetime | None = None
    condicionComida: CondicionComida = "NO_INFORMADA"

    @field_validator("modoMedicion", "condicionComida", mode="before")
    @classmethod
    def normalizarCodigo(cls, value):
        return normalizeUpper(value)

    @field_validator("fechaHoraUltimaComida", mode="before")
    @classmethod
    def normalizarFechaHora(cls, value):
        # «Última comida» es opcional: vacío o en blanco es NULL (no un error de formato).
        if isinstance(value, str) and not value.strip():
            return None
        return normalizeDateTime(value)


class MeasurementUpdate(MeasurementBase):
    model_config = ConfigDict(extra="forbid")


class MeasurementRead(MeasurementBase):
    model_config = ConfigDict(from_attributes=True)

    idMedicion: uuid.UUID
    idPerfilMedicion: uuid.UUID
    idDispositivo: uuid.UUID
    idMatriz: uuid.UUID | None = None
    modoMedicion: ModoMedicion
    estadoMedicion: EstadoMedicion
    fechaHoraInicio: datetime
    fechaHoraFin: datetime | None = None
    fechaHoraUltimaComida: datetime | None = None
    condicionComida: CondicionComida
    edadAlMomento: int | None = None
    sexoModelo: SexoModelo | None = None
    versionFirmwareAlMomento: str | None = None
    modeloSensorAlMomento: ModeloSensor | None = None
    versionAlgoritmo: str | None = None
    calidadSenal: Decimal | None = None
    spo2: Decimal | None = None
    frecuenciaCardiaca: int | None = None
    glucosaEstimada: Decimal | None = None
    minutosDesdeUltimaComida: int | None = None
    duracionMs: int | None = None

    @field_validator("modoMedicion", "condicionComida", "sexoModelo", "modeloSensorAlMomento", mode="before")
    @classmethod
    def normalizarCodigo(cls, value):
        return normalizeUpper(value)

    @field_validator("estadoMedicion", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)


# --- Contratos del módulo Medición (/measurements e historial institucional) -----------------------------------
#
# Aviso fijo en todo resultado: GlucoLume es una prueba experimental, no un diagnóstico ni un sustituto de
# mediciones clínicas certificadas.

from app.schemas.group import MetricSummary  # noqa: E402
from app.schemas.capillaryReference import (  # noqa: E402
    CapillaryReferenceMeasurementBase,
    CapillaryReferenceMeasurementRead,
)

EXPERIMENTAL_NOTICE = (
    "Resultado experimental de GlucoLume: no es un diagnóstico ni reemplaza una medición clínica certificada."
)


class MeasurementStart(MeasurementBase):
    """Inicio de una medición: el cliente solo elige perfil, dispositivo, modo y contexto. Edad, sexo, firmware,
    sensor, matriz, versión del algoritmo, estado y fechas los fija el servidor."""

    model_config = ConfigDict(extra="forbid")

    idPerfilMedicion: uuid.UUID
    idDispositivo: uuid.UUID
    modoMedicion: ModoMedicion = "OXIMETRIA"
    fechaHoraUltimaComida: datetime | None = None
    condicionComida: CondicionComida = "NO_INFORMADA"
    # OPCIONALES y solo de ESTA medición: la edad en años y el sexo del modelo. Prioridad: lo informado acá > el perfil de
    # medición > los datos de la cuenta > NULL. No modifican el perfil ni la cuenta; nunca se rechaza una solicitud por no traerlos.
    # `edadInformada` / `sexoInformado` son nombres equivalentes aceptados en la solicitud.
    edadAlMomento: Annotated[int, Field(ge=0, le=130)] | None = Field(default=None, validation_alias=AliasChoices("edadAlMomento", "edadInformada"))
    sexoModelo: SexoModelo | None = Field(default=None, validation_alias=AliasChoices("sexoModelo", "sexoInformado"))

    @field_validator("edadAlMomento", mode="before")
    @classmethod
    def edadVaciaEsNula(cls, value):
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("sexoModelo", mode="before")
    @classmethod
    def sexoVacioEsNulo(cls, value):
        return None if isinstance(value, str) and not value.strip() else normalizeUpper(value)

    @field_validator("modoMedicion", "condicionComida", mode="before")
    @classmethod
    def normalizarCodigo(cls, value):
        return normalizeUpper(value)

    @field_validator("fechaHoraUltimaComida", mode="before")
    @classmethod
    def normalizarFechaHora(cls, value):
        # «Última comida» es opcional: vacío o en blanco es NULL (no un error de formato).
        if isinstance(value, str) and not value.strip():
            return None
        return normalizeDateTime(value)


class SampleItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    numeroMuestra: Annotated[int, Field(ge=0)]
    tiempoRelativoMs: Annotated[int, Field(ge=0)] | None = None
    valorRed: Annotated[int, Field(ge=0)]
    valorIR: Annotated[int, Field(ge=0)]


class SamplesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    muestras: Annotated[list[SampleItem], Field(min_length=1, max_length=2000)]


class MeasurementFinish(MeasurementBase):
    """Cierre de la adquisición con los resultados que informa el procesamiento de la señal (el puente del
    dispositivo). La glucosa NUNCA se recibe del cliente: la calcula el servidor con la matriz y su regla."""

    model_config = ConfigDict(extra="forbid")

    spo2: Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)] | None = None
    frecuenciaCardiaca: Annotated[int, Field(gt=0, le=300)] | None = None
    calidadSenal: Annotated[Decimal, Field(ge=0, max_digits=6, decimal_places=3)] | None = None
    versionAlgoritmo: Annotated[str, Field(max_length=50)] | None = None


class CapillaryReferenceRequest(CapillaryReferenceMeasurementBase):
    model_config = ConfigDict(extra="forbid")


class MeasurementListItem(BaseModel):
    idMedicion: uuid.UUID
    fechaHoraInicio: datetime
    fechaHoraFin: datetime | None
    modoMedicion: str
    estadoMedicion: str
    condicionComida: str
    fechaHoraUltimaComida: datetime | None = None  # opcional: null = «Sin informar»
    edadAlMomento: int | None
    glucosaEstimada: Decimal | None
    spo2: Decimal | None
    frecuenciaCardiaca: int | None
    calidadSenal: Decimal | None
    observacion: str | None
    dispositivo: str | None = None
    # Datos informados por el dispositivo (puente serie). esDemo: valor sintético de prueba, no una glucemia.
    origenGlucosa: str | None = None
    glucosaDispositivo: Decimal | None = None
    indiceOptico: Decimal | None = None
    esDemo: bool = False
    # Una medición cancelada o inválida de la vista personal se oculta VISIBLE_MINUTES después de cerrarse; hasta cuándo se ve.
    visibleHasta: datetime | None = None


# --- Evolución histórica (GET /measurements/evolution) ---------------------------------------------------------------
# Una medición guardada = un punto. Se calcula sobre Medicion en cada consulta (no se guardan promedios). Las pruebas DEMO y los
# registros experimentales nunca se mezclan en una misma estadística.


class EvolutionPoint(BaseModel):
    idMedicion: uuid.UUID
    fecha: datetime
    modoMedicion: str
    origen: str | None  # DEMO | EXPERIMENTAL | SIN_CALIBRAR | null (sin dato del dispositivo)
    esDemo: bool
    frecuenciaCardiaca: int | None
    spo2: float | None
    glucosa: float | None  # solo valores con origen EXPERIMENTAL o DEMO; SIN_CALIBRAR nunca es una glucosa
    indiceOptico: float | None
    calidadSenal: float | None = None  # índice registrado por el equipo; null si no lo informó (no se asume ni se completa)


class EvolutionLast(BaseModel):
    valor: float
    fecha: datetime


class EvolutionStat(BaseModel):
    cantidad: int
    ultimo: EvolutionLast | None
    promedio: float | None
    minimo: float | None
    maximo: float | None


class EvolutionStats(BaseModel):
    mediciones: int
    frecuenciaCardiaca: EvolutionStat
    spo2: EvolutionStat
    glucosa: EvolutionStat
    indiceOptico: EvolutionStat
    calidadSenal: EvolutionStat | None = None


class EvolutionBlock(BaseModel):
    experimental: EvolutionStats | None  # NOT DEMO (None si el filtro no lo pide)
    demo: EvolutionStats | None  # solo pruebas DEMO (None si el filtro no lo pide)


class EvolutionLastMeasurement(BaseModel):
    fecha: datetime
    modoMedicion: str
    esDemo: bool


class EvolutionSummary(BaseModel):
    """Conteos de las mediciones COMPLETADAS del período y del modo elegidos, SIN importar el origen pedido (para mostrar DEMO y
    experimentales por separado aunque el gráfico muestre solo uno). `ultima` es la más reciente del historial, sin filtro de período."""
    total: int
    experimentales: int
    demo: int
    porModo: dict[str, int]
    ultima: EvolutionLastMeasurement | None


class EvolutionRead(BaseModel):
    origen: str  # EXPERIMENTAL | DEMO | TODOS
    desde: datetime | None
    hasta: datetime | None
    puntos: list[EvolutionPoint]
    truncado: bool  # hubo más mediciones que MAX_EVOLUTION_POINTS: se devuelven las más recientes
    estadisticas: EvolutionBlock
    resumen: EvolutionSummary | None = None


class MeasurementPage(BaseModel):
    items: list[MeasurementListItem]
    total: int
    pagina: int
    tamanioPagina: int


class DeviceSummary(BaseModel):
    idDispositivo: uuid.UUID
    codigoDispositivo: str
    nombre: str | None
    modelo: str | None
    modeloSensor: str
    versionFirmware: str | None


class MatrixSummary(BaseModel):
    idMatriz: uuid.UUID
    nombre: str
    version: str
    # GLOBAL o INSTITUCION: la matriz la elige el backend; se informa para que se vea cuál se aplicó.
    ambito: str


# --- Matriz de referencia de glucosa (detalle de una medición GLUCOSA_EXPERIMENTAL) ---------------------------------------------


class ReferenceRule(BaseModel):
    idRegla: uuid.UUID
    codigo: str
    sexoModelo: str
    edadDesde: int | None  # NULL = sin límite inferior (una regla sin rango de edad vale para cualquier edad)
    edadHasta: int | None
    condicionComida: str
    minutosComidaMin: int | None
    minutosComidaMax: int | None
    glucosaMinReferencia: float
    glucosaMaxReferencia: float


class ReferenceGroup(BaseModel):
    sexoModelo: str
    titulo: str
    reglas: list[ReferenceRule]  # candidatas según lo informado (sin elegir ninguna por la persona)
    reglaSeleccionada: ReferenceRule | None  # solo si edad, alimentación y regla quedan determinadas sin ambigüedad
    posicion: str | None  # DENTRO | POR_DEBAJO | POR_ENCIMA: comparación matemática con el intervalo, no una clasificación clínica
    aplicada: bool  # esta regla participó de una estimación del servidor
    motivoSinSeleccion: str | None


class GlucoseReference(BaseModel):
    estado: str  # APLICADA | REFERENCIA | SIN_MATRIZ
    matriz: MatrixSummary | None
    valor: float | None
    unidad: str
    origen: str | None  # DEMO | EXPERIMENTAL | SIN_CALIBRAR | null
    esDemo: bool
    sexoInformado: bool
    edadInformada: bool
    sexoModelo: str | None
    edad: int | None
    condicionComida: str
    minutosDesdeUltimaComida: int | None
    grupos: list[ReferenceGroup]
    avisoSexo: str | None


class MeasurementDetail(BaseModel):
    idMedicion: uuid.UUID
    idPerfilMedicion: uuid.UUID
    modoMedicion: str
    estadoMedicion: str
    fechaHoraInicio: datetime
    fechaHoraFin: datetime | None
    fechaHoraUltimaComida: datetime | None
    condicionComida: str
    minutosDesdeUltimaComida: int | None
    duracionMs: int | None
    edadAlMomento: int | None
    sexoModelo: str | None
    versionFirmwareAlMomento: str | None
    modeloSensorAlMomento: str | None
    versionAlgoritmo: str | None
    calidadSenal: Decimal | None
    spo2: Decimal | None
    frecuenciaCardiaca: int | None
    glucosaEstimada: Decimal | None
    observacion: str | None
    # Datos informados por el dispositivo (puente serie), guardados al confirmar «Guardar medición».
    origenGlucosa: str | None = None
    glucosaDispositivo: Decimal | None = None
    unidadGlucosa: str | None = None
    indiceOptico: Decimal | None = None
    lecturasEstabilizadas: int | None = None
    esDemo: bool = False
    puedeEliminar: bool = False
    unidades: dict[str, str] = {"spo2": "%", "frecuenciaCardiaca": "lpm", "glucosa": "mg/dL", "indiceOptico": "adimensional"}
    dispositivo: DeviceSummary
    matriz: MatrixSummary | None
    cantidadMuestras: int
    referenciaCapilar: CapillaryReferenceMeasurementRead | None
    # El usuario autenticado puede registrar muestras, cerrar o cancelar esta medición.
    puedeOperar: bool
    visibleHasta: datetime | None = None  # cancelada/inválida de la vista personal: hasta cuándo se ve
    referenciaGlucosa: GlucoseReference | None = None  # solo en modo GLUCOSA_EXPERIMENTAL
    # Quién recibe el resultado si se pide enviarlo por correo: CUENTA_PROPIA (individual), PACIENTE (el operador indica
    # el correo que el paciente informó) o None (no disponible: medición no completada o sin permiso de operar).
    envioResultado: Literal["CUENTA_PROPIA", "PACIENTE"] | None = None
    # Solo al guardar una medición de un paciente con correo cargado: resultado del envío automático (None si no correspondía: DEMO, sin correo).
    envioAutomatico: Literal["ENVIADO", "FALLIDO"] | None = None
    aviso: str = EXPERIMENTAL_NOTICE


class OwnProfileRead(BaseModel):
    """Perfil de medición propio del consumidor final (se construye desde Usuario)."""

    perfilDisponible: bool
    datosFaltantes: list[str]  # datos OBLIGATORIOS que faltan (hoy ninguno: medir no exige fecha de nacimiento ni sexo)
    datosRecomendados: list[str] = []  # fechaNacimiento / sexo sin informar: se recomiendan, no se exigen
    idPerfilMedicion: uuid.UUID | None = None
    nombre: str | None = None
    apellido: str | None = None
    fechaNacimiento: date | None = None
    edad: int | None = None
    sexoModelo: str | None = None
    fechaCreacion: datetime | None = None
    fechaUltimaMedicion: datetime | None = None


class InstitutionIndicators(BaseModel):
    """Indicadores agregados de la institución: sin ningún dato identificativo de pacientes."""

    pacientesActivos: int
    operadoresActivos: int
    medicionesTotal: int
    medicionesPorEstado: dict[str, int]
    medicionesPorModo: dict[str, int]
    completadas: dict[str, MetricSummary]
