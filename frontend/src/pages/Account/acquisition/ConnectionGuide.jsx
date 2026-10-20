// Elección del medio (Bluetooth o USB) y su guía paso a paso. Los pasos que el backend puede comprobar llevan su marca real
// (correcto / con problema / pendiente); los que hace la persona se presentan como tales, sin aparentar una verificación.

import { Bluetooth, Hand, Usb } from 'lucide-react';

import { StateIcon } from './ConnectionStatusPanel.jsx';
import { MEDIA, guideSteps } from './connectModel.js';

const ICONS = { BLUETOOTH: Bluetooth, USB: Usb };
const STATE_CLASS = { OK: 'is-ok', ERROR: 'is-error', PENDIENTE: 'is-pending', MANUAL: 'is-manual' };
const STATE_LABEL = { OK: 'Comprobado', ERROR: 'Con problema', PENDIENTE: 'Pendiente', MANUAL: 'Lo hacés vos' };

export function ConnectionGuide({ medium, onMediumChange, status, readiness, institutional = false }) {
  const steps = guideSteps(medium, status, readiness, institutional);
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

      <h3 className="guide-title">Guía: {MEDIA[medium].label} ({MEDIA[medium].baud} baudios)</h3>
      <ol className="guide-steps" aria-label={`Pasos de la conexión por ${MEDIA[medium].label}`}>
        {steps.map((step, index) => (
          <li key={step.titulo} className={`guide-step ${STATE_CLASS[step.estado]}`}>
            <span className="guide-marker" aria-hidden="true">{step.estado === 'MANUAL' ? <Hand size={14} /> : <StateIcon state={step.estado} size={14} />}</span>
            <span className="guide-body">
              <b>{index + 1}. {step.titulo}</b>
              {step.detalle && <small>{step.detalle}</small>}
            </span>
            <span className="guide-state">{STATE_LABEL[step.estado]}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
