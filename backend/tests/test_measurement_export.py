# Exportación del historial propio de mediciones (CSV, Excel o PDF): sale lo que filtra el historial, solo de la cuenta individual y
# cada intento queda auditado sin los valores exportados.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_measurement_export.py -v

import csv
import io
from datetime import date

import pytest
from sqlalchemy import select

from app.models.audit import Audit
from app.services import measurement as measurements
from app.services import measurementExport
from tests.test_account_deletion import db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_institutions import expectError, institutional, team  # noqa: F401 - fixtures
from tests.test_measurements import completeOximetry, consumer, device, noEstimator, oximetry  # noqa: F401 - fixtures


def rowsOf(content: bytes) -> list[dict[str, str]]:
    text = content.decode("utf-8")
    assert text.startswith("﻿")
    reader = csv.reader(io.StringIO(text[1:]), delimiter=";")
    header = next(reader)
    assert tuple(header) == measurementExport.EXPORT_COLUMNS
    return [dict(zip(header, row)) for row in reader]


def spo2Text(value) -> str:
    """Formato de la exportación: dos decimales con coma."""
    return f"{float(value):.2f}".replace(".", ",")


def auditOf(db, action: str) -> list[Audit]:
    db.expire_all()
    return list(db.scalars(select(Audit).where(Audit.accion == action)))


def test_exporta_todas_las_mediciones_con_los_filtros_del_historial(db, mails, consumer):
    user, profileId = consumer
    dev = device(db)
    completeOximetry(db, user, profileId, dev, spo2="95", hr=60)
    completeOximetry(db, user, profileId, dev, spo2="99", hr=80)
    cancelled = oximetry(db, user, profileId, dev)
    measurements.cancelMeasurement(db, user, cancelled.idMedicion)
    content, filename = measurementExport.exportOwnMeasurements(db, user, alcance="TODOS", formato="csv")
    assert filename.startswith("mis-mediciones-") and filename.endswith(".csv")
    rows = rowsOf(content)
    assert len(rows) == 3
    assert {row["Estado"] for row in rows} == {"Completada", "Cancelada"}
    history = measurements.listOwnHistory(db, user).items
    assert {row["SpO2 (%)"] for row in rows if row["Estado"] == "Completada"} == {spo2Text(m.spo2) for m in history if m.spo2 is not None}
    assert all(row["Origen de los datos"] == "Real" and row["Dispositivo"] == dev.codigoDispositivo for row in rows)
    completed = measurementExport.exportOwnMeasurements(db, user, alcance="TODOS", estado="COMPLETADA", formato="csv")[0]
    assert len(rowsOf(completed)) == 2
    assert len(rowsOf(measurementExport.exportOwnMeasurements(db, user, alcance="TODOS", desde=date.today(),
                                                             hasta=date.today(), orden="asc")[0])) == 3
    assert rowsOf(measurementExport.exportOwnMeasurements(db, user, alcance="TODOS", hasta=date(2000, 1, 1))[0]) == []


def test_selecciona_solo_las_mediciones_elegidas(db, mails, consumer):
    user, profileId = consumer
    dev = device(db)
    chosen = completeOximetry(db, user, profileId, dev, spo2="96", hr=70)
    completeOximetry(db, user, profileId, dev, spo2="98", hr=75)
    content, _ = measurementExport.exportOwnMeasurements(db, user, alcance="SELECCION", ids=[chosen.idMedicion], formato="csv")
    rows = rowsOf(content)
    assert len(rows) == 1 and rows[0]["SpO2 (%)"] == spo2Text(chosen.spo2)
    expectError("DATOS_INVALIDOS", measurementExport.exportOwnMeasurements, db, user, alcance="SELECCION", ids=[], formato="csv")


def test_una_seleccion_con_medicion_ajena_se_rechaza(db, mails, consumer):
    user, profileId = consumer
    dev = device(db)
    completeOximetry(db, user, profileId, dev)
    other_user = makeUser(db, email="otra@example.com", usuario="otra")
    foreign = completeOximetry(db, other_user, measurements.getOwnProfile(db, other_user).idPerfilMedicion, dev)
    expectError("DATOS_INVALIDOS", measurementExport.exportOwnMeasurements, db, user, alcance="SELECCION",
                ids=[foreign.idMedicion], formato="csv")
    assert auditOf(db, "EXPORTACION_FALLIDA")[-1].observacion == "Motivo: DATOS_INVALIDOS"


@pytest.mark.parametrize("formato, signature", [("xlsx", b"PK"), ("pdf", b"%PDF")])
def test_excel_y_pdf_son_archivos_validos(db, mails, consumer, formato, signature):
    user, profileId = consumer
    completeOximetry(db, user, profileId, device(db))
    content, filename = measurementExport.exportOwnMeasurements(db, user, alcance="TODOS", formato=formato)
    assert content.startswith(signature) and filename.endswith(f".{formato}")


def test_una_cuenta_institucional_no_exporta_mediciones_propias(db, mails, team):
    expectError("PERFIL_NO_DISPONIBLE", measurementExport.exportOwnMeasurements, db, team.owner, alcance="TODOS", formato="csv")
    assert auditOf(db, "EXPORTACION_FALLIDA")[-1].observacion == "Motivo: PERFIL_NO_DISPONIBLE"


def test_cada_exportacion_queda_auditada_con_la_cantidad_y_sin_valores(db, mails, consumer):
    user, profileId = consumer
    completeOximetry(db, user, profileId, device(db), spo2="93")
    measurementExport.exportOwnMeasurements(db, user, alcance="TODOS", formato="csv")
    done = auditOf(db, "EXPORTACION_COMPLETADA")
    assert len(done) == 1 and "cantidadRegistros" in (done[0].datosNuevos or "") and "93" not in (done[0].datosNuevos or "")
    assert done[0].accion == "EXPORTACION_COMPLETADA" and done[0].idUsuario == user.idUsuario
