# H-19 (N+1 del historial): el semáforo de cada medición de glucosa de una página se calcula con las reglas precargadas en lote.
#
# Garantías que cubre esta prueba:
#   1. El semáforo y la referencia de cada fila son IGUALES a los que produce glucoseReference.build sin precarga (camino original).
#   2. El número de consultas del listado NO crece con la cantidad de mediciones de glucosa de la página (antes crecía en 2 por medición).

import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import event, select

from app.models.matrixRule import MatrixRule
from app.models.measurement import Measurement
from app.services import glucoseReference, schemaCompat
from app.services import measurement as measurements
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import db, engine, mails  # noqa: F401 - fixtures
from tests.test_measurements import (  # noqa: F401 - fixtures y helpers
    addMatrix,
    consumer,
    device,
)

VALORES = (60, 72, 90, 108, 130, 85)  # rango de la regla de prueba: 70–110 mg/dL


def _addRules(db, matrix):  # noqa: F811 - el parámetro db es el fixture
    """Dos reglas para la misma matriz y sexo: una con rango de edad y otra sin rango, para ejercitar el orden y la selección."""
    db.add(MatrixRule(idReglaMatriz=uuid.uuid4(), idMatriz=matrix.idMatriz, codigoRegla="R2", sexoModelo="FEMENINO",
                      edadDesde=None, edadHasta=None, condicionComida="AYUNO", glucosaMinReferencia=Decimal(60),
                      glucosaMaxReferencia=Decimal(140)))
    db.commit()


def _insertGlucose(db, profileId, deviceId, matrixId, count, start, applied=None):  # noqa: F811
    ids = []
    for index in range(count):
        estimated = index % 2 == 0  # alterna valores estimados (con regla aplicada) y valores del dispositivo
        value = Decimal(VALORES[index % len(VALORES)])  # cubre VERDE, AMARILLO (bordes y debajo) y ROJO (encima)
        row = Measurement(
            idMedicion=uuid.uuid4(), idPerfilMedicion=profileId, idDispositivo=deviceId, modoMedicion="GLUCOSA_EXPERIMENTAL",
            estadoMedicion="COMPLETADA", fechaHoraInicio=start - timedelta(minutes=index), condicionComida="AYUNO",
            sexoModelo="FEMENINO", edadAlMomento=30, idMatriz=matrixId, origenGlucosa="EXPERIMENTAL",
            glucosaDispositivo=value, glucosaEstimada=value if estimated else None, unidadGlucosa="mg/dL",
            versionAlgoritmo="1.0" if estimated else None,
        )
        db.add(row)
        db.flush()
        if estimated and applied is not None:
            schemaCompat.setRuleId(db, row.idMedicion, applied)
        ids.append(row.idMedicion)
    db.commit()
    return ids


def _countStatements(engine, action):  # noqa: F811
    statements = []

    def counter(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", counter)
    try:
        result = action()
    finally:
        event.remove(engine, "before_cursor_execute", counter)
    return result, len(statements)


def test_semaforo_de_cada_fila_igual_al_calculo_individual(db, mails, consumer, engine):  # noqa: F811
    user, profileId = consumer
    dev = device(db)
    matrix = addMatrix(db, condicion="AYUNO", sexo="FEMENINO", edad=(18, 80), rule=True)
    _addRules(db, matrix)
    appliedRule = db.scalars(select(MatrixRule.idReglaMatriz).where(MatrixRule.idMatriz == matrix.idMatriz)
                             .order_by(MatrixRule.codigoRegla)).first()
    _insertGlucose(db, profileId, dev.idDispositivo, matrix.idMatriz, 6, nowForDb(), applied=appliedRule)

    page = measurements.listOwnHistory(db, user, tamanioPagina=20)
    glucoseRows = [m for m in page.items if m.modoMedicion == "GLUCOSA_EXPERIMENTAL" and m.estadoMedicion == "COMPLETADA"]
    assert len(glucoseRows) == 6

    for item in glucoseRows:
        row = db.get(Measurement, item.idMedicion)
        expected = glucoseReference.build(db, row).semaforo  # camino original, sin precarga
        assert item.semaforo == expected
        assert expected is not None
    assert {item.semaforo for item in glucoseRows} == {"VERDE", "AMARILLO", "ROJO"}  # la comparación cubre todos los colores


def test_el_numero_de_consultas_no_crece_con_las_mediciones_de_glucosa(db, mails, consumer, engine):  # noqa: F811
    user, profileId = consumer
    dev = device(db)
    matrix = addMatrix(db, condicion="AYUNO", sexo="FEMENINO", edad=(18, 80), rule=True)
    _addRules(db, matrix)
    start = nowForDb()
    _insertGlucose(db, profileId, dev.idDispositivo, matrix.idMatriz, 3, start)
    measurements.listOwnHistory(db, user, tamanioPagina=20)  # calentamiento: columnas y cachés de esquema

    _, pocas = _countStatements(engine, lambda: measurements.listOwnHistory(db, user, tamanioPagina=20))
    _insertGlucose(db, profileId, dev.idDispositivo, matrix.idMatriz, 12, start - timedelta(hours=1))
    _, muchas = _countStatements(engine, lambda: measurements.listOwnHistory(db, user, tamanioPagina=20))

    assert muchas == pocas, f"el listado hace {muchas} consultas con 15 mediciones y {pocas} con 3: crece con la página (N+1)"
