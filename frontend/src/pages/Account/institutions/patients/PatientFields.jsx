// Campos de un paciente institucional: columnas de dbo.PerfilMedicion (tipoPerfil INSTITUCIONAL) que carga la
// institución (app/schemas/measurementProfile.py: InstitutionalProfileCreate). Sin datos de contacto ni clínicos.

import { CalendarDays, IdCard, UserRound } from 'lucide-react';

import { SelectField, TextField } from '../../../../components/FormControls.jsx';
import { SEXO_OPTIONS } from '../../accountFormat.js';

const DOCUMENT_PATTERN = /^[A-Z0-9]{6,12}$/;

export const EMPTY_PATIENT = { nombre: '', apellido: '', dni: '', fechaNacimiento: '', sexoModelo: '' };

export function normalizeDocument(value) {
  return value.replace(/[\s.-]/g, '').toUpperCase();
}

export function patientFormFrom(patient) {
  return {
    nombre: patient.nombre ?? '', apellido: patient.apellido ?? '', dni: patient.dni ?? '',
    fechaNacimiento: patient.fechaNacimiento ?? '', sexoModelo: patient.sexoModelo ?? '',
  };
}

export function validatePatient(form, today = new Date()) {
  const errors = {};
  if (!form.nombre.trim()) errors.nombre = 'Ingresá el nombre.';
  if (!form.apellido.trim()) errors.apellido = 'Ingresá el apellido.';
  // Documento, fecha de nacimiento y sexo son opcionales: solo se validan si se completan.
  if (form.dni.trim() && !DOCUMENT_PATTERN.test(normalizeDocument(form.dni))) errors.dni = 'Ingresá un documento válido: entre 6 y 12 letras o números.';
  if (form.fechaNacimiento && form.fechaNacimiento > today.toISOString().slice(0, 10)) errors.fechaNacimiento = 'La fecha de nacimiento no puede ser futura.';
  return errors;
}

export function patientPayload(form) {
  // Lo opcional vacío no se envía.
  return {
    nombre: form.nombre.trim(), apellido: form.apellido.trim(), dni: normalizeDocument(form.dni) || undefined,
    fechaNacimiento: form.fechaNacimiento || undefined, sexoModelo: form.sexoModelo || undefined,
  };
}

const FIELD_PATHS = { nombre: 'nombre', apellido: 'apellido', dni: 'dni', fechaNacimiento: 'fechaNacimiento', sexoModelo: 'sexoModelo' };

export function patientFieldErrors(apiError) {
  const byField = {};
  for (const field of apiError.fields ?? []) {
    const key = FIELD_PATHS[field.ruta];
    if (key && !byField[key]) byField[key] = field.mensaje;
  }
  if (apiError.codigo === 'PACIENTE_REGISTRADO') byField.dni = apiError.message;
  if (apiError.codigo === 'EDAD_FUERA_DE_RANGO') byField.fechaNacimiento = apiError.message;
  return byField;
}

export function PatientFields({ form, update, errors }) {
  return (
    <>
      <div className="form-grid">
        <TextField label="Nombre" icon={UserRound} autoComplete="off" maxLength={100} value={form.nombre}
          onChange={update('nombre')} error={errors.nombre} />
        <TextField label="Apellido" autoComplete="off" maxLength={100} value={form.apellido}
          onChange={update('apellido')} error={errors.apellido} />
        <TextField label="Documento (DNI) (opcional)" icon={IdCard} autoComplete="off" maxLength={20} value={form.dni}
          onChange={update('dni')} error={errors.dni} />
        <TextField label="Fecha de nacimiento (opcional)" icon={CalendarDays} type="date" value={form.fechaNacimiento}
          onChange={update('fechaNacimiento')} error={errors.fechaNacimiento} />
      </div>
      <SelectField label="Sexo (opcional)" value={form.sexoModelo} onChange={update('sexoModelo')} error={errors.sexoModelo}
        hint="Lo usa el modelo de estimación. Para iniciar una medición hacen falta la fecha de nacimiento y el sexo: se pueden completar después."
        options={[{ value: '', label: 'Sin especificar' }, ...SEXO_OPTIONS]} />
    </>
  );
}

/** Selector de operador responsable. `allowSelf`: opción vacía "A mi cargo" (alta por un operador). */
export function ResponsibleSelect({ operators, value, onChange, error, allowSelf = false, label = 'Operador responsable' }) {
  return (
    <SelectField label={label} value={value} onChange={onChange} error={error}>
      <option value="">{allowSelf ? 'A mi cargo' : 'Elegí un operador'}</option>
      {operators.map((operator) => (
        <option key={operator.idInstitucionUsuario} value={operator.idInstitucionUsuario}>
          {[operator.nombre, operator.apellido].filter(Boolean).join(' ') || 'Operador/a'}
        </option>
      ))}
    </SelectField>
  );
}
