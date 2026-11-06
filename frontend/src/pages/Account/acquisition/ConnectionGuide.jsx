// Elección del medio de conexión (Bluetooth o USB). La guía paso a paso se quitó de esta pantalla: el medio elegido
// sigue determinando la velocidad y el tipo de puerto que usan el puente y la conexión desde el navegador.

import { Bluetooth, Usb } from 'lucide-react';

import { MEDIA } from './connectModel.js';

const ICONS = { BLUETOOTH: Bluetooth, USB: Usb };

export function ConnectionGuide({ medium, onMediumChange }) {
  return (
    <section className="panel connect-panel" aria-labelledby="guia-conexion">
      <div className="panel-title">
        <div>
          <h2 id="guia-conexion">1. Elegí cómo conectar el Arduino</h2>
          <p>Las dos opciones usan el mismo firmware (GlucoLume_MAX30100.ino): no hay nada que cambiar en el Arduino.</p>
        </div>
      </div>

      <div className="medium-options" role="radiogroup" aria-label="Tipo de conexión">
        {Object.entries(MEDIA).map(([key, info]) => {
          const Icon = ICONS[key];
          return (
            <label key={key} className={`medium-card${medium === key ? ' is-selected' : ''}`}>
              <input type="radio" name="medio" value={key} checked={medium === key} onChange={() => onMediumChange(key)} />
              <Icon size={22} aria-hidden="true" />
              <span><b>Conexión por {info.label}</b><small>{info.device} · {info.baud} baudios</small></span>
            </label>
          );
        })}
      </div>
    </section>
  );
}
