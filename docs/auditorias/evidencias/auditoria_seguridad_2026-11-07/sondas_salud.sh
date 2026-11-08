#!/usr/bin/env bash
# Sondas de salud de la API (B-6, auditoría 07/11/2026). Solo lectura. No usar contra producción.
#
# Uso: sondas_salud.sh [URL_BASE] [HOST]
#   URL_BASE  por defecto http://127.0.0.1:8080 (Nginx del frontend; /api/... llega al backend)
#
# Mide /api/v1/healthz (liveness) y /api/v1/readyz (readiness): código, tiempo, cabeceras de caché y reintento, y el cuerpo.
# Comprueba además que ninguna respuesta exponga versión, cadena de conexión ni nombres internos.
set -u
BASE="${1:-http://127.0.0.1:8080}"
HOST_PUBLICO="${2:-glucolume-server.tailb27487.ts.net}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

sonda() {  # ruta
  local ruta="$1"
  local salida
  salida=$(curl -s -m 15 -D "$TMP/h" -o "$TMP/b" -w '%{http_code} %{time_total}' -H "Host: $HOST_PUBLICO" "$BASE$ruta")
  local codigo="${salida% *}" tiempo="${salida#* }"
  local cache reintento
  cache=$(tr -d '\r' < "$TMP/h" | awk 'tolower($1)=="cache-control:"{print $2}' | head -1)
  reintento=$(tr -d '\r' < "$TMP/h" | awk 'tolower($1)=="retry-after:"{print $2}' | head -1)
  printf '%-22s %s  tiempo=%ss  cache-control=%s  retry-after=%s\n' "$ruta" "$codigo" "$tiempo" "${cache:--}" "${reintento:--}"
  printf '   cuerpo: %s\n' "$(tr -d '\n' < "$TMP/b" | head -c 220)"
  if grep -qiE 'version|versión|server=|password|database=|trusted_connection|sql-|traceback|rutas?:' "$TMP/b"; then
    echo "   !! el cuerpo contiene un término sensible"
  else
    echo "   sin términos sensibles en el cuerpo"
  fi
}

echo "== liveness"
sonda /api/v1/healthz
echo "== readiness (1.ª consulta: comprueba)"
sonda /api/v1/readyz
echo "== readiness (2.ª consulta dentro de la ventana de caché: no vuelve a consultar la base)"
sonda /api/v1/readyz
