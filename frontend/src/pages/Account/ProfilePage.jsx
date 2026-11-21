// /app/perfil: datos reales de GET /auth/me, en modo lectura o edición (PATCH /auth/me/profile).
// ?editar=1 abre directamente la edición (p. ej. desde el aviso de perfil incompleto).
// Las cuentas individuales ven también la autorización de almacenamiento de mediciones (la misma que en Mediciones).

import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import * as authApi from '../../api/authApi.js';
import { useAuth } from '../../auth/AuthContext.jsx';
import { Alert } from '../../components/FormControls.jsx';
import { ExperimentalConsent } from './measurements/ExperimentalConsent.jsx';
import { ProfileEditForm } from './ProfileEditForm.jsx';
import { ProfileSummary } from './ProfileSummary.jsx';

export default function ProfilePage() {
  const { account, updateAccount } = useAuth();
  const [params, setParams] = useSearchParams();
  const [editing, setEditing] = useState(params.get('editar') === '1');
  const [notice, setNotice] = useState(null);
  const [consent, setConsent] = useState(null); // null: cargando · { aceptado, ... }
  const [consentError, setConsentError] = useState('');
  const individual = account.usuario.tipoCuenta === 'CONSUMIDOR_FINAL';

  useEffect(() => {
    if (!individual) return;
    authApi.getConsents().then(
      (all) => setConsent(all.DATOS_EXPERIMENTALES),
      () => setConsentError('No pudimos cargar tu autorización. Probá de nuevo en unos minutos.'),
    );
  }, [individual]);

  function startEditing() {
    setNotice(null);
    setEditing(true);
  }

  function stopEditing() {
    setEditing(false);
    if (params.has('editar')) setParams({}, { replace: true });
  }

  function handleSaved(response) {
    updateAccount(response);
    setNotice(response.actualizado ? 'Se registraron los cambios.' : 'No se registraron cambios.');
    stopEditing();
  }

  return (
    <div className="page is-form is-cards">
      <header className="page-head">
        <h1>Mi perfil</h1>
        <p>Tus datos de cuenta y personales en GlucoLume.</p>
      </header>

      {notice && <Alert kind="success">{notice}</Alert>}

      {editing ? (
        <ProfileEditForm account={account} onSaved={handleSaved} onCancel={stopEditing} />
      ) : (
        <>
          <ProfileSummary account={account} onEdit={startEditing} />
          {individual && consentError && <Alert>{consentError}</Alert>}
          {individual && !consentError && (consent === null ? (
            <p className="field-hint" role="status">Cargando tu autorización…</p>
          ) : (
            <ExperimentalConsent consent={consent} onChange={setConsent} />
          ))}
        </>
      )}
    </div>
  );
}
