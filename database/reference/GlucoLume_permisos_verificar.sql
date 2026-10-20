-- GlucoLume - Verificacion NO destructiva de la proteccion de auditoria (GL-03)
--
-- Actua como la cuenta de la aplicacion (EXECUTE AS USER) y prueba, sin dejar cambios:
--   INSERT en Auditoria y AuditoriaContexto dentro de una transaccion que se revierte (debe poder);
--   UPDATE TOP (0) y DELETE TOP (0) en ambas tablas (no tocan filas; deben fallar con el error 229 si el DENY esta aplicado).
-- La cantidad de filas de la auditoria tiene que ser la misma al empezar y al terminar.
--   sqlcmd -S <servidor> -E -C -I -d <base> -i GlucoLume_permisos_verificar.sql -v API_LOGIN="glucolume_app"

SET NOCOUNT ON;
DECLARE @antes bigint = (SELECT COUNT_BIG(*) FROM dbo.Auditoria) + (SELECT COUNT_BIG(*) FROM dbo.AuditoriaContexto);
DECLARE @r TABLE (prueba nvarchar(60), resultado nvarchar(60));
DECLARE @id uniqueidentifier = NEWID();

EXECUTE AS USER = N'$(API_LOGIN)';
BEGIN TRANSACTION;
BEGIN TRY
    INSERT INTO dbo.Auditoria (idAuditoria, tipoEvento, accion, resultado, fechaHora)
    VALUES (@id, N'CRUD', N'VERIFICACION_PERMISOS', N'EXITO', SYSDATETIME());
    INSERT INTO dbo.AuditoriaContexto (idAuditoria) VALUES (@id);
    INSERT INTO @r VALUES (N'INSERT (Auditoria y contexto)', N'permitido');
END TRY
BEGIN CATCH
    INSERT INTO @r VALUES (N'INSERT (Auditoria y contexto)', N'rechazado ' + CONVERT(nvarchar(10), ERROR_NUMBER()));
END CATCH
ROLLBACK TRANSACTION;
BEGIN TRY UPDATE TOP (0) dbo.Auditoria SET observacion = observacion; INSERT INTO @r VALUES (N'UPDATE Auditoria', N'permitido'); END TRY
BEGIN CATCH INSERT INTO @r VALUES (N'UPDATE Auditoria', N'rechazado ' + CONVERT(nvarchar(10), ERROR_NUMBER())); END CATCH
BEGIN TRY DELETE TOP (0) FROM dbo.Auditoria; INSERT INTO @r VALUES (N'DELETE Auditoria', N'permitido'); END TRY
BEGIN CATCH INSERT INTO @r VALUES (N'DELETE Auditoria', N'rechazado ' + CONVERT(nvarchar(10), ERROR_NUMBER())); END CATCH
BEGIN TRY UPDATE TOP (0) dbo.AuditoriaContexto SET ipOrigen = ipOrigen; INSERT INTO @r VALUES (N'UPDATE AuditoriaContexto', N'permitido'); END TRY
BEGIN CATCH INSERT INTO @r VALUES (N'UPDATE AuditoriaContexto', N'rechazado ' + CONVERT(nvarchar(10), ERROR_NUMBER())); END CATCH
BEGIN TRY DELETE TOP (0) FROM dbo.AuditoriaContexto; INSERT INTO @r VALUES (N'DELETE AuditoriaContexto', N'permitido'); END TRY
BEGIN CATCH INSERT INTO @r VALUES (N'DELETE AuditoriaContexto', N'rechazado ' + CONVERT(nvarchar(10), ERROR_NUMBER())); END CATCH
REVERT;

SELECT prueba, resultado FROM @r;
SELECT N'Filas de auditoria sin cambios: ' + CASE WHEN @antes = (SELECT COUNT_BIG(*) FROM dbo.Auditoria) + (SELECT COUNT_BIG(*) FROM dbo.AuditoriaContexto)
       THEN N'SI' ELSE N'NO' END AS control;
