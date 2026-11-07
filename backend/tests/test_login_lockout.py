# Límite de intentos fallidos del inicio de sesión (M-2, auditoría 07/11/2026) y bloqueo de la reautenticación con sesión.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_login_lockout.py -v
#
# El login se limita por (identificador, origen) en app/services/loginThrottle.py: 5 fallos en 15 min y 15 en 1 h. Esas ventanas usan el
# reloj monotónico de RateLimiter, que estas pruebas reemplazan por uno controlable (`steps`). La reautenticación con sesión conserva el
# contador de CredencialLocal, controlado con el reloj del servicio (`clock`).

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
from app.services import rateLimiter
from app.utils.timeZone import nowForDb
from app.utils.userAgent import ClientInfo
from tests.test_account_deletion import (  # noqa: F401 - fixtures
    EMAIL,
    PASSWORD,
    db,
    engine,
    mails,
    makeUser,
)

WRONG = "OtraClave#2026"
ORIGEN_A = "198.51.100.10"
ORIGEN_B = "198.51.100.20"
LIMITE_CORTO_SEGUNDOS = 15 * 60
ALERTA_ASUNTO = "actividad de seguridad"  # asunto del correo INTENTO_ACCESO_INUSUAL ("Revisá una actividad de seguridad")


class FakeMonotonic:
    """Reloj monotónico controlable para las ventanas de RateLimiter."""

    now = 10_000.0

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def steps(monkeypatch):
    fake = FakeMonotonic()
    monkeypatch.setattr(rateLimiter, "time", fake)
    return fake


@pytest.fixture
def clock(monkeypatch):
    """Reloj controlable del servicio de autenticación (bloqueo de la reautenticación)."""

    class Clock:
        now = nowForDb()

        def advance(self, **delta):
            self.now += timedelta(**delta)

    current = Clock()
    monkeypatch.setattr(authService, "nowForDb", lambda: current.now)
    return current


def attempt(db, password=WRONG, ip=ORIGEN_A, identificador=EMAIL, acceso="GENERAL"):
    """Un intento de login. Devuelve el AuthError rechazado o la respuesta de éxito."""
    try:
        return authService.loginLocal(db, identificador, password, ClientInfo(ip=ip), acceso)
    except AuthError as error:
        return error


def codes(results):
    return [r.code if isinstance(r, AuthError) else r.estado for r in results]


def credential(db) -> LocalCredential:
    db.expire_all()
    return db.scalar(select(LocalCredential))


def lockMinutes() -> int:
    return getSettings().AUTH_LOCKOUT_MINUTES


# --- Límite por (identificador, origen) -----------------------------------------------------------------------------------------------


def test_cinco_fallos_limitan_ese_origen_y_el_sexto_recibe_retry_after(db, mails, steps):
    makeUser(db)
    # Los cinco primeros fallos se procesan como contraseña incorrecta (el quinto incluido).
    assert codes([attempt(db) for _ in range(5)]) == ["CREDENCIALES_INVALIDAS"] * 5
    sixth = attempt(db)
    assert sixth.code == "CUENTA_BLOQUEADA"
    assert sixth.retryAfterSeconds == LIMITE_CORTO_SEGUNDOS


def test_mientras_dura_el_limite_ni_la_contrasena_correcta_se_procesa_ni_los_fallos_suman(db, mails, steps):
    makeUser(db)
    for _ in range(5):
        attempt(db)
    for _ in range(20):
        assert attempt(db).code == "CUENTA_BLOQUEADA"
    assert attempt(db, PASSWORD).code == "CUENTA_BLOQUEADA"
    # El límite vive en loginThrottle: el login no toca el contador de la base (eso queda para la reautenticación).
    assert credential(db).intentosFallidosConsecutivos == 0


def test_el_tiempo_restante_disminuye_y_el_acceso_vuelve_solo(db, mails, steps):
    makeUser(db)
    for _ in range(5):
        attempt(db)
    steps.advance(300)
    blocked = attempt(db, PASSWORD)
    assert blocked.code == "CUENTA_BLOQUEADA" and blocked.retryAfterSeconds == LIMITE_CORTO_SEGUNDOS - 300

    steps.advance(LIMITE_CORTO_SEGUNDOS - 300 + 1)
    assert attempt(db, PASSWORD).estado == "AUTENTICADO"


def test_no_se_puede_renovar_el_limite_insistiendo_desde_el_mismo_origen(db, mails, steps):
    makeUser(db)
    for _ in range(5):
        attempt(db)
    for _ in range(50):  # insistir mientras dura el límite no lo extiende: los rechazos no se registran
        assert attempt(db).code == "CUENTA_BLOQUEADA"

    steps.advance(LIMITE_CORTO_SEGUNDOS + 1)
    # Vencido el límite, vuelven a caber exactamente cinco intentos (el sexto ya queda bloqueado), como al principio.
    assert codes([attempt(db) for _ in range(5)]) == ["CREDENCIALES_INVALIDAS"] * 5
    assert attempt(db).code == "CUENTA_BLOQUEADA"


def test_un_tercero_desde_otro_origen_no_deja_fuera_a_la_victima(db, mails, steps):
    makeUser(db)
    for _ in range(5):
        attempt(db, ip=ORIGEN_A)  # el atacante agota su límite
    assert attempt(db, ip=ORIGEN_A).code == "CUENTA_BLOQUEADA"
    # La víctima entra con la contraseña correcta desde otro origen, sin esperar.
    assert attempt(db, PASSWORD, ip=ORIGEN_B).estado == "AUTENTICADO"


def test_el_limite_es_por_identificador_no_por_origen_entero(db, mails, steps):
    makeUser(db)
    for _ in range(5):
        attempt(db, identificador="otra@example.com", ip=ORIGEN_A)
    assert attempt(db, PASSWORD, identificador=EMAIL, ip=ORIGEN_A).estado == "AUTENTICADO"


def test_el_identificador_se_normaliza_para_el_limite(db, mails, steps):
    makeUser(db)
    for _ in range(5):
        attempt(db, identificador="  " + EMAIL.upper() + " ")
    assert attempt(db, identificador=EMAIL).code == "CUENTA_BLOQUEADA"


def test_existente_e_inexistente_reciben_la_misma_respuesta_al_limite(db, mails, steps):
    makeUser(db)
    existing = [attempt(db, identificador=EMAIL) for _ in range(5)]
    missing = [attempt(db, identificador="nadie@example.com") for _ in range(5)]
    assert [(e.code, e.message) for e in existing] == [(m.code, m.message) for m in missing]

    blockedExisting = attempt(db, identificador=EMAIL)
    blockedMissing = attempt(db, identificador="nadie@example.com")
    assert (blockedExisting.code, blockedExisting.message, blockedExisting.retryAfterSeconds) == (
        blockedMissing.code, blockedMissing.message, blockedMissing.retryAfterSeconds)


def test_cuenta_inexistente_responde_igual_que_contrasena_incorrecta(db, mails, steps):
    makeUser(db)
    missing = attempt(db, identificador="nadie@example.com")
    wrong = attempt(db, identificador=EMAIL)
    assert (missing.code, missing.message) == (wrong.code, wrong.message)
    assert wrong.retryAfterSeconds is None


def test_el_limite_corto_se_levanta_pero_el_largo_sigue_vigente(db, mails, steps):
    """Quince fallos en una hora: el límite de 15 min vence, pero el de una hora sigue bloqueando hasta que venzan los fallos."""
    makeUser(db)
    for _ in range(5):
        attempt(db)
    steps.advance(LIMITE_CORTO_SEGUNDOS + 1)
    for _ in range(5):
        attempt(db)
    steps.advance(LIMITE_CORTO_SEGUNDOS + 1)
    for _ in range(5):
        attempt(db)  # 15 fallos en poco más de una hora
    blocked = attempt(db, PASSWORD)
    assert blocked.code == "CUENTA_BLOQUEADA"
    assert blocked.retryAfterSeconds > LIMITE_CORTO_SEGUNDOS  # ahora manda la ventana de una hora


def test_el_limite_tambien_aplica_al_acceso_de_administracion(db, mails, steps):
    makeUser(db, tipoCuenta="ADMINISTRADOR_PLATAFORMA")
    for _ in range(5):
        attempt(db, acceso="PLATAFORMA")
    assert attempt(db, PASSWORD, acceso="PLATAFORMA").code == "CUENTA_BLOQUEADA"


def test_aviso_al_titular_una_vez_al_alcanzar_el_limite_y_nunca_a_quien_ataca(db, mails, steps):
    makeUser(db)
    for _ in range(5):
        attempt(db)
    alerts = [m for m in mails if m["to"] == EMAIL and ALERTA_ASUNTO in m["subject"].lower()]
    assert len(alerts) == 1
    for _ in range(10):
        attempt(db)  # mientras dura el límite no se suman avisos
    assert len([m for m in mails if ALERTA_ASUNTO in m["subject"].lower()]) == 1


def test_cuenta_inexistente_al_limite_no_envia_ningun_correo(db, mails, steps):
    makeUser(db)
    for _ in range(8):
        attempt(db, identificador="nadie@example.com")
    assert mails == []


def test_solicitudes_simultaneas_no_superan_el_limite(engine, db, mails, steps):
    makeUser(db)
    workers = 8
    barrier = threading.Barrier(workers)
    makeSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    results, errors = [], []

    def worker():
        session = makeSession()
        try:
            barrier.wait()
            results.append(attempt(session))
        except Exception as error:  # pragma: no cover - diagnóstico
            errors.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    listed = codes(results)
    # Solo cinco intentos llegan a verificar la contraseña; el resto se rechaza por el límite.
    assert listed.count("CREDENCIALES_INVALIDAS") == 5
    assert listed.count("CUENTA_BLOQUEADA") == workers - 5


def test_retry_after_se_expresa_en_la_cabecera_del_rechazo(db, mails, steps):
    makeUser(db)
    for _ in range(5):
        attempt(db)
    steps.advance(120)
    with pytest.raises(AuthError) as locked:
        authService.loginLocal(db, EMAIL, WRONG, ClientInfo(ip=ORIGEN_A))
    assert locked.value.retryAfterSeconds == LIMITE_CORTO_SEGUNDOS - 120
    response = asyncio.run(authErrorHandler(None, locked.value))
    assert response.status_code == 429
    assert response.headers["Retry-After"] == str(LIMITE_CORTO_SEGUNDOS - 120)


# --- Reautenticación con sesión (bloqueo de CredencialLocal, sin cambios) -----------------------------------------------------------


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
