# Exportación de pacientes (CSV): propietario, moderador y operador (solo sus pacientes), por selección o con el listado filtrado.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_patient_export.py -v

import csv
import io
import json
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.services import institutionPatients as patients
from tests.test_account_deletion import db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import admin, api  # noqa: F401 - fixtures
from tests.test_institution_patients import addOperator, patientData
from tests.test_institutions import expectError, institutional, team  # noqa: F401 - fixtures


def rowsOf(content: bytes) -> list[dict[str, str]]:
    text = content.decode("utf-8")
    assert text.startswith("﻿"), "el CSV lleva BOM para que Excel reconozca las tildes"
    reader = csv.reader(io.StringIO(text[1:]), delimiter=";")
    header = next(reader)
    assert tuple(header) == patients.PATIENT_EXPORT_COLUMNS
    return [dict(zip(header, row)) for row in reader]


def auditOf(db, action: str) -> list[Audit]:
    db.expire_all()
    return list(db.scalars(select(Audit).where(Audit.accion == action)))


@pytest.fixture
def clinic(db, mails, team):
    """Dos pacientes: uno a cargo de la operadora y otro a cargo de un segundo operador (lo registró el moderador)."""
    second = addOperator(db, team)
    mine = patients.createPatient(db, team.operator, team.id, patientData(nombre="Ana", apellido="Zapata", dni="40000001"))
    theirs = patients.createPatient(db, team.moderator, team.id, patientData(
        nombre="Dario", apellido="Benitez", dni="40000009", idInstitucionUsuarioResponsable=second.idInstitucionUsuario))
    return SimpleNamespace(mine=mine, theirs=theirs, second=second)


def test_propietario_exporta_todos_los_pacientes_con_sus_datos_administrativos(db, mails, team, clinic):
    rows = rowsOf(patients.exportPatients(db, team.owner, team.id, alcance="TODOS")[0])
    assert sorted(row["Nombre"] for row in rows) == ["Ana", "Dario"]
    dario = next(row for row in rows if row["Nombre"] == "Dario")
    assert dario["Documento"] == "40000009" and dario["Operador responsable"]  # el propietario ve documento y responsable
    assert dario["Estado"] == "Activo" and dario["Fecha de nacimiento"] == "02/01/1980"


def test_moderador_exporta_todos_los_pacientes(db, mails, team, clinic):
    rows = rowsOf(patients.exportPatients(db, team.moderator, team.id, alcance="TODOS")[0])
    assert len(rows) == 2


def test_operador_exporta_solo_sus_pacientes(db, mails, team, clinic):
    rows = rowsOf(patients.exportPatients(db, team.operator, team.id, alcance="TODOS")[0])
    assert [row["Nombre"] for row in rows] == ["Ana"]
    assert rows[0]["Documento"] == "40000001"  # a su cargo: sus datos de identificación sí salen


def test_operador_no_exporta_un_paciente_ajeno_ni_en_una_seleccion(db, mails, team, clinic):
    expectError("DATOS_INVALIDOS", patients.exportPatients, db, team.operator, team.id, alcance="SELECCION",
                ids=[clinic.theirs.idPerfilMedicion])
    mixed = [clinic.mine.idPerfilMedicion, clinic.theirs.idPerfilMedicion]
    expectError("DATOS_INVALIDOS", patients.exportPatients, db, team.operator, team.id, alcance="SELECCION", ids=mixed)


def test_seleccion_exporta_solo_las_personas_marcadas(db, mails, team, clinic):
    rows = rowsOf(patients.exportPatients(db, team.owner, team.id, alcance="SELECCION",
                                          ids=[clinic.theirs.idPerfilMedicion])[0])
    assert [row["Nombre"] for row in rows] == ["Dario"]


def test_seleccion_vacia_o_inexistente_no_exporta(db, mails, team, clinic):
    expectError("DATOS_INVALIDOS", patients.exportPatients, db, team.owner, team.id, alcance="SELECCION", ids=[])
    expectError("DATOS_INVALIDOS", patients.exportPatients, db, team.owner, team.id, alcance="SELECCION", ids=[uuid.uuid4()])


def test_todos_respeta_busqueda_responsable_y_estado(db, mails, team, clinic):
    by_name = rowsOf(patients.exportPatients(db, team.owner, team.id, alcance="TODOS", busqueda="benitez")[0])
    assert [row["Nombre"] for row in by_name] == ["Dario"]
    by_responsable = rowsOf(patients.exportPatients(db, team.owner, team.id, alcance="TODOS",
                                                    idResponsable=clinic.second.idInstitucionUsuario)[0])
    assert [row["Nombre"] for row in by_responsable] == ["Dario"]
    assert rowsOf(patients.exportPatients(db, team.owner, team.id, alcance="TODOS", estado="BAJA")[0]) == []


def test_quien_no_pertenece_no_exporta_y_queda_auditado(db, mails, team, clinic):
    stranger = institutional(db, "ajena@example.com", "ajena")
    expectError("INSTITUCION_NO_ENCONTRADA", patients.exportPatients, db, stranger, team.id, alcance="TODOS")
    assert [f.observacion for f in auditOf(db, "EXPORTACION_FALLIDA")] == ["Motivo: INSTITUCION_NO_ENCONTRADA"]


def test_cada_exportacion_queda_en_la_auditoria_solo_con_cantidades(db, mails, team, clinic):
    patients.exportPatients(db, team.owner, team.id, alcance="TODOS")
    patients.exportPatients(db, team.operator, team.id, alcance="TODOS")
    completed = auditOf(db, "EXPORTACION_COMPLETADA")
    assert sorted(json.loads(event.datosNuevos)["cantidadRegistros"] for event in completed) == [1, 2]
    for event in completed:
        assert json.loads(event.datosNuevos)["tipoDatos"] == "PACIENTES_INSTITUCION"
        assert "Zapata" not in event.datosNuevos and "40000001" not in event.datosNuevos


def test_http_exporta_para_todo_el_equipo_y_valida_el_pedido(db, mails, team, clinic, api):
    base = f"/api/v1/institutions/{team.id}/patients/export"
    owner = api(team.owner).post(base, json={"alcance": "TODOS"})
    assert owner.status_code == 200 and owner.headers["content-type"].startswith("text/csv")
    assert owner.headers["content-disposition"].startswith("attachment; filename=")
    operator = api(team.operator).post(base, json={"alcance": "TODOS"})
    assert operator.status_code == 200 and len(rowsOf(operator.content)) == 1
    assert api(team.owner).post(base, json={"alcance": "ROBOT"}).status_code == 422
    foreign = api(team.operator).post(base, json={"alcance": "SELECCION", "idsPerfilMedicion": [str(clinic.theirs.idPerfilMedicion)]})
    assert foreign.status_code >= 400 and foreign.json()["codigo"] == "DATOS_INVALIDOS"
