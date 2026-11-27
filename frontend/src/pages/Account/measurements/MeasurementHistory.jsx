// Historial de mediciones con filtros (fecha, modo, orden), detalle, estadísticas y gráficos. Lo usan el
// perfil propio y cada paciente institucional: cambia solo de dónde salen los datos (`loadPage`/`loadEvolution`),
// que el backend autoriza en cada consulta. Los gráficos usan solo mediciones completadas.

import { Activity, ChevronLeft, ChevronRight, Download, Filter, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { Badge } from '../../../components/Badge.jsx';
import { EmptyState } from '../../../components/EmptyState.jsx';
import { Alert, SelectField, TextField } from '../../../components/FormControls.jsx';
import { Modal } from '../../../components/Modal.jsx';
import { SkeletonList } from '../../../components/Skeleton.jsx';
import { saveBlob } from '../../../utils/downloadFile.js';
import { EXPORT_FORMATS } from '../../../utils/exportFormats.js';
import { useLatestRequest } from '../../../utils/useLatestRequest.js';
import '../institutions/exportControls.css';
import './MeasurementHistory.css';
import { DemoBadge } from './DeviceReadout.jsx';
import { EvolutionPanel } from './EvolutionPanel.jsx';
import { MEALS, MODES, STATES, formatDateTime } from './measurementFormat.js';
import { Semaforo } from './Semaforo.jsx';

const PAGE_SIZE = 25;
const EMPTY_FILTERS = { desde: '', hasta: '', modo: '', condicion: '', orden: 'desc' };

function value(number, unit) {
  return number === null || number === undefined ? '—' : `${Number(number).toLocaleString('es-AR')} ${unit}`;
}

/** Glucosa a mostrar en la tabla: la estimada, o la del dispositivo si el firmware informó su origen. */
function glucoseOf(item) {
  if (item.glucosaEstimada !== null && item.glucosaEstimada !== undefined) return { value: item.glucosaEstimada };
  if (item.origenGlucosa && item.glucosaDispositivo !== null && item.glucosaDispositivo !== undefined) {
    return { value: item.glucosaDispositivo };
  }
  return null;
}

const NO_EVOLUTION = { puntos: [], truncado: false, desde: null, hasta: null, estadisticas: { experimental: null, demo: null }, resumen: null };

/** «Gráficos y estadísticas» del paciente: TODAS las mediciones completadas (experimentales y DEMO, de ambos modos), con los DEMO
 * identificados y calculados aparte. Reutiliza el panel de evolución; solo cambia de dónde salen los datos. */
function Evolution({ loadEvolution, pointPath, handleOperationError }) {
  const [period, setPeriod] = useState({ dias: 30 });
  const [mode, setMode] = useState('');
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setData(null);
    loadEvolution({ ...period, modo: mode || undefined, origen: 'TODOS' }).then(
      (result) => active && (setData(result), setError('')),
      (loadError) => active && (setError(handleOperationError(loadError)), setData(NO_EVOLUTION)),
    );
    return () => { active = false; };
  }, [period, mode, loadEvolution, handleOperationError]);

  return (
    <>
      {error && <Alert>{error}</Alert>}
      <EvolutionPanel data={data} period={period} onPeriodChange={setPeriod} mode={mode} onModeChange={setMode} pointPath={pointPath} compact
        title="Gráficos y estadísticas"
        description="Incluye todas las mediciones completadas del paciente. Los datos DEMO se muestran identificados y las estadísticas separan los valores DEMO y experimentales." />
    </>
  );
}

/** Filtros con valor, listos para la API de exportación (sin campos vacíos). */
function filledFilters(filters) {
  return Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== ''));
}

/** `filtroCondicion`: muestra el filtro por condición de comida (solo lo soporta el historial propio). */
export function MeasurementHistory({ loadPage, loadEvolution, detailPath, handleOperationError, emptyText, refreshKey, onDeleteDemo, onDeleteOne, onExport, filtroCondicion = false }) {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [confirmingDemo, setConfirmingDemo] = useState(false);
  const [confirmingSelected, setConfirmingSelected] = useState(false);
  const [deletingSelected, setDeletingSelected] = useState(false);
  const [notice, setNotice] = useState('');
  const [pagina, setPagina] = useState(1);
  const [page, setPage] = useState(null);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(() => new Set()); // mediciones marcadas para exportar (solo de la página visible)
  const [exportFormat, setExportFormat] = useState('csv');
  const [exporting, setExporting] = useState(false);

  const beginRequest = useLatestRequest(); // filtros, páginas, el refresco por vencimiento y «eliminar demos» comparten esta carga: gana la última

  const load = useCallback(async () => {
    const isCurrent = beginRequest();
    try {
      const result = await loadPage({ ...filters, pagina, tamanioPagina: PAGE_SIZE });
      if (!isCurrent()) return;
      setPage(result);
      setError('');
    } catch (loadError) {
      if (!isCurrent()) return;
      setError(handleOperationError(loadError));
      setPage({ items: [], total: 0, pagina: 1, tamanioPagina: PAGE_SIZE });
    }
  }, [loadPage, filters, pagina, handleOperationError, beginRequest]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  // Las canceladas/inválidas se ocultan solas a los 30 minutos: mientras haya alguna a la vista se vuelve a consultar cada minuto.
  const expiring = Boolean(page?.items.some((item) => item.visibleHasta));
  useEffect(() => {
    if (!expiring) return undefined;
    const timer = setInterval(load, 60_000);
    return () => clearInterval(timer);
  }, [expiring, load]);

  // La selección es de la página y de los filtros que se ven: al cambiar cualquiera de los dos, se limpia.
  useEffect(() => {
    setSelected(new Set());
    setConfirmingSelected(false);
  }, [filters, pagina]);

  function update(field) {
    return (event) => {
      setFilters((current) => ({ ...current, [field]: event.target.value }));
      setPagina(1);
    };
  }

  function toggleOne(id) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleExport(body) {
    setExporting(true);
    setError('');
    setNotice('');
    try {
      const { blob, filename } = await onExport(body, exportFormat);
      saveBlob(blob, filename);
      setNotice(`Exportación lista: ${filename}.`);
    } catch (exportError) {
      setError(handleOperationError(exportError));
    } finally {
      setExporting(false);
    }
  }

  async function deleteDemo() {
    try {
      const { eliminadas } = await onDeleteDemo();
      setNotice(eliminadas
        ? `Se eliminaron ${eliminadas} mediciones de prueba. Tus mediciones reales no se modificaron.` : 'No había mediciones de prueba.');
      setConfirmingDemo(false);
      await load();
    } catch (deleteError) {
      setError(handleOperationError(deleteError));
      setConfirmingDemo(false);
    }
  }

  // Borra una por una las mediciones marcadas (DEMO o reales, de la propia cuenta).
  async function deleteSelected() {
    setDeletingSelected(true);
    setError('');
    setNotice('');
    let eliminadas = 0;
    let lastError = '';
    for (const id of selectedIds) {
      try {
        await onDeleteOne(id);
        eliminadas += 1;
      } catch (deleteError) {
        lastError = handleOperationError(deleteError);
      }
    }
    setDeletingSelected(false);
    setConfirmingSelected(false);
    setSelected(new Set());
    if (eliminadas) setNotice(`Se eliminaron ${eliminadas} mediciones.`);
    if (eliminadas < selectedIds.length) setError(`No se pudieron eliminar ${selectedIds.length - eliminadas} mediciones. ${lastError}`.trim());
    await load();
  }

  const hasDemo = Boolean(page?.items.some((item) => item.esDemo));
  const totalPages = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;
  const filtered = Object.entries(filters).some(([key, current]) => current !== EMPTY_FILTERS[key]);
  // Exportar: solo en el perfil propio (`onExport`). La API vuelve a validar cada pedido.
  const pageIds = page?.items.map((measurement) => measurement.idMedicion) ?? [];
  const allOnPageSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id));
  // Solo las mediciones completadas de la selección se pueden eliminar.
  const selectedIds = page
    ? page.items.filter((item) => selected.has(item.idMedicion) && item.estadoMedicion === 'COMPLETADA')
      .map((item) => item.idMedicion)
    : [];

  return (
    <>
      <section className="panel" aria-labelledby="mediciones-historial">
        <div className="panel-title">
          <span className="panel-icon"><Activity size={22} aria-hidden="true" /></span>
          <div>
            <h2 id="mediciones-historial">Historial de mediciones</h2>
            <p>Prototipo experimental: los resultados no son un diagnóstico ni reemplazan una medición clínica certificada. Las pruebas DEMO se muestran identificadas.</p>
          </div>
        </div>
        <form className="history-filters" aria-label="Filtros del historial" onSubmit={(event) => event.preventDefault()}>
          <TextField label="Desde" type="date" value={filters.desde} onChange={update('desde')} />
          <TextField label="Hasta" type="date" value={filters.hasta} onChange={update('hasta')} />
          <SelectField label="Modo" value={filters.modo} onChange={update('modo')}>
            <option value="">Todos</option>
            {Object.entries(MODES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </SelectField>
          {filtroCondicion && (
            <SelectField label="Condición de comida" value={filters.condicion} onChange={update('condicion')}>
              <option value="">Todas</option>
              {Object.entries(MEALS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </SelectField>
          )}
          <SelectField label="Orden" value={filters.orden} onChange={update('orden')}>
            <option value="desc">Más recientes primero</option>
            <option value="asc">Más antiguas primero</option>
          </SelectField>
          {filtered && (
            <button type="button" className="btn btn-ghost history-filters-clear" onClick={() => { setFilters(EMPTY_FILTERS); setPagina(1); }}>
              <Filter size={16} aria-hidden="true" /> Limpiar filtros
            </button>
          )}
        </form>
        {error && <Alert>{error}</Alert>}
        {notice && <Alert kind="success">{notice}</Alert>}
        {page === null ? (
          <SkeletonList rows={5} label="Cargando mediciones…" />
        ) : page.items.length === 0 ? (
          <EmptyState variant="framed" headingLevel={0} title={filtered ? 'No hay mediciones que coincidan con los filtros.' : emptyText} />
        ) : (
          <>
            {onExport && (
              <div className="export-toolbar history-export">
                <label className="history-select-page">
                  <input type="checkbox" className="export-check" checked={allOnPageSelected}
                    onChange={() => setSelected(allOnPageSelected ? new Set() : new Set(pageIds))} />
                  Seleccionar esta página
                </label>
                <div className="history-export-actions">
                  <SelectField label="Formato" value={exportFormat} onChange={(event) => setExportFormat(event.target.value)} options={EXPORT_FORMATS} />
                  <button type="button" className="btn btn-outline" disabled={selected.size === 0 || exporting}
                    onClick={() => handleExport({ alcance: 'SELECCION', idsMedicion: [...selected] })}>
                    <Download size={18} aria-hidden="true" /> Exportar seleccionadas{selected.size > 0 ? ` (${selected.size})` : ''}
                  </button>
                  <button type="button" className="btn btn-outline" disabled={exporting}
                    onClick={() => handleExport({ alcance: 'TODOS', ...filledFilters(filters) })}>
                    <Download size={18} aria-hidden="true" /> Exportar todas{filtered ? ' las filtradas' : ''} ({page.total})
                  </button>
                  {onDeleteOne && (
                    <button type="button" className="btn btn-outline" disabled={selectedIds.length === 0 || deletingSelected}
                      onClick={() => setConfirmingSelected(true)}>
                      <Trash2 size={18} aria-hidden="true" /> Eliminar seleccionadas{selectedIds.length > 0 ? ` (${selectedIds.length})` : ''}
                    </button>
                  )}
                </div>
                {confirmingSelected && (
                  <Modal
                    title={`Eliminar ${selectedIds.length} ${selectedIds.length === 1 ? 'medición' : 'mediciones'}`}
                    onClose={() => { if (!deletingSelected) setConfirmingSelected(false); }}
                    actions={(
                      <>
                        <button type="button" className="btn btn-ghost" disabled={deletingSelected} onClick={() => setConfirmingSelected(false)}>Cancelar</button>
                        <button type="button" className="btn btn-primary" disabled={deletingSelected} onClick={deleteSelected}>
                          {deletingSelected && <span className="spinner" aria-hidden="true" />} Confirmar eliminación
                        </button>
                      </>
                    )}
                  >
                    <p>Se borran de tu historial y no se pueden recuperar.</p>
                  </Modal>
                )}
              </div>
            )}
            <div className="history-table-wrap">
              <table className="dash-table history-table" aria-label="Mediciones">
                <thead>
                  <tr>
                    {onExport && <th scope="col" className="export-check-cell"><span className="sr-only">Seleccionar</span></th>}
                    <th scope="col">Fecha y hora</th>
                    <th scope="col">Modo</th>
                    <th scope="col">Condición de comida</th>
                    <th scope="col">Valor glucosa</th>
                    <th scope="col">Frecuencia cardíaca</th>
                    <th scope="col">SpO₂</th>
                    <th scope="col">Estado</th>
                    <th scope="col"><span className="sr-only">Acciones</span></th>
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((measurement) => {
                    const when = formatDateTime(measurement.fechaHoraInicio);
                    const completed = measurement.estadoMedicion === 'COMPLETADA';
                    const glucose = completed ? glucoseOf(measurement) : null;
                    return (
                      <tr key={measurement.idMedicion}>
                        {onExport && (
                          <td data-label="Exportar" className="export-check-cell">
                            <input type="checkbox" className="export-check" checked={selected.has(measurement.idMedicion)}
                              onChange={() => toggleOne(measurement.idMedicion)} aria-label={`Seleccionar la medición del ${when}`} />
                          </td>
                        )}
                        <td data-label="Fecha y hora">
                          {when}
                          {measurement.visibleHasta && (
                            <small className="history-sub field-hint">Temporal: se oculta a las {measurement.visibleHasta.slice(11, 16)}</small>
                          )}
                        </td>
                        <td data-label="Modo">{MODES[measurement.modoMedicion] ?? measurement.modoMedicion}</td>
                        <td data-label="Condición de comida">
                          {MEALS[measurement.condicionComida] ?? measurement.condicionComida}
                        </td>
                        <td data-label="Valor glucosa">
                          <span className="history-value">
                            {glucose ? <span className="dash-chip">{value(glucose.value, 'mg/dL')}</span> : <span className="dash-muted">—</span>}
                            {measurement.esDemo && <DemoBadge />}
                            <Semaforo color={measurement.semaforo} />
                          </span>
                          {!completed && <small className="history-sub">Sin resultado válido.</small>}
                        </td>
                        <td data-label="Frecuencia cardíaca">{completed ? value(measurement.frecuenciaCardiaca, 'lpm') : '—'}</td>
                        <td data-label="SpO₂">{completed ? value(measurement.spo2, '%') : '—'}</td>
                        <td data-label="Estado">
                          <Badge tone={completed ? 'success' : 'neutral'}>
                            {STATES[measurement.estadoMedicion] ?? measurement.estadoMedicion}
                          </Badge>
                        </td>
                        <td className="dash-actions-cell">
                          <Link to={detailPath(measurement.idMedicion)} className="btn btn-outline" aria-label={`Ver detalle de la medición del ${when}`}>
                            Ver detalle <ChevronRight size={16} aria-hidden="true" />
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {onDeleteDemo && hasDemo && (
              <div className="form-actions">
                <button type="button" className="btn btn-outline" onClick={() => setConfirmingDemo(true)}>
                  <Trash2 size={16} aria-hidden="true" /> Eliminar mis datos de prueba
                </button>
              </div>
            )}
            {confirmingDemo && (
              <Modal
                title="Eliminar tus datos de prueba"
                onClose={() => setConfirmingDemo(false)}
                actions={(
                  <>
                    <button type="button" className="btn btn-ghost" onClick={() => setConfirmingDemo(false)}>Cancelar</button>
                    <button type="button" className="btn btn-primary" onClick={deleteDemo}>Confirmar eliminación</button>
                  </>
                )}
              >
                <p>Se borran todas tus pruebas DEMO completadas. Las mediciones reales no se tocan.</p>
              </Modal>
            )}
            {page.total > PAGE_SIZE && (
              <nav className="pagination" aria-label="Páginas de mediciones">
                <button type="button" className="btn btn-ghost" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>
                  <ChevronLeft size={16} aria-hidden="true" /> Anterior
                </button>
                <span>Página {page.pagina} de {totalPages} · {page.total} mediciones</span>
                <button type="button" className="btn btn-ghost" disabled={pagina >= totalPages} onClick={() => setPagina((p) => p + 1)}>
                  Siguiente <ChevronRight size={16} aria-hidden="true" />
                </button>
              </nav>
            )}
          </>
        )}
      </section>
      {loadEvolution && <Evolution loadEvolution={loadEvolution} pointPath={detailPath} handleOperationError={handleOperationError} />}
    </>
  );
}
