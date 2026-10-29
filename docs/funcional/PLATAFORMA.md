# Administración de la plataforma — especificación funcional

Administración global (`backend/app/services/{platform,platformDashboard,platformInstitutions,device,matrix,auditQuery}.py`,
`backend/app/cli/{initAdmin,recoverAdmin}.py`, `frontend/src/pages/Platform`, `frontend/src/layouts/PlatformLayout.jsx`). Manual práctico:
[MANUAL_USUARIO.md](../MANUAL_USUARIO.md#parte-4--administración-de-la-plataforma).

## 1. Roles globales

| Rol (`Usuario.tipoCuenta`) | Etiqueta | Cantidad |
|---|---|---|
| `ADMINISTRADOR_PLATAFORMA` | Administrador del sistema | A lo sumo **uno** vigente (`UX_Usuario_administradorUnico`, cuenta también pendientes o bloqueadas) |
| `MODERADOR_PLATAFORMA` | Moderador del sistema | Varios |

Cuentas propias, sin vínculos institucionales; no se convierte una cuenta existente (se invita otro correo). El rol se lee de SQL Server en
cada pedido. Accesos: `/administracion/login` (redirige a `/plataforma/login`), `/administracion/activar` (activación con el código de un solo
uso en el fragmento `#codigo=…`, que no llega a los registros de Nginx), `/plataforma/recuperar` y `/plataforma/restablecer`.
Dos ingresos separados, aplicados por el backend (`acceso` en `POST /auth/login` y en el inicio con Google): el general (`localhost:8080/login`,
por omisión) **no admite** administradores ni moderadores de plataforma (`ACCESO_PLATAFORMA_REQUERIDO`), y el administrativo
(`/plataforma/login`, `acceso=PLATAFORMA`) **solo admite** a esas cuentas (`ACCESO_PLATAFORMA_DENEGADO` para el resto). El rechazo ocurre
antes de abrir la sesión o pedir MFA, y queda en la auditoría.

## 2. Permisos (`PERMISSIONS`)

| Permiso | Administrador | Moderador |
|---|:-:|:-:|
| Dashboard general | ✔ | — |
| Dashboard técnico y estado de los componentes | ✔ | ✔ |
| Gestionar moderadores (invitar, reenviar, revocar, restablecer contraseña) | ✔ | — |
| Transferir la administración | ✔ (inicia) | Recibe y responde |
| Auditoría global | ✔ | — |
| Inventario global: consultar, alta, edición técnica, cambio de estado | ✔ | ✔ |
| Asignar dispositivos a instituciones y descomisionar | ✔ | — |
| Matrices globales | ✔ | ✔ |
| Instituciones: listar, detalle administrativo, pausar, reactivar, cambiar el límite de cuentas, auditar su actividad | ✔ | ✔ |
| Eliminar instituciones (MFA + reautenticación) | ✔ | — |
| Matrices institucionales | — | — |
| Suscripciones y pagos («Próximamente») | ✔ | — |

## 3. Seguridad de las cuentas administrativas

MFA obligatoria (`PLATFORM_MFA_REQUIRED`): hasta activarla solo se puede configurar. Reautenticación (contraseña si tiene credencial local +
código MFA) en las acciones sensibles. Invitaciones y restablecimientos son enlaces de un solo uso: nadie define la contraseña de otra persona.
Todo queda en `Auditoria` (módulo `PLATAFORMA`) sin secretos.

## 4. Primer administrador y recuperación

- `python -m app.cli.initAdmin --nombre … --apellido … --correo …` (en Docker con `docker compose exec backend …`), después de preparar la
  base: se niega si hay un administrador activo; crea la cuenta PENDIENTE y envía un enlace de un solo uso (sin SMTP, `--mostrar-enlace`);
  auditado (`INICIALIZAR_ADMINISTRADOR`).
- `python -m app.cli.recoverAdmin` (solo servidor, sin ruta HTTP ni contraseña maestra):
  - `reemplazar --destino … --motivo … [--conservar-anterior]`: un moderador activo con MFA pasa a ser el único administrador, en una
    transacción condicionada (dos recuperaciones simultáneas no dejan dos administradores); cancela transferencias pendientes.
  - `reinvitar --motivo … [--resetear-mfa] [--mostrar-enlace]`: la misma persona recupera el acceso con un enlace nuevo.
  - Exigen motivo y escribir el correo; auditados (`RECUPERAR_ADMINISTRACION_PLATAFORMA`, `REINVITAR_ADMINISTRADOR_PLATAFORMA`).

## 5. Dashboard y estado del sistema

- **General** (administrador): estado de los componentes, cifras clave, instituciones (tabla con búsqueda y filtro; detalle solo con conteos),
  cuentas (cada una una vez), dispositivos, mediciones (DEMO aparte) y resumen de seguridad del período (accesos fallidos y motivos, cuentas
  bloqueadas, eventos críticos, operaciones administrativas, exportaciones, accesos por tipo de cuenta). Agregados **sin nombres, correos ni
  resultados identificables**; períodos de 7, 30 o 90 días o rango.
- **Técnico** (moderador): dispositivos, mediciones agregadas y estado del sistema.
- **Estado de los componentes** con verificaciones reales (consulta a la base con latencia, cifrado de prueba de MFA, conexión a SMTP y a
  Google, pySerial, matriz global con reglas): Operativo, Degradado, No disponible o Estado desconocido.

## 6. Moderadores del sistema

Invitar (nombre, apellido, correo, reautenticación; crea una cuenta PENDIENTE). Estados: Invitación enviada, Invitación vencida, Activo,
Activo falta MFA, Acceso revocado. Acciones con reautenticación y auditadas: reenviar, restablecer contraseña, revocar (bloquea, cierra
sesiones y cancela transferencias hacia esa persona). La reactivación de un moderador con MFA exige el segundo factor.

## 7. Transferencia de la administración

Solo el administrador la inicia hacia un moderador activo con MFA (`DESTINATARIO_INVALIDO`, `DESTINATARIO_INACTIVO`, `DESTINATARIO_SIN_MFA`), con confirmación y
reautenticación; una pendiente a la vez. Nada cambia hasta que el destinatario acepta (también con reautenticación); al aceptar, en una
transacción, el destinatario queda como único administrador y quien transfería como moderador. No se transfiere la propiedad de datos de
pacientes. Historial de transferencias.

## 8. Inventario global de dispositivos

Como el institucional pero global: filtros, indicadores, alta, edición y cambio de estado con motivo; **asignar** (con responsable opcional) y
**descomisionar** solo el administrador. Nunca se borran dispositivos ni mediciones. Uso compartido del equipo: DEC-01
([DISPOSITIVOS_Y_ADQUISICION.md](../DISPOSITIVOS_Y_ADQUISICION.md)).

## 9. Matrices globales y auditoría global

- Matriz **global** (catálogo de GlucoLume) por administrador y moderador: versiones, borrador, reglas, validación, activación y su auditoría.
  Es la referencia de cuentas individuales y de instituciones sin matriz activa. Las institucionales son privadas de cada institución.
- **Auditoría global** (solo administrador, `CONSULTAR_AUDITORIA_GLOBAL`): todos los módulos e instituciones, con IP, cliente y correlación,
  señales de seguridad y ficha por cuenta ([SEGURIDAD.md](../SEGURIDAD.md) §3).

## 10. Cuenta propia

Perfil («Tu rol en GlucoLume» y estado de MFA), Seguridad y MFA y cambio de contraseña en `/plataforma/perfil`, `/seguridad` y
`/cambiar-contrasena`.

## 11. Control de instituciones

| Endpoint | Permiso | Efecto |
|---|---|---|
| `GET /platform/institutions/{id}/audit` | `AUDITAR_INSTITUCIONES` | Eventos por categoría (registro, pausa, cierre, cupos, cuentas, exportaciones, accesos fallidos del personal, seguridad); sin datos clínicos; disponible aunque esté pausada o cerrada |
| `POST /platform/institutions/{id}/pause` | `GESTIONAR_ESTADO_INSTITUCIONES` | `ACTIVA → INACTIVA`, motivo de 10–300 caracteres |
| `POST /platform/institutions/{id}/reactivate` | `GESTIONAR_ESTADO_INSTITUCIONES` | `INACTIVA → ACTIVA`, motivo obligatorio |
| `PUT /platform/institutions/{id}/capacity` | `GESTIONAR_CUPOS_INSTITUCIONES` | Nuevo máximo de cuentas internas (1 a 100 000); puede quedar **excedida** |
| `POST /platform/institutions/{id}/delete` | `ELIMINAR_INSTITUCIONES` (administrador) | Eliminación administrativa (11.2) |

### 11.1 Pausa

Inmediata y aplicada en cada pedido: `requireMembership` responde `403 INSTITUCION_PAUSADA` a su personal (los tokens ya emitidos no la evaden).
Bloquea el contexto institucional, cuentas, pacientes, mediciones, dispositivos, exportaciones y modificaciones; la adquisición la respeta para
el personal de esa institución. Con el modo compartido del dispositivo (DEC-01), la pausa de la institución titular **no** impide que las
demás cuentas usen el equipo. Quien pertenece a varias instituciones solo pierde la pausada. Los procesos internos no operan sobre recursos de
instituciones pausadas (no inicia períodos de gracia). No modifica datos. Único contexto abierto: `POST /institutions/{id}/support-request`
(propietario, institución `INACTIVA`, 3 por hora, auditado sin el texto). El cambio de estado y su evento (`PAUSAR_INSTITUCION`,
`REACTIVAR_INSTITUCION`) se guardan en la misma transacción; el estado es la fuente de verdad. Aviso por correo al propietario.

### 11.2 Eliminación administrativa

- Solo el administrador con MFA y reautenticación en la misma solicitud (protección contra reutilización del código), nombre exacto y motivo.
  Admite `ACTIVA` o `INACTIVA`.
- Reutiliza el cierre lógico del propietario (`institution.applyLogicalClosure`): `CERRADA`, vínculos dados de baja, recursos liberados,
  reasignaciones canceladas, período de gracia y retención de pacientes. Nunca `DELETE` físico.
- Se distingue con una **marca en la fila** (`Institucion.cierreAdministrativo`, fecha, actor y motivo), escrita en la misma transacción que el
  estado y el evento `ELIMINAR_INSTITUCION_ADMINISTRATIVA`. No se deduce de la auditoría, que puede depurarse.
- **El propietario no puede reabrirla** (`403 INSTITUCION_CERRADA_ADMINISTRATIVAMENTE`, auditado) ni crear otra con el mismo CUIT; al último
  propietario se le indica comunicarse con el soporte; a terceros se les responde como ante cualquier institución cerrada ajena.
- Si la base instalada no tiene las columnas (incluidas en el esquema v5), responde `409 ELIMINACION_ADMINISTRATIVA_NO_DISPONIBLE` sin tocar
  nada y el detalle informa `eliminacionDisponible: false`.
- Aviso a los integrantes activos (`INSTITUCION_ELIMINADA_ADMINISTRATIVAMENTE`, sin el motivo). Es definitiva en esta etapa (sin
  «restaurar») y reutiliza el período de gracia vigente.

## 12. Limitaciones

- Suscripciones y pagos «Próximamente»: las tablas existen, sin funcionalidad.
- La administración ve agregados; la validación externa de la política sigue pendiente.
- `purgeInstitutionalRetention` no está programado; la política de retención no tiene interfaz.
- Descartados (19/10/2026): el desbloqueo manual de cuentas (el bloqueo por intentos vence solo y la recuperación de contraseña lo resuelve)
  y la restauración de instituciones eliminadas administrativamente (la eliminación es definitiva; el propietario tampoco puede reabrirla).
