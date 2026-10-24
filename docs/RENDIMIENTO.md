# Rendimiento

> Revisión del 23/10/2026 (rama `perf/rendimiento-2026-10-23`, sobre `master` ya integrado). Todo lo medido salió de un stack descartable con datos **sintéticos** y reproducible con los scripts de
> [evidencias/rendimiento](evidencias/rendimiento/README.md). No se tocó la base «GlucoLume» ni la instancia real de Windows. Lo que no se pudo medir figura como tal, con el motivo (§9).

Regla seguida: solo se corrigió lo que una medición demostró, sin cambiar funcionalidades ni reglas de negocio; lo demás queda como hallazgo o pendiente. La remediación de seguridad ya validada no se tocó.

## 0. Matriz de resultados

| # | Problema | Veredicto | Dónde (archivo · función) | Causa técnica | Impacto medido | Corrección | Pruebas |
|---|---|---|---|---|---|---|---|
| 1a | Dependencias lentas: **concurrencia del driver ODBC** | **Confirmado** | [`backend/app/db/session.py`](../backend/app/db/session.py) `_createEngine` → nuevo [`app/db/gate.py`](../backend/app/db/gate.py) | Con ≥ 5–6 hilos dentro de `pyodbc` a la vez, el rendimiento cae ~9× y la CPU por consulta se multiplica ~40× (con pyodbc puro: no es SQLAlchemy, ni el cifrado, ni el pool, ni la GIL) | 8 clientes: **4,4 → 28,2 req/s**, p95 **7,0 s → 0,75 s**; 32 clientes: 3,5 → 26,1 req/s (§3.1) | Semáforo de llamadas al driver (`DB_MAX_CONCURRENT_CALLS`, por defecto 2, configurable) | 7 pruebas nuevas + suite; carga sobre SQL Server real |
| 1b | Dependencias lentas: **compilación del frontend** | **Confirmado, no resuelto** | `frontend/vite.config.js` (fase de tree-shaking de Rollup) | ~75 % de los ~215 s se van en el análisis de «include» de Rollup al dibujar `<App/>`; no es `lucide-react`, ni los datos de consejos, ni las opciones de `treeshake` probadas (§3.2) | 3 min 20 s en Docker y 3 min 36 s en Windows, igual antes y después | Ninguna (hipótesis descartadas con medición) | — |
| 1c | Dependencias lentas: **JS inicial** | **Confirmado** | `frontend/src/App.jsx` | Todas las pantallas importadas de forma estática: un solo archivo de 888 kB | JS inicial **297 → 124–196 KB** transferidos según la pantalla; en 3G el FCP de la portada **2,8 → 1,7 s** y el de las pantallas autenticadas **2,2–2,5 → 1,26–1,28 s** | Carga diferida por pantalla + precarga de la ruta + íconos en un solo archivo (§5) | 700/700 frontend |
| 1d | Correo / SMTP | **Confirmado (por código), parcialmente corregido** | `services/email.py` `sendEmailEvent` (unas 40 llamadas, la mayoría en línea con 20 s de *timeout*) | El envío SMTP bloquea la respuesta HTTP; solo el aviso de inicio de sesión va en segundo plano | No medido contra SMTP real (no se envía correo real) | Solo el aviso de medición al grupo pasa a segundo plano (§3.4) | suite |
| 1e | Redis | **No medido** (opcional y apagado) | `services/rateLimiter.py` | Opcional y apagado por defecto; con Redis es un viaje por pedido con corte de circuito | No medido (no está activo) | — | — |
| 1f | SQL costosas | **Confirmado, pendiente** | `services/dashboard.py` (institución: 31 sentencias, `TOP 50000`) | Traen decenas de miles de filas para agregarlas en Python | Dashboard de institución p50 **142 ms**, el más lento; escala con los datos | No se tocó (riesgo sobre cálculos del panel) | — |
| 2a | Peticiones secuenciales: `useHomeData` | **Descartado** | `frontend/src/pages/Account/home/useHomeData.js` | Ya pide en paralelo las dos series y descarta respuestas viejas (`active`) | 0 solicitudes repetidas (§4) | — | — |
| 2b | **Condición de carrera** (respuesta vieja pisa a la nueva) | **Confirmado** | `PatientsPage.jsx`, `MeasurementHistory.jsx`, `DevicesInventory.jsx`, `TransfersPage.jsx` · `load` | La función de carga no descartaba respuestas anteriores | Reproducido con prueba que **falla** con el código anterior | Hook `useLatestRequest` | 2 pruebas de regresión + 3 del hook |
| 2c | Endpoints `async` con bloqueo | **Descartado** | `app/api/v1/*` | Solo 4 `async def` de negocio; `contact` usa `run_in_threadpool`; el resto son `def` en el *threadpool* | — | — | — |
| 3a | **Escrituras una a una**: muestras del sensor | **Confirmado** | `services/measurement.py` `addSamples` | El ORM ejecuta un `INSERT` por muestra (clave `newsequentialid()` del servidor) | 400 muestras = **403 INSERT**, 211 ms | `INSERT` de varias filas (400 por sentencia): **414 → 15 sentencias, 403 → 4 escrituras, 211 → 52 ms** por tanda de 400 | 2 pruebas nuevas |
| 3b | Otros bucles con `commit`/N+1 | **Descartado** | `measurementLifecycle.invalidateStale`, `institutionReassignments`, `audit._identitySnapshot` | Transacción por elemento y auditoría por elemento son deliberadas; los N son chicos | — | — | — |
| 4 | Optimistic loading | **Parcial** | Skeletons: `components/Skeleton.jsx`; progresivo: ya existía | Pantallas con spinner de página completa o texto suelto | CLS igual o mejor, salvo `/pacientes` en 3G (0,058 → 0,13, inestable entre corridas; §6) | Esqueletos; **optimistic UI no aplicado** a propósito (§6) | suite |
| 5 | Página no estática | **Descartado** (ya es estática) + mejoras SEO | `docker/nginx/default.conf.template` | Se sirve `dist/` compilado con Nginx; `index.html` sin caché y assets con hash a 1 año ya estaban bien | `/robots.txt` y `/sitemap.xml` devolvían HTML con 200; faltaba `Vary` | gzip precomprimido, `robots.txt`, 404 de archivos, `X-Robots-Tag` (§7) | Nginx real |
| + | **Defecto funcional hallado** (no de rendimiento) | **Confirmado y corregido** | `services/notifications.py` `notifyGroupMeasurement` | `.is_(True)` llega a SQL Server como `IS 1` (error 102): el aviso al grupo **nunca se enviaba** y el error quedaba tragado | Visible en el log de cada cierre de medición | `== True` + guarda estática | 1 prueba nueva |

## 1. Entorno y método

- **Equipo:** Windows 11, 16 hilos lógicos, 64 GB; Docker Desktop (WSL2, 16 CPU, 31 GB). Las mediciones se hicieron sin otras cargas pesadas a propósito (las suites y las compilaciones se corrieron antes o después); el equipo no estuvo aislado de los procesos normales del sistema.
- **Stack medido** (`docs/evidencias/rendimiento/compose.rendimiento.yaml`): SQL Server 2022 CU16 (el contenedor del perfil `db`, base descartable `GlucoLume_perf`), API en contenedor con los límites de producción (1 CPU, 512 MB) y Nginx real del proyecto (0,5 CPU, 128 MB). Imágenes `…:baseline` (código de `master`) y `…:perf` (esta rama).
- **Datos sintéticos** (`seed.py`, servicios reales de la aplicación): 5 cuentas, 1 institución, **601 perfiles**, **8 708 mediciones** (1 500 de la cuenta individual, 12 por paciente), 3 200 muestras de sensor.
- **Herramientas:** Playwright 1.49 + Chromium (FCP, LCP, CLS, TBT con `PerformanceObserver`; red «Fast 3G» de DevTools —1,6 Mbps, 150 ms— y CPU 4× más lenta), `medir_http.py` (p50/p95/p99 y concurrencia con conexiones persistentes), `medir_consultas.py` (sentencias SQL y tiempo de base por operación, en proceso y contra SQL Server real), microbenchmarks de hilos (`hilos_*.py`).
- **Repeticiones:** 5 por pantalla y condición (mediana), 100 pedidos por endpoint, 15 s por nivel de concurrencia. Una sesión de login por pantalla (el login tiene límite por IP).
- **INP:** no se midió. Chromium solo lo informa con interacciones reales del usuario y no hay un guion de interacción estable; el análogo medido es TBT (bloqueo del hilo principal). Ver §9.

## 2. Línea base (resumen)

| Medida | Antes (`master`) |
|---|---|
| JS inicial transferido (gzip de Nginx) | 296,7 KB en 1 archivo (888 kB sin comprimir) + CSS 41 KB |
| Carga / FCP de la portada, red rápida · «Fast 3G» | 53 ms / 168 ms · 2 155 ms / 2 776 ms (TBT 578 ms) |
| Consultas SQL por operación | de 3 (perfil) a 31 (dashboard de institución); login 7 con 4 escrituras y 3 *commit* |
| Latencia secuencial p50 | 8,7 ms (operadores asignables) a 141,6 ms (dashboard de institución) |
| Concurrencia (mezcla de 5 endpoints) | 1 cliente 20,3 req/s · **8 clientes 4,4 req/s** · **32 clientes 3,5 req/s** |
| Guardar 400 muestras | 414 sentencias (403 `INSERT`), 211,6 ms en una tanda |
| Compilación del frontend (`vite build`) | 3 min 26 s en Docker · 3 min 36 s en Windows |

## 3. Dependencias lentas

### 3.1 Concurrencia del driver ODBC (el hallazgo de mayor impacto)

**Síntoma.** Con un cliente, la API atiende ~20 req/s; con 8 clientes, **baja a 4,4 req/s** (p95 7 s) y con 32 a 3,5 req/s: sirve a *más* clientes con *menos* trabajo total. El contenedor consume el 100 % de su CPU y la base de datos solo el 15 %.

**Cómo se aisló** (`hilos_servicio.py`, `hilos_micro.py`, `hilos_micro2.py`, `hilos_micro3.py`; contenedor con 1 CPU, SQL Server real):

| Prueba (1, 4 y 8 hilos) | 1 hilo | 4 hilos | 8 hilos |
|---|---|---|---|
| Python puro (la GIL no es la causa) | 0,67 ms CPU/llamada | 0,68 | 0,60 |
| `pyodbc` puro, 20 filas | 1 939/s (0,11 ms CPU) | 2 473/s (0,41) | **187/s (4,96 ms CPU)** |
| `pyodbc` puro, `SELECT 1` | 4 137/s | 8 792/s | 2 568/s |
| SQLAlchemy Core, 20 filas | 1 436/s | 1 035/s | 183/s |
| Servicio de listado de pacientes (código real, `hilos_servicio.py`) | 104/s (4,9 ms CPU) | 72/s (11,8) | **21/s (45,1 ms CPU)** |

Descartado con mediciones: **no** es el cifrado (`Encrypt=no` da lo mismo: 191/s), **no** es MARS (193/s), **no** es el *pooling* de ODBC (191/s), **no** es el intervalo de conmutación de la GIL (0,2–5 ms: 186–206/s), **no** es el pool de SQLAlchemy (solo 4 conexiones nuevas en toda la corrida) y **no** depende del límite de CPU del contenedor (con 16 CPU: 29/s). El «precipicio» está entre 4 y 6 hilos dentro del driver (4 hilos: 1 467/s; 6 hilos: 288/s). Solo se recupera limitando cuántos hilos están **dentro** de `pyodbc` al mismo tiempo, y el límite tiene que cubrir *ejecutar y traer filas* (limitar solo uno de los dos: 194/s y 533/s; limitar ambos a 3: 3 039/s, más que con un hilo). Salidas: `resultados/hilos_*.txt`.

**Corrección.** [`app/db/gate.py`](../backend/app/db/gate.py): un semáforo que se toma solo durante **una** llamada al driver (`execute`, `fetch*`, `commit`, `rollback`), nunca entre llamadas. No retiene nada mientras el código hace otra cosa ni se anida, así que **no puede producir interbloqueos** aunque una petición abra una segunda sesión (a diferencia de reducir el pool). Configurable con `DB_MAX_CONCURRENT_CALLS` (0 lo desactiva).

**Elección del valor** (misma mezcla, HTTP, 8 y 32 clientes, `compose.rendimiento.yaml` con `PERF_GATE`):

| `DB_MAX_CONCURRENT_CALLS` | 8 clientes req/s · p95 | 32 clientes req/s · p95 |
|---|---|---|
| 0 (sin tope) | 4,5 · 7 581 ms | 3,5 · 18 619 ms |
| 4 | 8,4 · 3 399 ms | 7,7 · 7 539 ms |
| 3 | 17,3 · 1 403 ms | 17,9 · 3 304 ms |
| **2 (por defecto)** | **27,9 · 804 ms** | **27,4 · 1 943 ms** |

Con un cliente no cambia nada (20,3 → 20,2 req/s; latencias secuenciales idénticas en los 9 endpoints, ver §8).

**Límites del hallazgo.** Se reprodujo en Docker Desktop (WSL2) con el driver `msodbcsql18` 18.7; **la causa dentro del driver no se identificó** y puede depender del entorno: en un servidor Linux real el óptimo podría ser otro. Por eso el valor es configurable y el procedimiento de re-medición queda documentado (§10). Con un tope de 2, dos consultas lentas simultáneas retrasan al resto; hoy la más lenta tarda 16 ms.

### 3.2 Compilación del frontend (3 min 20 s) — no resuelto

`vite build` tarda ~215 s (Windows) y ~205 s (Docker, Linux): **igual antes y después** de los cambios. Con `--cpu-prof`, el 75 % del tiempo es la fase de «include» del tree-shaking de Rollup (`trackEntityAtPathAndGetIfTrack`, `includeCallArgumentsWhenCalled`); entre `buildStart` y `buildEnd` pasan 215 s y el minificado dura menos de 1 s. Sin tree-shaking (diagnóstico) la compilación tarda 5 s.

Hipótesis **descartadas con una compilación medida cada una**: el barril de `lucide-react` (se reescribieron los 126 íconos a importaciones directas: 1 862 → 422 módulos y el tiempo no mejoró; el plugin se retiró), el archivo de consejos de 52 KB, `propertyReadSideEffects`/`unknownGlobalSideEffects` en `false`, `preset: 'smallest'`, `tryCatchDeoptimization: false`, declarar React como sin efectos secundarios, y quitar `ErrorBoundary`, `OriginGuard`, `StrictMode` o los CSS del punto de entrada. Compilar cada grupo de pantallas por separado con `import * as` tarda 1–3 s: el costo aparece al **dibujar** `<App/>`. Queda como pendiente con esta evidencia.

### 3.3 Bundles y dependencias

Dependencias de ejecución del frontend: 5 (`react`, `react-dom`, `react-router-dom`, `lucide-react`, `qrcode.react`); del backend: las de `requirements.in`. **No se actualizó ni reemplazó ninguna**: no hay una medición que lo justifique (los costos medidos son de uso, no de versión). Tamaños en §5.

### 3.4 Servicios externos: correo

`sendEmailEvent` envía por SMTP **en línea** dentro de la petición HTTP, con 20 s de *timeout* (`integrations/email/sender.py`); solo el aviso de inicio de sesión y, desde ahora, el aviso de medición al grupo usan `sendEmailEventInBackground`. unas 40 llamadas en total (registro, invitaciones, alta de pacientes —hasta 2 correos seguidos—, traspasos…). Con SMTP real de Gmail (~1–2 s por envío) esas respuestas tardan lo que tarde el correo; con el servidor caído, hasta 20 s.

No se midió con un SMTP real (no se envía correo desde esta revisión) ni con uno simulado. **No se movió el resto a segundo plano** porque en la mayoría de los flujos el resultado del envío forma parte de lo que se audita (`notifications._send` registra éxito o fallo y «se puede reintentar»): cambiarlo exige decidir una cola de salida persistente (*outbox*). Queda en [PENDIENTES.md](PENDIENTES.md). El aviso al grupo sí se movió porque nadie espera su resultado.

### 3.5 Consultas SQL costosas

`medir_consultas.py`, base de 8,7 mil mediciones, p50 de 15 corridas:

| Operación | Sentencias SQL | Escrituras | Commits | Tiempo de base p50 ms | Total p50 ms |
|---|---|---|---|---|---|
| POST /auth/login (consumidor) | 7 → 7 | 4 → 4 | 3 → 3 | 7.8 → 5.6 | 219.7 → 171.1 |
| GET /measurements/profile | 3 → 3 | 0 → 0 | 0 → 0 | 1.7 → 1.3 | 11.0 → 8.4 |
| GET /measurements/evolution?dias=7 | 6 → 6 | 0 → 0 | 0 → 0 | 7.8 → 7.9 | 22.0 → 22.2 |
| GET /measurements/evolution?dias=90 | 6 → 6 | 0 → 0 | 0 → 0 | 8.8 → 7.5 | 31.3 → 28.3 |
| GET /measurements/evolution?dias=30 | 6 → 6 | 0 → 0 | 0 → 0 | 8.0 → 6.3 | 24.1 → 19.8 |
| GET /measurements (historial, pág. 1) | 6 → 6 | 0 → 0 | 0 → 0 | 6.9 → 6.5 | 18.8 → 17.9 |
| GET /measurements/dashboard?dias=30 | 16 → 16 | 0 → 0 | 0 → 0 | 27.3 → 21.8 | 51.2 → 41.5 |
| GET /measurements/statistics?dias=30 | 4 → 4 | 0 → 0 | 0 → 0 | 3.7 → 2.5 | 15.8 → 11.1 |
| GET /institutions/{id}/patients (pág. 1, 20) | 6 → 6 | 0 → 0 | 0 → 0 | 5.5 → 5.5 | 18.2 → 18.3 |
| GET /institutions/{id}/patients?busqueda= | 6 → 6 | 0 → 0 | 0 → 0 | 8.1 → 7.5 | 22.5 → 19.2 |
| GET /institutions/{id}/patients/assignable-operators | 4 → 4 | 0 → 0 | 0 → 0 | 2.1 → 1.8 | 10.9 → 9.9 |
| GET /institutions/{id}/patients/{pid} | 9 → 9 | 2 → 2 | 1 → 1 | 7.8 → 6.9 | 26.8 → 23.6 |
| GET /institutions/{id}/patients/{pid}/measurements | 7 → 7 | 0 → 0 | 0 → 0 | 5.2 → 4.2 | 18.2 → 15.3 |
| GET /institutions/{id}/patients/{pid}/measurements/evolution | 7 → 7 | 0 → 0 | 0 → 0 | 7.6 → 7.3 | 20.8 → 19.7 |
| GET /institutions/{id}/patients/{pid}/dashboard | 19 → 19 | 2 → 2 | 1 → 1 | 19.8 → 16.5 | 47.8 → 40.3 |
| GET /institutions/{id}/dashboard | 31 → 31 | 0 → 0 | 0 → 0 | 68.6 → 64.6 | 157.1 → 132.5 |
| GET /institutions/{id}/operators/{op}/dashboard | 22 → 22 | 0 → 0 | 0 → 0 | 29.6 → 36.7 | 71.7 → 77.5 |
| GET /institutions/{id}/indicators | 9 → 9 | 0 → 0 | 0 → 0 | 21.5 → 20.2 | 60.6 → 55.3 |
| escritura: medición con 400 muestras en una tanda de 400 · iniciar | 10 → 10 | 3 → 3 | 1 → 1 | — | 30.7 → 29.9 |
| escritura: medición con 400 muestras en una tanda de 400 · muestras | 414 → 15 | 403 → 4 | 1 → 1 | — | 211.6 → 54.0 |
| escritura: medición con 400 muestras en una tanda de 400 · cerrar | 25 → 26 | 7 → 7 | 2 → 2 | — | 56.4 → 47.8 |
| escritura: medición con 400 muestras en lotes de 20 (puente) · iniciar | 10 → 10 | 3 → 3 | 1 → 1 | — | 24.5 → 22.9 |
| escritura: medición con 400 muestras en lotes de 20 (puente) · muestras | 642 → 262 | 422 → 42 | 20 → 20 | — | 712.5 → 479.6 |
| escritura: medición con 400 muestras en lotes de 20 (puente) · cerrar | 25 → 26 | 7 → 7 | 2 → 2 | — | 55.5 → 49.4 |

`cerrar` pasa de 25 a 26 sentencias porque el aviso al grupo ahora **ejecuta** su consulta (antes fallaba en la primera: ver «Defecto funcional» de la matriz). Las lecturas simples hacen 3–9 sentencias (2 de ellas son la sesión y el usuario de cada pedido autenticado). Los dashboards hacen 16–31, con `TOP 50 000` que trae las filas a Python: el de institución tarda 142 ms con **8,7 mil** mediciones y crece con los datos. La capa de compatibilidad de esquema (`schemaCompat`) ya guarda en memoria sus consultas al catálogo (positivas 10 min). `pool_pre_ping=True` agrega un viaje por conexión sacada del pool: se conserva porque da la reconexión por pedido documentada en [DESPLIEGUE.md](DESPLIEGUE.md) §5. **Pendiente:** llevar las agregaciones del dashboard a SQL (una consulta con `CASE`) con comparación fila a fila de los resultados.

## 4. Peticiones secuenciales y repetidas

- **Cada carga fría** hace `/auth/refresh` → `/auth/me` en cadena (el segundo necesita el *access token* del primero): inevitable sin cambiar el contrato de la API. El resto de cada pantalla sale en paralelo.
- **Solicitudes repetidas:** ninguna en ninguna de las 8 pantallas medidas (`repetidas: []` en `frontend_base.json` y `frontend_perf.json`).
- **`useHomeData`:** las dos series (90 días para «últimos valores» y la del gráfico) salen en paralelo, ya descartan respuestas viejas y no se repiten: **sin defecto**.
- **Pantallas de institución:** el *layout* pide la institución y recién después los hijos (cuota, reasignaciones, actividad, dispositivos, dashboard) salen en paralelo: dependencia real (permisos), no se tocó.
- **Carrera confirmada y corregida:** en `PatientsPage` y `MeasurementHistory` (y por el mismo patrón `DevicesInventory` y `TransfersPage`) escribir en el buscador, cambiar de filtro o de página más rápido que el servidor dejaba que **la respuesta lenta de la consulta anterior pisara a la nueva**. Se reprodujo con una prueba que **falla con el código anterior** y pasa con `useLatestRequest` ([`utils/useLatestRequest.js`](../frontend/src/utils/useLatestRequest.js)): solo la última consulta puede actualizar la pantalla, y se invalidan todas al desmontar. `AuditView`, `Evolution` y `useHomeData` ya tenían su propia guarda.
- **FastAPI:** solo hay 4 `async def` de negocio (`googleLogin`, `googleAuthorizationUrl`, `googleCallback`, `contact`); usan `authlib` asíncrono o `run_in_threadpool`. El resto son `def`, que Starlette ejecuta en el *threadpool*: es lo correcto con SQLAlchemy/pyodbc síncronos. **No se convirtió nada a `async`.**

## 5. Frontend: carga inicial, JS y estrategia de chunks

Mediana de 5 corridas; «fría» = caché del navegador desactivada, «caché» = recarga con los recursos con hash ya descargados; «3g» = «Fast 3G» de DevTools (1,6 Mbps, 150 ms) con CPU 4× más lenta. `A → B` = antes → después. JS inicial = bytes transferidos (gzip) de todos los `.js` de la carga.

| Pantalla | Red / caché | JS inicial (KB gzip) | FCP ms | LCP ms | TBT ms | CLS | Carga ms | Solicitudes (API) |
|---|---|---|---|---|---|---|---|---|
| landing | rapida · fría | 297 → 124 | 168 → 139 | 168 → 139 | 28 → 23 | 0 → 0 | 53 → 31 | 3 (0) → 6 (0) |
| login | rapida · fría | 297 → 154 | 118 → 94 | 118 → 94 | 0 → 0 | 0 → 0 | 57 → 33 | 3 (0) → 15 (0) |
| privacidad | rapida · fría | 297 → 124 | 128 → 96 | 128 → 96 | 0 → 0 | 0 → 0 | 57 → 30 | 3 (0) → 6 (0) |
| inicio-individual | rapida · fría | 297 → 154 | 76 → 55 | 198 → 177 | 0 → 0 | 0.02 → 0.02 | 55 → 49 | 7 (4) → 19 (4) |
| inicio-individual | rapida · caché | 0 → 0 | 68 → 57 | 185 → 180 | 0 → 0 | 0.02 → 0.02 | 48 → 47 | 7 (4) → 19 (4) |
| historial | rapida · fría | 297 → 196 | 72 → 61 | 160 → 136 | 0 → 0 | 0.033 → 0 | 54 → 38 | 7 (3) → 33 (3) |
| historial | rapida · caché | 0 → 0 | 77 → 54 | 169 → 127 | 0 → 0 | 0.033 → 0 | 50 → 33 | 7 (3) → 33 (3) |
| pacientes | rapida · fría | 297 → 137 | 76 → 54 | 214 → 165 | 0 → 0 | 0.058 → 0.039 | 54 → 52 | 9 (5) → 20 (5) |
| pacientes | rapida · caché | 0 → 0 | 67 → 52 | 185 → 181 | 0 → 0 | 0.039 → 0.039 | 48 → 42 | 9 (5) → 20 (5) |
| dashboard-institucion | rapida · fría | 297 → 164 | 78 → 58 | 207 → 170 | 2 → 0 | 0.008 → 0.008 | 55 → 57 | 12 (8) → 31 (8) |
| dashboard-institucion | rapida · caché | 0 → 0 | 70 → 50 | 180 → 165 | 3 → 0 | 0.008 → 0.008 | 48 → 50 | 12 (8) → 31 (8) |
| dashboard-operador | rapida · fría | 297 → 155 | 75 → 58 | 168 → 163 | 0 → 0 | 0.097 → 0.097 | 52 → 57 | 9 (5) → 24 (5) |
| dashboard-operador | rapida · caché | 0 → 0 | 66 → 52 | 172 → 148 | 0 → 0 | 0.097 → 0.097 | 48 → 44 | 9 (5) → 24 (5) |
| landing | 3g · fría | 297 → 124 | 2776 → 1702 | 2776 → 1702 | 578 → 443 | 0 → 0 | 2155 → 1163 | 3 (0) → 6 (0) |
| login | 3g · fría | 297 → 154 | 2482 → 1419 | 2482 → 1419 | 252 → 151 | 0 → 0 | 2173 → 1147 | 3 (0) → 15 (0) |
| privacidad | 3g · fría | 297 → 124 | 2488 → 1461 | 2488 → 1461 | 286 → 214 | 0 → 0 | 2147 → 1142 | 3 (0) → 6 (0) |
| inicio-individual | 3g · fría | 297 → 154 | 2241 → 1262 | 3069 → 2116 | 449 → 281 | 0.02 → 0.02 | 2146 → 1516 | 7 (4) → 19 (4) |
| inicio-individual | 3g · caché | 0 → 0 | 468 → 435 | 1256 → 1221 | 438 → 348 | 0.02 → 0.02 | 364 → 393 | 7 (4) → 19 (4) |
| historial | 3g · fría | 297 → 196 | 2274 → 1267 | 2850 → 2378 | 178 → 193 | 0.033 → 0 | 2168 → 1177 | 7 (3) → 33 (3) |
| historial | 3g · caché | 0 → 0 | 440 → 422 | 1038 → 982 | 180 → 120 | 0.033 → 0 | 346 → 314 | 7 (3) → 33 (3) |
| pacientes | 3g · fría | 297 → 137 | 2243 → 1258 | 3167 → 2266 | 143 → 75 | 0.058 → 0.13 | 2148 → 1392 | 9 (5) → 20 (5) |
| pacientes | 3g · caché | 0 → 0 | 439 → 402 | 1348 → 1263 | 133 → 71 | 0.058 → 0.13 | 341 → 364 | 9 (5) → 20 (5) |
| dashboard-institucion | 3g · fría | 297 → 164 | 2240 → 1266 | 3147 → 2457 | 1938 → 1159 | 0.008 → 0.008 | 2146 → 1559 | 12 (8) → 31 (8) |
| dashboard-institucion | 3g · caché | 0 → 0 | 433 → 416 | 1287 → 1228 | 1209 → 1051 | 0.008 → 0.008 | 341 → 379 | 12 (8) → 31 (8) |
| dashboard-operador | 3g · fría | 297 → 155 | 2247 → 1278 | 3053 → 2302 | 258 → 143 | 0.097 → 0.097 | 2149 → 1394 | 9 (5) → 24 (5) |
| dashboard-operador | 3g · caché | 0 → 0 | 431 → 434 | 1208 → 1180 | 155 → 112 | 0.097 → 0.097 | 339 → 391 | 9 (5) → 24 (5) |

Qué se hizo y por qué (cada paso medido):

1. **Carga diferida de las pantallas** (`App.jsx`): el JS inicial pasó de 888 kB (297 KB transferidos) a 124 KB transferidos en la portada y en `/privacidad`, 137 KB en `/pacientes`, 154 KB en el inicio, 164 KB en el dashboard de institución y 196 KB en el historial (esa pantalla arrastra los módulos del dispositivo). La política de privacidad (13 KB) y las pantallas de acceso (login, registro, recuperación, verificación) quedan en el inicial a propósito.
2. **Primera versión (descartada):** la carga diferida sin más **empeoraba el LCP en red rápida** de 198 a 442 ms (y una pantalla pedía hasta 42 archivos, evidencia en `resultados/frontend_iter1_parcial.txt`). Dos causas, ambas medidas: el módulo de la pantalla recién se pedía cuando React la dibujaba (tras `/auth/refresh` y `/auth/me`), y un `Suspense` que muestra su *fallback* mantiene el contenido oculto ~300 ms (regla de React 19) aunque el módulo ya esté.
3. **Corrección:** `preloadForPath` (`main.jsx`) descarga la pantalla de la ruta de entrada en paralelo con la recuperación de la sesión, y `lazyNamed` dibuja **sin suspender** un componente ya descargado. Con eso el LCP en red rápida volvió a ser igual o mejor que antes. En el login se precarga además el inicio (con el navegador ocioso y sin «ahorro de datos»).
4. **React, el router y los íconos en archivos aparte** (`manualChunks`): React y el router casi no cambian entre versiones, así que el navegador los conserva en caché aunque cambie el código (no se midió en visitas repetidas); los íconos de `lucide-react` compartidos entre pantallas diferidas eran **un archivo de ~400 B cada uno** (una pantalla pedía 25 o más): agrupados en uno, el historial bajó de 50 a 33 solicitudes y el inicio de 27 a 19.
5. **`experimentalMinChunkSize`** para juntar fragmentos chicos: 40 kB y 100 kB dan **los mismos 94 archivos**; no tiene efecto aquí y se quitó.

**Trade-off a la vista:** a cambio de bajar el JS inicial, cada pantalla hace más solicitudes (el inicio individual pasa de 7 a 19; el historial de 7 a 33; el dashboard de institución de 12 a 31). El puerto 8080 de Nginx habla HTTP/1.1 (HTTP/2 lo da el proxy Caddy de producción), que limita a 6 conexiones simultáneas; aun así todas las cargas **en frío** mejoran en FCP y LCP, y con caché en 3G el LCP queda igual o mejor en las cinco pantallas autenticadas (la excepción es el TBT de `/historial` en frío en 3G, 178 → 193 ms). No se reordenaron más los chunks por falta de una mejora medible.

## 6. Experiencia de carga: esqueleto, progresivo, optimista y revalidación

| Técnica | Estado | Detalle |
|---|---|---|
| **Skeleton** | Aplicado | `components/Skeleton.jsx`: `PageSkeleton` en el `Suspense` del contenido (el menú y la barra siguen visibles; antes, una pantalla completa con un spinner) y `SkeletonList` en pacientes e historial (antes, «Cargando…» suelto). Anuncian el mismo texto a lectores de pantalla; respetan `prefers-reduced-motion`. |
| **Carga progresiva** | Ya existía | El inicio muestra primero las tarjetas y carga el gráfico aparte («Cargando tus mediciones…»); en el dashboard de institución cada sección pide sus datos por separado (8 solicitudes en paralelo). En las 8 pantallas medidas no se vio ninguna que se quedara en blanco; no se revisaron una por una las demás. |
| **Revalidación y caché de datos** | No aplicado | No hay caché de respuestas de la API (cada pantalla vuelve a pedir). Para datos de salud, permisos y auditoría se prefiere el dato fresco; introducir una caché (SWR) sin una necesidad medida añade riesgo de mostrar datos viejos. No hay solicitudes repetidas que justificarla. |
| **Optimistic UI** | **No aplicado, a propósito** | Las acciones del producto son mediciones de salud, permisos y compartición de datos, autenticación, eliminación de cuentas y decisiones sobre pacientes: justo lo que no debe reflejarse antes de la confirmación del servidor, y no hay una acción menor con reversión confiable que valga la complejidad. |

CLS: igual o mejor en 11 de 12 combinaciones. **Excepción:** `/pacientes` en 3G con CPU 4× mide 0,13 (0,058 antes). El valor **no es estable entre corridas** (0 / 0,039 / 0,13 en corridas repetidas; 4 de 5 con 0,13 en la corrida documentada) y no se pudo reproducir con `cls_fuentes.mjs` ni identificar su origen: queda anotado como pendiente.

## 7. ¿Se sirve estático? Nginx, caché y SEO

**Confirmado:** producción sirve `dist/` compilado con Nginx (`frontend/Dockerfile`: etapa `build` → Nginx sin privilegios); no hay servidor de Node ni SSR. Las áreas autenticadas siguen siendo la SPA dinámica.

| Revisión | Antes | Después |
|---|---|---|
| `index.html` y rutas de la SPA | `Cache-Control: no-cache` + `ETag` ✔ | igual |
| Assets con hash (`/assets/`) | `Expires` +1 año, `Cache-Control: max-age=31536000` ✔ | igual (`immutable` exigiría repetir las cabeceras de seguridad en la ubicación: no se justifica) |
| Compresión | gzip nivel 1 al vuelo (JS 303 KB, CSS 41 KB); **sin `Vary: Accept-Encoding`** | **gzip -9 precomprimido en el build** y servido con `gzip_static` (JS 254 KB, CSS 28,8 KB); `Vary` activo; nivel 5 para API e `index.html` |
| `/robots.txt`, `/sitemap.xml` | **200 con el HTML de la SPA** («soft 404») | `robots.txt` real (`Disallow` de `/app/`, `/plataforma/`, `/administracion/`, `/api/`); `sitemap.xml` y cualquier archivo inexistente → **404** |
| Páginas privadas en buscadores | sin señal | `X-Robots-Tag: noindex, nofollow` en `/app`, `/plataforma`, `/administracion`, `/login`, `/registro`, etc. |
| Metadatos | solo `description` y `title` | + `theme-color`, Open Graph y `twitter:card` |

**Prerenderizado de la portada: no se justifica.** Con la carga diferida, la portada carga 124 KB y tiene FCP/LCP de 139 ms (red rápida) y 1 702 ms («Fast 3G», CPU 4× más lenta), TBT 443 ms. Prerenderizar exigiría un paso de compilación con un navegador o `react-dom/server`, hidratación y revisar la CSP sin `unsafe-inline`, para ganar a lo sumo ~1 s en 3G en una sola página; la mejora de bytes ya se consiguió (FCP en 3G: 2 776 → 1 702 ms). No se migró a Next.js ni se implementó SSR. Si en el futuro el SEO de la portada importa, lo medible es el LCP en 3G (hoy 1,7 s) y la ausencia de `canonical`/`sitemap` (necesitan el dominio de producción, que no se conoce al compilar la imagen: misma imagen para cualquier dominio).

## 8. Backend: latencia, sentencias y escrituras

Por HTTP real contra la API (puerto 18000, sin Nginx), `antes → después`, medidos **uno tras otro en las mismas condiciones** (`http_final-baseline.json` y `http_final-perf.json`):

| Endpoint (secuencial, 100 pedidos) | p50 ms | p95 ms | p99 ms |
|---|---|---|---|
| evolution 7d | 17.7 → 18.8 | 24.4 → 25.7 | 26.9 → 30.6 |
| evolution 90d | 27.6 → 28.3 | 33.0 → 31.7 | 103.1 → 33.9 |
| historial pág.1 | 16.5 → 16.5 | 19.1 → 18.8 | 21.5 → 19.7 |
| dashboard personal | 42.4 → 43.1 | 47.6 → 47.6 | 56.4 → 48.9 |
| pacientes pág.1 | 16.7 → 16.5 | 19.6 → 20.8 | 20.0 → 23.5 |
| operadores asignables | 8.7 → 9.0 | 10.9 → 10.6 | 11.7 → 12.1 |
| dashboard institución | 141.6 → 142.4 | 211.1 → 227.9 | 225.9 → 238.4 |
| dashboard operador | 72.7 → 74.1 | 84.1 → 88.3 | 98.7 → 93.1 |
| indicadores institución | 57.5 → 57.6 | 63.9 → 77.0 | 144.8 → 148.3 |

| Clientes simultáneos (mezcla de 5 endpoints, 15 s) | req/s | p50 ms | p95 ms | p99 ms |
|---|---|---|---|---|
| 1 | 20.3 → 20.2 | 18.9 → 18.7 | 146.4 → 147.0 | 167.6 → 192.4 |
| 8 | 4.4 → 28.2 | 530.0 → 174.5 | 7009.9 → 754.1 | 8400.8 → 878.0 |
| 32 | 3.5 → 26.1 | 5102.0 → 1028.0 | 18316.6 → 2084.9 | 22654.5 → 2282.2 |

| Ingesta de muestras (400 por medición) | ms por solicitud p50 | p95 | ms por medición p50 | errores |
|---|---|---|---|---|
| 1 en paralelo, lotes de 20 | 29.1 → 23.5 | 34.6 → 29.1 | 598.8 → 474.5 | 0 → 0 |
| 1 en paralelo, lotes de 200 | 90.2 → 37.8 | 98.3 → 65.5 | 181.3 → 77.3 | 0 → 0 |
| 8 en paralelo, lotes de 20 | 411.2 → 163.0 | 527.9 → 204.4 | 8584.2 → 3290.2 | 0 → 0 |
| 16 en paralelo, lotes de 20 | 883.7 → 329.4 | 1083.7 → 432.3 | 17842.3 → 6596.2 | 0 → 6 |

Con un solo cliente las latencias son las mismas (diferencias dentro del ruido de ±1–2 ms; el tope no agrega costo medible). El tiempo de base es una fracción de la latencia total (p. ej. 7 ms de 18 ms en la evolución a 7 días): el resto es serialización, validación y autenticación en Python.

### 8.1 Escrituras de muestras del sensor

`addSamples` creaba un objeto ORM por muestra y SQLAlchemy ejecutaba **un `INSERT` por fila** porque la clave primaria la genera el servidor (`newsequentialid()`, que se conserva a propósito para no fragmentar el índice agrupado) y así no puede agrupar ni pedir las claves en lote. Ahora cada tanda de hasta 400 muestras es **un `INSERT` de varias filas** (5 parámetros × 400 = 2 000, bajo el tope de 2 100 de SQL Server), en la **misma transacción**: atomicidad, `UQ_MuestraSensor_orden`, permisos y auditoría iguales. Una muestra repetida revierte toda la tanda (prueba nueva). El puente real envía lotes de 20–200 muestras; el resto del costo por lote (13 sentencias de comprobación de acceso, estado, consentimiento y armado de la respuesta) no se tocó.

### 8.2 Otras escrituras revisadas

- **Login:** 7 sentencias, 4 escrituras y 3 *commit* (sesión, auditoría, contexto): cada uno es una decisión de seguridad/auditoría; no se agrupó.
- **`GET /patients/{id}`** escribe 2 filas de auditoría (acceso a datos de un paciente) en un `GET`: deliberado.
- **`invalidateStale`** (mantenimiento cada 60 s) hace un `commit` por medición vencida a propósito: una falla no frena al resto ni deja la sesión sucia; los volúmenes son chicos.
- **Reasignaciones:** un solo `commit` por lote; las notificaciones por correo son por paciente (ver §3.4).

## 9. Qué no se pudo medir o queda con reservas

- **INP:** no hay guion de interacción estable; se informa TBT. En 3G con CPU 4× más lenta el TBT del dashboard de institución bajó de 1,9 s a 1,2 s con la carga diferida, y sigue siendo alto (render pesado de gráficos): oportunidad de mejora no abordada.
- **Servidor real / otro hardware:** todo se midió en una máquina de desarrollo con Docker Desktop. El óptimo de `DB_MAX_CONCURRENT_CALLS` y la causa del hallazgo §3.1 pueden variar.
- **Correo real, Redis, HTTPS/HTTP/2 y Caddy:** no medidos (§3.4, §3.5, §5).
- **Tiempo de compilación:** sin causa raíz resuelta (§3.2).
- **Pruebas sobre SQL Server:** ver §11.
- Las mediciones con carga de 16/32 clientes alcanzan el límite por IP de endpoints con sesión (1 800 pedidos/min, H-11); en esas pruebas aparecen unos pocos `429` que **no son fallos**.

## 10. Cómo reproducir

Instrucciones y scripts en [evidencias/rendimiento/README.md](evidencias/rendimiento/README.md) (crear la base descartable, sembrar datos, levantar el stack con `PERF_TAG=baseline|perf`, `medir_consultas.py`, `medir_http.py`, `medir_frontend.mjs`, `comparar.py`, y los microbenchmarks de hilos).

## 11. Resultados de las pruebas

| Suite | Antes (`master`) | Después (rama) |
|---|---|---|
| Backend, `python -m pytest` (SQLite) | 1 903 pasaron, 80 omitidas, 0 fallaron | — |
| Backend **con las pruebas `*_sqlserver` activadas** contra un SQL Server 2022 CU16 descartable (`TEST_SQLSERVER_URL`, `TEST_SQLSERVER_CONFIRM=DESCARTABLE`) | no corrida sobre `master` en esta sesión | **1 980 pasaron, 13 omitidas, 0 fallaron.** Las 13 omitidas necesitan `gcc`, `redis-server` y `dpkg`/`zlib1g`, que Windows no tiene (la corrida del 23/10 en Linux: 1 983 sin omitidas) |
| Frontend, `npm test` | 693 de 695 (2 fallas **previas**: la guarda del refresh token comparaba rutas con `/` y Windows usa `\`) | **700 de 700** |
| Pruebas nuevas | — | `test_db_gate.py` (7), `test_mssql_boolean_comparisons.py` (1), 2 de inserción por tandas en `test_measurements.py`, `useLatestRequest.test.jsx` (3) y 2 de carrera (pacientes e historial; **fallan con el código anterior**, comprobado) |

La integración con SQL Server real encontró dos pruebas de `test_security_config.py` que reemplazan `create_engine` por un objeto cualquiera y rompían con el tope de llamadas (corregido: el tope ignora lo que no es un `Engine`).

**Integración y regresión:** `medir_consultas.py` recorre la API completa (login, perfil, evolución, historial, dashboards, pacientes, institución y el flujo de una medición con 400 muestras) contra SQL Server real sin errores
(los dos únicos no-200 son del propio script: un `405` por una ruta que no existe y un `403` por usar un operador sin acceso al paciente). `medir_http.py` con 32 clientes simultáneos: 0 errores (salvo `429` del límite por IP cuando 16 mediciones en paralelo superan
30 pedidos/s). Playwright cargó las 8 pantallas con sesión real y no registró ninguna solicitud de la API con error (`noOk: []`).

**No ejecutado en esta revisión:** la validación integral de `evidencias/validacion_integral` (cuentas restringidas, Redis, Caddy) y `python -m tests.lifecycle_concurrency`: no se tocó nada que las afecte, pero tampoco se repitieron.
