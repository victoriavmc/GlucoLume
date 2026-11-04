-- GlucoLume - RESET de la auditoría de la DEMO (excepción controlada a GL-03). Lo ejecuta el DBA, UNA vez, antes de limpiar y recargar
-- los datos demo cuando cambió su forma (p. ej., las altas, transferencias y auditorías de inicio de medición de los pacientes).
--
-- Por qué existe: la auditoría es de solo inserción para la API (GL-03). La limpieza demo (app/demo/limpieza.py) no la toca y, con
-- auditoría que referencia cuentas demo, se bloquea. Este script borra SOLO las filas de auditoría cuyo autor es una cuenta demo
-- (correo demo.*@example.com). No borra auditoría de cuentas reales.
--
-- Requisitos antes de ejecutar:
--   1. Copia de seguridad completa de la base (y confirmación de que se puede restaurar).
--   2. Decisión registrada del responsable del sistema: el borrado de auditoría es un hecho que lo requiere.
--   3. Ejecutar primero el bloque de VERIFICACIÓN y revisar los números.
--   4. NO ejecutado aquí: el script no fue probado en SQL Server en este entorno.

-- ---------------------------------------------------------------------------------------------------------------------------------
-- 1. VERIFICACIÓN (solo lectura)
-- ---------------------------------------------------------------------------------------------------------------------------------

-- Cuentas demo.
SELECT COUNT(*) AS cuentas_demo
FROM dbo.Usuario
WHERE correoElectronico LIKE 'demo.%@example.com';

-- Auditoría que se borraría (autor demo).
SELECT accion, COUNT(*) AS filas
FROM dbo.Auditoria
WHERE idUsuario IN (SELECT idUsuario FROM dbo.Usuario WHERE correoElectronico LIKE 'demo.%@example.com')
GROUP BY accion
ORDER BY filas DESC;

-- Auditoría de cuentas NO demo que apunta a instituciones demo (si hay filas, el reset no la toca y la limpieza seguirá bloqueada:
-- revisar antes de seguir).
SELECT COUNT(*) AS auditoria_real_sobre_instituciones_demo
FROM dbo.Auditoria
WHERE (idUsuario IS NULL OR idUsuario NOT IN (SELECT idUsuario FROM dbo.Usuario WHERE correoElectronico LIKE 'demo.%@example.com'))
  AND idInstitucion IN (SELECT idInstitucion FROM dbo.Institucion WHERE nombre LIKE N'Institución Demo %');
GO

-- ---------------------------------------------------------------------------------------------------------------------------------
-- 2. BORRADO (solo después de la copia de seguridad y de revisar la verificación)
-- ---------------------------------------------------------------------------------------------------------------------------------

BEGIN TRANSACTION;

DELETE FROM dbo.Auditoria
WHERE idUsuario IN (SELECT idUsuario FROM dbo.Usuario WHERE correoElectronico LIKE 'demo.%@example.com');

-- Comprobación: debe devolver 0.
SELECT COUNT(*) AS restante
FROM dbo.Auditoria
WHERE idUsuario IN (SELECT idUsuario FROM dbo.Usuario WHERE correoElectronico LIKE 'demo.%@example.com');

-- Si el número de la comprobación es 0 y el de la verificación era el esperado: COMMIT. Si no: ROLLBACK.
-- COMMIT TRANSACTION;
-- ROLLBACK TRANSACTION;
GO
