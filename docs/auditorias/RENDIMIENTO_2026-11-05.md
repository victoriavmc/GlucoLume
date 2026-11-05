# Auditoría integral de rendimiento de GlucoLume — estado de `master` al 5 de noviembre de 2026

> **Tipo de documento:** diagnóstico. No se implementó ninguna corrección, no se modificó código funcional, base de datos, Docker ni configuración de servidor, y no se envió ningún correo real.
> **Vigencia:** el diagnóstico describe solo el commit indicado en la sección 1. Cualquier cambio posterior exige repetir las mediciones afectadas.
> **Autorización:** todas las soluciones de la sección 7 quedan **pendientes de autorización expresa**.

---

## Resumen ejecutivo

1. **La pantalla de Ayuda no es lenta por sus imágenes ni por su contenido.** Con 114 capturas y 1 235 nodos DOM, el desplazamiento es fluido (cuadros de 16,7 ms, sin jank) y la memoria JS es de ≈5 MB. La carga se explica por la **app shell compartida** (≈160 KB comprimidos entre JS y CSS, en cascada) y por el **costo de re-montar la guía al cambiar de pestaña** (≈90 ms en escritorio y ≈220 ms en móvil simulado). En móvil simulado, la guía agrega solo ≈80–100 ms al `load` frente a la portada.
2. **Problema funcional de mayor urgencia: `/ayuda` responde 403 al cargarse directamente** con la plantilla de Nginx del repositorio (`/ayuda` → 301 → `/ayuda/` → 403). El enlace de la barra pública es navegación interna y funciona, pero recargar la página o compartir el enlace no. Se confirmó con Nginx 1.24 y la plantilla del repositorio; la imagen de producción (nginx 1.30) no pudo ejecutarse aquí.
3. **Los correos bloquean las peticiones HTTP en 9 flujos** (registro, reenvío de verificación, eliminación de cuenta, código de cambio de contraseña, recuperación MFA, invitaciones y restablecimientos de plataforma, contacto y soporte). Con SMTP con 150 ms por comando, un correo tarda ≈1,2 s; con un servidor caído, la petición queda colgada **20 s** y después devuelve error.
4. **Ese bloqueo es más grave que la lentitud del propio correo:** 40 peticiones esperando SMTP agotan el threadpool de la API y un endpoint no relacionado pasa de **5 ms a 5 s** (medido con un modelo de FastAPI). Como casi todos los endpoints son síncronos, un SMTP lento degrada toda la API, incluido el inicio de sesión.
5. **Inicio de sesión con Argon2id:** el backend satura en ≈12 verificaciones por segundo en 4 vCPU, con p95 de 3,5 s a 32 simultáneas, y **≈56 MB de RAM por operación concurrente**. Con el límite de 1 GB del contenedor de producción, el riesgo de OOM aparece con alrededor de 15 inicios de sesión simultáneos (estimación a partir de la RAM medida; no verificada en contenedor).
6. **Restricciones de base de datos sin medir en ejecución:** `DB_MAX_CONCURRENT_CALLS=2` limita a dos llamadas simultáneas al driver por proceso (modelo: ≈388 ejecuciones/s frente a ≈1 554 sin tope), y `Medicion` no tiene índice que empiece por `idPerfilMedicion`. Ambos son hallazgos de código; su efecto real requiere SQL Server y no pudo medirse en este entorno.
7. **Diagnóstico de Ayuda y correo frente a la documentación anterior:** no se reutilizó ninguna métrica ni prioridad previa. Todos los datos de este documento provienen de mediciones o de código de `6922949`.

---

## 1. Identificación del estado auditado

| Dato | Valor |
|---|---|
| Repositorio | `victoriavmc/GlucoLume` |
| Rama auditada | `master` |
| Commit SHA auditado | `6922949a002d85c047a40da2a66d7c978f32ab2b` |
| Mensaje del commit | «Merge optimización de frontend (S-01, S-02, S-07) y validación» |
| Fecha del commit | 2026-11-05 22:47:58 +0000 |
| Fecha de revisión | 2026-11-05 |
| Árbol de trabajo al inicio | limpio (`git status` sin cambios) |
| Otras ramas | `claude/sweet-mendel-xd2663` apunta al mismo SHA; no se usó para esta auditoría (ver nota) |
| Historial de `master` | 37 commits posteriores al estado local anterior (`1e03322`), sincronizado con `origin/master` antes de auditar |

> **Nota de rama.** La instrucción de la auditoría pide usar `master` y no crear ramas nuevas. Esta auditoría se escribió y publicó solo en `master`. La rama `claude/sweet-mendel-xd2663` que indicaban las instrucciones de la sesión apunta al mismo SHA auditado; no se modificó.

**Tratamiento de la documentación anterior.** `docs/RENDIMIENTO.md`, `docs/PENDIENTES.md`, `PR_rendimiento.md`, `docs/auditorias/REMEDIACION_RENDIMIENTO_2026-11-05.md`, `docs/auditorias/VALIDACION_OPTIMIZACION_2026-11-11.md` y las evidencias de rendimiento previas se leyeron **solo como historial**. Sus métricas, prioridades y pendientes no se reutilizan. Las afirmaciones de código que se citan aquí se volvieron a comprobar en `6922949`.

El archivo `docs/auditorias/RENDIMIENTO_2026-11-05.md` ya existía con una auditoría de otro commit (`933d84c`, rama `claude/amazing-clarke-p75731`). Esta versión lo reemplaza; la versión previa sigue disponible con `git show 2481da1:docs/auditorias/RENDIMIENTO_2026-11-05.md`.

### 1.1 Entorno de medición

Entorno de laboratorio, **no** el servidor de producción ni el servidor HP.

| Componente | Valor |
|---|---|
| Host | contenedor Linux, 4 vCPU, 16 GB RAM, sin límites de cgroup configurados por la auditoría |
| Node / Playwright | Node 22.23.4, Chromium de Playwright (`/opt/pw-browsers`) |
| Frontend | build de producción con Vite 6.4.5 (`VITE_API_BASE_URL=/`), tiempo de build 4 min 13 s |
| Nginx | nginx 1.24.0 (Ubuntu) con la plantilla real `docker/nginx/default.conf.template` (variables sustituidas, `user root`, puerto 8080) |
| Backend | Python 3.13 con `backend/requirements.txt` (hashes fijados); FastAPI 0.142.2; uvicorn 0.53.0 |
| SMTP | servidor de laboratorio `aiosmtpd` 1.4.6 en `127.0.0.1` con STARTTLS, AUTH y verificación de certificado con CA propia; descarta los mensajes |
| Docker | **no disponible** (sin daemon). No se levantó SQL Server ni `compose`. |
| SQL Server | **no disponible**. Solo análisis de esquema y de código. |

---

## 2. Alcance y metodología

### 2.1 Alcance

- **Frontend:** pantalla de Ayuda (caso obligatorio A), cambio de pestañas, desplazamiento, visor de capturas, bundles, cascada de carga, polling, memoria y cobertura de CSS/JS. Core Web Vitals (LCP, CLS, FCP) y tiempos en móvil simulado.
- **Backend:** flujos de correo (caso obligatorio B), endpoints síncronos y asíncronos, threadpool, hashing Argon2id, semáforo de llamadas al driver, procesos de fondo (mantenimiento y streams).
- **SQL Server:** esquema v5 (`database/reference/GlucoLume_DB_v5.sql`, codificado en UTF-16), índices, claves, consultas de los caminos calientes (historial, estadísticas, indicadores institucionales, auditoría).
- **Infraestructura:** `compose.yaml`, `compose.prod.yaml`, `backend/Dockerfile`, `frontend/Dockerfile`, plantilla de Nginx, límites de recursos y healthchecks.
- **Integraciones:** SMTP (todos los flujos de envío y su clasificación) y Google OAuth (lectura de código).

### 2.2 Metodología

| Técnica | Qué se midió | Herramienta |
|---|---|---|
| Medición en navegador | carga, FCP, LCP, CLS, long tasks, nodos, peticiones y bytes; cambio de pestaña con atribución de scripting, estilo, layout y pintado; desplazamiento; visor; cobertura de CSS | Playwright + CDP (`bench_help.js`, `help_extra.js`, `coverage_help.js`, `leak_*.js`, `baseline_load.js`) |
| Medición de cabeceras | caché, codificación y códigos de respuesta de Nginx con la plantilla del repositorio | `curl` contra Nginx 1.24 |
| Medición de CPU y RAM | latencia p50/p95, throughput y RSS pico del hashing Argon2id con los parámetros de `security.py` | `bench_argon2.py` |
| Medición del camino SMTP | render, construcción MIME, fases de la conexión (TCP/EHLO, STARTTLS, AUTH, envío, QUIT), timeouts, cola en segundo plano, con retardo inyectado por comando | `bench_smtp.py` + `smtp_sink.py` |
| Modelos mínimos | threadpool con endpoints síncronos bloqueados; semáforo `DB_MAX_CONCURRENT_CALLS` con el código real de `app/db/gate.py` | `pool_model.py`, `pool_client.py`, `gate_model.py` |
| Análisis estático | esquema, índices, claves, consultas, flujos de llamada, polling, configuración | lectura de código con búsqueda por texto |

**Escala de clasificación** (aplicada a cada resultado):

- **CONFIRMADO POR MEDICIÓN:** reproducido con una medición en este entorno. Indica el alcance de la medición.
- **CONFIRMADO POR CÓDIGO:** el comportamiento se lee directamente del código o del esquema; su efecto en producción no se midió.
- **HIPÓTESIS NO VERIFICADA:** causa plausible sin evidencia suficiente.
- **NO EVALUADO:** no se pudo medir ni verificar con las herramientas disponibles. Se indica cómo medirlo.

**Escala de prioridad:** **P0** afecta a usuarios hoy y conviene corregirlo de inmediato; **P1** riesgo alto de disponibilidad o rendimiento; **P2** impacto medio; **P3** mejora menor o riesgo bajo.

### 2.3 Restricciones cumplidas

- No se modificó código funcional, base de datos, Docker ni configuración de ningún servidor. Los archivos de la copia de medición (build, configuración de Nginx) están en el scratchpad de la sesión, no en el repositorio.
- No se enviaron correos reales: todos los envíos fueron a `example.com` (dominio reservado) a través de un servidor de laboratorio en `127.0.0.1`, que descarta los mensajes.
- No hubo carga contra producción ni contra servicios externos. No hubo pruebas destructivas.
- **Limitación de la prueba de Ayuda:** Nginx responde 403 a `/ayuda`, así que para medir la guía en el laboratorio la **navegación de documento** a `/ayuda` se respondió con el `index.html` del propio build (interceptación con Playwright). Todos los demás pedidos (JS, CSS, capturas) llegaron a Nginx sin cambios. Esta sustitución no altera la medición de la pantalla, pero sí significa que el 403 se documenta por la prueba de `curl` directa (sección 4.4), no por el navegador.

---

## 3. Matriz de hallazgos priorizados

Prioridad, clasificación y costo son estimaciones de este diagnóstico. El costo es esfuerzo de desarrollo y prueba, sin medir, y no incluye la medición previa que algunos requieren.

| ID | Prio. | Área | Hallazgo | Clasificación | Impacto | Costo estimado | Riesgo de corregir |
|---|---|---|---|---|---|---|---|
| AUD-01 | **P0** | Infra / Ayuda | `/ayuda` responde 403 al cargarse directamente (plantilla Nginx + carpeta `public/ayuda`) | CONFIRMADO POR MEDICIÓN (Nginx 1.24) | Enlace público roto al recargar o compartir | 1–2 h | Bajo |
| AUD-02 | P1 | Correo / Backend | 9 flujos envían SMTP dentro de la petición HTTP | MEDICIÓN + CÓDIGO | 1–20 s por acción; 20 s por intento con servidor caído | 3–5 días | Medio (cambia respuesta) |
| AUD-03 | P1 | Backend | Threadpool agotado por endpoints síncronos que esperan SMTP; `/healthz` también es síncrono | MEDICIÓN (modelo) + CÓDIGO | Un SMTP lento degrada toda la API | 0,5–1 día | Bajo |
| AUD-04 | P2 | Correo | Cola en segundo plano de 2 hilos, sin límite ni persistencia | MEDICIÓN + CÓDIGO | 30 avisos = 17,7 s; se pierden al reiniciar | 2–3 días | Medio |
| AUD-05 | P1 | Backend / Auth | Argon2id sin límite de concurrencia | MEDICIÓN (laboratorio) + CÓDIGO | Techo ≈12 verif./s; OOM estimado con ≈15 simultáneas en 1 GB | 0,5 día | Bajo (no cambiar parámetros) |
| AUD-06 | P1 | Base de datos | Tope de 2 llamadas simultáneas al driver por proceso | CÓDIGO + MODELO (efecto NO EVALUADO) | Posible techo de throughput en producción | 1–2 días de medición | Alto si se cambia sin medir |
| AUD-07 | P1 | SQL | `Medicion` sin índice líder por `idPerfilMedicion`; listados y estadísticas por paciente | CÓDIGO (plan NO EVALUADO) | Escaneos crecientes con el historial | 1–3 días (DBA) | Medio–alto (DDL) |
| AUD-08 | P2 | SQL / Backend | Indicadores institucionales cargan todas las mediciones completadas a memoria | CÓDIGO | Memoria y CPU crecientes con el volumen de la institución | 2–3 días | Medio (supresión de grupos pequeños) |
| AUD-09 | P2 | Backend | Rango `desde`/`hasta` de estadísticas sin tope de duración | CÓDIGO | Carga arbitraria de filas en una petición | 0,5 día | Bajo–medio (contrato de API) |
| AUD-10 | P2 | SQL / Auditoría | Listado y resumen de auditoría sin ventana por defecto (COUNT y agregados sobre todo el historial) | CÓDIGO (NO EVALUADO) | Cada carga de la pantalla recorre el historial del ámbito | 2–4 días | Medio (cambio de comportamiento; cumplimiento) |
| AUD-11 | P2 | Backend | Purga de `AuditoriaTecnicaMedicion` en un `DELETE` sin lotes cada 60 s en cada réplica | CÓDIGO | Bloqueos o transacciones largas con backlog | 0,5 día | Bajo |
| AUD-12 | P2 | Frontend | 9 bucles de polling (3–60 s); solo 2 pausan con la pestaña oculta | CÓDIGO (costo NO EVALUADO) | Peticiones y consultas repetidas por usuario | 1–2 días | Bajo |
| AUD-13 | P2 | Frontend / Ayuda | Cambiar de pestaña re-monta ≈1 131 nodos | MEDICIÓN | 89 ms (escritorio), 219 ms (móvil simulado) | 0,5–1 día | Bajo |
| AUD-14 | P2 | Frontend / Ayuda | El chunk de la guía se pide solo después de ejecutar el bundle de entrada | MEDICIÓN | Móvil simulado: el chunk de la guía empieza a pedirse ≈1,1 s después de la petición del documento | 0,5 día (precarga); 2–3 días (dividir shell) | Bajo / medio |
| AUD-15 | P2 | Frontend / CSS | CSS global de 123 KB en todas las pantallas; en Ayuda se usa 4,9 % | MEDICIÓN (cobertura) | Render bloqueado y bytes sin uso en cada pantalla | 3–5 días | Alto (regresión visual) |
| AUD-16 | P3 | Infra / Ayuda | Capturas de `/ayuda` sin política de caché (solo `Last-Modified`) | MEDICIÓN (cabeceras) | Revalidación en cada visita | 0,5 h | Bajo |
| AUD-17 | P3 | Frontend / Ayuda | El visor descarga el PNG original al abrir y al cambiar de captura | MEDICIÓN | Móvil simulado: 818 ms al abrir, 259 ms por captura (p50) | 1 día | Bajo–medio |
| AUD-18 | P3 | Frontend / Ayuda | Nodos desconectados y listeners retenidos tras abrir el visor | MEDICIÓN (causa HIPÓTESIS) | ≈25 nodos y 5–19 listeners por apertura | 0,5–1 día | Bajo |
| AUD-19 | P3 | Frontend / Ayuda | Capturas sin `width`/`height` (riesgo de CLS) | HIPÓTESIS (CLS = 0 en la prueba) | Sin efecto medido; riesgo residual | 0,5 h | Bajo |
| AUD-20 | P2 | Infra | Un proceso uvicorn; límites de producción sin dimensionar con datos; `lifecycle` y `notifications` sin límites | CÓDIGO (capacidad NO EVALUADA) | Techo de capacidad desconocido | 1–2 días (medir) | Medio |
| AUD-21 | P3 | Backend / Institucional | Soporte institucional mantiene la conexión de BD durante el SMTP | CÓDIGO | Conexión del pool ocupada 1–20 s por consulta | 2 h | Bajo |
| AUD-22 | P3 | Integraciones | Llamadas a Google (token y People API) sin timeout explícito | CÓDIGO (latencia NO EVALUADA) | Latencia externa no acotada | 0,5 día | Bajo |
| AUD-23 | P3 | SQL | Claves agrupadas `NEWID()` en tablas de alto volumen (`Medicion`, `NotificacionUsuario`, `AuditoriaTecnicaMedicion`) | CÓDIGO (efecto NO EVALUADO) | Fragmentación de índices con inserciones | 2–4 días + ventana | Alto (migración) |
| AUD-24 | P3 | Correo | Cada correo abre una conexión SMTP nueva (TCP + STARTTLS + AUTH) | MEDICIÓN | 2 correos: 2 451 ms frente a 1 688 ms con conexión compartida (150 ms/comando) | 1–2 días (después de AUD-02) | Medio |

**Positivos verificados (no son hallazgos):** rutas con `lazy` en `App.jsx`; capturas con `loading="lazy"` y miniaturas WebP de 840 px; precompresión `gzip -9` con `gzip_static`; `/assets/` con `max-age=31536000`; conexión SMTP compartida en el flujo de contacto; caché de 10 minutos para las comprobaciones de esquema; actividad de sesión escrita como máximo una vez por minuto; escritura de muestras del sensor en lotes de 400 filas (dentro del límite de 2100 parámetros); `IN` de la pantalla de operador acotado por página.

---

## 4. Resultados de mediciones y limitaciones

### 4.1 Pantalla de Ayuda (`/ayuda`, build de producción, Nginx 1.24)

Medición de 5 repeticiones por perfil. Escritorio: 1 366×800, sin limitación. Móvil simulado: 390×844, CPU 4× más lenta, 1,6 Mbps de bajada, 750 kbps de subida, RTT 150 ms. Fuente: `docs/auditorias/evidencias/auditoria_master_2026-11-05/mediciones/ayuda_5_repeticiones.json`.

**Carga**

| Métrica | Escritorio p50 (p95) | Móvil simulado p50 (p95) |
|---|---|---|
| TTFB | 2,9 ms (7,7) | 2,9 ms (3,2) |
| DOMContentLoaded | 55,5 ms (69,1) | 1 077 ms (1 085) |
| `load` | 89,3 ms (101,9) | 1 275 ms (1 276) |
| FCP | 96 ms (104) | 1 168 ms (1 200) |
| **LCP** | **460 ms (464)** | **1 648 ms (1 712)** |
| CLS (carga) | 0 | 0 |
| Long tasks (suma) | 0 | 288 ms (376) |
| Red en reposo (network idle) | 979 ms (1 013) | 2 484 ms (2 540) |
| Nodos DOM | 1 235 | 1 235 |
| Figuras (capturas en el DOM) | 114 | 114 |
| Capturas cargadas al inicio (lazy) | 22 | 5 |
| Bytes de imágenes al inicio | 296 KB (22 WebP) | 34 KB (5 WebP) |
| Peticiones totales | 32 | 15 |
| Heap JS | 4,7 MB | 5,0 MB |

Tamaños de los recursos (sin comprimir / comprimidos con gzip -9, del build):

| Recurso | Sin comprimir | gzip |
|---|---|---|
| `react-*.js` (React) | 186,6 KB | 58,3 KB |
| `index-*.js` (app shell) | 163,6 KB | 47,6 KB |
| `icons-*.js` (lucide) | 71,5 KB | 14,4 KB |
| `HelpPage-*.js` (guía y `helpContent.js`) | 66,1 KB | 19,3 KB |
| `index-*.css` (CSS global) | 123,2 KB | 22,3 KB |
| `HelpPage-*.css` | 3,7 KB | — |

**Cambio de pestaña** (20 cambios por perfil, medidos con dos cuadros de `requestAnimationFrame`):

| Métrica | Escritorio p50 (p95) | Móvil simulado p50 (p95) |
|---|---|---|
| Hasta el pintado | 89,6 ms (116,5) | 219,3 ms (258,7) |
| Scripting | 10,2 ms (15,0) | 41,6 ms (46,8) |
| Recálculo de estilos | 2,3 ms (3,5) | 9,7 ms (13,2) |
| Layout | 18,0 ms (26,9) | 62,6 ms (82,8) |
| Nodos que cambian por cambio | 1 131 | 1 131 |

**Desplazamiento** (scroll programático de 300 px por cuadro, 5 repeticiones): cuadros p50 y p95 de 16,7 ms en ambos perfiles, **0 cuadros con más de 50 ms**. Altura de página: 29 084 px (escritorio) y 39 716 px (móvil).

**Visor** (apertura de captura ampliada y cambio con flecha):

| Métrica | Escritorio p50 (p95) | Móvil simulado p50 (p95) |
|---|---|---|
| Abrir (hasta que el original está listo) | 61,5 ms (65,9) | 818 ms (1 073) |
| Cambiar de captura | 31,7 ms (37,6) | 259 ms (1 156) |

**Cobertura de CSS en `/ayuda`** (Playwright `coverage`, `ayuda_cobertura_css.txt`): el CSS global (`index-*.css`, 123 171 bytes) tiene **4,9 % de uso**; `HelpPage-*.css` (3 692 bytes), **55,1 %**.

**Cascada de carga en móvil simulado** (`ayuda_cascada_js_cls.txt`, una corrida, en milisegundos):

| Recurso | Inicio | Fin |
|---|---|---|
| Documento `/ayuda` | 0 | 4 |
| `index-*.js` (app shell) | 18 | 918 |
| `react-*.js`, `icons-*.js`, `router-*.js` | 19–20 | 561–969 |
| `index-*.css` | 20 | 668 |
| `HelpPage-*.js` (chunk de la guía) | **1 075** | 1 384 |
| `PageHeader-*.js`, `Tabs-*.js` | 1 092 | 1 270–1 299 |
| `HelpPage-*.css` | 1 093 | 1 291 |

**Comparación con la línea base** (4 repeticiones, `ayuda_linea_base_portada_login.json`):

| Pantalla | Escritorio `load` / LCP | Móvil simulado `load` / LCP | Bytes transferidos (móvil) |
|---|---|---|---|
| Portada `/` | 46,9 ms / 144 ms | 1 214 ms / 1 516 ms | 158 KB |
| Login `/plataforma/login` | 42,6 ms / 380 ms | 1 205 ms / 1 620 ms | 164 KB |
| Ayuda `/ayuda` | 73,1 ms / 440 ms | 1 294 ms / 1 700 ms | 220 KB |

**Retención de memoria** (GC forzado antes de cada lectura; `ayuda_tabs_retencion.txt`, `ayuda_visor_retencion.txt`):

| Acción | Nodos vivos | Listeners JS | Heap |
|---|---|---|---|
| Inicio | 1 795 | 541 | 3,71 MB |
| Tras 10 aperturas de visor | 2 060 | 730 | 4,10 MB |
| Tras 20 aperturas de visor | 2 310 | 780 | 4,19 MB |
| Tras 40 aperturas de visor | 2 810 | 880 | 4,31 MB |
| Tras 30 cambios de pestaña | 1 809 | 541 | 4,50 MB (no concluyente) |

**Lectura de los resultados:**

- El DOM visible se mantiene en 1 235 nodos en todas las mediciones; los nodos adicionales son desconectados y retenidos.
- La guía no aporta peso significativo al `load` en móvil simulado (≈80–100 ms sobre la portada), pero sí a LCP (≈+180 ms).

### 4.2 Correo (SMTP de laboratorio, STARTTLS verificado, sin correos reales)

**Render y construcción** (`smtp_render.json`, 40 repeticiones por evento):

| Etapa | p50 | p95 |
|---|---|---|
| Validación + render Jinja (`EMAIL_VERIFICACION`) | 0,7 ms | 0,8 ms |
| Construcción MIME con banner embebido | 2,1 ms | 2,5 ms |

**Fases de un envío** (`smtp_phases_*.json`; `tcp_ehlo` incluye la apertura TCP y el saludo; `starttls` incluye el EHLO previo y el handshake TLS; `auth` incluye el EHLO posterior y la autenticación; `mail_rcpt_data` es la aceptación del mensaje por el servidor):

| Fase (p50) | Sin retardo (10 envíos) | 150 ms por comando (3 envíos) |
|---|---|---|
| Apertura TCP + saludo del servidor | 0,9 ms | 1,3 ms |
| STARTTLS (EHLO + handshake) | 2,0 ms | 303,8 ms |
| AUTH | 0,7 ms | 302,4 ms |
| MAIL / RCPT / DATA (aceptación) | 7,4 ms | 461,5 ms |
| **Total** | **14,8 ms (p95 40,4)** | **1 225,7 ms (p95 1 250,1)** |

**Envíos completos y envíos de un mismo flujo** (`smtp_delay_*.json`, 5 repeticiones por escenario):

| Retardo por comando | 1 correo | 2 correos, conexión propia | 2 correos, conexión compartida |
|---|---|---|---|
| 50 ms | 424 ms | 846 ms | 587 ms (−31 %) |
| 150 ms | 1 229 ms | 2 451 ms | 1 688 ms (−31 %) |

**Servidor que no responde** (`smtp_blackhole_8028.json`, EHLO demorado 25 s): `sendEmailEvent` devuelve `False` a los **20 054 ms**. Es el tiempo que el hilo de la petición queda bloqueado.

**Cola en segundo plano** (`smtp_queue_8029_30.json`, 2 workers, 150 ms por comando, 30 avisos): encolar los 30 tarda 6 ms; 28 quedan en cola en ese momento; el vaciado completo tarda **17 720 ms** (≈1,7 avisos/s).

### 4.3 Backend: CPU, RAM y concurrencia

**Argon2id** (`argon2_concurrencia.json`; parámetros de `security.py`: m = 64 MiB, t = 3, p = 4; RSS inicial del proceso 110 MB):

| Operaciones simultáneas | Latencia p50 | Latencia p95 | Throughput | RSS pico |
|---|---|---|---|---|
| 1 | 127 ms | 140 ms | 8,1 /s | 110 MB |
| 2 | 174 ms | 238 ms | 10,7 /s | 175 MB |
| 4 | 317 ms | 377 ms | 12,3 /s | 303 MB |
| 8 | 586 ms | 879 ms | 12,5 /s | 558 MB |
| 16 | 1 225 ms | 1 770 ms | 12,3 /s | 1 004 MB |
| 32 | 2 380 ms | 3 524 ms | 12,3 /s | 1 884 MB |

Lectura: el throughput se estabiliza en ≈12,3 verificaciones/s desde 4 simultáneas; por encima de eso, la latencia crece linealmente con la cola. La RAM crece ≈56 MB por operación concurrente. Con 1 GB de límite (`compose.prod.yaml`) y 110 MB base, el límite se alcanza en ≈15–16 operaciones simultáneas. **Ese número es una estimación a partir de la medición en el proceso de laboratorio; no se verificó con el contenedor real.**

**Threadpool con endpoints síncronos bloqueados por SMTP** (`modelo_threadpool_smtp.txt`; modelo mínimo con FastAPI 0.142.2, no es el código de GlucoLume). Se disparan N peticiones que esperan 6 s y luego se mide un endpoint no relacionado:

| Peticiones bloqueadas | Endpoint `def` (síncrono) | Endpoint `async` (control) |
|---|---|---|
| 10 | 4 ms | 2 ms |
| 39 | 5 ms | 3 ms |
| **40** | **5 052 ms** | 3 ms |
| 80 | 11 075 ms | 3 ms |

En GlucoLume hay **264 endpoints `def`** y solo **9 `async def`** (verificado con `grep`). Por eso el umbral del threadpool de 40 hilos (valor por defecto de AnyIO/Starlette) es el que importa.

**Semáforo del driver** (`modelo_semaforo_driver.txt`; código real de `app/db/gate.py`, cursor simulado de 5 ms por ejecución, 8 hilos; el valor de ejecuciones/s es la mitad de las llamadas medidas, porque cada hilo hace una ejecución y un `fetchall`):

| `DB_MAX_CONCURRENT_CALLS` | Ejecuciones/s (modelo) |
|---|---|
| sin tope | ≈1 554 |
| 2 (valor por defecto de `config.py:55`) | ≈388 |
| 4 | ≈775 |
| 8 | ≈1 557 |

**Procesos de fondo dentro de la API:** el mantenimiento (`maintenance.py`) ejecuta `measurementLifecycle.sweep` cada 60 s en cada réplica (`MAINTENANCE_INTERVAL_SECONDS=60`, sin desactivarlo en `compose`). El `sweep` incluye un `DELETE` sin lotes sobre `AuditoriaTecnicaMedicion` (`technicalAudit.py:48`). Los streams SSE revalidan la sesión cada 30 s (`streams.py:22`). Ambos son periódicos y pequeños en condiciones normales; su costo con volumen real no se midió.

### 4.4 Infraestructura y Nginx

**Rutas** (`nginx_rutas.txt`, Nginx 1.24 con la plantilla del repositorio):

| Petición | Respuesta |
|---|---|
| `GET /ayuda` | **301** → `/ayuda/` |
| `GET /ayuda/` | **403** |
| `GET /app/ayuda` | 200 (sirve el SPA; requiere sesión en la app) |
| `GET /consejos` | 200 |

**Cabeceras de caché y compresión** (`nginx_cabeceras.txt`):

| Recurso | `Cache-Control` | `Expires` | Compresión |
|---|---|---|---|
| `/assets/HelpPage-*.js` | `max-age=31536000` | 1 año | `gzip` |
| `/index.html` | `no-cache` | −1 | `gzip` |
| `/ayuda/cliente-menu-inicio.png` | **ausente** | **ausente** | ninguna |
| `/ayuda/miniaturas/cliente-menu-inicio.webp` | **ausente** | **ausente** | ninguna |

**Límites y configuración** (lectura de `compose.yaml`, `compose.prod.yaml`, `Dockerfile`):

| Servicio | Base (`compose.yaml`) | Producción (`compose.prod.yaml`) |
|---|---|---|
| `backend` | 1,0 CPU / 512 MB | 2,0 CPU / 1 GB |
| `db` (SQL Server) | 2 GB | 4 GB |
| `frontend` (Nginx) | 0,5 CPU / 128 MB | sin override |
| `lifecycle`, `notifications` | 0,5 CPU / 256 MB cada uno | **sin límites** |

El backend arranca con `uvicorn app.main:app` sin `--workers` (`backend/Dockerfile:78`): **un solo proceso**. El healthcheck usa `/healthz` con `timeout: 5s`, `interval: 30s`, `retries: 3` (`compose.yaml:68-74`), y `/healthz` es síncrono (`app/main.py:64`).

**Capacidad del servidor HP:** el repositorio no documenta hardware, CPU, memoria, disco ni versión de Docker del servidor de producción (`docs/DESPLIEGUE.md`, `README.md`). **NO EVALUADO.**

### 4.5 Build y bundles

Build de producción sin errores (`build_vite_tamanos.txt`). Los chunks por ruta son pequeños (la mayoría entre 3 y 15 KB gzip, según el reporte de Vite). Los chunks compartidos cargados en `/ayuda` son `react` (58,3 KB gzip), `index` (47,6 KB gzip), `icons` (14,4 KB gzip) y `router` (14,4 KB gzip, según el reporte de Vite).

**Cobertura de JS precisa:** la cobertura de CDP marca 100 % en todos los bundles porque el bloque de nivel superior de cada módulo cubre el archivo entero. **No es concluyente** y no se usa en este documento (ver `mediciones/LEEME.md`).

### 4.6 Limitaciones y mediciones pendientes

| Área | Estado | Motivo | Cómo medirlo |
|---|---|---|---|
| Endpoints reales con SQL Server (latencia, planes, bloqueos) | NO EVALUADO | sin Docker ni SQL Server | Staging con SQL Server 2022, datos sintéticos a volumen real, `SET STATISTICS IO/TIME` y Query Store; carga controlada con k6 o Locust |
| Efecto de `DB_MAX_CONCURRENT_CALLS` | NO EVALUADO | depende de pyodbc y SQL Server reales | Medir con 1, 2, 4, 8 y 0 (sin tope) en staging, con el mismo flujo de carga |
| Contenedor de backend con límite de 1 GB (OOM con Argon2) | NO EVALUADO | sin Docker | Contenedor con `--memory 1g --cpus 2` en staging; escalera de 4, 8, 12, 16 y 20 logins simultáneos |
| Servidor HP (hardware, Docker, disco) | NO EVALUADO | sin datos en el repositorio | Recolectar `nproc`, `free -m`, `docker info`, tipo de disco y latencia a la base |
| Nginx 1.30 (imagen de producción) | NO EVALUADO directo | sin Docker; verificado con 1.24 | `docker run` de la imagen con la plantilla y la matriz de rutas de la sección 4.4 |
| SMTP real del proveedor | NO EVALUADO | sin credenciales ni envíos permitidos | Cuenta de prueba dedicada en staging, un destinatario controlado, medición de fases con `bench_smtp.py` apuntando al host real |
| Google OAuth y People API | NO EVALUADO | sin credenciales ni salida autorizada | Medir token exchange y People API en staging con cuenta de prueba |
| Pantallas autenticadas (cuenta individual, institución, plataforma) | NO EVALUADO | requieren backend y base | Sembrado de datos demo (`app/demo/seeder.py`) en staging y repetir `bench_help.js` adaptado a cada pantalla |
| Cabecera de caché del visor y CLS en redes lentas | parcialmente | medido solo en escritorio para CLS | Repetir CLS con red móvil simulada y rueda real |

---

## 5. Análisis específico: Ayuda y SMTP

### 5.1 Ayuda: qué causa la sensación de lentitud

**Preguntas que pidió la auditoría y respuesta con evidencia:**

| Pregunta | Respuesta medida | Clasificación |
|---|---|---|
| ¿Abrir la sección es lento? | En escritorio, LCP de 460 ms. En móvil simulado, LCP de 1 648 ms; el `load` de la guía es ≈80–100 ms mayor que el de la portada. | CONFIRMADO POR MEDICIÓN |
| ¿El problema son las imágenes? | No en el arranque: 22 capturas (escritorio) o 5 (móvil) se piden por lazy loading; los bytes de imágenes al inicio son 296 KB (escritorio) y 34 KB (móvil). | CONFIRMADO POR MEDICIÓN (descartado como causa principal) |
| ¿El problema es el tamaño del contenido? | No: 1 235 nodos DOM, heap de ≈5 MB, 0 long tasks en escritorio. | CONFIRMADO POR MEDICIÓN (descartado) |
| ¿Cambiar de pestaña es lento? | Sí, en móvil simulado: 219 ms hasta pintar (p50), con 1 131 nodos reemplazados. | CONFIRMADO POR MEDICIÓN |
| ¿Desplazarse es lento? | No: 16,7 ms por cuadro, 0 cuadros con jank en ambos perfiles. | CONFIRMADO POR MEDICIÓN (descartado) |
| ¿El visor es lento? | Abrir y cambiar en móvil simulado: 818 ms y 259 ms (p50), con descarga del original en cada cambio. En escritorio, ≈60 ms y ≈30 ms. | CONFIRMADO POR MEDICIÓN |
| ¿Cuántos componentes se renderizan? | 114 figuras; ≈1 130 nodos cambian al cambiar de pestaña. La guía no usa `memo` ni `content-visibility`. | CONFIRMADO POR MEDICIÓN y CÓDIGO |
| ¿Hay fugas de memoria? | Retención menor: ≈25 nodos y 5–19 listeners por apertura de visor, sin crecimiento visible del heap (+0,6 MB en 40 aperturas). Cambiar de pestaña no retiene nodos. | CONFIRMADO POR MEDICIÓN (causa HIPÓTESIS) |
| ¿Hay problemas de carga de la pantalla? | Sí, el camino crítico pasa por el app shell: el chunk de la guía empieza a pedirse a 1 075 ms, después de ejecutar el bundle de entrada (918 ms). | CONFIRMADO POR MEDICIÓN |
| ¿Responde la ruta? | La ruta pública `/ayuda` responde 403 al cargarse directamente. | CONFIRMADO POR MEDICIÓN (Nginx 1.24) |

**Causa principal de la lentitud percibida:** la combinación de (a) la app shell compartida de ≈160 KB comprimidos (JS y CSS) cargada en cascada, (b) el CSS global con 95 % sin uso en esta pantalla, y (c) el re-montaje de ≈1 130 nodos y su pintado en cada cambio de pestaña. Las capturas, el scroll y la memoria JS no explican la sensación de lentitud en esta medición.

**Riesgo de estructura del visor:** el original PNG (hasta 497 KB, por ejemplo `conectar-usar-pantalla.png`) se descarga al abrir y en cada cambio, sin precarga de la captura siguiente. En móvil simulado, esto es lo que más se nota dentro de la guía.

### 5.2 SMTP: flujos, qué bloquea y qué no

**Clasificación de los envíos** (verificado con `grep` sobre `backend/app`):

| Flujo | Ubicación | Modo | ¿Bloquea la respuesta HTTP? |
|---|---|---|---|
| Registro local: correo de verificación | `auth.py:212` → `_sendVerificationEmail` (`auth.py:230`) | sincrónico (después del commit) | **Sí** |
| Reenvío de verificación | `auth.py:295`, envío en `auth.py:321` | sincrónico | **Sí** |
| Solicitud de eliminación de cuenta | `accountDeletion.py:249` (`requestDeletion`) | sincrónico (después del commit) | **Sí** |
| Código para cambiar contraseña | `passwordChangeCode.py:103` (`requestCode`), invocado desde `platform.py:537` | sincrónico (después del commit) | **Sí** |
| Recuperación de MFA (código por correo) | `mfaRecovery.py:164` (`_issueAndSendCode`) | sincrónico (después del commit) | **Sí** |
| Invitación de moderador / reinvitación / alta de primer administrador | `platform.py:291, 317, 779, 908` → `_sendInvitation` (`platform.py:199`) | sincrónico (después del commit) | **Sí** |
| Restablecimiento de contraseña de moderador y de plataforma | `platform.py:360, 494` → `_sendResetLink` (`platform.py:478`) | sincrónico (después del commit) | **Sí** |
| Consulta de contacto público (2 correos) | `contact.py:80-81` y `contact.py:45`, invocado desde `api/v1/contact.py:29` con `run_in_threadpool` | sincrónico, con una conexión compartida | **Sí** (fuera del event loop, pero dentro de un hilo del pool) |
| Consulta de soporte institucional | `institutionSupport.py:49` | sincrónico, **con transacción de BD abierta** | **Sí**, y retiene una conexión del pool |
| Aviso de inicio de sesión | `auth.py:92` | segundo plano | No |
| Alertas de seguridad, MFA, grupos, institución, plataforma, ciclo de vida, pacientes, reasignaciones | `mfa.py:31`, `securityMonitor.py:166`, `adminAccessAlerts.py:142`, `group.py`, `institution.py`, `platform.py` (varios), `institutionPatients.py`, `accountLifecycle.py`, `accountGrace.py`, `profileTransfers.py` | segundo plano (`sendEmailEventInBackground`) | No (usan el mismo pool de 2 hilos) |
| Notificaciones de usuario y confirmaciones de resultados | `notifications.py:98`, `userNotifications.py:378`, `resultEmailConfirmation.py:64`, `measurement.py:1109` | segundo plano (`runInBackground`) | No |

**Fases de un envío** (medido, sección 4.2): en una conexión nueva, un envío consume **cuatro grupos de comandos** (apertura y EHLO, STARTTLS con handshake, EHLO y AUTH, y MAIL/RCPT/DATA), además del QUIT. Con 150 ms de RTT, cada grupo suma ≈300 ms y el total es ≈1,2 s por correo.

**Qué operaciones bloquean:** todas las listadas como «Sí» en la tabla anterior. El tiempo de bloqueo depende del servidor SMTP: 1–2 s con un servidor sano y latencia normal; **20 s** por intento con un servidor caído (`SMTP_TIMEOUT_SECONDS = 20`, `sender.py:17`); **más** si el servidor responde lento en cada paso, porque el timeout aplica por operación de socket y no al envío completo (**HIPÓTESIS NO VERIFICADA**: sería necesario un servidor que responda gota a gota para confirmarlo).

**Qué ya funciona en segundo plano:** los avisos de seguridad y de actividad, las notificaciones y las confirmaciones de resultados. **Pero** el pool de segundo plano tiene dos hilos sin límite de cola (`email.py:74`), y un servidor lento o caído los deja ocupados: 30 avisos tardan 17,7 s en vaciarse con 150 ms por comando, y con timeouts de 20 s el throughput cae a una fracción de correo por segundo. Los avisos encolados se pierden si el proceso se reinicia.

**Conclusión del análisis de correo:** el problema no es el render (≈3 ms) ni la construcción del mensaje; es la **espera de red dentro de la petición HTTP** en los flujos sincrónicos, y la falta de límites y persistencia en la cola de segundo plano.

---

## 6. Problemas confirmados frente a hipótesis

### 6.1 Confirmados por medición

- **AUD-01:** `/ayuda` responde 301 → `/ayuda/` → 403 con la plantilla de Nginx del repositorio (Nginx 1.24).
- **AUD-02:** un envío SMTP sincrónico cuesta ≈1,2 s con 150 ms por comando, y ≈20 s con servidor caído.
- **AUD-03:** 40 peticiones bloqueadas en un endpoint síncrono llevan a 5 s la latencia de un endpoint no relacionado; con `async` no hay efecto (modelo).
- **AUD-04:** la cola de segundo plano de 2 hilos tarda 17,7 s en vaciar 30 avisos (150 ms por comando).
- **AUD-05:** Argon2id satura en ≈12,3 verificaciones/s en 4 vCPU; 56 MB de RAM por operación concurrente (laboratorio).
- **AUD-13:** cambiar de pestaña en Ayuda cuesta 89 ms (escritorio) y 219 ms (móvil simulado), con ≈1 131 nodos.
- **AUD-14:** el chunk de la guía empieza a pedirse después de ejecutar el bundle de entrada en la cascada móvil.
- **AUD-15:** el CSS global se usa en 4,9 % en `/ayuda`.
- **AUD-16:** las capturas no tienen `Cache-Control` ni `Expires`.
- **AUD-17:** el visor descarga el original en cada apertura y cambio (móvil: 818 ms y 259 ms p50).
- **AUD-18:** retención de ≈25 nodos y 5–19 listeners por apertura de visor.
- **AUD-24:** una conexión compartida reduce 31 % el costo de dos correos del mismo flujo (150 ms y 50 ms por comando).
- **Descartados por medición:** render de correos (≈0,7–2,1 ms); scroll de Ayuda con jank; DOM excesivo; heap JS alto; CLS en scroll con rueda (0).

### 6.2 Confirmados por código

- **AUD-06:** `DB_MAX_CONCURRENT_CALLS=2` por defecto (`config.py:55`) y el semáforo en cada llamada al driver (`app/db/gate.py`, `app/db/session.py:52`). El tope es real; su efecto en producción no.
- **AUD-07:** `FK_Medicion_Perfil` sin índice líder por `idPerfilMedicion`; el índice más cercano es `IX_Medicion_estado_fin (estadoMedicion, fechaHoraFin) INCLUDE (idPerfilMedicion, fechaHoraInicio)` (`models/measurement.py:85`). Los listados usan `WHERE idPerfilMedicion = ?` (`measurement.py:702-707`, `_history`).
- **AUD-08:** `institutionIndicators` (`measurement.py:1011-1012`) carga todas las filas de mediciones completadas de la institución sin ventana y las promedia en Python.
- **AUD-09:** `_checkPeriod` (`measurement.py:971`) valida solo que `hasta ≥ desde`; el rango no tiene tope y `buildStatistics` (`measurement.py:833`) carga todas las filas.
- **AUD-10:** `_list` (`auditQuery.py:922`, `COUNT` sobre todo el ámbito filtrado), `_summary` (seis agregados, más `GROUP BY` por institución en `auditQuery.py:969`) y `_moduleCountsQuery` (`auditQuery.py:939`) no tienen ventana por defecto: `FILTER_DEFAULTS` (`auditQuery.py:134`) define `desde=None` y `hasta=None`.
- **AUD-11:** `technicalAudit.purgeExpired` (`technicalAudit.py:48`) ejecuta `DELETE` sin lotes; se invoca desde `measurementLifecycle.sweep` (`measurementLifecycle.py:78-89`) cada 60 s en cada réplica.
- **AUD-12:** 9 bucles de polling; sin pausa con pestaña oculta en `LiveAcquisition.jsx:44`, `useDeviceReadiness.js:34`, `useDeviceStatus.js:30`, `MeasurementPanel.jsx:223` y `:231`, `PersonalDashboard.jsx:190` y `MeasurementHistory.jsx:88`. Con pausa en `useIncomingNotifications.js:43` y `useNotificationList.js:60,79`.
- **AUD-20:** un proceso uvicorn (`backend/Dockerfile:78`); límites de producción sin dimensionar con datos; `lifecycle` y `notifications` sin límites (`compose.prod.yaml`).
- **AUD-21:** `institutionSupport.requestSupport` lee con `db.get` y `scalar` antes de la línea 49, envía el correo en esa línea y recién después registra y hace `commit`: la conexión queda ocupada durante el SMTP.
- **AUD-22:** `google/oauth.py:49-58` (cliente sin timeout explícito) y `oauth.py:105-122` (People API).
- **AUD-23:** `Medicion.idMedicion` tiene `DEFAULT NEWID()` en el esquema v5, con clave agrupada `PK_Medicion`; `Auditoria` usa `NEWSEQUENTIALID()`.

### 6.3 Hipótesis no verificadas

- **AUD-19:** las capturas sin `width`/`height` producen CLS en redes lentas. En la prueba de rueda no se midió CLS (0), pero no se probó con red lenta ni con viewport móvil.
- **Timeout SMTP por operación:** un servidor que responde gota a gota podría bloquear un hilo más de 20 s por correo (sección 5.2).
- **Causa de la retención en el visor (AUD-18):** posiblemente referencias en el cierre del componente o en React; no identificada.
- **Límite OOM de Argon2 en el contenedor real (AUD-05):** estimado en 15–16 simultáneas a partir de RSS de laboratorio; no verificado.
- **Efecto del semáforo en pyodbc (AUD-06):** el código lo justifica con mediciones de una versión previa; no se reutilizaron esos números y no se reprodujo aquí.
- **Impacto de la purga sin lotes (AUD-11):** depende del volumen de `AuditoriaTecnicaMedicion`, que no se conoce.

### 6.4 No evaluados

Ver la tabla de la sección 4.6: SQL Server en ejecución, contención de pyodbc, OOM en contenedor, hardware HP, Nginx 1.30, SMTP real, Google OAuth y las pantallas autenticadas.

---

## 7. Soluciones propuestas (sin implementar)

Cada hallazgo indica ubicación, síntoma y causa, evidencia, impacto, solución, riesgos y pruebas. **Ninguna solución está implementada.**

### AUD-01 — `/ayuda` responde 403 al cargarse directamente (P0)

- **Ubicación:** `docker/nginx/default.conf.template:188` (`try_files $uri $uri/ /index.html;`), y la carpeta `frontend/public/ayuda/` que se copia a `dist/ayuda/`. La ruta se define en `frontend/src/App.jsx:211` y el enlace en `frontend/src/components/Navbar.jsx:86`.
- **Síntoma:** al cargar `/ayuda` (o recargar la página, o compartir el enlace) el usuario ve «403 Forbidden». La navegación interna desde la barra funciona porque no hace petición al servidor.
- **Causa confirmada:** Nginx encuentra el directorio `ayuda/` del build, redirige a `/ayuda/` y, al no existir `index.html` dentro, responde 403 en lugar de caer en la SPA.
- **Evidencia:** `mediciones/nginx_rutas.txt` (301 → 403); `/app/ayuda` y `/consejos` responden 200.
- **Impacto:** alto para quien entra por enlace directo o recarga; el sitemap no lista `/ayuda`.
- **Solución recomendada (elegir una):**
  1. Agregar a la plantilla una ubicación exacta: `location = /ayuda { try_files /index.html =404; }` y `location = /ayuda/ { try_files /index.html =404; }`.
  2. Renombrar la carpeta pública de capturas (por ejemplo `public/guia-capturas/`) y actualizar `GuiaVisual.jsx:66` (``const src = `/ayuda/${captura}` ``) y la ruta de la miniatura en la misma función, además de los scripts de captura que generan `public/ayuda/`.
  La opción 2 elimina la colisión de raíz; la opción 1 es un cambio de una sola línea de Nginx.
- **Riesgo funcional:** bajo. Cambiar el nombre de la carpeta exige actualizar todas las referencias; hay que revisar `helpCaptures.test.jsx`.
- **Riesgo de seguridad:** ninguno nuevo. No cambia cabeceras ni controles.
- **Pruebas de regresión:** matriz de `curl` (`/ayuda`, `/ayuda/`, `/app/ayuda`, `/consejos`, `/assets/...`, `/ayuda/...png` y `/ayuda/miniaturas/...webp`) con códigos esperados; prueba de Playwright de carga directa de `/ayuda` (sin interceptar), y `helpCaptures.test.jsx`.

### AUD-02 — Envío sincrónico de correo dentro de peticiones HTTP (P1)

- **Ubicación:** los 9 flujos de la sección 5.2 (`auth.py:212, 321`; `accountDeletion.py:249`; `passwordChangeCode.py:103`; `mfaRecovery.py:164`; `platform.py:291, 317, 360, 494, 779, 908`; `contact.py:80-81`; `institutionSupport.py:49`).
- **Síntoma:** la petición espera el SMTP (1–2 s normal; 20 s con servidor caído).
- **Causa:** el envío se invoca con `sendEmailEvent` (sincrónico) y no con `sendEmailEventInBackground`, a diferencia de otros flujos. Algunos devuelven `sent` al cliente (`CORREO_NO_ENVIADO` o `confirmacionEnviada: false`).
- **Solución recomendada:** pasar cada flujo a una cola persistente (tabla de salida o *outbox* con estado `PENDIENTE/ENVIADO/FALLIDO` y reintentos) procesada por un worker dedicado. La respuesta HTTP confirma que el envío quedó **registrado**, no que salió. Para los flujos que hoy informan el fallo al usuario, la respuesta cambia a «se encoló» y el estado se consulta después. Alternativa de corto plazo: seguir en segundo plano con cola acotada (AUD-04).
- **Riesgo funcional:** medio. Los textos y códigos de error de los endpoints cambian (por ejemplo, `CORREO_NO_ENVIADO` deja de existir en el flujo de reenvío). Requiere revisar el frontend, que muestra esos mensajes.
- **Riesgo de seguridad:** medio. Mantener **respuestas idénticas** para cuentas existentes e inexistentes (evitar enumeración por tiempo o por mensaje) y no reducir el rate limit de los endpoints. El contenido del correo no cambia.
- **Pruebas de regresión:** tests de integración de cada flujo con la respuesta esperada; test de equivalencia de respuestas para cuenta inexistente y existente; prueba de caída de SMTP (la petición responde en < 1 s); verificación de que cada correo se envía una vez (sin duplicados por reintento); revisión de la auditoría (`registerEvent`) de cada flujo.

### AUD-03 — Threadpool agotado por endpoints síncronos bloqueados por SMTP (P1)

- **Ubicación:** endpoints `def` de `api/v1/*` (264 en total); `app/main.py:64` (`/healthz` síncrono).
- **Síntoma:** con 40 peticiones bloqueadas, un endpoint no relacionado tarda 5 s; con 80, 11 s. `/healthz` también queda bloqueado, así que el healthcheck (`timeout: 5s`, `retries: 3`) puede marcar el contenedor como *unhealthy*. Docker no lo reinicia automáticamente porque la política es `unless-stopped`.
- **Causa confirmada:** los hilos del threadpool (40) quedan ocupados esperando SMTP.
- **Solución recomendada:** (a) resolver AUD-02 para quitar la espera SMTP de las peticiones; (b) mientras tanto, limitar la concurrencia de SMTP con un semáforo (por ejemplo, 4) y rechazar con 503 cuando esté lleno; (c) pasar `/healthz` a `async def` para que no dependa del threadpool. No aumentar el tamaño del threadpool sin medir: solo ocultaría el problema.
- **Riesgo funcional:** bajo para (b) y (c). Con (b), los envíos rechazados por saturación deben informarse igual que un fallo de SMTP.
- **Riesgo de seguridad:** ninguno nuevo; no cambia autenticación ni límites.
- **Pruebas de regresión:** el modelo de `pool_model.py` como prueba automática; prueba con SMTP de laboratorio caído (`blackhole`) y con 40 peticiones de registro; verificación de que `/healthz` responde con SMTP bloqueado; prueba de carga en staging con la mezcla real de endpoints.

### AUD-04 — Cola de correo en segundo plano sin límite ni persistencia (P2)

- **Ubicación:** `services/email.py:74` (`ThreadPoolExecutor(max_workers=2)`) y `services/email.py:228` (`sendEmailEventInBackground`).
- **Síntoma:** 30 avisos tardan 17,7 s con 150 ms por comando; con servidor caído, la cola crece sin límite en memoria; al reiniciar el backend se pierden los avisos pendientes.
- **Causa confirmada:** dos hilos, cola ilimitada y sin persistencia.
- **Solución recomendada:** (a) corto plazo: cola acotada con métrica de profundidad y descarte registrado; (b) mediano plazo: la misma tabla de salida de AUD-02, procesada por el worker `notifications` que ya existe en `compose.yaml`.
- **Riesgo funcional:** medio. Los avisos de seguridad no deben descartarse; la prioridad de cola debe reflejar la categoría (`highPriority`, `securityNotice`, ya presentes en `eventTypes.py`).
- **Riesgo de seguridad:** medio. Un aviso de seguridad perdido es un riesgo real; la persistencia es el requisito.
- **Pruebas de regresión:** prueba de vaciado con 1 000 avisos y SMTP de laboratorio; prueba de reinicio (no pierde avisos encolados); prueba de prioridad.

### AUD-05 — Argon2id sin límite de concurrencia (P1)

- **Ubicación:** `core/security.py:44-47` (parámetros fijados por H-12, no modificar sin aprobación); `verifyPassword` en login y en `auth.py:541, 584, 695`.
- **Síntoma:** con 32 inicios simultáneos, p95 de 3,5 s; con ≈15 o más, riesgo de agotar la memoria del contenedor de 1 GB.
- **Causa confirmada:** cada verificación reserva 64 MiB; no hay semáforo que limite las simultáneas.
- **Solución recomendada:** semáforo global por proceso para `verifyPassword` y `hashPassword` (por ejemplo, `max(1, cpu_limit)` a 2×; medir), con espera acotada y respuesta 503 con `Retry-After` cuando se agota. **No cambiar `ARGON2_*`**: requiere decisión de seguridad expresa.
- **Riesgo funcional:** bajo; un inicio puede demorar más en pico o recibir 503.
- **Riesgo de seguridad:** el semáforo no debe servir para evitar el rate limit por cuenta ni por IP; la espera en cola no debe permitir que un atacante bloquee el inicio de usuarios legítimos más de lo necesario.
- **Pruebas de regresión:** escalera de inicios simultáneos en contenedor de 1 GB (ver sección 4.6); prueba de que `verifyPassword` devuelve el mismo resultado; prueba de 503 con `Retry-After`; revisión de OWASP para la política de rate limit.

### AUD-06 — Tope de 2 llamadas simultáneas al driver (P1, medir antes de cambiar)

- **Ubicación:** `backend/app/core/config.py:55` (`DB_MAX_CONCURRENT_CALLS: int = 2`), `backend/app/db/gate.py` (semáforo y `GatedCursor`), `backend/app/db/session.py:52`.
- **Síntoma:** en el modelo, el techo queda en ≈388 ejecuciones/s frente a ≈1 554 sin tope; en producción, el efecto depende de SQL Server y no se midió.
- **Causa:** tope deliberado para evitar contención de pyodbc. El código afirma que el beneficio viene de una medición previa, que aquí no se reutilizó.
- **Solución recomendada:** no cambiar el valor a ciegas. Medir en staging con SQL Server real los valores 0, 2, 4 y 8, con el mismo flujo de carga, y comparar throughput, p95 y CPU del proceso. Solo cambiar si el resultado lo justifica.
- **Riesgo funcional:** ninguno si solo se mide; alto si se cambia y se reabre la contención (throughput cae o la CPU del proceso sube).
- **Pruebas de regresión:** medición comparativa reproducible; prueba de que el semáforo no se anida ni produce interbloqueo (ya cubierto por diseño, verificar con `pytest`).

### AUD-07 — Índices para filtros por paciente en `Medicion` (P1, validar con DBA)

- **Ubicación:** `database/reference/GlucoLume_DB_v5.sql` (`Medicion`, `FK_Medicion_Perfil`, `PK_Medicion`); `backend/app/models/measurement.py:85-86`; consultas en `measurement.py` (`_history` ≈702, `buildStatistics` 833, `_evolution` 924, `institutionIndicators` 1011).
- **Síntoma esperado:** listados, estadísticas y evolución por paciente escanean el historial de todos los pacientes cuando crece la tabla.
- **Causa probable:** no hay índice que empiece por `idPerfilMedicion`. **HIPÓTESIS hasta confirmar el plan.**
- **Solución recomendada:** en staging, obtener el plan actual con Query Store para las consultas de historial; si confirma el escaneo, proponer un índice del tipo `(idPerfilMedicion, estadoMedicion, fechaHoraInicio) INCLUDE (...)`. El DDL lo aplica un administrador (la cuenta de la aplicación no tiene permisos de DDL, según `schemaCompat.py`).
- **Riesgo funcional:** ninguno en el resultado; el índice aumenta el costo de escritura de `Medicion`.
- **Riesgo de seguridad:** ninguno nuevo; el DDL debe seguir la política de cambios de esquema del proyecto.
- **Pruebas de regresión:** comparar planes antes y después; `SET STATISTICS IO` y Query Store; tiempo de inserción de `Medicion`; pruebas de `measurement` con el esquema actualizado.

### AUD-08 — Indicadores institucionales con todas las mediciones en memoria (P2)

- **Ubicación:** `measurement.py:1011-1012` (`institutionIndicators`), `_summary` (`_summary` de `measurement.py`).
- **Síntoma:** memoria y CPU crecientes con el volumen de la institución.
- **Solución recomendada:** calcular en SQL: `COUNT`, `AVG`, `MIN`, `MAX` y serie diaria con `GROUP BY` sobre `CONVERT(date, fechaHoraInicio)`, aplicando la misma regla de supresión de grupos pequeños (`patientAccess.suppressSmallGroup`).
- **Riesgo funcional:** bajo si los valores son idénticos (redondeo incluido).
- **Riesgo de seguridad / privacidad:** medio. La supresión de grupos pequeños debe mantenerse exactamente, porque evita identificar a una persona en un promedio.
- **Pruebas de regresión:** equivalencia de resultados entre la versión en memoria y la SQL con datos sintéticos; prueba de supresión con un paciente y con varios.

### AUD-09 — Rango explícito de estadísticas sin tope (P2)

- **Ubicación:** `measurement.py:971-978` (`_checkPeriod`), `buildStatistics` (`measurement.py:833`).
- **Síntoma:** una petición con `desde=2000-01-01` y `hasta=2099-12-31` carga todas las filas del rango.
- **Solución recomendada:** tope de 366 días en `_checkPeriod` con error `PERIODO_INVALIDO` y mensaje claro; o paginar la serie.
- **Riesgo funcional:** cambia el contrato de la API para rangos mayores a 366 días (hoy válidos). Requiere aviso al frontend.
- **Riesgo de seguridad:** ninguno; reduce el costo máximo por petición.
- **Pruebas de regresión:** rango de 366 días aceptado; 367 rechazado; rango de un año en institución con volumen.

### AUD-10 — Auditoría sin ventana por defecto (P2)

- **Ubicación:** `services/auditQuery.py` (`FILTER_DEFAULTS` línea 134; `_list`, `_summary`, `_moduleCountsQuery`).
- **Síntoma esperado:** cada carga de la pantalla recorre todo el historial del ámbito (`COUNT` y 6 agregados más los `GROUP BY`). **NO EVALUADO** con datos de volumen.
- **Solución recomendada:** ventana por defecto (por ejemplo, últimos 30 días) con indicador visible, paginación por *keyset* (`fechaHora`, `idAuditoria`) y total aproximado (`sys.partitions`) cuando no hay filtros; los agregados se calculan solo al pedir el resumen.
- **Riesgo funcional:** alto de negocio: cambia qué ve el operador por defecto. Requiere aprobación.
- **Riesgo de seguridad y cumplimiento:** medio. No debe ocultarse ningún evento: la exportación y los filtros explícitos deben seguir devolviendo el historial completo. La retención (`auditRetention.py`) no cambia.
- **Pruebas de regresión:** filtros explícitos devuelven el mismo resultado que antes; paginación sin duplicados ni huecos; exportación completa.

### AUD-11 — Purga de auditoría técnica sin lotes (P2)

- **Ubicación:** `services/technicalAudit.py:48`; `services/measurementLifecycle.py:78-89` (`sweep`); `services/maintenance.py` (loop cada 60 s).
- **Síntoma esperado:** con un backlog grande, el `DELETE` mantiene bloqueos e infla el log de transacciones. **NO EVALUADO** con volumen real.
- **Solución recomendada:** borrar en lotes (`DELETE TOP (5000)` en bucle con pausa) y mover la purga al servicio `lifecycle`, que ya existe, en lugar de la API.
- **Riesgo funcional:** bajo; la purga sigue cumpliendo el plazo.
- **Riesgo de seguridad:** ninguno; la retención no cambia.
- **Pruebas de regresión:** purga con 1 millón de filas sintéticas en staging; verificación de que no quedan eventos vencidos.

### AUD-12 — Polling con la pestaña oculta (P2)

- **Ubicación:** `LiveAcquisition.jsx:17,44` (3 s), `useDeviceReadiness.js:10,34` (5 s), `useDeviceStatus.js:11,30` (5 s), `MeasurementPanel.jsx:28,223,231` (3 s), `PersonalDashboard.jsx:46,190` (10 s), `MeasurementHistory.jsx:88` (60 s). Ya tienen pausa: `useIncomingNotifications.js:11,43` y `useNotificationList.js:60,79`.
- **Síntoma:** cada pantalla abierta consulta 12–20 veces por minuto, también con la pestaña en segundo plano.
- **Solución recomendada:** pausar cuando `document.visibilityState === 'hidden'` (como ya hacen dos hooks), con reanudación inmediata al volver; en las pantallas del dispositivo, evaluar reemplazar el polling por el stream SSE que ya existe (`/acquisition/telemetry/stream`).
- **Riesgo funcional:** bajo; al volver a la pestaña debe refrescarse de inmediato.
- **Riesgo de seguridad:** ninguno. El encabezado de segundo plano (`X-GlucoLume-Segundo-Plano`) sigue igual.
- **Pruebas de regresión:** prueba con `visibilitychange` simulado; las pantallas de medición siguen actualizando estados.

### AUD-13 — Re-montaje de la guía al cambiar de pestaña (P2)

- **Ubicación:** `frontend/src/pages/Account/help/HelpPage.jsx:137` (tabla de temas) y `:143` (listado de `Tema`); `components/Tabs.jsx`.
- **Síntoma:** 89 ms (escritorio) y 219 ms (móvil simulado) por cambio, con ≈1 131 nodos reemplazados.
- **Causa:** `pestana.temas.map(...)` remonta todos los temas al cambiar; no hay `memo` ni `content-visibility`.
- **Solución recomendada:** (a) `memo` por `Tema` con clave estable; o (b) mantener ambas pestañas montadas y ocultar la inactiva con `hidden`; o (c) `content-visibility: auto` con `contain-intrinsic-size` en `.help-topic`. La opción (c) es la de menor riesgo.
- **Riesgo funcional:** bajo. La opción (b) cambia el orden de foco y el DOM oculto; revisar accesibilidad (`aria-hidden`/`hidden`).
- **Riesgo de seguridad:** ninguno.
- **Pruebas de regresión:** `Help.test.jsx`; medición de cambio de pestaña con `bench_help.js` (antes y después); prueba de teclado (flechas, Inicio y Fin).

### AUD-14 — Cascada de carga de la guía (P2)

- **Ubicación:** `frontend/src/App.jsx:92-93` (lazy de `HelpPage` y `PublicHelpPage`), `vite.config.js` (`manualChunks`).
- **Síntoma:** el chunk de la guía empieza a pedirse ≈1 075 ms después de la petición del documento en móvil simulado, porque el router lo carga después del bundle de entrada.
- **Solución recomendada:** (a) `<link rel="modulepreload">` del chunk de `HelpPage` cuando la ruta es `/ayuda`, o `prefetch` desde la portada (corto plazo); (b) reducir `index-*.js` (163 KB sin comprimir) separando el código de inicio de sesión y del menú (mediano plazo).
- **Riesgo funcional:** bajo para (a); medio para (b) (orden de carga y errores de chunk tras un despliegue).
- **Riesgo de seguridad:** ninguno.
- **Pruebas de regresión:** cascada de carga con `help_extra.js` antes y después; `Help.test.jsx`; prueba de chunk faltante tras despliegue.

### AUD-15 — CSS global cargado en todas las pantallas (P2)

- **Ubicación:** `frontend/src/main.jsx:8` (`import './styles/global.css'`); el build genera `index-*.css` de 123 KB (22 KB gzip).
- **Síntoma:** CSS bloqueante en todas las pantallas, con 4,9 % de uso en `/ayuda`.
- **Solución recomendada:** medir la cobertura en las pantallas principales (NO EVALUADO fuera de Ayuda) y luego mover a cada pantalla su CSS (CSS por ruta) o purgar reglas no usadas con cuidado.
- **Riesgo funcional:** alto de regresión visual; la CSS global afecta a componentes compartidos.
- **Riesgo de seguridad:** ninguno.
- **Pruebas de regresión:** capturas visuales de todas las pantallas antes y después; `vitest`; revisión en modo oscuro (`prefers-color-scheme`).

### AUD-16 — Capturas de Ayuda sin política de caché (P3)

- **Ubicación:** `docker/nginx/default.conf.template:183-186`.
- **Síntoma:** cada visita revalida las capturas (solo `Last-Modified`).
- **Solución recomendada:** `expires 7d;` y `add_header Cache-Control "public, max-age=604800";` para `/ayuda/` y `/ayuda/miniaturas/`. Las capturas no tienen hash en el nombre: si cambian, deben renombrarse o el plazo debe ser corto.
- **Riesgo funcional:** imágenes desactualizadas si una captura cambia sin renombrarse.
- **Riesgo de seguridad:** ninguno.
- **Pruebas de regresión:** cabeceras con `curl`; prueba de que la guía muestra la captura nueva tras renombrarla.

### AUD-17 — Visor con descarga del original en cada cambio (P3)

- **Ubicación:** `frontend/src/pages/Account/help/GuiaVisual.jsx:107` (`<img className="help-visor-img" src={actual.src}>`).
- **Síntoma:** en móvil simulado, 818 ms al abrir y 259 ms por captura (p95 1,1 s).
- **Solución recomendada:** precargar la captura anterior y la siguiente cuando se abre el visor; ofrecer una variante WebP de 1 280 px (hoy el original es PNG de hasta 497 KB).
- **Riesgo funcional:** bajo.
- **Riesgo de seguridad:** ninguno.
- **Pruebas de regresión:** cambio de captura medido con `bench_help.js`; `helpCaptures.test.jsx`.

### AUD-18 — Retención de nodos y listeners en el visor (P3, causa no identificada)

- **Ubicación:** `GuiaVisual.jsx` (`VisorCapturas`, `PasoImagen`) y `components/Modal.jsx` (listeners de teclado, portal, `inert`).
- **Síntoma:** ≈25 nodos y 5–19 listeners por apertura, retenidos tras GC forzado.
- **Solución recomendada:** identificar la referencia retenida con un *heap snapshot* comparado (dos snapshots antes y después de 20 aperturas); luego corregir. Mientras tanto, el impacto es bajo (≈0,1 MB por 10 aperturas).
- **Riesgo funcional:** ninguno si solo se identifica.
- **Riesgo de seguridad:** ninguno. Cuidado con `inert` y el foco al cerrar.
- **Pruebas de regresión:** `leak_visor.js` antes y después; prueba de foco al cerrar (`Modal.test`).

### AUD-19 — Capturas sin dimensiones (P3, hipótesis)

- **Ubicación:** `GuiaVisual.jsx:78`.
- **Solución recomendada:** agregar `width` y `height` (los de cada WebP) a la miniatura; con `height:auto` el marco reserva espacio sin esperar la imagen.
- **Riesgo funcional:** ninguno.
- **Pruebas de regresión:** CLS con red móvil simulada y rueda real.

### AUD-20 — Capacidad del backend y límites de contenedor (P2)

- **Ubicación:** `backend/Dockerfile:78` (un proceso sin `--workers`); `compose.prod.yaml` (backend 2 CPU / 1 GB; `lifecycle` y `notifications` sin límites); `compose.yaml:68-74` (healthcheck).
- **Síntoma:** capacidad desconocida; se estima por la medición de Argon2 y el semáforo.
- **Solución recomendada:** medir primero (sección 4.6). Luego, agregar límites a `lifecycle` y `notifications` (bajo riesgo) y evaluar `--workers 2` solo si la RAM por proceso lo permite (cada proceso reserva su propio pool de SQLAlchemy y, si hay Argon2 concurrente, 64 MiB por operación).
- **Riesgo funcional:** bajo para límites; medio para `--workers` (duplica memoria, pools y tope del semáforo por proceso).
- **Riesgo de seguridad:** ninguno nuevo. Con varios procesos, el rate limit en memoria se separa por proceso; el de Redis (`RATE_LIMIT_REDIS_URL`) lo evita.
- **Pruebas de regresión:** prueba de carga en staging con la configuración propuesta; `docker stats` durante la prueba; prueba de rate limit con más de un proceso.

### AUD-21 — Conexión de BD ocupada durante el SMTP de soporte (P3)

- **Ubicación:** `services/institutionSupport.py:29-49`.
- **Solución recomendada:** registrar la consulta y hacer `commit` antes de enviar el correo; el envío pasa a segundo plano (AUD-02).
- **Riesgo funcional:** bajo; el mensaje de error del 503 debe mantenerse.
- **Pruebas de regresión:** `institutionSupport` tests; prueba de consulta exitosa con SMTP caído.

### AUD-22 — Timeouts de Google (P3)

- **Ubicación:** `integrations/google/oauth.py:49-58` (`_client`), `:105-122` (`_fetchPersonalData`, `fetchIdentity`).
- **Solución recomendada:** definir `timeout` explícito (por ejemplo, 5 s de conexión y 10 s de lectura) en el cliente de Authlib.
- **Riesgo funcional:** bajo; un timeout deja los datos personales sin informar, como ya ocurre en el error.
- **Pruebas de regresión:** prueba con Google simulado lento; registro sin People API.

### AUD-23 — Claves agrupadas `NEWID()` (P3)

- **Ubicación:** esquema v5 (`Medicion`, `NotificacionUsuario`, `AuditoriaTecnicaMedicion`, y otras 35 tablas con `NEWID()`).
- **Solución recomendada:** solo tras medir la fragmentación (`sys.dm_db_index_physical_stats`) en staging; luego, `NEWSEQUENTIALID()` para las tablas de alto volumen en una migración programada.
- **Riesgo funcional:** alto (migración de claves con referencias). Requiere ventana de mantenimiento y respaldo.
- **Riesgo de seguridad:** ninguno nuevo, pero los identificadores secuenciales son predecibles en parte; revisar que no se usen como secreto.
- **Pruebas de regresión:** migración en copia; verificación de referencias; medición de fragmentación antes y después.

### AUD-24 — Conexión SMTP no compartida entre flujos (P3)

- **Ubicación:** `integrations/email/sender.py:61-63` (`_open`) y `:101-104` (`_send`, conexión por correo).
- **Solución recomendada:** después de AUD-02, usar un pool pequeño de conexiones por worker de correo.
- **Riesgo funcional:** bajo. Riesgo de seguridad: conexiones reutilizadas deben reabrirse ante cualquier error (ya lo hace `SmtpSession`).
- **Pruebas de regresión:** `bench_smtp.py` con conexión compartida; prueba de reconexión tras fallo.

---

## 8. Riesgos y pruebas requeridas

### 8.1 Riesgos transversales

- **Cambios de contrato de API** (AUD-02, AUD-09): el frontend debe ajustarse en el mismo despliegue; los mensajes de error cambian.
- **Cambios de comportamiento visible** (AUD-10, AUD-13, AUD-15): requieren aprobación de negocio o revisión visual.
- **Cambios de esquema** (AUD-07, AUD-23): requieren un administrador de la base; la cuenta de la aplicación no tiene DDL.
- **Política de seguridad** (AUD-05, AUD-10, AUD-02): nada de lo propuesto cambia parámetros de Argon2, rate limits, controles de permisos ni la retención de auditoría. Cualquier cambio en esos puntos exige decisión expresa.
- **Auditoría y cumplimiento:** las correcciones de correo y auditoría no deben hacer que se pierdan eventos.

### 8.2 Pruebas requeridas antes de cualquier optimización

1. **Entorno de staging** con SQL Server 2022, Nginx, backend y frontend en contenedores con los límites de producción; datos sintéticos a volumen real (decenas de miles de mediciones y millones de filas de auditoría).
2. **Línea base** de los flujos de la sección 5 y de las pantallas principales, con `bench_help.js` y las pruebas de carga.
3. **Pruebas de regresión funcional** de cada flujo de correo (contenido, destinatarios, respuesta HTTP, auditoría).
4. **Prueba de SMTP caído y lento** (el sumidero de laboratorio con `blackhole` y retardo).
5. **Prueba de inicio de sesión masivo** en el contenedor de 1 GB (escalera de la sección 4.6).
6. **Prueba de Nginx**: matriz de rutas y cabeceras (AUD-01, AUD-16).
7. **Pruebas de frontend**: `vitest` (`Help.test.jsx`, `helpCaptures.test.jsx`), capturas visuales y accesibilidad de teclado.

---

## 9. Plan de optimización posterior a la exposición

Orden sugerido. Las estimaciones son de esfuerzo de desarrollo y prueba, sin medir. Los pasos se agrupan por riesgo.

### 9.1 Riesgo bajo

| Orden | ID | Acción | Esfuerzo estimado |
|---|---|---|---|
| 1 | AUD-01 | Corregir la ruta `/ayuda` en Nginx o renombrar la carpeta de capturas | 1–2 h |
| 2 | AUD-16, AUD-19 | Caché de capturas y dimensiones de la miniatura | 1 h |
| 3 | AUD-05 | Semáforo de Argon2 con 503 y `Retry-After` (sin tocar parámetros) | 0,5 día |
| 4 | AUD-03 (b, c) | Semáforo de SMTP y `/healthz` asíncrono | 0,5 día |
| 5 | AUD-11 | Purga de auditoría técnica en lotes, en el servicio `lifecycle` | 0,5 día |
| 6 | AUD-12 | Pausa de polling con la pestaña oculta | 1–2 días |
| 7 | AUD-13 (c) | `content-visibility` en los temas de la guía | 0,5 día |
| 8 | AUD-14 (a) | `modulepreload` del chunk de la guía | 0,5 día |
| 9 | AUD-21, AUD-22 | Cerrar la transacción antes del SMTP de soporte; timeouts de Google | 0,5 día |
| 10 | AUD-17 | Precarga de capturas vecinas en el visor | 1 día |
| 11 | AUD-20 (límites) | Límites de CPU y memoria para `lifecycle` y `notifications` | 1 h |

### 9.2 Riesgo medio

| Orden | ID | Acción | Esfuerzo estimado |
|---|---|---|---|
| 12 | AUD-02 | Pasar los 9 flujos sincrónicos a la cola persistente, con respuestas equivalentes | 3–5 días |
| 13 | AUD-04 | Cola acotada y persistente para avisos, con prioridad por categoría | 2–3 días |
| 14 | AUD-24 | Pool de conexiones SMTP por worker | 1–2 días |
| 15 | AUD-08 | Indicadores institucionales en SQL con supresión de grupos pequeños | 2–3 días |
| 16 | AUD-09 | Tope de 366 días en estadísticas | 0,5 día |
| 17 | AUD-10 | Ventana por defecto y paginación por keyset en auditoría (con aprobación de negocio) | 2–4 días |
| 18 | AUD-14 (b) | Reducir el bundle de entrada | 2–3 días |
| 19 | AUD-18 | Corregir la retención del visor (después de identificar la referencia) | 0,5–1 día |
| 20 | AUD-20 (`--workers`) | Evaluar más de un proceso, solo con medición | 1–2 días |

### 9.3 Riesgo alto

| Orden | ID | Acción | Esfuerzo estimado |
|---|---|---|---|
| 21 | AUD-06 | Cambiar `DB_MAX_CONCURRENT_CALLS`, solo si la medición en staging lo justifica | 1–2 días de medición |
| 22 | AUD-07 | Índice `Medicion` por paciente (DDL aplicado por DBA, con plan verificado) | 1–3 días |
| 23 | AUD-15 | CSS por pantalla o purga de CSS global | 3–5 días |
| 24 | AUD-23 | `NEWSEQUENTIALID()` en tablas de alto volumen (solo si la fragmentación lo justifica) | 2–4 días + ventana |

**Prerrequisito de todo el plan:** completar las mediciones de la sección 4.6 en staging (SQL Server, contenedor con límites, SMTP de prueba y servidor HP). Sin esas cifras, AUD-06, AUD-07, AUD-10, AUD-20 y AUD-23 no deben implementarse.

---

## Anexo: evidencias y reproducción

**Carpeta de evidencias** (no sensible; no incluye claves ni certificados): `docs/auditorias/evidencias/auditoria_master_2026-11-05/`

- `mediciones/` — resultados JSON y de texto (ver `mediciones/LEEME.md`).
- `scripts/` — scripts de medición. Requieren Chromium de Playwright, Node 22, Python 3.13 con `backend/requirements.txt` y `aiosmtpd`.

**Reproducción de la prueba de Ayuda** (sobre un build de producción servido por Nginx con la plantilla del repositorio):

```bash
cd frontend && VITE_API_BASE_URL=/ npx vite build
```

```bash
cd docs/auditorias/evidencias/auditoria_master_2026-11-05/scripts
REPS=5 DIST_INDEX=/ruta/al/dist/index.html node bench_help.js http://127.0.0.1:8080/ayuda ./salida_ayuda.json
```

**Reproducción de las mediciones de correo** (sumidero de laboratorio; no envía nada fuera de la máquina):

```bash
cd docs/auditorias/evidencias/auditoria_master_2026-11-05/scripts
python -I smtp_sink.py 8027 150 &
SCR=/ruta/con/pki python -I bench_smtp.py phases:8027:3
```

**Reproducción de Argon2:**

```bash
cd backend && python -I ../docs/auditorias/evidencias/auditoria_master_2026-11-05/scripts/bench_argon2.py
```

Los certificados de laboratorio (`pki/`) se generan con `openssl` en una carpeta fuera del repositorio y no se incluyen en la evidencia.
