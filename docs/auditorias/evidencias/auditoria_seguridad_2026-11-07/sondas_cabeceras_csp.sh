#!/usr/bin/env bash
# Cabeceras CSP de la SPA y de la API antes y después de B-7 (report-uri). Solo lectura. Ver resultados_cabeceras_csp_antes.txt y _despues.txt.
# Cabeceras CSP de la SPA y de la API, con el Nginx local. Uso: cabeceras_csp.sh [URL_BASE]
BASE="${1:-http://127.0.0.1:8080}"
for ruta in /login /app/inicio /api/v1/healthz /api/v1/security/csp-report; do
  metodo=GET; [ "$ruta" = /api/v1/security/csp-report ] && metodo=POST
  echo "== $metodo $ruta"
  curl -s -o /dev/null -D - -X $metodo -H "Host: glucolume-server.tailb27487.ts.net" "$BASE$ruta" | tr -d '\r' | grep -i "^content-security-policy\|^HTTP/" 
done
