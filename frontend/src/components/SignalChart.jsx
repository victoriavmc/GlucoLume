// Señal en tiempo real de un canal (RED o IR) en SVG. Muestra solo las muestras que llegan del Arduino; autoescala al
// rango de lo que se ve, porque los valores crudos (decenas de miles) varían muy poco entre latidos.

const WIDTH = 600;
const HEIGHT = 120;

export function SignalChart({ title, samples, color }) {
  if (samples.length < 2) return <p className="field-hint">{title}: esperando muestras…</p>;
  const min = Math.min(...samples);
  const max = Math.max(...samples);
  const span = max - min || 1;
  const points = samples.map((value, index) => {
    const x = (index / (samples.length - 1)) * WIDTH;
    const y = HEIGHT - 6 - ((value - min) / span) * (HEIGHT - 12);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <figure className="signal-chart">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`${title}: ${samples.length} muestras recientes`} preserveAspectRatio="none">
        <title>{title}</title>
        <polyline points={points.join(' ')} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
      <figcaption>{title} · último valor {samples.at(-1).toLocaleString('es-AR')}</figcaption>
    </figure>
  );
}
