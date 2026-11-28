# Identidad visual de las exportaciones de GlucoLume.
#
# El encabezado institucional es el banner completo (mascota Lumi, logo y eslogan en una sola imagen). Se usa el archivo original del
# proyecto, sin recortes ni versiones nuevas: se escala manteniendo su proporción. Si el archivo no existe, la exportación sale sin banner.

from pathlib import Path

from PIL import Image

ROJO = "#D90820"
ROJO_SUAVE = "#FBEAEC"
GRIS_TEXTO = "#4A4A4F"
GRIS_LINEA = "#E6DADC"
SLOGAN = "Luz que acompaña tu salud"
AVISO_EXPERIMENTAL = "Prototipo experimental. No constituye un diagnóstico médico"

# Mismo archivo que usan los correos (backend/app/emails): es el banner original de GlucoLume.
BANNER_PATH = Path(__file__).resolve().parent.parent / "emails" / "bannerCorreoGlucoLume.jpg"


def existing(path: Path) -> Path | None:
    """Archivo de marca si ya existe; None si no está en el proyecto."""
    return path if path.is_file() else None


def proporcion(path: Path) -> float:
    """Ancho dividido por alto de la imagen, para escalarla sin deformarla."""
    with Image.open(path) as image:
        return image.width / image.height
