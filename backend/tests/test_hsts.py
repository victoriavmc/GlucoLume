# HSTS (B-4, auditoría 07/11/2026): valor, alcance y hosts excluidos.
#
# Criterio: HSTS es por host (no por puerto) y dura lo que indique max-age. Por eso:
#  - no se emite para localhost ni IPs de loopback (un HSTS allí forzaría http://localhost:5173 a HTTPS);
#  - no lleva includeSubDomains (afectaría a todos los subdominios del dominio, y el del demo es de Tailscale);
#  - el max-age es de 30 días, no de un año, para que un error de HTTPS se pueda deshacer en un mes.
# Las pruebas leen la regla real de la plantilla de Nginx y el valor del backend; no fijan una copia.

import re
from pathlib import Path

import pytest

from app.api.securityHeaders import HSTS_VALUE

REPO = Path(__file__).resolve().parents[2]
PLANTILLA = REPO / "docker" / "nginx" / "default.conf.template"


def _linea_hsts_de_nginx() -> tuple[re.Pattern, str]:
    conf = PLANTILLA.read_text(encoding="utf-8")
    bloque = re.search(r"map \"\$fwd_proto:\$host\" \$hsts_value \{(.*?)\n\}", conf, re.S).group(1)
    regla = re.search(r'"~(\^https:[^"]+)" "([^"]+)";', bloque)
    assert regla, "no se encontró la regla de HSTS en la plantilla"
    return re.compile(regla.group(1)), regla.group(2)


@pytest.mark.parametrize("host", ["glucolume-server.tailb27487.ts.net", "app.midominio.example", "localhost.example.com"])
def test_hsts_se_emite_para_hosts_publicos_por_https(host):
    patron, _ = _linea_hsts_de_nginx()
    assert patron.search(f"https:{host}")


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
def test_hsts_no_se_emite_para_hosts_locales_aunque_llegue_https(host):
    patron, _ = _linea_hsts_de_nginx()
    assert not patron.search(f"https:{host}")


@pytest.mark.parametrize("host", ["glucolume-server.tailb27487.ts.net", "localhost"])
def test_hsts_nunca_se_emite_por_http(host):
    patron, _ = _linea_hsts_de_nginx()
    assert not patron.search(f"http:{host}")


def test_el_valor_de_nginx_y_del_backend_coinciden_y_no_incluyen_subdominios():
    _, valor_nginx = _linea_hsts_de_nginx()
    assert valor_nginx == HSTS_VALUE
    assert "includeSubDomains" not in valor_nginx and "preload" not in valor_nginx


def test_el_max_age_es_de_30_dias_y_no_de_un_ano():
    assert HSTS_VALUE == "max-age=2592000"
