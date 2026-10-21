# 04 — Requerimientos no funcionales de GlucoLume

**Relevamiento por ingeniería inversa** · Etapa 4 · 21 de octubre de 2026.

Este documento reúne los atributos de calidad y las restricciones tecnológicas que el proyecto respalda con código, configuración o pruebas. Para cada requerimiento se distinguen tres cosas que no deben confundirse:

1. **Implementado:** existe el código o la configuración que lo sustenta.
2. **Probado:** hay pruebas automatizadas que lo ejercitan (el resultado de su ejecución se informa en `07_RESUMEN_EJECUTIVO.md`).
3. **Medido:** existe una medición con resultado numérico, realizada sobre el sistema. Una configuración relacionada con el rendimiento, la seguridad o la disponibilidad **no** demuestra por sí sola que el requisito se cumpla.

## Convenciones

- **Criterio de aceptación:** condición verificable que permitiría dar por cumplido el requerimiento.
- **Respaldo:** código, configuración o script, con archivo y línea de la lectura del 21 de octubre de 2026.
- **Verificación disponible:** pruebas automatizadas del repositorio o evidencias documentadas. Una evidencia documentada en `docs/` pero que no puede reproducirse desde el repositorio se indica como «declarada», porque no pudo verificarse en esta revisión.
- **Estado:** IMPLEMENTADO, PARCIAL, PREVISTO, OBSOLETO o NO VERIFICADO (definidos en `01_INVENTARIO_MODULOS.md`, sección 1.3). Un requerimiento puede estar IMPLEMENTADO sin estar medido: en ese caso la línea «Medición» lo aclara.

## Resumen

| Categoría | RNF | Cantidad |
|---|---|---|
| Seguridad | RNF-001 a RNF-016 | 16 |
| Privacidad | RNF-017 a RNF-019 | 3 |
| Rendimiento | RNF-020 a RNF-023 | 4 |
| Disponibilidad | RNF-024 a RNF-027 | 4 |
| Integridad | RNF-028 a RNF-031 | 4 |
| Trazabilidad | RNF-032 a RNF-033 | 2 |
| Mantenibilidad | RNF-034 a RNF-037 | 4 |
| Usabilidad y accesibilidad | RNF-038 a RNF-041 | 4 |
| Interoperabilidad | RNF-042 a RNF-044 | 3 |
| Compatibilidad | RNF-045 a RNF-046 | 2 |
| Escalabilidad | RNF-047 a RNF-048 | 2 |
| Despliegue y operación | RNF-049 a RNF-051 | 3 |
| Recuperación | RNF-052 a RNF-053 | 2 |
| Cumplimiento normativo | RNF-054 | 1 |
| **Total** | | **54** |

---

## Seguridad

### RNF-001 — Las contraseñas se almacenan con Argon2id
- **Categoría:** seguridad.
- **Descripción:** el sistema guarda únicamente un hash Argon2id con sal propia por contraseña, con rehash automático cuando los parámetros cambian, y verifica en tiempo comparable incluso cuando la cuenta no existe.
- **Criterio de aceptación:** ninguna columna almacena contraseñas en claro; `CredencialLocal.passwordHash` contiene un hash con el identificador `$argon2id$`; verificar una contraseña de una cuenta inexistente consume un tiempo equivalente a verificar una real.
- **Respaldo:** `backend/app/core/security.py:42-44,132-143`.
- **Verificación disponible:** no hay una prueba automatizada que compruebe el formato del hash. La documentación declara los parámetros (64 MiB, 3 pasadas, 4 hilos; son los valores por defecto de la biblioteca) en `docs/SEGURIDAD.md`.
- **Medición:** no hay medición de tiempos.
- **Estado:** IMPLEMENTADO.

### RNF-002 — Los tokens de sesión son JWT con claims obligatorios y algoritmo fijado por configuración
- **Categoría:** seguridad.
- **Descripción:** el token de acceso se firma con un algoritmo HMAC elegido por configuración (nunca el que declara el token), con emisor y audiencia fijos, vigencia de 30 minutos y claims `exp`, `iat`, `sub` y `typ` obligatorios; el secreto debe tener al menos 32 caracteres.
- **Criterio de aceptación:** un token con otro algoritmo, tipo, emisor o audiencia se rechaza; un secreto de menos de 32 caracteres impide arrancar la aplicación.
- **Respaldo:** `backend/app/core/security.py:25-35,161-195`; `backend/app/core/config.py:17,56-58,146-165`.
- **Verificación disponible:** `test_security_config.py`, `test_auth_access.py`, `test_auth_access_flows.py`.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

### RNF-003 — Los secretos TOTP se cifran en reposo y admiten rotación de claves
- **Categoría:** seguridad.
- **Descripción:** el secreto de cada factor TOTP se guarda cifrado con Fernet; el cifrado usa la clave vigente y el descifrado admite claves anteriores (`MFA_PREVIOUS_ENCRYPTION_KEYS`) para rotar sin dejar sin MFA a nadie. En producción una clave inválida impide el arranque.
- **Criterio de aceptación:** `FactorMfa.secretoCifrado` no contiene el secreto en claro; tras rotar la clave, los factores existentes siguen verificando códigos; una clave Fernet inválida en producción aborta el arranque.
- **Respaldo:** `backend/app/core/security.py:278-307`; `backend/app/core/config.py:67-71,277-284`; `backend/app/cli/mfaKeys.py`.
- **Verificación disponible:** `test_security_config.py`, `test_mfa_flow.py`, `test_account_deletion.py`.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

### RNF-004 — Los tokens y códigos se guardan solo como hash
- **Categoría:** seguridad.
- **Descripción:** los tokens opacos (renovación, verificación, activación, eliminación, recuperación) se generan con 48 bytes aleatorios y se guardan como SHA-256; los códigos cortos de 6 dígitos se guardan como HMAC-SHA256 con una clave derivada con HKDF del secreto del servidor y ligada al usuario y al token; los códigos de recuperación de MFA se guardan con hash.
- **Criterio de aceptación:** ninguna tabla contiene un token ni un código utilizable en claro; un volcado de la base no permite reconstruir códigos de 6 dígitos.
- **Respaldo:** `backend/app/core/security.py:146-155,228-248,346-348`; `models/accountToken.py`, `models/mfaRecoveryCode.py`.
- **Verificación disponible:** `test_mfa_recovery.py`, `test_account_deletion.py`, `test_google_exchange.py`.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

### RNF-005 — Control de abuso por cuenta, por IP y en el perímetro
- **Categoría:** seguridad.
- **Descripción:** hay tres capas independientes: bloqueo por cuenta (contraseña y MFA), límites de solicitudes por IP en los puntos públicos (429 con `Retry-After`) y un tope de Nginx de 30 pedidos por segundo con ráfaga de 60 sobre `/api/v1/auth/`.
- **Criterio de aceptación:** el cuarto intento fallido de contraseña seguido devuelve bloqueo; superar el tope de un punto público devuelve 429 con `Retry-After`; el tope de Nginx responde 429.
- **Respaldo:** `backend/app/api/rateLimit.py:23-87`; `backend/app/services/auth.py:61,392-591`; `backend/app/services/mfa.py:26`; `docker/nginx/default.conf.template` (zona `auth_zone`).
- **Verificación disponible:** `test_login_lockout.py`, `test_rate_limiter.py`, `test_security_hardening.py`, `test_mfa_attempts_atomic.py`. El tope de Nginx no tiene prueba automatizada.
- **Medición:** no hay una prueba de carga que demuestre el comportamiento bajo ataque distribuido. Los contadores por IP del backend viven en memoria (ver RNF-047).
- **Estado:** IMPLEMENTADO.

### RNF-006 — La autorización se centraliza en el backend y lo ajeno responde «inexistente»
- **Categoría:** seguridad.
- **Descripción:** todos los permisos se resuelven en el servidor con el estado de la base (vínculo activo, institución activa, rol, asignación vigente). Para quien no pertenece a un ámbito, el recurso responde como inexistente, y el cliente nunca decide roles, matrices, responsables ni identificadores de otros usuarios.
- **Criterio de aceptación:** una cuenta sin vínculo recibe «no encontrada» al pedir una institución, un grupo, un paciente, un dispositivo, una matriz o una medición ajenos; un operador sin asignación vigente no accede a mediciones de un paciente aunque conozca su identificador.
- **Respaldo:** `backend/app/services/institution.py:263-292`, `group.py:162-179`, `patientAccess.py`, `device.py:162-172`, `matrix.py:108-135`, `measurement.py:139-169`.
- **Verificación disponible:** `test_operator_scope.py`, `test_patient_access.py`, `test_institutions.py`, `test_groups.py`, `test_device_context_authority.py`, `test_matrices_institucion.py`.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

### RNF-007 — Entradas validadas de forma estricta y acceso a datos parametrizado
- **Categoría:** seguridad.
- **Descripción:** los esquemas de entrada rechazan campos desconocidos, tipifican enumeraciones e identificadores y acotan longitudes y páginas; el acceso a la base usa SQLAlchemy con parámetros, con escape en las búsquedas por texto.
- **Criterio de aceptación:** un cuerpo con un campo no declarado responde error de validación; un valor de búsqueda con comodines o comillas no altera la consulta.
- **Respaldo:** `backend/app/schemas/*.py` (`extra="forbid"`, `Field(max_length=…)`); `backend/app/services/institutionPatients.py:244-245` (`_escapeLike`).
- **Verificación disponible:** `test_security_hardening.py`, `test_measurements.py`, `test_audit.py`.
- **Medición:** no hay un análisis automatizado de inyección (la documentación declara una comprobación con cargas de prueba).
- **Estado:** IMPLEMENTADO.

### RNF-008 — Cabeceras de seguridad HTTP en la API y en el perímetro
- **Categoría:** seguridad.
- **Descripción:** la API agrega `X-Content-Type-Options: nosniff` a todo y, bajo `/api/`, `Cache-Control: no-store`, `Referrer-Policy: no-referrer` y una política CSP que no permite cargar nada; HSTS solo en producción y sobre HTTPS. Nginx agrega además `X-Frame-Options: DENY`, `Permissions-Policy` sin cámara, micrófono ni geolocalización y una CSP sin `'unsafe-inline'`.
- **Criterio de aceptación:** una respuesta de `/api/…` incluye `Cache-Control: no-store` y la CSP indicada; HSTS no aparece en desarrollo ni sobre HTTP.
- **Respaldo:** `backend/app/api/securityHeaders.py:7-45`; `docker/nginx/default.conf.template` (bloque `server`).
- **Verificación disponible:** `test_security_hardening.py` (API). Las cabeceras de Nginx no tienen prueba en el repositorio (la documentación declara una verificación del 19/10/2026).
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

### RNF-009 — CORS restringido y API sin cookies de sesión
- **Categoría:** seguridad.
- **Descripción:** solo se admite el origen configurado del frontend, con métodos y cabeceras acotados, sin credenciales; la autenticación viaja en la cabecera `Authorization`. La cookie de estado de OAuth es firmada, `SameSite=Lax`, de 10 minutos y `Secure` en producción.
- **Criterio de aceptación:** una petición con `Origin` distinto no recibe cabeceras CORS de aprobación; la API no emite cookies de sesión.
- **Respaldo:** `backend/app/main.py:56-90`.
- **Verificación disponible:** `test_google_exchange.py` (cookie de estado), `test_security_hardening.py`.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

### RNF-010 — Transporte cifrado hacia SQL Server, SMTP y los clientes
- **Categoría:** seguridad.
- **Descripción:** la conexión a SQL Server exige cifrado y verifica el certificado salvo en desarrollo (en producción no admite `TrustServerCertificate`); el envío por SMTP usa STARTTLS con verificación de certificado y nombre y TLS 1.2 o superior; el tráfico de clientes usa HTTPS con HSTS mediante Caddy en producción.
- **Criterio de aceptación:** una configuración de producción con `DB_TRUST_SERVER_CERTIFICATE=true` no arranca; el contexto TLS de SMTP verifica el certificado y rechaza TLS anteriores a 1.2.
- **Respaldo:** `backend/app/db/session.py:35-51`; `backend/app/core/config.py:262-267`; `backend/app/integrations/email/sender.py:31-40`; `compose.prod.yaml` (perfil `https`); `docker/caddy/Caddyfile`.
- **Verificación disponible:** `test_security_config.py`, `test_register_contact.py`, `test_connection.py`. La conexión TLS real a SQL Server no se prueba en el repositorio.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

### RNF-011 — Gestión segura de secretos y validación de la configuración al arrancar
- **Categoría:** seguridad.
- **Descripción:** los archivos con secretos (`.env`, `docker/db.env`, `acquisition/bridge/bridge.env`) están excluidos del control de versiones y solo se versionan plantillas; los errores de validación no muestran el valor recibido; en producción no arranca con secretos repetidos entre variables, un secreto de sesión corto o una clave Fernet inválida; las advertencias de configuración mencionan solo nombres de variables.
- **Criterio de aceptación:** `git ls-files` no contiene archivos `.env` con valores; arrancar con `API_ENV=production` y dos variables con el mismo secreto aborta.
- **Respaldo:** `.gitignore:100-102`; `backend/app/core/config.py:25-29,214-284`.
- **Verificación disponible:** `test_security_config.py`. Se verificó sin abrirlos que los archivos de secretos reales no están versionados.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

### RNF-012 — Endurecimiento de los contenedores
- **Categoría:** seguridad.
- **Descripción:** los contenedores corren sin privilegios (usuario sin root), con sistema de archivos de solo lectura y `tmpfs`, sin capacidades (`cap_drop: ALL`), con `no-new-privileges`, límites de CPU y memoria y redes separadas (`edge` y `data`); el backend y la base no publican puertos.
- **Criterio de aceptación:** `docker compose config` muestra esas opciones para backend, frontend y `lifecycle`; los puertos publicados son solo los del frontend.
- **Respaldo:** `compose.yaml:23-30,33-135`; `backend/Dockerfile:50-65`.
- **Verificación disponible:** sin prueba automatizada. La documentación declara una comprobación con contenedores en ejecución el 19/10/2026 (`docs/SEGURIDAD.md`), no reproducible desde el repositorio.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO (verificación declarada, no reproducida).

### RNF-013 — Cadena de suministro controlada
- **Categoría:** seguridad.
- **Descripción:** las imágenes base se fijan por digest; las dependencias de Python se instalan con `--require-hashes` y las de Node con `package-lock.json`; el proyecto conserva una línea base de vulnerabilidades de imágenes y registra las decisiones.
- **Criterio de aceptación:** reconstruir la imagen del backend instala exactamente las versiones con hash del lock; no hay etiquetas `latest` en producción.
- **Respaldo:** `backend/Dockerfile:11-20`; `compose.prod.yaml:11-12`; `backend/requirements.txt`; `frontend/package-lock.json`; `docs/evidencias/CVE_LINEA_BASE_2026-10-10.md`.
- **Verificación disponible:** declarada (`pip-audit` y `npm audit` con cero vulnerabilidades conocidas el 19/10/2026, según `docs/SEGURIDAD.md`). `docs/PENDIENTES.md` registra una vulnerabilidad alta de `zlib` sin parche. No se ejecutaron escaneos en esta revisión.
- **Medición:** la línea base de 10/10/2026 es evidencia histórica de las imágenes originales, no del estado actual.
- **Estado:** IMPLEMENTADO (escaneos declarados, no reproducidos).

### RNF-014 — Mínimo privilegio en la base de datos
- **Categoría:** seguridad.
- **Descripción:** la API usa una cuenta con lectura y escritura sin permisos de cambio de esquema; un script opcional separa una cuenta de conservación y deniega a la cuenta de la API el UPDATE y el DELETE sobre la auditoría; Docker nunca crea ni modifica esquemas.
- **Criterio de aceptación:** con el script aplicado, un UPDATE de la cuenta de la API sobre `Auditoria` falla; la API no puede ejecutar DDL.
- **Respaldo:** `database/reference/GlucoLume_permisos.sql`, `GlucoLume_permisos_verificar.sql`, `GlucoLume_permisos_revertir.sql`; `backend/app/core/config.py:48-53,229-231`; `compose.yaml:50-52`.
- **Verificación disponible:** el script está documentado como ensayado en una instancia descartable; no hay constancia en el repositorio de que esté aplicado en la base real (`docs/SEGURIDAD.md` lo lista como procedimiento preparado que requiere autorización).
- **Medición:** no aplica.
- **Estado:** PARCIAL (preparado; su aplicación en la base real no está verificada).

### RNF-015 — Autenticación del puente serie con token propio
- **Categoría:** seguridad.
- **Descripción:** el puente se autentica con un token compartido de al menos 32 caracteres, comparado en tiempo constante, con rotación sin corte y bloqueo de la IP tras 20 fallos en 10 minutos; el puente rechaza usar HTTP fuera de `localhost` salvo opción expresa.
- **Criterio de aceptación:** una petición sin el token o con un token incorrecto es rechazada; 20 fallos seguidos bloquean a esa IP aunque luego acierte.
- **Respaldo:** `backend/app/core/config.py:102-106,153-158`; `backend/app/api/rateLimit.py:42-45`; `acquisition/bridge/glucolume_bridge.py:1-30`.
- **Verificación disponible:** `test_bridge.py`, `test_bridge_runtime.py`, `test_security_config.py`.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

### RNF-016 — Sin enumeración de cuentas por mensajes ni por tiempo
- **Categoría:** seguridad.
- **Descripción:** el inicio de sesión, la recuperación de contraseña, el reenvío de verificación y la verificación de códigos responden igual exista o no la cuenta; el inicio de sesión iguala el tiempo con un hash ficticio.
- **Criterio de aceptación:** las respuestas y el código de estado para una cuenta existente y una inexistente son idénticos en esos flujos.
- **Respaldo:** `backend/app/services/auth.py:281-314,522-549,947-958`; `backend/app/core/security.py:141-143`.
- **Verificación disponible:** `test_auth_access.py`, `test_password_recovery.py`, `test_register_contact.py`.
- **Medición:** no hay medición de diferencia de tiempos entre los casos.
- **Estado:** IMPLEMENTADO.

## Privacidad

### RNF-017 — Minimización de datos en auditoría, registros técnicos y correos
- **Categoría:** privacidad.
- **Descripción:** la auditoría descarta claves sensibles y no guarda valores personales ni de salud en los campos previos y nuevos; los correos usan asuntos genéricos y se muestran enmascarados; los registros técnicos no incluyen contexto de correos, tokens ni códigos; el identificador escrito en un acceso a una cuenta inexistente se guarda solo como HMAC.
- **Criterio de aceptación:** un evento con un campo `password` o `token` se guarda con `[omitido]`; ningún asunto de correo contiene valores de mediciones.
- **Respaldo:** `backend/app/services/audit.py:70-86,200-205`; `backend/app/services/email.py:30-40`; `backend/app/emails/formatting.py` (`maskEmail`).
- **Verificación disponible:** `test_audit.py`, `test_emails.py`, `test_audit_security.py`, `test_login_email_no_ip.py`.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

### RNF-018 — Cifrado en reposo de la base y de los respaldos
- **Categoría:** privacidad.
- **Descripción:** hay un procedimiento para activar TDE y respaldos cifrados con restauración de prueba. La base instalada es SQL Server 2025 Express, que no admite TDE ni respaldos cifrados; la alternativa documentada es cifrar el volumen y el archivo de respaldo.
- **Criterio de aceptación:** la base y los respaldos se almacenan cifrados (TDE o cifrado de volumen verificado).
- **Respaldo:** `database/reference/GlucoLume_cifrado_y_respaldo.sql:1-30`; `database/respaldos/*.ps1`; `docs/BASE_DE_DATOS.md`.
- **Verificación disponible:** el procedimiento figura como ensayado el 19/10/2026 en una instancia descartable; no está aplicado en la base real (`docs/PENDIENTES.md`).
- **Medición:** no aplica.
- **Estado:** PARCIAL (preparado; sin cifrado en reposo verificado en la instalación real).

### RNF-019 — Sin analítica ni servicios de terceros en el frontend
- **Categoría:** privacidad.
- **Descripción:** el frontend no incluye scripts de analítica ni de terceros; las únicas integraciones externas son Google (acceso) y SMTP (correo). La CSP restringe los orígenes a `'self'`.
- **Criterio de aceptación:** el paquete del frontend no declara dependencias de analítica y la CSP no admite orígenes externos.
- **Respaldo:** `frontend/package.json` (dependencias: React, React Router, Lucide, qrcode.react); `docker/nginx/default.conf.template` (CSP).
- **Verificación disponible:** estática (lectura de dependencias y CSP). La CSP más permisiva de `/docs` aplica solo fuera de producción.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

## Rendimiento

### RNF-020 — Control del volumen de datos leídos y devueltos
- **Categoría:** rendimiento.
- **Descripción:** las consultas paginan con topes (50 por página en historiales y pacientes, 100 en dispositivos y reasignaciones), las series se limitan (1000 puntos de evolución, 500 de estadísticas compartidas, 5000 intentos de seguridad, 400 eventos de actividad) y las agregaciones se resuelven en SQL; existen índices de consulta para la auditoría y las mediciones.
- **Criterio de aceptación:** ninguna lista devuelve más registros que su tope; una consulta de gran volumen informa que fue truncada.
- **Respaldo:** `backend/app/services/measurement.py:110,823-824`, `group.py:80-83`, `institutionPatients.py:77`, `securityDetection.py:30`, `institutionActivity.py:35-37`; índices `IX_Auditoria_*`, `IX_Medicion_*` en `GlucoLume_DB_v5.sql` del commit (ver H-01 en `06`).
- **Verificación disponible:** `test_measurements.py`, `test_groups.py`, `test_patient_analytics.py`.
- **Medición:** no hay medición de tiempos ni de consumo de recursos.
- **Estado:** IMPLEMENTADO (control de volumen; sin medición de rendimiento).

### RNF-021 — Objetivos de tiempo de respuesta y capacidad
- **Categoría:** rendimiento.
- **Descripción:** el proyecto no define objetivos de tiempo de respuesta, de usuarios concurrentes ni de volumen de mediciones, y no contiene pruebas de carga ni de rendimiento.
- **Criterio de aceptación (propuesto, no vigente):** a definir por el equipo, por ejemplo percentil 95 de respuesta de los endpoints principales bajo una carga dada.
- **Respaldo:** ninguno (búsqueda de pruebas de carga, *benchmarks* y objetivos en el repositorio sin resultados).
- **Verificación disponible:** ninguna.
- **Medición:** ninguna.
- **Estado:** PREVISTO (no definido).

### RNF-022 — Tope de conexiones de transmisión en vivo
- **Categoría:** rendimiento.
- **Descripción:** las transmisiones SSE tienen un máximo de 6 por cuenta y 300 en total, con apertura que responde 429 al superarse, revalidación de la sesión cada 30 segundos y liberación de la conexión de base de datos antes de transmitir.
- **Criterio de aceptación:** la séptima transmisión de una cuenta recibe 429; una sesión revocada termina su transmisión en el siguiente control.
- **Respaldo:** `backend/app/api/streams.py:1-40,87-96`; `backend/app/api/deps.py:49-61`.
- **Verificación disponible:** `test_stream_limits.py`.
- **Medición:** no hay medición de capacidad real (los topes son del proceso).
- **Estado:** IMPLEMENTADO.

### RNF-023 — Tamaño de entrega del frontend y recursos de los contenedores
- **Categoría:** rendimiento.
- **Descripción:** el frontend carga de forma diferida las pantallas de plataforma, matrices, auditoría, dispositivos, analítica, grupos y otras; los recursos con hash se cachean un año y el `index.html` no se cachea; los contenedores tienen límites de CPU y memoria.
- **Criterio de aceptación:** el paquete inicial no supera un tamaño fijado por el equipo (no hay umbral fijado); las pantallas de carga diferida se descargan al visitarlas.
- **Respaldo:** `frontend/src/App.jsx:60-90` (carga diferida); `docker/nginx/default.conf.template` (caché de `/assets/` y `index.html`); `compose.yaml` (límites).
- **Verificación disponible:** declarada en `docs/FRONTEND.md` (paquete inicial de 887 kB, sobre el aviso de 500 kB de Vite). No se ejecutó la compilación en esta revisión.
- **Medición:** declarada, no reproducida.
- **Estado:** PARCIAL (implementado; el tamaño excede el aviso del compilador y no hay umbral definido).

## Disponibilidad

### RNF-024 — Comprobación de vida independiente de la base y reinicio automático
- **Categoría:** disponibilidad.
- **Descripción:** `GET /healthz` informa que la API responde sin consultar la base, para que una caída de SQL Server no reinicie el contenedor en bucle; los contenedores tienen verificaciones de salud y política de reinicio; Nginx resuelve el destino en cada pedido, de modo que el frontend sirve aunque el backend caiga.
- **Criterio de aceptación:** con SQL Server detenido, `/healthz` responde 200; con el backend caído, el frontend sigue sirviendo la aplicación.
- **Respaldo:** `backend/app/main.py:52-55`; `compose.yaml` (`healthcheck`, `restart`); `docker/nginx/default.conf.template`.
- **Verificación disponible:** `test_security_hardening.py` (respuesta de `/healthz`).
- **Medición:** no se midió la recuperación ante fallas.
- **Estado:** IMPLEMENTADO.

### RNF-025 — Degradación controlada ante fallas de dependencias
- **Categoría:** disponibilidad.
- **Descripción:** el sistema evita caerse por: correo que falla (los avisos se envían después de confirmar y un error no revierte la operación); base no migrada (las columnas nuevas se comprueban antes de usarse y se informa un mensaje de esquema desactualizado); puntos muertos de SQL Server (reintento acotado); Google o SMTP no configurados (se deshabilitan con una advertencia).
- **Criterio de aceptación:** con SMTP caído, crear una institución o guardar una medición se completa; con una columna de la migración ausente, la funcionalidad dependiente responde un mensaje explícito y el resto sigue.
- **Respaldo:** `backend/app/services/schemaCompat.py:1-30`; `backend/app/utils/dbRetry.py`; `backend/app/main.py:41-52`; `backend/app/services/notifications.py:1-15`.
- **Verificación disponible:** `test_emails.py`, `test_quota.py`, `test_glucose_mode.py`, `test_lifecycle_concurrency.py`; evidencia de los puntos muertos reales en `docs/evidencias/PRUEBAS_CONCURRENCIA_SQLSERVER_2026-10-16.md`.
- **Medición:** la evidencia de concurrencia (480 de 480 y 560 de 560 comprobaciones correctas) se obtuvo sobre un esquema anterior ya retirado; es histórica.
- **Estado:** IMPLEMENTADO.

### RNF-026 — Continuidad de la adquisición ante cortes del enlace
- **Categoría:** disponibilidad.
- **Descripción:** el puente se reconecta con espera progresiva (1, 2, 4… hasta 30 segundos), conserva hasta 1000 líneas si el servidor no responde y las reenvía sin duplicar gracias a un número de secuencia; el servidor libera las sesiones abandonadas del dispositivo.
- **Criterio de aceptación:** un corte de red de hasta 16 minutos no pierde lecturas; una sesión sin actividad se libera.
- **Respaldo:** `acquisition/bridge/glucolume_bridge.py:1-60`; `backend/app/acquisition/telemetry.py:81-88`; `backend/app/services/maintenance.py`.
- **Verificación disponible:** `test_bridge_runtime.py`, `test_bridge.py`, `test_device_control.py`.
- **Medición:** sin hardware real (`docs/PENDIENTES.md`: «verificar con el Arduino real»).
- **Estado:** IMPLEMENTADO en software; NO VERIFICADO en hardware.

### RNF-027 — Objetivo de disponibilidad y tolerancia a fallas
- **Categoría:** disponibilidad.
- **Descripción:** no hay objetivo de disponibilidad (porcentaje, ventana de mantenimiento) ni redundancia: el diseño prevé una sola instancia del backend y de SQL Server.
- **Criterio de aceptación (propuesto, no vigente):** a definir por el equipo.
- **Respaldo:** ninguno.
- **Verificación disponible:** ninguna.
- **Medición:** ninguna.
- **Estado:** PREVISTO (no definido).

## Integridad

### RNF-028 — Integridad referencial y de dominio definida en la base
- **Categoría:** integridad.
- **Descripción:** el esquema define 49 claves foráneas, 125 restricciones CHECK, 16 restricciones UNIQUE y valores por defecto, y los modelos replican las restricciones; índices únicos filtrados garantizan reglas como un solo administrador del sistema, un grupo activo por cuenta o una matriz activa por ámbito.
- **Criterio de aceptación:** todo estado inválido (por ejemplo una medición completada sin glucosa trazable o un vínculo activo sin fecha de incorporación) es rechazado por la base; `DBCC CHECKCONSTRAINTS` no informa violaciones.
- **Respaldo:** `database/reference/GlucoLume_DB_v5.sql`; `backend/app/models/*.py`.
- **Verificación disponible:** `test_reference_schema.py` compara los modelos con el texto del script; el contrato de los índices únicos filtrados se prueba en los comportamientos de grupos, matrices e instituciones. **La versión del script sin confirmar en la copia de trabajo no contiene ninguno de los 15 índices únicos filtrados ni los 16 índices de consulta que sí figuran en el commit** (ver H-01 en `06`).
- **Medición:** la verificación de integridad posterior a las pruebas de concurrencia del 16/10/2026 informó cero violaciones (evidencia histórica, esquema anterior).
- **Estado:** PARCIAL (esquema completo en el commit; la copia de trabajo actual perdió los índices).

### RNF-029 — Atomicidad y consistencia ante concurrencia
- **Categoría:** integridad.
- **Descripción:** las transiciones de estado críticas se hacen con actualizaciones condicionadas al estado esperado, bloqueos de fila (`UPDLOCK`) en operaciones que compiten (eliminación automática de cuentas, bajas de operadores, incorporaciones y cupos), reintento acotado ante puntos muertos y verificaciones previas y posteriores a la escritura dentro de la misma transacción.
- **Criterio de aceptación:** dos solicitudes simultáneas aplican una sola vez la misma transición; nunca quedan cero ni dos administradores, ni cupos excedidos por una incorporación concurrente.
- **Respaldo:** `backend/app/services/accountGrace.py:62-122`, `quota.py:70-97`, `measurement.py:346-352`, `institution.py:240-250`, `utils/dbRetry.py`.
- **Verificación disponible:** `test_lifecycle_concurrency.py`, `test_mfa_attempts_atomic.py`, `lifecycle_concurrency.py` (requiere una base SQL Server descartable) y la evidencia de `docs/evidencias/PRUEBAS_CONCURRENCIA_SQLSERVER_2026-10-16.md`.
- **Medición:** la evidencia de concurrencia sobre SQL Server es del 16/10/2026 y se obtuvo con un esquema anterior (`v2` más scripts incrementales, ya retirados); no se repitió con el esquema v5 en esta revisión.
- **Estado:** IMPLEMENTADO (evidencia de SQL Server histórica).

### RNF-030 — Política temporal única: hora de Argentina
- **Categoría:** integridad.
- **Descripción:** toda fecha y hora generada por el backend se obtiene de un único módulo y se guarda en hora de Argentina (UTC-03:00) sin zona; los valores devueltos al cliente se marcan con su zona cuando corresponde. Algunas columnas con valor por defecto en SQL Server usan UTC, y el código convive con esa diferencia.
- **Criterio de aceptación:** ningún módulo usa `datetime.now()` directo; las comparaciones de plazos usan la misma referencia temporal.
- **Respaldo:** `backend/app/utils/timeZone.py:1-40`; `backend/app/services/auth.py:236` (comentario sobre columnas con UTC).
- **Verificación disponible:** `test_audit_security.py`, `test_account_lifecycle.py` y la mayoría de las pruebas usan el mismo módulo.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO (con la excepción documentada de las columnas con valor por defecto en UTC).

### RNF-031 — La auditoría es de solo inserción desde la aplicación
- **Categoría:** integridad.
- **Descripción:** ningún servicio ni ruta de la API modifica ni borra `Auditoria` ni `AuditoriaContexto`; solo la conservación programada, con su propia cuenta de base, puede depurarla.
- **Criterio de aceptación:** una búsqueda de `UPDATE` o `DELETE` sobre esas tablas en el código de la API no encuentra coincidencias fuera de `auditRetention.py`; con el script de permisos aplicado, la cuenta de la API no puede modificarla.
- **Respaldo:** `backend/app/services/audit.py:1-18`; `backend/app/services/auditRetention.py`; `database/reference/GlucoLume_permisos.sql`.
- **Verificación disponible:** `test_audit_security.py` (según `docs/SEGURIDAD.md`, una prueba global falla si otro código modifica la auditoría).
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO en código; la restricción en la base depende de aplicar el script (ver RNF-014).

## Trazabilidad

### RNF-032 — Registro de eventos con correlación de solicitudes
- **Categoría:** trazabilidad.
- **Descripción:** cada solicitud recibe un identificador de correlación (propio de Nginx, el del cliente se descarta) que se devuelve en `X-Request-ID` y se guarda, junto con la IP y el cliente, en el contexto de cada evento de auditoría; los eventos registran quién, qué, sobre qué entidad, resultado y motivo normalizado.
- **Criterio de aceptación:** dado un `X-Request-ID` de una respuesta, es posible localizar los eventos de auditoría de esa solicitud.
- **Respaldo:** `backend/app/api/requestContext.py`; `backend/app/core/requestContext.py`; `backend/app/services/audit.py:218-284`; `docker/nginx/default.conf.template` (`X-Request-ID`).
- **Verificación disponible:** `test_audit_security.py`.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

### RNF-033 — Trazabilidad del origen de cada valor medido
- **Categoría:** trazabilidad.
- **Descripción:** cada medición conserva la versión del firmware, el modelo de sensor, la matriz, la regla aplicada, la versión del algoritmo, el origen de la glucosa y la edad y el sexo del momento, y toda glucosa estimada exige matriz y versión de algoritmo.
- **Criterio de aceptación:** dada una medición completada, se puede identificar con qué dispositivo, firmware, sensor, matriz y algoritmo se obtuvo, sin recalcularla.
- **Respaldo:** `backend/app/models/measurement.py:14-95`; `backend/app/services/measurement.py:319-338`; `backend/app/services/telemetry.py:56`.
- **Verificación disponible:** `test_measurements.py`, `test_glucose_mode.py`, `test_measurement_profile.py`.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

## Mantenibilidad

### RNF-034 — Arquitectura en capas y documentación en el código
- **Categoría:** mantenibilidad.
- **Descripción:** el backend separa rutas (`api/v1`), servicios, modelos, esquemas, núcleo y utilidades; cada módulo de servicio tiene un encabezado que explica sus reglas, alcance y decisiones; el frontend separa páginas, componentes, acceso a la API y utilidades. Los nombres de archivos y símbolos son coherentes (camelCase).
- **Criterio de aceptación:** un servicio nuevo sigue la estructura existente y su encabezado describe reglas y alcance.
- **Respaldo:** estructura de `backend/app/**` y `frontend/src/**`.
- **Verificación disponible:** inspección. Hay referencias a documentos que no existen en el repositorio (`docs/DOCKER.md`, `docs/AUDITORIA_ADMINISTRATIVA.md`, `docs/RETENCION_Y_ANONIMIZACION.md`, `docs/PRIVACIDAD.md`; ver H-06 en `06`) y comentarios desactualizados (ver H-03 y H-15).
- **Medición:** no hay métricas de complejidad ni de cobertura.
- **Estado:** IMPLEMENTADO.

### RNF-035 — Suite de pruebas automatizadas aislada de los sistemas reales
- **Categoría:** mantenibilidad.
- **Descripción:** hay 99 archivos de pruebas de backend con 1468 funciones `test_` y 50 archivos de frontend con 646 casos; las pruebas de backend usan SQLite y un archivo de configuración con valores ficticios y SMTP inexistente, y nunca alcanzan la base ni el correo reales; las pruebas contra SQL Server exigen una base descartable con confirmación expresa.
- **Criterio de aceptación:** `python -m pytest` en `backend/` y `npm test` en `frontend/` finalizan sin fallas y sin tocar sistemas externos.
- **Respaldo:** `backend/tests/conftest.py`, `backend/tests/test.env`; `frontend/package.json` (`vitest`).
- **Verificación disponible:** el resultado de la ejecución del backend en esta revisión figura en `07_RESUMEN_EJECUTIVO.md`; el de frontend no se ejecutó.
- **Medición:** no hay medición de cobertura de código.
- **Estado:** IMPLEMENTADO.

### RNF-036 — Detección de diferencias entre la base instalada y el esquema esperado
- **Categoría:** mantenibilidad.
- **Descripción:** el sistema incluye una herramienta de solo lectura que compara catálogos de SQL Server con los modelos y una prueba que compara el script de referencia con los modelos; las migraciones las aplica un administrador de la base, no la aplicación.
- **Criterio de aceptación:** `python -m app.cli.schemaCheck` sale con 0 cuando no hay diferencias y con 1 cuando las hay, sin modificar nada.
- **Respaldo:** `backend/app/cli/schemaCheck.py:1-60`; `backend/tests/test_reference_schema.py`.
- **Verificación disponible:** `test_reference_schema.py`. La herramienta contra una base real no se ejecutó.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

### RNF-037 — Dependencias reproducibles
- **Categoría:** mantenibilidad.
- **Descripción:** las dependencias de Python se declaran en archivos `.in` y se compilan a `requirements.txt` con hashes; las de Node se fijan con `package-lock.json` y versiones exactas.
- **Criterio de aceptación:** una instalación limpia produce las mismas versiones.
- **Respaldo:** `backend/requirements.in`, `requirements.txt`, `requirements-dev.in`, `acquisition/requirements.in`; `frontend/package.json`, `package-lock.json`.
- **Verificación disponible:** estática.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

## Usabilidad y accesibilidad

### RNF-038 — Accesibilidad de la interfaz
- **Categoría:** accesibilidad.
- **Descripción:** la interfaz incluye enlace de omisión de navegación, un encabezado principal por pantalla, atributos ARIA en 171 archivos, contrastes de color definidos como tokens y componentes con pruebas de teclado y roles (pestañas, modales, enlace de omisión).
- **Criterio de aceptación:** las pantallas cumplen contraste de texto, tienen enlace «Saltar al contenido» y un solo `h1`; los componentes interactivos se operan con teclado.
- **Respaldo:** `frontend/src/components/SkipLink.jsx`, `Modal.jsx`, `Tabs.jsx`; estilos en `frontend/src/styles` y `*.css`.
- **Verificación disponible:** `SkipLink.test.jsx`, `Tabs.test.jsx`, `Modal.test.jsx`, `FormControls.test.jsx`. La documentación declara un barrido de 243 vistas (56 pantallas, tres anchos, cinco roles) con 0 fallas de contraste, pero realizado con herramientas externas al repositorio (`docs/FRONTEND.md`).
- **Medición:** declarada, no reproducible desde el repositorio. No se cita una conformidad formal con WCAG.
- **Estado:** IMPLEMENTADO (medición declarada, no reproducida).

### RNF-039 — Diseño adaptable a distintos tamaños de pantalla
- **Categoría:** usabilidad.
- **Descripción:** las hojas de estilo usan consultas de medios y la documentación declara una revisión a 1440, 768 y 390 píxeles sin desbordes horizontales a 390 px.
- **Criterio de aceptación:** ninguna pantalla produce desplazamiento horizontal a 390 px de ancho.
- **Respaldo:** `frontend/src/**/*.css` (`@media`), `frontend/index.html` (`viewport`).
- **Verificación disponible:** declarada en `docs/FRONTEND.md`.
- **Medición:** declarada, no reproducida.
- **Estado:** IMPLEMENTADO (medición declarada).

### RNF-040 — Mensajes en español con códigos de error estables
- **Categoría:** usabilidad.
- **Descripción:** todos los textos de la interfaz y de los errores están en español rioplatense; el backend devuelve códigos de error estables con mensaje, y el frontend traduce códigos a mensajes comprensibles sin exponer detalles técnicos; los errores no controlados devuelven el mensaje genérico del marco de trabajo.
- **Criterio de aceptación:** un error del servidor muestra un mensaje en español sin trazas ni mensajes de la base.
- **Respaldo:** `backend/app/api/errors.py:1-226`; `backend/app/core/exceptions.py`; `frontend/src/auth/errorMessages.js`.
- **Verificación disponible:** `client.test.js` y las pruebas de códigos de error de cada módulo; no se encontró una prueba específica del comportamiento ante un error 500.
- **Medición:** no hay evaluación de usabilidad con personas usuarias.
- **Estado:** IMPLEMENTADO.

### RNF-041 — Transparencia sobre el carácter experimental de los resultados
- **Categoría:** usabilidad.
- **Descripción:** la interfaz y los correos advierten que los resultados son experimentales y no reemplazan una medición clínica; el origen de cada glucosa (experimental, sin calibrar, DEMO) es siempre visible; los propios sketches del firmware declaran que el resultado no es apto para decisiones clínicas ni de dosificación de insulina.
- **Criterio de aceptación:** toda pantalla que muestra un valor de glucosa incluye el aviso y el origen.
- **Respaldo:** `frontend/src/components/ExperimentalNotice.jsx`, `pages/Account/measurements/GlucoseReferencePanel.jsx`, `MeasurementsInfo.jsx`; `firmware/GlucoLume_MAX30100/GlucoLume_MAX30100.ino:1-31`.
- **Verificación disponible:** `Measurements.test.jsx`, `Display.test.jsx`.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

## Interoperabilidad

### RNF-042 — API REST JSON versionada y documentada fuera de producción
- **Categoría:** interoperabilidad.
- **Descripción:** la API expone 241 endpoints REST con JSON bajo `/api/v1`, esquemas tipados y documentación OpenAPI/Swagger/ReDoc que se publica solo fuera de producción.
- **Criterio de aceptación:** con `API_ENV=development` existe `/openapi.json`; con `production` responde 404.
- **Respaldo:** `backend/app/main.py:36-50`; `backend/app/api/v1/*.py`.
- **Verificación disponible:** `test_security_hardening.py`.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

### RNF-043 — Integración con servicios y dispositivos externos
- **Categoría:** interoperabilidad.
- **Descripción:** el sistema se integra con Google OAuth 2.0 / OpenID Connect (estado, nonce y PKCE), con SMTP (STARTTLS), con SQL Server (ODBC Driver 18) y con el Arduino por USB (115200 baudios) o Bluetooth HC-05/HC-06 (9600 baudios) mediante un protocolo de texto documentado.
- **Criterio de aceptación:** las integraciones se pueden deshabilitar por configuración sin impedir el arranque (Google y SMTP).
- **Respaldo:** `backend/app/integrations/google/oauth.py`; `backend/app/integrations/email/sender.py`; `backend/app/db/session.py`; `backend/app/acquisition/protocol.py`.
- **Verificación disponible:** `test_google_exchange.py`, `test_emails.py`, `test_bridge.py`, `test_acquisition.py`. El intercambio real con Google y el SMTP real figuran como pendientes en `docs/PENDIENTES.md`.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO (integraciones reales no verificadas).

### RNF-044 — Transmisión en tiempo real mediante *Server-Sent Events*
- **Categoría:** interoperabilidad.
- **Descripción:** el estado y las lecturas del dispositivo se entregan por SSE (con configuración específica de Nginx sin búfer y tiempo de lectura de una hora).
- **Criterio de aceptación:** el navegador recibe eventos continuos sin que el proxy los almacene en búfer.
- **Respaldo:** `backend/app/api/v1/telemetry.py:157-203`; `docker/nginx/default.conf.template` (ubicación de `stream`).
- **Verificación disponible:** `test_stream_limits.py`, `test_telemetry.py`.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

## Compatibilidad

### RNF-045 — Plataforma tecnológica requerida
- **Categoría:** compatibilidad.
- **Descripción:** backend en Python 3.14 con FastAPI y SQLAlchemy; base SQL Server (esquema con tipos `DATETIME2` y `UNIQUEIDENTIFIER`, TDE desde la edición 2019 Standard); controlador ODBC 18; frontend en React 19.1, React Router 7 y Vite 6; firmware para Arduino UNO (ATmega328P) con sensor MAX30100 y pantalla I2C; el puente serie se ejecuta en Windows (el puerto COM no puede pasarse a un contenedor Linux). No se declara una lista de navegadores soportados.
- **Criterio de aceptación:** la aplicación arranca en el entorno descrito; el puente funciona en Windows.
- **Respaldo:** `backend/Dockerfile`; `backend/requirements.in`; `frontend/package.json`; `compose.yaml:11-16`; `acquisition/bridge/*.bat`.
- **Verificación disponible:** `test_connection.py`; no se probó en otros entornos. El uso de Python 3.14 y de versiones recientes de las bibliotecas no se cotejó con matrices de soporte.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO (restricciones tecnológicas; sin lista de navegadores).

### RNF-046 — Convivencia con bases de datos sin las últimas migraciones
- **Categoría:** compatibilidad.
- **Descripción:** el backend comprueba la existencia de las columnas y restricciones de las migraciones recientes (capacidad de cuentas, cierre administrativo, correo de resultados, retención, contexto de auditoría) antes de usarlas, de modo que actualizar el código no deja caídos los módulos mientras la base se migra.
- **Criterio de aceptación:** con una base sin una columna nueva, el módulo afectado responde un mensaje claro y las demás funciones siguen disponibles.
- **Respaldo:** `backend/app/services/schemaCompat.py`; `backend/app/models/institution.py:42-50`, `measurement.py:84-92`, `measurementProfile.py`.
- **Verificación disponible:** `test_quota.py`, `test_platform_institution_deletion.py`, `test_glucose_mode.py`, `test_auth_access_account_type.py`.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

## Escalabilidad

### RNF-047 — Escalabilidad horizontal limitada por estado en memoria
- **Categoría:** escalabilidad.
- **Descripción:** varios mecanismos guardan su estado en la memoria de un proceso: los límites de solicitudes por IP, el monitor de ráfagas de rechazos, los topes de transmisiones, los limitadores de búsquedas y de contacto, y todo el estado del dispositivo (sesión, lecturas en vivo, control y órdenes al puente). Con una sola réplica los límites son exactos; con varias, cada una cuenta por separado y el dispositivo no sería coherente entre réplicas.
- **Criterio de aceptación (para escalar):** un almacén compartido (por ejemplo Redis) o un único proceso responsable del estado del dispositivo.
- **Respaldo:** `backend/app/api/rateLimit.py:10-12`, `services/securityMonitor.py:1-25`, `api/streams.py:1-10`, `services/contact.py:34-60`, `acquisition/telemetry.py` (objeto `hub`); `docs/PENDIENTES.md` («el control vive en memoria»; «Redis… si hay más de una réplica»).
- **Verificación disponible:** `test_rate_limiter.py`, `test_stream_limits.py` (comportamiento de una instancia).
- **Medición:** ninguna.
- **Estado:** PARCIAL (diseño de una sola réplica; limitación documentada).

### RNF-048 — Capacidad configurable por institución
- **Categoría:** escalabilidad.
- **Descripción:** cada institución tiene un máximo de cuentas activas configurable por la plataforma (1000 por omisión, hasta 100 000), calculado sobre las relaciones vigentes sin contadores guardados.
- **Criterio de aceptación:** al llegar al máximo, la incorporación siguiente se rechaza con `CAPACIDAD_COMPLETA`.
- **Respaldo:** `backend/app/services/quota.py:1-100`; `backend/app/models/institution.py`.
- **Verificación disponible:** `test_quota.py`, `test_platform_institution_control.py`.
- **Medición:** no se midió el comportamiento con 1000 o más cuentas.
- **Estado:** IMPLEMENTADO.

## Despliegue y operación

### RNF-049 — Despliegue reproducible con contenedores
- **Categoría:** despliegue.
- **Descripción:** Docker Compose define los servicios, redes, volúmenes y perfiles (base opcional, compilación de firmware, HTTPS); producción exige imágenes versionadas y fuerza `API_ENV=production`; la base y los esquemas se preparan manualmente.
- **Criterio de aceptación:** `docker compose -f compose.yaml -f compose.prod.yaml up -d` levanta los servicios con la versión indicada o falla si falta `GLUCOLUME_VERSION`.
- **Respaldo:** `compose.yaml`, `compose.prod.yaml`, `compose.dev.yaml`, `compose.serial.yaml`, `docker/**`.
- **Verificación disponible:** sin prueba automatizada; la documentación (`docs/DESPLIEGUE.md`) describe el procedimiento. No se ejecutó Docker en esta revisión.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO (no verificado en esta revisión).

### RNF-050 — Configuración por variables de entorno con plantillas
- **Categoría:** despliegue.
- **Descripción:** toda la configuración se lee de variables de entorno o de un `.env`; hay plantillas `.env.example` (raíz, base de datos, frontend, puente) con comentarios; los valores vacíos usan el valor por defecto.
- **Criterio de aceptación:** copiar las plantillas y completar los valores permite arrancar; ninguna constante secreta está en el código.
- **Respaldo:** `.env.example`, `docker/db.env.example`, `frontend/.env.example`, `acquisition/bridge/bridge.env.example`; `backend/app/core/config.py`.
- **Verificación disponible:** `test_security_config.py`.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

### RNF-051 — Observabilidad básica
- **Categoría:** operación.
- **Descripción:** los contenedores escriben registros JSON con rotación (10 MB por 5 archivos); el backend registra con niveles y sin datos sensibles; el panel de plataforma muestra el estado de los componentes; el servicio `lifecycle` mantiene un latido para su verificación de salud. No hay recolección de métricas, trazas distribuidas ni alertas externas, más allá del aviso por correo ante ráfagas de rechazos.
- **Criterio de aceptación:** un fallo de un componente se refleja en el estado del sistema y en los registros.
- **Respaldo:** `compose.yaml:19-22`; `backend/app/main.py:30-34`; `backend/app/services/platformDashboard.py:213-290`; `backend/app/jobs/accountLifecycle.py` (latido).
- **Verificación disponible:** `test_platform_dashboard.py`.
- **Medición:** no aplica.
- **Estado:** PARCIAL (registros y estado de componentes; sin métricas ni alertas externas).

## Recuperación

### RNF-052 — Respaldo y restauración de la base de datos
- **Categoría:** recuperación.
- **Descripción:** existen scripts para generar un respaldo cifrado con restauración de prueba y verificación de filas, y para guardar la clave del respaldo; la política de retención propuesta (diarios 35 días, mensuales 12 meses, restauración de prueba mensual) está pendiente de aprobación. La instalación indicada es SQL Server Express, que no admite respaldos cifrados ni comprimidos. No hay objetivos de punto ni de tiempo de recuperación definidos.
- **Criterio de aceptación:** un respaldo se restaura en una instancia de prueba y las cantidades de filas coinciden con el original; existen objetivos de recuperación aprobados.
- **Respaldo:** `database/respaldos/GlucoLume_respaldo.ps1`, `GlucoLume_prueba_restauracion.ps1`, `GlucoLume_clave_respaldo.ps1`; `database/reference/GlucoLume_cifrado_y_respaldo.sql`.
- **Verificación disponible:** los scripts figuran como ensayados en una instancia descartable el 19/10/2026 (declarado); no se ejecutaron en esta revisión.
- **Medición:** ninguna.
- **Estado:** PARCIAL (preparado; sin política aprobada ni evidencia de ejecución en la instalación real).

### RNF-053 — Recuperación del acceso administrativo y de las claves de MFA
- **Categoría:** recuperación.
- **Descripción:** existen comandos de servidor para reinvitar al administrador, reemplazarlo por un moderador y diagnosticar y recifrar los secretos de MFA con otra clave, todos auditados y con confirmación expresa.
- **Criterio de aceptación:** perdido el acceso del administrador, el operador del servidor puede restablecerlo sin contraseña maestra y dejando evidencia.
- **Respaldo:** `backend/app/cli/recoverAdmin.py`, `initAdmin.py`, `mfaKeys.py`.
- **Verificación disponible:** `test_platform_recovery.py`, `test_platform_reinvite.py`, `test_security_config.py`.
- **Medición:** no aplica.
- **Estado:** IMPLEMENTADO.

## Cumplimiento normativo

### RNF-054 — Tratamiento de datos personales con referencia a la Ley 25.326
- **Categoría:** cumplimiento.
- **Descripción:** el sistema toma como referencia la Ley 25.326 de protección de datos personales en Argentina: consentimiento versionado y registrado, minimización, plazos de conservación definidos para pacientes y auditoría técnica, derechos de supresión por baja de cuenta y baja de paciente, y separación entre información administrativa y de salud. El texto de la política de privacidad (versión 1.1), la base legal del envío de resultados por correo y la inscripción de la base de datos están pendientes de validación externa; tres políticas de conservación (auditoría total, personal histórico y trabajo de retención de pacientes) están desactivadas o sin programar hasta su aprobación.
- **Criterio de aceptación:** validación del texto de la política y de los plazos por asesoría legal o por la cátedra; inscripción de la base si corresponde.
- **Respaldo:** `backend/app/services/consent.py:1-35`; `backend/app/core/config.py:113-141`; `docs/PRIVACIDAD_Y_RETENCION.md`; `docs/PENDIENTES.md`.
- **Verificación disponible:** pruebas de los comportamientos (consentimientos, anonimización, retención); la conformidad legal no es verificable desde el software y consta como pendiente.
- **Medición:** no aplica.
- **Estado:** PARCIAL (mecanismos implementados; validación legal pendiente).
