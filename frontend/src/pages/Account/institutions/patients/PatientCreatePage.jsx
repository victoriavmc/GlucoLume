// Agregar paciente (POST /institutions/{id}/patients). Un OPERADOR no elige responsable: el paciente queda a su cargo y el backend lo
// resuelve con su sesión (acá no se envía ningún identificador de operador). Propietario y moderador designan al operador responsable entre
// los operadores activos de la institución; quien lo registra queda como autor del alta, distinto del responsable de las mediciones.

import { ArrowLeft, UserPlus } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, Navigate, useNavigate, useOutletContext } from 'react-router-dom';

import * as institutionsApi from '../../../../api/institutionsApi.js';
import { Alert, SubmitButton } from '../../../../components/FormControls.jsx';
import { can } from '../institutionFormat.js';
import {
  EMPTY_PATIENT, PatientFields, ResponsibleSelect, patientFieldErrors, patientPayload, validatePatient,
} from './PatientFields.jsx';

export function PatientCreatePage() {
  const { institution, handleOperationError } = useOutletContext();
  const navigate = useNavigate();
  const isOperator = institution.rolInstitucion === 'OPERADOR';
  const [form, setForm] = useState(EMPTY_PATIENT);
  const [responsable, setResponsable] = useState('');
  const [operators, setOperators] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isOperator) return; // el operador no elige: queda a su cargo
    institutionsApi.getAssignableOperators(institution.idInstitucion)
      .then(setOperators)
      .catch((loadError) => {
        setOperators([]);
        setError(handleOperationError(loadError));
      });
  }, [institution.idInstitucion, handleOperationError, isOperator]);

  if (!can(institution, 'GESTIONAR_PACIENTES')) return <Navigate to=".." relative="path" replace />;

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
    if (!isOperator && !responsable) errors.responsable = 'Elegí el operador responsable del paciente.';
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    setError('');
    setSaving(true);
    try {
      const created = await institutionsApi.createPatient(institution.idInstitucion, {
        ...patientPayload(form), ...(isOperator ? {} : { idInstitucionUsuarioResponsable: responsable }),
      });
      navigate(`../${created.idPerfilMedicion}`, { relative: 'path', state: { patientNotice: 'Registramos al paciente.' } });
    } catch (createError) {
      const byField = patientFieldErrors(createError);
      if (createError.codigo === 'OPERADOR_NO_DISPONIBLE' || createError.codigo === 'RESPONSABLE_REQUERIDO') {
        byField.responsable = createError.message;
      }
      setFieldErrors(byField);
      if (!Object.keys(byField).length) setError(handleOperationError(createError));
      setSaving(false);
    }
  }

  const noOperators = !isOperator && operators !== null && operators.length === 0;

  return (
    <form className="panel" onSubmit={handleSubmit} noValidate aria-labelledby="paciente-nuevo">
      <Link to=".." relative="path" className="back-link">
        <ArrowLeft size={16} aria-hidden="true" /> Pacientes
      </Link>
      <div className="panel-title">
        <span className="panel-icon">
          <UserPlus size={22} aria-hidden="true" />
        </span>
        <div>
          <h2 id="paciente-nuevo">Agregar paciente</h2>
          <p>Queda registrado en {institution.nombre}. No crea una cuenta de acceso a GlucoLume.</p>
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      {noOperators && (
        <Alert kind="info">La institución todavía no tiene operadores activos: incorporá uno para poder asignarle pacientes. Hasta entonces no se puede registrar un paciente.</Alert>
      )}
      <PatientFields form={form} update={update} errors={fieldErrors} />
      {isOperator ? (
        <p className="field-hint" role="note">
          El paciente va a quedar a tu cargo: vas a ser su operador responsable y el único que consulte sus mediciones. Quedás registrado/a como quien
          lo dio de alta.
        </p>
      ) : (
        <>
          <ResponsibleSelect operators={operators ?? []} value={responsable}
            onChange={(event) => { setResponsable(event.target.value); setFieldErrors((current) => ({ ...current, responsable: undefined })); }}
            error={fieldErrors.responsable} />
          <p className="field-hint">
            El operador elegido será el responsable de las mediciones del paciente. Vos quedás registrado/a como autor/a del alta, sin acceso a sus
            mediciones por eso.
          </p>
        </>
      )}
      <div className="form-actions">
        <Link to=".." relative="path" className="btn btn-ghost">
          Cancelar
        </Link>
        <SubmitButton loading={saving} loadingLabel="Guardando…" className="btn btn-primary" disabled={saving || noOperators}>
          Agregar paciente
        </SubmitButton>
      </div>
    </form>
  );
}
