// Adquisición en tiempo real de una medición PENDIENTE / ADQUIRIENDO. Habla solo con FastAPI: el backend (pySerial) recibe
// las muestras del Arduino, las guarda en SQL Server y las retransmite por SSE. Aquí NO se genera ninguna muestra ni
// resultado: los indicadores provisorios los calcula el servidor sobre la señal real y los definitivos salen al finalizar.

import { Ban, CircleCheck, PlugZap, Radio } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import * as acquisitionApi from '../../../api/acquisitionApi.js';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Alert } from '../../../components/FormControls.jsx';
import { SignalChart } from '../../../components/SignalChart.jsx';
import { formatNumber } from '../groups/groupFormat.js';

const KEEP = 300; // muestras recientes que se grafican (~12 s a 25 Hz)
const POLL_MS = 3000;

const DEVICE_STATES = { LISTO: 'Listo', ADQUIRIENDO: 'Adquiriendo', FINALIZADA: 'Finalizada', ERROR_SENSOR: 'Sensor desconectado' };

export function LiveAcquisition({ measurement, onUpdated, onLiveChange }) {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [signal, setSignal] = useState({ red: [], ir: [], count: 0, lastMs: 0 });
  const [indicators, setIndicators] = useState(null);
  const [deviceDone, setDeviceDone] = useState(false);
  const closeStream = useRef(null);

  const idMedicion = measurement.idMedicion;
  const session = status?.adquisicion && status.adquisicion.idMedicion === idMedicion ? status.adquisicion : null;
  const live = Boolean(session && session.estado !== 'FIN');

  const refresh = useCallback(async () => {
    try {
      setStatus(await acquisitionApi.getStatus());
    } catch (loadError) {
      setError(friendlyError(loadError));
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  useEffect(() => { onLiveChange?.(live); }, [live, onLiveChange]);

  // El avance en tiempo real llega por SSE mientras hay una sesión de esta medición.
  useEffect(() => {
    if (!live) return undefined;
    closeStream.current = acquisitionApi.openStream({
      onEvent: (event) => {
        if (event.tipo === 'muestra') {
          setSignal((current) => ({
            red: [...current.red, event.red].slice(-KEEP), ir: [...current.ir, event.ir].slice(-KEEP),
            count: current.count + 1, lastMs: event.t,
          }));
        } else if (event.tipo === 'indicadores') {
          setIndicators(event);
        } else if (event.tipo === 'fin') {
          setDeviceDone(true);
        } else if (event.tipo === 'error') {
          setError(event.mensaje ?? 'El dispositivo informó un error.');
          refresh();
        } else if (event.tipo === 'resultado' || (event.tipo === 'conexion' && !event.conectado)) {
          refresh();
        }
      },
      onError: () => {},
    });
    return () => closeStream.current?.();
  }, [live, refresh]);

  async function run(name, action) {
    setBusy(name);
    setError('');
    try {
      await action();
    } catch (actionError) {
      setError(friendlyError(actionError));
    } finally {
      setBusy('');
      refresh();
    }
  }

  const start = () => run('start', async () => {
    setSignal({ red: [], ir: [], count: 0, lastMs: 0 });
    setIndicators(null);
    setDeviceDone(false);
    setStatus(await acquisitionApi.startAcquisition(idMedicion));
  });
  const identify = () => run('identify', async () => setStatus(await acquisitionApi.identify()));
  const finish = () => run('finish', async () => onUpdated(await acquisitionApi.finishAcquisition()));
  const cancel = () => run('cancel', async () => onUpdated(await acquisitionApi.cancelAcquisition()));

  if (!status) return <p className="field-hint" role="status">Consultando el dispositivo…</p>;

  const connected = status.conectado && !status.ocupado;
  const device = status.dispositivo;
  const matchesDevice = device && measurement.dispositivo && device.codigo.toLowerCase() === measurement.dispositivo.codigoDispositivo.toLowerCase();

  return (
    <section className="live-acquisition" aria-label="Adquisición en tiempo real">
      <h3 className="member-list-title"><Radio size={16} aria-hidden="true" /> Adquisición con el Arduino</h3>
      {error && <Alert>{error}</Alert>}

      {status.ocupado && <Alert kind="info">Dispositivo temporalmente ocupado: otra cuenta está midiendo ahora. Reintentá en unos instantes.</Alert>}
      {!status.ocupado && !connected && (
        <Alert kind="info">
          No hay un Arduino conectado. <Link to="/app/conectar-dispositivo"><PlugZap size={14} aria-hidden="true" /> Conectar dispositivo</Link>{' '}
          (USB o Bluetooth HC-06) y volvé a esta pantalla.
        </Alert>
      )}

      {connected && !live && (
        <>
          <dl className="data-list" aria-label="Dispositivo conectado">
            <div><dt>Conexión</dt><dd>{status.puerto} · {status.medio === 'BLUETOOTH' ? 'Bluetooth HC-06' : 'USB'}</dd></div>
            <div><dt>Arduino identificado</dt><dd className={device ? undefined : 'is-empty'}>{device ? `${device.codigo} · ${device.sensor} · firmware ${device.firmware}` : 'Sin identificar'}</dd></div>
            <div><dt>Dispositivo de la medición</dt><dd>{measurement.dispositivo?.codigoDispositivo}</dd></div>
          </dl>
          {device && !matchesDevice && (
            <Alert>El Arduino conectado ({device.codigo}) no es el dispositivo elegido para esta medición ({measurement.dispositivo?.codigoDispositivo}).</Alert>
          )}
          <div className="form-actions">
            {!device && (
              <button type="button" className="btn btn-outline" disabled={Boolean(busy)} onClick={identify}>Identificar dispositivo</button>
            )}
            <button type="button" className="btn btn-primary" disabled={!matchesDevice || Boolean(busy)} onClick={start}>
              {busy === 'start' && <span className="spinner" aria-hidden="true" />} Iniciar adquisición
            </button>
          </div>
          <p className="field-hint">Apoyá el dedo sobre el sensor sin presionar de más y mantenelo quieto durante la medición.</p>
        </>
      )}

      {live && (
        <>
          <dl className="data-list" aria-label="Estado de la adquisición">
            <div><dt>Estado de conexión</dt><dd>Conectado · {status.puerto}</dd></div>
            <div><dt>Dispositivo y sensor</dt><dd>{device ? `${device.codigo} · ${device.sensor}` : '—'}</dd></div>
            <div><dt>Modo</dt><dd>{measurement.modoMedicion === 'GLUCOSA_EXPERIMENTAL' ? 'Glucosa (experimental)' : 'Oximetría'}</dd></div>
            <div><dt>Estado del dispositivo</dt><dd>{DEVICE_STATES[status.estadoDispositivo] ?? status.estadoDispositivo ?? '—'}</dd></div>
            <div><dt>Tiempo de adquisición</dt><dd>{(Math.max(signal.lastMs, (session.segundos ?? 0) * 1000) / 1000).toLocaleString('es-AR', { maximumFractionDigits: 1 })} s</dd></div>
            <div><dt>Muestras recibidas</dt><dd>{Math.max(signal.count, session.muestras)}</dd></div>
            <div><dt>Calidad de señal</dt><dd className={indicators?.calidad != null ? undefined : 'is-empty'}>{indicators?.calidad != null ? formatNumber(indicators.calidad) : 'Calculando…'}</dd></div>
            <div><dt>SpO₂ (provisorio)</dt><dd className={indicators?.spo2 != null ? undefined : 'is-empty'}>{indicators?.spo2 != null ? formatNumber(indicators.spo2, '%') : 'Sin datos disponibles'}</dd></div>
            <div><dt>Frecuencia cardíaca (provisoria)</dt><dd className={indicators?.frecuenciaCardiaca != null ? undefined : 'is-empty'}>{indicators?.frecuenciaCardiaca != null ? formatNumber(indicators.frecuenciaCardiaca, 'lpm') : 'Sin datos disponibles'}</dd></div>
          </dl>
          {indicators?.motivo && <p className="field-hint">{indicators.motivo}</p>}
          <SignalChart title="Canal rojo (RED)" samples={signal.red} color="#d6283b" />
          <SignalChart title="Canal infrarrojo (IR)" samples={signal.ir} color="#4b5563" />
          {session.estado === 'ERROR' && <Alert>{session.error ?? 'La adquisición se interrumpió.'} Finalizá para conservar lo recibido.</Alert>}
          {deviceDone && session.estado !== 'ERROR' && <Alert kind="info"><CircleCheck size={14} aria-hidden="true" /> El dispositivo terminó de adquirir. Finalizá para procesar la señal.</Alert>}
          <div className="form-actions">
            <button type="button" className="btn btn-primary" disabled={Boolean(busy) || Math.max(signal.count, session.muestras) === 0} onClick={finish}>
              {busy === 'finish' && <span className="spinner" aria-hidden="true" />} Finalizar y procesar
            </button>
            <button type="button" className="btn btn-outline" disabled={Boolean(busy)} onClick={cancel}>
              <Ban size={16} aria-hidden="true" /> Cancelar adquisición
            </button>
          </div>
          <p className="field-hint">Los valores en vivo son provisorios; el resultado oficial lo calcula el servidor al finalizar.</p>
        </>
      )}
    </section>
  );
}
