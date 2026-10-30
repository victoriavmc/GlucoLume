# Servicios y persistencia (instancia descartable). Requiere env.sh del ensayo y las variables SP (carpeta del ensayo) y WT (raíz del repositorio).
RJ() { docker run --rm --env-file "$SP/it/backend.env" --add-host host.docker.internal:host-gateway -v "$WT/backend:/srv/backend:ro" glucolume/backend:dev python -m app.jobs.reminders "$@" 2>&1 | tail -3 | cut -c1-200; }
echo "== A. persistencia: filas antes y después de reiniciar SQL Server y el backend"
sq -d GlucoLume -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM dbo.NotificacionUsuario; SELECT COUNT(*) FROM dbo.PreferenciaNotificacion" | tr '\n' ' '; echo
docker restart glucolume-notiftest-db > /dev/null; for i in $(seq 1 30); do sq -Q "SELECT 1" -h -1 > /dev/null 2>&1 && break; sleep 3; done; docker restart glucolume-notiftest-backend > /dev/null; sleep 12
sq -d GlucoLume -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM dbo.NotificacionUsuario; SELECT COUNT(*) FROM dbo.PreferenciaNotificacion" | tr '\n' ' '; echo
echo "== B. lifecycle (cuenta de procesos): una pasada en seco no elimina nada"
docker run --rm --env-file "$SP/it/backend.env" --add-host host.docker.internal:host-gateway -v "$WT/backend:/srv/backend:ro" glucolume/backend:dev python -m app.jobs.accountLifecycle --dry-run 2>&1 | tr -d '\n ' | cut -c1-200; echo
echo "== C. lifecycle con ACCOUNT_LIFECYCLE_INTERVAL_SECONDS=0 (como la instalación en uso): queda inactivo"
timeout 20 docker run --rm --env-file "$SP/it/backend.env" -e ACCOUNT_LIFECYCLE_INTERVAL_SECONDS=0 --add-host host.docker.internal:host-gateway -v "$WT/backend:/srv/backend:ro" glucolume/backend:dev python -m app.jobs.accountLifecycle --loop 2>&1 | head -2 | cut -c1-200
echo "== D. depuración con la cuenta de procesos: elimina solo lo vencido; la auditoría no cambia"
sq -d GlucoLume -i /tmp/seed_old.sql 2>/dev/null || { docker cp "$SP/it/seed_old.sql" $N:/tmp/seed_old.sql; sq -d GlucoLume -i /tmp/seed_old.sql; }
A0=$(sq -d GlucoLume -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM dbo.Auditoria" | tr -d '[:space:]')
echo "previsualizar: $(RJ previsualizar)"; echo "depurar:       $(RJ depurar)"
sq -d GlucoLume -W -Q "SET NOCOUNT ON; SELECT titulo FROM dbo.NotificacionUsuario WHERE claveEvento LIKE 'purga:%' ORDER BY claveEvento"
A1=$(sq -d GlucoLume -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM dbo.Auditoria" | tr -d '[:space:]'); echo "auditoría antes=$A0 después=$A1"
echo "== E. depuración con la cuenta de la API (sin DELETE): falla y no borra"
docker run --rm --env-file "$SP/it/backend.env" -e DB_JOBS_USER= -e DB_JOBS_PASSWORD= --add-host host.docker.internal:host-gateway -v "$WT/backend:/srv/backend:ro" glucolume/backend:dev python -m app.jobs.reminders depurar 2>&1 | grep -o "DELETE permission was denied[^\"]*" | head -1
echo "== F. servicio notifications: healthcheck y registro"
docker rm -f glucolume-notiftest-notifications > /dev/null 2>&1
docker run -d --name glucolume-notiftest-notifications --env-file "$SP/it/backend.env" -e NOTIFICATIONS_INTERVAL_SECONDS=10 --add-host host.docker.internal:host-gateway -v "$WT/backend:/srv/backend:ro" -v "$SP/it/smtp_cert.pem:/run/smtp_cert.pem:ro" glucolume/backend:dev python -m app.jobs.reminders --loop > /dev/null
docker exec glucolume-notiftest-notifications python -m app.jobs.reminders --health; echo "health recién arrancado exit=$?"
sq -d GlucoLume -i /tmp/due.sql; sleep 25; docker exec glucolume-notiftest-notifications python -m app.jobs.reminders --health; echo "health tras varias pasadas (con un recordatorio vencido en la base) exit=$?"
docker logs glucolume-notiftest-notifications 2>&1 | grep -v Deprecat | tail -3 | cut -c1-200
docker rm -f glucolume-notiftest-notifications > /dev/null
