-- GlucoLume - Agrega la tabla dbo.PuenteCredencial a una base YA INSTALADA (H-16, credenciales individuales de los puentes serie)
--
-- Una instalación nueva ya la trae (GlucoLume_DB_v5.sql). Este script es para las bases instaladas antes: crea SOLO esa tabla, vacía.
-- Idempotente (si existe no hace nada) y transaccional (todo o nada). No lee ni modifica filas de otras tablas. Sin esta tabla el puente sigue
-- funcionando con el BRIDGE_TOKEN compartido; la API la detecta sola (schemaCompat) a los pocos minutos de crearla.
--
-- Antes: respaldo restaurable (GlucoLume_respaldo.ps1) y probar el script en una copia restaurada.
--   sqlcmd -S <servidor> -E -C -I -d <base> -i GlucoLume_agregar_puente_credencial.sql -v CONFIRMAR="AGREGAR_PUENTE_CREDENCIAL"
-- Después, si ya se aplicaron los permisos, volver a ejecutar GlucoLume_permisos.sql (idempotente) para que los roles la cubran.
-- Reversión (la tabla debe estar vacía o sus credenciales ya no hacer falta; los puentes vuelven al token compartido):
--   DROP TABLE dbo.PuenteCredencial;

:on error exit

IF N'$(CONFIRMAR)' <> N'AGREGAR_PUENTE_CREDENCIAL'
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="AGREGAR_PUENTE_CREDENCIAL": no se hizo nada.', 16, 1);
    SET NOEXEC ON;
END
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF OBJECT_ID(N'dbo.PuenteCredencial', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[PuenteCredencial](
        [idPuenteCredencial] [uniqueidentifier] NOT NULL CONSTRAINT [DF_PuenteCredencial_id] DEFAULT (newid()),
        [nombre] [nvarchar](100) NOT NULL,
        [tokenHash] [nvarchar](64) NOT NULL,
        [codigoDispositivo] [nvarchar](100) NOT NULL,
        [fechaCreacion] [datetime2](3) NOT NULL CONSTRAINT [DF_PuenteCredencial_fechaCreacion] DEFAULT (sysutcdatetime()),
        [fechaExpiracion] [datetime2](3) NOT NULL,
        [fechaRevocacion] [datetime2](3) NULL,
        [fechaUltimoUso] [datetime2](3) NULL,
        CONSTRAINT [PK_PuenteCredencial] PRIMARY KEY CLUSTERED ([idPuenteCredencial] ASC),
        CONSTRAINT [UQ_PuenteCredencial_tokenHash] UNIQUE NONCLUSTERED ([tokenHash] ASC),
        CONSTRAINT [CK_PuenteCredencial_expiracion] CHECK (([fechaExpiracion]>[fechaCreacion])),
        CONSTRAINT [CK_PuenteCredencial_textos] CHECK (([codigoDispositivo]<>N'' AND [nombre]<>N''))
    );
END

COMMIT TRANSACTION;
GO

-- VERIFICACION: la tabla existe, está vacía y sus restricciones están habilitadas y confiables.
SELECT N'PuenteCredencial' AS tabla, (SELECT COUNT_BIG(*) FROM dbo.PuenteCredencial) AS filas;
SELECT name, is_disabled, is_not_trusted FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID(N'dbo.PuenteCredencial');
GO

SET NOEXEC OFF;
GO
