# 05 — Matriz de trazabilidad

**Relevamiento por ingeniería inversa** · Etapa 5 · 21 de octubre de 2026.

Esta matriz relaciona las reglas de negocio (RN, `02_REGLAS_NEGOCIO.md`), los requerimientos funcionales (RF, `03_REQUERIMIENTOS_FUNCIONALES.md`) y los no funcionales (RNF, `04_REQUERIMIENTOS_NO_FUNCIONALES.md`) con los archivos, módulos, endpoints, tablas y pruebas que los respaldan. Se generó a partir de esos documentos y del inventario de rutas del backend (extraído por análisis sintáctico de `backend/app/api/v1/*.py`), de modo que cada relación se puede rastrear hasta su fuente.

## Cómo leerla

- Las rutas HTTP se escriben sin el prefijo `/api/v1`. Las pruebas se citan por nombre de archivo (`backend/tests/` para el backend; las que terminan en `.jsx` o `.js` están bajo `frontend/src/`).
- «Transversal» indica un requerimiento no funcional que aplica a todo el sistema o a toda una capa y no a un requerimiento funcional puntual.
- La columna «Estado» repite el estado real del requerimiento. Las pruebas citadas ejercitan el tema; el resultado de su ejecución se informa en `07_RESUMEN_EJECUTIVO.md`.

## Contenido

1. Matriz RF → RN, RNF, endpoints, tablas y pruebas.
2. Matriz RN → RF, RNF, evidencia principal y pruebas.
3. Matriz RNF → RN, RF y artefactos.
4. Endpoints → RF (los 241 endpoints).
5. Tablas de la base → RF y RN.
6. Dependencias entre requerimientos.
7. Verificación de integridad de la matriz.

---

## 1. Matriz RF → RN, RNF, endpoints, tablas y pruebas

| RF | Requerimiento | Módulo | RN | RNF | Endpoints | Tablas | Pruebas | Estado |
|---|---|---|---|---|---|---|---|---|
| RF-001 | Registro local con verificación de correo | M-01 | RN-001, RN-002, RN-003, RN-004, RN-005, RN-018 | RNF-001, RNF-004, RNF-005, RNF-007, RNF-016 | 3 | `Usuario`, `CredencialLocal`, `TokenCuenta`, `ConsentimientoUsuario` | test_register_contact.py, test_username.py, test_account_lifecycle.py, Register.test.jsx, VerifyEmail.test.jsx | IMPLEMENTADO |
| RF-002 | Inicio de sesión con correo o nombre de usuario | M-01 | RN-006, RN-007, RN-008, RN-011, RN-015, RN-018 | RNF-001, RNF-002, RNF-005, RNF-016 | 1 | `CredencialLocal` (`CK_CredencialLocal_intentos`), `SesionUsuario` | test_login_lockout.py, test_auth_access.py, test_auth_access_flows.py, PublicAccess.test.jsx | IMPLEMENTADO |
| RF-003 | Acceso y registro con Google | M-01 | RN-002, RN-009, RN-010 | RNF-002, RNF-004, RNF-009, RNF-010, RNF-043 | 5 | `IdentidadExterna`, `TokenCuenta` | test_google_exchange.py | IMPLEMENTADO |
| RF-004 | Renovación y cierre de sesión; consulta de la cuenta actual | M-01 | RN-011, RN-012 | RNF-002 | 3 | `SesionUsuario` | test_auth_access_flows.py, client.test.js, tokenStore.test.js | IMPLEMENTADO |
| RF-005 | Completar y actualizar el perfil personal | M-01 | RN-020, RN-005 | RNF-007 | 1 | `Usuario` | test_profile.py, test_username.py, Account.test.jsx | IMPLEMENTADO |
| RF-006 | Recuperación de contraseña | M-01 | RN-003, RN-013, RN-018 | RNF-001, RNF-004, RNF-005, RNF-016 | 2 | `TokenCuenta` | test_password_recovery.py, PublicAccess.test.jsx | IMPLEMENTADO |
| RF-007 | Cambiar la contraseña y agregar una contraseña local | M-01 | RN-003, RN-014 | RNF-001 | 2 | `CredencialLocal` | test_password_change.py, Account.test.jsx | IMPLEMENTADO |
| RF-008 | Activación de una cuenta creada por invitación institucional | M-01 | RN-002, RN-003, RN-025 | RNF-001, RNF-004 | 2 | `Usuario`, `TokenCuenta`, `InstitucionUsuario` | test_institution_staff.py, test_personnel_incorporation.py, test_google_exchange.py | IMPLEMENTADO |
| RF-009 | Configurar y activar la verificación en dos pasos | M-02 | RN-015, RN-016 | RNF-003 | 2 | `FactorMfa`, `CodigoRecuperacionMfa` | test_mfa_flow.py, Account.test.jsx | IMPLEMENTADO |
| RF-010 | Verificar el segundo factor al iniciar sesión | M-02 | RN-015, RN-018 | RNF-003, RNF-005 | 1 | `FactorMfa` (`CK_FactorMfa_intentos`) | test_mfa_flow.py, test_mfa_attempts_atomic.py | IMPLEMENTADO |
| RF-011 | Desactivar la verificación en dos pasos | M-02 | RN-015 | RNF-003 | 1 | `FactorMfa` | test_mfa_flow.py | IMPLEMENTADO |
| RF-012 | Recuperar el acceso cuando se perdió el autenticador | M-02 | RN-016 | RNF-003, RNF-004, RNF-005, RNF-053 | 4 | `TokenCuenta`, `FactorMfa` | test_mfa_recovery.py, MfaRecovery.test.jsx | IMPLEMENTADO |
| RF-013 | Gestionar los consentimientos | M-03 | RN-002, RN-021 | RNF-054 | 2 | `ConsentimientoUsuario` | test_consents.py, Measurements.test.jsx | IMPLEMENTADO |
| RF-014 | Gestionar el aviso de nuevo inicio de sesión | M-03 | RN-019 | — | 2 | `Usuario.notificarNuevoInicioSesion` | test_security_hardening.py | PARCIAL |
| RF-015 | Eliminar la cuenta propia | M-03 | RN-022, RN-023 | RNF-004, RNF-054 | 3 | `Usuario`, `TokenCuenta` | test_account_deletion.py, Account.test.jsx | IMPLEMENTADO |
| RF-016 | Período de gracia y eliminación automática de cuentas institucionales | M-03 | RN-024, RN-023 | RNF-029 | 0 (sin endpoint HTTP) | `Usuario.fechaInicioGracia`, `fechaVencimientoGracia` | test_account_lifecycle.py, lifecycle_concurrency.py, Lifecycle.test.jsx | IMPLEMENTADO |
| RF-017 | Depuración automática de cuentas no verificadas e invitadas sin salida | M-03 | RN-004, RN-025 | — | 0 (sin endpoint HTTP) | `Usuario` | test_account_lifecycle.py | IMPLEMENTADO |
| RF-018 | Crear y modificar un grupo familiar | M-04 | RN-026, RN-027, RN-030, RN-091 | RNF-028 | 5 | `Grupo`, `GrupoUsuario` | test_groups.py, Groups.test.jsx | IMPLEMENTADO |
| RF-019 | Invitar a un grupo y responder invitaciones | M-04 | RN-026, RN-028 | RNF-006 | 7 | `GrupoUsuario` | test_groups.py, Groups.test.jsx | IMPLEMENTADO |
| RF-020 | Gestionar integrantes, abandonar el grupo y transferir la… | M-04 | RN-027, RN-029 | RNF-006 | 4 | `GrupoUsuario` | test_groups.py, Groups.test.jsx | IMPLEMENTADO |
| RF-021 | Eliminar un grupo | M-04 | RN-029 | — | 1 | `Grupo.estado` | test_groups.py | IMPLEMENTADO |
| RF-022 | Configurar qué comparto con el grupo | M-04 | RN-030, RN-031 | RNF-006 | 2 | `GrupoUsuario` (columnas de permisos) | test_groups.py, test_group_shared_measurements.py, Groups.test.jsx | IMPLEMENTADO |
| RF-023 | Consultar los datos que otros integrantes comparten | M-04 | RN-030, RN-031, RN-032, RN-061 | RNF-006 | 7 | `GrupoUsuario`, `Medicion`, `PerfilMedicion` | test_group_shared_measurements.py, test_group_measurement_notice.py, Groups.test.jsx | IMPLEMENTADO |
| RF-024 | Panel del grupo familiar | M-04 | RN-031, RN-061 | — | 1 | `Medicion` | test_dashboards.py, Dashboards.test.jsx | IMPLEMENTADO |
| RF-025 | Verificar el CUIT y crear una institución | M-05 | RN-035, RN-024, RN-091 | RNF-025, RNF-028 | 3 | `Institucion` (`UQ_Institucion_identificadorLegal`) | test_institutions.py, Institutions.test.jsx | IMPLEMENTADO |
| RF-026 | Reabrir una institución cerrada | M-05 | RN-035, RN-041, RN-054 | — | 1 | `Institucion.cantidadReaperturas`, `fechaUltimaReapertura` | test_institution_reopen.py, test_reopen_period_views.py | IMPLEMENTADO |
| RF-027 | Consultar y modificar los datos de la institución | M-05 | RN-033, RN-034 | RNF-006 | 2 | `Institucion` | test_institutions.py, Institutions.test.jsx, Administration.test.jsx | IMPLEMENTADO |
| RF-028 | Consultar mis instituciones y responder invitaciones | M-05 | RN-036, RN-037, RN-024 | RNF-029, RNF-048 | 4 | `InstitucionUsuario` | test_institution_staff.py, test_quota.py, Institutions.test.jsx | IMPLEMENTADO |
| RF-029 | Incorporar y desvincular moderadores y operadores | M-05 | RN-025, RN-036, RN-038, RN-042, RN-050 | RNF-006 | 12 | `InstitucionUsuario`, `Usuario`, `TokenCuenta` | test_institution_staff.py, test_personnel_incorporation.py, Personnel.test.jsx, InstitutionStaff.test.jsx | IMPLEMENTADO |
| RF-030 | Editar los datos administrativos del personal | M-05 | RN-044 | — | 2 | `InstitucionUsuario` | test_personnel.py, Personnel.test.jsx | IMPLEMENTADO |
| RF-031 | Consultar el personal, su perfil e historial | M-05 | RN-043 | RNF-006 | 4 | `InstitucionUsuario` | test_personnel.py, Personnel.test.jsx | IMPLEMENTADO |
| RF-032 | Eliminar los datos históricos de una persona del personal | M-05 | RN-096 | — | 1 | `InstitucionUsuario` | test_account_lifecycle.py, Personnel.test.jsx | IMPLEMENTADO |
| RF-033 | Consultar los cupos de cuentas de la institución | M-05 | RN-037 | RNF-046, RNF-048 | 1 | `Institucion.capacidadMaximaUsuarios` | test_quota.py, Quota.test.jsx | IMPLEMENTADO |
| RF-034 | Eliminar la institución | M-05 | RN-039, RN-024 | RNF-029 | 1 | `Institucion.estado` | test_institutions.py, test_institution_reopen.py, Administration.test.jsx | IMPLEMENTADO |
| RF-035 | Consultar la actividad reciente de la institución | M-05 | RN-086 | RNF-020 | 1 | `Auditoria` | test_institution_activity.py | IMPLEMENTADO |
| RF-036 | Consultar al soporte desde una institución pausada | M-05 | RN-040 | — | 1 | `Auditoria` | test_platform_institution_control.py | IMPLEMENTADO |
| RF-037 | Registrar un paciente | M-06 | RN-045, RN-046, RN-047 | RNF-007, RNF-028 | 2 | `PerfilMedicion` (`UX_PerfilMedicion_dniInstitucion`) | test_institution_patients.py, test_patient_assignment.py, Patients.test.jsx | IMPLEMENTADO |
| RF-038 | Consultar y modificar pacientes | M-06 | RN-046, RN-047 | RNF-006, RNF-007, RNF-020 | 3 | `PerfilMedicion` | test_institution_patients.py, test_patient_access.py, Patients.test.jsx | IMPLEMENTADO |
| RF-039 | Asignar el responsable de un paciente | M-06 | RN-048, RN-049 | — | 1 | `TransferenciaPerfil`, `PerfilMedicion` | test_patient_assignment.py, test_manager_reassignment.py | IMPLEMENTADO |
| RF-040 | Transferir pacientes entre operadores | M-06 | RN-048 | RNF-006, RNF-028, RNF-029 | 6 | `TransferenciaPerfil` | test_profile_transfers.py, test_transfer_detail.py, Transfers.test.jsx, TransferDetail.test.jsx | IMPLEMENTADO |
| RF-041 | Desvincular a un operador reasignando sus pacientes | M-06 | RN-038, RN-050 | RNF-006, RNF-029 | 3 | `PerfilMedicion`, `InstitucionUsuario` | test_operator_offboarding.py, Lifecycle.test.jsx | IMPLEMENTADO |
| RF-042 | Gestionar las reasignaciones pendientes | M-06 | RN-050 | — | 4 | `ReasignacionPaciente` | test_manager_reassignment.py, Lifecycle.test.jsx | IMPLEMENTADO |
| RF-043 | Dar de baja a un paciente | M-06 | RN-051, RN-095 | RNF-054 | 1 | `PerfilMedicion` | test_institution_patients.py, test_retention_anonymization.py | IMPLEMENTADO |
| RF-044 | Gestionar el correo de resultados del paciente | M-06 | RN-052 | RNF-025, RNF-046, RNF-054 | 3 | `PerfilMedicion.correoResultados`, `fechaAutorizacionCorreo`,… | test_patient_result_email.py, test_patient_mails.py, ConfirmResultEmailPage.test.jsx | IMPLEMENTADO |
| RF-045 | Consultar el perfil de medición propio | M-07 | RN-020, RN-058 | — | 1 | `PerfilMedicion` (`UX_PerfilMedicion_consumidor`) | test_measurement_profile.py, test_measurement_optional_data.py | IMPLEMENTADO |
| RF-046 | Iniciar una medición para un perfil y un dispositivo | M-07 | RN-055, RN-056, RN-057, RN-058, RN-064, RN-021 | RNF-028, RNF-033, RNF-046 | 3 | `Medicion` | test_measurements.py, test_glucose_mode.py, test_optional_meal.py | PARCIAL |
| RF-047 | Adquirir muestras crudas, finalizar y cancelar una medición | M-07 | RN-055, RN-059, RN-060 | RNF-033 | 3 | `Medicion`, `MuestraSensor` | test_measurements.py, test_measurement_lifecycle.py, test_oximetry.py, Measurements.test.jsx | PARCIAL |
| RF-048 | Medir con el dispositivo (sesión de telemetría) | M-07 | RN-055, RN-056, RN-057, RN-059, RN-060, RN-061, RN-067, RN-072 | RNF-026, RNF-029, RNF-033, RNF-041 | 3 | `Medicion` | test_telemetry.py, test_glucose_mode.py, test_ppg.py, DeviceMeasurement.test.jsx, PatientMeasure.test.jsx | IMPLEMENTADO |
| RF-049 | Consultar el historial de mediciones | M-07 | RN-046, RN-062, RN-066 | RNF-006, RNF-020 | 2 | `Medicion` | test_measurements.py, test_patient_access.py, test_measurement_lifecycle.py, Measurements.test.jsx | IMPLEMENTADO |
| RF-050 | Consultar el detalle de una medición | M-07 | RN-060, RN-062, RN-064 | RNF-033, RNF-041 | 1 | `Medicion`, `MedicionReferenciaCapilar` | test_measurements.py, test_glucose_mode.py, Measurements.test.jsx | IMPLEMENTADO |
| RF-051 | Registrar una referencia capilar | M-07 | RN-063 | — | 1 | `MedicionReferenciaCapilar` | test_glucose_mode.py | IMPLEMENTADO |
| RF-052 | Consultar estadísticas y evolución | M-07 | RN-061, RN-066 | RNF-020 | 4 | `Medicion` | test_evolution.py, test_patient_evolution.py, test_health_aggregates.py, Measurements.test.jsx | IMPLEMENTADO |
| RF-053 | Eliminar mediciones de prueba (DEMO) | M-07 | RN-061 | — | 2 | `Medicion`, `MuestraSensor`, `EnvioResultado` | test_telemetry.py, test_glucose_mode.py, Measurements.test.jsx | IMPLEMENTADO |
| RF-054 | Enviar el resultado de una medición por correo | M-07 | RN-052, RN-061, RN-065 | RNF-017, RNF-025 | 1 | `EnvioResultado` | test_result_email.py, test_result_email_on_save.py, test_patient_result_email.py | IMPLEMENTADO |
| RF-055 | Estimar la glucosa en el servidor | M-07 | RN-060 | RNF-033, RNF-041 | 0 (sin endpoint HTTP) | columnas `glucosaEstimada`, `idMatriz`, `versionAlgoritmo` y su… | test_measurements.py, test_glucose_mode.py | PREVISTO |
| RF-056 | Administrar el inventario global de dispositivos | M-08 | RN-068, RN-069, RN-070 | RNF-006, RNF-028 | 12 | `Dispositivo` | test_devices.py, test_device_context_authority.py, Devices.test.jsx | IMPLEMENTADO |
| RF-057 | Administrar el inventario de una institución | M-08 | RN-068, RN-070 | RNF-006 | 10 | `Dispositivo` | test_devices.py, Devices.test.jsx | IMPLEMENTADO |
| RF-058 | Conectar, identificar y vincular el Arduino | M-08 | RN-069, RN-071 | RNF-043 | 4 | `Dispositivo` | test_device_connection.py, test_device_resolve_authority.py, DeviceIdentification.test.jsx, ConnectDevice.test.jsx | IMPLEMENTADO |
| RF-059 | Consultar las mediciones realizadas con un dispositivo | M-08 | RN-070 | — | 2 | `Medicion`, `Dispositivo` | test_devices.py | IMPLEMENTADO |
| RF-060 | Consultar el estado del puente y qué falta para poder medir | M-09 | RN-068, RN-073 | RNF-044 | 2 | no persiste (estado en memoria) | test_bridge_diagnostics.py, test_telemetry.py, ConnectDevice.test.jsx | IMPLEMENTADO |
| RF-061 | Tomar y soltar el control temporal del dispositivo | M-09 | RN-072, RN-073 | RNF-047 | 2 | no persiste | test_device_control.py, test_shared_device.py | IMPLEMENTADO |
| RF-062 | Dar órdenes al puente serie | M-09 | RN-073 | RNF-015, RNF-047 | 1 | no persiste | test_bridge_command_authority.py, test_bridge_ctl.py, test_bridge.py | IMPLEMENTADO |
| RF-063 | Recibir las lecturas del puente y verificar un código de dispositivo | M-09 | RN-059, RN-074 | RNF-005, RNF-015, RNF-026, RNF-043 | 2 | `Dispositivo` (alta automática) | test_bridge.py, test_bridge_runtime.py, test_telemetry.py, test_ppg.py | IMPLEMENTADO |
| RF-064 | Transmitir en vivo el estado y las lecturas | M-09 | RN-072 | RNF-022, RNF-026, RNF-044, RNF-047 | 2 | no persiste | test_stream_limits.py, test_telemetry.py, PpgChart.test.jsx | IMPLEMENTADO |
| RF-065 | Operar el enlace serie desde el backend (adquisición de muestras… | M-09 | RN-055, RN-059, RN-068 | RNF-043 | 9 | `MuestraSensor` | test_acquisition.py, test_acquisition_port_validation.py, Acquisition.test.jsx | IMPLEMENTADO |
| RF-066 | Crear una matriz con sus reglas | M-10 | RN-075, RN-076, RN-077 | RNF-006, RNF-007, RNF-028 | 2 | `Matriz`, `ReglaMatriz` | test_matrices.py, test_matrices_institucion.py, Matrices.test.jsx | IMPLEMENTADO |
| RF-067 | Editar un borrador y sus reglas | M-10 | RN-076, RN-077 | RNF-007 | 4 | `Matriz`, `ReglaMatriz` | test_matrices.py, test_matrix_unreported_conditions.py | IMPLEMENTADO |
| RF-068 | Validar, activar, desactivar y archivar una matriz | M-10 | RN-076, RN-077 | RNF-029 | 4 | `UX_Matriz_globalActiva`, `UX_Matriz_institucionActiva` | test_matrices.py, Matrices.test.jsx | IMPLEMENTADO |
| RF-069 | Crear una nueva versión de una matriz | M-10 | RN-076 | — | 1 | `Matriz` | test_matrices.py | IMPLEMENTADO |
| RF-070 | Consultar matrices, la matriz efectiva y su auditoría | M-10 | RN-064, RN-075, RN-078 | — | 5 | `Matriz`, `Auditoria` | test_matrices.py, test_matrices_institucion.py | IMPLEMENTADO |
| RF-071 | Panel personal | M-11 | RN-061, RN-066 | — | 1 | `Medicion` | test_dashboards.py, Dashboards.test.jsx, Home.test.jsx | IMPLEMENTADO |
| RF-072 | Panel institucional de gestión | M-11 | RN-053, RN-061 | — | 1 | `Medicion`, `PerfilMedicion` | test_admin_dashboard.py, test_health_aggregates.py, test_dashboard_privacy.py, test_dashboard_multiple_measurements.py,… | IMPLEMENTADO |
| RF-073 | Panel por operador | M-11 | RN-046, RN-057 | — | 1 | `Medicion`, `Auditoria` | test_operator_panel.py, test_operator_scope.py | IMPLEMENTADO |
| RF-074 | Panel por paciente | M-11 | RN-046 | — | 1 | `Medicion`, `PerfilMedicion` | test_dashboards.py | PARCIAL |
| RF-075 | Analítica de los pacientes del operador | M-11 | RN-046, RN-061 | RNF-020 | 1 | `Medicion`, `PerfilMedicion` | test_patient_analytics.py, PatientAnalyticsPage.test.jsx | IMPLEMENTADO |
| RF-076 | Indicadores agregados de la institución (interfaz de programación) | M-11 | RN-053 | — | 1 | — | test_health_aggregates.py | PARCIAL |
| RF-077 | Acceso administrativo: activación con código y recuperación | M-12 | RN-017, RN-079, RN-080 | RNF-001 | 3 | `Usuario`, `TokenCuenta` | test_platform_code_activation.py, test_platform.py, Platform.test.jsx | IMPLEMENTADO |
| RF-078 | Panel global y estado del sistema | M-12 | RN-017, RN-084 | RNF-024, RNF-051 | 2 | varias (consultas de conteo) | test_platform_dashboard.py, test_admin_dashboard.py, Platform.test.jsx | IMPLEMENTADO |
| RF-079 | Gestionar a los moderadores del sistema | M-12 | RN-079, RN-080 | — | 6 | `Usuario`, `TokenCuenta` | test_platform.py, test_platform_reinvite.py, Platform.test.jsx | IMPLEMENTADO |
| RF-080 | Transferir la administración del sistema | M-12 | RN-081 | RNF-029 | 5 | `TransferenciaAdministracion` | test_platform.py, Platform.test.jsx | IMPLEMENTADO |
| RF-081 | Supervisar y controlar instituciones | M-12 | RN-037, RN-040, RN-083 | RNF-006, RNF-048 | 6 | `Institucion`, `Auditoria` | test_platform_institution_control.py, test_quota.py, Platform.test.jsx | IMPLEMENTADO |
| RF-082 | Eliminar una institución administrativamente | M-12 | RN-039, RN-041 | RNF-046 | 1 | `Institucion` (columnas de cierre administrativo,… | test_platform_institution_deletion.py | IMPLEMENTADO |
| RF-083 | Cuenta propia de la administración | M-12 | RN-017 | — | 2 | `Usuario`, `FactorMfa` | test_platform.py, Platform.test.jsx | IMPLEMENTADO |
| RF-084 | Inicializar y recuperar la administración desde el servidor | M-12 | RN-082 | RNF-011, RNF-053 | 0 (sin endpoint HTTP) | `Usuario`, `Auditoria` | test_platform_recovery.py, test_platform_reinvite.py, test_platform_sqlserver.py | IMPLEMENTADO |
| RF-085 | Diagnosticar el esquema de la base y las claves de MFA | M-12 | RN-015 | RNF-003, RNF-036, RNF-053 | 0 (sin endpoint HTTP) | catálogo del sistema (solo lectura) | test_reference_schema.py, test_security_config.py | IMPLEMENTADO |
| RF-086 | Consultar la auditoría global | M-13 | RN-085, RN-086, RN-087 | RNF-006, RNF-014, RNF-017, RNF-020, RNF-031, RNF-032 | 4 | `Auditoria`, `AuditoriaContexto` | test_audit.py, test_audit_security.py, test_audit_names.py, test_audit_resolution.py, test_audit_summary.py,… | IMPLEMENTADO |
| RF-087 | Consultar la auditoría de una institución | M-13 | RN-086 | RNF-006, RNF-014, RNF-017, RNF-031, RNF-032 | 3 | `Auditoria` | test_audit.py, test_audit_security.py, Audit.test.jsx | IMPLEMENTADO |
| RF-088 | Señales de actividad sospechosa y alerta por correo | M-13 | RN-087 | RNF-017, RNF-032, RNF-047 | 1 | `Auditoria` | test_audit_security.py | IMPLEMENTADO |
| RF-089 | Buscar cuentas y consultar su ficha de auditoría | M-13 | RN-086 | RNF-017, RNF-032 | 2 | `Auditoria` | test_audit.py, test_audit_names.py, AuditAdmin.test.jsx | IMPLEMENTADO |
| RF-090 | Consultar la auditoría técnica anonimizada de mediciones | M-13 | RN-089 | — | 2 | `AuditoriaTecnicaMedicion` | test_measurement_lifecycle.py | PARCIAL |
| RF-091 | Conservar y depurar la auditoría | M-13 | RN-088 | RNF-014, RNF-031 | 0 (sin endpoint HTTP) | `Auditoria`, `AuditoriaContexto`; permisos en… | test_audit_security.py | PARCIAL |
| RF-092 | Enviar una consulta desde el formulario de contacto | M-14 | RN-093 | RNF-007, RNF-047 | 1 | no persiste | test_register_contact.py, Landing.test.jsx | IMPLEMENTADO |
| RF-093 | Enviar los correos transaccionales del sistema | M-14 | RN-091, RN-092 | RNF-010, RNF-017, RNF-025, RNF-043 | 0 (sin endpoint HTTP) | no persiste | test_emails.py, test_email.py, test_security_config.py | PARCIAL |
| RF-094 | Desidentificar y anonimizar datos de pacientes vencidos | M-14 | RN-095 | RNF-018, RNF-046, RNF-054 | 0 (sin endpoint HTTP) | `PerfilMedicion`, `Medicion` | test_retention_anonymization.py | PARCIAL |
| RF-095 | Minimizar los datos históricos del personal | M-14 | RN-094 | RNF-054 | 0 (sin endpoint HTTP) | `InstitucionUsuario.fechaMinimizacionDatos` | test_account_lifecycle.py, test_audit_minimized_names.py | PARCIAL |
| RF-096 | Suscripciones, planes y pagos | M-14 | — | — | 0 (sin endpoint HTTP) | `PlanSuscripcion`, `Suscripcion`, `SuscripcionUsuario`,… | Platform.test.jsx | PREVISTO |
| RF-097 | Consultar consejos para personas con diabetes | M-14 | — | RNF-019, RNF-038 | 0 (sin endpoint HTTP) | no interviene | DiabetesTips.test.jsx | IMPLEMENTADO |
| RF-098 | Consultar la página de presentación y la política de privacidad | M-14 | RN-002 | RNF-019, RNF-023, RNF-038, RNF-054 | 0 (sin endpoint HTTP) | no interviene | Landing.test.jsx, Privacy.test.jsx | IMPLEMENTADO |
| RF-099 | Exportar datos | M-14 | RN-090 | — | 0 (sin endpoint HTTP) | eventos de auditoría de exportación definidos, sin emisión | test_audit_security.py, auditedExport | PREVISTO |
| RF-100 | Control de acceso por ruta y permiso en la interfaz | M-14 | RN-012 | RNF-002, RNF-023, RNF-038 | 0 (sin endpoint HTTP) | no interviene | App.test.jsx, Layout.test.jsx, SkipLink.test.jsx, InstitutionNavigation.test.jsx | IMPLEMENTADO |

## 2. Matriz RN → RF, RNF, evidencia principal y pruebas

| RN | Regla | Módulo | RF | RNF | Evidencia principal | Estado |
|---|---|---|---|---|---|---|
| RN-001 | El registro público solo crea cuentas individuales o institucionales | M-01 | RF-001 | — | `backend/app/services/auth.py:73,130-134,148-153`. Pruebas: `test_auth_access_account_type.py`. | IMPLEMENTADO |
| RN-002 | Crear una cuenta exige confirmar la Política de Privacidad | M-01, M-03 | RF-001, RF-003, RF-008, RF-013, RF-098 | RNF-054 | `backend/app/services/consent.py:29,85-87`, `auth.py:155,187,754,787`. Pruebas: `test_consents.py`, `test_register_contact.py`. | IMPLEMENTADO |
| RN-003 | Política de contraseñas nuevas | M-01 | RF-001, RF-006, RF-007, RF-008 | RNF-001 | `backend/app/core/security.py:54-129`, `auth.py:137-145,1108-1111`. Pruebas: `test_password_change.py`, `test_password_recovery.py`, `test_register_contact.py`. | IMPLEMENTADO |
| RN-004 | Verificación del correo electrónico con plazo fijo | M-01 | RF-001, RF-017 | RNF-004, RNF-030 | `backend/app/services/auth.py:148-361`, `unverifiedAccounts.py:1-40`. Pruebas: `test_account_lifecycle.py`, `test_register_contact.py`. | IMPLEMENTADO |
| RN-005 | Unicidad de correo y de nombre de usuario | M-01 | RF-001, RF-005 | — | `backend/app/services/auth.py:159-168,193-196`, `user.py:31-112`. Pruebas: `test_username.py`, `test_profile.py`. | IMPLEMENTADO |
| RN-006 | Solo una cuenta activa puede iniciar sesión | M-01 | RF-002 | — | `backend/app/services/auth.py:120-124,380-389,932-936`, `resolveAccessSession` (`auth.py:1055-1072`). Pruebas: `test_auth_access.py`, `test_auth_access_flows.py`. | IMPLEMENTADO |
| RN-007 | Bloqueo temporal por contraseñas incorrectas | M-01 | RF-002 | RNF-005, RNF-029 | `backend/app/services/auth.py:61,392-591`. Pruebas: `test_login_lockout.py`, `test_mfa_attempts_atomic.py`, `test_lifecycle_concurrency.py`. | IMPLEMENTADO |
| RN-008 | Respuesta uniforme ante credenciales inválidas | M-01 | RF-002 | RNF-001, RNF-016 | `backend/app/services/auth.py:367-377,522-549`, `security.py:141-143`, `audit.py:200-205`. Pruebas: `test_auth_access.py`, `test_login_email_no_ip.py`. | IMPLEMENTADO |
| RN-009 | Vinculación y creación de cuentas con Google | M-01 | RF-003 | RNF-009, RNF-043 | `backend/app/services/auth.py:604-815`. Pruebas: `test_google_exchange.py`. | IMPLEMENTADO |
| RN-010 | Los tokens de sesión no viajan en la URL de retorno de Google | M-01 | RF-003 | RNF-004, RNF-009 | `backend/app/services/auth.py:70,662-730`. Pruebas: `test_google_exchange.py`. | IMPLEMENTADO |
| RN-011 | Sesión con renovación rotativa y revocación ante reutilización | M-01 | RF-002, RF-004 | RNF-002 | `backend/app/services/auth.py:895-937`, `security.py:149-155,161-195`. Pruebas: `test_auth_access_flows.py`, `test_audit_security.py`. | IMPLEMENTADO |
| RN-012 | La autorización se evalúa contra la base en cada pedido | M-01, M-05, M-12 | RF-004, RF-100 | RNF-002, RNF-006 | `backend/app/services/auth.py:1055-1072`, `institution.py:19-22,263-292`, `platform.py:3-6`. Pruebas: `test_auth_access.py`, `test_operator_scope.py`. | IMPLEMENTADO |
| RN-013 | Recuperación de contraseña con enlace de un solo uso | M-01 | RF-006 | RNF-004, RNF-016 | `backend/app/services/auth.py:943-1035`. Pruebas: `test_password_recovery.py`. | IMPLEMENTADO |
| RN-014 | El cambio de contraseña exige reautenticación y cierra las demás… | M-01 | RF-007 | — | `backend/app/services/auth.py:1078-1120`. Pruebas: `test_password_change.py`. | IMPLEMENTADO |
| RN-015 | La verificación en dos pasos es opcional, bloqueable y no admite… | M-02 | RF-002, RF-009, RF-010, RF-011, RF-085 | RNF-003, RNF-005 | `backend/app/services/mfa.py:26,52-232`, `auth.py:822-826`, `security.py:37-40,278-331`. Pruebas: `test_mfa_flow.py`, `test_mfa_attempts_atomic.py`. | IMPLEMENTADO |
| RN-016 | Recuperación del segundo factor controlada por correo | M-02 | RF-009, RF-012 | RNF-003, RNF-004 | `backend/app/services/mfaRecovery.py:1-60`, `security.py:32,336-348`. Pruebas: `test_mfa_recovery.py`. | IMPLEMENTADO |
| RN-017 | Las cuentas administrativas exigen MFA para operar | M-02, M-12 | RF-077, RF-078, RF-083 | — | `backend/app/services/platform.py:84,108-111`. Pruebas: `test_platform.py`, `test_account_deletion.py`. | IMPLEMENTADO |
| RN-018 | Límite de solicitudes por IP en los puntos públicos | M-01, M-13 | RF-001, RF-002, RF-006, RF-010 | RNF-005, RNF-047 | API: `backend/app/api/rateLimit.py:23-87`; Pr: `test_rate_limiter.py`,…. Pruebas: `test_rate_limiter.py`, `test_security_hardening.py`, `test_stream_limits.py`. | IMPLEMENTADO |
| RN-019 | Avisos de seguridad por correo | M-03, M-14 | RF-014 | — | `backend/app/services/auth.py:1123-1162`, `security.py:262-272`. Pruebas: `test_security_hardening.py`, `test_emails.py`. | PARCIAL |
| RN-020 | Edición del perfil personal | M-03 | RF-005, RF-045 | — | `backend/app/services/user.py:17-114`. Pruebas: `test_profile.py`, `test_username.py`. | IMPLEMENTADO |
| RN-021 | Consentimiento de datos experimentales | M-03, M-07 | RF-013, RF-046 | RNF-054 | `backend/app/services/consent.py:1-106`, `measurement.py:172-177,272,364`. Pruebas: `test_consents.py`, `test_measurements.py`. | IMPLEMENTADO |
| RN-022 | Eliminación de la cuenta propia en dos pasos y con impedimentos | M-03 | RF-015 | RNF-004 | `backend/app/services/accountDeletion.py:1-30,126-166,213-263,461-500`. Pruebas: `test_account_deletion.py`. | IMPLEMENTADO |
| RN-023 | La baja de cuenta anonimiza y conserva la trazabilidad | M-03, M-15 | RF-015, RF-016 | RNF-054 | `backend/app/services/accountDeletion.py:360-431`. Pruebas: `test_account_deletion.py`. | IMPLEMENTADO |
| RN-024 | Período de gracia de 30 días para cuentas institucionales sin vínculos | M-03, M-05 | RF-016, RF-025, RF-028, RF-034 | RNF-029, RNF-030 | `backend/app/services/accountGrace.py:1-144`, `accountLifecycle.py:1-48`; trabajo:…. Pruebas: `test_account_lifecycle.py`, `lifecycle_concurrency.py`. | IMPLEMENTADO |
| RN-025 | Cuentas creadas por invitación institucional | M-03, M-05 | RF-008, RF-017, RF-029 | — | `backend/app/services/invitedAccounts.py:1-60`, `accountActivation.py:1-45`,…. Pruebas: `test_institution_staff.py`, `test_account_lifecycle.py`,… | IMPLEMENTADO |
| RN-026 | Los grupos son solo para cuentas individuales y una cuenta pertenece… | M-04 | RF-018, RF-019 | RNF-028 | `backend/app/services/group.py:5-11,133-135,227-253,324-345`. Pruebas: `test_groups.py`. | IMPLEMENTADO |
| RN-027 | Cada grupo tiene un único administrador | M-04 | RF-018, RF-020 | RNF-028 | `backend/app/services/group.py:500-552`. Pruebas: `test_groups.py`. | IMPLEMENTADO |
| RN-028 | Invitaciones a un grupo | M-04 | RF-019 | — | `backend/app/services/group.py:79,105,324-481`. Pruebas: `test_groups.py`. | IMPLEMENTADO |
| RN-029 | Salida, desvinculación y eliminación de grupos | M-04 | RF-020, RF-021 | — | `backend/app/services/group.py:146-150,487-586`. Pruebas: `test_groups.py`. | IMPLEMENTADO |
| RN-030 | Compartición con cuatro permisos independientes decididos solo por su… | M-04 | RF-018, RF-022, RF-023 | — | `backend/app/services/group.py:13-23,85,602-624`. Pruebas: `test_groups.py`, `test_group_shared_measurements.py`. | IMPLEMENTADO |
| RN-031 | Cada consulta de datos compartidos verifica la autorización vigente | M-04 | RF-022, RF-023, RF-024 | — | `backend/app/services/group.py:650-744`. Pruebas: `test_group_shared_measurements.py`, `test_group_measurement_notice.py`. | IMPLEMENTADO |
| RN-032 | Estadísticas del grupo: períodos fijos, solo agregados y datos DEMO… | M-04, M-11 | RF-023 | RNF-020 | `backend/app/services/group.py:80-83,747-776`. Pruebas: `test_group_shared_measurements.py`, `test_dashboards.py`. | IMPLEMENTADO |
| RN-033 | Roles institucionales y matriz de permisos | M-05 | RF-027 | RNF-006 | `backend/app/services/institution.py:1-14,97-146`. Pruebas: `test_institutions.py`, `test_operator_scope.py`. | IMPLEMENTADO |
| RN-034 | Pertenecer a una institución se verifica en cada operación | M-05 | RF-027 | RNF-006 | `backend/app/services/institution.py:263-292`. Pruebas: `test_institutions.py`, `test_institution_staff.py`. | IMPLEMENTADO |
| RN-035 | El CUIT es único y una institución cerrada solo la reabre su último… | M-05 | RF-025, RF-026 | — | `backend/app/services/institution.py:327-519`. Pruebas: `test_institution_reopen.py`, `test_institutions.py`. | IMPLEMENTADO |
| RN-036 | Incorporación de personal por invitación con aceptación | M-05 | RF-028, RF-029 | RNF-006 | `backend/app/services/institution.py:723-1162`. Pruebas: `test_institution_staff.py`, `test_personnel_incorporation.py`. | IMPLEMENTADO |
| RN-037 | Capacidad máxima de cuentas activas por institución | M-05, M-12 | RF-028, RF-033, RF-081 | RNF-029, RNF-046, RNF-048 | `backend/app/services/quota.py:1-100`, `institution.py:1080-1121`. Pruebas: `test_quota.py`, `test_platform_institution_control.py`. | IMPLEMENTADO |
| RN-038 | Revocar vínculos y cancelar invitaciones | M-05 | RF-029, RF-041 | RNF-029 | `backend/app/services/institution.py:1186-1290`. Pruebas: `test_institution_staff.py`. | IMPLEMENTADO |
| RN-039 | Eliminación lógica de la institución con retención de pacientes | M-05, M-15 | RF-034, RF-082 | — | `backend/app/services/institution.py:142,1296-1426`. Pruebas: `test_institutions.py`, `test_institution_reopen.py`,… | IMPLEMENTADO |
| RN-040 | Una institución pausada no permite ningún contexto institucional | M-05, M-12 | RF-036, RF-081 | RNF-006 | `backend/app/services/institution.py:258-260,287-288`, `institutionSupport.py:1-45`,…. Pruebas: `test_platform_institution_control.py`. | IMPLEMENTADO |
| RN-041 | El cierre administrativo de una institución no puede revertirse desde… | M-05, M-12 | RF-026, RF-082 | RNF-046 | `backend/app/services/institution.py:318-358`, `platformInstitutions.py:185-240`. Pruebas: `test_platform_institution_deletion.py`. | IMPLEMENTADO |
| RN-042 | Un solo vínculo vigente por cuenta e institución y sin autoinvitación | M-05 | RF-029 | RNF-028 | M: `backend/app/models/institutionUser.py:20-60`; BD: `UX_InstitucionUsuario_vinculoVigente`,…. Pruebas: `test_institution_staff.py`. | IMPLEMENTADO |
| RN-043 | El rol de un vínculo es fijo | M-05 | RF-031 | — | `backend/app/services/personnel.py:1-30`. Pruebas: `test_personnel.py`. | IMPLEMENTADO |
| RN-044 | Los datos administrativos del vínculo los edita quien administra ese… | M-05 | RF-030 | — | `backend/app/services/institution.py:977-1002`. Pruebas: `test_personnel.py`. | IMPLEMENTADO |
| RN-045 | El paciente institucional no es una cuenta: pertenece a la… | M-06 | RF-037 | — | `backend/app/services/institutionPatients.py:1-30,61-71`. Pruebas: `test_institution_patients.py`. | IMPLEMENTADO |
| RN-046 | Separación entre información administrativa e información de salud | M-06, M-07, M-11 | RF-037, RF-038, RF-049, RF-073, RF-074, RF-075 | RNF-006 | `backend/app/services/patientAccess.py:1-71`, `institutionPatients.py:142-170,263-265`,…. Pruebas: `test_patient_access.py`, `test_operator_scope.py`, `test_dashboard_privacy.py`. | IMPLEMENTADO |
| RN-047 | Alta, modificación y documento del paciente | M-06 | RF-037, RF-038 | RNF-007, RNF-028 | `backend/app/services/institutionPatients.py:194-216,318-399`. Pruebas: `test_institution_patients.py`, `test_patient_assignment.py`, `test_patient_identity.py`. | IMPLEMENTADO |
| RN-048 | El cambio de responsable entre operadores requiere aceptación del… | M-06 | RF-039, RF-040 | RNF-029 | `backend/app/services/profileTransfers.py:1-30,386-585`, `institutionPatients.py:234-241`. Pruebas: `test_profile_transfers.py`, `test_transfer_detail.py`. | IMPLEMENTADO |
| RN-049 | La asignación de responsable por la gestión no es unilateral cuando… | M-06 | RF-039 | — | `backend/app/services/institutionPatients.py:402-496`. Pruebas: `test_patient_assignment.py`, `test_manager_reassignment.py`. | IMPLEMENTADO |
| RN-050 | Un operador con pacientes activos no puede desvincularse sin… | M-05, M-06 | RF-029, RF-041, RF-042 | — | `backend/app/services/institution.py:1203-1262`, `operatorOffboarding.py:1-150`,…. Pruebas: `test_operator_offboarding.py`, `test_manager_reassignment.py`,… | IMPLEMENTADO |
| RN-051 | La baja de un paciente inicia su conservación y su anonimización | M-06, M-15 | RF-043 | RNF-054 | `backend/app/services/institutionPatients.py:499-543`, `measurementRetention.py:1-30`. Pruebas: `test_institution_patients.py`, `test_retention_anonymization.py`. | IMPLEMENTADO |
| RN-052 | El correo de resultados del paciente requiere autorización y… | M-06, M-07 | RF-044, RF-054 | RNF-046 | `backend/app/services/resultEmailStore.py:1-20`, `resultEmailConfirmation.py:1-25`,…. Pruebas: `test_patient_result_email.py`, `test_result_email.py`, `test_result_email_on_save.py`,… | IMPLEMENTADO |
| RN-053 | No se informan estadísticas de salud de grupos con menos de cinco… | M-06, M-11 | RF-072, RF-076 | — | `backend/app/services/patientAccess.py:34,82-86`, `measurement.py:966-991`. Pruebas: `test_dashboard_privacy.py`, `test_patient_access.py`. | IMPLEMENTADO |
| RN-054 | La reapertura no devuelve el acceso a pacientes del período anterior | M-05, M-06 | RF-026 | — | `backend/app/services/patientAccess.py:37-42`, `institutionPatients.py:97-118`. Pruebas: `test_reopen_period_views.py`. | IMPLEMENTADO |
| RN-055 | Ciclo de vida de una medición con transiciones atómicas | M-07 | RF-046, RF-047, RF-048, RF-065 | RNF-007, RNF-029 | `backend/app/services/measurement.py:3-10,346-558`. Pruebas: `test_measurements.py`, `test_measurement_lifecycle.py`. | IMPLEMENTADO |
| RN-056 | Quién puede iniciar y operar una medición | M-07 | RF-046, RF-048 | RNF-006 | `backend/app/services/measurement.py:12-17,139-185`. Pruebas: `test_measurements.py`, `test_operator_scope.py`, `test_patient_access.py`. | IMPLEMENTADO |
| RN-057 | Autoría de la medición y datos históricos del momento | M-07, M-13 | RF-046, RF-048, RF-073 | RNF-033 | `backend/app/services/measurement.py:17-19,277-338`. Pruebas: `test_measurement_profile.py`, `test_measurements.py`. | IMPLEMENTADO |
| RN-058 | Edad y sexo opcionales; nunca se inventan | M-07 | RF-045, RF-046 | — | `backend/app/services/measurement.py:268-317`, `measurementProfile.py:1-45`. Pruebas: `test_measurement_optional_data.py`, `test_optional_meal.py`, `test_glucose_mode.py`. | IMPLEMENTADO |
| RN-059 | SpO₂ y frecuencia cardíaca: cálculo del servidor o valores del… | M-07, M-09 | RF-047, RF-048, RF-063, RF-065 | RNF-033 | `backend/app/services/measurement.py:21-30,447-480`, `telemetry.py:1-21`; núcleo:…. Pruebas: `test_oximetry.py`, `test_ppg.py`, `test_telemetry.py`. | IMPLEMENTADO |
| RN-060 | La glucosa nunca se inventa: no hay algoritmo de estimación en el… | M-07 | RF-047, RF-048, RF-050, RF-055 | RNF-033, RNF-041 | `backend/app/services/measurement.py:121-125,482-485,827-834`. Pruebas: `test_glucose_mode.py`, `test_measurements.py` (el estimador se simula por *monkeypatch*). | PARCIAL |
| RN-061 | Los datos DEMO quedan fuera de todo indicador | M-07, M-11, M-04 | RF-023, RF-024, RF-048, RF-052, RF-053, RF-054, RF-071, RF-072, RF-075 | RNF-041 | `backend/app/services/measurement.py:21-24,724-764,1011-1014`. Pruebas: `test_dashboards.py`, `test_evolution.py`, `test_group_shared_measurements.py`,… | IMPLEMENTADO |
| RN-062 | Visibilidad temporal de mediciones canceladas o inválidas y… | M-07 | RF-049, RF-050 | — | `backend/app/services/measurementVisibility.py:1-22`, `measurementLifecycle.py:1-45`,…. Pruebas: `test_measurement_lifecycle.py`. | IMPLEMENTADO |
| RN-063 | La referencia capilar se carga a mano y no reemplaza la estimación | M-07 | RF-051 | — | `backend/app/services/measurement.py:564-587`. Pruebas: `test_glucose_mode.py`. | IMPLEMENTADO |
| RN-064 | La matriz aplicable la decide siempre el servidor | M-07, M-10 | RF-046, RF-050, RF-070 | RNF-033 | `backend/app/services/matrix.py:287-321`, `measurement.py:235-262,290-293`,…. Pruebas: `test_matrices.py`, `test_matrices_institucion.py`,… | IMPLEMENTADO |
| RN-065 | Envío del resultado por correo: destinatario, confirmación y límite | M-07, M-14 | RF-054 | — | `backend/app/services/measurement.py:996-1103`. Pruebas: `test_result_email.py`, `test_result_email_on_save.py`, `test_patient_result_email.py`. | IMPLEMENTADO |
| RN-066 | Historial, estadísticas y evolución: períodos, límites y paginación | M-07, M-11 | RF-049, RF-052, RF-071 | RNF-020 | `backend/app/services/measurement.py:110-111,644-690,781-960`. Pruebas: `test_evolution.py`, `test_patient_evolution.py`, `test_health_aggregates.py`. | IMPLEMENTADO |
| RN-067 | Criterio de estabilidad para guardar una medición con el dispositivo | M-09 | RF-048 | — | `backend/app/acquisition/telemetry.py:66-80`, `backend/app/services/telemetry.py:560-600`. Pruebas: `test_telemetry.py`, `test_glucose_mode.py`. | IMPLEMENTADO |
| RN-068 | Estados del dispositivo y uso solo en estado operativo | M-08 | RF-056, RF-057, RF-060, RF-065 | — | `backend/app/services/device.py:3-14,77,415-418,785-803`, `measurement.py:360-390`. Pruebas: `test_devices.py`, `test_device_control.py`. | IMPLEMENTADO |
| RN-069 | Identidad del dispositivo por su código persistente | M-08, M-09 | RF-056, RF-058 | — | `backend/app/services/device.py:404-405,832-893`, `deviceConnection.py:1-30`. Pruebas: `test_device_connection.py`, `test_device_resolve_authority.py`. | IMPLEMENTADO |
| RN-070 | Quién registra, asigna y retira dispositivos | M-08, M-12 | RF-056, RF-057, RF-059 | — | `backend/app/services/device.py:15-27,102-131,496-516,705-803`. Pruebas: `test_devices.py`, `test_device_context_authority.py`. | IMPLEMENTADO |
| RN-071 | Uso compartido o restringido del dispositivo | M-08, M-09 | RF-058 | — | `backend/app/services/device.py:809-829`, `telemetry.py:131-157`. Pruebas: `test_shared_device.py`, `test_device_context_authority.py`. | IMPLEMENTADO |
| RN-072 | Una sola cuenta controla el dispositivo a la vez | M-09 | RF-048, RF-061, RF-064 | RNF-022, RNF-026, RNF-047 | `backend/app/acquisition/telemetry.py:81-88`, `backend/app/services/telemetry.py:172-210`. Pruebas: `test_device_control.py`, `test_telemetry.py`. | IMPLEMENTADO |
| RN-073 | Autoridad sobre las órdenes al puente | M-09 | RF-060, RF-061, RF-062 | — | `backend/app/services/telemetry.py:131-226`, `backend/app/acquisition/telemetry.py:361-362,616-636`. Pruebas: `test_bridge_command_authority.py`, `test_bridge.py`, `test_bridge_ctl.py`. | IMPLEMENTADO |
| RN-074 | Autenticación del puente y un solo puente activo | M-09, M-21 | RF-063 | RNF-015, RNF-026 | `backend/app/core/config.py:102-106,153-158`, `api/rateLimit.py:42-45`,…. Pruebas: `test_bridge.py`, `test_bridge_runtime.py`, `test_security_config.py`. | IMPLEMENTADO |
| RN-075 | Ámbitos de las matrices y quién las administra | M-10 | RF-066, RF-070 | RNF-006 | `backend/app/services/matrix.py:3-12,100-155,449-455`. Pruebas: `test_matrices.py`, `test_matrices_institucion.py`. | IMPLEMENTADO |
| RN-076 | Ciclo de vida e inmutabilidad de las matrices | M-10 | RF-066, RF-067, RF-068, RF-069 | RNF-028 | `backend/app/services/matrix.py:14-21,458-528,534-539,649-710`. Pruebas: `test_matrices.py`. | IMPLEMENTADO |
| RN-077 | Las reglas de una matriz no pueden solaparse ni duplicarse | M-10 | RF-066, RF-067, RF-068 | — | `backend/app/services/matrix.py:23-31,333-446,649-663`. Pruebas: `test_matrices.py`, `test_matrix_unreported_conditions.py`. | IMPLEMENTADO |
| RN-078 | Auditoría de las matrices | M-10, M-13 | RF-070 | — | `backend/app/services/matrix.py:39-41,157-165,270-285`. Pruebas: `test_matrices_institucion.py`. | IMPLEMENTADO |
| RN-079 | Un único administrador del sistema y moderadores que no se convierten | M-12 | RF-077, RF-079 | — | `backend/app/services/platform.py:1-9,245-321`. Pruebas: `test_platform.py`, `test_platform_reinvite.py`. | IMPLEMENTADO |
| RN-080 | Reautenticación reforzada y circuitos propios de la administración | M-12 | RF-077, RF-079 | — | `backend/app/services/platform.py:99-148,401-438,444-505`. Pruebas: `test_platform_code_activation.py`, `test_platform.py`. | IMPLEMENTADO |
| RN-081 | Transferencia de la administración con aceptación del destinatario | M-12 | RF-080 | RNF-029 | `backend/app/services/platform.py:550-669`. Pruebas: `test_platform.py`. | IMPLEMENTADO |
| RN-082 | El primer administrador y su recuperación solo se hacen desde el… | M-12 | RF-084 | RNF-053 | `backend/app/cli/initAdmin.py:1-30`, `recoverAdmin.py:1-30`, `services/platform.py:682-860`. Pruebas: `test_platform_recovery.py`, `test_platform_reinvite.py`. | IMPLEMENTADO |
| RN-083 | Control de instituciones por la plataforma | M-12, M-05 | RF-081 | — | `backend/app/services/platformInstitutions.py:1-71,185-250`. Pruebas: `test_platform_institution_control.py`. | IMPLEMENTADO |
| RN-084 | El panel global solo muestra agregados | M-11, M-12 | RF-078 | — | `backend/app/services/platformDashboard.py:1-8`. Pruebas: `test_platform_dashboard.py`, `test_admin_dashboard.py`. | IMPLEMENTADO |
| RN-085 | Todo evento relevante se registra por un único camino, sin secretos y… | M-13 | RF-086 | RNF-014, RNF-017, RNF-031, RNF-032 | `backend/app/services/audit.py:1-86,232-295`. Pruebas: `test_audit.py`, `test_audit_security.py`. | IMPLEMENTADO |
| RN-086 | Quién consulta la auditoría y con qué alcance | M-13 | RF-035, RF-086, RF-087, RF-089 | RNF-032 | `backend/app/services/auditQuery.py:1-30`, `institution.py:121-122`. Pruebas: `test_audit.py`, `test_audit_security.py`, `test_audit_resolution.py`. | IMPLEMENTADO |
| RN-087 | Clasificación de eventos y señales de actividad sospechosa | M-13 | RF-086, RF-088 | RNF-047 | `backend/app/services/auditClassification.py:1-45`, `securityDetection.py:1-35`,…. Pruebas: `test_audit_security.py`. | IMPLEMENTADO |
| RN-088 | Conservación de la auditoría | M-13, M-15 | RF-091 | RNF-031 | `backend/app/services/auditRetention.py:1-25`. Pruebas: `test_audit_security.py`. | PARCIAL |
| RN-089 | La auditoría técnica de mediciones fallidas es anónima y temporal | M-13, M-07 | RF-090 | — | `backend/app/services/technicalAudit.py:1-30`. Pruebas: `test_measurement_lifecycle.py`. | PARCIAL |
| RN-090 | Toda exportación futura de datos deberá pasar por la auditoría de… | M-13 | RF-099 | — | `backend/app/services/exportAudit.py:1-30`. Pruebas: `test_audit_security.py` (`auditedExport`). | PREVISTO |
| RN-091 | Los correos se envían después de confirmar la operación y un fallo no… | M-14 | RF-018, RF-025, RF-093 | RNF-025 | `backend/app/services/notifications.py:1-50`, `email.py`, `auth.py:83-87`. Pruebas: `test_emails.py`, `test_institutions.py`. | IMPLEMENTADO |
| RN-092 | Los correos no incluyen datos de salud en el asunto ni claves… | M-14 | RF-093 | RNF-017 | `backend/app/emails/eventTypes.py:1-5`, `services/email.py:1-125`. Pruebas: `test_emails.py`. | IMPLEMENTADO |
| RN-093 | El formulario de contacto público está limitado y no guarda datos | M-14, M-17 | RF-092 | — | `backend/app/services/contact.py:1-35`. Pruebas: `test_register_contact.py`. | IMPLEMENTADO |
| RN-094 | Minimización de datos personales históricos del personal | M-15 | RF-095 | RNF-054 | `backend/app/services/personnelRetention.py:1-40`. Pruebas: `test_account_lifecycle.py`, `test_audit_minimized_names.py`. | PARCIAL |
| RN-095 | Fin de la conservación de los datos de pacientes y cohorte anónima | M-06, M-15 | RF-043, RF-094 | RNF-018, RNF-054 | `backend/app/services/measurementRetention.py:1-30`, `institutionalRetention.py:1-25`; trabajo:…. Pruebas: `test_retention_anonymization.py`. | PARCIAL |
| RN-096 | Eliminación a pedido de los datos históricos de una persona del… | M-05, M-15 | RF-032 | RNF-054 | `backend/app/services/personnel.py:328-360`. Pruebas: `test_account_lifecycle.py`. | IMPLEMENTADO |

## 3. Matriz RNF → RN, RF y artefactos

| RNF | Requerimiento | RN | RF | Artefactos principales |
|---|---|---|---|---|
| RNF-001 | Argon2id para contraseñas | RN-003, RN-008 | RF-001, RF-002, RF-006, RF-007, RF-008, RF-077 | `core/security.py`; `CredencialLocal` |
| RNF-002 | JWT y sesiones | RN-011, RN-012 | RF-002, RF-003, RF-004, RF-100 | `core/security.py`, `core/config.py`; `SesionUsuario` |
| RNF-003 | Cifrado de secretos TOTP | RN-015, RN-016 | RF-009, RF-010, RF-011, RF-012, RF-085 | `core/security.py`, `cli/mfaKeys.py`; `FactorMfa` |
| RNF-004 | Tokens y códigos solo como hash | RN-004, RN-010, RN-013, RN-016, RN-022 | RF-001, RF-003, RF-006, RF-008, RF-012, RF-015 | `core/security.py`; `TokenCuenta`, `SesionUsuario`, `CodigoRecuperacionMfa` |
| RNF-005 | Control de abuso | RN-007, RN-015, RN-018 | RF-001, RF-002, RF-006, RF-010, RF-012, RF-063 | `api/rateLimit.py`, `docker/nginx/default.conf.template`; `CredencialLocal`, `FactorMfa` |
| RNF-006 | Autorización centralizada | RN-012, RN-033, RN-034, RN-036, RN-040, RN-046, RN-056, RN-075 | RF-019, RF-020, RF-022, RF-023, RF-027, RF-029, RF-031, RF-038, RF-040, RF-041, RF-049, RF-056, RF-057, RF-066, RF-081, RF-086, RF-087 | `services/institution.py`, `group.py`, `patientAccess.py`, `device.py`, `matrix.py` |
| RNF-007 | Entradas validadas y consultas parametrizadas | RN-047, RN-055 | RF-001, RF-005, RF-037, RF-038, RF-066, RF-067, RF-092 | `schemas/*.py` |
| RNF-008 | Cabeceras de seguridad | — | Transversal (toda respuesta HTTP) | `api/securityHeaders.py`, `docker/nginx/default.conf.template` |
| RNF-009 | CORS y API sin cookies | RN-009, RN-010 | RF-003, Transversal | `main.py` |
| RNF-010 | Transporte cifrado | — | RF-003, RF-093, Transversal | `db/session.py`, `integrations/email/sender.py`, `compose.prod.yaml` |
| RNF-011 | Gestión de secretos y configuración | — | RF-084, Transversal | `.gitignore`, `core/config.py` |
| RNF-012 | Endurecimiento de contenedores | — | Transversal (despliegue) | `compose.yaml`, `backend/Dockerfile` |
| RNF-013 | Cadena de suministro | — | Transversal (despliegue) | `backend/Dockerfile`, `requirements.txt`, `package-lock.json` |
| RNF-014 | Mínimo privilegio en la base | RN-085 | RF-086, RF-087, RF-091 | `database/reference/GlucoLume_permisos.sql`; `Auditoria` |
| RNF-015 | Autenticación del puente | RN-074 | RF-062, RF-063 | `core/config.py`, `api/rateLimit.py`, `acquisition/bridge/glucolume_bridge.py` |
| RNF-016 | Sin enumeración de cuentas | RN-008, RN-013 | RF-001, RF-002, RF-006 | `services/auth.py` |
| RNF-017 | Minimización en auditoría, registros y correos | RN-085, RN-092 | RF-054, RF-086, RF-087, RF-088, RF-089, RF-093 | `services/audit.py`, `services/email.py`; `Auditoria` |
| RNF-018 | Cifrado en reposo | RN-095 | RF-094, Transversal | `database/reference/GlucoLume_cifrado_y_respaldo.sql` |
| RNF-019 | Sin analítica de terceros | — | RF-097, RF-098 | `frontend/package.json`, CSP de Nginx |
| RNF-020 | Control de volumen | RN-032, RN-066 | RF-035, RF-038, RF-049, RF-052, RF-075, RF-086 | `services/measurement.py`, `group.py`, `institutionPatients.py` |
| RNF-021 | Objetivos de tiempo de respuesta | — | Transversal | (sin respaldo) |
| RNF-022 | Tope de transmisiones | RN-072 | RF-064 | `api/streams.py` |
| RNF-023 | Tamaño de entrega del frontend | — | RF-098, RF-100 | `frontend/src/App.jsx` |
| RNF-024 | Vida independiente de la base | — | RF-078, Transversal | `main.py`, `compose.yaml` |
| RNF-025 | Degradación controlada | RN-091 | RF-025, RF-044, RF-054, RF-093 | `services/schemaCompat.py`, `utils/dbRetry.py` |
| RNF-026 | Continuidad de la adquisición | RN-072, RN-074 | RF-048, RF-063, RF-064 | `acquisition/bridge/glucolume_bridge.py` |
| RNF-027 | Objetivo de disponibilidad | — | Transversal | (sin respaldo) |
| RNF-028 | Integridad referencial y de dominio | RN-026, RN-027, RN-042, RN-047, RN-076 | RF-018, RF-025, RF-037, RF-040, RF-046, RF-056, RF-066 | `GlucoLume_DB_v5.sql`, `models/*.py` |
| RNF-029 | Atomicidad y concurrencia | RN-007, RN-024, RN-037, RN-038, RN-048, RN-055, RN-081 | RF-016, RF-028, RF-034, RF-040, RF-041, RF-048, RF-068, RF-080 | `services/accountGrace.py`, `quota.py`, `measurement.py` |
| RNF-030 | Hora de Argentina única | RN-004, RN-024 | Transversal | `utils/timeZone.py` |
| RNF-031 | Auditoría de solo inserción | RN-085, RN-088 | RF-086, RF-087, RF-091 | `services/audit.py`, `auditRetention.py` |
| RNF-032 | Correlación de solicitudes | RN-085, RN-086 | RF-086, RF-087, RF-088, RF-089 | `api/requestContext.py`, `services/audit.py` |
| RNF-033 | Trazabilidad del valor medido | RN-057, RN-059, RN-060, RN-064 | RF-046, RF-047, RF-048, RF-050, RF-055 | `models/measurement.py` |
| RNF-034 | Arquitectura en capas y documentación | — | Transversal | `backend/app/**`, `frontend/src/**` |
| RNF-035 | Pruebas automatizadas aisladas | — | Transversal | `backend/tests/**`, `frontend/src/**/*.test.*` |
| RNF-036 | Diferencias de esquema | — | RF-085 | `cli/schemaCheck.py`, `tests/test_reference_schema.py` |
| RNF-037 | Dependencias reproducibles | — | Transversal | `requirements*.txt`, `package-lock.json` |
| RNF-038 | Accesibilidad | — | RF-097, RF-098, RF-100 | `components/SkipLink.jsx`, `Modal.jsx`, `Tabs.jsx` |
| RNF-039 | Diseño adaptable | — | Transversal (interfaz) | `frontend/src/**/*.css` |
| RNF-040 | Mensajes en español y códigos estables | — | Transversal | `api/errors.py`, `auth/errorMessages.js` |
| RNF-041 | Transparencia del carácter experimental | RN-060, RN-061 | RF-048, RF-050, RF-055 | `components/ExperimentalNotice.jsx`, firmware |
| RNF-042 | API REST versionada | — | Transversal | `main.py`, `api/v1/*.py` |
| RNF-043 | Integraciones externas | RN-009 | RF-003, RF-058, RF-063, RF-065, RF-093 | `integrations/**`, `acquisition/protocol.py` |
| RNF-044 | Tiempo real por SSE | — | RF-060, RF-064 | `api/v1/telemetry.py`, Nginx |
| RNF-045 | Plataforma tecnológica | — | Transversal | `backend/Dockerfile`, `frontend/package.json` |
| RNF-046 | Bases sin migrar | RN-037, RN-041, RN-052 | RF-033, RF-044, RF-046, RF-082, RF-094 | `services/schemaCompat.py` |
| RNF-047 | Estado en memoria (una réplica) | RN-018, RN-072, RN-087 | RF-061, RF-062, RF-064, RF-088, RF-092 | `api/rateLimit.py`, `acquisition/telemetry.py` |
| RNF-048 | Capacidad por institución | RN-037 | RF-028, RF-033, RF-081 | `services/quota.py` |
| RNF-049 | Despliegue con contenedores | — | Transversal | `compose*.yaml` |
| RNF-050 | Configuración por variables | — | Transversal | `.env.example`, `core/config.py` |
| RNF-051 | Observabilidad básica | — | RF-078 | `compose.yaml`, `services/platformDashboard.py` |
| RNF-052 | Respaldo y restauración | — | Transversal | `database/respaldos/*.ps1` |
| RNF-053 | Recuperación administrativa y de claves MFA | RN-082 | RF-012, RF-084, RF-085 | `cli/recoverAdmin.py`, `cli/mfaKeys.py` |
| RNF-054 | Referencia a la Ley 25.326 | RN-002, RN-021, RN-023, RN-051, RN-094, RN-095, RN-096 | RF-013, RF-015, RF-043, RF-044, RF-094, RF-095, RF-098 | `services/consent.py`, `docs/PRIVACIDAD_Y_RETENCION.md` |

## 4. Endpoints → RF

Cada fila es un endpoint de `/api/v1`. El archivo de ruta y la línea de la función figuran en el inventario extraído (`backend/app/api/v1/`).

| Método | Ruta | RF |
|---|---|---|
| GET | `/acquisition/ports` | RF-065 |
| GET | `/acquisition/status` | RF-065 |
| POST | `/acquisition/connect` | RF-065 |
| POST | `/acquisition/disconnect` | RF-065 |
| POST | `/acquisition/probe` | RF-065 |
| POST | `/acquisition/identify` | RF-065 |
| POST | `/acquisition/start` | RF-065 |
| POST | `/acquisition/finish` | RF-065 |
| POST | `/acquisition/cancel` | RF-065 |
| GET | `/acquisition/stream` | RF-064 |
| GET | `/audit` | RF-086 |
| GET | `/audit/summary` | RF-086 |
| GET | `/audit/security/signals` | RF-088 |
| GET | `/audit/institutions` | RF-086 |
| GET | `/audit/accounts` | RF-089 |
| GET | `/audit/accounts/{idUsuario}` | RF-089 |
| GET | `/audit/technical-measurements` | RF-090 |
| GET | `/audit/technical-measurements/summary` | RF-090 |
| GET | `/audit/events/{idAuditoria}` | RF-086 |
| GET | `/institutions/{idInstitucion}/audit` | RF-087 |
| GET | `/institutions/{idInstitucion}/audit/summary` | RF-087 |
| GET | `/institutions/{idInstitucion}/audit/events/{idAuditoria}` | RF-087 |
| POST | `/auth/register` | RF-001 |
| GET | `/auth/verify-email` | RF-001 |
| POST | `/auth/verify-email/resend` | RF-001 |
| POST | `/auth/login` | RF-002 |
| GET | `/auth/google/login` | RF-003 |
| GET | `/auth/google/authorization-url` | RF-003 |
| GET | `/auth/google/callback` | RF-003 |
| POST | `/auth/google/exchange` | RF-003 |
| POST | `/auth/session-transfer` | RF-003 |
| POST | `/auth/mfa/verify` | RF-010 |
| POST | `/auth/mfa/recovery/start` | RF-012 |
| POST | `/auth/mfa/recovery/verify` | RF-012 |
| POST | `/auth/mfa/setup` | RF-009 |
| POST | `/auth/mfa/enable` | RF-009 |
| POST | `/auth/me/mfa/recovery/start` | RF-012 |
| POST | `/auth/me/mfa/recovery/verify` | RF-012 |
| POST | `/auth/mfa/disable` | RF-011 |
| POST | `/auth/refresh` | RF-004 |
| POST | `/auth/logout` | RF-004 |
| GET | `/auth/me` | RF-004 |
| PATCH | `/auth/me/profile` | RF-005 |
| POST | `/auth/password` | RF-007 |
| POST | `/auth/password/forgot` | RF-006 |
| POST | `/auth/password/reset` | RF-006 |
| POST | `/auth/password/change` | RF-007 |
| PUT | `/auth/me/notifications/new-login` | RF-014 |
| POST | `/auth/notifications/new-login/unsubscribe` | RF-014 |
| GET | `/auth/account-deletion/preview` | RF-015 |
| POST | `/auth/account-deletion/request` | RF-015 |
| POST | `/auth/account-deletion/confirm` | RF-015 |
| POST | `/auth/account-activation/check` | RF-008 |
| POST | `/auth/account-activation/complete` | RF-008 |
| GET | `/auth/consents` | RF-013 |
| PUT | `/auth/consents/datos-experimentales` | RF-013 |
| POST | `/contact` | RF-092 |
| POST | `/devices/resolve` | RF-058 |
| GET | `/devices` | RF-056 |
| GET | `/devices/summary` | RF-056 |
| POST | `/devices` | RF-056 |
| GET | `/devices/institutions` | RF-056 |
| GET | `/devices/institutions/{idInstitucion}/responsibles` | RF-056 |
| GET | `/devices/{idDispositivo}` | RF-056 |
| PATCH | `/devices/{idDispositivo}` | RF-056 |
| POST | `/devices/{idDispositivo}/state` | RF-056 |
| POST | `/devices/{idDispositivo}/assign` | RF-056 |
| POST | `/devices/{idDispositivo}/responsible` | RF-056 |
| POST | `/devices/{idDispositivo}/unassign` | RF-056 |
| POST | `/devices/{idDispositivo}/decommission` | RF-056 |
| GET | `/devices/{idDispositivo}/measurements` | RF-059 |
| GET | `/institutions/{idInstitucion}/devices` | RF-057 |
| GET | `/institutions/{idInstitucion}/devices/summary` | RF-057 |
| GET | `/institutions/{idInstitucion}/devices/responsibles` | RF-057 |
| POST | `/institutions/{idInstitucion}/devices` | RF-057 |
| GET | `/institutions/{idInstitucion}/devices/{idDispositivo}` | RF-057 |
| PATCH | `/institutions/{idInstitucion}/devices/{idDispositivo}` | RF-057 |
| POST | `/institutions/{idInstitucion}/devices/{idDispositivo}/state` | RF-057 |
| POST | `/institutions/{idInstitucion}/devices/{idDispositivo}/responsible` | RF-057 |
| POST | `/institutions/{idInstitucion}/devices/{idDispositivo}/unassign` | RF-057 |
| POST | `/institutions/{idInstitucion}/devices/{idDispositivo}/decommission` | RF-057 |
| GET | `/institutions/{idInstitucion}/devices/{idDispositivo}/measurements` | RF-059 |
| GET | `/groups/mine` | RF-018 |
| GET | `/groups/invitations` | RF-019 |
| POST | `/groups/invitations/{idGrupoUsuario}/accept` | RF-019 |
| POST | `/groups/invitations/{idGrupoUsuario}/reject` | RF-019 |
| POST | `/groups` | RF-018 |
| POST | `/groups/{idGrupo}/creation-notice` | RF-018 |
| GET | `/groups/{idGrupo}` | RF-018 |
| PATCH | `/groups/{idGrupo}` | RF-018 |
| POST | `/groups/{idGrupo}/deletion` | RF-021 |
| POST | `/groups/{idGrupo}/leave` | RF-020 |
| POST | `/groups/{idGrupo}/transfer` | RF-020 |
| GET | `/groups/{idGrupo}/members` | RF-020 |
| DELETE | `/groups/{idGrupo}/members/{idGrupoUsuario}` | RF-020 |
| GET | `/groups/{idGrupo}/invitations` | RF-019 |
| POST | `/groups/{idGrupo}/invitations/lookup` | RF-019 |
| POST | `/groups/{idGrupo}/invitations` | RF-019 |
| DELETE | `/groups/{idGrupo}/invitations/{idGrupoUsuario}` | RF-019 |
| GET | `/groups/{idGrupo}/sharing/me` | RF-022 |
| PUT | `/groups/{idGrupo}/sharing/me` | RF-022 |
| GET | `/groups/{idGrupo}/shared` | RF-023 |
| GET | `/groups/{idGrupo}/shared/{idGrupoUsuario}/profile` | RF-023 |
| GET | `/groups/{idGrupo}/shared/{idGrupoUsuario}/latest` | RF-023 |
| GET | `/groups/{idGrupo}/shared/{idGrupoUsuario}/history` | RF-023 |
| GET | `/groups/{idGrupo}/shared/{idGrupoUsuario}/notices` | RF-023 |
| GET | `/groups/{idGrupo}/dashboard` | RF-024 |
| GET | `/groups/{idGrupo}/shared/{idGrupoUsuario}/measurements/{idMedicion}` | RF-023 |
| GET | `/groups/{idGrupo}/shared/{idGrupoUsuario}/statistics` | RF-023 |
| POST | `/institutions/{idInstitucion}/support-request` | RF-036 |
| GET | `/institutions/mine` | RF-028 |
| GET | `/institutions/invitations` | RF-028 |
| POST | `/institutions/invitations/{idInstitucionUsuario}/accept` | RF-028 |
| POST | `/institutions/invitations/{idInstitucionUsuario}/reject` | RF-028 |
| POST | `/institutions/legal-id/status` | RF-025 |
| POST | `/institutions` | RF-025 |
| POST | `/institutions/reopen` | RF-026 |
| POST | `/institutions/{idInstitucion}/creation-notice` | RF-025 |
| GET | `/institutions/{idInstitucion}` | RF-027 |
| PATCH | `/institutions/{idInstitucion}` | RF-027 |
| POST | `/institutions/{idInstitucion}/deletion` | RF-034 |
| GET | `/institutions/{idInstitucion}/activity` | RF-035 |
| GET | `/institutions/{idInstitucion}/quota` | RF-033 |
| GET | `/institutions/{idInstitucion}/personnel` | RF-031 |
| GET | `/institutions/{idInstitucion}/invitations` | RF-031 |
| GET | `/institutions/{idInstitucion}/personnel/{idInstitucionUsuario}` | RF-031 |
| DELETE | `/institutions/{idInstitucion}/personnel/{idInstitucionUsuario}/personal-data` | RF-032 |
| GET | `/institutions/{idInstitucion}/members` | RF-031 |
| GET | `/institutions/{idInstitucion}/moderators` | RF-029 |
| POST | `/institutions/{idInstitucion}/moderators/lookup` | RF-029 |
| POST | `/institutions/{idInstitucion}/moderators` | RF-029 |
| PATCH | `/institutions/{idInstitucion}/moderators/{idInstitucionUsuario}` | RF-029, RF-030 |
| POST | `/institutions/{idInstitucion}/moderators/{idInstitucionUsuario}/resend` | RF-029 |
| DELETE | `/institutions/{idInstitucion}/moderators/{idInstitucionUsuario}` | RF-029 |
| GET | `/institutions/{idInstitucion}/operators` | RF-029 |
| POST | `/institutions/{idInstitucion}/operators/lookup` | RF-029 |
| POST | `/institutions/{idInstitucion}/operators` | RF-029 |
| PATCH | `/institutions/{idInstitucion}/operators/{idInstitucionUsuario}` | RF-029, RF-030 |
| POST | `/institutions/{idInstitucion}/operators/{idInstitucionUsuario}/resend` | RF-029 |
| GET | `/institutions/{idInstitucion}/operators/{idInstitucionUsuario}/offboarding` | RF-041 |
| POST | `/institutions/{idInstitucion}/operators/{idInstitucionUsuario}/offboard` | RF-041 |
| DELETE | `/institutions/{idInstitucion}/operators/{idInstitucionUsuario}` | RF-029, RF-041 |
| GET | `/institutions/{idInstitucion}/patients` | RF-038 |
| GET | `/institutions/{idInstitucion}/patients/assignable-operators` | RF-037 |
| GET | `/institutions/{idInstitucion}/reassignments` | RF-042 |
| GET | `/institutions/{idInstitucion}/reassignments/items` | RF-042 |
| POST | `/institutions/{idInstitucion}/reassignments/assign` | RF-042 |
| POST | `/institutions/{idInstitucion}/reassignments/regularize` | RF-042 |
| POST | `/institutions/{idInstitucion}/patients` | RF-037 |
| GET | `/institutions/{idInstitucion}/patients/{idPerfilMedicion}` | RF-038 |
| PATCH | `/institutions/{idInstitucion}/patients/{idPerfilMedicion}` | RF-038 |
| POST | `/institutions/result-email/confirm` | RF-044 |
| PUT | `/institutions/{idInstitucion}/patients/{idPerfilMedicion}/result-email` | RF-044 |
| DELETE | `/institutions/{idInstitucion}/patients/{idPerfilMedicion}/result-email` | RF-044 |
| PUT | `/institutions/{idInstitucion}/patients/{idPerfilMedicion}/responsible` | RF-039 |
| GET | `/institutions/{idInstitucion}/patients/{idPerfilMedicion}/measurements` | RF-049 |
| GET | `/institutions/{idInstitucion}/patients/{idPerfilMedicion}/measurements/statistics` | RF-052 |
| GET | `/institutions/{idInstitucion}/patients/{idPerfilMedicion}/measurements/evolution` | RF-052 |
| GET | `/institutions/{idInstitucion}/dashboard` | RF-072 |
| GET | `/institutions/{idInstitucion}/analytics/patients` | RF-075 |
| GET | `/institutions/{idInstitucion}/operators/{idOperador}/dashboard` | RF-073 |
| GET | `/institutions/{idInstitucion}/patients/{idPerfilMedicion}/dashboard` | RF-074 |
| GET | `/institutions/{idInstitucion}/indicators` | RF-076 |
| POST | `/institutions/{idInstitucion}/patients/{idPerfilMedicion}/discharge` | RF-043 |
| POST | `/institutions/{idInstitucion}/patients/{idPerfilMedicion}/transfers` | RF-040 |
| GET | `/institutions/{idInstitucion}/transfers` | RF-040 |
| GET | `/institutions/{idInstitucion}/transfers/{idTransferenciaPerfil}` | RF-040 |
| POST | `/institutions/{idInstitucion}/transfers/{idTransferenciaPerfil}/accept` | RF-040 |
| POST | `/institutions/{idInstitucion}/transfers/{idTransferenciaPerfil}/reject` | RF-040 |
| POST | `/institutions/{idInstitucion}/transfers/{idTransferenciaPerfil}/cancel` | RF-040 |
| GET | `/institutions/{idInstitucion}/matrices` | RF-070 |
| GET | `/institutions/{idInstitucion}/matrices/effective` | RF-070 |
| GET | `/matrices/global` | RF-070 |
| POST | `/matrices/check-rules` | RF-066 |
| POST | `/matrices` | RF-066 |
| GET | `/matrices/{idMatriz}` | RF-070 |
| PATCH | `/matrices/{idMatriz}` | RF-067 |
| POST | `/matrices/{idMatriz}/new-version` | RF-069 |
| POST | `/matrices/{idMatriz}/validate` | RF-068 |
| POST | `/matrices/{idMatriz}/activate` | RF-068 |
| POST | `/matrices/{idMatriz}/deactivate` | RF-068 |
| POST | `/matrices/{idMatriz}/archive` | RF-068 |
| GET | `/matrices/{idMatriz}/audit` | RF-070 |
| POST | `/matrices/{idMatriz}/rules` | RF-067 |
| PATCH | `/matrices/{idMatriz}/rules/{idReglaMatriz}` | RF-067 |
| DELETE | `/matrices/{idMatriz}/rules/{idReglaMatriz}` | RF-067 |
| GET | `/measurements/profile` | RF-045 |
| GET | `/measurements/devices` | RF-046 |
| GET | `/measurements/matrix` | RF-046 |
| POST | `/measurements` | RF-046 |
| GET | `/measurements` | RF-049 |
| DELETE | `/measurements/demo` | RF-053 |
| GET | `/measurements/statistics` | RF-052 |
| GET | `/measurements/evolution` | RF-052 |
| GET | `/measurements/dashboard` | RF-071 |
| GET | `/measurements/{idMedicion}` | RF-050 |
| DELETE | `/measurements/{idMedicion}` | RF-053 |
| POST | `/measurements/{idMedicion}/samples` | RF-047 |
| POST | `/measurements/{idMedicion}/finish` | RF-047 |
| POST | `/measurements/{idMedicion}/cancel` | RF-047 |
| POST | `/measurements/{idMedicion}/capillary-reference` | RF-051 |
| POST | `/measurements/{idMedicion}/send-result` | RF-054 |
| GET | `/platform/me` | RF-083 |
| GET | `/platform/dashboard` | RF-078 |
| GET | `/platform/institutions` | RF-081 |
| GET | `/platform/institutions/{idInstitucion}` | RF-081 |
| GET | `/platform/institutions/{idInstitucion}/audit` | RF-081 |
| POST | `/platform/institutions/{idInstitucion}/pause` | RF-081 |
| POST | `/platform/institutions/{idInstitucion}/reactivate` | RF-081 |
| POST | `/platform/institutions/{idInstitucion}/delete` | RF-082 |
| PUT | `/platform/institutions/{idInstitucion}/capacity` | RF-081 |
| GET | `/platform/system` | RF-078 |
| GET | `/platform/moderators` | RF-079 |
| POST | `/platform/moderators` | RF-079 |
| GET | `/platform/moderators/{idUsuario}` | RF-079 |
| POST | `/platform/moderators/{idUsuario}/resend-invitation` | RF-079 |
| POST | `/platform/moderators/{idUsuario}/revoke` | RF-079 |
| POST | `/platform/moderators/{idUsuario}/password-reset` | RF-079 |
| GET | `/platform/transfer` | RF-080 |
| POST | `/platform/transfer` | RF-080 |
| POST | `/platform/transfer/cancel` | RF-080 |
| POST | `/platform/transfer/accept` | RF-080 |
| POST | `/platform/transfer/reject` | RF-080 |
| POST | `/platform/password/change` | RF-083 |
| POST | `/platform/activation/with-code` | RF-077 |
| POST | `/platform/password/forgot` | RF-077 |
| POST | `/platform/password/reset` | RF-077 |
| POST | `/acquisition/bridge/ingest` | RF-063 |
| POST | `/acquisition/bridge/check` | RF-063 |
| POST | `/acquisition/bridge/command` | RF-062 |
| POST | `/acquisition/telemetry/control` | RF-061 |
| DELETE | `/acquisition/telemetry/control` | RF-061 |
| GET | `/acquisition/telemetry/readiness` | RF-060 |
| POST | `/acquisition/telemetry/device/register` | RF-058 |
| POST | `/acquisition/telemetry/device/link` | RF-058 |
| POST | `/acquisition/telemetry/device/confirm` | RF-058 |
| GET | `/acquisition/telemetry/status` | RF-060 |
| GET | `/acquisition/telemetry/stream` | RF-064 |
| POST | `/acquisition/telemetry/session` | RF-048 |
| POST | `/acquisition/telemetry/session/save` | RF-048 |
| POST | `/acquisition/telemetry/session/cancel` | RF-048 |

## 5. Tablas de la base → RF y RN

| Tabla | RF que la usan (según la evidencia de cada RF) | RN con restricciones o índices en la tabla |
|---|---|---|
| `Usuario` | RF-001, RF-005, RF-008, RF-014, RF-015, RF-016, RF-017, RF-029, RF-077, RF-079, RF-083, RF-084 | RN-005, RN-079 |
| `CredencialLocal` | RF-001, RF-002, RF-007 | RN-007 |
| `IdentidadExterna` | RF-003 | — |
| `FactorMfa` | RF-009, RF-010, RF-011, RF-012, RF-083 | RN-015 |
| `CodigoRecuperacionMfa` | RF-009 | — |
| `SesionUsuario` | RF-002, RF-004 | — |
| `TokenCuenta` | RF-001, RF-003, RF-006, RF-008, RF-012, RF-015, RF-029, RF-077, RF-079 | — |
| `ConsentimientoUsuario` | RF-001, RF-013 | RN-021 |
| `ConfiguracionNotificacion` | RF-096 | — |
| `Institucion` | RF-025, RF-026, RF-027, RF-033, RF-034, RF-081, RF-082 | RN-035, RN-037, RN-041 |
| `InstitucionUsuario` | RF-008, RF-028, RF-029, RF-030, RF-031, RF-032, RF-041, RF-095 | RN-042 |
| `Grupo` | RF-018, RF-021 | — |
| `GrupoUsuario` | RF-018, RF-019, RF-020, RF-022, RF-023 | RN-026, RN-027 |
| `TransferenciaPerfil` | RF-039, RF-040 | RN-048 |
| `ReasignacionPaciente` | RF-042 | RN-050 |
| `TransferenciaAdministracion` | RF-080 | RN-081 |
| `PerfilMedicion` | RF-023, RF-037, RF-038, RF-039, RF-041, RF-043, RF-044, RF-045, RF-072, RF-074, RF-075, RF-094 | RN-047, RN-095 |
| `Medicion` | RF-023, RF-024, RF-046, RF-047, RF-048, RF-049, RF-050, RF-052, RF-053, RF-059, RF-071, RF-072, RF-073, RF-074, RF-075, RF-094 | RN-055, RN-060, RN-061, RN-095 |
| `MuestraSensor` | RF-047, RF-053, RF-065 | — |
| `MedicionReferenciaCapilar` | RF-050, RF-051 | RN-063 |
| `Dispositivo` | RF-056, RF-057, RF-058, RF-059, RF-063 | RN-068, RN-069 |
| `Matriz` | RF-066, RF-067, RF-069, RF-070 | RN-076 |
| `ReglaMatriz` | RF-066, RF-067 | RN-077 |
| `EnvioResultado` | RF-053, RF-054 | RN-065 |
| `PlanSuscripcion` | RF-096 | — |
| `Suscripcion` | RF-096 | — |
| `SuscripcionUsuario` | RF-096 | — |
| `PeriodoPrueba` | RF-096 | — |
| `ProveedorPago` | RF-096 | — |
| `TransaccionPago` | RF-096 | — |
| `Auditoria` | RF-035, RF-036, RF-070, RF-073, RF-081, RF-084, RF-086, RF-087, RF-088, RF-089, RF-091 | — |
| `AuditoriaContexto` | RF-086, RF-091 | — |
| `AuditoriaTecnicaMedicion` | RF-090 | — |

## 6. Dependencias entre requerimientos

| Requerimiento | Depende de | Motivo |
|---|---|---|
| RF-002, RF-003 | RF-001 | Solo una cuenta activa, creada y verificada, inicia sesión. |
| RF-010, RF-011, RF-012 | RF-009 | El segundo factor debe estar habilitado para verificarse, desactivarse o recuperarse. |
| RF-015 | RF-020, RF-021, RF-029 | La eliminación de cuenta exige haber transferido o cerrado grupos y finalizado los vínculos institucionales. |
| RF-016 | RF-029, RF-034 | El período de gracia nace al perder el último vínculo (baja de personal o cierre de institución). |
| RF-019, RF-020, RF-022, RF-023, RF-024 | RF-018 | Todo el módulo de grupos parte de un grupo activo. |
| RF-023, RF-024 | RF-022 | Solo se consulta lo que el dueño autorizó compartir. |
| RF-029, RF-037, RF-057 | RF-025 | Sin institución no hay personal, pacientes ni inventario. |
| RF-028 | RF-029 | Las invitaciones recibidas se crean al incorporar personal. |
| RF-008 | RF-029 | La activación por invitación existe porque una institución invitó a un correo sin cuenta. |
| RF-037, RF-038, RF-039, RF-040 | RF-029 | Un paciente se asigna a un operador activo incorporado previamente. |
| RF-041, RF-042 | RF-037, RF-040 | Reasignar y desvincular operan sobre pacientes y transferencias existentes. |
| RF-043 | RF-037 | Solo se da de baja a un paciente registrado. |
| RF-094 | RF-043, RF-034 | La retención y anonimización se inician con la baja del paciente o el cierre de la institución. |
| RF-044, RF-054 | RF-037, RF-048 | El resultado por correo se envía de una medición completada de un paciente con correo confirmado. |
| RF-046, RF-048 | RF-013, RF-045, RF-056, RF-058, RF-061, RF-066 | Medir exige consentimiento, perfil, dispositivo operativo identificado, control del equipo y, para glucosa por matriz, una matriz con regla. |
| RF-047, RF-065 | RF-046 | Las muestras crudas se registran sobre una medición ya iniciada. |
| RF-048 | RF-060, RF-063 | La sesión con el dispositivo exige un puente activo que envíe lecturas. |
| RF-051, RF-054 | RF-048 | La referencia capilar y el envío operan sobre una medición completada. |
| RF-052, RF-071, RF-072, RF-073, RF-074, RF-075, RF-076 | RF-048, RF-047 | Los indicadores se calculan sobre mediciones completadas. |
| RF-055 | RF-066, RF-068 | Una estimación por el servidor requeriría matriz activa y regla aplicable; hoy no hay algoritmo. |
| RF-058 | RF-056, RF-057, RF-063 | Registrar y vincular un dispositivo usa el inventario y la identidad informada por el puente. |
| RF-061, RF-062 | RF-060 | Tomar el control y dar órdenes requieren conocer el estado del puente. |
| RF-068 | RF-066, RF-067 | Solo se activa una matriz con reglas válidas creadas y editadas. |
| RF-079, RF-080 | RF-077 | La administración opera con una cuenta activada y con MFA. |
| RF-081, RF-082 | RF-025 | Controlan instituciones existentes. |
| RF-086, RF-087, RF-088, RF-089, RF-090 | Todos los RF que registran eventos | La auditoría muestra lo que los demás módulos registran. |
| RF-091 | RF-086 | La conservación depura lo que la auditoría consulta. |
| RF-093 | Todos los RF que envían avisos | Los correos son efecto de operaciones de otros módulos. |
| RF-096, RF-099 | — | Previstos: no dependen de funcionalidad existente. |

## 7. Verificación de integridad de la matriz

- Requerimientos funcionales: **100**; reglas de negocio: **96**; requerimientos no funcionales: **54**; endpoints: **241**.
- Endpoints sin requerimiento funcional asociado: **0**.
- Reglas de negocio sin requerimiento funcional que las use: **0**.
- Requerimientos funcionales sin regla de negocio asociada: **2** (RF-096, RF-097), todos previstos o sin regla propia.
- Endpoints asignados a más de un RF: **3** (rutas compartidas entre funciones; por ejemplo el retiro de un operador).

