#!/usr/bin/env bash
# Valida la configuración REAL de Nginx (docker/nginx/default.conf.template) con un nginx de verdad delante de la API real (SQLite sintético).
# Limitación honesta: usa el nginx del sistema (no la imagen nginxinc/nginx-unprivileged fijada por digest, que no se pudo descargar: límite de
# Docker Hub). La plantilla es la misma, procesada con envsubst como hace el entrypoint de la imagen; solo cambia el binario y el `root`.
# Con IMAGEN=<imagen del frontend> (construida con el Dockerfile del proyecto) las mismas comprobaciones corren contra la IMAGEN REAL (nginx-unprivileged
# fijada por digest) con --network host, en vez del nginx del sistema.
# Uso (desde backend/ con el entorno virtual activo): DIST=<carpeta del build con VITE_API_BASE_URL=/> bash ../docs/evidencias/validacion_integral/nginx_real.sh
#                                                   IMAGEN=glucolume/frontend:validacion bash ../docs/evidencias/validacion_integral/nginx_real.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"; REPO="$(cd "$HERE/../../.." && pwd)"
IMAGEN="${IMAGEN:-}"; DIST="${DIST:-/nonexistent}"; [ -n "$IMAGEN" ] || : "${DIST:?definir DIST (build del frontend) o IMAGEN}"; PORT_NGINX="${PORT_NGINX:-18090}"; PORT_API=18080; CNAME=gl-front-validacion; TRUSTED=172.16.0.0/12
[ -n "$IMAGEN" ] && PORT_NGINX=8080
W="$(mktemp -d)"; chmod 755 "$W"; pass=0; fail=0
ok(){ echo "OK    $1"; pass=$((pass+1)); }; bad(){ echo "FALLA $1"; fail=$((fail+1)); }
cleanup(){ [ -n "$IMAGEN" ] && docker rm -f "$CNAME" >/dev/null 2>&1; [ -n "${NGPID:-}" ] && kill "$NGPID" 2>/dev/null; [ -n "${APIPID:-}" ] && kill "$APIPID" 2>/dev/null; wait 2>/dev/null; }
trap cleanup EXIT
mkdir -p "$W/conf.d" "$W/tmp" "$W/html"; [ -n "$IMAGEN" ] || { cp -r "$DIST"/. "$W/html"/; chmod -R a+rX "$W/html"; DIST="$W/html"; }  # el worker de nginx (www-data) debe poder leer el build
gen(){ # $1 = TRUSTED_PROXY_CIDR
  TRUSTED="$1"; [ -n "$IMAGEN" ] && return
  BACKEND_UPSTREAM="127.0.0.1:$PORT_API" DNS_RESOLVER=127.0.0.1 TRUSTED_PROXY_CIDR="$1" \
  envsubst '${BACKEND_UPSTREAM} ${DNS_RESOLVER} ${TRUSTED_PROXY_CIDR}' < "$REPO/docker/nginx/default.conf.template" \
  | sed "s#root /usr/share/nginx/html;#root $DIST;#; s#listen 8080;#listen $PORT_NGINX;#" > "$W/conf.d/default.conf"
}
cat > "$W/nginx.conf" <<CONF
worker_processes 1; daemon off; pid $W/nginx.pid; error_log $W/error.log warn;
events { worker_connections 256; }
http { include /etc/nginx/mime.types; default_type application/octet-stream;
  client_body_temp_path $W/tmp/c; proxy_temp_path $W/tmp/p; fastcgi_temp_path $W/tmp/f; uwsgi_temp_path $W/tmp/u; scgi_temp_path $W/tmp/s;
  include $W/conf.d/*.conf; }
CONF
mark_log(){ if [ -n "$IMAGEN" ]; then MARK=$(date +%s.%N); else : > "$W/access.log"; fi; }
refresh_log(){ [ -n "$IMAGEN" ] && docker logs --since "$MARK" "$CNAME" > "$W/access.log" 2>&1; return 0; }
start_nginx(){ if [ -n "$IMAGEN" ]; then docker rm -f "$CNAME" >/dev/null 2>&1; docker run -d --name "$CNAME" --network host -e BACKEND_UPSTREAM="127.0.0.1:$PORT_API" -e DNS_RESOLVER=127.0.0.1 -e TRUSTED_PROXY_CIDR="$TRUSTED" "$IMAGEN" >/dev/null; MARK=$(date +%s.%N); for i in $(seq 1 60); do curl -s -o /dev/null "http://127.0.0.1:$PORT_NGINX/nginx-health" && return; sleep 0.5; done; return; fi
  nginx -c "$W/nginx.conf" > "$W/access.log" 2>>"$W/error.log" & NGPID=$!; for i in $(seq 1 40); do curl -s -o /dev/null "http://127.0.0.1:$PORT_NGINX/nginx-health" 2>/dev/null && return; curl -s -o /dev/null "http://127.0.0.1:$PORT_NGINX/" && return; sleep 0.25; done; }
stop_nginx(){ if [ -n "$IMAGEN" ]; then docker rm -f "$CNAME" >/dev/null 2>&1; return; fi; kill "$NGPID" 2>/dev/null; wait "$NGPID" 2>/dev/null; NGPID=; }

start_api(){ [ -n "${APIPID:-}" ] && { kill "$APIPID" 2>/dev/null; wait "$APIPID" 2>/dev/null; }
  PORT=$PORT_API python "$HERE/servidor_sintetico.py" >/dev/null 2>&1 & APIPID=$!
  for i in $(seq 1 100); do curl -s "http://127.0.0.1:$PORT_API/healthz" >/dev/null && break; sleep 0.3; done; }
start_api

echo "== 1. Sintaxis"; gen 172.16.0.0/12
if [ -n "$IMAGEN" ]; then docker run --rm --network host -e BACKEND_UPSTREAM=127.0.0.1:$PORT_API -e DNS_RESOLVER=127.0.0.1 -e TRUSTED_PROXY_CIDR=172.16.0.0/12 --entrypoint sh "$IMAGEN" -c '/docker-entrypoint.d/20-envsubst-on-templates.sh >/dev/null 2>&1; nginx -t 2>&1' >"$W/t.out" 2>&1; grep -q "syntax is ok" "$W/t.out" && ok "nginx -t dentro de la imagen: configuración válida" || { bad "nginx -t"; cat "$W/t.out"; }; else nginx -t -c "$W/nginx.conf" >"$W/t.out" 2>&1 && ok "nginx -t: configuración válida" || { bad "nginx -t"; cat "$W/t.out"; }; fi
echo "== 2. Arranque, SPA y logs sin query (H-14)"; start_nginx
code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT_NGINX/verificar-correo?token=PRUEBA123&otro=SECRETO456"); [ "$code" = 200 ] && ok "ruta de la SPA con token en la query responde 200 (index.html)" || bad "SPA $code"
curl -s -o /dev/null "http://127.0.0.1:$PORT_NGINX/api/v1/auth/verify-email?token=ENLACE789"
curl -s -o /dev/null "http://127.0.0.1:$PORT_NGINX/restablecer?token=RESET000"
sleep 0.5; refresh_log; cat "$W/access.log" | sed 's/^/   log: /'
grep -qE "PRUEBA123|SECRETO456|ENLACE789|RESET000|token=" "$W/access.log" && bad "el log contiene tokens" || ok "el access_log NO contiene ninguno de los tokens de la query"
grep -q '"GET /verificar-correo"' "$W/access.log" && ok "el log conserva método y ruta" || bad "formato del log"
grep -qE '127\.0\.0\.1 - \[.*rid=[0-9a-f]{16,}' "$W/access.log" && ok "el log conserva IP, estado y rid= (correlación)" || bad "campos del log"
if [ -n "$IMAGEN" ]; then
  echo "== 2b. Imagen"
  [ "$(docker exec "$CNAME" id -u)" = 101 ] && ok "el proceso corre sin privilegios (uid 101)" || bad "uid"
  for i in $(seq 1 12); do st=$(docker inspect -f '{{.State.Health.Status}}' "$CNAME"); [ "$st" = healthy ] && break; sleep 5; done; [ "$st" = healthy ] && ok "HEALTHCHECK de la imagen: healthy" || bad "healthcheck: $st"
  docker exec "$CNAME" sh -c 'nginx -T 2>/dev/null | grep -c "log_format sin_query"' | grep -q 1 && ok "la plantilla se procesó al iniciar (log_format sin_query presente)" || bad "plantilla"
fi
echo "== 3. Cabeceras de seguridad"
H=$(curl -s -D- -o /dev/null "http://127.0.0.1:$PORT_NGINX/")
echo "$H" | grep -qi "^content-security-policy: default-src 'self'.*style-src 'self'; script-src 'self'.*frame-ancestors 'none'" && ok "CSP estricta (style-src 'self', sin unsafe-inline)" || bad "CSP"
echo "$H" | grep -qi "unsafe-inline" && bad "CSP contiene unsafe-inline" || ok "CSP sin unsafe-inline"
echo "$H" | grep -qi "^x-frame-options: DENY" && echo "$H" | grep -qi "^x-content-type-options: nosniff" && ok "X-Frame-Options y nosniff" || bad "cabeceras"
echo "$H" | grep -qi "^strict-transport-security" && bad "HSTS por HTTP" || ok "sin HSTS cuando el pedido es HTTP"
echo "$H" | grep -qi "^server: nginx/" && bad "Server revela la versión" || ok "server_tokens off (sin versión)"
echo "== 4. Proxy de confianza: HSTS y X-Forwarded-For"
H=$(curl -s -D- -o /dev/null -H 'X-Forwarded-Proto: https' "http://127.0.0.1:$PORT_NGINX/")
echo "$H" | grep -qi "^strict-transport-security" && bad "HSTS desde un cliente no confiable" || ok "un cliente no confiable NO puede forzar HSTS con X-Forwarded-Proto"
mark_log; curl -s -o /dev/null -H 'X-Forwarded-For: 6.6.6.6' "http://127.0.0.1:$PORT_NGINX/api/v1/auth/verify-email?token=x"; sleep 0.5; refresh_log
grep -q "^127.0.0.1 " "$W/access.log" && ! grep -q "6.6.6.6" "$W/access.log" && ok "una IP falsificada en X-Forwarded-For se ignora si el pedido no viene de un proxy de confianza" || bad "IP falsificable"
stop_nginx; gen 127.0.0.1/32; start_nginx; [ -n "$IMAGEN" ] && sleep 1
H=$(curl -s -D- -o /dev/null -H 'X-Forwarded-Proto: https' "http://127.0.0.1:$PORT_NGINX/")
echo "$H" | grep -qi "^strict-transport-security: max-age=31536000" && ok "con TRUSTED_PROXY_CIDR que incluye al proxy, HSTS se envía según el esquema original" || bad "HSTS con proxy confiable"
mark_log; curl -s -o /dev/null -H 'X-Forwarded-For: 203.0.113.9' "http://127.0.0.1:$PORT_NGINX/api/v1/auth/verify-email?token=x"; sleep 0.5; refresh_log
grep -q "^203.0.113.9 " "$W/access.log" && ok "con proxy de confianza se toma la IP real del cliente" || bad "IP real"
stop_nginx; gen 172.16.0.0/12; start_nginx
echo "== 5. Tope de pedidos en /api/v1/auth/ (limit_req 30r/s, ráfaga 60)"
codes=$(for i in $(seq 1 220); do curl -s -o /dev/null -w '%{http_code}\n' -X POST -H 'Content-Type: application/json' -d '{"identificador":"nadie.sintetico","password":"x"}' "http://127.0.0.1:$PORT_NGINX/api/v1/auth/login" & done; wait)
n429=$(echo "$codes" | grep -c 429); echo "   respuestas: $(echo "$codes" | sort | uniq -c | tr '\n' ' ')"; [ "$n429" -gt 0 ] && ok "Nginx responde 429 ante una ráfaga ($n429 de 220)" || bad "sin 429 de Nginx"
start_api   # reinicia la API: la ráfaga anterior agotó el límite de /login por IP de la propia API (contador en memoria)
echo "== 6. H-09 detrás de Nginx: la cookie HttpOnly atraviesa el proxy"
JAR="$W/jar"; curl -s -c "$JAR" -D "$W/h1" -o "$W/b1" -X POST -H 'Content-Type: application/json' -H 'X-GlucoLume-CSRF: 1' -d '{"identificador":"victoria","password":"Glucolume#Prueba2026"}' "http://127.0.0.1:$PORT_NGINX/api/v1/auth/login"
grep -qi "^set-cookie: glucolume_refresh=.*HttpOnly.*SameSite=strict" "$W/h1" && ok "Set-Cookie (HttpOnly, SameSite=strict) llega al cliente a través de Nginx" || { bad "Set-Cookie"; cat "$W/h1"; }
grep -q '"refreshToken":null' "$W/b1" && ok "el cuerpo no trae el refresh token" || bad "cuerpo con refresh token"
code=$(curl -s -b "$JAR" -c "$JAR" -o /dev/null -w '%{http_code}' -X POST -H 'X-GlucoLume-CSRF: 1' "http://127.0.0.1:$PORT_NGINX/api/v1/auth/refresh"); [ "$code" = 200 ] && ok "refresh por Nginx con la cookie: 200" || bad "refresh $code"
code=$(curl -s -b "$JAR" -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$PORT_NGINX/api/v1/auth/refresh"); [ "$code" != 200 ] && ok "sin la cabecera anti-CSRF la cookie no sirve ($code)" || bad "refresh sin cabecera"
code=$(curl -s -b "$JAR" -o /dev/null -w '%{http_code}' -X POST -H 'X-GlucoLume-CSRF: 1' -H 'Origin: https://sitio-malicioso.example' "http://127.0.0.1:$PORT_NGINX/api/v1/auth/refresh"); [ "$code" = 401 ] && ok "Origin ajeno rechazado (401)" || bad "Origin ajeno $code"
echo "== 7. Documentación de la API"
code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT_NGINX/openapi.json"); echo "   /openapi.json (API_ENV=development en este ensayo): $code"
echo; echo "RESUMEN: $pass correctas, $fail con falla"; cp "$W/access.log" "${LOG_OUT:-/dev/null}" 2>/dev/null; [ "$fail" = 0 ]
