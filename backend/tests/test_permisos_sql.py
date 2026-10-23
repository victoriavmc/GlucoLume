# Permisos de SQL Server (H-02): verificaciones ESTATICAS de los scripts de database/reference. No se ejecuta nada contra ninguna base (no hay SQL
# Server en las pruebas): leen el texto de los scripts. La parte dinamica —que el codigo solo borre tablas con DELETE concedido— la hace la fixture
# autouse `deleteGrants` de tests/conftest.py durante toda la suite. Lo que esto NO prueba: que T-SQL compile y se comporte como se espera en un
# servidor real; eso lo verifica quien administra la instancia con GlucoLume_permisos_verificar.sql (docs/SEGURIDAD.md, §5.1).

import re
from pathlib import Path

import pytest

import app.models as modelsPackage  # noqa: F401
from app.db.base import Base
from tests.conftest import _grantedDeletes

REFERENCE = Path(__file__).resolve().parents[2] / "database" / "reference"


def script(name: str) -> str:
    return (REFERENCE / name).read_text(encoding="utf-8")


PERMISOS = script("GlucoLume_permisos.sql")
GATED = {
    "GlucoLume_permisos.sql": "APLICAR_PERMISOS_GLUCOLUME",
    "GlucoLume_permisos_revertir.sql": "REVERTIR_PERMISOS_GLUCOLUME",
    "GlucoLume_permisos_quitar_roles_fijos.sql": "QUITAR_ROLES_FIJOS_GLUCOLUME",
    "GlucoLume_permisos_restaurar_roles_fijos.sql": "RESTAURAR_ROLES_FIJOS_GLUCOLUME",
    "GlucoLume_agregar_puente_credencial.sql": "AGREGAR_PUENTE_CREDENCIAL",
}


def modelTables() -> set[str]:
    import importlib
    import pkgutil

    for module in pkgutil.iter_modules(modelsPackage.__path__):
        importlib.import_module(f"app.models.{module.name}")
    return {table.name for table in Base.metadata.tables.values()}


@pytest.mark.parametrize("name, token", GATED.items())
def test_cada_script_que_modifica_permisos_exige_una_confirmacion_explicita_y_no_ejecuta_sin_ella(name, token):
    text = script(name)
    assert ":on error exit" in text
    assert f"N'$(CONFIRMAR)' <> N'{token}'" in text
    gate = text.index(f"N'$(CONFIRMAR)' <> N'{token}'")
    assert text.index("SET NOEXEC ON", gate) < text.index("COMMIT TRANSACTION", gate)
    assert text.rstrip().endswith("SET NOEXEC OFF;\nGO")  # no deja la sesion sin ejecutar


@pytest.mark.parametrize("name", [*GATED, "GlucoLume_permisos_verificar.sql"])
def test_los_scripts_no_crean_inicios_de_sesion_ni_llevan_contrasenas_ni_borran_datos(name):
    code = re.sub(r"--[^\n]*", "", script(name)).upper()
    for forbidden in ("CREATE LOGIN", "ALTER LOGIN", "PASSWORD", "DROP TABLE", "TRUNCATE", "DROP DATABASE", "DROP USER", "ALTER ROLE DB_OWNER ADD"):
        assert forbidden not in code, forbidden
    if name != "GlucoLume_permisos_verificar.sql":
        assert not re.search(r"\bDELETE\s+FROM\b", code)  # solo la verificacion usa DELETE TOP (0) FROM


def test_el_script_de_permisos_es_idempotente():
    code = re.sub(r"--[^\n]*", "", PERMISOS)
    # Todo CREATE esta protegido por una comprobacion de existencia; ALTER ROLE ... ADD MEMBER, por IS_ROLEMEMBER.
    for create in re.finditer(r"CREATE (?:ROLE|USER)", code):
        before = code[max(0, create.start() - 140):create.start()]
        assert "IS NULL" in before, code[create.start():create.start() + 60]
    for add in re.finditer(r"ALTER ROLE [^;]*ADD MEMBER", code):
        assert "IS_ROLEMEMBER" in code[max(0, add.start() - 140):add.start()]
    assert "SET XACT_ABORT ON" in code and code.count("BEGIN TRANSACTION") == code.count("COMMIT TRANSACTION") == 1


def test_la_api_no_tiene_delete_de_esquema_y_solo_borra_tablas_que_existen():
    granted = _grantedDeletes()
    assert not re.search(r"GRANT[^;]*\bDELETE\b[^;]*ON SCHEMA", PERMISOS)  # el DELETE se concede tabla por tabla
    assert "REVOKE DELETE ON SCHEMA::dbo FROM rol_glucolume_api" in PERMISOS  # y se revoca el que dio una version anterior
    assert set(granted) == {"rol_glucolume_api", "rol_glucolume_retencion"}
    assert granted["rol_glucolume_api"] <= granted["rol_glucolume_retencion"]
    assert not {"Auditoria", "AuditoriaContexto"} & granted["rol_glucolume_api"]  # la auditoria es de solo agregado para la API
    assert {"Auditoria", "AuditoriaContexto"} <= granted["rol_glucolume_retencion"]
    assert re.search(r"DENY UPDATE, DELETE ON OBJECT::dbo\.Auditoria TO rol_glucolume_api;", PERMISOS)
    assert re.search(r"DENY UPDATE, DELETE ON OBJECT::dbo\.AuditoriaContexto TO rol_glucolume_api;", PERMISOS)
    tables = modelTables()
    assert (granted["rol_glucolume_api"] | granted["rol_glucolume_retencion"]) <= tables
    # Tablas de negocio que se dan de baja con estados y nunca con DELETE: la API no puede borrarlas.
    for kept in ("Institucion", "InstitucionUsuario", "PerfilMedicion", "Dispositivo", "Grupo", "GrupoUsuario", "Matriz"):
        assert kept in tables and kept not in granted["rol_glucolume_api"]


def test_las_credenciales_de_puente_son_de_solo_lectura_para_la_api():
    assert "DENY INSERT, UPDATE, DELETE ON OBJECT::dbo.PuenteCredencial TO rol_glucolume_api" in PERMISOS
    assert "GRANT UPDATE (fechaUltimoUso) ON OBJECT::dbo.PuenteCredencial TO rol_glucolume_api" in PERMISOS
    assert "PuenteCredencial" not in _grantedDeletes()["rol_glucolume_api"]


def test_quitar_y_restaurar_roles_fijos_son_simetricos_y_revertir_los_exige_restaurados():
    remove, restore, revert = (script(f"GlucoLume_permisos_{name}_fijos.sql") if name != "revertir" else script("GlucoLume_permisos_revertir.sql")
                               for name in ("quitar_roles", "restaurar_roles", "revertir"))
    prop = "GlucoLume_roles_fijos_quitados"
    assert prop in remove and prop in restore and prop in revert
    for role in ("db_datawriter", "db_datareader"):
        assert f"ALTER ROLE {role} DROP MEMBER" in remove and f"ALTER ROLE {role} ADD MEMBER" in restore
    assert "db_owner" not in re.sub(r"--[^\n]*", "", remove + restore)  # nunca toca db_owner
    assert "IS_ROLEMEMBER(N'rol_glucolume_api'" in remove  # exige haber aplicado antes el script de permisos
    assert revert.index(prop) < revert.index("DROP ROLE")  # no borra los roles de GlucoLume si faltan restaurar los fijos


def test_la_verificacion_comprueba_los_delete_y_los_roles_de_la_cuenta():
    verify = script("GlucoLume_permisos_verificar.sql")
    assert "DELETE TOP (0) FROM dbo.Institucion" in verify and "DELETE TOP (0) FROM dbo.SesionUsuario" in verify
    assert "SELECT r.name AS rolDeLaCuenta" in verify
    assert "ROLLBACK TRANSACTION" in verify and "REVERT;" in verify
