// Zona de riesgo: eliminación de la cuenta, con el flujo del backend.
//   0. GET /auth/account-deletion/preview: si la cuenta puede eliminarse y qué consecuencias tiene (solo consulta).
//   1. POST /auth/account-deletion/request (con sesión, sin body): valida Grupo/Institución y envía un enlace.
//   2. El enlace del correo abre /cuenta/eliminar/confirmar, donde se pide contraseña / MFA según la cuenta.
// Desde acá nunca se elimina nada directamente. Una cuenta institucional con una o más instituciones activas no puede usar este camino:
// primero debe finalizar sus vinculaciones (lo decide y vuelve a validar FastAPI; esto solo lo explica).

import { MailWarning, TriangleAlert } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import * as authApi from '../../../api/authApi.js';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Alert } from '../../../components/FormControls.jsx';

// El backend guarda la hora de Argentina sin zona (AAAA-MM-DDTHH:MM:SS): se muestra tal cual.
function formatDateTime(value) {
  const [date, time = ''] = String(value).split('T');
  const [year, month, day] = date.split('-');
  return `${day}/${month}/${year} a las ${time.slice(0, 5)} (hora de Argentina)`;
}

function formatDay(value) {
  const [year, month, day] = String(value).slice(0, 10).split('-');
  return `${day}/${month}/${year}`;
}

function Consequences({ preview }) {
  return (
    <div className="deletion-consequences">
      <p className="mfa-text"><b>Qué se elimina:</b></p>
      <ul>{preview.datosEliminados.map((item) => <li key={item}>{item}</li>)}</ul>
      {preview.datosConservados.length > 0 && (
        <>
          <p className="mfa-text"><b>Qué se conserva, sin tu cuenta ni tus datos de acceso:</b></p>
          <ul>{preview.datosConservados.map((item) => <li key={item}>{item}</li>)}</ul>
        </>
      )}
      {preview.invitacionesPendientes > 0 && (
        <p className="mfa-text">
          {preview.invitacionesPendientes === 1 ? 'Tenés 1 invitación pendiente: se cancelará.' : `Tenés ${preview.invitacionesPendientes} invitaciones pendientes: se cancelarán.`}
        </p>
      )}
      {preview.periodoGracia && (
        <p className="mfa-text">
          Tu cuenta se eliminaría sola el {formatDay(preview.periodoGracia.fechaVencimiento)} ({preview.periodoGracia.diasRestantes}{' '}
          {preview.periodoGracia.diasRestantes === 1 ? 'día' : 'días'}). Podés eliminarla ahora sin esperar.
        </p>
      )}
    </div>
  );
}

export function AccountDeletionSection({ account }) {
  const [step, setStep] = useState('idle'); // idle | confirming | sending | sent
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    let active = true;
    authApi.getAccountDeletionPreview().then((value) => active && setPreview(value), () => {}); // sin la consulta, el flujo funciona igual
    return () => { active = false; };
  }, []);

  async function request() {
    setStep('sending');
    setError('');
    try {
      setResult(await authApi.requestAccountDeletion());
      setStep('sent');
    } catch (requestError) {
      // Bloqueos de Grupo/Institución llegan con un detalle redactado para el usuario.
      setError(friendlyError(requestError));
      setStep('confirming');
    }
  }

  const blocked = preview && !preview.puedeEliminar;

  return (
    <section className="panel is-danger" aria-labelledby="seguridad-baja">
      <div className="panel-title">
        <span className="panel-icon">
          <TriangleAlert size={22} aria-hidden="true" />
        </span>
        <div>
          <h2 id="seguridad-baja">Zona de riesgo</h2>
          <p>Eliminar tu cuenta borra tus datos personales identificatorios. No se puede deshacer.</p>
        </div>
      </div>

      {error && <Alert>{error}</Alert>}

      {blocked && (
        <>
          <Alert kind="info">{preview.mensajeBloqueo}</Alert>
          <div className="form-actions">
            <Link to="/app/instituciones" className="btn btn-outline">Gestionar mis instituciones</Link>
          </div>
        </>
      )}

      {!blocked && step === 'idle' && (
        <div className="form-actions">
          <button type="button" className="btn btn-outline" onClick={() => setStep('confirming')}>
            Eliminar cuenta
          </button>
        </div>
      )}

      {!blocked && (step === 'confirming' || step === 'sending') && (
        <div className="auth-form">
          {preview && <Consequences preview={preview} />}
          <p className="mfa-text">
            Te vamos a enviar un enlace a <b>{account.usuario.correoElectronico}</b>, válido por 30 minutos. La cuenta se
            elimina recién cuando lo abras y confirmes
            {account.tieneCredencialLocal ? ' con tu contraseña' : ''}
            {account.mfaHabilitado ? ' y un código de verificación' : ''}.
          </p>
          <div className="form-actions">
            <button type="button" className="btn btn-ghost" onClick={() => { setStep('idle'); setError(''); }}
              disabled={step === 'sending'}>
              Cancelar
            </button>
            <button type="button" className="btn btn-primary" onClick={request} disabled={step === 'sending'}>
              {step === 'sending' && <span className="spinner" aria-hidden="true" />} Enviar enlace de confirmación
            </button>
          </div>
        </div>
      )}

      {step === 'sent' && (
        <Alert kind="info">
          <MailWarning size={16} aria-hidden="true" className="inline-icon" /> Te enviamos el enlace de confirmación. Vence
          el {formatDateTime(result.fechaExpiracion)}. Si no lo usás, tu cuenta sigue activa.
        </Alert>
      )}
    </section>
  );
}
