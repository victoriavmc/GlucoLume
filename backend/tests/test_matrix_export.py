# Exportación de una matriz con sus reglas (CSV): quien la puede ver la exporta; el resto recibe «inexistente» y el intento queda auditado.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_matrix_export.py -v

import csv
import io
import json

from sqlalchemy import select

from app.models.audit import Audit
from app.services import matrix as matrices
from tests.test_account_deletion import db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import admin, api  # noqa: F401 - fixtures
from tests.test_institutions import expectError, institutional, team  # noqa: F401 - fixtures
from tests.test_matrices import activeMatrix, newMatrix, north, platform, rule  # noqa: F401 - fixtures


def rowsOf(content: bytes) -> list[dict[str, str]]:
    text = content.decode("utf-8")
    assert text.startswith("﻿")
    reader = csv.reader(io.StringIO(text[1:]), delimiter=";")
    header = next(reader)
    assert tuple(header) == matrices.MATRIX_EXPORT_COLUMNS
    return [dict(zip(header, row)) for row in reader]


def auditOf(db, action: str) -> list[Audit]:
    db.expire_all()
    return list(db.scalars(select(Audit).where(Audit.accion == action)))


def test_la_plataforma_exporta_una_global_con_una_fila_por_regla(db, mails, platform):
    draft = newMatrix(db, platform, rules=(None, rule(sexoModelo="MASCULINO")))
    rows = rowsOf(matrices.exportMatrix(db, platform, draft.idMatriz)[0])
    assert len(rows) == 2
    assert {row["Código de regla"] for row in rows} == {r.codigoRegla for r in draft.reglas}
    first = rows[0]
    assert (first["Matriz"], first["Origen"], first["Estado"]) == ("Matriz GlucoLume", "Global (GlucoLume)", "Borrador")
    assert first["Referencia base"] == "Fuente de prueba" and first["Glucosa mínima de referencia"] == "70,00"


def test_el_nombre_del_archivo_es_seguro_y_lleva_fecha(db, mails, platform):
    draft = newMatrix(db, platform)
    _, filename = matrices.exportMatrix(db, platform, draft.idMatriz)
    assert filename.startswith("matriz-Matriz-GlucoLume-") and filename.endswith(".csv") and " " not in filename


def test_propietario_y_moderador_exportan_su_matriz_y_la_global_activa(db, mails, team, platform):
    own = activeMatrix(db, team.owner, ambito="INSTITUCION", idInstitucion=team.id, nombre="Matriz Hospital X")
    assert rowsOf(matrices.exportMatrix(db, team.owner, own.idMatriz)[0])[0]["Origen"] == "Hospital X"
    assert rowsOf(matrices.exportMatrix(db, team.moderator, own.idMatriz)[0])[0]["Matriz"] == "Matriz Hospital X"
    global_active = activeMatrix(db, platform)
    assert rowsOf(matrices.exportMatrix(db, team.owner, global_active.idMatriz)[0])[0]["Origen"] == "Global (GlucoLume)"


def test_quien_no_puede_ver_la_matriz_no_la_exporta_y_el_intento_queda_auditado(db, mails, team, north, platform):
    own = newMatrix(db, team.owner, ambito="INSTITUCION", idInstitucion=team.id, nombre="Matriz Hospital X")
    private_draft = newMatrix(db, platform)  # global en borrador: privada
    expectError("MATRIZ_NO_ENCONTRADA", matrices.exportMatrix, db, team.operator, own.idMatriz)  # operador: no administra ni exporta
    expectError("MATRIZ_NO_ENCONTRADA", matrices.exportMatrix, db, north.owner, own.idMatriz)  # otra institución
    expectError("MATRIZ_NO_ENCONTRADA", matrices.exportMatrix, db, platform, own.idMatriz)  # la plataforma no ve matrices privadas
    expectError("MATRIZ_NO_ENCONTRADA", matrices.exportMatrix, db, team.owner, private_draft.idMatriz)  # global en borrador
    failures = auditOf(db, "EXPORTACION_FALLIDA")
    assert len(failures) == 4 and {f.observacion for f in failures} == {"Motivo: MATRIZ_NO_ENCONTRADA"}
    assert auditOf(db, "EXPORTACION_COMPLETADA") == []


def test_cada_exportacion_queda_auditada_con_cuantas_reglas_salieron(db, mails, team):
    matrix = newMatrix(db, team.owner, ambito="INSTITUCION", idInstitucion=team.id, rules=(None, rule(sexoModelo="MASCULINO")))
    matrices.exportMatrix(db, team.owner, matrix.idMatriz)
    [event] = auditOf(db, "EXPORTACION_COMPLETADA")
    data = json.loads(event.datosNuevos)
    assert data["cantidadRegistros"] == 2 and data["tipoDatos"] == "MATRIZ_REGLAS" and data["ambito"] == "INSTITUCION"


def test_una_matriz_sin_reglas_sale_en_una_fila_con_las_reglas_vacias(db, mails, team):
    empty = newMatrix(db, team.owner, ambito="INSTITUCION", idInstitucion=team.id, rules=())
    rows = rowsOf(matrices.exportMatrix(db, team.owner, empty.idMatriz)[0])
    assert len(rows) == 1 and rows[0]["Matriz"] == "Matriz GlucoLume" and rows[0]["Código de regla"] == ""


def test_los_limites_sin_valor_salen_como_sin_limite(db, mails, team):
    matrix = newMatrix(db, team.owner, ambito="INSTITUCION", idInstitucion=team.id,
                       rules=(rule(sexoModelo="MASCULINO", edadDesde=None, edadHasta=None),))
    [row] = rowsOf(matrices.exportMatrix(db, team.owner, matrix.idMatriz)[0])
    assert row["Edad desde"] == "Sin límite" and row["Edad hasta"] == "Sin límite"


def test_http_exporta_para_el_propietario_y_responde_404_al_operador(db, mails, team, api):
    matrix = newMatrix(db, team.owner, ambito="INSTITUCION", idInstitucion=team.id)
    base = f"/api/v1/matrices/{matrix.idMatriz}/export"
    ok = api(team.owner).post(base)
    assert ok.status_code == 200 and ok.headers["content-type"].startswith("text/csv")
    assert ok.headers["content-disposition"].startswith("attachment; filename=")
    assert api(team.operator).post(base).status_code == 404
