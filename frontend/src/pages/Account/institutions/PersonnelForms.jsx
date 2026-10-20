// Formularios del personal institucional: «Agregar moderador/operador» (invitación) y edición de los datos administrativos del vínculo.
// Es un USUARIO del sistema con un vínculo InstitucionUsuario: nada de esto toca PerfilMedicion ni la gestión de pacientes.
//
// «Agregar moderador/operador»: nombre, apellido y correo. Al salir del correo se consulta su estado:
//   cuenta institucional existente -> se la invita (no se modifican sus datos);
//   sin cuenta                     -> nombre y apellido crean una cuenta institucional pendiente de activación;
//   cuenta individual / ya vinculada -> se informa el motivo y no se envía nada.
// En ambos roles se registran los datos administrativos del vínculo (matrícula, legajo, función profesional y nombre/apellido
// profesional histórico, que arrancan con los de la persona y se pueden cambiar). Quien administra el rol los puede editar después.
// El vínculo queda PENDIENTE hasta que la persona active su cuenta (si es nueva) y acepte. El rol lo fija el backend.

import { IdCard, Mail, Pencil, UserPlus, UserRound, X } from 'lucide-react';
import { useState } from 'react';

import * as institutionsApi from '../../../api/institutionsApi.js';
import { Alert, SelectField, SubmitButton, TextField } from '../../../components/FormControls.jsx';
import { EMAIL_PATTERN } from '../../../utils/validation.js';
import { ROLE_LABELS, personName } from './institutionFormat.js';

export const CONFIG = {
  MODERADOR: {
    title: 'Moderadores',
    description: 'Los moderadores incorporan y administran a los operadores. Solo el propietario los designa.',
    invitePermission: 'GESTIONAR_MODERADORES',
    revokePermission: 'GESTIONAR_MODERADORES',
    addLabel: 'Agregar moderador',
    revokeLabel: 'Desvincular',
    empty: 'Esta institución todavía no tiene moderadores. Podés agregar uno para que gestione la incorporación de operadores.',
  },
  OPERADOR: {
    title: 'Operadores',
    description: 'Los operadores gestionan los pacientes de la institución. Los incorporan los moderadores.',
    invitePermission: 'INCORPORAR_OPERADORES',
    revokePermission: 'ADMINISTRAR_OPERADORES',
    addLabel: 'Agregar operador',
    revokeLabel: 'Desvincular',
    empty: 'Esta institución todavía no tiene operadores.',
  },
};

const EMPTY_FORM = {
  correo: '',
  matriculaProfesional: '', legajoInstitucional: '', funcionProfesional: '', nombreProfesionalHistorico: '',
  apellidoProfesionalHistorico: '',
};

// Función profesional opcional (dato descriptivo del vínculo; no es el rol del sistema ni cambia permisos).
export const FUNCTION_LABELS = { OPERADOR: 'Operador/a', ENFERMERO: 'Enfermero/a', MEDICO: 'Médico/a' };

/** Matrícula, legajo y nombre/apellido profesional histórico: mismos campos al agregar y al editar. */
function AdminFields({ form, update, idPrefix, errors = {} }) {
  return (
    <fieldset className="member-admin-fields" aria-labelledby={`${idPrefix}-admin`}>
      <legend id={`${idPrefix}-admin`}>Datos en la institución</legend>
      <p className="field-hint">
        El nombre y apellido quedan registrados en este vínculo; en una cuenta existente no cambian los datos de la persona.
      </p>
      <div className="form-grid">
        <TextField label="Nombre profesional" icon={UserRound} autoComplete="off" maxLength={100}
          value={form.nombreProfesionalHistorico} onChange={update('nombreProfesionalHistorico')}
          error={errors.nombreProfesionalHistorico} />
        <TextField label="Apellido profesional" autoComplete="off" maxLength={100}
          value={form.apellidoProfesionalHistorico} onChange={update('apellidoProfesionalHistorico')}
          error={errors.apellidoProfesionalHistorico} />
        <TextField label="Matrícula profesional (opcional)" icon={IdCard} autoComplete="off" maxLength={100}
          value={form.matriculaProfesional} onChange={update('matriculaProfesional')} />
        <TextField label="Legajo institucional (opcional)" autoComplete="off" maxLength={100}
          value={form.legajoInstitucional} onChange={update('legajoInstitucional')} />
        <SelectField label="Rol institucional (opcional)" value={form.funcionProfesional} onChange={update('funcionProfesional')}
          hint="Es la función profesional de la persona; no cambia sus permisos en la institución.">
          <option value="">Sin especificar</option>
          {Object.entries(FUNCTION_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </SelectField>
      </div>
    </fieldset>
  );
}

export function AddMemberForm({ institution, rol, config, onAdded, onCancel, handleOperationError }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [account, setAccount] = useState(null); // null: sin consultar · { existe, nombre, apellido, cuentaPendiente }
  const [checkedEmail, setCheckedEmail] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState('');
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  // Mientras no se editen a mano, el nombre y apellido profesional siguen a los de la cuenta existente.
  const [editedHistoric, setEditedHistoric] = useState({});
  const email = form.correo.trim();
  const isNew = account && !account.existe;

  function update(field) {
    return (event) => {
      const { value } = event.target;
      if (field === 'nombreProfesionalHistorico' || field === 'apellidoProfesionalHistorico') {
        setEditedHistoric((current) => ({ ...current, [field]: true }));
      }
      setForm((current) => ({ ...current, [field]: value }));
      if (fieldErrors[field]) setFieldErrors((current) => ({ ...current, [field]: undefined }));
      if (field === 'correo' && value.trim() !== checkedEmail) {
        setAccount(null);
        setError('');
      }
    };
  }

  async function checkEmail() {
    if (!EMAIL_PATTERN.test(email)) return null;
    if (email === checkedEmail && account) return account;
    setChecking(true);
    setError('');
    try {
      const candidate = await institutionsApi.lookupMember(institution.idInstitucion, rol, email);
      const result = { existe: true, ...candidate };
      setAccount(result);
      setForm((current) => ({
        ...current,
        nombreProfesionalHistorico: editedHistoric.nombreProfesionalHistorico ? current.nombreProfesionalHistorico : candidate.nombre ?? '',
        apellidoProfesionalHistorico: editedHistoric.apellidoProfesionalHistorico ? current.apellidoProfesionalHistorico : candidate.apellido ?? '',
      }));
      setCheckedEmail(email);
      return result;
    } catch (lookupError) {
      if (lookupError.codigo === 'USUARIO_NO_ENCONTRADO') {
        const result = { existe: false };
        setAccount(result);
        setCheckedEmail(email);
        return result;
      }
      setAccount(null);
      setError(handleOperationError(lookupError));
      return null;
    } finally {
      setChecking(false);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving || checking) return;
    if (!EMAIL_PATTERN.test(email)) {
      setFieldErrors({ correo: 'Ingresá un correo electrónico válido.' });
      return;
    }
    const current = await checkEmail();
    if (!current) return;
    const errors = {};
    // Una persona sin cuenta se crea con este nombre y apellido: son obligatorios.
    if (!current.existe && !form.nombreProfesionalHistorico.trim()) errors.nombreProfesionalHistorico = 'Ingresá el nombre.';
    if (!current.existe && !form.apellidoProfesionalHistorico.trim()) errors.apellidoProfesionalHistorico = 'Ingresá el apellido.';
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    setSaving(true);
    setError('');
    try {
      const added = await institutionsApi.inviteMember(institution.idInstitucion, rol, {
        correoElectronico: email,
        nombre: current.existe ? undefined : form.nombreProfesionalHistorico.trim(),
        apellido: current.existe ? undefined : form.apellidoProfesionalHistorico.trim(),
        ...Object.fromEntries(institutionsApi.MEMBER_ADMIN_FIELDS.map((field) => [field, form[field].trim() || undefined])),
      });
      onAdded(added);
    } catch (inviteError) {
      setError(handleOperationError(inviteError));
      setSaving(false);
    }
  }

  return (
    <form className="member-add" onSubmit={handleSubmit} noValidate aria-labelledby={`agregar-${rol}`}>
      <h3 id={`agregar-${rol}`}>
        <UserPlus size={18} aria-hidden="true" /> {config.addLabel}
      </h3>
      <p className="field-hint">
        Rol: <b>{ROLE_LABELS[rol]}</b> (lo asigna el sistema). Es una cuenta de GlucoLume, no un paciente.
      </p>
      {error && <Alert>{error}</Alert>}
      <TextField label="Correo electrónico" icon={Mail} type="email" autoComplete="off" maxLength={254}
        value={form.correo} onChange={update('correo')} onBlur={checkEmail} error={fieldErrors.correo} />
      {checking && <p className="field-hint" role="status">Verificando el correo…</p>}
      {account?.existe && (
        <Alert kind="info">
          Cuenta institucional {account.cuentaPendiente ? 'invitada, pendiente de activación' : 'existente'}:{' '}
          <b>{personName(account)}</b>. Se le va a enviar la invitación; sus datos no se modifican.
        </Alert>
      )}
      {isNew && (
        <Alert kind="info">
          No hay una cuenta con este correo. Se va a crear una cuenta institucional pendiente: la persona recibirá un
          enlace para elegir su usuario y contraseña (o usar Google) y después aceptar la invitación.
        </Alert>
      )}
      {account && <AdminFields form={form} update={update} idPrefix={`agregar-${rol}`} errors={fieldErrors} />}
      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={saving}>
          <X size={16} aria-hidden="true" /> Cancelar
        </button>
        <SubmitButton loading={saving} loadingLabel="Enviando…" className="btn btn-primary" disabled={saving || checking}>
          {isNew ? 'Crear cuenta e invitar' : 'Enviar invitación'}
        </SubmitButton>
      </div>
    </form>
  );
}

/** Edición de los datos administrativos de un vínculo: envía solo lo que cambió (PATCH). */
export function EditMemberForm({ institution, rol, member, onSaved, onCancel, handleOperationError }) {
  const initial = Object.fromEntries(institutionsApi.MEMBER_ADMIN_FIELDS.map((field) => [field, member[field] ?? '']));
  const [form, setForm] = useState(initial);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const changes = Object.fromEntries(
    institutionsApi.MEMBER_ADMIN_FIELDS
      .filter((field) => form[field].trim() !== (initial[field] ?? '').trim())
      .map((field) => [field, form[field].trim() || null]),
  );
  const dirty = Object.keys(changes).length > 0;

  function update(field) {
    return (event) => {
      const { value } = event.target;
      setForm((current) => ({ ...current, [field]: value }));
    };
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving || !dirty) return;
    setSaving(true);
    setError('');
    try {
      onSaved(await institutionsApi.updateMemberAdmin(institution.idInstitucion, rol, member.idInstitucionUsuario, changes));
    } catch (saveError) {
      setError(handleOperationError(saveError));
      setSaving(false);
    }
  }

  const idPrefix = `editar-${member.idInstitucionUsuario}`;
  return (
    <form className="member-add" onSubmit={handleSubmit} noValidate aria-labelledby={idPrefix}>
      <h3 id={idPrefix}>
        <Pencil size={18} aria-hidden="true" /> Datos de {personName(member)}
      </h3>
      <p className="field-hint">Rol: <b>{ROLE_LABELS[rol]}</b> (no se modifica desde acá).</p>
      {error && <Alert>{error}</Alert>}
      <AdminFields form={form} update={update} idPrefix={idPrefix} />
      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={saving}>
          <X size={16} aria-hidden="true" /> Cancelar
        </button>
        <SubmitButton loading={saving} loadingLabel="Guardando…" className="btn btn-primary" disabled={saving || !dirty}>
          Guardar cambios
        </SubmitButton>
      </div>
    </form>
  );
}
