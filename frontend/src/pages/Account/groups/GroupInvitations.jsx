// Invitaciones del grupo (solo administrador): buscar una cuenta individual por correo, invitar, ver pendientes y
// cancelarlas. La persona se incorpora solo si acepta desde su cuenta.

import { Copy, Mail, Search, UserPlus, X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Navigate, useOutletContext } from 'react-router-dom';

import * as groupsApi from '../../../api/groupsApi.js';
import { Badge } from '../../../components/Badge.jsx';
import { Alert, SubmitButton, TextField } from '../../../components/FormControls.jsx';
import { copyText } from '../../../utils/clipboard.js';
import { EMAIL_PATTERN } from '../../../utils/validation.js';
import { formatDateTime, individualSignupUrl, personName } from './groupFormat.js';

export function GroupInvitations() {
  const { group, isAdmin, handleOperationError } = useOutletContext();
  const [email, setEmail] = useState('');
  const [candidate, setCandidate] = useState(null);
  const [fieldError, setFieldError] = useState('');
  const [error, setError] = useState(null); // { message, codigo }
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    try {
      setPending(await groupsApi.listSentInvitations(group.idGrupo));
    } catch (loadError) {
      setError({ message: handleOperationError(loadError) });
      setPending([]);
    }
  }, [group.idGrupo, handleOperationError]);

  useEffect(() => {
    if (isAdmin) load();
  }, [isAdmin, load]);

  if (!isAdmin) return <Navigate to=".." relative="path" replace />;

  async function search(event) {
    event.preventDefault();
    if (busy) return;
    if (!EMAIL_PATTERN.test(email.trim())) {
      setFieldError('Ingresá un correo electrónico válido.');
      return;
    }
    setFieldError('');
    setError(null);
    setCandidate(null);
    setNotice('');
    setBusy(true);
    try {
      setCandidate(await groupsApi.lookupCandidate(group.idGrupo, email.trim()));
    } catch (lookupError) {
      setError({ message: handleOperationError(lookupError), codigo: lookupError.codigo });
    } finally {
      setBusy(false);
    }
  }

  async function sendInvitation() {
    setBusy(true);
    setError(null);
    try {
      const invited = await groupsApi.invite(group.idGrupo, email.trim());
      setNotice(`Invitación enviada a ${personName(invited)}. Se va a incorporar cuando la acepte.`);
      setEmail('');
      setCandidate(null);
      await load();
    } catch (inviteError) {
      setError({ message: handleOperationError(inviteError), codigo: inviteError.codigo });
    } finally {
      setBusy(false);
    }
  }

  async function cancel(invitation) {
    setBusy(true);
    setError(null);
    try {
      await groupsApi.cancelInvitation(group.idGrupo, invitation.idGrupoUsuario);
      setNotice(`Cancelaste la invitación de ${personName(invitation)}.`);
      await load();
    } catch (cancelError) {
      setError({ message: handleOperationError(cancelError) });
    } finally {
      setBusy(false);
    }
  }

  async function copySignupLink() {
    setCopied(await copyText(individualSignupUrl()));
  }

  return (
    <section className="panel" aria-labelledby="grupo-invitar">
      <div className="panel-title">
        <span className="panel-icon">
          <UserPlus size={22} aria-hidden="true" />
        </span>
        <div>
          <h2 id="grupo-invitar">Invitar a una persona</h2>
          <p>Solo cuentas individuales de GlucoLume que no pertenezcan a otro grupo.</p>
        </div>
      </div>
      {notice && <Alert kind="success">{notice}</Alert>}
      <form className="member-search" onSubmit={search} noValidate>
        <TextField label="Correo electrónico de la cuenta individual" icon={Mail} type="email" autoComplete="off"
          maxLength={254} value={email} error={fieldError}
          onChange={(event) => { setEmail(event.target.value); setCandidate(null); setError(null); setCopied(false); }} />
        <SubmitButton loading={busy && !candidate} loadingLabel="Buscando…" className="btn btn-primary">
          <Search size={16} aria-hidden="true" /> Buscar
        </SubmitButton>
      </form>
      {error && (
        <Alert kind={error.codigo === 'USUARIO_NO_ENCONTRADO' ? 'info' : 'error'}>
          {error.message}
          {error.codigo === 'USUARIO_NO_ENCONTRADO' && (
            <div className="signup-share">
              <a href="/registro?tipo=usuario" target="_blank" rel="noreferrer">Registro de cuentas individuales</a>
              <button type="button" className="btn btn-ghost" onClick={copySignupLink}>
                <Copy size={16} aria-hidden="true" /> {copied ? 'Enlace copiado' : 'Copiar enlace para compartir'}
              </button>
            </div>
          )}
        </Alert>
      )}
      {candidate && (
        <div className="member-candidate">
          <p>
            Vas a invitar a <b>{personName(candidate)}</b>. La invitación vence a los 7 días y no le da acceso a ningún
            dato: cada persona decide qué compartir.
          </p>
          <div className="form-actions">
            <button type="button" className="btn btn-ghost" onClick={() => setCandidate(null)} disabled={busy}>
              Cancelar
            </button>
            <button type="button" className="btn btn-primary" onClick={sendInvitation} disabled={busy}>
              {busy && <span className="spinner" aria-hidden="true" />} Enviar invitación
            </button>
          </div>
        </div>
      )}

      <h3 className="member-list-title gd-pending-title">Invitaciones pendientes</h3>
      {pending === null ? (
        <p className="field-hint" role="status">Cargando…</p>
      ) : pending.length === 0 ? (
        <p className="field-hint">No hay invitaciones pendientes.</p>
      ) : (
        <ul className="member-list-items" aria-label="Invitaciones pendientes">
          {pending.map((invitation) => (
            <li key={invitation.idGrupoUsuario} className="member-row">
              <span>
                <b>{personName(invitation)}</b>
                <small> · enviada el {formatDateTime(invitation.fechaInvitacion)}</small>
                <br />
                <Badge tone="neutral">
                  {invitation.vencida ? 'Vencida' : `Pendiente · vence el ${formatDateTime(invitation.fechaVencimiento)}`}
                </Badge>
              </span>
              <button type="button" className="btn btn-outline" disabled={busy} onClick={() => cancel(invitation)}
                aria-label={`Cancelar invitación de ${personName(invitation)}`}>
                <X size={16} aria-hidden="true" /> Cancelar invitación
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
