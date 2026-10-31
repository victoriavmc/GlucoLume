// Marca «analizado» de un evento de la auditoría general (solo la administración de la plataforma; FastAPI lo vuelve a comprobar).
// La marca se guarda aparte: el evento y su registro original no cambian. Desmarcar la quita; cada cambio queda en la auditoría.

import { useState } from 'react';

import { setGlobalAuditReview } from '../../../api/auditApi.js';
import { friendlyError } from '../../../auth/errorMessages.js';
import { formatInstant } from '../../../utils/dateTime.js';

/** `name`: nombre del evento para el lector de pantalla (la lista tiene una casilla por fila). */
export function AuditReviewToggle({ idAuditoria, revision, name, onChange }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function toggle(event) {
    setBusy(true);
    setError('');
    try {
      onChange(await setGlobalAuditReview(idAuditoria, event.target.checked));
    } catch (requestError) {
      setError(friendlyError(requestError));
    } finally {
      setBusy(false);
    }
  }

  const detail = revision.revisado && revision.fechaRevision
    ? `Analizado por ${revision.revisor ?? 'la administración'}, ${formatInstant(revision.fechaRevision)}`
    : 'Sin analizar';
  return (
    <span className="audit-review" title={detail}>
      <label>
        <input type="checkbox" checked={revision.revisado} disabled={busy} onChange={toggle} aria-label={`Analizado: ${name}`} />
        <span>{revision.revisado ? 'Analizado' : 'Sin analizar'}</span>
      </label>
      {revision.revisado && revision.fechaRevision && <small className="audit-note">{detail}</small>}
      {error && <small className="audit-note is-error" role="alert">{error}</small>}
    </span>
  );
}
