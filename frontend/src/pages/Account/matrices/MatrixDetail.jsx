// Detalle de una matriz: datos, reglas y acciones. Las acciones disponibles las informa el backend en `permisos`
// (según el ámbito, el rol y el estado de la versión); cada operación se vuelve a validar en FastAPI. Solo un BORRADOR
// se edita; una versión activada es inmutable y para cambiarla se crea una versión nueva (las mediciones ya hechas
// conservan la versión con la que se calcularon).
//
// Aviso: los límites de glucosa de referencia no son un algoritmo de estimación. Elegir una regla no calcula glucosa.

import { Archive, CheckCircle2, CopyPlus, History, Pencil, Play, PowerOff, ShieldCheck, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import * as matricesApi from '../../../api/matricesApi.js';
import { Badge, toneFromClass } from '../../../components/Badge.jsx';
import { Alert, SubmitButton, TextField } from '../../../components/FormControls.jsx';
import { RuleEditor } from './RuleEditor.jsx';
import { RulesTable } from './MatrixRules.jsx';
import {
  AUDIT_ACTIONS, MATRIX_SCOPES, MATRIX_STATES, formatDate, formatDateTime, stateBadge,
} from './matrixFormat.js';

function DraftForm({ matrix, onSaved, handleOperationError }) {
  const [form, setForm] = useState({
    nombre: matrix.nombre, descripcion: matrix.descripcion ?? '', desde: matrix.fechaVigenciaDesde,
    hasta: matrix.fechaVigenciaHasta ?? '',
  });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  function update(field) {
    return (event) => setForm((current) => ({ ...current, [field]: event.target.value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving) return;
    if (form.nombre.trim().length < 2) {
      setError('Ingresá el nombre de la matriz.');
      return;
    }
    if (form.hasta && form.desde && form.hasta < form.desde) {
      setError('La vigencia no puede terminar antes de empezar.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      onSaved(await matricesApi.updateDraft(matrix.idMatriz, {
        nombre: form.nombre.trim(), descripcion: form.descripcion.trim() || null, fechaVigenciaDesde: form.desde || null,
        fechaVigenciaHasta: form.hasta || null,
      }));
    } catch (saveError) {
      setError(handleOperationError(saveError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="member-add" onSubmit={handleSubmit} noValidate aria-label="Datos del borrador">
      <h3>Datos del borrador</h3>
      {error && <Alert>{error}</Alert>}
      <div className="form-grid">
        <TextField label="Nombre" maxLength={100} value={form.nombre} onChange={update('nombre')} />
        <TextField label="Descripción (opcional)" maxLength={500} value={form.descripcion} onChange={update('descripcion')} />
        <TextField label="Vigente desde" type="date" value={form.desde} onChange={update('desde')} />
        <TextField label="Vigente hasta (opcional)" type="date" value={form.hasta} onChange={update('hasta')} />
      </div>
      <div className="form-actions">
        <SubmitButton loading={saving} loadingLabel="Guardando…" className="btn btn-outline">Guardar datos</SubmitButton>
      </div>
    </form>
  );
}

/** `titleAs`: «h1» cuando la pantalla no tiene otro título principal (matrices globales); «h2» dentro de una institución. */
export function MatrixDetail({ idMatriz, onOpenMatrix, handleOperationError, onChanged, titleAs: Title = 'h2' }) {
  const [matrix, setMatrix] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [confirming, setConfirming] = useState(null);
  const [busy, setBusy] = useState(false);
  const [editingRule, setEditingRule] = useState(null); // null: cerrado · 'new' · regla
  const [validation, setValidation] = useState(null);
  const [audit, setAudit] = useState(null);

  const load = useCallback(async () => {
    try {
      setMatrix(await matricesApi.getMatrix(idMatriz));
      setError('');
    } catch (loadError) {
      setError(handleOperationError(loadError));
    }
  }, [idMatriz, handleOperationError]);

  useEffect(() => {
    setMatrix(null);
    setAudit(null);
    setValidation(null);
    setEditingRule(null);
    load();
  }, [load]);

  function adopt(updated, message) {
    setMatrix(updated);
    setValidation(null);
    if (message) setNotice(message);
    onChanged?.(updated);
  }

  async function run(name, call, message) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await call();
      setConfirming(null);
      if (name === 'version') {
        onOpenMatrix?.(result.idMatriz);
        return;
      }
      adopt(result, message);
    } catch (actionError) {
      const message = handleOperationError(actionError);
      setConfirming(null);
      await load(); // refresca el estado real; el mensaje del rechazo se muestra después para que no se borre
      setError(message);
    } finally {
      setBusy(false);
    }
  }

  async function validate() {
    setBusy(true);
    setError('');
    try {
      setValidation(await matricesApi.validateMatrix(idMatriz));
    } catch (validateError) {
      setError(handleOperationError(validateError));
    } finally {
      setBusy(false);
    }
  }

  async function toggleAudit() {
    if (audit) {
      setAudit(null);
      return;
    }
    try {
      setAudit(await matricesApi.getMatrixAudit(idMatriz));
    } catch (auditError) {
      setError(handleOperationError(auditError));
    }
  }

  async function saveRule(payload) {
    const updated = editingRule === 'new'
      ? await matricesApi.addRule(idMatriz, payload)
      : await matricesApi.updateRule(idMatriz, editingRule.idReglaMatriz, payload);
    adopt(updated, editingRule === 'new' ? 'Agregamos la regla.' : 'Guardamos la regla.');
    setEditingRule(null);
  }

  if (error && !matrix) return <Alert>{error}</Alert>;
  if (!matrix) return <p className="field-hint" role="status">Cargando matriz…</p>;

  const { permisos } = matrix;
  const CONFIRMS = {
    activate: { text: matrix.estado === 'BORRADOR' ? '¿Activar esta versión? La activa actual dejará de usarse para nuevas mediciones.' : '¿Volver a activar esta versión?', run: () => run('activate', () => matricesApi.activateMatrix(idMatriz), 'La versión quedó activa.') },
    deactivate: { text: '¿Desactivar esta versión? Las nuevas mediciones usarán la matriz de respaldo.', run: () => run('deactivate', () => matricesApi.deactivateMatrix(idMatriz), 'La versión quedó inactiva.') },
    archive: { text: '¿Archivar esta versión? Se conserva en el historial pero no se puede volver a usar.', run: () => run('archive', () => matricesApi.archiveMatrix(idMatriz), 'La versión quedó archivada.') },
    version: { text: '¿Crear una versión nueva en borrador con las mismas reglas?', run: () => run('version', () => matricesApi.createVersion(idMatriz)) },
  };

  return (
    <>
      <section className="panel" aria-labelledby="matriz-titulo">
        <div className="panel-head">
          <div className="panel-title">
            <span className="panel-icon"><ShieldCheck size={22} aria-hidden="true" /></span>
            <div>
              <Title id="matriz-titulo">{matrix.nombre} · versión {matrix.version}</Title>
              <p>
                <Badge tone={toneFromClass(stateBadge(matrix.estado))}>{MATRIX_STATES[matrix.estado]}</Badge>{' '}
                {MATRIX_SCOPES[matrix.ambito]}{matrix.nombreInstitucion ? ` · ${matrix.nombreInstitucion}` : ''}
              </p>
            </div>
          </div>
        </div>
        {notice && <Alert kind="success">{notice}</Alert>}
        {error && <Alert>{error}</Alert>}
        <dl className="data-list">
          <div><dt>Vigencia</dt><dd>{formatDate(matrix.fechaVigenciaDesde)}{matrix.fechaVigenciaHasta ? ` al ${formatDate(matrix.fechaVigenciaHasta)}` : ' en adelante'}</dd></div>
          <div><dt>Descripción</dt><dd className={matrix.descripcion ? undefined : 'is-empty'}>{matrix.descripcion || 'Sin descripción'}</dd></div>
          <div><dt>Reglas</dt><dd>{matrix.cantidadReglas}</dd></div>
          <div><dt>Creada</dt><dd>{formatDateTime(matrix.fechaCreacion)}{matrix.creadaPor?.por ? ` · ${matrix.creadaPor.por}` : ''}</dd></div>
          {matrix.ultimaModificacion && (
            <div><dt>Última modificación</dt><dd>{formatDateTime(matrix.ultimaModificacion.fecha)}{matrix.ultimaModificacion.por ? ` · ${matrix.ultimaModificacion.por}` : ''}</dd></div>
          )}
        </dl>
        {matrix.medicionesRegistradas > 0 && (
          <Alert kind="info">
            Esta versión se usó en {matrix.medicionesRegistradas} {matrix.medicionesRegistradas === 1 ? 'medición' : 'mediciones'}: forma parte del historial y no se modifica.
          </Alert>
        )}
        {matrix.estado !== 'BORRADOR' && (
          <p className="field-hint">Una versión activada no se edita. Para cambiarla, creá una versión nueva.</p>
        )}

        <div className="form-actions" aria-label="Acciones de la matriz">
          {confirming ? (
            <>
              <span className="field-hint">{CONFIRMS[confirming].text}</span>
              <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => setConfirming(null)}>Volver</button>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={CONFIRMS[confirming].run}>
                {busy && <span className="spinner" aria-hidden="true" />} Confirmar
              </button>
            </>
          ) : (
            <>
              {permisos.puedeEditar || permisos.puedeActivar || permisos.puedeDesactivar ? (
                <button type="button" className="btn btn-ghost" disabled={busy} onClick={validate}>
                  <CheckCircle2 size={16} aria-hidden="true" /> Validar reglas
                </button>
              ) : null}
              {permisos.puedeActivar && (
                <button type="button" className="btn btn-primary" onClick={() => setConfirming('activate')}>
                  <Play size={16} aria-hidden="true" /> Activar
                </button>
              )}
              {permisos.puedeDesactivar && (
                <button type="button" className="btn btn-outline" onClick={() => setConfirming('deactivate')}>
                  <PowerOff size={16} aria-hidden="true" /> Desactivar
                </button>
              )}
              {permisos.puedeCrearVersion && (
                <button type="button" className="btn btn-outline" onClick={() => setConfirming('version')}>
                  <CopyPlus size={16} aria-hidden="true" /> Crear nueva versión
                </button>
              )}
              {permisos.puedeArchivar && (
                <button type="button" className="btn btn-ghost" onClick={() => setConfirming('archive')}>
                  <Archive size={16} aria-hidden="true" /> Archivar
                </button>
              )}
              {permisos.puedeVerAuditoria && (
                <button type="button" className="btn btn-ghost" onClick={toggleAudit}>
                  <History size={16} aria-hidden="true" /> {audit ? 'Ocultar auditoría' : 'Ver auditoría'}
                </button>
              )}
            </>
          )}
        </div>

        {validation?.advertencias?.length > 0 && (
          <Alert kind="info">
            <b>Para tener en cuenta (no impide activar):</b>
            <ul>{validation.advertencias.map((warning, index) => <li key={`${warning.codigo}-${index}`}>{warning.mensaje}</li>)}</ul>
          </Alert>
        )}
        {validation && (
          validation.valida ? (
            <Alert kind="success">La matriz es válida y se puede activar.</Alert>
          ) : (
            <Alert>
              <b>La matriz no es válida:</b>
              <ul>{validation.problemas.map((problem, index) => <li key={`${problem.codigo}-${index}`}>{problem.mensaje}</li>)}</ul>
            </Alert>
          )
        )}
      </section>

      {permisos.puedeEditar && <DraftForm key={matrix.idMatriz} matrix={matrix} onSaved={(updated) => adopt(updated, 'Guardamos los datos del borrador.')} handleOperationError={handleOperationError} />}

      <section className="panel" aria-labelledby="matriz-reglas">
        <div className="panel-head">
          <h2 id="matriz-reglas">Reglas</h2>
          {permisos.puedeEditar && editingRule === null && (
            <button type="button" className="btn btn-primary" onClick={() => setEditingRule('new')}>Agregar regla</button>
          )}
        </div>
        <p className="field-hint">
          Los límites de glucosa son valores de referencia de la configuración, no un algoritmo: seleccionar una regla no
          calcula ninguna glucosa.
        </p>
        {editingRule !== null && (
          <RuleEditor key={editingRule === 'new' ? 'new' : editingRule.idReglaMatriz} rule={editingRule === 'new' ? null : editingRule}
            onSave={saveRule} onCancel={() => setEditingRule(null)} handleOperationError={handleOperationError} />
        )}
        {matrix.reglas.length === 0 ? (
          <p className="field-hint">Esta matriz todavía no tiene reglas.</p>
        ) : (
          <RulesTable rules={matrix.reglas} caption="Reglas de la matriz"
            renderActions={permisos.puedeEditar ? (rule) => (
              <span className="member-actions">
                <button type="button" className="btn btn-ghost" onClick={() => setEditingRule(rule)}
                  aria-label={`Editar regla ${rule.codigoRegla}`}><Pencil size={16} aria-hidden="true" /></button>
                <button type="button" className="btn btn-ghost" disabled={busy}
                  onClick={() => run('rule', () => matricesApi.deleteRule(idMatriz, rule.idReglaMatriz), `Eliminamos la regla ${rule.codigoRegla}.`)}
                  aria-label={`Eliminar regla ${rule.codigoRegla}`}><Trash2 size={16} aria-hidden="true" /></button>
              </span>
            ) : undefined} />
        )}
      </section>

      {audit && (
        <section className="panel" aria-labelledby="matriz-auditoria">
          <h2 id="matriz-auditoria">Auditoría</h2>
          <ul className="member-list-items" aria-label="Auditoría de la matriz">
            {audit.map((entry, index) => (
              <li key={`${entry.fechaHora}-${index}`} className="member-row">
                <span>
                  <b>{AUDIT_ACTIONS[entry.accion] ?? entry.accion}</b>
                  <small> · {formatDateTime(entry.fechaHora)}{entry.usuario ? ` · ${entry.usuario}` : ''}</small>
                </span>
                <Badge tone={entry.resultado === 'EXITO' ? 'success' : 'neutral'}>{entry.resultado === 'EXITO' ? 'Correcto' : 'Rechazado'}</Badge>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
