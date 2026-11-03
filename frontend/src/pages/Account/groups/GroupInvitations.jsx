// Invitaciones del grupo (solo administrador): buscar una cuenta individual por correo, invitar, ver pendientes y
// cancelarlas. La persona se incorpora solo si acepta desde su cuenta.

import { Copy, Mail, Search, Send, UserPlus, X } from 'lucide-react';
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
  const [searching, setSearching] = useState(false);
  const [acting, setActing] = useState(false);
  const [pending, setPending] = useState(null);
  const [copied, setCopied] = useState(false);
  const [noAccount, setNoAccount] = useState(false); // el correo buscado no tiene cuenta: se ofrece invitarla por correo

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
    if (searching) return;
    if (!EMAIL_PATTERN.test(email.trim())) {
      setFieldError('Ingresá un correo electrónico válido.');
      return;
    }
    setFieldError('');
    setError(null);
    setCandidate(null);
    setNoAccount(false);
    setNotice('');
    setSearching(true);
    try {
      setCandidate(await groupsApi.lookupCandidate(group.idGrupo, email.trim()));
    } catch (lookupError) {
      setError({ message: handleOperationError(lookupError), codigo: lookupError.codigo });
      setNoAccount(lookupError.codigo === 'USUARIO_NO_ENCONTRADO');
    } finally {
      setSearching(false);
    }
  }

  async function sendInvitation() {
    setActing(true);
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
      setActing(false);
    }
  }

  async function resend(invitation) {
    setActing(true);
    setError(null);
    try {
      await groupsApi.resendInvitation(group.idGrupo, invitation.idGrupoUsuario);
      setNotice(`Reenviaste la invitación a ${personName(invitation)}. Vence de nuevo en 7 días.`);
      await load();
    } catch (resendError) {
      setError({ message: handleOperationError(resendError) });
    } finally {
      setActing(false);
    }
  }

  async function cancel(invitation) {
    setActing(true);
    setError(null);
    try {
      await groupsApi.cancelInvitation(group.idGrupo, invitation.idGrupoUsuario);
      setNotice(`Cancelaste la invitación de ${personName(invitation)}.`);
      await load();
    } catch (cancelError) {
      setError({ message: handleOperationError(cancelError) });
    } finally {
      setActing(false);
    }
  }

  async function copySignupLink() {
    setCopied(await copyText(individualSignupUrl()));
  }

  async function sendSignupInvitation(event) {
    event.preventDefault();
    if (acting) return;
    setActing(true);
    setError(null);
    try {
      await groupsApi.invite(group.idGrupo, email.trim());
      setNotice(`Enviamos a ${email.trim()} un correo para que cree su cuenta y acepte la invitación al grupo. Tiene 7 días para hacerlo.`);
      setEmail('');
      setNoAccount(false);
      await load();
    } catch (inviteError) {
      setError({ message: handleOperationError(inviteError), codigo: inviteError.codigo });
    } finally {
      setActing(false);
    }
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
          onChange={(event) => { setEmail(event.target.value); setCandidate(null); setError(null); setNoAccount(false); setCopied(false); }} />
        <SubmitButton loading={searching} loadingLabel="Buscando…" className="btn btn-primary">
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
      {noAccount && (
        <form className="member-candidate" onSubmit={sendSignupInvitation} noValidate>
          <p>
            Le enviamos un correo a <b>{email.trim()}</b> con la invitación al grupo. Desde el enlace crea su cuenta
            (elige su nombre de usuario y su contraseña) y después puede aceptar o rechazar la invitación. Tiene 7 días
            para hacerlo.
          </p>
          <div className="form-actions">
            <SubmitButton loading={acting} loadingLabel="Enviando…" className="btn btn-primary">
              <Send size={16} aria-hidden="true" /> Enviar invitación por correo
            </SubmitButton>
          </div>
        </form>
      )}
      {candidate && (
        <div className="member-candidate">
          <p>
            Vas a invitar a <b>{personName(candidate)}</b>. La invitación vence a los 7 días y no le da acceso a ningún
            dato: cada persona decide qué compartir.
          </p>
          <div className="form-actions">
            <button type="button" className="btn btn-ghost" onClick={() => setCandidate(null)} disabled={acting}>
              Cancelar
            </button>
            <button type="button" className="btn btn-primary" onClick={sendInvitation} disabled={acting}>
              {acting && <span className="spinner" aria-hidden="true" />} Enviar invitación
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
              <div className="form-actions">
                <button type="button" className="btn btn-outline" disabled={acting} onClick={() => resend(invitation)}
                  aria-label={`Reenviar invitación de ${personName(invitation)}`}>
                  <Send size={16} aria-hidden="true" /> Reenviar
                </button>
                <button type="button" className="btn btn-outline" disabled={acting} onClick={() => cancel(invitation)}
                  aria-label={`Cancelar invitación de ${personName(invitation)}`}>
                  <X size={16} aria-hidden="true" /> Cancelar invitación
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
