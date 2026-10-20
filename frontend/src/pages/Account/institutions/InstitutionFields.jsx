// Campos de los datos institucionales, compartidos por el alta (POST /institutions) y la edición (PATCH).
// Solo las columnas reales de dbo.Institucion: nombre, tipoInstitucion y descripcion (el CUIT lo agrega el alta).
// Las mismas reglas que app/schemas/institution.py; el backend vuelve a validar siempre.

import { Building2, FileText } from 'lucide-react';
import { useId } from 'react';

import { TextField } from '../../../components/FormControls.jsx';
import { INSTITUTION_TYPES } from './institutionFormat.js';

export const EMPTY_INSTITUTION = { nombre: '', tipoInstitucion: 'CONSULTORIO', descripcion: '' };

// Ruta del error de validación del backend -> campo del formulario.
export const INSTITUTION_FIELD_PATHS = {
  nombre: 'nombre', tipoInstitucion: 'tipoInstitucion', descripcion: 'descripcion', identificadorLegal: 'cuit',
};

export function institutionFormFrom(institution) {
  return Object.fromEntries(Object.keys(EMPTY_INSTITUTION).map((key) => [key, institution[key] ?? '']));
}

export function validateInstitution(form) {
  const errors = {};
  if (form.nombre.trim().length < 2) errors.nombre = 'Ingresá el nombre de la institución.';
  return errors;
}

/** Cuerpo para la API: textos recortados y la descripción vacía como null. */
export function institutionPayload(form) {
  return { nombre: form.nombre.trim(), tipoInstitucion: form.tipoInstitucion, descripcion: form.descripcion.trim() || null };
}

function SelectField({ label, value, onChange, error, children }) {
  const id = useId();
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      <select id={id} className="field-input field-select" value={value} onChange={onChange}
        aria-invalid={error ? 'true' : undefined}>
        {children}
      </select>
      {error && <p className="field-error">{error}</p>}
    </div>
  );
}

/** `extraGeneral`: contenido adicional del bloque general (p. ej. el CUIT en el alta). */
export function InstitutionFields({ form, update, errors, extraGeneral }) {
  const descripcionId = useId();
  return (
    <>
      <fieldset className="form-section">
        <legend>Datos de la institución</legend>
        <TextField label="Nombre de la institución" icon={Building2} autoComplete="organization" maxLength={150}
          value={form.nombre} onChange={update('nombre')} error={errors.nombre} />
        <div className="form-grid">
          <SelectField label="Tipo de institución" value={form.tipoInstitucion} onChange={update('tipoInstitucion')}
            error={errors.tipoInstitucion}>
            {INSTITUTION_TYPES.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </SelectField>
          {extraGeneral}
        </div>
        <div className="field">
          <label className="field-label" htmlFor={descripcionId}>
            Descripción <span className="optional">(opcional)</span>
          </label>
          <div className="field-control">
            <FileText className="field-icon field-icon-top" size={20} aria-hidden="true" />
            <textarea id={descripcionId} className="field-input field-textarea has-icon" rows={3} maxLength={500}
              value={form.descripcion} onChange={update('descripcion')} />
          </div>
          {errors.descripcion && <p className="field-error">{errors.descripcion}</p>}
        </div>
      </fieldset>

    </>
  );
}

/** Errores de validación del backend (422) por campo. */
export function fieldErrorsFrom(apiError) {
  const byField = {};
  for (const field of apiError.fields ?? []) {
    const key = INSTITUTION_FIELD_PATHS[field.ruta];
    if (key && !byField[key]) byField[key] = field.mensaje;
  }
  return byField;
}
