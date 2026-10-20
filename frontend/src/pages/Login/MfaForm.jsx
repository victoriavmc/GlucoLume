import { ArrowLeft, KeyRound, ShieldCheck } from 'lucide-react';
import { useState } from 'react';

import { Alert, SubmitButton, TextField } from '../../components/FormControls.jsx';
import { friendlyError } from '../../auth/errorMessages.js';

const TOTP_PATTERN = /^\d{6}$/;

/** Segundo paso cuando el backend responde MFA_REQUERIDO (POST /auth/mfa/verify). */
export function MfaForm({ onSubmit, onCancel, onLostAuthenticator }) {
  const [useRecovery, setUseRecovery] = useState(false);
  const [value, setValue] = useState('');
  const [fieldError, setFieldError] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  function validate(text) {
    if (!text) return useRecovery ? 'Ingresá un código de recuperación.' : 'Ingresá el código de 6 dígitos.';
    if (!useRecovery && !TOTP_PATTERN.test(text)) return 'El código tiene 6 dígitos.';
    return '';
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const text = value.trim();
    const validation = validate(text);
    setFieldError(validation);
    if (validation) return;
    setError('');
    setLoading(true);
    try {
      await onSubmit(useRecovery ? { codigoRecuperacion: text } : { codigo: text });
    } catch (submitError) {
      setError(friendlyError(submitError));
      setLoading(false);
    }
  }

  function toggleMode() {
    setUseRecovery((current) => !current);
    setValue('');
    setFieldError('');
    setError('');
  }

  return (
    <form className="auth-form" onSubmit={handleSubmit} noValidate>
      <div className="auth-info">
        <span className="auth-info-icon">
          <ShieldCheck size={24} aria-hidden="true" />
        </span>
        <div>
          <b>Verificación en dos pasos</b>
          <p>
            {useRecovery
              ? 'Ingresá uno de los códigos de recuperación que guardaste al activar la verificación.'
              : 'Ingresá el código de 6 dígitos de tu aplicación autenticadora.'}
          </p>
        </div>
      </div>

      {error && <Alert>{error}</Alert>}

      {useRecovery ? (
        <TextField
          key="recovery"
          label="Código de recuperación"
          icon={KeyRound}
          name="codigoRecuperacion"
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={32}
          placeholder="XXXX-XXXX"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          error={fieldError}
          autoFocus
        />
      ) : (
        <TextField
          key="totp"
          label="Código de verificación"
          icon={ShieldCheck}
          name="codigo"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          placeholder="123456"
          value={value}
          onChange={(event) => setValue(event.target.value.replace(/\D/g, ''))}
          error={fieldError}
          autoFocus
        />
      )}

      <SubmitButton loading={loading} loadingLabel="Verificando…">
        Verificar
      </SubmitButton>

      {onLostAuthenticator && (
        <button type="button" className="link-button" onClick={onLostAuthenticator}>
          ¿Perdiste acceso a tu aplicación autenticadora?
        </button>
      )}

      <div className="auth-row">
        <button type="button" className="link-button" onClick={toggleMode}>
          {useRecovery ? 'Usar el código de la aplicación' : 'Usar un código de recuperación'}
        </button>
        <button type="button" className="btn-text" onClick={onCancel}>
          <ArrowLeft size={16} aria-hidden="true" /> Volver
        </button>
      </div>
    </form>
  );
}
