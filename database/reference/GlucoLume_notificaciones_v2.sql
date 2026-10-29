-- GlucoLume - Notificaciones v2 (rediseño de la sección «Notificaciones»): unicidad de avisos, registro de entrega del correo, nuevos avisos de
-- seguridad y de grupo, y criterio de equipo nuevo para el inicio de sesión. Se aplica sobre una base que ya tiene GlucoLume_notificaciones_usuario.sql.
--
-- Qué hace (todo en una transacción, sin borrar ninguna fila):
--   1. NotificacionUsuario: agrega claveEvento, visible, estadoCorreo e intentosCorreo, el índice único filtrado (idUsuario, claveEvento) y
--      el CHECK de estadoCorreo.
--   2. Datos existentes: cada aviso anterior recibe una clave propia («LEGADO:<id>») y su fechaCreacion se corrige de UTC a hora de Argentina
--      (se guardaba con sysutcdatetime() pero la aplicación la interpreta como hora de Argentina: se veía 3 horas adelantada). Solo toca filas
--      sin clave, así que correr el script otra vez no vuelve a restar las 3 horas.
--   3. CHECK de evento (NotificacionUsuario y PreferenciaNotificacion): admite CAMBIO_CONTRASENA, CAMBIO_MFA, ACTIVIDAD_SOSPECHOSA,
--      INVITACION_GRUPO y MEDICION_GRUPO además de los cuatro anteriores. Se vuelven a crear con la lista completa.
--   4. PreferenciaNotificacion: quien ya había elegido canales para NUEVA_ACCION_GRUPO conserva esa elección para el nuevo aviso
--      MEDICION_GRUPO (antes las mediciones del grupo usaban ese mismo aviso). Solo inserta lo que falta.
--   5. Tabla nueva AccesoConocido (equipos desde los que cada cuenta ya inició sesión): sin ella el inicio de sesión se audita igual y
--      simplemente no se avisa de equipos nuevos.
--
-- Idempotente: lo que ya existe no se toca. Requiere permiso de DDL (la cuenta de la API no lo tiene: lo aplica quien administra la base).
-- Los permisos SELECT/INSERT/UPDATE de rol_glucolume_api ya cubren el esquema dbo (GlucoLume_permisos.sql). La depuración de avisos
-- (python -m app.jobs.reminders depurar) usa la cuenta de procesos: necesita el GRANT DELETE sobre NotificacionUsuario que agrega GlucoLume_permisos.sql.
--
-- Antes: respaldo restaurable (BACKUP ... WITH CHECKSUM) y, si hay dudas, probar el script en una copia restaurada.
--   sqlcmd -S <servidor> -d <base> -I -i GlucoLume_notificaciones_v2.sql -v CONFIRMAR="ACTUALIZAR_NOTIFICACIONES_V2"
-- Reversión (los datos nuevos se pierden; los avisos anteriores quedan):
--   DROP TABLE dbo.AccesoConocido;
--   DROP INDEX UX_NotificacionUsuario_clave ON dbo.NotificacionUsuario;
--   (y quitar las columnas nuevas y volver a crear los CHECK con los cuatro avisos de GlucoLume_notificaciones_usuario.sql)
-- Mientras el script no se aplique, el backend nuevo deja «Notificaciones» como no disponible (schemaCompat) en lugar de fallar.

:on error exit

IF N'$(CONFIRMAR)' <> N'ACTUALIZAR_NOTIFICACIONES_V2' OR OBJECT_ID(N'dbo.NotificacionUsuario', N'U') IS NULL
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="ACTUALIZAR_NOTIFICACIONES_V2" o la base no tiene dbo.NotificacionUsuario (aplicar antes GlucoLume_notificaciones_usuario.sql): no se hizo nada.', 16, 1);
    SET NOEXEC ON;
END
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;

-- 1. Columnas nuevas de NotificacionUsuario.
IF COL_LENGTH(N'dbo.NotificacionUsuario', N'claveEvento') IS NULL
    ALTER TABLE [dbo].[NotificacionUsuario] ADD [claveEvento] [nvarchar](200) NULL;
IF COL_LENGTH(N'dbo.NotificacionUsuario', N'visible') IS NULL
    ALTER TABLE [dbo].[NotificacionUsuario] ADD [visible] [bit] NOT NULL CONSTRAINT [DF_NotificacionUsuario_visible] DEFAULT ((1));
IF COL_LENGTH(N'dbo.NotificacionUsuario', N'estadoCorreo') IS NULL
    ALTER TABLE [dbo].[NotificacionUsuario] ADD [estadoCorreo] [nvarchar](12) NULL;
IF COL_LENGTH(N'dbo.NotificacionUsuario', N'intentosCorreo') IS NULL
    ALTER TABLE [dbo].[NotificacionUsuario] ADD [intentosCorreo] [int] NOT NULL CONSTRAINT [DF_NotificacionUsuario_intentosCorreo] DEFAULT ((0));

-- 2. Datos existentes (SQL dinámico: las columnas recién agregadas no existen todavía cuando se compila este lote).
EXEC (N'UPDATE [dbo].[NotificacionUsuario]
        SET [claveEvento] = N''LEGADO:'' + CONVERT(nvarchar(36), [idNotificacion]),
            [fechaCreacion] = DATEADD(HOUR, -3, [fechaCreacion])
        WHERE [claveEvento] IS NULL;');

-- 3. CHECK de evento con los nueve avisos.
IF OBJECT_ID(N'dbo.CK_NotificacionUsuario_evento', N'C') IS NOT NULL
    ALTER TABLE [dbo].[NotificacionUsuario] DROP CONSTRAINT [CK_NotificacionUsuario_evento];
ALTER TABLE [dbo].[NotificacionUsuario]  WITH CHECK ADD  CONSTRAINT [CK_NotificacionUsuario_evento] CHECK  (([evento]=N'INICIO_SESION' OR [evento]=N'CAMBIO_CONTRASENA' OR [evento]=N'CAMBIO_MFA' OR [evento]=N'ACTIVIDAD_SOSPECHOSA' OR [evento]=N'INVITACION_GRUPO' OR [evento]=N'AGREGADO_GRUPO' OR [evento]=N'NUEVA_ACCION_GRUPO' OR [evento]=N'MEDICION_GRUPO' OR [evento]=N'RECORDATORIO_MEDICION'));
IF OBJECT_ID(N'dbo.CK_PreferenciaNotificacion_evento', N'C') IS NOT NULL
    ALTER TABLE [dbo].[PreferenciaNotificacion] DROP CONSTRAINT [CK_PreferenciaNotificacion_evento];
ALTER TABLE [dbo].[PreferenciaNotificacion]  WITH CHECK ADD  CONSTRAINT [CK_PreferenciaNotificacion_evento] CHECK  (([evento]=N'INICIO_SESION' OR [evento]=N'CAMBIO_CONTRASENA' OR [evento]=N'CAMBIO_MFA' OR [evento]=N'ACTIVIDAD_SOSPECHOSA' OR [evento]=N'INVITACION_GRUPO' OR [evento]=N'AGREGADO_GRUPO' OR [evento]=N'NUEVA_ACCION_GRUPO' OR [evento]=N'MEDICION_GRUPO' OR [evento]=N'RECORDATORIO_MEDICION'));

-- CHECK de estadoCorreo e índice único filtrado (SQL dinámico por la misma razón que el paso 2).
IF OBJECT_ID(N'dbo.CK_NotificacionUsuario_estadoCorreo', N'C') IS NULL
    EXEC (N'ALTER TABLE [dbo].[NotificacionUsuario] WITH CHECK ADD CONSTRAINT [CK_NotificacionUsuario_estadoCorreo] CHECK ([estadoCorreo] IS NULL OR [estadoCorreo]=N''PENDIENTE'' OR [estadoCorreo]=N''ENVIADO'' OR [estadoCorreo]=N''FALLIDO'');');
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_NotificacionUsuario_clave' AND object_id = OBJECT_ID(N'dbo.NotificacionUsuario'))
    EXEC (N'CREATE UNIQUE NONCLUSTERED INDEX [UX_NotificacionUsuario_clave] ON [dbo].[NotificacionUsuario] ([idUsuario], [claveEvento]) WHERE [claveEvento] IS NOT NULL;');

-- 4. La elección de canales de NUEVA_ACCION_GRUPO se conserva para el nuevo aviso MEDICION_GRUPO.
INSERT INTO [dbo].[PreferenciaNotificacion] ([idUsuario], [evento], [enPagina], [porCorreo])
SELECT p.[idUsuario], N'MEDICION_GRUPO', p.[enPagina], p.[porCorreo]
FROM [dbo].[PreferenciaNotificacion] p
WHERE p.[evento] = N'NUEVA_ACCION_GRUPO'
  AND NOT EXISTS (SELECT 1 FROM [dbo].[PreferenciaNotificacion] q WHERE q.[idUsuario] = p.[idUsuario] AND q.[evento] = N'MEDICION_GRUPO');

-- 5. Equipos desde los que cada cuenta ya inició sesión.
IF OBJECT_ID(N'dbo.AccesoConocido', N'U') IS NULL
    CREATE TABLE [dbo].[AccesoConocido](
    	[idAccesoConocido] [uniqueidentifier] NOT NULL,
    	[idUsuario] [uniqueidentifier] NOT NULL,
    	[huella] [nvarchar](64) NOT NULL,
    	[navegador] [nvarchar](60) NULL,
    	[sistemaOperativo] [nvarchar](60) NULL,
    	[dispositivo] [nvarchar](40) NULL,
    	[primerAcceso] [datetime2](3) NOT NULL,
    	[ultimoAcceso] [datetime2](3) NOT NULL,
     CONSTRAINT [PK_AccesoConocido] PRIMARY KEY CLUSTERED
    (
    	[idAccesoConocido] ASC
    )WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
     CONSTRAINT [UQ_AccesoConocido_usuarioHuella] UNIQUE NONCLUSTERED
    (
    	[idUsuario] ASC,
    	[huella] ASC
    )WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
    ) ON [PRIMARY]

IF OBJECT_ID(N'dbo.DF_AccesoConocido_id', N'D') IS NULL
    ALTER TABLE [dbo].[AccesoConocido] ADD  CONSTRAINT [DF_AccesoConocido_id]  DEFAULT (newid()) FOR [idAccesoConocido];
IF OBJECT_ID(N'dbo.DF_AccesoConocido_primerAcceso', N'D') IS NULL
    ALTER TABLE [dbo].[AccesoConocido] ADD  CONSTRAINT [DF_AccesoConocido_primerAcceso]  DEFAULT (sysutcdatetime()) FOR [primerAcceso];
IF OBJECT_ID(N'dbo.DF_AccesoConocido_ultimoAcceso', N'D') IS NULL
    ALTER TABLE [dbo].[AccesoConocido] ADD  CONSTRAINT [DF_AccesoConocido_ultimoAcceso]  DEFAULT (sysutcdatetime()) FOR [ultimoAcceso];
IF OBJECT_ID(N'dbo.FK_AccesoConocido_Usuario', N'F') IS NULL
    ALTER TABLE [dbo].[AccesoConocido]  WITH CHECK ADD  CONSTRAINT [FK_AccesoConocido_Usuario] FOREIGN KEY([idUsuario])
    REFERENCES [dbo].[Usuario] ([idUsuario]);
ALTER TABLE [dbo].[AccesoConocido] CHECK CONSTRAINT [FK_AccesoConocido_Usuario];

COMMIT TRANSACTION;
GO

-- VERIFICACION: las columnas nuevas, el índice único y la tabla AccesoConocido deben existir; ninguna fila de NotificacionUsuario debe quedar sin clave.
SELECT name FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.NotificacionUsuario') AND name IN (N'claveEvento', N'visible', N'estadoCorreo', N'intentosCorreo') ORDER BY name;
SELECT name FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.NotificacionUsuario') AND name = N'UX_NotificacionUsuario_clave';
SELECT name FROM sys.tables WHERE name = N'AccesoConocido';
EXEC (N'SELECT COUNT(*) AS avisosSinClave FROM dbo.NotificacionUsuario WHERE claveEvento IS NULL;');
GO

SET NOEXEC OFF;
GO
