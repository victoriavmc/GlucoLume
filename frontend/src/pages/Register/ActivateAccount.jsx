// /activar-cuenta?token=… : activación de una cuenta creada por una invitación institucional.
//
// 1. Valida el enlace (POST /auth/account-activation/check) y muestra quién invita y con qué rol.
// 2. La persona elige su nombre de usuario y su contraseña (POST /auth/account-activation/complete), con la misma
//    política que el registro; nadie más la conoce. También puede ingresar con Google con ese mismo correo.
// 3. Con la sesión abierta pasa a Instituciones, donde acepta o rechaza la invitación (la aceptación es explícita).

import { ArrowRight, AtSign, CircleAlert, Lock, UserCheck } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { checkAccountActivation } from '../../api/authApi.js';
import { useAuth } from '../../auth/AuthContext.jsx';
import { friendlyError } from '../../auth/errorMessages.js';
import { startGoogleLogin } from '../../auth/googleLogin.js';
import { Alert, SubmitButton, TextField } from '../../components/FormControls.jsx';
import { POLICY_REQUIRED_MESSAGE, PolicyConsent } from '../../components/PolicyConsent.jsx';
import { passwordMeetsPolicy, usernameError } from '../../utils/validation.js';
import { AuthShell } from '../Login/Login.jsx';
import { GoogleIcon } from '../Login/GoogleIcon.jsx';
import { PasswordRules } from './RegisterForm.jsx';
import './Register.css';

const ROLE_LABELS = { PROPIETARIO: 'propietario/a', MODERADOR: 'moderador/a', OPERADOR: 'operador/a' };

function readToken() {
  const token = new URLSearchParams(window.location.search).get('token');
  // El token no debe quedar en la barra de direcciones ni en el historial.
  if (token) window.history.replaceState(null, '', window.location.pathname);
  return token;
}

// Para el enlace se muestra el motivo específico del backend (inválido, usado o vencido), no el genérico de sesión.
function linkError(error) {
  return ['TOKEN_INVALIDO', 'TOKEN_VENCIDO'].includes(error?.codigo) ? error.message : friendlyError(error);
}

export default function ActivateAccount() {
  const { completeActivation } = useAuth();
  const navigate = useNavigate();
  const rulesId = useId();
  const tokenRef = useRef(undefined);
  const [state, setState] = useState({ phase: 'checking' });
  const [form, setForm] = useState({ usuario: '', password: '', confirm: '' });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [policyRead, setPolicyRead] = useState(false);
  const [policyError, setPolicyError] = useState('');

  function confirmPolicy(checked) {
    setPolicyRead(checked);
    if (checked) setPolicyError('');
  }

  function handleGoogle() {
    if (!policyRead) {
      setPolicyError(POLICY_REQUIRED_MESSAGE);
      return;
    }
    startGoogleLogin(false, undefined, true); // el backend exige y registra la confirmación al activar la cuenta
  }

  useEffect(() => {
    if (tokenRef.current !== undefined) return;
    tokenRef.current = readToken();
    if (!tokenRef.current) {
      setState({ phase: 'error', message: 'El enlace de activación es inválido.' });
      return;
    }
    checkAccountActivation(tokenRef.current)
      .then((info) => setState({ phase: 'form', info }))
      .catch((checkError) => setState({ phase: 'error', message: linkError(checkError) }));
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
    const usuarioError = usernameError(form.usuario);
    if (usuarioError) next.usuario = usuarioError;
    if (!passwordMeetsPolicy(form.password)) next.password = 'La contraseña no cumple todos los requisitos.';
    if (form.confirm !== form.password) next.confirm = 'Las contraseñas no coinciden.';
    setErrors(next);
    if (!policyRead) setPolicyError(POLICY_REQUIRED_MESSAGE);
    if (Object.keys(next).length || !policyRead) return;
    setError('');
    setSaving(true);
    try {
      await completeActivation(tokenRef.current, form.usuario.trim(), form.password, true);
      navigate('/app/instituciones', { replace: true, state: { notice: 'Activaste tu cuenta. Aceptá la invitación para sumarte a la institución.' } });
    } catch (activationError) {
      if (activationError.codigo === 'USUARIO_REGISTRADO') setErrors({ usuario: 'Ese nombre de usuario ya está en uso. Elegí otro.' });
      else if (activationError.codigo === 'PASSWORD_DEBIL') setErrors({ password: friendlyError(activationError) });
      else setError(linkError(activationError));
      setSaving(false);
    }
  }

  return (
    <AuthShell
      title={
        <>
          Activá tu
          <br />
          <span className="accent">cuenta</span>
        </>
      }
      lead="Una institución te invitó a GlucoLume. Elegí tus credenciales: nadie más las conoce."
    >
      <h2 className="auth-title">Activación de cuenta</h2>

      {state.phase === 'checking' && (
        <div className="auth-status" role="status">
          <span className="spinner" aria-hidden="true" /> Validando el enlace…
        </div>
      )}

      {state.phase === 'error' && (
        <div className="auth-form">
          <div className="register-success">
            <span className="success-icon is-error">
              <CircleAlert size={32} aria-hidden="true" />
            </span>
            <h3>No pudimos usar este enlace</h3>
          </div>
          <Alert>{state.message}</Alert>
          <Link to="/login" className="btn btn-ghost btn-block">Ya activé mi cuenta: iniciar sesión</Link>
        </div>
      )}

      {state.phase === 'form' && (
        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <div className="register-success">
            <span className="success-icon">
              <UserCheck size={32} aria-hidden="true" />
            </span>
            <h3>Hola, {state.info.nombre}</h3>
            <p>Correo: {state.info.correoEnmascarado}</p>
          </div>
          {state.info.invitaciones.length > 0 && (
            <Alert kind="info">
              Te invitaron como{' '}
              {state.info.invitaciones.map((i) => `${ROLE_LABELS[i.rolInstitucion] ?? i.rolInstitucion} de ${i.nombreInstitucion}`).join(', ')}.
              Después de activar tu cuenta vas a poder aceptar o rechazar la invitación.
            </Alert>
          )}
          {error && <Alert>{error}</Alert>}
          <TextField label="Nombre de usuario" icon={AtSign} autoComplete="username" maxLength={50} value={form.usuario}
            onChange={update('usuario')} error={errors.usuario} />
          <TextField label="Contraseña" icon={Lock} revealable autoComplete="new-password" maxLength={128} value={form.password}
            onChange={update('password')} error={errors.password} aria-describedby={rulesId} />
          <PasswordRules value={form.password} id={rulesId} />
          <TextField label="Repetir contraseña" icon={Lock} revealable autoComplete="new-password" maxLength={128}
            value={form.confirm} onChange={update('confirm')} error={errors.confirm} />
          <PolicyConsent checked={policyRead} onChange={confirmPolicy} error={policyError} disabled={saving} />
          <SubmitButton loading={saving} loadingLabel="Activando…" disabled={saving}>
            Activar cuenta <ArrowRight size={18} aria-hidden="true" />
          </SubmitButton>
          <div className="divider">
            <span>o</span>
          </div>
          <button type="button" className="btn btn-ghost btn-block btn-lg" onClick={handleGoogle} disabled={saving}>
            <GoogleIcon /> Continuar con Google
          </button>
          <p className="field-hint">Con Google, usá la cuenta de este mismo correo.</p>
        </form>
      )}
    </AuthShell>
  );
}
