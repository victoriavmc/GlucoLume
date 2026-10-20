// Estado REAL de la conexión: cuatro etapas distintas (emparejado, puerto abierto, telemetría, disponible) más los indicadores
// pedidos y la acción siguiente. Todo sale del backend (estado en vivo + diagnóstico); un puerto abierto nunca basta para «listo».

import { Check, Circle, X } from 'lucide-react';

import { SharedDeviceBanner } from '../measurements/SharedDeviceBanner.jsx';
import { indicators, nextAction, pipeline } from './connectModel.js';

const LABELS = { OK: 'correcto', ERROR: 'con problema', PENDIENTE: 'pendiente', MANUAL: 'a cargo de la persona' };
const STATE_CLASS = { OK: 'is-ok', ERROR: 'is-error', PENDIENTE: 'is-pending', MANUAL: 'is-manual' };

export function StateIcon({ state, size = 16 }) {
  if (state === 'OK') return <Check size={size} aria-hidden="true" />;
  if (state === 'ERROR') return <X size={size} aria-hidden="true" />;
  return <Circle size={size} aria-hidden="true" />;
}

export function ConnectionStatusPanel({ status, readiness, medium, onRetry, institutional = false }) {
  const stages = pipeline(status, readiness, medium);
  const rows = indicators(status, readiness, institutional);
  const action = nextAction(status, readiness, medium);

  return (
    <section className="panel connect-panel" aria-labelledby="estado-conexion">
      <div className="panel-title">
        <div>
          <h2 id="estado-conexion">Estado de la conexión</h2>
          <p>Se actualiza solo. Cada etapa se comprueba por separado.</p>
        </div>
      </div>

      <SharedDeviceBanner status={status} onRetry={onRetry} />

      <ol className="stage-strip" aria-label="Etapas de la conexión">
        {stages.map((stage) => (
          <li key={stage.id} className={`stage ${STATE_CLASS[stage.state]}`}>
            <span className="stage-dot"><StateIcon state={stage.state} /></span>
            <span className="stage-text">
              <b>{stage.title}</b>
              <small>{stage.hint}</small>
              <span className="visually-hidden"> ({LABELS[stage.state]})</span>
            </span>
          </li>
        ))}
      </ol>

      <div className={`connect-action is-${action.kind}`} role="status">
        <b>{action.title}</b>
        {action.detail && <p>{action.detail}</p>}
        {action.solution && <p><span className="connect-fix">Cómo resolverlo:</span> {action.solution}</p>}
      </div>

      <dl className="indicator-grid" aria-label="Indicadores de la conexión">
        {rows.map((row) => (
          <div key={row.id} className={`indicator ${STATE_CLASS[row.state]}`}>
            <dt>{row.label}</dt>
            <dd>
              <span className="indicator-icon"><StateIcon state={row.state} size={14} /></span>
              {row.value}
              <span className="visually-hidden"> ({LABELS[row.state]})</span>
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
