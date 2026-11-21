// Destino del callback de Google: FRONTEND_URL/auth/google/callback#code=… o #error=…
// El código es de un solo uso (2 minutos) y se canjea con POST /auth/google/exchange.
//
// Mismo destino para iniciar sesión y para registrarse: el tipo de una cuenta nueva lo decidió el backend con la
// intención guardada en el flujo OAuth; una cuenta existente conserva su tipo.

import { ArrowLeft } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { useAuth } from '../../auth/AuthContext.jsx';
import { friendlyError, googleCallbackError } from '../../auth/errorMessages.js';
import { takePendingGooglePlatform, takePendingGoogleRemember } from '../../auth/tokenStore.js';
import { Alert } from '../../components/FormControls.jsx';
import { AuthShell, MFA_RECOVERED_NOTICE } from './Login.jsx';
import { MfaForm } from './MfaForm.jsx';
import { MfaRecoveryFlow } from './MfaRecoveryFlow.jsx';

// Registrarse con Google con un correo que ya tiene cuenta: el backend lo rechaza y aquí se redirige a iniciar sesión.
const CUENTA_EXISTENTE_CODES = ['CUENTA_YA_EXISTE', 'CUENTA_OTRO_TIPO'];
const CUENTA_EXISTENTE_REDIRECT_MS = 4000;
// Destino de «volver» según el acceso con el que se inició el flujo (A-8). Son rutas fijas: nunca salen de un parámetro.
const LOGIN_GENERAL = '/login';
const LOGIN_PLATAFORMA = '/plataforma/login';

function readFragment() {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  // El código no debe quedar en el historial ni en la barra de direcciones.
  window.history.replaceState(null, '', window.location.pathname);
  return { code: params.get('code'), error: params.get('error'), remember: params.get('recordar') === '1' };
}

export default function GoogleCallback() {
  const { completeGoogle, completeMfa, completeMfaRecovery, setFlash } = useAuth();
  const navigate = useNavigate();
  const started = useRef(false);
  const remember = useRef(false);
  const platform = useRef(false);
  const [state, setState] = useState({ phase: 'loading' });

  function finish() {
    // «Continuar con Google» desde el acceso administrativo: se entra al panel (el backend valida el rol).
    navigate(platform.current ? '/plataforma/dashboard' : '/app', { replace: true });
  }

  useEffect(() => {
    // Un solo canje aunque React monte dos veces el efecto (StrictMode): el código es de un solo uso.
    if (started.current) return;
    started.current = true;
    const fragment = readFragment();
    const { code, error } = fragment;
    // «Recordarme» puede venir del backend (login iniciado en otro origen) o de este mismo origen.
    remember.current = takePendingGoogleRemember() || fragment.remember;
    // Se consume al volver, también si el ingreso falla: una marca que queda vieja enviaría al próximo ingreso de la pestaña al panel.
    platform.current = takePendingGooglePlatform();
    if (!code) {
      setState({ phase: 'error', message: googleCallbackError(error), code: error });
      return;
    }
    completeGoogle(code, remember.current)
      .then((result) => {
        if (result.mfaRequired) setState({ phase: 'mfa', challengeToken: result.challengeToken });
        else finish();
      })
      .catch((exchangeError) => setState({ phase: 'error', message: friendlyError(exchangeError) }));
    // finish usa refs y navigate: solo debe ejecutarse al montar.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [completeGoogle]);

  // Login al que vuelve el usuario si el flujo no terminó: el mismo acceso con el que empezó (marca de PLATAFORMA del inicio).
  const loginPath = platform.current ? LOGIN_PLATAFORMA : LOGIN_GENERAL;

  useEffect(() => {
    // Ese correo ya tiene cuenta: se muestra el motivo un momento y se lleva a iniciar sesión (sin pasar por MFA).
    if (state.phase !== 'error' || !CUENTA_EXISTENTE_CODES.includes(state.code)) return undefined;
    const timer = setTimeout(() => navigate(platform.current ? LOGIN_PLATAFORMA : LOGIN_GENERAL, { replace: true }), CUENTA_EXISTENTE_REDIRECT_MS);
    return () => clearTimeout(timer);
  }, [state, navigate]);

  async function handleMfa(factor) {
    try {
      await completeMfa(state.challengeToken, factor, remember.current);
      finish();
    } catch (mfaError) {
      if (mfaError.codigo === 'TOKEN_INVALIDO') {
        setState({ phase: 'error', message: 'La verificación tardó demasiado. Volvé a ingresar con Google.' });
        return;
      }
      throw mfaError;
    }
  }

  return (
    <AuthShell>
      <h2 className="auth-title">Acceso con Google</h2>
      {state.phase === 'loading' && (
        <div className="auth-status" role="status">
          <span className="spinner" aria-hidden="true" /> Completando el acceso con Google…
        </div>
      )}
      {state.phase === 'mfa' && (
        <MfaForm
          onSubmit={handleMfa}
          onCancel={() => navigate(loginPath, { replace: true })}
          onLostAuthenticator={() => setState({ ...state, phase: 'recovery' })}
        />
      )}
      {state.phase === 'recovery' && (
        <MfaRecoveryFlow
          challengeToken={state.challengeToken}
          askPassword={false}
          onVerify={async (recoveryToken, codigo) => {
            setFlash({ message: MFA_RECOVERED_NOTICE, path: '/app/inicio' });
            try {
              await completeMfaRecovery(recoveryToken, codigo, remember.current);
            } catch (error) {
              setFlash(null);
              throw error;
            }
            navigate('/app/inicio', { replace: true });
          }}
          onCancel={() => setState({ ...state, phase: 'mfa' })}
        />
      )}
      {state.phase === 'error' && (
        <div className="auth-form">
          <Alert>{state.message}</Alert>
          {CUENTA_EXISTENTE_CODES.includes(state.code) && (
            <p className="auth-status" role="status">Te llevamos a iniciar sesión…</p>
          )}
          {state.code === 'CUENTA_NO_REGISTRADA' && (
            <Link to="/registro" className="btn btn-primary btn-block btn-lg">
              Registrarme
            </Link>
          )}
          <Link to={loginPath} className="btn btn-outline btn-block btn-lg">
            <ArrowLeft size={18} aria-hidden="true" /> Volver a iniciar sesión
          </Link>
        </div>
      )}
    </AuthShell>
  );
}
