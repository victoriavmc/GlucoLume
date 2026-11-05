#!/usr/bin/env bash
# Genera las miniaturas WebP de la guía de Ayuda (public/ayuda/miniaturas/) a partir de las capturas originales (public/ayuda/*.png).
#
# - Las capturas originales NO se modifican: el visor ampliado sigue usando el PNG original.
# - Cada miniatura tiene como máximo 840 px de ancho o alto (2× el ancho máximo de 420 px con que se muestran en la guía).
# - Requiere ImageMagick (`convert`). Ejecutar desde cualquier directorio:
#     frontend/scripts/generar-miniaturas-ayuda.sh
# - Volver a ejecutarlo después de cambiar o agregar una captura. El nombre del archivo WebP es el mismo que el del PNG.
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)/public/ayuda"
OUT="$DIR/miniaturas"

if ! command -v convert >/dev/null 2>&1; then
  echo "Falta ImageMagick (convert)." >&2
  exit 1
fi

mkdir -p "$OUT"
for original in "$DIR"/*.png; do
  nombre="$(basename "$original" .png)"
  convert "$original" -resize '840x840>' -strip -quality 85 -define webp:method=6 "$OUT/$nombre.webp"
done
echo "Miniaturas generadas en $OUT ($(ls "$OUT" | wc -l) archivos)."
