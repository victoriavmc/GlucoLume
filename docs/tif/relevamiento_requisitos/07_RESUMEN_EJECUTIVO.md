# 07 — Resumen ejecutivo del relevamiento de GlucoLume

**Ingeniería inversa del repositorio** · 21 de octubre de 2026 · Rama `master`, commit base `90d4063` (más una modificación sin confirmar en `database/reference/GlucoLume_DB_v5.sql`).

Este documento resume el relevamiento descrito en `01_INVENTARIO_MODULOS.md` a `06_BRECHAS_Y_PENDIENTES.md`. Es un inventario del sistema **tal como existe hoy**: no compara los resultados con la documentación académica anterior y no redacta el Trabajo de Integración Final (TIF). Está pensado como insumo para actualizar los apartados 8.3.1 (requerimientos funcionales), 8.3.2 (requerimientos no funcionales) y 8.3.3 (reglas de negocio).

## 1. Qué es el sistema

GlucoLume es un prototipo experimental de medición de oximetría y de glucosa con un dispositivo propio (Arduino UNO con sensor óptico MAX30100) y una aplicación web. La cadena técnica es: Arduino → USB o Bluetooth → puente de Windows → API FastAPI → SQL Server → aplicación React. Atiende a cuatro tipos de uso: cuentas individuales con grupos familiares, instituciones de salud con personal y pacientes, administración de la plataforma y un sitio público con contenido educativo. Los propios sketches del firmware y la documentación declaran que los resultados son experimentales, que la glucosa no está validada clínicamente y que no sirven para decisiones clínicas ni de dosificación de insulina.

## 2. Qué se relevó

| Elemento | Cantidad |
|---|---|
| Módulos del sistema | 24 |
| Reglas de negocio (RN) | 96 |
| Requerimientos funcionales (RF) | 100 |
| Requerimientos no funcionales (RNF) | 54 |
| Endpoints HTTP en `/api/v1` | 241 (todos asociados a un RF) |
| Tablas de la base de datos | 33 |
| Claves foráneas / restricciones CHECK / UNIQUE | 49 / 125 / 16 |
| Tipos de correo del catálogo | 68 (11 sin emisión) |
| Pruebas automatizadas | 1468 funciones de prueba en 99 archivos (backend); 646 casos en 50 archivos (frontend) |

### Estado de lo relevado

| Tipo | IMPLEMENTADO | PARCIAL | PREVISTO | Total |
|---|---|---|---|---|
| Reglas de negocio | 89 | 6 | 1 | 96 |
| Requerimientos funcionales | 87 | 10 | 3 | 100 |
| Requerimientos no funcionales | 44 | 8 | 2 | 54 |

Las definiciones de los estados figuran en `01_INVENTARIO_MODULOS.md`, sección 1.3. No se registró ningún elemento OBSOLETO como requerimiento; lo obsoleto aparece como comentarios y funciones de código (hallazgos H-03, H-05, H-15).

## 3. Qué se verificó y qué no

### 3.1 Ejecución de pruebas

| Verificación | Resultado |
|---|---|
| Suite de pruebas del backend (SQLite, configuración ficticia, sin base ni correo reales) | **1799 pasaron, 67 se omitieron, 1 falló** (17 min 51 s). La prueba que falló es `test_reference_schema.py::test_los_indices_de_los_modelos_estan_en_el_esquema_con_el_mismo_filtro` y confirma el hallazgo H-01 |
| Suite de pruebas del frontend | **No se ejecutó**: `node_modules` no está instalado y instalarlo modificaría el entorno |
| Pruebas contra SQL Server y de concurrencia | **No se ejecutaron** (requieren una base descartable) |
| Aplicación, hardware, Docker, correo y Google reales | **No se ejecutaron ni se probaron** |

Que las pruebas pasen demuestra los comportamientos que ejercitan; no demuestra que el sistema esté completo ni que cumpla requisitos de rendimiento o disponibilidad, que no tienen medición (ver sección 5).

### 3.2 Evidencia principal

El código fuente, las configuraciones y los scripts de base de datos fueron la evidencia principal. La documentación (`README.md`, `docs/`) y las pruebas se usaron para contrastar. No se leyeron ni se mostraron secretos: los archivos `.env`, `bridge.env` y `docker/db.env` no se abrieron y se comprobó que no están versionados.

## 4. Hallazgos principales

Ordenados por prioridad; el detalle y la evidencia están en `06_BRECHAS_Y_PENDIENTES.md`.

1. **El script de la base de datos de la copia de trabajo perdió 31 índices (H-01, alta).** `GlucoLume_DB_v5.sql` fue regenerado el 21/10/2026 y ya no contiene 15 índices únicos filtrados ni 16 índices de consulta que sí figuran en el commit. Varias reglas de integridad (un solo administrador del sistema, un grupo activo por cuenta, un paciente activo por documento, una matriz activa por ámbito, vínculos únicos) dependen de esos índices. La prueba automatizada de coincidencia de esquema ya falla por esta causa.
2. **Dos enlaces de los correos apuntan a rutas que el frontend no tiene (H-04, alta).** El botón «revisar seguridad» (`/cuenta/seguridad`) y el enlace para dejar de recibir el aviso de inicio de sesión (`/cuenta/notificaciones/desuscribir`) llevan a la página de inicio. La verificación fue estática.
3. **No existe algoritmo de estimación de glucosa en el servidor (H-02, alta).** La glucosa disponible proviene del firmware, con origen DEMO (sintético, por defecto), experimental o sin calibrar. La infraestructura de matrices, reglas y trazabilidad está implementada; el estimador es un punto de integración vacío.
4. **El firmware, el puente y el control del dispositivo no se verificaron con hardware real (H-13, alta).** Toda la adquisición se prueba con simulaciones.
5. **El trabajo de retención de pacientes no está programado (H-10, alta)** y tres políticas de conservación están desactivadas o sin aprobar: auditoría completa, personal histórico y mediciones de cuentas eliminadas (H-14, H-23).
6. **Los controles de base de datos y de cifrado en reposo están preparados, no verificados en la instalación real (H-20, alta).**
7. **El sistema asume una sola réplica del backend (H-07, media):** los límites de solicitudes, el monitor de ráfagas y todo el estado del dispositivo viven en memoria.
8. **Hay funcionalidades del backend sin pantalla (H-08, media):** panel por paciente, indicadores agregados, auditoría técnica anonimizada, reenvío de confirmaciones de creación y el inicio de mediciones por muestras crudas, entre otras.

## 5. Calidad: lo implementado frente a lo medido

El relevamiento de requerimientos no funcionales separó lo implementado de lo probado y de lo medido (`04_REQUERIMIENTOS_NO_FUNCIONALES.md`):

- **Seguridad:** la mayor parte de los controles está implementada y varios tienen pruebas (contraseñas con Argon2id, sesiones y tokens con rotación, bloqueo por intentos, límites por IP, MFA con cifrado de secretos, cabeceras de seguridad, autorización centralizada, mínimo privilegio, endurecimiento de contenedores). Algunas verificaciones de la documentación (escaneos de dependencias, comprobación de contenedores, cabeceras de Nginx) no son reproducibles desde el repositorio.
- **Rendimiento y disponibilidad:** existen controles de volumen, topes de transmisiones, comprobaciones de salud y degradación controlada, pero **no hay objetivos ni mediciones** de tiempo de respuesta, capacidad o disponibilidad (RNF-021 y RNF-027 figuran como previstos). Una configuración relacionada no equivale a un requisito cumplido.
- **Integridad:** la integridad de dominio y la concurrencia están implementadas y respaldadas por pruebas y por una evidencia histórica sobre SQL Server (16/10/2026, esquema anterior); el esquema actual no se probó en concurrencia y su script tiene el problema H-01.
- **Accesibilidad y adaptación a pantallas:** hay componentes accesibles con pruebas y mediciones declaradas en la documentación, hechas con herramientas externas.
- **Recuperación:** los scripts de respaldo y restauración existen y están ensayados según la documentación, sin política de retención aprobada ni objetivos de recuperación.

## 6. Qué se puede afirmar y qué no

| Puede afirmarse como implementado (con evidencia en código y pruebas que pasaron) | Debe declararse con reservas | No debe declararse como implementado |
|---|---|---|
| Registro, acceso con correo y Google, sesiones, MFA y recuperaciones; consentimientos; eliminación de cuenta con anonimización; período de gracia | Estimación experimental de glucosa: solo la informada por el firmware (en modo DEMO por defecto) | Estimación de glucosa por el servidor (RF-055) |
| Grupos familiares con compartición por permisos independientes | Aviso de inicio de sesión: la preferencia funciona, el enlace del correo no (RF-014) | Suscripciones, planes y pagos (RF-096) |
| Instituciones, roles, invitaciones, cupos, pausa, cierre y reapertura | Retención de pacientes, personal histórico y auditoría total (parcial, ver H-10, H-14) | Exportación de datos (RF-099) |
| Pacientes: separación entre información administrativa y de salud, transferencias, reasignaciones, baja con anonimización | Medición con el dispositivo: implementada y probada con simulación, sin hardware real | Objetivos de rendimiento y disponibilidad (RNF-021, RNF-027) |
| Dispositivos: inventario, estados, conexión, control exclusivo y órdenes al puente | Cifrado en reposo y respaldos (preparados, no aplicados a la instalación real) | |
| Matrices de referencia versionadas con reglas validadas | Accesibilidad y adaptación a pantallas (declaradas, no reproducidas) | |
| Auditoría con consulta por ámbito, señales de actividad sospechosa y conservación parcial | | |
| Administración de la plataforma: administrador único, moderadores, transferencia, control de instituciones | | |

## 7. Uso para los apartados del TIF

Sin redactar todavía el TIF, la correspondencia sugerida es:

| Apartado | Fuente en esta serie | Observaciones |
|---|---|---|
| 8.3.1 Requerimientos funcionales | `03_REQUERIMIENTOS_FUNCIONALES.md` (100 RF, con estado real y evidencia) | Declarar solo los IMPLEMENTADOS como funcionalidades existentes; los PARCIALES con su limitación; los PREVISTOS como alcance futuro |
| 8.3.2 Requerimientos no funcionales | `04_REQUERIMIENTOS_NO_FUNCIONALES.md` (54 RNF, con criterio de aceptación y distinción entre implementado, probado y medido) | No afirmar cumplimiento de rendimiento, disponibilidad o accesibilidad sin medición |
| 8.3.3 Reglas de negocio | `02_REGLAS_NEGOCIO.md` (96 RN) | Cada regla tiene evidencia, roles y estado |
| Trazabilidad | `05_MATRIZ_TRAZABILIDAD.md` | Relaciona RN, RF, RNF, endpoints, tablas y pruebas |
| Limitaciones y trabajo futuro | `06_BRECHAS_Y_PENDIENTES.md` | 24 hallazgos con prioridad |

Dos advertencias de uso: el código de `backend/app/services/device.py` y `matrix.py` conserva en sus comentarios las numeraciones `RF35 a RF37`, `RN43 a RN45` y `RF42, RF43, RF47 a RF49`, que corresponden a una numeración anterior. No se utilizaron como evidencia y no coinciden con la numeración de esta serie; deberán tratarse en la etapa de contraste con el TIF.

## 8. Limitaciones del relevamiento

- La interfaz se analizó de forma estática (rutas, módulos de acceso a la API y pantallas); no se abrió la aplicación en un navegador.
- No se pudo probar hardware, Docker, correo ni Google reales, ni ejecutar pruebas contra SQL Server o del frontend.
- Los números de línea citados corresponden a la lectura del 21/10/2026 y pueden desplazarse con cambios posteriores.
- La carpeta `OpenCode/` contiene un análisis previo con otra herramienta y no se utilizó.
- Las relaciones de la matriz de trazabilidad se generaron a partir de los propios documentos de la serie y del inventario de rutas; reflejan lo relevado, no una verificación independiente del comportamiento.

## 9. Cobertura de los módulos

Todos los módulos identificados en la Etapa 1 (M-01 a M-24) fueron revisados en alguna etapa:

| Módulos | Dónde se revisaron |
|---|---|
| M-01 a M-17 (funcionalidad de negocio) | Reglas en `02`, requerimientos en `03`, matriz en `05` |
| M-18 (base de datos) | `01`, `04` (RNF-028, RNF-036, RNF-046) y `06` (H-01, H-20) |
| M-19 (frontend transversal) | `03` (RF-100), `04` (RNF-038 a RNF-041) |
| M-20 y M-21 (firmware y puente) | `02` (RN-059, RN-067, RN-073, RN-074), `03` (RF-060 a RF-065), `06` (H-13) |
| M-22 (infraestructura) | `04` (RNF-012, RNF-013, RNF-024, RNF-049 a RNF-052) |
| M-23 (pruebas) | `04` (RNF-035), `06` (secciones 7 y 8), esta sección 3 |
| M-24 (documentación) | `06` (H-05, H-06, H-16 a H-18) |

## 10. Cómo continuar (sin ejecutar nada de esto todavía)

1. Resolver la diferencia del script de base de datos (H-01) antes de usarlo como evidencia o para crear una base nueva.
2. Contrastar este inventario con la documentación académica anterior (siguiente etapa del trabajo, fuera del alcance de este relevamiento).
3. Decidir el tratamiento de los hallazgos H-04, H-10 y H-13 antes de declarar las funcionalidades afectadas.
4. Definir objetivos medibles de rendimiento y disponibilidad si el TIF los va a afirmar.
