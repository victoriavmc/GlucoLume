-- Borra SOLO los datos de prueba de individuo1..6@example.com (usuarios, perfiles, mediciones, grupo, dispositivos y lo que la app
-- registró para esas cuentas). No toca la matriz global ni ningun otro usuario.
USE [GlucoLume];
SET NOCOUNT ON;
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET XACT_ABORT ON;
BEGIN TRANSACTION;

DECLARE @u TABLE (id UNIQUEIDENTIFIER PRIMARY KEY);
INSERT INTO @u SELECT idUsuario FROM dbo.Usuario WHERE correoElectronico LIKE N'individuo_@example.com';

DECLARE @p TABLE (id UNIQUEIDENTIFIER PRIMARY KEY);
INSERT INTO @p SELECT idPerfilMedicion FROM dbo.PerfilMedicion WHERE idUsuario IN (SELECT id FROM @u);

DECLARE @m TABLE (id UNIQUEIDENTIFIER PRIMARY KEY);
INSERT INTO @m SELECT idMedicion FROM dbo.Medicion WHERE idPerfilMedicion IN (SELECT id FROM @p) OR observacion = N'Dato de prueba ficticio';

DECLARE @a TABLE (id UNIQUEIDENTIFIER PRIMARY KEY);
INSERT INTO @a SELECT idAuditoria FROM dbo.Auditoria WHERE idUsuario IN (SELECT id FROM @u);

DECLARE @f TABLE (id UNIQUEIDENTIFIER PRIMARY KEY);
INSERT INTO @f SELECT idFactorMfa FROM dbo.FactorMfa WHERE idUsuario IN (SELECT id FROM @u);

DECLARE @c TABLE (id UNIQUEIDENTIFIER PRIMARY KEY);
INSERT INTO @c SELECT idCredencialLocal FROM dbo.CredencialLocal WHERE idUsuario IN (SELECT id FROM @u);

-- hojas primero
DELETE FROM dbo.EnvioResultado WHERE idMedicion IN (SELECT id FROM @m);
DELETE FROM dbo.MedicionReferenciaCapilar WHERE idMedicion IN (SELECT id FROM @m);
DELETE FROM dbo.MuestraSensor WHERE idMedicion IN (SELECT id FROM @m);
DELETE FROM dbo.Medicion WHERE idMedicion IN (SELECT id FROM @m);
DELETE FROM dbo.TransferenciaPerfil WHERE idPerfilMedicion IN (SELECT id FROM @p);
DELETE FROM dbo.ReasignacionPaciente WHERE idPerfilMedicion IN (SELECT id FROM @p);
DELETE FROM dbo.PerfilMedicion WHERE idPerfilMedicion IN (SELECT id FROM @p);

DELETE FROM dbo.AuditoriaRevision WHERE idAuditoria IN (SELECT id FROM @a) OR idUsuarioRevisor IN (SELECT id FROM @u);
DELETE FROM dbo.AuditoriaContexto WHERE idAuditoria IN (SELECT id FROM @a);
DELETE FROM dbo.Auditoria WHERE idAuditoria IN (SELECT id FROM @a);

DELETE FROM dbo.CodigoRecuperacionMfa WHERE idFactorMfa IN (SELECT id FROM @f);
DELETE FROM dbo.FactorMfa WHERE idFactorMfa IN (SELECT id FROM @f);
DELETE FROM dbo.CredencialLocalHistorial WHERE idCredencialLocal IN (SELECT id FROM @c);
DELETE FROM dbo.CredencialLocal WHERE idCredencialLocal IN (SELECT id FROM @c);

DELETE FROM dbo.NotificacionUsuario WHERE idUsuario IN (SELECT id FROM @u);
DELETE FROM dbo.PreferenciaNotificacion WHERE idUsuario IN (SELECT id FROM @u);
DELETE FROM dbo.ConfiguracionNotificacion WHERE idUsuario IN (SELECT id FROM @u);
DELETE FROM dbo.RecordatorioMedicion WHERE idUsuario IN (SELECT id FROM @u);
DELETE FROM dbo.AccesoConocido WHERE idUsuario IN (SELECT id FROM @u);
DELETE FROM dbo.SesionUsuario WHERE idUsuario IN (SELECT id FROM @u);
DELETE FROM dbo.TokenCuenta WHERE idUsuario IN (SELECT id FROM @u);
DELETE FROM dbo.IdentidadExterna WHERE idUsuario IN (SELECT id FROM @u);
DELETE FROM dbo.ConsentimientoUsuario WHERE idUsuario IN (SELECT id FROM @u);
DELETE FROM dbo.SuscripcionUsuario WHERE idUsuario IN (SELECT id FROM @u);
DELETE FROM dbo.PeriodoPrueba WHERE idUsuario IN (SELECT id FROM @u);
DELETE FROM dbo.GrupoUsuario WHERE idUsuario IN (SELECT id FROM @u);
DELETE FROM dbo.Grupo WHERE nombre = N'Grupo familiar de prueba' AND idGrupo NOT IN (SELECT idGrupo FROM dbo.GrupoUsuario);
DELETE FROM dbo.Dispositivo WHERE codigoDispositivo LIKE N'PRUEBA-IND-%';

DELETE FROM dbo.Usuario WHERE idUsuario IN (SELECT id FROM @u);

COMMIT TRANSACTION;
SELECT 'usuarios de prueba restantes' AS control, COUNT(*) AS filas FROM dbo.Usuario WHERE correoElectronico LIKE N'individuo_@example.com';
