// Edad y sexo OPCIONALES de UNA medición. Nada de esto es obligatorio ni bloquea nunca el inicio:
//   - si el perfil ya tiene edad (calculada desde la fecha de nacimiento) o sexo, se sugieren y se pueden cambiar solo para esta medición;
//   - si no los tiene, se pueden informar o dejar vacíos («Prefiero no informar»);
//   - lo que se informa acá NO cambia los datos personales ni el perfil: el backend lo guarda solo con esa medición.
// Prioridad en el backend: informado en la medición > perfil de medición > datos de la cuenta > sin informar (NULL).

import { SelectField, TextField } from '../../../components/FormControls.jsx';
import { SEXO } from './measurementFormat.js';

/** Valores sugeridos a partir del perfil (la edad ya viene calculada a la fecha de hoy). */
export function initialMeasurementContext(profile) {
  return { edad: profile?.edad !== null && profile?.edad !== undefined ? String(profile.edad) : '', sexo: profile?.sexoModelo ?? '' };
}

/** Error solo si escribió una edad inválida; un campo vacío nunca es un error. */
export function measurementContextError(value) {
  if (value.edad === '') return '';
  const age = Number(value.edad);
  return Number.isInteger(age) && age >= 0 && age <= 130 ? '' : 'La edad tiene que ser un número entero de años, entre 0 y 130.';
}

/** Campos a enviar: solo los que la persona informó y que difieren de lo sugerido por el perfil (lo demás lo resuelve el backend). */
export function measurementContextPayload(value, profile) {
  const suggested = initialMeasurementContext(profile);
  const payload = {};
  if (value.edad !== '' && value.edad !== suggested.edad) payload.edadAlMomento = Number(value.edad);
  if (value.sexo !== '' && value.sexo !== suggested.sexo) payload.sexoModelo = value.sexo;
  return payload;
}

// `patient`: el perfil es el de un paciente institucional (otra persona): cambia solo la redacción, no la lógica.
export function OptionalMeasurementContext({ profile, value, onChange, idPrefix = 'ctx', error = '', patient = false, children }) {
  const suggested = initialMeasurementContext(profile);
  const hasAge = suggested.edad !== '';
  const hasSex = suggested.sexo !== '';
  const set = (field) => (event) => onChange({ ...value, [field]: event.target.value });
  return (
    <fieldset className="form-section optional-context">
      <legend>Datos opcionales de esta medición</legend>
      <p className="field-hint">
        {patient
          ? 'Podés dejarlos vacíos. Solo se guardan con esta medición: no modifican el perfil del paciente ni sus datos registrados.'
          : 'Podés dejarlos vacíos. Solo se guardan con esta medición: no cambian tu perfil ni tus datos personales.'}
      </p>
      <div className="form-grid">
        <TextField label="Edad en años (opcional)" type="number" inputMode="numeric" min="0" max="130" step="1"
          value={value.edad} onChange={set('edad')} placeholder="Ej.: 5, 25 o 60" error={error || undefined}
          hint={hasAge ? `Calculada de ${patient ? 'la' : 'tu'} fecha de nacimiento${patient ? ' del paciente' : ''}: ${suggested.edad} años. Podés cambiarla solo para esta medición.` : 'No hace falta la fecha de nacimiento: alcanza con la edad.'} />
        <SelectField label="Sexo (opcional)" value={value.sexo} onChange={set('sexo')}
          hint={`${hasSex ? `Tomado ${patient ? 'del perfil del paciente' : 'de tu perfil'}; podés cambiarlo solo para esta medición. ` : ''}Sexo biológico que usa el modelo experimental, no género.`}>
          {!hasSex && <option value="">Prefiero no informar</option>}
          {Object.entries(SEXO).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </SelectField>
      </div>
      {children}
    </fieldset>
  );
}
