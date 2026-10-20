// Dashboard general de la Administración de GlucoLume: panel ejecutivo de supervisión. Todo sale de FastAPI (/platform/dashboard,
// /platform/system, /platform/institutions): consultas reales, sin valores simulados. Son agregados operativos —nunca nombres, correos ni
// resultados clínicos— y el moderador del sistema solo ve la parte técnica. Orden por importancia operativa: salud de la plataforma, cifras
// clave, instituciones, cuentas, dispositivos, mediciones operativas y seguridad.

import {
  Activity, Building2, CalendarDays, Cpu, FileText, KeyRound, ShieldCheck, User, Users,
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

/** El número destacado son los intentos fallidos (color de advertencia si hay); los ingresos correctos van debajo. */
function AccessStat({ icon, label, counts }) {
  return (
    <Stat icon={icon} label={label} value={n(counts.fallidos)} hint={`intentos fallidos · ${n(counts.exitosos)} ingresos correctos`}
      tone={counts.fallidos > 0 ? 'warn' : 'ok'} />
  );
}

/** Intentos sin cuenta identificable (identificador inexistente) o con contexto contradictorio: no se asignan a ningún tipo. */
function UnclassifiedAccess({ counts }) {
  if (counts.fallidos + counts.exitosos === 0) return null;
  return (
    <p className="field-hint pd-unclassified">
      Sin clasificar: {n(counts.fallidos)} {counts.fallidos === 1 ? 'intento fallido' : 'intentos fallidos'} · {n(counts.exitosos)} {counts.exitosos === 1 ? 'ingreso correcto' : 'ingresos correctos'}.
      {' '}Son intentos sin una cuenta identificable (por ejemplo, un usuario o correo inexistente) o con datos contradictorios, y no se suman a ningún tipo de cuenta.
    </p>
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
      {!data && !error && <p className="field-hint" role="status">Cargando indicadores…</p>}
      {data && (
        <>
          <div className="pd-period">
            <PeriodFilter value={period} onChange={setPeriod} idPrefix="dash-plataforma" compact />
            <p className="field-hint">Período: {periodLabel(data.periodo)}.</p>
          </div>

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
              <UnclassifiedAccess counts={sec.accesosPorTipo.sinClasificar} />
            </>
          )}

          {admin && (
            <Card id="pd-instituciones" icon={Building2} title="Instituciones" subtitle="Buscá una institución y abrí su detalle administrativo.">
              <dl className="pd-minis" aria-label="Resumen de instituciones">
                <Mini label="Activas" value={n(data.instituciones.activas)} />
                <Mini label="Pausadas" value={n(data.instituciones.inactivas)} />
                <Mini label="Cerradas" value={n(data.instituciones.cerradas)} />
                <Mini label="Moderadores institucionales" value={n(data.instituciones.moderadores)} />
                <Mini label="Operadores institucionales" value={n(data.instituciones.operadores)} />
              </dl>
              <InstitutionsTable pageSize={8} compact />
            </Card>
          )}

          {!admin && me.permisos.includes('SUPERVISAR_INSTITUCIONES') && (
            <Card id="pd-instituciones" icon={Building2} title="Instituciones" subtitle="Buscá una institución para ver su detalle y pausarla, reactivarla o ajustar su límite de cuentas.">
              <InstitutionsTable pageSize={8} compact />
            </Card>
          )}

          <div className="pd-grid">
            {admin && (
              <Card id="pd-cuentas" icon={Users} title="Cuentas y grupos" subtitle="Cada cuenta se cuenta una sola vez, según su tipo.">
                <dl className="pd-minis" aria-label="Cuentas">
                  <Mini label="Individuales" value={n(users.individuales)} />
                  <Mini label="Institucionales" value={n(users.institucionales)} hint={`${n(users.conVinculoInstitucional)} con vínculo activo · ${n(users.institucionalesSinVinculo)} sin vínculo`} />
                  <Mini label="Administración" value={n(users.plataforma)} hint="administrador y moderadores del sistema" />
                  <Mini label="Registradas en 7 días" value={n(users.registradas7Dias)} />
                  <Mini label="Registradas en el período" value={n(users.registradasPeriodo)} />
                  <Mini label="Grupos" value={n(data.grupos.total)} hint={`${n(data.grupos.activos)} activos · ${n(data.grupos.usuariosAgrupados)} personas agrupadas`} />
                </dl>
                <p className="field-hint">
                  «Con vínculo activo» son las cuentas internas de una institución: una persona con varios roles o instituciones cuenta una vez.
                </p>
              </Card>
            )}

            <Card id="pd-dispositivos" icon={Cpu} title="Dispositivos" subtitle="Disponibilidad técnica, aparte del resultado de cada medición.">
              <DeviceBar devices={devices} />
              <dl className="pd-minis" aria-label="Dispositivos">
                <Mini label="Asignados a instituciones" value={n(devices.asignados)} />
                <Mini label="Sin asignar" value={n(devices.sinAsignar)} />
                <Mini label="Con lecturas inválidas (7 días)" value={n(devices.conLecturasInvalidasRecientes)}
                  hint="señal para revisarlos; una lectura cancelada no implica avería" />
                <Mini label="Desconectados" value={devices.desconectados == null ? 'No disponible' : n(devices.desconectados)}
                  hint={devices.conexionVerificable ? undefined : 'el sistema no registra la conexión de cada dispositivo'} />
              </dl>
              <Link to="/plataforma/dispositivos" className="text-link">Ver el inventario de dispositivos</Link>
            </Card>
          </div>

          <Card id="pd-mediciones" icon={FileText} title="Mediciones: volumen operativo" subtitle="Solo cantidades. La administración no consulta resultados clínicos.">
            <dl className="pd-minis" aria-label="Mediciones">
              <Mini label="Procesadas (total)" value={n(meas.total)} hint={meas.demo ? `${n(meas.demo)} DEMO aparte en el período` : undefined} />
              <Mini label="Completadas" value={n(meas.completadas)} />
              <Mini label="Canceladas" value={n(meas.canceladas)} />
              <Mini label="Inválidas" value={n(meas.invalidas)} />
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

          {admin && (
            <Card id="pd-seguridad" icon={ShieldCheck} title="Seguridad y actividad" subtitle="Resumen del período. El detalle está en Auditoría y seguridad."
              action={<Link to="/plataforma/auditoria" className="btn btn-outline btn-sm"><KeyRound size={15} aria-hidden="true" /> Auditoría y seguridad</Link>}>
              <dl className="pd-minis" aria-label="Seguridad">
                <Mini label="Intentos de acceso fallidos" value={n(sec.loginsFallidos)} />
                <Mini label="Cuentas con accesos fallidos repetidos" value={n(sec.cuentasConFallosRepetidos)} hint="3 o más contraseñas incorrectas" />
                <Mini label="Cuentas bloqueadas" value={n(sec.cuentasBloqueadas)} hint={`${n(sec.bloqueosTemporales)} con bloqueo temporal vigente`} />
                <Mini label="Eventos críticos" value={n(sec.eventosCriticos)} />
                <Mini label="Operaciones administrativas" value={n(sec.operacionesAdministrativas)} />
                <Mini label="Exportaciones de datos" value={n(sec.exportaciones)} hint={sec.exportaciones === 0 ? 'ninguna registrada' : undefined} />
              </dl>
              <div className="pd-split">
                <div>
                  <h3>Motivos de los accesos fallidos</h3>
                  {sec.motivosFallo.length === 0 ? <p className="field-hint">Sin accesos fallidos en el período.</p> : (
                    <ul className="pd-reasons" aria-label="Motivos de los accesos fallidos">
                      {sec.motivosFallo.map((reason) => <li key={reason.clave}><span>{reason.clave}</span><b>{n(reason.total)}</b></li>)}
                    </ul>
                  )}
                </div>
                <div>
                  <h3>Operaciones administrativas recientes</h3>
                  <EventList events={data.operacionesAdministrativas} label="Operaciones administrativas recientes" />
                </div>
              </div>
              <h3>Errores operativos recientes</h3>
              <EventList events={data.erroresRecientes} label="Errores operativos recientes" />
            </Card>
          )}
        </>
      )}
    </div>
  );
}
