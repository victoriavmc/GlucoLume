// Personal de la institución: vista general (Todos) y filtrada por rol (Moderadores, Operadores). Una fila por persona, con su rol y
// estado actuales; los filtros (rol, estado, búsqueda) y los indicadores salen del backend (/personnel), no de la página visible.
// Desde acá se agregan moderadores y operadores (según el permiso del rol) y se abre el perfil individual, donde se administra.
// Los filtros y la página viven en la URL: al volver desde un perfil se recupera el mismo listado.

import {
  ChevronLeft, ChevronRight, Filter, MailPlus, Search, UserCheck, UserMinus, UserPlus, Users, UsersRound,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useLocation, useOutletContext, useSearchParams } from 'react-router-dom';

import * as institutionsApi from '../../../api/institutionsApi.js';
import { Badge, toneFromClass } from '../../../components/Badge.jsx';
import { EmptyState } from '../../../components/EmptyState.jsx';
import { Alert, SelectField, TextField } from '../../../components/FormControls.jsx';
import { Kpi, KpiGrid } from '../../../components/dashboard.jsx';
import { AddMemberForm, CONFIG } from './PersonnelForms.jsx';
import { QuotaLine } from './QuotaSection.jsx';
import { ROLE_LABELS, can, personName } from './institutionFormat.js';
import { RELATION_STATES, stateInfo, when } from './personnelFormat.js';
import './Personnel.css';

const PAGE_SIZE = 15;
const TITLES = { undefined: 'Personal', MODERADOR: 'Moderadores', OPERADOR: 'Operadores' };

function PersonCell({ person }) {
  return (
    <span className="person-cell">
      <b>{person.nombreCompleto}</b>
      {person.correoElectronico && <small>{person.correoElectronico}</small>}
    </span>
  );
}

export function PersonnelPage({ rol }) {
  const { institution, reload, handleOperationError } = useOutletContext();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [role, setRole] = useState(searchParams.get('rol') ?? '');
  const [state, setState] = useState(searchParams.get('estado') ?? '');
  const [query, setQuery] = useState(searchParams.get('busqueda') ?? '');
  const [pagina, setPagina] = useState(Number(searchParams.get('pagina')) || 1);
  const [page, setPage] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [adding, setAdding] = useState(null); // 'MODERADOR' | 'OPERADOR' | null
  const [version, setVersion] = useState(0);
  const effectiveRole = rol ?? role; // en las pestañas Moderadores y Operadores el rol lo fija la pestaña

  const filtersActive = Boolean(state || query || (!rol && role));
  const params = { ...(effectiveRole ? { rol: effectiveRole } : {}), ...(state ? { estado: state } : {}), ...(query.trim() ? { busqueda: query.trim() } : {}) };

  // Los filtros del listado quedan en la URL (sin el rol de la pestaña, que ya está en la ruta).
  useEffect(() => {
    const shown = { ...(!rol && role ? { rol: role } : {}), ...(state ? { estado: state } : {}), ...(query.trim() ? { busqueda: query.trim() } : {}), ...(pagina > 1 ? { pagina } : {}) };
    setSearchParams(shown, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role, state, query, pagina, rol]);

  useEffect(() => {
    let active = true;
    setPage(null);
    const timer = setTimeout(() => {
      institutionsApi.listPersonnel(institution.idInstitucion, { ...params, pagina, tamanioPagina: PAGE_SIZE }).then(
        (result) => active && (setPage(result), setError('')),
        (loadError) => active && (setError(handleOperationError(loadError)), setPage({ items: [], total: 0, pagina: 1, tamanioPagina: PAGE_SIZE, resumen: null })),
      );
    }, query ? 250 : 0); // la búsqueda espera un instante para no consultar en cada tecla
    return () => { active = false; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [institution.idInstitucion, effectiveRole, state, query, pagina, version]);

  const canAddModerator = can(institution, 'GESTIONAR_MODERADORES');
  const canAddOperator = can(institution, 'INCORPORAR_OPERADORES');
  const adders = [
    ['MODERADOR', canAddModerator], ['OPERADOR', canAddOperator],
  ].filter(([key, allowed]) => allowed && (!rol || rol === key));
  const summary = page?.resumen;
  const totalPages = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;
  const config = CONFIG[rol] ?? null;

  function update(setter) {
    return (event) => {
      setter(event.target.value);
      setPagina(1);
    };
  }

  function clear() {
    setRole('');
    setState('');
    setQuery('');
    setPagina(1);
  }

  async function handleAdded(added) {
    setAdding(null);
    setNotice(added.cuentaPendiente
      ? `Creamos la cuenta de ${personName(added)} y le enviamos el enlace de activación. Va a figurar activo cuando la active y acepte.`
      : `Invitación enviada a ${personName(added)}. Va a figurar activo cuando la acepte.`);
    setVersion((current) => current + 1);
    await reload();
  }

  return (
    <div className="personnel">
      <section className="panel" aria-labelledby="personal-resumen">
        <div className="panel-head">
          <div className="panel-title">
            <span className="panel-icon is-lg" aria-hidden="true"><Users size={26} /></span>
            <div>
              <h2 id="personal-resumen">{TITLES[rol]}</h2>
              <p>{config?.description ?? 'Quiénes trabajan en la institución, con su rol, su información laboral y su estado.'}</p>
            </div>
          </div>
          {!adding && adders.length > 0 && (
            <div className="personnel-add">
              {adders.map(([key], index) => (
                <button key={key} type="button" className={`btn ${index === 0 ? 'btn-primary' : 'btn-outline'}`}
                  onClick={() => { setNotice(''); setAdding(key); }}>
                  <UserPlus size={18} aria-hidden="true" /> {CONFIG[key].addLabel}
                </button>
              ))}
            </div>
          )}
        </div>
        {summary ? (
          <KpiGrid label="Indicadores del personal" compact>
            <Kpi icon={UsersRound} label="Integrantes activos" value={summary.totalActivos} />
            <Kpi icon={UserCheck} tone="warn" label="Moderadores activos" value={summary.moderadoresActivos} />
            <Kpi icon={Users} tone="ok" label="Operadores activos" value={summary.operadoresActivos} />
            <Kpi icon={UserMinus} tone="muted" label="Personal dado de baja" value={summary.bajas} />
            <Kpi icon={MailPlus} tone="blue" label="Invitaciones pendientes" value={summary.invitacionesPendientes} />
          </KpiGrid>
        ) : page === null ? <p className="field-hint" role="status">Cargando indicadores…</p> : null}
        {!rol && <QuotaLine institution={institution} refreshKey={`${version}-${summary?.totalActivos ?? ''}-${summary?.invitacionesPendientes ?? ''}`} />}
      </section>

      {notice && <Alert kind="success">{notice}</Alert>}
      {error && <Alert>{error}</Alert>}
      {!canAddOperator && rol === 'OPERADOR' && (
        <Alert kind="info">Los operadores los incorpora un moderador de la institución. Desde acá podés consultarlos y administrarlos.</Alert>
      )}
      {adding && (
        <AddMemberForm institution={institution} rol={adding} config={CONFIG[adding]} onAdded={handleAdded}
          onCancel={() => setAdding(null)} handleOperationError={handleOperationError} />
      )}

      <section className="panel" aria-labelledby="personal-listado">
        <div className="panel-head">
          <h2 id="personal-listado">{rol ? TITLES[rol] : 'Todo el personal'}</h2>
          {page && page.total > 0 && <span className="audit-count">{page.total.toLocaleString('es-AR')} {page.total === 1 ? 'persona' : 'personas'}</span>}
        </div>
        <form className="personnel-filters" aria-label="Filtros del personal" onSubmit={(event) => event.preventDefault()}>
          <div className="personnel-search">
            <TextField label="Buscar" icon={Search} value={query} maxLength={100} onChange={update(setQuery)}
              placeholder="Nombre, apellido, correo, legajo o matrícula" />
          </div>
          {!rol && (
            <SelectField label="Rol" value={role} onChange={update(setRole)}>
              <option value="">Todos</option>
              <option value="PROPIETARIO">{ROLE_LABELS.PROPIETARIO}</option>
              <option value="MODERADOR">Moderadores</option>
              <option value="OPERADOR">Operadores</option>
            </SelectField>
          )}
          <SelectField label="Estado" value={state} onChange={update(setState)}>
            <option value="">Todos los estados</option>
            {Object.entries(RELATION_STATES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </SelectField>
          {filtersActive && (
            <button type="button" className="btn btn-ghost" onClick={clear}>
              <Filter size={16} aria-hidden="true" /> Limpiar filtros
            </button>
          )}
        </form>

        {page === null ? (
          <p className="field-hint" role="status">Cargando personal…</p>
        ) : page.items.length === 0 ? (
          <EmptyState icon={Users} headingLevel={0}
            title={filtersActive ? 'No hay personal que coincida con los filtros.' : (config?.empty ?? 'Todavía no hay personal en esta institución.')}
            description={filtersActive ? 'Probá con otra búsqueda o limpiá los filtros.' : undefined} />
        ) : (
          <>
            <div className="table-scroll">
              <table className="data-table personnel-table" aria-label="Personal de la institución">
                <thead>
                  <tr>
                    <th scope="col">Persona</th><th scope="col">Rol</th><th scope="col">Legajo</th><th scope="col">Matrícula</th>
                    <th scope="col">Fecha de incorporación</th><th scope="col">Fecha de baja</th><th scope="col">Estado</th><th scope="col"><span className="sr-only">Acciones</span></th>
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((person) => {
                    const info = stateInfo(person);
                    return (
                      <tr key={person.idInstitucionUsuario}>
                        <th scope="row" data-label="Persona"><PersonCell person={person} /></th>
                        <td data-label="Rol">
                          <Badge tone="brand">{ROLE_LABELS[person.rolInstitucion]}</Badge>
                          {person.rolesAnteriores.length > 0 && (
                            <small className="person-before">Antes: {person.rolesAnteriores.map((r) => ROLE_LABELS[r]).join(', ')}</small>
                          )}
                        </td>
                        <td data-label="Legajo" className={person.legajoInstitucional ? undefined : 'is-empty'}>{person.legajoInstitucional ?? 'Sin informar'}</td>
                        <td data-label="Matrícula" className={person.matriculaProfesional ? undefined : 'is-empty'}>{person.matriculaProfesional ?? 'Sin informar'}</td>
                        <td data-label="Fecha de incorporación" className={person.fechaIncorporacion ? undefined : 'is-empty'}>
                          {person.fechaIncorporacion ? when(person.fechaIncorporacion) : 'Todavía no ocurrió'}
                        </td>
                        <td data-label="Fecha de baja" className={person.estadoRelacion === 'BAJA' && person.fechaBaja ? undefined : 'is-empty'}>
                          {person.estadoRelacion === 'BAJA' && person.fechaBaja ? when(person.fechaBaja) : 'Sin baja'}
                        </td>
                        <td data-label="Estado"><Badge tone={toneFromClass(info.tone)}>{info.label}</Badge></td>
                        <td className="audit-actions">
                          <Link to={`/app/instituciones/${institution.idInstitucion}/personal/perfil/${person.idInstitucionUsuario}`}
                            state={{ from: location.pathname, search: location.search }} className="btn btn-ghost"
                            aria-label={`Ver perfil de ${person.nombreCompleto}`}>Ver perfil</Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {page.total > PAGE_SIZE && (
              <nav className="pagination" aria-label="Páginas del personal">
                <button type="button" className="btn btn-ghost" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>
                  <ChevronLeft size={16} aria-hidden="true" /> Anterior
                </button>
                <span>Página {page.pagina} de {totalPages} · {page.total} personas</span>
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
