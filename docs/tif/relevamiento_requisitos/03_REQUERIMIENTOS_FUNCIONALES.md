# 03 — Requerimientos funcionales de GlucoLume

**Relevamiento por ingeniería inversa** · Etapa 3 · 21 de octubre de 2026.

Este documento enumera los requerimientos funcionales (RF) verificables del sistema, redactados como «El sistema debe permitir…». Cada uno indica actor, precondiciones, comportamiento y resultado, las reglas de negocio relacionadas (`02_REGLAS_NEGOCIO.md`), la evidencia en backend, frontend y base de datos, las pruebas relacionadas y el estado real.

## Convenciones

- **Evidencia:** `Back:` servicio y ruta (`backend/app/...`; las rutas HTTP se escriben sin el prefijo `/api/v1`). `Front:` archivos bajo `frontend/src/` (o «sin pantalla»). `BD:` tablas o restricciones relevantes.
- **Disponibilidad:** se indica explícitamente cuando una funcionalidad existe en el backend y no en la interfaz, o viceversa. La comprobación de la interfaz es estática (lectura de rutas, módulos de acceso a la API y pantallas): no se ejecutó la aplicación en un navegador.
- **Pruebas:** archivos de prueba que ejercitan el tema. El resultado de su ejecución se informa en `07_RESUMEN_EJECUTIVO.md`.
- **Estados:** IMPLEMENTADO, PARCIAL, PREVISTO, OBSOLETO, NO VERIFICADO (definidos en `01_INVENTARIO_MODULOS.md`, sección 1.3).

## Resumen

| Módulo | RF | Cantidad |
|---|---|---|
| M-01 Autenticación y sesiones | RF-001 a RF-008 | 8 |
| M-02 Verificación en dos pasos | RF-009 a RF-012 | 4 |
| M-03 Cuenta personal | RF-013 a RF-017 | 5 |
| M-04 Grupos familiares | RF-018 a RF-024 | 7 |
| M-05 Instituciones | RF-025 a RF-036 | 12 |
| M-06 Pacientes institucionales | RF-037 a RF-044 | 8 |
| M-07 Mediciones | RF-045 a RF-055 | 11 |
| M-08 Dispositivos | RF-056 a RF-059 | 4 |
| M-09 Adquisición y telemetría | RF-060 a RF-065 | 6 |
| M-10 Matrices | RF-066 a RF-070 | 5 |
| M-11 Paneles e indicadores | RF-071 a RF-076 | 6 |
| M-12 Plataforma | RF-077 a RF-085 | 9 |
| M-13 Auditoría | RF-086 a RF-091 | 6 |
| M-14 a M-17 Correo, retención, suscripciones y contenido | RF-092 a RF-100 | 9 |
| **Total** | | **100** |

---

## M-01 Autenticación y sesiones

### RF-001 — Registro local con verificación de correo
- **Descripción:** El sistema debe permitir que una persona cree una cuenta individual o institucional con correo, contraseña y aceptación de la política de privacidad, y que verifique su correo desde un enlace.
- **Actor / precondiciones:** persona sin cuenta; correo y usuario no registrados.
- **Comportamiento y resultado:** crea un usuario `PENDIENTE` con credencial local (hash Argon2id) y envía un enlace de verificación; al abrirlo la cuenta pasa a `ACTIVO`. Permite reenviar el enlace (respuesta uniforme). La cuenta no verificada en 24 horas se elimina.
- **RN:** RN-001, RN-002, RN-003, RN-004, RN-005, RN-018.
- **Evidencia:** Back: `services/auth.py:148-361`; API `auth.py` `POST /auth/register`, `GET /auth/verify-email`, `POST /auth/verify-email/resend`. Front: `pages/Register/Register.jsx`, `RegisterForm.jsx`, `RegisterSuccess.jsx`, `VerifyEmail.jsx`, `components/ResendVerification.jsx`. BD: `Usuario`, `CredencialLocal`, `TokenCuenta`, `ConsentimientoUsuario`.
- **Pruebas:** `test_register_contact.py`, `test_username.py`, `test_account_lifecycle.py`, `Register.test.jsx`, `VerifyEmail.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-002 — Inicio de sesión con correo o nombre de usuario
- **Descripción:** El sistema debe permitir iniciar sesión con correo o nombre de usuario y contraseña, con bloqueo temporal tras intentos fallidos.
- **Actor / precondiciones:** cuenta activa con credencial local.
- **Comportamiento y resultado:** entrega un par de tokens (acceso de 30 minutos y renovación de 7 días) o, si hay MFA, un desafío de 5 minutos. Responde de forma uniforme ante credenciales inválidas y bloquea 15 minutos tras 3 fallos. Informa si falta completar el perfil sin bloquear el acceso.
- **RN:** RN-006, RN-007, RN-008, RN-011, RN-015, RN-018.
- **Evidencia:** Back: `services/auth.py:522-595,818-889`; API `POST /auth/login`. Front: `pages/Login/Login.jsx`, `auth/AuthContext.jsx`, `auth/tokenStore.js`. BD: `CredencialLocal` (`CK_CredencialLocal_intentos`), `SesionUsuario`.
- **Pruebas:** `test_login_lockout.py`, `test_auth_access.py`, `test_auth_access_flows.py`, `PublicAccess.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-003 — Acceso y registro con Google
- **Descripción:** El sistema debe permitir registrarse e iniciar sesión con una cuenta de Google, y vincular la cuenta de Google a una cuenta existente con el mismo correo verificado.
- **Actor / precondiciones:** persona con cuenta de Google; el servidor tiene configurados los datos de Google (si no, el acceso queda deshabilitado con una advertencia).
- **Comportamiento y resultado:** el callback entrega al frontend un código de un solo uso (120 s) que se canjea por la sesión; admite continuar la sesión en otro origen. Iniciar sesión no crea cuentas; el registro sí y exige la política de privacidad.
- **RN:** RN-002, RN-009, RN-010.
- **Evidencia:** Back: `services/auth.py:598-730`, `integrations/google/oauth.py`; API `GET /auth/google/login`, `GET /auth/google/callback`, `POST /auth/google/exchange`, `POST /auth/session-transfer`, `GET /auth/google/authorization-url` (solo desarrollo). Front: `pages/Login/GoogleCallback.jsx`, `auth/googleLogin.js`, `auth/OriginGuard.jsx`. BD: `IdentidadExterna`, `TokenCuenta`.
- **Pruebas:** `test_google_exchange.py`.
- **Estado:** IMPLEMENTADO (el intercambio con el proveedor real de Google no se ejercita en las pruebas automatizadas; NO VERIFICADO contra el servicio real).

### RF-004 — Renovación y cierre de sesión; consulta de la cuenta actual
- **Descripción:** El sistema debe permitir renovar la sesión con rotación del token, cerrarla y consultar los datos de la cuenta autenticada (tipo, estado, MFA, período de gracia, perfil incompleto).
- **Actor / precondiciones:** cuenta autenticada.
- **Comportamiento y resultado:** la renovación revoca el token usado; reutilizar uno ya usado revoca todas las sesiones. El cierre de sesión revoca la sesión actual.
- **RN:** RN-011, RN-012.
- **Evidencia:** Back: `services/auth.py:895-937,1046-1072,1165-1177`; API `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`. Front: `auth/AuthContext.jsx`, `api/client.js`. BD: `SesionUsuario`.
- **Pruebas:** `test_auth_access_flows.py`, `client.test.js`, `tokenStore.test.js`.
- **Estado:** IMPLEMENTADO.

### RF-005 — Completar y actualizar el perfil personal
- **Descripción:** El sistema debe permitir completar y actualizar nombre, apellido, nombre de usuario, fecha de nacimiento y sexo.
- **Actor / precondiciones:** cuenta autenticada.
- **Comportamiento y resultado:** guarda y audita solo los cambios reales; valida disponibilidad del nombre de usuario; una cuenta de Google nueva debe elegir un nombre de usuario para completar la cuenta.
- **RN:** RN-020, RN-005.
- **Evidencia:** Back: `services/user.py`; API `PATCH /auth/me/profile`. Front: `pages/Account/ProfilePage.jsx`, `ProfileEditForm.jsx`, `ProfileSummary.jsx`. BD: `Usuario`.
- **Pruebas:** `test_profile.py`, `test_username.py`, `Account.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-006 — Recuperación de contraseña
- **Descripción:** El sistema debe permitir recuperar el acceso mediante un enlace de un solo uso enviado al correo.
- **Actor / precondiciones:** cuenta activa con credencial local, que no sea de plataforma.
- **Comportamiento y resultado:** emite un enlace con vigencia de 30 minutos y responde igual exista o no la cuenta; al completar, establece la nueva contraseña (con la política), cierra todas las sesiones y reinicia el bloqueo.
- **RN:** RN-003, RN-013, RN-018.
- **Evidencia:** Back: `services/auth.py:943-1035`; API `POST /auth/password/forgot`, `POST /auth/password/reset`. Front: `pages/Login/PasswordRecovery.jsx`. BD: `TokenCuenta`.
- **Pruebas:** `test_password_recovery.py`, `PublicAccess.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-007 — Cambiar la contraseña y agregar una contraseña local
- **Descripción:** El sistema debe permitir cambiar la contraseña con la sesión abierta y permitir que una cuenta solo con Google agregue una contraseña local.
- **Actor / precondiciones:** cuenta autenticada; contraseña actual y, si hay MFA, un código.
- **Comportamiento y resultado:** exige distinta contraseña, aplica la política, conserva la sesión actual y revoca las demás; envía aviso de cambio.
- **RN:** RN-003, RN-014.
- **Evidencia:** Back: `services/auth.py:1078-1120`; API `POST /auth/password` (alta), `POST /auth/password/change`. Front: `pages/Account/security/PasswordSection.jsx`. BD: `CredencialLocal`.
- **Pruebas:** `test_password_change.py`, `Account.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-008 — Activación de una cuenta creada por invitación institucional
- **Descripción:** El sistema debe permitir que una persona invitada por una institución valide su enlace de activación y active su cuenta eligiendo usuario y contraseña (o ingresando con Google con ese correo).
- **Actor / precondiciones:** persona con enlace vigente y al menos una invitación institucional vigente.
- **Comportamiento y resultado:** el sistema muestra quién invitó, activa la cuenta, consume el enlace, abre la sesión y registra la política; la invitación institucional sigue pendiente hasta que la persona la acepte.
- **RN:** RN-002, RN-003, RN-025.
- **Evidencia:** Back: `services/accountActivation.py`, `invitedAccounts.py`; API `POST /auth/account-activation/check`, `POST /auth/account-activation/complete`. Front: `pages/Register/ActivateAccount.jsx`. BD: `Usuario`, `TokenCuenta`, `InstitucionUsuario`.
- **Pruebas:** `test_institution_staff.py`, `test_personnel_incorporation.py`, `test_google_exchange.py`.
- **Estado:** IMPLEMENTADO.

## M-02 Verificación en dos pasos

### RF-009 — Configurar y activar la verificación en dos pasos
- **Descripción:** El sistema debe permitir generar un secreto TOTP (con código QR), confirmarlo con un código y recibir códigos de recuperación.
- **Actor / precondiciones:** cuenta autenticada; el servidor tiene configurada la clave de cifrado de MFA.
- **Comportamiento y resultado:** el secreto se guarda cifrado y pendiente; al confirmar un código válido el factor queda habilitado y se muestran 10 códigos de recuperación una sola vez; envía aviso por correo.
- **RN:** RN-015, RN-016.
- **Evidencia:** Back: `services/mfa.py:52-91`; API `POST /auth/mfa/setup`, `POST /auth/mfa/enable`. Front: `pages/Account/security/MfaSection.jsx` (con `qrcode.react`). BD: `FactorMfa`, `CodigoRecuperacionMfa`.
- **Pruebas:** `test_mfa_flow.py`, `Account.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-010 — Verificar el segundo factor al iniciar sesión
- **Descripción:** El sistema debe permitir completar el inicio de sesión con un código TOTP o un código de recuperación.
- **Actor / precondiciones:** cuenta con MFA habilitado y desafío vigente.
- **Comportamiento y resultado:** acepta exactamente uno de los dos factores, no admite reutilizar un código TOTP y bloquea el factor tras 5 fallos.
- **RN:** RN-015, RN-018.
- **Evidencia:** Back: `services/mfa.py:115-222`, `auth.py:863-889`; API `POST /auth/mfa/verify`. Front: `pages/Login/MfaForm.jsx`. BD: `FactorMfa` (`CK_FactorMfa_intentos`).
- **Pruebas:** `test_mfa_flow.py`, `test_mfa_attempts_atomic.py`.
- **Estado:** IMPLEMENTADO.

### RF-011 — Desactivar la verificación en dos pasos
- **Descripción:** El sistema debe permitir desactivar el MFA con un código válido.
- **Actor / precondiciones:** cuenta con MFA habilitado.
- **Comportamiento y resultado:** elimina el factor y sus códigos, audita el evento y avisa por correo.
- **RN:** RN-015.
- **Evidencia:** Back: `services/mfa.py:94-107`; API `POST /auth/mfa/disable`. Front: `pages/Account/security/MfaSection.jsx`. BD: `FactorMfa`.
- **Pruebas:** `test_mfa_flow.py`.
- **Estado:** IMPLEMENTADO.

### RF-012 — Recuperar el acceso cuando se perdió el autenticador
- **Descripción:** El sistema debe permitir recuperar el acceso sin la aplicación autenticadora mediante un código enviado al correo registrado, tanto desde el inicio de sesión como desde la sección de seguridad.
- **Actor / precondiciones:** cuenta con MFA; contraseña actual (o ingreso reciente con Google).
- **Comportamiento y resultado:** emite un código (10 minutos; 1 por minuto y 3 por hora); al verificarlo elimina el MFA, revoca las demás sesiones y avisa.
- **RN:** RN-016.
- **Evidencia:** Back: `services/mfaRecovery.py`; API `POST /auth/mfa/recovery/start|verify`, `POST /auth/me/mfa/recovery/start|verify`. Front: `pages/Login/MfaRecoveryFlow.jsx`, `pages/Account/security/MfaAccountRecovery.jsx`. BD: `TokenCuenta`, `FactorMfa`.
- **Pruebas:** `test_mfa_recovery.py`, `MfaRecovery.test.jsx`.
- **Estado:** IMPLEMENTADO.

## M-03 Cuenta personal

### RF-013 — Gestionar los consentimientos
- **Descripción:** El sistema debe permitir consultar el estado de los consentimientos y autorizar o revocar el almacenamiento de mediciones experimentales propias.
- **Actor / precondiciones:** cuenta individual autenticada.
- **Comportamiento y resultado:** muestra versión vigente, versión aceptada y fecha; agrega una fila al historial solo si cambia el estado; sin autorización vigente no se mide.
- **RN:** RN-002, RN-021.
- **Evidencia:** Back: `services/consent.py`; API `GET /auth/consents`, `PUT /auth/consents/datos-experimentales`. Front: `pages/Account/measurements/ExperimentalConsent.jsx`, `components/PolicyConsent.jsx`. BD: `ConsentimientoUsuario`.
- **Pruebas:** `test_consents.py`, `Measurements.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-014 — Gestionar el aviso de nuevo inicio de sesión
- **Descripción:** El sistema debe permitir activar o desactivar el aviso por correo de nuevo inicio de sesión, desde la cuenta y desde el enlace del correo.
- **Actor / precondiciones:** cuenta autenticada (desde la cuenta); portador del enlace firmado (desde el correo).
- **Comportamiento y resultado:** cambia la preferencia y la audita solo si hubo cambio.
- **RN:** RN-019.
- **Evidencia:** Back: `services/auth.py:1123-1162`; API `PUT /auth/me/notifications/new-login`, `POST /auth/notifications/new-login/unsubscribe`. Front: `pages/Account/security/LoginNoticeSection.jsx` (desde la cuenta). La pantalla del enlace del correo (`/cuenta/notificaciones/desuscribir`) no existe en las rutas del frontend. BD: `Usuario.notificarNuevoInicioSesion`.
- **Pruebas:** `test_security_hardening.py`.
- **Estado:** PARCIAL (desde la cuenta funciona; el enlace del correo no tiene pantalla, ver H-04 en `06`).

### RF-015 — Eliminar la cuenta propia
- **Descripción:** El sistema debe permitir consultar las consecuencias, solicitar la eliminación de la cuenta y confirmarla desde un enlace del correo con reautenticación.
- **Actor / precondiciones:** cuenta individual o institucional sin vínculos institucionales activos ni administración de un grupo activo.
- **Comportamiento y resultado:** anonimiza la cuenta, revoca sus sesiones y conserva las mediciones desidentificadas (RN-023); informa los impedimentos con su motivo.
- **RN:** RN-022, RN-023.
- **Evidencia:** Back: `services/accountDeletion.py`; API `GET /auth/account-deletion/preview`, `POST /auth/account-deletion/request`, `POST /auth/account-deletion/confirm`. Front: `pages/Account/security/AccountDeletionSection.jsx`, `pages/Account/ConfirmDeletionPage.jsx`. BD: `Usuario`, `TokenCuenta`.
- **Pruebas:** `test_account_deletion.py`, `Account.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-016 — Período de gracia y eliminación automática de cuentas institucionales
- **Descripción:** El sistema debe iniciar un período de gracia de 30 días cuando una cuenta institucional queda sin vínculos activos, mostrarlo a la persona y eliminar y anonimizar la cuenta al vencer.
- **Actor / precondiciones:** cuenta institucional activa sin vínculos; servicio `lifecycle` en ejecución.
- **Comportamiento y resultado:** avisa por correo al iniciar y al eliminar; el plazo se cancela al incorporarse a una institución.
- **RN:** RN-024, RN-023.
- **Evidencia:** Back: `services/accountGrace.py`, `accountLifecycle.py`, `jobs/accountLifecycle.py`; compose servicio `lifecycle`. Front: `components/GracePeriodNotice.jsx`. BD: `Usuario.fechaInicioGracia`, `fechaVencimientoGracia`.
- **Pruebas:** `test_account_lifecycle.py`, `lifecycle_concurrency.py`, `Lifecycle.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-017 — Depuración automática de cuentas no verificadas e invitadas sin salida
- **Descripción:** El sistema debe eliminar las cuentas locales no verificadas con plazo vencido y depurar las cuentas invitadas que quedaron sin invitación aceptable ni enlace vigente.
- **Actor / precondiciones:** trabajo programado o disparo desde operaciones sensibles.
- **Comportamiento y resultado:** libera correo y usuario; deja un evento de auditoría sin datos personales.
- **RN:** RN-004, RN-025.
- **Evidencia:** Back: `services/unverifiedAccounts.py`, `pendingAccounts.py`, `jobs/cleanupUnverifiedAccounts.py`, `jobs/accountLifecycle.py`. Front: sin pantalla. BD: `Usuario`.
- **Pruebas:** `test_account_lifecycle.py`.
- **Estado:** IMPLEMENTADO (la limpieza de no verificadas por trabajo independiente no figura como servicio de Compose; se ejecuta además dentro de las operaciones sensibles).

## M-04 Grupos familiares

### RF-018 — Crear y modificar un grupo familiar
- **Descripción:** El sistema debe permitir que una cuenta individual cree un grupo familiar y que su administrador modifique nombre y descripción.
- **Actor / precondiciones:** cuenta individual sin grupo activo.
- **Comportamiento y resultado:** crea el grupo y el vínculo de administrador con todos los permisos de compartición en 0; envía confirmación (reenviable si no se envió).
- **RN:** RN-026, RN-027, RN-030, RN-091.
- **Evidencia:** Back: `services/group.py:227-278`; API `POST /groups`, `PATCH /groups/{id}`, `POST /groups/{id}/creation-notice`, `GET /groups/mine`, `GET /groups/{id}`. Front: `pages/Account/groups/GroupsHome.jsx`, `GroupSettings.jsx`, `GroupOverview.jsx` (el reenvío de la confirmación no tiene pantalla). BD: `Grupo`, `GrupoUsuario`.
- **Pruebas:** `test_groups.py`, `Groups.test.jsx`.
- **Estado:** IMPLEMENTADO (el reenvío de la confirmación solo está en el backend).

### RF-019 — Invitar a un grupo y responder invitaciones
- **Descripción:** El sistema debe permitir al administrador buscar e invitar cuentas individuales por correo y cancelar invitaciones, y permitir a la persona invitada aceptar o rechazar.
- **Actor / precondiciones:** administrador del grupo; persona con cuenta individual activa sin otro grupo.
- **Comportamiento y resultado:** la invitación vence a los 7 días y no incorpora hasta aceptarse; al aceptar se dan de baja otras invitaciones pendientes; avisa a ambas partes.
- **RN:** RN-026, RN-028.
- **Evidencia:** Back: `services/group.py:324-481`; API `POST /groups/{id}/invitations/lookup`, `POST /groups/{id}/invitations`, `GET /groups/{id}/invitations`, `DELETE /groups/{id}/invitations/{idGU}`, `GET /groups/invitations`, `POST /groups/invitations/{idGU}/accept|reject`. Front: `groups/GroupInvitations.jsx` (invitar y cancelar), `GroupsHome.jsx` (responder invitaciones recibidas). BD: `GrupoUsuario`.
- **Pruebas:** `test_groups.py`, `Groups.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-020 — Gestionar integrantes, abandonar el grupo y transferir la administración
- **Descripción:** El sistema debe permitir listar integrantes, desvincular a un integrante, abandonar el grupo y designar a otro administrador.
- **Actor / precondiciones:** integrante activo (listar, abandonar); administrador (desvincular, transferir).
- **Comportamiento y resultado:** el administrador no abandona con otros integrantes sin transferir; la transferencia es atómica; al terminar un vínculo se revoca lo compartido y se avisa por correo.
- **RN:** RN-027, RN-029.
- **Evidencia:** Back: `services/group.py:284-302,487-552`; API `GET /groups/{id}/members`, `DELETE /groups/{id}/members/{idGU}`, `POST /groups/{id}/leave`, `POST /groups/{id}/transfer`. Front: `groups/GroupOverview.jsx` (listar y desvincular), `GroupSettings.jsx` (abandonar y transferir la administración). BD: `GrupoUsuario`.
- **Pruebas:** `test_groups.py`, `Groups.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-021 — Eliminar un grupo
- **Descripción:** El sistema debe permitir al administrador eliminar el grupo confirmando su nombre exacto.
- **Actor / precondiciones:** administrador del grupo.
- **Comportamiento y resultado:** cierra el grupo, da de baja los vínculos y revoca lo compartido sin tocar cuentas, perfiles ni mediciones; avisa a los integrantes y confirma al administrador.
- **RN:** RN-029.
- **Evidencia:** Back: `services/group.py:555-586`; API `POST /groups/{id}/deletion`. Front: `groups/GroupSettings.jsx`. BD: `Grupo.estado`.
- **Pruebas:** `test_groups.py`.
- **Estado:** IMPLEMENTADO.

### RF-022 — Configurar qué comparto con el grupo
- **Descripción:** El sistema debe permitir a cada integrante consultar y modificar sus cuatro permisos de compartición.
- **Actor / precondiciones:** integrante activo; la identidad sale de la sesión.
- **Comportamiento y resultado:** registra cada cambio como consentimiento auditado; revocar rige en la consulta siguiente.
- **RN:** RN-030, RN-031.
- **Evidencia:** Back: `services/group.py:602-624`; API `GET|PUT /groups/{id}/sharing/me`. Front: `groups/MyPrivacy.jsx`. BD: `GrupoUsuario` (columnas de permisos).
- **Pruebas:** `test_groups.py`, `test_group_shared_measurements.py`, `Groups.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-023 — Consultar los datos que otros integrantes comparten
- **Descripción:** El sistema debe permitir consultar, según el permiso vigente de cada integrante, su perfil, última medición, historial, avisos de medición, estadísticas y el detalle ampliado de una medición.
- **Actor / precondiciones:** integrante activo; el dueño autorizó el permiso correspondiente.
- **Comportamiento y resultado:** verifica la autorización en cada consulta, audita accesos y rechazos, e informa los datos DEMO aparte.
- **RN:** RN-030, RN-031, RN-032, RN-061.
- **Evidencia:** Back: `services/group.py:630-793`; API `GET /groups/{id}/shared`, `.../shared/{idGU}/profile|latest|history|notices|statistics`, `.../measurements/{idMedicion}`. Front: `groups/SharedData.jsx`, `SharedMeasurementDetail.jsx`, `MemberHero.jsx`, `GroupEvolution.jsx`. BD: `GrupoUsuario`, `Medicion`, `PerfilMedicion`.
- **Pruebas:** `test_group_shared_measurements.py`, `test_group_measurement_notice.py`, `Groups.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-024 — Panel del grupo familiar
- **Descripción:** El sistema debe permitir consultar un panel con los indicadores de lo que cada integrante autorizó compartir.
- **Actor / precondiciones:** integrante activo.
- **Comportamiento y resultado:** calcula indicadores sobre las mediciones completadas no DEMO, evaluando los permisos en cada consulta.
- **RN:** RN-031, RN-061.
- **Evidencia:** Back: `services/dashboard.py`; API `GET /groups/{id}/dashboard`. Front: `groups/GroupDashboard.jsx`, `components/dashboard.jsx`. BD: `Medicion`.
- **Pruebas:** `test_dashboards.py`, `Dashboards.test.jsx`.
- **Estado:** IMPLEMENTADO.

## M-05 Instituciones

### RF-025 — Verificar el CUIT y crear una institución
- **Descripción:** El sistema debe permitir a una cuenta institucional consultar el estado de un CUIT (disponible, activo o cerrado) y crear una institución, quedando como propietario.
- **Actor / precondiciones:** cuenta institucional activa; CUIT válido (dígito verificador).
- **Comportamiento y resultado:** crea la institución y el vínculo de propietario en una transacción, cancela el período de gracia y envía una confirmación (reenviable); revela los datos de una institución cerrada solo a quien puede reabrirla; limita las consultas de CUIT.
- **RN:** RN-035, RN-024, RN-091.
- **Evidencia:** Back: `services/institution.py:361-446`; API `POST /institutions/legal-id/status`, `POST /institutions`, `POST /institutions/{id}/creation-notice`. Front: `institutions/CreateInstitutionForm.jsx`, `InstitutionsPage.jsx`. BD: `Institucion` (`UQ_Institucion_identificadorLegal`).
- **Pruebas:** `test_institutions.py`, `Institutions.test.jsx`.
- **Estado:** IMPLEMENTADO (el reenvío de la confirmación solo está en el backend).

### RF-026 — Reabrir una institución cerrada
- **Descripción:** El sistema debe permitir al último propietario reabrir su institución cerrada con nuevos datos administrativos y reautenticación.
- **Actor / precondiciones:** último propietario; cierre no administrativo.
- **Comportamiento y resultado:** conserva identificador, CUIT y auditoría; incrementa las reaperturas; crea un vínculo de propietario nuevo.
- **RN:** RN-035, RN-041, RN-054.
- **Evidencia:** Back: `services/institution.py:449-519`; API `POST /institutions/reopen`. Front: `institutions/CreateInstitutionForm.jsx` (flujo de CUIT cerrado). BD: `Institucion.cantidadReaperturas`, `fechaUltimaReapertura`.
- **Pruebas:** `test_institution_reopen.py`, `test_reopen_period_views.py`.
- **Estado:** IMPLEMENTADO.

### RF-027 — Consultar y modificar los datos de la institución
- **Descripción:** El sistema debe permitir consultar el detalle de una institución según el rol y que el propietario modifique nombre, tipo y descripción.
- **Actor / precondiciones:** integrante activo (consultar); propietario (modificar). El CUIT no se modifica.
- **Comportamiento y resultado:** audita datos previos y nuevos; el operador no recibe estadísticas generales.
- **RN:** RN-033, RN-034.
- **Evidencia:** Back: `services/institution.py:614-665`; API `GET|PATCH /institutions/{id}`. Front: `institutions/InstitutionDataPage.jsx`, `InstitutionOverview.jsx`. BD: `Institucion`.
- **Pruebas:** `test_institutions.py`, `Institutions.test.jsx`, `Administration.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-028 — Consultar mis instituciones y responder invitaciones
- **Descripción:** El sistema debe permitir listar las instituciones de la cuenta con su rol y permisos, y aceptar o rechazar invitaciones recibidas.
- **Actor / precondiciones:** cuenta institucional activa.
- **Comportamiento y resultado:** aceptar consume un cupo (verificado con bloqueo), cancela el período de gracia y avisa a quien invitó, a la persona y a los propietarios; las invitaciones vencidas o de instituciones no activas solo informan.
- **RN:** RN-036, RN-037, RN-024.
- **Evidencia:** Back: `services/institution.py:535-563,1021-1162`; API `GET /institutions/mine`, `GET /institutions/invitations`, `POST /institutions/invitations/{id}/accept|reject`. Front: `institutions/InstitutionsPage.jsx`, `InvitationsSection.jsx`. BD: `InstitucionUsuario`.
- **Pruebas:** `test_institution_staff.py`, `test_quota.py`, `Institutions.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-029 — Incorporar y desvincular moderadores y operadores
- **Descripción:** El sistema debe permitir buscar un correo, invitar a un moderador (propietario) o a un operador (moderador), reenviar invitaciones, cancelarlas y revocar vínculos.
- **Actor / precondiciones:** propietario o moderador según el rol de destino.
- **Comportamiento y resultado:** clasifica el correo (cuenta nueva, existente, individual, ya vinculada); crea cuentas pendientes con enlace de activación; revoca con las restricciones de RN-038 y RN-050.
- **RN:** RN-025, RN-036, RN-038, RN-042, RN-050.
- **Evidencia:** Back: `services/institution.py:723-974,1186-1290`; API `GET|POST /institutions/{id}/moderators`, `POST .../moderators/lookup`, `PATCH|DELETE .../moderators/{idIU}`, `POST .../moderators/{idIU}/resend`, y las equivalentes de `operators`. Front: `institutions/PersonnelForms.jsx`, `PersonnelPage.jsx`, `PersonnelInvitationsPage.jsx`. BD: `InstitucionUsuario`, `Usuario`, `TokenCuenta`.
- **Pruebas:** `test_institution_staff.py`, `test_personnel_incorporation.py`, `Personnel.test.jsx`, `InstitutionStaff.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-030 — Editar los datos administrativos del personal
- **Descripción:** El sistema debe permitir editar matrícula, legajo, función profesional y nombre y apellido profesionales de un vínculo vigente.
- **Actor / precondiciones:** propietario (moderadores y operadores) o moderador (operadores).
- **Comportamiento y resultado:** no cambia el rol ni los datos de la cuenta; audita los nombres de campos.
- **RN:** RN-044.
- **Evidencia:** Back: `services/institution.py:977-1002`; API `PATCH .../moderators/{idIU}`, `PATCH .../operators/{idIU}`. Front: `institutions/PersonnelForms.jsx`, `PersonnelProfilePage.jsx`. BD: `InstitucionUsuario`.
- **Pruebas:** `test_personnel.py`, `Personnel.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-031 — Consultar el personal, su perfil e historial
- **Descripción:** El sistema debe permitir consultar un listado unificado del personal con indicadores, el perfil de cada persona con sus períodos, las invitaciones enviadas y el equipo activo.
- **Actor / precondiciones:** propietario o moderador.
- **Comportamiento y resultado:** agrupa por persona, muestra solo a quien se incorporó o tiene invitación vigente y oculta el correo cuando la cuenta fue eliminada.
- **RN:** RN-043.
- **Evidencia:** Back: `services/personnel.py`; API `GET /institutions/{id}/personnel`, `GET .../personnel/{idIU}`, `GET .../invitations`, `GET .../members`. Front: `institutions/PersonnelPage.jsx`, `PersonnelProfilePage.jsx`. BD: `InstitucionUsuario`.
- **Pruebas:** `test_personnel.py`, `Personnel.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-032 — Eliminar los datos históricos de una persona del personal
- **Descripción:** El sistema debe permitir suprimir de forma irreversible los datos personales históricos de una persona ya desvinculada.
- **Actor / precondiciones:** quien tiene permiso para desvincular ese rol.
- **Comportamiento y resultado:** suprime nombre, apellido, legajo y matrícula de todos sus períodos en esa institución, conservando el vínculo y la autoría.
- **RN:** RN-096.
- **Evidencia:** Back: `services/personnel.py:328-360`; API `DELETE /institutions/{id}/personnel/{idIU}/personal-data`. Front: `institutions/PersonnelProfilePage.jsx`. BD: `InstitucionUsuario`.
- **Pruebas:** `test_account_lifecycle.py`, `Personnel.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-033 — Consultar los cupos de cuentas de la institución
- **Descripción:** El sistema debe permitir consultar la capacidad, las cuentas activas, los cupos disponibles y el porcentaje de utilización.
- **Actor / precondiciones:** propietario o moderador.
- **Comportamiento y resultado:** informa estados disponible, próximo al límite (80 % o más), completa o excedida.
- **RN:** RN-037.
- **Evidencia:** Back: `services/quota.py`; API `GET /institutions/{id}/quota`. Front: `institutions/QuotaSection.jsx`. BD: `Institucion.capacidadMaximaUsuarios`.
- **Pruebas:** `test_quota.py`, `Quota.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-034 — Eliminar la institución
- **Descripción:** El sistema debe permitir al propietario cerrar la institución de forma lógica, confirmando el nombre y reautenticándose.
- **Actor / precondiciones:** propietario con credencial local o MFA habilitado.
- **Comportamiento y resultado:** ver RN-039; avisa a los integrantes y a las cuentas que inician período de gracia.
- **RN:** RN-039, RN-024.
- **Evidencia:** Back: `services/institution.py:1329-1426`; API `POST /institutions/{id}/deletion`. Front: `institutions/DeleteInstitution.jsx`. BD: `Institucion.estado`.
- **Pruebas:** `test_institutions.py`, `test_institution_reopen.py`, `Administration.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-035 — Consultar la actividad reciente de la institución
- **Descripción:** El sistema debe permitir consultar la actividad reciente de la institución, filtrada por lo que el rol puede ver.
- **Actor / precondiciones:** integrante activo (el operador ve solo lo que él hizo).
- **Comportamiento y resultado:** presenta eventos legibles tomados de la auditoría, con pacientes por seudónimo.
- **RN:** RN-086.
- **Evidencia:** Back: `services/institutionActivity.py`; API `GET /institutions/{id}/activity`. Front: `institutions/InstitutionActivityPage.jsx`, `InstitutionActivity.jsx`. BD: `Auditoria`.
- **Pruebas:** `test_institution_activity.py`.
- **Estado:** IMPLEMENTADO.

### RF-036 — Consultar al soporte desde una institución pausada
- **Descripción:** El sistema debe permitir al propietario de una institución pausada enviar una consulta al soporte.
- **Actor / precondiciones:** propietario; institución en estado `INACTIVA`.
- **Comportamiento y resultado:** envía el correo por el servicio de contacto, audita sin el texto y limita a 3 consultas por hora.
- **RN:** RN-040.
- **Evidencia:** Back: `services/institutionSupport.py`; API `POST /institutions/{id}/support-request`. Front: `institutions/PausedSupport.jsx`. BD: `Auditoria`.
- **Pruebas:** `test_platform_institution_control.py`.
- **Estado:** IMPLEMENTADO.

## M-06 Pacientes institucionales

### RF-037 — Registrar un paciente
- **Descripción:** El sistema debe permitir registrar un paciente institucional con nombre, apellido, documento, fecha de nacimiento o edad declarada y sexo del modelo.
- **Actor / precondiciones:** operador (el paciente queda a su cargo), moderador o propietario (designan un operador activo responsable).
- **Comportamiento y resultado:** valida el documento único por institución y la edad; genera el identificador seudónimo; audita quién registró y quién es responsable; envía avisos al operador responsable.
- **RN:** RN-045, RN-046, RN-047.
- **Evidencia:** Back: `services/institutionPatients.py:318-366`; API `POST /institutions/{id}/patients`, `GET .../patients/assignable-operators`. Front: `institutions/patients/PatientCreatePage.jsx`, `PatientFields.jsx`. BD: `PerfilMedicion` (`UX_PerfilMedicion_dniInstitucion`).
- **Pruebas:** `test_institution_patients.py`, `test_patient_assignment.py`, `Patients.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-038 — Consultar y modificar pacientes
- **Descripción:** El sistema debe permitir listar pacientes con búsqueda, filtros y paginación, consultar el detalle de un paciente y modificar sus datos.
- **Actor / precondiciones:** integrante con permiso de consulta; modificar exige gestionar pacientes (el operador solo los suyos).
- **Comportamiento y resultado:** devuelve solo información administrativa a quien no es el responsable; audita la consulta de un paciente; máximo 50 por página; no permite modificar a un paciente dado de baja.
- **RN:** RN-046, RN-047.
- **Evidencia:** Back: `services/institutionPatients.py:251-299,376-399`; API `GET /institutions/{id}/patients`, `GET|PATCH .../patients/{idPerfil}`. Front: `institutions/patients/PatientsPage.jsx`, `PatientDetailPage.jsx`. BD: `PerfilMedicion`.
- **Pruebas:** `test_institution_patients.py`, `test_patient_access.py`, `Patients.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-039 — Asignar el responsable de un paciente
- **Descripción:** El sistema debe permitir a propietario y moderador asignar o proponer un nuevo operador responsable.
- **Actor / precondiciones:** propietario o moderador; operador destino activo de la misma institución.
- **Comportamiento y resultado:** con responsable activo crea una propuesta de transferencia; sin responsable activo asigna directamente y deja transferencia aceptada y auditoría.
- **RN:** RN-048, RN-049.
- **Evidencia:** Back: `services/institutionPatients.py:402-496`; API `PUT /institutions/{id}/patients/{idPerfil}/responsible`. Front: `institutions/patients/PatientDetailPage.jsx`. BD: `TransferenciaPerfil`, `PerfilMedicion`.
- **Pruebas:** `test_patient_assignment.py`, `test_manager_reassignment.py`.
- **Estado:** IMPLEMENTADO.

### RF-040 — Transferir pacientes entre operadores
- **Descripción:** El sistema debe permitir a un operador solicitar la transferencia de un paciente a otro operador, y al destinatario aceptarla o rechazarla, y al solicitante cancelarla; y listar y consultar transferencias.
- **Actor / precondiciones:** operador responsable (solicita), operador destino (responde); propietario y moderador ven el historial.
- **Comportamiento y resultado:** una solicitud pendiente por paciente; aceptar cambia el responsable de forma atómica; la solicitud obsoleta se cancela; avisa a la otra parte.
- **RN:** RN-048.
- **Evidencia:** Back: `services/profileTransfers.py`; API `POST /institutions/{id}/patients/{idPerfil}/transfers`, `GET /institutions/{id}/transfers`, `GET .../transfers/{idTransf}`, `POST .../accept|reject|cancel`. Front: `institutions/patients/TransferPatient.jsx`, `transfers/TransfersPage.jsx`, `TransferDetailPage.jsx`. BD: `TransferenciaPerfil`.
- **Pruebas:** `test_profile_transfers.py`, `test_transfer_detail.py`, `Transfers.test.jsx`, `TransferDetail.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-041 — Desvincular a un operador reasignando sus pacientes
- **Descripción:** El sistema debe permitir consultar el plan de baja de un operador y desvincularlo reasignando todos sus pacientes en una sola operación.
- **Actor / precondiciones:** propietario o moderador; el operador tiene pacientes activos.
- **Comportamiento y resultado:** o se reasigna todo y se desvincula, o no cambia nada; rechaza pacientes con transferencia pendiente o la ausencia de operadores disponibles.
- **RN:** RN-038, RN-050.
- **Evidencia:** Back: `services/operatorOffboarding.py`, `institution.py:1203-1290`; API `GET .../operators/{idIU}/offboarding`, `POST .../operators/{idIU}/offboard`, `DELETE .../operators/{idIU}`. Front: `institutions/OffboardOperator.jsx`. BD: `PerfilMedicion`, `InstitucionUsuario`.
- **Pruebas:** `test_operator_offboarding.py`, `Lifecycle.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-042 — Gestionar las reasignaciones pendientes
- **Descripción:** El sistema debe permitir consultar los pacientes pendientes de reasignación de operadores ya desvinculados, reasignarlos en lote a un operador activo y regularizar a un operador desvinculado que figura como responsable.
- **Actor / precondiciones:** propietario o moderador.
- **Comportamiento y resultado:** el lote es una sola transacción; una tarea ya resuelta se informa como ya resuelta; la regularización crea una tarea pendiente por paciente.
- **RN:** RN-050.
- **Evidencia:** Back: `services/institutionReassignments.py`, `reassignments.py`; API `GET .../reassignments`, `GET .../reassignments/items`, `POST .../reassignments/assign`, `POST .../reassignments/regularize`. Front: `institutions/reassignments/ReassignmentsPage.jsx`, `PendingReassignmentsSection.jsx`. BD: `ReasignacionPaciente`.
- **Pruebas:** `test_manager_reassignment.py`, `Lifecycle.test.jsx`.
- **Estado:** IMPLEMENTADO (el aviso por correo a los moderadores descrito en `reassignments.py` no se invoca; ver H-03).

### RF-043 — Dar de baja a un paciente
- **Descripción:** El sistema debe permitir a propietario y moderador dar de baja a un paciente.
- **Actor / precondiciones:** propietario o moderador; sin medición en curso.
- **Comportamiento y resultado:** inicia la conservación de 12 meses, borra el correo de resultados y, con el esquema de retención aplicado, anonimiza al paciente; avisa al operador responsable.
- **RN:** RN-051, RN-095.
- **Evidencia:** Back: `services/institutionPatients.py:499-543`, `measurementRetention.py`; API `POST /institutions/{id}/patients/{idPerfil}/discharge`. Front: `institutions/patients/PatientDetailPage.jsx`. BD: `PerfilMedicion`.
- **Pruebas:** `test_institution_patients.py`, `test_retention_anonymization.py`.
- **Estado:** IMPLEMENTADO.

### RF-044 — Gestionar el correo de resultados del paciente
- **Descripción:** El sistema debe permitir al operador responsable cargar, cambiar y quitar el correo del paciente para el envío de resultados, y al paciente confirmar su dirección desde un enlace.
- **Actor / precondiciones:** operador responsable que declara la autorización del paciente; paciente con el enlace firmado (72 horas).
- **Comportamiento y resultado:** guarda el correo recién tras la confirmación del paciente, por 12 meses; muestra el correo enmascarado; limita los pedidos de confirmación.
- **RN:** RN-052.
- **Evidencia:** Back: `services/patientResultEmail.py`, `resultEmailConfirmation.py`, `resultEmailStore.py`; API `PUT|DELETE .../patients/{idPerfil}/result-email`, `POST /institutions/result-email/confirm`. Front: `institutions/patients/PatientResultEmail.jsx`, `pages/ResultEmail/ConfirmResultEmailPage.jsx`. BD: `PerfilMedicion.correoResultados`, `fechaAutorizacionCorreo`, `fechaExpiracionCorreo`.
- **Pruebas:** `test_patient_result_email.py`, `test_patient_mails.py`, `ConfirmResultEmailPage.test.jsx`.
- **Estado:** IMPLEMENTADO (requiere el esquema de correo de resultados; probar el envío SMTP real figura como pendiente en `docs/PENDIENTES.md`).

## M-07 Mediciones

### RF-045 — Consultar el perfil de medición propio
- **Descripción:** El sistema debe permitir a una cuenta individual consultar su perfil de medición, creado automáticamente desde los datos de la cuenta, y ver qué datos recomendados faltan.
- **Actor / precondiciones:** cuenta individual.
- **Comportamiento y resultado:** calcula la edad desde la fecha de nacimiento; fecha de nacimiento y sexo son recomendados, no obligatorios.
- **RN:** RN-020, RN-058.
- **Evidencia:** Back: `services/measurement.py:197-209`, `measurementProfile.py`; API `GET /measurements/profile`. Front: `measurements/OwnMeasurementScreens.jsx` (`/app/mediciones/perfil`), `useOwnMeasurementProfile.js`, `RecommendedNotice.jsx`. BD: `PerfilMedicion` (`UX_PerfilMedicion_consumidor`).
- **Pruebas:** `test_measurement_profile.py`, `test_measurement_optional_data.py`.
- **Estado:** IMPLEMENTADO.

### RF-046 — Iniciar una medición para un perfil y un dispositivo
- **Descripción:** El sistema debe permitir iniciar una medición de oximetría o de glucosa experimental para el perfil propio o un paciente a cargo, eligiendo el dispositivo operativo, la condición de alimentación y datos opcionales, y consultar los dispositivos utilizables y la matriz que se aplicaría.
- **Actor / precondiciones:** cuenta individual (con consentimiento vigente) u operador responsable; dispositivo operativo utilizable.
- **Comportamiento y resultado:** crea la medición pendiente con los datos históricos del momento y deja la autoría auditada; para glucosa por matriz resuelve matriz y regla o rechaza.
- **RN:** RN-055, RN-056, RN-057, RN-058, RN-064, RN-021.
- **Evidencia:** Back: `services/measurement.py:223-340`; API `POST /measurements`, `GET /measurements/devices`, `GET /measurements/matrix`. Front: `measurementsApi.getMatrixPreview` y `listDevices` se usan en `measurements/DeviceMonitor.jsx`; la función `startMeasurement` del módulo de acceso no se usa en ninguna pantalla. BD: `Medicion`.
- **Pruebas:** `test_measurements.py`, `test_glucose_mode.py`, `test_optional_meal.py`.
- **Estado:** PARCIAL (backend completo; la interfaz inicia las mediciones por la sesión del dispositivo, RF-048, y no por este endpoint).

### RF-047 — Adquirir muestras crudas, finalizar y cancelar una medición
- **Descripción:** El sistema debe permitir registrar muestras del sensor (canales rojo e infrarrojo) de una medición, finalizarla para que el servidor calcule SpO₂ y frecuencia cardíaca, o cancelarla.
- **Actor / precondiciones:** quien opera la medición; medición pendiente o en adquisición; dispositivo operativo.
- **Comportamiento y resultado:** la primera muestra pasa a adquiriendo; finalizar procesa la señal y deja completada o inválida con el motivo; los valores del cliente se ignoran.
- **RN:** RN-055, RN-059, RN-060.
- **Evidencia:** Back: `services/measurement.py:360-558`, `backend/app/acquisition/oximetry.py`; API `POST /measurements/{id}/samples|finish|cancel`. Front: `acquisition/LiveAcquisition.jsx` y `measurements/MeasurementPanel.jsx` (finalizar y cancelar); no hay pantalla que cree la medición por este camino. BD: `Medicion`, `MuestraSensor`.
- **Pruebas:** `test_measurements.py`, `test_measurement_lifecycle.py`, `test_oximetry.py`, `Measurements.test.jsx`.
- **Estado:** PARCIAL (backend completo; el endpoint de muestras no se usa desde la interfaz; sin hardware real).

### RF-048 — Medir con el dispositivo (sesión de telemetría)
- **Descripción:** El sistema debe permitir abrir una sesión de medición con el dispositivo conectado, ver las lecturas en vivo y guardar o cancelar la medición.
- **Actor / precondiciones:** cuenta individual con consentimiento, o operador con paciente a cargo; el puente activo atiende un dispositivo operativo utilizable y la cuenta tiene el control del equipo.
- **Comportamiento y resultado:** crea la medición y reserva el dispositivo; solo se atribuyen las lecturas posteriores al inicio; guardar toma una lectura estabilizada (mediana) y completa la medición con origen y versión de algoritmo; cancelar libera el equipo.
- **RN:** RN-055, RN-056, RN-057, RN-059, RN-060, RN-061, RN-067, RN-072.
- **Evidencia:** Back: `services/telemetry.py:480-660`; API `POST /acquisition/telemetry/session`, `POST .../session/save`, `POST .../session/cancel`. Front: `measurements/DeviceMonitor.jsx`, `DeviceSession.jsx`, `DeviceReadout.jsx`, `DeviceStatusChecks.jsx`, `OwnMeasurementScreens.jsx` (`/app/mediciones/nueva`), `institutions/patients/PatientMeasurePage.jsx`. BD: `Medicion`.
- **Pruebas:** `test_telemetry.py`, `test_glucose_mode.py`, `test_ppg.py`, `DeviceMeasurement.test.jsx`, `PatientMeasure.test.jsx`.
- **Estado:** IMPLEMENTADO (verificado con pruebas automatizadas; sin hardware real según `docs/PENDIENTES.md`).

### RF-049 — Consultar el historial de mediciones
- **Descripción:** El sistema debe permitir consultar el historial propio o el de un paciente a cargo, con filtros por fechas, modo, estado y origen, orden y paginación.
- **Actor / precondiciones:** cuenta individual (propio) u operador responsable (paciente).
- **Comportamiento y resultado:** oculta las canceladas e inválidas vencidas en la vista personal; el historial de un paciente solo lo ve su operador responsable.
- **RN:** RN-046, RN-062, RN-066.
- **Evidencia:** Back: `services/measurement.py:644-718`; API `GET /measurements`, `GET /institutions/{id}/patients/{idPerfil}/measurements`. Front: `measurements/MeasurementHistory.jsx`, `institutions/patients/PatientDetailPage.jsx`, `PatientMeasurementCard.jsx`. BD: `Medicion`.
- **Pruebas:** `test_measurements.py`, `test_patient_access.py`, `test_measurement_lifecycle.py`, `Measurements.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-050 — Consultar el detalle de una medición
- **Descripción:** El sistema debe permitir consultar el detalle y el estado de una medición, con su dispositivo, matriz, referencia capilar y la referencia de glucosa.
- **Actor / precondiciones:** quien tiene acceso a la medición.
- **Comportamiento y resultado:** informa el origen visible (experimental, sin calibrar, DEMO), si puede operarse o eliminarse y hasta cuándo es visible; una medición oculta no se recupera.
- **RN:** RN-060, RN-062, RN-064.
- **Evidencia:** Back: `services/measurement.py:593-641`, `glucoseReference.py`; API `GET /measurements/{id}`. Front: `measurements/MeasurementPanel.jsx`, `GlucoseReferencePanel.jsx`, `institutions/patients/PatientMeasurementCard.jsx`. BD: `Medicion`, `MedicionReferenciaCapilar`.
- **Pruebas:** `test_measurements.py`, `test_glucose_mode.py`, `Measurements.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-051 — Registrar una referencia capilar
- **Descripción:** El sistema debe permitir registrar a mano el valor de un glucómetro capilar asociado a una medición de glucosa completada.
- **Actor / precondiciones:** quien opera la medición.
- **Comportamiento y resultado:** una referencia por medición, sin reemplazar la estimación; auditado.
- **RN:** RN-063.
- **Evidencia:** Back: `services/measurement.py:564-587`; API `POST /measurements/{id}/capillary-reference`. Front: `measurements/MeasurementPanel.jsx`. BD: `MedicionReferenciaCapilar`.
- **Pruebas:** `test_glucose_mode.py`.
- **Estado:** IMPLEMENTADO.

### RF-052 — Consultar estadísticas y evolución
- **Descripción:** El sistema debe permitir consultar estadísticas del período (promedios, mínimos, máximos, serie diaria) y la evolución histórica de las mediciones propias o de un paciente a cargo.
- **Actor / precondiciones:** cuenta individual u operador responsable.
- **Comportamiento y resultado:** solo mediciones completadas; DEMO aparte; períodos válidos de 24 horas a 90 días o rango; hasta 1000 puntos.
- **RN:** RN-061, RN-066.
- **Evidencia:** Back: `services/measurement.py:781-960`; API `GET /measurements/statistics`, `GET /measurements/evolution`, `GET /institutions/{id}/patients/{idPerfil}/measurements/statistics|evolution`. Front: `measurements/EvolutionPanel.jsx`, `PersonalDashboard.jsx`, `institutions/patients/PatientDetailPage.jsx` (evolución); la ruta de estadísticas por paciente (`getPatientStatistics`) no se usa en ninguna pantalla. BD: `Medicion`.
- **Pruebas:** `test_evolution.py`, `test_patient_evolution.py`, `test_health_aggregates.py`, `Measurements.test.jsx`.
- **Estado:** IMPLEMENTADO (el endpoint de estadísticas por paciente existe sin pantalla).

### RF-053 — Eliminar mediciones de prueba (DEMO)
- **Descripción:** El sistema debe permitir eliminar una medición DEMO completada o todas las propias, sin tocar las mediciones reales.
- **Actor / precondiciones:** quien opera la medición.
- **Comportamiento y resultado:** borra la medición y sus datos derivados; una medición real responde conflicto; queda auditado.
- **RN:** RN-061.
- **Evidencia:** Back: `services/measurement.py:724-764`; API `DELETE /measurements/{id}`, `DELETE /measurements/demo`. Front: `measurements/MeasurementPanel.jsx`, `OwnMeasurementScreens.jsx`. BD: `Medicion`, `MuestraSensor`, `EnvioResultado`.
- **Pruebas:** `test_telemetry.py`, `test_glucose_mode.py`, `Measurements.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-054 — Enviar el resultado de una medición por correo
- **Descripción:** El sistema debe permitir enviar por correo el resultado de una medición completada: a la propia cuenta o, un operador, al paciente (con confirmación), y enviar automáticamente al guardar una medición de un paciente con correo vigente.
- **Actor / precondiciones:** quien opera la medición; medición completada; no DEMO para cuentas individuales.
- **Comportamiento y resultado:** limita a 3 envíos por hora por medición; registra el envío sin guardar el correo.
- **RN:** RN-052, RN-061, RN-065.
- **Evidencia:** Back: `services/measurement.py:996-1103`; API `POST /measurements/{id}/send-result`. Front: `measurements/MeasurementPanel.jsx`. BD: `EnvioResultado`.
- **Pruebas:** `test_result_email.py`, `test_result_email_on_save.py`, `test_patient_result_email.py`.
- **Estado:** IMPLEMENTADO.

### RF-055 — Estimar la glucosa en el servidor
- **Descripción:** El sistema debería estimar la glucosa en el servidor a partir de las muestras del sensor y la regla de la matriz aplicable.
- **Actor / precondiciones:** medición de glucosa experimental por muestras con regla aplicable.
- **Comportamiento y resultado:** hoy no existe un algoritmo: la medición termina inválida con el motivo «el algoritmo de estimación todavía no está disponible».
- **RN:** RN-060.
- **Evidencia:** Back: `services/measurement.py:121-125,482-485`; `glucoseEstimator = None`. Front: textos explicativos en `measurements/GlucoseReferencePanel.jsx`. BD: columnas `glucosaEstimada`, `idMatriz`, `versionAlgoritmo` y su restricción de trazabilidad.
- **Pruebas:** `test_measurements.py` y `test_glucose_mode.py` simulan el estimador por *monkeypatch*; no hay un estimador real que probar.
- **Estado:** PREVISTO (punto de integración; figura en `docs/PENDIENTES.md`).

## M-08 Dispositivos

### RF-056 — Administrar el inventario global de dispositivos
- **Descripción:** El sistema debe permitir a la administración de la plataforma listar, consultar, registrar, editar, cambiar de estado, asignar a una institución, cambiar el responsable, desvincular y descomisionar dispositivos.
- **Actor / precondiciones:** administrador (todas las acciones) o moderador del sistema (consultar, alta, edición técnica y estado), con MFA habilitado.
- **Comportamiento y resultado:** código único; nunca se borra; asignar o desvincular con mediciones en curso se rechaza; cada cambio se audita.
- **RN:** RN-068, RN-069, RN-070.
- **Evidencia:** Back: `services/device.py`; API `GET|POST /devices`, `GET /devices/summary`, `GET /devices/institutions`, `GET /devices/institutions/{id}/responsibles`, `GET|PATCH /devices/{id}`, `POST /devices/{id}/state|assign|responsible|unassign|decommission`. Front: `Account/devices/DevicePages.jsx`, `DevicesInventory.jsx`, `DeviceDetail.jsx`, `DeviceForm.jsx` (rutas `/plataforma/dispositivos` y `/app/dispositivos`). BD: `Dispositivo`.
- **Pruebas:** `test_devices.py`, `test_device_context_authority.py`, `Devices.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-057 — Administrar el inventario de una institución
- **Descripción:** El sistema debe permitir a cada institución consultar su inventario y, según el rol, registrar, editar nombre y modelo, cambiar estados, cambiar responsable, desvincular y descomisionar dispositivos.
- **Actor / precondiciones:** propietario (todo), moderador (registrar, editar, estado), operador (consulta mínima).
- **Comportamiento y resultado:** el alta queda asignada a la institución y al propietario vigente; el operador solo ve los dispositivos operativos sin responsable o a su cargo.
- **RN:** RN-068, RN-070.
- **Evidencia:** Back: `services/device.py`; API `GET|POST /institutions/{id}/devices`, `GET /institutions/{id}/devices/summary|responsibles`, `GET|PATCH .../devices/{idDisp}`, `POST .../devices/{idDisp}/state|responsible|unassign|decommission`. Front: `institutions/InstitutionOverview.jsx`, `devices/DevicePages.jsx` (rutas `/app/instituciones/:id/dispositivos`). BD: `Dispositivo`.
- **Pruebas:** `test_devices.py`, `Devices.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-058 — Conectar, identificar y vincular el Arduino
- **Descripción:** El sistema debe permitir identificar el Arduino conectado por su identificador persistente, registrar un dispositivo nuevo en la institución del operador, vincular uno sin institución con confirmación explícita y confirmar uno existente.
- **Actor / precondiciones:** operador (registro y vinculación institucional) o cuenta individual; puente activo.
- **Comportamiento y resultado:** nunca transfiere un dispositivo de otra institución; si el firmware no informa identificador exige confirmar que es el Arduino conectado; muestra el estado de la comunicación separado del estado administrativo.
- **RN:** RN-069, RN-071.
- **Evidencia:** Back: `services/deviceConnection.py`, `device.py:549-669,832-893`; API `POST /acquisition/telemetry/device/register|link|confirm`, `POST /devices/resolve` (sin consumo desde la interfaz). Front: `acquisition/DeviceIdentification.jsx`, `ConnectDevicePage.jsx`, `connectModel.js`, `acquisition/ConnectDevicePage.jsx` (`InstitutionConnectDevicePage`, ruta `/app/instituciones/:id/conectar-dispositivo`). BD: `Dispositivo`.
- **Pruebas:** `test_device_connection.py`, `test_device_resolve_authority.py`, `DeviceIdentification.test.jsx`, `ConnectDevice.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-059 — Consultar las mediciones realizadas con un dispositivo
- **Descripción:** El sistema debe permitir consultar, con paginación, las mediciones hechas con un dispositivo del inventario.
- **Actor / precondiciones:** quien administra el inventario correspondiente.
- **Comportamiento y resultado:** muestra las mediciones sin exponer datos personales del paciente.
- **RN:** RN-070.
- **Evidencia:** Back: `services/device.py:359-386`; API `GET /devices/{id}/measurements`, `GET /institutions/{id}/devices/{idDisp}/measurements`. Front: `devices/DeviceDetail.jsx`. BD: `Medicion`, `Dispositivo`.
- **Pruebas:** `test_devices.py`.
- **Estado:** IMPLEMENTADO.

## M-09 Adquisición y telemetría

### RF-060 — Consultar el estado del puente y qué falta para poder medir
- **Descripción:** El sistema debe permitir consultar el estado del puente, del puerto y del dispositivo, y un diagnóstico de lo que falta para medir.
- **Actor / precondiciones:** cuenta autenticada habilitada para medir.
- **Comportamiento y resultado:** distingue puente detenido, Bluetooth desconectado, conectado sin datos y conectado; explica problemas de puerto con una acción sugerida; no revela datos de otras cuentas.
- **RN:** RN-068, RN-073.
- **Evidencia:** Back: `services/telemetry.py:229-480`, `acquisition/telemetry.py`; API `GET /acquisition/telemetry/status`, `GET /acquisition/telemetry/readiness`. Front: `acquisition/ConnectionStatusPanel.jsx`, `DeviceReadinessHint.jsx`, `measurements/DeviceStatusChecks.jsx`, `useDeviceReadiness.js`, `useDeviceStatus.js`. BD: no persiste (estado en memoria).
- **Pruebas:** `test_bridge_diagnostics.py`, `test_telemetry.py`, `ConnectDevice.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-061 — Tomar y soltar el control temporal del dispositivo
- **Descripción:** El sistema debe permitir tomar el control temporal exclusivo del equipo («Usar dispositivo») y soltarlo («Dejar de usar»).
- **Actor / precondiciones:** cuenta habilitada para medir con autoridad sobre el dispositivo.
- **Comportamiento y resultado:** una sola cuenta lo controla; el control vence por inactividad; una medición en curso impide soltarlo.
- **RN:** RN-072, RN-073.
- **Evidencia:** Back: `services/telemetry.py:172-210`; API `POST|DELETE /acquisition/telemetry/control`. Front: `acquisition/BridgeSettings.jsx`. BD: no persiste.
- **Pruebas:** `test_device_control.py`, `test_shared_device.py`.
- **Estado:** IMPLEMENTADO.

### RF-062 — Dar órdenes al puente serie
- **Descripción:** El sistema debe permitir pedir al puente configurar puerto o medio, pausar, reanudar, detener o reiniciar.
- **Actor / precondiciones:** quien controla el dispositivo y tiene autoridad sobre el que atiende el puente.
- **Comportamiento y resultado:** valida la lista cerrada de acciones y que haya una sola orden pendiente; audita; el puente la recoge en su siguiente latido.
- **RN:** RN-073.
- **Evidencia:** Back: `services/telemetry.py:213-226`, `acquisition/telemetry.py:361-362,616-636`; API `POST /acquisition/bridge/command`. Front: `acquisition/BridgeSettings.jsx`. BD: no persiste.
- **Pruebas:** `test_bridge_command_authority.py`, `test_bridge_ctl.py`, `test_bridge.py`.
- **Estado:** IMPLEMENTADO.

### RF-063 — Recibir las lecturas del puente y verificar un código de dispositivo
- **Descripción:** El sistema debe recibir de forma idempotente las líneas del firmware enviadas por el puente y permitir comprobar si un código existe y está operativo.
- **Actor / precondiciones:** puente con el token compartido.
- **Comportamiento y resultado:** valida cada línea, descarta las corruptas, da de alta automáticamente un código no inventariado bajo las condiciones de RN-074 y bloquea a la IP con demasiados fallos de token.
- **RN:** RN-059, RN-074.
- **Evidencia:** Back: `services/telemetry.py:70-123`, `acquisition/telemetry.py`; API `POST /acquisition/bridge/ingest`, `POST /acquisition/bridge/check` (límite `bridgeCheck`). Front: sin pantalla (lo consume `acquisition/bridge/glucolume_bridge.py`). BD: `Dispositivo` (alta automática).
- **Pruebas:** `test_bridge.py`, `test_bridge_runtime.py`, `test_telemetry.py`, `test_ppg.py`.
- **Estado:** IMPLEMENTADO.

### RF-064 — Transmitir en vivo el estado y las lecturas
- **Descripción:** El sistema debe transmitir por *Server-Sent Events* el estado y las lecturas del dispositivo a la cuenta que lo controla, y el avance de la adquisición cruda.
- **Actor / precondiciones:** cuenta autenticada; la transmisión libera la conexión de base de datos tras identificar a la cuenta.
- **Comportamiento y resultado:** solo quien controla ve las lecturas; hay límites de transmisiones simultáneas; Nginx entrega los flujos sin búfer.
- **RN:** RN-072.
- **Evidencia:** Back: `api/v1/telemetry.py:157-203`, `api/v1/acquisition.py:75`, `api/streams.py`, `api/deps.py:49-61`; API `GET /acquisition/telemetry/stream`, `GET /acquisition/stream`. Front: `useDeviceStatus.js`, `acquisition/LiveAcquisition.jsx`, `components/LiveChart.jsx`, `PpgChart.jsx`. BD: no persiste.
- **Pruebas:** `test_stream_limits.py`, `test_telemetry.py`, `PpgChart.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-065 — Operar el enlace serie desde el backend (adquisición de muestras crudas)
- **Descripción:** El sistema debe permitir listar puertos, conectar y desconectar un puerto, probar la comunicación, identificar el dispositivo e iniciar, finalizar o cancelar una adquisición de muestras.
- **Actor / precondiciones:** cuenta individual u operador activo; backend ejecutándose en el equipo que tiene el puerto (no en Docker de Windows).
- **Comportamiento y resultado:** el primero que conecta es dueño del enlace; iniciar exige que el Arduino identificado coincida con el dispositivo elegido; las muestras se guardan por lotes de 40 y con tope de 6000.
- **RN:** RN-055, RN-059, RN-068.
- **Evidencia:** Back: `services/acquisition.py`, `acquisition/link.py`, `acquisition/protocol.py`; API `GET /acquisition/ports`, `GET /acquisition/status`, `POST /acquisition/connect|disconnect|probe|identify|start|finish|cancel`. Front: `acquisition/LiveAcquisition.jsx`, `ConnectionGuide.jsx`; `probe` no se usa en pantallas. BD: `MuestraSensor`.
- **Pruebas:** `test_acquisition.py`, `test_acquisition_port_validation.py`, `Acquisition.test.jsx`.
- **Estado:** IMPLEMENTADO (sin hardware real; el enlace desde un contenedor de Windows no es posible).

## M-10 Matrices de referencia

### RF-066 — Crear una matriz con sus reglas
- **Descripción:** El sistema debe permitir crear una matriz global o institucional como borrador, con reglas opcionales, y revisar las reglas antes de guardar.
- **Actor / precondiciones:** moderador o administrador del sistema (global); propietario o moderador de la institución (institucional).
- **Comportamiento y resultado:** rechaza configuraciones inválidas o ambiguas (todo o nada); numera versión y códigos de regla.
- **RN:** RN-075, RN-076, RN-077.
- **Evidencia:** Back: `services/matrix.py:424-498`; API `POST /matrices`, `POST /matrices/check-rules`. Front: `matrices/MatrixPages.jsx`, `CreateInstitutionMatrixForm.jsx`. BD: `Matriz`, `ReglaMatriz`.
- **Pruebas:** `test_matrices.py`, `test_matrices_institucion.py`, `Matrices.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-067 — Editar un borrador y sus reglas
- **Descripción:** El sistema debe permitir modificar los datos de un borrador y agregar, modificar y eliminar sus reglas.
- **Actor / precondiciones:** quien administra la matriz; la matriz está en borrador.
- **Comportamiento y resultado:** rechaza solapamientos y duplicados; una versión no borrador es inmutable.
- **RN:** RN-076, RN-077.
- **Evidencia:** Back: `services/matrix.py:534-635`; API `PATCH /matrices/{id}`, `POST /matrices/{id}/rules`, `PATCH|DELETE /matrices/{id}/rules/{idRegla}`. Front: `matrices/MatrixDetail.jsx`, `MatrixRules.jsx`, `RuleEditor.jsx`. BD: `Matriz`, `ReglaMatriz`.
- **Pruebas:** `test_matrices.py`, `test_matrix_unreported_conditions.py`.
- **Estado:** IMPLEMENTADO.

### RF-068 — Validar, activar, desactivar y archivar una matriz
- **Descripción:** El sistema debe permitir validar una matriz (con advertencias de cobertura), activarla reemplazando a la activa del ámbito, desactivarla y archivarla.
- **Actor / precondiciones:** quien administra la matriz.
- **Comportamiento y resultado:** solo se activa una matriz válida y vigente; las activaciones simultáneas las resuelve el índice único filtrado.
- **RN:** RN-076, RN-077.
- **Evidencia:** Back: `services/matrix.py:367-446,649-710`; API `POST /matrices/{id}/validate|activate|deactivate|archive`. Front: `matrices/MatrixDetail.jsx`, `InstitutionMatrices.jsx`. BD: `UX_Matriz_globalActiva`, `UX_Matriz_institucionActiva`.
- **Pruebas:** `test_matrices.py`, `Matrices.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-069 — Crear una nueva versión de una matriz
- **Descripción:** El sistema debe permitir copiar una versión ya utilizada o archivada como nuevo borrador con sus reglas.
- **Actor / precondiciones:** quien administra la matriz; la matriz no está en borrador.
- **Comportamiento y resultado:** la original no cambia; numera la versión siguiente.
- **RN:** RN-076.
- **Evidencia:** Back: `services/matrix.py:500-528`; API `POST /matrices/{id}/new-version`. Front: `matrices/MatrixDetail.jsx`. BD: `Matriz`.
- **Pruebas:** `test_matrices.py`.
- **Estado:** IMPLEMENTADO.

### RF-070 — Consultar matrices, la matriz efectiva y su auditoría
- **Descripción:** El sistema debe permitir consultar las matrices globales, el resumen institucional, el detalle de una matriz con sus reglas y permisos, la matriz que se aplicaría a una medición y la auditoría de la matriz.
- **Actor / precondiciones:** según ámbito y rol (RN-075 y RN-078).
- **Comportamiento y resultado:** el operador solo consulta cuál se aplica; la auditoría institucional solo la ve el propietario.
- **RN:** RN-064, RN-075, RN-078.
- **Evidencia:** Back: `services/matrix.py:239-285`; API `GET /matrices/global`, `GET /matrices/{id}`, `GET /matrices/{id}/audit`, `GET /institutions/{id}/matrices`, `GET /institutions/{id}/matrices/effective` (sin consumo desde la interfaz), `GET /measurements/matrix`. Front: `matrices/MatrixPages.jsx`, `InstitutionMatrices.jsx`, `MatrixDetail.jsx`. BD: `Matriz`, `Auditoria`.
- **Pruebas:** `test_matrices.py`, `test_matrices_institucion.py`.
- **Estado:** IMPLEMENTADO.

## M-11 Paneles e indicadores

### RF-071 — Panel personal
- **Descripción:** El sistema debe permitir a una cuenta individual consultar un panel con su última medición, mediciones recientes y accesos rápidos, por período.
- **Actor / precondiciones:** cuenta individual.
- **Comportamiento y resultado:** calcula sobre mediciones completadas no DEMO; sin datos informa nulo y no cero.
- **RN:** RN-061, RN-066.
- **Evidencia:** Back: `services/dashboard.py`; API `GET /measurements/dashboard`. Front: `measurements/PersonalDashboard.jsx`, `pages/Account/HomePage.jsx`, `home/*`. BD: `Medicion`.
- **Pruebas:** `test_dashboards.py`, `Dashboards.test.jsx`, `Home.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-072 — Panel institucional de gestión
- **Descripción:** El sistema debe permitir a propietario y moderador consultar un panel general de la institución con filtros, resultados agregados por origen y operadores.
- **Actor / precondiciones:** propietario o moderador.
- **Comportamiento y resultado:** agregados sin identificar pacientes; mínimo de cinco pacientes distintos para informar estadísticas de salud.
- **RN:** RN-053, RN-061.
- **Evidencia:** Back: `services/dashboard.py`; API `GET /institutions/{id}/dashboard`. Front: `institutions/dashboard/ManagementPanel.jsx`, `InstitutionDashboards.jsx`, `OperatorCharts.jsx`. BD: `Medicion`, `PerfilMedicion`.
- **Pruebas:** `test_admin_dashboard.py`, `test_health_aggregates.py`, `test_dashboard_privacy.py`, `test_dashboard_multiple_measurements.py`, `Dashboards.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-073 — Panel por operador
- **Descripción:** El sistema debe permitir consultar el panel de un operador (pacientes asignados y mediciones iniciadas por él).
- **Actor / precondiciones:** propietario o moderador; el propio operador para el suyo.
- **Comportamiento y resultado:** atribuye cada medición a quien la inició y no al responsable actual.
- **RN:** RN-046, RN-057.
- **Evidencia:** Back: `services/dashboard.py`; API `GET /institutions/{id}/operators/{idOperador}/dashboard`. Front: `institutions/OperatorOverview.jsx`, `institutions/dashboard/InstitutionDashboards.jsx` (ruta `personal/operadores/:id`). BD: `Medicion`, `Auditoria`.
- **Pruebas:** `test_operator_panel.py`, `test_operator_scope.py`.
- **Estado:** IMPLEMENTADO.

### RF-074 — Panel por paciente
- **Descripción:** El sistema debe permitir consultar el panel de un paciente con perfil, indicadores, estadísticas, historial con operador y transferencias.
- **Actor / precondiciones:** operador responsable (datos de salud).
- **Comportamiento y resultado:** nombre y apellido solo con autorización.
- **RN:** RN-046.
- **Evidencia:** Back: `services/dashboard.py`; API `GET /institutions/{id}/patients/{idPerfil}/dashboard`. Front: la ruta `pacientes/:id/dashboard` redirige al detalle del paciente; ningún módulo de acceso consume este endpoint. BD: `Medicion`, `PerfilMedicion`.
- **Pruebas:** `test_dashboards.py`.
- **Estado:** PARCIAL (backend completo; sin pantalla).

### RF-075 — Analítica de los pacientes del operador
- **Descripción:** El sistema debe permitir al operador consultar una analítica de sus propios pacientes activos, con filtros y segmentación.
- **Actor / precondiciones:** operador activo; solo sus pacientes.
- **Comportamiento y resultado:** usa todos los campos registrados, muestra «Sin informar» en lugar de ceros, separa DEMO y experimental y limita el volumen leído.
- **RN:** RN-046, RN-061.
- **Evidencia:** Back: `services/patientAnalytics.py`; API `GET /institutions/{id}/analytics/patients`. Front: `institutions/analytics/PatientAnalyticsPage.jsx`, `components/AnalyticsCharts.jsx`. BD: `Medicion`, `PerfilMedicion`.
- **Pruebas:** `test_patient_analytics.py`, `PatientAnalyticsPage.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-076 — Indicadores agregados de la institución (interfaz de programación)
- **Descripción:** El sistema debe exponer conteos y promedios agregados de la institución sin identificar pacientes.
- **Actor / precondiciones:** propietario o moderador.
- **Comportamiento y resultado:** incluye la cohorte anónima y suprime los promedios con menos de cinco pacientes distintos.
- **RN:** RN-053.
- **Evidencia:** Back: `services/measurement.py:966-991`; API `GET /institutions/{id}/indicators`. Front: sin pantalla (el panel institucional usa `/dashboard`).
- **Pruebas:** `test_health_aggregates.py`.
- **Estado:** PARCIAL (backend completo; sin consumo desde la interfaz).

## M-12 Administración de la plataforma

### RF-077 — Acceso administrativo: activación con código y recuperación
- **Descripción:** El sistema debe permitir a las cuentas administrativas activar su cuenta con un código de un solo uso, iniciar sesión, recuperar y restablecer su contraseña, y configurar MFA antes de operar.
- **Actor / precondiciones:** persona invitada como administrador o moderador del sistema.
- **Comportamiento y resultado:** el código viaja en el fragmento de la URL; no activa un segundo administrador; la sesión de activación solo permite configurar MFA.
- **RN:** RN-017, RN-079, RN-080.
- **Evidencia:** Back: `services/platform.py:343-505`; API `POST /platform/activation/with-code`, `POST /platform/password/forgot|reset` (más `POST /auth/login` y `POST /auth/mfa/verify` compartidos). Front: `pages/Platform/PlatformAuth.jsx` (`/plataforma/login`, `/administracion/activar`, `/plataforma/recuperar`, `/plataforma/restablecer`). BD: `Usuario`, `TokenCuenta`.
- **Pruebas:** `test_platform_code_activation.py`, `test_platform.py`, `Platform.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-078 — Panel global y estado del sistema
- **Descripción:** El sistema debe permitir consultar un panel global (administrador) o técnico (moderador) y el estado real de los componentes del sistema.
- **Actor / precondiciones:** administrador o moderador del sistema con MFA.
- **Comportamiento y resultado:** solo agregados sin datos personales; verifica la base de datos con su latencia, el cifrado de MFA, la conexión TCP al servidor SMTP y a `accounts.google.com`, la biblioteca pySerial y la matriz global, e informa operativo, degradado, no disponible o desconocido.
- **RN:** RN-017, RN-084.
- **Evidencia:** Back: `services/platformDashboard.py`; API `GET /platform/dashboard`, `GET /platform/system`. Front: `Platform/PlatformDashboard.jsx`. BD: varias (consultas de conteo).
- **Pruebas:** `test_platform_dashboard.py`, `test_admin_dashboard.py`, `Platform.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-079 — Gestionar a los moderadores del sistema
- **Descripción:** El sistema debe permitir al administrador listar, invitar, reenviar la invitación, restablecer la contraseña y revocar el acceso de moderadores del sistema.
- **Actor / precondiciones:** administrador con MFA y reautenticación.
- **Comportamiento y resultado:** ver RN-079 y RN-080; todo se audita en el módulo de plataforma.
- **RN:** RN-079, RN-080.
- **Evidencia:** Back: `services/platform.py:226-340`; API `GET|POST /platform/moderators`, `GET /platform/moderators/{id}`, `POST .../resend-invitation|revoke|password-reset`. Front: `Platform/PlatformPages.jsx` (`/plataforma/moderadores`). BD: `Usuario`, `TokenCuenta`.
- **Pruebas:** `test_platform.py`, `test_platform_reinvite.py`, `Platform.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-080 — Transferir la administración del sistema
- **Descripción:** El sistema debe permitir al administrador ofrecer la administración a un moderador activo con MFA y al destinatario aceptarla o rechazarla, y al administrador cancelarla.
- **Actor / precondiciones:** administrador (inicia y cancela); moderador del sistema destinatario (responde).
- **Comportamiento y resultado:** el intercambio de roles es atómico; conserva el historial de transferencias.
- **RN:** RN-081.
- **Evidencia:** Back: `services/platform.py:534-679`; API `GET|POST /platform/transfer`, `POST /platform/transfer/cancel|accept|reject`. Front: `Platform/PlatformPages.jsx` (`/plataforma/transferencia`). BD: `TransferenciaAdministracion`.
- **Pruebas:** `test_platform.py`, `Platform.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-081 — Supervisar y controlar instituciones
- **Descripción:** El sistema debe permitir listar instituciones, consultar su detalle administrativo, pausarlas, reactivarlas, cambiar su límite de cuentas y auditar su actividad.
- **Actor / precondiciones:** administrador o moderador del sistema con MFA.
- **Comportamiento y resultado:** la pausa rige de inmediato; el cambio de estado y su evidencia se confirman juntos; el límite puede quedar por debajo de las cuentas activas.
- **RN:** RN-037, RN-040, RN-083.
- **Evidencia:** Back: `services/platformInstitutions.py`; API `GET /platform/institutions`, `GET .../{id}`, `GET .../{id}/audit`, `POST .../{id}/pause|reactivate`, `PUT .../{id}/capacity`. Front: `Platform/PlatformInstitutions.jsx`, `PlatformInstitutionControl.jsx`. BD: `Institucion`, `Auditoria`.
- **Pruebas:** `test_platform_institution_control.py`, `test_quota.py`, `Platform.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-082 — Eliminar una institución administrativamente
- **Descripción:** El sistema debe permitir al administrador eliminar (cerrar lógicamente) una institución con motivo, confirmación de nombre, MFA y reautenticación.
- **Actor / precondiciones:** administrador; institución activa o pausada.
- **Comportamiento y resultado:** marca el cierre administrativo, que el propietario no puede revertir; avisa a los integrantes sin el motivo.
- **RN:** RN-039, RN-041.
- **Evidencia:** Back: `services/platformInstitutions.py:185-240`, `institution.py:1336-1388`; API `POST /platform/institutions/{id}/delete`. Front: `Platform/PlatformInstitutionControl.jsx`. BD: `Institucion` (columnas de cierre administrativo, `CK_Institucion_cierreAdministrativo`).
- **Pruebas:** `test_platform_institution_deletion.py`.
- **Estado:** IMPLEMENTADO.

### RF-083 — Cuenta propia de la administración
- **Descripción:** El sistema debe permitir a la cuenta administrativa consultar su rol, permisos y estado de MFA, configurar su MFA y cambiar su contraseña.
- **Actor / precondiciones:** administrador o moderador del sistema.
- **Comportamiento y resultado:** informa si debe configurar MFA para operar.
- **RN:** RN-017.
- **Evidencia:** Back: `services/platform.py:151-161,507-533`; API `GET /platform/me`, `POST /platform/password/change`. Front: `Platform/PlatformPages.jsx` (`/plataforma/perfil`, `/seguridad`, `/cambiar-contrasena`). BD: `Usuario`, `FactorMfa`.
- **Pruebas:** `test_platform.py`, `Platform.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-084 — Inicializar y recuperar la administración desde el servidor
- **Descripción:** El sistema debe permitir, mediante comandos de servidor, crear la invitación del primer administrador, reemplazar al administrador por un moderador activo con MFA y recuperar el acceso de la misma persona.
- **Actor / precondiciones:** quien opera el servidor, con el entorno del backend.
- **Comportamiento y resultado:** nunca deja dos administradores ni ninguno; audita siempre, también los rechazos.
- **RN:** RN-082.
- **Evidencia:** Back: `cli/initAdmin.py`, `cli/recoverAdmin.py`, `services/platform.py:682-860`. Front: sin pantalla. BD: `Usuario`, `Auditoria`.
- **Pruebas:** `test_platform_recovery.py`, `test_platform_reinvite.py`, `test_platform_sqlserver.py` (requiere SQL Server de prueba).
- **Estado:** IMPLEMENTADO.

### RF-085 — Diagnosticar el esquema de la base y las claves de MFA
- **Descripción:** El sistema debe permitir comparar, en modo solo lectura, la base instalada con el esquema que esperan los modelos, y diagnosticar las claves de cifrado de MFA sin mostrarlas.
- **Actor / precondiciones:** quien opera el servidor.
- **Comportamiento y resultado:** `schemaCheck` informa diferencias de tablas, columnas, restricciones e índices y sale con código 0 o 1; `mfaKeys` informa cuántos factores descifra cada clave candidata y puede recifrar con confirmación expresa.
- **RN:** RN-015.
- **Evidencia:** Back: `cli/schemaCheck.py`, `cli/mfaKeys.py`, `services/schemaCompat.py`. Front: sin pantalla. BD: catálogo del sistema (solo lectura).
- **Pruebas:** `test_reference_schema.py` (compara texto del esquema con los modelos), `test_security_config.py`.
- **Estado:** IMPLEMENTADO.

## M-13 Auditoría

### RF-086 — Consultar la auditoría global
- **Descripción:** El sistema debe permitir al administrador consultar la auditoría general con filtros, resumen, detalle de eventos, instituciones y cuentas.
- **Actor / precondiciones:** administrador del sistema con MFA.
- **Comportamiento y resultado:** muestra clasificación y severidad, IP, cliente y correlación; paginación y conteos resueltos en SQL.
- **RN:** RN-085, RN-086, RN-087.
- **Evidencia:** Back: `services/auditQuery.py`, `auditClassification.py`; API `GET /audit`, `GET /audit/summary`, `GET /audit/institutions`, `GET /audit/events/{id}`. Front: `Account/audit/AdminAudit.jsx`, `AuditPages.jsx`, `AuditDetail.jsx` (`/plataforma/auditoria`). BD: `Auditoria`, `AuditoriaContexto`.
- **Pruebas:** `test_audit.py`, `test_audit_security.py`, `test_audit_names.py`, `test_audit_resolution.py`, `test_audit_summary.py`, `Audit.test.jsx`, `AuditAdmin.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-087 — Consultar la auditoría de una institución
- **Descripción:** El sistema debe permitir al propietario consultar la auditoría de su institución con resumen y detalle.
- **Actor / precondiciones:** propietario de una institución activa.
- **Comportamiento y resultado:** solo eventos de esa institución, sin IP, cliente ni eventos de plataforma.
- **RN:** RN-086.
- **Evidencia:** Back: `services/auditQuery.py`; API `GET /institutions/{id}/audit`, `.../audit/summary`, `.../audit/events/{idAuditoria}`. Front: `Account/audit/AuditPages.jsx` (`/app/instituciones/:id/auditoria`). BD: `Auditoria`.
- **Pruebas:** `test_audit.py`, `test_audit_security.py`, `Audit.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-088 — Señales de actividad sospechosa y alerta por correo
- **Descripción:** El sistema debe calcular y mostrar señales de actividad sospechosa y avisar por correo al administrador ante una ráfaga detectada.
- **Actor / precondiciones:** administrador del sistema.
- **Comportamiento y resultado:** señales calculadas al momento con umbrales configurables, sin bloquear a nadie; el aviso se limita a uno por patrón y hora.
- **RN:** RN-087.
- **Evidencia:** Back: `services/securityDetection.py`, `securityMonitor.py`; API `GET /audit/security/signals`. Front: `Account/audit/AuditSecurity.jsx`. BD: `Auditoria`.
- **Pruebas:** `test_audit_security.py`.
- **Estado:** IMPLEMENTADO (los contadores viven en la memoria del proceso).

### RF-089 — Buscar cuentas y consultar su ficha de auditoría
- **Descripción:** El sistema debe permitir al administrador buscar cuentas y ver su ficha con los eventos como autoras o afectadas.
- **Actor / precondiciones:** administrador del sistema.
- **Comportamiento y resultado:** abrir la ficha de una cuenta individual queda auditado a nombre de quien la abrió.
- **RN:** RN-086.
- **Evidencia:** Back: `services/auditQuery.py`; API `GET /audit/accounts`, `GET /audit/accounts/{idUsuario}`. Front: `Account/audit/AdminAudit.jsx`. BD: `Auditoria`.
- **Pruebas:** `test_audit.py`, `test_audit_names.py`, `AuditAdmin.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-090 — Consultar la auditoría técnica anonimizada de mediciones
- **Descripción:** El sistema debe permitir al administrador consultar la auditoría técnica anonimizada de mediciones fallidas y su resumen.
- **Actor / precondiciones:** administrador del sistema.
- **Comportamiento y resultado:** datos sin identificar personas, conservados 180 días.
- **RN:** RN-089.
- **Evidencia:** Back: `services/technicalAudit.py`; API `GET /audit/technical-measurements`, `GET /audit/technical-measurements/summary`. Front: sin pantalla ni módulo de acceso. BD: `AuditoriaTecnicaMedicion`.
- **Pruebas:** `test_measurement_lifecycle.py` (escritura del evento).
- **Estado:** PARCIAL (el registro y la consulta existen en el backend; no hay pantalla).

### RF-091 — Conservar y depurar la auditoría
- **Descripción:** El sistema debe anular la IP y el cliente de los eventos antiguos, eliminar los intentos de acceso sin cuenta identificable y, si se configura un plazo, eliminar eventos vencidos, dejando constancia de cada depuración.
- **Actor / precondiciones:** servicio `lifecycle` con la cuenta de base de conservación.
- **Comportamiento y resultado:** depuración por lotes e idempotente.
- **RN:** RN-088.
- **Evidencia:** Back: `services/auditRetention.py`, `jobs/accountLifecycle.py`. Front: sin pantalla. BD: `Auditoria`, `AuditoriaContexto`; permisos en `database/reference/GlucoLume_permisos.sql`.
- **Pruebas:** `test_audit_security.py`.
- **Estado:** PARCIAL (90 días y 12 meses por defecto; la eliminación total de eventos queda desactivada hasta aprobar el plazo).

## M-14 a M-17 Correo, retención, suscripciones y contenido

### RF-092 — Enviar una consulta desde el formulario de contacto
- **Descripción:** El sistema debe permitir a un visitante enviar una consulta desde la página pública.
- **Actor / precondiciones:** visitante; el servidor tiene configurada la casilla de destino.
- **Comportamiento y resultado:** envía la consulta con `Reply-To` del visitante y una confirmación secundaria; aplica los límites de RN-093.
- **RN:** RN-093.
- **Evidencia:** Back: `services/contact.py`; API `POST /contact`. Front: `pages/Landing/ContactSection.jsx`. BD: no persiste.
- **Pruebas:** `test_register_contact.py`, `Landing.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-093 — Enviar los correos transaccionales del sistema
- **Descripción:** El sistema debe enviar por correo los avisos y enlaces del catálogo de eventos (verificación, seguridad, grupos, instituciones, pacientes, mediciones, plataforma), con plantilla, asunto genérico y validación del contexto.
- **Actor / precondiciones:** SMTP configurado (sin SMTP el envío queda deshabilitado).
- **Comportamiento y resultado:** envía después de confirmar la operación; un fallo no la revierte.
- **RN:** RN-091, RN-092.
- **Evidencia:** Back: `services/email.py`, `emails/eventTypes.py`, `integrations/email/sender.py`, `emails/*.html`. Front: sin pantalla propia; los enlaces apuntan a rutas del frontend (dos no existen, ver H-04). BD: no persiste.
- **Pruebas:** `test_emails.py`, `test_email.py`, `test_security_config.py`.
- **Estado:** PARCIAL (68 tipos definidos, 11 sin emisión; dos enlaces apuntan a rutas inexistentes).

### RF-094 — Desidentificar y anonimizar datos de pacientes vencidos
- **Descripción:** El sistema debe desidentificar de forma irreversible los datos personales de pacientes cuya conservación venció y, con el esquema de retención, mover sus mediciones a la cohorte anónima y borrar las mediciones vencidas.
- **Actor / precondiciones:** ejecución del trabajo de retención con la cuenta de base correspondiente.
- **Comportamiento y resultado:** por lotes e idempotente; deja un evento por ejecución con cantidades.
- **RN:** RN-095.
- **Evidencia:** Back: `services/institutionalRetention.py`, `measurementRetention.py`, `jobs/purgeInstitutionalRetention.py`. Front: sin pantalla (`docs/PENDIENTES.md`: sin interfaz de la política). BD: `PerfilMedicion`, `Medicion`.
- **Pruebas:** `test_retention_anonymization.py`.
- **Estado:** PARCIAL (el trabajo no está programado en Compose; se ejecuta a mano).

### RF-095 — Minimizar los datos históricos del personal
- **Descripción:** El sistema debe suprimir los datos personales históricos del personal dado de baja una vez vencido el plazo configurado.
- **Actor / precondiciones:** servicio `lifecycle`; `PERSONNEL_RETENTION_MONTHS` mayor que 0.
- **Comportamiento y resultado:** suprime nombre, apellido, legajo y matrícula y registra la fecha de minimización.
- **RN:** RN-094.
- **Evidencia:** Back: `services/personnelRetention.py`, `jobs/accountLifecycle.py`. Front: sin pantalla. BD: `InstitucionUsuario.fechaMinimizacionDatos`.
- **Pruebas:** `test_account_lifecycle.py`, `test_audit_minimized_names.py`.
- **Estado:** PARCIAL (desactivado por defecto: plazo no aprobado).

### RF-096 — Suscripciones, planes y pagos
- **Descripción:** El sistema debería gestionar planes, suscripciones, períodos de prueba, proveedores y transacciones de pago.
- **Actor / precondiciones:** administrador del sistema (permiso `SUSCRIPCIONES_Y_PAGOS`).
- **Comportamiento y resultado:** hoy solo existen las tablas, los modelos y esquemas; la pantalla informa «Próximamente: no hay cobros, suscripciones, facturación ni integraciones con proveedores de pago». Los servicios `subscription.py` y `notificationConfig.py` están vacíos.
- **RN:** —.
- **Evidencia:** Back: `models/subscription*.py`, `paymentProvider.py`, `paymentTransaction.py`, `trialPeriod.py`, `notificationConfig.py` y sus esquemas. Front: `Platform/PlatformPages.jsx` (`SubscriptionsPage`). BD: `PlanSuscripcion`, `Suscripcion`, `SuscripcionUsuario`, `PeriodoPrueba`, `ProveedorPago`, `TransaccionPago`, `ConfiguracionNotificacion`.
- **Pruebas:** `Platform.test.jsx` (verifica el aviso «Próximamente»).
- **Estado:** PREVISTO.

### RF-097 — Consultar consejos para personas con diabetes
- **Descripción:** El sistema debe permitir leer artículos educativos en cinco categorías, con buscador, filtro por etiqueta y fuentes con enlace, y aviso de que no reemplazan la consulta médica.
- **Actor / precondiciones:** cuenta autenticada.
- **Comportamiento y resultado:** contenido estático del frontend; dos destacados en el inicio.
- **RN:** —.
- **Evidencia:** Back: no interviene. Front: `Account/DiabetesTipsPage.jsx`, `components/DiabetesTips.jsx`, `DiabetesArticle.jsx`, `data/diabetesTips.js`. BD: no interviene.
- **Pruebas:** `DiabetesTips.test.jsx`.
- **Estado:** IMPLEMENTADO.

### RF-098 — Consultar la página de presentación y la política de privacidad
- **Descripción:** El sistema debe permitir a cualquier visitante ver la página de presentación (funcionalidades y soluciones) y la política de privacidad.
- **Actor / precondiciones:** visitante.
- **Comportamiento y resultado:** contenido público estático.
- **RN:** RN-002.
- **Evidencia:** Back: no interviene (la versión de la política es `POLICY_VERSION=1.1`). Front: `pages/Landing/*`, `pages/Privacy/PrivacyPolicy.jsx`. BD: no interviene.
- **Pruebas:** `Landing.test.jsx`, `Privacy.test.jsx`.
- **Estado:** IMPLEMENTADO (la validación externa del texto de la política figura como pendiente en `docs/PENDIENTES.md`).

### RF-099 — Exportar datos
- **Descripción:** El sistema debería permitir exportar datos (por ejemplo mediciones o auditoría) en formatos como CSV o PDF, auditando cada exportación.
- **Actor / precondiciones:** por definir.
- **Comportamiento y resultado:** hoy no existe ninguna función de exportación; solo está el punto obligatorio de auditoría para las futuras.
- **RN:** RN-090.
- **Evidencia:** Back: `services/exportAudit.py` (`auditedExport`). Front: sin pantalla. BD: eventos de auditoría de exportación definidos, sin emisión.
- **Pruebas:** `test_audit_security.py` (exige que toda exportación futura pase por `auditedExport`).
- **Estado:** PREVISTO.

### RF-100 — Control de acceso por ruta y permiso en la interfaz
- **Descripción:** El sistema debe restringir en la interfaz las rutas privadas a cuentas autenticadas, las rutas de invitados a quienes no tienen sesión y las secciones por permiso, informado por el backend.
- **Actor / precondiciones:** cualquier cuenta; la autorización real la decide el backend en cada pedido.
- **Comportamiento y resultado:** redirige según sesión y permisos; las rutas desconocidas vuelven al inicio; el enlace de omisión de navegación facilita el acceso por teclado.
- **RN:** RN-012.
- **Evidencia:** Back: los permisos se informan en `GET /institutions/mine` y `GET /platform/me`. Front: `routes/ProtectedRoute.jsx`, `App.jsx`, `institutions/SectionGuard.jsx`, `components/SkipLink.jsx`, `layouts/*`. BD: no interviene.
- **Pruebas:** `App.test.jsx`, `Layout.test.jsx`, `SkipLink.test.jsx`, `InstitutionNavigation.test.jsx`.
- **Estado:** IMPLEMENTADO.
