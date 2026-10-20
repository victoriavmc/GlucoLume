// Datos de Inicio de una cuenta individual: últimos valores medidos y la serie de glucosa reciente. Todo sale de GET /measurements/evolution
// (mediciones guardadas reales): nada se inventa ni se clasifica. El último valor es el más reciente EXPERIMENTAL; si solo hay pruebas, el de la
// última prueba DEMO, identificada como tal (igual que en «Mi dashboard»).

import { useEffect, useState } from 'react';

import { friendlyError } from '../../../auth/errorMessages.js';
import * as measurementsApi from '../../../api/measurementsApi.js';

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

/** Últimos valores (una consulta de 90 días) y la serie del período elegido para el gráfico (otra consulta, solo cuando cambia). */
export function useHomeData({ enabled, chartDays }) {
  const [latest, setLatest] = useState(undefined); // undefined: cargando
  const [chart, setChart] = useState(undefined);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!enabled) return undefined;
    let active = true;
    measurementsApi.getOwnEvolution({ dias: LATEST_DAYS, origen: 'TODOS' }).then(
      (data) => { if (active) setLatest(latestValues(data.puntos ?? [])); },
      (loadError) => { if (active) { setLatest(null); setError(friendlyError(loadError)); } },
    );
    return () => { active = false; };
  }, [enabled]);

  useEffect(() => {
    if (!enabled) return undefined;
    let active = true;
    setChart(undefined);
    measurementsApi.getOwnEvolution({ dias: chartDays, origen: 'TODOS' }).then(
      (data) => { if (active) setChart(data); },
      (loadError) => { if (active) { setChart(null); setError(friendlyError(loadError)); } },
    );
    return () => { active = false; };
  }, [enabled, chartDays]);

  return { latest, chart, error };
}
