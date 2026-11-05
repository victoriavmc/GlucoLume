# Cuellos de botella de rendimiento

> Revisión desde cero del 05/11/2026, sobre la rama `claude/modest-curie-903ohj` (código tal como está hoy).
> Los cuellos se ordenan por los seis perfiles de optimización: Software Performance, Backend, Frontend, Database, SRE y Performance Testing.
>
> **Este documento no usa como fuente** `docs/RENDIMIENTO.md` ni `docs/PENDIENTES.md`: están desactualizados y quedan solo como historial, sin cambios.
> Tampoco cambia código. Es un diagnóstico para decidir qué medir y qué corregir primero.

## 1. Cómo leer este documento

Cada hallazgo lleva una etiqueta de evidencia:

- **Medido**: lo ejecuté en esta revisión. El detalle figura en la sección 3.
- **Código**: lo leí en el código con la referencia de archivo y línea. No lo medí.
- **Hipótesis**: se deduce del código, pero el costo real depende de datos o de infraestructura que no tengo aquí. Hay que confirmarla antes de tocarla.

**Entorno de la revisión:** contenedor de 4 vCPU (Intel Xeon 2,10 GHz), Python 3.13, Node 22. **No hay SQL Server ni daemon de Docker activos**, así que ninguna consulta SQL se midió. Todo lo de base de datos es hipótesis.

## 2. Resumen

| ID | Cuello de botella | Perfil | Evidencia | Severidad |
|---|---|---|---|---|
| BE-1 | Login con Argon2id: CPU y memoria por intento, sin límite de concurrencia | Backend, SRE | Medido + Código | **Alta** |
| BE-2 | Semáforo del driver con 2 llamadas por proceso y sin timeouts | Backend, SRE | Código | **Alta** |
| BE-3 | Correo: 15 envíos síncronos dentro de la petición y cola sin límite | Backend, SRE | Código | **Alta** |
| BE-4 | Dashboards traen hasta 50 000 filas a Python | Backend, DB | Medido (memoria) + Código | Media-alta |
| BE-5 | Mantenimiento periódico corriendo dentro de la API | Backend, DB | Código | Media |
| DB-1 | `Medicion` sin índice que empiece por `idPerfilMedicion` | Database | Código (esquema) | **Alta** |
| DB-2 | Búsquedas `LIKE '%…%'` sobre varias columnas | Database | Código | Media |
| DB-3 | Paginación con `OFFSET` en páginas profundas | Database | Código | Media |
| DB-4 | Retención en lotes compitiendo con la API por bloqueos | Database, SRE | Código | Media |
| FE-1 | Carga inicial: 461 KB de JS y 123 KB de CSS antes del primer render | Frontend | Medido | Media |
| FE-2 | Sondeos cada 3 a 60 s sin pausa con la pestaña oculta | Frontend, Backend | Código | Media |
| FE-3 | Compilación de 4 min 22 s | Frontend | Medido | Media (entrega) |
| SP-1 | Un solo proceso Python para toda la API: la 2.ª CPU de producción queda casi sin uso para Python | Software | Código + Medido | Media |
| SR-1 | Sin métricas de aplicación ni registro de accesos | SRE | Código | **Alta** |
| SR-2 | Health check solo de vida, sin indicador de disponibilidad | SRE | Código | Media |
| SR-3 | Estado en memoria del proceso: escalar réplicas cambia los límites | SRE | Código | Media |
| PT-1 | Sin pruebas de carga en integración continua | Performance Testing | Código | **Alta** |
| PT-2 | No hay medición en un entorno parecido al de destino | Performance Testing | Código | **Alta** |

## 3. Mediciones de esta revisión

| Qué | Cómo | Resultado |
|---|---|---|
| Compilación del frontend | `vite build`, una corrida | **4 min 22 s**; el tiempo de CPU fue ~290 s, así que casi todo corrió en un solo núcleo |
| JS de la carga inicial | Archivos que `index.html` precarga o carga como entrada | **461 KB** sin comprimir, **135 KB** con gzip -9 (índice 163 KB, React 187 KB, router 40 KB, íconos 71 KB) |
| CSS de la carga inicial | `index-*.css` referenciado en `index.html` | **123 KB** sin comprimir, **22 KB** con gzip |
| JS total del build | 89 archivos `.js` | 1,34 MB sin comprimir, 429 KB con gzip |
| Argon2id, un núcleo | `verify` con m=64 MiB, t=3, p=4 (los parámetros de `app/core/security.py`) | **≈180 ms por login**; ≈5 logins/s; cae a ≈3,4/s con 8 concurrentes |
| Argon2id, dos núcleos | Igual, con `taskset` en 2 CPU | **≈119 ms por login**; ≈10 logins/s |
| Argon2id, memoria | Pico de RSS con N verificaciones simultáneas | Base 79 MB; 4 concurrentes → 272 MB; 8 concurrentes → **527 MB** (≈50–55 MB por login simultáneo) |
| Sondeo SSE | Prototipo con el mismo bucle de `api/v1/acquisition.py` (`get_nowait` + `sleep(0.2)`) | 10 streams: 0,1 % de un núcleo; 100: 0,4 %; **300: 1,3 %** |
| Modelo `Medicion` | Instanciar 50 000 filas del modelo real sin base | **≥31 MB** y **≈380 ms** de CPU solo para construirlas (cota inferior: una sesión real suma estado propio) |

Las mediciones de Argon2id usaron la librería con las mismas versiones fijadas en `backend/requirements.txt`.

## 4. Software Performance Engineer

**SP-1 · Un solo proceso Python para toda la API** · *Código + Medido*
- **Dónde:** `backend/Dockerfile:78` arranca `uvicorn` sin `--workers`. Producción asigna 2 CPU al backend (`compose.prod.yaml:23`).
- **Qué pasa:** el GIL impide que el código Python use más de un núcleo a la vez. La medición de Argon2 muestra que el código nativo sí puede usar el segundo núcleo: el throughput se duplica de un núcleo a dos (≈5 a ≈10 logins/s). Pero el trabajo Python de cada petición (serialización, validaciones, agregados) queda en un solo núcleo.
- **Cómo confirmar:** perfil de CPU bajo carga real con `py-spy` en producción o en un entorno equivalente, separando tiempo en Python de tiempo en espera de base o de hashing.
- **Dirección:** evaluar más de un proceso **solo después** de resolver BE-2 y SR-3, porque cada proceso tendría su propio semáforo y sus propios límites en memoria.

## 5. Backend Performance Engineer

**BE-1 · Login con Argon2id: costo de CPU y memoria, sin límite de concurrencia** · *Medido + Código*
- **Dónde:** `backend/app/core/security.py:47` (parámetros m=64 MiB, t=3, p=4, fijados a propósito por H-12); `verifyPassword` (línea 142) se llama desde `services/auth.py` en las líneas 541, 549, 584 y 695. `verifyDummyPassword` (línea 148) se ejecuta en `auth.py:664, 671, 680` cuando la cuenta no existe. No hay ningún semáforo ni límite que controle cuántas verificaciones corren a la vez (búsqueda de `Semaphore` en `app/`: solo el del driver de base).
- **Qué pasa, medido:**
  - Un login cuesta **≈180 ms de CPU** en un núcleo. Con 20 logins simultáneos al empezar una clase, el último espera ≈4 s en un núcleo y ≈2 s en dos.
  - Cada verificación simultánea agrega **≈50–55 MB** de memoria. Con un límite de 512 MB (`compose.yaml:80-81`, el valor por defecto) no caben muchos logins a la vez: estimo **≈7** antes de un OOM, asumiendo ~100 MB de base del proceso (no medida dentro del contenedor). Con 1 GB (producción) estimo **≈16**.
  - Un **cambio de contraseña** hace hasta 4 verificaciones seguidas: la actual más las 3 del historial (`auth.py:541-549`, `PASSWORD_HISTORY_SIZE = 3`). Estimo **≈0,7 s** de CPU en un núcleo. Es secuencial, no paralelo.
- **Por qué importa:** un pico de inicios de sesión no degrada solo el login: el proceso consume memoria y CPU que también necesitan las demás peticiones.
- **Dirección:** limitar la concurrencia de verificaciones con un semáforo propio, con espera acotada y respuesta controlada cuando se excede. Medir el resultado con ráfagas de 1, 5, 10 y 20 logins en el límite de 512 MB y en el de 1 GB. No bajar los parámetros: el costo es el objetivo de seguridad.

**BE-2 · Semáforo del driver con 2 llamadas por proceso y sin timeouts** · *Código*
- **Dónde:** `backend/app/core/config.py:55` (`DB_MAX_CONCURRENT_CALLS = 2`); `backend/app/db/gate.py` (`with self._gate:` espera sin límite); `backend/app/db/session.py` (`_createEngine`: la cadena de conexión no fija timeout de conexión ni de consulta). `DB_LOCK_TIMEOUT_MS = 5000` (`config.py:60`) acota solo las esperas por **bloqueos**.
- **Qué pasa:** cada proceso permite 2 llamadas simultáneas al driver. Con *N* réplicas hay hasta *2N* contra SQL Server. Una llamada que se cuelga por red o por un servidor que no responde no tiene límite de tiempo, y ocupa uno de los dos cupos. Con dos colgadas, **toda** petición que use la base espera sin límite. `/healthz` sigue respondiendo, así que nada lo señala.
- **Capacidad (cálculo, no medido):** el throughput máximo de consultas del proceso es ≈ **2 / latencia media de una llamada al driver**. Si una llamada toma 10 ms, el techo es ≈200 llamadas por segundo, sin importar cuántos hilos haya.
- **Nota:** el valor 2 y la estrategia están justificados en el comentario de `gate.py` con una medición de ese entorno. Hay que repetirla en el destino antes de cambiarlo.
- **Dirección:** timeout de conexión y de consulta en la cadena de conexión, y un tiempo máximo de espera para tomar el semáforo que devuelva un error controlado.

**BE-3 · Correo: envíos síncronos dentro de la petición y cola sin límite** · *Código*
- **Dónde:** 15 llamadas directas a `sendEmailEvent` (síncrono) en 10 archivos de `backend/app/services/`: `auth.py`, `mfaRecovery.py`, `passwordChangeCode.py`, `accountDeletion.py`, `measurement.py` (2), `platform.py` (2), `userNotifications.py`, `notifications.py`, `resultEmailConfirmation.py` y `contact.py` (2, dentro de un `run_in_threadpool`). El resto usa `sendEmailEventInBackground`.
- **Qué pasa:** cada envío síncrono ocupa un hilo del pool de la petición durante todo el intento SMTP. El timeout es de 20 s (`backend/app/integrations/email/sender.py:16`). Con un SMTP lento, esos hilos se agotan y las demás peticiones que usan el pool esperan. La cola de envío en segundo plano tiene **2 hilos y sin límite** (`backend/app/services/email.py:72`), vive en memoria y **se pierde al reiniciar**.
- **Cómo confirmar:** simular un SMTP que acepta la conexión y no responde; medir el pool de hilos y la profundidad de la cola durante 5 minutos.
- **Dirección:** llevar los 15 envíos a segundo plano, acotar la cola y registrar en un *outbox* persistente lo que no pudo salir.

**BE-4 · Dashboards que traen filas a Python** · *Medido (memoria) + Código*
- **Dónde:** `backend/app/services/dashboard.py:209` (`MAX_ADMIN_ROWS = 50000`) y `:565` (`MAX_CHART_ROWS = 20000`); `patientAnalytics.py:52` (`MAX_ROWS = 100000`); `securityDetection.py:41` (`MAX_ROWS = 5000`).
- **Qué pasa:** las agregaciones se hacen en Python sobre objetos ORM. **Medido:** construir 50 000 filas de `Medicion` ocupa **≥31 MB y ≈380 ms de CPU** antes de cualquier cálculo. Con tres dashboards de administración a la vez son ≥100 MB de un proceso que tiene 512 MB. El costo de la consulta en la base no está medido.
- **Dirección:** llevar `GROUP BY` y los agregados a SQL, y comparar los resultados con los actuales antes de cambiar nada. Bajar los topes sin cambiar la consulta solo cambia el error por un resultado incompleto.

**BE-5 · Mantenimiento periódico corriendo dentro de la API** · *Código (hipótesis de impacto)*
- **Dónde:** `backend/app/services/maintenance.py` arranca un bucle en el `lifespan` de la API: primera pasada a los 15 s y luego cada 60 s (`MAINTENANCE_INTERVAL_SECONDS`). Cada pasada llama a `measurementLifecycle.sweep()`: libera sesiones vencidas, carga hasta 200 mediciones activas como objetos ORM completos (`invalidateStale`) y purga auditoría técnica.
- **Qué pasa:** el trabajo corre en el mismo proceso, en el mismo pool de hilos y con el mismo semáforo que las peticiones de usuarios. Si la base está lenta o hay muchas mediciones activas acumuladas, la pasada compite con la API cada minuto.
- **Cómo confirmar:** registrar la duración de cada `sweep()` y la espera del semáforo durante esa pasada.
- **Dirección:** mover el mantenimiento a un proceso propio (como ya se hizo con `lifecycle` y `notifications` en `compose.yaml`) o, como mínimo, medir su costo antes de decidir.

**Descartado con evidencia: ingreso de lecturas del puente.** El puente envía un latido por segundo (`acquisition/bridge/glucolume_bridge.py:71`). Cada envío busca la credencial por `tokenHash`, que tiene índice único (`UQ_PuenteCredencial_tokenHash`), y el registro de último uso está limitado a una escritura por intervalo (`bridgeCredentials._touch`). A escala de un equipo, no es un cuello. Con muchos puentes habría que medirlo.

## 6. Frontend Performance Engineer

**FE-1 · Carga inicial pesada** · *Medido*
- **Medido:** antes del primer render se precargan `index` (163 KB, 47 KB gz), React (187 KB, 58 KB gz), router (40 KB, 14 KB gz) e íconos (71 KB, 14 KB gz), y se carga el CSS `index-*.css` (**123 KB**, 22 KB gz). `index.html` precarga los íconos también en la pantalla de login.
- **Dónde:** `frontend/vite.config.js` (`manualChunks`); el CSS global de `frontend/src/styles/` y `frontend/src/components/*.css`.
- **Qué falta:** medir qué porción del CSS se usa en login y en la primera pantalla de cada rol con cobertura de Chrome DevTools. Sin esa cifra no conviene partir el CSS a ciegas.
- **Dirección:** evaluar CSS por ruta y los íconos por pantalla, y comparar FCP y LCP en 3G simulado antes y después.

**FE-2 · Sondeos sin pausa con la pestaña oculta** · *Código (cálculo, no medido)*
- **Dónde y periodos:** `LiveAcquisition.jsx:17` (3 s), `MeasurementPanel.jsx:28` (3 s), `useDeviceReadiness.js:10` (5 s), `useDeviceStatus.js:11` (5 s), `PersonalDashboard.jsx:46` (10 s), `useIncomingNotifications.js:11` y `useNotificationList.js:79` (30 s, mismo intervalo), `MeasurementHistory.jsx:88` (60 s).
- **Qué pasa:** solo `useIncomingNotifications.js` y `useNotificationList.js` leen `visibilityState`. El resto sigue consultando con la ventana minimizada. `enSegundoPlano` (`frontend/src/api/client.js:75`) marca la petición como de fondo, pero no pausa ningún sondeo.
- **Cálculo:** `ConnectDevicePage.jsx` importa componentes que usan `LiveAcquisition`, `useDeviceReadiness` y `MeasurementPanel`. Si se montan juntos, son **≈74 peticiones por minuto por pestaña abierta**. Confirmar en la pestaña Red de DevTools en esa pantalla.
- **Dirección:** pausar los sondeos con `document.hidden`, unificar los que consultan lo mismo, y para adquisición usar el stream SSE que ya existe en lugar de consultar.

**FE-3 · Compilación de 4 min 22 s** · *Medido*
- Una corrida en el entorno de la sección 1. No investigué la causa en esta revisión. Afecta el ciclo de desarrollo y la entrega, no al usuario final. Antes de atribuirla a una herramienta hay que perfilar el build.

**FE-4 · Render de gráficos al llegar cada muestra** · *Hipótesis*
- **Dónde:** `LiveChart.jsx`, `PpgChart.jsx`, `SignalChart.jsx`, `TimeSeriesChart.jsx`, `AnalyticsCharts.jsx`.
- **Hipótesis:** cada evento del stream actualiza el estado y vuelve a dibujar el gráfico completo. Confirmar con el React Profiler durante una adquisición de 60 s y medir INP con una interacción real.

## 7. Database Performance Engineer

**DB-1 · `Medicion` sin índice por `idPerfilMedicion`** · *Código (esquema) · Hipótesis de costo*
- **Dónde:** `database/reference/GlucoLume_DB_v5.sql` (lista completa de índices de `Medicion`: `IX_Medicion_estado_fin` y `IX_Medicion_vencimientoRetencion`); FK `FK_Medicion_Perfil` en `backend/app/models/measurement.py`.
- **Qué pasa:** `idPerfilMedicion` no es la clave inicial de ningún índice; aparece solo como `INCLUDE` en `IX_Medicion_estado_fin`, que no sirve para buscar por ese valor. Las consultas que lo filtran son el historial (`backend/app/services/measurement.py`, `_history`: `WHERE idPerfilMedicion = …`, `COUNT(*)` sobre todas las filas del perfil **en cada página**, `ORDER BY fechaHoraInicio` y `OFFSET`) y los resúmenes de `dashboard.py:116` (`idPerfilMedicion IN (…)`).
- **Cómo confirmar:** plan de ejecución real de `_history` con un volumen parecido al de producción, con `SET STATISTICS IO ON` o Query Store. Si confirma un recorrido amplio, el candidato natural es un índice que empiece por `idPerfilMedicion, fechaHoraInicio`. Medir antes y después.

**DB-2 · Búsquedas con comodín inicial** · *Código*
- **Dónde:** `backend/app/services/institutionPatients.py:305-313` (`ilike` con `%término%` sobre `dni`, `nombre`, `apellido` e `identificadorPseudonimo`, combinados con `OR`); `auditQuery.py:162-175` (concatenación con `coalesce` antes del `ilike`); `auditQuery.py:1112`; `device.py:288`; `platformDashboard.py:348`.
- **Qué pasa:** un comodín inicial no usa índice, y el `OR` sobre varias columnas empeora el plan. El costo crece con el número de pacientes y de auditorías.
- **Dirección:** búsqueda por prefijo donde el negocio lo permita, columnas normalizadas o índices de texto completo.

**DB-3 · Paginación con `OFFSET`** · *Código*
- **Dónde:** `auditQuery.py:924`, `institutionActivity.py:204`, `platformInstitutions.py:329`, `technicalAudit.py:75`, `institutionReassignments.py:154`, `platformDashboard.py:352`, `measurement.py` (`_history`).
- **Qué pasa:** `OFFSET` descarta filas en el servidor; las páginas profundas cuestan más. Varias de estas consultas ya ordenan por una clave estable (`fechaHora, idAuditoria`), así que pueden pasar a paginación por cursor sin cambiar el orden.

**DB-4 · Retención en lotes compitiendo con la API** · *Código + Hipótesis*
- **Dónde:** `measurementRetention.py:160` y `:169`, `auditRetention.py:61` y `:142`; servicios `lifecycle` y `notifications` en `compose.yaml`.
- **Qué pasa:** los trabajos borran o actualizan en lotes mientras la API escribe. Si un lote retiene bloqueos más de `DB_LOCK_TIMEOUT_MS` (5 s), la petición del usuario falla. No hay métrica de duración por lote.
- **Cómo confirmar:** ejecutar la retención con volumen y registrar errores de bloqueo en la API durante cada lote.

**DB-5 · Edición Express: límites de capacidad** · *Código (verificar)*
- La configuración apunta a SQL Server Express (`.env.example:134`, `MSSQL_PID=Express`; `docs/DESPLIEGUE.md` describe una instalación de Express existente). Las ediciones Express tienen límites publicados de tamaño por base de datos, de memoria para el caché de búfer y de núcleos. Antes de dimensionar, verificar los límites de la versión instalada contra la documentación de Microsoft. Si la base crece hasta el tope, es un fallo de capacidad, no de rendimiento.

## 8. Site Reliability Engineer (SRE)

**SR-1 · Sin métricas de aplicación ni registro de accesos** · *Código · prioridad alta*
- **Dónde:** `backend/Dockerfile:78` incluye `--no-access-log`. No hay endpoint `/metrics` ni cliente de Prometheus o StatsD en `backend/app`. `opentelemetry-api` aparece en `backend/requirements.txt:626` solo como dependencia transitiva.
- **Qué pasa:** en producción no hay latencia por endpoint, tasa de errores, profundidad de la cola de correo, ocupación del semáforo ni tiempo de espera para hashing. Hoy el rendimiento solo se conoce con pruebas manuales.
- **Dirección mínima:** registrar duración y código de respuesta por ruta; exponer contadores del semáforo, de la cola de correo y de las verificaciones de contraseña en curso.

**SR-2 · Health check solo de vida** · *Código*
- **Dónde:** `backend/app/main.py:63-66`. El comentario dice que `/healthz` no consulta la base a propósito, para que una caída de SQL Server no reinicie el contenedor en bucle. Es una decisión correcta, pero falta un indicador de **disponibilidad** (readiness) que refleje si la base responde y si el semáforo está bloqueado. Hoy esa situación no aparece en el estado del servicio.

**SR-3 · Estado en memoria: escalar cambia los límites** · *Código*
- **Qué pasa:** el semáforo (BE-2) es por proceso, el limitador de solicitudes usa memoria salvo que se configure `RATE_LIMIT_REDIS_URL`, y el hub de telemetría exige una sola réplica (encabezado de `backend/app/services/rateLimiter.py`). Agregar réplicas multiplica las llamadas a la base y divide el control de abuso sin que nada lo avise.
- **Dirección:** antes de escalar, definir qué estado debe ser compartido y medir el límite efectivo con 1 y 2 réplicas.

**SR-4 · Recursos de referencia** · *Código*
- Desarrollo y el `compose.yaml` base: backend con **1 CPU y 512 MB**. Producción (`compose.prod.yaml:23-24`): **2 CPU y 1 GB**. Con los costos de BE-1 y BE-4, el límite de 512 MB es el primero que se agota. Dimensionar con las mediciones de PT-3, no con supuestos.

## 9. Performance Testing Engineer

**PT-1 · Sin pruebas de carga en integración continua** · *Código · prioridad alta*
- El repositorio no tiene carpeta `.github/` ni otro pipeline de CI. Ninguna prueba de rendimiento corre automáticamente ni tiene umbrales.

**PT-2 · Ningún entorno parecido al de destino** · *Código · prioridad alta*
- El destino previsto es Windows con SQL Server Express (DB-5) y el puente de Windows (`acquisition/bridge`). Esta revisión corrió en Linux, sin base, con 4 vCPU. Las cifras de Argon2 y de memoria son válidas para la CPU medida; las de base de datos no existen todavía.

**PT-3 · Herramientas existentes y escenarios que faltan**
- Ya existen en `docs/evidencias/rendimiento/`: `carga_endpoint.py` (N clientes sobre un mismo endpoint), `medir_http.py`, `medir_consultas.py`, `hilos_micro*.py`, `medir_frontend.mjs`, `cls_fuentes.mjs` y `compose.rendimiento.yaml`. No los ejecuté hoy porque no hay base.
- Escenarios a construir, cada uno con criterios de aceptación que defina el equipo:
  1. **Ráfaga de logins** de 1, 5, 10 y 20 usuarios, con pico de memoria y p95 en los límites de 512 MB y de 1 GB (BE-1).
  2. **Dashboards con volumen** de 50 000 y 500 000 mediciones: p95, memoria y CPU (BE-4, DB-1).
  3. **Correo con SMTP que no responde** durante 5 minutos: hilos ocupados y profundidad de cola (BE-3).
  4. **Corte de la base** durante la carga: cuántas peticiones quedan esperando y cuánto tardan en fallar (BE-2).
  5. **Sesión de medición completa** con un puente simulado: latencia de extremo a extremo.
  6. **Mantenimiento en marcha**: duración de cada pasada y su efecto sobre la API (BE-5, DB-4).
- Registrar p50, p95, rendimiento, CPU, memoria, conexiones y errores en cada corrida.

## 10. Revisado y sin cuello con la evidencia actual

- **Sondeo SSE:** 1,3 % de un núcleo con 300 streams (medido). El límite de 6 streams por usuario y 300 en total (`api/streams.py:20-21`) es razonable.
- **Ingreso de lecturas del puente:** una operación indexada por segundo y escrituras de último uso limitadas (sección 5).
- **Historial del paciente:** paginado, con tope de 50 filas por página (`measurement.py`, `MAX_PAGE_SIZE`). Solo el `COUNT` de DB-1 es el problema.
- **Contacto:** el envío bloqueante corre en `run_in_threadpool` (`api/v1/contact.py`) y tiene límite de 5 consultas por 15 minutos por IP.
- **Estáticos:** Nginx sirve con `gzip_static` (archivos precomprimidos al construir la imagen) y `expires 1y` (`docker/nginx/default.conf.template`). Las visitas repetidas no vuelven a descargar el bundle.
- **Columnas calculadas de `Medicion`** (`minutosDesdeUltimaComida`, `duracionMs`): solo se leen, no se filtran.
- **Índice de muestras del sensor:** `UQ_MuestraSensor_orden (idMedicion, numeroMuestra)` cubre las búsquedas por medición.

## 11. Prioridad sugerida

| Prioridad | Acción | Referencia |
|---|---|---|
| **P1** | Limitar la concurrencia de verificaciones de contraseña y medir ráfagas en 512 MB y 1 GB | BE-1 |
| **P1** | Timeouts de conexión, de consulta y de espera en el semáforo | BE-2 |
| **P1** | Registro de duración por ruta y contadores de semáforo y de cola | SR-1 |
| **P1** | Medir en un entorno igual al de destino (Windows, SQL Server Express) | PT-2, DB-5 |
| **P1** | Plan de ejecución real de `_history` y decisión sobre el índice | DB-1 |
| P2 | Correo fuera de la petición y cola acotada con *outbox* | BE-3 |
| P2 | Agregados en SQL para dashboards | BE-4 |
| P2 | Pausar sondeos con la pestaña oculta y unificarlos | FE-2 |
| P2 | Sacar el mantenimiento de la API o medir su costo | BE-5 |
| P2 | Indicador de disponibilidad (readiness) | SR-2 |
| P2 | Búsquedas sin comodín inicial; paginación por cursor | DB-2, DB-3 |
| P3 | CSS e íconos por ruta, con cobertura medida | FE-1 |
| P3 | Evaluar más de un proceso por contenedor (después de BE-2 y SR-3) | SP-1 |
| P3 | Perfilar el build del frontend | FE-3 |
| P3 | Renderizado de gráficos durante la adquisición | FE-4 |

## 12. Límites de esta revisión

- **Ninguna consulta SQL se midió.** DB-1 a DB-4 son hipótesis hasta tener un plan de ejecución.
- Argon2id se midió en la CPU de la revisión, con los parámetros de producción. El límite de logins por memoria (≈7 y ≈16) es una estimación: la base del proceso dentro del contenedor no se midió.
- La compilación del frontend es una sola corrida. El bundle se midió con el build de esta revisión; el tamaño comprimido usa gzip -9, cercano al precomprimido que sirve Nginx.
- La medición de memoria de `Medicion` es una cota inferior.
- No se ejecutó ninguna prueba de carga, porque no hay base disponible en este entorno.
