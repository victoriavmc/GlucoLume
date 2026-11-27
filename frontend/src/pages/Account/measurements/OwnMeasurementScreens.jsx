// Pantallas internas de «Mediciones» de una cuenta individual (se muestran de a una, con regreso al dashboard):
//   · NewMeasurementPage        /app/mediciones/nueva     — dispositivo, lecturas en vivo, datos opcionales e inicio/guardado.
//   · MeasurementHistoryPage    /app/mediciones/historial — historial completo con filtros.
// Los datos personales y la autorización de almacenamiento viven en «Mi perfil» (/app/perfil), no aquí.
// Reutilizan DeviceMonitor (adquisición), MeasurementHistory y useOwnMeasurementProfile.

import { CheckCircle2 } from 'lucide-react';
import { useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';

import * as measurementsApi from '../../../api/measurementsApi.js';
import { friendlyError } from '../../../auth/errorMessages.js';
import { ExperimentalNotice } from '../../../components/ExperimentalNotice.jsx';
import { Alert } from '../../../components/FormControls.jsx';
import { DeviceMonitor } from './DeviceMonitor.jsx';
import { MeasurementHistory } from './MeasurementHistory.jsx';
import { MeasurementsInfo } from './MeasurementsInfo.jsx';
import { MeasurementsScreen, useIndividualOnly } from './MeasurementsPage.jsx';
import { useOwnMeasurementProfile } from './useOwnMeasurementProfile.js';
import { ageFrom, sexoLabel } from '../accountFormat.js';

// Lo que se muestra del perfil durante la medición: género y edad (no el nombre del perfil ni datos del dispositivo).
function ownProfileLabel(profile) {
  const edad = profile.edad ?? ageFrom(profile.fechaNacimiento);
  const partes = [sexoLabel(profile.sexoModelo), edad != null ? `${edad} años` : null].filter(Boolean);
  return partes.length ? partes.join(' · ') : 'Sin género ni edad cargados';
}

/** /app/mediciones/nueva */
export function NewMeasurementPage() {
  const individual = useIndividualOnly();
  const navigate = useNavigate();
  const [savedMeasurement, setSavedMeasurement] = useState(null); // medición recién guardada (estado final del flujo)
  const { profile, consent, error } = useOwnMeasurementProfile({ enabled: individual });
  if (!individual) return <Navigate to="/app/inicio" replace />;

  return (
    <MeasurementsScreen title="Nueva medición" subtitle="Conectá el dispositivo, completá los datos opcionales y pulsá «Iniciar medición».">
      <ExperimentalNotice />
      {error && <Alert>{error}</Alert>}
      {profile === null || consent === null ? (
        <p className="field-hint" role="status">Cargando tu perfil…</p>
      ) : !profile.perfilDisponible ? (
        <Alert kind="info">Tu perfil de medición no está disponible en este momento. Probá de nuevo en unos minutos.</Alert>
      ) : !consent.aceptado ? (
        <Alert kind="info">
          Para medir necesitamos tu autorización para almacenar mediciones experimentales. Podés otorgarla en{' '}
          <Link to="/app/perfil">Mi perfil</Link>.
        </Alert>
      ) : savedMeasurement ? (
        <section className="panel save-confirmation" aria-labelledby="medicion-guardada">
          <div className="panel-title">
            <span className="panel-icon"><CheckCircle2 size={22} aria-hidden="true" /></span>
            <div>
              <h2 id="medicion-guardada">Medición guardada</h2>
              <p>
                Quedó asociada a tu perfil y ya figura en tu dashboard e historial.
                {savedMeasurement.esDemo && ' Es una medición de prueba (DEMO): no suma a tus indicadores experimentales.'}
              </p>
            </div>
          </div>
          <div className="form-actions">
            <Link to={`/app/mediciones/${savedMeasurement.idMedicion}`} className="btn btn-primary">Ver medición</Link>
            <Link to="/app/mediciones" className="btn btn-outline">Volver a mi dashboard</Link>
          </div>
        </section>
      ) : (
        <>
          <DeviceMonitor idPerfilMedicion={profile.idPerfilMedicion} profileLabel={ownProfileLabel(profile)} profile={profile} autoConnect
            handleOperationError={friendlyError}
            onSaved={setSavedMeasurement}
            onCancelled={() => navigate('/app/mediciones')} />
        </>
      )}
    </MeasurementsScreen>
  );
}

/** /app/mediciones/historial */
export function MeasurementHistoryPage() {
  const individual = useIndividualOnly();
  if (!individual) return <Navigate to="/app/inicio" replace />;
  return (
    <MeasurementsScreen title="Historial de mediciones" subtitle="Todas tus mediciones, con filtros y estadísticas.">
      <MeasurementHistory loadPage={measurementsApi.getOwnHistory} detailPath={(id) => `/app/mediciones/${id}`} filtroCondicion
        onDeleteDemo={measurementsApi.deleteOwnDemoMeasurements} onDeleteOne={measurementsApi.deleteDemoMeasurement}
        onExport={measurementsApi.exportOwnMeasurements} handleOperationError={friendlyError}
        emptyText="Todavía no hiciste ninguna medición." />
      <MeasurementsInfo />
    </MeasurementsScreen>
  );
}
