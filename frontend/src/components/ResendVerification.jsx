// Reenvío del correo de verificación (POST /auth/verify-email/resend).
// Se usa en /verificar-correo (enlace vencido o inválido) y en el login (CORREO_NO_VERIFICADO).

import { Mail, RotateCw } from 'lucide-react';
import { useState } from 'react';

import { resendVerification } from '../api/authApi.js';
import { friendlyError } from '../auth/errorMessages.js';
import { EMAIL_PATTERN } from '../utils/validation.js';
import { Alert, SubmitButton, TextField } from './FormControls.jsx';

export function ResendVerification({ initialEmail = '', label = 'Enviar un enlace nuevo' }) {
  const [email, setEmail] = useState(EMAIL_PATTERN.test(initialEmail.trim()) ? initialEmail.trim() : '');
  const [fieldError, setFieldError] = useState('');
  const [status, setStatus] = useState({ phase: 'idle' });

  async function handleSubmit(event) {
    event.preventDefault();
    event.stopPropagation();
    if (status.phase === 'sending') return;
    if (!EMAIL_PATTERN.test(email.trim())) {
      setFieldError('Ingresá el correo con el que te registraste.');
      return;
    }
    setFieldError('');
    setStatus({ phase: 'sending' });
    try {
      await resendVerification(email.trim());
      setStatus({ phase: 'sent' });
    } catch (error) {
      setStatus({ phase: 'error', message: friendlyError(error) });
    }
  }

  return (
    <form className="auth-form resend-verification" onSubmit={handleSubmit} noValidate>
      {status.phase === 'sent' && (
        <Alert kind="success">Te enviamos un nuevo correo de verificación, si ese correo corresponde a una cuenta pendiente. Revisá tu bandeja de entrada o spam. Podés pedir otro pasado un minuto.</Alert>
      )}
      {status.phase === 'error' && <Alert>{status.message}</Alert>}
      <TextField
        label="Correo electrónico de tu cuenta"
        icon={Mail}
        type="email"
        autoComplete="email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        error={fieldError}
      />
      <SubmitButton loading={status.phase === 'sending'} loadingLabel="Enviando…" className="btn btn-outline btn-block">
        <RotateCw size={18} aria-hidden="true" /> {label}
      </SubmitButton>
    </form>
  );
}
