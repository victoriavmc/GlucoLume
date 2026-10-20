// Mi privacidad: permisos personales de compartición con el grupo (PUT /groups/{id}/sharing/me). Solo los propios:
// nadie, ni el administrador, puede cambiarlos. Los cuatro son independientes y arrancan desactivados.

import { ShieldCheck, ShieldOff } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useOutletContext } from 'react-router-dom';

import * as groupsApi from '../../../api/groupsApi.js';
import { Alert } from '../../../components/FormControls.jsx';
import { NO_SHARING, SHARING_OPTIONS } from './groupFormat.js';

function sameSettings(a, b) {
  return SHARING_OPTIONS.every(({ field }) => Boolean(a?.[field]) === Boolean(b?.[field]));
}

export function MyPrivacy() {
  const { group, handleOperationError } = useOutletContext();
  const [saved, setSaved] = useState(null);
  const [form, setForm] = useState(NO_SHARING);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    groupsApi.getMySharing(group.idGrupo)
      .then((settings) => { setSaved(settings); setForm(settings); })
      .catch((loadError) => setError(handleOperationError(loadError)));
  }, [group.idGrupo, handleOperationError]);

  async function save(next) {
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const settings = Object.fromEntries(SHARING_OPTIONS.map(({ field }) => [field, Boolean(next[field])]));
      const result = await groupsApi.updateMySharing(group.idGrupo, settings);
      setSaved(result);
      setForm(result);
      setNotice(Object.values(settings).some(Boolean)
        ? 'Guardamos tus permisos. Rigen desde ahora para todo el grupo.'
        : 'Dejaste de compartir todos tus datos con el grupo.');
    } catch (saveError) {
      setError(handleOperationError(saveError));
    } finally {
      setSaving(false);
    }
  }

  if (!saved && !error) return <p className="field-hint" role="status">Cargando tus permisos…</p>;

  const active = SHARING_OPTIONS.filter(({ field }) => saved?.[field]);
  const dirty = !sameSettings(form, saved);

  return (
    <form className="panel" aria-labelledby="privacidad" onSubmit={(event) => { event.preventDefault(); save(form); }}>
      <div className="panel-title">
        <span className="panel-icon">
          <ShieldCheck size={22} aria-hidden="true" />
        </span>
        <div>
          <h2 id="privacidad">Mi privacidad</h2>
          <p>Elegí qué ve el resto del grupo. Podés cambiarlo o revocarlo cuando quieras.</p>
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      {notice && <Alert kind="success">{notice}</Alert>}

      {saved && !saved.perfilDisponible && (
        <Alert kind="info">
          Todavía no tenés un perfil de medición: completá tu fecha de nacimiento y sexo en <Link to="/app/perfil">Perfil</Link>.
          Hasta entonces no hay datos para compartir.
        </Alert>
      )}
      {saved?.perfilDisponible && (
        <p className="field-hint">
          Se comparte únicamente <b>tu perfil de medición personal</b>. Nunca tu correo, contraseña, códigos de seguridad
          ni información institucional.
        </p>
      )}

      <p className="field-hint" role="status">
        {active.length ? `Compartís: ${active.map(({ label }) => label.toLowerCase()).join(', ')}.` : 'No compartís ningún dato con el grupo.'}
      </p>

      <ul className="sharing-options" aria-label="Permisos de compartición">
        {SHARING_OPTIONS.map(({ field, label, detail }) => (
          <li key={field} className="toggle-row">
            <label className="sharing-option">
              <input type="checkbox" checked={Boolean(form[field])} disabled={saving}
                onChange={(event) => setForm((current) => ({ ...current, [field]: event.target.checked }))} />
              <span>
                <b>{label}</b>
                <small>{detail}</small>
              </span>
            </label>
          </li>
        ))}
      </ul>

      <div className="form-actions">
        <button type="button" className="btn btn-ghost" disabled={saving || !active.length}
          onClick={() => save(NO_SHARING)}>
          <ShieldOff size={16} aria-hidden="true" /> Dejar de compartir todo
        </button>
        <button type="submit" className="btn btn-primary" disabled={saving || !dirty}>
          {saving && <span className="spinner" aria-hidden="true" />} Guardar cambios
        </button>
      </div>
    </form>
  );
}
