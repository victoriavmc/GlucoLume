// Etiquetas del módulo Grupo (valores del backend: app/schemas/group.py y Medicion).

export const ROLE_LABELS = { ADMINISTRADOR: 'Administrador/a', MIEMBRO: 'Miembro' };

// Permisos personales de compartición: independientes, ninguno implica a otro. Los gráficos y estadísticas son una
// visualización del historial: los habilita «Historial de mediciones» (no hay un permiso aparte).
export const SHARING_OPTIONS = [
  {
    field: 'compartePerfil', label: 'Datos básicos del perfil',
    detail: 'Edad y sexo usado por el modelo de medición. Nunca tu documento ni tu fecha de nacimiento.',
  },
  { field: 'comparteUltimaMedicion', label: 'Última medición', detail: 'Solo tu medición más reciente.' },
  {
    field: 'comparteHistorial', label: 'Historial de mediciones',
    detail: 'Tus mediciones completadas, con fecha y valores, y los gráficos y estadísticas calculados con ellas.',
  },
  {
    field: 'notificaMedicion', label: 'Aviso de medición', notice: true,
    detail: 'Avisa al grupo que te mediste, con día y hora. No dice cómo te fue: nunca incluye el valor.',
  },
];

/** Hay algo para ver de esa persona: cualquiera de los cuatro permisos (el aviso solo muestra fecha y hora). */
export function sharesAnything(member) {
  return SHARING_OPTIONS.some(({ field }) => member[field]);
}

/** Texto de glucosa de una medición compartida, identificando su carácter de prueba o experimental; null si no informa glucosa. */
export function glucoseText(measurement) {
  const value = measurement.glucosa ?? measurement.glucosaEstimada;
  if (value === null || value === undefined) return null;
  const kind = measurement.esDemo ? 'Glucosa de prueba (DEMO)'
    : measurement.origenGlucosa === 'EXPERIMENTAL' ? 'Glucosa experimental' : 'Glucosa estimada';
  return `${kind} ${formatNumber(value, 'mg/dL')}`;
}

/** «14/10/2026 a las 18:35» a partir de la fecha y hora sin zona del backend. */
export function formatNoticeMoment(value) {
  const [date = '', time = ''] = formatDateTime(value).split(' ');
  return time ? `${date} a las ${time}` : date;
}

export const NO_SHARING = Object.fromEntries(SHARING_OPTIONS.map(({ field }) => [field, false]));

export const MEALS = { AYUNO: 'En ayunas', POSTPRANDIAL: 'Después de comer', NO_INFORMADA: 'Comida sin informar' };
export const MODES = { OXIMETRIA: 'Oximetría', GLUCOSA_EXPERIMENTAL: 'Glucosa (experimental)' };

export function personName(person) {
  return [person.nombre, person.apellido].filter(Boolean).join(' ') || 'Integrante';
}

/** El backend guarda la hora de Argentina sin zona (AAAA-MM-DDTHH:MM:SS): se muestra tal cual. */
export function formatDateTime(value) {
  if (!value) return '';
  const [date, time = ''] = String(value).split('T');
  const [year, month, day] = date.split('-');
  return `${day}/${month}/${year}${time ? ` ${time.slice(0, 5)}` : ''}`;
}

const WEEKDAYS = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];

/** «Mié, 14/10/2026 00:49»: día de la semana, fecha y hora (hora de Argentina sin zona, tal cual la guarda el backend). */
export function formatWeekdayDateTime(value) {
  if (!value) return '';
  const [year, month, day] = String(value).split('T')[0].split('-').map(Number);
  const weekday = WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()];
  return `${weekday}, ${formatDateTime(value)}`;
}

export function formatDate(value) {
  return formatDateTime(value).split(' ')[0];
}

export function formatNumber(value, unit) {
  if (value === null || value === undefined) return '—';
  return `${Number(value).toLocaleString('es-AR', { maximumFractionDigits: 1 })}${unit ? ` ${unit}` : ''}`;
}

export function individualSignupUrl() {
  return `${window.location.origin}/registro?tipo=usuario`;
}
