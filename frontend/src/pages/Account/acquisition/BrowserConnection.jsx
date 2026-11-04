// Conexión del Arduino DESDE ESTE NAVEGADOR (Web Serial), sin instalar el puente. El navegador abre el puerto en solo lectura (nunca escribe en el
// Arduino) y le entrega al backend las mismas líneas que leería el puente; lo demás (identidad, lecturas, control, sesión) es igual que con el puente.
// Funciona en Chrome o Edge de escritorio. La conexión vive fuera de esta pantalla (utils/browserSerialLink.js): sigue activa al ir a «Mis mediciones».

import { Plug, Unplug } from 'lucide-react';

import { Alert } from '../../../components/FormControls.jsx';
import { STATES, useBrowserLink } from '../../../utils/browserSerialLink.js';
import { BridgeInstallSteps } from './BridgeSettings.jsx';
import { MEDIA } from './connectModel.js';

export function BrowserConnection({ status, medium }) {
  const link = useBrowserLink();
  const physical = MEDIA[medium] ? medium : 'USB';
  const info = MEDIA[physical];
  const others = status?.puente?.origen === 'NAVEGADOR' && !status.puente.propio;
  const connected = link.estado === STATES.CONNECTED;
  const connecting = link.estado === STATES.CONNECTING;

  return (
    <section className="panel connect-panel" aria-labelledby="conexion-navegador">
      <div className="panel-title">
        <div>
          <h2 id="conexion-navegador">2. Conectar el Arduino desde este navegador</h2>
          <p>Sin instalar nada: el navegador lee el Arduino por el cable USB o por el Bluetooth ya emparejado y se lo entrega a GlucoLume.</p>
        </div>
      </div>

      {link.error && <Alert>{link.error}</Alert>}
      {others && <Alert kind="info">Otra cuenta tiene el dispositivo conectado desde su navegador: cuando lo desconecte vas a poder usarlo.</Alert>}
      {connected && (
        <Alert kind="success">
          Leyendo el Arduino desde este navegador ({link.puerto}, {info.baud} baudios). Podés ir a «Mis mediciones» sin desconectar; si cerrás o
          recargás la pestaña, la conexión se corta.
        </Alert>
      )}

      <div className="form-actions">
        {connected ? (
          <button type="button" className="btn btn-outline" onClick={() => link.disconnect()}>
            <Unplug size={16} aria-hidden="true" /> Desconectar el Arduino
          </button>
        ) : (
          <button type="button" className="btn btn-primary" disabled={connecting || others} onClick={() => link.connect(physical)}>
            {connecting ? <span className="spinner" aria-hidden="true" /> : <Plug size={16} aria-hidden="true" />} Conectar Arduino por {info.label}
          </button>
        )}
      </div>
      {!connected && (
        <p className="field-hint">
          {physical === 'BLUETOOTH'
            ? 'Antes emparejá el HC-05/HC-06 en el sistema (PIN 1234 o 0000). El navegador te muestra una lista: elegí el puerto del módulo («Standard Serial over Bluetooth link»).'
            : 'Conectá el Arduino con un cable USB de datos. El navegador te muestra una lista de puertos: elegí el del Arduino (por ejemplo «Arduino Uno»).'}
          {' '}Solo lee: GlucoLume nunca escribe en el Arduino. Si no aparece ninguno, revisá el cable o el controlador.
        </p>
      )}

      <details className="connect-alt">
        <summary>¿Preferís instalar el puente en la computadora?</summary>
        <BridgeInstallSteps />
      </details>
    </section>
  );
}
