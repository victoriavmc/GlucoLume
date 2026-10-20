// Aviso por correo en cada inicio de sesión (PUT /auth/me/notifications/new-login).

import { BellRing } from 'lucide-react';
import { useState } from 'react';

import * as authApi from '../../../api/authApi.js';
import { useAuth } from '../../../auth/AuthContext.jsx';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Alert } from '../../../components/FormControls.jsx';

export function LoginNoticeSection({ account }) {
  const { updateAccount } = useAuth();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const enabled = account.notificarNuevoInicioSesion;

  async function toggle() {
    if (saving) return;
    setSaving(true);
    setError('');
    try {
      updateAccount(await authApi.setNewLoginNotification(!enabled));
    } catch (toggleError) {
      setError(friendlyError(toggleError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel" aria-labelledby="seguridad-avisos">
      <div className="toggle-row">
        <div className="panel-title">
          <span className="panel-icon">
            <BellRing size={22} aria-hidden="true" />
          </span>
          <div>
            <h2 id="seguridad-avisos">Avisos de inicio de sesión</h2>
            <p>Recibí un correo cada vez que alguien inicia sesión en tu cuenta. Las alertas de actividad sospechosa se envían siempre.</p>
          </div>
        </div>
        <button type="button" role="switch" className="switch" aria-checked={enabled} aria-labelledby="seguridad-avisos"
          onClick={toggle} disabled={saving} />
      </div>
      {error && <Alert>{error}</Alert>}
    </section>
  );
}
