# GlucoLume: resumen del sistema para el TIF

Resumen para redactar el Trabajo de Integración Final. Sale del relevamiento del 21/10/2026 ([relevamiento_requisitos/](relevamiento_requisitos/)) y lo actualiza con los cambios registrados hasta el 25/10/2026 en [HISTORIAL.md](../HISTORIAL.md). Los detalles de cada requerimiento están en la serie de relevamiento; este documento no los repite.

Los identificadores de hallazgos se citan como **R-nn** (relevamiento, `06_BRECHAS_Y_PENDIENTES.md`) y **H-nn** (auditoría de seguridad, [SEGURIDAD.md](../SEGURIDAD.md)). Son numeraciones distintas: el relevamiento usa `H-01` a `H-24` con otro significado, y la auditoría usa `H-01` a `H-17`. Por eso el relevamiento se cita siempre con prefijo R.

## 1. Qué es el sistema

GlucoLume es un prototipo experimental de medición de oximetría y de glucosa. Usa un dispositivo propio con un Arduino UNO y un sensor óptico MAX30100, y una aplicación web.

La cadena técnica es: Arduino → USB o Bluetooth → puente de Windows → API FastAPI → SQL Server → aplicación React.

Atiende cuatro tipos de uso:
- **Cuentas individuales** con grupos familiares.
- **Instituciones de salud** con personal y pacientes.
- **Administración de la plataforma.**
- **Sitio público** con contenido educativo.

**Advertencia para el TIF:** el firmware, la documentación y los sketches declaran que los resultados son experimentales. La glucosa no está validada clínicamente y el sistema no sirve para decisiones clínicas ni de dosificación de insulina.

## 2. Cifras del relevamiento

| Elemento | Cantidad |
|---|---|
| Módulos del sistema | 24 |
| Reglas de negocio (RN) | 96 |
| Requerimientos funcionales (RF) | 100 |
| Requerimientos no funcionales (RNF) | 54 |
| Endpoints HTTP en `/api/v1` | 241, todos asociados a un RF |
| Tablas de la base de datos | 33 |
| Claves foráneas / CHECK / UNIQUE | 49 / 125 / 16 |
| Tipos de correo del catálogo | 68 (11 sin emisión) |
| Pruebas automatizadas | 1468 funciones en 99 archivos (backend); 646 casos en 50 archivos (frontend) |

## 3. Estado de lo relevado

| Tipo | Implementado | Parcial | Previsto | Total |
|---|---|---|---|---|
| Reglas de negocio | 89 | 6 | 1 | 96 |
| Requerimientos funcionales | 87 | 10 | 3 | 100 |
| Requerimientos no funcionales | 44 | 8 | 2 | 54 |

Ningún elemento se registró como obsoleto. Lo obsoleto aparece en comentarios y funciones de código (R-03, R-15).

### Previstos (no implementados)

- **RF-055:** estimación de glucosa en el servidor.
- **RF-096:** suscripciones, planes y pagos.
- **RF-099:** exportación de datos.
- **RN-090:** auditoría de exportaciones.
- **RNF-021 y RNF-027:** objetivos de rendimiento y de disponibilidad.

### Parciales (principales)

- **RF-014:** el enlace de desuscripción del correo no lleva a ninguna pantalla (R-04).
- **RF-074 y RF-076:** falta la pantalla del panel por paciente y la de indicadores (R-08).
- **RF-090:** falta la pantalla de auditoría técnica (R-17).
- **RF-091 y RF-095:** la eliminación total de auditoría y el plazo de retención de pacientes están desactivados por defecto (R-14, R-10).
- **RF-094:** el trabajo de retención de pacientes no está programado (R-10).
- **RF-046 y RF-047:** la interfaz no usa todos los endpoints de medición (R-19).

## 4. Qué se puede afirmar

Los criterios siguen los de [07_RESUMEN_EJECUTIVO.md](relevamiento_requisitos/07_RESUMEN_EJECUTIVO.md) §6.

**Afirmable como implementado**, con evidencia en código y pruebas que pasaron:
- Registro, acceso con correo y Google, sesiones, MFA y recuperación de cuenta.
- Consentimientos y eliminación de cuenta con anonimización. Período de gracia.
- Grupos familiares con compartición por permisos independientes.
- Instituciones: roles, invitaciones, cupos, pausa, cierre y reapertura.
- Pacientes: separación entre datos administrativos y de salud, transferencias, reasignaciones y baja con anonimización.
- Dispositivos: inventario, estados, conexión, control exclusivo y órdenes al puente.
- Matrices de referencia versionadas con reglas validadas.
- Auditoría con consulta por ámbito y conservación parcial.
- Administración de la plataforma: administrador único, moderadores, transferencia y control de instituciones.

**Declarar con reservas:**
- Estimación de glucosa: solo la que informa el firmware, en modo DEMO por defecto (R-02).
- Aviso de inicio de sesión: la preferencia funciona, pero el enlace del correo no (R-04).
- Medición con el dispositivo: probada con simulación, sin hardware real (R-13).
- Cifrado en reposo y respaldos: preparados, no aplicados a la instalación real (R-20).
- Accesibilidad y adaptación a pantallas: declaradas, no reproducidas.

**No declarar como implementado:**
- Estimación de glucosa por el servidor (RF-055).
- Suscripciones, planes y pagos (RF-096).
- Exportación de datos (RF-099).
- Objetivos de rendimiento y disponibilidad (RNF-021, RNF-027).

## 5. Verificación

| Verificación | Estado |
|---|---|
| Pruebas del backend, 21/10 (SQLite, sin base ni correo reales) | 1799 pasaron, 67 omitidas, 1 falló. La que falló confirma R-01. |
| Pruebas del backend, 23/10 (con SQL Server 2022 real y pruebas `*_sqlserver` activadas) | 1980 pasaron, 0 fallaron, 13 omitidas por herramientas ausentes en Windows ([HISTORIAL.md](../HISTORIAL.md)) |
| Pruebas del frontend | 685 pasaron con React 19.1.10 (23/10). No se ejecutaron en el relevamiento del 21/10. |
| Hardware real, Docker de producción, correo y Google reales | No verificados en el repositorio. Ver R-13 y R-20. |
| Rendimiento y disponibilidad | Sin objetivos ni mediciones formales (RNF-021, RNF-027). Hay mediciones puntuales de la revisión del 24/10 ([RENDIMIENTO.md](../RENDIMIENTO.md)), que no son requisitos cumplidos. |

Que las pruebas pasen demuestra los comportamientos que ejercitan. No demuestra que el sistema esté completo ni que cumpla requisitos no medidos.

## 6. Hallazgos del relevamiento y su estado

Estado según los registros del HISTORIAL hasta el 25/10. El HISTORIAL no registra el cierre de la mayoría de estos hallazgos, así que figuran como abiertos salvo que se indique lo contrario.

| ID | Hallazgo | Prioridad | Estado |
|---|---|---|---|
| R-01 | El script de referencia `GlucoLume_DB_v5.sql` perdió 31 índices respecto del commit | Alta | Revisar. El 23/10 se corrigió el script de actualización (`GlucoLume_actualizar_instalada.sql`) y la instalación nueva tiene 33 índices `IX_`/`UX_`. No se confirmó que el archivo de referencia esté corregido. |
| R-02 | No existe estimador de glucosa en el servidor | Alta | Abierto (es una funcionalidad prevista) |
| R-03 | El aviso de reasignación a moderadores está definido pero no se invoca | Media | Abierto |
| R-04 | Dos enlaces de correo apuntan a rutas que el frontend no tiene | Alta | Abierto |
| R-05 | Comentario y configuración del plazo de minimización no coinciden | Baja | Abierto |
| R-06 | El código cita seis documentos que no existen | Baja | Abierto |
| R-07 | Estado en memoria: solo una réplica del backend | Media | Limitación de diseño |
| R-08 | Funcionalidades del backend sin pantalla | Media | Abierto |
| R-09 | Once tipos de correo sin emisión | Baja | Abierto |
| R-10 | Trabajo de retención de pacientes sin programar | Alta | Abierto |
| R-11 | Suscripciones, planes y pagos: solo estructuras | Baja | Previsto |
| R-12 | Sin exportación de datos | Baja | Previsto |
| R-13 | Firmware y puente sin verificación con hardware real | Alta | Abierto (ver pendiente P1 en [PENDIENTES.md](../PENDIENTES.md)) |
| R-14 | Plazos de conservación sin aprobar | Media | Abierto (pendiente de asesoría legal) |
| R-15 | Comentarios y constantes de auditoría obsoletos | Baja | Abierto |
| R-16 | Un documento funcional describe una política de privacidad ya corregida | Baja | Revisar |
| R-17 | La auditoría técnica anonimizada no tiene documentación ni pantalla | Media | Abierto |
| R-18 | Seis parámetros de configuración no están en `.env.example` | Baja | Abierto |
| R-19 | El flujo de muestras crudas no tiene punto de inicio en la interfaz | Media | Abierto |
| R-20 | Permisos mínimos de base y cifrado en reposo preparados, no verificados en la base real | Alta | Abierto (pendiente P1) |
| R-21 | Verificaciones declaradas que no se pueden reproducir desde el repositorio | Media | Abierto |
| R-22 | Pruebas no ejecutadas o omitidas en la revisión del 21/10 | Media | Parcialmente cubierto por las ejecuciones del 23/10 |
| R-23 | Mediciones de cuentas eliminadas sin plazo de borrado | Media | Abierto |
| R-24 | Validación legal de la política de privacidad pendiente | Media | Abierto (pendiente P1) |

## 7. Remediación de seguridad posterior

El 23/10 se trabajó sobre los hallazgos H-01 a H-17 de la auditoría de seguridad, con un commit por hallazgo. Ese trabajo es independiente de la tabla anterior.

- **Aplicados en código o configuración:** H-01 (`-CopiaExterna` en el script de respaldo), H-04 (advertencia de arranque), H-07, H-08 (`JWT_PREVIOUS_SECRET`), H-11, H-12, H-13, H-14, H-15, H-16 y H-17.
- **Abiertos, sin riesgo aceptado:** H-05, H-06, H-09 y H-10. H-03 tampoco se tocó.
- **Pendientes de acción humana:** H-01 (elegir el destino de la copia externa), H-02, H-03, H-04 y H-08 (rotar los secretos reales).
- **No verificados en el entorno de ensayo:** el script de PowerShell, el formato de log de Nginx y el build de producción del frontend.
- **Validados en entorno descartable con datos sintéticos:** H-02 y H-16 contra SQL Server (76/76 y 51/51), H-06 con dos procesos de la API y Redis (12/12), H-09 en Chromium (24/24), H-14 con Nginx real (20/20 y 23/23) y H-01 con los scripts `.ps1` (33/33).

El detalle por hallazgo está en [SEGURIDAD.md](../SEGURIDAD.md) §2.0.1 y en [HISTORIAL.md](../HISTORIAL.md).

## 8. Limitaciones que el TIF debe declarar

- La interfaz se analizó de forma estática. No se abrió la aplicación en un navegador en el relevamiento del 21/10.
- El hardware, Docker de producción, el correo y Google no se probaron en el relevamiento.
- Los números de línea de la serie corresponden a la lectura del 21/10 y pueden haber cambiado.
- La carpeta `OpenCode/` contiene un análisis previo y no se usó como evidencia.
- Las relaciones de la matriz de trazabilidad reflejan lo relevado. No son una verificación independiente del comportamiento.

## 9. Advertencias de terminología

- Algunos comentarios del código citan numeraciones anteriores: `RF35` a `RF37`, `RN43` a `RN45` y `RF42`, `RF43`, `RF47` a `RF49`. No coinciden con la numeración actual y no se usaron como evidencia.
- Los identificadores de la auditoría (H-nn) y del relevamiento (R-nn) son distintos. En el TIF conviene citar siempre el prefijo.

## 10. Dónde está cada detalle

| Para | Documento |
|---|---|
| Módulos y su inventario | [01_INVENTARIO_MODULOS.md](relevamiento_requisitos/01_INVENTARIO_MODULOS.md) |
| Reglas de negocio (96) | [02_REGLAS_NEGOCIO.md](relevamiento_requisitos/02_REGLAS_NEGOCIO.md) |
| Requerimientos funcionales (100) | [03_REQUERIMIENTOS_FUNCIONALES.md](relevamiento_requisitos/03_REQUERIMIENTOS_FUNCIONALES.md) |
| Requerimientos no funcionales (54) | [04_REQUERIMIENTOS_NO_FUNCIONALES.md](relevamiento_requisitos/04_REQUERIMIENTOS_NO_FUNCIONALES.md) |
| Trazabilidad entre elementos | [05_MATRIZ_TRAZABILIDAD.md](relevamiento_requisitos/05_MATRIZ_TRAZABILIDAD.md) |
| Hallazgos completos con evidencia | [06_BRECHAS_Y_PENDIENTES.md](relevamiento_requisitos/06_BRECHAS_Y_PENDIENTES.md) |
| Resumen del relevamiento | [07_RESUMEN_EJECUTIVO.md](relevamiento_requisitos/07_RESUMEN_EJECUTIVO.md) |
| Cambios posteriores | [HISTORIAL.md](../HISTORIAL.md) |
| Pendientes actuales | [PENDIENTES.md](../PENDIENTES.md) |
