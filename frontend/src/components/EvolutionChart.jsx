// Gráfico histórico de UNA variable: cada medición guardada es un punto (observación discreta, no un monitoreo continuo). Escala y unidad
// propias de la variable. Interactivo: al pasar el cursor, enfocar con el teclado o tocar un punto aparece su fecha, hora, valor, unidad,
// modo y origen; al elegirlo (clic/Enter) se avisa con `onSelect` para abrir su detalle. Los puntos DEMO se dibujan con otro marcador y
// otro trazo. No interpola: entre dos mediciones solo hay una línea guía; si no hay datos no se dibuja nada.

import { useState } from 'react';

import { MODES } from '../pages/Account/groups/groupFormat.js';
import { ChartTooltip } from './ChartTooltip.jsx';
import { useElementWidth } from './useElementWidth.js';
import { bucketLabel, formatClock, formatDay, formatValue, timeTicks } from '../pages/Account/measurements/evolutionModel.js';

const PAD_WIDE = { top: 18, right: 22, bottom: 40, left: 62 };
const PAD_NARROW = { top: 18, right: 14, bottom: 40, left: 52 };

export function EvolutionChart({ title, demoTitle, series, unit, decimals = 0, color, selectedKey = null, onSelect, domain, granularity = 'MEDICION' }) {
  const [hover, setHover] = useState(null);
  const [setBox, WIDTH] = useElementWidth(); // se dibuja con el ancho real del contenedor (sin escalar un dibujo fijo)
  if (series.length === 0) return null;
  const HEIGHT = Math.round(Math.min(340, Math.max(240, WIDTH * 0.32))); // ancha pero no innecesariamente alta
  const PAD = WIDTH < 480 ? PAD_NARROW : PAD_WIDE;
  const innerW = WIDTH - PAD.left - PAD.right;
  const innerH = HEIGHT - PAD.top - PAD.bottom;

  const times = series.map((point) => point.t);
  const t0 = domain?.[0] ?? Math.min(...times);
  const rawT1 = domain?.[1] ?? Math.max(...times);
  const t1 = rawT1 > t0 ? rawT1 : t0 + 3_600_000; // un solo punto: ventana mínima de una hora
  const values = series.map((point) => point.value);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const margin = (high - low || Math.max(Math.abs(high) * 0.05, 1)) * 0.15;
  const yMin = low - margin;
  const yMax = high + margin;
  const x = (t) => PAD.left + Math.min(1, Math.max(0, (t - t0) / (t1 - t0))) * innerW; // un promedio queda dentro del eje
  const y = (value) => PAD.top + innerH - ((value - yMin) / (yMax - yMin)) * innerH;
  const { ticks: xTicks, step: xStep } = timeTicks(t0, t1);
  const hourly = xStep < 86_400_000;
  const yTicks = Array.from({ length: 4 }, (_, index) => yMin + ((yMax - yMin) * index) / 3);

  const line = (points) => points.map((point) => `${x(point.t).toFixed(1)},${y(point.value).toFixed(1)}`).join(' ');
  const experimental = series.filter((point) => !point.demo);
  const demo = series.filter((point) => point.demo);
  const shown = hover ? series.find((point) => point.key === hover) : null;
  const shownDecimals = (point) => (point.count > 1 ? Math.max(decimals, 1) : decimals); // un promedio puede tener decimales

  function activate(point) {
    onSelect?.(point);
  }

  return (
    <figure className="evolution-chart" ref={setBox}>
      <svg width={WIDTH} height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="group" aria-label={`${title}: ${series.length} ${series.length === 1 ? 'punto' : 'puntos'}`}>
        <title>{title}</title>
        {yTicks.map((tick) => (
          <g key={`y${tick}`}>
            <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(tick)} y2={y(tick)} className="evo-grid" />
            <text x={PAD.left - 8} y={y(tick) + 4} textAnchor="end" className="trend-label">{formatValue(tick, decimals)}</text>
          </g>
        ))}
        <text x={14} y={PAD.top + innerH / 2} className="trend-label" transform={`rotate(-90 14 ${PAD.top + innerH / 2})`} textAnchor="middle">{unit || 'índice'}</text>
        {xTicks.map((tick) => (
          <text key={`x${tick}`} x={x(tick)} y={HEIGHT - 16} textAnchor="middle" className="trend-label">
            {hourly ? (tick % 86_400_000 === 0 ? formatDay(tick).slice(0, 5) : formatClock(tick)) : formatDay(tick).slice(0, 5)}
          </text>
        ))}
        <line x1={PAD.left} x2={WIDTH - PAD.right} y1={PAD.top + innerH} y2={PAD.top + innerH} className="trend-axis" />
        {experimental.length > 1 && <polyline points={line(experimental)} className="evo-line" style={{ stroke: color }} />}
        {demo.length > 1 && <polyline points={line(demo)} className="evo-line is-demo" />}
        {series.map((point) => {
          const selected = point.key === selectedKey;
          const label = `${formatDay(point.bucket ? point.bucket.from : point.t)} ${point.bucket ? bucketLabel(point) : formatClock(point.t)}: ${formatValue(point.value, shownDecimals(point))} ${unit}${point.demo ? ' (DEMO)' : ''}`;
          return (
            <g key={point.key} tabIndex={0} role="button" aria-label={label} aria-pressed={selected} className="evo-point"
              onMouseEnter={() => setHover(point.key)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(point.key)}
              onBlur={() => setHover(null)} onClick={() => activate(point)}
              onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(point); } }}>
              <circle cx={x(point.t)} cy={y(point.value)} r={14} className="evo-hit" />
              {point.demo
                ? <rect x={x(point.t) - 5} y={y(point.value) - 5} width={10} height={10} transform={`rotate(45 ${x(point.t)} ${y(point.value)})`} className={`evo-demo${selected ? ' is-selected' : ''}`} />
                : <circle cx={x(point.t)} cy={y(point.value)} r={selected ? 7 : 5} style={{ fill: color }} className={`evo-dot${selected ? ' is-selected' : ''}`} />}
              {point.count > 1 && <text x={x(point.t)} y={y(point.value) - 11} textAnchor="middle" className="evo-count">{point.count}</text>}
            </g>
          );
        })}
      </svg>
      {shown && (
        <ChartTooltip left={(x(shown.t) / WIDTH) * 100} top={(y(shown.value) / HEIGHT) * 100}
          variable={shown.demo && demoTitle ? demoTitle : title}
          value={formatValue(shown.value, shownDecimals(shown))} unit={unit}
          date={formatDay(shown.bucket ? shown.bucket.from : shown.t)} time={shown.bucket ? (shown.bucket.granularity === 'HORA' ? bucketLabel(shown) : undefined) : formatClock(shown.t)} demo={shown.demo}
          origin={shown.demo ? 'DEMO (prueba)' : 'Experimental'}
          note={shown.bucket ? `Promedio de ${shown.count} ${shown.count === 1 ? 'medición' : 'mediciones'}${shown.bucket.granularity === 'DIA' ? ' del día' : ' de esa hora'}` : (MODES[shown.mode] ?? undefined)} />
      )}
      <figcaption>
        {experimental.length > 0 && <span className="evo-legend"><i className="evo-swatch" style={{ background: color }} /> Medición experimental</span>}
        {demo.length > 0 && <span className="evo-legend"><i className="evo-swatch is-demo" /> Prueba DEMO (simulada)</span>}
        <span className="field-hint">
          {granularity === 'MEDICION' ? 'Cada punto es una medición guardada; la línea solo las une en orden cronológico.'
            : `Cada punto es el promedio de las mediciones de un${granularity === 'HORA' ? 'a hora' : ' día'}; el número indica cuántas se promediaron.`}
          {' '}Eje: {formatDay(t0)} {formatClock(t0)} a {formatDay(t1)} {formatClock(t1)}.
        </span>
      </figcaption>
    </figure>
  );
}
