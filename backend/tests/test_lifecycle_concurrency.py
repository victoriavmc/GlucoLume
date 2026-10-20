# Carreras del ciclo de vida de cuentas con conexiones independientes. En la suite corre sobre SQLite (que serializa las escrituras con un
# bloqueo de base): comprueba la lógica de revalidación y el reclamo condicional. Las carreras con bloqueos de fila reales (UPDLOCK) se prueban
# contra SQL Server con `python -m tests.lifecycle_concurrency` (ver ese módulo; escribe datos sintéticos y exige confirmar la base).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_lifecycle_concurrency.py -v

from sqlalchemy.orm import sessionmaker

from tests import lifecycle_concurrency
from tests.test_account_deletion import db, engine, mails  # noqa: F401 - fixtures


def test_las_carreras_no_dejan_estados_inconsistentes(engine, mails):
    makeSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    harness = lifecycle_concurrency.run(makeSession, rounds=5, tolerateLocks=True)
    assert harness.failures == [] and harness.checks > 0


def test_el_comando_exige_confirmar_la_base(engine, monkeypatch):
    monkeypatch.delenv("LIFECYCLE_CONCURRENCY_CONFIRM", raising=False)
    assert lifecycle_concurrency.main([]) == 2  # no escribe nada sin la confirmación explícita


def test_un_deadlock_de_sql_server_se_reintenta_y_otros_errores_no():
    import pytest
    from sqlalchemy.exc import DBAPIError, IntegrityError

    from app.utils.dbRetry import MAX_ATTEMPTS, retryOnDeadlock

    class FakeDb:
        rollbacks = 0

        def rollback(self):
            self.rollbacks += 1

    deadlock = DBAPIError("stmt", {}, Exception("('40001', 'Transaction was deadlocked ... (1205)')"))
    calls = []

    @retryOnDeadlock
    def flaky(db):
        calls.append(1)
        if len(calls) < 3:
            raise deadlock
        return "ok"

    db = FakeDb()
    assert flaky(db) == "ok" and len(calls) == 3 and db.rollbacks == 2  # dos víctimas, tercer intento correcto

    @retryOnDeadlock
    def always(db):
        raise deadlock

    with pytest.raises(DBAPIError):
        always(FakeDb())  # tras MAX_ATTEMPTS se propaga

    seen = []

    @retryOnDeadlock
    def other(db):
        seen.append(1)
        raise IntegrityError("stmt", {}, Exception("duplicate key"))

    with pytest.raises(IntegrityError):
        other(FakeDb())
    assert len(seen) == 1 and MAX_ATTEMPTS >= 3  # un error que no es deadlock no se reintenta
