// Dashboard personal (cuenta individual): encabezado con los accesos principales, última medición registrada, últimos valores, accesos
// rápidos (dispositivo, perfil, historial), «Evolución de mis mediciones» (gráficos históricos interactivos), mediciones recientes y
// sección de pruebas DEMO de MI perfil.
// Todo sale de la base real (GET /measurements/dashboard y GET /measurements/evolution); se vuelve a consultar al entrar, así que una
// medición recién guardada aparece sin pasar por el historial.
//
// Dos conjuntos distintos, sin mezclarlos:
//   · Indicadores, promedios y tendencias: solo mediciones EXPERIMENTALES (las pruebas DEMO nunca los alimentan).
//   · «Última medición registrada», «Mediciones recientes» y «Pruebas DEMO»: todo lo guardado, con las DEMO claramente identificadas.

import {
  ChevronRight,
  Droplets,
  HeartPulse,
  History,
  Link2,
  Monitor,
  Plus,
  Settings,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import * as acquisitionApi from "../../../api/acquisitionApi.js";
import * as dashboardApi from "../../../api/dashboardApi.js";
import * as measurementsApi from "../../../api/measurementsApi.js";
import { Alert } from "../../../components/FormControls.jsx";
import { NO_DATA } from "../../../components/dashboard.jsx";
import { OriginBadge } from "../../../components/Badge.jsx";
import { EmptyState } from "../../../components/EmptyState.jsx";
import { PageHeader } from "../../../components/PageHeader.jsx";
import { DemoBadge } from "./DeviceReadout.jsx";
import { EvolutionPanel } from "./EvolutionPanel.jsx";
import { MeasurementsInfo } from "./MeasurementsInfo.jsx";
import {
  DEVICE_STATES,
  MEALS,
  ORIGINS,
  formatDateTime,
  formatNumber,
} from "./measurementFormat.js";

const MODE_SHORT = { OXIMETRIA: "Oximetría", GLUCOSA_EXPERIMENTAL: "Glucosa" };
const MEDIUMS = { BLUETOOTH: "Bluetooth", USB: "USB" };
const DEVICE_POLL_MS = 10000;

/** Glucosa de una medición guardada y de qué tipo es. La DEMO se rotula como simulada y nunca como indicador experimental. */
function glucoseOf(item) {
  if (item.esDemo && item.glucosaDispositivo !== null)
    return { value: item.glucosaDispositivo, label: "Glucosa DEMO (simulada)" };
  if (item.glucosaEstimada !== null)
    return { value: item.glucosaEstimada, label: "Glucosa estimada" };
  if (
    item.glucosaDispositivo !== null &&
    item.origenGlucosa === "EXPERIMENTAL"
  ) {
    return { value: item.glucosaDispositivo, label: "Glucosa experimental" };
  }
  return null;
}

/** Valores de una medición guardada en una línea. */
function savedValues(item) {
  const parts = [
    `SpO₂ ${formatNumber(item.spo2, "%")}`,
    `Frecuencia cardíaca ${formatNumber(item.frecuenciaCardiaca, "lpm")}`,
  ];
  const glucose = glucoseOf(item);
  if (glucose)
    parts.push(`${glucose.label} ${formatNumber(glucose.value, "mg/dL")}`);
  return parts.join(" · ");
}

function LastSaved({ item }) {
  const glucose = item ? glucoseOf(item) : null;
  return (
    <section
      className="dash-card dash-last"
      aria-label="Última medición registrada"
    >
      <header className="dash-card-head">
        <h2>Última medición registrada</h2>
        {item && (
          <span className="dash-tags">
            <OriginBadge origin="EXPERIMENTAL">
              {MODE_SHORT[item.modoMedicion] ?? item.modoMedicion}
            </OriginBadge>
            {item.esDemo && <DemoBadge />}
          </span>
        )}
      </header>
      {item === null ? (
        <EmptyState variant="inline" headingLevel={0} title="Todavía no guardaste ninguna medición." />
      ) : (
        <>
          <p className="dash-when">{formatDateTime(item.fechaHoraInicio)}</p>
          <div className="dash-last-main">
            <p className="dash-big">
              <b>
                {glucose
                  ? formatNumber(glucose.value)
                  : formatNumber(item.spo2)}
              </b>
              <small>{glucose ? "mg/dL" : "%"}</small>
              <span className="dash-big-label">
                {glucose ? glucose.label : "SpO₂"}
              </span>
            </p>
            <Link
              to={`/app/mediciones/${item.idMedicion}`}
              className="dash-round"
              aria-label="Ver detalle"
            >
              <ChevronRight size={20} aria-hidden="true" />
            </Link>
          </div>
          <p className="dash-last-meta">
            {item.esDemo ? (
              <b>Medición de prueba (DEMO)</b>
            ) : (
              <>
                Origen:{" "}
                {item.origenGlucosa
                  ? (ORIGINS[item.origenGlucosa] ?? item.origenGlucosa)
                  : (MODE_SHORT[item.modoMedicion] ?? item.modoMedicion)}
              </>
            )}
            {item.condicionComida &&
              item.condicionComida !== "NO_INFORMADA" && (
                <span>{MEALS[item.condicionComida]}</span>
              )}
            {item.edadAlMomento !== null &&
              item.edadAlMomento !== undefined && (
                <span>{item.edadAlMomento} años</span>
              )}
          </p>
          <p className="field-hint">{savedValues(item)}</p>
          {item.esDemo && (
            <p className="field-hint">
              Sus valores no se cuentan como indicadores experimentales.
            </p>
          )}
        </>
      )}
    </section>
  );
}

/** Último valor de una variable: el experimental del período o, si solo hay pruebas, la última DEMO identificada como tal. */
function LatestCard({ icon: Icon, label, value, unit, when, demo }) {
  const empty = value === null || value === undefined;
  return (
    <li className="dash-card dash-mini">
      <span className="dash-icon">
        <Icon size={22} aria-hidden="true" />
      </span>
      <small>{label}</small>
      <b>{empty ? NO_DATA : formatNumber(Number(value), unit)}</b>
      {!empty && (
        <span className="field-hint">
          {when ? formatDateTime(when) : ""}
          {demo && (
            <>
              {" "}
              <OriginBadge origin="DEMO">DEMO</OriginBadge>
            </>
          )}
        </span>
      )}
    </li>
  );
}

/** Acceso rápido al dispositivo con su estado real (GET /acquisition/telemetry/status, sin abrir el flujo en vivo). */
function DeviceShortcut() {
  const [status, setStatus] = useState(undefined);
  useEffect(() => {
    let active = true;
    const load = () =>
      acquisitionApi.getTelemetryStatus().then(
        (result) => {
          if (active) setStatus(result);
        },
        () => {
          if (active) setStatus(null);
        },
      );
    load();
    const timer = setInterval(load, DEVICE_POLL_MS);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);
  const state = status
    ? (DEVICE_STATES[status.estado] ?? DEVICE_STATES.SIN_PUENTE)
    : null;
  const bridge = status?.puente;
  return (
    <li>
      <Link to="/app/conectar-dispositivo" className="dash-card dash-shortcut">
        <span className="dash-icon is-neutral">
          <Monitor size={22} aria-hidden="true" />
        </span>
        <span className="dash-shortcut-text">
          <small>Dispositivo</small>
          {state ? (
            <b className={`dash-state ${state.tone}`}>{state.label}</b>
          ) : (
            <b>{status === null ? "Sin información" : "Consultando…"}</b>
          )}
          <span className="field-hint">
            {bridge
              ? `${bridge.puerto ?? "Sin puerto"} · ${MEDIUMS[bridge.medio] ?? bridge.medio}`
              : "Revisá la conexión de tu Arduino"}
          </span>
        </span>
        <ChevronRight size={18} aria-hidden="true" />
      </Link>
    </li>
  );
}

function Shortcut({ to, icon: Icon, title, hint }) {
  return (
    <li>
      <Link to={to} className="dash-card dash-shortcut">
        <span className="dash-icon">
          <Icon size={22} aria-hidden="true" />
        </span>
        <span className="dash-shortcut-text">
          <b>{title}</b>
          <span className="field-hint">{hint}</span>
        </span>
        <ChevronRight size={18} aria-hidden="true" />
      </Link>
    </li>
  );
}

function RecentTable({ items }) {
  return (
    <table className="dash-table" aria-label="Mediciones recientes">
      <thead>
        <tr>
          <th scope="col">Fecha y hora</th>
          <th scope="col">Tipo</th>
          <th scope="col">Valor</th>
          <th scope="col">Condición de comida</th>
          <th scope="col">Frecuencia cardíaca</th>
          <th scope="col">SpO₂</th>
          <th scope="col">
            <span className="sr-only">Acciones</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => {
          const glucose = glucoseOf(item);
          const when = formatDateTime(item.fechaHoraInicio);
          return (
            <tr key={item.idMedicion}>
              <td data-label="Fecha y hora">{when}</td>
              <td data-label="Tipo">
                {MODE_SHORT[item.modoMedicion] ?? item.modoMedicion}
              </td>
              <td data-label="Valor">
                {glucose ? (
                  <>
                    <span className="dash-chip">
                      {formatNumber(glucose.value, "mg/dL")}
                    </span>
                    {item.esDemo && (
                      <>
                        {" "}
                        <DemoBadge />
                      </>
                    )}
                  </>
                ) : (
                  <>
                    {item.esDemo && (
                      <>
                        <DemoBadge />{" "}
                      </>
                    )}
                    <span className="dash-muted">—</span>
                  </>
                )}
              </td>
              <td data-label="Condición de comida">
                {MEALS[item.condicionComida] ?? item.condicionComida}
              </td>
              <td data-label="Frecuencia cardíaca">
                {formatNumber(item.frecuenciaCardiaca, "lpm")}
              </td>
              <td data-label="SpO₂">{formatNumber(item.spo2, "%")}</td>
              <td className="dash-actions-cell">
                <Link
                  to={`/app/mediciones/${item.idMedicion}`}
                  className="btn btn-outline"
                  aria-label={`Ver detalle de la medición del ${when}`}
                >
                  Ver detalle <ChevronRight size={16} aria-hidden="true" />
                </Link>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function PersonalDashboard({ handleOperationError }) {
  const [period, setPeriod] = useState({ dias: 30 });
  const [summary, setSummary] = useState(null);
  const [evolution, setEvolution] = useState(null);
  const [error, setError] = useState("");

  // Resumen general (última medición, recientes, cantidad de pruebas): no depende del período.
  useEffect(() => {
    let active = true;
    dashboardApi.getPersonalDashboard({ dias: 30 }).then(
      (result) => {
        if (active) {
          setSummary(result);
        }
      },
      (loadError) => {
        if (active) {
          setError(handleOperationError(loadError));
          setSummary({ recientes: [], ultimaGuardada: null, pruebasDemo: 0 });
        }
      },
    );
    return () => {
      active = false;
    };
  }, [handleOperationError]);

  // Evolución y tarjetas: se piden TODOS los registros del período; experimentales y DEMO traen estadísticas separadas.
  useEffect(() => {
    let active = true;
    setEvolution(null);
    measurementsApi.getOwnEvolution({ ...period, origen: "TODOS" }).then(
      (result) => {
        if (active) setEvolution(result);
      },
      (loadError) => {
        if (active) {
          setError(handleOperationError(loadError));
          setEvolution({
            puntos: [],
            truncado: false,
            estadisticas: { experimental: null, demo: null },
          });
        }
      },
    );
    return () => {
      active = false;
    };
  }, [JSON.stringify(period), handleOperationError]); // eslint-disable-line react-hooks/exhaustive-deps

  const exp = evolution?.estadisticas.experimental ?? null;
  const noExperimental =
    Boolean(summary) && Boolean(evolution) && (exp?.mediciones ?? 0) === 0;
  // Sin valores experimentales, los «últimos valores» muestran los de la última prueba guardada, identificada como DEMO.
  const saved = summary?.ultimaGuardada ?? null;
  const latest = (variable, savedValue) => {
    const experimental = exp?.[variable].ultimo;
    if (experimental)
      return {
        value: experimental.valor,
        when: experimental.fecha,
        demo: false,
      };
    if (
      evolution &&
      saved?.esDemo &&
      savedValue !== null &&
      savedValue !== undefined
    ) {
      return { value: savedValue, when: saved.fechaHoraInicio, demo: true };
    }
    return { value: null, when: null, demo: false };
  };
  const heart = latest("frecuenciaCardiaca", saved?.frecuenciaCardiaca);
  const oxygen = latest("spo2", saved?.spo2);

  return (
    <section className="dash" aria-labelledby="dashboard-personal">
      <PageHeader
        id="dashboard-personal"
        title="Mi dashboard"
        description="Resumen de tu estado y actividad reciente. Solo tus mediciones."
        actionsClassName="dash-actions"
        actions={(
          <>
            <Link to="/app/mediciones/nueva" className="btn btn-primary">
              <span className="dash-plus">
                <Plus size={14} aria-hidden="true" />
              </span>{" "}
              Nueva medición
            </Link>
            <Link to="/app/conectar-dispositivo" className="btn btn-ghost">
              <Link2 size={16} aria-hidden="true" /> Conectar dispositivo
            </Link>
          </>
        )}
      />
      {error && <Alert>{error}</Alert>}
      {summary === null ? (
        <p className="field-hint" role="status">
          Cargando tu resumen…
        </p>
      ) : (
        <>
          <div className="dash-top">
            <LastSaved item={saved} />
            <ul className="dash-minis" aria-label="Resumen personal">
              <LatestCard
                icon={HeartPulse}
                label="Última frecuencia cardíaca"
                unit="lpm"
                {...heart}
              />
              <LatestCard
                icon={Droplets}
                label="Última SpO₂"
                unit="%"
                {...oxygen}
              />
            </ul>
          </div>
          {noExperimental && (
            <p className="field-hint" role="status">
              Todavía no hay mediciones experimentales en este período.
              {summary.pruebasDemo > 0 && (
                <>
                  {" "}
                  <b>Tenés mediciones de prueba disponibles</b> (
                  {summary.pruebasDemo}): figuran en tus mediciones recientes.
                </>
              )}
            </p>
          )}

          <ul className="dash-shortcuts" aria-label="Accesos rápidos">
            <DeviceShortcut />
            <Shortcut
              to="/app/mediciones/perfil"
              icon={Settings}
              title="Configuración de perfil"
              hint="Edad, sexo, comidas y más"
            />
            <Shortcut
              to="/app/mediciones/historial"
              icon={History}
              title="Historial de mediciones"
              hint="Todas tus mediciones guardadas"
            />
          </ul>

          <EvolutionPanel
            data={evolution}
            period={period}
            onPeriodChange={setPeriod}
          />

          <section
            className="panel dash-recent"
            aria-labelledby="recientes-titulo"
          >
            <div className="panel-head">
              <div className="panel-title">
                <span className="panel-icon">
                  <History size={22} aria-hidden="true" />
                </span>
                <h2 id="recientes-titulo">Mediciones recientes</h2>
              </div>
              <Link to="/app/mediciones/historial" className="dash-link">
                Ver historial completo{" "}
                <ChevronRight size={16} aria-hidden="true" />
              </Link>
            </div>
            {summary.recientes.length === 0 ? (
              <EmptyState variant="inline" headingLevel={0} title="Todavía no hay mediciones recientes." />
            ) : (
              <RecentTable items={summary.recientes} />
            )}
          </section>

          <MeasurementsInfo />
        </>
      )}
    </section>
  );
}
