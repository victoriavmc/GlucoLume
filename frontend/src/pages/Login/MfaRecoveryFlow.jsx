// "Perdí acceso a mi aplicación autenticadora": recuperación controlada desde el paso MFA del login.
//
//   1. Contraseña actual (si la cuenta la tiene) -> POST /auth/mfa/recovery/start { challengeToken, password? }
//      El backend envía un código al correo registrado (nunca a uno ingresado acá).
//   2. Código del correo -> POST /auth/mfa/recovery/verify { recoveryToken, codigo }
//      El backend desactiva el MFA perdido, revoca las sesiones anteriores y abre una sesión nueva.
//
// Ingreso con Google: se intenta sin contraseña; si la cuenta tiene una, el backend la pide (PASSWORD_REQUERIDA).

import { ArrowLeft, Lock, MailCheck, RotateCw, ShieldAlert } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { startMfaRecovery } from '../../api/authApi.js';
import { friendlyError } from '../../auth/errorMessages.js';
import { Alert, SubmitButton, TextField } from '../../components/FormControls.jsx';

const CODE_PATTERN = /^\d{6}$/;
// Mensajes del backend redactados para este flujo (más precisos que los genéricos).
const BACKEND_MESSAGE_CODES = ['CODIGO_INVALIDO', 'CODIGO_VENCIDO', 'PASSWORD_INCORRECTA', 'DEMASIADAS_SOLICITUDES'];

function recoveryError(error) {
  if (error?.codigo === 'TOKEN_INVALIDO') return 'La recuperación venció. Volvé a iniciar sesión para empezar de nuevo.';
  return BACKEND_MESSAGE_CODES.includes(error?.codigo) ? error.message : friendlyError(error);
}

export function MfaRecoveryFlow({ challengeToken, askPassword, onVerify, onCancel }) {
  const [step, setStep] = useState(askPassword ? 'password' : 'starting'); // password | starting | code
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [sent, setSent] = useState(null); // { recoveryToken, correoEnmascarado, vigenciaMinutos }
  const [fieldError, setFieldError] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const startedWithoutPassword = useRef(false);

  async function requestCode(withPassword) {
    setBusy(true);
    setError('');
    try {
      const result = await startMfaRecovery(challengeToken, withPassword || undefined);
      setSent(result);
      setStep('code');
      return true;
    } catch (requestError) {
      if (requestError.codigo === 'PASSWORD_REQUERIDA') {
        setStep('password');
      } else {
        setError(recoveryError(requestError));
        if (step === 'starting') setStep('password');
      }
      return false;
    } finally {
      setBusy(false);
    }
  }

  // Cuenta que ingresó con Google: primero sin contraseña (una cuenta solo Google no tiene).
  useEffect(() => {
    if (askPassword || startedWithoutPassword.current) return;
    startedWithoutPassword.current = true;
    requestCode(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function submitPassword(event) {
    event.preventDefault();
    if (busy) return;
    if (!password) {
      setFieldError('Ingresá tu contraseña actual.');
      return;
    }
    setFieldError('');
    await requestCode(password);
  }

  async function submitCode(event) {
    event.preventDefault();
    if (busy) return;
    const value = code.trim();
    if (!CODE_PATTERN.test(value)) {
      setFieldError('Ingresá el código de 6 dígitos que te enviamos.');
      return;
    }
    setFieldError('');
    setError('');
    setBusy(true);
    try {
      await onVerify(sent.recoveryToken, value);
    } catch (verifyError) {
      setError(recoveryError(verifyError));
      setCode('');
      setBusy(false);
    }
  }

  async function resend() {
    setNotice('');
    if (await requestCode(password)) setNotice('Te enviamos un código nuevo. El anterior ya no sirve.');
  }

  return (
    <div className="auth-form">
      <div className="auth-info">
        <span className="auth-info-icon">
          <ShieldAlert size={24} aria-hidden="true" />
        </span>
        <div>
          <b>Recuperar acceso</b>
          <p>
            Si perdiste tu aplicación autenticadora, podés desactivar la verificación en dos pasos confirmando tu
            identidad y un código que enviamos a tu correo registrado.
          </p>
        </div>
      </div>

      {error && <Alert>{error}</Alert>}

      {step === 'starting' && (
        <div className="auth-status" role="status">
          <span className="spinner" aria-hidden="true" /> Enviando el código a tu correo…
        </div>
      )}

      {step === 'password' && (
        <form className="auth-form" onSubmit={submitPassword} noValidate>
          <p className="field-hint">Para proteger tu cuenta, confirmá tu contraseña.</p>
          <TextField label="Contraseña actual" icon={Lock} revealable autoComplete="current-password" maxLength={128}
            value={password} onChange={(event) => setPassword(event.target.value)} error={fieldError} autoFocus />
          <SubmitButton loading={busy} loadingLabel="Verificando…">
            Continuar
          </SubmitButton>
        </form>
      )}

      {step === 'code' && sent && (
        <form className="auth-form" onSubmit={submitCode} noValidate>
          <Alert kind="info">
            <MailCheck size={16} aria-hidden="true" className="inline-icon" /> Enviamos un código de seguridad a{' '}
            <b>{sent.correoEnmascarado}</b>. Vence en {sent.vigenciaMinutos} minutos.
          </Alert>
          {notice && <Alert kind="success">{notice}</Alert>}
          <TextField label="Código enviado a tu correo" icon={MailCheck} inputMode="numeric" autoComplete="one-time-code"
            maxLength={6} placeholder="123456" value={code} error={fieldError} autoFocus
            onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))} />
          <p className="field-hint">Al verificarlo se desactiva la verificación en dos pasos de tu cuenta.</p>
          <SubmitButton loading={busy} loadingLabel="Verificando…">
            Verificar
          </SubmitButton>
          <button type="button" className="link-button" onClick={resend} disabled={busy}>
            <RotateCw size={14} aria-hidden="true" className="inline-icon" /> Enviar un código nuevo
          </button>
        </form>
      )}

      <div className="auth-row">
        <button type="button" className="btn-text" onClick={onCancel} disabled={busy}>
          <ArrowLeft size={16} aria-hidden="true" /> Volver al código de la aplicación
        </button>
      </div>
    </div>
  );
}
