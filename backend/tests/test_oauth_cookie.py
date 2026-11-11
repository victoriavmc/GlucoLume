# Cookie del estado OAuth de Google (glucolume_oauth): atributos de Set-Cookie (auditoría 2, hallazgo A-4).
#
# Ejecutar desde backend/:  python -m pytest tests/test_oauth_cookie.py -v
#
# El middleware de sesión se construye al importar la aplicación, según si Google está configurado y con qué esquema. Por eso cada
# escenario corre en un subproceso con su propio entorno. Solo se sustituye el cliente de Authlib (que pediría los metadatos de Google);
# la cookie la emite el middleware real y el origen, la redirección y el 307 los decide la ruta real. No se contacta a Google.

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
ENV_FILE = Path(__file__).with_name("test.env")

PROBE = r"""
import json
from fastapi.testclient import TestClient
from app.integrations.google import oauth


class FakeClient:
    async def create_authorization_url(self, redirect_uri, scope=None):
        return {"url": "https://accounts.google.com/o/oauth2/v2/auth?state=probe", "state": "probe"}

    async def save_authorize_data(self, request, redirect_uri=None, **data):
        request.session["_state_google_probe"] = {"state": data["state"]}


oauth._client = lambda: FakeClient()

from app.main import app  # noqa: E402

client = TestClient(app, base_url=__import__("os").environ["PROBE_BASE_URL"], follow_redirects=False)
response = client.get("/api/v1/auth/google/login")
print(json.dumps({
    "status": response.status_code,
    "location": response.headers.get("location"),
    "setCookie": response.headers.get_list("set-cookie"),
}))
"""

CALLBACK_ORIGIN_HTTP = "http://localhost:8000"
CALLBACK_ORIGIN_HTTPS = "https://glucolume.test"


def probe(monkeypatch_env: dict[str, str], baseUrl: str) -> dict:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "GLUCOLUME_ENV_FILE": str(ENV_FILE),
        "API_ENV": "development",
        "GOOGLE_CLIENT_ID": "client-id-test",
        "GOOGLE_CLIENT_SECRET": "client-secret-test",
        "SESSION_SECRET": "s" * 40,
        "PROBE_BASE_URL": baseUrl,
        **monkeypatch_env,
    }
    result = subprocess.run(
        [sys.executable, "-c", PROBE], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout.strip().splitlines()[-1])


def oauthCookie(data: dict) -> str:
    [cookie] = [c for c in data["setCookie"] if c.startswith("glucolume_oauth=")]
    return cookie.lower()


def callbackUrl(origin: str) -> str:
    return f"{origin}/api/v1/auth/google/callback"


def test_desarrollo_http_local_sigue_sin_secure_y_con_atributos_correctos():
    # Desarrollo en http://localhost: el navegador acepta la cookie sin Secure y el flujo local sigue funcionando.
    data = probe({"GOOGLE_REDIRECT_URI": callbackUrl(CALLBACK_ORIGIN_HTTP)}, CALLBACK_ORIGIN_HTTP)
    assert data["status"] == 302 and data["location"].startswith("https://accounts.google.com/")
    cookie = oauthCookie(data)
    assert "httponly" in cookie and "samesite=lax" in cookie and "max-age=600" in cookie and "path=/" in cookie
    assert "; secure" not in cookie


def test_callback_https_emite_secure_aunque_api_env_no_sea_production():
    # A-4: el atributo dependía solo de API_ENV=production. Un callback https (Tailscale/Caddy) en otro perfil salía sin Secure.
    data = probe({"GOOGLE_REDIRECT_URI": callbackUrl(CALLBACK_ORIGIN_HTTPS)}, CALLBACK_ORIGIN_HTTPS)
    assert data["status"] == 302 and data["location"].startswith("https://accounts.google.com/")
    cookie = oauthCookie(data)
    assert "; secure" in cookie
    assert "httponly" in cookie and "samesite=lax" in cookie and "max-age=600" in cookie


def test_produccion_emite_secure_y_no_se_puede_desactivar_por_configuracion():
    data = probe({
        "API_ENV": "production", "GOOGLE_REDIRECT_URI": callbackUrl(CALLBACK_ORIGIN_HTTPS),
        "OAUTH_COOKIE_SECURE": "false",
    }, CALLBACK_ORIGIN_HTTPS)
    cookie = oauthCookie(data)
    assert "; secure" in cookie and "httponly" in cookie and "samesite=lax" in cookie


def test_override_explicito_permite_secure_en_desarrollo_local():
    # Para probar el flujo con HTTPS en localhost sin producción.
    data = probe({"GOOGLE_REDIRECT_URI": callbackUrl(CALLBACK_ORIGIN_HTTP), "OAUTH_COOKIE_SECURE": "true"}, CALLBACK_ORIGIN_HTTP)
    assert "; secure" in oauthCookie(data)


def test_origen_distinto_del_callback_redirige_sin_emitir_cookie():
    # Petición por http hacia un callback https: 307 al origen canónico, sin cookie ni bucle (comportamiento existente, debe seguir igual).
    data = probe({"GOOGLE_REDIRECT_URI": callbackUrl(CALLBACK_ORIGIN_HTTPS)}, "http://glucolume.test")
    assert data["status"] == 307
    assert data["location"].startswith(CALLBACK_ORIGIN_HTTPS + "/api/v1/auth/google/login")
    assert not [c for c in data["setCookie"] if c.startswith("glucolume_oauth=")]
