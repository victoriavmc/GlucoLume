# Institución (propietario, moderador y operador) — especificación funcional

Módulo institucional (`backend/app/services/{institution,personnel,invitedAccounts,quota,institutionPatients,patientAccess,profileTransfers,reassignments,institutionReassignments,device,deviceConnection,matrix,measurement,telemetry,dashboard,institutionActivity,auditQuery,accountLifecycle,accountGrace,operatorOffboarding,pendingAccounts,institutionalRetention}.py`,
`frontend/src/pages/Account/{institutions,devices,matrices,audit}`). Manual práctico: [MANUAL_USUARIO.md](../MANUAL_USUARIO.md#parte-3--institución).

## 1. Modelo

- **Tipo de cuenta** (`USUARIO_INSTITUCIONAL`, se elige al registrarse y no cambia) y **rol institucional** (`PROPIETARIO`, `MODERADOR`,
  `OPERADOR`, en cada vínculo `InstitucionUsuario`, fijo: quien vuelve con otro rol tiene un vínculo nuevo) son conceptos distintos.
- Una cuenta pertenece a 0..N instituciones; un vínculo vigente por cuenta e institución.
- **El rol sale de la base en cada operación**: una baja o el cierre rigen de inmediato también en sesiones abiertas. Ocultar una opción no
  reemplaza la autorización del backend (403/404). Lo de otra institución responde como inexistente.
- **Pacientes** no son cuentas: son perfiles de medición administrados por la institución.

## 2. Permisos por rol (`ROLE_PERMISSIONS`)

| Capacidad | Propietario | Moderador | Operador |
|---|:-:|:-:|:-:|
| Consultar la institución y su panel | Sí | Sí | Sí |
| Modificar datos de la institución | Sí | — | — |
| Invitar y revocar moderadores | Sí | — | — |
| Invitar operadores | — | Sí | — |
| Revocar/administrar operadores y editar sus datos administrativos | Sí | Sí | — |
| Consultar equipo (Personal, Administración) | Sí | Sí | — |
| Eliminar la institución | Sí | — | — |
| Listado de pacientes (datos administrativos) | Sí | Sí | Sí |
| Alta y modificación de pacientes | Sí | Sí | Solo los suyos |
| Dar de baja pacientes | Sí | Sí | — |
| Cambiar el responsable de un paciente | Sí (propuesta, §7) | Sí (propuesta, §7) | Solo pide transferencias |
| **Datos de salud del paciente** | **No** por su rol | **No** por su rol | **Solo el operador responsable vigente** |
| Dispositivos: consultar | Sí | Sí | Los operativos que puede usar, con datos mínimos |
| Dispositivos: alta, edición y cambio de estado | Sí | Sí | Alta por primera conexión |
| Dispositivos: desvincular y descomisionar | Sí | — | — |
| Matrices: consultar la aplicable | Sí | Sí | Sí |
| Matrices: crear versiones, editar borradores, activar | Sí | Sí | — |
| Auditoría de la institución | **Sí (único)** | — | — |
| Actividad reciente | Sí | Sí | — |

## 3. Instituciones de una cuenta

- **Crear** (queda propietaria): nombre (2–150, puede repetirse), tipo (Consultorio, Clínica, Hospital, Laboratorio, Otro), CUIT **único**
  (no se modifica luego) y descripción. Si el CUIT es de una institución ACTIVA se rechaza; si es de una CERRADA corresponde reabrirla.
- **Reabrir**: solo **la cuenta que fue el último propietario**, con reautenticación (conocer el CUIT no basta). Conserva identificador, CUIT,
  auditoría, vínculos dados de baja y perfiles archivados; incrementa `cantidadReaperturas`. No se reabre un cierre administrativo de la
  plataforma ([PLATAFORMA.md](PLATAFORMA.md) §11).
- **Eliminar** (solo el propietario, reautenticación y nombre): cierre **lógico** (`CERRADA`, CUIT reservado); vínculos e invitaciones a BAJA,
  transferencias pendientes canceladas, recursos liberados, período de gracia para quien queda sin institución; pacientes sin acceso operativo y
  conservados 12 meses (`fechaExpiracionDatosPersonales`) antes de anonimizarse ([PRIVACIDAD_Y_RETENCION.md](../PRIVACIDAD_Y_RETENCION.md) §5).
  Nunca hay `DELETE` físico.
- **Pausa** por la plataforma (`INACTIVA`): el personal no opera en ella hasta que se reactive; el propietario puede escribir al soporte.

## 4. Personal, invitaciones y cupos

- El propietario designa moderadores; los moderadores incorporan operadores. Siempre por **invitación con aceptación** (7 días). Si la persona
  no tiene cuenta, la invitación crea una cuenta institucional pendiente con un enlace de activación de un solo uso (usuario y contraseña, o
  Google con ese correo verificado). Un enlace de una invitación cancelada, rechazada o vencida no activa la cuenta (`INVITACION_NO_VIGENTE`).
- Estados del vínculo: `PENDIENTE` → `ACTIVO` o `BAJA`. Datos administrativos del vínculo: nombre y apellido profesionales, matrícula,
  legajo, función.
- **Personal** muestra solo a quien se incorporó o tiene una invitación vigente; indicadores, filtros y perfil con historial.
- **Revocar**: propietario → moderadores; propietario o moderador → operadores. Al revocar un moderador caen sus invitaciones.
- **Cupos** (`capacidadMaximaUsuarios`, 1000 por defecto; la plataforma puede cambiarlo): consumen cupo propietario, moderadores y operadores
  activos (una persona cuenta una vez); no lo consumen invitaciones, bajas ni pacientes. Se controla con bloqueo de la fila de la institución;
  sin cupo la invitación queda pendiente. Con un límite menor que las cuentas activas la institución queda **excedida** hasta regularizarse.

## 5. Ciclo de vida de las cuentas institucionales

| # | Regla |
|---|---|
| 1 | Una baja afecta solo a esa relación; los demás vínculos no cambian |
| 2 | Eliminación voluntaria solo sin vínculos `ACTIVO`; sin vínculos se pide el enlace por correo, se reautentica y se elimina en el acto. No reemplaza una solicitud formal de supresión de datos |
| 3 | Al perder la **última** vinculación activa, o al quedar habilitada sin ninguna institución (verificó el correo, se registró con Google o activó una cuenta invitada), empieza un **período de gracia de 30 días corridos** (`fechaInicioGracia`/`fechaVencimientoGracia`) con correo y aviso. Una invitación pendiente no lo cancela; iniciar sesión no lo reinicia; aceptar una invitación o crear/reabrir una institución lo cancela |
| 4 | Vencido el plazo, el servicio `lifecycle` elimina y anonimiza la cuenta. Antes revalida con la fila bloqueada (`UPDLOCK`): tipo, estado, vencimiento, sin vínculos activos, 30 días completos desde el inicio (un vencimiento adelantado se omite como `PLAZO_INVALIDO`). Una cuenta sin plazo nunca se elimina |
| 5 | La eliminación **anonimiza** `Usuario` (no lo borra): suprime nombre, apellido, correo, usuario, nacimiento, sexo y fechas de gracia; borra credenciales, Google, MFA y tokens; revoca sesiones; conserva identificador, tipo y fechas |
| 6 | `InstitucionUsuario` se conserva; se completa el nombre profesional histórico; las invitaciones pendientes pasan a BAJA |
| 7 | La autoría de las mediciones no cambia: la guarda `Auditoria` (`INICIAR_MEDICION` con el vínculo del operador) |

- Incorporación y eliminación compiten con un `UPDATE` condicionado: gana exactamente una (verificado en SQL Server, ver
  [evidencias/PRUEBAS_CONCURRENCIA_SQLSERVER_2026-10-16.md](../evidencias/PRUEBAS_CONCURRENCIA_SQLSERVER_2026-10-16.md)). Ante un *deadlock*
  (1205) se reintenta (`app/utils/dbRetry.py`).
- Cuentas invitadas sin invitación vigente y con el enlace vencido se depuran (se anonimizan) para liberar el correo (`pendingAccounts`).
- `--dry-run` informa plazos sin escribir; una cuenta anterior a la política se regulariza con `--regularize` solo con autorización.
- **Nómina:** solo la consultan propietario y moderadores de esa institución; no vence por defecto; minimización opcional desactivada
  (`PERSONNEL_RETENTION_MONTHS=0`); el propietario (moderadores y operadores) o un moderador (operadores) puede **eliminar los datos
  históricos** de una persona ya desvinculada (409 `PERSONA_VIGENTE`, `DATOS_YA_ELIMINADOS`; auditado como crítico, irreversible).
- Eventos: `REVOCAR_MIEMBRO_INSTITUCION`, `INICIAR_PERIODO_GRACIA`, `CANCELAR_PERIODO_GRACIA`, `PACIENTES_PENDIENTES_REASIGNACION`,
  `ASIGNAR_RESPONSABLE_PACIENTE`, `SOLICITUD_ELIMINACION_CUENTA`, `ELIMINACION_CUENTA`, `ELIMINACION_AUTOMATICA_CUENTA`,
  `MINIMIZAR_DATOS_PERSONAL_HISTORICO`, sin datos personales.

## 6. Pacientes

- Perfil de medición institucional: nombre y apellido obligatorios; documento, nacimiento y sexo opcionales; pertenece a la institución a través
  de su **único operador responsable**. Documento único por institución ([PRIVACIDAD_Y_RETENCION.md](../PRIVACIDAD_Y_RETENCION.md) §5).
- Estados: `ACTIVO`; baja (solo lectura; con el código de retención vigente se anonimiza al darlo de baja); depurado.
- **Datos administrativos** visibles para el personal; un operador que consulta un paciente ajeno no recibe documento, nacimiento, edad, sexo ni
  salud. **Datos de salud** (mediciones, gráficos, estadísticas, nuevas mediciones, resultados por correo): **solo el operador responsable
  vigente**; cada rechazo queda en `Auditoria` sin valores. Agregados con mínimo de 5 pacientes distintos.

## 7. Transferencias y reasignaciones

- **Entre operadores:** el responsable solicita; rige recién cuando el destino **acepta**; el solicitante puede cancelar; una solicitud
  pendiente por paciente; aceptar es atómico. Quien no participa recibe «no encontrado».
- **Por propietario o moderador:** si el responsable sigue activo se crea una **propuesta** que el destino acepta (aviso a los propietarios,
  marca `destinoInvitadoPorElGestor` si el destino fue invitado por quien propone); un paciente sin responsable activo se asigna directo.
- **Por desvinculación:** no se desvincula a un operador con pacientes a cargo (`409 PACIENTES_ASIGNADOS`); el propietario o un moderador los
  reasigna a operadores activos y desvincula en una transacción (`POST …/operators/{id}/offboard`). Las bajas anteriores con pacientes sin
  responsable se detectan y regularizan (`/reassignments/regularize`) con tareas `ReasignacionPaciente` (una pendiente por paciente). El sistema
  nunca elige el destino.

## 8. Dispositivos

Inventario, estados e identidad: [DISPOSITIVOS_Y_ADQUISICION.md](../DISPOSITIVOS_Y_ADQUISICION.md) §6. Uso del equipo (DEC-01):

- **Modo compartido:** los operadores de esta y de otras instituciones usan el equipo para sus pacientes sin cambiar su titularidad; un equipo
  sin institución se usa sin vincularlo; un equipo de otra institución se confirma y usa (si el firmware no informa su ID).
- **Modo restringido:** un paciente se mide solo con equipos del inventario de su institución; uno sin institución se vincula primero
  (confirmación explícita, atómica, conserva sus mediciones y deja de estar disponible para las cuentas individuales); uno de otra institución
  no se usa ni se revela.
- **Alta:** por la primera conexión de un operador (queda en su institución, a cargo del propietario vigente) o manual por propietario y
  moderador. La institución no elige responsable ni desvincula.
- **Control temporal:** una sola cuenta controla el equipo a la vez; solo ella ve las lecturas y da órdenes al puente.

## 9. Matrices de referencia de glucosa

- Ámbitos: *GLOBAL* (la administra la plataforma) e *INSTITUCION* (propietario y moderador; nadie más la ve, ni la plataforma). La
  institucional activa tiene prioridad; sin ella se usa la global.
- Ciclo: `BORRADOR → ACTIVA ⇄ INACTIVA`, `ARCHIVADA` (terminal). Solo un borrador se edita; para cambiar una activa se crea una versión.
  Una activa por ámbito. Solo se activa una matriz válida y vigente.
- Reglas: sexo del modelo, condición de comida, rango de edad, minutos desde la ingesta e intervalo de glucosa de referencia; sin solapamientos
  ni duplicados (`REGLA_SOLAPADA`, `REGLA_DUPLICADA`); los huecos solo advierten. No es un algoritmo de estimación.
- Cada medición guarda el `idMatriz` con que se evaluó. La auditoría de la matriz institucional la ve el propietario.

## 10. Mediciones de pacientes

- Mide solo el operador responsable vigente (vínculo ACTIVO, institución ACTIVA, paciente sin baja). Sesión, guardado, estados, orígenes y DEMO
  como en [INDIVIDUAL.md](INDIVIDUAL.md).
- **Resultados por correo:** envío puntual al correo que da el paciente (no se guarda) o correo cargado con vencimiento a 12 meses y envío
  automático de cada medición guardada ([PRIVACIDAD_Y_RETENCION.md](../PRIVACIDAD_Y_RETENCION.md) §4). El operador declara la autorización
  y el paciente confirma la dirección desde el enlace que recibe: sin esa confirmación no se guarda ni recibe resultados.
- Referencia capilar como en la cuenta individual. El consentimiento de los pacientes es responsabilidad de la institución.

## 11. Dashboards, actividad y auditoría

- **Dashboard institucional** (agregados): pacientes activos, personal, dispositivos, mediciones (totales, hoy, 7 y 30 días), estados,
  última actividad; con períodos y sin grupos menores a 5 pacientes. Dashboards por operador y por paciente según permisos.
- **Actividad reciente** (de la auditoría): cambios de institución, invitaciones, personal, pacientes, dispositivos y matrices; quien audita ve
  además las operaciones rechazadas.
- **Auditoría** (solo propietario): resumen, filtros, detalle con cambios antes/después; sin IP, sin registros de plataforma y sin identificar
  al paciente en los eventos de medición ([SEGURIDAD.md](../SEGURIDAD.md) §3).
- **Datos institucionales:** información general, identificación legal, estado, rol, fechas, reaperturas, capacidad y cupos.

## 12. Limitaciones

- Sin acceso a datos de salud por función profesional para propietario o moderador.
- `purgeInstitutionalRetention` no está programado en Compose.
- Minimización del personal desactivada; los 10 años son una referencia a validar.
- Sin interfaz para la política de retención.
- El consentimiento de los pacientes no se registra.
- La estimación de glucosa no tiene algoritmo en el servidor.
- La reasignación masiva de pacientes sin responsable sigue siendo directa (sin aceptación del destino).
