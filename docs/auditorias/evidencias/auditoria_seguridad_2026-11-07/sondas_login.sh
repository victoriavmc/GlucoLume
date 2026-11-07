#!/usr/bin/env bash
# Sondas de M-2 (inicio de sesión) contra UNA instancia de Nginx + backend de PRUEBA. No usar contra producción.
#
# Uso: sondas_login.sh [URL_BASE]     (por defecto http://127.0.0.1:8080)
# Los contadores por IP viven en memoria: ejecutar con el backend recién iniciado, o el límite ya estará agotado para esa IP.
#
# 1) La secuencia del auditor: 15 POST consecutivos con credenciales incorrectas desde la misma IP.
# 2) Falsificación de X-Forwarded-For: 70 pedidos, cada uno con una IP distinta en la cabecera. Si el límite fuera por la cabecera del
#    cliente, no se alcanzaría nunca. Debe responder 429 desde el pedido 61 (límite por IP real: 60 en 10 min).
# Los 500 son de un backend sin SQL Server (entorno local): el límite cuenta antes de consultar la base, así que igual se cuentan.
set -u
BASE="${1:-http://127.0.0.1:8080}"
URL="$BASE/api/v1/auth/login"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "== 1) Secuencia del auditor (15 intentos incorrectos, cuenta inexistente, misma IP)"
echo "   Nota: la parte 1 solo es concluyente con SQL Server. Sin base, la app responde 500 antes de registrar el fallo; la evidencia
   con base de prueba es resultados_login_pytest.txt (test_quince_intentos_seguidos_desde_una_ip_quedan_limitados_con_retry_after)."
for i in $(seq 1 15); do
  curl -s -D "$TMP/h1_$i" -o "$TMP/b1_$i" -X POST -H "Content-Type: application/json" \
    -d '{"identificador":"nadie@example.com","password":"Incorrecta123!"}' "$URL"
  printf '   intento %2d -> %s  Retry-After=%s\n' "$i" "$(head -1 "$TMP/h1_$i" | awk '{print $2}')" \
    "$(grep -i '^retry-after:' "$TMP/h1_$i" | tr -d '\r' | awk '{print $2}')"
done

echo "== 2) X-Forwarded-For falsificado distinto en cada pedido (70 pedidos)"
for i in $(seq 1 70); do
  curl -s -D "$TMP/h2_$i" -o /dev/null -X POST -H "Content-Type: application/json" -H "X-Forwarded-For: 10.250.$((i / 250)).$((i % 250))" \
    -d '{"identificador":"nadie@example.com","password":"Incorrecta123!"}' "$URL"
done
# Las dos partes usan la misma IP: el límite (60 en 10 min) se alcanza en el pedido 61 contando la parte 1 (15 pedidos), o sea el 46 de esta parte.
primero=$(grep -l '^HTTP/1.1 429' "$TMP"/h2_* 2>/dev/null | sed 's/.*h2_//' | sort -n | head -1)
echo "   primer 429 en el pedido: ${primero:-ninguno}  (esperado: 46 = 61 - 15 de la parte 1; Retry-After=600 de la aplicación)"
