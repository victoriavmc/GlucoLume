# Límite de intentos del inicio de sesión a nivel HTTP (M-2, auditoría 07/11/2026), con la aplicación real.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_login_throttle.py -v
#
# Reproduce la secuencia del auditor (15 POST consecutivos a /api/v1/auth/login con credenciales incorrectas) y comprueba: intentos válidos,
# inválidos, límite alcanzado con Retry-After, respuestas iguales para cuentas existentes e inexistentes, ausencia de bloqueos por terceros,
# recuperación posterior, y que la recuperación de contraseña y Google no dependen del límite del login.

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.db.session import getDb
from app.main import app
from app.services import auth as authService
from app.services import rateLimiter
from app.services.rateLimiter import RateLimiter
from tests.test_account_deletion import EMAIL, PASSWORD, db, engine, makeUser, mails  # noqa: F401 - fixtures

WRONG = "OtraClave#2026"
LOGIN = "/api/v1/auth/login"
LIMITE_CORTO = 15 * 60
ORIGEN_ATACANTE = "198.51.100.10"
ORIGEN_VICTIMA = "203.0.113.30"


class FakeMonotonic:
    now = 50_000.0

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


def http(ip: str) -> TestClient:
    return TestClient(app, raise_server_exceptions=False, client=(ip, 50000))


def login(ip: str, identificador: str, password: str):
    response = http(ip).post(LOGIN, json={"identificador": identificador, "password": password})
    return response


def summary(response):
    """Lo que ve quien ataca: estado, código, mensaje y Retry-After."""
    body = response.json()
    return response.status_code, body.get("codigo"), body.get("detail"), response.headers.get("retry-after")


# --- La secuencia del auditor -------------------------------------------------------------------------------------------------------


def test_quince_intentos_seguidos_desde_una_ip_quedan_limitados_con_retry_after(onlyDb, db, mails, steps):
    """Antes: 15 × 401 sin Retry-After. Ahora: 5 × 401 y el resto 429 con Retry-After, desde el 6.º."""
    statuses, retries = [], []
    for _ in range(15):
        r = login(ORIGEN_ATACANTE, "nadie@example.com", WRONG)
        statuses.append(r.status_code)
        retries.append(r.headers.get("retry-after"))
    assert statuses == [401] * 5 + [429] * 10
    assert retries[:5] == [None] * 5
    assert all(value == str(LIMITE_CORTO) for value in retries[5:])


def loginPlataforma(ip: str, identificador: str, password: str):
    return http(ip).post(LOGIN, json={"identificador": identificador, "password": password, "acceso": "PLATAFORMA"})


def test_quince_intentos_al_acceso_administrativo_quedan_limitados(onlyDb, db, mails, steps):
    """A-1 (auditoría 2, 07/11/2026): la misma secuencia contra una cuenta administrativa por el acceso PLATAFORMA. Antes de M-2 respondía
    15 × 401 sin Retry-After; el límite por (cuenta, origen) se aplica antes de buscar la cuenta y del control de acceso."""
    makeUser(db, tipoCuenta="ADMINISTRADOR_PLATAFORMA")
    db.commit()
    statuses, retries = [], []
    for _ in range(15):
        r = loginPlataforma(ORIGEN_ATACANTE, EMAIL, WRONG)
        statuses.append(r.status_code)
        retries.append(r.headers.get("retry-after"))
    assert statuses == [401] * 5 + [429] * 10
    assert all(value == str(LIMITE_CORTO) for value in retries[5:])
    assert loginPlataforma(ORIGEN_ATACANTE, EMAIL, PASSWORD).status_code == 429  # ni la clave correcta salta el límite


def test_el_rechazo_limitado_tiene_forma_consistente(onlyDb, db, mails, steps):
    for _ in range(5):
        login(ORIGEN_ATACANTE, EMAIL, WRONG)
    r = login(ORIGEN_ATACANTE, EMAIL, WRONG)
    assert r.status_code == 429
    assert r.json() == {"codigo": "CUENTA_BLOQUEADA", "detail": "Demasiados intentos fallidos. Intentá más tarde."}
    assert r.headers["content-type"].startswith("application/json")


# --- Sin enumeración -----------------------------------------------------------------------------------------------------------------


def test_cuenta_existente_e_inexistente_se_ven_igual_antes_y_despues_del_limite(onlyDb, db, mails, steps):
    makeUser(db)
    db.commit()
    existing = [summary(login(ORIGEN_ATACANTE, EMAIL, WRONG)) for _ in range(6)]
    missing = [summary(login(ORIGEN_ATACANTE, "nadie@example.com", WRONG)) for _ in range(6)]
    assert existing[:5] == missing[:5] and all(s[0] == 401 for s in existing[:5])
    assert existing[5] == missing[5] and existing[5][0] == 429
    assert existing[5][3] == str(LIMITE_CORTO)


# --- Terceros y víctima --------------------------------------------------------------------------------------------------------------


def test_un_atacante_no_deja_fuera_a_la_victima_que_usa_la_clave_correcta(onlyDb, db, mails, steps):
    makeUser(db)
    db.commit()
    for _ in range(8):
        login(ORIGEN_ATACANTE, EMAIL, WRONG)
    assert login(ORIGEN_ATACANTE, EMAIL, PASSWORD).status_code == 429  # el atacante queda limitado a sí mismo
    victim = login(ORIGEN_VICTIMA, EMAIL, PASSWORD)
    assert victim.status_code == 200
    assert victim.json()["estado"] == "AUTENTICADO"


def test_el_acceso_vuelve_solo_cuando_vencen_los_fallos(onlyDb, db, mails, steps):
    makeUser(db)
    db.commit()
    for _ in range(5):
        login(ORIGEN_ATACANTE, EMAIL, WRONG)
    assert login(ORIGEN_ATACANTE, EMAIL, PASSWORD).status_code == 429
    steps.advance(LIMITE_CORTO + 1)
    r = login(ORIGEN_ATACANTE, EMAIL, PASSWORD)
    assert r.status_code == 200 and r.json()["estado"] == "AUTENTICADO"


# --- Recuperación de contraseña y Google no dependen del límite del login ----------------------------------------------------------


def test_la_recuperacion_de_contrasena_sigue_disponible_con_el_login_limitado(onlyDb, db, mails, steps):
    makeUser(db)
    db.commit()
    for _ in range(5):
        login(ORIGEN_ATACANTE, EMAIL, WRONG)
    assert login(ORIGEN_ATACANTE, EMAIL, PASSWORD).status_code == 429
    r = http(ORIGEN_ATACANTE).post("/api/v1/auth/password/forgot", json={"correoElectronico": EMAIL})
    assert r.status_code not in (429, 500) and r.status_code < 400


def test_el_intercambio_de_google_sigue_funcionando_con_el_login_limitado(onlyDb, db, mails, steps):
    user = makeUser(db)
    db.commit()
    for _ in range(5):
        login(ORIGEN_ATACANTE, EMAIL, WRONG)
    assert login(ORIGEN_ATACANTE, EMAIL, PASSWORD).status_code == 429
    code = authService.createGoogleExchangeCode(db, user)
    r = http(ORIGEN_ATACANTE).post("/api/v1/auth/google/exchange", json={"code": code})
    assert r.status_code == 200, r.text


# --- Intentos válidos y tipos de cuenta ----------------------------------------------------------------------------------------------


def test_inicio_de_sesion_normal_no_se_limita_y_entrega_la_sesion(onlyDb, db, mails, steps):
    makeUser(db)
    db.commit()
    r = login(ORIGEN_VICTIMA, EMAIL, PASSWORD)
    assert r.status_code == 200
    body = r.json()
    assert body["estado"] == "AUTENTICADO"
    assert body["tokens"]["accessToken"] and body["tokens"]["refreshToken"]  # sin el modo cookie (cabecera CSRF), el cuerpo lo trae


@pytest.mark.parametrize("tipoCuenta", ["CONSUMIDOR_FINAL", "USUARIO_INSTITUCIONAL"])
def test_el_limite_aplica_igual_a_cada_tipo_de_cuenta(onlyDb, db, mails, steps, tipoCuenta):
    makeUser(db, tipoCuenta=tipoCuenta)
    db.commit()
    for _ in range(5):
        login(ORIGEN_ATACANTE, EMAIL, WRONG)
    assert login(ORIGEN_ATACANTE, EMAIL, WRONG).status_code == 429
    assert login(ORIGEN_VICTIMA, EMAIL, PASSWORD).status_code == 200


# --- Ventana deslizante exacta (RateLimiter.retryAfter) ----------------------------------------------------------------------------


def test_retry_after_exacto_en_la_ventana_deslizante(steps):
    limitador = RateLimiter(3, 100)
    for _ in range(3):
        assert limitador.allow("clave")
    assert limitador.retryAfter("clave") == 100  # el primer evento vence en 100 s
    steps.advance(40)
    assert limitador.retryAfter("clave") == pytest.approx(60)
    steps.advance(60)
    assert limitador.retryAfter("clave") == 0 and limitador.allow("clave")


def test_una_rafaga_de_pares_nuevos_no_anula_el_limite_del_par_de_la_victima(monkeypatch):
    """Regresión del hallazgo bloqueante del PR #9: llenar la tabla de claves no debe desactivar el límite por (cuenta, origen)."""
    from app.services import loginThrottle

    for limitador in loginThrottle._limitadores:
        monkeypatch.setattr(limitador, "MAX_KEYS", 200)
    loginThrottle.reset()
    try:
        for i in range(600):  # primero el atacante llena la tabla con pares de un solo fallo
            loginThrottle.registrarFallo(f"nadie{i}@example.com", f"203.0.113.{i % 250}")
        for _ in range(5):  # después la víctima falla desde su origen
            loginThrottle.registrarFallo("victima@example.com", "198.51.100.9")
        assert loginThrottle.retryAfter("victima@example.com", "198.51.100.9") is not None, "el par de la víctima queda limitado"
    finally:
        loginThrottle.reset()
