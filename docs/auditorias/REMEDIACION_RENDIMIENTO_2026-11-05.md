# Informe de remediación de rendimiento de GlucoLume — 5 de noviembre de 2026

> **Documento separado de la auditoría.** Las mediciones originales de `docs/auditorias/RENDIMIENTO_2026-11-05.md` no se modifican.
> Este informe registra qué se implementó, cómo se midió y qué queda pendiente.
> **Exposición:** miércoles 11 de noviembre de 2026. **Ningún cambio está integrado, desplegado ni mergeado.** Todo requiere validación y autorización expresa.

---

## 0. Resumen ejecutivo

- Se verificó cada hallazgo contra el código vigente. La auditoría sigue siendo válida salvo dos puntos: **H-08 en resultados ya no aplica** (se corrigió después de la auditoría) y **H-19 también afecta a la analítica de pacientes**.
- Se implementaron **4 correcciones**, cada una en su commit:

| Hallazgo | Corrección | Clase | Estado | Medición principal |
|---|---|---|---|---|
| H-09 | Banner de correo de 1,35 MB a 112 kB | A | **VALIDADO** (laboratorio) | Mensaje de contacto: 1 829 630 → 159 297 bytes (−91,3 %) |
| H-07 | Consulta y confirmación de contacto en una sola conexión SMTP | B | **PENDIENTE DE VALIDACIÓN** | 20 → 10 conexiones SMTP por 10 consultas; p50 a RTT 50 ms y 2 Mbps: 16 230 → 2 117 ms (con H-09) |
| H-19 | Reglas de matriz del historial en lote (sin N+1) | B | **PENDIENTE DE VALIDACIÓN** (SQL Server) | 15 mediciones de glucosa: 34 → 6 consultas; semáforos idénticos |
| H-18 | Contadores del dashboard del operador en una pasada | B | **PENDIENTE DE VALIDACIÓN** (SQL Server) | Dashboard del operador: 23 → 18 consultas; contadores idénticos |

- **Pruebas:** suite completa del backend sobre el árbol modificado: **2 370 pasan, 3 fallan por entorno (ver §5.3), 203 omitidas**. La línea base de HEAD tiene los mismos fallos de entorno y 2 367 pasan. Las dos pruebas nuevas explican la diferencia de pasadas. No hay regresiones.
- **Qué no se tocó** (por consigna): `DB_MAX_CONCURRENT_CALLS`, número de workers, parámetros de Argon2, flujos de MFA, códigos de verificación, recuperación y confirmación de resultados, esquema, DDL, Docker, el servidor HP y `master`. No se enviaron correos reales.
- **Recomendación para la exposición:** integrar H-09 (bajo riesgo, ya validado) y, solo si pasan las validaciones de §6, H-07, H-19 y H-18. El resto queda para después (§7).

---

## 1. Preparación obligatoria

### 1.1 Rama y commit

| Dato | Valor |
|---|---|
| Rama de trabajo | `claude/gracious-hamilton-j2msck` (rama designada de la sesión; distinta de `master`) |
| Commit base (HEAD al iniciar) | `b608ead` (merge de `claude/amazing-clarke-p75731` en `master`) |
| `master` | `1e03322`, anterior a la rama; **no se modificó** |
| Árbol al iniciar | limpio |
| Commits de remediación | `3b398f3` (H-09), `c05e14d` (H-07), `1f4f131` (H-19), `df268d3` (H-18) |

**Decisión de rama.** La consigna pide una rama independiente, y las instrucciones de la sesión piden desarrollar en la rama designada. Se usó la rama designada, que ya es independiente de `master`, para no crear una rama adicional con otro nombre. No se hizo merge.

### 1.2 Soluciones ya implementadas (verificación)

| Afirmación de la auditoría | Estado en el código vigente |
|---|---|
| Tope de llamadas al driver `DB_MAX_CONCURRENT_CALLS = 2` | Presente (`core/config.py:55`), sin cambios |
| Argon2id con `m=64 MiB, t=3, p=4` | Presente (`core/security.py`, constantes `ARGON2_*`), sin cambios |
| Backend en Compose: 1 CPU y 512 MB; un solo proceso Uvicorn | Presente (`compose.yaml`, `backend/Dockerfile`), sin cambios |
| Streams SSE con `asyncio.sleep(0.2)` | Presente (`api/v1/telemetry.py:219`, `api/v1/acquisition.py:101`), sin cambios |
| `_executor` con 2 hilos y cola sin límite | Presente (`services/email.py`), sin cambios |
| Índice en `Medicion` que empiece por `idPerfilMedicion` | **No existe.** Revisado en `database/reference/GlucoLume_DB_v5.sql` (UTF-16). Solo hay `IX_Medicion_estado_fin`, que incluye `idPerfilMedicion` como columna `INCLUDE` y no sirve para búsquedas por esa clave |
| Índice en `Auditoria(tablaAfectada, accion, idRelacionado)` | **No existe.** Solo `IX_Auditoria_accion_fecha` (`accion`, `fechaHora`) |

### 1.3 Diferencias respecto de la auditoría

| Punto | Auditoría | Código vigente | Consecuencia |
|---|---|---|---|
| Commit auditado | `933d84c` en `claude/amazing-clarke-p75731` | Contenido en HEAD; 13 commits posteriores tocan correo, dashboard y notificaciones | Se revalidó todo lo afectado |
| **H-08, confirmación de resultados** | Envío síncrono en `resultEmailConfirmation.requestConfirmation` | Ya usa `emailService.runInBackground` (commit `47d8c1e`); la respuesta no espera SMTP | **DESCARTADO** (ya no aplica) |
| H-08, resto de flujos | MFA de recuperación, eliminación de cuenta, cambio de contraseña, administración de plataforma | Siguen síncronos (`mfaRecovery.py:164`, `accountDeletion.py:249`, `passwordChangeCode.py:103`, `platform.py:200/479`) | Restringido por la consigna: no se toca |
| H-19 | Historial de mediciones | También la analítica de pacientes (`patientAnalytics.py`, comparación con la matriz) tenía el mismo N+1 | Corregido en la misma corrección |
| H-18 | Más de 10 consultas repitiendo `performedAll` | Medido: 7 usos de la subconsulta en el dashboard del operador, separados en dos llamadas (`incluirGraficos`) por `47d8c1e` | Confirmado; se redujo a 2 pasadas |
| Referencias de línea | `institution.py:1424`, `platformInstitutions.py:94` | `institution.py:1426`, `platformInstitutions.py:98 y 228` | Solo cambió la numeración |
| H-09 | Banner de 1,35 MB | 1 348 681 bytes (`bannerCorreoGlucoLume.png`, 1536 × 650) | Confirmado |
| H-07 | Dos envíos en serie | Confirmado (`services/contact.py`); la API devuelve `confirmacionEnviada` | Confirmado y corregido sin cambiar el contrato |

### 1.4 Métricas iniciales (reproducibles)

Entorno de laboratorio: 4 vCPU compartidas; Python 3.13.18; dependencias de `requirements.txt` y `requirements-dev.txt` instaladas por hash en un entorno virtual fuera del repositorio. SQLite para pruebas de consultas; aiosmtpd con STARTTLS y AUTH como servidor SMTP **de pruebas**, con RTT y ancho de banda simulados por proxy TCP. Evidencia en `docs/auditorias/evidencias/remediacion_2026-11-05/`.

| Métrica | Línea base (HEAD `b608ead`) |
|---|---|
| Banner embebido | 1 348 681 bytes |
| Correo de contacto (MIME completo) | 1 829 630 bytes |
| Construcción del MIME, p50 | 11,14 ms |
| Conexiones SMTP por consulta de contacto | 2 |
| Consultas SQL del historial, 15 mediciones de glucosa | 34 |
| Consultas SQL del historial, 3 mediciones de glucosa | 10 |
| Consultas SQL del dashboard del operador, sin / con gráficos | 23 / 24 |
| Suite del backend, árbol completo de HEAD | 2 367 pasan, 4 fallan por entorno, 203 omitidas (ver §5) |

### 1.5 Pruebas automatizadas por módulo

| Módulo | Pruebas asociadas |
|---|---|
| Transporte SMTP (`integrations/email/sender.py`) | `test_security_config.py` (STARTTLS verificado), `test_email.py` |
| Servicio de correo y plantillas (`services/email.py`, `emails/`) | `test_emails.py`, `test_email.py`, `test_result_email.py`, `test_patient_result_email.py`, `test_user_notifications.py` |
| Contacto (`services/contact.py`, `api/v1/contact.py`) | `test_register_contact.py` |
| Eliminación de cuenta (fixture `mails`, flujo de correo) | `test_account_deletion.py` |
| Mediciones, historial, glucosa (`services/measurement.py`, `glucoseReference.py`) | `test_measurements.py`, `test_glucose_mode.py`, `test_measurement_lifecycle.py`, `test_matrices*.py`, **`test_historial_glucosa_consultas.py` (nuevo)** |
| Analítica de pacientes (`services/patientAnalytics.py`) | `test_patient_analytics.py` |
| Dashboards (`services/dashboard.py`) | `test_operator_panel.py`, `test_dashboards.py`, `test_dashboard_privacy.py`, `test_dashboard_multiple_measurements.py` |
| Autenticación, MFA, contraseñas (sin cambios) | `test_auth_access*.py`, `test_login_*.py`, `test_password_*.py`, `test_mfa_*.py` |
| Concurrencia y tope del driver (sin cambios) | `test_db_gate.py`, `test_stream_limits.py`, `test_lifecycle_concurrency.py` |

---

## 2. Correcciones implementadas

### 2.1 H-09 — Banner de correo embebido (clase A, **VALIDADO** en laboratorio)

- **Commit:** `3b398f3`. **Archivo:** `backend/app/emails/bannerCorreoGlucoLume.png` (sin cambios de código).
- **Causa técnica.** El banner se adjunta a cada correo como imagen `cid:`. Pesa 1,35 MB y se muestra a 600 px CSS (`base.html`, `width="600"`); la fuente tenía 1536 px. El mensaje MIME resultante pesaba 1,83 MB, casi todo banner.
- **Solución.** Reducción a 1200 px de ancho (2× para pantallas retina) y cuantización a paleta de 256 colores (FASTOCTREE). Se descartó MEDIANCUT (269 kB) y la versión de 1000 px (84 kB, menos nítida en retina). El canal alfa es opaco, así que no se pierde transparencia. Mismo nombre, así que `renderer.py` y las pruebas no cambian.
- **Latencia y tamaño (medido):**

| Medición | Antes | Después | Cambio |
|---|---|---|---|
| Banner (bytes) | 1 348 681 | 112 202 | −91,7 % |
| Correo de contacto recibido (bytes) | 1 829 630 | 159 297 | −91,3 % |
| Correo de confirmación (bytes) | 1 828 275 | 157 940 | −91,4 % |
| Construcción del MIME, p50 (CPU) | 11,14 ms | 3,04 ms | −72,7 % |
| Tamaño en memoria del mensaje | 1,83 MB | 0,16 MB | −91 % |

- **CPU/RAM:** se midió el tiempo de construcción y el tamaño del mensaje en memoria. **No se midió el RSS del proceso.**
- **Pruebas.** `test_email.py`, `test_emails.py` (incluida `test_banner_detecta_extension_real`) y `test_register_contact.py` pasan. Revisión visual de la imagen reducida: los colores se conservan; en degradados se nota ligera cuantización al hacer zoom, no a 600 px.
- **Riesgo residual.** Cuantización visible en degradados en pantallas grandes; algunos clientes de correo pueden bloquear imágenes incrustadas (igual que antes, sin cambio).
- **Estado:** **VALIDADO** en laboratorio (medición y pruebas). Pendiente solo la revisión visual en clientes reales.

### 2.2 H-07 — Contacto con una sola conexión SMTP (clase B, **PENDIENTE DE VALIDACIÓN**)

- **Commit:** `c05e14d`.
- **Archivos y funciones.**
  - `integrations/email/sender.py`: nueva `SmtpSession` (apertura perezosa, reutilización, descarte ante cualquier fallo, `close()` con QUIT); `_secure()` comparte STARTTLS + AUTH; `sendHtmlEmail(..., *, session=None)`. `_send()` conserva su `with smtplib.SMTP` original.
  - `services/email.py`: `smtpSession()` (gestor de contexto) y `sendEmailEvent(..., session=None)`. El kwarg `session` solo se pasa cuando existe.
  - `services/contact.py`: `sendContactMessage` y `_sendConfirmation` usan la misma sesión.
  - `tests/test_account_deletion.py`: el fake `fakeSend` del fixture `mails` acepta `session=None` para reflejar la firma real. Es el único cambio de prueba existente.
- **Causa técnica.** La consulta y su confirmación abrían dos conexiones SMTP completas en serie (TCP, TLS, EHLO, AUTH). Cada conexión agrega varios viajes de ida y vuelta antes del DATA.
- **Solución.** Ambos correos van por una sola conexión. Cada correo sigue registrando su resultado por separado. La respuesta mantiene `confirmacionEnviada` y el 503 sigue dependiendo solo de la consulta. Ante un fallo, la conexión se descarta y el envío siguiente abre otra: no hay reintentos, así que no se duplica ningún correo.
- **Latencia y conexiones (medido con SMTP de pruebas, n = 10, p50 / p95 en ms):**

| Escenario | Código | p50 / p95 (ms) | Conexiones SMTP | Mensajes DATA |
|---|---|---|---|---|
| Flujo de contacto, RTT 0, sin límite | HEAD | 337,8 / 416,6 | 20 | 20 |
| | Modificado | 93,4 / 114,0 | 10 | 20 |
| Flujo de contacto, RTT 50 ms, 2 Mbps | HEAD | 16 230,3 / 16 295,5 | 20 | 20 |
| | Modificado | 2 117,1 / 2 563,7 | 10 | 20 |
| Flujo de contacto, RTT 150 ms, sin límite | HEAD | 3 554,9 / 3 582,0 | 20 | 20 |
| | Modificado | 2 258,1 / 2 300,6 | 10 | 20 |

  Aislamiento del efecto de la sesión (mismo código modificado, dos envíos por iteración):

| Escenario | Sin sesión compartida p50 / p95 (conexiones) | Con sesión compartida p50 / p95 (conexiones) | Cambio p50 |
|---|---|---|---|
| RTT 50 ms, 2 Mbps | 2 488,3 / 2 537,4 (20) | 2 119,7 / 2 271,9 (10) | −14,8 % |
| RTT 150 ms, sin límite | 3 253,3 / 3 289,7 (20) | 2 256,1 / 2 301,7 (10) | −30,6 % |

  Lectura: con RTT 50 ms, una conexión evitada equivale a unos 370 ms. El efecto del banner (H-09), aislado, es de alrededor de −85 % a RTT 50 ms y 2 Mbps (16 230 → 2 488 ms).
- **CPU/RAM:** no se midió. Se evitan dos handshakes TLS y dos AUTH por consulta.
- **Pruebas.** `test_register_contact.py` (incluidas las fallas de confirmación, la ausencia de reintentos y los límites por IP y por destinatario), `test_security_config.py` (STARTTLS con verificación de certificado), `test_email.py` y `test_emails.py`: 230 pasan. Además, `test_result_email.py`, `test_patient_result_email.py`, `test_user_notifications.py` y `test_account_deletion.py` (que usan el fixture `mails` modificado) pasan.
- **Riesgo residual.**
  - Si el servidor cierra la sesión entre la consulta y la confirmación, la confirmación falla y la respuesta marca `confirmacionEnviada: false`. Antes, la conexión nueva habría podido funcionar. Es un fallo de un correo auxiliar, sin reintento.
  - Diferencias de comportamiento del proveedor SMTP real al reutilizar la conexión (límites de mensajes por sesión, tiempo de inactividad). **No medido**: falta el SMTP de pruebas del proveedor.
- **Estado:** **PENDIENTE DE VALIDACIÓN** con el SMTP de pruebas del entorno de despliegue.

### 2.3 H-19 — Reglas de matriz del historial en lote (clase B, **PENDIENTE DE VALIDACIÓN** en SQL Server)

- **Commit:** `1f4f131`.
- **Archivos y funciones.**
  - `services/glucoseReference.py`: nuevos `Preloaded` y `preload(db, measurements)`; `build(db, measurement, preloaded=None)` usa los datos precargados cuando se pasan. Sin ellos (detalle de una medición), el camino original no cambia.
  - `services/schemaCompat.py`: nueva `ruleIdsOf(db, idMediciones)`, la versión en lote de `ruleIdOf`, con la misma guardia de migración.
  - `services/measurement.py`: `_history` precarga las reglas de las filas que calculan semáforo (`_needsSemaphore`, la misma condición que `_semaphoreOf`); `_semaphoreOf` acepta los datos precargados.
  - `services/patientAnalytics.py`: la comparación con la matriz precarga las mediciones que compara.
  - `tests/test_historial_glucosa_consultas.py` (nuevo): (1) el semáforo de cada fila es igual al cálculo individual, con valores que cubren VERDE, AMARILLO y ROJO; (2) el número de consultas no crece con la página.
- **Causa técnica.** `_history` llamaba a `build()` por cada medición de glucosa completada de la página, y cada llamada lanzaba dos consultas: las reglas de la matriz y la regla aplicada (N+1).
- **Solución.** Dos consultas por página en lugar de dos por medición. El orden de las reglas dentro de cada matriz es el mismo del camino original. Los `IN` están acotados: hasta 50 mediciones por página (`MAX_PAGE_SIZE`) y 100 comparaciones en la analítica (`MATRIX_LIMIT`), muy por debajo del límite de parámetros de SQL Server.
- **Medición (SQLite, conteo de sentencias SQL, mismo escenario; evidencia en `resultados/historial_*.json`):**

| Escenario | Antes | Después |
|---|---|---|
| Página con 15 mediciones de glucosa | 34 consultas | 6 consultas |
| Página con 3 mediciones de glucosa | 10 consultas | 6 consultas |
| Semáforos de las 15 filas (VERDE / AMARILLO / ROJO) | referencia | idénticos fila por fila |

- **Latencia en SQL Server:** **no medida**. Cada consulta eliminada ahorra un viaje al servidor, pero el beneficio real depende del plan y de la red entre la API y SQL Server.
- **CPU/RAM:** no medido.
- **Pruebas.** `test_historial_glucosa_consultas.py` pasa (2/2); en el código anterior, la prueba de conteo **falla** (34 frente a 10 consultas), lo que confirma que detecta el N+1. Regresión: `test_measurements.py`, `test_glucose_mode.py`, `test_measurement_lifecycle.py`, `test_matrices*.py`, `test_patient_analytics.py` y los dashboards: 224 pasan.
- **Riesgo residual.** Cambio en el cálculo del semáforo: **no cambia**, pero se valida por equivalencia. Verificar en SQL Server que el orden de las reglas sea estable (las reglas con el mismo `codigoRegla` dentro de una matriz quedarían en orden no determinado, como ya ocurría).
- **Estado:** **PENDIENTE DE VALIDACIÓN** en SQL Server con datos representativos, incluidos casos límite (sin matriz, sin regla aplicable, mediciones sin edad ni sexo).

### 2.4 H-18 — Contadores del dashboard del operador en una pasada (clase B, **PENDIENTE DE VALIDACIÓN** en SQL Server)

- **Commit:** `df268d3`. **Archivo y función:** `services/dashboard.py`, `operatorDashboard`.
- **Causa técnica.** La misma subconsulta de mediciones iniciadas por el operador (join con `Auditoria` por `idRegistro`, filtrada por `tablaAfectada`, `accion` e `idRelacionado`) se usaba en cinco consultas de conteo y una de máximo, y otra vez en la agrupación por estado. `Auditoria` no tiene índice por `idRelacionado` (ver §1.2).
- **Solución.**
  - Una consulta agregada con `CASE` calcula los conteos DEMO (total y del período), sin resultado (total y del período) y el último inicio.
  - Una consulta agrupada por estado calcula los conteos por estado y el total del período en el mismo recorrido.
  - Los criterios no cambian: DEMO es `origenGlucosa = 'DEMO'`; sin resultado es `estadoMedicion <> 'COMPLETADA' AND origenGlucosa IS NULL`; el período usa las mismas condiciones que `_inPeriod`. Las condiciones se evalúan igual que los `WHERE` que reemplazan.
- **Medición (SQLite, mismo escenario de `test_operator_panel.py`; evidencia en `resultados/panel_*.json`):**

| Medición | Antes | Después |
|---|---|---|
| Consultas, sin gráficos | 23 | 18 |
| Consultas, con gráficos | 24 | 19 |
| Contadores devueltos (realizadas, en período, DEMO, sin resultado, por estado, pacientes, transferencias, última actividad) | referencia | **idénticos** (JSON comparado) |

- **Latencia y CPU/RAM en SQL Server:** no medidas. La subconsulta sigue sin índice; la reducción de pasadas depende de cómo SQL Server ejecute el `CASE` agregado.
- **Pruebas.** `test_operator_panel.py`, `test_dashboards.py`, `test_dashboard_privacy.py`, `test_dashboard_multiple_measurements.py` y `test_patient_analytics.py` pasan.
- **Riesgo residual.** Plan de ejecución en SQL Server (puede ser distinto del que hoy elige el optimizador). Los contadores no cambian en SQLite; falta confirmarlo con datos reales de SQL Server.
- **Estado:** **PENDIENTE DE VALIDACIÓN** en SQL Server (planes con `SET STATISTICS XML ON` sobre base descartable).

---

## 3. Clasificación de todos los hallazgos

| ID | Área | Clase | Estado | Motivo |
|---|---|---|---|---|
| H-01 | Ayuda (imágenes) | Fuera del alcance backend | Propuesta (frontend) | Consigna: backend. Ver S-02 de la auditoría |
| H-02 | Nginx, caché de `/ayuda/` | C | Solo propuesta | Configuración de servidor: requiere autorización |
| H-03 | Ayuda (chunk) | Fuera del alcance backend | Propuesta (frontend) | |
| H-04 | Ayuda (precarga de ruta) | Fuera del alcance backend | Propuesta (frontend) | |
| H-05 | Ayuda (cambio de pestaña) | Fuera del alcance backend | Propuesta (frontend) | |
| **H-06** | Correo, alta y reenvío de verificación | C (restringido) | Solo propuesta | Verificación de cuenta: no se toca |
| **H-07** | Correo, contacto | B | **PENDIENTE DE VALIDACIÓN** | §2.2 |
| **H-08** | Correo, flujos síncronos | C (restringido) | Solo propuesta | MFA, códigos y recuperación: no se tocan |
| H-08 (resultados) | Confirmación de resultados | — | **DESCARTADO** | Ya en segundo plano desde `47d8c1e` |
| **H-09** | Correo, banner | A | **VALIDADO** (laboratorio) | §2.1 |
| H-10 | Correo, conexión por envío | C (parcial) | Parcial: contacto resuelto (H-07); lotes, solo propuesta | Reutilizar conexión en lotes requiere diseño (§4) |
| H-11 | Correo, cola sin límite ni persistencia | C | Solo propuesta | Cambia la entrega de avisos y requiere esquema (§4) |
| H-12 | Correo, lotes por destinatario | C | Solo propuesta | Requiere medición con 50 destinatarios (§4) |
| **H-13** | SQL, índice `Medicion(idPerfilMedicion, ...)` | C | Solo propuesta (DDL) | Prohibido ejecutar DDL: ver §4.1 |
| **H-14** | Tope del driver (`DB_MAX_CONCURRENT_CALLS`) | C | Sin cambios | Requiere medición en SQL Server |
| **H-15** | CPU/memoria de Argon2 | C | Sin cambios; límites propuestos | Parámetros de Argon2 y auth: no se tocan (§4.2) |
| **H-16** | Dimensionamiento de contenedor | C | Sin cambios; propuesta | Configuración de producción (§4.2) |
| H-17 | Edición de SQL Server | C (hipótesis) | Verificación manual pendiente | No verificable desde aquí |
| H-18 | Dashboard del operador | B | **PENDIENTE DE VALIDACIÓN** | §2.4 |
| **H-19** | N+1 del historial y analítica | B | **PENDIENTE DE VALIDACIÓN** | §2.3 |
| H-20 | Streams SSE | C | Solo propuesta | Cambio de arquitectura de streams (§4.3) |
| H-21 | Paginación `OFFSET` | C | Solo propuesta | Requiere volumen real (§4.4) |
| H-22 | Búsqueda `ILIKE` | C | Solo propuesta | Depende del volumen |
| H-23 | Polling en frontend | Fuera del alcance backend | Propuesta (frontend) | La auditoría ya registra pausa con pestaña oculta |
| H-24 | `React.memo` | Fuera del alcance backend | Propuesta (frontend) | Requiere medición previa |
| H-25 | Estado del sistema (sondas SMTP y Google) | A (implementable) | Solo propuesta, no implementada en esta entrega | Cambia la frescura que ve el administrador; decisión de producto (§4.5) |
| H-26 | Google OAuth | NO EVALUADO | — | Sin acceso a Google |
| — | Acceso a configuración (`getSettings`) | — | **DESCARTADO** | Ya tiene `lru_cache` (`core/config.py:610`) |
| — | Verificación de esquema (`hasColumn`, `hasTable`) | — | **DESCARTADO** | Ya tiene caché con TTL (`schemaCompat._check`) |
| — | Serialización JSON y cálculos duplicados en el resto de servicios | — | No hay hallazgo medido | No se modificó nada por intuición |

---

## 4. Propuestas (clase C): sin implementar

Ninguna de estas propuestas está en la rama. Todas requieren autorización expresa y, cuando corresponde, medición en un entorno equivalente.

### 4.1 H-13 — Índice en `Medicion` (propuesta de DDL, **NO EJECUTAR**)

La aplicación no ejecuta DDL y el script de actualización lo aplica un administrador. Propuesta para base descartable, con planes reales antes y después:

```sql
-- PROPUESTA. NO EJECUTAR sobre la base instalada.
-- Validar con SET STATISTICS XML ON en una base descartable, con volumen representativo.
CREATE NONCLUSTERED INDEX [IX_Medicion_perfil_inicio]
    ON [dbo].[Medicion] ([idPerfilMedicion], [fechaHoraInicio] DESC)
    INCLUDE ([estadoMedicion], [modoMedicion]);
```

- **Riesgos:** espacio y costo de escritura en una tabla que crece; ventana de creación del índice. Revisar `FK_Medicion_Perfil` y la retención (`IX_Medicion_vencimientoRetencion`).

**Índice para H-18 (propuesta, también sin ejecutar):**

```sql
-- PROPUESTA. Un índice FILTRADO solo se usa si la consulta reproduce el predicado literal
-- (accion = N'INICIAR_MEDICION'). Con parámetros enlazados, validar el plan antes de crearlo.
CREATE NONCLUSTERED INDEX [IX_Auditoria_inicio_medicion]
    ON [dbo].[Auditoria] ([idRelacionado])
    INCLUDE ([idRegistro])
    WHERE ([tablaAfectada] = N'Medicion' AND [accion] = N'INICIAR_MEDICION');
```

- **Riesgos:** `Auditoria` es de solo anexado (GL-03); el índice no altera registros, pero sí el costo de escritura de auditoría. Confirmar con el administrador de auditoría.

### 4.2 H-14, H-15 y H-16 — Concurrencia y memoria (sin cambios)

- **Medido en la auditoría (proceso de laboratorio con `pwdlib`):** una verificación Argon2 cuesta ~49 ms de CPU y ~110 MB de RSS base; 4 simultáneas llegan a ~303 MB; 8 simultáneas, a ~555 MB.
- **Dimensionamiento propuesto (con límite de concurrencia por proceso, sin cambiar parámetros):**
  - Backend de Compose base (512 MB): **4 verificaciones simultáneas** (~303 MB de pico en laboratorio, con margen para la API).
  - Backend de producción (1 GB): **8 simultáneas** (~555 MB de pico, con margen).
- **Métricas antes de decidir:** p95 de inicio de sesión con N concurrentes; RSS del contenedor (`docker stats`) durante la prueba; tasa de respuestas de espera por el límite.
- **Riesgo:** bajo la cola de logins, la espera sube. Requiere definir el tiempo de espera y el mensaje al usuario, y no altera la verificación de contraseñas.
- **Tope del driver (H-14):** mantener `DB_MAX_CONCURRENT_CALLS = 2`. Evaluar en SQL Server un pool separado para consultas rápidas (S-14 de la auditoría) con las consultas reales de historial y dashboard, después de §2.3 y §2.4.
- **Workers de Uvicorn:** no cambiar sin medir el consumo de memoria por worker en un entorno equivalente al servidor HP (`NO EVALUADO`).

### 4.3 H-20 — Streams SSE

- Los streams despiertan cada 0,2 s (`api/v1/telemetry.py:219`, `api/v1/acquisition.py:101`). Con el tope de 300 streams, hasta 1 500 despertares por segundo en el peor caso (cálculo, no medido).
- **Propuesta (S-17):** notificación por `asyncio.Event` desde el hub, en lugar de sondeo.
- **Métrica previa:** CPU del proceso con 300 streams abiertos y sin datos, antes y después.
- **Riesgo:** reconexión y pérdida de eventos al reiniciar; revisar `test_stream_limits.py`.

### 4.4 H-11, H-12 y lotes de correo

- **H-12 (lotes por destinatario):** `institution.py` (cierre de institución) y `platformInstitutions.py` encolan un correo por destinatario. **Propuesta:** tandas de 10 destinatarios por tarea del ejecutor, cada tanda con una `SmtpSession` (H-07). Así se evita monopolizar un único hilo, y el ahorro por tanda es de una conexión por cada 10 correos. **Medir** con 50 destinatarios antes de implementar.
- **H-11 (cola sin límite, sin persistencia):** `services/email.py` usa `ThreadPoolExecutor(max_workers=2)` con cola ilimitada. **Propuesta:** cola acotada, métrica de profundidad y, para avisos, persistencia con el patrón de `UserNotification` (`estadoCorreo`, `intentosCorreo`), que ya existe para avisos de usuario. Requiere esquema y cambia la entrega, por lo que necesita autorización y pruebas de pérdida y duplicados.

### 4.5 H-25 — Caché corta del estado del sistema (clase A, no implementada)

- `services/platformDashboard.py:systemStatus` abre dos conexiones (SMTP y Google) con timeout de 2 s dentro de la petición.
- **Propuesta:** caché de 30 a 60 s del resultado global (no por usuario), con el endpoint sin cambios de autorización. Queda como siguiente paso porque cambia la frescura que ve el administrador, y esa decisión es de producto.

### 4.6 H-06 y H-08 (flujos restringidos)

- Verificación de correo, códigos MFA, recuperación de contraseña y confirmación de resultados **no se tocan**, como exige la consigna.
- **Propuesta para más adelante:** envío en segundo plano con un estado consultable, sin revelar si el correo existe (S-06 de la auditoría). Requiere diseño de UX y revisión de seguridad.

### 4.7 Otros

- **H-21 (`OFFSET`) y H-22 (`ILIKE`):** paginación por clave (keyset) y búsqueda por prefijo o texto completo. Medir con volumen real en SQL Server.
- **H-02 (caché de `/ayuda/`) y H-17 (edición de SQL Server):** configuración de servidor, requiere autorización y verificación manual del servidor HP.

---

## 5. Pruebas y resultados

### 5.1 Suite completa del backend

| Corrida | Pasan | Fallan | Omitidas | Observaciones |
|---|---|---|---|---|
| Línea base, árbol **parcial** (solo `backend/` y `database/`) | 2 356 | 15 | 203 | 11 de los 15 fallos eran archivos ausentes en el árbol parcial, no código |
| Línea base, árbol **completo** de HEAD (solo los 15 fallos repetidos) | 11 de 15 | 4 | — | Equivale a 2 367 pasan y 4 fallan de entorno |
| Árbol modificado (corrida final, §5.2) | **2 370** | **3** | 203 | Fallos de entorno, idénticos a HEAD |

### 5.2 Corrida final sobre el árbol commiteado

Evidencia: `docs/auditorias/evidencias/remediacion_2026-11-05/resultados/suite_remediacion_final.txt`
(`3 failed, 2370 passed, 203 skipped` en 20 min 27 s). Las tres pruebas fallidas son las de §5.3, que también fallan en HEAD.

### 5.3 Fallos de entorno (presentes también en HEAD)

| Prueba | Causa |
|---|---|
| `test_bridge_ctl.py::test_el_comando_de_inicio_usa_pythonw_sin_consola_...` | Prueba específica de Windows (`pythonw`); el contenedor es Linux |
| `test_patient_access.py::test_la_api_directa_sin_autenticacion_es_rechazada` | Un 500 causado por `libodbc.so.2` ausente (el driver ODBC no está instalado en el contenedor). Se verificó que el error viene de esa importación |
| `test_stream_limits.py::test_los_streams_no_retienen_conexiones_del_pool[...]` | Igual: `libodbc.so.2` ausente en el stream de telemetría |

Nota: `test_platform_dashboard.py::test_los_componentes_informan_verificaciones_reales_...` falló en una corrida intermedia porque el `tests/test.env` local tenía el puerto SMTP 8025 copiado de la auditoría. Con `SMTP_PORT=587`, que es lo que la prueba espera, pasa en HEAD y en el árbol modificado. Es un error de mi entorno de prueba, no del código.

Ninguna de estas causas está en el código modificado. Las pruebas que requieren SQL Server real y el Windows del equipo de desarrollo quedan omitidas (203), como en la línea base.

### 5.4 Lint

`ruff` (versión fijada en `requirements-dev.txt`) sobre los archivos tocados: sin hallazgos nuevos. Los hallazgos preexistentes (p. ej. `SIM101` en `sender.py`, `I001` y `RUF007` en `patientAnalytics.py`) no se modificaron.

---

## 6. Validaciones pendientes antes de integrar

1. **H-07:** repetir `smtp_bench.py` con el SMTP de pruebas del entorno de despliegue (no el sumidero local). Verificar que el servidor acepte dos mensajes por sesión y medir el tiempo de aceptación de DATA.
2. **H-19 y H-18:** en una base SQL Server **descartable** con datos representativos: planes de ejecución antes y después (`SET STATISTICS XML ON`), tiempos de respuesta del historial (15 y 50 mediciones) y del dashboard del operador, y comparación de resultados con casos límite (sin matriz, sin regla aplicable, mediciones DEMO, canceladas sin origen, período vacío).
3. **H-09:** revisión visual del correo en dos o tres clientes de correo.
4. Reejecutar la suite completa en el entorno de integración (Windows, con `libodbc` y `.env` reales en el entorno de pruebas, sin tocarlos aquí).

---

## 7. Resumen para la exposición

**Podría integrarse antes del 11 de noviembre**, previa validación de §6 y autorización:

1. **H-09** (banner): riesgo bajo, validado en laboratorio.
2. **H-19** (N+1): riesgo bajo-medio; equivalencia probada; falta SQL Server.
3. **H-18** (dashboard): riesgo medio; contadores idénticos; falta plan en SQL Server.
4. **H-07** (contacto): riesgo medio; falta SMTP de pruebas del proveedor.

**Conviene dejar para después:** H-11 y H-12 (cola y lotes, requieren diseño y esquema), H-13 (índice: ventana de actualización y plan real), H-14, H-15 y H-16 (dimensionamiento tras medir en un entorno equivalente), H-20 (streams), H-21 y H-22 (paginación y búsqueda con volumen real), H-06 y H-08 (flujos restringidos), H-25 (caché de sondas, decisión de producto) y todo el frontend de Ayuda (H-01 a H-05, H-23 y H-24).

---

## 8. Límites de esta entrega

- Sin SQL Server, sin el servidor HP, sin Google y sin SMTP del proveedor: las latencias de base de datos y de correo real **no están medidas**.
- Los conteos de consultas son de SQLite; el número de sentencias es el mismo código de consulta, pero el costo no.
- No se hizo merge, no se actualizó Docker, no se ejecutaron migraciones ni despliegues, no se modificó `master`, la base instalada ni el servidor HP.
- No se enviaron correos reales. El SMTP fue un servidor de pruebas local con certificado de prueba.
- Los valores sintéticos de `backend/tests/test.env` no están versionados ni se incluyen en la evidencia.
- **Línea de commit:** los commits llevan la línea `Claude-Session`, pero no la de `Co-Authored-By` con el nombre del modelo, porque las instrucciones de la sesión prohíben identificadores de modelo en mensajes de commit. Si se requiere esa línea, debe decidirlo quien revisa.
