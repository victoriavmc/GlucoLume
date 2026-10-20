# SchemaCheck - Diferencias entre una base SQL Server instalada y el esquema que esperan los modelos (GL-05, DEC-02), SOLO LECTURA
#
# Que GlucoLume_DB_v5.sql incluya una pieza no demuestra que la base instalada la tenga. Esta herramienta lee el catálogo (sys.tables,
# sys.columns, sys.check_constraints, sys.foreign_keys, sys.indexes: claves primarias, índices únicos y de consulta) y lo compara con los modelos SQLAlchemy, que coinciden con v5
# (tests/test_reference_schema.py). No ejecuta DDL ni modifica datos: solo SELECT sobre vistas del sistema.
#
#     python -m app.cli.schemaCheck                 # base configurada en el .env (requiere autorización si es la real)
#     python -m app.cli.schemaCheck --url <URL>     # otra base (p. ej. una copia descartable)
#
# Sale con 0 si no hay diferencias y 1 si las hay. Las diferencias se corrigen con un procedimiento controlado (docs/BASE_DE_DATOS.md §3),
# nunca aplicando v5 completo sobre una base con datos.

import argparse
import importlib
import pkgutil
import sys

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint, create_engine, text
from sqlalchemy.dialects import mssql
from sqlalchemy.engine import Connection

import app.models as modelsPackage
from app.db.base import Base


def expected() -> dict[str, set[str]]:
    for module in pkgutil.iter_modules(modelsPackage.__path__):
        importlib.import_module(f"app.models.{module.name}")
    tables = Base.metadata.tables.values()
    return {
        "tablas": {table.name for table in tables},
        "columnas": {f"{table.name}.{column.name}" for table in tables for column in table.c},
        "check": {c.name for table in tables for c in table.constraints if isinstance(c, CheckConstraint) and c.name},
        "fk": {c.name for table in tables for c in table.constraints if isinstance(c, ForeignKeyConstraint) and c.name},
        "unicos": ({c.name for table in tables for c in table.constraints if isinstance(c, UniqueConstraint) and c.name}
                   | {index.name for table in tables for index in table.indexes if index.unique and index.name}),
        "indices": {index.name for table in tables for index in table.indexes if not index.unique and index.name},
        "pk": {f"{table.name}({','.join(c.name for c in table.primary_key.columns)})" for table in tables if table.primary_key.columns},
    }


# Objetos propios de SSMS (diagramas de base de datos): no son parte del esquema de GlucoLume.
IGNORED = {"sysdiagrams", "UK_principal_name", "sysdiagrams.definition", "sysdiagrams.diagram_id", "sysdiagrams.name",
           "sysdiagrams.principal_id", "sysdiagrams.version", "sysdiagrams(diagram_id)"}


def installed(connection: Connection) -> dict[str, set[str]]:
    rows = lambda sql: {row[0] for row in connection.execute(text(sql))} - IGNORED  # noqa: E731
    return {
        "tablas": rows("SELECT name FROM sys.tables WHERE schema_id = SCHEMA_ID('dbo') AND is_ms_shipped = 0"),
        "columnas": rows("SELECT t.name + '.' + c.name FROM sys.columns c JOIN sys.tables t ON t.object_id = c.object_id "
                         "WHERE t.schema_id = SCHEMA_ID('dbo') AND t.is_ms_shipped = 0"),
        "check": rows("SELECT name FROM sys.check_constraints"),
        "fk": rows("SELECT name FROM sys.foreign_keys"),
        "unicos": rows("SELECT name FROM sys.indexes WHERE is_unique = 1 AND is_primary_key = 0 AND name IS NOT NULL "
                       "AND object_id IN (SELECT object_id FROM sys.tables WHERE is_ms_shipped = 0)"),
        "indices": rows("SELECT name FROM sys.indexes WHERE is_unique = 0 AND type > 0 AND name IS NOT NULL "
                        "AND object_id IN (SELECT object_id FROM sys.tables WHERE is_ms_shipped = 0)"),
        "pk": rows("SELECT t.name + '(' + STRING_AGG(c.name, ',') WITHIN GROUP (ORDER BY ic.key_ordinal) + ')' FROM sys.indexes i "
                   "JOIN sys.tables t ON t.object_id = i.object_id JOIN sys.index_columns ic ON ic.object_id = i.object_id "
                   "AND ic.index_id = i.index_id JOIN sys.columns c ON c.object_id = i.object_id AND c.column_id = ic.column_id "
                   "WHERE i.is_primary_key = 1 AND t.is_ms_shipped = 0 GROUP BY t.name"),
    }


def compare(connection: Connection) -> dict[str, dict[str, list[str]]]:
    """{categoría: {'faltan': [...], 'sobran': [...]}} solo con las categorías que difieren."""
    want, have = expected(), installed(connection)
    result = {}
    for key in want:
        missing, extra = sorted(want[key] - have[key]), sorted(have[key] - want[key])
        if missing or extra:
            result[key] = {"faltan": missing, "sobran": extra}
    return result


def validationQueries(differences: dict[str, dict[str, list[str]]]) -> list[str]:
    """Consultas para correr ANTES de agregar a una base con datos los CHECK o índices únicos que faltan. Solo devuelven CONTEOS (cuántos
    grupos duplicados o cuántas filas violarían la regla), nunca valores ni filas. No se ejecutan desde acá."""
    expected()  # carga los modelos
    dialect = mssql.dialect()
    queries = []
    missingChecks = set(differences.get("check", {}).get("faltan", []))
    missingUnique = set(differences.get("unicos", {}).get("faltan", []))
    for table in Base.metadata.tables.values():
        for constraint in table.constraints:
            if isinstance(constraint, CheckConstraint) and constraint.name in missingChecks:
                queries.append(f"SELECT N'{constraint.name}' AS regla, COUNT_BIG(*) AS filasQueLaViolan FROM dbo.[{table.name}] "
                               f"WHERE NOT ({constraint.sqltext});")
        for index in table.indexes:
            if index.unique and index.name in missingUnique:
                columns = ", ".join(f"[{column.name}]" for column in index.columns)
                where = index.dialect_options["mssql"].get("where")
                condition = f" WHERE {where.compile(dialect=dialect, compile_kwargs={'literal_binds': True})}" if where is not None else ""
                queries.append(f"SELECT N'{index.name}' AS indice, COUNT_BIG(*) AS gruposDuplicados FROM (SELECT {columns} FROM "
                               f"dbo.[{table.name}]{condition} GROUP BY {columns} HAVING COUNT_BIG(*) > 1) AS d;")
    return queries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compara la base instalada con el esquema de los modelos (solo lectura).")
    parser.add_argument("--url", default=None, help="URL de SQLAlchemy; sin ella, la base configurada.")
    parser.add_argument("--preparar-validacion", action="store_true",
                        help="Además imprime (sin ejecutarlas) las consultas de conteo de duplicados y violaciones para lo que falta.")
    args = parser.parse_args(argv)
    if args.url:
        engine = create_engine(args.url)
    else:
        from app.db.session import getEngine

        engine = getEngine()
    with engine.connect() as connection:
        differences = compare(connection)
        connection.rollback()
    if not differences:
        print("Sin diferencias: la base instalada tiene las tablas, columnas y restricciones que esperan los modelos (esquema v5).")
        return 0
    for key, diff in differences.items():
        for kind in ("faltan", "sobran"):
            for name in diff[kind]:
                print(f"{key}: {kind} {name}")
    if args.preparar_validacion:
        print()
        print("-- Consultas de validación previa (solo conteos; NO se ejecutaron):")
        for query in validationQueries(differences):
            print(query)
    return 1


if __name__ == "__main__":
    sys.exit(main())
