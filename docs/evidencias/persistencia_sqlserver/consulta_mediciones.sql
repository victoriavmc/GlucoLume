-- Mediciones persistidas en GlucoLume (SOLO LECTURA, sin datos personales).
-- No muestra nombre, apellido, DNI, correo ni fecha de nacimiento del perfil; los identificadores se recortan.
--
-- Ejecutar desde la raíz del repositorio (la contraseña la toma sqlcmd del contenedor, no se escribe):
--   powershell -ExecutionPolicy Bypass -File docs\evidencias\persistencia_sqlserver\verificar_persistencia.ps1 -Seccion 5
-- (el puerto 1433 no se publica al host: la consulta corre con sqlcmd dentro del contenedor glucolume-db-1).
SET NOCOUNT ON;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

PRINT '== Mediciones con su dispositivo';
SELECT LEFT(CONVERT(varchar(36), m.idMedicion), 8) + '...'  AS idMedicion,
       CONVERT(varchar(19), m.fechaHoraInicio, 120)          AS inicio,
       CONVERT(varchar(19), m.fechaHoraFin, 120)             AS fin,
       m.duracionMs / 1000                                   AS duracion_s,
       LEFT(d.codigoDispositivo, 7)                          AS dispositivo,
       d.modelo                                              AS modeloDispositivo,
       m.modeloSensorAlMomento                               AS sensor,
       m.frecuenciaCardiaca                                  AS bpm,
       m.spo2                                                AS spo2,
       m.origenGlucosa,
       m.glucosaDispositivo,
       m.unidadGlucosa,
       m.modoMedicion,
       m.estadoMedicion,
       m.lecturasEstabilizadas,
       m.versionAlgoritmo,
       p.tipoPerfil
FROM dbo.Medicion m
LEFT JOIN dbo.Dispositivo d    ON d.idDispositivo = m.idDispositivo
LEFT JOIN dbo.PerfilMedicion p ON p.idPerfilMedicion = m.idPerfilMedicion
ORDER BY m.fechaHoraInicio DESC;

PRINT '== Recuento por origen de la glucosa y estado';
SELECT origenGlucosa, estadoMedicion, COUNT(*) AS cantidad
FROM dbo.Medicion
GROUP BY origenGlucosa, estadoMedicion
ORDER BY origenGlucosa, estadoMedicion;

PRINT '== Auditoría del flujo de adquisición (sin datos previos/nuevos)';
SELECT CONVERT(varchar(23), fechaHora, 121) AS fechaHora, tipoEvento, accion, tablaAfectada, resultado, modulo
FROM dbo.Auditoria
WHERE modulo IN ('DISPOSITIVOS', 'MEDICIONES') OR accion = 'ORDEN_PUENTE_SERIE'
ORDER BY fechaHora;
