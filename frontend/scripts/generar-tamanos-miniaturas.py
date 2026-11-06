#!/usr/bin/env python3
# Genera src/pages/Account/help/miniaturasTamanos.js: ancho y alto de cada miniatura WebP de la guía de Ayuda.
#
# La guía fija el ancho y el alto de cada <img> de captura con estos valores. El navegador reserva el marco antes de que cargue la
# imagen (sin saltos de diseño al cargarla); el tamaño visible sigue siendo el de la hoja (width: 100%, height: auto), así que la
# presentación no cambia.
#
# Ejecutar después de agregar o regenerar miniaturas (frontend/scripts/generar-miniaturas-ayuda.sh):
#     python3 frontend/scripts/generar-tamanos-miniaturas.py
# Requiere Pillow (está en backend/requirements.txt). La prueba helpCaptures.test.jsx falla si el mapa queda desactualizado.
import pathlib
import sys

from PIL import Image

RAIZ = pathlib.Path(__file__).resolve().parent.parent
MINIATURAS = RAIZ / "public" / "ayuda" / "miniaturas"
SALIDA = RAIZ / "src" / "pages" / "Account" / "help" / "miniaturasTamanos.js"


def main() -> int:
    archivos = sorted(MINIATURAS.glob("*.webp"))
    if not archivos:
        print(f"No hay miniaturas WebP en {MINIATURAS}", file=sys.stderr)
        return 1
    lineas = [
        "// Generado por frontend/scripts/generar-tamanos-miniaturas.py. No editar a mano.",
        "// Ancho y alto (px) de cada miniatura WebP de public/ayuda/miniaturas/.",
        "export const TAMANOS_MINIATURAS = {",
    ]
    for archivo in archivos:
        with Image.open(archivo) as imagen:
            ancho, alto = imagen.size
        lineas.append(f"  '{archivo.name}': [{ancho}, {alto}],")
    lineas.append("};")
    SALIDA.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"{len(archivos)} tamaños escritos en {SALIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
