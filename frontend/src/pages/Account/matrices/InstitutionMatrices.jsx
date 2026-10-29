// /app/instituciones/:id/matrices — Matrices de estimación de la institución (propietario y moderador).
//   A. Matriz actualmente utilizada (la que decide el backend: la institucional activa o, si no hay, la global activa).
//   B. Reglas de esa matriz, en un desplegable (global o institucional; la global es de solo lectura).
//   C. Acciones: crear una matriz institucional y volver a utilizar la global.
//   D. Matrices institucionales: todas las versiones, con estado, reglas y activación.
// Todo sale de FastAPI (matriz vigente, reglas, permisos y estados); nada de la matriz global está escrito en React. Guardar una matriz
// no la activa, y activar o volver a la global nunca borra versiones ni modifica las mediciones ya registradas (cada medición guarda la
// matriz con la que se registró). GlucoLume es un prototipo experimental: las matrices son configuraciones de referencia para
// interpretar estimaciones experimentales, no una herramienta de diagnóstico ni una recomendación clínica.

import { ChevronDown, ChevronRight, Globe2, Layers, Pencil, Play, Plus, RotateCcw } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useOutletContext } from 'react-router-dom';

import * as matricesApi from '../../../api/matricesApi.js';
import { Badge } from '../../../components/Badge.jsx';
import { Alert } from '../../../components/FormControls.jsx';
import { CreateInstitutionMatrixForm } from './CreateInstitutionMatrixForm.jsx';
import { RulesTable } from './MatrixRules.jsx';
import { MATRIX_SCOPES, MATRIX_STATES, formatDate, formatDateTime } from './matrixFormat.js';
import { MatrixReference } from './MatrixReference.jsx';
import './Matrices.css';

const pluralRules = (count) => `${count} regla${count === 1 ? '' : 's'}`;

/** Estado de una matriz: «En uso» (verde) solo para la ACTIVA. */
function StateBadge({ state }) {
  if (state === 'ACTIVA') return <Badge tone="success" className="matrix-inuse">En uso</Badge>;
  return <Badge tone="neutral">{MATRIX_STATES[state] ?? state}</Badge>;
}

/** Desplegable de reglas: contraído al inicio; al abrirlo muestra todas (cargando, sin reglas y error se distinguen). */
function RulesDisclosure({ idMatriz, detail, label = 'Ver reglas de esta matriz', readOnlyNote, handleOperationError }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState(detail ? { status: 'ok', matrix: detail } : { status: 'idle' });
  const panelId = `reglas-${idMatriz}`;

  useEffect(() => {
    if (detail) setState({ status: 'ok', matrix: detail });
  }, [detail]);

  const fetchRules = useCallback(async () => {
    setState({ status: 'loading' });
    try {
      setState({ status: 'ok', matrix: await matricesApi.getMatrix(idMatriz) });
    } catch (error) {
      setState({ status: 'error', message: handleOperationError(error) });
    }
  }, [idMatriz, handleOperationError]);

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next && state.status === 'idle') fetchRules();
  }

  return (
    <div className="rules-disclosure">
      <button type="button" className="btn btn-outline rules-toggle" aria-expanded={open} aria-controls={panelId} onClick={toggle}>
        {open ? <ChevronDown size={18} aria-hidden="true" /> : <ChevronRight size={18} aria-hidden="true" />} {label}
      </button>
      {open && (
        <div id={panelId} className="rules-panel" role="region" aria-label={`Reglas de la matriz`}>
          {readOnlyNote && <p className="field-hint">{readOnlyNote}</p>}
          {state.status === 'loading' || state.status === 'idle' ? (
            <p className="field-hint" role="status">Cargando reglas…</p>
          ) : state.status === 'error' ? (
            <>
              <Alert>No pudimos recuperar las reglas de esta matriz. {state.message}</Alert>
              <button type="button" className="btn btn-outline" onClick={fetchRules}><RotateCcw size={16} aria-hidden="true" /> Reintentar</button>
            </>
          ) : state.matrix.reglas.length === 0 ? (
            <p className="field-hint">Esta matriz todavía no tiene reglas configuradas.</p>
          ) : (
            <>
              <p className="field-hint">
                {pluralRules(state.matrix.reglas.length)}. Cada regla indica a quién se aplica y el intervalo de glucosa de referencia. Son valores de
                referencia de la configuración: no calculan ninguna glucosa ni constituyen un diagnóstico.
              </p>
              <RulesTable rules={state.matrix.reglas} caption={`Reglas de ${state.matrix.nombre}, versión ${state.matrix.version}`} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

/** A. Tarjeta de la matriz en uso. */
function ActiveMatrixCard({ summary, detail, institution, handleOperationError }) {
  const global = summary.ambito === 'GLOBAL';
  return (
    <section className="panel matrix-active" aria-labelledby="matriz-en-uso">
      <div className="matrix-active-head">
        <span className="panel-icon is-lg" aria-hidden="true">{global ? <Globe2 size={26} /> : <Layers size={26} />}</span>
        <div>
          <p className="matrix-eyebrow" id="matriz-en-uso">Matriz de estimación actualmente utilizada</p>
          <h3>{summary.nombre} · versión {summary.version}</h3>
          <p className="matrix-tags">
            <StateBadge state={summary.estado} />
            <Badge tone="brand">{MATRIX_SCOPES[summary.ambito]}</Badge>
            {global && <span className="chip">Solo lectura</span>}
          </p>
        </div>
      </div>
      <p className="matrix-explain">
        {global
          ? 'Esta matriz la define la plataforma GlucoLume y es la que se aplica a las mediciones de la institución. Si querés modificarla, creá tu propia matriz institucional.'
          : `${institution.nombre} utiliza actualmente una matriz institucional propia. La matriz global de GlucoLume queda como respaldo.`}
      </p>
      <dl className="data-list matrix-facts">
        <div><dt>Estado</dt><dd>Activa</dd></div>
        <div><dt>Origen</dt><dd>{MATRIX_SCOPES[summary.ambito]}</dd></div>
        <div><dt>Descripción</dt><dd className={detail?.descripcion ? undefined : 'is-empty'}>{detail ? (detail.descripcion || 'Sin descripción') : 'No disponible'}</dd></div>
        <div><dt>Referencia base</dt><dd><MatrixReference name={summary.referenciaBase} url={summary.urlReferencia} /></dd></div>
        <div><dt>Reglas</dt><dd>{detail ? detail.cantidadReglas : 'No disponible'}</dd></div>
        <div><dt>Vigente desde</dt><dd>{detail ? formatDate(detail.fechaVigenciaDesde) : 'No disponible'}</dd></div>
        <div><dt>Creada</dt><dd>{detail ? formatDateTime(detail.fechaCreacion) : 'No disponible'}</dd></div>
      </dl>
      <RulesDisclosure idMatriz={summary.idMatriz} detail={detail} handleOperationError={handleOperationError}
        readOnlyNote={global ? 'La matriz global es de solo lectura: ninguna institución puede modificar sus reglas.' : undefined} />
    </section>
  );
}

function VersionCard({ item, busy, confirming, onConfirm, onCancelConfirm, onActivate, handleOperationError }) {
  const canActivate = item.estado === 'BORRADOR' || item.estado === 'INACTIVA';
  return (
    <li className={`matrix-version${item.estado === 'ACTIVA' ? ' is-active' : ''}`}>
      <div className="matrix-version-head">
        <div>
          <h4><Link to={item.idMatriz} className="patient-link">{item.nombre} · versión {item.version}</Link></h4>
          <p className="field-hint">{item.descripcion || 'Sin descripción.'}</p>
        </div>
        <StateBadge state={item.estado} />
      </div>
      <dl className="matrix-version-facts">
        <div><dt>Origen</dt><dd>Institucional</dd></div>
        <div><dt>Referencia base</dt><dd><MatrixReference name={item.referenciaBase} url={item.urlReferencia} /></dd></div>
        <div><dt>Creada</dt><dd>{formatDate(item.fechaCreacion)}</dd></div>
        <div><dt>Reglas</dt><dd>{item.cantidadReglas}</dd></div>
        <div><dt>Mediciones</dt><dd>{item.medicionesRegistradas > 0 ? `Usada en ${item.medicionesRegistradas}` : 'Sin usar'}</dd></div>
      </dl>
      <div className="matrix-version-actions">
        {confirming ? (
          <>
            <span className="field-hint">¿Activar esta versión? Las próximas mediciones la usarán; la activa actual se conserva como versión histórica.</span>
            <button type="button" className="btn btn-ghost" disabled={busy} onClick={onCancelConfirm}>Volver</button>
            <button type="button" className="btn btn-primary" disabled={busy} onClick={onActivate}>
              {busy && <span className="spinner" aria-hidden="true" />} Confirmar activación
            </button>
          </>
        ) : (
          <>
            <Link to={item.idMatriz} className="btn btn-outline" aria-label={`Ver matriz ${item.nombre} versión ${item.version}`}>Ver matriz</Link>
            {item.estado === 'BORRADOR' && (
              <Link to={item.idMatriz} className="btn btn-outline" aria-label={`Editar borrador ${item.nombre} versión ${item.version}`}>
                <Pencil size={16} aria-hidden="true" /> Editar borrador
              </Link>
            )}
            {canActivate && (
              <button type="button" className="btn btn-primary" onClick={onConfirm} aria-label={`Activar ${item.nombre} versión ${item.version}`}>
                <Play size={16} aria-hidden="true" /> Activar
              </button>
            )}
          </>
        )}
      </div>
      <RulesDisclosure idMatriz={item.idMatriz} label="Ver reglas" handleOperationError={handleOperationError} />
    </li>
  );
}

export function InstitutionMatricesPage() {
  const { institution, handleOperationError } = useOutletContext();
  const navigate = useNavigate();
  const location = useLocation();
  const [overview, setOverview] = useState(null);
  const [effective, setEffective] = useState(null); // detalle de la matriz en uso (con reglas y permisos)
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [creating, setCreating] = useState(Boolean(location.state?.crear));
  const [confirming, setConfirming] = useState(null); // 'global' | idMatriz
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const result = await matricesApi.getInstitutionMatrices(institution.idInstitucion);
      setOverview(result);
      setError('');
      setEffective(null);
      if (result.efectiva) {
        try {
          setEffective(await matricesApi.getMatrix(result.efectiva.idMatriz));
        } catch {
          setEffective(null); // la tarjeta se muestra con lo que se sabe y las reglas se reintentan al desplegar
        }
      }
    } catch (loadError) {
      setError(handleOperationError(loadError));
      setOverview({ institucionActiva: null, globalActiva: null, efectiva: null, versiones: [] });
    }
  }, [institution.idInstitucion, handleOperationError]);

  useEffect(() => {
    load();
  }, [load]);

  async function run(call, message) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await call();
      setConfirming(null);
      setNotice(message);
      await load();
    } catch (actionError) {
      const text = handleOperationError(actionError);
      setConfirming(null);
      await load();
      setError(text);
    } finally {
      setBusy(false);
    }
  }

  const own = overview?.institucionActiva;
  const canUseGlobal = Boolean(own && effective?.idMatriz === own.idMatriz && effective.permisos.puedeDesactivar);

  return (
    <>
      <section className="panel" aria-labelledby="inst-matrices">
        <div className="panel-head">
          <div className="panel-title">
            <span className="panel-icon" aria-hidden="true"><Layers size={22} /></span>
            <div>
              <h2 id="inst-matrices">Matrices de estimación</h2>
              <p>Configuración de referencia para las mediciones de glucosa experimental de esta institución.</p>
            </div>
          </div>
        </div>
        <p className="field-hint">
          GlucoLume es un prototipo tecnológico experimental y no constituye un dispositivo médico validado. Las matrices son configuraciones de
          referencia para interpretar estimaciones experimentales: no son una herramienta de diagnóstico ni una recomendación clínica.
        </p>
        {notice && <Alert kind="success">{notice}</Alert>}
        {error && <Alert>{error}</Alert>}
      </section>

      {overview === null ? (
        <p className="field-hint" role="status">Cargando matrices…</p>
      ) : overview.efectiva ? (
        <ActiveMatrixCard summary={overview.efectiva} detail={effective} institution={institution} handleOperationError={handleOperationError} />
      ) : error ? null : (
        <section className="panel" aria-labelledby="matriz-en-uso">
          <p className="matrix-eyebrow" id="matriz-en-uso">Matriz de estimación actualmente utilizada</p>
          <Alert kind="info">No hay una matriz activa y vigente: no se pueden iniciar mediciones de glucosa experimental hasta que haya una activa.</Alert>
        </section>
      )}

      {overview !== null && (
        <section className="panel" aria-labelledby="matriz-acciones">
          <h3 id="matriz-acciones">Acciones</h3>
          {creating ? (
            <CreateInstitutionMatrixForm idInstitucion={institution.idInstitucion} handleOperationError={handleOperationError}
              onCancel={() => setCreating(false)}
              onCreated={(created) => navigate(created.idMatriz, {
                state: { notice: `Guardamos «${created.nombre}» (versión ${created.version}) con ${pluralRules(created.cantidadReglas)}. Todavía no se usa: activala cuando quieras desde sus versiones.` },
              })} />
          ) : confirming === 'global' ? (
            <div className="form-actions">
              <span className="field-hint">
                ¿Utilizar la matriz global de GlucoLume? Las próximas mediciones la usarán. Tus matrices institucionales se conservan y podés volver a activarlas.
              </span>
              <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => setConfirming(null)}>Volver</button>
              <button type="button" className="btn btn-primary" disabled={busy}
                onClick={() => run(() => matricesApi.deactivateMatrix(own.idMatriz), 'La institución vuelve a utilizar la matriz global de GlucoLume. Las matrices institucionales se conservan.')}>
                {busy && <span className="spinner" aria-hidden="true" />} Confirmar
              </button>
            </div>
          ) : (
            <div className="form-actions matrix-actions">
              <button type="button" className="btn btn-primary" onClick={() => { setNotice(''); setCreating(true); }}>
                <Plus size={18} aria-hidden="true" /> Crear matriz institucional
              </button>
              {canUseGlobal && (
                <button type="button" className="btn btn-outline" onClick={() => setConfirming('global')}>
                  <Globe2 size={18} aria-hidden="true" /> Utilizar matriz global
                </button>
              )}
            </div>
          )}
        </section>
      )}

      {overview !== null && own && overview.globalActiva && (
        <section className="panel matrix-global-backup" aria-labelledby="matriz-global-respaldo">
          <h3 id="matriz-global-respaldo"><Globe2 size={20} aria-hidden="true" /> Matriz global de GlucoLume (respaldo)</h3>
          <p>
            <b>{overview.globalActiva.nombre} · versión {overview.globalActiva.version}</b> <span className="chip">Solo lectura</span>
          </p>
          <p>Referencia base: <MatrixReference name={overview.globalActiva.referenciaBase} url={overview.globalActiva.urlReferencia} /></p>
          <p className="field-hint">Se usa si la institución no tiene una matriz propia activa.</p>
          <RulesDisclosure idMatriz={overview.globalActiva.idMatriz} label="Ver reglas de la matriz global" handleOperationError={handleOperationError}
            readOnlyNote="La matriz global es de solo lectura: ninguna institución puede modificar sus reglas." />
        </section>
      )}

      {overview !== null && (
        <section className="panel" aria-labelledby="inst-versiones">
          <h3 id="inst-versiones">Matrices institucionales</h3>
          {overview.versiones.length === 0 ? (
            <p className="field-hint">
              Todavía no se crearon matrices institucionales.
              {overview.efectiva?.ambito === 'GLOBAL' ? ' Actualmente se utiliza la matriz global de GlucoLume.' : ''}
            </p>
          ) : (
            <ul className="matrix-versions" aria-label="Matrices institucionales">
              {overview.versiones.map((item) => (
                <VersionCard key={item.idMatriz} item={item} busy={busy} confirming={confirming === item.idMatriz}
                  onConfirm={() => setConfirming(item.idMatriz)} onCancelConfirm={() => setConfirming(null)}
                  onActivate={() => run(() => matricesApi.activateMatrix(item.idMatriz), `Activaste «${item.nombre}» (versión ${item.version}). La versión anterior se conservó como histórica.`)}
                  handleOperationError={handleOperationError} />
              ))}
            </ul>
          )}
        </section>
      )}
    </>
  );
}
