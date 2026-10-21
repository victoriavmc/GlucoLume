# 02 — Reglas de negocio de GlucoLume

**Relevamiento por ingeniería inversa** · Etapa 2 · 21 de octubre de 2026.

Este documento enumera las reglas de negocio (RN) que el sistema aplica, con la evidencia técnica que las respalda. Una regla de negocio es una condición que determina cómo debe comportarse el sistema; no describe una funcionalidad (ver `03_REQUERIMIENTOS_FUNCIONALES.md`) ni un atributo de calidad (ver `04_REQUERIMIENTOS_NO_FUNCIONALES.md`).

## Cómo leer el documento

- Cada regla tiene identificador `RN-nnn`, nombre, descripción, módulo, roles afectados, condición con sus excepciones y estados, evidencia y estado de implementación (definiciones en `01_INVENTARIO_MODULOS.md`, sección 1.3).
- Las rutas son relativas a la raíz del repositorio. Las abreviaturas `S:` (servicio), `M:` (modelo), `API:` (router), `BD:` (script SQL), `Cfg:` (configuración) y `Pr:` (pruebas automatizadas) identifican el tipo de evidencia. Las líneas citadas corresponden a la lectura del 21 de octubre de 2026.
- La columna «Pr:» solo indica los archivos de pruebas que ejercitan el tema. En esta etapa **no se afirma que las pruebas pasen**; el resultado de su ejecución se informa en `07_RESUMEN_EJECUTIVO.md`.
- Los roles se escriben con los nombres que usa el sistema: cuenta individual (`CONSUMIDOR_FINAL`), cuenta institucional (`USUARIO_INSTITUCIONAL`), propietario, moderador y operador (roles de una institución), administrador del grupo, administrador del sistema (`ADMINISTRADOR_PLATAFORMA`) y moderador del sistema (`MODERADOR_PLATAFORMA`).

## Resumen

| Bloque | Reglas | Cantidad |
|---|---|---|
| A. Cuentas, acceso y seguridad de la identidad | RN-001 a RN-025 | 25 |
| B. Grupos familiares | RN-026 a RN-032 | 7 |
| C. Instituciones y roles | RN-033 a RN-044 | 12 |
| D. Pacientes institucionales | RN-045 a RN-054 | 10 |
| E. Mediciones | RN-055 a RN-067 | 13 |
| F. Dispositivos y adquisición | RN-068 a RN-074 | 7 |
| G. Matrices de referencia | RN-075 a RN-078 | 4 |
| H. Administración de la plataforma | RN-079 a RN-084 | 6 |
| I. Auditoría | RN-085 a RN-090 | 6 |
| J. Correo electrónico | RN-091 a RN-093 | 3 |
| K. Retención y privacidad | RN-094 a RN-096 | 3 |
| **Total** | | **96** |

---

## A. Cuentas, acceso y seguridad de la identidad

### RN-001 — El registro público solo crea cuentas individuales o institucionales
- **Módulo:** M-01. **Roles:** persona sin cuenta.
- **Descripción:** el formulario público de registro admite únicamente los tipos `CONSUMIDOR_FINAL` y `USUARIO_INSTITUCIONAL`. Los tipos de plataforma no se pueden elegir ni crear por esa vía. El registro de tipo institucional solo marca la cuenta: no crea instituciones ni vínculos.
- **Condición y excepciones:** la comprobación se repite en el servicio además del esquema. Un correo ya registrado con otro tipo no cambia de tipo (RN-009).
- **Evidencia:** S: `backend/app/services/auth.py:73,130-134,148-153`; M: `backend/app/schemas/user.py` (`TipoCuentaPublica`); Pr: `test_auth_access_account_type.py`.
- **Estado:** IMPLEMENTADO.

### RN-002 — Crear una cuenta exige confirmar la Política de Privacidad
- **Módulo:** M-01, M-03. **Roles:** persona que se registra; persona invitada que activa su cuenta.
- **Descripción:** el backend rechaza el registro local, el registro con Google y la activación de una cuenta invitada si no consta la confirmación de lectura de la política (`POLITICA_NO_ACEPTADA`). La aceptación queda registrada en `ConsentimientoUsuario` con la versión vigente del texto (1.1).
- **Condición y excepciones:** la validación no depende del frontend. Iniciar sesión con una cuenta existente no vuelve a exigirla.
- **Evidencia:** S: `backend/app/services/consent.py:29,85-87`, `auth.py:155,187,754,787`; Pr: `test_consents.py`, `test_register_contact.py`.
- **Estado:** IMPLEMENTADO.

### RN-003 — Política de contraseñas nuevas
- **Módulo:** M-01. **Roles:** toda cuenta con contraseña local.
- **Descripción:** una contraseña nueva (registro, activación, restablecimiento, cambio o alta de credencial local) debe tener entre 8 y 128 caracteres, con al menos una mayúscula, una minúscula, un número y un símbolo; no puede reducirse a una palabra común, una secuencia o una repetición; y no puede contener el nombre, el apellido, el usuario ni la parte local del correo.
- **Condición y excepciones:** el inicio de sesión no aplica la política, para no bloquear cuentas anteriores a ella. En el cambio de contraseña, la nueva debe ser distinta de la actual.
- **Evidencia:** S: `backend/app/core/security.py:54-129`, `auth.py:137-145,1108-1111`; M: `backend/app/schemas/auth.py:30-44`; datos: `backend/app/core/commonPasswords.txt` (233 líneas); Pr: `test_password_change.py`, `test_password_recovery.py`, `test_register_contact.py`.
- **Estado:** IMPLEMENTADO.

### RN-004 — Verificación del correo electrónico con plazo fijo
- **Módulo:** M-01. **Roles:** cuenta local nueva.
- **Descripción:** la cuenta local nace en estado `PENDIENTE` y solo se activa al abrir el enlace de verificación (token de un solo uso). El plazo es de 24 horas desde la creación (`EMAIL_VERIFICATION_EXPIRE_HOURS`); los reenvíos no lo extienden y deben separarse al menos 60 segundos. Vencido el plazo, la cuenta se elimina y libera correo y usuario.
- **Condición y excepciones:** la respuesta al reenvío es idéntica exista o no la cuenta. La eliminación ocurre tanto en el trabajo programado como en las operaciones sensibles (inicio de sesión, verificación, reenvío y registro). Si la cuenta dejó eventos de auditoría, queda como baja anónima en lugar de borrarse.
- **Evidencia:** S: `backend/app/services/auth.py:148-361`, `unverifiedAccounts.py:1-40`; Cfg: `backend/app/core/config.py:65`; trabajo: `backend/app/jobs/cleanupUnverifiedAccounts.py`; Pr: `test_account_lifecycle.py`, `test_register_contact.py`.
- **Estado:** IMPLEMENTADO.

### RN-005 — Unicidad de correo y de nombre de usuario
- **Módulo:** M-01. **Roles:** toda cuenta.
- **Descripción:** no puede haber dos cuentas con el mismo correo ni con el mismo nombre de usuario. Una cuenta pendiente con plazo vencido no retiene ninguno de los dos. Un correo asociado a una invitación institucional pendiente no se puede registrar por el formulario: la persona debe activar su cuenta desde el enlace recibido.
- **Condición y excepciones:** el nombre de usuario no puede estar vacío, tener menos de 4 caracteres ni contener «@». Ante dos registros simultáneos, los índices únicos filtrados deciden.
- **Evidencia:** S: `backend/app/services/auth.py:159-168,193-196`, `user.py:31-112`; M: `backend/app/schemas/user.py:19-33`; BD: `UX_Usuario_correoElectronico`, `UX_Usuario_usuario`; Pr: `test_username.py`, `test_profile.py`.
- **Estado:** IMPLEMENTADO (los índices figuran en el commit del esquema; ver hallazgo H-01 en `06`).

### RN-006 — Solo una cuenta activa puede iniciar sesión
- **Módulo:** M-01. **Roles:** toda cuenta.
- **Descripción:** el acceso (por contraseña, Google o MFA) exige el estado `ACTIVO`. Una cuenta `PENDIENTE` recibe `CORREO_NO_VERIFICADO`; cualquier otro estado, `CUENTA_NO_ACTIVA`. El intento queda auditado.
- **Evidencia:** S: `backend/app/services/auth.py:120-124,380-389,932-936`, `resolveAccessSession` (`auth.py:1055-1072`); Pr: `test_auth_access.py`, `test_auth_access_flows.py`.
- **Estado:** IMPLEMENTADO.

### RN-007 — Bloqueo temporal por contraseñas incorrectas
- **Módulo:** M-01. **Roles:** cuentas con credencial local.
- **Descripción:** tres contraseñas incorrectas consecutivas bloquean la credencial durante 15 minutos (`AUTH_LOCKOUT_MINUTES`). Durante el bloqueo no se verifica la contraseña ni se suma al contador. Vencido el bloqueo, el contador se reinicia con el siguiente intento. El contador se modifica con sentencias condicionadas para que las solicitudes simultáneas no superen el límite. El bloqueo genera un evento de seguridad y un aviso por correo al titular.
- **Condición y excepciones:** la reautenticación con la contraseña actual (cambio de contraseña, eliminación de cuenta, operaciones sensibles) comparte el mismo contador y bloqueo. Una contraseña correcta reinicia el contador.
- **Evidencia:** S: `backend/app/services/auth.py:61,392-591`; BD: `CK_CredencialLocal_intentos`; Cfg: `config.py:62`; Pr: `test_login_lockout.py`, `test_mfa_attempts_atomic.py`, `test_lifecycle_concurrency.py`.
- **Estado:** IMPLEMENTADO.

### RN-008 — Respuesta uniforme ante credenciales inválidas
- **Módulo:** M-01. **Roles:** cualquier persona que intente ingresar.
- **Descripción:** para una cuenta inexistente, una cuenta solo con Google o una contraseña incorrecta, el sistema responde lo mismo (`CREDENCIALES_INVALIDAS`) y tarda un tiempo equivalente (verificación contra un hash ficticio), para no revelar si la cuenta existe. El identificador escrito en un intento sobre una cuenta inexistente no se guarda: solo un HMAC.
- **Evidencia:** S: `backend/app/services/auth.py:367-377,522-549`, `security.py:141-143`, `audit.py:200-205`; Pr: `test_auth_access.py`, `test_login_email_no_ip.py`.
- **Estado:** IMPLEMENTADO.

### RN-009 — Vinculación y creación de cuentas con Google
- **Módulo:** M-01. **Roles:** persona con cuenta de Google.
- **Descripción:** iniciar sesión con Google nunca crea una cuenta: solo entra una identidad ya vinculada o un correo ya registrado y activo. Registrarse con Google crea una cuenta nueva del tipo público pedido. La vinculación automática a una cuenta existente exige que Google informe el correo como verificado, que coincida y que la cuenta de GlucoLume esté `ACTIVA`. Una persona con correo ya registrado con otro tipo de cuenta no puede registrarse de nuevo con ese tipo (`CUENTA_OTRO_TIPO`).
- **Condición y excepciones:** una cuenta que ya tiene una identidad de Google no admite otra. Una cuenta creada por invitación institucional vigente puede activarse con Google (RN-025).
- **Evidencia:** S: `backend/app/services/auth.py:604-815`; Pr: `test_google_exchange.py`.
- **Estado:** IMPLEMENTADO.

### RN-010 — Los tokens de sesión no viajan en la URL de retorno de Google
- **Módulo:** M-01. **Roles:** persona que ingresa con Google.
- **Descripción:** el retorno de Google entrega al frontend un código de un solo uso con vigencia de 120 segundos, que el frontend canjea por la sesión. Solo se guarda el hash del código y se descartan los códigos anteriores sin usar. Un segundo tipo de código (prefijo `t.`) permite continuar una sesión ya autenticada en otro origen.
- **Evidencia:** S: `backend/app/services/auth.py:70,662-730`; Pr: `test_google_exchange.py`.
- **Estado:** IMPLEMENTADO.

### RN-011 — Sesión con renovación rotativa y revocación ante reutilización
- **Módulo:** M-01. **Roles:** toda cuenta autenticada.
- **Descripción:** el token de acceso (JWT) vence a los 30 minutos y el de renovación a los 7 días. Cada renovación revoca el token usado y entrega uno nuevo. Presentar un token de renovación ya usado o revocado revoca todas las sesiones de la cuenta y deja el evento `REFRESH_REUTILIZADO`.
- **Condición y excepciones:** el token de renovación es opaco, de 48 bytes aleatorios; solo se guarda su hash SHA-256.
- **Evidencia:** S: `backend/app/services/auth.py:895-937`, `security.py:149-155,161-195`; Cfg: `config.py:58,61`; Pr: `test_auth_access_flows.py`, `test_audit_security.py`.
- **Estado:** IMPLEMENTADO.

### RN-012 — La autorización se evalúa contra la base en cada pedido
- **Módulo:** M-01, M-05, M-12. **Roles:** toda cuenta autenticada.
- **Descripción:** el token no transporta el rol, el tipo de cuenta ni el estado. En cada pedido se verifica que la sesión siga vigente y que el usuario esté activo, y los permisos (rol institucional, tipo de cuenta de plataforma, estado de la institución) se leen de la base. Un cambio de rol, una baja, una pausa o un cierre rigen de inmediato también para las sesiones ya iniciadas.
- **Evidencia:** S: `backend/app/services/auth.py:1055-1072`, `institution.py:19-22,263-292`, `platform.py:3-6`; API: `backend/app/api/deps.py:30-43`; Pr: `test_auth_access.py`, `test_operator_scope.py`.
- **Estado:** IMPLEMENTADO.

### RN-013 — Recuperación de contraseña con enlace de un solo uso
- **Módulo:** M-01. **Roles:** cuentas activas con contraseña local que no son de plataforma.
- **Descripción:** el enlace vence a los 30 minutos (`PASSWORD_RESET_EXPIRE_MINUTES`) y puede usarse una vez. Un enlace nuevo no se emite antes de 60 segundos. La respuesta es idéntica exista o no la cuenta. Al completar el restablecimiento se cierran todas las sesiones y se reinicia el bloqueo.
- **Condición y excepciones:** las cuentas de plataforma usan su propio circuito (RN-080). Una cuenta solo con Google no tiene contraseña que recuperar.
- **Evidencia:** S: `backend/app/services/auth.py:943-1035`; Cfg: `config.py:80`; Pr: `test_password_recovery.py`.
- **Estado:** IMPLEMENTADO.

### RN-014 — El cambio de contraseña exige reautenticación y cierra las demás sesiones
- **Módulo:** M-01. **Roles:** cuentas con credencial local.
- **Descripción:** para cambiar la contraseña se pide la actual y, si la cuenta tiene MFA habilitado, un código. Se conserva la sesión desde la que se cambia y se revocan las demás. Una cuenta solo con Google puede agregar una contraseña local.
- **Evidencia:** S: `backend/app/services/auth.py:1078-1120`; Pr: `test_password_change.py`.
- **Estado:** IMPLEMENTADO.

### RN-015 — La verificación en dos pasos es opcional, bloqueable y no admite reutilizar códigos
- **Módulo:** M-02. **Roles:** cuentas con MFA habilitado.
- **Descripción:** el segundo factor TOTP (6 dígitos, intervalos de 30 s, tolerancia de un intervalo) se aplica tras cualquier autenticación primaria. Cinco códigos inválidos consecutivos bloquean el factor durante 15 minutos. Un mismo intervalo de tiempo solo se acepta una vez, también ante pedidos simultáneos. Si el servidor no tiene clave de cifrado, un MFA habilitado nunca se omite: no hay sesión (`MFA_NO_DISPONIBLE`).
- **Condición y excepciones:** el secreto TOTP se guarda cifrado (Fernet, con soporte de claves anteriores para rotación). El factor se activa solo al confirmar un código válido.
- **Evidencia:** S: `backend/app/services/mfa.py:26,52-232`, `auth.py:822-826`, `security.py:37-40,278-331`; BD: `CK_FactorMfa_intentos`; Pr: `test_mfa_flow.py`, `test_mfa_attempts_atomic.py`.
- **Estado:** IMPLEMENTADO.

### RN-016 — Recuperación del segundo factor controlada por correo
- **Módulo:** M-02. **Roles:** cuentas con MFA que perdieron el autenticador.
- **Descripción:** se generan 10 códigos de recuperación de 16 caracteres, almacenados con hash y de un solo uso. Quien perdió también los códigos puede pedir un código de 6 dígitos al correo registrado: vigencia de 10 minutos, un solo uso, como máximo uno por minuto y tres por hora por cuenta. Antes se revalida la contraseña actual (o un ingreso reciente con Google). Al verificar, se elimina el factor y sus códigos, se revocan las sesiones anteriores y se avisa por correo.
- **Evidencia:** S: `backend/app/services/mfaRecovery.py:1-60`, `security.py:32,336-348`; Pr: `test_mfa_recovery.py`.
- **Estado:** IMPLEMENTADO.

### RN-017 — Las cuentas administrativas exigen MFA para operar
- **Módulo:** M-02, M-12. **Roles:** administrador y moderador del sistema.
- **Descripción:** mientras `PLATFORM_MFA_REQUIRED` esté activo (valor por defecto), el panel de plataforma y las rutas globales de dispositivos, matrices y auditoría rechazan a la cuenta administrativa sin MFA habilitado (`MFA_REQUERIDA_PLATAFORMA`). Solo se permite consultar el perfil propio y configurar el MFA.
- **Evidencia:** S: `backend/app/services/platform.py:84,108-111`; API: `backend/app/api/deps.py:64-71`; Cfg: `config.py:76`; Pr: `test_platform.py`, `test_account_deletion.py`.
- **Estado:** IMPLEMENTADO.

### RN-018 — Límite de solicitudes por IP en los puntos públicos
- **Módulo:** M-01, M-13. **Roles:** cualquier cliente sin sesión.
- **Descripción:** cada punto público tiene un tope de pedidos por ventana y por IP (por ejemplo: inicio de sesión 60 cada 10 minutos, registro 10 por hora, reenvío de verificación 5 cada 15 minutos, recuperación 5 cada 15 minutos, MFA 30 cada 10 minutos, activación administrativa 10 cada 15 minutos). Superado el tope se responde 429 con `Retry-After`. Las direcciones IPv6 se agrupan por prefijo /64. El puente serie bloquea a una IP que falla 20 veces el token en 10 minutos.
- **Condición y excepciones:** los contadores viven en la memoria del proceso: el límite es exacto con una sola réplica del backend (ver RNF-014).
- **Evidencia:** API: `backend/app/api/rateLimit.py:23-87`; Pr: `test_rate_limiter.py`, `test_security_hardening.py`, `test_stream_limits.py`.
- **Estado:** IMPLEMENTADO.

### RN-019 — Avisos de seguridad por correo
- **Módulo:** M-03, M-14. **Roles:** titular de la cuenta.
- **Descripción:** el aviso de nuevo inicio de sesión se envía por defecto y el titular puede desactivarlo (desde la cuenta o desde un enlace firmado de 30 días). Las alertas de acceso inusual, bloqueo, cambio de contraseña, activación o desactivación de MFA y vinculación de Google se envían siempre.
- **Evidencia:** S: `backend/app/services/auth.py:1123-1162`, `security.py:262-272`; Pr: `test_security_hardening.py`, `test_emails.py`.
- **Estado:** PARCIAL (el enlace de desuscripción de los correos apunta a una ruta del frontend que no existe; ver H-04 en `06`).

### RN-020 — Edición del perfil personal
- **Módulo:** M-03. **Roles:** toda cuenta.
- **Descripción:** la cuenta puede completar o actualizar nombre, apellido, usuario, fecha de nacimiento y sexo. Solo los cambios reales se guardan y se auditan; la auditoría registra el estado de cada campo (completado, actualizado, mantenido), nunca los valores. Fecha de nacimiento y sexo son opcionales y solo se piden, en una cuenta individual, para medir; el nombre de usuario nunca es obligatorio. Una vez completados, los campos no se borran.
- **Evidencia:** S: `backend/app/services/user.py:17-114`; M: `backend/app/schemas/user.py:114-156`; Pr: `test_profile.py`, `test_username.py`.
- **Estado:** IMPLEMENTADO.

### RN-021 — Consentimiento de datos experimentales
- **Módulo:** M-03, M-07. **Roles:** cuenta individual.
- **Descripción:** sin una autorización vigente para almacenar sus mediciones experimentales, una cuenta individual no puede iniciar mediciones ni recibir muestras (`CONSENTIMIENTO_REQUERIDO`). El historial de consentimientos es de solo agregado: revocar agrega una fila y no borra lo medido. Si cambia el texto de un consentimiento se sube su versión y las aceptaciones anteriores dejan de ser vigentes.
- **Condición y excepciones:** el consentimiento de los pacientes de una institución lo gestiona la institución y no se valida en este módulo.
- **Evidencia:** S: `backend/app/services/consent.py:1-106`, `measurement.py:172-177,272,364`; M: `ConsentimientoUsuario`; Pr: `test_consents.py`, `test_measurements.py`.
- **Estado:** IMPLEMENTADO.

### RN-022 — Eliminación de la cuenta propia en dos pasos y con impedimentos
- **Módulo:** M-03. **Roles:** cuentas individuales e institucionales.
- **Descripción:** primero se solicita (enlace de un solo uso por correo, 30 minutos); después se confirma con reautenticación (contraseña si tiene credencial local y MFA si lo tiene habilitado). Se impide la baja si la cuenta tiene un vínculo institucional activo (en cualquier rol), si administra un grupo activo, o si es una cuenta de plataforma.
- **Evidencia:** S: `backend/app/services/accountDeletion.py:1-30,126-166,213-263,461-500`; Pr: `test_account_deletion.py`.
- **Estado:** IMPLEMENTADO.

### RN-023 — La baja de cuenta anonimiza y conserva la trazabilidad
- **Módulo:** M-03, M-15. **Roles:** cuenta eliminada.
- **Descripción:** la fila de `Usuario` se conserva con el mismo identificador, estado `ELIMINADO` y los datos personales en nulo (nombre, apellido, correo, usuario, fecha de nacimiento, sexo). Se eliminan las credenciales, el MFA, la identidad de Google y los tokens, y se revocan las sesiones. Se abandonan los grupos donde era integrante, se cierran las invitaciones pendientes y se anonimiza el perfil de medición propio. Las mediciones se conservan desidentificadas, con edad y sexo del momento. Las relaciones institucionales históricas y la auditoría no se modifican.
- **Evidencia:** S: `backend/app/services/accountDeletion.py:360-431`; Pr: `test_account_deletion.py`.
- **Estado:** IMPLEMENTADO (las mediciones de cuentas individuales eliminadas no tienen plazo de borrado; decisión pendiente en `docs/PENDIENTES.md`).

### RN-024 — Período de gracia de 30 días para cuentas institucionales sin vínculos
- **Módulo:** M-03, M-05. **Roles:** cuentas institucionales activas.
- **Descripción:** cuando una cuenta institucional pierde su última vinculación activa, o queda habilitada sin ninguna, comienza un período de 30 días corridos. Iniciar sesión no lo reinicia y una invitación pendiente no lo cancela. Incorporarse efectivamente a una institución (aceptar una invitación, crear una institución o reabrirla) cancela el plazo. Vencido el plazo, el trabajo `lifecycle` elimina y anonimiza la cuenta con la misma anonimización de RN-023.
- **Condición y excepciones:** las cuentas pendientes (sin verificar o sin activar) no tienen plazo de gracia. Las operaciones concurrentes se serializan con bloqueo de fila y actualizaciones condicionadas.
- **Evidencia:** S: `backend/app/services/accountGrace.py:1-144`, `accountLifecycle.py:1-48`; trabajo: `backend/app/jobs/accountLifecycle.py`; Pr: `test_account_lifecycle.py`, `lifecycle_concurrency.py`.
- **Estado:** IMPLEMENTADO.

### RN-025 — Cuentas creadas por invitación institucional
- **Módulo:** M-03, M-05. **Roles:** persona sin cuenta invitada por una institución.
- **Descripción:** invitar a un correo sin cuenta crea un usuario institucional `PENDIENTE` sin credenciales y un enlace de activación de un solo uso. El enlace solo habilita la cuenta si queda al menos una invitación vigente (pendiente, no vencida y de una institución activa). La persona elige usuario y contraseña (misma política que RN-003) o ingresa con Google con ese correo, y después acepta o rechaza la invitación. La invitación vigente dura 7 días. Las cuentas que quedan sin ninguna invitación aceptable y sin enlace vigente se depuran: se anonimizan y se libera el correo.
- **Evidencia:** S: `backend/app/services/invitedAccounts.py:1-60`, `accountActivation.py:1-45`, `pendingAccounts.py:1-40`, `institution.py:723-943`; Pr: `test_institution_staff.py`, `test_account_lifecycle.py`, `test_personnel_incorporation.py`.
- **Estado:** IMPLEMENTADO.

---

## B. Grupos familiares

### RN-026 — Los grupos son solo para cuentas individuales y una cuenta pertenece a un único grupo activo
- **Módulo:** M-04. **Roles:** cuenta individual.
- **Descripción:** solo las cuentas `CONSUMIDOR_FINAL` crean o integran grupos familiares. Una cuenta no puede tener más de un grupo activo. Un correo de cuenta institucional o inexistente se rechaza como candidato.
- **Condición y excepciones:** los índices únicos filtrados garantizan la regla ante solicitudes simultáneas; el servicio traduce el choque a un conflicto controlado.
- **Evidencia:** S: `backend/app/services/group.py:5-11,133-135,227-253,324-345`; BD: `UX_GrupoUsuario_grupoActivo`, `UX_GrupoUsuario_vinculoVigente`; Pr: `test_groups.py`.
- **Estado:** IMPLEMENTADO.

### RN-027 — Cada grupo tiene un único administrador
- **Módulo:** M-04. **Roles:** administrador del grupo, integrantes.
- **Descripción:** el creador del grupo queda como administrador (`PROPIETARIO` en el modelo). Nunca hay dos administradores ni ninguno. El administrador no puede abandonar el grupo si hay otros integrantes (debe transferir antes el rol) y, si es el único integrante, debe eliminar el grupo. El rol de moderador no se usa en grupos familiares.
- **Evidencia:** S: `backend/app/services/group.py:500-552`; BD: `UX_GrupoUsuario_administrador`; Pr: `test_groups.py`.
- **Estado:** IMPLEMENTADO.

### RN-028 — Invitaciones a un grupo
- **Módulo:** M-04. **Roles:** administrador del grupo (invita); persona invitada (responde).
- **Descripción:** solo el administrador invita, por correo exacto, a cuentas individuales activas que no sean ya integrantes ni tengan invitación pendiente ni pertenezcan a otro grupo. La invitación vence a los 7 días, no incorpora a nadie hasta que la persona la acepta y, al aceptar, se dan de baja las otras invitaciones pendientes. Las búsquedas e invitaciones están limitadas a 20 cada 10 minutos por cuenta.
- **Evidencia:** S: `backend/app/services/group.py:79,105,324-481`; Pr: `test_groups.py`.
- **Estado:** IMPLEMENTADO.

### RN-029 — Salida, desvinculación y eliminación de grupos
- **Módulo:** M-04. **Roles:** administrador del grupo, integrantes.
- **Descripción:** un integrante puede abandonar el grupo; el administrador puede desvincular integrantes, transferir su rol a otro integrante activo y eliminar el grupo, para lo cual debe escribir el nombre exacto del grupo. Eliminar el grupo lo deja en estado `CERRADO` y da de baja todos los vínculos; no modifica cuentas, perfiles ni mediciones. Al terminar cualquier vínculo se revoca lo compartido.
- **Evidencia:** S: `backend/app/services/group.py:146-150,487-586`; Pr: `test_groups.py`.
- **Estado:** IMPLEMENTADO.

### RN-030 — Compartición con cuatro permisos independientes decididos solo por su titular
- **Módulo:** M-04. **Roles:** cada integrante sobre su propio perfil.
- **Descripción:** cada integrante decide cuatro permisos sobre su perfil de medición: perfil, última medición, historial (que incluye gráficos y estadísticas) y aviso de medición. Todos quedan en 0 al incorporarse. Solo la propia cuenta puede modificarlos (la identidad sale de la sesión). Cada cambio se audita como consentimiento. Ser integrante o administrador no da acceso a datos ajenos.
- **Evidencia:** S: `backend/app/services/group.py:13-23,85,602-624`; Pr: `test_groups.py`, `test_group_shared_measurements.py`.
- **Estado:** IMPLEMENTADO.

### RN-031 — Cada consulta de datos compartidos verifica la autorización vigente
- **Módulo:** M-04. **Roles:** integrantes del grupo.
- **Descripción:** en cada consulta se comprueba que el grupo esté activo, que ambos vínculos estén activos en el mismo grupo, que el permiso específico esté vigente y que el dueño tenga perfil propio no depurado. Revocar, salir, ser desvinculado o eliminar el grupo corta el acceso en la consulta siguiente. Sin permiso se responde 403 y se audita el intento; un integrante ajeno al grupo recibe 404. Los accesos exitosos se auditan sin datos de salud. La última medición no habilita el historial y el aviso solo expone fecha y hora.
- **Evidencia:** S: `backend/app/services/group.py:650-744`; Pr: `test_group_shared_measurements.py`, `test_group_measurement_notice.py`.
- **Estado:** IMPLEMENTADO.

### RN-032 — Estadísticas del grupo: períodos fijos, solo agregados y datos DEMO aparte
- **Módulo:** M-04, M-11. **Roles:** integrantes con permiso de historial.
- **Descripción:** las estadísticas compartidas admiten 7, 30 o 90 días y devuelven agregados y una serie diaria; el historial compartido pagina con un máximo de 50 por página. Las mediciones DEMO se informan aparte y nunca dentro de los promedios.
- **Evidencia:** S: `backend/app/services/group.py:80-83,747-776`; Pr: `test_group_shared_measurements.py`, `test_dashboards.py`.
- **Estado:** IMPLEMENTADO.

---

## C. Instituciones y roles

### RN-033 — Roles institucionales y matriz de permisos
- **Módulo:** M-05. **Roles:** propietario, moderador, operador.
- **Descripción:** el tipo de cuenta y el rol institucional son conceptos distintos. Una cuenta institucional puede pertenecer a varias instituciones con un rol en cada una. El propietario crea la institución, la modifica, designa y revoca moderadores, supervisa y desvincula operadores, consulta la auditoría, gestiona matrices y dispositivos y elimina la institución. El moderador incorpora y desvincula operadores, gestiona pacientes, matrices y dispositivos (sin retirarlos) y consulta el equipo. El operador consulta la institución, gestiona los pacientes a su cargo y ve los dispositivos operativos que puede usar.
- **Condición y excepciones:** la función profesional (operador, enfermero, médico) es descriptiva: no otorga permisos.
- **Evidencia:** S: `backend/app/services/institution.py:1-14,97-146`; M: `backend/app/models/institutionUser.py` (restricciones de rol y función); Pr: `test_institutions.py`, `test_operator_scope.py`.
- **Estado:** IMPLEMENTADO.

### RN-034 — Pertenecer a una institución se verifica en cada operación
- **Módulo:** M-05. **Roles:** personal institucional.
- **Descripción:** cada operación resuelve el vínculo `ACTIVO` de la cuenta con una institución `ACTIVA` y el rol sale de la base. Quien no pertenece, o si la institución fue cerrada, recibe «no encontrada» (no se revela qué instituciones existen). Sin el permiso, 403 `PERMISO_INSUFICIENTE`.
- **Evidencia:** S: `backend/app/services/institution.py:263-292`; Pr: `test_institutions.py`, `test_institution_staff.py`.
- **Estado:** IMPLEMENTADO.

### RN-035 — El CUIT es único y una institución cerrada solo la reabre su último propietario
- **Módulo:** M-05. **Roles:** cuenta institucional, último propietario.
- **Descripción:** el identificador legal debe ser único. Si el CUIT pertenece a una institución activa se rechaza el alta; si pertenece a una cerrada no se crea otra: solo el último propietario puede reabrirla, con reautenticación. La reapertura conserva identificador, CUIT, auditoría, bajas y perfiles archivados, incrementa el contador de reaperturas, actualiza los datos administrativos y crea un vínculo de propietario nuevo; no restaura moderadores, operadores ni invitaciones. Un CUIT se valida con su dígito verificador cuando el tipo de identificador es CUIT.
- **Evidencia:** S: `backend/app/services/institution.py:327-519`; M: `backend/app/schemas/institution.py:76-120`; BD: `UQ_Institucion_identificadorLegal`; Pr: `test_institution_reopen.py`, `test_institutions.py`.
- **Estado:** IMPLEMENTADO.

### RN-036 — Incorporación de personal por invitación con aceptación
- **Módulo:** M-05. **Roles:** propietario (invita moderadores), moderador (invita operadores), persona invitada.
- **Descripción:** se invita por correo exacto a cuentas institucionales activas. Si el correo no tiene cuenta, se crea una pendiente (RN-025). Una cuenta individual se rechaza sin cambiar su tipo; una cuenta ya vinculada no se duplica ni cambia de rol. La invitación vence a los 7 días y se reenvía renovando el vencimiento. La incorporación solo se concreta cuando la propia persona la acepta; puede rechazarla. Cae si venció, si la institución dejó de estar activa o si quien invitó perdió el permiso de invitar ese rol.
- **Condición y excepciones:** la búsqueda e invitación están limitadas a 20 cada 10 minutos por cuenta. El nombre y apellido son obligatorios solo cuando se crea la cuenta.
- **Evidencia:** S: `backend/app/services/institution.py:723-1162`; Pr: `test_institution_staff.py`, `test_personnel_incorporation.py`.
- **Estado:** IMPLEMENTADO.

### RN-037 — Capacidad máxima de cuentas activas por institución
- **Módulo:** M-05, M-12. **Roles:** propietario y moderador (consultan), administración de plataforma (modifica).
- **Descripción:** cada institución tiene un máximo de cuentas con vínculo activo (1000 por omisión, hasta 100 000). Consumen cupo las cuentas distintas con vínculo `ACTIVO` no eliminadas; no lo consumen invitaciones, bajas ni pacientes. El cupo se ocupa al aceptar la invitación, con la institución bloqueada, y se verifica de nuevo antes de confirmar. Si la plataforma reduce el máximo por debajo de las cuentas activas, estas se conservan y la institución queda «excedida» sin admitir más hasta regularizarse.
- **Evidencia:** S: `backend/app/services/quota.py:1-100`, `institution.py:1080-1121`; BD: `CK_Institucion_capacidadMaximaUsuarios`; Pr: `test_quota.py`, `test_platform_institution_control.py`.
- **Estado:** IMPLEMENTADO.

### RN-038 — Revocar vínculos y cancelar invitaciones
- **Módulo:** M-05. **Roles:** propietario, moderador.
- **Descripción:** el propietario revoca moderadores y operadores; el moderador solo operadores. Nadie puede revocarse a sí mismo. Al revocar un moderador caen las invitaciones que emitió. La baja libera los dispositivos a cargo del integrante y cancela las transferencias pendientes dirigidas a él. Si era la última vinculación activa de la cuenta, comienza el período de gracia (RN-024).
- **Evidencia:** S: `backend/app/services/institution.py:1186-1290`; Pr: `test_institution_staff.py`.
- **Estado:** IMPLEMENTADO.

### RN-039 — Eliminación lógica de la institución con retención de pacientes
- **Módulo:** M-05, M-15. **Roles:** propietario (con reautenticación).
- **Descripción:** solo el propietario, escribiendo el nombre exacto y reautenticándose (contraseña y MFA si corresponde; una cuenta solo con Google sin MFA no puede confirmar), cierra la institución. El cierre es lógico (estado `CERRADA`, nunca `DELETE`): da de baja todos los vínculos, libera recursos, cancela las reasignaciones pendientes e inicia el período de gracia de las cuentas que quedan sin otra institución. Los datos de los pacientes pasan a conservación por 12 meses desde el cierre, sin acceso operativo. Las cuentas personales de los miembros no se modifican. El CUIT queda reservado.
- **Condición y excepciones:** el cierre es condicionado al estado vigente: dos cierres simultáneos no se aplican dos veces.
- **Evidencia:** S: `backend/app/services/institution.py:142,1296-1426`; Pr: `test_institutions.py`, `test_institution_reopen.py`, `test_platform_institution_deletion.py`.
- **Estado:** IMPLEMENTADO.

### RN-040 — Una institución pausada no permite ningún contexto institucional
- **Módulo:** M-05, M-12. **Roles:** personal de la institución pausada.
- **Descripción:** al pausar una institución (estado `INACTIVA`), todo pedido de su personal responde `INSTITUCION_PAUSADA` (403) con cualquier token ya emitido, porque el estado se lee de la base en cada pedido. El único contexto abierto es la consulta al soporte del propietario (limitada a 3 por hora por cuenta). La pausa no elimina ni modifica datos y solo afecta a esa institución. La adquisición y la telemetría solo reconocen instituciones activas; con el modo compartido del dispositivo (RN-071) la pausa de la institución titular no impide que otras cuentas usen el equipo.
- **Evidencia:** S: `backend/app/services/institution.py:258-260,287-288`, `institutionSupport.py:1-45`, `platformInstitutions.py:1-20`, `telemetry.py:131-157`; Pr: `test_platform_institution_control.py`.
- **Estado:** IMPLEMENTADO.

### RN-041 — El cierre administrativo de una institución no puede revertirse desde la cuenta
- **Módulo:** M-05, M-12. **Roles:** último propietario, administración de plataforma.
- **Descripción:** la eliminación administrativa (solo el administrador del sistema, con MFA y reautenticación, nombre exacto y motivo) reutiliza el cierre lógico y deja una marca en la fila (`cierreAdministrativo`, fecha, actor y motivo). El propietario no puede reabrirla ni crear otra con el mismo CUIT (`INSTITUCION_CERRADA_ADMINISTRATIVAMENTE`). El motivo no se informa a los integrantes.
- **Condición y excepciones:** si la base instalada no tiene las columnas, la operación responde `ELIMINACION_ADMINISTRATIVA_NO_DISPONIBLE` sin tocar nada.
- **Evidencia:** S: `backend/app/services/institution.py:318-358`, `platformInstitutions.py:185-240`; BD: `CK_Institucion_cierreAdministrativo`; Pr: `test_platform_institution_deletion.py`.
- **Estado:** IMPLEMENTADO.

### RN-042 — Un solo vínculo vigente por cuenta e institución y sin autoinvitación
- **Módulo:** M-05. **Roles:** personal institucional.
- **Descripción:** una cuenta no puede tener dos vínculos no dados de baja con la misma institución, ni invitarse a sí misma; todo vínculo necesita invitador salvo el que se origina al crear la institución; un vínculo activo exige fecha de incorporación y una baja exige fecha de baja.
- **Evidencia:** M: `backend/app/models/institutionUser.py:20-60`; BD: `UX_InstitucionUsuario_vinculoVigente`, `CK_InstitucionUsuario_*`; Pr: `test_institution_staff.py`.
- **Estado:** IMPLEMENTADO.

### RN-043 — El rol de un vínculo es fijo
- **Módulo:** M-05. **Roles:** personal institucional.
- **Descripción:** no existe una operación de cambio de rol. Quien vuelve con otro rol tiene un vínculo nuevo; los períodos anteriores se conservan en el perfil de la persona. Solo figura como personal quien se incorporó efectivamente (tiene fecha de incorporación) o tiene una invitación pendiente vigente; una baja sin incorporación no es una desvinculación.
- **Evidencia:** S: `backend/app/services/personnel.py:1-30`; Pr: `test_personnel.py`.
- **Estado:** IMPLEMENTADO.

### RN-044 — Los datos administrativos del vínculo los edita quien administra ese rol
- **Módulo:** M-05. **Roles:** propietario (moderadores y operadores), moderador (operadores).
- **Descripción:** matrícula, legajo, función profesional y nombre y apellido profesionales históricos se editan sin cambiar el rol ni los datos de la cuenta; la auditoría registra los nombres de los campos modificados, no sus valores. Esos datos se conservan aunque la cuenta se elimine y se anonimice.
- **Evidencia:** S: `backend/app/services/institution.py:977-1002`; Pr: `test_personnel.py`.
- **Estado:** IMPLEMENTADO.

---

## D. Pacientes institucionales

### RN-045 — El paciente institucional no es una cuenta: pertenece a la institución por su responsable
- **Módulo:** M-06. **Roles:** personal institucional.
- **Descripción:** un paciente es un perfil de medición de tipo institucional administrado por una institución. Pertenece a ella a través de su único operador responsable vigente, aunque ese vínculo luego quede de baja. Está activo mientras no tenga fecha de expiración de datos personales; en baja cuando la tiene (12 meses); depurado cuando se desidentificó.
- **Evidencia:** S: `backend/app/services/institutionPatients.py:1-30,61-71`; M: `backend/app/models/measurementProfile.py` (restricción de coherencia por tipo de perfil); Pr: `test_institution_patients.py`.
- **Estado:** IMPLEMENTADO.

### RN-046 — Separación entre información administrativa e información de salud
- **Módulo:** M-06, M-07, M-11. **Roles:** propietario, moderador, operador.
- **Descripción:** propietario, moderador y operador con permiso de consulta de pacientes ven la información administrativa (nombre, apellido, responsable, fecha de registro, estado). La información de salud individual (última medición, historial, gráficos, estadísticas, detalle de una medición, registro de nuevas mediciones y resultados por correo) la ve únicamente el operador responsable vigente del paciente. El rol administrativo no autoriza por sí solo ese acceso y no existe una excepción en esta versión. Un operador que consulta un paciente ajeno no recibe documento, fecha de nacimiento, edad ni sexo, ni puede buscar por documento ajeno. El intento rechazado se audita (acceso, fallo) sin valores de salud. La autoría histórica de una medición no es una autorización vigente.
- **Evidencia:** S: `backend/app/services/patientAccess.py:1-71`, `institutionPatients.py:142-170,263-265`, `measurement.py:139-169,702-718`; Pr: `test_patient_access.py`, `test_operator_scope.py`, `test_dashboard_privacy.py`.
- **Estado:** IMPLEMENTADO.

### RN-047 — Alta, modificación y documento del paciente
- **Módulo:** M-06. **Roles:** operador, moderador, propietario.
- **Descripción:** un operador registra pacientes que quedan siempre a su cargo y no puede asignarlos a otro (el intento se rechaza y se audita). Propietario y moderador deben designar al responsable, que debe ser un operador activo de la misma institución. Solo puede haber un paciente activo por documento dentro de una institución (el mismo documento puede existir en otra). El documento se normaliza (sin puntos, guiones ni espacios; 6 a 12 caracteres alfanuméricos) y la edad debe estar entre 0 y 130 años. Un operador solo modifica sus pacientes; propietario y moderador, cualquiera de la institución. Un paciente dado de baja no se modifica.
- **Evidencia:** S: `backend/app/services/institutionPatients.py:194-216,318-399`; M: `backend/app/schemas/measurementProfile.py:88-98,172-202`; BD: `UX_PerfilMedicion_dniInstitucion`, `CK_PerfilMedicion_dniNormalizado`; Pr: `test_institution_patients.py`, `test_patient_assignment.py`, `test_patient_identity.py`.
- **Estado:** IMPLEMENTADO.

### RN-048 — El cambio de responsable entre operadores requiere aceptación del destino
- **Módulo:** M-06. **Roles:** operador (solicita), operador destino (acepta o rechaza), propietario y moderador (proponen).
- **Descripción:** transferir un paciente no cambia su responsable al solicitar: crea una solicitud pendiente (una sola por paciente) que el operador destinatario acepta o rechaza, y que el solicitante puede cancelar. Solo el responsable actual solicita; solo el destino responde; solo el solicitante cancela; quien no participa recibe «no encontrada». Aceptar actualiza la solicitud y el perfil en una sola transacción; si el origen dejó de ser el responsable o dejó de estar activo, la solicitud se cancela por obsoleta sin sobrescribir al responsable actual. Si el responsable cambia o el paciente se da de baja, las solicitudes pendientes pierden vigencia. Las mediciones no se tocan.
- **Evidencia:** S: `backend/app/services/profileTransfers.py:1-30,386-585`, `institutionPatients.py:234-241`; M: `backend/app/models/profileTransfer.py:18-31`; BD: `UX_TransferenciaPerfil_pendiente`, `CK_TransferenciaPerfil_*`; Pr: `test_profile_transfers.py`, `test_transfer_detail.py`.
- **Estado:** IMPLEMENTADO.

### RN-049 — La asignación de responsable por la gestión no es unilateral cuando el responsable sigue activo
- **Módulo:** M-06. **Roles:** propietario, moderador.
- **Descripción:** si el paciente tiene un responsable activo, la designación de otro operador por propietario o moderador crea una propuesta de transferencia que el operador destino debe aceptar (los propietarios reciben aviso y se marca si el destino fue invitado por el propio gestor). Solo un paciente sin responsable activo (operador desvinculado) se asigna directamente. Cada asignación directa deja una transferencia aceptada y la auditoría con el responsable anterior y el nuevo.
- **Evidencia:** S: `backend/app/services/institutionPatients.py:402-496`; Pr: `test_patient_assignment.py`, `test_manager_reassignment.py`.
- **Estado:** IMPLEMENTADO.

### RN-050 — Un operador con pacientes activos no puede desvincularse sin reasignarlos
- **Módulo:** M-05, M-06. **Roles:** propietario, moderador, operador a desvincular.
- **Descripción:** la baja de un operador activo se rechaza con `PACIENTES_ASIGNADOS` mientras tenga pacientes activos a su cargo. El camino de baja reasigna todos sus pacientes y lo desvincula en una sola transacción: el destino lo elige siempre quien gestiona (nunca el sistema) entre operadores activos de la misma institución; un paciente con transferencia pendiente impide la baja hasta que se resuelva. Para operadores ya desvinculados con pacientes sin responsable, una operación de regularización crea una tarea de reasignación pendiente por paciente (una sola por paciente) que propietario o moderador resuelven.
- **Condición y excepciones:** la reasignación es independiente de la eliminación de la cuenta global del operador. Un paciente dado de baja o anonimizado no genera tarea. El aviso por correo a los moderadores descrito en el encabezado de `reassignments.py` no se emite desde el código de la aplicación (ver H-03 en `06`).
- **Evidencia:** S: `backend/app/services/institution.py:1203-1262`, `operatorOffboarding.py:1-150`, `reassignments.py:1-153`, `institutionReassignments.py:1-128`; M: `backend/app/models/patientReassignment.py`; BD: `UX_ReasignacionPaciente_pendiente`; Pr: `test_operator_offboarding.py`, `test_manager_reassignment.py`, `test_account_lifecycle.py`.
- **Estado:** IMPLEMENTADO, con el aviso a moderadores PARCIAL (sin invocación).

### RN-051 — La baja de un paciente inicia su conservación y su anonimización
- **Módulo:** M-06, M-15. **Roles:** propietario, moderador.
- **Descripción:** la baja administrativa fija el fin de conservación en 12 meses, elimina el correo de resultados, cancela transferencias y reasignaciones y, si la base tiene las columnas del esquema v5 de retención, anonimiza al paciente en el acto: se borran sus datos personales y sus mediciones pasan a la cohorte anónima de la institución. Se rechaza si el paciente tiene una medición en curso (`MEDICION_EN_CURSO`). Sin las columnas, rige la desidentificación posterior por trabajo programado.
- **Evidencia:** S: `backend/app/services/institutionPatients.py:499-543`, `measurementRetention.py:1-30`; Pr: `test_institution_patients.py`, `test_retention_anonymization.py`.
- **Estado:** IMPLEMENTADO.

### RN-052 — El correo de resultados del paciente requiere autorización y confirmación del propio paciente
- **Módulo:** M-06, M-07. **Roles:** operador responsable, paciente.
- **Descripción:** el correo del paciente lo carga solo el operador responsable vigente, que declara la autorización del paciente. Una dirección nueva solo se guarda después de que el propio paciente confirma, desde un enlace firmado (72 horas, propósito único, botón explícito, idempotente). Se guarda 12 meses desde la confirmación y se borra al vencer o al darse de baja el paciente. La auditoría no registra el correo y la lectura lo devuelve enmascarado. Un envío puntual a una dirección distinta de la confirmada dispara la misma confirmación. Los pedidos de confirmación están limitados a 10 por hora por operador.
- **Evidencia:** S: `backend/app/services/resultEmailStore.py:1-20`, `resultEmailConfirmation.py:1-25`, `patientResultEmail.py:1-12`; Pr: `test_patient_result_email.py`, `test_result_email.py`, `test_result_email_on_save.py`, `test_patient_mails.py`.
- **Estado:** IMPLEMENTADO (requiere las columnas del esquema v5 de correo de resultados; sin ellas responde un mensaje de esquema desactualizado).

### RN-053 — No se informan estadísticas de salud de grupos con menos de cinco pacientes
- **Módulo:** M-06, M-11. **Roles:** propietario, moderador.
- **Descripción:** un conjunto de mediciones con menos de cinco pacientes distintos no se informa como estadística agregada de la institución, para que los filtros o los grupos pequeños no identifiquen a una persona. La cohorte anónima cuenta como un solo paciente.
- **Evidencia:** S: `backend/app/services/patientAccess.py:34,82-86`, `measurement.py:966-991`; Pr: `test_dashboard_privacy.py`, `test_patient_access.py`.
- **Estado:** IMPLEMENTADO.

### RN-054 — La reapertura no devuelve el acceso a pacientes del período anterior
- **Módulo:** M-05, M-06. **Roles:** personal institucional.
- **Descripción:** el padrón, las transferencias y las reasignaciones excluyen a los pacientes archivados cuyo responsable dejó de estar vinculado antes de la última reapertura de la institución.
- **Evidencia:** S: `backend/app/services/patientAccess.py:37-42`, `institutionPatients.py:97-118`; Pr: `test_reopen_period_views.py`.
- **Estado:** IMPLEMENTADO.

---

## E. Mediciones

### RN-055 — Ciclo de vida de una medición con transiciones atómicas
- **Módulo:** M-07. **Roles:** quien opera la medición.
- **Descripción:** estados `PENDIENTE`, `ADQUIRIENDO`, `PROCESANDO`, `COMPLETADA`, `INVALIDA`, `CANCELADA`. Las muestras llevan de pendiente a adquiriendo; finalizar lleva a procesando y después a completada o inválida; cancelar es posible desde pendiente o adquiriendo. Cada transición es una actualización condicionada al estado esperado, por lo que dos pedidos simultáneos no aplican la misma transición dos veces. Una medición solo pasa a completada en el mismo paso que persiste sus resultados. Las inválidas y canceladas nunca se presentan como resultado y quedan fuera de las estadísticas.
- **Evidencia:** S: `backend/app/services/measurement.py:3-10,346-558`; BD: `CK_Medicion_estado`, `CK_Medicion_fechas`; Pr: `test_measurements.py`, `test_measurement_lifecycle.py`.
- **Estado:** IMPLEMENTADO.

### RN-056 — Quién puede iniciar y operar una medición
- **Módulo:** M-07. **Roles:** cuenta individual, operador.
- **Descripción:** una cuenta individual opera solo su propio perfil (pertenecer a un grupo no da propiedad). Un operador opera solo los pacientes que tiene a cargo en ese momento, con vínculo activo, institución activa y paciente sin baja. Todo lo no autorizado se informa como inexistente (o como rechazo explícito auditado para integrantes de la institución sin asignación).
- **Evidencia:** S: `backend/app/services/measurement.py:12-17,139-185`; Pr: `test_measurements.py`, `test_operator_scope.py`, `test_patient_access.py`.
- **Estado:** IMPLEMENTADO.

### RN-057 — Autoría de la medición y datos históricos del momento
- **Módulo:** M-07, M-13. **Roles:** operador, cuenta individual.
- **Descripción:** quien inició la medición queda registrado en la auditoría (usuario y vínculo del operador) y esa autoría se conserva aunque el paciente cambie de responsable. La edad, el sexo, el firmware, el sensor, la matriz y la versión del algoritmo se copian a la medición y no se recalculan si cambia el perfil.
- **Evidencia:** S: `backend/app/services/measurement.py:17-19,277-338`; Pr: `test_measurement_profile.py`, `test_measurements.py`.
- **Estado:** IMPLEMENTADO.

### RN-058 — Edad y sexo opcionales; nunca se inventan
- **Módulo:** M-07. **Roles:** cuenta individual, operador.
- **Descripción:** la edad y el sexo de una medición toman, por prioridad, el dato informado para esa medición, el del perfil o nulo; nunca se asigna un valor por defecto. Son opcionales para oximetría y para la medición con el dispositivo. Una medición de glucosa por matriz exige edad y, para elegir regla, sexo masculino o femenino (o una regla prevista para sexo no informado). La hora de la última comida es opcional y no puede ser futura.
- **Evidencia:** S: `backend/app/services/measurement.py:268-317`, `measurementProfile.py:1-45`; Pr: `test_measurement_optional_data.py`, `test_optional_meal.py`, `test_glucose_mode.py`.
- **Estado:** IMPLEMENTADO.

### RN-059 — SpO₂ y frecuencia cardíaca: cálculo del servidor o valores del firmware, con origen identificado
- **Módulo:** M-07, M-09. **Roles:** todos los que miden.
- **Descripción:** en la adquisición de muestras crudas, el servidor calcula SpO₂ y frecuencia cardíaca sobre las muestras guardadas (versión `oximetria-ppg-v1`: ventana mínima de 10 s, descarte de los 2 s iniciales, nivel continuo mínimo de 3000, calidad mínima de 0,5, perfusión mínima de 0,0005) e ignora los valores que informe el cliente. En la medición con el dispositivo, el servidor guarda los valores ya procesados por el firmware, identificados con su versión de algoritmo; nunca escribe en el Arduino. Sin señal válida, la medición termina inválida.
- **Evidencia:** S: `backend/app/services/measurement.py:21-30,447-480`, `telemetry.py:1-21`; núcleo: `backend/app/acquisition/oximetry.py:19-25`; Pr: `test_oximetry.py`, `test_ppg.py`, `test_telemetry.py`.
- **Estado:** IMPLEMENTADO (sin validación clínica ni con hardware real; ver H-13).

### RN-060 — La glucosa nunca se inventa: no hay algoritmo de estimación en el servidor
- **Módulo:** M-07. **Roles:** todos los que miden.
- **Descripción:** el servidor no tiene algoritmo de estimación de glucosa definido: `glucoseEstimator` es solo un punto de integración vacío. Una medición de glucosa por muestras termina inválida con un motivo explícito. La única glucosa disponible es la que informa el firmware, con origen `DEMO` (sintético), `EXPERIMENTAL` o `SIN_CALIBRAR`. La glucosa mostrada es la estimada por matriz (si existiera) o la del dispositivo solo si su origen es experimental o DEMO; `SIN_CALIBRAR` nunca se toma como glucosa. La trazabilidad exige matriz y versión de algoritmo para toda glucosa estimada.
- **Condición y excepciones:** el propio firmware advierte que su resultado experimental es una correlación ajustada con referencias capilares y no una medición validada.
- **Evidencia:** S: `backend/app/services/measurement.py:121-125,482-485,827-834`; BD: `CK_Medicion_glucosaTrazable`, `CK_Medicion_glucosaCompletada`, `CK_Medicion_origenGlucosa`; firmware: `firmware/GlucoLume_MAX30100/GlucoLume_MAX30100.ino:1-31`; Pr: `test_glucose_mode.py`, `test_measurements.py` (el estimador se simula por *monkeypatch*).
- **Estado:** PARCIAL (infraestructura y reglas implementadas; algoritmo de estimación PREVISTO).

### RN-061 — Los datos DEMO quedan fuera de todo indicador
- **Módulo:** M-07, M-11, M-04. **Roles:** todos.
- **Descripción:** una medición DEMO usa un valor sintético del firmware. Puede consultarse y eliminarse (solo si está completada; una medición real responde 409), pero queda fuera de estadísticas, paneles, indicadores, avisos y correos. A una cuenta individual no se le envía una medición DEMO como resultado; a un paciente institucional sí, identificada como simulada. Cuando se muestran, sus estadísticas van aparte de las experimentales.
- **Evidencia:** S: `backend/app/services/measurement.py:21-24,724-764,1011-1014`; M: `backend/app/models/measurement.py:155-161` (`NOT_DEMO`); BD: `CK_Medicion_demoSinEstimacion`; Pr: `test_dashboards.py`, `test_evolution.py`, `test_group_shared_measurements.py`, `test_result_email.py`.
- **Estado:** IMPLEMENTADO.

### RN-062 — Visibilidad temporal de mediciones canceladas o inválidas y vencimiento por inactividad
- **Módulo:** M-07. **Roles:** cuenta individual.
- **Descripción:** en la vista personal, las mediciones canceladas o inválidas se ven 30 minutos desde su cierre y después se ocultan (no se borran; tampoco se recuperan por dirección directa). Las mediciones pendientes, adquiriendo o procesando sin actividad durante 30 minutos pasan a inválidas por tiempo agotado, salvo que haya una adquisición viva. Un mantenimiento periódico (cada 60 segundos) lo aplica y libera sesiones abandonadas del dispositivo.
- **Evidencia:** S: `backend/app/services/measurementVisibility.py:1-22`, `measurementLifecycle.py:1-45`, `maintenance.py:1-55`; Cfg: `config.py:111`; Pr: `test_measurement_lifecycle.py`.
- **Estado:** IMPLEMENTADO.

### RN-063 — La referencia capilar se carga a mano y no reemplaza la estimación
- **Módulo:** M-07. **Roles:** quien opera la medición.
- **Descripción:** solo se registra una referencia capilar (valor de glucómetro, fecha y hora no futura, marca y modelo opcionales) sobre una medición de glucosa completada, una por medición. Queda separada del valor estimado y nunca lo reemplaza. No se genera ni se deduce.
- **Evidencia:** S: `backend/app/services/measurement.py:564-587`; BD: `UQ_MedicionReferenciaCapilar_medicion`; Pr: `test_glucose_mode.py`.
- **Estado:** IMPLEMENTADO.

### RN-064 — La matriz aplicable la decide siempre el servidor
- **Módulo:** M-07, M-10. **Roles:** quien opera la medición.
- **Descripción:** para un perfil institucional se usa la matriz activa y vigente de su institución y, si no hay, la global activa y vigente; para un perfil individual, la global. El cliente nunca envía una matriz. Sin matriz o sin regla aplicable para el contexto no se inicia una medición de glucosa por matriz. En la medición con el dispositivo la matriz vigente se asocia solo como referencia de comparación; «dentro, por debajo o por encima» es una comparación matemática con el intervalo y no una clasificación clínica.
- **Evidencia:** S: `backend/app/services/matrix.py:287-321`, `measurement.py:235-262,290-293`, `glucoseReference.py:1-15`; Pr: `test_matrices.py`, `test_matrices_institucion.py`, `test_matrix_unreported_conditions.py`.
- **Estado:** IMPLEMENTADO.

### RN-065 — Envío del resultado por correo: destinatario, confirmación y límite
- **Módulo:** M-07, M-14. **Roles:** cuenta individual, operador responsable.
- **Descripción:** solo se envía el resultado de una medición completada. Una cuenta individual lo recibe en su propio correo. Un operador lo envía al correo confirmado del paciente; una dirección distinta exige confirmación del paciente (RN-052) y la declaración de autorización. Se admiten como máximo 3 envíos por medición por hora. Al completar una medición de un paciente institucional con correo vigente el resultado se envía automáticamente; un fallo de correo no deshace la medición. El correo de destino no se conserva en el registro de envíos.
- **Evidencia:** S: `backend/app/services/measurement.py:996-1103`; BD: `CK_EnvioResultado_enviado`; Pr: `test_result_email.py`, `test_result_email_on_save.py`, `test_patient_result_email.py`.
- **Estado:** IMPLEMENTADO.

### RN-066 — Historial, estadísticas y evolución: períodos, límites y paginación
- **Módulo:** M-07, M-11. **Roles:** cuenta individual, operador responsable.
- **Descripción:** el historial pagina con un máximo de 50 por página y filtra por fechas, modo, estado y origen. Las estadísticas admiten 7, 30 o 90 días o un rango; la evolución admite 24 horas, 7, 14, 30 o 90 días o un rango, con un máximo de 1000 puntos (se informa si se truncó). Solo se calculan sobre mediciones completadas y no DEMO; los valores ausentes son nulos y nunca ceros.
- **Evidencia:** S: `backend/app/services/measurement.py:110-111,644-690,781-960`; Pr: `test_evolution.py`, `test_patient_evolution.py`, `test_health_aggregates.py`.
- **Estado:** IMPLEMENTADO.

### RN-067 — Criterio de estabilidad para guardar una medición con el dispositivo
- **Módulo:** M-09. **Roles:** quien mide con el dispositivo.
- **Descripción:** «Guardar medición» solo procede si las últimas 8 lecturas consecutivas (separadas a lo sumo 3 segundos y de antigüedad máxima 5 segundos) son utilizables (dedo colocado, señal válida, al menos 25 muestras por segundo, BPM entre 20 y 250), tienen el mismo origen y varían poco (BPM hasta 8, SpO₂ hasta 2 puntos y, solo con origen experimental, glucosa hasta 15 mg/dL). El valor guardado es la mediana de cada magnitud. Con datos DEMO no se exige estabilidad de la glucosa. Dos guardados simultáneos no pueden completar dos veces.
- **Evidencia:** S: `backend/app/acquisition/telemetry.py:66-80`, `backend/app/services/telemetry.py:560-600`; Pr: `test_telemetry.py`, `test_glucose_mode.py`.
- **Estado:** IMPLEMENTADO.

---

## F. Dispositivos y adquisición

### RN-068 — Estados del dispositivo y uso solo en estado operativo
- **Módulo:** M-08. **Roles:** todos los que miden o administran.
- **Descripción:** los estados son operativo, en mantenimiento, fuera de servicio y baja (descomisionado, terminal). Solo un dispositivo operativo permite iniciar y continuar adquisiciones; si pasa a otro estado durante una medición, no se aceptan más datos. «Operativo» no es «conectado»: la conexión es un estado distinto del puente. Los dispositivos nunca se borran físicamente ni se borran sus mediciones.
- **Evidencia:** S: `backend/app/services/device.py:3-14,77,415-418,785-803`, `measurement.py:360-390`; BD: `CK_Dispositivo_estado`; Pr: `test_devices.py`, `test_device_control.py`.
- **Estado:** IMPLEMENTADO.

### RN-069 — Identidad del dispositivo por su código persistente
- **Módulo:** M-08, M-09. **Roles:** operador, cuenta individual, administración.
- **Descripción:** el código del dispositivo es único (sin distinguir mayúsculas) y proviene del identificador persistente que el firmware guarda en su memoria, nunca del puerto, el medio o el equipo. Si el firmware no informa identificador, el código configurado en el puente no prueba qué Arduino es: toda asociación a una institución exige confirmación explícita del operador. Un dispositivo existente con otro sensor se rechaza; el firmware solo lo actualiza quien administra el inventario de su ámbito.
- **Evidencia:** S: `backend/app/services/device.py:404-405,832-893`, `deviceConnection.py:1-30`; BD: `UQ_Dispositivo_codigo`; Pr: `test_device_connection.py`, `test_device_resolve_authority.py`.
- **Estado:** IMPLEMENTADO.

### RN-070 — Quién registra, asigna y retira dispositivos
- **Módulo:** M-08, M-12. **Roles:** administrador y moderador del sistema, propietario, moderador, operador.
- **Descripción:** el administrador del sistema administra todo el inventario global, incluida la asignación a instituciones y el retiro; el moderador del sistema consulta, da de alta, edita datos técnicos y cambia estados, sin asignar ni descomisionar. El propietario registra, cambia estados y descomisiona; el moderador institucional registra y cambia estados; el operador solo consulta los dispositivos operativos que puede usar. El alta institucional queda asignada a la institución y al propietario vigente sin que el cuerpo del pedido pueda elegir otro responsable. Una institución solo ve y administra sus dispositivos; los demás responden como inexistentes. Retirar o desvincular un dispositivo con mediciones en curso se rechaza.
- **Evidencia:** S: `backend/app/services/device.py:15-27,102-131,496-516,705-803`; Pr: `test_devices.py`, `test_device_context_authority.py`.
- **Estado:** IMPLEMENTADO.

### RN-071 — Uso compartido o restringido del dispositivo
- **Módulo:** M-08, M-09. **Roles:** cuentas individuales, operadores.
- **Descripción:** con `ALLOW_INDIVIDUAL_ON_INSTITUTIONAL_DEVICE` activado (valor transitorio, por defecto apagado), todas las cuentas habilitadas usan el único equipo sin importar a qué institución esté asignado, sin cambiar su titularidad ni compartir mediciones. Con el valor apagado rige la asignación: un dispositivo de una institución solo lo usan sus operadores y uno sin institución, las cuentas individuales.
- **Evidencia:** S: `backend/app/services/device.py:809-829`, `telemetry.py:131-157`; Cfg: `config.py:107-109`; Pr: `test_shared_device.py`, `test_device_context_authority.py`.
- **Estado:** IMPLEMENTADO (regla marcada en el código como transitoria).

### RN-072 — Una sola cuenta controla el dispositivo a la vez
- **Módulo:** M-09. **Roles:** cuentas habilitadas para medir.
- **Descripción:** el control del equipo se toma con una acción explícita («Usar dispositivo») o al iniciar una medición. Mientras otra cuenta lo controla se responde `DISPOSITIVO_EN_USO`. El control sin medición vence a los 5 minutos de la última acción explícita o a los 30 segundos sin consultar el estado; una sesión de medición dura como máximo 30 minutos y se da por abandonada tras 120 segundos sin actividad. Solo quien controla ve las lecturas en vivo y da órdenes. El control vive en memoria: un reinicio del servidor lo libera.
- **Evidencia:** S: `backend/app/acquisition/telemetry.py:81-88`, `backend/app/services/telemetry.py:172-210`; Pr: `test_device_control.py`, `test_telemetry.py`.
- **Estado:** IMPLEMENTADO (sin verificación con dos cuentas sobre hardware real, `docs/PENDIENTES.md`).

### RN-073 — Autoridad sobre las órdenes al puente
- **Módulo:** M-09. **Roles:** cuentas que miden.
- **Descripción:** las órdenes al puente (configurar puerto o medio, pausar, reanudar, detener, reiniciar) las da solo quien tiene el control temporal y autoridad sobre el dispositivo que ese puente atiende (contexto personal, compartido, institucional propio, institucional ajeno, institución pausada). Los rechazos se auditan. El puente acepta únicamente una lista cerrada de órdenes y ninguna escribe en el Arduino.
- **Evidencia:** S: `backend/app/services/telemetry.py:131-226`, `backend/app/acquisition/telemetry.py:361-362,616-636`; Pr: `test_bridge_command_authority.py`, `test_bridge.py`, `test_bridge_ctl.py`.
- **Estado:** IMPLEMENTADO.

### RN-074 — Autenticación del puente y un solo puente activo
- **Módulo:** M-09, M-21. **Roles:** puente serie.
- **Descripción:** el puente se autentica con un token compartido de al menos 32 caracteres (con rotación sin corte mediante un token anterior). Una IP que falla el token 20 veces en 10 minutos queda bloqueada aunque después acierte. Solo puede haber un puente activo por dispositivo. Un código informado por el puente que no está en el inventario se da de alta automáticamente solo si el Arduino nunca informó un identificador y transcurrieron 15 segundos; el alta queda operativa y sin institución.
- **Evidencia:** S: `backend/app/core/config.py:102-106,153-158`, `api/rateLimit.py:42-45`, `services/telemetry.py:70-111`, `device.py:463-493`; Pr: `test_bridge.py`, `test_bridge_runtime.py`, `test_security_config.py`.
- **Estado:** IMPLEMENTADO.

---

## G. Matrices de referencia

### RN-075 — Ámbitos de las matrices y quién las administra
- **Módulo:** M-10. **Roles:** administrador y moderador del sistema, propietario, moderador.
- **Descripción:** las matrices globales las administran las cuentas de plataforma y son la referencia de las cuentas individuales y de las instituciones sin matriz propia activa. Las institucionales las administran el propietario y el moderador de esa institución; nadie de otra institución las ve ni las modifica, ni siquiera la plataforma, y tienen prioridad dentro de su institución. Un moderador del sistema no adquiere permisos sobre matrices institucionales ni un propietario puede editar una global. El operador solo consulta cuál se aplica.
- **Evidencia:** S: `backend/app/services/matrix.py:3-12,100-155,449-455`; Pr: `test_matrices.py`, `test_matrices_institucion.py`.
- **Estado:** IMPLEMENTADO.

### RN-076 — Ciclo de vida e inmutabilidad de las matrices
- **Módulo:** M-10. **Roles:** quienes administran matrices.
- **Descripción:** estados `BORRADOR`, `ACTIVA`, `INACTIVA` y `ARCHIVADA` (terminal). Solo un borrador se edita; las versiones activas, inactivas o archivadas son inmutables y para cambiarlas se crea una versión nueva copiada en borrador. Activar reemplaza, en una sola transacción, a la activa del mismo ámbito, que pasa a inactiva. Se archiva un borrador o una versión inactiva. Las mediciones guardan el identificador de matriz, por lo que conservan la configuración con la que se calcularon. Las versiones se numeran de forma incremental por ámbito, institución y nombre.
- **Evidencia:** S: `backend/app/services/matrix.py:14-21,458-528,534-539,649-710`; BD: `UX_Matriz_globalActiva`, `UX_Matriz_institucionActiva`, `CK_Matriz_estado`; Pr: `test_matrices.py`.
- **Estado:** IMPLEMENTADO.

### RN-077 — Las reglas de una matriz no pueden solaparse ni duplicarse
- **Módulo:** M-10. **Roles:** quienes administran matrices.
- **Descripción:** dos reglas de la misma población (sexo y condición de comida) no pueden pisarse en rango de edad ni en minutos desde la comida, ni tener las mismas condiciones; no existe precedencia: una configuración ambigua no se guarda ni se activa (`REGLA_SOLAPADA`, `REGLA_DUPLICADA`). «Edad no especificada» es otra población. Los huecos de cobertura no bloquean y se informan como advertencias. Solo se activa una matriz válida y dentro de su vigencia. Los códigos de regla se generan (R-001, R-002…).
- **Evidencia:** S: `backend/app/services/matrix.py:23-31,333-446,649-663`; BD: `CK_ReglaMatriz_*`, `UQ_ReglaMatriz_codigo`; Pr: `test_matrices.py`, `test_matrix_unreported_conditions.py`.
- **Estado:** IMPLEMENTADO.

### RN-078 — Auditoría de las matrices
- **Módulo:** M-10, M-13. **Roles:** propietario, administración de plataforma.
- **Descripción:** toda operación sobre una matriz queda auditada; la auditoría de una matriz institucional la consulta solo el propietario (el moderador puede modificar pero no auditar) y la de una global solo las cuentas de plataforma.
- **Evidencia:** S: `backend/app/services/matrix.py:39-41,157-165,270-285`; Pr: `test_matrices_institucion.py`.
- **Estado:** IMPLEMENTADO.

---

## H. Administración de la plataforma

### RN-079 — Un único administrador del sistema y moderadores que no se convierten
- **Módulo:** M-12. **Roles:** administrador y moderador del sistema.
- **Descripción:** a lo sumo una cuenta de administrador del sistema vigente (incluye pendientes y bloqueadas). Las cuentas de plataforma no usan vínculos institucionales. Una cuenta individual o institucional no se convierte en moderador del sistema: hay que invitar otro correo. El moderador se invita por enlace de un solo uso (72 horas); no se puede invitar a quien ya es moderador activo. Revocar a un moderador lo bloquea, cierra sus sesiones y cancela las transferencias dirigidas a él.
- **Evidencia:** S: `backend/app/services/platform.py:1-9,245-321`; BD: `UX_Usuario_administradorUnico`; Pr: `test_platform.py`, `test_platform_reinvite.py`.
- **Estado:** IMPLEMENTADO.

### RN-080 — Reautenticación reforzada y circuitos propios de la administración
- **Módulo:** M-12. **Roles:** administrador y moderador del sistema.
- **Descripción:** las acciones sensibles de la administración piden contraseña (si hay credencial local) y código MFA. Las invitaciones y los restablecimientos son enlaces de un solo uso: nadie define ni conoce la contraseña de otra persona. La activación administrativa con código tiene un único mensaje de error para códigos inexistentes, vencidos o usados; no activa un segundo administrador y la sesión resultante solo puede configurar MFA. Los accesos y operaciones denegados se auditan.
- **Evidencia:** S: `backend/app/services/platform.py:99-148,401-438,444-505`; Cfg: `config.py:77-78`; Pr: `test_platform_code_activation.py`, `test_platform.py`.
- **Estado:** IMPLEMENTADO.

### RN-081 — Transferencia de la administración con aceptación del destinatario
- **Módulo:** M-12. **Roles:** administrador (inicia), moderador del sistema con MFA (destino).
- **Descripción:** solo el administrador inicia la transferencia hacia un moderador activo con MFA, con reautenticación; solo una pendiente a la vez; nada cambia hasta que el destinatario acepta, también con reautenticación. Aceptar baja al administrador a moderador y sube al destinatario en una sola transacción: nunca quedan cero ni dos administradores. Si quien la ofreció dejó de ser administrador, la transferencia se cancela por obsoleta.
- **Evidencia:** S: `backend/app/services/platform.py:550-669`; M: `backend/app/models/platformTransfer.py`; BD: `UX_TransferenciaAdministracion_pendiente`; Pr: `test_platform.py`.
- **Estado:** IMPLEMENTADO.

### RN-082 — El primer administrador y su recuperación solo se hacen desde el servidor
- **Módulo:** M-12. **Roles:** operador del servidor.
- **Descripción:** no existe ninguna ruta pública para crear administradores. El primero se crea con un comando de servidor que se niega si ya hay uno activo, no define contraseñas (envía un enlace de un solo uso) y exige activar MFA antes de operar. La recuperación (reemplazar al administrador por un moderador activo con MFA, o reinvitar a la misma persona) exige confirmar escribiendo el correo, y la opción automática requiere declarar autorización por variable de entorno. Cada ejecución, incluso las rechazadas, deja auditoría con motivo, usuario del sistema y equipo.
- **Evidencia:** S: `backend/app/cli/initAdmin.py:1-30`, `recoverAdmin.py:1-30`, `services/platform.py:682-860`; Pr: `test_platform_recovery.py`, `test_platform_reinvite.py`.
- **Estado:** IMPLEMENTADO.

### RN-083 — Control de instituciones por la plataforma
- **Módulo:** M-12, M-05. **Roles:** administrador y moderador del sistema.
- **Descripción:** ambos roles pueden listar instituciones, ver su detalle administrativo, pausarlas (motivo de 10 a 300 caracteres), reactivarlas (motivo obligatorio), cambiar su límite de cuentas (1 a 100 000) y auditar su actividad (también si está pausada o cerrada, sin datos clínicos ni secretos). Solo el administrador las elimina. La transición de estado y su evidencia se confirman en una sola transacción, condicionada al estado vigente.
- **Evidencia:** S: `backend/app/services/platformInstitutions.py:1-71,185-250`; API: `backend/app/api/v1/platform.py:86-141`; Pr: `test_platform_institution_control.py`.
- **Estado:** IMPLEMENTADO.

### RN-084 — El panel global solo muestra agregados
- **Módulo:** M-11, M-12. **Roles:** administrador y moderador del sistema.
- **Descripción:** el panel de plataforma calcula agregados con consultas reales, sin nombres, correos ni resultados clínicos identificables; el administrador ve todo y el moderador solo la parte técnica (dispositivos, mediciones agregadas, estado del sistema). Los eventos de actividad muestran módulo, acción y resultado, nunca quién los hizo.
- **Evidencia:** S: `backend/app/services/platformDashboard.py:1-8`; Pr: `test_platform_dashboard.py`, `test_admin_dashboard.py`.
- **Estado:** IMPLEMENTADO.

---

## I. Auditoría

### RN-085 — Todo evento relevante se registra por un único camino, sin secretos y sin modificación posterior
- **Módulo:** M-13. **Roles:** todos (generan eventos).
- **Descripción:** todos los módulos registran eventos mediante un servicio central que completa el módulo, la institución donde ocurrió el hecho (resuelta desde la entidad afectada, no desde el usuario) y la fecha y hora de Argentina. Se descartan las claves sensibles (contraseñas, tokens, secretos, hashes, códigos) antes de guardar. Los intentos rechazados de operaciones críticas se confirman aunque la operación no se aplique. Ningún endpoint modifica ni elimina eventos y la cuenta de base de la API puede tener denegados el UPDATE y el DELETE sobre la auditoría.
- **Evidencia:** S: `backend/app/services/audit.py:1-86,232-295`; BD: `database/reference/GlucoLume_permisos.sql`; Pr: `test_audit.py`, `test_audit_security.py`.
- **Estado:** IMPLEMENTADO (la denegación a nivel de base depende de aplicar el script de permisos).

### RN-086 — Quién consulta la auditoría y con qué alcance
- **Módulo:** M-13. **Roles:** administrador del sistema, propietario.
- **Descripción:** el administrador del sistema consulta la auditoría general con filtro opcional por institución; el propietario de una institución activa, únicamente los eventos de su institución (el filtro lo fija la ruta validada, no un parámetro). Moderadores, operadores, integrantes de grupos, cuentas individuales y moderadores del sistema reciben 403. La IP, el cliente y la correlación solo se muestran a la administración de la plataforma; la auditoría de una institución nunca los incluye ni muestra los eventos del módulo de plataforma. Los intentos no autorizados se registran sin recursión; abrir la ficha de una cuenta individual se audita.
- **Evidencia:** S: `backend/app/services/auditQuery.py:1-30`, `institution.py:121-122`; Pr: `test_audit.py`, `test_audit_security.py`, `test_audit_resolution.py`.
- **Estado:** IMPLEMENTADO.

### RN-087 — Clasificación de eventos y señales de actividad sospechosa
- **Módulo:** M-13. **Roles:** administrador del sistema.
- **Descripción:** los eventos se clasifican como informativos, operativos, sospechosos o confirmados (un control aplicado, sin afirmar que haya un ataque). Se calculan señales con umbrales configurables dentro de una ventana de 15 minutos: 5 fallos contra una misma cuenta, 5 cuentas distintas probadas desde un mismo origen, origen inusual para una cuenta con al menos 5 accesos exitosos previos, ráfagas de 20 rechazos 401/403 o de 30 rechazos 400/422 de un mismo origen y reutilización de tokens de sesión. No bloquean a nadie. Una ráfaga detectada se avisa por correo al administrador como máximo una vez por patrón cada 60 minutos (0 desactiva el aviso).
- **Evidencia:** S: `backend/app/services/auditClassification.py:1-45`, `securityDetection.py:1-35`, `securityMonitor.py:1-25,130-165`; Cfg: `config.py:118-134`; Pr: `test_audit_security.py`.
- **Estado:** IMPLEMENTADO.

### RN-088 — Conservación de la auditoría
- **Módulo:** M-13, M-15. **Roles:** servicio `lifecycle`.
- **Descripción:** la IP y el cliente de un evento se anulan a los 90 días y el evento sigue; los intentos de acceso sin cuenta identificable se eliminan a los 12 meses; los eventos completos solo se eliminan si se configura un plazo (por defecto no hay límite: el plazo legal no está aprobado). Cada pasada que depura algo deja un evento con las cantidades. La depuración la hace una cuenta de base propia de los trabajos.
- **Evidencia:** S: `backend/app/services/auditRetention.py:1-25`; Cfg: `config.py:135-141`, `compose.yaml:50-52`; Pr: `test_audit_security.py`.
- **Estado:** PARCIAL (90 días y 12 meses activos por defecto; conservación total sin límite hasta aprobar el plazo).

### RN-089 — La auditoría técnica de mediciones fallidas es anónima y temporal
- **Módulo:** M-13, M-07. **Roles:** administrador del sistema.
- **Descripción:** cuando una medición termina sin completarse se agrega un evento técnico anonimizado (tipo de operación, estado final, motivo, sensor, duración y código de error), sin identificadores de usuario, perfil ni medición y con la hora redondeada a la hora en punto. Se escribe en un punto de guardado: un problema no impide cerrar la medición. Se conserva 180 días y solo lo consulta el administrador del sistema.
- **Evidencia:** S: `backend/app/services/technicalAudit.py:1-30`; API: `backend/app/api/v1/audit.py:137-147`; Pr: `test_measurement_lifecycle.py`.
- **Estado:** PARCIAL (backend completo; la consulta no tiene pantalla en el frontend).

### RN-090 — Toda exportación futura de datos deberá pasar por la auditoría de exportaciones
- **Módulo:** M-13. **Roles:** quien exporte.
- **Descripción:** hoy no existe ninguna función de exportación de datos. El módulo de auditoría de exportaciones define el único camino obligatorio para cualquier exportación futura (solicitud, finalización o fallo, con el tipo de datos, el formato y la cantidad de registros, nunca el contenido), y una prueba exige que toda exportación futura lo use.
- **Evidencia:** S: `backend/app/services/exportAudit.py:1-30`; Pr: `test_audit_security.py` (`auditedExport`).
- **Estado:** PREVISTO.

---

## J. Correo electrónico

### RN-091 — Los correos se envían después de confirmar la operación y un fallo no la revierte
- **Módulo:** M-14. **Roles:** sistema.
- **Descripción:** los avisos se envían después del `commit` de la operación que los origina, en segundo plano cuando no deben demorar la respuesta, y un fallo de SMTP nunca revierte una creación, una baja o una medición. Las confirmaciones de creación de grupos e instituciones dejan constancia del envío y solo se reintentan si no hubo un envío exitoso.
- **Evidencia:** S: `backend/app/services/notifications.py:1-50`, `email.py`, `auth.py:83-87`; Pr: `test_emails.py`, `test_institutions.py`.
- **Estado:** IMPLEMENTADO.

### RN-092 — Los correos no incluyen datos de salud en el asunto ni claves prohibidas en el contexto
- **Módulo:** M-14. **Roles:** sistema.
- **Descripción:** los asuntos son genéricos y nunca incluyen datos de salud. El servicio rechaza contextos que contengan claves como contraseña, token, secreto o código de recuperación, valida el destinatario, las variables requeridas y que las URL de acción pertenezcan a los orígenes configurados, y no registra el contexto ni los códigos en los logs. El resultado de una medición solo se envía por la regla RN-065.
- **Evidencia:** S: `backend/app/emails/eventTypes.py:1-5`, `services/email.py:1-125`; Pr: `test_emails.py`.
- **Estado:** IMPLEMENTADO.

### RN-093 — El formulario de contacto público está limitado y no guarda datos
- **Módulo:** M-14, M-17. **Roles:** visitante.
- **Descripción:** la consulta se envía a la casilla configurada con la dirección del visitante como `Reply-To` y con el remitente siempre la cuenta SMTP del sistema; si falla, responde 503. La confirmación al visitante es secundaria: si falla se registra y la respuesta sigue siendo exitosa. Hay un máximo de 5 consultas por IP cada 15 minutos y 3 confirmaciones por dirección por hora. No se guarda nada en la base.
- **Evidencia:** S: `backend/app/services/contact.py:1-35`; API: `backend/app/api/v1/contact.py`; Pr: `test_register_contact.py`.
- **Estado:** IMPLEMENTADO.

---

## K. Retención y privacidad

### RN-094 — Minimización de datos personales históricos del personal
- **Módulo:** M-15. **Roles:** personal dado de baja.
- **Descripción:** pasado el plazo contado desde la baja de una relación institucional, se suprimen el nombre y apellido profesionales históricos, el legajo y la matrícula y se registra la fecha de minimización; la relación (rol, función, fechas, origen) no se borra. El plazo es el valor de `PERSONNEL_RETENTION_MONTHS`.
- **Condición y excepciones:** el valor por defecto es 0, que desactiva el procedimiento («el plazo todavía no fue aprobado»); el comentario del módulo menciona 120 meses por defecto, lo que no coincide con la configuración (ver H-05).
- **Evidencia:** S: `backend/app/services/personnelRetention.py:1-40`; Cfg: `config.py:113-116`, `.env.example:127`; trabajo: `backend/app/jobs/accountLifecycle.py`; Pr: `test_account_lifecycle.py`, `test_audit_minimized_names.py`.
- **Estado:** PARCIAL (implementado pero desactivado por defecto).

### RN-095 — Fin de la conservación de los datos de pacientes y cohorte anónima
- **Módulo:** M-06, M-15. **Roles:** pacientes dados de baja o de instituciones cerradas.
- **Descripción:** vencidos los 12 meses de conservación, los datos personales se desidentifican de forma irreversible. Con las columnas del esquema v5 de retención, las mediciones pasan a una cohorte anónima de la institución (sin persona, seudónimo ni responsable), con su fecha de fin de conservación fijada en la última medición de la persona más 12 meses; el perfil original queda sin datos de salud y con un seudónimo nuevo. Al vencer, se borran la medición y sus derivados (muestras, referencia capilar y envíos). La regla se evalúa por fecha, por lo que tras restaurar un respaldo antiguo una pasada vuelve a borrar lo vencido. Un paciente activo o una cuenta individual no vencen por no medir.
- **Evidencia:** S: `backend/app/services/measurementRetention.py:1-30`, `institutionalRetention.py:1-25`; trabajo: `backend/app/jobs/purgeInstitutionalRetention.py`; BD: `CK_PerfilMedicion_coherenciaTipo`, `IX_Medicion_vencimientoRetencion`; Pr: `test_retention_anonymization.py`.
- **Estado:** PARCIAL (el trabajo de retención no está programado en Compose y se ejecuta a mano con confirmación de la base; ver H-10).

### RN-096 — Eliminación a pedido de los datos históricos de una persona del personal
- **Módulo:** M-05, M-15. **Roles:** propietario (moderadores y operadores), moderador (operadores).
- **Descripción:** quien tiene permiso para desvincular a ese rol puede suprimir, de todos los períodos de una persona en esa institución, el nombre y apellido profesionales, el legajo y la matrícula, solo si la persona ya está desvinculada (`PERSONA_VIGENTE` en caso contrario) y si queda algo por eliminar (`DATOS_YA_ELIMINADOS`). Es irreversible; el vínculo, la autoría de mediciones y la auditoría se conservan sin identificar a la persona.
- **Evidencia:** S: `backend/app/services/personnel.py:328-360`; API: `backend/app/api/v1/institutions.py:318-336`; Pr: `test_account_lifecycle.py`.
- **Estado:** IMPLEMENTADO.
