// Modelo de la «Evolución de mis mediciones»: variables, filtros de origen y agregación. Cada medición guardada es un punto (observación
// discreta, no un monitoreo continuo). Nada se interpola: si falta un valor, el punto no existe. Los valores DEMO nunca se mezclan con
// los experimentales en promedios ni tendencias.

export const VARIABLES = {
  frecuenciaCardiaca: { key: 'frecuenciaCardiaca', label: 'Frecuencia cardíaca', unit: 'lpm', decimals: 0, color: '#e3101e' },
  spo2: { key: 'spo2', label: 'Saturación de oxígeno (SpO₂)', unit: '%', decimals: 1, color: '#0f8b8d' },
  glucosa: { key: 'glucosa', label: 'Glucosa experimental', demoLabel: 'Glucosa DEMO (simulada)', unit: 'mg/dL', decimals: 1, color: '#d98200' },
  calidadSenal: { key: 'calidadSenal', label: 'Calidad de señal', unit: '', decimals: 2, color: '#7a5cc2' },
  indiceOptico: { key: 'indiceOptico', label: 'Índice óptico', unit: '', decimals: 4, color: '#5b6b8c' },
};

export const ORIGIN_FILTERS = {
  EXPERIMENTAL: 'Mediciones experimentales',
  DEMO: 'Mediciones DEMO',
  TODOS: 'Todos los registros',
};

/** Identificación visible del origen en el título de cada gráfico: los datos DEMO son simulados y nunca resultados clínicos. */
export const ORIGIN_SUFFIX = {
  EXPERIMENTAL: 'Experimental',
  DEMO: 'DEMO (datos simulados)',
  TODOS: 'Experimental y DEMO (series separadas)',
};

export const GRANULARITIES = { MEDICION: 'Cada medición', HORA: 'Promedio por hora', DIA: 'Promedio por día' };

const STAMP = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/;

/** Fecha/hora de una medición («AAAA-MM-DDTHH:MM:SS», hora de Argentina sin zona) como número, sin conversión de zona horaria. */
export function parseStamp(text) {
  const match = STAMP.exec(text);
  if (!match) return NaN;
  const [, year, month, day, hour, minute] = match;
  return Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute));
}

const two = (value) => String(value).padStart(2, '0');

export function formatDay(ms) {
  const date = new Date(ms);
  return `${two(date.getUTCDate())}/${two(date.getUTCMonth() + 1)}/${date.getUTCFullYear()}`;
}

export function formatClock(ms) {
  const date = new Date(ms);
  return `${two(date.getUTCHours())}:${two(date.getUTCMinutes())}`;
}

export function formatValue(value, decimals) {
  return Number(value).toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: decimals });
}

function passes(point, filter) {
  return filter === 'TODOS' || (filter === 'DEMO' ? point.esDemo : !point.esDemo);
}

/** Puntos de una variable según el filtro de origen. Solo existen donde hay un valor real. */
export function seriesFor(points, variable, filter) {
  return points
    .filter((point) => passes(point, filter) && point[variable] !== null && point[variable] !== undefined)
    .map((point) => ({
      key: point.idMedicion, ids: [point.idMedicion], t: parseStamp(point.fecha), value: Number(point[variable]), demo: point.esDemo,
      origin: point.origen, mode: point.modoMedicion, count: 1,
    }))
    .filter((point) => Number.isFinite(point.t))
    .sort((a, b) => a.t - b.t);
}

export const HOUR = 3_600_000;
export const DAY = 24 * HOUR;

/** Agrega por hora o día (promedio dentro de cada grupo DEMO/experimental por separado). `MEDICION` deja cada observación tal cual. */
export function aggregateSeries(series, granularity) {
  if (granularity === 'MEDICION') return series;
  const size = granularity === 'HORA' ? HOUR : DAY;
  const buckets = new Map();
  for (const point of series) {
    const start = Math.floor(point.t / size) * size;
    const id = `${start}:${point.demo ? 'demo' : 'exp'}`;
    if (!buckets.has(id)) buckets.set(id, { key: id, start, demo: point.demo, items: [] });
    buckets.get(id).items.push(point);
  }
  return [...buckets.values()].sort((a, b) => a.start - b.start).map((bucket) => ({
    key: bucket.key, ids: bucket.items.flatMap((item) => item.ids), t: bucket.start + (granularity === 'HORA' ? HOUR / 2 : DAY / 2),
    value: bucket.items.reduce((sum, item) => sum + item.value, 0) / bucket.items.length, demo: bucket.demo,
    origin: bucket.items.length === 1 ? bucket.items[0].origin : bucket.demo ? 'DEMO' : 'EXPERIMENTAL',
    mode: bucket.items.length === 1 ? bucket.items[0].mode : null, count: bucket.items.length, items: bucket.items,
    bucket: { from: bucket.start, to: bucket.start + size, granularity },
  }));
}

/** Ventana de tiempo del período elegido, para que el eje X represente el período y no solo el rango de los datos.
 * El backend informa `desde` (ahora − N días, o el inicio del rango) y `hasta` (solo en rangos explícitos). */
export function periodWindow(data, period, points) {
  const start = data?.desde ? parseStamp(data.desde) : NaN;
  if (!Number.isFinite(start)) return undefined;
  const explicitEnd = data?.hasta ? parseStamp(data.hasta) : NaN;
  let end = explicitEnd;
  if (!Number.isFinite(end)) {
    const days = !period?.desde && !period?.hasta ? Number(period?.dias) : NaN;
    end = Number.isFinite(days) ? start + days * DAY : Math.max(start + HOUR, ...points.map((point) => point.t));
  }
  return [start, end];
}

const TICK_STEPS = [HOUR, 2 * HOUR, 3 * HOUR, 6 * HOUR, 12 * HOUR, DAY, 2 * DAY, 7 * DAY, 14 * DAY, 30 * DAY];

/** Marcas del eje X en horas o días «redondos» (00:00, 06:00, 12:00… o cada día), nunca en instantes arbitrarios. */
export function timeTicks(t0, t1, max = 7) {
  const span = Math.max(t1 - t0, HOUR);
  const step = TICK_STEPS.find((candidate) => span / candidate <= max - 1) ?? TICK_STEPS.at(-1);
  const ticks = [];
  for (let tick = Math.ceil(t0 / step) * step; tick <= t1; tick += step) ticks.push(tick);
  return { ticks, step };
}

/** Texto de la hora o del bloque que representa un punto: «23:00–00:00» para un promedio por hora, «Día completo» por día. */
export function bucketLabel(point) {
  if (!point.bucket) return null;
  return point.bucket.granularity === 'HORA' ? `${formatClock(point.bucket.from)}–${formatClock(point.bucket.to)}` : 'Día completo';
}


/** Nombre de la variable en un detalle o tooltip: una prueba DEMO de glucosa es «simulada», nunca «experimental». */
export function variableName(variable, demo) {
  const spec = VARIABLES[variable];
  return demo && spec.demoLabel ? spec.demoLabel : spec.label;
}

/** Resumen breve de un punto, en palabras: qué es y qué NO es (las pruebas DEMO no son clínicas ni entran en promedios experimentales). */
export function describePoint(point, variable) {
  if (point.bucket) {
    const unit = point.bucket.granularity === 'HORA' ? 'esa hora' : 'ese día';
    return `Promedio de ${point.count} ${point.count === 1 ? 'medición' : 'mediciones'} de ${unit}${point.demo ? ', todas pruebas DEMO' : ''}.`;
  }
  if (point.demo) return 'Prueba DEMO del firmware: valor simulado, no es una medición clínica ni entra en los promedios experimentales.';
  if (variable === 'glucosa') return 'Estimación experimental de glucosa a partir de la señal óptica: no es un resultado clínico.';
  return 'Medición experimental guardada en el historial.';
}

/** Los demás valores de la MISMA medición (solo si el punto es una medición, no un promedio). `raw` tiene los campos de la variable. */
export function otherValues(raw, exclude) {
  if (!raw) return [];
  return Object.keys(VARIABLES)
    .filter((key) => key !== exclude && raw[key] !== null && raw[key] !== undefined)
    .map((key) => ({ label: VARIABLES[key].label, value: `${formatValue(raw[key], VARIABLES[key].decimals)} ${VARIABLES[key].unit}`.trim() }));
}
