/* =====================================================================================================================
   GlucoLume - copia COMPLETA de la base (estructura + datos) generada desde Docker (glucolume-db-1 / GlucoLume)
   Generado: 2026-10-25 19:51:56 -03:00 | 34 tablas | 60 filas | origen verificado identico
   Crea la base [GlucoLume_Copia] y la llena. NO reemplaza ni modifica ninguna base existente: si [GlucoLume_Copia] ya existe, se detiene.
   CONTIENE DATOS PERSONALES (Usuario, PerfilMedicion, Auditoria...). No subir a GitHub ni compartir.
   No incluye usuarios ni roles de base (dependen de logins del servidor de origen).
   Uso en SSMS: abrir este archivo (File > Open), conectar a la instancia deseada y ejecutar con F5.
   ===================================================================================================================== */
SET NOCOUNT ON;
GO
IF DB_ID(N'GlucoLume_Copia') IS NOT NULL
BEGIN
    RAISERROR(N'La base GlucoLume_Copia ya existe: no se reemplaza. Cambiar el nombre en este archivo (buscar GlucoLume_Copia) o borrarla a mano.', 16, 1);
    SET NOEXEC ON;
END
GO
CREATE DATABASE [GlucoLume_Copia];
GO
USE [GlucoLume_Copia];
GO
-- ===== 1. Tablas (claves primarias, unicas, CHECK, DEFAULT e indices) =====
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[Auditoria](
	[idAuditoria] [uniqueidentifier] NOT NULL,
	[idUsuario] [uniqueidentifier] NULL,
	[tipoEvento] [nvarchar](20) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[accion] [nvarchar](50) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[tablaAfectada] [nvarchar](128) COLLATE Modern_Spanish_CI_AS NULL,
	[idRegistro] [uniqueidentifier] NULL,
	[tablaRelacionada] [nvarchar](128) COLLATE Modern_Spanish_CI_AS NULL,
	[idRelacionado] [uniqueidentifier] NULL,
	[datosPrevios] [nvarchar](max) COLLATE Modern_Spanish_CI_AS NULL,
	[datosNuevos] [nvarchar](max) COLLATE Modern_Spanish_CI_AS NULL,
	[resultado] [nvarchar](10) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaHora] [datetime2](3) NOT NULL,
	[observacion] [nvarchar](1000) COLLATE Modern_Spanish_CI_AS NULL,
	[detalle] [nvarchar](max) COLLATE Modern_Spanish_CI_AS NULL,
	[idInstitucion] [uniqueidentifier] NULL,
	[modulo] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NULL,
	[tipoCuentaActor] [nvarchar](40) COLLATE Modern_Spanish_CI_AS NULL,
 CONSTRAINT [PK_Auditoria] PRIMARY KEY CLUSTERED 
(
	[idAuditoria] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]

GO
SET ANSI_PADDING ON

GO
CREATE NONCLUSTERED INDEX [IX_Auditoria_accion_fecha] ON [dbo].[Auditoria]
(
	[accion] ASC,
	[fechaHora] ASC
)
INCLUDE([idUsuario],[idInstitucion],[resultado]) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
CREATE NONCLUSTERED INDEX [IX_Auditoria_fecha] ON [dbo].[Auditoria]
(
	[fechaHora] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
CREATE NONCLUSTERED INDEX [IX_Auditoria_institucion_fecha] ON [dbo].[Auditoria]
(
	[idInstitucion] ASC,
	[fechaHora] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
SET ANSI_PADDING ON

GO
CREATE NONCLUSTERED INDEX [IX_Auditoria_modulo_fecha] ON [dbo].[Auditoria]
(
	[modulo] ASC,
	[fechaHora] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
CREATE NONCLUSTERED INDEX [IX_Auditoria_usuario_fecha] ON [dbo].[Auditoria]
(
	[idUsuario] ASC,
	[fechaHora] ASC
)
WHERE ([idUsuario] IS NOT NULL)
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
ALTER TABLE [dbo].[Auditoria] ADD  CONSTRAINT [DF_Auditoria_id]  DEFAULT (newsequentialid()) FOR [idAuditoria]
GO
ALTER TABLE [dbo].[Auditoria] ADD  CONSTRAINT [DF_Auditoria_resultado]  DEFAULT (N'EXITO') FOR [resultado]
GO
ALTER TABLE [dbo].[Auditoria] ADD  CONSTRAINT [DF_Auditoria_fechaHora]  DEFAULT (sysutcdatetime()) FOR [fechaHora]
GO
ALTER TABLE [dbo].[Auditoria]  WITH CHECK ADD  CONSTRAINT [CK_Auditoria_datosNuevosJson] CHECK  (([datosNuevos] IS NULL OR isjson([datosNuevos])=(1)))
GO
ALTER TABLE [dbo].[Auditoria] CHECK CONSTRAINT [CK_Auditoria_datosNuevosJson]
GO
ALTER TABLE [dbo].[Auditoria]  WITH CHECK ADD  CONSTRAINT [CK_Auditoria_datosPreviosJson] CHECK  (([datosPrevios] IS NULL OR isjson([datosPrevios])=(1)))
GO
ALTER TABLE [dbo].[Auditoria] CHECK CONSTRAINT [CK_Auditoria_datosPreviosJson]
GO
ALTER TABLE [dbo].[Auditoria]  WITH CHECK ADD  CONSTRAINT [CK_Auditoria_detalleJson] CHECK  (([detalle] IS NULL OR isjson([detalle])=(1)))
GO
ALTER TABLE [dbo].[Auditoria] CHECK CONSTRAINT [CK_Auditoria_detalleJson]
GO
ALTER TABLE [dbo].[Auditoria]  WITH CHECK ADD  CONSTRAINT [CK_Auditoria_registro] CHECK  (([idRegistro] IS NULL OR [tablaAfectada] IS NOT NULL))
GO
ALTER TABLE [dbo].[Auditoria] CHECK CONSTRAINT [CK_Auditoria_registro]
GO
ALTER TABLE [dbo].[Auditoria]  WITH CHECK ADD  CONSTRAINT [CK_Auditoria_relacionado] CHECK  (([idRelacionado] IS NULL OR [tablaRelacionada] IS NOT NULL))
GO
ALTER TABLE [dbo].[Auditoria] CHECK CONSTRAINT [CK_Auditoria_relacionado]
GO
ALTER TABLE [dbo].[Auditoria]  WITH CHECK ADD  CONSTRAINT [CK_Auditoria_resultado] CHECK  (([resultado]=N'FALLO' OR [resultado]=N'EXITO'))
GO
ALTER TABLE [dbo].[Auditoria] CHECK CONSTRAINT [CK_Auditoria_resultado]
GO
ALTER TABLE [dbo].[Auditoria]  WITH CHECK ADD  CONSTRAINT [CK_Auditoria_tipoCuentaActor] CHECK  (([tipoCuentaActor] IS NULL OR ([tipoCuentaActor]=N'MODERADOR_PLATAFORMA' OR [tipoCuentaActor]=N'ADMINISTRADOR_PLATAFORMA' OR [tipoCuentaActor]=N'USUARIO_INSTITUCIONAL' OR [tipoCuentaActor]=N'CONSUMIDOR_FINAL')))
GO
ALTER TABLE [dbo].[Auditoria] CHECK CONSTRAINT [CK_Auditoria_tipoCuentaActor]
GO
ALTER TABLE [dbo].[Auditoria]  WITH CHECK ADD  CONSTRAINT [CK_Auditoria_tipoEvento] CHECK  (([tipoEvento]=N'ACCESO' OR [tipoEvento]=N'PERMISO' OR [tipoEvento]=N'CRUD' OR [tipoEvento]=N'LOGIN'))
GO
ALTER TABLE [dbo].[Auditoria] CHECK CONSTRAINT [CK_Auditoria_tipoEvento]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[AuditoriaContexto](
	[idAuditoria] [uniqueidentifier] NOT NULL,
	[idCorrelacion] [nvarchar](64) COLLATE Modern_Spanish_CI_AS NULL,
	[ipOrigen] [nvarchar](45) COLLATE Modern_Spanish_CI_AS NULL,
	[agenteUsuario] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NULL,
	[motivo] [nvarchar](40) COLLATE Modern_Spanish_CI_AS NULL,
	[identificadorHash] [nvarchar](32) COLLATE Modern_Spanish_CI_AS NULL,
 CONSTRAINT [PK_AuditoriaContexto] PRIMARY KEY CLUSTERED 
(
	[idAuditoria] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
SET ANSI_PADDING ON

GO
CREATE NONCLUSTERED INDEX [IX_AuditoriaContexto_correlacion] ON [dbo].[AuditoriaContexto]
(
	[idCorrelacion] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
SET ANSI_PADDING ON

GO
CREATE NONCLUSTERED INDEX [IX_AuditoriaContexto_identificador] ON [dbo].[AuditoriaContexto]
(
	[identificadorHash] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
SET ANSI_PADDING ON

GO
CREATE NONCLUSTERED INDEX [IX_AuditoriaContexto_ip] ON [dbo].[AuditoriaContexto]
(
	[ipOrigen] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[AuditoriaTecnicaMedicion](
	[idEvento] [uniqueidentifier] NOT NULL,
	[fechaHora] [datetime2](0) NOT NULL,
	[tipoOperacion] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[estadoFinal] [nvarchar](12) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[motivo] [nvarchar](40) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[modeloSensor] [nvarchar](20) COLLATE Modern_Spanish_CI_AS NULL,
	[duracionSegundos] [int] NULL,
	[codigoError] [nvarchar](40) COLLATE Modern_Spanish_CI_AS NULL,
 CONSTRAINT [PK_AuditoriaTecnicaMedicion] PRIMARY KEY CLUSTERED 
(
	[idEvento] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
CREATE NONCLUSTERED INDEX [IX_AuditoriaTecnica_fecha] ON [dbo].[AuditoriaTecnicaMedicion]
(
	[fechaHora] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
ALTER TABLE [dbo].[AuditoriaTecnicaMedicion] ADD  DEFAULT (newid()) FOR [idEvento]
GO
ALTER TABLE [dbo].[AuditoriaTecnicaMedicion]  WITH CHECK ADD  CONSTRAINT [CK_AuditoriaTecnica_duracion] CHECK  (([duracionSegundos] IS NULL OR [duracionSegundos]>=(0)))
GO
ALTER TABLE [dbo].[AuditoriaTecnicaMedicion] CHECK CONSTRAINT [CK_AuditoriaTecnica_duracion]
GO
ALTER TABLE [dbo].[AuditoriaTecnicaMedicion]  WITH CHECK ADD  CONSTRAINT [CK_AuditoriaTecnica_estado] CHECK  (([estadoFinal]=N'CANCELADA' OR [estadoFinal]=N'INVALIDA'))
GO
ALTER TABLE [dbo].[AuditoriaTecnicaMedicion] CHECK CONSTRAINT [CK_AuditoriaTecnica_estado]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[CodigoRecuperacionMfa](
	[idCodigoRecuperacionMfa] [uniqueidentifier] NOT NULL,
	[idFactorMfa] [uniqueidentifier] NOT NULL,
	[codigoHash] [nvarchar](255) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaCreacion] [datetime2](3) NOT NULL,
	[fechaUso] [datetime2](3) NULL,
 CONSTRAINT [PK_CodigoRecuperacionMfa] PRIMARY KEY CLUSTERED 
(
	[idCodigoRecuperacionMfa] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
 CONSTRAINT [UQ_CodigoRecuperacionMfa_codigoHash] UNIQUE NONCLUSTERED 
(
	[codigoHash] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
ALTER TABLE [dbo].[CodigoRecuperacionMfa] ADD  CONSTRAINT [DF_CodigoRecuperacionMfa_id]  DEFAULT (newid()) FOR [idCodigoRecuperacionMfa]
GO
ALTER TABLE [dbo].[CodigoRecuperacionMfa] ADD  CONSTRAINT [DF_CodigoRecuperacionMfa_fechaCreacion]  DEFAULT (sysutcdatetime()) FOR [fechaCreacion]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ConfiguracionNotificacion](
	[idConfiguracionNotificacion] [uniqueidentifier] NOT NULL,
	[idUsuario] [uniqueidentifier] NOT NULL,
	[habilitada] [bit] NOT NULL,
	[intervaloMinutos] [int] NOT NULL,
	[horaInicio] [time](0) NULL,
	[horaFin] [time](0) NULL,
	[canal] [nvarchar](20) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaActualizacion] [datetime2](3) NOT NULL,
 CONSTRAINT [PK_ConfiguracionNotificacion] PRIMARY KEY CLUSTERED 
(
	[idConfiguracionNotificacion] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
 CONSTRAINT [UQ_ConfiguracionNotificacion_idUsuario] UNIQUE NONCLUSTERED 
(
	[idUsuario] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
ALTER TABLE [dbo].[ConfiguracionNotificacion] ADD  CONSTRAINT [DF_ConfiguracionNotificacion_id]  DEFAULT (newid()) FOR [idConfiguracionNotificacion]
GO
ALTER TABLE [dbo].[ConfiguracionNotificacion] ADD  CONSTRAINT [DF_ConfiguracionNotificacion_habilitada]  DEFAULT ((1)) FOR [habilitada]
GO
ALTER TABLE [dbo].[ConfiguracionNotificacion] ADD  CONSTRAINT [DF_ConfiguracionNotificacion_canal]  DEFAULT (N'WEB') FOR [canal]
GO
ALTER TABLE [dbo].[ConfiguracionNotificacion] ADD  CONSTRAINT [DF_ConfiguracionNotificacion_fechaActualizacion]  DEFAULT (sysutcdatetime()) FOR [fechaActualizacion]
GO
ALTER TABLE [dbo].[ConfiguracionNotificacion]  WITH CHECK ADD  CONSTRAINT [CK_ConfiguracionNotificacion_canal] CHECK  (([canal]=N'EMAIL' OR [canal]=N'WEB'))
GO
ALTER TABLE [dbo].[ConfiguracionNotificacion] CHECK CONSTRAINT [CK_ConfiguracionNotificacion_canal]
GO
ALTER TABLE [dbo].[ConfiguracionNotificacion]  WITH CHECK ADD  CONSTRAINT [CK_ConfiguracionNotificacion_intervalo] CHECK  (([intervaloMinutos]>(0)))
GO
ALTER TABLE [dbo].[ConfiguracionNotificacion] CHECK CONSTRAINT [CK_ConfiguracionNotificacion_intervalo]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ConsentimientoUsuario](
	[idConsentimiento] [uniqueidentifier] NOT NULL,
	[idUsuario] [uniqueidentifier] NOT NULL,
	[tipo] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[version] [nvarchar](20) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[estado] [nvarchar](20) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaHora] [datetime2](3) NOT NULL,
 CONSTRAINT [PK_ConsentimientoUsuario] PRIMARY KEY CLUSTERED 
(
	[idConsentimiento] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
SET ANSI_PADDING ON

GO
CREATE NONCLUSTERED INDEX [IX_ConsentimientoUsuario_usuario_tipo_fecha] ON [dbo].[ConsentimientoUsuario]
(
	[idUsuario] ASC,
	[tipo] ASC,
	[fechaHora] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
ALTER TABLE [dbo].[ConsentimientoUsuario] ADD  CONSTRAINT [DF_ConsentimientoUsuario_id]  DEFAULT (newid()) FOR [idConsentimiento]
GO
ALTER TABLE [dbo].[ConsentimientoUsuario] ADD  CONSTRAINT [DF_ConsentimientoUsuario_fechaHora]  DEFAULT (sysutcdatetime()) FOR [fechaHora]
GO
ALTER TABLE [dbo].[ConsentimientoUsuario]  WITH CHECK ADD  CONSTRAINT [CK_ConsentimientoUsuario_estado] CHECK  (([estado]=N'ACEPTADO' OR [estado]=N'REVOCADO'))
GO
ALTER TABLE [dbo].[ConsentimientoUsuario] CHECK CONSTRAINT [CK_ConsentimientoUsuario_estado]
GO
ALTER TABLE [dbo].[ConsentimientoUsuario]  WITH CHECK ADD  CONSTRAINT [CK_ConsentimientoUsuario_tipo] CHECK  (([tipo]=N'POLITICA_PRIVACIDAD' OR [tipo]=N'DATOS_EXPERIMENTALES'))
GO
ALTER TABLE [dbo].[ConsentimientoUsuario] CHECK CONSTRAINT [CK_ConsentimientoUsuario_tipo]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[CredencialLocal](
	[idCredencialLocal] [uniqueidentifier] NOT NULL,
	[idUsuario] [uniqueidentifier] NOT NULL,
	[passwordHash] [nvarchar](255) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[requiereCambioPassword] [bit] NOT NULL,
	[intentosFallidosConsecutivos] [tinyint] NOT NULL,
	[fechaUltimoIntentoFallido] [datetime2](3) NULL,
	[bloqueadoHasta] [datetime2](3) NULL,
	[fechaUltimoCambioPassword] [datetime2](3) NULL,
	[fechaCreacion] [datetime2](3) NOT NULL,
	[fechaActualizacion] [datetime2](3) NOT NULL,
 CONSTRAINT [PK_CredencialLocal] PRIMARY KEY CLUSTERED 
(
	[idCredencialLocal] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
 CONSTRAINT [UQ_CredencialLocal_idUsuario] UNIQUE NONCLUSTERED 
(
	[idUsuario] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
ALTER TABLE [dbo].[CredencialLocal] ADD  CONSTRAINT [DF_CredencialLocal_id]  DEFAULT (newid()) FOR [idCredencialLocal]
GO
ALTER TABLE [dbo].[CredencialLocal] ADD  CONSTRAINT [DF_CredencialLocal_requiereCambio]  DEFAULT ((0)) FOR [requiereCambioPassword]
GO
ALTER TABLE [dbo].[CredencialLocal] ADD  CONSTRAINT [DF_CredencialLocal_intentos]  DEFAULT ((0)) FOR [intentosFallidosConsecutivos]
GO
ALTER TABLE [dbo].[CredencialLocal] ADD  CONSTRAINT [DF_CredencialLocal_fechaCreacion]  DEFAULT (sysutcdatetime()) FOR [fechaCreacion]
GO
ALTER TABLE [dbo].[CredencialLocal] ADD  CONSTRAINT [DF_CredencialLocal_fechaActualizacion]  DEFAULT (sysutcdatetime()) FOR [fechaActualizacion]
GO
ALTER TABLE [dbo].[CredencialLocal]  WITH CHECK ADD  CONSTRAINT [CK_CredencialLocal_intentos] CHECK  (([intentosFallidosConsecutivos]>=(0) AND [intentosFallidosConsecutivos]<=(3)))
GO
ALTER TABLE [dbo].[CredencialLocal] CHECK CONSTRAINT [CK_CredencialLocal_intentos]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[Dispositivo](
	[idDispositivo] [uniqueidentifier] NOT NULL,
	[codigoDispositivo] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[nombre] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NULL,
	[modelo] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NULL,
	[modeloSensor] [nvarchar](20) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[versionFirmware] [nvarchar](50) COLLATE Modern_Spanish_CI_AS NULL,
	[estado] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[idInstitucionAsignada] [uniqueidentifier] NULL,
	[idInstitucionUsuarioResponsable] [uniqueidentifier] NULL,
	[fechaRegistro] [datetime2](3) NOT NULL,
	[fechaAsignacionInstitucional] [datetime2](3) NULL,
 CONSTRAINT [PK_Dispositivo] PRIMARY KEY CLUSTERED 
(
	[idDispositivo] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
 CONSTRAINT [UQ_Dispositivo_codigo] UNIQUE NONCLUSTERED 
(
	[codigoDispositivo] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
ALTER TABLE [dbo].[Dispositivo] ADD  CONSTRAINT [DF_Dispositivo_id]  DEFAULT (newid()) FOR [idDispositivo]
GO
ALTER TABLE [dbo].[Dispositivo] ADD  CONSTRAINT [DF_Dispositivo_estado]  DEFAULT (N'OPERATIVO') FOR [estado]
GO
ALTER TABLE [dbo].[Dispositivo] ADD  CONSTRAINT [DF_Dispositivo_fechaRegistro]  DEFAULT (sysutcdatetime()) FOR [fechaRegistro]
GO
ALTER TABLE [dbo].[Dispositivo]  WITH CHECK ADD  CONSTRAINT [CK_Dispositivo_estado] CHECK  (([estado]=N'BAJA' OR [estado]=N'FUERA_DE_SERVICIO' OR [estado]=N'EN_MANTENIMIENTO' OR [estado]=N'OPERATIVO'))
GO
ALTER TABLE [dbo].[Dispositivo] CHECK CONSTRAINT [CK_Dispositivo_estado]
GO
ALTER TABLE [dbo].[Dispositivo]  WITH CHECK ADD  CONSTRAINT [CK_Dispositivo_modeloSensor] CHECK  (([modeloSensor]=N'MAX30102' OR [modeloSensor]=N'MAX30100'))
GO
ALTER TABLE [dbo].[Dispositivo] CHECK CONSTRAINT [CK_Dispositivo_modeloSensor]
GO
ALTER TABLE [dbo].[Dispositivo]  WITH CHECK ADD  CONSTRAINT [CK_Dispositivo_responsableRequiereInstitucion] CHECK  (([idInstitucionUsuarioResponsable] IS NULL OR [idInstitucionAsignada] IS NOT NULL))
GO
ALTER TABLE [dbo].[Dispositivo] CHECK CONSTRAINT [CK_Dispositivo_responsableRequiereInstitucion]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[EnvioResultado](
	[idEnvioResultado] [uniqueidentifier] NOT NULL,
	[idMedicion] [uniqueidentifier] NOT NULL,
	[correoDestino] [nvarchar](254) COLLATE Modern_Spanish_CI_AS NULL,
	[estadoEnvio] [nvarchar](20) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaSolicitud] [datetime2](3) NOT NULL,
	[fechaEnvio] [datetime2](3) NULL,
	[detalleError] [nvarchar](500) COLLATE Modern_Spanish_CI_AS NULL,
 CONSTRAINT [PK_EnvioResultado] PRIMARY KEY CLUSTERED 
(
	[idEnvioResultado] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
ALTER TABLE [dbo].[EnvioResultado] ADD  CONSTRAINT [DF_EnvioResultado_id]  DEFAULT (newid()) FOR [idEnvioResultado]
GO
ALTER TABLE [dbo].[EnvioResultado] ADD  CONSTRAINT [DF_EnvioResultado_estado]  DEFAULT (N'PENDIENTE') FOR [estadoEnvio]
GO
ALTER TABLE [dbo].[EnvioResultado] ADD  CONSTRAINT [DF_EnvioResultado_fechaSolicitud]  DEFAULT (sysutcdatetime()) FOR [fechaSolicitud]
GO
ALTER TABLE [dbo].[EnvioResultado]  WITH CHECK ADD  CONSTRAINT [CK_EnvioResultado_enviado] CHECK  (([estadoEnvio]<>N'ENVIADO' OR [fechaEnvio] IS NOT NULL AND [correoDestino] IS NULL))
GO
ALTER TABLE [dbo].[EnvioResultado] CHECK CONSTRAINT [CK_EnvioResultado_enviado]
GO
ALTER TABLE [dbo].[EnvioResultado]  WITH CHECK ADD  CONSTRAINT [CK_EnvioResultado_estado] CHECK  (([estadoEnvio]=N'FALLIDO' OR [estadoEnvio]=N'ENVIADO' OR [estadoEnvio]=N'PENDIENTE'))
GO
ALTER TABLE [dbo].[EnvioResultado] CHECK CONSTRAINT [CK_EnvioResultado_estado]
GO
ALTER TABLE [dbo].[EnvioResultado]  WITH CHECK ADD  CONSTRAINT [CK_EnvioResultado_pendiente] CHECK  (([estadoEnvio]<>N'PENDIENTE' OR [correoDestino] IS NOT NULL))
GO
ALTER TABLE [dbo].[EnvioResultado] CHECK CONSTRAINT [CK_EnvioResultado_pendiente]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[FactorMfa](
	[idFactorMfa] [uniqueidentifier] NOT NULL,
	[idUsuario] [uniqueidentifier] NOT NULL,
	[tipo] [nvarchar](20) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[secretoCifrado] [nvarchar](500) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[habilitado] [bit] NOT NULL,
	[ultimoPasoUsado] [bigint] NULL,
	[intentosFallidosConsecutivos] [tinyint] NOT NULL,
	[bloqueadoHasta] [datetime2](3) NULL,
	[fechaCreacion] [datetime2](3) NOT NULL,
	[fechaConfirmacion] [datetime2](3) NULL,
 CONSTRAINT [PK_FactorMfa] PRIMARY KEY CLUSTERED 
(
	[idFactorMfa] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
 CONSTRAINT [UQ_FactorMfa_idUsuario] UNIQUE NONCLUSTERED 
(
	[idUsuario] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
ALTER TABLE [dbo].[FactorMfa] ADD  CONSTRAINT [DF_FactorMfa_id]  DEFAULT (newid()) FOR [idFactorMfa]
GO
ALTER TABLE [dbo].[FactorMfa] ADD  CONSTRAINT [DF_FactorMfa_tipo]  DEFAULT (N'TOTP') FOR [tipo]
GO
ALTER TABLE [dbo].[FactorMfa] ADD  CONSTRAINT [DF_FactorMfa_habilitado]  DEFAULT ((0)) FOR [habilitado]
GO
ALTER TABLE [dbo].[FactorMfa] ADD  CONSTRAINT [DF_FactorMfa_intentos]  DEFAULT ((0)) FOR [intentosFallidosConsecutivos]
GO
ALTER TABLE [dbo].[FactorMfa] ADD  CONSTRAINT [DF_FactorMfa_fechaCreacion]  DEFAULT (sysutcdatetime()) FOR [fechaCreacion]
GO
ALTER TABLE [dbo].[FactorMfa]  WITH CHECK ADD  CONSTRAINT [CK_FactorMfa_confirmacion] CHECK  (([habilitado]=(0) OR [fechaConfirmacion] IS NOT NULL))
GO
ALTER TABLE [dbo].[FactorMfa] CHECK CONSTRAINT [CK_FactorMfa_confirmacion]
GO
ALTER TABLE [dbo].[FactorMfa]  WITH CHECK ADD  CONSTRAINT [CK_FactorMfa_intentos] CHECK  (([intentosFallidosConsecutivos]>=(0) AND [intentosFallidosConsecutivos]<=(5)))
GO
ALTER TABLE [dbo].[FactorMfa] CHECK CONSTRAINT [CK_FactorMfa_intentos]
GO
ALTER TABLE [dbo].[FactorMfa]  WITH CHECK ADD  CONSTRAINT [CK_FactorMfa_tipo] CHECK  (([tipo]=N'TOTP'))
GO
ALTER TABLE [dbo].[FactorMfa] CHECK CONSTRAINT [CK_FactorMfa_tipo]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[Grupo](
	[idGrupo] [uniqueidentifier] NOT NULL,
	[nombre] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[descripcion] [nvarchar](500) COLLATE Modern_Spanish_CI_AS NULL,
	[estado] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaCreacion] [datetime2](3) NOT NULL,
	[fechaActualizacion] [datetime2](3) NOT NULL,
 CONSTRAINT [PK_Grupo] PRIMARY KEY CLUSTERED 
(
	[idGrupo] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
ALTER TABLE [dbo].[Grupo] ADD  CONSTRAINT [DF_Grupo_id]  DEFAULT (newid()) FOR [idGrupo]
GO
ALTER TABLE [dbo].[Grupo] ADD  CONSTRAINT [DF_Grupo_estado]  DEFAULT (N'ACTIVO') FOR [estado]
GO
ALTER TABLE [dbo].[Grupo] ADD  CONSTRAINT [DF_Grupo_fechaCreacion]  DEFAULT (sysutcdatetime()) FOR [fechaCreacion]
GO
ALTER TABLE [dbo].[Grupo] ADD  CONSTRAINT [DF_Grupo_fechaActualizacion]  DEFAULT (sysutcdatetime()) FOR [fechaActualizacion]
GO
ALTER TABLE [dbo].[Grupo]  WITH CHECK ADD  CONSTRAINT [CK_Grupo_estado] CHECK  (([estado]=N'CERRADO' OR [estado]=N'INACTIVO' OR [estado]=N'ACTIVO'))
GO
ALTER TABLE [dbo].[Grupo] CHECK CONSTRAINT [CK_Grupo_estado]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[GrupoUsuario](
	[idGrupoUsuario] [uniqueidentifier] NOT NULL,
	[idGrupo] [uniqueidentifier] NOT NULL,
	[idUsuario] [uniqueidentifier] NOT NULL,
	[rolGrupo] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[estadoRelacion] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[nivelComparticion] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaInvitacion] [datetime2](3) NOT NULL,
	[fechaIncorporacion] [datetime2](3) NULL,
	[fechaBaja] [datetime2](3) NULL,
	[visualiza] [bit] NOT NULL,
	[compartePerfil] [bit] NOT NULL,
	[comparteUltimaMedicion] [bit] NOT NULL,
	[comparteHistorial] [bit] NOT NULL,
	[notificaMedicion] [bit] NOT NULL,
 CONSTRAINT [PK_GrupoUsuario] PRIMARY KEY CLUSTERED 
(
	[idGrupoUsuario] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
CREATE UNIQUE NONCLUSTERED INDEX [UX_GrupoUsuario_administrador] ON [dbo].[GrupoUsuario]
(
	[idGrupo] ASC
)
WHERE ([rolGrupo]=N'PROPIETARIO' AND [estadoRelacion]=N'ACTIVO')
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
CREATE UNIQUE NONCLUSTERED INDEX [UX_GrupoUsuario_grupoActivo] ON [dbo].[GrupoUsuario]
(
	[idUsuario] ASC
)
WHERE ([estadoRelacion]=N'ACTIVO')
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
CREATE UNIQUE NONCLUSTERED INDEX [UX_GrupoUsuario_vinculoVigente] ON [dbo].[GrupoUsuario]
(
	[idGrupo] ASC,
	[idUsuario] ASC
)
WHERE ([estadoRelacion]<>N'BAJA')
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
ALTER TABLE [dbo].[GrupoUsuario] ADD  CONSTRAINT [DF_GrupoUsuario_id]  DEFAULT (newid()) FOR [idGrupoUsuario]
GO
ALTER TABLE [dbo].[GrupoUsuario] ADD  CONSTRAINT [DF_GrupoUsuario_rol]  DEFAULT (N'MIEMBRO') FOR [rolGrupo]
GO
ALTER TABLE [dbo].[GrupoUsuario] ADD  CONSTRAINT [DF_GrupoUsuario_estado]  DEFAULT (N'PENDIENTE') FOR [estadoRelacion]
GO
ALTER TABLE [dbo].[GrupoUsuario] ADD  CONSTRAINT [DF_GrupoUsuario_nivel]  DEFAULT (N'NINGUNA') FOR [nivelComparticion]
GO
ALTER TABLE [dbo].[GrupoUsuario] ADD  CONSTRAINT [DF_GrupoUsuario_fechaInvitacion]  DEFAULT (sysutcdatetime()) FOR [fechaInvitacion]
GO
ALTER TABLE [dbo].[GrupoUsuario] ADD  CONSTRAINT [DF_GrupoUsuario_visualiza]  DEFAULT ((1)) FOR [visualiza]
GO
ALTER TABLE [dbo].[GrupoUsuario] ADD  CONSTRAINT [DF_GrupoUsuario_compartePerfil]  DEFAULT ((0)) FOR [compartePerfil]
GO
ALTER TABLE [dbo].[GrupoUsuario] ADD  CONSTRAINT [DF_GrupoUsuario_comparteUltimaMedicion]  DEFAULT ((0)) FOR [comparteUltimaMedicion]
GO
ALTER TABLE [dbo].[GrupoUsuario] ADD  CONSTRAINT [DF_GrupoUsuario_comparteHistorial]  DEFAULT ((0)) FOR [comparteHistorial]
GO
ALTER TABLE [dbo].[GrupoUsuario] ADD  CONSTRAINT [DF_GrupoUsuario_notificaMedicion]  DEFAULT ((0)) FOR [notificaMedicion]
GO
ALTER TABLE [dbo].[GrupoUsuario]  WITH CHECK ADD  CONSTRAINT [CK_GrupoUsuario_baja] CHECK  (([estadoRelacion]<>N'BAJA' OR [fechaBaja] IS NOT NULL))
GO
ALTER TABLE [dbo].[GrupoUsuario] CHECK CONSTRAINT [CK_GrupoUsuario_baja]
GO
ALTER TABLE [dbo].[GrupoUsuario]  WITH CHECK ADD  CONSTRAINT [CK_GrupoUsuario_estado] CHECK  (([estadoRelacion]=N'BAJA' OR [estadoRelacion]=N'SUSPENDIDO' OR [estadoRelacion]=N'ACTIVO' OR [estadoRelacion]=N'PENDIENTE'))
GO
ALTER TABLE [dbo].[GrupoUsuario] CHECK CONSTRAINT [CK_GrupoUsuario_estado]
GO
ALTER TABLE [dbo].[GrupoUsuario]  WITH CHECK ADD  CONSTRAINT [CK_GrupoUsuario_incorporacion] CHECK  (([estadoRelacion]<>N'ACTIVO' OR [fechaIncorporacion] IS NOT NULL))
GO
ALTER TABLE [dbo].[GrupoUsuario] CHECK CONSTRAINT [CK_GrupoUsuario_incorporacion]
GO
ALTER TABLE [dbo].[GrupoUsuario]  WITH CHECK ADD  CONSTRAINT [CK_GrupoUsuario_nivel] CHECK  (([nivelComparticion]=N'MEDICION_COMPLETA' OR [nivelComparticion]=N'SOLO_MOMENTO' OR [nivelComparticion]=N'NINGUNA'))
GO
ALTER TABLE [dbo].[GrupoUsuario] CHECK CONSTRAINT [CK_GrupoUsuario_nivel]
GO
ALTER TABLE [dbo].[GrupoUsuario]  WITH CHECK ADD  CONSTRAINT [CK_GrupoUsuario_rol] CHECK  (([rolGrupo]=N'MIEMBRO' OR [rolGrupo]=N'MODERADOR' OR [rolGrupo]=N'PROPIETARIO'))
GO
ALTER TABLE [dbo].[GrupoUsuario] CHECK CONSTRAINT [CK_GrupoUsuario_rol]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[IdentidadExterna](
	[idIdentidadExterna] [uniqueidentifier] NOT NULL,
	[idUsuario] [uniqueidentifier] NOT NULL,
	[proveedor] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[subjectProveedor] [nvarchar](255) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[emailProveedor] [nvarchar](254) COLLATE Modern_Spanish_CI_AS NULL,
	[emailVerificado] [bit] NOT NULL,
	[fechaVinculacion] [datetime2](3) NOT NULL,
	[ultimoAcceso] [datetime2](3) NULL,
 CONSTRAINT [PK_IdentidadExterna] PRIMARY KEY CLUSTERED 
(
	[idIdentidadExterna] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
 CONSTRAINT [UQ_IdentidadExterna_proveedor_subject] UNIQUE NONCLUSTERED 
(
	[proveedor] ASC,
	[subjectProveedor] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
ALTER TABLE [dbo].[IdentidadExterna] ADD  CONSTRAINT [DF_IdentidadExterna_id]  DEFAULT (newid()) FOR [idIdentidadExterna]
GO
ALTER TABLE [dbo].[IdentidadExterna] ADD  CONSTRAINT [DF_IdentidadExterna_emailVerificado]  DEFAULT ((0)) FOR [emailVerificado]
GO
ALTER TABLE [dbo].[IdentidadExterna] ADD  CONSTRAINT [DF_IdentidadExterna_fechaVinculacion]  DEFAULT (sysutcdatetime()) FOR [fechaVinculacion]
GO
ALTER TABLE [dbo].[IdentidadExterna]  WITH CHECK ADD  CONSTRAINT [CK_IdentidadExterna_proveedor] CHECK  (([proveedor]=N'GOOGLE'))
GO
ALTER TABLE [dbo].[IdentidadExterna] CHECK CONSTRAINT [CK_IdentidadExterna_proveedor]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[Institucion](
	[idInstitucion] [uniqueidentifier] NOT NULL,
	[tipoIdentificadorLegal] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[identificadorLegal] [nvarchar](50) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[nombre] [nvarchar](150) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[tipoInstitucion] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[descripcion] [nvarchar](500) COLLATE Modern_Spanish_CI_AS NULL,
	[estado] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaCreacion] [datetime2](3) NOT NULL,
	[fechaActualizacion] [datetime2](3) NOT NULL,
	[cantidadReaperturas] [int] NOT NULL,
	[fechaUltimaReapertura] [datetime2](3) NULL,
	[capacidadMaximaUsuarios] [int] NOT NULL,
	[cierreAdministrativo] [bit] NOT NULL,
	[fechaCierreAdministrativo] [datetime2](3) NULL,
	[idUsuarioCierreAdministrativo] [uniqueidentifier] NULL,
	[motivoCierreAdministrativo] [nvarchar](300) COLLATE Modern_Spanish_CI_AS NULL,
 CONSTRAINT [PK_Institucion] PRIMARY KEY CLUSTERED 
(
	[idInstitucion] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
 CONSTRAINT [UQ_Institucion_identificadorLegal] UNIQUE NONCLUSTERED 
(
	[identificadorLegal] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
ALTER TABLE [dbo].[Institucion] ADD  CONSTRAINT [DF_Institucion_id]  DEFAULT (newid()) FOR [idInstitucion]
GO
ALTER TABLE [dbo].[Institucion] ADD  CONSTRAINT [DF_Institucion_tipoIdentificador]  DEFAULT (N'CUIT') FOR [tipoIdentificadorLegal]
GO
ALTER TABLE [dbo].[Institucion] ADD  CONSTRAINT [DF_Institucion_estado]  DEFAULT (N'ACTIVA') FOR [estado]
GO
ALTER TABLE [dbo].[Institucion] ADD  CONSTRAINT [DF_Institucion_fechaCreacion]  DEFAULT (sysutcdatetime()) FOR [fechaCreacion]
GO
ALTER TABLE [dbo].[Institucion] ADD  CONSTRAINT [DF_Institucion_fechaActualizacion]  DEFAULT (sysutcdatetime()) FOR [fechaActualizacion]
GO
ALTER TABLE [dbo].[Institucion] ADD  CONSTRAINT [DF_Institucion_cantidadReaperturas]  DEFAULT ((0)) FOR [cantidadReaperturas]
GO
ALTER TABLE [dbo].[Institucion] ADD  CONSTRAINT [DF_Institucion_capacidadMaximaUsuarios]  DEFAULT ((1000)) FOR [capacidadMaximaUsuarios]
GO
ALTER TABLE [dbo].[Institucion] ADD  CONSTRAINT [DF_Institucion_cierreAdministrativo]  DEFAULT ((0)) FOR [cierreAdministrativo]
GO
ALTER TABLE [dbo].[Institucion]  WITH CHECK ADD  CONSTRAINT [CK_Institucion_cantidadReaperturas] CHECK  (([cantidadReaperturas]>=(0)))
GO
ALTER TABLE [dbo].[Institucion] CHECK CONSTRAINT [CK_Institucion_cantidadReaperturas]
GO
ALTER TABLE [dbo].[Institucion]  WITH CHECK ADD  CONSTRAINT [CK_Institucion_capacidadMaximaUsuarios] CHECK  (([capacidadMaximaUsuarios]>(0)))
GO
ALTER TABLE [dbo].[Institucion] CHECK CONSTRAINT [CK_Institucion_capacidadMaximaUsuarios]
GO
ALTER TABLE [dbo].[Institucion]  WITH CHECK ADD  CONSTRAINT [CK_Institucion_cierreAdministrativo] CHECK  (([cierreAdministrativo]=(0) AND [fechaCierreAdministrativo] IS NULL AND [idUsuarioCierreAdministrativo] IS NULL AND [motivoCierreAdministrativo] IS NULL OR [cierreAdministrativo]=(1) AND [estado]=N'CERRADA' AND [fechaCierreAdministrativo] IS NOT NULL AND [idUsuarioCierreAdministrativo] IS NOT NULL AND [motivoCierreAdministrativo] IS NOT NULL))
GO
ALTER TABLE [dbo].[Institucion] CHECK CONSTRAINT [CK_Institucion_cierreAdministrativo]
GO
ALTER TABLE [dbo].[Institucion]  WITH CHECK ADD  CONSTRAINT [CK_Institucion_estado] CHECK  (([estado]=N'CERRADA' OR [estado]=N'INACTIVA' OR [estado]=N'ACTIVA'))
GO
ALTER TABLE [dbo].[Institucion] CHECK CONSTRAINT [CK_Institucion_estado]
GO
ALTER TABLE [dbo].[Institucion]  WITH CHECK ADD  CONSTRAINT [CK_Institucion_tipo] CHECK  (([tipoInstitucion]=N'OTRO' OR [tipoInstitucion]=N'LABORATORIO' OR [tipoInstitucion]=N'CONSULTORIO' OR [tipoInstitucion]=N'CLINICA' OR [tipoInstitucion]=N'HOSPITAL'))
GO
ALTER TABLE [dbo].[Institucion] CHECK CONSTRAINT [CK_Institucion_tipo]
GO
ALTER TABLE [dbo].[Institucion]  WITH CHECK ADD  CONSTRAINT [CK_Institucion_tipoIdentificador] CHECK  (([tipoIdentificadorLegal]=N'OTRO' OR [tipoIdentificadorLegal]=N'CUIT'))
GO
ALTER TABLE [dbo].[Institucion] CHECK CONSTRAINT [CK_Institucion_tipoIdentificador]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[InstitucionUsuario](
	[idInstitucionUsuario] [uniqueidentifier] NOT NULL,
	[idInstitucion] [uniqueidentifier] NOT NULL,
	[idUsuarioInvitado] [uniqueidentifier] NOT NULL,
	[rolInstitucion] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[matriculaProfesional] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NULL,
	[legajoInstitucional] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NULL,
	[estadoRelacion] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[origenVinculo] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[idUsuarioInvitador] [uniqueidentifier] NULL,
	[fechaInvitacion] [datetime2](3) NOT NULL,
	[fechaIncorporacion] [datetime2](3) NULL,
	[fechaBaja] [datetime2](3) NULL,
	[nombreProfesionalHistorico] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NULL,
	[apellidoProfesionalHistorico] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NULL,
	[funcionProfesional] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NULL,
	[fechaMinimizacionDatos] [datetime2](3) NULL,
 CONSTRAINT [PK_InstitucionUsuario] PRIMARY KEY CLUSTERED 
(
	[idInstitucionUsuario] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
CREATE UNIQUE NONCLUSTERED INDEX [UX_InstitucionUsuario_vinculoVigente] ON [dbo].[InstitucionUsuario]
(
	[idInstitucion] ASC,
	[idUsuarioInvitado] ASC
)
WHERE ([estadoRelacion]<>N'BAJA')
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
ALTER TABLE [dbo].[InstitucionUsuario] ADD  CONSTRAINT [DF_InstitucionUsuario_id]  DEFAULT (newid()) FOR [idInstitucionUsuario]
GO
ALTER TABLE [dbo].[InstitucionUsuario] ADD  CONSTRAINT [DF_InstitucionUsuario_estado]  DEFAULT (N'PENDIENTE') FOR [estadoRelacion]
GO
ALTER TABLE [dbo].[InstitucionUsuario] ADD  CONSTRAINT [DF_InstitucionUsuario_origen]  DEFAULT (N'INVITACION') FOR [origenVinculo]
GO
ALTER TABLE [dbo].[InstitucionUsuario] ADD  CONSTRAINT [DF_InstitucionUsuario_fechaInvitacion]  DEFAULT (sysutcdatetime()) FOR [fechaInvitacion]
GO
ALTER TABLE [dbo].[InstitucionUsuario]  WITH CHECK ADD  CONSTRAINT [CK_InstitucionUsuario_autoInvitacion] CHECK  (([idUsuarioInvitador] IS NULL OR [idUsuarioInvitador]<>[idUsuarioInvitado]))
GO
ALTER TABLE [dbo].[InstitucionUsuario] CHECK CONSTRAINT [CK_InstitucionUsuario_autoInvitacion]
GO
ALTER TABLE [dbo].[InstitucionUsuario]  WITH CHECK ADD  CONSTRAINT [CK_InstitucionUsuario_baja] CHECK  (([estadoRelacion]<>N'BAJA' OR [fechaBaja] IS NOT NULL))
GO
ALTER TABLE [dbo].[InstitucionUsuario] CHECK CONSTRAINT [CK_InstitucionUsuario_baja]
GO
ALTER TABLE [dbo].[InstitucionUsuario]  WITH CHECK ADD  CONSTRAINT [CK_InstitucionUsuario_estado] CHECK  (([estadoRelacion]=N'BAJA' OR [estadoRelacion]=N'SUSPENDIDO' OR [estadoRelacion]=N'ACTIVO' OR [estadoRelacion]=N'PENDIENTE'))
GO
ALTER TABLE [dbo].[InstitucionUsuario] CHECK CONSTRAINT [CK_InstitucionUsuario_estado]
GO
ALTER TABLE [dbo].[InstitucionUsuario]  WITH CHECK ADD  CONSTRAINT [CK_InstitucionUsuario_funcionProfesional] CHECK  (([funcionProfesional] IS NULL OR ([funcionProfesional]=N'MEDICO' OR [funcionProfesional]=N'ENFERMERO' OR [funcionProfesional]=N'OPERADOR')))
GO
ALTER TABLE [dbo].[InstitucionUsuario] CHECK CONSTRAINT [CK_InstitucionUsuario_funcionProfesional]
GO
ALTER TABLE [dbo].[InstitucionUsuario]  WITH CHECK ADD  CONSTRAINT [CK_InstitucionUsuario_incorporacion] CHECK  (([estadoRelacion]<>N'ACTIVO' OR [fechaIncorporacion] IS NOT NULL))
GO
ALTER TABLE [dbo].[InstitucionUsuario] CHECK CONSTRAINT [CK_InstitucionUsuario_incorporacion]
GO
ALTER TABLE [dbo].[InstitucionUsuario]  WITH CHECK ADD  CONSTRAINT [CK_InstitucionUsuario_invitador] CHECK  (([origenVinculo]=N'CREACION_INSTITUCION' OR [idUsuarioInvitador] IS NOT NULL))
GO
ALTER TABLE [dbo].[InstitucionUsuario] CHECK CONSTRAINT [CK_InstitucionUsuario_invitador]
GO
ALTER TABLE [dbo].[InstitucionUsuario]  WITH CHECK ADD  CONSTRAINT [CK_InstitucionUsuario_origen] CHECK  (([origenVinculo]=N'CREACION_CUENTA' OR [origenVinculo]=N'INVITACION' OR [origenVinculo]=N'CREACION_INSTITUCION'))
GO
ALTER TABLE [dbo].[InstitucionUsuario] CHECK CONSTRAINT [CK_InstitucionUsuario_origen]
GO
ALTER TABLE [dbo].[InstitucionUsuario]  WITH CHECK ADD  CONSTRAINT [CK_InstitucionUsuario_rol] CHECK  (([rolInstitucion]=N'OPERADOR' OR [rolInstitucion]=N'MODERADOR' OR [rolInstitucion]=N'PROPIETARIO'))
GO
ALTER TABLE [dbo].[InstitucionUsuario] CHECK CONSTRAINT [CK_InstitucionUsuario_rol]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[Matriz](
	[idMatriz] [uniqueidentifier] NOT NULL,
	[idInstitucion] [uniqueidentifier] NULL,
	[nombre] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[version] [nvarchar](50) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[ambito] [nvarchar](20) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaVigenciaDesde] [date] NOT NULL,
	[fechaVigenciaHasta] [date] NULL,
	[descripcion] [nvarchar](500) COLLATE Modern_Spanish_CI_AS NULL,
	[estado] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaCreacion] [datetime2](3) NOT NULL,
 CONSTRAINT [PK_Matriz] PRIMARY KEY CLUSTERED 
(
	[idMatriz] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
 CONSTRAINT [UQ_Matriz_version] UNIQUE NONCLUSTERED 
(
	[idInstitucion] ASC,
	[nombre] ASC,
	[version] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
SET ANSI_PADDING ON

GO
CREATE UNIQUE NONCLUSTERED INDEX [UX_Matriz_globalActiva] ON [dbo].[Matriz]
(
	[ambito] ASC
)
WHERE ([ambito]=N'GLOBAL' AND [estado]=N'ACTIVA')
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
CREATE UNIQUE NONCLUSTERED INDEX [UX_Matriz_institucionActiva] ON [dbo].[Matriz]
(
	[idInstitucion] ASC
)
WHERE ([ambito]=N'INSTITUCION' AND [estado]=N'ACTIVA')
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
ALTER TABLE [dbo].[Matriz] ADD  CONSTRAINT [DF_Matriz_id]  DEFAULT (newid()) FOR [idMatriz]
GO
ALTER TABLE [dbo].[Matriz] ADD  CONSTRAINT [DF_Matriz_ambito]  DEFAULT (N'GLOBAL') FOR [ambito]
GO
ALTER TABLE [dbo].[Matriz] ADD  CONSTRAINT [DF_Matriz_estado]  DEFAULT (N'BORRADOR') FOR [estado]
GO
ALTER TABLE [dbo].[Matriz] ADD  CONSTRAINT [DF_Matriz_fechaCreacion]  DEFAULT (sysutcdatetime()) FOR [fechaCreacion]
GO
ALTER TABLE [dbo].[Matriz]  WITH CHECK ADD  CONSTRAINT [CK_Matriz_ambito] CHECK  (([ambito]=N'GLOBAL' AND [idInstitucion] IS NULL OR [ambito]=N'INSTITUCION' AND [idInstitucion] IS NOT NULL))
GO
ALTER TABLE [dbo].[Matriz] CHECK CONSTRAINT [CK_Matriz_ambito]
GO
ALTER TABLE [dbo].[Matriz]  WITH CHECK ADD  CONSTRAINT [CK_Matriz_estado] CHECK  (([estado]=N'ARCHIVADA' OR [estado]=N'INACTIVA' OR [estado]=N'ACTIVA' OR [estado]=N'BORRADOR'))
GO
ALTER TABLE [dbo].[Matriz] CHECK CONSTRAINT [CK_Matriz_estado]
GO
ALTER TABLE [dbo].[Matriz]  WITH CHECK ADD  CONSTRAINT [CK_Matriz_vigencia] CHECK  (([fechaVigenciaHasta] IS NULL OR [fechaVigenciaHasta]>=[fechaVigenciaDesde]))
GO
ALTER TABLE [dbo].[Matriz] CHECK CONSTRAINT [CK_Matriz_vigencia]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[Medicion](
	[idMedicion] [uniqueidentifier] NOT NULL,
	[idPerfilMedicion] [uniqueidentifier] NOT NULL,
	[idDispositivo] [uniqueidentifier] NOT NULL,
	[idMatriz] [uniqueidentifier] NULL,
	[modoMedicion] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[estadoMedicion] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaHoraInicio] [datetime2](3) NOT NULL,
	[fechaHoraFin] [datetime2](3) NULL,
	[fechaHoraUltimaComida] [datetime2](3) NULL,
	[condicionComida] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[edadAlMomento] [smallint] NULL,
	[sexoModelo] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NULL,
	[versionFirmwareAlMomento] [nvarchar](50) COLLATE Modern_Spanish_CI_AS NULL,
	[modeloSensorAlMomento] [nvarchar](20) COLLATE Modern_Spanish_CI_AS NULL,
	[versionAlgoritmo] [nvarchar](50) COLLATE Modern_Spanish_CI_AS NULL,
	[calidadSenal] [decimal](6, 3) NULL,
	[spo2] [decimal](5, 2) NULL,
	[frecuenciaCardiaca] [smallint] NULL,
	[glucosaEstimada] [decimal](8, 2) NULL,
	[observacion] [nvarchar](500) COLLATE Modern_Spanish_CI_AS NULL,
	[minutosDesdeUltimaComida]  AS (datediff(minute,[fechaHoraUltimaComida],[fechaHoraInicio])),
	[duracionMs]  AS (datediff_big(millisecond,[fechaHoraInicio],[fechaHoraFin])),
	[origenGlucosa] [nvarchar](20) COLLATE Modern_Spanish_CI_AS NULL,
	[glucosaDispositivo] [decimal](8, 2) NULL,
	[unidadGlucosa] [nvarchar](10) COLLATE Modern_Spanish_CI_AS NULL,
	[indiceOptico] [decimal](10, 5) NULL,
	[lecturasEstabilizadas] [smallint] NULL,
	[idReglaMatriz] [uniqueidentifier] NULL,
	[fechaVencimientoRetencion] [datetime2](3) NULL,
 CONSTRAINT [PK_Medicion] PRIMARY KEY CLUSTERED 
(
	[idMedicion] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
SET ANSI_PADDING ON

GO
CREATE NONCLUSTERED INDEX [IX_Medicion_estado_fin] ON [dbo].[Medicion]
(
	[estadoMedicion] ASC,
	[fechaHoraFin] ASC
)
INCLUDE([idPerfilMedicion],[fechaHoraInicio]) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
CREATE NONCLUSTERED INDEX [IX_Medicion_vencimientoRetencion] ON [dbo].[Medicion]
(
	[fechaVencimientoRetencion] ASC
)
WHERE ([fechaVencimientoRetencion] IS NOT NULL)
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
ALTER TABLE [dbo].[Medicion] ADD  CONSTRAINT [DF_Medicion_id]  DEFAULT (newid()) FOR [idMedicion]
GO
ALTER TABLE [dbo].[Medicion] ADD  CONSTRAINT [DF_Medicion_modo]  DEFAULT (N'OXIMETRIA') FOR [modoMedicion]
GO
ALTER TABLE [dbo].[Medicion] ADD  CONSTRAINT [DF_Medicion_estado]  DEFAULT (N'PENDIENTE') FOR [estadoMedicion]
GO
ALTER TABLE [dbo].[Medicion] ADD  CONSTRAINT [DF_Medicion_fechaHoraInicio]  DEFAULT (sysutcdatetime()) FOR [fechaHoraInicio]
GO
ALTER TABLE [dbo].[Medicion] ADD  CONSTRAINT [DF_Medicion_condicionComida]  DEFAULT (N'NO_INFORMADA') FOR [condicionComida]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_calidad] CHECK  (([calidadSenal] IS NULL OR [calidadSenal]>=(0)))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_calidad]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_condicionComida] CHECK  (([condicionComida]=N'NO_INFORMADA' OR [condicionComida]=N'POSTPRANDIAL' OR [condicionComida]=N'AYUNO'))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_condicionComida]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_demoSinEstimacion] CHECK  (([origenGlucosa] IS NULL OR [origenGlucosa]<>N'DEMO' OR [glucosaEstimada] IS NULL))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_demoSinEstimacion]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_edad] CHECK  (([edadAlMomento]>=(0) AND [edadAlMomento]<=(130)))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_edad]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_estado] CHECK  (([estadoMedicion]=N'CANCELADA' OR [estadoMedicion]=N'INVALIDA' OR [estadoMedicion]=N'COMPLETADA' OR [estadoMedicion]=N'PROCESANDO' OR [estadoMedicion]=N'ADQUIRIENDO' OR [estadoMedicion]=N'PENDIENTE'))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_estado]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_fc] CHECK  (([frecuenciaCardiaca] IS NULL OR [frecuenciaCardiaca]>(0)))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_fc]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_fechas] CHECK  (([fechaHoraFin] IS NULL OR [fechaHoraFin]>=[fechaHoraInicio]))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_fechas]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_glucosaCompletada] CHECK  ((NOT ([modoMedicion]=N'GLUCOSA_EXPERIMENTAL' AND [estadoMedicion]=N'COMPLETADA') OR [glucosaEstimada] IS NOT NULL OR [glucosaDispositivo] IS NOT NULL))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_glucosaCompletada]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_glucosaDispositivoOrigen] CHECK  (([glucosaDispositivo] IS NULL OR coalesce([origenGlucosa],N'')=N'DEMO' OR coalesce([origenGlucosa],N'')=N'EXPERIMENTAL'))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_glucosaDispositivoOrigen]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_glucosaDispositivoRango] CHECK  (([glucosaDispositivo] IS NULL OR [glucosaDispositivo]>=(0)))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_glucosaDispositivoRango]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_glucosaRango] CHECK  (([glucosaEstimada] IS NULL OR [glucosaEstimada]>=(0)))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_glucosaRango]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_glucosaTrazable] CHECK  (([glucosaEstimada] IS NULL OR [idMatriz] IS NOT NULL AND [versionAlgoritmo] IS NOT NULL))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_glucosaTrazable]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_indiceOptico] CHECK  (([indiceOptico] IS NULL OR [indiceOptico]>=(0)))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_indiceOptico]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_lecturas] CHECK  (([lecturasEstabilizadas] IS NULL OR [lecturasEstabilizadas]>(0)))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_lecturas]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_modeloSensor] CHECK  (([modeloSensorAlMomento] IS NULL OR ([modeloSensorAlMomento]=N'MAX30102' OR [modeloSensorAlMomento]=N'MAX30100')))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_modeloSensor]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_modo] CHECK  (([modoMedicion]=N'GLUCOSA_EXPERIMENTAL' OR [modoMedicion]=N'OXIMETRIA'))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_modo]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_origenConGlucosa] CHECK  (([origenGlucosa] IS NULL OR [origenGlucosa]=N'SIN_CALIBRAR' OR [glucosaDispositivo] IS NOT NULL))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_origenConGlucosa]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_origenGlucosa] CHECK  (([origenGlucosa] IS NULL OR [origenGlucosa]=N'DEMO' OR [origenGlucosa]=N'EXPERIMENTAL' OR [origenGlucosa]=N'SIN_CALIBRAR'))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_origenGlucosa]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_oximetriaSinGlucosa] CHECK  (([modoMedicion]<>N'OXIMETRIA' OR [glucosaEstimada] IS NULL))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_oximetriaSinGlucosa]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_sexo] CHECK  (([sexoModelo]=N'MASCULINO' OR [sexoModelo]=N'FEMENINO'))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_sexo]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_spo2] CHECK  (([spo2] IS NULL OR [spo2]>=(0) AND [spo2]<=(100)))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_spo2]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [CK_Medicion_unidadGlucosa] CHECK  (([glucosaDispositivo] IS NULL OR coalesce([unidadGlucosa],N'')=N'mg/dL'))
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [CK_Medicion_unidadGlucosa]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[MedicionReferenciaCapilar](
	[idMedicionReferencia] [uniqueidentifier] NOT NULL,
	[idMedicion] [uniqueidentifier] NOT NULL,
	[glucosaReferencia] [decimal](8, 2) NOT NULL,
	[fechaHoraReferencia] [datetime2](3) NOT NULL,
	[marcaGlucometro] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NULL,
	[modeloGlucometro] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NULL,
	[observacion] [nvarchar](500) COLLATE Modern_Spanish_CI_AS NULL,
 CONSTRAINT [PK_MedicionReferenciaCapilar] PRIMARY KEY CLUSTERED 
(
	[idMedicionReferencia] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
 CONSTRAINT [UQ_MedicionReferenciaCapilar_medicion] UNIQUE NONCLUSTERED 
(
	[idMedicion] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
ALTER TABLE [dbo].[MedicionReferenciaCapilar] ADD  CONSTRAINT [DF_MedicionReferenciaCapilar_id]  DEFAULT (newid()) FOR [idMedicionReferencia]
GO
ALTER TABLE [dbo].[MedicionReferenciaCapilar]  WITH CHECK ADD  CONSTRAINT [CK_MedicionReferenciaCapilar_valor] CHECK  (([glucosaReferencia]>=(0)))
GO
ALTER TABLE [dbo].[MedicionReferenciaCapilar] CHECK CONSTRAINT [CK_MedicionReferenciaCapilar_valor]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[MuestraSensor](
	[idMuestraSensor] [uniqueidentifier] NOT NULL,
	[idMedicion] [uniqueidentifier] NOT NULL,
	[numeroMuestra] [int] NOT NULL,
	[tiempoRelativoMs] [int] NULL,
	[valorRed] [int] NOT NULL,
	[valorIR] [int] NOT NULL,
 CONSTRAINT [PK_MuestraSensor] PRIMARY KEY CLUSTERED 
(
	[idMuestraSensor] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
 CONSTRAINT [UQ_MuestraSensor_orden] UNIQUE NONCLUSTERED 
(
	[idMedicion] ASC,
	[numeroMuestra] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
ALTER TABLE [dbo].[MuestraSensor] ADD  CONSTRAINT [DF_MuestraSensor_id]  DEFAULT (newsequentialid()) FOR [idMuestraSensor]
GO
ALTER TABLE [dbo].[MuestraSensor]  WITH CHECK ADD  CONSTRAINT [CK_MuestraSensor_valores] CHECK  (([numeroMuestra]>=(0) AND [valorRed]>=(0) AND [valorIR]>=(0) AND ([tiempoRelativoMs] IS NULL OR [tiempoRelativoMs]>=(0))))
GO
ALTER TABLE [dbo].[MuestraSensor] CHECK CONSTRAINT [CK_MuestraSensor_valores]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[PerfilMedicion](
	[idPerfilMedicion] [uniqueidentifier] NOT NULL,
	[tipoPerfil] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[idUsuario] [uniqueidentifier] NULL,
	[idInstitucionUsuarioResponsable] [uniqueidentifier] NULL,
	[identificadorPseudonimo] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NULL,
	[nombre] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NULL,
	[apellido] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NULL,
	[dni] [nvarchar](20) COLLATE Modern_Spanish_CI_AS NULL,
	[fechaNacimiento] [date] NULL,
	[edadDeclarada] [smallint] NULL,
	[sexoModelo] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NULL,
	[fechaCreacion] [datetime2](3) NOT NULL,
	[fechaUltimaMedicion] [datetime2](3) NULL,
	[fechaExpiracionDatosPersonales] [datetime2](3) NULL,
	[fechaDepuracionDatosPersonales] [datetime2](3) NULL,
	[correoResultados] [nvarchar](254) COLLATE Modern_Spanish_CI_AS NULL,
	[fechaAutorizacionCorreo] [datetime2](3) NULL,
	[fechaExpiracionCorreo] [datetime2](3) NULL,
	[idInstitucion] [uniqueidentifier] NULL,
 CONSTRAINT [PK_PerfilMedicion] PRIMARY KEY CLUSTERED 
(
	[idPerfilMedicion] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
CREATE UNIQUE NONCLUSTERED INDEX [UX_PerfilMedicion_cohorte] ON [dbo].[PerfilMedicion]
(
	[idInstitucion] ASC
)
WHERE ([tipoPerfil]=N'COHORTE_ANONIMA')
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
CREATE UNIQUE NONCLUSTERED INDEX [UX_PerfilMedicion_consumidor] ON [dbo].[PerfilMedicion]
(
	[idUsuario] ASC
)
WHERE ([tipoPerfil]=N'CONSUMIDOR_FINAL')
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
SET ANSI_PADDING ON

GO
CREATE UNIQUE NONCLUSTERED INDEX [UX_PerfilMedicion_dniInstitucion] ON [dbo].[PerfilMedicion]
(
	[idInstitucion] ASC,
	[dni] ASC
)
WHERE ([idInstitucion] IS NOT NULL AND [dni] IS NOT NULL AND [tipoPerfil]=N'INSTITUCIONAL' AND [fechaExpiracionDatosPersonales] IS NULL AND [fechaDepuracionDatosPersonales] IS NULL)
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
ALTER TABLE [dbo].[PerfilMedicion] ADD  CONSTRAINT [DF_PerfilMedicion_id]  DEFAULT (newid()) FOR [idPerfilMedicion]
GO
ALTER TABLE [dbo].[PerfilMedicion] ADD  CONSTRAINT [DF_PerfilMedicion_fechaCreacion]  DEFAULT (sysutcdatetime()) FOR [fechaCreacion]
GO
ALTER TABLE [dbo].[PerfilMedicion]  WITH CHECK ADD  CONSTRAINT [CK_PerfilMedicion_coherenciaTipo] CHECK  (([tipoPerfil]=N'CONSUMIDOR_FINAL' AND [idUsuario] IS NOT NULL AND [idInstitucionUsuarioResponsable] IS NULL OR [tipoPerfil]=N'INSTITUCIONAL' AND [idUsuario] IS NULL AND [idInstitucionUsuarioResponsable] IS NOT NULL AND [identificadorPseudonimo] IS NOT NULL OR [tipoPerfil]=N'COHORTE_ANONIMA' AND [idUsuario] IS NULL AND [idInstitucionUsuarioResponsable] IS NULL AND [identificadorPseudonimo] IS NULL AND [nombre] IS NULL AND [apellido] IS NULL AND [dni] IS NULL AND [fechaNacimiento] IS NULL AND [edadDeclarada] IS NULL AND [idInstitucion] IS NOT NULL))
GO
ALTER TABLE [dbo].[PerfilMedicion] CHECK CONSTRAINT [CK_PerfilMedicion_coherenciaTipo]
GO
ALTER TABLE [dbo].[PerfilMedicion]  WITH CHECK ADD  CONSTRAINT [CK_PerfilMedicion_correoResultados] CHECK  (([correoResultados] IS NULL AND [fechaAutorizacionCorreo] IS NULL AND [fechaExpiracionCorreo] IS NULL OR [correoResultados] IS NOT NULL AND [fechaAutorizacionCorreo] IS NOT NULL AND [fechaExpiracionCorreo] IS NOT NULL))
GO
ALTER TABLE [dbo].[PerfilMedicion] CHECK CONSTRAINT [CK_PerfilMedicion_correoResultados]
GO
ALTER TABLE [dbo].[PerfilMedicion]  WITH CHECK ADD  CONSTRAINT [CK_PerfilMedicion_dniNormalizado] CHECK  (([dni] IS NULL OR NOT [dni] like N'%[^A-Z0-9]%'))
GO
ALTER TABLE [dbo].[PerfilMedicion] CHECK CONSTRAINT [CK_PerfilMedicion_dniNormalizado]
GO
ALTER TABLE [dbo].[PerfilMedicion]  WITH CHECK ADD  CONSTRAINT [CK_PerfilMedicion_edad] CHECK  (([edadDeclarada] IS NULL OR [edadDeclarada]>=(0) AND [edadDeclarada]<=(130)))
GO
ALTER TABLE [dbo].[PerfilMedicion] CHECK CONSTRAINT [CK_PerfilMedicion_edad]
GO
ALTER TABLE [dbo].[PerfilMedicion]  WITH CHECK ADD  CONSTRAINT [CK_PerfilMedicion_sexo] CHECK  (([sexoModelo]=N'MASCULINO' OR [sexoModelo]=N'FEMENINO'))
GO
ALTER TABLE [dbo].[PerfilMedicion] CHECK CONSTRAINT [CK_PerfilMedicion_sexo]
GO
ALTER TABLE [dbo].[PerfilMedicion]  WITH CHECK ADD  CONSTRAINT [CK_PerfilMedicion_tipo] CHECK  (([tipoPerfil]=N'INSTITUCIONAL' OR [tipoPerfil]=N'CONSUMIDOR_FINAL' OR [tipoPerfil]=N'COHORTE_ANONIMA'))
GO
ALTER TABLE [dbo].[PerfilMedicion] CHECK CONSTRAINT [CK_PerfilMedicion_tipo]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[PeriodoPrueba](
	[idPeriodoPrueba] [uniqueidentifier] NOT NULL,
	[idUsuario] [uniqueidentifier] NULL,
	[idInstitucion] [uniqueidentifier] NULL,
	[numeroPeriodo] [tinyint] NOT NULL,
	[origen] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaInicio] [datetime2](3) NOT NULL,
	[fechaFin] [datetime2](3) NOT NULL,
	[estado] [nvarchar](20) COLLATE Modern_Spanish_CI_AS NOT NULL,
 CONSTRAINT [PK_PeriodoPrueba] PRIMARY KEY CLUSTERED 
(
	[idPeriodoPrueba] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
ALTER TABLE [dbo].[PeriodoPrueba] ADD  CONSTRAINT [DF_PeriodoPrueba_id]  DEFAULT (newid()) FOR [idPeriodoPrueba]
GO
ALTER TABLE [dbo].[PeriodoPrueba] ADD  CONSTRAINT [DF_PeriodoPrueba_numero]  DEFAULT ((1)) FOR [numeroPeriodo]
GO
ALTER TABLE [dbo].[PeriodoPrueba] ADD  CONSTRAINT [DF_PeriodoPrueba_origen]  DEFAULT (N'PRIMER_ALTA') FOR [origen]
GO
ALTER TABLE [dbo].[PeriodoPrueba] ADD  CONSTRAINT [DF_PeriodoPrueba_fechaInicio]  DEFAULT (sysutcdatetime()) FOR [fechaInicio]
GO
ALTER TABLE [dbo].[PeriodoPrueba] ADD  CONSTRAINT [DF_PeriodoPrueba_estado]  DEFAULT (N'ACTIVO') FOR [estado]
GO
ALTER TABLE [dbo].[PeriodoPrueba]  WITH CHECK ADD  CONSTRAINT [CK_PeriodoPrueba_duenio] CHECK  (([idUsuario] IS NOT NULL AND [idInstitucion] IS NULL OR [idUsuario] IS NULL AND [idInstitucion] IS NOT NULL))
GO
ALTER TABLE [dbo].[PeriodoPrueba] CHECK CONSTRAINT [CK_PeriodoPrueba_duenio]
GO
ALTER TABLE [dbo].[PeriodoPrueba]  WITH CHECK ADD  CONSTRAINT [CK_PeriodoPrueba_duracion] CHECK  (([fechaFin]=dateadd(day,(7),[fechaInicio])))
GO
ALTER TABLE [dbo].[PeriodoPrueba] CHECK CONSTRAINT [CK_PeriodoPrueba_duracion]
GO
ALTER TABLE [dbo].[PeriodoPrueba]  WITH CHECK ADD  CONSTRAINT [CK_PeriodoPrueba_estado] CHECK  (([estado]=N'CANCELADO' OR [estado]=N'VENCIDO' OR [estado]=N'ACTIVO'))
GO
ALTER TABLE [dbo].[PeriodoPrueba] CHECK CONSTRAINT [CK_PeriodoPrueba_estado]
GO
ALTER TABLE [dbo].[PeriodoPrueba]  WITH CHECK ADD  CONSTRAINT [CK_PeriodoPrueba_numero] CHECK  (([idUsuario] IS NOT NULL AND [numeroPeriodo]=(1) OR [idInstitucion] IS NOT NULL AND ([numeroPeriodo]>=(1) AND [numeroPeriodo]<=(3))))
GO
ALTER TABLE [dbo].[PeriodoPrueba] CHECK CONSTRAINT [CK_PeriodoPrueba_numero]
GO
ALTER TABLE [dbo].[PeriodoPrueba]  WITH CHECK ADD  CONSTRAINT [CK_PeriodoPrueba_origen] CHECK  (([numeroPeriodo]=(1) AND [origen]=N'PRIMER_ALTA' OR [numeroPeriodo]>(1) AND [origen]=N'REACTIVACION'))
GO
ALTER TABLE [dbo].[PeriodoPrueba] CHECK CONSTRAINT [CK_PeriodoPrueba_origen]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
SET ANSI_PADDING ON
GO
CREATE TABLE [dbo].[PlanSuscripcion](
	[idPlan] [uniqueidentifier] NOT NULL,
	[nombre] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[tipoCliente] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[tipoPlan] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[cupoUsuarios] [int] NULL,
	[precioBase] [decimal](12, 2) NULL,
	[moneda] [char](3) COLLATE Modern_Spanish_CI_AS NULL,
	[requiereCanalVentas] [bit] NOT NULL,
	[estado] [nvarchar](20) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaVigenciaDesde] [date] NOT NULL,
	[fechaVigenciaHasta] [date] NULL,
	[descripcion] [nvarchar](500) COLLATE Modern_Spanish_CI_AS NULL,
 CONSTRAINT [PK_PlanSuscripcion] PRIMARY KEY CLUSTERED 
(
	[idPlan] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
 CONSTRAINT [UQ_PlanSuscripcion_nombre] UNIQUE NONCLUSTERED 
(
	[nombre] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
SET ANSI_PADDING OFF
GO
ALTER TABLE [dbo].[PlanSuscripcion] ADD  CONSTRAINT [DF_PlanSuscripcion_id]  DEFAULT (newid()) FOR [idPlan]
GO
ALTER TABLE [dbo].[PlanSuscripcion] ADD  CONSTRAINT [DF_PlanSuscripcion_moneda]  DEFAULT ('ARS') FOR [moneda]
GO
ALTER TABLE [dbo].[PlanSuscripcion] ADD  CONSTRAINT [DF_PlanSuscripcion_canalVentas]  DEFAULT ((0)) FOR [requiereCanalVentas]
GO
ALTER TABLE [dbo].[PlanSuscripcion] ADD  CONSTRAINT [DF_PlanSuscripcion_estado]  DEFAULT (N'ACTIVO') FOR [estado]
GO
ALTER TABLE [dbo].[PlanSuscripcion]  WITH CHECK ADD  CONSTRAINT [CK_PlanSuscripcion_coherencia] CHECK  (([tipoCliente]=N'CONSUMIDOR' AND ([tipoPlan]=N'MULTIUSUARIO' OR [tipoPlan]=N'INDIVIDUAL') OR [tipoCliente]=N'INSTITUCION' AND [tipoPlan]=N'INSTITUCIONAL'))
GO
ALTER TABLE [dbo].[PlanSuscripcion] CHECK CONSTRAINT [CK_PlanSuscripcion_coherencia]
GO
ALTER TABLE [dbo].[PlanSuscripcion]  WITH CHECK ADD  CONSTRAINT [CK_PlanSuscripcion_cupo] CHECK  ((([cupoUsuarios] IS NULL OR [cupoUsuarios]>(0)) AND ([tipoPlan]<>N'INDIVIDUAL' OR [cupoUsuarios]=(1))))
GO
ALTER TABLE [dbo].[PlanSuscripcion] CHECK CONSTRAINT [CK_PlanSuscripcion_cupo]
GO
ALTER TABLE [dbo].[PlanSuscripcion]  WITH CHECK ADD  CONSTRAINT [CK_PlanSuscripcion_estado] CHECK  (([estado]=N'INACTIVO' OR [estado]=N'ACTIVO'))
GO
ALTER TABLE [dbo].[PlanSuscripcion] CHECK CONSTRAINT [CK_PlanSuscripcion_estado]
GO
ALTER TABLE [dbo].[PlanSuscripcion]  WITH CHECK ADD  CONSTRAINT [CK_PlanSuscripcion_precio] CHECK  (([precioBase] IS NULL OR [precioBase]>=(0)))
GO
ALTER TABLE [dbo].[PlanSuscripcion] CHECK CONSTRAINT [CK_PlanSuscripcion_precio]
GO
ALTER TABLE [dbo].[PlanSuscripcion]  WITH CHECK ADD  CONSTRAINT [CK_PlanSuscripcion_tipoCliente] CHECK  (([tipoCliente]=N'INSTITUCION' OR [tipoCliente]=N'CONSUMIDOR'))
GO
ALTER TABLE [dbo].[PlanSuscripcion] CHECK CONSTRAINT [CK_PlanSuscripcion_tipoCliente]
GO
ALTER TABLE [dbo].[PlanSuscripcion]  WITH CHECK ADD  CONSTRAINT [CK_PlanSuscripcion_tipoPlan] CHECK  (([tipoPlan]=N'INSTITUCIONAL' OR [tipoPlan]=N'MULTIUSUARIO' OR [tipoPlan]=N'INDIVIDUAL'))
GO
ALTER TABLE [dbo].[PlanSuscripcion] CHECK CONSTRAINT [CK_PlanSuscripcion_tipoPlan]
GO
ALTER TABLE [dbo].[PlanSuscripcion]  WITH CHECK ADD  CONSTRAINT [CK_PlanSuscripcion_vigencia] CHECK  (([fechaVigenciaHasta] IS NULL OR [fechaVigenciaHasta]>=[fechaVigenciaDesde]))
GO
ALTER TABLE [dbo].[PlanSuscripcion] CHECK CONSTRAINT [CK_PlanSuscripcion_vigencia]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ProveedorPago](
	[idProveedorPago] [uniqueidentifier] NOT NULL,
	[codigo] [nvarchar](40) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[nombre] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[estado] [nvarchar](20) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[entorno] [nvarchar](20) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaAlta] [datetime2](3) NOT NULL,
 CONSTRAINT [PK_ProveedorPago] PRIMARY KEY CLUSTERED 
(
	[idProveedorPago] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
 CONSTRAINT [UQ_ProveedorPago_codigo] UNIQUE NONCLUSTERED 
(
	[codigo] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
ALTER TABLE [dbo].[ProveedorPago] ADD  CONSTRAINT [DF_ProveedorPago_id]  DEFAULT (newid()) FOR [idProveedorPago]
GO
ALTER TABLE [dbo].[ProveedorPago] ADD  CONSTRAINT [DF_ProveedorPago_estado]  DEFAULT (N'INACTIVO') FOR [estado]
GO
ALTER TABLE [dbo].[ProveedorPago] ADD  CONSTRAINT [DF_ProveedorPago_entorno]  DEFAULT (N'SANDBOX') FOR [entorno]
GO
ALTER TABLE [dbo].[ProveedorPago] ADD  CONSTRAINT [DF_ProveedorPago_fechaAlta]  DEFAULT (sysutcdatetime()) FOR [fechaAlta]
GO
ALTER TABLE [dbo].[ProveedorPago]  WITH CHECK ADD  CONSTRAINT [CK_ProveedorPago_entorno] CHECK  (([entorno]=N'PRODUCCION' OR [entorno]=N'SANDBOX'))
GO
ALTER TABLE [dbo].[ProveedorPago] CHECK CONSTRAINT [CK_ProveedorPago_entorno]
GO
ALTER TABLE [dbo].[ProveedorPago]  WITH CHECK ADD  CONSTRAINT [CK_ProveedorPago_estado] CHECK  (([estado]=N'INACTIVO' OR [estado]=N'ACTIVO'))
GO
ALTER TABLE [dbo].[ProveedorPago] CHECK CONSTRAINT [CK_ProveedorPago_estado]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[PuenteCredencial](
	[idPuenteCredencial] [uniqueidentifier] NOT NULL,
	[nombre] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[tokenHash] [nvarchar](64) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[codigoDispositivo] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaCreacion] [datetime2](3) NOT NULL,
	[fechaExpiracion] [datetime2](3) NOT NULL,
	[fechaRevocacion] [datetime2](3) NULL,
	[fechaUltimoUso] [datetime2](3) NULL,
 CONSTRAINT [PK_PuenteCredencial] PRIMARY KEY CLUSTERED 
(
	[idPuenteCredencial] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
 CONSTRAINT [UQ_PuenteCredencial_tokenHash] UNIQUE NONCLUSTERED 
(
	[tokenHash] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
ALTER TABLE [dbo].[PuenteCredencial] ADD  CONSTRAINT [DF_PuenteCredencial_id]  DEFAULT (newid()) FOR [idPuenteCredencial]
GO
ALTER TABLE [dbo].[PuenteCredencial] ADD  CONSTRAINT [DF_PuenteCredencial_fechaCreacion]  DEFAULT (sysutcdatetime()) FOR [fechaCreacion]
GO
ALTER TABLE [dbo].[PuenteCredencial]  WITH CHECK ADD  CONSTRAINT [CK_PuenteCredencial_expiracion] CHECK  (([fechaExpiracion]>[fechaCreacion]))
GO
ALTER TABLE [dbo].[PuenteCredencial] CHECK CONSTRAINT [CK_PuenteCredencial_expiracion]
GO
ALTER TABLE [dbo].[PuenteCredencial]  WITH CHECK ADD  CONSTRAINT [CK_PuenteCredencial_textos] CHECK  (([codigoDispositivo]<>N'' AND [nombre]<>N''))
GO
ALTER TABLE [dbo].[PuenteCredencial] CHECK CONSTRAINT [CK_PuenteCredencial_textos]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ReasignacionPaciente](
	[idReasignacionPaciente] [uniqueidentifier] NOT NULL,
	[idInstitucion] [uniqueidentifier] NOT NULL,
	[idPerfilMedicion] [uniqueidentifier] NOT NULL,
	[idOperadorAnterior] [uniqueidentifier] NOT NULL,
	[idOperadorNuevo] [uniqueidentifier] NULL,
	[estado] [nvarchar](20) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[motivo] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaCreacion] [datetime2](3) NOT NULL,
	[fechaResolucion] [datetime2](3) NULL,
	[idUsuarioResolutor] [uniqueidentifier] NULL,
	[resultado] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NULL,
	[observacion] [nvarchar](500) COLLATE Modern_Spanish_CI_AS NULL,
 CONSTRAINT [PK_ReasignacionPaciente] PRIMARY KEY CLUSTERED 
(
	[idReasignacionPaciente] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
SET ANSI_PADDING ON

GO
CREATE NONCLUSTERED INDEX [IX_ReasignacionPaciente_institucion] ON [dbo].[ReasignacionPaciente]
(
	[idInstitucion] ASC,
	[estado] ASC,
	[fechaCreacion] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
CREATE UNIQUE NONCLUSTERED INDEX [UX_ReasignacionPaciente_pendiente] ON [dbo].[ReasignacionPaciente]
(
	[idPerfilMedicion] ASC
)
WHERE ([estado]=N'PENDIENTE')
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
ALTER TABLE [dbo].[ReasignacionPaciente] ADD  CONSTRAINT [DF_ReasignacionPaciente_id]  DEFAULT (newid()) FOR [idReasignacionPaciente]
GO
ALTER TABLE [dbo].[ReasignacionPaciente] ADD  CONSTRAINT [DF_ReasignacionPaciente_estado]  DEFAULT (N'PENDIENTE') FOR [estado]
GO
ALTER TABLE [dbo].[ReasignacionPaciente] ADD  CONSTRAINT [DF_ReasignacionPaciente_motivo]  DEFAULT (N'BAJA_OPERADOR') FOR [motivo]
GO
ALTER TABLE [dbo].[ReasignacionPaciente] ADD  CONSTRAINT [DF_ReasignacionPaciente_fecha]  DEFAULT (sysutcdatetime()) FOR [fechaCreacion]
GO
ALTER TABLE [dbo].[ReasignacionPaciente]  WITH CHECK ADD  CONSTRAINT [CK_ReasignacionPaciente_coherencia] CHECK  (([estado]=N'PENDIENTE' AND [fechaResolucion] IS NULL AND [idOperadorNuevo] IS NULL AND [resultado] IS NULL OR [estado]=N'COMPLETADA' AND [fechaResolucion] IS NOT NULL AND [idOperadorNuevo] IS NOT NULL AND [resultado]=N'REASIGNADO' OR [estado]=N'CANCELADA' AND [fechaResolucion] IS NOT NULL AND [idOperadorNuevo] IS NULL AND [resultado] IS NOT NULL AND [resultado]<>N'REASIGNADO'))
GO
ALTER TABLE [dbo].[ReasignacionPaciente] CHECK CONSTRAINT [CK_ReasignacionPaciente_coherencia]
GO
ALTER TABLE [dbo].[ReasignacionPaciente]  WITH CHECK ADD  CONSTRAINT [CK_ReasignacionPaciente_estado] CHECK  (([estado]=N'CANCELADA' OR [estado]=N'COMPLETADA' OR [estado]=N'PENDIENTE'))
GO
ALTER TABLE [dbo].[ReasignacionPaciente] CHECK CONSTRAINT [CK_ReasignacionPaciente_estado]
GO
ALTER TABLE [dbo].[ReasignacionPaciente]  WITH CHECK ADD  CONSTRAINT [CK_ReasignacionPaciente_motivo] CHECK  (([motivo]=N'BAJA_OPERADOR'))
GO
ALTER TABLE [dbo].[ReasignacionPaciente] CHECK CONSTRAINT [CK_ReasignacionPaciente_motivo]
GO
ALTER TABLE [dbo].[ReasignacionPaciente]  WITH CHECK ADD  CONSTRAINT [CK_ReasignacionPaciente_resultado] CHECK  (([resultado] IS NULL OR ([resultado]=N'INSTITUCION_CERRADA' OR [resultado]=N'PACIENTE_DADO_DE_BAJA' OR [resultado]=N'REASIGNADO')))
GO
ALTER TABLE [dbo].[ReasignacionPaciente] CHECK CONSTRAINT [CK_ReasignacionPaciente_resultado]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ReglaMatriz](
	[idReglaMatriz] [uniqueidentifier] NOT NULL,
	[idMatriz] [uniqueidentifier] NOT NULL,
	[codigoRegla] [nvarchar](50) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[sexoModelo] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[edadDesde] [smallint] NULL,
	[edadHasta] [smallint] NULL,
	[condicionComida] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[minutosComidaMin] [int] NULL,
	[minutosComidaMax] [int] NULL,
	[glucosaMinReferencia] [decimal](8, 2) NOT NULL,
	[glucosaMaxReferencia] [decimal](8, 2) NOT NULL,
 CONSTRAINT [PK_ReglaMatriz] PRIMARY KEY CLUSTERED 
(
	[idReglaMatriz] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
 CONSTRAINT [UQ_ReglaMatriz_codigo] UNIQUE NONCLUSTERED 
(
	[idMatriz] ASC,
	[codigoRegla] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
ALTER TABLE [dbo].[ReglaMatriz] ADD  CONSTRAINT [DF_ReglaMatriz_id]  DEFAULT (newid()) FOR [idReglaMatriz]
GO
ALTER TABLE [dbo].[ReglaMatriz]  WITH CHECK ADD  CONSTRAINT [CK_ReglaMatriz_condicion] CHECK  (([condicionComida]=N'NO_INFORMADA' OR [condicionComida]=N'POSTPRANDIAL' OR [condicionComida]=N'AYUNO'))
GO
ALTER TABLE [dbo].[ReglaMatriz] CHECK CONSTRAINT [CK_ReglaMatriz_condicion]
GO
ALTER TABLE [dbo].[ReglaMatriz]  WITH CHECK ADD  CONSTRAINT [CK_ReglaMatriz_edad] CHECK  (([edadDesde] IS NULL AND [edadHasta] IS NULL OR [edadDesde] IS NOT NULL AND [edadHasta] IS NOT NULL AND ([edadDesde]>=(0) AND [edadDesde]<=(130)) AND ([edadHasta]>=[edadDesde] AND [edadHasta]<=(130))))
GO
ALTER TABLE [dbo].[ReglaMatriz] CHECK CONSTRAINT [CK_ReglaMatriz_edad]
GO
ALTER TABLE [dbo].[ReglaMatriz]  WITH CHECK ADD  CONSTRAINT [CK_ReglaMatriz_glucosaReferencia] CHECK  (([glucosaMinReferencia]>=(0) AND [glucosaMaxReferencia]>=[glucosaMinReferencia]))
GO
ALTER TABLE [dbo].[ReglaMatriz] CHECK CONSTRAINT [CK_ReglaMatriz_glucosaReferencia]
GO
ALTER TABLE [dbo].[ReglaMatriz]  WITH CHECK ADD  CONSTRAINT [CK_ReglaMatriz_minutos] CHECK  ((([minutosComidaMin] IS NULL OR [minutosComidaMin]>=(0)) AND ([minutosComidaMax] IS NULL OR [minutosComidaMax]>=(0)) AND ([minutosComidaMin] IS NULL OR [minutosComidaMax] IS NULL OR [minutosComidaMax]>=[minutosComidaMin])))
GO
ALTER TABLE [dbo].[ReglaMatriz] CHECK CONSTRAINT [CK_ReglaMatriz_minutos]
GO
ALTER TABLE [dbo].[ReglaMatriz]  WITH CHECK ADD  CONSTRAINT [CK_ReglaMatriz_sexo] CHECK  (([sexoModelo]=N'NO_INFORMADO' OR [sexoModelo]=N'MASCULINO' OR [sexoModelo]=N'FEMENINO'))
GO
ALTER TABLE [dbo].[ReglaMatriz] CHECK CONSTRAINT [CK_ReglaMatriz_sexo]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[SesionUsuario](
	[idSesion] [uniqueidentifier] NOT NULL,
	[idUsuario] [uniqueidentifier] NOT NULL,
	[refreshTokenHash] [nvarchar](255) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaCreacion] [datetime2](3) NOT NULL,
	[fechaExpiracion] [datetime2](3) NOT NULL,
	[fechaRevocacion] [datetime2](3) NULL,
 CONSTRAINT [PK_SesionUsuario] PRIMARY KEY CLUSTERED 
(
	[idSesion] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
 CONSTRAINT [UQ_SesionUsuario_refreshTokenHash] UNIQUE NONCLUSTERED 
(
	[refreshTokenHash] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
ALTER TABLE [dbo].[SesionUsuario] ADD  CONSTRAINT [DF_SesionUsuario_id]  DEFAULT (newid()) FOR [idSesion]
GO
ALTER TABLE [dbo].[SesionUsuario] ADD  CONSTRAINT [DF_SesionUsuario_fechaCreacion]  DEFAULT (sysutcdatetime()) FOR [fechaCreacion]
GO
ALTER TABLE [dbo].[SesionUsuario]  WITH CHECK ADD  CONSTRAINT [CK_SesionUsuario_expiracion] CHECK  (([fechaExpiracion]>[fechaCreacion]))
GO
ALTER TABLE [dbo].[SesionUsuario] CHECK CONSTRAINT [CK_SesionUsuario_expiracion]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[Suscripcion](
	[idSuscripcion] [uniqueidentifier] NOT NULL,
	[idPlan] [uniqueidentifier] NOT NULL,
	[idUsuarioTitular] [uniqueidentifier] NULL,
	[idInstitucion] [uniqueidentifier] NULL,
	[estado] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaInicio] [datetime2](3) NOT NULL,
	[fechaFin] [datetime2](3) NULL,
	[renovacionAutomatica] [bit] NOT NULL,
	[origenContratacion] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[referenciaContrato] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NULL,
	[fechaCreacion] [datetime2](3) NOT NULL,
 CONSTRAINT [PK_Suscripcion] PRIMARY KEY CLUSTERED 
(
	[idSuscripcion] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
ALTER TABLE [dbo].[Suscripcion] ADD  CONSTRAINT [DF_Suscripcion_id]  DEFAULT (newid()) FOR [idSuscripcion]
GO
ALTER TABLE [dbo].[Suscripcion] ADD  CONSTRAINT [DF_Suscripcion_estado]  DEFAULT (N'PENDIENTE') FOR [estado]
GO
ALTER TABLE [dbo].[Suscripcion] ADD  CONSTRAINT [DF_Suscripcion_renovacion]  DEFAULT ((0)) FOR [renovacionAutomatica]
GO
ALTER TABLE [dbo].[Suscripcion] ADD  CONSTRAINT [DF_Suscripcion_origen]  DEFAULT (N'ONLINE') FOR [origenContratacion]
GO
ALTER TABLE [dbo].[Suscripcion] ADD  CONSTRAINT [DF_Suscripcion_fechaCreacion]  DEFAULT (sysutcdatetime()) FOR [fechaCreacion]
GO
ALTER TABLE [dbo].[Suscripcion]  WITH CHECK ADD  CONSTRAINT [CK_Suscripcion_estado] CHECK  (([estado]=N'CANCELADA' OR [estado]=N'SUSPENDIDA' OR [estado]=N'VENCIDA' OR [estado]=N'ACTIVA' OR [estado]=N'PENDIENTE'))
GO
ALTER TABLE [dbo].[Suscripcion] CHECK CONSTRAINT [CK_Suscripcion_estado]
GO
ALTER TABLE [dbo].[Suscripcion]  WITH CHECK ADD  CONSTRAINT [CK_Suscripcion_fechas] CHECK  (([fechaFin] IS NULL OR [fechaFin]>=[fechaInicio]))
GO
ALTER TABLE [dbo].[Suscripcion] CHECK CONSTRAINT [CK_Suscripcion_fechas]
GO
ALTER TABLE [dbo].[Suscripcion]  WITH CHECK ADD  CONSTRAINT [CK_Suscripcion_origen] CHECK  (([origenContratacion]=N'CANAL_VENTAS' OR [origenContratacion]=N'ONLINE'))
GO
ALTER TABLE [dbo].[Suscripcion] CHECK CONSTRAINT [CK_Suscripcion_origen]
GO
ALTER TABLE [dbo].[Suscripcion]  WITH CHECK ADD  CONSTRAINT [CK_Suscripcion_titular] CHECK  (([idUsuarioTitular] IS NOT NULL AND [idInstitucion] IS NULL OR [idUsuarioTitular] IS NULL AND [idInstitucion] IS NOT NULL))
GO
ALTER TABLE [dbo].[Suscripcion] CHECK CONSTRAINT [CK_Suscripcion_titular]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[SuscripcionUsuario](
	[idSuscripcionUsuario] [uniqueidentifier] NOT NULL,
	[idSuscripcion] [uniqueidentifier] NOT NULL,
	[idUsuario] [uniqueidentifier] NOT NULL,
	[esTitular] [bit] NOT NULL,
	[estadoRelacion] [nvarchar](20) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaIncorporacion] [datetime2](3) NOT NULL,
	[fechaBaja] [datetime2](3) NULL,
 CONSTRAINT [PK_SuscripcionUsuario] PRIMARY KEY CLUSTERED 
(
	[idSuscripcionUsuario] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
ALTER TABLE [dbo].[SuscripcionUsuario] ADD  CONSTRAINT [DF_SuscripcionUsuario_id]  DEFAULT (newid()) FOR [idSuscripcionUsuario]
GO
ALTER TABLE [dbo].[SuscripcionUsuario] ADD  CONSTRAINT [DF_SuscripcionUsuario_esTitular]  DEFAULT ((0)) FOR [esTitular]
GO
ALTER TABLE [dbo].[SuscripcionUsuario] ADD  CONSTRAINT [DF_SuscripcionUsuario_estado]  DEFAULT (N'ACTIVA') FOR [estadoRelacion]
GO
ALTER TABLE [dbo].[SuscripcionUsuario] ADD  CONSTRAINT [DF_SuscripcionUsuario_fechaIncorporacion]  DEFAULT (sysutcdatetime()) FOR [fechaIncorporacion]
GO
ALTER TABLE [dbo].[SuscripcionUsuario]  WITH CHECK ADD  CONSTRAINT [CK_SuscripcionUsuario_baja] CHECK  (([estadoRelacion]<>N'BAJA' OR [fechaBaja] IS NOT NULL))
GO
ALTER TABLE [dbo].[SuscripcionUsuario] CHECK CONSTRAINT [CK_SuscripcionUsuario_baja]
GO
ALTER TABLE [dbo].[SuscripcionUsuario]  WITH CHECK ADD  CONSTRAINT [CK_SuscripcionUsuario_estado] CHECK  (([estadoRelacion]=N'BAJA' OR [estadoRelacion]=N'ACTIVA'))
GO
ALTER TABLE [dbo].[SuscripcionUsuario] CHECK CONSTRAINT [CK_SuscripcionUsuario_estado]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[TokenCuenta](
	[idTokenCuenta] [uniqueidentifier] NOT NULL,
	[idUsuario] [uniqueidentifier] NOT NULL,
	[tipo] [nvarchar](40) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[tokenHash] [nvarchar](255) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaCreacion] [datetime2](3) NOT NULL,
	[fechaExpiracion] [datetime2](3) NOT NULL,
	[fechaUso] [datetime2](3) NULL,
 CONSTRAINT [PK_TokenCuenta] PRIMARY KEY CLUSTERED 
(
	[idTokenCuenta] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
 CONSTRAINT [UQ_TokenCuenta_tokenHash] UNIQUE NONCLUSTERED 
(
	[tokenHash] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
ALTER TABLE [dbo].[TokenCuenta] ADD  CONSTRAINT [DF_TokenCuenta_id]  DEFAULT (newid()) FOR [idTokenCuenta]
GO
ALTER TABLE [dbo].[TokenCuenta] ADD  CONSTRAINT [DF_TokenCuenta_fechaCreacion]  DEFAULT (sysutcdatetime()) FOR [fechaCreacion]
GO
ALTER TABLE [dbo].[TokenCuenta]  WITH CHECK ADD  CONSTRAINT [CK_TokenCuenta_expiracion] CHECK  (([fechaExpiracion]>[fechaCreacion]))
GO
ALTER TABLE [dbo].[TokenCuenta] CHECK CONSTRAINT [CK_TokenCuenta_expiracion]
GO
ALTER TABLE [dbo].[TokenCuenta]  WITH CHECK ADD  CONSTRAINT [CK_TokenCuenta_tipo] CHECK  (([tipo]=N'ACTIVACION_CUENTA' OR [tipo]=N'RECUPERACION_MFA' OR [tipo]=N'INTERCAMBIO_GOOGLE' OR [tipo]=N'ELIMINAR_CUENTA' OR [tipo]=N'RECUPERACION_PASSWORD' OR [tipo]=N'VERIFICACION_EMAIL'))
GO
ALTER TABLE [dbo].[TokenCuenta] CHECK CONSTRAINT [CK_TokenCuenta_tipo]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
SET ANSI_PADDING ON
GO
CREATE TABLE [dbo].[TransaccionPago](
	[idTransaccionPago] [uniqueidentifier] NOT NULL,
	[idSuscripcion] [uniqueidentifier] NOT NULL,
	[idProveedorPago] [uniqueidentifier] NOT NULL,
	[idOperacionProveedor] [nvarchar](150) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[monto] [decimal](12, 2) NOT NULL,
	[moneda] [char](3) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[estado] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaCreacion] [datetime2](3) NOT NULL,
	[fechaConfirmacion] [datetime2](3) NULL,
	[detalleProveedor] [nvarchar](max) COLLATE Modern_Spanish_CI_AS NULL,
 CONSTRAINT [PK_TransaccionPago] PRIMARY KEY CLUSTERED 
(
	[idTransaccionPago] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
 CONSTRAINT [UQ_TransaccionPago_operacion] UNIQUE NONCLUSTERED 
(
	[idOperacionProveedor] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]

GO
SET ANSI_PADDING OFF
GO
ALTER TABLE [dbo].[TransaccionPago] ADD  CONSTRAINT [DF_TransaccionPago_id]  DEFAULT (newid()) FOR [idTransaccionPago]
GO
ALTER TABLE [dbo].[TransaccionPago] ADD  CONSTRAINT [DF_TransaccionPago_moneda]  DEFAULT ('ARS') FOR [moneda]
GO
ALTER TABLE [dbo].[TransaccionPago] ADD  CONSTRAINT [DF_TransaccionPago_estado]  DEFAULT (N'PENDIENTE') FOR [estado]
GO
ALTER TABLE [dbo].[TransaccionPago] ADD  CONSTRAINT [DF_TransaccionPago_fechaCreacion]  DEFAULT (sysutcdatetime()) FOR [fechaCreacion]
GO
ALTER TABLE [dbo].[TransaccionPago]  WITH CHECK ADD  CONSTRAINT [CK_TransaccionPago_detalleJson] CHECK  (([detalleProveedor] IS NULL OR isjson([detalleProveedor])=(1)))
GO
ALTER TABLE [dbo].[TransaccionPago] CHECK CONSTRAINT [CK_TransaccionPago_detalleJson]
GO
ALTER TABLE [dbo].[TransaccionPago]  WITH CHECK ADD  CONSTRAINT [CK_TransaccionPago_estado] CHECK  (([estado]=N'REEMBOLSADA' OR [estado]=N'ANULADA' OR [estado]=N'RECHAZADA' OR [estado]=N'APROBADA' OR [estado]=N'PENDIENTE'))
GO
ALTER TABLE [dbo].[TransaccionPago] CHECK CONSTRAINT [CK_TransaccionPago_estado]
GO
ALTER TABLE [dbo].[TransaccionPago]  WITH CHECK ADD  CONSTRAINT [CK_TransaccionPago_monto] CHECK  (([monto]>=(0)))
GO
ALTER TABLE [dbo].[TransaccionPago] CHECK CONSTRAINT [CK_TransaccionPago_monto]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[TransferenciaAdministracion](
	[idTransferenciaAdministracion] [uniqueidentifier] NOT NULL,
	[idUsuarioOrigen] [uniqueidentifier] NOT NULL,
	[idUsuarioDestino] [uniqueidentifier] NOT NULL,
	[estado] [nvarchar](20) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaSolicitud] [datetime2](3) NOT NULL,
	[fechaRespuesta] [datetime2](3) NULL,
 CONSTRAINT [PK_TransferenciaAdministracion] PRIMARY KEY CLUSTERED 
(
	[idTransferenciaAdministracion] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
SET ANSI_PADDING ON

GO
CREATE NONCLUSTERED INDEX [IX_TransferenciaAdministracion_destino] ON [dbo].[TransferenciaAdministracion]
(
	[idUsuarioDestino] ASC,
	[estado] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
SET ANSI_PADDING ON

GO
CREATE UNIQUE NONCLUSTERED INDEX [UX_TransferenciaAdministracion_pendiente] ON [dbo].[TransferenciaAdministracion]
(
	[estado] ASC
)
WHERE ([estado]=N'PENDIENTE')
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
ALTER TABLE [dbo].[TransferenciaAdministracion] ADD  CONSTRAINT [DF_TransferenciaAdministracion_id]  DEFAULT (newid()) FOR [idTransferenciaAdministracion]
GO
ALTER TABLE [dbo].[TransferenciaAdministracion] ADD  CONSTRAINT [DF_TransferenciaAdministracion_estado]  DEFAULT (N'PENDIENTE') FOR [estado]
GO
ALTER TABLE [dbo].[TransferenciaAdministracion] ADD  CONSTRAINT [DF_TransferenciaAdministracion_fecha]  DEFAULT (sysutcdatetime()) FOR [fechaSolicitud]
GO
ALTER TABLE [dbo].[TransferenciaAdministracion]  WITH CHECK ADD  CONSTRAINT [CK_TransferenciaAdministracion_distintos] CHECK  (([idUsuarioOrigen]<>[idUsuarioDestino]))
GO
ALTER TABLE [dbo].[TransferenciaAdministracion] CHECK CONSTRAINT [CK_TransferenciaAdministracion_distintos]
GO
ALTER TABLE [dbo].[TransferenciaAdministracion]  WITH CHECK ADD  CONSTRAINT [CK_TransferenciaAdministracion_estado] CHECK  (([estado]=N'PENDIENTE' OR [estado]=N'ACEPTADA' OR [estado]=N'RECHAZADA' OR [estado]=N'CANCELADA'))
GO
ALTER TABLE [dbo].[TransferenciaAdministracion] CHECK CONSTRAINT [CK_TransferenciaAdministracion_estado]
GO
ALTER TABLE [dbo].[TransferenciaAdministracion]  WITH CHECK ADD  CONSTRAINT [CK_TransferenciaAdministracion_respuesta] CHECK  (([estado]=N'PENDIENTE' AND [fechaRespuesta] IS NULL OR [estado]<>N'PENDIENTE' AND [fechaRespuesta] IS NOT NULL))
GO
ALTER TABLE [dbo].[TransferenciaAdministracion] CHECK CONSTRAINT [CK_TransferenciaAdministracion_respuesta]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[TransferenciaPerfil](
	[idTransferenciaPerfil] [uniqueidentifier] NOT NULL,
	[idPerfilMedicion] [uniqueidentifier] NOT NULL,
	[idOperadorDestino] [uniqueidentifier] NOT NULL,
	[estado] [nvarchar](20) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaPeticion] [datetime2](3) NOT NULL,
	[fechaTransferencia] [datetime2](3) NULL,
	[observacion] [nvarchar](500) COLLATE Modern_Spanish_CI_AS NULL,
 CONSTRAINT [PK_TransferenciaPerfil] PRIMARY KEY CLUSTERED 
(
	[idTransferenciaPerfil] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
SET ANSI_PADDING ON

GO
CREATE NONCLUSTERED INDEX [IX_TransferenciaPerfil_destino] ON [dbo].[TransferenciaPerfil]
(
	[idOperadorDestino] ASC,
	[estado] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
CREATE UNIQUE NONCLUSTERED INDEX [UX_TransferenciaPerfil_pendiente] ON [dbo].[TransferenciaPerfil]
(
	[idPerfilMedicion] ASC
)
WHERE ([estado]=N'PENDIENTE')
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
ALTER TABLE [dbo].[TransferenciaPerfil] ADD  CONSTRAINT [DF_TransferenciaPerfil_id]  DEFAULT (newid()) FOR [idTransferenciaPerfil]
GO
ALTER TABLE [dbo].[TransferenciaPerfil] ADD  CONSTRAINT [DF_TransferenciaPerfil_estado]  DEFAULT (N'PENDIENTE') FOR [estado]
GO
ALTER TABLE [dbo].[TransferenciaPerfil] ADD  CONSTRAINT [DF_TransferenciaPerfil_fechaPeticion]  DEFAULT (sysutcdatetime()) FOR [fechaPeticion]
GO
ALTER TABLE [dbo].[TransferenciaPerfil]  WITH CHECK ADD  CONSTRAINT [CK_TransferenciaPerfil_estado] CHECK  (([estado]=N'CANCELADA' OR [estado]=N'RECHAZADA' OR [estado]=N'ACEPTADA' OR [estado]=N'PENDIENTE'))
GO
ALTER TABLE [dbo].[TransferenciaPerfil] CHECK CONSTRAINT [CK_TransferenciaPerfil_estado]
GO
ALTER TABLE [dbo].[TransferenciaPerfil]  WITH CHECK ADD  CONSTRAINT [CK_TransferenciaPerfil_fechaTransferencia] CHECK  (([estado]=N'ACEPTADA' AND [fechaTransferencia] IS NOT NULL AND [fechaTransferencia]>=[fechaPeticion] OR [estado]<>N'ACEPTADA' AND [fechaTransferencia] IS NULL))
GO
ALTER TABLE [dbo].[TransferenciaPerfil] CHECK CONSTRAINT [CK_TransferenciaPerfil_fechaTransferencia]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[Usuario](
	[idUsuario] [uniqueidentifier] NOT NULL,
	[nombre] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NULL,
	[apellido] [nvarchar](100) COLLATE Modern_Spanish_CI_AS NULL,
	[correoElectronico] [nvarchar](254) COLLATE Modern_Spanish_CI_AS NULL,
	[usuario] [nvarchar](50) COLLATE Modern_Spanish_CI_AS NULL,
	[tipoCuenta] [nvarchar](40) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[estado] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NOT NULL,
	[fechaCreacion] [datetime2](3) NOT NULL,
	[fechaActualizacion] [datetime2](3) NOT NULL,
	[fechaEliminacion] [datetime2](3) NULL,
	[fechaNacimiento] [date] NULL,
	[sexo] [nvarchar](30) COLLATE Modern_Spanish_CI_AS NULL,
	[notificarNuevoInicioSesion] [bit] NOT NULL,
	[fechaInicioGracia] [datetime2](3) NULL,
	[fechaVencimientoGracia] [datetime2](3) NULL,
 CONSTRAINT [PK_Usuario] PRIMARY KEY CLUSTERED 
(
	[idUsuario] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]

GO
CREATE NONCLUSTERED INDEX [IX_Usuario_graciaVencimiento] ON [dbo].[Usuario]
(
	[fechaVencimientoGracia] ASC
)
WHERE ([fechaVencimientoGracia] IS NOT NULL)
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
SET ANSI_PADDING ON

GO
CREATE UNIQUE NONCLUSTERED INDEX [UX_Usuario_administradorUnico] ON [dbo].[Usuario]
(
	[tipoCuenta] ASC
)
WHERE ([tipoCuenta]=N'ADMINISTRADOR_PLATAFORMA' AND [estado]<>N'ELIMINADO')
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
SET ANSI_PADDING ON

GO
CREATE UNIQUE NONCLUSTERED INDEX [UX_Usuario_correoElectronico] ON [dbo].[Usuario]
(
	[correoElectronico] ASC
)
WHERE ([correoElectronico] IS NOT NULL)
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
SET ANSI_PADDING ON

GO
CREATE UNIQUE NONCLUSTERED INDEX [UX_Usuario_usuario] ON [dbo].[Usuario]
(
	[usuario] ASC
)
WHERE ([usuario] IS NOT NULL)
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
ALTER TABLE [dbo].[Usuario] ADD  CONSTRAINT [DF_Usuario_id]  DEFAULT (newid()) FOR [idUsuario]
GO
ALTER TABLE [dbo].[Usuario] ADD  CONSTRAINT [DF_Usuario_tipoCuenta]  DEFAULT (N'CONSUMIDOR_FINAL') FOR [tipoCuenta]
GO
ALTER TABLE [dbo].[Usuario] ADD  CONSTRAINT [DF_Usuario_estado]  DEFAULT (N'PENDIENTE') FOR [estado]
GO
ALTER TABLE [dbo].[Usuario] ADD  CONSTRAINT [DF_Usuario_fechaCreacion]  DEFAULT (sysutcdatetime()) FOR [fechaCreacion]
GO
ALTER TABLE [dbo].[Usuario] ADD  CONSTRAINT [DF_Usuario_fechaActualizacion]  DEFAULT (sysutcdatetime()) FOR [fechaActualizacion]
GO
ALTER TABLE [dbo].[Usuario] ADD  CONSTRAINT [DF_Usuario_notificarNuevoInicioSesion]  DEFAULT ((1)) FOR [notificarNuevoInicioSesion]
GO
ALTER TABLE [dbo].[Usuario]  WITH CHECK ADD  CONSTRAINT [CK_Usuario_correo] CHECK  (([estado]=N'ELIMINADO' OR [correoElectronico] IS NOT NULL))
GO
ALTER TABLE [dbo].[Usuario] CHECK CONSTRAINT [CK_Usuario_correo]
GO
ALTER TABLE [dbo].[Usuario]  WITH CHECK ADD  CONSTRAINT [CK_Usuario_eliminacion] CHECK  (([estado]=N'ELIMINADO' AND [fechaEliminacion] IS NOT NULL OR [estado]<>N'ELIMINADO' AND [fechaEliminacion] IS NULL))
GO
ALTER TABLE [dbo].[Usuario] CHECK CONSTRAINT [CK_Usuario_eliminacion]
GO
ALTER TABLE [dbo].[Usuario]  WITH CHECK ADD  CONSTRAINT [CK_Usuario_estado] CHECK  (([estado]=N'ELIMINADO' OR [estado]=N'BLOQUEADO' OR [estado]=N'ACTIVO' OR [estado]=N'PENDIENTE'))
GO
ALTER TABLE [dbo].[Usuario] CHECK CONSTRAINT [CK_Usuario_estado]
GO
ALTER TABLE [dbo].[Usuario]  WITH CHECK ADD  CONSTRAINT [CK_Usuario_fechaNacimiento] CHECK  (([fechaNacimiento] IS NULL OR [fechaNacimiento]<=CONVERT([date],sysutcdatetime())))
GO
ALTER TABLE [dbo].[Usuario] CHECK CONSTRAINT [CK_Usuario_fechaNacimiento]
GO
ALTER TABLE [dbo].[Usuario]  WITH CHECK ADD  CONSTRAINT [CK_Usuario_gracia] CHECK  (([fechaInicioGracia] IS NULL AND [fechaVencimientoGracia] IS NULL OR [fechaInicioGracia] IS NOT NULL AND [fechaVencimientoGracia] IS NOT NULL AND [fechaVencimientoGracia]>[fechaInicioGracia]))
GO
ALTER TABLE [dbo].[Usuario] CHECK CONSTRAINT [CK_Usuario_gracia]
GO
ALTER TABLE [dbo].[Usuario]  WITH CHECK ADD  CONSTRAINT [CK_Usuario_sexo] CHECK  (([sexo] IS NULL OR ([sexo]=N'MASCULINO' OR [sexo]=N'FEMENINO')))
GO
ALTER TABLE [dbo].[Usuario] CHECK CONSTRAINT [CK_Usuario_sexo]
GO
ALTER TABLE [dbo].[Usuario]  WITH CHECK ADD  CONSTRAINT [CK_Usuario_tipoCuenta] CHECK  (([tipoCuenta]=N'MODERADOR_PLATAFORMA' OR [tipoCuenta]=N'ADMINISTRADOR_PLATAFORMA' OR [tipoCuenta]=N'USUARIO_INSTITUCIONAL' OR [tipoCuenta]=N'CONSUMIDOR_FINAL'))
GO
ALTER TABLE [dbo].[Usuario] CHECK CONSTRAINT [CK_Usuario_tipoCuenta]
GO
-- ===== 2. Datos =====
-- dbo.Auditoria: 11 sentencias
INSERT [dbo].[Auditoria] ([idAuditoria], [idUsuario], [tipoEvento], [accion], [tablaAfectada], [idRegistro], [tablaRelacionada], [idRelacionado], [datosPrevios], [datosNuevos], [resultado], [fechaHora], [observacion], [detalle], [idInstitucion], [modulo], [tipoCuentaActor]) VALUES (N'085a433e-f36b-1410-88a6-00891fb53762', NULL, N'LOGIN', N'LOGIN_GOOGLE', NULL, NULL, NULL, NULL, NULL, NULL, N'FALLO', CAST(N'2026-10-24T19:46:27.3080000' AS DateTime2), N'Cuenta no registrada', NULL, NULL, N'CUENTA', NULL)
GO
INSERT [dbo].[Auditoria] ([idAuditoria], [idUsuario], [tipoEvento], [accion], [tablaAfectada], [idRegistro], [tablaRelacionada], [idRelacionado], [datosPrevios], [datosNuevos], [resultado], [fechaHora], [observacion], [detalle], [idInstitucion], [modulo], [tipoCuentaActor]) VALUES (N'396f433e-f36b-1410-88a7-00891fb53762', N'cf11117b-7385-4449-a7c4-5d603ab17123', N'CRUD', N'REGISTRO_GOOGLE', N'Usuario', N'cf11117b-7385-4449-a7c4-5d603ab17123', NULL, NULL, NULL, NULL, N'EXITO', CAST(N'2026-10-25T17:12:15.6250000' AS DateTime2), N'Tipo de cuenta: CONSUMIDOR_FINAL', NULL, NULL, N'CUENTA', NULL)
GO
INSERT [dbo].[Auditoria] ([idAuditoria], [idUsuario], [tipoEvento], [accion], [tablaAfectada], [idRegistro], [tablaRelacionada], [idRelacionado], [datosPrevios], [datosNuevos], [resultado], [fechaHora], [observacion], [detalle], [idInstitucion], [modulo], [tipoCuentaActor]) VALUES (N'406f433e-f36b-1410-88a7-00891fb53762', N'cf11117b-7385-4449-a7c4-5d603ab17123', N'LOGIN', N'LOGIN_GOOGLE', NULL, NULL, NULL, NULL, NULL, NULL, N'EXITO', CAST(N'2026-10-25T17:12:15.9170000' AS DateTime2), NULL, NULL, NULL, N'CUENTA', N'CONSUMIDOR_FINAL')
GO
INSERT [dbo].[Auditoria] ([idAuditoria], [idUsuario], [tipoEvento], [accion], [tablaAfectada], [idRegistro], [tablaRelacionada], [idRelacionado], [datosPrevios], [datosNuevos], [resultado], [fechaHora], [observacion], [detalle], [idInstitucion], [modulo], [tipoCuentaActor]) VALUES (N'476f433e-f36b-1410-88a7-00891fb53762', N'cf11117b-7385-4449-a7c4-5d603ab17123', N'CRUD', N'CREAR_PERFIL_MEDICION', N'PerfilMedicion', N'5a73b044-f895-4845-a549-5a6b07784a4c', NULL, NULL, NULL, N'{"tipoPerfil": "CONSUMIDOR_FINAL"}', N'EXITO', CAST(N'2026-10-25T17:12:20.9070000' AS DateTime2), NULL, NULL, NULL, N'PERFILES', NULL)
GO
INSERT [dbo].[Auditoria] ([idAuditoria], [idUsuario], [tipoEvento], [accion], [tablaAfectada], [idRegistro], [tablaRelacionada], [idRelacionado], [datosPrevios], [datosNuevos], [resultado], [fechaHora], [observacion], [detalle], [idInstitucion], [modulo], [tipoCuentaActor]) VALUES (N'4e6f433e-f36b-1410-88a7-00891fb53762', N'cf11117b-7385-4449-a7c4-5d603ab17123', N'PERMISO', N'CONSENTIMIENTO_DATOS_EXPERIMENTALES', N'ConsentimientoUsuario', N'9f04c521-c392-44fd-9e22-3ed21f6eb4bc', NULL, NULL, NULL, N'{"estado": "ACEPTADO", "version": "1.0"}', N'EXITO', CAST(N'2026-10-25T17:12:35.6270000' AS DateTime2), NULL, NULL, NULL, N'SISTEMA', NULL)
GO
INSERT [dbo].[Auditoria] ([idAuditoria], [idUsuario], [tipoEvento], [accion], [tablaAfectada], [idRegistro], [tablaRelacionada], [idRelacionado], [datosPrevios], [datosNuevos], [resultado], [fechaHora], [observacion], [detalle], [idInstitucion], [modulo], [tipoCuentaActor]) VALUES (N'546f433e-f36b-1410-88a7-00891fb53762', NULL, N'CRUD', N'REGISTRAR_DISPOSITIVO', N'Dispositivo', N'8cabe09f-6170-4235-a14d-d4ba94fab913', NULL, NULL, NULL, N'{"modeloSensor": "MAX30100", "estado": "OPERATIVO", "registroAutomatico": true, "origen": "PUENTE_SERIE", "idInstitucion": null}', N'EXITO', CAST(N'2026-10-25T17:14:33.3230000' AS DateTime2), NULL, NULL, NULL, N'DISPOSITIVOS', NULL)
GO
INSERT [dbo].[Auditoria] ([idAuditoria], [idUsuario], [tipoEvento], [accion], [tablaAfectada], [idRegistro], [tablaRelacionada], [idRelacionado], [datosPrevios], [datosNuevos], [resultado], [fechaHora], [observacion], [detalle], [idInstitucion], [modulo], [tipoCuentaActor]) VALUES (N'596f433e-f36b-1410-88a7-00891fb53762', N'cf11117b-7385-4449-a7c4-5d603ab17123', N'ACCESO', N'TOMAR_CONTROL_DISPOSITIVO', N'Dispositivo', N'8cabe09f-6170-4235-a14d-d4ba94fab913', NULL, NULL, NULL, NULL, N'EXITO', CAST(N'2026-10-25T17:15:27.0780000' AS DateTime2), NULL, NULL, NULL, N'DISPOSITIVOS', NULL)
GO
INSERT [dbo].[Auditoria] ([idAuditoria], [idUsuario], [tipoEvento], [accion], [tablaAfectada], [idRegistro], [tablaRelacionada], [idRelacionado], [datosPrevios], [datosNuevos], [resultado], [fechaHora], [observacion], [detalle], [idInstitucion], [modulo], [tipoCuentaActor]) VALUES (N'5e6f433e-f36b-1410-88a7-00891fb53762', N'cf11117b-7385-4449-a7c4-5d603ab17123', N'PERMISO', N'ORDEN_PUENTE_SERIE', NULL, NULL, NULL, NULL, NULL, N'{"accion": "CONFIGURAR", "puerto": "COM4", "medio": "BLUETOOTH"}', N'EXITO', CAST(N'2026-10-25T17:15:32.0030000' AS DateTime2), NULL, NULL, NULL, N'SISTEMA', NULL)
GO
INSERT [dbo].[Auditoria] ([idAuditoria], [idUsuario], [tipoEvento], [accion], [tablaAfectada], [idRegistro], [tablaRelacionada], [idRelacionado], [datosPrevios], [datosNuevos], [resultado], [fechaHora], [observacion], [detalle], [idInstitucion], [modulo], [tipoCuentaActor]) VALUES (N'606f433e-f36b-1410-88a7-00891fb53762', N'cf11117b-7385-4449-a7c4-5d603ab17123', N'CRUD', N'INICIAR_MEDICION', N'Medicion', N'2de67bf5-7ca4-4d85-b837-20c68acbdd1d', NULL, NULL, NULL, N'{"modoMedicion": "GLUCOSA_EXPERIMENTAL", "tipoPerfil": "CONSUMIDOR_FINAL", "idPerfilMedicion": "5a73b044-f895-4845-a549-5a6b07784a4c", "edadInformadaEnLaMedicion": true, "sexoInformadoEnLaMedicion": true}', N'EXITO', CAST(N'2026-10-25T17:16:06.4480000' AS DateTime2), NULL, NULL, NULL, N'MEDICIONES', NULL)
GO
INSERT [dbo].[Auditoria] ([idAuditoria], [idUsuario], [tipoEvento], [accion], [tablaAfectada], [idRegistro], [tablaRelacionada], [idRelacionado], [datosPrevios], [datosNuevos], [resultado], [fechaHora], [observacion], [detalle], [idInstitucion], [modulo], [tipoCuentaActor]) VALUES (N'666f433e-f36b-1410-88a7-00891fb53762', N'cf11117b-7385-4449-a7c4-5d603ab17123', N'CRUD', N'INICIAR_SESION_DISPOSITIVO', N'Medicion', N'2de67bf5-7ca4-4d85-b837-20c68acbdd1d', NULL, NULL, N'{"estadoMedicion": "PENDIENTE"}', N'{"estadoMedicion": "ADQUIRIENDO", "medio": "BLUETOOTH"}', N'EXITO', CAST(N'2026-10-25T17:16:06.4980000' AS DateTime2), NULL, NULL, NULL, N'MEDICIONES', NULL)
GO
INSERT [dbo].[Auditoria] ([idAuditoria], [idUsuario], [tipoEvento], [accion], [tablaAfectada], [idRegistro], [tablaRelacionada], [idRelacionado], [datosPrevios], [datosNuevos], [resultado], [fechaHora], [observacion], [detalle], [idInstitucion], [modulo], [tipoCuentaActor]) VALUES (N'6a6f433e-f36b-1410-88a7-00891fb53762', N'cf11117b-7385-4449-a7c4-5d603ab17123', N'CRUD', N'GUARDAR_MEDICION_DISPOSITIVO', N'Medicion', N'2de67bf5-7ca4-4d85-b837-20c68acbdd1d', NULL, NULL, N'{"estadoMedicion": "ADQUIRIENDO"}', N'{"estadoMedicion": "COMPLETADA", "origenGlucosa": "DEMO", "lecturasEstabilizadas": 8, "versionAlgoritmo": "firmware-glucolume-max30100-v1"}', N'EXITO', CAST(N'2026-10-25T17:17:04.1390000' AS DateTime2), NULL, NULL, NULL, N'MEDICIONES', NULL)
GO
-- dbo.AuditoriaContexto: 11 sentencias
INSERT [dbo].[AuditoriaContexto] ([idAuditoria], [idCorrelacion], [ipOrigen], [agenteUsuario], [motivo], [identificadorHash]) VALUES (N'085a433e-f36b-1410-88a6-00891fb53762', N'7a1864870b883df6ba505cd2e0068c3b', N'172.19.0.1', N'Microsoft Edge · Windows · Computadora', N'CUENTA_NO_REGISTRADA', NULL)
GO
INSERT [dbo].[AuditoriaContexto] ([idAuditoria], [idCorrelacion], [ipOrigen], [agenteUsuario], [motivo], [identificadorHash]) VALUES (N'396f433e-f36b-1410-88a7-00891fb53762', N'45771931b5f433a3f17f0c0e14263a90', N'172.19.0.1', N'Microsoft Edge · Windows · Computadora', NULL, NULL)
GO
INSERT [dbo].[AuditoriaContexto] ([idAuditoria], [idCorrelacion], [ipOrigen], [agenteUsuario], [motivo], [identificadorHash]) VALUES (N'406f433e-f36b-1410-88a7-00891fb53762', N'a987dfbb835f956e98a667ea818e9281', N'172.19.0.1', N'Microsoft Edge · Windows · Computadora', NULL, NULL)
GO
INSERT [dbo].[AuditoriaContexto] ([idAuditoria], [idCorrelacion], [ipOrigen], [agenteUsuario], [motivo], [identificadorHash]) VALUES (N'476f433e-f36b-1410-88a7-00891fb53762', N'399a71428dfe88b80499b7126be82e74', N'172.19.0.1', N'Microsoft Edge · Windows · Computadora', NULL, NULL)
GO
INSERT [dbo].[AuditoriaContexto] ([idAuditoria], [idCorrelacion], [ipOrigen], [agenteUsuario], [motivo], [identificadorHash]) VALUES (N'4e6f433e-f36b-1410-88a7-00891fb53762', N'c6d982bd3cb02bbca930477c773c929c', N'172.19.0.1', N'Microsoft Edge · Windows · Computadora', NULL, NULL)
GO
INSERT [dbo].[AuditoriaContexto] ([idAuditoria], [idCorrelacion], [ipOrigen], [agenteUsuario], [motivo], [identificadorHash]) VALUES (N'546f433e-f36b-1410-88a7-00891fb53762', N'db44cf6ef9e5db2f35960690dc64c3e9', N'172.19.0.1', N'Python-urllib/3.14', NULL, NULL)
GO
INSERT [dbo].[AuditoriaContexto] ([idAuditoria], [idCorrelacion], [ipOrigen], [agenteUsuario], [motivo], [identificadorHash]) VALUES (N'596f433e-f36b-1410-88a7-00891fb53762', N'd0cb04f94e6aaf760bb11373a519c64f', N'172.19.0.1', N'Microsoft Edge · Windows · Computadora', NULL, NULL)
GO
INSERT [dbo].[AuditoriaContexto] ([idAuditoria], [idCorrelacion], [ipOrigen], [agenteUsuario], [motivo], [identificadorHash]) VALUES (N'5e6f433e-f36b-1410-88a7-00891fb53762', N'f56ad0295780431c9cc8e760f9e6db2b', N'172.19.0.1', N'Microsoft Edge · Windows · Computadora', NULL, NULL)
GO
INSERT [dbo].[AuditoriaContexto] ([idAuditoria], [idCorrelacion], [ipOrigen], [agenteUsuario], [motivo], [identificadorHash]) VALUES (N'606f433e-f36b-1410-88a7-00891fb53762', N'6444659d5561b5834e9767b820fd99a1', N'172.19.0.1', N'Microsoft Edge · Windows · Computadora', NULL, NULL)
GO
INSERT [dbo].[AuditoriaContexto] ([idAuditoria], [idCorrelacion], [ipOrigen], [agenteUsuario], [motivo], [identificadorHash]) VALUES (N'666f433e-f36b-1410-88a7-00891fb53762', N'6444659d5561b5834e9767b820fd99a1', N'172.19.0.1', N'Microsoft Edge · Windows · Computadora', NULL, NULL)
GO
INSERT [dbo].[AuditoriaContexto] ([idAuditoria], [idCorrelacion], [ipOrigen], [agenteUsuario], [motivo], [identificadorHash]) VALUES (N'6a6f433e-f36b-1410-88a7-00891fb53762', N'ff177c4380ced35920902b3c444d39f8', N'172.19.0.1', N'Microsoft Edge · Windows · Computadora', NULL, NULL)
GO
-- dbo.ConsentimientoUsuario: 2 sentencias
INSERT [dbo].[ConsentimientoUsuario] ([idConsentimiento], [idUsuario], [tipo], [version], [estado], [fechaHora]) VALUES (N'9f04c521-c392-44fd-9e22-3ed21f6eb4bc', N'cf11117b-7385-4449-a7c4-5d603ab17123', N'DATOS_EXPERIMENTALES', N'1.0', N'ACEPTADO', CAST(N'2026-10-25T17:12:35.6230000' AS DateTime2))
GO
INSERT [dbo].[ConsentimientoUsuario] ([idConsentimiento], [idUsuario], [tipo], [version], [estado], [fechaHora]) VALUES (N'fab7d8dc-7f1f-49b2-ab55-41a281953f21', N'cf11117b-7385-4449-a7c4-5d603ab17123', N'POLITICA_PRIVACIDAD', N'1.1', N'ACEPTADO', CAST(N'2026-10-25T17:12:15.5960000' AS DateTime2))
GO
-- dbo.Dispositivo: 1 sentencias
INSERT [dbo].[Dispositivo] ([idDispositivo], [codigoDispositivo], [nombre], [modelo], [modeloSensor], [versionFirmware], [estado], [idInstitucionAsignada], [idInstitucionUsuarioResponsable], [fechaRegistro], [fechaAsignacionInstitucional]) VALUES (N'8cabe09f-6170-4235-a14d-d4ba94fab913', N'GL-0001', N'Arduino GlucoLume (registro automático)', N'Arduino UNO + MAX30100', N'MAX30100', NULL, N'OPERATIVO', NULL, NULL, CAST(N'2026-10-25T17:14:33.3180000' AS DateTime2), NULL)
GO
-- dbo.IdentidadExterna: 1 sentencias
INSERT [dbo].[IdentidadExterna] ([idIdentidadExterna], [idUsuario], [proveedor], [subjectProveedor], [emailProveedor], [emailVerificado], [fechaVinculacion], [ultimoAcceso]) VALUES (N'b0787080-2bac-4eb1-bc49-5b724da632bd', N'cf11117b-7385-4449-a7c4-5d603ab17123', N'GOOGLE', N'103082176263800800502', N'materialprog3@gmail.com', 1, CAST(N'2026-10-25T17:12:15.6480000' AS DateTime2), CAST(N'2026-10-25T17:12:15.5620000' AS DateTime2))
GO
-- dbo.Matriz: 1 sentencias
INSERT [dbo].[Matriz] ([idMatriz], [idInstitucion], [nombre], [version], [ambito], [fechaVigenciaDesde], [fechaVigenciaHasta], [descripcion], [estado], [fechaCreacion]) VALUES (N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', NULL, N'ADA 2026 - Seguimiento adulto no gestante', N'2', N'GLOBAL', CAST(N'2026-10-24' AS Date), NULL, N'Matriz orientativa para adultos con diabetes no gestantes. 27 reglas, incluye datos no informados. DEMO no representa una glucemia real.', N'ACTIVA', CAST(N'2026-10-24T17:57:42.1380000' AS DateTime2))
GO
-- dbo.Medicion: 1 sentencias
INSERT [dbo].[Medicion] ([idMedicion], [idPerfilMedicion], [idDispositivo], [idMatriz], [modoMedicion], [estadoMedicion], [fechaHoraInicio], [fechaHoraFin], [fechaHoraUltimaComida], [condicionComida], [edadAlMomento], [sexoModelo], [versionFirmwareAlMomento], [modeloSensorAlMomento], [versionAlgoritmo], [calidadSenal], [spo2], [frecuenciaCardiaca], [glucosaEstimada], [observacion], [origenGlucosa], [glucosaDispositivo], [unidadGlucosa], [indiceOptico], [lecturasEstabilizadas], [idReglaMatriz], [fechaVencimientoRetencion]) VALUES (N'2de67bf5-7ca4-4d85-b837-20c68acbdd1d', N'5a73b044-f895-4845-a549-5a6b07784a4c', N'8cabe09f-6170-4235-a14d-d4ba94fab913', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'GLUCOSA_EXPERIMENTAL', N'COMPLETADA', CAST(N'2026-10-25T17:16:06.4330000' AS DateTime2), CAST(N'2026-10-25T17:17:04.1320000' AS DateTime2), NULL, N'POSTPRANDIAL', 24, N'FEMENINO', NULL, N'MAX30100', N'firmware-glucolume-max30100-v1', NULL, CAST(97.20 AS Decimal(5, 2)), 104, NULL, N'Datos de prueba (DEMO): la glucosa es un valor sintético del firmware, no una medición.', N'DEMO', CAST(115.00 AS Decimal(8, 2)), N'mg/dL', CAST(1.95352 AS Decimal(10, 5)), 8, NULL, NULL)
GO
-- dbo.PerfilMedicion: 1 sentencias
INSERT [dbo].[PerfilMedicion] ([idPerfilMedicion], [tipoPerfil], [idUsuario], [idInstitucionUsuarioResponsable], [identificadorPseudonimo], [nombre], [apellido], [dni], [fechaNacimiento], [edadDeclarada], [sexoModelo], [fechaCreacion], [fechaUltimaMedicion], [fechaExpiracionDatosPersonales], [fechaDepuracionDatosPersonales], [correoResultados], [fechaAutorizacionCorreo], [fechaExpiracionCorreo], [idInstitucion]) VALUES (N'5a73b044-f895-4845-a549-5a6b07784a4c', N'CONSUMIDOR_FINAL', N'cf11117b-7385-4449-a7c4-5d603ab17123', NULL, NULL, N'Victoria Valentina', N'Maidana Corti', NULL, NULL, NULL, NULL, CAST(N'2026-10-25T17:12:20.8970000' AS DateTime2), NULL, NULL, NULL, NULL, NULL, NULL, NULL)
GO
-- dbo.ReglaMatriz: 27 sentencias
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'822acb52-fd59-4cf6-bfae-1491106acd5f', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'F_N_U', N'FEMENINO', NULL, NULL, N'NO_INFORMADA', NULL, NULL, CAST(70.00 AS Decimal(8, 2)), CAST(180.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'd443efab-0d7d-496d-8f58-253712e69e03', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'F_A65', N'FEMENINO', 65, 130, N'AYUNO', NULL, NULL, CAST(80.00 AS Decimal(8, 2)), CAST(130.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'f9360f3a-f45a-4756-8ab1-2b5c56596f2d', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'F_P65', N'FEMENINO', 65, 130, N'POSTPRANDIAL', 60, 120, CAST(70.00 AS Decimal(8, 2)), CAST(179.99 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'3c4f6280-d370-42a7-8e31-36f6385a4ec3', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'NI_N_U', N'NO_INFORMADO', NULL, NULL, N'NO_INFORMADA', NULL, NULL, CAST(70.00 AS Decimal(8, 2)), CAST(180.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'698eacb5-1ae0-4b11-883c-3f421db50ede', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'M_P65', N'MASCULINO', 65, 130, N'POSTPRANDIAL', 60, 120, CAST(70.00 AS Decimal(8, 2)), CAST(179.99 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'0bad3d05-6a3a-43bb-a31a-41650a8ce19b', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'F_A_U', N'FEMENINO', NULL, NULL, N'AYUNO', NULL, NULL, CAST(70.00 AS Decimal(8, 2)), CAST(180.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'296178cf-c274-4d63-8999-4b5787e61614', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'NI_A65', N'NO_INFORMADO', 65, 130, N'AYUNO', NULL, NULL, CAST(80.00 AS Decimal(8, 2)), CAST(130.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'ab78c569-54d9-4117-85ae-54a8d89ff84f', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'NI_P_U', N'NO_INFORMADO', NULL, NULL, N'POSTPRANDIAL', 60, 120, CAST(70.00 AS Decimal(8, 2)), CAST(180.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'6bd00be4-6bba-44b3-8a5f-5912bb6caa88', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'M_P18', N'MASCULINO', 18, 64, N'POSTPRANDIAL', 60, 120, CAST(70.00 AS Decimal(8, 2)), CAST(179.99 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'aeaa0b67-f02a-43bc-96b5-65f9d3aeddc0', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'M_N_U', N'MASCULINO', NULL, NULL, N'NO_INFORMADA', NULL, NULL, CAST(70.00 AS Decimal(8, 2)), CAST(180.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'a2420751-a38e-4c42-86e6-6922f7c08cec', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'NI_A18', N'NO_INFORMADO', 18, 64, N'AYUNO', NULL, NULL, CAST(80.00 AS Decimal(8, 2)), CAST(130.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'c34e8ca7-bd57-47c2-9fdc-778570ca6ff0', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'NI_N65', N'NO_INFORMADO', 65, 130, N'NO_INFORMADA', NULL, NULL, CAST(70.00 AS Decimal(8, 2)), CAST(180.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'7b6244b9-36e7-43b5-88ac-82013164e0a8', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'F_N18', N'FEMENINO', 18, 64, N'NO_INFORMADA', NULL, NULL, CAST(70.00 AS Decimal(8, 2)), CAST(180.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'd9c7e771-404b-4e6e-8194-8286e041cbc7', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'NI_N18', N'NO_INFORMADO', 18, 64, N'NO_INFORMADA', NULL, NULL, CAST(70.00 AS Decimal(8, 2)), CAST(180.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'7ac07889-0cd3-4238-b65e-86d97ccf1e76', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'F_P_U', N'FEMENINO', NULL, NULL, N'POSTPRANDIAL', 60, 120, CAST(70.00 AS Decimal(8, 2)), CAST(180.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'4c548453-3491-42f5-b9f9-8a97b5df3146', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'M_A_U', N'MASCULINO', NULL, NULL, N'AYUNO', NULL, NULL, CAST(70.00 AS Decimal(8, 2)), CAST(180.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'cfdc6985-7b13-4b70-b42a-8cc50e65a4b6', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'NI_P18', N'NO_INFORMADO', 18, 64, N'POSTPRANDIAL', 60, 120, CAST(70.00 AS Decimal(8, 2)), CAST(179.99 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'26cf402c-05c4-4ebd-ba7c-9bb244c5913d', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'F_A18', N'FEMENINO', 18, 64, N'AYUNO', NULL, NULL, CAST(80.00 AS Decimal(8, 2)), CAST(130.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'ca8804af-a19b-4c1d-a28a-9e91685908ff', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'F_N65', N'FEMENINO', 65, 130, N'NO_INFORMADA', NULL, NULL, CAST(70.00 AS Decimal(8, 2)), CAST(180.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'bc263539-01d0-4399-91e5-9fdbc68d3552', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'M_N18', N'MASCULINO', 18, 64, N'NO_INFORMADA', NULL, NULL, CAST(70.00 AS Decimal(8, 2)), CAST(180.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'6a74e70c-605f-4977-a07f-afea7362eb1b', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'M_P_U', N'MASCULINO', NULL, NULL, N'POSTPRANDIAL', 60, 120, CAST(70.00 AS Decimal(8, 2)), CAST(180.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'84a7914d-5ca4-4461-b347-cc14970cf867', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'M_N65', N'MASCULINO', 65, 130, N'NO_INFORMADA', NULL, NULL, CAST(70.00 AS Decimal(8, 2)), CAST(180.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'49e02c41-e98e-462b-8695-d748558fcc50', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'F_P18', N'FEMENINO', 18, 64, N'POSTPRANDIAL', 60, 120, CAST(70.00 AS Decimal(8, 2)), CAST(179.99 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'1c62026b-4766-45ab-9bae-e6487546abe0', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'M_A18', N'MASCULINO', 18, 64, N'AYUNO', NULL, NULL, CAST(80.00 AS Decimal(8, 2)), CAST(130.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'45e8d379-3ad5-4a97-a480-ecb900a8dfdd', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'NI_A_U', N'NO_INFORMADO', NULL, NULL, N'AYUNO', NULL, NULL, CAST(70.00 AS Decimal(8, 2)), CAST(180.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'c49916ad-ff57-4693-ac08-f309044d5764', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'M_A65', N'MASCULINO', 65, 130, N'AYUNO', NULL, NULL, CAST(80.00 AS Decimal(8, 2)), CAST(130.00 AS Decimal(8, 2)))
GO
INSERT [dbo].[ReglaMatriz] ([idReglaMatriz], [idMatriz], [codigoRegla], [sexoModelo], [edadDesde], [edadHasta], [condicionComida], [minutosComidaMin], [minutosComidaMax], [glucosaMinReferencia], [glucosaMaxReferencia]) VALUES (N'44a21f69-d5d8-4e1a-b631-fa9198a172a7', N'fe9e4149-c42e-4d85-b72b-cd96302cfbba', N'NI_P65', N'NO_INFORMADO', 65, 130, N'POSTPRANDIAL', 60, 120, CAST(70.00 AS Decimal(8, 2)), CAST(179.99 AS Decimal(8, 2)))
GO
-- dbo.SesionUsuario: 2 sentencias
INSERT [dbo].[SesionUsuario] ([idSesion], [idUsuario], [refreshTokenHash], [fechaCreacion], [fechaExpiracion], [fechaRevocacion]) VALUES (N'64924327-44d3-4f87-967b-5c9333a98450', N'cf11117b-7385-4449-a7c4-5d603ab17123', N'66fe107964130bc29fcfb37fe923d7537c508e9b71a84cd4c0ad701b0c369d76', CAST(N'2026-10-25T17:12:15.9170000' AS DateTime2), CAST(N'2026-11-01T17:12:15.9160000' AS DateTime2), CAST(N'2026-10-25T19:19:38.2040000' AS DateTime2))
GO
INSERT [dbo].[SesionUsuario] ([idSesion], [idUsuario], [refreshTokenHash], [fechaCreacion], [fechaExpiracion], [fechaRevocacion]) VALUES (N'4ce3e8d1-bd84-4c1a-a0eb-b6e191ca3fc2', N'cf11117b-7385-4449-a7c4-5d603ab17123', N'459270c9a291b43db2db873fe6c74f95fac23d974a9192e290ee29d5017b9177', CAST(N'2026-10-25T19:19:38.2170000' AS DateTime2), CAST(N'2026-11-01T19:19:38.2170000' AS DateTime2), NULL)
GO
-- dbo.TokenCuenta: 1 sentencias
INSERT [dbo].[TokenCuenta] ([idTokenCuenta], [idUsuario], [tipo], [tokenHash], [fechaCreacion], [fechaExpiracion], [fechaUso]) VALUES (N'd154b598-3d4f-4d0e-aa1d-270b87256d06', N'cf11117b-7385-4449-a7c4-5d603ab17123', N'INTERCAMBIO_GOOGLE', N'c6d8966b21530f973cb8f75c9df010482727300ddc9d68e04196feccbf1c5428', CAST(N'2026-10-25T17:12:15.6580000' AS DateTime2), CAST(N'2026-10-25T17:14:15.6580000' AS DateTime2), CAST(N'2026-10-25T17:12:15.8750000' AS DateTime2))
GO
-- dbo.Usuario: 1 sentencias
INSERT [dbo].[Usuario] ([idUsuario], [nombre], [apellido], [correoElectronico], [usuario], [tipoCuenta], [estado], [fechaCreacion], [fechaActualizacion], [fechaEliminacion], [fechaNacimiento], [sexo], [notificarNuevoInicioSesion], [fechaInicioGracia], [fechaVencimientoGracia]) VALUES (N'cf11117b-7385-4449-a7c4-5d603ab17123', N'Victoria Valentina', N'Maidana Corti', N'materialprog3@gmail.com', NULL, N'CONSUMIDOR_FINAL', N'ACTIVO', CAST(N'2026-10-25T17:12:15.5750000' AS DateTime2), CAST(N'2026-10-25T17:12:15.5750000' AS DateTime2), NULL, NULL, NULL, 1, NULL, NULL)
GO
-- ===== 3. Claves foraneas =====
ALTER TABLE [dbo].[Auditoria]  WITH CHECK ADD  CONSTRAINT [FK_Auditoria_Institucion] FOREIGN KEY([idInstitucion])
REFERENCES [dbo].[Institucion] ([idInstitucion])
GO
ALTER TABLE [dbo].[Auditoria] CHECK CONSTRAINT [FK_Auditoria_Institucion]
GO
ALTER TABLE [dbo].[Auditoria]  WITH CHECK ADD  CONSTRAINT [FK_Auditoria_Usuario] FOREIGN KEY([idUsuario])
REFERENCES [dbo].[Usuario] ([idUsuario])
GO
ALTER TABLE [dbo].[Auditoria] CHECK CONSTRAINT [FK_Auditoria_Usuario]
GO
ALTER TABLE [dbo].[AuditoriaContexto]  WITH CHECK ADD  CONSTRAINT [FK_AuditoriaContexto_Auditoria] FOREIGN KEY([idAuditoria])
REFERENCES [dbo].[Auditoria] ([idAuditoria])
ON DELETE CASCADE
GO
ALTER TABLE [dbo].[AuditoriaContexto] CHECK CONSTRAINT [FK_AuditoriaContexto_Auditoria]
GO
ALTER TABLE [dbo].[CodigoRecuperacionMfa]  WITH CHECK ADD  CONSTRAINT [FK_CodigoRecuperacionMfa_FactorMfa] FOREIGN KEY([idFactorMfa])
REFERENCES [dbo].[FactorMfa] ([idFactorMfa])
GO
ALTER TABLE [dbo].[CodigoRecuperacionMfa] CHECK CONSTRAINT [FK_CodigoRecuperacionMfa_FactorMfa]
GO
ALTER TABLE [dbo].[ConfiguracionNotificacion]  WITH CHECK ADD  CONSTRAINT [FK_ConfiguracionNotificacion_Usuario] FOREIGN KEY([idUsuario])
REFERENCES [dbo].[Usuario] ([idUsuario])
GO
ALTER TABLE [dbo].[ConfiguracionNotificacion] CHECK CONSTRAINT [FK_ConfiguracionNotificacion_Usuario]
GO
ALTER TABLE [dbo].[ConsentimientoUsuario]  WITH CHECK ADD  CONSTRAINT [FK_ConsentimientoUsuario_Usuario] FOREIGN KEY([idUsuario])
REFERENCES [dbo].[Usuario] ([idUsuario])
GO
ALTER TABLE [dbo].[ConsentimientoUsuario] CHECK CONSTRAINT [FK_ConsentimientoUsuario_Usuario]
GO
ALTER TABLE [dbo].[CredencialLocal]  WITH CHECK ADD  CONSTRAINT [FK_CredencialLocal_Usuario] FOREIGN KEY([idUsuario])
REFERENCES [dbo].[Usuario] ([idUsuario])
GO
ALTER TABLE [dbo].[CredencialLocal] CHECK CONSTRAINT [FK_CredencialLocal_Usuario]
GO
ALTER TABLE [dbo].[Dispositivo]  WITH CHECK ADD  CONSTRAINT [FK_Dispositivo_Institucion] FOREIGN KEY([idInstitucionAsignada])
REFERENCES [dbo].[Institucion] ([idInstitucion])
GO
ALTER TABLE [dbo].[Dispositivo] CHECK CONSTRAINT [FK_Dispositivo_Institucion]
GO
ALTER TABLE [dbo].[Dispositivo]  WITH CHECK ADD  CONSTRAINT [FK_Dispositivo_Responsable] FOREIGN KEY([idInstitucionUsuarioResponsable])
REFERENCES [dbo].[InstitucionUsuario] ([idInstitucionUsuario])
GO
ALTER TABLE [dbo].[Dispositivo] CHECK CONSTRAINT [FK_Dispositivo_Responsable]
GO
ALTER TABLE [dbo].[EnvioResultado]  WITH CHECK ADD  CONSTRAINT [FK_EnvioResultado_Medicion] FOREIGN KEY([idMedicion])
REFERENCES [dbo].[Medicion] ([idMedicion])
GO
ALTER TABLE [dbo].[EnvioResultado] CHECK CONSTRAINT [FK_EnvioResultado_Medicion]
GO
ALTER TABLE [dbo].[FactorMfa]  WITH CHECK ADD  CONSTRAINT [FK_FactorMfa_Usuario] FOREIGN KEY([idUsuario])
REFERENCES [dbo].[Usuario] ([idUsuario])
GO
ALTER TABLE [dbo].[FactorMfa] CHECK CONSTRAINT [FK_FactorMfa_Usuario]
GO
ALTER TABLE [dbo].[GrupoUsuario]  WITH CHECK ADD  CONSTRAINT [FK_GrupoUsuario_Grupo] FOREIGN KEY([idGrupo])
REFERENCES [dbo].[Grupo] ([idGrupo])
GO
ALTER TABLE [dbo].[GrupoUsuario] CHECK CONSTRAINT [FK_GrupoUsuario_Grupo]
GO
ALTER TABLE [dbo].[GrupoUsuario]  WITH CHECK ADD  CONSTRAINT [FK_GrupoUsuario_Usuario] FOREIGN KEY([idUsuario])
REFERENCES [dbo].[Usuario] ([idUsuario])
GO
ALTER TABLE [dbo].[GrupoUsuario] CHECK CONSTRAINT [FK_GrupoUsuario_Usuario]
GO
ALTER TABLE [dbo].[IdentidadExterna]  WITH CHECK ADD  CONSTRAINT [FK_IdentidadExterna_Usuario] FOREIGN KEY([idUsuario])
REFERENCES [dbo].[Usuario] ([idUsuario])
GO
ALTER TABLE [dbo].[IdentidadExterna] CHECK CONSTRAINT [FK_IdentidadExterna_Usuario]
GO
ALTER TABLE [dbo].[Institucion]  WITH CHECK ADD  CONSTRAINT [FK_Institucion_cierreAdministrativo_Usuario] FOREIGN KEY([idUsuarioCierreAdministrativo])
REFERENCES [dbo].[Usuario] ([idUsuario])
GO
ALTER TABLE [dbo].[Institucion] CHECK CONSTRAINT [FK_Institucion_cierreAdministrativo_Usuario]
GO
ALTER TABLE [dbo].[InstitucionUsuario]  WITH CHECK ADD  CONSTRAINT [FK_InstitucionUsuario_Institucion] FOREIGN KEY([idInstitucion])
REFERENCES [dbo].[Institucion] ([idInstitucion])
GO
ALTER TABLE [dbo].[InstitucionUsuario] CHECK CONSTRAINT [FK_InstitucionUsuario_Institucion]
GO
ALTER TABLE [dbo].[InstitucionUsuario]  WITH CHECK ADD  CONSTRAINT [FK_InstitucionUsuario_Invitado] FOREIGN KEY([idUsuarioInvitado])
REFERENCES [dbo].[Usuario] ([idUsuario])
GO
ALTER TABLE [dbo].[InstitucionUsuario] CHECK CONSTRAINT [FK_InstitucionUsuario_Invitado]
GO
ALTER TABLE [dbo].[InstitucionUsuario]  WITH CHECK ADD  CONSTRAINT [FK_InstitucionUsuario_Invitador] FOREIGN KEY([idUsuarioInvitador])
REFERENCES [dbo].[Usuario] ([idUsuario])
GO
ALTER TABLE [dbo].[InstitucionUsuario] CHECK CONSTRAINT [FK_InstitucionUsuario_Invitador]
GO
ALTER TABLE [dbo].[Matriz]  WITH CHECK ADD  CONSTRAINT [FK_Matriz_Institucion] FOREIGN KEY([idInstitucion])
REFERENCES [dbo].[Institucion] ([idInstitucion])
GO
ALTER TABLE [dbo].[Matriz] CHECK CONSTRAINT [FK_Matriz_Institucion]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [FK_Medicion_Dispositivo] FOREIGN KEY([idDispositivo])
REFERENCES [dbo].[Dispositivo] ([idDispositivo])
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [FK_Medicion_Dispositivo]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [FK_Medicion_Matriz] FOREIGN KEY([idMatriz])
REFERENCES [dbo].[Matriz] ([idMatriz])
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [FK_Medicion_Matriz]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [FK_Medicion_Perfil] FOREIGN KEY([idPerfilMedicion])
REFERENCES [dbo].[PerfilMedicion] ([idPerfilMedicion])
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [FK_Medicion_Perfil]
GO
ALTER TABLE [dbo].[Medicion]  WITH CHECK ADD  CONSTRAINT [FK_Medicion_ReglaMatriz] FOREIGN KEY([idReglaMatriz])
REFERENCES [dbo].[ReglaMatriz] ([idReglaMatriz])
GO
ALTER TABLE [dbo].[Medicion] CHECK CONSTRAINT [FK_Medicion_ReglaMatriz]
GO
ALTER TABLE [dbo].[MedicionReferenciaCapilar]  WITH CHECK ADD  CONSTRAINT [FK_MedicionReferenciaCapilar_Medicion] FOREIGN KEY([idMedicion])
REFERENCES [dbo].[Medicion] ([idMedicion])
GO
ALTER TABLE [dbo].[MedicionReferenciaCapilar] CHECK CONSTRAINT [FK_MedicionReferenciaCapilar_Medicion]
GO
ALTER TABLE [dbo].[MuestraSensor]  WITH CHECK ADD  CONSTRAINT [FK_MuestraSensor_Medicion] FOREIGN KEY([idMedicion])
REFERENCES [dbo].[Medicion] ([idMedicion])
GO
ALTER TABLE [dbo].[MuestraSensor] CHECK CONSTRAINT [FK_MuestraSensor_Medicion]
GO
ALTER TABLE [dbo].[PerfilMedicion]  WITH CHECK ADD  CONSTRAINT [FK_PerfilMedicion_Institucion] FOREIGN KEY([idInstitucion])
REFERENCES [dbo].[Institucion] ([idInstitucion])
GO
ALTER TABLE [dbo].[PerfilMedicion] CHECK CONSTRAINT [FK_PerfilMedicion_Institucion]
GO
ALTER TABLE [dbo].[PerfilMedicion]  WITH CHECK ADD  CONSTRAINT [FK_PerfilMedicion_Responsable] FOREIGN KEY([idInstitucionUsuarioResponsable])
REFERENCES [dbo].[InstitucionUsuario] ([idInstitucionUsuario])
GO
ALTER TABLE [dbo].[PerfilMedicion] CHECK CONSTRAINT [FK_PerfilMedicion_Responsable]
GO
ALTER TABLE [dbo].[PerfilMedicion]  WITH CHECK ADD  CONSTRAINT [FK_PerfilMedicion_Usuario] FOREIGN KEY([idUsuario])
REFERENCES [dbo].[Usuario] ([idUsuario])
GO
ALTER TABLE [dbo].[PerfilMedicion] CHECK CONSTRAINT [FK_PerfilMedicion_Usuario]
GO
ALTER TABLE [dbo].[PeriodoPrueba]  WITH CHECK ADD  CONSTRAINT [FK_PeriodoPrueba_Institucion] FOREIGN KEY([idInstitucion])
REFERENCES [dbo].[Institucion] ([idInstitucion])
GO
ALTER TABLE [dbo].[PeriodoPrueba] CHECK CONSTRAINT [FK_PeriodoPrueba_Institucion]
GO
ALTER TABLE [dbo].[PeriodoPrueba]  WITH CHECK ADD  CONSTRAINT [FK_PeriodoPrueba_Usuario] FOREIGN KEY([idUsuario])
REFERENCES [dbo].[Usuario] ([idUsuario])
GO
ALTER TABLE [dbo].[PeriodoPrueba] CHECK CONSTRAINT [FK_PeriodoPrueba_Usuario]
GO
ALTER TABLE [dbo].[ReasignacionPaciente]  WITH CHECK ADD  CONSTRAINT [FK_ReasignacionPaciente_Anterior] FOREIGN KEY([idOperadorAnterior])
REFERENCES [dbo].[InstitucionUsuario] ([idInstitucionUsuario])
GO
ALTER TABLE [dbo].[ReasignacionPaciente] CHECK CONSTRAINT [FK_ReasignacionPaciente_Anterior]
GO
ALTER TABLE [dbo].[ReasignacionPaciente]  WITH CHECK ADD  CONSTRAINT [FK_ReasignacionPaciente_Institucion] FOREIGN KEY([idInstitucion])
REFERENCES [dbo].[Institucion] ([idInstitucion])
GO
ALTER TABLE [dbo].[ReasignacionPaciente] CHECK CONSTRAINT [FK_ReasignacionPaciente_Institucion]
GO
ALTER TABLE [dbo].[ReasignacionPaciente]  WITH CHECK ADD  CONSTRAINT [FK_ReasignacionPaciente_Nuevo] FOREIGN KEY([idOperadorNuevo])
REFERENCES [dbo].[InstitucionUsuario] ([idInstitucionUsuario])
GO
ALTER TABLE [dbo].[ReasignacionPaciente] CHECK CONSTRAINT [FK_ReasignacionPaciente_Nuevo]
GO
ALTER TABLE [dbo].[ReasignacionPaciente]  WITH CHECK ADD  CONSTRAINT [FK_ReasignacionPaciente_Perfil] FOREIGN KEY([idPerfilMedicion])
REFERENCES [dbo].[PerfilMedicion] ([idPerfilMedicion])
GO
ALTER TABLE [dbo].[ReasignacionPaciente] CHECK CONSTRAINT [FK_ReasignacionPaciente_Perfil]
GO
ALTER TABLE [dbo].[ReasignacionPaciente]  WITH CHECK ADD  CONSTRAINT [FK_ReasignacionPaciente_Resolutor] FOREIGN KEY([idUsuarioResolutor])
REFERENCES [dbo].[Usuario] ([idUsuario])
GO
ALTER TABLE [dbo].[ReasignacionPaciente] CHECK CONSTRAINT [FK_ReasignacionPaciente_Resolutor]
GO
ALTER TABLE [dbo].[ReglaMatriz]  WITH CHECK ADD  CONSTRAINT [FK_ReglaMatriz_Matriz] FOREIGN KEY([idMatriz])
REFERENCES [dbo].[Matriz] ([idMatriz])
GO
ALTER TABLE [dbo].[ReglaMatriz] CHECK CONSTRAINT [FK_ReglaMatriz_Matriz]
GO
ALTER TABLE [dbo].[SesionUsuario]  WITH CHECK ADD  CONSTRAINT [FK_SesionUsuario_Usuario] FOREIGN KEY([idUsuario])
REFERENCES [dbo].[Usuario] ([idUsuario])
GO
ALTER TABLE [dbo].[SesionUsuario] CHECK CONSTRAINT [FK_SesionUsuario_Usuario]
GO
ALTER TABLE [dbo].[Suscripcion]  WITH CHECK ADD  CONSTRAINT [FK_Suscripcion_Institucion] FOREIGN KEY([idInstitucion])
REFERENCES [dbo].[Institucion] ([idInstitucion])
GO
ALTER TABLE [dbo].[Suscripcion] CHECK CONSTRAINT [FK_Suscripcion_Institucion]
GO
ALTER TABLE [dbo].[Suscripcion]  WITH CHECK ADD  CONSTRAINT [FK_Suscripcion_Plan] FOREIGN KEY([idPlan])
REFERENCES [dbo].[PlanSuscripcion] ([idPlan])
GO
ALTER TABLE [dbo].[Suscripcion] CHECK CONSTRAINT [FK_Suscripcion_Plan]
GO
ALTER TABLE [dbo].[Suscripcion]  WITH CHECK ADD  CONSTRAINT [FK_Suscripcion_Titular] FOREIGN KEY([idUsuarioTitular])
REFERENCES [dbo].[Usuario] ([idUsuario])
GO
ALTER TABLE [dbo].[Suscripcion] CHECK CONSTRAINT [FK_Suscripcion_Titular]
GO
ALTER TABLE [dbo].[SuscripcionUsuario]  WITH CHECK ADD  CONSTRAINT [FK_SuscripcionUsuario_Suscripcion] FOREIGN KEY([idSuscripcion])
REFERENCES [dbo].[Suscripcion] ([idSuscripcion])
GO
ALTER TABLE [dbo].[SuscripcionUsuario] CHECK CONSTRAINT [FK_SuscripcionUsuario_Suscripcion]
GO
ALTER TABLE [dbo].[SuscripcionUsuario]  WITH CHECK ADD  CONSTRAINT [FK_SuscripcionUsuario_Usuario] FOREIGN KEY([idUsuario])
REFERENCES [dbo].[Usuario] ([idUsuario])
GO
ALTER TABLE [dbo].[SuscripcionUsuario] CHECK CONSTRAINT [FK_SuscripcionUsuario_Usuario]
GO
ALTER TABLE [dbo].[TokenCuenta]  WITH CHECK ADD  CONSTRAINT [FK_TokenCuenta_Usuario] FOREIGN KEY([idUsuario])
REFERENCES [dbo].[Usuario] ([idUsuario])
GO
ALTER TABLE [dbo].[TokenCuenta] CHECK CONSTRAINT [FK_TokenCuenta_Usuario]
GO
ALTER TABLE [dbo].[TransaccionPago]  WITH CHECK ADD  CONSTRAINT [FK_TransaccionPago_Proveedor] FOREIGN KEY([idProveedorPago])
REFERENCES [dbo].[ProveedorPago] ([idProveedorPago])
GO
ALTER TABLE [dbo].[TransaccionPago] CHECK CONSTRAINT [FK_TransaccionPago_Proveedor]
GO
ALTER TABLE [dbo].[TransaccionPago]  WITH CHECK ADD  CONSTRAINT [FK_TransaccionPago_Suscripcion] FOREIGN KEY([idSuscripcion])
REFERENCES [dbo].[Suscripcion] ([idSuscripcion])
GO
ALTER TABLE [dbo].[TransaccionPago] CHECK CONSTRAINT [FK_TransaccionPago_Suscripcion]
GO
ALTER TABLE [dbo].[TransferenciaAdministracion]  WITH CHECK ADD  CONSTRAINT [FK_TransferenciaAdministracion_destino] FOREIGN KEY([idUsuarioDestino])
REFERENCES [dbo].[Usuario] ([idUsuario])
GO
ALTER TABLE [dbo].[TransferenciaAdministracion] CHECK CONSTRAINT [FK_TransferenciaAdministracion_destino]
GO
ALTER TABLE [dbo].[TransferenciaAdministracion]  WITH CHECK ADD  CONSTRAINT [FK_TransferenciaAdministracion_origen] FOREIGN KEY([idUsuarioOrigen])
REFERENCES [dbo].[Usuario] ([idUsuario])
GO
ALTER TABLE [dbo].[TransferenciaAdministracion] CHECK CONSTRAINT [FK_TransferenciaAdministracion_origen]
GO
ALTER TABLE [dbo].[TransferenciaPerfil]  WITH CHECK ADD  CONSTRAINT [FK_TransferenciaPerfil_Destino] FOREIGN KEY([idOperadorDestino])
REFERENCES [dbo].[InstitucionUsuario] ([idInstitucionUsuario])
GO
ALTER TABLE [dbo].[TransferenciaPerfil] CHECK CONSTRAINT [FK_TransferenciaPerfil_Destino]
GO
ALTER TABLE [dbo].[TransferenciaPerfil]  WITH CHECK ADD  CONSTRAINT [FK_TransferenciaPerfil_Perfil] FOREIGN KEY([idPerfilMedicion])
REFERENCES [dbo].[PerfilMedicion] ([idPerfilMedicion])
GO
ALTER TABLE [dbo].[TransferenciaPerfil] CHECK CONSTRAINT [FK_TransferenciaPerfil_Perfil]
GO
-- ===== 4. Procedimientos =====
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE   PROCEDURE [dbo].[usp_GlucoLume_CompararGlucosa]
    @Glucosa DECIMAL(8,2),
    @Edad SMALLINT = NULL,
    @Sexo NVARCHAR(30) = NULL,
    @CondicionComida NVARCHAR(30) = N'NO_INFORMADA',
    @MinutosComida INT = NULL,
    @TipoDato NVARCHAR(20) = N'DEMO',
    @IdInstitucion UNIQUEIDENTIFIER = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @idMatriz UNIQUEIDENTIFIER = NULL,
            @idRegla UNIQUEIDENTIFIER = NULL,
            @min DECIMAL(8,2) = NULL,
            @max DECIMAL(8,2) = NULL,
            @condicionAplicada NVARCHAR(30) = NULL,
            @comparacion NVARCHAR(60) = N'SIN_COMPARACION',
            @resultado NVARCHAR(60) = N'SIN_COMPARACION',
            @origenReferencia NVARCHAR(70) = N'SIN_REGLA',
            @sexoInformado BIT = 0,
            @edadInformada BIT = 0,
            @clasificacionHabilitada BIT = 0,
            @hoy DATE = CONVERT(DATE, SYSDATETIME());

    SET @Sexo = UPPER(LTRIM(RTRIM(COALESCE(@Sexo, N''))));
    SET @CondicionComida = UPPER(LTRIM(RTRIM(COALESCE(@CondicionComida, N''))));
    SET @TipoDato = UPPER(LTRIM(RTRIM(COALESCE(@TipoDato, N'DEMO'))));

    IF @TipoDato NOT IN (N'CAPILAR', N'EXPERIMENTAL', N'DEMO')
        THROW 51007, 'TipoDato debe ser CAPILAR, EXPERIMENTAL o DEMO.', 1;

    IF @Sexo IN (N'FEMENINO', N'MASCULINO') SET @sexoInformado = 1;
    ELSE SET @Sexo = N'NO_INFORMADO';

    IF @Edad IS NOT NULL SET @edadInformada = 1;

    IF @CondicionComida NOT IN (N'AYUNO', N'POSTPRANDIAL', N'NO_INFORMADA')
        SET @CondicionComida = N'NO_INFORMADA';

    -- Prioridad institucional; en ausencia de matriz institucional, la global.
    IF @IdInstitucion IS NOT NULL
        SELECT TOP (1) @idMatriz = m.idMatriz
        FROM dbo.Matriz AS m
        WHERE m.ambito = N'INSTITUCION' AND m.idInstitucion = @IdInstitucion
          AND m.estado = N'ACTIVA' AND m.fechaVigenciaDesde <= @hoy
          AND (m.fechaVigenciaHasta IS NULL OR m.fechaVigenciaHasta >= @hoy);

    IF @idMatriz IS NULL
        SELECT TOP (1) @idMatriz = m.idMatriz
        FROM dbo.Matriz AS m
        WHERE m.ambito = N'GLOBAL' AND m.idInstitucion IS NULL
          AND m.estado = N'ACTIVA' AND m.fechaVigenciaDesde <= @hoy
          AND (m.fechaVigenciaHasta IS NULL OR m.fechaVigenciaHasta >= @hoy);

    IF @Glucosa IS NULL OR @Glucosa <= 0
        SET @comparacion = N'VALOR_INVALIDO';
    ELSE IF @idMatriz IS NULL
        SET @comparacion = N'SIN_MATRIZ';
    ELSE IF @Edad IS NOT NULL AND (@Edad < 18 OR @Edad > 130)
        SET @comparacion = N'EDAD_FUERA_DE_ALCANCE';
    ELSE
    BEGIN
        SELECT TOP (1)
               @idRegla = r.idReglaMatriz,
               @min = r.glucosaMinReferencia,
               @max = r.glucosaMaxReferencia,
               @condicionAplicada = r.condicionComida,
               @origenReferencia = CASE
                    WHEN @Edad IS NULL THEN N'REGLA_EDAD_NO_INFORMADA_SOLO_ORIENTATIVA'
                    WHEN @Sexo = N'NO_INFORMADO' THEN N'REGLA_SEXO_NO_INFORMADO'
                    WHEN r.condicionComida = N'NO_INFORMADA' THEN N'REGLA_COMIDA_NO_INFORMADA'
                    ELSE N'REGLA_DEL_PERFIL'
               END
        FROM dbo.ReglaMatriz AS r
        WHERE r.idMatriz = @idMatriz
          AND r.sexoModelo = @Sexo
          AND ((@Edad IS NULL AND r.edadDesde IS NULL AND r.edadHasta IS NULL)
               OR (@Edad IS NOT NULL AND r.edadDesde IS NOT NULL
                   AND @Edad BETWEEN r.edadDesde AND r.edadHasta))
          AND (r.condicionComida = @CondicionComida
               OR r.condicionComida = N'NO_INFORMADA')
          AND (r.condicionComida <> N'POSTPRANDIAL'
               OR (@MinutosComida IS NOT NULL AND @MinutosComida >= 0
                   AND @MinutosComida BETWEEN COALESCE(r.minutosComidaMin, 0)
                                          AND COALESCE(r.minutosComidaMax, 2147483647)))
        ORDER BY CASE WHEN r.condicionComida = @CondicionComida THEN 0 ELSE 1 END,
                 r.codigoRegla;

        IF @idRegla IS NULL SET @comparacion = N'SIN_REGLA';
    END;

    IF @Glucosa > 0 AND @min IS NOT NULL AND @max IS NOT NULL
    BEGIN
        IF @Glucosa < 54 SET @comparacion = N'MUY_BAJO';
        ELSE IF @Glucosa < 70 SET @comparacion = N'BAJO';
        ELSE IF @Glucosa < @min SET @comparacion = N'BAJO_OBJETIVO';
        ELSE IF @Glucosa <= @max
            SET @comparacion = CASE WHEN @Edad IS NULL OR @condicionAplicada = N'NO_INFORMADA'
                                   THEN N'EN_RANGO_ORIENTATIVO' ELSE N'EN_RANGO_REFERENCIA' END;
        ELSE SET @comparacion = CASE WHEN @Edad IS NULL OR @condicionAplicada = N'NO_INFORMADA'
                                   THEN N'SOBRE_REFERENCIA_ORIENTATIVA' ELSE N'ALTO_OBJETIVO' END;
    END;

    SET @clasificacionHabilitada = CASE
        WHEN @TipoDato = N'CAPILAR' AND @Edad BETWEEN 18 AND 130
         AND @condicionAplicada IN (N'AYUNO', N'POSTPRANDIAL')
         AND @idRegla IS NOT NULL THEN 1 ELSE 0 END;

    SET @resultado = CASE
        WHEN @comparacion IN (N'VALOR_INVALIDO', N'SIN_MATRIZ', N'EDAD_FUERA_DE_ALCANCE', N'SIN_REGLA')
            THEN @comparacion
        WHEN @TipoDato = N'DEMO' THEN N'SIMULADO'
        WHEN @TipoDato = N'EXPERIMENTAL' THEN N'NO_VALIDADO'
        WHEN @Edad IS NULL THEN N'REFERENCIA_ORIENTATIVA_SIN_EDAD'
        WHEN @condicionAplicada = N'NO_INFORMADA' THEN N'REFERENCIA_ORIENTATIVA'
        ELSE @comparacion END;

    SELECT @Glucosa AS glucosaMgDl,
           @TipoDato AS tipoDato,
           @resultado AS resultadoPublicable,
           @comparacion AS comparacionNumericaDeEstudio,
           @min AS referenciaMinMgDl,
           @max AS referenciaMaxMgDl,
           @condicionAplicada AS condicionAplicada,
           @idMatriz AS idMatriz,
           @idRegla AS idReglaMatriz,
           @origenReferencia AS origenReferencia,
           @sexoInformado AS sexoInformado,
           @edadInformada AS edadInformada,
           @clasificacionHabilitada AS clasificacionHabilitada,
           N'Referencia orientativa para adultos con diabetes no gestantes, no diagnostica. '
            + N'Sin edad no hay interpretacion clinica. DEMO es sintetico y EXPERIMENTAL no validado.' AS advertencia;
END;
GO
-- ===== 5. Verificacion =====
SELECT COUNT(*) AS tablas FROM sys.tables WHERE is_ms_shipped = 0;
SELECT d.codigoDispositivo, m.fechaHoraInicio, m.estadoMedicion, m.frecuenciaCardiaca, m.spo2, m.glucosaDispositivo, m.origenGlucosa, m.glucosaEstimada
FROM dbo.Medicion m JOIN dbo.Dispositivo d ON d.idDispositivo = m.idDispositivo ORDER BY m.fechaHoraInicio DESC;
GO
SET NOEXEC OFF;
GO