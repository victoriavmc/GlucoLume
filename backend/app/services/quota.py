# Quota - Cupos de cuentas institucionales (capacidad máxima de cuentas ACTIVAS por institución)
#
# Cada institución tiene su propia capacidad (Institucion.capacidadMaximaUsuarios, 1000 por omisión). Lo que consume
# cupo se CALCULA con las relaciones vigentes, sin contadores guardados:
#   cuentas activas  = cuentas DISTINTAS con InstitucionUsuario.estadoRelacion = 'ACTIVO' en esa institución (propietario, moderadores y
#                      operadores), sin cuentas eliminadas. Una persona cuenta una sola vez aunque tenga invitaciones o roles históricos.
#   cupos disponibles = max(0, capacidad − cuentas activas)
#   utilización       = cuentas activas / capacidad
# NO consumen cupo: invitaciones pendientes, canceladas, rechazadas o vencidas, personas dadas de baja ni los pacientes del padrón.
# El cupo se ocupa al incorporarse de verdad (aceptar la invitación) y se libera solo al dejar de estar activa la relación.
#
# Control del límite (siempre en el backend): quien vuelve ACTIVA una relación pasa por requireSlot() dentro de su transacción, que primero
# bloquea la fila de la institución (UPDLOCK/HOLDLOCK en SQL Server: dos incorporaciones simultáneas se encolan) y recién entonces cuenta;
# después de escribir, verifyNotExceeded() vuelve a contar dentro de la misma transacción y la revierte si se pasó. Una invitación pendiente
# no se activa a medias: si no hay cupo, la relación sigue PENDIENTE.
#
# Compatibilidad: si la base instalada no tiene la columna, la capacidad es la predeterminada (DEFAULT_CAPACITY) y los cupos se calculan igual.

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.user import User
from app.schemas.institution import QuotaRead
from app.services import schemaCompat

DEFAULT_CAPACITY = 1000
NEAR_LIMIT_PERCENT = 80  # configuración visual: no impide incorporar antes del límite real
RELACION_ACTIVO = "ACTIVO"
CAPACITY_FULL_MESSAGE = ("La institución alcanzó su capacidad máxima de cuentas activas. Para incorporar a otra persona, es necesario "
                         "liberar un cupo o ampliar la capacidad.")


def capacityOf(db: Session, idInstitucion: uuid.UUID) -> int:
    """Capacidad máxima de cuentas activas de la institución (la predeterminada si la migración 028 todavía no se aplicó)."""
    if not schemaCompat.hasColumn(db, "Institucion", "capacidadMaximaUsuarios"):
        return DEFAULT_CAPACITY
    table = Institution.__table__
    value = db.scalar(select(table.c.capacidadMaximaUsuarios).where(table.c.idInstitucion == idInstitucion))
    return int(value) if value else DEFAULT_CAPACITY


def activeCount(db: Session, idInstitucion: uuid.UUID) -> int:
    """Cuentas distintas con relación institucional ACTIVA (cuentas eliminadas no cuentan)."""
    return db.scalar(
        select(func.count(func.distinct(InstitutionUser.idUsuarioInvitado)))
        .join(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
        .where(InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.estadoRelacion == RELACION_ACTIVO, User.estado != "ELIMINADO")
    ) or 0


MAX_CAPACITY = 100_000


def stateOf(active: int, capacity: int) -> str:
    if active > capacity:
        return "EXCEDIDA"  # la plataforma redujo el límite por debajo de las cuentas existentes: se conservan, pero no se admiten más
    if active >= capacity:
        return "COMPLETA"
    return "PROXIMO_AL_LIMITE" if active * 100 >= capacity * NEAR_LIMIT_PERCENT else "DISPONIBLE"


def usage(db: Session, idInstitucion: uuid.UUID) -> QuotaRead:
    """Cupos de UNA institución, calculados con sus relaciones vigentes (nunca con datos del cliente)."""
    capacity = capacityOf(db, idInstitucion)
    active = activeCount(db, idInstitucion)
    return QuotaRead(
        capacidadMaximaUsuarios=capacity, usuariosActivos=active, cuposDisponibles=max(0, capacity - active), excedente=max(0, active - capacity),
        porcentajeUtilizacion=min(100.0, round(active * 100 / capacity, 1)), estado=stateOf(active, capacity),
    )


def lockInstitution(db: Session, idInstitucion: uuid.UUID) -> None:
    """Serializa las incorporaciones de UNA institución: la fila queda bloqueada hasta el fin de la transacción. SQLAlchemy ignora
    with_for_update en SQL Server: se usa el hint de tabla (UPDLOCK + HOLDLOCK); otras instituciones no se ven afectadas."""
    db.execute(select(Institution.idInstitucion).with_hint(Institution, "WITH (UPDLOCK, HOLDLOCK, ROWLOCK)", "mssql")
               .where(Institution.idInstitucion == idInstitucion))


def requireSlot(db: Session, idInstitucion: uuid.UUID) -> QuotaRead:
    """Debe llamarse dentro de la transacción que va a activar la relación. Bloquea, cuenta y rechaza si no queda cupo."""
    lockInstitution(db, idInstitucion)
    current = usage(db, idInstitucion)
    if current.cuposDisponibles <= 0:
        raise AuthError("CAPACIDAD_COMPLETA", CAPACITY_FULL_MESSAGE)
    return current


def verifyNotExceeded(db: Session, idInstitucion: uuid.UUID) -> QuotaRead:
    """Segunda comprobación, después de escribir y antes de confirmar: si algo se coló, la transacción se revierte."""
    current = usage(db, idInstitucion)
    if current.usuariosActivos > current.capacidadMaximaUsuarios:
        raise AuthError("CAPACIDAD_COMPLETA", CAPACITY_FULL_MESSAGE)
    return current


def validateNewCapacity(db: Session, idInstitucion: uuid.UUID, newCapacity: int) -> None:
    """Regla de la modificación administrativa de la capacidad: entero entre 1 y MAX_CAPACITY. PUEDE ser menor que las cuentas activas: en ese
    caso las cuentas existentes se conservan (ninguna se elimina ni se suspende), la institución queda EXCEDIDA y no admite cuentas nuevas
    que consuman cupo hasta regularizarse (requireSlot sigue rechazando mientras no haya disponibles)."""
    if isinstance(newCapacity, bool) or not isinstance(newCapacity, int) or newCapacity <= 0:
        raise AuthError("CAPACIDAD_INVALIDA", "La capacidad máxima debe ser un número entero mayor que cero.")
    if newCapacity > MAX_CAPACITY:
        raise AuthError("CAPACIDAD_INVALIDA", f"La capacidad máxima no puede superar {MAX_CAPACITY:,} cuentas.".replace(",", "."))
