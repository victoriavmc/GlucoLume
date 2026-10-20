// Pantallas internas de «Mediciones» de una cuenta individual (se muestran de a una, con regreso al dashboard):
//   · NewMeasurementPage        /app/mediciones/nueva     — dispositivo, lecturas en vivo, datos opcionales e inicio/guardado.
//   · MeasurementProfilePage    /app/mediciones/perfil    — perfil de medición, edición de datos y autorización de almacenamiento.
//   · MeasurementHistoryPage    /app/mediciones/historial — historial completo con filtros.
// Reutilizan DeviceMonitor (adquisición), ProfileEditForm (datos del usuario), ExperimentalConsent y MeasurementHistory.

import { CheckCircle2, UserRound } from 'lucide-react';
import { useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';

import * as measurementsApi from '../../../api/measurementsApi.js';
import { useAuth } from '../../../auth/AuthContext.jsx';
import { friendlyError } from '../../../auth/errorMessages.js';
import { ExperimentalNotice } from '../../../components/ExperimentalNotice.jsx';
import { Alert } from '../../../components/FormControls.jsx';
import { ProfileEditForm } from '../ProfileEditForm.jsx';
import { DeviceMonitor } from './DeviceMonitor.jsx';
import { ExperimentalConsent } from './ExperimentalConsent.jsx';
import { MeasurementHistory } from './MeasurementHistory.jsx';
import { MeasurementsInfo } from './MeasurementsInfo.jsx';
import { MeasurementsScreen, useIndividualOnly } from './MeasurementsPage.jsx';
import { RecommendedNotice } from './RecommendedNotice.jsx';
import { SEXO, formatDate, formatDateTime } from './measurementFormat.js';
import { useOwnMeasurementProfile } from './useOwnMeasurementProfile.js';

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
          <Link to="/app/mediciones/perfil">Configuración de perfil</Link>.
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
          <RecommendedNotice profile={profile} />
          <DeviceMonitor idPerfilMedicion={profile.idPerfilMedicion} profileLabel="Mi perfil" profile={profile}
            handleOperationError={friendlyError}
            onSaved={setSavedMeasurement}
            onCancelled={() => navigate('/app/mediciones')} />
        </>
      )}
    </MeasurementsScreen>
  );
}

/** /app/mediciones/perfil */
export function MeasurementProfilePage() {
  const individual = useIndividualOnly();
  const { updateAccount, account } = useAuth();
  const { profile, consent, setConsent, error, reloadProfile } = useOwnMeasurementProfile({ enabled: individual });
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState('');
  if (!individual) return <Navigate to="/app/inicio" replace />;

  function saved(response) {
    updateAccount(response);
    setNotice(response.actualizado ? 'Se registraron los cambios.' : 'No se registraron cambios.');
    setEditing(false);
    reloadProfile(); // la edad y el sexo del perfil de medición salen de los datos de la cuenta
  }

  return (
    <MeasurementsScreen title="Configuración de perfil" subtitle="Tu perfil de medición se arma con los datos de tu cuenta.">
      {error && <Alert>{error}</Alert>}
      {notice && <Alert kind="success">{notice}</Alert>}
      {profile === null ? (
        <p className="field-hint" role="status">Cargando tu perfil…</p>
      ) : !profile.perfilDisponible ? (
        <Alert kind="info">Tu perfil de medición no está disponible en este momento. Probá de nuevo en unos minutos.</Alert>
      ) : editing ? (
        <ProfileEditForm account={account} onSaved={saved} onCancel={() => setEditing(false)} />
      ) : (
        <>
          <RecommendedNotice profile={profile} />
          <section className="panel" aria-labelledby="mediciones-perfil">
            <div className="panel-head">
              <div className="panel-title">
                <span className="panel-icon"><UserRound size={22} aria-hidden="true" /></span>
                <div>
                  <h2 id="mediciones-perfil">Mi perfil de medición</h2>
                  <p>La edad se calcula desde la fecha de nacimiento a la fecha de cada medición.</p>
                </div>
              </div>
              <button type="button" className="btn btn-outline" onClick={() => { setNotice(''); setEditing(true); }}>Editar datos</button>
            </div>
            <dl className="data-list">
              <div><dt>Nombre</dt><dd>{[profile.nombre, profile.apellido].filter(Boolean).join(' ')}</dd></div>
              <div><dt>Edad</dt><dd className={profile.edad === null ? 'is-empty' : undefined}>{profile.edad === null ? 'Sin informar' : `${profile.edad} años`}</dd></div>
              <div><dt>Fecha de nacimiento</dt><dd className={profile.fechaNacimiento ? undefined : 'is-empty'}>{profile.fechaNacimiento ? formatDate(profile.fechaNacimiento) : 'Sin informar'}</dd></div>
              <div><dt>Sexo biológico</dt><dd className={profile.sexoModelo ? undefined : 'is-empty'}>{profile.sexoModelo ? (SEXO[profile.sexoModelo] ?? profile.sexoModelo) : 'Sin informar'}</dd></div>
              <div>
                <dt>Última medición</dt>
                <dd className={profile.fechaUltimaMedicion ? undefined : 'is-empty'}>
                  {profile.fechaUltimaMedicion ? formatDateTime(profile.fechaUltimaMedicion) : 'Sin informar'}
                </dd>
              </div>
            </dl>
          </section>
          {consent === null ? (
            <p className="field-hint" role="status">Cargando tu autorización…</p>
          ) : (
            <ExperimentalConsent consent={consent} onChange={setConsent} />
          )}
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
      <MeasurementHistory loadPage={measurementsApi.getOwnHistory} detailPath={(id) => `/app/mediciones/${id}`}
        onDeleteDemo={measurementsApi.deleteOwnDemoMeasurements} handleOperationError={friendlyError}
        emptyText="Todavía no hiciste ninguna medición." />
      <MeasurementsInfo />
    </MeasurementsScreen>
  );
}
