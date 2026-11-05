# Informe de validación: primera etapa de optimización (S-01, S-02, S-07)

**Fecha:** 5/11/2026 · **Rama:** `claude/optimizacion-exposicion-2026-11-11` · **Base:** `master` (933d84c, código auditado).
**Alcance autorizado:** S-01, S-02 y S-07 de `RENDIMIENTO_2026-11-05.md`. No se avanzó a S-03 (requiere cambio de Nginx), S-06, S-09, S-10, S-11, S-14 ni S-15.
**Estado de integración:** nada se fusionó a `master` ni se desplegó.

---

## 1. Resumen y recomendación

| Solución | Commits | Resultado medido | Recomendación |
|---|---|---|---|
| **S-01** Precarga de Ayuda | `04b4f53` | Móvil: LCP −68 ms, FCP −34 ms (p50). Escritorio: sin cambio material. | **Integrar.** Riesgo bajo. Beneficio menor al estimado (ver §4). |
| **S-07** Banner de correo (PNG → JPEG 900 px) | `38dcd8f` | MIME del correo: 1 829 355 → 91 312 bytes (**−95 %**). 181/181 pruebas de correo. Visual sin diferencias apreciables. | **Integrar**, con una verificación manual en un cliente de correo real antes de la exposición (§5). |
| **S-02** Miniaturas WebP de Ayuda | `b1ddc88`, `158a16d`, `1be47cd` | Bytes al abrir −81 %; píxeles decodificados −30 %; tarea larga al cambiar de pestaña en móvil p95 176 → 75 ms. Visor sin regresión de composición (0 píxeles distintos en la captura ampliada). | **Integrar después de la revisión manual de teclado y visor** (§5). Si no hay tiempo, postergar: no bloquea la exposición. |

Los tres cambios son independientes y reversibles. S-02 tiene tres commits porque el primero introdujo una regresión del visor que se corrigió en dos pasos (ver §3.2); antes de integrar conviene decidir si se aplasta en un solo commit.

---

## 2. Archivos modificados

| Archivo | Cambio | Solución |
|---|---|---|
| `frontend/src/App.jsx` | Agrega `/ayuda` y `/app/ayuda` a `PRELOADS` | S-01 |
| `frontend/src/pages/Account/help/GuiaVisual.jsx` | Miniatura WebP en `PasoImagen`; visor con marco de tamaño fijo y miniatura de fondo mientras carga el original | S-02 |
| `frontend/src/pages/Account/help/Help.css` | Regla `.help-visor-marco` (caja fija) | S-02 |
| `frontend/src/pages/Account/help/helpCaptures.test.jsx` | Pruebas nuevas: referencias, miniaturas, visor | S-02 |
| `frontend/public/ayuda/miniaturas/*.webp` | 131 miniaturas WebP (máx. 840 px, calidad 85) | S-02 |
| `frontend/scripts/generar-miniaturas-ayuda.sh` | Script reproducible de las miniaturas | S-02 |
| `backend/app/emails/bannerCorreoGlucoLume.png` | **Eliminado** (1 348 681 bytes) | S-07 |
| `backend/app/emails/bannerCorreoGlucoLume.jpg` | **Nuevo** JPEG 900×381, calidad 82, 62 079 bytes | S-07 |
| `.gitignore` | Comentario actualizado (el banner es `.jpg`) | S-07 |
| `docs/auditorias/**` | Auditoría como contexto y evidencias de esta validación | documentación |

**Sin tocar:** autenticación, MFA, roles, permisos, base de datos, migraciones, concurrencia del backend, ODBC, flujo de mediciones y adquisición, transporte SMTP, auditoría, destinatarios, lógica de entrega, Docker, Nginx, configuración de producción ni dependencias.

**Archivo local no commiteado:** `backend/tests/test.env` (ignorado por git, valores ficticios) — necesario para ejecutar las pruebas de backend en este entorno.

---

## 3. Problemas solucionados y cómo se abordaron

### 3.1 S-01: cadena de carga de Ayuda
- **Problema:** el chunk `HelpPage` se pedía después del JavaScript del shell (`index.js`), porque `/ayuda` no estaba en la lista de precarga.
- **Solución:** agregar las dos rutas a `PRELOADS`. `main.jsx` ya llama `preloadForPath(pathname)` al cargar, así que la descarga arranca en paralelo con el shell. Ninguna otra pantalla cambia.
- **Límite:** el chunk sigue dependiendo del `index.js` (el navegador no lo conoce hasta ejecutarlo). Eliminar ese paso requiere un `modulepreload` inyectado en el HTML del build; queda como trabajo posterior.

### 3.2 S-02: miniaturas y visor
- **Problema:** cada captura se mostraba a ≤ 420 px desde el PNG completo (hasta 1315 px), con 22 PNG (1,59 MB) pedidos al abrir la guía en escritorio.
- **Solución:** la miniatura de la guía es WebP de máx. 840 px. El visor sigue usando el PNG original (`data-src`).
- **Regresión encontrada en la primera versión:** el visor pedía el original recién al abrirse (no estaba en caché porque antes la miniatura *era* el original): **~890 ms en móvil simulado** (antes 70 ms).
- **Primer intento (`158a16d`):** mostrar la miniatura como fondo de la `<img>`. **No funcionó**: la imagen sin cargar mide 0 px de ancho, así que el fondo no se pintaba.
- **Corrección (`1be47cd`):** la imagen va dentro de `.help-visor-marco`, una caja de tamaño fijo con la miniatura de fondo y el original superpuesto con `object-fit: contain`.
- **Verificación:** el visor aparece en 20–26 ms (fondo de miniatura) y el original se afina después. La captura ampliada coincide píxel a píxel con `master` (escritorio 0 de 202 704; móvil 0 de 800 656 distintos).

### 3.3 S-07: peso del banner
- **Problema:** el banner de 1,35 MB viaja como imagen inline en cada correo; el mensaje completo pesa 1,83 MB.
- **Alternativas evaluadas:**
  - PNG de 256 colores a 768 px: 92 KB, con **bandas visibles** en los degradados a 3× de zoom.
  - PNG con dithering: 128 KB, con patrón de ruido visible.
  - **JPEG 900 px, calidad 82: 62 KB, sin bandas.** Elegido.
- **Por qué el cambio de formato:** la ilustración tiene degradados suaves y el canal alfa del original es completamente opaco, así que no se pierde nada al pasar a JPEG. Todos los clientes de correo soportan JPEG inline.
- **Compatibilidad del código:** `loadBanner` detecta el formato por la firma del archivo (`FFD8FF`), y el `Content-ID` y el `cid:` no cambian.

---

## 4. Métricas antes/después

Condiciones: build de producción en `localhost` con compresión, caché fría por corrida, navegador nuevo por corrida, **n = 10** por condición, valores **p50** (p95 entre paréntesis). Fuente: `docs/auditorias/evidencias/optimizacion_2026-11-11/`.

### 4.1 Escritorio (1366×768, sin limitación)

| Métrica | master (antes) | S-01 | S-01 + S-02 (final) |
|---|---|---|---|
| Apertura hasta primera figura (ms) | 467,5 (648,8) | 457,5 (477,4) | 463,0 (502,8) |
| FCP (ms) | 114,0 (226,6) | 94,0 (100,0) | 98,0 (110,2) |
| LCP (ms) | 464,0 (1233,8) | 456,0 (460,0) | 472,0 (496,8) |
| Bytes de imagen al abrir | 1 589 129 | 1 589 129 | **296 074 (−81 %)** |
| Cambio a pestaña Institucional (ms) | 40,3 (58,7) | 42,1 (45,9) | 43,4 (50,4) |
| Visor: original listo (ms) | 24,0 (26,6) | 21,5 (29,0) | 29,0 (47,9) |
| Píxeles decodificados (MB) | 51,8 | 51,8 | **36,8 (−29 %)** |

Lectura: en escritorio las imágenes no limitaban la apertura, así que no hay mejora de tiempo. El visor del original tiene un p95 algo mayor (27 → 48 ms) porque el original ya no está en caché; la diferencia es de decenas de ms.

**Nota sobre el LCP de escritorio:** la mediana cambia de 464 a 472 ms, pero la dispersión es alta (p95 1234 ms antes por la primera corrida en frío tras un reinicio del contenedor; ver §6). Es ruido de medición y no debe leerse como regresión.

### 4.2 Móvil simulado (390×844, DPR 2, CPU ×4, Fast 3G de Chrome)

| Métrica | master (antes) | S-01 | S-01 + S-02 (final) |
|---|---|---|---|
| Apertura hasta primera figura (ms) | 3123,0 (3151,7) | 3054,0 (3122,7) | **3052,0 (3076,1)** |
| FCP (ms) | 2168,0 (2192,8) | 2148,0 (2177,6) | **2134,0 (2148,4)** |
| LCP (ms) | 3102,0 (3141,2) | 3038,0 (3112,2) | **3034,0 (3050,2)** |
| Bytes de imagen al abrir | 703 969 | 703 969 | **133 202 (−81 %)** |
| Cambio a Institucional (ms) | 166,0 (180,7) | 169,0 (227,6) | 168,8 (185,0) |
| Tarea larga al cambiar pestaña (ms, p95) | 175,7 | 151,6 | **75,3** |
| Visor aparece (ms) | — | — | 76,5 (90,1) |
| Visor: original listo (ms) | 69,5 (79,5) | 72,0 (94,5) | 697,5 (714,0) |
| Píxeles decodificados (MB) | 49,9 | 49,9 | **35,2 (−29 %)** |

Lectura:
- **La apertura mejora poco (−71 ms, −2 %).** El límite está en la cadena de carga de JavaScript y CSS, no en las imágenes (ver §4.3).
- **El visor es el costo principal de S-02 en móvil:** aparece en 76 ms, pero la imagen en calidad completa llega a ~0,7 s en Fast 3G porque ya no está en caché. Es el precio de no descargar el original al abrir la guía. Se considera aceptable porque la imagen se ve de inmediato (miniatura) y se afina después.
- **La tarea larga al cambiar de pestaña baja de 176 a 75 ms (p95)**, lo que se atribuye a no decodificar 50 MB de capturas completas.

### 4.3 Waterfall de la ruta (móvil, una corrida)

| Recurso | master: fin (ms) | S-01: fin (ms) |
|---|---|---|
| `index-*.js` (shell) | 1932 | 1911 |
| `react-*.js` | 1998 | 1977 |
| `HelpPage-*.js` (chunk de la ruta) | 2867 | 2779 |

S-01 adelanta el chunk de la ruta 88 ms, pero su descarga sigue esperando a `index.js`: falta un nivel de latencia de red (~0,56 s en este perfil). La mejora medida de S-01 es menor que la estimada en la auditoría (0,6–0,9 s); lo corrijo aquí.

### 4.4 Correo (S-07)

| Dato | Antes | Después | Variación |
|---|---|---|---|
| Archivo del banner | 1 348 681 bytes (PNG) | 62 079 bytes (JPEG) | −95 % |
| Mensaje MIME del correo de verificación | 1 829 355 bytes | 91 312 bytes | **−95 %** |
| Tipo de imagen adjunta | `image/png`, inline, Content-ID correcto | `image/jpeg`, inline, Content-ID correcto | — |
| Generación de plantilla (mediana de 78 eventos) | 0,86 ms | sin cambio (no depende del tamaño de la imagen) | — |

**Efecto en el envío real** (medido en auditoría): con 2 Mbps de subida y RTT 50 ms, un envío con el banner anterior tardaba ~8 s; el mensaje nuevo se transfiere en ~0,4 s más el RTT. Cálculo a partir del tamaño medido; no se midió en un servidor SMTP real.

---

## 5. Pruebas ejecutadas y resultados

### 5.1 Frontend (vitest, suite completa)

| Ejecución | Archivos | Pruebas | Resultado |
|---|---|---|---|
| `master` (933d84c) | 64 | 847 | 846 pasan, **1 falla preexistente** |
| Árbol con S-01 y S-02 | 65 | 852 | 851 pasan, la misma falla preexistente |
| Pruebas de Ayuda (`src/pages/Account/help`) | 2 | 15 | 15 pasan (incluye 5 pruebas nuevas de capturas) |

**Falla preexistente (no atribuible a estos cambios):** `src/pages/Account/institutions/patients/PatientMeasure.test.jsx` → «si se informa la última comida se envía con su fecha y hora» (`expected false to be true`). Es determinista (2/2 corridas), también ocurre en `master` sin cambios y no toca Ayuda ni los componentes modificados. Queda registrada y **no se corrigió** porque está fuera de alcance.

### 5.2 Backend (correo)

| Ejecución | Pruebas | Resultado |
|---|---|---|
| `master` (PNG) | `tests/test_emails.py`: 181 | 181 pasan |
| Con JPEG (S-07) | `tests/test_emails.py`: 181 | 181 pasan |

Entorno: `backend/tests/test.env` local (ignorado por git) con valores ficticios. Sin base de datos ni SMTP reales.

### 5.3 Build y referencias a recursos

- Build de producción de `master`, de S-01 y de S-01+S-02: sin errores (`built in ~4 min 22 s`).
- Las 131 miniaturas se sirven desde el build (`/ayuda/miniaturas/*.webp`, 200 OK). Cada captura citada en la guía tiene original y miniatura; no hay miniaturas huérfanas (prueba automatizada).
- Las rutas `/ayuda` y `/app/ayuda`, las pestañas y las anclas no cambian (sólo se agregó precarga).

### 5.4 Consola, navegación y errores

- Mediciones de navegador: **0 errores** en 60 corridas por campaña.
- No se revisó la consola del navegador de forma exhaustiva en todas las pantallas: **pendiente de revisión manual** (ver §6).

### 5.5 Legibilidad y composición

- Legibilidad de texto: comparación a escala de dispositivo (840 px) entre original y miniatura; el texto se lee igual (archivo `legibilidad_miniatura_vs_original.png`).
- Visor: captura ampliada idéntica píxel a píxel a `master` (escritorio y móvil). Las diferencias de página completa son sólo el desplazamiento del fondo por la carga lazy.
- Banner: comparación visual del correo a 598 px (`correo_banner_antes_despues.png`); sin diferencias apreciables.

---

## 6. Riesgos restantes y limitaciones

1. **Medición de laboratorio:** un solo equipo, 4 vCPU compartidas con el navegador, móvil simulado con throttling (no dispositivo físico). Las diferencias relativas son válidas; los tiempos absolutos no.
2. **Primera corrida en frío de la campaña BEFORE:** tras un reinicio del contenedor, la primera corrida de escritorio tardó 778 ms (vs ~465 ms del resto). Se conserva en los datos; p50 no se ve afectado.
3. **Visor sin caché en la primera apertura (S-02):** en móvil, la imagen en calidad completa tarda ~0,7 s en llegar. Riesgo de percepción, no de funcionalidad.
4. **Correo real no probado:** el banner JPEG se validó en MIME y en render de navegador, no en Gmail, Outlook ni Apple Mail. Es el riesgo principal de S-07.
5. **Revisión manual pendiente:** navegación por teclado dentro del visor (Tab, Escape, flechas), lector de pantalla y consola en las pantallas de Ayuda. Las pruebas automatizadas cubren flechas y texto alternativo, pero no el recorrido completo.
6. **Trabajo no hecho (fuera de alcance):** `modulepreload` del chunk de Ayuda (eliminaría el nivel de latencia restante, §4.3); caché HTTP para `/ayuda/` en Nginx (S-03, requiere autorización de configuración); CLS de las miniaturas (no tienen `width`/`height` explícitos, igual que antes).
7. **Historial de commits de S-02:** tres commits (inicial + dos correcciones). Aplastarlos en uno requiere reescribir la rama; no se hizo sin autorización.

---

## 7. Efectos sobre funcionalidades existentes

- **Ayuda:** misma guía, mismos textos, mismas pestañas, anclas, enlaces, roles y reglas de acceso. El visor mantiene el original, la navegación por flechas y el cierre con Escape/clic fuera (pruebas automatizadas).
- **Correo:** mismo contenido, mismos destinatarios, mismo transporte SMTP, mismos enlaces de acción y mismo remitente. Sólo cambia la imagen del encabezado.
- **Navegación general:** la precarga de `/ayuda` y `/app/ayuda` descarga el chunk de la guía al cargar esas rutas; no afecta a ninguna otra pantalla.

---

## 8. Recomendación de integración

| Cambio | Estado | Acción antes de la exposición |
|---|---|---|
| **S-01** | Listo para integrar | Revisión rápida de `/ayuda` y `/app/ayuda` en navegador. |
| **S-07** | Listo para integrar | **Verificación manual** del correo de verificación en un cliente real (al menos Gmail y Outlook). Si no se puede, postergar. |
| **S-02** | Listo técnicamente; requiere validación manual | **Revisión manual** del visor con teclado (Tab, Escape, flechas) y lector de pantalla. Si falla algo, postergar; el resto no depende de S-02. |

**Postergar hasta después de la exposición:** `modulepreload` del chunk de Ayuda, caché de Nginx para `/ayuda/`, CLS de miniaturas, y la falla preexistente de `PatientMeasure.test.jsx`.

**Lo que no está validado y debe quedar explícito:** SMTP real, clientes de correo reales, lector de pantalla y el servidor HP (no se accedió).
