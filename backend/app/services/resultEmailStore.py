# ResultEmailStore - Correo del paciente institucional para el envío automático de resultados (migración 030)
#
# El paciente no tiene cuenta: el operador a cargo carga el correo que el paciente le dio, con su autorización, y se guarda en
# PerfilMedicion (correoResultados + fechaAutorizacionCorreo + fechaExpiracionCorreo = autorización + 12 meses). Vencido el plazo, o con
# la baja del paciente, se borra. Las tres columnas se agregan con la migración 030 y NO se mapean como atributos (ver
# MeasurementProfile.__mapper_args__): se leen y escriben con Core solo si existen (schemaCompat), así el backend no se cae mientras la
# migración no se aplique. Este módulo no depende de otros servicios: lo usan institutionPatients, measurement y el job de retención.

import uuid
from datetime import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models.measurementProfile import MeasurementProfile
from app.services import schemaCompat

RETENTION_MONTHS = 12
_T = MeasurementProfile.__table__


def ready(db: Session) -> bool:
    """¿Tiene la base instalada las columnas de correo de resultados (esquema v5)?"""
    return schemaCompat.hasColumn(db, "PerfilMedicion", "correoResultados")


def stored(db: Session, idPerfilMedicion: uuid.UUID, now: datetime) -> tuple[str, datetime] | None:
    """(correo, vencimiento) vigente del paciente, o None si no hay, venció o la migración no está aplicada."""
    if not ready(db):
        return None
    row = db.execute(select(_T.c.correoResultados, _T.c.fechaExpiracionCorreo).where(_T.c.idPerfilMedicion == idPerfilMedicion)).first()
    if row is None or row[0] is None or row[1] is None or row[1] <= now:
        return None
    return row[0], row[1]


def authorization(db: Session, idPerfilMedicion: uuid.UUID) -> tuple[str, datetime] | None:
    """(correo, fecha de autorización) guardados, aunque hayan vencido; None si no hay o la base no tiene las columnas."""
    if not ready(db):
        return None
    row = db.execute(select(_T.c.correoResultados, _T.c.fechaAutorizacionCorreo).where(_T.c.idPerfilMedicion == idPerfilMedicion)).first()
    return None if row is None or row[0] is None else (row[0], row[1])


def recipient(db: Session, idPerfilMedicion: uuid.UUID, now: datetime) -> str | None:
    found = stored(db, idPerfilMedicion, now)
    return None if found is None else found[0]


def save(db: Session, idPerfilMedicion: uuid.UUID, email: str, authorizedAt: datetime, expiresAt: datetime) -> None:
    db.execute(update(_T).where(_T.c.idPerfilMedicion == idPerfilMedicion)
               .values(correoResultados=email, fechaAutorizacionCorreo=authorizedAt, fechaExpiracionCorreo=expiresAt))


def clear(db: Session, idPerfilMedicion: uuid.UUID) -> bool:
    """Borra el correo guardado (si la migración existe). No hace commit: lo decide quien llama."""
    if not ready(db):
        return False
    db.execute(update(_T).where(_T.c.idPerfilMedicion == idPerfilMedicion)
               .values(correoResultados=None, fechaAutorizacionCorreo=None, fechaExpiracionCorreo=None))
    return True


def purgeExpired(db: Session, now: datetime) -> int:
    """Borra los correos vencidos y los de pacientes dados de baja o desidentificados. Devuelve la cantidad. Idempotente."""
    if not ready(db):
        return 0
    result = db.execute(
        update(_T)
        .where(_T.c.correoResultados.is_not(None),
               or_(_T.c.fechaExpiracionCorreo <= now, _T.c.fechaExpiracionDatosPersonales.is_not(None)))
        .values(correoResultados=None, fechaAutorizacionCorreo=None, fechaExpiracionCorreo=None)
        .execution_options(synchronize_session=False))
    db.commit()
    return result.rowcount or 0
