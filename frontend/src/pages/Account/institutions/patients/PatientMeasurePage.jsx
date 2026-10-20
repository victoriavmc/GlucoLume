// /app/instituciones/:id/pacientes/:idPerfilMedicion/medir — medición de un paciente a cargo del operador, en UNA sola pantalla:
// datos del paciente → configuración → estado del dispositivo → señal en vivo → resultado y guardado. Reutiliza el mismo
// DeviceMonitor (modo completo) que la cuenta individual; el backend vuelve a verificar que el paciente sea de la institución
// y esté a cargo de quien mide, y la medición queda asociada al paciente (nunca al operador).

import { ArrowLeft, CheckCircle2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useOutletContext, useParams } from 'react-router-dom';

import * as institutionsApi from '../../../../api/institutionsApi.js';
import { Alert } from '../../../../components/FormControls.jsx';
import { ExperimentalNotice } from '../../../../components/ExperimentalNotice.jsx';
import { DeviceMonitor } from '../../measurements/DeviceMonitor.jsx';
import { PatientMeasurementCard, patientMeasurementProfile } from './PatientMeasurementCard.jsx';
import { PatientResultEmail } from './PatientResultEmail.jsx';

export function PatientMeasurePage() {
  const { institution, handleOperationError } = useOutletContext();
  const { idPerfilMedicion } = useParams();
  const [patient, setPatient] = useState(null);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(null); // medición recién guardada (estado final del flujo)

  useEffect(() => {
    institutionsApi.getPatient(institution.idInstitucion, idPerfilMedicion).then(setPatient, (loadError) => {
      setError(handleOperationError(loadError));
    });
  }, [institution.idInstitucion, idPerfilMedicion, handleOperationError]);

  const profile = useMemo(() => (patient ? patientMeasurementProfile(patient) : null), [patient]);
  const canMeasure = Boolean(patient && patient.estado === 'ACTIVO' && patient.puedeModificar && patient.medicionesAutorizadas);

  return (
    <>
      <Link to=".." relative="path" className="back-link">
        <ArrowLeft size={16} aria-hidden="true" /> Paciente
      </Link>
      {error && <Alert>{error}</Alert>}
      {!patient && !error && <p className="field-hint" role="status">Cargando paciente…</p>}
      {patient && <PatientMeasurementCard patient={patient} institution={institution} />}
      {patient && patient.estado !== 'ACTIVO' && <Alert>El paciente está dado de baja: no se pueden iniciar mediciones.</Alert>}
      {patient && patient.estado === 'ACTIVO' && !canMeasure && (
        <Alert>Solo el operador responsable del paciente puede iniciar mediciones.</Alert>
      )}
      {canMeasure && saved && (
        <section className="panel save-confirmation" aria-labelledby="medicion-guardada">
          <div className="panel-title">
            <span className="panel-icon"><CheckCircle2 size={22} aria-hidden="true" /></span>
            <div>
              <h2 id="medicion-guardada">Medición guardada</h2>
              <p>
                Quedó asociada al paciente {patient.identificadorPseudonimo} y figura en su historial.
                {saved.esDemo && ' Es una medición de prueba (DEMO): no suma a los indicadores de salud.'}
              </p>
            </div>
          </div>
          {saved.envioAutomatico === 'ENVIADO' && (
            <Alert kind="success">Enviamos el resultado por correo al paciente ({patient.correoResultados}): dónde se midió y los valores.</Alert>
          )}
          {saved.envioAutomatico === 'FALLIDO' && (
            <Alert>No pudimos enviar el correo automático al paciente. La medición quedó guardada: podés reenviarlo desde el detalle de la medición.</Alert>
          )}
          <div className="form-actions">
            <Link to={`../mediciones/${saved.idMedicion}`} relative="path" className="btn btn-primary">Ver medición</Link>
            <Link to=".." relative="path" className="btn btn-outline">Volver al paciente</Link>
          </div>
        </section>
      )}
      {canMeasure && !saved && (
        <DeviceMonitor patient idPerfilMedicion={patient.idPerfilMedicion} idInstitucion={institution.idInstitucion} profile={profile}
          profileLabel={patient.identificadorPseudonimo ?? 'Paciente'} handleOperationError={handleOperationError}
          savingSteps={patient.correoResultados ? ['Enviando el resultado por correo al paciente'] : []}
          extraOptions={<PatientResultEmail institution={institution} patient={patient} onChanged={setPatient} handleOperationError={handleOperationError} />}
          onSaved={setSaved} onCancelled={() => setSaved(null)} />
      )}
      <ExperimentalNotice variant="inline" />
    </>
  );
}
