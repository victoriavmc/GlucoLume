# Guarda de zlib del Dockerfile y herramienta de evidencia de la imagen base (H-10). Sin red y sin Docker: se ejecuta el MISMO fragmento de shell del
# Dockerfile con el dpkg del equipo de pruebas (si no hay dpkg, esas pruebas se omiten) y se prueba el analizador con un archivo de estado sintético.

import importlib.util
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")


def loadTool():
    spec = importlib.util.spec_from_file_location("baseImageVersions", ROOT / "docker" / "tools" / "baseImageVersions.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def guardScript() -> str:
    block = re.search(r"^RUN (if \[ -n \"\$ZLIB_MIN_VERSION\" \].*?\n    fi)$", DOCKERFILE, re.M | re.S)
    assert block, "falta la guarda de zlib en backend/Dockerfile"
    return block.group(1).replace("\\\n", " ")


def test_la_guarda_de_zlib_es_opcional_y_no_cambia_el_build_por_defecto():
    assert re.search(r"^ARG ZLIB_MIN_VERSION=$", DOCKERFILE, re.M)  # vacío: la guarda no hace nada
    assert DOCKERFILE.index("ARG ZLIB_MIN_VERSION") > DOCKERFILE.index("apt-get upgrade")  # se evalúa DESPUÉS de actualizar los paquetes


@pytest.mark.skipif(shutil.which("dpkg") is None or shutil.which("dpkg-query") is None, reason="dpkg no está instalado")
def test_la_guarda_falla_si_zlib1g_es_anterior_a_la_version_exigida_y_pasa_si_no():
    installed = subprocess.run(["dpkg-query", "-W", "-f=${Version}", "zlib1g"], capture_output=True, text=True).stdout
    if not installed:
        pytest.skip("zlib1g no está instalado en este equipo")

    def run(minimum: str):
        return subprocess.run(["bash", "-c", guardScript()], env={"ZLIB_MIN_VERSION": minimum, "PATH": "/usr/bin:/bin"}, capture_output=True, text=True)

    assert run("").returncode == 0  # sin versión exigida: no hace nada
    assert run(installed).returncode == 0  # igual a la instalada: pasa
    assert run("0").returncode == 0
    failed = run("99:9.9.9-1")
    assert failed.returncode == 1 and "anterior a 99:9.9.9-1" in failed.stderr
    # El caso real de H-10: un rebuild (+b1) NO equivale a la corrección de seguridad (+deb13u1).
    assert subprocess.run(["dpkg", "--compare-versions", "1:1.3.dfsg+really1.3.1-1+b1", "ge", "1:1.3.dfsg+really1.3.1-1+deb13u1"]).returncode != 0


def test_el_analizador_lee_la_version_instalada_y_la_herramienta_toma_el_digest_del_dockerfile():
    tool = loadTool()
    status = ("Package: zlib1g\nStatus: install ok installed\nVersion: 1:1.3.dfsg+really1.3.1-1+b1\nArchitecture: amd64\n\n"
              "Package: libssl3t64\nStatus: install ok installed\nVersion: 3.5.7-1~deb13u3\n\n"
              "Package: perl-base\nStatus: deinstall ok config-files\nVersion: 5.40.1-6\n\n"
              "Package: otro\nStatus: install ok installed\nVersion: 1\n")
    assert tool.parseStatus(status, ("zlib1g", "libssl3t64", "perl-base")) == {"zlib1g": "1:1.3.dfsg+really1.3.1-1+b1", "libssl3t64": "3.5.7-1~deb13u3"}
    pinned = tool.pinnedReference(ROOT / "backend" / "Dockerfile")
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", pinned) and pinned in DOCKERFILE
