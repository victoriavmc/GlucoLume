// Vista de auditoría compartida por la auditoría general (administrador del sistema), la de una institución (el administrador o su
// propietario) y la de una cuenta individual. Cambia solo de dónde salen los datos; el filtrado, la paginación y la autorización ocurren en
// FastAPI/SQL Server.
// Resumen, filtros y listado usan EXACTAMENTE los mismos filtros (y el mismo ámbito: lo fija el backend por la ruta o por `fixedParams`): los
// contadores salen del backend, nunca de la página visible. Nunca se cargan todos los eventos en el navegador: se pide una página por vez.
// Las fechas llegan con su zona. No se muestran contraseñas, tokens ni datos clínicos: el backend no los entrega.
// Colores: verde = exitoso, naranja = advertencia o sospechoso, rojo = error o crítico, gris = informativo. El significado siempre va también
// en texto (nunca solo el color).

import { AlertTriangle, Building2, CheckCircle2, ChevronLeft, ChevronRight, Filter, KeyRound, ListChecks, ShieldAlert, ShieldCheck, User, XCircle } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';

import { Badge } from '../../../components/Badge.jsx';
import { EmptyState } from '../../../components/EmptyState.jsx';
import { Alert, CheckField, SelectField, TextField } from '../../../components/FormControls.jsx';
import { PageHeader } from '../../../components/PageHeader.jsx';
import { BarList, Kpi, KpiGrid } from '../../../components/dashboard.jsx';
import { formatInstant } from '../../../utils/dateTime.js';
import './Audit.css';
import './AuditFilters.css';
import { AUDIT_CHANGED, AuditReviewToggle } from './AuditReviewToggle.jsx';
import {
  ACTOR_ORIGINS, AUDIT_CATEGORIES, AUDIT_CLASSIFICATIONS, AUDIT_MODULES, CLASSIFICATION_HELP, actionLabel, eventName, resultInfo, severityInfo,
} from './auditLabels.js';

export { AUDIT_MODULES, actionLabel };

const PAGE_SIZE = 20;
const BASE_FILTERS = {
  desde: '', hasta: '', usuario: '', modulo: '', accion: '', categoria: '', clasificacion: '', origenActor: '', resultado: '', idInstitucion: '',
  uso: '', estadoCritico: '',
};
// Solo la administración de la plataforma puede filtrar por estos (y solo ella recibe IP, cliente y correlación).
const AUTO_REFRESH_MS = 15000;
const ADMIN_FILTERS = { identificador: '', idCorrelacion: '', ip: '', refIdentificador: '', idCuenta: '' };

function cleanFilters(filters, { withInstitution, admin }) {
  const params = {};
  for (const [key, value] of Object.entries(filters)) {
    if (key === 'idInstitucion' && !withInstitution) continue;
    if (key in ADMIN_FILTERS && !admin) continue;
    if (value) {
      params[key] = typeof value === 'string' ? value.trim() : value;
    }
  }
  return params;
}

/** A. Resumen de actividad: indicadores, accesos y controles de seguridad, y la distribución por módulo (y por institución en la auditoría general). */
function Summary({ summary, failed, global }) {
  if (failed) return <Alert>No pudimos cargar el resumen de actividad ahora. El listado de eventos sigue disponible.</Alert>;
  if (!summary) return <p className="field-hint" role="status">Cargando resumen…</p>;
  const security = summary.accesosFallidos !== undefined;
  return (
    <>
      <KpiGrid label="Resumen de la auditoría" compact>
        <Kpi icon={ListChecks} label="Total de eventos" value={summary.total} />
        <Kpi icon={CheckCircle2} tone="ok" label="Exitosos" value={summary.exitosos} />
        <Kpi icon={XCircle} tone="danger" label="Fallidos" value={summary.fallidos} />
        <Kpi icon={ShieldAlert} tone="warn" label="Operaciones críticas" value={summary.criticas} />
      </KpiGrid>
      {security && (
        <KpiGrid label="Seguridad según los filtros" compact>
          <Kpi icon={KeyRound} tone="warn" label="Accesos fallidos" value={summary.accesosFallidos} />
          <Kpi icon={ShieldAlert} tone="warn" label="Eventos sospechosos" value={summary.sospechosos} />
          <Kpi icon={ShieldCheck} tone="danger" label="Controles activados" value={summary.confirmados} />
        </KpiGrid>
      )}
      {(summary.porModulo.length > 0 || (global && summary.porInstitucion.length > 0)) && (
        <div className="audit-distribution">
          {summary.porModulo.length > 0 && (
            <div className="audit-distribution-block">
              <h3>Actividad por módulo</h3>
              <BarList label="Actividad por módulo"
                items={summary.porModulo.map((item) => ({ label: AUDIT_MODULES[item.clave] ?? item.clave, value: item.total }))} />
            </div>
          )}
          {global && summary.porInstitucion.length > 0 && (
            <div className="audit-distribution-block">
              <h3>Actividad por institución</h3>
              <BarList label="Actividad por institución" items={summary.porInstitucion.map((item) => ({ label: item.nombre, value: item.total }))} />
            </div>
          )}
        </div>
      )}
    </>
  );
}

/** Quién obró: el nombre y, si es la administración de GlucoLume o el sistema, una marca para distinguirlo del personal de la institución. */
const USE_LABELS = { INDIVIDUAL: 'Individual', INSTITUCION: 'Institución', PLATAFORMA: 'Plataforma' };
const USE_ICONS = { INDIVIDUAL: User, INSTITUCION: Building2, PLATAFORMA: ShieldCheck };

/** Uso de la cuenta que obró: individual, institucional o de plataforma (el sistema no tiene cuenta). */
function UseBadge({ uso }) {
  // Sin cuenta que obró (p. ej. un error del servidor): el uso no aplica, no se etiqueta como categoría.
  if (!uso) return <span className="audit-note">—</span>;
  const Icon = USE_ICONS[uso];
  return <Badge tone={uso === 'PLATAFORMA' ? 'brand' : uso === 'INDIVIDUAL' ? 'info' : 'neutral'} icon={Icon}>{USE_LABELS[uso] ?? uso}</Badge>;
}

/** Usuario con inicial, nombre y, solo para la administración, correo. */
function UserCell({ item, admin }) {
  const name = item.usuario ?? 'Sistema';
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase() || '?';
  return (
    <span className="audit-user">
      <span className="audit-avatar" aria-hidden="true">{initials}</span>
      <span className="audit-cell">
        <span className="audit-event">{name}{item.origenActor === 'PLATAFORMA' && <> <Badge tone="brand" size="sm">Administración</Badge></>}</span>
        {admin && item.correoUsuario && <small className="audit-note">{item.correoUsuario}</small>}
        {admin && item.ipOrigen && <small className="audit-note">IP {item.ipOrigen}</small>}
      </span>
    </span>
  );
}

function ActorCell({ item, admin }) {
  return (
    <span className="audit-cell">
      <span>{item.usuario ?? 'Sistema'}{item.origenActor === 'PLATAFORMA' && <> <Badge tone="brand" size="sm">Administración</Badge></>}</span>
      {admin && item.ipOrigen && <small className="audit-note">IP {item.ipOrigen}</small>}
    </span>
  );
}

export function AuditView({
  title, lead, global, embedded = false, showSummary = true, loadPage, loadSummary, handleOperationError, institutionOptions,
  admin = global, hideInstitution = false, fixedParams, urlParams, headingLevel, preset,
}) {
  // Filtros y página viven en la URL: al volver desde un detalle se recupera el mismo listado. `urlParams` (ámbito elegido) se conserva en la
  // URL sin enviarse como filtro; `fixedParams` (la institución o la cuenta elegida) se envía siempre, en el listado y en el resumen.
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const emptyFilters = { ...BASE_FILTERS, ...(admin ? ADMIN_FILTERS : {}) };
  const [filters, setFilters] = useState(() => {
    const initial = { ...emptyFilters };
    for (const key of Object.keys(emptyFilters)) {
      const value = searchParams.get(key);
      if (value) initial[key] = value;
    }
    return initial;
  });
  const [pagina, setPagina] = useState(() => Number(searchParams.get('pagina')) || 1);
  // Una señal de seguridad pide ver sus eventos: reemplaza los filtros por los de la señal (cada pedido trae un `id` nuevo).
  useEffect(() => {
    if (!preset) return;
    setFilters({ ...emptyFilters, ...preset.filters });
    setPagina(1);
    document.getElementById('auditoria-eventos')?.scrollIntoView?.({ block: 'start' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preset?.id]);
  const [page, setPage] = useState(null);
  const [summary, setSummary] = useState(null);
  const [summaryFailed, setSummaryFailed] = useState(false);
  const [options, setOptions] = useState([]);
  const [error, setError] = useState('');

  const withInstitution = global && !hideInstitution;
  const params = cleanFilters(filters, { withInstitution, admin });
  const fixedKey = JSON.stringify(fixedParams ?? {});
  const urlKey = JSON.stringify(urlParams ?? {});

  useEffect(() => {
    setSearchParams({ ...(urlParams ?? {}), ...params, ...(pagina > 1 ? { pagina } : {}) }, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(params), pagina, urlKey]);

  useEffect(() => {
    let active = true;
    setPage(null);
    loadPage({ ...(fixedParams ?? {}), ...params, pagina, tamanioPagina: PAGE_SIZE }).then(
      (result) => active && (setPage(result), setError('')),
      (loadError) => active && (setError(handleOperationError(loadError)), setPage({ items: [], total: 0, pagina: 1, tamanioPagina: PAGE_SIZE })),
    );
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(params), pagina, loadPage, fixedKey]);

  // Sincronización automática: cada 30 s (solo con la pestaña visible) vuelve a pedir el listado y el resumen con los mismos filtros.
  const [refreshTick, setRefreshTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => { if (document.visibilityState === 'visible') setRefreshTick((tick) => tick + 1); }, AUTO_REFRESH_MS);
    return () => clearInterval(timer);
  }, []);
  // Actualización inmediata: al marcar un evento como analizado, o al volver a la pestaña, sin recargar la página.
  useEffect(() => {
    const refresh = () => { if (document.visibilityState === 'visible') setRefreshTick((tick) => tick + 1); };
    window.addEventListener(AUDIT_CHANGED, refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      window.removeEventListener(AUDIT_CHANGED, refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, []);

  useEffect(() => {
    if (refreshTick === 0) return undefined;
    let active = true;
    loadPage({ ...(fixedParams ?? {}), ...params, pagina, tamanioPagina: PAGE_SIZE }).then((result) => active && setPage(result), () => {});
    loadSummary({ ...(fixedParams ?? {}), ...params }).then((result) => active && (setSummary(result), setSummaryFailed(false)), () => active && setSummaryFailed(true));
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshTick]);

  // El resumen usa los mismos filtros que el listado (salvo la institución del selector global, que no cambia las opciones).
  useEffect(() => {
    let active = true;
    setSummary(null);
    setSummaryFailed(false);
    loadSummary({ ...(fixedParams ?? {}), ...params }).then(
      (result) => active && setSummary(result),
      // Un error del resumen se informa: mostrar ceros haría creer que no hay eventos mientras la tabla los lista.
      () => active && setSummaryFailed(true),
    );
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(params), loadSummary, fixedKey]);

  // Las instituciones del selector salen del resumen sin filtrar por institución (global).
  useEffect(() => {
    if (withInstitution && summary?.porInstitucion?.length && !options.length) setOptions(summary.porInstitucion);
  }, [withInstitution, summary, options.length]);
  const institutions = institutionOptions ?? options;

  // La marca «analizado» cambia solo ese evento de la página ya cargada; no vuelve a pedir el listado.
  function setItemRevision(idAuditoria, revision) {
    setPage((current) => current && { ...current, items: current.items.map((item) => (item.idAuditoria === idAuditoria ? { ...item, revision } : item)) });
  }

  function update(field) {
    return (event) => {
      setFilters((current) => ({ ...current, [field]: event.target.value }));
      setPagina(1);
    };
  }

  const totalPages = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;
  const filtered = JSON.stringify(filters) !== JSON.stringify(emptyFilters);
  // Chips del estado crítico: la cantidad sale del resumen con los mismos filtros (sin cantidad si el resumen no está disponible).
  const stateChips = [
    { value: 'CRITICA_SIN_ANALIZAR', label: 'Sin analizar', tone: 'danger', count: summaryFailed ? '—' : summary?.criticasSinAnalizar },
    { value: 'CRITICA_ANALIZADA', label: 'Analizados', tone: 'success', count: summaryFailed ? '—' : summary?.criticasAnalizadas },
    { value: 'TODAS_CRITICAS', label: 'Todos', tone: 'neutral', count: summaryFailed ? '—' : summary?.criticas },
  ];
  const showOrigin = !global || Boolean(fixedParams?.idInstitucion) || Boolean(fixedParams?.idCuenta);

  return (
    <div className={embedded ? 'audit' : 'page audit'}>
      {title && <PageHeader as={embedded || headingLevel === 2 ? 'h2' : 'h1'} title={title} description={lead} />}
      {error && <Alert>{error}</Alert>}

      {showSummary && (
        <section className="panel" aria-labelledby="auditoria-resumen">
          <div className="panel-title">
            <span className="panel-icon is-lg"><ShieldAlert size={26} aria-hidden="true" /></span>
            <div><h2 id="auditoria-resumen">Resumen de actividad</h2><p>Según los filtros elegidos. Fechas en tu hora local.</p></div>
          </div>
          <Summary summary={summary} failed={summaryFailed} global={withInstitution} />
        </section>
      )}

      <section className="panel" aria-labelledby="auditoria-eventos">
        <div className="panel-head">
          <h2 id="auditoria-eventos">Eventos</h2>
          {page && page.total > 0 && <span className="audit-count">{page.total.toLocaleString('es-AR')} {page.total === 1 ? 'evento' : 'eventos'}</span>}
        </div>
        <form className="audit-filter-card" aria-label="Filtros de auditoría" onSubmit={(event) => event.preventDefault()}>
          <div className="audit-filter-head">
            <span className="audit-filter-title"><Filter size={18} aria-hidden="true" /> Filtros de búsqueda</span>
            <div className="audit-state-chips" role="group" aria-label="Estado de las operaciones críticas">
              <span className="audit-state-label">Estado (críticos)</span>
              {stateChips.map(({ value, label, tone, count }) => (
                <button key={value} type="button" className={`audit-state-chip is-${tone}${filters.estadoCritico === value ? ' is-active' : ''}`}
                  aria-pressed={filters.estadoCritico === value}
                  onClick={() => { setFilters((current) => ({ ...current, estadoCritico: current.estadoCritico === value ? '' : value })); setPagina(1); }}>
                  {label}{count !== undefined && count !== null && <b>{count}</b>}
                </button>
              ))}
            </div>
          </div>
          <div className="audit-filters">
            <TextField label="Desde" type="date" value={filters.desde} onChange={update('desde')} />
            <TextField label="Hasta" type="date" value={filters.hasta} onChange={update('hasta')} />
            <TextField label="Usuario" value={filters.usuario} maxLength={100} onChange={update('usuario')} placeholder="Nombre, apellido, correo o usuario" />
            <SelectField label="Uso" value={filters.uso} onChange={update('uso')}>
              <option value="">Todos</option>
              <option value="INSTITUCION">Institución</option>
              <option value="INDIVIDUAL">Individual</option>
              <option value="PLATAFORMA">Plataforma</option>
              <option value="SIN_CUENTA">— (sin cuenta)</option>
            </SelectField>
            <SelectField label="Tipo de evento" value={filters.categoria} onChange={update('categoria')}>
              <option value="">Todos</option>
              {Object.entries(AUDIT_CATEGORIES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </SelectField>
            <SelectField label="Módulo" value={filters.modulo} onChange={update('modulo')}>
              <option value="">Todos</option>
              {Object.entries(AUDIT_MODULES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </SelectField>
            <SelectField label="Resultado" value={filters.resultado} onChange={update('resultado')}>
              <option value="">Todos</option><option value="EXITO">Exitosos</option><option value="FALLO">Fallidos</option>
            </SelectField>
            <TextField label="Acción" value={filters.accion} maxLength={50} onChange={update('accion')} placeholder="Ej.: matriz, transferencia" />
            <SelectField label="Clasificación" value={filters.clasificacion} onChange={update('clasificacion')}>
              <option value="">Todas</option>
              {Object.entries(AUDIT_CLASSIFICATIONS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </SelectField>
            {admin && <TextField label="IP de origen" value={filters.ip} maxLength={45} onChange={update('ip')} placeholder="Ej.: 203.0.113.7 o 203.0.113.*" />}
          </div>
          {filtered && (
            <div className="audit-filter-actions">
              <button type="button" className="btn btn-ghost" onClick={() => { setFilters(emptyFilters); setPagina(1); }}>
                <Filter size={16} aria-hidden="true" /> Limpiar filtros
              </button>
            </div>
          )}
        </form>
        {(filters.idCuenta || filters.refIdentificador) && (
          <p className="audit-chip" role="status">
            {filters.idCuenta ? 'Solo los eventos de la cuenta elegida' : `Solo los intentos sobre un identificador inexistente (ref. ${filters.refIdentificador.slice(0, 8)})`}
            <button type="button" className="btn btn-ghost" onClick={() => { setFilters((current) => ({ ...current, idCuenta: '', refIdentificador: '' })); setPagina(1); }}>Quitar</button>
          </p>
        )}
        {page === null ? (
          <p className="field-hint" role="status">Cargando eventos…</p>
        ) : page.items.length === 0 ? (
          <EmptyState icon={ShieldAlert} title={filtered ? 'No hay eventos que coincidan con los filtros.' : 'Todavía no hay eventos registrados.'}
            description={filtered ? 'Probá con otro período o limpiá los filtros.' : undefined} />
        ) : (
          <>
            <div className="table-scroll">
              <table className="data-table audit-table" aria-label="Eventos de auditoría">
                <thead>
                  <tr>
                    <th scope="col">Fecha</th><th scope="col">Usuario</th><th scope="col">Uso</th><th scope="col">Tipo de evento</th>
                    <th scope="col">Módulo</th><th scope="col">Resultado</th><th scope="col"><span className="sr-only">Operaciones</span></th>
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((item) => {
                    const result = resultInfo(item);
                    const severity = severityInfo(item);
                    const kind = item.clasificacion;
                    return (
                      <tr key={item.idAuditoria} className={`audit-row is-${severity.key.toLowerCase()}`}>
                        <td data-label="Fecha" className="audit-date">{formatInstant(item.fechaHora)}</td>
                        <td data-label="Usuario"><UserCell item={item} admin={admin} /></td>
                        <td data-label="Uso"><UseBadge uso={item.usoCuenta} /></td>
                        <td data-label="Tipo de evento" className="audit-action">
                          <span className="audit-cell">
                            <span className="audit-event">{eventName(item)}{item.critica && <> <Badge tone="warning" size="sm">Crítica</Badge></>}</span>
                            {item.entidadEtiqueta && <small className="audit-note">Sobre: {item.entidadEtiqueta}</small>}
                            {item.motivoEtiqueta && <small className="audit-note">{item.motivoEtiqueta}</small>}
                          </span>
                        </td>
                        <td data-label="Módulo"><Badge>{AUDIT_MODULES[item.modulo] ?? item.modulo}</Badge></td>
                        <td data-label="Resultado">
                          <span className="audit-result">
                            <Badge tone={severity.tone}>{result.label}</Badge>
                            {item.critica && (
                              <Badge tone={item.revision?.revisado ? 'success' : 'danger'} size="sm" icon={AlertTriangle}>
                                {item.revision ? (item.revision.revisado ? 'Analizado' : 'Sin analizar') : 'Pendiente'}
                              </Badge>
                            )}
                            {(kind === 'SOSPECHOSO' || kind === 'CONFIRMADO') && (
                              <Badge tone={kind === 'SOSPECHOSO' ? 'warning' : 'danger'} size="sm" title={CLASSIFICATION_HELP[kind]}>{AUDIT_CLASSIFICATIONS[kind]}</Badge>
                            )}
                          </span>
                        </td>
                        <td className="audit-actions">
                          {item.revision && (
                            <AuditReviewToggle idAuditoria={item.idAuditoria} revision={item.revision}
                              name={`${eventName(item)}, ${formatInstant(item.fechaHora)}`}
                              onChange={(revision) => setItemRevision(item.idAuditoria, revision)} />
                          )}
                          <Link to={item.idAuditoria} state={{ search: location.search }} className="btn btn-outline btn-sm"
                            aria-label={`Ver detalle: ${eventName(item)}, ${formatInstant(item.fechaHora)}`}>Ver detalle</Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {showOrigin && page.items.some((item) => item.origenActor === 'PLATAFORMA') && (
              <p className="field-hint">«Administración» marca lo realizado por la administración de GlucoLume; el resto lo hizo el personal o la cuenta.</p>
            )}
            {page.total > PAGE_SIZE && (
              <nav className="pagination" aria-label="Páginas de auditoría">
                <button type="button" className="btn btn-ghost" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>
                  <ChevronLeft size={16} aria-hidden="true" /> Anterior
                </button>
                <span>Página {page.pagina} de {totalPages} · {page.total} eventos</span>
                <button type="button" className="btn btn-ghost" disabled={pagina >= totalPages} onClick={() => setPagina((p) => p + 1)}>
                  Siguiente <ChevronRight size={16} aria-hidden="true" />
                </button>
              </nav>
            )}
          </>
        )}
      </section>
    </div>
  );
}
