-- GlucoLume - Revisión de eventos de auditoría: tabla AuditoriaRevision (marca «analizado» de la administración).
-- Se aplica sobre una base que ya tiene la tabla Auditoria (esquema v5). No modifica ni borra ninguna fila de Auditoria.
--
-- Qué hace (una transacción):
--   Crea AuditoriaRevision si no existe: un registro por evento revisado (idAuditoria, quién lo revisó y cuándo). Los eventos sin marca
--   no tienen fila. Mientras no se aplique, la auditoría funciona igual y la marca «analizado» no aparece.
--
-- Idempotente. Requiere permiso de DDL (lo aplica quien administra la base).
--   sqlcmd -S <servidor> -d <base> -I -i GlucoLume_revision_auditoria.sql -v CONFIRMAR="ACTUALIZAR_REVISION_AUDITORIA"
-- Reversión: DROP TABLE dbo.AuditoriaRevision (solo borra las marcas; los eventos no cambian).
-- Además concede DELETE a los roles de la API y de retención (como GlucoLume_permisos.sql).

:on error exit

IF N'$(CONFIRMAR)' <> N'ACTUALIZAR_REVISION_AUDITORIA'
   OR OBJECT_ID(N'dbo.Auditoria', N'U') IS NULL
   OR OBJECT_ID(N'dbo.Usuario', N'U') IS NULL
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="ACTUALIZAR_REVISION_AUDITORIA" o la base no tiene la tabla Auditoria: no se hizo nada.', 16, 1);
    SET NOEXEC ON;
END
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF OBJECT_ID(N'dbo.AuditoriaRevision', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.AuditoriaRevision (
        idAuditoria      UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_AuditoriaRevision PRIMARY KEY,
        idUsuarioRevisor UNIQUEIDENTIFIER NOT NULL,
        fechaRevision    DATETIME2(3)     NOT NULL CONSTRAINT DF_AuditoriaRevision_fechaRevision DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_AuditoriaRevision_Auditoria FOREIGN KEY (idAuditoria) REFERENCES dbo.Auditoria (idAuditoria) ON DELETE CASCADE,
        CONSTRAINT FK_AuditoriaRevision_Usuario FOREIGN KEY (idUsuarioRevisor) REFERENCES dbo.Usuario (idUsuario)
    );
END;

-- Permiso de la API para quitar una marca (desmarcar). Se concede tabla por tabla, como en GlucoLume_permisos.sql; si el rol
-- todavía no existe, se aplica GlucoLume_permisos.sql y después se vuelve a ejecutar este script.
IF DATABASE_PRINCIPAL_ID(N'rol_glucolume_api') IS NOT NULL
    GRANT DELETE ON OBJECT::dbo.AuditoriaRevision TO rol_glucolume_api;
IF DATABASE_PRINCIPAL_ID(N'rol_glucolume_retencion') IS NOT NULL
    GRANT DELETE ON OBJECT::dbo.AuditoriaRevision TO rol_glucolume_retencion;

COMMIT TRANSACTION;
GO
