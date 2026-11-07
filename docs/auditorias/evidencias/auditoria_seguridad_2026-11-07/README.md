# Evidencias: auditoría técnica de seguridad del 07/11/2026

Estas evidencias respaldan `docs/auditorias/CORRECCIONES_AUDITORIA_SEGURIDAD_2026-11-07.md`.

## Qué contiene

| Archivo | Qué es |
|---|---|
| `sondas_nginx.sh` | Sondas HTTP de solo lectura para M-1, B-1, B-2, B-3, B-6 y B-5/B-7. Recibe la URL base y no escribe nada. |
| `resultados_antes.txt` | Salida de las sondas con la plantilla de `HEAD` (`a3908c0`). |
| `resultados_despues.txt` | Salida de las sondas con la plantilla de la rama de trabajo. |
| `verificar_rutas_antes.txt` | Salida de `docker/nginx/verificar-rutas.sh` con la plantilla de `HEAD`. |
| `verificar_rutas_despues.txt` | Salida de `docker/nginx/verificar-rutas.sh` con la plantilla de la rama. |
| `sondas_redireccion_api.sh` | M-1: redirección de `/api` (Host de Tailscale), rutas proxificadas, seguimiento de redirecciones y mixed content. |
| `resultados_redireccion_api_antes.txt` | M-1: plantilla de `a3908c0` (la de la auditoría). |
| `resultados_redireccion_api_rama_previa.txt` | M-1: plantilla de `HEAD` previo a este parche (`1931580`). |
| `resultados_redireccion_api_despues.txt` | M-1: plantilla de la rama con este parche. |
| `sondas_tamano_cuerpo.sh` | B-1: límites de tamaño exactos por operación (justo bajo, justo encima y casos normales). |
| `resultados_tamano_cuerpo_antes.txt` / `_despues.txt` | B-1: medición con HEAD (1 MB global) y con la rama (tramos por operación). |
| `calcular_tamanos_maximos.py` / `resultados_tamanos_maximos.tsv` | B-1: peor caso legítimo de cada operación, generado desde el OpenAPI de la app. |
| `resultados_pruebas_b1.txt` | B-1: resultados de pruebas (backend, nginx, verificar-rutas). |
| `M1_redireccion_api.patch` | M-1: parche (plantilla, Dockerfile del frontend, pruebas). Reversible con `git apply -R`. |
| `sondas_salud.sh` / `resultados_salud_antes.txt` / `resultados_salud_despues.txt` | B-6: liveness `/api/v1/healthz` y readiness `/api/v1/readyz` (404 por Nginx; 503 directo al backend sin base). |
| `sondas_rutas_spa.sh` / `resultados_rutas_spa_antes.txt` / `_despues.txt` | B-2: código y tipo de una matriz de rutas (válidas, desconocidas, sensibles, API) con la plantilla de `HEAD` y con la de la rama. |
| `verificar_navegacion_spa.cjs` / `resultados_navegacion_spa_antes.txt` / `_despues.txt` | B-2: navegación en Chromium (clic interno, acceso directo, recarga, desconocidas, API). Requiere Playwright y el build del frontend. |
| `sondas_cabeceras_csp.sh` / `resultados_cabeceras_csp_antes.txt` / `_despues.txt` | B-7: cabecera CSP de la SPA y de la API antes y después de `report-uri`. |
| `sondas_hsts.sh` / `resultados_hsts_antes.txt` / `_despues.txt` | B-4: HSTS, Location y código por host (dominio, localhost) y X-Forwarded-Proto. Requiere `TRUSTED_PROXY_CIDR=127.0.0.0/8` en el banco. |
| `verificar_reportes_csp.cjs` / `resultados_reportes_csp.txt` | B-7: navegación normal (0 reportes) y violación provocada (2 reportes sanitizados, sin tokens en el log). Requiere Playwright y el build del frontend. |

## Cómo se obtuvieron

- **Nginx 1.24 local** (paquete de Ubuntu). La imagen de producción usa `nginx-unprivileged:1.30-alpine-slim`; el comportamiento de redirecciones y de `add_header`/`proxy_hide_header` es el mismo para estas pruebas.
- **Plantilla renderizada** con `envsubst` sobre `docker/nginx/default.conf.template`, con `BACKEND_UPSTREAM=127.0.0.1:8000` y `TRUSTED_PROXY_CIDR=172.16.0.0/12` (los valores por defecto de `compose.yaml`).
- **Dos cambios sólo en el banco de pruebas, no en el repo:** la ruta `root` de la plantilla (`/usr/share/nginx/html`) se reemplazó por un webroot temporal, y el archivo de configuración lleva `user root;` para que los workers puedan leer ese directorio.
- **Backend real** (`app.main:app`) con uvicorn en `127.0.0.1:8000`, sin base de datos. Por eso las respuestas de login que requieren base (500) no se miden aquí; el comportamiento del login se prueba con pytest sobre SQLite.
- **Webroot temporal** con `index.html` y un `assets/*.js` de relleno. No es el build real del frontend.

## Reproducir

```bash
# Instancia local de Nginx con la plantilla del repo y un backend en 127.0.0.1:8000
bash docs/auditorias/evidencias/auditoria_seguridad_2026-11-07/sondas_nginx.sh http://127.0.0.1:8080
bash docker/nginx/verificar-rutas.sh http://127.0.0.1:8080
```

No ejecutar estas sondas contra producción sin autorización.
