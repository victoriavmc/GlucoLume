// Gráfico de oximetría experimental: SpO₂ (%) y frecuencia cardíaca (lpm) en un mismo gráfico, cada una con su escala (izquierda la SpO₂,
// derecha la frecuencia). Cada punto es una medición guardada (o un promedio, si se agrupa). Sin semáforo ni glucosa: el semáforo es solo
// de glucosa. Interactivo como EvolutionChart: al pasar el cursor o elegir un punto (clic / Enter) se avisa con `onSelect(variable, point)`.

import { useState } from 'react';

import { ChartTooltip } from './ChartTooltip.jsx';
import { useElementWidth } from './useElementWidth.js';
import { MODES } from '../pages/Account/groups/groupFormat.js';
import {
  BLOCK_NAMES, DAY, HOUR, VARIABLES, formatClock, formatDay, formatValue, pointWhen, timeTicks,
} from '../pages/Account/measurements/evolutionModel.js';

const SPO2 = 'spo2';
const FC = 'frecuenciaCardiaca';
const PAD_WIDE = { top: 18, right: 60, bottom: 40, left: 60 };
const PAD_NARROW = { top: 18, right: 46, bottom: 40, left: 46 };
const GROUP_PHRASES = { HORA: 'una hora', DIA: 'un día', SEMANA: 'una semana', MES: 'un mes' };

/** Escala con margen para una serie (sin valores, no hay escala). */
function scaleOf(series) {
  if (series.length === 0) return null;
  const values = series.map((point) => point.value);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const margin = (high - low || Math.max(Math.abs(high) * 0.05, 1)) * 0.15;
  return { min: low - margin, max: high + margin };
}

export function OximetryChart({ spo2Series, fcSeries, domain, granularity = 'MEDICION', selected = null, onSelect }) {
  const [hover, setHover] = useState(null); // { variable, key }
  const [setBox, WIDTH] = useElementWidth();
  const all = [...spo2Series, ...fcSeries];
  if (all.length === 0) return null;
  const HEIGHT = Math.round(Math.min(340, Math.max(240, WIDTH * 0.32)));
  const PAD = WIDTH < 480 ? PAD_NARROW : PAD_WIDE;
  const innerW = WIDTH - PAD.left - PAD.right;
  const innerH = HEIGHT - PAD.top - PAD.bottom;

  const times = all.map((point) => point.t);
  const t0 = domain?.[0] ?? Math.min(...times);
  const rawT1 = domain?.[1] ?? Math.max(...times);
  const t1 = rawT1 > t0 ? rawT1 : t0 + HOUR;
  const scales = { [SPO2]: scaleOf(spo2Series), [FC]: scaleOf(fcSeries) };
  const x = (t) => PAD.left + Math.min(1, Math.max(0, (t - t0) / (t1 - t0))) * innerW;
  // Cada variable se dibuja con su propia escala; los 4 niveles de la grilla son los mismos para ambos ejes.
  const y = (variable, value) => {
    const scale = scales[variable] ?? { min: 0, max: 1 };
    return PAD.top + innerH - ((value - scale.min) / (scale.max - scale.min || 1)) * innerH;
  };
  const gridFractions = [0, 1 / 3, 2 / 3, 1];
  const tickAt = (variable, fraction) => {
    const scale = scales[variable];
    return scale ? scale.min + (scale.max - scale.min) * fraction : null;
  };
  const { ticks: xTicks, step: xStep } = timeTicks(t0, t1);
  const hourly = xStep < DAY;
  const experimentalOf = (series) => series.filter((point) => !point.demo);
  const shownDecimals = (variable, point) => (point.count > 1 ? Math.max(VARIABLES[variable].decimals, 1) : VARIABLES[variable].decimals); // un promedio puede tener decimales
  const label = (variable, point) => `${formatValue(point.value, shownDecimals(variable, point))} ${VARIABLES[variable].unit}`;
  const anyDemo = all.some((point) => point.demo);
  const measuredCount = new Set(all.map((point) => point.key)).size;

  function dots(variable, series) {
    const spec = VARIABLES[variable];
    return series.map((point) => {
      const isSelected = selected?.variable === variable && selected?.point.key === point.key;
      const when = pointWhen(point);
      const text = `${when.date}${when.time ? ` ${when.time}` : ''}: ${label(variable, point)}${point.demo ? ' (DEMO)' : ''}`;
      const cx = x(point.t);
      const cy = y(variable, point.value);
      return (
        <g key={`${variable}-${point.key}`} tabIndex={0} role="button" aria-label={text} aria-pressed={isSelected} className="evo-point"
          onMouseEnter={() => setHover({ variable, key: point.key })} onMouseLeave={() => setHover(null)}
          onFocus={() => setHover({ variable, key: point.key })} onBlur={() => setHover(null)} onClick={() => onSelect?.(variable, point)}
          onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect?.(variable, point); } }}>
          <circle cx={cx} cy={cy} r={14} className="evo-hit" />
          {point.demo
            ? <rect x={cx - 5} y={cy - 5} width={10} height={10} transform={`rotate(45 ${cx} ${cy})`} className={`evo-demo${isSelected ? ' is-selected' : ''}`} />
            : <circle cx={cx} cy={cy} r={isSelected ? 7 : 5} style={{ fill: spec.color }} className={`evo-dot${isSelected ? ' is-selected' : ''}`} />}
          {point.count > 1 && <text x={cx} y={cy - 11} textAnchor="middle" className="evo-count">{point.count}</text>}
        </g>
      );
    });
  }

  const shown = hover ? (hover.variable === SPO2 ? spo2Series : fcSeries).find((point) => point.key === hover.key) : null;
  const shownVariable = hover?.variable;

  return (
    <figure className="evolution-chart" ref={setBox}>
      <svg width={WIDTH} height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="group"
        aria-label={`Oximetría experimental: SpO₂ y frecuencia cardíaca: ${measuredCount} ${measuredCount === 1 ? 'punto' : 'puntos'}`}>
        <title>Oximetría experimental: SpO₂ y frecuencia cardíaca</title>
        {gridFractions.map((fraction) => {
          const row = PAD.top + innerH - fraction * innerH;
          const left = tickAt(SPO2, fraction);
          const right = tickAt(FC, fraction);
          return (
            <g key={`grid${fraction}`}>
              <line x1={PAD.left} x2={WIDTH - PAD.right} y1={row} y2={row} className="evo-grid" />
              {left !== null && <text x={PAD.left - 8} y={row + 4} textAnchor="end" className="trend-label">{formatValue(left, 0)}</text>}
              {right !== null && <text x={WIDTH - PAD.right + 8} y={row + 4} textAnchor="start" className="trend-label">{formatValue(right, 0)}</text>}
            </g>
          );
        })}
        {scales[SPO2] && <text x={14} y={PAD.top + innerH / 2} className="trend-label" transform={`rotate(-90 14 ${PAD.top + innerH / 2})`} textAnchor="middle">SpO₂ (%)</text>}
        {scales[FC] && <text x={WIDTH - 10} y={PAD.top + innerH / 2} className="trend-label" transform={`rotate(90 ${WIDTH - 10} ${PAD.top + innerH / 2})`} textAnchor="middle">lpm</text>}
        {xTicks.map((tick) => (
          <text key={`x${tick}`} x={x(tick)} y={HEIGHT - 16} textAnchor="middle" className="trend-label">
            {hourly ? (tick % DAY === 0 ? formatDay(tick).slice(0, 5) : formatClock(tick)) : formatDay(tick).slice(0, 5)}
          </text>
        ))}
        <line x1={PAD.left} x2={WIDTH - PAD.right} y1={PAD.top + innerH} y2={PAD.top + innerH} className="trend-axis" />
        {scales[SPO2] && experimentalOf(spo2Series).length > 1 && (
          <polyline points={experimentalOf(spo2Series).map((p) => `${x(p.t).toFixed(1)},${y(SPO2, p.value).toFixed(1)}`).join(' ')}
            className="evo-line" style={{ stroke: VARIABLES[SPO2].color }} />
        )}
        {scales[FC] && experimentalOf(fcSeries).length > 1 && (
          <polyline points={experimentalOf(fcSeries).map((p) => `${x(p.t).toFixed(1)},${y(FC, p.value).toFixed(1)}`).join(' ')}
            className="evo-line is-dashed" style={{ stroke: VARIABLES[FC].color }} />
        )}
        {dots(SPO2, spo2Series)}
        {dots(FC, fcSeries)}
      </svg>
      {shown && (
        <ChartTooltip left={(x(shown.t) / WIDTH) * 100} top={(y(shownVariable, shown.value) / HEIGHT) * 100}
          variable={VARIABLES[shownVariable].label} value={formatValue(shown.value, shownDecimals(shownVariable, shown))} unit={VARIABLES[shownVariable].unit}
          date={pointWhen(shown).date} time={pointWhen(shown).time} demo={shown.demo}
          origin={shown.demo ? 'DEMO (prueba)' : 'Experimental'}
          note={shown.bucket ? `Promedio de ${shown.count} ${shown.count === 1 ? 'medición' : 'mediciones'} de ${BLOCK_NAMES[shown.bucket.granularity]}` : (MODES[shown.mode] ?? undefined)} />
      )}
      <figcaption>
        {scales[SPO2] && <span className="evo-legend"><i className="evo-swatch" style={{ background: VARIABLES[SPO2].color }} /> Saturación SpO₂ (%)</span>}
        {scales[FC] && <span className="evo-legend"><i className="evo-swatch is-dashed" style={{ background: VARIABLES[FC].color }} /> Frecuencia cardíaca (lpm)</span>}
        {anyDemo && <span className="evo-legend"><i className="evo-swatch is-demo" /> Prueba DEMO (simulada)</span>}
        <span className="field-hint">
          {granularity === 'MEDICION' ? 'Cada punto es una medición guardada; la línea solo las une en orden cronológico.'
            : `Cada punto es el promedio de las mediciones de ${GROUP_PHRASES[granularity]}; el número indica cuántas se promediaron.`}
          {' '}Eje: {formatDay(t0)} {formatClock(t0)} a {formatDay(t1)} {formatClock(t1)}.
        </span>
      </figcaption>
    </figure>
  );
}
