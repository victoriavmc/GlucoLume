# Base - Base declarativa común de los modelos
#
# Fuente de verdad del esquema: database/reference/GlucoLume_DB_v5.sql (DEC-02, esquema consolidado único; tests/test_reference_schema.py lo compara con los modelos).
# Los modelos mapean el esquema existente en SQL Server; no deben usarse para crearlo.

from sqlalchemy import MetaData, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session

from app.utils.timeZone import nowForDb


class Base(DeclarativeBase):
    metadata = MetaData(
        schema="dbo",
        naming_convention={"pk": "PK_%(table_name)s"},
    )


# Las columnas de fecha del esquema tienen DEFAULT sysutcdatetime() (UTC) en SQL Server. Para que
# todas las fechas generadas por el backend sigan la misma política (hora de Argentina, ver
# app/utils/timeZone.py), antes de insertar se completan aquí las que llegan vacías, en lugar de
# dejar que la base aplique su DEFAULT en UTC.
_SERVER_UTC_DEFAULT = "sysutcdatetime()"


def _usesServerUtcDefault(column) -> bool:
    default = column.server_default
    return default is not None and _SERVER_UTC_DEFAULT in str(getattr(default, "arg", "")).lower()


@event.listens_for(Session, "before_flush")
def _fillArgentinaTimestamps(session: Session, flushContext, instances) -> None:
    now = nowForDb()
    for instance in session.new:
        mapper = inspect(instance).mapper
        for column in mapper.columns:
            if _usesServerUtcDefault(column):
                key = mapper.get_property_by_column(column).key
                if getattr(instance, key) is None:
                    setattr(instance, key, now)
