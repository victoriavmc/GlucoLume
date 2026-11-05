# Cuellos de botella de rendimiento

> Diagnóstico por código del 05/11/2026, sobre la rama `claude/modest-curie-903ohj`. Ordena los cuellos de botella según los perfiles de ingeniería de rendimiento.
> **No cambia código, no fija metas y no reemplaza las mediciones** de [RENDIMIENTO.md](../RENDIMIENTO.md) (23/10/2026), que sigue siendo la referencia de lo medido.

## 1. Alcance y método

- Se revisaron el backend (FastAPI, SQLAlchemy, SQL Server), el frontend (React, Vite, Nginx), la configuración Docker, el esquema SQL consolidado y los informes previos ([RENDIMIENTO.md](../RENDIMIENTO.md), [PENDIENTES.md](../PENDIENTES.md), `PR_rendimiento.md`).
- **Esta revisión no ejecutó carga ni midió nada nuevo.** Cada hallazgo lleva una etiqueta de evidencia:
  - **Medido**: hay una medición reproducible en `docs/RENDIMIENTO.md` o en `docs/evidencias/rendimiento/`.
  - **Código**: se observa en el código; falta medirlo.
  - **Hipótesis**: se deduce del código; hay que confirmarla antes de tocarla.
- Las mediciones previas se hicieron en Docker Desktop/WSL2 con **1 CPU** y **datos sintéticos**. El destino real es Windows con SQL Server (ver PT-2).

## 2. Resumen

| ID | Cuello de botella | Perfil principal | Evidencia | Severidad | Estado |
|---|---|---|---|---|---|
| BE-1 | Concurrencia en el driver ODBC (tope de 2 llamadas) | Backend, DB | Medido | Alta | Mitigado; falta barrido en el servidor destino |
| BE-6 | Sin timeout de consulta ni de espera en el semáforo | Backend, SRE | Código | **Alta** | Abierto |
| DB-1 | `Medicion` sin índice por `idPerfilMedicion` | Database | Hipótesis | **Alta** | Confirmar con plan de ejecución |
| BE-4 / BE-5 | Correo en la petición y cola en memoria de 2 hilos | Backend, SRE | Medido (≈40 llamadas, hasta 20 s) + Código | Alta | Abierto (P2) |
| SR-1 | Sin métricas de aplicación ni registro de accesos | SRE | Código | **Alta** | Abierto |
| PT-1 / PT-2 | Sin pruebas de carga automatizadas; entorno no representativo | Performance Testing | Código | **Alta** | Abierto |
| BE-3 | Dashboards traen hasta 50 000 filas a Python | Backend, DB | Medido (institución) + Código | Media-alta | Abierto (P2) |
| DB-2 | Búsquedas `LIKE '%…%'` sobre varias columnas | Database | Código | Media | Abierto |
| DB-3 | Paginación con `OFFSET` sobre la auditoría | Database | Código | Media | Abierto |
| FE-1 | Sondeos cada 3 a 10 s sin pausa con la pestaña oculta | Frontend, Backend | Código | Media | Abierto |
| FE-2 | Compilación del frontend de 3 min 20 s | Frontend, SRE | Medido | Media (entrega) | Sin solución |
| BE-7 | Streams SSE con sondeo cada 0,2 s | Backend | Código | Media | Abierto |
| BE-2 | Un solo proceso Uvicorn con 1 CPU y 512 MB | Backend, SRE | Código | Media | Límite de diseño |

**Ruta crítica de una medición.** Sensor → puente de Windows (latido y envío cada 1 s) → API → SQL Server → SSE → interfaz. La escritura de muestras ya se corrigió (ver §9). Los cuellos que quedan están en la **lectura** (dashboards, historial, auditoría), en la **conexión a la base** (concurrencia, timeouts) y en el **correo**.

---

## 3. Software Performance Engineer (visión integral)

- **Tope de CPU y de proceso (BE-2).** La API corre en un único proceso Uvicorn (`backend/Dockerfile`, línea 78, sin `--workers`), con `cpus: 1.0` y `memory: 512M` en `compose.yaml`. Toda la lógica Python (JSON, hash Argon2id en cada inicio de sesión, render de correos, agregación de dashboards) compite por una sola CPU.
- **Escalar horizontalmente rompe supuestos (BE-8).** El semáforo del driver (BE-1) es **por proceso**: con *N* réplicas hay hasta *2N* llamadas simultáneas contra SQL Server, y el número vuelve a subir la contención que BE-1 corrigió. El limitador de solicitudes y el hub de telemetría están en memoria; el hub exige una sola réplica (`backend/app/services/rateLimiter.py`, cabecera).
- **Decisión a tomar:** antes de agregar réplicas o workers hay que medir el tope por proceso y el consumo de Redis (`compose.redis.yaml`), no suponer que escalan.

## 4. Backend Performance Engineer

**BE-1 · Concurrencia del driver ODBC** · *Medido, mitigado*
- **Dónde:** `backend/app/db/gate.py`, `backend/app/db/session.py` (`_createEngine`).
- **Qué pasa:** con 6 u 8 hilos dentro de pyodbc a la vez, el rendimiento cae cerca de 9× (RENDIMIENTO §3.1). El tope por defecto (`DB_MAX_CONCURRENT_CALLS=2`) lo corrige: con 8 clientes pasa de 4,4 a 28,2 req/s y el p95 de 7,0 s a 0,75 s.
- **Pendiente:** la causa interna del driver `msodbcsql18` y el valor óptimo en el servidor destino (PENDIENTES, Rendimiento).

**BE-6 · Sin timeout de consulta ni de espera en el semáforo** · *Código, riesgo alto*
- **Dónde:** `_createEngine` (la cadena de conexión no fija timeout de conexión ni de consulta); `gate.py` (`with self._gate:` espera sin límite).
- **Qué pasa:** `DB_LOCK_TIMEOUT_MS` (5 000 ms, `backend/app/core/config.py:60`) acota solo las esperas por **bloqueos**. Una consulta colgada por red o por un servidor que no responde no tiene límite. Si dos llamadas quedan colgadas, ocupan los dos cupos del semáforo y **toda** petición que use la base se detiene, mientras `/healthz` (que no consulta la base) sigue respondiendo bien.
- **Cómo confirmar:** simular un corte de red o un servidor que no responde entre la API y SQL Server, y medir cuántas peticiones quedan esperando y durante cuánto tiempo.
- **Dirección:** timeout de conexión y de consulta en la cadena de conexión, y un tiempo máximo de espera al tomar el semáforo que devuelva un error controlado.

**BE-2 · Un proceso, una CPU** · *Código*
- **Dónde:** `backend/Dockerfile:78`, `compose.yaml` (servicio `backend`).
- **Qué pasa:** la mayoría de los endpoints son `def` (síncronos) y AnyIO los ejecuta en su pool de hilos (40 por defecto). Con una CPU, el paralelismo real de Python es limitado y el pool compite por el GIL.
- **Cómo confirmar:** perfil de CPU bajo carga (`py-spy`) y medir si el tiempo se va en Python o en espera de la base.

**BE-3 · Dashboards que traen filas a Python** · *Medido (institución) + Código*
- **Dónde:** `backend/app/services/dashboard.py:209` (`MAX_ADMIN_ROWS = 50000`), `:565` (`MAX_CHART_ROWS = 20000`); `patientAnalytics.py:52` (`MAX_ROWS = 100000`); `securityDetection.py:41` (`MAX_ROWS = 5000`).
- **Qué pasa:** las agregaciones se hacen en Python sobre filas traídas de la base. El costo crece con el número de mediciones y el tope de filas es también un tope de memoria. Medido: el dashboard de institución tiene p50 de 142 ms con 8,7 mil mediciones y crece con los datos; 16 a 31 sentencias por carga (RENDIMIENTO §3.5).
- **Dirección:** llevar `GROUP BY` y los agregados a SQL y comparar fila a fila con el resultado actual (PENDIENTES, Rendimiento).

**BE-4 · Correo en la ruta de la petición** · *Medido (≈40 llamadas) + Código*
- **Dónde:** `sendEmailEvent` (síncrono) se llama directamente desde `services/auth.py:256`, `mfaRecovery.py:164`, `passwordChangeCode.py:103`, `accountDeletion.py:249`, `measurement.py:1112` y `:1150`, `userNotifications.py:344`, `platform.py:200` y `:479`. El envío en segundo plano (`sendEmailEventInBackground`) sí se usa en la mayoría de los demás flujos.
- **Qué pasa:** cada envío síncrono ocupa un hilo del pool de la petición durante todo el intento SMTP. El timeout es de 20 s (`backend/app/integrations/email/sender.py:16`). Con un SMTP lento, esos hilos se agotan y las peticiones que no tienen nada que ver con el correo empiezan a esperar. Medido: hasta 20 s de espera dentro de la petición HTTP.
- **Dirección:** pasar los envíos restantes a segundo plano o a una cola persistente (*outbox*), conservando el registro del resultado del envío (PENDIENTES, Rendimiento).

**BE-5 · Cola de correos en memoria** · *Código*
- **Dónde:** `backend/app/services/email.py:72` (`ThreadPoolExecutor(max_workers=2)`, cola sin límite).
- **Qué pasa:** con SMTP lento o caído, la cola crece sin tope y **se pierde al reiniciar** el proceso. No hay reintentos ni métricas de profundidad.
- **Cómo confirmar:** simular un SMTP que no responde y observar la profundidad de la cola y los correos perdidos tras un reinicio.

**BE-7 · SSE con sondeo cada 0,2 s** · *Código*
- **Dónde:** `backend/app/api/v1/acquisition.py` (`stream`, alrededor de las líneas 77 a 120), `backend/app/api/v1/telemetry.py` (`telemetryStream`, línea 185). Cada iteración hace `channel.get_nowait()` y `asyncio.sleep(0.2)`; `Revalidator` (`backend/app/api/streams.py:87`) vuelve a consultar la sesión cada `STREAM_REVALIDATE_SECONDS`.
- **Qué pasa:** cada stream abierto despierta unas 5 veces por segundo aunque no haya datos. Con una CPU, muchos streams compiten con el resto de la API. El canal es una `queue.Queue` de hilos, por eso se sondea; un puente a `asyncio` evitaría el sondeo.
- **Cómo confirmar:** medir el uso de CPU con 0, 10 y 50 streams abiertos y sin datos.

**BE-8 · Estado en memoria y escalado** · *Código*
- Ver §3. El limitador de solicitudes usa memoria por defecto y Redis solo si se configura `RATE_LIMIT_REDIS_URL`; el hub de telemetría requiere una réplica.

**BE-9 · Pool de conexiones por defecto y `pool_pre_ping`** · *Hipótesis (costo bajo)*
- **Dónde:** `session.py`, `create_engine(url, pool_pre_ping=True)`; no se configura `pool_size` ni `max_overflow` (valores por defecto de SQLAlchemy).
- **Qué pasa:** `pool_pre_ping` agrega un viaje de ida y vuelta en cada préstamo de conexión. Con el semáforo en 2, el pool suele sobrar; el costo real es pequeño, pero no está medido.

## 5. Frontend Performance Engineer

**FE-1 · Sondeos concurrentes sin pausa en pestaña oculta** · *Código*
- **Dónde y periodos:** `LiveAcquisition.jsx:17` (3 s), `MeasurementPanel.jsx:28` (3 s), `useDeviceReadiness.js:10` (5 s), `useDeviceStatus.js:11` (5 s), `PersonalDashboard.jsx:46` (10 s), `useIncomingNotifications.js:11` y `useNotificationList.js` (30 s), `MeasurementHistory.jsx:88` (60 s).
- **Qué pasa:** `ConnectDevicePage.jsx` importa componentes que usan `LiveAcquisition`, `useDeviceReadiness` y `MeasurementPanel`; si se montan a la vez, una sola pantalla dispara varias peticiones cada 3 a 5 s por usuario. Solo `useIncomingNotifications.js` y `useNotificationList.js` leen `visibilityState`; el resto sigue consultando con la pestaña oculta. `enSegundoPlano` (`api/client.js:75`) solo marca la petición como de fondo; no pausa ni limita los sondeos.
- **Cómo confirmar:** en la pantalla de conexión del dispositivo (`ConnectDevicePage`, ruta declarada en `frontend/src/App.jsx:82`), pestaña Red de DevTools con la ventana en primer plano y luego oculta, contando peticiones por minuto.
- **Dirección:** pausar los sondeos con `document.hidden`, unificar los que consultan lo mismo y reemplazar los sondeos de adquisición por el stream SSE que ya existe.

**FE-2 · Compilación de 3 min 20 s** · *Medido, sin solución*
- **Dónde:** `frontend/vite.config.js`, fase de tree-shaking de Rollup.
- **Qué pasa:** cerca del 75 % del tiempo se va en el análisis de Rollup al dibujar `<App/>`. No es `lucide-react`, ni los datos de consejos, ni las opciones de `treeshake` probadas (RENDIMIENTO §3.2). Afecta el ciclo de desarrollo y la entrega, no al usuario final.

**FE-3 · Cifras de bundle inconsistentes** · *Por aclarar*
- `PR_rendimiento.md` indica JS inicial de 124 a 196 KB; `PENDIENTES.md` indica un bundle inicial de ~887 kB. Puede ser la diferencia entre comprimido y sin comprimir, o entre inicial y total. Hay que aclararlo antes de fijar una meta.

**FE-4 · Gráficos y render por muestra** · *Medido (TBT) + Hipótesis*
- **Dónde:** `LiveChart.jsx`, `PpgChart.jsx`, `SignalChart.jsx`, `TimeSeriesChart.jsx`, `AnalyticsCharts.jsx`.
- **Qué pasa:** el TBT del dashboard de institución en 3G con CPU 4× sigue en 1,2 s por el render de gráficos (PENDIENTES, Rendimiento). El INP no se midió con un guion de interacción real. La hipótesis es que cada evento SSE actualiza estado y repinta gráficos completos; hay que confirmarlo con el React Profiler.

**FE-5 · Estabilidad visual de `/pacientes`** · *Medido*
- CLS de 0 a 0,13 en 3G según la corrida (RENDIMIENTO §9). Hace falta reservar el espacio de la tabla antes de cargar los datos.

**FE-6 · Peticiones por pantalla sobre HTTP/1.1** · *Medido + Código*
- Con la carga diferida cada pantalla pide más archivos. `docker/nginx/default.conf.template` sirve el frontend sin HTTP/2 (lo da el proxy Caddy, si está). Las cargas repetidas quedan cubiertas por `expires 1y` (línea 172), así que el impacto está en la primera visita.

## 6. Database Performance Engineer

**DB-1 · `Medicion` sin índice por `idPerfilMedicion`** · *Hipótesis, prioridad alta*
- **Dónde:** `database/reference/GlucoLume_DB_v5.sql` (índices de `Medicion`: `IX_Medicion_estado_fin` y `IX_Medicion_vencimientoRetencion`); `backend/app/models/measurement.py` (FK `FK_Medicion_Perfil`); consultas en `backend/app/services/dashboard.py:116` (`idPerfilMedicion IN (…)`) y `:191`.
- **Qué pasa:** `idPerfilMedicion` no es la clave de ningún índice; aparece solo como `INCLUDE` en `IX_Medicion_estado_fin`, que no sirve para buscar por ese valor. Las consultas de historial y de resumen filtran por perfil y ordenan por `fechaHoraInicio DESC`, así que es probable que hagan un recorrido amplio de la tabla y un ordenamiento. El costo crece con cada medición.
- **Cómo confirmar:** plan de ejecución real de la consulta de historial con `SET STATISTICS IO ON` o con Query Store, con un volumen parecido al de producción. Si confirma el recorrido, el índice compuesto `(idPerfilMedicion, fechaHoraInicio)` es el candidato natural; hay que medir antes y después.

**DB-2 · Búsquedas con comodín inicial** · *Código*
- **Dónde:** `institutionPatients.py:305` a `:313` (`ilike` con `%término%` sobre `dni`, `nombre`, `apellido` e `identificadorPseudonimo`, combinados con `OR`); `auditQuery.py:162` a `:175` (concatenación con `coalesce` antes del `ilike`, lo que impide el uso de índices); `auditQuery.py:1112`; `device.py:288`.
- **Qué pasa:** un comodín al inicio no usa índices; combinar varias columnas con `OR` empeora el plan. El costo crece con el número de pacientes y de auditorías.
- **Dirección:** búsqueda por prefijo cuando sea posible, columnas normalizadas o índices de texto completo; medir con un volumen grande.

**DB-3 · Paginación con `OFFSET`** · *Código*
- **Dónde:** `auditQuery.py:924`, `institutionActivity.py:204`, `platformInstitutions.py:329`, `technicalAudit.py:75`.
- **Qué pasa:** `OFFSET` descarta filas en el servidor, así que las páginas profundas cuestan más. Las consultas ya ordenan por `(fechaHora, idAuditoria)`, que es una clave estable: se puede pasar a paginación por cursor sin cambiar el orden.

**DB-4 · Retención y limpieza compitiendo con la API** · *Código + hipótesis*
- **Dónde:** `measurementRetention.py:160` y `:169`, `auditRetention.py:61` y `:142`; servicio `notifications` en `compose.yaml`.
- **Qué pasa:** los trabajos borran en lotes mientras la API escribe. Si un lote retiene bloqueos, las peticiones esperan hasta `DB_LOCK_TIMEOUT_MS` (5 s) y fallan con error. No hay métricas de duración de lote.
- **Cómo confirmar:** correr la retención con datos de volumen y medir los errores de bloqueo en la API durante el lote.

**DB-5 · Límites de SQL Server Express** · *Código (verificar)*
- El destino previsto es Windows con SQL Express (PENDIENTES, P1). SQL Server Express tiene límites publicados de tamaño por base de datos y de memoria para la caché de búfer, además de un máximo de núcleos. Si la instalación real es Express, el tamaño de la base y la caché son cuellos que las pruebas en Docker no reproducen. Verificar los límites de la versión instalada antes de fijar capacidades.

**Lo que no es cuello en la base:** `MuestraSensor` tiene el índice único `UQ_MuestraSensor_orden (idMedicion, numeroMuestra)`, que cubre las búsquedas por medición. Las columnas calculadas `minutosDesdeUltimaComida` y `duracionMs` solo se leen, no se filtran.

## 7. Site Reliability Engineer (SRE)

**SR-1 · Sin métricas ni registro de accesos en producción** · *Código, prioridad alta*
- **Dónde:** `backend/Dockerfile:78` (`--no-access-log`); no hay endpoint `/metrics` ni cliente de Prometheus o StatsD en el código. `opentelemetry-api` aparece en `backend/requirements.txt:626` solo como dependencia transitiva.
- **Qué pasa:** en producción no hay latencia por endpoint, tasa de errores, profundidad de la cola de correo ni tamaño del pool. Hoy el rendimiento solo se conoce con pruebas manuales.
- **Dirección mínima:** registrar duración y código por petición, exponer contadores de la cola de correo y del semáforo, y medir la latencia p95 por ruta.

**SR-2 · Health check superficial** · *Código (verificar)*
- `/healthz` (`backend/app/main.py:63`) es **liveness** por diseño: no consulta la base, para que una caída de SQL Server no reinicie el contenedor en bucle. Eso es correcto, pero falta una comprobación de **disponibilidad** (readiness) que refleje si la base responde y si el semáforo está ocupado (ver BE-6). Hoy un corte de la base no aparece en el estado del servicio.

**SR-3 · Recursos ajustados y punto único** · *Código*
- Un contenedor de API con 1 CPU y 512 MB, un servicio de ciclo de vida con 0,5 CPU y 256 MB, y una sola base. No hay réplica ni plan de alta disponibilidad. Antes de dimensionar, medir consumo real de CPU y memoria con el perfil de uso esperado.

## 8. Performance Testing Engineer

**PT-1 · Sin pruebas de carga automatizadas** · *Código, prioridad alta*
- El repositorio no tiene carpeta `.github/` ni pipeline de integración continua. Las pruebas de carga son manuales.

**PT-2 · Entorno no representativo** · *Medido + Código, prioridad alta*
- Las mediciones previas usaron Docker Desktop/WSL2 con 1 CPU y datos sintéticos. El tope de 2 llamadas se midió en ese entorno (RENDIMIENTO §3.1 y `docs/evidencias/rendimiento/README.md`). El destino real es Windows con SQL Server y el puente de Windows, con otro perfil de CPU, disco y red.

**PT-3 · Herramientas existentes y escenarios que faltan**
- Ya existen en `docs/evidencias/rendimiento/`: `carga_endpoint.py` (N clientes sobre un mismo endpoint), `medir_http.py`, `hilos_micro*.py`, `medir_consultas.py`, `medir_frontend.mjs`, `cls_fuentes.mjs` y `compose.rendimiento.yaml`.
- Escenarios que faltan, cada uno con criterios de aceptación que defina el equipo:
  1. **Inicio de sesión concurrente** (costo de Argon2id en una CPU).
  2. **Dashboards con volumen grande** (BE-3, DB-1, DB-2): p95 con 50 000 mediciones y con 500 000.
  3. **Correo con SMTP lento** (BE-4, BE-5): simular un servidor que tarda 20 s y medir el pool y la cola.
  4. **Muchos streams SSE abiertos** (BE-7) sin datos y con datos.
  5. **Corte de la base** (BE-6): cuántas peticiones quedan colgadas y cuánto tardan en fallar.
  6. **Sesión de medición completa** con un puente simulado: latencia de extremo a extremo.
- Registrar p50, p95, rendimiento, CPU, memoria, conexiones y errores en cada corrida, y guardar los resultados en `docs/evidencias/rendimiento/`.

## 9. Ya resuelto o descartado

- **Escrituras de muestras del sensor:** de 403 `INSERT` (211 ms) a 4 escrituras (52 ms) en la misma transacción (RENDIMIENTO §8.1).
- **Concurrencia del driver:** mitigada con el semáforo (BE-1).
- **Carga diferida, esqueletos y `useLatestRequest`:** JS inicial reducido y respuestas viejas que no pisan a las nuevas (RENDIMIENTO §5 y §6).
- **Correo de contacto:** el envío bloqueante corre en el pool de hilos (`backend/app/api/v1/contact.py`), no en el event loop.
- **Estáticos:** `gzip_static`, `expires 1y` y `robots.txt` en Nginx.
- **Descartados con medición:** `lucide-react`, datos de consejos y opciones de `treeshake` como causa de la compilación lenta (RENDIMIENTO §3.2).

## 10. Prioridad sugerida

| Prioridad | Acción | Ref. |
|---|---|---|
| **P1** | Timeouts de consulta y de espera en el semáforo | BE-6 |
| **P1** | Métricas por ruta, cola de correo y semáforo; registro de accesos | SR-1 |
| **P1** | Medir en el servidor destino (Windows + SQL Server, edición real) | PT-2, DB-5 |
| **P1** | Confirmar con el plan de ejecución el índice de `Medicion` | DB-1 |
| P2 | Dashboards con agregados en SQL | BE-3 |
| P2 | Búsquedas sin comodín inicial; paginación por cursor en auditoría | DB-2, DB-3 |
| P2 | Correo restante en segundo plano y cola persistente (*outbox*) | BE-4, BE-5 |
| P2 | Pausar sondeos con la pestaña oculta y unificarlos | FE-1 |
| P2 | Pruebas de carga de los seis escenarios de PT-3 | PT-1, PT-3 |
| P3 | SSE sin sondeo; bridge a `asyncio` | BE-7 |
| P3 | Aclarar las cifras de bundle; reducir render de gráficos | FE-3, FE-4 |
| P3 | Reservar espacio en `/pacientes`; HTTP/2 en Nginx | FE-5, FE-6 |
| P3 | Revisar `pool_pre_ping` y el pool de SQLAlchemy | BE-9 |

## 11. Límites de esta revisión

- No se midió nada nuevo. Todo lo marcado como *Hipótesis* o *Código* requiere confirmación.
- La causa interna del driver ODBC y el valor óptimo del tope en el servidor destino siguen abiertos (RENDIMIENTO §3.1).
- Los límites de SQL Server Express (DB-5) deben verificarse contra la edición instalada.
- Las cifras de bundle (FE-3) están en conflicto entre dos documentos.
