# Errores 500 inesperados: respuesta genérica, cabeceras de seguridad y un evento de auditoría sin el mensaje de la excepción (H-15).

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api import unhandledErrors
from app.api.errors import authErrorHandler
from app.api.requestContext import RequestContextMiddleware
from app.api.securityHeaders import SecurityHeadersMiddleware
from app.api.unhandledErrors import UnhandledErrorMiddleware
from app.core.exceptions import AuthError
from app.services import auditClassification as classification
from tests.test_account_deletion import db, engine  # noqa: F401 - fixtures
from tests.test_audit_security import contextOf, events

SECRET_IN_MESSAGE = "dato-personal-que-no-debe-quedar@example.com"


def buildApp() -> FastAPI:
    """Las mismas tres capas que app/main.py, en el mismo orden, con rutas que fallan."""
    app = FastAPI()
    app.add_exception_handler(AuthError, authErrorHandler)

    @app.get("/api/v1/falla/{item}")
    def falla(item: str):
        raise RuntimeError(f"falló con {SECRET_IN_MESSAGE}")

    @app.get("/api/v1/rechazo")
    def rechazo():
        raise AuthError("TOKEN_INVALIDO", "No autorizado.")

    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    return app


@pytest.fixture
def failing(engine, monkeypatch):
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(unhandledErrors, "sessionFactory", lambda: sessions())
    return TestClient(buildApp(), client=("203.0.113.7", 50000))


def test_un_error_inesperado_responde_500_generico_con_cabeceras_y_correlacion(failing, db):
    response = failing.get("/api/v1/falla/abc", headers={"X-Request-ID": "corr-0001"})
    assert response.status_code == 500
    assert response.json() == {"codigo": "ERROR_SERVIDOR", "detail": unhandledErrors.MESSAGE}
    assert SECRET_IN_MESSAGE not in response.text and "RuntimeError" not in response.text
    assert response.headers["X-Request-ID"] == "corr-0001"
    assert response.headers["X-Content-Type-Options"] == "nosniff" and response.headers["Cache-Control"] == "no-store"


def test_el_error_inesperado_queda_en_la_auditoria_sin_el_mensaje_de_la_excepcion(failing, db):
    failing.get("/api/v1/falla/abc", headers={"X-Request-ID": "corr-0002", "User-Agent": "pruebas/1.0"})
    [event] = events(db, classification.ACCION_ERROR_INESPERADO)
    context = contextOf(db, event)
    assert (event.tipoEvento, event.modulo, event.resultado) == ("ACCESO", "SISTEMA", "FALLO")
    assert event.observacion == "RuntimeError en GET /api/v1/falla/{item}"
    assert SECRET_IN_MESSAGE not in repr((event.observacion, event.datosNuevos, event.datosPrevios))
    assert (context.ipOrigen, context.motivo, context.idCorrelacion) == ("203.0.113.7", "ERROR_INTERNO", "corr-0002")
    assert classification.severity(event.accion, event.resultado, event.tipoEvento, classification.classify(event.accion, event.resultado)) \
        == classification.ADVERTENCIA


def test_los_errores_controlados_no_se_registran_como_inesperados(failing, db):
    assert failing.get("/api/v1/rechazo").status_code == 401  # lo resuelve el manejador de AuthError, antes de llegar al middleware
    assert events(db, classification.ACCION_ERROR_INESPERADO) == []


def test_si_la_auditoria_falla_igual_se_responde_500(engine, monkeypatch):
    def broken():
        raise RuntimeError("base caída")

    monkeypatch.setattr(unhandledErrors, "sessionFactory", broken)
    response = TestClient(buildApp()).get("/api/v1/falla/abc")
    assert response.status_code == 500 and response.json()["codigo"] == "ERROR_SERVIDOR"
