# Rutas de la SPA en Nginx (B-2, auditoría 07/11/2026).
#
# Antes, cualquier ruta que no fuera archivo devolvía la shell de React con 200: /nonexistent-xyz, /phpinfo.php y /.git/config
# «existían». Ahora Nginx solo sirve la shell para las rutas que declara el router, y responde 404 al resto, incluidos los archivos
# sensibles. La lista de rutas la GENERA frontend/scripts/generar-rutas-spa.mjs desde src/App.jsx (fuente única); su copia versionada
# docker/nginx/rutas-spa.generado.conf es la que leen estas pruebas, y una prueba de frontend verifica que no esté desactualizada.
#
# Estas pruebas no levantan Nginx: comparan el mapa con el router, con los enlaces que genera el backend (FRONTEND_ROUTES en
# services/email.py) y con las reglas de archivos sensibles de la plantilla. El comportamiento medido en un Nginx real está en
# docs/auditorias/evidencias/auditoria_seguridad_2026-11-07/sondas_rutas_spa.sh.

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PLANTILLA = REPO / "docker" / "nginx" / "default.conf.template"
MAPA_RUTAS = REPO / "docker" / "nginx" / "rutas-spa.generado.conf"
APP_JSX = REPO / "frontend" / "src" / "App.jsx"
EMAIL_PY = REPO / "backend" / "app" / "services" / "email.py"

# Enlace de correo que el router solo redirige (no tiene pantalla propia). Se declara como <Navigate> en App.jsx y la prueba exige que
# siga siendo una redirección: si alguien le da una pantalla, o si aparece otro enlace así, hay que actualizar esta lista a propósito.
ENLACES_DE_CORREO_SOLO_REDIRECCION = {"/cuenta/notificaciones/desuscribir"}


def _texto(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8")


def _patrones_de_mapa_publica() -> list[re.Pattern]:
    """Los patrones `~* ... 1;` del mapa generado $ruta_spa, compilados sin distinguir mayúsculas (como ~* de Nginx)."""
    patrones = []
    for linea in _texto(MAPA_RUTAS).splitlines():
        linea = linea.strip()
        if linea.startswith("~*") and " 1;" in linea:
            patrones.append(re.compile(linea[2:linea.index(" 1;")], re.IGNORECASE))
    assert patrones, "no se encontró el mapa $ruta_spa generado"
    return patrones


def _ruta_spa_valida(ruta: str) -> bool:
    return any(p.search(ruta) for p in _patrones_de_mapa_publica())


def _reglas_que_responden_404() -> list[re.Pattern]:
    """Las ubicaciones `location ~ ...` o `location ~* ...` que devuelven 404 (archivos sensibles y control de versiones)."""
    conf = _texto(PLANTILLA)
    reglas = []
    for modo, patron in re.findall(r"location (~\*?) (\S+) \{\s*return 404;", conf):
        flags = re.IGNORECASE if modo == "~*" else 0
        reglas.append(re.compile(patron, flags))
    assert len(reglas) >= 2, "faltan las reglas de archivos sensibles"
    return reglas


def _sensible(ruta: str) -> bool:
    return any(r.search(ruta) for r in _reglas_que_responden_404())


def _rutas_de_app_jsx() -> list[str]:
    """Rutas de primer nivel con barra inicial. Las anidadas son relativas (sin barra) y van cubiertas por /app y /plataforma."""
    return sorted(set(re.findall(r'<Route\s+path="(/[^"*]*)"', _texto(APP_JSX), re.S)))


def _rutas_de_correo() -> set[str]:
    bloque = re.search(r"FRONTEND_ROUTES = \{(.*?)\n\}", _texto(EMAIL_PY), re.S).group(1)
    return set(re.findall(r'"(/[^"]*)"', bloque))


def test_toda_ruta_publica_de_la_spa_sirve_la_shell():
    rutas = _rutas_de_app_jsx()
    assert "/login" in rutas and "/consejos/:idConsejo" in rutas  # la lectura de App.jsx encontró lo esperado
    for ruta in rutas:
        ejemplo = re.sub(r":\w+", "ejemplo", ruta)
        assert _ruta_spa_valida(ejemplo), f"{ruta} está en App.jsx pero Nginx la respondería 404"


@pytest.mark.parametrize("ruta", [
    "/", "/LOGIN", "/login/", "/registro", "/caracteristicas", "/ayuda", "/consejos", "/consejos/abc-123",
    "/auth/google/callback", "/cuenta/eliminar/confirmar", "/administracion/activar", "/administracion/login",
    "/plataforma/login", "/plataforma/dashboard", "/app", "/app/", "/app/inicio", "/app/mediciones/abc", "/APP/inicio",
])
def test_rutas_validas_pasan_al_index_de_la_spa(ruta):
    assert _ruta_spa_valida(ruta)


@pytest.mark.parametrize("ruta", [
    "/nonexistent-xyz", "/administracion/xyz", "/cuenta", "/cuenta/otra", "/login/extra", "/consejos/a/b",
    "/plataformax", "/appx", "/wp-admin/", "/gallery.html", "/index.php",
])
def test_rutas_desconocidas_no_pasan_al_index(ruta):
    assert not _ruta_spa_valida(ruta)


@pytest.mark.parametrize("ruta", [
    "/phpinfo.php", "/.git/config", "/app/.git/config", "/.env", "/.htaccess", "/config.php.bak", "/backup.sql",
    "/archivo.zip", "/admin.aspx", "/cgi-bin/x.cgi", "/a/.svn/entries", "/logs/app.log",
])
def test_archivos_sensibles_responden_404(ruta):
    # Aunque la ruta empiece por /app (sección privada, que el mapa deja pasar), la regla de punto/extensión corre antes y la corta.
    assert _sensible(ruta)


def test_la_api_no_la_alcanzan_las_reglas_de_archivos_sensibles():
    for ruta in ("/api/v1/healthz", "/api/v1/auth/login", "/api/v1/contact", "/api/v1/archivo.log"):
        assert not _sensible(ruta), f"{ruta} no debe caer en las reglas de la SPA"


def test_los_enlaces_de_correo_son_rutas_de_la_spa_y_los_conocidos_solo_redirigen():
    for ruta in _rutas_de_correo():
        assert _ruta_spa_valida(ruta), f"el correo apunta a {ruta} y Nginx la respondería 404"
    texto_app = _texto(APP_JSX)
    for ruta in ENLACES_DE_CORREO_SOLO_REDIRECCION:
        assert re.search(r'path="' + re.escape(ruta) + r'" element=\{<Navigate', texto_app), (
            f"{ruta} debe seguir siendo una redirección declarada en App.jsx (no tiene pantalla propia)")


def test_ningun_correo_apunta_a_la_ruta_inexistente_cuenta_seguridad():
    """El enlace de seguridad de los correos era /cuenta/seguridad (no existe). Ahora va a /app/seguridad o /plataforma/seguridad según la
    cuenta. Solo los correos ya enviados antes del cambio lo siguen usando, y ese enlace redirige a /app/seguridad."""
    assert "/cuenta/seguridad" not in _rutas_de_correo()
    assert {"/app/seguridad", "/plataforma/seguridad"} <= _rutas_de_correo()


def test_el_mapa_de_noindex_no_distingue_mayusculas():
    """Las rutas privadas se marcan noindex también con mayúsculas (React Router tampoco distingue)."""
    conf = _texto(PLANTILLA)
    bloque = re.search(r"map \$request_uri \$robots_tag \{(.*?)\n\}", conf, re.S).group(1)
    assert re.search(r"~\*\^/\(app\|plataforma", bloque), "el mapa de noindex debe usar ~* (sin distinguir mayúsculas)"
    patron = re.compile(re.search(r"~\*(\^/\(app[^ ]*)\s+\"noindex", bloque).group(1), re.IGNORECASE)
    assert patron.search("/APP/inicio") and patron.search("/Plataforma/login")
