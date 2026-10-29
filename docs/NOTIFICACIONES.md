# Notificaciones

Módulo de avisos de la cuenta: bandeja en la aplicación (`/app/notificaciones`), preferencias (`/app/notificaciones/preferencias`) y correo.
Rediseño del 29/10/2026 en la rama `claude/glucolume-notifications-redesign-ff6c02`. Lo abierto está en [PENDIENTES.md](PENDIENTES.md) (§ «Notificaciones»); lo cerrado, en [HISTORIAL.md](HISTORIAL.md).

Estado de este documento: describe lo **implementado**. Lo **verificado** y lo **pendiente** están separados en §10 y §11. Nada de esto se ejecutó contra SQL Server real: las pruebas usan SQLite.

## 1. Descripción funcional

| Pantalla | Ruta | Qué hace |
|---|---|---|
| Bandeja | `/app/notificaciones` | Encabezado con avisos sin leer, «Marcar todas como leídas» y acceso a «Preferencias». Filtros Todas, No leídas, Seguridad, Recordatorios y Grupo. Avisos agrupados en Hoy, Ayer y Anteriores, «Cargar más» (20 por página) y estados de carga, error con «Reintentar» y vacío. |
| Preferencias | `/app/notificaciones/preferencias` | Canales «En la aplicación» y «Por correo» por aviso, agrupados por categoría, y el horario de los recordatorios (modificar o eliminar la programación). |

- **La tarjeta entera es el control** (un `<button>`): al elegirla se marca como leída (de forma optimista; si el backend falla, vuelve atrás y se informa) y, si el aviso tiene un destino, se navega. Ya no hay enlace «Ver».
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
| **RN-NOT-05** Retención | Parametrizable (`NOTIFICATION_READ_RETENTION_DAYS` = 180 y `NOTIFICATION_UNREAD_RETENTION_DAYS` = 365; 0 desactiva). Solo elimina filas de `NotificacionUsuario`; no toca `Auditoria` ni `AuditoriaContexto`. Antes no había política: la tabla crecía sin límite. |
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
- **Quién los envía:** `python -m app.jobs.reminders ejecutar` (recomendado, cada ~5 minutos; llega también por correo) y, como **respaldo**, `GET /notificaciones` con `desplazamiento = 0` revisa el horario de la propia cuenta. La reserva atómica hace seguro que corran a la vez. El job **no está agendado en Compose**: lo agenda quien administra el servidor (ver [DESPLIEGUE.md](DESPLIEGUE.md)). Sin job, un recordatorio por correo solo sale si la persona tiene la aplicación abierta.
- **Si el proceso estuvo apagado:** se envía **un** recordatorio (el horario cumplido más reciente de hoy o de ayer), no uno por cada horario perdido.
- **Reintentos de correo:** el correo se envía en un hilo aparte y anota `estadoCorreo` (`PENDIENTE` → `ENVIADO` | `FALLIDO`) e `intentosCorreo`. Un correo `FALLIDO` se reintenta hasta 3 intentos totales, dentro de las 6 horas: o bien al procesar otra vez el mismo hecho, o bien en la siguiente pasada del job (que reintenta **antes** de procesar los recordatorios nuevos). Solo se reenvía el correo: el aviso de la página no se vuelve a crear. Si la cuenta apagó el correo entretanto, no se reintenta.
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
| `GET /preferencias` | **Modificado** | Cada preferencia suma `categoria` y `obligatoria`; ahora son 9. |
| `PUT /preferencias/{evento}` | **Modificado** | Admite los 9 avisos. Obligatorios: `409 AVISO_OBLIGATORIO`. |
| `PUT /recordatorio` | Sin cambio | `NINGUNO` elimina la programación. |

Comandos: `python -m app.jobs.reminders ejecutar | depurar | previsualizar`.

## 8. Cambios de esquema

Script versionado e idempotente: [GlucoLume_notificaciones_v2.sql](../database/reference/GlucoLume_notificaciones_v2.sql). Se aplica **después** de `GlucoLume_notificaciones_usuario.sql`, con respaldo previo y de preferencia primero en una copia restaurada:

```
sqlcmd -S <servidor> -d <base> -I -i GlucoLume_notificaciones_v2.sql -v CONFIRMAR="ACTUALIZAR_NOTIFICACIONES_V2"
```

- `NotificacionUsuario`: columnas `claveEvento`, `visible` (por omisión 1), `estadoCorreo`, `intentosCorreo` (por omisión 0); índice único filtrado `UX_NotificacionUsuario_clave`; `CHECK` de `estadoCorreo`.
- `CHECK` de `evento` en `NotificacionUsuario` y `PreferenciaNotificacion`: los 9 avisos.
- Tabla nueva `AccesoConocido` (clave única `(idUsuario, huella)`).
- **Datos existentes:** cada aviso anterior recibe la clave `LEGADO:<id>` y su `fechaCreacion` se corrige en −3 h. Causa: la columna se completaba con `sysutcdatetime()` (UTC) pero la API la interpreta como hora de Argentina, así que se veía **3 horas adelantada**. Solo toca filas sin clave: volver a correr el script no resta otra vez. Desde ahora el backend escribe la fecha explícitamente en hora de Argentina.
- Se copia la elección de canales de `NUEVA_ACCION_GRUPO` a `MEDICION_GRUPO` donde falte.
- **Permisos:** `GlucoLume_permisos.sql` concede `DELETE` sobre `NotificacionUsuario` **solo** al rol de conservación (`rol_glucolume_retencion`), para `depurar`. La API sigue sin `DELETE`.
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

## 10. Pruebas

Resultados de la corrida del 29/10/2026 (Windows, Python 3.14, Node 24, SQLite temporal). Ninguna prueba usó SQL Server real.

| Conjunto | Resultado |
|---|---|
| Backend, suite completa (`python -m pytest tests`) | **2 040 pasaron, 2 fallaron, 80 omitidas** (24 min). Las 2 fallas **ya fallaban con el código anterior** y no son de este módulo: `test_toda_exportacion_futura_pasa_por_audited_export` (`csvExport.py` y otros, ya listado como P3 en PENDIENTES) y `test_ningun_cuerpo_de_peticion_acepta_campos_de_mas` (`PatientExportRequest`, `PersonnelExportRequest`). Las 80 omitidas son las que exigen SQL Server real o herramientas ausentes. |
| Backend, `tests/test_user_notifications.py` | 82 pasaron (antes 28). |
| Backend, `test_reference_schema.py` y `test_permisos_sql.py` | Pasan. Una primera corrida completa mostró 5 fallas de `test_reference_schema` causadas por este cambio (el esquema consolidado `GlucoLume_DB_v5.sql` no tenía las columnas, el `CHECK`, el índice ni la tabla nuevos): se actualizó `GlucoLume_DB_v5.sql` y la cantidad de tablas esperada (37 → 38), y la segunda corrida completa ya no las muestra. |
| Frontend, suite completa (`npx vitest run`) | **761/761 pasaron** (57 archivos). Una primera corrida simultánea con la suite del backend tuvo 7 fallas por demoras (máquina saturada); repetida sola, pasa completa. |
| Frontend, módulo | 44 pruebas en 4 archivos: bandeja (12), preferencias (10), catálogo y destinos (`notificationsCopy.test.js`), cartel de avisos (`NotificationToasts.test.jsx`). |
| Reproducción del defecto | Con el código anterior (extraído de `HEAD`), 6 hilos que procesan la misma ocurrencia crearon 6 avisos (3 de 3 corridas); con el código nuevo, 1. |
| Revisión visual manual | Bandeja a 1440 px y a 375 px, y preferencias a 375 y 1440 px, en un navegador real (Vite con datos simulados, ya retirado): sin desborde horizontal; tarjetas por categoría, alertas obligatorias atenuadas con «Siempre activa». |

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

- **No verificado en SQL Server real:** la migración `GlucoLume_notificaciones_v2.sql` (solo se revisó su texto y se probó el mismo esquema en SQLite), el índice único filtrado bajo concurrencia real y el `GRANT DELETE`. Aplicarla primero en una copia restaurada y probar `reminders ejecutar` / `depurar` con la cuenta de procesos.
- Las pruebas de concurrencia usan hilos y SQLite: demuestran la reserva y el índice, no reemplazan una prueba con SQL Server.
- El job de recordatorios **no está agendado** en Compose ni en el servidor; sin él, los recordatorios por correo dependen de que la aplicación esté abierta.
- Los avisos de las cuentas de la plataforma (`platform.py`: cambios de contraseña) y de las instituciones no se incorporaron a la bandeja; solo siguen enviando su correo.
- No hay zona horaria por usuario: todo es hora de Argentina.
- La línea base de equipos conocidos se arma en el primer inicio de sesión posterior a la migración; hasta entonces no hay aviso de equipo nuevo para esa cuenta.
- «Cargar más» usa desplazamiento: si llegan avisos nuevos entre una carga y otra, la pantalla descarta los repetidos pero un aviso podría tardar en aparecer hasta recargar.
- Un recordatorio reservado cuyo aviso no pudo guardarse (error de base en ese instante) no se recupera; el siguiente horario sí se envía.
- Sin pruebas automáticas de la apariencia responsive (ver §10).
