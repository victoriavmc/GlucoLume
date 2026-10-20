// Invitaciones institucionales recibidas: la propia cuenta, con su sesión, las acepta o rechaza.
// No se muestra nada si no hay invitaciones pendientes.

import { Check, MailOpen, X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import * as institutionsApi from '../../../api/institutionsApi.js';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Badge } from '../../../components/Badge.jsx';
import { Alert } from '../../../components/FormControls.jsx';
import { ROLE_LABELS, formatDateTime, typeLabel } from './institutionFormat.js';

export function InvitationsSection({ onAccepted }) {
  const [items, setItems] = useState([]);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    try {
      setItems(await institutionsApi.getInvitations());
    } catch (loadError) {
      setError(friendlyError(loadError));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function respond(invitation, accept) {
    if (busyId) return;
    setBusyId(invitation.idInstitucionUsuario);
    setError('');
    setNotice('');
    try {
      if (accept) {
        await institutionsApi.acceptInvitation(invitation.idInstitucionUsuario);
        setNotice(`Te sumaste a «${invitation.nombreInstitucion}» como ${ROLE_LABELS[invitation.rolInstitucion].toLowerCase()}.`);
        onAccepted?.();
      } else {
        await institutionsApi.rejectInvitation(invitation.idInstitucionUsuario);
        setNotice(`Rechazaste la invitación de «${invitation.nombreInstitucion}».`);
      }
    } catch (respondError) {
      setError(friendlyError(respondError));
    } finally {
      setBusyId(null);
      await load();
    }
  }

  if (!items.length && !error && !notice) return null;

  return (
    <section className="panel" aria-labelledby="invitaciones">
      <div className="panel-title">
        <span className="panel-icon">
          <MailOpen size={22} aria-hidden="true" />
        </span>
        <div>
          <h2 id="invitaciones">Invitaciones</h2>
          <p>Una institución te invitó a sumarte a su equipo. Solo vos podés aceptarlas; vencen a los 7 días.</p>
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      {notice && <Alert kind="success">{notice}</Alert>}
      {items.length > 0 && (
        <ul className="member-list-items">
          {items.map((invitation) => (
            <li key={invitation.idInstitucionUsuario} className="member-row">
              <span>
                <b>{invitation.nombreInstitucion}</b>
                <small>
                  {' '}
                  {typeLabel(invitation.tipoInstitucion)} · Rol propuesto: {ROLE_LABELS[invitation.rolInstitucion]}
                  {invitation.nombreInvitante && ` · Invitación de ${invitation.nombreInvitante}`} ·{' '}
                  {invitation.estado === 'VENCIDA' ? 'Venció el' : 'Vence el'} {formatDateTime(invitation.fechaVencimiento)}
                </small>
                <br />
                <Badge tone={invitation.estado === 'VENCIDA' ? 'neutral' : 'success'}>
                  {invitation.estado === 'VENCIDA' ? 'Vencida: pedí una nueva invitación' : 'Pendiente de respuesta'}
                </Badge>
              </span>
              {invitation.estado === 'PENDIENTE' && (
              <span className="member-actions">
                <button type="button" className="btn btn-primary" disabled={busyId !== null}
                  onClick={() => respond(invitation, true)} aria-label={`Aceptar invitación de ${invitation.nombreInstitucion}`}>
                  <Check size={16} aria-hidden="true" /> Aceptar
                </button>
                <button type="button" className="btn btn-ghost" disabled={busyId !== null}
                  onClick={() => respond(invitation, false)} aria-label={`Rechazar invitación de ${invitation.nombreInstitucion}`}>
                  <X size={16} aria-hidden="true" /> Rechazar
                </button>
              </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
