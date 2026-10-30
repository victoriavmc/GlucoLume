-- GlucoLume - Notificaciones v3: eliminación lógica de avisos de la bandeja. Se aplica sobre una base que ya tiene GlucoLume_notificaciones_v2.sql.
--
-- Qué hace (una transacción, sin borrar ni modificar ninguna fila):
--   NotificacionUsuario: agrega fechaEliminacion (datetime2(3) NULL). Es el tercer estado de un aviso, independiente de los otros dos:
--     fechaLectura (leído, todavía visible), fechaEliminacion (la persona lo quitó de SU bandeja) y visible (la cuenta apagó el canal de la página).
--     Un aviso eliminado deja de verse y de contarse, pero la fila se conserva con su claveEvento: el mismo hecho no vuelve a crear el aviso (un hecho
--     nuevo sí). La depuración física, con sus plazos de 30 y 365 días, la hace `python -m app.jobs.reminders depurar` (servicio «notifications»).
--   La auditoría (Auditoria, AuditoriaContexto) no se toca.
--
-- Idempotente: si la columna ya existe no se hace nada. Requiere permiso de DDL (la cuenta de la API no lo tiene: lo aplica quien administra la base).
-- No hacen falta permisos nuevos: la eliminación lógica es un UPDATE, que rol_glucolume_api ya tiene (GlucoLume_permisos.sql).
--
-- Antes: respaldo restaurable (BACKUP ... WITH CHECKSUM) y, si hay dudas, probar el script en una copia restaurada.
--   sqlcmd -S <servidor> -d <base> -I -i GlucoLume_notificaciones_v3.sql -v CONFIRMAR="ACTUALIZAR_NOTIFICACIONES_V3"
-- Reversión (se pierde quién eliminó qué; los avisos quedan todos visibles): ALTER TABLE dbo.NotificacionUsuario DROP COLUMN fechaEliminacion;
-- Mientras el script no se aplique, el backend nuevo deja «Notificaciones» como no disponible (schemaCompat) en lugar de fallar.

:on error exit

IF N'$(CONFIRMAR)' <> N'ACTUALIZAR_NOTIFICACIONES_V3' OR COL_LENGTH(N'dbo.NotificacionUsuario', N'claveEvento') IS NULL
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="ACTUALIZAR_NOTIFICACIONES_V3" o la base no tiene dbo.NotificacionUsuario.claveEvento (aplicar antes GlucoLume_notificaciones_v2.sql): no se hizo nada.', 16, 1);
    SET NOEXEC ON;
END
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF COL_LENGTH(N'dbo.NotificacionUsuario', N'fechaEliminacion') IS NULL
    ALTER TABLE [dbo].[NotificacionUsuario] ADD [fechaEliminacion] [datetime2](3) NULL;

COMMIT TRANSACTION;
GO

-- VERIFICACION: la columna debe existir y ningún aviso existente debe figurar como eliminado.
SELECT name FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.NotificacionUsuario') AND name = N'fechaEliminacion';
EXEC (N'SELECT COUNT(*) AS avisosEliminados FROM dbo.NotificacionUsuario WHERE fechaEliminacion IS NOT NULL;');
GO

SET NOEXEC OFF;
GO
