# Demo - Eliminación de los datos demo (y solo de ellos)
#
# 1. plan(): a partir de los IDs fijos del catálogo, busca en la base lo que existe y, por las claves foráneas del modelo, todo lo
#    que depende de esos registros (sesiones, consentimientos, mediciones, etc.). Solo lee.
# 2. Si algún dependiente está en una tabla que el procedimiento no puede eliminar, o es auditoría, la limpieza se BLOQUEA y no
#    borra nada: la auditoría es de solo inserción para la API (GL-03) y no se altera desde aquí.
# 3. execute(): borra en UNA transacción, hijos antes que padres, con la cuenta DB_DEMO_USER (rol rol_glucolume_demo_limpieza,
#    database/reference/GlucoLume_demo_permisos.sql). La cuenta de la API no tiene DELETE sobre instituciones, grupos ni perfiles.
#
# Nunca toca: administradores de plataforma, usuarios reales, matrices, reglas, parámetros ni la auditoría.

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import delete, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.demo import catalog as C

# Tablas que el rol de limpieza puede eliminar. Debe coincidir con database/reference/GlucoLume_demo_permisos.sql.
TABLAS_PERMITIDAS = frozenset({
    "Medicion", "MedicionReferenciaCapilar", "MuestraSensor", "EnvioResultado", "AuditoriaTecnicaMedicion",
    "NotificacionUsuario", "SesionUsuario", "TokenCuenta", "ConsentimientoUsuario", "CredencialLocal",
    "CredencialLocalHistorial", "FactorMfa", "CodigoRecuperacionMfa", "IdentidadExterna", "PerfilMedicion", "Dispositivo",
    "GrupoUsuario", "Grupo", "InstitucionUsuario", "Institucion", "Usuario",
})


class LimpiezaBloqueada(Exception):
    """La limpieza no puede completarse sin tocar datos que no son demo o auditoría. Nada se borró."""


@dataclass
class CleanupPlan:
    existentes: dict[str, set[uuid.UUID]] = field(default_factory=dict)  # tabla -> IDs a eliminar (incluye dependientes)
    orden: list[str] = field(default_factory=list)  # hijos antes que padres
    bloqueos: list[str] = field(default_factory=list)

    @property
    def bloqueada(self) -> bool:
        return bool(self.bloqueos)

    def resumen(self) -> dict[str, int]:
        return {tabla: len(self.existentes[tabla]) for tabla in self.orden if self.existentes.get(tabla)}


def _semillas() -> dict[str, set[uuid.UUID]]:
    """IDs fijos del catálogo, por tabla."""
    return {
        "Usuario": {a.id for a in C.ACCOUNTS},
        "Institucion": {i.id for i in C.INSTITUTIONS},
        "Grupo": {C.demoId("grupo", C.GROUP_KEY)},
        "GrupoUsuario": {C.demoId("vinculo-grupo", k) for k in ["grupo-admin"] + [m[0] for m in C.GROUP_MEMBERS]},
        "InstitucionUsuario": {s.id for s in C.STAFF},
        "Dispositivo": {d.id for d in C.DEVICES},
        "PerfilMedicion": {C.demoId("perfil", a.key) for a in C.ACCOUNTS if a.individual} | {p.id for p in C.PATIENTS},
        "Medicion": {s.id for _, specs in C.individualMeasurements() for s in specs}
                    | {s.id for _, specs in C.patientMeasurements() for s in specs},
    }


def _table(name: str):
    """Tabla del modelo (el esquema es dbo: las claves de metadata llevan el prefijo)."""
    return Base.metadata.tables[f"dbo.{name}"]


def _pk(table):
    columns = list(table.primary_key.columns)
    if len(columns) != 1:
        raise LimpiezaBloqueada(f"La tabla {table.name} tiene clave compuesta: el procedimiento no la soporta.")
    return columns[0]


def _chunks(values: list, size: int = 500):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _existingPks(db: Session, table, ids: set[uuid.UUID]) -> set[uuid.UUID]:
    pk = _pk(table)
    found: set[uuid.UUID] = set()
    for chunk in _chunks(sorted(ids, key=str)):
        found.update(db.scalars(select(pk).where(pk.in_(chunk))).all())
    return found


def plan(db: Session) -> CleanupPlan:
    """Calcula qué se borraría. Solo lee."""
    result = CleanupPlan()
    tables = {table.name: table for table in Base.metadata.tables.values()}
    inspector = inspect(db.get_bind())
    present = {name for name, table in tables.items() if inspector.has_table(table.name, schema=table.schema)}
    found: dict[str, set[uuid.UUID]] = {}
    for name, ids in _semillas().items():
        existing = _existingPks(db, _table(name), ids)
        if existing:
            found[name] = existing

    changed = True
    while changed:  # cierre transitivo por claves foráneas (dependientes de dependientes)
        changed = False
        for parentName in list(found):
            for child in tables.values():
                if child.name not in present:  # la base no tiene esa tabla (p. ej., una base de prueba parcial): no puede tener datos
                    continue
                for fk in child.foreign_keys:
                    if fk.column.table.name != parentName or not fk.column.primary_key:
                        continue
                    childPk = _pk(child)
                    dependents: set[uuid.UUID] = set()
                    for chunk in _chunks(list(found[parentName])):
                        dependents.update(db.scalars(select(childPk).where(fk.parent.in_(chunk))).all())
                    new = dependents - found.get(child.name, set())
                    if new:
                        found.setdefault(child.name, set()).update(new)
                        changed = True
    result.existentes = found

    for name in found:
        if name not in TABLAS_PERMITIDAS:
            result.bloqueos.append(f"Hay {len(found[name])} registro(s) en {name} que el procedimiento no puede eliminar "
                                   f"(auditoría o tabla no prevista).")
    result.orden = _deleteOrder(found)
    return result


def _deleteOrder(found: dict[str, set[uuid.UUID]]) -> list[str]:
    """Orden seguro de borrado: una tabla se borra cuando ninguna tabla pendiente la referencia (hijas primero, padres después)."""
    parentsOf: dict[str, set[str]] = {name: set() for name in found}
    for name in found:
        for fk in _table(name).foreign_keys:
            parent = fk.column.table.name
            if parent in found and parent != name:
                parentsOf[name].add(parent)
    order: list[str] = []
    remaining = {name: set(parents) for name, parents in parentsOf.items()}
    while remaining:
        ready = sorted(name for name in remaining
                       if not any(name in parents for other, parents in remaining.items() if other != name))
        if not ready:
            raise LimpiezaBloqueada("Ciclo de claves foráneas entre tablas demo: no se puede ordenar la limpieza.")
        for name in ready:
            order.append(name)
            del remaining[name]
    return order


def execute(cleanup: CleanupPlan, sessionFactory: sessionmaker) -> dict[str, int]:
    """Borra el plan en una transacción. Ante cualquier error, deshace todo."""
    if cleanup.bloqueada:
        raise LimpiezaBloqueada("La limpieza está bloqueada:\n- " + "\n- ".join(cleanup.bloqueos))
    borrados: dict[str, int] = {}
    session = sessionFactory()
    try:
        for name in cleanup.orden:
            ids = cleanup.existentes.get(name)
            if not ids:
                continue
            table = _table(name)
            pk = _pk(table)
            total = 0
            for chunk in _chunks(sorted(ids, key=str)):
                total += session.execute(delete(table).where(pk.in_(chunk))).rowcount or 0
            borrados[name] = total
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return borrados
