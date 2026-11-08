#!/usr/bin/env bash
# Anexo C (auditoría 07/11/2026). DIAGNÓSTICO DE SOLO LECTURA dentro de los contenedores (docker compose exec).
# Lee identidades, capacidades, versiones de paquetes y la configuración efectiva de Nginx. No escribe nada en los contenedores
# (rootfs de solo lectura) y no imprime variables de entorno.
#
# Uso (desde el directorio del repo, en el servidor):
#   bash 03_contenedores.sh 2>&1 | tee "$HOME/diag_03_contenedores_$(date +%F).txt"
sec() { printf '\n===== %s =====\n' "$1"; }
ejec() { docker compose exec -T "$1" sh -c "$2" 2>&1; }

for svc in backend lifecycle notifications frontend proxy; do
  sec "contenedor: $svc"
  if ! docker compose ps --status running --services 2>/dev/null | grep -qx "$svc"; then echo "(no está en ejecución)"; continue; fi
  echo "--- identidad y capacidades del proceso 1:"
  ejec "$svc" 'id; grep -E "^(Uid|Gid|CapEff|CapBnd|NoNewPrivs|Seccomp):" /proc/1/status; echo "proceso 1: $(tr "\0" " " < /proc/1/cmdline)"' 
  echo "--- directorios escribibles por cualquiera dentro del contenedor (debe ser vacío salvo /tmp):"
  ejec "$svc" 'find / -xdev -type d -perm -0002 2>/dev/null | grep -v "^/proc\|^/sys\|^/dev" | head -n 10'
  echo "--- versiones de librerías críticas:"
  ejec "$svc" 'if command -v dpkg-query >/dev/null; then dpkg-query -W -f="\${Package} \${Version}\n" openssl libssl3t64 libssl3 zlib1g unixodbc msodbcsql18 2>/dev/null; elif command -v apk >/dev/null; then apk info -v 2>/dev/null | grep -E "^(musl|openssl|libcrypto|zlib|nginx|caddy)"; fi'
done

sec "backend: paquetes Python instalados (comparar con backend/requirements.txt)"
ejec backend 'python -c "import sys; print(sys.version)"; python -m pip list --format=freeze 2>/dev/null | head -n 80'

sec "frontend (Nginx): versión y configuración efectiva (sin secretos)"
ejec frontend 'nginx -v 2>&1; nginx -T 2>/dev/null | grep -nE "server_tokens|listen |client_max_body_size|proxy_pass|add_header Content-Security|Strict-Transport|Cross-Origin|error_page|return 404"'

sec "proxy (Caddy, solo perfil https): versión y reglas"
ejec proxy 'caddy version 2>&1; caddy adapt --config /etc/caddy/Caddyfile --adapter caddyfile 2>/dev/null | head -n 60' 

sec "db (SQL Server en contenedor, solo perfil db): versión del motor (sin consultas de datos)"
ejec db '/opt/mssql/bin/sqlservr -v 2>/dev/null | head -n 3 || echo "(versión por sqlcmd: ver 04_sqlserver.sh)"'

echo
echo "Fin del diagnóstico de contenedores. Enviar la salida completa (sin editarla) para el análisis."
