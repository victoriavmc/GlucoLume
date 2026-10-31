-- GlucoLume - Notificaciones v4: avisos de la gestión de la institución en la bandeja (según el rol de quien los recibe). Se aplica sobre una
-- base que ya tiene GlucoLume_notificaciones_v3.sql.
--
-- Qué hace (una transacción, sin borrar ni modificar ninguna fila):
--   CHECK de evento en NotificacionUsuario y PreferenciaNotificacion: admite los nueve avisos nuevos de la institución
--   (INSTITUCION_OPERADOR_NUEVO, INSTITUCION_OPERADOR_BAJA, INSTITUCION_MODERADOR_NUEVO, INSTITUCION_MODERADOR_BAJA,
--   INSTITUCION_PACIENTE_NUEVO, INSTITUCION_PACIENTE_A_CARGO, INSTITUCION_SOLICITUD_NUEVA, INSTITUCION_SOLICITUD_ACEPTADA e
--   INSTITUCION_SOLICITUD_RECHAZADA). Los avisos existentes no cambian.
--
-- Idempotente: vuelve a crear los dos CHECK con la lista completa. Requiere permiso de DDL (lo aplica quien administra la base).
-- Antes: respaldo restaurable (BACKUP ... WITH CHECKSUM) y, si hay dudas, probar el script en una copia restaurada.
--   sqlcmd -S <servidor> -d <base> -I -i GlucoLume_notificaciones_v4.sql -v CONFIRMAR="ACTUALIZAR_NOTIFICACIONES_V4"
-- Reversión: volver a crear los CHECK con los nueve avisos anteriores. Antes hay que borrar los avisos de institución ya guardados
-- (si no, la restricción no se puede crear).
-- Mientras el script no se aplique, la institución funciona igual (altas, bajas, pacientes y solicitudes): solo no se guarda el aviso de
-- bandeja, que queda registrado como error en el log del backend.

:on error exit

IF N'$(CONFIRMAR)' <> N'ACTUALIZAR_NOTIFICACIONES_V4'
   OR OBJECT_ID(N'dbo.NotificacionUsuario', N'U') IS NULL
   OR OBJECT_ID(N'dbo.PreferenciaNotificacion', N'U') IS NULL
   OR COL_LENGTH(N'dbo.NotificacionUsuario', N'fechaEliminacion') IS NULL
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="ACTUALIZAR_NOTIFICACIONES_V4" o la base no tiene el esquema de Notificaciones v3 (aplicar antes GlucoLume_notificaciones_v3.sql): no se hizo nada.', 16, 1);
    SET NOEXEC ON;
END
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF OBJECT_ID(N'dbo.CK_NotificacionUsuario_evento', N'C') IS NOT NULL
    ALTER TABLE [dbo].[NotificacionUsuario] DROP CONSTRAINT [CK_NotificacionUsuario_evento];
ALTER TABLE [dbo].[NotificacionUsuario] WITH CHECK ADD CONSTRAINT [CK_NotificacionUsuario_evento] CHECK
    (([evento]=N'INICIO_SESION' OR [evento]=N'CAMBIO_CONTRASENA' OR [evento]=N'CAMBIO_MFA' OR [evento]=N'ACTIVIDAD_SOSPECHOSA' OR [evento]=N'INVITACION_GRUPO' OR [evento]=N'AGREGADO_GRUPO' OR [evento]=N'NUEVA_ACCION_GRUPO' OR [evento]=N'MEDICION_GRUPO' OR [evento]=N'RECORDATORIO_MEDICION' OR [evento]=N'INSTITUCION_OPERADOR_NUEVO' OR [evento]=N'INSTITUCION_OPERADOR_BAJA' OR [evento]=N'INSTITUCION_MODERADOR_NUEVO' OR [evento]=N'INSTITUCION_MODERADOR_BAJA' OR [evento]=N'INSTITUCION_PACIENTE_NUEVO' OR [evento]=N'INSTITUCION_PACIENTE_A_CARGO' OR [evento]=N'INSTITUCION_SOLICITUD_NUEVA' OR [evento]=N'INSTITUCION_SOLICITUD_ACEPTADA' OR [evento]=N'INSTITUCION_SOLICITUD_RECHAZADA'));

IF OBJECT_ID(N'dbo.CK_PreferenciaNotificacion_evento', N'C') IS NOT NULL
    ALTER TABLE [dbo].[PreferenciaNotificacion] DROP CONSTRAINT [CK_PreferenciaNotificacion_evento];
ALTER TABLE [dbo].[PreferenciaNotificacion] WITH CHECK ADD CONSTRAINT [CK_PreferenciaNotificacion_evento] CHECK
    (([evento]=N'INICIO_SESION' OR [evento]=N'CAMBIO_CONTRASENA' OR [evento]=N'CAMBIO_MFA' OR [evento]=N'ACTIVIDAD_SOSPECHOSA' OR [evento]=N'INVITACION_GRUPO' OR [evento]=N'AGREGADO_GRUPO' OR [evento]=N'NUEVA_ACCION_GRUPO' OR [evento]=N'MEDICION_GRUPO' OR [evento]=N'RECORDATORIO_MEDICION' OR [evento]=N'INSTITUCION_OPERADOR_NUEVO' OR [evento]=N'INSTITUCION_OPERADOR_BAJA' OR [evento]=N'INSTITUCION_MODERADOR_NUEVO' OR [evento]=N'INSTITUCION_MODERADOR_BAJA' OR [evento]=N'INSTITUCION_PACIENTE_NUEVO' OR [evento]=N'INSTITUCION_PACIENTE_A_CARGO' OR [evento]=N'INSTITUCION_SOLICITUD_NUEVA' OR [evento]=N'INSTITUCION_SOLICITUD_ACEPTADA' OR [evento]=N'INSTITUCION_SOLICITUD_RECHAZADA'));

COMMIT TRANSACTION;
GO

-- VERIFICACION: las dos restricciones deben existir y admitir los dieciocho avisos.
SELECT name FROM sys.check_constraints WHERE name IN (N'CK_NotificacionUsuario_evento', N'CK_PreferenciaNotificacion_evento');
GO

SET NOEXEC OFF;
GO
