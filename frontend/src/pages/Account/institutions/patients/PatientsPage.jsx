// Pacientes de la institución: listado paginado con búsqueda y filtros (todos / míos, operador responsable y estado). Todo el personal
// ve la identificación administrativa; las mediciones solo las ve el operador responsable (el backend lo decide en cada consulta: acá
// solo se distingue «registrado en la institución» de «a mi cargo» y se ofrece «Medir» en los propios).

import { ChevronLeft, ChevronRight, Download, Plus, Search, Users } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useOutletContext, useSearchParams } from 'react-router-dom';

import * as institutionsApi from '../../../../api/institutionsApi.js';
import { Badge } from '../../../../components/Badge.jsx';
import { EmptyState } from '../../../../components/EmptyState.jsx';
import { Alert, SelectField, TextField } from '../../../../components/FormControls.jsx';
import { SkeletonList } from '../../../../components/Skeleton.jsx';
import { saveBlob } from '../../../../utils/downloadFile.js';
import { useLatestRequest } from '../../../../utils/useLatestRequest.js';
import { can, formatDateTime } from '../institutionFormat.js';
import '../exportControls.css';

const PAGE_SIZE = 20;

// Plazos del filtro «Datos que vencen»: los que pierden sus datos dentro de ese número de días (y los ya vencidos).
const DUE_WITHIN_OPTIONS = [{ value: '7', label: 'Dentro de 7 días' }, { value: '30', label: 'Dentro de 30 días' }, { value: '90', label: 'Dentro de 90 días' }];

export function patientName(patient) {
  return [patient.apellido, patient.nombre].filter(Boolean).join(', ') || patient.identificadorPseudonimo;
}

/** Insignia de un paciente dado de baja: cuántos días le quedan a sus datos (propietario y moderador) o solo la fecha, para el resto. */
function dischargeBadge(patient, showDays) {
  const date = formatDateTime(patient.fechaExpiracionDatosPersonales).split(' ')[0];
  if (!showDays || patient.diasRestantesDatos === null) return <Badge tone="neutral">De baja · datos conservados hasta {date}</Badge>;
  const dias = patient.diasRestantesDatos;
  if (dias < 0) return <Badge tone="danger">De baja · venció el {date}, pendiente de depuración</Badge>;
  if (dias === 0) return <Badge tone="danger">De baja · vence hoy ({date})</Badge>;
  const tone = dias <= 7 ? 'danger' : dias <= 30 ? 'warning' : 'neutral';
  return <Badge tone={tone}>De baja · le quedan {dias} {dias === 1 ? 'día' : 'días'} de conservación (hasta {date})</Badge>;
}

/** Al entrar a un paciente: quien puede ver su salud (operador responsable, paciente activo) abre su dashboard; el resto, la ficha administrativa. */
const entryTo = (patient) => (patient.medicionesAutorizadas && patient.estado === 'ACTIVO' ? `${patient.idPerfilMedicion}/dashboard` : patient.idPerfilMedicion);

export function PatientsPage() {
  const { institution, handleOperationError } = useOutletContext();
  const isOperator = institution.rolInstitucion === 'OPERADOR';
  const canManage = can(institution, 'GESTIONAR_PACIENTES');
  const canSeeRetention = can(institution, 'BAJA_PACIENTES'); // propietario y moderador: plazos de conservación
  const [searchParams] = useSearchParams();
  const choosingToMeasure = isOperator && searchParams.get('medir') === '1'; // viene de «Nueva medición»
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState({ busqueda: '', estado: 'ACTIVO', idResponsable: '', soloMios: searchParams.get('mios') === '1', venceEnDias: '', pagina: 1 });
  const [page, setPage] = useState(null);
  const [operators, setOperators] = useState([]);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(() => new Set()); // pacientes marcados para exportar (solo de la página visible)
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');
  const [exportNotice, setExportNotice] = useState('');

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

  // Una selección no sobrevive a un cambio de filtros o de página.
  useEffect(() => {
    setSelected(new Set());
  }, [filters]);

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

  // Exportar: propietario y moderador exportan a todos los pacientes; el operador, solo a los que tiene a su cargo. La API lo valida
  // en cada pedido: acá solo se ofrecen las opciones que corresponden.
  // Un paciente anonimizado ya no tiene datos personales que exportar (el backend lo rechaza en una selección).
  const canExportPatient = (patient) => !patient.anonimizado && (!isOperator || patient.esMio);

  function toggle(id) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleExport(body) {
    setExporting(true);
    setExportError('');
    setExportNotice('');
    try {
      const { blob, filename } = await institutionsApi.exportPatients(institution.idInstitucion, body);
      saveBlob(blob, filename);
      setExportNotice(`Exportación lista: ${filename}.`);
    } catch (failure) {
      setExportError(handleOperationError(failure));
    } finally {
      setExporting(false);
    }
  }

  // «Todos» exporta con los mismos filtros del listado (búsqueda, estado, operador responsable y plazo).
  const exportAllBody = {
    alcance: 'TODOS',
    busqueda: filters.busqueda || null,
    estado: filters.estado,
    idResponsable: filters.idResponsable || null,
    ...(filters.venceEnDias ? { venceEnDias: Number(filters.venceEnDias) } : {}),
  };

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
      {exportError && <Alert>{exportError}</Alert>}
      {choosingToMeasure && <Alert kind="info">Elegí el paciente al que vas a medir y tocá «Medir».</Alert>}
      <p className="field-hint">
        Las mediciones de cada paciente están disponibles únicamente para su operador responsable autorizado; el resto del personal ve su
        información administrativa.
      </p>

      <form className="patient-filters" onSubmit={applySearch} role="search" noValidate>
        <TextField label="Buscar por nombre, apellido o documento" icon={Search} maxLength={100} value={search}
          onChange={(event) => setSearch(event.target.value)} />
        <SelectField label="Estado" value={filters.estado}
          onChange={(event) => setFilters((current) => ({ ...current, estado: event.target.value, venceEnDias: '', pagina: 1 }))}
          options={[
            { value: 'ACTIVO', label: 'Activos' },
            { value: 'BAJA', label: 'Dados de baja' },
            { value: 'ANONIMIZADO', label: 'Anonimizados' },
            { value: 'TODOS', label: 'Todos, sin importar su estado' },
          ]} />
        {canSeeRetention && filters.estado === 'BAJA' && (
          <SelectField label="Datos que vencen" value={filters.venceEnDias} onChange={(event) => setFilter('venceEnDias', event.target.value)}>
            <option value="">Cualquier plazo</option>
            {DUE_WITHIN_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </SelectField>
        )}
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
          title={filters.busqueda || filters.idResponsable || filters.venceEnDias
            ? 'No hay pacientes que coincidan con la búsqueda.'
            : filters.estado === 'BAJA' ? 'No hay pacientes dados de baja.'
              : filters.estado === 'ANONIMIZADO' ? 'No hay pacientes anonimizados.'
                : filters.soloMios ? 'Todavía no tenés pacientes asignados. Podés agregar uno nuevo con «Agregar paciente».' : 'Todavía no hay pacientes registrados.'} />
      ) : (
        <>
          <div className="export-toolbar">
            <button type="button" className="btn btn-outline" disabled={selected.size === 0 || exporting}
              onClick={() => handleExport({ alcance: 'SELECCION', idsPerfilMedicion: [...selected] })}>
              <Download size={18} aria-hidden="true" /> Exportar seleccionados{selected.size > 0 ? ` (${selected.size})` : ''}
            </button>
            <button type="button" className="btn btn-outline" disabled={exporting} onClick={() => handleExport(exportAllBody)}>
              <Download size={18} aria-hidden="true" />{' '}
              {isOperator ? 'Exportar mis pacientes' : `Exportar todos${filters.busqueda || filters.idResponsable || filters.venceEnDias || filters.estado !== 'ACTIVO' ? ' los filtrados' : ''} (${page.total})`}
            </button>
            {exportNotice && <p className="field-hint" role="status">{exportNotice}</p>}
          </div>
          <ul className="member-list-items" aria-label="Listado de pacientes">
            {page.items.map((patient) => (
              <li key={patient.idPerfilMedicion} className="member-row">
                {canExportPatient(patient) && (
                  <input type="checkbox" className="export-check" checked={selected.has(patient.idPerfilMedicion)}
                    onChange={() => toggle(patient.idPerfilMedicion)} aria-label={`Seleccionar a ${patientName(patient)}`} />
                )}
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
                  {patient.anonimizado && <Badge tone="neutral">Datos anonimizados · sin identidad</Badge>}
                  {!patient.anonimizado && patient.estado === 'BAJA' && dischargeBadge(patient, canSeeRetention)}
                </span>
                <span className="member-actions">
                  {patient.medicionesAutorizadas && patient.estado === 'ACTIVO' && (
                    <Link to={`${patient.idPerfilMedicion}/medir`} className="btn btn-outline" aria-label={`Medir a ${patientName(patient)}`}>Medir</Link>
                  )}
                  {canExportPatient(patient) && (
                    <button type="button" className="btn btn-ghost" disabled={exporting}
                      onClick={() => handleExport({ alcance: 'SELECCION', idsPerfilMedicion: [patient.idPerfilMedicion] })}
                      aria-label={`Exportar los datos de ${patientName(patient)}`}>
                      <Download size={16} aria-hidden="true" /> Exportar
                    </button>
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
