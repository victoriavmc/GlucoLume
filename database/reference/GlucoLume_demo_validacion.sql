-- GlucoLume - Consultas de VALIDACIÓN de los datos de demostración (solo lectura). Ejecutar en SSMS sobre la base de GlucoLume,
-- después de `python -m app.cli.demoSeed --aplicar` (o en una base de prueba). Ninguna consulta modifica datos.
-- Cada bloque indica el resultado esperado con el catálogo actual (backend/app/demo/catalog.py) y la fecha de ancla de la carga.

-- 1. Cuentas demo por tipo. Esperado: CONSUMIDOR_FINAL = 7 · USUARIO_INSTITUCIONAL = 14.
SELECT tipoCuenta, COUNT(*) AS cuentas
FROM dbo.Usuario
WHERE correoElectronico LIKE N'demo.%@example.com'
GROUP BY tipoCuenta;

-- 2. Estado y verificación de correo de las cuentas demo. Esperado: todas ACTIVO (ninguna PENDIENTE) y sin factor MFA habilitado.
SELECT u.estado, COUNT(*) AS cuentas,
       SUM(CASE WHEN f.idFactorMfa IS NOT NULL AND f.habilitado = 1 THEN 1 ELSE 0 END) AS conMfaHabilitado
FROM dbo.Usuario u
LEFT JOIN dbo.FactorMfa f ON f.idUsuario = u.idUsuario
WHERE u.correoElectronico LIKE N'demo.%@example.com'
GROUP BY u.estado;

-- 3. Credenciales locales. Esperado: 21 (una por cuenta demo), todas con hash y sin bloqueo.
SELECT COUNT(*) AS credenciales,
       SUM(CASE WHEN c.bloqueadoHasta IS NOT NULL THEN 1 ELSE 0 END) AS bloqueadas
FROM dbo.CredencialLocal c
JOIN dbo.Usuario u ON u.idUsuario = c.idUsuario
WHERE u.correoElectronico LIKE N'demo.%@example.com';

-- 4. Administradores de plataforma: deben ser EXACTAMENTE los que existían antes de la carga (la demo no crea ni modifica ninguno).
SELECT idUsuario, correoElectronico, estado, fechaCreacion
FROM dbo.Usuario
WHERE tipoCuenta = N'ADMINISTRADOR_PLATAFORMA' OR tipoCuenta = N'MODERADOR_PLATAFORMA';

-- 5. Instituciones demo. Esperado: 3 (A consultorio, B clínica, C consultorio), todas ACTIVA, CUIT con 11 dígitos.
SELECT nombre, tipoInstitucion, estado, identificadorLegal, LEN(identificadorLegal) AS largoCuit
FROM dbo.Institucion
WHERE nombre LIKE N'Institución Demo %'
ORDER BY nombre;

-- 6. Propietarios: cuántas instituciones administra cada cuenta propietaria. Esperado: propietario-a = 2 (A y C), propietario-b = 1 (B).
SELECT u.correoElectronico, COUNT(*) AS institucionesPropias
FROM dbo.InstitucionUsuario iu
JOIN dbo.Usuario u ON u.idUsuario = iu.idUsuarioInvitado
WHERE iu.rolInstitucion = N'PROPIETARIO' AND iu.estadoRelacion = N'ACTIVO'
  AND u.correoElectronico LIKE N'demo.%@example.com'
GROUP BY u.correoElectronico
ORDER BY u.correoElectronico;

-- 7. Personal por institución y rol. Esperado por cada institución A y B: 1 propietario, 2 moderadores, 4 operadores.
SELECT i.nombre, iu.rolInstitucion, COUNT(*) AS personas
FROM dbo.InstitucionUsuario iu
JOIN dbo.Institucion i ON i.idInstitucion = iu.idInstitucion
WHERE i.nombre LIKE N'Institución Demo %' AND iu.estadoRelacion = N'ACTIVO'
GROUP BY i.nombre, iu.rolInstitucion
ORDER BY i.nombre, iu.rolInstitucion;

-- 8. Pacientes por operador responsable (el modelo asigna UN responsable por paciente). Esperado: 3 a 5 por operador, 32 en total.
SELECT i.nombre AS institucion, u.correoElectronico AS operador, COUNT(*) AS pacientes
FROM dbo.PerfilMedicion p
JOIN dbo.InstitucionUsuario iu ON iu.idInstitucionUsuario = p.idInstitucionUsuarioResponsable
JOIN dbo.Usuario u ON u.idUsuario = iu.idUsuarioInvitado
JOIN dbo.Institucion i ON i.idInstitucion = iu.idInstitucion
WHERE p.tipoPerfil = N'INSTITUCIONAL' AND p.identificadorPseudonimo LIKE N'DEMO-PAC-%'
GROUP BY i.nombre, u.correoElectronico
ORDER BY i.nombre, u.correoElectronico;

-- 9. Documentos de pacientes demo únicos por institución (índice UX_PerfilMedicion_dniInstitucion). Esperado: sin filas.
SELECT idInstitucion, dni, COUNT(*) AS repeticiones
FROM dbo.PerfilMedicion
WHERE dni LIKE N'DEMO%' AND fechaExpiracionDatosPersonales IS NULL AND fechaDepuracionDatosPersonales IS NULL
GROUP BY idInstitucion, dni
HAVING COUNT(*) > 1;

-- 10. Grupo familiar: un administrador activo y sus cinco integrantes con permisos distintos. Esperado: 1 PROPIETARIO + 5 MIEMBRO.
SELECT gu.rolGrupo, gu.compartePerfil, gu.comparteUltimaMedicion, gu.comparteHistorial, gu.notificaMedicion, COUNT(*) AS integrantes
FROM dbo.GrupoUsuario gu
JOIN dbo.Grupo g ON g.idGrupo = gu.idGrupo
WHERE g.nombre = N'Grupo familiar DEMO' AND gu.estadoRelacion = N'ACTIVO'
GROUP BY gu.rolGrupo, gu.compartePerfil, gu.comparteUltimaMedicion, gu.comparteHistorial, gu.notificaMedicion
ORDER BY gu.rolGrupo, gu.compartePerfil DESC, gu.comparteUltimaMedicion DESC, gu.comparteHistorial DESC, gu.notificaMedicion DESC;

-- 11. Mediciones demo por perfil: todas identificadas como sintéticas, con origen DEMO cuando informan glucosa.
--     Esperado: 0 filas sin la marca DEMO en observacion; ninguna con glucosaEstimada (la demo no estima glucosa).
SELECT
    SUM(CASE WHEN m.observacion LIKE N'DEMO - %' THEN 0 ELSE 1 END) AS sinMarcaDemo,
    SUM(CASE WHEN m.glucosaEstimada IS NOT NULL THEN 1 ELSE 0 END) AS conGlucosaEstimada,
    SUM(CASE WHEN m.origenGlucosa = N'DEMO' THEN 1 ELSE 0 END) AS origenDemo,
    COUNT(*) AS mediciones
FROM dbo.Medicion m
JOIN dbo.PerfilMedicion p ON p.idPerfilMedicion = m.idPerfilMedicion
WHERE p.identificadorPseudonimo LIKE N'DEMO-PAC-%' OR p.idUsuario IN (SELECT idUsuario FROM dbo.Usuario
                                                                    WHERE correoElectronico LIKE N'demo.%@example.com');

-- 12. Mediciones por modo, estado y condición de alimentación (variedad). Esperado: los cuatro modos/estados aparecen.
SELECT modoMedicion, estadoMedicion, condicionComida, COUNT(*) AS mediciones
FROM dbo.Medicion
WHERE observacion LIKE N'DEMO - %'
GROUP BY modoMedicion, estadoMedicion, condicionComida
ORDER BY modoMedicion, estadoMedicion, condicionComida;

-- 13. Días distintos con mediciones por perfil individual (para gráficos y filtros de historial).
SELECT u.correoElectronico, COUNT(DISTINCT CONVERT(date, m.fechaHoraInicio)) AS diasConMediciones, COUNT(*) AS mediciones
FROM dbo.Medicion m
JOIN dbo.PerfilMedicion p ON p.idPerfilMedicion = m.idPerfilMedicion
JOIN dbo.Usuario u ON u.idUsuario = p.idUsuario
WHERE u.correoElectronico LIKE N'demo.%@example.com'
GROUP BY u.correoElectronico
ORDER BY u.correoElectronico;

-- 14. Dispositivos demo. Esperado: 6, todos DEMO-DISP-* y OPERATIVO. Ninguno de los equipos físicos reales.
SELECT codigoDispositivo, estado, idInstitucionAsignada, modeloSensor
FROM dbo.Dispositivo
WHERE codigoDispositivo LIKE N'DEMO-DISP-%'
ORDER BY codigoDispositivo;

-- 15. Consentimientos demo (política y datos experimentales) de las cuentas individuales. Esperado: 14 (2 por cuenta).
SELECT c.tipo, c.estado, COUNT(*) AS registros
FROM dbo.ConsentimientoUsuario c
JOIN dbo.Usuario u ON u.idUsuario = c.idUsuario
WHERE u.correoElectronico LIKE N'demo.%@example.com'
GROUP BY c.tipo, c.estado;

-- 16. Colisiones: correos demo ya usados por otra cuenta o dominios demo fuera de example.com. Esperado: sin filas.
SELECT idUsuario, correoElectronico
FROM dbo.Usuario
WHERE correoElectronico LIKE N'demo.%' AND correoElectronico NOT LIKE N'%@example.com';

-- 17. Integridad de la auditoría: la carga demo no genera filas de auditoría propias (solo las de los inicios de sesión de la demo).
SELECT accion, COUNT(*) AS filas
FROM dbo.Auditoria
WHERE idUsuario IN (SELECT idUsuario FROM dbo.Usuario WHERE correoElectronico LIKE N'demo.%@example.com')
GROUP BY accion
ORDER BY filas DESC;
