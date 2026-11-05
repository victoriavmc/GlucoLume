# Medición temporal (no versionada): consultas SQL del historial de glucosa con 3 y con 15 mediciones completadas.
import json, os
from datetime import timedelta
from sqlalchemy import event
from app.services import measurement as measurements
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import db, engine, mails, makeUser  # noqa: F401
from tests.test_measurements import addMatrix, consumer, device  # noqa: F401
from tests.test_historial_glucosa_consultas import _addRules, _insertGlucose  # noqa: F401

def _count(engine, action):
    statements = []
    def counter(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(engine, "before_cursor_execute", counter)
    try:
        result = action()
    finally:
        event.remove(engine, "before_cursor_execute", counter)
    return result, len(statements)

def test_medir_historial(db, mails, consumer, engine):
    user, profileId = consumer
    dev = device(db)
    matrix = addMatrix(db, condicion="AYUNO", sexo="FEMENINO", edad=(18, 80), rule=True)
    _addRules(db, matrix)
    start = nowForDb()
    _insertGlucose(db, profileId, dev.idDispositivo, matrix.idMatriz, 3, start)
    measurements.listOwnHistory(db, user, tamanioPagina=20)
    page3, c3 = _count(engine, lambda: measurements.listOwnHistory(db, user, tamanioPagina=20))
    _insertGlucose(db, profileId, dev.idDispositivo, matrix.idMatriz, 12, start - timedelta(hours=1))
    page15, c15 = _count(engine, lambda: measurements.listOwnHistory(db, user, tamanioPagina=20))
    out = {"consultasCon3Glucosa": c3, "consultasCon15Glucosa": c15, "filasPagina15": len(page15.items),
           "semaforos": [i.semaforo for i in page15.items]}
    with open(os.environ["METRICS_OUT"], "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
