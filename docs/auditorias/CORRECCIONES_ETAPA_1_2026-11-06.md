# Correcciones de la primera etapa (estabilidad antes de la exposición)

> **Rama:** `fix/estabilidad-pre-exposicion`, creada desde `master` (`6922949`). **No se hizo merge a `master`, no se actualizó el servidor HP y no se desplegó nada.**
> **Hallazgos:** los identificados en `docs/auditorias/RENDIMIENTO_2026-11-05.md`.
> **Evidencia:** `docs/auditorias/evidencias/correcciones_etapa1_2026-11-06/` (resultados, scripts y comparaciones).

## 1. Commits (uno por corrección)

| Commit | Corrección | Qué cambia |
|---|---|---|
| `1ea9e9e` | AUD-01 (P0) | Dos ubicaciones exactas en Nginx (`= /ayuda`, `= /ayuda/`) que entregan la SPA con `no-cache`. Agrega `docker/nginx/verificar-rutas.sh`. |
| `9b14d8f` | AUD-16 | Ubicación `^~ /ayuda/` con `expires 7d` para capturas y miniaturas. Sin `add_header` propio (hereda las cabeceras de seguridad). |
| `bd14149` | AUD-19 | `width` y `height` en cada miniatura de la guía, desde un mapa generado (`miniaturasTamanos.js`) con su script y pruebas. |
| `eb724eb` | AUD-03 (solo `/healthz`) | El handler pasa a `async`. Misma respuesta (`{"estado": "ok"}`) y mismas cabeceras. Pruebas en `backend/tests/test_healthz.py`. |
| `ebd9d64` | Plan etapa 2 | Documento `PLAN_ETAPA_2_BACKEND_2026-11-06.md`: soluciones y pruebas **sin implementar**. |

## 2. Antes y después

| Corrección | Antes (`master`) | Después (rama) | Medición |
|---|---|---|---|
| AUD-01 `/ayuda` | `/ayuda` → 301 → `/ayuda/` → **403**. En el navegador, el acceso directo no muestra la guía. | `/ayuda`, `/ayuda/` y `/ayuda?query` → 200 (SPA). Acceso directo, recarga y navegación desde la portada cargan 114 figuras sin errores HTTP ni JS. | `mediciones/rutas_antes_master.txt`, `rutas_despues.txt`, `pruebas/ayuda_directo_*.txt` |
| AUD-16 caché | Capturas sin `Cache-Control` ni `Expires`. | `max-age=604800` en capturas y miniaturas. | `mediciones/cache_capturas_ab.json` |
| AUD-19 salto de altura | Altura de la guía: **29 084 px** al abrir → **59 774 px** con las miniaturas cargadas (**+51 %**). | **59 774 px** desde el inicio (**0 %**). | `mediciones/altura_pagina_master.json`, `altura_pagina_despues.json` |
| AUD-19 aspecto visual | — | Captura de página completa de escritorio: **0 píxeles distintos** de 81,6 millones. | `mediciones/comparacion_visual_pixeles.txt` |
| AUD-03 `/healthz` | Con 40 peticiones bloqueadas (simulan SMTP colgado): máximo **7 361 ms**. | Máximo **3,4–3,7 ms**. En reposo, igual (p50 ≈1,4 ms). | `mediciones/healthz_bajo_carga_antes.json`, `..._despues.json` |

**Lectura honesta de cada medición:**

- **AUD-16:** en la visita inmediata, `master` también sirve las capturas desde caché (la caché heurística de Chromium a partir de `Last-Modified`). El beneficio real es que la política queda **explícita y predecible** (7 días fijos, no una fracción de la antigüedad del archivo). Ese beneficio no está medido en el tiempo: se deduce de la regla de caché.
- **AUD-19:** el CLS medido con desplazamiento en móvil lento fue **0 en ambas versiones**. La mejora medida es la **estabilidad de la altura de la página** mientras el usuario baja (el "salto" que ve), no el CLS.
- **AUD-01:** es un fallo funcional, no de rendimiento. La medición compara solo el comportamiento de la ruta.

## 3. Pruebas ejecutadas

| Prueba | Resultado |
|---|---|
| `docker/nginx/verificar-rutas.sh` contra Nginx 1.24 con la plantilla del repositorio | **19 de 19** pasan (`master`: 5 fallos). |
| Navegador, sin interceptación: acceso directo, recarga, `/ayuda/`, navegación desde portada | **Pasan** en la rama. En `master`, el acceso directo falla (ver `pruebas/ayuda_directo_antes_master.txt`). |
| Vitest, pruebas de Ayuda (`src/pages/Account/help`) | **17 de 17** pasan. |
| Mutación de una dimensión del mapa | La prueba de encabezados WebP la **detecta** (falla) y, restaurada, pasa. |
| Vitest, suite completa del frontend | 854 pasan, **1 falla preexistente** (`PatientMeasure.test.jsx`, misma falla en `master`). |
| pytest, suite completa del backend (`master` y rama, sin variables de entorno) | Mismo conjunto de **86 fallos** en ambas: son de entorno (falta `backend/tests/test.env` y la librería ODBC). |
| pytest, esos 86 fallos con entorno de laboratorio (ODBC instalado, SMTP de prueba) | **80 pasan** en ambas versiones. Los **6 restantes fallan igual en `master`** (filtros de auditoría y mediciones con fechas, prueba de la imagen Docker, prueba de lectura del `.env` real). |
| `test_healthz.py` y `test_security_hardening.py` | **30 de 30** pasan (incluye las 3 pruebas nuevas). |

**No hay regresiones detectadas** en las pruebas que se pudieron ejecutar.

## 4. Problemas que continúan

1. **Nginx validado solo con 1.24.** La imagen de producción es `nginx-unprivileged:1.30`. No pude ejecutar Docker aquí. Hay que correr `docker/nginx/verificar-rutas.sh` contra la imagen de staging antes de la exposición.
2. **El bloqueo por SMTP sigue vigente.** Los flujos de registro, reenvío, eliminación, recuperación MFA, invitaciones y contacto siguen esperando al SMTP dentro de la petición. Con el servidor de correo lento o caído, cada intento tarda hasta 20 s y ocupa un hilo del pool. **Esto es el mayor riesgo de estabilidad para la exposición** y no se corrigió, porque cambiar la entrega de correos estaba fuera de esta etapa.
3. **Argon2 sin límite de concurrencia (AUD-05).** Con muchos inicios simultáneos, la memoria del contenedor de 1 GB puede agotarse (estimado en ≈15 simultáneos). No se tocó.
4. **Fallos de pruebas preexistentes.** La suite del backend necesita `backend/tests/test.env` y la librería ODBC; sin eso, 86 pruebas no corren. Con el entorno, 6 siguen fallando en `master`. La prueba de `PatientMeasure` falla en `master` con un tiempo de ≈5,2 s.
5. **Capturas con caché de 7 días.** Si se corrige una captura durante la semana, algunos navegadores la mostrarán vieja hasta que venza la caché o se recargue con forzado. Para la exposición no hay cambios de capturas planeados; si los hubiera, hay que renombrar el archivo.
6. **Riesgo de la colisión `/ayuda`.** Las dos ubicaciones exactas resuelven el caso actual. Si en el futuro se crea otra carpeta pública con nombre de ruta de la SPA, ocurrirá lo mismo. La prueba `verificar-rutas.sh` lo detectaría en staging.

## 5. ¿Conviene incorporar los cambios antes de la exposición?

**Sí, considero seguro incorporarlos, con dos condiciones:**

- Son cambios **pequeños y localizados**: una ubicación de Nginx que solo afecta a `/ayuda` y sus capturas, un atributo de tamaño en la guía (sin diferencia visual medida), y un handler que devuelve lo mismo. No tocan autenticación, MFA, Argon2, correo, base de datos, purgas ni concurrencia.
- **Condición 1:** correr `docker/nginx/verificar-rutas.sh` contra la imagen de Nginx que se usará en la exposición (staging). Debe devolver 19 de 19.
- **Condición 2:** una pasada manual de la portada, `/ayuda` (acceso directo y recarga) y un inicio de sesión de prueba, en el mismo entorno.

**Lo que no recomiendo cambiar antes de la exposición** (riesgo mayor que el beneficio): la entrega de correos (AUD-02/AUD-04), el semáforo de Argon2 (AUD-05), la concurrencia ODBC (AUD-06), los índices (AUD-07) y las purgas (AUD-11). Son las correcciones de la segunda etapa, con las pruebas descritas en `PLAN_ETAPA_2_BACKEND_2026-11-06.md`.

**Recomendación operativa para la exposición (sin cambio de código):** verificar en el entorno de producción que el SMTP responde (credenciales y host). Si el correo está caído el día de la exposición, los flujos de cuenta se verán lentos y pueden fallar en 20 s.

## 6. Pendiente de autorización

- Merge de `fix/estabilidad-pre-exposicion` a `master`.
- Despliegue o actualización del servidor HP.
- Implementación de la segunda etapa.
