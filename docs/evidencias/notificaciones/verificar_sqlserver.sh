# Verificaciones de la migración y los permisos de Notificaciones sobre SQL Server real (instancia descartable). Requiere env.sh del ensayo
# (funciones sq/sqa/sqj: sqlcmd como sa / glucolume_app / glucolume_jobs) y haber corrido rebuild.sh (esquema anterior + datos heredados + v2).
echo "== 1. columnas, índice y tabla nuevos"
sq -d GlucoLume -h -1 -W -Q "SET NOCOUNT ON; SELECT name FROM sys.columns WHERE object_id=OBJECT_ID('dbo.NotificacionUsuario') AND name IN ('claveEvento','visible','estadoCorreo','intentosCorreo') ORDER BY name; SELECT name FROM sys.indexes WHERE name='UX_NotificacionUsuario_clave'; SELECT name FROM sys.tables WHERE name='AccesoConocido'"
echo "== 2. datos heredados: clave LEGADO y fecha corregida -3 h (sembrada 19:00/19:30/20:00 UTC)"
sq -d GlucoLume -W -Q "SET NOCOUNT ON; SELECT evento, CONVERT(varchar(19),fechaCreacion,126) AS fechaArgentina, LEFT(claveEvento,7) AS clave FROM dbo.NotificacionUsuario WHERE claveEvento LIKE 'LEGADO:%' ORDER BY fechaCreacion"
echo "== 3. la preferencia de NUEVA_ACCION_GRUPO se copió a MEDICION_GRUPO"
sq -d GlucoLume -W -Q "SET NOCOUNT ON; SELECT evento, enPagina, porCorreo FROM dbo.PreferenciaNotificacion ORDER BY evento"
echo "== 4. segunda ejecución de v2 (idempotencia): sin errores y las fechas no vuelven a restarse"
sq -d GlucoLume -i /tmp/notif_v2.sql -v CONFIRMAR=ACTUALIZAR_NOTIFICACIONES_V2 > /dev/null 2>&1; echo "exit=$?"
sq -d GlucoLume -W -Q "SET NOCOUNT ON; SELECT CONVERT(varchar(19),fechaCreacion,126) AS fechaArgentina FROM dbo.NotificacionUsuario WHERE claveEvento LIKE 'LEGADO:%' ORDER BY fechaCreacion"
echo "== 5. sin CONFIRMAR exacto no hace nada"
sq -d GlucoLume -i /tmp/notif_v2.sql -v CONFIRMAR=NO 2>&1 | tail -2
echo "== 6. cuenta de la API: INSERT/SELECT/UPDATE sí, DELETE no, clave duplicada rechazada"
sqa -W -Q "SET NOCOUNT ON; INSERT INTO dbo.NotificacionUsuario (idUsuario, evento, titulo, mensaje, claveEvento, fechaCreacion) VALUES ('11111111-1111-4111-8111-111111111111', N'CAMBIO_MFA', N't', N'm', N'verif:1', SYSDATETIME()); UPDATE dbo.NotificacionUsuario SET fechaLectura = SYSDATETIME() WHERE claveEvento = N'verif:1'; PRINT 'insert/select/update ok'"
sqa -W -Q "DELETE FROM dbo.NotificacionUsuario WHERE claveEvento = N'verif:1'" 2>&1 | head -2
sqa -W -Q "INSERT INTO dbo.NotificacionUsuario (idUsuario, evento, titulo, mensaje, claveEvento, fechaCreacion) VALUES ('11111111-1111-4111-8111-111111111111', N'CAMBIO_MFA', N't', N'm', N'verif:1', SYSDATETIME())" 2>&1 | head -2
echo "== 7. cuenta de procesos: DELETE sobre NotificacionUsuario sí; sobre otra tabla no"
sqj -W -Q "DELETE FROM dbo.NotificacionUsuario WHERE claveEvento = N'verif:1'; PRINT 'jobs delete ok'"
sqj -W -Q "DELETE TOP (0) FROM dbo.Institucion" 2>&1 | head -2
echo "== 8. valor no permitido en evento / estadoCorreo rechazado por el CHECK"
sq -d GlucoLume -W -Q "INSERT INTO dbo.NotificacionUsuario (idUsuario, evento, titulo, mensaje, fechaCreacion) VALUES ('11111111-1111-4111-8111-111111111111', N'OTRO', N't', N'm', SYSDATETIME())" 2>&1 | head -2
sq -d GlucoLume -W -Q "INSERT INTO dbo.NotificacionUsuario (idUsuario, evento, titulo, mensaje, fechaCreacion, estadoCorreo) VALUES ('11111111-1111-4111-8111-111111111111', N'CAMBIO_MFA', N't', N'm', SYSDATETIME(), N'QUIEN_SABE')" 2>&1 | head -2
