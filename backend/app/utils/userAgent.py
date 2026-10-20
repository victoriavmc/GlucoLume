# UserAgent - Descripción legible del cliente (navegador, sistema operativo, dispositivo)
#
# Detección aproximada por patrones del encabezado User-Agent, sin dependencias externas. Solo se usa
# para informar al usuario (aviso de nuevo inicio de sesión), nunca para decisiones de seguridad.

import re
from dataclasses import dataclass

# Orden relevante: Edge y Opera también contienen "Chrome"; Chrome contiene "Safari".
_BROWSERS = (
    (r"Edg(?:e|A|iOS)?/", "Microsoft Edge"),
    (r"OPR/|Opera", "Opera"),
    (r"SamsungBrowser/", "Samsung Internet"),
    (r"Firefox/|FxiOS/", "Firefox"),
    (r"Chrome/|CriOS/", "Chrome"),
    (r"Safari/", "Safari"),
)
_SYSTEMS = (
    (r"Windows NT", "Windows"),
    (r"Android", "Android"),
    (r"iPhone|iPad|iPod", "iOS"),
    (r"Mac OS X|Macintosh", "macOS"),
    (r"CrOS", "ChromeOS"),
    (r"Linux", "Linux"),
)


@dataclass(frozen=True)
class ClientInfo:
    navegador: str | None = None
    sistemaOperativo: str | None = None
    dispositivo: str | None = None
    ip: str | None = None


def _match(patterns, userAgent: str) -> str | None:
    return next((name for pattern, name in patterns if re.search(pattern, userAgent)), None)


def describeClient(userAgent: str | None, ip: str | None = None) -> ClientInfo:
    if not userAgent:
        return ClientInfo(ip=ip)
    if re.search(r"iPad|Tablet", userAgent):
        device = "Tablet"
    elif re.search(r"Mobi|iPhone|Android", userAgent):
        device = "Celular"
    else:
        device = "Computadora"
    return ClientInfo(
        navegador=_match(_BROWSERS, userAgent),
        sistemaOperativo=_match(_SYSTEMS, userAgent),
        dispositivo=device,
        ip=ip,
    )
