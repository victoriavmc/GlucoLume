SET NOCOUNT ON;
DECLARE @ana uniqueidentifier = '11111111-1111-4111-8111-111111111111', @ahora datetime2 = SYSDATETIME();
INSERT INTO dbo.NotificacionUsuario (idUsuario, evento, titulo, mensaje, claveEvento, fechaCreacion, fechaLectura) VALUES
 (@ana, N'CAMBIO_MFA', N'leido-viejo-1', N'm', N'purga:1', DATEADD(day,-100,@ahora), DATEADD(day,-99,@ahora)),
 (@ana, N'CAMBIO_MFA', N'leido-viejo-2', N'm', N'purga:2', DATEADD(day,-45,@ahora), DATEADD(day,-44,@ahora)),
 (@ana, N'CAMBIO_MFA', N'leido-reciente', N'm', N'purga:3', DATEADD(day,-3,@ahora), DATEADD(day,-2,@ahora)),
 (@ana, N'CAMBIO_MFA', N'sin-leer-medio', N'm', N'purga:4', DATEADD(day,-200,@ahora), NULL),
 (@ana, N'CAMBIO_MFA', N'sin-leer-muy-viejo', N'm', N'purga:5', DATEADD(day,-400,@ahora), NULL);
