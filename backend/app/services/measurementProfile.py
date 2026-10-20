# MeasurementProfile - PerfilMedicion base
#
# Persona a la que corresponde una medición. Base mínima para que el módulo Medición pueda iniciar una
# medición; no incluye Medicion, adquisición ni ConfiguracionNotificacion.
#
#   CONSUMIDOR_FINAL: el perfil es el propio Usuario (idUsuario). Se crea automáticamente la primera vez
#     que se necesita y sus datos se toman siempre de Usuario, que es la fuente de los datos actuales:
#     nombre, apellido, fechaNacimiento y sexo (-> sexoModelo). Usuario no tiene DNI: el perfil lo deja
#     en NULL hasta que exista una forma de completarlo.
#   INSTITUCIONAL: representa a un paciente, no al operador. Lo crea un operador ACTIVO de la institución
#     (idInstitucionUsuarioResponsable). Aquí solo se prepara su construcción; el CRUD de pacientes se
#     implementa con el módulo Institución/Medición.
#
# La edad no se guarda como dato estático: se calcula desde fechaNacimiento al iniciar cada medición y
# Medicion la conserva como snapshot (edadAlMomento, sexoModelo). El contexto de la medición (comida,
# estado actual) no pertenece al perfil.

import secrets
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.models.institutionUser import InstitutionUser
from app.models.measurementProfile import MeasurementProfile
from app.models.user import User
from app.schemas.measurementProfile import InstitutionalProfileCreate
from app.services.audit import registerEvent
from app.utils.timeZone import nowForDb, toDbTime

TIPO_CONSUMIDOR_FINAL = "CONSUMIDOR_FINAL"
TIPO_INSTITUCIONAL = "INSTITUCIONAL"
INSTITUCION_ACTIVA = "ACTIVA"
ESTADO_ACTIVO = "ACTIVO"
ROL_OPERADOR = "OPERADOR"
# Rango de CK_Medicion_edad / CK_PerfilMedicion_edad.
EDAD_MINIMA = 0
EDAD_MAXIMA = 130
# Datos de Usuario que se RECOMIENDAN para el perfil (mejoran la estimación experimental). NO son obligatorios para medir.
CONSUMER_RECOMMENDED_FIELDS = ("fechaNacimiento", "sexo")
# Perfil que se sincroniza desde Usuario: columna del perfil -> atributo de Usuario.
_SYNCED_FIELDS = {"nombre": "nombre", "apellido": "apellido", "fechaNacimiento": "fechaNacimiento", "sexoModelo": "sexo"}


@dataclass(frozen=True)
class MeasurementSnapshot:
    """Datos del perfil que Medicion copia al iniciar (no cambian si después cambia el perfil)."""

    edadAlMomento: int | None
    sexoModelo: str | None


# --- Edad --------------------------------------------------------------------------------


def calculateAge(fechaNacimiento: date, onDate: date) -> int:
    """Años cumplidos a la fecha indicada."""
    years = onDate.year - fechaNacimiento.year
    if (onDate.month, onDate.day) < (fechaNacimiento.month, fechaNacimiento.day):
        years -= 1
    return years


def measurementSnapshot(profile: MeasurementProfile, at: datetime | None = None) -> MeasurementSnapshot:
    """Edad y sexo del modelo para una medición que inicia en `at` (por defecto, ahora; hora de Argentina).

    Con fechaNacimiento la edad se calcula a esa fecha; edadDeclarada solo se usa si no hay fecha de
    nacimiento. En un paciente INSTITUCIONAL la edad y el sexo son opcionales (None si no se definieron); un perfil
    individual sin ellos no puede medir.
    """
    onDate = toDbTime(at).date() if at is not None else nowForDb().date()
    if profile.fechaNacimiento is not None:
        age = calculateAge(profile.fechaNacimiento, onDate)
    elif profile.edadDeclarada is not None:
        age = profile.edadDeclarada
    else:
        age = None  # la edad y el sexo son opcionales en cualquier perfil (solo la estimación por matriz los necesita)
    if age is not None and not EDAD_MINIMA <= age <= EDAD_MAXIMA:
        raise AuthError("EDAD_FUERA_DE_RANGO", f"La edad debe estar entre {EDAD_MINIMA} y {EDAD_MAXIMA} años.")
    return MeasurementSnapshot(edadAlMomento=age, sexoModelo=profile.sexoModelo)


# --- Consumidor final --------------------------------------------------------------------


def getConsumerProfile(db: Session, user: User) -> MeasurementProfile | None:
    return db.scalar(
        select(MeasurementProfile).where(
            MeasurementProfile.idUsuario == user.idUsuario, MeasurementProfile.tipoPerfil == TIPO_CONSUMIDOR_FINAL
        )
    )


def missingRecommendedFields(user: User) -> list[str]:
    """Datos que conviene completar (informativo): no impiden crear el perfil ni medir."""
    return [field for field in CONSUMER_RECOMMENDED_FIELDS if getattr(user, field) is None]


def _syncFromUser(profile: MeasurementProfile, user: User) -> bool:
    changed = False
    for profileField, userField in _SYNCED_FIELDS.items():
        value = getattr(user, userField)
        if getattr(profile, profileField) != value:
            setattr(profile, profileField, value)
            changed = True
    return changed


def ensureConsumerProfile(db: Session, user: User) -> MeasurementProfile:
    """Devuelve el perfil propio del consumidor final, creándolo la primera vez y actualizándolo desde Usuario.

    La fecha de nacimiento y el sexo de Usuario (PATCH /auth/me/profile) son opcionales: si faltan, el perfil se crea
    igual y esos datos quedan sin informar. Confirma la transacción. La creación se audita (sin datos personales); la
    sincronización no, porque el cambio ya se auditó al actualizar el Usuario.
    """
    if user.tipoCuenta != TIPO_CONSUMIDOR_FINAL or user.estado != ESTADO_ACTIVO:
        raise AuthError("PERFIL_NO_DISPONIBLE", "Solo una cuenta de consumidor final activa tiene perfil de medición propio.")

    profile = getConsumerProfile(db, user)
    if profile is not None:
        if _syncFromUser(profile, user):
            db.commit()
        return profile

    profile = MeasurementProfile(tipoPerfil=TIPO_CONSUMIDOR_FINAL, idUsuario=user.idUsuario)
    _syncFromUser(profile, user)
    db.add(profile)
    try:
        db.flush()
        registerEvent(
            db, "CRUD", "CREAR_PERFIL_MEDICION", True, user.idUsuario, "PerfilMedicion", profile.idPerfilMedicion,
            datosNuevos={"tipoPerfil": TIPO_CONSUMIDOR_FINAL},
        )
        db.commit()
    except IntegrityError:
        # Carrera contra UX_PerfilMedicion_consumidor: otra solicitud lo creó; se usa ese.
        db.rollback()
        profile = getConsumerProfile(db, user)
        if profile is None:
            raise
        if _syncFromUser(profile, user):
            db.commit()
    return profile


# --- Institucional (preparado; el CRUD de pacientes es del módulo Institución/Medición) ----


def newPseudonym() -> str:
    """Identificador pseudónimo del paciente (obligatorio por CK_PerfilMedicion_coherenciaTipo)."""
    return f"PAC-{secrets.token_hex(6).upper()}"


def buildInstitutionalProfile(responsable: InstitutionUser, data: InstitutionalProfileCreate) -> MeasurementProfile:
    """Arma (sin persistir) el perfil de un paciente a cargo de un operador ACTIVO.

    El perfil representa al paciente: no toma ningún dato del operador. Quien llame lo agrega a la sesión,
    lo audita y confirma.
    """
    if responsable.rolInstitucion != ROL_OPERADOR or responsable.estadoRelacion != ESTADO_ACTIVO:
        raise AuthError("RESPONSABLE_INVALIDO", "Solo un operador activo de la institución puede crear pacientes.")
    if responsable.institucion.estado != INSTITUCION_ACTIVA:
        # Una institución eliminada (CERRADA) o inactiva no registra pacientes ni mediciones nuevas.
        raise AuthError("RESPONSABLE_INVALIDO", "La institución no está activa.")
    if data.fechaNacimiento is not None:
        age = calculateAge(data.fechaNacimiento, nowForDb().date())
        if age > EDAD_MAXIMA:
            raise AuthError("EDAD_FUERA_DE_RANGO", f"La edad debe estar entre {EDAD_MINIMA} y {EDAD_MAXIMA} años.")
    return MeasurementProfile(
        tipoPerfil=TIPO_INSTITUCIONAL,
        idInstitucionUsuarioResponsable=responsable.idInstitucionUsuario,
        identificadorPseudonimo=newPseudonym(),
        nombre=data.nombre,
        apellido=data.apellido,
        dni=data.dni,
        fechaNacimiento=data.fechaNacimiento,
        sexoModelo=data.sexoModelo,
    )
