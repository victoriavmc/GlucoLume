# Formatos de exportación (CSV, Excel y PDF): mismo contenido en los tres, el CSV sigue siendo el por defecto y cada formato queda auditado.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_table_export.py -v

import io
import json

import openpyxl
import pytest
from sqlalchemy import select

from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.services import matrix as matrices
from app.services import personnel
from app.services.csvExport import csvBytes
from app.services.tableExport import mediaTypeOf, tableFile
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import admin, api  # noqa: F401 - fixtures
from tests.test_institutions import expectError, institutional, relationOf, team  # noqa: F401 - fixtures
from tests.test_matrices import newMatrix, platform, rule  # noqa: F401 - fixtures

COLUMNS = ("Nombre", "Correo", "Observación")
ROWS = [["Ana", "ana@example.com", "'=2+2"], ["Bruno", "bruno@example.com", "Sin novedades"]]  # ya escapado por csvText


def auditOf(db, action: str) -> list[Audit]:
    db.expire_all()
    return list(db.scalars(select(Audit).where(Audit.accion == action).order_by(Audit.idAuditoria)))


def test_el_csv_sigue_igual_y_es_el_formato_por_defecto():
    content, filename = tableFile("csv", "datos-prueba", "Datos", COLUMNS, ROWS, nowForDb())
    assert content == csvBytes(COLUMNS, ROWS)
    assert filename == "datos-prueba.csv"


def test_el_excel_tiene_encabezado_filas_y_no_ejecuta_formulas():
    content, filename = tableFile("xlsx", "datos-prueba", "Pacientes: enero/2026", COLUMNS, ROWS, nowForDb())
    assert filename == "datos-prueba.xlsx"
    book = openpyxl.load_workbook(io.BytesIO(content))
    sheet = book.active
    assert sheet.title == "Pacientes  enero 2026"  # Excel no admite / ni : en el nombre de la hoja
    assert [cell.value for cell in sheet[1]] == list(COLUMNS)
    assert [cell.value for cell in sheet[2]] == ROWS[0]
    assert sheet[2][2].data_type == "s"  # el valor escapado queda como texto, nunca como fórmula
    assert sheet.freeze_panes == "A2" and sheet.auto_filter.ref == "A1:C3"


def test_el_pdf_es_un_pdf_en_horizontal_con_el_titulo():
    content, filename = tableFile("pdf", "datos-prueba", "Datos de prueba", COLUMNS, ROWS, nowForDb())
    assert filename == "datos-prueba.pdf"
    assert content.startswith(b"%PDF-") and content.rstrip().endswith(b"%%EOF")


def test_un_pdf_sin_filas_sale_igual_con_solo_el_encabezado():
    content, _ = tableFile("pdf", "vacio", "Vacío", COLUMNS, [], nowForDb())
    assert content.startswith(b"%PDF-")


def test_un_formato_desconocido_no_exporta():
    with pytest.raises(ValueError):
        tableFile("docx", "datos", "Datos", COLUMNS, ROWS, nowForDb())


def test_cada_formato_tiene_su_tipo_de_contenido():
    assert mediaTypeOf("csv").startswith("text/csv")
    assert mediaTypeOf("xlsx") == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert mediaTypeOf("pdf") == "application/pdf"


def test_personal_en_excel_y_pdf_con_la_misma_cantidad_de_personas_y_auditoria(db, mails, team):
    for formato, extension in (("xlsx", ".xlsx"), ("pdf", ".pdf")):
        content, filename = personnel.exportPersonnel(db, team.owner, team.id, alcance="TODOS", formato=formato)
        assert filename.startswith("personal-institucion-") and filename.endswith(extension)
        assert content
    sheet = openpyxl.load_workbook(io.BytesIO(personnel.exportPersonnel(db, team.owner, team.id, alcance="TODOS", formato="xlsx")[0])).active
    assert sheet.max_row == 4  # encabezado + propietaria, moderador y operadora
    assert [cell.value for cell in sheet[1]] == list(personnel.EXPORT_COLUMNS)
    formats = [json.loads(event.datosNuevos)["formato"] for event in auditOf(db, "EXPORTACION_COMPLETADA")]
    assert sorted(formats) == ["PDF", "XLSX", "XLSX"]


def test_un_intento_sin_permiso_en_pdf_queda_auditado_con_su_formato(db, mails, team):
    with pytest.raises(AuthError):
        personnel.exportPersonnel(db, team.operator, team.id, alcance="TODOS", formato="pdf")
    [failure] = auditOf(db, "EXPORTACION_FALLIDA")
    assert json.loads(failure.datosNuevos)["formato"] == "PDF"


def test_http_entrega_el_formato_pedido_y_rechaza_uno_desconocido(db, mails, team, api):
    base = f"/api/v1/institutions/{team.id}/personnel/export"
    excel = api(team.owner).post(f"{base}?formato=xlsx", json={"alcance": "TODOS"})
    assert excel.status_code == 200
    assert excel.headers["content-type"] == mediaTypeOf("xlsx")
    assert excel.headers["content-disposition"].endswith('.xlsx"')
    pdf = api(team.moderator).post(f"{base}?formato=pdf", json={"alcance": "TODOS"})
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-")
    assert api(team.owner).post(f"{base}?formato=docx", json={"alcance": "TODOS"}).status_code == 422
    default = api(team.owner).post(base, json={"alcance": "TODOS"})
    assert default.headers["content-type"].startswith("text/csv")


def test_la_matriz_sale_en_excel_y_en_pdf_con_una_fila_por_regla(db, mails, platform):
    draft = newMatrix(db, platform, rules=(None, rule(sexoModelo="MASCULINO")))
    content, filename = matrices.exportMatrix(db, platform, draft.idMatriz, formato="xlsx")
    assert filename.startswith("matriz-") and filename.endswith(".xlsx")
    sheet = openpyxl.load_workbook(io.BytesIO(content)).active
    assert [cell.value for cell in sheet[1]] == list(matrices.MATRIX_EXPORT_COLUMNS)
    assert sheet.max_row == 3  # encabezado + una fila por regla
    pdf, filename = matrices.exportMatrix(db, platform, draft.idMatriz, formato="pdf")
    assert filename.endswith(".pdf") and pdf.startswith(b"%PDF-")
