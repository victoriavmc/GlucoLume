-- GlucoLume - Aviso de vencimiento de matrices globales al administrador de la plataforma.
-- Se aplica sobre una base que ya tiene GlucoLume_notificaciones_v8.sql (y la matriz de referencia).
--
-- Qué hace (una transacción, sin borrar ni modificar ninguna fila existente):
--   1. Matriz: agrega el estado de los avisos de vencimiento (avisoVencimientoNivel, avisoVencimientoUltimo,
--      avisoVencimientoSilenciado). Las filas actuales quedan sin aviso enviado y no silenciadas.
--   2. CHECK de evento en NotificacionUsuario y PreferenciaNotificacion: admite PLATAFORMA_MATRIZ_VENCIMIENTO (solo llega
--      al administrador de la plataforma, por la página).
--   3. Permiso: el servicio «notifications» (rol_glucolume_retencion) reserva y marca los avisos en Matriz.
--
-- Idempotente. Requiere permiso de DDL (lo aplica quien administra la base).
--   sqlcmd -S <servidor> -d <base> -I -i GlucoLume_matriz_vencimiento.sql -v CONFIRMAR="ACTUALIZAR_MATRIZ_VENCIMIENTO"
-- Antes: respaldo restaurable (BACKUP ... WITH CHECKSUM) y, si hay dudas, probar el script en una copia restaurada.
-- Reversión: quitar las tres columnas y volver a crear los CHECK sin PLATAFORMA_MATRIZ_VENCIMIENTO (antes borrar esos avisos).
-- Mientras no se aplique, la matriz sigue funcionando; el aviso de vencimiento no se guarda y queda como error en el log.

:on error exit

IF N'$(CONFIRMAR)' <> N'ACTUALIZAR_MATRIZ_VENCIMIENTO'
   OR OBJECT_ID(N'dbo.Matriz', N'U') IS NULL
   OR OBJECT_ID(N'dbo.NotificacionUsuario', N'U') IS NULL
   OR OBJECT_ID(N'dbo.PreferenciaNotificacion', N'U') IS NULL
   OR COL_LENGTH(N'dbo.NotificacionUsuario', N'fechaEliminacion') IS NULL
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="ACTUALIZAR_MATRIZ_VENCIMIENTO" o la base no tiene el esquema de Notificaciones v8 (aplicar antes GlucoLume_notificaciones_v8.sql): no se hizo nada.', 16, 1);
    SET NOEXEC ON;
END
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF COL_LENGTH(N'dbo.Matriz', N'avisoVencimientoNivel') IS NULL
    ALTER TABLE [dbo].[Matriz] ADD [avisoVencimientoNivel] SMALLINT NULL;
IF COL_LENGTH(N'dbo.Matriz', N'avisoVencimientoUltimo') IS NULL
    ALTER TABLE [dbo].[Matriz] ADD [avisoVencimientoUltimo] DATETIME2(3) NULL;
IF COL_LENGTH(N'dbo.Matriz', N'avisoVencimientoSilenciado') IS NULL
    ALTER TABLE [dbo].[Matriz] ADD [avisoVencimientoSilenciado] BIT NOT NULL CONSTRAINT [DF_Matriz_avisoVencimientoSilenciado] DEFAULT ((0));

IF OBJECT_ID(N'dbo.CK_NotificacionUsuario_evento', N'C') IS NOT NULL
    ALTER TABLE [dbo].[NotificacionUsuario] DROP CONSTRAINT [CK_NotificacionUsuario_evento];
ALTER TABLE [dbo].[NotificacionUsuario] WITH CHECK ADD CONSTRAINT [CK_NotificacionUsuario_evento] CHECK
    (([evento]=N'INICIO_SESION' OR [evento]=N'CAMBIO_CONTRASENA' OR [evento]=N'CAMBIO_MFA' OR [evento]=N'ACTIVIDAD_SOSPECHOSA' OR [evento]=N'INTENTO_INGRESO' OR [evento]=N'INVITACION_GRUPO' OR [evento]=N'AGREGADO_GRUPO' OR [evento]=N'NUEVA_ACCION_GRUPO' OR [evento]=N'MEDICION_GRUPO' OR [evento]=N'RECORDATORIO_MEDICION' OR [evento]=N'INSTITUCION_INVITACION' OR [evento]=N'INSTITUCION_OPERADOR_NUEVO' OR [evento]=N'INSTITUCION_OPERADOR_BAJA' OR [evento]=N'INSTITUCION_MODERADOR_NUEVO' OR [evento]=N'INSTITUCION_MODERADOR_BAJA' OR [evento]=N'INSTITUCION_PACIENTE_NUEVO' OR [evento]=N'INSTITUCION_PACIENTE_A_CARGO' OR [evento]=N'INSTITUCION_SOLICITUD_NUEVA' OR [evento]=N'INSTITUCION_SOLICITUD_ACEPTADA' OR [evento]=N'INSTITUCION_SOLICITUD_RECHAZADA' OR [evento]=N'RESULTADO_ENVIADO' OR [evento]=N'MEDICION_REALIZADA' OR [evento]=N'PLATAFORMA_TRANSFERENCIA_SOLICITADA' OR [evento]=N'PLATAFORMA_TRANSFERENCIA_RESPONDIDA' OR [evento]=N'PLATAFORMA_MODERADOR_ACTIVO' OR [evento]=N'PLATAFORMA_MATRIZ_VENCIMIENTO'));

IF OBJECT_ID(N'dbo.CK_PreferenciaNotificacion_evento', N'C') IS NOT NULL
    ALTER TABLE [dbo].[PreferenciaNotificacion] DROP CONSTRAINT [CK_PreferenciaNotificacion_evento];
ALTER TABLE [dbo].[PreferenciaNotificacion] WITH CHECK ADD CONSTRAINT [CK_PreferenciaNotificacion_evento] CHECK
    (([evento]=N'INICIO_SESION' OR [evento]=N'CAMBIO_CONTRASENA' OR [evento]=N'CAMBIO_MFA' OR [evento]=N'ACTIVIDAD_SOSPECHOSA' OR [evento]=N'INTENTO_INGRESO' OR [evento]=N'INVITACION_GRUPO' OR [evento]=N'AGREGADO_GRUPO' OR [evento]=N'NUEVA_ACCION_GRUPO' OR [evento]=N'MEDICION_GRUPO' OR [evento]=N'RECORDATORIO_MEDICION' OR [evento]=N'INSTITUCION_INVITACION' OR [evento]=N'INSTITUCION_OPERADOR_NUEVO' OR [evento]=N'INSTITUCION_OPERADOR_BAJA' OR [evento]=N'INSTITUCION_MODERADOR_NUEVO' OR [evento]=N'INSTITUCION_MODERADOR_BAJA' OR [evento]=N'INSTITUCION_PACIENTE_NUEVO' OR [evento]=N'INSTITUCION_PACIENTE_A_CARGO' OR [evento]=N'INSTITUCION_SOLICITUD_NUEVA' OR [evento]=N'INSTITUCION_SOLICITUD_ACEPTADA' OR [evento]=N'INSTITUCION_SOLICITUD_RECHAZADA' OR [evento]=N'RESULTADO_ENVIADO' OR [evento]=N'MEDICION_REALIZADA' OR [evento]=N'PLATAFORMA_TRANSFERENCIA_SOLICITADA' OR [evento]=N'PLATAFORMA_TRANSFERENCIA_RESPONDIDA' OR [evento]=N'PLATAFORMA_MODERADOR_ACTIVO' OR [evento]=N'PLATAFORMA_MATRIZ_VENCIMIENTO'));

-- El servicio «notifications» (rol de retención) reserva los avisos con UPDATE sobre Matriz. Solo esa columna de estado; nada más.
IF DATABASE_PRINCIPAL_ID(N'rol_glucolume_retencion') IS NOT NULL
    GRANT UPDATE ON OBJECT::dbo.Matriz TO rol_glucolume_retencion;

COMMIT TRANSACTION;
GO

-- VERIFICACION: las columnas y las dos restricciones deben existir.
SELECT name FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.Matriz') AND name LIKE N'avisoVencimiento%';
SELECT name FROM sys.check_constraints WHERE name IN (N'CK_NotificacionUsuario_evento', N'CK_PreferenciaNotificacion_evento');
GO

SET NOEXEC OFF;
GO
