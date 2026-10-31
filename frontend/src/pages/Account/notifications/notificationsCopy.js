// Textos y presentación de «Notificaciones»: qué avisos existen, cómo se agrupan y a dónde llevan. Los avisos y categorías vienen del
// backend (app/models/notificationEvents.py): aquí solo se decide cómo se muestran.

import {
  Activity, AlarmClock, ArrowRightLeft, Check, ClipboardList, KeyRound, MailPlus, MonitorSmartphone, ShieldAlert, ShieldCheck,
  Stethoscope, UserCheck, UserMinus, UserPlus, UserX, Users, X,
} from 'lucide-react';

export const CUENTA_INDIVIDUAL = 'CONSUMIDOR_FINAL';
export const CUENTA_INSTITUCIONAL = 'USUARIO_INSTITUCIONAL';
export const RUTA_BANDEJA = '/app/notificaciones';
export const RUTA_PREFERENCIAS = '/app/notificaciones/preferencias';

/**
 * Categorías, en el orden en que se muestran. `individual`: solo las cuentas individuales reciben avisos de esa categoría.
 * `institucional`: solo las cuentas institucionales; a cuál llega cada aviso lo decide el backend según el rol en la institución.
 */
export const CATEGORIAS = {
  SEGURIDAD: { titulo: 'Seguridad', individual: false },
  GRUPO: { titulo: 'Grupo familiar', individual: true },
  RECORDATORIO: { titulo: 'Recordatorios de medición', individual: true },
  INSTITUCION: { titulo: 'Institución', individual: false, institucional: true },
};

/** Avisos: texto en Preferencias, ícono y tono (`alert` = advertencia; `security`, `group`, `reminder` = categoría). */
export const EVENTOS = {
  INICIO_SESION: {
    categoria: 'SEGURIDAD', icono: MonitorSmartphone, tono: 'security', titulo: 'Nuevos dispositivos o accesos desconocidos',
    descripcion: 'Cuando alguien inicia sesión en tu cuenta desde un navegador o equipo que nunca habías usado. Cada inicio de sesión queda siempre en la auditoría.',
  },
  CAMBIO_CONTRASENA: {
    categoria: 'SEGURIDAD', icono: KeyRound, tono: 'security', titulo: 'Cambios de contraseña',
    descripcion: 'Cuando se cambia, se restablece o se agrega la contraseña de tu cuenta.',
  },
  CAMBIO_MFA: {
    categoria: 'SEGURIDAD', icono: ShieldCheck, tono: 'security', titulo: 'Cambios en la verificación en dos pasos',
    descripcion: 'Cuando se activa o se desactiva la verificación en dos pasos.',
  },
  ACTIVIDAD_SOSPECHOSA: {
    categoria: 'SEGURIDAD', icono: ShieldAlert, tono: 'alert', titulo: 'Actividad sospechosa',
    descripcion: 'Intentos de acceso fallidos repetidos o bloqueos de tu cuenta.',
  },
  INVITACION_GRUPO: {
    categoria: 'GRUPO', icono: MailPlus, tono: 'group', titulo: 'Invitaciones a un grupo',
    descripcion: 'Cuando te invitan a un grupo familiar.',
  },
  AGREGADO_GRUPO: {
    categoria: 'GRUPO', icono: UserPlus, tono: 'group', titulo: 'Me incorporo a un grupo',
    descripcion: 'Cuando aceptás una invitación y pasás a formar parte de un grupo.',
  },
  NUEVA_ACCION_GRUPO: {
    categoria: 'GRUPO', icono: Users, tono: 'group', titulo: 'Incorporaciones y salidas del grupo',
    descripcion: 'Cuando alguien se suma o abandona tu grupo.',
  },
  MEDICION_GRUPO: {
    categoria: 'GRUPO', icono: Activity, tono: 'group', titulo: 'Mediciones del grupo',
    descripcion: 'Cuando alguien del grupo se midió y eligió avisar. Respeta lo que cada persona decidió compartir y nunca incluye el resultado.',
  },
  RECORDATORIO_MEDICION: {
    categoria: 'RECORDATORIO', icono: AlarmClock, tono: 'reminder', titulo: 'Recordatorio para medirme',
    descripcion: 'Te recordamos medirte en el horario que configures más abajo.',
  },
  INSTITUCION_OPERADOR_NUEVO: {
    categoria: 'INSTITUCION', icono: UserPlus, tono: 'institution', titulo: 'Nuevos operadores',
    descripcion: 'Cuando una persona se incorpora como operador de tu institución. Lo reciben propietarios y moderadores.',
  },
  INSTITUCION_OPERADOR_BAJA: {
    categoria: 'INSTITUCION', icono: UserMinus, tono: 'institution', titulo: 'Bajas de operadores',
    descripcion: 'Cuando se da de baja a un operador de la institución. Lo reciben propietarios y moderadores.',
  },
  INSTITUCION_MODERADOR_NUEVO: {
    categoria: 'INSTITUCION', icono: UserCheck, tono: 'institution', titulo: 'Nuevos moderadores',
    descripcion: 'Cuando una persona se incorpora como moderadora de la institución. Lo reciben propietarios y moderadores.',
  },
  INSTITUCION_MODERADOR_BAJA: {
    categoria: 'INSTITUCION', icono: UserX, tono: 'institution', titulo: 'Bajas de moderadores',
    descripcion: 'Cuando se da de baja a un moderador de la institución. Lo reciben propietarios y moderadores.',
  },
  INSTITUCION_PACIENTE_NUEVO: {
    categoria: 'INSTITUCION', icono: Stethoscope, tono: 'institution', titulo: 'Pacientes nuevos',
    descripcion: 'Cuando se registra un paciente en la institución. Lo reciben propietarios y moderadores.',
  },
  INSTITUCION_PACIENTE_A_CARGO: {
    categoria: 'INSTITUCION', icono: ClipboardList, tono: 'institution', titulo: 'Pacientes a mi cargo',
    descripcion: 'Cuando un paciente pasa a estar a tu cargo, por alta, asignación o transferencia.',
  },
  INSTITUCION_SOLICITUD_NUEVA: {
    categoria: 'INSTITUCION', icono: ArrowRightLeft, tono: 'institution', titulo: 'Solicitudes de pacientes',
    descripcion: 'Cuando otro operador te pide un paciente, o la gestión propone uno para vos.',
  },
  INSTITUCION_SOLICITUD_ACEPTADA: {
    categoria: 'INSTITUCION', icono: Check, tono: 'institution', titulo: 'Solicitudes aceptadas',
    descripcion: 'Cuando el operador destino acepta un paciente que pediste.',
  },
  INSTITUCION_SOLICITUD_RECHAZADA: {
    categoria: 'INSTITUCION', icono: X, tono: 'institution', titulo: 'Solicitudes rechazadas',
    descripcion: 'Cuando el operador destino rechaza un paciente que pediste.',
  },
};

/** Filtros de la bandeja. `params` es lo que se pide al backend; `categoria` oculta el filtro a quien no recibe esa categoría. */
export const FILTROS = [
  { key: 'TODAS', label: 'Todas', params: {} },
  { key: 'NO_LEIDAS', label: 'No leídas', params: { soloNoLeidas: true } },
  { key: 'SEGURIDAD', label: 'Seguridad', params: { categoria: 'SEGURIDAD' }, categoria: 'SEGURIDAD' },
  { key: 'RECORDATORIO', label: 'Recordatorios', params: { categoria: 'RECORDATORIO' }, categoria: 'RECORDATORIO' },
  { key: 'GRUPO', label: 'Grupo', params: { categoria: 'GRUPO' }, categoria: 'GRUPO' },
  { key: 'INSTITUCION', label: 'Institución', params: { categoria: 'INSTITUCION' }, categoria: 'INSTITUCION' },
];

/** ¿Recibe esta cuenta avisos de la categoría? Las de seguridad son de todas las cuentas. */
function recibeCategoria(categoria, tipoCuenta) {
  const { individual, institucional } = CATEGORIAS[categoria];
  if (individual) return tipoCuenta === CUENTA_INDIVIDUAL;
  if (institucional) return tipoCuenta === CUENTA_INSTITUCIONAL;
  return true;
}

export function filtrosVisibles(tipoCuenta) {
  return FILTROS.filter((filtro) => !filtro.categoria || recibeCategoria(filtro.categoria, tipoCuenta));
}

/** Categorías que se administran en Preferencias para este tipo de cuenta. */
export function categoriasVisibles(tipoCuenta) {
  return Object.keys(CATEGORIAS).filter((categoria) => recibeCategoria(categoria, tipoCuenta));
}

/** Presentación de un aviso de la bandeja: la del evento, o la de su categoría si el backend manda uno que esta versión no conoce. */
export function presentacion(notificacion) {
  const evento = EVENTOS[notificacion.evento];
  if (evento) return { Icono: evento.icono, tono: evento.tono, categoria: CATEGORIAS[evento.categoria]?.titulo ?? '' };
  return { Icono: ShieldCheck, tono: 'security', categoria: CATEGORIAS[notificacion.categoria]?.titulo ?? '' };
}

// Destinos que existen en App.jsx. El backend ya solo guarda estos, pero la pantalla no confía en un texto recibido para navegar.
const DESTINOS = ['/app/mediciones', '/app/grupo', '/app/seguridad', '/app/instituciones', RUTA_BANDEJA];

/** Ruta interna válida a la que lleva el aviso, o null (sin enlaces externos ni rutas inventadas). */
export function destinoSeguro(url) {
  if (typeof url !== 'string' || !url.startsWith('/app/') || /[\\:?#]|\/\//.test(url)) return null;
  return DESTINOS.some((base) => url === base || url.startsWith(`${base}/`)) ? url : null;
}

const mismoDia = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

/** 'HOY' | 'AYER' | 'ANTERIORES' según el día (del equipo de quien mira) en que se creó el aviso. */
export function grupoDeDia(fechaCreacion, ahora = new Date()) {
  const fecha = new Date(fechaCreacion);
  if (Number.isNaN(fecha.getTime())) return 'ANTERIORES';
  if (mismoDia(fecha, ahora)) return 'HOY';
  const ayer = new Date(ahora);
  ayer.setDate(ayer.getDate() - 1);
  return mismoDia(fecha, ayer) ? 'AYER' : 'ANTERIORES';
}

export const GRUPOS_DE_DIA = [
  { key: 'HOY', label: 'Hoy' },
  { key: 'AYER', label: 'Ayer' },
  { key: 'ANTERIORES', label: 'Anteriores' },
];

/** Agrupa (en orden) los avisos por día, sin grupos vacíos. */
export function agruparPorDia(notificaciones, ahora = new Date()) {
  return GRUPOS_DE_DIA
    .map(({ key, label }) => ({ key, label, items: notificaciones.filter((n) => grupoDeDia(n.fechaCreacion, ahora) === key) }))
    .filter((grupo) => grupo.items.length > 0);
}
