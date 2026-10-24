// Historial de mediciones con filtros (fecha, modo, estado, orden), detalle, estadísticas y gráficos. Lo usan el
// perfil propio y cada paciente institucional: cambia solo de dónde salen los datos (`loadPage`/`loadEvolution`),
// que el backend autoriza en cada consulta. Los gráficos usan solo mediciones completadas.

import { Activity, ChevronLeft, ChevronRight, Filter, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { Badge, OriginBadge } from '../../../components/Badge.jsx';
import { EmptyState } from '../../../components/EmptyState.jsx';
import { Alert, SelectField, TextField } from '../../../components/FormControls.jsx';
import { SkeletonList } from '../../../components/Skeleton.jsx';
import { useLatestRequest } from '../../../utils/useLatestRequest.js';
import { DemoBadge } from './DeviceReadout.jsx';
import { EvolutionPanel } from './EvolutionPanel.jsx';
import { MEALS, MODES, ORIGINS, STATES, formatDateTime } from './measurementFormat.js';

const PAGE_SIZE = 10;
const EMPTY_FILTERS = { desde: '', hasta: '', modo: '', estado: '', origen: '', orden: 'desc' };

function value(number, unit) {
  return number === null || number === undefined ? '—' : `${Number(number).toLocaleString('es-AR')} ${unit}`;
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

export function MeasurementHistory({ loadPage, loadEvolution, detailPath, handleOperationError, emptyText, refreshKey, onDeleteDemo }) {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [confirmingDemo, setConfirmingDemo] = useState(false);
  const [notice, setNotice] = useState('');
  const [pagina, setPagina] = useState(1);
  const [page, setPage] = useState(null);
  const [error, setError] = useState('');

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

  function update(field) {
    return (event) => {
      setFilters((current) => ({ ...current, [field]: event.target.value }));
      setPagina(1);
    };
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

  const hasDemo = Boolean(page?.items.some((item) => item.esDemo));
  const totalPages = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;
  const filtered = Object.entries(filters).some(([key, current]) => current !== EMPTY_FILTERS[key]);

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
        <form className="form-grid measurement-filters" aria-label="Filtros del historial" onSubmit={(event) => event.preventDefault()}>
          <TextField label="Desde" type="date" value={filters.desde} onChange={update('desde')} />
          <TextField label="Hasta" type="date" value={filters.hasta} onChange={update('hasta')} />
          <SelectField label="Modo" value={filters.modo} onChange={update('modo')}>
            <option value="">Todos</option>
            {Object.entries(MODES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </SelectField>
          <SelectField label="Estado" value={filters.estado} onChange={update('estado')}>
            <option value="">Todos</option>
            {Object.entries(STATES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </SelectField>
          <SelectField label="Origen de los datos" value={filters.origen} onChange={update('origen')}>
            <option value="">Todos</option>
            <option value="REAL">Mediciones reales</option>
            <option value="DEMO">Datos de prueba (DEMO)</option>
          </SelectField>
          <SelectField label="Orden" value={filters.orden} onChange={update('orden')}>
            <option value="desc">Más recientes primero</option>
            <option value="asc">Más antiguas primero</option>
          </SelectField>
          {filtered && (
            <button type="button" className="btn btn-ghost" onClick={() => { setFilters(EMPTY_FILTERS); setPagina(1); }}>
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
            <ul className="member-list-items" aria-label="Mediciones">
              {page.items.map((measurement) => (
                <li key={measurement.idMedicion} className="member-row measurement-card">
                  <span>
                    <b>{formatDateTime(measurement.fechaHoraInicio)}</b>
                    <small> · {MODES[measurement.modoMedicion] ?? measurement.modoMedicion} · {MEALS[measurement.condicionComida] ?? measurement.condicionComida}{measurement.modoMedicion === 'GLUCOSA_EXPERIMENTAL' && ` · Última comida: ${measurement.fechaHoraUltimaComida ? formatDateTime(measurement.fechaHoraUltimaComida) : 'Sin informar'}`}</small>
                    {measurement.origenGlucosa && !measurement.esDemo && (
                      <> <OriginBadge origin={measurement.origenGlucosa}>{measurement.origenGlucosa}</OriginBadge></>
                    )}
                    <br />
                    {measurement.estadoMedicion === 'COMPLETADA' ? (
                      <small>
                        SpO₂ {value(measurement.spo2, '%')} · Frecuencia cardíaca {value(measurement.frecuenciaCardiaca, 'lpm')}
                        {measurement.glucosaEstimada !== null && ` · Glucosa estimada ${value(measurement.glucosaEstimada, 'mg/dL')}`}
                      </small>
                    ) : (
                      <small>Sin resultado válido.</small>
                    )}
                    {measurement.origenGlucosa && measurement.estadoMedicion === 'COMPLETADA' && (
                      <small> · Glucosa del dispositivo {value(measurement.glucosaDispositivo, 'mg/dL')} ({ORIGINS[measurement.origenGlucosa] ?? measurement.origenGlucosa})</small>
                    )}
                    {measurement.dispositivo && <small> · Dispositivo {measurement.dispositivo}</small>}
                    {measurement.visibleHasta && (
                      <small className="field-hint"> · Temporal: se oculta del historial a las {measurement.visibleHasta.slice(11, 16)}</small>
                    )}
                  </span>
                  <span className="measurement-card-actions">
                    {measurement.esDemo && <DemoBadge />}{' '}
                    <Badge tone={measurement.estadoMedicion === 'COMPLETADA' ? 'success' : 'neutral'}>
                      {STATES[measurement.estadoMedicion] ?? measurement.estadoMedicion}
                    </Badge>
                    <Link to={detailPath(measurement.idMedicion)} className="btn btn-outline">Ver detalle</Link>
                  </span>
                </li>
              ))}
            </ul>
            {onDeleteDemo && (hasDemo || filters.origen === 'DEMO') && (
              <div className="form-actions">
                {confirmingDemo ? (
                  <>
                    <span className="field-hint">¿Eliminar todos tus datos de prueba (DEMO)? Las mediciones reales no se tocan.</span>
                    <button type="button" className="btn btn-ghost" onClick={() => setConfirmingDemo(false)}>Volver</button>
                    <button type="button" className="btn btn-primary" onClick={deleteDemo}>Confirmar eliminación</button>
                  </>
                ) : (
                  <button type="button" className="btn btn-outline" onClick={() => setConfirmingDemo(true)}>
                    <Trash2 size={16} aria-hidden="true" /> Eliminar mis datos de prueba
                  </button>
                )}
              </div>
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
