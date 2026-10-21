# 06 — Brechas, contradicciones y pendientes

**Relevamiento por ingeniería inversa** · Etapa 5 · 21 de octubre de 2026.

Este documento reúne lo que el contraste entre frontend, backend, firmware, Docker, SQL Server, documentación y pruebas dejó como diferencias, faltantes o puntos no verificables. Cada hallazgo tiene identificador `H-nn`, evidencia y una prioridad sugerida para quien deba corregirlo o declararlo.

**Prioridad:** Alta (afecta la integridad de datos, la seguridad o la veracidad de lo que se declara), Media (funcionalidad o control incompleto con alternativa o impacto acotado), Baja (documentación, comentarios o mejoras menores).

## 1. Cuadro de hallazgos

| ID | Hallazgo | Tipo | Prioridad |
|---|---|---|---|
| H-01 | El script de referencia `GlucoLume_DB_v5.sql` de la copia de trabajo perdió 31 índices respecto del commit | Integridad de datos | Alta |
| H-02 | No existe algoritmo de estimación de glucosa en el servidor | Funcionalidad prevista | Alta |
| H-03 | El aviso de reasignación pendiente a moderadores está definido pero no se invoca | Código obsoleto | Media |
| H-04 | Dos enlaces de los correos apuntan a rutas inexistentes del frontend | Defecto de integración | Alta |
| H-05 | El comentario de `personnelRetention.py` indica 120 meses por defecto; la configuración es 0 | Contradicción | Baja |
| H-06 | El código cita seis documentos que no existen | Documentación | Baja |
| H-07 | Estado de seguridad y del dispositivo en memoria: solo una réplica | Limitación de diseño | Media |
| H-08 | Funcionalidades del backend sin pantalla en el frontend | Disponibilidad | Media |
| H-09 | Once tipos de correo definidos sin emisión | Funcionalidad prevista | Baja |
| H-10 | El trabajo de retención de pacientes no está programado | Operación | Alta |
| H-11 | Suscripciones, planes y pagos: solo estructuras | Funcionalidad prevista | Baja |
| H-12 | No existe exportación de datos | Funcionalidad prevista | Baja |
| H-13 | Firmware y puente sin verificación con hardware real | Verificación | Alta |
| H-14 | Plazos de conservación sin aprobar (auditoría total y personal histórico) | Política | Media |
| H-15 | Comentarios y constantes de auditoría obsoletos o sin uso | Código obsoleto | Baja |
| H-16 | `docs/funcional/INDIVIDUAL.md` describe una política de privacidad ya corregida | Documentación obsoleta | Baja |
| H-17 | La auditoría técnica anonimizada no figura en la documentación ni tiene pantalla | Documentación y disponibilidad | Media |
| H-18 | Seis parámetros de configuración no figuran en `.env.example` | Documentación | Baja |
| H-19 | El flujo de muestras crudas no tiene punto de inicio en la interfaz | Disponibilidad | Media |
| H-20 | Permisos mínimos de base y cifrado en reposo preparados pero no verificados en la base real | Seguridad | Alta |
| H-21 | Verificaciones declaradas en la documentación que no se pueden reproducir desde el repositorio | Verificación | Media |
| H-22 | Pruebas no ejecutadas en esta revisión y pruebas omitidas | Verificación | Media |
| H-23 | Las mediciones de cuentas individuales eliminadas quedan sin plazo de borrado | Política | Media |
| H-24 | Validación legal de la política de privacidad pendiente | Cumplimiento | Media |

---

## 2. Detalle de los hallazgos

### H-01 — El script de la base de datos perdió los índices (Alta)

- **Qué se encontró:** la copia de trabajo de `database/reference/GlucoLume_DB_v5.sql` está modificada respecto del último commit (generada el 21/10/2026 a las 14:52:46 según su encabezado; el tamaño pasó de 220 144 a 207 644 bytes). La versión confirmada contiene 370 objetos con nombre de restricción o índice; la actual, 339. Se perdieron **31 índices**:
  - 15 índices únicos filtrados `UX_*`: `UX_GrupoUsuario_administrador`, `UX_GrupoUsuario_grupoActivo`, `UX_GrupoUsuario_vinculoVigente`, `UX_InstitucionUsuario_vinculoVigente`, `UX_Matriz_globalActiva`, `UX_Matriz_institucionActiva`, `UX_PerfilMedicion_cohorte`, `UX_PerfilMedicion_consumidor`, `UX_PerfilMedicion_dniInstitucion`, `UX_ReasignacionPaciente_pendiente`, `UX_TransferenciaAdministracion_pendiente`, `UX_TransferenciaPerfil_pendiente`, `UX_Usuario_administradorUnico`, `UX_Usuario_correoElectronico`, `UX_Usuario_usuario`.
  - 16 índices de consulta `IX_*`: los de `Auditoria` (fecha, acción, institución, módulo, usuario), `AuditoriaContexto` (correlación, identificador, IP), `AuditoriaTecnicaMedicion`, `ConsentimientoUsuario`, `Medicion` (estado y vencimiento de retención), `ReasignacionPaciente`, `TransferenciaAdministracion`, `TransferenciaPerfil` y `Usuario` (vencimiento de gracia).
  No hay objetos nuevos en la versión actual: solo faltan los de la confirmada. Las 125 restricciones CHECK, las 49 claves foráneas y las 16 restricciones UNIQUE no cambiaron.
- **Evidencia:** comparación de nombres de objetos entre el commit `90d4063` y la copia de trabajo; `git status` (archivo modificado); `backend/tests/test_reference_schema.py` falló en la ejecución del 21/10/2026: `test_los_indices_de_los_modelos_estan_en_el_esquema_con_el_mismo_filtro` con `AssertionError: IX_AuditoriaTecnica_fecha`.
- **Por qué importa:** muchas reglas de negocio que el sistema da por garantizadas por la base dependen de esos índices (RN-005, RN-026, RN-027, RN-042, RN-045, RN-047, RN-048, RN-050, RN-076, RN-079, RN-081). Una base creada con esta versión del script no las haría cumplir ante solicitudes simultáneas; el servicio traduciría el conflicto solo si la base lo informa. Además, se pierden los índices de rendimiento de la auditoría y de las mediciones.
- **Causa probable (no verificada):** una regeneración del script desde SQL Server Management Studio con la opción de scripting de índices desactivada. No se verificó cómo se generó.
- **Qué hace falta:** regenerar el script incluyendo índices y claves únicas, o restaurar la versión confirmada, y volver a ejecutar la prueba `test_reference_schema.py`. También conviene comprobar con `python -m app.cli.schemaCheck` que la base instalada conserva los índices.

### H-02 — Sin algoritmo de estimación de glucosa en el servidor (Alta)

- **Qué se encontró:** `glucoseEstimator` es `None`; una medición de glucosa por muestras termina inválida. La glucosa que aparece en el sistema proviene del firmware (origen DEMO, experimental o sin calibrar). El propio firmware declara que su valor es una correlación ajustada con referencias capilares y no una medición validada, y que arranca en modo DEMO por defecto (`MODO_GLUCO_DEMO_INICIAL 1`).
- **Evidencia:** `backend/app/services/measurement.py:121-125,482-485`; `firmware/GlucoLume_MAX30100/GlucoLume_MAX30100.ino:1-31,128-133`; `docs/PENDIENTES.md` («Estimador de glucosa del servidor… solo un punto de integración»).
- **Relación:** RF-055, RN-060, RNF-041. Tampoco hay validación clínica del dispositivo (`docs/PENDIENTES.md`: «validación clínica, fuera del alcance del software»).
- **Qué hace falta:** definir el algoritmo y validarlo, o mantener el alcance declarado como experimental sin estimación del servidor.

### H-03 — El aviso de reasignación a moderadores no se invoca (Media)

- **Qué se encontró:** `reassignments.notifyManagers()` y el encabezado de `reassignments.py` describen un aviso por correo a los moderadores (o al propietario si no hay moderador) cuando un operador se desvincula con pacientes a cargo. El único llamador es `backend/tests/legacy_offboarding.py`, un asistente de pruebas. Hoy la baja de un operador con pacientes se bloquea hasta reasignarlos (`PACIENTES_ASIGNADOS`) y las tareas pendientes solo nacen al «regularizar» a un operador ya desvinculado, sin aviso.
- **Evidencia:** `backend/app/services/reassignments.py:1-12,142-152`; `backend/app/services/institution.py:1241-1249`; búsqueda de llamadores en `backend/`.
- **Relación:** RN-050, RF-042. El tipo de correo `PACIENTES_PENDIENTES_REASIGNACION` existe (y figura en la auditoría) pero no se emite.
- **Qué hace falta:** decidir si el aviso corresponde a la regularización y, si no, retirar la función y actualizar el encabezado.

### H-04 — Enlaces de correo hacia rutas inexistentes del frontend (Alta)

- **Qué se encontró:** `backend/app/services/email.py:44-67` define las rutas del frontend a las que apuntan los botones de los correos. Dos no existen en el enrutador de React (`frontend/src/App.jsx`):
  - `seguridad` → `/cuenta/seguridad`. La pantalla de seguridad está en `/app/seguridad`. Los correos de nuevo inicio de sesión, acceso inusual, cambio de contraseña, MFA y Google usan este enlace (`urlSeguridad`).
  - `desuscribirInicioSesion` → `/cuenta/notificaciones/desuscribir`. No existe ninguna pantalla ni llamada a `POST /auth/notifications/new-login/unsubscribe` en el frontend.
  La ruta comodín del enrutador redirige a la página de inicio, por lo que el botón lleva a la página de presentación.
- **Evidencia:** `backend/app/services/email.py:44-67`; `frontend/src/App.jsx` (rutas `/cuenta/eliminar/confirmar`, `/app/seguridad`; ninguna `/cuenta/seguridad` ni `/cuenta/notificaciones/desuscribir`); búsqueda de `desuscrib` y `unsubscribe` en `frontend/src` sin resultados. La comprobación fue estática, no en un navegador.
- **Relación:** RN-019, RF-014, RF-093.
- **Prueba faltante:** una prueba que compare `FRONTEND_ROUTES` con las rutas del frontend habría detectado el defecto.

### H-05 — Plazo de minimización del personal: comentario y configuración no coinciden (Baja)

- **Qué se encontró:** el encabezado de `personnelRetention.py` indica «PERSONNEL_RETENTION_MONTHS; 120 meses por defecto». La configuración real es `PERSONNEL_RETENTION_MONTHS: int = 0` (desactivado), igual que `.env.example`, `docs/DESPLIEGUE.md` y `docs/PRIVACIDAD_Y_RETENCION.md`.
- **Evidencia:** `backend/app/services/personnelRetention.py:1-15`; `backend/app/core/config.py:113-116`; `.env.example:127`.
- **Relación:** RN-094, RF-095. Corresponde corregir el comentario.

### H-06 — El código cita documentos que no existen (Baja)

- **Qué se encontró:** archivos de código y configuración remiten a `docs/AUDITORIA_ADMINISTRATIVA.md`, `docs/CICLO_VIDA_CUENTAS_INSTITUCIONALES.md`, `docs/DOCKER.md`, `docs/PRIVACIDAD.md`, `docs/PUENTE.md` y `docs/RETENCION_Y_ANONIMIZACION.md`. No están en el repositorio; su contenido está repartido en `docs/DESPLIEGUE.md`, `SEGURIDAD.md`, `PRIVACIDAD_Y_RETENCION.md` y `DISPOSITIVOS_Y_ADQUISICION.md`.
- **Evidencia:** referencias en `.env.example`, `backend/app/core/config.py:118`, `services/auditRetention.py`, `securityMonitor.py`, `consent.py:16`, `measurementRetention.py`, `compose.yaml`, `compose.serial.yaml`, `frontend/Dockerfile` y varias pruebas.
- **Resultado inverso:** la comparación sistemática de rutas de archivo, endpoints y variables mencionados en `docs/` **no** encontró elementos documentados que falten en el código.

### H-07 — Estado en memoria (Media)

- **Qué se encontró:** los límites de solicitudes por IP, el monitor de ráfagas, los topes de transmisiones, los limitadores de búsquedas y de contacto y todo el estado del dispositivo (control temporal, sesión, lecturas y órdenes al puente) viven en la memoria de un proceso. El diseño y la documentación asumen una sola réplica.
- **Evidencia:** `backend/app/api/rateLimit.py:10-12`, `services/securityMonitor.py:1-25`, `api/streams.py:1-10`, `services/contact.py`, `acquisition/telemetry.py`; `docs/PENDIENTES.md`.
- **Relación:** RNF-047, RN-018, RN-072. Un reinicio del backend libera el control del dispositivo.

### H-08 — Funcionalidades del backend sin pantalla (Media)

Verificado por búsqueda estática en `frontend/src`:

| Funcionalidad del backend | Endpoint | Observación |
|---|---|---|
| Panel por paciente | `GET /institutions/{id}/patients/{idPerfil}/dashboard` | La ruta de pantalla redirige al detalle del paciente; ningún módulo de acceso lo consume (RF-074) |
| Indicadores agregados de la institución | `GET /institutions/{id}/indicators` | El panel institucional usa `/dashboard` (RF-076) |
| Estadísticas de un paciente | `GET .../patients/{idPerfil}/measurements/statistics` | La pantalla usa la evolución (RF-052) |
| Matriz efectiva de la institución | `GET /institutions/{id}/matrices/effective` | La pantalla usa el resumen `/matrices` (RF-070) |
| Reenvío de la confirmación de creación | `POST /groups/{id}/creation-notice`, `POST /institutions/{id}/creation-notice` | Sin pantalla (RF-018, RF-025) |
| Auditoría técnica anonimizada | `GET /audit/technical-measurements`, `/summary` | Sin pantalla (RF-090, H-17) |
| Desactivar el aviso desde el correo | `POST /auth/notifications/new-login/unsubscribe` | Sin pantalla (H-04) |
| Resolver dispositivo por identificador | `POST /devices/resolve` | Sin consumo desde la interfaz (RF-058) |
| Probar la comunicación serie | `POST /acquisition/probe` | La función de acceso existe y no se usa (RF-065) |
| Crear una medición para muestras crudas | `POST /measurements` | La función `startMeasurement` no se usa (H-19, RF-046) |
| Registrar muestras | `POST /measurements/{id}/samples` | Lo usa el puente o un cliente externo, no la interfaz (RF-047) |

En sentido inverso, no se encontró ninguna ruta del frontend sin ruta correspondiente en el backend: la comparación automática de 143 literales de ruta de `frontend/src/api` no dejó ninguna sin coincidencia directa, salvo ocho rutas armadas con una base o una acción variable, que corresponden a rutas existentes.

### H-09 — Tipos de correo sin emisión (Baja)

`EMAIL_CAMBIADO`, `CODIGO_MFA_EMAIL`, `METODO_MFA_CAMBIADO`, `GOOGLE_DESVINCULADO`, `MIEMBRO_ELIMINADO`, `ADMIN_GRUPO_CAMBIADO`, `ROL_INSTITUCIONAL_CAMBIADO`, `MEDICION_REGISTRADA`, `MEDICION_FUERA_UMBRAL`, `ERROR_MEDICION` e `INFORMACION_RETENCION_DATOS` están en el catálogo (con plantilla) pero ningún código de la aplicación los emite. Parte de ellos corresponde a funciones que no existen (cambio de correo, desvincular Google, cambio de rol, umbrales de medición). Evidencia: conteo de usos de `EmailEventType.<nombre>` en `backend/app/`.

### H-10 — Trabajo de retención de pacientes sin programar (Alta)

- **Qué se encontró:** el servicio `lifecycle` de Compose ejecuta eliminación de cuentas, depuración de cuentas invitadas, minimización del personal y conservación de la auditoría, pero **no** la retención de pacientes (`purgeInstitutionalRetention`). Según `docs/PENDIENTES.md` se ejecuta «a mano, con `--confirmo-base`»; programarlo sobre datos reales requiere autorización. Mientras tanto, los datos de pacientes dados de baja con la migración de retención aplicada se anonimizan en el acto, pero los de instituciones cerradas y los vencimientos de mediciones anonimizadas dependen de ese trabajo.
- **Evidencia:** `backend/app/jobs/accountLifecycle.py:1-60`, `backend/app/jobs/purgeInstitutionalRetention.py`, `compose.yaml` (servicio `lifecycle`).
- **Relación:** RN-095, RF-094.

### H-11 — Suscripciones, planes y pagos (Baja)

Existen siete tablas, sus modelos y esquemas, un permiso `SUSCRIPCIONES_Y_PAGOS` y una pantalla «Próximamente». Los servicios `subscription.py` y `notificationConfig.py` están vacíos y no hay endpoints. La tabla `ConfiguracionNotificacion` tampoco tiene uso. Relación: RF-096.

### H-12 — Sin exportación de datos (Baja)

No existe ninguna función de exportación (CSV, PDF, descarga masiva). `exportAudit.auditedExport` es el camino obligatorio para futuras exportaciones y una prueba lo exige. Relación: RF-099, RN-090.

### H-13 — Firmware y puente sin verificación con hardware (Alta)

La documentación indica que los sketches se compilaron pero «no se cargaron en una placa» (uso del 84 % de la RAM del Arduino UNO en el principal), y `docs/PENDIENTES.md` lista como prioridad P1 verificar con el Arduino real (USB y Bluetooth, adquisición sostenida, reconexión, guardado completo y control temporal entre dos cuentas). Todas las pruebas automatizadas de adquisición usan un puerto o un puente simulado. Relación: RF-047, RF-048, RF-063, RF-065, RNF-026.

### H-14 — Plazos de conservación sin aprobar (Media)

`AUDIT_RETENTION_MONTHS=0` (la auditoría completa se conserva sin límite) y `PERSONNEL_RETENTION_MONTHS=0` (sin minimización) están en 0 porque el plazo legal no fue aprobado; la propuesta técnica para la auditoría es de 24 a 36 meses y la referencia para el personal es de 120 meses. Relación: RN-088, RN-094, RF-091, RF-095.

### H-15 — Comentarios y constantes de auditoría obsoletos (Baja)

- `auditClassification.py:36-39`: `ACCION_CAMBIAR_LIMITE` («CAMBIAR_LIMITE_INSTITUCION») está descrita como prevista «hoy el límite… lo fija el administrador de la base», pero el cambio de límite existe (`PUT /platform/institutions/{id}/capacity`) y registra la acción `MODIFICAR_CUPOS_INSTITUCION`. La constante `CAMBIAR_VIGENCIA_INSTITUCION` no corresponde a ninguna función (la institución no tiene vigencia).
- `reassignments.py` (encabezado): describe la creación de tareas al desvincular a un operador, flujo reemplazado por la reasignación previa (H-03).

### H-16 — Documento funcional con una afirmación ya corregida (Baja)

`docs/funcional/INDIVIDUAL.md` (sección 9) y `docs/HISTORIAL.md` dicen que la política de privacidad «todavía dice lo contrario» sobre el almacenamiento de la IP durante 90 días (GL-23). El código y la página de privacidad ya están en la versión 1.1 (`consent.py:29`, `PrivacyPolicy.jsx:15,94,252`) y `docs/SEGURIDAD.md` marca GL-23 como corregido.

### H-17 — Auditoría técnica anonimizada sin documentación ni pantalla (Media)

La tabla `AuditoriaTecnicaMedicion`, el registro de eventos, la conservación de 180 días y los endpoints de consulta existen, pero ninguna búsqueda textual en `docs/` encuentra «auditoría técnica», «AuditoriaTecnica» ni «180 días», y el frontend no tiene pantalla. Relación: RN-089, RF-090.

### H-18 — Parámetros de configuración fuera de `.env.example` (Baja)

`PLATFORM_MFA_REQUIRED`, `PLATFORM_INVITATION_EXPIRE_HOURS`, `PLATFORM_RESET_EXPIRE_MINUTES`, `PASSWORD_RESET_EXPIRE_MINUTES`, `MAINTENANCE_INTERVAL_SECONDS` y `SECURITY_ALERT_EMAIL_MINUTES` existen en `config.py` con valor por defecto, pero no figuran en la plantilla de configuración.

### H-19 — Flujo de muestras crudas sin inicio en la interfaz (Media)

El backend ofrece dos caminos para medir: la sesión con el dispositivo (telemetría, procesada por el firmware) y la adquisición de muestras crudas, donde el servidor calcula SpO₂ y frecuencia cardíaca. En la interfaz, la creación de la medición por `POST /measurements` (`startMeasurement`) no se usa en ninguna pantalla; `LiveAcquisition` y los botones de finalizar y cancelar subsisten para una medición ya existente. Por eso el cálculo de oximetría del servidor (`oximetry.py`) solo se alcanza desde clientes que usen la API directamente. No se ejecutó la aplicación para confirmar si alguna pantalla crea esas mediciones por otro camino. Relación: RF-046, RF-047, RF-065, RN-059.

### H-20 — Controles de base de datos preparados pero no verificados en la instalación real (Alta)

El script de permisos de mínimo privilegio y el procedimiento de cifrado en reposo y respaldo cifrado están preparados y documentados como ensayados en una instancia descartable. La instalación indicada es SQL Server 2025 Express, que no admite TDE ni respaldos cifrados ni comprimidos; la alternativa documentada (cifrado de volumen, respaldo con suma de verificación y restauración de prueba mensual) no tiene evidencia de aplicación en el repositorio. Sin el script de permisos, la protección de solo inserción de la auditoría descansa en el código. Relación: RNF-014, RNF-018, RNF-031, RNF-052.

### H-21 — Verificaciones declaradas que no se pueden reproducir (Media)

La documentación declara resultados que dependen de herramientas o entornos fuera del repositorio: el barrido de accesibilidad de 243 vistas (`docs/FRONTEND.md`), la comprobación de contenedores en ejecución, los escaneos `pip-audit` y `npm audit` y la compilación del firmware (`docs/SEGURIDAD.md`, `docs/DISPOSITIVOS_Y_ADQUISICION.md`), el tamaño del paquete del frontend y la suite del frontend (677 casos según `docs/FRONTEND.md`; el conteo estático de este relevamiento es de 646 casos `it`/`test`, la diferencia no se investigó). No se ejecutó nada de esto en esta revisión.

### H-22 — Pruebas no ejecutadas y pruebas omitidas (Media)

- **Backend:** se ejecutó la suite completa con SQLite y la configuración ficticia del repositorio: 1799 pruebas pasaron, 67 se omitieron y 1 falló (la de H-01). Las omitidas son pruebas condicionadas, entre ellas las que exigen una base SQL Server descartable (`test_*_sqlserver.py`).
- **Frontend:** no se ejecutaron (`frontend/node_modules` no está instalado; instalar dependencias modificaría el entorno).
- **Contra SQL Server real:** ninguna prueba de concurrencia ni de integración con SQL Server se ejecutó. La evidencia de concurrencia disponible (16/10/2026) usó un esquema anterior, ya retirado.

### H-23 — Mediciones de cuentas eliminadas sin plazo de borrado (Media)

Al eliminar una cuenta individual, las mediciones se conservan desidentificadas sin plazo automático de borrado y, a diferencia de las de pacientes, sin anonimización en cohorte. La decisión está abierta en `docs/PENDIENTES.md` (prioridad P2). Relación: RN-023.

### H-24 — Validación legal pendiente (Media)

El texto de la política de privacidad (versión 1.1), la base legal del envío de resultados por correo y la inscripción de la base de datos o el comité de ética figuran como pendientes (`docs/PENDIENTES.md`, prioridad P1). Relación: RNF-054.

---

## 3. Requerimientos parcialmente implementados

| Tipo | Identificador | Qué falta | Hallazgo |
|---|---|---|---|
| RF | RF-014 | Pantalla del enlace de desuscripción del correo | H-04 |
| RF | RF-046 | La interfaz no usa el endpoint de creación de mediciones | H-19 |
| RF | RF-047 | El endpoint de muestras no se usa desde la interfaz; sin hardware | H-19, H-13 |
| RF | RF-074 | Sin pantalla para el panel por paciente | H-08 |
| RF | RF-076 | Sin pantalla para los indicadores | H-08 |
| RF | RF-090 | Sin pantalla para la auditoría técnica | H-17 |
| RF | RF-091 | Eliminación total de la auditoría desactivada | H-14 |
| RF | RF-093 | Once correos sin emisión; dos enlaces inválidos | H-09, H-04 |
| RF | RF-094 | Trabajo de retención sin programar | H-10 |
| RF | RF-095 | Desactivado por defecto | H-14 |
| RN | RN-019, RN-060, RN-088, RN-089, RN-094, RN-095 (y RN-050 en lo que respecta al aviso a moderadores) | Ver cada regla | H-04, H-02, H-14, H-17, H-10, H-03 |
| RNF | RNF-014, RNF-018, RNF-023, RNF-028, RNF-047, RNF-051, RNF-052, RNF-054 | Ver cada requerimiento | H-20, H-01, H-07, H-24 |

## 4. Requerimientos previstos (no implementados)

RF-055 (estimación de glucosa en el servidor), RF-096 (suscripciones y pagos), RF-099 (exportación de datos), RNF-021 (objetivos de rendimiento), RNF-027 (objetivo de disponibilidad) y RN-090 (auditoría de exportaciones).

## 5. Requerimientos implementados sin documentación

Verificado por búsqueda textual en `README.md` y `docs/`:

| Elemento implementado | Dónde está | Observación |
|---|---|---|
| Auditoría técnica anonimizada de mediciones (tabla, conservación de 180 días, endpoints) | `services/technicalAudit.py`, `api/v1/audit.py:137-147` | Ausente de la documentación (H-17) |
| Validación del dígito verificador del CUIT | `schemas/institution.py:76-120` | La documentación menciona el CUIT, no su validación |
| Reenvío de la confirmación de creación de grupos e instituciones | `services/notifications.py`, rutas `creation-notice` | No se menciona en la documentación |
| Consulta de estado de un CUIT antes de crear (`legal-id/status`) | `services/institution.py:361-382` | Solo descrita de forma general |
| Continuar la sesión en otro origen (`session-transfer`) | `services/auth.py:662-730` | Descrita solo en `docs/DESPLIEGUE.md` |
| Valores de configuración listados en H-18 | `core/config.py` | No figuran en `.env.example` |

## 6. Reglas de negocio dispersas en varios módulos

Las siguientes reglas no tienen un único punto de aplicación; cualquier cambio exige revisar todos los lugares:

| Regla | Dónde se aplica |
|---|---|
| RN-012 Autorización por pedido | `api/deps.py`, `services/auth.py` (`resolveAccessSession`), `institution.py` (`requireMembership`), `group.py`, `platform.py`, `device.py` (`Scope`), `matrix.py`, `patientAccess.py` |
| RN-046 Separación administrativo y salud | `patientAccess.py`, `institutionPatients.py`, `measurement.py`, `dashboard.py`, `patientAnalytics.py`, `profileTransfers.py`, resolución de nombres en `audit.py`, indicadores `medicionesAutorizadas` del frontend |
| RN-024 Período de gracia | `accountGrace.py`, `institution.py` (alta, reapertura, aceptación, revocación y cierre), `auth.py` (verificación y Google), `accountLifecycle.py`, `jobs/accountLifecycle.py` |
| RN-061 Exclusión de datos DEMO | filtro `NOT_DEMO` en `measurement.py`, `group.py`, `dashboard.py`, `patientAnalytics.py`, `platformDashboard.py`, correos y frontend |
| RN-018 Límites de solicitudes | `rateLimit.py`, `group.py`, `institution.py`, `contact.py`, `resultEmailConfirmation.py`, `institutionSupport.py`, `measurement.py`, Nginx |
| RN-007 Bloqueo por intentos | `auth.py`, `mfa.py`, `accountDeletion.py`, `institution.py` (`_reauthenticate`), `platform.py` (`reauthenticate`): comparten contador y bloqueo |
| RN-071 Uso compartido del dispositivo | `config.py`, `device.py` (`usableBy`), `deviceConnection.py`, `measurement.py` (`_deviceUsable`), `telemetry.py` (`bridgeAuthority`) |
| RN-040 Institución pausada | `institution.py` (`requireMembership`), `platformInstitutions.py`, `telemetry.py`, `acquisition.py` |
| RN-051, RN-095 Retención de pacientes | `institutionPatients.py`, `institution.py` (`applyLogicalClosure`), `measurementRetention.py`, `institutionalRetention.py`, `resultEmailStore.py`, trabajos |
| RN-054 Período operativo de la institución | `patientAccess.py`, `institutionPatients.py`, `profileTransfers.py`, `reassignments.py` |
| RN-085 Registro de auditoría | `audit.py` más una llamada en cada módulo que modifica datos |
| RN-021 Consentimiento experimental | `consent.py`, `measurement.py`, `telemetry.py`, `ExperimentalConsent.jsx` |

## 7. Controles de seguridad declarados que no pudieron verificarse

| Control | Declarado en | Qué se pudo comprobar | Qué falta |
|---|---|---|---|
| Contenedores sin privilegios, solo lectura y `cap_drop` | `docs/SEGURIDAD.md` | La configuración está en `compose.yaml` | Verificación con contenedores en ejecución |
| Cabeceras de Nginx y CSP | `docs/SEGURIDAD.md` | Están en `default.conf.template` | Prueba automatizada de las cabeceras reales |
| Parámetros de Argon2id | `docs/SEGURIDAD.md` | Se usa Argon2id con parámetros por defecto de la biblioteca | Prueba del formato y parámetros |
| `pip-audit` y `npm audit` sin vulnerabilidades | `docs/SEGURIDAD.md` | Nada | Ejecutar los escaneos |
| Permisos mínimos de base y auditoría de solo inserción en la base | `docs/SEGURIDAD.md` | El script existe | Constancia de su aplicación en la base real (H-20) |
| TDE o cifrado de volumen y respaldos cifrados | `docs/SEGURIDAD.md`, `docs/BASE_DE_DATOS.md` | Los scripts existen | Evidencia de aplicación (H-20) |
| Ausencia de inyección SQL y XSS | `docs/SEGURIDAD.md` | Consultas parametrizadas y ausencia de `dangerouslySetInnerHTML` en el frontend (búsqueda estática) | Análisis dinámico |
| Alerta por correo ante ráfagas de rechazos | `docs/SEGURIDAD.md` | Código y pruebas (`test_audit_security.py`) | SMTP real |
| Envío SMTP con certificado verificado | `docs/PENDIENTES.md` | Código y pruebas con contexto TLS | Envío real |

## 8. Pruebas faltantes

| Área sin prueba específica | Detalle |
|---|---|
| Coherencia entre rutas de los correos y rutas del frontend | Ninguna prueba compara `FRONTEND_ROUTES` con `App.jsx`; permitió H-04 |
| Nginx | Sin pruebas de límites, cabeceras ni proxy de flujos |
| Endurecimiento de contenedores y Compose | Sin pruebas |
| Argon2id | Sin prueba del formato ni de los parámetros |
| Rendimiento y carga | No hay pruebas ni objetivos (RNF-021) |
| Accesibilidad automatizada | No hay herramienta de auditoría de accesibilidad en el repositorio |
| Pruebas de extremo a extremo con navegador | No hay Playwright, Cypress ni equivalente en `frontend/package.json` |
| Hardware | Firmware, puente real, USB y Bluetooth |
| Integraciones reales | Google OAuth y SMTP reales |
| Concurrencia sobre SQL Server con el esquema v5 | Solo evidencia histórica del esquema anterior |
| Scripts de respaldo, restauración y permisos | Solo ensayo declarado |
| Aviso de reasignación a moderadores | Solo un asistente de pruebas lo invoca (H-03) |
| Flujo de muestras crudas desde la interfaz | Sin pantalla de inicio (H-19) |
| Cobertura de código | No hay medición |

## 9. Dependencias entre requerimientos

Las dependencias entre RF están en `05_MATRIZ_TRAZABILIDAD.md`, sección 6. Las más relevantes para el cambio y la planificación son: medir (RF-046 y RF-048) depende de consentimiento, perfil, dispositivo operativo identificado, control del equipo y, para glucosa por matriz, matriz con regla; el módulo de pacientes depende de personal incorporado (RF-029) e institución (RF-025); la retención (RF-094) depende de la baja (RF-043) o del cierre (RF-034); la administración de plataforma depende de cuentas con MFA (RF-077, RF-009).

## 10. Pendientes que el proyecto declara y su estado verificado

`docs/PENDIENTES.md` lista pendientes propios. Se contrastaron con el código:

| Pendiente declarado | Prioridad | Estado verificado en el código |
|---|---|---|
| Verificar con el Arduino real | P1 | Sin evidencia (H-13) |
| Revisión legal de la política y base legal | P1 | Sin evidencia (H-24) |
| Estimador de glucosa del servidor | P2 | Confirmado: no existe (H-02) |
| Control del dispositivo en memoria | P2 | Confirmado (H-07) |
| Programar `purgeInstitutionalRetention` | P2 | Confirmado: no programado (H-10) |
| Decidir el destino de las mediciones de cuentas eliminadas | P2 | Confirmado (H-23) |
| Probar SMTP real y confirmación del correo de resultados | P2 | Sin evidencia |
| Versionar con Git y conservar historial | P2 | El repositorio ya está versionado (2 commits); el pendiente podría retirarse |
| Minimización del personal con plazo validado | P3 | Confirmado: desactivada (H-14) |
| Plazo de la auditoría total | P3 | Confirmado: sin límite (H-14) |
| Redis para límites con más de una réplica | P3 | Confirmado (H-07) |
| Suscripciones y pagos | P3 | Confirmado: previsto (H-11) |
| Exportaciones con `auditedExport` | P3 | Confirmado: previsto (H-12) |
| Token por puente | P3 | Confirmado: hay un token compartido con rotación |
| Mejoras de frontend (tokens de diseño, bundle de 887 kB) | P3 | No verificado (H-21) |

Hallazgos que **no** figuran en `docs/PENDIENTES.md` y surgieron de este relevamiento: H-01, H-03, H-04, H-05, H-06, H-08 (parcialmente), H-15, H-16, H-17, H-18 y H-19.
