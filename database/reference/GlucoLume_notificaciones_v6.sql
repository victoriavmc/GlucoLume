-- GlucoLume - Notificaciones v6: aviso de envío del resultado por correo (RESULTADO_ENVIADO), categoría MEDICION.
-- Se aplica sobre una base que ya tiene GlucoLume_notificaciones_v5.sql.
--
-- Qué hace (una transacción, sin borrar ni modificar ninguna fila):
--   CHECK de evento en NotificacionUsuario y PreferenciaNotificacion: admite el aviso nuevo. Los avisos existentes no cambian.
--   La categoría MEDICION no tiene CHECK en la base: se deriva del evento en el backend.
--
-- Idempotente: vuelve a crear los dos CHECK con la lista completa. Requiere permiso de DDL (lo aplica quien administra la base).
-- Antes: respaldo restaurable (BACKUP ... WITH CHECKSUM) y, si hay dudas, probar el script en una copia restaurada.
--   sqlcmd -S <servidor> -d <base> -I -i GlucoLume_notificaciones_v6.sql -v CONFIRMAR="ACTUALIZAR_NOTIFICACIONES_V6"
-- Reversión: volver a crear los CHECK sin RESULTADO_ENVIADO. Antes hay que borrar esos avisos ya guardados (si no, la
-- restricción no se puede crear).
-- Mientras el script no se aplique, el aviso de bandeja del envío del resultado no se guarda: queda registrado como error en el log
-- del backend, y el envío por correo sigue igual.

:on error exit

IF N'$(CONFIRMAR)' <> N'ACTUALIZAR_NOTIFICACIONES_V6'
   OR OBJECT_ID(N'dbo.NotificacionUsuario', N'U') IS NULL
   OR OBJECT_ID(N'dbo.PreferenciaNotificacion', N'U') IS NULL
   OR COL_LENGTH(N'dbo.NotificacionUsuario', N'fechaEliminacion') IS NULL
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="ACTUALIZAR_NOTIFICACIONES_V6" o la base no tiene el esquema de Notificaciones v5 (aplicar antes GlucoLume_notificaciones_v5.sql): no se hizo nada.', 16, 1);
    SET NOEXEC ON;
END
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF OBJECT_ID(N'dbo.CK_NotificacionUsuario_evento', N'C') IS NOT NULL
    ALTER TABLE [dbo].[NotificacionUsuario] DROP CONSTRAINT [CK_NotificacionUsuario_evento];
ALTER TABLE [dbo].[NotificacionUsuario] WITH CHECK ADD CONSTRAINT [CK_NotificacionUsuario_evento] CHECK
    (([evento]=N'INICIO_SESION' OR [evento]=N'CAMBIO_CONTRASENA' OR [evento]=N'CAMBIO_MFA' OR [evento]=N'ACTIVIDAD_SOSPECHOSA' OR [evento]=N'INTENTO_INGRESO' OR [evento]=N'INVITACION_GRUPO' OR [evento]=N'AGREGADO_GRUPO' OR [evento]=N'NUEVA_ACCION_GRUPO' OR [evento]=N'MEDICION_GRUPO' OR [evento]=N'RECORDATORIO_MEDICION' OR [evento]=N'INSTITUCION_INVITACION' OR [evento]=N'INSTITUCION_OPERADOR_NUEVO' OR [evento]=N'INSTITUCION_OPERADOR_BAJA' OR [evento]=N'INSTITUCION_MODERADOR_NUEVO' OR [evento]=N'INSTITUCION_MODERADOR_BAJA' OR [evento]=N'INSTITUCION_PACIENTE_NUEVO' OR [evento]=N'INSTITUCION_PACIENTE_A_CARGO' OR [evento]=N'INSTITUCION_SOLICITUD_NUEVA' OR [evento]=N'INSTITUCION_SOLICITUD_ACEPTADA' OR [evento]=N'INSTITUCION_SOLICITUD_RECHAZADA' OR [evento]=N'RESULTADO_ENVIADO'));

IF OBJECT_ID(N'dbo.CK_PreferenciaNotificacion_evento', N'C') IS NOT NULL
    ALTER TABLE [dbo].[PreferenciaNotificacion] DROP CONSTRAINT [CK_PreferenciaNotificacion_evento];
ALTER TABLE [dbo].[PreferenciaNotificacion] WITH CHECK ADD CONSTRAINT [CK_PreferenciaNotificacion_evento] CHECK
    (([evento]=N'INICIO_SESION' OR [evento]=N'CAMBIO_CONTRASENA' OR [evento]=N'CAMBIO_MFA' OR [evento]=N'ACTIVIDAD_SOSPECHOSA' OR [evento]=N'INTENTO_INGRESO' OR [evento]=N'INVITACION_GRUPO' OR [evento]=N'AGREGADO_GRUPO' OR [evento]=N'NUEVA_ACCION_GRUPO' OR [evento]=N'MEDICION_GRUPO' OR [evento]=N'RECORDATORIO_MEDICION' OR [evento]=N'INSTITUCION_INVITACION' OR [evento]=N'INSTITUCION_OPERADOR_NUEVO' OR [evento]=N'INSTITUCION_OPERADOR_BAJA' OR [evento]=N'INSTITUCION_MODERADOR_NUEVO' OR [evento]=N'INSTITUCION_MODERADOR_BAJA' OR [evento]=N'INSTITUCION_PACIENTE_NUEVO' OR [evento]=N'INSTITUCION_PACIENTE_A_CARGO' OR [evento]=N'INSTITUCION_SOLICITUD_NUEVA' OR [evento]=N'INSTITUCION_SOLICITUD_ACEPTADA' OR [evento]=N'INSTITUCION_SOLICITUD_RECHAZADA' OR [evento]=N'RESULTADO_ENVIADO'));

COMMIT TRANSACTION;
GO

-- VERIFICACION: las dos restricciones deben existir y admitir los veintiún avisos.
SELECT name FROM sys.check_constraints WHERE name IN (N'CK_NotificacionUsuario_evento', N'CK_PreferenciaNotificacion_evento');
GO

SET NOEXEC OFF;
GO
