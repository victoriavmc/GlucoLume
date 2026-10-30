# Depuración física de avisos eliminados + compatibilidad con lifecycle (instancia descartable, tras e2e_delete.py). Requiere env.sh y las variables SP y WT.
RJ() { docker run --rm --env-file "$SP/it/backend.env" --add-host host.docker.internal:host-gateway -v "$WT/backend:/srv/backend:ro" glucolume/backend:dev python -m app.jobs.reminders "$@" 2>&1 | tail -2 | cut -c1-200; }
cnt() { sq -d GlucoLume -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM dbo.NotificacionUsuario" | tr -d '[:space:]'; }
echo "== filas por estado antes (eliminadas lógicamente / visibles / total)"
sq -d GlucoLume -W -Q "SET NOCOUNT ON; SELECT SUM(CASE WHEN fechaEliminacion IS NOT NULL THEN 1 ELSE 0 END) AS eliminadas, SUM(CASE WHEN fechaEliminacion IS NULL THEN 1 ELSE 0 END) AS visibles, COUNT(*) AS total FROM dbo.NotificacionUsuario"
echo "== se envejecen 2 eliminadas (40 días: vencidas para la depuración de leídos de 30) y 1 eliminada queda reciente"
sq -d GlucoLume -Q "SET NOCOUNT ON; WITH v AS (SELECT TOP (2) * FROM dbo.NotificacionUsuario WHERE claveEvento NOT LIKE 'masivo:%' AND fechaEliminacion IS NOT NULL ORDER BY fechaCreacion) UPDATE v SET fechaCreacion = DATEADD(day,-40,fechaCreacion), fechaEliminacion = DATEADD(day,-39,fechaEliminacion)"
AUD0=$(sq -d GlucoLume -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM dbo.Auditoria" | tr -d '[:space:]')
echo "== lifecycle completo (cuenta de procesos): no debe tocar ningún aviso"
N0=$(cnt); docker run --rm --env-file "$SP/it/backend.env" --add-host host.docker.internal:host-gateway -v "$WT/backend:/srv/backend:ro" glucolume/backend:dev python -m app.jobs.accountLifecycle 2>&1 | tail -1 | cut -c1-300; echo "avisos antes=$N0 después=$(cnt)"
echo "== depuración física con la cuenta de procesos"
echo "previsualizar: $(RJ previsualizar)"; echo "depurar:       $(RJ depurar)"
echo "avisos después de depurar: $(cnt) (solo salieron las 2 eliminadas vencidas)"
sq -d GlucoLume -W -Q "SET NOCOUNT ON; SELECT SUM(CASE WHEN fechaEliminacion IS NOT NULL THEN 1 ELSE 0 END) AS eliminadas, SUM(CASE WHEN fechaEliminacion IS NULL THEN 1 ELSE 0 END) AS visibles FROM dbo.NotificacionUsuario"
AUD1=$(sq -d GlucoLume -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM dbo.Auditoria" | tr -d '[:space:]'); echo "auditoría antes=$AUD0 después=$AUD1"
echo "== la cuenta de la API puede eliminar lógicamente (UPDATE) pero no borrar físicamente"
sqa -W -Q "SET NOCOUNT ON; UPDATE TOP (1) dbo.NotificacionUsuario SET fechaEliminacion = SYSDATETIME() WHERE fechaEliminacion IS NULL; PRINT 'update fechaEliminacion ok'"
sqa -W -Q "DELETE FROM dbo.NotificacionUsuario" 2>&1 | head -2
