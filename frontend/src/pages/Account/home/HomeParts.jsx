// Piezas de Inicio: fecha y hora, aviso de bienestar, últimos valores y evolución reciente.
// Nada se calcula ni se clasifica acá: los valores llegan de las mediciones guardadas y se muestran con su origen (experimental o DEMO).

import {
  ArrowRight,
  CalendarDays,
  ChartColumn,
  Clock,
  Droplet,
  HeartPulse,
  Layers,
  Wind,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { OriginBadge } from "../../../components/Badge.jsx";
import { EmptyState } from "../../../components/EmptyState.jsx";
import { PointDetail } from "../../../components/PointDetail.jsx";
import { TabPanel, Tabs } from "../../../components/Tabs.jsx";

import { DonutChart } from "../../../components/AnalyticsCharts.jsx";
import { EvolutionChart } from "../../../components/EvolutionChart.jsx";
import { StackedBarChart } from "../../../components/StackedBarChart.jsx";
import {
  GROUPING_LABELS,
  HOME_PERIODS,
  SEMAFORO,
  SIN_REGLA_COLOR,
  VARIABLES,
  aggregateSeries,
  countByBlock,
  countGranularity,
  describePoint,
  formatValue,
  glucoseSemaforo,
  groupingOptions,
  otherValues,
  periodWindow,
  pointWhen,
  seriesFor,
  shortBlockLabel,
  variableName,
} from "../measurements/evolutionModel.js";
import { MODES, formatDateTime } from "../groups/groupFormat.js";

const DISMISS_KEY = "glucolume.home.bienestar.oculto";

const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);

/** «Miércoles, 15 de enero de 2026» y la hora, con el reloj del dispositivo (se actualiza cada medio minuto). */
export function DateBlock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(timer);
  }, []);
  const date = capitalize(
    now.toLocaleDateString("es-AR", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    }),
  );
  const time = now.toLocaleTimeString("es-AR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return (
    <div className="home-date" aria-label="Fecha y hora actuales">
      <CalendarDays size={28} aria-hidden="true" />
      <div>
        <b>{date}</b>
        <small>{time}</small>
      </div>
    </div>
  );
}

/** Aviso amable que se puede cerrar; si lo cerrás no vuelve a aparecer en este navegador (solo una comodidad, no un dato de la cuenta). */
export function WellbeingNotice() {
  const [hidden, setHidden] = useState(() => {
    try {
      return localStorage.getItem(DISMISS_KEY) === "1";
    } catch {
      return false;
    }
  });
  if (hidden) return null;
  function close() {
    setHidden(true);
    try {
      localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      /* sin almacenamiento: se oculta solo en esta visita */
    }
  }
  return (
    <aside className="home-notice" aria-label="Tu bienestar nos importa">
      <span className="home-notice-icon">
        <HeartPulse size={28} aria-hidden="true" />
      </span>
      <div>
        <b>Tu bienestar nos importa</b>
        <p>
          Mantené tus mediciones al día para un mejor seguimiento de tu salud.
        </p>
      </div>
      <button
        type="button"
        className="home-notice-close"
        onClick={close}
        aria-label="Cerrar el aviso"
      >
        <X size={20} aria-hidden="true" />
      </button>
    </aside>
  );
}

/** «Hoy, 15:28», «Ayer, 09:10» o la fecha completa, a partir de la fecha y hora que guarda el backend (sin zona). */
export function whenText(stamp, now = new Date()) {
  if (!stamp) return "";
  const [date] = String(stamp).split("T");
  const pad = (value) => String(value).padStart(2, "0");
  const iso = (day) =>
    `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const time = formatDateTime(stamp).split(" ")[1] ?? "";
  if (date === iso(now)) return `Hoy, ${time}`;
  if (date === iso(yesterday)) return `Ayer, ${time}`;
  return formatDateTime(stamp);
}

const KPIS = [
  {
    key: "glucosa",
    label: "Última glucosa",
    unit: "mg/dL",
    icon: Droplet,
    tone: "glucose",
    decimals: 0,
  },
  {
    key: "frecuenciaCardiaca",
    label: "Última frecuencia cardíaca",
    unit: "lpm",
    icon: HeartPulse,
    tone: "heart",
    decimals: 0,
  },
  {
    key: "spo2",
    label: "Última SpO₂",
    unit: "%",
    icon: Wind,
    tone: "lungs",
    decimals: 1,
  },
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
            <span className={`home-kpi-icon is-${tone}`}>
              <Icon size={30} aria-hidden="true" />
            </span>
            <div className="home-kpi-body">
              <small>{label}</small>
              {loading ? (
                <b className="is-empty">Cargando…</b>
              ) : item ? (
                <b>
                  {item.value.toLocaleString("es-AR", {
                    maximumFractionDigits: decimals,
                  })}{" "}
                  {unit && <span>{unit}</span>}
                </b>
              ) : (
                <b className="is-empty">Sin datos</b>
              )}
            </div>
            <div className="home-kpi-foot">
              <span className="home-kpi-when">
                <Clock size={18} aria-hidden="true" />{" "}
                {item ? whenText(item.when) : "Todavía sin mediciones"}
              </span>
              {item && (
                <OriginBadge origin={item.demo ? "DEMO" : "EXPERIMENTAL"}>
                  {item.demo ? "DEMO (prueba)" : "Experimental"}
                </OriginBadge>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

const TABS = ["glucosa", "frecuenciaCardiaca", "spo2"];

/** Detalle del punto elegido en Inicio: variable, valor, fecha, hora, origen y resumen (igual que en «Mis mediciones»). */
function HomePointDetail({ selection, points }) {
  const { point, variable } = selection;
  const spec = VARIABLES[variable];
  const bucket = point.bucket;
  const when = pointWhen(point);
  const raw =
    !bucket && point.count === 1
      ? points.find((item) => item.idMedicion === point.ids[0])
      : null;
  return (
    <PointDetail
      variable={variableName(variable, point.demo)}
      value={formatValue(
        point.value,
        bucket ? Math.max(spec.decimals, 1) : spec.decimals,
      )}
      unit={spec.unit}
      date={when.date}
      time={when.time}
      demo={point.demo}
      summary={[
        !bucket && (MODES[point.mode] ?? null),
        point.semaforo && `Semáforo: ${SEMAFORO[point.semaforo].label}`,
        describePoint(point, variable),
      ]
        .filter(Boolean)
        .join(" · ")}
      others={otherValues(raw, variable)}
    />
  );
}

/** Un gráfico de una variable con las mediciones del período; cada punto es una medición guardada (o un promedio por hora/día/semana/mes). */
function VariableChart({
  variable,
  points,
  chart,
  days,
  grouping,
  selected,
  onSelect,
  onClear,
}) {
  const spec = VARIABLES[variable];
  const series = aggregateSeries(
    seriesFor(points, variable, "TODOS"),
    grouping,
  );
  const domain = chart
    ? periodWindow(chart, { dias: days }, series)
    : undefined;
  if (series.length === 0) {
    return (
      <EmptyState
        variant="framed"
        headingLevel={0}
        title={`Sin datos de ${spec.label.toLowerCase()} en este período.`}
      />
    );
  }
  // Semáforo de la glucosa experimental (como en «Mis mediciones»): color por medición y zonas del intervalo. Con promedios no hay un color por punto.
  const semaforo =
    variable === "glucosa" && grouping === "MEDICION"
      ? glucoseSemaforo(series)
      : null;
  return (
    <>
      {semaforo && (
        <div className="evo-glucose-bar">
          {semaforo.rangesVary && (
            <p className="field-hint">
              Hay mediciones con distintos intervalos de referencia: el gráfico
              muestra el de la más reciente.
            </p>
          )}
          <ul className="evo-semaforo-legend" aria-label="Resumen del semáforo">
            {Object.entries(SEMAFORO).map(([key, info]) => (
              <li key={key}>
                <i style={{ background: info.color }} aria-hidden="true" />{" "}
                {info.label} <b>{semaforo.counts[key]}</b>
              </li>
            ))}
            {semaforo.sinRegla > 0 && (
              <li>
                <i style={{ background: SIN_REGLA_COLOR }} aria-hidden="true" />{" "}
                Sin regla <b>{semaforo.sinRegla}</b>
              </li>
            )}
          </ul>
        </div>
      )}
      <EvolutionChart
        title={spec.label}
        demoTitle={spec.demoLabel}
        series={series}
        unit={spec.unit}
        decimals={spec.decimals}
        color={spec.color}
        dotColor={semaforo?.dotColor}
        range={semaforo?.range ?? null}
        domain={domain}
        granularity={grouping}
        selectedKey={selected?.point.key}
        onSelect={onSelect}
      />
      {selected ? (
        <>
          <HomePointDetail selection={selected} points={points} />
          <button type="button" className="btn btn-ghost" onClick={onClear}>
            Volver a la evolución del período
          </button>
        </>
      ) : (
        <p className="field-hint">
          Elegí un punto del gráfico para ver el detalle de esa medición acá
          mismo.
        </p>
      )}
    </>
  );
}

/** Filtros de Inicio (agrupación y período), con el mismo aspecto que la evolución del grupo. El origen no se filtra acá: Inicio muestra ambos. */
export function HomeFilters({ days, onDaysChange, grouping, onGroupingChange }) {
  return (
    <section className="gd-evo-filters" aria-label="Filtros del gráfico">
      <label className="gd-evo-filter">
        <span className="gd-evo-filter-icon"><Layers size={22} aria-hidden="true" /></span>
        <span className="gd-evo-filter-body">
          <span>Agrupación</span>
          <select className="field-input field-select" aria-label="Agrupación de la evolución" value={grouping}
            onChange={(event) => onGroupingChange(event.target.value)}>
            {groupingOptions(days).options.map((key) => <option key={key} value={key}>{GROUPING_LABELS[key]}</option>)}
          </select>
        </span>
      </label>
      <label className="gd-evo-filter">
        <span className="gd-evo-filter-icon"><CalendarDays size={22} aria-hidden="true" /></span>
        <span className="gd-evo-filter-body">
          <span>Período</span>
          <select className="field-input field-select" aria-label="Período de la evolución" value={days}
            onChange={(event) => onDaysChange(Number(event.target.value))}>
            {HOME_PERIODS.map((period) => <option key={period.days} value={period.days}>{period.name}</option>)}
          </select>
        </span>
      </label>
    </section>
  );
}

/** Evolución reciente: pestañas por variable. Pasá el cursor por un punto para ver el valor y la hora. */
export function RecentEvolution({ chart, days, grouping }) {
  const [variable, setVariable] = useState("glucosa");
  const [selected, setSelected] = useState(null); // { variable, point }: el punto elegido con clic o Enter
  const points = chart?.puntos ?? [];
  const hasAny = TABS.some((key) => seriesFor(points, key, "TODOS").length > 0);
  // Cambiar período o agrupación rehace los puntos: la selección anterior ya no corresponde.
  useEffect(() => setSelected(null), [days, grouping]);
  const changeVariable = (key) => {
    setVariable(key);
    setSelected(null);
  };
  const shownSelection = selected?.variable === variable ? selected : null;
  return (
    <section className="home-card" aria-labelledby="home-evolucion">
      <header className="home-card-head">
        <span className="home-card-icon">
          <ChartColumn size={28} aria-hidden="true" />
        </span>
        <div>
          <h2 id="home-evolucion">Evolución reciente</h2>
          <p>
            Tus mediciones guardadas (la glucosa es una estimación
            experimental).
          </p>
        </div>
      </header>
      <Tabs
        label="Variable a graficar"
        idBase="home-evo"
        variant="pill"
        value={variable}
        onChange={changeVariable}
        items={TABS.map((key) => ({ key, label: VARIABLES[key].label }))}
      />
      <TabPanel
        idBase="home-evo"
        value={variable}
        className="ui-stack ui-stack--card"
      >
        {chart === undefined ? (
          <EmptyState
            variant="framed"
            headingLevel={0}
            role="status"
            title="Cargando tus mediciones…"
          />
        ) : !hasAny ? (
          <EmptyState
            variant="framed"
            headingLevel={0}
            title="No hay mediciones en este período."
            description="Probá con otro período o hacé una nueva medición."
            action={
              <Link to="/app/mediciones/nueva" className="btn btn-outline">
                Nueva medición
              </Link>
            }
          />
        ) : (
          <VariableChart
            variable={variable}
            points={points}
            chart={chart}
            days={days}
            grouping={grouping}
            selected={shownSelection}
            onSelect={(point) => setSelected({ variable, point })}
            onClear={() => setSelected(null)}
          />
        )}
      </TabPanel>
      {hasAny && chart !== undefined && (
        <Link to="/app/mediciones/historial" className="home-more">
          Ver Historial de mediciones{" "}
          <ArrowRight size={18} aria-hidden="true" />
        </Link>
      )}
    </section>
  );
}

const DEVICE_CATEGORIES = [
  { key: "oximetria", label: "Oximetría", color: "#0f8b8d" },
  { key: "glucosa", label: "Glucosa (experimental)", color: "#d98200" },
];
const MEAL_CATEGORIES = [
  { key: "ayuno", label: "En ayunas", color: "#2f6fb5" },
  { key: "postprandial", label: "Después de comer", color: "#7a5cc2" },
  { key: "sinInformar", label: "Sin informar", color: "#9aa3b5" },
];

/** Semáforo de las glucosas del período (cada medición, DEMO incluida): cuántas quedaron en cada zona de la matriz vigente. */
function GlucoseSemaforoKpi({ series }) {
  const { counts, sinRegla } = glucoseSemaforo(series);
  const items = [
    {
      label: "Muy alto",
      tone: "semaforoRojo",
      value: counts.ROJO,
      hint: "por encima del intervalo",
    },
    {
      label: "Revisar",
      tone: "semaforoAmarillo",
      value: counts.AMARILLO,
      hint: "al borde o por debajo",
    },
    {
      label: "Está bien",
      tone: "semaforoVerde",
      value: counts.VERDE,
      hint: "dentro del intervalo",
    },
    {
      label: "Sin regla",
      tone: "semaforoSinRegla",
      value: sinRegla,
      hint: "sin intervalo en la matriz",
    },
  ];
  return (
    <article
      className="home-mini-kpi home-kpi-semaforo"
      aria-label="Semáforo de glucosa del período"
    >
      <h3>Semáforo de glucosa</h3>
      {series.length === 0 ? (
        <p className="field-hint">Sin mediciones de glucosa en este período.</p>
      ) : (
        <DonutChart
          title="Semáforo de glucosa"
          items={items}
          centerLabel="mediciones"
        />
      )}
    </article>
  );
}

/** Promedio de una variable en el período. Experimental y DEMO no se promedian juntas: si hay experimentales, se promedian solo esas. */
function AverageKpi({ name, unit, series }) {
  const experimental = series.filter((point) => !point.demo);
  const demo = series.filter((point) => point.demo);
  const useDemo = experimental.length === 0 && demo.length > 0;
  const group = useDemo ? demo : experimental;
  const average = group.length
    ? group.reduce((sum, point) => sum + point.value, 0) / group.length
    : null;
  const noun = group.length === 1 ? "medición" : "mediciones";
  return (
    <article
      className="home-mini-kpi"
      aria-label={`Promedio de ${name} del período`}
    >
      <h3>Promedio de {name}</h3>
      {average === null ? (
        <b className="is-empty">Sin datos</b>
      ) : (
        <b>
          {formatValue(average, 1)} <span>{unit}</span>
        </b>
      )}
      <small>
        {average === null
          ? `No hay mediciones de ${name} en este período.`
          : `${useDemo ? "Prueba DEMO (simulada)" : "Experimental"}: promedio de ${group.length} ${noun}.`}
        {!useDemo &&
          demo.length > 0 &&
          ` ${demo.length} ${demo.length === 1 ? "prueba DEMO no entra" : "pruebas DEMO no entran"} en el promedio.`}
      </small>
    </article>
  );
}

/** Cuántas mediciones fueron con oxímetro o con glucosa, y en qué condición de comida, por bloque de tiempo del mismo período. */
export function MeasurementMix({ chart, days, grouping }) {
  const granularity = countGranularity(days, grouping);
  const window = periodWindow(chart, { dias: days }, []);
  const blocks = chart
    ? countByBlock(chart.puntos ?? [], granularity, window)
    : [];
  const total = blocks.reduce((sum, block) => sum + block.total, 0);
  const glucoseSeries = chart
    ? seriesFor(chart.puntos ?? [], "glucosa", "TODOS")
    : [];
  const heartSeries = chart
    ? seriesFor(chart.puntos ?? [], "frecuenciaCardiaca", "TODOS")
    : [];
  const spo2Series = chart
    ? seriesFor(chart.puntos ?? [], "spo2", "TODOS")
    : [];
  const labelFor = (block) => shortBlockLabel(block.start, granularity);
  const describeBlock = (block, categories) =>
    `${labelFor(block)}: ${block.total} ${block.total === 1 ? "medición" : "mediciones"}, ${
      categories
        .filter((category) => block[category.key] > 0)
        .map(
          (category) =>
            `${block[category.key]} ${category.label.toLowerCase()}`,
        )
        .join(", ") || "ninguna"
    }`;
  return (
    <section className="home-card" aria-labelledby="home-mezclas">
      <header className="home-card-head">
        <span className="home-card-icon">
          <ChartColumn size={28} aria-hidden="true" />
        </span>
        <div>
          <h2 id="home-mezclas">Cómo fueron tus mediciones</h2>
          <p>
            Cantidad por tipo de medición y por condición de comida. Agrupado{" "}
            {GROUPING_LABELS[granularity].toLowerCase()}.
          </p>
        </div>
      </header>
      {chart === undefined ? (
        <EmptyState
          variant="framed"
          headingLevel={0}
          role="status"
          title="Cargando tus mediciones…"
        />
      ) : total === 0 ? (
        <EmptyState
          variant="framed"
          headingLevel={0}
          title="No hay mediciones en este período."
          description="Probá con otro período o hacé una nueva medición."
        />
      ) : (
        <>
          <div className="home-kpi-row">
            <GlucoseSemaforoKpi series={glucoseSeries} />
            <AverageKpi name="glucosa" unit="mg/dL" series={glucoseSeries} />
            <AverageKpi
              name="frecuencia cardíaca"
              unit="lpm"
              series={heartSeries}
            />
            <AverageKpi name="SpO₂" unit="%" series={spo2Series} />
          </div>
          <div className="home-mix">
            <StackedBarChart
              title="Oximetría y glucosa"
              categories={DEVICE_CATEGORIES}
              blocks={blocks}
              labelFor={labelFor}
              describe={(block) => describeBlock(block, DEVICE_CATEGORIES)}
            />
            <StackedBarChart
              title="Condición de comida"
              categories={MEAL_CATEGORIES}
              blocks={blocks}
              labelFor={labelFor}
              describe={(block) => describeBlock(block, MEAL_CATEGORIES)}
            />
          </div>
        </>
      )}
    </section>
  );
}
