// Casilla «Leí la Política de Privacidad» (sin marcar al inicio). El enlace abre /privacidad en otra pestaña para no
// perder lo que la persona ya escribió. La obligatoriedad también la valida el backend (POLITICA_NO_ACEPTADA).

import { Link } from 'react-router-dom';

import { CheckField } from './FormControls.jsx';

export function PolicyConsent({ checked, onChange, error, disabled = false }) {
  return (
    <div className="policy-consent">
      <CheckField
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        disabled={disabled}
        aria-describedby={error ? 'policy-consent-error' : undefined}
        label={(
          <span>
            Leí la{' '}
            <Link to="/privacidad" target="_blank" rel="noopener noreferrer">Política de Privacidad</Link>.
          </span>
        )}
      />
      {error && <p className="field-error" id="policy-consent-error" role="alert">{error}</p>}
    </div>
  );
}

export const POLICY_REQUIRED_MESSAGE = 'Para continuar tenés que confirmar que leíste la Política de Privacidad.';
