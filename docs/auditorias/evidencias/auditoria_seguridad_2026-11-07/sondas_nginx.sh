#!/usr/bin/env bash
# Sondas HTTP de los hallazgos de la auditoría del 07/11/2026 (M-1, B-1, B-2, B-3, B-5, B-6, B-7) contra UNA instancia de Nginx.
#
# Uso: sondas_nginx.sh [URL_BASE]        (por defecto http://127.0.0.1:8080)
#
# Solo lectura y pedidos pequeños: no escribe nada en el servidor. Pensado para una instancia local o de prueba. No ejecutar contra
# producción sin autorización. Los cuerpos de 1 MB, 15 KB y 17 KB se generan en un directorio temporal.

set -u
BASE="${1:-http://127.0.0.1:8080}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

head -c 1048576 /dev/zero | tr '\0' 'a' > "$TMP/1mb.bin"
head -c 17408 /dev/zero | tr '\0' 'a' > "$TMP/17k.bin"
head -c 15360 /dev/zero | tr '\0' 'a' > "$TMP/15k.bin"

# Cuenta las cabeceras de seguridad de una respuesta: una aparición por cabecera es lo esperado (B-3).
repetidas() {
  curl -s -D - -o /dev/null "$1" | tr -d '\r' \
    | awk -F': ' 'tolower($1) ~ /^(x-content-type-options|referrer-policy|content-security-policy|strict-transport-security|x-frame-options|permissions-policy|cache-control)$/ {print tolower($1)}' \
    | sort | uniq -c | awk '{printf "%s x%s  ", $2, $1} END {print ""}'
}

echo "== M-1: redirección de /api (Location relativa, sin puerto interno ni esquema)"
curl -s -D - -o /dev/null "$BASE/api" | tr -d '\r' | grep -i '^HTTP\|^location' | sed 's/^/   /'

echo "== B-1: límite de cuerpo en autenticación (16 KB) y en /api/ general (1 MB, sin cambio)"
for f in 1mb 17k 15k; do
  curl -s -o /dev/null -w "   login cuerpo $f -> %{http_code}\n" -X POST -H 'Content-Type: application/json' --data-binary "@$TMP/$f.bin" "$BASE/api/v1/auth/login"
done
curl -s -o /dev/null -w "   /api/v1/contact cuerpo 1mb -> %{http_code}\n" -X POST -H 'Content-Type: application/json' --data-binary "@$TMP/1mb.bin" "$BASE/api/v1/contact"

echo "== B-2: rutas inexistentes (soft 404 de la SPA: 200 con index.html; no es fuga de datos)"
for p in /ruta-inexistente-xyz /.git/config /phpinfo.php /robots.txt /assets/no-existe.js; do
  curl -s -o /dev/null -w "   $p -> %{http_code} %{content_type}\n" "$BASE$p"
done

echo "== B-3: cabeceras de seguridad por respuesta (cada una debe aparecer UNA sola vez)"
for p in /api/ /api/v1/auth/login /api/v1/acquisition/stream /docs /index.html; do
  printf '   %-30s ' "$p"; repetidas "$BASE$p"
done

echo "== B-6: liveness publicado y readiness no publicado"
for p in /api/v1/healthz /api/v1/readyz /api/health; do
  curl -s -o /dev/null -w "   $p -> %{http_code}\n" "$BASE$p"
done

echo "== B-5 / B-7: aislamiento de origen y reporte de CSP en /"
curl -s -D - -o /dev/null "$BASE/" | tr -d '\r' | grep -i 'cross-origin\|report-to\|report-uri\|reporting-endpoints\|content-security-policy-report-only' | sed 's/^/   /'
echo "   (sin líneas arriba = ausentes)"
