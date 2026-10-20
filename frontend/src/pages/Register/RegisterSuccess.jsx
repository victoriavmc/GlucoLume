import { ArrowRight, MailCheck, RotateCw } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { resendVerification } from '../../api/authApi.js';
import { friendlyError } from '../../auth/errorMessages.js';
import { Alert } from '../../components/FormControls.jsx';

export function RegisterSuccess({ email }) {
  const [status, setStatus] = useState({ phase: 'idle' });

  async function resend() {
    setStatus({ phase: 'sending' });
    try {
      await resendVerification(email);
      setStatus({ phase: 'sent' });
    } catch (error) {
      setStatus({ phase: 'error', message: friendlyError(error) });
    }
  }

  return (
    <div className="auth-form register-success">
      <span className="success-icon">
        <MailCheck size={32} aria-hidden="true" />
      </span>
      <h3>Revisá tu correo</h3>
      <p>
        Te enviamos un enlace de verificación a <b>{email}</b>. Abrilo para activar tu cuenta y después iniciá
        sesión.
      </p>
      {status.phase === 'sent' && <Alert kind="success">Te enviamos un nuevo correo de verificación.</Alert>}
      {status.phase === 'error' && <Alert>{status.message}</Alert>}
      <Link to="/login" className="btn btn-primary btn-block btn-lg">
        Ir a iniciar sesión <ArrowRight size={18} aria-hidden="true" />
      </Link>
      <button type="button" className="btn btn-ghost btn-block" onClick={resend} disabled={status.phase === 'sending'}>
        {status.phase === 'sending' ? <span className="spinner" aria-hidden="true" /> : <RotateCw size={18} aria-hidden="true" />}
        Reenviar el correo
      </button>
    </div>
  );
}
