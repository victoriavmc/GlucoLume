-- GlucoLume - Cuenta de MINIMO PRIVILEGIO para la anulacion tecnica de IP y agente vencidos (app/jobs/technicalRetention.py)
--
-- No forma parte del esquema (GlucoLume_DB_v5.sql) ni cambia tablas: solo crea un rol y concede permisos a una cuenta que ya existe.
-- Idempotente: repetirlo no cambia nada. Probarlo primero en una copia restaurada; antes de aplicarlo en la base real, respaldo verificado.
--
-- Lo que puede hacer la cuenta (RET_LOGIN), y nada mas:
--   - leer Auditoria (fecha, accion, tipo, resultado, cuenta) y Usuario.fechaEliminacion, para decidir que contexto vencio;
--   - leer AuditoriaContexto (identificador, IP, agente);
--   - ANULAR ipOrigen y agenteUsuario en AuditoriaContexto (UPDATE de esas dos columnas, nada mas);
--   - agregar eventos (INSERT) para registrar el resultado del mantenimiento.
-- Lo que NO puede: borrar nada (ni eventos, ni contextos, ni cuentas), modificar Auditoria, modificar otras columnas de AuditoriaContexto,
-- modificar Usuario ni cambiar el esquema. Tampoco es db_owner ni tiene los roles fijos de lectura/escritura.
--
-- La cuenta de la API (DB_USER) y la de los jobs (DB_JOBS_USER) NO reciben nada de este script. La contrasena nunca va en este archivo: la crea el
-- administrador de la instancia con CREATE LOGIN (ver docs/DESPLIEGUE.md) y la guarda en el .env del servidor como DB_RETENCION_USER / DB_RETENCION_PASSWORD.
--
-- Uso (sqlcmd con -I: los indices filtrados exigen QUOTED_IDENTIFIER ON):
--   sqlcmd -S <servidor> -E -C -I -d <base> -i GlucoLume_retencion_ip_tecnica.sql ^
--          -v RET_LOGIN="glucolume_ip_tecnica" CONFIRMAR="APLICAR_RETENCION_IP_TECNICA"
-- Sin CONFIRMAR exacto no se ejecuta nada. Reversion: quitar el rol y el usuario (no toca datos).

:on error exit

IF N'$(CONFIRMAR)' <> N'APLICAR_RETENCION_IP_TECNICA'
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="APLICAR_RETENCION_IP_TECNICA": no se aplico ningun permiso.', 16, 1);
    SET NOEXEC ON;
END
GO

IF SUSER_ID(N'$(RET_LOGIN)') IS NULL
BEGIN
    RAISERROR(N'RET_LOGIN debe existir como login de la instancia antes de aplicar este script.', 16, 1);
    SET NOEXEC ON;
END
GO

-- Una cuenta de sysadmin o duena de la base no queda alcanzada por ningun DENY.
IF IS_SRVROLEMEMBER(N'sysadmin', N'$(RET_LOGIN)') = 1
   OR EXISTS (SELECT 1 FROM sys.databases WHERE name = DB_NAME() AND SUSER_SNAME(owner_sid) = N'$(RET_LOGIN)')
BEGIN
    RAISERROR(N'La cuenta de mantenimiento es sysadmin o duena de la base: quitar ese privilegio antes de seguir.', 16, 1);
    SET NOEXEC ON;
END
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF DATABASE_PRINCIPAL_ID(N'$(RET_LOGIN)') IS NULL
    EXEC (N'CREATE USER ' + N'[$(RET_LOGIN)]' + N' FOR LOGIN [$(RET_LOGIN)] WITH DEFAULT_SCHEMA = dbo;');

IF DATABASE_PRINCIPAL_ID(N'rol_glucolume_ip_tecnica') IS NULL
    CREATE ROLE rol_glucolume_ip_tecnica AUTHORIZATION dbo;

IF NOT EXISTS (SELECT 1 FROM sys.database_role_members rm
               JOIN sys.database_principals r ON r.principal_id = rm.role_principal_id AND r.name = N'rol_glucolume_ip_tecnica'
               JOIN sys.database_principals m ON m.principal_id = rm.member_principal_id AND m.name = N'$(RET_LOGIN)')
    EXEC (N'ALTER ROLE rol_glucolume_ip_tecnica ADD MEMBER [$(RET_LOGIN)];');

-- Lectura: solo las columnas que decide la regla de vencimiento.
GRANT SELECT ON OBJECT::dbo.Auditoria (idAuditoria, idUsuario, tipoEvento, accion, resultado, fechaHora) TO rol_glucolume_ip_tecnica;
GRANT SELECT ON OBJECT::dbo.Usuario (idUsuario, fechaEliminacion) TO rol_glucolume_ip_tecnica;
GRANT SELECT ON OBJECT::dbo.AuditoriaContexto (idAuditoria, ipOrigen, agenteUsuario) TO rol_glucolume_ip_tecnica;
-- Solo para decidir la extensión de la baja: la última decisión sobre la política y su versión (nunca el texto ni otros datos del consentimiento).
GRANT SELECT ON OBJECT::dbo.ConsentimientoUsuario (idUsuario, tipo, version, estado, fechaHora) TO rol_glucolume_ip_tecnica;

-- Unica modificacion permitida: anular IP y agente.
GRANT UPDATE ON OBJECT::dbo.AuditoriaContexto (ipOrigen, agenteUsuario) TO rol_glucolume_ip_tecnica;

-- Solo agrega el evento que registra el resultado del mantenimiento.
GRANT INSERT ON OBJECT::dbo.Auditoria TO rol_glucolume_ip_tecnica;
GRANT INSERT ON OBJECT::dbo.AuditoriaContexto TO rol_glucolume_ip_tecnica;

-- DENY prevalece sobre cualquier GRANT o membresia: la cuenta no puede borrar ni modificar la evidencia.
DENY UPDATE, DELETE ON OBJECT::dbo.Auditoria TO rol_glucolume_ip_tecnica;
DENY DELETE ON OBJECT::dbo.AuditoriaContexto TO rol_glucolume_ip_tecnica;
DENY UPDATE ON OBJECT::dbo.AuditoriaContexto (idCorrelacion, motivo, identificadorHash) TO rol_glucolume_ip_tecnica;
DENY UPDATE, DELETE ON OBJECT::dbo.Usuario TO rol_glucolume_ip_tecnica;

COMMIT TRANSACTION;
GO

-- Verificacion: lo que la cuenta puede hacer sobre la auditoria (debe salir solo SELECT, INSERT y UPDATE de las dos columnas de IP).
EXECUTE AS USER = N'$(RET_LOGIN)';
SELECT N'Auditoria' AS objeto, permission_name FROM fn_my_permissions(N'dbo.Auditoria', N'OBJECT') WHERE subentity_name = N'';
SELECT N'AuditoriaContexto' AS objeto, permission_name, subentity_name FROM fn_my_permissions(N'dbo.AuditoriaContexto', N'OBJECT');
REVERT;
GO
