# Grupo familiar — especificación funcional

Módulo de grupos familiares (`backend/app/services/group.py`, `dashboard.py`, `frontend/src/pages/Account/groups`). Manual práctico:
[MANUAL_USUARIO.md](../MANUAL_USUARIO.md#parte-2--grupo-familiar). Requisitos de la cuenta: [INDIVIDUAL.md](INDIVIDUAL.md).

## 1. Qué es

Reúne **cuentas individuales** para que cada integrante decida qué comparte de sí. No es un grupo institucional y solo cuentas individuales
lo crean o integran (`PERMISO_INSUFICIENTE`). El grupo **no es dueño de ningún dato**: las mediciones no se copian ni cambian de dueño; se
leen del perfil de cada persona al consultar. Para medir, cada integrante usa el dispositivo como cuenta individual, siempre en su propio
perfil ([DISPOSITIVOS_Y_ADQUISICION.md](../DISPOSITIVOS_Y_ADQUISICION.md), DEC-01).

## 2. Roles y estados

| Elemento | Valores |
|---|---|
| Rol | **Administrador/a** (`rolGrupo = PROPIETARIO`, uno por grupo) y **Miembro** (el rol MODERADOR no se usa) |
| Grupo | `ACTIVO` o `CERRADO` (baja lógica) |
| Vínculo | `PENDIENTE` (invitación, vence a los 7 días), `ACTIVO`, `BAJA` (rechazo, cancelación, salida, desvinculación o grupo eliminado) |

Garantías en la base (índices únicos filtrados, también con pedidos simultáneos): un grupo ACTIVO por cuenta, un vínculo vigente por cuenta
y grupo, un administrador por grupo.

## 3. Permisos

| Acción | Administrador/a | Miembro |
|---|---|---|
| Ver panel, integrantes y actividad compartida | Sí | Sí |
| Elegir qué comparte de sí | Sí (solo lo propio) | Sí (solo lo propio) |
| Ver lo que otros habilitaron | Sí | Sí |
| Editar nombre y descripción; invitar, ver y cancelar invitaciones; desvincular; designar administrador; eliminar el grupo | Sí | No |
| Abandonar | Solo tras designar otro administrador (si es el único integrante, elimina el grupo) | Sí |
| Aceptar o rechazar invitaciones recibidas | Cualquier cuenta individual invitada | |

**Ser administrador o integrante no da acceso a datos ajenos.**

## 4. Crear e invitar

- Crear: nombre obligatorio (`NOMBRE_REQUERIDO`) y descripción opcional; quien crea queda como administrador con todo sin compartir. Con un
  grupo ACTIVO no se crea otro ni se acepta otra invitación (`YA_PERTENECE_A_GRUPO`).
- Invitar: por **correo exacto** de una cuenta individual activa. Se rechazan inexistentes, cuentas no individuales (`CUENTA_NO_INDIVIDUAL`),
  integrantes (`VINCULO_EXISTENTE`) e invitaciones pendientes (`INVITACION_PENDIENTE`); la búsqueda tiene límite (`DEMASIADAS_SOLICITUDES`).
  La invitación queda PENDIENTE, se avisa por correo, vence a los 7 días (`INVITACION_VENCIDA`) y se puede cancelar.

## 5. Privacidad de cada integrante

Cuatro permisos independientes sobre el propio perfil, todos en **0** al incorporarse:

| Permiso | Habilita |
|---|---|
| Compartir perfil | Datos básicos |
| Compartir última medición | La medición completada más reciente |
| Compartir historial | Historial **y** gráficos y estadísticas calculados con él |
| Avisar mediciones | Aviso con **solo fecha y hora** de cada medición, nunca el valor |

Para ver un dato ajeno deben cumplirse a la vez: grupo ACTIVO, vínculo ACTIVO de quien consulta y de quien comparte, el permiso vigente y
perfil propio válido (`DATOS_NO_COMPARTIDOS`, `PERFIL_NO_DISPONIBLE`). Se verifica en **cada consulta**: revocar, salir, ser desvinculado o
eliminar el grupo corta el acceso en la consulta siguiente, también en sesiones abiertas. Las mediciones compartidas incluyen las DEMO
(marcadas) y las anteriores al ingreso.

## 6. Panel y evolución

Panel (resumen, integrantes, actividad compartida reciente con cupo de 2 por integrante, estadísticas); datos compartidos de cada integrante;
evolución grupal (una serie por integrante que compartió su historial; períodos de 7, 30 o 90 días, `PERIODO_INVALIDO` en otro caso; los
permisos se leen en esa consulta; agregados con al menos 2 participantes).

## 7. Administración

Editar datos; designar nuevo administrador (una transacción: nunca sin administrador ni con dos; aviso por correo); desvincular (vínculo a
BAJA, perfiles y mediciones intactos); abandonar (`TRANSFERENCIA_REQUERIDA` o `ELIMINACION_REQUERIDA` para el administrador); eliminar el grupo
escribiendo el nombre exacto (`CONFIRMACION_INVALIDA`): vínculos e invitaciones a BAJA y compartición revocada.

## 8. Avisos y correos

Avisos de medición dentro de la aplicación (solo fecha y hora). Correos: invitación, alta del grupo, integrante agregado, desvinculado o que
abandona, asignación y cambio de administrador, eliminación del grupo. Si un correo no sale, la operación lo informa
(`NOTIFICACION_NO_ENVIADA`) y el aviso de creación se puede reenviar.

## 9. Relación con otras funciones y limitaciones

- Eliminar la cuenta saca a la persona de los grupos donde es miembro; si administra uno, se bloquea hasta transferir o eliminar.
- Sin pagos ni suscripciones (la sección de la plataforma está rotulada «Próximamente»).
- El plazo de las invitaciones (7 días) es fijo en el código.
- Los datos compartidos son experimentales; la validación legal de la política sigue pendiente.
