# Exportación del personal (CSV): solo propietario y moderador, con la selección o con el listado filtrado, y cada intento auditado.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_personnel_export.py -v

import csv
import io
import json
import uuid

import pytest
from sqlalchemy import select

from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.services import personnel
from tests.test_account_deletion import db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import admin, api  # noqa: F401 - fixtures
from tests.test_institutions import expectError, institutional, relationOf, team  # noqa: F401 - fixtures


def rowsOf(content: bytes) -> list[list[str]]:
    text = content.decode("utf-8")
    assert text.startswith("﻿"), "el CSV lleva BOM para que Excel reconozca las tildes"
    return list(csv.reader(io.StringIO(text[1:]), delimiter=";"))


def auditOf(db, action: str) -> list[Audit]:
    db.expire_all()
    return list(db.scalars(select(Audit).where(Audit.accion == action).order_by(Audit.idAuditoria)))


def test_propietario_exporta_todo_el_personal_con_una_fila_por_persona(db, mails, team):
    content, filename = personnel.exportPersonnel(db, team.owner, team.id, alcance="TODOS")
    rows = rowsOf(content)
    assert rows[0] == list(personnel.EXPORT_COLUMNS)
    assert len(rows) == 4  # encabezado + propietaria, moderador y operadora
    assert {row[2] for row in rows[1:]} == {"duenia@example.com", "moderador@example.com", "operadora@example.com"}
    assert filename.startswith("personal-institucion-") and filename.endswith(".csv")


def test_moderador_exporta_solo_las_personas_seleccionadas(db, mails, team):
    ids = [relationOf(db, team, team.operator).idInstitucionUsuario]
    rows = rowsOf(personnel.exportPersonnel(db, team.moderator, team.id, alcance="SELECCION", idsInstitucionUsuario=ids)[0])
    assert len(rows) == 2
    assert rows[1][2] == "operadora@example.com" and rows[1][3] == "Operador/a" and rows[1][5] == "Activo"


def test_todos_respeta_los_filtros_del_listado(db, mails, team):
    rows = rowsOf(personnel.exportPersonnel(db, team.owner, team.id, alcance="TODOS", rol="OPERADOR")[0])
    assert len(rows) == 2 and rows[1][2] == "operadora@example.com"


def test_operador_y_quien_no_pertenece_no_exportan_y_el_intento_queda_auditado(db, mails, team):
    with pytest.raises(AuthError) as denied:
        personnel.exportPersonnel(db, team.operator, team.id, alcance="TODOS")
    assert denied.value.code == "PERMISO_INSUFICIENTE"
    stranger = institutional(db, "ajeno@example.com", "ajeno")
    with pytest.raises(AuthError) as hidden:
        personnel.exportPersonnel(db, stranger, team.id, alcance="TODOS")
    assert hidden.value.code == "INSTITUCION_NO_ENCONTRADA"
    failures = auditOf(db, "EXPORTACION_FALLIDA")
    assert sorted(f.observacion for f in failures) == ["Motivo: INSTITUCION_NO_ENCONTRADA", "Motivo: PERMISO_INSUFICIENTE"]
    assert auditOf(db, "EXPORTACION_COMPLETADA") == []


def test_una_seleccion_invalida_no_exporta_y_queda_como_fallida(db, mails, team):
    expectError("DATOS_INVALIDOS", personnel.exportPersonnel, db, team.owner, team.id, alcance="SELECCION", idsInstitucionUsuario=[])
    expectError("DATOS_INVALIDOS", personnel.exportPersonnel, db, team.owner, team.id, alcance="SELECCION",
                idsInstitucionUsuario=[uuid.uuid4()])
    assert [f.observacion for f in auditOf(db, "EXPORTACION_FALLIDA")] == ["Motivo: DATOS_INVALIDOS", "Motivo: DATOS_INVALIDOS"]
    assert auditOf(db, "EXPORTACION_COMPLETADA") == []


def test_la_exportacion_completada_registra_cuantas_personas_salieron_sin_datos_personales(db, mails, team):
    personnel.exportPersonnel(db, team.owner, team.id, alcance="TODOS")
    [event] = auditOf(db, "EXPORTACION_COMPLETADA")
    data = json.loads(event.datosNuevos)
    assert data["cantidadRegistros"] == 3 and data["tipoDatos"] == "PERSONAL_INSTITUCION" and data["formato"] == "CSV"
    assert "example.com" not in event.datosNuevos and "operadora" not in event.datosNuevos


def test_los_valores_que_empiezan_con_formula_se_escapan(db, mails, team):
    team.operator.nombre = '=HYPERLINK("http://example.com")'
    db.commit()
    rows = rowsOf(personnel.exportPersonnel(db, team.owner, team.id, alcance="TODOS", rol="OPERADOR")[0])
    assert rows[1][0] == '\'=HYPERLINK("http://example.com")'


def test_http_exporta_para_propietario_y_moderador_y_rechaza_al_operador(db, mails, team, api):
    base = f"/api/v1/institutions/{team.id}/personnel/export"
    ok = api(team.moderator).post(base, json={"alcance": "TODOS"})
    assert ok.status_code == 200 and ok.headers["content-type"].startswith("text/csv")
    assert ok.headers["content-disposition"].startswith("attachment; filename=")
    assert ok.headers["cache-control"] == "no-store"
    assert api(team.operator).post(base, json={"alcance": "TODOS"}).status_code == 403
    assert api(team.owner).post(base, json={"alcance": "ROBOT"}).status_code == 422
    selected = api(team.owner).post(base, json={"alcance": "SELECCION", "idsInstitucionUsuario": [str(uuid.uuid4())]})
    assert selected.status_code >= 400 and selected.json()["codigo"] == "DATOS_INVALIDOS"
