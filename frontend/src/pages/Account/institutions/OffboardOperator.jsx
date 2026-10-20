// Reasignación obligatoria de pacientes antes de desvincular a un operador (propietario y moderador).
// Un operador con pacientes a cargo no se desvincula directamente: acá se elige quién se hace cargo de cada paciente (todos con un operador o
// repartidos entre varios), se revisa un resumen y recién al confirmar FastAPI reasigna y desvincula en una sola operación. Si se cancela, no
// cambia nada. Nunca se asigna a nadie de forma automática; la validación real (todos los pacientes, destinos activos, transferencias
// pendientes, concurrencia) la hace el backend en cada llamada.

import { ArrowRightLeft, TriangleAlert } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import * as institutionsApi from '../../../api/institutionsApi.js';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Badge } from '../../../components/Badge.jsx';
import { Alert, RadioField, SelectField, TextAreaField } from '../../../components/FormControls.jsx';
import { Modal } from '../../../components/Modal.jsx';
import { PatientIdentity } from '../../../components/PatientIdentity.jsx';

const fullName = (item) => [item.nombre, item.apellido].filter(Boolean).join(' ') || null;
const plural = (count, one, many) => `${count} ${count === 1 ? one : many}`;

export function OffboardOperator({ institution, operatorId, operatorName, initialPlan = null, onClose, onDone }) {
  const [plan, setPlan] = useState(initialPlan);
  const [mode, setMode] = useState('all'); // all = todos con un mismo operador; split = uno por paciente
  const [target, setTarget] = useState('');
  const [perPatient, setPerPatient] = useState({});
  const [note, setNote] = useState('');
  const [step, setStep] = useState('choose'); // choose -> summary
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadPlan = useCallback(async () => {
    try {
      setPlan(await institutionsApi.getOperatorOffboarding(institution.idInstitucion, operatorId));
      setError('');
    } catch (loadError) {
      setError(friendlyError(loadError));
    }
  }, [institution.idInstitucion, operatorId]);

  useEffect(() => { if (!initialPlan) loadPlan(); }, [initialPlan, loadPlan]);

  const patients = plan?.pacientes ?? [];
  const targets = plan?.destinos ?? [];
  const targetName = useMemo(() => Object.fromEntries(targets.map((item) => [item.idInstitucionUsuario, item.operador ?? 'Operador'])), [targets]);
  const assignment = useMemo(() => {
    const result = {};
    patients.forEach((patient) => {
      const chosen = mode === 'all' ? target : perPatient[patient.idPerfilMedicion];
      if (chosen) result[patient.idPerfilMedicion] = chosen;
    });
    return result;
  }, [patients, mode, target, perPatient]);
  const complete = patients.length > 0 && patients.every((patient) => assignment[patient.idPerfilMedicion]);
  const summary = useMemo(() => {
    const counts = {};
    Object.values(assignment).forEach((id) => { counts[id] = (counts[id] ?? 0) + 1; });
    return Object.entries(counts).map(([id, count]) => ({ id, count, name: targetName[id] ?? 'Operador' }));
  }, [assignment, targetName]);

  async function confirm() {
    setBusy(true);
    setError('');
    try {
      const result = await institutionsApi.offboardOperator(institution.idInstitucion, operatorId, {
        asignaciones: patients.map((patient) => ({ idPerfilMedicion: patient.idPerfilMedicion, idOperadorNuevo: assignment[patient.idPerfilMedicion] })),
        ...(note.trim() ? { observacion: note.trim() } : {}),
      });
      onDone(result);
    } catch (offboardError) {
      setError(friendlyError(offboardError));
      setBusy(false);
      setStep('choose');
      // La lista pudo cambiar (otro gestor reasignó o dio de alta a un paciente): se vuelve a consultar para no insistir con datos viejos.
      if (['REASIGNACION_DESACTUALIZADA', 'REASIGNACION_INCOMPLETA', 'PACIENTE_EN_TRANSFERENCIA', 'SIN_OPERADOR_DISPONIBLE'].includes(offboardError?.codigo)) loadPlan();
    }
  }

  const blocked = plan?.bloqueo;
  let actions = <button type="button" className="btn btn-ghost" onClick={onClose}>Cerrar</button>;
  if (plan && !blocked && step === 'choose') {
    actions = (
      <>
        <button type="button" className="btn btn-ghost" disabled={busy} onClick={onClose}>Cancelar</button>
        <button type="button" className="btn btn-primary" disabled={!complete} onClick={() => { setError(''); setStep('summary'); }}>Revisar resumen</button>
      </>
    );
  } else if (plan && !blocked && step === 'summary') {
    actions = (
      <>
        <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => setStep('choose')}>Volver</button>
        <button type="button" className="btn btn-primary risk-button" disabled={busy} aria-busy={busy || undefined} onClick={confirm}>
          {busy && <span className="spinner" aria-hidden="true" />} Confirmar reasignación y desvincular
        </button>
      </>
    );
  }

  return (
    <Modal title="Reasignación de pacientes" role="dialog" onClose={busy ? () => {} : onClose} actions={actions}>
      <div className="offboard">
        <p className="offboard-operator">
          <ArrowRightLeft size={18} aria-hidden="true" /> Operador a desvincular: <b>{plan?.operador ?? operatorName}</b>
        </p>
        {error && <Alert>{error}</Alert>}
        {!plan && !error && <div className="auth-status" role="status"><span className="spinner" aria-hidden="true" /> Consultando pacientes…</div>}

        {plan && (
          <>
            <Alert kind="info">
              Este operador tiene pacientes asignados. Antes de desvincularlo, debés reasignarlos.
              {' '}Pacientes pendientes de reasignación: <b>{plan.cantidadPacientes}</b>.
            </Alert>

            {blocked === 'SIN_OPERADOR_DISPONIBLE' && (
              <Alert>
                No hay otro operador habilitado que pueda recibir a los pacientes. Primero incorporá o habilitá un responsable; hasta entonces
                el operador sigue vinculado.
              </Alert>
            )}
            {blocked === 'TRANSFERENCIAS_PENDIENTES' && (
              <Alert>
                {plural(plan.transferenciasPendientes, 'paciente tiene', 'pacientes tienen')} una transferencia pendiente de aceptación y siguen a cargo
                de este operador hasta que se resuelva. Esperá la respuesta del operador destinatario o pedí que se cancele la solicitud.
              </Alert>
            )}

            {step === 'choose' && (
              <>
                {!blocked && (
                  <>
                    <fieldset className="offboard-mode">
                      <legend>¿Cómo querés reasignarlos?</legend>
                      <RadioField name="offboard-mode" label="Todos a un mismo operador" checked={mode === 'all'} onChange={() => setMode('all')} />
                      <RadioField name="offboard-mode" label="Distribuir entre varios operadores" checked={mode === 'split'} onChange={() => setMode('split')} />
                    </fieldset>
                    <SelectField label={mode === 'all' ? 'Nuevo operador responsable' : 'Asignar todos a… (atajo)'}
                      value={mode === 'all' ? target : ''}
                      onChange={(event) => {
                        const value = event.target.value;
                        if (mode === 'all') setTarget(value);
                        else if (value) setPerPatient(Object.fromEntries(patients.map((patient) => [patient.idPerfilMedicion, value])));
                      }}>
                      <option value="">Elegí un operador activo…</option>
                      {targets.map((item) => (
                        <option key={item.idInstitucionUsuario} value={item.idInstitucionUsuario}>
                          {item.operador ?? 'Operador'} ({plural(item.pacientesActuales, 'paciente', 'pacientes')} hoy)
                        </option>
                      ))}
                    </SelectField>
                  </>
                )}
                <ul className="member-list offboard-patients" aria-label="Pacientes a reasignar">
                  {patients.map((patient) => (
                    <li key={patient.idPerfilMedicion} className="member-row">
                      <PatientIdentity name={fullName(patient)} code={patient.identificadorPseudonimo} available={fullName(patient) ? true : false} />
                      {patient.transferenciaPendiente && <Badge tone="warning">Transferencia pendiente</Badge>}
                      {!blocked && mode === 'split' && (
                        <SelectField label="Nuevo responsable" value={perPatient[patient.idPerfilMedicion] ?? ''}
                          onChange={(event) => setPerPatient((current) => ({ ...current, [patient.idPerfilMedicion]: event.target.value }))}>
                          <option value="">Elegí…</option>
                          {targets.map((item) => (
                            <option key={item.idInstitucionUsuario} value={item.idInstitucionUsuario}>{item.operador ?? 'Operador'}</option>
                          ))}
                        </SelectField>
                      )}
                    </li>
                  ))}
                </ul>
                {!blocked && <TextAreaField label="Motivo (opcional)" rows={2} maxLength={500} value={note} onChange={(event) => setNote(event.target.value)} />}
              </>
            )}

            {step === 'summary' && (
              <section aria-labelledby="offboard-resumen">
                <h3 id="offboard-resumen"><TriangleAlert size={18} aria-hidden="true" /> Resumen de la reasignación</h3>
                <ul className="offboard-summary">
                  {summary.map((item) => (
                    <li key={item.id}><b>{plural(item.count, 'paciente', 'pacientes')}</b> pasan a cargo de <b>{item.name}</b></li>
                  ))}
                </ul>
                <p className="field-hint">
                  Al confirmar, <b>{plan.operador ?? operatorName}</b> deja de pertenecer a la institución. Las mediciones que ya realizó conservan su autoría.
                  Si cancelás, nada cambia y el operador sigue vinculado.
                </p>
              </section>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}
