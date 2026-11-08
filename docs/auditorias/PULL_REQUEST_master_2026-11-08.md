# Remediación de la auditoría de seguridad del 07/11/2026 (M-1 a M-3, B-1 a B-7, Anexo C pendiente)

**Rama:** `claude/intelligent-keller-ujcsuf` → **master**. Commit de referencia: `2981130`. Base de comparación: `a3908c0`.

> Este PR **no** se fusiona ni se despliega hasta que se confirmen los pendientes de la sección «Riesgos y pendientes» (en particular la
> ejecución de las pruebas de SQL Server en un entorno descartable con driver ODBC).

## Resumen

Cierra los hallazgos de la auditoría del 07/11/2026 que se pueden corregir en el código, sin cambiar el esquema de base de datos ni
modificar el servidor. Cambios principales:

- **M-2 (login y reautenticación).** El login se limita por (cuenta, origen): 5 fallos en 15 min y 15 en 1 h, sin bloquear la cuenta
  para terceros. La reautenticación de operaciones sensibles cuenta sus fallos en la auditoría, por operación y usuario (3 en 15 min), y
  sobrevive a reinicios y a varias réplicas. Cada intento rechazado deja una fila de auditoría; las colas de escritura están acotadas.
- **M-3 (Argon2).** Control de concurrencia (2 en curso, 8 en espera, 503 con `Retry-After`) sin cambiar el coste del hash.
- **M-1, B-1, B-3, B-5, B-6, B-7.** Redirección relativa de `/api`, tope de cuerpos por operación, cabeceras de seguridad sin duplicar,
  COOP/CORP en la SPA, readiness interna, y registro sanitizado de incumplimientos de CSP.
- **B-2 (rutas de la SPA).** Mapa de rutas de Nginx generado desde el router (`App.jsx`), con prueba de sincronía; rutas inexistentes y
  archivos sensibles responden 404; los enlaces de seguridad de los correos apuntan a la ruta real por tipo de cuenta.
- **B-4.** HSTS de 30 días sin `includeSubDomains` ni emisión en `localhost` (Nginx). El `Caddyfile` del perfil `https` queda pendiente.

Detalle por hallazgo y estado: [CORRECCIONES_AUDITORIA_SEGURIDAD_2026-11-07.md](CORRECCIONES_AUDITORIA_SEGURIDAD_2026-11-07.md).

## Alcance: 143 archivos entre `a3908c0` y `2981130`

| Área | Archivos | Contenido |
|---|---|---|
| Backend, código | 22 | `auth.py` (M-2: límite, reautenticación, auditoría, colas acotadas), `loginThrottle.py`, `rateLimiter.py`, `auditRetention.py` (corte de purga en hora de Argentina), `platform*.py`, `institution.py`, `mfa*.py`, `accountDeletion.py`, `email.py` (enlaces de seguridad por tipo de cuenta), `api/*` (cabeceras, errores, rate limit, CSP report, readiness) |
| Backend, pruebas | 22 | Nuevas: `test_login_m2_reglas.py`, `test_readyz.py`, `test_hsts.py`, `test_argon2_gate.py`, `test_rutas_spa.py`, `test_csp_reports.py`, `test_tamano_solicitudes.py`, `test_aislamiento_origenes.py`, `test_login_throttle.py`, `test.env.example`; modificadas: `conftest.py` (zona horaria fija, avisos en línea), `test_login_lockout.py`, `test_account_deletion.py`, `test_audit_security.py`, `test_auth_access_flows.py`, entre otras |
| Frontend | 6 | `App.jsx` (redirecciones `/cuenta/seguridad` y `/cuenta/notificaciones/desuscribir`), `Dockerfile` (genera el mapa de rutas en la build), `package.json` y lock (`@babel/parser` como devDependency), `scripts/generar-rutas-spa.mjs` y su prueba |
| Docker / Nginx | 2 | `docker/nginx/default.conf.template` (mapa `$ruta_spa` incluido, CSP/HSTS/COOP por ubicación), `docker/nginx/rutas-spa.generado.conf` (copia versionada del mapa) |
| Documentación y evidencias | 90 | Correcciones, verificación final, evidencias de cada hallazgo, scripts de sondas, Anexo C (diagnóstico de solo lectura), esta etapa |
| Raíz | 1 | `.env.example`: variables de Argon2 |
| Documentación de reglas de negocio | 2 | `docs/tif/.../02_REGLAS_NEGOCIO.md` e `docs/funcional/INDIVIDUAL.md`: reflejan el nuevo límite de login (5 por origen) |

**Base de datos:** no hay scripts SQL nuevos ni cambios de esquema en esta rama. El ledger de reautenticación usa la tabla `Auditoria`
(acción nueva `REAUTENTICACION_CONTADOR`, sin `CHECK` sobre la acción) y la cuenta de la aplicación solo necesita `INSERT` y `SELECT` ahí.

## Pruebas

**Backend** (`pytest -n 8`, mismo entorno sintético para la base y la rama):

| | Pasadas | Fallidas | Omitidas |
|---|---|---|---|
| `a3908c0` | 2403 | 1 (`test_patient_access`, acceso anónimo: 500 por SQL Server real) | 203 |
| `2981130` | 2584 | 0 | 203 |

- Regresiones nuevas por identificador: **0**. Corregidas: `test_patient_access::test_la_api_directa_sin_autenticacion_es_rechazada`.
- Agregadas: 184. Eliminadas: 11, con equivalencia documentada en [EQUIVALENCIA_PRUEBAS_ELIMINADAS_2026-11-08.md](EQUIVALENCIA_PRUEBAS_ELIMINADAS_2026-11-08.md).
- Omitidas en ambas: 203 (192 requieren SQL Server descartable; 11 requieren `TEST_SQLSERVER_RET_URL`). **No ejecutadas en esta verificación.**

**Frontend** (vitest, por identificador): sin regresiones. Una falla preexistente en ambas versiones (`PatientMeasure`, timeout).
8 pruebas agregadas (generador de rutas).

**SQL Server (descartable, 2022 CU16):** ver [SQLSERVER_DESCARTABLE_2026-11-08.md](SQLSERVER_DESCARTABLE_2026-11-08.md). Confirmado: `CK_TokenCuenta_tipo`
compatible con el enum, bloqueo `UPDLOCK` serializado, lecturas no bloqueadas, persistencia tras reinicio, rollback ante error,
permisos de auditoría (UPDATE/DELETE rechazados a la aplicación), y el corte de retención corregido.

**Compose y Nginx:**
- Los seis archivos `compose*.yaml` validan con `docker compose config` (base + prod, dev, retención, serial; redis con un valor ficticio
  en la copia, porque `REDIS_PASSWORD` es obligatoria por diseño).
- La plantilla de Nginx renderizada pasa `nginx -t` (Nginx 1.24, banco local). La versión de Nginx de la imagen de producción no se verificó aquí.

## Procedimiento de respaldo

No hay migración de base de datos en esta rama. Antes del despliegue:

1. Respaldo completo de la base de producción, verificado (ver `database/respaldos` y `docs/BASE_DE_DATOS.md`):
   `BACKUP DATABASE [GlucoLume] TO DISK = N'<ruta>' WITH COPY_ONLY, CHECKSUM, COMPRESSION;` seguido de `RESTORE VERIFYONLY FROM DISK = N'<ruta>' WITH CHECKSUM;`.
   La protección de la clave de respaldo con DPAPI en Windows no se validó en este entorno.
2. Registrar la versión actual de las imágenes (`docker images`) y una copia cifrada del `.env` vigente (no va al repo).
3. Verificar que `docker/db.env` y `.env` existen con sus valores de producción (no se modifican en este cambio).

## Procedimiento de despliegue y rollback

**Despliegue** (no ejecutado):
```bash
GLUCOLUME_VERSION=<nueva> docker compose -f compose.yaml -f compose.prod.yaml build backend frontend
GLUCOLUME_VERSION=<nueva> docker compose -f compose.yaml -f compose.prod.yaml up -d backend frontend
```

**Rollback** (sin cambios de base de datos que revertir):
```bash
GLUCOLUME_VERSION=<anterior> docker compose -f compose.yaml -f compose.prod.yaml up -d backend frontend
```
La versión anterior ignora las filas `REAUTENTICACION_CONTADOR` (son solo inserciones) y el límite en memoria del login no depende de la
base. Restaurar el respaldo solo si hay corrupción de datos; el rollback de código no lo requiere.

## Plan de validación posterior al despliegue

1. `GET /api/v1/healthz` (público, liveness) y `GET /api/v1/readyz` desde la red interna (no desde el exterior; Nginx responde 404).
2. Ingreso con contraseña válida e inválida; cinco fallos desde el mismo origen bloquean ese origen 15 min; la cuenta sigue accesible desde otro origen.
3. Reautenticación: tres fallos en 15 min bloquean solo esa operación; el login sigue disponible; un reinicio del contenedor backend no libera el bloqueo.
4. Operaciones sensibles: cambio de contraseña, borrado de cuenta, recuperación de MFA, borrado y reapertura de institución, plataforma.
5. SPA: acceso directo y recarga de las rutas de primer nivel (`/login`, `/app/inicio`, `/plataforma/dashboard`, `/consejos/abc`); `/cuenta` y `/nonexistent-xyz` responden 404.
6. Cabeceras con el edge real: CSP, HSTS de 30 días sin `includeSubDomains`, COOP/CORP en la SPA y no en la API.
7. Auditoría: las filas `REAUTENTICACION_CONTADOR` aumentan solo con fallos reales; los intentos rechazados por el límite aparecen como `LOGIN_LOCAL/CUENTA_BLOQUEADA`.
8. Logs del backend: buscar `Cola avisos-limite llena` y `Cola auditoria-limite llena` (pérdida por desborde) y `No se pudo auditar` (fallo de persistencia).
9. Crecimiento de la tabla `Auditoria` durante una semana (ver riesgo 3).

## Riesgos y pendientes

1. **Pruebas de SQL Server sin ejecutar en esta verificación:** 203 pruebas omitidas (`*_sqlserver`, concurrencia del ciclo de vida). Bloqueo técnico
   del entorno: falta el driver ODBC del host. Deben ejecutarse en una base descartable antes del merge (procedimiento en `docs/BASE_DE_DATOS.md` §6).
2. **Purga de auditoría desactivada.** Plazo inicial propuesto: 12 meses para registros de seguridad. Activarla requiere `AUDIT_RETENTION_MONTHS=12`
   **y** `RETENTION_APPROVAL_REFERENCE` (aprobación legal, H-04). Antes de activarla: verificar en la base real que las filas escritas por la
   aplicación tienen la hora de Argentina (`SELECT TOP 5 fechaHora, sysutcdatetime() FROM Auditoria ORDER BY fechaHora DESC`). Las filas
   insertadas fuera de la aplicación (scripts con el `DEFAULT` UTC) vencen 3 horas más tarde: lado seguro.
3. **Crecimiento de la auditoría de cuentas identificadas.** Cada intento rechazado sobre una cuenta identificada deja una fila; el límite HTTP
   por IP (60 por 10 min) acota por origen, no globalmente. Sin el plazo activado, el crecimiento es ilimitado para esas filas.
4. **Ataque distribuido.** Los límites son por (cuenta, origen): N orígenes generan hasta 5 fallos cada uno. Un tope global por cuenta
   reintroduciría el bloqueo entre orígenes que M-2 pidió evitar. Decisión pendiente.
5. **Colas de auditoría (por proceso).** Hasta 200 pendientes por cola. Un desborde no escribe el detalle del intento (queda contado y en el log).
   Un fallo de escritura se registra y no se reintenta. Una caída del proceso pierde los pendientes (como máximo 200 por proceso).
6. **Reautenticación por operación.** Cada fallo deja una fila extra (`REAUTENTICACION_CONTADOR`) además de la fila de la operación. Es el costo
   de contar sin cambiar el esquema.
7. **Cuentas solo Google en plataforma.** La reautenticación de una cuenta sin credencial local se confirma con MFA o código por correo, no con contraseña.
8. **Login correcto no reinicia el límite por origen.** Es un cambio de diseño respecto de `a3908c0`, y el más estricto.
9. **Esquemas sin uso:** `LocalCredentialCreate` y `LocalCredentialUpdate` no tienen rutas. Se pueden retirar en otra etapa.
10. **M-4** (tokens en la URL de cuatro flujos): diseño pendiente de aprobación; sin cambios de código.
11. **B-4 (HSTS en el edge real):** el `Caddyfile` del perfil `https` no se validó en el servidor. Pendiente.
12. **B-5:** COEP no se habilitó (falta el inventario de recursos). HTTP/2 pendiente de verificar en el edge real.
13. **Anexo C:** los cuatro scripts están listos y revisados (solo lectura; `04` ya no expone la contraseña en la lista de procesos), pero no se ejecutaron en el servidor.
14. **Pruebas dependientes del reloj:** en la línea base aparecieron fallos de zona horaria que no se reproducen en todas las corridas. No afectan la comparación porque se usó el mismo entorno, pero conviene fijar la zona horaria del entorno de CI.

## Bloqueo técnico para integrar

**No se identificó ningún defecto de código abierto.** Las regresiones contra `a3908c0` son cero en las pruebas que se pueden ejecutar aquí.
Lo que falta para considerar validado el despliegue es verificación, no corrección: las 203 pruebas de SQL Server (riesgo 1) y la
verificación del edge (riesgos 11 y 12). Sin esas dos, el merge es técnicamente posible pero la validación queda incompleta.
