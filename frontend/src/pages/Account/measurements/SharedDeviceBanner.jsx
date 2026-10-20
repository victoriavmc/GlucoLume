// El Arduino es compartido entre todas las cuentas: solo está "ocupado" mientras OTRA cuenta tiene una adquisición activa.
// Una asociación previa, una sesión abandonada o una reserva vencida no lo bloquean (el backend las libera).

import { RefreshCw } from 'lucide-react';

import { Alert } from '../../../components/FormControls.jsx';

export const BUSY_TEXT = 'Dispositivo temporalmente ocupado: otra cuenta está midiendo ahora.';
export const AVAILABLE_TEXT = 'Dispositivo compartido disponible';

export function SharedDeviceBanner({ status, onRetry }) {
  if (!status) return null;
  if (status.ocupado) {
    return (
      <Alert kind="info">
        {BUSY_TEXT} Cuando termine, el equipo queda libre para vos.{' '}
        {onRetry && (
          <button type="button" className="btn btn-ghost" onClick={onRetry}>
            <RefreshCw size={14} aria-hidden="true" /> Reintentar
          </button>
        )}
      </Alert>
    );
  }
  if (status.estado === 'CONECTADO' && !status.sesion) {
    return <p className="field-hint" role="status"><b>{AVAILABLE_TEXT}</b>: conectado y operativo, listo para medir.</p>;
  }
  return null;
}
