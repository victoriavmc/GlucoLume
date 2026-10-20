// Auditoría de la administración de la plataforma, en tres ámbitos de consulta (solo ADMINISTRADOR_PLATAFORMA; FastAPI lo exige en cada llamada):
//   · Plataforma general  – operaciones administrativas globales y eventos de seguridad, con el panel de accesos fallidos y actividad sospechosa.
//   · Instituciones       – los eventos de UNA institución elegida, distinguiendo al personal de la administración de GlucoLume.
//   · Cuentas individuales – los eventos de una cuenta (como autora o como afectada). Abrir su ficha queda registrado en la auditoría.
// El ámbito, la institución y la cuenta elegidos viven en la URL (volver desde un detalle recupera la misma vista). Los eventos se piden por
// página al backend: nunca se cargan en bloque. No se muestran mediciones, contraseñas, códigos MFA ni datos médicos.

import { Building2, Globe2, Search, UserSearch, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Navigate, useSearchParams } from 'react-router-dom';

import * as auditApi from '../../../api/auditApi.js';
import { useAuth } from '../../../auth/AuthContext.jsx';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Badge } from '../../../components/Badge.jsx';
import { EmptyState } from '../../../components/EmptyState.jsx';
import { Alert, TextField } from '../../../components/FormControls.jsx';
import { PageHeader } from '../../../components/PageHeader.jsx';
import { TabPanel, Tabs } from '../../../components/Tabs.jsx';
import { formatInstant } from '../../../utils/dateTime.js';
import { ACCOUNT_TYPES } from '../accountFormat.js';
import './Audit.css';
import { AuditSecurityPanel } from './AuditSecurity.jsx';
import { AuditView } from './AuditView.jsx';

const SCOPES = [
  { key: 'plataforma', label: 'Plataforma general', icon: Globe2 },
  { key: 'instituciones', label: 'Instituciones', icon: Building2 },
  { key: 'cuentas', label: 'Cuentas individuales', icon: UserSearch },
];
const ID_BASE = 'auditoria-ambito';
const STATE_TONES = { ACTIVO: 'success', PENDIENTE: 'warning', BLOQUEADO: 'danger', ELIMINADO: 'neutral' };

/** Resultados de una búsqueda con demora: no consulta en cada tecla y descarta respuestas que llegan fuera de orden. */
function useSearch(run, query, minimum) {
  const [state, setState] = useState({ items: null, error: '' });
  const latest = useRef(0);
  useEffect(() => {
    if (query.trim().length < minimum) { setState({ items: null, error: '' }); return undefined; }
    const ticket = ++latest.current;
    const timer = setTimeout(() => {
      run(query.trim()).then(
        (items) => ticket === latest.current && setState({ items, error: '' }),
        (error) => ticket === latest.current && setState({ items: [], error: friendlyError(error) }),
      );
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);
  return state;
}

function SearchResults({ label, state, empty, children }) {
  if (state.error) return <Alert>{state.error}</Alert>;
  if (state.items === null) return null;
  if (state.items.length === 0) return <p className="field-hint" role="status">{empty}</p>;
  return <ul className="audit-pick-list" aria-label={label}>{children}</ul>;
}

function InstitutionScope({ id, onChoose, onClear, onViewEvents, preset }) {
  const [query, setQuery] = useState('');
  const [all, setAll] = useState({ items: null, error: '' });
  const found = useSearch(auditApi.listAuditInstitutions, query, 2);
  const [name, setName] = useState('');

  useEffect(() => {
    let active = true;
    auditApi.listAuditInstitutions('').then((items) => active && setAll({ items, error: '' }), (error) => active && setAll({ items: [], error: friendlyError(error) }));
    return () => { active = false; };
  }, []);
  const shown = query.trim().length >= 2 ? found : all;
  const selectedName = name || (all.items ?? []).find((item) => item.clave === id)?.nombre || 'Institución elegida';
  const loadPage = useCallback((filters) => auditApi.listGlobalAudit(filters), []);
  const loadSummary = useCallback((filters) => auditApi.getGlobalAuditSummary(filters), []);

  return (
    <>
      <section className="panel" aria-labelledby="auditoria-institucion">
        <div className="panel-title">
          <span className="panel-icon is-lg"><Building2 size={26} aria-hidden="true" /></span>
          <div><h2 id="auditoria-institucion">Institución a auditar</h2><p>Solo se muestran los eventos asociados a la institución elegida. No se mezclan con los de otras.</p></div>
        </div>
        {id ? (
          <p className="audit-chosen">
            <b>{selectedName}</b>
            <button type="button" className="btn btn-ghost" onClick={onClear}><X size={16} aria-hidden="true" /> Elegir otra institución</button>
          </p>
        ) : (
          <>
            <TextField label="Buscar institución" icon={Search} value={query} maxLength={100} onChange={(event) => setQuery(event.target.value)}
              placeholder="Parte del nombre" />
            <SearchResults label="Instituciones" state={shown} empty="No encontramos instituciones con ese nombre.">
              {shown.items?.map((item) => (
                <li key={item.clave}>
                  <button type="button" className="audit-pick" onClick={() => { setName(item.nombre); onChoose(item.clave); }}>
                    <Building2 size={18} aria-hidden="true" /> {item.nombre}
                  </button>
                </li>
              ))}
            </SearchResults>
          </>
        )}
      </section>
      {id ? (
        <>
          <AuditSecurityPanel idInstitucion={id} onViewEvents={onViewEvents} title="Seguridad de esta institución" />
          <AuditView embedded global admin hideInstitution fixedParams={{ idInstitucion: id }} urlParams={{ ambito: 'instituciones', institucion: id }}
            loadPage={loadPage} loadSummary={loadSummary} handleOperationError={friendlyError} preset={preset} />
        </>
      ) : (
        <EmptyState icon={Building2} title="Elegí una institución para ver su auditoría."
          description="Verás sus altas y bajas de cuentas, accesos fallidos de su personal, exportaciones y cambios administrativos." />
      )}
    </>
  );
}

function AccountHeader({ id }) {
  const [account, setAccount] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    setAccount(null);
    setError('');
    auditApi.getAuditAccount(id).then((result) => active && setAccount(result), (loadError) => active && setError(friendlyError(loadError)));
    return () => { active = false; };
  }, [id]);
  if (error) return <Alert>{error}</Alert>;
  if (!account) return <p className="field-hint" role="status">Cargando la ficha de la cuenta…</p>;
  return (
    <section className="panel audit-account" aria-labelledby="auditoria-cuenta">
      <div className="panel-head">
        <h2 id="auditoria-cuenta">{account.nombre ?? 'Cuenta sin nombre'}{account.usuario && <small> @{account.usuario}</small>}</h2>
        <Badge tone={STATE_TONES[account.estado] ?? 'neutral'}>{account.estado === 'ACTIVO' ? 'Activa' : account.estado === 'BLOQUEADO' ? 'Bloqueada' : account.estado === 'PENDIENTE' ? 'Pendiente' : 'Eliminada'}</Badge>
      </div>
      <dl className="data-list audit-summary-list">
        <div><dt>Tipo de cuenta</dt><dd>{ACCOUNT_TYPES[account.tipoCuenta] ?? account.tipoCuenta}</dd></div>
        <div><dt>Correo</dt><dd>{account.correo ?? '—'}</dd></div>
        <div><dt>Alta</dt><dd>{formatInstant(account.fechaCreacion)}</dd></div>
        <div><dt>Verificación en dos pasos</dt><dd>{account.mfaHabilitado ? 'Activada' : 'No activada'}</dd></div>
        <div><dt>Accesos fallidos en 24 h</dt><dd>{account.fallosAcceso24h}</dd></div>
        <div><dt>Último acceso exitoso</dt><dd>{account.ultimoAccesoExitoso ? formatInstant(account.ultimoAccesoExitoso) : 'Sin registro'}</dd></div>
        {account.bloqueadaHasta && <div><dt>Bloqueada hasta</dt><dd>{formatInstant(account.bloqueadaHasta)}</dd></div>}
        {account.instituciones.length > 0 && (
          <div><dt>Instituciones</dt><dd>{account.instituciones.map((item) => `${item.institucion ?? 'Institución'} (${item.rol.toLowerCase()}, ${item.estado.toLowerCase()})`).join(' · ')}</dd></div>
        )}
      </dl>
      <p className="field-hint">No incluye mediciones ni datos médicos. Abrir esta ficha queda registrado en la auditoría a tu nombre.</p>
    </section>
  );
}

function AccountScope({ id, onChoose, onClear }) {
  const [query, setQuery] = useState('');
  const found = useSearch(auditApi.searchAuditAccounts, query, 3);
  const loadPage = useCallback((filters) => auditApi.listGlobalAudit(filters), []);
  const loadSummary = useCallback((filters) => auditApi.getGlobalAuditSummary(filters), []);
  return (
    <>
      <section className="panel" aria-labelledby="auditoria-buscar-cuenta">
        <div className="panel-title">
          <span className="panel-icon is-lg"><UserSearch size={26} aria-hidden="true" /></span>
          <div>
            <h2 id="auditoria-buscar-cuenta">Cuenta</h2>
            <p>Consulta autorizada de los eventos de una cuenta: creación, baja, reactivación, exportaciones, accesos fallidos y bloqueos.</p>
          </div>
        </div>
        {id ? (
          <p className="audit-chosen">
            <button type="button" className="btn btn-ghost" onClick={onClear}><X size={16} aria-hidden="true" /> Elegir otra cuenta</button>
          </p>
        ) : (
          <>
            <TextField label="Buscar cuenta" icon={Search} value={query} maxLength={100} onChange={(event) => setQuery(event.target.value)}
              placeholder="Nombre, usuario o correo (mínimo 3 caracteres)"
              hint="Para investigar intentos sobre un correo que no existe, usá «Correo o usuario consultado» en Plataforma general → Más filtros." />
            <SearchResults label="Cuentas encontradas" state={found} empty="No encontramos cuentas con esos datos.">
              {found.items?.map((item) => (
                <li key={item.idUsuario}>
                  <button type="button" className="audit-pick" onClick={() => onChoose(item.idUsuario)}>
                    <UserSearch size={18} aria-hidden="true" />
                    <span><b>{item.nombre ?? 'Sin nombre'}</b>{item.usuario && <> · @{item.usuario}</>}<small className="audit-note">{item.correo} · {ACCOUNT_TYPES[item.tipoCuenta] ?? item.tipoCuenta}</small></span>
                  </button>
                </li>
              ))}
            </SearchResults>
          </>
        )}
      </section>
      {id ? (
        <>
          <AccountHeader id={id} />
          <AuditView embedded global admin fixedParams={{ idCuenta: id }} urlParams={{ ambito: 'cuentas', cuenta: id }}
            loadPage={loadPage} loadSummary={loadSummary} handleOperationError={friendlyError} />
        </>
      ) : (
        <EmptyState icon={UserSearch} title="Buscá una cuenta para ver su auditoría."
          description="Solo la administración de la plataforma puede consultar esta vista." />
      )}
    </>
  );
}

export function AdminAuditPage() {
  const { account } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [preset, setPreset] = useState(null);
  const loadPage = useCallback((filters) => auditApi.listGlobalAudit(filters), []);
  const loadSummary = useCallback((filters) => auditApi.getGlobalAuditSummary(filters), []);
  if (account.usuario.tipoCuenta !== 'ADMINISTRADOR_PLATAFORMA') return <Navigate to="/app/inicio" replace />;

  const scope = SCOPES.some((item) => item.key === searchParams.get('ambito')) ? searchParams.get('ambito') : 'plataforma';
  const viewEvents = (filters) => setPreset({ id: Date.now(), filters });
  const go = (next) => { setPreset(null); setSearchParams(next, { replace: true }); };

  return (
    <div className="page audit">
      <PageHeader title="Auditoría general"
        description="Operaciones administrativas, accesos fallidos y eventos de seguridad de GlucoLume, por plataforma, por institución o por cuenta. Solo lectura: los registros no se editan ni se eliminan desde acá; su conservación la fija una política técnica." />
      <Tabs label="Ámbito de la auditoría" items={SCOPES} value={scope} idBase={ID_BASE} variant="underline"
        onChange={(key) => go(key === 'plataforma' ? {} : { ambito: key })} />
      <TabPanel idBase={ID_BASE} value={scope} className="audit-scope">
        {scope === 'plataforma' && (
          <>
            <AuditSecurityPanel onViewEvents={viewEvents} />
            <AuditView embedded global loadPage={loadPage} loadSummary={loadSummary} handleOperationError={friendlyError} preset={preset} />
          </>
        )}
        {scope === 'instituciones' && (
          <InstitutionScope id={searchParams.get('institucion')} preset={preset} onViewEvents={viewEvents}
            onChoose={(id) => go({ ambito: 'instituciones', institucion: id })} onClear={() => go({ ambito: 'instituciones' })} />
        )}
        {scope === 'cuentas' && (
          <AccountScope id={searchParams.get('cuenta')} onChoose={(id) => go({ ambito: 'cuentas', cuenta: id })} onClear={() => go({ ambito: 'cuentas' })} />
        )}
      </TabPanel>
    </div>
  );
}
