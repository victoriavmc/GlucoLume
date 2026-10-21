# 01 — Inventario de módulos del sistema GlucoLume

**Relevamiento por ingeniería inversa del repositorio** · Fecha de relevamiento: 21 de octubre de 2026 · Rama `master` (commit base `90d4063`, más una modificación sin confirmar en `database/reference/GlucoLume_DB_v5.sql`).

Este documento es la **Etapa 1** del relevamiento. No contrasta los resultados con la documentación académica anterior: solo establece el inventario del sistema tal como existe en el código, las configuraciones y los scripts. Los demás entregables de la serie son `02_REGLAS_NEGOCIO.md`, `03_REQUERIMIENTOS_FUNCIONALES.md`, `04_REQUERIMIENTOS_NO_FUNCIONALES.md`, `05_MATRIZ_TRAZABILIDAD.md`, `06_BRECHAS_Y_PENDIENTES.md` y `07_RESUMEN_EJECUTIVO.md`.

## 1. Alcance y método

### 1.1 Qué se analizó

| Área | Evidencia examinada | Volumen |
|---|---|---|
| Backend (FastAPI, SQLAlchemy, SQL Server) | `backend/app/**` (servicios, modelos, esquemas, API v1, núcleo, trabajos, CLI, integraciones, correos) | 249 archivos versionados, 241 endpoints HTTP |
| Frontend (React) | `frontend/src/**` | 274 archivos versionados, 50 archivos de pruebas |
| Base de datos | `database/reference/GlucoLume_DB_v5.sql`, `GlucoLume_permisos*.sql`, `GlucoLume_cifrado_y_respaldo.sql` y modelos SQLAlchemy | 33 tablas, 49 claves foráneas, 125 restricciones CHECK, 16 restricciones UNIQUE |
| Firmware y puente serie | `firmware/**`, `acquisition/bridge/**`, `backend/app/acquisition/**` | 2 sketches Arduino, 2 programas del puente |
| Infraestructura | `compose*.yaml`, `docker/**`, `backend/Dockerfile`, `frontend/Dockerfile`, `.env.example` | 4 archivos Compose, Nginx, Caddy, SQL Server y compilación de firmware en contenedores |
| Pruebas | `backend/tests/**`, `frontend/src/**/*.test.*` | 99 archivos con 1468 funciones `test_` (backend) y 50 archivos con 646 casos `it`/`test` (frontend) |
| Documentación del proyecto | `README.md`, `docs/**`, `OpenCode/**` | Se usó únicamente para contrastar, no como evidencia principal |

### 1.2 Qué no se hizo

- No se modificó código, base de datos, configuración, dependencias ni servicios. Los únicos archivos creados son los de esta carpeta (`docs/tif/relevamiento_requisitos/`).
- No se leyó ni se mostró el contenido de `.env`, `acquisition/bridge/bridge.env` ni `docker/db.env`. Solo se comprobó, sin abrirlos, que están excluidos del control de versiones (`.gitignore:100-102`) y que únicamente se versionan los archivos `*.example`.
- No se ejecutó la aplicación, no se conectó a ninguna base de datos real y no se probó el hardware.
- La carpeta `OpenCode/` contiene un análisis previo hecho con otra herramienta. No se utilizó como evidencia.

### 1.3 Criterio de estados

| Estado | Significado en esta serie |
|---|---|
| **IMPLEMENTADO** | Existe el código que realiza la funcionalidad o regla y está conectado a un punto de entrada alcanzable (endpoint, trabajo programado, CLI o pantalla). |
| **PARCIAL** | Existe una parte verificable, pero falta algo esencial (la interfaz, el algoritmo, el programador, la activación por defecto o la evidencia de funcionamiento). |
| **PREVISTO** | Hay estructuras (tablas, esquemas, plantillas, constantes, permisos) pero no la funcionalidad. |
| **OBSOLETO** | El código o el comentario describe algo que ya no corresponde al comportamiento vigente. |
| **NO VERIFICADO** | No pudo comprobarse con la evidencia disponible; se indica qué faltaría para comprobarlo. |

## 2. Inventario de módulos

La columna «Estado» califica el módulo en conjunto; el detalle por funcionalidad está en `03_REQUERIMIENTOS_FUNCIONALES.md`.

| ID | Módulo | Descripción | Componentes | Estado |
|---|---|---|---|---|
| M-01 | Autenticación y sesiones | Registro local, verificación de correo, inicio de sesión con usuario o correo, acceso y registro con Google OAuth 2.0 / OpenID Connect, sesiones con *access token* y *refresh token* rotativo, recuperación y cambio de contraseña, bloqueo temporal por intentos fallidos | Backend, frontend, BD | IMPLEMENTADO |
| M-02 | Verificación en dos pasos (MFA) | Segundo factor TOTP opcional, códigos de recuperación, recuperación de acceso por correo, MFA obligatoria para cuentas administrativas | Backend, frontend, BD | IMPLEMENTADO |
| M-03 | Cuenta personal | Perfil, consentimientos versionados (política de privacidad y datos experimentales), aviso de nuevo inicio de sesión, eliminación de cuenta en dos pasos con anonimización, período de gracia de cuentas institucionales, activación de cuentas creadas por invitación | Backend, frontend, BD, trabajo programado | IMPLEMENTADO |
| M-04 | Cuentas individuales y grupos familiares | Creación y administración de grupos, invitaciones, roles, compartición de datos con cuatro permisos independientes, panel y estadísticas del grupo | Backend, frontend, BD | IMPLEMENTADO |
| M-05 | Instituciones | Alta, modificación, cierre y reapertura de instituciones, roles (propietario, moderador, operador), invitaciones, cupos de cuentas, pausa y soporte, actividad reciente, personal | Backend, frontend, BD | IMPLEMENTADO |
| M-06 | Pacientes institucionales | Padrón, responsable, acceso administrativo frente a acceso a datos de salud, transferencias entre operadores, reasignaciones al desvincular operadores, baja con conservación y anonimización, correo de resultados con confirmación del paciente | Backend, frontend, BD, trabajo de retención | IMPLEMENTADO (con aspectos PARCIAL, ver `06`) |
| M-07 | Mediciones | Perfil de medición, ciclo de vida, oximetría (SpO₂ y frecuencia cardíaca), glucosa experimental informada por el firmware, datos de prueba DEMO, referencia capilar, historial, estadísticas, evolución, envío de resultados por correo | Backend, frontend, BD | IMPLEMENTADO; la estimación de glucosa por el servidor es PREVISTO |
| M-08 | Dispositivos | Inventario global e institucional, estados, alta y asignación, responsable, retiro, conexión y vinculación del Arduino a una institución | Backend, frontend, BD | IMPLEMENTADO |
| M-09 | Adquisición y telemetría | Recepción de lecturas del puente serie, estado en vivo, control temporal exclusivo del equipo, sesiones de medición, guardado con criterio de estabilidad, adquisición de muestras crudas por pySerial, flujos SSE | Backend, frontend, firmware, puente | IMPLEMENTADO en software; sin verificación con hardware real |
| M-10 | Matrices de referencia | Matrices globales e institucionales versionadas con reglas por sexo, edad y condición de comida, validación de solapamientos, ciclo de vida y auditoría propia | Backend, frontend, BD | IMPLEMENTADO |
| M-11 | Paneles, analítica e indicadores | Panel personal, grupal, institucional, por operador, por paciente, analítica de pacientes del operador, indicadores institucionales y panel global de la plataforma | Backend, frontend | IMPLEMENTADO |
| M-12 | Administración de la plataforma | Administrador único y moderadores del sistema, transferencia de la administración, control de instituciones (pausa, reactivación, cupos, eliminación administrativa), estado del sistema, comandos de servidor para el primer administrador y su recuperación | Backend, frontend, CLI | IMPLEMENTADO |
| M-13 | Auditoría y seguridad operativa | Registro central de eventos, consulta con control de acceso por ámbito, clasificación y señales de actividad sospechosa, alerta por correo, conservación, auditoría técnica anonimizada, cabeceras de seguridad, límites de solicitudes | Backend, frontend, BD, Nginx | IMPLEMENTADO |
| M-14 | Correo electrónico y contacto | Catálogo de 68 tipos de correo, plantillas, envío SMTP con STARTTLS, avisos de seguridad, formulario de contacto público | Backend, frontend | IMPLEMENTADO (11 tipos de correo sin uso) |
| M-15 | Privacidad, retención y anonimización | Retención de 12 meses de pacientes, anonimización en cohorte, minimización de datos del personal, conservación de auditoría, depuración de cuentas | Backend, trabajos programados | PARCIAL (plazos no aprobados en tres políticas; un trabajo sin programar) |
| M-16 | Suscripciones, pagos y planes | Tablas, modelos y esquemas; pantalla «Próximamente» | BD, modelos, frontend | PREVISTO |
| M-17 | Sitio público y contenido educativo | Página de presentación, política de privacidad, formulario de contacto, consejos para personas con diabetes | Frontend | IMPLEMENTADO |
| M-18 | Base de datos SQL Server | Esquema de referencia v5, permisos de mínimo privilegio, cifrado y respaldo, compatibilidad con bases no migradas, herramienta de comparación de esquemas | SQL, backend | PARCIAL (ver hallazgo sobre índices en `06`) |
| M-19 | Frontend transversal | Aplicación de una página con rutas protegidas, guardias de permisos, almacenamiento de sesión, enlace de omisión para accesibilidad, galería de componentes | Frontend | IMPLEMENTADO |
| M-20 | Firmware y hardware | Arduino UNO, sensor MAX30100, LCD, Bluetooth HC-05/HC-06; cálculo de métricas, señal PPG, calibración, modo DEMO, identificación persistente | Firmware | IMPLEMENTADO en código; no cargado ni probado en placa según la documentación |
| M-21 | Puente serie | Programa de Windows que lee el puerto COM y envía las líneas al servidor con token compartido | Python | IMPLEMENTADO |
| M-22 | Infraestructura y despliegue | Docker Compose (backend, trabajo de ciclo de vida, frontend, base opcional, compilación de firmware, HTTPS opcional), Nginx, endurecimiento de contenedores | Docker | IMPLEMENTADO |
| M-23 | Pruebas y evidencias de calidad | Pruebas automatizadas de backend y frontend, pruebas contra SQL Server opcionales, evidencia de escaneo de vulnerabilidades y de concurrencia | Pruebas | IMPLEMENTADO (resultados de ejecución en `07`) |
| M-24 | Documentación del proyecto | `README.md` y `docs/` (funcional, seguridad, privacidad, base de datos, despliegue, historial, pendientes) | Documentos | Se contrasta en `05` y `06` |

Módulos no previstos en la lista de partida que se incorporaron: M-14 (correo y contacto), M-17 (contenido educativo), M-18 (compatibilidad de esquema), M-19 (frontend transversal), M-21 (puente serie), M-22 (infraestructura) y M-23 (pruebas).

## 3. Detalle por módulo

Las rutas son relativas a la raíz del repositorio. «API» indica el archivo de rutas bajo `backend/app/api/v1/`.

### M-01 Autenticación y sesiones

- **Servicios:** `backend/app/services/auth.py`, `authAccess.py`, `unverifiedAccounts.py`, `invitedAccounts.py`; núcleo criptográfico en `backend/app/core/security.py`; configuración en `backend/app/core/config.py`.
- **API:** `auth.py` (registro, verificación, inicio de sesión, Google, sesiones, contraseñas). Integración con Google en `backend/app/integrations/google/oauth.py`.
- **Frontend:** `pages/Login`, `pages/Register`, `auth/AuthContext.jsx`, `auth/tokenStore.js`, `auth/googleLogin.js`, `auth/originGuard.js`, `routes/ProtectedRoute.jsx`.
- **BD:** `Usuario`, `CredencialLocal`, `IdentidadExterna`, `SesionUsuario`, `TokenCuenta`.
- **Observaciones:** el inicio de sesión de Google puede separar el origen de la pantalla de acceso (`localhost`) del de la aplicación (`glucolume.local`) mediante un código de transferencia de sesión (`auth.py:662-730`).

### M-02 Verificación en dos pasos

- **Servicios:** `mfa.py`, `mfaRecovery.py`; CLI `backend/app/cli/mfaKeys.py` para diagnosticar claves.
- **BD:** `FactorMfa`, `CodigoRecuperacionMfa`, `TokenCuenta` (tipo de recuperación).
- **Frontend:** `pages/Account/security/MfaSection.jsx`, `MfaAccountRecovery.jsx`, `pages/Login/MfaForm.jsx`, `MfaRecoveryFlow.jsx`.

### M-03 Cuenta personal

- **Servicios:** `user.py`, `consent.py`, `accountDeletion.py`, `accountGrace.py`, `accountLifecycle.py`, `accountActivation.py`, `pendingAccounts.py`.
- **Trabajo programado:** `backend/app/jobs/accountLifecycle.py` (servicio `lifecycle` de Compose) y `cleanupUnverifiedAccounts.py`.
- **Frontend:** `pages/Account/ProfilePage.jsx`, `SecurityPage.jsx`, `security/*`, `ConfirmDeletionPage.jsx`, `pages/Register/ActivateAccount.jsx`, `measurements/ExperimentalConsent.jsx`, `components/PolicyConsent.jsx`, `GracePeriodNotice.jsx`.
- **BD:** `Usuario`, `ConsentimientoUsuario`, `ConfiguracionNotificacion` (sin uso, ver M-16).

### M-04 Grupos familiares

- **Servicio:** `group.py`; notificaciones en `notifications.py`.
- **API:** `groups.py` (27 rutas).
- **Frontend:** `pages/Account/groups/*`.
- **BD:** `Grupo`, `GrupoUsuario` (índices únicos filtrados para grupo activo, vínculo vigente y administrador).

### M-05 Instituciones

- **Servicios:** `institution.py` (roles, permisos, invitaciones, cierre), `quota.py`, `personnel.py`, `personnelRetention.py`, `institutionActivity.py`, `institutionSupport.py`, `schemaCompat.py`.
- **API:** `institutions.py` (rutas de instituciones, equipo, pacientes, transferencias, paneles y matrices).
- **Frontend:** `pages/Account/institutions/*` (excepto `patients`, `reassignments`, `transfers`, `analytics`, `dashboard`).
- **BD:** `Institucion`, `InstitucionUsuario`.

### M-06 Pacientes institucionales

- **Servicios:** `institutionPatients.py`, `patientAccess.py`, `profileTransfers.py`, `reassignments.py`, `institutionReassignments.py`, `operatorOffboarding.py`, `patientResultEmail.py`, `resultEmailStore.py`, `resultEmailConfirmation.py`, `measurementRetention.py`, `institutionalRetention.py`.
- **Frontend:** `pages/Account/institutions/patients`, `reassignments`, `transfers`, `pages/ResultEmail`.
- **BD:** `PerfilMedicion` (tipo institucional y cohorte anónima), `TransferenciaPerfil`, `ReasignacionPaciente`.

### M-07 Mediciones

- **Servicios:** `measurement.py`, `measurementProfile.py`, `measurementVisibility.py`, `measurementLifecycle.py`, `glucoseReference.py`, `technicalAudit.py`, `maintenance.py`; análisis de señal en `backend/app/acquisition/oximetry.py`.
- **API:** `measurements.py`.
- **Frontend:** `pages/Account/measurements/*`, `components/EvolutionChart.jsx`, `TimeSeries`, `PpgChart.jsx`.
- **BD:** `PerfilMedicion`, `Medicion`, `MuestraSensor`, `MedicionReferenciaCapilar`, `EnvioResultado`, `AuditoriaTecnicaMedicion`.

### M-08 Dispositivos

- **Servicios:** `device.py`, `deviceConnection.py`.
- **API:** `devices.py` (inventario global y por institución).
- **Frontend:** `pages/Account/devices/*`, `pages/Account/acquisition/DeviceIdentification.jsx`.
- **BD:** `Dispositivo`.

### M-09 Adquisición y telemetría

- **Servicios:** `telemetry.py`, `acquisition.py`; núcleo en memoria en `backend/app/acquisition/telemetry.py`, `link.py`, `protocol.py`, `oximetry.py`; transmisión SSE en `backend/app/api/streams.py`.
- **API:** `telemetry.py` (puente, control, sesión) y `acquisition.py` (enlace serie del backend).
- **Frontend:** `pages/Account/acquisition/*`, `measurements/DeviceSession.jsx`, `DeviceMonitor.jsx`, `LiveAcquisition` (ruta de muestras crudas).
- **BD:** `MuestraSensor`, `Medicion`.

### M-10 Matrices de referencia

- **Servicio:** `matrix.py`.
- **API:** `matrices.py` y dos rutas de `institutions.py`.
- **Frontend:** `pages/Account/matrices/*`.
- **BD:** `Matriz`, `ReglaMatriz` (índices únicos filtrados de activa por ámbito).

### M-11 Paneles, analítica e indicadores

- **Servicios:** `dashboard.py`, `patientAnalytics.py`, `platformDashboard.py`, `institutionActivity.py`, `measurement.py` (indicadores institucionales).
- **Frontend:** `pages/Account/dashboards`, `pages/Account/institutions/dashboard`, `analytics`, `pages/Platform/PlatformDashboard.jsx`, `components/dashboard.jsx`, `AnalyticsCharts.jsx`.

### M-12 Administración de la plataforma

- **Servicios:** `platform.py`, `platformInstitutions.py`, `platformDashboard.py`, más `device.py` y `matrix.py` en su alcance global.
- **API:** `platform.py` (25 rutas) y rutas globales de `devices.py`, `matrices.py`, `audit.py`.
- **CLI:** `backend/app/cli/initAdmin.py`, `recoverAdmin.py`, `schemaCheck.py`.
- **Frontend:** `pages/Platform/*`, `layouts/PlatformLayout.jsx`.
- **BD:** `Usuario` (tipos de plataforma, índice de administrador único), `TransferenciaAdministracion`.

### M-13 Auditoría y seguridad operativa

- **Servicios:** `audit.py`, `auditQuery.py`, `auditClassification.py`, `securityDetection.py`, `securityMonitor.py`, `auditRetention.py`, `exportAudit.py`, `technicalAudit.py`.
- **Transversal:** `backend/app/api/rateLimit.py`, `securityHeaders.py`, `requestContext.py`, `errors.py`, `core/requestContext.py`.
- **Frontend:** `pages/Account/audit/*`.
- **BD:** `Auditoria`, `AuditoriaContexto`, `AuditoriaTecnicaMedicion`; permisos en `database/reference/GlucoLume_permisos.sql`.

### M-14 Correo electrónico y contacto

- **Servicios:** `email.py`, `contact.py`, `notifications.py`; catálogo en `backend/app/emails/eventTypes.py`; plantillas en `backend/app/emails/`; transporte en `backend/app/integrations/email/sender.py`.
- **API:** `contact.py`.
- **Frontend:** `pages/Landing/ContactSection.jsx`.

### M-15 Privacidad, retención y anonimización

- **Servicios y trabajos:** `institutionalRetention.py`, `measurementRetention.py`, `personnelRetention.py`, `auditRetention.py`, `backend/app/jobs/purgeInstitutionalRetention.py`, `backend/app/jobs/accountLifecycle.py`.

### M-16 Suscripciones, pagos y planes

- **Modelos y esquemas:** `PlanSuscripcion`, `Suscripcion`, `SuscripcionUsuario`, `PeriodoPrueba`, `ProveedorPago`, `TransaccionPago`, `ConfiguracionNotificacion`.
- **Servicios:** `services/subscription.py` y `services/notificationConfig.py` están vacíos (0 bytes).
- **Frontend:** `pages/Platform/PlatformPages.jsx` (`SubscriptionsPage`, aviso «Próximamente»).

### M-17 Sitio público y contenido educativo

- **Frontend:** `pages/Landing/*`, `pages/Privacy/*`, `pages/Account/DiabetesTipsPage.jsx`, `components/DiabetesTips.jsx`, `data/diabetesTips.js`.

### M-18 Base de datos

- **Scripts:** `database/reference/GlucoLume_DB_v5.sql`, `GlucoLume_permisos.sql`, `GlucoLume_permisos_revertir.sql`, `GlucoLume_permisos_verificar.sql`, `GlucoLume_cifrado_y_respaldo.sql`, `GlucoLume_actualizar_instalada.sql`, `MATRIZ.SQL`, `BorrarRap.sql`; respaldos en `database/respaldos/`.
- **Código:** `backend/app/db/session.py`, `base.py`, `utils/dbRetry.py`, `cli/schemaCheck.py`.

### M-19 a M-24

- **M-19:** `frontend/src/App.jsx`, `routes/`, `layouts/`, `components/SkipLink.jsx`, `dev/gallery.jsx`.
- **M-20:** `firmware/GlucoLume_MAX30100/*.ino` y `firmware/GlucoLume_MAX30100_optimizado/*.ino`; compilación en `docker/firmware/Dockerfile`.
- **M-21:** `acquisition/bridge/glucolume_bridge.py` (versión 1.2.0), `bridge_ctl.py`, archivos `.bat`.
- **M-22:** `compose.yaml`, `compose.dev.yaml`, `compose.prod.yaml`, `compose.serial.yaml`, `docker/nginx/default.conf.template`, `docker/caddy/Caddyfile`, `docker/mssql/Dockerfile`, `backend/Dockerfile`, `frontend/Dockerfile`.
- **M-23:** `backend/tests/**`, `frontend/src/**/*.test.*`, `docs/evidencias/*`.
- **M-24:** `README.md`, `docs/*.md`, `docs/funcional/*.md`, `docs/seguridad/auditorias/`.

## 4. Inventario de artefactos

### 4.1 Base de datos (esquema `GlucoLume_DB_v5.sql`, 33 tablas)

| Grupo | Tablas |
|---|---|
| Cuenta y seguridad | `Usuario`, `CredencialLocal`, `IdentidadExterna`, `FactorMfa`, `CodigoRecuperacionMfa`, `SesionUsuario`, `TokenCuenta`, `ConsentimientoUsuario`, `ConfiguracionNotificacion` |
| Instituciones y grupos | `Institucion`, `InstitucionUsuario`, `Grupo`, `GrupoUsuario`, `TransferenciaPerfil`, `ReasignacionPaciente`, `TransferenciaAdministracion` |
| Mediciones | `PerfilMedicion`, `Medicion`, `MuestraSensor`, `MedicionReferenciaCapilar`, `Dispositivo`, `Matriz`, `ReglaMatriz`, `EnvioResultado` |
| Suscripción y pagos | `PlanSuscripcion`, `Suscripcion`, `SuscripcionUsuario`, `PeriodoPrueba`, `ProveedorPago`, `TransaccionPago` |
| Auditoría | `Auditoria`, `AuditoriaContexto`, `AuditoriaTecnicaMedicion` |

### 4.2 API

241 endpoints bajo `/api/v1`, extraídos por análisis sintáctico de los routers, distribuidos así por archivo de `backend/app/api/v1/`: `auth.py` 34, `institutions.py` 63 (incluye las rutas de pacientes, transferencias, paneles y dos de matrices), `groups.py` 27, `devices.py` 25 (inventario global e institucional), `platform.py` 25, `measurements.py` 16, `matrices.py` 14, `telemetry.py` 14, `audit.py` 12 (auditoría global e institucional), `acquisition.py` 10 y `contact.py` 1; además `GET /healthz` fuera de `/api/v1`. El detalle por área figura en `05_MATRIZ_TRAZABILIDAD.md`.

### 4.3 Frontend

Rutas públicas: inicio, ingreso, registro, verificación de correo, activación de cuenta, recuperación y restablecimiento de contraseña, confirmación de eliminación, confirmación del correo de resultados, política de privacidad, retorno de Google. Rutas de plataforma bajo `/plataforma/*` (panel, instituciones, moderadores, transferencia, dispositivos, matrices, auditoría, suscripciones, perfil, seguridad, contraseña). Rutas de cuenta bajo `/app/*`: inicio, consejos, perfil, seguridad, mediciones (nueva, perfil, historial, detalle), conectar dispositivo, grupo (panel, integrantes, privacidad, compartidos, configuración), instituciones (panel, personal, administración, auditoría, actividad, pacientes, reasignaciones, transferencias, dispositivos, matrices).

### 4.4 Correos electrónicos

68 tipos definidos en `backend/app/emails/eventTypes.py`. Once no se emiten desde el código de la aplicación: `EMAIL_CAMBIADO`, `CODIGO_MFA_EMAIL`, `METODO_MFA_CAMBIADO`, `GOOGLE_DESVINCULADO`, `MIEMBRO_ELIMINADO`, `ADMIN_GRUPO_CAMBIADO`, `ROL_INSTITUCIONAL_CAMBIADO`, `MEDICION_REGISTRADA`, `MEDICION_FUERA_UMBRAL`, `ERROR_MEDICION`, `INFORMACION_RETENCION_DATOS`.

### 4.5 Servicios de Compose

`backend`, `lifecycle` (programador de ciclo de vida), `frontend` (Nginx), `db` (perfil opcional `db`), `firmware` (perfil `firmware`), `proxy` (Caddy, perfil `https` de producción).

## 5. Verificación de cobertura del inventario

Antes de dar por cerrada la Etapa 1 se comprobó que cada carpeta de primer nivel del repositorio quedó asignada a un módulo:

| Carpeta | Módulo(s) |
|---|---|
| `backend/app/api`, `services`, `models`, `schemas`, `core`, `db`, `utils` | M-01 a M-16, M-18 |
| `backend/app/acquisition` | M-07, M-09 |
| `backend/app/cli` | M-02, M-12, M-18 |
| `backend/app/emails`, `integrations/email` | M-14 |
| `backend/app/jobs` | M-03, M-15 |
| `backend/tests` | M-23 |
| `frontend/src` | M-01 a M-19 |
| `database` | M-18 |
| `acquisition` | M-21 |
| `firmware` | M-20 |
| `docker`, `compose*.yaml`, `*/Dockerfile` | M-22 |
| `docs`, `README.md` | M-24 |
| `OpenCode` | Fuera del sistema (análisis y tablero previos); no se usa como evidencia |

Todos los módulos listados en la sección 2 fueron examinados en alguna de las etapas siguientes; la lista de módulos con revisión pendiente es vacía.
