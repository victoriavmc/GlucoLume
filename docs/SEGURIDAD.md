# Seguridad

Controles vigentes, módulo de auditoría y estado de los hallazgos. Fuente única de seguridad del software; los informes de auditoría
originales se conservan como evidencia y no se copian aquí:

| Informe | Fecha | Dónde |
|---|---|---|
| Auditoría de 20 controles previa al despliegue (H-01 a H-13) | 16/10/2026 | Consolidado en este documento y en [HISTORIAL.md](HISTORIAL.md) |
| Bloques de corrección 1–7 (optimización y seguridad) | 17/10/2026 | [HISTORIAL.md](HISTORIAL.md) |
| Auditoría administrativa y monitoreo de seguridad | 18/10/2026 | Sección 3 de este documento y [HISTORIAL.md](HISTORIAL.md) |
| Auditoría de ciberseguridad (GL-01 a GL-21) | 19/10/2026 | [seguridad/auditorias/AUDITORIA_CIBERSEGURIDAD_GLUCOLUME.pdf](seguridad/auditorias/AUDITORIA_CIBERSEGURIDAD_GLUCOLUME.pdf) |

Etiquetas: **[PRUEBA]** comprobado ejecutando algo; **[CÓDIGO]** leído en el código o la configuración; **[NO VERIFICADO]** depende de un
sistema que no se inspeccionó (SQL Server real, servidor de producción, consola de Google, respaldos). Que las pruebas pasen demuestra los
comportamientos probados, no que el sistema sea «completamente seguro». La seguridad del software no es una validación clínica del dispositivo.

## 1. Controles vigentes

| Área | Control | Verificación |
|---|---|---|
| Contraseñas | Argon2id (m=64 MiB, t=3, p=4), sal por contraseña, rehash automático, hash ficticio para igualar tiempos; política de 8–128 caracteres con mayúscula, minúscula, número y símbolo, lista de contraseñas comunes y sin datos personales | [PRUEBA] |
| JWT y sesiones | Algoritmo fijado por configuración (nunca el del token); `iss`, `aud`, `exp`, `iat`, `sub`, `typ` obligatorios; secreto ≥ 32; cada pedido valida la sesión en la base (no revocada, no vencida, usuario `ACTIVO`); refresh rotado en cada uso y reutilización ⇒ revocación de todas las sesiones (`REFRESH_REUTILIZADO`) | [CÓDIGO] + pruebas |
| Tokens en el navegador | Access token en memoria (30 min); refresh en `sessionStorage` o, con «Recordarme», `localStorage` (7 días); la API usa Bearer, sin cookies de sesión (CSRF no aplica) | Riesgo aceptado (GL-14) |
| MFA | TOTP con secretos cifrados (Fernet, `MFA_ENCRYPTION_KEY`; rotación con `MFA_PREVIOUS_ENCRYPTION_KEYS` y `python -m app.cli.mfaKeys`), contador de intentos atómico (5), códigos de recuperación, recuperación por correo; obligatorio para cuentas de plataforma | [PRUEBA] |
| OAuth Google | `state`, nonce y PKCE en cookie firmada (`SameSite=Lax`, 10 min, `Secure` en producción); el inicio de sesión no crea cuentas | [CÓDIGO] |
| Abuso | Bloqueo por cuenta (3 contraseñas, 15 min), límites por IP en los endpoints sin sesión (429 + `Retry-After`, IPv6 por /64), tope de Nginx en `/api/v1/auth/`, cooldown de reenvío de verificación, honeypot en contacto. Sin CAPTCHA (decisión de accesibilidad) | [PRUEBA] |
| Autorización | Centralizada en el backend: `requireMembership` (vínculo `ACTIVO` + institución `ACTIVA` + permiso del rol), `platformAccess`/`platformSecure`, `requireAdministrator`/`requireOwner`; lo ajeno responde «inexistente» | [PRUEBA] |
| Datos de salud | Solo el operador responsable vigente ve las mediciones de un paciente; propietario y moderador no por su rol; agregados con mínimo de 5 pacientes; grupos revalidan el permiso en cada consulta | [PRUEBA] |
| Dispositivo compartido | DEC-01: control temporal atómico, lecturas en vivo y órdenes solo para quien controla, sin interferencia entre sesiones, modo restringido por asignación ([DISPOSITIVOS_Y_ADQUISICION.md](DISPOSITIVOS_Y_ADQUISICION.md)) | [PRUEBA] |
| Entradas | Esquemas Pydantic con `extra="forbid"`, enums y UUID tipados, paginación acotada; la glucosa y la matriz nunca vienen del cliente | [PRUEBA] |
| Inyección SQL | SQLAlchemy Core/ORM parametrizado; los pocos `text()` son constantes con parámetros; `ilike` con escape | [CÓDIGO] + [PRUEBA] payloads |
| XSS | React sin `dangerouslySetInnerHTML`, `innerHTML`, `eval` ni `document.write`; Jinja2 con autoescape; CSP `script-src 'self'` | [CÓDIGO] |
| Respuestas | Ningún esquema de respuesta expone hashes ni secretos; correos enmascarados; errores 500 genéricos, sin mensajes de SQL Server | [PRUEBA] |
| Cabeceras | Nginx y API: `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, CSP sin `'unsafe-inline'` en estilos ni scripts, `Cache-Control: no-store` en la API, HSTS solo sobre HTTPS; Swagger/OpenAPI fuera de producción | [PRUEBA] |
| Red | Nginx sobrescribe `X-Forwarded-For` y solo confía en el proxy configurado; backend y base sin puertos publicados; CORS solo para `FRONTEND_URL`, sin credenciales | [PRUEBA] |
| Secretos | `.env`, `docker/db.env` y `bridge.env` ignorados por Git; plantillas sin valores; nada secreto en imágenes ni en el frontend (solo `VITE_*` públicas) | [CÓDIGO] |
| Contenedores | Sin root, sistema de archivos de solo lectura, `cap_drop: ALL`, `no-new-privileges`, límites, redes `edge`/`data` | [PRUEBA] contenedores en ejecución (19/10) |
| Dependencias | Lock de Python con hashes (`--require-hashes`), `package-lock.json`; `pip-audit` (requirements y dev) y `npm audit` con 0 vulnerabilidades conocidas el 19/10/2026; imágenes base fijadas por digest y escaneadas con Docker Scout (imagen final del frontend sin altas ni críticas; backend con 1 alta de `zlib` de Debian sin corrección publicada) | [PRUEBA] 19/10; repetir antes de publicar |
| Streams SSE | Tope de 6 por cuenta y 300 en total, sesión de base liberada, revalidación cada 30 s | [PRUEBA] |
| Auditoría de solo inserción | Ninguna ruta ni servicio de la API modifica o borra `Auditoria`/`AuditoriaContexto`: solo `services/auditRetention.py`, que corre en `lifecycle` con su propia cuenta de base (`DB_JOBS_USER`). Una prueba global falla si código de `app/` emite esos `UPDATE`/`DELETE`. Los permisos de SQL Server están preparados (`database/reference/GlucoLume_permisos.sql`), no aplicados | [PRUEBA] en SQLite; permisos [NO VERIFICADO] |
| Correo de resultados | El paciente confirma la dirección con un enlace firmado (72 h, botón explícito): sin confirmación no se guarda ni recibe resultados; un envío puntual a otra dirección también espera la confirmación | [PRUEBA] |
| Pruebas aisladas | Las pruebas cargan `backend/tests/test.env` (valores ficticios, SMTP `.invalid`); nunca el `.env` real | [PRUEBA] |
| Configuración | Un error de validación nunca muestra el valor recibido (`hide_input_in_errors`); en producción no arranca con secretos repetidos entre variables ni con `SESSION_SECRET` corto; advertencias solo con nombres | [PRUEBA] |
| Alerta activa | Una ráfaga de rechazos se registra en la auditoría y además se avisa por correo al administrador de la plataforma (máximo una por patrón y hora, sin IP) | [PRUEBA] |
| Puente | Token propio en `X-Bridge-Token` con comparación en tiempo constante; token anterior aceptado durante la rotación (`BRIDGE_PREVIOUS_TOKEN`); una IP que falla el token 20 veces en 10 min queda bloqueada aunque después acierte; `/bridge/check` con límite por IP; lista cerrada de órdenes; HTTPS fuera de localhost | [PRUEBA] |

### 1.1 Protección por categoría de datos

| Categoría | Hoy | Propuesta |
|---|---|---|
| Contraseñas | Argon2id | Mantener |
| Secretos TOTP | Fernet | Respaldar la clave aparte (perderla invalida el MFA de todos) |
| Tokens y códigos | SHA-256 / HMAC con clave derivada por propósito (HKDF de `JWT_SECRET`) | Mantener |
| Identificación de pacientes | En claro (búsqueda con `ILIKE`) | TDE y cifrado de disco y respaldos; *Always Encrypted* rompería la búsqueda parcial |
| Mediciones | En claro | TDE (datos experimentales tratados como salud) |
| Correo de resultados del paciente | En claro, 12 meses, solo después de que el paciente lo confirma | TDE |
| Auditoría | En claro, sin secretos; solo inserción desde la API | Aplicar `GlucoLume_permisos.sql` (GL-03) |
| Respaldos | Procedimiento con TDE, respaldo cifrado AES-256 y restauración de prueba, ensayado en una instancia descartable; no aplicado en la real | Aplicar `GlucoLume_cifrado_y_respaldo.sql` y aprobar la retención |

### 1.2 Row-Level Security nativo

No se implementa ahora: la API usa un único usuario con pool de conexiones (habría que fijar y limpiar `SESSION_CONTEXT` en cada conexión
prestada), `Medicion` no tiene `idInstitucion` (el predicado necesitaría *joins* en las tablas más grandes), hay actores que cruzan
instituciones (plataforma, `lifecycle`, retención, puente) y la suite corre sobre SQLite. Alternativa de menor riesgo: permisos de base más
finos y, si se avanza, probar RLS solo sobre `PerfilMedicion`, `Medicion` y `Auditoria` detrás de una bandera y en un entorno de pruebas.

## 2. Estado de los hallazgos

Los GL-xx provienen del informe del 19/10/2026; GL-22 y GL-23 se agregaron después con la misma numeración. Los pendientes viven en
[PENDIENTES.md](PENDIENTES.md); lo resuelto, con su evidencia, en [HISTORIAL.md](HISTORIAL.md).

| ID | Hallazgo | Severidad original | Estado al 19/10/2026 |
|---|---|---|---|
| GL-01 | Interruptor que permite usar el equipo institucional desde otras cuentas | Alta | **Reclasificado y cerrado como hallazgo:** es la decisión DEC-01. El riesgo real (órdenes y lecturas sin control, interferencia) se resolvió con el control temporal y se verificó con pruebas en ambos modos. Falta validarlo con el hardware real |
| GL-02 | `UPDATE` sobre `Auditoria` en cada inicio de sesión | Media | **Corregido:** `tipoCuentaActor` viaja en el INSERT; prueba de que ningún LOGIN emite UPDATE/DELETE. No probado en SQL Server |
| GL-03 | La cuenta de la aplicación puede modificar y borrar la auditoría | Media | **Verificado en ensayo con datos reales; pendiente en producción:** imagen nueva + permisos probados sobre la copia restaurada (la imagen vieja falla con el `DENY`, por eso el orden es despliegue → permisos). Falta desplegar y aplicar (§5.1 pasos 1 y 3) |
| GL-04 | STARTTLS sin verificar el certificado del servidor SMTP | Media | **Corregido:** STARTTLS con `ssl.create_default_context()` (certificado y nombre verificados, TLS ≥ 1.2); prueba con servidor simulado |
| GL-05 | Estado del antiguo script 034 y de la base real | Media | **Corregido y aplicado en producción:** 6 `CK_Medicion_*` agregadas tras respaldo y ensayo (0 violaciones, 14 casos); 6 índices con filtros verificados con `VIEW DEFINITION`; `schemaCheck` sin diferencias |
| GL-06 | `MFA_ENCRYPTION_KEY` duplicada con valores distintos en `.env` | Media | **Diagnosticado; pendiente un cambio del `.env`:** en la copia restaurada la clave vigente (`e60adb4b`) descifra todos los factores y la otra (`b15fb16d`) ninguno; rotación y re-cifrado probados en la copia. Quitar la línea de `b15fb16d` (§5.1 paso 2; la sesión no tiene permiso para editar el `.env`) |
| GL-07 | Cifrado en reposo, TLS verificado hacia la base y respaldos sin evidencia | Media | **Respaldos aplicados; TLS y BitLocker pendientes de administrador:** respaldo cifrado AES-256 automatizado con restauración de prueba (Express no tiene TDE ni cifrado de backups). Validación del certificado implementada y verificada en ensayo; en producción falta instalar un certificado en la instancia (§5.1 paso 4) y BitLocker (paso 5) |
| GL-08 | Resultados por correo: consentimiento autodeclarado, correo guardado en claro | Media | **Corregido:** doble confirmación del destinatario (el operador declara la autorización y el paciente confirma desde su correo); un envío puntual a una dirección no confirmada espera la confirmación. El correo sigue en claro (TDE pendiente, GL-07) |
| GL-09 | Carpeta sin documentación, scripts SQL ni control de versiones | Baja | **Parcial:** referencias a scripts retirados reemplazadas por el esquema v5 en código, mensajes e interfaz; falta versionar con Git |
| GL-10 | `DATABASE_URL` huérfano en `.env` | Baja | **Detectado al arrancar:** advertencia si `DATABASE_URL` sigue en el `.env`. Quitarla es una acción sobre el `.env` real |
| GL-11 | Endpoints del puente sin límite por IP; token único sin rotación | Baja | **Corregido:** bloqueo por IP tras 20 tokens fallidos en 10 min, límite en `/bridge/check`, rotación con `BRIDGE_PREVIOUS_TOKEN`. Token por puente: requiere esquema, no se implementó |
| GL-12 | La suite depende del `.env` real | Baja | **Corregido:** las pruebas usan `backend/tests/test.env` (`GLUCOLUME_ENV_FILE`); prueba que lo comprueba |
| GL-13 | Dependencias e imágenes sin reescaneo; imágenes por etiqueta | Baja | **Corregido salvo un residual:** dependencias sin vulnerabilidades; imágenes fijadas por digest; Node 22.12 → 22.23 (etapa de build) y Caddy 2.9 → 2.11; imagen final del frontend sin altas ni críticas; la del backend conserva 1 alta de `zlib` de Debian sin corrección publicada |
| GL-14 | Refresh token en `localStorage` con «Recordarme» | Baja | Riesgo aceptado |
| GL-15 | Contadores en memoria, sin CAPTCHA, alertas pasivas | Baja | **Parcial:** alerta activa por correo al administrador (acotada y sin IP). Contadores en memoria y sin CAPTCHA: aceptado con una réplica; Redis/WAF solo si se escala |
| GL-16 | Auditoría conservada sin plazo | Baja | Pendiente (decisión legal). La depuración total sigue desactivada (`AUDIT_RETENTION_MONTHS=0`) |
| GL-17 | Clave MFA sin rotación; `JWT_SECRET` como clave HMAC | Baja | **Corregido:** el HMAC de códigos cortos usa una clave derivada (HKDF) y acepta el cálculo anterior mientras vencen los códigos emitidos; rotación del MFA con `MultiFernet` |
| GL-18 | `FORWARDED_ALLOW_IPS="*"` en desarrollo | Baja | **Corregido:** en desarrollo (`compose.dev.yaml`) el backend solo confía en `127.0.0.1` |
| GL-19 | CSP con `style-src 'unsafe-inline'` | Baja | **Corregido:** CSP con `style-src 'self'`, verificada en el navegador con el build y la galería de componentes (React aplica estilos por CSSOM) |
| GL-20 | Secretos reales en texto plano en una carpeta sin repositorio | Baja | **Validaciones corregidas, rotación pendiente (acción humana):** en producción no se arranca con secretos repetidos entre variables ni con `SESSION_SECRET` corto; el `.env` real no tiene secretos repetidos (solo se compararon, sin mostrarlos). Rotar antes de publicar; procedimiento en §5.1 |
| GL-21 | `BorrarRap.sql` sin controles de entorno | Baja | **Corregido:** `BorrarRap.sql` exige `-v BASE` y `CONFIRMAR_BORRADO` iguales al nombre de la base conectada; sin ellos no borra nada |
| GL-22 | Lecturas en vivo del equipo visibles para cualquier cuenta que mide, sin sesión | Media | **Corregido:** solo quien controla el equipo recibe valores y PPG; prueba de estado y de stream |
| GL-23 | La Política de Privacidad dice que la IP y el navegador no se guardan, pero `AuditoriaContexto` los conserva 90 días | Media | **Corregido:** la política (versión 1.1) informa que la IP y el navegador se guardan 90 días; no se fuerza una nueva aceptación (no cambia la base legal) |

### 2.0 Alcance (decisión del 19/10/2026)

GlucoLume es un prototipo académico (TIF) que funciona en un equipo local con Docker y SQL Server Express; no se publica en Internet ni
busca una certificación. OWASP, ISO 27001 y NIST CSF se usan como referencia para identificar riesgos, no como lista de controles
obligatorios. Se distinguen: **riesgos del prototipo** (se corrigen), **mejoras para una instalación productiva** (quedan documentadas,
no bloquean la entrega) y **controles fuera de alcance** (no se aplican). BitLocker y un certificado de servidor para SQL Server son
mejoras productivas: en local la conexión va cifrada (`Encrypt=yes`) y, en `development`, sin verificar el certificado; producción
(`API_ENV=production`) sigue exigiendo la verificación.

### 2.1 Estado por entorno (19/10/2026, 23:00)

**Código**: corregido en el repositorio y probado. **Ensayo**: copia restaurada del respaldo real en SQL Server 2025 Developer descartable,
con la imagen nueva del backend. **Producción**: instancia real (SQL Server 2025 Express, `localhost\GLUCOLUME`) y contenedores en
ejecución. **Desplegado el 20/10/2026**: `glucolume/backend:remediacion` y `glucolume/frontend:remediacion2` (reversión: `pre-remediacion`);
con eso quedan en producción las correcciones de código (GL-02, GL-04, GL-08, GL-11, GL-12, GL-15, GL-17, GL-19, GL-20, `MultiFernet`).

| Hallazgo | Código | Ensayo | Producción |
|---|---|---|---|
| GL-02 / GL-03 auditoría de solo inserción | Verificado | Imagen nueva + `GlucoLume_permisos.sql`: login con y sin MFA correcto; la API recibe 229 al modificar o borrar auditoría; conservación depura; la imagen vieja falla con el `DENY` | **Pendiente**: requiere desplegar la imagen nueva antes del `DENY`; luego crear el login de conservación y configurar `DB_JOBS_*` (decisión/acción tuya) |
| GL-05 esquema | Verificado | Migración aplicada a la copia; 14 casos válidos/inválidos/límite; 67/67 pruebas SQL Server 2025 | **Aplicado**: 6 `CK_Medicion_*` agregadas (habilitadas y confiables); índices y filtros verificados con `VIEW DEFINITION`; `schemaCheck` sin diferencias |
| GL-06 claves MFA | Verificado (`MultiFernet`, `mfaKeys`) | La clave vigente (`e60adb4b`) descifra todos los factores; la otra (`b15fb16d`) ninguno | **Aplicado**: `.env` con una sola `MFA_ENCRYPTION_KEY` (se quitó `b15fb16d`) y sin `DATABASE_URL`; copia cifrada del anterior en `C:\GlucoLumeRespaldos` |
| GL-07 TLS | Verificado: certificado fijado o de confianza agregada; producción rechaza `TrustServerCertificate` | Certificado propio: correcto conecta; otro o nombre distinto se rechazan | Local: cifrado sin verificar el certificado (`development`). **Mejora productiva**, no requisito del prototipo |
| GL-07 respaldos | Scripts en `database/respaldos/` | — | **Aplicado**: respaldo cifrado AES-256 verificado, restauración de prueba sin diferencias y tareas programadas. BitLocker: **fuera de alcance** (mejora productiva) |
| GL-04, GL-08, GL-11, GL-12, GL-15, GL-17, GL-19, GL-20 | Verificado | Imagen nueva funcionando (CSP estricta en Nginx comprobada) | **Pendiente de despliegue** |

Correspondencia con el informe del 16/10: H-01 a H-05 corregidos (IP falsificable, límites por IP, reenvío sin cooldown, Swagger en
producción, cabeceras); H-06 = GL-10; H-07 y H-08 = GL-03; H-09 = GL-07; H-10 = GL-14; H-11 (enumeración en registro y activación) y H-12
(bloqueo de una cuenta ajena por intentos) son riesgos residuales aceptados; H-13 (pruebas con fallas previas) quedó resuelto el 17/10.

## 3. Auditoría de la aplicación

Única vía de escritura: `services/audit.py::registerEvent`. Cada evento se confirma con su operación; no hay ninguna ruta para crear,
editar o borrar eventos.

**Qué se registra:** accesos (éxito y fallo, también sobre cuentas inexistentes, solo con una huella HMAC de lo escrito), MFA, sesiones
reutilizadas, cambios de contraseña, eliminación y ciclo de vida de cuentas, operaciones institucionales (instituciones, personal,
pacientes, transferencias, matrices, dispositivos, mediciones), operaciones de plataforma, controles activados (`BLOQUEO_TEMPORAL_CUENTA`,
`LIMITE_SOLICITUDES_EXCEDIDO`, `RAFAGA_RECHAZOS_HTTP`, `RAFAGA_VALIDACION_HTTP`), exportaciones (`EXPORTACION_SOLICITADA/COMPLETADA/FALLIDA`,
punto único `services/exportAudit.py`, todavía sin ninguna exportación real), control del dispositivo y órdenes al puente.
**Nunca se registra:** contraseñas, tokens, cookies, códigos TOTP o de recuperación, cuerpos de pedidos, lo escrito en un identificador
inexistente, valores de salud.

**Contexto** (`AuditoriaContexto`, 1:1): correlación (`X-Request-ID` que fija Nginx; la API acepta uno solo si tiene formato seguro),
IP, cliente acotado (navegador resumido; herramientas automáticas truncadas a 100 caracteres), motivo normalizado
(`PASSWORD_INCORRECTA`, `CUENTA_INEXISTENTE`, `CUENTA_INACTIVA`, `CORREO_NO_VERIFICADO`, `CUENTA_BLOQUEADA`, `INTENTOS_EXCEDIDOS`,
`CODIGO_MFA_INVALIDO`, `MFA_BLOQUEADO`, `LIMITE_POR_ORIGEN`, `RECHAZOS_REITERADOS`, `PERMISO_INSUFICIENTE`, entre otros). Sin la tabla, la
auditoría sigue sin contexto. **Tipo de cuenta** (`Auditoria.tipoCuentaActor`): en los eventos LOGIN con cuenta identificable, en el mismo
INSERT, si la base tiene la columna.

| Quién | Qué ve |
|---|---|
| Administrador de la plataforma | Todo: plataforma, cualquier institución o cuenta (autora o afectada), con IP, cliente y correlación; señales de seguridad |
| Propietario de una institución | Solo los eventos de su institución, sin IP, cliente, correlación ni registros del módulo `PLATAFORMA`; los eventos de medición sin identificar al paciente |
| Moderadores, operadores, cuentas individuales y moderación de plataforma | Nada (403 auditado) |

**Clasificación:** Informativo, Error operativo (no es un ataque), Actividad sospechosa (señal para investigar) y Control activado. Colores
verde/naranja/rojo/gris, siempre con texto. **Señales** calculadas al consultar (no escriben): ≥ 5 fallos contra una cuenta o identificador
en 15 min; ≥ 5 cuentas distintas desde un origen en 15 min; origen inusual solo si la cuenta tiene ≥ 5 accesos exitosos con IP en 90 días;
controles y ráfagas (≥ 20 rechazos o ≥ 30 errores de validación por origen en 15 min). Umbrales `AUDIT_ALERT_*` configurables.

**Accesos por tipo de cuenta** (tablero de la plataforma, `services/authAccess.py`): individuales, institucionales, de plataforma y «sin
clasificar» salen de la misma consulta y suman el total. El tipo es el de la cuenta que se autenticó (registrado en el evento cuando existe la
columna; si no, el vigente). Los eventos anteriores se infieren: solo cambian de tipo los relevos administrador↔moderador, ambos de plataforma.

**Conservación:** IP y cliente 90 días (`AUDIT_CONTEXT_RETENTION_DAYS`); intentos sin cuenta identificable 12 meses
(`AUDIT_ANONYMOUS_RETENTION_MONTHS`); toda la auditoría sin límite (`AUDIT_RETENTION_MONTHS=0`, plazo no aprobado). Cada depuración deja
`DEPURAR_AUDITORIA`. La aplica el servicio `lifecycle`.

## 4. Riesgos residuales

1. Estado en memoria (límites, monitor de ráfagas, hub del dispositivo): la arquitectura asume **una** réplica.
2. IP compartida por NAT (falsos positivos en las señales) e IPv6 rotativa (falsos negativos): son señales, no veredictos.
3. En la instancia real: datos en reposo sin cifrar (GL-07) y auditoría modificable a nivel de base hasta aplicar `GlucoLume_permisos.sql` (GL-03); ambos procedimientos están ensayados en una instancia descartable.
4. Sin CAPTCHA: un atacante distribuido supera los límites por IP; los controles por cuenta siguen vigentes.
5. Alertas: solo las ráfagas de rechazos avisan por correo al administrador; las demás señales se ven al abrir la consola.
6. La cuenta `glucolume_app` de la base real no se inspeccionó.
7. Las dependencias y las imágenes base acumulan CVE nuevas: el escaneo se repite.
8. La imagen del backend tiene una vulnerabilidad alta de `zlib` (Debian) sin corrección publicada: se reconstruye cuando Debian la publique.

## 5. Antes de publicar con datos reales

1. Dominio con HTTPS (perfil `https`), `API_ENV=production`, `GLUCOLUME_VERSION` fija.
2. Secretos nuevos generados en el servidor; `MFA_ENCRYPTION_KEY` única y respaldada; eliminar `DATABASE_URL` del `.env`.
3. Base: TLS verificado, TDE, respaldos cifrados con restauración de prueba, permisos mínimos y `DENY` sobre la auditoría, puerto 1433 no
   accesible desde Internet.
4. Probar el envío real por SMTP con certificado verificado (GL-04) y el circuito de confirmación de resultados (GL-08) en el entorno final.
5. Una sola réplica del backend y un solo `lifecycle`; Redis antes de escalar.
6. Repetir `pip-audit`, `npm audit` y el escaneo de imágenes el día de la publicación.
7. Monitorear 429, `REFRESH_REUTILIZADO` y bloqueos desde el primer día; activar alertas.
8. Aprobar con asesoría legal la retención y revisar la política de privacidad (Ley 25.326, GL-23).

### 5.1 Procedimientos pendientes (comandos exactos)

Orden para cerrar el prototipo: (1) despliegue, (2) `.env` — **hecho el 19/10** —, (3) permisos de auditoría. Los puntos 4 y 5 son
mejoras para una instalación productiva, no requisitos de la entrega. Los comandos `sqlcmd` llevan `-I` (`QUOTED_IDENTIFIER ON`: lo
exigen los índices filtrados). Respaldo previo verificado:
`C:\GlucoLumeRespaldos\GlucoLume_pre_remediacion_20261019_223643.bak.gpg` (copia en claro en la carpeta de respaldos de la instancia).

1. **Desplegar la imagen validada** (desde la raíz del proyecto):
   `docker tag glucolume/backend:remediacion glucolume/backend:dev`, `docker tag glucolume/frontend:remediacion2 glucolume/frontend:dev`
   (la imagen `frontend:remediacion` quedó con la ruta de Git como base de la API: no usarla),
   `docker compose -f compose.yaml up -d --no-deps --no-build backend frontend`. Comprobar `docker ps` (healthy), un inicio de sesión real
   con y sin MFA y `docker logs glucolume-backend-1`. **Reversión**: `docker tag glucolume/backend:pre-remediacion glucolume/backend:dev`
   (ídem frontend) y el mismo `up -d`; la base no cambia con el despliegue.
2. **`.env`**: quitar la línea `MFA_ENCRYPTION_KEY` cuya huella es `b15fb16d` (no descifra ningún factor; `python -m app.cli.mfaKeys` lo
   confirma) y la línea `DATABASE_URL`. Copia cifrada del `.env` anterior en `C:\GlucoLumeRespaldos\env_pre_remediacion_*.gpg`.
3. **Permisos de auditoría** (después del paso 1): crear el login de conservación como `sysadmin`
   (`CREATE LOGIN glucolume_retencion WITH PASSWORD = '<nueva>', CHECK_POLICY = ON`), ejecutar
   `sqlcmd -S localhost\GLUCOLUME -E -d GlucoLume -i database\reference\GlucoLume_permisos.sql -v API_LOGIN=glucolume_app JOBS_LOGIN=glucolume_retencion CONFIRMAR=APLICAR_PERMISOS_GLUCOLUME`,
   agregar `DB_JOBS_USER`/`DB_JOBS_PASSWORD` al `.env` y recrear `backend` (y `lifecycle` si se usa). Verificar un inicio de sesión. Reversión:
   `ALTER ROLE rol_glucolume_api DROP MEMBER glucolume_app; DROP ROLE rol_glucolume_api;` (ídem retención); no toca datos.


4. *(Mejora productiva)* **Certificado de SQL Server (GL-07)**, como administrador de Windows: crear o importar un certificado de servidor con el nombre o la IP que
   usa el backend (`192.168.56.1`) en `Cert:\LocalMachine\My`, dar lectura de su clave privada a `NT SERVICE\MSSQL$GLUCOLUME`, elegirlo en
   el Administrador de configuración de SQL Server (Protocolos de GLUCOLUME → Certificado; Forzar cifrado = Sí) y reiniciar el servicio en
   una ventana sin uso. Exportar el certificado público a `docker\certs\sqlserver.crt` y en el `.env`: `DB_SERVER_CERTIFICATE=/run/certs/sqlserver.crt`,
   `DB_TRUST_SERVER_CERTIFICATE=false`. Reversión: volver a `DB_TRUST_SERVER_CERTIFICATE=true` y quitar el certificado en el Administrador.
5. *(Mejora productiva)* **BitLocker**, como administrador: `manage-bde -on C: -RecoveryPassword` (guardar la clave de recuperación fuera del equipo). Y guardar la
   clave de los respaldos: `powershell -File database\respaldos\GlucoLume_clave_respaldo.ps1 -Mostrar` → gestor de contraseñas.
- **Base cifrada con TDE (solo Standard o superior).** `sqlcmd ... -i database/reference/GlucoLume_cifrado_y_respaldo.sql -v BASE=... DIR_RESPALDO=...
  CLAVE_CERTIFICADOS=... CONFIRMAR=CIFRAR_Y_RESPALDAR_GLUCOLUME` (primero en una copia); guardar fuera del servidor los certificados exportados y
  su contraseña; certificado de SQL Server confiable para el host (`DB_TRUST_SERVER_CERTIFICATE` sin definir).
- **Base instalada (GL-05).** `python -m app.cli.schemaCheck` (solo lectura) después de cualquier cambio de esquema o restauración.
- **Rotación de secretos (GL-20, H-08)**, cada seis meses o ante cualquier sospecha de filtración, en una ventana acordada. Generar los valores nuevos
  en el servidor con `python -c "import secrets; print(secrets.token_urlsafe(64))"` y recrear `backend` (y `lifecycle`) después de cada paso:
  1. `JWT_SECRET`: pasar el valor vigente a `JWT_PREVIOUS_SECRET` y poner el nuevo en `JWT_SECRET`. La API firma con el nuevo y sigue aceptando los
     tokens ya emitidos con el anterior, así que **no se cierran las sesiones**. Quitar `JWT_PREVIOUS_SECRET` pasados **7 días** (el refresh es opaco y
     vive en la base; los tokens firmados más largos son los enlaces de correo, de hasta 30 días: los de baja de avisos). Al arrancar, la API advierte
     mientras `JWT_PREVIOUS_SECRET` siga definido. Efecto colateral: las claves derivadas de `JWT_SECRET` (HMAC de códigos cortos, vigentes minutos, y de
     identificadores de auditoría) cambian; los códigos emitidos antes de la rotación hay que pedirlos de nuevo y la búsqueda por identificador en la
     auditoría deja de encontrar las huellas anteriores (acotadas por `AUDIT_CONTEXT_RETENTION_DAYS`).
  2. `BRIDGE_TOKEN`: el anterior pasa a `BRIDGE_PREVIOUS_TOKEN`, se actualiza el del puente y se quita el anterior en cuanto el puente use el nuevo (máximo 24 h).
  3. `SESSION_SECRET` (solo invalida un inicio de sesión con Google en curso) y `GOOGLE_CLIENT_SECRET` (se rota también en Google Cloud): cambio directo.
  4. `DB_PASSWORD`, `DB_JOBS_PASSWORD` y `SMTP_PASSWORD`: `ALTER LOGIN ... WITH PASSWORD = '<nueva>'` en SQL Server (o el panel del proveedor de correo), luego el `.env`.
  5. `MFA_ENCRYPTION_KEY`: con `MFA_PREVIOUS_ENCRYPTION_KEYS` y `python -m app.cli.mfaKeys`.
  Registrar la fecha de la rotación (sin los valores) y verificar un inicio de sesión real con y sin MFA.
- **Imágenes (GL-13).** Para actualizar un digest: `docker buildx imagetools inspect`, `docker scout cves` y reconstruir.

Esta documentación no reemplaza una prueba de penetración externa.
