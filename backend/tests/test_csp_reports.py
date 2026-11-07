# Monitoreo de incumplimientos de CSP (B-7, auditoría 07/11/2026).
#
# El navegador envía a /api/v1/security/csp-report los bloqueos de la CSP de la app. Estas pruebas cubren:
#  - la sanitización: nada de query, fragmentos, scripts, políticas, referrer ni tokens llega al log;
#  - el endpoint: 204 siempre, tope de tamaño, límite por IP, sin cookies ni sesión;
#  - la plantilla de Nginx: la CSP de la app tiene report-uri y no se debilitó al agregarlo.

import json
import logging
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.rateLimit import resetLimits
from app.main import app
from app.services import cspReports

REPO = Path(__file__).resolve().parents[2]
PLANTILLA = REPO / "docker" / "nginx" / "default.conf.template"

SECRETOS = ("SECRETO123", "CLAVE-ABC", "var clave", "original-policy-marca", "https://referrer.example", "@correo-personal")


def _reporte_clasico(**cambios):
    base = {
        "document-uri": "https://glucolume.example/restablecer-contrasena?token=SECRETO123#CLAVE-ABC",
        "referrer": "https://referrer.example/pagina?email=persona@correo-personal.example",
        "violated-directive": "script-src-elem",
        "effective-directive": "script-src-elem",
        "original-policy": "default-src 'self'; script-src 'self' original-policy-marca",
        "disposition": "enforce",
        "blocked-uri": "https://evil.example/x.js?token=CLAVE-ABC",
        "line-number": 12,
        "column-number": 4,
        "source-file": "https://glucolume.example/assets/index-hL8qm7aU.js?v=SECRETO123",
        "script-sample": "var clave = 'SECRETO123';",
    }
    base.update(cambios)
    return {"csp-report": base}


def _cuerpo(datos) -> bytes:
    return json.dumps(datos).encode("utf-8")


# --- Sanitización ----------------------------------------------------------------------------------------------------------------------


def test_el_reporte_clasico_no_conserva_query_fragmento_ni_datos_sensibles():
    reportes = cspReports.parsear(_cuerpo(_reporte_clasico()), "application/csp-report")
    assert len(reportes) == 1
    salida = json.dumps(reportes, ensure_ascii=False)
    for secreto in SECRETOS:
        assert secreto not in salida, f"se registró {secreto!r}"
    assert "?" not in salida and "#" not in salida
    assert reportes[0] == {
        "directiva": "script-src-elem",
        "bloqueado": "https://evil.example",
        "documento": "/restablecer-contrasena",
        "fuente": "https://glucolume.example/assets/index-hL8qm7aU.js",
        "linea": 12,
        "columna": 4,
        "disposicion": "enforce",
    }


def test_el_formato_de_reporting_api_se_normaliza_igual():
    cuerpo = _cuerpo([{"type": "csp-violation", "body": {
        "documentURL": "https://glucolume.example/app/mediciones/3f2a9c1e-7b4d-4e8a-9c2f-1a2b3c4d5e6f?x=1",
        "blockedURL": "inline", "effectiveDirective": "style-src-attr", "disposition": "report", "lineNumber": 5,
    }}, {"type": "otra-cosa", "body": {"blockedURL": "https://no-debe-aparecer.example"}}])
    reportes = cspReports.parsear(cuerpo, "application/reports+json")
    assert reportes == [{"directiva": "style-src-attr", "bloqueado": "inline", "documento": "/app/mediciones/:id",
                         "fuente": "desconocida", "linea": 5, "columna": None, "disposicion": "report"}]


@pytest.mark.parametrize("cuerpo,tipo", [
    (b"{no es json", "application/csp-report"),
    (b"[1,2]", "application/csp-report"),
    (_cuerpo(_reporte_clasico()), "text/plain"),
    (_cuerpo({"csp-report": "no es un objeto"}), "application/csp-report"),
    (b"x" * (cspReports.MAX_BODY_BYTES + 1), "application/csp-report"),
])
def test_un_cuerpo_invalido_o_demasiado_grande_no_produce_reportes(cuerpo, tipo):
    assert cspReports.parsear(cuerpo, tipo) == []


@pytest.mark.parametrize("url,esperado", [
    ("https://Evil.Example:8443/x?token=1", "https://evil.example"),
    ("https://usuario:clave@host.example/p", "https://host.example"),
    ("data:image/png;base64,AAAA", "data"),
    ("chrome-extension://abcdef/popup.js", "chrome-extension"),
    ("inline", "inline"),
    ("", "desconocido"),
    ("https://[no-cerrado", "desconocido"),
])
def test_el_origen_del_recurso_bloqueado_es_solo_esquema_y_host(url, esperado):
    assert cspReports._origen(url) == esperado


@pytest.mark.parametrize("segmento,esperado", [
    ("restablecer-contrasena", "restablecer-contrasena"),
    ("3f2a9c1e-7b4d-4e8a-9c2f-1a2b3c4d5e6f", ":id"),
    ("tok3nLargoConDigitos99", ":id"),
    ("persona@correo.example", ":x"),
    ("a+b/c=", ":x"),
])
def test_los_segmentos_con_aspecto_de_id_o_token_se_reemplazan(segmento, esperado):
    assert cspReports._segmento(segmento) == esperado


def test_los_caracteres_de_control_no_inyectan_lineas_en_el_log():
    assert "\n" not in cspReports._texto("linea\nfalsa\r\x1b[31m")


# --- Endpoint ----------------------------------------------------------------------------------------------------------------------------


@pytest.fixture
def cliente():
    resetLimits()
    yield TestClient(app, raise_server_exceptions=False, client=("203.0.113.70", 50000))
    resetLimits()


def test_el_endpoint_responde_204_registra_lo_sanitizado_y_no_guarda_secretos(cliente, caplog):
    caplog.set_level(logging.WARNING, logger="glucolume.csp")
    r = cliente.post("/api/v1/security/csp-report", content=_cuerpo(_reporte_clasico()),
                     headers={"Content-Type": "application/csp-report"})
    assert r.status_code == 204 and r.content == b""
    assert r.headers["cache-control"] == "no-store"
    lineas = [rec.getMessage() for rec in caplog.records if rec.name == "glucolume.csp"]
    assert len(lineas) == 1 and "directiva=script-src-elem" in lineas[0] and "documento=/restablecer-contrasena" in lineas[0]
    for secreto in SECRETOS:
        assert secreto not in lineas[0]


def test_el_endpoint_responde_204_aunque_el_reporte_sea_basura(cliente, caplog):
    caplog.set_level(logging.WARNING, logger="glucolume.csp")
    r = cliente.post("/api/v1/security/csp-report", content=b"{{{", headers={"Content-Type": "application/csp-report"})
    assert r.status_code == 204
    assert not [rec for rec in caplog.records if rec.name == "glucolume.csp"]


def test_un_cuerpo_de_mas_de_8_kb_responde_204_sin_registrar_nada(cliente, caplog):
    caplog.set_level(logging.WARNING, logger="glucolume.csp")
    grande = _cuerpo(_reporte_clasico(**{"script-sample": "x" * 20000}))
    r = cliente.post("/api/v1/security/csp-report", content=grande, headers={"Content-Type": "application/csp-report"})
    assert r.status_code == 204
    assert not [rec for rec in caplog.records if rec.name == "glucolume.csp"]


def test_el_endpoint_solo_acepta_post(cliente):
    assert cliente.get("/api/v1/security/csp-report").status_code == 405


def test_el_limite_por_ip_corta_las_rafagas_de_reportes(cliente):
    cuerpo = _cuerpo(_reporte_clasico())
    codigos = [cliente.post("/api/v1/security/csp-report", content=cuerpo,
                            headers={"Content-Type": "application/csp-report"}).status_code for _ in range(31)]
    assert codigos[:30] == [204] * 30
    assert codigos[30] == 429


# --- Plantilla de Nginx --------------------------------------------------------------------------------------------------------------------


def _csp_de_la_app() -> str:
    conf = PLANTILLA.read_text(encoding="utf-8")
    return re.search(r'map \$request_uri \$csp_value \{.*?default "([^"]+)";', conf, re.S).group(1)


def test_la_csp_de_la_app_tiene_report_uri_y_ninguna_directiva_nueva_ni_mas_laxa():
    directivas = {d.strip() for d in _csp_de_la_app().split(";") if d.strip()}
    assert "report-uri /api/v1/security/csp-report" in directivas
    assert directivas == {
        "default-src 'self'", "img-src 'self' data:", "style-src 'self'", "script-src 'self'", "connect-src 'self'",
        "frame-ancestors 'none'", "base-uri 'self'", "form-action 'self'", "object-src 'none'",
        "report-uri /api/v1/security/csp-report",
    }, "la CSP de la app cambió más de lo que corresponde a B-7: revisar antes de aceptar"


def test_el_endpoint_de_reportes_tiene_su_propio_tope_de_8_kb_y_proxy_a_la_api():
    conf = PLANTILLA.read_text(encoding="utf-8")
    bloque = re.search(r"location = /api/v1/security/csp-report \{(.*?)\n    \}", conf, re.S).group(1)
    assert "client_max_body_size 8k;" in bloque and "proxy_pass http://$backend;" in bloque
    assert "proxy_hide_header Content-Security-Policy;" in bloque  # una sola CSP por respuesta (B-3)
