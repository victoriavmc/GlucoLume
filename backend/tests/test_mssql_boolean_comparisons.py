# SQL Server no tiene el tipo booleano: SQLAlchemy convierte `columna.is_(True)` en «columna IS 1», que T-SQL rechaza (error 102, «Incorrect syntax near '1'»),
# mientras SQLite lo acepta, así que las pruebas con SQLite no lo detectan. Pasó en notifications.notifyGroupMeasurement (el aviso al grupo nunca se enviaba
# en SQL Server y el error quedaba tragado por un try/except). Esta guarda impide volver a escribirlo en cualquier lugar del código de la aplicación.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_mssql_boolean_comparisons.py -v

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
FORBIDDEN = re.compile(r"\.(?:is_|isnot|is_not)\(\s*(?:True|False)\s*\)")


def test_no_se_compara_un_bit_con_is_true_ni_is_false():
    offenders = []
    for path in sorted(APP.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if FORBIDDEN.search(line):
                offenders.append(f"{path.relative_to(APP.parent)}:{number}: {line.strip()}")
    assert not offenders, "SQL Server rechaza «IS 1»/«IS 0»: comparar con == True / == False.\n" + "\n".join(offenders)
