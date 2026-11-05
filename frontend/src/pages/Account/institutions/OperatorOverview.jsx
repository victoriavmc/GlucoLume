// Panel del OPERADOR/A: una pantalla de trabajo individual. Solo lo que su rol permite: sus pacientes, nuevas mediciones, su propia
// actividad y sus indicadores y transferencias. No muestra estadísticas generales de la institución, personal, matrices, inventario ni
// auditoría. Todo lo que llega está filtrado en FastAPI por el usuario autenticado y su vínculo (no por nombre, ni en React).

import { HeartPulse, Play, Zap } from 'lucide-react';
import { Link, useOutletContext } from 'react-router-dom';

import { Alert } from '../../../components/FormControls.jsx';
import {
  AssignedPatientsPanel, OperatorKpiPanel, OperatorWorkCards, useOperatorCharts, useOperatorDashboard,
} from './dashboard/InstitutionDashboards.jsx';
import { OperatorChartsSection } from './dashboard/OperatorCharts.jsx';
import { InstitutionActivity } from './InstitutionActivity.jsx';
import { can } from './institutionFormat.js';

export function OperatorOverview() {
  const { institution, handleOperationError } = useOutletContext();
  const canManagePatients = can(institution, 'GESTIONAR_PACIENTES');
  const { data, error, period, setPeriod } = useOperatorDashboard(institution, 'me', handleOperationError);
  // Los gráficos se piden aparte: los indicadores y los pacientes no esperan a la consulta más pesada.
  const charts = useOperatorCharts(institution, period, handleOperationError);
  return (
    <>
      {canManagePatients && (
        <section className="panel quick-panel" aria-labelledby="inst-acciones">
          <div className="quick-head">
            <span className="panel-icon is-lg" aria-hidden="true"><Zap size={26} /></span>
            <div>
              <h2 id="inst-acciones">Accesos rápidos</h2>
              <p>Acciones frecuentes de tu trabajo diario.</p>
            </div>
          </div>
          <div className="quick-actions">
            <Link to="pacientes?mios=1" className="btn btn-primary">
              <HeartPulse size={18} aria-hidden="true" /> Administrar mis pacientes
            </Link>
            <Link to="pacientes?mios=1&medir=1" className="btn btn-outline">
              <Play size={18} aria-hidden="true" /> Nueva medición
            </Link>
          </div>
        </section>
      )}
      <OperatorKpiPanel institution={institution} data={data} error={error} period={period} setPeriod={setPeriod} />
      {data && (charts.error ? <Alert>{charts.error}</Alert>
        : charts.loaded ? <OperatorChartsSection institution={institution} data={{ ...data, graficos: charts.charts }} />
          : <p className="field-hint" role="status">Cargando gráficos…</p>)}
      <div className="op-columns">
        <InstitutionActivity institution={institution} />
        {data && <AssignedPatientsPanel institution={institution} data={data} />}
      </div>
      {data && <OperatorWorkCards data={data} institution={institution} />}
    </>
  );
}
