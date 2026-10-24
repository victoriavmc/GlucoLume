# Historial técnico

Registro acumulativo de cambios implementados, vulnerabilidades corregidas, decisiones, pruebas y funcionalidades reemplazadas. Lo abierto
está en [PENDIENTES.md](PENDIENTES.md). Se agrega al principio; no se reescribe lo anterior salvo para corregir un error de registro.

## 23/10/2026 — Revisión y optimización del rendimiento (rama `perf/rendimiento-2026-10-23`)

Informe completo con evidencia, causa, solución, métricas y limitaciones: [RENDIMIENTO.md](RENDIMIENTO.md). Scripts y resultados: [evidencias/rendimiento](evidencias/rendimiento/README.md). Rama aparte de `master`
para revisión; no mezcla la remediación de seguridad ya validada. Todo medido con datos sintéticos en una base descartable (`GlucoLume_perf`); la base «GlucoLume» y la instancia real no se tocaron.

- **Corregido (cada uno con su medición antes/después):** (1) tope de llamadas simultáneas al driver ODBC (`DB_MAX_CONCURRENT_CALLS=2`, `app/db/gate.py`): con 8 clientes la API pasaba de ~20 a **4,4 req/s** (p95 7 s) y ahora
  sostiene **28 req/s** (p95 0,75 s); (2) las muestras del sensor se insertan por tandas: 400 muestras pasan de **403 `INSERT`** (211 ms) a **4** (52 ms); (3) condiciones de carrera en pacientes, historial, dispositivos y
  transferencias (una respuesta vieja pisaba a la nueva), con pruebas que fallan con el código anterior; (4) carga diferida por pantalla con precarga de la ruta: JS inicial de 297 a 124–196 KB transferidos y FCP en 3G de 2,2–2,8 s a 1,26–1,70 s;
  (5) esqueletos de carga; (6) Nginx: gzip -9 precomprimido, `Vary`, `robots.txt`, 404 para archivos inexistentes (antes devolvían el HTML con 200) y `X-Robots-Tag` en el área privada.
- **Defecto funcional hallado y corregido (no es de rendimiento):** `notifyGroupMeasurement` usaba `.is_(True)`, que SQL Server recibe como `IS 1` (error 102): el aviso al grupo **nunca se enviaba** y el error quedaba tragado.
  Ahora compara con `=`, con una guarda estática contra `.is_(True/False)`, y el aviso se envía en segundo plano (no demora el cierre de la medición).
- **Descartado con medición:** `useHomeData` (ya paralelo y sin repetidas), endpoints `async` con bloqueo, bucles con `commit` (deliberados), SQL con N+1, caché de datos y *optimistic UI* (no hay acciones seguras que lo justifiquen), SSR/Next.js y prerenderizado de la portada.
  El plugin de íconos directos de `lucide-react` y `experimentalMinChunkSize` se probaron y se retiraron: no mejoraban nada.
- **Sin resolver:** compilación del frontend de ~3 min 20 s (causa localizada en el tree-shaking de Rollup al dibujar `<App/>`, sin solución); dashboards con `TOP 50000`; correo SMTP en línea en la mayoría de los flujos; causa raíz del precipicio de `pyodbc`
  dentro del driver. Ver [PENDIENTES.md](PENDIENTES.md).
- **Pruebas:** backend **1 980 pasaron, 0 fallaron** (13 omitidas por herramientas ausentes en Windows) con las pruebas `*_sqlserver` activadas contra SQL Server 2022 descartable; frontend **700/700** (2 fallas previas eran rutas de Windows). Pruebas nuevas: gate (7), guarda `IS 1` (1), inserción por tandas (2), `useLatestRequest` (3) y 2 de carrera que fallan con el código anterior.
- **Entorno de la sesión:** Docker Desktop estaba apagado; al iniciarlo mostró un aviso del Secrets Engine (`engine.sock` obsoleto sin permiso para renombrarlo) pero el motor arrancó y se pudo trabajar. Se creó el contenedor `glucolume-db-1` con la base completa para uso local (34 tablas, 27 reglas de matriz, permisos de mínimo privilegio).

## 23/10/2026 — Integración final en `master` y stack Docker verificado

PR #2 (rama `claude/vigilant-shannon-legfop`, 0 commits por detrás de `master`, sin conflictos) fusionado con un merge commit de GitHub, sin `force push` y **sin borrar la rama**. La auditoría
**no** se declara aprobada: H-03, H-05 y H-10 siguen abiertos y hay verificaciones pendientes en Windows ([seguridad/VERIFICACIONES_PENDIENTES_WINDOWS.md](seguridad/VERIFICACIONES_PENDIENTES_WINDOWS.md)).

- **Base de datos:** instalación nueva en el contenedor `db` con los scripts oficiales (v5 + `MATRIZ.SQL` + permisos): 34 tablas, 49 FK, 127 `CHECK`, 33 índices `IX_`/`UX_`, 27 reglas de matriz, `PuenteCredencial`. **Defecto encontrado y corregido:**
  `GlucoLume_actualizar_instalada.sql` no restauraba los 31 índices que el v5 de `master` había perdido; ahora los crea de forma idempotente. Ensayo de actualización sin pérdida de datos (16/16).
- **Docker:** `compose.redis.yaml` (Redis opcional, H-06). Stack completo en ejecución (`db`, `backend`, `frontend`, `redis`, y `proxy` Caddy en producción) con healthchecks, redes `edge`/`data`, volumen persistente, sin publicar SQL Server ni Redis, sin `lifecycle`.
  Modo desarrollo 49/49 y producción por HTTPS 50/50. El `backend/Dockerfile` y la etapa `build` del `frontend/Dockerfile` oficiales **no se pudieron construir** en el entorno (red); se usó una imagen de ensayo documentada.
- **Documentación revisada:** `README.md`, `DESPLIEGUE.md` (guía de Windows, Redis, estado real de cada servicio), `BASE_DE_DATOS.md` (instalación, actualización, permisos), `SEGURIDAD.md` (§2.0.3), `PENDIENTES.md` y el checklist de Windows.
  Contradicciones corregidas: v5 ya no crea usuarios ni agrega roles fijos; "todavía no se ensayó" v5; versión de Caddy; cantidad de tablas e índices.

## 23/10/2026 — Validación integral de la remediación (entorno descartable)

Evidencia y scripts: [evidencias/validacion_integral](evidencias/validacion_integral/README.md). Matriz por hallazgo: [SEGURIDAD.md](SEGURIDAD.md) §2.0.2. Pendiente en Windows: [seguridad/VERIFICACIONES_PENDIENTES_WINDOWS.md](seguridad/VERIFICACIONES_PENDIENTES_WINDOWS.md).

- **Qué se hizo:** con Docker, SQL Server 2022 (imagen fijada), Redis 7, Nginx (sistema e imagen fijada), Chromium, PowerShell 7 en Linux, simavr y Trivy, todo **descartable y con datos sintéticos**, se
  validaron H-02/H-16 contra SQL Server real (76/76 y, con la API real y las cuentas restringidas, 51/51), H-06 con dos procesos de la API y Redis real (12/12), H-09 en Chromium con el build de producción
  detrás de la plantilla real de Nginx (24/24), H-14 con Nginx real (20/20 y 23/23), H-01 con los `.ps1` reales (33/33), H-04 por simulación y la concurrencia del ciclo de vida de cuentas en SQL Server (120/120).
- **Defectos reales encontrados y corregidos (un commit cada uno):** (1) H-14: las rutas de la SPA se registraban como `/index.html` en el log de Nginx; ahora la ruta original sin query; (2) `opentelemetry-api`
  1.45.0 → 1.45.1 (CVE-2026-114603, transitiva de FastAPI) con `pip-audit` y Trivy sin hallazgos; (3) la prueba del certificado de SQL Server dependía del sistema operativo.
- **Resuelto como limitación del entorno:** las pruebas que fallaban sin `libodbc` (instalado el ODBC 18) pasan; las cuatro que dependían de `tests/test.env`/`.env` pasan con el sintético.
- **Sigue abierto, sin aceptar:** H-05 (confidencialidad, PIN, placa real), H-10 (zlib y 44 HIGH del sistema base sin corrección publicada, ver Trivy) y H-03 (no tocado).
- **No se pudo:** construir la imagen del backend (`deb.debian.org` bloqueado) ni `npm ci`/`apk upgrade` dentro de Docker; validar nada específico de Windows (DPAPI, Programador de tareas) ni de la placa.

## 23/10/2026 — Remediación del informe de auditoría del 21/10 (H-01 a H-17)

Estado completo por hallazgo en [SEGURIDAD.md](SEGURIDAD.md) §2.0.1. Un commit por hallazgo.

- **Código y configuración:** H-07 (`API_ENV` obligatorio en la imagen), H-08 (`JWT_PREVIOUS_SECRET`), H-11 (límite por IP con sesión), H-12
  (Argon2 fijado), H-13 (HKDF en el HMAC de identificadores), H-14 (Nginx sin query en el log), H-15 (`ErrorBoundary` y 500 auditado),
  H-16 (plazo del token anterior del puente), H-17 (React 19.1.10), H-01 (`-CopiaExterna`), H-04 (advertencia de arranque).
- **Documentado como abierto o pendiente (ningún riesgo fue aceptado en esta remediación):** H-05, H-06, H-09, H-10; acciones humanas: H-01 (destino), H-02, H-03, H-04, H-08.
- **Pruebas:** nuevas en `test_security_config.py`, `test_security_hardening.py`, `test_telemetry.py`, `test_unhandled_errors.py` y
  `ErrorBoundary.test.jsx`; frontend 685/685 con React 19.1.10. La prueba `test_en_produccion_se_verifica_el_certificado_de_sql_server` falla en
  Linux con o sin estos cambios (usa una ruta de Windows).
- **No verificado:** el script de PowerShell (sin PowerShell en el entorno), el `log_format` de Nginx (sin Docker) y el build de producción del frontend.

## 20/10/2026 — Revisión de lo corregido y reglas de negocio

- **Falla encontrada y corregida (retención institucional):** el aislamiento de errores del 19/10 hacía `rollback()` ante un perfil que
  fallaba, pero `anonymizeProfile` no confirma: se deshacían también los perfiles ya anonimizados del mismo lote, que se contaban igual y
  se volvían a procesar (el total y el evento `ANONIMIZAR_PACIENTES` quedaban inflados; los datos terminaban bien). Ahora cada perfil va en
  un punto de guardado (`begin_nested`). La prueba se reescribió con la falla a mitad de lote y después de haber cambiado datos: cuenta 2 de
  3, el que falla queda intacto y el evento registra 2 (con la lógica anterior daba 3). `services/institutionalRetention.py`,
  `tests/test_retention_anonymization.py`: 38/38 en los archivos de retención. El job es manual (`purgeInstitutionalRetention`); la imagen
  del backend desplegada todavía tiene la versión anterior de ese job, que no se ejecuta solo.
- **Revisado sin fallas:** confirmación del correo de resultados (token, zona horaria, idempotencia), límite del puente, códigos cortos,
  envío del enlace de recuperación después del commit, baja anónima de cuentas vencidas, guarda de compilación del frontend.
- **Reglas de negocio en la base real** (15 conteos de solo lectura, todos en 0): un administrador vigente; cuentas de plataforma activas
  con MFA; cuentas eliminadas sin datos personales ni sesiones; correo y usuario únicos; factores MFA confirmados; sin vínculos activos en
  instituciones cerradas; instituciones activas con propietario y dentro de su capacidad; una matriz activa por ámbito; DEMO sin estimación;
  sin correos de resultados vencidos; pacientes depurados sin identificación; una reasignación pendiente por paciente; auditoría válida.
- Frontend completo 683/683 (cambio de `vite.config.js`).

## 20/10/2026 — Protección de auditoría aplicada en la base real (GL-03)

- **Antes:** la cuenta `glucolume_app` tenía `UPDATE` y `DELETE` sobre `Auditoria` y `AuditoriaContexto` (verificado: «permitido»).
- **Cambios en el proyecto:** `GlucoLume_permisos.sql` admite `JOBS_LOGIN=NINGUNA` (con `lifecycle` desactivado no hace falta crear la
  cuenta de conservación ni manejar contraseñas; el rol de conservación queda vacío) y usa SQL dinámico para lo opcional. Nuevos
  `GlucoLume_permisos_revertir.sql` (quita miembros y roles; no toca datos) y `GlucoLume_permisos_verificar.sql` (como `glucolume_app`:
  `INSERT` dentro de una transacción revertida y `UPDATE`/`DELETE TOP (0)`; comprueba que las filas no cambian).
- **Ensayo:** copia restaurada del último respaldo cifrado en SQL Server 2025 descartable: guarda de confirmación, aplicación,
  reaplicación sin cambios, verificación, reversión y nueva aplicación, todo correcto. Contenedor y copia descifrada borrados.
- **Producción:** respaldo previo `GlucoLume_20261020_001111.bak.gpg` (verificado); `sqlcmd -E -C -I` con
  `API_LOGIN=glucolume_app JOBS_LOGIN=NINGUNA CONFIRMAR=APLICAR_PERMISOS_GLUCOLUME`; la API queda con `SELECT` e `INSERT` sobre ambas
  tablas. Reaplicación idempotente.
- **Verificación:** `INSERT` permitido; `UPDATE` y `DELETE` rechazados con el error 229 en `Auditoria` y `AuditoriaContexto`; filas sin
  cambios. Backend en ejecución (sin recrear): login con credenciales incorrectas → 401 y nuevo evento `LOGIN_LOCAL FALLO` (32 → 33
  eventos); ningún error de permisos en sus registros; `schemaCheck` desde el contenedor sin diferencias. Los inicios con Google y MFA
  ya se habían comprobado con la imagen nueva (`LOGIN_GOOGLE_MFA_PENDIENTE` y `LOGIN_GOOGLE_MFA`, 20/10 00:02–00:03).
- **Reversión:** `sqlcmd -S localhost\GLUCOLUME -E -C -I -d GlucoLume -i database
eference\GlucoLume_permisos_revertir.sql -v CONFIRMAR=REVERTIR_PERMISOS_GLUCOLUME`.

## 20/10/2026 — Inicio de sesión con Google roto tras el despliegue

- **Síntoma:** `Not allowed to load local resource: file:///C:/Program%20Files/Git/api/v1/auth/google/login`.
- **Causa comprobada:** la imagen `glucolume/frontend:remediacion` se compiló desde Git Bash con `--build-arg VITE_API_BASE_URL=/`; MSYS
  convirtió `/` en `C:/Program Files/Git/`, que quedó dentro del JavaScript (verificado en la imagen y en el script que sirve
  `http://localhost:8080`). Ese build tampoco recibió `VITE_LOGIN_ORIGIN`/`VITE_APP_ORIGIN`. El backend y Nginx estaban bien:
  `/api/v1/auth/google/login` responde 307 hacia el origen del login.
- **Corrección:** imagen `glucolume/frontend:remediacion2` compilada con `docker compose build frontend` desde PowerShell (toma los orígenes
  del `.env`): base `"/"`, `http://localhost:8080` y `http://glucolume.local` en el bundle, sin rutas de Windows. `vite.config.js` ahora
  rechaza al compilar un `VITE_*` que no sea `/` o una URL http(s) (probado: la ruta de Git corta el build; `/` compila).
- **Pruebas:** bundle inspeccionado dentro de la imagen; contenedor de prueba aislado: `/login` 200 y `/api/v1/auth/google/login` 307.
  **Desplegado** (solo el servicio `frontend`, `docker compose -f compose.yaml up -d --no-deps --no-build frontend`): el script servido en
  `http://localhost:8080` ya no contiene la ruta de Git y «Continuar con Google» lleva a `accounts.google.com` con PKCE (S256), `state`,
  `nonce` y `redirect_uri=http://localhost/api/v1/auth/google/callback`. El backend en ejecución es `backend:remediacion`.
  `remediacion` y `pre-remediacion` se conservan para reversión.

## 19/10/2026 — Ajuste de alcance (TIF) y limpieza del `.env`

- **Alcance:** prototipo académico local. BitLocker y el certificado de servidor de SQL Server pasan a mejoras para una instalación
  productiva ([SEGURIDAD.md](SEGURIDAD.md) §2.0); no bloquean la entrega. En `development` la conexión a SQL Server va cifrada sin verificar el
  certificado; `production` sigue exigiendo la verificación. Comprobado sin conectar a la base: la imagen nueva arranca con el `.env` local
  (`development`, sin certificado fijado, una clave MFA).
- **`.env` (GL-06, GL-10):** se quitaron la `MFA_ENCRYPTION_KEY` de huella `b15fb16d` (no descifraba ningún factor, comprobado en la copia
  restaurada) y `DATABASE_URL` (sin consumidores en el proyecto). Copia cifrada del anterior en `C:\GlucoLumeRespaldos`. Sin rotación de claves.
- **Verificación no destructiva de la protección de auditoría:** `EXECUTE AS USER = 'glucolume_app'` + `UPDATE TOP (0) dbo.Auditoria`
  (no cambia filas). Hoy devuelve «permitido»; tras `GlucoLume_permisos.sql` debe devolver el error 229. `sqlcmd` requiere `-I`
  (`QUOTED_IDENTIFIER ON`) por los índices filtrados.
- Pendiente de ejecución por la usuaria: despliegue de las imágenes `remediacion` y permisos de auditoría (SEGURIDAD §5.1 pasos 1 y 3).

## 19/10/2026 — Remediación con autorización sobre el entorno real

| Problema | Causa | Corrección | Prueba | Estado |
|---|---|---|---|---|
| Respaldo restaurable antes de tocar la base | — | `BACKUP … COPY_ONLY, CHECKSUM` + `RESTORE VERIFYONLY`; restaurado en SQL Server 2025 descartable con conteos idénticos | Restauración real | Hecho |
| 6 `CK_Medicion_*` ausentes en la base real | Base instalada antes de que el modelo las declarara | `GlucoLume_actualizar_instalada.sql` (idempotente, confirmación, transacción) | Copia: 14 casos válidos/inválidos/límite; real: habilitadas y confiables; `schemaCheck` sin diferencias | **Aplicado en producción** |
| 4 filtros de índice sin verificar | La cuenta de la app no tiene `VIEW DEFINITION` | Lectura con la cuenta de Windows `sysadmin` | Los 6 coinciden con modelos y v5 | Verificado |
| Imagen de producción vieja (GL-02 `UPDATE`, sin GL-04/08/11, sin `MultiFernet`) | Imagen del 19/10 05:03 | Imágenes `remediacion` (backend y frontend) | Ensayo: login con y sin MFA, CSP, proxy; la imagen vieja falla con el `DENY` | Validado; **despliegue bloqueado** por permisos de la sesión |
| Auditoría modificable por la API (GL-03) | Sin roles separados | `GlucoLume_permisos.sql` sobre la copia | API: 229 al modificar/borrar; conservación depura; carreras 30/30 como cuenta restringida | Verificado en ensayo; pendiente en producción |
| Dos claves MFA (GL-06) | `.env` duplicado | Diagnóstico y re-cifrado en la copia | La vigente descifra todo, la otra nada | Pendiente: quitar la línea (edición del `.env` bloqueada para la sesión) |
| TLS sin validar el certificado (GL-07) | `TrustServerCertificate=yes`; el driver de Linux ignora `ServerCertificate` | `DB_SERVER_CERTIFICATE` (Windows: fijado con `Encrypt=strict`; Linux: bundle con las autoridades del sistema + el certificado), `DB_CERTIFICATE_HOSTNAME`; producción rechaza `TrustServerCertificate` | Ensayo con certificado propio: correcto conecta; otro certificado o nombre distinto se rechazan; SMTP conserva 151 autoridades | Código verificado; producción requiere certificado (administrador) |
| Respaldos sin cifrar (GL-07, Express) | Express sin cifrado nativo ni Agent | `database/respaldos/` (clave DPAPI, respaldo cifrado AES-256 con retención, restauración de prueba) y dos tareas programadas | Respaldo verificado y restauración sin diferencias | **Aplicado**; BitLocker pendiente (administrador) |

Pruebas: backend completo 1 800 aprobadas, 0 fallidas (67 omitidas, ejecutadas aparte en SQL Server 2025: 67/67); `test_security_config.py`
15/15; logins de ensayo 6/6 (sin MFA, con MFA, código incorrecto, contraseña incorrecta) con TLS validado y `DENY`; frontend de ensayo
(200, CSP estricta, 401 sin token). Frontend sin cambios de código en esta etapa. Reversión del despliegue: imágenes `pre-remediacion`.

## 19/10/2026 — Cierre de verificaciones en la instancia real (solo lectura)

- **`CK_Medicion_*`:** las 6 consultas de conteo (`SELECT COUNT_BIG(*)`, validadas antes de ejecutarlas para que no contengan escrituras)
  dieron 0 violaciones cada una. Las restricciones siguen sin agregarse.
- **Índices:** los 6 existen con las columnas, unicidad y columnas incluidas de los modelos; 2 sin filtro quedan verificados por completo; los
  4 filtrados no se pueden leer sin `VIEW DEFINITION` (la cuenta de la aplicación no lo tiene). Consulta para una cuenta autorizada en
  [BASE_DE_DATOS.md](BASE_DE_DATOS.md) §1.2.1.
- **Imagen del backend en ejecución:** construida el 19/10 a las 05:03 UTC, anterior a las correcciones: conserva el `UPDATE` de GL-02 en
  cada inicio de sesión y el de la limpieza de cuentas vencidas, no tiene `MultiFernet`, `mfaKeys`, la verificación SMTP ni la confirmación
  de GL-08. Aplicar el `DENY` antes de desplegar el código actual rompería el login: el procedimiento de GL-03 empieza por el despliegue.
- **Documentación:** estado por entorno (código, descartable, producción) en [SEGURIDAD.md](SEGURIDAD.md) §2.1; procedimientos de GL-03 y
  GL-06 con su orden y requisitos en §5.1.
- Sin escrituras SQL, sin cambios de permisos, contenedores, `.env` ni claves. No se repitieron las suites (sin cambios de código).

## 19/10/2026 — Verificación de la instancia real (solo lectura)

| Tema | Resultado verificado | Cambio en el proyecto |
|---|---|---|
| Docker | Activo. `glucolume-backend-1` estaba **en ejecución** (iniciado a las 23:58 UTC, con `restart=no`: arranque manual o de Compose, no automático) contra la base real; `frontend` con `unless-stopped`; sin `lifecycle`; único volumen `glucolume_firmware-build` (la base es externa). No se tocó | — |
| GL-06 | Dos `MFA_ENCRYPTION_KEY` válidas y distintas (líneas 42 y 52); prevalece la 52; sin claves anteriores. No se descifró ningún factor | Procedimiento con respaldo y vuelta atrás en SEGURIDAD §5.1 |
| GL-05 | `schemaCheck` sobre la base real: coinciden tablas, columnas, PK, FK e índices; faltan las 6 `CK_Medicion_*`. La base tenía 6 índices ausentes en v5 y en los modelos (únicos de correo y usuario, gracia, auditoría, mediciones) | Índices agregados a los modelos y a v5; `schemaCheck` compara PK e índices de consulta, ignora `sysdiagrams` y prepara consultas de conteo (`--preparar-validacion`) |
| GL-03 | La cuenta de la aplicación tiene `db_datareader`/`db_datawriter` y `UPDATE`/`DELETE` sobre la auditoría; no es `sysadmin`, `db_owner` ni dueña; no existen los roles del script | — (aplicar requiere autorización) |
| GL-07 | SQL Server 2025 Express 17.0 RTM: sin TDE, sin respaldos cifrados ni comprimidos, sin Agent; base sin TDE; último respaldo completo 18/10/2026 sin cifrar; modelo `SIMPLE`; conexión `Encrypt=yes` con `TrustServerCertificate=yes` en desarrollo; el estado TLS de la sesión no es visible sin `VIEW SERVER STATE` | Alternativa para Express en BASE_DE_DATOS §4; el script con TDE queda para Standard o superior |

Pruebas: `test_reference_schema.py` 7/7 (incluye columnas `INCLUDE` y consultas de conteo); suite completa del backend 1 798 aprobadas, 0
fallidas, 67 omitidas (las opcionales de SQL Server: no había instancia descartable; el cambio de v5 se validó con la prueba estática, no en
SQL Server). Frontend sin cambios: no se repitió. Ninguna escritura en SQL Server real; solo vistas del catálogo, funciones de sesión y
`msdb.dbo.backupset` (metadatos de respaldos).

## 19/10/2026 — Remediación final y preparación para una nueva auditoría

### Correcciones

| Problema original | Corrección | Archivos | Prueba | Resultado |
|---|---|---|---|---|
| Los errores de validación de la configuración mostraban el valor recibido (p. ej. `BRIDGE_TOKEN`, `JWT_SECRET`) | `hide_input_in_errors=True`; lectura del `.env` unificada (admite `export`, espacios, comillas) en la herramienta MFA | `core/config.py`, `cli/mfaKeys.py` | `test_security_config.py` (3 nuevas) | Corregido |
| GL-20: un mismo secreto podía repetirse entre variables | En producción no arranca con secretos repetidos ni `SESSION_SECRET` corto; advertencia en desarrollo (solo nombres). El `.env` real no tiene repetidos | `core/config.py` | `test_security_config.py` | Corregido |
| GL-05: v5 no tenía los 25 índices de los modelos (13 únicos filtrados con reglas de negocio) | Agregados a v5 (solo líneas nuevas, UTF-16); la prueba del esquema compara índices; herramienta de solo lectura `python -m app.cli.schemaCheck` | `GlucoLume_DB_v5.sql`, `cli/schemaCheck.py`, `test_reference_schema.py` | Instalación desde cero en SQL Server descartable y `schemaCheck` sin diferencias | Corregido en v5 |
| GL-03: `SELECT EXISTS` de la baja anónima, inválido en SQL Server | Consulta portable | `services/unverifiedAccounts.py` | Prueba nueva en `test_platform_sqlserver.py` | Corregido |
| Recuperación de contraseña de plataforma: correo SMTP síncrono antes del commit (bloqueaba `TokenCuenta`; enlace posiblemente no guardado) | Confirmar y después enviar | `services/platform.py` | `test_platform_recovery.py` y las pruebas de SQL Server que se colgaban | Corregido |
| `test_platform_sqlserver.py` corría sobre SQLite (orden de importación del fixture) | Import reordenado | `tests/test_platform_sqlserver.py` | Ahora corre sobre SQL Server | Corregido |
| GL-15: alertas solo pasivas | Correo al administrador de la plataforma ante una ráfaga (una por patrón y hora, sin IP, `SECURITY_ALERT_EMAIL_MINUTES`) | `services/securityMonitor.py`, `emails/plataforma/alertaSeguridad.html` | `test_audit_security.py` | Corregido (parcial del hallazgo) |
| Retención institucional: un perfil que fallaba frenaba a todos | Se registra, se omite y se reintenta en la próxima pasada | `services/institutionalRetention.py` | `test_retention_anonymization.py` | Corregido |
| GL-13: imágenes por etiqueta; Node 22.12 y Caddy 2.9 con vulnerabilidades | Digests en todos los `FROM` y en Caddy; Node 22.23 (build), Caddy 2.11 | `backend/Dockerfile`, `frontend/Dockerfile`, `docker/*/Dockerfile`, `compose.prod.yaml` | Builds, `nginx -t`, `caddy validate`, Docker Scout | Corregido; 1 alta de `zlib` sin parche en el backend |
| GL-07: sin procedimiento de cifrado ni respaldo | `GlucoLume_cifrado_y_respaldo.sql` (TDE, respaldo cifrado, restauración de prueba) | `database/reference/` | Ensayado en descartable | Preparado; no aplicado en la real |
| Frontend: bundle de 953 kB | Carga diferida de grupos, transferencias, reasignaciones, actividad y ficha del personal | `frontend/src/App.jsx` | Pruebas de grupos e instituciones y build | 887 kB |

### Validaciones en SQL Server descartable

Contenedor SQL Server 2022 Developer propio, sin volúmenes, solo en `127.0.0.1:14333`, credenciales generadas para él (procedimiento en
[BASE_DE_DATOS.md](BASE_DE_DATOS.md) §6): v5 desde cero (33 tablas, 49 FK, 125 `CHECK`), `MATRIZ.SQL` (1 matriz, 27 reglas), 67/67 pruebas
`*_sqlserver`, carreras del ciclo de vida 30/30 con la cuenta restringida, permisos de `GlucoLume_permisos.sql` (la API recibe 229 al
modificar o borrar la auditoría y no hace DDL; la conservación depura y es idempotente), TLS (certificado no confiable rechazado; sesión
cifrada), TDE + respaldo AES-256 + restauración sin diferencias.

### Incidente operativo

Al iniciar Docker Desktop, `glucolume-backend-1` se levantó solo (`restart: unless-stopped`) con el `.env` real durante 52 s: respondió dos
`healthz` y corrió una pasada de mantenimiento, que no registró cambios ni errores. Se detuvo y se le quitó el reinicio automático
(`docker update --restart=no`). No se levantó `lifecycle`.

### Pruebas

- **Backend completo:** 1 796 aprobadas, 1 fallida, 67 omitidas. La fallida era el validador nuevo detectando dos valores ficticios iguales en
  `tests/test.env`; se cambiaron esos valores de prueba y su archivo pasó (38/38). Las 67 omitidas son las pruebas opcionales de SQL Server,
  ejecutadas aparte contra la instancia descartable: 67/67.
- **Frontend completo:** 683/683 (50 archivos).
- **Escáneres:** `pip-audit` y `npm audit` sin vulnerabilidades; Docker Scout: imagen final del frontend sin altas ni críticas, backend con
  1 alta de `zlib` sin corrección publicada.
- **Secretos:** ningún valor del `.env` real ni de las credenciales descartables aparece en archivos del proyecto (solo
  `acquisition/bridge/bridge.env`, que guarda el token del puente por diseño y está ignorado por Git).
- **No ejecutado:** nada sobre la base real, el `.env` real ni la instancia real; Arduino y Bluetooth reales; SMTP real.

## 19/10/2026 — Remediación de pendientes, seguridad y calidad

### Seguridad

| Hallazgo | Cambio | Prueba |
|---|---|---|
| GL-04 | STARTTLS con `ssl.create_default_context()` (certificado y nombre, TLS ≥ 1.2) | `test_security_config.py` (SMTP simulado) |
| GL-06 | `MultiFernet` con `MFA_PREVIOUS_ENCRYPTION_KEYS`; `python -m app.cli.mfaKeys` informa por huella qué clave descifra los factores y `--reencriptar --confirmo-base` re-cifra; advertencias de configuración sin valores. No se tocó el `.env` ni la base | `test_security_config.py` |
| GL-23 | Política 1.1: la IP y el resumen del navegador se guardan 90 días; sin nueva aceptación forzada | Revisión del texto y `POLICY_VERSION` |
| GL-08 | Confirmación del destinatario: cargar el correo del paciente o enviar a una dirección no confirmada dispara un enlace firmado (72 h); se guarda o se envía recién al confirmar con un botón en `/confirmar-correo-resultados`. Sin columnas nuevas | `test_patient_result_email.py`, `test_result_email*.py`, `test_emails.py`, `ConfirmResultEmailPage.test.jsx` |
| GL-03 | La API ya no modifica la auditoría: una cuenta vencida sin verificar con eventos queda como baja anónima (antes se anulaba `Auditoria.idUsuario`). Cuenta de base `DB_JOBS_USER` para `lifecycle` y jobs, oculta a la API en Compose. `GlucoLume_permisos.sql` preparado (no aplicado) | Guardián global en `conftest.py` (falla si `app/` emite `UPDATE`/`DELETE` sobre la auditoría), `test_platform_reinvite.py`, `test_security_config.py` |
| GL-07 | `Encrypt=yes` explícito en la conexión | — |
| GL-11 | Bloqueo por IP tras 20 tokens del puente fallidos en 10 min; límite en `/bridge/check`; `BRIDGE_PREVIOUS_TOKEN` para rotar | `test_telemetry.py` |
| GL-12 | Las pruebas cargan `backend/tests/test.env` (`GLUCOLUME_ENV_FILE`) | `test_security_config.py` |
| GL-13 | `pip-audit` (requirements y dev) y `npm audit`: 0 vulnerabilidades conocidas | Escaneo del 19/10 |
| GL-17 | HMAC de códigos cortos con clave derivada (HKDF); el cálculo anterior se acepta mientras vencen los códigos emitidos | `test_security_config.py`, `test_mfa_recovery.py` |
| GL-18 | `FORWARDED_ALLOW_IPS=127.0.0.1` en `compose.dev.yaml` | `test_security_hardening.py` |
| GL-19 | CSP de Nginx con `style-src 'self'` (sin `'unsafe-inline'`) y `object-src 'none'` | Build y galería servidos con esa CSP en el navegador: estilos por CSSOM aplicados, `<style>` y atributos inyectados bloqueados; `test_security_hardening.py` |
| GL-21 | `BorrarRap.sql` exige `BASE` y `CONFIRMAR_BORRADO` iguales a la base conectada | `test_security_hardening.py` (estático) |
| Retención | `purgeInstitutionalRetention` exige `--confirmo-base <DB_NAME>` | `test_retention_anonymization.py` |

### Base de datos y backend

- Las 6 `CK_Medicion_*` de glucosa del dispositivo se agregaron a `GlucoLume_DB_v5.sql` (UTF-16, solo líneas nuevas). La prueba del esquema
  ya no tiene diferencias registradas y compara además los valores, columnas y números de cada `CHECK` (125). No se ejecutó sobre SQL Server.
- `schemaCompat`: un «sí» se vuelve a comprobar a los 10 minutos (antes, hasta reiniciar).
- Referencias a `database/scripts/NNN` retiradas del código, los mensajes al usuario (auditoría, plataforma, telemetría) y la interfaz.

### Decisiones funcionales

- **Descartado — desbloqueo manual de cuentas:** se quitó el permiso `DESBLOQUEAR_CUENTAS` (no tenía endpoint); el bloqueo vence solo.
- **Descartado — restauración de instituciones eliminadas administrativamente:** la eliminación es definitiva (el propietario tampoco reabre).
- **Verificado y cerrado — reasignación masiva:** asignación directa con aceptación implícita, solo propietario o moderador, una transacción,
  `ASIGNAR_RESPONSABLE_PACIENTE` por paciente y aviso al operador nuevo (10 pruebas).
- **Verificado, sin implementar — purga de nombres en `Auditoria.detalle`:** se ocultan al leer; no hay plazo aprobado y una purga física
  modificaría la auditoría.
- **Se mantienen pendientes:** estimador del servidor, suscripciones y pagos, exportaciones (nueva prueba de arquitectura que exige
  `auditedExport`) e interfaz de retención (la creación de una institución ya informa consentimiento y conservación).

### Frontend

- Página pública de confirmación del correo de resultados y textos de la ficha del paciente.
- Carga diferida de plataforma, matrices, auditoría, dispositivos y analítica: bundle inicial de 1 137 kB a 953 kB.
- Se quitaron 4 funciones del cliente de API sin uso (`listPorts`, `getIndicators`, `getEffectiveMatrix`, `getOwnStatistics`).
- Aviso de privacidad y conservación al crear una institución.

### Pruebas

- **Suites completas (después de todos los cambios):** backend 1 787 aprobadas, 65 omitidas (SQL Server y scripts manuales), 0 fallidas;
  frontend 683/683 (50 archivos). Una corrida del frontend en paralelo con la del backend falló una vez en `Groups.test.jsx` por una carrera
  de tiempos de la propia prueba (pasa aislada); se endureció la espera y la corrida final pasó completa.
- **No ejecutado:** nada sobre SQL Server (v5 con las restricciones nuevas, `GlucoLume_permisos.sql`, `BorrarRap.sql`), envío SMTP real,
  Arduino real ni contenedores (Docker apagado). La base real, el `.env` real y `Glucolume-web` no se tocaron.

## 19/10/2026

### Decisiones

- **DEC-01 — Dispositivo compartido.** El único equipo experimental lo usan cuentas individuales, familiares y operadores de cualquier
  institución con `ALLOW_INDIVIDUAL_ON_INSTITUTIONAL_DEVICE=true`; con `false` rige la asignación. Compartir el hardware no comparte mediciones,
  datos ni el control de una sesión ajena. Reemplaza al «interruptor transitorio» que solo abría el equipo a cuentas individuales y a la regla
  del 17/10 (bloque 3) que reservaba las órdenes al operador de la institución titular. Detalle:
  [DISPOSITIVOS_Y_ADQUISICION.md](DISPOSITIVOS_Y_ADQUISICION.md) §2.
- **DEC-02 — Esquema SQL consolidado.** `database/reference/GlucoLume_DB_v5.sql` es la única referencia para instalaciones nuevas; se retiraron
  los scripts `001`–`034` y los esquemas `v1`–`v3`. Detalle: [BASE_DE_DATOS.md](BASE_DE_DATOS.md) §1.

### Cambios implementados

| Tema | Cambio | Archivos |
|---|---|---|
| Control temporal del dispositivo (GL-01, GL-22) | «Usar dispositivo» / «Dejar de usar» (`POST`/`DELETE /acquisition/telemetry/control`), atómico; lecturas y PPG solo para quien controla; órdenes solo con el control (una orden no lo toma); vencimiento sin medición a 5 min (30 s sin consultar); la medición activa no vence por eso; auditoría `TOMAR_CONTROL_DISPOSITIVO` / `SOLTAR_CONTROL_DISPOSITIVO` | `backend/app/acquisition/telemetry.py`, `services/telemetry.py`, `api/v1/telemetry.py`, `schemas/acquisition.py`, `services/auditQuery.py` |
| Modo compartido entre instituciones (DEC-01) | `device.sharedDeviceMode()`; en modo compartido la asignación y el responsable no restringen el uso; operadores de otra institución confirman y usan el equipo sin vincularlo; la pausa de la institución titular no bloquea a las demás cuentas | `services/device.py`, `services/measurement.py`, `services/deviceConnection.py`, `services/telemetry.py` |
| Diagnóstico sin valores | `readiness` usa `hub.diagnosticReading()` (antigüedad y dedo); el estado expone `controlPropio` y `edadUltimaLectura` | `acquisition/telemetry.py`, `services/telemetry.py` |
| Frontend del control | Botones «Usar dispositivo» / «Dejar de usar» en la configuración del puente; diagnóstico con `edadUltimaLectura` | `frontend/src/api/acquisitionApi.js`, `pages/Account/acquisition/{BridgeSettings.jsx,connectModel.js,useDeviceReadiness.js}` |
| Auditoría de solo inserción (GL-02) | `Auditoria.tipoCuentaActor` se escribe en el mismo INSERT (columna diferida, `FetchedValue`, `eager_defaults=False`); se eliminó el `UPDATE` posterior del listener `after_insert` | `backend/app/models/audit.py`, `services/audit.py` |
| Pruebas aisladas del `.env` | Fixture `deviceMode` (modo restringido por defecto) y `referenceSchema` | `backend/tests/conftest.py` |
| Pruebas del esquema (DEC-02) | Las 4 pruebas que leían scripts retirados validan las mismas reglas en v5; prueba nueva de cobertura modelo↔v5 con 6 diferencias registradas | `test_auth_access_account_type.py`, `test_platform_institution_deletion.py`, `test_quota.py`, `test_google_exchange.py`, `test_reference_schema.py` |
| Pruebas de DEC-01 | Cinco pruebas existentes pasan a ser de modo restringido explícito; pruebas nuevas de modo compartido, control, vencimientos, concurrencia, stream y pausa | `test_device_context_authority.py`, `test_device_control.py` y ajustes en `test_bridge_command_authority.py`, `test_bridge_diagnostics.py`, `test_bridge.py`, `test_telemetry.py`, `test_device_connection.py`, `test_measurements.py`, `test_account_deletion.py`, `frontend/.../ConnectDevice.test.jsx` |
| Documentación | Consolidación de 33 documentos y el README en esta estructura (`docs/`); se corrigieron las contradicciones listadas abajo | `README.md`, `docs/` |

### Contradicciones resueltas en la documentación

- Referencias a scripts `NNN` y a `v1`–`v3` como requisito de instalación → esquema v5 (DEC-02).
- «Vincular el equipo lo quita a las cuentas individuales» → solo en modo restringido (DEC-01).
- «El correo del paciente no se guarda» → se guarda 12 meses cuando se carga para envíos automáticos; el envío puntual no lo guarda.
- «Ingresar con Google crea la cuenta» → el inicio de sesión no crea cuentas; el registro con Google es un flujo aparte.
- «La IP y el navegador no se guardan» → la auditoría los conserva 90 días (la política todavía lo contradice: GL-23).
- «034 borrador no aplicado» → su columna está en v5; el estado de la base instalada no se verificó (GL-05).

### Auditoría y pruebas

- **Auditoría de ciberseguridad** (GL-01 a GL-21, dictamen condicionado):
  [seguridad/auditorias/AUDITORIA_CIBERSEGURIDAD_GLUCOLUME.pdf](seguridad/auditorias/AUDITORIA_CIBERSEGURIDAD_GLUCOLUME.pdf). Estado actualizado
  de cada hallazgo: [SEGURIDAD.md](SEGURIDAD.md) §2.
- **Docker:** imágenes construidas; backend y frontend sanos. Pruebas en vivo: 401 sin token, 403 del puente sin token, CORS sin
  `Access-Control-Allow-Origin` para un origen ajeno, contenedores sin privilegios, cabeceras de Nginx. Después se detuvo el backend para no
  operar sobre la base real; `lifecycle` no se levantó.
- **Suite completa antes de los cambios:** backend 1 739 aprobadas, 65 omitidas, 9 fallidas (5 por el `.env` con el modo compartido y 4 por
  scripts retirados); frontend 677/677.
- **Después de los cambios (pruebas dirigidas):** 542 + 350 aprobadas en los módulos de dispositivos, telemetría, autenticación, auditoría y
  esquema (incluidos los 9 que fallaban); 138 de auditoría; 24 de control y contexto del dispositivo; frontend 123/123 en adquisición,
  mediciones y API. Las suites completas no se repitieron.
- **No ejecutado:** pruebas contra SQL Server y aplicación de v5 en una base descartable (no hay una disponible).

## 18/10/2026

- **Módulo de auditoría administrativa:** tres ámbitos (plataforma, instituciones, cuentas), registro de accesos fallidos con motivo
  normalizado (cuenta inexistente solo como HMAC, inactiva, sin verificar, bloqueos, segundo factor, límites, ráfagas), tabla
  `AuditoriaContexto` (correlación, IP, cliente, motivo), clasificación (informativo, error operativo, sospechoso, control activado), señales
  con umbrales configurables, punto único de exportaciones, ficha de cuenta, política de conservación (IP 90 días, anónimos 12 meses).
  Interfaz con colores semánticos. 76 pruebas de backend y 19 de frontend nuevas.
- **Accesos del dashboard por tipo de cuenta** (individual, institucional, plataforma, sin clasificar) y el registro del tipo en el evento.
- **Eliminación administrativa de instituciones:** se eligió la opción B (columnas en `Institucion`) frente a deducirlo de la auditoría (podía
  depurarse) o crear un estado nuevo (más invasivo). Implementada como definitiva y reutilizando el período de gracia.
- **Retención y anonimización de pacientes** (cohorte anónima, 12 meses desde la última medición, documento único por institución).
- **Correo de resultados del paciente** con autorización y vencimiento a 12 meses; envío automático al guardar.
- Suite completa: backend 1 658 aprobadas, 65 omitidas, 8 fallidas (dispositivos por el `.env`, scripts borrados y una de rutas públicas);
  frontend 665/665.

## 17/10/2026

### Bloques de corrección (optimización y seguridad)

| Bloque | Corrección | Regresión |
|---|---|---|
| 1 (P0) | Dashboards sin fuga de salud: series diarias con mínimo de 5 pacientes; el operador ve valores solo de pacientes a cargo hoy. Higiene de pruebas: `test_email.py` y `test_connection.py` fuera de la recolección; SMTP bloqueado en todas las pruebas | `test_dashboard_privacy.py` |
| 2 (P1) | Streams SSE que agotaban el pool: sesión de base liberada, tope de 6 por cuenta y 300 en total, revalidación cada 30 s | `test_stream_limits.py` |
| 3 (P1) | Órdenes al puente reservadas al operador de la institución titular (**reemplazado el 19/10 por DEC-01 y el control temporal**). Se anotó como mejora que las lecturas en vivo eran visibles para cualquier cuenta que mide (resuelto el 19/10, GL-22) | `test_bridge_command_authority.py` |
| 4 (P1) | Contador de intentos MFA atómico; limitador de IP con purga acotada, tope de claves e IPv6 por /64 | `test_mfa_attempts_atomic.py`, `test_rate_limiter.py` |
| 5 | `/devices/resolve` sin permiso de edición; períodos tras reabrir una institución; MFA al reactivar un moderador; purga de re-invitados; validación de puertos en `/acquisition/connect`; prueba intermitente corregida | `test_device_resolve_authority.py`, `test_reopen_period_views.py`, `test_platform_reinvite.py`, `test_acquisition_port_validation.py` |
| 6 | Reasignación por la gestión como propuesta que acepta el destino (antes unilateral), aviso al propietario con marca, auditoría del propietario sin identificar al paciente en eventos de medición | `test_manager_reassignment.py` |
| 7 | `getDevice` sin registrante ni uso de la institución anterior; auditoría sin nombres de personal minimizado (supresión al leer) | `test_devices.py`, `test_audit_minimized_names.py` |

Validación: suite completa del backend 1 398 aprobadas, 0 fallidas, 37 omitidas. Una corrida externa de auditoría automatizada quedó incompleta
y sus candidatos se trataron como pistas, cada uno confirmado con una prueba.

### Otros

- Verificado en una base descartable que el esquema `v3` equivalía a `v2` + `001`–`029` (reemplazado por v5 el 19/10).
- Firmware compilado con Arduino CLI (ambos sketches); no se cargó en una placa.
- **Modernización visual del frontend:** tokens y accesibilidad base (contraste 251 → 0 fallos, «Saltar al contenido»), componentes
  compartidos (`Tabs`, `Modal`, `Badge`, `EmptyState`, `PageHeader`, campos), migración por módulos (acceso, inicio y mediciones, institución,
  dispositivos y matrices, grupo, auditoría y plataforma), limpieza aprobada (101 reglas CSS y 7 exports sin uso; CSS 154,2 → 143,8 kB),
  revisión de encabezados, controles y texto pequeño, y rediseño del dashboard del paciente. Vitest 600/600 al cierre de la migración. Se
  validó con capturas de 243 vistas y métricas de accesibilidad hechas con herramientas externas al repositorio.

## 16/10/2026

- **Auditoría de 20 controles previa al despliegue:** sin hallazgos P0. Corregidos H-01 (IP del cliente falsificable detrás de Nginx), H-02
  (sin límite por IP en endpoints públicos), H-03 (reenvío de verificación sin cooldown y con enumeración), H-04 (Swagger en producción) y
  H-05 (cabeceras incompletas). Nuevos `api/rateLimit.py`, `api/securityHeaders.py`, `tests/test_security_hardening.py` (24 pruebas) y
  `tests/conftest.py`. Suite: 1 335 aprobadas, 1 fallida preexistente; frontend 556; `pip-audit` y `npm audit` sin vulnerabilidades.
- **Ciclo de vida de cuentas institucionales:** período de gracia de 30 días y eliminación automática por el servicio `lifecycle` (activo desde
  esta fecha en la base de desarrollo).
- **Pruebas de concurrencia en SQL Server** sobre una base aislada: 480/480 y 560/560 comprobaciones; se corrigieron una carrera lógica y un
  *deadlock* real con reintento ([evidencias/PRUEBAS_CONCURRENCIA_SQLSERVER_2026-10-16.md](evidencias/PRUEBAS_CONCURRENCIA_SQLSERVER_2026-10-16.md)).

## 13/10/2026

- Pruebas operativas del puente en Windows (enumeración de puertos, instalación con hashes, ACL de `bridge.env`, instancia única, 409 y 403 del
  backend real).
- Consentimientos (`POLITICA_PRIVACIDAD`, `DATOS_EXPERIMENTALES`) y documento de privacidad.

## 10/10/2026

- Contenerización con Docker Compose (servicios, redes `edge`/`data`, perfiles `db`, `https`, `firmware`).
- Escaneo de imágenes: de 8/35, 19/65, 33/158 y 0/3 críticas/altas a 0/1, 0/0, 0/1 y 0/0 (backend, frontend, firmware, SQL Server); queda
  aceptada `zlib` CVE-2026-85091 ([evidencias/CVE_LINEA_BASE_2026-10-10.md](evidencias/CVE_LINEA_BASE_2026-10-10.md)).

## Funcionalidades reemplazadas

| Antes | Ahora | Desde |
|---|---|---|
| Scripts incrementales `001`–`034` y esquemas `v1`–`v3` | Esquema único v5 | 19/10/2026 |
| Interruptor transitorio solo para cuentas individuales | Modo compartido para todas las cuentas habilitadas (DEC-01) | 19/10/2026 |
| Órdenes al puente según la institución titular; cualquier orden sin control | Control temporal explícito | 19/10/2026 |
| `UPDATE` de `tipoCuentaActor` tras el INSERT | Valor en el mismo INSERT | 19/10/2026 |
| Reasignación unilateral por la gestión | Propuesta que acepta el destino | 17/10/2026 |
| Cuenta institucional sin plazo y sin eliminación automática | Período de gracia de 30 días | 16/10/2026 |
| Sketch de muestras crudas en el repositorio | Retirado; contrato conservado como antecedente | antes del 16/10/2026 |
