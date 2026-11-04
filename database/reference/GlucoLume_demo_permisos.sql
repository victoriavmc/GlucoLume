-- GlucoLume - Permisos de la LIMPIEZA de datos DEMO (app/demo/limpieza.py). Lo ejecuta el DBA UNA vez, sobre la base de GlucoLume.
--
-- Por qué existe: la cuenta de la API (rol_glucolume_api) no tiene DELETE sobre Institucion, InstitucionUsuario, Grupo, GrupoUsuario,
-- PerfilMedicion ni Dispositivo (GlucoLume_permisos.sql), y no debe tenerlo. La limpieza demo usa una cuenta propia, separada de la API,
-- con DELETE solo sobre las tablas que puede tocar una carga demo. NO concede INSERT ni UPDATE, y NO concede nada sobre la auditoria.
--
-- Los nombres de tabla de la lista deben coincidir con TABLAS_PERMITIDAS en backend/app/demo/limpieza.py.
--
-- Tras ejecutar este script, el DBA crea la cuenta de inicio de sesión y la asocia al rol (con contraseña propia, nunca en el repo):
--     CREATE LOGIN [glucolume_demo] WITH PASSWORD = N'<contraseña fuerte>', CHECK_POLICY = ON;
--     CREATE USER [glucolume_demo] FOR LOGIN [glucolume_demo];
--     ALTER ROLE rol_glucolume_demo_limpieza ADD MEMBER [glucolume_demo];
-- y la configura solo en el entorno de la demo: DB_DEMO_USER=glucolume_demo, DB_DEMO_PASSWORD=<la misma contraseña>.

IF DATABASE_PRINCIPAL_ID(N'rol_glucolume_demo_limpieza') IS NULL
    CREATE ROLE rol_glucolume_demo_limpieza AUTHORIZATION dbo;
GO

-- Lectura del esquema (la limpieza consulta las claves foráneas y los dependientes antes de borrar).
GRANT SELECT ON SCHEMA::dbo TO rol_glucolume_demo_limpieza;
GO

-- DELETE, una tabla por vez, solo para registros demo y sus dependientes directos.
GRANT DELETE ON OBJECT::dbo.Medicion TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.TransferenciaPerfil TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.MedicionReferenciaCapilar TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.MuestraSensor TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.EnvioResultado TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.AuditoriaTecnicaMedicion TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.NotificacionUsuario TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.SesionUsuario TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.TokenCuenta TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.ConsentimientoUsuario TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.CredencialLocal TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.CredencialLocalHistorial TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.FactorMfa TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.CodigoRecuperacionMfa TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.IdentidadExterna TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.PerfilMedicion TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.Dispositivo TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.GrupoUsuario TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.Grupo TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.InstitucionUsuario TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.Institucion TO rol_glucolume_demo_limpieza;
GRANT DELETE ON OBJECT::dbo.Usuario TO rol_glucolume_demo_limpieza;
GO

-- La auditoria no se borra desde la demo (GL-03): se niega explícitamente, aunque el esquema tenga otros permisos.
DENY DELETE, UPDATE ON OBJECT::dbo.Auditoria TO rol_glucolume_demo_limpieza;
DENY DELETE, UPDATE ON OBJECT::dbo.AuditoriaContexto TO rol_glucolume_demo_limpieza;
DENY DELETE, UPDATE ON OBJECT::dbo.AuditoriaRevision TO rol_glucolume_demo_limpieza;
GO
