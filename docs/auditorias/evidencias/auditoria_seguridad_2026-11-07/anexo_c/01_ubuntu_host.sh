#!/usr/bin/env bash
# Anexo C (auditoría 07/11/2026). DIAGNÓSTICO DE SOLO LECTURA del host Ubuntu.
# No instala, no actualiza (no ejecuta apt-get update), no reinicia, no cambia el firewall ni Docker Compose.
# No imprime valores de secretos: solo nombres de variables, permisos y conteos.
#
# Uso (en el servidor, con sudo para ver sshd, ufw, nft y los logs de autenticación):
#   sudo bash 01_ubuntu_host.sh [RUTA_DEL_REPO] 2>&1 | tee "$HOME/diag_01_host_$(date +%F).txt"
REPO="${1:-$HOME/GlucoLume}"
sec() { printf '\n===== %s =====\n' "$1"; }
existe() { command -v "$1" >/dev/null 2>&1; }

sec "1. Sistema, kernel y actualizaciones"
hostnamectl 2>/dev/null | grep -Ev '^\s*(Machine ID|Boot ID)'
grep -E '^(PRETTY_NAME|VERSION_ID|VERSION_CODENAME)=' /etc/os-release
uname -r
echo "uptime: $(uptime -p 2>/dev/null)"
if [ -f /var/run/reboot-required ]; then echo "reinicio pendiente: SÍ ($(cat /var/run/reboot-required.pkgs 2>/dev/null | tr '\n' ' '))"; else echo "reinicio pendiente: no"; fi
echo "--- paquetes actualizables según la caché actual de apt (sin apt-get update):"
apt list --upgradable 2>/dev/null | grep -v '^Listing' | head -n 80
echo "--- de los cuales, de seguridad (origen -security o esm):"
apt list --upgradable 2>/dev/null | grep -Ei 'security|esm' | head -n 80 || true
echo "--- actualizaciones automáticas:"
for unidad in unattended-upgrades apt-daily-upgrade.timer; do
  echo "$unidad: habilitado=$(systemctl is-enabled $unidad 2>/dev/null) activo=$(systemctl is-active $unidad 2>/dev/null)"
done
grep -hE '^APT::Periodic::(Update-Package-Lists|Unattended-Upgrade)' /etc/apt/apt.conf.d/20auto-upgrades 2>/dev/null
echo "--- orígenes habilitados en unattended-upgrades:"
grep -A10 'Allowed-Origins' /etc/apt/apt.conf.d/50unattended-upgrades 2>/dev/null | grep -v '^\s*//' | grep -v '^$' | head -n 12
echo "--- últimas ejecuciones:"
tail -n 5 /var/log/unattended-upgrades/unattended-upgrades.log 2>/dev/null || echo "(sin registro)"
existe ubuntu-security-status && ubuntu-security-status 2>/dev/null | head -n 20
existe needrestart && needrestart -b 2>/dev/null | head -n 25

sec "5. Puertos escuchando y procesos (0.0.0.0 y :: = expuesto)"
ss -tulpn 2>/dev/null
echo "--- direcciones del equipo:"
ip -brief address 2>/dev/null

sec "5b. Firewall (UFW y reglas de Docker)"
if existe ufw; then ufw status verbose 2>/dev/null; else echo "ufw no instalado"; fi
echo "--- cadena DOCKER-USER (reglas propias que filtran puertos publicados por Docker):"
iptables -S DOCKER-USER 2>/dev/null || echo "(no disponible)"
echo "--- puertos publicados por Docker en iptables NAT:"
iptables -t nat -S DOCKER 2>/dev/null | grep -- '--dport' || echo "(ninguno o sin permisos)"
echo "--- nftables (resumen):"
nft list ruleset 2>/dev/null | grep -E 'table|chain|policy|dport' | head -n 60 || echo "(sin nft o sin permisos)"

sec "7. Tailscale (acceso remoto y Serve)"
if existe tailscale; then
  tailscale version 2>/dev/null | head -n 1
  echo "--- estado:"; tailscale status 2>/dev/null | head -n 20
  echo "--- Serve (qué rutas publica el tailnet):"; tailscale serve status 2>/dev/null || echo "(sin Serve configurado o sin permisos)"
  echo "--- Funnel (publica en Internet abierta; debe NO estar activo):"; tailscale funnel status 2>/dev/null || echo "(sin Funnel)"
  echo "--- preferencias relevantes (RunSSH, ShieldsUp, ExitNode, rutas anunciadas):"
  tailscale debug prefs 2>/dev/null | grep -E '"(RunSSH|ShieldsUp|ExitNodeID|AdvertiseRoutes|RouteAll|CorpDNS|RunWebClient)"' || echo "(no disponible)"
  echo "MANUAL: en la consola de administración de Tailscale revisar ACL (quién llega a este equipo y a qué puerto), claves de nodo sin expirar en el equipo del servidor, y que ninguna otra persona tenga rol de administrador innecesario."
else echo "tailscale no instalado"; fi

sec "8. SSH"
if existe sshd; then
  sshd -T 2>/dev/null | grep -Ei '^(port|permitrootlogin|passwordauthentication|kbdinteractiveauthentication|pubkeyauthentication|permitemptypasswords|allowusers|allowgroups|maxauthtries|x11forwarding|usepam|permituserenvironment) ' || echo "(sshd -T requiere sudo)"
  systemctl is-active ssh 2>/dev/null || systemctl is-active sshd 2>/dev/null
else echo "sshd no instalado"; fi
echo "fail2ban: $(systemctl is-active fail2ban 2>/dev/null)"
echo "--- intentos fallidos de SSH, últimos 7 días (conteo):"
journalctl -u ssh -u sshd --since '7 days ago' --no-pager 2>/dev/null | grep -c 'Failed password\|Invalid user' || echo "(sin journal)"
echo "--- inicios de sesión aceptados recientes (usuario y origen; sin contraseñas):"
journalctl -u ssh -u sshd --since '7 days ago' --no-pager 2>/dev/null | grep 'Accepted ' | awk '{for(i=1;i<=NF;i++) if($i=="for"){u=$(i+1)} for(i=1;i<=NF;i++) if($i=="from"){o=$(i+1)} print u, o}' | sort | uniq -c | head -n 20
echo "--- cuentas humanas y cantidad de claves autorizadas (sin mostrar las claves):"
awk -F: '$3>=1000 && $7 !~ /(nologin|false)$/ {print $1}' /etc/passwd | while read -r u; do
  h=$(getent passwd "$u" | cut -d: -f6); n=$(wc -l < "$h/.ssh/authorized_keys" 2>/dev/null || echo 0)
  echo "usuario=$u claves_autorizadas=$n grupos=$(id -nG "$u" | tr ' ' ',')"
done
echo "--- cuentas con sudo (grupo sudo/admin y /etc/sudoers.d):"
getent group sudo admin 2>/dev/null
ls -l /etc/sudoers.d 2>/dev/null

sec "9. Secretos y acceso a Docker (solo nombres y permisos)"
getent group docker || echo "(grupo docker no existe)"
if [ -d "$REPO" ]; then
  stat -c '%U:%G %a %n' "$REPO/.env" "$REPO/docker/db.env" "$REPO/docker/certs" "$REPO/docker/certs"/* 2>/dev/null
  if [ -f "$REPO/.env" ]; then
    echo "variables definidas en .env (solo nombres):"; grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$REPO/.env" | cut -d= -f1 | sort | tr '\n' ' '; echo
    echo "variables repetidas en .env (la última gana):"; grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$REPO/.env" | cut -d= -f1 | sort | uniq -d
    echo "longitud de SESSION_SECRET (>= 32 esperado): $(awk -F= '/^SESSION_SECRET=/{print length($2)}' "$REPO/.env")"
    echo "valores de ejemplo sin cambiar (solo el nombre de la variable):"
    grep -iE '=(changeme|cambiar|example|ejemplo|password|secret|test|todo)' "$REPO/.env" | cut -d= -f1
    echo "DATABASE_URL presente (no debe, ver config.py): $(grep -c '^DATABASE_URL=' "$REPO/.env")"
    echo "FRONTEND_BIND: $(grep -E '^FRONTEND_BIND=' "$REPO/.env" | cut -d= -f2)  (debe ser 127.0.0.1 salvo decisión explícita)"
    echo "API_ENV: $(grep -E '^API_ENV=' "$REPO/.env" | cut -d= -f2)"
  else echo ".env no encontrado en $REPO"; fi
else echo "repo no encontrado: $REPO (pasar la ruta como argumento)"; fi
echo "--- historiales de shell con posibles contraseñas (solo nombres de archivo):"
for h in "$HOME/.bash_history" /root/.bash_history; do [ -f "$h" ] && grep -lE 'PASSWORD|SECRET|TOKEN' "$h" 2>/dev/null; done; echo "(fin)"

sec "10b. Cifrado del disco (es una notebook: pérdida o robo del equipo)"
lsblk -o NAME,TYPE,FSTYPE,MOUNTPOINT 2>/dev/null
if lsblk -o TYPE 2>/dev/null | grep -qx crypt; then echo "hay volúmenes cifrados (crypt)"; else echo "NO se detectan volúmenes cifrados (LUKS): confirmar con el administrador"; fi
existe cryptsetup && cryptsetup status $(lsblk -o NAME,TYPE 2>/dev/null | awk '$2=="crypt"{print $1}' | head -n 1) 2>/dev/null | head -n 5

sec "10. Permisos, volúmenes, espacio y copias de seguridad"
ls -ld /var/lib/docker /var/lib/docker/volumes 2>/dev/null
df -h / /var/lib/docker 2>/dev/null
if [ -d "$REPO" ]; then
  echo "archivos del repo con escritura para todos (excluido .git):"
  find "$REPO" -path "$REPO/.git" -prune -o -type f -perm -0002 -print 2>/dev/null | head -n 20
fi
echo "--- trabajos programados que mencionan base, volúmenes o respaldos:"
grep -rlEi 'mssql|docker volume|backup|respaldo|pg_dump|sqlcmd' /etc/cron* /etc/systemd/system 2>/dev/null || echo "(ninguno encontrado en /etc)"
crontab -l 2>/dev/null | grep -v '^#' | head -n 20
systemctl list-timers --all --no-pager 2>/dev/null | head -n 25
echo "MANUAL: confirmar dónde está el último respaldo de la base (volumen mssql-data o copia) y su fecha de restauración de prueba."

sec "12. Logs y retención"
journalctl --disk-usage 2>/dev/null
grep -E '^\s*(Storage|SystemMaxUse|MaxRetentionSec|SystemKeepFree)' /etc/systemd/journald.conf 2>/dev/null || echo "journald.conf: valores por defecto"
du -sh /var/log 2>/dev/null

echo
echo "Fin del diagnóstico del host. Enviar la salida completa (sin editarla) para el análisis."
