// «Transferir paciente»: solicitud al operador destinatario. El paciente sigue a cargo del solicitante hasta que el
// destinatario acepte (Transferencias recibidas). Solo se ofrece al operador responsable; el backend lo vuelve a validar.

import { ArrowRightLeft } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import * as institutionsApi from '../../../../api/institutionsApi.js';
import { Alert, SelectField, SubmitButton, TextField } from '../../../../components/FormControls.jsx';

export function TransferPatient({ institution, patient, handleOperationError }) {
  const [operators, setOperators] = useState(null);
  const [selected, setSelected] = useState('');
  const [observation, setObservation] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [sent, setSent] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    institutionsApi.getAssignableOperators(institution.idInstitucion).then(
      (list) => setOperators(list.filter((operator) => operator.idInstitucionUsuario !== patient.responsable.idInstitucionUsuario)),
      (loadError) => { setOperators([]); setError(handleOperationError(loadError)); },
    );
  }, [institution.idInstitucion, patient.responsable.idInstitucionUsuario, handleOperationError]);

  async function submit() {
    setSaving(true);
    setError('');
    try {
      await institutionsApi.requestTransfer(institution.idInstitucion, patient.idPerfilMedicion, {
        idOperadorDestino: selected, observacion: observation.trim(),
      });
      setSent(true);
      setConfirming(false);
    } catch (transferError) {
      setError(handleOperationError(transferError));
    } finally {
      setSaving(false);
    }
  }

  const target = operators?.find((operator) => operator.idInstitucionUsuario === selected);

  return (
    <section className="panel" aria-labelledby="paciente-transferir">
      <div className="panel-title">
        <span className="panel-icon"><ArrowRightLeft size={22} aria-hidden="true" /></span>
        <div>
          <h2 id="paciente-transferir">Transferir paciente</h2>
          <p>El paciente sigue a tu cargo hasta que el otro operador acepte la solicitud.</p>
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      {sent ? (
        <Alert kind="success">
          Enviamos la solicitud. Podés seguirla o cancelarla en <Link to="../../transferencias" relative="path">Transferencias</Link>.
        </Alert>
      ) : operators === null ? (
        <p className="field-hint" role="status">Cargando operadores…</p>
      ) : operators.length === 0 ? (
        <p className="field-hint">No hay otros operadores activos en la institución para recibir al paciente.</p>
      ) : (
        <>
          <SelectField label="Operador destinatario" value={selected} onChange={(event) => { setSelected(event.target.value); setConfirming(false); }}>
            <option value="">Elegí un operador</option>
            {operators.map((operator) => (
              <option key={operator.idInstitucionUsuario} value={operator.idInstitucionUsuario}>
                {[operator.nombre, operator.apellido].filter(Boolean).join(' ')}
              </option>
            ))}
          </SelectField>
          <TextField label="Observación (opcional)" maxLength={500} value={observation}
            onChange={(event) => setObservation(event.target.value)} />
          <div className="form-actions">
            {confirming ? (
              <>
                <span className="field-hint">
                  ¿Pedirle a {[target?.nombre, target?.apellido].filter(Boolean).join(' ')} que se haga cargo del paciente?
                </span>
                <button type="button" className="btn btn-ghost" disabled={saving} onClick={() => setConfirming(false)}>Volver</button>
                <SubmitButton type="button" loading={saving} loadingLabel="Enviando…" className="btn btn-primary" onClick={submit}>
                  Confirmar transferencia
                </SubmitButton>
              </>
            ) : (
              <button type="button" className="btn btn-outline" disabled={!selected} onClick={() => setConfirming(true)}>
                Transferir paciente
              </button>
            )}
          </div>
        </>
      )}
    </section>
  );
}
