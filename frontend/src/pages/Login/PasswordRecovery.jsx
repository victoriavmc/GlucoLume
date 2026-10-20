// Recuperación de contraseña de las cuentas comunes (la de plataforma tiene su propio flujo en /plataforma/recuperar):
//   /recuperar-contrasena            POST /auth/password/forgot  -> el backend envía un enlace de un solo uso
//   /restablecer-contrasena?token=…  POST /auth/password/reset   -> elige la contraseña nueva
// La respuesta de «forgot» es siempre la misma exista o no la cuenta: la pantalla no revela qué correos están registrados.

import { ArrowRight, CircleAlert, Lock, Mail } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import * as authApi from '../../api/authApi.js';
import { friendlyError } from '../../auth/errorMessages.js';
import { Alert, SubmitButton, TextField } from '../../components/FormControls.jsx';
import { EMAIL_PATTERN, passwordMeetsPolicy } from '../../utils/validation.js';
import { PasswordRules } from '../Register/RegisterForm.jsx';
import { AuthShell } from './Login.jsx';

const SHELL = {
  title: (
    <>
      Recuperá el acceso
      <br />a tu <span className="accent">cuenta</span>
    </>
  ),
  lead: 'Te enviamos por correo un enlace de un solo uso para elegir una contraseña nueva.',
};

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (loading) return;
    if (!EMAIL_PATTERN.test(email.trim())) {
      setError('Ingresá un correo electrónico válido.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      await authApi.forgotPassword(email.trim());
      setSent(true);
    } catch (forgotError) {
      setError(friendlyError(forgotError));
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell {...SHELL}>
      <h2 className="auth-title">Recuperar contraseña</h2>
      {sent ? (
        <div className="auth-form">
          <Alert kind="success">
            Si el correo corresponde a una cuenta con contraseña, te enviamos un enlace para elegir una nueva. Vence en 30
            minutos. Si tu cuenta ingresa solo con Google, usá «Continuar con Google».
          </Alert>
          <Link to="/login" className="btn btn-ghost btn-block">
            Volver a iniciar sesión
          </Link>
        </div>
      ) : (
        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          {error && <Alert>{error}</Alert>}
          <TextField
            label="Correo electrónico"
            icon={Mail}
            type="email"
            autoComplete="email"
            maxLength={254}
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <SubmitButton loading={loading} loadingLabel="Enviando…" disabled={loading}>
            Enviar enlace <ArrowRight size={18} aria-hidden="true" />
          </SubmitButton>
          <Link to="/login" className="link-button">
            Volver a iniciar sesión
          </Link>
        </form>
      )}
    </AuthShell>
  );
}

// El token se lee una vez y se quita de la barra de direcciones y del historial.
function readToken() {
  const token = new URLSearchParams(window.location.search).get('token');
  if (token) window.history.replaceState(null, '', window.location.pathname);
  return token;
}

const linkError = (error) =>
  ['TOKEN_INVALIDO', 'TOKEN_VENCIDO'].includes(error?.codigo) ? error.message : friendlyError(error);

function BadLink({ message }) {
  return (
    <div className="auth-form">
      <div className="register-success">
        <span className="success-icon is-error">
          <CircleAlert size={32} aria-hidden="true" />
        </span>
        <h3>No pudimos usar este enlace</h3>
      </div>
      <Alert>{message}</Alert>
      <Link to="/recuperar-contrasena" className="btn btn-primary btn-block">
        Pedir un enlace nuevo
      </Link>
    </div>
  );
}

export function ResetPasswordPage() {
  const rulesId = useId();
  const tokenRef = useRef(undefined);
  const [bad, setBad] = useState('');
  const [form, setForm] = useState({ password: '', confirm: '' });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    // Un solo efecto aunque React monte dos veces (StrictMode): la segunda lectura ya no encontraría el token.
    if (tokenRef.current !== undefined) return;
    tokenRef.current = readToken();
    if (!tokenRef.current) setBad('El enlace de restablecimiento es inválido.');
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving) return;
    const next = {};
    if (!passwordMeetsPolicy(form.password)) next.password = 'La contraseña no cumple todos los requisitos.';
    if (form.confirm !== form.password) next.confirm = 'Las contraseñas no coinciden.';
    setErrors(next);
    if (Object.keys(next).length) return;
    setSaving(true);
    setError('');
    try {
      await authApi.resetPassword(tokenRef.current, form.password);
      setDone(true);
    } catch (resetError) {
      if (resetError.codigo === 'PASSWORD_DEBIL') setErrors({ password: friendlyError(resetError) });
      else if (['TOKEN_INVALIDO', 'TOKEN_VENCIDO'].includes(resetError.codigo)) setBad(linkError(resetError));
      else setError(friendlyError(resetError));
      setSaving(false);
    }
  }

  return (
    <AuthShell {...SHELL}>
      <h2 className="auth-title">Nueva contraseña</h2>
      {bad ? (
        <BadLink message={bad} />
      ) : done ? (
        <div className="auth-form">
          <Alert kind="success">Contraseña actualizada. Cerramos tus sesiones abiertas: iniciá sesión con la nueva.</Alert>
          <Link to="/login" className="btn btn-primary btn-block">
            Ir a iniciar sesión
          </Link>
        </div>
      ) : (
        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          {error && <Alert>{error}</Alert>}
          <TextField
            label="Contraseña nueva"
            icon={Lock}
            revealable
            autoComplete="new-password"
            maxLength={128}
            value={form.password}
            onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))}
            error={errors.password}
            aria-describedby={rulesId}
          />
          <PasswordRules value={form.password} id={rulesId} />
          <TextField
            label="Repetir contraseña"
            icon={Lock}
            revealable
            autoComplete="new-password"
            maxLength={128}
            value={form.confirm}
            onChange={(event) => setForm((current) => ({ ...current, confirm: event.target.value }))}
            error={errors.confirm}
          />
          <SubmitButton loading={saving} loadingLabel="Guardando…" disabled={saving}>
            Guardar contraseña <ArrowRight size={18} aria-hidden="true" />
          </SubmitButton>
        </form>
      )}
    </AuthShell>
  );
}
