# Verificación de las correcciones de la auditoría del 07/11/2026

Fecha de la verificación: 08/11/2026 (corridas del 07 al 08/11, en el banco de trabajo).
Rama: `claude/intelligent-keller-ujcsuf`, HEAD `1db54a6`. Base de la auditoría: `a3908c0`.

## 0. Qué significa cada nivel de verificación

Cada corrección se evalúa en tres niveles distintos. Ninguno implica los anteriores.

| Nivel | Qué se demuestra | Qué **no** demuestra |
|---|---|---|
| **Código corregido** | El cambio está en un commit de la rama y aparece en el diff. | Que funcione ni que haya sido probado. |
| **Pruebas superadas** | Las pruebas automatizadas, la medición en el banco y las pruebas de navegador pasan sobre el código de la rama. | Comportamiento en el servidor, con SQL Server real, con el borde de Tailscale ni con Google. |
| **Despliegue verificado** | El servidor de demostración sirve la versión corregida y se midió allí. | **Nada de esto se ha hecho.** No se tocó el servidor ni sus imágenes. |

Todas las conclusiones de este documento son de los dos primeros niveles. **Ninguna corrección está desplegada ni verificada en el servidor.**

## 1. Resultado final por hallazgo

Estados: CORREGIDO = código + pruebas; PARCIAL = código + pruebas con parte pendiente o con regresión abierta; PENDIENTE = sin corrección en la rama.

| Hallazgo | Código (commits) | Pruebas superadas | Despliegue | Resultado final |
|---|---|---|---|---|
| M-1 `/api` redirige con puerto interno | `6b8b7a5` (+`446f967`) | Matriz Nginx (`Location: /api/` relativo, 308); `verificar-rutas` 17/17; `test_security_hardening` | No | **CORREGIDO** (en la rama) |
| M-2 Enumeración y bloqueo de cuenta por terceros | `bd525e3` | Límites por cuenta y origen; concurrencia; alerta verificada en el umbral vigente. **Tres pruebas de la versión anterior fallan** (regresión, secciones 3.1 y 6.1) | No | **PARCIAL** |
| M-3 Argon2 sin límite de concurrencia | `1931580` (+`446f967`) | `test_argon2_gate` (17); flujos de auth (259) | No | **CORREGIDO** (en la rama) |
| M-4 Tokens en URL y sesiones | — | — | — | **PENDIENTE** (requiere aprobación del diseño) |
| B-1 Tamaño del cuerpo sin límite por operación | `df48716` | `test_tamano_solicitudes` (14); medición Nginx antes/después | No | **CORREGIDO** (en la rama) |
| B-2 Soft 404 de la SPA | `fb1686f` | `test_rutas_spa` (46); navegador 18/18 (antes 13/18); matriz de 49 rutas | No | **PARCIAL** (subrutas de `/app` y `/plataforma`; correos a `/cuenta/*`) |
| B-3 Cabeceras de seguridad duplicadas | `68a0442` (+`446f967`) | Matriz de cabeceras: cada una aparece una vez en API y SPA | No | **CORREGIDO** (en la rama) |
| B-4 HSTS y redirección | `a1b0b6e` | `test_hsts` (10); matriz de 24 combinaciones; 259 de flujos | No | **PARCIAL** (Caddy pendiente de validar; el 302 del borde no se pudo verificar) |
| B-5 COOP/CORP y HTTP/2 | `b7fcf0a` | `test_aislamiento_origenes` (4); navegador 9/9 | No | **PARCIAL** (COEP y HTTP/2 en el borde pendientes) |
| B-6 Monitoreo de salud | `e8e4535` (+`1db54a6`) | `test_readyz` (10, estable en paralelo); `/readyz` 404 por Nginx y 503 directo | No | **CORREGIDO** (en la rama) |
| B-7 Monitoreo de CSP | `a665ac7` | `test_csp_reports` (27); navegador: 0 reportes en uso normal, 2 en violación provocada | No | **CORREGIDO** (en la rama; la alerta sigue pendiente) |
| Anexo C Infraestructura | `069ef6e` (solo diagnóstico) | Solo sintaxis y humo en el banco | No | **PENDIENTE** (depende del servidor) |

## 2. Evidencia de la causa raíz tratada

Para cada hallazgo, la causa identificada en la auditoría y la medición que lo confirma. Las mediciones están en `docs/auditorias/evidencias/auditoria_seguridad_2026-11-07/`.

- **M-1.** Causa: Nginx construía `Location` con `$scheme` y el puerto de escucha interno. Medido: `/api` con `Host` de Tailscale devuelve `308 Location: /api/` (relativo). Antes, `Location: http://<host>:8080/api/` (`resultados_redireccion_api_antes.txt` vs `_despues.txt`).
- **M-2.** Causa: el límite de intentos estaba ligado a la cuenta, y el bloqueo global permitía que un tercero bloqueara a la víctima. Medido: el bloqueo ahora es por par (cuenta, origen), con 5 fallos en 15 minutos y 15 en una hora. Las solicitudes simultáneas no superan el límite (`tests/test_login_lockout.py::test_solicitudes_simultaneas_no_superan_el_limite`, en verde en la corrida final). Verificado en el umbral vigente: el aviso `ACTIVIDAD_SOSPECHOSA` se dispara **una vez** y se envía **un correo**; los intentos siguientes no repiten ni el aviso ni el correo.
- **M-3.** Causa: Argon2 (64 MiB por verificación) sin tope de concurrencia. Medido: `bench_argon2` antes/después (`resultados_argon2_*.json`), y con el tope, los intentos por encima de 2 en curso y 8 en espera reciben `503 SERVIDOR_OCUPADO`. Costo por verificación sin cambios.
- **B-1.** Causa: un tope global de 1 MB para todas las operaciones. Medido: tope por operación (160 KB general, 16 KB auth, 768 KB ingesta, 384 KB muestras y offboarding). Un cuerpo por encima del límite responde `413` en JSON de la API (`resultados_tamano_cuerpo_antes.txt` vs `_despues.txt`).
- **B-2.** Causa: `location /` servía `index.html` para cualquier ruta, y el router redirige lo desconocido a la portada (soft 404). Medido: 11 de 49 rutas cambian; las desconocidas, `/.git/config`, `/phpinfo.php` y `/.env` pasan de `200` a `404` (`resultados_rutas_spa_antes.txt` vs `_despues.txt`).
- **B-3.** Causa: la CSP de la API se emitía en Nginx y en el backend, y el navegador aplica ambas. Medido: cada cabecera aparece una vez en la API, la SPA, `/docs` y el 404 (`verificacion_final/http_cabeceras_final_head.txt`).
- **B-4.** Causa: HSTS de un año con `includeSubDomains`, emitido también para `localhost`. Medido: solo cambia la columna HSTS de la matriz (`resultados_hsts_antes.txt` vs `_despues.txt`); en `localhost` deja de emitirse.
- **B-5.** Causa: sin COOP ni CORP. Medido: COOP y CORP `same-origin` en la SPA y los estáticos, y ausentes en la API (`resultados_aislamiento_cabeceras_antes.txt` vs `_despues.txt`). Entre dos orígenes reales, la transferencia de sesión llega al canje, y un estático cargado desde otro origen se bloquea.
- **B-6.** Causa: no existía readiness. Medido: `/api/v1/readyz` responde `404` por Nginx (no se publica) y `503 no_listo` directo al backend, con valores enumerados y sin versión ni cadenas de conexión.
- **B-7.** Causa: la CSP no tenía `report-uri`, así que un bloqueo no dejaba registro. Medido: 0 reportes en 11 páginas normales; 2 reportes sanitizados en una violación provocada, sin tokens en el log (`resultados_reportes_csp.txt`).
- **Anexo C.** Causa: no hay evidencia de estado del servidor en el repo. No hay corrección que verificar; el diagnóstico está preparado.

## 3. Resultados de las pruebas automatizadas

### 3.1 Backend (`pytest`, 4 workers)

| Corrida | Commit | Zona horaria | Pasan | Fallan | Saltan |
|---|---|---|---|---|---|
| A | `069ef6e` (antes de cualquier fix de readiness) | UTC del banco | 2477 | 89 | 203 |
| B | `069ef6e` + fix de timing en el árbol de trabajo | UTC del banco | — | 91 | 203 |
| **C (final)** | **`1db54a6`** (= árbol de trabajo con ambos fixes) | **America/Argentina/Buenos_Aires** | **2480** | **86** | **203** |

Los 86 fallos de la corrida final, clasificados (detalle en `verificacion_final/clasificacion_fallos_backend.tsv`):

- **83 preexistentes**: fallan igual en el commit base `a3908c0`. 78 de `test_emails.py`, 1 de `test_security_config.py`, 3 de `test_smtp_limits.py` y 1 de `test_patient_access.py`.
- **3 regresiones de M-2** (pasan en `446f967`, fallan desde `bd525e3`): ver secciones 3.1 y 6.1.

Los 203 saltos son todos pruebas opt-in de SQL Server (`TEST_SQLSERVER_CONFIRM=DESCARTABLE` más una base localhost). No se ejecutaron.

**Fallas corregidas en esta verificación (defectos de mis propias pruebas):**

- `test_readyz::test_concurrencia_de_sondeos…` era intermitente. La causa no era el tiempo de espera, como se había supuesto al principio: un sondeo de la prueba anterior seguía vivo, escribía un resultado viejo en el caché global y la prueba siguiente no disparaba su propio sondeo. Se corrigió en el fixture (`1db54a6`). Ahora pasa 10 de 10 aislada y en paralelo.

**Defectos preexistentes del arnés, no de la corrección:**

- `test_measurements` (2) y `test_audit` / `test_audit_security` (2): dependen de la zona horaria. Usan `date.today()` del proceso y la app usa la hora de Argentina; difieren entre las 00:00 y las 03:00 UTC. Pasan con `TZ=America/Argentina/Buenos_Aires` y fallan con UTC. **Fallan también en `a3908c0`.** No los introdujo esta serie.

### 3.2 Frontend (`vitest`)

- **856 pasan, 1 falla** (`PatientMeasure`, "última comida", timeout de 5,4 s). La falla se reproduce aislada. `frontend/src` no cambió desde `a3908c0`, así que es preexistente. Ver `verificacion_final/frontend_vitest.txt`.

### 3.3 Pruebas de comportamiento (HTTP y navegador) sobre el HEAD final

| Prueba | Resultado |
|---|---|
| Matriz de rutas (49) | Sin cambios respecto de la línea base de B-2 |
| Cabeceras (SPA, API, `/docs`) | Sin cambios respecto de B-5; cada cabecera de seguridad aparece una vez |
| HSTS (24 combinaciones) | Sin cambios respecto de B-4 |
| Reporte CSP por POST | 204 |
| `/api/v1/readyz` por Nginx | 404 |
| `/api/v1/readyz` directo al backend | 503 |
| Navegador: navegación, recarga, rutas desconocidas (B-2) | **18/18** |
| Navegador: aislamiento entre dos orígenes (B-5) | **9/9** |
| Navegador: reportes CSP (B-7) | Uso normal: 0 reportes, 0 violaciones. Violación provocada: 2 reportes, script no ejecutado. Cadenas sensibles en el log: 0 |

## 4. Pruebas que no pudieron ejecutarse

| Prueba | Motivo | Riesgo que deja sin cubrir |
|---|---|---|
| Pruebas SQL Server (203 saltos) | Requieren una instancia SQL Server descartable en localhost; no hay Docker ni SQL Server en el banco | Consultas y transacciones específicas de SQL Server, incluidas las de login y de jobs |
| Build de imágenes Docker y escaneo | No hay daemon de Docker en el banco | Que las imágenes construyan y su CVE del sistema operativo |
| `caddy validate` del `Caddyfile` | El binario descargado fue bloqueado por la política de ejecución; no se forzó | Que el perfil `https` arranque con el cambio de HSTS (propuesto, no aplicado) |
| Borde de Tailscale real | Fuera del repo y del banco | HSTS y redirección 302 en el borde, HTTP/2, COOP/CORP que añada el borde |
| Google OAuth de extremo a extremo | Sin credenciales ni `GOOGLE_*` configurados | El intercambio real con Google. Se probó solo la transferencia de sesión entre orígenes |
| Envío real de correo | Sin SMTP | Entrega de los correos de seguridad (los 78 de `test_emails` además fallan preexistentes) |
| Scripts del Anexo C `03` y `04` en contenedores reales | Sin Docker | Que las consultas y los comandos funcionen en el servidor |
| Navegadores distintos de Chromium | — | Comportamiento de COOP/CORP y de los reportes CSP en Firefox y Safari |
| Carga real de Argon2 | El banco no tiene la carga ni el hardware del servidor | Latencia y tasa de `503` bajo carga real |

## 5. Contratos de API

Comparación semántica de OpenAPI entre `a3908c0` y `1db54a6` (`verificacion_final/comparar_openapi.py`, `contratos_openapi_base_vs_head.txt`):

- **257 operaciones** en ambos: mismas rutas, métodos, parámetros, `requestBody.required` y códigos de respuesta. Ninguno cambió.
- **Restricciones de esquema que cambiaron (3):**
  - `LoginRequest.password`: `maxLength: 256` (nuevo, M-3).
  - `MfaRecoveryVerifyRequest.codigo` y `AccountMfaRecoveryVerifyRequest.codigo`: `maxLength: 16` (nuevo, B-1). El patrón de 6 dígitos no cambió.
- **Restricciones que ya existían** y que el informe presentó como nuevas: los límites de lotes (200 líneas, 512 caracteres, 2000 muestras, 300 reglas, 2000 asignaciones) estaban en `a3908c0`. No cambiaron.
- **Cambios que el OpenAPI no muestra:**
  - Nginx: tope de tamaño por operación (cuerpos mayores responden `413` JSON).
  - Código de error nuevo `SERVIDOR_OCUPADO` (503, M-3). El frontend lo muestra con su mensaje (`El servidor está procesando muchos ingresos…`), sin mapeo propio.
  - `/api/v1/readyz` responde 404 por Nginx y `/api/v1/security/csp-report` acepta POST con 204. Ninguna de las dos aparece en el esquema.
  - `/api` redirige a `/api/` relativo (308), que es compatible.
  - HSTS de 30 días sin `includeSubDomains`.

**Veredicto de compatibilidad:** compatible con los clientes actuales, con tres excepciones deliberadas:
1. Una contraseña de login de más de 256 caracteres responde `422` (antes `401`). Las contraseñas de registro siguen con su límite de 128.
2. Un código MFA de recuperación de más de 16 caracteres responde `422`. Los códigos válidos tienen 6 dígitos y no se afectan.
3. Los cuerpos por encima del límite de cada operación responden `413`. Ningún endpoint recibe archivos, y el mayor cuerpo legítimo medido (`calcular_tamanos_maximos`) entra en su límite.

## 6. Regresiones en autenticación, permisos y funcionalidades

### 6.1 Autenticación

Lo que cambió por diseño (M-2 y M-3):

- **Límite de login:** 5 fallos en 15 minutos y 15 en una hora, **por cuenta y origen**. Antes eran 3 por cuenta. El límite ya no bloquea la cuenta para terceros. El texto de ayuda y la documentación de usuario se actualizaron (`MANUAL_USUARIO.md`, `SEGURIDAD.md`).
- **Intentos bloqueados por el límite:** ya no generan un registro `INTENTO_INGRESO` en la bandeja del titular. Antes sí. Es un cambio de comportamiento visible, que una prueba existente exige.
- **Reconfirmación de contraseña** (`verifyCurrentPassword`, dentro de una sesión): **sigue bloqueando la cuenta a los 3 intentos.** Es una inconsistencia con el login. Pendiente de decisión.
- **`CUENTA_BLOQUEADA`:** se mantiene en el contrato, con `retryAfterSeconds`. El frontend lo sigue reconociendo.
- **`SERVIDOR_OCUPADO` (503):** nuevo, solo bajo saturación de Argon2.

Lo que se comprobó sin cambios:

- Emisión, rotación y revocación de tokens: ninguna función de tokens cambió. Las rutas de auth (`api/v1/auth.py`) y las cookies (`sessionCookie.py`) no tienen diff.
- Modelos y migraciones: no cambió ninguno. `grep` sobre el diff no encontró cambios de esquema.
- MFA, recuperación de contraseña, Google OAuth, cookie de refresh y login general: **259 pruebas en verde** (`test_auth_access*`, `test_google*`, `test_password*`, `test_mfa*`, `test_refresh_cookie`, `test_login_*`, `test_link_auth`).
- Anonymous access: con la base disponible, `/api/v1/auth/me`, `/measurements/{id}` y las rutas de pacientes responden `401` (verificado con la base sustituida por SQLite). La prueba `test_la_api_directa_sin_autenticacion` falla por el arnés, no por el control.

**Observación de diseño (no corregida):** en el orden de las dependencias, la conexión a la base se resuelve antes que la verificación de autenticación. Un anónimo puede disparar un intento de conexión. No es una vulnerabilidad, pero conviene saberlo para la carga.

### 6.2 Permisos

- Ningún módulo de permisos cambió: `RequirePermission`, roles de institución y permisos de plataforma están fuera del diff.
- Las pruebas de autorización de pacientes, mediciones y dispositivos pasan en la corrida final, salvo `test_patient_access` (preexistente).

### 6.3 Funcionalidades relacionadas

- **Navegación de la SPA**, acceso directo, recarga y rutas válidas: 18/18 en el navegador. Las rutas válidas no cambian.
- **Transferencia de sesión entre orígenes** (login en `localhost` → app): el código llega al canje y la app renderiza.
- **Subidas de archivos:** ningún endpoint recibe archivos, así que los topes nuevos de Nginx no las afectan.
- **Monitoreo externo:** `/api/v1/readyz` ya no es accesible por la URL pública. Un monitor debe llamar al backend directamente (`http://backend:8000/api/v1/readyz`).
- **HSTS de 30 días:** los navegadores que ya guardaron un año de HSTS lo reemplazan en su próxima visita por HTTPS.
- **COOP/CORP:** no afectan ningún flujo de la app (no hay popups ni `postMessage`).
- **SSE** (telemetría y muestras): reciben `Permissions-Policy` adicional. Sus pruebas pasan.

## 7. Archivos modificados

Lista completa en `verificacion_final/commits_y_archivos.txt`. Resumen:

- **Código backend (`backend/app`):** 14 archivos. Los más relevantes: `services/loginThrottle.py` (nuevo), `services/auth.py`, `core/security.py`, `core/config.py`, `api/rateLimit.py`, `api/securityHeaders.py`, `api/v1/health.py` (nuevo), `api/v1/cspReport.py` (nuevo), `services/readiness.py` (nuevo), `services/cspReports.py` (nuevo), `services/rateLimiter.py`, `schemas/auth.py`, `schemas/acquisition.py`, `api/errors.py`, `main.py`.
- **Pruebas (`backend/tests`):** 13 archivos modificados o nuevos, de ellos 8 nuevos. Nuevos: `test_login_throttle.py`, `test_argon2_gate.py`, `test_tamano_solicitudes.py`, `test_readyz.py`, `test_rutas_spa.py`, `test_csp_reports.py`, `test_hsts.py`, `test_aislamiento_origenes.py`.
- **Nginx y frontend:** `docker/nginx/default.conf.template`, `frontend/Dockerfile` (un valor de upstream que apuntaba al puerto equivocado).
- **Configuración:** `.env.example` (variables de Argon2, opcionales con valor por defecto).
- **Documentación:** `docs/DESPLIEGUE.md`, `docs/SEGURIDAD.md`, `docs/MANUAL_USUARIO.md`, `docs/funcional/INDIVIDUAL.md`, `docs/tif/relevamiento_requisitos/02_REGLAS_NEGOCIO.md` (textos del nuevo límite de login), la guía de corrección y las evidencias.

No se modificó ningún `compose*.yaml`, ni migraciones, ni modelos, ni el frontend de la aplicación (`frontend/src`).

## 8. Commits

| Commit | Hallazgo |
|---|---|
| `446f967` | M-1, M-3, B-1, B-3, B-6 (primera tanda, sesión anterior) |
| `bd525e3` | M-2 |
| `1931580` | M-3 |
| `6b8b7a5` | M-1 |
| `68a0442` | B-3 |
| `df48716` | B-1 |
| `e8e4535` | B-6 |
| `fb1686f` | B-2 |
| `a665ac7` | B-7 |
| `a1b0b6e` | B-4 |
| `b7fcf0a` | B-5 |
| `069ef6e` | Anexo C (solo diagnóstico) |
| `1db54a6` | Verificación: aislamiento del estado de readiness en las pruebas |

Ningún commit se ha desplegado.

## 9. Procedimiento de rollback

**En el repositorio.** Revertir la serie con commits nuevos, nunca con `reset` ni con `push --force`:

```bash
git checkout claude/intelligent-keller-ujcsuf
git revert --no-commit a3908c0..HEAD
git commit -m "Revertir la remediación de la auditoría del 07/11/2026"
git push -u origin claude/intelligent-keller-ujcsuf
```

**Ensayo de este rollback:** se ejecutó en un worktree desechable. No hubo conflictos, y el código de producción (`backend/app`, `docker`, `frontend`) y las pruebas quedaron **idénticos** a `a3908c0`. No se confirmó nada en la rama. Ver `verificacion_final/rollback_ensayo.txt`.

**Rollback parcial por hallazgo.** Cada uno se revierte por su commit (tabla de la sección 8), o por la línea que cambió (ver la sección correspondiente de la guía de corrección). Es seguro, porque los commits posteriores tocan la plantilla de Nginx, así que revertir uno suelto puede generar conflictos y debe probarse.

**En el servidor (cuando se despliegue).** No aplica todavía, porque nada se ha desplegado. Cuando se despliegue:

- No hay cambios en Compose, en la base ni en las variables obligatorias. El rollback es volver a la **imagen anterior**: `GLUCOLUME_VERSION=<versión previa>` con `docker compose -f compose.yaml -f compose.prod.yaml up -d`.
- La plantilla de Nginx va dentro de la imagen del frontend, así que hay que revertir esa imagen.
- Antes de desplegar, conservar la etiqueta anterior y el `.env` actual.

## 10. Riesgos residuales

| Riesgo | Gravedad | Mitigación actual | Pendiente |
|---|---|---|---|
| El límite por origen no frena un ataque distribuido desde muchas IP contra una misma cuenta | Media | Límite por cuenta y origen, sin bloqueo global | Decisión sobre umbral y alerta (M-2) |
| Reconfirmación de contraseña bloquea la cuenta a los 3 intentos, mientras el login usa límites por origen | Media | Requiere sesión activa | Decisión (sección 6.1) |
| Argon2 bajo carga real puede responder `503` a logins legítimos en picos | Media | Tope configurable (`ARGON2_MAX_CONCURRENT`, `ARGON2_MAX_WAITING`) | Medir en el servidor |
| Sistema operativo de la imagen del backend con zlib y 44 HIGH sin parche de Debian | Media | Contenedor de solo lectura, sin puertos, usuario no root | Reconstruir cuando Debian publique la corrección (H-10) |
| La base de la imagen no se ha vuelto a escanear desde el 23/10/2026 | Media | — | Escaneo de las imágenes desplegadas (Anexo C) |
| B-2: subrutas inexistentes de `/app` y `/plataforma` siguen con 200 | Baja | El router las redirige al inicio de la sección | Tabla de rutas privadas o manifiesto |
| B-2: correos de seguridad apuntan a `/cuenta/seguridad`, que no existe | Baja | Caen en la portada (sin cambio) | Decisión de producto sobre el destino |
| B-4: el `Caddyfile` del perfil `https` conserva el HSTS anterior | Media | Propuesta lista en la guía | Validar con `caddy validate` en el servidor |
| B-4 y B-5: el borde de Tailscale puede añadir sus propias cabeceras o su redirección 302 | Baja | — | Medir en el servidor |
| B-6: `/readyz` se oculta en Nginx, así que los monitores deben usar la red interna | Baja | Documentado | Confirmar la configuración del monitor |
| B-7: reportes CSP sin alerta; el endpoint es público y puede contaminar el log | Baja | Sanitización, tope por IP, rotación de logs | Decisión sobre alerta |
| Anexo C: estado real del servidor desconocido (parches, puertos, grupo docker, cifrado del disco, Tailscale, SSH) | Alta | Diagnóstico preparado | Ejecutar los scripts en el servidor |
| Respaldos de la base: solo hay procedimiento para Windows | Alta | — | Procedimiento Linux (Anexo C, fase 2) |
| 78 pruebas de correo y 1 de configuración fallan preexistentes | Media | — | Arreglar el entorno de pruebas de correo |
| `test_measurements`, `test_audit*` dependen de la zona horaria | Baja | Pasan con la zona de la aplicación | Corregir el arnés para usar `nowArgentina()` |

## 11. Resultado final

Ninguna corrección está desplegada ni verificada en el servidor. Los estados de la sección 1 corresponden a código en la rama y pruebas en el banco.

- **CORREGIDO** (en la rama): M-1, M-3, B-1, B-3, B-6, B-7.
- **PARCIAL**: M-2, B-2, B-4, B-5.
- **PENDIENTE**: M-4, Anexo C.
- **NO REPRODUCIDO**: ninguno.

La guía de corrección (`CORRECCIONES_AUDITORIA_SEGURIDAD_2026-11-07.md`) se actualizó para reflejar estos estados.
