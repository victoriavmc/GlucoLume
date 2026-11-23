-- GlucoLume - Vincula las cuentas individuales que YA midieron con el dispositivo que usaron
--
-- Las mediciones de una cuenta individual se hicieron con un dispositivo, pero las cuentas que midieron antes de que existiera
-- dbo.VinculoCuentaDispositivo no quedaron vinculadas (la vinculación solo nace en la primera medición nueva). Este script crea el
-- vínculo para cada cuenta CONSUMIDOR_FINAL que tiene mediciones y todavía no tiene vínculo, usando el dispositivo de su PRIMERA
-- medición. Si una cuenta midió con más de un dispositivo, se toma el de la primera medición y el caso aparece en la verificación
-- (la aplicación no permitirá medir con otro de ahí en adelante).
--
-- Idempotente: una cuenta que ya tiene vínculo no se toca, y volver a ejecutarlo no duplica nada. No modifica mediciones, perfiles,
-- dispositivos ni cuentas. Transaccional (todo o nada).
--
-- Requisito: haber aplicado antes GlucoLume_vinculo_cuenta_dispositivo.sql (crea la tabla).
--
-- Antes: respaldo restaurable (GlucoLume_respaldo.ps1).
--   sqlcmd -S <servidor> -E -C -I -d <base> -i GlucoLume_vinculo_cuenta_dispositivo_datos.sql -v CONFIRMAR="VINCULAR_CUENTAS_DATOS_EXISTENTES"
-- Reversión: restaurar el respaldo. Este script no guarda cuáles vínculos creó; borrar vínculos no toca mediciones ni dispositivos.

:on error exit

IF N'$(CONFIRMAR)' <> N'VINCULAR_CUENTAS_DATOS_EXISTENTES'
BEGIN
    RAISERROR(N'Falta -v CONFIRMAR="VINCULAR_CUENTAS_DATOS_EXISTENTES": no se hizo nada.', 16, 1);
    SET NOEXEC ON;
END
GO

IF OBJECT_ID(N'dbo.VinculoCuentaDispositivo', N'U') IS NULL
BEGIN
    RAISERROR(N'Falta la tabla dbo.VinculoCuentaDispositivo: aplicar antes GlucoLume_vinculo_cuenta_dispositivo.sql. No se hizo nada.', 16, 1);
    SET NOEXEC ON;
END
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;

;WITH medicionesPorDispositivo AS (
    -- Una fila por (cuenta, dispositivo) usado en sus mediciones, con la fecha de la primera medición con ese dispositivo.
    SELECT p.idUsuario,
           m.idDispositivo,
           MIN(m.fechaHoraInicio) AS fechaPrimera
    FROM dbo.Medicion m
    INNER JOIN dbo.PerfilMedicion p ON p.idPerfilMedicion = m.idPerfilMedicion
    INNER JOIN dbo.Usuario u ON u.idUsuario = p.idUsuario
    WHERE u.tipoCuenta = N'CONSUMIDOR_FINAL'
      AND p.idUsuario IS NOT NULL
    GROUP BY p.idUsuario, m.idDispositivo
),
primerDispositivo AS (
    -- Por cuenta, el dispositivo de su primera medición (desempate estable por idDispositivo).
    SELECT idUsuario,
           idDispositivo,
           fechaPrimera,
           ROW_NUMBER() OVER (PARTITION BY idUsuario ORDER BY fechaPrimera, idDispositivo) AS orden
    FROM medicionesPorDispositivo
)
INSERT INTO dbo.VinculoCuentaDispositivo (idUsuario, idDispositivo, fechaVinculo)
SELECT d.idUsuario, d.idDispositivo, d.fechaPrimera
FROM primerDispositivo d
WHERE d.orden = 1
  AND NOT EXISTS (SELECT 1 FROM dbo.VinculoCuentaDispositivo v WHERE v.idUsuario = d.idUsuario);

COMMIT TRANSACTION;
GO

-- VERIFICACION 1: cuentas individuales con mediciones y SIN vínculo (debe quedar 0; las cuentas sin mediciones no necesitan vínculo).
SELECT COUNT(DISTINCT p.idUsuario) AS cuentasConMedicionesSinVinculo
FROM dbo.Medicion m
INNER JOIN dbo.PerfilMedicion p ON p.idPerfilMedicion = m.idPerfilMedicion
INNER JOIN dbo.Usuario u ON u.idUsuario = p.idUsuario
WHERE u.tipoCuenta = N'CONSUMIDOR_FINAL'
  AND NOT EXISTS (SELECT 1 FROM dbo.VinculoCuentaDispositivo v WHERE v.idUsuario = p.idUsuario);

-- VERIFICACION 2: cuentas que midieron con MÁS de un dispositivo (revisar a mano: solo quedó vinculado el de la primera medición).
SELECT p.idUsuario, COUNT(DISTINCT m.idDispositivo) AS dispositivosUsados
FROM dbo.Medicion m
INNER JOIN dbo.PerfilMedicion p ON p.idPerfilMedicion = m.idPerfilMedicion
INNER JOIN dbo.Usuario u ON u.idUsuario = p.idUsuario
WHERE u.tipoCuenta = N'CONSUMIDOR_FINAL'
GROUP BY p.idUsuario
HAVING COUNT(DISTINCT m.idDispositivo) > 1;

-- VERIFICACION 3: vínculos por dispositivo.
SELECT d.codigoDispositivo, COUNT(*) AS cuentasVinculadas
FROM dbo.VinculoCuentaDispositivo v
INNER JOIN dbo.Dispositivo d ON d.idDispositivo = v.idDispositivo
GROUP BY d.codigoDispositivo
ORDER BY d.codigoDispositivo;
GO

SET NOEXEC OFF;
GO
