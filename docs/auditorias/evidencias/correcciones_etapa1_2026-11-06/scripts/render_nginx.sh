#!/usr/bin/env bash
# Renderiza la plantilla del repositorio para el laboratorio (mismas sustituciones que antes) y recarga Nginx.
set -e
TPL=${1:-/home/user/GlucoLume/docker/nginx/default.conf.template}
sed -e 's#${TRUSTED_PROXY_CIDR}#127.0.0.1/32#g' -e 's#${DNS_RESOLVER}#127.0.0.11#g' -e 's#${BACKEND_UPSTREAM}#127.0.0.1:9#g' \
  -e "s#root /usr/share/nginx/html;#root /tmp/claude-0/-home-user-GlucoLume/f3e9e155-d85e-5eeb-a123-2ced2a57f6db/scratchpad/fe/frontend/dist;#" -e "s#access_log /dev/stdout sin_query;#access_log /tmp/claude-0/-home-user-GlucoLume/f3e9e155-d85e-5eeb-a123-2ced2a57f6db/scratchpad/nginx/access.log sin_query;#" "$TPL" > /tmp/claude-0/-home-user-GlucoLume/f3e9e155-d85e-5eeb-a123-2ced2a57f6db/scratchpad/nginx/server.inc
nginx -t -c /tmp/claude-0/-home-user-GlucoLume/f3e9e155-d85e-5eeb-a123-2ced2a57f6db/scratchpad/nginx/nginx.conf >/dev/null 2>&1 && nginx -s reload -c /tmp/claude-0/-home-user-GlucoLume/f3e9e155-d85e-5eeb-a123-2ced2a57f6db/scratchpad/nginx/nginx.conf && sleep 1 && echo "nginx recargado con $TPL"
