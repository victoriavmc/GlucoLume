// Editor de una regla de una matriz en BORRADOR (columnas de dbo.ReglaMatriz). Mismos valores y enumeraciones que
// el backend: sexo del modelo, rango de edad, condición respecto de la última comida, tiempo desde esa ingesta y los
// límites de glucosa de referencia. El código lo asigna el servidor. La validación definitiva (rangos, duplicadas y
// solapadas) corre en FastAPI antes de guardar; acá solo se evita enviar lo evidentemente incoherente.

import { Plus, Save, X } from 'lucide-react';
import { useState } from 'react';

import { Alert, SelectField, SubmitButton, TextField } from '../../../components/FormControls.jsx';
import { MEALS, RULE_SEX } from './matrixFormat.js';

const EMPTY = {
  sexoModelo: 'FEMENINO', edadDesde: '', edadHasta: '', condicionComida: 'AYUNO', minutosComidaMin: '', minutosComidaMax: '',
  glucosaMinReferencia: '', glucosaMaxReferencia: '',
};

export function ruleFormFrom(rule) {
  if (!rule) return EMPTY;
  return Object.fromEntries(Object.keys(EMPTY).map((key) => [key, rule[key] === null || rule[key] === undefined ? '' : String(rule[key])]));
}

function validate(form) {
  const errors = {};
  const number = (value) => (value === '' ? NaN : Number(value));
  // Ambas edades vacías = «edad no especificada» (válido, igual que en la matriz global); una sola no.
  const ageGiven = form.edadDesde !== '' || form.edadHasta !== '';
  if (ageGiven) {
    if (!(number(form.edadDesde) >= 0) || number(form.edadDesde) > 130) errors.edadDesde = 'Ingresá una edad entre 0 y 130, o dejá ambas vacías.';
    if (!(number(form.edadHasta) >= 0) || number(form.edadHasta) > 130) errors.edadHasta = 'Ingresá una edad entre 0 y 130, o dejá ambas vacías.';
    else if (!errors.edadDesde && number(form.edadHasta) < number(form.edadDesde)) errors.edadHasta = 'La edad mínima no puede superar la máxima.';
  }
  for (const key of ['minutosComidaMin', 'minutosComidaMax']) {
    if (form[key] !== '' && !(Number(form[key]) >= 0)) errors[key] = 'Ingresá minutos mayores o iguales a 0.';
  }
  if (!errors.minutosComidaMin && !errors.minutosComidaMax && form.minutosComidaMin !== '' && form.minutosComidaMax !== ''
      && Number(form.minutosComidaMax) < Number(form.minutosComidaMin)) {
    errors.minutosComidaMax = 'El tiempo mínimo no puede superar el máximo.';
  }
  if (!(number(form.glucosaMinReferencia) >= 0)) errors.glucosaMinReferencia = 'Ingresá un valor de glucosa (mg/dL).';
  if (!(number(form.glucosaMaxReferencia) >= 0)) errors.glucosaMaxReferencia = 'Ingresá un valor de glucosa (mg/dL).';
  else if (!errors.glucosaMinReferencia && number(form.glucosaMaxReferencia) < number(form.glucosaMinReferencia)) {
    errors.glucosaMaxReferencia = 'El límite mínimo no puede superar el máximo.';
  }
  return errors;
}

export function rulePayload(form) {
  const optional = (value) => (value === '' ? null : Number(value));
  return {
    sexoModelo: form.sexoModelo, edadDesde: optional(form.edadDesde), edadHasta: optional(form.edadHasta),
    condicionComida: form.condicionComida, minutosComidaMin: optional(form.minutosComidaMin),
    minutosComidaMax: optional(form.minutosComidaMax), glucosaMinReferencia: form.glucosaMinReferencia,
    glucosaMaxReferencia: form.glucosaMaxReferencia,
  };
}

const FIELD_ROUTES = {
  sexoModelo: 'sexoModelo', edadDesde: 'edadDesde', edadHasta: 'edadHasta', condicionComida: 'condicionComida',
  minutosComidaMin: 'minutosComidaMin', minutosComidaMax: 'minutosComidaMax',
  glucosaMinReferencia: 'glucosaMinReferencia', glucosaMaxReferencia: 'glucosaMaxReferencia',
};

export function RuleEditor({ rule, onSave, onCancel, handleOperationError }) {
  const editing = Boolean(rule);
  const [form, setForm] = useState(() => ruleFormFrom(rule));
  const [errors, setErrors] = useState({});
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  function update(field) {
    return (event) => {
      setForm((current) => ({ ...current, [field]: event.target.value }));
      if (errors[field]) setErrors((current) => ({ ...current, [field]: undefined }));
    };
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving) return;
    const found = validate(form);
    setErrors(found);
    if (Object.keys(found).length) return;
    setSaving(true);
    setError('');
    try {
      await onSave(rulePayload(form));
    } catch (saveError) {
      const byField = {};
      for (const item of saveError.fields ?? []) {
        const key = FIELD_ROUTES[item.ruta];
        if (key && !byField[key]) byField[key] = item.mensaje;
      }
      setErrors(byField);
      if (!Object.keys(byField).length) setError(handleOperationError(saveError));
      setSaving(false);
    }
  }

  return (
    <form className="member-add" onSubmit={handleSubmit} noValidate aria-label={editing ? `Editar regla ${rule.codigoRegla}` : 'Agregar regla'}>
      <h3>{editing ? `Editar regla ${rule.codigoRegla}` : 'Agregar regla'}</h3>
      {error && <Alert>{error}</Alert>}
      <div className="form-grid">
        <SelectField label="Sexo del modelo" value={form.sexoModelo} onChange={update('sexoModelo')} error={errors.sexoModelo}
          options={Object.entries(RULE_SEX).map(([key, label]) => ({ value: key, label }))} />
        <SelectField label="Condición respecto de la última comida" value={form.condicionComida} onChange={update('condicionComida')} error={errors.condicionComida}
          options={Object.entries(MEALS).map(([key, label]) => ({ value: key, label }))} />
        <TextField label="Edad mínima" type="number" min="0" max="130" value={form.edadDesde} onChange={update('edadDesde')} error={errors.edadDesde} />
        <TextField label="Edad máxima" type="number" min="0" max="130" value={form.edadHasta} onChange={update('edadHasta')} error={errors.edadHasta} />
        <TextField label="Minutos desde la última ingesta, mínimo (opcional)" type="number" min="0" value={form.minutosComidaMin}
          onChange={update('minutosComidaMin')} error={errors.minutosComidaMin} />
        <TextField label="Minutos desde la última ingesta, máximo (opcional)" type="number" min="0" value={form.minutosComidaMax}
          onChange={update('minutosComidaMax')} error={errors.minutosComidaMax} />
        <TextField label="Glucosa de referencia mínima (mg/dL)" type="number" min="0" step="0.01" value={form.glucosaMinReferencia}
          onChange={update('glucosaMinReferencia')} error={errors.glucosaMinReferencia} />
        <TextField label="Glucosa de referencia máxima (mg/dL)" type="number" min="0" step="0.01" value={form.glucosaMaxReferencia}
          onChange={update('glucosaMaxReferencia')} error={errors.glucosaMaxReferencia} />
      </div>
      <p className="field-hint">
        «Sexo no informado» y «Comida sin informar» son condiciones válidas de la regla. Si dejás las dos edades vacías, la regla es para «edad no
        especificada».
      </p>
      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={saving}>
          <X size={16} aria-hidden="true" /> Cancelar
        </button>
        <SubmitButton loading={saving} loadingLabel="Guardando…" className="btn btn-primary">
          {editing ? <><Save size={16} aria-hidden="true" /> Guardar regla</> : <><Plus size={16} aria-hidden="true" /> Agregar regla</>}
        </SubmitButton>
      </div>
    </form>
  );
}
