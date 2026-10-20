// Edición del perfil con PATCH /auth/me/profile.
//
// Editables (UserProfileUpdate): nombre, apellido, usuario, fechaNacimiento, sexo. Solo se envían los
// campos que cambiaron. Ninguno admite null en el backend: un dato ya completado no puede vaciarse.
// El correo no es editable: el backend no tiene endpoint para cambiarlo.

import { AtSign, CalendarDays, Mail, Save, User, X } from 'lucide-react';
import { useId, useState } from 'react';

import * as authApi from '../../api/authApi.js';
import { ApiError } from '../../api/client.js';
import { friendlyError } from '../../auth/errorMessages.js';
import { Alert, SubmitButton, TextField } from '../../components/FormControls.jsx';
import { usernameError } from '../../utils/validation.js';
import { SEXO_OPTIONS, ageFrom, todayIso } from './accountFormat.js';

const FIELDS = ['nombre', 'apellido', 'usuario', 'fechaNacimiento', 'sexo'];
const MAX_AGE = 130; // EDAD_MAXIMA del backend

function initialForm(user) {
  return Object.fromEntries(FIELDS.map((field) => [field, user[field] ?? '']));
}

function validate(form, user) {
  const errors = {};
  for (const field of FIELDS) {
    // Un dato que ya tenía valor no puede quedar vacío (el backend no admite null).
    if (user[field] && !String(form[field]).trim()) errors[field] = 'Este dato no puede quedar vacío.';
  }
  if (form.usuario.trim() || user.usuario === null) {
    const error = usernameError(form.usuario);
    if (error) errors.usuario = error;
  }
  if (form.fechaNacimiento) {
    if (form.fechaNacimiento > todayIso()) errors.fechaNacimiento = 'La fecha de nacimiento no puede ser futura.';
    else if (ageFrom(form.fechaNacimiento) > MAX_AGE) errors.fechaNacimiento = `La edad no puede superar los ${MAX_AGE} años.`;
  }
  return errors;
}

function changedFields(form, user) {
  const changes = {};
  for (const field of FIELDS) {
    const value = typeof form[field] === 'string' ? form[field].trim() : form[field];
    if (value && value !== (user[field] ?? '')) changes[field] = value;
  }
  return changes;
}

function serverFieldErrors(error) {
  if (!(error instanceof ApiError)) return {};
  if (error.codigo === 'USUARIO_NO_DISPONIBLE' || error.codigo === 'USUARIO_REQUERIDO') {
    return { usuario: friendlyError(error) };
  }
  const errors = {};
  for (const field of error.fields ?? []) {
    if (FIELDS.includes(field.ruta) && !errors[field.ruta]) errors[field.ruta] = field.mensaje;
  }
  return errors;
}

export function ProfileEditForm({ account, onSaved, onCancel }) {
  const user = account.usuario;
  const ids = { fecha: useId(), sexo: useId() };
  const [form, setForm] = useState(() => initialForm(user));
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
    const errors = validate(form, user);
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    const changes = changedFields(form, user);
    if (!Object.keys(changes).length) {
      onSaved({ ...account, actualizado: false });
      return;
    }
    setError('');
    setSaving(true);
    try {
      onSaved(await authApi.updateProfile(changes));
    } catch (saveError) {
      const byField = serverFieldErrors(saveError);
      setFieldErrors(byField);
      if (!Object.keys(byField).length) setError(friendlyError(saveError));
      setSaving(false);
    }
  }

  return (
    <form className="panel" onSubmit={handleSubmit} noValidate aria-labelledby="editar-perfil">
      <div className="panel-title">
        <span className="panel-icon">
          <User size={22} aria-hidden="true" />
        </span>
        <div>
          <h2 id="editar-perfil">Editar perfil</h2>
          <p>Los cambios se guardan en tu cuenta al confirmar.</p>
        </div>
      </div>

      {error && <Alert>{error}</Alert>}

      <div className="form-grid">
        <TextField label="Nombre" name="nombre" icon={User} autoComplete="given-name" maxLength={100}
          value={form.nombre} onChange={update('nombre')} error={fieldErrors.nombre} />
        <TextField label="Apellido" name="apellido" icon={User} autoComplete="family-name" maxLength={100}
          value={form.apellido} onChange={update('apellido')} error={fieldErrors.apellido} />
        <TextField label="Nombre de usuario" name="usuario" icon={AtSign} autoComplete="username" maxLength={50}
          value={form.usuario} onChange={update('usuario')} error={fieldErrors.usuario} />
        <TextField label="Correo electrónico" name="correoElectronico" icon={Mail} value={user.correoElectronico ?? ''}
          readOnly disabled aria-describedby={`${ids.fecha}-correo`} />
        <div className="field">
          <label className="field-label" htmlFor={ids.fecha}>
            Fecha de nacimiento
          </label>
          <div className="field-control">
            <CalendarDays className="field-icon" size={20} aria-hidden="true" />
            <input id={ids.fecha} type="date" className="field-input" max={todayIso()}
              value={form.fechaNacimiento} onChange={update('fechaNacimiento')}
              aria-invalid={fieldErrors.fechaNacimiento ? 'true' : undefined}
              aria-describedby={fieldErrors.fechaNacimiento ? `${ids.fecha}-error` : undefined} />
          </div>
          {fieldErrors.fechaNacimiento && <p className="field-error" id={`${ids.fecha}-error`}>{fieldErrors.fechaNacimiento}</p>}
        </div>
        <div className="field">
          <label className="field-label" htmlFor={ids.sexo}>
            Sexo
          </label>
          <select id={ids.sexo} className="field-input field-select" value={form.sexo} onChange={update('sexo')}
            aria-invalid={fieldErrors.sexo ? 'true' : undefined}>
            {!user.sexo && <option value="">Seleccioná una opción</option>}
            {SEXO_OPTIONS.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          {fieldErrors.sexo && <p className="field-error">{fieldErrors.sexo}</p>}
        </div>
      </div>
      <p className="field-hint">
        La fecha de nacimiento y el sexo son opcionales. Se recomiendan porque ayudan a que la estimación experimental sea más
        precisa, pero no hacen falta para medir.
      </p>
      <p className="field-hint" id={`${ids.fecha}-correo`}>
        El correo electrónico no puede modificarse desde aquí.
      </p>

      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={saving}>
          <X size={18} aria-hidden="true" /> Cancelar
        </button>
        <SubmitButton loading={saving} loadingLabel="Guardando…" className="btn btn-primary">
          <Save size={18} aria-hidden="true" /> Guardar cambios
        </SubmitButton>
      </div>
    </form>
  );
}
