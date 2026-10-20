// «Cómo realizar una medición»: guía de uso, con el tiempo de espera que corresponde al firmware (una lectura por segundo) y al
// criterio de estabilidad del backend (lecturas válidas consecutivas y parecidas). El acceso a medir solo se habilita cuando el
// diagnóstico del backend dice que el dispositivo está listo.

import { Hand } from 'lucide-react';
import { Link } from 'react-router-dom';

import { FINGER_TIPS, MEASUREMENT_STEPS } from './connectModel.js';

export function MeasurementGuide({ ready, individual, blockedBy, measureTo }) {
  return (
    <section className="panel connect-panel" aria-labelledby="guia-medicion">
      <div className="panel-title">
        <div>
          <h2 id="guia-medicion">3. Cómo realizar una medición</h2>
          <p>Una vez que el dispositivo esté listo, la medición se hace y se guarda en «Mis mediciones» (o en el historial del paciente, si sos operador/a).</p>
        </div>
      </div>
      <ol className="guide-steps plain" aria-label="Pasos para medir">
        {MEASUREMENT_STEPS.map((step, index) => (
          <li key={step.titulo} className="guide-step is-manual">
            <span className="guide-body"><b>{index + 1}. {step.titulo}</b><small>{step.detalle}</small></span>
          </li>
        ))}
      </ol>

      <div className="finger-guide">
        <h3><Hand size={18} aria-hidden="true" /> Cómo colocar el dedo en el MAX30100</h3>
        <ul>{FINGER_TIPS.map((tip) => <li key={tip}>{tip}</li>)}</ul>
        <p className="field-hint">
          Los datos DEMO son valores sintéticos para probar la integración: se identifican como DEMO y nunca se mezclan con las
          mediciones experimentales ni cuentan en las estadísticas.
        </p>
      </div>

      <div className="form-actions">
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
  );
}
