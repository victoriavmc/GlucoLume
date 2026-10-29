-- GlucoLume - Actualización controlada de una base instalada: referencia de las matrices (dbo.Matriz)
--
-- Agrega a dbo.Matriz: urlReferencia (opcional: enlace a la fuente) y referenciaBase (obligatoria: de dónde se tomaron los criterios).
-- Las matrices que ya existían reciben referenciaBase = 'Sin registrar (matriz anterior)' para poder volver la columna NOT NULL.
-- Hay que completarla: en un BORRADOR, desde su pantalla (Datos del borrador); en una versión activada, inactiva o archivada,
-- creando una versión nueva (son inmutables).
-- Idempotente: lo que ya existe no se toca. No borra filas. Si alguna parte falla, la transacción se revierte entera.
--
-- Antes: respaldo restaurable (BACKUP ... WITH CHECKSUM + RESTORE VERIFYONLY) y este script probado en una copia restaurada.
--   sqlcmd -S <servidor> -d <base> -v CONFIRMAR="ACTUALIZAR_MATRIZ_REFERENCIA" -i GlucoLume_matriz_referencia.sql
-- Verificación después: python -m app.cli.schemaCheck (no debe informar diferencias en dbo.Matriz).
-- Reversión (no toca datos de otras columnas): ALTER TABLE dbo.Matriz DROP CONSTRAINT CK_Matriz_referenciaBase;
--   ALTER TABLE dbo.Matriz DROP COLUMN referenciaBase, urlReferencia;

:on error exit

IF N'$(CONFIRMAR)' <> N'ACTUALIZAR_MATRIZ_REFERENCIA' OR OBJECT_ID(N'dbo.Matriz') IS NULL
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="ACTUALIZAR_MATRIZ_REFERENCIA" o la base no tiene dbo.Matriz: no se hizo nada.', 16, 1);
    SET NOEXEC ON;
END
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF COL_LENGTH(N'dbo.Matriz', N'urlReferencia') IS NULL
    ALTER TABLE [dbo].[Matriz] ADD [urlReferencia] NVARCHAR(500) NULL;
IF COL_LENGTH(N'dbo.Matriz', N'referenciaBase') IS NULL
    ALTER TABLE [dbo].[Matriz] ADD [referenciaBase] NVARCHAR(200) NULL;
GO

-- Las filas anteriores no tienen fuente registrada: se marcan para completarlas antes de que la columna sea obligatoria.
UPDATE [dbo].[Matriz] SET [referenciaBase] = N'Sin registrar (matriz anterior)' WHERE [referenciaBase] IS NULL;
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.Matriz') AND name = N'referenciaBase' AND is_nullable = 1)
    ALTER TABLE [dbo].[Matriz] ALTER COLUMN [referenciaBase] NVARCHAR(200) NOT NULL;
GO

IF OBJECT_ID(N'dbo.CK_Matriz_referenciaBase', N'C') IS NULL
    ALTER TABLE [dbo].[Matriz] WITH CHECK ADD CONSTRAINT [CK_Matriz_referenciaBase]
        CHECK ([referenciaBase] <> N'');
GO

COMMIT TRANSACTION;
GO
