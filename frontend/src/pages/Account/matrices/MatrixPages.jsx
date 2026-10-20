// Pantallas del módulo de matrices:
//   - /app/matrices                       administración de matrices globales (cuentas de plataforma);
//   - /app/instituciones/:id/matrices     matrices de una institución (propietario y moderador);
//   - …/:idMatriz                         detalle de una versión con su editor de reglas.
// Todo sale de FastAPI: el ámbito, la versión activa y las acciones permitidas los decide el backend.

import { ArrowLeft, Layers, Plus } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, Navigate, useNavigate, useOutletContext, useParams } from 'react-router-dom';

import * as matricesApi from '../../../api/matricesApi.js';
import { useAuth } from '../../../auth/AuthContext.jsx';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Badge, toneFromClass } from '../../../components/Badge.jsx';
import { EmptyState } from '../../../components/EmptyState.jsx';
import { Alert, SubmitButton, TextField } from '../../../components/FormControls.jsx';
import { PageHeader } from '../../../components/PageHeader.jsx';
import { MatrixDetail } from './MatrixDetail.jsx';
import { MATRIX_STATES, formatDate, stateBadge } from './matrixFormat.js';

const PLATFORM_ACCOUNTS = ['MODERADOR_PLATAFORMA', 'ADMINISTRADOR_PLATAFORMA'];

function VersionList({ items, emptyText }) {
  if (items.length === 0) return <EmptyState variant="framed" headingLevel={0} title={emptyText} />;
  return (
    <ul className="member-list-items" aria-label="Versiones de matrices">
      {items.map((item) => (
        <li key={item.idMatriz} className="member-row">
          <span>
            <Link to={item.idMatriz} className="patient-link"><b>{item.nombre} · versión {item.version}</b></Link>
            <small> · {item.cantidadReglas} regla{item.cantidadReglas === 1 ? '' : 's'}
              {' '}· vigente desde {formatDate(item.fechaVigenciaDesde)}{item.fechaVigenciaHasta ? ` hasta ${formatDate(item.fechaVigenciaHasta)}` : ''}
              {item.medicionesRegistradas > 0 ? ` · usada en ${item.medicionesRegistradas} ${item.medicionesRegistradas === 1 ? 'medición' : 'mediciones'}` : ''}</small>
          </span>
          <Badge tone={toneFromClass(stateBadge(item.estado))}>{MATRIX_STATES[item.estado]}</Badge>
        </li>
      ))}
    </ul>
  );
}

function CreateMatrixForm({ ambito, idInstitucion, onCreated, onCancel, handleOperationError }) {
  const [form, setForm] = useState({ nombre: '', descripcion: '', desde: '', hasta: '' });
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
    const found = {};
    if (form.nombre.trim().length < 2) found.nombre = 'Ingresá el nombre de la matriz.';
    if (form.hasta && form.desde && form.hasta < form.desde) found.hasta = 'La vigencia no puede terminar antes de empezar.';
    setErrors(found);
    if (Object.keys(found).length) return;
    setSaving(true);
    setError('');
    try {
      onCreated(await matricesApi.createMatrix({
        ambito, idInstitucion, nombre: form.nombre.trim(), descripcion: form.descripcion.trim(),
        fechaVigenciaDesde: form.desde, fechaVigenciaHasta: form.hasta,
      }));
    } catch (createError) {
      setError(handleOperationError(createError));
      setSaving(false);
    }
  }

  return (
    <form className="member-add" onSubmit={handleSubmit} noValidate aria-label="Crear matriz">
      <h3><Plus size={18} aria-hidden="true" /> {ambito === 'GLOBAL' ? 'Crear matriz global' : 'Crear matriz institucional'}</h3>
      <p className="field-hint">Se crea como borrador. Después cargás sus reglas, la validás y la activás.</p>
      {error && <Alert>{error}</Alert>}
      <div className="form-grid">
        <TextField label="Nombre" maxLength={100} value={form.nombre} onChange={update('nombre')} error={errors.nombre} />
        <TextField label="Descripción (opcional)" maxLength={500} value={form.descripcion} onChange={update('descripcion')} />
        <TextField label="Vigente desde (opcional, por defecto hoy)" type="date" value={form.desde} onChange={update('desde')} />
        <TextField label="Vigente hasta (opcional)" type="date" value={form.hasta} onChange={update('hasta')} error={errors.hasta} />
      </div>
      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={saving}>Cancelar</button>
        <SubmitButton loading={saving} loadingLabel="Creando…" className="btn btn-primary">Crear matriz</SubmitButton>
      </div>
    </form>
  );
}

// --- Matrices globales ----------------------------------------------------------------------------------

export function GlobalMatricesPage() {
  const { account } = useAuth();
  const navigate = useNavigate();
  const [items, setItems] = useState(null);
  const [error, setError] = useState('');
  const [creating, setCreating] = useState(false);
  const platform = PLATFORM_ACCOUNTS.includes(account.usuario.tipoCuenta);

  const load = useCallback(async () => {
    try {
      setItems(await matricesApi.listGlobalMatrices());
    } catch (loadError) {
      setError(friendlyError(loadError));
      setItems([]);
    }
  }, []);

  useEffect(() => {
    if (platform) load();
  }, [platform, load]);

  if (!platform) return <Navigate to="/app/inicio" replace />;
  const active = items?.find((item) => item.estado === 'ACTIVA');

  return (
    <div className="page">
      <PageHeader title="Administración de matrices globales" description="Referencia de GlucoLume para usuarios individuales y para instituciones sin matriz propia activa." />
      {error && <Alert>{error}</Alert>}
      <section className="panel" aria-labelledby="globales-activa">
        <div className="panel-head">
          <div className="panel-title">
            <span className="panel-icon"><Layers size={22} aria-hidden="true" /></span>
            <div>
              <h2 id="globales-activa">Matriz global activa</h2>
              <p>Solo una versión global puede estar activa a la vez.</p>
            </div>
          </div>
          {!creating && <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>Crear matriz global</button>}
        </div>
        {items === null ? (
          <p className="field-hint" role="status">Cargando matrices…</p>
        ) : active ? (
          <p><b>{active.nombre} · versión {active.version}</b> · {active.cantidadReglas} regla{active.cantidadReglas === 1 ? '' : 's'}</p>
        ) : (
          <Alert kind="info">No hay una matriz global activa: las mediciones de glucosa no se pueden iniciar hasta activar una.</Alert>
        )}
        {creating && (
          <CreateMatrixForm ambito="GLOBAL" handleOperationError={friendlyError} onCancel={() => setCreating(false)}
            onCreated={(created) => navigate(created.idMatriz)} />
        )}
      </section>
      <section className="panel" aria-labelledby="globales-versiones">
        <h2 id="globales-versiones">Versiones</h2>
        {items !== null && <VersionList items={items} emptyText="Todavía no hay matrices globales. Creá la primera." />}
      </section>
    </div>
  );
}

export function GlobalMatrixDetailPage() {
  const { account } = useAuth();
  const { idMatriz } = useParams();
  const navigate = useNavigate();
  if (!PLATFORM_ACCOUNTS.includes(account.usuario.tipoCuenta)) return <Navigate to="/app/inicio" replace />;
  return (
    <div className="page">
      <Link to=".." relative="path" className="back-link"><ArrowLeft size={16} aria-hidden="true" /> Matrices globales</Link>
      <MatrixDetail idMatriz={idMatriz} handleOperationError={friendlyError} titleAs="h1"
        onOpenMatrix={(id) => navigate(`../${id}`, { relative: 'path' })} />
    </div>
  );
}

// --- Matrices de una institución -----------------------------------------------------------------------

export { InstitutionMatricesPage } from './InstitutionMatrices.jsx';

export function InstitutionMatrixDetailPage() {
  const { handleOperationError } = useOutletContext();
  const { idMatriz } = useParams();
  const navigate = useNavigate();
  return (
    <>
      <Link to=".." relative="path" className="back-link"><ArrowLeft size={16} aria-hidden="true" /> Matrices</Link>
      <MatrixDetail idMatriz={idMatriz} handleOperationError={handleOperationError}
        onOpenMatrix={(id) => navigate(`../${id}`, { relative: 'path' })} />
    </>
  );
}
