// «Evolución de mis mediciones»: gráficos históricos interactivos sobre las mediciones REALES guardadas (GET /measurements/evolution).
// Pestañas de variable (cada una con su escala y unidad), selector de período, de origen (experimentales / DEMO / todos) y de agregación. Los
// datos DEMO se distinguen siempre y sus estadísticas van aparte: nunca hay promedios mezclados. Esto es distinto del monitoreo EN VIVO.

import { Activity, ArrowDown, ArrowUp, ChartColumn, Clock, Droplet, FileText, FlaskConical, Heart, Minus, Signal } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { EvolutionChart } from '../../../components/EvolutionChart.jsx';
import { PointDetail } from '../../../components/PointDetail.jsx';
import { OriginBadge } from '../../../components/Badge.jsx';
import { EmptyState } from '../../../components/EmptyState.jsx';
import { Alert, SelectField } from '../../../components/FormControls.jsx';
import { TabPanel, Tabs } from '../../../components/Tabs.jsx';
import { Kpi, NO_DATA, PeriodFilter } from '../../../components/dashboard.jsx';
import { MODES } from '../groups/groupFormat.js';
import { formatDateTime } from './measurementFormat.js';
import {
  GRANULARITIES, ORIGIN_FILTERS, ORIGIN_SUFFIX, VARIABLES, aggregateSeries, bucketLabel, describePoint, formatClock, formatDay, formatValue, otherValues,
  parseStamp, periodWindow, seriesFor, variableName,
} from './evolutionModel.js';

const PERIOD_DAYS = [1, 7, 14, 30, 90];
const OVERVIEW = 'GENERAL';
// Orden de las pestañas: la glucosa (objetivo del proyecto) primero.
const TABS = ['glucosa', 'frecuenciaCardiaca', 'spo2', 'calidadSenal', 'indiceOptico'];
const personalPointPath = (id) => `/app/mediciones/${id}`;

function StatCards({ title, stats, variable, tag }) {
  const spec = VARIABLES[variable];
  const stat = stats?.[variable];
  const cell = (label, Icon, value, decimals = spec.decimals) => (
    <li className="evo-stat" key={label}>
      <span className="evo-stat-icon"><Icon size={18} aria-hidden="true" /></span>
      <span>
        <small>{label}</small>
        <b>{value === null || value === undefined ? NO_DATA : `${formatValue(value, decimals)} ${spec.unit}`.trim()}</b>
      </span>
    </li>
  );
  return (
    <section className="evolution-stats" aria-label={title}>
      <h4 className="member-list-title">{title} {tag && <OriginBadge origin={tag}>{tag}</OriginBadge>}</h4>
      <ul className="evo-stat-list">
        {cell('Último valor del período', Clock, stat?.ultimo?.valor)}
        {cell('Promedio del período', Minus, stat?.promedio, Math.max(spec.decimals, 1))}
        {cell('Mínimo registrado', ArrowDown, stat?.minimo)}
        {cell('Máximo registrado', ArrowUp, stat?.maximo)}
        <li className="evo-stat">
          <span className="evo-stat-icon"><FileText size={18} aria-hidden="true" /></span>
          <span><small>Registros considerados</small><b>{stat?.cantidad ?? 0}</b></span>
        </li>
      </ul>
    </section>
  );
}

/** Mediciones que hay detrás del punto elegido: un enlace «Ver detalle completo» (medición única) o la lista de las promediadas. */
function SelectedActions({ selection, pointPath }) {
  const { point, variable } = selection;
  const spec = VARIABLES[variable];
  if (!point.bucket && point.count === 1) {
    return <Link to={pointPath(point.ids[0])} className="btn btn-ghost point-detail-link">Ver detalle completo</Link>;
  }
  return (
    <ul className="evolution-members" aria-label="Mediciones promediadas">
      {point.items.map((item) => (
        <li key={item.key}>
          <Link to={pointPath(item.ids[0])}>{formatDay(item.t)} {formatClock(item.t)}</Link> — {formatValue(item.value, spec.decimals)} {spec.unit}
        </li>
      ))}
    </ul>
  );
}

/** Detalle del punto elegido, dentro de la misma vista: variable, valor, fecha, hora, origen y resumen. Con `actions` incluye el acceso al detalle completo. */
function SelectedPoint({ selection, points, pointPath, actions = false }) {
  if (!selection) return <p className="field-hint">Elegí un punto del gráfico para ver el detalle de esa medición acá mismo.</p>;
  const { point, variable } = selection;
  const spec = VARIABLES[variable];
  const bucket = point.bucket;
  const raw = !bucket && point.count === 1 ? points.find((item) => item.idMedicion === point.ids[0]) : null;
  return (
    <PointDetail variable={variableName(variable, point.demo)} value={formatValue(point.value, bucket ? Math.max(spec.decimals, 1) : spec.decimals)}
      unit={spec.unit} date={formatDay(bucket ? bucket.from : point.t)}
      time={bucket ? (bucket.granularity === 'HORA' ? bucketLabel(point) : undefined) : formatClock(point.t)} demo={point.demo}
      summary={[!bucket && (MODES[point.mode] ?? null), describePoint(point, variable)].filter(Boolean).join(' · ')}
      others={otherValues(raw, variable)}>
      {actions && <SelectedActions selection={selection} pointPath={pointPath} />}
    </PointDetail>
  );
}

/** Tarjetas del paciente: total (DEMO y experimentales por separado), promedio de cada variable y calidad de señal. Cada promedio usa solo
 * las mediciones que tienen ese dato e informa cuántas fueron; DEMO y experimentales nunca se promedian juntos. Sin dato no hay número. */
function PatientKpis({ data, origin }) {
  const { resumen, estadisticas, puntos } = data;
  const blocks = [origin !== 'DEMO' && ['EXPERIMENTAL', estadisticas.experimental], origin !== 'EXPERIMENTAL' && ['DEMO', estadisticas.demo]].filter(Boolean);
  const counted = (n) => `${n} ${n === 1 ? 'valor' : 'valores'}`;
  const tag = (group) => (group === 'DEMO' ? 'DEMO (simulado)' : 'Experimental');

  function mean(icon, label, variable, tone) {
    const spec = VARIABLES[variable];
    const lines = blocks.map(([group, stats]) => [group, stats?.[variable]]).filter(([, stat]) => stat && stat.cantidad > 0);
    const show = ([, stat]) => `${formatValue(stat.promedio, Math.max(spec.decimals, 1))} ${spec.unit}`.trim();
    return (
      <Kpi key={variable} icon={icon} tone={tone} label={label} value={lines.length ? show(lines[0]) : null}
        hint={lines.length === 1 ? `${counted(lines[0][1].cantidad)}${lines[0][0] === 'DEMO' ? ' · DEMO (simulado)' : ''}`
          : lines.map(([group, stat]) => <span key={group} className="kpi-line">{tag(group)}: {show([group, stat])} · {counted(stat.cantidad)}</span>)} />
    );
  }

  const quality = blocks.map(([group, stats]) => [group, stats?.calidadSenal]).filter(([, stat]) => stat && stat.cantidad > 0);
  const withQuality = quality.reduce((sum, [, stat]) => sum + stat.cantidad, 0);
  const shown = puntos.filter((point) => (origin === 'TODOS' ? true : origin === 'DEMO' ? point.esDemo : !point.esDemo)).length;
  const last = resumen.ultima;
  return (
    <>
      <ul className="summary-grid kpi-grid is-five" aria-label="Resumen de las mediciones del paciente">
        <Kpi icon={Activity} label="Total de mediciones" value={resumen.total}
          hint={<><span className="kpi-line">{resumen.demo} DEMO (simuladas)</span><span className="kpi-line">{resumen.experimentales} experimentales</span></>} />
        {mean(Droplet, 'SpO₂ promedio', 'spo2', 'info')}
        {mean(Heart, 'Frecuencia cardíaca promedio', 'frecuenciaCardiaca')}
        {mean(FlaskConical, 'Glucosa estimada promedio', 'glucosa', 'warn')}
        <Kpi icon={Signal} tone="ok" label="Calidad de señal" value={quality.length ? formatValue(quality.reduce((sum, [, stat]) => sum + stat.promedio * stat.cantidad, 0) / withQuality, 2) : null}
          hint={<>
            {quality.length > 0 && <span className="kpi-line">{counted(withQuality)} · rango {formatValue(Math.min(...quality.map(([, stat]) => stat.minimo)), 2)}–{formatValue(Math.max(...quality.map(([, stat]) => stat.maximo)), 2)}</span>}
            <span className="kpi-line">Sin dato: {Math.max(0, shown - withQuality)}</span>
          </>} />
      </ul>
      <p className="field-hint evo-strip">
        Oximetría: {resumen.porModo.OXIMETRIA ?? 0} · Glucosa experimental: {resumen.porModo.GLUCOSA_EXPERIMENTAL ?? 0} · Última medición:{' '}
        {last ? `${formatDateTime(last.fecha)} (${MODES[last.modoMedicion] ?? last.modoMedicion}, ${last.esDemo ? 'DEMO simulada' : 'experimental'})` : NO_DATA}
      </p>
    </>
  );
}

export function EvolutionPanel({
  data, period, onPeriodChange, title = 'Evolución de mis mediciones', pointPath = personalPointPath, mode, onModeChange, compact = false,
  description = 'Visualizá cómo variaron tus valores en el tiempo. Cada punto es una medición guardada; la glucosa es una estimación experimental, no clínica.',
}) {
  // Sin elección de la persona se propone lo que tiene datos: glucosa si hay, y las pruebas DEMO si es lo único que hay.
  const [variableChoice, setVariableChoice] = useState(null);
  const [originChoice, setOriginChoice] = useState(null);
  const [granularity, setGranularity] = useState('MEDICION');
  const [selected, setSelected] = useState(null);

  const points = data?.puntos ?? [];
  const hasExperimental = points.some((point) => !point.esDemo);
  const hasDemo = points.some((point) => point.esDemo);
  // Ficha del paciente (`compact`): todas las fuentes juntas pero en series separadas; el resto propone lo que tiene datos.
  const origin = originChoice ?? (compact ? 'TODOS' : !hasExperimental && hasDemo ? 'DEMO' : 'EXPERIMENTAL');
  const seriesOf = (key) => aggregateSeries(seriesFor(points, key, origin), granularity);
  // El eje X representa el período elegido (p. ej. las últimas 24 horas), no solo el rango en que hay datos.
  const domain = periodWindow(data, period, points.map((point) => ({ t: parseStamp(point.fecha) })).filter((point) => Number.isFinite(point.t)));
  const variable = variableChoice ?? (compact ? OVERVIEW : seriesOf('glucosa').length > 0 ? 'glucosa' : 'frecuenciaCardiaca');
  const visible = Object.keys(VARIABLES).filter((key) => seriesOf(key).length > 0);
  const overview = variable === OVERVIEW;
  const spec = VARIABLES[variable];
  const series = overview ? [] : seriesOf(variable);
  const noPoints = points.filter((point) => (origin === 'TODOS' || (origin === 'DEMO' ? point.esDemo : !point.esDemo))).length === 0;

  function changeVariable(key) {
    setVariableChoice(key);
    setSelected(null);
  }

  // Una medición se elige con clic y queda resaltada (también en los demás gráficos de la vista general); el detalle sale en esta misma vista.
  function selectPoint(key, point) {
    setSelected({ variable: key, point });
  }

  // El rótulo dice el origen de lo que realmente se dibuja (con «Todas» y solo DEMO, es «DEMO (datos simulados)»).
  const drawn = points.filter((point) => (origin === 'TODOS' || (origin === 'DEMO' ? point.esDemo : !point.esDemo)));
  const drawsDemo = drawn.some((point) => point.esDemo);
  const suffix = ORIGIN_SUFFIX[drawsDemo ? (drawn.some((point) => !point.esDemo) ? 'TODOS' : 'DEMO') : 'EXPERIMENTAL'];
  // «Glucosa experimental — DEMO» sería contradictorio: con datos DEMO el valor es una estimación o una simulación.
  const heading = (key) => (key === 'glucosa' && drawsDemo ? 'Glucosa estimada' : VARIABLES[key].label);
  const chartArticle = !overview && series.length > 0 && (
    <article className="evolution-card" aria-label={spec.label}>
      <h3 className="member-list-title">{heading(variable)} — {suffix} <small>({spec.unit || 'índice'})</small></h3>
      <EvolutionChart title={spec.label} demoTitle={spec.demoLabel} series={series} unit={spec.unit} decimals={spec.decimals} color={spec.color}
        domain={domain} granularity={granularity}
        selectedKey={selected?.point.key} onSelect={(point) => selectPoint(variable, point)} />
      {selected && selected.variable === variable ? (
        <div className="evolution-selected"><SelectedActions selection={selected} pointPath={pointPath} /></div>
      ) : (
        <p className="field-hint">Elegí un punto del gráfico para ver el detalle de esa medición a la derecha.</p>
      )}
    </article>
  );

  return (
    <section className="panel evolution-panel" id="evolucion" aria-labelledby="evolucion-titulo">
      <div className="evo-head">
        <div className="panel-title">
          <span className="panel-icon"><ChartColumn size={22} aria-hidden="true" /></span>
          <div>
            <h2 id="evolucion-titulo">{title}</h2>
            <p>{description}</p>
          </div>
        </div>
        {!compact && <PeriodFilter value={period} onChange={(next) => { setSelected(null); onPeriodChange(next); }} idPrefix="evo" days={PERIOD_DAYS} />}
      </div>

      {compact && (
        <div className="pe-filters">
          <PeriodFilter value={period} onChange={(next) => { setSelected(null); onPeriodChange(next); }} idPrefix="evo" days={PERIOD_DAYS} />
          {onModeChange && (
            <SelectField label="Modo" value={mode ?? ''} onChange={(event) => { onModeChange(event.target.value); setSelected(null); }}
              options={[{ value: '', label: 'Todos' }, ...Object.entries(MODES).map(([key, label]) => ({ value: key, label }))]} />
          )}
          <SelectField label="Origen" value={origin} onChange={(event) => { setOriginChoice(event.target.value); setSelected(null); }}
            options={[{ value: 'TODOS', label: 'Todas' }, { value: 'DEMO', label: 'DEMO' }, { value: 'EXPERIMENTAL', label: 'Experimental' }]} />
          <SelectField label="Variable" value={variable} onChange={(event) => changeVariable(event.target.value)}
            options={[{ value: OVERVIEW, label: 'Todas' }, ...TABS.map((key) => ({ value: key, label: VARIABLES[key].label }))]} />
        </div>
      )}
      {compact && data?.resumen && <PatientKpis data={data} origin={origin} />}
      {origin !== 'EXPERIMENTAL' && points.some((point) => point.esDemo) && (
        <Alert kind="info">Los datos DEMO son simulados por el firmware para probar el equipo: no representan resultados clínicos y se calculan aparte de los experimentales.</Alert>
      )}

      {!compact && <Tabs label="Variable" idBase="evo" variant="pill" value={variable} onChange={changeVariable}
        items={[...TABS, OVERVIEW].map((key) => ({ key, label: key === OVERVIEW ? 'Vista general' : VARIABLES[key].label }))} />}

      <TabPanel idBase="evo" value={variable} className="ui-stack">
      {!compact && <div className="form-grid measurement-filters evo-filters">
        <SelectField label="Origen de los datos" value={origin} onChange={(event) => { setOriginChoice(event.target.value); setSelected(null); }}
          options={Object.entries(ORIGIN_FILTERS).map(([key, label]) => ({ value: key, label }))} />
        {onModeChange && (
          <SelectField label="Modo de medición" value={mode ?? ''} onChange={(event) => { onModeChange(event.target.value); setSelected(null); }}
            options={[{ value: '', label: 'Todos los modos' }, ...Object.entries(MODES).map(([key, label]) => ({ value: key, label }))]} />
        )}
        <SelectField label="Agrupación" value={granularity} onChange={(event) => { setGranularity(event.target.value); setSelected(null); }}
          options={Object.entries(GRANULARITIES).map(([key, label]) => ({ value: key, label }))} />
      </div>}

      {data === null ? (
        <p className="field-hint" role="status">Cargando la evolución…</p>
      ) : noPoints ? (
        <EmptyState variant="framed" headingLevel={0} role="status"
          title={origin === 'DEMO' ? 'No hay pruebas DEMO en este período.' : 'No hay mediciones guardadas en este período.'}
          description="Probá con otro período u origen, o hacé una nueva medición." />
      ) : overview ? (
        <div className={`evolution-overview${compact ? ' is-four' : ''}`} aria-label="Vista general">
          {visible.length === 0 && <EmptyState variant="framed" headingLevel={0} title="Ninguna métrica tiene datos en este período." />}
          {visible.length > 0 && <div className="evolution-overview-detail"><SelectedPoint selection={selected} points={points} pointPath={pointPath} actions /></div>}
          {visible.map((key) => (
            <article key={key} className="evolution-card" aria-label={VARIABLES[key].label}>
              <h3 className="member-list-title">{heading(key)} — {suffix} <small>({VARIABLES[key].unit || 'índice'})</small></h3>
              <EvolutionChart title={VARIABLES[key].label} demoTitle={VARIABLES[key].demoLabel} domain={domain} granularity={granularity} series={seriesOf(key)} unit={VARIABLES[key].unit} decimals={VARIABLES[key].decimals}
                color={VARIABLES[key].color} selectedKey={selected?.point.key} onSelect={(point) => selectPoint(key, point)} />
            </article>
          ))}
        </div>
      ) : series.length === 0 ? (
        <EmptyState variant="framed" headingLevel={0} role="status"
          title={variable === 'glucosa'
            ? 'Sin datos disponibles de glucosa experimental en este período (las mediciones sin calibrar no informan glucosa).'
            : `Sin datos disponibles de ${spec.label.toLowerCase()} en este período.`} />
      ) : null}

      {!overview && data && !noPoints && (
        <div className="evo-body">
          {chartArticle}
          <div className="evo-side">
            {selected && selected.variable === variable ? (
              <>
                <SelectedPoint selection={selected} points={points} pointPath={pointPath} />
                <button type="button" className="btn btn-ghost" onClick={() => setSelected(null)}>Volver a las estadísticas del período</button>
              </>
            ) : (
              <>
            {(origin === 'EXPERIMENTAL' || origin === 'TODOS') && (
              <StatCards title={`${spec.label}: estadísticas experimentales`} stats={data.estadisticas.experimental} variable={variable} />
            )}
            {(origin === 'DEMO' || origin === 'TODOS') && (
              <StatCards title={`${spec.label}: estadísticas de pruebas`} stats={data.estadisticas.demo} variable={variable} tag="DEMO" />
            )}
              </>
            )}
          </div>
        </div>
      )}
      </TabPanel>
      {data?.truncado && <p className="field-hint">Hay más mediciones que las que se pueden graficar: se muestran las más recientes del período.</p>}
    </section>
  );
}
