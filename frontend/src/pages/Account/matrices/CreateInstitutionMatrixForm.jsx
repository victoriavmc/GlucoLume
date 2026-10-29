// Alta de una matriz institucional con sus reglas, en tres pasos: datos generales, reglas (agregar, editar y quitar antes de guardar) y
// revisión. Las reglas usan los campos reales de ReglaMatriz (sexo, edad, condición y tiempo desde la comida, y límites de glucosa en
// mg/dL). «Guardar» registra la matriz con todas sus reglas en una sola operación (todo o nada) y NO la activa: la activación es una
// acción aparte y explícita. La validación se hace acá (campos, rangos, duplicadas y solapadas) y se repite en FastAPI, que además
// informa advertencias de cobertura (edades o sexos sin regla) con «Revisar configuración». No existe precedencia entre reglas: una
// configuración que se pisa no se puede guardar. La versión la asigna el servidor. La referencia base (de dónde se tomaron los
// criterios) es obligatoria; el enlace a esa fuente es opcional.

import { Pencil, Plus, Save, SearchCheck, Trash2 } from 'lucide-react';
import { useState } from 'react';

import * as matricesApi from '../../../api/matricesApi.js';
import { Alert, TextField } from '../../../components/FormControls.jsx';
import { RulesTable } from './MatrixRules.jsx';
import { RuleEditor } from './RuleEditor.jsx';
import { ruleProblem } from './matrixFormat.js';
import './Matrices.css';

const withCodes = (rules) => rules.map((rule, index) => ({ ...rule, idReglaMatriz: rule.key, codigoRegla: `Regla ${index + 1}` }));
const toPayload = ({ key, idReglaMatriz, codigoRegla, ...rule }) => rule; // eslint-disable-line no-unused-vars
const URL_REFERENCIA = /^https?:\/\/\S+$/i; // igual que el backend: http(s) y sin espacios

// Campo del formulario según la ruta que informa el backend en un 422 (ver api/client.js).
const FIELD_BY_PATH = {
  nombre: 'nombre', descripcion: 'descripcion', referenciaBase: 'referenciaBase', urlReferencia: 'urlReferencia',
  fechaVigenciaDesde: 'desde', fechaVigenciaHasta: 'hasta',
};

/** Mensaje legible: Pydantic informa en inglés los tipos de dato inválidos (p. ej., una fecha que no existe). */
function spanishMessage(message) {
  return message.startsWith('Input should be a valid date') ? 'Ingresá una fecha válida (AAAA-MM-DD).' : message;
}

/** Errores del backend por campo: cada mensaje se muestra bajo el campo que lo causó. */
function fieldErrorsFrom(apiError) {
  const byField = {};
  for (const field of apiError.fields ?? []) {
    const key = FIELD_BY_PATH[field.ruta];
    if (key && !byField[key]) byField[key] = spanishMessage(field.mensaje);
  }
  return byField;
}

export function CreateInstitutionMatrixForm({ idInstitucion, onCreated, onCancel, handleOperationError }) {
  const [form, setForm] = useState({ nombre: '', descripcion: '', referenciaBase: '', urlReferencia: '', desde: '', hasta: '' });
  const [errors, setErrors] = useState({});
  const [rules, setRules] = useState([]); // cada regla local lleva una `key` propia
  const [editing, setEditing] = useState(null); // null · 'new' · regla
  const [review, setReview] = useState(null);
  const [error, setError] = useState('');
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);

  function update(field) {
    return (event) => {
      setForm((current) => ({ ...current, [field]: event.target.value }));
      setReview(null);
      if (errors[field]) setErrors((current) => ({ ...current, [field]: undefined }));
    };
  }

  const listed = withCodes(rules);

  /** Guarda la regla en la lista local, revisando duplicadas y solapadas contra las demás. */
  function saveRule(payload) {
    const others = listed.filter((rule) => editing === 'new' || rule.key !== editing.key);
    const problem = ruleProblem({ ...payload, codigoRegla: 'nueva' }, others);
    if (problem) throw new Error(problem);
    setReview(null);
    setRules((current) => (editing === 'new'
      ? [...current, { ...payload, key: `${Date.now()}-${current.length}` }]
      : current.map((rule) => (rule.key === editing.key ? { ...payload, key: rule.key } : rule))));
    setEditing(null);
  }

  function validateForm() {
    const found = {};
    if (form.nombre.trim().length < 2) found.nombre = 'Ingresá el nombre de la matriz.';
    if (form.referenciaBase.trim().length < 2) found.referenciaBase = 'Indicá de dónde se tomaron los criterios: es obligatorio.';
    if (form.urlReferencia.trim() && !URL_REFERENCIA.test(form.urlReferencia.trim())) {
      found.urlReferencia = 'El enlace tiene que empezar con http:// o https:// y no llevar espacios.';
    }
    if (form.hasta && form.desde && form.hasta < form.desde) found.hasta = 'La vigencia no puede terminar antes de empezar.';
    setErrors(found);
    return Object.keys(found).length === 0;
  }

  function localProblems() {
    const problems = [];
    if (rules.length === 0) problems.push('Agregá al menos una regla.');
    listed.forEach((rule, index) => {
      const problem = ruleProblem(rule, listed.slice(0, index));
      if (problem) problems.push(`${rule.codigoRegla}: ${problem}`);
    });
    return problems;
  }

  async function check() {
    setError('');
    const problems = localProblems();
    if (problems.length) {
      setReview({ valida: false, problemas: problems.map((mensaje) => ({ mensaje })), advertencias: [] });
      return;
    }
    setChecking(true);
    try {
      setReview(await matricesApi.checkRules(rules.map(toPayload)));
    } catch (checkError) {
      setError(handleOperationError(checkError));
    } finally {
      setChecking(false);
    }
  }

  async function handleSubmit() {
    if (saving) return;
    setError('');
    const formOk = validateForm();
    const problems = localProblems();
    if (!formOk || problems.length) {
      if (problems.length) setReview({ valida: false, problemas: problems.map((mensaje) => ({ mensaje })), advertencias: [] });
      return;
    }
    setSaving(true);
    try {
      onCreated(await matricesApi.createMatrix({
        ambito: 'INSTITUCION', idInstitucion, nombre: form.nombre.trim(), descripcion: form.descripcion.trim(),
        referenciaBase: form.referenciaBase.trim(), urlReferencia: form.urlReferencia.trim(),
        fechaVigenciaDesde: form.desde, fechaVigenciaHasta: form.hasta, reglas: rules.map(toPayload),
      }));
    } catch (saveError) {
      const byField = fieldErrorsFrom(saveError);
      if (Object.keys(byField).length) {
        // El rechazo es de datos concretos: se marcan los campos y el aviso general no repite el texto técnico.
        setErrors((current) => ({ ...current, ...byField }));
        setError('Revisá los campos marcados en el formulario.');
      } else {
        setError(handleOperationError(saveError));
      }
      setSaving(false);
    }
  }

  return (
    // No es un <form>: el editor de reglas es un formulario propio y los formularios no se anidan.
    <div className="member-add matrix-create" role="form" aria-label="Crear matriz institucional">
      <h3><Plus size={18} aria-hidden="true" /> Crear matriz institucional</h3>
      <p className="field-hint">
        Completá los datos, agregá las reglas y revisá la configuración. Al guardar, la matriz queda como borrador: no reemplaza a la que se usa hoy
        hasta que la actives.
      </p>
      {error && <Alert>{error}</Alert>}

      <fieldset className="matrix-step">
        <legend>1. Datos generales</legend>
        <div className="form-grid">
          <TextField label="Nombre" maxLength={100} value={form.nombre} onChange={update('nombre')} error={errors.nombre} />
          <TextField label="Descripción (opcional)" maxLength={500} value={form.descripcion} onChange={update('descripcion')} error={errors.descripcion} />
          <TextField label="Referencia base (obligatoria)" maxLength={200} value={form.referenciaBase} onChange={update('referenciaBase')} error={errors.referenciaBase} />
          <TextField label="Enlace de la referencia (opcional)" maxLength={500} value={form.urlReferencia} onChange={update('urlReferencia')} error={errors.urlReferencia} />
          <TextField label="Vigente desde (opcional, por defecto hoy)" type="date" value={form.desde} onChange={update('desde')} error={errors.desde} />
          <TextField label="Vigente hasta (opcional)" type="date" value={form.hasta} onChange={update('hasta')} error={errors.hasta} />
        </div>
        <p className="field-hint">
          La referencia base es el nombre del lugar de donde se tomaron los criterios (una guía, un protocolo o un servicio). La versión la asigna
          GlucoLume automáticamente (1, 2, 3…) y no se puede cambiar.
        </p>
      </fieldset>

      <fieldset className="matrix-step">
        <legend>2. Reglas de la matriz</legend>
        <p className="field-hint">
          Cada regla indica a quién se aplica (sexo, edad y condición respecto de la comida) y su intervalo de glucosa de referencia en mg/dL.
          Dos reglas de la misma población no pueden pisarse: GlucoLume no elige entre ellas, así que no deja guardar una configuración ambigua.
        </p>
        {editing !== null ? (
          <RuleEditor key={editing === 'new' ? 'new' : editing.key} rule={editing === 'new' ? null : editing}
            onSave={saveRule} onCancel={() => setEditing(null)} handleOperationError={(e) => e.message} />
        ) : (
          <div className="form-actions">
            <button type="button" className="btn btn-outline" onClick={() => setEditing('new')}><Plus size={16} aria-hidden="true" /> Agregar regla</button>
          </div>
        )}
        {listed.length === 0 ? (
          <p className="field-hint">Todavía no agregaste reglas.</p>
        ) : (
          <RulesTable rules={listed} caption="Reglas cargadas"
            renderActions={(rule) => (
              <span className="member-actions">
                <button type="button" className="btn btn-ghost" onClick={() => setEditing(rule)}
                  aria-label={`Editar ${rule.codigoRegla}`}><Pencil size={16} aria-hidden="true" /></button>
                <button type="button" className="btn btn-ghost" onClick={() => { setReview(null); setRules((current) => current.filter((item) => item.key !== rule.key)); }}
                  aria-label={`Quitar ${rule.codigoRegla}`}><Trash2 size={16} aria-hidden="true" /></button>
              </span>
            )} />
        )}
      </fieldset>

      <fieldset className="matrix-step">
        <legend>3. Revisar y guardar</legend>
        {review && (
          <div aria-live="polite">
            {review.problemas.length > 0 ? (
              <Alert><b>La configuración no se puede guardar todavía:</b>
                <ul>{review.problemas.map((problem, index) => <li key={index}>{problem.mensaje}</li>)}</ul></Alert>
            ) : (
              <Alert kind="success">La configuración es válida: no hay reglas repetidas ni que se pisen.</Alert>
            )}
            {review.advertencias?.length > 0 && (
              <Alert kind="info"><b>Para tener en cuenta (no impide guardar):</b>
                <ul>{review.advertencias.map((warning, index) => <li key={index}>{warning.mensaje}</li>)}</ul></Alert>
            )}
          </div>
        )}
        <div className="form-actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={saving}>Cancelar</button>
          <button type="button" className="btn btn-outline" onClick={check} disabled={checking || saving}>
            <SearchCheck size={16} aria-hidden="true" /> {checking ? 'Revisando…' : 'Revisar configuración'}
          </button>
          <button type="button" className="btn btn-primary" onClick={handleSubmit} disabled={saving}>
            {saving ? <span className="spinner" aria-hidden="true" /> : <Save size={16} aria-hidden="true" />} {saving ? 'Guardando…' : 'Guardar matriz'}
          </button>
        </div>
      </fieldset>
    </div>
  );
}
