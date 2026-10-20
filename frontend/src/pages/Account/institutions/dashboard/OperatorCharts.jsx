// Fila de gráficos del panel del OPERADOR (su propio dashboard). Todo viene calculado de FastAPI (`graficos` del dashboard del operador):
// serie y modos cuentan las mediciones que él inició en el período —los mismos números que sus indicadores—, la calidad de señal solo usa
// pacientes que tiene a cargo hoy y la demografía cuenta pacientes únicos asignados. Los datos DEMO (sintéticos) siempre van con su propio
// color y nunca se funden con los experimentales. Sin nombres ni documentos dentro de los gráficos.

import { ArrowRight, ChartNoAxesColumn, ChartPie, TrendingUp, UsersRound } from 'lucide-react';
import { Activity } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { DonutChart, SeriesChart, StackedColumnChart } from '../../../../components/AnalyticsCharts.jsx';
import { periodLabel } from '../../../../components/dashboard.jsx';
import { MODES } from '../../measurements/measurementFormat.js';

const GRANULARITIES = { dia: 'Por día', semana: 'Por semana', mes: 'Por mes' };

/** Inicio del día, de la semana (lunes) o del mes de una fecha «AAAA-MM-DD», para agrupar sin tocar zonas horarias. */
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

function ChartBox({ icon: Icon, title, subtitle, children, action }) {
  return (
    <article className="chart-card op-chart">
      <header className="chart-card-head has-subtitle">
        <span className="panel-icon" aria-hidden="true"><Icon size={20} /></span>
        <div>
          <h3>{title}</h3>
          <p className="field-hint">{subtitle}</p>
        </div>
      </header>
      {action}
      {children}
    </article>
  );
}

const quality = (value) => Number(value).toLocaleString('es-AR', { maximumFractionDigits: 3 });

export function OperatorChartsSection({ institution, data }) {
  const [granularity, setGranularity] = useState('dia');
  const charts = data.graficos;
  if (!charts) return null;
  // El análisis detallado arranca con el MISMO período y con todas las fuentes, para que no parezca que cambian las cantidades.
  const range = data.periodo.desde || data.periodo.hasta;
  const query = new URLSearchParams(range ? { ...(data.periodo.desde ? { desde: data.periodo.desde } : {}), ...(data.periodo.hasta ? { hasta: data.periodo.hasta } : {}), origen: 'TODOS' }
    : { dias: String(data.periodo.dias ?? 30), origen: 'TODOS' });
  const analysisPath = `/app/instituciones/${institution.idInstitucion}/pacientes/analisis?${query}`;

  // 1) Mediciones por fecha (experimentales y DEMO en series separadas).
  const grouped = new Map();
  for (const day of charts.serie) {
    const key = bucketOf(day.fecha, granularity);
    const current = grouped.get(key) ?? { experimentales: 0, demo: 0 };
    grouped.set(key, { experimentales: current.experimentales + day.experimentales, demo: current.demo + day.demo });
  }
  const keys = [...grouped.keys()].sort();
  const totalDemo = charts.serie.reduce((sum, day) => sum + day.demo, 0);
  const series = [
    { name: 'Experimentales', tone: 'experimental', points: keys.map((key) => ({ x: key, y: grouped.get(key).experimentales, n: grouped.get(key).experimentales })) },
    ...(totalDemo > 0 ? [{ name: 'DEMO (sintéticas)', tone: 'demo', dashed: true, points: keys.map((key) => ({ x: key, y: grouped.get(key).demo, n: grouped.get(key).demo })) }] : []),
  ];

  // 2) Distribución por modo: cantidades y porcentajes sobre las mismas mediciones.
  const modeItems = charts.porModo.map((mode, index) => ({
    label: MODES[mode.modo] ?? mode.modo, value: mode.experimentales + mode.demo, tone: index === 0 ? 'experimental' : 'soft',
    hint: mode.demo > 0 ? `${mode.demo} DEMO` : undefined,
  }));
  const modeTotal = modeItems.reduce((sum, item) => sum + item.value, 0);

  // 3) Calidad de señal: rangos iguales del intervalo registrado, sin categorías inventadas.
  const q = charts.calidadSenal;
  const qualityCategories = q.rangos.map((bin) => ({
    label: bin.desde === bin.hasta ? quality(bin.desde) : `${quality(bin.desde)}–${quality(bin.hasta)}`,
    parts: [{ label: 'Experimentales', value: bin.experimentales, tone: 'experimental' }, { label: 'DEMO (sintéticas)', value: bin.demo, tone: 'demo' }],
  }));

  // 4) Pacientes por sexo y edad.
  const demographics = charts.demografia.map((row) => ({
    label: row.rango === 'SIN_INFORMAR' ? 'Sin informar' : row.rango,
    parts: [{ label: 'Masculino', value: row.masculino, tone: 'male' }, { label: 'Femenino', value: row.femenino, tone: 'female' }, { label: 'Sin informar', value: row.sinInformar, tone: 'unknown' }],
  }));
  const sexTotals = ['masculino', 'femenino', 'sinInformar'].map((key) => charts.demografia.reduce((sum, row) => sum + row[key], 0));

  return (
    <section className="panel" aria-labelledby="op-graficos">
      <div className="panel-head">
        <div className="panel-title">
          <span className="panel-icon is-lg" aria-hidden="true"><ChartNoAxesColumn size={26} /></span>
          <div>
            <h2 id="op-graficos">Gráficos de mi trabajo</h2>
            <p>Mediciones que iniciaste en {periodLabel(data.periodo)} y pacientes que tenés a cargo. Los datos DEMO son sintéticos y van aparte.</p>
            <p className="field-hint">El análisis detallado usa las mediciones de tus pacientes actuales (las hayas hecho vos u otro operador), por eso sus totales pueden diferir.</p>
          </div>
        </div>
        <Link to={analysisPath} className="summary-link">Análisis detallado de mediciones <ArrowRight size={16} aria-hidden="true" /></Link>
      </div>
      {charts.truncado && <p className="field-hint">Hay muchas mediciones en el período: los gráficos usan las más recientes.</p>}
      {charts.sinResultado > 0 && (
        <p className="field-hint">{charts.sinResultado} {charts.sinResultado === 1 ? 'medición cancelada o inválida' : 'mediciones canceladas o inválidas'} del período no {charts.sinResultado === 1 ? 'tiene' : 'tienen'} resultado ni origen: no se grafican como experimentales ni como DEMO.</p>
      )}
      <div className="op-charts">
        <ChartBox icon={TrendingUp} title="Mediciones por fecha" subtitle="Cantidad de mediciones realizadas."
          action={(
            <label className="op-chart-select">
              <span className="sr-only">Agrupar mediciones</span>
              <select className="field-input field-select" value={granularity} onChange={(event) => setGranularity(event.target.value)}>
                {Object.entries(GRANULARITIES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
              </select>
            </label>
          )}>
          {keys.length === 0 ? <p className="field-hint">No hiciste mediciones en este período.</p>
            : <SeriesChart title="Mediciones por fecha" unit="" series={series} granularity={granularity === 'mes' ? 'mes' : 'dia'} decimals={0} width={440} height={250} />}
        </ChartBox>

        <ChartBox icon={ChartPie} title="Distribución por modo" subtitle="Tipos de medición en el período.">
          {modeTotal === 0 ? <p className="field-hint">No hiciste mediciones en este período.</p> : <DonutChart title="Mediciones por modo" items={modeItems} centerLabel="mediciones" />}
        </ChartBox>

        <ChartBox icon={Activity} title="Calidad de señal" subtitle="Valor registrado en las mediciones de tus pacientes.">
          {q.conValor === 0 ? (
            <p className="field-hint">Ninguna medición de tus pacientes guardó calidad de señal en este período ({q.sinDato} sin dato): las que llegan del equipo, experimentales y DEMO, no la informan. No se inventa.</p>
          ) : (
            <>
              <StackedColumnChart title="Mediciones por rango de calidad de señal registrada" categories={qualityCategories} width={440} height={175}
                legend={[{ label: 'Experimentales', tone: 'experimental' }, { label: 'DEMO (sintéticas)', tone: 'demo' }]} />
              <p className="field-hint">{q.conValor} con calidad (de {quality(q.minimo)} a {quality(q.maximo)}) · {q.sinDato} sin dato. El sistema no define umbrales: los rangos parten el intervalo observado.
                {q.fueraDeAlcance > 0 && ` ${q.fueraDeAlcance} de pacientes que ya no tenés a cargo no se leen.`}</p>
            </>
          )}
          {q.lecturas.length > 0 && (
            <>
              <h4 className="op-subchart">Lecturas estabilizadas por medición</h4>
              <StackedColumnChart title="Lecturas estabilizadas por medición" width={440} height={175} categories={q.lecturas.map((bin) => ({
                label: String(bin.lecturas), parts: [{ label: 'Experimentales', value: bin.experimentales, tone: 'experimental' }, { label: 'DEMO (sintéticas)', value: bin.demo, tone: 'demo' }],
              }))} legend={[{ label: 'Experimentales', tone: 'experimental' }, { label: 'DEMO (sintéticas)', tone: 'demo' }]} />
              <p className="field-hint">{q.conLecturas} con lecturas estabilizadas: cuántas lecturas estables registró el equipo al guardar. No es la calidad de señal.</p>
            </>
          )}
        </ChartBox>

        <ChartBox icon={UsersRound} title="Pacientes por sexo y edad" subtitle="Pacientes que tenés a cargo hoy.">
          {charts.pacientesDemografia === 0 ? <p className="field-hint">No tenés pacientes asignados.</p> : (
            <>
              <StackedColumnChart title="Pacientes por rango de edad y sexo" categories={demographics} width={440} height={250}
                legend={[{ label: `Masculino (${sexTotals[0]})`, tone: 'male' }, { label: `Femenino (${sexTotals[1]})`, tone: 'female' }, { label: `Sin informar (${sexTotals[2]})`, tone: 'unknown' }]} />
              <p className="field-hint">Cuenta pacientes únicos. La edad sale de la fecha de nacimiento (o de la edad declarada); lo que falta es «Sin informar».</p>
            </>
          )}
        </ChartBox>
      </div>
    </section>
  );
}
