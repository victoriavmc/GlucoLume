// Serie temporal de la sesión de medición en curso: ventana deslizante en memoria con las lecturas REALES que el backend recibe
// del Arduino (≈1 por segundo, mismo SSE/estado que ya usa la pantalla). Reglas:
//   · empieza cuando la sesión empieza: una lectura anterior al inicio de la sesión nunca se atribuye a ella;
//   · cambia o termina la sesión (guardar, cancelar, otra medición): la serie se descarta, no se mezcla con la anterior;
//   · una lectura sin dedo o con señal inválida entra como «inválida» (valor nulo), no como un valor ni como un cero;
//   · no se interpola ni se inventa ningún dato faltante.

import { useEffect, useState } from 'react';

export const SERIES_CAPACITY = 30;

function pointOf(reading) {
  const valid = Boolean(reading.dedo && reading.senalValida);
  const keep = (value) => (valid && value !== null && value !== undefined ? Number(value) : null);
  return {
    key: reading.instante, valid, origen: reading.origen, esDemo: Boolean(reading.esDemo),
    bpm: keep(reading.bpm), spo2: keep(reading.spo2), glucosa: keep(reading.glucosa), indiceOptico: keep(reading.indiceOptico),
  };
}

export function useSessionSeries(status, capacity = SERIES_CAPACITY) {
  const [series, setSeries] = useState({ id: null, points: [] });
  const sessionId = status?.sesion?.idMedicion ?? null;
  const startedAt = status?.sesion?.iniciada ?? null;
  const reading = status?.lectura ?? null;

  useEffect(() => {
    setSeries((current) => {
      if (sessionId === null) return current.id === null && current.points.length === 0 ? current : { id: null, points: [] };
      const points = current.id === sessionId ? current.points : [];
      const fresh = reading?.instante && startedAt && Date.parse(reading.instante) >= Date.parse(startedAt)
        && !points.some((point) => point.key === reading.instante);
      if (current.id === sessionId && !fresh) return current;
      return { id: sessionId, points: fresh ? [...points, pointOf(reading)].slice(-capacity) : points };
    });
  }, [sessionId, startedAt, reading, capacity]);

  return series.id === sessionId ? series.points : [];
}
