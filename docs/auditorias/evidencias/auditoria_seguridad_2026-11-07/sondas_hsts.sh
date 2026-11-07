#!/usr/bin/env bash
# HSTS y redirecciones por host y X-Forwarded-Proto (B-4, auditoría 07/11/2026). Solo lectura. No usar contra producción.
# Requiere Nginx con TRUSTED_PROXY_CIDR=127.0.0.0/8 (banco): sin proxy de confianza Nginx ignora X-Forwarded-Proto y no emite HSTS.
# Matriz de HSTS y redirecciones. Uso: hsts_matriz.sh [BASE]. Columnas: host, X-Forwarded-Proto, ruta, código, Location, HSTS.
BASE="${1:-http://127.0.0.1:8080}"
for host in glucolume-server.tailb27487.ts.net localhost; do
  for xfp in "" http https; do
    for ruta in /login /api/v1/healthz /api /api/v1/auth/google/login; do
      args=(-s -o /dev/null -D - -H "Host: $host")
      [ -n "$xfp" ] && args+=(-H "X-Forwarded-Proto: $xfp")
      cab=$(curl "${args[@]}" "$BASE$ruta" | tr -d '\r')
      codigo=$(echo "$cab" | awk 'NR==1{print $2}')
      loc=$(echo "$cab" | awk -F': ' 'tolower($1)=="location"{print $2}')
      hsts=$(echo "$cab" | awk -F': ' 'tolower($1)=="strict-transport-security"{print $2}')
      printf '%-38s xfp=%-6s %-28s %-4s loc=%-22s hsts=%s\n' "$host" "${xfp:--}" "$ruta" "$codigo" "${loc:--}" "${hsts:--}"
    done
  done
done
