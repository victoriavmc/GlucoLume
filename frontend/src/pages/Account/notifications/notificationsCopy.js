// Textos y presentación de «Notificaciones»: qué avisos existen, cómo se agrupan y a dónde llevan. Los avisos y categorías vienen del
// backend (app/models/notificationEvents.py): aquí solo se decide cómo se muestran.

import {
  Activity, AlarmClock, KeyRound, MailPlus, MonitorSmartphone, ShieldAlert, ShieldCheck, UserPlus, Users,
} from 'lucide-react';

export const CUENTA_INDIVIDUAL = 'CONSUMIDOR_FINAL';
export const RUTA_BANDEJA = '/app/notificaciones';
export const RUTA_PREFERENCIAS = '/app/notificaciones/preferencias';

/** Categorías, en el orden en que se muestran. `individual`: solo las cuentas individuales reciben avisos de esa categoría. */
export const CATEGORIAS = {
  SEGURIDAD: { titulo: 'Seguridad', individual: false },
  GRUPO: { titulo: 'Grupo familiar', individual: true },
  RECORDATORIO: { titulo: 'Recordatorios de medición', individual: true },
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
};

/** Filtros de la bandeja. `params` es lo que se pide al backend; `categoria` oculta el filtro a quien no recibe esa categoría. */
export const FILTROS = [
  { key: 'TODAS', label: 'Todas', params: {} },
  { key: 'NO_LEIDAS', label: 'No leídas', params: { soloNoLeidas: true } },
  { key: 'SEGURIDAD', label: 'Seguridad', params: { categoria: 'SEGURIDAD' }, categoria: 'SEGURIDAD' },
  { key: 'RECORDATORIO', label: 'Recordatorios', params: { categoria: 'RECORDATORIO' }, categoria: 'RECORDATORIO' },
  { key: 'GRUPO', label: 'Grupo', params: { categoria: 'GRUPO' }, categoria: 'GRUPO' },
];

export function filtrosVisibles(tipoCuenta) {
  return FILTROS.filter((filtro) => !filtro.categoria || !CATEGORIAS[filtro.categoria].individual || tipoCuenta === CUENTA_INDIVIDUAL);
}

/** Categorías que se administran en Preferencias para este tipo de cuenta. */
export function categoriasVisibles(tipoCuenta) {
  return Object.keys(CATEGORIAS).filter((categoria) => !CATEGORIAS[categoria].individual || tipoCuenta === CUENTA_INDIVIDUAL);
}

/** Presentación de un aviso de la bandeja: la del evento, o la de su categoría si el backend manda uno que esta versión no conoce. */
export function presentacion(notificacion) {
  const evento = EVENTOS[notificacion.evento];
  if (evento) return { Icono: evento.icono, tono: evento.tono, categoria: CATEGORIAS[evento.categoria]?.titulo ?? '' };
  return { Icono: ShieldCheck, tono: 'security', categoria: CATEGORIAS[notificacion.categoria]?.titulo ?? '' };
}

// Destinos que existen en App.jsx. El backend ya solo guarda estos, pero la pantalla no confía en un texto recibido para navegar.
const DESTINOS = ['/app/mediciones', '/app/grupo', '/app/seguridad', RUTA_BANDEJA];

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
