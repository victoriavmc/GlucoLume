// Configuración del puente local. El navegador NO puede abrir puertos COM ni ejecutar programas: lo que se ofrece acá es
// únicamente lo que el puente sí puede aplicar cuando GlucoLume se lo pide (a través del backend autenticado y con una lista
// cerrada de órdenes): elegir un puerto entre los que el propio puente ve, pausar/reanudar, detener y reiniciar. Iniciar el
// puente desde cero es una acción local: se explica cómo, sin botones que no funcionen.
// El dispositivo es compartido (DEC-01): solo da órdenes la cuenta que tiene su control temporal, que se toma con «Usar dispositivo».

import { Pause, Play, Power, RefreshCw } from 'lucide-react';
import { useEffect, useState } from 'react';

import * as acquisitionApi from '../../../api/acquisitionApi.js';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Alert, RadioField } from '../../../components/FormControls.jsx';
import { copyText } from '../../../utils/clipboard.js';
import { LOCAL_COMMANDS, MEDIA, bridgeRunning, portsOf } from './connectModel.js';

const AUTO_MEDIUM = 'AUTO'; // modo automático: el puente busca el GlucoLume por USB y Bluetooth (sin puerto)
const ACTION_LABELS = { CONFIGURAR: 'Aplicar la configuración', PAUSAR: 'Pausar', REANUDAR: 'Reanudar', DETENER: 'Detener', REINICIAR: 'Reiniciar' };

function Command({ text }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    setCopied(await copyText(text));
  }
  return (
    <div className="command-line">
      <code>{text}</code>
      <button type="button" className="btn btn-ghost" onClick={copy}>{copied ? 'Copiado' : 'Copiar'}</button>
    </div>
  );
}

function describePort(port) {
  const tags = [port.esBluetooth && 'Bluetooth', port.esArduino && 'Arduino/USB'].filter(Boolean).join(', ');
  const warning = port.estadoWindows && port.estadoWindows !== 'OK' ? ` ⚠ Windows: ${port.estadoWindows}` : '';
  return `${port.puerto}${port.descripcion ? ` — ${port.descripcion}` : ''}${tags ? ` [${tags}]` : ''}${warning}`;
}

export function BridgeSettings({ status, medium, onMediumChange, onChanged, authority }) {
  const running = bridgeRunning(status);
  const bridge = status?.puente;
  const ports = portsOf(status);
  const [port, setPort] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [confirming, setConfirming] = useState('');
  const measuring = Boolean(status?.sesion);
  const controlling = Boolean(status?.controlPropio);
  const takenByOther = Boolean(status?.ocupado);
  const paused = bridge?.estadoEnlace === 'PAUSADO';
  const pending = Boolean(bridge?.comandoPendiente);

  // Preselecciona el puerto con el que ya está leyendo el puente (si el sistema lo sigue mostrando).
  useEffect(() => {
    if (!bridge?.puerto) return;
    setPort((current) => (current && ports.some((item) => item.puerto === current) ? current : (ports.some((item) => item.puerto === bridge.puerto) ? bridge.puerto : '')));
  }, [bridge?.puerto, ports.length]); // eslint-disable-line react-hooks/exhaustive-deps

  async function send(accion, extra = {}) {
    setBusy(accion);
    setError('');
    setConfirming('');
    try {
      await acquisitionApi.sendBridgeCommand({ accion, ...extra });
      onChanged?.();
    } catch (sendError) {
      setError(friendlyError(sendError));
    } finally {
      setBusy('');
    }
  }

  async function control(take) {
    setBusy(take ? 'TOMAR' : 'SOLTAR');
    setError('');
    setConfirming('');
    try {
      await (take ? acquisitionApi.takeDeviceControl() : acquisitionApi.releaseDeviceControl());
      onChanged?.();
    } catch (controlError) {
      setError(friendlyError(controlError));
    } finally {
      setBusy('');
    }
  }

  if (!running) {
    return (
      <section className="panel connect-panel" aria-labelledby="config-puente">
        <div className="panel-title">
          <div>
            <h2 id="config-puente">2. Puente de GlucoLume en esta computadora</h2>
            <p>El puente es el programa que lee el puerto COM y se lo entrega a GlucoLume.</p>
          </div>
        </div>
        <Alert kind="info">
          El puente no está ejecutándose. El navegador no puede iniciar programas de tu computadora, por eso este paso se hace
          en el equipo, una sola vez.
        </Alert>
        <ol className="plain-steps">
          <li><b>Primera vez (instalación guiada):</b> hacé doble clic en <code>{LOCAL_COMMANDS.install}</code> (carpeta <code>acquisition\bridge</code>).
            Te pregunta si usás Bluetooth o USB, te deja elegir el puerto COM y comprueba el servidor y el dispositivo.</li>
          <li><b>Después:</b> abrí <code>{LOCAL_COMMANDS.menu}</code> y elegí «Iniciar el puente», o activá allí el inicio automático al abrir sesión.
            El puente se ejecuta sin ventana.</li>
          <li><b>Por línea de comandos</b> (alternativa):</li>
        </ol>
        <Command text={LOCAL_COMMANDS.start} />
        <p className="field-hint">Para detenerlo en cualquier momento: opción «Detener el puente» del mismo menú, o el botón de esta pantalla cuando esté ejecutándose.</p>
      </section>
    );
  }

  const candidates = [...ports].sort((a, b) => Number(medium === 'BLUETOOTH' ? b.esBluetooth : b.esArduino) - Number(medium === 'BLUETOOTH' ? a.esBluetooth : a.esArduino));
  const last = bridge.ultimoComando;
  // El backend resuelve quién puede dar órdenes según a quién pertenece el dispositivo (readiness.ordenesPuente): acá solo se refleja.
  const blocked = authority && !authority.permitido ? authority.motivo : '';
  const controlReason = takenByOther ? 'Otra cuenta está usando el dispositivo: vas a poder usarlo cuando lo libere.'
    : !controlling ? 'Tocá «Usar dispositivo» para darle órdenes al puente.' : '';
  const disabledReason = blocked || controlReason || (measuring ? 'Hay una sesión de medición en curso: guardala o cancelala antes de cambiar el puente.' : pending ? 'Esperando que el puente tome la orden anterior…' : '');

  return (
    <section className="panel connect-panel" aria-labelledby="config-puente">
      <div className="panel-title">
        <div>
          <h2 id="config-puente">2. Configuración del puente</h2>
          <p>El puente corre en tu computadora y aplica estos cambios. GlucoLume solo se los pide.</p>
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      {last && <Alert kind={last.ok ? 'success' : 'error'}>{last.mensaje ?? (last.ok ? 'Orden aplicada.' : 'La orden no se pudo aplicar.')}</Alert>}
      {pending && <Alert kind="info">Orden «{ACTION_LABELS[bridge.comandoPendiente]}» enviada: el puente la aplica en unos segundos.</Alert>}

      {!blocked && !takenByOther && (
        <div className="form-actions" role="group" aria-label="Uso del dispositivo">
          {!controlling && (
            <button type="button" className="btn btn-primary" disabled={Boolean(busy)} onClick={() => control(true)}>
              {busy === 'TOMAR' ? <span className="spinner" aria-hidden="true" /> : null} Usar dispositivo
            </button>
          )}
          {controlling && !measuring && (
            <button type="button" className="btn btn-ghost" disabled={Boolean(busy)} onClick={() => control(false)}>Dejar de usar</button>
          )}
        </div>
      )}

      <div className="bridge-form">
        <fieldset className="field" aria-label="Medio de conexión del puente">
          <legend className="field-label">Medio</legend>
          {Object.entries(MEDIA).map(([key, info]) => (
            <RadioField key={key} name="medio-puente" label={`${info.label} (${info.baud} baudios)`} checked={medium === key} onChange={() => onMediumChange(key)} />
          ))}
          <RadioField name="medio-puente" label="Automático (USB o Bluetooth, sin elegir puerto)" checked={medium === AUTO_MEDIUM} onChange={() => onMediumChange(AUTO_MEDIUM)} />
        </fieldset>
        {medium !== AUTO_MEDIUM && <div className="field">
          <label className="field-label" htmlFor="puerto-puente">Puerto COM</label>
          <select id="puerto-puente" className="field-input field-select" value={port} onChange={(event) => setPort(event.target.value)}>
            <option value="">{candidates.length ? 'Elegí un puerto de la lista' : 'El puente no ve ningún puerto'}</option>
            {candidates.map((item) => <option key={item.puerto} value={item.puerto}>{describePort(item)}</option>)}
          </select>
          <span className="field-hint">Solo figuran los puertos que Windows muestra en esta computadora. Velocidad: {MEDIA[medium].baud} baudios (automática).</span>
        </div>}
        <div className="form-actions">
          <button type="button" className="btn btn-primary" disabled={(medium !== AUTO_MEDIUM && !port) || Boolean(busy) || Boolean(disabledReason)}
            onClick={() => send('CONFIGURAR', medium === AUTO_MEDIUM ? { medio: AUTO_MEDIUM } : { puerto: port, medio: medium })}>
            {busy === 'CONFIGURAR' ? <span className="spinner" aria-hidden="true" /> : null} {medium === AUTO_MEDIUM ? 'Aplicar modo automático' : 'Aplicar puerto y medio'}
          </button>
        </div>
      </div>

      <div className="bridge-controls" role="group" aria-label="Control del puente">
        {paused
          ? <button type="button" className="btn btn-outline" disabled={Boolean(busy) || pending || !controlling} onClick={() => send('REANUDAR')}><Play size={16} aria-hidden="true" /> Reanudar lectura</button>
          : <button type="button" className="btn btn-outline" disabled={Boolean(busy) || Boolean(disabledReason)} onClick={() => send('PAUSAR')}><Pause size={16} aria-hidden="true" /> Pausar lectura (liberar el puerto)</button>}
        <button type="button" className="btn btn-outline" disabled={Boolean(busy) || Boolean(disabledReason)} onClick={() => setConfirming('REINICIAR')}>
          <RefreshCw size={16} aria-hidden="true" /> Reiniciar puente
        </button>
        <button type="button" className="btn btn-ghost danger" disabled={Boolean(busy) || Boolean(disabledReason)} onClick={() => setConfirming('DETENER')}>
          <Power size={16} aria-hidden="true" /> Detener puente
        </button>
      </div>
      {disabledReason && <p className="field-hint" role="status">{disabledReason}</p>}
      {confirming && (
        <div className="connect-confirm" role="alertdialog" aria-label={`Confirmar: ${ACTION_LABELS[confirming]} el puente`}>
          <p>
            {confirming === 'DETENER'
              ? 'Se detiene la lectura y se libera el puerto COM. Para volver a iniciarlo hay que hacerlo en esta computadora (menú del puente o inicio automático).'
              : 'El puente se cierra y se vuelve a abrir solo, con la misma configuración.'}
          </p>
          <div className="form-actions">
            <button type="button" className="btn btn-primary" onClick={() => send(confirming)}>{confirming === 'DETENER' ? 'Detener' : 'Reiniciar'}</button>
            <button type="button" className="btn btn-ghost" onClick={() => setConfirming('')}>Cancelar</button>
          </div>
        </div>
      )}
    </section>
  );
}
