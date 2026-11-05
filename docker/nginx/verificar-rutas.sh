#!/usr/bin/env bash
# Verificación de rutas y cabeceras del Nginx del frontend (docker/nginx/default.conf.template).
#
# Uso: docker/nginx/verificar-rutas.sh [URL_BASE]     (por defecto http://127.0.0.1:8080)
#
# Comprueba las rutas de la SPA (acceso directo, con barra final, con query), la carpeta de capturas de la guía de Ayuda
# (public/ayuda/, que tiene el mismo nombre que la ruta /ayuda), las cabeceras de caché y las cabeceras de seguridad.
# Devuelve 0 si todas las comprobaciones pasan, 1 si alguna falla. No envía nada a ningún servicio externo.

set -u
BASE="${1:-http://127.0.0.1:8080}"
fallos=0
ok() { printf 'PASS  %s\n' "$1"; }
mal() { printf 'FAIL  %s\n' "$1"; fallos=$((fallos + 1)); }

# Devuelve código, tipo, cache-control y un fragmento del cuerpo de una ruta (una sola petición).
consulta() {
  curl -s -o /tmp/verificar-rutas.cuerpo -D /tmp/verificar-rutas.cabeceras -w '%{http_code}' "$BASE$1"
}
cabecera() { grep -i "^$1:" /tmp/verificar-rutas.cabeceras | tr -d '\r' | sed -E "s/^[^:]+: *//" | head -1; }

# 1) Rutas de la SPA: deben responder el index.html (200, text/html, con el contenedor de React).
for ruta in /ayuda /ayuda/ "/ayuda?seccion=cliente" /app/ayuda /consejos; do
  codigo=$(consulta "$ruta")
  if [ "$codigo" = "200" ] && grep -q 'id="root"' /tmp/verificar-rutas.cuerpo && [[ "$(cabecera content-type)" == text/html* ]]; then
    ok "SPA $ruta -> 200 index.html"
  else
    mal "SPA $ruta -> $codigo (esperado 200 index.html)"
  fi
done

# 2) Capturas de la guía: archivos reales, con caché explícita de 7 días.
captura="/ayuda/cliente-menu-inicio.png"
codigo=$(consulta "$captura")
if [ "$codigo" = "200" ] && [[ "$(cabecera content-type)" == image/png* ]]; then ok "captura $captura -> 200 image/png"; else mal "captura $captura -> $codigo"; fi
if [[ "$(cabecera cache-control)" == *"max-age=604800"* ]]; then ok "captura $captura -> Cache-Control max-age=604800"; else mal "captura $captura sin max-age=604800 (Cache-Control: $(cabecera cache-control))"; fi

miniatura="/ayuda/miniaturas/cliente-menu-inicio.webp"
codigo=$(consulta "$miniatura")
if [ "$codigo" = "200" ] && [[ "$(cabecera content-type)" == image/webp* ]]; then ok "miniatura $miniatura -> 200 image/webp"; else mal "miniatura $miniatura -> $codigo"; fi
if [[ "$(cabecera cache-control)" == *"max-age=604800"* ]]; then ok "miniatura -> Cache-Control max-age=604800"; else mal "miniatura sin max-age=604800"; fi

# 3) Un archivo inexistente dentro de la carpeta de capturas es 404 (no el index.html de la SPA).
codigo=$(consulta "/ayuda/no-existe.png")
if [ "$codigo" = "404" ]; then ok "/ayuda/no-existe.png -> 404"; else mal "/ayuda/no-existe.png -> $codigo (esperado 404)"; fi

# 4) Cabeceras de seguridad heredadas en la ruta de Ayuda (no se pierden por una ubicación nueva).
codigo=$(consulta "/ayuda")
for cab in content-security-policy x-frame-options x-content-type-options referrer-policy; do
  if [ -n "$(cabecera "$cab")" ]; then ok "/ayuda conserva $cab"; else mal "/ayuda sin $cab"; fi
done

# 5) index.html nunca se cachea (tampoco la página /ayuda, que es el mismo index.html); los archivos con hash, sí.
consulta "/ayuda" >/dev/null
if [[ "$(cabecera cache-control)" == "no-cache" ]]; then ok "/ayuda (SPA) -> no-cache"; else mal "/ayuda (SPA) -> Cache-Control: $(cabecera cache-control)"; fi
consulta "/index.html" >/dev/null
if [[ "$(cabecera cache-control)" == "no-cache" ]]; then ok "/index.html -> no-cache"; else mal "/index.html -> Cache-Control: $(cabecera cache-control)"; fi
js=$(grep -o 'assets/[^"]*\.js' /tmp/verificar-rutas.cuerpo 2>/dev/null | head -1)
if [ -z "$js" ]; then consulta "/" >/dev/null; js=$(grep -o 'assets/[^"]*\.js' /tmp/verificar-rutas.cuerpo | head -1); fi
if [ -n "$js" ]; then
  codigo=$(consulta "/$js")
  if [ "$codigo" = "200" ] && [[ "$(cabecera cache-control)" == *"max-age=31536000"* ]]; then ok "/$js -> 200 con max-age=31536000"; else mal "/$js -> $codigo, Cache-Control: $(cabecera cache-control)"; fi
else
  mal "no se encontró un archivo JS en assets/ para comprobar caché"
fi

rm -f /tmp/verificar-rutas.cuerpo /tmp/verificar-rutas.cabeceras
echo
if [ "$fallos" -eq 0 ]; then echo "Todas las comprobaciones pasaron."; exit 0; fi
echo "$fallos comprobación(es) fallaron."; exit 1
