# PatientAnalytics - Contratos del dashboard analítico de pacientes y mediciones (operador)
#
# Todo se calcula en el backend sobre Medicion y PerfilMedicion y SOLO sobre los pacientes que el operador autenticado tiene a cargo hoy.
# Reglas de presentación que los contratos hacen explícitas:
#   · un dato que falta llega como null o en la categoría SIN_INFORMAR; nunca como 0;
#   · cada estadística lleva `n` (observaciones válidas con ese dato) y se calcula solo con ellas;
#   · los datos DEMO (sintéticos) y los experimentales viajan SIEMPRE en series separadas: nunca se promedian juntos.

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.dashboard import Period

Origen = Literal["TODOS", "EXPERIMENTAL", "DEMO"]
Grupo = Literal["EXPERIMENTAL", "DEMO"]
Variable = Literal["spo2", "frecuenciaCardiaca", "glucosaDispositivo", "glucosaEstimada", "indiceOptico"]
Granularidad = Literal["dia", "semana", "mes"]
Segmentacion = Literal["NINGUNA", "SEXO", "EDAD", "ALIMENTACION", "MODO", "ORIGEN", "DISPOSITIVO", "MATRIZ"]
SIN_INFORMAR = "SIN_INFORMAR"


class AppliedFilters(BaseModel):
    idPerfilMedicion: uuid.UUID | None
    sexo: str | None
    edad: str | None
    edadBase: Literal["ACTUAL", "MEDICION"]
    edadCortes: list[int]
    alimentacion: str | None
    modo: str | None
    origen: Origen
    estado: str
    calidad: str | None
    calidadMinima: float | None
    variable: Variable
    granularidad: Granularidad
    segmentar: Segmentacion
    compararMatriz: bool


class Bucket(BaseModel):
    categoria: str
    pacientes: int  # pacientes únicos del alcance en esta categoría
    conMediciones: int  # de ellos, los que tienen al menos una medición con los filtros activos


class CategoryCount(BaseModel):
    categoria: str
    mediciones: int


class ModeOrigin(BaseModel):
    modo: str
    origen: Grupo
    mediciones: int


class Faltante(BaseModel):
    campo: str
    sinDato: int
    sobre: int  # mediciones del conjunto filtrado sobre las que se cuenta


class AnalyticsKpis(BaseModel):
    pacientesEnAlcance: int  # pacientes a cargo que cumplen los filtros de paciente (sexo, edad, paciente)
    pacientesConMediciones: int  # pacientes ÚNICOS con al menos una medición con los filtros activos
    totalMediciones: int  # mediciones (no pacientes) con los filtros activos
    completadas: int
    experimentales: int
    demo: int
    porModo: dict[str, int]  # solo mediciones con resultado (experimentales + DEMO): no incluye las «sin resultado»
    sinResultado: int = 0  # canceladas/inválidas/en curso sin origen: no son experimentales ni DEMO; totalMediciones = experimentales + demo + sinResultado
    conSenalValida: int  # completadas con lecturas estabilizadas informadas (criterio de estabilidad del dispositivo)
    faltantes: list[Faltante]


class VariableStat(BaseModel):
    n: int
    promedio: float | None
    minimo: float | None
    maximo: float | None


class VariablePoint(BaseModel):
    periodo: date
    n: int
    promedio: float | None
    minimo: float | None
    maximo: float | None


class VariableSeries(BaseModel):
    origen: Grupo
    resumen: VariableStat
    puntos: list[VariablePoint]


class VariableBlock(BaseModel):
    variable: Variable
    unidad: str
    series: list[VariableSeries]


class CountPoint(BaseModel):
    periodo: date
    experimentales: int
    demo: int


class QualityRange(BaseModel):
    desde: float
    hasta: float
    mediciones: int


class ReadingsBin(BaseModel):
    lecturas: int  # lecturas estabilizadas que registró el equipo en esa medición
    experimentales: int
    demo: int


class QualityBlock(BaseModel):
    """`calidadSenal` solo la guarda el procesamiento de la señal cruda en el servidor: las mediciones que llegan del equipo (puente serie,
    experimentales o DEMO) la dejan en null y registran en cambio `lecturasEstabilizadas`. Se informan las dos, sin mezclarlas ni inventar
    umbrales: si `conValor` es 0, la interfaz explica por qué y muestra las lecturas estabilizadas como lo que son."""
    conValor: int
    sinInformar: int
    rangos: list[QualityRange]  # partición en partes iguales del rango observado: el modelo no define umbrales de calidad
    conLecturas: int = 0
    lecturas: list[ReadingsBin] = []


class LastValues(BaseModel):
    fecha: datetime
    modo: str
    origen: Grupo
    spo2: float | None
    frecuenciaCardiaca: int | None
    glucosa: float | None


class PatientRow(BaseModel):
    idPerfilMedicion: uuid.UUID
    identificadorPseudonimo: str | None
    nombre: str | None
    apellido: str | None
    edad: int | None
    sexoModelo: str | None
    medicionesExperimentales: int
    medicionesDemo: int
    ultima: LastValues | None


class PatientTable(BaseModel):
    items: list[PatientRow]
    total: int
    pagina: int
    tamanioPagina: int


class ReferenceInfo(BaseModel):
    estado: str  # APLICADA | REFERENCIA | SIN_MATRIZ
    matriz: str | None
    minimo: float | None
    maximo: float | None
    posicion: str | None  # DENTRO | POR_DEBAJO | POR_ENCIMA: comparación matemática, no una clasificación clínica
    motivo: str | None = None  # por qué no hay intervalo aplicable (sin matriz, condición sin regla…)


class SegmentRow(BaseModel):
    categoria: str  # «SIN_INFORMAR» cuando el dato falta; en DISPOSITIVO/MATRIZ, el nombre
    origen: Grupo  # DEMO y experimental nunca comparten fila
    mediciones: int
    n: int  # observaciones válidas de la variable elegida en esta fila (completadas que traen el dato)
    promedio: float | None
    minimo: float | None
    maximo: float | None


class MatrixSummary(BaseModel):
    comparadas: int
    dentro: int
    porDebajo: int
    porEncima: int
    sinReferencia: int
    limitado: bool  # había más mediciones comparables que el tope por consulta


class MeasurementPoint(BaseModel):
    idMedicion: uuid.UUID
    fecha: datetime
    modo: str
    origen: Grupo
    estado: str
    alimentacion: str
    edadAlMomento: int | None
    calidadSenal: float | None
    spo2: float | None
    frecuenciaCardiaca: int | None
    glucosaDispositivo: float | None
    glucosaEstimada: float | None
    indiceOptico: float | None
    referencia: ReferenceInfo | None = None


class PatientDetail(BaseModel):
    idPerfilMedicion: uuid.UUID
    identificadorPseudonimo: str | None
    nombre: str | None
    apellido: str | None
    fechaNacimiento: date | None
    edadActual: int | None
    sexoModelo: str | None
    puntos: list[MeasurementPoint]
    puntosTruncados: bool
    resumenMatriz: MatrixSummary | None = None  # solo si se pidió la comparación (glucosa experimental de este paciente)


class OriginTotals(BaseModel):
    """Mediciones que cumplen TODOS los filtros activos salvo el origen: permiten explicar un resultado vacío («hay 6 DEMO, ninguna experimental»)."""
    experimentales: int
    demo: int
    sinResultado: int = 0


class PatientAnalytics(BaseModel):
    periodo: Period
    filtros: AppliedFilters
    kpis: AnalyticsKpis
    sexo: list[Bucket]
    edades: list[Bucket]
    rangosEdad: list[str]  # códigos de los rangos con los cortes elegidos, más SIN_INFORMAR
    segmentacion: list[SegmentRow] = []  # vacío si no se pidió segmentar
    edadBaseDemografia: Literal["ACTUAL"] = "ACTUAL"
    porModoOrigen: list[ModeOrigin]
    alimentacion: list[CategoryCount]  # mediciones por condición de última comida (NO_INFORMADA se muestra como «Sin informar», nunca como ayuno)
    evolucion: list[CountPoint]
    variable: VariableBlock
    calidad: QualityBlock
    pacientes: PatientTable
    paciente: PatientDetail | None = None
    origenes: OriginTotals | None = None
    truncado: bool = False
