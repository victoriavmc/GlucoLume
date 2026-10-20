// Evolución grupal: por cada integrante que autorizó compartir su HISTORIAL (también el propio, si lo compartiste) se grafica cada medición
// con su fecha y hora completas. Las experimentales van en línea continua y las pruebas DEMO en línea punteada con puntos huecos, siempre
// rotuladas «DEMO (prueba)». Vista por variable o «Vista general» (grilla con todas, como en el dashboard personal), con los mismos filtros:
// período, origen de los datos y agrupación (cada medición, promedio por hora o por día). Hover = tooltip; clic = el punto queda resaltado y
// su detalle aparece en la misma vista. Quien solo compartió la última medición, el aviso o los datos básicos NO figura: ni se consulta ni se
// grafica. Los permisos los vuelve a verificar el backend en cada consulta.

import { CalendarDays, ChartColumn, Database, Droplet, HeartPulse, Info, Layers, Target, Wind } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import * as groupsApi from '../../../api/groupsApi.js';
import * as measurementsApi from '../../../api/measurementsApi.js';
import { ChartTooltip } from '../../../components/ChartTooltip.jsx';
import { EmptyState } from '../../../components/EmptyState.jsx';
import { PointDetail } from '../../../components/PointDetail.jsx';
import { TabPanel, Tabs } from '../../../components/Tabs.jsx';
import { useElementWidth } from '../../../components/useElementWidth.js';
import {
  GRANULARITIES, ORIGIN_FILTERS, VARIABLES, aggregateSeries, bucketLabel, describePoint, formatClock, formatDay, formatValue, otherValues,
  parseStamp, timeTicks, variableName,
} from '../measurements/evolutionModel.js';
import { personName } from './groupFormat.js';

const OVERVIEW = 'GENERAL';
const ORDER = ['glucosa', 'spo2', 'frecuenciaCardiaca', 'indiceOptico'];
const AXIS_LABELS = { glucosa: 'Glucosa', spo2: 'SpO₂', frecuenciaCardiaca: 'Frecuencia cardíaca', indiceOptico: 'Índice óptico' };
const TAB_ICONS = { glucosa: Droplet, frecuenciaCardiaca: HeartPulse, spo2: Wind, indiceOptico: Target };
const TAB_ORDER = ['glucosa', 'frecuenciaCardiaca', 'spo2', 'indiceOptico'];
const PERIODS = [7, 30, 90];
const COLORS = ['#e3101e', '#3b82f6', '#16a34a', '#7c3aed', '#d97706', '#0891b2'];

const PAD_WIDE = { top: 20, right: 24, bottom: 44, left: 72 };
const PAD_NARROW = { top: 20, right: 14, bottom: 44, left: 54 };
const DAY = 86_400_000;

function niceTicks(min, max, count = 4) {
  const span = max - min || Math.max(Math.abs(max) * 0.05, 1);
  const rough = span / count;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 5, 10].map((factor) => factor * magnitude).find((candidate) => candidate >= rough) ?? rough;
  const start = Math.floor(min / step) * step;
  const ticks = [];
  for (let value = start; value <= max + step; value += step) ticks.push(Number(value.toPrecision(12)));
  return ticks;
}

/** Un gráfico multiserie: una línea por integrante (y otra, punteada, por sus pruebas DEMO). `series[].points` ya vienen agrupados. */
function GroupLineChart({ title, variable, series, selectedKey, onSelect }) {
  const spec = VARIABLES[variable];
  const [hover, setHover] = useState(null);
  const [wrapRef, WIDTH] = useElementWidth();
  const HEIGHT = Math.round(Math.min(380, Math.max(280, WIDTH * 0.36)));
  const PAD = WIDTH < 480 ? PAD_NARROW : PAD_WIDE; // en pantallas chicas el eje Y cede espacio al área de puntos
  const all = series.flatMap((item) => item.points);
  if (all.length === 0) return <EmptyState variant="framed" headingLevel={0} title={`Sin datos de ${spec.label.toLowerCase()} para graficar con estos filtros.`} />;

  const times = all.map((point) => point.t);
  const t0 = Math.min(...times);
  const rawT1 = Math.max(...times);
  const t1 = rawT1 > t0 ? rawT1 : t0 + 3_600_000;
  const ticks = niceTicks(Math.min(...all.map((point) => point.value)), Math.max(...all.map((point) => point.value)));
  const lo = ticks[0];
  const hi = ticks.at(-1);
  const innerWidth = WIDTH - PAD.left - PAD.right;
  const innerHeight = HEIGHT - PAD.top - PAD.bottom;
  const x = (t) => PAD.left + Math.min(1, Math.max(0, (t - t0) / (t1 - t0))) * innerWidth;
  const y = (value) => PAD.top + innerHeight - ((value - lo) / (hi - lo || 1)) * innerHeight;
  const { ticks: xTicks, step } = timeTicks(t0, t1, Math.max(5, Math.floor(innerWidth / 85)));
  const hourly = step < DAY;
  const decimals = (point) => (point.bucket ? Math.max(spec.decimals, 1) : spec.decimals);
  const when = (point) => ({
    date: formatDay(point.bucket ? point.bucket.from : point.t),
    time: point.bucket ? (point.bucket.granularity === 'HORA' ? bucketLabel(point) : undefined) : formatClock(point.t),
  });

  const shown = hover ? (() => {
    const [serieKey, pointKey] = hover.split('|');
    const item = series.find((candidate) => candidate.key === serieKey);
    const point = item?.points.find((candidate) => candidate.key === pointKey);
    return item && point ? { item, point } : null;
  })() : null;

  return (
    <div className="gd-evo-wrap" ref={wrapRef}>
      <svg className="gd-evo-chart" width={WIDTH} height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="group" aria-label={`${title}: ${series.length} series`}>
        <title>{title}</title>
        {ticks.filter((tick) => tick <= hi).map((tick) => (
          <g key={tick}>
            <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(tick)} y2={y(tick)} className="gd-evo-grid" />
            <text x={PAD.left - 8} y={y(tick) + 4} textAnchor="end" className="trend-label">{formatValue(tick, Math.max(spec.decimals, 0))}</text>
          </g>
        ))}
        {xTicks.map((tick) => (
          <line key={`v${tick}`} x1={x(tick)} x2={x(tick)} y1={PAD.top} y2={PAD.top + innerHeight} className="gd-evo-grid is-vertical" />
        ))}
        <text x={16} y={PAD.top + innerHeight / 2} className="trend-label" transform={`rotate(-90 16 ${PAD.top + innerHeight / 2})`} textAnchor="middle">
          {AXIS_LABELS[variable]}{spec.unit ? ` (${spec.unit})` : ''}
        </text>
        {xTicks.map((tick) => (
          <text key={tick} x={x(tick)} y={HEIGHT - 14} textAnchor="middle" className="trend-label">
            {hourly && tick % DAY !== 0 ? formatClock(tick) : formatDay(tick).slice(0, 5)}
          </text>
        ))}
        {series.map((item) => {
          const path = item.points.map((point, i) => `${i === 0 ? 'M' : 'L'}${x(point.t).toFixed(1)},${y(point.value).toFixed(1)}`).join(' ');
          return (
            <g key={item.key}>
              <path d={path} fill="none" stroke={item.color} strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round"
                strokeOpacity="0.7" strokeDasharray={item.demo ? '6 5' : undefined} />
              {item.points.map((point) => {
                const id = `${item.key}|${point.key}`;
                const selected = id === selectedKey;
                const label = `${item.label} · ${when(point).date} ${when(point).time ?? ''}`.trim() + `: ${formatValue(point.value, decimals(point))} ${spec.unit}`;
                return (
                  <g key={point.key} tabIndex={0} role="button" aria-label={label} aria-pressed={selected} className="evo-point"
                    onMouseEnter={() => setHover(id)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(id)} onBlur={() => setHover(null)}
                    onClick={() => onSelect?.(item, point)}
                    onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect?.(item, point); } }}>
                    <circle cx={x(point.t)} cy={y(point.value)} r="14" className="evo-hit" />
                    <circle cx={x(point.t)} cy={y(point.value)} r={selected ? 8 : hover === id ? 7 : 5} stroke={selected ? '#1d2433' : item.color}
                      strokeWidth={selected ? 3 : 2} fill={item.demo ? '#fff' : item.color} />
                    {point.count > 1 && <text x={x(point.t)} y={y(point.value) - 10} textAnchor="middle" className="evo-count">{point.count}</text>}
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
      {shown && (
        <ChartTooltip left={(x(shown.point.t) / WIDTH) * 100} top={(y(shown.point.value) / HEIGHT) * 100}
          member={shown.item.name} color={shown.item.color} variable={variableName(variable, shown.item.demo)}
          value={formatValue(shown.point.value, decimals(shown.point))} unit={spec.unit} date={when(shown.point).date} time={when(shown.point).time}
          demo={shown.item.demo}
          note={shown.point.bucket ? `Promedio de ${shown.point.count} ${shown.point.count === 1 ? 'medición' : 'mediciones'}${shown.point.bucket.granularity === 'DIA' ? ' del día' : ' de esa hora'}` : undefined} />
      )}
    </div>
  );
}

const present = (value) => value !== null && value !== undefined;

export function GroupEvolution({ idGrupo, members, title = 'Evolución grupal de mediciones', description }) {
  const [variable, setVariable] = useState('glucosa');
  const [dias, setDias] = useState(30);
  const [origin, setOrigin] = useState('TODOS');
  const [granularity, setGranularity] = useState('MEDICION');
  const [selection, setSelection] = useState(null); // { variable, item, point }
  const [loaded, setLoaded] = useState(null); // { dias, items: [{ id, name, self, readings }], failed }

  // Solo quienes habilitaron «Historial de mediciones» (el backend lo vuelve a comprobar en cada consulta).
  const sharing = useMemo(
    () => members.filter((member) => member.comparteHistorial && (member.esVos || member.tienePerfil)),
    [members],
  );
  const key = `${dias}|${sharing.map((member) => member.idGrupoUsuario).join(',')}`;

  useEffect(() => {
    let active = true;
    if (sharing.length === 0) {
      setLoaded({ dias, items: [], failed: 0 });
      return undefined;
    }
    // Compartido: las estadísticas traen cada medición experimental (`puntos`) y, aparte, las pruebas DEMO (`puntosDemo`).
    // Propio: la evolución personal con todos los registros, cada uno marcado DEMO o experimental.
    const fetchMember = async (member) => {
      if (!member.esVos) {
        const statistics = await groupsApi.getSharedStatistics(idGrupo, member.idGrupoUsuario, dias);
        return [
          ...(statistics.puntos ?? []).map((point) => ({ ...point, demo: false })),
          ...(statistics.puntosDemo ?? []).map((point) => ({ ...point, demo: true })),
        ];
      }
      const own = await measurementsApi.getOwnEvolution({ dias, origen: 'TODOS' });
      return (own.puntos ?? []).map((point) => ({ ...point, demo: Boolean(point.esDemo) }));
    };
    Promise.allSettled(sharing.map(fetchMember)).then((results) => {
      if (!active) return;
      const items = [];
      let failed = 0;
      results.forEach((result, index) => {
        if (result.status !== 'fulfilled') {
          failed += 1;
          return;
        }
        const member = sharing[index];
        items.push({ id: member.idGrupoUsuario, name: `${personName(member)}${member.esVos ? ' (vos)' : ''}`, self: Boolean(member.esVos), readings: result.value });
      });
      setLoaded({ dias, items, failed });
    });
    return () => { active = false; };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  // Las series de una variable con el origen y la agrupación elegidos: por integrante, una experimental y otra DEMO (nunca mezcladas).
  const seriesOf = (variableKey) => (loaded?.items ?? []).flatMap((item, index) => {
    const color = COLORS[index % COLORS.length];
    const build = (demo) => aggregateSeries(
      item.readings
        .filter((reading) => reading.demo === demo && present(reading[variableKey]))
        .map((reading) => ({
          key: String(reading.idMedicion), ids: [reading.idMedicion], t: parseStamp(reading.fecha), value: Number(reading[variableKey]),
          demo, origin: demo ? 'DEMO' : 'EXPERIMENTAL', mode: reading.modoMedicion, count: 1,
        }))
        .filter((point) => Number.isFinite(point.t))
        .sort((a, b) => a.t - b.t),
      granularity,
    );
    const meta = { memberId: item.id, name: item.name, self: item.self, color };
    return [
      origin !== 'DEMO' && { ...meta, key: `${item.id}-exp`, demo: false, label: item.name, points: build(false) },
      origin !== 'EXPERIMENTAL' && { ...meta, key: `${item.id}-demo`, demo: true, label: `${item.name} · DEMO (prueba)`, points: build(true) },
    ].filter(Boolean);
  }).filter((item) => item.points.length > 0);

  const overview = variable === OVERVIEW;
  const visible = ORDER.filter((candidate) => seriesOf(candidate).length > 0);
  const legendSeries = overview ? visible.flatMap((candidate) => seriesOf(candidate)).filter((item, i, list) => list.findIndex((other) => other.key === item.key) === i)
    : seriesOf(variable);
  const ready = loaded !== null && loaded.dias === dias;
  const clear = () => setSelection(null);

  function choose(setter) {
    return (event) => { setter(event.target.value); clear(); };
  }

  // Detalle contextual del punto elegido: integrante, variable, valor, fecha y hora, origen y resumen; el detalle completo es secundario.
  function detail() {
    if (!selection) {
      return (
        <p className="gd-evo-note"><Info size={20} aria-hidden="true" /> Elegí un punto del gráfico para ver el detalle de esa medición acá mismo.</p>
      );
    }
    const { variable: chosen, item, point } = selection;
    const spec = VARIABLES[chosen];
    const bucket = point.bucket;
    const raw = !bucket ? loaded.items.find((candidate) => candidate.id === item.memberId)?.readings.find((reading) => String(reading.idMedicion) === point.key) : null;
    const to = item.self ? `/app/mediciones/${point.ids[0]}` : `/app/grupo/${idGrupo}/compartidos/${item.memberId}/mediciones/${point.ids[0]}`;
    return (
      <PointDetail member={item.name} color={item.color} variable={variableName(chosen, item.demo)}
        value={formatValue(point.value, bucket ? Math.max(spec.decimals, 1) : spec.decimals)} unit={spec.unit}
        date={formatDay(bucket ? bucket.from : point.t)} time={bucket ? (bucket.granularity === 'HORA' ? bucketLabel(point) : undefined) : formatClock(point.t)}
        demo={item.demo} summary={describePoint(point, chosen)} others={otherValues(raw, chosen)}>
        {!bucket && <Link to={to} className="btn btn-ghost point-detail-link">Ver detalle completo</Link>}
      </PointDetail>
    );
  }

  const selectedKeyFor = (variableKey) => (selection && (overview || selection.variable === variableKey) ? `${selection.item.key}|${selection.point.key}` : null);
  const onSelectFor = (variableKey) => (item, point) => setSelection({ variable: variableKey, item, point });

  return (
    <section className="gd-panel" aria-labelledby="grupo-evolucion">
      <header className="gd-evo-head">
        <h2 id="grupo-evolucion"><span className="gd-section-icon"><ChartColumn size={22} aria-hidden="true" /></span>{title}</h2>
        <p className="gd-evo-hint">
          {description ?? 'Comparativa de las mediciones compartidas por los integrantes que habilitaron «Historial de mediciones». Las pruebas DEMO también se muestran, identificadas aparte (línea punteada) y sin mezclarse con las experimentales.'}
        </p>
        <p className="gd-evo-hint">
          Pasá el cursor por un punto para ver quién, qué, cuánto, cuándo y el origen; hacé clic para dejarlo seleccionado y ver su detalle.
        </p>
      </header>
      <Tabs label="Variable a comparar" idBase="group-evo" variant="pill" value={variable} onChange={(key) => { setVariable(key); clear(); }}
        items={[...TAB_ORDER, OVERVIEW].map((key) => ({ key, icon: key === OVERVIEW ? ChartColumn : TAB_ICONS[key], label: key === OVERVIEW ? 'Vista general' : VARIABLES[key].label }))} />
      <TabPanel idBase="group-evo" value={variable} className="ui-stack">
      <section className="gd-evo-filters" aria-label="Filtros de la evolución">
        <label className="gd-evo-filter">
          <span className="gd-evo-filter-icon"><Database size={22} aria-hidden="true" /></span>
          <span className="gd-evo-filter-body">
            <span>Origen de los datos</span>
            <select className="field-input field-select" aria-label="Origen de los datos de la evolución" value={origin} onChange={choose(setOrigin)}>
              {Object.entries(ORIGIN_FILTERS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </span>
        </label>
        <label className="gd-evo-filter">
          <span className="gd-evo-filter-icon"><Layers size={22} aria-hidden="true" /></span>
          <span className="gd-evo-filter-body">
            <span>Agrupación</span>
            <select className="field-input field-select" aria-label="Agrupación de la evolución" value={granularity} onChange={choose(setGranularity)}>
              {Object.entries(GRANULARITIES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </span>
        </label>
        <label className="gd-evo-filter">
          <span className="gd-evo-filter-icon"><CalendarDays size={22} aria-hidden="true" /></span>
          <span className="gd-evo-filter-body">
            <span>Período</span>
            <select className="field-input field-select" aria-label="Período de la evolución" value={dias} onChange={(event) => { setDias(Number(event.target.value)); clear(); }}>
              {PERIODS.map((count) => <option key={count} value={count}>Últimos {count} días</option>)}
            </select>
          </span>
        </label>
      </section>
      {!ready ? (
        <p className="field-hint" role="status">Cargando la evolución…</p>
      ) : sharing.length === 0 ? (
        <EmptyState variant="framed" headingLevel={0} title="Ningún integrante compartió su historial de mediciones, por eso no hay nada para graficar." />
      ) : (
        <>
          {overview ? (
            <div className="evolution-overview" aria-label="Vista general grupal">
              {visible.length === 0 && <EmptyState variant="framed" headingLevel={0} title="Ninguna variable tiene datos con estos filtros." />}
              {visible.map((candidate) => (
                <article key={candidate} className="evolution-card" aria-label={VARIABLES[candidate].label}>
                  <h3 className="member-list-title">{VARIABLES[candidate].label} <small>({VARIABLES[candidate].unit || 'índice'})</small></h3>
                  <GroupLineChart title={`${VARIABLES[candidate].label}: evolución por integrante`} variable={candidate} series={seriesOf(candidate)}
                    selectedKey={selectedKeyFor(candidate)} onSelect={onSelectFor(candidate)} />
                </article>
              ))}
            </div>
          ) : (
            <div className="gd-evo-frame">
              <GroupLineChart title={`${VARIABLES[variable].label}: evolución por integrante`} variable={variable} series={seriesOf(variable)}
                selectedKey={selectedKeyFor(variable)} onSelect={onSelectFor(variable)} />
              <ul className="gd-evo-legend" aria-label="Series graficadas">
                {legendSeries.map((item) => (
                  <li key={item.key}><span className={`gd-evo-swatch${item.demo ? ' is-demo' : ''}`} style={{ '--swatch': item.color }} aria-hidden="true" />{item.label}</li>
                ))}
              </ul>
            </div>
          )}
          {overview && (
            <ul className="gd-evo-legend" aria-label="Series graficadas">
              {legendSeries.map((item) => (
                <li key={item.key}>
                  <span className={`gd-evo-swatch${item.demo ? ' is-demo' : ''}`} style={{ '--swatch': item.color }} aria-hidden="true" />{item.label}
                </li>
              ))}
            </ul>
          )}
          {granularity !== 'MEDICION' && (
            <p className="field-hint">Cada punto es el promedio de las mediciones de un{granularity === 'HORA' ? 'a hora' : ' día'} de esa persona; el número indica cuántas se promediaron.</p>
          )}
          {(!overview || visible.length > 0) && <div className="gd-evo-detail">{detail()}</div>}
          {loaded.failed > 0 && <p className="field-hint">No pudimos cargar los datos de {loaded.failed} integrante{loaded.failed === 1 ? '' : 's'}.</p>}
        </>
      )}
      </TabPanel>
    </section>
  );
}
