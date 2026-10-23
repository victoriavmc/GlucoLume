-- GlucoLume - Quita db_datareader y db_datawriter a la cuenta de la API (H-02, paso 2 del minimo privilegio; REVERSIBLE)
--
-- db_datawriter da INSERT, UPDATE y DELETE sobre TODAS las tablas y db_datareader da SELECT sobre todas: mientras la cuenta de la API siga en
-- esos roles fijos, el DELETE tabla por tabla de GlucoLume_permisos.sql no sirve de nada (el rol fijo lo concede igual; solo el DENY sobre la
-- auditoria sigue prevaleciendo). Este script los quita; lo que la API necesita lo concede rol_glucolume_api.
--
-- Requisitos: GlucoLume_permisos.sql ya aplicado (la cuenta es miembro de rol_glucolume_api). EJECUTARLO PRIMERO EN UNA COPIA RESTAURADA y
-- recorrer ahi la aplicacion (inicio de sesion, mediciones, cuentas, instituciones, puente) antes de hacerlo en la base real: si una operacion
-- necesitara un permiso que falta, falla con el error 229 y se corrige la lista de GlucoLume_permisos.sql, no se vuelve a dar db_datawriter.
-- Antes de la base real: respaldo verificado. Idempotente.
--   sqlcmd -S <servidor> -E -C -I -d <base> -i GlucoLume_permisos_quitar_roles_fijos.sql -v API_LOGIN="glucolume_app" CONFIRMAR="QUITAR_ROLES_FIJOS_GLUCOLUME"
-- Reversion (devuelve los roles que ESTE script quito, guardados en la propiedad extendida GlucoLume_roles_fijos_quitados):
--   sqlcmd -S <servidor> -E -C -I -d <base> -i GlucoLume_permisos_restaurar_roles_fijos.sql -v CONFIRMAR="RESTAURAR_ROLES_FIJOS_GLUCOLUME"

:on error exit

IF N'$(CONFIRMAR)' <> N'QUITAR_ROLES_FIJOS_GLUCOLUME'
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="QUITAR_ROLES_FIJOS_GLUCOLUME": no se quito ningun rol.', 16, 1);
    SET NOEXEC ON;
END
GO

IF DATABASE_PRINCIPAL_ID(N'$(API_LOGIN)') IS NULL OR IS_ROLEMEMBER(N'rol_glucolume_api', N'$(API_LOGIN)') <> 1
BEGIN
    RAISERROR(N'La cuenta no existe en la base o no es miembro de rol_glucolume_api: aplicar antes GlucoLume_permisos.sql.', 16, 1);
    SET NOEXEC ON;
END
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;
DECLARE @quitados nvarchar(300) = N'';
IF IS_ROLEMEMBER(N'db_datawriter', N'$(API_LOGIN)') = 1
BEGIN
    EXEC (N'ALTER ROLE db_datawriter DROP MEMBER [$(API_LOGIN)];');
    SET @quitados += N'db_datawriter;';
END
IF IS_ROLEMEMBER(N'db_datareader', N'$(API_LOGIN)') = 1
BEGIN
    EXEC (N'ALTER ROLE db_datareader DROP MEMBER [$(API_LOGIN)];');
    SET @quitados += N'db_datareader;';
END
IF @quitados <> N''
BEGIN
    -- Se guarda que se quito (y a quien) para poder devolverlo con GlucoLume_permisos_restaurar_roles_fijos.sql.
    IF EXISTS (SELECT 1 FROM sys.extended_properties WHERE class = 0 AND name = N'GlucoLume_roles_fijos_quitados')
        EXEC sys.sp_dropextendedproperty @name = N'GlucoLume_roles_fijos_quitados';
    DECLARE @valor nvarchar(400) = N'$(API_LOGIN)' + N'|' + @quitados;
    EXEC sys.sp_addextendedproperty @name = N'GlucoLume_roles_fijos_quitados', @value = @valor;
END
COMMIT TRANSACTION;
GO

-- VERIFICACION: la cuenta ya no debe figurar en ningun rol fijo de datos (ni en db_owner, db_ddladmin ni db_securityadmin).
SELECT r.name AS rolFijoQueConserva
FROM sys.database_role_members AS rm
JOIN sys.database_principals AS r ON r.principal_id = rm.role_principal_id
JOIN sys.database_principals AS m ON m.principal_id = rm.member_principal_id
WHERE m.name = N'$(API_LOGIN)' AND r.name <> N'rol_glucolume_api';
GO

SET NOEXEC OFF;
GO
