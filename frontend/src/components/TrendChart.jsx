// Gráfico de línea simple en SVG (sin dependencias). Recibe solo los puntos ya autorizados por el backend.
// Accesible: el SVG tiene título y la tabla de valores queda disponible para lectores de pantalla.

const WIDTH = 600;
const HEIGHT = 180;
const PADDING = { top: 16, right: 16, bottom: 28, left: 44 };

export function TrendChart({ title, points, unit }) {
  const values = points.filter((point) => point.value !== null && point.value !== undefined);
  if (values.length === 0) return <p className="field-hint">Sin datos para graficar en este período.</p>;

  const min = Math.min(...values.map((point) => point.value));
  const max = Math.max(...values.map((point) => point.value));
  const span = max - min || 1;
  const innerWidth = WIDTH - PADDING.left - PADDING.right;
  const innerHeight = HEIGHT - PADDING.top - PADDING.bottom;
  const x = (index) => PADDING.left + (values.length === 1 ? innerWidth / 2 : (index / (values.length - 1)) * innerWidth);
  const y = (value) => PADDING.top + innerHeight - ((value - min) / span) * innerHeight;
  const path = values.map((point, index) => `${index === 0 ? 'M' : 'L'}${x(index).toFixed(1)},${y(point.value).toFixed(1)}`).join(' ');

  return (
    <figure className="trend-chart">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`${title}: ${values.length} puntos`}>
        <title>{title}</title>
        <line x1={PADDING.left} y1={PADDING.top + innerHeight} x2={WIDTH - PADDING.right} y2={PADDING.top + innerHeight}
          className="trend-axis" />
        <text x={PADDING.left - 8} y={y(max) + 4} textAnchor="end" className="trend-label">{max.toLocaleString('es-AR')}</text>
        <text x={PADDING.left - 8} y={y(min) + 4} textAnchor="end" className="trend-label">{min.toLocaleString('es-AR')}</text>
        <path d={path} className="trend-line" />
        {values.map((point, index) => (
          <circle key={point.label} cx={x(index)} cy={y(point.value)} r={4} className="trend-dot">
            <title>{`${point.label}: ${point.value.toLocaleString('es-AR')} ${unit}`}</title>
          </circle>
        ))}
        <text x={PADDING.left} y={HEIGHT - 8} className="trend-label">{values[0].label}</text>
        <text x={WIDTH - PADDING.right} y={HEIGHT - 8} textAnchor="end" className="trend-label">{values.at(-1).label}</text>
      </svg>
      <figcaption>{title}</figcaption>
    </figure>
  );
}
