-- GlucoLume - Devuelve db_datareader / db_datawriter a la cuenta de la API (reversion de GlucoLume_permisos_quitar_roles_fijos.sql)
--
-- Lee la propiedad extendida GlucoLume_roles_fijos_quitados (login|roles) que dejo el script de quitar y vuelve a agregar SOLO esos roles a esa
-- cuenta. Si no hay propiedad no hace nada (nada que restaurar). Idempotente.
--   sqlcmd -S <servidor> -E -C -I -d <base> -i GlucoLume_permisos_restaurar_roles_fijos.sql -v CONFIRMAR="RESTAURAR_ROLES_FIJOS_GLUCOLUME"

:on error exit

IF N'$(CONFIRMAR)' <> N'RESTAURAR_ROLES_FIJOS_GLUCOLUME'
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="RESTAURAR_ROLES_FIJOS_GLUCOLUME": no se restauro nada.', 16, 1);
    SET NOEXEC ON;
END
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;
DECLARE @valor nvarchar(400) = CONVERT(nvarchar(400), (SELECT value FROM sys.extended_properties WHERE class = 0 AND name = N'GlucoLume_roles_fijos_quitados'));
IF @valor IS NULL OR CHARINDEX(N'|', @valor) = 0
BEGIN
    PRINT N'No hay roles fijos registrados como quitados: no se restauro nada.';
END
ELSE
BEGIN
    DECLARE @login sysname = LEFT(@valor, CHARINDEX(N'|', @valor) - 1);
    DECLARE @roles nvarchar(300) = SUBSTRING(@valor, CHARINDEX(N'|', @valor) + 1, 300);
    IF DATABASE_PRINCIPAL_ID(@login) IS NOT NULL
    BEGIN
        IF CHARINDEX(N'db_datawriter;', @roles) > 0 AND IS_ROLEMEMBER(N'db_datawriter', @login) = 0
            EXEC (N'ALTER ROLE db_datawriter ADD MEMBER ' + N'[' + @login + N'];');
        IF CHARINDEX(N'db_datareader;', @roles) > 0 AND IS_ROLEMEMBER(N'db_datareader', @login) = 0
            EXEC (N'ALTER ROLE db_datareader ADD MEMBER ' + N'[' + @login + N'];');
    END
    EXEC sys.sp_dropextendedproperty @name = N'GlucoLume_roles_fijos_quitados';
END
COMMIT TRANSACTION;
GO

SET NOEXEC OFF;
GO
