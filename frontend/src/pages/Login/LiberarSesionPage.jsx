// /liberar-sesion?token=… : destino del botón «Fui yo» del correo de inicio bloqueado por sesión activa.
//
// POST /auth/sesion-activa/liberar { token } (sin sesión): cierra las sesiones abiertas de la cuenta. No abre sesión ni cambia la
// contraseña: después el titular ingresa con su contraseña normal. El enlace sirve una sola vez y vence; un error de red no lo consume.

import { ArrowRight } from 'lucide-react';
import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import * as authApi from '../../api/authApi.js';
import { friendlyError } from '../../auth/errorMessages.js';
import { Alert, SubmitButton } from '../../components/FormControls.jsx';
import { AuthShell } from './Login.jsx';

function readToken() {
  const token = new URLSearchParams(window.location.search).get('token');
  if (token) window.history.replaceState(null, '', window.location.pathname);
  return token;
}

// Errores que ya no se arreglan confirmando de nuevo: el enlace no sirve (usado, vencido o inventado). Textos propios: el mapa compartido de
// friendlyError trae el de la eliminación de cuenta para TOKEN_VENCIDO.
const TEXTOS_FINALES = {
  TOKEN_INVALIDO: 'El enlace es inválido o ya fue usado. Volvé a intentar ingresar para recibir uno nuevo.',
  TOKEN_VENCIDO: 'El enlace venció. Volvé a intentar ingresar para recibir uno nuevo.',
};

export default function LiberarSesionPage() {
  const token = useRef(undefined);
  if (token.current === undefined) token.current = readToken();

  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState(token.current ? '' : 'El enlace es inválido. Usá el botón del correo de aviso.');
  const [finalError, setFinalError] = useState(!token.current);

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving || finalError || done) return;
    setError('');
    setSaving(true);
    try {
      await authApi.liberarSesionActiva(token.current);
      setDone(true);
    } catch (liberarError) {
      if (liberarError.codigo in TEXTOS_FINALES) {
        setFinalError(true);
        setError(TEXTOS_FINALES[liberarError.codigo]);
      } else {
        setError(friendlyError(liberarError));
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <AuthShell title={<>Fui <span className="accent">yo</span></>}
      lead="Si intentaste ingresar mientras tenías una sesión abierta en otro dispositivo, podés cerrar esa sesión desde acá.">
      <h2 className="auth-title">Cerrar la sesión anterior</h2>

      {done ? (
        <div className="auth-form">
          <Alert kind="success">Listo. Cerramos la sesión que estaba abierta. Ahora podés iniciar sesión con tu contraseña.</Alert>
          <Link to="/login" className="btn btn-primary btn-block btn-lg">
            Ir a iniciar sesión <ArrowRight size={18} aria-hidden="true" />
          </Link>
        </div>
      ) : finalError ? (
        <div className="auth-form">
          <Alert>{error}</Alert>
          <Link to="/login" className="btn btn-outline btn-block btn-lg">Ir a iniciar sesión</Link>
        </div>
      ) : (
        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <Alert kind="info">
            Al confirmar se cierran las sesiones abiertas de tu cuenta. Después ingresás con tu contraseña normal. El enlace sirve una sola vez.
          </Alert>
          {error && <Alert>{error}</Alert>}
          <SubmitButton loading={saving} loadingLabel="Cerrando la sesión…">
            Sí, fui yo: cerrar la sesión anterior
          </SubmitButton>
          <p className="auth-foot">
            Si no fuiste vos, no confirmes. <Link to="/recuperar-contrasena">Restablecé tu contraseña</Link>: cierra todas las sesiones de tu cuenta.
          </p>
        </form>
      )}
    </AuthShell>
  );
}
