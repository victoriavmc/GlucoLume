// Panel de supervisión y gestión de la institución para MODERADOR y PROPIETARIO (un solo componente; las diferencias de rol salen de `can`).
// Todo lo calcula FastAPI (GET /institutions/{id}/dashboard → `administrativo`): son cantidades ADMINISTRATIVAS de actividad —toda
// medición iniciada, tenga o no valores— y se muestran desde el primer registro. No traen SpO₂, frecuencia cardíaca, glucosa, sexo ni edad,
// ni identifican pacientes: los resultados de salud agregados (`saludAgregada`) van aparte, separados por origen (DEMO sintético / experimental, con mínimo de pacientes). Con `fixedOperator`
// el mismo panel muestra la actividad laboral de UN operador (vista de supervisión), siempre como cantidades.

import {
  ArrowRight, Ban, ChartNoAxesColumn, ChartPie, CircleCheck, Cpu, FileText, FlaskConical, Layers, ShieldCheck, TrendingUp,
  Upload, UserRound, UsersRound, Wrench,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import * as dashboardApi from '../../../../api/dashboardApi.js';
import { ColumnChart, DonutChart, SeriesChart, StackedColumnChart, TimeSeriesChart } from '../../../../components/AnalyticsCharts.jsx';
import { Badge } from '../../../../components/Badge.jsx';
import { Alert, SelectField } from '../../../../components/FormControls.jsx';
import { ChartCard, Kpi, PeriodFilter, periodLabel } from '../../../../components/dashboard.jsx';
import { MEALS, MODES, STATES } from '../../measurements/measurementFormat.js';
import { can } from '../institutionFormat.js';

const DEFAULT_FILTERS = { period: { dias: 30 }, operador: '', modo: '', estado: '', origen: 'TODOS' };
const GRANULARITIES = { dia: 'Por día', semana: 'Por semana', mes: 'Por mes' };
const STATE_ORDER = ['COMPLETADA', 'CANCELADA', 'INVALIDA', 'PENDIENTE', 'ADQUIRIENDO', 'PROCESANDO'];

const option = (value, label) => ({ value, label });
const personName = (person) => [person?.nombre, person?.apellido].filter(Boolean).join(' ') || 'Operador desvinculado';

/** Inicio del día, de la semana (lunes) o del mes de una fecha «AAAA-MM-DD», sin tocar zonas horarias. */
function bucketOf(iso, granularity) {
  const [year, month, day] = iso.split('-').map(Number);
  if (granularity === 'mes') return `${year}-${String(month).padStart(2, '0')}-01`;
  if (granularity === 'semana') {
    const date = new Date(Date.UTC(year, month - 1, day));
    date.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 6) % 7));
    return date.toISOString().slice(0, 10);
  }
  return iso;
}

function requestFilters(filters, fixedOperator) {
  const params = { origen: filters.origen };
  const operator = fixedOperator ?? filters.operador;
  if (operator) params.operador = operator;
  if (filters.modo) params.modo = filters.modo;
  if (filters.estado) params.estado = filters.estado;
  return params;
}

// Variable -> cómo se llama, su unidad, de dónde sale cada punto (medición individual / promedio del día) y los decimales que se muestran.
const HEALTH_METRICS = [
  { key: 'glucosa', title: 'Glucosa estimada', unit: 'mg/dL', point: 'glucosa', dayAverage: 'glucosaPromedio', dayCount: 'glucosaN', decimals: 0 },
  { key: 'spo2', title: 'SpO₂', unit: '%', point: 'spo2', dayAverage: 'spo2Promedio', dayCount: 'spo2N', decimals: 1 },
  { key: 'frecuenciaCardiaca', title: 'Frecuencia cardíaca', unit: 'lpm', point: 'frecuenciaCardiaca', dayAverage: 'frecuenciaPromedio', dayCount: 'frecuenciaN', decimals: 0 },
];
const ORIGIN_NOTE = { DEMO: 'DEMO — dato sintético de prueba', EXPERIMENTAL: 'Experimental — estimación no clínica' };
const number = (value, decimals) => Number(value).toLocaleString('es-AR', { maximumFractionDigits: decimals });
const foodLabel = (key) => (key === 'NO_INFORMADA' ? 'Sin informar' : (MEALS[key] ?? key));

/** Una variable de un origen: promedio, mínimo, máximo y observaciones, y un gráfico temporal grande (por medición o por día). */
function HealthMetricCard({ group, metric, view }) {
  const demo = group.origen === 'DEMO';
  const summary = group[metric.key];
  const label = `${metric.title} — ${demo ? 'DEMO' : 'Experimental'}`;
  const points = useMemo(() => (view === 'dia'
    ? group.serieDiaria.map((day) => ({ t: new Date(`${day.fecha}T12:00:00`), y: day[metric.dayAverage], n: day[metric.dayCount] }))
    : group.puntos.map((item) => ({ t: new Date(item.fecha), y: item[metric.point], n: 1 }))), [group, metric, view]);
  return (
    <article className="hl-card" aria-label={label}>
      <h4>{label}</h4>
      {summary.cantidad === 0 ? (
        <p className="field-hint">Sin informar en ninguna de las mediciones incluidas.</p>
      ) : (
        <>
          <dl className="hl-stats">
            <div><dt>Promedio</dt><dd>{number(summary.promedio, 1)} <small>{metric.unit}</small></dd></div>
            <div><dt>Mínimo</dt><dd>{number(summary.minimo, 1)} <small>{metric.unit}</small></dd></div>
            <div><dt>Máximo</dt><dd>{number(summary.maximo, 1)} <small>{metric.unit}</small></dd></div>
            <div><dt>Observaciones</dt><dd>{summary.cantidad}</dd></div>
          </dl>
          <TimeSeriesChart title={`${label}: ${view === 'dia' ? 'promedio diario' : 'por medición'}`} unit={metric.unit} points={points} kind={view}
            tone={demo ? 'demo' : 'experimental'} origin={ORIGIN_NOTE[group.origen]} decimals={1} />
          {view === 'dia' && <p className="field-hint">Cada cuadrado es el promedio de un día (su tooltip indica cuántas observaciones lo componen); no es una medición individual.</p>}
        </>
      )}
    </article>
  );
}

/** Resumen compacto bajo los gráficos: modos, pacientes únicos, alimentación, calidad de señal y datos faltantes, con los mismos filtros. */
function HealthSummary({ group }) {
  const missing = [['glucosa', 'glucosa'], ['spo2', 'SpO₂'], ['frecuenciaCardiaca', 'frecuencia'], ['calidadSenal', 'calidad de señal']].filter(([key]) => group.sinInformar[key] > 0);
  return (
    <dl className="hl-summary" aria-label="Resumen de las mediciones incluidas">
      <div><dt>Mediciones</dt><dd>{group.mediciones} de {group.pacientes} {group.pacientes === 1 ? 'paciente único' : 'pacientes únicos'}</dd></div>
      <div><dt>Por modo</dt><dd>{Object.entries(group.porModo ?? {}).map(([mode, count]) => `${MODES[mode] ?? mode} ${count}`).join(' · ') || 'Sin informar'}</dd></div>
      <div><dt>Alimentación</dt><dd>{Object.entries(group.alimentacion ?? {}).map(([key, count]) => `${foodLabel(key)} ${count}`).join(' · ') || 'Sin informar'}</dd></div>
      <div>
        <dt>Calidad de señal</dt>
        <dd>{group.calidadSenal?.cantidad > 0 ? `promedio ${number(group.calidadSenal.promedio, 2)} · ${group.calidadSenal.cantidad} ${group.calidadSenal.cantidad === 1 ? 'lectura' : 'lecturas'}` : 'Sin informar en ninguna medición'}</dd>
      </div>
      <div><dt>Datos faltantes</dt><dd>{missing.length > 0 ? missing.map(([key, name]) => `${name} en ${group.sinInformar[key]}`).join(' · ') : 'Ninguno'}</dd></div>
    </dl>
  );
}

/** Un solo origen: o sus tres tarjetas (con su resumen) o un aviso compacto. Los DEMO permiten ver cada medición; los experimentales, solo promedios diarios. */
function HealthGroupView({ group, minimum, demo = false }) {
  const [view, setView] = useState(demo ? 'medicion' : 'dia');
  if (!group) return null;
  const label = demo ? 'Datos DEMO (sintéticos)' : 'Resultados experimentales';
  if (group.estado !== 'DISPONIBLE') {
    return <Alert kind="info"><b>{label}:</b> {group.motivo}</Alert>;
  }
  return (
    <section className={`mg-health${demo ? ' is-demo' : ''}`} aria-label={label}>
      <header className="hl-head">
        <h4 className="member-list-title">
          {demo ? 'Resultados DEMO — datos sintéticos de prueba' : 'Resultados experimentales — estimaciones no clínicas'}{' '}
          <Badge tone={demo ? 'warning' : 'brand'}>{demo ? 'Simulados' : 'Reales'}</Badge>
        </h4>
        {demo && (
          <div className="hl-toggle" role="group" aria-label="Vista temporal de los datos DEMO">
            <button type="button" className={view === 'medicion' ? 'is-on' : ''} aria-pressed={view === 'medicion'} onClick={() => setView('medicion')}>Por medición</button>
            <button type="button" className={view === 'dia' ? 'is-on' : ''} aria-pressed={view === 'dia'} onClick={() => setView('dia')}>Por día</button>
          </div>
        )}
      </header>
      {demo ? (
        <Alert kind="info">
          Son valores simulados de pruebas DEMO: no son mediciones clínicas, no describen la salud de ninguna persona y no se promedian con los experimentales.
        </Alert>
      ) : (
        <p className="field-hint">
          Son estimaciones experimentales, no resultados clínicos. Se muestran solo promedios diarios con al menos {minimum} pacientes distintos por día: el detalle por
          medición no se expone para no identificar a una persona.
        </p>
      )}
      <div className="hl-cards">
        {HEALTH_METRICS.map((metric) => <HealthMetricCard key={metric.key} group={group} metric={metric} view={view} />)}
      </div>
      {!demo && group.serieDiaria.length === 0 && (
        <p className="field-hint">Todavía ningún día reúne al menos {minimum} pacientes distintos: los promedios se muestran arriba, sin gráfico por fecha.</p>
      )}
      <HealthSummary group={group} />
    </section>
  );
}

function HealthResults({ health }) {
  const { experimentales, demo } = health;
  return (
    <div className="mg-health-groups">
      <HealthGroupView group={experimentales} minimum={health.minimoPacientes} />
      <HealthGroupView group={demo} minimum={health.minimoPacientes} demo />
    </div>
  );
}

function ChartBox({ icon: Icon, title, subtitle, wide = false, action, children }) {
  return (
    <article className={`chart-card mg-chart${wide ? ' is-wide' : ''}`}>
      <header className="chart-card-head has-subtitle">
        <span className="panel-icon" aria-hidden="true"><Icon size={20} /></span>
        <div><h3>{title}</h3><p className="field-hint">{subtitle}</p></div>
      </header>
      {action}
      {children}
    </article>
  );
}

function Filters({ filters, setFilters, operators, fixedOperator }) {
  const set = (field) => (event) => setFilters((current) => ({ ...current, [field]: event.target.value }));
  return (
    <div className="pe-filters mg-filters">
      <PeriodFilter value={filters.period} onChange={(period) => setFilters((current) => ({ ...current, period }))} idPrefix="mg-periodo" days={[7, 30, 90, 180, 365]} />
      {!fixedOperator && (
        <SelectField label="Operador" value={filters.operador} onChange={set('operador')}
          options={[option('', 'Todos los operadores'), ...operators.map((op) => option(op.idInstitucionUsuario, `${personName(op)}${op.activo ? '' : ' (desvinculado/a)'}`))]} />
      )}
      <SelectField label="Modo de medición" value={filters.modo} onChange={set('modo')}
        options={[option('', 'Todos'), ...Object.entries(MODES).map(([value, label]) => option(value, label))]} />
      <SelectField label="Estado" value={filters.estado} onChange={set('estado')}
        options={[option('', 'Todos'), ...STATE_ORDER.map((value) => option(value, STATES[value] ?? value))]} />
      <SelectField label="Origen de los datos" value={filters.origen} onChange={set('origen')}
        options={[option('TODOS', 'Todas las fuentes'), option('EXPERIMENTAL', 'Solo experimental'), option('DEMO', 'Solo DEMO (sintéticos)')]} />
    </div>
  );
}

function Indicators({ institution, kpis, period, fixedOperator }) {
  const owner = can(institution, 'GESTIONAR_MODERADORES'); // facultad exclusiva del propietario
  const notCompleted = kpis.canceladas + kpis.invalidas;
  const pending = (count) => `${count} ${count === 1 ? 'pendiente' : 'pendientes'}`;
  return (
    <>
      <ul className="summary-grid kpi-grid mg-kpis" aria-label="Indicadores administrativos">
        {!fixedOperator && <Kpi icon={UsersRound} label="Pacientes activos" value={kpis.pacientesActivos} hint={`${kpis.pacientesRegistrados} registrados`} />}
        {!fixedOperator && (
          <Kpi icon={UserRound} label="Pacientes con mediciones" value={kpis.pacientesConMediciones}
            hint={`pacientes distintos · ${kpis.total} ${kpis.total === 1 ? 'medición' : 'mediciones'}`} />
        )}
        {!fixedOperator && <Kpi icon={Wrench} tone={kpis.pacientesSinOperador ? 'warn' : undefined} label="Pacientes sin operador" value={kpis.pacientesSinOperador} hint="sin responsable" />}
        {!fixedOperator && <Kpi icon={UserRound} label="Operadores activos" value={kpis.operadoresActivos} />}
        {!fixedOperator && <Kpi icon={FileText} label="Mediciones en el período" value={kpis.total} hint={periodLabel(period)} />}
        <Kpi icon={CircleCheck} tone="ok" label="Completadas" value={kpis.completadas} hint="con valores válidos" />
        <Kpi icon={ChartNoAxesColumn} label="Experimentales" value={kpis.experimentales} hint="no incluye DEMO" />
        <Kpi icon={FlaskConical} tone="warn" label="DEMO (sintéticas)" value={kpis.demo} hint="datos simulados" />
        <Kpi icon={Ban} label="Canceladas o inválidas" value={notCompleted}
          hint={`${kpis.canceladas} canceladas · ${kpis.invalidas} inválidas${kpis.enCurso ? ` · ${kpis.enCurso} en curso` : ''}`} />
        {!fixedOperator && <Kpi icon={Upload} label="Transferencias pendientes" value={kpis.transferenciasPendientes} hint={`${kpis.transferenciasTotal} en total`} />}
        {!fixedOperator && <Kpi icon={Cpu} label="Dispositivos disponibles" value={kpis.dispositivosDisponibles} hint={`${kpis.dispositivosRegistrados} registrados`} />}
      </ul>
      {owner && !fixedOperator && (
        <ul className="summary-grid kpi-grid mg-kpis is-owner" aria-label="Indicadores de gestión del propietario">
          <Kpi icon={Layers} label="Personal activo" value={kpis.operadoresActivos + kpis.moderadoresActivos}
            hint={`${kpis.moderadoresActivos} moderadores · ${kpis.operadoresActivos} operadores`} />
          <Kpi icon={UsersRound} label="Pacientes registrados" value={kpis.pacientesRegistrados} hint={`${kpis.pacientesRegistrados - kpis.pacientesActivos} dados de baja`} />
          <Kpi icon={TrendingUp} label="Actividad total" value={kpis.total} hint="mediciones iniciadas en el período" />
        </ul>
      )}
    </>
  );
}

export function ManagementDashboard({ institution, handleOperationError, fixedOperator = null }) {
  const id = institution.idInstitucion;
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [granularity, setGranularity] = useState('dia');
  const [state, setState] = useState({ data: null, error: '' });
  const key = JSON.stringify([filters, fixedOperator]);

  useEffect(() => {
    let active = true;
    dashboardApi.getInstitutionDashboard(id, filters.period, requestFilters(filters, fixedOperator)).then(
      (data) => active && setState({ data, error: '' }),
      (error) => active && setState((current) => ({ ...current, error: handleOperationError(error) })),
    );
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, key]);

  const { data, error } = state;
  const stats = data?.administrativo;

  const series = useMemo(() => {
    if (!stats) return [];
    const grouped = new Map();
    for (const day of stats.serie) {
      const bucket = bucketOf(day.fecha, granularity);
      const current = grouped.get(bucket) ?? { completadas: 0, canceladas: 0, invalidas: 0, enCurso: 0 };
      for (const field of Object.keys(current)) current[field] += day[field];
      grouped.set(bucket, current);
    }
    const keys = [...grouped.keys()].sort();
    const line = (name, tone, field, dashed) => ({ name, tone, dashed, points: keys.map((bucket) => ({ x: bucket, y: grouped.get(bucket)[field], n: grouped.get(bucket)[field] })) });
    const all = [line('Completadas', 'experimental', 'completadas'), line('Canceladas', 'unknown', 'canceladas', true), line('Inválidas', 'info', 'invalidas', true), line('En curso', 'male', 'enCurso', true)];
    return all.filter((item) => item.name === 'Completadas' || item.points.some((point) => point.y > 0));
  }, [stats, granularity]);

  return (
    <section className="panel mg-panel" aria-labelledby="mg-titulo">
      <div className="inst-dashboard-head">
        <div className="panel-title">
          <span className="panel-icon is-lg" aria-hidden="true"><ChartNoAxesColumn size={26} /></span>
          <div>
            <h2 id="mg-titulo">{fixedOperator ? 'Actividad del operador' : 'Supervisión de la institución'}</h2>
            <p>{fixedOperator
              ? 'Cantidades de trabajo de este operador. Sus pacientes y valores de salud los consulta solo él, con autorización vigente.'
              : 'Actividad administrativa desde el primer registro. Son cantidades, no resultados de salud; los datos DEMO (sintéticos) van aparte.'}</p>
          </div>
        </div>
      </div>
      <Filters filters={filters} setFilters={setFilters} operators={stats?.operadores ?? []} fixedOperator={fixedOperator} />
      {error && <Alert>{error}</Alert>}
      {!data && !error && <p className="field-hint" role="status">Cargando el panel…</p>}
      {stats && (
        <>
          <Indicators institution={institution} kpis={stats.kpis} period={data.periodo} fixedOperator={fixedOperator} />
          {stats.truncado && <p className="field-hint">Hay muchas mediciones en el período: los gráficos usan las más recientes.</p>}
          <div className="mg-charts">
            <ChartBox icon={TrendingUp} title="Mediciones por fecha" subtitle="Toda la actividad: las canceladas e inválidas también cuentan."
              action={(
                <label className="mg-select">
                  <span className="sr-only">Agrupar mediciones</span>
                  <select className="field-input field-select" value={granularity} onChange={(event) => setGranularity(event.target.value)}>
                    {Object.entries(GRANULARITIES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                </label>
              )}>
              {stats.serie.length === 0 ? <p className="field-hint">No hay actividad con estos filtros.</p>
                : <SeriesChart title="Mediciones por fecha" unit="" series={series} granularity={granularity === 'mes' ? 'mes' : 'dia'} decimals={0} width={460} height={250} />}
            </ChartBox>

            <ChartBox icon={ChartPie} title="Distribución por modo" subtitle="Oximetría y glucosa experimental, con su estado y origen.">
              {stats.kpis.total === 0 ? <p className="field-hint">No hay actividad con estos filtros.</p> : (
                <>
                  <DonutChart title="Mediciones por modo" centerLabel="mediciones"
                    items={stats.porModo.map((mode, index) => ({ label: MODES[mode.modo] ?? mode.modo, value: mode.total, tone: index === 0 ? 'experimental' : 'soft', hint: mode.demo > 0 ? `${mode.demo} DEMO` : undefined }))} />
                  <div className="an-table-wrap">
                    <table className="an-table">
                      <caption className="sr-only">Estado y origen por modo de medición</caption>
                      <thead><tr><th scope="col">Modo</th><th scope="col"><abbr title="Completadas">Compl.</abbr></th><th scope="col"><abbr title="Canceladas">Canc.</abbr></th><th scope="col"><abbr title="Inválidas">Inv.</abbr></th><th scope="col"><abbr title="Experimentales">Exp.</abbr></th><th scope="col">DEMO</th></tr></thead>
                      <tbody>
                        {stats.porModo.map((mode) => (
                          <tr key={mode.modo}><th scope="row">{MODES[mode.modo] ?? mode.modo}</th><td>{mode.completadas}</td><td>{mode.canceladas}</td><td>{mode.invalidas}</td><td>{mode.experimentales}</td><td>{mode.demo}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </ChartBox>

            <ChartBox icon={FileText} title="Estados de las mediciones" subtitle="Cada estado, con experimentales, DEMO y sin origen.">
              {stats.kpis.total === 0 ? <p className="field-hint">No hay actividad con estos filtros.</p> : (
                <>
                  <StackedColumnChart title="Mediciones por estado" width={460} height={250}
                    categories={stats.porEstado.filter((item) => item.total > 0 || STATE_ORDER.slice(0, 3).includes(item.estado)).map((item) => ({
                      label: STATES[item.estado] ?? item.estado,
                      parts: [{ label: 'Experimentales', value: item.experimentales, tone: 'experimental' }, { label: 'DEMO (sintéticas)', value: item.demo, tone: 'demo' }, { label: 'Sin origen', value: item.sinResultado, tone: 'unknown' }],
                    }))}
                    legend={[{ label: 'Experimentales', tone: 'experimental' }, { label: 'DEMO (sintéticas)', tone: 'demo' }, { label: 'Sin origen (no completadas)', tone: 'unknown' }]} />
                  <p className="field-hint">«Sin origen» son las canceladas, inválidas o en curso: no tienen resultado, así que no son experimentales ni DEMO.</p>
                </>
              )}
            </ChartBox>

            <ChartBox icon={ChartPie} title="Mediciones por origen" subtitle="Experimentales, DEMO (sintéticas) y sin resultado; cada medición cuenta una vez.">
              {stats.kpis.total === 0 ? <p className="field-hint">No hay actividad con estos filtros.</p> : (
                <DonutChart title="Mediciones por origen" centerLabel="mediciones"
                  items={[{ label: 'Experimentales', value: stats.kpis.experimentales, tone: 'experimental' }, { label: 'DEMO (sintéticas)', value: stats.kpis.demo, tone: 'demo' },
                    { label: 'Sin resultado', value: stats.kpis.sinResultado, tone: 'unknown', hint: 'canceladas, inválidas o en curso' }]} />
              )}
            </ChartBox>

            {!fixedOperator && (
              <ChartBox icon={UsersRound} title="Pacientes con mediciones"
                subtitle={`${stats.kpis.pacientesConMediciones} ${stats.kpis.pacientesConMediciones === 1 ? 'paciente distinto aportó' : 'pacientes distintos aportaron'} ${stats.kpis.total} ${stats.kpis.total === 1 ? 'medición' : 'mediciones'} en el período. Un paciente puede medirse varias veces el mismo día.`}>
                <ColumnChart title="Pacientes según su cantidad de mediciones" unit="pacientes"
                  items={stats.pacientesPorCantidad.map((band) => ({
                    label: band.hasta === 0 ? 'Sin mediciones' : band.hasta === null ? `${band.desde} o más` : band.desde === band.hasta ? `${band.desde}` : `${band.desde}–${band.hasta}`,
                    value: band.pacientes,
                  }))} />
                <p className="field-hint">Cada columna cuenta pacientes según cuántas mediciones tienen. «Sin mediciones» son pacientes activos sin ninguna con estos filtros.</p>
              </ChartBox>
            )}

            <ChartBox icon={FileText} title="Alimentación" subtitle="Condición registrada en cada medición; «Sin informar» cuando no se indicó.">
              {stats.porAlimentacion.length === 0 ? <p className="field-hint">No hay actividad con estos filtros.</p> : (
                <ColumnChart title="Mediciones por alimentación"
                  items={stats.porAlimentacion.map((item) => ({ label: item.condicion === 'NO_INFORMADA' ? 'Sin informar' : (MEALS[item.condicion] ?? item.condicion), value: item.total }))} />
              )}
            </ChartBox>

            {!fixedOperator && data.saludAgregada && (
              <ChartBox icon={ShieldCheck} title="Resultados de salud agregados" wide
                subtitle="Solo mediciones completadas, de toda la institución. Aplican el período, el modo y el origen; experimentales y DEMO nunca se promedian juntos.">
                <HealthResults health={data.saludAgregada} />
              </ChartBox>
            )}

            {!fixedOperator && (
              <ChartBox icon={UserRound} title="Mediciones por operador" subtitle="Cantidades de trabajo de cada operador (quien inició la medición). Sin valores ni pacientes." wide>
                {stats.porOperador.length === 0 ? <p className="field-hint">Todavía no hay operadores.</p> : (
                  <div className="an-table-wrap">
                    <table className="an-table mg-operators">
                      <caption className="sr-only">Distribución de trabajo por operador</caption>
                      <thead>
                        <tr><th scope="col">Operador</th><th scope="col">Pacientes asignados</th><th scope="col">Mediciones</th><th scope="col">Completadas</th><th scope="col">Canceladas / inválidas</th>
                          <th scope="col">Experimentales</th><th scope="col">DEMO</th><th scope="col"><span className="sr-only">Carga</span></th></tr>
                      </thead>
                      <tbody>
                        {stats.porOperador.map((op) => {
                          const max = Math.max(1, ...stats.porOperador.map((item) => item.total));
                          return (
                            <tr key={op.idInstitucionUsuario}>
                              <th scope="row">
                                {can(institution, 'ADMINISTRAR_OPERADORES')
                                  ? <Link to={`/app/instituciones/${id}/personal/operadores/${op.idInstitucionUsuario}`}><b>{personName(op)}</b></Link>
                                  : <b>{personName(op)}</b>}
                                {!op.activo && <> <Badge tone="neutral">Desvinculado/a</Badge></>}
                              </th>
                              <td>{op.pacientesAsignados}</td><td><b>{op.total}</b></td><td>{op.completadas}</td><td>{op.canceladas + op.invalidas}</td><td>{op.experimentales}</td><td>{op.demo}</td>
                              <td className="mg-bar" aria-hidden="true"><span style={{ width: `${(op.total / max) * 100}%` }} /></td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
                {stats.porOperador.some((op) => !op.activo) && (
                  <p className="field-hint">Los operadores desvinculados se muestran solo si tuvieron actividad en el período elegido.</p>
                )}
              </ChartBox>
            )}
          </div>
          {fixedOperator === null && (
            <p className="field-hint">
              Período: {periodLabel(data.periodo)}. Las mediciones de pacientes ya anonimizados siguen sumando a estos conteos, sin revelar identidades.{' '}
              {can(institution, 'ADMINISTRAR_OPERADORES') && <Link to={`/app/instituciones/${id}/personal/operadores`}>Gestionar operadores <ArrowRight size={14} aria-hidden="true" /></Link>}
            </p>
          )}
        </>
      )}
    </section>
  );
}
