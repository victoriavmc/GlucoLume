// Inventario de dispositivos: indicadores reales, listado con búsqueda, filtros y paginación, alta y cambio de estado.
// Compartido por el inventario global (plataforma) y el de cada institución; cambia solo `api` y lo que el backend permite.
// En una institución el alta asigna el dispositivo al propietario (lo decide FastAPI) y lo único que se modifica desde la
// lista es el estado; la autorización de cada operación se vuelve a validar en el servidor.

import {
  AlertCircle, Building2, CheckCircle2, ChevronLeft, ChevronRight, Cpu, Download, Info, Link2Off, List, PackageOpen, Plus, Search, Trash2, Wrench,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { Badge, toneFromClass } from '../../../components/Badge.jsx';
import { EmptyState } from '../../../components/EmptyState.jsx';
import { Alert, SelectField, TextField } from '../../../components/FormControls.jsx';
import { Kpi, KpiGrid } from '../../../components/dashboard.jsx';
import { Modal } from '../../../components/Modal.jsx';
import { PageHeader } from '../../../components/PageHeader.jsx';
import { saveBlob } from '../../../utils/downloadFile.js';
import { EXPORT_FORMATS } from '../../../utils/exportFormats.js';
import { useLatestRequest } from '../../../utils/useLatestRequest.js';
import '../institutions/InstitutionPanel.css';
import '../institutions/exportControls.css';
import './DevicesInventory.css';
import { DeviceForm } from './DeviceForm.jsx';
import { DEVICE_STATES, EDITABLE_STATES, personLabel, stateBadge } from './deviceFormat.js';

const PAGE_SIZE = 10;
const EMPTY_FILTERS = { busqueda: '', estado: '', asignado: '', uso: '' };

function Summary({ summary, institutional }) {
  if (!summary) return <p className="field-hint" role="status">Cargando indicadores…</p>;
  return (
    <KpiGrid label="Indicadores del inventario" compact>
      <Kpi icon={Cpu} label="Total de dispositivos" value={summary.total} />
      <Kpi icon={CheckCircle2} tone="ok" label="Operativos" value={summary.operativos} />
      <Kpi icon={Wrench} tone="warn" label="En mantenimiento" value={summary.enMantenimiento} />
      <Kpi icon={AlertCircle} tone="danger" label="Fuera de servicio" value={summary.fueraDeServicio} />
      <Kpi icon={Trash2} tone="muted" label="Descomisionados" value={summary.descomisionados} />
      {!institutional && <Kpi icon={Building2} label="Asignados" value={summary.asignados} />}
      {!institutional && <Kpi icon={Link2Off} tone="muted" label="Sin asignar" value={summary.sinAsignar} />}
    </KpiGrid>
  );
}

/** Aviso sobre la asignación y sobre qué significa «operativo» (estado administrativo ≠ conexión ≠ disponibilidad real). */
function AssignmentNote({ institutional }) {
  if (institutional) {
    return (
      <div className="info-note" role="note">
        <Info size={22} aria-hidden="true" />
        <div>
          <b>Los dispositivos se registran solos cuando un operador conecta un Arduino nuevo, y quedan a cargo del propietario/a de la institución.</b>
          <p>
            Acá se consultan, se les cambia el nombre y se administra su estado; quien los conectó no adquiere su titularidad. El «Registrar dispositivo»
            manual queda para cargar un equipo que todavía no se conectó (o con firmware sin identificador): si ya está, no se duplica.
            «Operativo» significa que el dispositivo
            está habilitado administrativamente para utilizarse, pero no necesariamente conectado en tiempo real: el estado
            administrativo, la conexión y la disponibilidad real para medir son conceptos distintos. Los dispositivos descomisionados
            se conservan en el inventario como historial: no pueden reactivarse ni volver a usarse.
          </p>
        </div>
      </div>
    );
  }
  return null;
}

/** Cambio de estado administrativo desde la lista: pide confirmación explícita y no ofrece el retiro definitivo. */
function ChangeStateModal({ device, api, handleOperationError, onClose, onChanged }) {
  const [estado, setEstado] = useState(EDITABLE_STATES.find((state) => state !== device.estado) ?? 'OPERATIVO');
  const [motivo, setMotivo] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function save() {
    setBusy(true);
    setError('');
    try {
      await api.setState(device.idDispositivo, estado, motivo.trim());
      onChanged(device, estado);
    } catch (changeError) {
      setError(handleOperationError(changeError));
      setBusy(false);
    }
  }

  return (
    <Modal title={`Cambiar estado de ${device.codigoDispositivo}`} onClose={busy ? () => {} : onClose}
      actions={(
        <>
          <button type="button" className="btn btn-ghost" disabled={busy} onClick={onClose}>Cancelar</button>
          <button type="button" className="btn btn-primary" disabled={busy || estado === device.estado} aria-busy={busy || undefined} onClick={save}>
            {busy && <span className="spinner" aria-hidden="true" />} Confirmar cambio
          </button>
        </>
      )}>
      <p>
        Estado actual: <b>{DEVICE_STATES[device.estado]}</b>. Un dispositivo que no está operativo no puede iniciar ni continuar mediciones.
        Las mediciones ya realizadas no se modifican.
      </p>
      {error && <Alert>{error}</Alert>}
      <div className="ui-stack device-state-fields">
        <SelectField label="Nuevo estado" value={estado} onChange={(event) => setEstado(event.target.value)}
          options={EDITABLE_STATES.map((key) => ({ value: key, label: DEVICE_STATES[key] }))} />
        <TextField label="Motivo (opcional)" maxLength={300} value={motivo} onChange={(event) => setMotivo(event.target.value)} />
      </div>
    </Modal>
  );
}

export function DevicesInventory({
  title, lead, api, institutional, institutionName, showOwner = true, canRegister, canAssign, canChangeState, detailPath,
  handleOperationError, embedded,
}) {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [pagina, setPagina] = useState(1);
  const [page, setPage] = useState(null);
  const [summary, setSummary] = useState(null);
  const [registering, setRegistering] = useState(false);
  const [changing, setChanging] = useState(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(() => new Set()); // dispositivos marcados para exportar (solo de la página visible)
  const [exportFormat, setExportFormat] = useState('csv');
  const [exporting, setExporting] = useState(null); // clave de la exportación en curso: evita pedidos repetidos

  const beginRequest = useLatestRequest(); // una respuesta lenta de un filtro anterior no pisa a la del filtro actual

  const load = useCallback(async () => {
    const isCurrent = beginRequest();
    const params = { pagina, tamanioPagina: PAGE_SIZE };
    for (const [key, value] of Object.entries(filters)) if (value) params[key] = value;
    try {
      const [list, counts] = await Promise.all([api.list(params), api.summary()]);
      if (!isCurrent()) return;
      setPage(list);
      setSummary(counts);
      setError('');
    } catch (loadError) {
      if (!isCurrent()) return;
      setError(handleOperationError(loadError));
      setPage({ items: [], total: 0, pagina: 1, tamanioPagina: PAGE_SIZE });
      setSummary((current) => current ?? { total: 0, operativos: 0, enMantenimiento: 0, fueraDeServicio: 0, descomisionados: 0, asignados: 0, sinAsignar: 0, conectividadDisponible: false });
    }
  }, [api, filters, pagina, handleOperationError, beginRequest]);

  useEffect(() => {
    load();
  }, [load]);

  // Cambiar de página o de filtro limpia la selección: solo se exporta lo que se ve marcado.
  useEffect(() => {
    setSelected(new Set());
  }, [filters, pagina]);

  function update(field) {
    return (event) => {
      setFilters((current) => ({ ...current, [field]: event.target.value }));
      setPagina(1);
    };
  }

  const filtered = Object.values(filters).some(Boolean);
  const totalPages = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;
  // Inventario global: el responsable institucional por correo; si es de uso individual, los correos de sus cuentas.
  const ownerText = (device) => {
    if (!institutional) {
      if (device.responsable) return device.responsable.correoElectronico || personLabel(device.responsable);
      if (device.correosIndividuales?.length) return device.correosIndividuales.join(', ');
      return device.idInstitucionAsignada ? 'Sin responsable' : 'No responsable';
    }
    if (device.responsable) return personLabel(device.responsable);
    if (device.esMio) return 'Vos';
    return showOwner ? 'Sin asignar' : '—';
  };
  // Inventario global, columna «Uso»: la institución asignada, «Individual» si está vinculado a una cuenta, o «Sin asignar».
  const usageText = (device) => {
    if (device.idInstitucionAsignada) return device.nombreInstitucion ?? 'Institución';
    return device.vinculadoCuentasIndividuales ? 'Individual' : 'Sin asignar';
  };
  const pageIds = page ? page.items.map((device) => device.idDispositivo) : [];
  const allVisibleSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id));

  function toggleAll() {
    setSelected(allVisibleSelected ? new Set() : new Set(pageIds));
  }

  function toggleOne(id) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // Filtros del listado, tal como los recibe el backend para exportar «todos».
  const exportFilters = () => ({
    busqueda: filters.busqueda.trim() || undefined,
    estado: filters.estado || undefined,
    asignado: filters.asignado === '' ? undefined : filters.asignado === 'true',
    uso: filters.uso || undefined,
  });

  async function handleExport(key, body) {
    setExporting(key);
    setError('');
    setNotice('');
    try {
      const { blob, filename } = await api.exportList(body, exportFormat);
      saveBlob(blob, filename);
      setNotice(`Exportación lista: ${filename}.`);
    } catch (failure) {
      setError(handleOperationError(failure));
    } finally {
      setExporting(null);
    }
  }

  const register = (
    <button type="button" className="btn btn-primary" onClick={() => { setNotice(''); setRegistering(true); }}>
      <Plus size={18} aria-hidden="true" /> Registrar dispositivo
    </button>
  );

  return (
    <div className={embedded ? 'inventory' : 'page inventory'}>
      {!embedded && <PageHeader title={title} description={lead} />}
      {embedded && <p className="inventory-lead">{lead}</p>}
      {notice && <Alert kind="success">{notice}</Alert>}
      {error && <Alert>{error}</Alert>}

      <section className="panel" aria-labelledby="inventario-resumen">
        <div className="panel-head">
          <div className="panel-title">
            <span className="panel-icon"><Cpu size={22} aria-hidden="true" /></span>
            <div><h2 id="inventario-resumen">Inventario de dispositivos</h2><p>Prototipos con Arduino y sensor MAX30100 o MAX30102.</p></div>
          </div>
          {canRegister && !registering && register}
        </div>
        <Summary summary={summary} institutional={institutional} />
        <AssignmentNote institutional={institutional} />
      </section>

      {registering && (
        <DeviceForm api={api} institutional={institutional} canAssign={canAssign} handleOperationError={handleOperationError}
          onCancel={() => setRegistering(false)}
          onSaved={(saved) => { setRegistering(false); setNotice(`Registramos el dispositivo ${saved.codigoDispositivo}.`); load(); }} />
      )}

      <section className="panel" aria-labelledby="inventario-listado">
        <div className="panel-title">
          <span className="panel-icon"><List size={22} aria-hidden="true" /></span>
          <h2 id="inventario-listado">Dispositivos</h2>
        </div>
        <form className="form-grid measurement-filters device-filters" aria-label="Filtros del inventario" onSubmit={(event) => event.preventDefault()}>
          <TextField label="Buscar" icon={Search} value={filters.busqueda} maxLength={100} onChange={update('busqueda')} placeholder="Código, nombre, modelo o responsable" />
          <SelectField label="Estado" value={filters.estado} onChange={update('estado')}>
            <option value="">Todos</option>
            {Object.entries(DEVICE_STATES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </SelectField>
          {!institutional && (
            <SelectField label="Asignación" value={filters.asignado} onChange={update('asignado')}>
              <option value="">Todos</option><option value="true">Asignados</option><option value="false">Sin asignar</option>
            </SelectField>
          )}
          {!institutional && (
            <SelectField label="Uso" value={filters.uso} onChange={update('uso')}>
              <option value="">Todos</option><option value="INSTITUCION">Institución</option><option value="INDIVIDUAL">Individual</option>
            </SelectField>
          )}
          {filtered && <button type="button" className="btn btn-ghost" onClick={() => { setFilters(EMPTY_FILTERS); setPagina(1); }}>Limpiar filtros</button>}
        </form>
        {page === null ? (
          <p className="field-hint" role="status">Cargando dispositivos…</p>
        ) : page.items.length === 0 ? (
          filtered ? (
            <EmptyState variant="framed" icon={Search} title="No hay dispositivos que coincidan con los filtros." description="Probá con otro código, nombre o modelo, o limpiá los filtros." />
          ) : (
            <EmptyState icon={PackageOpen} title="Todavía no hay dispositivos en el inventario."
              description={institutional
                ? 'Registrá el primer dispositivo para comenzar a gestionar el inventario de esta institución.'
                : 'Registrá el primer dispositivo para comenzar a gestionar el inventario.'}
              action={canRegister && !registering ? register : undefined} />
          )
        ) : (
          <>
            <div className="export-toolbar device-export" role="group" aria-label="Exportar dispositivos">
              <select className="field-input field-select" aria-label="Formato de exportación" value={exportFormat}
                onChange={(event) => setExportFormat(event.target.value)}>
                {EXPORT_FORMATS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
              <button type="button" className="btn btn-outline btn-sm" disabled={selected.size === 0 || exporting !== null}
                onClick={() => handleExport('seleccion', { alcance: 'SELECCION', idsDispositivo: [...selected] })}>
                <Download size={16} aria-hidden="true" /> Exportar seleccionados{selected.size > 0 ? ` (${selected.size})` : ''}
              </button>
              <button type="button" className="btn btn-primary btn-sm" disabled={exporting !== null}
                onClick={() => handleExport('todos', { alcance: 'TODOS', ...exportFilters() })}>
                <Download size={16} aria-hidden="true" /> Exportar todos{filtered ? ' los filtrados' : ''} ({page.total})
              </button>
            </div>
            <div className="table-scroll">
              <table className="data-table device-table" aria-label="Dispositivos">
                <thead>
                  <tr>
                    <th scope="col" className="export-check-cell">
                      <input type="checkbox" className="export-check" aria-label="Seleccionar todos los de esta página"
                        checked={allVisibleSelected} onChange={toggleAll} />
                    </th>
                    <th scope="col">Código</th><th scope="col">Nombre</th><th scope="col">Modelo</th><th scope="col">Estado</th>
                    <th scope="col">{institutional ? 'Institución' : 'Uso'}</th>
                    <th scope="col">{institutional ? 'Propietario asignado' : 'Responsable'}</th>
                    <th scope="col"><span className="sr-only">Acciones</span></th>
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((device) => (
                    <tr key={device.idDispositivo}>
                      <td className="export-check-cell" data-label="Exportar">
                        <input type="checkbox" className="export-check" aria-label={`Seleccionar ${device.codigoDispositivo}`}
                          checked={selected.has(device.idDispositivo)} onChange={() => toggleOne(device.idDispositivo)} />
                      </td>
                      <th scope="row" data-label="Código">{device.codigoDispositivo}</th>
                      <td data-label="Nombre">{device.nombre ?? '—'}</td>
                      <td data-label="Modelo">{device.modelo ?? device.modeloSensor}</td>
                      <td data-label="Estado"><Badge tone={toneFromClass(stateBadge(device.estado))}>{DEVICE_STATES[device.estado]}</Badge></td>
                      <td data-label={institutional ? 'Institución' : 'Uso'}>{institutional ? institutionName ?? '—' : usageText(device)}</td>
                      <td data-label={institutional ? 'Propietario asignado' : 'Responsable'}>{ownerText(device)}</td>
                      <td className="device-actions">
                        <Link to={detailPath(device.idDispositivo)} className="btn btn-ghost" aria-label={`Ver detalle de ${device.codigoDispositivo}`}>Ver detalle</Link>
                        {canChangeState && device.estado !== 'BAJA' && (
                          <button type="button" className="btn btn-outline" aria-label={`Cambiar estado de ${device.codigoDispositivo}`}
                            onClick={() => { setNotice(''); setChanging(device); }}>
                            Cambiar estado
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {page.total > PAGE_SIZE && (
              <nav className="pagination" aria-label="Páginas del inventario">
                <button type="button" className="btn btn-ghost" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>
                  <ChevronLeft size={16} aria-hidden="true" /> Anterior
                </button>
                <span>Página {page.pagina} de {totalPages} · {page.total} dispositivos</span>
                <button type="button" className="btn btn-ghost" disabled={pagina >= totalPages} onClick={() => setPagina((p) => p + 1)}>
                  Siguiente <ChevronRight size={16} aria-hidden="true" />
                </button>
              </nav>
            )}
          </>
        )}
      </section>

      {changing && (
        <ChangeStateModal device={changing} api={api} handleOperationError={handleOperationError} onClose={() => setChanging(null)}
          onChanged={(device, estado) => {
            setChanging(null);
            setNotice(`El dispositivo ${device.codigoDispositivo} quedó ${DEVICE_STATES[estado].toLowerCase()}.`);
            load();
          }} />
      )}
    </div>
  );
}
