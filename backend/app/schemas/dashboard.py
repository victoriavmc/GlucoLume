# Dashboard - Contratos de los dashboards por ámbito (personal, familiar, institucional, operador y paciente)
#
# Todo se calcula sobre Medicion (y PerfilMedicion); ningún dashboard guarda copias. Las estadísticas usan solo mediciones
# COMPLETADA. Los valores sin datos llegan como null (la interfaz muestra «Sin datos disponibles», nunca ceros).

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.group import FamilyGroupDetail, GroupMemberRead, MetricSummary, SharedMeasurementRead, SharedStatisticsRead
from app.schemas.measurement import MeasurementListItem


class Period(BaseModel):
    dias: int | None
    desde: date | None
    hasta: date | None


class LastValue(BaseModel):
    valor: float
    fecha: datetime


class MeasurementSummary(BaseModel):
    """Conteos y últimos valores de un conjunto de mediciones."""

    total: int
    completadas: int
    enPeriodo: int
    ultimaMedicion: datetime | None
    ultimaGlucosa: LastValue | None
    ultimaSpo2: LastValue | None
    ultimaFrecuencia: LastValue | None


# --- Personal ---------------------------------------------------------------------------------------------------


class PersonalDashboard(BaseModel):
    perfilDisponible: bool
    datosFaltantes: list[str] = []
    periodo: Period
    resumen: MeasurementSummary | None
    estadisticas: SharedStatisticsRead | None
    # Mediciones guardadas (COMPLETADA), incluidas las de prueba DEMO identificadas por `esDemo`. Los indicadores y promedios
    # de `resumen` y `estadisticas` NO las incluyen.
    recientes: list[MeasurementListItem]
    ultimaGuardada: MeasurementListItem | None = None
    pruebasDemo: int = 0  # cantidad de mediciones de prueba (DEMO) guardadas; no suman a las experimentales


# --- Institucional ----------------------------------------------------------------------------------------------


class DayCount(BaseModel):
    fecha: date
    total: int
    completadas: int


class OperatorLoad(BaseModel):
    idInstitucionUsuario: uuid.UUID
    nombre: str | None
    apellido: str | None
    activo: bool
    pacientesAsignados: int
    mediciones: int  # en el período, atribuidas a quien las inició (trazabilidad histórica)


class AdminFilters(BaseModel):
    operador: uuid.UUID | None
    modo: str | None
    estado: str | None
    origen: Literal["TODOS", "EXPERIMENTAL", "DEMO"]


class AdminCounts(BaseModel):
    """Cantidades ADMINISTRATIVAS de mediciones (actividad), no resultados de salud: cuenta toda medición iniciada, tenga o no valores.
    total = completadas + canceladas + invalidas + enCurso = experimentales + demo + sinResultado. «Sin resultado» son las no completadas sin
    origen (canceladas, inválidas o en curso): no son experimentales ni DEMO."""
    total: int
    completadas: int
    canceladas: int
    invalidas: int
    enCurso: int
    experimentales: int
    demo: int
    sinResultado: int


class AdminDay(BaseModel):
    fecha: date
    completadas: int
    canceladas: int
    invalidas: int
    enCurso: int
    experimentales: int
    demo: int


class AdminMode(AdminCounts):
    modo: str


class AdminState(BaseModel):
    estado: str
    total: int
    experimentales: int
    demo: int
    sinResultado: int


class AdminFood(BaseModel):
    """Mediciones por condición de alimentación registrada; NO_INFORMADA es «Sin informar». Solo cantidades."""
    condicion: str
    total: int


class AdminPatientBand(BaseModel):
    """Cuántos pacientes aportaron `desde`..`hasta` mediciones (hasta=None: o más); desde=0 son los activos sin mediciones. Sin identificar a nadie."""
    desde: int
    hasta: int | None
    pacientes: int


class AdminOperator(AdminCounts):
    """Actividad laboral de un operador (vínculo histórico): cantidades por quien INICIÓ las mediciones. Nunca valores ni pacientes."""
    idInstitucionUsuario: uuid.UUID
    nombre: str | None
    apellido: str | None
    activo: bool
    pacientesAsignados: int


class AdminKpis(AdminCounts):
    pacientesRegistrados: int  # del período operativo vigente, activos y dados de baja
    pacientesActivos: int
    pacientesConMediciones: int  # pacientes DISTINTOS con al menos una medición que cumple el período y los filtros (no la cantidad de mediciones)
    pacientesSinOperador: int  # activos cuyo responsable ya no está vinculado
    pacientesAsignadosOperador: int | None  # solo con el filtro de operador
    operadoresActivos: int
    moderadoresActivos: int
    transferenciasPendientes: int
    transferenciasTotal: int
    dispositivosDisponibles: int
    dispositivosRegistrados: int


class AdminStats(BaseModel):
    filtros: AdminFilters
    operadores: list[PersonRef]  # opciones del filtro: operadores vinculados y desvinculados con actividad en el período
    kpis: AdminKpis
    serie: list[AdminDay]
    porModo: list[AdminMode]
    porEstado: list[AdminState]
    porAlimentacion: list[AdminFood] = []
    pacientesPorCantidad: list[AdminPatientBand] = []  # distribución de pacientes según cuántas mediciones tienen (admite varias el mismo día)
    porOperador: list[AdminOperator]  # vinculados y desvinculados con actividad en el período (el desvinculado sin actividad se omite)
    truncado: bool = False


class HealthDay(BaseModel):
    """Promedio de UN día con cuántas observaciones válidas lo componen (por variable): nunca es una medición individual."""
    fecha: date
    mediciones: int
    glucosaPromedio: float | None = None
    glucosaN: int = 0
    spo2Promedio: float | None = None
    spo2N: int = 0
    frecuenciaPromedio: float | None = None
    frecuenciaN: int = 0


class HealthPoint(BaseModel):
    """Una medición DEMO (sintética) con su fecha y hora reales y sus valores, sin identificar paciente, operador ni medición."""
    fecha: datetime
    glucosa: float | None = None
    spo2: float | None = None
    frecuenciaCardiaca: float | None = None


class HealthGroup(BaseModel):
    """Resultados de salud AGREGADOS de un solo origen (experimental o DEMO): nunca se mezclan en un mismo promedio. Solo mediciones COMPLETADA.
    DISPONIBLE = hay resultados; PROTEGIDO = faltan pacientes distintos para informarlos (solo experimentales); SIN_DATOS = no hay mediciones con
    esos filtros; NO_APLICA = el filtro elegido no se puede aplicar a este origen (se explica en `motivo`). `sinInformar` cuenta las mediciones
    incluidas que no registraron cada valor."""

    origen: Literal["EXPERIMENTAL", "DEMO"]
    estado: Literal["DISPONIBLE", "PROTEGIDO", "SIN_DATOS", "NO_APLICA"]
    motivo: str | None = None
    mediciones: int = 0
    pacientes: int = 0
    spo2: MetricSummary | None = None
    frecuenciaCardiaca: MetricSummary | None = None
    glucosa: MetricSummary | None = None
    calidadSenal: MetricSummary | None = None  # cuando está registrada; su ausencia no impide mostrar las demás variables
    alimentacion: dict[str, int] = {}  # mediciones por condición registrada (NO_INFORMADA = «Sin informar»)
    porModo: dict[str, int] = {}  # mediciones incluidas por modo
    sinInformar: dict[str, int] = {}
    serieDiaria: list[HealthDay] = []  # promedio por día con sus observaciones; experimentales: solo días con el mínimo de pacientes
    # Cada medición con su fecha y hora reales: SOLO para DEMO (valores simulados que no describen a nadie). En experimentales nunca: ahí un
    # punto individual sería el resultado de salud de una persona.
    puntos: list[HealthPoint] = []


class HealthAggregates(BaseModel):
    minimoPacientes: int  # pacientes distintos mínimos para informar resultados EXPERIMENTALES (los DEMO son sintéticos: sin mínimo)
    filtros: AdminFilters
    experimentales: HealthGroup | None = None  # None si el filtro de origen es DEMO
    demo: HealthGroup | None = None  # None si el filtro de origen es EXPERIMENTAL


class InstitutionDashboard(BaseModel):
    periodo: Period
    # Pacientes de operadores desvinculados que esperan un nuevo responsable (services/reassignments.py).
    pacientesPendientesReasignacion: int = 0
    pacientesActivos: int
    moderadoresActivos: int
    operadoresActivos: int
    dispositivosRegistrados: int
    dispositivosOperativos: int
    medicionesTotal: int
    medicionesHoy: int
    medicionesUltimos7Dias: int
    medicionesUltimos30Dias: int
    medicionesEnPeriodo: int
    porEstado: dict[str, int]
    porModo: dict[str, int]
    ultimaActividad: datetime | None
    serie: list[DayCount]
    estadisticas: SharedStatisticsRead
    porOperador: list[OperatorLoad]
    # True si hay menos pacientes con mediciones que el mínimo para informar estadísticas de salud agregadas: no se informan (sin
    # promedios ni serie diaria) para que un período o un grupo pequeño no permita identificar a una persona.
    agregadosProtegidos: bool = False
    minimoPacientesAgregados: int = 5
    administrativo: AdminStats | None = None  # conteos administrativos desde el primer registro (los resultados de salud siguen protegidos)
    saludAgregada: HealthAggregates | None = None  # resultados de salud agregados, por origen y con los filtros de período, modo y origen


class PersonRef(BaseModel):
    idInstitucionUsuario: uuid.UUID
    nombre: str | None
    apellido: str | None
    rolInstitucion: str | None = None
    activo: bool = True


class AssignedPatient(BaseModel):
    idPerfilMedicion: uuid.UUID
    identificadorPseudonimo: str | None
    nombre: str | None
    apellido: str | None
    datosIdentificativos: bool | None
    edad: int | None
    sexoModelo: str | None
    ultimaMedicion: datetime | None  # la más reciente COMPLETADA, sea experimental o DEMO
    ultimaModo: str | None = None
    ultimaEsDemo: bool | None = None  # True si esa última medición es DEMO (simulada)


class PerformedMeasurement(BaseModel):
    idMedicion: uuid.UUID
    idPerfilMedicion: uuid.UUID
    paciente: str | None
    fechaHoraInicio: datetime
    modoMedicion: str
    estadoMedicion: str
    glucosaEstimada: float | None
    spo2: float | None
    frecuenciaCardiaca: int | None
    dispositivo: str | None
    operador: str | None = None
    esDemo: bool = False  # medición de prueba DEMO (valores simulados): siempre se identifica


class TransferCounters(BaseModel):
    recibidas: int
    recibidasPendientes: int
    enviadas: int
    enviadasPendientes: int


class AvailableDevice(BaseModel):
    idDispositivo: uuid.UUID
    codigoDispositivo: str
    nombre: str | None
    modeloSensor: str


class OperatorDay(BaseModel):
    fecha: date
    experimentales: int
    demo: int


class OperatorModeCount(BaseModel):
    modo: str
    experimentales: int
    demo: int


class QualityBin(BaseModel):
    desde: float
    hasta: float
    experimentales: int
    demo: int


class ReadingsBin(BaseModel):
    lecturas: int  # lecturas estabilizadas que registró el equipo
    experimentales: int
    demo: int


class OperatorQuality(BaseModel):
    """Distribución de `calidadSenal` (número registrado por el equipo; el modelo no define categorías ni umbrales): rangos iguales del
    intervalo observado. Solo mediciones de pacientes que el operador tiene a cargo HOY; las de pacientes ya transferidos se cuentan aparte."""
    conValor: int
    sinDato: int
    fueraDeAlcance: int
    minimo: float | None
    maximo: float | None
    rangos: list[QualityBin]
    # Las mediciones que llegan del equipo (experimentales y DEMO) no traen `calidadSenal` (se guarda en null) pero sí cuántas lecturas
    # estabilizadas registró: se informan aparte, sin presentarlas como calidad.
    conLecturas: int = 0
    lecturas: list[ReadingsBin] = []


class DemographicRow(BaseModel):
    rango: str  # rango de edad calculada (fecha de nacimiento o edad declarada) o «SIN_INFORMAR»
    masculino: int
    femenino: int
    sinInformar: int  # sexo sin informar


class OperatorCharts(BaseModel):
    sinResultado: int = 0  # mediciones del período no completadas y sin origen: fuera de la serie y de los modos por origen
    serie: list[OperatorDay]  # mediciones iniciadas por el operador en el período, por día
    porModo: list[OperatorModeCount]
    calidadSenal: OperatorQuality
    demografia: list[DemographicRow]  # pacientes únicos asignados ahora
    pacientesDemografia: int
    truncado: bool = False


class OperatorDashboard(BaseModel):
    periodo: Period
    operador: PersonRef
    pacientesAsignados: int
    pacientes: list[AssignedPatient]
    medicionesRealizadas: int
    medicionesEnPeriodo: int
    medicionesRealizadasDemo: int = 0  # además de `medicionesRealizadas` (que no incluye DEMO)
    medicionesEnPeriodoDemo: int = 0
    # De `medicionesEnPeriodo` (no DEMO): las no completadas no son «experimentales», no tienen resultado ni origen.
    medicionesEnPeriodoSinResultado: int = 0
    medicionesSinResultado: int = 0  # ídem sobre `medicionesRealizadas`
    medicionesPorEstado: dict[str, int]
    ultimaActividad: datetime | None
    graficos: OperatorCharts | None = None  # solo el propio operador
    realizadas: list[PerformedMeasurement]
    ultimasDePacientes: list[PerformedMeasurement]
    transferencias: TransferCounters
    dispositivosDisponibles: int
    dispositivos: list[AvailableDevice]
    esPropio: bool


class PatientProfileInfo(BaseModel):
    idPerfilMedicion: uuid.UUID
    identificadorPseudonimo: str | None
    nombre: str | None
    apellido: str | None
    datosIdentificativos: bool | None
    edad: int | None
    fechaNacimiento: date | None
    sexoModelo: str | None
    estado: str
    responsable: PersonRef | None
    ultimaMedicion: datetime | None


class PatientTransferRow(BaseModel):
    idTransferenciaPerfil: uuid.UUID
    estado: str
    tipo: Literal["TRANSFERENCIA", "REASIGNACION"]
    fechaPeticion: datetime
    fechaTransferencia: datetime | None
    origen: PersonRef | None
    destino: PersonRef


class PatientDashboard(BaseModel):
    periodo: Period
    perfil: PatientProfileInfo
    resumen: MeasurementSummary
    estadisticas: SharedStatisticsRead
    historial: list[PerformedMeasurement]
    transferencias: list[PatientTransferRow]


# --- Familiar ---------------------------------------------------------------------------------------------------


class GroupActivity(BaseModel):
    """Un hecho de la actividad compartida, siempre con su fecha y hora completas.

    MEDICION: la última medición de quien autorizó compartir «última medición» o «historial»; trae los valores autorizados.
    AVISO: una medición de quien autorizó «aviso de medición»; trae solo la fecha y hora, NUNCA valores (`medicion` es null)."""

    idGrupoUsuario: uuid.UUID
    nombre: str | None
    apellido: str | None
    tipo: str = "MEDICION"  # MEDICION | AVISO
    fechaHoraInicio: datetime
    medicion: SharedMeasurementRead | None = None


class GroupAggregate(BaseModel):
    """Estadísticas agrupadas SOLO con integrantes que compartieron su historial."""

    participantes: list[str]
    estadisticas: SharedStatisticsRead


class GroupDashboard(BaseModel):
    grupo: FamilyGroupDetail
    periodo: Period
    integrantesActivos: int
    administradores: int
    miembros: int
    comparteUltimaMedicion: int
    comparteHistorial: int
    integrantes: list[GroupMemberRead]
    actividadReciente: list[GroupActivity]
    agregado: GroupAggregate | None
    motivoSinAgregado: str | None
