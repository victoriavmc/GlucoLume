// /confirmar-correo-resultados#token=… : destino del correo CONFIRMAR_CORREO_RESULTADOS (GL-08).
//
// El paciente institucional no tiene cuenta. Un operador cargó su correo (o pidió enviarle un resultado) y el paciente confirma que la
// dirección es suya. El token viaja en el fragmento (no llega a los registros del servidor) y se quita de la barra de direcciones al leerlo.
// Confirmar exige tocar el botón: abrir el enlace no hace nada, así un escáner de enlaces no puede confirmar solo.
// POST /institutions/result-email/confirm { token } (sin sesión). Repetirlo no vuelve a enviar nada.

import { ArrowRight, MailCheck } from 'lucide-react';
import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import * as institutionsApi from '../../api/institutionsApi.js';
import { friendlyError } from '../../auth/errorMessages.js';
import { Alert, SubmitButton } from '../../components/FormControls.jsx';
import { AuthShell } from '../Login/Login.jsx';

function readToken() {
  const token = new URLSearchParams(window.location.hash.replace(/^#/, '')).get('token');
  if (token) window.history.replaceState(null, '', window.location.pathname);
  return token;
}

function successMessage(result) {
  if (result.resultadoEnviado) return `Listo: enviamos tu resultado a ${result.correoEnmascarado}.`;
  if (result.correoGuardado) return `Listo: ${result.correoEnmascarado} va a recibir tus resultados durante los próximos 12 meses.`;
  return 'Este enlace ya se había usado: no hace falta hacer nada más.';
}

export default function ConfirmResultEmailPage() {
  const token = useRef(undefined);
  if (token.current === undefined) token.current = readToken();

  const [error, setError] = useState(token.current ? '' : 'El enlace no es válido o venció. Pedile al operador que te lo envíe de nuevo.');
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState(null);

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving || !token.current) return;
    setError('');
    setSaving(true);
    try {
      setResult(await institutionsApi.confirmResultEmail(token.current));
    } catch (confirmError) {
      setError(friendlyError(confirmError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <AuthShell title={<>Confirmar <span className="accent">correo</span></>}
      lead="Una institución que usa GlucoLume quiere enviarte tus resultados por correo.">
      <h2 className="auth-title">¿Este correo es tuyo?</h2>
      {result ? (
        <div className="auth-form">
          <Alert kind="success">{successMessage(result)}</Alert>
          <Link to="/" className="btn btn-primary btn-block btn-lg">
            Ir al inicio <ArrowRight size={18} aria-hidden="true" />
          </Link>
        </div>
      ) : (
        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <Alert kind="info">
            Confirmá solo si autorizaste a la institución a enviarte tus resultados. Si no reconocés este pedido, cerrá esta página: sin tu
            confirmación no se envía nada.
          </Alert>
          {error && <Alert>{error}</Alert>}
          <SubmitButton loading={saving} loadingLabel="Confirmando…" disabled={saving || !token.current}>
            <MailCheck size={18} aria-hidden="true" /> Confirmar mi correo
          </SubmitButton>
          <Link to="/privacidad" className="btn btn-ghost btn-block">Política de privacidad</Link>
        </form>
      )}
    </AuthShell>
  );
}
