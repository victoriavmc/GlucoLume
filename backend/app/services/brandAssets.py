# Identidad visual de las exportaciones de GlucoLume.
#
# - La gota de marca tiene las mismas formas que el logo de la app (frontend/src/components/Logo.jsx y favicon.svg). En el PDF se dibuja
#   con vectores; en el Excel se genera un PNG pequeño con esa misma forma.
# - Lumi (mascota) y el logo oficial se incrustan SOLO si existen en app/assets/brand/ (lumi.png, logo.png). No se inventa su diseño:
#   mientras no estén los archivos oficiales, la exportación sale sin ellos.

import io
import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw

ROJO = "#D90820"
ROJO_SUAVE = "#FBEAEC"
GRIS_TEXTO = "#4A4A4F"
GRIS_LINEA = "#E6DADC"
SLOGAN = "Luz que acompaña tu salud"
AVISO_EXPERIMENTAL = "Prototipo experimental. No constituye un diagnóstico médico"

_ASSETS = Path(__file__).resolve().parent.parent / "assets" / "brand"
LUMI_PATH = _ASSETS / "lumi.png"
LOGO_PATH = _ASSETS / "logo.png"

# Gota en el sistema del SVG (viewBox 0 0 32 32, y hacia abajo). Contorno exterior: M16 2, curva a (6,20), arco inferior de radio 10
# hasta (26,20) y curva de vuelta a (16,2). Interior blanco: M16 13, curva a (11.5,21.5), arco inferior de radio 4.5 y curva de vuelta.
_OUTER_CURVES = (((16, 2), (11, 9), (6, 14.5), (6, 20)), ((26, 20), (26, 14.5), (21, 9), (16, 2)))
_INNER_CURVES = (((16, 13), (13.6, 16.4), (11.5, 19), (11.5, 21.5)), ((20.5, 21.5), (20.5, 19), (18.4, 16.4), (16, 13)))
_OUTER_ARC = ((16, 20), 10)   # centro y radio del arco inferior exterior (de (6,20) a (26,20))
_INNER_ARC = ((16, 21.5), 4.5)  # centro y radio del arco inferior interior (de (11.5,21.5) a (20.5,21.5))


def _cubic(p0, p1, p2, p3, steps: int = 24):
    points = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        points.append((
            u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
            u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
        ))
    return points


def _lower_half(center, radius, steps: int = 48):
    """Semicírculo inferior (y hacia abajo): de la izquierda del centro, pasando por el punto más bajo, hasta la derecha."""
    cx, cy = center
    return [(cx + radius * math.cos(math.pi - math.pi * i / steps), cy + radius * math.sin(math.pi - math.pi * i / steps))
            for i in range(1, steps + 1)]


def drop_polygon(outer: bool = True) -> list[tuple[float, float]]:
    """Contorno de la gota exterior o de la interior, en coordenadas del viewBox 32x32."""
    curves, (center, radius) = (_OUTER_CURVES, _OUTER_ARC) if outer else (_INNER_CURVES, _INNER_ARC)
    points = [curves[0][0]]
    points += _cubic(*curves[0])
    points += _lower_half(center, radius)
    points += _cubic(*curves[1])
    return points


@lru_cache(maxsize=4)
def logo_png(size: int = 256) -> bytes:
    """Gota de la marca en PNG con fondo transparente (para el Excel). Se dibuja al doble de tamaño y se reduce para bordes suaves."""
    scale = size * 2 / 32
    canvas = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.polygon([(x * scale, y * scale) for x, y in drop_polygon(outer=True)], fill=ROJO)
    draw.polygon([(x * scale, y * scale) for x, y in drop_polygon(outer=False)], fill="#FFFFFF")
    buffer = io.BytesIO()
    canvas.resize((size, size), Image.LANCZOS).save(buffer, format="PNG")
    return buffer.getvalue()


def existing(path: Path) -> Path | None:
    """Archivo de marca si ya fue cargado (PNG o JPG); None si todavía no existe."""
    return path if path.is_file() else None


def proporcion(path: Path) -> float:
    """Ancho dividido por alto de la imagen, para escalarla sin deformarla."""
    with Image.open(path) as image:
        return image.width / image.height
