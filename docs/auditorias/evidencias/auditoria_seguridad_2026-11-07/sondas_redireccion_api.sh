#!/usr/bin/env bash
# Sondas de M-1 (redirección de /api) contra UNA instancia de Nginx del frontend + backend. Solo lectura. No usar contra producción.
#
# Uso: sondas_redireccion_api.sh [URL_BASE] [HOST_PUBLICO]
#   URL_BASE       por defecto http://127.0.0.1:8080 (el puerto de escucha del contenedor del frontend)
#   HOST_PUBLICO   por defecto glucolume-server.tailb27487.ts.net (cabecera Host como la envía el acceso por Tailscale, sin puerto)
#
# Qué comprueba:
#   1. Redirección de /api, /api?x=1 y POST /api: código, Location (relativa o no), que no lleve esquema http ni el puerto :8080.
#   2. Rutas proxificadas sin cambios: /api/, /api/v1/auth/login (GET y POST), /api/v1/healthz. Códigos y cuerpo del backend.
#   3. Seguimiento de la redirección (curl -L, máx. 5): destino final, cantidad de saltos (bucles) y códigos 5xx.
#   4. Mixed content: ninguna Location de /api puede empezar con http:// cuando el acceso fue por HTTPS (proxy de confianza).
set -u
BASE="${1:-http://127.0.0.1:8080}"
HOST_PUBLICO="${2:-glucolume-server.tailb27487.ts.net}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cabeceras() { curl -s -m 10 -D - -o /dev/null "$@" | tr -d '\r' | grep -i '^HTTP\|^location' | sed 's/^/   /'; }

echo "== 1) Redirección de /api (Host público: $HOST_PUBLICO)"
echo "   GET /api"; cabeceras -H "Host: $HOST_PUBLICO" "$BASE/api"
echo "   POST /api"; cabeceras -X POST -H "Host: $HOST_PUBLICO" "$BASE/api"
echo "   GET /api?x=1"; cabeceras -H "Host: $HOST_PUBLICO" "$BASE/api?x=1"
echo "   GET /api sin Host (acceso local)"; cabeceras "$BASE/api"

echo "== 2) Rutas proxificadas (código y cuerpo del backend)"
for ruta in /api/ /api/v1/healthz; do
  printf '   GET %-20s -> ' "$ruta"; curl -s -m 10 -o "$TMP/cuerpo" -w '%{http_code}' -H "Host: $HOST_PUBLICO" "$BASE$ruta"; printf '  %s\n' "$(head -c 80 "$TMP/cuerpo" | tr -d '\n')"
done
printf '   GET  /api/v1/auth/login -> '; curl -s -m 10 -o "$TMP/cuerpo" -w '%{http_code}' -H "Host: $HOST_PUBLICO" "$BASE/api/v1/auth/login"; printf '  %s\n' "$(head -c 80 "$TMP/cuerpo" | tr -d '\n')"
printf '   POST /api/v1/auth/login -> '; curl -s -m 10 -o "$TMP/cuerpo" -w '%{http_code}' -X POST -H "Content-Type: application/json" -H "Host: $HOST_PUBLICO" -d '{"identificador":"nadie@example.com","password":"x"}' "$BASE/api/v1/auth/login"; printf '  %s\n' "$(head -c 80 "$TMP/cuerpo" | tr -d '\n')"

echo "== 3) Seguimiento de redirecciones (curl -L, máx. 5 saltos)"
for ruta in /api /api?x=1; do
  curl -s -m 10 -L --max-redirs 5 -o /dev/null -H "Host: $HOST_PUBLICO" -w "   $ruta -> final=%{url_effective} codigo=%{http_code} saltos=%{num_redirects}\n" "$BASE$ruta"
done

echo "== 4) Mixed content: Location de /api con acceso HTTPS de confianza (X-Forwarded-Proto: https)"
curl -s -m 10 -D - -o /dev/null -H "Host: $HOST_PUBLICO" -H "X-Forwarded-Proto: https" "$BASE/api" | tr -d '\r' | grep -i '^location' | sed 's/^/   /'
echo "   (vacío = sin Location absoluta; relativa = se resuelve contra el origen HTTPS del navegador)"
