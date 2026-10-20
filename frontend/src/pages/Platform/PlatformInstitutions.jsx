// Instituciones desde la Administración de GlucoLume: tabla con búsqueda y filtro por estado (en el dashboard y en su propia página) y el
// módulo de detalle administrativo de cada una, con pausa/reactivación, límite de cuentas y auditoría. Solo conteos y estado técnico: nunca
// pacientes, personas ni valores clínicos (FastAPI lo exige: permiso SUPERVISAR_INSTITUCIONES, del administrador y del moderador del sistema).

import { Building2, Cpu, FileText, Search, ShieldCheck, Users } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import * as platformApi from '../../api/platformApi.js';
import { friendlyError } from '../../auth/errorMessages.js';
import { Badge } from '../../components/Badge.jsx';
import { EmptyState } from '../../components/EmptyState.jsx';
import { Alert } from '../../components/FormControls.jsx';
import { PageHeader } from '../../components/PageHeader.jsx';
import { usePlatform } from '../../layouts/PlatformLayout.jsx';
import { formatDate, formatDateTime, formatNumber } from '../Account/groups/groupFormat.js';
import { AdministrativeClosureNotice, ExcessNotice, InstitutionActions, InstitutionAuditSection, SuspensionNotice } from './PlatformInstitutionControl.jsx';
import './PlatformDashboard.css';

const STATE_LABEL = { ACTIVA: 'Activa', INACTIVA: 'Pausada', CERRADA: 'Cerrada' };
const STATE_TONE = { ACTIVA: 'success', INACTIVA: 'warning', CERRADA: 'danger' };
const DEVICE_LABEL = { OPERATIVO: 'Operativo', EN_MANTENIMIENTO: 'En mantenimiento', FUERA_DE_SERVICIO: 'Fuera de servicio', BAJA: 'Descomisionado' };
const DEVICE_TONE = { OPERATIVO: 'success', EN_MANTENIMIENTO: 'warning', FUERA_DE_SERVICIO: 'danger', BAJA: 'neutral' };
const n = (value) => formatNumber(value ?? 0);

/** Tabla de instituciones con búsqueda por nombre y filtro por estado; `compact` la limita a una página corta con enlace al listado completo. */
export function InstitutionsTable({ pageSize = 15, compact = false }) {
  const [term, setTerm] = useState('');
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [state, setState] = useState({ data: null, error: '' });

  useEffect(() => {
    const timer = setTimeout(() => { setQuery(term.trim()); setPage(1); }, 300);
    return () => clearTimeout(timer);
  }, [term]);

  useEffect(() => {
    let active = true;
    setState((current) => ({ ...current, data: null }));
    platformApi.getInstitutions({ busqueda: query || undefined, estado: status || undefined, pagina: page, tamanio: pageSize }).then(
      (data) => active && setState({ data, error: '' }), (error) => active && setState({ data: null, error: friendlyError(error) }));
    return () => { active = false; };
  }, [query, status, page, pageSize]);

  const { data, error } = state;
  const pages = data ? Math.max(1, Math.ceil(data.total / data.tamanioPagina)) : 1;
  return (
    <div className="pd-institutions">
      <form className="pd-filters" role="search" aria-label="Buscar instituciones" onSubmit={(event) => event.preventDefault()}>
        <label className="pd-search">
          <span className="sr-only">Buscar por nombre</span>
          <Search size={16} aria-hidden="true" />
          <input type="search" className="field-input" placeholder="Buscar por nombre" value={term} maxLength={100} onChange={(event) => setTerm(event.target.value)} />
        </label>
        <label className="pd-status">
          <span className="sr-only">Estado</span>
          <select className="field-input field-select" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
            <option value="">Todos los estados</option>
            {Object.entries(STATE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        {data && <span className="pd-count" role="status">{n(data.total)} {data.total === 1 ? 'institución' : 'instituciones'}</span>}
      </form>
      {error && <Alert>{error}</Alert>}
      {!data && !error && <p className="field-hint" role="status">Cargando instituciones…</p>}
      {data && data.items.length === 0 && <EmptyState variant="framed" icon={Building2} headingLevel={0} title="No hay instituciones con esos filtros." />}
      {data && data.items.length > 0 && (
        <div className="an-table-wrap">
          <table className="an-table pd-table">
            <caption className="sr-only">Instituciones registradas en GlucoLume</caption>
            <thead>
              <tr>
                <th scope="col">Institución</th><th scope="col">Estado</th><th scope="col">Inicio</th><th scope="col">Finalización</th>
                <th scope="col">Moderadores</th><th scope="col">Operadores</th><th scope="col">Cuentas internas</th><th scope="col">Límite de cuentas</th>
                <th scope="col"><span className="sr-only">Acciones</span></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((row) => (
                <tr key={row.idInstitucion}>
                  <th scope="row"><b>{row.nombre}</b><small>{row.tipoInstitucion}</small></th>
                  <td><Badge tone={STATE_TONE[row.estado] ?? 'neutral'}>{STATE_LABEL[row.estado] ?? row.estado}</Badge></td>
                  <td>{formatDate(row.fechaInicio)}</td>
                  <td>{row.fechaFin ? formatDate(row.fechaFin) : <span className="pd-muted">—</span>}</td>
                  <td>{n(row.moderadores)}</td><td>{n(row.operadores)}</td><td>{n(row.cuentasInternas)}</td>
                  <td>{row.limiteCuentas ? n(row.limiteCuentas) : <span className="pd-muted">Sin informar</span>}</td>
                  <td><Link to={`/plataforma/instituciones/${row.idInstitucion}`} className="btn btn-outline btn-sm" aria-label={`Ver detalle de ${row.nombre}`}>Ver detalle</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && pages > 1 && (
        <nav className="pd-pager" aria-label="Paginación de instituciones">
          <button type="button" className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</button>
          <span>Página {page} de {pages}</span>
          <button type="button" className="btn btn-ghost btn-sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>Siguiente</button>
        </nav>
      )}
      {compact && data && data.total > pageSize && <p><Link to="/plataforma/instituciones" className="text-link">Ver las {n(data.total)} instituciones</Link></p>}
    </div>
  );
}

export function PlatformInstitutionsPage() {
  return (
    <div className="pd">
      <PageHeader title="Instituciones" description="Estado, personal y cuentas de cada institución registrada. Solo datos administrativos." />
      <section className="pd-card" aria-label="Listado de instituciones"><InstitutionsTable /></section>
    </div>
  );
}

function Mini({ label, value, hint }) {
  return <div className="pd-mini"><dt>{label}</dt><dd>{value}</dd>{hint && <small>{hint}</small>}</div>;
}

/** Módulo independiente con el detalle administrativo de UNA institución. */
export function PlatformInstitutionDetailPage() {
  const { idInstitucion } = useParams();
  const { me } = usePlatform();
  const [state, setState] = useState({ data: null, error: '' });
  const [auditKey, setAuditKey] = useState(0);

  useEffect(() => {
    let active = true;
    setState({ data: null, error: '' });
    platformApi.getInstitution(idInstitucion).then(
      (data) => active && setState({ data, error: '' }), (error) => active && setState({ data: null, error: friendlyError(error) }));
    return () => { active = false; };
  }, [idInstitucion]);

  const { data, error } = state;
  const back = { to: '/plataforma/instituciones', label: 'Volver a instituciones' };
  if (error) return <div className="pd"><PageHeader title="Institución" back={back} /><Alert>{error}</Alert></div>;
  if (!data) return <div className="pd"><PageHeader title="Institución" back={back} /><p className="field-hint" role="status">Cargando el detalle…</p></div>;
  const row = data.fila;
  return (
    <div className="pd">
      <PageHeader title={row.nombre} back={back} description={`${row.tipoInstitucion} · ${data.tipoIdentificador} ${data.identificador}`}
        actions={<Badge tone={STATE_TONE[row.estado] ?? 'neutral'}>{STATE_LABEL[row.estado] ?? row.estado}</Badge>} />
      <p className="field-hint pd-privacy"><ShieldCheck size={14} aria-hidden="true" /> Vista administrativa: no incluye pacientes, personas ni resultados clínicos.</p>
      <SuspensionNotice detail={data} />
      <AdministrativeClosureNotice detail={data} />
      <ExcessNotice detail={data} />
      <InstitutionActions detail={data} permissions={me.permisos} hasPassword={me.tieneCredencialLocal} onChanged={(updated) => { setState({ data: updated, error: '' }); setAuditKey((key) => key + 1); }} />
      <div className="pd-grid">
        <section className="pd-card" aria-labelledby="det-estado">
          <header className="pd-card-head"><span className="pd-card-icon" aria-hidden="true"><Building2 size={20} /></span><div><h2 id="det-estado">Estado y cupo</h2></div></header>
          <dl className="pd-minis">
            <Mini label="Inicio" value={formatDate(row.fechaInicio)} />
            <Mini label="Finalización" value={row.fechaFin ? formatDate(row.fechaFin) : 'No corresponde'} hint={row.fechaFin ? undefined : 'GlucoLume no programa vencimientos'} />
            <Mini label="Reaperturas" value={n(data.reaperturas)} />
            <Mini label="Cuentas en uso" value={`${n(data.cupoUtilizado)} de ${n(row.limiteCuentas)}`} hint={data.porcentajeUtilizacion != null ? `${data.porcentajeUtilizacion}% del cupo` : undefined} />
            <Mini label="Cupos disponibles" value={n(data.cuposDisponibles)} hint={data.excedente ? `${n(data.excedente)} cuentas por encima del límite` : undefined} />
          </dl>
          {data.porcentajeUtilizacion != null && (
            <div className="pd-meter" role="img" aria-label={`Cupo utilizado: ${data.porcentajeUtilizacion}%`}><span style={{ width: `${Math.min(100, data.porcentajeUtilizacion)}%` }} /></div>
          )}
        </section>
        <section className="pd-card" aria-labelledby="det-personal">
          <header className="pd-card-head"><span className="pd-card-icon" aria-hidden="true"><Users size={20} /></span><div><h2 id="det-personal">Personal y pacientes</h2></div></header>
          <dl className="pd-minis">
            <Mini label="Propietarios" value={n(row.propietarios)} /><Mini label="Moderadores" value={n(row.moderadores)} /><Mini label="Operadores" value={n(row.operadores)} />
            <Mini label="Cuentas internas" value={n(row.cuentasInternas)} hint="personas distintas con vínculo activo" />
            <Mini label="Invitaciones pendientes" value={n(data.invitacionesPendientes)} />
            <Mini label="Pacientes activos" value={n(data.pacientesActivos)} hint={`${n(data.pacientesRegistrados)} registrados (solo cantidad)`} />
          </dl>
        </section>
      </div>
      <section className="pd-card" aria-labelledby="det-mediciones">
        <header className="pd-card-head"><span className="pd-card-icon" aria-hidden="true"><FileText size={20} /></span><div><h2 id="det-mediciones">Mediciones (volumen operativo)</h2></div></header>
        <dl className="pd-minis">
          <Mini label="Total" value={n(data.medicionesTotal)} /><Mini label="En los últimos 30 días" value={n(data.medicionesPeriodo)} />
          <Mini label="Completadas" value={n(data.completadas)} /><Mini label="Canceladas" value={n(data.canceladas)} /><Mini label="Inválidas" value={n(data.invalidas)} />
          <Mini label="Última actividad" value={data.ultimaActividad ? formatDateTime(data.ultimaActividad) : 'Sin actividad'} />
        </dl>
      </section>
      <section className="pd-card" aria-labelledby="det-dispositivos">
        <header className="pd-card-head">
          <span className="pd-card-icon" aria-hidden="true"><Cpu size={20} /></span>
          <div><h2 id="det-dispositivos">Dispositivos asignados</h2><p>Estado técnico. Una lectura cancelada no implica que el dispositivo esté averiado.</p></div>
        </header>
        {data.dispositivosAsignados.length === 0 ? <p className="field-hint">Esta institución no tiene dispositivos asignados.</p> : (
          <div className="an-table-wrap">
            <table className="an-table pd-table">
              <caption className="sr-only">Dispositivos asignados a la institución</caption>
              <thead><tr><th scope="col">Código</th><th scope="col">Modelo</th><th scope="col">Sensor</th><th scope="col">Firmware</th><th scope="col">Estado técnico</th><th scope="col">Asignado</th><th scope="col">Lecturas inválidas (7 días)</th></tr></thead>
              <tbody>
                {data.dispositivosAsignados.map((device) => (
                  <tr key={device.idDispositivo}>
                    <th scope="row"><b>{device.codigoDispositivo}</b>{device.nombre && <small>{device.nombre}</small>}</th>
                    <td>{device.modelo ?? <span className="pd-muted">Sin informar</span>}</td><td>{device.modeloSensor}</td>
                    <td>{device.versionFirmware ?? <span className="pd-muted">Sin informar</span>}</td>
                    <td><Badge tone={DEVICE_TONE[device.estado] ?? 'neutral'}>{DEVICE_LABEL[device.estado] ?? device.estado}</Badge></td>
                    <td>{device.fechaAsignacion ? formatDate(device.fechaAsignacion) : <span className="pd-muted">Sin informar</span>}</td>
                    <td>{n(device.lecturasInvalidasRecientes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {me.permisos.includes('AUDITAR_INSTITUCIONES') && <InstitutionAuditSection idInstitucion={row.idInstitucion} reloadKey={auditKey} />}
    </div>
  );
}
