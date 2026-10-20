// Detalle de un dispositivo, acciones autorizadas y mediciones relacionadas. Las acciones salen de `permisos` (rol,
// institución y estado, calculados por FastAPI) y cada operación se vuelve a validar en el servidor. Cambiar la
// asignación, el estado o el firmware no modifica las mediciones anteriores: conservan lo que tenía el dispositivo al medir.

import { Ban, Cpu, Link2Off, Pencil, UserCog } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Badge, toneFromClass } from '../../../components/Badge.jsx';
import { Alert, SelectField, SubmitButton, TextField } from '../../../components/FormControls.jsx';
import { DeviceForm } from './DeviceForm.jsx';
import { DEVICE_STATES, EDITABLE_STATES, formatDateTime, personLabel, stateBadge } from './deviceFormat.js';

const MODES = { OXIMETRIA: 'Oximetría', GLUCOSA_EXPERIMENTAL: 'Glucosa (experimental)' };
const MEASUREMENT_STATES = {
  PENDIENTE: 'Pendiente', ADQUIRIENDO: 'Adquiriendo', PROCESANDO: 'Procesando', COMPLETADA: 'Completada', INVALIDA: 'Inválida', CANCELADA: 'Cancelada',
};

const REGISTRATION_ORIGINS = {
  CONEXION_OPERADOR: 'Primera conexión de un operador',
  AUTOMATICO_PUENTE: 'Alta automática del puente',
  MANUAL: 'Alta administrativa desde el inventario',
};
const CONNECTION_MEDIA = { BLUETOOTH: 'Bluetooth', USB: 'USB' };

function registrationText(registro) {
  if (!registro) return undefined;
  const person = [registro.nombre, registro.apellido].filter(Boolean).join(' ');
  const medium = registro.medio ? ` por ${CONNECTION_MEDIA[registro.medio] ?? registro.medio}` : '';
  return `${REGISTRATION_ORIGINS[registro.origen] ?? registro.origen}${person ? `: ${person}` : ''}${medium}, el ${formatDateTime(registro.fecha)}`;
}

function Row({ label, children }) {
  return <div><dt>{label}</dt><dd className={children ? undefined : 'is-empty'}>{children || '—'}</dd></div>;
}

export function DeviceDetail({ idDispositivo, api, institutional, handleOperationError }) {
  const [device, setDevice] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(null);
  const [busy, setBusy] = useState(false);
  const [state, setState] = useState({ estado: 'OPERATIVO', motivo: '' });
  const [responsibleId, setResponsibleId] = useState('');
  const [responsibles, setResponsibles] = useState([]);
  const [assign, setAssign] = useState({ institucion: '', responsable: '' });
  const [institutionOptions, setInstitutionOptions] = useState([]);
  const [assignMembers, setAssignMembers] = useState([]);
  const [measurements, setMeasurements] = useState(null);

  const adopt = useCallback((loaded) => {
    setDevice(loaded);
    setState({ estado: loaded.estado === 'BAJA' ? 'OPERATIVO' : loaded.estado, motivo: '' });
    setResponsibleId(loaded.responsable?.idInstitucionUsuario ?? '');
  }, []);

  const load = useCallback(async () => {
    try {
      const loaded = await api.get(idDispositivo);
      adopt(loaded);
      setError('');
      return loaded;
    } catch (loadError) {
      setError(handleOperationError(loadError));
      return null;
    }
  }, [api, idDispositivo, handleOperationError, adopt]);

  useEffect(() => {
    setDevice(null);
    load();
  }, [load]);

  const permisos = device?.permisos;

  useEffect(() => {
    if (!permisos?.puedeVerMediciones) return;
    api.measurements(idDispositivo).then(setMeasurements, () => setMeasurements({ items: [], total: 0 }));
  }, [api, idDispositivo, permisos?.puedeVerMediciones, device?.estado, device?.idInstitucionAsignada]);

  useEffect(() => {
    if (!permisos?.puedeCambiarResponsable || !device?.idInstitucionAsignada) return;
    (institutional ? api.responsibles() : api.institutionResponsibles(device.idInstitucionAsignada)).then(setResponsibles, () => setResponsibles([]));
  }, [api, institutional, permisos?.puedeCambiarResponsable, device?.idInstitucionAsignada]);

  useEffect(() => {
    if (!permisos?.puedeAsignarInstitucion) return;
    api.institutionOptions().then(setInstitutionOptions, () => setInstitutionOptions([]));
  }, [api, permisos?.puedeAsignarInstitucion]);

  useEffect(() => {
    if (!assign.institucion) { setAssignMembers([]); return; }
    api.institutionResponsibles(assign.institucion).then(setAssignMembers, () => setAssignMembers([]));
  }, [api, assign.institucion]);

  async function run(call, message) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      adopt(await call());
      setNotice(message);
      setConfirming(null);
    } catch (actionError) {
      const text = handleOperationError(actionError);
      setConfirming(null);
      await load();
      setError(text);
    } finally {
      setBusy(false);
    }
  }

  if (error && !device) return <Alert>{error}</Alert>;
  if (!device) return <p className="field-hint" role="status">Cargando dispositivo…</p>;
  const retired = device.estado === 'BAJA';

  return (
    <>
      <section className="panel" aria-labelledby="dispositivo-titulo">
        <div className="panel-head">
          <div className="panel-title">
            <span className="panel-icon"><Cpu size={22} aria-hidden="true" /></span>
            <div>
              {institutional ? <h2 id="dispositivo-titulo">{device.nombre || device.codigoDispositivo}</h2> : <h1 id="dispositivo-titulo">{device.nombre || device.codigoDispositivo}</h1>}
              <p><Badge tone={toneFromClass(stateBadge(device.estado))}>{DEVICE_STATES[device.estado]}</Badge>{' '}
                {device.disponibleParaMedir ? 'Disponible para medir' : 'No disponible para nuevas mediciones'}</p>
            </div>
          </div>
          {permisos.puedeEditar && !editing && (
            <button type="button" className="btn btn-outline" onClick={() => { setNotice(''); setEditing(true); }}>
              <Pencil size={16} aria-hidden="true" /> Modificar
            </button>
          )}
        </div>
        {notice && <Alert kind="success">{notice}</Alert>}
        {error && <Alert>{error}</Alert>}
        <dl className="data-list">
          <Row label="Identificador">{device.idDispositivo}</Row>
          <Row label="Código">{device.codigoDispositivo}</Row>
          <Row label="Nombre">{device.nombre}</Row>
          <Row label="Modelo">{device.modelo}</Row>
          <Row label="Sensor">{device.modeloSensor}</Row>
          <Row label="Firmware">{device.versionFirmware}</Row>
          <Row label="Estado operativo">{DEVICE_STATES[device.estado]}</Row>
          <Row label="Estado de conexión">No informado: el inventario no verifica la conexión</Row>
          <Row label="Institución">{institutional ? undefined : device.nombreInstitucion ?? 'Sin asignar'}</Row>
          <Row label={institutional ? 'Propietario asignado' : 'Responsable'}>{device.responsable ? personLabel(device.responsable) : device.esMio ? 'Vos' : undefined}</Row>
          <Row label="Registrado">{formatDateTime(device.fechaRegistro)}</Row>
          <Row label="Registrado por">{registrationText(device.registro)}</Row>
          <Row label="Asignado desde">{device.fechaAsignacionInstitucional && formatDateTime(device.fechaAsignacionInstitucional)}</Row>
        </dl>
        {retired && <Alert kind="info">Este dispositivo fue descomisionado: se conserva su historial pero ya no admite cambios ni mediciones nuevas.</Alert>}
      </section>

      {editing && (
        <DeviceForm api={api} device={device} institutional={institutional} handleOperationError={handleOperationError}
          onCancel={() => setEditing(false)}
          onSaved={(saved) => { setEditing(false); setDevice(saved); setNotice('Guardamos los cambios del dispositivo.'); load(); }} />
      )}

      {permisos.puedeCambiarEstado && (
        <section className="panel" aria-labelledby="dispositivo-estado">
          <h2 id="dispositivo-estado">Cambiar estado</h2>
          <p className="field-hint">Un dispositivo que no está operativo no puede iniciar ni continuar adquisiciones.</p>
          <div className="form-grid">
            <SelectField label="Nuevo estado" value={state.estado} onChange={(event) => setState((c) => ({ ...c, estado: event.target.value }))}>
              {EDITABLE_STATES.map((key) => <option key={key} value={key}>{DEVICE_STATES[key]}</option>)}
            </SelectField>
            <TextField label="Motivo (opcional)" maxLength={300} value={state.motivo} onChange={(event) => setState((c) => ({ ...c, motivo: event.target.value }))} />
          </div>
          <div className="form-actions">
            <SubmitButton type="button" loading={busy} loadingLabel="Guardando…" className="btn btn-outline" disabled={busy || state.estado === device.estado}
              onClick={() => run(() => api.setState(idDispositivo, state.estado, state.motivo.trim()), `El dispositivo quedó ${DEVICE_STATES[state.estado].toLowerCase()}.`)}>
              Cambiar estado
            </SubmitButton>
          </div>
        </section>
      )}

      {permisos.puedeAsignarInstitucion && (
        <section className="panel" aria-labelledby="dispositivo-asignar">
          <div className="panel-title">
            <span className="panel-icon"><UserCog size={22} aria-hidden="true" /></span>
            <div><h2 id="dispositivo-asignar">Asignar a una institución</h2><p>Solo el administrador del sistema asigna dispositivos a instituciones.</p></div>
          </div>
          <div className="form-grid">
            <SelectField label="Institución" value={assign.institucion} onChange={(event) => setAssign({ institucion: event.target.value, responsable: '' })}>
              <option value="">Elegí una institución</option>
              {institutionOptions.map((option) => <option key={option.idInstitucion} value={option.idInstitucion}>{option.nombre}</option>)}
            </SelectField>
            {assign.institucion && (
              <SelectField label="Responsable (opcional)" value={assign.responsable} onChange={(event) => setAssign((c) => ({ ...c, responsable: event.target.value }))}>
                <option value="">Sin responsable</option>
                {assignMembers.map((person) => <option key={person.idInstitucionUsuario} value={person.idInstitucionUsuario}>{personLabel(person)}</option>)}
              </SelectField>
            )}
          </div>
          <div className="form-actions">
            <SubmitButton type="button" loading={busy} loadingLabel="Asignando…" className="btn btn-primary" disabled={busy || !assign.institucion}
              onClick={() => run(() => api.assign(idDispositivo, assign.institucion, assign.responsable), 'Asignamos el dispositivo.')}>
              Asignar dispositivo
            </SubmitButton>
          </div>
        </section>
      )}

      {permisos.puedeCambiarResponsable && (
        <section className="panel" aria-labelledby="dispositivo-responsable">
          <h2 id="dispositivo-responsable">Responsable</h2>
          <p className="field-hint">Solo integrantes activos de la institución del dispositivo.</p>
          <SelectField label="Responsable" value={responsibleId} onChange={(event) => setResponsibleId(event.target.value)}>
            <option value="">Sin responsable</option>
            {responsibles.map((person) => <option key={person.idInstitucionUsuario} value={person.idInstitucionUsuario}>{personLabel(person)}</option>)}
          </SelectField>
          <div className="form-actions">
            <SubmitButton type="button" loading={busy} loadingLabel="Guardando…" className="btn btn-outline"
              disabled={busy || responsibleId === (device.responsable?.idInstitucionUsuario ?? '')}
              onClick={() => run(() => api.setResponsible(idDispositivo, responsibleId || null), 'Cambiamos el responsable.')}>
              Cambiar responsable
            </SubmitButton>
          </div>
        </section>
      )}

      {(permisos.puedeDesvincular || permisos.puedeDescomisionar) && (
        <section className="panel is-danger" aria-labelledby="dispositivo-retiro">
          <h2 id="dispositivo-retiro">Retirar</h2>
          <p className="field-hint">El dispositivo y las mediciones realizadas con él se conservan siempre.</p>
          <div className="form-actions">
            {confirming ? (
              <>
                <span className="field-hint">
                  {confirming === 'unassign'
                    ? '¿Desvincular el dispositivo de la institución? Queda sin institución ni responsable.'
                    : '¿Descomisionar definitivamente? Sigue en el inventario como «Descomisionado», conserva su historial y no se puede reactivar ni volver a usar para medir.'}
                </span>
                <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => setConfirming(null)}>Volver</button>
                <button type="button" className="btn btn-primary" disabled={busy}
                  onClick={() => (confirming === 'unassign'
                    ? run(() => api.unassign(idDispositivo), 'Desvinculamos el dispositivo.')
                    : run(() => api.decommission(idDispositivo), 'El dispositivo quedó descomisionado.'))}>
                  {busy && <span className="spinner" aria-hidden="true" />} Confirmar
                </button>
              </>
            ) : (
              <>
                {permisos.puedeDesvincular && (
                  <button type="button" className="btn btn-outline" onClick={() => setConfirming('unassign')}>
                    <Link2Off size={16} aria-hidden="true" /> Desvincular
                  </button>
                )}
                {permisos.puedeDescomisionar && (
                  <button type="button" className="btn btn-outline" onClick={() => setConfirming('decommission')}>
                    <Ban size={16} aria-hidden="true" /> Descomisionar
                  </button>
                )}
              </>
            )}
          </div>
        </section>
      )}

      {permisos.puedeVerMediciones && (
        <section className="panel" aria-labelledby="dispositivo-mediciones">
          <h2 id="dispositivo-mediciones">Mediciones relacionadas</h2>
          <p className="field-hint">
            Sin datos de los pacientes. Cada medición muestra el sensor y el firmware que tenía el dispositivo en ese momento.
            {institutional ? ' Solo se incluyen pacientes de esta institución.' : ''}
          </p>
          {measurements === null ? (
            <p className="field-hint" role="status">Cargando mediciones…</p>
          ) : measurements.items.length === 0 ? (
            <p className="field-hint">Todavía no hay mediciones con este dispositivo.</p>
          ) : (
            <ul className="member-list-items" aria-label="Mediciones del dispositivo">
              {measurements.items.map((item) => (
                <li key={item.idMedicion} className="member-row">
                  <span>
                    <b>{formatDateTime(item.fechaHoraInicio)}</b>
                    <small> · {MODES[item.modoMedicion] ?? item.modoMedicion} · {item.modeloSensorAlMomento ?? '—'} · firmware {item.versionFirmwareAlMomento ?? '—'}
                      {item.nombreInstitucion ? ` · ${item.nombreInstitucion}` : ''}</small>
                  </span>
                  <Badge tone="neutral">{MEASUREMENT_STATES[item.estadoMedicion] ?? item.estadoMedicion}</Badge>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </>
  );
}
