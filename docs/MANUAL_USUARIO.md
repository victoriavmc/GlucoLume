# Manual de usuario

Guía práctica de GlucoLume por tipo de cuenta. Las reglas completas están en [`funcional/`](funcional/). GlucoLume es un **prototipo
experimental**: sus resultados no reemplazan una medición clínica ni un consejo médico.

- [Parte 1 — Usuario individual](#parte-1--usuario-individual)
- [Parte 2 — Grupo familiar](#parte-2--grupo-familiar)
- [Parte 3 — Institución](#parte-3--institución)
- [Parte 4 — Administración de la plataforma](#parte-4--administración-de-la-plataforma)

## Parte 1 — Usuario individual

### Crear la cuenta e iniciar sesión

1. **Registrarme** → cuenta individual: nombre, apellido, correo, usuario (mínimo 4 caracteres, sin «@») y contraseña dos veces (8 o más
   caracteres con mayúscula, minúscula, número y símbolo). Aceptá la Política de Privacidad.
2. Abrí el enlace de verificación del correo dentro de las **24 horas** (después la cuenta pendiente se elimina). Si no llegó, usá
   **Reenviar correo de verificación** (no extiende el plazo).
3. También podés **registrarte con Google**. Para entrar con Google tu cuenta ya tiene que existir; si ya tenías una con ese correo
   verificado, se vinculan solas.
4. Para entrar: correo o usuario y contraseña; **Recordarme** mantiene la sesión en ese equipo. Con **3 intentos fallidos** el acceso se
   bloquea 15 minutos. Si activaste la verificación en dos pasos, se pide el código (o uno de recuperación).
5. ¿Olvidaste la contraseña? **Recuperar contraseña** → enlace al correo.

### Inicio, perfil y seguridad

- **Inicio:** últimos valores, accesos rápidos, evolución reciente y consejos.
- **Perfil → Editar perfil:** nombre, apellido, usuario, fecha de nacimiento y sexo (se usan para la regla de referencia de glucosa). El
  correo no se edita.
- **Seguridad:**
  - Contraseña: la actual, la nueva dos veces y, con verificación en dos pasos, el código; se cierran las otras sesiones. Con Google podés
    **crear** una contraseña.
  - Verificación en dos pasos: escaneá el QR, ingresá el código y **guardá los códigos de recuperación**.
  - Perdí la aplicación autenticadora: «Recuperar acceso de otra manera» → contraseña actual → código por correo (10 min); se desactiva la
    verificación en dos pasos y se cierran las demás sesiones.
  - Avisos de inicio de sesión: activá o desactivá el correo (las alertas de actividad sospechosa llegan siempre).
  - **Eliminar cuenta:** enlace por correo (30 min) y confirmación; tus datos se anonimizan y tus mediciones quedan sin identificarte. Si
    administrás un grupo, antes designá a otra persona o eliminá el grupo.

### Conectar el dispositivo

1. Instalá el puente en la computadora Windows donde conectás el Arduino: `acquisition\bridge\Instalar-Puente.bat` (puerto, medio y servidor).
2. En GlucoLume abrí **Conectar dispositivo** y elegí el medio (Bluetooth HC-05/HC-06 a 9600 baudios; USB a 115200).
3. Mirá **Estado de la conexión**: *Puente serie detenido* (iniciá `Puente-GlucoLume.bat`), *Bluetooth desconectado* (encendé el Arduino y
   revisá el emparejamiento), *Conectado, sin datos* (el Arduino todavía no envía) o *Conectado*.
4. El equipo es **compartido**: para cambiar el puerto, pausar, reiniciar o detener el puente tocá **Usar dispositivo** (si otra cuenta lo
   está usando, la pantalla lo indica). Al terminar, **Dejar de usar**; si te olvidás, se libera solo a los 5 minutos o al cerrar la pantalla.

### Medir

1. **Mediciones → Nueva medición.** La primera vez aceptá la **autorización para almacenar tus mediciones** (sin eso no se mide).
2. Elegí el dispositivo, el **modo** (Oximetría o Glucosa experimental) y la **alimentación**; si hace falta, edad y sexo solo para esta
   medición y observaciones.
3. **Iniciar medición** toma el dispositivo para vos. Si falta algo, **Ver qué falta** lo indica.
4. Apoyá el dedo: verás la señal de pulso, la frecuencia, la SpO₂, el índice óptico y la glucosa informada. Esperá a que la lectura se
   estabilice y tocá **Guardar medición** (o **Cancelar**). Al terminar, el dispositivo queda libre para otra cuenta.
- Si dejás de usarlo unos dos minutos, la sesión se cancela sola. Las canceladas o inválidas se ocultan del historial a los 30 minutos.
- **DEMO (prueba):** valor sintético para probar el equipo; no es una glucemia y no entra en tus estadísticas.

### Ver tus mediciones

- **Mi dashboard:** última medición y recientes.
- **Historial:** filtros por fecha, modo, estado, origen y orden; **Ver detalle** muestra la matriz de referencia (comparación con un rango, no
  un diagnóstico) y permite **registrar una referencia capilar** de tu glucómetro.
- **Gráficos y evolución:** período, variable, origen y agrupación.
- Solo se eliminan las mediciones **DEMO**.

### Si algo no funciona

| Qué ves | Qué hacer |
|---|---|
| «Cuenta pendiente de verificación» | Abrí el enlace o reenviá el correo |
| Acceso bloqueado | Esperá 15 minutos |
| «Se necesita tu autorización» | Aceptá la autorización de datos experimentales en Mediciones |
| El dispositivo está en uso por otra cuenta | Esperá a que termine o lo libere |
| El botón de medir está deshabilitado | Revisá el estado de la conexión y que el dispositivo esté operativo |
| No hay regla de referencia | Completá fecha de nacimiento y sexo (o edad y sexo en la medición) |
| Enlace vencido o usado | Pedí uno nuevo |

## Parte 2 — Grupo familiar

> Al entrar a un grupo **no compartís nada** hasta que lo habilites. Ser administrador no da acceso a los datos de los demás.

- **Grupo** sin grupo: **Crear un grupo** (quedás como administrador/a) o **Unirme** aceptando una invitación (valen 7 días). Un solo grupo a
  la vez.
- **Invitar** (administrador/a): correo exacto de una cuenta individual activa; podés cancelar la invitación mientras está pendiente.
- **Mi privacidad:** activá por separado **Perfil**, **Última medición**, **Historial** (incluye gráficos y estadísticas) y **Aviso de
  medición** (solo fecha y hora). Rige en la próxima consulta de los demás. Solo vos los cambiás.
- **Datos compartidos:** elegí a una persona y verás lo que habilitó; si dice que no autorizó, ese permiso está apagado.
- **Panel y evolución:** resumen, integrantes, actividad compartida y evolución por persona (7, 30 o 90 días).
- **Integrantes:** el administrador puede desvincular (sus mediciones no se tocan).
- **Configuración:** datos del grupo, designar nuevo administrador, eliminar el grupo escribiendo su nombre exacto, abandonar (el administrador
  antes designa a otra persona; si es el único integrante, elimina el grupo).
- Para medir, cada integrante usa el dispositivo como cuenta individual (Parte 1), siempre en su propio perfil.

## Parte 3 — Institución

| Sección | Propietario | Moderador | Operador |
|---|:-:|:-:|:-:|
| Panel | ✔ | ✔ | ✔ |
| Personal | ✔ | ✔ | — |
| Pacientes | ✔ | ✔ | ✔ |
| Dispositivos | ✔ | ✔ | ✔ (los que puede usar) |
| Conectar dispositivo | — | — | ✔ |
| Matrices | ✔ (administra) | ✔ (administra) | ✔ (consulta) |
| Administración | ✔ | ✔ | — |
| Actividad | ✔ | ✔ | — |
| Auditoría | ✔ | — | — |

### Cuenta e invitaciones

1. Registrate como **cuenta institucional** (distinta de una individual) o, si te invitaron, abrí el enlace de **Activación de cuenta** y elegí
   usuario y contraseña (o Google con ese correo).
2. En **Instituciones**, aceptá o rechazá las invitaciones recibidas (7 días).
- Si tu cuenta queda **sin ninguna institución**, empieza un plazo de **30 días**: vencido, la cuenta se elimina y anonimiza. Crear una
  institución o aceptar una invitación lo cancela.

### Propietario

- **Crear institución:** nombre, tipo, CUIT (único, no se cambia) y descripción. Si el CUIT es de una institución cerrada y fuiste su último
  propietario/a, podés **reabrirla** (con tu contraseña y código).
- **Administración → Datos institucionales:** información, rol, fechas, reaperturas, capacidad y cupos; el propietario modifica los datos
  (nunca el CUIT).
- **Eliminar institución:** nombre, contraseña y código. Queda cerrada, se dan de baja vínculos e invitaciones y los datos de los pacientes se
  conservan 12 meses sin acceso antes de anonimizarse.
- Si la plataforma **pausó** la institución, solo podés escribir al soporte desde la tarjeta de la institución.

### Personal (propietario y moderador)

- El propietario invita **moderadores**; el moderador invita **operadores** (correo y, opcionalmente, datos profesionales).
- **Invitaciones:** estados, cancelar o reenviar. **Editar datos administrativos** desde el perfil de la persona (el rol no cambia).
- **Dar de baja:** el propietario a moderadores y operadores; el moderador a operadores. Un operador con pacientes primero los reasigna
  (desvinculación con reasignación en un paso).
- **Cupos:** sin lugar, la invitación espera. **Eliminar datos históricos** de alguien ya desvinculado desde su perfil (irreversible).

### Pacientes

- **Agregar paciente:** nombre y apellido; documento, nacimiento y sexo opcionales. El operador que lo carga queda responsable.
- **Buscar** y filtrar; **Editar** (propietario y moderador cualquiera; operador solo los suyos).
- **Datos de salud:** solo el **operador responsable actual**. Propietario y moderador ven datos administrativos.
- **Dar de baja** (propietario y moderador).
- **Transferir** (operador responsable): elegí el destinatario; rige cuando acepta. **Transferencias:** aceptar o rechazar.
- **Cambiar responsable** (propietario y moderador): con el responsable activo se envía una propuesta que el destino acepta.
- **Reasignaciones** (propietario y moderador): pacientes de operadores dados de baja; elegí un operador activo, marcá pacientes y confirmá.

### Dispositivos y medición

- **Inventario** (propietario y moderador): totales, filtros, alta manual, cambio de estado; desvincular y descomisionar solo el propietario.
- **Conectar dispositivo** (operador): puente en marcha → medio → **Dispositivo de esta conexión** (de la institución, sin institución para
  vincular, nuevo para registrar). Si el firmware no informa su identificador, confirmá que es el Arduino conectado. Con el **uso compartido**
  habilitado también podés usar el equipo de otra institución o sin vincular, sin cambiar su titularidad; **Usar dispositivo** te da el
  control del puente.
- **Medir a un paciente** (operador responsable): **Pacientes → Medir**; datos del paciente arriba; elegí dispositivo, modo y alimentación;
  iniciá, esperá la lectura estable y **Guardar medición**.
- **Resultados por correo:** cargá el correo que te dio el paciente confirmando que lo autorizó (se conserva 12 meses, se muestra enmascarado,
  podés cambiarlo o quitarlo) y cada medición guardada se le envía sola; o enviá un resultado puntual a otro correo, que no se guarda.
- **Referencia capilar:** en el detalle de una medición de glucosa completada.

### Matrices, panel y auditoría

- Todos ven qué matriz se aplica. Propietario y moderador: **Crear matriz** → reglas en el **borrador** → **Validar** → **Activar**; una activa
  no se edita (se crea una versión).
- **Panel:** indicadores (sin grupos menores a 5 pacientes). **Actividad** (propietario y moderador). **Auditoría** (solo propietario):
  resumen, filtros y detalle, solo lectura.

## Parte 4 — Administración de la plataforma

| Sección | Administrador | Moderador |
|---|:-:|:-:|
| Dashboard | General | Técnico |
| Moderadores del sistema | ✔ | — |
| Transferir administración | ✔ (inicia) | Recibe y responde |
| Dispositivos globales | ✔ | Consulta, alta, edita, cambia estado |
| Matrices globales | ✔ | ✔ |
| Instituciones (pausa, reactivación, límite de cuentas) | ✔ | ✔ |
| Eliminar instituciones | ✔ | — |
| Auditoría general | ✔ | — |
| Suscripciones y pagos («Próximamente») | ✔ | — |

1. **Primer administrador** (quien instala, una vez, después de preparar la base):
   `docker compose exec backend python -m app.cli.initAdmin --nombre … --apellido … --correo …` (sin SMTP, `--mostrar-enlace`).
2. **Activar la cuenta:** abrí el enlace, elegí usuario y contraseña y **activá la verificación en dos pasos** (hasta entonces el panel no
   funciona). Para volver: `/plataforma/login`.
3. **Dashboard:** período y agregados; **Estado de los componentes** indica qué falta configurar.
4. **Moderadores:** agregar (nombre, apellido, correo, contraseña y código); reenviar invitación, restablecer contraseña o revocar acceso, todo con
   reautenticación.
5. **Transferir administración:** elegí un moderador activo con MFA, confirmá y reautenticá; nada cambia hasta que acepte. El destinatario
   acepta o rechaza en la misma pantalla.
6. **Dispositivos globales:** inventario completo; asignar a una institución y descomisionar solo el administrador.
7. **Matrices globales:** crear, cargar reglas en el borrador, validar y activar.
8. **Instituciones:** pausar o reactivar con motivo, cambiar el límite de cuentas, consultar su auditoría administrativa; **eliminar**
   (administrador) con nombre exacto, motivo, contraseña y código: el propietario ya no puede reabrirla.
9. **Auditoría general:** filtros por fecha, usuario, institución, módulo, acción y resultado; detalle con cambios; solo lectura.
10. **Si algo no funciona:** solo entra a Seguridad → activá la verificación en dos pasos; «No tenés acceso» → tu rol no incluye esa
    sección; sin moderadores elegibles → el destinatario debe estar activo y con MFA; componente «No configurado» → completá la variable en
    `.env` y reiniciá el backend.
