# Liveness y readiness de la API (B-6, auditoría 07/11/2026).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_readyz.py -v
#
# Estados sanos y fallos simulados de dependencias (base, tabla de sesiones, base colgada), caché de la comprobación, tope de tiempo,
# y que ninguna respuesta revele detalles internos.

import inspect
import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.v1 import health
from app.main import app
from app.services import readiness
from tests.test_account_deletion import engine  # noqa: F401 - fixture: SQLite con el esquema de prueba

SECRETO = "Server=sql-interno.example;Password=ClaveSecreta123;Database=GlucoLume"


@pytest.fixture(autouse=True)
def estado_limpio(monkeypatch):
    """Cada prueba parte sin caché y sin comprobación en curso."""
    readiness.reset()
    with readiness._lock:
        readiness._probing = False
    monkeypatch.setattr(readiness, "PROBE_TIMEOUT_SECONDS", 3.0)
    yield
    readiness.reset()
    with readiness._lock:
        readiness._probing = False


@pytest.fixture
def cliente():
    return TestClient(app, raise_server_exceptions=False, client=("203.0.113.60", 50000))


class SesionFalsa:
    """Sesión que falla donde se le indique (sin base real)."""

    def __init__(self, falla_select=None, falla_base=None):
        self.falla_select = falla_select
        self.falla_base = falla_base

    def execute(self, sentencia, *args, **kwargs):
        if self.falla_base is not None and "SELECT 1" in str(sentencia):
            raise self.falla_base
        if self.falla_select is not None and "SesionUsuario" in str(sentencia):
            raise self.falla_select
        return self

    def first(self):
        return None

    def close(self):
        pass


# --- Liveness -----------------------------------------------------------------------------------------------------------------


def test_liveness_responde_200_aunque_la_base_este_caida(monkeypatch, cliente):
    monkeypatch.setattr(readiness, "newSession", lambda: (_ for _ in ()).throw(RuntimeError(SECRETO)))
    r = cliente.get("/healthz")
    assert r.status_code == 200 and r.json() == {"estado": "ok"}


# --- Estados sanos -----------------------------------------------------------------------------------------------------------


def test_readiness_sano_responde_200_listo(monkeypatch, engine, cliente):  # noqa: F811
    monkeypatch.setattr(readiness, "newSession", lambda: sessionmaker(bind=engine)())
    r = cliente.get("/api/v1/readyz")
    assert r.status_code == 200
    assert r.json() == {"estado": "listo", "dependencias": {"baseDeDatos": "ok", "tablaSesiones": "ok"}}
    assert r.headers["cache-control"] == "no-store"
    assert "retry-after" not in r.headers


# --- Fallos simulados de dependencias --------------------------------------------------------------------------------------


def test_base_caida_responde_503_con_valores_enumerados_y_sin_detalles(monkeypatch, cliente):
    monkeypatch.setattr(readiness, "newSession", lambda: SesionFalsa(falla_base=RuntimeError(SECRETO)))
    r = cliente.get("/api/v1/readyz")
    assert r.status_code == 503
    assert r.json() == {"estado": "no_listo", "dependencias": {"baseDeDatos": "no_disponible", "tablaSesiones": "no_verificado"}}
    assert r.headers["retry-after"] == str(readiness.RETRY_AFTER_SECONDS)
    assert r.headers["cache-control"] == "no-store"
    cuerpo = r.text
    for sensible in ("Server", "Password", "ClaveSecreta", "sql-interno", "Database", "RuntimeError"):
        assert sensible not in cuerpo


def test_sin_poder_crear_la_sesion_responde_503(monkeypatch, cliente):
    def sin_sesion():
        raise OSError(SECRETO)

    monkeypatch.setattr(readiness, "newSession", sin_sesion)
    r = cliente.get("/api/v1/readyz")
    assert r.status_code == 503 and r.json()["dependencias"]["baseDeDatos"] == "no_disponible"
    assert SECRETO not in r.text


def test_base_viva_pero_sin_tabla_de_sesiones_responde_503(monkeypatch, cliente):
    monkeypatch.setattr(readiness, "newSession",
                        lambda: SesionFalsa(falla_select=RuntimeError("Invalid object name 'SesionUsuario'")))
    r = cliente.get("/api/v1/readyz")
    assert r.status_code == 503
    assert r.json() == {"estado": "no_listo", "dependencias": {"baseDeDatos": "ok", "tablaSesiones": "no_disponible"}}


# --- Caché: los sondeos frecuentes no generan consultas frecuentes -----------------------------------------------------------


def test_sondeos_dentro_de_la_ventana_comprueban_una_sola_vez(monkeypatch, engine, cliente):  # noqa: F811
    monkeypatch.setattr(readiness, "newSession", lambda: sessionmaker(bind=engine)())
    reloj = {"t": 1000.0}
    monkeypatch.setattr(readiness.time, "monotonic", lambda: reloj["t"])
    llamadas = []
    real = readiness._probe

    def contada():
        llamadas.append(1)
        return real()

    monkeypatch.setattr(readiness, "_probe", contada)
    for _ in range(20):
        assert cliente.get("/api/v1/readyz").status_code == 200
    assert len(llamadas) == 1
    reloj["t"] += readiness.CACHE_SECONDS + 1
    assert cliente.get("/api/v1/readyz").status_code == 200
    assert len(llamadas) == 2


# --- Tope de tiempo y comprobación colgada -----------------------------------------------------------------------------------


def test_base_colgada_responde_503_tiempo_agotado_sin_apilar_comprobaciones(monkeypatch, cliente):
    monkeypatch.setattr(readiness, "PROBE_TIMEOUT_SECONDS", 0.2)
    bloqueo = threading.Event()
    llamadas = []

    def colgada():
        llamadas.append(1)
        bloqueo.wait(timeout=10)
        return {"baseDeDatos": "ok", "tablaSesiones": "ok"}

    monkeypatch.setattr(readiness, "_probe", colgada)
    inicio = time.monotonic()
    r = cliente.get("/api/v1/readyz")
    assert time.monotonic() - inicio < 2.0  # no espera más que el tope
    assert r.status_code == 503 and r.json()["dependencias"]["baseDeDatos"] == "tiempo_agotado"
    # Mientras la comprobación siga colgada, los siguientes pedidos no lanzan otra.
    for _ in range(5):
        assert cliente.get("/api/v1/readyz").status_code == 503
    assert len(llamadas) == 1
    bloqueo.set()


def test_concurrencia_de_sondeos_con_base_colgada_lanza_una_sola_comprobacion(monkeypatch):
    monkeypatch.setattr(readiness, "PROBE_TIMEOUT_SECONDS", 0.5)
    bloqueo = threading.Event()
    llamadas = []
    monkeypatch.setattr(readiness, "_probe", lambda: (llamadas.append(1), bloqueo.wait(timeout=10))[1] or {"baseDeDatos": "ok"})
    resultados = []
    hilos = [threading.Thread(target=lambda: resultados.append(readiness.snapshot())) for _ in range(20)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=10)
    bloqueo.set()
    assert len(llamadas) == 1
    assert all(not r["listo"] for r in resultados)


# --- Forma de la ruta y del contrato -----------------------------------------------------------------------------------------


def test_readyz_es_sincrona_para_no_bloquear_el_event_loop():
    assert not inspect.iscoroutinefunction(health.readyz)


def test_ninguna_respuesta_de_salud_expone_version_ni_detalles(monkeypatch, engine, cliente):  # noqa: F811
    monkeypatch.setattr(readiness, "newSession", lambda: sessionmaker(bind=engine)())
    for ruta in ("/healthz", "/api/v1/readyz"):
        cuerpo = cliente.get(ruta).text.lower()
        assert "version" not in cuerpo and "versión" not in cuerpo and "server" not in cuerpo and "password" not in cuerpo
