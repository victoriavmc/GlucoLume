// «Cómo realizar una medición»: guía de uso, con el tiempo de espera que corresponde al firmware (una lectura por segundo) y al
// criterio de estabilidad del backend (lecturas válidas consecutivas y parecidas). El acceso a medir solo se habilita cuando el
// diagnóstico del backend dice que el dispositivo está listo.

import { BarChart3, ChevronDown, Hand, Info } from 'lucide-react';
import { Link } from 'react-router-dom';

import { FINGER_TIPS, IMPORTANT_NOTES, MEASUREMENT_STEPS } from './connectModel.js';

/** Dibujo esquemático del MAX30100 con el dedo encima: el sensor se ilumina en rojo a través de la yema. */
function FingerSensor() {
  return (
    <svg className="finger-sensor" viewBox="0 0 220 180" role="img" aria-label="Dedo cubriendo el sensor MAX30100">
      <defs>
        <radialGradient id="finger-glow" cx="50%" cy="60%" r="60%">
          <stop offset="0%" stopColor="#ff5a5f" stopOpacity="0.95" />
          <stop offset="100%" stopColor="#e3101e" stopOpacity="0.55" />
        </radialGradient>
      </defs>
      <rect x="40" y="96" width="140" height="70" rx="10" fill="#14201c" />
      <rect x="82" y="108" width="56" height="40" rx="4" fill="#2b3a35" />
      <circle cx="158" cy="124" r="3" fill="#e3101e" />
      <circle cx="158" cy="138" r="3" fill="#ff8a8f" />
      <path d="M96 116 Q110 100 124 116 L130 150 Q110 160 92 150 Z" fill="url(#finger-glow)" opacity="0.85" />
      <path
        d="M86 150 L84 58 Q84 16 110 14 Q136 16 136 58 L138 150 Q112 168 86 150 Z"
        fill="#e9b49c"
        stroke="#c98f76"
        strokeWidth="2"
      />
      <path d="M94 62 Q110 50 126 62" fill="none" stroke="#d99c84" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function MeasurementGuide({ ready, individual, blockedBy, measureTo }) {
  return (
    <div className="measure-grid">
      <section className="panel connect-panel measure-panel" aria-labelledby="guia-medicion">
        <div className="panel-title">
          <div>
            <h2 id="guia-medicion" className="measure-title">
              <BarChart3 size={22} aria-hidden="true" /> 3. Cómo realizar una medición
            </h2>
            <p>Una vez que el dispositivo esté listo, la medición se hace y se guarda en «Mis mediciones» (o en el historial del paciente, si sos operador/a).</p>
          </div>
        </div>

        <ol className="measure-steps" aria-label="Pasos para medir">
          {MEASUREMENT_STEPS.map((step, index) => (
            <li key={step.titulo}>
              <details className="measure-step">
                <summary>
                  <span className="measure-num" aria-hidden="true">{index + 1}</span>
                  <span className="measure-step-title">{step.titulo}</span>
                  <ChevronDown className="measure-chevron" size={18} aria-hidden="true" />
                </summary>
                <p>{step.detalle}</p>
              </details>
            </li>
          ))}
        </ol>

        <div className="form-actions measure-actions">
          {ready ? (
            <Link to={measureTo ?? (individual ? '/app/mediciones' : '/app/instituciones')} className="btn btn-primary">
              {individual ? 'Ir a «Mis mediciones» para medir' : 'Ir a mis pacientes para medir'}
            </Link>
          ) : (
            <>
              <button type="button" className="btn btn-primary" disabled aria-describedby="medir-bloqueo">Medir todavía no está disponible</button>
              <span className="field-hint" id="medir-bloqueo">{blockedBy ?? 'Resolvé el primer paso pendiente del estado de la conexión.'}</span>
            </>
          )}
        </div>
      </section>

      <div className="measure-side">
        <section className="measure-card finger-card" aria-labelledby="guia-dedo">
          <h3 id="guia-dedo"><Hand size={22} aria-hidden="true" /> Cómo colocar el dedo en el MAX30100</h3>
          <div className="finger-body">
            <FingerSensor />
            <ul className="finger-tips">
              {FINGER_TIPS.map((tip) => <li key={tip}>{tip}</li>)}
            </ul>
          </div>
        </section>

        <aside className="measure-card important-card" aria-labelledby="guia-importante">
          <h3 id="guia-importante"><Info size={22} aria-hidden="true" /> Importante</h3>
          <ul>
            {IMPORTANT_NOTES.map((note) => <li key={note}>{note}</li>)}
          </ul>
        </aside>
      </div>
    </div>
  );
}
