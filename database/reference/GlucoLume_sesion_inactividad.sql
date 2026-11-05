-- GlucoLume - Cierre de sesión por inactividad (SesionUsuario.ultimaActividad)
--
-- Agrega a una base ya instalada solo la columna nueva ultimaActividad en dbo.SesionUsuario (NULL). No cambia ninguna otra columna,
-- ni ninguna fila: las sesiones anteriores quedan con NULL y el backend las cuenta como activas desde su primer pedido (no se cierran de golpe).
-- Con la columna, una sesión sin pedidos autenticados durante SESION_INACTIVIDAD_MINUTOS (15 por omisión) se cierra sola.
-- Permisos: la cuenta de la API ya tiene SELECT, INSERT y UPDATE sobre el esquema dbo (GlucoLume_permisos.sql); no hace falta permiso nuevo.
-- Idempotente: si la columna ya existe, no hace nada.
-- Antes: respaldo restaurable (BACKUP ... WITH CHECKSUM + RESTORE VERIFYONLY) y el mismo script probado en una copia restaurada.
--   sqlcmd -S <servidor> -d <base> -I -i GlucoLume_sesion_inactividad.sql -v CONFIRMAR="AGREGAR_SESION_INACTIVIDAD"   (-I: consistencia de índices)
-- Reversión (no toca las demás columnas): ALTER TABLE dbo.SesionUsuario DROP COLUMN ultimaActividad;

:on error exit

IF N'$(CONFIRMAR)' <> N'AGREGAR_SESION_INACTIVIDAD' OR OBJECT_ID(N'dbo.SesionUsuario') IS NULL
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="AGREGAR_SESION_INACTIVIDAD" o la base no tiene dbo.SesionUsuario: no se hizo nada.', 16, 1);
    SET NOEXEC ON;
END
GO

SET XACT_ABORT ON;
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;

IF COL_LENGTH(N'dbo.SesionUsuario', N'ultimaActividad') IS NULL
BEGIN
    BEGIN TRANSACTION;
    ALTER TABLE [dbo].[SesionUsuario] ADD [ultimaActividad] [datetime2](3) NULL;
    COMMIT TRANSACTION;
END
GO
