-- GlucoLume - Cifrado en reposo (TDE), respaldo cifrado y restauración de prueba (GL-07)
--
-- PREPARADO. Ensayado el 19/10/2026 en un SQL Server 2022 Developer descartable (contenedor sin volúmenes). Aplicarlo en la instancia real
-- requiere autorización expresa y quien administra SQL Server: crea claves y certificados en master que, si se pierden, hacen IRRECUPERABLES
-- la base y sus respaldos. TDE está disponible en SQL Server 2019+ Standard/Enterprise/Developer; no en Express.
-- La instancia instalada el 19/10/2026 es SQL Server 2025 EXPRESS: no admite TDE ni respaldos cifrados ni comprimidos, así que este
-- script NO se puede aplicar ahí. Alternativa para Express (docs/BASE_DE_DATOS.md §4): BitLocker en el volumen de datos y de respaldos,
-- BACKUP ... WITH CHECKSUM, cifrado del .bak con una herramienta del sistema antes de sacarlo del equipo y restauración de prueba mensual en
-- una instancia descartable.
--
-- Uso (sqlcmd; en SSMS activar el modo SQLCMD):
--   sqlcmd -S <servidor> -i GlucoLume_cifrado_y_respaldo.sql -v BASE="<base>" DIR_RESPALDO="<carpeta del servidor>" ^
--          CLAVE_CERTIFICADOS="<contraseña fuerte para exportar los certificados>" CONFIRMAR="CIFRAR_Y_RESPALDAR_GLUCOLUME"
--
-- Hace, en orden: (1) clave maestra de master y dos certificados (TDE y respaldos) si no existen; (2) respalda los certificados con su clave
-- privada en DIR_RESPALDO (GUARDARLOS FUERA DEL SERVIDOR, junto con CLAVE_CERTIFICADOS); (3) activa TDE en BASE; (4) respaldo completo
-- comprimido, con CHECKSUM y cifrado AES-256; (5) RESTORE VERIFYONLY; (6) restaura una copia BASE_RestauracionPrueba, compara la cantidad
-- de filas de cada tabla con la original y la borra. No toca datos de BASE.
--
-- Retención de respaldos (política propuesta, a aprobar): completos diarios 35 días, mensuales 12 meses; una restauración de prueba por
-- mes con este mismo procedimiento. La retención la aplica el sistema de respaldos del servidor, no este script.

:on error exit

IF N'$(CONFIRMAR)' <> N'CIFRAR_Y_RESPALDAR_GLUCOLUME' OR DB_ID(N'$(BASE)') IS NULL
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="CIFRAR_Y_RESPALDAR_GLUCOLUME" o la base BASE no existe: no se hizo nada.', 16, 1);
    SET NOEXEC ON;
END
GO

USE master;
GO

IF NOT EXISTS (SELECT 1 FROM sys.symmetric_keys WHERE name = N'##MS_DatabaseMasterKey##')
    CREATE MASTER KEY ENCRYPTION BY PASSWORD = N'$(CLAVE_CERTIFICADOS)';
IF NOT EXISTS (SELECT 1 FROM sys.certificates WHERE name = N'GlucoLume_TDE')
    CREATE CERTIFICATE GlucoLume_TDE WITH SUBJECT = N'GlucoLume - cifrado en reposo (TDE)';
IF NOT EXISTS (SELECT 1 FROM sys.certificates WHERE name = N'GlucoLume_Respaldos')
    CREATE CERTIFICATE GlucoLume_Respaldos WITH SUBJECT = N'GlucoLume - respaldos cifrados';
GO

-- Sin estos archivos (y CLAVE_CERTIFICADOS) no se puede restaurar en otro servidor.
BACKUP CERTIFICATE GlucoLume_TDE TO FILE = N'$(DIR_RESPALDO)/GlucoLume_TDE.cer'
    WITH PRIVATE KEY (FILE = N'$(DIR_RESPALDO)/GlucoLume_TDE.pvk', ENCRYPTION BY PASSWORD = N'$(CLAVE_CERTIFICADOS)');
BACKUP CERTIFICATE GlucoLume_Respaldos TO FILE = N'$(DIR_RESPALDO)/GlucoLume_Respaldos.cer'
    WITH PRIVATE KEY (FILE = N'$(DIR_RESPALDO)/GlucoLume_Respaldos.pvk', ENCRYPTION BY PASSWORD = N'$(CLAVE_CERTIFICADOS)');
GO

USE [$(BASE)];
GO
IF NOT EXISTS (SELECT 1 FROM sys.dm_database_encryption_keys WHERE database_id = DB_ID())
    CREATE DATABASE ENCRYPTION KEY WITH ALGORITHM = AES_256 ENCRYPTION BY SERVER CERTIFICATE GlucoLume_TDE;
GO
USE master;
GO
ALTER DATABASE [$(BASE)] SET ENCRYPTION ON;
GO
-- El cifrado inicial corre en segundo plano: se espera a que termine (estado 3 = cifrada).
DECLARE @intentos int = 0;
WHILE NOT EXISTS (SELECT 1 FROM sys.dm_database_encryption_keys WHERE database_id = DB_ID(N'$(BASE)') AND encryption_state = 3)
      AND @intentos < 600
BEGIN
    WAITFOR DELAY '00:00:01';
    SET @intentos += 1;
END
SELECT DB_NAME(database_id) AS base, encryption_state AS estadoCifrado, key_algorithm, key_length
FROM sys.dm_database_encryption_keys WHERE database_id = DB_ID(N'$(BASE)');
GO

DECLARE @archivo nvarchar(400) = N'$(DIR_RESPALDO)/$(BASE)_' + FORMAT(SYSUTCDATETIME(), 'yyyyMMdd_HHmmss') + N'.bak';
BACKUP DATABASE [$(BASE)] TO DISK = @archivo
    WITH COMPRESSION, CHECKSUM, INIT, ENCRYPTION (ALGORITHM = AES_256, SERVER CERTIFICATE = GlucoLume_Respaldos);
RESTORE VERIFYONLY FROM DISK = @archivo WITH CHECKSUM;

-- Restauración de prueba con otro nombre y archivos propios.
DECLARE @datos nvarchar(400) = CAST(SERVERPROPERTY('InstanceDefaultDataPath') AS nvarchar(400));
DECLARE @log nvarchar(400) = CAST(SERVERPROPERTY('InstanceDefaultLogPath') AS nvarchar(400));
DECLARE @logico_datos sysname = (SELECT name FROM sys.master_files WHERE database_id = DB_ID(N'$(BASE)') AND type = 0);
DECLARE @logico_log sysname = (SELECT name FROM sys.master_files WHERE database_id = DB_ID(N'$(BASE)') AND type = 1);
DECLARE @mover_datos nvarchar(400) = @datos + N'$(BASE)_RestauracionPrueba.mdf';
DECLARE @mover_log nvarchar(400) = @log + N'$(BASE)_RestauracionPrueba.ldf';
IF DB_ID(N'$(BASE)_RestauracionPrueba') IS NOT NULL
BEGIN
    RAISERROR(N'Ya existe $(BASE)_RestauracionPrueba: revisarla y borrarla a mano antes de repetir.', 16, 1);
    RETURN;
END
RESTORE DATABASE [$(BASE)_RestauracionPrueba] FROM DISK = @archivo
    WITH CHECKSUM, MOVE @logico_datos TO @mover_datos, MOVE @logico_log TO @mover_log;
GO

-- Comparación de filas por tabla entre la base y su restauración (debe salir vacía).
DECLARE @sql nvarchar(max) = N'';
SELECT @sql += N'SELECT N''' + t.name + N''' AS tabla, (SELECT COUNT_BIG(*) FROM [$(BASE)].dbo.' + QUOTENAME(t.name)
             + N') AS original, (SELECT COUNT_BIG(*) FROM [$(BASE)_RestauracionPrueba].dbo.' + QUOTENAME(t.name) + N') AS restaurada UNION ALL '
FROM [$(BASE)].sys.tables AS t WHERE t.is_ms_shipped = 0;
SET @sql = N'SELECT tabla, original, restaurada FROM (' + LEFT(@sql, LEN(@sql) - LEN(N' UNION ALL')) + N') AS x WHERE original <> restaurada;';
EXEC sys.sp_executesql @sql;
SELECT N'Restauración de prueba completa' AS resultado,
       (SELECT COUNT(*) FROM [$(BASE)_RestauracionPrueba].sys.tables) AS tablasRestauradas;
GO

-- Solo se borra la COPIA de prueba (nunca BASE).
ALTER DATABASE [$(BASE)_RestauracionPrueba] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
DROP DATABASE [$(BASE)_RestauracionPrueba];
GO

SET NOEXEC OFF;
GO
