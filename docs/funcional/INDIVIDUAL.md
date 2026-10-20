# Usuario individual — especificación funcional

Lo que GlucoLume hace hoy para una cuenta individual (`Usuario.tipoCuenta = CONSUMIDOR_FINAL`). Manual práctico:
[MANUAL_USUARIO.md](../MANUAL_USUARIO.md#parte-1--usuario-individual). GlucoLume es un **prototipo experimental**: sus resultados no
reemplazan una medición clínica certificada.

Fuentes: `backend/app/services/{auth,user,mfa,mfaRecovery,consent,accountDeletion,measurement,measurementProfile,measurementVisibility,telemetry,deviceConnection,glucoseReference}.py`,
`frontend/src/pages/{Login,Register,Account}`.

## 1. Alcance

Una cuenta tiene **un único tipo** y no se convierte en institucional ni de plataforma (para eso se registra otro correo).

| Puede | No puede |
|---|---|
| Mantener su perfil y su seguridad | Ver datos de otra persona, salvo lo que un integrante de su [grupo familiar](GRUPO_FAMILIAR.md) le habilite |
| Medir con el dispositivo y consultar su historial, gráficos y estadísticas | Acceder a instituciones, pacientes, inventario global ni auditoría |
| Crear un grupo familiar o integrarse a uno | Medir sin el consentimiento de datos experimentales |
| Leer los consejos para personas con diabetes | Eliminar una medición real completada (solo las DEMO) |

Menú de `/app`: Inicio, Mediciones, Conectar dispositivo, Grupo, Perfil y Seguridad. Los consejos se abren desde Inicio.

## 2. Alta y acceso

- **Registro local:** nombre, apellido, correo, usuario (4–50 caracteres, sin «@»), contraseña y repetición, y aceptación de la Política de
  Privacidad (`POLITICA_NO_ACEPTADA` si falta). Política de contraseña: 8–128 caracteres, mayúscula, minúscula, número y símbolo, sin
  contraseñas comunes; se guarda solo el hash (Argon2id). La cuenta nace **PENDIENTE** hasta verificar el correo; si no se verifica en 24 h
  (`EMAIL_VERIFICATION_EXPIRE_HOURS`) se elimina; reenviar no extiende el plazo. Un correo ya registrado se informa en el formulario.
- **Google:** el registro con Google es un flujo aparte (exige aceptar la política); el inicio de sesión con Google no crea cuentas
  (`CUENTA_NO_REGISTRADA`). Con el mismo correo se vinculan automáticamente solo si Google lo informa verificado **y** la cuenta de GlucoLume ya
  está ACTIVA. Una cuenta puede tener contraseña, Google o ambos.
- **Inicio de sesión:** correo o usuario y contraseña; «Recordarme» define si la sesión persiste. **3 intentos fallidos** bloquean 15 min
  (`AUTH_LOCKOUT_MINUTES`), con contadores atómicos. Con MFA se pide después el código o uno de recuperación.
- **Recuperar contraseña:** enlace de un solo uso al correo; la pantalla no revela si el correo existe.

## 3. Perfil

Nombre, apellido, usuario, fecha de nacimiento y sexo (femenino/masculino); el correo es de solo lectura. El **perfil de medición**
(`PerfilMedicion`) es el propio usuario y se crea la primera vez que hace falta; la edad se calcula al iniciar cada medición. Cada medición
conserva su contexto (edad y sexo al momento) y no se recalcula si cambia el perfil.

## 4. Seguridad de la cuenta

| Función | Comportamiento |
|---|---|
| Contraseña | Pide la actual, la nueva y, con MFA, el código; una cuenta solo Google puede **crear** una. Cierra las otras sesiones |
| MFA (TOTP) | Opcional; QR + código; códigos de recuperación de un solo uso (descargables). Requiere `MFA_ENCRYPTION_KEY` en el servidor. Bloqueo a los 5 intentos incorrectos |
| Recuperar acceso sin la aplicación | Contraseña actual (o ingreso reciente con Google) + código de 6 dígitos al correo (10 min; 1 por minuto y 3 por hora). Desactiva el MFA, borra el secreto, revoca todas las sesiones y avisa por correo |
| Avisos de inicio de sesión | Interruptor del correo de «nuevo inicio de sesión»; las alertas de actividad sospechosa se envían siempre |
| Eliminar la cuenta | Solicitud → enlace al correo (30 min) → reautenticación. Anonimiza `Usuario` (conserva el identificador), elimina credenciales, MFA, Google y tokens, revoca sesiones y **conserva las mediciones desidentificadas**. Sale de los grupos donde es integrante; si administra uno, la eliminación se bloquea hasta transferir el rol o eliminar el grupo |

## 5. Consentimientos

`POLITICA_PRIVACIDAD` al registrarse y `DATOS_EXPERIMENTALES` (autorización para almacenar **sus** mediciones con finalidad académica): sin una
aceptación vigente no se inicia ni se reciben muestras (`CONSENTIMIENTO_REQUERIDO`). Revocar frena nuevas mediciones y no borra lo medido.
Detalle: [PRIVACIDAD_Y_RETENCION.md](../PRIVACIDAD_Y_RETENCION.md).

## 6. Dispositivo

Cadena: Arduino + MAX30100 → Bluetooth o USB → puente de Windows → API → SQL Server ([DISPOSITIVOS_Y_ADQUISICION.md](../DISPOSITIVOS_Y_ADQUISICION.md)).

- «Conectar dispositivo» muestra el estado real (puente detenido, Bluetooth desconectado, conectado sin datos, conectado), distinto del estado
  administrativo (operativo, en mantenimiento, fuera de servicio, descomisionado). Solo un equipo **operativo** mide.
- **Uso del equipo (DEC-01):** con el modo compartido la cuenta individual usa el equipo aunque esté asignado a una institución, sin cambiar
  su titularidad; con el modo restringido usa solo equipos sin institución.
- **Control temporal:** una sola cuenta controla el equipo a la vez. Se toma con «Usar dispositivo» (configuración del puente) o al iniciar la
  medición; solo quien controla ve las lecturas en vivo y da órdenes al puente. Sin medición vence a los 5 min (o 30 s sin la pantalla
  abierta); al guardar o cancelar la medición el equipo queda libre.
- El identificador del equipo lo informa el firmware (EEPROM), no el puerto COM.

## 7. Mediciones

**Configuración:** modo *Oximetría* (BPM y SpO₂) o *Glucosa (experimental)*; alimentación *En ayunas*, *Después de comer* o *Comida sin
informar* (opcionalmente fecha y hora de la última comida); datos opcionales de esa medición (edad y sexo, sin modificar el perfil) y
observaciones. Para iniciar: consentimiento vigente, equipo operativo atendido por el puente y libre; para glucosa, una **regla de la matriz
aplicable** (la elige siempre el backend por edad, sexo y condición de comida; sin regla no se inicia).

**Ciclo de vida:** `PENDIENTE → ADQUIRIENDO → PROCESANDO → COMPLETADA | INVALIDA`; `CANCELADA` desde las fases previas; transiciones atómicas.
Solo `COMPLETADA` cuenta para estadísticas. «Guardar medición» toma una lectura estabilizada en una transacción. Una sesión sin actividad
~120 s se cancela por abandono; una medición temporal sin actividad pasa a `INVALIDA` (`TIEMPO_AGOTADO`). Las canceladas e inválidas se ocultan
del historial personal 30 min después (no se borran).

**Valores:** BPM, SpO₂, índice óptico y glucosa **procesados por el firmware**, con la versión del algoritmo; el servidor no calcula glucosa.
Origen visible siempre: *Experimental*, *Sin calibrar* o *DEMO*. **DEMO** es sintético: se consulta y elimina, y queda fuera de estadísticas,
dashboards, avisos y correos. **Referencia capilar:** valor de un glucómetro cargado a mano para una medición de glucosa completada; nunca
reemplaza al informado. La **matriz de referencia** compara el valor con un rango: no es una clasificación clínica.

**Consultas:** dashboard personal (última medición, recientes, accesos rápidos), historial (filtros por fecha, modo, estado, origen y orden;
paginado; detalle), gráficos y evolución (promedios diarios por período, variable, origen y agrupación) y eliminación solo de DEMO.

## 8. Consejos para personas con diabetes

Artículos educativos en 5 categorías (Alimentación, Hidratación, Actividad física, Control y seguimiento, Cuidado de los pies), buscador sin
tildes ni mayúsculas que exige todas las palabras, filtro por etiqueta y fuentes con enlace; 2 destacados en Inicio y la colección en
`/app/consejos`. Con aviso de que no reemplaza la consulta médica.

## 9. Privacidad

Sin analítica ni scripts de terceros; servicios externos: Google y SMTP. La administración ve agregados. Al eliminar la cuenta, las mediciones
quedan desidentificadas sin plazo automático de borrado. La auditoría guarda IP y cliente de cada evento durante 90 días (la política todavía
dice lo contrario: GL-23).

## 10. Reglas de negocio

1. Una cuenta = un tipo; no cambia.
2. Sin consentimiento de datos experimentales vigente no se mide.
3. Solo mediciones COMPLETADAS entran en estadísticas; DEMO nunca.
4. La matriz la decide el backend; sin regla aplicable no se inicia una medición de glucosa.
5. Compartir el equipo no comparte mediciones ni el control de una sesión ajena.
6. Fechas en hora de Argentina sin zona; la auditoría y los correos usan sus propias reglas de zona.
7. Cada acceso, rechazo o cambio relevante queda en `Auditoria` sin datos de salud.

Mensajes frecuentes: credenciales incorrectas (con bloqueo), cuenta pendiente de verificación, consentimiento requerido, dispositivo no
operativo o en uso, control del dispositivo de otra cuenta, sin regla aplicable, estado del puente, enlace vencido o usado.

## 11. Limitaciones

- No existe un algoritmo de estimación de glucosa en el servidor (`glucoseEstimator` es solo un punto de integración): una medición que
  dependa de él termina `INVALIDA`; nunca se inventa un valor.
- Cuentas anteriores a los consentimientos deben aceptarlos antes de medir.
- Validación externa del texto de la política pendiente.
- El firmware principal usa el 84 % de la RAM del Arduino UNO; no se probó en hardware real.
