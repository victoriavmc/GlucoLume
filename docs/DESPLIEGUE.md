# Despliegue y operación

> Última revisión: 23/10/2026, contrastada con una ejecución real del stack (SQL Server, backend, Nginx, Redis y Caddy en contenedores): ver §8 y [evidencias/validacion_integral](evidencias/validacion_integral/README.md).

Contenerización con Docker Compose para desarrollo en Windows y para un servidor Linux. Base de datos: [BASE_DE_DATOS.md](BASE_DE_DATOS.md).
Puente y Arduino: [DISPOSITIVOS_Y_ADQUISICION.md](DISPOSITIVOS_Y_ADQUISICION.md). Controles de seguridad: [SEGURIDAD.md](SEGURIDAD.md).

## 1. Servicios

```text
navegador ──HTTPS──▶ proxy Caddy (perfil https) ──HTTP──▶ frontend (Nginx + SPA, 127.0.0.1:8080) ──/api──▶ backend (FastAPI :8000)
                                                                                                          │ ODBC 18 (red data)      │ (opcional)
                                                                                    SQL Server externo  ◀─┴─▶  db (perfil db)       └─▶ redis (perfil redis)
```

| Servicio | Origen | Responsabilidad | Puertos | Redes |
|---|---|---|---|---|
| `backend` | `backend/Dockerfile` (Python 3.14 slim, ODBC 18, usuario 10001) | API `/api/v1`: autenticación local/Google/JWT/MFA, usuarios, grupos, instituciones, dispositivos, mediciones, correo, adquisición | Ninguno (solo `compose.dev.yaml` publica 127.0.0.1:8000) | edge, data |
| `lifecycle` | Misma imagen (`python -m app.jobs.accountLifecycle --loop`) | Único programador del ciclo de vida de cuentas institucionales y de la retención de la auditoría | Ninguno | data |
| `notifications` | Misma imagen (`python -m app.jobs.reminders --loop`) | Genera los recordatorios de medición, reintenta correos fallidos y depura avisos vencidos de la bandeja | Ninguno | data |
| `frontend` | `frontend/Dockerfile` (build Vite → Nginx 1.30 alpine-slim sin privilegios, usuario 101) | Sirve la SPA, reenvía `/api/` y pone las cabeceras de seguridad | 8080 → `127.0.0.1:${FRONTEND_PORT}` | edge |
| `db` (perfil `db`) | `docker/mssql/Dockerfile` (SQL Server 2022 CU16 parcheado) | SQL Server opcional con volumen `mssql-data` | Ninguno (dev: 127.0.0.1:1433) | data |
| `proxy` (perfil `https` de `compose.prod.yaml`) | `caddy:2.11-alpine` (digest fijo) | Dominio y HTTPS automático (Let's Encrypt, HSTS) | 80, 443 | edge |
| `redis` (perfil `redis` de `compose.redis.yaml`) | `redis:7-alpine` (digest fijo) | **Opcional**: límites de solicitudes compartidos entre réplicas (H-06). Sin contraseña no arranca, sin persistencia | Ninguno | data |
| `firmware` (perfil `firmware`) | `docker/firmware/Dockerfile` (Arduino CLI) | Compila el sketch y termina | Ninguno | Ninguna |

Imágenes base fijadas por digest (backend, frontend, SQL Server, firmware y Caddy 2.11; GL-13). `restart: unless-stopped` vuelve a levantar
al iniciar Docker Desktop un contenedor que no se detuvo con `docker compose stop`: si el `.env` apunta a la base real, detener los
servicios con `docker compose stop` (o `docker update --restart=no`) antes de cerrar Docker.

**Servicio `notifications` (`python -m app.jobs.reminders --loop`):** genera los recordatorios de medición a su hora (con la aplicación abierta o no), reintenta con espera creciente los correos que fallaron y, una vez por hora,
elimina los avisos vencidos de la bandeja (`NOTIFICATION_READ_RETENTION_DAYS`, `NOTIFICATION_UNREAD_RETENTION_DAYS`; no toca la auditoría). Misma imagen que el backend, sin puertos; healthcheck `--health`; intervalo
`NOTIFICATIONS_INTERVAL_SECONDS` (60 por defecto, no se puede apagar). Es **independiente de `lifecycle`**: puede quedar siempre encendido aunque `lifecycle` esté desactivado. La depuración necesita la cuenta de procesos
(`DB_JOBS_USER`); sin ella los recordatorios funcionan y la depuración se registra como advertencia. Comandos manuales: `ejecutar` (una pasada), `depurar`, `previsualizar`. Ver [NOTIFICACIONES.md](NOTIFICACIONES.md) §5 y §12.

**`lifecycle` modifica datos reales** (elimina y anonimiza cuentas con plazo vencido, depura auditoría vencida): no levantarlo contra una
base de prueba ajena ni contra una base real sin decidirlo. El backend también corre un mantenimiento de mediciones cada
`MAINTENANCE_INTERVAL_SECONDS` (60 s; 0 lo desactiva) que cierra mediciones vencidas o abandonadas.

Endurecimiento de los contenedores: sin root, `read_only` + `tmpfs`, `cap_drop: ALL`, `no-new-privileges`, límites de CPU y memoria, logs
rotados (10 MB × 5), backend y base sin puertos publicados. SQL Server corre como `mssql` sin `cap_drop` (sus binarios usan capacidades de
archivo). Ningún secreto en Dockerfile, Compose ni imágenes (`.dockerignore` excluye `.env*`).

## 2. Variables

La configuración sale de `.env` (copiar `.env.example`; no entra en las imágenes ni en Git). Generar los secretos con los comandos del
propio `.env.example`.

| Variable de Docker | Para qué | Por defecto |
|---|---|---|
| `GLUCOLUME_VERSION` | Etiqueta de las imágenes (**obligatoria en producción**) | `dev` |
| `GLUCOLUME_IMAGE_PREFIX` | Prefijo o registro | `glucolume` |
| `DOCKER_DB_HOST` / `DOCKER_DB_PORT` | Reemplazan `DB_HOST`/`DB_PORT` dentro de Docker (`localhost` es el contenedor) | `DB_HOST`/`DB_PORT` |
| `FRONTEND_BIND` / `FRONTEND_PORT` / `FRONTEND_LOGIN_PORT` | Dirección y puertos publicados | `127.0.0.1` / `80` / `8080` |
| `FRONTEND_BACKEND_UPSTREAM` | Destino de `/api` en Nginx | `backend:8000` |
| `FRONTEND_API_BASE_URL` | `VITE_API_BASE_URL` al compilar (pública) | `/` |
| `FRONTEND_TRUSTED_PROXY_CIDR` | Único origen del que Nginx acepta `X-Forwarded-For` | `172.16.0.0/12` |
| `MSSQL_PID` | Edición del perfil `db` | `Express` |
| `GLUCOLUME_DOMAIN` | Dominio del perfil `https` | `localhost` |
| `SERIAL_DEVICE`, `SERIAL_GROUP_ID` | `compose.serial.yaml` (host Linux) | `/dev/ttyACM0`, `20` |
| `ACCOUNT_LIFECYCLE_INTERVAL_SECONDS` | Intervalo del servicio `lifecycle` (0 lo desactiva) | `3600` |
| `PERSONNEL_RETENTION_MONTHS` | Minimización de datos históricos del personal (0 = desactivada) | `0` |
| `BRIDGE_TOKEN` | Token del puente (≥ 32 caracteres; el mismo en `acquisition/bridge/bridge.env`) | vacío (recepción deshabilitada) |
| `BRIDGE_PREVIOUS_TOKEN` | Token anterior aceptado mientras se actualiza el puente (rotación); quitarlo después | vacío |
| `DB_MAX_CONCURRENT_CALLS` | Tope de hilos de la API dentro del driver ODBC a la vez (`app/db/gate.py`); evita el desplome de rendimiento con 6 o más consultas simultáneas ([RENDIMIENTO.md](RENDIMIENTO.md) §3.1). 0 lo desactiva | `2` |
| `DB_JOBS_USER` / `DB_JOBS_PASSWORD` | Cuenta de base de `lifecycle` y de los jobs, la única que depura la auditoría (GL-03). Las dos o ninguna; distinta de `DB_USER`. Compose no se la pasa a la API | vacías (los jobs usan `DB_USER`) |
| `SECURITY_ALERT_EMAIL_MINUTES` | Alerta por correo al administrador de la plataforma ante una ráfaga de rechazos (como máximo una por patrón en ese lapso; 0 la desactiva) | `60` |
| `MFA_PREVIOUS_ENCRYPTION_KEYS` | Claves Fernet anteriores, separadas por coma, para descifrar mientras se re-cifra (`python -m app.cli.mfaKeys`) | vacía |
| `ALLOW_INDIVIDUAL_ON_INSTITUTIONAL_DEVICE` | Modo de uso del dispositivo (DEC-01): `true` compartido, `false` restringido | `false` en el código; el prototipo usa `true` |

| Variable de la aplicación según el modo | Compose base / producción | `compose.dev.yaml` |
|---|---|---|
| `FRONTEND_URL` / `API_BASE_URL` | URL pública (`http://glucolume.local` o `https://dominio`) | `http://localhost:5173` / `http://localhost:8000` |
| `GOOGLE_REDIRECT_URI` | `{API_BASE_URL}/api/v1/auth/google/callback` (registrada en Google Cloud) | ídem |
| `API_ENV` | `production` (lo fuerza `compose.prod.yaml`); obligatorio en la imagen: sin él la API no arranca | `development` |

La contraseña de `sa` del perfil `db` va aparte en `docker/db.env` (desde `docker/db.env.example`, ignorado por Git). La API usa su propio
usuario con permisos limitados, nunca `sa`.

## 3. Desarrollo

Requisitos: Docker Desktop y `.env` completo. Con SQL Server instalado en Windows: `DOCKER_DB_HOST=host.docker.internal` (o una IP
alcanzable) y `DOCKER_DB_PORT` si no es 1433; habilitar TCP/IP y el puerto en el firewall para la red de Docker.

```bash
docker compose up --build -d                                     # backend + lifecycle + frontend
docker compose up -d backend frontend                            # sin lifecycle
docker compose -f compose.yaml -f compose.dev.yaml up --build    # recarga: Vite :5173, API :8000
docker compose --profile db up -d                                # + SQL Server en contenedor (requiere docker/db.env)
```

Sin Docker: backend `cd backend && python -m uvicorn app.main:app --host localhost --port 8000` (Python 3.14, ODBC Driver 18); frontend
`cd frontend && npm ci && npm run dev` (necesita `VITE_API_BASE_URL`).

**Pruebas:** `cd backend && python -m pytest` y `cd frontend && npm test`. Sin `node_modules` locales, el frontend se prueba en un contenedor
descartable: `docker build --target dev -t glucolume-frontend-test frontend` y `docker run --rm glucolume-frontend-test npx vitest run`. Las
pruebas de backend usan SQLite temporal, bloquean SMTP y fijan el modo del dispositivo; las que necesitan SQL Server exigen una base
descartable ([BASE_DE_DATOS.md](BASE_DE_DATOS.md) §6).

### 3.0 Guía rápida para Windows (PowerShell, Docker Desktop)

Dos formas de tener la base; **no restaurar ni ejecutar nada sobre tu SQL Server Express real sin respaldo y sin ensayarlo antes en una copia** ([BASE_DE_DATOS.md](BASE_DE_DATOS.md) §2–§3).

**A. Con tu SQL Server Express de Windows (instalación existente)** — el backend en Docker se conecta a la instancia del equipo:

```powershell
cd C:\ruta\a\GlucoLume
git fetch origin; git checkout master; git pull --ff-only                  # versión integrada
Copy-Item .env.example .env                                                # solo la primera vez; completar con tus valores (nunca subirlo a Git)
# En .env: DOCKER_DB_HOST=host.docker.internal, DB_NAME/DB_USER/DB_PASSWORD, API_ENV=development, ACCOUNT_LIFECYCLE_INTERVAL_SECONDS=0
docker compose build backend frontend                                      # construye las imágenes desde el código
docker compose up -d backend frontend                                      # SIN lifecycle (no elimina ni anonimiza nada)
docker compose ps                                                          # los dos deben figurar «healthy»
Start-Process "http://localhost:8080"                                      # o http://glucolume.local si resolviste el nombre (§3.1)
```

**B. Con SQL Server en contenedor (base nueva y aislada, volumen persistente `mssql-data`)** — ideal para ensayar:

```powershell
Copy-Item .env.example .env; Copy-Item docker\db.env.example docker\db.env          # completar: contraseña de sa en db.env; DB_HOST=db en .env
docker compose --profile db up -d db                                       # SQL Server (sin puertos publicados); esperar «healthy»
# Crear la base y aplicar los scripts oficiales: BASE_DE_DATOS.md §2 (v5, matriz, logins y permisos)
docker compose --profile db up -d backend frontend
```

Redis es **opcional** (solo con más de una réplica): `docker compose -f compose.yaml -f compose.redis.yaml --profile db --profile redis up -d`, con `REDIS_PASSWORD` y
`RATE_LIMIT_REDIS_URL=redis://:<contraseña>@redis:6379/0` en el `.env` (`compose.redis.yaml` no publica el puerto).

Detener, reiniciar, reconstruir y verificar:

```powershell
docker compose stop                                   # detiene todo y conserva los datos (si el .env apunta a la base real, hacerlo antes de cerrar Docker Desktop)
docker compose start                                  # lo vuelve a iniciar
docker compose up -d --build backend frontend         # reconstruye con el código actual
docker compose down                                   # quita contenedores y redes; CONSERVA el volumen mssql-data (nunca usar «down -v» con datos reales)
docker compose ps; docker compose logs --tail 50 backend
Invoke-RestMethod http://localhost:8080/nginx-health  # «ok»
curl.exe -s -o NUL -w "%{http_code}`n" http://localhost:8080/api/v1/auth/me                # 401: la API responde detrás de Nginx
```

Respaldo y restauración de prueba del volumen/base: [BASE_DE_DATOS.md](BASE_DE_DATOS.md) §4.

### 3.1 Acceso por `glucolume.local`

Nginx es el único punto de entrada, en el puerto 80 del equipo: `/` (SPA), `/api/v1/…` (API) y `/docs`, `/redoc`, `/openapi.json`
(solo fuera de producción).

1. Resolver el nombre (PowerShell como administrador): `Add-Content -Path "$env:SystemRoot\System32\drivers\etc\hosts" -Value "127.0.0.1 glucolume.local"`.
2. En `.env`: `FRONTEND_URL=http://glucolume.local`, `API_BASE_URL=http://glucolume.local`.
3. `docker compose up -d --build` con el puerto 80 libre.

Google no admite `.local` como URI de redirección: solo `/login` se sirve desde `http://localhost:8080` (`FRONTEND_LOGIN_ORIGIN`,
`FRONTEND_APP_ORIGIN`, compilados en el frontend; `OriginGuard.jsx` mueve cada página a su origen). Google redirige a
`http://localhost/api/v1/auth/google/callback`, el backend valida `state`/nonce/PKCE y entrega un código de un solo uso (2 min) que se canjea en
`POST /auth/google/exchange` en `glucolume.local`. Con contraseña, el login en `localhost` obtiene un código de traspaso
(`POST /auth/session-transfer`) y la aplicación abre una sesión nueva en `glucolume.local` sin repetir MFA. El inicio de sesión con Google
no crea cuentas (`CUENTA_NO_REGISTRADA`); el registro es un flujo aparte.

## 4. Producción en un servidor Linux

1. Docker Engine + Compose; clonar el repositorio; crear `.env` con **secretos nuevos** (`JWT_SECRET`, `SESSION_SECRET`, `DB_PASSWORD`,
   SMTP, Google, `BRIDGE_TOKEN`). `MFA_ENCRYPTION_KEY` debe ser la que cifró los factores de la base existente.
2. `.env`: `FRONTEND_URL` y `API_BASE_URL` con `https://dominio`, `GOOGLE_REDIRECT_URI`, `GLUCOLUME_VERSION`, `GLUCOLUME_DOMAIN` y
   `DB_TRUST_SERVER_CERTIFICATE=false` con un certificado válido en SQL Server.
3. DNS del dominio al servidor; abrir solo 80 y 443.
4. `docker compose -f compose.yaml -f compose.prod.yaml --profile https up -d --build`. Con otro proxy en el host: omitir el perfil, apuntar el
   proxy a `127.0.0.1:8080` enviando `X-Forwarded-Proto: https` y fijar `FRONTEND_TRUSTED_PROXY_CIDR` al CIDR de ese proxy (nunca `0.0.0.0/0`).
5. Primer administrador después de preparar la base: `docker compose exec backend python -m app.cli.initAdmin …`.
6. Limpieza periódica de cuentas sin verificar (cron del host):
   `docker compose -f compose.yaml -f compose.prod.yaml exec -T backend python -m app.jobs.cleanupUnverifiedAccounts`.
7. La retención de pacientes (`python -m app.jobs.purgeInstitutionalRetention --confirmo-base <DB_NAME>`) **no está programada** en Compose: se
   ejecuta a mano y sin `--confirmo-base` exacto no modifica nada.

**Actualización y vuelta atrás:** cada componente por separado con su `GLUCOLUME_VERSION`
(`… up -d --build backend` o `frontend`); para volver, usar la etiqueta anterior. Un cambio de base no es un paso de Docker: se hace con
respaldo previo ([BASE_DE_DATOS.md](BASE_DE_DATOS.md)).

**Red y límites:** Nginx sobrescribe `X-Forwarded-For` hacia el backend con la IP real (solo confía en `FRONTEND_TRUSTED_PROXY_CIDR`);
límites por IP en los endpoints sin sesión (429 con `Retry-After`) en la memoria del proceso (exactos con **una** réplica); tope de inundación
de Nginx en `/api/v1/auth/` (30/s, ráfaga 60); HSTS solo si el pedido original fue HTTPS; Swagger/OpenAPI no se publican con
`API_ENV=production`. El hub de telemetría también exige un único proceso del backend.

## 5. Operación diaria

```bash
docker compose ps                         # estado y salud
docker compose logs -f backend            # logs
docker compose restart backend            # reiniciar un componente
docker compose stop backend               # detener uno (conserva todo)
docker compose down                       # quitar contenedores (conserva volúmenes; down -v los borra: nunca en producción)
docker stats                              # consumo frente a límites
```

Salud: backend `GET /healthz` (no consulta la base, para no reiniciar en bucle si SQL Server cae); Nginx `GET /nginx-health`.
`restart: unless-stopped` (producción: `always`). La conexión a SQL Server se reintenta por pedido (`pool_pre_ping`).

## 6. Imágenes y dependencias

Escaneo con Trivy del 23/10/2026 ([resultados](evidencias/validacion_integral/resultados/ESCANEO_TRIVY_2026-10-23.md)): base de Nginx y imagen del frontend 0 vulnerabilidades y 0 secretos; dependencias de Python y de npm 0; la base del backend (Debian 13.7) tiene `zlib` y 44 HIGH del sistema **sin corrección publicada** (H-10, abierto). Escaneo con Docker Scout del 10/10/2026: tras las correcciones, 0 críticas en las cuatro imágenes (backend 0/1, frontend 0/0,
firmware-build 0/1, mssql 0/0). Alta abierta: `zlib` CVE-2026-85091 en backend y firmware (sin parche en Debian al 23/10/2026: [evidencias/CVE_ZLIB_2026-10-23.md](evidencias/CVE_ZLIB_2026-10-23.md)). Línea base anterior:
[evidencias/CVE_LINEA_BASE_2026-10-10.md](evidencias/CVE_LINEA_BASE_2026-10-10.md).

Mantenimiento: reconstruir con `--pull` al menos una vez por mes y antes de cada despliegue; escanear la imagen etiquetada que se despliega;
`pip-audit` (en `requirements-dev`) y `npm audit` sobre los lock. Resumen por paquete:

```bash
docker scout cves --only-severity critical,high --format packages local://glucolume/backend:dev > b.txt
python docs/evidencias/scan_summary.py b.txt
```

Las bases se fijan por etiqueta de rama para recibir parches; fijarlas por digest es una mejora pendiente.

## 7. Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `Can't open lib … msodbcsql` | Reconstruir el backend con la Dockerfile actual (`--no-cache`) |
| El backend no conecta a SQL Server de Windows | Usar `DOCKER_DB_HOST=host.docker.internal`; TCP/IP y firewall; revisar el puerto |
| `required variable GLUCOLUME_VERSION is missing` | Producción exige versión |
| `env file docker/db.env not found` | Perfil `db`: copiar `docker/db.env.example` |
| Error de CORS | `FRONTEND_URL` no coincide con el origen real |
| Enlaces de correos a `localhost:5173` | Falta `FRONTEND_URL` pública |
| Google `redirect_uri_mismatch` | `GOOGLE_REDIRECT_URI` debe estar registrada |
| `bind: address already in use` | Cambiar `FRONTEND_PORT` o liberar el puerto |
| Recarga lenta en Windows | Mantener el repositorio dentro de Windows (no en `\\wsl$`) |
| SQL Server en contenedor se reinicia | Necesita ≥ 2 GB de RAM y una contraseña de `sa` que cumpla la política |
| El Arduino no aparece en Docker | Esperado: usar el puente de Windows |
| «Sin DB_JOBS_USER» al arrancar el backend en producción | Esperado en Docker: Compose no entrega `DB_JOBS_USER` a la API (solo al servicio `lifecycle` y a las herramientas de línea de comandos) |
| `docker compose run lifecycle …` | Crea un contenedor de un solo uso con la cuenta de conservación (p. ej. `--entrypoint python lifecycle -m app.cli.bridgeTokens listar`); no levanta el bucle de `lifecycle` |

## 8. Qué se ejecutó de verdad (23/10/2026) y qué no

Con Docker 29.9 en un entorno cloud aislado (Linux), datos sintéticos y contraseñas generadas en cada corrida. **No** es tu instalación de Windows.

| Pieza | Estado | Cómo se comprobó |
|---|---|---|
| `db` (perfil `db`) | **Construida con el `docker/mssql/Dockerfile` oficial** y en ejecución, sin puertos publicados, volumen `mssql-data`, `healthy`; esquema v5 + permisos aplicados con los scripts del repositorio (34 tablas); persistió a `down`/`up` | `stack_funcional.py` secciones 1 y 7 |
| `frontend` (Nginx) | Imagen de **runtime** construida con la **misma base fijada y plantilla** y el build de producción hecho en el host; en ejecución, `healthy`, sin privilegios, `read_only` | idem; la etapa `build` del Dockerfile (`npm ci` dentro de Docker) y `apk upgrade` **no se pudieron ejecutar** en el entorno (proxy de salida / `dl-cdn.alpinelinux.org` bloqueado) |
| `backend` | En ejecución en contenedor, `healthy`, `read_only`, `cap_drop ALL`, usuario 10001, conectado a SQL Server como `glucolume_app` (sin roles fijos). **Imagen de ensayo** (`evidencias/validacion_integral/docker/Dockerfile.backend-entorno-cloud`): el `backend/Dockerfile` oficial **no se pudo construir** porque `deb.debian.org` está bloqueado, así que los paquetes del sistema (ODBC 18, unixODBC, Kerberos) se instalaron como `.deb` de Ubuntu/Microsoft sobre la misma base Debian fijada | idem |
| `redis` (`compose.redis.yaml`) | En ejecución, `healthy`, con contraseña, sin puertos; el backend lo usa para los límites; caída y recuperación comprobadas | idem sección 6 |
| `proxy` (Caddy, `compose.prod.yaml --profile https`) | En ejecución con `API_ENV=production`: HTTPS con la CA interna de Caddy para `localhost`, HSTS, cookie `Secure`, certificado de SQL Server **verificado** (fijado con `DB_SERVER_CERTIFICATE`), token compartido del puente desactivado | `stack_funcional.py` contra `https://localhost:18444` |
| `lifecycle` | **Nunca se levantó** (`ACCOUNT_LIFECYCLE_INTERVAL_SECONDS=0` y solo contenedores de un solo uso para la CLI de puentes) | comprobado en la sección 5 |
| `firmware` | No se construyó (necesita Arduino CLI desde GitHub/Debian) | — |

**Pendiente en tu equipo:** `docker compose build` **completo** de `backend` y `frontend` (con el Dockerfile oficial), Docker Desktop/WSL2, tu SQL Server Express, `glucolume.local`, Google y SMTP reales.

