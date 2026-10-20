// Aviso compacto de «qué falta para poder medir», para «Medir con el dispositivo» y «Nueva medición». Usa el mismo diagnóstico
// del backend que «Conectar dispositivo» (una sola fuente), explica el primer paso pendiente y enlaza a la página de conexión.
// Mientras carga (o si el diagnóstico falla) muestra `children` como alternativa; si el dispositivo está listo no muestra nada.

import { PlugZap } from 'lucide-react';
import { Link } from 'react-router-dom';

import { nextAction } from './connectModel.js';
import { useDeviceReadiness } from './useDeviceReadiness.js';

export function DeviceReadinessHint({ idPerfilMedicion, status, children = null }) {
  const { readiness } = useDeviceReadiness(idPerfilMedicion, status);
  if (!readiness) return children;
  if (readiness.listo) return null;
  const action = nextAction(status, readiness, status?.puente?.medio ?? 'BLUETOOTH');
  return (
    <div className={`connect-action is-${action.kind}`} role="status">
      <b>{action.title}</b>
      {action.detail && <p>{action.detail}</p>}
      {action.solution && <p><span className="connect-fix">Cómo resolverlo:</span> {action.solution}</p>}
      <p><Link to="/app/conectar-dispositivo"><PlugZap size={14} aria-hidden="true" /> Ver el estado de la conexión</Link></p>
    </div>
  );
}
