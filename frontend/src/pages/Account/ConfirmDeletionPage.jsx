// /cuenta/eliminar/confirmar?token=… : destino del enlace del correo ELIMINACION_SOLICITADA.
//
// POST /auth/account-deletion/confirm { token, password?, codigo? | codigoRecuperacion? } (sin sesión):
//   - password: solo si la cuenta tiene contraseña local;
//   - codigo o codigoRecuperacion: solo si tiene MFA (nunca ambos).
// Si hay una sesión abierta en este navegador se sabe de antemano qué pedir; si no, la pantalla se adapta a
// lo que responda el backend (PASSWORD_REQUERIDA / CODIGO_MFA_REQUERIDO). Un error no consume el enlace.

import { ArrowRight, KeyRound, Lock, Smartphone, Trash2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import * as authApi from '../../api/authApi.js';
import { useAuth } from '../../auth/AuthContext.jsx';
import { friendlyError } from '../../auth/errorMessages.js';
import { Alert, SubmitButton, TextField } from '../../components/FormControls.jsx';
import { AuthShell } from '../Login/Login.jsx';

function readToken() {
  const token = new URLSearchParams(window.location.search).get('token');
  if (token) window.history.replaceState(null, '', window.location.pathname);
  return token;
}

const FINAL_ERRORS = ['TOKEN_INVALIDO', 'TOKEN_VENCIDO', 'TOKEN_YA_UTILIZADO', 'CUENTA_NO_ACTIVA'];

export default function ConfirmDeletionPage() {
  const { account, clearSession } = useAuth();
  const token = useRef(undefined);
  if (token.current === undefined) token.current = readToken();

  const [needsPassword, setNeedsPassword] = useState(account ? account.tieneCredencialLocal : true);
  const [needsMfa, setNeedsMfa] = useState(account ? account.mfaHabilitado : false);
  const [form, setForm] = useState({ password: '', codigo: '', codigoRecuperacion: '' });
  const [useRecovery, setUseRecovery] = useState(false);
  const [error, setError] = useState(token.current ? '' : 'El enlace de eliminación es inválido.');
  const [finalError, setFinalError] = useState(!token.current);
  const [saving, setSaving] = useState(false);
  const [deleted, setDeleted] = useState(false);

  useEffect(() => {
    if (account) {
      setNeedsPassword(account.tieneCredencialLocal);
      setNeedsMfa(account.mfaHabilitado);
    }
  }, [account]);

  function update(field) {
    return (event) => {
      const value = field === 'codigo' ? event.target.value.replace(/\D/g, '') : event.target.value;
      setForm((current) => ({ ...current, [field]: value }));
    };
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving || finalError) return;
    setError('');
    setSaving(true);
    try {
      await authApi.confirmAccountDeletion({
        token: token.current,
        password: needsPassword ? form.password : undefined,
        codigo: needsMfa && !useRecovery ? form.codigo.trim() : undefined,
        codigoRecuperacion: needsMfa && useRecovery ? form.codigoRecuperacion.trim() : undefined,
      });
      // El backend revocó todas las sesiones: se limpia también la sesión local.
      clearSession();
      setDeleted(true);
    } catch (confirmError) {
      if (confirmError.codigo === 'CODIGO_MFA_REQUERIDO') setNeedsMfa(true);
      if (confirmError.codigo === 'PASSWORD_REQUERIDA') setNeedsPassword(true);
      if (FINAL_ERRORS.includes(confirmError.codigo)) setFinalError(true);
      setError(friendlyError(confirmError));
      setSaving(false);
    }
  }

  return (
    <AuthShell title={<>Eliminar <span className="accent">cuenta</span></>}
      lead="Confirmá la eliminación de tu cuenta de GlucoLume. Esta acción no se puede deshacer.">
      <h2 className="auth-title">Confirmar eliminación</h2>

      {deleted ? (
        <div className="auth-form">
          <Alert kind="success">Tu cuenta fue eliminada. Te enviamos un correo de confirmación.</Alert>
          <Link to="/" className="btn btn-primary btn-block btn-lg">
            Ir al inicio <ArrowRight size={18} aria-hidden="true" />
          </Link>
        </div>
      ) : finalError ? (
        <div className="auth-form">
          <Alert>{error}</Alert>
          <Link to="/app/seguridad" className="btn btn-outline btn-block btn-lg">
            Volver a seguridad
          </Link>
        </div>
      ) : (
        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <Alert kind="info">
            Se eliminarán tus datos personales identificatorios y se cerrarán todas tus sesiones. Las mediciones se
            conservan de forma anonimizada.
          </Alert>
          {error && <Alert>{error}</Alert>}
          {needsPassword && (
            <TextField label="Contraseña actual" icon={Lock} revealable autoComplete="current-password" maxLength={128}
              value={form.password} onChange={update('password')} />
          )}
          {!account && needsPassword && (
            <p className="field-hint">Si tu cuenta usa solo Google y no tiene contraseña, dejá este campo vacío.</p>
          )}
          {needsMfa && (
            <>
              {useRecovery ? (
                <TextField key="recovery" label="Código de recuperación" icon={KeyRound} autoComplete="off" maxLength={32}
                  value={form.codigoRecuperacion} onChange={update('codigoRecuperacion')} />
              ) : (
                <TextField key="totp" label="Código de verificación" icon={Smartphone} inputMode="numeric"
                  autoComplete="one-time-code" maxLength={6} value={form.codigo} onChange={update('codigo')} />
              )}
              <button type="button" className="link-button" onClick={() => setUseRecovery((value) => !value)}>
                {useRecovery ? 'Usar el código de la aplicación' : 'Usar un código de recuperación'}
              </button>
            </>
          )}
          <SubmitButton loading={saving} loadingLabel="Eliminando…">
            <Trash2 size={18} aria-hidden="true" /> Eliminar mi cuenta definitivamente
          </SubmitButton>
          <Link to="/" className="btn btn-ghost btn-block">
            No eliminar
          </Link>
        </form>
      )}
    </AuthShell>
  );
}
