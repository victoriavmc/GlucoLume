# Dashboard - Indicadores por ámbito, siempre calculados sobre Medicion (sin copias ni registros duplicados)
#
#   - Personal:      solo el perfil propio (cuenta individual).
#   - Familiar:      solo lo que cada integrante autorizó compartir; los permisos se evalúan en cada consulta.
#   - Institucional: general (propietario y moderador), por operador y por paciente, siempre acotado a la institución.
#
# Operador de una medición: el que la inició (Auditoria INICIAR_MEDICION, idRelacionado = vínculo operador). Es una
# trazabilidad histórica: una transferencia posterior no se la atribuye al nuevo responsable. «Pacientes asignados» es
# otra cosa: el responsable ACTUAL del perfil.
# Las estadísticas usan solo mediciones COMPLETADA; sin datos los valores son null, nunca cero. Los datos DEMO del
# dispositivo (valor sintético de prueba) nunca entran en ningún indicador (NOT_DEMO).

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, not_, select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.device import Device
from app.models.group import Group  # noqa: F401 - registro del modelo
from app.models.groupUser import GroupUser
from app.models.institutionUser import InstitutionUser
from app.models.measurement import NOT_DEMO, ORIGEN_DEMO, Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.profileTransfer import ProfileTransfer
from app.models.user import User
from app.schemas.dashboard import (
    AdminDay,
    AdminFilters,
    AdminFood,
    AdminPatientBand,
    AdminKpis,
    AdminMode,
    AdminOperator,
    AdminState,
    AdminStats,
    AssignedPatient,
    AvailableDevice,
    DayCount,
    GroupActivity,
    GroupAggregate,
    GroupDashboard,
    HealthAggregates,
    HealthDay,
    HealthGroup,
    HealthPoint,
    InstitutionDashboard,
    LastValue,
    MeasurementSummary,
    DemographicRow,
    OperatorCharts,
    OperatorDashboard,
    OperatorDay,
    OperatorLoad,
    OperatorModeCount,
    OperatorQuality,
    PatientDashboard,
    PatientProfileInfo,
    PatientTransferRow,
    PerformedMeasurement,
    PersonalDashboard,
    PersonRef,
    Period,
    QualityBin,
    ReadingsBin,
    TransferCounters,
)
from app.services import group as groups
from app.services import institution as institutions
from app.services import institutionPatients as patients
from app.services import measurementRetention, patientAccess, reassignments
from app.services import measurement as measurements
from app.services import profileTransfers as transfers
from app.services.audit import personName, registerEvent
from app.services.measurementProfile import TIPO_CONSUMIDOR_FINAL, calculateAge, getConsumerProfile
from app.services.measurementVisibility import hiddenCondition
from app.utils.timeZone import nowForDb

COMPLETADA = measurements.COMPLETADA
RECENT = 10
ACTIVITY_PER_MEMBER = 2  # cupo de actividades recientes por integrante: ninguna persona ocupa toda la lista
MIN_GROUP_PARTICIPANTS = 2
MAX_LISTED = 50


# --- Auxiliares ------------------------------------------------------------------------------------------------


def _range(dias: int, desde: date | None, hasta: date | None) -> tuple[datetime, datetime | None, Period]:
    measurements._checkPeriod(dias, desde, hasta)
    if desde or hasta:
        start = datetime.combine(desde, datetime.min.time()) if desde else datetime.min
        end = datetime.combine(hasta + timedelta(days=1), datetime.min.time()) if hasta else None
        return start, end, Period(dias=None, desde=desde, hasta=hasta)
    return nowForDb() - timedelta(days=dias), None, Period(dias=dias, desde=None, hasta=None)


def _inPeriod(column, start: datetime, end: datetime | None):
    condition = [column >= start]
    if end is not None:
        condition.append(column < end)
    return condition


def _last(db: Session, scope, field) -> LastValue | None:
    row = db.execute(
        select(Measurement.fechaHoraInicio, field).where(scope, Measurement.estadoMedicion == COMPLETADA, field.is_not(None), NOT_DEMO)
        .order_by(Measurement.fechaHoraInicio.desc()).limit(1)).first()
    return LastValue(valor=float(row[1]), fecha=row[0]) if row else None


def _summary(db: Session, profileIds, start: datetime, end: datetime | None, hideExpired: bool = False) -> MeasurementSummary:
    """`profileIds`: lista o subconsulta de idPerfilMedicion."""
    scope = and_(Measurement.idPerfilMedicion.in_(profileIds), NOT_DEMO)
    if hideExpired:
        scope = and_(scope, not_(hiddenCondition(nowForDb())))
    completed = [scope, Measurement.estadoMedicion == COMPLETADA]
    return MeasurementSummary(
        total=db.scalar(select(func.count()).select_from(Measurement).where(scope)) or 0,
        completadas=db.scalar(select(func.count()).select_from(Measurement).where(*completed)) or 0,
        enPeriodo=db.scalar(select(func.count()).select_from(Measurement).where(
            *completed, *_inPeriod(Measurement.fechaHoraInicio, start, end))) or 0,
        ultimaMedicion=db.scalar(select(func.max(Measurement.fechaHoraInicio)).where(*completed)),
        ultimaGlucosa=_last(db, scope, Measurement.glucosaEstimada),
        ultimaSpo2=_last(db, scope, Measurement.spo2),
        ultimaFrecuencia=_last(db, scope, Measurement.frecuenciaCardiaca),
    )


def _performers(db: Session, measurementIds: list[uuid.UUID]) -> dict[uuid.UUID, tuple[uuid.UUID, str | None]]:
    """Operador que inició cada medición (vínculo y nombre histórico), en dos consultas para toda la lista."""
    if not measurementIds:
        return {}
    traced = dict(db.execute(
        select(Audit.idRegistro, Audit.idRelacionado).where(
            Audit.tablaAfectada == "Medicion", Audit.accion == "INICIAR_MEDICION", Audit.idRegistro.in_(measurementIds),
            Audit.idRelacionado.is_not(None))).all())
    return {mid: (rel, _names(db, list(set(traced.values()))).get(rel)) for mid, rel in traced.items()}


def _names(db: Session, relationIds: list[uuid.UUID]) -> dict[uuid.UUID, str | None]:
    if not relationIds:
        return {}
    rows = db.execute(select(InstitutionUser, User).outerjoin(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
                      .where(InstitutionUser.idInstitucionUsuario.in_(relationIds))).all()
    return {rel.idInstitucionUsuario: personName(rel, user) for rel, user in rows}


def _performedRows(db: Session, rows, pseudonyms: dict, withOperator: bool) -> list[PerformedMeasurement]:
    codes = {d.idDispositivo: d.codigoDispositivo for d in db.scalars(
        select(Device).where(Device.idDispositivo.in_({r.idDispositivo for r in rows}))).all()} if rows else {}
    performers = _performers(db, [r.idMedicion for r in rows]) if withOperator else {}
    items = []
    for r in rows:
        trace = performers.get(r.idMedicion)
        items.append(PerformedMeasurement(
            idMedicion=r.idMedicion, idPerfilMedicion=r.idPerfilMedicion, paciente=pseudonyms.get(r.idPerfilMedicion),
            fechaHoraInicio=r.fechaHoraInicio, modoMedicion=r.modoMedicion, estadoMedicion=r.estadoMedicion,
            glucosaEstimada=float(r.glucosaEstimada) if r.glucosaEstimada is not None else None,
            spo2=float(r.spo2) if r.spo2 is not None else None, frecuenciaCardiaca=r.frecuenciaCardiaca,
            dispositivo=codes.get(r.idDispositivo), esDemo=r.origenGlucosa == ORIGEN_DEMO,
            operador=(trace[1] or "Operador no disponible") if trace else None))
    return items


def _pseudonyms(db: Session, ids) -> dict[uuid.UUID, str | None]:
    ids = list(set(ids))
    if not ids:
        return {}
    return dict(db.execute(select(MeasurementProfile.idPerfilMedicion, MeasurementProfile.identificadorPseudonimo)
                           .where(MeasurementProfile.idPerfilMedicion.in_(ids))).all())


# --- Personal --------------------------------------------------------------------------------------------------


def personalDashboard(db: Session, actor: User, dias: int = 30, desde: date | None = None,
                      hasta: date | None = None) -> PersonalDashboard:
    start, end, period = _range(dias, desde, hasta)
    own = measurements.getOwnProfile(db, actor) if actor.tipoCuenta == TIPO_CONSUMIDOR_FINAL else None  # lo crea si falta
    if own is None or not own.perfilDisponible:
        return PersonalDashboard(perfilDisponible=False, datosFaltantes=own.datosFaltantes if own else [], periodo=period,
                                 resumen=None, estadisticas=None, recientes=[])
    profile = getConsumerProfile(db, actor)
    # Las mediciones guardadas se listan TODAS (también las DEMO, identificadas); solo los indicadores las excluyen.
    recent = measurements._history(db, profile.idPerfilMedicion, desde=None, hasta=None, modo=None, estado=COMPLETADA,
                                   orden="desc", pagina=1, tamanioPagina=RECENT, origen=None)
    demo = db.scalar(select(func.count()).select_from(Measurement).where(
        Measurement.idPerfilMedicion == profile.idPerfilMedicion, Measurement.estadoMedicion == COMPLETADA,
        Measurement.origenGlucosa == ORIGEN_DEMO)) or 0
    return PersonalDashboard(
        perfilDisponible=True, periodo=period, resumen=_summary(db, [profile.idPerfilMedicion], start, end, hideExpired=True),
        estadisticas=measurements.buildStatistics(db, profile.idPerfilMedicion, dias, desde=desde, hasta=hasta),
        recientes=recent.items, ultimaGuardada=recent.items[0] if recent.items else None, pruebasDemo=demo)


# --- Institucional: general -------------------------------------------------------------------------------------


def _institutionProfileIds(idInstitucion: uuid.UUID):
    return patients._patientsOf(idInstitucion).with_only_columns(
        MeasurementProfile.idPerfilMedicion, maintain_column_froms=True)


NO_RESULT = and_(Measurement.estadoMedicion != COMPLETADA, Measurement.origenGlucosa.is_(None))
ADMIN_STATES = ("PENDIENTE", "ADQUIRIENDO", "PROCESANDO", "COMPLETADA", "INVALIDA", "CANCELADA")
MAX_ADMIN_ROWS = 50000


def _counts(rows) -> dict:
    """Cantidades administrativas de filas (estado, origenGlucosa): ver AdminCounts."""
    states = [r[0] for r in rows]
    demo = sum(1 for r in rows if r[1] == ORIGEN_DEMO)
    noResult = sum(1 for r in rows if r[0] != COMPLETADA and r[1] is None)
    return dict(
        total=len(rows), completadas=states.count(COMPLETADA), canceladas=states.count("CANCELADA"), invalidas=states.count("INVALIDA"),
        enCurso=sum(1 for s in states if s in ("PENDIENTE", "ADQUIRIENDO", "PROCESANDO")), demo=demo, sinResultado=noResult,
        experimentales=len(rows) - demo - noResult)


PATIENT_BANDS = ((1, 1), (2, 3), (4, 5), (6, None))


def _patientBands(perPatient: dict, active: int, db: Session, profiles) -> list[AdminPatientBand]:
    """Pacientes por tramo de cantidad de mediciones (con los filtros aplicados) y los activos que no tienen ninguna. Solo cantidades."""
    bands = [AdminPatientBand(desde=low, hasta=high, pacientes=sum(1 for n in perPatient.values() if n >= low and (high is None or n <= high)))
             for low, high in PATIENT_BANDS]
    withAny = set(perPatient)
    activeIds = set(db.scalars(profiles.where(patients._IS_ACTIVE)))
    return [AdminPatientBand(desde=0, hasta=0, pacientes=len(activeIds - withAny)), *bands]


def _adminStats(db: Session, idInstitucion: uuid.UUID, profileIds, start: datetime, end: datetime | None, operador: uuid.UUID | None,
                modo: str | None, estado: str | None, origen: str) -> AdminStats:
    """Estadísticas ADMINISTRATIVAS (actividad, no resultados de salud) de la institución, desde el primer registro: no se aplica el mínimo de
    pacientes porque solo son cantidades (sin SpO₂, frecuencia cardíaca, glucosa, sexo ni edad). Incluyen DEMO, todos los estados y las
    mediciones de pacientes ya anonimizados (cohorte). Nunca devuelven valores de salud ni identifican pacientes: un operador se
    identifica solo como autor de cantidades de trabajo."""
    if modo not in (None, "OXIMETRIA", "GLUCOSA_EXPERIMENTAL"):
        raise AuthError("DATOS_INVALIDOS", "El modo de medición no es válido.")
    if estado is not None and estado not in ADMIN_STATES:
        raise AuthError("DATOS_INVALIDOS", "El estado de la medición no es válido.")
    if origen not in ("TODOS", "EXPERIMENTAL", "DEMO"):
        raise AuthError("DATOS_INVALIDOS", "El origen de los datos no es válido.")
    staff = db.execute(select(InstitutionUser, User).outerjoin(User, User.idUsuario == InstitutionUser.idUsuarioInvitado).where(
        InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.rolInstitucion.in_((institutions.ROL_OPERADOR, institutions.ROL_MODERADOR)))).all()
    operators = {rel.idInstitucionUsuario: (rel, user) for rel, user in staff if rel.rolInstitucion == institutions.ROL_OPERADOR}
    if operador is not None and operador not in operators:
        raise AuthError("MIEMBRO_NO_ENCONTRADO", "No encontramos a ese operador en la institución.")

    conditions = [Measurement.idPerfilMedicion.in_(profileIds), *_inPeriod(Measurement.fechaHoraInicio, start, end)]
    if modo:
        conditions.append(Measurement.modoMedicion == modo)
    if estado:
        conditions.append(Measurement.estadoMedicion == estado)
    if origen == "EXPERIMENTAL":
        conditions += [NOT_DEMO, not_(NO_RESULT)]
    elif origen == "DEMO":
        conditions.append(Measurement.origenGlucosa == ORIGEN_DEMO)
    started = and_(Audit.tablaAfectada == "Medicion", Audit.accion == "INICIAR_MEDICION")
    if operador is not None:
        conditions.append(Measurement.idMedicion.in_(select(Audit.idRegistro).where(started, Audit.idRelacionado == operador)))
    rows = db.execute(select(Measurement.fechaHoraInicio, Measurement.estadoMedicion, Measurement.origenGlucosa, Measurement.modoMedicion,
                             Measurement.idPerfilMedicion, Measurement.condicionComida)
                      .where(*conditions).order_by(Measurement.fechaHoraInicio.desc()).limit(MAX_ADMIN_ROWS + 1)).all()
    truncated = len(rows) > MAX_ADMIN_ROWS
    rows = rows[:MAX_ADMIN_ROWS]
    authored = db.execute(select(Audit.idRelacionado, Measurement.estadoMedicion, Measurement.origenGlucosa).join(
        Measurement, Measurement.idMedicion == Audit.idRegistro).where(started, Audit.idRelacionado.is_not(None), *conditions)
        .limit(MAX_ADMIN_ROWS)).all()

    byDay: dict[date, list] = {}
    byMode: dict[str, list] = {"OXIMETRIA": [], "GLUCOSA_EXPERIMENTAL": []}
    byState: dict[str, list] = {state: [] for state in ADMIN_STATES}
    byFood: dict[str, int] = {}
    perPatient: dict[uuid.UUID, int] = {}  # cada medición cuenta: un paciente con tres en el día suma tres, no una
    for moment, state, origin, mode, patientId, food in rows:
        byFood[food] = byFood.get(food, 0) + 1
        perPatient[patientId] = perPatient.get(patientId, 0) + 1
        byDay.setdefault(moment.date(), []).append((state, origin))
        byMode.setdefault(mode, []).append((state, origin))
        byState.setdefault(state, []).append((state, origin))
    byOperator: dict[uuid.UUID, list] = {}
    for rel, state, origin in authored:
        byOperator.setdefault(rel, []).append((state, origin))

    profiles = _institutionProfileIds(idInstitucion)
    registered = db.scalar(select(func.count()).select_from(profiles.subquery())) or 0
    active = db.scalar(select(func.count()).select_from(profiles.where(patients._IS_ACTIVE).subquery())) or 0
    assigned = dict(db.execute(select(MeasurementProfile.idInstitucionUsuarioResponsable, func.count()).where(
        MeasurementProfile.idPerfilMedicion.in_(profiles.where(patients._IS_ACTIVE))).group_by(MeasurementProfile.idInstitucionUsuarioResponsable)).all())
    relations = {rel.idInstitucionUsuario: rel for rel, _ in staff}
    unassigned = sum(count for rel, count in assigned.items() if rel not in relations or relations[rel].estadoRelacion != institutions.RELACION_ACTIVO)

    # Transferencias de pacientes de esta institución; con el filtro de operador, las que envió o recibió.
    transferScope = [ProfileTransfer.idPerfilMedicion.in_(profiles)]
    if operador is not None:
        sent = select(Audit.idRegistro).where(Audit.tablaAfectada == "TransferenciaPerfil", Audit.accion == "SOLICITAR_TRANSFERENCIA_PERFIL", Audit.idRelacionado == operador)
        transferScope.append((ProfileTransfer.idOperadorDestino == operador) | ProfileTransfer.idTransferenciaPerfil.in_(sent))
    transferStates = dict(db.execute(select(ProfileTransfer.estado, func.count()).where(*transferScope).group_by(ProfileTransfer.estado)).all())
    devices = db.execute(select(Device.estado, func.count()).where(Device.idInstitucionAsignada == idInstitucion, Device.estado != "BAJA")
                         .group_by(Device.estado)).all()

    counts = _counts([(s, o) for _, s, o, _, _, _ in rows])
    people = []
    load = []
    for rel, (relation, user) in operators.items():
        name, surname = _staffName(relation, user)
        isActive = relation.estadoRelacion == institutions.RELACION_ACTIVO
        # Un operador desvinculado sigue en las estadísticas mientras tenga actividad en el período y los filtros elegidos (con su identificación
        # histórica permitida, o «Operador desvinculado»); sin actividad no es más que una fila de ceros y se omite. Nada se borra: si el período
        # cambia, su actividad se recalcula. Elegirlo explícitamente (filtro de operador) siempre lo muestra.
        item = AdminOperator(idInstitucionUsuario=rel, nombre=name, apellido=surname, activo=isActive, pacientesAsignados=assigned.get(rel, 0),
                             **_counts(byOperator.get(rel, [])))
        if isActive or item.total > 0 or rel == operador:
            people.append(PersonRef(idInstitucionUsuario=rel, nombre=name, apellido=surname, rolInstitucion=institutions.ROL_OPERADOR, activo=isActive))
        if operador is not None and rel != operador:
            continue
        if isActive or item.total > 0 or rel == operador:
            load.append(item)
    load.sort(key=lambda item: (-item.total, item.apellido or "", item.nombre or ""))
    people.sort(key=lambda item: (not item.activo, item.apellido or "", item.nombre or ""))
    return AdminStats(
        filtros=AdminFilters(operador=operador, modo=modo, estado=estado, origen=origen), operadores=people,
        kpis=AdminKpis(
            **counts, pacientesRegistrados=registered, pacientesActivos=active, pacientesConMediciones=len(perPatient), pacientesSinOperador=unassigned,
            pacientesAsignadosOperador=assigned.get(operador, 0) if operador is not None else None,
            operadoresActivos=sum(1 for rel, _ in operators.values() if rel.estadoRelacion == institutions.RELACION_ACTIVO),
            moderadoresActivos=sum(1 for rel, _ in staff if rel.rolInstitucion == institutions.ROL_MODERADOR and rel.estadoRelacion == institutions.RELACION_ACTIVO),
            transferenciasPendientes=transferStates.get("PENDIENTE", 0), transferenciasTotal=sum(transferStates.values()),
            dispositivosDisponibles=sum(n for state, n in devices if state == "OPERATIVO"), dispositivosRegistrados=sum(n for _, n in devices)),
        serie=[AdminDay(fecha=day, **{k: v for k, v in _counts(items).items() if k in ("completadas", "canceladas", "invalidas", "enCurso", "experimentales", "demo")})
               for day, items in sorted(byDay.items())],
        porModo=[AdminMode(modo=mode, **_counts(items)) for mode, items in byMode.items()],
        porEstado=[AdminState(estado=state, total=len(items), **{k: v for k, v in _counts(items).items() if k in ("experimentales", "demo", "sinResultado")})
                   for state, items in byState.items()],
        porAlimentacion=[AdminFood(condicion=food, total=total) for food, total in sorted(byFood.items(), key=lambda item: (-item[1], item[0]))],
        pacientesPorCantidad=_patientBands(perPatient, active, db, profiles),
        porOperador=load, truncado=truncated)


HEALTH_NOT_COMPLETED = ("Los resultados de salud se calculan solo con mediciones completadas: con el filtro de estado elegido no hay resultados "
                        "que promediar. Quitá el filtro de estado para verlos.")
HEALTH_BY_OPERATOR = ("Los resultados de salud experimentales no se desagregan por operador, porque un grupo tan chico permitiría reconstruir "
                      "resultados individuales. El conteo de mediciones por operador está en la actividad.")


MAX_HEALTH_POINTS = 1000


def _modeCounts(pairs) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row, _ in pairs:
        counts[row.modoMedicion] = counts.get(row.modoMedicion, 0) + 1
    return counts


def _foodCounts(pairs) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row, _ in pairs:
        counts[row.condicionComida] = counts.get(row.condicionComida, 0) + 1
    return counts


def _healthGroup(origin: str, rows, *, minDaily: int) -> HealthGroup:
    """Resumen de un solo origen sobre filas de Medicion (columnas de _healthAggregates). Cada valor sale de su campo registrado; lo que falta
    se cuenta como «sin informar» y nunca como cero."""
    def values(row) -> tuple:
        return (float(row.spo2) if row.spo2 is not None else None,
                float(row.frecuenciaCardiaca) if row.frecuenciaCardiaca is not None else None, measurements._evolutionGlucose(row))

    pairs = [(row, values(row)) for row in rows]
    column = lambda index: [v[index] for _, v in pairs if v[index] is not None]  # noqa: E731
    byDay: dict[date, list] = {}
    for row, value in pairs:
        byDay.setdefault(row.fechaHoraInicio.date(), []).append((row, value))
    def dayOf(day, items) -> HealthDay:
        glucose, spo2, rate = ([v[i] for _, v in items if v[i] is not None] for i in (2, 0, 1))
        return HealthDay(fecha=day, mediciones=len(items), glucosaPromedio=measurements._average(glucose), glucosaN=len(glucose),
                         spo2Promedio=measurements._average(spo2), spo2N=len(spo2), frecuenciaPromedio=measurements._average(rate), frecuenciaN=len(rate))

    # Todas las mediciones del día cuentan (un paciente puede medirse varias veces): no se deduplica por paciente y fecha.
    series = [dayOf(day, items) for day, items in sorted(byDay.items()) if len({r.idPerfilMedicion for r, _ in items}) >= minDaily]
    points = [] if origin != "DEMO" else [
        HealthPoint(fecha=row.fechaHoraInicio, glucosa=v[2], spo2=v[0], frecuenciaCardiaca=v[1])
        for row, v in sorted(pairs, key=lambda pair: pair[0].fechaHoraInicio)[-MAX_HEALTH_POINTS:]]
    return HealthGroup(
        origen=origin, estado="DISPONIBLE", mediciones=len(pairs), pacientes=len({r.idPerfilMedicion for r, _ in pairs}),
        spo2=measurements._summary(column(0)), frecuenciaCardiaca=measurements._summary(column(1)), glucosa=measurements._summary(column(2)),
        calidadSenal=measurements._summary([float(row.calidadSenal) for row, _ in pairs if row.calidadSenal is not None]),
        alimentacion=_foodCounts(pairs), porModo=_modeCounts(pairs), puntos=points,
        sinInformar={"spo2": len(pairs) - len(column(0)), "frecuenciaCardiaca": len(pairs) - len(column(1)), "glucosa": len(pairs) - len(column(2)),
                     "calidadSenal": sum(1 for row, _ in pairs if row.calidadSenal is None)},
        serieDiaria=series)


def _healthAggregates(db: Session, profileIds, start: datetime, end: datetime | None, operador: uuid.UUID | None, modo: str | None,
                      estado: str | None, origen: str) -> HealthAggregates:
    """Resultados de salud agregados de toda la institución, SEPARADOS por origen (experimental y DEMO nunca comparten promedio).
      - Período, modo y origen se aplican de verdad; el estado y el operador, cuando no se pueden aplicar, se informan en `motivo` (nunca en silencio).
      - DEMO: valores sintéticos, no describen a ninguna persona: se informan desde una sola medición, siempre identificados como simulados.
      - EXPERIMENTAL: datos de salud reales. Se exige un mínimo de pacientes distintos EN EL CONJUNTO FILTRADO (período + modo), porque ocultar nombre
        y documento no anonimiza: con pocos pacientes el promedio, el mínimo o el máximo son el valor de una persona. Con filtro de modo el
        complemento también debe ser 0 o alcanzar el mínimo (si no, restar un conjunto del otro revelaría al paciente de la diferencia). Sin
        desagregación por operador. Los resultados individuales siguen siendo del operador responsable (patientAccess).
    Los filtros inválidos ya los rechaza `_adminStats`."""
    minimum = patientAccess.MIN_AGGREGATE_PATIENTS
    base = [Measurement.idPerfilMedicion.in_(profileIds), Measurement.estadoMedicion == COMPLETADA, *_inPeriod(Measurement.fechaHoraInicio, start, end)]
    cols = (Measurement.idPerfilMedicion, Measurement.fechaHoraInicio, Measurement.spo2, Measurement.frecuenciaCardiaca,
            Measurement.glucosaEstimada, Measurement.glucosaDispositivo, Measurement.origenGlucosa, Measurement.calidadSenal, Measurement.condicionComida,
            Measurement.modoMedicion)
    notCompleted = estado is not None and estado != COMPLETADA

    def fetch(*conditions):
        return db.execute(select(*cols).where(*base, *conditions).limit(MAX_ADMIN_ROWS)).all()

    def distinct(rows) -> int:
        return len({r.idPerfilMedicion for r in rows})

    experimental = demo = None
    if origen in ("TODOS", "EXPERIMENTAL"):
        if notCompleted:
            experimental = HealthGroup(origen="EXPERIMENTAL", estado="NO_APLICA", motivo=HEALTH_NOT_COMPLETED)
        elif operador is not None:
            experimental = HealthGroup(origen="EXPERIMENTAL", estado="NO_APLICA", motivo=HEALTH_BY_OPERATOR)
        else:
            modeCondition = [Measurement.modoMedicion == modo] if modo else []
            rows = fetch(NOT_DEMO, *modeCondition)
            others = fetch(NOT_DEMO, Measurement.modoMedicion != modo) if modo else []
            if not rows:
                experimental = HealthGroup(origen="EXPERIMENTAL", estado="SIN_DATOS", motivo="No hay mediciones experimentales completadas con estos filtros.")
            elif distinct(rows) < minimum or (others and distinct(others) < minimum):
                experimental = HealthGroup(
                    origen="EXPERIMENTAL", estado="PROTEGIDO",
                    motivo=f"Los resultados experimentales se informan con al menos {minimum} pacientes distintos con mediciones en el conjunto elegido, "
                           "para que no identifiquen a una persona. Probá con un período más amplio o quitá el filtro de modo.")
            else:
                experimental = _healthGroup("EXPERIMENTAL", rows, minDaily=minimum)
    if origen in ("TODOS", "DEMO"):
        if notCompleted:
            demo = HealthGroup(origen="DEMO", estado="NO_APLICA", motivo=HEALTH_NOT_COMPLETED)
        else:
            conditions = [Measurement.origenGlucosa == ORIGEN_DEMO]
            if modo:
                conditions.append(Measurement.modoMedicion == modo)
            if operador is not None:
                conditions.append(Measurement.idMedicion.in_(select(Audit.idRegistro).where(
                    Audit.tablaAfectada == "Medicion", Audit.accion == "INICIAR_MEDICION", Audit.idRelacionado == operador)))
            rows = fetch(*conditions)
            demo = (_healthGroup("DEMO", rows, minDaily=0) if rows else
                    HealthGroup(origen="DEMO", estado="SIN_DATOS", motivo="No hay mediciones DEMO completadas con estos filtros."))
    return HealthAggregates(minimoPacientes=minimum, filtros=AdminFilters(operador=operador, modo=modo, estado=estado, origen=origen),
                            experimentales=experimental, demo=demo)


def institutionDashboard(db: Session, actor: User, idInstitucion: uuid.UUID, dias: int = 30, desde: date | None = None,
                         hasta: date | None = None, operador: uuid.UUID | None = None, modo: str | None = None,
                         estado: str | None = None, origen: str = "TODOS") -> InstitutionDashboard:
    """Propietario y moderador (CONSULTAR_EQUIPO). Agregados y seudonimizado: sin nombres ni identificadores de pacientes."""
    start, end, period = _range(dias, desde, hasta)
    institutions.requireMembership(db, actor, idInstitucion, institutions.P_EQUIPO)
    # Pacientes del período vigente MÁS la cohorte anónima (pacientes ya anonimizados): solo en estos agregados, nunca en un acceso individual.
    profileIds = measurementRetention.withCohort(db, idInstitucion, _institutionProfileIds(idInstitucion))
    scope = and_(Measurement.idPerfilMedicion.in_(profileIds), NOT_DEMO)
    now = nowForDb()
    count = lambda *conditions: db.scalar(select(func.count()).select_from(Measurement).where(scope, *conditions)) or 0  # noqa: E731
    states = dict(db.execute(select(Measurement.estadoMedicion, func.count()).where(scope).group_by(Measurement.estadoMedicion)).all())
    modes = dict(db.execute(select(Measurement.modoMedicion, func.count()).where(scope).group_by(Measurement.modoMedicion)).all())
    rows = db.execute(select(Measurement.fechaHoraInicio, Measurement.estadoMedicion).where(
        scope, *_inPeriod(Measurement.fechaHoraInicio, start, end))).all()
    byDay: dict[date, list[int]] = {}
    for moment, state in rows:
        bucket = byDay.setdefault(moment.date(), [0, 0])
        bucket[0] += 1
        bucket[1] += state == COMPLETADA
    devices = db.execute(select(Device.estado, func.count()).where(
        Device.idInstitucionAsignada == idInstitucion, Device.estado != "BAJA").group_by(Device.estado)).all()

    # Pacientes asignados por operador (responsable actual) y mediciones del período por quien las inició.
    assigned = dict(db.execute(select(MeasurementProfile.idInstitucionUsuarioResponsable, func.count()).where(
        MeasurementProfile.idPerfilMedicion.in_(_institutionProfileIds(idInstitucion).where(patients._IS_ACTIVE)))
        .group_by(MeasurementProfile.idInstitucionUsuarioResponsable)).all())
    started = dict(db.execute(
        select(Audit.idRelacionado, func.count()).join(Measurement, Measurement.idMedicion == Audit.idRegistro).where(
            Audit.tablaAfectada == "Medicion", Audit.accion == "INICIAR_MEDICION", Audit.idRelacionado.is_not(None), scope,
            *_inPeriod(Measurement.fechaHoraInicio, start, end)).group_by(Audit.idRelacionado)).all())
    operators = db.execute(
        select(InstitutionUser, User).outerjoin(User, User.idUsuario == InstitutionUser.idUsuarioInvitado).where(
            InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.rolInstitucion == institutions.ROL_OPERADOR)).all()
    load = [
        OperatorLoad(
            idInstitucionUsuario=rel.idInstitucionUsuario,
            nombre=_staffName(rel, user)[0],
            apellido=_staffName(rel, user)[1],
            activo=rel.estadoRelacion == institutions.RELACION_ACTIVO,
            pacientesAsignados=assigned.get(rel.idInstitucionUsuario, 0), mediciones=started.get(rel.idInstitucionUsuario, 0))
        for rel, user in operators
        if rel.estadoRelacion == institutions.RELACION_ACTIVO or started.get(rel.idInstitucionUsuario)
    ]
    load.sort(key=lambda item: (-item.mediciones, item.apellido or "", item.nombre or ""))
    # Estadísticas de salud agregadas: solo si el conjunto (con el período elegido) tiene suficientes pacientes distintos.
    protected = patientAccess.suppressSmallGroup(db, scope, (Measurement.estadoMedicion == COMPLETADA, *_inPeriod(Measurement.fechaHoraInicio, start, end)))
    if protected:
        byDay.clear()
    return InstitutionDashboard(
        periodo=period, pacientesPendientesReasignacion=reassignments.pendingCount(db, idInstitucion), agregadosProtegidos=protected, minimoPacientesAgregados=patientAccess.MIN_AGGREGATE_PATIENTS,
        pacientesActivos=db.scalar(select(func.count()).select_from(
            _institutionProfileIds(idInstitucion).where(patients._IS_ACTIVE).subquery())) or 0,
        moderadoresActivos=institutions._activeCount(db, idInstitucion, institutions.ROL_MODERADOR),
        operadoresActivos=institutions._activeCount(db, idInstitucion, institutions.ROL_OPERADOR),
        dispositivosRegistrados=sum(n for _, n in devices), dispositivosOperativos=sum(n for state, n in devices if state == "OPERATIVO"),
        medicionesTotal=sum(states.values()),
        medicionesHoy=count(Measurement.fechaHoraInicio >= datetime.combine(now.date(), datetime.min.time())),
        medicionesUltimos7Dias=count(Measurement.fechaHoraInicio >= now - timedelta(days=7)),
        medicionesUltimos30Dias=count(Measurement.fechaHoraInicio >= now - timedelta(days=30)),
        medicionesEnPeriodo=len(rows), porEstado=states, porModo=modes,
        ultimaActividad=db.scalar(select(func.max(Measurement.fechaHoraInicio)).where(scope)),
        serie=[DayCount(fecha=day, total=total, completadas=done) for day, (total, done) in sorted(byDay.items())],
        estadisticas=measurements.buildStatistics(db, None, dias, desde=desde, hasta=hasta, profileIds=[] if protected else profileIds,
                                                  minPatientsPerDay=patientAccess.MIN_AGGREGATE_PATIENTS),
        porOperador=load,
        administrativo=_adminStats(db, idInstitucion, profileIds, start, end, operador, modo, estado, origen),
        saludAgregada=_healthAggregates(db, profileIds, start, end, operador, modo, estado, origen))


# --- Institucional: por operador --------------------------------------------------------------------------------


def _resolveOperator(db: Session, actor: User, idInstitucion: uuid.UUID, idOperador: str):
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_PACIENTES)
    if idOperador == "me":
        relation = membership.relation if membership.role == institutions.ROL_OPERADOR else None
    else:
        try:
            relation = db.get(InstitutionUser, uuid.UUID(idOperador))
        except ValueError:
            relation = None
    if relation is None or relation.idInstitucion != idInstitucion or relation.rolInstitucion != institutions.ROL_OPERADOR:
        raise AuthError("MIEMBRO_NO_ENCONTRADO", "No encontramos a ese operador en la institución.")
    isSelf = relation.idInstitucionUsuario == membership.relation.idInstitucionUsuario
    if not isSelf and not membership.can(institutions.P_EQUIPO):
        raise AuthError("PERMISO_INSUFICIENTE", "Un operador solo consulta su propio dashboard.")
    return membership, relation, isSelf


def _staffName(relation: InstitutionUser, user: User | None) -> tuple[str | None, str | None]:
    """(nombre, apellido) con que las ESTADÍSTICAS muestran a una persona del personal: su identificación histórica registrada en el vínculo
    (nombre y apellido profesional, que se conservan aunque se desvincule o su cuenta se elimine) y, si no hay, la de su cuenta vigente. Solo
    cuando los datos históricos ya se minimizaron (vencida la conservación) o no hay ningún nombre se muestra un rótulo neutro; las cifras se
    conservan atribuidas a su vínculo. La nómina de la institución (personal) es otra pantalla, con su propia regla de conservación."""
    full = personName(relation, user) or ""  # personName ya devuelve None si el vínculo se minimizó
    if not full:
        return ("Operador desvinculado" if relation.rolInstitucion == institutions.ROL_OPERADOR else "Integrante desvinculado"), None
    return full.split(" ", 1)[0] or None, full.partition(" ")[2] or None


def _personRef(relation: InstitutionUser, user: User | None) -> PersonRef:
    name, surname = _staffName(relation, user)
    return PersonRef(idInstitucionUsuario=relation.idInstitucionUsuario, nombre=name, apellido=surname,
                     rolInstitucion=relation.rolInstitucion, activo=relation.estadoRelacion == institutions.RELACION_ACTIVO)


MAX_CHART_ROWS = 20000
AGE_RANGES = (("0-17", 0, 17), ("18-39", 18, 39), ("40-59", 40, 59), ("60+", 60, 200))


def _operatorCharts(db: Session, performedAllIds, assignedRows, assignedIds, start: datetime, end: datetime | None, now: datetime) -> OperatorCharts:
    """Gráficos del PROPIO operador. Serie y modos cuentan las mediciones que él inició en el período (los mismos números que sus indicadores,
    DEMO aparte); la calidad de señal es un valor de la medición y solo se lee de pacientes que tiene a cargo hoy; la demografía cuenta
    pacientes únicos asignados ahora, sin nombres ni documentos."""
    rows = db.execute(select(Measurement.fechaHoraInicio, Measurement.modoMedicion, Measurement.origenGlucosa, Measurement.calidadSenal,
                             Measurement.idPerfilMedicion, Measurement.estadoMedicion,
                             Measurement.lecturasEstabilizadas).where(Measurement.idMedicion.in_(performedAllIds),
                                                                 *_inPeriod(Measurement.fechaHoraInicio, start, end))
                      .order_by(Measurement.fechaHoraInicio.desc()).limit(MAX_CHART_ROWS + 1)).all()
    truncated = len(rows) > MAX_CHART_ROWS
    rows = rows[:MAX_CHART_ROWS]
    isDemo = lambda row: row.origenGlucosa == ORIGEN_DEMO  # noqa: E731
    noResultRows = [row for row in rows if row.estadoMedicion != COMPLETADA and row.origenGlucosa is None]
    rows = [row for row in rows if not (row.estadoMedicion != COMPLETADA and row.origenGlucosa is None)]  # sin resultado: se cuentan aparte
    perDay: dict[date, list[int]] = {}
    perMode = {"OXIMETRIA": [0, 0], "GLUCOSA_EXPERIMENTAL": [0, 0]}
    for row in rows:
        perDay.setdefault(row.fechaHoraInicio.date(), [0, 0])[1 if isDemo(row) else 0] += 1
        perMode.setdefault(row.modoMedicion, [0, 0])[1 if isDemo(row) else 0] += 1
    assigned = set(assignedIds)
    completed = [row for row in rows if row.estadoMedicion == COMPLETADA]  # la calidad de señal solo existe en mediciones completadas
    inScope = [row for row in completed if row.idPerfilMedicion in assigned]
    values = [float(row.calidadSenal) for row in inScope if row.calidadSenal is not None]
    bins: list[QualityBin] = []
    if values:
        low, high = min(values), max(values)
        parts = 1 if low == high else 4
        width = (high - low) / parts
        for index in range(parts):
            a = low + index * width
            b = high if index == parts - 1 else low + (index + 1) * width
            members = [row for row in inScope if row.calidadSenal is not None
                       and (a <= float(row.calidadSenal) <= b if index == parts - 1 else a <= float(row.calidadSenal) < b)]
            bins.append(QualityBin(desde=round(a, 3), hasta=round(b, 3), experimentales=sum(1 for r in members if not isDemo(r)),
                                   demo=sum(1 for r in members if isDemo(r))))
    readings: dict[int, list[int]] = {}
    for row in inScope:
        if row.lecturasEstabilizadas is not None:
            readings.setdefault(int(row.lecturasEstabilizadas), [0, 0])[1 if isDemo(row) else 0] += 1
    sexKeys = {"MASCULINO": "masculino", "FEMENINO": "femenino"}
    table = {label: {"masculino": 0, "femenino": 0, "sinInformar": 0} for label in (*(a[0] for a in AGE_RANGES), "SIN_INFORMAR")}
    for profile, _, _ in assignedRows:
        age = calculateAge(profile.fechaNacimiento, now.date()) if profile.fechaNacimiento else profile.edadDeclarada
        label = next((name for name, low, high in AGE_RANGES if age is not None and low <= age <= high), "SIN_INFORMAR")
        table[label][sexKeys.get(profile.sexoModelo, "sinInformar")] += 1
    return OperatorCharts(
        sinResultado=len(noResultRows),
        serie=[OperatorDay(fecha=day, experimentales=pair[0], demo=pair[1]) for day, pair in sorted(perDay.items())],
        porModo=[OperatorModeCount(modo=mode, experimentales=pair[0], demo=pair[1]) for mode, pair in perMode.items()],
        calidadSenal=OperatorQuality(conValor=len(values), sinDato=len(inScope) - len(values), fueraDeAlcance=len(completed) - len(inScope),
                                     minimo=min(values) if values else None, maximo=max(values) if values else None, rangos=bins,
                                     conLecturas=sum(sum(pair) for pair in readings.values()),
                                     lecturas=[ReadingsBin(lecturas=count, experimentales=pair[0], demo=pair[1]) for count, pair in sorted(readings.items())]),
        demografia=[DemographicRow(rango=label, **counts) for label, counts in table.items()], pacientesDemografia=len(assignedRows),
        truncado=truncated)


def operatorDashboard(db: Session, actor: User, idInstitucion: uuid.UUID, idOperador: str, dias: int = 30,
                      desde: date | None = None, hasta: date | None = None) -> OperatorDashboard:
    start, end, period = _range(dias, desde, hasta)
    membership, relation, isSelf = _resolveOperator(db, actor, idInstitucion, idOperador)
    relId = relation.idInstitucionUsuario
    user = db.get(User, relation.idUsuarioInvitado)
    now = nowForDb()

    # Pacientes asignados AHORA (responsable actual, sin baja).
    assignedRows = db.execute(patients._patientsOf(idInstitucion).where(
        patients._IS_ACTIVE, MeasurementProfile.idInstitucionUsuarioResponsable == relId)
        .order_by(MeasurementProfile.identificadorPseudonimo)).all()
    assignedIds = [row[0].idPerfilMedicion for row in assignedRows]
    # Última medición COMPLETADA de cada paciente listado, sea experimental o DEMO (una medición DEMO también es un registro del paciente).
    listedIds = [row[0].idPerfilMedicion for row in assignedRows[:MAX_LISTED]]
    latest = select(Measurement.idPerfilMedicion.label("perfil"), func.max(Measurement.fechaHoraInicio).label("momento")).where(
        Measurement.idPerfilMedicion.in_(listedIds), Measurement.estadoMedicion == COMPLETADA).group_by(Measurement.idPerfilMedicion).subquery()
    lastByProfile = {row[0]: row for row in db.execute(
        select(Measurement.idPerfilMedicion, Measurement.fechaHoraInicio, Measurement.modoMedicion, Measurement.origenGlucosa)
        .join(latest, (Measurement.idPerfilMedicion == latest.c.perfil) & (Measurement.fechaHoraInicio == latest.c.momento))
        .where(Measurement.estadoMedicion == COMPLETADA)).all()} if listedIds else {}
    patientList = []
    for profile, _, _ in assignedRows[:MAX_LISTED]:
        allowed = transfers.canSeeIdentity(membership, profile)
        patientList.append(AssignedPatient(
            idPerfilMedicion=profile.idPerfilMedicion, identificadorPseudonimo=profile.identificadorPseudonimo,
            nombre=profile.nombre if allowed else None, apellido=profile.apellido if allowed else None,
            datosIdentificativos=bool(profile.nombre or profile.apellido) if allowed else None,
            edad=calculateAge(profile.fechaNacimiento, now.date()) if profile.fechaNacimiento else profile.edadDeclarada,
            sexoModelo=profile.sexoModelo,
            ultimaMedicion=lastByProfile[profile.idPerfilMedicion][1] if profile.idPerfilMedicion in lastByProfile else None,
            ultimaModo=lastByProfile[profile.idPerfilMedicion][2] if profile.idPerfilMedicion in lastByProfile else None,
            ultimaEsDemo=(lastByProfile[profile.idPerfilMedicion][3] == ORIGEN_DEMO) if profile.idPerfilMedicion in lastByProfile else None))

    # Mediciones que ESTE operador inició (histórico, aunque el paciente ya no esté a su cargo).
    performedAll = (select(Measurement).join(Audit, Audit.idRegistro == Measurement.idMedicion).where(
        Audit.tablaAfectada == "Medicion", Audit.accion == "INICIAR_MEDICION", Audit.idRelacionado == relId,
        Measurement.idPerfilMedicion.in_(_institutionProfileIds(idInstitucion))))
    performed = performedAll.where(NOT_DEMO)  # los contadores históricos conservan su criterio; lo DEMO se informa aparte
    performedIds = performed.with_only_columns(Measurement.idMedicion)
    performedAllIds = performedAll.with_only_columns(Measurement.idMedicion)
    isDemo = Measurement.origenGlucosa == ORIGEN_DEMO
    demoTotal = db.scalar(select(func.count()).select_from(Measurement).where(Measurement.idMedicion.in_(performedAllIds), isDemo)) or 0
    demoInPeriod = db.scalar(select(func.count()).select_from(Measurement).where(
        Measurement.idMedicion.in_(performedAllIds), isDemo, *_inPeriod(Measurement.fechaHoraInicio, start, end))) or 0
    noResult = and_(Measurement.estadoMedicion != COMPLETADA, Measurement.origenGlucosa.is_(None))  # canceladas/inválidas/en curso: sin resultado ni origen
    noResultInPeriod = db.scalar(select(func.count()).select_from(Measurement).where(
        Measurement.idMedicion.in_(performedAllIds), noResult, *_inPeriod(Measurement.fechaHoraInicio, start, end))) or 0
    noResultTotal = db.scalar(select(func.count()).select_from(Measurement).where(Measurement.idMedicion.in_(performedAllIds), noResult)) or 0
    perStatus = dict(db.execute(select(Measurement.estadoMedicion, func.count()).where(
        Measurement.idMedicion.in_(performedIds)).group_by(Measurement.estadoMedicion)).all())
    inPeriod = db.scalar(select(func.count()).select_from(Measurement).where(
        Measurement.idMedicion.in_(performedIds), *_inPeriod(Measurement.fechaHoraInicio, start, end))) or 0
    # Con valores de salud solo los pacientes que el operador tiene a cargo HOY: la autoría histórica (Auditoria) no autoriza la lectura
    # (patientAccess.py); los conteos históricos de arriba no llevan valores y se conservan.
    recentRows = db.scalars(performedAll.where(Measurement.idPerfilMedicion.in_(assignedIds)).order_by(
        Measurement.fechaHoraInicio.desc()).limit(RECENT)).all() if assignedIds else []
    ofPatients = db.scalars(select(Measurement).where(Measurement.idPerfilMedicion.in_(assignedIds))
                            .order_by(Measurement.fechaHoraInicio.desc()).limit(RECENT)).all() if assignedIds else []
    pseudonyms = _pseudonyms(db, [r.idPerfilMedicion for r in (*recentRows, *ofPatients)])

    # Transferencias del operador (las asignaciones directas no son solicitudes y no se cuentan).
    request = Audit.accion == "SOLICITAR_TRANSFERENCIA_PERFIL"
    sent = dict(db.execute(select(ProfileTransfer.estado, func.count()).join(
        Audit, (Audit.idRegistro == ProfileTransfer.idTransferenciaPerfil) & (Audit.tablaAfectada == "TransferenciaPerfil")
    ).where(request, Audit.idRelacionado == relId).group_by(ProfileTransfer.estado)).all())
    received = dict(db.execute(select(ProfileTransfer.estado, func.count()).join(
        Audit, (Audit.idRegistro == ProfileTransfer.idTransferenciaPerfil) & (Audit.tablaAfectada == "TransferenciaPerfil")
    ).where(request, ProfileTransfer.idOperadorDestino == relId).group_by(ProfileTransfer.estado)).all())

    lastStart = db.scalar(select(func.max(Measurement.fechaHoraInicio)).where(Measurement.idMedicion.in_(performedAllIds)))
    lastTransfer = db.scalar(select(func.max(ProfileTransfer.fechaPeticion)).where(ProfileTransfer.idOperadorDestino == relId))
    activity = [moment for moment in (lastStart, lastTransfer) if moment]

    available = db.scalars(select(Device).where(
        Device.idInstitucionAsignada == idInstitucion, Device.estado == "OPERATIVO",
        (Device.idInstitucionUsuarioResponsable.is_(None)) | (Device.idInstitucionUsuarioResponsable == relId)
        | Device.idInstitucionUsuarioResponsable.in_(  # custodia del propietario: no excluye al operador
            select(InstitutionUser.idInstitucionUsuario).where(InstitutionUser.rolInstitucion == institutions.ROL_PROPIETARIO)))
        .order_by(Device.codigoDispositivo)).all()
    # Quien supervisa (propietario o moderador) ve la carga de trabajo del operador, no sus pacientes ni sus mediciones individuales:
    # sin lista de pacientes, sin mediciones y sin resultados (información de salud, solo del operador responsable).
    return OperatorDashboard(
        periodo=period, operador=_personRef(relation, user), pacientesAsignados=len(assignedRows), pacientes=patientList if isSelf else [],
        medicionesRealizadas=sum(perStatus.values()), medicionesEnPeriodo=inPeriod, medicionesPorEstado=perStatus,
        medicionesRealizadasDemo=demoTotal, medicionesEnPeriodoDemo=demoInPeriod,
        medicionesEnPeriodoSinResultado=noResultInPeriod, medicionesSinResultado=noResultTotal,
        ultimaActividad=max(activity) if activity else None,
        graficos=_operatorCharts(db, performedAllIds, assignedRows, assignedIds, start, end, now) if isSelf else None,
        realizadas=_performedRows(db, recentRows, pseudonyms, withOperator=False) if isSelf else [],
        ultimasDePacientes=_performedRows(db, ofPatients, pseudonyms, withOperator=True) if isSelf else [],
        transferencias=TransferCounters(
            recibidas=sum(received.values()), recibidasPendientes=received.get("PENDIENTE", 0),
            enviadas=sum(sent.values()), enviadasPendientes=sent.get("PENDIENTE", 0)),
        dispositivosDisponibles=len(available),
        dispositivos=[AvailableDevice(idDispositivo=d.idDispositivo, codigoDispositivo=d.codigoDispositivo, nombre=d.nombre,
                                      modeloSensor=d.modeloSensor) for d in available[:MAX_LISTED]],
        esPropio=isSelf)


# --- Institucional: por paciente --------------------------------------------------------------------------------


def patientDashboard(db: Session, actor: User, idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, dias: int = 30,
                     desde: date | None = None, hasta: date | None = None) -> PatientDashboard:
    start, end, period = _range(dias, desde, hasta)
    membership, profile = measurements.requireClinicalAccess(db, actor, idInstitucion, idPerfilMedicion, "DASHBOARD")
    allowed = transfers.canSeeIdentity(membership, profile)
    if allowed:  # acceso a datos identificativos: queda registrado (sin los datos)
        registerEvent(db, "ACCESO", "CONSULTAR_PACIENTE", True, actor.idUsuario, "PerfilMedicion", idPerfilMedicion)
        db.commit()
    now = nowForDb()
    relation = db.get(InstitutionUser, profile.idInstitucionUsuarioResponsable)
    responsible = _personRef(relation, db.get(User, relation.idUsuarioInvitado)) if relation else None

    history = db.scalars(select(Measurement).where(Measurement.idPerfilMedicion == idPerfilMedicion, NOT_DEMO)
                         .order_by(Measurement.fechaHoraInicio.desc()).limit(15)).all()

    # Historial de transferencias del perfil: origen desde el evento que la solicitó (o la asignación directa).
    rows = db.execute(select(ProfileTransfer).where(ProfileTransfer.idPerfilMedicion == idPerfilMedicion)
                      .order_by(ProfileTransfer.fechaPeticion.desc())).scalars().all()
    origins = {}
    if rows:
        origins = {r[0]: (r[1], r[2]) for r in db.execute(select(Audit.idRegistro, Audit.idRelacionado, Audit.accion).where(
            Audit.tablaAfectada == "TransferenciaPerfil", Audit.idRegistro.in_([t.idTransferenciaPerfil for t in rows]),
            Audit.accion.in_(transfers.ORIGIN_ACTIONS))).all()}
    relIds = {t.idOperadorDestino for t in rows} | {o[0] for o in origins.values() if o[0]}
    people = {}
    if relIds:
        for rel, user in db.execute(select(InstitutionUser, User).outerjoin(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
                                    .where(InstitutionUser.idInstitucionUsuario.in_(relIds))).all():
            people[rel.idInstitucionUsuario] = _personRef(rel, user)
    transferRows = []
    for t in rows:
        origin = origins.get(t.idTransferenciaPerfil)
        transferRows.append(PatientTransferRow(
            idTransferenciaPerfil=t.idTransferenciaPerfil, estado=t.estado,
            tipo="REASIGNACION" if origin and origin[1] == patients.ACCION_ORIGEN_DIRECTA else "TRANSFERENCIA",
            fechaPeticion=t.fechaPeticion, fechaTransferencia=t.fechaTransferencia,
            origen=people.get(origin[0]) if origin and origin[0] else None, destino=people[t.idOperadorDestino]))
    return PatientDashboard(
        periodo=period,
        perfil=PatientProfileInfo(
            idPerfilMedicion=profile.idPerfilMedicion, identificadorPseudonimo=profile.identificadorPseudonimo,
            nombre=profile.nombre if allowed else None, apellido=profile.apellido if allowed else None,
            datosIdentificativos=bool(profile.nombre or profile.apellido) if allowed else None,
            edad=calculateAge(profile.fechaNacimiento, now.date()) if profile.fechaNacimiento else profile.edadDeclarada,
            fechaNacimiento=profile.fechaNacimiento if allowed else None, sexoModelo=profile.sexoModelo,
            estado=patients.patientState(profile), responsable=responsible, ultimaMedicion=profile.fechaUltimaMedicion),
        resumen=_summary(db, [idPerfilMedicion], start, end),
        estadisticas=measurements.buildStatistics(db, idPerfilMedicion, dias, desde=desde, hasta=hasta),
        historial=_performedRows(db, history, {idPerfilMedicion: profile.identificadorPseudonimo}, withOperator=True),
        transferencias=transferRows)


# --- Familiar ---------------------------------------------------------------------------------------------------


def _memberActivity(db: Session, member, relation: GroupUser, profile) -> list[GroupActivity]:
    """Las últimas `ACTIVITY_PER_MEMBER` actividades que ESTA persona autorizó mostrar (cupo por integrante).

    Se toman sus mediciones completadas más recientes (DEMO incluidas) y cada una se muestra según SUS permisos:
      · «Historial» → con valores en todo el cupo; «Última medición» → con valores solo la más reciente;
      · «Aviso de medición» → solo el hecho (fecha y hora): NUNCA valores. Sin ningún permiso aplicable no hay actividad.
    El orden global entre integrantes lo hace quien llama, después de aplicar el cupo a cada persona."""
    withValues = ACTIVITY_PER_MEMBER if relation.comparteHistorial else (1 if relation.comparteUltimaMedicion else 0)
    if withValues == 0 and not relation.notificaMedicion:
        return []
    rows = db.scalars(select(Measurement).where(
        Measurement.idPerfilMedicion == profile.idPerfilMedicion, Measurement.estadoMedicion == COMPLETADA)
        .order_by(Measurement.fechaHoraInicio.desc()).limit(ACTIVITY_PER_MEMBER)).all()
    items: list[GroupActivity] = []
    for index, row in enumerate(rows):
        base = dict(idGrupoUsuario=member.idGrupoUsuario, nombre=member.nombre, apellido=member.apellido, fechaHoraInicio=row.fechaHoraInicio)
        if index < withValues:
            items.append(GroupActivity(tipo="MEDICION", medicion=groups._measurement(row), **base))
        elif relation.notificaMedicion:
            items.append(GroupActivity(tipo="AVISO", **base))
    return items


def groupDashboard(db: Session, actor: User, idGrupo: uuid.UUID, dias: int = 30, desde: date | None = None,
                   hasta: date | None = None) -> GroupDashboard:
    """Los permisos de cada integrante se leen en esta consulta: si alguien revoca, deja de aparecer ya mismo."""
    start, end, period = _range(dias, desde, hasta)
    detail = groups.getDetail(db, actor, idGrupo)
    members = groups.listMembers(db, actor, idGrupo)
    owners = {relation.idGrupoUsuario: (relation, user) for relation, user in db.execute(
        select(GroupUser, User).join(User, User.idUsuario == GroupUser.idUsuario)
        .where(GroupUser.idGrupo == idGrupo, GroupUser.estadoRelacion == groups.ACTIVO)).all()}

    activity: list[GroupActivity] = []
    pooled: list[tuple[uuid.UUID, str]] = []
    for member in members:
        relation, user = owners[member.idGrupoUsuario]
        profile = groups._ownProfile(db, user.idUsuario)
        if profile is None:
            continue
        activity.extend(_memberActivity(db, member, relation, profile))
        if relation.comparteHistorial:  # solo el historial autoriza estadísticas; «última medición» no alcanza
            pooled.append((profile.idPerfilMedicion, " ".join(p for p in (member.nombre, member.apellido) if p) or "Integrante"))
    activity.sort(key=lambda item: item.fechaHoraInicio, reverse=True)

    aggregate, reason = None, None
    if len(pooled) >= MIN_GROUP_PARTICIPANTS:
        aggregate = GroupAggregate(
            participantes=sorted(name for _, name in pooled),
            estadisticas=measurements.buildStatistics(db, None, dias, desde=desde, hasta=hasta, profileIds=[p for p, _ in pooled]))
    else:
        reason = (f"Se necesitan al menos {MIN_GROUP_PARTICIPANTS} integrantes que compartan su historial para mostrar "
                  "estadísticas del grupo sin exponer a una sola persona.")
    registerEvent(db, "ACCESO", "CONSULTAR_DASHBOARD_GRUPO", True, actor.idUsuario, "Grupo", idGrupo,
                  datosNuevos={"integrantesIncluidos": len(pooled)})
    db.commit()
    return GroupDashboard(
        grupo=detail, periodo=period, integrantesActivos=len(members),
        administradores=sum(m.rol == "ADMINISTRADOR" for m in members),
        miembros=sum(m.rol == "MIEMBRO" for m in members),
        comparteUltimaMedicion=sum(m.comparteUltimaMedicion for m in members),
        comparteHistorial=sum(m.comparteHistorial for m in members), integrantes=members,
        actividadReciente=activity, agregado=aggregate, motivoSinAgregado=reason)
