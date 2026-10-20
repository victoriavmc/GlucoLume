# Esquema SQL consolidado (DEC-02): database/reference/GlucoLume_DB_v5.sql es la referencia de una instalación nueva y debe coincidir con
# los modelos del backend. Reemplaza a las comprobaciones contra scripts incrementales, que se retiraron a propósito.
#
#     python -m pytest tests/test_reference_schema.py -v
#
# Solo compara texto: no ejecuta SQL ni demuestra el estado de una base ya instalada (eso lo resuelve schemaCompat en tiempo de ejecución).

import importlib
import pkgutil
import re

import app.models as modelsPackage
from app.db.base import Base

# Restricciones que los modelos declaran y el esquema v5 todavía no incluye. Vacío desde el 19/10/2026: las 6 CK_Medicion_* de glucosa
# del dispositivo se agregaron a v5. Si aparece una diferencia nueva, la prueba falla.
KNOWN_SCHEMA_GAPS: set[str] = set()


def _metadata():
    for module in pkgutil.iter_modules(modelsPackage.__path__):
        importlib.import_module(f"app.models.{module.name}")
    return Base.metadata


def _schemaTables(schema: str) -> dict[str, set[str]]:
    return {match.group(1): set(re.findall(r"^\t\[(\w+)\]", match.group(2), re.M))
            for match in re.finditer(r"CREATE TABLE \[dbo\]\.\[(\w+)\]\((.*?)\n\)", schema, re.S)}


def test_las_tablas_y_columnas_del_esquema_consolidado_coinciden_con_los_modelos(referenceSchema):
    tables = _schemaTables(referenceSchema)
    models = {table.name: {column.name for column in table.c} for table in _metadata().tables.values()}
    assert set(tables) == set(models)
    assert {name: models[name] ^ tables[name] for name in models if models[name] != tables[name]} == {}


def test_las_restricciones_con_nombre_de_los_modelos_estan_en_el_esquema_salvo_las_diferencias_registradas(referenceSchema):
    named = {constraint.name for table in _metadata().tables.values() for constraint in table.constraints
             if constraint.name and constraint.name.startswith(("CK_", "UQ_", "FK_"))}
    missing = {name for name in named if f"[{name}]" not in referenceSchema}
    assert missing == KNOWN_SCHEMA_GAPS


def _checkTokens(expression: str) -> tuple[frozenset, frozenset, frozenset]:
    """Lo que define a un CHECK sin depender de cómo SQL Server reescribe la expresión (paréntesis, orden, IN → OR): los valores
    literales, las columnas y los números."""
    return (frozenset(re.findall(r"N'([^']*)'", expression)), frozenset(re.findall(r"\[(\w+)\]", expression)),
            frozenset(re.findall(r"\((\d+)\)", expression)))


def test_cada_check_del_esquema_admite_los_mismos_valores_que_el_modelo(referenceSchema):
    from sqlalchemy import CheckConstraint

    schema = {match.group(1): match.group(2)
              for match in re.finditer(r"CONSTRAINT \[(CK_\w+)\] CHECK  \((.*)\)\r?$", referenceSchema, re.M)}
    checks = [constraint for table in _metadata().tables.values() for constraint in table.constraints
              if isinstance(constraint, CheckConstraint) and constraint.name in schema]
    assert len(checks) > 100
    assert [c.name for c in checks if _checkTokens(str(c.sqltext)) != _checkTokens(schema[c.name])] == []


def test_el_esquema_consolidado_no_crea_inicios_de_sesion_ni_borra_objetos(referenceSchema):
    upper = referenceSchema.upper()
    assert "CREATE LOGIN" not in upper and "DROP " not in upper and "DELETE FROM" not in upper and "TRUNCATE " not in upper
    assert "ALTER ROLE [DB_OWNER]" not in upper  # la cuenta de la aplicación no es dueña de la base


def test_schema_compat_vuelve_a_comprobar_un_si_vencido(monkeypatch):
    # Una base restaurada sin la columna se detecta sin reiniciar el backend: el «sí» dura POSITIVE_TTL_SECONDS.
    from types import SimpleNamespace

    from app.services import schemaCompat

    answers, clock = [1, None], [1000.0]
    db = SimpleNamespace(get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="mssql")), scalar=lambda *a, **k: answers.pop(0))
    monkeypatch.setattr(schemaCompat.time, "monotonic", lambda: clock[0])
    schemaCompat.reset()
    try:
        assert schemaCompat.hasColumn(db, "Medicion", "x") is True
        clock[0] += schemaCompat.POSITIVE_TTL_SECONDS - 1
        assert schemaCompat.hasColumn(db, "Medicion", "x") is True and answers == [None]  # todavía en caché
        clock[0] += 2
        assert schemaCompat.hasColumn(db, "Medicion", "x") is False and answers == []  # se volvió a consultar
    finally:
        schemaCompat.reset()



def test_los_indices_de_los_modelos_estan_en_el_esquema_con_el_mismo_filtro(referenceSchema):
    # Los índices únicos filtrados (UX_*) sostienen reglas de negocio (un administrador vigente, un DNI por institución, una matriz activa);
    # hasta el 19/10/2026 v5 no los tenía. Se comparan nombre, tabla, unicidad, columnas, columnas incluidas y los valores del filtro.
    schema = {match.group(2): match for match in re.finditer(
        r"^CREATE (UNIQUE )?NONCLUSTERED INDEX \[(\w+)\] ON \[dbo\]\.\[(\w+)\] \(([^)]*)\)(?: INCLUDE \(([^)]*)\))?(?: WHERE \((.*)\))?\r?$",
        referenceSchema, re.M)}
    for table in _metadata().tables.values():
        for index in table.indexes:
            found = schema.get(index.name)
            assert found is not None, index.name
            assert found.group(3) == table.name and bool(found.group(1)) == bool(index.unique), index.name
            assert re.findall(r"\[(\w+)\]", found.group(4)) == [column.name for column in index.columns], index.name
            include = [str(column) for column in index.dialect_options["mssql"].get("include") or []]
            assert re.findall(r"\[(\w+)\]", found.group(5) or "") == include, index.name
            where = index.dialect_options["mssql"].get("where")
            assert _checkTokens(str(where) if where is not None else "") == _checkTokens(found.group(6) or ""), index.name


def test_schema_check_prepara_validaciones_que_solo_cuentan():
    # GL-05: antes de agregar a una base con datos un índice único o un CHECK faltante se cuentan duplicados o violaciones; nunca se leen filas.
    from app.cli import schemaCheck

    expected = schemaCheck.expected()
    assert len(expected["tablas"]) == 33 and len(expected["pk"]) == 33 and len(expected["indices"]) == 16
    queries = schemaCheck.validationQueries({"check": {"faltan": ["CK_Medicion_lecturas"], "sobran": []},
                                             "unicos": {"faltan": ["UX_Usuario_administradorUnico"], "sobran": []}})
    assert len(queries) == 2 and all(q.startswith("SELECT N'") and "COUNT_BIG(*)" in q for q in queries)
    assert all(not re.search(r"\b(UPDATE|DELETE|INSERT|ALTER|CREATE|DROP)\b", q) for q in queries)
    [unique] = [q for q in queries if "UX_Usuario_administradorUnico" in q]
    assert "HAVING COUNT_BIG(*) > 1" in unique and "[estado]<>N'ELIMINADO'" in unique
