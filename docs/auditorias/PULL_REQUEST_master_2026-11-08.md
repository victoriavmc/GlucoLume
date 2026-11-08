# Remediación de la auditoría de seguridad del 07/11/2026 (M-1 a M-3, B-1 a B-7; Anexo C pendiente de ejecución en servidor)

**Rama:** `claude/intelligent-keller-ujcsuf` → **master**. Base de comparación: `a3908c0`. **No se fusiona en esta etapa.**

## Veredicto

**APTO CON RIESGOS ACEPTADOS** para integrar a master, con dos condiciones que se cumplen antes de **desplegar** (no antes de integrar):

1. Confirmar en el servidor, en solo lectura, la cadena de proxies y las variables de origen (`TRUSTED_PROXY_CIDR`, `FORWARDED_ALLOW_IPS`, Tailscale Serve): sección «Origen».
2. Verificar el Caddyfile del perfil `https` (B-4) y HTTP/2 (B-5) en el edge real.

Motivos: no hay defectos abiertos de código; las 204 pruebas de SQL Server pasan en un motor 2022 CU16 descartable; la comparación contra
`a3908c0` no muestra regresiones; los riesgos que quedan son de configuración de despliegue o de decisión de negocio, no de código.

## Resumen de cambios

- **M-2 (login).** Límite por (cuenta, origen): 5 fallos en 15 min y 15 en 1 h. No bloquea la cuenta para terceros ni para su titular desde otro origen.
- **M-2 (reautenticación).** Operaciones sensibles: 3 fallos en 15 min por operación y usuario, en la auditoría (`REAUTENTICACION_CONTADOR`).
  Sobrevive a reinicios y es común a varias réplicas. Serializado con `UPDLOCK` sobre la fila de `CredencialLocal` (ver «Defecto corregido»).
  No comparte contador con el login.
- **M-2 (auditoría).** Cada intento rechazado por el límite deja una fila `LOGIN_LOCAL/CUENTA_BLOQUEADA`; cuentas inexistentes, HMAC; origen nunca en claro.
  Escritura en colas acotadas (200 pendientes).
- **M-3.** Control de concurrencia de Argon2 (2 en curso, 8 en espera, 503 con `Retry-After`); coste del hash sin cambios.
- **M-1, B-1, B-3, B-5, B-6, B-7.** Redirección relativa de `/api`; tope de cuerpos por operación; cabeceras sin duplicar; COOP/CORP en la SPA; readiness interna; CSP report sanitizado.
- **B-2.** Mapa de rutas de Nginx generado desde `App.jsx`, con prueba de sincronía; rutas inexistentes y archivos sensibles responden 404; enlaces de seguridad por tipo de cuenta.
- **B-4.** HSTS de 30 días sin `includeSubDomains` ni emisión en `localhost`.
- **Retención.** Corte de purga corregido a hora de Argentina. Plazo inicial propuesto: 12 meses. **Purga desactivada**; no se completó `RETENTION_APPROVAL_REFERENCE`.

Detalle por hallazgo: [CORRECCIONES_AUDITORIA_SEGURIDAD_2026-11-07.md](CORRECCIONES_AUDITORIA_SEGURIDAD_2026-11-07.md).

## Alcance

**154 archivos** entre `a3908c0` y HEAD (109 agregados, 45 modificados; 7716 líneas agregadas, 331 eliminadas). Por área:

| Área | Contenido principal |
|---|---|
| Backend, código | `auth.py` (límite, reautenticación, auditoría, colas), `loginThrottle.py`, `rateLimiter.py`, `auditRetention.py` (corte corregido), `platform*.py`, `institution.py`, `mfa*.py`, `accountDeletion.py`, `email.py`, `api/*` (cabeceras, errores, rate limit, CSP report, readiness) |
| Backend, pruebas | Nuevas: `test_login_m2_reglas.py`, `test_reautenticacion_sqlserver.py`, `test_readyz.py`, `test_hsts.py`, `test_argon2_gate.py`, `test_rutas_spa.py`, `test_csp_reports.py`, `test_tamano_solicitudes.py`, `test_aislamiento_origenes.py`, `test_login_throttle.py`, `test.env.example`; modificadas: `conftest.py`, `test_login_lockout.py`, `test_account_deletion.py`, `test_audit_security.py`, `test_auth_access_flows.py`, `test_telemetry_sqlserver.py`, entre otras |
| Frontend | `App.jsx` (redirecciones), `Dockerfile` (genera el mapa de rutas), `package.json` y lock (`@babel/parser`), `scripts/generar-rutas-spa.mjs` y su prueba |
| Docker / Nginx | `docker/nginx/default.conf.template`, `docker/nginx/rutas-spa.generado.conf` |
| Documentación y evidencias | Correcciones, verificación final, equivalencia de pruebas, SQL Server, origen, script reproducible de SQL Server, Anexo C (solo lectura) |
| Raíz | `.env.example`: variables de Argon2 |
| Reglas de negocio | `02_REGLAS_NEGOCIO.md`, `INDIVIDUAL.md`: reflejan el límite de login (5 por origen) |

**Base de datos:** no hay scripts SQL ni cambios de esquema en la rama. La reautenticación escribe en `Auditoria` (acción nueva sin `CHECK`) y lee esa tabla.
La cuenta de la aplicación ya tiene el permiso necesario (`INSERT` y `SELECT`; `UPDLOCK` verificado con esa cuenta).

## Resultados verificables

**Backend (SQLite, suite completa, `pytest -n 8`, mismo entorno sintético que la base):**

| | Pasadas | Fallidas | Omitidas |
|---|---|---|---|
| `a3908c0` | 2403 | 1 | 203 |
| `0657963` (rama) | 2584 | 0 | 204 |

Por identificador (`comparacion_final_backend_0657963.txt`): **regresiones nuevas: 0**; corregidas: 1 (`test_patient_access`, acceso anónimo);
agregadas: 190; eliminadas: 13 (11 de la lista de equivalencia y 2 de retención renombradas, `EQUIVALENCIA_PRUEBAS_ELIMINADAS_2026-11-08.md`).

**SQL Server 2022 CU16 descartable (las pruebas omitidas arriba):** **204 pasadas, 0 fallidas, 0 omitidas** (`sqlserver_descartable_resultados_2026-11-08.txt`).
Procedimiento reproducible: `sqlserver_descartable.sh`.

**Frontend (vitest, por identificador):** sin regresiones. Una falla preexistente en ambas versiones (`PatientMeasure`, timeout). 8 pruebas agregadas (generador de rutas).

**Compose y Nginx:**
- Los seis `compose*.yaml` validan con `docker compose config` (base + prod, dev, retención, serial; redis con valor ficticio en una copia, porque `REDIS_PASSWORD` es obligatoria).
- La plantilla de Nginx renderizada pasa `nginx -t`; la versión de Nginx de producción no se verificó.

**Compatibilidad con el esquema v5:** `CK_TokenCuenta_tipo` (7 valores) igual al enum del backend y a la migración; 40 tablas y 135 CHECK aplicados sin errores; `test_reference_schema.py` pasa.

**Seguridad de la reautenticación y concurrencia:** 8 sesiones simultáneas sobre la misma cuenta registran exactamente 3 fallos y 5 rechazos
(`test_reautenticacion_sqlserver.py`); el bloqueo `UPDLOCK` serializa, las lecturas del login no esperan, y el contador sobrevive a reinicios.

**Tipos de usuario y accesos (cobertura en pruebas):** consumidor final (18 archivos), institucional (12), administrador de plataforma (23), moderador (10); casos Google solo y unificada (23 archivos); accesos general y plataforma (11); operaciones de reautenticación (8). Todas las pruebas pasan.

## Defecto corregido en esta etapa

- **`with_for_update()` no bloquea en SQL Server.** SQLAlchemy no emite `UPDLOCK` para ese dialecto. La reautenticación salía sin bloqueo y 8 intentos
  simultáneos pasaban todos el límite. Corregido con el hint de tabla `WITH (UPDLOCK, ROWLOCK)`, igual que el resto del backend, y cubierto por
  `test_reautenticacion_sqlserver.py`. **Sin SQL Server, esto no se habría detectado.**
- **Corte de la purga de auditoría 3 horas antes del plazo** (`ab6327f`). Corregido y verificado en SQL Server sin borrar nada.
- **Dos pruebas de telemetría con variable de otra prueba** (`NameError`, heredado de `a3908c0`). Corregidas sin cambiar lo que verifican.

## Limitaciones de auditoría

- **Crecimiento sin límite para cuentas identificadas.** Cada intento rechazado sobre una cuenta identificada deja una fila. Sin plazo activado, no hay límite de crecimiento.
- **Purga desactivada.** Plazo propuesto: 12 meses. Activarla exige `RETENTION_APPROVAL_REFERENCE` (aprobación legal, pendiente) y verificar la purga en la base real.
- **Pérdida por desborde.** Si la cola de auditoría supera 200 pendientes, el detalle de esos intentos no se escribe; queda contado en memoria y en el log (`Cola auditoria-limite llena`).
- **Pérdida por fallo o caída.** Un fallo de escritura se registra en el log (`No se pudo auditar el intento bloqueado por el límite`) y no se reintenta.
  Una caída del proceso pierde como máximo 200 pendientes por proceso.
- **Varias réplicas.** Cada proceso tiene sus colas. El límite de login es en memoria: solo es exacto con un proceso (la imagen lo fuerza; una prueba lo verifica).
- **Reautenticación.** Cada fallo deja una fila extra `REAUTENTICACION_CONTADOR`, además de la fila de la operación.
- **Login correcto.** No reinicia el límite por origen (más estricto que `a3908c0`; decisión de diseño).
- **Trazabilidad.** `AuditoriaContexto` conserva IP y agente 90 días (`AUDIT_CONTEXT_RETENTION_DAYS`); los intentos sin cuenta guardan solo HMAC.

## Origen, cabeceras no confiables y ataques distribuidos

Detalle y pruebas: [VERIFICACION_ORIGEN_Y_ATAQUES_DISTRIBUIDOS_2026-11-08.md](VERIFICACION_ORIGEN_Y_ATAQUES_DISTRIBUIDOS_2026-11-08.md).

- Con la configuración por defecto y un par que no está en `TRUSTED_PROXY_CIDR`, Nginx **descarta** la `X-Forwarded-For` del cliente.
- Si el par que ve Nginx **está** en la lista de confianza, **acepta** lo que mande el cliente: el origen se puede forjar.
  La lista por defecto (`172.16.0.0/12`) cubre toda la red de Docker. **Riesgo a cerrar antes de desplegar:** fijar `TRUSTED_PROXY_CIDR` a la IP exacta del proxy
  y confirmar que Tailscale Serve reemplaza (o añade a la derecha) `X-Forwarded-For`.
- El backend directo (`FORWARDED_ALLOW_IPS="*"`) acepta cualquier origen de cualquier par que lo alcance. No está publicado; debe fijarse a la IP de Nginx.
- **Ataques distribuidos (riesgo residual aceptado):** el límite es por (cuenta, origen). Con N orígenes, un atacante obtiene hasta 5·N intentos por cuenta cada 15 min.
  La defensa en esa escala es la fortaleza de la contraseña y la MFA. Controles complementarios propuestos (límite global alto por cuenta, verificación adicional, reputación en el edge) **no incorporados**, para decisión posterior.

## Procedimiento de respaldo

No hay migración de base de datos en esta rama. Antes del despliegue:

1. Respaldo completo de la base de producción, verificado (ver `database/respaldos` y `docs/BASE_DE_DATOS.md`):
   `BACKUP DATABASE [GlucoLume] TO DISK = N'<ruta>' WITH COPY_ONLY, CHECKSUM, COMPRESSION;` seguido de
   `RESTORE VERIFYONLY FROM DISK = N'<ruta>' WITH CHECKSUM;`. La protección de la clave de respaldo con DPAPI en Windows no se validó aquí.
2. Registrar las imágenes actuales (`docker images`) y una copia cifrada del `.env` vigente (no va al repo).
3. Verificar que `docker/db.env` y `.env` existen con sus valores de producción (este cambio no los modifica).

## Procedimiento de despliegue y rollback (no ejecutado)

```bash
GLUCOLUME_VERSION=<nueva> docker compose -f compose.yaml -f compose.prod.yaml build backend frontend
GLUCOLUME_VERSION=<nueva> docker compose -f compose.yaml -f compose.prod.yaml up -d backend frontend
```

**Rollback** (sin cambios de base de datos que revertir):

```bash
GLUCOLUME_VERSION=<anterior> docker compose -f compose.yaml -f compose.prod.yaml up -d backend frontend
```

La versión anterior ignora las filas `REAUTENTICACION_CONTADOR` (son solo inserciones) y el límite en memoria del login no depende de la base.
Restaurar el respaldo solo si hay corrupción de datos.

## Plan de validación posterior al despliegue

1. `GET /api/v1/healthz` (público) y `GET /api/v1/readyz` desde la red interna (desde fuera, Nginx responde 404).
2. Ingreso con contraseña válida e inválida; cinco fallos desde el mismo origen bloquean ese origen 15 min; el titular entra desde otro origen.
3. Reautenticación: tres fallos en 15 min bloquean solo esa operación; el login sigue; un reinicio del backend no libera el bloqueo.
4. Operaciones sensibles: cambio de contraseña, borrado de cuenta, recuperación de MFA, borrado y reapertura de institución, operaciones de plataforma.
5. SPA: acceso directo y recarga de `/login`, `/app/inicio`, `/plataforma/dashboard`, `/consejos/abc`; `/cuenta` y `/nonexistent-xyz` responden 404.
6. Cabeceras con el edge real: CSP, HSTS de 30 días sin `includeSubDomains`, COOP/CORP en la SPA y no en la API.
7. **Origen:** con la cadena de proxies final, un pedido con `X-Forwarded-For` forjada no cambia el origen registrado (comandos en el documento de origen).
8. Auditoría: las filas `REAUTENTICACION_CONTADOR` aumentan solo con fallos reales; los rechazos del límite aparecen como `LOGIN_LOCAL/CUENTA_BLOQUEADA`.
9. Logs: buscar `Cola avisos-limite llena`, `Cola auditoria-limite llena` y `No se pudo auditar`.
10. Crecimiento de `Auditoria` durante una semana.

## Riesgos residuales

| # | Riesgo | Tratamiento |
|---|---|---|
| 1 | Origen forjable si el par que ve Nginx está en `TRUSTED_PROXY_CIDR` (por defecto, toda la red de Docker) | **Precondición de despliegue**: fijar la IP exacta del proxy; verificar Tailscale Serve |
| 2 | Backend directo con `FORWARDED_ALLOW_IPS="*"` | **Precondición de despliegue**: fijar a la IP de Nginx |
| 3 | Ataques distribuidos: 5·N intentos por cuenta cada 15 min | Aceptado; controles complementarios propuestos, no incorporados |
| 4 | Crecimiento de la auditoría de cuentas identificadas | Aceptado hasta aprobar la purga; plazo propuesto 12 meses |
| 5 | Purga desactivada; falta `RETENTION_APPROVAL_REFERENCE` | No bloquea la integración (la purga no modifica datos) |
| 6 | Pérdida de intentos por desborde o caída del proceso | Registrado en log; sin reintento |
| 7 | Reautenticación de cuentas solo Google en plataforma: MFA o código por correo, sin contraseña | Diseño vigente; a documentar para la operación |
| 8 | Edge (Caddy `https`, Tailscale) sin verificar en el servidor | Precondición de despliegue |
| 9 | B-4 (`Caddyfile`, HSTS en edge) y B-5 (HTTP/2, COEP no habilitado) | Pendientes de verificación en el edge |
| 10 | M-4: tokens en la URL de cuatro flujos | Diseño pendiente de aprobación; sin cambios de código |
| 11 | Anexo C: scripts listos, no ejecutados en el servidor | Pendiente; solo lectura cuando se ejecute |
| 12 | Esquemas `LocalCredentialCreate/Update` sin uso | Limpieza posterior; sin rutas |
| 13 | Pruebas sensibles al reloj en la línea base | Misma base y entorno en la comparación; fijar zona horaria en CI |

## Qué no cubre esta verificación

- Edge real (Tailscale, Caddy, HTTP/2, HSTS en producción).
- Instancia de SQL Server de producción (Windows): solo un motor 2022 CU16 Express en Linux descartable.
- Respaldos con DPAPI en Windows.
- Anexo C en el servidor.
- Google y SMTP reales (simulados en pruebas).
