# Coste de Argon2 en el login (M-3, auditoría 07/11/2026): control de concurrencia, validación antes del hash, y compatibilidad de hashes.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_argon2_gate.py -v
#
# Las pruebas no cambian los parámetros de Argon2: comprueban que no cambien (un hash existente debe seguir verificando).

import asyncio
import inspect
import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.v1 import auth as authRoutes
from app.core import security
from app.core.exceptions import AuthError
from app.db.session import getDb
from app.main import app
from app.services import auth as authService
from app.services import loginThrottle
from app.utils.userAgent import ClientInfo
from tests.test_account_deletion import EMAIL, PASSWORD, db, engine, makeUser, mails  # noqa: F401 - fixtures

WRONG = "OtraClave#2026"
# Hash Argon2id de PASSWORD con los parámetros vigentes (t=3, m=65536, p=4), fijado como literal: debe seguir verificando tal cual.
HASH_DE_REFERENCIA = "$argon2id$v=19$m=65536,t=3,p=4$wgTpP1ZnACFzu8i8Pf+d1g$gUrDZymGVOdY0ogM3X+qjF4ttlKbHTcKYTIwBpTEuHQ"


class FakeHasher:
    """Sustituye al hasher real: bloquea hasta que el test lo libere, y cuenta cuántas operaciones corren a la vez."""

    def __init__(self, fail: Exception | None = None):
        self.active = 0
        self.maxActive = 0
        self.lock = threading.Lock()
        self.release = threading.Event()
        self.fail = fail

    def verify_and_update(self, password, passwordHash):
        with self.lock:
            self.active += 1
            self.maxActive = max(self.maxActive, self.active)
        try:
            if self.fail is not None:
                raise self.fail
            self.release.wait(timeout=10)
            return True, None
        finally:
            with self.lock:
                self.active -= 1

    def verify(self, password, passwordHash):
        self.verify_and_update(password, passwordHash)

    def hash(self, password):
        return "fake"


@pytest.fixture
def gate(monkeypatch):
    """Un lugar para Argon2 y espera máxima de 1; los tests ajustan lo que necesitan."""
    monkeypatch.setattr(security, "_argonSlots", threading.BoundedSemaphore(1))
    monkeypatch.setattr(security, "_argonWaiting", 0)
    monkeypatch.setenv("ARGON2_MAX_WAITING", "1")
    from app.core.config import getSettings

    getSettings.cache_clear()
    yield
    getSettings.cache_clear()


def wait_for(condition, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.005)
    return False


# --- Concurrencia acotada ----------------------------------------------------------------------------------------------------------


def test_no_corren_mas_operaciones_argon2_que_lugares(monkeypatch, gate):
    monkeypatch.setattr(security, "_argonSlots", threading.BoundedSemaphore(2))
    monkeypatch.setenv("ARGON2_MAX_WAITING", "8")
    from app.core.config import getSettings

    getSettings.cache_clear()
    hasher = FakeHasher()
    monkeypatch.setattr(security, "_passwordHash", hasher)
    hilos = [threading.Thread(target=security.verifyPassword, args=(PASSWORD, "x")) for _ in range(6)]
    for hilo in hilos:
        hilo.start()
    assert wait_for(lambda: hasher.active == 2)
    time.sleep(0.05)
    assert hasher.active == 2 and hasher.maxActive == 2  # los demás esperan su lugar, no corren
    hasher.release.set()
    for hilo in hilos:
        hilo.join(timeout=10)
    assert hasher.maxActive == 2 and security._argonWaiting == 0


def test_con_la_espera_llena_responde_503_de_inmediato(monkeypatch, gate):
    hasher = FakeHasher()
    monkeypatch.setattr(security, "_passwordHash", hasher)
    primero = threading.Thread(target=security.verifyPassword, args=(PASSWORD, "x"))  # ocupa el único lugar
    primero.start()
    assert wait_for(lambda: hasher.active == 1)
    segundo = threading.Thread(target=security.verifyPassword, args=(PASSWORD, "x"))  # espera (espera máxima = 1)
    segundo.start()
    assert wait_for(lambda: security._argonWaiting == 1)

    inicio = time.monotonic()
    with pytest.raises(AuthError) as busy:
        security.verifyPassword(PASSWORD, "x")
    assert time.monotonic() - inicio < 0.5  # rechazo inmediato: no retiene el hilo esperando
    assert busy.value.code == "SERVIDOR_OCUPADO"
    assert busy.value.retryAfterSeconds == security.ARGON2_RETRY_AFTER_SECONDS

    hasher.release.set()
    primero.join(timeout=10)
    segundo.join(timeout=10)


def test_esperar_un_lugar_tiene_tope_y_no_deja_la_espera_contada(monkeypatch, gate):
    monkeypatch.setattr(security, "ARGON2_WAIT_SECONDS", 0.2)
    hasher = FakeHasher()
    monkeypatch.setattr(security, "_passwordHash", hasher)
    primero = threading.Thread(target=security.verifyPassword, args=(PASSWORD, "x"))
    primero.start()
    assert wait_for(lambda: hasher.active == 1)

    inicio = time.monotonic()
    with pytest.raises(AuthError) as timedOut:
        security.verifyPassword(PASSWORD, "x")
    assert 0.15 <= time.monotonic() - inicio < 2.0
    assert timedOut.value.code == "SERVIDOR_OCUPADO"
    assert security._argonWaiting == 0  # la espera fallida no queda contada
    hasher.release.set()
    primero.join(timeout=10)


def test_el_lugar_se_libera_aunque_la_operacion_falle(monkeypatch, gate):
    monkeypatch.setattr(security, "_passwordHash", FakeHasher(fail=RuntimeError("fallo simulado")))
    with pytest.raises(RuntimeError):
        security.verifyPassword(PASSWORD, "x")
    assert security._argonSlots.acquire(blocking=False)  # el único lugar sigue disponible
    security._argonSlots.release()


@pytest.mark.parametrize("operacion", ["hashPassword", "verifyPassword", "verifyDummyPassword"])
def test_todas_las_operaciones_argon2_pasan_por_el_control(monkeypatch, gate, operacion):
    monkeypatch.setenv("ARGON2_MAX_WAITING", "0")
    from app.core.config import getSettings

    getSettings.cache_clear()
    assert security._argonSlots.acquire(blocking=False)  # se ocupa el único lugar
    llamadas = {
        "hashPassword": lambda: security.hashPassword(PASSWORD),
        "verifyPassword": lambda: security.verifyPassword(PASSWORD, security._DUMMY_PASSWORD_HASH),
        "verifyDummyPassword": lambda: security.verifyDummyPassword(PASSWORD),
    }
    with pytest.raises(AuthError) as busy:
        llamadas[operacion]()
    assert busy.value.code == "SERVIDOR_OCUPADO"
    security._argonSlots.release()


# --- Validación antes del hash -----------------------------------------------------------------------------------------------------


@pytest.fixture
def onlyDb(engine):
    makeSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def getTestDb():
        session = makeSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[getDb] = getTestDb
    yield
    app.dependency_overrides.clear()


def test_una_contrasena_de_mas_de_256_caracteres_se_rechaza_sin_calcular_argon2(monkeypatch, onlyDb):
    llamadas = []
    monkeypatch.setattr(security, "verifyPassword", lambda *a, **k: llamadas.append(a) or (False, None))
    monkeypatch.setattr(security, "verifyDummyPassword", lambda *a, **k: llamadas.append(a))
    http = TestClient(app, raise_server_exceptions=False, client=("203.0.113.40", 50000))
    r = http.post("/api/v1/auth/login", json={"identificador": "nadie@example.com", "password": "A" * 100_000})
    assert r.status_code == 422
    assert llamadas == []


def test_un_identificador_de_mas_de_254_caracteres_se_rechaza_sin_consultar_ni_hashear(monkeypatch, onlyDb):
    llamadas = []
    monkeypatch.setattr(security, "verifyPassword", lambda *a, **k: llamadas.append(a) or (False, None))
    monkeypatch.setattr(security, "verifyDummyPassword", lambda *a, **k: llamadas.append(a))
    http = TestClient(app, raise_server_exceptions=False, client=("203.0.113.41", 50000))
    r = http.post("/api/v1/auth/login", json={"identificador": "a" * 300, "password": WRONG})
    assert r.status_code == 422
    assert llamadas == []


def test_el_login_es_sincrono_y_corre_en_el_threadpool_no_en_el_event_loop():
    """Un handler async que hashea bloquearía el event loop entero (todas las peticiones). Los de contraseña deben ser síncronos."""
    assert not inspect.iscoroutinefunction(authRoutes.login)
    assert not inspect.iscoroutinefunction(authRoutes.verifyEmail)


# --- Interacción con M-2 y con la respuesta de saturación --------------------------------------------------------------------------


def test_un_intento_limitado_por_M2_no_calcula_argon2(monkeypatch, db, mails):
    makeUser(db)
    llamadas = []
    real = security.verifyPassword
    monkeypatch.setattr(security, "verifyPassword", lambda *a, **k: llamadas.append(a) or real(*a, **k))
    for _ in range(5):
        with pytest.raises(AuthError):
            authService.loginLocal(db, EMAIL, WRONG, ClientInfo(ip="198.51.100.77"))
    assert len(llamadas) == 5
    with pytest.raises(AuthError) as limited:
        authService.loginLocal(db, EMAIL, PASSWORD, ClientInfo(ip="198.51.100.77"))
    assert limited.value.code == "CUENTA_BLOQUEADA"
    assert len(llamadas) == 5  # el intento limitado no verificó ni una contraseña más


def test_saturacion_no_cuenta_como_fallo_de_contrasena(monkeypatch, db, mails):
    makeUser(db)

    def ocupado(*args, **kwargs):
        raise AuthError("SERVIDOR_OCUPADO", security.SERVER_BUSY_MESSAGE, retryAfterSeconds=2)

    monkeypatch.setattr(security, "verifyPassword", ocupado)
    for _ in range(10):
        with pytest.raises(AuthError) as busy:
            authService.loginLocal(db, EMAIL, WRONG, ClientInfo(ip="198.51.100.78"))
        assert busy.value.code == "SERVIDOR_OCUPADO"
    assert loginThrottle.retryAfter(EMAIL, "198.51.100.78") is None  # un equipo ocupado no bloquea a nadie


def test_saturacion_responde_503_con_retry_after_por_http(monkeypatch, onlyDb):
    def ocupado(*args, **kwargs):
        raise AuthError("SERVIDOR_OCUPADO", security.SERVER_BUSY_MESSAGE, retryAfterSeconds=2)

    monkeypatch.setattr(security, "verifyDummyPassword", ocupado)
    http = TestClient(app, raise_server_exceptions=False, client=("203.0.113.42", 50000))
    r = http.post("/api/v1/auth/login", json={"identificador": "nadie@example.com", "password": WRONG})
    assert r.status_code == 503
    assert r.headers["Retry-After"] == "2"
    assert r.json()["codigo"] == "SERVIDOR_OCUPADO"


# --- Compatibilidad: sin cambios de coste ni de formato -----------------------------------------------------------------------------


def test_los_parametros_de_argon2_no_cambian():
    """Regresión de coste: si alguien los baja, este test lo marca. Los valores vienen de OWASP (m ≥ 64 MiB, t = 3, p = 4)."""
    assert (security.ARGON2_TIME_COST, security.ARGON2_MEMORY_COST_KIB, security.ARGON2_PARALLELISM) == (3, 64 * 1024, 4)
    fresh = security.hashPassword(PASSWORD)
    assert fresh.startswith("$argon2id$v=19$m=65536,t=3,p=4$")


def test_un_hash_existente_sigue_verificando_sin_rehashearse():
    """Un hash guardado con los parámetros vigentes sigue verificando y no pide rehash (no hay migración de contraseñas)."""
    valid, newHash = security.verifyPassword(PASSWORD, HASH_DE_REFERENCIA)
    assert valid is True and newHash is None
    valid, _ = security.verifyPassword(WRONG, HASH_DE_REFERENCIA)
    assert valid is False


def test_una_contrasena_larga_se_verifica_con_el_mismo_costo_y_sin_error():
    """La longitud no es la causa del coste: se mide en bench_argon2.py. Aquí solo se comprueba que una entrada grande no rompe la verificación."""
    valid, _ = security.verifyPassword("A" * 100_000, HASH_DE_REFERENCIA)
    assert valid is False


def test_ninguna_verificacion_ocurre_con_la_transaccion_de_lectura_abierta(monkeypatch, db, mails):
    """La conexión a la base no debe quedar ocupada mientras Argon2 espera un lugar (M-3): antes de cada verificación se cierra la transacción."""
    makeUser(db)
    estados = []
    real = security.verifyPassword
    monkeypatch.setattr(security, "verifyPassword", lambda *a, **k: estados.append(("real", db.in_transaction())) or real(*a, **k))
    dummy = security.verifyDummyPassword
    monkeypatch.setattr(security, "verifyDummyPassword", lambda *a, **k: estados.append(("dummy", db.in_transaction())) or dummy(*a, **k))
    authService.loginLocal(db, EMAIL, PASSWORD, ClientInfo(ip="198.51.100.90"))
    with pytest.raises(AuthError):
        authService.loginLocal(db, "nadie@example.com", WRONG, ClientInfo(ip="198.51.100.91"))
    assert estados and all(not enTransaccion for _, enTransaccion in estados), estados
