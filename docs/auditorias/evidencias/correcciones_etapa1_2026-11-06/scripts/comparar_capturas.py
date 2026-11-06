# Compara dos capturas de página completa (PNG) píxel a píxel. Uso: python3 comparar_capturas.py antes.png despues.png
import sys
from PIL import Image, ImageChops
a = Image.open(sys.argv[1]).convert("RGB"); b = Image.open(sys.argv[2]).convert("RGB")
print("tamaños:", a.size, b.size)
if a.size != b.size:
    print("resultado: tamaños distintos"); raise SystemExit(1)
d = ImageChops.difference(a, b)
print("bbox de diferencias:", d.getbbox())
print("píxeles distintos:", sum(d.convert("L").point(lambda v: 255 if v else 0).histogram()[255:]), "de", a.size[0] * a.size[1])
