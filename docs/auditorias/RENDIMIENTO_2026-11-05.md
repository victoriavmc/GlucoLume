# Auditoría integral de rendimiento de GlucoLume — 5 de noviembre de 2026

> **Estado:** diagnóstico. No se implementó ninguna corrección ni se modificó código funcional, base de datos, Docker, configuración de servidor ni se enviaron correos reales.
> **Exposición:** miércoles 11 de noviembre de 2026. Las soluciones de este documento quedan **pendientes de autorización expresa**.

---

## 1. Identificación del estado auditado

| Dato | Valor |
|---|---|
| Repositorio | `victoriavmc/GlucoLume` (GitHub) |
| Rama auditada | `claude/amazing-clarke-p75731` |
| Commit SHA | `933d84c67834a6515a1ff161518b202420f3a664` |
| Fecha del commit | 5/11/2026 17:17:49 +0000 — «Las señales ya analizadas se ocultan del panel de seguridad» |
| Fecha de revisión | 5/11/2026 |
| Árbol de trabajo | limpio al inicio (sin cambios sin confirmar) |
| Historial | 52 commits en la rama |

**Tratamiento de la documentación anterior.** `docs/RENDIMIENTO.md`, `docs/PENDIENTES.md`, `PR_rendimiento.md` y los informes de `docs/evidencias/rendimiento*` se leyeron **solo como historial**. Sus métricas, prioridades y pendientes no se reutilizan. Algunas afirmaciones de esos documentos se verificaron de nuevo contra el código vigente, como trazabilidad (ver §6.3). Cada hallazgo de este informe se basa en código, archivos o mediciones hechas en esta auditoría.

---

## 2. Alcance y metodología

### 2.1 Alcance

- **Frontend (React 19 + Vite 6):** carga de la pantalla de Ayuda (caso obligatorio A), cambio de pestañas, desplazamiento, visor de capturas, tamaño de bundles, polling por pantalla y memoria.
- **Backend (FastAPI + SQLAlchemy, Python 3.14 en imagen):** flujos de correo (caso obligatorio B), endpoints síncronos y asíncronos, operaciones de CPU (hash de contraseñas), streams SSE, tope de llamadas al driver.
- **SQL Server:** esquema de referencia v5 y scripts de actualización (índices, FK, consultas costosas por lectura de código).
- **Infraestructura:** `compose.yaml`, `compose.prod.yaml`, `Dockerfile` de backend y frontend, plantilla de Nginx.
- **Integraciones:** SMTP (envío, latencia, tamaño de mensaje), Google OAuth (lectura de código).

### 2.2 Entorno de medición (laboratorio, no servidor de producción)

| Recurso | Valor |
|---|---|
| Host | contenedor de laboratorio, 4 vCPU, 16 GB RAM |
| Navegador | Chromium preinstalado + Playwright (Node 22.23.4) |
| Frontend | build de producción propio (`vite build`, VITE_API_BASE_URL=/) servido en `localhost` |
| Backend (micro-mediciones) | Python 3.13 local con las dependencias fijadas del `requirements.txt` (hash-locked) |
| Base de datos | **No disponible**: no hay SQL Server ni daemon de Docker en el laboratorio |
| SMTP | **No se usó ningún servidor real.** Sumidero local aiosmtpd con STARTTLS y certificado de prueba |

### 2.3 Restricciones respetadas

- No se accedió al servidor HP ni a su base, ni se ejecutaron cargas contra producción.
- No se enviaron correos reales: el SMTP usado es un sumidero local y las credenciales son valores ficticios (`lab-no-real`).
- No se modificó el repositorio más allá de este documento y de sus evidencias.

### 2.4 Clasificación de resultados

- **CONFIRMADO POR MEDICIÓN:** obtenido con una medición reproducible en este laboratorio (ver scripts en `docs/auditorias/evidencias/rendimiento_2026-11-05/`).
- **CONFIRMADO POR CÓDIGO:** el comportamiento está en el código o en el esquema, pero su costo real no se midió.
- **HIPÓTESIS NO VERIFICADA:** plausible según el código; falta la evidencia.
- **NO EVALUADO:** no fue posible medirlo en este entorno (se explica la limitación).

### 2.5 Pruebas de carga y datos

Todas las mediciones de navegador usan datos estáticos del build. Las respuestas de la API de sesión se interceptan con un 401 inmediato para no depender de un backend inexistente en el laboratorio.

---

## 3. Matriz de hallazgos priorizados

Prioridad: **P1** = bloquea al usuario o expone riesgo de disponibilidad; **P2** = degrada la experiencia o escala mal; **P3** = mejora menor o depende de volumen.

| ID | Área | Ubicación | Hallazgo | Clasificación | Prioridad |
|---|---|---|---|---|---|
| H-01 | Ayuda | `frontend/src/pages/Account/help/GuiaVisual.jsx` (`PasoImagen`), `frontend/public/ayuda/` | Miniaturas con el PNG a resolución completa (hasta 1315 px; 56 archivos > 1000 px) mostradas a ≤ 420 px CSS. 22 PNG (≈1,59 MB) se piden al abrir la pantalla. | CONFIRMADO POR MEDICIÓN (conteo y bytes); impacto móvil: ver §4.3 | P2 (sube a P1 si la medición móvil lo confirma) |
| H-02 | Ayuda / Nginx | `docker/nginx/default.conf.template` (bloque regex de estáticos) | Los PNG de `/ayuda/` no tienen `Cache-Control` ni `expires` (solo `/assets/` tiene 1 año). Se revalidan en cada visita. | CONFIRMADO POR CÓDIGO | P2 |
| H-03 | Ayuda | `helpContent.js` + `HelpPage` | Chunk de Ayuda de 65,9 kB (19,2 kB gzip), que incluye todo el texto de la guía. Se descarga solo al visitar la ruta. | CONFIRMADO POR MEDICIÓN (build) | P3 |
| H-04 | Correo | `services/auth.py` (`registerLocal` → `_sendVerificationEmail`; `resendVerification`) | El alta de cuenta y el reenvío de verificación esperan la conexión y el envío SMTP dentro de la petición. | CONFIRMADO POR CÓDIGO | P1 |
| H-05 | Correo | `services/contact.py` (`sendContactMessage`, `_sendConfirmation`) | El formulario de contacto envía **dos correos en serie** dentro de la petición (aviso a GlucoLume y confirmación al remitente), cada uno con su propia sesión SMTP. | CONFIRMADO POR CÓDIGO; latencia: §4.4 | P1 |
| H-06 | Correo | `services/mfaRecovery.py:164`, `services/accountDeletion.py:249`, `services/passwordChangeCode.py:103`, `services/platform.py:200/479`, `services/resultEmailConfirmation.py:60` | Otros flujos también envían de forma síncrona (código MFA, eliminación de cuenta, código de cambio de contraseña, invitación y restablecimiento de administradores, confirmación de resultados). | CONFIRMADO POR CÓDIGO | P1 |
| H-07 | Correo | `integrations/email/sender.py` y `services/email.py` | Cada correo adjunta `bannerCorreoGlucoLume.png` de **1,35 MB** embebido como imagen `cid:`. El mensaje completo pesa ~1,8 MB en base64. | CONFIRMADO POR CÓDIGO y medición del archivo; tamaño MIME: §4.4 | P1 |
| H-08 | Correo | `integrations/email/sender.py` (`_send`) | Una conexión SMTP nueva por correo: TCP, handshake TLS, EHLO ×2, STARTTLS, AUTH, MAIL, RCPT, DATA, QUIT. Sin reutilización de conexión. | CONFIRMADO POR CÓDIGO; comandos medidos: §4.4 | P2 |
| H-09 | Correo | `services/email.py` (`_executor = ThreadPoolExecutor(max_workers=2)`) | Pool de 2 hilos con cola **sin límite** y sin persistencia. Al eliminar una institución se encola un correo por miembro. Una caída del proceso pierde la cola. | CONFIRMADO POR CÓDIGO | P2 |
| H-10 | Correo | `services/institution.py:1424` (cierre de institución) y `services/platformInstitutions.py:94` | Bucles que encolan un correo por destinatario dentro de la transacción de negocio. | CONFIRMADO POR CÓDIGO | P2 |
| H-11 | SQL Server | `database/reference/GlucoLume_DB_v5.sql` (tabla `Medicion`) y `services/measurement.py:_history` | `Medicion` tiene FK a `PerfilMedicion` (`FK_Medicion_Perfil`) pero **ningún índice con `idPerfilMedicion` como clave**. El historial, la analítica de pacientes y los datos de grupo filtran por esa columna. | CONFIRMADO POR CÓDIGO (esquema); plan de ejecución: NO EVALUADO | P1 |
| H-12 | Backend | `services/measurement.py:_history` (`_semaphoreOf` → `glucoseReference.build`) | N+1: por cada medición completada de glucosa de la página se hacen 2 consultas (reglas de matriz y `ruleIdOf`). | CONFIRMADO POR CÓDIGO | P2 |
| H-13 | SQL Server | `services/dashboard.py` (dashboard institucional, ~l. 655–700) | Más de 10 consultas que repiten la subconsulta `performedAll` (join con `Auditoria` filtrada por `idRelacionado`, sin índice). | CONFIRMADO POR CÓDIGO; plan: NO EVALUADO | P2 |
| H-14 | Concurrencia | `db/gate.py`, `core/config.py` (`DB_MAX_CONCURRENT_CALLS = 2`) | Cada proceso ejecuta como máximo 2 llamadas simultáneas al driver. Una consulta lenta ocupa un slot y retrasa a las demás (bloqueo por cabeza de línea). | CONFIRMADO POR CÓDIGO; simulación: §4.6 | P1 |
| H-15 | CPU / memoria | `core/security.py` (Argon2id `m=64 MiB, t=3, p=4`), `services/auth.py:_passwordReuseError` | Cada verificación consume 64 MiB y CPU. Un cambio de contraseña ejecuta 5 operaciones Argon2 en serie. Con un límite de 512 MB de la API, la concurrencia de logins puede agotar la memoria. | CONFIRMADO POR CÓDIGO; medición: §4.5 | P1 |
| H-16 | Infraestructura | `compose.yaml` (`backend`: `cpus 1.0`, `memory 512M`), `Dockerfile` (un proceso Uvicorn, sin `--workers`) | Límites ajustados y un único proceso. CPU y memoria son el techo del backend. La versión de producción sube a 2 CPU y 1 GB. | CONFIRMADO POR CÓDIGO | P2 |
| H-17 | Infraestructura | `compose.yaml` (`db`: `MSSQL_PID` por defecto `Express`) | La edición Express limita memoria del buffer pool y núcleos. El valor es configurable y la edición instalada en el servidor no se verificó. | HIPÓTESIS NO VERIFICADA | P2 |
| H-18 | Streams SSE | `api/v1/acquisition.py:stream`, `api/v1/telemetry.py:telemetryStream`, `api/streams.py` | Cada stream despierta cada 0,2 s en el event loop único; tope de 300 streams globales. Revalida la sesión en la base cada 30 s. | CONFIRMADO POR CÓDIGO; costo: HIPÓTESIS (cálculo en §4.7) | P3 |
| H-19 | Paginación | `services/auditQuery.py:924`, `services/measurement.py:699`, `services/institutionPatients.py:334` | `OFFSET` en tablas que crecen; el costo de la página crece con la profundidad. | CONFIRMADO POR CÓDIGO | P3 |
| H-20 | Búsqueda | `services/auditQuery.py:166`, `services/institutionPatients.py:305`, `services/device.py:288` | `ILIKE '%término%'` sobre varias columnas (no sargable). Acotado por institución y página, pero escala con el volumen. | HIPÓTESIS NO VERIFICADA (depende del volumen) | P3 |
| H-21 | Frontend polling | `MeasurementPanel.jsx` (3 s), `LiveAcquisition.jsx` (3 s), `useDeviceStatus.js` (5 s), `useDeviceReadiness.js` (5 s), `PersonalDashboard.jsx` (10 s), `useIncomingNotifications.js` (30 s), `MeasurementHistory.jsx` (60 s) | Polling por pestaña abierta. Cada pantalla de medición genera varias peticiones por segundo mientras está visible. | CONFIRMADO POR CÓDIGO; carga por usuario: §4.8 | P3 |
| H-22 | Frontend | toda la aplicación | No hay `React.memo` en ningún componente (0 usos). Las actualizaciones de estado por polling re-renderizan el árbol de la pantalla. | HIPÓTESIS NO VERIFICADA | P3 |
| H-23 | Administración | `services/platform.py`, `services/platformDashboard.py:systemStatus` | Cada carga del panel de estado abre dos conexiones TCP (SMTP y Google) con timeout de 2 s, dentro de la petición. | CONFIRMADO POR CÓDIGO | P3 |
| H-24 | Integraciones | `integrations/google/oauth.py` | Google OAuth usa `authlib` asíncrono (no bloquea el loop), pero añade al menos dos llamadas HTTPS externas por inicio de sesión. | NO EVALUADO (sin acceso a Google desde el laboratorio) | P3 |

Diferencias de estado respecto de documentación anterior se detallan en §6.3.

---

## 4. Resultados de mediciones y limitaciones

### 4.1 Pantalla Ayuda — escritorio (1366×768, DPR 1, sin limitación)

Build de producción en `localhost`, caché fría por corrida, n = 10 corridas por condición. Fuente: `docs/auditorias/evidencias/rendimiento_2026-11-05/ayuda-results.jsonl`, resumen con `resumen.py`.

| Métrica | p50 | p95 |
|---|---|---|
| Apertura hasta primera figura (ms) | 466,5 | 476,8 |
| FCP (ms) | 102 | 122,2 |
| LCP (ms) | 452 | 472,4 |
| PNG pedidos al abrir (n) | 22 | 22 |
| Bytes PNG al abrir | 1,59 MB | 1,59 MB |
| Cambio de pestaña a Institucional (ms, hasta 2 cuadros) | 36,8 | 44,1 |
| Cambio de pestaña a Cliente (ms) | 28,7 | 39,9 |
| Cuadro p95 al desplazar (ms) | 16,7 | 16,8 |
| Cuadros > 50 ms al desplazar (n) | 0 | 0,5 |
| PNG pedidos durante el desplazamiento (n) | 8 | 8 |
| Visor ampliado: abrir y decodificar (ms) | 25,5 | 31 |
| Nodos DOM al abrir | 1235 | 1235 |
| Píxeles decodificados estimados (MB) | 51,8 | 51,8 |
| Heap JS (MB) | 9,5 | 9,5 |

**Lectura.** En escritorio, la pantalla **no muestra bloqueo medible**: el cambio de pestaña tarda ≈ 37 ms (por debajo de lo perceptible como demora), el desplazamiento mantiene cuadros de ≈ 16,7 ms (60 fps) y el visor abre en ~25 ms. El costo real es de memoria y de bytes: 22 PNG se descargan antes de desplazarse y las capturas, decodificadas a píxeles completos, ocupan unos 52 MB estimados.

### 4.2 Pantalla Ayuda — controles de causa (escritorio)

| Condición | Resultado |
|---|---|
| Base (PNG originales) | ver §4.1 |
| Sin imágenes (`/ayuda/*.png` abortados) | apertura p50 463,5 ms; FCP p50 110 ms; cambio de pestaña p50 38,7 ms; sin PNG; visor no carga la captura (espera de 15 s por diseño del banco) |
| Capturas WebP ≤ 840 px (cota superior de optimización) | PENDIENTE — ver §4.3 |

**Conclusión provisional para escritorio.** Quitar las imágenes **no cambia** la apertura (FCP y LCP), el cambio de pestaña ni el desplazamiento. En escritorio, por lo tanto, las imágenes no explican una lentitud de render o de JS. Las imágenes sí explican el costo de red y de memoria (bytes y píxeles decodificados). Si la lentitud percibida aparece en móvil, la causa debe buscarse en el perfil de §4.3, no en este control.

### 4.3 Pantalla Ayuda — perfil móvil simulado (PENDIENTE)

Perfil: viewport 390×844, DPR 2, CPU ×4 y red «Fast 3G» de Chrome DevTools (1,6 Mbps de bajada, 750 kbps de subida, RTT 562,5 ms). Se mide con las tres condiciones de la §4.2.

> **PENDIENTE:** esta sección se completa cuando termine la campaña móvil. Las conclusiones de la §5.1 dependen de estos números.

### 4.4 Correo: generación, tamaño y latencia SMTP (PENDIENTE)

| Dato | Estado |
|---|---|
| Banner `bannerCorreoGlucoLume.png` | 1 348 681 bytes (1,35 MB), 1536×650 px, **CONFIRMADO POR MEDICIÓN** del archivo |
| Tamaño del mensaje MIME de verificación (con banner / sin banner) | PENDIENTE |
| Generación de plantilla y MIME (p50/p95) por tipo de evento | PENDIENTE |
| Envío SMTP real del código contra sumidero local, RTT 0/50/150 ms, subida 10 y 2 Mbps | PENDIENTE |
| Comandos SMTP por envío | PENDIENTE |

### 4.5 CPU y memoria del hash de contraseñas (PENDIENTE)

Argon2id con los parámetros del código (m = 64 MiB, t = 3, p = 4). Se mide hash y verificación (p50/p95), el patrón de cambio de contraseña (5 operaciones) y el pico de RSS con 1, 2, 4 y 8 verificaciones concurrentes.

### 4.6 Tope de llamadas al driver (PENDIENTE)

Simulación con el `limitDriverCalls` real sobre SQLite: (A) consultas/s con tope 0 frente a tope 2 con 40 hilos; (B) latencia de 200 consultas rápidas con y sin una consulta lenta (~1 s) ocupando un slot. **No representa SQL Server**: mide el comportamiento del semáforo del código.

### 4.7 Streams SSE (CÁLCULO, no medido)

Cada stream ejecuta un bucle con `asyncio.sleep(0.2)` y `request.is_disconnected()`, es decir, 5 despertares por segundo por stream. Con los 300 streams globales permitidos, el event loop único recibe hasta **1 500 despertares por segundo** solo por streams. Costo real: NO EVALUADO; requiere carga controlada en un entorno de prueba.

### 4.8 Polling por usuario (cálculo, no medido)

Con una pantalla de medición visible: 1 petición cada 3 s (panel de medición) + 1 cada 3 s (adquisición en vivo) + 1 cada 5 s (estado del dispositivo) + 1 cada 30 s (avisos). Suma máxima de **≈0,9 peticiones/s por pestaña abierta** (solo cuando las pantallas están visibles y en esos intervalos), sin contar los streams SSE. Ver §6.4 para la limitación de este cálculo.

### 4.9 SQL Server (NO EVALUADO)

No hay SQL Server disponible en el laboratorio (puerto 1433 cerrado, sin daemon de Docker). Por eso no hay planes de ejecución, conteos de lecturas ni tiempos de consulta. Los hallazgos H-11, H-13 y H-19 son **CONFIRMADOS POR CÓDIGO** y su costo queda como NO EVALUADO. La forma de medirlos se describe en §8.

### 4.10 Build del frontend (CONFIRMADO POR MEDICIÓN)

| Chunk | Tamaño (kB) | gzip (kB) | Nota |
|---|---|---|---|
| `index-*.js` (inicial) | 163,19 | 47,73 | shell de la aplicación |
| `react-*.js` | 186,65 | 58,60 | React y ReactDOM |
| `router-*.js` | 39,71 | 14,36 | react-router |
| `icons-*.js` | 71,50 | 14,53 | lucide-react |
| Base compartida (suma de los 4 anteriores) | 461,05 | 135,22 | |
| `HelpPage-*.js` | 65,88 | 19,24 | solo en `/ayuda` y `/app/ayuda` |
| CSS total (17 archivos) | 194,5 | — | |

Las pantallas están divididas por ruta (`App.jsx`, `lazyNamed`). El build no reporta problemas de tamaño en el bundle inicial.

### 4.11 Limitaciones explícitas

1. **Sin SQL Server**: no hay planes de ejecución ni tiempos de consulta reales.
2. **Sin servidor HP**: no se midió el hardware productivo ni su configuración real; las diferencias se listan en §6.5.
3. **Sin SMTP real ni Google**: la latencia del proveedor de correo y la de Google son NO EVALUADAS.
4. **Sin Nginx real**: el comportamiento de caché de §H-02 se toma del código (no hay Nginx en el laboratorio ni caché de paquetes para instalarlo).
5. **Entorno de un solo equipo**: 4 vCPU compartidas entre navegador y servidor local; los tiempos absolutos no son comparables con un equipo de usuario.

---

## 5. Análisis específico: Ayuda y SMTP

### 5.1 Ayuda

**Síntoma reportado:** «se siente pesada y lenta».

**Lo que se descartó como causa única:**
- El cambio de pestaña no es lento en escritorio (≈ 37 ms p50).
- El desplazamiento no tiene cuadros largos en escritorio.
- El visor abre en ~25 ms.
- La pantalla renderiza 1235 nodos DOM, que no es excesivo para el contenido.

**Lo que sí se confirmó:**
- 22 PNG pedidos al abrir (1,59 MB) y 8 más al desplazarse. Es el costo de red principal.
- Las capturas se decodifican a su resolución completa aunque se muestren a 420 px: ~52 MB de píxeles decodificados estimados.
- Sin caché HTTP en Nginx para esos archivos (H-02): cada visita revalida los 131 PNG.

**Pendiente de decisión:** el impacto en móvil (§4.3). Solo si el control con imágenes reducidas mejora de forma significativa la apertura o el desplazamiento en el perfil móvil, las imágenes se confirman como causa principal de la lentitud percibida.

### 5.2 SMTP — flujos de envío

Se distinguen cuatro tiempos por flujo: **generación** (plantilla + MIME), **base de datos** (registro del envío y auditoría), **conexión SMTP** (TCP + TLS + AUTH) y **aceptación** (DATA hasta el 250 del servidor). El tiempo que espera el usuario es el de la petición, no el del envío.

| Flujo | Dónde se envía | Respuesta al usuario espera SMTP | Observaciones |
|---|---|---|---|
| Alta de cuenta (verificación) | `registerLocal` → `_sendVerificationEmail` (síncrono) | **Sí** | H-04 |
| Reenvío de verificación | `resendVerification` → `_sendVerificationEmail` (síncrono) | **Sí** | H-04 |
| Formulario de contacto | `sendContactMessage` + `_sendConfirmation` (síncrono, dos envíos en serie) | **Sí, dos veces** | H-05 |
| Código MFA de recuperación | `mfaRecovery._issueAndSendCode` (síncrono) | **Sí** | H-06 |
| Solicitud de eliminación de cuenta | `accountDeletion.requestDeletion` (síncrono) | **Sí** | H-06 |
| Código de cambio de contraseña | `passwordChangeCode.requestCode` (síncrono) | **Sí** | H-06 |
| Recuperación de contraseña | `auth.requestPasswordReset` → `_notify` (segundo plano) | No | Vía correcta; inconsistente con las anteriores |
| Avisos de cuenta (inicio de sesión, cambios) | `_notify` / `sendEmailEventInBackground` | No | |
| Resultado de medición | `measurement._queueResult` → `runInBackground` | No (estado PENDIENTE) | Bien resuelto |
| Confirmación de resultados | `resultEmailConfirmation.requestConfirmation` (síncrono) | **Sí** | H-06 |
| Eliminación de institución | `institution.py:1424` (cola por miembro) | No (pero cola sin límite) | H-10 |

**Qué bloquea y qué ya corre en segundo plano:** los flujos de la primera mitad de la tabla bloquean la respuesta HTTP. Los avisos y el resultado de medición ya se resolvieron con segundo plano y registro posterior. La inconsistencia entre módulos es el problema de fondo.

**Costo estimado del bloqueo:** cada envío síncrono suma el tiempo de conexión, TLS, AUTH, DATA y la transferencia del mensaje de ~1,8 MB. El valor concreto se completa con §4.4.

**Prueba no realizada con correo real:** no se enviaron correos reales. La medición se hizo contra un sumidero local con latencia simulada.

---

## 6. Problemas confirmados frente a hipótesis

### 6.1 Confirmados por medición

- Ayuda abre con 22 PNG pedidos y 1,59 MB antes de desplazarse (escritorio).
- En escritorio, quitar las imágenes no cambia apertura, cambio de pestaña ni desplazamiento.
- El banner de correo pesa 1,35 MB (archivo).
- Bundle inicial compartido: 461 kB sin comprimir / 135 kB gzip; HelpPage 65,9 kB.

### 6.2 Confirmados por código

- H-02, H-04 a H-10, H-11 (esquema), H-12, H-13, H-14, H-15, H-16, H-18, H-19, H-21, H-23.

### 6.3 Afirmaciones de documentación anterior, verificadas de nuevo

| Afirmación anterior (historial) | Estado en el código actual |
|---|---|
| Tope de llamadas al driver `DB_MAX_CONCURRENT_CALLS = 2` | **Presente** (`db/gate.py`, `core/config.py`) |
| Muestras del sensor en tandas de 400 | **Presente** (`services/measurement.py`, `SAMPLES_PER_INSERT = 400`) |
| Corrección del aviso de grupo `.is_(True)` | **No aparece** `.is_(True)` en `services/` (búsqueda por texto) |
| Carga diferida por pantalla | **Presente** (`App.jsx`, `lazyNamed`, precarga por ruta) |
| Nginx gzip precomprimido y `Vary` | **Presente** (`gzip_static`, `gzip_vary`) |
| Compilación del frontend ~3 min 20 s sin resolver | No verificable con esta medición: el build de este laboratorio tardó ~4 min 22 s en 4 vCPU |

Ninguna de estas afirmaciones se reutiliza como métrica: se refieren a otro estado del código.

### 6.4 Limitaciones de los cálculos

- El polling de §4.8 es un cálculo a partir del código; no se midió el tráfico real.
- Los 1500 despertares/s de §4.7 son el máximo permitido por el tope, no una carga observada.

### 6.5 Diferencias entre el entorno de pruebas y el servidor HP

| Aspecto | Compose base (desarrollo) | Compose producción | Servidor HP |
|---|---|---|---|
| CPU del backend | 1,0 | 2,0 | NO EVALUADO |
| Memoria del backend | 512 MB | 1 GB | NO EVALUADO |
| Memoria SQL Server | 2 GB | 4 GB | NO EVALUADO |
| Edición SQL Server | Express (por defecto) | Express (por defecto) | NO EVALUADO — verificar |
| Procesos Uvicorn | 1 | 1 | NO EVALUADO |
| Cifrado y certificado SQL | verificado en producción | verificado | NO EVALUADO |

---

## 7. Soluciones propuestas (NO implementadas)

Cada solución incluye su costo y su riesgo. Ninguna se implementa sin autorización expresa.

### 7.1 Ayuda

- **S-01 Miniaturas reducidas:** generar variantes ≤ 840 px (y WebP) para las miniaturas, mantener el original para el visor. Costo: bajo (script de build + cambio en `PasoImagen`). Riesgo funcional: bajo; hay que revisar legibilidad del texto en las capturas.
- **S-02 Caché de `/ayuda/`:** agregar `expires` o `Cache-Control` de larga duración a `/ayuda/*.png` en Nginx, con nombres versionados. Costo: bajo. Riesgo: si se cambia una captura sin cambiar el nombre, el navegador la conserva.
- **S-03 Carga de la guía por tema:** dividir `helpContent.js` por pestaña. Costo: medio. Beneficio: pequeño; prioridad baja.

### 7.2 Correo

- **S-04 Envío fuera de la petición para todos los flujos:** aplicar el patrón de `measurement._queueResult` (registro PENDIENTE + segundo plano + estado). Costo: medio (cambia la respuesta de algunos endpoints a 202 o a estado diferido). Riesgo funcional: alto en flujos de verificación y códigos; requiere revisar la UX de «correo enviado».
- **S-05 Banner más liviano:** reducir `bannerCorreoGlucoLume.png` (dimensiones y compresión) o pasarlo a una URL HTTPS externa. Costo: bajo. Riesgo: clientes de correo que bloquean imágenes externas; por eso se prefiere reducir el archivo.
- **S-06 Reutilización de conexión SMTP:** mantener una conexión por lotes o un pool pequeño con reconexión. Costo: medio. Riesgo: manejo de errores y timeouts con conexiones viejas.
- **S-07 Cola acotada y persistente:** reemplazar el `ThreadPoolExecutor` sin límite por una cola con tope, métrica de profundidad y reintentos registrados en base. Costo: alto. Riesgo: cambio en la entrega de avisos; hay que probar pérdida y duplicados.
- **S-08 Contacto:** unificar los dos envíos en un solo correo o enviar la confirmación en segundo plano. Costo: bajo. Riesgo: la confirmación puede llegar después; es aceptable y debe informarse.

### 7.3 SQL Server y backend

- **S-09 Índice en `Medicion(idPerfilMedicion, fechaHoraInicio)`** incluyendo `estadoMedicion` y `modoMedicion`. Costo: bajo en código, medio en operación (script de actualización aplicado por un administrador de la base, como indica `services/schemaCompat.py`). Riesgo: crecimiento del tamaño y tiempo de escritura; a validar con plan real.
- **S-10 Eliminar el N+1 del listado:** cargar reglas de matriz y `ruleIdOf` en lote por página. Costo: medio. Riesgo: cambio en el cálculo del semáforo; cubrir con pruebas de regresión.
- **S-11 Dashboard institucional:** materializar `performedAll` una vez y reutilizar el conjunto de identificadores; agregar índice en `Auditoria(tablaAfectada, accion, idRelacionado)`. Costo: medio. Riesgo: cambio de conteos; probar contra la versión actual.
- **S-12 Tope de llamadas al driver:** evaluar subir el límite o separar el pool de lecturas cortas del de consultas pesadas. Costo: medio. Riesgo: volver a provocar la contención que el tope evitó; requiere medición en SQL Server real.
- **S-13 Argon2:** bajar el costo solo con una decisión de seguridad documentada (no es una optimización "libre"); alternativa: dimensionar memoria del contenedor y limitar verificaciones concurrentes. Costo: bajo en código, alto en decisión. Riesgo de seguridad: cambiar parámetros de hash afecta la verificación de contraseñas existentes (requiere rehash gradual, que el código ya soporta con `verify_and_update`).
- **S-14 Dimensionamiento de contenedores:** revisar límites de memoria del backend frente a la concurrencia de logins. Costo: bajo. Riesgo: cambio de configuración de servidor, que requiere autorización.
- **S-15 Streams:** reemplazar el polling de 0,2 s por notificación (`asyncio.Event`) desde el hub. Costo: medio. Riesgo: pérdida de eventos si no se maneja la reconexión.

### 7.4 Frontend

- **S-16 Polling con visibilidad y backoff:** pausar los intervalos con `document.visibilityState` y espaciar las consultas cuando no hay cambios. Costo: bajo. Riesgo: avisos menos inmediatos.
- **S-17 Memorizar componentes de listas:** `React.memo` en filas y tarjetas de las pantallas con polling. Costo: bajo. Riesgo: bajo, pero requiere pruebas de estado.

### 7.5 Administración

- **S-18 Estado del sistema con caché corta:** guardar el resultado de la sonda SMTP/Google durante 30–60 s. Costo: bajo. Riesgo: un estado obsoleto de hasta un minuto.

---

## 8. Riesgos y pruebas requeridas

### 8.1 Riesgos de seguridad y funcionales

- Cambiar el envío a segundo plano altera qué ve el usuario después de registrarse o pedir un código (riesgo de usabilidad y de enumeración de cuentas si la respuesta cambia según exista o no el correo).
- Cambiar parámetros de Argon2 requiere migración gradual del hash.
- Un índice nuevo en `Medicion` requiere un script de actualización aplicado por el administrador de la base, sin tocar la base desde la aplicación.
- Reducir imágenes de Ayuda o del banco de correo no debe alterar la información visible (legibilidad, texto alternativo).

### 8.2 Pruebas necesarias antes de cualquier cambio

1. **Plan de ejecución en SQL Server real** para el historial de mediciones, la analítica de pacientes y el dashboard institucional (antes y después de S-09 y S-11), en una base descartable.
2. **Prueba de carga con SMTP de prueba** (sumidero local con latencia simulada, como en §4.4) para medir la respuesta de contacto, registro y reenvío antes y después de S-04 y S-08.
3. **Prueba de memoria** de logins concurrentes con el límite real del contenedor.
4. **Pruebas de regresión de Ayuda:** navegación por pestañas, visor, teclas de flecha y texto alternativo.
5. **Pruebas de regresión de correo:** cada plantilla renderiza, el banner se muestra, el reply-to y los enlaces de acción pasan la validación de origen.
6. **Pruebas de regresión del semáforo de glucosa** después de S-10.
7. Ejecutar las pruebas existentes del repositorio (backend y frontend) antes y después de cada cambio.

---

## 9. Plan de optimización posterior a la exposición

Se divide por riesgo. Se propone ejecutar en orden dentro de cada grupo y solo con autorización.

### 9.1 Riesgo bajo

- S-01 Miniaturas reducidas en Ayuda.
- S-02 Caché para `/ayuda/` en Nginx (cambio de configuración: requiere autorización).
- S-05 Reducir el banner de correo.
- S-08 Contacto: confirmación en segundo plano.
- S-16 Pausa de polling con visibilidad.
- S-17 `React.memo` en listas con polling.
- S-18 Caché corta del estado del sistema.

### 9.2 Riesgo medio

- S-04 Envío fuera de la petición para verificación, códigos, eliminación, confirmación de resultados (con cambios de respuesta).
- S-06 Reutilización de conexión SMTP.
- S-10 Eliminar el N+1 del listado de mediciones.
- S-11 Dashboard institucional con conjunto materializado y nuevo índice.
- S-14 Dimensionamiento de contenedores.
- S-12 Revisión del tope de llamadas al driver (solo con medición en SQL Server).

### 9.3 Riesgo alto

- S-07 Cola de correo acotada y persistente.
- S-09 Índice en `Medicion(idPerfilMedicion, ...)` (requiere plan real y ventana de actualización).
- S-13 Cambio de parámetros de Argon2 (decisión de seguridad).
- S-15 Streams sin polling.

---

## 10. Resumen de la auditoría

Ver el resumen ejecutivo en la respuesta de la sesión. Este documento queda como diagnóstico y no autoriza cambios.
