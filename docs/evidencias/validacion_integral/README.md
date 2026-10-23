# Validación integral (23/10/2026) — evidencia reproducible

Todo lo de esta carpeta se ejecutó en un contenedor Linux **aislado** con Docker, **sin tocar ninguna base, Redis, SMTP, Google ni credencial reales**: SQL Server 2022,
Redis 7 y Nginx corrieron en contenedores o procesos **descartables**, con contraseñas sintéticas generadas en cada corrida y datos 100 % sintéticos. Ningún script
apunta a un servicio que no sea el descartable en `localhost` (solo se descargan imágenes y paquetes públicos). El estado por hallazgo está en [../../SEGURIDAD.md](../../SEGURIDAD.md) §2.0.2 y la lista de lo que sigue pendiente en
[../../seguridad/VERIFICACIONES_PENDIENTES_WINDOWS.md](../../seguridad/VERIFICACIONES_PENDIENTES_WINDOWS.md).

## Qué hay y cómo repetirlo

Desde la raíz del repositorio, con el entorno virtual del backend activo (`pip install --require-hashes -r backend/requirements.txt`) salvo que se indique otra cosa.

| Script | Qué valida | Requiere | Resultado del 23/10 | Log |
|---|---|---|---|---|
| `sqlserver_h02_h16.sh` | v5 en SQL Server real; `GlucoLume_permisos*.sql` (antes/después, idempotencia, DENY, roles fijos, reversión); migración de `PuenteCredencial` | Docker, imagen de SQL Server 2022 | **76/76** | `resultados/sqlserver_h02_h16.log` |
| `app_sqlserver_minimos_permisos.py` | La API REAL y las CLI contra SQL Server con las cuentas restringidas: registro, MFA, cookie, refresh, baja de cuenta, Google simulado, puentes (CLI + API), retención simulada | lo anterior + ODBC 18 (`GL_MSSQL_CONTAINER`, `GL_MSSQL_PORT`, `GL_MSSQL_SA_PW`) | **51/51** | `resultados/app_sqlserver_permisos_minimos.log` |
| `redis_multi_instancia.py` | H-06: dos procesos de la API + Redis real: cuota compartida, privacidad de claves, caída y recuperación (`local` y `deny`) | Docker (`redis:7-alpine`) | **12/12** | `resultados/redis_multi_instancia.log` |
| `nginx_real.sh` | Plantilla real de Nginx: log sin query, cabeceras, proxy de confianza, 429, cookie `HttpOnly` a través del proxy. `DIST=<build>` usa el nginx del sistema; `IMAGEN=<imagen>` usa la imagen fijada | nginx + `envsubst`, o Docker | **20/20** (1.24) y **23/23** (imagen 1.30.6) | `resultados/nginx_sistema_1.24.log`, `nginx_imagen_1.30.6.log` |
| `nginx_servir.sh` + `verificar_navegador.py` | Build de producción (`VITE_API_BASE_URL=/`) detrás de esa plantilla, en un **Chromium real**: cookie `HttpOnly`/`SameSite`/`Path`, «Recordarme», recarga, logout, CSRF desde otro sitio | Playwright (`pip install playwright`), Chromium | **24/24** (+ 0 violaciones de CSP) | `resultados/chromium_*.log` |
| `powershell_respaldos.sh` | Los `.ps1` de `database/respaldos` SIN modificar, con PowerShell 7 en Linux y SQL Server real | `pwsh`, Docker, `gpg` | **33/33** | `resultados/powershell_respaldos.log` |
| `servidor_sintetico.py` | API real con SQLite temporal y una persona sintética (lo usan los anteriores) | — | — | — |
| `powershell_shims/sqlcmd` | Reenviador a `sqlcmd` del contenedor (**solo ensayo**; no existe en Windows) | — | — | — |

Además (comandos en `resultados/`): `firmware/verificacion/verificar_firma.sh` (ATmega328P simulado: 5 líneas firmadas verificadas por el puente), compilación de los dos sketches
con el núcleo oficial, `python -m tests.lifecycle_concurrency --rondas 20` contra SQL Server (**120/120**), validez de los cuatro `compose*.yaml`, y
[ESCANEO_TRIVY_2026-10-23.md](resultados/ESCANEO_TRIVY_2026-10-23.md) (imágenes base, dependencias, secretos y Dockerfiles).

Suites completas sobre el último commit: backend con las pruebas opcionales de SQL Server **activadas** (`TEST_SQLSERVER_URL=… TEST_SQLSERVER_CONFIRM=DESCARTABLE` hacia una
base descartable): **1983 pasaron, 0 fallaron, 0 omitidas** (`resultados/suites.md`); frontend 695/695.

## Limitaciones (qué NO demuestra esto)

- No es tu instalación: SQL Server 2022 CU16 (la imagen del proyecto), no SQL Server 2025 Express; Linux, no Windows; sin tus datos, tu `.env`, tu dominio ni HTTPS.
- PowerShell en Linux no tiene DPAPI: la protección de la clave de respaldo y las tareas programadas **no** se validaron.
- La imagen del backend no se pudo construir (`deb.debian.org` bloqueado); la del frontend se armó con la misma base fijada y plantilla, y el build de producción se generó en el host
  (`npm ci` dentro de Docker falla tras el proxy de salida y `apk upgrade` necesita `dl-cdn.alpinelinux.org`).
- Google, SMTP y el firmware son simulaciones: no prueban el servicio real ni la placa.
- La prueba en Chromium usa HTTP (el atributo `Secure` de la cookie lo cubre una prueba HTTP, no el navegador).

## Análisis de regresión (funcional y de seguridad)

| Área | Cómo se comprobó | Resultado |
|---|---|---|
| Autenticación local, MFA, recuperación, activación, sesiones | Suite completa (incluye `test_auth_*`, `test_mfa_*`, `test_platform_*`) + API real contra SQL Server con cuentas restringidas (51/51) | Sin regresiones; el modo heredado (refresh token en el cuerpo) sigue funcionando para puentes y scripts |
| Google OAuth | Pruebas de canje y callback + canje simulado y `session-transfer` en la API real | Sin regresiones; el código es de un solo uso y la sesión se entrega por cookie |
| Permisos y autorización | Suite completa; una cuenta común recibe 403 en `/platform/*` y `/audit` (API real) | Sin regresiones |
| Auditoría | Suite; con las cuentas restringidas la API solo inserta (UPDATE/DELETE → 229) y la baja de cuenta conserva y amplía la auditoría | Sin regresiones |
| Comunicación del dispositivo / puentes | Suite (`test_bridge*`, `test_telemetry*`, también contra SQL Server real) + CLI y API con credenciales individuales | Sin regresiones |
| Operaciones institucionales | Suite (instituciones, pacientes, transferencias, reasignaciones) + concurrencia del ciclo de vida en SQL Server (120/120) | Sin regresiones |
| Frontend | Vitest 695/695; build de producción; Chromium real (login, recarga, logout, CSP sin violaciones) | Sin regresiones |
| Seguridad (nuevos riesgos introducidos por los cambios) | CORS con credenciales solo para el origen explícito del frontend; cookie `HttpOnly`/`SameSite=Strict`; CSRF por cabecera + `Origin`; Trivy sin secretos; `pip-audit`/`npm audit`/Trivy sin vulnerabilidades en las dependencias | Dos hallazgos propios corregidos (log de Nginx, `opentelemetry-api`); ninguno nuevo abierto |

Qué **no** cubre esta tabla: el comportamiento con tus datos reales, con Windows y con hardware (ver las limitaciones de arriba).
