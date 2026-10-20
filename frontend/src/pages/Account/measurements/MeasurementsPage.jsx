// /app/mediciones — «Mediciones» (cuentas individuales), organizado en cuatro pantallas que se muestran de a una:
//   · Mi dashboard (esta página): indicadores, promedios del período y mediciones recientes.
//   · /app/mediciones/nueva      → Nueva medición con el dispositivo (NewMeasurementPage).
//   · /app/mediciones/perfil     → Configuración de perfil y autorización de almacenamiento (MeasurementProfilePage).
//   · /app/mediciones/historial  → Historial completo con filtros (MeasurementHistoryPage).
// El backend resuelve siempre el perfil de la sesión: aquí no se elige el perfil de otra persona. Lo que otros integrantes
// del grupo ven de estos datos lo decide «Mi privacidad» en Grupo.

import { ArrowLeft, ChevronLeft } from 'lucide-react';
import { Link, Navigate, useOutletContext, useParams } from 'react-router-dom';

import { useAuth } from '../../../auth/AuthContext.jsx';
import { friendlyError } from '../../../auth/errorMessages.js';
import { ExperimentalNotice } from '../../../components/ExperimentalNotice.jsx';
import { Alert } from '../../../components/FormControls.jsx';
import { PageHeader } from '../../../components/PageHeader.jsx';
import { MeasurementPanel } from './MeasurementPanel.jsx';
import { PersonalDashboard } from './PersonalDashboard.jsx';
import { RecommendedNotice } from './RecommendedNotice.jsx';
import { useOwnMeasurementProfile } from './useOwnMeasurementProfile.js';

/** Solo las cuentas individuales tienen «Mediciones» propias. */
export function useIndividualOnly() {
  const { account } = useAuth();
  return account.usuario.tipoCuenta === 'CONSUMIDOR_FINAL';
}

/** Marco común de las pantallas internas de Mediciones: título y regreso al dashboard. */
export function MeasurementsScreen({ title, subtitle, children }) {
  return (
    <div className="page">
      <PageHeader title={title} description={subtitle} back={{ to: '/app/mediciones', label: 'Mi dashboard' }} />
      {children}
    </div>
  );
}

export function MeasurementsPage() {
  const individual = useIndividualOnly();
  const { profile } = useOwnMeasurementProfile({ enabled: individual });

  if (!individual) return <Navigate to="/app/inicio" replace />;

  return (
    <div className="page is-wide">
      <RecommendedNotice profile={profile} />
      <PersonalDashboard handleOperationError={friendlyError} />
      <ExperimentalNotice />
    </div>
  );
}

/** /app/mediciones/:idMedicion */
export function MeasurementDetailPage({ handleOperationError }) {
  const { idMedicion } = useParams();
  return (
    <div className="page">
      <header className="md-page-head">
        <Link to="/app/mediciones/historial" className="md-back" aria-label="Volver al historial"><ChevronLeft size={26} aria-hidden="true" /></Link>
        <div>
          <h1>Detalle de medición</h1>
          <p>Información completa de la medición y su análisis</p>
        </div>
        <nav className="detail-nav" aria-label="Navegación">
          <Link to="/app/mediciones" className="back-link">Volver a mi dashboard</Link>
          <Link to="/app/mediciones#evolucion" className="back-link">Ver evolución histórica</Link>
        </nav>
      </header>
      <MeasurementPanel idMedicion={idMedicion} profileLabel="Mi perfil" handleOperationError={handleOperationError ?? friendlyError} />
    </div>
  );
}

/** Detalle dentro del panel de una institución (usa su manejo de errores de permisos). */
export function InstitutionMeasurementDetail() {
  const { handleOperationError } = useOutletContext();
  const { idMedicion } = useParams();
  return (
    <>
      <Link to="../.." relative="path" className="back-link">
        <ArrowLeft size={16} aria-hidden="true" /> Paciente
      </Link>
      <MeasurementPanel idMedicion={idMedicion} profileLabel="Paciente" handleOperationError={handleOperationError} />
    </>
  );
}
