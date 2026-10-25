## Qué es
Revisión de rendimiento del 23/10/2026, en rama aparte de `master` y sin tocar la remediación de seguridad ya validada. Informe completo, con evidencia, causa, solución, métricas antes/después y limitaciones: `docs/RENDIMIENTO.md`. Scripts y resultados reproducibles: `docs/evidencias/rendimiento/`.

Todo se midió con datos sintéticos en una base descartable (`GlucoLume_perf`); la base «GlucoLume» y la instancia real no se tocaron.

## Cambios (un commit por tema)
- **Backend – tope de llamadas al driver ODBC** (`DB_MAX_CONCURRENT_CALLS`, por defecto 2): con 8 clientes la API pasa de 4,4 a 28,2 req/s (p95 7,0 s → 0,75 s); con 32, de 3,5 a 26,1 req/s. Sin cambio con un cliente.
- **Backend – muestras del sensor por tandas:** 400 muestras pasan de 403 `INSERT` (211 ms) a 4 escrituras (52 ms), misma transacción.
- **Backend – defecto funcional:** `notifyGroupMeasurement` usaba `.is_(True)`, que SQL Server recibe como `IS 1` (error 102): el aviso al grupo nunca se enviaba. Corregido, con guarda estática, y enviado en segundo plano. **Efecto visible:** quienes activaron ese aviso empezarán a recibirlo.
- **Frontend:** carga diferida por pantalla con precarga de la ruta (JS inicial 297 → 124–196 KB; FCP en 3G de 2,2–2,8 s a 1,26–1,70 s), esqueletos de carga, e `useLatestRequest` contra respuestas viejas que pisaban a las nuevas (pacientes, historial, dispositivos, transferencias).
- **Nginx:** gzip -9 precomprimido, `Vary`, `robots.txt`, 404 para archivos inexistentes (antes HTML con 200) y `X-Robots-Tag` en el área privada.

## Pruebas
- Backend: 1980 pasaron, 0 fallaron, 13 omitidas (`gcc`, `redis-server` y `dpkg` no están en Windows), con las pruebas `*_sqlserver` activadas contra SQL Server 2022 descartable.
- Frontend: 700/700 (2 fallas previas eran rutas de Windows en una guarda estática).
- Pruebas nuevas: tope de llamadas (7), guarda `IS 1` (1), inserción por tandas (2), `useLatestRequest` (3) y 2 de carrera que fallan con el código anterior.

## Sin resolver (ver `docs/PENDIENTES.md`)
- Compilación del frontend de ~3 min 20 s: causa localizada en el tree-shaking de Rollup, sin solución.
- Dashboards con `TOP 50000`, y correo SMTP en línea en ~40 llamadas.
- Causa interna del driver ODBC y óptimo del tope en el servidor de destino: repetir el barrido allí.
- CLS de `/pacientes` en 3G inestable (0–0,13).

## Para revisar
- El tope de 2 se midió con 1 CPU en Docker Desktop; es configurable.
- La carga diferida pide más archivos por pantalla (HTTP/1.1 en el puerto 8080); a cambio, todas las cargas en frío mejoran.
