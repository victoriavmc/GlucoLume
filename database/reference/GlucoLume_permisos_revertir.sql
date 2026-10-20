-- GlucoLume - Reversion de GlucoLume_permisos.sql (GL-03)
--
-- Quita los miembros de rol_glucolume_api y rol_glucolume_retencion y borra ambos roles (con ellos se van sus GRANT y DENY). No toca
-- datos ni usuarios: la cuenta de la aplicacion conserva db_datareader/db_datawriter y vuelve a poder modificar la auditoria.
--   sqlcmd -S <servidor> -E -C -I -d <base> -i GlucoLume_permisos_revertir.sql -v CONFIRMAR="REVERTIR_PERMISOS_GLUCOLUME"

:on error exit

IF N'$(CONFIRMAR)' <> N'REVERTIR_PERMISOS_GLUCOLUME'
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="REVERTIR_PERMISOS_GLUCOLUME": no se revirtio nada.', 16, 1);
    SET NOEXEC ON;
END
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;
DECLARE @sql nvarchar(max) = N'';
SELECT @sql += N'ALTER ROLE ' + QUOTENAME(r.name) + N' DROP MEMBER ' + QUOTENAME(m.name) + N';'
FROM sys.database_role_members AS rm
JOIN sys.database_principals AS r ON r.principal_id = rm.role_principal_id
JOIN sys.database_principals AS m ON m.principal_id = rm.member_principal_id
WHERE r.name IN (N'rol_glucolume_api', N'rol_glucolume_retencion');
EXEC (@sql);
IF DATABASE_PRINCIPAL_ID(N'rol_glucolume_api') IS NOT NULL DROP ROLE rol_glucolume_api;
IF DATABASE_PRINCIPAL_ID(N'rol_glucolume_retencion') IS NOT NULL DROP ROLE rol_glucolume_retencion;
COMMIT TRANSACTION;
SELECT N'Roles de GlucoLume restantes: ' + CONVERT(nvarchar(5), COUNT(*)) FROM sys.database_principals WHERE name LIKE N'rol[_]glucolume%';
GO

SET NOEXEC OFF;
GO
