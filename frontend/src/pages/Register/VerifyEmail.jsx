// /verificar-correo?token=… : destino del enlace del correo de verificación.
//
// Verifica la cuenta con GET /auth/verify-email (el token es de un solo uso) y muestra el resultado.
// Si el enlace venció o ya se usó, permite pedir un correo nuevo (POST /auth/verify-email/resend).

import { ArrowRight, CircleAlert, MailCheck } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { verifyEmail } from '../../api/authApi.js';
import { friendlyError } from '../../auth/errorMessages.js';
import { Alert } from '../../components/FormControls.jsx';
import { ResendVerification } from '../../components/ResendVerification.jsx';
import { AuthShell } from '../Login/Login.jsx';
import './Register.css';

function readToken() {
  const token = new URLSearchParams(window.location.search).get('token');
  // El token no debe quedar en la barra de direcciones ni en el historial.
  if (token) window.history.replaceState(null, '', window.location.pathname);
  return token;
}

const ERROR_MESSAGES = {
  TOKEN_INVALIDO:
    'El enlace no es válido o ya fue utilizado. Si ya verificaste tu correo, iniciá sesión; si no, pedí un enlace nuevo.',
  VERIFICACION_EXPIRADA: 'El plazo para verificar la cuenta venció y la cuenta se eliminó. Registrate nuevamente.',
};

export default function VerifyEmail() {
  const started = useRef(false);
  const [state, setState] = useState({ phase: 'verifying' });

  useEffect(() => {
    // Una sola verificación aunque React monte dos veces el efecto (StrictMode): el token es de un solo uso.
    if (started.current) return;
    started.current = true;
    const token = readToken();
    if (!token) {
      setState({ phase: 'error', codigo: 'TOKEN_INVALIDO' });
      return;
    }
    verifyEmail(token)
      .then(() => setState({ phase: 'verified' }))
      .catch((error) => setState({ phase: 'error', codigo: error.codigo, message: friendlyError(error) }));
  }, []);

  return (
    <AuthShell
      title={
        <>
          Verificá tu
          <br />
          <span className="accent">correo</span>
        </>
      }
      lead="Confirmamos que el correo es tuyo antes del primer ingreso, para proteger tu cuenta y tus datos."
    >
      <h2 className="auth-title">Verificación de correo</h2>

      {state.phase === 'verifying' && (
        <div className="auth-status" role="status">
          <span className="spinner" aria-hidden="true" /> Verificando tu correo…
        </div>
      )}

      {state.phase === 'verified' && (
        <div className="auth-form register-success">
          <span className="success-icon">
            <MailCheck size={32} aria-hidden="true" />
          </span>
          <h3>¡Correo verificado!</h3>
          <p>Tu cuenta ya está activa. Te enviamos un correo de bienvenida.</p>
          <Link to="/login" className="btn btn-primary btn-block btn-lg">
            Iniciar sesión <ArrowRight size={18} aria-hidden="true" />
          </Link>
        </div>
      )}

      {state.phase === 'error' && (
        <div className="auth-form">
          <div className="register-success">
            <span className="success-icon is-error">
              <CircleAlert size={32} aria-hidden="true" />
            </span>
            <h3>No pudimos verificar el correo</h3>
          </div>
          <Alert>{ERROR_MESSAGES[state.codigo] ?? state.message}</Alert>
          {state.codigo === 'VERIFICACION_EXPIRADA' ? (
            <Link to="/registro" className="btn btn-primary btn-block btn-lg">
              Registrarme nuevamente <ArrowRight size={18} aria-hidden="true" />
            </Link>
          ) : (
            <>
              <ResendVerification />
              <Link to="/login" className="btn btn-ghost btn-block">
                Ya verifiqué: iniciar sesión
              </Link>
            </>
          )}
        </div>
      )}
    </AuthShell>
  );
}
