// Etiquetas del módulo Medición (valores de CK_Medicion_modo, CK_Medicion_estado y CK_Medicion_condicionComida).
// Los formatos de fecha y número se comparten con Grupo para que todas las pantallas se vean igual.

import { MEALS, MODES, formatDate, formatDateTime, formatNumber } from '../groups/groupFormat.js';

export { MEALS, MODES, formatDate, formatDateTime, formatNumber };

export const STATES = {
  PENDIENTE: 'Pendiente',
  ADQUIRIENDO: 'Adquiriendo datos',
  PROCESANDO: 'Procesando',
  COMPLETADA: 'Completada',
  INVALIDA: 'Inválida',
  CANCELADA: 'Cancelada',
};

/** Estados en los que la medición sigue en curso (la pantalla consulta el estado real al backend). */
export const ACTIVE_STATES = ['PENDIENTE', 'ADQUIRIENDO', 'PROCESANDO'];

export const SEXO = { FEMENINO: 'Femenino', MASCULINO: 'Masculino' };

/** `datetime-local` entrega «AAAA-MM-DDTHH:MM»: el backend espera segundos. */
export function dateTimeForApi(value) {
  if (!value) return undefined;
  return value.length === 16 ? `${value}:00` : value;
}

export function stateBadge(state) {
  return state === 'COMPLETADA' ? 'is-on' : 'is-off';
}

/** Origen del valor de glucosa que informa el firmware. DEMO es un número sintético de prueba, no una glucemia. */
/** El índice óptico es adimensional y de poca magnitud: se muestra con hasta 4 decimales. */
export function formatIndex(value) {
  if (value === null || value === undefined) return '—';
  return Number(value).toLocaleString('es-AR', { maximumFractionDigits: 4 });
}

export const ORIGINS = { DEMO: 'DEMO (prueba)', EXPERIMENTAL: 'Experimental', SIN_CALIBRAR: 'Sin calibrar' };

export const DEMO_NOTICE = 'Datos de prueba (DEMO): la glucosa es un valor sintético que genera el firmware para verificar la '
  + 'comunicación. No es una glucemia, no entra en estadísticas ni en indicadores y no se envía como resultado.';

/** Estado del dispositivo que informa el backend (GET /acquisition/telemetry/status). */
export const DEVICE_STATES = {
  SIN_PUENTE: { label: 'Puente serie detenido', tone: 'is-off', hint: 'El programa que lee el Bluetooth no está en ejecución en el equipo del dispositivo.' },
  PUERTO_DESCONECTADO: { label: 'Bluetooth desconectado', tone: 'is-off', hint: 'Encendé el Arduino y revisá que el HC-05/HC-06 esté emparejado: el puente reintenta solo.' },
  SIN_DATOS: { label: 'Conectado, sin datos', tone: 'is-off', hint: 'El enlace está abierto pero el Arduino todavía no envía lecturas.' },
  CONECTADO: { label: 'Conectado', tone: 'is-on', hint: '' },
};
