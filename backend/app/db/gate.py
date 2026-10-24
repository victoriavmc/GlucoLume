# Gate - Tope de llamadas simultáneas al driver ODBC (pyodbc) dentro de un proceso.
#
# Medido el 23/10/2026 (docs/RENDIMIENTO.md §3.1, docs/evidencias/rendimiento/hilos_micro*.py): con 6 u 8 hilos usando pyodbc a la vez, el mismo
# trabajo que con 1 a 4 hilos pasa de ~1700 a ~190 consultas/s y la CPU por consulta se multiplica por ~40, aunque cada hilo tenga su propia
# conexión y la CPU del contenedor no sea el límite. No es SQLAlchemy (ocurre con pyodbc puro), ni el cifrado, ni el pool, ni el intervalo de
# conmutación de la GIL: solo desaparece si se limita cuántos hilos están DENTRO del driver al mismo tiempo (con 2 es el máximo medido; con 3 se recupera ~5x y con 4 casi nada).
# Los demás hilos esperan en un semáforo (sin gastar CPU) y la aplicación sigue atendiendo pedidos que no usan la base.
#
# El semáforo se toma solo durante UNA llamada al driver (ejecutar, traer filas, confirmar, revertir), nunca entre llamadas: no se retiene
# mientras el código de la aplicación hace otra cosa, no se anida (el driver no llama a la aplicación) y, por eso, no puede producir un
# interbloqueo aunque una petición abra una segunda sesión. DB_MAX_CONCURRENT_CALLS = 0 lo desactiva.

import threading

from sqlalchemy import event
from sqlalchemy.engine import Engine

_gates: dict[int, threading.BoundedSemaphore] = {}
_gatesLock = threading.Lock()


def gateFor(limit: int) -> threading.BoundedSemaphore:
    """Un único semáforo por tamaño y por proceso: la API y los jobs de un mismo proceso comparten el tope."""
    with _gatesLock:
        return _gates.setdefault(limit, threading.BoundedSemaphore(limit))


class GatedCursor:
    """Cursor de pyodbc que toma el semáforo en cada llamada que habla con el driver. Todo lo demás (description, rowcount, setinputsizes,
    fast_executemany, arraysize...) se delega tal cual."""

    __slots__ = ("_cursor", "_gate")

    def __init__(self, cursor, gate: threading.BoundedSemaphore) -> None:
        object.__setattr__(self, "_cursor", cursor)
        object.__setattr__(self, "_gate", gate)

    def execute(self, *args, **kwargs):
        with self._gate:
            result = self._cursor.execute(*args, **kwargs)
        return self if result is self._cursor else result

    def executemany(self, *args, **kwargs):
        with self._gate:
            return self._cursor.executemany(*args, **kwargs)

    def fetchone(self):
        with self._gate:
            return self._cursor.fetchone()

    def fetchmany(self, *args):
        with self._gate:
            return self._cursor.fetchmany(*args)

    def fetchall(self):
        with self._gate:
            return self._cursor.fetchall()

    def fetchval(self, *args):
        with self._gate:
            return self._cursor.fetchval(*args)

    def nextset(self):
        with self._gate:
            return self._cursor.nextset()

    def skip(self, count):
        with self._gate:
            return self._cursor.skip(count)

    def commit(self):
        with self._gate:
            return self._cursor.commit()

    def rollback(self):
        with self._gate:
            return self._cursor.rollback()

    def __iter__(self):
        return iter(self.fetchone, None)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        with self._gate:
            return self._cursor.__exit__(*exc)

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def __setattr__(self, name, value):
        setattr(self._cursor, name, value)


class GatedConnection:
    """Conexión de pyodbc cuyos cursores y cuyas confirmaciones pasan por el semáforo."""

    __slots__ = ("_connection", "_gate")

    def __init__(self, connection, gate: threading.BoundedSemaphore) -> None:
        object.__setattr__(self, "_connection", connection)
        object.__setattr__(self, "_gate", gate)

    def cursor(self, *args, **kwargs):
        return GatedCursor(self._connection.cursor(*args, **kwargs), self._gate)

    def execute(self, *args, **kwargs):
        with self._gate:
            return GatedCursor(self._connection.execute(*args, **kwargs), self._gate)

    def commit(self):
        with self._gate:
            return self._connection.commit()

    def rollback(self):
        with self._gate:
            return self._connection.rollback()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        with self._gate:
            return self._connection.__exit__(*exc)

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def __setattr__(self, name, value):
        setattr(self._connection, name, value)


def limitDriverCalls(engine: Engine, limit: int) -> Engine:
    """Hace que las conexiones nuevas de `engine` pasen por el tope. Con limit <= 0 no hace nada (tampoco con un reemplazo de prueba que no sea un Engine)."""
    if limit <= 0 or not isinstance(engine, Engine):
        return engine
    gate = gateFor(limit)

    @event.listens_for(engine, "do_connect")
    def connectGated(dialect, connectionRecord, cargs, cparams):
        return GatedConnection(dialect.loaded_dbapi.connect(*cargs, **cparams), gate)

    return engine
