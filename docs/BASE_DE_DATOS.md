# Base de datos

> Última revisión: 23/10/2026. Contrastada con una instalación y una actualización reales en SQL Server 2022 (contenedor descartable, datos sintéticos): §2.1, §3.1 y §6. No se tocó ninguna base real.

Esquema de SQL Server, estrategia de esquema único (**DEC-02**), instalación, actualización, respaldo y permisos. Docker nunca crea, borra
ni migra bases: todo lo de este documento se hace a mano, con un usuario administrador de SQL Server (no el de la API).

## 1. DEC-02 — Esquema SQL consolidado

**Decisión:** el proyecto mantiene **un único esquema SQL final** como referencia para instalaciones nuevas:
`database/reference/GlucoLume_DB_v5.sql`. Los scripts incrementales numerados (`001`–`034`) y los esquemas anteriores (`v1`–`v3`) se
**retiraron intencionalmente**; no se restauran ni son dependencia de las pruebas.

| Qué | Dónde |
|---|---|
| Esquema vigente | `database/reference/GlucoLume_DB_v5.sql` (UTF-16, generado por SSMS el 19/10/2026 y corregido el 23/10/2026; **34 tablas** —incluye `PuenteCredencial`, H-16—, 49 claves foráneas, 127 `CHECK` y los **31 índices** que el export original había perdido; **no crea usuarios, roles ni permisos**: los aplican los scripts de permisos) |
| Matriz global de referencia | `database/reference/MATRIZ.SQL`: carga la matriz global (27 reglas: 3 sexos × 3 rangos de edad × 3 condiciones de comida) y el procedimiento `usp_GlucoLume_CompararGlucosa`; sus cambios de esquema sobre `ReglaMatriz` ya están en v5 (v5 no contiene filas de datos) |
| Vaciado de datos (no es instalación) | `database/reference/BorrarRap.sql`: borra todas las filas; exige `-v BASE=<base> CONFIRMAR_BORRADO=<base>` iguales a la base conectada; nunca sobre una base con datos reales |
| Permisos de mínimo privilegio (no es instalación) | `GlucoLume_permisos.sql` (roles de API y de conservación; `DELETE` solo en 14 tablas; `DENY UPDATE, DELETE` sobre la auditoría), `GlucoLume_permisos_quitar_roles_fijos.sql` (quita `db_datareader`/`db_datawriter`; reversible con `…_restaurar_roles_fijos.sql`), `GlucoLume_permisos_verificar.sql` (solo comprueba) y `GlucoLume_permisos_revertir.sql`. Validados en SQL Server 2022 descartable; **no aplicados a tu instancia** (§5) |
| Actualización de una base ya instalada | `GlucoLume_actualizar_instalada.sql` (6 `CK_Medicion_*` y los 31 índices, idempotente) y `GlucoLume_agregar_puente_credencial.sql` (tabla `PuenteCredencial`, H-16, idempotente) y `GlucoLume_matriz_referencia.sql` (`Matriz.urlReferencia` opcional y `Matriz.referenciaBase` obligatoria; las filas anteriores quedan con «Sin registrar (matriz anterior)» hasta completarse). Ensayo sin pérdida de datos: §3.1 |
| Validación automática | `backend/tests/test_reference_schema.py` (tablas, columnas y restricciones del modelo frente a v5) y las pruebas de reglas puntuales que antes leían scripts (`test_auth_access_account_type`, `test_platform_institution_deletion`, `test_quota`, `test_google_exchange`) |

### 1.1 Qué incluye v5 que antes dependía de scripts

| Regla (script retirado) | En v5 |
|---|---|
| Capacidad de cuentas de la institución (028) | `Institucion.capacidadMaximaUsuarios INT NOT NULL DEFAULT 1000`, `CK_Institucion_capacidadMaximaUsuarios` (> 0) |
| Ciclo de vida de cuentas institucionales (029) | Columnas de gracia y minimización, `ReasignacionPaciente` |
| Correo de resultados del paciente (030) | `PerfilMedicion.correoResultados`, `fechaAutorizacionCorreo`, `fechaExpiracionCorreo` y su `CHECK` |
| Contexto de seguridad de la auditoría (032) | Tabla `AuditoriaContexto` (correlación, IP, cliente, motivo, huella) |
| Cierre administrativo de instituciones (033) | `Institucion.cierreAdministrativo`, fecha, actor y motivo; `CK_Institucion_cierreAdministrativo`, `FK_Institucion_cierreAdministrativo_Usuario` |
| Tipo de cuenta en el evento de acceso (034) | `Auditoria.tipoCuentaActor NVARCHAR(40) NULL` sin `DEFAULT`; `CK_Auditoria_tipoCuentaActor` con los cuatro tipos de cuenta |
| Tipos de token de cuenta (011) | `CK_TokenCuenta_tipo` igual al Enum `TipoTokenCuenta` |

### 1.2 Diferencias registradas entre el modelo y v5

Ninguna desde el 19/10/2026: las seis restricciones de glucosa del dispositivo que los modelos declaraban y v5 no tenía
(`CK_Medicion_lecturas`, `CK_Medicion_glucosaDispositivoOrigen`, `CK_Medicion_origenConGlucosa`, `CK_Medicion_glucosaDispositivoRango`,
`CK_Medicion_unidadGlucosa`, `CK_Medicion_indiceOptico`) se agregaron a v5 con la misma definición, y también los **25 índices** que v5 no
tenía (12 de consulta `IX_*` y 13 únicos filtrados `UX_*` que sostienen reglas de negocio: un administrador vigente, un DNI por institución,
una matriz activa por ámbito, una transferencia o reasignación pendiente por paciente, un vínculo vigente). `tests/test_reference_schema.py`
compara tablas, columnas, nombres de restricciones, cada `CHECK` (valores, columnas y números) y cada índice (tabla, unicidad, columnas y
filtro); falla ante cualquier diferencia nueva.

Ensayo del 19/10/2026 en SQL Server 2022 Developer descartable (contenedor sin volúmenes): v5 se instala desde cero sin errores (33 tablas,
49 FK, 125 `CHECK`, 25 índices además de las claves y `UNIQUE`), `MATRIZ.SQL` crea la matriz global y sus 27 reglas, y
`python -m app.cli.schemaCheck` no encuentra diferencias con los modelos. La comparación de catálogos del 16/10/2026 indicaba que la base real no tenía esas seis
([evidencias/PRUEBAS_CONCURRENCIA_SQLSERVER_2026-10-16.md](evidencias/PRUEBAS_CONCURRENCIA_SQLSERVER_2026-10-16.md)): agregarlas a una base con
datos es parte de la actualización controlada (§3) y requiere autorización.

### 1.2.1 Base instalada frente a v5 (19/10/2026, solo lectura del catálogo)

`python -m app.cli.schemaCheck` contra la base real (vistas `sys.*` con la cuenta de la aplicación; ninguna fila de datos):

- Coinciden las 33 tablas, sus columnas, claves primarias, las 49 FK y los índices únicos y de consulta.
- **(Resuelto, ver abajo)** Faltaban las 6 `CK_Medicion_*` de glucosa del dispositivo. Las consultas de conteo de `python -m app.cli.schemaCheck --preparar-validacion`
  (solo `SELECT COUNT_BIG(*)`, sin filas) se ejecutaron sobre la base real el 19/10/2026 con autorización: **0 filas violarían cada una**
  (`glucosaDispositivoOrigen`, `origenConGlucosa`, `glucosaDispositivoRango`, `unidadGlucosa`, `indiceOptico`, `lecturas`). Agregarlas sigue
  sin hacerse (requiere autorización y una copia previa).
- La base tenía 6 índices que ni v5 ni los modelos declaraban: `UX_Usuario_correoElectronico` y `UX_Usuario_usuario` (únicos, de los que
  depende el código para rechazar correos y usuarios repetidos), `IX_Usuario_graciaVencimiento`, `IX_Auditoria_accion_fecha`,
  `IX_Auditoria_usuario_fecha` e `IX_Medicion_estado_fin`. Se agregaron a los modelos y a v5. Verificado en el catálogo: columnas, unicidad
  y columnas incluidas de los seis; `IX_Auditoria_accion_fecha` e `IX_Medicion_estado_fin` no tienen filtro (**verificados por completo**).
  Los otros cuatro tienen filtro (`has_filter = 1`), pero la cuenta de la aplicación no tiene `VIEW DEFINITION` (`HAS_PERMS_BY_NAME = 0`) y
  `filter_definition` vuelve vacío. **Verificado después con la cuenta de Windows `sysadmin`**: los cuatro filtros son exactamente
  `[columna] IS NOT NULL`, igual que en los modelos y en v5. Consulta usada (requiere una cuenta con
  `VIEW DEFINITION` sobre `dbo.Usuario` y `dbo.Auditoria` debe ejecutar (solo lectura):

  ```sql
  SELECT t.name AS tabla, i.name AS indice, i.is_unique, i.filter_definition
  FROM sys.indexes AS i JOIN sys.tables AS t ON t.object_id = i.object_id
  WHERE i.name IN (N'UX_Usuario_correoElectronico', N'UX_Usuario_usuario', N'IX_Usuario_graciaVencimiento', N'IX_Auditoria_usuario_fecha');
  ```

  Si un filtro difiere, se corrige en el modelo y en v5 y `tests/test_reference_schema.py` lo vuelve a exigir.
- `sysdiagrams` (diagramas de SSMS) no es parte del esquema y la herramienta lo ignora.

**Migración aplicada (19/10/2026, 22:55):** `database/reference/GlucoLume_actualizar_instalada.sql` (idempotente, con confirmación y en una
transacción) agregó las 6 `CK_Medicion_*` a la base real, tras respaldo verificado y ensayo en la copia restaurada (14 casos válidos,
inválidos y límite contra las definiciones instaladas). Quedaron habilitadas y confiables (`is_disabled = 0`, `is_not_trusted = 0`) y
`schemaCheck` no informa diferencias. Reversión: `ALTER TABLE dbo.Medicion DROP CONSTRAINT <nombre>` (no toca datos).

### 1.3 Esquema final frente a base instalada

Que v5 incluya una columna o restricción **no demuestra** que exista en una base ya instalada. El backend lo resuelve en tiempo de
ejecución con `services/schemaCompat.py`: comprueba en el catálogo si existen las piezas opcionales (por ejemplo `tipoCuentaActor`,
`AuditoriaContexto`, columnas de cierre administrativo o de correo) y, si faltan, no las nombra y desactiva la función correspondiente sin
fallar. Con SQLite (pruebas) supone siempre que existen. Un «no» se vuelve a consultar a los 30 s y un «sí» a los 10 minutos: si se
restaura una base sin una columna, el backend lo nota sin reiniciarse.

## 2. Instalación nueva

1. Crear una base **vacía** `GlucoLume` con la intercalación del proyecto: `CREATE DATABASE GlucoLume COLLATE Modern_Spanish_CI_AS` (el archivo empieza con
   `USE [GlucoLume]`; con otro nombre, reemplazarlo en una copia).
2. Aplicar `GlucoLume_DB_v5.sql` y comprobar que termine **sin errores** (usar `-I`: los índices filtrados exigen `QUOTED_IDENTIFIER ON`):
   - Windows (PowerShell, instancia de Windows): `sqlcmd -S localhost\GLUCOLUME -E -C -I -b -d GlucoLume -i database\reference\GlucoLume_DB_v5.sql`
   - Contenedor del perfil `db` (el archivo es UTF-16; hay que convertirlo y copiarlo, `sqlcmd` del contenedor lee un archivo local):
     ```powershell
     # PowerShell (5.1 o 7): convertir a UTF-8 sin BOM y copiar al contenedor (se llama «glucolume-db-1»)
     [IO.File]::WriteAllText("$env:TEMP\v5.sql", [IO.File]::ReadAllText("$PWD\database\reference\GlucoLume_DB_v5.sql", [Text.Encoding]::Unicode), (New-Object Text.UTF8Encoding($false)))   # UTF-8 sin BOM
     docker cp $env:TEMP\v5.sql glucolume-db-1:/tmp/v5.sql
     docker cp database\reference\MATRIZ.SQL glucolume-db-1:/tmp/MATRIZ.SQL
     docker compose --profile db exec db /opt/mssql-tools18/bin/sqlcmd -C -I -S localhost -U sa -Q "CREATE DATABASE GlucoLume COLLATE Modern_Spanish_CI_AS"
     docker compose --profile db exec db /opt/mssql-tools18/bin/sqlcmd -C -I -S localhost -U sa -d GlucoLume -b -i /tmp/v5.sql
     ```
     (la contraseña de `sa` la toma `SQLCMDPASSWORD` de `docker/db.env`). En Linux/macOS: `iconv -f UTF-16 -t UTF-8 …`.
3. Si se quiere la matriz global de referencia precargada, ejecutar `MATRIZ.SQL` completo (27 reglas; también se puede crear desde el panel de la plataforma).
4. **Cuentas y permisos (H-02):** crear los inicios de sesión en la instancia —uno para la API y, aparte, uno para la conservación— con contraseñas propias (nunca `sa`), y
   aplicar los permisos con los scripts de `database/reference` (cada uno exige su `CONFIRMAR`; ver el encabezado de cada archivo):
   ```sql
   CREATE LOGIN glucolume_app   WITH PASSWORD = N'<contraseña larga>', CHECK_POLICY = ON;
   CREATE LOGIN glucolume_jobs  WITH PASSWORD = N'<otra contraseña larga>', CHECK_POLICY = ON;
   ```
   ```text
   sqlcmd … -d GlucoLume -I -i GlucoLume_permisos.sql -v API_LOGIN="glucolume_app" JOBS_LOGIN="glucolume_jobs" CONFIRMAR="APLICAR_PERMISOS_GLUCOLUME"
   sqlcmd … -d GlucoLume -I -i GlucoLume_permisos_quitar_roles_fijos.sql -v API_LOGIN="glucolume_app" CONFIRMAR="QUITAR_ROLES_FIJOS_GLUCOLUME"
   sqlcmd … -d GlucoLume -I -i GlucoLume_permisos_verificar.sql -v API_LOGIN="glucolume_app"      # solo comprueba
   ```
   La API usa `DB_USER=glucolume_app`; `DB_JOBS_USER=glucolume_jobs` es solo del servicio `lifecycle` y de las herramientas de conservación y de `bridgeTokens`.
5. Generar `MFA_ENCRYPTION_KEY` (comando en `.env.example`) **antes del primer uso** y guardarla aparte: con otra clave los secretos MFA
   guardados dejan de descifrarse.
6. Crear el primer administrador: `docker compose exec backend python -m app.cli.initAdmin --help`.

### 2.1 Resultado verificado de esta instalación (23/10/2026)

Contenedor `db` del Compose del proyecto (SQL Server 2022 CU16 Express, volumen persistente `mssql-data`, sin puertos publicados), con los pasos 1–4:
**34 tablas**, 49 claves foráneas, 127 `CHECK`, 33 índices `IX_`/`UX_`, 1 procedimiento (`usp_GlucoLume_CompararGlucosa`), 27 reglas de matriz, tabla `PuenteCredencial` presente,
`GlucoLume_permisos_verificar.sql` con todas las comprobaciones esperadas (auditoría sin UPDATE/DELETE: error 229; `DELETE` ajeno rechazado; la API solo anota `fechaUltimoUso`
en `PuenteCredencial`) y la cuenta de la API solo en `rol_glucolume_api`. El backend en otro contenedor se conectó con `glucolume_app` y recorrió registro, MFA,
instituciones, grupos y puentes sin un solo error de permisos ([evidencias/validacion_integral](evidencias/validacion_integral/README.md)). Los datos sobrevivieron a `docker compose down`
(sin `-v`) y a un nuevo `up`.

## 3. Base existente

No hay tabla de migraciones ni scripts numerados (DEC-02): ejecutar v5 sobre una base con datos **no es seguro** (crea objetos que ya existen). Una base ya instalada se
actualiza con scripts **idempotentes y transaccionales** que no tocan filas, siempre con respaldo previo y **primero en una copia restaurada**:

1. **Comparar** el catálogo con `python -m app.cli.schemaCheck` (solo lectura: tablas, columnas, `CHECK`, `FK` e índices que faltan o sobran; sale con 1 si hay
   diferencias). Ejecutarlo contra la base real requiere autorización.
2. Aplicar, en este orden y con `sqlcmd -I`, solo lo que corresponda:
   - `GlucoLume_actualizar_instalada.sql -v CONFIRMAR="ACTUALIZAR_GLUCOLUME_V5"`: las 6 `CK_Medicion_*` y los 31 índices que falten (cada uno se crea solo si no existe; los `UX_*` son
     únicos filtrados: si los datos violaran una regla, el script falla y se revierte entero).
   - `GlucoLume_agregar_puente_credencial.sql -v CONFIRMAR="AGREGAR_PUENTE_CREDENCIAL"`: la tabla `PuenteCredencial` (H-16).
   - Los permisos de §2 paso 4 / §5 (`GlucoLume_permisos.sql` y, aparte, `…_quitar_roles_fijos.sql`).
3. Repetir `schemaCheck` (debe informar «Sin diferencias») y registrar el cambio (fecha, responsable, objetos) en [HISTORIAL.md](HISTORIAL.md).

Mientras tanto el backend tolera la falta de piezas opcionales (1.3). Alternativa: **reconstruir** (base nueva con v5 y migrar los datos).

### 3.1 Ensayo de actualización sin pérdida de datos (23/10/2026)

`evidencias/validacion_integral/actualizacion_sin_perdida.sh`: una base instalada con el v5 de `master` (33 tablas, **2** índices `IX_`/`UX_`, sin `PuenteCredencial`) recibió filas
sintéticas (usuarios, auditoría, dispositivo) y se actualizó con los scripts de esta rama (más la cuenta de la API partiendo de `db_datareader`/`db_datawriter`, como en la base
real). Resultado, **16/16**: conteos y checksums de las tablas con datos idénticos antes y después; columnas, índices (nombre, unicidad y filtro), `CHECK`, claves foráneas y valores
por defecto idénticos a una instalación nueva con el v5 actual; `schemaCheck` dentro del contenedor del backend: «Sin diferencias»; segunda ejecución de cada script sin errores.
Tu base de Windows **no** se usó: si fue creada con los scripts antiguos ya tiene los índices (el script no los duplica).

## 4. Respaldo y restauración

Perfil `db` (SQL Server en contenedor):

```bash
docker compose --profile db exec db /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -Q "BACKUP DATABASE GlucoLume TO DISK='/var/opt/mssql/backup/glucolume.bak' WITH COMPRESSION, CHECKSUM"
docker compose --profile db exec db /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -Q "RESTORE VERIFYONLY FROM DISK='/var/opt/mssql/backup/glucolume.bak' WITH CHECKSUM"
docker compose --profile db cp db:/var/opt/mssql/backup/glucolume.bak ./glucolume.bak        # llevarlo fuera del servidor
# restaurar con la aplicación detenida (docker compose stop backend lifecycle):
docker compose --profile db exec db /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -Q "RESTORE DATABASE GlucoLume FROM DISK='/var/opt/mssql/backup/glucolume.bak' WITH REPLACE"
```

Ensayo en una copia: restaurar el respaldo con otro nombre (`RESTORE DATABASE GlucoLume_Ensayo … WITH MOVE …`, nombres lógicos con
`RESTORE FILELISTONLY`), trabajar ahí y eliminarla al terminar. En una instancia externa, usar sus herramientas de respaldo. Tras restaurar un
respaldo antiguo, correr el job de retención antes de volver a dar acceso ([PRIVACIDAD_Y_RETENCION.md](PRIVACIDAD_Y_RETENCION.md)).

**Implementado para Express (19/10/2026):** `database/respaldos/GlucoLume_respaldo.ps1` (BACKUP con CHECKSUM, `RESTORE VERIFYONLY`,
cifrado AES-256 con GnuPG y verificación SHA-256 del descifrado antes de borrar el `.bak` en claro, retención de 35 días + 12 mensuales que
nunca borra el último ni archivos ajenos), `GlucoLume_clave_respaldo.ps1` (frase de paso aleatoria protegida con DPAPI) y
`GlucoLume_prueba_restauracion.ps1` (descifra, restaura en un SQL Server 2025 descartable, corre `schemaCheck` y borra todo). Carpeta
`C:\GlucoLumeRespaldos` con acceso solo para la cuenta, el servicio `MSSQL$GLUCOLUME`, SYSTEM y Administradores. Ejecutados: respaldo cifrado
verificado y restauración de prueba sin diferencias. Tareas programadas «GlucoLume - Respaldo diario cifrado» (02:30) y «GlucoLume -
Prueba de restauracion» (cada 4 semanas); corren con la sesión de la cuenta iniciada (DPAPI). Falta: BitLocker y la copia de la clave
fuera del equipo (SEGURIDAD §5.1).

**Copia de la base de Docker en Windows (25/10/2026):** la base principal es la del contenedor `glucolume-db-1` (la que usa el backend);
`database/respaldos/GlucoLume_copia_docker.ps1` la replica en `localhost\GLUCOLUME`, base `GlucoLume`, en un solo sentido: `BACKUP … WITH
COPY_ONLY, CHECKSUM` y `RESTORE VERIFYONLY` dentro del contenedor, `docker cp` a `C:\GlucoLumeRespaldos\copia_docker`, `RESTORE … WITH
REPLACE` en Windows y la deja en `READ_ONLY` (lo escrito ahí se perdería en la copia siguiente); el `.bak` en claro se borra siempre. Tarea
programada «GlucoLume - Copia desde Docker» cada 5 minutos, desfasada 2 minutos (…:02, …:07) para no cruzarse con el respaldo diario de
las 02:30, que así respalda lo mismo que hay en Docker. Registro en `C:\GlucoLumeRespaldos\copia_docker.log`. La copia queda hasta 5 minutos
atrás y necesita Docker Desktop abierto; antes de la primera copia se respaldó la base que había en Windows (solo datos de referencia:
`GlucoLume_20261025_200830.bak.gpg`).

**Copia fuera del equipo (H-01, regla 3-2-1):** `GlucoLume_respaldo.ps1 -CopiaExterna <destino>` copia cada respaldo cifrado a otro disco o recurso de
red y verifica su SHA-256 en el destino; es una copia (no un espejo): no borra nada allí, así un equipo comprometido no puede vaciarla. Si solo
falla la copia, el respaldo local queda hecho y el script sale con código 2. Sin `-CopiaExterna` el registro lo deja asentado. La frase de cifrado
**no** viaja con los respaldos: se guarda aparte (gestor de contraseñas o sobre cerrado) con `GlucoLume_clave_respaldo.ps1 -Mostrar`. Cada tres
meses se prueba la restauración **desde la copia externa**: `GlucoLume_prueba_restauracion.ps1 -Archivo <ruta de la copia>`. El destino debería
conservar versiones inmutables (almacenamiento con bloqueo de objetos o disco rotado fuera del equipo). Pendiente de la persona que administra el
servidor: elegir el destino, agregar `-CopiaExterna` a la tarea «GlucoLume - Respaldo diario cifrado» y guardar la frase.

**Instancia instalada (19/10/2026, metadatos):** SQL Server 2025 **Express** 17.0 RTM, modelo de recuperación `SIMPLE`, base sin TDE,
2 respaldos completos registrados (el último del 18/10/2026), ninguno cifrado, ningún certificado de usuario en `master`. Express no admite
TDE, respaldos cifrados ni comprimidos y no tiene SQL Agent. Para esta edición:

1. Cifrado en reposo: BitLocker en los volúmenes de datos, registro y respaldos (sistema operativo).
2. Respaldo: `BACKUP DATABASE … TO DISK = … WITH CHECKSUM, INIT` y `RESTORE VERIFYONLY … WITH CHECKSUM`, programado con el Programador de
   tareas de Windows y `sqlcmd`; cifrar el `.bak` (AES-256) con una herramienta del sistema antes de copiarlo fuera del equipo; la clave se
   guarda aparte.
3. Retención propuesta (a aprobar): diarios 35 días, mensuales 12 meses, aplicada por el script programado.
4. Restauración de prueba mensual en una instancia descartable (contenedor SQL Server Developer sin volúmenes, como en §6): restaurar con otro
   nombre, `python -m app.cli.schemaCheck --url …` y comparar conteos por tabla; borrar la instancia al terminar.

Con una edición Standard o superior:
Cifrado en reposo y respaldos cifrados: `database/reference/GlucoLume_cifrado_y_respaldo.sql` (exige `CONFIRMAR=CIFRAR_Y_RESPALDAR_GLUCOLUME`)
activa TDE (AES-256), exporta los certificados con su clave privada, hace un respaldo comprimido, con `CHECKSUM` y cifrado AES-256, lo
verifica, lo restaura con otro nombre, compara las filas de cada tabla y borra solo la copia. Ensayado el 19/10/2026 en la instancia
descartable: base cifrada (estado 3), respaldo con `encryptor_type = CERTIFICATE`, restauración sin diferencias en las 33 tablas. Sin los
certificados exportados y su contraseña la base y los respaldos son irrecuperables. Política propuesta (a aprobar): completos diarios 35
días, mensuales 12 meses y una restauración de prueba mensual. TDE no existe en SQL Server Express. En la instancia real: **no aplicado**.

## 5. Permisos de la cuenta de la aplicación

v5 **ya no** agrega `glucolume_app` a `db_datareader`/`db_datawriter` ni crea usuarios (H-02). En una base heredada donde la cuenta sí está en esos roles puede modificar y borrar
cualquier tabla, incluida `Auditoria`, hasta aplicar los scripts de permisos (§2 paso 4): `GlucoLume_permisos.sql` concede lectura, alta, cambio y ejecución sobre `dbo` y `DELETE` **solo** en las 14 tablas
que el código borra de verdad (una prueba de la suite lo cruza con los `DELETE` reales), con `DENY UPDATE, DELETE` sobre `Auditoria` y `AuditoriaContexto`, y sin `ALTER`/`CONTROL`;
`GlucoLume_permisos_quitar_roles_fijos.sql` retira los roles fijos (reversible). **Validado el 23/10/2026 en SQL Server 2022 descartable (76/76 comprobaciones y la API real sin errores de permisos); no aplicado a tu instancia.**

| Escritura sobre la auditoría | Quién |
|---|---|
| Alta de eventos (`INSERT`) | API y procesos (`services/audit.py`) |
| Depuración por retención (`DELETE` de eventos vencidos, anular IP/cliente) | Solo `services/auditRetention.py`, en el servicio `lifecycle`, con `DB_JOBS_USER` si está configurada |

Desde el 19/10/2026 la API no modifica ni borra la auditoría (GL-02 y GL-03): una cuenta local vencida sin verificar que dejó eventos queda
como baja anónima (estado `ELIMINADO`, sin datos personales) en lugar de anular `Auditoria.idUsuario`, y una prueba global falla si código de
la aplicación emite `UPDATE`/`DELETE` sobre `Auditoria` o `AuditoriaContexto` fuera de la política de conservación.

Para aplicarlo en tu instancia: primero en una copia restaurada, recorriendo la aplicación y buscando errores 229 en el log; el procedimiento completo y la reversión están en [SEGURIDAD.md](SEGURIDAD.md) §5.1.

## 6. Pruebas sobre SQL Server

La suite corre sobre SQLite con el esquema de los modelos. Las pruebas `*_sqlserver` y de concurrencia necesitan una base **descartable**:
`TEST_SQLSERVER_URL` apuntando a `localhost`/`127.0.0.1` y `TEST_SQLSERVER_CONFIRM=DESCARTABLE`; nunca la base real. Resultados del
16/10/2026 sobre una base aislada: [evidencias/PRUEBAS_CONCURRENCIA_SQLSERVER_2026-10-16.md](evidencias/PRUEBAS_CONCURRENCIA_SQLSERVER_2026-10-16.md).

Ensayo con datos reales (19/10/2026, 23:00): el respaldo de la base real se restauró como `GlucoLume_Ensayo` en un SQL Server 2025
Developer descartable (mismos conteos por tabla que la real). Ahí se probaron la migración de `CHECK`, `GlucoLume_permisos.sql`, el
re-cifrado MFA, la imagen nueva del backend (logins con y sin MFA) y la validación TLS con un certificado propio. Con v5 vigente en ese motor:
67/67 pruebas `*_sqlserver` y carreras del ciclo de vida 30/30 como la cuenta restringida. Los contenedores de ensayo se borran al terminar.

Procedimiento usado el 19/10/2026 (nada del proyecto real):

1. Contenedor propio `mcr.microsoft.com/mssql/server:2022-latest`, `MSSQL_PID=Developer`, **sin volúmenes**, publicado solo en
   `127.0.0.1:14333`, con una contraseña generada para ese contenedor.
2. `CREATE DATABASE GlucoLume_Descartable` y v5 con su `USE` apuntando a esa base (las pruebas rechazan una base llamada `GlucoLume`); logins
   de prueba `glucolume_app` y `glucolume_retencion`.
3. `TEST_SQLSERVER_URL=mssql+pyodbc://sa:<clave>@127.0.0.1:14333/GlucoLume_Descartable?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes`
   y `TEST_SQLSERVER_CONFIRM=DESCARTABLE`; después `GlucoLume_permisos.sql` y `python -m tests.lifecycle_concurrency` como `glucolume_app`.
4. Borrar el contenedor al terminar.

Resultados: 67/67 pruebas `*_sqlserver`; carreras del ciclo de vida 30/30 y bloqueo de fila correcto con la cuenta restringida; permisos:
la API recibe *permission denied* (229) al modificar o borrar `Auditoria`/`AuditoriaContexto` y no puede hacer DDL; la cuenta de conservación
depura (2 contextos anulados, 1 intento anónimo vencido eliminado; la segunda pasada no cambia nada). La conexión del backend con
`Encrypt=yes` rechaza el certificado autofirmado si se verifica y queda cifrada (`encrypt_option = TRUE`) si se confía en él. Estas pruebas
destaparon tres defectos ya corregidos: un `SELECT EXISTS` inválido en SQL Server, el correo de recuperación de plataforma enviado antes del
commit (bloqueaba `TokenCuenta`) y una prueba que corría sobre SQLite en lugar de SQL Server (orden de importación del fixture).

### 6.1 Corrida del 23/10/2026 (versión integrada)

SQL Server 2022 CU16 en Docker (la imagen fijada del proyecto), bases descartables, datos sintéticos: la suite de backend completa con las pruebas `*_sqlserver` activadas —**1983 pasaron, 0 fallaron, 0 omitidas**—,
carreras del ciclo de vida **120/120** con `python -m tests.lifecycle_concurrency --rondas 20`, y los scripts de `database/reference` (76/76), la API real con las cuentas restringidas (51/51), la
actualización sin pérdida (16/16) y los respaldos con PowerShell (33/33): [evidencias/validacion_integral](evidencias/validacion_integral/README.md). Instancia real de Windows: sin tocar.

