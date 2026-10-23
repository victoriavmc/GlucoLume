# BaseImageVersions - Qué versiones de paquetes trae una imagen base publicada (evidencia reproducible para H-10)
#
# Lee el registro de Docker Hub (solo lectura, sin ejecutar nada de la imagen) y extrae /var/lib/dpkg/status de sus capas para informar la versión
# EXACTA de los paquetes pedidos. Sirve para comprobar, sin Docker, si una imagen oficial ya incluye una corrección (p. ej. de zlib1g) antes de
# cambiar el digest fijado en backend/Dockerfile. NO consulta bases de CVE: que una versión corrija una CVE se confirma en el rastreador de
# seguridad de Debian (https://security-tracker.debian.org/tracker/<CVE>) o con un escáner sobre la imagen que se despliega.
#
#     python docker/tools/baseImageVersions.py                                  # imagen fijada en el Dockerfile y la última de la rama
#     python docker/tools/baseImageVersions.py library/python 3.14-slim-trixie zlib1g libssl3t64
#
# Descarga ~45 MB por imagen (capas comprimidas) y respeta el límite anónimo de Docker Hub. Los datos descargados se tratan como NO confiables:
# solo se leen dos archivos de texto de las capas y no se ejecuta nada.

import io
import json
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

DEFAULT_PACKAGES = ("zlib1g", "libssl3t64", "libc6", "libsqlite3-0", "perl-base", "dpkg")
INDEX_TYPES = ("application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json,"
               "application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json")
STATUS_PATH = "var/lib/dpkg/status"


def parseStatus(text: str, packages: tuple[str, ...]) -> dict[str, str]:
    """Versión instalada de cada paquete pedido, a partir del texto de /var/lib/dpkg/status (el último bloque de un paquete manda)."""
    found: dict[str, str] = {}
    for block in text.split("\n\n"):
        name = re.search(r"^Package: (\S+)$", block, re.M)
        version = re.search(r"^Version: (\S+)$", block, re.M)
        installed = re.search(r"^Status: .* installed$", block, re.M)
        if name and version and installed and name.group(1) in packages:
            found[name.group(1)] = version.group(1)
    return found


def pinnedReference(dockerfile: Path) -> str:
    """El digest fijado en `ARG PYTHON_IMAGE=python:<tag>@sha256:<digest>` de backend/Dockerfile."""
    match = re.search(r"^ARG PYTHON_IMAGE=python:[\w.\-]+@(sha256:[0-9a-f]{64})", dockerfile.read_text(encoding="utf-8"), re.M)
    if not match:
        raise SystemExit("No se encontró ARG PYTHON_IMAGE con digest en el Dockerfile.")
    return match.group(1)


def _get(url: str, token: str, accept: str = INDEX_TYPES):
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": accept})
    return urllib.request.urlopen(request, timeout=120)  # noqa: S310 - URL https fija del registro


def installedVersions(repository: str, reference: str, packages: tuple[str, ...]) -> dict:
    token = json.load(urllib.request.urlopen(  # noqa: S310
        f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repository}:pull", timeout=60))["token"]
    base = f"https://registry-1.docker.io/v2/{repository}"
    manifest = json.load(_get(f"{base}/manifests/{reference}", token))
    annotations = {}
    if "manifests" in manifest:
        chosen = next(m for m in manifest["manifests"]
                      if m.get("platform", {}).get("architecture") == "amd64" and m.get("platform", {}).get("os") == "linux")
        annotations = chosen.get("annotations", {})
        manifest = json.load(_get(f"{base}/manifests/{chosen['digest']}", token))
    status = ""
    for layer in manifest["layers"]:  # la última capa que trae el archivo es la vigente
        with tarfile.open(fileobj=io.BytesIO(_get(f"{base}/blobs/{layer['digest']}", token).read()), mode="r:*") as tar:
            for member in tar:
                if member.isfile() and member.name.lstrip("./") == STATUS_PATH:
                    status = tar.extractfile(member).read().decode("utf-8", errors="replace")
    return {"imagen": f"{repository}@{reference}", "version": annotations.get("org.opencontainers.image.version"),
            "creada": annotations.get("org.opencontainers.image.created"), "paquetes": parseStatus(status, packages)}


def main(argv: list[str]) -> int:
    if argv:
        repository, reference, *packages = argv
        targets = [(repository, reference)]
        wanted = tuple(packages) or DEFAULT_PACKAGES
    else:
        dockerfile = Path(__file__).resolve().parents[2] / "backend" / "Dockerfile"
        targets = [("library/python", pinnedReference(dockerfile)), ("library/python", "3.14-slim-trixie")]
        wanted = DEFAULT_PACKAGES
    for repository, reference in targets:
        print(json.dumps(installedVersions(repository, reference, wanted), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
