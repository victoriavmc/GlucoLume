# Aislamiento entre orígenes (B-5, auditoría 07/11/2026): COOP y CORP en la SPA y los estáticos, no en la API.
#
# Reglas que cubren estas pruebas:
#  - COOP y CORP con valor same-origin en las respuestas de la SPA y de los estáticos (mapas $coop_value y $corp_value);
#  - ninguna en /api/: sus respuestas JSON y sus redirecciones (p. ej. el callback de Google) no son documentos de navegación;
#  - las ubicaciones que sirven la SPA y los estáticos NO declaran add_header propio (un add_header en la ubicación anularía las del
#    server, igual que pasó con B-3);
#  - COEP no se activa: exige revisar dependencias (recursos de terceros, popups) antes; ver la guía de auditoría.

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLANTILLA = REPO / "docker" / "nginx" / "default.conf.template"


def _conf() -> str:
    return PLANTILLA.read_text(encoding="utf-8")


def _mapa(nombre: str) -> dict:
    """Pares patrón -> valor de un map de Nginx sobre $request_uri."""
    bloque = re.search(r"map \$request_uri \$%s \{(.*?)\n\}" % nombre, _conf(), re.S).group(1)
    return dict(re.findall(r'"([^"]*)" "([^"]*)";', bloque) + [("default", m) for m in re.findall(r'default "([^"]*)";', bloque)])


def _ubicacion(cabecera: str) -> str:
    """Texto de un bloque location del nivel de server (indentación de 4 espacios). La cabecera va sin la llave."""
    m = re.search(re.escape(cabecera) + r"\s*\{(.*?)\n    \}", _conf(), re.S)
    assert m, f"no se encontró {cabecera}"
    return m.group(1)


def test_coop_y_corp_son_same_origin_fuera_de_la_api():
    for nombre, cabecera in (("coop_value", "Cross-Origin-Opener-Policy"), ("corp_value", "Cross-Origin-Resource-Policy")):
        mapa = _mapa(nombre)
        assert mapa["default"] == "same-origin", f"{cabecera}: el valor por defecto debe ser same-origin"
        assert _conf().count(f"add_header {cabecera} ${nombre} always;") == 1, f"{cabecera} debe declararse una sola vez, en el server"


def test_la_api_no_recibe_coop_ni_corp():
    for nombre in ("coop_value", "corp_value"):
        patron = next(p for p in _mapa(nombre) if p != "default")  # sin el prefijo ~ de Nginx
        regla = re.compile(patron.removeprefix("~"))
        assert regla.search("/api"), f"{nombre} debe excluir /api"
        assert regla.search("/api/v1/auth/google/callback")
        assert regla.search("/api?x=1")
        assert not regla.search("/apix"), "el patrón no debe capturar rutas que solo empiezan igual"
        assert not regla.search("/login")
        assert not regla.search("/assets/index.js")


def test_las_ubicaciones_de_la_spa_y_los_estaticos_heredan_las_cabeceras_del_server():
    for cabecera in ("location /assets/", "location = /index.html", "location = /ayuda", "location = /ayuda/",
                     "location ^~ /ayuda/", "location /"):
        directivas = [l.strip() for l in _ubicacion(cabecera).splitlines() if l.strip() and not l.strip().startswith("#")]
        assert not any(d.startswith("add_header") for d in directivas), f"{cabecera} declara add_header propio y perdería COOP/CORP"


def test_no_se_activa_coep_sin_analizar_dependencias():
    assert "Cross-Origin-Embedder-Policy" not in _conf()
