// Cómo se presenta una medición compartida del grupo. Una prueba DEMO se identifica siempre («DEMO — Medición de prueba») y nunca se presenta
// como medición clínica; su glucosa es sintética. `glucosaEstimada` (cálculo del servidor) y `glucosaDispositivo` (lo informa el firmware con su
// origen) son conceptos distintos y no se confunden.

import { formatNumber } from './groupFormat.js';

export const DEMO_LABEL = 'DEMO — Medición de prueba';
export const ORIGIN_LABELS = { DEMO: 'DEMO (prueba)', EXPERIMENTAL: 'Experimental', SIN_CALIBRAR: 'Sin calibrar' };

/** Texto de glucosa de una medición compartida, o null si no tiene ninguna. `glucosa` es el valor que el servidor ya eligió para mostrar. */
export function glucoseText(measurement) {
  const device = measurement.glucosaDispositivo ?? measurement.glucosa ?? null;
  if (measurement.esDemo && device !== null) {
    return `Glucosa DEMO (simulada) ${formatNumber(device, measurement.unidadGlucosa ?? 'mg/dL')}`;
  }
  if (measurement.glucosaEstimada !== null && measurement.glucosaEstimada !== undefined) {
    return `Glucosa estimada ${formatNumber(measurement.glucosaEstimada, 'mg/dL')}`;
  }
  if (device !== null && measurement.origenGlucosa === 'EXPERIMENTAL') {
    return `Glucosa experimental ${formatNumber(device, measurement.unidadGlucosa ?? 'mg/dL')}`;
  }
  return null;
}
