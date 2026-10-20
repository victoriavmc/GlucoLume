# PatientAnalytics - Dashboard analítico de pacientes y mediciones del operador
#
# ALCANCE (lo decide este módulo, nunca el cliente): solo el OPERADOR autenticado, con vínculo ACTIVO y permiso de operar pacientes, y SOLO
# sobre los pacientes ACTIVOS que tiene a cargo hoy (misma regla que patientAccess: el rol administrativo —propietario, moderador— no
# autoriza información de salud individual). No hay parámetro para elegir otro operador. Un paciente elegido por filtro pasa por
# measurements.requireClinicalAccess (asignación vigente, aislamiento por institución y auditoría del intento rechazado).
# Pacientes dados de baja, desidentificados (retención) o de otro período de la institución no están en el alcance.
#
# DATOS: se recuperan TODOS los campos registrados de cada medición, sin importar su modo: una oximetría puede traer glucosa y una medición
# de glucosa trae SpO₂ y frecuencia cardíaca. Lo que falta es «Sin informar» o queda fuera de ESA estadística; jamás se reemplaza por 0
# ni se interpreta (alimentación desconocida no es ayuno). Cada estadística informa cuántas observaciones válidas usó.
#
# ORIGEN: por defecto EXPERIMENTAL (todo lo que no es DEMO). DEMO solo con pedido expreso. Con «TODOS» las series viajan SEPARADAS: los
# valores sintéticos nunca se promedian con los experimentales ni se presentan como una misma población.
#
# SEXO Y EDAD: el sistema guarda sexo biológico del modelo (sexoModelo), no género; no se asigna por suposición. La edad ACTUAL sale de la
# fecha de nacimiento (o de la edad declarada si no hay fecha); la edad AL MOMENTO de cada medición es Medicion.edadAlMomento. Son dos
# filtros distintos (edadBase) y no se mezclan.
#
# VOLUMEN: se leen solo las columnas necesarias de las mediciones filtradas del alcance y se agregan acá; al navegador viajan agregados
# (y, para un paciente elegido, sus puntos individuales con un tope). Un conjunto mayor a MAX_ROWS se informa como truncado.

import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, not_, select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.models.device import Device
from app.models.matrix import Matrix
from app.models.measurement import NOT_DEMO, ORIGEN_DEMO, Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.user import User
from app.schemas.patientAnalytics import (
    SIN_INFORMAR, AnalyticsKpis, AppliedFilters, Bucket, CategoryCount, CountPoint, Faltante, LastValues, MeasurementPoint, ModeOrigin,
    MatrixSummary, OriginTotals, PatientAnalytics, PatientDetail, PatientRow, PatientTable, QualityBlock, QualityRange, ReadingsBin, ReferenceInfo, SegmentRow, VariableBlock,
    VariablePoint, VariableSeries, VariableStat,
)
from app.services import glucoseReference
from app.services import institution as institutions
from app.services import institutionPatients as patients
from app.services import measurement as measurements
from app.services import patientAccess, profileTransfers as transfers
from app.services.audit import registerEvent
from app.schemas.dashboard import Period
from app.services.dashboard import _range
from app.services.measurementProfile import calculateAge
from app.utils.timeZone import nowForDb

MAX_ROWS = 100_000
MAX_DETAIL_POINTS = 500
MAX_PAGE_SIZE = 50
MATRIX_LIMIT = 100  # comparaciones con la matriz por consulta: cada una lee las reglas de su medición
IN_CHUNK = 1000  # SQL Server admite ~2100 parámetros por consulta: los pacientes se consultan por tandas
DEFAULT_CUTS = [12, 17, 30, 50, 70]  # techo de cada rango; el último queda abierto («71+»)
SEGMENTS = ("NINGUNA", "SEXO", "EDAD", "ALIMENTACION", "MODO", "ORIGEN", "DISPOSITIVO", "MATRIZ")
SEXES = ("MASCULINO", "FEMENINO")
FOODS = ("AYUNO", "POSTPRANDIAL", "NO_INFORMADA")
MODES = ("OXIMETRIA", "GLUCOSA_EXPERIMENTAL")
STATES = ("COMPLETADA", "INVALIDA", "CANCELADA", "PENDIENTE", "ADQUIRIENDO", "PROCESANDO")
VARIABLES = {
    "spo2": (Measurement.spo2, "%"),
    "frecuenciaCardiaca": (Measurement.frecuenciaCardiaca, "lpm"),
    "glucosaDispositivo": (Measurement.glucosaDispositivo, "mg/dL"),  # valor del firmware: experimental calibrado o DEMO
    "glucosaEstimada": (Measurement.glucosaEstimada, "mg/dL"),  # estimación con la matriz experimental
    "indiceOptico": (Measurement.indiceOptico, ""),
}

_COLUMNS = (
    Measurement.idMedicion, Measurement.idPerfilMedicion, Measurement.fechaHoraInicio, Measurement.modoMedicion, Measurement.estadoMedicion,
    Measurement.origenGlucosa, Measurement.condicionComida, Measurement.edadAlMomento, Measurement.calidadSenal, Measurement.spo2,
    Measurement.frecuenciaCardiaca, Measurement.glucosaDispositivo, Measurement.glucosaEstimada, Measurement.indiceOptico,
    Measurement.lecturasEstabilizadas, Measurement.sexoModelo, Measurement.idDispositivo, Measurement.idMatriz,
)


ANALYSIS_DAYS = (180, 365)  # además de 7, 30 y 90: la pantalla de análisis ofrece estos períodos más largos


def _period(dias: int, desde: date | None, hasta: date | None):
    """Mismo período que el resto de los dashboards (7, 30, 90 días o un rango), más 180 y 365 días que ofrece el análisis."""
    if not (desde or hasta) and dias in ANALYSIS_DAYS:
        return nowForDb() - timedelta(days=dias), None, Period(dias=dias, desde=None, hasta=None)
    return _range(dias, desde, hasta)


def _invalid(message: str) -> AuthError:
    return AuthError("DATOS_INVALIDOS", message)


def parseCuts(raw: str | None) -> list[int]:
    """«12,17,30,50,70» → techo de cada rango (el último rango queda abierto). Estrictamente crecientes, de 1 a 8 cortes."""
    if raw is None or not raw.strip():
        return list(DEFAULT_CUTS)
    try:
        cuts = [int(part) for part in raw.split(",") if part.strip()]
    except ValueError as error:
        raise _invalid("Los cortes de edad tienen que ser números enteros separados por comas.") from error
    if not 1 <= len(cuts) <= 8 or any(c < 0 or c > 130 for c in cuts) or any(a >= b for a, b in zip(cuts, cuts[1:], strict=False)):
        raise _invalid("Los cortes de edad tienen que ser entre 1 y 8 números crecientes entre 0 y 130.")
    return cuts


def ageBuckets(cuts: list[int]) -> list[tuple[str, int, int | None]]:
    buckets, low = [], 0
    for cut in cuts:
        buckets.append((f"{low}-{cut}", low, cut))
        low = cut + 1
    buckets.append((f"{low}+", low, None))
    return buckets


def _ageRange(age: int | None, buckets) -> str:
    if age is None:
        return SIN_INFORMAR
    return next((label for label, low, high in buckets if age >= low and (high is None or age <= high)), SIN_INFORMAR)


def _noResult(row) -> bool:
    """Medición sin resultado: no completada y sin origen (el origen se fija al completarse). No es experimental ni DEMO: se cuenta aparte
    y no se rotula «experimental» solo por no ser DEMO."""
    return row.estadoMedicion != "COMPLETADA" and row.origenGlucosa is None


NO_RESULT = and_(Measurement.estadoMedicion != "COMPLETADA", Measurement.origenGlucosa.is_(None))


def _group(row) -> str:
    return "DEMO" if row.origenGlucosa == ORIGEN_DEMO else "EXPERIMENTAL"


def _num(value) -> float | None:
    return None if value is None else float(value)


def _stat(values: list[float]) -> VariableStat:
    if not values:
        return VariableStat(n=0, promedio=None, minimo=None, maximo=None)
    return VariableStat(n=len(values), promedio=round(sum(values) / len(values), 2), minimo=min(values), maximo=max(values))


def _bucketStart(moment: datetime, granularity: str) -> date:
    day = moment.date()
    if granularity == "semana":
        return day - timedelta(days=day.weekday())
    if granularity == "mes":
        return day.replace(day=1)
    return day


def _requireOperator(db: Session, actor: User, idInstitucion: uuid.UUID):
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_PACIENTES)
    relation = membership.relation
    if (membership.role != institutions.ROL_OPERADOR or relation.estadoRelacion != institutions.RELACION_ACTIVO
            or not membership.can(institutions.P_GESTIONAR_PACIENTES)):
        registerEvent(db, "ACCESO", "CONSULTAR_ANALISIS_PACIENTES", False, actor.idUsuario, "InstitucionUsuario", relation.idInstitucionUsuario,
                      observacion="Motivo: SOLO_OPERADOR_RESPONSABLE")
        db.commit()
        raise AuthError("MEDICIONES_NO_AUTORIZADAS", patientAccess.MEASUREMENTS_NOT_AUTHORIZED)
    return membership


def analyze(
    db: Session, actor: User, idInstitucion: uuid.UUID, *, dias: int = 30, desde: date | None = None, hasta: date | None = None,
    idPerfilMedicion: uuid.UUID | None = None, sexo: str | None = None, edad: str | None = None, edadBase: str = "ACTUAL",
    alimentacion: str | None = None, modo: str | None = None, origen: str = "TODOS", estado: str = "TODOS",
    calidad: str | None = None, variable: str = "spo2", granularidad: str = "dia", compararMatriz: bool = False,
    pagina: int = 1, tamanioPagina: int = 10, edadCortes: list[int] | str | None = None, segmentar: str = "NINGUNA",
    calidadMinima: float | None = None,
) -> PatientAnalytics:
    if sexo not in (None, *SEXES, SIN_INFORMAR):
        raise _invalid("El sexo debe ser MASCULINO, FEMENINO o SIN_INFORMAR.")
    cuts = edadCortes if isinstance(edadCortes, list) else parseCuts(edadCortes)
    buckets = ageBuckets(cuts)
    codes = [label for label, _, _ in buckets]
    if edad not in (None, SIN_INFORMAR, *codes):
        raise _invalid("El rango de edad no existe con los cortes elegidos.")
    if segmentar not in SEGMENTS:
        raise _invalid("La segmentación no es válida.")
    if edadBase not in ("ACTUAL", "MEDICION"):
        raise _invalid("La edad se toma ACTUAL o al momento de la MEDICION.")
    if alimentacion not in (None, *FOODS):
        raise _invalid("La alimentación debe ser AYUNO, POSTPRANDIAL o NO_INFORMADA.")
    if modo not in (None, *MODES):
        raise _invalid("El modo de medición no es válido.")
    if origen not in ("TODOS", "EXPERIMENTAL", "DEMO"):
        raise _invalid("El origen debe ser TODOS, EXPERIMENTAL o DEMO.")
    if estado not in (*STATES, "TODOS"):
        raise _invalid("El estado de la medición no es válido.")
    if calidad not in (None, "CON_DATO", SIN_INFORMAR):
        raise _invalid("La calidad de señal debe ser CON_DATO o SIN_INFORMAR.")
    if variable not in VARIABLES:
        raise _invalid("La variable a analizar no es válida.")
    if granularidad not in ("dia", "semana", "mes"):
        raise _invalid("La granularidad debe ser dia, semana o mes.")
    if compararMatriz and not (idPerfilMedicion is not None and variable in ("glucosaDispositivo", "glucosaEstimada")):
        raise _invalid("La comparación con la matriz está disponible solo para la glucosa de un paciente seleccionado.")
    start, end, period = _period(dias, desde, hasta)
    membership = _requireOperator(db, actor, idInstitucion)
    now = nowForDb()

    # --- Alcance: pacientes ACTIVOS a cargo del operador hoy (o el paciente elegido, con su propia comprobación) -------------------
    if idPerfilMedicion is not None:
        measurements.requireClinicalAccess(db, actor, idInstitucion, idPerfilMedicion, "ANALISIS")  # 403/404 + auditoría del intento
    rows = db.execute(patients._patientsOf(idInstitucion).where(
        patients._IS_ACTIVE, MeasurementProfile.idInstitucionUsuarioResponsable == membership.relation.idInstitucionUsuario)).all()
    profiles = {row[0].idPerfilMedicion: row[0] for row in rows}
    if idPerfilMedicion is not None and idPerfilMedicion not in profiles:
        raise AuthError("PACIENTE_NO_ENCONTRADO", patients.PATIENT_NOT_FOUND)  # de baja o fuera del alcance vigente

    def currentAge(profile: MeasurementProfile) -> int | None:
        return calculateAge(profile.fechaNacimiento, now.date()) if profile.fechaNacimiento else profile.edadDeclarada

    inScope: dict[uuid.UUID, MeasurementProfile] = {}
    for profileId, profile in profiles.items():
        if idPerfilMedicion is not None and profileId != idPerfilMedicion:
            continue
        if sexo is not None and (profile.sexoModelo or SIN_INFORMAR) != sexo:
            continue
        if edad is not None and edadBase == "ACTUAL" and _ageRange(currentAge(profile), buckets) != edad:
            continue
        inScope[profileId] = profile

    # --- Mediciones del alcance con los filtros activos --------------------------------------------------------------------------
    conditions = [Measurement.fechaHoraInicio >= start]
    if end is not None:
        conditions.append(Measurement.fechaHoraInicio < end)
    if estado != "TODOS":
        conditions.append(Measurement.estadoMedicion == estado)
    if modo is not None:
        conditions.append(Measurement.modoMedicion == modo)
    if alimentacion is not None:
        conditions.append(Measurement.condicionComida == alimentacion)
    if calidadMinima is not None:
        conditions.append(Measurement.calidadSenal >= calidadMinima)
    if calidad == "CON_DATO":
        conditions.append(Measurement.calidadSenal.is_not(None))
    elif calidad == SIN_INFORMAR:
        conditions.append(Measurement.calidadSenal.is_(None))
    if edad is not None and edadBase == "MEDICION":
        if edad == SIN_INFORMAR:
            conditions.append(Measurement.edadAlMomento.is_(None))
        else:
            _, low, high = next(b for b in buckets if b[0] == edad)
            conditions.append(Measurement.edadAlMomento >= low)
            if high is not None:
                conditions.append(Measurement.edadAlMomento <= high)
    scopeIds = list(inScope)
    originCondition = {"EXPERIMENTAL": [NOT_DEMO, not_(NO_RESULT)], "DEMO": [Measurement.origenGlucosa == ORIGEN_DEMO]}.get(origen, [])
    data = []
    for index in range(0, len(scopeIds), IN_CHUNK):  # por tandas: el IN con miles de pacientes excede el tope de parámetros de SQL Server
        chunk = scopeIds[index:index + IN_CHUNK]
        data.extend(db.execute(select(*_COLUMNS).where(Measurement.idPerfilMedicion.in_(chunk), *conditions, *originCondition)
                               .order_by(Measurement.fechaHoraInicio.desc()).limit(MAX_ROWS + 1)).all())
    data.sort(key=lambda r: r.fechaHoraInicio)
    truncated = len(data) > MAX_ROWS
    data = data[-MAX_ROWS:]  # las más recientes del período

    withMeasurements = {row.idPerfilMedicion for row in data}
    completed = [row for row in data if row.estadoMedicion == "COMPLETADA"]
    noResult = [row for row in data if _noResult(row)]
    resolved = [row for row in data if not _noResult(row)]  # experimentales + DEMO: base de los desgloses por origen y por modo

    # Totales por origen con los MISMOS filtros salvo el origen: así un resultado vacío se explica en vez de parecer que los registros desaparecieron.
    if origen == "TODOS" and not truncated:
        originTotals = OriginTotals(experimentales=sum(1 for r in resolved if _group(r) == "EXPERIMENTAL"), demo=sum(1 for r in resolved if _group(r) == "DEMO"),
                                    sinResultado=len(noResult))
    else:
        counts = {"experimentales": 0, "demo": 0, "sinResultado": 0}
        for index in range(0, len(scopeIds), IN_CHUNK):
            chunk = scopeIds[index:index + IN_CHUNK]
            for key, flag in (("experimentales", and_(NOT_DEMO, not_(NO_RESULT))), ("demo", Measurement.origenGlucosa == ORIGEN_DEMO), ("sinResultado", NO_RESULT)):
                counts[key] += db.scalar(select(func.count()).select_from(Measurement).where(Measurement.idPerfilMedicion.in_(chunk), *conditions, flag)) or 0
        originTotals = OriginTotals(**counts)

    # --- KPIs ---------------------------------------------------------------------------------------------------------------------
    byMode = Counter(row.modoMedicion for row in resolved)
    missing = [
        Faltante(campo="spo2", sinDato=sum(1 for r in completed if r.spo2 is None), sobre=len(completed)),
        Faltante(campo="frecuenciaCardiaca", sinDato=sum(1 for r in completed if r.frecuenciaCardiaca is None), sobre=len(completed)),
        Faltante(campo="glucosa", sinDato=sum(1 for r in completed if r.glucosaDispositivo is None and r.glucosaEstimada is None), sobre=len(completed)),
        Faltante(campo="calidadSenal", sinDato=sum(1 for r in completed if r.calidadSenal is None), sobre=len(completed)),
        Faltante(campo="alimentacion", sinDato=sum(1 for r in completed if r.condicionComida == "NO_INFORMADA"), sobre=len(completed)),
        Faltante(campo="edadAlMomento", sinDato=sum(1 for r in completed if r.edadAlMomento is None), sobre=len(completed)),
    ]
    kpis = AnalyticsKpis(
        pacientesEnAlcance=len(inScope), pacientesConMediciones=len(withMeasurements), totalMediciones=len(data), completadas=len(completed),
        experimentales=sum(1 for r in resolved if _group(r) == "EXPERIMENTAL"), demo=sum(1 for r in resolved if _group(r) == "DEMO"),
        sinResultado=len(noResult), porModo={mode: byMode.get(mode, 0) for mode in MODES},
        conSenalValida=sum(1 for r in completed if r.lecturasEstabilizadas is not None), faltantes=missing)

    # --- Demografía de los PACIENTES del alcance (únicos; «Sin informar» cuenta como categoría) -----------------------------------
    sexCount, sexWith, ageCount, ageWith = Counter(), Counter(), Counter(), Counter()
    for profileId, profile in inScope.items():
        sexKey = profile.sexoModelo or SIN_INFORMAR
        ageKey = _ageRange(currentAge(profile), buckets)
        sexCount[sexKey] += 1
        ageCount[ageKey] += 1
        if profileId in withMeasurements:
            sexWith[sexKey] += 1
            ageWith[ageKey] += 1
    sexes = [Bucket(categoria=c, pacientes=sexCount.get(c, 0), conMediciones=sexWith.get(c, 0)) for c in (*SEXES, SIN_INFORMAR)]
    ages = [Bucket(categoria=c, pacientes=ageCount.get(c, 0), conMediciones=ageWith.get(c, 0)) for c in (*codes, SIN_INFORMAR)]

    foods = Counter(row.condicionComida for row in data)

    # --- Mediciones por modo y origen; evolución de la cantidad ------------------------------------------------------------------
    modeOrigin = [ModeOrigin(modo=mode, origen=group, mediciones=sum(1 for r in resolved if r.modoMedicion == mode and _group(r) == group))
                  for mode in MODES for group in ("EXPERIMENTAL", "DEMO") if origen in ("TODOS", group)]
    counts: dict[date, list[int]] = defaultdict(lambda: [0, 0])
    for row in resolved:
        counts[_bucketStart(row.fechaHoraInicio, granularidad)][0 if _group(row) == "EXPERIMENTAL" else 1] += 1
    evolution = [CountPoint(periodo=day, experimentales=pair[0], demo=pair[1]) for day, pair in sorted(counts.items())]

    # --- Variable elegida: series SEPARADAS por origen; promedio solo con observaciones que tienen el dato -------------------------
    column, unit = VARIABLES[variable]
    attr = column.key
    series: list[VariableSeries] = []
    for group in ("EXPERIMENTAL", "DEMO"):
        if origen not in ("TODOS", group):
            continue
        observed = [(r.fechaHoraInicio, float(getattr(r, attr))) for r in data
                    if _group(r) == group and r.estadoMedicion == "COMPLETADA" and getattr(r, attr) is not None]  # solo completadas con ESE dato
        perBucket: dict[date, list[float]] = defaultdict(list)
        for moment, value in observed:
            perBucket[_bucketStart(moment, granularidad)].append(value)
        values = [value for _, value in observed]
        series.append(VariableSeries(
            origen=group,
            resumen=VariableStat(n=len(values), promedio=round(sum(values) / len(values), 2) if values else None,
                                 minimo=min(values) if values else None, maximo=max(values) if values else None),
            puntos=[VariablePoint(periodo=day, n=len(vals), promedio=round(sum(vals) / len(vals), 2), minimo=min(vals), maximo=max(vals))
                    for day, vals in sorted(perBucket.items())]))

    # --- Calidad de señal: solo lo registrado; sin umbrales inventados -----------------------------------------------------------
    quality = [float(r.calidadSenal) for r in completed if r.calidadSenal is not None]
    ranges: list[QualityRange] = []
    if quality:
        low, high = min(quality), max(quality)
        parts = 1 if low == high else 4
        width = (high - low) / parts if parts > 1 else 0
        for index in range(parts):
            a = low + index * width
            b = high if index == parts - 1 else low + (index + 1) * width
            inside = sum(1 for q in quality if (a <= q <= b if index == parts - 1 or parts == 1 else a <= q < b))
            ranges.append(QualityRange(desde=round(a, 3), hasta=round(b, 3), mediciones=inside))
    readings: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for r in completed:
        if r.lecturasEstabilizadas is not None:
            readings[int(r.lecturasEstabilizadas)][0 if _group(r) == "EXPERIMENTAL" else 1] += 1
    qualityBlock = QualityBlock(
        conValor=len(quality), sinInformar=len(completed) - len(quality), rangos=ranges, conLecturas=sum(sum(pair) for pair in readings.values()),
        lecturas=[ReadingsBin(lecturas=count, experimentales=pair[0], demo=pair[1]) for count, pair in sorted(readings.items())])

    # --- Segmentación: filas por categoría Y origen (DEMO nunca comparte fila con lo experimental) --------------------------------
    segments: list[SegmentRow] = []
    if segmentar != "NINGUNA" and data:
        deviceNames: dict = {}
        matrixNames: dict = {}
        if segmentar == "DISPOSITIVO":
            ids = {r.idDispositivo for r in data}
            deviceNames = {d.idDispositivo: (d.nombre or d.codigoDispositivo) for d in db.scalars(select(Device).where(Device.idDispositivo.in_(ids))).all()}
        elif segmentar == "MATRIZ":
            ids = {r.idMatriz for r in data if r.idMatriz}
            matrixNames = {m.idMatriz: f"{m.nombre}, versión {m.version}" for m in db.scalars(select(Matrix).where(Matrix.idMatriz.in_(ids))).all()} if ids else {}

        def segmentKey(row) -> str:
            if segmentar == "SEXO":
                return row.sexoModelo or inScope[row.idPerfilMedicion].sexoModelo or SIN_INFORMAR
            if segmentar == "EDAD":
                return _ageRange(row.edadAlMomento if edadBase == "MEDICION" else currentAge(inScope[row.idPerfilMedicion]), buckets)
            if segmentar == "ALIMENTACION":
                return SIN_INFORMAR if row.condicionComida == "NO_INFORMADA" else row.condicionComida
            if segmentar == "MODO":
                return row.modoMedicion
            if segmentar == "ORIGEN":
                return _group(row)
            if segmentar == "DISPOSITIVO":
                return deviceNames.get(row.idDispositivo, SIN_INFORMAR)
            return matrixNames.get(row.idMatriz, SIN_INFORMAR) if row.idMatriz else SIN_INFORMAR

        grouped: dict[tuple[str, str], list] = defaultdict(list)
        for row in resolved:
            grouped[(segmentKey(row), _group(row))].append(row)
        base = {"SEXO": SEXES, "EDAD": codes, "ALIMENTACION": ("AYUNO", "POSTPRANDIAL")}.get(segmentar, ())
        order = {**{c: i for i, c in enumerate(base)}, SIN_INFORMAR: 98}
        for (category, group), items in sorted(grouped.items(), key=lambda kv: (order.get(kv[0][0], 50), kv[0][0], kv[0][1])):
            stat = _stat([float(getattr(r, attr)) for r in items if r.estadoMedicion == "COMPLETADA" and getattr(r, attr) is not None])
            segments.append(SegmentRow(categoria=category, origen=group, mediciones=len(items), n=stat.n, promedio=stat.promedio,
                                       minimo=stat.minimo, maximo=stat.maximo))

    # --- Tabla de pacientes (paginada) -------------------------------------------------------------------------------------------
    perPatient: dict[uuid.UUID, list] = defaultdict(list)
    for row in data:  # el detalle de un paciente conserva todas sus mediciones; los contadores por origen usan solo las «con resultado»
        perPatient[row.idPerfilMedicion].append(row)
    tableRows = []
    for profileId, profile in inScope.items():
        own = perPatient.get(profileId, [])
        last = own[-1] if own else None
        allowed = transfers.canSeeIdentity(membership, profile)
        tableRows.append(PatientRow(
            idPerfilMedicion=profileId, identificadorPseudonimo=profile.identificadorPseudonimo,
            nombre=profile.nombre if allowed else None, apellido=profile.apellido if allowed else None,
            edad=currentAge(profile), sexoModelo=profile.sexoModelo,
            medicionesExperimentales=sum(1 for r in own if not _noResult(r) and _group(r) == "EXPERIMENTAL"), medicionesDemo=sum(1 for r in own if _group(r) == "DEMO"),
            ultima=None if last is None else LastValues(
                fecha=last.fechaHoraInicio, modo=last.modoMedicion, origen=_group(last), spo2=_num(last.spo2),
                frecuenciaCardiaca=last.frecuenciaCardiaca,
                glucosa=_num(last.glucosaDispositivo if last.glucosaDispositivo is not None else last.glucosaEstimada))))
    tableRows.sort(key=lambda item: (item.ultima is None, -(item.ultima.fecha.timestamp()) if item.ultima else 0, item.identificadorPseudonimo or ""))
    size = max(1, min(tamanioPagina, MAX_PAGE_SIZE))
    page = max(1, pagina)
    table = PatientTable(items=tableRows[(page - 1) * size: page * size], total=len(tableRows), pagina=page, tamanioPagina=size)

    # --- Detalle de UN paciente: sus puntos reales (sin agregar) y, si se pide, la comparación con la matriz ----------------------
    detail = None
    if idPerfilMedicion is not None:
        profile = inScope.get(idPerfilMedicion) or profiles[idPerfilMedicion]
        own = perPatient.get(idPerfilMedicion, [])
        cut = len(own) > MAX_DETAIL_POINTS
        own = own[-MAX_DETAIL_POINTS:]
        references: dict[uuid.UUID, ReferenceInfo] = {}
        matrixSummary = None
        if compararMatriz:  # solo glucosa experimental COMPLETADA con valor; DEMO (sintético) nunca se compara con la matriz
            candidates = [r for r in own if r.modoMedicion == "GLUCOSA_EXPERIMENTAL" and r.estadoMedicion == "COMPLETADA" and _group(r) == "EXPERIMENTAL"
                          and (r.glucosaDispositivo is not None or r.glucosaEstimada is not None)]
            ids = [r.idMedicion for r in candidates[-MATRIX_LIMIT:]]
            for entity in (db.scalars(select(Measurement).where(Measurement.idMedicion.in_(ids))).all() if ids else []):
                built = glucoseReference.build(db, entity)
                selected = next((g for g in built.grupos if g.reglaSeleccionada is not None), None)
                references[entity.idMedicion] = ReferenceInfo(
                    estado=built.estado, matriz=None if built.matriz is None else f"{built.matriz.nombre}, versión {built.matriz.version}",
                    minimo=selected.reglaSeleccionada.glucosaMinReferencia if selected else None,
                    maximo=selected.reglaSeleccionada.glucosaMaxReferencia if selected else None,
                    posicion=selected.posicion if selected else None,
                    motivo=None if selected else next((g.motivoSinSeleccion for g in built.grupos if g.motivoSinSeleccion), None) or "Sin matriz aplicable a esta medición.")  # nunca se inventa una referencia
            tally = Counter(ref.posicion for ref in references.values())
            matrixSummary = MatrixSummary(comparadas=len(references), dentro=tally["DENTRO"], porDebajo=tally["POR_DEBAJO"], porEncima=tally["POR_ENCIMA"],
                                          sinReferencia=tally[None], limitado=len(candidates) > MATRIX_LIMIT)
        identity = transfers.canSeeIdentity(membership, profile)
        detail = PatientDetail(
            idPerfilMedicion=idPerfilMedicion, identificadorPseudonimo=profile.identificadorPseudonimo,
            nombre=profile.nombre if identity else None, apellido=profile.apellido if identity else None,
            fechaNacimiento=profile.fechaNacimiento if identity else None, edadActual=currentAge(profile), sexoModelo=profile.sexoModelo,
            puntosTruncados=cut, resumenMatriz=matrixSummary,
            puntos=[MeasurementPoint(
                idMedicion=r.idMedicion, fecha=r.fechaHoraInicio, modo=r.modoMedicion, origen=_group(r), estado=r.estadoMedicion,
                alimentacion=r.condicionComida, edadAlMomento=r.edadAlMomento, calidadSenal=_num(r.calidadSenal), spo2=_num(r.spo2),
                frecuenciaCardiaca=r.frecuenciaCardiaca, glucosaDispositivo=_num(r.glucosaDispositivo), glucosaEstimada=_num(r.glucosaEstimada),
                indiceOptico=_num(r.indiceOptico), referencia=references.get(r.idMedicion)) for r in own])

    return PatientAnalytics(
        periodo=period,
        filtros=AppliedFilters(idPerfilMedicion=idPerfilMedicion, sexo=sexo, edad=edad, edadBase=edadBase, edadCortes=cuts, alimentacion=alimentacion,
                               modo=modo, origen=origen, estado=estado, calidad=calidad, calidadMinima=calidadMinima, variable=variable,
                               granularidad=granularidad, segmentar=segmentar, compararMatriz=compararMatriz),
        kpis=kpis, sexo=sexes, edades=ages, rangosEdad=[*codes, SIN_INFORMAR], segmentacion=segments, porModoOrigen=modeOrigin,
        alimentacion=[CategoryCount(categoria=c, mediciones=foods.get(c, 0)) for c in FOODS],
        evolucion=evolution, variable=VariableBlock(variable=variable, unidad=unit, series=series), calidad=qualityBlock,
        pacientes=table, paciente=detail, origenes=originTotals, truncado=truncated)
