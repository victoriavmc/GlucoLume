SET NOCOUNT ON;
DECLARE @ana uniqueidentifier = '11111111-1111-4111-8111-111111111111', @beto uniqueidentifier = '22222222-2222-4222-8222-222222222222';
INSERT INTO dbo.Usuario (idUsuario, nombre, apellido, correoElectronico, usuario) VALUES (@ana, N'Ana', N'Prueba', N'ana.sintetica@example.com', N'ana'), (@beto, N'Beto', N'Prueba', N'beto.sintetico@example.com', N'beto');
-- avisos «heredados»: fechaCreacion con el DEFAULT anterior (UTC); sin claveEvento (la columna todavía no existe)
INSERT INTO dbo.NotificacionUsuario (idUsuario, evento, titulo, mensaje, url, fechaCreacion) VALUES
 (@ana, N'INICIO_SESION', N'Nuevo inicio de sesión', N'Se inició sesión', N'/app/seguridad', '2026-10-29T19:00:00'),
 (@ana, N'RECORDATORIO_MEDICION', N'Es hora de medirte', N'Conectá', N'/app/mediciones', '2026-10-29T19:30:00'),
 (@beto, N'INICIO_SESION', N'Nuevo inicio de sesión', N'Se inició sesión', N'/app/seguridad', '2026-10-29T20:00:00');
INSERT INTO dbo.PreferenciaNotificacion (idUsuario, evento, enPagina, porCorreo, fechaActualizacion) VALUES (@ana, N'NUEVA_ACCION_GRUPO', 1, 0, '2026-10-29T10:00:00');
INSERT INTO dbo.RecordatorioMedicion (idUsuario, modo, horarios, ultimoAviso, fechaActualizacion) VALUES (@ana, N'HORARIOS', N'16:30', '2026-10-29T16:30:00', '2026-10-29T16:26:00');
