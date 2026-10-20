# Pruebas del bloqueo temporal por intentos fallidos de contraseña (CredencialLocal).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_login_lockout.py -v
#
# Usan el esquema SQLite temporal de test_account_deletion.py. El reloj del servicio se controla
# reemplazando app.services.auth.nowForDb, sin modificar la duración configurada del bloqueo.

import asyncio
import threading
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.api.errors import authErrorHandler
from app.core.config import getSettings
from app.core.exceptions import AuthError
from app.models.localCredential import LocalCredential
from app.services import auth as authService
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import (  # noqa: F401 - fixtures
    EMAIL,
    PASSWORD,
    db,
    engine,
    mails,
    makeUser,
)

WRONG = "OtraClave#2026"


@pytest.fixture
def clock(monkeypatch):
    """Reloj controlable del servicio de autenticación."""

    class Clock:
        now = nowForDb()

        def advance(self, **delta):
            self.now += timedelta(**delta)

    current = Clock()
    monkeypatch.setattr(authService, "nowForDb", lambda: current.now)
    return current


def credential(db) -> LocalCredential:
    db.expire_all()
    return db.scalar(select(LocalCredential))


def fail(db, password=WRONG) -> str:
    with pytest.raises(AuthError) as error:
        authService.loginLocal(db, EMAIL, password)
    return error.value.code


def lockMinutes() -> int:
    return getSettings().AUTH_LOCKOUT_MINUTES


def test_tres_errores_consecutivos_bloquean(db, mails, clock):
    makeUser(db)
    assert fail(db) == "CREDENCIALES_INVALIDAS"
    assert credential(db).intentosFallidosConsecutivos == 1
    assert fail(db) == "CREDENCIALES_INVALIDAS"
    assert credential(db).intentosFallidosConsecutivos == 2
    assert fail(db) == "CUENTA_BLOQUEADA"

    row = credential(db)
    assert row.intentosFallidosConsecutivos == 3
    assert row.bloqueadoHasta == clock.now + timedelta(minutes=lockMinutes())


def test_durante_el_bloqueo_no_se_procesan_intentos_ni_suman(db, mails, clock):
    makeUser(db)
    for _ in range(3):
        fail(db)
    lockedUntil = credential(db).bloqueadoHasta

    clock.advance(minutes=lockMinutes() - 1)
    # Ni una contraseña incorrecta ni la correcta se procesan mientras dura el bloqueo.
    assert fail(db) == "CUENTA_BLOQUEADA"
    assert fail(db, PASSWORD) == "CUENTA_BLOQUEADA"
    row = credential(db)
    assert row.intentosFallidosConsecutivos == 3
    assert row.bloqueadoHasta == lockedUntil


def test_al_vencer_el_bloqueo_el_contador_vuelve_a_cero(db, mails, clock):
    makeUser(db)
    for _ in range(3):
        fail(db)
    clock.advance(minutes=lockMinutes(), seconds=1)

    # Sin proceso programado: el desbloqueo lógico ocurre al evaluar el próximo intento, y se persiste.
    assert authService.loginLocal(db, EMAIL, PASSWORD).estado == "AUTENTICADO"
    row = credential(db)
    assert row.intentosFallidosConsecutivos == 0 and row.bloqueadoHasta is None


def test_un_error_despues_del_desbloqueo_deja_el_contador_en_uno(db, mails, clock):
    makeUser(db)
    for _ in range(3):
        fail(db)
    clock.advance(minutes=lockMinutes(), seconds=1)

    assert fail(db) == "CREDENCIALES_INVALIDAS"
    row = credential(db)
    assert row.intentosFallidosConsecutivos == 1 and row.bloqueadoHasta is None


def test_tres_nuevos_errores_despues_del_desbloqueo_vuelven_a_bloquear(db, mails, clock):
    makeUser(db)
    for _ in range(3):
        fail(db)
    clock.advance(minutes=lockMinutes(), seconds=1)

    # Cada bloqueo vencido devuelve los 3 intentos completos.
    assert [fail(db) for _ in range(3)] == ["CREDENCIALES_INVALIDAS", "CREDENCIALES_INVALIDAS", "CUENTA_BLOQUEADA"]
    row = credential(db)
    assert row.intentosFallidosConsecutivos == 3
    assert row.bloqueadoHasta == clock.now + timedelta(minutes=lockMinutes())


def test_inicio_de_sesion_exitoso_reinicia_el_contador(db, mails, clock):
    makeUser(db)
    fail(db)
    fail(db)
    assert authService.loginLocal(db, EMAIL, PASSWORD).estado == "AUTENTICADO"
    assert credential(db).intentosFallidosConsecutivos == 0
    # Vuelve a tener 3 intentos completos.
    assert [fail(db) for _ in range(2)] == ["CREDENCIALES_INVALIDAS", "CREDENCIALES_INVALIDAS"]


def test_contador_residual_sin_bloqueo_vigente_no_bloquea_anticipadamente(db, mails, clock):
    makeUser(db)
    row = credential(db)
    row.intentosFallidosConsecutivos = 3
    row.bloqueadoHasta = None
    db.commit()

    assert fail(db) == "CREDENCIALES_INVALIDAS"
    assert credential(db).intentosFallidosConsecutivos == 1


def test_cuenta_inexistente_responde_igual_que_contraseña_incorrecta(db, mails, clock):
    makeUser(db)
    with pytest.raises(AuthError) as missing:
        authService.loginLocal(db, "nadie@example.com", WRONG)
    with pytest.raises(AuthError) as wrong:
        authService.loginLocal(db, EMAIL, WRONG)
    assert (missing.value.code, missing.value.message) == (wrong.value.code, wrong.value.message)
    assert wrong.value.retryAfterSeconds is None


def test_bloqueo_informa_retry_after(db, mails, clock):
    makeUser(db)
    for _ in range(2):
        fail(db)
    with pytest.raises(AuthError) as locked:
        authService.loginLocal(db, EMAIL, WRONG)
    assert locked.value.retryAfterSeconds == lockMinutes() * 60

    clock.advance(minutes=5)
    with pytest.raises(AuthError) as stillLocked:
        authService.loginLocal(db, EMAIL, WRONG)
    assert stillLocked.value.retryAfterSeconds == (lockMinutes() - 5) * 60

    response = asyncio.run(authErrorHandler(None, stillLocked.value))
    assert response.status_code == 429
    assert response.headers["Retry-After"] == str((lockMinutes() - 5) * 60)


def test_reautenticacion_comparte_el_mismo_contador(db, mails, clock):
    user = makeUser(db)
    row = credential(db)
    for _ in range(3):
        assert authService.verifyCurrentPassword(db, row, WRONG) is False
        db.commit()
    with pytest.raises(AuthError) as locked:
        authService.verifyCurrentPassword(db, row, PASSWORD)
    assert locked.value.code == "CUENTA_BLOQUEADA"

    clock.advance(minutes=lockMinutes(), seconds=1)
    assert authService.verifyCurrentPassword(db, row, WRONG) is False
    db.commit()
    assert credential(db).intentosFallidosConsecutivos == 1
    assert user.idUsuario == credential(db).idUsuario


def test_solicitudes_simultaneas_no_superan_el_limite(engine, db, mails, clock):
    makeUser(db)
    workers = 8
    barrier = threading.Barrier(workers)
    makeSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    results, errors = [], []

    def attempt():
        session = makeSession()
        try:
            barrier.wait()
            authService.loginLocal(session, EMAIL, WRONG)
        except AuthError as error:
            results.append(error.code)
        except Exception as error:  # pragma: no cover - diagnóstico
            errors.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=attempt) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    # Solo se procesan los 3 intentos permitidos; el resto se rechaza por bloqueo sin sumar al contador.
    assert results.count("CREDENCIALES_INVALIDAS") == 2
    assert results.count("CUENTA_BLOQUEADA") == workers - 2
    row = credential(db)
    assert row.intentosFallidosConsecutivos == 3
    assert row.bloqueadoHasta == clock.now + timedelta(minutes=lockMinutes())
