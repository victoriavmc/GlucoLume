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
