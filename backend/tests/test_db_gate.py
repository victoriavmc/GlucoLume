# Tope de llamadas simultáneas al driver ODBC (app/db/gate.py): limita cuántos hilos están dentro de pyodbc a la vez y delega todo lo demás.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_db_gate.py -v

import threading
import time

import pytest

from app.db.gate import GatedConnection, GatedCursor, gateFor


class FakeCursor:
    """Cursor de pyodbc de mentira: cuenta cuántos hilos están dentro de una llamada al mismo tiempo."""

    description = [("id",)]
    rowcount = 1
    fast_executemany = False

    def __init__(self, tracker, fail=False):
        self.tracker, self.fail = tracker, fail

    def _enter(self):
        with self.tracker["lock"]:
            self.tracker["now"] += 1
            self.tracker["max"] = max(self.tracker["max"], self.tracker["now"])
        time.sleep(0.01)
        with self.tracker["lock"]:
            self.tracker["now"] -= 1

    def execute(self, *args):
        self._enter()
        if self.fail:
            raise RuntimeError("falla del driver")
        return self

    def executemany(self, *args):
        self._enter()

    def fetchall(self):
        self._enter()
        return [(1,)]

    def fetchone(self):
        self._enter()
        return None

    def close(self):
        pass


class FakeConnection:
    autocommit = False

    def __init__(self, tracker, fail=False):
        self.tracker, self.fail = tracker, fail

    def cursor(self):
        return FakeCursor(self.tracker, self.fail)

    def commit(self):
        FakeCursor(self.tracker)._enter()

    def rollback(self):
        FakeCursor(self.tracker)._enter()

    def add_output_converter(self, *args):
        return "converter"


def newTracker():
    return {"lock": threading.Lock(), "now": 0, "max": 0}


def hammer(connection, threads=12, rounds=5):
    def work():
        for _ in range(rounds):
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchall()
            connection.commit()

    workers = [threading.Thread(target=work) for _ in range(threads)]
    [worker.start() for worker in workers]
    [worker.join() for worker in workers]


def test_nunca_hay_mas_de_n_hilos_dentro_del_driver():
    tracker = newTracker()
    hammer(GatedConnection(FakeConnection(tracker), threading.BoundedSemaphore(3)))
    assert 1 <= tracker["max"] <= 3


def test_sin_tope_se_ve_la_concurrencia_que_el_tope_evita():
    tracker = newTracker()
    hammer(FakeConnection(tracker))
    assert tracker["max"] > 3


def test_delega_atributos_y_asignaciones_al_cursor_y_a_la_conexion_reales():
    gate = threading.BoundedSemaphore(2)
    tracker = newTracker()
    connection = GatedConnection(FakeConnection(tracker), gate)
    cursor = connection.cursor()
    assert isinstance(cursor, GatedCursor)
    assert cursor.description == [("id",)] and cursor.rowcount == 1
    cursor.fast_executemany = True  # SQLAlchemy lo asigna sobre el cursor del driver
    assert cursor._cursor.fast_executemany is True
    connection.autocommit = True
    assert connection._connection.autocommit is True
    assert connection.add_output_converter(1, None) == "converter"  # lo llama el dialecto al conectar
    assert cursor.execute("SELECT 1") is cursor  # pyodbc devuelve el propio cursor


def test_una_falla_del_driver_libera_el_semaforo():
    gate = threading.BoundedSemaphore(1)
    connection = GatedConnection(FakeConnection(newTracker(), fail=True), gate)
    for _ in range(3):  # con 1 sola plaza, una plaza perdida colgaría la segunda vuelta
        with pytest.raises(RuntimeError):
            connection.cursor().execute("SELECT 1")
    assert gate.acquire(timeout=0.5)
    gate.release()


def test_iterar_el_cursor_trae_filas_pasando_por_el_tope():
    tracker = newTracker()
    cursor = GatedConnection(FakeConnection(tracker), threading.BoundedSemaphore(1)).cursor()
    assert list(cursor) == []  # el falso fetchone() devuelve None: fin de las filas


def test_un_semaforo_por_tamano_y_por_proceso():
    assert gateFor(4) is gateFor(4) and gateFor(4) is not gateFor(5)
