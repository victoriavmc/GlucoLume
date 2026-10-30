# Pendientes

Solo problemas abiertos, riesgos sin resolver, pruebas faltantes y funcionalidades incompletas. Cuando algo se resuelve y se verifica, se
registra en [HISTORIAL.md](HISTORIAL.md) y se quita de aquí. Prioridad: **P0** antes de cualquier uso con datos reales; **P1** antes de
producción; **P2** próxima iteración; **P3** planificado. Estado de los hallazgos de seguridad: [SEGURIDAD.md](SEGURIDAD.md) §2; los
procedimientos preparados que requieren autorización están en [SEGURIDAD.md](SEGURIDAD.md) §5.1.

## Seguridad y configuración

> Revisado el 23/10/2026 tras la integración en `master`. H-03, H-05 y H-10 siguen abiertos; ningún riesgo fue aceptado. Qué se verificó y qué falta: [seguridad/VERIFICACIONES_PENDIENTES_WINDOWS.md](seguridad/VERIFICACIONES_PENDIENTES_WINDOWS.md).

| Prioridad | Pendiente | Referencia |
|---|---|---|
| P1 | **Windows:** `docker compose build backend frontend` **completo** con los Dockerfiles oficiales (en el entorno cloud no se pudo: `deb.debian.org` y `dl-cdn.alpinelinux.org` bloqueados) y levantar `backend frontend` contra tu SQL Express ([DESPLIEGUE.md](DESPLIEGUE.md) §3.0) | Integración |
| P1 | H-03: cifrado en reposo (BitLocker o edición con TDE); **no implementado** | H-03 |
| P1 | Copia externa de los respaldos (`GlucoLume_respaldo.ps1 -CopiaExterna`) y custodia de la frase fuera del equipo; probar la restauración desde esa copia. Requiere elegir el destino | H-01 |
| P1 | Aplicar `GlucoLume_permisos.sql` y `…_quitar_roles_fijos.sql` en la instancia real (SEGURIDAD §5.1 paso 3), **primero en una copia restaurada**. Validado en SQL Server 2022 descartable (76/76 y API real 51/51); falta tu instancia | H-02 |
| P1 | Fijar con asesoría legal `AUDIT_RETENTION_MONTHS` y `PERSONNEL_RETENTION_MONTHS`; producción advierte mientras estén en 0 | H-04 |
| P2 | Rotar los secretos reales con el procedimiento de SEGURIDAD §5.1 (`JWT_PREVIOUS_SECRET`, `BRIDGE_PREVIOUS_TOKEN_UNTIL`) | H-08, GL-20 |
| P2 | H-05: validar la firma de líneas en la placa real (sketch completo, tiempos con el HC-06, EEPROM), provisionar la clave, cambiar el PIN del módulo (acción física) y decidir sobre la confidencialidad del enlace (BLE o aceptación formal); el sketch original no firma | H-05 |
| P2 | H-09: probar el login (local, Google, MFA, «Recordarme», cierre de sesión) con el build de producción en un navegador real de tu despliegue (HTTPS, mismo *site*) y, cuando no queden puentes ni scripts heredados, poner `REFRESH_TOKEN_IN_BODY=false`. Decidir sobre el flujo `VITE_LOGIN_ORIGIN` (login en `localhost`, no ensayado) | H-09 |
| P3 | Mejoras para una instalación productiva (no requeridas para el prototipo local): certificado de servidor en SQL Server con `DB_SERVER_CERTIFICATE`, BitLocker y copia de la clave de respaldos fuera del equipo (SEGURIDAD §5.1 pasos 4 y 5) | GL-07 |
| P3 | Antes de una instalación productiva: rotar `JWT_SECRET`, `SESSION_SECRET`, `BRIDGE_TOKEN` y credenciales de base y SMTP; no compartir la carpeta con los `.env` | GL-20 |
| P3 | Windows: repetir lo de [VERIFICACIONES_PENDIENTES_WINDOWS.md](seguridad/VERIFICACIONES_PENDIENTES_WINDOWS.md) §2 (respaldos con DPAPI y tarea programada) y §1 (suite con tu `.env`) | H-01 |
| P3 | H-10 / GL-13: confirmar en el rastreador de Debian cuándo se corrige `zlib` (CVE-2026-85091), reconstruir con `--pull --build-arg ZLIB_MIN_VERSION=<versión>` y repetir el escaneo; `python docker/tools/baseImageVersions.py` muestra qué versión trae la imagen base | H-10, GL-13 |
| P2 | Aplicar `GlucoLume_agregar_puente_credencial.sql` a la base real, crear las credenciales con `python -m app.cli.bridgeTokens` y poner `BRIDGE_ALLOW_SHARED_TOKEN=false` | H-16, GL-11 |
| P3 | Plazo de conservación total de la auditoría aprobado con asesoría legal (propuesta 24–36 meses) | GL-16 |
| P3 | Redis para el **monitor de ráfagas** si hay más de una réplica (los límites por IP ya pueden usar Redis: `compose.redis.yaml`, H-06); WAF delante de Nginx; MFA obligatoria para propietarios (decisión funcional y de costos) | GL-15, auditoría 18/10 |
| P3 | SQL Server Audit para cambios de límites y vigencia hechos fuera de la aplicación | Auditoría 18/10 |

## Rendimiento

> Revisión del 23/10/2026: [RENDIMIENTO.md](RENDIMIENTO.md). La rama `perf/rendimiento-2026-10-23` espera revisión; no está fusionada en `master`.

| Prioridad | Pendiente | Referencia |
|---|---|---|
| P2 | **Compilación del frontend de ~3 min 20 s** (Windows y Docker): el 75 % es el tree-shaking de Rollup al dibujar `<App/>`. Descartados con medición: `lucide-react`, datos de consejos, opciones de `treeshake`, `ErrorBoundary`, CSS. Probar un Rollup/Vite más nuevo **solo si se demuestra beneficio y compatibilidad** | RENDIMIENTO §3.2 |
| P2 | Dashboards de institución, operador y paciente: 16–31 sentencias y `TOP 50000` traído a Python (institución: p50 142 ms con 8,7 mil mediciones, crece con los datos). Llevar las agregaciones a SQL y comparar los resultados fila a fila | RENDIMIENTO §3.5 |
| P2 | Correo SMTP **en línea** en unas 40 llamadas (hasta 20 s de *timeout* dentro de la petición HTTP): decidir una cola de salida persistente (*outbox*) conservando la auditoría del resultado del envío | RENDIMIENTO §3.4 |
| P2 | Repetir en el servidor de destino el barrido de `DB_MAX_CONCURRENT_CALLS` (0/2/3/4) y averiguar la causa dentro del driver `msodbcsql18` (caída de ~9× con ≥ 6 hilos en Docker Desktop/WSL2); probar otra versión del driver solo si se demuestra beneficio | RENDIMIENTO §3.1 |
| P3 | INP con un guion de interacción real (hoy solo TBT); el TBT del dashboard de institución en 3G con CPU 4× sigue en 1,2 s (render pesado de gráficos); el CLS de `/pacientes` en 3G es inestable (0–0,13) | RENDIMIENTO §9 |
| P3 | HTTP/2 en el Nginx del frontend (hoy HTTP/1.1; lo da el proxy Caddy): cada pantalla pide más archivos tras la carga diferida | RENDIMIENTO §5 |
| P3 | `canonical` y `sitemap.xml` de la portada cuando se conozca el dominio de producción; reevaluar el prerenderizado solo si el SEO de la portada pasa a importar | RENDIMIENTO §7 |
| P3 | Imagen del frontend: `musl` 1.2.6-r2 con el CVE-2026-107891 (sin severidad; corregido en 1.2.6-r6, que Alpine 3.24 todavía no publica: el repositorio ofrece r3). Reconstruir con `--pull`/`--no-cache-filter runtime` cuando salga r6 y repetir `docker scout` | H-10 |

## Base de datos (DEC-02)

| Prioridad | Pendiente | Referencia |
|---|---|---|
| P2 | Versionar la carpeta con Git y conservar el historial | GL-09 |

## Dispositivo y adquisición (DEC-01)

| Prioridad | Pendiente |
|---|---|
| P1 | Verificar con el Arduino real (USB y Bluetooth): adquisición sostenida, reconexión con el sensor activo, guardado completo, control temporal entre dos cuentas. **Requiere el hardware** |
| P2 | El control vive en memoria: un reinicio del backend lo libera; evaluar avisar a la cuenta afectada |
| P3 | Calidad de la señal PPG y de las estimaciones experimentales sobre personas (validación clínica, fuera del alcance del software) |

## Pruebas y entorno

| Prioridad | Pendiente | Referencia |
|---|---|---|
| P2 | Probar en el entorno final el envío SMTP real con certificado verificado y el circuito de confirmación del correo de resultados | GL-04, GL-08 |

## Privacidad y legal

| Prioridad | Pendiente |
|---|---|
| P1 | Revisión del texto de la política (versión 1.1) por la cátedra o el tutor y, si corresponde, por asesoría legal; base legal del envío de resultados por correo; comité de ética o inscripción de la base |
| P2 | Decidir si las mediciones de cuentas individuales eliminadas se anonimizan como las de pacientes (hoy quedan desidentificadas sin plazo) |
| P2 | Programar `purgeInstitutionalRetention` (hoy a mano, con `--confirmo-base`): programarlo sobre datos reales requiere autorización |
| P3 | Minimización del personal histórico (`PERSONNEL_RETENTION_MONTHS`, referencia de 120 meses a validar) |
| P3 | Nombres de personal minimizado en `Auditoria.detalle`: hoy se ocultan al leer. Una purga física solo con la política anterior aprobada, y la haría la cuenta de conservación (la API no modifica la auditoría, GL-03) |

## Funcionalidades incompletas

| Prioridad | Pendiente |
|---|---|
| P2 | Estimador de glucosa del servidor (`glucoseEstimator` es solo un punto de integración) |
| P3 | Suscripciones y pagos («Próximamente») |
| P3 | Exportaciones: deben usar `auditedExport`; `test_toda_exportacion_futura_pasa_por_audited_export` lo exige |
| P3 | Interfaz administrativa avanzada para la política de retención (la creación de una institución ya informa consentimiento y conservación) |

## Notificaciones

Detalle y causas en [NOTIFICACIONES.md](NOTIFICACIONES.md) §9 y §11; pasos en §12.

| Prioridad | Pendiente |
|---|---|
| P1 | **Aplicar en la instalación en uso** `GlucoLume_notificaciones_v2.sql` (después de `GlucoLume_notificaciones_usuario.sql`), el nuevo `GRANT DELETE` de `GlucoLume_permisos.sql`, definir `DB_JOBS_USER` y levantar el servicio `notifications` (NOTIFICACIONES.md §12). Ensayado con SQL Server 2022 real **descartable**, no en tu base: allí, hoy, los recordatorios solo se generan al abrir la bandeja y el backend nuevo dejaría Notificaciones «no disponible» |
| P2 | Probar la entrega real por el SMTP configurado (Gmail): se verificó el envío contra un SMTP de prueba con STARTTLS, no la aceptación del proveedor ni SPF/DKIM |
| P2 | Completar una medición real con el dispositivo y comprobar el aviso `MEDICION_GRUPO` (se probó con la función que invocan `measurement.py` y `telemetry.py`) |
| P3 | Llevar a la bandeja los avisos de cuentas de plataforma e instituciones (hoy solo correo) y definir una zona horaria por usuario (hoy todo es hora de Argentina) |
| P3 | Prueba visual automatizada de la bandeja y las preferencias en móvil y escritorio (hoy solo se revisó a mano en un navegador) |

## Frontend

| Prioridad | Pendiente |
|---|---|
| P3 | Escala de espaciado, tipografía, radios y breakpoints; ~420 colores hex sueltos por migrar a tokens |
| P3 | `AppShell` compartido (sidebar, drawer y foco duplicados en `AuthenticatedLayout` y `PlatformLayout`), `Breadcrumbs`, `LoadingState`, variantes de `Kpi` |
| P3 | Mover las clases base (`.page-head`, `.panel`, `.data-list`) a una hoja global; dividir `AuthenticatedLayout.css` por módulo |
| P3 | Bundle inicial de ~887 kB tras la carga diferida; lo que queda son las pantallas de cuenta, mediciones, pacientes y adquisición |
| P3 | Exports usados solo en su propio archivo (candidatos de limpieza sin revisar uno por uno) |
| P3 | Cobertura visual pendiente: estados de error simulados, modales abiertos, formularios con validación e interacción con teclado |
