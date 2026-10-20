// Gráficos del dashboard analítico (SVG, sin dependencias). Solo dibujan lo que llega del backend: un dato ausente no se grafica como 0 y
// cada gráfico tiene nombre accesible y una tabla de valores para lectores de pantalla. Los datos DEMO (sintéticos) siempre van con su propio
// color y trazo, separados de los experimentales.

import { useEffect, useRef, useState } from 'react';

const TONES = {
  experimental: '#e3101e',
  demo: '#d99a00',
  male: '#3b82f6',
  female: '#f4768a',
  unknown: '#b8bdc9',
  soft: '#f6b6bd',
  info: '#7c3aed',
};

export const toneOf = (name) => TONES[name] ?? TONES.unknown;

const fmt = (value, decimals = 0) => Number(value).toLocaleString('es-AR', { maximumFractionDigits: decimals });

/** «2026-10-05» -> «05/10»; con mes completo -> «10/2026». */
export function shortDate(iso, granularity = 'dia') {
  const [year, month, day] = String(iso).slice(0, 10).split('-');
  return granularity === 'mes' ? `${month}/${year}` : `${day}/${month}`;
}

function DataTable({ caption, rows, columns }) {
  return (
    <div className="sr-only">
      <table>
        <caption>{caption}</caption>
        <thead><tr>{columns.map((column) => <th key={column} scope="col">{column}</th>)}</tr></thead>
        <tbody>{rows.map((row) => <tr key={row[0]}>{row.map((cell, index) => <td key={`${row[0]}-${index}`}>{cell}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

/** Dona con leyenda. items: [{ label, value, tone, hint }]. Las categorías en 0 se listan en la leyenda pero no ocupan arco. */
export function DonutChart({ title, items, centerLabel }) {
  const total = items.reduce((sum, item) => sum + item.value, 0);
  const radius = 64;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  return (
    <div className="an-donut">
      <figure className="an-donut-figure">
        <svg viewBox="0 0 180 180" role="img" aria-label={`${title}: ${total} en total`}>
          <title>{title}</title>
          <circle cx="90" cy="90" r={radius} fill="none" stroke="#f3eaec" strokeWidth="26" />
          {total > 0 && items.filter((item) => item.value > 0).map((item) => {
            const length = (item.value / total) * circumference;
            const circle = (
              <circle key={item.label} cx="90" cy="90" r={radius} fill="none" stroke={toneOf(item.tone)} strokeWidth="26"
                strokeDasharray={`${length} ${circumference - length}`} strokeDashoffset={-offset} transform="rotate(-90 90 90)">
                <title>{`${item.label}: ${item.value}`}</title>
              </circle>
            );
            offset += length;
            return circle;
          })}
          <text x="90" y="88" textAnchor="middle" className="an-donut-total">{fmt(total)}</text>
          <text x="90" y="108" textAnchor="middle" className="an-donut-caption">{centerLabel}</text>
        </svg>
      </figure>
      <ul className="an-legend" aria-label={`Detalle de ${title}`}>
        {items.map((item) => (
          <li key={item.label}>
            <span className="an-dot" style={{ background: toneOf(item.tone) }} aria-hidden="true" />
            <span>{item.label}{item.hint && <small> · {item.hint}</small>}</span>
            <b>{fmt(item.value)}</b>
            <small>{total ? `${fmt((item.value / total) * 100, 1)} %` : '—'}</small>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Columnas verticales. items: [{ label, value, secondary, hint }]; `secondary` es la parte del valor con una condición (se dibuja más oscura). */
export function ColumnChart({ title, items, unit = '', secondaryLabel }) {
  const width = 520;
  const height = 220;
  const pad = { top: 22, right: 8, bottom: 38, left: 30 };
  const max = Math.max(1, ...items.map((item) => item.value));
  const slot = (width - pad.left - pad.right) / Math.max(1, items.length);
  const barWidth = Math.min(46, slot * 0.62);
  const y = (value) => pad.top + (height - pad.top - pad.bottom) * (1 - value / max);
  return (
    <figure className="an-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
        <title>{title}</title>
        <line x1={pad.left} y1={y(0)} x2={width - pad.right} y2={y(0)} className="trend-axis" />
        <text x={pad.left - 6} y={y(max) + 4} textAnchor="end" className="trend-label">{fmt(max)}</text>
        <text x={pad.left - 6} y={y(0) + 4} textAnchor="end" className="trend-label">0</text>
        {items.map((item, index) => {
          const x = pad.left + slot * index + (slot - barWidth) / 2;
          return (
            <g key={item.label}>
              <rect x={x} y={y(item.value)} width={barWidth} height={Math.max(0, y(0) - y(item.value))} rx="4" fill={TONES.soft}>
                <title>{`${item.label}: ${item.value}${unit}${item.hint ? ` (${item.hint})` : ''}`}</title>
              </rect>
              {item.secondary > 0 && (
                <rect x={x} y={y(item.secondary)} width={barWidth} height={Math.max(0, y(0) - y(item.secondary))} rx="4" fill={TONES.experimental} />
              )}
              <text x={x + barWidth / 2} y={y(item.value) - 6} textAnchor="middle" className="trend-label">{fmt(item.value)}</text>
              <text x={x + barWidth / 2} y={height - 18} textAnchor="middle" className="trend-label">{item.label}</text>
            </g>
          );
        })}
      </svg>
      {secondaryLabel && <figcaption className="an-caption"><span className="an-dot" style={{ background: TONES.soft }} /> Pacientes del alcance <span className="an-dot" style={{ background: TONES.experimental }} /> {secondaryLabel}</figcaption>}
      <DataTable caption={title} columns={['Categoría', 'Valor', secondaryLabel ?? '']} rows={items.map((item) => [item.label, item.value, item.secondary ?? ''])} />
    </figure>
  );
}

/** Filas con dos segmentos por categoría (experimental / DEMO) para comparar modos sin mezclar orígenes. */
export function SplitBars({ title, rows }) {
  const max = Math.max(1, ...rows.map((row) => row.experimental + row.demo));
  return (
    <ul className="an-split" aria-label={title}>
      {rows.map((row) => (
        <li key={row.label}>
          <span className="an-split-label">{row.label}</span>
          <span className="an-split-track" role="img" aria-label={`${row.label}: ${row.experimental} experimentales, ${row.demo} DEMO`}>
            <span style={{ width: `${(row.experimental / max) * 100}%`, background: TONES.experimental }} />
            <span style={{ width: `${(row.demo / max) * 100}%`, background: TONES.demo }} className="is-demo" />
          </span>
          <b>{fmt(row.experimental)}{row.showDemo && <small className="an-demo-count"> + {fmt(row.demo)} DEMO</small>}</b>
        </li>
      ))}
    </ul>
  );
}

/**
 * Líneas por período. series: [{ name, tone, dashed, points: [{ x, y, min, max, n }] }]. Una banda suave muestra mínimo–máximo cuando existe.
 * Los puntos sin valor no se grafican. La escala es de UNA sola unidad (no se mezclan variables).
 */
export function SeriesChart({ title, unit, series, granularity = 'dia', decimals = 1, width = 520, height = 220 }) {
  const pad = { top: 16, right: 14, bottom: 30, left: 48 };
  const xs = [...new Set(series.flatMap((item) => item.points.map((point) => point.x)))].sort();
  const values = series.flatMap((item) => item.points.flatMap((point) => [point.y, point.min, point.max])).filter((v) => v !== null && v !== undefined);
  if (xs.length === 0 || values.length === 0) return <p className="field-hint">No hay observaciones con este dato en el período.</p>;
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || Math.max(1, Math.abs(high) * 0.05);
  const yMin = low - span * 0.12;
  const yMax = high + span * 0.12;
  const x = (key) => pad.left + (xs.length === 1 ? (width - pad.left - pad.right) / 2 : (xs.indexOf(key) / (xs.length - 1)) * (width - pad.left - pad.right));
  const y = (value) => pad.top + (height - pad.top - pad.bottom) * (1 - (value - yMin) / (yMax - yMin));
  return (
    <figure className="an-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${title}${unit ? ` (${unit})` : ''}`}>
        <title>{title}</title>
        <line x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} className="trend-axis" />
        <text x={pad.left - 6} y={y(high) + 4} textAnchor="end" className="trend-label">{fmt(high, decimals)}</text>
        <text x={pad.left - 6} y={y(low) + 4} textAnchor="end" className="trend-label">{fmt(low, decimals)}</text>
        {xs.length === 1 ? (
          <text x={(pad.left + width - pad.right) / 2} y={height - 8} textAnchor="middle" className="trend-label">{shortDate(xs[0], granularity)}</text>
        ) : (
          <>
            <text x={pad.left} y={height - 8} className="trend-label">{shortDate(xs[0], granularity)}</text>
            <text x={width - pad.right} y={height - 8} textAnchor="end" className="trend-label">{shortDate(xs.at(-1), granularity)}</text>
          </>
        )}
        {series.map((item) => {
          const withMinMax = item.points.filter((point) => point.min !== null && point.min !== undefined && point.max !== null && point.max !== undefined);
          const band = withMinMax.length > 1
            ? `${withMinMax.map((p) => `${x(p.x)},${y(p.max)}`).join(' ')} ${[...withMinMax].reverse().map((p) => `${x(p.x)},${y(p.min)}`).join(' ')}` : null;
          const line = item.points.filter((point) => point.y !== null && point.y !== undefined);
          return (
            <g key={item.name}>
              {band && <polygon points={band} fill={toneOf(item.tone)} opacity="0.10" />}
              {line.length > 1 && (
                <polyline points={line.map((p) => `${x(p.x)},${y(p.y)}`).join(' ')} fill="none" stroke={toneOf(item.tone)} strokeWidth="2.4"
                  strokeLinejoin="round" strokeDasharray={item.dashed ? '6 5' : undefined} />
              )}
              {line.map((point) => (
                <circle key={point.x} cx={x(point.x)} cy={y(point.y)} r="4" fill={toneOf(item.tone)} stroke="#fff" strokeWidth="1.5">
                  <title>{`${item.name} · ${shortDate(point.x, granularity)}: ${fmt(point.y, decimals)}${unit ? ` ${unit}` : ''}${point.n ? ` (${point.n} obs.)` : ''}`}</title>
                </circle>
              ))}
            </g>
          );
        })}
      </svg>
      <ul className="an-series-legend" aria-label="Series del gráfico">
        {series.map((item) => (
          <li key={item.name}><span className={`an-line${item.dashed ? ' is-dashed' : ''}`} style={{ borderColor: toneOf(item.tone) }} aria-hidden="true" />{item.name}</li>
        ))}
      </ul>
      <DataTable caption={title} columns={['Serie', 'Período', 'Valor', 'Observaciones']}
        rows={series.flatMap((item) => item.points.map((p) => [`${item.name}-${p.x}`, item.name, p.x, p.y === null || p.y === undefined ? 'Sin dato' : fmt(p.y, decimals), p.n ?? '']))} />
    </figure>
  );
}

/**
 * Columnas apiladas. categories: [{ label, parts: [{ label, value, tone }] }]; legend: [{ label, tone }]. Cada parte conserva su propio color
 * (p. ej. experimental / DEMO, o masculino / femenino / sin informar): nunca se funden en una sola barra de un solo color.
 */
export function StackedColumnChart({ title, categories, legend, width = 520, height = 220 }) {
  const pad = { top: 22, right: 8, bottom: 38, left: 30 };
  const totalOf = (category) => category.parts.reduce((sum, part) => sum + part.value, 0);
  const max = Math.max(1, ...categories.map(totalOf));
  const slot = (width - pad.left - pad.right) / Math.max(1, categories.length);
  const barWidth = Math.min(46, slot * 0.62);
  const y = (value) => pad.top + (height - pad.top - pad.bottom) * (1 - value / max);
  return (
    <figure className="an-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
        <title>{title}</title>
        <line x1={pad.left} y1={y(0)} x2={width - pad.right} y2={y(0)} className="trend-axis" />
        <text x={pad.left - 6} y={y(max) + 4} textAnchor="end" className="trend-label">{fmt(max)}</text>
        <text x={pad.left - 6} y={y(0) + 4} textAnchor="end" className="trend-label">0</text>
        {categories.map((category, index) => {
          const x = pad.left + slot * index + (slot - barWidth) / 2;
          let acc = 0;
          return (
            <g key={category.label}>
              {category.parts.filter((part) => part.value > 0).map((part) => {
                const top = y(acc + part.value);
                const rect = (
                  <rect key={part.label} x={x} y={top} width={barWidth} height={Math.max(0, y(acc) - top)} fill={toneOf(part.tone)} className={part.tone === 'demo' ? 'is-demo' : undefined}>
                    <title>{`${category.label} · ${part.label}: ${part.value}`}</title>
                  </rect>
                );
                acc += part.value;
                return rect;
              })}
              {totalOf(category) > 0 && <text x={x + barWidth / 2} y={y(totalOf(category)) - 6} textAnchor="middle" className="trend-label">{fmt(totalOf(category))}</text>}
              <text x={x + barWidth / 2} y={height - 18} textAnchor="middle" className="trend-label">{category.label}</text>
            </g>
          );
        })}
      </svg>
      <figcaption className="an-caption">
        {legend.map((item) => <span key={item.label}><span className="an-dot" style={{ background: toneOf(item.tone) }} /> {item.label}</span>)}
      </figcaption>
      <DataTable caption={title} columns={['Categoría', ...legend.map((item) => item.label)]}
        rows={categories.map((category) => [category.label, ...category.parts.map((part) => part.value)])} />
    </figure>
  );
}

// --- Serie temporal con eje de fecha y hora real ---------------------------------------------------------------------------------------------

const HOUR = 3600 * 1000;
const TIME_STEPS = [HOUR, 3 * HOUR, 6 * HOUR, 12 * HOUR, 24 * HOUR, 2 * 24 * HOUR, 3 * 24 * HOUR, 7 * 24 * HOUR, 14 * 24 * HOUR, 30 * 24 * HOUR];

const dateText = (date) => date.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit' });
const timeText = (date) => date.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hour12: false });

/** Marcas «redondas» del eje vertical dentro de [low, high]: ni se inventa un cero ni se fuerza un rango clínico. */
export function niceTicks(low, high, target = 5) {
  const span = high - low || Math.max(1, Math.abs(high) * 0.1);
  const rough = span / Math.max(1, target - 1);
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((factor) => factor * magnitude).find((candidate) => candidate >= rough) ?? 10 * magnitude;
  const start = Math.floor(low / step) * step;
  const ticks = [];
  for (let value = start; value <= high + step; value += step) ticks.push(Number(value.toFixed(6)));
  return ticks.filter((value, index, all) => value >= low - step && (index === 0 || all[index - 1] <= high));
}

function useWidth(fallback = 560) {
  const ref = useRef(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const node = ref.current;
    if (!node || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(260, Math.round(entry.contentRect.width))));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

/**
 * Serie temporal. points: [{ t: Date, y, n, label? }] con t en hora real.
 *   kind = 'medicion': cada punto ES una medición (círculo). No se unen con líneas: son de pacientes distintos y una línea sugeriría la evolución de una persona.
 *   kind = 'dia':      cada punto es el PROMEDIO de un día con `n` observaciones (cuadrado, con su cantidad): nunca se confunde con una medición.
 * `origin` rotula el tooltip («DEMO — dato sintético» o «Experimental — estimación no clínica»). Los valores ausentes no se grafican.
 * La escala vertical sale de los propios datos (sin cero forzado) y la unidad va en el eje. Cada punto es enfocable y tiene su tooltip.
 */
export function TimeSeriesChart({ title, unit, points, kind = 'medicion', tone = 'demo', origin, decimals = 1, height = 300 }) {
  const [ref, width] = useWidth();
  const [active, setActive] = useState(null);
  const data = points.filter((point) => point.y !== null && point.y !== undefined && point.t instanceof Date && !Number.isNaN(point.t.getTime()))
    .sort((a, b) => a.t - b.t);
  if (data.length === 0) return <p className="field-hint">No hay observaciones con este dato en el período.</p>;

  const pad = { top: 16, right: 16, bottom: 44, left: 62 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const color = toneOf(tone);
  const values = data.map((point) => point.y);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const margin = (high - low || Math.max(1, Math.abs(high) * 0.1)) * 0.12;
  const yMin = low - margin;
  const yMax = high + margin;
  const yTicks = niceTicks(yMin, yMax).filter((tick) => tick >= yMin && tick <= yMax);
  let tMin = data[0].t.getTime();
  let tMax = data.at(-1).t.getTime();
  if (tMin === tMax) { tMin -= 12 * HOUR; tMax += 12 * HOUR; } else { const gap = (tMax - tMin) * 0.04; tMin -= gap; tMax += gap; }
  const x = (time) => pad.left + ((time - tMin) / (tMax - tMin)) * plotW;
  const y = (value) => pad.top + plotH * (1 - (value - yMin) / (yMax - yMin));

  const wanted = Math.max(3, Math.floor(plotW / (kind === "dia" || (tMax - tMin) > 2 * 24 * HOUR ? 80 : 92)));
  const step = TIME_STEPS.find((candidate) => (tMax - tMin) / candidate <= wanted) ?? TIME_STEPS.at(-1);
  const xTicks = [];
  const first = new Date(tMin);
  const offset = first.getTimezoneOffset() * 60000;
  for (let time = Math.ceil((tMin - offset) / step) * step + offset; time <= tMax; time += step) xTicks.push(new Date(time));
  const tickLabel = (date) => (step < 24 * HOUR ? `${dateText(date)} ${timeText(date)}` : dateText(date));

  const describe = (point) => {
    const when = kind === 'dia' ? `Día ${point.t.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' })}` : `${dateText(point.t)}/${point.t.getFullYear()} ${timeText(point.t)}`;
    return {
      when,
      value: `${fmt(point.y, decimals)}${unit ? ` ${unit}` : ''}`,
      kindText: kind === 'dia' ? `Promedio diario de ${point.n} ${point.n === 1 ? 'observación' : 'observaciones'}` : 'Medición individual',
      origin,
    };
  };
  const hovered = active !== null ? data[active] : null;
  const info = hovered ? describe(hovered) : null;
  const left = hovered ? Math.min(Math.max(x(hovered.t.getTime()), 90), width - 90) : 0;

  return (
    <figure className="an-chart hl-chart" ref={ref}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${title}${unit ? ` (${unit})` : ''}: ${data.length} ${kind === 'dia' ? 'promedios diarios' : 'mediciones'}`}>
        <title>{title}</title>
        {yTicks.map((tick) => (
          <g key={tick}>
            <line x1={pad.left} y1={y(tick)} x2={width - pad.right} y2={y(tick)} className="hl-grid" />
            <text x={pad.left - 8} y={y(tick) + 4} textAnchor="end" className="hl-tick">{fmt(tick, decimals)}</text>
          </g>
        ))}
        <text transform={`translate(14 ${pad.top + plotH / 2}) rotate(-90)`} textAnchor="middle" className="hl-axis-title">{unit}</text>
        <line x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} className="trend-axis" />
        {xTicks.map((date) => (
          <g key={date.getTime()}>
            <line x1={x(date.getTime())} y1={height - pad.bottom} x2={x(date.getTime())} y2={height - pad.bottom + 5} className="trend-axis" />
            <text x={x(date.getTime())} y={height - pad.bottom + 20} textAnchor="middle" className="hl-tick">{tickLabel(date)}</text>
          </g>
        ))}
        <text x={pad.left + plotW / 2} y={height - 4} textAnchor="middle" className="hl-axis-title">{kind === 'dia' ? 'Fecha (promedio de cada día)' : 'Fecha y hora de la medición'}</text>
        {data.map((point, index) => {
          const cx = x(point.t.getTime());
          const cy = y(point.y);
          const common = {
            tabIndex: 0, role: 'img', fill: color, stroke: '#fff', strokeWidth: 2, className: `hl-point${active === index ? ' is-active' : ''}`,
            'aria-label': `${describe(point).when}: ${describe(point).value}. ${describe(point).kindText}. ${origin ?? ''}`,
            onMouseEnter: () => setActive(index), onMouseLeave: () => setActive(null), onFocus: () => setActive(index), onBlur: () => setActive(null),
          };
          return kind === 'dia'
            ? <rect key={`${point.t.getTime()}-${index}`} x={cx - 6} y={cy - 6} width="12" height="12" rx="2" {...common} />
            : <circle key={`${point.t.getTime()}-${index}`} cx={cx} cy={cy} r="5.5" {...common} />;
        })}
      </svg>
      {info && (
        <div className="hl-tooltip" role="status" style={{ left }}>
          <b>{info.value}</b>
          <span>{info.when}</span>
          <span>{info.kindText}</span>
          {info.origin && <span className="hl-tooltip-origin">{info.origin}</span>}
        </div>
      )}
      <DataTable caption={title} columns={['Fecha', 'Valor', 'Observaciones']}
        rows={data.map((point, index) => [`${point.t.getTime()}-${index}`, describe(point).when, describe(point).value, kind === 'dia' ? point.n : 1])} />
    </figure>
  );
}
