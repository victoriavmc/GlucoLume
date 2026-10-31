# Measurement - Mediciones sobre un PerfilMedicion (individual o institucional)
#
# Ciclo de vida (estados exactos de CK_Medicion_estado), todas las transiciones son UPDATE condicionados al estado
# esperado, por lo que dos pedidos simultáneos no pueden aplicar la misma transición dos veces:
#
#   PENDIENTE ──muestras──▶ ADQUIRIENDO ──finish──▶ PROCESANDO ──▶ COMPLETADA | INVALIDA
#       └──cancel──▶ CANCELADA  (también desde ADQUIRIENDO)
#
# Una medición solo pasa a COMPLETADA en el mismo UPDATE que persiste sus resultados. INVALIDA y CANCELADA nunca se
# presentan como resultado completo y quedan fuera de las estadísticas (solo se calculan sobre COMPLETADA).
#
# Quién puede qué:
#   - Consumidor final: inicia, opera y consulta SOLO su propio perfil (CONSUMIDOR_FINAL). La pertenencia a un grupo
#     no da propiedad; lo que otros ven lo decide el módulo de grupos (permisos personales).
#   - Operador: inicia y opera mediciones de los pacientes que tiene a cargo AHORA (responsable actual, vínculo
#     ACTIVO, institución ACTIVA, paciente sin baja). Consulta el historial según CONSULTAR_PACIENTES.
#   - Quien inició la medición queda en Auditoria (INICIAR_MEDICION: idUsuario + idRelacionado = vínculo operador),
#     por lo que la autoría se conserva aunque el paciente cambie de responsable. Los valores históricos
#     (edad, sexo, firmware, sensor, matriz, versión del algoritmo) se copian a Medicion y no se recalculan.
#
# Datos del dispositivo (puente serie): el firmware envía BPM, SpO₂, el índice óptico y la glucosa experimental ya
# procesados; app/services/telemetry.py guarda UNA medición al confirmar «Guardar medición» (nunca una por segundo) con
# `origenGlucosa`. DEMO = valor sintético solo para probar la integración: se puede consultar y eliminar, y queda fuera
# de estadísticas, dashboards, indicadores, avisos y correos (NOT_DEMO en cada consulta de indicadores).
#
# Adquisición: las muestras llegan por la API (MuestraSensor), enviadas por el puente Arduino → pySerial
# (app/acquisition). SpO₂ y frecuencia cardíaca las calcula el servidor sobre esas muestras (acquisition/oximetry.py);
# los valores que informe un cliente en el cierre se ignoran. Este módulo no genera datos del sensor ni simula un dispositivo. La estimación de glucosa necesita un algoritmo que aún no
# está definido: `glucoseEstimator` es el punto de integración. Sin él, una medición GLUCOSA_EXPERIMENTAL termina
# INVALIDA y nunca se inventa un valor.

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, delete, func, insert, not_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.acquisition import oximetry
from app.core.exceptions import AuthError
from app.models.capillaryReference import CapillaryReferenceMeasurement
from app.models.device import Device
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.matrix import Matrix
from app.models.matrixRule import MatrixRule
from app.models.measurement import NOT_DEMO, ORIGEN_DEMO, Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.sensorSample import SensorSample
from app.models.user import User
from app.emails.eventTypes import EmailEventType
from app.emails.formatting import maskEmail
from app.services import resultEmailStore
from app.models.resultDelivery import ResultDelivery
from app.schemas.resultDelivery import ResultSendRead, ResultSendRequest
from app.services import email as emailService
from app.schemas.capillaryReference import CapillaryReferenceMeasurementRead
from app.schemas.group import DailyPoint, MetricSummary, SharedStatisticsRead
from app.schemas.measurement import (
    CapillaryReferenceRequest,
    EvolutionBlock,
    EvolutionLast,
    EvolutionLastMeasurement,
    EvolutionPoint,
    EvolutionRead,
    EvolutionStat,
    EvolutionStats,
    EvolutionSummary,
    DeviceSummary,
    InstitutionIndicators,
    MatrixSummary,
    MeasurementDetail,
    MeasurementFinish,
    MeasurementListItem,
    MeasurementPage,
    MeasurementStart,
    OwnProfileRead,
    SamplesRequest,
)
from app.services import device as deviceService
from app.services import institution as institutions
from app.services import patientAccess
from app.services import matrix as matrixService
from app.services import consent as consentService
from app.services import glucoseReference, measurementRetention, schemaCompat, technicalAudit
from app.services.measurementVisibility import hiddenCondition, isHidden, visibleUntil
from app.services import notifications
from app.services import institutionPatients as patients
from app.services.audit import registerEvent
from app.services.measurementProfile import (
    TIPO_CONSUMIDOR_FINAL,
    TIPO_INSTITUCIONAL,
    calculateAge,
    ensureConsumerProfile,
    getConsumerProfile,
    measurementSnapshot,
    missingRecommendedFields,
)
from app.utils.timeZone import nowForDb

PENDIENTE, ADQUIRIENDO, PROCESANDO = "PENDIENTE", "ADQUIRIENDO", "PROCESANDO"
COMPLETADA, INVALIDA, CANCELADA = "COMPLETADA", "INVALIDA", "CANCELADA"
OXIMETRIA, GLUCOSA = "OXIMETRIA", "GLUCOSA_EXPERIMENTAL"
DEVICE_OPERATIVO = "OPERATIVO"
MATRIX_ACTIVA = "ACTIVA"
MAX_PAGE_SIZE = 50
STATISTICS_DAYS = (7, 30, 90)

NOT_FOUND = "No encontramos esa medición."
PROFILE_NOT_FOUND = "No encontramos ese perfil de medición."


def _error(code: str, message: str) -> AuthError:
    return AuthError(code, message)


# Punto de integración del algoritmo de estimación de glucosa. Firma:
#   estimator(samples: list[tuple[int, int]], rule: MatrixRule, matrix: Matrix, edad: int, sexo: str) -> (Decimal, versionAlgoritmo) | None
# Sin algoritmo definido es None: no se fabrica ninguna estimación.
GlucoseEstimator = Callable[..., "tuple[Decimal, str] | None"]
glucoseEstimator: GlucoseEstimator | None = None


# --- Acceso al perfil ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ProfileAccess:
    profile: MeasurementProfile
    idInstitucion: uuid.UUID | None  # None: perfil individual
    relation: InstitutionUser | None  # responsable actual (perfil institucional)
    canOperate: bool


def _access(db: Session, actor: User, profile: MeasurementProfile | None, notFound: str,
            notFoundMessage: str) -> ProfileAccess:
    """Resuelve si `actor` puede ver (y operar) el perfil. Todo lo que no corresponde se informa como inexistente."""
    missing = _error(notFound, notFoundMessage)
    if profile is None:
        raise missing
    if profile.tipoPerfil == TIPO_CONSUMIDOR_FINAL:
        if profile.idUsuario != actor.idUsuario:
            raise missing
        return ProfileAccess(profile, None, None, True)
    if profile.tipoPerfil != TIPO_INSTITUCIONAL or profile.idInstitucionUsuarioResponsable is None:
        raise missing
    relation = db.get(InstitutionUser, profile.idInstitucionUsuarioResponsable)
    if relation is None:
        raise missing
    try:
        membership = institutions.requireMembership(db, actor, relation.idInstitucion, institutions.P_PACIENTES)
        patients._load(db, relation.idInstitucion, profile.idPerfilMedicion)  # período vigente, sin depurados
    except AuthError as error:
        raise missing from error
    # Información de salud: solo el operador responsable vigente (patientAccess). Un integrante de la institución sin esa asignación,
    # sea cual sea su rol, recibe el rechazo explícito (y queda auditado); quien no pertenece a la institución recibe «inexistente».
    patientAccess.requireMeasurementAccess(db, actor, membership, profile, "MEDICION")
    canOperate = (
        relation.idUsuarioInvitado == actor.idUsuario
        and relation.estadoRelacion == institutions.RELACION_ACTIVO
        and relation.rolInstitucion == institutions.ROL_OPERADOR
        and membership.can(institutions.P_GESTIONAR_PACIENTES)
        and patients.patientState(profile) == patients.PACIENTE_ACTIVO
    )
    return ProfileAccess(profile, relation.idInstitucion, relation, canOperate)


def _requireExperimentalConsent(db: Session, actor: User, profile: MeasurementProfile) -> None:
    """Perfil propio de una cuenta individual: no se recolectan mediciones sin su autorización expresa vigente
    (app/services/consent.py). Los pacientes de una institución los opera su personal: ese consentimiento lo gestiona
    la institución y no se valida acá."""
    if profile.tipoPerfil == TIPO_CONSUMIDOR_FINAL:
        consentService.requireExperimentalData(db, actor)


def _requireOperate(access: ProfileAccess) -> None:
    if not access.canOperate:
        raise _error("PERMISO_INSUFICIENTE", "Solo podés operar mediciones de tu propio perfil o de los pacientes a tu cargo.")


def _measurementAccess(db: Session, actor: User, idMedicion: uuid.UUID) -> tuple[Measurement, ProfileAccess]:
    measurement = db.get(Measurement, idMedicion)
    profile = db.get(MeasurementProfile, measurement.idPerfilMedicion) if measurement else None
    access = _access(db, actor, profile, "MEDICION_NO_ENCONTRADA", NOT_FOUND)
    if profile.tipoPerfil == TIPO_CONSUMIDOR_FINAL and isHidden(measurement, nowForDb()):
        raise _error("MEDICION_NO_ENCONTRADA", NOT_FOUND)  # vencida su visibilidad: ya no se recupera ni por URL directa
    return measurement, access


# --- Perfil propio y dispositivos ----------------------------------------------------------------------------


def getOwnProfile(db: Session, actor: User) -> OwnProfileRead:
    """Perfil de medición propio. Lo crea la primera vez desde los datos de la cuenta. La fecha de nacimiento y el sexo son
    OPCIONALES: `datosRecomendados` indica cuáles faltan (se recomiendan, no se exigen)."""
    if actor.tipoCuenta != TIPO_CONSUMIDOR_FINAL:
        raise _error("PERFIL_NO_DISPONIBLE", "Solo una cuenta individual tiene un perfil de medición propio.")
    profile = ensureConsumerProfile(db, actor)
    age = calculateAge(profile.fechaNacimiento, nowForDb().date()) if profile.fechaNacimiento else profile.edadDeclarada
    return OwnProfileRead(
        perfilDisponible=True, datosFaltantes=[], datosRecomendados=missingRecommendedFields(actor),
        idPerfilMedicion=profile.idPerfilMedicion, nombre=profile.nombre,
        apellido=profile.apellido, fechaNacimiento=profile.fechaNacimiento, edad=age, sexoModelo=profile.sexoModelo,
        fechaCreacion=profile.fechaCreacion, fechaUltimaMedicion=profile.fechaUltimaMedicion,
    )


def _deviceUsable(device: Device, idInstitucion: uuid.UUID | None, relationId: uuid.UUID | None = None) -> bool:
    """Estado OPERATIVO, institución (los individuales usan los no asignados) y responsable: ver device.usableBy.
    Un paciente de una institución se mide solo con dispositivos de SU inventario: uno sin institución se vincula primero (Conectar dispositivo)."""
    return deviceService.usableBy(device, idInstitucion, relationId)[0] and (
        idInstitucion is None or device.idInstitucionAsignada == idInstitucion or deviceService.sharedDeviceMode())  # DEC-01


def _operatorRelation(access: ProfileAccess) -> uuid.UUID | None:
    return access.relation.idInstitucionUsuario if access.relation is not None else None


def listDevices(db: Session, actor: User, idPerfilMedicion: uuid.UUID) -> list[DeviceSummary]:
    """Dispositivos operativos que se pueden usar para medir ese perfil (solo lectura)."""
    access = _access(db, actor, db.get(MeasurementProfile, idPerfilMedicion), "PERFIL_NO_ENCONTRADO", PROFILE_NOT_FOUND)
    _requireOperate(access)
    devices = db.scalars(select(Device).where(Device.estado == DEVICE_OPERATIVO).order_by(Device.codigoDispositivo)).all()
    return [
        DeviceSummary(idDispositivo=d.idDispositivo, codigoDispositivo=d.codigoDispositivo, nombre=d.nombre,
                      modelo=d.modelo, modeloSensor=d.modeloSensor, versionFirmware=d.versionFirmware)
        for d in devices if _deviceUsable(d, access.idInstitucion, _operatorRelation(access))
    ]


# --- Matriz y regla (modo GLUCOSA_EXPERIMENTAL) --------------------------------------------------------------
#
# La matriz la decide el backend (app/services/matrix.py): la ACTIVA y vigente de la institución del perfil y, si no
# tiene, la global; los perfiles individuales usan la global. El cliente nunca envía un idMatriz.


def _resolveGlucoseRule(db, idInstitucion, sexo, edad, condicion, minutos, today) -> tuple[Matrix, MatrixRule]:
    matrix = matrixService.resolveMatrix(db, idInstitucion, today)
    if matrix is None:
        raise _error("SIN_REGLA_APLICABLE",
                     "No hay una matriz activa y vigente para estimar glucosa: no se puede iniciar una medición de "
                     "glucosa experimental.")
    rule = matrixService.resolveRule(db, matrix.idMatriz, sexo, edad, condicion, minutos)
    if rule is None:
        raise _error(
            "SIN_REGLA_APLICABLE",
            "La matriz aplicable no tiene una regla para este perfil y contexto: no se puede iniciar una medición de "
            "glucosa experimental.",
        )
    return matrix, rule


def matrixPreview(db: Session, actor: User, idPerfilMedicion: uuid.UUID) -> MatrixSummary | None:
    """Matriz que se aplicaría a una medición de glucosa de ese perfil (informativo; solo quien opera el perfil)."""
    access = _access(db, actor, db.get(MeasurementProfile, idPerfilMedicion), "PERFIL_NO_ENCONTRADO", PROFILE_NOT_FOUND)
    _requireOperate(access)
    matrix = matrixService.resolveMatrix(db, access.idInstitucion, nowForDb().date())
    return matrixService.summary(matrix)


# --- Iniciar -------------------------------------------------------------------------------------------------


def startMeasurement(db: Session, actor: User, data: MeasurementStart, deviceSession: bool = False) -> MeasurementDetail:
    access = _access(db, actor, db.get(MeasurementProfile, data.idPerfilMedicion), "PERFIL_NO_ENCONTRADO", PROFILE_NOT_FOUND)
    _requireOperate(access)
    profile = access.profile
    _requireExperimentalConsent(db, actor, profile)
    device = db.get(Device, data.idDispositivo)
    if device is None or not _deviceUsable(device, access.idInstitucion, _operatorRelation(access)):
        raise _error("DISPOSITIVO_NO_DISPONIBLE", "El dispositivo no está disponible para medir este perfil.")

    now = nowForDb()
    snapshot = measurementSnapshot(profile, now)
    # Prioridad: informado para ESTA medición > perfil de medición (que ya toma los datos de la cuenta) > NULL.
    # Nunca se inventa un valor (ni edad 0 ni un sexo por defecto) y nunca se escribe en la cuenta ni en el perfil.
    edad = data.edadAlMomento if data.edadAlMomento is not None else snapshot.edadAlMomento
    sexo = data.sexoModelo if data.sexoModelo is not None else snapshot.sexoModelo
    minutes = None
    if data.fechaHoraUltimaComida is not None:
        if data.fechaHoraUltimaComida > now:
            raise _error("FECHA_INVALIDA", "La hora de la última comida no puede ser futura.")
        minutes = int((now - data.fechaHoraUltimaComida).total_seconds() // 60)
    matrix = None
    rule = None
    if data.modoMedicion == GLUCOSA and deviceSession:
        # Sesión con el dispositivo: el valor de glucosa lo informa el firmware (DEMO / EXPERIMENTAL) y el servidor NO estima nada, así que no se
        # exige edad, sexo ni regla. La matriz vigente se asocia solo como REFERENCIA para comparar (no participa de ningún cálculo).
        matrix = matrixService.resolveMatrix(db, access.idInstitucion, now.date())
    elif data.modoMedicion == GLUCOSA:
        # Única dependencia real: la regla de la matriz se elige por edad y sexo, y sin regla no hay estimación trazable
        # (CK_Medicion_glucosaCompletada / glucosaTrazable). No es una exigencia demográfica del formulario: la oximetría y la
        # medición con el dispositivo no los necesitan, y acá se pueden informar solo para esta medición.
        incomplete = _error(
            "DATOS_PACIENTE_INCOMPLETOS",
            "Estimación de glucosa no disponible: la regla de la matriz depende de la edad (y del sexo, si la matriz lo distingue), y sin esos datos "
            "no se puede estimar (no se inventan valores). Indicalos para esta medición, o usá oximetría o la medición con el "
            "dispositivo, que no los necesitan.")
        if edad is None:
            raise incomplete
        # La última comida es OPCIONAL: sin ella la medición se inicia igual (se adquieren SpO₂ y frecuencia cardíaca) y, si la regla de la matriz
        # para «después de comer» necesita la hora, la estimación queda no disponible (se explica al finalizar); nunca se bloquea ni se inventa.
        # Sin dato de comida, o posprandial sin hora de la última comida: la matriz vigente queda como REFERENCIA y no se elige regla
        # (la matriz ADA no fija objetivo sin saber si la medición es en ayunas/preprandial o posprandial). Nunca se inventa.
        mealMissing = data.condicionComida == "NO_INFORMADA" or (data.condicionComida == "POSTPRANDIAL" and minutes is None)
        try:
            matrix, rule = _resolveGlucoseRule(db, access.idInstitucion, sexo, edad, data.condicionComida, minutes, now.date())
        except AuthError as error:
            if mealMissing and error.code == "SIN_REGLA_APLICABLE" and matrixService.resolveMatrix(db, access.idInstitucion, now.date()) is not None:
                matrix, rule = matrixService.resolveMatrix(db, access.idInstitucion, now.date()), None
            # Sexo no informado: solo sirve una regla que no distinga sexo o la prevista para «sexo no informado»; sin ella no se inventa otra.
            elif sexo is None and error.code == "SIN_REGLA_APLICABLE":
                raise incomplete from error
            else:
                raise

    measurement = Measurement(
        idPerfilMedicion=profile.idPerfilMedicion, idDispositivo=device.idDispositivo,
        idMatriz=matrix.idMatriz if matrix else None, modoMedicion=data.modoMedicion, estadoMedicion=PENDIENTE,
        fechaHoraInicio=now, fechaHoraUltimaComida=data.fechaHoraUltimaComida, condicionComida=data.condicionComida,
        edadAlMomento=edad, sexoModelo=sexo,
        versionFirmwareAlMomento=device.versionFirmware, modeloSensorAlMomento=device.modeloSensor,
        observacion=data.observacion,
    )
    db.add(measurement)
    db.flush()
    schemaCompat.setRuleId(db, measurement.idMedicion, rule.idReglaMatriz if rule else None)  # regla aplicada; sin la columna en la base instalada no se escribe
    registerEvent(
        db, "CRUD", "INICIAR_MEDICION", True, actor.idUsuario, "Medicion", measurement.idMedicion,
        datosNuevos={"modoMedicion": data.modoMedicion, "tipoPerfil": profile.tipoPerfil,
                     "idPerfilMedicion": str(profile.idPerfilMedicion),
                     "edadInformadaEnLaMedicion": data.edadAlMomento is not None,
                     "sexoInformadoEnLaMedicion": data.sexoModelo is not None},
        tablaRelacionada="InstitucionUsuario" if access.relation else None,
        idRelacionado=access.relation.idInstitucionUsuario if access.relation else None,
    )
    db.commit()
    return _detail(db, measurement, access)


# --- Transiciones ----------------------------------------------------------------------------------------------


def _transition(db: Session, idMedicion: uuid.UUID, expected: tuple[str, ...], new: str, **values) -> bool:
    result = db.execute(
        update(Measurement)
        .where(Measurement.idMedicion == idMedicion, Measurement.estadoMedicion.in_(expected))
        .values(estadoMedicion=new, **values).execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def _stateError(measurement: Measurement) -> AuthError:
    return _error("MEDICION_ESTADO_INVALIDO",
                  f"Esta operación no corresponde a una medición en estado {measurement.estadoMedicion.lower()}.")


SAMPLES_PER_INSERT = 400  # filas por INSERT: 5 columnas × 400 = 2000 parámetros (tope de SQL Server: 2100)


def addSamples(db: Session, actor: User, idMedicion: uuid.UUID, data: SamplesRequest) -> MeasurementDetail:
    """Registra muestras de los canales rojo e infrarrojo (MuestraSensor). La primera pasa PENDIENTE → ADQUIRIENDO."""
    measurement, access = _measurementAccess(db, actor, idMedicion)
    _requireOperate(access)
    _requireExperimentalConsent(db, actor, access.profile)  # revocar frena también las muestras de una medición en curso
    if measurement.estadoMedicion not in (PENDIENTE, ADQUIRIENDO):
        raise _stateError(measurement)
    device = db.get(Device, measurement.idDispositivo)
    if device is None or device.estado != DEVICE_OPERATIVO:
        # Pasó a mantenimiento, fuera de servicio o descomisionado: no se reciben más datos (la medición se puede cancelar).
        raise _error("DISPOSITIVO_NO_DISPONIBLE", "El dispositivo ya no está operativo: no se pueden registrar más datos.")
    started = measurement.estadoMedicion == PENDIENTE
    try:
        # Condiciona al estado: una cancelación o cierre simultáneo gana y las muestras no se insertan.
        if not _transition(db, idMedicion, (PENDIENTE, ADQUIRIENDO), ADQUIRIENDO):
            db.rollback()
            raise _stateError(measurement)
        # Un INSERT de varias filas por tanda (no uno por muestra): el ORM no puede agrupar estos INSERT porque la clave la genera el servidor
        # (newsequentialid(), que se conserva a propósito para no fragmentar el índice agrupado) y los ejecutaba uno a uno (400 muestras = 400 viajes).
        # 5 parámetros por fila × 400 = 2000, por debajo de los 2100 que admite SQL Server. Misma transacción: atomicidad y UQ_MuestraSensor_orden intactas.
        table = SensorSample.__table__
        rows = [{"idMedicion": idMedicion, "numeroMuestra": s.numeroMuestra, "tiempoRelativoMs": s.tiempoRelativoMs,
                 "valorRed": s.valorRed, "valorIR": s.valorIR} for s in data.muestras]
        for start in range(0, len(rows), SAMPLES_PER_INSERT):
            db.execute(insert(table).values(rows[start:start + SAMPLES_PER_INSERT]))
        if started:
            registerEvent(db, "CRUD", "CAMBIAR_ESTADO_MEDICION", True, actor.idUsuario, "Medicion", idMedicion,
                          datosPrevios={"estadoMedicion": PENDIENTE}, datosNuevos={"estadoMedicion": ADQUIRIENDO})
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _error("MUESTRAS_DUPLICADAS", "Alguna muestra ya estaba registrada para esta medición.") from error
    db.expire_all()
    return _detail(db, db.get(Measurement, idMedicion), access)


def cancelMeasurement(db: Session, actor: User, idMedicion: uuid.UUID, operation: str = "MEDICION") -> MeasurementDetail:
    measurement, access = _measurementAccess(db, actor, idMedicion)
    _requireOperate(access)
    previous = measurement.estadoMedicion
    if previous not in (PENDIENTE, ADQUIRIENDO):
        raise _stateError(measurement)
    end = _endTime(measurement)
    if not _transition(db, idMedicion, (PENDIENTE, ADQUIRIENDO), CANCELADA, fechaHoraFin=end):
        db.rollback()
        raise _stateError(measurement)
    registerEvent(db, "CRUD", "CANCELAR_MEDICION", True, actor.idUsuario, "Medicion", idMedicion,
                  datosPrevios={"estadoMedicion": previous}, datosNuevos={"estadoMedicion": CANCELADA, "motivo": "CANCELADA_POR_USUARIO"})
    technicalAudit.record(db, measurement, CANCELADA, "CANCELADA_POR_USUARIO", operation=operation, end=end)
    db.commit()
    db.expire_all()
    return _detail(db, db.get(Measurement, idMedicion), access)


def cancelAbandoned(db: Session, idMedicion: uuid.UUID, idUsuario: uuid.UUID | None, reason: str) -> bool:
    """Cierra como CANCELADA la medición de una sesión del dispositivo que quedó sin dueño (abandonada, vencida o con cierre de sesión).
    No exige actor: lo dispara el sistema. Solo toca una medición todavía en curso (nunca una completada) y deja auditoría."""
    measurement = db.get(Measurement, idMedicion)
    if measurement is None or measurement.estadoMedicion not in (PENDIENTE, ADQUIRIENDO):
        return False
    note = " ".join(part for part in (measurement.observacion, "Sesión cancelada automáticamente: quedó sin uso.") if part)[:500]
    if not _transition(db, idMedicion, (PENDIENTE, ADQUIRIENDO), CANCELADA, fechaHoraFin=_endTime(measurement), observacion=note):
        db.rollback()
        return False
    registerEvent(db, "CRUD", "CANCELAR_SESION_ABANDONADA", True, idUsuario, "Medicion", idMedicion,
                  datosPrevios={"estadoMedicion": measurement.estadoMedicion}, datosNuevos={"estadoMedicion": CANCELADA, "motivo": reason})
    technicalAudit.record(db, measurement, CANCELADA, {"EXPIRADA": "SESION_EXPIRADA", "ABANDONADA": "SESION_ABANDONADA"}.get(reason, reason),
                          operation="SESION_DISPOSITIVO")
    db.commit()
    return True


def _endTime(measurement: Measurement) -> datetime:
    return max(nowForDb(), measurement.fechaHoraInicio)  # CK_Medicion_fechas: fin >= inicio


@dataclass(frozen=True)
class Outcome:
    valid: bool
    spo2: Decimal | None = None
    frecuenciaCardiaca: int | None = None
    calidadSenal: Decimal | None = None
    glucosa: Decimal | None = None
    versionAlgoritmo: str | None = None
    reason: str | None = None


SENSOR_BITS = {"MAX30100": 16, "MAX30102": 18}


def _analyze(db: Session, measurement: Measurement) -> oximetry.OximetryResult:
    """SpO₂ y frecuencia cardíaca calculadas por el servidor sobre las muestras guardadas (única fuente de estos valores)."""
    rows = db.execute(
        select(SensorSample.tiempoRelativoMs, SensorSample.valorRed, SensorSample.valorIR)
        .where(SensorSample.idMedicion == measurement.idMedicion).order_by(SensorSample.numeroMuestra)).all()
    return oximetry.analyze([(r[0], r[1], r[2]) for r in rows], bits=SENSOR_BITS.get(measurement.modeloSensorAlMomento or ""))


def _process(db: Session, measurement: Measurement, access: ProfileAccess, data: MeasurementFinish) -> Outcome:
    """Procesa según el modo sobre la señal adquirida. No inventa resultados: sin señal válida o sin algoritmo
    devuelve un resultado inválido con su motivo. Los valores que informe el cliente se ignoran."""
    signal = _analyze(db, measurement)
    if measurement.modoMedicion == OXIMETRIA:
        if not signal.ok:
            return Outcome(False, calidadSenal=Decimal(str(signal.quality)) if signal.quality is not None else None,
                           reason=signal.reason)
        # La oximetría nunca guarda glucosa estimada (CK_Medicion_oximetriaSinGlucosa).
        return Outcome(True, Decimal(str(signal.spo2)), signal.heartRate, Decimal(str(signal.quality)), None, signal.version)
    data = MeasurementFinish(
        spo2=Decimal(str(signal.spo2)) if signal.ok else None, frecuenciaCardiaca=signal.heartRate if signal.ok else None,
        calidadSenal=Decimal(str(signal.quality)) if signal.quality is not None else None, observacion=data.observacion)

    matrix = db.get(Matrix, measurement.idMatriz) if measurement.idMatriz else None
    minutes = None
    if measurement.fechaHoraUltimaComida is not None:
        minutes = int((measurement.fechaHoraInicio - measurement.fechaHoraUltimaComida).total_seconds() // 60)
    rule = (matrixService.resolveRule(db, matrix.idMatriz, measurement.sexoModelo, measurement.edadAlMomento,
                                      measurement.condicionComida, minutes) if matrix else None)
    if matrix is None or rule is None:
        if measurement.condicionComida == "POSTPRANDIAL" and minutes is None:
            reason = ("Estimación de glucosa no disponible por falta de información: no se indicó la hora de la última comida, que la regla de la matriz "
                      "necesita para medir después de comer. Se guardaron SpO₂ y frecuencia cardíaca; no se generó ningún valor de glucosa.")
        elif measurement.condicionComida == "NO_INFORMADA":
            reason = ("Estimación de glucosa no disponible: sin dato de comida (ayuno o posprandial) la matriz no fija un objetivo. Se guardaron "
                      "SpO₂ y frecuencia cardíaca; no se generó ningún valor de glucosa.")
        else:
            reason = "No hay una regla de matriz aplicable: no se estimó la glucosa."
        return Outcome(False, data.spo2, data.frecuenciaCardiaca, data.calidadSenal, reason=reason)
    estimator = glucoseEstimator
    if estimator is None:
        return Outcome(False, data.spo2, data.frecuenciaCardiaca, data.calidadSenal,
                       reason="El algoritmo de estimación de glucosa todavía no está disponible: no se generó ningún valor.")
    samples = [(r.valorRed, r.valorIR) for r in db.execute(
        select(SensorSample.valorRed, SensorSample.valorIR).where(SensorSample.idMedicion == measurement.idMedicion)
        .order_by(SensorSample.numeroMuestra)).all()]
    estimate = estimator(samples, rule, matrix, measurement.edadAlMomento, measurement.sexoModelo)
    if estimate is None or estimate[0] is None or estimate[0] < 0:
        return Outcome(False, data.spo2, data.frecuenciaCardiaca, data.calidadSenal,
                       reason="Los datos adquiridos no alcanzaron para estimar la glucosa.")
    value, version = estimate
    return Outcome(True, data.spo2, data.frecuenciaCardiaca, data.calidadSenal, Decimal(value), version)


def finishMeasurement(db: Session, actor: User, idMedicion: uuid.UUID, data: MeasurementFinish) -> MeasurementDetail:
    """ADQUIRIENDO → PROCESANDO → COMPLETADA | INVALIDA. COMPLETADA se escribe junto con los resultados."""
    measurement, access = _measurementAccess(db, actor, idMedicion)
    _requireOperate(access)
    if measurement.estadoMedicion != ADQUIRIENDO:
        raise _stateError(measurement)
    if not db.scalar(select(func.count()).select_from(SensorSample).where(SensorSample.idMedicion == idMedicion)):
        raise _error("MUESTRAS_INSUFICIENTES", "Todavía no hay muestras registradas para procesar esta medición.")
    if not _transition(db, idMedicion, (ADQUIRIENDO,), PROCESANDO):
        db.rollback()
        raise _stateError(measurement)
    registerEvent(db, "CRUD", "CAMBIAR_ESTADO_MEDICION", True, actor.idUsuario, "Medicion", idMedicion,
                  datosPrevios={"estadoMedicion": ADQUIRIENDO}, datosNuevos={"estadoMedicion": PROCESANDO})
    db.commit()

    db.expire_all()
    measurement = db.get(Measurement, idMedicion)
    outcome = _process(db, measurement, access, data)
    final = COMPLETADA if outcome.valid else INVALIDA
    note = " ".join(part for part in (data.observacion or measurement.observacion, outcome.reason) if part) or None
    end = _endTime(measurement)
    if not _transition(
        db, idMedicion, (PROCESANDO,), final, fechaHoraFin=end, spo2=outcome.spo2,
        frecuenciaCardiaca=outcome.frecuenciaCardiaca, calidadSenal=outcome.calidadSenal,
        glucosaEstimada=outcome.glucosa, versionAlgoritmo=outcome.versionAlgoritmo, observacion=note[:500] if note else None,
    ):
        db.rollback()
        raise _stateError(measurement)
    if final == COMPLETADA:
        db.execute(
            update(MeasurementProfile)
            .where(MeasurementProfile.idPerfilMedicion == measurement.idPerfilMedicion,
                   or_(MeasurementProfile.fechaUltimaMedicion.is_(None), MeasurementProfile.fechaUltimaMedicion < end))
            .values(fechaUltimaMedicion=end).execution_options(synchronize_session=False)
        )
    registerEvent(db, "CRUD", "FINALIZAR_MEDICION", final == COMPLETADA, actor.idUsuario, "Medicion", idMedicion,
                  datosPrevios={"estadoMedicion": PROCESANDO},
                  datosNuevos={"estadoMedicion": final, **({} if final == COMPLETADA else {"motivo": "LECTURA_NO_VALIDA"})},
                  observacion=outcome.reason)
    if final == INVALIDA:
        technicalAudit.record(db, measurement, INVALIDA, "LECTURA_NO_VALIDA", end=end)
    db.commit()
    if final == COMPLETADA:
        # Solo quién y cuándo, nunca el valor; únicamente si la persona lo autorizó en su grupo.
        owner = db.scalar(select(MeasurementProfile.idUsuario).where(
            MeasurementProfile.idPerfilMedicion == measurement.idPerfilMedicion))
        ownerUser = db.get(User, owner) if owner is not None else None
        if ownerUser is not None:
            notifications.notifyGroupMeasurement(db, ownerUser, end)
    # Cada medición completada de un paciente institucional con correo cargado y vigente envía su resultado (como al guardar con el dispositivo).
    autoSend = None
    if final == COMPLETADA:
        try:
            autoSend = autoSendResult(db, actor, idMedicion)
        except Exception:  # noqa: BLE001 - el correo nunca deshace una medición ya confirmada
            logging.getLogger(__name__).exception("No se pudo enviar el resultado automático (medición %s)", idMedicion)
            db.rollback()
            autoSend = "FALLIDO"
    db.expire_all()
    detail = _detail(db, db.get(Measurement, idMedicion), access)
    detail.envioAutomatico = autoSend
    return detail


# --- Referencia capilar ----------------------------------------------------------------------------------------


def registerCapillaryReference(db: Session, actor: User, idMedicion: uuid.UUID,
                               data: CapillaryReferenceRequest) -> MeasurementDetail:
    """Valor real de un glucómetro capilar asociado a una medición de glucosa COMPLETADA. Queda separado de
    glucosaEstimada (nunca la reemplaza) y se carga a mano: no se genera ni se deduce."""
    measurement, access = _measurementAccess(db, actor, idMedicion)
    _requireOperate(access)
    if measurement.modoMedicion != GLUCOSA or measurement.estadoMedicion != COMPLETADA:
        raise _error("MEDICION_ESTADO_INVALIDO",
                     "La referencia capilar solo se registra sobre una medición de glucosa experimental completada.")
    if data.fechaHoraReferencia > nowForDb():
        raise _error("FECHA_INVALIDA", "La fecha de la referencia capilar no puede ser futura.")
    try:
        db.add(CapillaryReferenceMeasurement(
            idMedicion=idMedicion, glucosaReferencia=data.glucosaReferencia,
            fechaHoraReferencia=data.fechaHoraReferencia, marcaGlucometro=data.marcaGlucometro,
            modeloGlucometro=data.modeloGlucometro, observacion=data.observacion,
        ))
        registerEvent(db, "CRUD", "REGISTRAR_REFERENCIA_CAPILAR", True, actor.idUsuario, "Medicion", idMedicion)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _error("REFERENCIA_EXISTENTE", "Esta medición ya tiene una referencia capilar registrada.") from error
    db.expire_all()
    return _detail(db, db.get(Measurement, idMedicion), access)


# --- Consulta ------------------------------------------------------------------------------------------------


def _detail(db: Session, measurement: Measurement, access: ProfileAccess) -> MeasurementDetail:
    visibleHasta = visibleUntil(measurement) if access.profile.tipoPerfil == TIPO_CONSUMIDOR_FINAL else None
    device = db.get(Device, measurement.idDispositivo)
    matrix = db.get(Matrix, measurement.idMatriz) if measurement.idMatriz else None
    reference = db.scalar(select(CapillaryReferenceMeasurement).where(
        CapillaryReferenceMeasurement.idMedicion == measurement.idMedicion))
    samples = db.scalar(select(func.count()).select_from(SensorSample).where(
        SensorSample.idMedicion == measurement.idMedicion))
    return MeasurementDetail(
        idMedicion=measurement.idMedicion, idPerfilMedicion=measurement.idPerfilMedicion,
        modoMedicion=measurement.modoMedicion, estadoMedicion=measurement.estadoMedicion,
        fechaHoraInicio=measurement.fechaHoraInicio, fechaHoraFin=measurement.fechaHoraFin,
        fechaHoraUltimaComida=measurement.fechaHoraUltimaComida, condicionComida=measurement.condicionComida,
        minutosDesdeUltimaComida=(
            int((measurement.fechaHoraInicio - measurement.fechaHoraUltimaComida).total_seconds() // 60)
            if measurement.fechaHoraUltimaComida else None),
        duracionMs=(int((measurement.fechaHoraFin - measurement.fechaHoraInicio) / timedelta(milliseconds=1))
                    if measurement.fechaHoraFin else None),
        edadAlMomento=measurement.edadAlMomento, sexoModelo=measurement.sexoModelo,
        versionFirmwareAlMomento=measurement.versionFirmwareAlMomento, modeloSensorAlMomento=measurement.modeloSensorAlMomento,
        versionAlgoritmo=measurement.versionAlgoritmo, calidadSenal=measurement.calidadSenal, spo2=measurement.spo2,
        frecuenciaCardiaca=measurement.frecuenciaCardiaca, glucosaEstimada=measurement.glucosaEstimada,
        observacion=measurement.observacion,
        origenGlucosa=measurement.origenGlucosa, glucosaDispositivo=measurement.glucosaDispositivo,
        unidadGlucosa=measurement.unidadGlucosa, indiceOptico=measurement.indiceOptico,
        lecturasEstabilizadas=measurement.lecturasEstabilizadas, esDemo=measurement.origenGlucosa == ORIGEN_DEMO,
        puedeEliminar=bool(access.canOperate and measurement.origenGlucosa == ORIGEN_DEMO
                           and measurement.estadoMedicion == COMPLETADA),
        dispositivo=DeviceSummary(
            idDispositivo=device.idDispositivo, codigoDispositivo=device.codigoDispositivo, nombre=device.nombre,
            modelo=device.modelo, modeloSensor=device.modeloSensor, versionFirmware=device.versionFirmware),
        matriz=MatrixSummary(idMatriz=matrix.idMatriz, nombre=matrix.nombre, version=matrix.version,
                             ambito=matrix.ambito) if matrix else None,
        cantidadMuestras=samples,
        referenciaCapilar=CapillaryReferenceMeasurementRead.model_validate(reference) if reference else None,
        puedeOperar=access.canOperate and (
            measurement.estadoMedicion in (PENDIENTE, ADQUIRIENDO)
            or (measurement.estadoMedicion == COMPLETADA and measurement.modoMedicion == GLUCOSA)),
        envioResultado=(("PACIENTE" if access.idInstitucion else "CUENTA_PROPIA")
                        if access.canOperate and measurement.estadoMedicion == COMPLETADA
                        and measurement.origenGlucosa != ORIGEN_DEMO else None),
        visibleHasta=visibleHasta,
        referenciaGlucosa=glucoseReference.build(db, measurement) if measurement.modoMedicion == GLUCOSA else None,
    )


def getMeasurement(db: Session, actor: User, idMedicion: uuid.UUID) -> MeasurementDetail:
    measurement, access = _measurementAccess(db, actor, idMedicion)
    return _detail(db, measurement, access)


def _history(db: Session, idPerfilMedicion: uuid.UUID, *, desde: date | None, hasta: date | None, modo: str | None,
             estado: str | None, orden: str, pagina: int, tamanioPagina: int, origen: str | None = None,
             hideExpired: bool = False) -> MeasurementPage:
    if modo is not None and modo not in (OXIMETRIA, GLUCOSA):
        raise _error("DATOS_INVALIDOS", "El modo de medición no es válido.")
    if estado is not None and estado not in (PENDIENTE, ADQUIRIENDO, PROCESANDO, COMPLETADA, INVALIDA, CANCELADA):
        raise _error("DATOS_INVALIDOS", "El estado de la medición no es válido.")
    if origen is not None and origen not in (ORIGEN_DEMO, "REAL"):
        raise _error("DATOS_INVALIDOS", "El origen de los datos no es válido.")
    if desde and hasta and hasta < desde:
        raise _error("PERIODO_INVALIDO", "La fecha final no puede ser anterior a la inicial.")
    tamanioPagina = max(1, min(tamanioPagina, MAX_PAGE_SIZE))
    pagina = max(1, pagina)
    query = select(Measurement).where(Measurement.idPerfilMedicion == idPerfilMedicion)
    if hideExpired:  # vista personal: las canceladas/inválidas vencidas ya no se ven
        query = query.where(not_(hiddenCondition(nowForDb())))
    if desde:
        query = query.where(Measurement.fechaHoraInicio >= datetime.combine(desde, datetime.min.time()))
    if hasta:
        query = query.where(Measurement.fechaHoraInicio < datetime.combine(hasta + timedelta(days=1), datetime.min.time()))
    if modo:
        query = query.where(Measurement.modoMedicion == modo)
    if estado:
        query = query.where(Measurement.estadoMedicion == estado)
    if origen == ORIGEN_DEMO:  # datos de prueba
        query = query.where(Measurement.origenGlucosa == ORIGEN_DEMO)
    elif origen == "REAL":  # todo lo que no es DEMO
        query = query.where(NOT_DEMO)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    order = Measurement.fechaHoraInicio.asc() if orden == "asc" else Measurement.fechaHoraInicio.desc()
    rows = db.scalars(query.order_by(order, Measurement.idMedicion).offset((pagina - 1) * tamanioPagina)
                      .limit(tamanioPagina)).all()
    codes = {d.idDispositivo: d.codigoDispositivo for d in db.scalars(
        select(Device).where(Device.idDispositivo.in_({r.idDispositivo for r in rows}))).all()} if rows else {}
    items = [
        MeasurementListItem(
            idMedicion=r.idMedicion, fechaHoraInicio=r.fechaHoraInicio, fechaHoraFin=r.fechaHoraFin,
            modoMedicion=r.modoMedicion, estadoMedicion=r.estadoMedicion, condicionComida=r.condicionComida,
            fechaHoraUltimaComida=r.fechaHoraUltimaComida, edadAlMomento=r.edadAlMomento, glucosaEstimada=r.glucosaEstimada, spo2=r.spo2,
            frecuenciaCardiaca=r.frecuenciaCardiaca, calidadSenal=r.calidadSenal, observacion=r.observacion,
            dispositivo=codes.get(r.idDispositivo), origenGlucosa=r.origenGlucosa,
            glucosaDispositivo=r.glucosaDispositivo, indiceOptico=r.indiceOptico, esDemo=r.origenGlucosa == ORIGEN_DEMO,
            visibleHasta=visibleUntil(r) if hideExpired else None,
        )
        for r in rows
    ]
    return MeasurementPage(items=items, total=total, pagina=pagina, tamanioPagina=tamanioPagina)


def listOwnHistory(db: Session, actor: User, *, desde=None, hasta=None, modo=None, estado=None, orden="desc",
                   pagina=1, tamanioPagina=20, origen=None) -> MeasurementPage:
    profile = getConsumerProfile(db, actor) if actor.tipoCuenta == TIPO_CONSUMIDOR_FINAL else None
    if profile is None:
        return MeasurementPage(items=[], total=0, pagina=1, tamanioPagina=tamanioPagina)
    return _history(db, profile.idPerfilMedicion, desde=desde, hasta=hasta, modo=modo, estado=estado, orden=orden,
                    pagina=pagina, tamanioPagina=tamanioPagina, origen=origen, hideExpired=True)


def requireClinicalAccess(db: Session, actor: User, idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, operation: str = "HISTORIAL"):
    """Mediciones individuales de un paciente (historial, estadísticas, dashboard): SOLO el operador responsable vigente. Propietario
    y moderador no acceden por su rol. Un paciente de otra institución responde como inexistente."""
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_PACIENTES)
    row = patients._load(db, idInstitucion, idPerfilMedicion)
    profile = row[0]
    patientAccess.requireMeasurementAccess(db, actor, membership, profile, operation)
    return membership, profile


def listPatientHistory(db: Session, actor: User, idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, *, desde=None,
                       hasta=None, modo=None, estado=None, orden="desc", pagina=1, tamanioPagina=20,
                       origen=None) -> MeasurementPage:
    """Historial de un paciente: solo su operador responsable vigente (el paciente debe ser de esa institución)."""
    requireClinicalAccess(db, actor, idInstitucion, idPerfilMedicion, "HISTORIAL")
    return _history(db, idPerfilMedicion, desde=desde, hasta=hasta, modo=modo, estado=estado, orden=orden,
                    pagina=pagina, tamanioPagina=tamanioPagina, origen=origen)


# --- Datos de prueba (DEMO) --------------------------------------------------------------------------------------


def _deleteDemo(db: Session, ids: list[uuid.UUID]) -> int:
    """Borra mediciones DEMO COMPLETADAS (y lo que cuelga de ellas). Cada DELETE se condiciona al origen: una
    medición real nunca se elimina aunque el identificador sea otro."""
    if not ids:
        return 0
    db.execute(delete(ResultDelivery).where(ResultDelivery.idMedicion.in_(ids)))
    db.execute(delete(SensorSample).where(SensorSample.idMedicion.in_(ids)))
    db.execute(delete(CapillaryReferenceMeasurement).where(CapillaryReferenceMeasurement.idMedicion.in_(ids)))
    return db.execute(delete(Measurement).where(
        Measurement.idMedicion.in_(ids), Measurement.origenGlucosa == ORIGEN_DEMO,
        Measurement.estadoMedicion == COMPLETADA).execution_options(synchronize_session=False)).rowcount


def deleteDemoMeasurement(db: Session, actor: User, idMedicion: uuid.UUID) -> int:
    """Elimina UNA medición de prueba que la cuenta puede operar. Una medición real responde 409."""
    measurement, access = _measurementAccess(db, actor, idMedicion)
    _requireOperate(access)
    if measurement.origenGlucosa != ORIGEN_DEMO or measurement.estadoMedicion != COMPLETADA:
        raise _error("DATO_NO_ELIMINABLE", "Solo se pueden eliminar mediciones de prueba (DEMO) completadas.")
    deleted = _deleteDemo(db, [idMedicion])
    registerEvent(db, "CRUD", "ELIMINAR_DATOS_DEMO", deleted == 1, actor.idUsuario, "Medicion", idMedicion,
                  datosNuevos={"cantidad": deleted},
                  tablaRelacionada="InstitucionUsuario" if access.relation else None,
                  idRelacionado=access.relation.idInstitucionUsuario if access.relation else None)
    db.commit()
    return deleted


def deleteOwnDemoMeasurements(db: Session, actor: User) -> int:
    """Elimina todas las mediciones de prueba del perfil propio (cuenta individual). No toca las reales."""
    profile = getConsumerProfile(db, actor) if actor.tipoCuenta == TIPO_CONSUMIDOR_FINAL else None
    if profile is None:
        return 0
    ids = list(db.scalars(select(Measurement.idMedicion).where(
        Measurement.idPerfilMedicion == profile.idPerfilMedicion, Measurement.origenGlucosa == ORIGEN_DEMO,
        Measurement.estadoMedicion == COMPLETADA)).all())
    deleted = _deleteDemo(db, ids)
    registerEvent(db, "CRUD", "ELIMINAR_DATOS_DEMO", True, actor.idUsuario, "PerfilMedicion", profile.idPerfilMedicion,
                  datosNuevos={"cantidad": deleted})
    db.commit()
    return deleted


# --- Estadísticas ----------------------------------------------------------------------------------------------


def _summary(values: list[float]) -> MetricSummary:
    if not values:
        return MetricSummary(cantidad=0, promedio=None, minimo=None, maximo=None)
    return MetricSummary(cantidad=len(values), promedio=round(sum(values) / len(values), 1),
                         minimo=min(values), maximo=max(values))


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def buildStatistics(db: Session, idPerfilMedicion: uuid.UUID | None, dias: int, *, desde: date | None = None,
                    hasta: date | None = None, profileIds=None, minPatientsPerDay: int = 0) -> SharedStatisticsRead:
    """Promedios, mínimos, máximos y serie diaria sobre mediciones COMPLETADA (las inválidas/canceladas no cuentan).
    Sin `desde`/`hasta`, los últimos `dias`. Es el cálculo único que usan el perfil propio, el paciente institucional
    y los grupos familiares (cada uno autoriza por su cuenta antes de llamarlo). `profileIds` (lista o subconsulta)
    agrupa varios perfiles para los dashboards institucional y familiar. `minPatientsPerDay` (> 0, vistas administrativas): la
    serie diaria omite los días con menos pacientes distintos que ese mínimo, porque con un solo paciente el promedio del día ES
    su medición individual."""
    query = select(Measurement.idPerfilMedicion, Measurement.fechaHoraInicio, Measurement.glucosaEstimada, Measurement.spo2,
                   Measurement.frecuenciaCardiaca).where(
        Measurement.idPerfilMedicion.in_(profileIds) if profileIds is not None else Measurement.idPerfilMedicion == idPerfilMedicion,
        Measurement.estadoMedicion == COMPLETADA, NOT_DEMO)
    if desde or hasta:
        if desde:
            query = query.where(Measurement.fechaHoraInicio >= datetime.combine(desde, datetime.min.time()))
        if hasta:
            query = query.where(Measurement.fechaHoraInicio < datetime.combine(hasta + timedelta(days=1), datetime.min.time()))
    else:
        query = query.where(Measurement.fechaHoraInicio >= nowForDb() - timedelta(days=dias))
    rows = db.execute(query).all()
    byDay: dict = {}
    for r in rows:
        byDay.setdefault(r.fechaHoraInicio.date(), []).append(r)
    series = [
        DailyPoint(
            fecha=day, mediciones=len(items),
            glucosaPromedio=_average([float(i.glucosaEstimada) for i in items if i.glucosaEstimada is not None]),
            spo2Promedio=_average([float(i.spo2) for i in items if i.spo2 is not None]),
            frecuenciaPromedio=_average([float(i.frecuenciaCardiaca) for i in items if i.frecuenciaCardiaca is not None]),
        )
        for day, items in sorted(byDay.items())
        if len({i.idPerfilMedicion for i in items}) >= minPatientsPerDay
    ]
    return SharedStatisticsRead(
        dias=dias, cantidadMediciones=len(rows),
        glucosa=_summary([float(r.glucosaEstimada) for r in rows if r.glucosaEstimada is not None]),
        spo2=_summary([float(r.spo2) for r in rows if r.spo2 is not None]),
        frecuenciaCardiaca=_summary([float(r.frecuenciaCardiaca) for r in rows if r.frecuenciaCardiaca is not None]),
        serieDiaria=series,
    )


EVOLUTION_DAYS = (1, 7, 14, 30, 90)  # 1 = últimas 24 horas
MAX_EVOLUTION_POINTS = 1000


def _evolutionGlucose(row: Measurement) -> float | None:
    """Glucosa de una medición: la estimada (matriz) o la que informa el dispositivo SOLO si su origen es EXPERIMENTAL o DEMO.
    SIN_CALIBRAR no tiene valor y nunca se toma como glucosa validada."""
    if row.glucosaEstimada is not None:
        return float(row.glucosaEstimada)
    if row.glucosaDispositivo is not None and row.origenGlucosa in (ORIGEN_DEMO, "EXPERIMENTAL"):
        return float(row.glucosaDispositivo)
    return None


def _evolutionStat(pairs: list[tuple[datetime, float]]) -> EvolutionStat:
    if not pairs:
        return EvolutionStat(cantidad=0, ultimo=None, promedio=None, minimo=None, maximo=None)
    values = [value for _, value in pairs]
    latest = max(pairs, key=lambda pair: pair[0])
    return EvolutionStat(cantidad=len(values), ultimo=EvolutionLast(valor=latest[1], fecha=latest[0]),
                         promedio=round(sum(values) / len(values), 2), minimo=min(values), maximo=max(values))


def _evolutionStats(points: list[EvolutionPoint]) -> EvolutionStats:
    def pairs(field: str) -> list[tuple[datetime, float]]:
        return [(p.fecha, float(getattr(p, field))) for p in points if getattr(p, field) is not None]

    return EvolutionStats(mediciones=len(points), frecuenciaCardiaca=_evolutionStat(pairs("frecuenciaCardiaca")),
                          spo2=_evolutionStat(pairs("spo2")), glucosa=_evolutionStat(pairs("glucosa")),
                          indiceOptico=_evolutionStat(pairs("indiceOptico")), calidadSenal=_evolutionStat(pairs("calidadSenal")))


def _evolution(db: Session, idPerfilMedicion: uuid.UUID | None, dias: int, desde: date | None, hasta: date | None, origen: str,
               modo: str | None) -> EvolutionRead:
    """Evolución de UN perfil (el llamador ya autorizó el acceso): cada medición COMPLETADA es un punto con TODOS sus valores
    registrados, sin importar el modo (una oximetría puede traer glucosa y una de glucosa, SpO₂). `origen`: EXPERIMENTAL (todo lo que no
    es DEMO), DEMO o TODOS (ambos, con estadísticas SEPARADAS: nunca promedios mezclados). Sin datos devuelve listas vacías y
    estadísticas con `null` (nunca ceros)."""
    if origen not in ("EXPERIMENTAL", ORIGEN_DEMO, "TODOS"):
        raise _error("DATOS_INVALIDOS", "El origen de los datos no es válido.")
    if modo not in (None, "OXIMETRIA", "GLUCOSA_EXPERIMENTAL"):
        raise _error("DATOS_INVALIDOS", "El modo de medición no es válido.")
    if desde or hasta:
        if desde and hasta and hasta < desde:
            raise _error("PERIODO_INVALIDO", "La fecha final no puede ser anterior a la inicial.")
        start = datetime.combine(desde, datetime.min.time()) if desde else None
        end = datetime.combine(hasta + timedelta(days=1), datetime.min.time()) if hasta else None
    elif dias in EVOLUTION_DAYS:
        start, end = nowForDb() - timedelta(days=dias), None
    else:
        raise _error("PERIODO_INVALIDO", "El período debe ser de 24 horas, 7, 14, 30 o 90 días, o un rango de fechas.")
    points: list[EvolutionPoint] = []
    truncated = False
    summary = EvolutionSummary(total=0, experimentales=0, demo=0, porModo={"OXIMETRIA": 0, "GLUCOSA_EXPERIMENTAL": 0}, ultima=None)
    if idPerfilMedicion is not None:
        base = [Measurement.idPerfilMedicion == idPerfilMedicion, Measurement.estadoMedicion == COMPLETADA]
        if start is not None:
            base.append(Measurement.fechaHoraInicio >= start)
        if end is not None:
            base.append(Measurement.fechaHoraInicio < end)
        if modo is not None:
            base.append(Measurement.modoMedicion == modo)
        query = select(Measurement).where(*base)
        if origen == "EXPERIMENTAL":
            query = query.where(NOT_DEMO)
        elif origen == ORIGEN_DEMO:
            query = query.where(Measurement.origenGlucosa == ORIGEN_DEMO)
        rows = db.scalars(query.order_by(Measurement.fechaHoraInicio.desc(), Measurement.idMedicion)
                          .limit(MAX_EVOLUTION_POINTS + 1)).all()
        truncated = len(rows) > MAX_EVOLUTION_POINTS
        for row in reversed(rows[:MAX_EVOLUTION_POINTS]):
            demo = row.origenGlucosa == ORIGEN_DEMO
            points.append(EvolutionPoint(
                idMedicion=row.idMedicion, fecha=row.fechaHoraInicio, modoMedicion=row.modoMedicion,
                origen=row.origenGlucosa or ("EXPERIMENTAL" if row.glucosaEstimada is not None else None), esDemo=demo,
                frecuenciaCardiaca=row.frecuenciaCardiaca, spo2=float(row.spo2) if row.spo2 is not None else None,
                glucosa=_evolutionGlucose(row), indiceOptico=float(row.indiceOptico) if row.indiceOptico is not None else None,
                calidadSenal=float(row.calidadSenal) if row.calidadSenal is not None else None))
        # Se agrupa por columnas simples (SQL Server no admite agrupar ni seleccionar una comparación) y lo DEMO se resuelve acá.
        grouped = db.execute(select(Measurement.origenGlucosa, Measurement.modoMedicion, func.count()).where(*base)
                             .group_by(Measurement.origenGlucosa, Measurement.modoMedicion)).all()
        counts = [(origin == ORIGEN_DEMO, mode, amount) for origin, mode, amount in grouped]
        byMode = {"OXIMETRIA": 0, "GLUCOSA_EXPERIMENTAL": 0}
        for _, mode, amount in counts:
            byMode[mode] = byMode.get(mode, 0) + amount
        latest = db.execute(select(Measurement.fechaHoraInicio, Measurement.modoMedicion, Measurement.origenGlucosa)
                            .where(Measurement.idPerfilMedicion == idPerfilMedicion, Measurement.estadoMedicion == COMPLETADA)
                            .order_by(Measurement.fechaHoraInicio.desc()).limit(1)).first()
        summary = EvolutionSummary(
            total=sum(amount for _, _, amount in counts), experimentales=sum(amount for flag, _, amount in counts if not flag),
            demo=sum(amount for flag, _, amount in counts if flag), porModo=byMode,
            ultima=None if latest is None else EvolutionLastMeasurement(fecha=latest[0], modoMedicion=latest[1], esDemo=latest[2] == ORIGEN_DEMO))
    experimental = [p for p in points if not p.esDemo]
    demo = [p for p in points if p.esDemo]
    return EvolutionRead(
        origen=origen, desde=start, hasta=end, puntos=points, truncado=truncated, resumen=summary,
        estadisticas=EvolutionBlock(experimental=_evolutionStats(experimental) if origen in ("EXPERIMENTAL", "TODOS") else None,
                                    demo=_evolutionStats(demo) if origen in (ORIGEN_DEMO, "TODOS") else None))


def ownEvolution(db: Session, actor: User, dias: int = 30, desde: date | None = None, hasta: date | None = None,
                 origen: str = "EXPERIMENTAL", modo: str | None = None) -> EvolutionRead:
    """Evolución histórica de MI perfil. Período: 1 (24 h), 7, 14, 30 o 90 días, o desde/hasta."""
    profile = getConsumerProfile(db, actor) if actor.tipoCuenta == TIPO_CONSUMIDOR_FINAL else None
    return _evolution(db, profile.idPerfilMedicion if profile is not None else None, dias, desde, hasta, origen, modo)


def patientEvolution(db: Session, actor: User, idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, dias: int = 30,
                     desde: date | None = None, hasta: date | None = None, origen: str = "TODOS", modo: str | None = None) -> EvolutionRead:
    """Evolución de UN paciente: solo su operador responsable vigente (misma regla que el historial). Incluye las mediciones DEMO,
    siempre identificadas y con estadísticas aparte de las experimentales."""
    requireClinicalAccess(db, actor, idInstitucion, idPerfilMedicion, "EVOLUCION")
    return _evolution(db, idPerfilMedicion, dias, desde, hasta, origen, modo)


def _checkPeriod(dias: int, desde: date | None, hasta: date | None) -> None:
    """Un rango explícito (desde/hasta) reemplaza a «últimos N días»; sin rango, N debe ser 7, 30 o 90."""
    if desde or hasta:
        if desde and hasta and hasta < desde:
            raise _error("PERIODO_INVALIDO", "La fecha final no puede ser anterior a la inicial.")
    elif dias not in STATISTICS_DAYS:
        raise _error("PERIODO_INVALIDO", "El período debe ser de 7, 30 o 90 días.")


def ownStatistics(db: Session, actor: User, dias: int = 30, desde=None, hasta=None) -> SharedStatisticsRead:
    _checkPeriod(dias, desde, hasta)
    profile = getConsumerProfile(db, actor) if actor.tipoCuenta == TIPO_CONSUMIDOR_FINAL else None
    if profile is None:
        return SharedStatisticsRead(dias=dias, cantidadMediciones=0, glucosa=_summary([]), spo2=_summary([]),
                                    frecuenciaCardiaca=_summary([]), serieDiaria=[])
    return buildStatistics(db, profile.idPerfilMedicion, dias, desde=desde, hasta=hasta)


def patientStatistics(db: Session, actor: User, idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, dias: int = 30,
                      desde=None, hasta=None) -> SharedStatisticsRead:
    _checkPeriod(dias, desde, hasta)
    requireClinicalAccess(db, actor, idInstitucion, idPerfilMedicion, "ESTADISTICAS")
    return buildStatistics(db, idPerfilMedicion, dias, desde=desde, hasta=hasta)


# --- Indicadores institucionales (agregados, sin identificar pacientes) -----------------------------------------


def institutionIndicators(db: Session, actor: User, idInstitucion: uuid.UUID) -> InstitutionIndicators:
    """Para propietario y moderador (CONSULTAR_EQUIPO). Solo conteos y agregados: ni nombres, ni documentos, ni
    identificadores de pacientes. Considera únicamente pacientes del período operativo vigente."""
    institutions.requireMembership(db, actor, idInstitucion, institutions.P_EQUIPO)
    profileIds = patients._patientsOf(idInstitucion).where(patients._IS_ACTIVE).with_only_columns(
        MeasurementProfile.idPerfilMedicion, maintain_column_froms=True)
    # Las mediciones de pacientes ya anonimizados (cohorte anónima) siguen contando en los agregados.
    scope = Measurement.idPerfilMedicion.in_(measurementRetention.withCohort(db, idInstitucion, profileIds))
    states = dict(db.execute(select(Measurement.estadoMedicion, func.count()).where(scope)
                             .group_by(Measurement.estadoMedicion)).all())
    modes = dict(db.execute(select(Measurement.modoMedicion, func.count()).where(scope)
                            .group_by(Measurement.modoMedicion)).all())
    rows = db.execute(select(Measurement.glucosaEstimada, Measurement.spo2, Measurement.frecuenciaCardiaca)
                      .where(scope, Measurement.estadoMedicion == COMPLETADA, NOT_DEMO)).all()
    if patientAccess.suppressSmallGroup(db, and_(scope, Measurement.estadoMedicion == COMPLETADA, NOT_DEMO)):
        rows = []  # menos pacientes distintos que el mínimo: no se informan promedios que identifiquen a una persona
    return InstitutionIndicators(
        pacientesActivos=db.scalar(select(func.count()).select_from(profileIds.subquery())),
        operadoresActivos=institutions._activeCount(db, idInstitucion, institutions.ROL_OPERADOR),
        medicionesTotal=sum(states.values()), medicionesPorEstado=states, medicionesPorModo=modes,
        completadas={
            "glucosa": _summary([float(r.glucosaEstimada) for r in rows if r.glucosaEstimada is not None]),
            "spo2": _summary([float(r.spo2) for r in rows if r.spo2 is not None]),
            "frecuenciaCardiaca": _summary([float(r.frecuenciaCardiaca) for r in rows if r.frecuenciaCardiaca is not None]),
        },
    )


# --- Envío del resultado por correo --------------------------------------------------------------------------------

RESULT_SEND_LIMIT = 3  # envíos por medición y por hora: evita usar el botón para enviar correo en masa


def sendResultByEmail(db: Session, actor: User, idMedicion: uuid.UUID, data: ResultSendRequest) -> ResultSendRead:
    """Envía el resultado (RESULTADO_MEDICION) de una medición COMPLETADA.

    Cuenta individual: al correo de la propia cuenta; pulsar el botón es la autorización. Paciente institucional: lo
    envía el operador a cargo al correo que el paciente le dio y confirma que el paciente lo autorizó. El correo del
    paciente no se guarda: queda solo en el envío PENDIENTE y se borra al terminar. La auditoría no registra correos.
    """
    measurement, access = _measurementAccess(db, actor, idMedicion)
    _requireOperate(access)
    if measurement.estadoMedicion != COMPLETADA:
        raise _error("MEDICION_NO_COMPLETADA", "Solo se puede enviar el resultado de una medición completada.")
    institutional = access.idInstitucion is not None
    if measurement.origenGlucosa == ORIGEN_DEMO and not institutional:
        # Una cuenta individual no recibe pruebas DEMO como resultado; a un paciente institucional se le envían identificadas como simuladas.
        raise _error("RESULTADO_DEMO_NO_ENVIABLE",
                     "Los datos DEMO son de prueba (la glucosa es sintética): no se envían como resultado.")
    if institutional:
        # Sin correo escrito se usa el que el paciente confirmó. Otra dirección nunca recibe el resultado directamente: se le pide al
        # paciente que la confirme desde su correo y el resultado sale recién entonces (GL-08; services/resultEmailConfirmation.py).
        confirmed = resultEmailStore.recipient(db, measurement.idPerfilMedicion, nowForDb())
        recipient = data.correoDestino or confirmed
        if recipient is None:
            raise _error("CORREO_DESTINO_REQUERIDO", "Ingresá el correo electrónico que informó el paciente.")
        if data.correoDestino is not None and not data.pacienteAutoriza:
            raise _error("AUTORIZACION_PACIENTE_REQUERIDA", "Confirmá que el paciente autorizó el envío de su resultado por correo.")
        if confirmed is None or recipient.lower() != confirmed.lower():
            from app.services import resultEmailConfirmation as confirmation

            if not confirmation.requestConfirmation(db, actor, access.idInstitucion, measurement.idPerfilMedicion, recipient, keep=False,
                                                    idMedicion=idMedicion):
                raise _error("ENVIO_CORREO_FALLIDO", "No pudimos enviar el correo. Probá de nuevo en unos minutos.")
            return ResultSendRead(estadoEnvio="CONFIRMACION_PENDIENTE", correoEnmascarado=maskEmail(recipient),
                                  mensaje="Enviamos al paciente un correo para que confirme su dirección: el resultado le llega cuando la confirma.")
    else:
        recipient = actor.correoElectronico  # una cuenta individual solo se envía a sí misma
    since = nowForDb() - timedelta(hours=1)
    recent = db.scalar(select(func.count()).select_from(ResultDelivery).where(
        ResultDelivery.idMedicion == idMedicion, ResultDelivery.fechaSolicitud >= since))
    if recent >= RESULT_SEND_LIMIT:
        raise _error("ENVIO_RESULTADO_LIMITE", "Ya se pidieron varios envíos de esta medición. Probá de nuevo más tarde.")

    sent = _deliverResult(db, actor, measurement, access, recipient, automatic=False)
    if not sent:
        raise _error("ENVIO_CORREO_FALLIDO", "No pudimos enviar el correo. Probá de nuevo en unos minutos.")
    return ResultSendRead(estadoEnvio="ENVIADO", correoEnmascarado=maskEmail(recipient),
                          mensaje="Enviamos el resultado por correo electrónico.")


def _deliverResult(db: Session, actor: User, measurement: Measurement, access, recipient: str, automatic: bool) -> bool:
    """Registra el envío, manda el correo y deja constancia SIN el correo (CK_EnvioResultado_enviado). Devuelve si se envió."""
    institutional = access.idInstitucion is not None
    idMedicion = measurement.idMedicion
    delivery = ResultDelivery(idMedicion=idMedicion, correoDestino=recipient, estadoEnvio="PENDIENTE", fechaSolicitud=nowForDb())
    db.add(delivery)
    db.commit()  # el SMTP corre fuera de la transacción
    context = {
        "fechaMedicion": measurement.fechaHoraInicio, "spo2": measurement.spo2,
        "frecuenciaCardiaca": measurement.frecuenciaCardiaca,
        "modo": "Glucosa experimental" if measurement.modoMedicion == "GLUCOSA_EXPERIMENTAL" else "Oximetría",
        "indiceOptico": measurement.indiceOptico,
        # La glucosa de una sesión con el dispositivo está en glucosaDispositivo (con su origen); la estimada por matriz, en glucosaEstimada.
        "valorGlucosa": measurement.glucosaEstimada if measurement.glucosaEstimada is not None else measurement.glucosaDispositivo,
        "unidad": "mg/dL" if (measurement.glucosaEstimada is not None or measurement.glucosaDispositivo is not None) else None,
        "esDemo": True if measurement.origenGlucosa == ORIGEN_DEMO else None,
        "condicionComida": measurement.condicionComida if measurement.modoMedicion == "GLUCOSA_EXPERIMENTAL" else None,
        "dispositivo": db.get(Device, measurement.idDispositivo).nombre,
    }
    if institutional:
        institution = db.get(Institution, access.idInstitucion)
        if institution is not None:
            context["institucion"] = institution.nombre  # dónde se midió
    else:
        context["urlMedicion"] = emailService.frontendUrl(f"/app/mediciones/{idMedicion}")
    try:
        sent = emailService.sendEmailEvent(EmailEventType.RESULTADO_MEDICION, recipient, context, incluirDetalleMedicion=True)
    except Exception:  # noqa: BLE001 - un dato inválido no debe dejar el envío en PENDIENTE
        sent = False
    delivery.estadoEnvio = "ENVIADO" if sent else "FALLIDO"
    delivery.fechaEnvio = nowForDb() if sent else None
    delivery.correoDestino = None  # CK_EnvioResultado_enviado: no se conserva el correo
    if not sent:
        delivery.detalleError = "No se pudo enviar el correo."
    registerEvent(db, "CRUD", "ENVIAR_RESULTADO_MEDICION", sent, actor.idUsuario, "Medicion", idMedicion,
                  datosNuevos={"estadoEnvio": delivery.estadoEnvio, "idEnvioResultado": str(delivery.idEnvioResultado),
                               "destino": "PACIENTE" if institutional else "CUENTA_PROPIA", "modo": "AUTOMATICO" if automatic else "MANUAL"},
                  tablaRelacionada="InstitucionUsuario" if access.relation else None,
                  idRelacionado=access.relation.idInstitucionUsuario if access.relation else None)
    db.commit()
    return sent


def autoSendResult(db: Session, actor: User, idMedicion: uuid.UUID) -> str | None:
    """Envío automático al guardar una medición de un paciente institucional con correo cargado y vigente (autorizado y de menos de
    12 meses). Se envían TODAS (oximetría, glucosa experimental y pruebas DEMO; el correo identifica las DEMO como simuladas). Nunca para
    cuentas individuales ni sin correo. Devuelve ENVIADO, FALLIDO o None (no correspondía). No levanta errores: la medición ya está guardada y un fallo del correo no la deshace."""
    # La sesión no expira los objetos al confirmar (expire_on_commit=False) y el guardado actualiza la medición con una sentencia directa: sin
    # esto se leería la copia anterior (ADQUIRIENDO), se concluiría que «no está completada» y NO se enviaría nada, sin ningún aviso.
    db.expire_all()
    measurement, access = _measurementAccess(db, actor, idMedicion)
    if access.idInstitucion is None or measurement.estadoMedicion != COMPLETADA:
        return None
    recipient = resultEmailStore.recipient(db, measurement.idPerfilMedicion, nowForDb())
    if recipient is None:
        return None
    return "ENVIADO" if _deliverResult(db, actor, measurement, access, recipient, automatic=True) else "FALLIDO"
