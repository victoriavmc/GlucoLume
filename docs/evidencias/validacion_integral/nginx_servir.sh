#!/usr/bin/env bash
# Sirve el build de producción del frontend (VITE_API_BASE_URL=/) con la plantilla REAL de Nginx delante de la API sintética (SQLite), para
# probar con un navegador. Se detiene con SIGTERM. Uso: DIST=<build> bash nginx_servir.sh   (puerto 18090; API en 18080)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"; REPO="$(cd "$HERE/../../.." && pwd)"
DIST="${DIST:?}"; PORT_NGINX="${PORT_NGINX:-18090}"; PORT_API=18080
W="$(mktemp -d)"; chmod 755 "$W"; mkdir -p "$W/conf.d" "$W/tmp" "$W/html"; cp -r "$DIST"/. "$W/html"/; chmod -R a+rX "$W/html"
BACKEND_UPSTREAM="127.0.0.1:$PORT_API" DNS_RESOLVER=127.0.0.1 TRUSTED_PROXY_CIDR=172.16.0.0/12 \
  envsubst '${BACKEND_UPSTREAM} ${DNS_RESOLVER} ${TRUSTED_PROXY_CIDR}' < "$REPO/docker/nginx/default.conf.template" \
  | sed "s#root /usr/share/nginx/html;#root $W/html;#; s#listen 8080;#listen $PORT_NGINX;#" > "$W/conf.d/default.conf"
cat > "$W/nginx.conf" <<CONF
worker_processes 1; daemon off; pid $W/nginx.pid; error_log $W/error.log warn;
events { worker_connections 256; }
http { include /etc/nginx/mime.types; default_type application/octet-stream;
  client_body_temp_path $W/tmp/c; proxy_temp_path $W/tmp/p; fastcgi_temp_path $W/tmp/f; uwsgi_temp_path $W/tmp/u; scgi_temp_path $W/tmp/s;
  include $W/conf.d/*.conf; }
CONF
trap 'kill $NGPID $APIPID 2>/dev/null; wait 2>/dev/null' EXIT TERM INT
PORT=$PORT_API FRONTEND_URL="http://localhost:$PORT_NGINX" API_BASE_URL="http://localhost:$PORT_NGINX" python "$HERE/servidor_sintetico.py" >/dev/null 2>&1 & APIPID=$!
nginx -c "$W/nginx.conf" > "${ACCESS_LOG:-$W/access.log}" 2>>"$W/error.log" & NGPID=$!
wait $NGPID
