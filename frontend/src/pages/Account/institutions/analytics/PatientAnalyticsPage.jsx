// /app/instituciones/:id/pacientes/analisis — dashboard analítico del OPERADOR sobre sus pacientes activos.
// Todo lo calcula el backend (GET /institutions/{id}/analytics/patients) y aplica el alcance: solo el operador responsable vigente, solo sus
// pacientes. Esta pantalla no filtra permisos, solo presenta: no hay forma de elegir a otro operador. Reglas de presentación:
//   · por defecto TODAS las fuentes y todos los estados (nada de DEMO excluido en silencio); lo DEMO (sintético) va siempre en series, colores y
//     promedios aparte, y si un filtro de origen deja el resultado vacío se explica con los totales por origen;
//   · «Sin informar» es una categoría más; un dato ausente nunca se grafica ni se promedia como 0;
//   · cada estadística muestra con cuántas observaciones válidas se calculó;
//   · al elegir un paciente se reutiliza el historial existente (MeasurementHistory), no una segunda implementación.

import {
  Activity, ChartColumn, CircleAlert, Droplet, FileText, FlaskConical, ListFilter, RotateCcw, Signal, UserRound, UsersRound, Wind,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useOutletContext, useSearchParams } from 'react-router-dom';

import * as dashboardApi from '../../../../api/dashboardApi.js';
import * as institutionsApi from '../../../../api/institutionsApi.js';
import { ColumnChart, DonutChart, SeriesChart, SplitBars, StackedColumnChart } from '../../../../components/AnalyticsCharts.jsx';
import { Badge } from '../../../../components/Badge.jsx';
import { EmptyState } from '../../../../components/EmptyState.jsx';
import { Alert, CheckField, SelectField, TextField } from '../../../../components/FormControls.jsx';
import { ChartCard, Kpi, KpiGrid, PeriodFilter } from '../../../../components/dashboard.jsx';
import { MeasurementHistory } from '../../measurements/MeasurementHistory.jsx';
import { MODES, formatDate, formatDateTime } from '../../measurements/measurementFormat.js';
import { can } from '../institutionFormat.js';
import { patientName } from '../patients/PatientsPage.jsx';

const SEX_LABELS = { MASCULINO: 'Masculino', FEMENINO: 'Femenino', SIN_INFORMAR: 'Sin informar' };
const SEX_TONES = { MASCULINO: 'male', FEMENINO: 'female', SIN_INFORMAR: 'unknown' };
const FOOD_LABELS = { AYUNO: 'Ayuno', POSTPRANDIAL: 'Después de comer', NO_INFORMADA: 'Sin informar' };
const VARIABLES = {
  spo2: { label: 'SpO₂', unit: '%' },
  frecuenciaCardiaca: { label: 'Frecuencia cardíaca', unit: 'lpm' },
  glucosaDispositivo: { label: 'Glucosa del dispositivo', unit: 'mg/dL' },
  glucosaEstimada: { label: 'Glucosa estimada con matriz', unit: 'mg/dL' },
  indiceOptico: { label: 'Índice óptico', unit: '' },
};
const MISSING_LABELS = {
  spo2: 'SpO₂', frecuenciaCardiaca: 'Frecuencia cardíaca', glucosa: 'Glucosa', calidadSenal: 'Calidad de señal',
  alimentacion: 'Alimentación', edadAlMomento: 'Edad al momento de la medición',
};
const SEGMENTS = {
  NINGUNA: 'Sin segmentar', SEXO: 'Sexo', EDAD: 'Rango de edad', ALIMENTACION: 'Alimentación', MODO: 'Modo de medición', ORIGEN: 'Origen',
  DISPOSITIVO: 'Dispositivo', MATRIZ: 'Matriz experimental',
};
const DEFAULT_AGE_RANGES = ['0-12', '13-17', '18-30', '31-50', '51-70', '71+', 'SIN_INFORMAR'];
const POSITION_LABELS = { DENTRO: 'Dentro del intervalo', POR_DEBAJO: 'Por debajo del intervalo', POR_ENCIMA: 'Por encima del intervalo' };

const DEFAULTS = {
  period: { dias: 30 }, idPerfilMedicion: '', sexo: '', edad: '', edadBase: 'ACTUAL', alimentacion: '', modo: '', origen: 'TODOS',
  estado: 'TODOS', calidad: '', calidadMinima: '', edadCortes: '', segmentar: 'NINGUNA', variable: 'spo2', granularidad: 'dia',
  compararMatriz: false, pagina: 1,
};

const option = (value, label) => ({ value, label });

/** Estado inicial: lo que llega del panel del operador (período y origen) cuando es compatible; si no, todas las fuentes y 30 días. */
function initialFilters(search) {
  const days = Number(search.get('dias'));
  const range = search.get('desde') || search.get('hasta');
  const origin = search.get('origen');
  return {
    ...DEFAULTS,
    period: range ? { desde: search.get('desde') || undefined, hasta: search.get('hasta') || undefined, dias: 30 } : { dias: [7, 30, 90, 180, 365].includes(days) ? days : 30 },
    origen: ['TODOS', 'EXPERIMENTAL', 'DEMO'].includes(origin) ? origin : DEFAULTS.origen,
  };
}

const SECONDARY = ['sexo', 'edad', 'edadCortes', 'edadBase', 'alimentacion', 'estado', 'calidad', 'calidadMinima', 'granularidad', 'segmentar'];

function requestParams(filters) {
  const { period, ...rest } = filters;
  const params = period.desde || period.hasta ? { desde: period.desde, hasta: period.hasta } : { dias: period.dias };
  for (const [key, value] of Object.entries(rest)) {
    if (value !== '' && value !== false && value !== undefined) params[key] = value;
  }
  params.tamanioPagina = 10;
  return params;
}

const SEGMENT_LABELS = { MODO: MODES, ALIMENTACION: FOOD_LABELS, SEXO: SEX_LABELS };
const segmentLabel = (kind, category) => (category === 'SIN_INFORMAR' ? 'Sin informar' : SEGMENT_LABELS[kind]?.[category] ?? category);
const isDemo = (origin) => origin === 'DEMO';
const num = (value, unit) => (value === null || value === undefined ? 'Sin informar' : `${Number(value).toLocaleString('es-AR', { maximumFractionDigits: 1 })}${unit ? ` ${unit}` : ''}`);

/** Cortes de edad «12,17,30,50,70»: se aplican al salir del campo o con Enter, para no consultar con cada tecla. */
function CutsField({ value, onCommit }) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  const commit = () => { if (draft.trim() !== value) onCommit(draft.trim()); };
  return (
    <TextField label="Cortes de edad (años)" value={draft} placeholder="12,17,30,50,70" inputMode="numeric" title="Edad máxima de cada rango, separada por comas" onChange={(event) => setDraft(event.target.value)}
      onBlur={commit} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); commit(); } }} />
  );
}

function Filters({ filters, setFilters, patientsList, ageRanges, onReset }) {
  const set = (field) => (event) => setFilters((current) => ({ ...current, [field]: event.target.value, pagina: 1 }));
  const glucoseVariable = filters.variable === 'glucosaDispositivo' || filters.variable === 'glucosaEstimada';
  const activeSecondary = SECONDARY.filter((key) => filters[key] !== DEFAULTS[key]).length;
  return (
    <section className="panel an-filters" aria-labelledby="an-filtros">
      <div className="panel-head">
        <div className="panel-title">
          <span className="panel-icon" aria-hidden="true"><ListFilter size={22} /></span>
          <div>
            <h2 id="an-filtros">Filtros</h2>
            <p>Se combinan entre sí y solo alcanzan a tus pacientes activos.</p>
          </div>
        </div>
        <button type="button" className="btn btn-outline" onClick={onReset}><RotateCcw size={16} aria-hidden="true" /> Limpiar filtros</button>
      </div>
      <div className="pe-filters an-primary">
        <PeriodFilter value={filters.period} onChange={(period) => setFilters((current) => ({ ...current, period, pagina: 1 }))} idPrefix="an-periodo" days={[7, 30, 90, 180, 365]} />
        <SelectField label="Paciente" value={filters.idPerfilMedicion} onChange={set('idPerfilMedicion')}
          options={[option('', 'Todos mis pacientes'), ...patientsList.map((p) => option(p.idPerfilMedicion, patientName(p)))]} />
        <SelectField label="Origen de los datos" value={filters.origen} onChange={set('origen')}
          options={[option('TODOS', 'Todas las fuentes'), option('EXPERIMENTAL', 'Solo experimental'), option('DEMO', 'Solo DEMO (sintéticos)')]} />
        <SelectField label="Modo de medición" value={filters.modo} onChange={set('modo')}
          options={[option('', 'Todos'), ...Object.entries(MODES).map(([v, l]) => option(v, l))]} />
        <SelectField label="Variable a analizar" value={filters.variable} onChange={set('variable')}
          options={Object.entries(VARIABLES).map(([v, item]) => option(v, `${item.label}${item.unit ? ` (${item.unit})` : ''}`))} />
      </div>
      <details className="an-more">
        <summary>Más filtros{activeSecondary > 0 ? ` (${activeSecondary} ${activeSecondary === 1 ? 'activo' : 'activos'})` : ''}</summary>
      <div className="an-filter-grid">
        <SelectField label="Sexo (biológico, para el modelo)" value={filters.sexo} onChange={set('sexo')}
          options={[option('', 'Todos'), ...Object.entries(SEX_LABELS).map(([v, l]) => option(v, l))]} />
        <SelectField label="Rango de edad" value={filters.edad} onChange={set('edad')}
          options={[option('', 'Todos'), ...ageRanges.map((v) => option(v, v === 'SIN_INFORMAR' ? 'Sin informar' : `${v} años`))]} />
        <CutsField value={filters.edadCortes} onCommit={(edadCortes) => setFilters((current) => ({ ...current, edadCortes, edad: '', pagina: 1 }))} />
        <SelectField label="La edad es…" value={filters.edadBase} onChange={set('edadBase')}
          options={[option('ACTUAL', 'Actual del paciente'), option('MEDICION', 'La que tenía al medir')]} />
        <SelectField label="Alimentación" value={filters.alimentacion} onChange={set('alimentacion')}
          options={[option('', 'Todas'), ...Object.entries(FOOD_LABELS).map(([v, l]) => option(v, l))]} />
        <SelectField label="Estado" value={filters.estado} onChange={set('estado')}
          options={[option('COMPLETADA', 'Completadas'), option('INVALIDA', 'Inválidas'), option('CANCELADA', 'Canceladas'), option('TODOS', 'Todos')]} />
        <SelectField label="Calidad de señal" value={filters.calidad} onChange={set('calidad')}
          options={[option('', 'Todas'), option('CON_DATO', 'Con dato registrado'), option('SIN_INFORMAR', 'Sin informar')]} />
        <TextField label="Calidad de señal mínima" type="number" min="0" step="0.1" value={filters.calidadMinima} onChange={set('calidadMinima')}
          placeholder="Sin mínimo" title="Excluye también las mediciones que no registraron calidad" />
        <SelectField label="Agrupar por" value={filters.granularidad} onChange={set('granularidad')}
          options={[option('dia', 'Día'), option('semana', 'Semana'), option('mes', 'Mes')]} />
        <SelectField label="Segmentar la variable por" value={filters.segmentar} onChange={set('segmentar')}
          options={Object.entries(SEGMENTS).map(([v, l]) => option(v, l))} />
      </div>
      </details>
      {glucoseVariable && filters.idPerfilMedicion && (
        <CheckField label="Comparar con la matriz experimental (solo mediciones de glucosa experimental; no es un diagnóstico)"
          checked={filters.compararMatriz} onChange={(event) => setFilters((current) => ({ ...current, compararMatriz: event.target.checked }))} />
      )}
    </section>
  );
}

/** Qué origen se está viendo y, si el filtro deja todo en cero pero hay registros del otro origen, un mensaje con los totales (no «desaparecen»). */
function OriginNotice({ data, filters, onShowAll }) {
  const totals = data.origenes;
  const origin = filters.origen;
  if (origin === 'DEMO') {
    return <Alert kind="info">Estás viendo solo datos DEMO: valores sintéticos para probar la comunicación del dispositivo, no mediciones reales.</Alert>;
  }
  if (!totals) return null;
  const hidden = origin === 'EXPERIMENTAL' ? totals.demo : 0;
  if (origin === 'EXPERIMENTAL' && data.kpis.totalMediciones === 0 && hidden > 0) {
    return (
      <Alert kind="info">
        No hay mediciones experimentales con estos filtros, pero los registros no desaparecieron: hay {totals.experimentales} experimentales y {totals.demo} DEMO (sintéticas).
        {' '}<button type="button" className="btn btn-outline" onClick={onShowAll}>Ver todas las fuentes</button>
      </Alert>
    );
  }
  return (
    <p className="field-hint an-origins" role="status">
      Con estos filtros: <b>{totals.experimentales}</b> experimentales · <b>{totals.demo}</b> DEMO (sintéticas)
      {totals.sinResultado > 0 && <> · <b>{totals.sinResultado}</b> sin resultado (canceladas o inválidas: no tienen valores ni origen)</>}.
      {origin === 'TODOS' ? ' Se muestran separadas y nunca se promedian juntas.' : hidden > 0 ? ` Hay ${hidden} DEMO fuera de esta vista.` : ''}
    </p>
  );
}

function KpiSection({ data }) {
  const { kpis } = data;
  const share = kpis.totalMediciones ? `${Math.round((kpis.demo / kpis.totalMediciones) * 1000) / 10} % del total` : undefined;
  return (
    <>
      <KpiGrid label="Indicadores del análisis" compact>
        <Kpi icon={UsersRound} label="Pacientes en el alcance" value={kpis.pacientesEnAlcance} hint="A tu cargo, con los filtros de paciente" />
        <Kpi icon={Activity} label="Pacientes con mediciones" value={kpis.pacientesConMediciones} hint={`Únicos, de ${kpis.pacientesEnAlcance}`} />
        <Kpi icon={FileText} label="Mediciones" value={kpis.totalMediciones} hint={`${kpis.completadas} completadas${kpis.sinResultado > 0 ? ` · ${kpis.sinResultado} sin resultado` : ''}`} />
        <Kpi icon={Wind} tone="info" label="Oximetría" value={kpis.porModo.OXIMETRIA} hint="Mediciones en este modo" />
        <Kpi icon={Droplet} tone="warn" label="Glucosa experimental" value={kpis.porModo.GLUCOSA_EXPERIMENTAL} hint="Mediciones en este modo" />
        <Kpi icon={ChartColumn} label="Experimentales" value={kpis.experimentales} hint="No incluye DEMO ni las sin resultado" />
        <Kpi icon={FlaskConical} tone="warn" label="Datos DEMO" value={kpis.demo} hint={share ?? 'Sintéticos: no son mediciones reales'} />
        <Kpi icon={Signal} tone="ok" label="Con señal válida" value={kpis.conSenalValida} hint="Completadas con lecturas estabilizadas" />
      </KpiGrid>
      {data.truncado && <Alert kind="info">El conjunto es muy grande: se analizaron las 100.000 mediciones más recientes del período. Acotá el período o los filtros.</Alert>}
    </>
  );
}

function Charts({ data, filters }) {
  const grouped = data.filtros.origen === 'TODOS';
  const variable = VARIABLES[data.variable.variable];
  const sexItems = data.sexo.map((b) => ({ label: SEX_LABELS[b.categoria], value: b.pacientes, tone: SEX_TONES[b.categoria], hint: `${b.conMediciones} con mediciones` }));
  const ageItems = data.edades.map((b) => ({ label: b.categoria === 'SIN_INFORMAR' ? 'Sin informar' : b.categoria, value: b.pacientes, secondary: b.conMediciones }));
  const modeRows = Object.keys(MODES).map((mode) => ({
    label: MODES[mode], showDemo: grouped || data.filtros.origen === 'DEMO',
    experimental: data.porModoOrigen.find((i) => i.modo === mode && i.origen === 'EXPERIMENTAL')?.mediciones ?? 0,
    demo: data.porModoOrigen.find((i) => i.modo === mode && i.origen === 'DEMO')?.mediciones ?? 0,
  }));
  const countSeries = [
    ...(data.filtros.origen !== 'DEMO' ? [{ name: 'Experimentales', tone: 'experimental', points: data.evolucion.map((p) => ({ x: p.periodo, y: p.experimentales, n: p.experimentales })) }] : []),
    ...(data.filtros.origen !== 'EXPERIMENTAL' ? [{ name: 'DEMO (sintéticas)', tone: 'demo', dashed: true, points: data.evolucion.map((p) => ({ x: p.periodo, y: p.demo, n: p.demo })) }] : []),
  ];
  const variableSeries = data.variable.series.map((s) => ({
    name: s.origen === 'DEMO' ? 'DEMO (sintético)' : 'Experimental', tone: s.origen === 'DEMO' ? 'demo' : 'experimental', dashed: s.origen === 'DEMO',
    points: s.puntos.map((p) => ({ x: p.periodo, y: p.promedio, min: p.minimo, max: p.maximo, n: p.n })),
  }));
  const quality = data.calidad;
  const qualityItems = quality.rangos.map((r) => ({ label: `${r.desde}–${r.hasta}`, value: r.mediciones }));
  return (
    <div className="an-charts">
      <ChartCard icon={UserRound} title="Pacientes por sexo" empty={data.kpis.pacientesEnAlcance === 0} emptyText="No hay pacientes con estos filtros.">
        <DonutChart title="Pacientes por sexo" items={sexItems} centerLabel="pacientes" />
        <p className="field-hint">Sexo biológico que usa el modelo experimental; «Sin informar» cuenta como categoría y no se completa por suposición.</p>
      </ChartCard>
      <ChartCard icon={UsersRound} title="Pacientes por edad actual" empty={data.kpis.pacientesEnAlcance === 0} emptyText="No hay pacientes con estos filtros.">
        <ColumnChart title="Pacientes por rango de edad actual" items={ageItems} secondaryLabel="con mediciones" />
        <p className="field-hint">Cuenta pacientes únicos. La edad sale de la fecha de nacimiento (o de la edad declarada si no hay fecha).</p>
      </ChartCard>
      <ChartCard icon={FlaskConical} title="Mediciones por modo y origen" empty={data.kpis.totalMediciones === 0} emptyText="No hay mediciones con estos filtros.">
        <SplitBars title="Mediciones por modo y origen" rows={modeRows} />
        <p className="field-hint">Ambos modos pueden registrar SpO₂, frecuencia cardíaca y glucosa: el modo indica cómo se midió, no qué campos tiene.</p>
      </ChartCard>
      <ChartCard icon={Activity} title="Evolución de las mediciones" empty={data.evolucion.length === 0} emptyText="No hay mediciones en el período.">
        <SeriesChart title="Cantidad de mediciones por período" unit="" series={countSeries} granularity={filters.granularidad} decimals={0} />
      </ChartCard>
      <ChartCard icon={ChartColumn} title={`${variable.label}${variable.unit ? ` (${variable.unit})` : ''}`} className="an-wide"
        empty={data.variable.series.every((s) => s.resumen.n === 0)} emptyText="No hay observaciones con este dato en el período.">
        <SeriesChart title={`${variable.label} por período`} unit={variable.unit} series={variableSeries} granularity={filters.granularidad} width={980} height={250} />
        <ul className="an-stats" aria-label="Estadísticas de la variable">
          {data.variable.series.map((s) => (
            <li key={s.origen} className={isDemo(s.origen) ? 'is-demo' : undefined}>
              <b>{isDemo(s.origen) ? 'DEMO (sintético)' : 'Experimental'}</b>
              <span>{s.resumen.n} observaciones válidas</span>
              <span>Promedio {num(s.resumen.promedio, variable.unit)}</span>
              <span>Mín. {num(s.resumen.minimo, variable.unit)} · Máx. {num(s.resumen.maximo, variable.unit)}</span>
            </li>
          ))}
        </ul>
        <p className="field-hint">Los promedios usan solo mediciones con este dato; las banda clara es el mínimo–máximo de cada período. No se promedian DEMO y experimentales.</p>
      </ChartCard>
      {data.segmentacion.length > 0 && (
        <ChartCard icon={ListFilter} title={`${variable.label} según ${SEGMENTS[data.filtros.segmentar].toLowerCase()}`} className="an-wide">
          <div className="an-table-wrap">
            <table className="an-table">
              <caption className="sr-only">Estadística de {variable.label} por {SEGMENTS[data.filtros.segmentar].toLowerCase()}</caption>
              <thead>
                <tr><th scope="col">{SEGMENTS[data.filtros.segmentar]}</th><th scope="col">Origen</th><th scope="col">Mediciones</th><th scope="col">Obs. válidas</th>
                  <th scope="col">Promedio</th><th scope="col">Mín.</th><th scope="col">Máx.</th></tr>
              </thead>
              <tbody>
                {data.segmentacion.map((row) => (
                  <tr key={`${row.categoria}-${row.origen}`} className={isDemo(row.origen) ? 'is-demo' : undefined}>
                    <th scope="row">{segmentLabel(data.filtros.segmentar, row.categoria)}</th>
                    <td>{isDemo(row.origen) ? <Badge tone="warning">DEMO</Badge> : 'Experimental'}</td>
                    <td>{row.mediciones}</td><td>{row.n}</td>
                    <td>{num(row.promedio, variable.unit)}</td><td>{num(row.minimo, variable.unit)}</td><td>{num(row.maximo, variable.unit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="field-hint">El promedio usa solo mediciones completadas con este dato (columna «Obs. válidas»). DEMO y experimental van en filas separadas.</p>
        </ChartCard>
      )}
      <ChartCard icon={Signal} title="Calidad de señal" empty={data.kpis.totalMediciones === 0} emptyText="No hay mediciones con estos filtros.">
        {quality.conValor > 0 ? <ColumnChart title="Mediciones por rango de calidad de señal registrada" items={qualityItems} /> : (
          <p className="field-hint">Ninguna de estas mediciones guardó calidad de señal: las que llegan del equipo (experimentales y DEMO) no la informan, y no se inventa.</p>
        )}
        <p className="field-hint">{quality.conValor} con calidad registrada · {quality.sinInformar} sin informar. El modelo no define umbrales: los rangos parten el intervalo observado.</p>
        {quality.lecturas.length > 0 && (
          <>
            <h4 className="op-subchart">Lecturas estabilizadas por medición</h4>
            <StackedColumnChart title="Lecturas estabilizadas por medición" height={180} categories={quality.lecturas.map((bin) => ({
              label: String(bin.lecturas), parts: [{ label: 'Experimentales', value: bin.experimentales, tone: 'experimental' }, { label: 'DEMO (sintéticas)', value: bin.demo, tone: 'demo' }],
            }))} legend={[{ label: 'Experimentales', tone: 'experimental' }, { label: 'DEMO (sintéticas)', tone: 'demo' }]} />
            <p className="field-hint">{quality.conLecturas} con lecturas estabilizadas: cuántas lecturas estables registró el equipo al guardar. No es la calidad de señal.</p>
          </>
        )}
      </ChartCard>
      <ChartCard icon={Droplet} title="Alimentación registrada" empty={data.kpis.totalMediciones === 0} emptyText="No hay mediciones con estos filtros.">
        <ColumnChart title="Mediciones por condición de última comida" items={data.alimentacion.map((a) => ({ label: FOOD_LABELS[a.categoria], value: a.mediciones }))} />
        <p className="field-hint">«Sin informar» no se interpreta como ayuno.</p>
      </ChartCard>
      <ChartCard icon={CircleAlert} title="Datos faltantes" empty={data.kpis.completadas === 0} emptyText="No hay mediciones completadas con estos filtros.">
        <ul className="an-missing" aria-label="Datos faltantes en mediciones completadas">
          {data.kpis.faltantes.map((m) => (
            <li key={m.campo}>
              <span>{MISSING_LABELS[m.campo] ?? m.campo}</span>
              <span className="an-split-track"><span style={{ width: `${m.sobre ? (m.sinDato / m.sobre) * 100 : 0}%`, background: '#b8bdc9' }} /></span>
              <b>{m.sinDato} de {m.sobre}</b>
            </li>
          ))}
        </ul>
        <p className="field-hint">Sin dato no se cuenta como cero: esas mediciones siguen aportando a las demás estadísticas.</p>
      </ChartCard>
    </div>
  );
}

function PatientDetail({ data, institution, handleOperationError }) {
  const detail = data.paciente;
  const id = detail.idPerfilMedicion;
  const loadMeasurements = useCallback((filters) => institutionsApi.getPatientMeasurements(institution.idInstitucion, id, filters), [institution.idInstitucion, id]);
  const points = detail.puntos;
  const series = (field) => ['EXPERIMENTAL', 'DEMO'].map((origin) => ({
    name: origin === 'DEMO' ? 'DEMO (sintético)' : 'Experimental', tone: origin === 'DEMO' ? 'demo' : 'experimental', dashed: origin === 'DEMO',
    points: points.filter((p) => p.origen === origin && p.estado === 'COMPLETADA' && p[field] !== null && p[field] !== undefined).map((p) => ({ x: p.fecha, y: p[field], n: 1 })),
  })).filter((item) => item.points.length > 0);
  const charts = [['spo2', 'SpO₂', '%'], ['frecuenciaCardiaca', 'Frecuencia cardíaca', 'lpm'], ['glucosaDispositivo', 'Glucosa del dispositivo', 'mg/dL'],
    ['glucosaEstimada', 'Glucosa estimada con matriz', 'mg/dL'], ['indiceOptico', 'Índice óptico', '']];
  const compared = points.filter((p) => p.referencia);
  const foods = ['AYUNO', 'POSTPRANDIAL', 'NO_INFORMADA'].map((c) => ({ label: FOOD_LABELS[c], value: points.filter((p) => p.alimentacion === c).length }));
  return (
    <section className="an-patient" aria-labelledby="an-detalle">
      <div className="panel">
        <div className="panel-head">
          <div className="panel-title">
            <span className="panel-icon" aria-hidden="true"><UserRound size={22} /></span>
            <div><h2 id="an-detalle">{patientName(detail)}</h2><p>{detail.identificadorPseudonimo}</p></div>
          </div>
          <Link to={`../${id}`} relative="path" className="btn btn-outline"><FileText size={16} aria-hidden="true" /> Ver ficha</Link>
        </div>
        <dl className="data-list" aria-label="Datos del paciente">
          <div><dt>Fecha de nacimiento</dt><dd className={detail.fechaNacimiento ? undefined : 'is-empty'}>{detail.fechaNacimiento ? formatDate(detail.fechaNacimiento) : 'Sin informar'}</dd></div>
          <div><dt>Edad actual</dt><dd className={detail.edadActual === null ? 'is-empty' : undefined}>{detail.edadActual === null ? 'Sin informar' : `${detail.edadActual} años`}</dd></div>
          <div><dt>Sexo (biológico, para el modelo)</dt><dd className={detail.sexoModelo ? undefined : 'is-empty'}>{SEX_LABELS[detail.sexoModelo ?? 'SIN_INFORMAR']}</dd></div>
          <div><dt>Mediciones con los filtros</dt><dd>{points.length}{detail.puntosTruncados ? ' (las más recientes)' : ''}</dd></div>
        </dl>
      </div>
      {points.length === 0 ? (
        <Alert kind="info">Este paciente no tiene mediciones con los filtros activos.</Alert>
      ) : (
        <div className="an-charts">
          {charts.map(([field, title, unit]) => {
            const items = series(field);
            return (
              <ChartCard key={field} icon={ChartColumn} title={`${title}${unit ? ` (${unit})` : ''}`} empty={items.length === 0} emptyText="Ninguna medición registró este dato.">
                <SeriesChart title={`${title} del paciente`} unit={unit} series={items} granularity="dia" decimals={field === 'indiceOptico' ? 4 : 1} />
              </ChartCard>
            );
          })}
          <ChartCard icon={Droplet} title="Alimentación registrada">
            <ColumnChart title="Mediciones del paciente por condición de última comida" items={foods} />
          </ChartCard>
        </div>
      )}
      {data.filtros.compararMatriz && (
        <section className="panel" aria-labelledby="an-matriz">
          <h3 id="an-matriz">Comparación con la matriz experimental</h3>
          {detail.resumenMatriz && detail.resumenMatriz.comparadas > 0 && (
            <ul className="an-stats" aria-label="Resumen de la comparación con la matriz">
              <li><b>{detail.resumenMatriz.comparadas} {detail.resumenMatriz.comparadas === 1 ? 'medición comparada' : 'mediciones comparadas'}</b>{detail.resumenMatriz.limitado && <span>Las más recientes (tope por consulta)</span>}</li>
              <li><span>Dentro del intervalo: {detail.resumenMatriz.dentro}</span><span>Por debajo: {detail.resumenMatriz.porDebajo} · Por encima: {detail.resumenMatriz.porEncima}</span></li>
              <li><span>Sin referencia aplicable: {detail.resumenMatriz.sinReferencia}</span></li>
            </ul>
          )}
          {compared.length === 0 ? <p className="field-hint">No hay mediciones de glucosa experimental con matriz en el período.</p> : (
            <ul className="an-matrix" aria-label="Comparación con la matriz">
              {compared.map((p) => (
                <li key={p.idMedicion}>
                  <span>{formatDateTime(p.fecha)}</span>
                  <b>{num(p.glucosaDispositivo ?? p.glucosaEstimada, 'mg/dL')}</b>
                  <span>{p.referencia.minimo === null ? 'Sin intervalo determinado' : `Intervalo ${p.referencia.minimo}–${p.referencia.maximo} mg/dL`}{p.referencia.matriz ? ` · ${p.referencia.matriz}` : ''}</span>
                  <span>{p.referencia.posicion ? POSITION_LABELS[p.referencia.posicion] : (p.referencia.motivo ?? 'Sin comparación')}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="field-hint">Es una comparación matemática con el intervalo de la matriz, no un diagnóstico clínico. Solo se aplica a mediciones en modo glucosa experimental.</p>
        </section>
      )}
      <MeasurementHistory loadPage={loadMeasurements} detailPath={(measurementId) => `/app/instituciones/${institution.idInstitucion}/pacientes/${id}/mediciones/${measurementId}`}
        handleOperationError={handleOperationError} emptyText="Todavía no hay mediciones registradas para este paciente." />
    </section>
  );
}

export function PatientAnalyticsPage() {
  const { institution, handleOperationError } = useOutletContext();
  const [searchParams] = useSearchParams();
  const [filters, setFilters] = useState(() => initialFilters(searchParams));
  const [state, setState] = useState({ data: null, error: '', loading: true });
  const [patientsList, setPatientsList] = useState([]);
  const allowed = institution.rolInstitucion === 'OPERADOR' && can(institution, 'GESTIONAR_PACIENTES');
  const params = useMemo(() => requestParams(filters), [filters]);

  useEffect(() => {
    if (!allowed) return undefined;
    let active = true;
    institutionsApi.listPatients(institution.idInstitucion, { soloMios: true, estado: 'ACTIVO', tamanioPagina: 50 }).then(
      (page) => active && setPatientsList(page.items), () => {},
    );
    return () => { active = false; };
  }, [allowed, institution.idInstitucion]);

  useEffect(() => {
    if (!allowed) return undefined;
    let active = true;
    setState((current) => ({ ...current, loading: true }));
    dashboardApi.getPatientAnalytics(institution.idInstitucion, params).then(
      (data) => active && setState({ data, error: '', loading: false }),
      (error) => active && setState({ data: null, error: handleOperationError(error), loading: false }),
    );
    return () => { active = false; };
  }, [allowed, institution.idInstitucion, params, handleOperationError]);

  if (!allowed) {
    return (
      <section className="panel">
        <EmptyState icon={UsersRound} title="Análisis disponible para el operador responsable"
          description="Las mediciones individuales solo las analiza el operador a cargo de cada paciente. Propietario y moderador no acceden por su rol." />
      </section>
    );
  }
  const { data, error, loading } = state;
  return (
    <div className="an-page">
      <header className="an-header">
        <h2>Análisis de pacientes y mediciones</h2>
        <p>Resumen de los pacientes que tenés a cargo hoy. Los datos DEMO son sintéticos y se muestran aparte.</p>
        <p className="field-hint an-scope">
          Alcance: las mediciones de tus pacientes asignados hoy, las haya hecho vos u otro operador. El <Link to=".." relative="path">panel</Link> cuenta, en cambio, las
          que iniciaste vos en el período (incluso de pacientes que ya transferiste), por eso sus totales pueden diferir. Por defecto se incluyen todas las fuentes y todos los estados.
        </p>
      </header>
      <Filters filters={filters} setFilters={setFilters} patientsList={patientsList} ageRanges={state.data?.rangosEdad ?? DEFAULT_AGE_RANGES} onReset={() => setFilters(DEFAULTS)} />
      {error && <Alert>{error}</Alert>}
      {!data && !error && <p className="field-hint" role="status">Calculando el análisis…</p>}
      {data && (
        <div aria-busy={loading}>
          <OriginNotice data={data} filters={filters} onShowAll={() => setFilters((current) => ({ ...current, origen: 'TODOS', pagina: 1 }))} />
          <KpiSection data={data} />
          <Charts data={data} filters={filters} />
          {data.paciente && <PatientDetail key={data.paciente.idPerfilMedicion} data={data} institution={institution} handleOperationError={handleOperationError} />}
        </div>
      )}
    </div>
  );
}
