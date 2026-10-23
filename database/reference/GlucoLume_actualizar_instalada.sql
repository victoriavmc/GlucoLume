-- GlucoLume - Actualización controlada de una base instalada al esquema v5 (DEC-02, GL-05)
--
-- No es una migración histórica: agrega a una base ya instalada solo lo que `python -m app.cli.schemaCheck` informó como faltante el
-- 19/10/2026 (las 6 restricciones CK_Medicion_* de glucosa del dispositivo) y los 31 índices que GlucoLume_DB_v5.sql no traía hasta el
-- 23/10/2026 (una base instalada con esa versión del archivo no los tiene). Idempotente: lo que ya existe no se toca. No borra ni modifica
-- filas: si alguna fila incumple una regla, el ALTER falla y la transacción se revierte entera.
--
-- Antes: respaldo restaurable (BACKUP ... WITH CHECKSUM + RESTORE VERIFYONLY), las consultas de conteo de
-- `schemaCheck --preparar-validacion` en 0 y el mismo script probado en una copia restaurada.
--   sqlcmd -S <servidor> -d <base> -I -i GlucoLume_actualizar_instalada.sql -v CONFIRMAR="ACTUALIZAR_GLUCOLUME_V5"   (-I: los índices filtrados exigen QUOTED_IDENTIFIER ON)
-- Reversión (no toca datos): ALTER TABLE dbo.Medicion DROP CONSTRAINT <nombre>; para cada una de las seis, y DROP INDEX <nombre> ON dbo.<tabla>; para los índices.

:on error exit

IF N'$(CONFIRMAR)' <> N'ACTUALIZAR_GLUCOLUME_V5' OR OBJECT_ID(N'dbo.Medicion') IS NULL
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="ACTUALIZAR_GLUCOLUME_V5" o la base no tiene dbo.Medicion: no se hizo nada.', 16, 1);
    SET NOEXEC ON;
END
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF OBJECT_ID(N'dbo.CK_Medicion_glucosaDispositivoOrigen', N'C') IS NULL
    ALTER TABLE [dbo].[Medicion] WITH CHECK ADD CONSTRAINT [CK_Medicion_glucosaDispositivoOrigen]
        CHECK (([glucosaDispositivo] IS NULL OR coalesce([origenGlucosa],N'')=N'DEMO' OR coalesce([origenGlucosa],N'')=N'EXPERIMENTAL'));
IF OBJECT_ID(N'dbo.CK_Medicion_glucosaDispositivoRango', N'C') IS NULL
    ALTER TABLE [dbo].[Medicion] WITH CHECK ADD CONSTRAINT [CK_Medicion_glucosaDispositivoRango]
        CHECK (([glucosaDispositivo] IS NULL OR [glucosaDispositivo]>=(0)));
IF OBJECT_ID(N'dbo.CK_Medicion_indiceOptico', N'C') IS NULL
    ALTER TABLE [dbo].[Medicion] WITH CHECK ADD CONSTRAINT [CK_Medicion_indiceOptico]
        CHECK (([indiceOptico] IS NULL OR [indiceOptico]>=(0)));
IF OBJECT_ID(N'dbo.CK_Medicion_lecturas', N'C') IS NULL
    ALTER TABLE [dbo].[Medicion] WITH CHECK ADD CONSTRAINT [CK_Medicion_lecturas]
        CHECK (([lecturasEstabilizadas] IS NULL OR [lecturasEstabilizadas]>(0)));
IF OBJECT_ID(N'dbo.CK_Medicion_origenConGlucosa', N'C') IS NULL
    ALTER TABLE [dbo].[Medicion] WITH CHECK ADD CONSTRAINT [CK_Medicion_origenConGlucosa]
        CHECK (([origenGlucosa] IS NULL OR [origenGlucosa]=N'SIN_CALIBRAR' OR [glucosaDispositivo] IS NOT NULL));
IF OBJECT_ID(N'dbo.CK_Medicion_unidadGlucosa', N'C') IS NULL
    ALTER TABLE [dbo].[Medicion] WITH CHECK ADD CONSTRAINT [CK_Medicion_unidadGlucosa]
        CHECK (([glucosaDispositivo] IS NULL OR coalesce([unidadGlucosa],N'')=N'mg/dL'));

-- Indices (31) que una base instalada con la version anterior de GlucoLume_DB_v5.sql no tiene: ese esquema exportado habia perdido todos los indices.
-- Cada uno se crea solo si no existe (los de las bases instaladas por los scripts antiguos ya estan). Los UX_* son unicos filtrados: si los datos
-- existentes violaran alguna regla (p. ej. dos administradores vigentes de una institucion), el CREATE falla y la transaccion se revierte entera.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Auditoria_fecha' AND object_id = OBJECT_ID(N'dbo.Auditoria'))
    CREATE NONCLUSTERED INDEX [IX_Auditoria_fecha] ON [dbo].[Auditoria] ([fechaHora]);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Auditoria_institucion_fecha' AND object_id = OBJECT_ID(N'dbo.Auditoria'))
    CREATE NONCLUSTERED INDEX [IX_Auditoria_institucion_fecha] ON [dbo].[Auditoria] ([idInstitucion], [fechaHora]);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Auditoria_modulo_fecha' AND object_id = OBJECT_ID(N'dbo.Auditoria'))
    CREATE NONCLUSTERED INDEX [IX_Auditoria_modulo_fecha] ON [dbo].[Auditoria] ([modulo], [fechaHora]);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_AuditoriaContexto_correlacion' AND object_id = OBJECT_ID(N'dbo.AuditoriaContexto'))
    CREATE NONCLUSTERED INDEX [IX_AuditoriaContexto_correlacion] ON [dbo].[AuditoriaContexto] ([idCorrelacion]);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_AuditoriaContexto_identificador' AND object_id = OBJECT_ID(N'dbo.AuditoriaContexto'))
    CREATE NONCLUSTERED INDEX [IX_AuditoriaContexto_identificador] ON [dbo].[AuditoriaContexto] ([identificadorHash]);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_AuditoriaContexto_ip' AND object_id = OBJECT_ID(N'dbo.AuditoriaContexto'))
    CREATE NONCLUSTERED INDEX [IX_AuditoriaContexto_ip] ON [dbo].[AuditoriaContexto] ([ipOrigen]);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_AuditoriaTecnica_fecha' AND object_id = OBJECT_ID(N'dbo.AuditoriaTecnicaMedicion'))
    CREATE NONCLUSTERED INDEX [IX_AuditoriaTecnica_fecha] ON [dbo].[AuditoriaTecnicaMedicion] ([fechaHora]);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ConsentimientoUsuario_usuario_tipo_fecha' AND object_id = OBJECT_ID(N'dbo.ConsentimientoUsuario'))
    CREATE NONCLUSTERED INDEX [IX_ConsentimientoUsuario_usuario_tipo_fecha] ON [dbo].[ConsentimientoUsuario] ([idUsuario], [tipo], [fechaHora]);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_GrupoUsuario_administrador' AND object_id = OBJECT_ID(N'dbo.GrupoUsuario'))
    CREATE UNIQUE NONCLUSTERED INDEX [UX_GrupoUsuario_administrador] ON [dbo].[GrupoUsuario] ([idGrupo]) WHERE ([rolGrupo]=N'PROPIETARIO' AND [estadoRelacion]=N'ACTIVO');
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_GrupoUsuario_grupoActivo' AND object_id = OBJECT_ID(N'dbo.GrupoUsuario'))
    CREATE UNIQUE NONCLUSTERED INDEX [UX_GrupoUsuario_grupoActivo] ON [dbo].[GrupoUsuario] ([idUsuario]) WHERE ([estadoRelacion]=N'ACTIVO');
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_GrupoUsuario_vinculoVigente' AND object_id = OBJECT_ID(N'dbo.GrupoUsuario'))
    CREATE UNIQUE NONCLUSTERED INDEX [UX_GrupoUsuario_vinculoVigente] ON [dbo].[GrupoUsuario] ([idGrupo], [idUsuario]) WHERE ([estadoRelacion]<>N'BAJA');
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_InstitucionUsuario_vinculoVigente' AND object_id = OBJECT_ID(N'dbo.InstitucionUsuario'))
    CREATE UNIQUE NONCLUSTERED INDEX [UX_InstitucionUsuario_vinculoVigente] ON [dbo].[InstitucionUsuario] ([idInstitucion], [idUsuarioInvitado]) WHERE ([estadoRelacion]<>N'BAJA');
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_Matriz_globalActiva' AND object_id = OBJECT_ID(N'dbo.Matriz'))
    CREATE UNIQUE NONCLUSTERED INDEX [UX_Matriz_globalActiva] ON [dbo].[Matriz] ([ambito]) WHERE ([ambito]=N'GLOBAL' AND [estado]=N'ACTIVA');
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_Matriz_institucionActiva' AND object_id = OBJECT_ID(N'dbo.Matriz'))
    CREATE UNIQUE NONCLUSTERED INDEX [UX_Matriz_institucionActiva] ON [dbo].[Matriz] ([idInstitucion]) WHERE ([ambito]=N'INSTITUCION' AND [estado]=N'ACTIVA');
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Medicion_vencimientoRetencion' AND object_id = OBJECT_ID(N'dbo.Medicion'))
    CREATE NONCLUSTERED INDEX [IX_Medicion_vencimientoRetencion] ON [dbo].[Medicion] ([fechaVencimientoRetencion]) WHERE ([fechaVencimientoRetencion] IS NOT NULL);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_PerfilMedicion_cohorte' AND object_id = OBJECT_ID(N'dbo.PerfilMedicion'))
    CREATE UNIQUE NONCLUSTERED INDEX [UX_PerfilMedicion_cohorte] ON [dbo].[PerfilMedicion] ([idInstitucion]) WHERE ([tipoPerfil]=N'COHORTE_ANONIMA');
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_PerfilMedicion_consumidor' AND object_id = OBJECT_ID(N'dbo.PerfilMedicion'))
    CREATE UNIQUE NONCLUSTERED INDEX [UX_PerfilMedicion_consumidor] ON [dbo].[PerfilMedicion] ([idUsuario]) WHERE ([tipoPerfil]=N'CONSUMIDOR_FINAL');
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_PerfilMedicion_dniInstitucion' AND object_id = OBJECT_ID(N'dbo.PerfilMedicion'))
    CREATE UNIQUE NONCLUSTERED INDEX [UX_PerfilMedicion_dniInstitucion] ON [dbo].[PerfilMedicion] ([idInstitucion], [dni]) WHERE ([idInstitucion] IS NOT NULL AND [dni] IS NOT NULL AND [tipoPerfil]=N'INSTITUCIONAL' AND [fechaExpiracionDatosPersonales] IS NULL AND [fechaDepuracionDatosPersonales] IS NULL);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ReasignacionPaciente_institucion' AND object_id = OBJECT_ID(N'dbo.ReasignacionPaciente'))
    CREATE NONCLUSTERED INDEX [IX_ReasignacionPaciente_institucion] ON [dbo].[ReasignacionPaciente] ([idInstitucion], [estado], [fechaCreacion]);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_ReasignacionPaciente_pendiente' AND object_id = OBJECT_ID(N'dbo.ReasignacionPaciente'))
    CREATE UNIQUE NONCLUSTERED INDEX [UX_ReasignacionPaciente_pendiente] ON [dbo].[ReasignacionPaciente] ([idPerfilMedicion]) WHERE ([estado]=N'PENDIENTE');
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_TransferenciaAdministracion_destino' AND object_id = OBJECT_ID(N'dbo.TransferenciaAdministracion'))
    CREATE NONCLUSTERED INDEX [IX_TransferenciaAdministracion_destino] ON [dbo].[TransferenciaAdministracion] ([idUsuarioDestino], [estado]);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_TransferenciaAdministracion_pendiente' AND object_id = OBJECT_ID(N'dbo.TransferenciaAdministracion'))
    CREATE UNIQUE NONCLUSTERED INDEX [UX_TransferenciaAdministracion_pendiente] ON [dbo].[TransferenciaAdministracion] ([estado]) WHERE ([estado]=N'PENDIENTE');
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_TransferenciaPerfil_destino' AND object_id = OBJECT_ID(N'dbo.TransferenciaPerfil'))
    CREATE NONCLUSTERED INDEX [IX_TransferenciaPerfil_destino] ON [dbo].[TransferenciaPerfil] ([idOperadorDestino], [estado]);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_TransferenciaPerfil_pendiente' AND object_id = OBJECT_ID(N'dbo.TransferenciaPerfil'))
    CREATE UNIQUE NONCLUSTERED INDEX [UX_TransferenciaPerfil_pendiente] ON [dbo].[TransferenciaPerfil] ([idPerfilMedicion]) WHERE ([estado]=N'PENDIENTE');
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_Usuario_administradorUnico' AND object_id = OBJECT_ID(N'dbo.Usuario'))
    CREATE UNIQUE NONCLUSTERED INDEX [UX_Usuario_administradorUnico] ON [dbo].[Usuario] ([tipoCuenta]) WHERE ([tipoCuenta]=N'ADMINISTRADOR_PLATAFORMA' AND [estado]<>N'ELIMINADO');
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Usuario_graciaVencimiento' AND object_id = OBJECT_ID(N'dbo.Usuario'))
    CREATE NONCLUSTERED INDEX [IX_Usuario_graciaVencimiento] ON [dbo].[Usuario] ([fechaVencimientoGracia]) WHERE ([fechaVencimientoGracia] IS NOT NULL);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_Usuario_correoElectronico' AND object_id = OBJECT_ID(N'dbo.Usuario'))
    CREATE UNIQUE NONCLUSTERED INDEX [UX_Usuario_correoElectronico] ON [dbo].[Usuario] ([correoElectronico]) WHERE ([correoElectronico] IS NOT NULL);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_Usuario_usuario' AND object_id = OBJECT_ID(N'dbo.Usuario'))
    CREATE UNIQUE NONCLUSTERED INDEX [UX_Usuario_usuario] ON [dbo].[Usuario] ([usuario]) WHERE ([usuario] IS NOT NULL);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Auditoria_accion_fecha' AND object_id = OBJECT_ID(N'dbo.Auditoria'))
    CREATE NONCLUSTERED INDEX [IX_Auditoria_accion_fecha] ON [dbo].[Auditoria] ([accion], [fechaHora]) INCLUDE ([idUsuario], [idInstitucion], [resultado]);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Auditoria_usuario_fecha' AND object_id = OBJECT_ID(N'dbo.Auditoria'))
    CREATE NONCLUSTERED INDEX [IX_Auditoria_usuario_fecha] ON [dbo].[Auditoria] ([idUsuario], [fechaHora]) WHERE ([idUsuario] IS NOT NULL);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Medicion_estado_fin' AND object_id = OBJECT_ID(N'dbo.Medicion'))
    CREATE NONCLUSTERED INDEX [IX_Medicion_estado_fin] ON [dbo].[Medicion] ([estadoMedicion], [fechaHoraFin]) INCLUDE ([idPerfilMedicion], [fechaHoraInicio]);

COMMIT TRANSACTION;
GO

-- VERIFICACION: las seis deben quedar habilitadas y confiables (is_disabled = 0, is_not_trusted = 0).
SELECT name, is_disabled, is_not_trusted
FROM sys.check_constraints
WHERE parent_object_id = OBJECT_ID(N'dbo.Medicion')
  AND name IN (N'CK_Medicion_glucosaDispositivoOrigen', N'CK_Medicion_glucosaDispositivoRango', N'CK_Medicion_indiceOptico',
               N'CK_Medicion_lecturas', N'CK_Medicion_origenConGlucosa', N'CK_Medicion_unidadGlucosa')
ORDER BY name;
GO

-- Los 31 indices deben existir (31 filas con IX_/UX_ en total si la base es nueva; esta cuenta solo debe ser >= 31).
SELECT COUNT(*) AS indicesIX_UX FROM sys.indexes WHERE name LIKE N'IX[_]%' OR name LIKE N'UX[_]%';
GO

SET NOEXEC OFF;
GO
