# Reportes de incumplimiento de Content-Security-Policy (B-7, auditoría 07/11/2026).
#
# El navegador envía un reporte cuando la CSP bloquea algo (report-uri en docker/nginx/default.conf.template). Este módulo lo convierte en
# una línea de log con solo lo necesario para corregir la política:
#   directiva que bloqueó, origen del recurso bloqueado (esquema y host), ruta de la pantalla (sin query), archivo y línea de origen.
#
# Nunca se registra: query ni fragmento de las URL (ahí van tokens de un solo uso: ?token=...), credenciales en la URL, la IP, el
# user-agent, el referrer, la política completa, ni el fragmento del script (script-sample). Los segmentos de ruta con aspecto de ID,
# token o correo se reemplazan (:id / :x). Los valores se limpian de caracteres de control para que no inyecten líneas en el log.

import json
import logging
import re
from urllib.parse import urlsplit

logger = logging.getLogger("glucolume.csp")

MAX_BODY_BYTES = 8 * 1024
CONTENT_TYPES_LEGACY = ("application/csp-report", "application/json")
CONTENT_TYPE_REPORTING = "application/reports+json"

# Palabras clave de la CSP que el navegador puede informar como origen bloqueado (no son URL).
PALABRAS_CLAVE = {"inline", "eval", "self", "data", "blob", "wasm-eval"}
ESQUEMAS_DE_RED = {"http", "https", "ws", "wss"}

_DIRECTIVA = re.compile(r"[a-z-]{1,40}")
_SEGMENTO_LEGIBLE = re.compile(r"[A-Za-z0-9._-]{1,40}")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _texto(valor, largo: int = 120) -> str:
    if not isinstance(valor, str):
        return ""
    return _CONTROL.sub("?", valor)[:largo]


def _segmento(segmento: str) -> str:
    """Un segmento de ruta tal como lo mostraría la app, o un marcador si parece un identificador, un token o un correo."""
    if not _SEGMENTO_LEGIBLE.fullmatch(segmento):
        return ":x"  # p. ej. un correo (lleva @) o un token con caracteres base64
    if "." in segmento:
        return segmento  # nombre de archivo (p. ej. el asset con hash de /assets/): público y útil para diagnosticar
    if len(segmento) >= 32 or (len(segmento) >= 16 and re.search(r"\d", segmento)):
        return ":id"  # UUID, id numérico largo o token: no sirve para diagnosticar y puede ser dato personal
    return segmento


def _ruta(url: str, maximo_segmentos: int) -> str:
    """Solo la ruta, sin esquema, host, query ni fragmento, con los segmentos limpios."""
    try:
        ruta = urlsplit(url).path
    except ValueError:
        return "/"
    partes = [s for s in ruta.split("/") if s][:maximo_segmentos]
    return "/" + "/".join(_segmento(s) for s in partes)


def _origen(url: str) -> str:
    """Un recurso bloqueado: su esquema y host (sin ruta, query ni credenciales), o el esquema si no es de red (extensiones, data:)."""
    if not url:
        return "desconocido"
    if url in PALABRAS_CLAVE:
        return url
    try:
        partes = urlsplit(url)
    except ValueError:
        return "desconocido"
    esquema = (partes.scheme or "").lower()
    if esquema in ESQUEMAS_DE_RED and partes.hostname:
        return f"{esquema}://{partes.hostname.lower()}"
    return esquema or "desconocido"


def _fuente(url: str) -> str:
    """El archivo que contiene el script infractor: origen y ruta (sin query), o solo el esquema si no es de red."""
    url = _texto(url, 500)
    if not url:
        return "desconocida"
    origen = _origen(url)
    if origen.startswith(tuple(f"{e}://" for e in ESQUEMAS_DE_RED)):
        return origen + _ruta(url, 3)
    return origen


def _directiva(valor: str) -> str:
    valor = _texto(valor, 40)
    return valor if _DIRECTIVA.fullmatch(valor) else "desconocida"


def _numero(valor):
    return valor if isinstance(valor, int) and not isinstance(valor, bool) and 0 <= valor <= 10_000_000 else None


def _normalizar(reporte: dict) -> dict | None:
    """Acepta el formato clásico (csp-report, con guiones) y el de Reporting API (camelCase)."""
    if not isinstance(reporte, dict):
        return None
    documento = reporte.get("document-uri") or reporte.get("documentURL")
    bloqueado = reporte.get("blocked-uri") or reporte.get("blockedURL")
    directiva = reporte.get("effective-directive") or reporte.get("effectiveDirective") or reporte.get("violated-directive") \
        or reporte.get("violatedDirective")
    origen = reporte.get("source-file") or reporte.get("sourceFile")
    disposicion = reporte.get("disposition")
    return {
        "directiva": _directiva(directiva),
        "bloqueado": _origen(_texto(bloqueado, 500)),
        "documento": _ruta(_texto(documento, 500), 3) if documento else "desconocido",
        "fuente": _fuente(origen),
        "linea": _numero(reporte.get("line-number", reporte.get("lineNumber"))),
        "columna": _numero(reporte.get("column-number", reporte.get("columnNumber"))),
        "disposicion": disposicion if disposicion in ("enforce", "report") else "desconocida",
    }


def parsear(cuerpo: bytes, tipo_de_contenido: str) -> list[dict]:
    """Los reportes válidos del cuerpo, ya sanitizados. Un cuerpo inválido no produce nada y no devuelve error al navegador."""
    if len(cuerpo) > MAX_BODY_BYTES:
        return []
    try:
        datos = json.loads(cuerpo)
    except (ValueError, UnicodeDecodeError):
        return []
    if tipo_de_contenido == CONTENT_TYPE_REPORTING and isinstance(datos, list):
        reportes = [d.get("body") for d in datos if isinstance(d, dict) and d.get("type") == "csp-violation"]
    elif tipo_de_contenido in CONTENT_TYPES_LEGACY and isinstance(datos, dict):
        reportes = [datos.get("csp-report")]
    else:
        reportes = []
    return [n for n in (_normalizar(r) for r in reportes) if n]


def registrar(reportes: list[dict]) -> None:
    for r in reportes:
        logger.warning(
            "CSP incumplida: directiva=%s bloqueado=%s documento=%s fuente=%s linea=%s columna=%s disposicion=%s",
            r["directiva"], r["bloqueado"], r["documento"], r["fuente"], r["linea"], r["columna"], r["disposicion"],
        )
