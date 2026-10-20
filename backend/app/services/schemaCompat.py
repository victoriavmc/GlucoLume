# Compatibilidad con migraciones todavía no aplicadas.
#
# Los cambios de esquema los aplica un administrador de la base (el usuario de la aplicación no tiene permiso de DDL). Para que
# actualizar el backend NUNCA deje el módulo caído mientras tanto, el código que usa una columna o una restricción nueva primero comprueba
# que existan. Un «no» se vuelve a consultar cada TTL_SECONDS; un «sí» se recuerda POSITIVE_TTL_SECONDS (10 minutos): si se restaura una
# base anterior sin la columna, el backend lo nota solo, sin reiniciarlo.

import time
import uuid

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.models.measurement import Measurement

TTL_SECONDS = 30.0
POSITIVE_TTL_SECONDS = 600.0
_positive: dict[tuple[str, str], float] = {}
_negative: dict[tuple[str, str], float] = {}


def reset() -> None:
    """Olvida lo comprobado (pruebas, o después de cambiar el esquema de la base instalada)."""
    _positive.clear()
    _negative.clear()


def _check(db: Session, key: tuple[str, str], query: str, **params) -> bool:
    if db.get_bind().dialect.name != "mssql":
        return True  # las pruebas con SQLite usan el esquema de los modelos (ya migrado)
    now = time.monotonic()
    confirmed = _positive.get(key)
    if confirmed is not None and now - confirmed < POSITIVE_TTL_SECONDS:
        return True
    checked = _negative.get(key)
    if checked is not None and now - checked < TTL_SECONDS:
        return False
    found = bool(db.scalar(text(query), params))
    if found:
        _positive[key] = now
        _negative.pop(key, None)
    else:
        _positive.pop(key, None)
        _negative[key] = now
    return found


def hasColumn(db: Session, table: str, column: str) -> bool:
    return _check(db, (f"col:{table}", column), "SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(:table) AND name = :column",
                  table=f"dbo.{table}", column=column)


def hasTable(db: Session, table: str) -> bool:
    return _check(db, ("table", table), "SELECT 1 FROM sys.tables WHERE object_id = OBJECT_ID(:table)", table=f"dbo.{table}")


def auditContextReady(db: Session) -> bool:
    """¿Tiene la base instalada la tabla AuditoriaContexto (esquema v5)? Sin ella la auditoría sigue funcionando, sin IP, cliente ni correlación."""
    return hasTable(db, "AuditoriaContexto")


def auditAccountTypeReady(db: Session) -> bool:
    """¿Tiene la base instalada Auditoria.tipoCuentaActor (esquema v5)? Sin ella el backend no la nombra y los accesos por tipo de cuenta se infieren del
    tipo vigente de la cuenta, como siempre."""
    return hasColumn(db, "Auditoria", "tipoCuentaActor")


def administrativeClosureReady(db: Session) -> bool:
    """¿Tiene la base instalada las columnas de cierre administrativo de Institucion (esquema v5)? Sin él nada cambia para el cierre y la reapertura del
    propietario; solo la eliminación administrativa queda no disponible (no puede existir un cierre administrativo sin la columna)."""
    return hasColumn(db, "Institucion", "cierreAdministrativo")


def glucoseDeviceModeReady(db: Session) -> bool:
    """¿Tiene la base instalada el modo de glucosa del dispositivo (esquema v5)? Se comprueba por la EXISTENCIA de sus objetos (CK_Medicion_demoSinEstimacion, que crea 025, y la
    ausencia de CK_Medicion_origenSoloOximetria, que elimina). No se lee la definición de las restricciones: el usuario de la aplicación no
    tiene permiso para verla y llegaría vacía."""
    migrated = _check(db, ("ck", "demoSinEstimacion"),
                      "SELECT 1 FROM sys.check_constraints WHERE name = N'CK_Medicion_demoSinEstimacion' "
                      "AND parent_object_id = OBJECT_ID(N'dbo.Medicion')")
    if not migrated:
        return False
    if db.get_bind().dialect.name != "mssql":
        return True
    legacy = db.scalar(text("SELECT 1 FROM sys.check_constraints WHERE name = N'CK_Medicion_origenSoloOximetria' "
                            "AND parent_object_id = OBJECT_ID(N'dbo.Medicion')"))
    return not legacy


def ruleIdOf(db: Session, idMedicion: uuid.UUID) -> uuid.UUID | None:
    """Regla de la matriz que se aplicó en la estimación del servidor de esta medición (None si no hubo o si falta la migración 025)."""
    if not hasColumn(db, "Medicion", "idReglaMatriz"):
        return None
    table = Measurement.__table__
    return db.scalar(select(table.c.idReglaMatriz).where(table.c.idMedicion == idMedicion))


def setRuleId(db: Session, idMedicion: uuid.UUID, idRegla: uuid.UUID | None) -> None:
    if idRegla is None or not hasColumn(db, "Medicion", "idReglaMatriz"):
        return
    table = Measurement.__table__
    db.execute(update(table).where(table.c.idMedicion == idMedicion).values(idReglaMatriz=idRegla))
