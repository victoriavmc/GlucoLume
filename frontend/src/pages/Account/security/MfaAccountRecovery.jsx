// Seguridad -> perdió la aplicación autenticadora Y los códigos de recuperación.
//
//   1. Contraseña actual   -> POST /auth/me/mfa/recovery/start { password }  (envía un código al correo registrado)
//   2. Código del correo   -> POST /auth/me/mfa/recovery/verify { codigo }   (desvincula el MFA, revoca las demás sesiones)
//
// Una cuenta solo Google no tiene contraseña: debe volver a ingresar con Google y usar la recuperación del paso
// MFA del login (el ingreso recién hecho con Google es la prueba de identidad). No se crea ninguna contraseña.

import { Lock, LogIn, MailCheck, RotateCw } from 'lucide-react';
import { useState } from 'react';

import * as authApi from '../../../api/authApi.js';
import { useAuth } from '../../../auth/AuthContext.jsx';
import { friendlyError } from '../../../auth/errorMessages.js';
import { startGoogleLogin } from '../../../auth/googleLogin.js';
import { Alert, SubmitButton, TextField } from '../../../components/FormControls.jsx';

const CODE_PATTERN = /^\d{6}$/;
const BACKEND_MESSAGE_CODES = ['CODIGO_INVALIDO', 'CODIGO_VENCIDO', 'PASSWORD_INCORRECTA', 'DEMASIADAS_SOLICITUDES'];

function recoveryError(error) {
  return BACKEND_MESSAGE_CODES.includes(error?.codigo) ? error.message : friendlyError(error);
}

function GoogleOnly({ onCancel }) {
  const { logout } = useAuth();
  const [leaving, setLeaving] = useState(false);

  async function relogin() {
    setLeaving(true);
    await logout();
    startGoogleLogin(false);
  }

  return (
    <div className="auth-form">
      <p className="mfa-text">
        Tu cuenta usa Google y no tiene contraseña. Para confirmar tu identidad, volvé a ingresar con Google: en el
        paso de verificación elegí <b>«¿Perdiste acceso a tu aplicación autenticadora?»</b> y te enviaremos un código
        a tu correo registrado.
      </p>
      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={leaving}>
          Cancelar
        </button>
        <button type="button" className="btn btn-primary" onClick={relogin} disabled={leaving}>
          {leaving ? <span className="spinner" aria-hidden="true" /> : <LogIn size={18} aria-hidden="true" />}
          Volver a ingresar con Google
        </button>
      </div>
    </div>
  );
}

export function MfaAccountRecovery({ account, onCancel, onRecovered }) {
  const { updateAccount } = useAuth();
  const [step, setStep] = useState('password'); // password | code
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [sent, setSent] = useState(null);
  const [fieldError, setFieldError] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  if (!account.tieneCredencialLocal) return <GoogleOnly onCancel={onCancel} />;

  async function requestCode() {
    setBusy(true);
    setError('');
    try {
      setSent(await authApi.startAccountMfaRecovery(password));
      setStep('code');
      return true;
    } catch (requestError) {
      setError(recoveryError(requestError));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function submitPassword(event) {
    event.preventDefault();
    if (busy) return;
    if (!password) {
      setFieldError('Ingresá tu contraseña actual.');
      return;
    }
    setFieldError('');
    await requestCode();
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
      updateAccount(await authApi.verifyAccountMfaRecovery(value));
      setPassword('');
      onRecovered();
    } catch (verifyError) {
      setError(recoveryError(verifyError));
      setCode('');
      setBusy(false);
    }
  }

  async function resend() {
    setNotice('');
    if (await requestCode()) setNotice('Te enviamos un código nuevo. El anterior ya no sirve.');
  }

  return (
    <div className="auth-form mfa-recovery">
      <h3 className="mfa-recovery-title">Recuperar acceso a la verificación en dos pasos</h3>
      {error && <Alert>{error}</Alert>}

      {step === 'password' && (
        <form className="auth-form" onSubmit={submitPassword} noValidate>
          <p className="mfa-text">Para proteger tu cuenta, primero confirmá tu contraseña.</p>
          <TextField label="Contraseña actual" icon={Lock} revealable autoComplete="current-password" maxLength={128}
            value={password} onChange={(event) => setPassword(event.target.value)} error={fieldError} autoFocus />
          <div className="form-actions">
            <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={busy}>
              Cancelar
            </button>
            <SubmitButton loading={busy} loadingLabel="Verificando…" className="btn btn-primary">
              Continuar
            </SubmitButton>
          </div>
        </form>
      )}

      {step === 'code' && sent && (
        <form className="auth-form" onSubmit={submitCode} noValidate>
          <Alert kind="info">
            Enviamos un código de seguridad a <b>{sent.correoEnmascarado}</b>. Vence en {sent.vigenciaMinutos} minutos.
          </Alert>
          {notice && <Alert kind="success">{notice}</Alert>}
          <TextField label="Código enviado a tu correo" icon={MailCheck} inputMode="numeric" autoComplete="one-time-code"
            maxLength={6} placeholder="123456" value={code} error={fieldError} autoFocus
            onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))} />
          <div className="form-actions">
            <button type="button" className="btn btn-ghost" onClick={resend} disabled={busy}>
              <RotateCw size={18} aria-hidden="true" /> Reenviar código
            </button>
            <SubmitButton loading={busy} loadingLabel="Desvinculando…" className="btn btn-primary">
              Verificar y desvincular MFA
            </SubmitButton>
          </div>
          <button type="button" className="link-button" onClick={onCancel} disabled={busy}>
            Cancelar
          </button>
        </form>
      )}
    </div>
  );
}
