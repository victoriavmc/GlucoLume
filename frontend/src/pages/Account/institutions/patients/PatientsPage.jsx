// Pacientes de la institución: listado paginado con búsqueda y filtros (todos / míos, operador responsable y estado). Todo el personal
// ve la identificación administrativa; las mediciones solo las ve el operador responsable (el backend lo decide en cada consulta: acá
// solo se distingue «registrado en la institución» de «a mi cargo» y se ofrece «Medir» en los propios).

import { ChevronLeft, ChevronRight, Plus, Search, Users } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useOutletContext, useSearchParams } from 'react-router-dom';

import * as institutionsApi from '../../../../api/institutionsApi.js';
import { Badge } from '../../../../components/Badge.jsx';
import { EmptyState } from '../../../../components/EmptyState.jsx';
import { Alert, SelectField, TextField } from '../../../../components/FormControls.jsx';
import { SkeletonList } from '../../../../components/Skeleton.jsx';
import { useLatestRequest } from '../../../../utils/useLatestRequest.js';
import { can, formatDateTime } from '../institutionFormat.js';

const PAGE_SIZE = 20;

export function patientName(patient) {
  return [patient.apellido, patient.nombre].filter(Boolean).join(', ') || patient.identificadorPseudonimo;
}

/** Al entrar a un paciente: quien puede ver su salud (operador responsable, paciente activo) abre su dashboard; el resto, la ficha administrativa. */
const entryTo = (patient) => (patient.medicionesAutorizadas && patient.estado === 'ACTIVO' ? `${patient.idPerfilMedicion}/dashboard` : patient.idPerfilMedicion);

export function PatientsPage() {
  const { institution, handleOperationError } = useOutletContext();
  const isOperator = institution.rolInstitucion === 'OPERADOR';
  const canManage = can(institution, 'GESTIONAR_PACIENTES');
  const [searchParams] = useSearchParams();
  const choosingToMeasure = isOperator && searchParams.get('medir') === '1'; // viene de «Nueva medición»
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState({ busqueda: '', estado: 'ACTIVO', idResponsable: '', soloMios: searchParams.get('mios') === '1', pagina: 1 });
  const [page, setPage] = useState(null);
  const [operators, setOperators] = useState([]);
  const [error, setError] = useState('');

  const beginRequest = useLatestRequest(); // una respuesta lenta de un filtro anterior no pisa a la del filtro actual

  const load = useCallback(async () => {
    const isCurrent = beginRequest();
    setError('');
    try {
      const result = await institutionsApi.listPatients(institution.idInstitucion, { ...filters, tamanioPagina: PAGE_SIZE });
      if (isCurrent()) setPage(result);
    } catch (loadError) {
      if (!isCurrent()) return;
      setError(handleOperationError(loadError));
      setPage({ items: [], total: 0, pagina: 1, tamanioPagina: PAGE_SIZE });
    }
  }, [institution.idInstitucion, filters, handleOperationError, beginRequest]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    let active = true;
    institutionsApi.getAssignableOperators(institution.idInstitucion).then(
      (list) => { if (active) setOperators(list); },
      () => { if (active) setOperators([]); },
    );
    return () => { active = false; };
  }, [institution.idInstitucion]);

  function applySearch(event) {
    event.preventDefault();
    setFilters((current) => ({ ...current, busqueda: search.trim(), pagina: 1 }));
  }

  function setFilter(field, value) {
    setFilters((current) => ({ ...current, [field]: value, pagina: 1 }));
  }

  const totalPages = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;

  return (
    <section className="panel" aria-labelledby="pacientes">
      <div className="panel-head">
        <div className="panel-title">
          <span className="panel-icon">
            <Users size={22} aria-hidden="true" />
          </span>
          <div>
            <h2 id="pacientes">Pacientes</h2>
            <p>{isOperator
              ? 'Los pacientes registrados en la institución. Registrás y consultás las mediciones solo de los que tenés a tu cargo.'
              : 'Personas que la institución registra para sus mediciones. No son cuentas de GlucoLume.'}</p>
          </div>
        </div>
        {canManage && (
          <Link to="nuevo" className="btn btn-primary">
            <Plus size={18} aria-hidden="true" /> Agregar paciente
          </Link>
        )}
      </div>

      {error && <Alert>{error}</Alert>}
      {choosingToMeasure && <Alert kind="info">Elegí el paciente al que vas a medir y tocá «Medir».</Alert>}
      <p className="field-hint">
        Las mediciones de cada paciente están disponibles únicamente para su operador responsable autorizado; el resto del personal ve su
        información administrativa.
      </p>

      <form className="patient-filters" onSubmit={applySearch} role="search" noValidate>
        <TextField label="Buscar por nombre, apellido o documento" icon={Search} maxLength={100} value={search}
          onChange={(event) => setSearch(event.target.value)} />
        <SelectField label="Estado" value={filters.estado} onChange={(event) => setFilter('estado', event.target.value)}
          options={[{ value: 'ACTIVO', label: 'Activos' }, { value: 'BAJA', label: 'Dados de baja' }]} />
        {isOperator && (
          <SelectField label="Ver" value={filters.soloMios ? 'mios' : 'todos'} onChange={(event) => setFilter('soloMios', event.target.value === 'mios')}
            options={[{ value: 'todos', label: 'Todos los pacientes' }, { value: 'mios', label: 'Mis pacientes' }]} />
        )}
        {operators.length > 0 && !filters.soloMios && (
          <SelectField label="Operador responsable" value={filters.idResponsable} onChange={(event) => setFilter('idResponsable', event.target.value)}>
            <option value="">Todos los operadores</option>
            {operators.map((operator) => (
              <option key={operator.idInstitucionUsuario} value={operator.idInstitucionUsuario}>
                {[operator.nombre, operator.apellido].filter(Boolean).join(' ')}
              </option>
            ))}
          </SelectField>
        )}
        <button type="submit" className="btn btn-outline">
          <Search size={16} aria-hidden="true" /> Buscar
        </button>
      </form>

      {page === null ? (
        <SkeletonList rows={6} label="Cargando pacientes…" />
      ) : page.items.length === 0 ? (
        <EmptyState icon={Users} headingLevel={0}
          title={filters.busqueda || filters.idResponsable
            ? 'No hay pacientes que coincidan con la búsqueda.'
            : filters.estado === 'BAJA' ? 'No hay pacientes dados de baja.'
              : filters.soloMios ? 'Todavía no tenés pacientes asignados. Podés agregar uno nuevo con «Agregar paciente».' : 'Todavía no hay pacientes registrados.'} />
      ) : (
        <>
          <ul className="member-list-items" aria-label="Listado de pacientes">
            {page.items.map((patient) => (
              <li key={patient.idPerfilMedicion} className="member-row">
                <span>
                  <Link to={entryTo(patient)} className="patient-link">
                    <b>{patientName(patient)}</b>
                  </Link>
                  <small>
                    {' '}
                    {patient.dni ? `· DNI ${patient.dni} ` : ''}{patient.edad !== null ? `· ${patient.edad} años ` : ''}· {patient.identificadorPseudonimo}
                  </small>
                  <br />
                  <Badge tone={patient.esMio ? 'success' : 'neutral'}>{patient.esMio ? 'Paciente asignado a mi cargo' : 'Paciente registrado en la institución'}</Badge>{' '}
                  <Badge tone={patient.responsable.activo ? 'success' : 'neutral'}>
                    Operador responsable: {[patient.responsable.nombre, patient.responsable.apellido].filter(Boolean).join(' ')}
                    {!patient.responsable.activo && ' (desvinculado)'}
                  </Badge>
                  {patient.registradoPor && (
                    <small className="field-hint"> Registrado por {[patient.registradoPor.nombre, patient.registradoPor.apellido].filter(Boolean).join(' ') || 'un usuario'}</small>
                  )}
                  {patient.estado === 'BAJA' && (
                    <Badge tone="neutral">
                      De baja · datos conservados hasta {formatDateTime(patient.fechaExpiracionDatosPersonales).split(' ')[0]}
                    </Badge>
                  )}
                </span>
                <span className="member-actions">
                  {patient.medicionesAutorizadas && patient.estado === 'ACTIVO' && (
                    <Link to={`${patient.idPerfilMedicion}/medir`} className="btn btn-outline" aria-label={`Medir a ${patientName(patient)}`}>Medir</Link>
                  )}
                  <Link to={entryTo(patient)} className="btn btn-ghost" aria-label={`Ver ${patientName(patient)}`}>
                    Ver detalle
                  </Link>
                </span>
              </li>
            ))}
          </ul>
          <nav className="pagination" aria-label="Páginas de pacientes">
            <button type="button" className="btn btn-ghost" disabled={filters.pagina <= 1}
              onClick={() => setFilters((current) => ({ ...current, pagina: current.pagina - 1 }))}>
              <ChevronLeft size={16} aria-hidden="true" /> Anterior
            </button>
            <span>
              Página {page.pagina} de {totalPages} · {page.total} paciente{page.total === 1 ? '' : 's'}
            </span>
            <button type="button" className="btn btn-ghost" disabled={filters.pagina >= totalPages}
              onClick={() => setFilters((current) => ({ ...current, pagina: current.pagina + 1 }))}>
              Siguiente <ChevronRight size={16} aria-hidden="true" />
            </button>
          </nav>
        </>
      )}
    </section>
  );
}
