// Accesos propios de la Administración de GlucoLume: /plataforma/login, /plataforma/activar, /plataforma/recuperar y
// /plataforma/restablecer. No es otro sistema de autenticación: usan el login, el MFA y la sesión de siempre; el backend
// decide después (GET /platform/me) si la cuenta tiene un rol de plataforma. Un usuario común recibe 403 y se cierra su sesión.

import { ArrowRight, AtSign, CircleAlert, KeyRound, Lock, Mail, ShieldCheck } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import * as platformApi from '../../api/platformApi.js';
import { useAuth } from '../../auth/AuthContext.jsx';
import { friendlyError } from '../../auth/errorMessages.js';
import { startGoogleLogin } from '../../auth/googleLogin.js';
import { Alert, SubmitButton, TextField } from '../../components/FormControls.jsx';
import { passwordMeetsPolicy, usernameError } from '../../utils/validation.js';
import { GoogleIcon } from '../Login/GoogleIcon.jsx';
import { Logo } from '../../components/Logo.jsx';
import { SkipLink } from '../../components/SkipLink.jsx';
import { MfaForm } from '../Login/MfaForm.jsx';
import { PasswordRules } from '../Register/RegisterForm.jsx';
import '../Login/Login.css';
import './PlatformAuth.css';

export const PLATFORM_LOGIN_KEY = 'glucolume.platformLogin';

/** Marco propio del acceso administrativo: sin la navegación pública ni el texto comercial; solo la marca, el acceso y el aviso de uso restringido. */
function PlatformShell({ children }) {
  return (
    <div className="pa-page">
      <SkipLink />
      <main className="pa-main" id="contenido" tabIndex={-1}>
        <div className="pa-wrap">
          <Logo to="/" />
          <section className="auth-card pa-card">
            <span className="pa-badge"><ShieldCheck size={16} aria-hidden="true" /> Acceso administrativo</span>
            {children}
          </section>
          <p className="pa-foot">
            Uso restringido al administrador y a los moderadores del sistema. Se exige verificación en dos pasos y cada acceso queda registrado en la auditoría.
          </p>
        </div>
      </main>
    </div>
  );
}

/** Confirma con el backend que la cuenta tiene un rol de plataforma; si no, cierra la sesión recién abierta. */
export async function enterPlatform({ logout, navigate, setError }) {
  try {
    await platformApi.getPlatformMe();
    navigate('/plataforma/dashboard', { replace: true });
  } catch (meError) {
    await logout();
    setError(meError.status === 403
      ? 'Esta cuenta no tiene acceso a la administración de la plataforma.'
      : friendlyError(meError));
    return false;
  }
  return true;
}

export function PlatformLogin() {
  const { login, completeMfa, logout } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ identificador: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [challengeToken, setChallengeToken] = useState(null);

  function update(field) {
    return (event) => setForm((current) => ({ ...current, [field]: event.target.value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!form.identificador.trim() || !form.password) {
      setError('Ingresá tu correo o usuario y tu contraseña.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const result = await login(form.identificador.trim(), form.password, false, 'PLATAFORMA');
      if (result.mfaRequired) {
        setChallengeToken(result.challengeToken);
        setLoading(false);
        return;
      }
      if (!(await enterPlatform({ logout, navigate, setError }))) setLoading(false);
    } catch (loginError) {
      setError(friendlyError(loginError));
      setForm((current) => ({ ...current, password: '' }));
      setLoading(false);
    }
  }

  async function handleMfa(factor) {
    try {
      await completeMfa(challengeToken, factor, false);
    } catch (mfaError) {
      if (mfaError.codigo === 'TOKEN_INVALIDO') {
        setChallengeToken(null);
        setError('La verificación tardó demasiado. Volvé a ingresar tu contraseña.');
        return;
      }
      throw mfaError;
    }
    if (!(await enterPlatform({ logout, navigate, setError }))) setChallengeToken(null);
  }

  function handleGoogle() {
    window.sessionStorage.setItem(PLATFORM_LOGIN_KEY, '1'); // al volver del callback se entra al panel
    startGoogleLogin(false, undefined, false, 'PLATAFORMA');
  }

  return (
    <PlatformShell>
      <h2 className="auth-title">Administración de GlucoLume</h2>
      {challengeToken ? (
        <>
          {error && <Alert>{error}</Alert>}
          <MfaForm onSubmit={handleMfa} onCancel={() => { setChallengeToken(null); setForm((c) => ({ ...c, password: '' })); }} />
        </>
      ) : (
        <>
          <p className="auth-subtitle">Ingresá con tu cuenta administrativa.</p>
          <form className="auth-form" onSubmit={handleSubmit} noValidate>
            {error && <Alert>{error}</Alert>}
            <TextField label="Correo electrónico o usuario" icon={Mail} name="identificador" autoComplete="username" maxLength={254}
              value={form.identificador} onChange={update('identificador')} />
            <TextField label="Contraseña" icon={Lock} name="password" revealable autoComplete="current-password" maxLength={128}
              value={form.password} onChange={update('password')} />
            <div className="auth-row">
              <Link to="/plataforma/recuperar" className="link-button">¿Olvidaste tu contraseña?</Link>
            </div>
            <SubmitButton loading={loading} loadingLabel="Ingresando…" disabled={loading}>
              Continuar <ArrowRight size={18} aria-hidden="true" />
            </SubmitButton>
            <div className="divider"><span>o</span></div>
            <button type="button" className="btn btn-ghost btn-block btn-lg" onClick={handleGoogle} disabled={loading}>
              <GoogleIcon /> Continuar con Google
            </button>
            <p className="field-hint">
              <ShieldCheck size={14} aria-hidden="true" /> El acceso lo habilita únicamente el rol que tu cuenta tiene en GlucoLume.
            </p>
          </form>
          <p className="pa-activate">
            ¿Tenés un código de activación administrativa? <Link to="/administracion/activar">Activar cuenta</Link>
          </p>
        </>
      )}
    </PlatformShell>
  );
}

/** Código de activación: el de los correos nuevos viaja en el fragmento (#codigo=…, que nunca llega al servidor); también se aceptan
 *  ?codigo=… y ?token=… de enlaces anteriores. Se quita de la barra de direcciones y del historial apenas se lee. */
export function readActivationCode() {
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, '')).get('codigo');
  const search = new URLSearchParams(window.location.search);
  const code = hash ?? search.get('codigo') ?? search.get('token');
  if (code) window.history.replaceState(null, '', window.location.pathname);
  return code;
}

function readToken() {
  const token = new URLSearchParams(window.location.search).get('token');
  if (token) window.history.replaceState(null, '', window.location.pathname); // no queda en la barra ni en el historial
  return token;
}

const linkError = (error) => (['TOKEN_INVALIDO', 'TOKEN_VENCIDO'].includes(error?.codigo) ? error.message : friendlyError(error));

function BadLink({ message }) {
  return (
    <div className="auth-form">
      <div className="register-success">
        <span className="success-icon is-error"><CircleAlert size={32} aria-hidden="true" /></span>
        <h3>No pudimos usar este enlace</h3>
      </div>
      <Alert>{message}</Alert>
      <Link to="/plataforma/login" className="btn btn-ghost btn-block">Ir al acceso administrativo</Link>
    </div>
  );
}

/**
 * /administracion/activar : activa por primera vez una cuenta administrativa con el código de un solo uso que entrega el servidor (primer
 * administrador) o la invitación del administrador (moderadores). Pide el código y los datos de la invitación; el rol NUNCA se elige acá:
 * lo fija la invitación en FastAPI. No es el registro público ni inicia sesión: una vez activada se ingresa por el acceso administrativo.
 */
export function PlatformActivateWithCode() {
  const { acceptLogin } = useAuth();
  const navigate = useNavigate();
  const rulesId = useId();
  const [form, setForm] = useState({ codigo: '', usuario: '', password: '', confirmacion: '' });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const prefilled = useRef(false);

  useEffect(() => {
    if (prefilled.current) return;
    prefilled.current = true;
    const code = readActivationCode(); // el enlace del correo lo completa y se quita de la barra
    if (code) setForm((current) => ({ ...current, codigo: code }));
  }, []);

  function update(field) {
    return (event) => {
      setForm((current) => ({ ...current, [field]: event.target.value }));
      if (errors[field]) setErrors((current) => ({ ...current, [field]: undefined }));
    };
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving) return;
    const next = {};
    if (form.codigo.trim().length < 20) next.codigo = 'Ingresá el código de activación completo.';
    const userProblem = usernameError(form.usuario);
    if (userProblem) next.usuario = userProblem;
    if (!passwordMeetsPolicy(form.password)) next.password = 'La contraseña no cumple todos los requisitos.';
    if (form.confirmacion !== form.password) next.confirmacion = 'Las contraseñas no coinciden.';
    setErrors(next);
    if (Object.keys(next).length) return;
    setSaving(true);
    setError('');
    try {
      await acceptLogin(await platformApi.activateWithCode({
        codigo: form.codigo.trim(), usuario: form.usuario.trim(), password: form.password, confirmacion: form.confirmacion,
      }), false);
      navigate('/plataforma/seguridad', {
        replace: true, state: { notice: 'Activación completada. Falta configurar la verificación en dos pasos (MFA): sin ella no se habilitan las funciones administrativas.' },
      });
    } catch (activationError) {
      if (activationError.codigo === 'USUARIO_REGISTRADO') setErrors({ usuario: 'Ese nombre de usuario ya está en uso. Elegí otro.' });
      else if (activationError.codigo === 'PASSWORD_DEBIL') setErrors({ password: friendlyError(activationError) });
      else setError(friendlyError(activationError));
      setSaving(false);
    }
  }

  return (
    <PlatformShell>
      <span className="pa-step"><KeyRound size={16} aria-hidden="true" /> Activación con código</span>
      <h2 className="auth-title">Activar cuenta administrativa</h2>
      <p className="auth-subtitle">Necesitás el código de un solo uso que te entregó quien administra GlucoLume. Sin él no se puede crear una cuenta administrativa.</p>
      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        {error && <Alert>{error}</Alert>}
        <TextField label="Código de activación" icon={KeyRound} name="codigo" autoComplete="off" spellCheck={false} maxLength={200} value={form.codigo}
          onChange={update('codigo')} error={errors.codigo} hint="Llega en el correo de la invitación, que ya tiene tus datos. Es personal, vence en poco tiempo y se usa una sola vez." />
        <TextField label="Nombre de usuario" icon={AtSign} autoComplete="username" maxLength={50} value={form.usuario}
          onChange={update('usuario')} error={errors.usuario} />
        <TextField label="Contraseña" icon={Lock} revealable autoComplete="new-password" maxLength={128} value={form.password}
          onChange={update('password')} error={errors.password} aria-describedby={rulesId} />
        <PasswordRules value={form.password} id={rulesId} />
        <TextField label="Repetir contraseña" icon={Lock} revealable autoComplete="new-password" maxLength={128}
          value={form.confirmacion} onChange={update('confirmacion')} error={errors.confirmacion} />
        <Alert kind="info">Después de activar vas a configurar obligatoriamente la verificación en dos pasos (MFA) para habilitar las funciones administrativas.</Alert>
        <SubmitButton loading={saving} loadingLabel="Activando…" disabled={saving}>
          Activar cuenta <ArrowRight size={18} aria-hidden="true" />
        </SubmitButton>
        <Link to="/administracion/login" className="link-button">Volver al acceso administrativo</Link>
      </form>
    </PlatformShell>
  );
}

/** /plataforma/recuperar : pide el enlace. La respuesta es la misma exista o no la cuenta. */
export function PlatformForgot() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) {
      setError('Ingresá un correo electrónico válido.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      await platformApi.forgotPassword(email.trim());
      setSent(true);
    } catch (forgotError) {
      setError(friendlyError(forgotError));
    } finally {
      setLoading(false);
    }
  }

  return (
    <PlatformShell>
      <h2 className="auth-title">Recuperar contraseña</h2>
      {sent ? (
        <div className="auth-form">
          <Alert kind="success">
            Si el correo corresponde a una cuenta administrativa, te enviamos un enlace de un solo uso para elegir una nueva contraseña.
          </Alert>
          <Link to="/plataforma/login" className="btn btn-ghost btn-block">Volver al acceso</Link>
        </div>
      ) : (
        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          {error && <Alert>{error}</Alert>}
          <TextField label="Correo electrónico" icon={Mail} autoComplete="email" maxLength={254} value={email}
            onChange={(event) => setEmail(event.target.value)} />
          <SubmitButton loading={loading} loadingLabel="Enviando…" disabled={loading}>Enviar enlace <ArrowRight size={18} aria-hidden="true" /></SubmitButton>
          <Link to="/plataforma/login" className="link-button">Volver al acceso</Link>
        </form>
      )}
    </PlatformShell>
  );
}

/** /plataforma/restablecer?token=… : establece la nueva contraseña. */
export function PlatformReset() {
  const rulesId = useId();
  const tokenRef = useRef(undefined);
  const [bad, setBad] = useState('');
  const [form, setForm] = useState({ password: '', confirm: '' });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
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
      await platformApi.resetPassword(tokenRef.current, form.password);
      setDone(true);
    } catch (resetError) {
      if (resetError.codigo === 'PASSWORD_DEBIL') setErrors({ password: friendlyError(resetError) });
      else setError(linkError(resetError));
      setSaving(false);
    }
  }

  return (
    <PlatformShell>
      <h2 className="auth-title">Nueva contraseña</h2>
      {bad ? <BadLink message={bad} /> : done ? (
        <div className="auth-form">
          <Alert kind="success">Contraseña actualizada. Cerramos tus sesiones abiertas: iniciá sesión con la nueva.</Alert>
          <Link to="/plataforma/login" className="btn btn-primary btn-block">Ir al acceso administrativo</Link>
        </div>
      ) : (
        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          {error && <Alert>{error}</Alert>}
          <TextField label="Contraseña nueva" icon={Lock} revealable autoComplete="new-password" maxLength={128} value={form.password}
            onChange={(event) => setForm((c) => ({ ...c, password: event.target.value }))} error={errors.password} aria-describedby={rulesId} />
          <PasswordRules value={form.password} id={rulesId} />
          <TextField label="Repetir contraseña" icon={Lock} revealable autoComplete="new-password" maxLength={128} value={form.confirm}
            onChange={(event) => setForm((c) => ({ ...c, confirm: event.target.value }))} error={errors.confirm} />
          <SubmitButton loading={saving} loadingLabel="Guardando…" disabled={saving}>Guardar contraseña <ArrowRight size={18} aria-hidden="true" /></SubmitButton>
        </form>
      )}
    </PlatformShell>
  );
}
