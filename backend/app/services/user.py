# User - Servicio de Usuario
#
# Usuario es la fuente de los datos personales actuales de la persona (usuario, fechaNacimiento,
# sexo). Las mediciones conservan su propio contexto histórico (Medicion.edadAlMomento,
# Medicion.sexoModelo); PerfilMedicion mantiene los datos de perfiles institucionales.

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.models.user import User
from app.schemas.user import UserProfileUpdate
from app.services.audit import registerEvent
from app.utils.timeZone import nowForDb

# Datos que toda cuenta debe completar (una cuenta Google nueva los completa tras el primer acceso).
# Completar el perfil NO es obligatorio para usar la cuenta. Solo una cuenta individual necesita fecha de nacimiento y sexo,
# y únicamente para medir (el perfil de medición los usa); el nombre de usuario nunca es obligatorio. La interfaz no
# interrumpe a nadie con avisos: la pantalla de mediciones pide esos datos en el momento en que hacen falta.
MEASUREMENT_PROFILE_FIELDS = ("fechaNacimiento", "sexo")


def missingRequiredFields(user: User) -> list[str]:
    """Datos que faltan para poder medir (solo cuentas individuales); informativo, no bloquea nada."""
    if user.tipoCuenta != "CONSUMIDOR_FINAL":
        return []
    return [field for field in MEASUREMENT_PROFILE_FIELDS if getattr(user, field) is None]


USERNAME_UNIQUE_INDEX = "UX_Usuario_usuario"


def _usernameUnavailable() -> AuthError:
    return AuthError("USUARIO_NO_DISPONIBLE", "El nombre de usuario ya se encuentra en uso. Elegí otro.")


def findUserByUsername(db: Session, username: str) -> User | None:
    # La comparación sigue la collation de la base, igual que el índice único.
    return db.scalar(select(User).where(User.usuario == username))


# Campos editables, en el orden en que se informan en auditoría.
PROFILE_FIELDS = ("nombre", "apellido", "usuario", "fechaNacimiento", "sexo")

COMPLETADO = "COMPLETADO"  # antes NULL, ahora con valor
ACTUALIZADO = "ACTUALIZADO"  # tenía valor y se reemplazó por otro distinto
MANTENIDO = "MANTENIDO"  # se envió, pero el valor final es igual al existente
REAL_CHANGES = (COMPLETADO, ACTUALIZADO)


def _fieldState(previous, new) -> str:
    if new == previous:
        return MANTENIDO
    return COMPLETADO if previous is None else ACTUALIZADO


def _auditObservation(states: dict[str, str]) -> str:
    """Texto legible con los campos que cambiaron realmente; sin valores personales."""
    parts = []
    for state, verb in ((ACTUALIZADO, "actualizaron"), (COMPLETADO, "completaron")):
        fields = [field for field, fieldState in states.items() if fieldState == state]
        if fields:
            parts.append(f"Se {verb} los campos: {', '.join(fields)}.")
    return " ".join(parts)


def updateProfile(db: Session, user: User, data: UserProfileUpdate) -> bool:
    """Completa o actualiza los datos personales del Usuario autenticado.

    Cada campo enviado (ya normalizado por UserProfileUpdate) se clasifica como COMPLETADO,
    ACTUALIZADO o MANTENIDO. Solo los cambios reales se guardan y se auditan; la auditoría registra
    el estado de cada campo, nunca sus valores. Devuelve True si hubo al menos un cambio real.
    """
    requested = data.model_dump(exclude_unset=True)
    if user.usuario is None and "usuario" not in requested:
        raise AuthError("USUARIO_REQUERIDO", "Elegí un nombre de usuario para completar la cuenta.")

    states = {
        field: _fieldState(getattr(user, field), requested[field]) for field in PROFILE_FIELDS if field in requested
    }
    changed = {field: requested[field] for field, state in states.items() if state in REAL_CHANGES}
    if not changed:
        # Todo MANTENIDO: sin UPDATE, sin fechaActualizacion y sin auditoría.
        return False

    if "usuario" in changed:
        # Solo se verifica disponibilidad al completar o cambiar el username, nunca contra sí mismo.
        existing = findUserByUsername(db, changed["usuario"])
        if existing is not None and existing.idUsuario != user.idUsuario:
            raise _usernameUnavailable()

    datosPrevios = {field: {"estado": "SIN_DATO" if getattr(user, field) is None else "EXISTENTE"} for field in states}
    datosNuevos = {field: {"estado": state} for field, state in states.items()}

    for field, value in changed.items():
        setattr(user, field, value)
    user.fechaActualizacion = nowForDb()
    registerEvent(
        db, "CRUD", "ACTUALIZAR_PERFIL", True, user.idUsuario, "Usuario", user.idUsuario,
        observacion=_auditObservation(states),
        datosPrevios=datosPrevios,
        datosNuevos=datosNuevos,
    )
    try:
        db.commit()
    except IntegrityError as error:
        # El rollback descarta los cambios: el Usuario queda como estaba.
        db.rollback()
        if USERNAME_UNIQUE_INDEX.lower() in str(error.orig).lower():
            # Carrera: otra solicitud tomó el mismo username entre la verificación y el guardado.
            raise _usernameUnavailable() from error
        raise
    return True
