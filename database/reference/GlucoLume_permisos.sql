-- GlucoLume - Permisos de minimo privilegio en la base (GL-03)
--
-- No forma parte del esquema (GlucoLume_DB_v5.sql): asigna permisos a cuentas que ya existen en la instancia. Idempotente: repetirlo no
-- cambia nada. Probarlo primero en una copia restaurada; antes de aplicarlo en la base real, respaldo verificado.
-- Requisito: el backend desplegado no debe hacer UPDATE/DELETE sobre la auditoria (imagen del 19/10/2026 o posterior): una imagen
-- anterior deja de poder iniciar sesion con el DENY (comprobado en ensayo).
--
-- Separa dos cuentas:
--   API       (DB_USER)      lee y escribe los datos de la aplicacion, pero NO puede modificar ni borrar la auditoria:
--                             DENY UPDATE, DELETE sobre dbo.Auditoria y dbo.AuditoriaContexto (solo agrega eventos).
--   Retencion (DB_JOBS_USER) OPCIONAL: la usan el servicio «lifecycle» y los jobs de backend/app/jobs para depurar eventos vencidos
--                             (backend/app/services/auditRetention.py). Con JOBS_LOGIN="NINGUNA" el rol se crea vacio y no hace falta
--                             ninguna cuenta ni contrasena nueva (lifecycle desactivado). sqlcmd no acepta -v vacio: usar JOBS_LOGIN="NINGUNA".
-- Ninguna de las dos es db_owner ni puede cambiar el esquema (sin ALTER/CONTROL). Las contrasenas nunca van en este archivo.
--
-- Uso (sqlcmd con -I: los indices filtrados exigen QUOTED_IDENTIFIER ON):
--   sqlcmd -S <servidor> -E -C -I -d <base> -i GlucoLume_permisos.sql ^
--          -v API_LOGIN="glucolume_app" JOBS_LOGIN="NINGUNA" CONFIRMAR="APLICAR_PERMISOS_GLUCOLUME"
-- Sin CONFIRMAR exacto no se ejecuta nada. Reversion: GlucoLume_permisos_revertir.sql (no toca datos).

:on error exit

IF N'$(CONFIRMAR)' <> N'APLICAR_PERMISOS_GLUCOLUME'
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="APLICAR_PERMISOS_GLUCOLUME": no se aplico ningun permiso.', 16, 1);
    SET NOEXEC ON;
END
GO

IF SUSER_ID(N'$(API_LOGIN)') IS NULL
   OR (N'$(JOBS_LOGIN)' NOT IN (N'', N'NINGUNA') AND (SUSER_ID(N'$(JOBS_LOGIN)') IS NULL OR N'$(API_LOGIN)' = N'$(JOBS_LOGIN)'))
BEGIN
    RAISERROR(N'API_LOGIN debe existir; JOBS_LOGIN, si se indica, debe existir y ser distinta.', 16, 1);
    SET NOEXEC ON;
END
GO

-- Un sysadmin (o el dueño de la base) no queda alcanzado por ningun DENY: esto no se puede corregir desde la base.
IF IS_SRVROLEMEMBER(N'sysadmin', N'$(API_LOGIN)') = 1
   OR EXISTS (SELECT 1 FROM sys.databases WHERE name = DB_NAME() AND SUSER_SNAME(owner_sid) = N'$(API_LOGIN)')
BEGIN
    RAISERROR(N'La cuenta de la API es sysadmin o duena de la base: quitar ese privilegio en la instancia antes de seguir.', 16, 1);
    SET NOEXEC ON;
END
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF DATABASE_PRINCIPAL_ID(N'$(API_LOGIN)') IS NULL
    EXEC (N'CREATE USER ' + N'[$(API_LOGIN)]' + N' FOR LOGIN [$(API_LOGIN)] WITH DEFAULT_SCHEMA = dbo;');

IF DATABASE_PRINCIPAL_ID(N'rol_glucolume_api') IS NULL
    CREATE ROLE rol_glucolume_api AUTHORIZATION dbo;
IF DATABASE_PRINCIPAL_ID(N'rol_glucolume_retencion') IS NULL
    CREATE ROLE rol_glucolume_retencion AUTHORIZATION dbo;

-- Datos de la aplicacion: lectura, alta, cambio y baja sobre el esquema dbo; procedimientos (usp_GlucoLume_*).
GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE ON SCHEMA::dbo TO rol_glucolume_api;
GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE ON SCHEMA::dbo TO rol_glucolume_retencion;

-- Auditoria de solo agregado para la API. DENY prevalece sobre el GRANT del esquema y sobre db_datawriter.
DENY UPDATE, DELETE ON OBJECT::dbo.Auditoria TO rol_glucolume_api;
DENY UPDATE, DELETE ON OBJECT::dbo.AuditoriaContexto TO rol_glucolume_api;

IF IS_ROLEMEMBER(N'rol_glucolume_api', N'$(API_LOGIN)') = 0
    EXEC (N'ALTER ROLE rol_glucolume_api ADD MEMBER [$(API_LOGIN)];');
-- db_owner ignora los DENY: si la cuenta lo era, se quita (db_datareader/db_datawriter no anulan el DENY).
IF IS_ROLEMEMBER(N'db_owner', N'$(API_LOGIN)') = 1
    EXEC (N'ALTER ROLE db_owner DROP MEMBER [$(API_LOGIN)];');

-- Cuenta de conservacion, solo si se indico (SQL dinamico: con NINGUNA no se ejecuta ninguna sentencia).
IF N'$(JOBS_LOGIN)' NOT IN (N'', N'NINGUNA')
BEGIN
    IF DATABASE_PRINCIPAL_ID(N'$(JOBS_LOGIN)') IS NULL
        EXEC (N'CREATE USER [$(JOBS_LOGIN)] FOR LOGIN [$(JOBS_LOGIN)] WITH DEFAULT_SCHEMA = dbo;');
    IF IS_ROLEMEMBER(N'rol_glucolume_retencion', N'$(JOBS_LOGIN)') = 0
        EXEC (N'ALTER ROLE rol_glucolume_retencion ADD MEMBER [$(JOBS_LOGIN)];');
    IF IS_ROLEMEMBER(N'db_owner', N'$(JOBS_LOGIN)') = 1
        EXEC (N'ALTER ROLE db_owner DROP MEMBER [$(JOBS_LOGIN)];');
END

COMMIT TRANSACTION;
GO

-- VERIFICACION: permisos efectivos sobre la auditoria (la API: solo SELECT e INSERT).
EXECUTE AS USER = N'$(API_LOGIN)';
SELECT N'API' AS cuenta, permission_name FROM fn_my_permissions(N'dbo.Auditoria', N'OBJECT') WHERE subentity_name = N''
UNION ALL
SELECT N'API (contexto)', permission_name FROM fn_my_permissions(N'dbo.AuditoriaContexto', N'OBJECT') WHERE subentity_name = N'';
REVERT;
IF N'$(JOBS_LOGIN)' NOT IN (N'', N'NINGUNA')
    EXEC (N'EXECUTE AS USER = N''$(JOBS_LOGIN)''; SELECT N''Retencion'' AS cuenta, permission_name
            FROM fn_my_permissions(N''dbo.Auditoria'', N''OBJECT'') WHERE subentity_name = N''''; REVERT;');
GO

SET NOEXEC OFF;
GO
