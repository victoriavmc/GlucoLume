# Notificaciones

Módulo de avisos de la cuenta: bandeja en la aplicación (`/app/notificaciones`), preferencias (`/app/notificaciones/preferencias`) y correo.
Rediseño del 29/10/2026 en la rama `claude/glucolume-notifications-redesign-ff6c02`. Lo abierto está en [PENDIENTES.md](PENDIENTES.md) (§ «Notificaciones»); lo cerrado, en [HISTORIAL.md](HISTORIAL.md).

Estado de este documento: describe lo **implementado**. Lo **verificado** (con SQL Server 2022 real y datos sintéticos, en una instancia descartable) y lo **pendiente** están separados en §10 y §11. Qué hacer en el servidor: §12.

## 1. Descripción funcional

| Pantalla | Ruta | Qué hace |
|---|---|---|
| Bandeja | `/app/notificaciones` | Encabezado con avisos sin leer, «Marcar todas como leídas» y acceso a «Preferencias». Filtros Todas, No leídas, Seguridad, Recordatorios y Grupo. Avisos agrupados en Hoy, Ayer y Anteriores, «Cargar más» (20 por página) y estados de carga, error con «Reintentar» y vacío. |
| Preferencias | `/app/notificaciones/preferencias` | Canales «En la aplicación» y «Por correo» por aviso, agrupados por categoría, y el horario de los recordatorios (modificar o eliminar la programación). |

- **La tarjeta entera es el control** (un `<button>`): al elegirla se marca como leída (de forma optimista; si el backend falla, vuelve atrás y se informa) y, si el aviso tiene un destino, se navega. Ya no hay enlace «Ver».
- **Tres estados independientes (no se reutiliza uno como indicador de otro):** *no leída* (`fechaLectura` vacía), *leída* (con `fechaLectura`, todavía visible) y *eliminada de la bandeja*
  (`fechaEliminacion`, ya no visible para esa cuenta). Eliminar no marca como leído ni al revés; un aviso eliminado deja de verse y de contarse en `noLeidas`, `total` y los filtros, y no se puede marcar.
- **Menú de acciones por tarjeta (⋮):** «Abrir» (si hay destino), «Marcar como leída» (si no lo está) y, separada por una línea y en rojo de advertencia, «Eliminar de la bandeja». Es un menú accesible
  (botón con `aria-haspopup`, `role="menu"`/`menuitem`, flechas, Inicio, Fin, Escape devuelve el foco, Tab y clic fuera cierran). El menú es un control aparte de la tarjeta: no se anidan botones.
- **Eliminar en bloque («Eliminar…» en el encabezado, separado de «Marcar todas como leídas»):** «Eliminar las leídas» (sin confirmación, no toca las sin leer) y «Vaciar la bandeja…», que **pide
  confirmación** («también las que todavía no leíste. No se puede deshacer.»). La lista y el contador se actualizan al instante y, si el backend falla, vuelven a como estaban.
- **Bandeja vacía:** «No tenés notificaciones» (y con filtros, el mensaje de ese filtro).
- **Destinos:** solo `/app/mediciones`, `/app/grupo`, `/app/seguridad` (y debajo de ellas), rutas que existen en `App.jsx`. El backend descarta otro destino al guardar (`safeUrl`) y la pantalla vuelve a validarlo (`destinoSeguro`): nunca se navega a un texto recibido sin comprobarlo.
- **Accesibilidad:** filtros con el componente `Tabs` (roles `tablist`/`tab`/`tabpanel`, flechas, Inicio y Fin), tarjetas y interruptores con nombre accesible, foco visible, estados de lectura en texto (no solo color).
- **Cuentas institucionales:** solo reciben avisos de Seguridad; no ven Grupo ni Recordatorios.
- **Aviso emergente (cartel + sonido):** sigue igual; ahora consulta solo los no leídos (`soloNoLeidas=true&limite=20`).

## 2. Categorías, avisos y canales

El catálogo vive en `backend/app/models/notificationEvents.py` (también arma el `CHECK` de la base); la pantalla lo refleja en `notificationsCopy.js`. Un test comprueba que no se desalineen.

| Categoría | Aviso | Cuándo | Obligatorio | Correo |
|---|---|---|---|---|
| Seguridad | `INICIO_SESION` | Inicio de sesión desde un equipo nuevo (§6) | No | Su propio interruptor (`Usuario.notificarNuevoInicioSesion`), un correo por acceso |
| Seguridad | `CAMBIO_CONTRASENA` | Se cambia, restablece o agrega la contraseña | **Sí** | `PASSWORD_CAMBIADA`, siempre (flujo existente) |
| Seguridad | `CAMBIO_MFA` | Se activa o desactiva MFA (incluida la recuperación) | **Sí** | `MFA_ACTIVADO` / `MFA_DESACTIVADO`, siempre |
| Seguridad | `ACTIVIDAD_SOSPECHOSA` | Bloqueo de la cuenta o del segundo factor por intentos fallidos | **Sí** | `INTENTO_ACCESO_INUSUAL`, siempre |
| Grupo familiar | `INVITACION_GRUPO` | Te invitan a un grupo | No | Preferencia (antes era incondicional) |
| Grupo familiar | `AGREGADO_GRUPO` | Aceptás una invitación | No | Preferencia |
| Grupo familiar | `NUEVA_ACCION_GRUPO` | Alguien se suma o abandona el grupo | No | Preferencia; el administrador ya recibe su propio correo |
| Grupo familiar | `MEDICION_GRUPO` | Alguien se midió y activó «Aviso de medición» (quién y cuándo, nunca el valor) | No | Preferencia |
| Recordatorios | `RECORDATORIO_MEDICION` | Vence un horario de medición | No | Preferencia (apagado por omisión) |

- **Canales independientes (RN-NOT-07):** `enPagina` y `porCorreo` se guardan y se respetan por separado. Con la página apagada la fila queda con `visible = 0` (no aparece ni se puede marcar) y solo sirve de registro del correo.
- **Obligatorios:** las alertas críticas se muestran siempre en la página; `PUT /preferencias/{evento}` responde `409 AVISO_OBLIGATORIO` y, aunque exista una fila de preferencia apagada, el servicio las entrega. El correo de esas alertas lo envía el flujo de seguridad que las origina (no depende de preferencias, como antes).
- **Mediciones del grupo:** antes compartían el aviso `NUEVA_ACCION_GRUPO`; ahora tienen el suyo. La migración copia la elección previa de cada cuenta. Siguen respetando el permiso individual `notificaMedicion` de cada integrante.

## 3. Reglas de negocio

| Regla | Cómo se cumple |
|---|---|
| **RN-NOT-01** Unicidad | Cada aviso lleva una `claveEvento` (§4). La fila de `NotificacionUsuario` es el aviso **y** su registro de entrega, y el índice único filtrado `UX_NotificacionUsuario_clave (idUsuario, claveEvento) WHERE claveEvento IS NOT NULL` la respalda en la base. Un segundo intento choca con el índice (`IntegrityError`) y no crea fila ni correo. |
| **RN-NOT-02** Recordatorios | Cada ocurrencia se **reserva** antes de enviar con `UPDATE RecordatorioMedicion SET ultimoAviso = :ocurrencia WHERE idUsuario = :id AND (ultimoAviso IS NULL OR ultimoAviso < :ocurrencia)`; solo quien cambia la fila (`rowcount = 1`) envía. Además la ocurrencia es parte de la clave del aviso. Los reintentos son solo del correo (§5). |
| **RN-NOT-03** Seguridad | El inicio de sesión se sigue auditando entero (`LOGIN_*`). Solo se avisa en pantalla desde un equipo nuevo (§6). La auditoría no se convierte en avisos en bloque ni se debilita. |
| **RN-NOT-04** Lectura | Estado por aviso (`fechaLectura`). Marcar es idempotente y no cambia la fecha de lectura ya guardada. «Marcar todas» solo actualiza filas con `idUsuario` = el de la sesión. |
| **RN-NOT-05** Retención | Parametrizable (`NOTIFICATION_READ_RETENTION_DAYS` = 30 y `NOTIFICATION_UNREAD_RETENTION_DAYS` = 365; 0 desactiva). **Automática:** corre una vez por hora dentro del servicio `notifications` (§5; por tandas de 1 000 con tope de 100 tandas por pasada) y elimina los avisos leídos de más de 30 días (y los ocultos por preferencia) y los nunca leídos de más de 365. Los avisos eliminados de la bandeja (RN-NOT-08) se depuran con el plazo de los leídos (30 días desde su creación); las reglas de 30 y 365 días **no cambiaron** y son la depuración **física**, distinta de la eliminación manual. Solo elimina filas de `NotificacionUsuario`; no toca `Auditoria` ni `AuditoriaContexto`. Antes no había política: la tabla crecía sin límite. |
| **RN-NOT-08** Eliminación de la bandeja | Lógica y por destinatario: `UPDATE ... SET fechaEliminacion` sobre filas con `idUsuario` = el de la sesión. La fila **se conserva con su `claveEvento`**: procesar otra vez el mismo hecho (p. ej. el reintento de un recordatorio) no recrea el aviso, pero un hecho nuevo e independiente sí crea uno nuevo. Las acciones masivas son **una sola sentencia y una sola transacción** (con su evento de auditoría `ELIMINAR_NOTIFICACIONES`: alcance y cantidad, nunca el contenido); si algo falla no queda nada a medias. No se toca `Auditoria` ni `AuditoriaContexto`. La depuración física sigue siendo la de RN-NOT-05. |
| **RN-NOT-06** Autorización | La identidad sale siempre de la sesión. Todas las consultas filtran por `idUsuario`. Un aviso ajeno o inexistente responde igual: `404 NOTIFICACION_NO_ENCONTRADA`. |
| **RN-NOT-07** Canales | Ver §2. El aviso de la página se confirma **antes** de intentar el correo; una falla SMTP queda en `estadoCorreo = FALLIDO` y no lo quita. |

## 4. Generación y deduplicación

`userNotifications.notify(..., clave=...)`. La clave identifica el hecho de origen **para esa cuenta**; el índice garantiza una fila por (cuenta, clave).

| Aviso | Clave |
|---|---|
| Recordatorio | `RECORDATORIO_MEDICION:<fecha-hora de la ocurrencia>` |
| Equipo nuevo | `INICIO_SESION:<huella del equipo>` |
| Contraseña / MFA | `CAMBIO_CONTRASENA:<instante del cambio>` / `CAMBIO_MFA:<instante>` |
| Actividad sospechosa | `ACTIVIDAD_SOSPECHOSA:BLOQUEO:<fin del bloqueo>` (y `BLOQUEO_MFA:`) |
| Invitación | `INVITACION_GRUPO:<idGrupoUsuario>` |
| Incorporación | `AGREGADO_GRUPO:<idGrupoUsuario>` |
| Novedad del grupo | `NUEVA_ACCION_GRUPO:<idGrupoUsuario>:SUMA` o `:SALE` |
| Medición del grupo | `MEDICION_GRUPO:<idUsuario>:<fin de la medición>` |

Sin `clave`, el aviso se trata como hecho único (clave aleatoria): ningún flujo del sistema lo hace.

## 5. Recordatorios

- **Configuración:** `PUT /notificaciones/recordatorio`. Modo `INTERVALO` (cada 1, 2, 3, 4, 6, 8, 12 o 24 horas, contadas desde que se guarda), `HORARIOS` (hasta 6 horas fijas `HH:MM`, todos los días) o `NINGUNO`. **Eliminar la programación = `NINGUNO`**: la API no tiene `DELETE` sobre la tabla. Al guardar, `ultimoAviso` pasa a «ahora»: nunca se dispara un horario anterior al cambio. Solo cuentas individuales.
- **Quién los genera: el servicio `notifications`** (`compose.yaml`; `python -m app.jobs.reminders --loop`, misma imagen del backend, sin puertos). Cada `NOTIFICATIONS_INTERVAL_SECONDS` (60 por defecto; mínimo 10, no se puede apagar) procesa los recordatorios vencidos, reintenta los correos que fallaron y, una vez por hora, depura la bandeja. **Es lo que hace que el recordatorio llegue a su hora aunque nadie tenga la aplicación abierta.** Antes ese proceso no existía en Compose: el recordatorio solo se generaba cuando alguien abría la bandeja (`GET /notificaciones` con `desplazamiento = 0`, que sigue revisando el horario de su propia cuenta como respaldo; el cartel de avisos solo consulta con la pestaña visible). Es **otro** servicio que `lifecycle` a propósito: `lifecycle` elimina cuentas institucionales y suele estar apagado (`ACCOUNT_LIFECYCLE_INTERVAL_SECONDS=0`); acoplarlos dejaba los recordatorios sin generar. La reserva atómica hace seguro que corran varias instancias, el servicio y la bandeja a la vez. `python -m app.jobs.reminders --health` es su healthcheck (marca de vida).
- **Si el proceso estuvo apagado:** se envía **un** recordatorio (el horario cumplido más reciente de hoy o de ayer), no uno por cada horario perdido.
- **Reintentos de correo:** el correo se envía en un hilo aparte y anota `estadoCorreo` (`PENDIENTE` → `ENVIADO` | `FALLIDO`) e `intentosCorreo`. Un correo `FALLIDO` se reintenta hasta **5 intentos totales**, dentro de las 6 horas y **con espera creciente** contada desde la creación del aviso (el 2.º intento no antes de 1 min, el 3.º de 5 min, el 4.º de 15 min y el 5.º de 1 h): o bien al procesar otra vez el mismo hecho, o bien en las pasadas del servicio (que reintentan **antes** de procesar los recordatorios nuevos). Sin la espera, una caída del SMTP agotaba los intentos en un par de pasadas y el correo no salía nunca (se vio en la prueba con SQL Server real). Solo se reenvía el correo: el aviso de la página no se vuelve a crear. Si la cuenta apagó el correo entretanto, no se reintenta.
- **Zona horaria:** la política del backend es única, **hora de Argentina** (`app/utils/timeZone.py`). Los horarios se interpretan en esa zona; no se guarda una zona por usuario.

## 6. Seguridad: cuándo hay aviso visible

Criterio de equipo nuevo (`services/knownAccess.py`, tabla `AccesoConocido`):

1. Se reconoce el equipo por **navegador + sistema operativo + tipo de equipo** (huella SHA-256), nunca por IP. No se guarda la IP ni el agente de usuario completo.
2. Es **nuevo** si esa combinación no está registrada para la cuenta **y** la cuenta ya tenía al menos un acceso registrado.
3. El **primer** acceso de una cuenta solo se registra: no hay contra qué compararlo, así que no se afirma nada. Lo mismo para las cuentas existentes al desplegar: su primer inicio de sesión después de la migración arma la línea base.
4. Sin datos del cliente no se registra ni se avisa.
5. Un equipo se avisa una sola vez. El texto no incluye la IP.

Sigue igual: cada inicio de sesión (con o sin aviso) queda en `Auditoria` (`LOGIN_PWD`, `LOGIN_GOOGLE`, `*_MFA`, `*_MFA_PENDIENTE`) y el correo «nuevo inicio de sesión» sale en cada acceso mientras la cuenta no lo apague.

## 7. Endpoints (`/api/v1/notificaciones`)

| Método y ruta | Cambio | Detalle |
|---|---|---|
| `GET /` | **Modificado** | Parámetros `categoria` (`SEGURIDAD`, `GRUPO`, `RECORDATORIO`), `soloNoLeidas`, `limite` (1–50, 20 por omisión), `desplazamiento` (≥ 0). Respuesta `{noLeidas, total, hayMas, notificaciones[{idNotificacion, evento, categoria, titulo, mensaje, url, fechaCreacion, leida}]}`. `noLeidas` ignora el filtro. Con `desplazamiento = 0` revisa el recordatorio propio. Parámetros inválidos: `422`. |
| `POST /{id}/leer` | **Modificado** | Responde `{noLeidas, marcadas}` (antes devolvía toda la bandeja). Ajeno o inexistente: `404 NOTIFICACION_NO_ENCONTRADA` (antes `200`). |
| `POST /leer-todas` | **Modificado** | Responde `{noLeidas, marcadas}`; solo avisos de la sesión. |
| `DELETE /{id}` | **Nuevo** | Quita un aviso propio de la bandeja (eliminación lógica). Responde `{noLeidas, eliminadas}`. Ajeno, inexistente o ya eliminado: `404 NOTIFICACION_NO_ENCONTRADA`, sin distinguirlos. |
| `DELETE /?alcance=leidas\|todas` | **Nuevo** | Quita de la bandeja los avisos leídos, o todos, de la cuenta autenticada, en una transacción. `alcance` es **obligatorio** (sin él `422`: no hay un valor que vacíe la bandeja por omisión). Responde `{noLeidas, eliminadas}` y deja el evento de auditoría. |
| `GET /preferencias` | **Modificado** | Cada preferencia suma `categoria` y `obligatoria`; ahora son 9. |
| `PUT /preferencias/{evento}` | **Modificado** | Admite los 9 avisos. Obligatorios: `409 AVISO_OBLIGATORIO`. |
| `PUT /recordatorio` | Sin cambio | `NINGUNO` elimina la programación. |

Comandos: `python -m app.jobs.reminders --loop | --health | ejecutar | depurar | previsualizar` (`depurar` es el mismo borrado que hace solo el servicio `notifications` cada hora, a demanda).

## 8. Cambios de esquema

**v3 (eliminación de la bandeja):** [GlucoLume_notificaciones_v3.sql](../database/reference/GlucoLume_notificaciones_v3.sql) agrega `NotificacionUsuario.fechaEliminacion` (`datetime2(3) NULL`) y nada más: no modifica ni borra
filas, es idempotente, exige `-v CONFIRMAR="ACTUALIZAR_NOTIFICACIONES_V3"` y se aplica **después** de v2. No hacen falta permisos nuevos (es un `UPDATE`). No se encontró ningún mecanismo de eliminación lógica previo
para los avisos: `visible` significa «la cuenta apagó el canal de la página» y no se reutilizó. El backend exige la columna (`schemaCompat`): con v2 sin v3, Notificaciones queda «no disponible» en lugar de fallar.
`GlucoLume_DB_v5.sql` ya la incluye para instalaciones nuevas.

**v2:** script versionado e idempotente: [GlucoLume_notificaciones_v2.sql](../database/reference/GlucoLume_notificaciones_v2.sql). Se aplica **después** de `GlucoLume_notificaciones_usuario.sql`, con respaldo previo y de preferencia primero en una copia restaurada:

```
sqlcmd -S <servidor> -d <base> -I -i GlucoLume_notificaciones_v2.sql -v CONFIRMAR="ACTUALIZAR_NOTIFICACIONES_V2"
```

- `NotificacionUsuario`: columnas `claveEvento`, `visible` (por omisión 1), `estadoCorreo`, `intentosCorreo` (por omisión 0); índice único filtrado `UX_NotificacionUsuario_clave`; `CHECK` de `estadoCorreo`.
- `CHECK` de `evento` en `NotificacionUsuario` y `PreferenciaNotificacion`: los 9 avisos.
- Tabla nueva `AccesoConocido` (clave única `(idUsuario, huella)`).
- **Datos existentes:** cada aviso anterior recibe la clave `LEGADO:<id>` y su `fechaCreacion` se corrige en −3 h. Causa: la columna se completaba con `sysutcdatetime()` (UTC) pero la API la interpreta como hora de Argentina, así que se veía **3 horas adelantada**. Solo toca filas sin clave: volver a correr el script no resta otra vez. Desde ahora el backend escribe la fecha explícitamente en hora de Argentina.
- Se copia la elección de canales de `NUEVA_ACCION_GRUPO` a `MEDICION_GRUPO` donde falte.
- **Permisos:** `GlucoLume_permisos.sql` concede `DELETE` sobre `NotificacionUsuario` **solo** al rol de conservación (`rol_glucolume_retencion`), para la depuración (servicio `notifications` con `DB_JOBS_USER`, o `depurar`). La API sigue sin `DELETE`; sin `DB_JOBS_USER` la depuración se registra como advertencia cada hora y los recordatorios siguen funcionando.
- **Compatibilidad:** mientras el script no esté aplicado, el backend deja «Notificaciones» como no disponible (`schemaCompat`: comprueba tablas y la columna `claveEvento`) y no falla. Los equipos nuevos no se avisan hasta que exista `AccesoConocido`.
- No se borra ni se reconstruye nada. Reversión documentada en el encabezado del script (se pierden los datos nuevos).

## 9. Causas de los problemas detectados

| # | Problema | Causa real (verificada en el código) |
|---|---|---|
| 1 | Recordatorios repetidos en intervalos cortos | `processReminders` leía `ultimoAviso`, enviaba y escribía sin una reserva atómica, y se ejecutaba desde `GET /notificaciones` (el cartel de avisos lo consulta cada 30 s, más al volver a la pestaña, más tras cada «marcar como leído») **y** desde el job. Dos ejecuciones simultáneas veían la misma ocurrencia vencida y las dos enviaban. Reproducido con el código anterior: 6 ejecuciones en paralelo crearon **6 avisos** del mismo recordatorio (3 de 3 corridas). No había clave de unicidad. |
| 2 | Aviso en cada inicio de sesión | `_authenticatedResponse` llamaba a `notify(INICIO_SESION)` en cada acceso, sin criterio. |
| 3 | Todos los avisos iguales, sin jerarquía | La tabla no tenía categoría ni la pantalla distinguía eventos. |
| 4 | Enlace «Ver» | La tarjeta no era interactiva; el destino era un texto libre guardado en la base, sin validar. |
| 5 | Pantalla demasiado extensa | Bandeja, canales y horario en una sola página de formulario (tope 1160 px) con paneles apilados. No encontré una regla CSS que alinee el contenido a la derecha: la página ya se centraba (`margin-inline: auto`); el efecto percibido era una sola columna larga junto a la barra lateral. Se rediseñó en dos pantallas con ancho de lectura de 1040 px; verificado en un navegador a 1440 px y a 375 px (sin desborde horizontal). |
| 6 | Hora de los avisos 3 h adelantada | `fechaCreacion` en UTC interpretada como hora de Argentina (§8). |
| 7 | Sin paginación | `inbox()` devolvía como máximo 50 sin forma de ver el resto. |
| 8 | Sin retención | No existía política: las filas nunca se borraban. |
| 9 | Marcar un aviso ajeno respondía `200` | `markRead` no distinguía «no es tuyo» de «no existe». |
| 10 | **Los recordatorios no llegaban a su hora** | Ningún proceso los generaba: en Compose solo existía `lifecycle` y `reminders` no estaba agendado. El recordatorio se creaba únicamente cuando alguien abría la bandeja con la pestaña visible. En la instalación en uso (solo lectura) el único contenedor programado, `lifecycle`, está desactivado y no hay ningún otro proceso que revise horarios. Reproducido con SQL Server real: con el horario vencido y nadie conectado, no se generó nada hasta arrancar el servicio. |
| 11 | `lifecycle` no sirve para esto | En la instalación en uso corre con `ACCOUNT_LIFECYCLE_INTERVAL_SECONDS=0` (desactivado a propósito: elimina cuentas) y sin `DB_JOBS_USER`. La depuración de avisos que se había puesto ahí **nunca corría** y, de activarse `lifecycle`, habría quedado atada a una tarea destructiva. Se sacó de `lifecycle`, que volvió a su estado original. |
| 12 | Correo fallido sin reintento útil | Los reintentos (3) ocurrían en pasadas consecutivas: una caída del SMTP de pocos minutos los agotaba y el correo quedaba `FALLIDO` para siempre. Ahora son 5 con espera creciente (§5). |
| 13 | Faltaban avisos de grupo | Quien invitó no se enteraba de un rechazo, y quien era desvinculado por el administrador (y los demás integrantes) no recibían aviso en la página. |
| 14 | **La bandeja no se podía limpiar** | Solo existían leído y no leído: no había eliminación de ningún tipo (la única baja era la depuración física por antigüedad, que ni siquiera corría con `lifecycle` apagado), así que todo aviso viejo seguía a la vista aunque estuviera leído. No existía ningún mecanismo previo de eliminación lógica para los avisos (`visible` es el canal de la página, no una baja). Se agregó `fechaEliminacion` (RN-NOT-08, §8). |

## 10. Pruebas

Corridas del 29 y 30/10/2026 (Windows, Python 3.14, Node 24, Docker 29, **SQL Server 2022 CU16 real** en una instancia descartable con datos sintéticos). Scripts, entorno y salidas
completas en [evidencias/notificaciones](evidencias/notificaciones/README.md). **No se tocó la instalación en uso**: de ella solo se hicieron consultas de lectura (catálogo, conteos y
horarios) para el diagnóstico.

### 10.1 Extremo a extremo con SQL Server real (evento → backend → SQL Server → API → frontend)

Backend en su imagen de Docker (`glucolume/backend:dev` con el código de la rama), SQL Server real, SMTP de prueba con STARTTLS y el frontend en un navegador real.

| Escenario | Resultado | Evidencia |
|---|---|---|
| Seguridad: equipo habitual / equipo nuevo / auditoría / contraseña / MFA / bloqueo / preferencias / autorización / lectura | **20/20** | [e2e_security.txt](evidencias/notificaciones/resultados/e2e_security.txt) |
| Grupo: invitación recibida, rechazada y aceptada, nuevo integrante, desvinculación voluntaria y por el administrador, medición compartida con y sin permiso, sin duplicados | **13/13** | [e2e_groups.txt](evidencias/notificaciones/resultados/e2e_groups.txt) |
| Recordatorios: sin servicio (no llega), con servicio (llega con correo), dos servicios simultáneos, periódico, cambio de horario, desactivar, SMTP caído y reintento | **13/13** | [e2e_reminders.txt](evidencias/notificaciones/resultados/e2e_reminders.txt) |
| Migración v2 sobre el esquema anterior con datos heredados, idempotencia, permisos de API y de procesos, índice único, `CHECK` | Correcta (ver archivo) | [sqlserver_migracion_y_permisos.txt](evidencias/notificaciones/resultados/sqlserver_migracion_y_permisos.txt) |
| Persistencia tras reiniciar SQL Server y el backend; `lifecycle`; depuración con cuenta de procesos y con la de la API; servicio `notifications` y su healthcheck | Correcto (ver archivo) | [servicios_y_persistencia.txt](evidencias/notificaciones/resultados/servicios_y_persistencia.txt) |
| Eliminar de la bandeja: avisos de eventos reales, eliminar uno, persistencia tras una sesión nueva, contadores, aislamiento entre cuentas (404), eliminar leídas, vaciar, hecho repetido vs. hecho nuevo, auditoría, vaciado de 5 000 avisos en una transacción | **24/24** | [e2e_delete.txt](evidencias/notificaciones/resultados/e2e_delete.txt) |
| Depuración física de lo eliminado con la cuenta de procesos, pasada completa de `lifecycle` (no toca avisos), auditoría intacta, la API puede eliminar lógicamente pero no borrar | Correcto (ver archivo) | [depuracion_y_lifecycle.txt](evidencias/notificaciones/resultados/depuracion_y_lifecycle.txt) |
| `GlucoLume_notificaciones_v3.sql` sobre una base con v2 + `GlucoLume_DB_v5.sql` nuevo (instalación limpia) en SQL Server 2022 | Sin errores; 38 tablas; `fechaEliminacion` presente en ambas | (la usa la base del punto siguiente) |
| Suite de Notificaciones (107 pruebas) **contra SQL Server real** (`tests/test_user_notifications_sqlserver.py`, mismas pruebas que SQLite, con hilos de conexiones distintas) | **107 pasaron** | ejecución del 30/10 |
| Frontend en un navegador real contra ese backend (cuenta sintética `ana`) | Bandeja con datos reales, filtro Seguridad, fecha corregida a hora de Argentina, la tarjeta abrió `/app/seguridad` y la fila quedó leída en SQL Server, interruptor de preferencia guardado en SQL Server; todas las llamadas `200`, sin errores en la consola ni de CORS | capturas y registro de red de la sesión |
| Eliminar desde la interfaz real contra ese backend: menú ⋮ de una tarjeta → «Eliminar de la bandeja» (el aviso desaparece, el contador baja y en SQL Server la fila queda con `fechaEliminacion` y sin `fechaLectura`); «Eliminar…» → «Vaciar la bandeja…» con confirmación → «No tenés notificaciones»; al **recargar** sigue vacía y SQL Server muestra las 7 filas de `ana` eliminadas y 1 evento de auditoría | Correcto; sin errores en la consola | capturas y consulta a SQL Server de la sesión |

Hallazgos de esas pruebas (corregidos): los recordatorios no se generaban sin la aplicación abierta (§9, #10); los reintentos del correo se agotaban en dos pasadas (§9, #12); faltaban
los avisos de rechazo y de desvinculación (§9, #13); la depuración de avisos no corría con `lifecycle` apagado (§9, #11).

### 10.2 Suites automáticas

| Conjunto | Resultado |
|---|---|
| Backend, suite completa (`python -m pytest tests`, SQLite) | **2 065 pasaron, 2 fallaron, 187 omitidas** (18 min). Las 2 fallas **ya fallaban con el código anterior** y no son de este módulo: `test_toda_exportacion_futura_pasa_por_audited_export` (ya listada como P3 en PENDIENTES) y `test_ningun_cuerpo_de_peticion_acepta_campos_de_mas` (`PatientExportRequest`, `PersonnelExportRequest`). Las omitidas son las que exigen SQL Server real (entre ellas las 107 de Notificaciones, que sí se corrieron aparte contra SQL Server real, ver 10.1) o herramientas ausentes. |
| Backend, `tests/test_user_notifications.py` | 107 pasaron (antes de este rediseño: 28). SQLite y SQL Server real: el mismo resultado. |
| Frontend, suite completa (`npx vitest run`) | **770/770 pasaron** (57 archivos). |
| Frontend, módulo | 53 pruebas en 4 archivos (bandeja 21, entre ellas 9 de eliminar de la bandeja: menú y teclado, eliminar uno, persistencia al recargar con un backend con estado, leído vs. eliminado, rollback, eliminar leídas, vaciar con confirmación y cancelación, vaciado fallido, acciones deshabilitadas; preferencias 10; catálogo y destinos; cartel de avisos). |
| Reproducción del defecto de duplicados | Con el código anterior (extraído de `HEAD`), 6 hilos que procesan la misma ocurrencia crearon 6 avisos (3 de 3 corridas); con el código nuevo, 1. |
| Revisión visual manual | Bandeja a 1440 px y a 375 px, y preferencias a 375 y 1440 px, en un navegador real: sin desborde horizontal. La prueba responsive **no está automatizada**. |

Cobertura por requisito:

| # | Requisito | Prueba |
|---|---|---|
| 1 | Generar un aviso válido | `test_un_aviso_valido_…`, `test_un_destino_externo_o_inventado_no_se_guarda` |
| 2 | Evitar duplicados | `test_el_mismo_hecho_procesado_dos_veces_…`, `test_la_base_rechaza_dos_filas_con_la_misma_clave_…`, `test_la_misma_incorporacion_procesada_dos_veces_…` |
| 3 | Procesamiento concurrente | `test_varias_sesiones_…_dejan_un_solo_aviso`, `test_varias_ejecuciones_simultaneas_reservan_…` (6 hilos) |
| 4 | Recordatorios con horarios | `test_los_horarios_configurados_avisan_exactamente_a_esa_hora`, `test_horarios_avisan_el_ultimo_cumplido_una_sola_vez` |
| 5 | Modificar y eliminar horarios | `test_modificar_el_horario_…`, `test_eliminar_la_programacion_…`; frontend «elimina la programación guardada» |
| 6 | Reintentos sin duplicar | `test_reintentar_el_mismo_hecho_…`, `test_el_proceso_reintenta_el_correo_…`, `test_no_se_reintenta_si_…` |
| 7 | Canales independientes | `test_apagar_la_pagina_no_apaga_el_correo_y_viceversa`; frontend «guarda solo ese canal» |
| 8 | Lectura individual | `test_la_lectura_individual_se_conserva_…`; frontend «optimista… vuelve atrás» |
| 9 | Lectura masiva | `test_marcar_todas_solo_afecta_a_la_cuenta_autenticada`; frontend «marcar todas… se revierte» |
| 10 | Filtros y paginación | `test_la_bandeja_pagina_…`, `test_filtra_por_categoria_…`, `test_la_bandeja_por_ruta_filtra_pagina_…`; frontend «filtros» y «carga más» |
| 11 | Acceso a avisos ajenos | `test_un_usuario_no_puede_leer_ni_marcar_los_avisos_de_otro_…` (404 idéntico a inexistente) |
| 12 | Falla de correo | `test_una_falla_smtp_no_quita_el_aviso_de_la_pagina_…` |
| 13 | Destinos autorizados | frontend «destino autorizado» y «destino no autorizado», `notificationsCopy.test.js` |
| 14 | Carga, vacío y error | frontend «estado vacío», «estado de carga … reintentar», «muestra el error de carga» |
| 15 | Responsive | **No automatizada** (jsdom no calcula estilos). Revisión manual en un navegador real (Vite + datos simulados) a 1440 y 375 px: sin desborde horizontal. |

Además: equipo nuevo (`test_un_equipo_nuevo_avisa_una_sola_vez_…`, `test_todos_los_inicios_de_sesion_siguen_auditados_…`), alertas obligatorias, retención (no toca la auditoría), contratos alineados con el catálogo y análisis estático de la migración.

## 11. Limitaciones y pendientes reales

- **La instalación en uso NO está migrada ni tiene el servicio `notifications`** (se comprobó solo en lectura: tiene las tablas v1, sin `claveEvento` ni `AccesoConocido`, y `lifecycle` está desactivado). Mientras no se aplique §12, el backend nuevo deja Notificaciones como «no disponible». Los pasos de §12 se ensayaron en una instancia descartable, no en la real.
- **Entrega real por Gmail no verificada:** el envío se probó contra un SMTP de prueba con STARTTLS y certificado verificado (mismo código y mismo transporte), no contra el SMTP real configurado: no hay credenciales válidas para usar en la prueba. Lo que no se comprueba con el SMTP de prueba: la aceptación por parte del proveedor, SPF/DKIM y la bandeja de entrada del destinatario.
- La medición completada que dispara `MEDICION_GRUPO` se probó llamando a `notifyGroupMeasurement` (la función que invocan `measurement.py` y `telemetry.py`) contra SQL Server real, no completando una medición real con el dispositivo.
- Los avisos de las cuentas de la plataforma (`platform.py`: cambios de contraseña) y de las instituciones no se incorporaron a la bandeja; solo siguen enviando su correo.
- No hay zona horaria por usuario: todo es hora de Argentina.
- La línea base de equipos conocidos se arma en el primer inicio de sesión posterior a la migración; hasta entonces no hay aviso de equipo nuevo para esa cuenta.
- «Cargar más» usa desplazamiento: si llegan avisos nuevos entre una carga y otra, la pantalla descarta los repetidos pero un aviso podría tardar en aparecer hasta recargar.
- Un recordatorio reservado cuyo aviso no pudo guardarse (error de base en ese instante) no se recupera; el siguiente horario sí se envía.
- Sin pruebas automáticas de la apariencia responsive (ver §10).

## 12. Pasos para aplicar los cambios al servidor

La instalación en uso **todavía no tiene** nada de esto (se comprobó en lectura: tablas v1, sin `claveEvento` ni `AccesoConocido`, sin servicio `notifications`, `lifecycle` desactivado y sin `DB_JOBS_USER`).
Hasta que se apliquen, el backend nuevo deja Notificaciones como «no disponible» (no falla). Orden recomendado, **primero en una copia restaurada**:

1. **Respaldo** restaurable de la base (`GlucoLume_respaldo.ps1` o `BACKUP ... WITH CHECKSUM`) y, de preferencia, ensayar los pasos 2 y 3 en una copia.
2. **Esquema:** con `sqlcmd -I`, `GlucoLume_notificaciones_v2.sql -v CONFIRMAR="ACTUALIZAR_NOTIFICACIONES_V2"` y **después** `GlucoLume_notificaciones_v3.sql -v CONFIRMAR="ACTUALIZAR_NOTIFICACIONES_V3"` (eliminación de la bandeja; si la base no tenía las tablas, antes `GlucoLume_notificaciones_usuario.sql`). Cada uno es idempotente y no borra filas.
3. **Permisos:** volver a aplicar `GlucoLume_permisos.sql` (agrega el `DELETE` de `NotificacionUsuario` para el rol de conservación) y comprobar con `GlucoLume_permisos_verificar.sql`.
4. **Cuenta de procesos:** definir `DB_JOBS_USER` y `DB_JOBS_PASSWORD` en el `.env` (cuenta distinta de la de la API, miembro de `rol_glucolume_retencion`). Sin ella los recordatorios funcionan pero la bandeja no se depura.
5. **Variables (opcionales):** `NOTIFICATIONS_INTERVAL_SECONDS` (60), `NOTIFICATION_READ_RETENTION_DAYS` (30) y `NOTIFICATION_UNREAD_RETENTION_DAYS` (365). No tocar `ACCOUNT_LIFECYCLE_INTERVAL_SECONDS`: son independientes.
6. **Imágenes y servicios:** reconstruir `backend` y `frontend`, y levantar el servicio nuevo: `docker compose up -d --build backend frontend notifications`. Comprobar `docker compose ps` (`notifications` en `healthy`) y `docker compose logs notifications`.
7. **Verificar:** abrir Notificaciones; configurar un recordatorio a un minuto y comprobar que llega **sin** tener la aplicación abierta; revisar en `NotificacionUsuario` que `estadoCorreo` pase a `ENVIADO`.
8. Sin Docker (Windows): agendar `python -m app.jobs.reminders --loop` como proceso permanente (o `ejecutar` cada minuto con una tarea programada).
