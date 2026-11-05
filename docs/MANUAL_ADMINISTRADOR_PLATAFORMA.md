# Manual del administrador de la plataforma

> **Estado: borrador sin capturas.** Las capturas de pantalla están marcadas como `📷 Captura NN` y se completan con la lista del [anexo](#anexo--lista-de-capturas). Las rutas, permisos y nombres de botones salen de `frontend/src/pages/Platform` y de [docs/funcional/PLATAFORMA.md](funcional/PLATAFORMA.md); si la interfaz cambia, este manual debe actualizarse.

Este manual es para la cuenta **Administrador del sistema** (`ADMINISTRADOR_PLATAFORMA`). Los moderadores del sistema ven una parte distinta; cada sección indica qué puede hacer cada rol.

## Antes de capturar

- **Ocultá datos personales.** Nombres, correos, CUIT, documentos, IDs de usuario y nombres de instituciones reales deben difuminarse o reemplazarse por datos de prueba.
- **No captures secretos:** contraseñas, códigos de activación, códigos MFA, enlaces de un solo uso ni tokens.
- Tomá las capturas en escritorio, modo claro, con ventana de al menos 1280 px de ancho.
- Guardalas en `docs/manual_admin/img/` con el nombre indicado en el anexo (`NN-descripcion.png`).

## Parte 1 — Acceso

### 1.1 Ingreso administrativo

Entrá por `/plataforma/login` (si abrís `/administracion/login` te redirige ahí). El ingreso general del sitio **no admite** cuentas de administración: si intentás entrar por allí, la aplicación lo rechaza.

📷 **Captura 01** — pantalla «Administración de GlucoLume» con los campos de usuario y contraseña y el botón de Google.

### 1.2 Activar la cuenta

La primera vez usás el enlace de activación que entregó el comando `initAdmin`. Ahí elegís nombre de usuario y contraseña. El código de activación es de un solo uso y no se muestra en esta guía.

📷 **Captura 02** — «Activar cuenta administrativa» con los campos Código de activación, Nombre de usuario, Contraseña y Repetir contraseña (sin valores).

> **Importante:** hasta que activés la verificación en dos pasos (MFA) el panel no funciona. Entrá a **Seguridad** y configurala primero.

### 1.3 Recuperar o restablecer la contraseña

- `/plataforma/recuperar`: pedís el enlace con tu correo.
- `/plataforma/restablecer`: definís la contraseña nueva desde el enlace.

📷 **Captura 03** — «Recuperar contraseña».
📷 **Captura 04** — «Nueva contraseña».

### 1.4 Seguridad y verificación en dos pasos

En **Seguridad** (`/plataforma/seguridad`) configurás el MFA y cambiás la contraseña (`/plataforma/cambiar-contrasena`). Las acciones sensibles piden reautenticación: contraseña y código MFA.

📷 **Captura 05** — pantalla Seguridad con el estado de MFA. *(verificar el título exacto en pantalla)*

## Parte 2 — Dashboard general

Vista de inicio. Muestra indicadores agregados **sin nombres, correos ni resultados identificables**. El período puede ser de 7, 30 o 90 días, o un rango.

- **Indicadores principales:** cuentas registradas, instituciones activas, dispositivos operativos y mediciones del período (volumen, sin valores clínicos).
- **Estado de los componentes:** verificación real de base de datos, cifrado de MFA, SMTP, Google, pySerial y matriz global. Cada componente puede figurar como *Operativo*, *Degradado*, *No disponible* o *Estado desconocido*. Si dice *No configurado*, falta una variable en `.env`: completala y reiniciá el backend.
- **Seguridad y actividad:** intentos de acceso fallidos, cuentas bloqueadas, eventos críticos, operaciones administrativas y exportaciones.

📷 **Captura 06** — Dashboard general completo.
📷 **Captura 07** — bloque «Estado de los componentes».
📷 **Captura 08** — bloque «Seguridad y actividad».

> El moderador ve el **dashboard técnico** (dispositivos, mediciones agregadas y estado del sistema), no el general.

## Parte 3 — Moderadores del sistema

Sección `/plataforma/moderadores`. Solo el administrador la gestiona.

### 3.1 Agregar un moderador

Completá nombre, apellido y correo, y confirmá con reautenticación. Se crea una cuenta **pendiente** y se envía una invitación. Nadie define la contraseña de otra persona: la define quien recibe la invitación.

📷 **Captura 09** — «Agregar moderador del sistema» (formulario vacío).

### 3.2 Estados

| Estado | Significado |
|---|---|
| Invitación enviada | Todavía no activó la cuenta |
| Invitación vencida | Hay que reenviar la invitación |
| Activo | Cuenta activa con MFA |
| Activo falta MFA | Activa, pero sin segundo factor: no puede transferirse la administración |
| Acceso revocado | Bloqueado, sin sesiones abiertas |

📷 **Captura 10** — listado de moderadores con varios estados.

### 3.3 Acciones sobre un moderador

Desde el detalle de cada moderador (`/plataforma/moderadores/:id`):

- **Reenviar invitación**
- **Restablecer contraseña** (envía un enlace de un solo uso)
- **Revocar acceso:** bloquea la cuenta, cierra sus sesiones y cancela las transferencias pendientes hacia esa persona.

Todas piden reautenticación y quedan en la auditoría. La reactivación de un moderador con MFA exige el segundo factor.

📷 **Captura 11** — detalle de un moderador con los botones de acción.

## Parte 4 — Transferir la administración

Sección `/plataforma/transferencia` (exige MFA). Hay una sola transferencia pendiente a la vez.

1. Elegí un moderador **activo y con MFA**. Si no aparece, el destinatario está inactivo o sin MFA.
2. Confirmá y reautenticate.
3. **Nada cambia todavía.** El destinatario acepta o rechaza desde la misma pantalla, también con reautenticación.
4. Al aceptar, el destinatario queda como único administrador y vos pasás a moderador, en la misma transacción.

No se transfiere la propiedad de los datos de los pacientes. El historial de transferencias queda visible.

📷 **Captura 12** — formulario de transferencia con el moderador elegido.
📷 **Captura 13** — transferencia pendiente y historial.

## Parte 5 — Dispositivos globales

Sección `/plataforma/dispositivos`. Es el inventario completo, no el de una institución.

- **Filtros e indicadores** para encontrar dispositivos.
- **Alta, edición técnica y cambio de estado.** Todo cambio de estado lleva un motivo.
- **Asignar** a una institución (con responsable opcional) y **descomisionar**: solo el administrador.

Nunca se borran dispositivos ni mediciones.

📷 **Captura 14** — inventario global con filtros.
📷 **Captura 15** — detalle de un dispositivo con las acciones de asignar y descomisionar.

## Parte 6 — Matrices globales

Sección `/plataforma/matrices`. La matriz global es la referencia para las cuentas individuales y para las instituciones sin matriz propia activa.

1. **Crear matriz** (queda en borrador).
2. Cargar las reglas en el **borrador**.
3. **Validar.**
4. **Activar.**

Una matriz activa no se edita: para cambiarla se crea una versión nueva. Cada paso queda auditado.

📷 **Captura 16** — listado de matrices globales.
📷 **Captura 17** — detalle de una matriz con reglas y validación.

## Parte 7 — Instituciones

Sección `/plataforma/instituciones`. Solo datos administrativos: estado, personal y cantidad de cuentas.

### 7.1 Listado y detalle

Buscá una institución y abrí **Ver detalle**. El detalle muestra:

- **Estado y cupo:** inicio, finalización, reaperturas, cuentas en uso y cupos disponibles.
- **Personal y pacientes:** propietarios, moderadores, operadores, invitaciones pendientes y pacientes activos (solo cantidades).
- **Mediciones (volumen operativo):** totales, completadas, canceladas e inválidas.
- **Dispositivos asignados.**
- **Auditoría de la institución:** registro, pausas, cupos, cuentas, exportaciones y accesos fallidos. Sin datos clínicos.

📷 **Captura 18** — listado de instituciones.
📷 **Captura 19** — detalle con «Estado y cupo» y «Personal y pacientes».
📷 **Captura 20** — sección «Auditoría de la institución».

### 7.2 Acciones

| Acción | Quién | Qué hace |
|---|---|---|
| **Pausar institución** | Administrador y moderador | Bloquea el uso de la institución para su personal, en cada pedido. No modifica datos. Motivo de 10 a 300 caracteres. |
| **Reactivar institución** | Administrador y moderador | Vuelve a habilitarla. Motivo obligatorio. |
| **Modificar límite de cuentas** | Administrador y moderador | Nuevo máximo de cuentas internas (1 a 100 000). Puede quedar excedido. |
| **Eliminar institución** | Solo administrador | Cierre administrativo definitivo, con MFA y reautenticación. |

Con el equipo compartido (DEC-01), pausar una institución no impide que otras cuentas usen el equipo.

📷 **Captura 21** — diálogo «Pausar institución».
📷 **Captura 22** — diálogo «Modificar límite de cuentas».

> ⚠️ **Eliminar institución es definitivo en esta etapa.** Exige escribir el nombre exacto, un motivo, la reautenticación y el código MFA. El propietario ya no puede reabrirla ni crear otra con el mismo CUIT, y no hay forma de restaurarla desde la interfaz. **No captures el diálogo con una institución real**: usá una de prueba o describilo sin ejecutarlo.

## Parte 8 — Notificaciones

Sección `/plataforma/notificaciones`: tu bandeja de avisos de la administración.

📷 **Captura 23** — bandeja de notificaciones.

## Parte 9 — Auditoría global

Sección `/plataforma/auditoria`. Solo el administrador (los moderadores no la ven).

- **Filtros:** fecha, usuario, institución, módulo, acción y resultado.
- **Detalle** de cada evento, con los cambios. Solo lectura.
- Incluye IP, cliente y correlación, señales de seguridad y la ficha por cuenta.

📷 **Captura 24** — listado de auditoría con filtros.
📷 **Captura 25** — detalle de un evento.

## Parte 10 — Suscripciones y pagos

Sección `/plataforma/suscripciones`: aparece como **«Próximamente»**. Las tablas existen, pero todavía no tiene funcionalidad.

📷 **Captura 26** — pantalla «Próximamente».

## Parte 11 — Tu perfil

En `/plataforma/perfil` ves tu rol en GlucoLume y el estado de MFA.

📷 **Captura 27** — perfil del administrador (con datos ocultos).

## Parte 12 — Si algo no funciona

| Síntoma | Causa y solución |
|---|---|
| Solo entrás a Seguridad | Falta activar la verificación en dos pasos. |
| «No tenés acceso» | Tu rol no incluye esa sección. |
| No aparecen moderadores para transferir | El destinatario debe estar **activo y con MFA**. |
| Componente «No configurado» en el dashboard | Completá la variable en `.env` y reiniciá el backend. |
| Ingreso rechazado en el acceso general | Las cuentas de administración entran por `/plataforma/login`. |

---

## Anexo — Lista de capturas

Nombrá cada archivo como aparece y guardalo en `docs/manual_admin/img/`.

| N.º | Archivo | Pantalla | Ruta | Rol que la ve | Ocultar |
|---|---|---|---|---|---|
| 01 | `01-login-plataforma.png` | Ingreso administrativo | `/plataforma/login` | Sin sesión | Nada |
| 02 | `02-activar-cuenta.png` | Activar cuenta administrativa | `/administracion/activar` | Sin sesión | Código (vacío) |
| 03 | `03-recuperar-contrasena.png` | Recuperar contraseña | `/plataforma/recuperar` | Sin sesión | Nada |
| 04 | `04-nueva-contrasena.png` | Nueva contraseña | `/plataforma/restablecer` | Sin sesión | Nada |
| 05 | `05-seguridad-mfa.png` | Seguridad y MFA | `/plataforma/seguridad` | Administrador y moderador | Códigos, secretos |
| 06 | `06-dashboard-general.png` | Dashboard general | `/plataforma/dashboard` | Administrador | Nombres de instituciones |
| 07 | `07-estado-componentes.png` | Estado de los componentes | `/plataforma/dashboard` | Administrador y moderador | Nada |
| 08 | `08-seguridad-actividad.png` | Seguridad y actividad | `/plataforma/dashboard` | Administrador | Nada |
| 09 | `09-agregar-moderador.png` | Agregar moderador | `/plataforma/moderadores` | Administrador | Datos de prueba |
| 10 | `10-listado-moderadores.png` | Moderadores y estados | `/plataforma/moderadores` | Administrador | Nombres, correos |
| 11 | `11-detalle-moderador.png` | Acciones sobre un moderador | `/plataforma/moderadores/:id` | Administrador | Nombre, correo |
| 12 | `12-transferencia-formulario.png` | Transferir administración | `/plataforma/transferencia` | Administrador | Nombre del moderador |
| 13 | `13-transferencia-pendiente.png` | Transferencia pendiente e historial | `/plataforma/transferencia` | Administrador y moderador | Nombres |
| 14 | `14-dispositivos-globales.png` | Inventario global | `/plataforma/dispositivos` | Administrador y moderador | Responsables |
| 15 | `15-dispositivo-detalle.png` | Detalle y acciones | `/plataforma/dispositivos/:id` | Administrador | Responsables |
| 16 | `16-matrices-globales.png` | Listado de matrices | `/plataforma/matrices` | Administrador y moderador | Nada |
| 17 | `17-matriz-detalle.png` | Reglas y validación | `/plataforma/matrices/:id` | Administrador y moderador | Nada |
| 18 | `18-instituciones.png` | Listado de instituciones | `/plataforma/instituciones` | Administrador y moderador | Nombres, CUIT |
| 19 | `19-institucion-detalle.png` | Estado, cupo y personal | `/plataforma/instituciones/:id` | Administrador y moderador | Nombres, CUIT |
| 20 | `20-institucion-auditoria.png` | Auditoría de la institución | `/plataforma/instituciones/:id` | Administrador y moderador | Usuarios |
| 21 | `21-pausar-institucion.png` | Diálogo Pausar | `/plataforma/instituciones/:id` | Administrador y moderador | Nombre |
| 22 | `22-limite-cuentas.png` | Diálogo Modificar límite | `/plataforma/instituciones/:id` | Administrador y moderador | Nombre |
| 23 | `23-notificaciones.png` | Bandeja | `/plataforma/notificaciones` | Administrador y moderador | Nada |
| 24 | `24-auditoria-global.png` | Listado con filtros | `/plataforma/auditoria` | Administrador | IP, usuarios |
| 25 | `25-auditoria-detalle.png` | Detalle de un evento | `/plataforma/auditoria/:id` | Administrador | IP, usuarios |
| 26 | `26-suscripciones.png` | Próximamente | `/plataforma/suscripciones` | Administrador | Nada |
| 27 | `27-perfil.png` | Perfil administrativo | `/plataforma/perfil` | Administrador y moderador | Nombre, correo |

**Nota:** la captura 13 necesita una transferencia pendiente y la 15 un dispositivo de prueba. Si no hay datos así en la cuenta, creálos antes en una institución de prueba, no en una real.
