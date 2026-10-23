# Privacidad, consentimiento y retención

Qué hace el código con los datos personales y de salud, qué afirma la Política de Privacidad (`/privacidad`,
`frontend/src/pages/Privacy/PrivacyPolicy.jsx`) y qué queda por validar. La Ley 25.326 se toma como **referencia**: nada de esto certifica su
cumplimiento. Si el comportamiento cambia, se actualiza la política y su versión (`POLICY_VERSION` / `EXPERIMENTAL_VERSION` en
`backend/app/services/consent.py`; hoy la política es la `1.1` y el consentimiento experimental la `1.0`).

## 1. Consentimientos

Tabla `ConsentimientoUsuario`, historial de solo agregado (usuario, tipo, versión, `ACEPTADO`/`REVOCADO`, fecha); vale la fila más reciente
de cada tipo y un cambio de versión invalida la aceptación anterior.

| Tipo | Cuándo se exige | Dónde lo valida el backend |
|---|---|---|
| `POLITICA_PRIVACIDAD` | Registro local, registro con Google y activación de cuenta invitada | `auth.registerLocal`, `auth._linkOrCreateGoogleUser`, `accountActivation.completeActivation` (`POLITICA_NO_ACEPTADA`) |
| `DATOS_EXPERIMENTALES` | Antes de iniciar o recibir muestras de una medición del **perfil propio** | `measurement.startMeasurement`, `addSamples` (`CONSENTIMIENTO_REQUERIDO`) |

Endpoints `GET /auth/consents` y `PUT /auth/consents/datos-experimentales`. Revocar frena nuevas recolecciones (también las muestras de una
medición en curso) y **no borra lo ya medido**. Las cuentas anteriores a los consentimientos deben aceptar «datos experimentales» antes de medir.
El consentimiento de los **pacientes institucionales** es responsabilidad de la institución: el sistema no lo registra.

## 2. Lo que afirma la política y su respaldo

| Afirmación | Respaldo | Estado |
|---|---|---|
| Contraseña guardada como hash | `core/security.py` (Argon2id) | Coincide |
| La IP y un resumen del navegador se guardan con cada evento de auditoría, solo los ve la administración y se borran a los 90 días (versión 1.1) | `AuditoriaContexto` y `services/auditRetention.py`; también se usan para el correo `NUEVO_INICIO_SESION` | Coincide (GL-23 corregido el 19/10/2026; no se pide una nueva aceptación porque no cambia la base legal) |
| El formulario de contacto no se guarda | `services/contact.py` solo envía correos | Coincide |
| Sin analítica ni píxeles | `frontend/index.html` y `src/` no cargan scripts ni fuentes de terceros | Coincide |
| Servicios externos: Google OAuth y SMTP | `integrations/google`, `integrations/email` | Coincide |
| La administración ve agregados, no mediciones individuales | `services/platformDashboard.py` | Coincide |
| Eliminar la cuenta borra/anonimiza datos personales y conserva mediciones desidentificadas | `services/accountDeletion.py` | Coincide |
| Una cuenta sin verificar se elimina a las 24 h | `services/unverifiedAccounts.py` (`EMAIL_VERIFICATION_EXPIRE_HOURS`) | Coincide |
| Pacientes de institución: 12 meses y luego desidentificación | `services/institutionalRetention.py` + `app/jobs/purgeInstitutionalRetention.py` (no programado en Compose) | Coincide, con ejecución manual |

## 3. Datos de seguridad (auditoría)

IP, cliente y correlación viven en `AuditoriaContexto`, separados del evento, solo los ve la administración y se anulan a los 90 días
(`AUDIT_CONTEXT_RETENTION_DAYS`). El identificador escrito en un intento sobre una cuenta inexistente nunca se guarda en claro (HMAC). Los
intentos sin cuenta identificable se eliminan a los 12 meses; el resto de la auditoría se conserva sin plazo hasta que se apruebe uno
(`AUDIT_RETENTION_MONTHS=0`, propuesta técnica 24–36 meses). La auditoría no guarda datos de salud. Detalle: [SEGURIDAD.md](SEGURIDAD.md) §3.

## 4. Resultados por correo

| Caso | Comportamiento |
|---|---|
| Cuenta individual | Solo a su propio correo; tocar «enviar» es la autorización. No se envían mediciones DEMO |
| Paciente institucional, envío puntual | Al correo confirmado, sale directo. A otra dirección, el operador declara la autorización y el paciente recibe un enlace para confirmar; el resultado sale recién cuando confirma. Esa dirección no se guarda |
| Paciente institucional, correo cargado | El operador declara la autorización y el paciente confirma la dirección desde el enlace; recién entonces se guarda en `PerfilMedicion.correoResultados`, con vencimiento a **12 meses** desde la confirmación; se borra al vencer o al dar de baja al paciente; se muestra enmascarado. Cada medición guardada (también DEMO, identificada como simulada) se envía sola |

Confirmación (GL-08, `services/resultEmailConfirmation.py`): enlace firmado de propósito único, válido 72 horas, con el token en el fragmento
de la URL (no llega a los registros del servidor); la página `/confirmar-correo-resultados` exige tocar un botón, así un escáner de enlaces no
confirma solo. Repetir el enlace no reenvía nada. Hasta 10 pedidos de confirmación por operador y hora. No agrega columnas: el pedido viaja
firmado en el enlace.

Límite de 3 envíos por medición y hora. La auditoría registra el pedido de confirmación, la confirmación y el envío sin el correo. La
conexión SMTP verifica el certificado (GL-04). Riesgo abierto: el correo confirmado se guarda en claro (TDE pendiente, GL-07). Requiere que la
base tenga las columnas de correo (incluidas en v5); si faltan, la función se desactiva sin errores.

## 5. Retención de pacientes institucionales

**Seudonimización** conserva la relación persona-datos; **anonimización** la corta de forma irreversible.

Con el código de retención y anonimización activo (`measurementRetention.ready()`, requiere `PerfilMedicion.idInstitucion` y
`Medicion.fechaVencimientoRetencion`):

1. **Al dar de baja a un paciente** se anonimiza en el momento: sus mediciones pasan a la **cohorte anónima** de la institución (un
   `PerfilMedicion` de tipo `COHORTE_ANONIMA`, sin persona), cada una con fin de conservación = última medición + 12 meses
   (`Medicion.fechaVencimientoRetencion`); conservan edad al momento, sexo, alimentación, calidad, SpO₂, frecuencia, glucosa, modo, origen y
   estado (se borra la observación libre). El perfil original queda como cáscara sin datos de salud, con seudónimo aleatorio `ANON-…`, su
   responsable y su historial de transferencias. La baja se rechaza (`MEDICION_EN_CURSO`) si hay una adquisición activa de los últimos 30 min.
2. **Retención de 12 meses desde la última medición**, solo para datos conservados (pacientes de baja o anonimizados); un paciente activo o una
   cuenta individual no vencen por no medir. Se borran la medición y sus derivados (`MuestraSensor`, `MedicionReferenciaCapilar`,
   `EnvioResultado`) por lotes e idempotente; `Auditoria` no se toca.
3. **Cierre de una institución:** conserva los datos personales 12 meses (`fechaExpiracionDatosPersonales`) y el job los anonimiza al vencer;
   como las mediciones ya vencieron para entonces, el cierre no deja cohorte.
4. **Job** `python -m app.jobs.purgeInstitutionalRetention`: borra lo vencido → anonimiza lo que venció → borra lo que nació vencido. Un evento
   por pasada (`DEPURAR_MEDICIONES_RETENCION`, `ANONIMIZAR_PACIENTES`) con cantidades, sin identificadores.

   **Cómo se ejecuta (H-04), en dos pasos y solo a mano:** `python -m app.jobs.purgeInstitutionalRetention --simular` informa cuántos perfiles se
   anonimizarían y cuántas mediciones se eliminarían sin modificar nada; la ejecución exige `--confirmo-base <DB_NAME> --confirmo-perfiles <A>
   --confirmo-mediciones <B>` con esas cantidades exactas (si cambiaron, no hace nada). Un error parcial deja el evento
   `ANONIMIZAR_PACIENTES_PARCIAL` (cantidades, sin identificadores) y se reintenta en la próxima pasada. No se programa solo.

   **Auditoría y personal histórico (H-04):** `AUDIT_RETENTION_MONTHS` y `PERSONNEL_RETENTION_MONTHS` están en 0 y **este proyecto no propone ni fija
   valores**: son una decisión legal. Aun con un valor mayor que 0 no se aplican sin `RETENTION_APPROVAL_REFERENCE` (la referencia del dictamen o acta;
   queda en cada evento). Una pasada automática que alcance más de `RETENTION_MAX_DELETE_FRACTION` de la tabla (y más de `RETENTION_GUARD_MIN_ROWS`
   filas) se omite y deja `DEPURAR_AUDITORIA_OMITIDA`/`MINIMIZAR_DATOS_PERSONAL_OMITIDA`. Para revisarlo y, con autorización, ejecutarlo:
   `python -m app.jobs.retention previsualizar` y luego `python -m app.jobs.retention ejecutar --confirmo-base <DB_NAME> --confirmo-eventos <N>
   --confirmo-personal <M>`. Cada pasada deja `..._INICIADA` antes de borrar, el evento final con la política y la aprobación, o `..._FALLIDA`.

Sin esas columnas, la baja es la anterior: 12 meses y desidentificación por el job.

**Documento único por institución:** normalización (sin puntos, guiones ni espacios; mayúsculas; 6 a 12 caracteres;
`CK_PerfilMedicion_dniNormalizado`), un solo paciente activo por documento en una institución (índice único filtrado
`UX_PerfilMedicion_dniInstitucion`, también ante altas simultáneas: `PACIENTE_REGISTRADO`), el mismo documento en otra institución permitido,
pacientes sin documento permitidos, bajas y anonimizados fuera del índice.

**Agregados:** suman la cohorte anónima (cuenta como un paciente en el mínimo de 5). Un operador eliminado figura como «Operador desvinculado»
con sus cifras.

## 6. Cuentas y personal

- **Cuenta individual eliminada:** `Usuario` anonimizado (se conserva el identificador), credenciales, MFA, Google y tokens borrados, sesiones
  revocadas; sus mediciones quedan **desidentificadas sin plazo automático de borrado** (decisión documentada; pendiente decidir si se les aplica
  la anonimización).
- **Cuentas institucionales:** período de gracia y anonimización automática ([funcional/INSTITUCION.md](funcional/INSTITUCION.md) §5).
- **Nómina institucional** (`InstitucionUsuario`): no vence por defecto; minimización opcional desactivada (`PERSONNEL_RETENTION_MONTHS=0`,
  referencia de 10 años = 120 meses a validar legalmente); la institución puede eliminar los datos históricos de una persona desvinculada.

## 7. Respaldos

La retención se evalúa por fecha: tras restaurar un respaldo antiguo, una pasada del job vuelve a borrar y anonimizar lo vencido, así que no
hace falta un registro de supresiones. Pendiente de la infraestructura: rotación de respaldos (que ninguno conserve datos semanas después de
su vencimiento), cifrado y correr el job antes de dar acceso tras una restauración.

## 8. Validaciones externas pendientes

Revisión del texto de la política por la cátedra o el tutor y, si corresponde, por asesoría legal; necesidad de comité de ética o de
inscripción de la base; plazo de conservación de la auditoría; trato de las mediciones de cuentas individuales eliminadas
([PENDIENTES.md](PENDIENTES.md)).
