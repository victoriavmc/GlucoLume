# Verificaciones de la remediación (informe del 21/10/2026): qué se verificó, dónde y qué sigue pendiente en Windows

Actualizado el 23/10/2026 tras la validación integral y la integración final (sección 7). La rama `claude/vigilant-shannon-legfop` se desarrolló en un contenedor Linux sin tu `.env`, sin Windows y
sin la base real. En esa validación **sí hubo** SQL Server 2022 real (Docker), Redis, Nginx, Chromium, PowerShell 7 y un escáner de vulnerabilidades, todos
**descartables y con datos sintéticos**; los resultados y su evidencia están en [../evidencias/validacion_integral/](../evidencias/validacion_integral/README.md).
El informe **no debe clasificarse como aprobado**: queda lo de la sección 8, que no puede sustituirse con una simulación.

Leyenda de cada fila: **✔ verificado** (entorno, resultado, evidencia) · **☐ pendiente en tu equipo** (solo lo que exige Windows, hardware, credenciales o decisión tuya).

Entorno de la validación: Ubuntu 24.04, Python 3.14, controlador ODBC 18 (18.7.1.1), SQL Server 2022 CU16 (la imagen fijada por el proyecto, con Docker 29.9),
Redis 7, Nginx 1.24 (sistema) y 1.30.6 (imagen fijada), Chromium 1194 (Playwright), PowerShell 7.6.8 (Linux), Node 22, simavr/avr-gcc.

## 1. Las seis pruebas del backend que estaban sin confirmar

Corrida completa del backend sobre el último commit, con las pruebas opcionales de SQL Server **activadas** contra una base descartable: **1983 pasaron, 0 fallaron, 0 omitidas**
(frontend: 695/695). Detalle: [resultados/](../evidencias/validacion_integral/resultados/).

| # | Prueba | Antes | Ahora (Linux, con ODBC y SQL Server descartable) | En Windows |
|---|---|---|---|---|
| 1 | `test_security_config::test_en_produccion_se_verifica_el_certificado_de_sql_server` | Fallaba: ruta `/certs/sql.crt` y rama de Linux | ✔ **Corregida** (la prueba fija la rama de Windows; la de Linux tiene la suya) y pasa | ☐ confirmar |
| 2 | `test_patient_access::test_la_api_directa_sin_autenticacion_es_rechazada` | Fallaba: sin `libodbc.so.2` | ✔ **Pasa** con el controlador ODBC 18 instalado (era una limitación del entorno) | ☐ confirmar |
| 3 | `test_reference_schema::test_los_indices_de_los_modelos_estan_en_el_esquema_con_el_mismo_filtro` | Fallaba | ✔ **Defecto real, corregido**: v5 había perdido sus 31 índices. Además v5 carga en SQL Server 2022 real y los índices existen (33 `IX_*`/`UX_*`) | ☐ confirmar |
| 4 | `test_register_contact::test_confirmacion_from_es_la_cuenta_smtp` | Fallaba | ✔ Pasa con un `tests/test.env` sintético; **depende de tu `.env` local** (no versionado) | ☐ confirmar con tu `.env` |
| 5 | `test_register_contact::test_mensaje_from_es_la_cuenta_smtp_y_reply_to_el_usuario` | Fallaba | ✔ Ídem | ☐ confirmar con tu `.env` |
| 6 | `test_stream_limits::test_los_streams_no_retienen_conexiones_del_pool[…/telemetry/stream]` | Fallaba | ✔ **Pasa** (necesitaba el motor de base: ODBC) | ☐ confirmar |

Las tres filas «confirmar con tu `.env`» y las de Windows son una repetición barata (`python -m pytest -q` con el ODBC de Windows); ya no esconden fallas conocidas.

## 2. Respaldos (H-01) — `database/respaldos/*.ps1`

**✔ Verificado** con **PowerShell 7.6.8 en Linux** ejecutando los scripts reales **sin modificarlos** contra un SQL Server 2022 real (Docker) con la base v5 y datos
sintéticos: [powershell_respaldos.txt](../evidencias/validacion_integral/resultados/powershell_respaldos.txt) (**33/33**). Script: `docs/evidencias/validacion_integral/powershell_respaldos.sh`.

| Ítem original | Resultado verificado |
|---|---|
| 1. `-CopiaExterna` | ✔ salida 0; respaldo local cifrado (OpenPGP AES-256) y **sin `.bak` en claro**; la copia externa es idéntica (SHA-256); `respaldo.log` dice «Copia externa verificada»; el contenido no es legible en el archivo cifrado |
| 2. Falla de la copia | ✔ destino inexistente: el respaldo local queda hecho, se aplica la retención y **sale con código 2**; el error queda en el log |
| 3. Sin `-CopiaExterna` | ✔ salida 0 y aviso de la regla 3-2-1 incompleta |
| 4. Restauración desde la copia | ✔ `GlucoLume_prueba_restauracion.ps1` descifra, restaura en un SQL Server descartable (34 tablas) y `schemaCheck` informa «Sin diferencias»; no deja contenedor ni `.bak` descifrado; un respaldo corrupto falla con código 1 |
| 5. Sintaxis | ✔ los tres scripts compilan como `scriptblock` |
| Retención | ✔ conserva los diarios recientes y uno por mes dentro de 12 meses, borra el segundo del mes y lo más viejo, **nunca el último** y no toca archivos ajenos o fuera del patrón |
| 6. Destino definitivo, tarea programada, frase fuera del equipo | ☐ **acción tuya** |

☐ **Sigue pendiente en Windows (no sustituible):** PowerShell en Linux no tiene DPAPI (la «protección» de la clave es solo texto codificado y
`[Marshal]::PtrToStringAuto` lee la frase truncada), por lo que **no se validó** la protección de la clave por cuenta de Windows, `sqlcmd.exe -E`, la ruta
`C:\Program Files\Git\usr\bin\gpg.exe`, ni el Programador de tareas. Repetir en Windows los ítems 1–4 con una base y un destino de prueba, y comprobar con
`-Mostrar` que la frase se recupera íntegra.

## 3. Configuración de Nginx (H-14) — `docker/nginx/default.conf.template`

**✔ Verificado con Nginx real**, de dos formas: el nginx del sistema (1.24, plantilla procesada con `envsubst`) y la **imagen fijada por digest** `nginx-unprivileged:1.30-alpine-slim`
(1.30.6) con la plantilla real, ambas delante de la API sintética: [nginx_sistema_1.24.txt](../evidencias/validacion_integral/resultados/nginx_sistema_1.24.txt) (20/20) y
[nginx_imagen_1.30.6.txt](../evidencias/validacion_integral/resultados/nginx_imagen_1.30.6.txt) (**23/23**).

| Ítem original | Resultado |
|---|---|
| 1. Nginx arranca sin errores de configuración | ✔ `nginx -t` correcto dentro de la imagen; contenedor `healthy` (HEALTHCHECK de la imagen); proceso con uid 101 (sin privilegios) |
| 2. Enlaces con token | ✔ `/verificar-correo?token=…`, `/restablecer?token=…` y `/api/v1/auth/verify-email?token=…` no dejan ningún token en el log. **Se encontró y corrigió un defecto**: las rutas de la SPA salían como `/index.html` (`$uri` reescrita por `try_files`); ahora se registra la ruta original sin query |
| 3. Logs útiles | ✔ IP real, método, ruta, estado y `rid=` |
| Extra | ✔ CSP estricta (`style-src 'self'`, sin `unsafe-inline`), HSTS solo con proxy de confianza, `X-Forwarded-For` no falsificable desde un cliente no confiable, `server_tokens off`, 429 de Nginx en `/api/v1/auth/` (160 de 220 en una ráfaga), la cookie `HttpOnly` y los encabezados anti-CSRF atraviesan el proxy |

☐ **Pendiente:** el Nginx de **tu** `compose.yaml` con el perfil `https` (Caddy), el dominio y el certificado reales, y confirmar que `FRONTEND_TRUSTED_PROXY_CIDR` coincide con la red de tu proxy.

## 4. Build de producción del frontend (H-15, H-17)

| Ítem original | Resultado |
|---|---|
| 1. `npm ci && npm test` | ✔ `npm test` **695/695** (52 archivos) sobre el último commit. `npm ci` dentro de Docker falló en el entorno (npm termina con «Exit handler never called» tras el proxy de salida); en el host se usó el `node_modules` existente |
| 2. `npm run build` con `VITE_API_BASE_URL` | ✔ **Termina sin errores** (4–6 min en el entorno; antes no terminaba dentro del límite de tiempo); con `VITE_API_BASE_URL=/` (mismo origen) y con una URL absoluta |
| 3. Imagen y navegador | ✔ imagen de runtime armada con la base fijada + plantilla + el build de producción: 0 vulnerabilidades, 0 secretos (Trivy); en **Chromium real** el build detrás de ese Nginx carga `/`, `/login`, `/registro` y rutas inexistentes con **0 violaciones de CSP**; `ErrorBoundary` cubierto por su prueba (Vitest) |
| 4. `npm audit` / escaneo | ✔ `npm audit` 0 (producción y desarrollo); Trivy sobre `package-lock.json` 0 |

☐ **Pendiente:** `docker compose build frontend` **completo** en tu equipo (en el entorno de desarrollo `apk upgrade` necesita `dl-cdn.alpinelinux.org`, bloqueado, y `npm ci` falla dentro del contenedor tras el proxy de salida; la etapa de runtime se validó
con la misma base y plantilla, y el build se hizo en el host). Provocar el `ErrorBoundary` en el navegador es opcional.

## 5. Imagen del backend y arranque (H-07, H-15, H-11)

| Ítem original | Resultado |
|---|---|
| 1. `docker compose build backend` | ☐ **No se pudo construir con el Dockerfile oficial en el entorno**: `apt-get` hacia `deb.debian.org` está bloqueado (probado, [construcciones_oficiales.md](../evidencias/validacion_integral/resultados/construcciones_oficiales.md)). Sí: el lock se instala con `--require-hashes` en Python 3.14, `pip-audit` y Trivy sin hallazgos, los `compose*.yaml` son válidos, y el **servicio** corrió en contenedor con una imagen de ensayo equivalente (sección 7) |
| 2. Sin `API_ENV` el backend no arranca | ✔ prueba automatizada (`test_security_config.py`); ☐ confirmarlo dentro de la imagen |
| 3. Tu `.env` | ☐ **acción tuya** (`API_ENV` explícito) |
| 4. Límite de 1800/min por IP con uso normal | ✔ prueba automatizada del límite; ☐ uso real |

## 6. Verificaciones nuevas (H-02, H-04, H-05, H-06, H-08, H-09, H-10, H-16)

| Hallazgo | Verificado (entorno · resultado · evidencia) | ☐ Pendiente en tu entorno |
|---|---|---|
| **H-02** permisos | ✔ SQL Server 2022 real: antes la API puede borrar `Institucion` y `Auditoria`; después solo las 14 tablas necesarias, `Auditoria`/`AuditoriaContexto` sin UPDATE/DELETE aunque conserve `db_datawriter`, roles fijos quitados y restaurados, idempotencia, reversión completa, ningún dato borrado; la API **no puede** CREATE/ALTER; la cuenta de conservación sí depura auditoría. **76/76** ([sqlserver_h02_h16.txt](../evidencias/validacion_integral/resultados/sqlserver_h02_h16.txt)) · y la API real con esas cuentas: registro, verificación, login, MFA, refresh, reutilización, baja de cuenta (DELETE por tabla), Google simulado: **51/51**, sin ningún error de permisos ([app_sqlserver_permisos_minimos.txt](../evidencias/validacion_integral/resultados/app_sqlserver_permisos_minimos.txt)) | Aplicar los scripts a una **copia restaurada de tu base real** (SQL Server 2025 Express) y recorrer tus flujos de instituciones, pacientes, transferencias y dispositivos; no se inspeccionó la cuenta `glucolume_app` real |
| **H-16** puentes | ✔ misma base: tabla `PuenteCredencial`; migración idempotente sobre una base «anterior» y estructura idéntica a v5; CLI `bridgeTokens` crear/rotar/revocar/listar con la cuenta de conservación; la API autentica, limita al dispositivo (403), anota `fechaUltimoUso` con el GRANT de columna y rechaza el token revocado de inmediato; todo auditado | Aplicar la migración a tu base; crear las credenciales reales y poner `BRIDGE_ALLOW_SHARED_TOKEN=false` cuando todos los puentes las usen |
| **H-04** retención | ✔ `retention previsualizar`, `retention ejecutar` con cantidad que no coincide (no borra) y `purgeInstitutionalRetention --simular` contra SQL Server real con la cuenta de conservación: sin aprobación el plazo efectivo es 0; **ningún dato se eliminó**; pruebas automatizadas de conservación, anonimización y errores parciales | La **decisión legal** de los plazos y su referencia (`RETENTION_APPROVAL_REFERENCE`); no se ejecutó ni programó ninguna purga |
| **H-06** Redis | ✔ **dos procesos reales de la API** + Redis 7 (Docker, con contraseña): sin Redis el límite se duplica (120 intentos), con Redis es único (60); una instancia ve el bloqueo de la otra; las claves no contienen IP ni identificadores; caída con política `local` (sigue respondiendo y limitando en memoria) y `deny` (rechaza) y recuperación. **12/12** ([redis_multi_instancia.txt](../evidencias/validacion_integral/resultados/redis_multi_instancia.txt)) | Un Redis protegido de verdad (contraseña, TLS o red interna sin puerto publicado) y decidir `RATE_LIMIT_ON_FAILURE` |
| **H-08** rotación | ✔ pruebas automatizadas (rotación, expiración de la ventana, revocación, configuraciones inválidas); procedimiento en SEGURIDAD §5.1 | Ensayar la rotación **real** y la reversión; rotar DB, SMTP y Google a mano |
| **H-09** cookie | ✔ **Chromium real**: dev (24/24) y **build de producción detrás de la plantilla real de Nginx** (24/24): cookie `HttpOnly`/`SameSite=Strict`/`Path`, persistente solo con «Recordarme», sin refresh token en `document.cookie` ni en Web Storage, rotación al recargar, cierre de sesión que la borra, `fetch` y formulario de otro sitio rechazados · API real contra SQL Server: login, MFA, refresh, reutilización → revocación, Google simulado (canje y `session-transfer`), logout | HTTPS real (atributo `Secure` en el navegador; en las pruebas lo cubre un test HTTP), Google real y MFA en el navegador, el flujo `VITE_LOGIN_ORIGIN`, y decidir `REFRESH_TOKEN_IN_BODY=false` |
| **H-05** firmware | ✔ ambos sketches **compilan** con el núcleo oficial (original 60 % de flash / **84 % de RAM**; optimizado 71 % / 50 %); el código de firma compilado corre en un ATmega328P **simulado** (simavr) y el verificador del puente acepta cada línea (5 líneas, contadores) | **Placa real + HC-06**: carga del sketch completo, tiempos, EEPROM, provisión de la clave por USB, cambio físico del PIN y la decisión sobre la confidencialidad del enlace. **Sigue abierto** |
| **H-10** zlib | ✔ evidencia refrescada: ni la imagen fijada ni la más nueva (3.14.9) traen una `zlib1g` distinta; **Trivy** la clasifica MEDIUM y sin corrección publicada ([ESCANEO_TRIVY](../evidencias/validacion_integral/resultados/ESCANEO_TRIVY_2026-10-23.md)); base de Nginx limpia | Reconstruir con `--pull --build-arg ZLIB_MIN_VERSION=<versión>` cuando Debian publique la corrección. **Sigue abierto** (no se cambió ninguna imagen) |

## 7. Integración final: el stack Docker (23/10/2026)

Entorno: Docker 29.9 en Linux (cloud aislado), datos y contraseñas sintéticos generados en cada corrida. Evidencia: [stack_docker_completo.txt](../evidencias/validacion_integral/resultados/stack_docker_completo.txt),
[estado_stack.md](../evidencias/validacion_integral/resultados/estado_stack.md), [actualizacion_sin_perdida.txt](../evidencias/validacion_integral/resultados/actualizacion_sin_perdida.txt). Script: `docs/evidencias/validacion_integral/stack_docker.sh`.

| Pieza | ✔ Verificado (resultado) | ☐ Pendiente en tu equipo |
|---|---|---|
| `db` | Imagen construida con el `docker/mssql/Dockerfile` oficial; `healthy`; sin puertos publicados; volumen `mssql-data` persiste a `down`/`up`; instalación con los scripts oficiales: 34 tablas, 49 FK, 127 CHECK, 33 índices, 27 reglas de matriz | Tu SQL Server Express (no se tocó); si usás el perfil `db`, crear la base ahí con los mismos pasos |
| `backend` | En contenedor (solo lectura, `cap_drop ALL`, usuario sin privilegios), `healthy`, conectado con `glucolume_app` (sin roles fijos); 49/49 por HTTP (dev) y 50/50 por HTTPS (producción) | **Construir con el `backend/Dockerfile` oficial** (en el cloud se usó una imagen de ensayo: mismos base y lock, ODBC instalado de otra fuente) |
| `frontend` (Nginx) | Imagen de runtime con la base fijada + plantilla + build de producción: `healthy`, sin privilegios, cabeceras y CSP correctas | **Construir con el `frontend/Dockerfile` oficial** (la etapa `build` y `apk upgrade` no corrieron en el cloud) |
| `redis` | `healthy`, contraseña, sin puertos; límites compartidos; caída y recuperación | Un Redis real solo si vas a usar más de una réplica |
| `proxy` (Caddy) | HTTPS con su CA interna para `localhost`: HSTS, cookie `Secure`, `API_ENV=production`, certificado de SQL Server verificado | Dominio real y certificado de Let's Encrypt |
| `lifecycle` | **No se levantó** (`ACCOUNT_LIFECYCLE_INTERVAL_SECONDS=0`); ninguna purga | Decidir cuándo activarlo contra datos reales |
| Actualización de la base | Base instalada con el v5 de `master` → scripts de la rama: 16/16 (ninguna fila cambia; estructura idéntica a una instalación nueva; `schemaCheck` sin diferencias) | Hacerlo en una **copia restaurada** de tu base real antes de la real |

Comandos para ejecutar GlucoLume en Windows: [DESPLIEGUE.md](../DESPLIEGUE.md) §3.0 (instalación y actualización de la base: [BASE_DE_DATOS.md](../BASE_DE_DATOS.md) §2 y §3).

## 8. Qué NO puede sustituirse con una simulación

- **Windows:** DPAPI, cuenta de Windows, `sqlcmd.exe -E`, Programador de tareas, rutas `C:\`, Git for Windows (`gpg.exe`), BitLocker y el SQL Server Express real.
- **Hardware:** la placa Arduino, el sensor MAX30100, el HC-06 y su PIN; el enlace Bluetooth en el aire.
- **Credenciales y servicios reales:** Google OAuth real, SMTP real, rotación de secretos de producción, dominio y certificado HTTPS.
- **Decisión legal:** plazos de conservación (H-04).
- **Infraestructura (H-03):** cifrado en reposo; **no se tocó**.

## 9. Qué NO se hizo (y no debe hacerse sin tu decisión)

- No se accedió a ninguna base, Redis, SMTP, Google ni credencial reales; todo lo anterior usó contenedores y procesos descartables con datos sintéticos.
- No se ejecutó ni programó `purgeInstitutionalRetention` ni ninguna purga destructiva; la retención se verificó solo por simulación.
- No se rotó ningún secreto real y no se desplegó nada. No se implementó H-03. El PR #2 se fusionó con `master` **por tu indicación expresa** (la rama de trabajo se conserva); fusionar el código no aprueba la auditoría. **No se aceptó ningún riesgo residual en tu nombre.**
