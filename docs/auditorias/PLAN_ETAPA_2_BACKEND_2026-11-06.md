# Plan de la segunda etapa (backend): soluciones y pruebas preparadas, sin implementar

> **Estado:** preparación. **Ninguna de estas soluciones está implementada.** Son el insumo para decidir qué autorizar después de la exposición.
> **Relación:** resuelve los hallazgos de `docs/auditorias/RENDIMIENTO_2026-11-05.md` (commit `6922949`, rama `master`).
> **Restricciones de esta etapa (del encargo):** no cambiar autenticación, MFA ni Argon2; no introducir 503 nuevos en el login; no alterar la entrega de correos ni sus estados de auditoría; no modificar SQL Server, sus índices ni las reglas de mediciones; no modificar purgas ni políticas de retención; no cambiar la concurrencia ODBC sin mediciones reales.

## 0. Resumen de conflictos con las restricciones

Algunas soluciones chocan con las restricciones de esta etapa. Quedan marcadas con **DECISIÓN REQUERIDA** y no deben implementarse sin tu autorización explícita.

| ID | Solución natural | Restricción que toca | Alternativa que respeta la restricción |
|---|---|---|---|
| AUD-02 | Mover los correos sincrónicos a una cola | Altera la entrega de correos y su momento de envío | Ninguna sin cambiar la entrega; requiere decisión |
| AUD-04 | Cola persistente de avisos | Altera la entrega de correos y sus estados | Solo medir; la persistencia requiere decisión |
| AUD-05 | Semáforo de Argon2 con 503 | Introduce 503 en el login | Semáforo **sin 503**: espera sin límite de tiempo (igual que hoy, pero acota la memoria) |
| AUD-06 | Cambiar `DB_MAX_CONCURRENT_CALLS` | Concurrencia ODBC sin medición real | Solo medir en staging (sin cambios) |
| AUD-07 | Índice `Medicion` por paciente | Índices de SQL Server | Solo plan de ejecución en copia, y propuesta para el DBA |
| AUD-11 | Purga en lotes | Purgas y retención | Solo propuesta; requiere decisión |
| AUD-09 | Tope de 366 días en estadísticas | Cambia el contrato de la API | Viable, pero fuera de la restricción de retención; requiere aviso al frontend |
| AUD-10 | Ventana por defecto en auditoría | Cambia qué ve el operador y la retención visible | Solo propuesta; requiere decisión de negocio |
| AUD-23 | `NEWSEQUENTIALID()` | Cambia claves de SQL Server | Solo medir fragmentación |

## 1. AUD-02: correo sincrónico dentro de peticiones HTTP (P1) — DECISIÓN REQUERIDA

**Propuesta.** Pasar los 9 flujos sincrónicos a una cola persistente (tabla de salida con estados `PENDIENTE`, `ENVIADO`, `FALLIDO` y reintentos) procesada por el servicio `notifications`. La petición confirma que el envío quedó registrado, no que salió.

**Por qué no se implementa ahora.** Cambia el momento y el estado de la entrega, y los mensajes que el usuario recibe hoy al fallar (`CORREO_NO_ENVIADO`, `confirmacionEnviada: false`). Es exactamente lo que el encargo prohíbe alterar.

**Alternativa de bajo riesgo sin tocar la entrega (válida para la etapa 2):** mantener el envío sincrónico pero **acotar el daño**: (a) un timeout total por envío además del de socket (hoy es por operación, `SMTP_TIMEOUT_SECONDS = 20`), (b) un semáforo de SMTP con 4 permisos para que el threadpool no se agote (AUD-03b). Esto reduce el peor caso sin cambiar qué se envía ni cuándo.

**Pruebas previstas:**
- Por cada flujo: el correo sale con el mismo contenido, destinatario, asunto y auditoría (`registerEvent`) que antes.
- Equivalencia de respuestas para cuenta existente e inexistente (anti enumeración).
- SMTP caído: la petición responde en menos de un segundo (cola) o en el timeout acotado (alternativa).
- Un correo, un envío (sin duplicados por reintento).

**Criterio de aceptación:** ninguna diferencia observable en contenido, destinatarios, auditoría ni mensajes de error; mejora medida del P95 de la petición con SMTP lento.

## 2. AUD-03 (parte SMTP): threadpool agotado por endpoints síncronos (P1)

**Ya resuelto en esta etapa:** `/healthz` (ver el commit de AUD-03 en la rama de correcciones). Medido: con 40 peticiones bloqueadas, su máximo pasó de 7 361 ms a 3,7 ms.

**Pendiente (requiere decisión):** la espera SMTP sigue dentro de los hilos del threadpool. Propuestas, de menor a mayor alcance:
1. Semáforo de SMTP de 4 permisos en `integrations/email/sender.py`, con espera sin 503. Efecto: como mucho 4 hilos atados a SMTP, el resto de la API sigue respondiendo. **Riesgo:** los envíos quedan en espera en lugar de fallar rápido; mismo resultado final que hoy.
2. Lo de AUD-02 (cola), que es la solución de fondo.

**Pruebas previstas:** el modelo `pool_model.py` como prueba automática; 40 peticiones de registro con SMTP `blackhole` y comprobación de que un endpoint no relacionado responde en menos de 100 ms.

## 3. AUD-04: cola de avisos sin límite ni persistencia (P2) — DECISIÓN REQUERIDA

**Problema medido:** 30 avisos tardan 17,7 s con 150 ms por comando; sin persistencia se pierden al reiniciar.

**Propuesta:** (a) cota de la cola con métrica y registro de descarte (no descartar avisos de seguridad); (b) persistencia en tabla de salida. **Restricción:** (b) altera la entrega; (a) también cambia qué pasa con un aviso cuando la cola está llena.

**Pruebas previstas:** vaciado con 1 000 avisos en el sumidero; reinicio del proceso con avisos pendientes (ninguno perdido en (b)); prioridad de avisos de seguridad (`highPriority`, `securityNotice` de `eventTypes.py`).

## 4. AUD-05: Argon2id sin límite de concurrencia (P1)

**Problema medido:** throughput estable en ≈12,3 verificaciones/s en 4 vCPU; ≈56 MB por operación; OOM estimado hacia 15 simultáneas en 1 GB.

**Propuesta compatible con las restricciones:** semáforo global por proceso alrededor de `verifyPassword` y `hashPassword` en `core/security.py`, **sin respuesta 503 y sin timeout de espera**: la petición espera su turno como hoy. Así la memoria queda acotada y la semántica del login no cambia.

**Lo que NO se propone:** cambiar `ARGON2_TIME_COST`, `ARGON2_MEMORY_COST_KIB` ni `ARGON2_PARALLELISM`; cambiar el rate limit; añadir 503 en `/auth/login`.

**Riesgo:** con cola sin límite, una ráfaga de logins alarga la latencia (no el error). El rate limit por IP y por cuenta sigue siendo la protección contra abuso.

**Pruebas previstas:**
- Equivalencia: `verifyPassword` y `hashPassword` devuelven lo mismo con y sin semáforo (`tests/test_auth_access.py`, `tests/test_login_lockout.py`, `tests/test_mfa_flow.py`).
- Escalera de 4, 8, 16 y 32 logins simultáneos en un contenedor de 1 GB: RSS pico debe quedar acotado (≈ 4 × 64 MB + base), sin OOM.
- Ningún cambio de código de respuesta de login (comparar cabeceras y cuerpos antes y después).

**Criterio de aceptación:** RSS pico acotado en la escalera; latencias p95 medidas antes y después; todas las pruebas de autenticación y MFA pasan sin cambios.

## 5. AUD-06: tope de llamadas simultáneas al driver (P1) — solo medición

**Restricción aplicada:** no se cambia `DB_MAX_CONCURRENT_CALLS` ni el semáforo.

**Plan de medición (staging):** SQL Server 2022 real, `pyodbc` real, carga reproducible (k6 o Locust) con mezcla de historial, dashboard y auditoría; valores 0, 2, 4 y 8; medir throughput, p95, CPU del proceso y tiempo de espera del semáforo. La decisión solo se toma con esas cifras.

**Pruebas previstas:** el test existente `tests/test_db_gate.py` debe seguir pasando sin cambios.

## 6. AUD-07: índice por paciente en `Medicion` (P1) — solo plan de ejecución

**Restricción aplicada:** no se crea ni modifica ningún índice.

**Plan:** en staging (copia de la base), capturar con Query Store el plan de las consultas de `_history`, `buildStatistics` y `_evolution`. Si confirma el escaneo, el DBA evalúa un índice del tipo `(idPerfilMedicion, estadoMedicion, fechaHoraInicio) INCLUDE (...)`.

**Pruebas previstas:** planes antes y después; `SET STATISTICS IO`; tiempo de inserción de `Medicion`; suite de mediciones (`tests/test_measurements.py`, `tests/test_evolution.py`) sobre el esquema actualizado.

## 7. AUD-08 y AUD-09: indicadores institucionales y rango de estadísticas (P2)

**AUD-08 (agregados en SQL):** `COUNT`, `AVG`, `MIN`, `MAX` y serie diaria con `GROUP BY` en lugar de cargar filas. **Restricción:** las reglas de mediciones no cambian; la supresión de grupos pequeños (`patientAccess.suppressSmallGroup`) se conserva exacta.
- **Pruebas:** equivalencia de resultados con datos sintéticos (redondeo incluido); prueba de supresión con uno y varios pacientes.

**AUD-09 (tope de 366 días):** cambia el contrato de la API para rangos mayores. **Pruebas:** rango de 366 días aceptado, 367 rechazado con `PERIODO_INVALIDO`; el frontend muestra el mensaje.

## 8. AUD-10: ventana por defecto en auditoría (P2) — DECISIÓN REQUERIDA

**Restricción:** no cambiar la retención ni lo visible en la auditoría sin decisión de negocio. **No se implementa.** Propuesta a discutir: ventana por defecto de 30 días con aviso visible, paginación por keyset y exportación completa sin cambios.

**Pruebas previstas:** filtros explícitos devuelven el mismo resultado; paginación sin duplicados ni huecos; exportación completa.

## 9. AUD-11: purga de auditoría técnica en un `DELETE` sin lotes (P2) — DECISIÓN REQUERIDA

**Restricción:** no se modifican purgas ni políticas de retención. **No se implementa.** La propuesta (borrar en lotes con pausa y mover la purga al servicio `lifecycle`) cambia cómo se ejecuta la purga.

**Pruebas previstas:** purga de 1 millón de filas sintéticas en staging; verificación de que la política de plazo se cumple igual.

## 10. AUD-12: polling con la pestaña oculta (P2, frontend)

Ya fuera del alcance de backend. Se puede implementar en una etapa posterior: pausa con `document.visibilityState === 'hidden'` como ya hacen dos hooks. No altera autenticación ni controles.

## 11. AUD-20, AUD-21, AUD-22 (P2–P3)

- **AUD-20:** límites de CPU y RAM para `lifecycle` y `notifications` (bajo riesgo). `--workers` solo con medición, porque multiplica la RAM de Argon2.
- **AUD-21:** cerrar la transacción antes del SMTP de soporte institucional. Cambia el orden de `registerEvent` y `commit` del flujo de soporte: requiere revisar la auditoría de ese flujo antes de cambiarlo.
- **AUD-22:** timeouts explícitos en Google OAuth. Riesgo bajo; no cambia el flujo de login.

## 12. AUD-23 y AUD-24 (P3)

- **AUD-23:** solo medir fragmentación (`sys.dm_db_index_physical_stats`) en staging. No se cambian claves.
- **AUD-24:** pool de conexiones SMTP. Depende de AUD-02; sin cambio de entrega no tiene sentido.

## 13. Orden recomendado si se autoriza la segunda etapa

1. **Mediciones en staging** (sección 4.6 del informe): SQL Server, contenedor de 1 GB, SMTP de prueba. Sin esto, AUD-06, AUD-07, AUD-10, AUD-11 y AUD-23 no deben tocarse.
2. **AUD-03b y AUD-05 sin 503** (semáforos), con las pruebas de autenticación como barrera.
3. **Decisiones de negocio:** AUD-02/AUD-04 (entrega de correos) y AUD-10 (ventana de auditoría).
4. **Cambios de datos o esquema** (AUD-07, AUD-11, AUD-23) solo con el DBA y ventana de mantenimiento.
