# Índice de la documentación

Índice por fecha y por estado. No mueve ni renombra archivos: solo los ordena. Lo abierto está en [PENDIENTES.md](PENDIENTES.md) y lo cerrado, en [HISTORIAL.md](HISTORIAL.md).

Las fechas de cada documento son la de su primera incorporación al repositorio (git). Las fechas de los hitos son las que registra el HISTORIAL. Por eso algunas no coinciden: el informe de auditoría aparece como «21/10» en el HISTORIAL, pero su PDF entró al repositorio el 20/10.

## 1. Estado actual

**Abierto:** 7 pendientes P1, 14 P2 y 23 P3 en [PENDIENTES.md](PENDIENTES.md). No hay ninguno P0.

Los P1 son:

| Pendiente | Referencia |
|---|---|
| Build completo de `backend` y `frontend` con los Dockerfiles oficiales en Windows | [DESPLIEGUE.md](DESPLIEGUE.md) §3.0 |
| Cifrado en reposo (BitLocker o TDE), no implementado | H-03 |
| Copia externa de los respaldos y prueba de restauración desde esa copia | H-01 |
| Aplicar los scripts de permisos SQL en la instancia real, primero en una copia | H-02, [SEGURIDAD.md](SEGURIDAD.md) §5.1 |
| Fijar los plazos de retención con asesoría legal | H-04 |
| Verificar con el Arduino real (USB y Bluetooth) | [DISPOSITIVOS_Y_ADQUISICION.md](DISPOSITIVOS_Y_ADQUISICION.md) |
| Revisar el texto de la política de privacidad, versión 1.1 | [PRIVACIDAD_Y_RETENCION.md](PRIVACIDAD_Y_RETENCION.md) |

**Auditoría:** no está aprobada. H-03, H-05 y H-10 siguen abiertos. Las verificaciones pendientes en Windows están en [seguridad/VERIFICACIONES_PENDIENTES_WINDOWS.md](seguridad/VERIFICACIONES_PENDIENTES_WINDOWS.md).

## 2. Cronología

| Fecha | Hito | Documentos |
|---|---|---|
| 10/10 | Línea base de CVE | [evidencias/CVE_LINEA_BASE_2026-10-10.md](evidencias/CVE_LINEA_BASE_2026-10-10.md) |
| 16/10 | Pruebas de concurrencia en SQL Server | [evidencias/PRUEBAS_CONCURRENCIA_SQLSERVER_2026-10-16.md](evidencias/PRUEBAS_CONCURRENCIA_SQLSERVER_2026-10-16.md) |
| 17/10 | Bloques de corrección de optimización y seguridad | [HISTORIAL.md](HISTORIAL.md) |
| 18/10 | Auditoría de seguridad (referenciada como «18/10» en pendientes) | [HISTORIAL.md](HISTORIAL.md) |
| 19/10 | Ajuste de alcance del TIF, remediación en el entorno real con autorización y verificación de solo lectura | [HISTORIAL.md](HISTORIAL.md), [funcional/](funcional/) |
| 20/10 | Protección de auditoría (GL-03), error de inicio de sesión con Google, análisis del código | [HISTORIAL.md](HISTORIAL.md), [OpenCode/](../OpenCode/) |
| 21/10 | Relevamiento de requisitos del TIF y remediación del informe de auditoría (H-01 a H-17) | [tif/relevamiento_requisitos/](tif/relevamiento_requisitos/) |
| 23/10 | Integración en `master`, validación integral en entorno descartable, revisión de rendimiento en rama aparte | [HISTORIAL.md](HISTORIAL.md), [seguridad/](seguridad/) |
| 24/10 | Revisión de rendimiento: causas, cambios y mediciones | [RENDIMIENTO.md](RENDIMIENTO.md), [evidencias/rendimiento/](evidencias/rendimiento/README.md) |
| 25/10 | Prototipo físico, persistencia en SQL Server, copia automática de la base de Docker a Windows | [evidencias/prototipo_fisico/](evidencias/prototipo_fisico/), [evidencias/persistencia_sqlserver/](evidencias/persistencia_sqlserver/) |
| 29/10 | Rediseño del módulo de Notificaciones: bandeja y preferencias separadas, unicidad de avisos y recordatorios, aviso de equipo nuevo | [NOTIFICACIONES.md](NOTIFICACIONES.md), [HISTORIAL.md](HISTORIAL.md) |

## 3. Documentos por estado

Estado según su papel y según lo que dicen [PENDIENTES.md](PENDIENTES.md) e [HISTORIAL.md](HISTORIAL.md). No revisé cada documento línea por línea.

### Vigentes (usar como referencia)

| Documento | Creado | Qué cubre |
|---|---|---|
| [SEGURIDAD.md](SEGURIDAD.md) | 20/10 | Hallazgos H-01 a H-17 y su estado. Tiene pendientes abiertos. |
| [BASE_DE_DATOS.md](BASE_DE_DATOS.md) | 20/10 | Instalación, actualización y permisos |
| [DESPLIEGUE.md](DESPLIEGUE.md) | 20/10 | Guía de Windows y estado de cada servicio. Tiene pendientes abiertos. |
| [DISPOSITIVOS_Y_ADQUISICION.md](DISPOSITIVOS_Y_ADQUISICION.md) | 20/10 | Dispositivo, Bluetooth y adquisición |
| [FRONTEND.md](FRONTEND.md) | 20/10 | Interfaz |
| [NOTIFICACIONES.md](NOTIFICACIONES.md) | 29/10 | Bandeja, preferencias, reglas de negocio, deduplicación, recordatorios, endpoints, migración y pruebas del módulo de Notificaciones. Tiene pendientes abiertos. |
| [RENDIMIENTO.md](RENDIMIENTO.md) | 24/10 | Revisión de rendimiento. Los cambios están en una rama aparte, sin fusionar. |
| [PRIVACIDAD_Y_RETENCION.md](PRIVACIDAD_Y_RETENCION.md) | 20/10 | Política de privacidad. Tiene un pendiente P1. |
| [MANUAL_USUARIO.md](MANUAL_USUARIO.md) | 20/10 | Manual de usuario |
| [funcional/](funcional/) (`GRUPO_FAMILIAR`, `INDIVIDUAL`, `INSTITUCION`, `PLATAFORMA`) | 20/10 | Reglas de negocio por tipo de cuenta |
| [seguridad/VERIFICACIONES_PENDIENTES_WINDOWS.md](seguridad/VERIFICACIONES_PENDIENTES_WINDOWS.md) | 23/10 | Lista de verificaciones pendientes en Windows |

### Control del proyecto

| Documento | Creado | Qué cubre |
|---|---|---|
| [PENDIENTES.md](PENDIENTES.md) | 20/10 | Solo lo abierto, por prioridad. Lo resuelto se pasa al HISTORIAL. |
| [HISTORIAL.md](HISTORIAL.md) | 20/10 | Cambios, correcciones y decisiones en orden cronológico inverso |

| [tif/TIF_resumen_del_sistema.md](tif/TIF_resumen_del_sistema.md) | 25/10 | Resumen limpio del sistema para el TIF, con el estado actualizado al 25/10 |

### Históricos (no reflejan el estado actual)

| Documento | Creado | Por qué es histórico |
|---|---|---|
| [tif/relevamiento_requisitos/01 a 07](tif/relevamiento_requisitos/) | 21/10 | Relevamiento de requisitos del TIF. Sus brechas pueden estar cubiertas por el HISTORIAL. Revisar antes de usarlas. |
| [seguridad/auditorias/](seguridad/auditorias/) (tres PDF de auditoría y uno de infraestructura IA) | 19/10 a 23/10 | Informes de la fecha en que se hicieron. Las correcciones están en el HISTORIAL. |
| [OpenCode/02A_01_RUTAS.md](../OpenCode/02A_01_RUTAS.md) y [02A_02_SESIONES.md](../OpenCode/02A_02_SESIONES.md) | 20/10 | Análisis del código antes de las remediaciones. Por ejemplo, el refresh token pasó a cookie HttpOnly el 23/10 (H-09), así que la parte de sesiones está desactualizada. |
| [OpenCode/ETAPA_01_INVENTARIO.md](../OpenCode/ETAPA_01_INVENTARIO.md) | 20/10 | Inventario inicial del proyecto |

### Evidencias (datos de prueba, no editar)

| Carpeta | Contenido |
|---|---|
| [evidencias/validacion_integral/](evidencias/validacion_integral/README.md) | Validación del 23/10: suites, Nginx, Redis, PowerShell, Trivy |
| [evidencias/rendimiento/](evidencias/rendimiento/README.md) | Scripts y resultados de rendimiento |
| [evidencias/persistencia_sqlserver/](evidencias/persistencia_sqlserver/resultados/verificacion_2026-10-25.txt) | Verificación de persistencia del 25/10 |
| [evidencias/prototipo_fisico/](evidencias/prototipo_fisico/) | Prueba física del prototipo del 25/10 |
| [evidencias/H09_navegador/](evidencias/H09_navegador/README.md) | Prueba de navegador para H-09 |

### Diagramas y planificación (OpenCode)

| Archivo | Creado | Qué es |
|---|---|---|
| [OpenCode/der/der.html](../OpenCode/der/der.html), `der.svg`, `der.png` | 23/10 | Diagrama entidad-relación, generado con `generar_der.py` |
| [OpenCode/KANBAN_TIF/tablero_kanban_glucolume.html](../OpenCode/KANBAN_TIF/tablero_kanban_glucolume.html) | 20/10 | Tablero Kanban del TIF |
| [OpenCode/KANBAN_TIF/secuencia_desarrollo_glucolume.png](../OpenCode/KANBAN_TIF/secuencia_desarrollo_glucolume.png) | 20/10 | Secuencia de etapas de desarrollo |

## 4. Cómo leer la carpeta

1. Para saber qué falta, empezar por [PENDIENTES.md](PENDIENTES.md).
2. Para saber qué cambió y cuándo, ir a [HISTORIAL.md](HISTORIAL.md).
3. Para operar o desplegar, usar los documentos vigentes de la sección 3.
4. Los documentos de `OpenCode/` y de `tif/` son de análisis y planificación. Antes de citarlos como estado actual, comparar con el HISTORIAL.
