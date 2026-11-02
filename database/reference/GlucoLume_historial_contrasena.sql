-- GlucoLume - Historial de contraseñas (CredencialLocalHistorial): la contraseña nueva no puede ser la vigente ni una de las últimas 5 anteriores
--
-- Agrega a una base ya instalada solo la tabla nueva, su índice, su clave primaria, sus valores por defecto y su clave foránea con borrado
-- en cascada (al borrar la CredencialLocal se borra su historial). No cambia ninguna tabla existente ni ninguna fila.
-- Permisos: la cuenta de la API y la de retención ya tienen SELECT, INSERT y UPDATE sobre el esquema dbo (GlucoLume_permisos.sql). Además
-- reciben DELETE solo sobre esta tabla, porque la API descarta las contraseñas anteriores que pasan de las 5 últimas, y la retención
-- tiene los mismos borrados que la API. El borrado en cascada de CredencialLocal no requiere ese permiso.
-- Idempotente: lo que ya existe no se toca. Si la base ya tiene la tabla, no hace nada.
-- Antes: respaldo restaurable (BACKUP ... WITH CHECKSUM + RESTORE VERIFYONLY) y el mismo script probado en una copia restaurada.
--   sqlcmd -S <servidor> -d <base> -I -i GlucoLume_historial_contrasena.sql -v CONFIRMAR="AGREGAR_HISTORIAL_CONTRASENA"   (-I: los índices filtrados exigen QUOTED_IDENTIFIER ON)
-- Reversión (no toca las demás tablas): DROP TABLE dbo.CredencialLocalHistorial;

:on error exit

IF N'$(CONFIRMAR)' <> N'AGREGAR_HISTORIAL_CONTRASENA' OR OBJECT_ID(N'dbo.CredencialLocal') IS NULL
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="AGREGAR_HISTORIAL_CONTRASENA" o la base no tiene dbo.CredencialLocal: no se hizo nada.', 16, 1);
    SET NOEXEC ON;
END
GO

SET XACT_ABORT ON;
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;

IF OBJECT_ID(N'dbo.CredencialLocalHistorial', N'U') IS NULL
BEGIN
    BEGIN TRANSACTION;
    CREATE TABLE [dbo].[CredencialLocalHistorial](
        [idCredencialLocalHistorial] [uniqueidentifier] NOT NULL CONSTRAINT [DF_CredencialLocalHistorial_id] DEFAULT (newid()),
        [idCredencialLocal] [uniqueidentifier] NOT NULL,
        [passwordHash] [nvarchar](255) NOT NULL,
        [fechaCreacion] [datetime2](3) NOT NULL CONSTRAINT [DF_CredencialLocalHistorial_fechaCreacion] DEFAULT (sysutcdatetime()),
        CONSTRAINT [PK_CredencialLocalHistorial] PRIMARY KEY CLUSTERED ([idCredencialLocalHistorial] ASC),
        CONSTRAINT [FK_CredencialLocalHistorial_CredencialLocal] FOREIGN KEY ([idCredencialLocal])
            REFERENCES [dbo].[CredencialLocal] ([idCredencialLocal]) ON DELETE CASCADE
    );
    COMMIT TRANSACTION;
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_CredencialLocalHistorial_idCredencialLocal_fechaCreacion'
               AND object_id = OBJECT_ID(N'dbo.CredencialLocalHistorial'))
    CREATE NONCLUSTERED INDEX [IX_CredencialLocalHistorial_idCredencialLocal_fechaCreacion]
        ON [dbo].[CredencialLocalHistorial] ([idCredencialLocal] ASC, [fechaCreacion] ASC);
GO

GRANT DELETE ON OBJECT::dbo.CredencialLocalHistorial TO rol_glucolume_api;
GRANT DELETE ON OBJECT::dbo.CredencialLocalHistorial TO rol_glucolume_retencion;
GO
