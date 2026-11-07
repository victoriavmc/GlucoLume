#!/usr/bin/env bash
# Matriz de cabeceras de seguridad por tipo de respuesta (B-3, auditoría 07/11/2026). Solo lectura. No usar contra producción.
#
# Uso: sondas_cabeceras.sh [URL_BASE] [HOST]
#   URL_BASE  por defecto http://127.0.0.1:8080 (Nginx del frontend)
#   HOST      cabecera Host (por defecto el de Tailscale, sin puerto)
#
# Para cada respuesta cuenta cuántas veces aparece cada cabecera de seguridad. Lo esperado tras la corrección: 1 por cabecera (salvo las
# que legítimamente no se emiten). Un valor 2 o más es una duplicación.
set -u
BASE="${1:-http://127.0.0.1:8080}"
HOST_PUBLICO="${2:-glucolume-server.tailb27487.ts.net}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
CABECERAS='content-security-policy|referrer-policy|x-content-type-options|strict-transport-security|x-frame-options|permissions-policy|cache-control|x-robots-tag'

head -c 2097152 /dev/zero | tr '\0' 'a' > "$TMP/2mb.bin"

fila() {  # etiqueta, método, ruta, [args de curl...]
  local etiqueta="$1" metodo="$2" ruta="$3"; shift 3
  local codigo
  codigo=$(curl -s -m 15 -X "$metodo" -D "$TMP/h" -o /dev/null -w '%{http_code}' -H "Host: $HOST_PUBLICO" "$@" "$BASE$ruta")
  local conteo
  conteo=$(tr -d '\r' < "$TMP/h" | awk -F': ' -v re="$CABECERAS" 'tolower($1) ~ "^(" re ")$" {print tolower($1)}' | sort | uniq -c | awk '{printf "%s=%s ", $2, $1}')
  printf '%-34s %-4s %-30s %-5s %s\n' "$etiqueta" "$metodo" "$ruta" "$codigo" "${conteo:-(ninguna)}"
}

printf '%-34s %-4s %-30s %-5s %s\n' RESPUESTA METODO RUTA CODIGO "CABECERAS (veces)"
fila "API JSON 404 backend"          GET  /api/
fila "API JSON 405 backend"          GET  /api/v1/auth/login
fila "API JSON 422 validación"       POST /api/v1/auth/login -H "Content-Type: application/json" -d '{}'
fila "API salud (liveness)"          GET  /api/v1/healthz
fila "API SSE sin credenciales"      GET  /api/v1/acquisition/stream
fila "Google login (sin configurar)" GET  /api/v1/auth/google/login
fila "Swagger /docs (HTML)"          GET  /docs
fila "SPA index (HTML)"              GET  /
fila "SPA ruta inexistente (200)"    GET  /ruta-inexistente-xyz
fila "Estático JS"                   GET  /assets/index-prueba.js
fila "robots.txt"                    GET  /robots.txt
fila "Estático inexistente (404)"    GET  /assets/no-existe.js
fila "API inexistente (404 JSON)"    GET  /api/no-existe
fila "Cuerpo 2 MB en /api (413)"     POST /api/v1/contact -H "Content-Type: application/json" --data-binary "@$TMP/2mb.bin"
fila "Redirección /api (308)"        GET  /api
