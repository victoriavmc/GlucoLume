// Piezas de Inicio: fecha y hora, aviso de bienestar, últimos valores, accesos rápidos y glucosa reciente.
// Nada se calcula ni se clasifica acá: los valores llegan de las mediciones guardadas y se muestran con su origen (experimental o DEMO).

import {
  ArrowRight, CalendarDays, ChartColumn, ChevronRight, Clock, Droplet, HeartPulse, Plus, Settings, ShieldCheck, Target, UserRound, Users, Wind, X, Zap,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { OriginBadge } from '../../../components/Badge.jsx';
import { EmptyState } from '../../../components/EmptyState.jsx';
import { TabPanel, Tabs } from '../../../components/Tabs.jsx';

import { EvolutionChart } from '../../../components/EvolutionChart.jsx';
import { VARIABLES, aggregateSeries, periodWindow, seriesFor } from '../measurements/evolutionModel.js';
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

/** Tarjeta de acceso con estructura fija (ícono y flecha arriba; título y descripción abajo): todas miden lo mismo aunque el texto sea más corto. */
function Shortcut({ to, icon: Icon, title, text }) {
  return (
    <li>
      <Link to={to} className="home-shortcut">
        <span className="home-shortcut-top">
          <span className="home-shortcut-icon"><Icon size={28} aria-hidden="true" /></span>
          <span className="home-shortcut-go"><ChevronRight size={20} aria-hidden="true" /></span>
        </span>
        <span className="home-shortcut-body"><b>{title}</b><small>{text}</small></span>
      </Link>
    </li>
  );
}

export function QuickAccess({ individual }) {
  return (
    <section className="home-card" aria-labelledby="home-accesos">
      <header className="home-card-head">
        <span className="home-card-icon is-bare"><Zap size={30} aria-hidden="true" /></span>
        <div>
          <h2 id="home-accesos">Accesos rápidos</h2>
          <p>Acciones frecuentes para que gestiones tu salud más fácilmente.</p>
        </div>
      </header>
      <ul className="home-shortcuts" aria-label="Accesos rápidos">
        {individual ? (
          <>
            <Shortcut to="/app/mediciones" icon={ChartColumn} title="Ver mis mediciones" text="Consultá tu historial y analizá tus tendencias." />
            <Shortcut to="/app/mediciones/nueva" icon={Plus} title="Nueva medición" text="Conectá tu dispositivo y registrá una medición." />
            <Shortcut to="/app/grupo" icon={Users} title="Ir a mi grupo" text="Compartí y revisá información con tu grupo." />
            <Shortcut to="/app/perfil" icon={Settings} title="Configurar perfil" text="Mantené tus datos actualizados." />
          </>
        ) : (
          <>
            <Shortcut to="/app/instituciones" icon={Users} title="Mis instituciones" text="Tus instituciones y los roles que tenés en cada una." />
            <Shortcut to="/app/perfil" icon={UserRound} title="Perfil" text="Tus datos personales." />
            <Shortcut to="/app/seguridad" icon={ShieldCheck} title="Seguridad" text="Verificación en dos pasos y sesiones." />
          </>
        )}
      </ul>
    </section>
  );
}

const PERIODS = [{ days: 1, label: '1D', name: 'Último día' }, { days: 7, label: '7D', name: 'Últimos 7 días' }, { days: 30, label: '30D', name: 'Últimos 30 días' }];
const TABS = ['glucosa', 'frecuenciaCardiaca', 'spo2', 'indiceOptico'];
const OVERVIEW = 'GENERAL';

/** Un gráfico de una variable con las mediciones del período; cada punto es una medición guardada (las pruebas DEMO con otro marcador). */
function VariableChart({ variable, points, chart, days }) {
  const spec = VARIABLES[variable];
  const series = aggregateSeries(seriesFor(points, variable, 'TODOS'), 'MEDICION');
  const domain = chart ? periodWindow(chart, { dias: days }, series) : undefined;
  if (series.length === 0) {
    return <EmptyState variant="framed" headingLevel={0} title={`Sin datos de ${spec.label.toLowerCase()} en este período.`} />;
  }
  return (
    <EvolutionChart title={spec.label} demoTitle={spec.demoLabel} series={series} unit={spec.unit} decimals={spec.decimals} color={spec.color}
      domain={domain} granularity="MEDICION" />
  );
}

/** Evolución reciente: pestañas por variable (o «Vista general» con las cuatro) y período 1D / 7D / 30D. Pasá el cursor por un punto para ver el valor y la hora. */
export function RecentEvolution({ chart, days, onDaysChange }) {
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
          <p>Tus últimas mediciones guardadas (la glucosa es una estimación experimental).</p>
        </div>
        <div className="home-toggle" role="group" aria-label="Período del gráfico">
          {PERIODS.map((period) => (
            <button key={period.days} type="button" className={`home-toggle-btn${days === period.days ? ' is-active' : ''}`} aria-pressed={days === period.days}
              aria-label={period.name} onClick={() => onDaysChange(period.days)}>{period.label}</button>
          ))}
        </div>
      </header>
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
                <VariableChart variable={key} points={points} chart={chart} days={days} />
              </article>
            ))}
          </div>
        ) : (
          <VariableChart variable={variable} points={points} chart={chart} days={days} />
        )}
      </TabPanel>
      {hasAny && chart !== undefined && <Link to="/app/mediciones#evolucion" className="home-more">Ver la evolución completa <ArrowRight size={18} aria-hidden="true" /></Link>}
    </section>
  );
}
