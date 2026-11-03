// Textos de «Ayuda» (/app/ayuda), separados por tipo de cuenta: cliente (CONSUMIDOR_FINAL) e institucional (USUARIO_INSTITUCIONAL).
// Reflejan las pantallas y las reglas actuales; si cambia un menú o una regla, se actualiza aquí.
// Base: docs/MANUAL_USUARIO.md y docs/funcional/ (INDIVIDUAL, GRUPO_FAMILIAR, INSTITUCION).
// Cada tema puede traer: `pasos` (cómo se usa, con enlace opcional a la pantalla), `detalles` (qué es cada cosa), `casos`
// (qué pasa en cada situación) y `tabla` (errores o permisos).

export const AYUDA_AVISO = 'GlucoLume es un prototipo experimental: sus resultados no reemplazan una medición clínica ni un consejo médico.';

// --- Temas comunes a las dos cuentas --------------------------------------------------------------------------------------

const TEMA_CONTRASENAS = {
  id: 'contrasenas',
  titulo: 'Contraseñas',
  intro: 'Una cuenta puede entrar con contraseña, con Google o con las dos. Esto cambia qué podés hacer si la olvidás.',
  detalles: [
    { titulo: 'Contraseña propia', texto: 'De 8 a 128 caracteres, con mayúscula, minúscula, número y símbolo. No puede ser una contraseña común ni contener tu usuario, correo, nombre o apellido. Se guarda cifrada.' },
    { titulo: 'Solo Google', texto: 'La cuenta no tiene contraseña. Para entrar también con correo o usuario, creala en Seguridad → Crear contraseña.' },
    { titulo: 'Google y contraseña', texto: 'La cuenta tiene las dos formas de entrar. Cambiar la contraseña pide la actual.' },
  ],
  casos: [
    { titulo: 'Contraseña nueva igual a la actual', texto: 'No se acepta: «La contraseña nueva tiene que ser distinta de la actual».' },
    { titulo: 'Contraseña de las últimas 3', texto: 'Tampoco se acepta: «Es una contraseña vieja. Elegí una distinta».' },
    { titulo: 'Contraseña que no cumple la política', texto: 'El sistema indica qué falta: mayúscula, minúscula, número, símbolo o longitud.' },
  ],
};

const TEMA_INICIAR_SESION = {
  id: 'iniciar-sesion',
  titulo: 'Iniciar sesión',
  intro: 'Entrás con usuario o correo y contraseña, o con Google. Si tenés verificación en dos pasos, te pide un código más.',
  pasos: [
    { texto: 'Escribí tu usuario o correo y tu contraseña. Marcá Recordarme si querés seguir en este equipo.', boton: 'Iniciar sesión', captura: 'iniciar-sesion.png' },
    { texto: 'Si tu cuenta tiene verificación en dos pasos, ingresá el código de 6 dígitos de tu app autenticadora.' },
    { texto: 'Si no podés usar la app, tocá «Usar un código de recuperación» y escribí uno de los que guardaste.' },
  ],
  casos: [
    { titulo: 'CASO 1 · Con usuario', texto: 'Escribís el nombre de usuario y la contraseña. Entrás si coinciden.' },
    { titulo: 'CASO 2 · Con correo', texto: 'Igual que el caso 1, con el correo electrónico.' },
    { titulo: 'CASO 3 · Con Google', texto: 'Tocá Continuar con Google. Si ya tenés una cuenta con ese correo, entrás. Si no, te avisa que la cuenta no está registrada: primero registrate.' },
    { titulo: 'CASO 4 · Pide código MFA por seguridad', texto: 'Ingresás el código de 6 dígitos de tu app. Después de varios códigos incorrectos, la verificación se bloquea por un rato.' },
    { titulo: 'CASO 5 · Olvidaste los códigos de recuperación', texto: 'No los necesitás si tenés la app: usá el código de 6 dígitos. Si tampoco tenés la app, mirá el caso 6.' },
    { titulo: 'CASO 6 · Perdiste la app y los códigos', texto: 'Tocá «Recuperar acceso de otra manera». Escribí tu contraseña actual y entrá con el código que llega al correo (vence en 10 minutos). Eso desactiva la verificación en dos pasos y cierra tus otras sesiones: podés volver a activarla en Seguridad.' },
    { titulo: 'Contraseña incorrecta', texto: 'Con 3 intentos fallidos el acceso se bloquea 15 minutos.' },
    { titulo: 'Correo sin verificar', texto: 'La app no te deja entrar y muestra «Tenés que verificar tu correo electrónico antes de iniciar sesión». Abrí el correo de verificación, o tocá «Reenviar correo de verificación» en la misma pantalla. El reenvío no extiende el plazo de 24 horas.', captura: 'iniciar-sesion-sin-verificar.png' },
  ],
};

const TEMA_RECUPERAR = {
  id: 'recuperar-contrasena',
  titulo: 'Recuperar contraseña',
  intro: 'Si olvidaste la contraseña, la recuperás desde el correo. Solo sirve para cuentas que tienen contraseña.',
  pasos: [
    { texto: 'En la pantalla de ingreso tocá «¿Olvidaste tu contraseña?» y escribí tu correo.', boton: '¿Olvidaste tu contraseña?', captura: 'olvide-contrasena.png' },
    { texto: 'Abrí el enlace del correo. Vence en 30 minutos y se usa una sola vez.' },
    { texto: 'Escribí la nueva contraseña dos veces y confirmala.' },
  ],
  casos: [
    { titulo: 'CASO 1 · Mismo correo y la misma contraseña de antes', texto: 'No se acepta: la nueva tiene que ser distinta de la actual, y tampoco una de las últimas 3.' },
    { titulo: 'CASO 2 · Mismo correo y una contraseña distinta y válida', texto: 'Se cambia. Se cierran todas las sesiones abiertas y te llega un aviso por correo.' },
    { titulo: 'Enlace vencido o ya usado', texto: 'Pedí uno nuevo desde la pantalla de recuperación.' },
    { titulo: 'Cuenta solo con Google', texto: 'No tiene contraseña para recuperar. Entrá con Google y creala en Seguridad.' },
    { titulo: 'Correo que no existe', texto: 'La pantalla responde lo mismo que si existiera: no revela qué correos están registrados.' },
  ],
};

const TEMA_PERFIL = {
  id: 'perfil',
  titulo: 'Perfil',
  intro: 'Tus datos personales. La fecha de nacimiento y el sexo se usan para calcular la referencia de glucosa.',
  pasos: [
    { texto: 'Entrá a Perfil y tocá Editar perfil.', ir: { to: '/app/perfil', label: 'Abrir Perfil' }, boton: 'Editar perfil', captura: 'perfil-editar.png' },
    { texto: 'Agregá los datos que falten: nombre, apellido, usuario, fecha de nacimiento y sexo (femenino o masculino).' },
    { texto: 'Guardá los cambios. El correo electrónico no se edita desde acá.' },
  ],
  detalles: [
    { titulo: 'Usuario', texto: 'Mínimo 4 caracteres, sin «@». Sirve para entrar junto con el correo. No puede estar usado por otra cuenta.' },
    { titulo: 'Perfil de medición', texto: 'Se crea solo la primera vez que hace falta. La edad se calcula al iniciar cada medición.' },
  ],
  casos: [
    { titulo: 'CASO 1 · Agregar fecha de nacimiento y sexo por primera vez', texto: 'Se guardan. La regla de referencia se aplica a partir de la próxima medición.' },
    { titulo: 'CASO 2 · Sin fecha de nacimiento o sexo', texto: 'No hay regla de referencia: la medición de glucosa no inicia. Podés medir en oximetría o completar edad y sexo solo para esa medición.' },
    { titulo: 'CASO 3 · Cambiar los datos después de medir', texto: 'Las mediciones guardadas conservan la edad y el sexo que tenían en ese momento; no se recalculan.' },
  ],
};

const TEMA_SEGURIDAD = {
  id: 'seguridad',
  titulo: 'Seguridad',
  intro: 'Cómo entrás a tu cuenta y cómo la protegés. Conviene revisarla apenas creás la cuenta.',
  pasos: [
    { texto: 'Activá la verificación en dos pasos: escaneá el QR con tu app autenticadora, ingresá el código de 6 dígitos y guardá los códigos de recuperación.', ir: { to: '/app/seguridad', label: 'Abrir Seguridad' } },
    { texto: 'Descargá o copiá los códigos de recuperación y guardalos en un lugar seguro. Cada uno sirve una sola vez.' },
    { texto: 'Dejá activado el aviso de nuevo inicio de sesión.' },
  ],
  detalles: [
    { titulo: 'Cambiar contraseña', texto: 'Pide la actual, la nueva dos veces y, si tenés verificación en dos pasos, un código. Al cambiarla se cierran las otras sesiones.' },
    { titulo: 'Verificación en dos pasos', texto: 'Pide un código de tu app cada vez que entrás. Los códigos de recuperación sirven si no tenés la app.' },
    { titulo: 'Avisos de inicio de sesión', texto: 'Podés activar o desactivar el correo que avisa de cada ingreso. Las alertas de actividad sospechosa llegan siempre.' },
    { titulo: 'Eliminar cuenta', texto: 'Se inicia desde un enlace que llega al correo (vence en 30 minutos) y pide reautenticarte. Tus datos se anonimizan y las mediciones quedan sin identificarte.' },
  ],
  casos: [
    { titulo: 'CASO 1 · Descargar los códigos', texto: 'Se muestran solo al activar la verificación. Descargalos o copialos en ese momento. Para tener códigos nuevos, desactivá y volvé a activar la verificación.' },
    { titulo: 'CASO 2 · Olvidé la contraseña', texto: 'Desde Seguridad no se puede: usá «¿Olvidaste tu contraseña?» en la pantalla de ingreso.' },
    { titulo: 'CASO 3 · Entrar con verificación en dos pasos', texto: 'Ingresás el código de tu app o un código de recuperación. Ver Iniciar sesión.' },
    { titulo: 'CASO 4 · Perdiste la app y los códigos', texto: 'En el ingreso, «Recuperar acceso de otra manera»: contraseña actual y código por correo. Desactiva la verificación en dos pasos.' },
    { titulo: 'CASO 5 · Cuenta solo con Google', texto: 'Crear contraseña en Seguridad, para poder entrar también con correo o usuario.' },
    { titulo: 'CASO 6 · Eliminar la cuenta con grupo a cargo', texto: 'Antes designá a otro administrador del grupo o eliminá el grupo. Si no, la eliminación se bloquea.' },
  ],
};

const TEMA_PROBLEMAS_COMUNES = {
  id: 'problemas',
  titulo: 'Si algo no funciona',
  tabla: {
    encabezados: ['Qué ves', 'Qué hacer'],
    filas: [
      ['Cuenta pendiente de verificación', 'Abrí el enlace del correo o reenviá la verificación. El reenvío no extiende el plazo de 24 horas.'],
      ['Acceso bloqueado', 'Con 3 intentos fallidos el acceso se bloquea 15 minutos. Esperá y volvé a intentar.'],
      ['El enlace de recuperación venció', 'Pedí uno nuevo desde «¿Olvidaste tu contraseña?».'],
      ['La contraseña nueva no se acepta', 'Tiene que ser distinta de la actual y de las últimas 3, y cumplir la política.'],
      ['Enlace de activación vencido o ya usado', 'Pedí uno nuevo a quien te invitó.'],
    ],
  },
};

// --- Cliente --------------------------------------------------------------------------------------------------------------

export const AYUDA_CLIENTE = [
  {
    id: 'primeros-pasos',
    titulo: 'Primeros pasos',
    intro: 'Lo que conviene hacer la primera vez, en este orden.',
    pasos: [
      { texto: 'Creá tu cuenta con correo y contraseña, o con Google, y verificá el correo dentro de las 24 horas.' },
      { texto: 'Completá tu perfil: fecha de nacimiento y sexo.', ir: { to: '/app/perfil', label: 'Abrir Perfil' } },
      { texto: 'Activá la verificación en dos pasos y guardá los códigos de recuperación.', ir: { to: '/app/seguridad', label: 'Abrir Seguridad' } },
      { texto: 'Autorizá el almacenamiento de tus mediciones y conectá el dispositivo.', ir: { to: '/app/conectar-dispositivo', label: 'Conectar dispositivo' } },
      { texto: 'Hacé tu primera medición.', ir: { to: '/app/mediciones/nueva', label: 'Nueva medición' } },
      { texto: 'Elegí qué avisos querés recibir y en qué horario te recordamos medirte.', ir: { to: '/app/notificaciones/preferencias', label: 'Preferencias de avisos' } },
    ],
  },
  {
    id: 'registro',
    titulo: 'Registro',
    intro: 'Podés tener cuenta con correo y contraseña, con Google, o con las dos. Con correo primero verificás el correo; con Google no hace falta, porque Google ya verificó tu dirección.',
    pasos: [
      { texto: 'Tocá Registrarse y elegí Uso personal.', captura: 'registro-tipo-cuenta.png', pie: 'Pantalla Crear una cuenta: elegí Uso personal.' },
      { texto: 'Completá nombre, apellido, correo, usuario (4 a 50 caracteres, sin «@») y contraseña. Repetí la contraseña.', captura: 'registro-datos.png', pie: 'Formulario Tus datos: correo, usuario y contraseña.' },
      { texto: 'Elegí una contraseña que cumpla todos los requisitos: 8 o más caracteres, mayúscula, minúscula, número y símbolo. No puede contener tu nombre, apellido, usuario ni correo.', captura: 'registro-contrasena-requisitos.png', pie: 'Cada requisito se marca en verde cuando lo cumplís.' },
      { texto: 'Leé la Política de Privacidad y marcá «Leí la Política de Privacidad». Sin esa casilla no se crea la cuenta.', captura: 'registro-politica.png', pie: 'La casilla queda sin marcar hasta que la tildes.' },
      { texto: 'Tocá Crear cuenta. Te llega un correo para verificar tu dirección.', captura: 'registro-verificar-correo.png', pie: 'Correo de verificación: tocá Verificar mi correo.' },
      { texto: 'Abrí el correo y tocá Verificar mi correo. El enlace vence en 24 horas y se usa una sola vez.' },
      { texto: 'Listo: al verificar te llega el correo de bienvenida y ya podés iniciar sesión.', captura: 'registro-bienvenida.png', pie: 'Correo de bienvenida con los datos de la cuenta.' },
      { texto: 'Si preferís Google, tocá Continuar con Google, elegí tu cuenta y aceptá la Política de Privacidad.', captura: 'registro-google-elegir-cuenta.png', pie: 'Elegí la cuenta de Google con la que querés entrar.' },
    ],
    casos: [
      { titulo: 'CASO 1 · Usuario con «@»', texto: 'El usuario no puede contener «@» (ese símbolo es del correo). Escribí solo letras, números y guiones.', captura: 'registro-usuario-arroba.png' },
      { titulo: 'CASO 2 · Contraseña que no cumple', texto: 'La app marca qué falta: mayúscula, minúscula, número, símbolo o longitud. También rechaza tu nombre, apellido o usuario dentro de la contraseña.', captura: 'registro-usuario-y-contrasena.png' },
      { titulo: 'CASO 3 · Sincronizar ambos', texto: 'Si ya verificaste la cuenta con correo, al entrar con Google con el mismo correo se vinculan solas. Si todavía no la verificaste, Google no la vincula: verificá el correo primero.', captura: 'google-vinculada.png' },
      { titulo: 'CASO 4 · Contraseña demasiado común', texto: 'Por ejemplo «Hola123.» cumple los requisitos pero es fácil de adivinar: la app dice «es demasiado común». Elegí otra.', captura: 'registro-contrasena-comun.png' },
      { titulo: 'CASO 5 · No aceptaste la Política de Privacidad', texto: 'Aparece «Para continuar tenés que confirmar que leíste la Política de Privacidad». Marcá la casilla y volvé a intentar.', captura: 'registro-politica.png' },
      { titulo: 'CASO 6 · Correo inválido', texto: 'Aparece «Ingresá un correo electrónico válido». Revisá que tenga @ y dominio, por ejemplo tunombre@gmail.com.', captura: 'registro-correo-invalido.png' },
      { titulo: 'CASO 7 · El correo ya tiene una cuenta', texto: 'Un mismo correo solo puede tener una cuenta, aunque la hayas creado como otro tipo. Iniciá sesión o usá otro correo.', captura: 'registro-correo-existe-personal.png' },
      { titulo: 'CASO 8 · Con Google, el correo tiene una cuenta de otro tipo', texto: 'Aparece «Ese correo ya está registrado con otro tipo de cuenta». Entrá con tu cuenta existente.', captura: 'google-otro-tipo.png' },
      { titulo: 'CASO 9 · Correo sin verificar: no podés iniciar sesión', texto: 'Si creaste la cuenta con correo y no lo verificaste, la app te avisa: «Tenés que verificar tu correo electrónico antes de iniciar sesión». Abrí el correo de verificación (vence en 24 horas) o tocá «Reenviar correo de verificación»: el reenvío no extiende el plazo.', captura: 'iniciar-sesion-sin-verificar.png' },
      { titulo: 'CASO 10 · Google sin cuenta previa', texto: 'Entrar con Google no crea cuentas: si no estás registrado, el sistema te lo indica y tenés que registrarte.', captura: 'registro-google-elegir-cuenta.png' },
    ],
  },
  {
    id: 'inicio',
    titulo: 'Inicio',
    intro: 'La pantalla de entrada: tu última medición, accesos rápidos, la evolución reciente y consejos.',
    detalles: [
      { titulo: 'Accesos rápidos', texto: 'Atajos a Mis mediciones, Nueva medición, Grupo, Perfil y Seguridad.' },
      { titulo: 'Evolución reciente', texto: 'Gráficos de tus últimos valores. Si no hay datos en el período, cambiá el período o hacé una medición.' },
    ],
  },
  TEMA_CONTRASENAS,
  TEMA_INICIAR_SESION,
  TEMA_RECUPERAR,
  TEMA_PERFIL,
  TEMA_SEGURIDAD,
  {
    id: 'notificaciones',
    titulo: 'Notificaciones',
    intro: 'La bandeja reúne los avisos de tu cuenta, tu grupo y tus recordatorios. Está en el menú Notificaciones.',
    pasos: [
      { texto: 'Abrí la bandeja y usá los filtros: todas, sin leer o por categoría.', ir: { to: '/app/notificaciones', label: 'Abrir Notificaciones' } },
      { texto: 'Marcá como leída una notificación tocándola, o todas juntas con «Marcar todas como leídas».', boton: 'Marcar todas como leídas', captura: 'notificaciones-marcar-leidas.png' },
      { texto: 'Para borrar, usá «Eliminar…»: podés borrar solo las leídas o vaciar la bandeja (pide confirmación y no se puede deshacer).', boton: 'Eliminar…', captura: 'eliminar-notificaciones.png' },
      { texto: 'En Preferencias elegí, por categoría, si querés el aviso en la aplicación, por correo o en ambos.', ir: { to: '/app/notificaciones/preferencias', label: 'Abrir Preferencias' } },
      { texto: 'En Horario para medirme elegí no recibir recordatorios, uno cada cierto tiempo o a horas específicas.' },
    ],
    detalles: [
      { titulo: 'Seguridad', texto: 'Inicios de sesión desde equipos nuevos, cambios de contraseña o de verificación en dos pasos, y actividad sospechosa.' },
      { titulo: 'Grupo familiar', texto: 'Invitaciones, incorporaciones o salidas del grupo, y mediciones del grupo cuando alguien elige avisar.' },
      { titulo: 'Recordatorios de medición', texto: 'El aviso para medirte en el horario que configuraste.' },
      { titulo: 'Mediciones', texto: 'Cuando sale por correo el resultado de una medición que pediste, o cuando no pudo salir.' },
    ],
    casos: [
      { titulo: 'CASO 1 · Marcar leídos', texto: 'Al leer una notificación baja el contador del menú. Las sin leer aparecen con su número en el menú.' },
      { titulo: 'CASO 2 · Borrar', texto: 'Podés borrar una notificación, las leídas o toda la bandeja. Vaciarla quita también las que no leíste.' },
      { titulo: 'CASO 3 · Preferencias', texto: 'Si apagás un aviso en la aplicación y en el correo, no te llega. Las alertas de actividad sospechosa y los intentos de ingreso siempre llegan a la aplicación.' },
    ],
  },
  {
    id: 'conectar-dispositivo',
    titulo: 'Conectar dispositivo',
    intro: 'Es el puente entre el Arduino y GlucoLume. El equipo es compartido: una cuenta lo controla a la vez.',
    pasos: [
      { texto: 'Instalá el puente en la computadora Windows donde conectás el Arduino: acquisition\\bridge\\Instalar-Puente.bat.' },
      { texto: 'En Conectar dispositivo elegí el medio: Bluetooth HC-05/HC-06 (9600 baudios) o USB (115200).', ir: { to: '/app/conectar-dispositivo', label: 'Conectar dispositivo' } },
      { texto: 'Mirá el estado de la conexión y resolvé lo que indique antes de medir.' },
      { texto: 'Tocá Usar dispositivo para tomar el control del puente.', boton: 'Usar dispositivo', captura: 'conectar-pantalla.png', pie: 'Pantalla de Conectar dispositivo. Con el puente en marcha aparece el botón «Usar dispositivo».' },
      { texto: 'Al terminar, tocá Dejar de usar para liberarlo.', boton: 'Dejar de usar', captura: 'conectar-pantalla.png', pie: 'Pantalla de Conectar dispositivo. Mientras lo usás, el botón «Dejar de usar» aparece aquí.' },
    ],
    detalles: [
      { titulo: 'Puente serie detenido', texto: 'Iniciá Puente-GlucoLume.bat en la computadora.' },
      { titulo: 'Bluetooth desconectado', texto: 'Encendé el Arduino y revisá el emparejamiento.' },
      { titulo: 'Conectado, sin datos', texto: 'El Arduino todavía no envía datos: esperá o revisá el equipo.' },
      { titulo: 'Conectado', texto: 'Ya podés medir.' },
    ],
  },
  {
    id: 'mediciones',
    titulo: 'Mediciones',
    intro: 'Para medir hacen falta tres cosas, en este orden: perfil completo, autorización y dispositivo conectado.',
    pasos: [
      { texto: 'PRIMERO · Configuración de perfil: cargá fecha de nacimiento y sexo.', ir: { to: '/app/mediciones/perfil', label: 'Configuración de perfil' } },
      { texto: 'SEGUNDO · Autorización: en Nueva medición aceptá «Autorización para almacenar tus mediciones». Sin eso no se mide.', ir: { to: '/app/mediciones/nueva', label: 'Nueva medición' } },
      { texto: 'Conectá el dispositivo y verificá que el estado sea Conectado.' },
      { texto: 'Elegí dispositivo, modo (Oximetría o Glucosa experimental) y alimentación. Si hace falta, completá edad y sexo solo para esta medición.' },
      { texto: 'Tocá Iniciar medición, apoyá el dedo y esperá a que la lectura se estabilice.', boton: 'Iniciar medición', captura: 'medicion-pantalla.png', pie: 'Pantalla de Nueva medición. Con el dispositivo conectado aparece el botón «Iniciar medición».' },
      { texto: 'Tocá Guardar medición para registrarla, o Cancelar para descartarla.', boton: 'Guardar medición', captura: 'medicion-pantalla.png', pie: 'Al terminar la lectura aparecen «Guardar medición» y «Cancelar» en esta pantalla.' },
      { texto: 'Revisá Mi dashboard, el Historial y los gráficos.', ir: { to: '/app/mediciones', label: 'Ver mis mediciones' } },
    ],
    detalles: [
      { titulo: 'Semáforo', texto: 'Compara una glucosa con el intervalo recomendado de tu regla: «Está bien», «Revisar» o «Muy alto». Es una comparación, no un diagnóstico.' },
      { titulo: 'Matriz de referencia', texto: 'Se ve en el detalle de cada medición. Permite registrar una referencia capilar de tu glucómetro.' },
      { titulo: 'Autorización', texto: 'Podés revocarla cuando quieras: frena nuevas mediciones, pero no borra lo medido.' },
      { titulo: 'DEMO', texto: 'Valor sintético para probar el equipo. No es una glucemia y no entra en tus estadísticas. Solo se puede eliminar lo DEMO.' },
    ],
    casos: [
      { titulo: 'CASO 1 · Medición permitida', texto: 'Autorización vigente, perfil con regla, dispositivo conectado, operativo y libre. Al guardar, la medición queda completada y entra en tus estadísticas.' },
    ],
    tabla: {
      encabezados: ['Qué ves', 'Qué hacer'],
      filas: [
        ['Falta la autorización', 'Aceptala en Nueva medición.'],
        ['No hay comunicación con el Arduino', 'Iniciá el puente y revisá el Bluetooth o el cable USB.'],
        ['El dispositivo está siendo usado por otra cuenta', 'Esperá a que termine. Si queda sin uso, se libera solo a los 5 minutos.'],
        ['El dispositivo no está operativo', 'No se puede medir hasta que vuelva a estar operativo.'],
        ['No hay regla de referencia para tu perfil', 'Completá fecha de nacimiento y sexo en Perfil, o edad y sexo en la medición.'],
        ['Lectura sin muestras', 'No se registró nada. Repetí la medición con el dedo apoyado.'],
        ['Sesión cancelada', 'Si dejás de usar el equipo unos dos minutos, la sesión se cancela sola. Volvé a iniciarla.'],
        ['Medición inválida por tiempo agotado', 'Volvé a medir.'],
      ],
    },
  },
  {
    id: 'grupo',
    titulo: 'Grupo familiar',
    intro: 'Compartí, si querés, información de tus mediciones con las personas de tu grupo. Ser administrador/a no da acceso a los datos de los demás.',
    pasos: [
      { texto: 'Creá un grupo (nombre obligatorio, descripción opcional) o aceptá una invitación. Solo podés tener un grupo a la vez.', ir: { to: '/app/grupo', label: 'Abrir Grupo' }, boton: 'Crear grupo', captura: 'grupo-crear.png' },
      { texto: 'Como administrador/a, invitá por correo exacto a una cuenta individual.' },
      { texto: 'En Mi privacidad elegí qué ven los demás: Perfil, Última medición, Historial (con gráficos y estadísticas) y Aviso de medición (solo fecha y hora). Todo arranca apagado.' },
      { texto: 'En Datos compartidos revisá lo que cada persona habilitó.' },
      { texto: 'Para cambiar de administrador, en Configuración designá a la otra persona.' },
      { texto: 'Para abandonar, en Configuración tocá Abandonar. Si sos administrador/a, antes designá a otra persona.' },
    ],
    detalles: [
      { titulo: 'Desvincular', texto: 'El administrador puede desvincular a un integrante. No se tocan sus mediciones.' },
      { titulo: 'Eliminar el grupo', texto: 'Desde Configuración, escribiendo su nombre exacto. Quedan canceladas las invitaciones y los permisos de compartir.' },
      { titulo: 'Panel y evolución', texto: 'Resumen del grupo y evolución por persona de 7, 30 o 90 días. Las estadísticas grupales necesitan al menos 2 integrantes que compartan su historial.' },
      { titulo: 'Cambios de permiso', texto: 'Rigen en la próxima consulta de los demás.' },
    ],
    casos: [
      { titulo: 'CASO 1 · Invitar a una cuenta individual existente', texto: 'Queda pendiente por 7 días. Le llega el aviso en la aplicación y por correo.' },
      { titulo: 'CASO 2 · Invitar a un correo sin cuenta', texto: 'Solo hace falta el correo. Se le envía una invitación con un enlace para activar la cuenta: elige usuario y contraseña, y después ve la invitación para aceptarla o rechazarla. Vence en 7 días.' },
      { titulo: 'CASO 3 · Aceptar', texto: 'Pasás a ser integrante, con todo lo que compartís apagado. Si ya tenés grupo, no podés aceptar otra invitación.' },
      { titulo: 'CASO 4 · Rechazar', texto: 'La invitación se cierra y el administrador puede volver a invitarte.' },
    ],
    tabla: {
      encabezados: ['Qué ves', 'Qué significa'],
      filas: [
        ['Correo de una cuenta institucional', 'No se puede invitar: el grupo es solo para cuentas individuales.'],
        ['La persona ya es integrante', '«Esta persona ya forma parte del grupo».'],
        ['Invitarte a vos mismo/a', 'Se informa como integrante existente, porque ya formás parte del grupo.'],
        ['Ya hay una invitación pendiente', 'Podés reenviarla o cancelarla desde el listado.'],
        ['La persona ya está en otro grupo', '«Ya pertenece a otro grupo»: no puede incorporarse.'],
        ['Correo sin verificar, bloqueado o eliminado', 'Se responde igual que si la cuenta no existiera.'],
        ['Demasiadas búsquedas seguidas', 'Esperá un rato y volvé a intentar.'],
      ],
    },
  },
  {
    id: 'consejos',
    titulo: 'Consejos',
    intro: 'Artículos sobre diabetes, con etiquetas y buscador. Son informativos: consultá a tu equipo de salud antes de cambiar algo.',
    pasos: [{ texto: 'Buscá o filtrá por etiqueta y abrí el artículo que te interese.', ir: { to: '/app/consejos', label: 'Abrir Consejos' } }],
  },
  TEMA_PROBLEMAS_COMUNES,
];

// --- Institucional --------------------------------------------------------------------------------------------------------

export const AYUDA_INSTITUCIONAL = [
  {
    id: 'primeros-pasos',
    titulo: 'Primeros pasos',
    intro: 'Una cuenta institucional trabaja dentro de una o más instituciones. Según tu rol, verás unas secciones u otras.',
    pasos: [
      { texto: 'Registrate con una cuenta institucional, o abrí el enlace de Activación de cuenta si te invitaron.' },
      { texto: 'En Instituciones aceptá o rechazá las invitaciones recibidas. Duran 7 días.', ir: { to: '/app/instituciones', label: 'Abrir Instituciones' } },
      { texto: 'Si sos propietario/a, creá tu institución con nombre, tipo, CUIT y descripción.' },
      { texto: 'Abrí la institución: su menú aparece en la barra lateral, con las secciones de tu rol.' },
      { texto: 'Completá tu perfil y activá la verificación en dos pasos.', ir: { to: '/app/perfil', label: 'Abrir Perfil' } },
    ],
    detalles: [
      { titulo: 'Sin institución', texto: 'Si tu cuenta queda sin ninguna institución, tenés 30 días. Vencido ese plazo, la cuenta se elimina. Crear una institución o aceptar una invitación lo cancela.' },
      { titulo: 'Institución pausada', texto: 'Si la plataforma la pausó, el personal no opera en ella. El propietario puede escribir al soporte desde la tarjeta de la institución.' },
    ],
  },
  {
    id: 'registro',
    titulo: 'Registro y acceso',
    intro: 'La cuenta institucional es distinta de la individual: si necesitás las dos, usá un correo para cada una. Se verifica igual que la personal.',
    pasos: [
      { texto: 'Tocá Registrarse y elegí Uso institucional.', captura: 'registro-tipo-cuenta.png', pie: 'Pantalla Crear una cuenta: elegí Uso institucional.' },
      { texto: 'Completá nombre, apellido, correo, usuario y contraseña (repetila). La contraseña debe cumplir todos los requisitos.' },
      { texto: 'Leé la Política de Privacidad y marcá «Leí la Política de Privacidad».', captura: 'registro-politica.png', pie: 'Sin esa casilla no se crea la cuenta.' },
      { texto: 'Tocá Crear cuenta institucional y abrí el correo de verificación dentro de las 24 horas.', captura: 'registro-verificar-correo.png', pie: 'Correo de verificación: tocá Verificar mi correo.' },
      { texto: 'Si te invitaron, abrí el enlace de Activación de cuenta, elegí usuario y contraseña (o entrá con Google con ese mismo correo).' },
    ],
    casos: [
      { titulo: 'CASO 1 · Registro con correo', texto: 'Queda pendiente hasta verificar el correo. Sin institución, la cuenta no puede operar hasta que aceptes una invitación o crees una institución.' },
      { titulo: 'CASO 2 · Registro con Google', texto: 'Exige aceptar la política. La cuenta se crea sin contraseña.' },
      { titulo: 'CASO 3 · Sincronizar ambos', texto: 'Igual que en la cuenta individual: si ya tenés cuenta institucional activa y entrás con Google usando el mismo correo verificado, las dos formas quedan vinculadas.' },
      { titulo: 'CASO 4 · Correo de una cuenta individual', texto: 'No sirve para una cuenta institucional: la app dice «Este correo ya está registrado». Registrate con otro correo.', captura: 'registro-correo-existe-institucional.png' },
      { titulo: 'CASO 5 · Con Google, el correo tiene una cuenta de otro tipo', texto: 'Aparece «Ese correo ya está registrado con otro tipo de cuenta». Entrá con tu cuenta existente o usá otro correo.', captura: 'google-otro-tipo.png' },
      { titulo: 'CASO 6 · Enlace de activación', texto: 'Es de un solo uso y vence con la invitación (7 días). Si la invitación fue cancelada o rechazada, el enlace no activa la cuenta.' },
    ],
  },
  TEMA_CONTRASENAS,
  TEMA_INICIAR_SESION,
  TEMA_RECUPERAR,
  {
    id: 'roles',
    titulo: 'Roles y secciones',
    intro: 'Cada sección del menú de la institución depende de tu rol. Ocultar una opción no reemplaza la autorización: el servidor controla cada acción.',
    tabla: {
      encabezados: ['Sección', 'Propietario', 'Moderador', 'Operador'],
      filas: [
        ['Panel', '✔', '✔', '✔'],
        ['Personal', '✔', '✔', '—'],
        ['Pacientes', '✔', '✔', '✔ (los suyos para editar y medir)'],
        ['Dispositivos', '✔', '✔', 'Los que puede usar'],
        ['Conectar dispositivo', '—', '—', '✔'],
        ['Matrices', 'Administra', 'Administra', 'Consulta'],
        ['Administración', '✔', '✔', '—'],
        ['Actividad', '✔', '✔', '—'],
        ['Auditoría', '✔', '—', '—'],
      ],
    },
  },
  {
    id: 'crear-institucion',
    titulo: 'Crear institución',
    intro: 'Solo las cuentas institucionales pueden crear una. Quien la crea queda como propietario/a.',
    pasos: [
      { texto: 'En Instituciones tocá crear institución.', ir: { to: '/app/instituciones', label: 'Abrir Instituciones' } },
      { texto: 'Completá el nombre (2 a 150 caracteres; puede repetirse), el tipo (Consultorio, Clínica, Hospital, Laboratorio u Otro), el CUIT y la descripción.' },
      { texto: 'Al escribir el CUIT el sistema lo valida: tiene que tener 11 dígitos con dígito verificador. Después te informa si ya existe.' },
      { texto: 'Confirmá la creación. El CUIT no se puede modificar después.' },
    ],
    casos: [
      { titulo: 'CASO 1 · CUIT disponible', texto: 'Se crea la institución y quedás como propietario/a.' },
      { titulo: 'CASO 2 · CUIT de una institución activa', texto: 'Se rechaza: «Ya existe una institución activa registrada con este CUIT».' },
      { titulo: 'CASO 3 · CUIT de una institución cerrada', texto: 'Solo quien fue su último propietario puede reabrirla, con contraseña y código. Otra cuenta no puede representarla aunque conozca el CUIT.' },
      { titulo: 'CASO 4 · CUIT inválido', texto: 'No pasa la validación: revisá los dígitos.' },
    ],
  },
  {
    id: 'propietario',
    titulo: 'Propietario',
    intro: 'Quien creó la institución. Administra sus datos, su equipo y su auditoría.',
    pasos: [
      { texto: 'En Administración → Datos institucionales revisá la información, el rol, las fechas, la capacidad y los cupos. Podés modificar todo menos el CUIT.' },
      { texto: 'Agregá moderadores desde Personal.' },
      { texto: 'Revisá Auditoría: resumen, filtros y el detalle de cada registro, con los cambios antes y después. Es de solo lectura y solo la ve el propietario.' },
    ],
    detalles: [
      { titulo: 'Eliminar institución', texto: 'Pide nombre, contraseña y código. Queda cerrada, los vínculos pasan a baja y los datos de los pacientes se conservan 12 meses sin acceso antes de anonimizarse.' },
      { titulo: 'Reabrir', texto: 'Solo el último propietario o propietaria de una institución cerrada puede reabrirla, con contraseña y código.' },
    ],
  },
  {
    id: 'personal',
    titulo: 'Personal',
    intro: 'El propietario agrega moderadores y el moderador agrega operadores. Siempre por invitación que la persona acepta.',
    pasos: [
      { texto: 'En Personal tocá agregar, elegí el rol (moderador u operador) e ingresá el correo.', boton: 'Agregar moderador', captura: 'institucional-personal-agregar.png' },
      { texto: 'Si la persona no tiene cuenta, completá nombre y apellido. Si ya tiene cuenta institucional, confirmá nombre y apellido.' },
      { texto: 'Opcional: cargá los datos profesionales. Son matrícula, legajo y función.' },
      { texto: 'En Invitaciones podés ver el estado, reenviar o cancelar cada invitación.' },
    ],
    detalles: [
      { titulo: 'Dar de baja', texto: 'El propietario da de baja a moderadores y operadores; el moderador, a operadores. Un operador con pacientes primero los reasigna, en el mismo paso.' },
      { titulo: 'Cupos', texto: 'Si no hay lugar, la invitación espera hasta que se libere un cupo.' },
      { titulo: 'Eliminar datos históricos', texto: 'Desde el perfil de una persona ya desvinculada. Es irreversible.' },
    ],
    casos: [
      { titulo: 'CASO 1 · Correo de una cuenta individual', texto: 'No se puede agregar: es una cuenta personal, no incorporable al equipo.' },
      { titulo: 'CASO 2 · El correo no existe', texto: 'Se crea una cuenta pendiente y se envía la invitación. La persona activa la cuenta, elige usuario y contraseña, y recién entonces ve la invitación.' },
      { titulo: 'CASO 3 · Aceptar o rechazar', texto: 'La persona lo responde en Instituciones. Aceptar la incorpora con su rol; rechazar cierra la invitación. Vence en 7 días.' },
      { titulo: 'CASO 4 · Ya está en la institución', texto: 'Si ya es moderador u operador, no se vuelve a invitar. Si tiene otro rol, su rol no cambia automáticamente: dalo de baja y volvé a invitarlo. Si tiene una invitación pendiente, la podés reenviar o cancelar.' },
      { titulo: 'CASO 5 · Cuenta sin verificar o no activa', texto: 'No se puede invitar hasta que la cuenta esté verificada y activa.' },
    ],
  },
  {
    id: 'pacientes',
    titulo: 'Pacientes',
    intro: 'Los datos de salud de un paciente los ve solo su operador responsable actual. Propietario y moderador ven los datos administrativos.',
    pasos: [
      { texto: 'Agregá un paciente con nombre y apellido. Documento, nacimiento y sexo son opcionales. Si lo cargás como operador, quedás como responsable.', ir: { to: '/app/instituciones', label: 'Abrir Instituciones' }, boton: 'Agregar paciente', captura: 'institucional-pacientes-agregar.png' },
      { texto: 'Buscá y filtrá la lista. Editá los datos desde la ficha del paciente.' },
      { texto: 'Para medir, el responsable toca Medir con el dispositivo. Un paciente sin responsable no se puede medir.' },
      { texto: 'Para cambiar de responsable: el operador responsable transfiere el paciente y el destino acepta en Transferencias.' },
      { texto: 'Propietario y moderador cambian el responsable con una propuesta que el destino acepta, desde la ficha del paciente.' },
      { texto: 'Los pacientes de un operador dado de baja se reasignan en Reasignaciones: el sistema nunca elige el destino.' },
    ],
    detalles: [
      { titulo: 'Datos de salud', texto: 'Mediciones, gráficos y estadísticas: solo el operador responsable vigente. Los demás ven los datos administrativos.' },
      { titulo: 'Documento', texto: 'No puede repetirse dentro de la misma institución.' },
      { titulo: 'Dar de baja', texto: 'Propietario y moderador. El paciente queda en solo lectura.' },
    ],
    casos: [
      { titulo: 'CASO 1 · Agregar paciente', texto: 'Aparece en el listado de la institución con su responsable.' },
      { titulo: 'CASO 2 · Enviar solicitud de paciente', texto: 'Se envía al operador destino. Mientras no la acepte, el responsable actual sigue igual. Solo puede haber una solicitud pendiente por paciente.' },
      { titulo: 'CASO 3 · Transferir cargo', texto: 'El nuevo responsable pasa a tener los datos de salud cuando acepta. Hasta entonces, la transferencia se puede cancelar.' },
      { titulo: 'CASO 4 · Medir a un paciente', texto: 'Solo el operador responsable vigente. Los demás no ven el botón Medir.' },
    ],
  },
  {
    id: 'dispositivos-medicion',
    titulo: 'Dispositivos y medición',
    intro: 'El operador conecta el dispositivo y mide a sus pacientes. El inventario lo administran propietario y moderador.',
    pasos: [
      { texto: 'Operador: en Conectar dispositivo, con el puente en marcha, elegí el medio y el dispositivo de esta conexión.', ir: { to: '/app/instituciones', label: 'Abrir Instituciones' } },
      { texto: 'Operador: en Pacientes → Medir, elegí dispositivo, modo y alimentación; iniciá, esperá la lectura estable y tocá Guardar medición.' },
      { texto: 'Propietario y moderador: en Dispositivos cargá equipos, cambiá su estado y revisá el inventario.' },
      { texto: 'Para enviar resultados por correo, cargá el correo que te dio el paciente y confirmá que lo autorizó.' },
    ],
    detalles: [
      { titulo: 'Uso compartido', texto: 'Con el uso compartido habilitado, podés usar equipos de otra institución o sin vincular, sin cambiar su titularidad.' },
      { titulo: 'Resultados por correo', texto: 'Cada medición guardada se envía sola al correo autorizado. También podés enviar un resultado puntual a otro correo, que no se guarda.' },
      { titulo: 'Referencia capilar', texto: 'Se registra en el detalle de una medición de glucosa completada.' },
    ],
    casos: [
      { titulo: 'CASO 1 · Equipo sin institución', texto: 'Se vincula a la institución antes de usarlo. La confirmación es explícita y conserva sus mediciones.' },
      { titulo: 'CASO 2 · Equipo de otra institución', texto: 'Con modo restringido no se usa ni se revela. Con uso compartido se puede usar sin cambiar su titularidad.' },
    ],
  },
  {
    id: 'matrices',
    titulo: 'Matrices',
    intro: 'La matriz define las reglas de referencia que se aplican a las mediciones de glucosa. Todos ven cuál está vigente.',
    pasos: [
      { texto: 'Propietario o moderador: en Matrices tocá Crear matriz institucional.', ir: { to: '/app/matrices', label: 'Abrir Matrices' }, boton: 'Crear matriz institucional', captura: 'institucional-matrices-crear.png' },
      { texto: 'Abrí la matriz en borrador y tocá Agregar regla: sexo, condición de comida, rango de edad, minutos desde la ingesta e intervalo de glucosa de referencia.', boton: 'Agregar regla', captura: 'institucional-matrices-agregar-regla.png' },
      { texto: 'Tocá Revisar configuración para validar las reglas antes de guardar.', boton: 'Revisar configuración', captura: 'institucional-matrices-revisar.png' },
      { texto: 'Si la validación está bien, tocá Activar y confirmá. Las próximas mediciones la usan y la anterior queda como versión histórica.' },
      { texto: 'Para cambiar una matriz activa, creá una versión nueva: la activa no se edita.' },
      { texto: 'Exportá la matriz en CSV (por defecto), Excel o PDF: una fila por regla.' },
    ],
    detalles: [
      { titulo: 'Quién la ve', texto: 'Las matrices institucionales solo las ven propietario y moderador. La plataforma no las ve.' },
      { titulo: 'Prioridad', texto: 'Si hay una matriz institucional activa, se usa. Si no, se usa la global.' },
      { titulo: 'Qué es y qué no es', texto: 'Compara el valor con un rango. No es una clasificación clínica ni un algoritmo de estimación.' },
    ],
    casos: [
      { titulo: 'CASO 1 · Reglas válidas', texto: 'Pasan la validación y se pueden activar.' },
      { titulo: 'CASO 2 · Reglas inválidas', texto: 'Si dos reglas se solapan, se rechaza: corregí los rangos. Si una regla está repetida, quitala. Los huecos solo advierten, no bloquean.' },
      { titulo: 'CASO 3 · Seleccionar la matriz', texto: 'Desde la lista elegís la matriz a revisar. El operador solo la consulta y no puede editarla.' },
    ],
  },
  {
    id: 'panel-actividad-auditoria',
    titulo: 'Panel, actividad y auditoría',
    intro: 'Indicadores y registros de lo que pasa en la institución.',
    detalles: [
      { titulo: 'Panel', texto: 'Indicadores de la institución. No muestra grupos de menos de 5 pacientes.' },
      { titulo: 'Actividad', texto: 'Qué hizo el equipo. Lo ven propietario y moderador.' },
      { titulo: 'Auditoría', texto: 'Resumen, filtros y detalle de cada registro. Solo la ve el propietario, es de solo lectura y no muestra IP.' },
    ],
  },
  {
    id: 'exportar',
    titulo: 'Exportar datos',
    intro: 'Podés exportar listados en CSV (separado por punto y coma, UTF-8), Excel o PDF. Cada exportación queda registrada en la auditoría.',
    pasos: [
      { texto: 'Personal: en Personal elegí las personas (selección) o TODOS (con los filtros de rol, estado y búsqueda), luego el formato y Exportar. Así se exportan moderadores y operadores, filtrando por rol.' },
      { texto: 'Pacientes: en Pacientes elegí los pacientes o TODOS con los filtros, luego el formato y Exportar.' },
      { texto: 'Matrices: abrí la matriz y tocá Exportar. Elegí CSV, Excel o PDF.' },
    ],
    casos: [
      { titulo: 'CASO 1 · Exportar moderadores', texto: 'Propietario o moderador: en Personal, filtrá por rol Moderador y exportá.' },
      { titulo: 'CASO 2 · Exportar operadores', texto: 'Propietario o moderador: en Personal, filtrá por rol Operador y exportá. Un operador no tiene acceso al personal: el intento se rechaza y queda en la auditoría.' },
      { titulo: 'CASO 3 · Exportar pacientes', texto: 'Quien ve el listado de pacientes puede exportarlo. El operador exporta solo los suyos.' },
      { titulo: 'CASO 4 · Sin selección', texto: 'Si elegís SELECCIÓN sin marcar a nadie, el sistema pide que elijas al menos una persona.' },
      { titulo: 'CASO 5 · Selección desactualizada', texto: 'Si alguna persona ya no figura en el personal, el sistema pide actualizar el listado.' },
    ],
  },
  {
    id: 'notificaciones',
    titulo: 'Notificaciones',
    intro: 'Llegan según tu rol en la institución. Podés elegir el canal (aplicación, correo o ambos) en Preferencias.',
    pasos: [
      { texto: 'Revisá la bandeja y marcá como leído lo que ya atendiste. Podés borrarlo desde «Eliminar…».', ir: { to: '/app/notificaciones', label: 'Abrir Notificaciones' } },
      { texto: 'Configurá qué avisos recibir en Preferencias.', ir: { to: '/app/notificaciones/preferencias', label: 'Abrir Preferencias' } },
    ],
    detalles: [
      { titulo: 'Institución', texto: 'Invitaciones, nuevos operadores o moderadores, bajas, pacientes nuevos o a tu cargo, y solicitudes de transferencia aceptadas o rechazadas.' },
      { titulo: 'Mediciones', texto: 'Envío de resultados por correo, cuando sale o cuando no pudo salir.' },
      { titulo: 'Seguridad', texto: 'Inicios de sesión desde equipos nuevos, cambios de contraseña o de verificación en dos pasos, y actividad sospechosa.' },
    ],
  },
  TEMA_PERFIL,
  TEMA_SEGURIDAD,
  {
    id: 'problemas',
    titulo: 'Si algo no funciona',
    tabla: {
      encabezados: ['Qué ves', 'Qué hacer'],
      filas: [
        ['Cuenta pendiente de verificación', 'Abrí el enlace del correo o reenviá la verificación. El reenvío no extiende el plazo de 24 horas.'],
        ['Acceso bloqueado', 'Con 3 intentos fallidos el acceso se bloquea 15 minutos. Esperá y volvé a intentar.'],
        ['No ves una sección del menú', 'Tu rol no incluye esa sección (ver la tabla de roles).'],
        ['La invitación figura en espera', 'No hay cupo disponible: cuando se libere un lugar, la invitación sigue su curso.'],
        ['El dispositivo está en uso por otra cuenta', 'Esperá a que termine. Si queda sin uso, se libera solo a los 5 minutos.'],
        ['La institución está pausada', 'Escribí al soporte desde la tarjeta de la institución.'],
        ['El enlace de activación venció o ya se usó', 'Pedí uno nuevo a quien te invitó.'],
        ['Tu cuenta quedó sin institución', 'Tenés 30 días para aceptar una invitación o crear una institución.'],
      ],
    },
  },
];
