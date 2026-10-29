-- GlucoLume - Notificaciones de la cuenta (sección «Notificaciones»): avisos en la página, preferencias por canal y horario
-- de recordatorio de medición. Agrega a una base ya instalada solo lo que falta: tres tablas nuevas (PreferenciaNotificacion,
-- RecordatorioMedicion, NotificacionUsuario), sus restricciones e índice. No borra ni modifica filas existentes.
--
-- Idempotente: lo que ya existe no se toca. Requiere permiso de DDL (la cuenta de la API no lo tiene: lo aplica quien administra la base).
-- Los permisos SELECT/INSERT/UPDATE de rol_glucolume_api ya cubren el esquema dbo (GlucoLume_permisos.sql); estas tablas no conceden DELETE.
--
-- Antes: respaldo restaurable (BACKUP ... WITH CHECKSUM) y, si hay dudas, probar el script en una copia restaurada.
--   sqlcmd -S <servidor> -d <base> -I -i GlucoLume_notificaciones_usuario.sql -v CONFIRMAR="ACTUALIZAR_NOTIFICACIONES_USUARIO"
-- Reversión (no toca datos de otras tablas): DROP TABLE dbo.NotificacionUsuario, dbo.RecordatorioMedicion, dbo.PreferenciaNotificacion;
-- Después de aplicarlo, el proceso de recordatorios puede programarse: python -m app.jobs.reminders ejecutar (cada 5 minutos).

:on error exit

IF N'$(CONFIRMAR)' <> N'ACTUALIZAR_NOTIFICACIONES_USUARIO' OR OBJECT_ID(N'dbo.Usuario', N'U') IS NULL
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="ACTUALIZAR_NOTIFICACIONES_USUARIO" o la base no tiene dbo.Usuario: no se hizo nada.', 16, 1);
    SET NOEXEC ON;
END
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF OBJECT_ID(N'dbo.NotificacionUsuario', N'U') IS NULL
    CREATE TABLE [dbo].[NotificacionUsuario](
    	[idNotificacion] [uniqueidentifier] NOT NULL,
    	[idUsuario] [uniqueidentifier] NOT NULL,
    	[evento] [nvarchar](40) NOT NULL,
    	[titulo] [nvarchar](120) NOT NULL,
    	[mensaje] [nvarchar](400) NOT NULL,
    	[url] [nvarchar](300) NULL,
    	[fechaCreacion] [datetime2](3) NOT NULL,
    	[fechaLectura] [datetime2](3) NULL,
     CONSTRAINT [PK_NotificacionUsuario] PRIMARY KEY CLUSTERED 
    (
    	[idNotificacion] ASC
    )WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
    ) ON [PRIMARY]

IF OBJECT_ID(N'dbo.PreferenciaNotificacion', N'U') IS NULL
    CREATE TABLE [dbo].[PreferenciaNotificacion](
    	[idPreferenciaNotificacion] [uniqueidentifier] NOT NULL,
    	[idUsuario] [uniqueidentifier] NOT NULL,
    	[evento] [nvarchar](40) NOT NULL,
    	[enPagina] [bit] NOT NULL,
    	[porCorreo] [bit] NOT NULL,
    	[fechaActualizacion] [datetime2](3) NOT NULL,
     CONSTRAINT [PK_PreferenciaNotificacion] PRIMARY KEY CLUSTERED 
    (
    	[idPreferenciaNotificacion] ASC
    )WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
     CONSTRAINT [UQ_PreferenciaNotificacion_usuarioEvento] UNIQUE NONCLUSTERED 
    (
    	[idUsuario] ASC,
    	[evento] ASC
    )WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
    ) ON [PRIMARY]

IF OBJECT_ID(N'dbo.RecordatorioMedicion', N'U') IS NULL
    CREATE TABLE [dbo].[RecordatorioMedicion](
    	[idUsuario] [uniqueidentifier] NOT NULL,
    	[modo] [nvarchar](12) NOT NULL,
    	[intervaloHoras] [int] NULL,
    	[horarios] [nvarchar](200) NULL,
    	[ultimoAviso] [datetime2](3) NULL,
    	[fechaActualizacion] [datetime2](3) NOT NULL,
     CONSTRAINT [PK_RecordatorioMedicion] PRIMARY KEY CLUSTERED 
    (
    	[idUsuario] ASC
    )WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
    ) ON [PRIMARY]

IF OBJECT_ID(N'dbo.DF_NotificacionUsuario_id', N'D') IS NULL
    ALTER TABLE [dbo].[NotificacionUsuario] ADD  CONSTRAINT [DF_NotificacionUsuario_id]  DEFAULT (newid()) FOR [idNotificacion];
IF OBJECT_ID(N'dbo.DF_NotificacionUsuario_fechaCreacion', N'D') IS NULL
    ALTER TABLE [dbo].[NotificacionUsuario] ADD  CONSTRAINT [DF_NotificacionUsuario_fechaCreacion]  DEFAULT (sysutcdatetime()) FOR [fechaCreacion];
IF OBJECT_ID(N'dbo.DF_PreferenciaNotificacion_id', N'D') IS NULL
    ALTER TABLE [dbo].[PreferenciaNotificacion] ADD  CONSTRAINT [DF_PreferenciaNotificacion_id]  DEFAULT (newid()) FOR [idPreferenciaNotificacion];
IF OBJECT_ID(N'dbo.DF_PreferenciaNotificacion_enPagina', N'D') IS NULL
    ALTER TABLE [dbo].[PreferenciaNotificacion] ADD  CONSTRAINT [DF_PreferenciaNotificacion_enPagina]  DEFAULT ((1)) FOR [enPagina];
IF OBJECT_ID(N'dbo.DF_PreferenciaNotificacion_porCorreo', N'D') IS NULL
    ALTER TABLE [dbo].[PreferenciaNotificacion] ADD  CONSTRAINT [DF_PreferenciaNotificacion_porCorreo]  DEFAULT ((0)) FOR [porCorreo];
IF OBJECT_ID(N'dbo.DF_PreferenciaNotificacion_fechaActualizacion', N'D') IS NULL
    ALTER TABLE [dbo].[PreferenciaNotificacion] ADD  CONSTRAINT [DF_PreferenciaNotificacion_fechaActualizacion]  DEFAULT (sysutcdatetime()) FOR [fechaActualizacion];
IF OBJECT_ID(N'dbo.DF_RecordatorioMedicion_modo', N'D') IS NULL
    ALTER TABLE [dbo].[RecordatorioMedicion] ADD  CONSTRAINT [DF_RecordatorioMedicion_modo]  DEFAULT (N'NINGUNO') FOR [modo];
IF OBJECT_ID(N'dbo.DF_RecordatorioMedicion_fechaActualizacion', N'D') IS NULL
    ALTER TABLE [dbo].[RecordatorioMedicion] ADD  CONSTRAINT [DF_RecordatorioMedicion_fechaActualizacion]  DEFAULT (sysutcdatetime()) FOR [fechaActualizacion];
IF OBJECT_ID(N'dbo.FK_NotificacionUsuario_Usuario', N'F') IS NULL
    ALTER TABLE [dbo].[NotificacionUsuario]  WITH CHECK ADD  CONSTRAINT [FK_NotificacionUsuario_Usuario] FOREIGN KEY([idUsuario])
    REFERENCES [dbo].[Usuario] ([idUsuario]);
ALTER TABLE [dbo].[NotificacionUsuario] CHECK CONSTRAINT [FK_NotificacionUsuario_Usuario];
IF OBJECT_ID(N'dbo.FK_PreferenciaNotificacion_Usuario', N'F') IS NULL
    ALTER TABLE [dbo].[PreferenciaNotificacion]  WITH CHECK ADD  CONSTRAINT [FK_PreferenciaNotificacion_Usuario] FOREIGN KEY([idUsuario])
    REFERENCES [dbo].[Usuario] ([idUsuario]);
ALTER TABLE [dbo].[PreferenciaNotificacion] CHECK CONSTRAINT [FK_PreferenciaNotificacion_Usuario];
IF OBJECT_ID(N'dbo.FK_RecordatorioMedicion_Usuario', N'F') IS NULL
    ALTER TABLE [dbo].[RecordatorioMedicion]  WITH CHECK ADD  CONSTRAINT [FK_RecordatorioMedicion_Usuario] FOREIGN KEY([idUsuario])
    REFERENCES [dbo].[Usuario] ([idUsuario]);
ALTER TABLE [dbo].[RecordatorioMedicion] CHECK CONSTRAINT [FK_RecordatorioMedicion_Usuario];
IF OBJECT_ID(N'dbo.CK_NotificacionUsuario_evento', N'C') IS NULL
    ALTER TABLE [dbo].[NotificacionUsuario]  WITH CHECK ADD  CONSTRAINT [CK_NotificacionUsuario_evento] CHECK  (([evento]=N'INICIO_SESION' OR [evento]=N'AGREGADO_GRUPO' OR [evento]=N'RECORDATORIO_MEDICION' OR [evento]=N'NUEVA_ACCION_GRUPO'));
IF OBJECT_ID(N'dbo.CK_PreferenciaNotificacion_evento', N'C') IS NULL
    ALTER TABLE [dbo].[PreferenciaNotificacion]  WITH CHECK ADD  CONSTRAINT [CK_PreferenciaNotificacion_evento] CHECK  (([evento]=N'INICIO_SESION' OR [evento]=N'AGREGADO_GRUPO' OR [evento]=N'RECORDATORIO_MEDICION' OR [evento]=N'NUEVA_ACCION_GRUPO'));
IF OBJECT_ID(N'dbo.CK_RecordatorioMedicion_modo', N'C') IS NULL
    ALTER TABLE [dbo].[RecordatorioMedicion]  WITH CHECK ADD  CONSTRAINT [CK_RecordatorioMedicion_modo] CHECK  (([modo]=N'NINGUNO' OR [modo]=N'INTERVALO' OR [modo]=N'HORARIOS'));
IF OBJECT_ID(N'dbo.CK_RecordatorioMedicion_intervalo', N'C') IS NULL
    ALTER TABLE [dbo].[RecordatorioMedicion]  WITH CHECK ADD  CONSTRAINT [CK_RecordatorioMedicion_intervalo] CHECK  (([intervaloHoras] IS NULL OR ([intervaloHoras]>(0) AND [intervaloHoras]<=(24))));
IF OBJECT_ID(N'dbo.CK_RecordatorioMedicion_intervaloRequerido', N'C') IS NULL
    ALTER TABLE [dbo].[RecordatorioMedicion]  WITH CHECK ADD  CONSTRAINT [CK_RecordatorioMedicion_intervaloRequerido] CHECK  (([modo]<>N'INTERVALO' OR [intervaloHoras] IS NOT NULL));
IF OBJECT_ID(N'dbo.CK_RecordatorioMedicion_horariosRequeridos', N'C') IS NULL
    ALTER TABLE [dbo].[RecordatorioMedicion]  WITH CHECK ADD  CONSTRAINT [CK_RecordatorioMedicion_horariosRequeridos] CHECK  (([modo]<>N'HORARIOS' OR [horarios] IS NOT NULL));
IF OBJECT_ID(N'dbo.UQ_PreferenciaNotificacion_usuarioEvento', N'UQ') IS NULL
    ALTER TABLE [dbo].[PreferenciaNotificacion] ADD CONSTRAINT [UQ_PreferenciaNotificacion_usuarioEvento] UNIQUE NONCLUSTERED ([idUsuario] ASC, [evento] ASC);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_NotificacionUsuario_usuarioFecha' AND object_id = OBJECT_ID(N'dbo.NotificacionUsuario'))
    CREATE NONCLUSTERED INDEX [IX_NotificacionUsuario_usuarioFecha] ON [dbo].[NotificacionUsuario] ([idUsuario], [fechaCreacion]);

COMMIT TRANSACTION;
GO

-- VERIFICACION: las tres tablas deben existir.
SELECT name FROM sys.tables WHERE name IN (N'NotificacionUsuario', N'PreferenciaNotificacion', N'RecordatorioMedicion')
ORDER BY name;
GO

SET NOEXEC OFF;
GO
