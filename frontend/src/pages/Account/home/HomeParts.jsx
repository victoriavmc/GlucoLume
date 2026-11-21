// Piezas de Inicio: fecha y hora, aviso de bienestar, últimos valores y evolución reciente.
// Nada se calcula ni se clasifica acá: los valores llegan de las mediciones guardadas y se muestran con su origen (experimental o DEMO).

import {
  ArrowRight, CalendarDays, ChartColumn, Clock, Droplet, HeartPulse, Target, Wind, X,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { OriginBadge } from '../../../components/Badge.jsx';
import { EmptyState } from '../../../components/EmptyState.jsx';
import { TabPanel, Tabs } from '../../../components/Tabs.jsx';

import { EvolutionChart } from '../../../components/EvolutionChart.jsx';
import { StackedBarChart } from '../../../components/StackedBarChart.jsx';
import {
  GROUPING_LABELS, HOME_PERIODS, VARIABLES, aggregateSeries, countByBlock, countGranularity, groupingOptions, periodWindow, seriesFor,
  shortBlockLabel,
} from '../measurements/evolutionModel.js';
import { formatDateTime } from '../groups/groupFormat.js';

const DISMISS_KEY = 'glucolume.home.bienestar.oculto';

const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);

/** «Miércoles, 15 de enero de 2026» y la hora, con el reloj del dispositivo (se actualiza cada medio minuto). */
export function DateBlock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(timer);
  }, []);
  const date = capitalize(now.toLocaleDateString('es-AR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }));
  const time = now.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hour12: false });
  return (
    <div className="home-date" aria-label="Fecha y hora actuales">
      <CalendarDays size={28} aria-hidden="true" />
      <div><b>{date}</b><small>{time}</small></div>
    </div>
  );
}

/** Aviso amable que se puede cerrar; si lo cerrás no vuelve a aparecer en este navegador (solo una comodidad, no un dato de la cuenta). */
export function WellbeingNotice() {
  const [hidden, setHidden] = useState(() => {
    try { return localStorage.getItem(DISMISS_KEY) === '1'; } catch { return false; }
  });
  if (hidden) return null;
  function close() {
    setHidden(true);
    try { localStorage.setItem(DISMISS_KEY, '1'); } catch { /* sin almacenamiento: se oculta solo en esta visita */ }
  }
  return (
    <aside className="home-notice" aria-label="Tu bienestar nos importa">
      <span className="home-notice-icon"><HeartPulse size={28} aria-hidden="true" /></span>
      <div>
        <b>Tu bienestar nos importa</b>
        <p>Mantené tus mediciones al día para un mejor seguimiento de tu salud.</p>
      </div>
      <button type="button" className="home-notice-close" onClick={close} aria-label="Cerrar el aviso"><X size={20} aria-hidden="true" /></button>
    </aside>
  );
}

/** «Hoy, 15:28», «Ayer, 09:10» o la fecha completa, a partir de la fecha y hora que guarda el backend (sin zona). */
export function whenText(stamp, now = new Date()) {
  if (!stamp) return '';
  const [date] = String(stamp).split('T');
  const pad = (value) => String(value).padStart(2, '0');
  const iso = (day) => `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const time = formatDateTime(stamp).split(' ')[1] ?? '';
  if (date === iso(now)) return `Hoy, ${time}`;
  if (date === iso(yesterday)) return `Ayer, ${time}`;
  return formatDateTime(stamp);
}

const KPIS = [
  { key: 'glucosa', label: 'Última glucosa', unit: 'mg/dL', icon: Droplet, tone: 'glucose', decimals: 0 },
  { key: 'frecuenciaCardiaca', label: 'Última frecuencia cardíaca', unit: 'lpm', icon: HeartPulse, tone: 'heart', decimals: 0 },
  { key: 'spo2', label: 'Última SpO₂', unit: '%', icon: Wind, tone: 'lungs', decimals: 1 },
  { key: 'indiceOptico', label: 'Último índice óptico', unit: '', icon: Target, tone: 'optic', decimals: 4 },
];

/** Cuatro tarjetas con el último valor medido. Sin dato nunca se muestra un cero. */
export function LatestKpis({ latest }) {
  return (
    <ul className="home-kpis" aria-label="Últimos valores medidos">
      {KPIS.map(({ key, label, unit, icon: Icon, tone, decimals }) => {
        const item = latest?.[key] ?? null;
        const loading = latest === undefined;
        return (
          <li key={key} className="home-kpi">
            <span className={`home-kpi-icon is-${tone}`}><Icon size={30} aria-hidden="true" /></span>
            <div className="home-kpi-body">
              <small>{label}</small>
              {loading ? <b className="is-empty">Cargando…</b> : item ? (
                <b>{item.value.toLocaleString('es-AR', { maximumFractionDigits: decimals })} {unit && <span>{unit}</span>}</b>
              ) : <b className="is-empty">Sin datos</b>}
            </div>
            <div className="home-kpi-foot">
              <span className="home-kpi-when"><Clock size={18} aria-hidden="true" /> {item ? whenText(item.when) : 'Todavía sin mediciones'}</span>
              {item && <OriginBadge origin={item.demo ? 'DEMO' : 'EXPERIMENTAL'}>{item.demo ? 'DEMO (prueba)' : 'Experimental'}</OriginBadge>}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

const TABS = ['glucosa', 'frecuenciaCardiaca', 'spo2', 'indiceOptico'];
const OVERVIEW = 'GENERAL';

/** Un gráfico de una variable con las mediciones del período; cada punto es una medición guardada (o un promedio por hora/día/semana/mes). */
function VariableChart({ variable, points, chart, days, grouping }) {
  const spec = VARIABLES[variable];
  const series = aggregateSeries(seriesFor(points, variable, 'TODOS'), grouping);
  const domain = chart ? periodWindow(chart, { dias: days }, series) : undefined;
  if (series.length === 0) {
    return <EmptyState variant="framed" headingLevel={0} title={`Sin datos de ${spec.label.toLowerCase()} en este período.`} />;
  }
  return (
    <EvolutionChart title={spec.label} demoTitle={spec.demoLabel} series={series} unit={spec.unit} decimals={spec.decimals} color={spec.color}
      domain={domain} granularity={grouping} />
  );
}

/** Evolución reciente: pestañas por variable (o «Vista general» con las cuatro), período (1D a 3A) y agrupación. Pasá el cursor por un punto para ver el valor y la hora. */
export function RecentEvolution({ chart, days, onDaysChange, grouping, onGroupingChange }) {
  const [variable, setVariable] = useState('glucosa');
  const points = chart?.puntos ?? [];
  const overview = variable === OVERVIEW;
  const hasAny = TABS.some((key) => seriesFor(points, key, 'TODOS').length > 0);
  return (
    <section className="home-card" aria-labelledby="home-evolucion">
      <header className="home-card-head">
        <span className="home-card-icon"><ChartColumn size={28} aria-hidden="true" /></span>
        <div>
          <h2 id="home-evolucion">Evolución reciente</h2>
          <p>Tus mediciones guardadas (la glucosa es una estimación experimental).</p>
        </div>
        <div className="home-toggle" role="group" aria-label="Período del gráfico">
          {HOME_PERIODS.map((period) => (
            <button key={period.days} type="button" className={`home-toggle-btn${days === period.days ? ' is-active' : ''}`} aria-pressed={days === period.days}
              aria-label={period.name} onClick={() => onDaysChange(period.days)}>{period.label}</button>
          ))}
        </div>
      </header>
      <div className="home-grouping" role="group" aria-label="Agrupar las mediciones">
        <span>Agrupar:</span>
        {groupingOptions(days).options.map((key) => (
          <button key={key} type="button" className={`home-chip${grouping === key ? ' is-active' : ''}`} aria-pressed={grouping === key}
            onClick={() => onGroupingChange(key)}>{GROUPING_LABELS[key]}</button>
        ))}
      </div>
      <Tabs label="Variable a graficar" idBase="home-evo" variant="pill" value={variable} onChange={setVariable}
        items={[...TABS, OVERVIEW].map((key) => ({ key, label: key === OVERVIEW ? 'Vista general' : VARIABLES[key].label }))} />
      <TabPanel idBase="home-evo" value={variable} className="ui-stack ui-stack--card">
        {chart === undefined ? (
          <EmptyState variant="framed" headingLevel={0} role="status" title="Cargando tus mediciones…" />
        ) : !hasAny ? (
          <EmptyState variant="framed" headingLevel={0} title="No hay mediciones en este período." description="Probá con otro período o hacé una nueva medición."
            action={<Link to="/app/mediciones/nueva" className="btn btn-outline">Nueva medición</Link>} />
        ) : overview ? (
          <div className="home-overview">
            {TABS.map((key) => (
              <article key={key} className="home-mini" aria-label={VARIABLES[key].label}>
                <h3>{VARIABLES[key].label} <small>({VARIABLES[key].unit || 'índice'})</small></h3>
                <VariableChart variable={key} points={points} chart={chart} days={days} grouping={grouping} />
              </article>
            ))}
          </div>
        ) : (
          <VariableChart variable={variable} points={points} chart={chart} days={days} grouping={grouping} />
        )}
      </TabPanel>
      {hasAny && chart !== undefined && <Link to="/app/mediciones#evolucion" className="home-more">Ver la evolución completa <ArrowRight size={18} aria-hidden="true" /></Link>}
    </section>
  );
}

const EACH_BLOCK = { HORA: 'una hora', DIA: 'un día', SEMANA: 'una semana', MES: 'un mes' };
const DEVICE_CATEGORIES = [
  { key: 'oximetria', label: 'Oximetría', color: '#0f8b8d' },
  { key: 'glucosa', label: 'Glucosa (experimental)', color: '#d98200' },
];
const MEAL_CATEGORIES = [
  { key: 'ayuno', label: 'En ayunas', color: '#2f6fb5' },
  { key: 'postprandial', label: 'Después de comer', color: '#7a5cc2' },
  { key: 'sinInformar', label: 'Sin informar', color: '#9aa3b5' },
];

/** Cuántas mediciones fueron con oxímetro o con glucosa, y en qué condición de comida, por bloque de tiempo del mismo período. */
export function MeasurementMix({ chart, days, grouping }) {
  const granularity = countGranularity(days, grouping);
  const window = periodWindow(chart, { dias: days }, []);
  const blocks = chart ? countByBlock(chart.puntos ?? [], granularity, window) : [];
  const total = blocks.reduce((sum, block) => sum + block.total, 0);
  const labelFor = (block) => shortBlockLabel(block.start, granularity);
  const describeBlock = (block, categories) => `${labelFor(block)}: ${block.total} ${block.total === 1 ? 'medición' : 'mediciones'}, ${categories
    .filter((category) => block[category.key] > 0).map((category) => `${block[category.key]} ${category.label.toLowerCase()}`).join(', ') || 'ninguna'}`;
  return (
    <section className="home-card" aria-labelledby="home-mezclas">
      <header className="home-card-head">
        <span className="home-card-icon"><ChartColumn size={28} aria-hidden="true" /></span>
        <div>
          <h2 id="home-mezclas">Cómo fueron tus mediciones</h2>
          <p>Cantidad por tipo de medición y por condición de comida. Agrupado {GROUPING_LABELS[granularity].toLowerCase()}.</p>
        </div>
      </header>
      {chart === undefined ? (
        <EmptyState variant="framed" headingLevel={0} role="status" title="Cargando tus mediciones…" />
      ) : total === 0 ? (
        <EmptyState variant="framed" headingLevel={0} title="No hay mediciones en este período." description="Probá con otro período o hacé una nueva medición." />
      ) : (
        <div className="home-mix">
          <StackedBarChart title="Oximetría y glucosa" categories={DEVICE_CATEGORIES} blocks={blocks} labelFor={labelFor}
            describe={(block) => describeBlock(block, DEVICE_CATEGORIES)} />
          <StackedBarChart title="Condición de comida" categories={MEAL_CATEGORIES} blocks={blocks} labelFor={labelFor}
            describe={(block) => describeBlock(block, MEAL_CATEGORIES)} />
        </div>
      )}
      <p className="home-mix-note">Cuenta todas las mediciones completadas del período, incluidas las pruebas DEMO. Cada barra es {EACH_BLOCK[granularity]}.</p>
    </section>
  );
}
