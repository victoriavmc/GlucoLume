// /app/perfil: datos reales de GET /auth/me, en modo lectura o edición (PATCH /auth/me/profile).
// ?editar=1 abre directamente la edición (p. ej. desde el aviso de perfil incompleto).

import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { useAuth } from '../../auth/AuthContext.jsx';
import { Alert } from '../../components/FormControls.jsx';
import { ProfileEditForm } from './ProfileEditForm.jsx';
import { ProfileSummary } from './ProfileSummary.jsx';

export default function ProfilePage() {
  const { account, updateAccount } = useAuth();
  const [params, setParams] = useSearchParams();
  const [editing, setEditing] = useState(params.get('editar') === '1');
  const [notice, setNotice] = useState(null);

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
        <ProfileSummary account={account} onEdit={startEditing} />
      )}
    </div>
  );
}
