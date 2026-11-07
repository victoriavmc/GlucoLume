#!/usr/bin/env bash
# Rutas de la SPA y respuestas de la API (B-2, auditoría 07/11/2026). Solo lectura. No usar contra producción.
#
# Uso: sondas_rutas_spa.sh [URL_BASE]   (por defecto http://127.0.0.1:8080). Imprime código, tipo y si el cuerpo es la shell de la SPA.
# Antes (HEAD): todas las rutas desconocidas y sensibles dan 200 con la shell. Después: 404, y las rutas válidas no cambian.
BASE="${1:-http://127.0.0.1:8080}"
rutas=(/ /login /LOGIN/ /registro /privacidad /caracteristicas /ayuda /consejos /consejos/abc
  /recuperar-contrasena /restablecer-contrasena /verificar-correo /activar-cuenta /confirmar-correo-resultados
  /auth/google/callback /cuenta/eliminar/confirmar /cuenta/seguridad /cuenta/notificaciones/desuscribir
  /administracion/activar /administracion/login /administracion/xyz /plataforma/login /plataforma/dashboard /plataforma/xyz
  /app /app/inicio /app/mediciones/abc /app/grupo/abc/configuracion /APP/inicio
  /nonexistent-xyz /phpinfo.php /.git/config /app/.git/config /.env /config.php.bak /backup.sql /gallery.html /cuenta /wp-admin/
  /index.html /robots.txt /sitemap.xml /favicon.svg /assets/no-existe.js /ayuda/no-existe.png
  /api/v1/no-existe /api/v1/healthz /api/v1/readyz /api/v1/contact)
for r in "${rutas[@]}"; do
  out=$(curl -s -m 10 -o /tmp/claude-0/b2body -w '%{http_code} %{content_type}' -H "Host: glucolume-server.tailb27487.ts.net" "$BASE$r")
  if grep -q '<div id="root"' /tmp/claude-0/b2body 2>/dev/null; then shell="shell-SPA"; else shell="-"; fi
  printf '%-40s %-28s %s\n' "$r" "$out" "$shell"
done
