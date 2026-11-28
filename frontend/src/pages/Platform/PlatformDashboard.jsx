// Dashboard general de la Administración de GlucoLume: panel ejecutivo de supervisión. Todo sale de FastAPI (/platform/dashboard,
// /platform/system, /platform/institutions): consultas reales, sin valores simulados. Son agregados operativos —nunca nombres, correos ni
// resultados clínicos— y el moderador del sistema solo ve la parte técnica. Orden por importancia operativa: salud de la plataforma, cifras
// clave, instituciones, cuentas, dispositivos, mediciones operativas y seguridad.

import {
  Activity, AlertCircle, Building2, CalendarDays, Cpu, Download, FileText, KeyRound, Layers, Lock, ShieldCheck, User, Users,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import * as platformApi from '../../api/platformApi.js';
import { friendlyError } from '../../auth/errorMessages.js';
import { Badge } from '../../components/Badge.jsx';
import { Alert } from '../../components/FormControls.jsx';
import { PageHeader } from '../../components/PageHeader.jsx';
import { TrendChart } from '../../components/TrendChart.jsx';
import { PeriodFilter, periodLabel } from '../../components/dashboard.jsx';
import { usePlatform } from '../../layouts/PlatformLayout.jsx';
import { formatInstant } from '../../utils/dateTime.js';
import { formatDate, formatNumber } from '../Account/groups/groupFormat.js';
import { InstitutionsTable } from './PlatformInstitutions.jsx';
import './PlatformDashboard.css';

export const COMPONENT_TONE = { OPERATIVO: 'success', DEGRADADO: 'warning', NO_DISPONIBLE: 'danger', DESCONOCIDO: 'neutral' };
export const COMPONENT_LABEL = { OPERATIVO: 'Operativo', DEGRADADO: 'Degradado', NO_DISPONIBLE: 'No disponible', DESCONOCIDO: 'Estado desconocido' };
const REASONS = {
  LECTURA_NO_VALIDA: 'Lectura no válida', SESION_EXPIRADA: 'Sesión expirada', SESION_ABANDONADA: 'Sesión abandonada',
  CANCELADA_POR_USUARIO: 'Cancelada por la persona', TIMEOUT_MEDICION: 'Tiempo de medición agotado',
};
const reasonLabel = (key) => REASONS[key] ?? key.toLowerCase().replace(/_/g, ' ');
const n = (value) => formatNumber(value ?? 0);

/** Número destacado de una tarjeta ejecutiva. `tone`: ok / warn / danger pinta el borde y el número. */
function Stat({ icon: Icon, label, value, hint, tone }) {
  return (
    <li className={`pd-stat${tone ? ` is-${tone}` : ''}`}>
      <span className="pd-stat-icon" aria-hidden="true"><Icon size={22} /></span>
      <div>
        <small>{label}</small>
        <b>{value}</b>
        {hint && <span className="pd-hint">{hint}</span>}
      </div>
    </li>
  );
}

// Accesos por tipo de cuenta (lo clasifica el backend según la cuenta que se autenticó: ver services/authAccess.py). Cada intento figura en un solo tipo.
const ACCESS_TYPES = [
  { key: 'individual', icon: User, label: 'Accesos individuales' },
  { key: 'institucional', icon: Building2, label: 'Accesos institucionales' },
  { key: 'plataforma', icon: ShieldCheck, label: 'Accesos de sistema / plataforma' },
];

/** El número son los intentos fallidos (color de advertencia si hay). */
function AccessStat({ icon, label, counts }) {
  return (
    <Stat icon={icon} label={label} value={n(counts.fallidos)}
      tone={counts.fallidos > 0 ? 'warn' : 'ok'} />
  );
}

function Mini({ label, value, hint }) {
  return (
    <div className="pd-mini">
      <dt>{label}</dt>
      <dd>{value}</dd>
      {hint && <small>{hint}</small>}
    </div>
  );
}

function Card({ id, icon: Icon, title, subtitle, action, children, className = '' }) {
  return (
    <section className={`pd-card ${className}`.trim()} aria-labelledby={id}>
      <header className="pd-card-head">
        <span className="pd-card-icon" aria-hidden="true"><Icon size={20} /></span>
        <div><h2 id={id}>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
        {action}
      </header>
      {children}
    </section>
  );
}

/** Estado de los componentes: una verificación real por componente, con qué se comprobó y cuánto tardó. */
export function HealthStrip({ system, failed }) {
  if (failed) return <Alert kind="info">No pudimos consultar el estado de los componentes. Los indicadores de abajo siguen siendo válidos.</Alert>;
  if (!system) return <p className="field-hint" role="status">Verificando los componentes…</p>;
  const problems = system.componentes.filter((component) => component.estado !== 'OPERATIVO');
  return (
    <section className="pd-health" aria-labelledby="pd-salud">
      <header>
        <h2 id="pd-salud"><Activity size={18} aria-hidden="true" /> Estado de los componentes</h2>
        <span className={problems.length ? 'is-warn' : 'is-ok'}>
          {problems.length === 0 ? 'Todo operativo' : `${problems.length} ${problems.length === 1 ? 'componente requiere' : 'componentes requieren'} atención`}
        </span>
        <small>Verificado {formatInstant(system.fecha)}</small>
      </header>
      <ul aria-label="Componentes de la plataforma">
        {system.componentes.map((component) => (
          <li key={component.nombre} className={`pd-chip is-${COMPONENT_TONE[component.estado] ?? 'neutral'}`}
            title={[component.verificacion, component.detalle, component.latenciaMs != null ? `${component.latenciaMs} ms` : null].filter(Boolean).join(' · ')}>
            <span className="pd-dot" aria-hidden="true" />
            <span className="pd-chip-name">{component.nombre}</span>
            <Badge tone={COMPONENT_TONE[component.estado] ?? 'neutral'} size="sm">{COMPONENT_LABEL[component.estado] ?? 'Estado desconocido'}</Badge>
            {component.detalle && <small>{component.detalle}</small>}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Resumen total: histórico desde la creación de la base de datos. No depende del período elegido. */
function TotalSummary({ data, admin }) {
  const { usuarios: users, dispositivos: devices, mediciones: meas } = data;
  return (
    <section className="pd-summary pd-total" aria-labelledby="pd-resumen-total">
      <header className="pd-summary-head">
        <h2 id="pd-resumen-total">Resumen total</h2>
        <small>Histórico desde la creación de la base de datos · no cambia con el período</small>
      </header>
      <ul className="pd-stats" aria-label="Totales históricos">
        {admin && <Stat icon={Users} label="Cuentas totales" value={n(users.total)} hint={`${n(users.activas)} activas · ${n(users.inactivas)} inactivas`} />}
        {admin && <Stat icon={User} label="Cuentas individuales" value={n(users.individuales)} hint="clientes" />}
        {admin && <Stat icon={Building2} label="Cuentas institucionales" value={n(users.institucionales)} hint={`${n(users.conVinculoInstitucional)} con vínculo activo`} />}
        <Stat icon={Cpu} label="Dispositivos operativos" value={n(devices.operativos)} hint={`de ${n(devices.total)} registrados`}
          tone={devices.fueraDeServicio > 0 ? 'warn' : 'ok'} />
        <Stat icon={FileText} label="Mediciones" value={n(meas.total)} hint="procesadas, sin DEMO" />
      </ul>
    </section>
  );
}

function DeviceBar({ devices }) {
  const parts = [
    ['Operativos', devices.operativos, 'ok'], ['En mantenimiento', devices.enMantenimiento, 'warn'],
    ['Fuera de servicio', devices.fueraDeServicio, 'danger'], ['Descomisionados', devices.descomisionados, 'muted'],
  ];
  const total = parts.reduce((sum, part) => sum + part[1], 0);
  return (
    <div>
      <div className="pd-bar" role="img" aria-label={`Dispositivos por estado técnico: ${parts.map(([label, value]) => `${label} ${value}`).join(', ')}`}>
        {total > 0 && parts.filter(([, value]) => value > 0).map(([label, value, tone]) => <span key={label} className={`is-${tone}`} style={{ flexGrow: value }} />)}
      </div>
      <ul className="pd-legend">
        {parts.map(([label, value, tone]) => <li key={label}><i className={`is-${tone}`} aria-hidden="true" />{label} <b>{value}</b></li>)}
      </ul>
    </div>
  );
}

function EventList({ events, label }) {
  if (events.length === 0) return <p className="field-hint">Sin eventos en el período.</p>;
  return (
    <ul className="pd-events" aria-label={label}>
      {events.map((event) => (
        <li key={event.idAuditoria}>
          <span className={`pd-dot is-${event.resultado === 'FALLO' ? 'danger' : 'ok'}`} aria-hidden="true" />
          <span><b>{event.accion.toLowerCase().replace(/_/g, ' ')}</b> · {event.modulo ?? 'SISTEMA'}{event.resultado === 'FALLO' ? ' · fallido' : ''}</span>
          <small>{formatInstant(event.fechaHora)}</small>
        </li>
      ))}
    </ul>
  );
}

const ACTION_LABELS = {
  EXPORTACION_SOLICITADA: 'Exportación solicitada', EXPORTACION_COMPLETADA: 'Exportación completada', EXPORTACION_FALLIDA: 'Exportación fallida',
  ERROR_INTERNO: 'Error de servidor inesperado',
};

/** Nombre legible de una acción de auditoría; las que no están en la tabla se leen en minúsculas, con mayúscula inicial. */
function actionLabel(accion) {
  const text = ACTION_LABELS[accion] ?? accion.toLowerCase().replace(/_/g, ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function SecurityKpi({ icon: Icon, label, value, hint, tone = 'ok' }) {
  return (
    <li className={`pd-sec-kpi is-${tone}`}>
      <span className="pd-sec-kpi-icon" aria-hidden="true"><Icon size={22} /></span>
      <div>
        <small>{label}</small>
        <b>{value}</b>
        {hint && <span className="pd-hint">{hint}</span>}
      </div>
    </li>
  );
}

/** Motivos de acceso fallido como barras proporcionales al máximo del período. */
function ReasonBars({ reasons }) {
  if (reasons.length === 0) return <p className="field-hint">Sin accesos fallidos en el período.</p>;
  const max = Math.max(...reasons.map((reason) => reason.total), 1);
  return (
    <ul className="pd-sec-bars" aria-label="Motivos principales de acceso fallido">
      {reasons.map((reason) => (
        <li key={reason.clave}>
          <span>{reason.clave}</span>
          <span className="pd-sec-bar-track" aria-hidden="true"><span style={{ width: `${(reason.total / max) * 100}%` }} /></span>
          <b>{n(reason.total)}</b>
        </li>
      ))}
    </ul>
  );
}

/** Lista de eventos: verde si salió bien, rojo si falló o si es una alerta operativa. */
function ActivityFeed({ events, label, alert = false, empty }) {
  if (events.length === 0) return <p className="field-hint">{empty}</p>;
  return (
    <ul className="pd-sec-feed" aria-label={label}>
      {events.map((event) => {
        const failed = event.resultado === 'FALLO';
        return (
          <li key={event.idAuditoria} className="pd-sec-row">
            <span className={`pd-dot is-${alert || failed ? 'danger' : 'ok'}`} aria-hidden="true" />
            <span className="pd-sec-text"><b>{actionLabel(event.accion)}</b> · {event.modulo ?? 'SISTEMA'}{failed ? ' · fallido' : ''}</span>
            <small>{formatInstant(event.fechaHora)}</small>
          </li>
        );
      })}
    </ul>
  );
}

/** Seguridad y actividad del período (solo administración): indicadores, motivos de fallo, actividad y alertas recientes. */
function SecuritySection({ data, sec }) {
  return (
    <section className="pd-sec" aria-labelledby="pd-seguridad">
      <header className="pd-sec-head">
        <span className="pd-sec-icon" aria-hidden="true"><ShieldCheck size={26} /></span>
        <div>
          <h2 id="pd-seguridad">Seguridad y actividad</h2>
          <p>Resumen del período. Solo eventos relevantes y alertas prioritarias.</p>
        </div>
        <Link to="/plataforma/auditoria" className="btn btn-outline pd-sec-link"><KeyRound size={16} aria-hidden="true" /> Auditoría y seguridad</Link>
      </header>
      <ul className="pd-sec-kpis" aria-label="Indicadores de seguridad">
        <SecurityKpi icon={Lock} label="Intentos fallidos" value={n(sec.loginsFallidos)} tone={sec.loginsFallidos > 0 ? 'warn' : 'ok'} />
        <SecurityKpi icon={Users} label="Cuentas con riesgo" value={n(sec.cuentasConFallosRepetidos)} hint="3 o más contraseñas incorrectas"
          tone={sec.cuentasConFallosRepetidos > 0 ? 'warn' : 'ok'} />
        <SecurityKpi icon={AlertCircle} label="Eventos críticos" value={n(sec.eventosCriticos)} tone={sec.eventosCriticos > 0 ? 'danger' : 'ok'} />
        <SecurityKpi icon={Layers} label="Operaciones administrativas" value={n(sec.operacionesAdministrativas)} />
        <SecurityKpi icon={Download} label="Exportaciones de datos" value={n(sec.exportaciones)}
          hint={sec.exportaciones === 0 ? 'ninguna registrada' : undefined} />
      </ul>
      <p className={`pd-sec-pill ${sec.bloqueosTemporales > 0 ? 'is-warn' : 'is-ok'}`}>
        <span className="pd-dot" aria-hidden="true" /> Bloqueos vigentes: {n(sec.bloqueosTemporales)}
      </p>
      <div className="pd-sec-panels">
        <section className="pd-sec-panel" aria-labelledby="pd-motivos">
          <header><h3 id="pd-motivos">Motivos principales de acceso fallido</h3></header>
          <ReasonBars reasons={sec.motivosFallo} />
        </section>
        <section className="pd-sec-panel" aria-labelledby="pd-actividad">
          <header>
            <h3 id="pd-actividad">Actividad reciente</h3>
            <span className="pd-sec-chip">{n(sec.operacionesAdministrativas)} operaciones en el período</span>
          </header>
          <ActivityFeed events={data.operacionesAdministrativas} label="Actividad reciente" empty="Sin operaciones en el período." />
        </section>
      </div>
      <section className="pd-sec-panel" aria-labelledby="pd-alertas">
        <header>
          <h3 id="pd-alertas">Alertas operativas recientes</h3>
          <span className="pd-sec-chip is-danger">{n(data.erroresRecientes.length)} errores recientes</span>
        </header>
        <ActivityFeed events={data.erroresRecientes} label="Alertas operativas recientes" alert empty="Sin errores recientes en el período." />
      </section>
    </section>
  );
}

export function PlatformDashboardPage() {
  const { me } = usePlatform();
  const [period, setPeriod] = useState({ dias: 30 });
  const [state, setState] = useState({ data: null, error: '' });
  const [system, setSystem] = useState({ value: null, failed: false });

  useEffect(() => {
    if (me.requiereConfigurarMfa) return undefined;
    let active = true;
    setState((current) => ({ ...current, data: null }));
    platformApi.getPlatformDashboard(period).then(
      (data) => active && setState({ data, error: '' }),
      (error) => active && setState({ data: null, error: friendlyError(error) }),
    );
    return () => { active = false; };
  }, [JSON.stringify(period), me.requiereConfigurarMfa]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (me.requiereConfigurarMfa) return undefined;
    let active = true;
    platformApi.getSystemStatus().then((value) => active && setSystem({ value, failed: false }), () => active && setSystem({ value: null, failed: true }));
    return () => { active = false; };
  }, [me.requiereConfigurarMfa]);

  if (me.requiereConfigurarMfa) {
    return <PageHeader title="Dashboard general" description="Activá MFA para ver los indicadores." />;
  }
  const { data, error } = state;
  const admin = data?.alcance === 'ADMINISTRADOR';
  const todayText = new Date().toLocaleDateString('es-AR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  const today = todayText.charAt(0).toUpperCase() + todayText.slice(1);
  const users = data?.usuarios;
  const devices = data?.dispositivos;
  const meas = data?.mediciones;
  const sec = data?.seguridad;
  return (
    <div className="pd">
      <PageHeader title={`Dashboard ${data?.alcance === 'TECNICO' ? 'técnico' : 'general'}`}
        description="Supervisión de la plataforma: cuentas, instituciones, dispositivos y seguridad. Solo agregados, sin datos personales ni resultados clínicos."
        actions={<span className="pd-date"><CalendarDays size={16} aria-hidden="true" /> {today}</span>} />
      {error && <Alert>{error}</Alert>}
      <HealthStrip system={system.value} failed={system.failed} />
      {data && <TotalSummary data={data} admin={admin} />}
      <div className="pd-period">
        <PeriodFilter value={period} onChange={setPeriod} idPrefix="dash-plataforma" />
      </div>
      {!data && !error && <p className="field-hint" role="status">Cargando indicadores…</p>}
      {data && (
        <>

          <section className="pd-summary" aria-labelledby="pd-resumen">
            <header className="pd-summary-head">
              <h2 id="pd-resumen">Resumen</h2>
              <small>{periodLabel(data.periodo)}</small>
            </header>
            <ul className="pd-stats" aria-label="Indicadores principales">
              {admin && <Stat icon={Users} label="Cuentas registradas" value={n(users.total)} hint={`${n(users.activas)} activas · ${n(users.inactivas)} inactivas`} />}
              {admin && <Stat icon={Building2} label="Instituciones activas" value={n(data.instituciones.activas)} hint={`de ${n(data.instituciones.total)} en total`} />}
              <Stat icon={Cpu} label="Dispositivos operativos" value={n(devices.operativos)} hint={`de ${n(devices.total)} registrados`}
                tone={devices.fueraDeServicio > 0 ? 'warn' : 'ok'} />
              <Stat icon={FileText} label="Mediciones del período" value={n(meas.enPeriodo)} hint="volumen operativo, sin valores clínicos" />
            </ul>

            {admin && (
              <>
                <ul className="pd-stats" aria-label="Accesos por tipo de cuenta">
                  {ACCESS_TYPES.map(({ key, icon, label }) => <AccessStat key={key} icon={icon} label={label} counts={sec.accesosPorTipo[key]} />)}
                </ul>
              </>
            )}
          </section>

          {admin && (
            <Card id="pd-instituciones" icon={Building2} title="Instituciones" subtitle="Resumen de las instituciones de la plataforma."
              action={<Link to="/plataforma/instituciones" className="btn btn-outline btn-sm">Mostrar instituciones →</Link>}>
              <dl className="pd-minis" aria-label="Resumen de instituciones">
                <Mini label="Activas" value={n(data.instituciones.activas)} />
                <Mini label="Pausadas" value={n(data.instituciones.inactivas)} />
                <Mini label="Cerradas" value={n(data.instituciones.cerradas)} />
                <Mini label="Cuentas institucionales" value={n(data.instituciones.cuentasInstitucionales)} hint="propietarios, moderadores y operadores" />
                <Mini label="Moderadores institucionales" value={n(data.instituciones.moderadores)} />
                <Mini label="Operadores institucionales" value={n(data.instituciones.operadores)} />
              </dl>
            </Card>
          )}

          {!admin && me.permisos.includes('SUPERVISAR_INSTITUCIONES') && (
            <Card id="pd-instituciones" icon={Building2} title="Instituciones" subtitle="Buscá una institución para ver su detalle y pausarla, reactivarla o ajustar su límite de cuentas.">
              <InstitutionsTable pageSize={8} compact />
            </Card>
          )}

          <div className="pd-grid">
            {admin && (
              <Card id="pd-cuentas" icon={Users} title="Cuentas y grupos" subtitle="Cada cuenta se cuenta una sola vez, según su tipo." className="pd-card-cuentas">
                <dl className="pd-minis" aria-label="Cuentas">
                  <Mini label="Cuentas individuales" value={n(users.individuales)} hint="solo clientes (no institucionales ni administrativos)" />
                  <Mini label="Cuentas grupales" value={n(data.grupos.usuariosAgrupados)} hint="personas agrupadas" />
                  <Mini label="Grupos" value={n(data.grupos.total)} hint={`${n(data.grupos.activos)} activos`} />
                  <Mini label="Registradas en el período" value={n(users.noInstitucionalesRegistradasPeriodo)} hint="sin contar las institucionales" />
                </dl>
              </Card>
            )}

            <Card id="pd-dispositivos" icon={Cpu} title="Dispositivos" subtitle="Disponibilidad técnica, aparte del resultado de cada medición."
              className="pd-card-dispositivos"
              action={<Link to="/plataforma/dispositivos" className="btn btn-outline btn-sm">Ver inventario de dispositivos →</Link>}>
              <DeviceBar devices={devices} />
              <dl className="pd-minis" aria-label="Dispositivos">
                <Mini label="Total de dispositivos" value={n(devices.total)} />
                <Mini label="Asignados a instituciones" value={n(devices.asignados)} />
                <Mini label="Asignados a cuentas individuales" value={devices.asignadosCuentasIndividuales == null ? 'No disponible' : n(devices.asignadosCuentasIndividuales)}
                  hint={devices.asignadosCuentasIndividuales == null ? 'la base todavía no registra estos vínculos' : 'dispositivos vinculados a al menos una cuenta individual'} />
                <Mini label="Sin asignar" value={n(devices.sinAsignar)} />
                <Mini label="Operativos" value={n(devices.operativos)} />
                <Mini label="En mantenimiento" value={n(devices.enMantenimiento)} />
                <Mini label="Fuera de servicio" value={n(devices.fueraDeServicio)} />
                <Mini label="Descomisionados" value={n(devices.descomisionados)} />
              </dl>
            </Card>
          </div>

          <Card id="pd-mediciones" icon={FileText} title="Mediciones: volumen operativo" subtitle="Solo cantidades. La administración no consulta resultados clínicos.">
            <dl className="pd-minis" aria-label="Mediciones">
              <Mini label="Procesadas (período)" value={n(meas.enPeriodo)} hint={meas.demo ? `${n(meas.demo)} DEMO aparte en el período` : undefined} />
              <Mini label="Completadas" value={n(meas.completadasPeriodo)} />
              <Mini label="Canceladas" value={n(meas.canceladasPeriodo)} />
              <Mini label="Inválidas" value={n(meas.invalidasPeriodo)} />
              <Mini label="Errores técnicos (período)" value={n(meas.erroresTecnicos)} hint="auditoría técnica anonimizada" />
            </dl>
            <div className="pd-split">
              <div>
                <h3>Tendencia del período</h3>
                {meas.serie.length === 0 ? <p className="field-hint">No hay mediciones en este período.</p>
                  : <TrendChart title="Mediciones por fecha" unit="mediciones" points={meas.serie.map((day) => ({ label: formatDate(day.fecha), value: day.total }))} />}
              </div>
              <div>
                <h3>Errores técnicos de adquisición</h3>
                {meas.motivosTecnicos.length === 0 ? <p className="field-hint">Sin errores técnicos registrados en el período.</p> : (
                  <ul className="pd-reasons" aria-label="Errores técnicos por motivo">
                    {meas.motivosTecnicos.map((reason) => <li key={reason.clave}><span>{reasonLabel(reason.clave)}</span><b>{n(reason.total)}</b></li>)}
                  </ul>
                )}
              </div>
            </div>
          </Card>

          {admin && <SecuritySection data={data} sec={sec} />}
        </>
      )}
    </div>
  );
}
