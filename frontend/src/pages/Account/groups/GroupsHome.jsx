// /app/grupo: punto de entrada del módulo (solo cuentas individuales). Es el espacio único de la persona, no un selector:
//   Con grupo activo -> redirige directo al panel del grupo (no hay pantalla intermedia ni se ofrece crear otro).
//   Sin grupo        -> crear un grupo o unirse con una invitación recibida (aceptar o rechazar).
//   Consultando      -> estado de carga (no aparece «crear grupo» de forma pasajera). Con error -> mensaje y reintento.
// Aceptar una invitación no comparte ningún dato: cada persona lo decide después en «Mi privacidad».

import { Check, MailOpen, Plus, ShieldCheck, Users, X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';

import * as groupsApi from '../../../api/groupsApi.js';
import { useAuth } from '../../../auth/AuthContext.jsx';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Badge } from '../../../components/Badge.jsx';
import { Alert, SubmitButton, TextField } from '../../../components/FormControls.jsx';
import { PageHeader } from '../../../components/PageHeader.jsx';
import { formatDateTime } from './groupFormat.js';

function CreateGroupForm({ onCreated, onCancel }) {
  const [form, setForm] = useState({ nombre: '', descripcion: '' });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving) return;
    if (form.nombre.trim().length < 2) {
      setErrors({ nombre: 'Ingresá el nombre del grupo (al menos 2 caracteres).' });
      return;
    }
    setErrors({});
    setError('');
    setSaving(true);
    try {
      onCreated(await groupsApi.createGroup({ nombre: form.nombre.trim(), descripcion: form.descripcion.trim() || null }));
    } catch (createError) {
      setError(friendlyError(createError));
      setSaving(false);
    }
  }

  return (
    <form className="panel" onSubmit={handleSubmit} noValidate aria-labelledby="grupo-crear">
      <div className="panel-title">
        <span className="panel-icon">
          <Users size={22} aria-hidden="true" />
        </span>
        <div>
          <h2 id="grupo-crear">Crear grupo</h2>
          <p>Vas a quedar como administrador/a. Crear el grupo no comparte ninguno de tus datos.</p>
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      <TextField label="Nombre del grupo" icon={Users} maxLength={100} value={form.nombre}
        onChange={(event) => setForm((current) => ({ ...current, nombre: event.target.value }))} error={errors.nombre} />
      <TextField label="Descripción (opcional)" maxLength={500} value={form.descripcion}
        onChange={(event) => setForm((current) => ({ ...current, descripcion: event.target.value }))} />
      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={saving}>
          Cancelar
        </button>
        <SubmitButton loading={saving} loadingLabel="Creando…" className="btn btn-primary">
          Crear grupo
        </SubmitButton>
      </div>
    </form>
  );
}

function ReceivedInvitations({ invitations, onAccepted, reload }) {
  const [confirmingId, setConfirmingId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function respond(invitation, accept) {
    setBusy(true);
    setError('');
    try {
      if (accept) {
        onAccepted(await groupsApi.acceptInvitation(invitation.idGrupoUsuario));
        return;
      }
      await groupsApi.rejectInvitation(invitation.idGrupoUsuario);
      setNotice(`Rechazaste la invitación a «${invitation.nombreGrupo}».`);
      await reload();
    } catch (respondError) {
      setError(friendlyError(respondError));
      await reload();
    } finally {
      setBusy(false);
      setConfirmingId(null);
    }
  }

  return (
    <section className="panel" aria-labelledby="grupo-invitaciones">
      <div className="panel-title">
        <span className="panel-icon">
          <MailOpen size={22} aria-hidden="true" />
        </span>
        <div>
          <h2 id="grupo-invitaciones">Invitaciones recibidas</h2>
          <p>Solo vos podés aceptarlas. Vencen a los 7 días.</p>
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      {notice && <Alert kind="success">{notice}</Alert>}
      {invitations.length === 0 ? (
        <p className="field-hint">No tenés invitaciones pendientes.</p>
      ) : (
        <ul className="member-list-items" aria-label="Invitaciones recibidas">
          {invitations.map((invitation) => (
            <li key={invitation.idGrupoUsuario} className="member-row">
              <span>
                <b>{invitation.nombreGrupo}</b>
                <small>
                  {' '}
                  · Invita {invitation.nombreAdministrador ?? 'el administrador'} · {formatDateTime(invitation.fechaInvitacion)}
                </small>
                <br />
                <Badge tone={invitation.estado === 'VENCIDA' ? 'neutral' : 'success'}>
                  {invitation.estado === 'VENCIDA'
                    ? `Vencida el ${formatDateTime(invitation.fechaVencimiento)}`
                    : `Pendiente · vence el ${formatDateTime(invitation.fechaVencimiento)}`}
                </Badge>
              </span>
              {invitation.estado === 'PENDIENTE' && (
                <span className="member-actions">
                  {confirmingId === invitation.idGrupoUsuario ? (
                    <span className="invitation-confirm" role="alertdialog" aria-label={`Unirte a ${invitation.nombreGrupo}`}>
                      <span className="field-hint">
                        <ShieldCheck size={14} aria-hidden="true" /> Unirte <b>no comparte tus mediciones</b>: después
                        elegís qué compartir desde «Mi privacidad».
                      </span>
                      <button type="button" className="btn btn-primary" disabled={busy} onClick={() => respond(invitation, true)}>
                        {busy && <span className="spinner" aria-hidden="true" />} Confirmar y unirme
                      </button>
                      <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => setConfirmingId(null)}>
                        Volver
                      </button>
                    </span>
                  ) : (
                    <>
                      <button type="button" className="btn btn-primary" disabled={busy}
                        onClick={() => setConfirmingId(invitation.idGrupoUsuario)}
                        aria-label={`Aceptar invitación a ${invitation.nombreGrupo}`}>
                        <Check size={16} aria-hidden="true" /> Aceptar
                      </button>
                      <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => respond(invitation, false)}
                        aria-label={`Rechazar invitación a ${invitation.nombreGrupo}`}>
                        <X size={16} aria-hidden="true" /> Rechazar
                      </button>
                    </>
                  )}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function GroupsHome() {
  const { account } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  // undefined = consultando; null = sin grupo; objeto = grupo activo (se entra directo a su panel).
  const [mine, setMine] = useState(undefined);
  const [invitations, setInvitations] = useState([]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');
  const individual = account.usuario.tipoCuenta === 'CONSUMIDOR_FINAL';

  // La pertenencia la decide el backend. Solo si no hay grupo se piden las invitaciones recibidas.
  const load = useCallback(async () => {
    try {
      const { grupo } = await groupsApi.getMyGroup();
      if (grupo) {
        setMine(grupo);
        return;
      }
      setInvitations(await groupsApi.getReceivedInvitations());
      setError('');
      setMine(null);
    } catch (loadError) {
      // Un error de consulta no es «sin grupo»: no se ofrece crear uno (podría ya tenerlo).
      setError(friendlyError(loadError));
    }
  }, []);

  useEffect(() => {
    if (individual) load();
  }, [individual, load]);

  if (!individual) return <Navigate to="/app/inicio" replace />;

  // Un usuario pertenece como máximo a un grupo activo: se entra directo a su panel, sin pantalla intermedia.
  if (mine) return <Navigate to={`/app/grupo/${mine.idGrupo}`} replace state={location.state} />;

  function openGroup(group, notice) {
    navigate(`/app/grupo/${group.idGrupo}`, { replace: true, state: { notice } });
  }

  function retry() {
    setError('');
    load();
  }

  if (mine === undefined) {
    return error ? (
      <div className="page institution-page">
        <Alert>{error}</Alert>
        <div className="form-actions">
          <button type="button" className="btn btn-outline" onClick={retry}>Reintentar</button>
        </div>
      </div>
    ) : (
      <div className="auth-status" role="status">
        <span className="spinner" aria-hidden="true" /> Cargando tu grupo…
      </div>
    );
  }

  const pending = invitations.filter((invitation) => invitation.estado === 'PENDIENTE').length;
  return (
    <div className="page institution-page">
      <PageHeader title="Grupo" description="Compartí, si querés, información de tus mediciones con las personas de tu grupo. Vos decidís qué y cuándo." />
      {location.state?.notice && <Alert kind="success">{location.state.notice}</Alert>}

      {creating ? (
        <CreateGroupForm onCancel={() => setCreating(false)}
          onCreated={(group) => openGroup(group, `Creaste «${group.nombre}». Invitá a quienes quieras sumar.`)} />
      ) : (
        <section className="panel" aria-labelledby="grupo-sin">
          <div className="panel-title">
            <span className="panel-icon">
              <Users size={22} aria-hidden="true" />
            </span>
            <div>
              <h2 id="grupo-sin">Todavía no formás parte de un grupo</h2>
              <p>Podés crear uno o unirte con una invitación. Solo podés pertenecer a un grupo a la vez.</p>
            </div>
          </div>
          <div className="group-options">
            <article className="group-option">
              <span className="panel-icon"><Plus size={22} aria-hidden="true" /></span>
              <h3>Crear un grupo</h3>
              <p>Vas a ser el administrador o la administradora e invitás por correo a las personas que quieras sumar.</p>
              <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
                <Plus size={18} aria-hidden="true" /> Crear grupo
              </button>
            </article>
            <article className="group-option">
              <span className="panel-icon"><MailOpen size={22} aria-hidden="true" /></span>
              <h3>Unirme a un grupo</h3>
              <p>El administrador de un grupo te invita con tu correo y la invitación aparece abajo. Aceptarla no comparte tus mediciones.</p>
              <Badge tone={pending > 0 ? 'success' : 'neutral'}>
                {pending > 0 ? `${pending} invitación${pending === 1 ? '' : 'es'} pendiente${pending === 1 ? '' : 's'}` : 'Sin invitaciones por ahora'}
              </Badge>
            </article>
          </div>
        </section>
      )}
      <ReceivedInvitations invitations={invitations} reload={load}
        onAccepted={(group) => openGroup(group, `Te uniste a «${group.nombre}». Elegí en «Mi privacidad» qué querés compartir.`)} />
    </div>
  );
}
