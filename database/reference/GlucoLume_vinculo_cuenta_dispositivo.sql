-- GlucoLume - Agrega la tabla dbo.VinculoCuentaDispositivo a una base YA INSTALADA (dispositivo vinculado a cada cuenta individual)
--
-- Una cuenta individual tiene UN solo dispositivo vinculado (UQ sobre idUsuario). Un mismo dispositivo puede estar vinculado a varias
-- cuentas (sin mezclar mediciones: cada medición guarda su cuenta y su dispositivo). Una instalación nueva ya la trae (GlucoLume_DB_v5.sql).
-- Idempotente (si existe no hace nada) y transaccional (todo o nada). No lee ni modifica filas de otras tablas. Sin esta tabla el backend
-- no vincula dispositivos (la API lo detecta sola con schemaCompat).
--
-- Antes: respaldo restaurable (GlucoLume_respaldo.ps1) y probar el script en una copia restaurada.
--   sqlcmd -S <servidor> -E -C -I -d <base> -i GlucoLume_vinculo_cuenta_dispositivo.sql -v CONFIRMAR="AGREGAR_VINCULO_CUENTA_DISPOSITIVO"
-- Después, si ya se aplicaron los permisos, volver a ejecutar GlucoLume_permisos.sql (idempotente) para que los roles la cubran.
-- Reversión (las filas son solo vínculos; borrarlas no toca mediciones ni dispositivos):
--   DROP TABLE dbo.VinculoCuentaDispositivo;

:on error exit

IF N'$(CONFIRMAR)' <> N'AGREGAR_VINCULO_CUENTA_DISPOSITIVO'
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="AGREGAR_VINCULO_CUENTA_DISPOSITIVO": no se hizo nada.', 16, 1);
    SET NOEXEC ON;
END
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF OBJECT_ID(N'dbo.VinculoCuentaDispositivo', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[VinculoCuentaDispositivo](
        [idVinculo] [uniqueidentifier] NOT NULL CONSTRAINT [DF_VinculoCuentaDispositivo_id] DEFAULT (newid()),
        [idUsuario] [uniqueidentifier] NOT NULL,
        [idDispositivo] [uniqueidentifier] NOT NULL,
        [fechaVinculo] [datetime2](3) NOT NULL CONSTRAINT [DF_VinculoCuentaDispositivo_fecha] DEFAULT (sysutcdatetime()),
        CONSTRAINT [PK_VinculoCuentaDispositivo] PRIMARY KEY CLUSTERED ([idVinculo] ASC),
        CONSTRAINT [UQ_VinculoCuentaDispositivo_usuario] UNIQUE NONCLUSTERED ([idUsuario] ASC),
        CONSTRAINT [FK_VinculoCuentaDispositivo_Usuario] FOREIGN KEY ([idUsuario]) REFERENCES [dbo].[Usuario] ([idUsuario]),
        CONSTRAINT [FK_VinculoCuentaDispositivo_Dispositivo] FOREIGN KEY ([idDispositivo]) REFERENCES [dbo].[Dispositivo] ([idDispositivo])
    );
    CREATE NONCLUSTERED INDEX [IX_VinculoCuentaDispositivo_dispositivo] ON [dbo].[VinculoCuentaDispositivo] ([idDispositivo]);
END

COMMIT TRANSACTION;
GO

-- VERIFICACION: la tabla existe y sus restricciones están habilitadas y confiables.
SELECT N'VinculoCuentaDispositivo' AS tabla, (SELECT COUNT_BIG(*) FROM dbo.VinculoCuentaDispositivo) AS filas;
SELECT name, is_disabled, is_not_trusted FROM sys.foreign_keys WHERE parent_object_id = OBJECT_ID(N'dbo.VinculoCuentaDispositivo');
GO

SET NOEXEC OFF;
GO
