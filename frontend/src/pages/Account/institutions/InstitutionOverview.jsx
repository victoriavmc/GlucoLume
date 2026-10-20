// Panel institucional (dashboard): administración institucional, accesos rápidos, resumen del equipo y los dispositivos, indicadores
// reales del backend, gráficos y actividad reciente, según los permisos del rol. El rol y el estado de la institución están en el
// encabezado. Los datos administrativos completos viven en Administración → Datos.

import {
  ArrowRight, Building2, ChartColumn, Cpu, Crown, HeartPulse, Settings, Settings2, ShieldCheck, UserRound, UsersRound, Zap,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useOutletContext } from 'react-router-dom';

import * as institutionsApi from '../../../api/institutionsApi.js';
import { devicesApi } from '../../../api/devicesApi.js';
import { ManagementDashboard } from './dashboard/ManagementPanel.jsx';

import { AdminAction } from './AdminAction.jsx';
import { InstitutionActivity } from './InstitutionActivity.jsx';
import { OperatorOverview } from './OperatorOverview.jsx';
import { QuotaSection } from './QuotaSection.jsx';
import { PendingReassignmentsSection } from './reassignments/PendingReassignmentsSection.jsx';
import { can, formatDateTime } from './institutionFormat.js';

/** Dispositivos no descomisionados de la institución; solo se consulta si el rol puede verlo. */
function useDeviceCount(institution) {
  const [count, setCount] = useState(null);
  const allowed = can(institution, 'CONSULTAR_DISPOSITIVOS');
  useEffect(() => {
    if (!allowed) return undefined;
    let active = true;
    devicesApi(institution.idInstitucion).summary().then(
      (result) => active && setCount(result.total - result.descomisionados), // el inventario completo (con históricos) está en Dispositivos
      () => active && setCount(null),
    );
    return () => { active = false; };
  }, [allowed, institution.idInstitucion]);
  return allowed ? count : undefined;
}

/** Tarjeta del resumen: ícono de color, etiqueta, cantidad con su unidad y acceso circular; navegable si el rol tiene la funcionalidad. */
function StatCard({ icon: Icon, tone, label, count, unit, to, linkText }) {
  const content = (
    <>
      <span className="panel-icon" aria-hidden="true"><Icon size={24} /></span>
      <div className="stat-text">
        <small>{label}</small>
        <b>{count}</b>
        <span className="stat-unit">{unit}</span>
        {to && <span className="summary-link">{linkText} <ArrowRight size={16} aria-hidden="true" /></span>}
      </div>
      {to && <span className="stat-go" aria-hidden="true"><ArrowRight size={18} /></span>}
    </>
  );
  const className = `summary-card stat-card${tone ? ` is-${tone}` : ''}`;
  return to ? (
    <Link to={to} className={`${className} is-link`} aria-label={`${label}: ${count} ${unit}`}>{content}</Link>
  ) : (
    <div className={className}>{content}</div>
  );
}

/** El panel depende del rol: el operador tiene su pantalla de trabajo; propietario y moderador, la de administración y supervisión. */
export function InstitutionOverview() {
  const { institution } = useOutletContext();
  return institution.rolInstitucion === 'OPERADOR' ? <OperatorOverview /> : <ManagementOverview />;
}

function ManagementOverview() {
  const { institution, handleOperationError } = useOutletContext();
  const showTeam = can(institution, 'CONSULTAR_EQUIPO');
  const devices = useDeviceCount(institution);
  const canAddModerator = can(institution, 'GESTIONAR_MODERADORES');
  const canAddPatient = can(institution, 'GESTIONAR_PACIENTES');
  const canManageStaff = can(institution, 'CONSULTAR_EQUIPO');
  const canManageMatrices = can(institution, 'GESTIONAR_MATRICES');
  const canSeeDevices = devices !== undefined;

  const canAdminister = canAddModerator || can(institution, 'ADMINISTRAR_OPERADORES') || can(institution, 'CONSULTAR_AUDITORIA');
  const base = `/app/instituciones/${institution.idInstitucion}`;

  return (
    <>
      {canAdminister && (
        <section className="panel" aria-labelledby="inst-admin">
          <div className="panel-head">
            <div className="panel-title">
              <span className="panel-icon is-lg" aria-hidden="true"><Settings2 size={26} /></span>
              <div>
                <h2 id="inst-admin">Administración institucional</h2>
                <p>Administrá los datos de la institución, incorporá y gestioná a los moderadores y supervisá a los operadores.</p>
              </div>
            </div>
            <span className="admin-updated">Última actualización: {formatDateTime(institution.fechaActualizacion)}</span>
          </div>
          <div className="admin-actions">
            <AdminAction to={`${base}/administracion/datos`} icon={Building2} title="Datos institucionales" text="Consultá o editá el nombre, tipo y descripción." />
            {canAddModerator && (
              <AdminAction to={`${base}/personal/moderadores`} icon={UsersRound} title="Moderadores" text="Designá y administrá a los moderadores." />
            )}
            {can(institution, 'ADMINISTRAR_OPERADORES') && (
              <AdminAction to={`${base}/personal/operadores`} icon={UserRound} title="Operadores" text="Supervisá a los operadores de la institución." />
            )}
            {can(institution, 'CONSULTAR_AUDITORIA') && (
              <AdminAction to={`${base}/auditoria`} icon={ShieldCheck} title="Auditoría" text="Revisá las operaciones realizadas." />
            )}
          </div>
        </section>
      )}

      {(canManageStaff || canAddPatient || canManageMatrices || canSeeDevices) && (
        <section className="panel quick-panel" aria-labelledby="inst-acciones">
          <div className="quick-head">
            <span className="panel-icon is-lg" aria-hidden="true"><Zap size={26} /></span>
            <div>
              <h2 id="inst-acciones">Accesos rápidos</h2>
              <p>Acciones frecuentes para gestionar tu institución.</p>
            </div>
          </div>
          <div className="quick-actions">
            {canManageStaff && (
              <Link to="personal" className="btn btn-primary">
                <UsersRound size={18} aria-hidden="true" /> Administrar personal
              </Link>
            )}
            {canAddPatient && (
              <Link to="pacientes" className={`btn ${canManageStaff ? 'btn-outline' : 'btn-primary'}`}>
                <HeartPulse size={18} aria-hidden="true" /> Administrar paciente
              </Link>
            )}
            {canManageMatrices && (
              <Link to="matrices" className="btn btn-outline">
                <ChartColumn size={18} aria-hidden="true" /> Administrar matrices glucosa
              </Link>
            )}
            {canSeeDevices && (
              <Link to="dispositivos" className="btn btn-outline">
                <Settings size={18} aria-hidden="true" /> Ver inventario
              </Link>
            )}
          </div>
          {canAddModerator && institution.cantidadModeradores === 0 && (
            <p className="field-hint quick-note">
              Los operadores los incorporan los moderadores: empezá designando un moderador.
            </p>
          )}
        </section>
      )}

      <section className="summary-grid stat-grid" aria-label="Resumen de la institución">
        {can(institution, 'CONSULTAR_PACIENTES') && (
          <StatCard icon={HeartPulse} label="Pacientes" count={institution.cantidadPacientes} unit={institution.cantidadPacientes === 1 ? 'activo' : 'activos'}
            to="pacientes" linkText={canAddPatient ? 'Gestionar' : 'Consultar'} />
        )}
        {canSeeDevices && (
          <StatCard icon={Cpu} tone="blue" label="Dispositivos" count={devices === null ? '—' : devices} unit={devices === 1 ? 'registrado' : 'registrados'}
            to="dispositivos" linkText="Ver inventario" />
        )}
        {showTeam && (
          <>
            <StatCard icon={UserRound} tone="green" label="Operadores" count={institution.cantidadOperadores}
              unit={institution.cantidadOperadores === 1 ? 'activo' : 'activos'}
              to={can(institution, 'ADMINISTRAR_OPERADORES') ? 'personal/operadores' : null} linkText="Gestionar" />
            <StatCard icon={Crown} tone="amber" label="Moderadores" count={institution.cantidadModeradores}
              unit={institution.cantidadModeradores === 1 ? 'activo' : 'activos'}
              to={can(institution, 'GESTIONAR_MODERADORES') ? 'personal/moderadores' : null} linkText="Gestionar" />
          </>
        )}
      </section>

      {showTeam && <PendingReassignmentsSection institution={institution} />}
      {showTeam && <QuotaSection institution={institution} />}
      {showTeam && <ManagementDashboard institution={institution} handleOperationError={handleOperationError} />}
      <InstitutionActivity institution={institution} />
    </>
  );
}
