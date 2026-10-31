# Persistencia de datos en SQL Server: verificación técnica (TIF, Anexo H.6)

- **Fecha de ejecución:** 25/10/2026, de 17:31 a 17:40 (UTC−03:00). Equipo local Windows 11 con Docker Desktop.
- **Rama:** `perf/rendimiento-2026-10-23`.
- **Alcance:** stack local `glucolume` (`glucolume-frontend-1`, `glucolume-backend-1`, `glucolume-db-1`) y base `GlucoLume` (SQL Server 2022 CU16, edición Express).
- **Criterio:** solo comprobaciones reales sobre el entorno en ejecución. Se marca **parcial** o **pendiente** lo que no tiene evidencia directa.

## Restricciones respetadas

- No se reinició ni recreó ningún contenedor para esta verificación, no se borraron volúmenes, no se ejecutaron migraciones y no se modificó el esquema.
- Las consultas de verificación son de solo lectura y se ejecutaron con `sqlcmd` dentro de `glucolume-db-1`. La contraseña la toma `sqlcmd` de la variable del propio contenedor (`SQLCMDPASSWORD`) y nunca se escribe ni se muestra. Los valores `*_PASSWORD` y `BRIDGE_TOKEN` aparecen como `***`.
- La única escritura fue el respaldo `BACKUP DATABASE … WITH COPY_ONLY, CHECKSUM`. No altera los datos de `GlucoLume` ni la cadena de copias del log; solo registra el historial en `msdb`.
- Los resultados no incluyen nombre, apellido, DNI, correo ni fecha de nacimiento, y los identificadores aparecen recortados.

## Archivos

| Archivo | Contenido |
|---|---|
| `verificar_persistencia.ps1` | Script de solo lectura con una sección por captura (`-Seccion N`). |
| `consulta_mediciones.sql` | Consulta SQL de solo lectura de las mediciones, el dispositivo y la auditoría, sin datos personales. |
| `resultados/verificacion_2026-10-25.txt` | Salida completa del script en la fecha de ejecución. |
| `../../../respaldos/sqlserver/GlucoLume_2026-10-25_COPY_ONLY.bak` | Respaldo de la base. **Excluido de Git** (`.gitignore`: `respaldos/` y `*.bak`). |

Para reproducir todo, o una sola sección, desde la raíz del repositorio:

```powershell
powershell -ExecutionPolicy Bypass -File docs\evidencias\persistencia_sqlserver\verificar_persistencia.ps1
powershell -ExecutionPolicy Bypass -File docs\evidencias\persistencia_sqlserver\verificar_persistencia.ps1 -Seccion 5
```

## 1. Configuración de SQL Server

Comandos: secciones 1 y 2 del script (`docker ps`, `docker exec glucolume-backend-1 env` con las contraseñas enmascaradas, `sys.dm_exec_sessions`, `HAS_PERMS_BY_NAME` con `EXECUTE AS USER`).

- **Contenedores:** los tres están `Up … (healthy)`.
- **Conexión configurada en el backend:** `DB_HOST=db`, `DB_PORT=1433`, `DB_NAME=GlucoLume`, `DB_USER=glucolume_app`. `DB_TRUST_SERVER_CERTIFICATE=true` es un ajuste solo para desarrollo, y el propio backend lo advierte al iniciar.
- **Conexión efectiva:** SQL Server registra 4 sesiones del login `glucolume_app`, sobre la base `GlucoLume`, desde `172.18.0.2` (la IP del backend en la red `glucolume_data`), con programa `python3.14`. El backend no usa `sa`.
- **Base:** `GlucoLume`, en estado `ONLINE` y con recuperación `FULL`.
- **Permisos de `glucolume_app`:** es miembro de `rol_glucolume_api`. Tiene `SELECT` e `INSERT` sobre `Medicion`, y `SELECT` sobre `Dispositivo`. No tiene `UPDATE` sobre `Auditoria` (está denegado), ni `CREATE TABLE`, ni es `db_owner`. Es decir, tiene los permisos mínimos para registrar y consultar mediciones.

## 2. Persistencia de datos

Comandos: sección 3 del script (`docker inspect`, `docker volume inspect`, `sys.master_files`, `df`, `ls`).

- `glucolume-db-1` monta el volumen con nombre `glucolume_mssql-data` (driver `local`, proyecto `glucolume`) en `/var/opt/mssql`, en modo lectura-escritura.
- Según SQL Server, los archivos de la base son `/var/opt/mssql/data/GlucoLume.mdf` (ROWS) y `/var/opt/mssql/data/GlucoLume_log.ldf` (LOG). Están en el punto de montaje del volumen (`df` muestra `/var/opt/mssql` sobre su propio dispositivo) y no en la capa del contenedor.
- **Registros persistidos (sección 4):** `Usuario` 1, `PerfilMedicion` 1, `Dispositivo` 1, `Medicion` 1, `Auditoria` 11, `ReglaMatriz` 27, `Matriz` 1, entre otras tablas.

## 3. Conservación de datos al recrear contenedores

No se recrearon contenedores para esta verificación. Evidencias encontradas:

1. **Recreación previa del contenedor de la base (24/10/2026, 18:46 UTC−3).** Ese día se reconstruyeron las imágenes para aplicar parches de seguridad y `docker compose up -d` reemplazó el contenedor de la base: antes era `812fd60a935e` con la imagen `8a6843af0e3b`, y ahora es `7055cfdfe7a7` con la imagen `be3bb41822a3`. Tras ese cambio:
   - El volumen se creó el `2026-10-24T17:57:08Z` y la base `GlucoLume` el `2026-10-24 17:57:39` (UTC). Ambos son anteriores al contenedor actual, creado el `2026-10-24T21:46:05Z`, y la base sigue presente con su esquema y sus datos de referencia.
   - `@@SERVERNAME` devuelve `812fd60a935e`, que es el nombre del contenedor **anterior**, mientras que el contenedor actual es `7055cfdfe7a7`. Ese valor se guarda en la base `master`, dentro del volumen, así que el contenido del volumen sobrevivió a la recreación del contenedor.
2. **Reinicio del stack.** Los contenedores se reiniciaron el `2026-10-25T20:11:15Z` sin recrearse. El evento de auditoría del `2026-10-24 19:46` (hora local), anterior a ese reinicio, sigue en la tabla.
3. **Evidencia anterior en el repositorio.** `docs/evidencias/validacion_integral/resultados/stack_docker_completo.txt`, sección 7, registra que `compose down` sin `-v` conserva `mssql-data`. Esa prueba corrió en **otro entorno** (Linux de pruebas), no en este equipo.

**Limitación:** la recreación del 24/10 no fue una prueba controlada de persistencia, y la medición del Arduino (25/10) es posterior a ella. Por lo tanto, la conservación de esa medición concreta ante una recreación **no fue comprobada**. Estado: **parcial**.

## 4. Mediciones del Arduino real

Comandos: sección 5 (`consulta_mediciones.sql`) y sección 8 (origen físico).

| Campo | Valor |
|---|---|
| Medición | `2DE67BF5…`, del 25/10/2026 17:16:06 a 17:17:04 (57 s) |
| Dispositivo | `GL-0001`, modelo `Arduino UNO + MAX30100`, sensor `MAX30100`, estado `OPERATIVO` (registrado a las 17:14:33) |
| Frecuencia cardíaca | 104 BPM |
| SpO₂ | 97,20 % |
| Origen de la glucosa | **DEMO**: valor sintético del firmware (115 mg/dL). **No es una medición de glucosa.** |
| Modo y estado | `GLUCOSA_EXPERIMENTAL`, `COMPLETADA`; 8 lecturas estabilizadas; algoritmo `firmware-glucolume-max30100-v1` |
| Perfil | `CONSUMIDOR_FINAL`, sin datos personales en la consulta |

Evidencias del origen físico:

- **Auditoría del flujo**, en orden: `REGISTRAR_DISPOSITIVO` (17:14:33), `TOMAR_CONTROL_DISPOSITIVO` (17:15:27), `ORDEN_PUENTE_SERIE` (17:15:32), `INICIAR_MEDICION` e `INICIAR_SESION_DISPOSITIVO` (17:16:06) y `GUARDAR_MEDICION_DISPOSITIVO` (17:17:04). Todos con resultado `EXITO`.
- **Puente serie:** `bridge.env` configura `SERIAL_PORT=COM4` y `SERIAL_MEDIUM=BLUETOOTH`. `COM4` es un puerto «Serie estándar sobre el vínculo Bluetooth» emparejado con un equipo de MAC `98:D3:31:F5:B6:7E`; ese prefijo es habitual en los módulos HC-05/HC-06. El proceso `glucolume_bridge.py --service` se ejecuta desde las 17:14:14.
- **Backend:** recibe `POST /api/v1/acquisition/bridge/ingest` desde el host. El recuento crece mientras el puente sigue enviando telemetría, y luego aparecen `telemetry/session` (201) y `telemetry/session/save` (200).
- **No hay registros sintéticos de pruebas automatizadas** en esta base: hay una sola medición, ligada al único dispositivo registrado.

Límites de la evidencia:

- Ninguna columna de `Medicion` registra el canal de llegada. `MuestraSensor` y `AuditoriaTecnicaMedicion` están vacías y `versionFirmwareAlMomento` es `NULL`.
- No se encontró el registro propio del puente. Los `bridge.log` y `status.json` de `%LOCALAPPDATA%\GlucoLume\bridge` son del 13/10, y `bridge_ctl.py status` informa «Detenido» aunque el proceso está activo.
- El origen físico se respalda con la correlación temporal entre el puerto Bluetooth, el proceso del puente, el registro del dispositivo, los envíos al backend y la auditoría, no con un campo de la base.
- La glucosa es **DEMO**, así que solo BPM y SpO₂ provienen del sensor.

**Historial en la aplicación:** después del guardado, el backend atendió `GET /api/v1/measurements/2de67bf5-…` (200) y `measurements/dashboard` y `measurements/evolution` (200). Es decir, la aplicación consultó la medición guardada. La captura de pantalla está **pendiente** (ver captura 6).

## 5. Copia de seguridad externa

- No había ningún `.bak` de la base fuera del volumen. El único `.bak` del repositorio es `.env.antes-rendimiento.bak`, que es una copia de configuración y no de la base.
- Se generó con `BACKUP DATABASE [GlucoLume] TO DISK=N'/tmp/…' WITH COPY_ONLY, CHECKSUM, INIT`, en `/tmp` del contenedor y fuera del volumen: 946 páginas.
- Se copió con `docker cp` a `respaldos/sqlserver/GlucoLume_2026-10-25_COPY_ONLY.bak` (7.852.032 bytes) y se borró la copia temporal del contenedor.
- **SHA-256:** `c48cc9cb205256f2e2a3c30b2f9b23bf302dfa861bd09a8c5c09380d7aa67e1c`, idéntico dentro y fuera del contenedor.
- **`RESTORE VERIFYONLY … WITH CHECKSUM`:** «The backup set on file 1 is valid». En `msdb.dbo.backupset` figura `is_copy_only = 1` y `has_backup_checksums = 1`. `RESTORE FILELISTONLY` lista `GlucoLume` (D) y `GlucoLume_log` (L).
- `git check-ignore` confirma la exclusión (`.gitignore: respaldos/`). El archivo contiene datos personales: no se sube ni se comparte.

## 6. Capturas para el TIF

Antes de cada captura, conviene ampliar la terminal y ocultar la barra de pestañas con otros proyectos. Ninguna salida muestra secretos.

| N.º | Qué capturar | Cómo |
|---|---|---|
| 1 | Contenedores activos | Docker Desktop → **Containers** → desplegar el proyecto `glucolume`: los tres en verde (*Running*). Complemento: `verificar_persistencia.ps1 -Seccion 1`. |
| 2 | Conexión backend–SQL Server | `verificar_persistencia.ps1 -Seccion 2`. Encuadrar las variables `DB_*` (con `***`), la sesión `glucolume_app` y los permisos. **No** abrir la pestaña *Inspect → Env* de Docker Desktop, que muestra las contraseñas. |
| 3 | Volumen persistente | Docker Desktop → **Volumes** → `glucolume_mssql-data` (*In use*, pestaña *Data*, carpeta `data/` con `GlucoLume.mdf`/`.ldf`). Complemento: `-Seccion 3`. |
| 4 | Base y tablas | `-Seccion 4`. |
| 5 | Mediciones registradas | `-Seccion 5`. |
| 6 | Historial en la aplicación | Abrir `http://localhost`, iniciar sesión, ir a la sección de mediciones/evolución y abrir la medición del 25/10/2026 17:16 (104 BPM, 97,2 % SpO₂, rótulo DEMO). Recortar el nombre y el correo de la cabecera. |
| 7 | Respaldo `.bak` verificado | `-Seccion 7` (tamaño, SHA-256, exclusión de Git y `RESTORE VERIFYONLY`). Opcional: el Explorador de Windows en `respaldos\sqlserver`. |
| 8 (opcional) | Origen físico | `-Seccion 8`. Y en Windows, **Configuración → Bluetooth y dispositivos → Dispositivos**, con el HC-06 emparejado. |

## Pendientes

- **Recreación controlada:** detener y recrear solo `db` en una ventana acordada, con `docker compose up -d --force-recreate db` y **sin** `-v`, y luego ejecutar `-Seccion 5` para mostrar que la medición del 25/10 sigue presente. No se hizo por la restricción de no recrear servicios en funcionamiento.
- **Captura 6** (historial en la aplicación): requiere iniciar sesión con la cuenta personal.
- **Trazabilidad del canal:** registrar en la medición, o en `AuditoriaTecnicaMedicion`, el canal (`PUENTE_SERIE`/Bluetooth) y la versión de firmware, para que el origen físico conste en la base y no dependa de la correlación temporal.
- **Registro del puente:** averiguar por qué el puente en ejecución no actualiza `%LOCALAPPDATA%\GlucoLume\bridge\bridge.log`/`status.json` (`bridge_ctl.py status` informa «Detenido»).
- **Medición de glucosa real:** la registrada es DEMO. Para documentar una glucosa experimental, desactivar el modo DEMO del firmware y repetir.
