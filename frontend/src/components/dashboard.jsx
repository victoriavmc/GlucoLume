// Piezas comunes de los dashboards: filtro de período, tarjetas de indicadores y bloque de estadísticas por variable.
// Sin datos nunca se muestra un cero: se muestra «Sin datos disponibles».

import { CalendarDays } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { TrendChart } from './TrendChart.jsx';
import { formatDate, formatDateTime, formatNumber } from '../pages/Account/groups/groupFormat.js';

export const NO_DATA = 'Sin datos disponibles';

/** Períodos del backend: 7, 30 o 90 días, o un rango de fechas. */
export function PeriodFilter({ value, onChange, idPrefix = 'periodo', days = [7, 30, 90], compact = false }) {
  const [customMode, setCustomMode] = useState(Boolean(value.desde || value.hasta));
  const custom = customMode || Boolean(value.desde || value.hasta);
  const [draft, setDraft] = useState({ desde: value.desde ?? '', hasta: value.hasta ?? '' });

  function choose(event) {
    const selected = event.target.value;
    if (selected === 'rango') {
      setCustomMode(true);
      onChange({ desde: draft.desde || undefined, hasta: draft.hasta || undefined, dias: 30 });
    } else {
      setCustomMode(false);
      onChange({ dias: Number(selected) });
    }
  }

  function dates(field) {
    return (event) => {
      const next = { ...draft, [field]: event.target.value };
      setDraft(next);
      onChange({ desde: next.desde || undefined, hasta: next.hasta || undefined, dias: 30 });
    };
  }

  const invalid = custom && draft.desde && draft.hasta && draft.hasta < draft.desde;
  return (
    <form className={`form-grid measurement-filters${compact ? ' is-compact' : ''}`} aria-label="Filtro de período" onSubmit={(event) => event.preventDefault()}>
      <div className="field">
        <label className="field-label" htmlFor={`${idPrefix}-select`}>Período</label>
        <div className="period-select">
          {compact && <CalendarDays size={18} aria-hidden="true" />}
          <select id={`${idPrefix}-select`} className="field-input field-select" value={custom ? 'rango' : value.dias} onChange={choose}>
            {days.map((count) => <option key={count} value={count}>{count === 1 ? 'Últimas 24 horas' : `Últimos ${count} días`}</option>)}
            <option value="rango">Período personalizado</option>
          </select>
        </div>
      </div>
      {custom && (
        <>
          <div className="field">
            <label className="field-label" htmlFor={`${idPrefix}-desde`}>Desde</label>
            <input id={`${idPrefix}-desde`} type="date" className="field-input" value={draft.desde} onChange={dates('desde')} />
          </div>
          <div className="field">
            <label className="field-label" htmlFor={`${idPrefix}-hasta`}>Hasta</label>
            <input id={`${idPrefix}-hasta`} type="date" className="field-input" value={draft.hasta} onChange={dates('hasta')} />
          </div>
        </>
      )}
      {invalid && <p className="field-error" role="alert">La fecha final no puede ser anterior a la inicial.</p>}
    </form>
  );
}

export function periodLabel(period) {
  if (!period) return '';
  if (period.desde || period.hasta) return `${period.desde ? formatDate(period.desde) : 'inicio'} a ${period.hasta ? formatDate(period.hasta) : 'hoy'}`;
  return period.dias === 1 ? 'últimas 24 horas' : `últimos ${period.dias} días`;
}

/** Tarjeta de indicador: valor o «Sin datos disponibles». Con `icon` se presenta en formato compacto (ícono + texto). */
export function Kpi({ label, value, hint, unit, icon: Icon, tone, to }) {
  const empty = value === null || value === undefined;
  const text = (
    <>
      <small>{label}</small>
      <b className={empty ? 'is-empty' : undefined}>{empty ? NO_DATA : typeof value === 'number' ? formatNumber(value, unit) : value}</b>
      {hint && <span className="field-hint">{hint}</span>}
    </>
  );
  if (!Icon) return <li className="summary-card">{text}</li>;
  // Ícono y título comparten la fila superior (el título ocupa todo el ancho restante); valor y descripción debajo, a todo el ancho.
  const content = (
    <div className="kpi-text">
      <span className="kpi-head">
        <span className="panel-icon" aria-hidden="true"><Icon size={20} /></span>
        <small>{label}</small>
      </span>
      <b className={empty ? 'is-empty' : undefined}>{empty ? NO_DATA : typeof value === 'number' ? formatNumber(value, unit) : value}</b>
      {hint && <span className="field-hint">{hint}</span>}
    </div>
  );
  // Con destino, toda la tarjeta es un enlace.
  return (
    <li className={`summary-card kpi-card${tone ? ` is-${tone}` : ''}${to ? ' is-link' : ''}`}>
      {to ? <Link to={to} className="kpi-link">{content}</Link> : content}
    </li>
  );
}

export function KpiGrid({ label, children, compact = false }) {
  return <ul className={compact ? 'summary-grid kpi-grid' : 'summary-grid'} aria-label={label}>{children}</ul>;
}

/** Tarjeta independiente de un gráfico o estadística. Sin datos muestra un estado vacío consistente, sin gráficos simulados. */
export function ChartCard({ icon: Icon, title, empty = false, emptyIcon: EmptyIcon = Icon, emptyText, className = '', children }) {
  return (
    <article className={`chart-card ${className}`.trim()}>
      <header className="chart-card-head">
        <span className="panel-icon" aria-hidden="true"><Icon size={20} /></span>
        <h3>{title}</h3>
      </header>
      {empty ? (
        <div className="chart-empty">
          <EmptyIcon size={44} aria-hidden="true" />
          <b>{NO_DATA}</b>
          <p>{emptyText}</p>
        </div>
      ) : children}
    </article>
  );
}

export function lastValueHint(last) {
  return last ? formatDateTime(last.fecha) : undefined;  // hora de Argentina sin zona, tal cual la guarda el backend
}

const METRICS = [
  { key: 'glucosa', title: 'Glucosa experimental', unit: 'mg/dL', series: 'glucosaPromedio', note: 'Estimación experimental: no es un resultado clínico.' },
  { key: 'spo2', title: 'SpO₂', unit: '%', series: 'spo2Promedio' },
  { key: 'frecuenciaCardiaca', title: 'Frecuencia cardíaca', unit: 'lpm', series: 'frecuenciaPromedio' },
];

/** Un bloque independiente por variable (nunca mezcla variables): evolución, promedio, mínimo, máximo y resultados válidos.
 *  `demo`: los valores son simulados (pruebas DEMO): la glucosa se rotula como simulada, nunca como estimación experimental. */
export function MetricBlocks({ statistics, demo = false }) {
  if (!statistics || statistics.cantidadMediciones === 0) {
    return <p className="field-hint">No hay mediciones completadas en este período.</p>;
  }
  return (
    <div className="metric-blocks">
      {METRICS.map((definition) => {
        const { key, unit, series } = definition;
        const title = demo && key === 'glucosa' ? 'Glucosa simulada' : definition.title;
        const note = demo && key === 'glucosa' ? 'Valor simulado de una prueba DEMO: no es una medición real.' : definition.note;
        const metric = statistics[key];
        return (
          <article key={key} className="metric-block" aria-label={title}>
            <h3 className="member-list-title">{title}</h3>
            {metric.cantidad === 0 ? (
              <p className="field-hint">{NO_DATA}</p>
            ) : (
              <>
                <dl className="data-list">
                  <div><dt>Promedio</dt><dd>{formatNumber(metric.promedio, unit)}</dd></div>
                  <div><dt>Mínimo</dt><dd>{formatNumber(metric.minimo, unit)}</dd></div>
                  <div><dt>Máximo</dt><dd>{formatNumber(metric.maximo, unit)}</dd></div>
                  <div><dt>Resultados válidos</dt><dd>{metric.cantidad}</dd></div>
                </dl>
                <TrendChart title={`${title}: evolución por fecha`} unit={unit}
                  points={statistics.serieDiaria.map((point) => ({ label: formatDate(point.fecha), value: point[series] }))} />
                {note && <p className="field-hint">{note}</p>}
              </>
            )}
          </article>
        );
      })}
    </div>
  );
}

/** Barras horizontales simples (sin dependencias) para distribuciones y cargas por operador. */
export function BarList({ label, items }) {
  const max = Math.max(1, ...items.map((item) => item.value));
  if (items.length === 0) return <p className="field-hint">{NO_DATA}</p>;
  return (
    <ul className="bar-list" aria-label={label}>
      {items.map((item) => (
        <li key={item.label}>
          <span className="bar-label">
            {item.link ? <Link to={item.link}>{item.label}</Link> : item.label}
            {item.hint && <small> · {item.hint}</small>}
          </span>
          <span className="bar-track"><span className="bar-fill" style={{ width: `${(item.value / max) * 100}%` }} /></span>
          <b>{item.value}</b>
        </li>
      ))}
    </ul>
  );
}
