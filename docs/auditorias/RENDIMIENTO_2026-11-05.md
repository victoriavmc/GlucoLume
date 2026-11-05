# Auditoría integral de rendimiento de GlucoLume — 5 de noviembre de 2026

> **Estado:** diagnóstico completo en laboratorio. **No se implementó ninguna corrección**, no se modificó código funcional, base de datos, Docker ni configuración de servidor, y no se enviaron correos reales.
> **Exposición:** miércoles 11 de noviembre de 2026. Todas las soluciones quedan **pendientes de autorización expresa**.

---

## 1. Identificación del estado auditado

| Dato | Valor |
|---|---|
| Repositorio | `victoriavmc/GlucoLume` (GitHub) |
| Rama auditada | `claude/amazing-clarke-p75731` |
| Commit SHA auditado | `933d84c67834a6515a1ff161518b202420f3a664` |
| Fecha del commit | 5/11/2026 17:17:49 +0000 — «Las señales ya analizadas se ocultan del panel de seguridad» |
| Fecha de revisión | 5/11/2026 |
| Árbol de trabajo al inicio | limpio |
| Historial de la rama | 52 commits |

**Tratamiento de la documentación anterior.** `docs/RENDIMIENTO.md`, `docs/PENDIENTES.md`, `PR_rendimiento.md` y `docs/evidencias/rendimiento*` se leyeron **solo como historial**. Sus métricas, prioridades y pendientes no se reutilizan. Algunas de sus afirmaciones se verificaron de nuevo contra el código vigente (§6.3). Cada hallazgo se basa en código, esquema, archivos o mediciones de esta auditoría.

---

## 2. Alcance y metodología

### 2.1 Alcance

- **Frontend (React 19 + Vite 6):** pantalla de Ayuda (caso obligatorio A), cambio de pestañas, desplazamiento, visor de capturas, bundles, carga por ruta, polling y memoria.
- **Backend (FastAPI + SQLAlchemy):** flujos de correo (caso obligatorio B), endpoints síncronos y asíncronos, operaciones de CPU (hash de contraseñas), streams SSE y tope de llamadas al driver.
- **SQL Server:** esquema de referencia v5 y scripts de actualización (índices, FK) y consultas costosas, por lectura de código.
- **Infraestructura:** `compose.yaml`, `compose.prod.yaml`, Dockerfile de backend y frontend, plantilla de Nginx.
- **Integraciones:** SMTP (envío, latencia y tamaño del mensaje) y Google OAuth (lectura de código).

### 2.2 Entorno de medición (laboratorio; no es el servidor de producción)

| Recurso | Valor |
|---|---|
| Host | contenedor de laboratorio, 4 vCPU, 16 GB RAM, compartido con el navegador |
| Navegador | Chromium + Playwright sobre Node 22.23.4 |
| Frontend | build de producción propio (`vite build`, `VITE_API_BASE_URL=/`) servido en `localhost` con compresión |
| Backend (micro-mediciones) | Python 3.13 local con el `requirements.txt` fijado por hashes |
| Base de datos | **no disponible**: sin SQL Server y sin daemon de Docker |
| SMTP | **ningún servidor real.** Sumidero local aiosmtpd con STARTTLS y certificado de prueba; latencia y ancho de banda simulados por proxy TCP |

### 2.3 Restricciones respetadas

- No se accedió al servidor HP ni a su base; no hubo cargas contra producción.
- No se enviaron correos reales. Las credenciales de `_env.py` son valores ficticios (`lab-no-real`).
- Solo se agregaron archivos bajo `docs/auditorias/`.

### 2.4 Clasificación de resultados

- **CONFIRMADO POR MEDICIÓN:** obtenido con una medición reproducible (ver `docs/auditorias/evidencias/rendimiento_2026-11-05/`).
- **CONFIRMADO POR CÓDIGO:** está en el código o el esquema; el costo real no se midió.
- **HIPÓTESIS NO VERIFICADA:** plausible según el código; falta evidencia.
- **NO EVALUADO:** no fue posible medirlo en este entorno.

### 2.5 Metodología de mediciones de navegador

- Perfil **escritorio**: 1366×768, DPR 1, sin limitación.
- Perfil **móvil simulado**: 390×844, DPR 2, CPU ×4 y red «Fast 3G» de Chrome DevTools (1,6 Mbps de bajada, 750 kbps de subida, RTT 562,5 ms).
- Cada condición: **n = 10 corridas**, caché fría (contexto nuevo) y un navegador nuevo por corrida. Se reportan p50 y p95.
- Controles de causa: **base** (PNG originales), **sinImagenes** (`/ayuda/*.png` abortados) y **webp840** (capturas >840 px reducidas y recodificadas a WebP calidad 85, como cota superior de optimización de imágenes).
- Las respuestas de sesión de la API se interceptan con un 401 inmediato, porque no hay backend en el laboratorio.

---

## 3. Matriz de hallazgos priorizados

Prioridad: **P1** = bloquea al usuario o pone en riesgo la disponibilidad; **P2** = degrada la experiencia o escala mal; **P3** = mejora menor o depende del volumen.

| ID | Área | Ubicación | Hallazgo | Clasificación | Prioridad |
|---|---|---|---|---|---|
| H-01 | Ayuda | `GuiaVisual.jsx` (`PasoImagen`), `frontend/public/ayuda/` | Las miniaturas usan el PNG a resolución completa (hasta 1315 px) mostrado a ≤ 420 px. Se piden 22 PNG (1,59 MB) en escritorio y 11 (0,70 MB) en móvil al abrir. Decodificado estimado: 52 MB en escritorio, 50 MB en móvil. **Las imágenes no cambian FCP ni LCP** en ningún perfil. Sí causan tareas largas al cambiar de pestaña en móvil (ver H-25). | CONFIRMADO POR MEDICIÓN | P3 |
| H-02 | Ayuda / Nginx | `docker/nginx/default.conf.template` (bloque regex de estáticos) | Los PNG de `/ayuda/` no tienen `Cache-Control` ni `expires`; solo `/assets/` tiene 1 año. Cada visita revalida las capturas. | CONFIRMADO POR CÓDIGO (Nginx real no disponible para medir) | P3 |
| H-03 | Ayuda | `helpContent.js` + `HelpPage` | Chunk de Ayuda de 65,9 kB (19,2 kB gzip) con todo el texto de la guía. Se descarga solo al visitar la ruta. | CONFIRMADO POR MEDICIÓN (build) | P3 |
| H-04 | Ayuda (lentitud percibida) | `App.jsx` (`PRELOADS`), `index.html` | **La cadena de carga de `/ayuda` es secuencial:** HTML → `index.js` → chunk `HelpPage` (que no está precargado ni tiene `modulepreload`). En móvil simulado, el chunk de la ruta termina a 2829 ms, y el LCP queda en 3,1 s. Se transfieren ~157 KB antes del FCP: el costo es de latencia encadenada, no de bytes. | CONFIRMADO POR MEDICIÓN (waterfall) y por código | **P2** |
| H-05 | Ayuda (CPU) | `HelpPage.jsx` (cambio de pestaña) | El cambio de pestaña re-renderiza el contenido completo de la pestaña (1235 nodos). En móvil simulado tarda 160–170 ms (p50) y tiene tareas largas de hasta 144 ms (p95). En escritorio, ~37 ms. | CONFIRMADO POR MEDICIÓN | P3 |
| H-06 | Correo | `services/auth.py` (`registerLocal` → `_sendVerificationEmail`; `resendVerification`) | El alta de cuenta y el reenvío de verificación esperan el SMTP completo dentro de la petición. | CONFIRMADO POR CÓDIGO; costo: §4.4 | P1 |
| H-07 | Correo | `services/contact.py` (`sendContactMessage`, `_sendConfirmation`) | El formulario de contacto envía **dos correos en serie** dentro de la petición (aviso a GlucoLume y confirmación), cada uno con su sesión SMTP completa. | CONFIRMADO POR CÓDIGO y medición del envío (§4.4) | P1 |
| H-08 | Correo | `mfaRecovery.py:164`, `accountDeletion.py:249`, `passwordChangeCode.py:103`, `platform.py:200/479`, `resultEmailConfirmation.py:60` | Otros flujos también envían de forma síncrona: código MFA de recuperación, solicitud de eliminación de cuenta, código de cambio de contraseña, invitación y restablecimiento de administradores, confirmación de resultados. | CONFIRMADO POR CÓDIGO | P1 |
| H-09 | Correo | `integrations/email/sender.py` (`buildHtmlMessage`), `emails/bannerCorreoGlucoLume.png` | **Cada correo adjunta un banner de 1,35 MB** como imagen embebida. El mensaje MIME pesa **1,83 MB** (medido), frente a 7 KB sin banner. El banner es ~99,6 % del mensaje. | CONFIRMADO POR MEDICIÓN (tamaño) | P1 |
| H-10 | Correo | `integrations/email/sender.py` (`_send`) | Una conexión SMTP nueva por correo: **9 comandos SMTP** por envío (EHLO, STARTTLS, EHLO, AUTH, MAIL, RCPT, DATA, cuerpo, QUIT), sin reutilización. | CONFIRMADO POR MEDICIÓN (conteo de comandos, sumidero local) | P2 |
| H-11 | Correo | `services/email.py` (`_executor = ThreadPoolExecutor(max_workers=2)`) | Pool de 2 hilos con cola **sin límite** y sin persistencia: si el proceso se reinicia, la cola se pierde. Sin métrica de profundidad. | CONFIRMADO POR CÓDIGO | P2 |
| H-12 | Correo | `services/institution.py:1424` (cierre), `services/platformInstitutions.py:94` | Bucles que encolan un correo por destinatario. Con 2 hilos y ~8 s por envío a 2 Mbps (§4.4), 50 miembros tardan ~200 s en salir. | CONFIRMADO POR CÓDIGO; tiempo por envío: §4.4 | P2 |
| H-13 | SQL Server | `GlucoLume_DB_v5.sql` (tabla `Medicion`), `services/measurement.py:_history` | `Medicion` tiene la FK `FK_Medicion_Perfil` pero **ningún índice que empiece por `idPerfilMedicion`**. El historial, la analítica de pacientes y los datos de grupo filtran por esa columna. | CONFIRMADO POR CÓDIGO (esquema); plan: NO EVALUADO | P1 |
| H-14 | Concurrencia | `db/gate.py`, `core/config.py` (`DB_MAX_CONCURRENT_CALLS = 2`) | Cada proceso ejecuta como máximo 2 llamadas simultáneas al driver. Con dos consultas lentas simultáneas, el p95 de las rápidas sube de 14,6 a 73 ms (y las que llegan durante la ocupación esperan ~1,2 s). En SQLite, el tope reduce el throughput de 125 a 62 consultas/s. | CONFIRMADO POR MEDICIÓN (simulación con el código real; no es SQL Server) | P1 |
| H-15 | CPU / memoria | `core/security.py` (Argon2id `m=64 MiB, t=3, p=4`), `services/auth.py` (`_passwordReuseError`) | Cada verificación cuesta ~55 ms de CPU y ~55 MB de RSS. **8 verificaciones simultáneas llegan a 555 MB de RSS**, por encima del límite de 512 MB del backend en `compose.yaml`. Un cambio de contraseña ejecuta 5 operaciones Argon2 (264 ms p50). | CONFIRMADO POR MEDICIÓN (proceso de laboratorio con pwdlib) | P1 |
| H-16 | Concurrencia / infraestructura | `compose.yaml` (`backend`: `cpus 1.0`, `memory 512M`), `Dockerfile` (un proceso Uvicorn, sin `--workers`) | Un único proceso y límites ajustados. En producción el backend sube a 2 CPU y 1 GB (`compose.prod.yaml`). | CONFIRMADO POR CÓDIGO | P2 |
| H-17 | Infraestructura | `compose.yaml` (`db`: `MSSQL_PID` por defecto `Express`) | La edición Express limita memoria del buffer pool y núcleos; el valor es configurable y la edición instalada en el servidor no se verificó. | HIPÓTESIS NO VERIFICADA | P2 |
| H-18 | Dashboard institucional | `services/dashboard.py` (~l. 655–700) | Más de 10 consultas que repiten la subconsulta `performedAll` (join con `Auditoria` filtrada por `idRelacionado`, columna sin índice). | CONFIRMADO POR CÓDIGO; plan: NO EVALUADO | P2 |
| H-19 | Backend (N+1) | `services/measurement.py:_history` → `_semaphoreOf` → `glucoseReference.build` | Por cada medición completada de glucosa en la página se hacen 2 consultas adicionales (reglas de matriz y `ruleIdOf`). | CONFIRMADO POR CÓDIGO | P2 |
| H-20 | Streams SSE | `api/v1/acquisition.py:stream`, `api/v1/telemetry.py:telemetryStream`, `api/streams.py` | Cada stream despierta cada 0,2 s en el event loop único; tope de 300 streams globales. Hasta 1500 despertares/s en el peor caso. | CONFIRMADO POR CÓDIGO; costo: HIPÓTESIS (§4.7) | P3 |
| H-21 | Paginación | `services/auditQuery.py:924`, `services/measurement.py:699`, `services/institutionPatients.py:334` | `OFFSET` en tablas que crecen; el costo de cada página crece con la profundidad. | CONFIRMADO POR CÓDIGO | P3 |
| H-22 | Búsqueda | `services/auditQuery.py:166`, `services/institutionPatients.py:305`, `services/device.py:288` | `ILIKE '%término%'` sobre varias columnas (no sargable). Acotado por institución y página. | HIPÓTESIS NO VERIFICADA (depende del volumen) | P3 |
| H-23 | Frontend polling | `MeasurementPanel.jsx` (3 s), `LiveAcquisition.jsx` (3 s), `useDeviceStatus.js` (5 s), `useDeviceReadiness.js` (5 s), `PersonalDashboard.jsx` (10 s), `useIncomingNotifications.js` (30 s), `MeasurementHistory.jsx` (60 s) | Polling por pestaña visible. Suma máxima ≈ 0,9 peticiones/s por pestaña. Pausa correcta de avisos con la pestaña oculta. | CONFIRMADO POR CÓDIGO; carga: §4.8 | P3 |
| H-24 | Frontend | toda la aplicación | No hay `React.memo` (0 usos). Las actualizaciones por polling re-renderizan el árbol de la pantalla. | HIPÓTESIS NO VERIFICADA | P3 |
| H-25 | Administración | `services/platformDashboard.py:systemStatus` | Cada carga del estado del sistema abre dos conexiones TCP (SMTP y Google), en paralelo y con timeout de 2 s, dentro de la petición. | CONFIRMADO POR CÓDIGO | P3 |
| H-26 | Integraciones | `integrations/google/oauth.py` | Google OAuth usa `authlib` asíncrono (no bloquea el loop), pero agrega llamadas HTTPS externas por inicio de sesión. | NO EVALUADO (sin acceso a Google) | P3 |

Notas de cambio respecto del borrador anterior: H-01 baja de P2 a P3 porque las imágenes no explican el tiempo de carga en ningún perfil. H-04 y H-05 son nuevos y explican la lentitud percibida en móvil. H-09, H-10 y H-14 pasan a medidos.

---

## 4. Resultados de mediciones y limitaciones

### 4.1 Pantalla Ayuda — escritorio (n = 10, p50 / p95)

| Métrica | Base | Sin imágenes | WebP ≤ 840 px |
|---|---|---|---|
| Apertura hasta primera figura (ms) | 466,5 / 476,8 | 465,0 / 474,1 | 482,0 / 516,2 |
| FCP (ms) | 102 / 122,2 | 104 / 112 | 104 / 114,2 |
| LCP (ms) | 452 / 472,4 | 460 / 474,2 | 462 / 488 |
| PNG pedidos al abrir (n) | 22 | 0 | 22 |
| Bytes PNG/WebP al abrir | 1 589 129 | 0 | 303 446 |
| Cambio de pestaña a Institucional (ms) | 36,8 / 44,1 | 42,8 / 57,5 | 45,3 / 61,7 |
| Cambio de pestaña a Cliente (ms) | 28,7 / 39,9 | 30,4 / 39,9 | 31,5 / 44,1 |
| Cuadro p95 al desplazar (ms) | 16,7 / 16,8 | 16,7 / 16,8 | 16,7 / 16,8 |
| Cuadros > 50 ms al desplazar (n) | 0 / 0,5 | 0 / 0,5 | 0 / 1,6 |
| Visor ampliado: abrir y decodificar (ms) | 25,5 / 31,0 | ver nota | 23,5 / 34,1 |
| Píxeles decodificados estimados (MB) | 51,8 | 0 | 36,8 |
| Nodos DOM al abrir | 1235 | 1235 | 1235 |

Nota: en «Sin imágenes» el visor no tiene captura que decodificar; el banco espera 15 s y registra que la imagen no cargó (`visorImgLoaded = false`). Ese tiempo no es un dato de rendimiento.

**Lectura.** En escritorio la pantalla no muestra bloqueo medible. Quitar las imágenes no cambia FCP, LCP, apertura ni cambio de pestaña. Las imágenes sí explican el costo de bytes y de memoria de decodificación.

### 4.2 Pantalla Ayuda — móvil simulado (n = 10, p50 / p95)

| Métrica | Base | Sin imágenes | WebP ≤ 840 px |
|---|---|---|---|
| Apertura hasta primera figura (ms) | 3116,5 / 3159,2 | 3147,5 / 3187,8 | 3144,5 / 3227,1 |
| FCP (ms) | 2178 / 2192,4 | 2184 / 2200,4 | 2166 / 2172 |
| LCP (ms) | 3098 / 3148,4 | 3110 / 3147,4 | 3074 / 3141,4 |
| PNG pedidos al abrir (n) | 11 | 0 | 11 |
| Bytes PNG/WebP al abrir | 703 969 | 0 | 136 054 |
| PNG pedidos durante el desplazamiento | 18 | 0 | 18 |
| Cambio de pestaña a Institucional (ms) | 171,7 / 213,4 | 162,0 / 198,8 | 169,1 / 198,3 |
| Tarea larga en el cambio de pestaña (ms, p95) | 143,7 | 59,9 | 118,5 |
| Cambio de pestaña a Cliente (ms) | 147,1 / 167,2 | 142,2 / 163,1 | 132,9 / 170,1 |
| Cuadro p95 al desplazar (ms) | 16,7 / 16,8 | 16,7 / 16,8 | 16,7 / 16,8 |
| Cuadros > 50 ms al desplazar (n) | 0 / 0,5 | 0 / 0 | 0 / 0 |
| Visor ampliado (ms) | 67,0 / 88,2 | ver nota §4.1 | 74,5 / 94,1 |
| Píxeles decodificados estimados (MB) | 49,9 | 0 | 35,2 |

**Lectura.**
1. **La apertura en móvil no depende de las imágenes.** Sin ninguna captura, el LCP sigue en ~3,1 s. El cuello de botella es la cadena de carga (H-04), que en el waterfall aparece así: HTML 628 ms → `index.js` 1919 ms → `HelpPage` 2829 ms; LCP 3112 ms.
2. **Las imágenes sí agregan tareas largas al cambiar de pestaña** en móvil: el p95 baja de 144 a 60 ms al quitarlas (≈ 84 ms atribuibles a las capturas). Con WebP ≤ 840 px baja solo a 119 ms: el costo restante es de render de React (H-05).
3. El desplazamiento se mantiene a 60 fps en móvil con los tres controles.

### 4.3 Waterfall de `/ayuda` en móvil simulado (una corrida)

Fuente: `docs/auditorias/evidencias/rendimiento_2026-11-05/waterfall_movil_salida.txt`.

| Recurso | Tiempo de fin (ms) | Transferido (kB) |
|---|---|---|
| `/ayuda` (HTML) | 628 | 1 |
| `icons-*.js` | 1536 | 14 |
| `router-*.js` | 1571 | 14 |
| `index-*.css` | 1714 | 24 |
| `index-*.js` (shell) | 1919 | 46 |
| `react-*.js` | 1982 | 58 |
| `PageHeader`, `Tabs`, `HelpPage-*.css` | 2721–2739 | 1 cada uno |
| **`HelpPage-*.js` (chunk de la ruta)** | **2829** | 19 |

Antes del FCP (2192 ms) se transfieren 6 requests y 157 kB. El resto del tiempo es latencia de red encadenada: cada etapa paga el RTT de 562 ms.

### 4.4 Correo: contenido, generación y envío real del código

**Tamaño del mensaje** (verificación de correo, misma plantilla):

| Variante | Bytes |
|---|---|
| Con banner embebido | 1 829 356 |
| Sin banner | 7 066 |

**Generación (sin enviar)**, 78 tipos de evento renderizados sin errores, 20 repeticiones por tipo:

| Etapa | p50 (mediana entre eventos) | Rango de p50 entre eventos |
|---|---|---|
| Renderizado de plantilla (Jinja + validación) | 0,86 ms | 0,8–1,0 ms |
| Construcción del MIME con banner | 8,9 ms | ~8–11 ms |
| Tamaño del mensaje | — | 1 827 243 – 1 831 846 bytes |

La generación es CPU despreciable. **El costo es de bytes.**

**Envío real del código (`integrations/email/sender._send`) contra el sumidero local**, con RTT y ancho de banda simulados por proxy TCP:

| RTT (ms) | Subida | n | Envío p50 (ms) | Envío p95 (ms) | Comandos SMTP (p50) | Fallos |
|---|---|---|---|---|---|---|
| 0 | sin límite | 10 | 106,3 | 128,6 | 9 | 0 |
| 50 | sin límite | 10 | 640,2 | 670,6 | 9 | 0 |
| 150 | sin límite | 10 | 1707,7 | 1737,5 | 9 | 0 |
| 50 | 10 Mbps | 5 | 2099,7 | 2103,5 | 9 | 0 |
| 50 | 2 Mbps | 5 | 8054,0 | 8075,3 | 9 | 0 |

Lectura: con RTT 50 ms, un envío toma ≈ 11 viajes de ida y vuelta (640 ms). Con RTT 150 ms, ≈ 1,7 s. Con el banner, la transferencia del mensaje de 1,83 MB agrega ≈ 1,5 s a 10 Mbps y ≈ 7,3 s a 2 Mbps. Sin banner, el mismo mensaje de 7 kB agregaría ~28 ms a 2 Mbps (cálculo a partir del tamaño medido). El `ConnectionResetError` que aparece en la salida es la limpieza del proxy al cerrar la conexión; no afecta los resultados.

**Tiempos de respuesta al usuario por flujo** (síntesis de §5.2): en los flujos síncronos, la respuesta HTTP espera la conexión, TLS, AUTH, DATA y la transferencia del mensaje. En el formulario de contacto eso ocurre **dos veces en serie**. Con RTT 50 ms y subida de 2 Mbps, el contacto tardaría ≈ 16 s en responder, medido como dos envíos de §4.4 en serie; con 10 Mbps ≈ 4,2 s. Son valores de laboratorio; el proveedor real puede sumar tiempo de aceptación no medido aquí.

**Qué no se midió:** latencia del proveedor SMTP real y tiempo de aceptación (NO EVALUADO; ver §8.2, prueba 2).

### 4.5 CPU y memoria del hash de contraseñas

Argon2id con los parámetros del código (m = 64 MiB, t = 3, p = 4), Python 3.13 con `pwdlib`. Fuente: `argon2_salida.txt`.

| Operación | p50 (ms) | p95 (ms) |
|---|---|---|
| Hash | 56,9 | 69,2 |
| Verificación | 54,9 | 67,6 |
| Cambio de contraseña (5 operaciones: vigente + 3 del historial + hash nuevo), n = 15 | 264,1 | 301,0 |

Concurrencia con procesos separados (pico de RSS real):

| Verificaciones simultáneas | Tiempo de pared (ms) | Por verificación p50 (ms) | Pico RSS (MB) |
|---|---|---|---|
| 1 | 49,4 | 49,1 | 110,6 |
| 2 | 118,8 | 116,9 | 174,7 |
| 4 | 260,1 | 237,0 | 302,6 |
| 8 | 670,7 | 632,3 | **554,6** |

**Lectura.** El costo de CPU es lineal: no hay paralelismo real entre verificaciones en 4 vCPU. El costo de memoria es ~55 MB por verificación en vuelo. El backend en `compose.yaml` tiene 512 MB, así que **unas 7 verificaciones simultáneas (logins o cambios de contraseña) agotan el límite**. En producción (1 GB) el margen sube a unas 15. El RSS medido corresponde al proceso de laboratorio con `pwdlib`; la API real tiene más memoria base (pool de conexiones, FastAPI), por lo que el margen real es **menor**.

### 4.6 Tope de llamadas al driver (`db/gate.py`)

Simulación con el `limitDriverCalls` real sobre SQLite. Consulta de calibración de ~30 ms. Fuente: `gate_sim.json`. **No representa SQL Server**: mide el comportamiento del semáforo del código.

**A. Techo de consultas por segundo, 40 hilos, 600 consultas:**

| Tope | Consultas/s | Latencia p50 (ms) | Latencia p95 (ms) |
|---|---|---|---|
| sin tope (0) | 124,8 | 298,7 | 410,7 |
| 2 (producción) | 62,3 | 30,3 | 2034,5 |

**B. Efecto de consultas lentas (~1,2 s) sobre 200 consultas rápidas, 10 hilos, tope 2:**

| Escenario | Rápidas p50 (ms) | Rápidas p95 (ms) |
|---|---|---|
| sin consulta lenta | 7,7 | 14,6 |
| 1 consulta lenta | 7,6 | 14,6 |
| 2 consultas lentas simultáneas | 7,6 | **73,2** |

**Lectura.** El tope evita que muchos hilos compitan dentro del driver, pero **limita el paralelismo a 2 llamadas por proceso**. Una consulta lenta no bloquea a las demás mientras haya un slot libre. Cuando dos consultas lentas ocupan los dos slots, las que llegan durante esa ventana esperan. El beneficio o perjuicio del tope en SQL Server depende de cuánto tiempo pasa cada llamada en el servidor, y eso no se midió (NO EVALUADO).

### 4.7 Streams SSE (cálculo, no medido)

Cada stream ejecuta un bucle con `asyncio.sleep(0.2)` y `request.is_disconnected()` (5 despertares por segundo). Con el tope global de 300 streams, el event loop único recibe hasta **1500 despertares/s** solo por streams. El costo real es NO EVALUADO.

### 4.8 Polling por usuario (cálculo, no medido)

Con una pantalla de medición visible, la suma es de ≈ 0,9 peticiones/s por pestaña (3 s + 3 s + 5 s + 30 s, según la pantalla). Sin contar streams SSE. Es un cálculo a partir del código; no se midió el tráfico real.

### 4.9 SQL Server (NO EVALUADO)

No hay SQL Server en el laboratorio (puerto 1433 cerrado; sin daemon de Docker). No hay planes de ejecución ni tiempos de consulta reales. H-13, H-18 y H-21 son CONFIRMADOS POR CÓDIGO; su costo queda NO EVALUADO. §8.2 describe cómo medirlos.

### 4.10 Build del frontend (CONFIRMADO POR MEDICIÓN)

| Chunk | kB | gzip (kB) | Nota |
|---|---|---|---|
| `index-*.js` (shell) | 163,19 | 47,73 | |
| `react-*.js` | 186,65 | 58,60 | React y ReactDOM |
| `router-*.js` | 39,71 | 14,36 | react-router |
| `icons-*.js` | 71,50 | 14,53 | lucide-react |
| Base compartida (suma de los 4) | 461,05 | 135,22 | |
| `HelpPage-*.js` | 65,88 | 19,24 | solo `/ayuda` y `/app/ayuda` |

El build tardó 4 min 22 s en este laboratorio (4 vCPU).

### 4.11 Limitaciones explícitas

1. **Sin SQL Server**: sin planes de ejecución ni tiempos de consulta reales.
2. **Sin servidor HP**: no se midió el hardware productivo; las diferencias se listan en §6.5.
3. **Sin SMTP real ni Google**: latencia del proveedor de correo y de Google NO EVALUADAS. El envío medido usa un sumidero local con latencia simulada.
4. **Sin Nginx real**: H-02 se verifica por código (no hay Nginx ni caché de paquetes en el laboratorio).
5. **Un solo equipo**: navegador y servidor local comparten 4 vCPU. Los tiempos absolutos no son comparables con un equipo de usuario, pero sí las diferencias entre controles.
6. **Móvil simulado**: throttling de CPU y red de Chrome, no un dispositivo físico.
7. **Argon2**: el RSS corresponde al proceso mínimo con `pwdlib`, no a la API completa.

---

## 5. Análisis específico: Ayuda y SMTP

### 5.1 Ayuda

**Síntoma reportado:** «se siente pesada y lenta».

**Lo que se descartó como causa principal:**
- Las imágenes no explican la apertura ni el LCP en escritorio ni en móvil (§4.1 y §4.2).
- El desplazamiento se mantiene a 60 fps en todos los controles.
- El visor abre en 25 ms (escritorio) o 67–75 ms (móvil).
- El número de nodos (1235) no es excesivo para el contenido.

**Lo que sí se confirmó:**
1. **Cadena de carga de la ruta (H-04):** en móvil, el chunk de `HelpPage` termina a 2,8 s; el LCP queda en 3,1 s. Es la principal fuente de lentitud percibida al abrir la pantalla en un dispositivo de gama media con red lenta.
2. **Render del cambio de pestaña (H-05):** 160–170 ms en móvil y tareas largas de hasta 144 ms. Las capturas contribuyen ~84 ms de ese p95 (H-01).
3. **Bytes y memoria (H-01, H-02):** 22 PNG (1,59 MB) en escritorio, 11 (0,70 MB) en móvil, ~50 MB de píxeles decodificados. No cambian el tiempo de carga, pero sí el consumo de memoria del navegador y los datos móviles.

### 5.2 SMTP — flujos de envío

Tiempos por flujo: **generación** (plantilla + MIME, ~9 ms), **base de datos** (registro del envío y auditoría), **conexión SMTP** (TCP + TLS + AUTH: ~3 RTT), **aceptación** (DATA + transferencia del mensaje: ~1,8 MB con banner). El tiempo que espera el usuario es el de la petición.

| Flujo | Dónde se envía | ¿La respuesta HTTP espera el SMTP? | Observaciones |
|---|---|---|---|
| Alta de cuenta (verificación) | `registerLocal` → `_sendVerificationEmail` | **Sí** | H-06 |
| Reenvío de verificación | `resendVerification` → `_sendVerificationEmail` | **Sí** | H-06 |
| Formulario de contacto | `sendContactMessage` + `_sendConfirmation` (dos envíos en serie) | **Sí, dos veces** | H-07 |
| Código MFA de recuperación | `mfaRecovery._issueAndSendCode` | **Sí** | H-08 |
| Solicitud de eliminación de cuenta | `accountDeletion.requestDeletion` | **Sí** | H-08 |
| Código de cambio de contraseña | `passwordChangeCode.requestCode` | **Sí** | H-08 |
| Recuperación de contraseña | `auth.requestPasswordReset` → `_notify` | No (segundo plano) | Vía correcta; inconsistente con las anteriores |
| Avisos de cuenta | `_notify` / `sendEmailEventInBackground` | No | |
| Resultado de medición | `measurement._queueResult` → `runInBackground` | No (estado PENDIENTE) | Bien resuelto; es el patrón a replicar |
| Confirmación de resultados | `resultEmailConfirmation.requestConfirmation` | **Sí** | H-08 |
| Eliminación de institución | `institution.py:1424` (cola por miembro) | No, pero sin límite de cola | H-12 |

**Qué bloquea y qué ya corre en segundo plano.** Los flujos sincrónicos bloquean la respuesta HTTP: con RTT 50 ms y subida de 2 Mbps, cada uno tarda entre 0,6 s y 8 s (§4.4), y el contacto tarda el doble. El patrón de `_queueResult` ya resuelve esto, pero no se aplicó de forma uniforme. La recuperación de contraseña va por segundo plano, mientras que el registro y el reenvío de verificación esperan al SMTP. La inconsistencia entre módulos es el problema de fondo.

**Costo de cada envío:** el banner aporta prácticamente todo el peso del mensaje (1,83 MB frente a 7 kB). Reducirlo cambia el tiempo de transferencia en un orden de magnitud sin tocar la lógica.

**No se enviaron correos reales.** Las mediciones se hicieron contra un sumidero local con latencia simulada.

---

## 6. Problemas confirmados frente a hipótesis

### 6.1 Confirmados por medición

- Ayuda abre con 22 PNG (1,59 MB) en escritorio y 11 PNG (0,70 MB) en móvil; las imágenes no cambian FCP ni LCP en ningún perfil (H-01).
- La apertura móvil está dominada por la cadena de carga del chunk de la ruta (H-04, waterfall).
- El cambio de pestaña en móvil tarda 160–170 ms con tareas largas de hasta 144 ms (H-05).
- El correo tiene 1,83 MB por mensaje, de los cuales 1,82 MB son el banner (H-09).
- Cada envío SMTP real hace 9 comandos y escala con el RTT (≈ 11 RTT) y con el ancho de banda de subida (H-10).
- 8 verificaciones de Argon2 simultáneas llegan a 555 MB de RSS (H-15).
- Con dos consultas lentas, el tope de 2 llamadas por proceso eleva el p95 de las rápidas de 15 a 73 ms (H-14).
- Build: shell 163 kB + react 187 kB + router 40 kB + icons 72 kB; HelpPage 66 kB.

### 6.2 Confirmados por código

H-02, H-06, H-07, H-08, H-11, H-12, H-13, H-16, H-18, H-19, H-21, H-23, H-25. Su costo en producción queda como NO EVALUADO donde corresponda.

### 6.3 Afirmaciones de documentación anterior, verificadas de nuevo

| Afirmación anterior (historial) | Estado en el código actual |
|---|---|
| Tope de llamadas al driver `DB_MAX_CONCURRENT_CALLS = 2` | **Presente** (`db/gate.py`, `core/config.py`); su efecto medido en este documento es H-14 |
| Muestras del sensor en tandas de 400 | **Presente** (`services/measurement.py`, `SAMPLES_PER_INSERT = 400`) |
| Corrección del aviso de grupo `.is_(True)` | **No aparece** `.is_(True)` en `services/` (búsqueda por texto) |
| Carga diferida por pantalla | **Presente** (`App.jsx`, `lazyNamed`); **no incluye precarga de `/ayuda`** (H-04) |
| Nginx gzip precomprimido y `Vary` | **Presente** (`gzip_static`, `gzip_vary`) |
| Compilación del frontend ~3 min 20 s | No comparable: este laboratorio tardó 4 min 22 s con otros recursos |

Ninguna de estas afirmaciones se reutiliza como métrica de este informe.

### 6.4 Validez de las mediciones y de los cálculos

- Las mediciones de navegador son comparables entre controles dentro de la misma campaña; no son absolutas.
- El tope de llamadas (§4.6) se mide con SQLite: confirma el mecanismo, no el efecto en SQL Server.
- Los despertares SSE (§4.7) y el polling (§4.8) son cálculos a partir del código.
- Las corridas de la primera tanda de Ayuda se interrumpieron por cierre del navegador; se descartaron y se repitieron completas (60 corridas válidas, 0 errores en el archivo final).

### 6.5 Diferencias entre el entorno de pruebas y el servidor HP

| Aspecto | Compose base (desarrollo) | Compose producción | Servidor HP |
|---|---|---|---|
| CPU del backend | 1,0 | 2,0 | NO EVALUADO |
| Memoria del backend | 512 MB | 1 GB | NO EVALUADO |
| Memoria SQL Server | 2 GB | 4 GB | NO EVALUADO |
| Edición SQL Server | Express (por defecto) | Express (por defecto) | NO EVALUADO — verificar |
| Procesos Uvicorn | 1 | 1 | NO EVALUADO |
| Certificado SQL verificado | sí (conexión cifrada) | sí | NO EVALUADO |

---

## 7. Soluciones propuestas (NO implementadas)

Cada solución incluye su costo y su riesgo. Ninguna se implementa sin autorización expresa.

### 7.1 Ayuda

- **S-01 Precarga de la ruta de Ayuda (H-04):** agregar `/ayuda` y `/app/ayuda` a `PRELOADS`, o `modulepreload` del chunk de `HelpPage` en el HTML inicial. Costo: bajo. Beneficio esperado: elimina un nivel de RTT del LCP en móvil (≈ 1 s con Fast 3G). Riesgo: bajo; sube un poco la carga del shell en la portada, así que conviene limitarla a esas rutas.
- **S-02 Miniaturas reducidas (H-01):** generar variantes ≤ 840 px (WebP o PNG reducido) para las miniaturas y mantener el original para el visor. Costo: bajo. Beneficio: –0,6 MB en móvil, –1,3 MB en escritorio, –15 MB de píxeles decodificados, y ~80 ms menos de tarea larga en móvil al cambiar de pestaña. Riesgo: legibilidad de texto en las capturas; revisar con el visor.
- **S-03 Caché para `/ayuda/` (H-02):** `expires` o `Cache-Control` de larga duración con nombres versionados. Costo: bajo, cambio de configuración de Nginx (requiere autorización). Riesgo: una captura actualizada sin cambiar el nombre quedaría en caché.
- **S-04 Cambio de pestaña más liviano (H-05):** renderizar solo los temas visibles o dividir el contenido por pestaña. Costo: medio. Beneficio: reduce el costo restante de ~120 ms en móvil. Riesgo: navegación por anclas y lectura de pantalla; cubrir con las pruebas de Ayuda.
- **S-05 División de `helpContent.js` (H-03):** cargar el texto por pestaña. Costo: medio. Beneficio pequeño; prioridad baja.

### 7.2 Correo

- **S-06 Envío fuera de la petición en todos los flujos (H-06, H-07, H-08):** aplicar el patrón de `measurement._queueResult` (registro PENDIENTE, segundo plano, estado consultable). Costo: medio; cambia la respuesta de algunos endpoints. Riesgo funcional: alto en verificación y códigos; hay que revisar la UX de «correo enviado» y evitar la enumeración de cuentas por diferencias de respuesta.
- **S-07 Banner más liviano (H-09):** reducir `bannerCorreoGlucoLume.png` (dimensiones y compresión) hasta un tamaño de ~50–100 kB. Costo: bajo. Beneficio: el mensaje pasa de ~1,8 MB a ~0,1 MB, con un envío a 2 Mbps de ~8 s a ~1 s (100 kB a 2 Mbps más 50 ms de RTT). Riesgo: calidad visual del encabezado; alternativa de imagen externa, descartada porque muchos clientes bloquean imágenes remotas.
- **S-08 Reutilización de conexión SMTP (H-10):** mantener una conexión por lote o un pool pequeño con reconexión ante error. Costo: medio. Beneficio: elimina ~5 de los 9 comandos y el handshake TLS por correo. Riesgo: conexiones obsoletas y timeouts; requiere pruebas de reconexión.
- **S-09 Contacto con una sola sesión SMTP o confirmación en segundo plano (H-07):** costo bajo; la confirmación puede llegar después, lo que debe informarse al usuario.
- **S-10 Cola acotada y persistente (H-11, H-12):** reemplazar el `ThreadPoolExecutor` sin límite por una cola con tope, métrica de profundidad y reintentos registrados en base. Costo: alto. Riesgo: cambio en la entrega de avisos; probar pérdidas y duplicados.

### 7.3 SQL Server y backend

- **S-11 Índice en `Medicion(idPerfilMedicion, fechaHoraInicio)`** incluyendo `estadoMedicion` y `modoMedicion` (H-13). Costo: bajo en código; medio en operación (script de actualización aplicado por un administrador, como indica `services/schemaCompat.py`). Riesgo: espacio y costo de escritura; validar con plan real.
- **S-12 Eliminar el N+1 del listado (H-19):** cargar reglas de matriz y `ruleIdOf` en lote por página. Costo: medio. Riesgo: cambio en el cálculo del semáforo; pruebas de regresión obligatorias.
- **S-13 Dashboard institucional (H-18):** materializar `performedAll` una vez y reutilizar el conjunto de identificadores; evaluar índice en `Auditoria(tablaAfectada, accion, idRelacionado)`. Costo: medio. Riesgo: cambio de conteos.
- **S-14 Tope de llamadas al driver (H-14):** revisar el valor de 2 con medición en SQL Server real, o separar un pool para consultas rápidas y otro para consultas pesadas. Costo: medio. Riesgo: volver a provocar la contención que el tope evitó; no tocar sin medición.
- **S-15 Argon2 (H-15):** el costo de CPU y memoria no se resuelve bajando parámetros sin una decisión de seguridad documentada. Alternativas: dimensionar memoria del contenedor (S-16) y limitar verificaciones concurrentes por proceso. Riesgo de seguridad: cambiar parámetros afecta contraseñas existentes; el código ya soporta rehash gradual con `verify_and_update`.
- **S-16 Dimensionamiento de contenedores (H-15, H-16):** el backend necesita memoria para la concurrencia de logins: ~110 MB base + ~55 MB por verificación. Costo: bajo. Riesgo: cambio de configuración de servidor (requiere autorización).
- **S-17 Streams sin polling (H-20):** reemplazar el sondeo de 0,2 s por notificación (`asyncio.Event`) desde el hub. Costo: medio. Riesgo: reconexión y pérdida de eventos.

### 7.4 Frontend

- **S-18 Polling con visibilidad y backoff (H-23):** pausar intervalos con `document.visibilityState` y espaciar cuando no hay cambios. Costo: bajo. Riesgo: avisos menos inmediatos.
- **S-19 Memorizar filas de listas (H-24):** `React.memo` en filas y tarjetas de pantallas con polling. Costo: bajo. Requiere medición antes de aplicar (es hipótesis).

### 7.5 Administración

- **S-20 Estado del sistema con caché corta (H-25):** guardar el resultado de la sonda SMTP y Google durante 30–60 s. Costo: bajo. Riesgo: estado obsoleto de hasta un minuto.

---

## 8. Riesgos y pruebas requeridas

### 8.1 Riesgos de seguridad y funcionales

- Cambiar el envío a segundo plano altera qué ve el usuario después de registrarse o pedir un código. Debe evitarse que la respuesta revele si el correo existe.
- Cambiar parámetros de Argon2 exige rehash gradual.
- Un índice nuevo en `Medicion` requiere un script de actualización aplicado por el administrador de la base; la aplicación no ejecuta DDL.
- Reducir el banner o las capturas no debe alterar el texto alternativo ni la legibilidad.
- Una cola de correo persistente guarda datos personales de destinatarios: debe respetar la política de retención vigente.

### 8.2 Pruebas necesarias antes de cualquier cambio

1. **Planes de ejecución en SQL Server real** para historial de mediciones, analítica de pacientes y dashboard institucional, antes y después de S-11 y S-13, en una base descartable.
2. **Prueba de SMTP con un servidor de prueba del proveedor o un sumidero con latencia medida:** tiempo de aceptación de DATA (no medido aquí), antes y después de S-06, S-08 y S-09.
3. **Prueba de memoria** con logins concurrentes y el límite real del contenedor (repetir §4.5 con la API completa).
4. **Prueba de SQL Server bajo el tope de llamadas** (S-14) con consultas reales de historial y dashboard.
5. **Regresión de Ayuda:** navegación por pestañas y anclas, visor con flechas y teclas, texto alternativo, y medición móvil de §4.2 con los mismos controles.
6. **Regresión de correo:** cada plantilla renderiza, el banner se muestra, `Reply-To` y los enlaces de acción pasan la validación de origen.
7. **Regresión del semáforo de glucosa** después de S-12.
8. Ejecutar las pruebas existentes del repositorio antes y después de cada cambio.

---

## 9. Plan de optimización posterior a la exposición

Orden dentro de cada grupo. Todo requiere autorización.

### 9.1 Riesgo bajo

- S-01 Precarga de la ruta de Ayuda (mayor beneficio en móvil con costo mínimo).
- S-02 Miniaturas reducidas en Ayuda.
- S-07 Banner de correo más liviano (mayor beneficio en bytes de correo).
- S-09 Contacto con una sola sesión SMTP o confirmación en segundo plano.
- S-18 Pausa de polling con visibilidad.
- S-20 Caché corta del estado del sistema.
- S-03 Caché para `/ayuda/` en Nginx (requiere autorización de configuración).
- S-16 Dimensionamiento de memoria del backend (requiere autorización de configuración).

### 9.2 Riesgo medio

- S-06 Envío fuera de la petición para verificación, códigos y confirmación de resultados (cambia respuestas).
- S-08 Reutilización de conexión SMTP.
- S-12 Eliminar el N+1 del listado de mediciones.
- S-13 Dashboard institucional con conjunto materializado.
- S-04 Cambio de pestaña más liviano en Ayuda.
- S-19 `React.memo` en listas con polling (tras medición).

### 9.3 Riesgo alto

- S-10 Cola de correo acotada y persistente.
- S-11 Índice en `Medicion(idPerfilMedicion, ...)` (requiere plan real y ventana de actualización).
- S-14 Cambio del tope de llamadas al driver (requiere medición en SQL Server).
- S-15 Cambio de parámetros de Argon2 (decisión de seguridad).
- S-17 Streams sin polling.

---

## 10. Resumen

Ver el resumen ejecutivo en la respuesta de la sesión. Este documento queda como diagnóstico y no autoriza cambios.
