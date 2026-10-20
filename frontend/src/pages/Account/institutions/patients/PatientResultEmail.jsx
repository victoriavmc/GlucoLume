// Correo del paciente para recibir sus resultados (opcional). El paciente no tiene cuenta: el operador responsable carga el correo que le
// dio, declarando que lo autorizó, y el PACIENTE confirma la dirección desde el enlace que recibe (GL-08): recién entonces se guarda y
// empieza a recibir cada medición que se guarde. El correo se conserva 12 meses desde que se confirma, y se puede cambiar (mismo camino)
// o quitar. Solo se muestra enmascarado; el backend es quien valida permisos, autorización, confirmación y plazo.

import { Mail, Pencil, Trash2 } from 'lucide-react';
import { useState } from 'react';

import * as institutionsApi from '../../../../api/institutionsApi.js';
import { Alert, CheckField, TextField } from '../../../../components/FormControls.jsx';
import { formatDate } from '../institutionFormat.js';

export function PatientResultEmail({ institution, patient, onChanged, handleOperationError }) {
  const stored = patient.correoResultados ?? null;
  const [editing, setEditing] = useState(false);
  const [confirmingRemove, setConfirmingRemove] = useState(false);
  const [email, setEmail] = useState('');
  const [authorized, setAuthorized] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const showForm = !stored || editing;

  function reset() {
    setEmail('');
    setAuthorized(false);
    setEditing(false);
    setConfirmingRemove(false);
  }

  async function save() {
    if (busy) return;
    if (!email.trim() || !authorized) {
      setError('Ingresá el correo del paciente y confirmá que autorizó recibir sus resultados.');
      return;
    }
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const updated = await institutionsApi.setPatientResultEmail(institution.idInstitucion, patient.idPerfilMedicion,
        { correo: email.trim(), pacienteAutoriza: true });
      onChanged(updated);
      setNotice(`Enviamos un correo a ${updated.correoResultadosPendiente ?? 'esa dirección'} para que el paciente la confirme (el enlace vence en `
        + `72 horas). Se guarda cuando la confirma y el plazo de 12 meses cuenta desde ese momento.`
        + (stored ? ' Hasta entonces sigue vigente el correo anterior.' : ''));
      reset();
    } catch (saveError) {
      setError(handleOperationError(saveError));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (busy) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      onChanged(await institutionsApi.clearPatientResultEmail(institution.idInstitucion, patient.idPerfilMedicion));
      setNotice('Quitamos el correo del paciente: ya no recibirá resultados automáticos.');
      reset();
    } catch (removeError) {
      setError(handleOperationError(removeError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <fieldset className="form-section result-email">
      <legend><Mail size={18} aria-hidden="true" /> Resultados por correo (opcional)</legend>
      <p className="field-hint">
        Si el paciente lo autoriza, recibe por correo dónde se midió y los valores de cada medición que se guarde: oximetría, glucosa experimental
        y también las pruebas DEMO (el correo las identifica como simuladas). Al cargarlo, el paciente recibe un enlace para confirmar que la
        dirección es suya: sin esa confirmación no recibe nada. El correo se conserva 12 meses desde que lo confirma, y podés cambiarlo o quitarlo cuando quieras.
      </p>
      {error && <Alert>{error}</Alert>}
      {notice && <Alert kind="success">{notice}</Alert>}
      {stored && !editing && (
        <div className="result-email-current">
          <p>
            <b>Correo cargado:</b> <span>{stored}</span>
            {patient.correoResultadosVence && <> · vence el {formatDate(patient.correoResultadosVence)}</>}
          </p>
          <div className="form-actions">
            {confirmingRemove ? (
              <>
                <span className="field-hint">¿Quitar el correo? El paciente deja de recibir resultados.</span>
                <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => setConfirmingRemove(false)}>Volver</button>
                <button type="button" className="btn btn-outline" disabled={busy} onClick={remove}>Confirmar</button>
              </>
            ) : (
              <>
                <button type="button" className="btn btn-outline" disabled={busy} onClick={() => { setNotice(''); setEditing(true); }}>
                  <Pencil size={16} aria-hidden="true" /> Cambiar correo
                </button>
                <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => { setNotice(''); setConfirmingRemove(true); }}>
                  <Trash2 size={16} aria-hidden="true" /> Quitar correo
                </button>
              </>
            )}
          </div>
        </div>
      )}
      {showForm && (
        <div className="result-email-form">
          <TextField label={stored ? 'Nuevo correo del paciente' : 'Correo del paciente'} type="email" maxLength={254} autoComplete="off"
            value={email} onChange={(event) => setEmail(event.target.value)}
            onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); save(); } }} />
          <CheckField label="El paciente autorizó recibir sus resultados por correo durante 12 meses."
            checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} />
          <div className="form-actions">
            {editing && <button type="button" className="btn btn-ghost" disabled={busy} onClick={reset}>Cancelar</button>}
            <button type="button" className="btn btn-outline" disabled={busy} onClick={save}>
              {busy && <span className="spinner" aria-hidden="true" />} Enviar confirmación al paciente
            </button>
          </div>
        </div>
      )}
    </fieldset>
  );
}
