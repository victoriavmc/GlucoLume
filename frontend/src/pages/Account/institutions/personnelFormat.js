// Etiquetas del módulo Personal. Los estados y roles son los reales del backend (CK_InstitucionUsuario_estado / _rol).

import { formatDateTime } from './institutionFormat.js';

export const RELATION_STATES = { ACTIVO: 'Activo', PENDIENTE: 'Pendiente de incorporación', SUSPENDIDO: 'Suspendido', BAJA: 'Dado de baja' };

/** Estado a mostrar con su tono: una invitación pendiente que venció se dice así; no se la presenta como activa. */
export function stateInfo(person) {
  if (person.estadoRelacion === 'BAJA' && person.datosEliminados) return { label: 'Eliminado', tone: 'is-off' };
  if (person.estadoRelacion === 'PENDIENTE' && person.invitacionVencida) return { label: 'Invitación vencida', tone: 'is-denied' };
  if (person.estadoRelacion === 'PENDIENTE' && person.cuentaPendiente) return { label: 'Cuenta pendiente de activación', tone: 'is-warn' };
  const label = RELATION_STATES[person.estadoRelacion] ?? person.estadoRelacion;
  if (person.estadoRelacion === 'ACTIVO') return { label, tone: 'is-on' };
  if (person.estadoRelacion === 'PENDIENTE') return { label, tone: 'is-warn' };
  return { label, tone: 'is-off' };
}

/** «15/10/2026 — 16:14» (hora de Argentina, tal como la guarda el backend). */
export function when(value, fallback = '') {
  if (!value) return fallback;
  return formatDateTime(value).replace(' ', ' — ');
}

export const initials = (person) => [person.nombre, person.apellido].filter(Boolean).map((part) => part[0].toUpperCase()).join('') || '?';
