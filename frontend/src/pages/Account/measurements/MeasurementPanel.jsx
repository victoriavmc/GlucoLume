// Estado y resultado de una medición. Muestra siempre el estado REAL que informa el backend (se consulta cada pocos
// segundos mientras la medición está en curso) y nunca presenta como resultado una medición inválida o cancelada.
//
// La adquisición real (Arduino → USB / Bluetooth HC-06 → pySerial → FastAPI) se opera desde LiveAcquisition. Esta
// pantalla no genera ni simula datos del sensor: muestra lo que el backend recibió y calculó.

import {
  Ban, CalendarDays, ChartColumn, Database, Droplet, FileText, FlaskConical, HeartPulse, BookOpen, Info, Mail, Settings, Signal, Smartphone, Sparkles,
  Trash2, User, Utensils, Wind,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import * as measurementsApi from '../../../api/measurementsApi.js';
import { ExperimentalNotice } from '../../../components/ExperimentalNotice.jsx';
import { Alert, CheckField, SubmitButton, TextField } from '../../../components/FormControls.jsx';
import { LiveAcquisition } from '../acquisition/LiveAcquisition.jsx';
import { Badge } from '../../../components/Badge.jsx';
import { DemoBadge, DeviceReadout } from './DeviceReadout.jsx';
import { GlucoseReferencePanel } from './GlucoseReferencePanel.jsx';
import { DeviceSession } from './DeviceSession.jsx';
import {
  ACTIVE_STATES, DEMO_NOTICE, MEALS, MODES, ORIGINS, STATES, dateTimeForApi, formatDateTime, formatIndex, formatNumber,
} from './measurementFormat.js';
import { useDeviceStatus } from './useDeviceStatus.js';

const POLL_MS = 3000;

function Row({ label, children }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className={children || children === 0 ? undefined : 'is-empty'}>{children || children === 0 ? children : 'No informado'}</dd>
    </div>
  );
}

/** Resultado grande del detalle, con su ícono. Un dato ausente se muestra «Sin dato», nunca como cero. */
function ResultCard({ label, value, unit, format, empty = 'Sin dato', badge = null, note = null, icon: Icon, tone = 'rose' }) {
  const missing = value === null || value === undefined;
  const text = missing ? null : format ? format(value) : typeof value === 'number' || /^[\d.]+$/.test(String(value)) ? formatNumber(value, unit) : String(value);
  return (
    <li className="result-card">
      {Icon && <span className={`result-icon is-${tone}`}><Icon size={26} aria-hidden="true" /></span>}
      <small>{label}</small>
      <b className={missing ? 'is-empty' : undefined}>{missing ? empty : text} {badge}</b>
      {note && <span className="field-hint">{note}</span>}
    </li>
  );
}

function CapillaryReference({ measurement, onSaved, handleOperationError }) {
  const [form, setForm] = useState({ valor: '', fecha: '', marca: '', modelo: '' });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const reference = measurement.referenciaCapilar;

  if (reference) {
    return (
      <dl className="data-list" aria-label="Referencia capilar">
        <Row label="Referencia capilar (glucómetro)">{formatNumber(reference.glucosaReferencia, 'mg/dL')}</Row>
        <Row label="Fecha de la referencia">{formatDateTime(reference.fechaHoraReferencia)}</Row>
        <Row label="Glucómetro">{[reference.marcaGlucometro, reference.modeloGlucometro].filter(Boolean).join(' ')}</Row>
      </dl>
    );
  }
  if (!measurement.puedeOperar) return null;

  function update(field) {
    return (event) => setForm((current) => ({ ...current, [field]: event.target.value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving) return;
    if (!form.valor || Number(form.valor) < 0 || !form.fecha) {
      setError('Ingresá el valor medido con el glucómetro y cuándo lo mediste.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      onSaved(await measurementsApi.registerCapillaryReference(measurement.idMedicion, {
        glucosaReferencia: form.valor, fechaHoraReferencia: dateTimeForApi(form.fecha),
        marcaGlucometro: form.marca.trim() || undefined, modeloGlucometro: form.modelo.trim() || undefined,
      }));
    } catch (saveError) {
      setError(handleOperationError(saveError));
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate aria-label="Registrar referencia capilar">
      <p className="field-hint">
        Si mediste la glucosa con un glucómetro capilar real, podés registrarla como referencia. Queda separada de la
        estimación y nunca la reemplaza.
      </p>
      {error && <Alert>{error}</Alert>}
      <div className="form-grid">
        <TextField label="Glucosa capilar (mg/dL)" type="number" min="0" step="0.01" value={form.valor} onChange={update('valor')} />
        <TextField label="Fecha y hora de la referencia" type="datetime-local" value={form.fecha} onChange={update('fecha')} />
        <TextField label="Marca del glucómetro (opcional)" maxLength={100} value={form.marca} onChange={update('marca')} />
        <TextField label="Modelo del glucómetro (opcional)" maxLength={100} value={form.modelo} onChange={update('modelo')} />
      </div>
      <div className="form-actions">
        <SubmitButton loading={saving} loadingLabel="Guardando…" className="btn btn-outline">Registrar referencia</SubmitButton>
      </div>
    </form>
  );
}

function SendResult({ measurement, handleOperationError }) {
  const forPatient = measurement.envioResultado === 'PACIENTE';
  const [email, setEmail] = useState('');
  const [authorized, setAuthorized] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState('');

  async function handleSubmit(event) {
    event.preventDefault();
    if (sending) return;
    if (forPatient && (!email.trim() || !authorized)) {
      setError('Ingresá el correo que informó el paciente y confirmá que autorizó el envío.');
      return;
    }
    setSending(true);
    setError('');
    setDone('');
    try {
      const answer = await measurementsApi.sendResult(
        measurement.idMedicion, forPatient ? { correoDestino: email.trim(), pacienteAutoriza: true } : {},
      );
      setDone(`${answer.mensaje} (${answer.correoEnmascarado})`);
      setEmail('');
      setAuthorized(false);
    } catch (sendError) {
      setError(handleOperationError(sendError));
    } finally {
      setSending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate aria-label="Enviar resultado por correo">
      <p className="field-hint">
        {forPatient
          ? 'Si el paciente quiere recibir su resultado, ingresá el correo que te informó. Este envío puntual no lo guarda; para que reciba todos sus resultados, cargá su correo antes de medir.'
          : 'Podés recibir el resultado de esta medición en el correo de tu cuenta.'}
      </p>
      {error && <Alert>{error}</Alert>}
      {done && <Alert kind="info">{done}</Alert>}
      {forPatient && (
        <>
          <TextField label="Correo del paciente" type="email" maxLength={254} autoComplete="off" value={email}
            onChange={(event) => setEmail(event.target.value)} />
          <CheckField label="El paciente autorizó el envío de su resultado por correo." checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} />
        </>
      )}
      <div className="form-actions">
        <SubmitButton loading={sending} loadingLabel="Enviando…" className="btn btn-outline">
          <Mail size={16} aria-hidden="true" /> {forPatient ? 'Enviar resultado al paciente' : 'Enviarme el resultado por correo'}
        </SubmitButton>
      </div>
    </form>
  );
}

export function MeasurementPanel({ idMedicion, handleOperationError, onChanged, profileLabel = 'Mi perfil' }) {
  const [measurement, setMeasurement] = useState(null);
  const [error, setError] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [liveActive, setLiveActive] = useState(false);
  const inProgress = Boolean(measurement && measurement.puedeOperar
    && (measurement.estadoMedicion === 'PENDIENTE' || measurement.estadoMedicion === 'ADQUIRIENDO'));
  // Sesión de medición con el dispositivo (puente serie) asociada a ESTA medición, si la hay.
  const device = useDeviceStatus({ enabled: inProgress });
  const deviceSession = Boolean(device.status && !device.status.ocupado && device.status.sesion?.idMedicion === idMedicion);

  const load = useCallback(async () => {
    try {
      const loaded = await measurementsApi.getMeasurement(idMedicion);
      setMeasurement(loaded);
      setError('');
      return loaded;
    } catch (loadError) {
      setError(handleOperationError(loadError));
      return null;
    }
  }, [idMedicion, handleOperationError]);

  useEffect(() => {
    load();
  }, [load]);

  const active = measurement && ACTIVE_STATES.includes(measurement.estadoMedicion);
  useEffect(() => {
    if (!active) return undefined;
    const timer = setInterval(() => { load().then((loaded) => loaded && onChanged?.(loaded)); }, POLL_MS);
    return () => clearInterval(timer);
  }, [active, load, onChanged]);

  async function cancel() {
    setBusy(true);
    setError('');
    try {
      const cancelled = await measurementsApi.cancelMeasurement(idMedicion);
      setMeasurement(cancelled);
      setConfirming(false);
      onChanged?.(cancelled);
    } catch (cancelError) {
      setError(handleOperationError(cancelError));
    } finally {
      setBusy(false);
    }
  }

  async function removeDemo() {
    setBusy(true);
    setError('');
    try {
      await measurementsApi.deleteDemoMeasurement(idMedicion);
      setDeleted(true);
      onChanged?.(null);
    } catch (deleteError) {
      setError(handleOperationError(deleteError));
      setConfirmingDelete(false);
    } finally {
      setBusy(false);
    }
  }

  if (deleted) return <Alert kind="success">La medición de prueba se eliminó. Tus mediciones reales no se modificaron.</Alert>;
  if (error && !measurement) return <Alert>{error}</Alert>;
  if (!measurement) return <p className="field-hint" role="status">Cargando medición…</p>;

  const state = measurement.estadoMedicion;
  const glucose = measurement.modoMedicion === 'GLUCOSA_EXPERIMENTAL';
  const canCancel = measurement.puedeOperar && !liveActive && (state === 'PENDIENTE' || state === 'ADQUIRIENDO');

  const showNotice = state === 'COMPLETADA' && (glucose || measurement.origenGlucosa);
  const deviceName = [measurement.dispositivo.nombre, measurement.dispositivo.codigoDispositivo].filter(Boolean).join(' · ');

  return (
    <section className="panel measurement-detail" aria-labelledby="medicion-estado">
      <header className="md-hero">
        <span className="md-hero-icon">{glucose ? <Droplet size={30} aria-hidden="true" /> : <HeartPulse size={30} aria-hidden="true" />}</span>
        <div className="md-hero-body">
          <h2 id="medicion-estado">{MODES[measurement.modoMedicion]} · {formatDateTime(measurement.fechaHoraInicio)}</h2>
          <p>
            Estado: <Badge tone={state === 'COMPLETADA' ? 'success' : 'neutral'}>{STATES[state]}</Badge>{' '}
            {measurement.esDemo && <DemoBadge />}
          </p>
        </div>
        {showNotice && <span className="md-experimental"><Droplet size={16} aria-hidden="true" /> Uso experimental</span>}
      </header>
      {error && <Alert>{error}</Alert>}

      {measurement.esDemo && <Alert kind="info"><b>Medición de prueba (DEMO).</b> {DEMO_NOTICE}</Alert>}

      <dl className="detail-overview" aria-label="Datos generales de la medición">
        <div><span className="fact-icon"><CalendarDays size={20} aria-hidden="true" /></span><dt>Fecha y hora</dt><dd>{formatDateTime(measurement.fechaHoraInicio)}</dd></div>
        <div><span className="fact-icon"><Database size={20} aria-hidden="true" /></span><dt>Origen de los datos</dt><dd>{measurement.origenGlucosa ? (ORIGINS[measurement.origenGlucosa] ?? measurement.origenGlucosa) : 'Sin dato'}</dd></div>
        <div><span className="fact-icon"><Settings size={20} aria-hidden="true" /></span><dt>Modo</dt><dd>{MODES[measurement.modoMedicion]}</dd></div>
        <div><span className="fact-icon"><User size={20} aria-hidden="true" /></span><dt>Perfil asociado</dt><dd>{profileLabel}</dd></div>
        <div><span className="fact-icon"><Utensils size={20} aria-hidden="true" /></span><dt>Alimentación</dt><dd>{measurement.condicionComida === 'NO_INFORMADA' ? 'Sin informar' : (MEALS[measurement.condicionComida] ?? measurement.condicionComida)}</dd></div>
        {glucose && measurement.fechaHoraUltimaComida && ( // opcional: «Alimentación» ya dice si fue después de comer
          <div><span className="fact-icon"><Utensils size={20} aria-hidden="true" /></span><dt>Última comida</dt><dd>{formatDateTime(measurement.fechaHoraUltimaComida)}</dd></div>
        )}
        <div><span className="fact-icon"><Smartphone size={20} aria-hidden="true" /></span><dt>Dispositivo utilizado</dt><dd>{deviceName || 'Sin dato'}</dd></div>
        {glucose && measurement.matriz && (
          <div>
            <span className="fact-icon"><BookOpen size={20} aria-hidden="true" /></span>
            <dt>Matriz aplicada</dt>
            <dd>{`${measurement.matriz.nombre}, versión ${measurement.matriz.version} · ${measurement.matriz.ambito === 'INSTITUCION' ? 'Institucional' : 'Global'}`}</dd>
          </div>
        )}
      </dl>

      {deviceSession && (
        <DeviceSession status={device.status} profileLabel={profileLabel} handleOperationError={handleOperationError}
          onSaved={(saved) => { setMeasurement(saved); device.refresh(); onChanged?.(saved); }}
          onCancelled={(cancelled) => { setMeasurement(cancelled); device.refresh(); onChanged?.(cancelled); }} />
      )}
      {!deviceSession && (state === 'PENDIENTE' || state === 'ADQUIRIENDO') && measurement.puedeOperar && (
        <LiveAcquisition measurement={measurement} onLiveChange={setLiveActive}
          onUpdated={(updated) => { setMeasurement(updated); onChanged?.(updated); }} />
      )}
      {(state === 'PENDIENTE' || state === 'ADQUIRIENDO') && !measurement.puedeOperar && (
        <Alert kind="info">
          <Info size={16} aria-hidden="true" /> {state === 'PENDIENTE' ? 'Esperando datos del dispositivo.' : 'Recibiendo datos del dispositivo.'}{' '}
          Muestras recibidas: {measurement.cantidadMuestras}.
        </Alert>
      )}
      {state === 'PROCESANDO' && <Alert kind="info">Estamos procesando la medición. El resultado aparecerá en esta pantalla.</Alert>}
      {state === 'INVALIDA' && (
        <Alert>La medición no es válida y no se usa como resultado.{measurement.observacion ? ` ${measurement.observacion}` : ''}</Alert>
      )}
      {state === 'CANCELADA' && <Alert kind="info">La medición se canceló: no tiene resultados.</Alert>}
      {measurement.visibleHasta && (
        <Alert kind="info">
          Las mediciones canceladas o inválidas son temporales: esta se oculta de tu historial a las {measurement.visibleHasta.slice(11, 16)}.
        </Alert>
      )}

      {state === 'COMPLETADA' && (
        <section className="md-card" aria-labelledby="md-resultados">
          <div className="md-section-head">
            <h3 id="md-resultados" className="md-section-title"><ChartColumn size={22} aria-hidden="true" /> Resultados principales</h3>
            {(glucose || measurement.origenGlucosa) && <span className="md-pill"><Info size={15} aria-hidden="true" /> Valores estimados</span>}
          </div>
          <ul className="result-grid" aria-label="Resultados">
            {(measurement.glucosaEstimada !== null || (glucose && !measurement.origenGlucosa)) && (
              <ResultCard label="Glucosa estimada (experimental)" value={measurement.glucosaEstimada} unit="mg/dL" icon={Droplet} tone="rose" />
            )}
            {measurement.origenGlucosa && (
              <ResultCard label={measurement.esDemo ? 'Glucosa (valor DEMO, sintético)' : 'Glucosa experimental del dispositivo'}
                value={measurement.glucosaDispositivo} unit={measurement.unidadGlucosa ?? 'mg/dL'}
                empty="Sin dato (dispositivo sin calibrar)" badge={measurement.esDemo ? <DemoBadge /> : null} icon={Droplet} tone="rose"
                note={measurement.esDemo ? 'Simulación para verificar la comunicación: no es una glucemia real.' : null} />
            )}
            <ResultCard label="Frecuencia cardíaca" value={measurement.frecuenciaCardiaca} unit="lpm" icon={HeartPulse} tone="rose" />
            <ResultCard label="SpO₂" value={measurement.spo2} unit="%" icon={Wind} tone="blue" />
            {measurement.origenGlucosa && (
              <ResultCard label="Índice óptico (Beer-Lambert)" value={measurement.indiceOptico} format={formatIndex}
                note="Indicador óptico asociado al procesamiento del sensor." icon={Sparkles} tone="rose" />
            )}
            {measurement.calidadSenal !== null && <ResultCard label="Calidad de señal" value={measurement.calidadSenal} icon={Signal} tone="violet" />}
            {measurement.lecturasEstabilizadas !== null && (
              <ResultCard label="N.º de lecturas" value={measurement.lecturasEstabilizadas} note="(se guarda la mediana)" icon={FileText} tone="rose" />
            )}
          </ul>
          {measurement.origenGlucosa && (
            <p className="field-hint">
              Este resultado consolida las lecturas estables de la sesión (mediana): no se conservan las lecturas segundo a segundo, así
              que no hay una evolución temporal para graficar.
            </p>
          )}
        </section>
      )}
      {showNotice && <ExperimentalNotice variant="inline" />}
      {measurement.referenciaGlucosa && <GlucoseReferencePanel reference={measurement.referenciaGlucosa} />}

      {glucose && state === 'COMPLETADA' && (
        <details className="md-details">
          <summary>
            <span className="md-details-title"><FlaskConical size={22} aria-hidden="true" /> Referencia capilar</span>
            <span className="md-details-hint">{measurement.referenciaCapilar ? 'Registrada' : 'Opcional'}</span>
          </summary>
          <div className="md-details-body">
            <CapillaryReference measurement={measurement} handleOperationError={handleOperationError}
              onSaved={(updated) => { setMeasurement(updated); onChanged?.(updated); }} />
          </div>
        </details>
      )}

      {state === 'COMPLETADA' && measurement.envioResultado && (
        <details className="md-details">
          <summary>
            <span className="md-details-title"><Mail size={22} aria-hidden="true" /> Enviar resultado por correo</span>
          </summary>
          <div className="md-details-body">
            <SendResult measurement={measurement} handleOperationError={handleOperationError} />
          </div>
        </details>
      )}

      {measurement.puedeEliminar && (
        <div className="form-actions">
          {confirmingDelete ? (
            <>
              <span className="field-hint">¿Eliminar esta medición de prueba? No afecta a tus mediciones reales.</span>
              <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => setConfirmingDelete(false)}>Volver</button>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={removeDemo}>
                {busy && <span className="spinner" aria-hidden="true" />} Confirmar eliminación
              </button>
            </>
          ) : (
            <button type="button" className="btn btn-outline" onClick={() => setConfirmingDelete(true)}>
              <Trash2 size={16} aria-hidden="true" /> Eliminar medición de prueba
            </button>
          )}
        </div>
      )}

      {!showNotice && <p className="field-hint">{measurement.aviso}</p>}

      {canCancel && (
        <div className="form-actions">
          {confirming ? (
            <>
              <span className="field-hint">¿Cancelar esta medición? No tendrá resultados.</span>
              <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => setConfirming(false)}>Volver</button>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={cancel}>
                {busy && <span className="spinner" aria-hidden="true" />} Confirmar cancelación
              </button>
            </>
          ) : (
            <button type="button" className="btn btn-outline" onClick={() => setConfirming(true)}>
              <Ban size={16} aria-hidden="true" /> Cancelar medición
            </button>
          )}
        </div>
      )}
    </section>
  );
}
