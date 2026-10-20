// Gráfico de línea de una serie temporal en tiempo real (SVG, sin dependencias). Recibe puntos REALES ya recibidos del dispositivo:
// no genera, suaviza ni interpola datos. Una lectura inválida o faltante llega con `value: null` y deja un corte en la línea.
// Escala responsive: ocupa el ancho disponible (escritorio y móvil) manteniendo la proporción.

const WIDTH = 480;
const HEIGHT = 150;
const PADDING = { top: 12, right: 12, bottom: 22, left: 40 };

function format(value, decimals) {
  return Number(value).toLocaleString('es-AR', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

/** points: [{ key, value: number | null }] en orden cronológico. Se muestran como máximo las últimas `capacity`. */
/** `compact`: tendencia mínima dentro de una tarjeta (sin rótulos de ejes); el nombre accesible conserva primer/último valor. */
export function LiveChart({ title, unit, points, capacity = 30, decimals = 0, emptyText = 'Sin señal', compact = false }) {
  const window = points.slice(-capacity);
  const valid = window.filter((point) => point.value !== null && point.value !== undefined);
  if (valid.length === 0) {
    return <p className="live-chart-empty" role="status" aria-label={`${title}: ${emptyText}`}>{emptyText}</p>;
  }

  const low = Math.min(...valid.map((point) => point.value));
  const high = Math.max(...valid.map((point) => point.value));
  const span = high - low || Math.max(1, Math.abs(high) * 0.02); // serie plana: escala mínima, sin inventar variación
  const yMin = low - (high === low ? span : span * 0.1);
  const yMax = high + (high === low ? span : span * 0.1);
  const innerWidth = WIDTH - PADDING.left - PADDING.right;
  const innerHeight = HEIGHT - PADDING.top - PADDING.bottom;
  const x = (index) => PADDING.left + (capacity <= 1 ? innerWidth / 2 : (index / (capacity - 1)) * innerWidth);
  const y = (value) => PADDING.top + innerHeight - ((value - yMin) / (yMax - yMin)) * innerHeight;

  const offset = Math.max(0, capacity - window.length); // la lectura más nueva queda siempre en el borde derecho
  // Segmentos continuos: una lectura inválida corta la línea (no se une con la siguiente).
  const segments = [];
  let current = [];
  window.forEach((point, index) => {
    if (point.value === null || point.value === undefined) {
      if (current.length) segments.push(current);
      current = [];
    } else {
      current.push([x(index + offset), y(point.value)]);
    }
  });
  if (current.length) segments.push(current);
  const lastIndex = window.map((point) => point.value !== null && point.value !== undefined).lastIndexOf(true);
  const last = window[lastIndex];

  return (
    <figure className={`live-chart${compact ? ' is-compact' : ''}`}>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`${title}: ${valid.length} lecturas válidas, última ${format(last.value, decimals)} ${unit}`}>
        <title>{title}</title>
        <line x1={PADDING.left} y1={PADDING.top} x2={WIDTH - PADDING.right} y2={PADDING.top} className="trend-axis" />
        <line x1={PADDING.left} y1={PADDING.top + innerHeight} x2={WIDTH - PADDING.right} y2={PADDING.top + innerHeight} className="trend-axis" />
        {!compact && <text x={PADDING.left - 6} y={PADDING.top + 4} textAnchor="end" className="trend-label">{format(yMax, decimals)}</text>}
        {!compact && <text x={PADDING.left - 6} y={PADDING.top + innerHeight + 4} textAnchor="end" className="trend-label">{format(yMin, decimals)}</text>}
        {segments.map((segment) => (
          segment.length === 1
            ? <circle key={`s${segment[0][0]}`} cx={segment[0][0]} cy={segment[0][1]} r={3} className="trend-dot" />
            : <polyline key={`p${segment[0][0]}`} points={segment.map(([px, py]) => `${px.toFixed(1)},${py.toFixed(1)}`).join(' ')} className="trend-line" />
        ))}
        <circle cx={x(lastIndex + offset)} cy={y(last.value)} r={4.5} className="trend-dot is-current" />
        {!compact && <text x={PADDING.left} y={HEIGHT - 6} className="trend-label">{`últimas ${capacity} lecturas`}</text>}
        {!compact && <text x={WIDTH - PADDING.right} y={HEIGHT - 6} textAnchor="end" className="trend-label">ahora</text>}
      </svg>
    </figure>
  );
}
