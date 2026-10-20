import { Activity, ArrowRight, BarChart3, Building2, KeyRound, Lock, Mail, ShieldCheck, Users } from 'lucide-react';
import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import { useAuth } from '../../auth/AuthContext.jsx';
import { friendlyError } from '../../auth/errorMessages.js';
import { startGoogleLogin } from '../../auth/googleLogin.js';
import { Alert, CheckField, SubmitButton, TextField } from '../../components/FormControls.jsx';
import { Navbar } from '../../components/Navbar.jsx';
import { ResendVerification } from '../../components/ResendVerification.jsx';
import { SkipLink } from '../../components/SkipLink.jsx';
import { GoogleIcon } from './GoogleIcon.jsx';
import { MfaForm } from './MfaForm.jsx';
import { MfaRecoveryFlow } from './MfaRecoveryFlow.jsx';

export const MFA_RECOVERED_NOTICE =
  'Acceso recuperado correctamente. La verificación en dos pasos fue desactivada. Podés volver a configurarla desde Seguridad.';
import './Login.css';

const BENEFITS = [
  { icon: BarChart3, title: 'Datos siempre contigo', text: 'Accedé a tus mediciones, historial y estadísticas en un solo lugar.' },
  { icon: Users, title: 'Acompañamiento continuo', text: 'Compartí tu información con familiares o profesionales de la salud.' },
  { icon: ShieldCheck, title: 'Gestión segura y confiable', text: 'Tus datos se protegen con buenas prácticas de seguridad.' },
];

function validate({ identificador, password }) {
  const errors = {};
  if (!identificador.trim()) errors.identificador = 'Ingresá tu correo electrónico o nombre de usuario.';
  if (!password) errors.password = 'Ingresá tu contraseña.';
  return errors;
}

export function AuthShell({ children, title, lead }) {
  return (
    <div className="auth-page">
      <SkipLink />
      <Navbar />
      <main className="auth-main" id="contenido" tabIndex={-1}>
        <div className="container auth-grid">
          <section className="auth-hero" aria-labelledby="auth-hero-title">
            <span className="pill">
              <Activity size={16} aria-hidden="true" /> Bienvenido a GlucoLume
            </span>
            <h1 id="auth-hero-title">
              {title ?? (
                <>
                  Tu salud,
                  <br />
                  en mejores <span className="accent">manos</span>
                </>
              )}
            </h1>
            <p className="auth-lead">
              {lead ??
                'Iniciá sesión para acceder a tu espacio personal o al panel institucional y seguí aprovechando todas las funcionalidades de GlucoLume.'}
            </p>
            <ul className="benefits">
              {BENEFITS.map(({ icon: Icon, title, text }) => (
                <li key={title}>
                  <span className="benefit-icon">
                    <Icon size={26} aria-hidden="true" />
                  </span>
                  <span>
                    <b>{title}</b>
                    <small>{text}</small>
                  </span>
                </li>
              ))}
            </ul>
          </section>
          <section className="auth-card">{children}</section>
        </div>
      </main>
    </div>
  );
}

export default function Login() {
  const { login, completeMfa, completeMfaRecovery, setFlash } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const destination = location.state?.from || '/app';

  const [form, setForm] = useState({ identificador: '', password: '' });
  const [remember, setRemember] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState('');
  const [errorCode, setErrorCode] = useState(null);
  const [loading, setLoading] = useState(false);
  const [redirectingToGoogle, setRedirectingToGoogle] = useState(false);
  const [challengeToken, setChallengeToken] = useState(null);
  const [recovering, setRecovering] = useState(false);

  function update(field) {
    return (event) => {
      setForm((current) => ({ ...current, [field]: event.target.value }));
      if (fieldErrors[field]) setFieldErrors((current) => ({ ...current, [field]: undefined }));
    };
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const errors = validate(form);
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    setError('');
    setErrorCode(null);
    setLoading(true);
    try {
      const result = await login(form.identificador.trim(), form.password, remember);
      if (result.mfaRequired) {
        setChallengeToken(result.challengeToken);
        setLoading(false);
        return;
      }
      if (result.transferring) return; // la sesión continúa en la aplicación (otro origen): el navegador se redirige
      navigate(destination, { replace: true });
    } catch (loginError) {
      setError(friendlyError(loginError));
      setErrorCode(loginError.codigo ?? null);
      setForm((current) => ({ ...current, password: '' }));
      setLoading(false);
    }
  }

  async function handleMfa(factor) {
    try {
      const result = await completeMfa(challengeToken, factor, remember);
      if (result.transferring) return;
      navigate(destination, { replace: true });
    } catch (mfaError) {
      if (mfaError.codigo === 'TOKEN_INVALIDO') {
        // El desafío MFA vence a los 5 minutos: hay que volver a ingresar la contraseña.
        setChallengeToken(null);
        setError('La verificación tardó demasiado. Volvé a ingresar tu contraseña.');
        return;
      }
      throw mfaError;
    }
  }

  function handleGoogle() {
    setRedirectingToGoogle(true);
    startGoogleLogin(remember);
  }

  return (
    <AuthShell>
      <h2 className="auth-title">Iniciar sesión</h2>

      {challengeToken && recovering && (
        <MfaRecoveryFlow
          challengeToken={challengeToken}
          askPassword
          onVerify={async (recoveryToken, codigo) => {
            // El aviso se fija antes de abrir la sesión: la redirección posterior al login lo conserva.
            setFlash({ message: MFA_RECOVERED_NOTICE, path: '/app/inicio' });
            try {
              const recovered = await completeMfaRecovery(recoveryToken, codigo, remember);
              if (recovered.transferring) return;
            } catch (error) {
              setFlash(null);
              throw error;
            }
            navigate('/app/inicio', { replace: true });
          }}
          onCancel={() => setRecovering(false)}
        />
      )}
      {challengeToken && !recovering && (
        <MfaForm
          onSubmit={handleMfa}
          onLostAuthenticator={() => setRecovering(true)}
          onCancel={() => {
            setChallengeToken(null);
            setForm((current) => ({ ...current, password: '' }));
          }}
        />
      )}
      {!challengeToken && (
        <>
          <p className="auth-subtitle">Ingresá con tu cuenta de GlucoLume.</p>

          {/* Un único inicio de sesión: el backend determina el tipo de cuenta, los roles y las instituciones. */}
          <div className="auth-info">
            <span className="auth-info-icon">
              <KeyRound size={24} aria-hidden="true" />
            </span>
            <div>
              <b>Una sola cuenta para todo</b>
              <p>
                Después de ingresar, GlucoLume carga tu espacio según tu cuenta: personal, grupo o las
                instituciones y roles que tengas asignados.
              </p>
            </div>
          </div>

          <form className="auth-form" onSubmit={handleSubmit} noValidate>
            {error && <Alert>{error}</Alert>}
            {errorCode === 'CREDENCIALES_INVALIDAS' && (
              // Regla general, igual para toda cuenta: no revela si existe ni cuántos intentos le quedan.
              <p className="field-hint">
                Por seguridad, después de 3 intentos fallidos seguidos el acceso se bloquea temporalmente.
              </p>
            )}

            <TextField
              label="Correo electrónico o usuario"
              icon={Mail}
              name="identificador"
              autoComplete="username"
              placeholder="tucorreo@ejemplo.com"
              maxLength={254}
              value={form.identificador}
              onChange={update('identificador')}
              error={fieldErrors.identificador}
            />
            <TextField
              label="Contraseña"
              icon={Lock}
              name="password"
              revealable
              autoComplete="current-password"
              placeholder="Tu contraseña"
              maxLength={128}
              value={form.password}
              onChange={update('password')}
              error={fieldErrors.password}
            />

            <div className="auth-row">
              <CheckField label="Recordarme" checked={remember} onChange={(event) => setRemember(event.target.checked)} />
              <Link to="/recuperar-contrasena" className="link-button">
                ¿Olvidaste tu contraseña?
              </Link>
            </div>

            <SubmitButton loading={loading} loadingLabel="Iniciando sesión…" disabled={loading || redirectingToGoogle}>
              Iniciar sesión <ArrowRight size={18} aria-hidden="true" />
            </SubmitButton>
          </form>

          {errorCode === 'CORREO_NO_VERIFICADO' && (
            <div className="auth-info is-institutional resend-box">
              <div>
                <b>¿No te llegó el correo de verificación?</b>
                <p>Te enviamos un enlace nuevo. El plazo para verificar la cuenta no se extiende.</p>
              </div>
              <ResendVerification
                initialEmail={form.identificador.includes('@') ? form.identificador : ''}
                label="Reenviar correo de verificación"
              />
            </div>
          )}

          <div className="divider">
            <span>o continuá con</span>
          </div>

          <button
            type="button"
            className="btn btn-ghost btn-block btn-lg"
            onClick={handleGoogle}
            disabled={loading || redirectingToGoogle}
          >
            {redirectingToGoogle ? <span className="spinner" aria-hidden="true" /> : <GoogleIcon />}
            {redirectingToGoogle ? 'Redirigiendo a Google…' : 'Continuar con Google'}
          </button>

          <div className="auth-info is-institutional auth-institution-note">
            <span className="auth-info-icon">
              <Building2 size={24} aria-hidden="true" />
            </span>
            <div>
              <b>¿Trabajás en una institución?</b>
              <p>Usás este mismo inicio de sesión. Accedés a las funcionalidades según el rol asignado en tu organización.</p>
            </div>
          </div>

          <p className="auth-footer">
            ¿Todavía no tenés una cuenta?{' '}
            <Link to="/registro">
              Registrarse <ArrowRight size={16} aria-hidden="true" />
            </Link>
          </p>
        </>
      )}
    </AuthShell>
  );
}
