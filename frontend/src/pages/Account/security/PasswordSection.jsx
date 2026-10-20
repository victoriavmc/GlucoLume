// Contraseña local.
// - Cuenta creada con Google sin contraseña: puede crear una (POST /auth/password).
// - Cuenta con contraseña: puede cambiarla (POST /auth/password/change) con la actual y, si tiene MFA, un código.

import { Check, Circle, KeyRound, Lock } from 'lucide-react';
import { useId, useState } from 'react';

import * as authApi from '../../../api/authApi.js';
import { useAuth } from '../../../auth/AuthContext.jsx';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Alert, SubmitButton, TextField } from '../../../components/FormControls.jsx';
import { PASSWORD_RULES, passwordMeetsPolicy } from '../../../utils/validation.js';

export function CreatePasswordForm({ onCreated }) {
  const { refreshAccount } = useAuth();
  const rulesId = useId();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState({});
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving) return;
    const next = {};
    if (!passwordMeetsPolicy(password)) next.password = 'La contraseña no cumple todos los requisitos.';
    if (confirm !== password) next.confirm = 'Las contraseñas no coinciden.';
    setErrors(next);
    if (Object.keys(next).length) return;
    setError('');
    setSaving(true);
    try {
      await authApi.setLocalPassword(password);
      // El formulario desaparece al refrescar la cuenta (pasa a tener contraseña): el aviso vive en PasswordSection.
      onCreated();
      await refreshAccount();
    } catch (saveError) {
      // PASSWORD_DEBIL trae el motivo exacto del backend (p. ej. contiene datos personales).
      setError(friendlyError(saveError));
      setSaving(false);
    }
  }

  return (
    <form className="auth-form" onSubmit={handleSubmit} noValidate>
      {error && <Alert>{error}</Alert>}
      <TextField label="Nueva contraseña" icon={Lock} revealable autoComplete="new-password" maxLength={128}
        value={password} onChange={(event) => setPassword(event.target.value)} error={errors.password}
        aria-describedby={rulesId} />
      <ul className="password-rules" id={rulesId} aria-label="Requisitos de la contraseña">
        {PASSWORD_RULES.map((rule) => {
          const ok = rule.test(password);
          return (
            <li key={rule.id} className={ok ? 'is-ok' : undefined}>
              {ok ? <Check size={14} aria-hidden="true" /> : <Circle size={14} aria-hidden="true" />}
              {rule.label}
            </li>
          );
        })}
      </ul>
      <TextField label="Confirmar contraseña" icon={Lock} revealable autoComplete="new-password" maxLength={128}
        value={confirm} onChange={(event) => setConfirm(event.target.value)} error={errors.confirm} />
      <div className="form-actions">
        <SubmitButton loading={saving} loadingLabel="Guardando…" className="btn btn-primary">
          Crear contraseña
        </SubmitButton>
      </div>
    </form>
  );
}

function ChangePasswordForm({ account, onChanged }) {
  const rulesId = useId();
  const [form, setForm] = useState({ actual: '', nueva: '', confirmacion: '', codigo: '' });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const update = (field) => (event) => setForm((current) => ({ ...current, [field]: event.target.value }));

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving) return;
    const next = {};
    if (!form.actual) next.actual = 'Ingresá tu contraseña actual.';
    if (!passwordMeetsPolicy(form.nueva)) next.nueva = 'La contraseña no cumple todos los requisitos.';
    if (form.confirmacion !== form.nueva) next.confirmacion = 'Las contraseñas no coinciden.';
    if (account.mfaHabilitado && !/^\d{6}$/.test(form.codigo.trim())) next.codigo = 'Ingresá el código de 6 dígitos.';
    setErrors(next);
    if (Object.keys(next).length) return;
    setError('');
    setSaving(true);
    try {
      await authApi.changePassword({
        passwordActual: form.actual, passwordNueva: form.nueva,
        ...(account.mfaHabilitado ? { codigo: form.codigo.trim() } : {}),
      });
      setForm({ actual: '', nueva: '', confirmacion: '', codigo: '' });
      onChanged();
    } catch (changeError) {
      setError(friendlyError(changeError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="auth-form" onSubmit={handleSubmit} noValidate aria-label="Cambiar contraseña">
      {error && <Alert>{error}</Alert>}
      <TextField label="Contraseña actual" icon={Lock} revealable autoComplete="current-password" maxLength={128}
        value={form.actual} onChange={update('actual')} error={errors.actual} />
      <TextField label="Contraseña nueva" icon={Lock} revealable autoComplete="new-password" maxLength={128}
        value={form.nueva} onChange={update('nueva')} error={errors.nueva} aria-describedby={rulesId} />
      <ul className="password-rules" id={rulesId} aria-label="Requisitos de la contraseña">
        {PASSWORD_RULES.map((rule) => {
          const ok = rule.test(form.nueva);
          return (
            <li key={rule.id} className={ok ? 'is-ok' : undefined}>
              {ok ? <Check size={14} aria-hidden="true" /> : <Circle size={14} aria-hidden="true" />}
              {rule.label}
            </li>
          );
        })}
      </ul>
      <TextField label="Confirmar contraseña nueva" icon={Lock} revealable autoComplete="new-password" maxLength={128}
        value={form.confirmacion} onChange={update('confirmacion')} error={errors.confirmacion} />
      {account.mfaHabilitado && (
        <TextField label="Código de verificación (6 dígitos)" inputMode="numeric" autoComplete="one-time-code" maxLength={6}
          value={form.codigo} error={errors.codigo}
          onChange={(event) => setForm((current) => ({ ...current, codigo: event.target.value.replace(/\D/g, '') }))} />
      )}
      <div className="form-actions">
        <SubmitButton loading={saving} loadingLabel="Guardando…" className="btn btn-primary">Cambiar contraseña</SubmitButton>
      </div>
    </form>
  );
}

export function PasswordSection({ account }) {
  const [created, setCreated] = useState(false);
  const [changed, setChanged] = useState(false);
  return (
    <section className="panel" aria-labelledby="seguridad-password">
      <div className="panel-title">
        <span className="panel-icon">
          <KeyRound size={22} aria-hidden="true" />
        </span>
        <div>
          <h2 id="seguridad-password">Contraseña</h2>
          <p>
            {account.tieneCredencialLocal
              ? 'Tu cuenta tiene una contraseña para iniciar sesión con tu correo o usuario.'
              : 'Tu cuenta usa solo Google. Podés crear una contraseña para ingresar también con tu correo o usuario.'}
          </p>
        </div>
      </div>
      {created && (
        <Alert kind="success">
          Contraseña creada con éxito. Te enviamos un correo para confirmarlo y ya podés ingresar también con tu correo o usuario.
        </Alert>
      )}
      {changed && (
        <Alert kind="success">Cambiaste tu contraseña con éxito. Te enviamos un correo para confirmarlo y cerramos tus otras sesiones.</Alert>
      )}
      {account.tieneCredencialLocal ? (
        <ChangePasswordForm account={account} onChanged={() => { setChanged(true); setCreated(false); }} />
      ) : (
        <CreatePasswordForm onCreated={() => setCreated(true)} />
      )}
    </section>
  );
}
