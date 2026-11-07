#!/usr/bin/env bash
# Cabeceras COOP/CORP/COEP por tipo de respuesta (B-5). Antes y después en resultados_aislamiento_cabeceras_*.txt. Solo lectura.
# Uso: [NGINX_HTML=<webroot con assets/>] sondas_aislamiento_cabeceras.sh [BASE]. Sin NGINX_HTML no se prueba el estático.
BASE="${1:-http://127.0.0.1:8080}"
ASSET=$(ls "${NGINX_HTML:-/dev/null}/assets" 2>/dev/null | grep "\.js$" | head -n1)
for ruta in /login /ayuda /ayuda/ /api/v1/healthz /api/v1/security/csp-report /api /docs /no-existe-xyz "/assets/$ASSET"; do
  metodo=GET; [ "$ruta" = /api/v1/security/csp-report ] && metodo=POST
  cab=$(curl -s -o /dev/null -D - -X $metodo -H "Host: glucolume-server.tailb27487.ts.net" "$BASE$ruta" | tr -d '\r')
  codigo=$(echo "$cab" | awk 'NR==1{print $2}')
  coop=$(echo "$cab" | awk -F': ' 'tolower($1)=="cross-origin-opener-policy"{print $2}')
  corp=$(echo "$cab" | awk -F': ' 'tolower($1)=="cross-origin-resource-policy"{print $2}')
  coep=$(echo "$cab" | awk -F': ' 'tolower($1)=="cross-origin-embedder-policy"{print $2}')
  printf '%-40s %-4s COOP=%-14s CORP=%-12s COEP=%s\n' "$ruta" "$codigo" "${coop:--}" "${corp:--}" "${coep:--}"
done
