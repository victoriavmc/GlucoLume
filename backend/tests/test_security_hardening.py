# Pruebas de seguridad transversales (auditoría de ciberseguridad previa al despliegue).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_security_hardening.py -v
#
# Usan el esquema SQLite temporal de test_account_deletion.py y un SMTP simulado: no tocan SQL Server real ni envían correos. Cubren:
#   - límite de solicitudes por IP y reenvío de verificación (anti correo masivo y anti enumeración de correos);
#   - cabeceras de seguridad de la API, Swagger/OpenAPI ocultos en producción y /healthz;
#   - la IP del cliente no se puede falsificar (contrato Nginx <-> uvicorn);
#   - invariantes del contrato de la API: todo endpoint privado exige sesión, ningún cuerpo acepta campos de más (mass assignment) y
#     ninguna respuesta incluye hashes, secretos ni tokens de uso interno.

import json
import os
import re
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import rateLimit
from app.api.deps import getDb
from app.api.securityHeaders import HSTS_VALUE, SecurityHeadersMiddleware
from app.core.exceptions import AuthError
from app.schemas.auth import RegisterRequest
from app.schemas.user import UserProfileUpdate
from app.services import auth as authService
from app.services.contact import RateLimiter
from tests.test_account_deletion import db, engine, mails  # noqa: F401 - fixtures

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
PASSWORD = "Zafiro#Montana2026"  # nosec B105 - contraseña de prueba


@pytest.fixture
def api(db, engine):  # noqa: F811
    from app.main import app

    def testDb():
        yield db

    app.dependency_overrides[getDb] = testDb
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def register(db, email="victima@example.com", usuario="victimaprueba"):
    return authService.registerLocal(
        db,
        RegisterRequest(nombre="Victima", apellido="Prueba", correoElectronico=email, password=PASSWORD,
                        tipoCuenta="CONSUMIDOR_FINAL", aceptaPoliticaPrivacidad=True, usuario=usuario),
    )


# --- Reenvío de la verificación: sin correo masivo y sin enumeración ----------------------------------------------------------


def test_el_reenvio_de_verificacion_no_inunda_de_correos_a_un_tercero(db, mails):
    register(db)
    assert len(mails) == 1  # el del registro
    for _ in range(25):
        authService.resendVerification(db, "victima@example.com")
    assert len(mails) == 1, "Dentro del intervalo mínimo no se emite ningún correo nuevo."


def test_el_reenvio_vuelve_a_enviar_pasado_el_intervalo(db, mails, monkeypatch):
    register(db)
    later = authService.nowForDb() + timedelta(seconds=authService.VERIFICATION_RESEND_MIN_INTERVAL_SECONDS + 1)
    monkeypatch.setattr(authService, "nowForDb", lambda: later)
    authService.resendVerification(db, "victima@example.com")
    assert len(mails) == 2


def test_el_reenvio_responde_igual_exista_o_no_la_cuenta(db, mails):
    from tests.test_account_deletion import makeUser

    makeUser(db, email="activa@example.com", usuario="activa")  # cuenta ya verificada
    before = len(mails)
    for email in ("no-existe@example.com", "activa@example.com"):
        authService.resendVerification(db, email)  # ni CORREO_NO_REGISTRADO ni CUENTA_YA_VERIFICADA
    assert len(mails) == before, "A una cuenta inexistente o ya verificada no se le envía nada."


def test_el_endpoint_de_reenvio_devuelve_202_neutro(api):
    response = api.post("/api/v1/auth/verify-email/resend", json={"correoElectronico": "no-existe@example.com"})
    assert response.status_code == 202
    assert "no-existe" not in response.text


# --- Límite de solicitudes por IP ---------------------------------------------------------------------------------------------


def test_el_endpoint_de_reenvio_responde_429_al_superar_el_limite_por_ip(api):
    maximum, _ = rateLimit.LIMITS["resend"]
    codes = [api.post("/api/v1/auth/verify-email/resend", json={"correoElectronico": f"x{i}@example.com"}).status_code
             for i in range(maximum + 2)]
    assert codes[:maximum] == [202] * maximum
    assert codes[maximum:] == [429, 429]
    blocked = api.post("/api/v1/auth/verify-email/resend", json={"correoElectronico": "otra@example.com"})
    assert blocked.json()["codigo"] == "DEMASIADAS_SOLICITUDES"
    assert int(blocked.headers["Retry-After"]) > 0


def test_el_login_tiene_limite_por_ip_aunque_se_prueben_cuentas_distintas(api):
    maximum, _ = rateLimit.LIMITS["login"]
    codes = {api.post("/api/v1/auth/login", json={"identificador": f"nadie{i}@example.com", "password": "Cualquiera#2026"}).status_code
             for i in range(maximum)}
    assert codes == {401}
    assert api.post("/api/v1/auth/login", json={"identificador": "otro@example.com", "password": "Cualquiera#2026"}).status_code == 429


def test_los_endpoints_con_sesion_tienen_limite_por_ip(api, monkeypatch):
    """H-11: quien presenta un token (aunque sea robado) también tiene tope por IP; sin credenciales sigue el 401 de siempre, sin consumir el cupo."""
    monkeypatch.setitem(rateLimit.LIMITS, "authenticated", (5, 60))
    monkeypatch.setitem(rateLimit._limiters, "authenticated", rateLimit.RateLimiter(5, 60))
    headers = {"Authorization": "Bearer token-que-no-es-valido"}
    codes = [api.get("/api/v1/auth/me", headers=headers).status_code for _ in range(8)]
    assert codes == [401] * 5 + [429] * 3
    blocked = api.get("/api/v1/auth/me", headers=headers)
    assert blocked.json()["codigo"] == "DEMASIADAS_SOLICITUDES" and int(blocked.headers["Retry-After"]) == 60
    assert [api.get("/api/v1/auth/me").status_code for _ in range(8)] == [401] * 8  # sin credenciales no cuenta


@pytest.mark.parametrize("path, body", [
    ("/api/v1/auth/register", {}), ("/api/v1/auth/password/forgot", {"correoElectronico": "a@example.com"}),
    ("/api/v1/auth/password/reset", {}), ("/api/v1/auth/mfa/verify", {}), ("/api/v1/auth/refresh", {"refreshToken": "x"}),
    ("/api/v1/auth/google/exchange", {"code": "x"}), ("/api/v1/auth/account-activation/check", {"token": "x"}),
    ("/api/v1/platform/password/forgot", {"correoElectronico": "a@example.com"}),
])
def test_todos_los_endpoints_publicos_sensibles_tienen_limite(api, path, body):
    """Se agotan los contadores de la ruta y el pedido siguiente es 429 (aunque el cuerpo sea inválido: el límite va antes)."""
    for limiter in rateLimit._limiters.values():
        for _ in range(limiter.maxEvents):
            limiter.allow("testclient")
    assert api.post(path, json=body).status_code == 429, path


def test_el_limitador_descarta_claves_vencidas_para_no_crecer_sin_limite():
    limiter = RateLimiter(1, 10)
    for i in range(RateLimiter.PURGE_THRESHOLD + 10):
        limiter.allow(f"ip-{i}", now=0.0)
    limiter.allow("nueva", now=100.0)  # todas las anteriores ya vencieron
    assert len(limiter._events) < 10


# --- Cabeceras de seguridad, Swagger oculto en producción, /healthz -------------------------------------------------------------


def test_cabeceras_de_seguridad_en_la_api(api):
    response = api.get("/api/v1/auth/me")  # 401 sin sesión: también lleva las cabeceras
    assert response.status_code == 401
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert "Strict-Transport-Security" not in response.headers  # fuera de producción / sin HTTPS


def test_el_middleware_respeta_cabeceras_de_la_ruta_y_pone_hsts_solo_en_https():
    app = FastAPI()

    @app.get("/api/v1/stream")
    def stream():
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("x", headers={"Cache-Control": "no-cache"})

    app.add_middleware(SecurityHeadersMiddleware, hsts=True)
    secure = TestClient(app, base_url="https://api.example.com").get("/api/v1/stream")
    assert secure.headers["Cache-Control"] == "no-cache"  # la ruta manda
    assert secure.headers["Strict-Transport-Security"] == HSTS_VALUE
    plain = TestClient(app, base_url="http://api.example.com").get("/api/v1/stream")
    assert "Strict-Transport-Security" not in plain.headers


PRODUCTION_PROBE = """
import json
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app, base_url="https://glucolume.example.com")
out = {"openapi_url": app.openapi_url, "docs": c.get("/docs").status_code, "redoc": c.get("/redoc").status_code,
       "openapi": c.get("/openapi.json").status_code, "health": c.get("/healthz").status_code,
       "hsts": c.get("/healthz").headers.get("Strict-Transport-Security")}
print("PROBE" + json.dumps(out))
"""


def test_en_produccion_no_se_publican_swagger_ni_openapi_y_hay_hsts():
    env = {**os.environ, "API_ENV": "production", "DB_HOST": "x", "DB_NAME": "x", "DB_USER": "x", "DB_PASSWORD": "x",
           "JWT_SECRET": "p" * 40, "FRONTEND_URL": "https://glucolume.example.com"}
    result = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {str(BACKEND)!r})\n{PRODUCTION_PROBE}"],
                            env=env, capture_output=True, text=True, timeout=120, cwd=BACKEND)
    line = next((l for l in result.stdout.splitlines() if l.startswith("PROBE")), None)
    assert line, result.stderr[-800:]
    probe = json.loads(line[5:])
    assert probe["openapi_url"] is None
    assert (probe["docs"], probe["redoc"], probe["openapi"]) == (404, 404, 404)
    assert probe["health"] == 200
    assert probe["hsts"] == HSTS_VALUE


# --- La IP del cliente no se puede falsificar (contrato Nginx <-> uvicorn) -------------------------------------------------------


def test_nginx_sobrescribe_x_forwarded_for_y_no_lo_acumula():
    """uvicorn (FORWARDED_ALLOW_IPS=*) toma el PRIMER valor de X-Forwarded-For: si Nginx agregara la IP real al final de lo que mandó el
    cliente, éste elegiría la suya y evadiría los límites por IP. Nginx debe fijar un único valor."""
    conf = (REPO / "docker" / "nginx" / "default.conf.template").read_text(encoding="utf-8")
    assert "$proxy_add_x_forwarded_for" not in conf
    assert len(re.findall(r"proxy_set_header X-Forwarded-For \$remote_addr;", conf)) == conf.count("proxy_pass")
    assert "set_real_ip_from ${TRUSTED_PROXY_CIDR};" in conf and "real_ip_recursive on;" in conf
    assert "0.0.0.0/0" not in conf
    compose = (REPO / "compose.yaml").read_text(encoding="utf-8")
    assert re.search(r"TRUSTED_PROXY_CIDR:\s*\$\{FRONTEND_TRUSTED_PROXY_CIDR:-172\.16\.0\.0/12\}", compose)


def test_nginx_no_registra_la_query_de_los_enlaces_con_token():
    """H-14: los enlaces de correo llevan un token de un solo uso en «?token=»; el log de accesos registra la ruta original sin query ($log_path), no el pedido completo."""
    conf = (REPO / "docker" / "nginx" / "default.conf.template").read_text(encoding="utf-8")
    format_ = re.search(r"^log_format sin_query (.+);$", conf, re.M).group(1)
    assert "$log_path" in format_ and not re.search(r"\$(request|request_uri|args|query_string|uri)\b", format_)
    # $log_path sale de $request_uri cortado en el «?» (la captura no admite «?»); $uri se evita: try_files lo reescribe a /index.html
    assert re.search(r'map \$request_uri \$log_path \{\s*"~\^\(\?<ruta>\[\^\?\]\*\)" \$ruta;', conf)
    assert "access_log /dev/stdout sin_query;" in conf
    assert not re.search(r"access_log\s+(?!off\b)(?!/dev/stdout sin_query;)", conf)  # ningún otro access_log con el formato por defecto


def test_csp_de_la_api_en_nginx_es_la_misma_que_la_del_backend():
    """B-3: una sola fuente de la política de la API. Nginx la elige por ruta y debe coincidir con SecurityHeadersMiddleware.API_CSP."""
    from app.api.securityHeaders import API_CSP

    conf = (REPO / "docker" / "nginx" / "default.conf.template").read_text(encoding="utf-8")
    mapa = re.search(r"map \$request_uri \$csp_value \{\n(.*?)\n\}", conf, re.S).group(1)
    apiCsp = re.search(r'"~\^/api[^"]*" "([^"]+)";', mapa).group(1)
    assert apiCsp == API_CSP
    assert conf.count(API_CSP) == 1  # el literal aparece una sola vez: no se copia en cada ubicación
    assert "add_header Content-Security-Policy $csp_value always;" in conf


def test_hsts_de_nginx_y_del_backend_son_el_mismo_valor():
    """Un solo valor de HSTS en el código: el de Nginx (map $hsts_value) y el del backend (HSTS_VALUE)."""
    conf = (REPO / "docker" / "nginx" / "default.conf.template").read_text(encoding="utf-8")
    assert '" "%s";' % HSTS_VALUE in conf  # la línea del map: "~^https:..." "max-age=...";


def test_ubicaciones_con_cabeceras_propias_declaran_las_que_el_server_no_puede_heredar():
    """Una ubicación con add_header propio no hereda las del server: debe declarar X-Frame-Options y Permissions-Policy (B-3)."""
    conf = (REPO / "docker" / "nginx" / "default.conf.template").read_text(encoding="utf-8")
    for nombre, patron in (
        ("swagger", r"location ~ \^/\(docs\|redoc\|openapi\\\.json\)\$ \{(.*?)\n    \}"),
        ("sse", r"location ~ \^/api/v1/acquisition/\(telemetry/\)\?stream\$ \{(.*?)\n    \}"),
    ):
        bloque = re.search(patron, conf, re.S).group(1)
        assert "add_header X-Frame-Options" in bloque and "add_header Permissions-Policy" in bloque, nombre


def test_tamano_del_cuerpo_por_operacion_y_sin_tope_global_de_1_mb():
    """B-1 (auditoría 07/11/2026): tope general de 160 KB, 16 KB en autenticación y tramos con lotes legítimos (sin el global de 1 MB)."""
    conf = (REPO / "docker" / "nginx" / "default.conf.template").read_text(encoding="utf-8")
    assert "client_max_body_size 1m;" not in conf
    server = conf.split("server {", 1)[1]
    assert server.count("client_max_body_size 160k;") == 1
    tramos = {
        r"^/api/v1/acquisition/(bridge|browser)/ingest$": "768k",
        r"^/api/v1/measurements/[^/]+/samples$": "384k",
        r"^/api/v1/institutions/[^/]+/operators/[^/]+/offboard$": "384k",
    }
    for regex, limite in tramos.items():
        bloque = re.search(r"location ~ " + re.escape(regex) + r" \{(.*?)\n    \}", conf, re.S)
        assert bloque is not None, regex
        assert f"client_max_body_size {limite};" in bloque.group(1), regex
        assert "proxy_pass http://$backend;" in bloque.group(1), regex
    auth = re.search(r"location \^~ /api/v1/auth/ \{(.*?)\n    \}", conf, re.S).group(1)
    assert "client_max_body_size 16k;" in auth and "error_page 413 = @cuerpo_grande;" in auth


def test_413_responde_en_formato_json_de_la_api():
    """El 413 de Nginx tiene el mismo formato que las respuestas de la API (codigo + detail), no la página HTML de Nginx."""
    conf = (REPO / "docker" / "nginx" / "default.conf.template").read_text(encoding="utf-8")
    assert "error_page 413 = @cuerpo_grande;" in conf
    bloque = re.search(r"location @cuerpo_grande \{(.*?)\n    \}", conf, re.S).group(1)
    assert "internal;" in bloque and "default_type application/json;" in bloque
    assert "CUERPO_DEMASIADO_GRANDE" in bloque and "return 413" in bloque


def test_nginx_limita_el_cuerpo_de_autenticacion():
    """B-1 (auditoría 07/11/2026): los formularios de autenticación no necesitan más de unos KB; el tope general de /api/ se mantiene."""
    conf = (REPO / "docker" / "nginx" / "default.conf.template").read_text(encoding="utf-8")
    auth = re.search(r"location \^~ /api/v1/auth/ \{(.*?)\n    \}", conf, re.S).group(1)
    assert "client_max_body_size 16k;" in auth
    assert "client_max_body_size 160k;" in conf  # tope general (B-1): ya no 1 MB


def test_nginx_responde_el_limite_de_rafaga_de_autenticacion_como_la_api():
    """M-2 (auditoría 07/11/2026): el 429 del borde era la página HTML de Nginx, sin Retry-After. Ahora es el mismo JSON de la API."""
    conf = (REPO / "docker" / "nginx" / "default.conf.template").read_text(encoding="utf-8")
    auth = re.search(r"location \^~ /api/v1/auth/ \{(.*?)\n    \}", conf, re.S).group(1)
    assert "error_page 429 = @auth_limite;" in auth
    block = re.search(r"location @auth_limite \{(.*?)\n    \}", conf, re.S).group(1)
    assert "internal;" in block and "default_type application/json;" in block and "add_header Retry-After 1 always;" in block
    assert "DEMASIADAS_SOLICITUDES" in block and "return 429" in block
    assert "Content-Security-Policy" in block and "X-Content-Type-Options" in block  # sin el server, hay que repetirlas


def test_api_sin_barra_redirige_relativo_con_308_y_sin_proxy():
    """M-1 (auditoría 07/11/2026): /api no debe generar una URL absoluta con esquema y puerto internos. Redirección relativa, 308 (conserva el
    método) y sin llegar al backend."""
    conf = (REPO / "docker" / "nginx" / "default.conf.template").read_text(encoding="utf-8")
    assert "absolute_redirect off;" in conf
    bloque = re.search(r"location = /api \{(.*?)\n    \}", conf, re.S)
    assert bloque is not None
    assert "return 308 /api/$is_args$args;" in bloque.group(1)
    assert "proxy_pass" not in bloque.group(1)


def test_nginx_no_apunta_a_su_propio_loopback_ni_a_localhost():
    """La propuesta del informe (proxy_pass a 127.0.0.1:8080 dentro del contenedor del frontend) se proxifica a sí misma: 502 en medición."""
    conf = (REPO / "docker" / "nginx" / "default.conf.template").read_text(encoding="utf-8")
    assert "proxy_pass http://127.0.0.1" not in conf and "proxy_pass http://localhost" not in conf
    assert "proxy_pass http://$backend;" in conf


def test_upstream_por_defecto_coincide_con_el_puerto_real_del_backend():
    """Dockerfile del frontend, compose y backend deben apuntar al mismo puerto: el backend escucha en 8000 (uvicorn y EXPOSE)."""
    frontend = (REPO / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"ENV BACKEND_UPSTREAM=backend:8000 \\", frontend)
    compose = (REPO / "compose.yaml").read_text(encoding="utf-8")
    assert re.search(r"BACKEND_UPSTREAM:\s*\$\{FRONTEND_BACKEND_UPSTREAM:-backend:8000\}", compose)
    backend = (REPO / "backend" / "Dockerfile").read_text(encoding="utf-8")
    assert "EXPOSE 8000" in backend and '"--port", "8000"' in backend


def test_nginx_expone_solo_la_liveness_de_la_api():
    """B-6 (auditoría 07/11/2026): /api/v1/healthz reenvía el /healthz del backend (sin base de datos). La readiness consulta la base
    y no se publica: Nginx la responde 404 (la ruta exacta gana al prefijo /api/)."""
    conf = (REPO / "docker" / "nginx" / "default.conf.template").read_text(encoding="utf-8")
    block = re.search(r"location = /api/v1/healthz \{(.*?)\n    \}", conf, re.S).group(1)
    assert "rewrite ^ /healthz break;" in block and "proxy_pass http://$backend;" in block
    ready = re.search(r"location = /api/v1/readyz \{(.*?)\n    \}", conf, re.S).group(1)
    assert "return 404" in ready and "proxy_pass" not in ready


def test_login_acota_la_contrasena_de_entrada():
    """M-3 (auditoría 07/11/2026): el login aceptaba contraseñas de cualquier longitud. Tope de 256, por encima de la política de 128
    para no bloquear contraseñas creadas antes de ella."""
    from app.schemas.auth import LoginRequest

    LoginRequest(identificador="persona@example.com", password="x" * 256)
    with pytest.raises(ValidationError):
        LoginRequest(identificador="persona@example.com", password="x" * 257)


def test_nginx_es_unico_emisor_de_cabeceras_que_el_backend_repite():
    """B-3 (auditoría 07/11/2026): la API recibía dos CSP y dos Referrer-Policy. Cada ubicación proxy descarta las del backend que Nginx
    también agrega; la CSP del backend se conserva solo en el flujo SSE, que no define una propia."""
    conf = (REPO / "docker" / "nginx" / "default.conf.template").read_text(encoding="utf-8")
    proxies = conf.count("proxy_pass http://$backend;")
    for header in ("X-Content-Type-Options", "Referrer-Policy", "Strict-Transport-Security"):
        assert conf.count(f"proxy_hide_header {header};") == proxies, header
    assert conf.count("proxy_hide_header Content-Security-Policy;") == proxies - 1


def test_nginx_redirige_con_ruta_relativa_sin_puerto_interno():
    """M-1 (auditoría 07/11/2026): /api redirigía a http://<host>:8080/api/, con el puerto interno y sin TLS. Redirección relativa."""
    conf = (REPO / "docker" / "nginx" / "default.conf.template").read_text(encoding="utf-8")
    assert re.search(r"^    absolute_redirect off;$", conf, re.M)


def test_controles_de_infraestructura_preparados():
    """GL-18/19/03/21: configuraciones que no se pueden verificar sin desplegar, fijadas para que no retrocedan."""
    conf = (REPO / "docker" / "nginx" / "default.conf.template").read_text(encoding="utf-8")
    appCsp = re.search(r"^    \"~\^/api\(/\|\\\?\|\$\)\" \"[^\"]+\";\n    default \"([^\"]+)\";", conf, re.M).group(1)  # la de la app: default del map $csp_value
    assert "unsafe-inline" not in appCsp and "style-src 'self';" in appCsp and "script-src 'self';" in appCsp
    dev = (REPO / "compose.dev.yaml").read_text(encoding="utf-8")
    assert 'FORWARDED_ALLOW_IPS: "127.0.0.1"' in dev  # el backend publicado en desarrollo no confía en X-Forwarded-*
    compose = (REPO / "compose.yaml").read_text(encoding="utf-8")
    backend = compose.split("\n  lifecycle:")[0]
    assert 'DB_JOBS_USER: ""' in backend and 'DB_JOBS_PASSWORD: ""' in backend  # la API no recibe la cuenta de la conservación
    reference = REPO / "database" / "reference"
    wipe = (reference / "BorrarRap.sql").read_text(encoding="utf-8")
    assert "USE [GlucoLume]" not in wipe and wipe.index("CONFIRMAR_BORRADO") < wipe.index("DELETE FROM")


def test_uvicorn_con_un_unico_valor_de_nginx_ignora_lo_que_manda_el_cliente():
    import asyncio

    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    seen = {}

    async def inner(scope, receive, send):
        seen["ip"] = scope["client"][0]

    middleware = ProxyHeadersMiddleware(inner, trusted_hosts="*")
    # Lo que envía Nginx tras la corrección: un solo valor, la IP real, aunque el cliente haya mandado "9.9.9.9".
    scope = {"type": "http", "client": ("172.18.0.3", 5000), "headers": [(b"x-forwarded-for", b"203.0.113.7")]}
    asyncio.run(middleware(scope, None, None))
    assert seen["ip"] == "203.0.113.7"


# --- Invariantes del contrato de la API -----------------------------------------------------------------------------------------

# Endpoints que no exigen sesión BEARER por diseño: se autentican con un token de un solo uso del correo, con el token del puente serie,
# o son el comienzo del inicio de sesión. Un endpoint nuevo sin sesión debe agregarse acá de forma consciente (y llevar límite por IP).
PUBLIC_OPERATIONS = {
    ("POST", "/api/v1/acquisition/bridge/check"), ("POST", "/api/v1/acquisition/bridge/ingest"),
    ("POST", "/api/v1/auth/account-activation/check"), ("POST", "/api/v1/auth/account-activation/complete"),
    ("POST", "/api/v1/auth/account-deletion/confirm"), ("GET", "/api/v1/auth/google/callback"),
    ("POST", "/api/v1/auth/google/exchange"), ("GET", "/api/v1/auth/google/login"), ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/mfa/recovery/start"), ("POST", "/api/v1/auth/mfa/recovery/verify"),
    ("POST", "/api/v1/auth/mfa/verify"), ("POST", "/api/v1/auth/notifications/new-login/unsubscribe"),
    ("POST", "/api/v1/auth/password/forgot"), ("POST", "/api/v1/auth/password/reset"), ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/register"), ("POST", "/api/v1/auth/sesion-activa/liberar"), ("GET", "/api/v1/auth/verify-email"),
    ("POST", "/api/v1/auth/verify-email/resend"),
    ("POST", "/api/v1/contact"), ("POST", "/api/v1/institutions/result-email/confirm"), ("POST", "/api/v1/platform/activation/with-code"),
    ("POST", "/api/v1/platform/password/forgot"), ("POST", "/api/v1/platform/password/reset"),
}


@pytest.fixture(scope="module")
def spec():
    env = {"API_ENV": "test", "DB_HOST": "x", "DB_NAME": "x", "DB_USER": "x", "DB_PASSWORD": "x", "JWT_SECRET": "t" * 40}
    previous = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    try:
        from app.core.config import getSettings

        getSettings.cache_clear()
        from app.main import app

        yield app.openapi()
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        getSettings.cache_clear()


# Solo se publica en el esquema con API_ENV=development y responde 404 en cualquier otro entorno (auth.googleAuthorizationUrl).
DEVELOPMENT_ONLY = {("GET", "/api/v1/auth/google/authorization-url")}


def test_todo_endpoint_privado_exige_sesion(spec):
    open_ = {(method.upper(), path) for path, ops in spec["paths"].items() for method, op in ops.items() if not op.get("security")}
    open_ -= DEVELOPMENT_ONLY
    assert open_ == PUBLIC_OPERATIONS, {"sobran": open_ - PUBLIC_OPERATIONS, "faltan": PUBLIC_OPERATIONS - open_}


def _schemaRefs(node, found):
    if isinstance(node, dict):
        if "$ref" in node:
            found.add(node["$ref"].rsplit("/", 1)[-1])
        for value in node.values():
            _schemaRefs(value, found)
    elif isinstance(node, list):
        for value in node:
            _schemaRefs(value, found)


def test_ningun_cuerpo_de_peticion_acepta_campos_de_mas(spec):
    """Mass assignment / overposting: todo esquema de entrada rechaza campos desconocidos (extra="forbid")."""
    import importlib
    import pkgutil

    from pydantic import BaseModel

    import app.schemas as schemas

    classes = {}
    for module in pkgutil.iter_modules(schemas.__path__):
        for name, cls in vars(importlib.import_module(f"app.schemas.{module.name}")).items():
            if isinstance(cls, type) and issubclass(cls, BaseModel):
                classes[name] = cls
    requestNames = set()
    for ops in spec["paths"].values():
        for op in ops.values():
            _schemaRefs(op.get("requestBody", {}), requestNames)
    assert len(requestNames) > 50
    permissive = sorted(name for name in requestNames if classes[name].model_config.get("extra") != "forbid")
    assert permissive == [], permissive


def test_ninguna_respuesta_expone_hashes_ni_secretos(spec):
    schemas = spec["components"]["schemas"]
    responseNames = set()
    for ops in spec["paths"].values():
        for op in ops.values():
            for code, response in op.get("responses", {}).items():
                if code.startswith("2"):
                    _schemaRefs(response, responseNames)
    pending, seen = list(responseNames), set(responseNames)
    while pending:
        refs = set()
        _schemaRefs(schemas.get(pending.pop(), {}), refs)
        for ref in refs - seen:
            seen.add(ref)
            pending.append(ref)
    forbidden = re.compile(r"hash|passwordHash|secretoTotp|clienteSecret|bridgeToken|^password$", re.IGNORECASE)
    # Campos que SÍ se devuelven a propósito, una sola vez, al titular: el secreto TOTP del alta de MFA (MfaSetupResponse.secreto), los
    # códigos de recuperación recién generados y los tokens de la sesión recién abierta.
    exposed = {(name, prop) for name in seen for prop in schemas.get(name, {}).get("properties", {}) if forbidden.search(prop)}
    assert exposed == set(), exposed


def test_los_campos_protegidos_no_se_pueden_enviar_por_el_cliente():
    for protected in ("tipoCuenta", "estado", "idUsuario", "rol", "correoElectronico"):
        with pytest.raises(ValidationError):
            UserProfileUpdate(**{protected: "ADMINISTRADOR_PLATAFORMA"})
    with pytest.raises((ValidationError, AuthError)):
        RegisterRequest(nombre="A", apellido="B", correoElectronico="a@example.com", password=PASSWORD,
                        tipoCuenta="ADMINISTRADOR_PLATAFORMA", aceptaPoliticaPrivacidad=True)
