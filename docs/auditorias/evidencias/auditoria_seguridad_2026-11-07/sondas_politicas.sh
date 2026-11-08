#!/usr/bin/env bash
# Política efectiva por respuesta (B-3): CSP y Referrer-Policy que recibe el navegador, con la regla de intersección y de última cabecera.
# Uso: sondas_politicas.sh [URL_BASE] [HOST]. Solo lectura.
BASE="${1:-http://127.0.0.1:8080}"; HOST_PUBLICO="${2:-glucolume-server.tailb27487.ts.net}"
politica() { # etiqueta, ruta, [args]
  local etiqueta="$1" ruta="$2"; shift 2
  local h; h=$(curl -s -m 15 -D - -o /dev/null -H "Host: $HOST_PUBLICO" "$@" "$BASE$ruta" | tr -d '\r')
  local csp ref
  csp=$(printf '%s\n' "$h" | awk 'tolower($1)=="content-security-policy:"{sub(/^[^:]*: */, ""); print}' | paste -sd'|' -)
  ref=$(printf '%s\n' "$h" | awk 'tolower($1)=="referrer-policy:"{sub(/^[^:]*: */, ""); print}' | paste -sd'|' -)
  printf '%-26s %-28s\n   CSP: %s\n   Referrer-Policy (en orden): %s\n' "$etiqueta" "$ruta" "${csp:-(ninguna)}" "${ref:-(ninguna)}"
}
politica "API JSON 404 backend" /api/
politica "API SSE sin credenciales" /api/v1/acquisition/stream
politica "Swagger /docs" /docs
politica "SPA index (HTML)" /
politica "Estático JS" /assets/index-prueba.js
politica "Error nginx 404 estático" /assets/no-existe.js
politica "Redirección /api" /api
