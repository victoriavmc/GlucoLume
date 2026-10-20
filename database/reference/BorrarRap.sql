-- BorrarRap - BORRA TODOS LOS DATOS de una base (conserva tablas, claves y triggers). Solo para bases descartables de desarrollo o
-- pruebas. Sobre la base real hace falta autorizacion expresa y un respaldo verificado (GL-21).
--
-- Exige dos variables de sqlcmd iguales al nombre de la base conectada; sin ellas no borra nada. En SSMS sin modo SQLCMD tampoco:
-- el USE falla y la comparacion del lote siguiente termina antes de borrar.
--   sqlcmd -S <servidor> -d <base descartable> -i BorrarRap.sql -v BASE="<base descartable>" CONFIRMAR_BORRADO="<base descartable>"
USE [$(BASE)];
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;

IF N'$(BASE)' <> DB_NAME() OR N'$(CONFIRMAR_BORRADO)' <> DB_NAME()
BEGIN
    RAISERROR(N'BorrarRap: BASE y CONFIRMAR_BORRADO deben ser el nombre de la base conectada. No se borro nada.', 16, 1);
    RETURN;
END;

DECLARE @disableFK NVARCHAR(MAX) = N'';
DECLARE @enableFK NVARCHAR(MAX) = N'';
DECLARE @disableTriggers NVARCHAR(MAX) = N'';
DECLARE @enableTriggers NVARCHAR(MAX) = N'';
DECLARE @deleteSQL NVARCHAR(MAX) = N'';

-- Evitar ejecutar sobre tablas temporales del sistema
-- (system-versioned temporal tables).
IF EXISTS (
    SELECT 1
    FROM sys.tables
    WHERE temporal_type <> 0
      AND is_ms_shipped = 0
)
BEGIN
    THROW 50001,
        'Existen tablas temporales que requieren un tratamiento especial.',
        1;
END;

-- 1. Preparar claves foráneas originalmente habilitadas
SELECT
    @disableFK +=
        N'ALTER TABLE ' +
        QUOTENAME(OBJECT_SCHEMA_NAME(parent_object_id)) + N'.' +
        QUOTENAME(OBJECT_NAME(parent_object_id)) +
        N' NOCHECK CONSTRAINT ' + QUOTENAME(name) + N';' + CHAR(10),

    @enableFK +=
        N'ALTER TABLE ' +
        QUOTENAME(OBJECT_SCHEMA_NAME(parent_object_id)) + N'.' +
        QUOTENAME(OBJECT_NAME(parent_object_id)) +
        CASE
            WHEN is_not_trusted = 0
            THEN N' WITH CHECK CHECK CONSTRAINT '
            ELSE N' CHECK CONSTRAINT '
        END +
        QUOTENAME(name) + N';' + CHAR(10)
FROM sys.foreign_keys
WHERE is_disabled = 0;

-- 2. Preparar triggers originalmente habilitados
SELECT
    @disableTriggers +=
        N'DISABLE TRIGGER ' + QUOTENAME(tr.name) +
        N' ON ' + QUOTENAME(s.name) + N'.' +
        QUOTENAME(t.name) + N';' + CHAR(10),

    @enableTriggers +=
        N'ENABLE TRIGGER ' + QUOTENAME(tr.name) +
        N' ON ' + QUOTENAME(s.name) + N'.' +
        QUOTENAME(t.name) + N';' + CHAR(10)
FROM sys.triggers tr
INNER JOIN sys.tables t
    ON tr.parent_id = t.object_id
INNER JOIN sys.schemas s
    ON t.schema_id = s.schema_id
WHERE tr.is_disabled = 0
  AND tr.parent_class = 1
  AND tr.is_ms_shipped = 0;

-- 3. Preparar eliminación de registros
SELECT
    @deleteSQL +=
        N'DELETE FROM ' + QUOTENAME(s.name) + N'.' +
        QUOTENAME(t.name) + N';' + CHAR(10)
FROM sys.tables t
INNER JOIN sys.schemas s
    ON t.schema_id = s.schema_id
WHERE t.is_ms_shipped = 0;

-- 4. Ejecutar limpieza dentro de una transacción
BEGIN TRY
    BEGIN TRANSACTION;

    EXEC sp_executesql @disableFK;
    EXEC sp_executesql @disableTriggers;

    EXEC sp_executesql @deleteSQL;

    EXEC sp_executesql @enableTriggers;
    EXEC sp_executesql @enableFK;

    COMMIT TRANSACTION;

    PRINT 'Limpieza completada correctamente.';
    PRINT 'Se conservaron las tablas y sus estructuras.';
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;
GO