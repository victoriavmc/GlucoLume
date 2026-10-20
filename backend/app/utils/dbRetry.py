# DbRetry - Reintento ante un deadlock de SQL Server (error 1205, SQLSTATE 40001)
#
# Una consulta por índice (p. ej. buscar una cuenta por correo: bloquea la clave del índice y luego la fila) y una actualización de esa misma
# fila (bloquea la fila y luego el índice) pueden bloquearse entre sí en SQL Server; el motor elige una víctima y le pide «volver a ejecutar la
# transacción». Es la respuesta estándar de SQL Server a ese caso: se deshace la transacción de la víctima y se repite desde el principio. Solo
# se aplica a operaciones que no tienen efectos externos antes del commit (los correos se envían después). Cualquier otro error se propaga.

import functools
import random
import time

from sqlalchemy.exc import DBAPIError

MAX_ATTEMPTS = 4


def isDeadlock(error: BaseException) -> bool:
    text = str(getattr(error, "orig", error))
    return "40001" in text or "(1205)" in text


def retryOnDeadlock(function):
    """Decora una función cuyo primer argumento es la Session. Reintenta (hasta MAX_ATTEMPTS) si la transacción fue elegida víctima de un deadlock."""
    @functools.wraps(function)
    def wrapper(db, *args, **kwargs):
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return function(db, *args, **kwargs)
            except DBAPIError as error:
                db.rollback()
                if not isDeadlock(error) or attempt == MAX_ATTEMPTS:
                    raise
                time.sleep(random.uniform(0.02, 0.08) * attempt)
    return wrapper
