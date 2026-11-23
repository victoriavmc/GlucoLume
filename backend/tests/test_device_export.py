# Exportación del inventario de dispositivos (CSV, Excel y PDF): selección o listado filtrado, lo que cada cuenta ve, datos del
# dispositivo, y cada intento auditado. Ejecutar desde backend/:
#     python -m pytest tests/test_device_export.py -v

import csv
import io
import uuid

import pytest
from sqlalchemy import func, select

from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.services import device as devices
from app.services import deviceExport
from tests.test_account_deletion import db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import admin, api  # noqa: F401 - fixtures
from tests.test_devices import register
from tests.test_institutions import team  # noqa: F401 - fixtures


def rowsOf(content: bytes) -> list[list[str]]:
    text = content.decode("utf-8")
    assert text.startswith("﻿"), "el CSV lleva BOM para que Excel reconozca las tildes"
    return list(csv.reader(io.StringIO(text[1:]), delimiter=";"))


def globalScope(db, actor):
    return devices.platformScope(db, actor)


def instScope(db, actor, idInstitucion):
    return devices.institutionScope(db, actor, idInstitucion)


def auditCount(db) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(Audit))


@pytest.fixture
def inventory(db, mails, admin, team):
    """Tres dispositivos del inventario global y uno registrado por la propietaria de la institución."""
    first = devices.registerDevice(db, globalScope(db, admin), register("GL-0001"))
    second = devices.registerDevice(db, globalScope(db, admin), register("GL-0002", "MAX30100"))
    third = devices.registerDevice(db, globalScope(db, admin), register("GL-0003"))
    own = devices.registerDevice(db, instScope(db, team.owner, team.id), register("GL-INST-1"))
    return {"first": first, "second": second, "third": third, "own": own}


def test_todos_exporta_el_inventario_con_las_columnas_del_listado(db, mails, admin, inventory):
    content, filename = deviceExport.exportDevices(db, globalScope(db, admin), alcance="TODOS")
    rows = rowsOf(content)
    assert rows[0] == list(deviceExport.COLUMNS)
    assert len(rows) == 5  # encabezado + 4 dispositivos
    assert {row[0] for row in rows[1:]} == {"GL-0001", "GL-0002", "GL-0003", "GL-INST-1"}
    assert filename.startswith("dispositivos-") and filename.endswith(".csv")


def test_seleccion_exporta_solo_los_dispositivos_marcados(db, mails, admin, inventory):
    ids = [inventory["first"].idDispositivo, inventory["third"].idDispositivo]
    rows = rowsOf(deviceExport.exportDevices(db, globalScope(db, admin), alcance="SELECCION", ids=ids)[0])
    assert {row[0] for row in rows[1:]} == {"GL-0001", "GL-0003"}


def test_seleccion_vacia_no_exporta_filas(db, mails, admin, inventory):
    rows = rowsOf(deviceExport.exportDevices(db, globalScope(db, admin), alcance="SELECCION", ids=[])[0])
    assert rows == [list(deviceExport.COLUMNS)]


def test_todos_respeta_busqueda_y_estado_del_listado(db, mails, admin, inventory):
    devices.changeState(db, globalScope(db, admin), inventory["second"].idDispositivo, "EN_MANTENIMIENTO", None)
    by_code = rowsOf(deviceExport.exportDevices(db, globalScope(db, admin), alcance="TODOS", busqueda="GL-000")[0])
    assert {row[0] for row in by_code[1:]} == {"GL-0001", "GL-0002", "GL-0003"}
    by_state = rowsOf(deviceExport.exportDevices(db, globalScope(db, admin), alcance="TODOS", estado="EN_MANTENIMIENTO")[0])
    assert [row[0] for row in by_state[1:]] == ["GL-0002"]
    assert by_state[1][3] == "En mantenimiento"


def test_el_operador_exporta_solo_lo_que_ve_en_su_listado(db, mails, team, inventory):
    own = inventory["own"]
    devices.changeState(db, instScope(db, team.owner, team.id), own.idDispositivo, "EN_MANTENIMIENTO", None)
    owner_rows = rowsOf(deviceExport.exportDevices(db, instScope(db, team.owner, team.id), alcance="TODOS")[0])
    operator_rows = rowsOf(deviceExport.exportDevices(db, instScope(db, team.operator, team.id), alcance="TODOS")[0])
    assert [row[0] for row in owner_rows[1:]] == ["GL-INST-1"]
    assert operator_rows == [list(deviceExport.COLUMNS)]  # en mantenimiento: el operador no lo ve en el listado


def test_la_institucion_no_exporta_dispositivos_que_no_son_suyos(db, mails, team, inventory):
    rows = rowsOf(deviceExport.exportDevices(db, instScope(db, team.owner, team.id), alcance="SELECCION",
                                             ids=[inventory["first"].idDispositivo])[0])
    assert rows == [list(deviceExport.COLUMNS)]  # el de la plataforma no está asignado a la institución: no se filtra


def test_exportar_un_dispositivo_sale_con_sus_datos_y_nombre_del_codigo(db, mails, admin, inventory):
    content, filename = deviceExport.exportDevice(db, globalScope(db, admin), inventory["first"].idDispositivo, "csv")
    rows = rowsOf(content)
    assert len(rows) == 2 and rows[1][0] == "GL-0001" and rows[1][3] == "Operativo"
    assert filename.startswith("dispositivo-GL-0001-") and filename.endswith(".csv")


def test_el_dispositivo_de_otra_institucion_no_existe_para_la_propietaria(db, mails, admin, team, inventory):
    with pytest.raises(AuthError) as hidden:
        deviceExport.exportDevice(db, instScope(db, team.owner, team.id), inventory["first"].idDispositivo, "csv")
    assert hidden.value.code == "DISPOSITIVO_NO_ENCONTRADO"


def test_los_tres_formatos_salen_con_su_tipo_de_archivo(db, mails, admin, inventory):
    scope = globalScope(db, admin)
    csvContent, csvName = deviceExport.exportDevices(db, scope, alcance="TODOS", formato="csv")
    xlsxContent, xlsxName = deviceExport.exportDevices(db, scope, alcance="TODOS", formato="xlsx")
    pdfContent, pdfName = deviceExport.exportDevices(db, scope, alcance="TODOS", formato="pdf")
    assert csvName.endswith(".csv") and csvContent.startswith("﻿".encode("utf-8"))
    assert xlsxName.endswith(".xlsx") and xlsxContent.startswith(b"PK")
    assert pdfName.endswith(".pdf") and pdfContent.startswith(b"%PDF")


def test_cada_exportacion_queda_en_la_auditoria(db, mails, admin, inventory):
    before = auditCount(db)
    deviceExport.exportDevices(db, globalScope(db, admin), alcance="TODOS")
    assert auditCount(db) > before


def test_una_cuenta_sin_permiso_de_consulta_no_exporta(db, mails, team, inventory):
    stranger = makeUser(db, tipoCuenta="CONSUMIDOR_FINAL", email="paciente@example.com", usuario="paciente")
    with pytest.raises(AuthError):
        devices.platformScope(db, stranger)


def test_http_exporta_para_el_administrador_y_para_la_propietaria(db, mails, admin, team, inventory, api):
    ok = api(admin).post("/api/v1/devices/export?formato=xlsx", json={"alcance": "TODOS"})
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert ok.headers["content-disposition"].startswith("attachment; filename=")
    assert ok.headers["cache-control"] == "no-store"
    base = f"/api/v1/institutions/{team.id}/devices/export"
    assert api(team.owner).post(base, json={"alcance": "TODOS"}).headers["content-type"].startswith("text/csv")
    assert api(admin).post("/api/v1/devices/export", json={"alcance": "ROBOT"}).status_code == 422
    device = inventory["first"].idDispositivo
    single = api(admin).post(f"/api/v1/devices/{device}/export?formato=pdf")
    assert single.status_code == 200 and single.content.startswith(b"%PDF")
