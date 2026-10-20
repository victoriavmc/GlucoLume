-- GlucoLume - Actualización controlada de una base instalada al esquema v5 (DEC-02, GL-05)
--
-- No es una migración histórica: agrega a una base ya instalada solo lo que `python -m app.cli.schemaCheck` informó como faltante el
-- 19/10/2026 (las 6 restricciones CK_Medicion_* de glucosa del dispositivo). Idempotente: lo que ya existe no se toca. No borra ni modifica
-- filas: si alguna fila incumple una regla, el ALTER falla y la transacción se revierte entera.
--
-- Antes: respaldo restaurable (BACKUP ... WITH CHECKSUM + RESTORE VERIFYONLY), las consultas de conteo de
-- `schemaCheck --preparar-validacion` en 0 y el mismo script probado en una copia restaurada.
--   sqlcmd -S <servidor> -d <base> -i GlucoLume_actualizar_instalada.sql -v CONFIRMAR="ACTUALIZAR_GLUCOLUME_V5"
-- Reversión (no toca datos): ALTER TABLE dbo.Medicion DROP CONSTRAINT <nombre>; para cada una de las seis.

:on error exit

IF N'$(CONFIRMAR)' <> N'ACTUALIZAR_GLUCOLUME_V5' OR OBJECT_ID(N'dbo.Medicion') IS NULL
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="ACTUALIZAR_GLUCOLUME_V5" o la base no tiene dbo.Medicion: no se hizo nada.', 16, 1);
    SET NOEXEC ON;
END
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF OBJECT_ID(N'dbo.CK_Medicion_glucosaDispositivoOrigen', N'C') IS NULL
    ALTER TABLE [dbo].[Medicion] WITH CHECK ADD CONSTRAINT [CK_Medicion_glucosaDispositivoOrigen]
        CHECK (([glucosaDispositivo] IS NULL OR coalesce([origenGlucosa],N'')=N'DEMO' OR coalesce([origenGlucosa],N'')=N'EXPERIMENTAL'));
IF OBJECT_ID(N'dbo.CK_Medicion_glucosaDispositivoRango', N'C') IS NULL
    ALTER TABLE [dbo].[Medicion] WITH CHECK ADD CONSTRAINT [CK_Medicion_glucosaDispositivoRango]
        CHECK (([glucosaDispositivo] IS NULL OR [glucosaDispositivo]>=(0)));
IF OBJECT_ID(N'dbo.CK_Medicion_indiceOptico', N'C') IS NULL
    ALTER TABLE [dbo].[Medicion] WITH CHECK ADD CONSTRAINT [CK_Medicion_indiceOptico]
        CHECK (([indiceOptico] IS NULL OR [indiceOptico]>=(0)));
IF OBJECT_ID(N'dbo.CK_Medicion_lecturas', N'C') IS NULL
    ALTER TABLE [dbo].[Medicion] WITH CHECK ADD CONSTRAINT [CK_Medicion_lecturas]
        CHECK (([lecturasEstabilizadas] IS NULL OR [lecturasEstabilizadas]>(0)));
IF OBJECT_ID(N'dbo.CK_Medicion_origenConGlucosa', N'C') IS NULL
    ALTER TABLE [dbo].[Medicion] WITH CHECK ADD CONSTRAINT [CK_Medicion_origenConGlucosa]
        CHECK (([origenGlucosa] IS NULL OR [origenGlucosa]=N'SIN_CALIBRAR' OR [glucosaDispositivo] IS NOT NULL));
IF OBJECT_ID(N'dbo.CK_Medicion_unidadGlucosa', N'C') IS NULL
    ALTER TABLE [dbo].[Medicion] WITH CHECK ADD CONSTRAINT [CK_Medicion_unidadGlucosa]
        CHECK (([glucosaDispositivo] IS NULL OR coalesce([unidadGlucosa],N'')=N'mg/dL'));

COMMIT TRANSACTION;
GO

-- VERIFICACION: las seis deben quedar habilitadas y confiables (is_disabled = 0, is_not_trusted = 0).
SELECT name, is_disabled, is_not_trusted
FROM sys.check_constraints
WHERE parent_object_id = OBJECT_ID(N'dbo.Medicion')
  AND name IN (N'CK_Medicion_glucosaDispositivoOrigen', N'CK_Medicion_glucosaDispositivoRango', N'CK_Medicion_indiceOptico',
               N'CK_Medicion_lecturas', N'CK_Medicion_origenConGlucosa', N'CK_Medicion_unidadGlucosa')
ORDER BY name;
GO

SET NOEXEC OFF;
GO
