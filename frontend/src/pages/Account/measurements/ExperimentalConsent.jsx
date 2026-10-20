// Autorización expresa para almacenar las mediciones experimentales de la persona (separada de la confirmación de la
// Política de Privacidad del registro). Sin ella el backend no inicia ni recibe mediciones (CONSENTIMIENTO_REQUERIDO).
// La persona puede rechazar o revocar cuando quiera; revocar frena nuevas recolecciones y no borra lo ya medido.

import { ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import * as authApi from '../../../api/authApi.js';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Alert } from '../../../components/FormControls.jsx';

/** `consent`: { aceptado, ... } de GET /auth/consents (DATOS_EXPERIMENTALES). `onChange` recibe el estado actualizado. */
export function ExperimentalConsent({ consent, onChange }) {
  const [busy, setBusy] = useState(false);
  const [declined, setDeclined] = useState(false);
  const [error, setError] = useState('');

  async function decide(accept) {
    setBusy(true);
    setError('');
    try {
      const updated = await authApi.setExperimentalConsent(accept);
      setDeclined(false);
      onChange(updated.DATOS_EXPERIMENTALES);
    } catch (decisionError) {
      setError(friendlyError(decisionError));
    } finally {
      setBusy(false);
    }
  }

  if (consent.aceptado) {
    return (
      <section className="panel consent-panel" aria-labelledby="consent-title">
        <div className="consent-status">
          <p id="consent-title">
            <ShieldCheck size={16} aria-hidden="true" style={{ display: 'inline', verticalAlign: '-3px' }} /> Autorizaste el
            almacenamiento de tus mediciones experimentales. Podés revocarlo cuando quieras: no se iniciarán nuevas mediciones
            (lo ya medido se conserva hasta que elimines tu cuenta).
          </p>
          <button type="button" className="btn btn-outline" onClick={() => decide(false)} disabled={busy}>
            {busy ? 'Revocando…' : 'Revocar autorización'}
          </button>
        </div>
        {error && <Alert>{error}</Alert>}
      </section>
    );
  }

  return (
    <section className="panel consent-panel" aria-labelledby="consent-title">
      <div className="panel-title">
        <span className="panel-icon"><ShieldCheck size={22} aria-hidden="true" /></span>
        <div>
          <h2 id="consent-title">Autorización para almacenar tus mediciones</h2>
          <p>Para medir necesitamos tu autorización expresa.</p>
        </div>
      </div>
      <ul>
        <li>
          Las mediciones (señal del sensor, SpO₂, frecuencia cardíaca y la estimación experimental de glucosa) se guardan
          asociadas a tu cuenta, junto con tu edad y sexo al momento de medir.
        </li>
        <li>
          La finalidad es <strong>exclusivamente académica y experimental</strong>: evaluar el prototipo. No forman parte de
          una historia clínica y no se usan para diagnóstico ni tratamiento.
        </li>
        <li>
          Podés rechazar esta autorización (no se recolectará ninguna medición) o revocarla después. Más información en la{' '}
          <Link to="/privacidad" target="_blank" rel="noopener noreferrer">Política de Privacidad</Link>.
        </li>
      </ul>
      {declined && (
        <Alert kind="info">
          No autorizaste el almacenamiento: no se recolectará ninguna medición. Podés cambiar de decisión cuando quieras.
        </Alert>
      )}
      {error && <Alert>{error}</Alert>}
      <div className="consent-actions">
        <button type="button" className="btn btn-primary" onClick={() => decide(true)} disabled={busy}>
          {busy ? 'Guardando…' : 'Autorizo el almacenamiento'}
        </button>
        <button type="button" className="btn btn-outline" onClick={() => setDeclined(true)} disabled={busy}>
          No autorizo
        </button>
      </div>
    </section>
  );
}
