# Callback de Google con el contexto de acceso (A-8, auditoría 2): el error vuelve siempre a la ruta fija del frontend, sin datos del
# flujo ni tokens, para GENERAL y PLATAFORMA. El destino no depende de ningún parámetro del pedido.
#
# Ejecutar desde backend/:  python -m pytest tests/test_google_callback_contexto.py -v
from urllib.parse import urlsplit

import pytest

from app.api.v1 import auth as authRoutes
from app.integrations.google.oauth import GoogleIdentity
from tests.test_account_deletion import db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_google_exchange import IDENTITY, googleEnv, runCallback  # noqa: F401 - fixtures

FRONTEND_CALLBACK = "http://localhost:5173/auth/google/callback"


async def _fallaIntercambio(request):
    raise RuntimeError("token de prueba que no debe filtrarse")


async def _identidad(request):
    return IDENTITY


def _errorDe(monkeypatch, db, session, fetchIdentity):
    fragment = runCallback(db, monkeypatch, fetchIdentity, session=session)
    return fragment


@pytest.mark.parametrize("acceso", ["GENERAL", "PLATAFORMA"])
def test_error_de_intercambio_vuelve_a_la_ruta_fija_sin_datos_internos(db, mails, googleEnv, monkeypatch, acceso):
    fragment = _errorDe(monkeypatch, db, {authRoutes.GOOGLE_ACCESO_KEY: acceso}, _fallaIntercambio)
    assert fragment == "error=TOKEN_INVALIDO"  # código estable; ni el mensaje interno de la excepción ni tokens


def test_cuenta_administrativa_por_el_acceso_general_se_rechaza(db, mails, googleEnv, monkeypatch):
    makeUser(db, tipoCuenta="ADMINISTRADOR_PLATAFORMA", email=IDENTITY.email)
    fragment = _errorDe(monkeypatch, db, {authRoutes.GOOGLE_ACCESO_KEY: "GENERAL"}, _identidad)
    assert fragment == "error=ACCESO_PLATAFORMA_REQUERIDO"


def test_cuenta_general_por_el_acceso_administrativo_se_rechaza(db, mails, googleEnv, monkeypatch):
    makeUser(db, tipoCuenta="CONSUMIDOR_FINAL", email=IDENTITY.email)
    fragment = _errorDe(monkeypatch, db, {authRoutes.GOOGLE_ACCESO_KEY: "PLATAFORMA"}, _identidad)
    assert fragment == "error=ACCESO_PLATAFORMA_DENEGADO"


@pytest.mark.parametrize("acceso", ["GENERAL", "PLATAFORMA"])
def test_callback_exitoso_sigue_entregando_solo_el_codigo(db, mails, googleEnv, monkeypatch, acceso):
    tipo = "CONSUMIDOR_FINAL" if acceso == "GENERAL" else "ADMINISTRADOR_PLATAFORMA"
    makeUser(db, tipoCuenta=tipo, email=IDENTITY.email)
    fragment = _errorDe(monkeypatch, db, {authRoutes.GOOGLE_ACCESO_KEY: acceso}, _identidad)
    assert fragment.startswith("code=") and "recordar" not in fragment


def test_sin_contexto_en_la_sesion_el_error_sigue_en_la_ruta_fija(db, mails, googleEnv, monkeypatch):
    fragment = _errorDe(monkeypatch, db, {}, _fallaIntercambio)
    assert fragment == "error=TOKEN_INVALIDO"
