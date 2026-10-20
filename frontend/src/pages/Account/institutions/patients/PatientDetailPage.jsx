// Detalle de un paciente: datos administrativos, edición, cambio de operador responsable y baja lógica. Las mediciones (última medición,
// historial, gráficos, estadísticas y registro) se muestran solo si `medicionesAutorizadas` (operador responsable vigente): para el resto
// del personal la ficha es solo administrativa y no se pide ni se dibuja nada de salud (el backend también lo rechaza).
// `puedeModificar` lo calcula el backend (un operador solo modifica los pacientes a su cargo); toda operación se
// valida otra vez en el servidor.

import { ArrowLeft, Pencil, Play, UserCog, UserMinus, UserRound } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useOutletContext, useParams } from 'react-router-dom';

import * as institutionsApi from '../../../../api/institutionsApi.js';
import * as measurementsApi from '../../../../api/measurementsApi.js';
import { Badge } from '../../../../components/Badge.jsx';
import { Alert, SubmitButton } from '../../../../components/FormControls.jsx';
import { ROLE_LABELS as ROLE_NAMES, SEXO_LABELS, can, formatDate, formatDateTime } from '../institutionFormat.js';
import {
  PatientFields, ResponsibleSelect, patientFieldErrors, patientFormFrom, patientPayload, validatePatient,
} from './PatientFields.jsx';
import { MeasurementHistory } from '../../measurements/MeasurementHistory.jsx';
import { TransferPatient } from './TransferPatient.jsx';
import { patientName } from './PatientsPage.jsx';

function Row({ label, children }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className={children ? undefined : 'is-empty'}>{children || 'Sin informar'}</dd>
    </div>
  );
}

function EditPatient({ institution, patient, onSaved, onCancel, handleOperationError }) {
  const [form, setForm] = useState(() => patientFormFrom(patient));
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  function update(field) {
    return (event) => {
      setForm((current) => ({ ...current, [field]: event.target.value }));
      if (fieldErrors[field]) setFieldErrors((current) => ({ ...current, [field]: undefined }));
    };
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving) return;
    const errors = validatePatient(form);
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    setSaving(true);
    setError('');
    try {
      onSaved(await institutionsApi.updatePatient(institution.idInstitucion, patient.idPerfilMedicion, patientPayload(form)),
        'Guardamos los cambios del paciente.');
    } catch (saveError) {
      const byField = patientFieldErrors(saveError);
      setFieldErrors(byField);
      if (!Object.keys(byField).length) setError(handleOperationError(saveError));
      setSaving(false);
    }
  }

  return (
    <form className="panel" onSubmit={handleSubmit} noValidate aria-labelledby="paciente-editar">
      <div className="panel-head">
        <h2 id="paciente-editar">Editar paciente</h2>
      </div>
      {error && <Alert>{error}</Alert>}
      <PatientFields form={form} update={update} errors={fieldErrors} />
      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={saving}>
          Cancelar
        </button>
        <SubmitButton loading={saving} loadingLabel="Guardando…" className="btn btn-primary">
          Guardar cambios
        </SubmitButton>
      </div>
    </form>
  );
}

function AssignResponsible({ institution, patient, onSaved, handleOperationError }) {
  const [operators, setOperators] = useState(null);
  const [selected, setSelected] = useState(patient.responsable.idInstitucionUsuario);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    institutionsApi.getAssignableOperators(institution.idInstitucion)
      .then(setOperators)
      .catch((loadError) => { setOperators([]); setError(handleOperationError(loadError)); });
  }, [institution.idInstitucion, handleOperationError]);

  async function assign(event) {
    event.preventDefault();
    if (saving || !selected || selected === patient.responsable.idInstitucionUsuario) return;
    setSaving(true);
    setError('');
    try {
      const updated = await institutionsApi.assignPatientResponsible(institution.idInstitucion, patient.idPerfilMedicion, selected);
      // Con un responsable activo el cambio es una propuesta: el responsable no cambia hasta que el operador destino la acepta.
      onSaved(updated, updated.responsable.idInstitucionUsuario === selected
        ? 'Cambiamos el operador responsable.'
        : 'Enviamos la propuesta al operador. El responsable cambiará cuando la acepte.');
    } catch (assignError) {
      setError(handleOperationError(assignError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="panel" onSubmit={assign} noValidate aria-labelledby="paciente-responsable">
      <div className="panel-title">
        <span className="panel-icon">
          <UserCog size={22} aria-hidden="true" />
        </span>
        <div>
          <h2 id="paciente-responsable">Operador responsable</h2>
          <p>Solo se puede asignar a operadores activos de esta institución. Si el paciente tiene un responsable activo, el cambio se envía como propuesta y se concreta cuando el operador elegido la acepta.</p>
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      {operators === null ? (
        <p className="field-hint" role="status">Cargando operadores…</p>
      ) : (
        <ResponsibleSelect label="Asignar a" operators={operators} value={selected}
          onChange={(event) => setSelected(event.target.value)} />
      )}
      <div className="form-actions">
        <SubmitButton loading={saving} loadingLabel="Asignando…" className="btn btn-primary"
          disabled={saving || !selected || selected === patient.responsable.idInstitucionUsuario}>
          Cambiar responsable
        </SubmitButton>
      </div>
    </form>
  );
}

function DischargePatient({ institution, patient, onSaved, handleOperationError }) {
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function discharge() {
    setSaving(true);
    setError('');
    try {
      onSaved(await institutionsApi.dischargePatient(institution.idInstitucion, patient.idPerfilMedicion),
        'El paciente quedó dado de baja.');
    } catch (dischargeError) {
      setError(handleOperationError(dischargeError));
      setSaving(false);
    }
  }

  return (
    <section className="panel is-danger" aria-labelledby="paciente-baja">
      <div className="panel-title">
        <span className="panel-icon">
          <UserMinus size={22} aria-hidden="true" />
        </span>
        <div>
          <h2 id="paciente-baja">Dar de baja</h2>
          <p>El paciente deja de estar activo. Sus datos se conservan 12 meses y luego se desidentifican.</p>
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      <div className="form-actions">
        {confirming ? (
          <>
            <span className="field-hint">¿Dar de baja a {patientName(patient)}? Ya no se podrá modificar.</span>
            <button type="button" className="btn btn-ghost" disabled={saving} onClick={() => setConfirming(false)}>
              Volver
            </button>
            <button type="button" className="btn btn-primary" disabled={saving} onClick={discharge}>
              {saving && <span className="spinner" aria-hidden="true" />} Confirmar baja
            </button>
          </>
        ) : (
          <button type="button" className="btn btn-outline" onClick={() => setConfirming(true)}>
            Dar de baja
          </button>
        )}
      </div>
    </section>
  );
}

export function PatientDetailPage() {
  const { institution, handleOperationError } = useOutletContext();
  const { idPerfilMedicion } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [patient, setPatient] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState(location.state?.patientNotice ?? '');

  const load = useCallback(async () => {
    try {
      setPatient(await institutionsApi.getPatient(institution.idInstitucion, idPerfilMedicion));
    } catch (error) {
      setLoadError(handleOperationError(error));
    }
  }, [institution.idInstitucion, idPerfilMedicion, handleOperationError]);

  useEffect(() => {
    load();
  }, [load]);

  function handleSaved(updated, message) {
    setPatient(updated);
    setEditing(false);
    setNotice(message);
    navigate('.', { replace: true, state: null });
  }

  const loadMeasurements = useCallback(
    (filters) => institutionsApi.getPatientMeasurements(institution.idInstitucion, idPerfilMedicion, filters),
    [institution.idInstitucion, idPerfilMedicion],
  );
  const loadEvolution = useCallback(
    (filters) => institutionsApi.getPatientEvolution(institution.idInstitucion, idPerfilMedicion, filters),
    [institution.idInstitucion, idPerfilMedicion],
  );

  if (loadError) {
    return (
      <>
        <Alert>{loadError}</Alert>
        <Link to=".." relative="path" className="btn btn-outline">
          <ArrowLeft size={18} aria-hidden="true" /> Volver a pacientes
        </Link>
      </>
    );
  }
  if (!patient) return <p className="field-hint" role="status">Cargando paciente…</p>;

  const active = patient.estado === 'ACTIVO';
  // Un operador que consulta un paciente de otro recibe solo la identificación administrativa (sin documento, nacimiento ni sexo).
  const administrativeOnly = institution.rolInstitucion === 'OPERADOR' && !patient.esMio;
  const responsible = [patient.responsable.nombre, patient.responsable.apellido].filter(Boolean).join(' ');

  return (
    <>
      <Link to=".." relative="path" className="back-link">
        <ArrowLeft size={16} aria-hidden="true" /> Pacientes
      </Link>
      {notice && <Alert kind="success">{notice}</Alert>}

      {editing ? (
        <EditPatient institution={institution} patient={patient} onSaved={handleSaved} onCancel={() => setEditing(false)}
          handleOperationError={handleOperationError} />
      ) : (
        <section className="panel" aria-labelledby="paciente-datos">
          <div className="panel-head">
            <div className="panel-title">
              <span className="panel-icon">
                <UserRound size={22} aria-hidden="true" />
              </span>
              <div>
                <h2 id="paciente-datos">{patientName(patient)}</h2>
                <p>
                  {patient.identificadorPseudonimo} ·{' '}
                  <Badge tone={active ? 'success' : 'neutral'}>{active ? 'Activo' : 'Dado de baja'}</Badge>{' '}
                  <Badge tone={patient.esMio ? 'success' : 'neutral'}>{patient.esMio ? 'Paciente asignado a mi cargo' : 'Paciente registrado en la institución'}</Badge>
                </p>
              </div>
            </div>
            <div className="member-actions">
              {active && patient.puedeModificar && patient.medicionesAutorizadas && (
                <Link to="medir" className="btn btn-primary">
                  <Play size={16} aria-hidden="true" /> Nueva medición
                </Link>
              )}
              {patient.puedeModificar && (
                <button type="button" className="btn btn-outline" onClick={() => { setNotice(''); setEditing(true); }}>
                  <Pencil size={16} aria-hidden="true" /> Editar
                </button>
              )}
            </div>
          </div>
          <dl className="data-list">
            <Row label="Nombre">{patient.nombre}</Row>
            <Row label="Apellido">{patient.apellido}</Row>
            {!administrativeOnly && <Row label="Documento">{patient.dni}</Row>}
            {!administrativeOnly && <Row label="Fecha de nacimiento">{patient.fechaNacimiento && `${formatDate(patient.fechaNacimiento)} (${patient.edad} años)`}</Row>}
            {!administrativeOnly && <Row label="Sexo">{SEXO_LABELS[patient.sexoModelo]}</Row>}
            <Row label="Operador responsable">{responsible && `${responsible}${patient.responsable.activo ? '' : ' (desvinculado)'}`}</Row>
            <Row label="Registrado el">{formatDateTime(patient.fechaCreacion)}</Row>
            <Row label="Registrado por">{patient.registradoPor && `${[patient.registradoPor.nombre, patient.registradoPor.apellido].filter(Boolean).join(' ') || 'Usuario'}${patient.registradoPor.rolInstitucion ? ` (${ROLE_NAMES[patient.registradoPor.rolInstitucion] ?? patient.registradoPor.rolInstitucion})` : ''}`}</Row>
            {patient.medicionesAutorizadas && <Row label="Última medición">{patient.fechaUltimaMedicion && formatDateTime(patient.fechaUltimaMedicion)}</Row>}
            {patient.fechaExpiracionDatosPersonales && (
              <Row label="Datos personales se conservan hasta">{formatDateTime(patient.fechaExpiracionDatosPersonales)}</Row>
            )}
          </dl>
          {active && !patient.puedeModificar && can(institution, 'GESTIONAR_PACIENTES') && (
            <p className="field-hint">Solo el operador responsable, un moderador o el propietario pueden modificarlo.</p>
          )}
        </section>
      )}

      {!editing && !patient.medicionesAutorizadas && (
        <Alert kind="info">Las mediciones de este paciente están disponibles únicamente para su operador responsable autorizado.</Alert>
      )}

      {!editing && patient.medicionesAutorizadas && (
        <MeasurementHistory loadPage={loadMeasurements} loadEvolution={loadEvolution} detailPath={(id) => `mediciones/${id}`}
          handleOperationError={handleOperationError} refreshKey={patient.fechaUltimaMedicion}
          emptyText="Todavía no hay mediciones registradas para este paciente." />
      )}

      {active && patient.puedeModificar && patient.medicionesAutorizadas && !editing && (
        <TransferPatient key={patient.responsable.idInstitucionUsuario} institution={institution} patient={patient}
          handleOperationError={handleOperationError} />
      )}

      {/* El operador no reasigna: usa «Transferir paciente». Reasignar es de propietario y moderador. */}
      {active && patient.puedeModificar && institution.rolInstitucion !== 'OPERADOR' && !editing && (
        <AssignResponsible key={patient.responsable.idInstitucionUsuario} institution={institution} patient={patient}
          onSaved={handleSaved} handleOperationError={handleOperationError} />
      )}
      {active && can(institution, 'BAJA_PACIENTES') && !editing && (
        <DischargePatient institution={institution} patient={patient} onSaved={handleSaved}
          handleOperationError={handleOperationError} />
      )}
    </>
  );
}
