// Estado del dispositivo ANTES de medir, con las comprobaciones separadas (nunca una sola luz verde):
//   · Conexión     — el puente abrió el puerto (Bluetooth/USB), no significa que el Arduino esté identificado;
//   · Dispositivo  — el Arduino está identificado, registrado y asociado a quien mide (o falta confirmarlo);
//   · Sensor       — el sensor responde y llega telemetría reciente (puerto abierto no basta);
//   · Disponible   — todo lo anterior + nadie más está midiendo.
// Todo sale del diagnóstico del backend («readiness»): esta pantalla no lo infiere ni lo da por bueno si todavía no llegó.

import { Check, Circle, PlugZap, X } from 'lucide-react';
import { Link } from 'react-router-dom';

import { MEDIA, nextAction, readinessStep } from '../acquisition/connectModel.js';
import { AVAILABLE_TEXT } from './SharedDeviceBanner.jsx';

const STATE_LABEL = { OK: 'correcto', ERROR: 'con problema', PENDIENTE: 'pendiente' };

function worst(steps) {
  const present = steps.filter(Boolean);
  if (present.some((step) => step.estado === 'ERROR')) return 'ERROR';
  if (present.length === 0 || present.some((step) => step.estado !== 'OK')) return 'PENDIENTE';
  return 'OK';
}

/** Las cuatro comprobaciones con su estado y su texto (función pura, testeable). */
export function deviceChecks(status, readiness) {
  const bridge = status?.puente ?? null;
  const step = (id) => readinessStep(readiness, id);
  const medium = bridge ? (MEDIA[bridge.medio]?.label ?? bridge.medio) : null;
  const code = bridge?.codigoDispositivo ?? null;
  const loading = !readiness;

  const portStep = step('PUERTO');
  const connection = !bridge
    ? { state: 'ERROR', value: 'Puente detenido' }
    : loading ? { state: 'PENDIENTE', value: `${medium} · ${bridge.puerto ?? 'sin puerto'}: comprobando…` }
      : portStep?.estado === 'OK' ? { state: 'OK', value: `${medium} · ${bridge.puerto} abierto` }
        : portStep?.estado === 'ERROR' ? { state: 'ERROR', value: `${bridge.puerto ?? 'Puerto'} sin abrir` }
          : { state: 'PENDIENTE', value: 'Sin comprobar' };

  const deviceState = worst([step('IDENTIDAD'), step('REGISTRADO'), step('ASOCIADO')]);
  const device = loading ? { state: 'PENDIENTE', value: 'Comprobando…' }
    : deviceState === 'OK' ? { state: 'OK', value: `${code ?? 'Arduino'} identificado` }
      : deviceState === 'ERROR' ? { state: 'ERROR', value: 'No disponible para medir' }
        : { state: 'PENDIENTE', value: 'Sin confirmar' };

  const sensorStep = step('SENSOR');
  const sensor = loading ? { state: 'PENDIENTE', value: 'Comprobando…' }
    : sensorStep?.estado === 'OK' ? { state: 'OK', value: 'Responde' }
      : sensorStep?.estado === 'ERROR' ? { state: 'ERROR', value: 'Con error' }
        : { state: 'PENDIENTE', value: 'Sin comprobar' };

  const available = loading ? { state: 'PENDIENTE', value: 'Comprobando…' }
    : readiness.listo ? { state: 'OK', value: 'Listo para medir' }
      : status?.ocupado ? { state: 'ERROR', value: 'En uso por otra cuenta' }
        : { state: 'PENDIENTE', value: 'Todavía no' };

  return [
    { id: 'CONEXION', label: 'Conexión', ...connection },
    { id: 'DISPOSITIVO', label: 'Dispositivo', ...device },
    { id: 'SENSOR', label: 'Sensor', ...sensor },
    { id: 'DISPONIBLE', label: 'Disponibilidad', ...available },
  ];
}

const ICONS = { OK: Check, ERROR: X, PENDIENTE: Circle };

export function DeviceStatusChecks({ status, readiness }) {
  const checks = deviceChecks(status, readiness);
  const medium = status?.puente?.medio ?? 'BLUETOOTH';
  const action = readiness && !readiness.listo ? nextAction(status, readiness, medium) : null;
  return (
    <div className="device-status">
      <ul className="device-checks" aria-label="Estado del dispositivo">
        {checks.map((check) => {
          const Icon = ICONS[check.state];
          return (
            <li key={check.id} data-state={check.state.toLowerCase()}>
              <span className="check-dot"><Icon size={14} aria-hidden="true" /></span>
              <span className="check-text">
                <small>{check.label}</small>
                <b>{check.value}</b>
                <span className="sr-only"> ({STATE_LABEL[check.state]})</span>
              </span>
            </li>
          );
        })}
      </ul>
      {readiness?.listo && (
        <p className="field-hint" role="status"><b>{AVAILABLE_TEXT}</b>: conectado, identificado y operativo, listo para medir.</p>
      )}
      {action && (
        <div className={`connect-action is-${action.kind}`} role="status">
          <b>{action.kind === 'info' ? `Pendiente: ${action.title}` : action.title}</b>
          {action.detail && <p>{action.detail}</p>}
          {action.solution && <p><span className="connect-fix">Cómo resolverlo:</span> {action.solution}</p>}
          <p><Link to="/app/conectar-dispositivo"><PlugZap size={14} aria-hidden="true" /> Ver el estado de la conexión</Link></p>
        </div>
      )}
    </div>
  );
}
