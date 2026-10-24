# Evidencias de rendimiento (23/10/2026)

Scripts y resultados de [../../RENDIMIENTO.md](../../RENDIMIENTO.md). Todo corre contra una base **descartable** (`GlucoLume_perf`, dentro del mismo SQL Server del perfil `db`) con datos
**sintéticos**; ningún script toca la base «GlucoLume» (`seed.py` y `medir_consultas.py` abortan si `DB_NAME` no es `GlucoLume_perf`).

| Archivo | Para qué |
|---|---|
| `crear_base_perf.sh` | Crea (o recrea) `GlucoLume_perf` con los scripts oficiales: v5, matriz global y permisos de la cuenta de la API |
| `compose.rendimiento.yaml` | Segunda API (`backend-perf`, 127.0.0.1:18000) y segundo Nginx (`frontend-perf`, 127.0.0.1:18080) con los límites de producción; `PERF_TAG` elige las imágenes y `PERF_GATE` el tope de llamadas al driver |
| `seed.py`, `ppg.py` | Datos sintéticos con los servicios reales (601 perfiles, 8,7 mil mediciones, muestras de sensor) |
| `medir_consultas.py` | Sentencias SQL, escrituras, *commits* y tiempo de base por operación (en proceso, SQL Server real) |
| `medir_http.py` | Latencia p50/p95/p99, concurrencia e ingesta de muestras por HTTP |
| `carga_endpoint.py` | Carga de un solo endpoint con N clientes (aísla qué operación se degrada) |
| `medir_frontend.mjs` | Playwright/Chromium: FCP, LCP, CLS, TBT, JS transferido, solicitudes, con red rápida y «Fast 3G» + CPU 4× |
| `cls_fuentes.mjs` | Diagnóstico de los desplazamientos de diseño (CLS) de una pantalla |
| `hilos_servicio.py`, `hilos_micro.py`, `hilos_micro2.py`, `hilos_micro3.py` | Diagnóstico de la caída de rendimiento con muchos hilos dentro de `pyodbc` (RENDIMIENTO.md §3.1) |
| `comparar.py` | Genera las tablas «antes → después» desde los JSON de `resultados/` |
| `resultados/` | Salidas: `consultas_*.txt`, `http_*.json`, `frontend_*.json`/`.txt`, `hilos_*.txt` (`seed_ids.json` se genera y no se versiona) |

## Procedimiento (Git Bash, desde la raíz del repositorio)

```bash
# 0. Requisitos: Docker Desktop, docker/db.env, .env, y `npm i playwright@1.49.1 && npx playwright install chromium` en una carpeta fuera del repo (NODE_PATH).
docker build -t glucolume/backend:baseline backend    # sobre master;  y la imagen del frontend con VITE_LOGIN_ORIGIN= y VITE_APP_ORIGIN= vacíos (ver abajo)
docker compose --profile db up -d db                  # SQL Server del proyecto
bash docs/evidencias/rendimiento/crear_base_perf.sh   # esquema v5 + matriz + permisos en GlucoLume_perf
export MSYS_NO_PATHCONV=1
PERF_TAG=baseline docker compose -f compose.yaml -f docs/evidencias/rendimiento/compose.rendimiento.yaml --profile db --profile perf run --rm --no-deps \
  -v "$(pwd -W)/docs/evidencias/rendimiento:/perf:ro" backend-perf python /perf/seed.py > docs/evidencias/rendimiento/resultados/seed_ids.json
PERF_TAG=baseline docker compose -f compose.yaml -f docs/evidencias/rendimiento/compose.rendimiento.yaml --profile db --profile perf up -d backend-perf frontend-perf
# medir (la máquina en reposo):
python docs/evidencias/rendimiento/medir_http.py --base http://127.0.0.1:18000 --etiqueta base
NODE_PATH=<carpeta>/node_modules node docs/evidencias/rendimiento/medir_frontend.mjs --etiqueta base
# repetir con PERF_TAG=perf (imágenes de la rama) y generar las tablas:
python docs/evidencias/rendimiento/comparar.py frontend
```

La imagen del frontend para medir se compila sin los orígenes del login real (`--build-arg VITE_LOGIN_ORIGIN= --build-arg VITE_APP_ORIGIN=`), porque Playwright abre `http://localhost:18080`
(`compose.rendimiento.yaml` fija `FRONTEND_URL`/`API_BASE_URL` a ese origen). Las contraseñas de las cuentas sintéticas son las de `seed.py` (públicas, solo de la base descartable).

Para repetir el barrido del tope de llamadas al driver: `PERF_GATE=<0|2|3|4> PERF_TAG=perf docker compose … up -d --force-recreate backend-perf` y `medir_http.py --concurrencia 8,32`.
