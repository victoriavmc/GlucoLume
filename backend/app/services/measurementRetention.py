# MeasurementRetention - Anonimización real de pacientes institucionales y fin de la conservación de sus mediciones (migración 031)
#
# SEUDONIMIZAR NO ES ANONIMIZAR. Hasta la 030 el job de retención borraba nombre, documento y fecha de nacimiento, pero dejaba el perfil con su
# seudónimo, su operador responsable y TODAS las mediciones colgando de él: cualquiera que conociera el seudónimo (o cruzara fechas) podía
# reconstruir la trayectoria de una persona. Eso es seudonimización. Acá, al vencer la conservación de los datos personales:
#   1. se calcula una vez la fecha de fin de conservación de cada medición: última medición de esa persona + 12 meses;
#   2. las mediciones pasan a la COHORTE ANÓNIMA de la institución (un PerfilMedicion sin persona, sin seudónimo y sin responsable), con
#      ese vencimiento sellado en Medicion.fechaVencimientoRetencion. Conservan edad al momento, sexo, alimentación, calidad de señal, SpO₂,
#      frecuencia cardíaca, glucosa, modo, origen DEMO/experimental y estado; se borra solo la observación libre;
#   3. el perfil original queda como cáscara administrativa sin ningún dato de salud: sin nombre, documento, nacimiento, edad ni sexo, con
#      un seudónimo nuevo y aleatorio (el anterior pudo haberse comunicado al operador) y sin mediciones.
# Ya no existe ninguna relación persona-medición. Lo que queda es estadística de una cohorte: por eso solo se muestra agregada y con el
# mínimo de pacientes distintos (patientAccess.suppressSmallGroup; la cohorte cuenta como UN solo paciente, lo que es conservador).
#
# RETENCIÓN. Alcance: solo datos CONSERVADOS (pacientes dados de baja o de institución cerrada, y ya anonimizados). Un paciente activo, o una
# cuenta individual, no vence por no medir. El fin de la conservación se controla así:
#   · paciente de BAJA con identidad todavía presente: última medición + 12 meses, calculado de sus propias mediciones;
#   · medición anonimizada: Medicion.fechaVencimientoRetencion, sellada al anonimizar (la identidad ya no hace falta para controlar el plazo).
# Al vencer se borra la medición y sus datos derivados: MuestraSensor, MedicionReferenciaCapilar y EnvioResultado. La Auditoría conserva solo
# identificadores y fechas (sin datos de salud ni personales) y no se toca.
#
# RESPALDOS. La regla se evalúa por fecha, no por evento: tras restaurar un respaldo antiguo, una pasada del job vuelve a borrar todo lo
# vencido. Los respaldos mismos se rotan fuera de la aplicación (docs/RETENCION_Y_ANONIMIZACION.md).
#
# Todo es idempotente, por lotes y confirma de a uno. Nada de esto corre si la base instalada no tiene las columnas de retención del esquema v5 (ready()).

import secrets
import uuid
from datetime import datetime

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.capillaryReference import CapillaryReferenceMeasurement
from app.models.institutionUser import InstitutionUser
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.resultDelivery import ResultDelivery
from app.models.sensorSample import SensorSample
from app.services import resultEmailStore, schemaCompat
from app.services.audit import registerEvent
from app.services.institution import addMonths
from app.utils.timeZone import nowForDb

TIPO_COHORTE = "COHORTE_ANONIMA"
TIPO_INSTITUCIONAL = "INSTITUCIONAL"
RETENTION_MONTHS = 12
BATCH = 500
ACCION_ANONIMIZAR = "ANONIMIZAR_PACIENTES"
ACCION_DEPURAR = "DEPURAR_MEDICIONES_RETENCION"

_P = MeasurementProfile.__table__
_M = Measurement.__table__


def ready(db: Session) -> bool:
    """¿Tiene la base instalada las columnas de retención y DNI normalizado del esquema v5? Hasta entonces todo sigue como antes (sin anonimizar ni borrar)."""
    return schemaCompat.hasColumn(db, "PerfilMedicion", "idInstitucion") and schemaCompat.hasColumn(db, "Medicion", "fechaVencimientoRetencion")


def cohortIds(db: Session, idInstitucion: uuid.UUID):
    """Subconsulta con la cohorte anónima de la institución (para sumar sus mediciones a los AGREGADOS institucionales), o None si todavía
    no se aplicó la 031. Nunca se usa para un acceso individual: la cohorte no es una persona."""
    if not ready(db):
        return None
    return select(_P.c.idPerfilMedicion).where(_P.c.tipoPerfil == TIPO_COHORTE, _P.c.idInstitucion == idInstitucion)


def withCohort(db: Session, idInstitucion: uuid.UUID, profileIds):
    """Los perfiles de una consulta AGREGADA de la institución más su cohorte anónima: las mediciones de pacientes ya anonimizados siguen
    contando en los totales y estadísticas (con el mínimo de pacientes), en lugar de desaparecer del tablero. Sin la 031, no cambia nada."""
    cohort = cohortIds(db, idInstitucion)
    if cohort is None:
        return profileIds
    union = profileIds.union_all(cohort).subquery()
    return select(union.c[0])


def stampInstitution(db: Session, idPerfilMedicion: uuid.UUID, idInstitucion: uuid.UUID) -> None:
    """Fija la institución de un paciente nuevo (la usa el índice de documento único). Sin commit. No hace nada si falta la 031."""
    if ready(db):
        db.execute(update(_P).where(_P.c.idPerfilMedicion == idPerfilMedicion).values(idInstitucion=idInstitucion))


def _cohortFor(db: Session, idInstitucion: uuid.UUID, now: datetime) -> uuid.UUID:
    """La cohorte anónima de la institución; la crea si falta. Un índice único (idInstitucion, COHORTE) evita dos ante pasadas simultáneas."""
    existing = db.scalar(select(_P.c.idPerfilMedicion).where(_P.c.tipoPerfil == TIPO_COHORTE, _P.c.idInstitucion == idInstitucion))
    if existing is not None:
        return existing
    created = uuid.uuid4()
    try:
        with db.begin_nested():
            db.execute(insert(_P).values(idPerfilMedicion=created, tipoPerfil=TIPO_COHORTE, idInstitucion=idInstitucion, fechaCreacion=now))
        return created
    except IntegrityError:  # otra pasada la creó primero
        return db.scalar(select(_P.c.idPerfilMedicion).where(_P.c.tipoPerfil == TIPO_COHORTE, _P.c.idInstitucion == idInstitucion))


def anonymizeProfile(db: Session, idPerfilMedicion: uuid.UUID, now: datetime) -> bool:
    """Anonimiza un paciente institucional (ver el encabezado). Sin commit. False si no es un perfil institucional todavía identificable."""
    institution = db.scalar(
        select(InstitutionUser.idInstitucion)
        .join(MeasurementProfile, MeasurementProfile.idInstitucionUsuarioResponsable == InstitutionUser.idInstitucionUsuario)
        .where(MeasurementProfile.idPerfilMedicion == idPerfilMedicion, MeasurementProfile.tipoPerfil == TIPO_INSTITUCIONAL,
               MeasurementProfile.fechaDepuracionDatosPersonales.is_(None)))
    if institution is None:
        return False
    last = db.scalar(select(func.max(_M.c.fechaHoraInicio)).where(_M.c.idPerfilMedicion == idPerfilMedicion))
    if last is not None:
        cohort = _cohortFor(db, institution, now)
        db.execute(update(_M).where(_M.c.idPerfilMedicion == idPerfilMedicion).values(
            idPerfilMedicion=cohort, fechaVencimientoRetencion=addMonths(last, RETENTION_MONTHS), observacion=None))
    resultEmailStore.clear(db, idPerfilMedicion)
    db.execute(update(_P).where(_P.c.idPerfilMedicion == idPerfilMedicion).values(
        nombre=None, apellido=None, dni=None, fechaNacimiento=None, edadDeclarada=None, sexoModelo=None, fechaUltimaMedicion=None,
        identificadorPseudonimo=f"ANON-{secrets.token_hex(6).upper()}", fechaDepuracionDatosPersonales=now))
    return True


def _deleteMeasurements(db: Session, ids: list[uuid.UUID]) -> None:
    """Borra las mediciones y sus datos derivados (las tablas hijas primero). Sin commit."""
    for model in (ResultDelivery, CapillaryReferenceMeasurement, SensorSample):
        db.execute(delete(model).where(model.idMedicion.in_(ids)).execution_options(synchronize_session=False))
    db.execute(delete(_M).where(_M.c.idMedicion.in_(ids)))


def _dueDischarged(db: Session, now: datetime) -> list[uuid.UUID]:
    """Pacientes de BAJA que todavía conservan su identidad y cuya última medición cumplió 12 meses."""
    rows = db.execute(
        select(Measurement.idPerfilMedicion, func.max(Measurement.fechaHoraInicio))
        .join(MeasurementProfile, MeasurementProfile.idPerfilMedicion == Measurement.idPerfilMedicion)
        .where(MeasurementProfile.tipoPerfil == TIPO_INSTITUCIONAL, MeasurementProfile.fechaExpiracionDatosPersonales.is_not(None),
               MeasurementProfile.fechaDepuracionDatosPersonales.is_(None))
        .group_by(Measurement.idPerfilMedicion)).all()
    return [profileId for profileId, last in rows if addMonths(last, RETENTION_MONTHS) <= now]


def plan(db: Session, now: datetime | None = None) -> dict:
    """Simulación, SIN modificar nada: cuántas mediciones borraría hoy el job (las de pacientes de baja cuya última medición cumplió 12 meses y las
    anonimizadas con el vencimiento ya cumplido). Cuenta cada medición una sola vez."""
    if not ready(db):
        return {"medicionesAEliminar": 0}
    now = now or nowForDb()
    discharged = _dueDischarged(db, now)
    fromDischarged = (db.scalar(select(func.count()).select_from(_M).where(_M.c.idPerfilMedicion.in_(discharged))) or 0) if discharged else 0
    sealed = db.scalar(select(func.count()).select_from(_M).where(_M.c.fechaVencimientoRetencion <= now)) or 0
    return {"medicionesAEliminar": fromDischarged + sealed}


def purgeExpiredMeasurements(db: Session, now: datetime | None = None, batchSize: int = BATCH) -> int:
    """Borra las mediciones conservadas (de pacientes de baja o ya anonimizados) a los 12 meses de la última medición de esa persona.
    Devuelve cuántas. Auditoría: un evento por pasada con la cantidad, sin identificadores ni datos."""
    if not ready(db):
        return 0
    now = now or nowForDb()
    total = 0
    for profileId in _dueDischarged(db, now):
        while True:
            ids = db.scalars(select(_M.c.idMedicion).where(_M.c.idPerfilMedicion == profileId).limit(batchSize)).all()
            if not ids:
                break
            _deleteMeasurements(db, ids)
            db.commit()
            total += len(ids)
        db.execute(update(_P).where(_P.c.idPerfilMedicion == profileId).values(fechaUltimaMedicion=None))
        db.commit()
    while True:
        ids = db.scalars(select(_M.c.idMedicion).where(_M.c.fechaVencimientoRetencion <= now).limit(batchSize)).all()
        if not ids:
            break
        _deleteMeasurements(db, ids)
        db.commit()
        total += len(ids)
    if total:
        registerEvent(db, "CRUD", ACCION_DEPURAR, True, None, "Medicion", None,
                      datosNuevos={"medicionesEliminadas": total, "plazoMeses": RETENTION_MONTHS})
        db.commit()
    return total
