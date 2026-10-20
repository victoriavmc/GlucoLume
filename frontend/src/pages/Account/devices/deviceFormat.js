// Etiquetas del inventario de dispositivos. El estado BAJA de la base es el «descomisionado» (retiro definitivo).

import { formatDate, formatDateTime } from '../groups/groupFormat.js';

export { formatDate, formatDateTime };

export const DEVICE_STATES = {
  OPERATIVO: 'Operativo', EN_MANTENIMIENTO: 'En mantenimiento', FUERA_DE_SERVICIO: 'Fuera de servicio', BAJA: 'Descomisionado',
};
// Estados que se pueden elegir manualmente (el retiro definitivo es su propia acción).
export const EDITABLE_STATES = ['OPERATIVO', 'EN_MANTENIMIENTO', 'FUERA_DE_SERVICIO'];
export const SENSORS = ['MAX30100', 'MAX30102'];

export function stateBadge(state) {
  return state === 'OPERATIVO' ? 'is-on' : 'is-off';
}

export const personLabel = (person) => [person?.nombre, person?.apellido].filter(Boolean).join(' ') || 'Sin nombre';
