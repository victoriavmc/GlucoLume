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

export const GRANULARITIES = { MEDICION: 'Cada medición', HORA: 'Promedio por hora', DIA: 'Promedio por día', SEMANA: 'Promedio por semana', MES: 'Promedio por mes' };

/** Nombre corto de cada agrupación para los botones y los textos («por día», «por mes»…). */
export const GROUPING_LABELS = { MEDICION: 'Cada medición', HORA: 'Por hora', DIA: 'Por día', SEMANA: 'Por semana', MES: 'Por mes' };

/** Períodos de Inicio (días): 1 = últimas 24 horas. Hay datos guardados por todo el período; el gráfico agrupa para que se lea. */
export const HOME_PERIODS = [
  { days: 1, label: '1D', name: 'Último día' },
  { days: 7, label: '7D', name: 'Últimos 7 días' },
  { days: 30, label: '30D', name: 'Últimos 30 días' },
  { days: 90, label: '90D', name: 'Últimos 90 días' },
  { days: 180, label: '6M', name: 'Últimos 6 meses' },
  { days: 365, label: '1A', name: 'Último año' },
  { days: 1095, label: '3A', name: 'Últimos 3 años' },
];

/** Agrupaciones que tienen sentido para cada período (la de por defecto va primero en `fallback`). Evita miles de barras vacías. */
const PERIOD_GROUPINGS = {
  1: { fallback: 'MEDICION', options: ['MEDICION', 'HORA'] },
  7: { fallback: 'MEDICION', options: ['MEDICION', 'DIA'] },
  30: { fallback: 'DIA', options: ['MEDICION', 'DIA', 'SEMANA'] },
  90: { fallback: 'SEMANA', options: ['DIA', 'SEMANA', 'MES'] },
  180: { fallback: 'SEMANA', options: ['SEMANA', 'MES'] },
  365: { fallback: 'MES', options: ['SEMANA', 'MES'] },
  1095: { fallback: 'MES', options: ['MES'] },
};

export function groupingOptions(days) {
  return PERIOD_GROUPINGS[days] ?? PERIOD_GROUPINGS[30];
}

/** La agrupación que se usa: la elegida si el período la permite; si no, la de por defecto del período. */
export function effectiveGrouping(days, chosen) {
  const { fallback, options } = groupingOptions(days);
  return chosen && options.includes(chosen) ? chosen : fallback;
}

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
      // Semáforo solo para glucosa experimental: una prueba DEMO es simulada y no se clasifica.
      semaforo: point.esDemo ? null : point.semaforo ?? null,
    }))
    .filter((point) => Number.isFinite(point.t))
    .sort((a, b) => a.t - b.t);
}

export const HOUR = 3_600_000;
export const DAY = 24 * HOUR;

/** Inicio del bloque que contiene `t`: hora, día, semana (desde el lunes) o mes. Los instantes son «hora local sin zona» (ver parseStamp). */
export function bucketStart(t, granularity) {
  if (granularity === 'HORA') return Math.floor(t / HOUR) * HOUR;
  if (granularity === 'DIA') return Math.floor(t / DAY) * DAY;
  const date = new Date(t);
  if (granularity === 'SEMANA') {
    const sinceMonday = (date.getUTCDay() + 6) % 7;
    return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() - sinceMonday);
  }
  return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1); // MES
}

/** Inicio del bloque siguiente al que empieza en `start`. */
export function nextBucketStart(start, granularity) {
  if (granularity === 'HORA') return start + HOUR;
  if (granularity === 'DIA') return start + DAY;
  if (granularity === 'SEMANA') return start + 7 * DAY;
  const date = new Date(start);
  return Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 1);
}

/** Agrega por hora, día, semana o mes (promedio dentro de cada grupo DEMO/experimental por separado). `MEDICION` deja cada observación tal cual. */
export function aggregateSeries(series, granularity) {
  if (granularity === 'MEDICION') return series;
  const buckets = new Map();
  for (const point of series) {
    const start = bucketStart(point.t, granularity);
    const id = `${start}:${point.demo ? 'demo' : 'exp'}`;
    if (!buckets.has(id)) buckets.set(id, { key: id, start, demo: point.demo, items: [] });
    buckets.get(id).items.push(point);
  }
  return [...buckets.values()].sort((a, b) => a.start - b.start).map((bucket) => {
    const end = nextBucketStart(bucket.start, granularity);
    return {
      key: bucket.key, ids: bucket.items.flatMap((item) => item.ids), t: (bucket.start + end) / 2,
      value: bucket.items.reduce((sum, item) => sum + item.value, 0) / bucket.items.length, demo: bucket.demo,
      origin: bucket.items.length === 1 ? bucket.items[0].origin : bucket.demo ? 'DEMO' : 'EXPERIMENTAL',
      mode: bucket.items.length === 1 ? bucket.items[0].mode : null, count: bucket.items.length, items: bucket.items,
      bucket: { from: bucket.start, to: end, granularity },
    };
  });
}

/**
 * Mediciones por bloque de tiempo: por modo (oximetría / glucosa) y por condición de comida. Incluye los bloques vacíos del período
 * (`window` = [inicio, fin]) para que el eje muestre también los días o meses sin mediciones. Cuenta todas las mediciones completadas
 * (experimentales y DEMO), tal como las devuelve el historial. Sin dato de comida cuenta como «sin informar».
 */
export function countByBlock(points, granularity, window) {
  const blocks = new Map();
  const blockAt = (start) => {
    if (!blocks.has(start)) {
      blocks.set(start, { start, end: nextBucketStart(start, granularity), total: 0, oximetria: 0, glucosa: 0, ayuno: 0, postprandial: 0, sinInformar: 0 });
    }
    return blocks.get(start);
  };
  if (window && Number.isFinite(window[0]) && Number.isFinite(window[1])) {
    for (let start = bucketStart(window[0], granularity); start < window[1]; start = nextBucketStart(start, granularity)) blockAt(start);
  }
  for (const point of points) {
    const t = parseStamp(point.fecha);
    if (!Number.isFinite(t)) continue;
    const block = blockAt(bucketStart(t, granularity));
    block.total += 1;
    if (point.modoMedicion === 'OXIMETRIA') block.oximetria += 1;
    else if (point.modoMedicion === 'GLUCOSA_EXPERIMENTAL') block.glucosa += 1;
    if (point.condicionComida === 'AYUNO') block.ayuno += 1;
    else if (point.condicionComida === 'POSTPRANDIAL') block.postprandial += 1;
    else block.sinInformar += 1;
  }
  return [...blocks.values()].sort((a, b) => a.start - b.start);
}

/** Granularidad de los gráficos de conteo: con «cada medición» se cuenta por hora (un día) o por día. */
export function countGranularity(days, grouping) {
  if (grouping !== 'MEDICION') return grouping;
  return days <= 1 ? 'HORA' : 'DIA';
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

const TICK_STEPS = [HOUR, 2 * HOUR, 3 * HOUR, 6 * HOUR, 12 * HOUR, DAY, 2 * DAY, 7 * DAY, 14 * DAY, 30 * DAY, 60 * DAY, 91 * DAY, 182 * DAY, 365 * DAY];

/** Marcas del eje X en horas o días «redondos» (00:00, 06:00, 12:00… o cada día), nunca en instantes arbitrarios. */
export function timeTicks(t0, t1, max = 7) {
  const span = Math.max(t1 - t0, HOUR);
  const step = TICK_STEPS.find((candidate) => span / candidate <= max - 1) ?? TICK_STEPS.at(-1);
  const ticks = [];
  for (let tick = Math.ceil(t0 / step) * step; tick <= t1; tick += step) ticks.push(tick);
  return { ticks, step };
}

/** Cómo se nombra un bloque en un texto: «de esa hora», «de ese mes»… */
export const BLOCK_NAMES = { HORA: 'esa hora', DIA: 'ese día', SEMANA: 'esa semana', MES: 'ese mes' };

const monthLabel = (ms) => {
  const text = new Date(ms).toLocaleDateString('es-AR', { month: 'long', year: 'numeric', timeZone: 'UTC' });
  return text.charAt(0).toUpperCase() + text.slice(1);
};

/** Texto de la hora o del bloque que representa un punto: «23:00–00:00» por hora, «Día completo», «Semana del 02/03 al 08/03» o «Marzo de 2026». */
export function bucketLabel(point) {
  if (!point.bucket) return null;
  const { from, to, granularity } = point.bucket;
  if (granularity === 'HORA') return `${formatClock(from)}–${formatClock(to)}`;
  if (granularity === 'DIA') return 'Día completo';
  if (granularity === 'SEMANA') return `Semana del ${formatDay(from).slice(0, 5)} al ${formatDay(to - DAY).slice(0, 5)}`;
  return monthLabel(from);
}

/** Fecha y, si corresponde, hora o rango de un punto (medición o bloque agregado), para el cursor, el teclado y el tooltip. */
export function pointWhen(point) {
  if (!point.bucket) return { date: formatDay(point.t), time: formatClock(point.t) };
  const { from, to, granularity } = point.bucket;
  if (granularity === 'HORA') return { date: formatDay(from), time: `${formatClock(from)}–${formatClock(to)}` };
  if (granularity === 'DIA') return { date: formatDay(from), time: 'Día completo' };
  return { date: bucketLabel(point), time: undefined }; // semana o mes: el rango ya dice la fecha
}

/** Eje corto de un bloque de conteo: «14:00», «15/03» o «mar 26». */
export function shortBlockLabel(start, granularity) {
  if (granularity === 'HORA') return formatClock(start);
  if (granularity === 'MES') {
    const text = new Date(start).toLocaleDateString('es-AR', { month: 'short', year: '2-digit', timeZone: 'UTC' });
    return text.replace('.', '');
  }
  return formatDay(start).slice(0, 5);
}


/** Nombre de la variable en un detalle o tooltip: una prueba DEMO de glucosa es «simulada», nunca «experimental». */
export function variableName(variable, demo) {
  const spec = VARIABLES[variable];
  return demo && spec.demoLabel ? spec.demoLabel : spec.label;
}

/** Resumen breve de un punto, en palabras: qué es y qué NO es (las pruebas DEMO no son clínicas ni entran en promedios experimentales). */
export function describePoint(point, variable) {
  if (point.bucket) {
    const unit = BLOCK_NAMES[point.bucket.granularity];
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
