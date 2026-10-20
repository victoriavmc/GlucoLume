// Dashboards institucionales: general (propietario y moderador), por operador y por paciente. Todo lo calcula FastAPI
// sobre Medicion, acotado a ESTA institución y a los permisos del rol; aquí solo se presenta. El dashboard general es
// agregado y seudonimizado: no lista nombres de pacientes. «Pacientes asignados» (responsable actual) y «mediciones
// realizadas» (quien las inició, histórico) son cosas distintas y se muestran por separado.

import {
  ArrowRight, CalendarDays, CalendarRange, ChartColumn, ChartNoAxesColumn, ChartPie, Clock, Cpu, Download, FileText, Play, Settings, ShieldCheck,
  Smartphone, TrendingUp, Upload, UserRound, Users, UsersRound,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useOutletContext, useParams } from 'react-router-dom';

import * as dashboardApi from '../../../../api/dashboardApi.js';
import { Badge, toneFromClass } from '../../../../components/Badge.jsx';
import { EmptyState } from '../../../../components/EmptyState.jsx';
import { Alert } from '../../../../components/FormControls.jsx';
import { PatientIdentity } from '../../../../components/PatientIdentity.jsx';
import { TrendChart } from '../../../../components/TrendChart.jsx';
import {
  BarList, ChartCard, Kpi, KpiGrid, MetricBlocks, PeriodFilter, periodLabel,
} from '../../../../components/dashboard.jsx';
import { MODES, STATES, formatDateTime, formatNumber, stateBadge } from '../../measurements/measurementFormat.js';
import { ManagementDashboard } from './ManagementPanel.jsx';

function useDashboard(load, deps, handleOperationError) {
  const [period, setPeriod] = useState({ dias: 30 });
  const [state, setState] = useState({ data: null, error: '' });
  useEffect(() => {
    let active = true;
    setState((current) => ({ ...current, data: null }));
    load(period).then(
      (data) => active && setState({ data, error: '' }),
      (error) => active && setState({ data: null, error: handleOperationError(error) }),
    );
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, JSON.stringify(period)]);
  return { ...state, period, setPeriod };
}

/** «3 experimentales · 2 DEMO»: el total incluye las mediciones DEMO (sintéticas), que siempre se informan aparte. */
const splitHint = (experimental, demo, noResult, fallback) => (demo > 0 || noResult > 0
  ? [`${experimental} experimentales`, demo > 0 && `${demo} DEMO`, noResult > 0 && `${noResult} sin resultado`].filter(Boolean).join(' · ') : fallback);

const personName = (person) => [person?.nombre, person?.apellido].filter(Boolean).join(' ') || 'Operador no disponible';

// --- Operador ------------------------------------------------------------------------------------------------------

function PerformedList({ items, label, showOperator, base }) {
  if (items.length === 0) return <p className="field-hint">Sin mediciones para mostrar.</p>;
  return (
    <ul className="member-list-items" aria-label={label}>
      {items.map((item) => (
        <li key={item.idMedicion} className="member-row">
          <span>
            {base
              ? <Link to={`${base}/pacientes/${item.idPerfilMedicion}/mediciones/${item.idMedicion}`} className="op-measure-link"><b>{item.paciente ?? 'Paciente'}</b></Link>
              : <b>{item.paciente ?? 'Paciente'}</b>}
            {' '}· {formatDateTime(item.fechaHoraInicio)}
            <small> · {MODES[item.modoMedicion] ?? item.modoMedicion} · </small>
            {item.esDemo && <><Badge tone="warning">DEMO</Badge>{' '}</>}
            <Badge tone={toneFromClass(stateBadge(item.estadoMedicion))}>{STATES[item.estadoMedicion]}</Badge>
            <br />
            <small>
              SpO₂ {formatNumber(item.spo2, '%')} · Frecuencia cardíaca {formatNumber(item.frecuenciaCardiaca, 'lpm')}
              {item.glucosaEstimada !== null && ` · Glucosa estimada ${formatNumber(item.glucosaEstimada, 'mg/dL')}`}
              {item.dispositivo && ` · ${item.dispositivo}`}
              {showOperator && item.operador && ` · Realizó: ${item.operador}`}
            </small>
          </span>
        </li>
      ))}
    </ul>
  );
}

// --- Dashboard del operador: indicadores, pacientes asignados y tarjetas de trabajo ---------------------------------------

/** «hace 6 horas»: tiempo transcurrido desde un momento (el backend lo guarda como hora de Argentina sin zona). */
function relativeTime(value) {
  if (!value) return undefined;
  const moment = new Date(/(Z|[+-]\d\d:?\d\d)$/.test(value) ? value : `${value}-03:00`).getTime();
  if (Number.isNaN(moment)) return undefined;
  const minutes = Math.max(0, Math.round((Date.now() - moment) / 60000));
  if (minutes < 1) return 'hace instantes';
  if (minutes < 60) return `hace ${minutes} ${minutes === 1 ? 'minuto' : 'minutos'}`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `hace ${hours} ${hours === 1 ? 'hora' : 'horas'}`;
  const days = Math.round(hours / 24);
  return `hace ${days} ${days === 1 ? 'día' : 'días'}`;
}

const initialsOf = (patient) => {
  const letters = [patient.nombre, patient.apellido].filter(Boolean).map((part) => part[0].toUpperCase()).join('');
  return letters || (patient.identificadorPseudonimo ?? 'P').slice(0, 2).toUpperCase();
};

/** Carga del dashboard de un operador («me» = el propio): lo filtra FastAPI por el usuario autenticado. */
export function useOperatorDashboard(institution, idOperador, handleOperationError) {
  const id = institution.idInstitucion;
  return useDashboard((p) => dashboardApi.getOperatorDashboard(id, idOperador, p), [id, idOperador], handleOperationError);
}

/** Encabezado con el período y las tarjetas de indicadores. */
export function OperatorKpiPanel({ institution, data, error, period, setPeriod }) {
  const own = data?.esPropio;
  const transfersPath = `/app/instituciones/${institution.idInstitucion}/pacientes/transferencias`;
  const pendings = (count) => `${count} ${count === 1 ? 'pendiente' : 'pendientes'}`;
  return (
    <section className="panel" aria-labelledby="op-dashboard">
      <div className="inst-dashboard-head">
        <div className="panel-title">
          <span className="panel-icon is-lg" aria-hidden="true"><ChartColumn size={26} /></span>
          <div>
            <h2 id="op-dashboard">{data ? (own ? 'Mi dashboard de trabajo' : `Operador: ${personName(data.operador)}`) : 'Dashboard del operador'}</h2>
            <p>{own === false ? 'Carga de trabajo del operador.' : 'Indicadores de tu actividad como operador.'}</p>
            {data && !data.operador.activo && <p><Badge tone="neutral">Ya no está vinculado/a</Badge></p>}
          </div>
        </div>
        <PeriodFilter value={period} onChange={setPeriod} idPrefix="dash-op" compact />
      </div>
      {error && <Alert>{error}</Alert>}
      {!data && !error && <p className="field-hint" role="status">Cargando el dashboard…</p>}
      {data && (
        <>
          {own ? (
            <>
              <ul className="summary-grid kpi-grid op-kpis is-four" aria-label="Resumen del operador">
                <Kpi icon={Users} label="Pacientes asignados ahora" value={data.pacientesAsignados} hint="pacientes a tu cargo" />
                <Kpi icon={FileText} label="Mediciones realizadas (histórico)" value={data.medicionesRealizadas + (data.medicionesRealizadasDemo ?? 0)}
                  hint={splitHint(data.medicionesRealizadas - (data.medicionesSinResultado ?? 0), data.medicionesRealizadasDemo ?? 0, data.medicionesSinResultado ?? 0, 'en total')} />
                <Kpi icon={TrendingUp} label="Mediciones en el período" value={data.medicionesEnPeriodo + (data.medicionesEnPeriodoDemo ?? 0)}
                  hint={splitHint(data.medicionesEnPeriodo - (data.medicionesEnPeriodoSinResultado ?? 0), data.medicionesEnPeriodoDemo ?? 0, data.medicionesEnPeriodoSinResultado ?? 0, periodLabel(data.periodo))} />
                <Kpi icon={CalendarDays} label="Última actividad" value={data.ultimaActividad ? formatDateTime(data.ultimaActividad) : null} hint={relativeTime(data.ultimaActividad)} />
              </ul>
              <ul className="summary-grid kpi-grid op-kpis is-three" aria-label="Transferencias y dispositivos">
                <Kpi icon={Download} label="Transferencias recibidas" value={data.transferencias.recibidas} hint={pendings(data.transferencias.recibidasPendientes)}
                  to={`${transfersPath}?direccion=recibidas`} />
                <Kpi icon={Upload} label="Transferencias enviadas" value={data.transferencias.enviadas} hint={pendings(data.transferencias.enviadasPendientes)}
                  to={`${transfersPath}?direccion=enviadas`} />
                <Kpi icon={Settings} label="Dispositivos disponibles" value={data.dispositivosDisponibles} hint={data.dispositivosDisponibles === 1 ? 'operativo' : 'operativos'} />
              </ul>
            </>
          ) : (
            <KpiGrid label="Resumen del operador" compact>
            <Kpi icon={Users} label="Pacientes asignados ahora" value={data.pacientesAsignados} hint={own ? 'pacientes a tu cargo' : 'pacientes a su cargo'} />
            <Kpi icon={FileText} label="Mediciones realizadas (histórico)" value={data.medicionesRealizadas} hint="en total" />
            <Kpi icon={TrendingUp} label="Mediciones en el período" value={data.medicionesEnPeriodo} hint={periodLabel(data.periodo)} />
            <Kpi icon={CalendarDays} label="Última actividad" value={data.ultimaActividad ? formatDateTime(data.ultimaActividad) : null} hint={relativeTime(data.ultimaActividad)} />
            {/* Solo el propio operador puede abrir la lista: es quien responde las transferencias recibidas. */}
            <Kpi icon={Download} label="Transferencias recibidas" value={data.transferencias.recibidas} hint={pendings(data.transferencias.recibidasPendientes)}
              to={own ? `${transfersPath}?direccion=recibidas` : undefined} />
            <Kpi icon={Upload} label="Transferencias enviadas" value={data.transferencias.enviadas} hint={pendings(data.transferencias.enviadasPendientes)}
              to={own ? `${transfersPath}?direccion=enviadas` : undefined} />
            <Kpi icon={Settings} label="Dispositivos disponibles" value={data.dispositivosDisponibles} hint={data.dispositivosDisponibles === 1 ? 'operativo' : 'operativos'} />
            </KpiGrid>
          )}
          {own === false && (
            <p className="field-hint">
              Los pacientes asignados son los que tiene a cargo hoy; las mediciones realizadas conservan a quien las inició aunque el paciente se
              haya transferido después.
            </p>
          )}
          {own === false && (
            <p className="field-hint">
              Como supervisión ves la carga de trabajo de este operador. Sus pacientes y sus mediciones individuales las consulta solo el operador
              responsable autorizado.
            </p>
          )}
        </>
      )}
    </section>
  );
}

/** Pacientes que el operador tiene a cargo hoy, con acceso a su dashboard y a medir. */
const PANEL_PATIENTS = 4; // el panel muestra los de actividad más reciente; el listado completo está en «Ver todos mis pacientes»
const PANEL_MEASUREMENTS = 5;

export function AssignedPatientsPanel({ institution, data }) {
  const base = `/app/instituciones/${institution.idInstitucion}`;
  const byRecent = [...data.pacientes].sort((a, b) => (b.ultimaMedicion ?? '').localeCompare(a.ultimaMedicion ?? ''));
  const shown = byRecent.slice(0, PANEL_PATIENTS);
  return (
    <section className="panel" aria-labelledby="op-pacientes">
      <div className="panel-head">
        <div className="panel-title">
          <span className="panel-icon is-lg" aria-hidden="true"><UsersRound size={26} /></span>
          <div>
            <h2 id="op-pacientes">Pacientes asignados</h2>
            <p>Pacientes que tienes actualmente a tu cargo{data.pacientesAsignados > shown.length ? ` · mostrando ${shown.length} de ${data.pacientesAsignados}, por última medición` : ''}.</p>
          </div>
        </div>
        <Link to={`${base}/pacientes?mios=1`} className="btn btn-outline">Ver todos mis pacientes <ArrowRight size={16} aria-hidden="true" /></Link>
      </div>
      {data.pacientes.length === 0 ? (
        <p className="field-hint">No tienes pacientes asignados actualmente.</p>
      ) : (
        <ul className="op-patients" aria-label="Pacientes asignados">
          {shown.map((patient) => {
            const name = [patient.nombre, patient.apellido].filter(Boolean).join(' ');
            return (
              <li key={patient.idPerfilMedicion} className="op-patient">
                <span className="op-avatar" aria-hidden="true">{initialsOf(patient)}</span>
                <div className="op-patient-id">
                  <b>{name || patient.identificadorPseudonimo}</b>
                  <small>Identificador: {patient.identificadorPseudonimo}</small>
                </div>
                <div className="op-patient-last">
                  <span className="op-last-icon" aria-hidden="true"><CalendarDays size={18} /></span>
                  <span>
                    <small>Última medición</small>
                    <b>{patient.ultimaMedicion ? formatDateTime(patient.ultimaMedicion) : 'Sin mediciones completadas'}</b>
                    {patient.ultimaMedicion && (
                      <small>{MODES[patient.ultimaModo] ?? patient.ultimaModo} {patient.ultimaEsDemo ? <Badge tone="warning">DEMO</Badge> : <Badge tone="success">Experimental</Badge>}</small>
                    )}
                  </span>
                </div>
                <span className="member-actions">
                  <Link to={`${base}/pacientes/${patient.idPerfilMedicion}`} className="btn btn-ghost"><FileText size={16} aria-hidden="true" /> Ver ficha</Link>
                  <Link to={`${base}/pacientes/${patient.idPerfilMedicion}/medir`} className="btn btn-outline" aria-label={`Medir a ${name || patient.identificadorPseudonimo}`}>
                    <Play size={16} aria-hidden="true" /> Medir
                  </Link>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function WorkCard({ icon: Icon, title, subtitle, empty, emptyIcon: EmptyIcon, emptyTitle, emptyText, children }) {
  return (
    <article className="chart-card">
      <header className="chart-card-head has-subtitle">
        <span className="panel-icon" aria-hidden="true"><Icon size={20} /></span>
        <div>
          <h3>{title}</h3>
          <p className="field-hint">{subtitle}</p>
        </div>
      </header>
      {empty ? (
        <div className="chart-empty is-framed">
          <EmptyIcon size={44} aria-hidden="true" />
          <b>{emptyTitle}</b>
          <p>{emptyText}</p>
        </div>
      ) : children}
    </article>
  );
}

/** Últimas mediciones del operador, de sus pacientes y dispositivos disponibles (tres tarjetas). */
export function OperatorWorkCards({ data, institution }) {
  const base = institution ? `/app/instituciones/${institution.idInstitucion}` : undefined;
  return (
    <div className="chart-grid is-three">
      <WorkCard icon={TrendingUp} title="Últimas mediciones que realizó" subtitle="Las que iniciaste vos, en pacientes que tenés a cargo hoy."
        empty={data.realizadas.length === 0} emptyIcon={ChartNoAxesColumn} emptyTitle="Sin mediciones para mostrar" emptyText="Todavía no realizaste mediciones.">
        <PerformedList items={data.realizadas.slice(0, PANEL_MEASUREMENTS)} label="Mediciones realizadas" base={base} />
      </WorkCard>
      <WorkCard icon={UserRound} title="Últimas mediciones de tus pacientes" subtitle="Las más recientes de tus pacientes, las haya hecho vos u otro operador (ver «Realizó»)."
        empty={data.ultimasDePacientes.length === 0} emptyIcon={ChartNoAxesColumn} emptyTitle="Sin mediciones para mostrar"
        emptyText="Tus pacientes aún no tienen mediciones registradas.">
        <PerformedList items={data.ultimasDePacientes.slice(0, PANEL_MEASUREMENTS)} label="Mediciones de sus pacientes" showOperator base={base} />
      </WorkCard>
      <WorkCard icon={Settings} title="Dispositivos disponibles" subtitle="Dispositivos operativos para realizar mediciones."
        empty={data.dispositivos.length === 0} emptyIcon={Smartphone} emptyTitle="No hay dispositivos operativos"
        emptyText="En este momento no hay dispositivos disponibles para realizar mediciones.">
        <ul className="member-list-items" aria-label="Dispositivos disponibles">
          {data.dispositivos.map((device) => (
            <li key={device.idDispositivo} className="member-row"><span><b>{device.codigoDispositivo}</b><small> · {device.nombre ?? 'Sin nombre'} · {device.modeloSensor}</small></span></li>
          ))}
        </ul>
      </WorkCard>
    </div>
  );
}

/** Vista completa de un operador. Para el propio operador, OperatorOverview arma el mismo contenido intercalando su actividad. */
export function OperatorDashboardView({ institution, idOperador, handleOperationError }) {
  const { data, error, period, setPeriod } = useOperatorDashboard(institution, idOperador, handleOperationError);
  return (
    <>
      <OperatorKpiPanel institution={institution} data={data} error={error} period={period} setPeriod={setPeriod} />
      {data?.esPropio && <AssignedPatientsPanel institution={institution} data={data} />}
      {data?.esPropio && <OperatorWorkCards data={data} />}
    </>
  );
}

/** /personal/operadores/:idOperador — vista operativa de un operador (propietario y moderador). */
export function OperatorDashboardPage() {
  const { institution, handleOperationError } = useOutletContext();
  const { idOperador } = useParams();
  return (
    <>
      <OperatorDashboardView institution={institution} idOperador={idOperador} handleOperationError={handleOperationError} />
      {/* Actividad laboral del operador, siempre como cantidades: sin pacientes ni valores de salud. */}
      <ManagementDashboard institution={institution} handleOperationError={handleOperationError} fixedOperator={idOperador} />
    </>
  );
}
