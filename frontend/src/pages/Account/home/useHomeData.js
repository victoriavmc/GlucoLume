// Datos de Inicio de una cuenta individual: últimos valores medidos y la serie de glucosa reciente. Todo sale de GET /measurements/evolution
// (mediciones guardadas reales): nada se inventa ni se clasifica. El último valor es el más reciente EXPERIMENTAL; si solo hay pruebas, el de la
// última prueba DEMO, identificada como tal (igual que en «Mi dashboard»).

import { friendlyError } from '../../../auth/errorMessages.js';
import * as measurementsApi from '../../../api/measurementsApi.js';
import { useCachedQuery } from '../../../utils/queryCache.js';

const LATEST_DAYS = 90;
const VARIABLE_KEYS = ['glucosa', 'frecuenciaCardiaca', 'spo2', 'indiceOptico'];

/** Último valor de cada variable entre los puntos (en orden cronológico): experimental primero y, si no hay, la última prueba DEMO. */
export function latestValues(points) {
  const result = {};
  for (const key of VARIABLE_KEYS) {
    let found = null;
    for (let index = points.length - 1; index >= 0; index -= 1) {
      const point = points[index];
      if (point[key] === null || point[key] === undefined) continue;
      if (!point.esDemo) {
        found = { value: Number(point[key]), when: point.fecha, demo: false };
        break;
      }
      if (found === null) found = { value: Number(point[key]), when: point.fecha, demo: true }; // se sigue buscando uno experimental
    }
    result[key] = found;
  }
  return result;
}

/**
 * Últimos valores (una consulta de 90 días) y la serie del período elegido para el gráfico (otra consulta). Ambas se recuerdan por clave: al
 * volver a Inicio se dibujan al instante y se actualizan en segundo plano.
 */
export function useHomeData({ enabled, chartDays }) {
  const latestQuery = useCachedQuery(
    `home:latest:${LATEST_DAYS}`,
    () => measurementsApi.getOwnEvolution({ dias: LATEST_DAYS, origen: 'TODOS' }),
    enabled,
  );
  const chartQuery = useCachedQuery(
    `home:chart:${chartDays}`,
    () => measurementsApi.getOwnEvolution({ dias: chartDays, origen: 'TODOS' }),
    enabled,
  );

  const failure = latestQuery.error ?? chartQuery.error;
  return {
    // undefined: cargando; null: falló y no hay nada guardado; objeto: los valores.
    latest: latestQuery.data === undefined ? (latestQuery.error ? null : undefined) : latestValues(latestQuery.data.puntos ?? []),
    chart: chartQuery.data === undefined ? (chartQuery.error ? null : undefined) : chartQuery.data,
    error: failure ? friendlyError(failure) : '',
  };
}
