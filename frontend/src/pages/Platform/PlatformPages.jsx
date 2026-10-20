// Páginas del panel de Administración de GlucoLume. Todo sale de FastAPI (/platform/*), que valida el rol real y exige MFA;
// las acciones sensibles piden reautenticación (contraseña + código MFA). Nunca se muestran contraseñas, tokens ni datos
// personales de pacientes: el dashboard es agregado.

import { ArrowLeft, CreditCard, KeyRound, Mail, Plus, Users } from 'lucide-react';
import { useCallback, useEffect, useId, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';

import * as platformApi from '../../api/platformApi.js';
import { useAuth } from '../../auth/AuthContext.jsx';
import { friendlyError } from '../../auth/errorMessages.js';
import { Badge } from '../../components/Badge.jsx';
import { EmptyState } from '../../components/EmptyState.jsx';
import { Alert, CheckField, SelectField, SubmitButton, TextField } from '../../components/FormControls.jsx';
import { PageHeader } from '../../components/PageHeader.jsx';
import { ReauthFields, useReauth } from '../../components/Reauth.jsx';
import { TrendChart } from '../../components/TrendChart.jsx';
import { BarList, Kpi, KpiGrid, PeriodFilter, periodLabel } from '../../components/dashboard.jsx';
import { usePlatform } from '../../layouts/PlatformLayout.jsx';
import { passwordMeetsPolicy } from '../../utils/validation.js';
import { formatInstant } from '../../utils/dateTime.js';
import { formatDate } from '../Account/groups/groupFormat.js';
import { LoginNoticeSection } from '../Account/security/LoginNoticeSection.jsx';
import { CreatePasswordForm } from '../Account/security/PasswordSection.jsx';
import { MfaSection } from '../Account/security/MfaSection.jsx';
import { PasswordRules } from '../Register/RegisterForm.jsx';
import ProfilePage from '../Account/ProfilePage.jsx';

const ACCESS = {
  INVITADO: ['Invitación enviada', 'info'], INVITACION_VENCIDA: ['Invitación vencida', 'warning'], ACTIVO: ['Activo', 'success'],
  ACTIVO_SIN_MFA: ['Activo, falta MFA', 'warning'], REVOCADO: ['Acceso revocado', 'danger'],
};
const STATES = { COMPLETADA: 'Completadas', CANCELADA: 'Canceladas', INVALIDA: 'Inválidas', PENDIENTE: 'Pendientes', ADQUIRIENDO: 'Adquiriendo', PROCESANDO: 'Procesando' };
const COMPONENT_TONE = { OPERATIVO: 'success', NO_CONFIGURADO: 'warning', CON_ERROR: 'danger' };
const COMPONENT_LABEL = { OPERATIVO: 'Operativo', NO_CONFIGURADO: 'No configurado', CON_ERROR: 'Con error' };

const accessBadge = (moderator) => <Badge tone={ACCESS[moderator.estadoAcceso][1]}>{ACCESS[moderator.estadoAcceso][0]}</Badge>;

const fullName = (person) => [person?.nombre, person?.apellido].filter(Boolean).join(' ') || 'Sin nombre';

// --- Moderadores -------------------------------------------------------------------------------------------------


/** Panel de confirmación con reautenticación para una acción sensible sobre un moderador. */
function ActionPanel({ title, confirmLabel, me, onConfirm, onCancel }) {
  const reauth = useReauth(me.tieneCredencialLocal);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault();
    if (reauth.missing || busy) {
      setError('Ingresá tu contraseña y el código de verificación de 6 dígitos.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await onConfirm(reauth.body());
    } catch (actionError) {
      setError(friendlyError(actionError));
      setBusy(false);
    }
  }
  return (
    <form className="panel action-panel" onSubmit={submit} noValidate aria-label={title}>
      <h3 className="member-list-title">{title}</h3>
      {error && <Alert>{error}</Alert>}
      <ReauthFields reauth={reauth} hasPassword={me.tieneCredencialLocal} idPrefix={`re-${title.length}`} />
      <div className="form-actions">
        <SubmitButton loading={busy} loadingLabel="Confirmando…">{confirmLabel}</SubmitButton>
        <button type="button" className="btn btn-ghost" disabled={busy} onClick={onCancel}>Cancelar</button>
      </div>
    </form>
  );
}

function InviteForm({ me, onInvited, onCancel }) {
  const reauth = useReauth(me.tieneCredencialLocal);
  const [form, setForm] = useState({ nombre: '', apellido: '', correoElectronico: '' });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const update = (field) => (event) => setForm((current) => ({ ...current, [field]: event.target.value }));

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    const next = {};
    if (!form.nombre.trim()) next.nombre = 'Ingresá el nombre.';
    if (!form.apellido.trim()) next.apellido = 'Ingresá el apellido.';
    if (!/^\S+@\S+\.\S+$/.test(form.correoElectronico.trim())) next.correoElectronico = 'Ingresá un correo electrónico válido.';
    setErrors(next);
    if (Object.keys(next).length) return;
    if (reauth.missing) {
      setError('Ingresá tu contraseña y el código de verificación de 6 dígitos.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      onInvited(await platformApi.inviteModerator({
        nombre: form.nombre.trim(), apellido: form.apellido.trim(), correoElectronico: form.correoElectronico.trim(), reautenticacion: reauth.body(),
      }));
    } catch (inviteError) {
      setError(friendlyError(inviteError));
      setBusy(false);
    }
  }

  return (
    <form className="panel" onSubmit={submit} noValidate aria-labelledby="mod-alta">
      <h2 id="mod-alta">Agregar moderador del sistema</h2>
      <p className="field-hint">El rol es siempre «Moderador del sistema». La persona recibe un correo, elige su usuario y su contraseña y activa MFA.</p>
      {error && <Alert>{error}</Alert>}
      <div className="form-grid">
        <TextField label="Nombre" maxLength={100} value={form.nombre} onChange={update('nombre')} error={errors.nombre} />
        <TextField label="Apellido" maxLength={100} value={form.apellido} onChange={update('apellido')} error={errors.apellido} />
        <TextField label="Correo electrónico" icon={Mail} maxLength={254} value={form.correoElectronico} onChange={update('correoElectronico')} error={errors.correoElectronico} />
      </div>
      <ReauthFields reauth={reauth} hasPassword={me.tieneCredencialLocal} idPrefix="invite" />
      <div className="form-actions">
        <SubmitButton loading={busy} loadingLabel="Enviando invitación…">Enviar invitación</SubmitButton>
        <button type="button" className="btn btn-ghost" disabled={busy} onClick={onCancel}>Cancelar</button>
      </div>
    </form>
  );
}

const ACTIONS = {
  resend: { title: 'Reenviar la invitación', confirm: 'Reenviar', run: platformApi.resendInvitation, done: 'Reenviamos la invitación.' },
  revoke: { title: 'Revocar el acceso', confirm: 'Revocar acceso', run: platformApi.revokeModerator, done: 'Revocaste el acceso del moderador.' },
  reset: { title: 'Restablecer la contraseña', confirm: 'Enviar enlace', run: platformApi.resetModeratorPassword, done: 'Enviamos el enlace de restablecimiento al correo del moderador.' },
};

function ModeratorActions({ moderator, me, onDone }) {
  const [action, setAction] = useState(null);
  const access = moderator.estadoAcceso;
  const options = [
    ['resend', ['INVITADO', 'INVITACION_VENCIDA'].includes(access)],
    ['reset', ['ACTIVO', 'ACTIVO_SIN_MFA'].includes(access) && moderator.tieneCredencialLocal],
    ['revoke', access !== 'REVOCADO'],
  ].filter(([, enabled]) => enabled);
  return (
    <>
      <div className="member-actions">
        {options.map(([key]) => (
          <button key={key} type="button" className="btn btn-outline" onClick={() => setAction(key)}
            aria-label={`${ACTIONS[key].title}: ${fullName(moderator)}`}>{ACTIONS[key].title}</button>
        ))}
      </div>
      {action && (
        <ActionPanel title={`${ACTIONS[action].title}: ${fullName(moderator)}`} confirmLabel={ACTIONS[action].confirm} me={me}
          onCancel={() => setAction(null)}
          onConfirm={async (reauthBody) => {
            const result = await ACTIONS[action].run(moderator.idUsuario, reauthBody);
            setAction(null);
            onDone(ACTIONS[action].done, result.moderador ?? result);
          }} />
      )}
    </>
  );
}

export function ModeratorsPage() {
  const { me } = usePlatform();
  const [moderators, setModerators] = useState(null);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setModerators(await platformApi.listModerators());
    } catch (loadError) {
      setError(friendlyError(loadError));
      setModerators([]);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <>
      <PageHeader title="Moderadores del sistema"
        description="Cuentas con funciones técnicas delegadas sobre GlucoLume. No son personal de ninguna institución." />
      {notice && <Alert kind="success">{notice}</Alert>}
      {error && <Alert>{error}</Alert>}
      {!adding && <div><button type="button" className="btn btn-primary" onClick={() => { setNotice(''); setAdding(true); }}><Plus size={16} aria-hidden="true" /> Agregar moderador</button></div>}
      {adding && (
        <InviteForm me={me} onCancel={() => setAdding(false)}
          onInvited={(result) => { setAdding(false); setNotice(result.mensaje); load(); }} />
      )}
      <section className="panel" aria-labelledby="mod-lista">
        <div className="panel-title"><span className="panel-icon"><Users size={22} aria-hidden="true" /></span><div><h2 id="mod-lista">Listado</h2></div></div>
        {moderators === null ? <p className="field-hint" role="status">Cargando…</p> : moderators.length === 0 ? (
          <EmptyState variant="inline" icon={Users} headingLevel={0} title="Todavía no hay moderadores del sistema." />
        ) : (
          <ul className="member-list-items" aria-label="Moderadores del sistema">
            {moderators.map((moderator) => (
              <li key={moderator.idUsuario} className="member-row">
                <span>
                  <b>{fullName(moderator)}</b><small> · {moderator.correoElectronico}</small>
                  <br />
                  {accessBadge(moderator)}
                  <small> · MFA {moderator.mfaHabilitado ? 'activa' : 'sin activar'}</small>
                  {moderator.invitacionVence && <small> · La invitación vence {formatInstant(moderator.invitacionVence)}</small>}
                  <br />
                  <Link to={moderator.idUsuario} className="text-link">Ver datos administrativos</Link>
                </span>
                <ModeratorActions moderator={moderator} me={me}
                  onDone={(message) => { setNotice(message); load(); }} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

export function ModeratorDetailPage() {
  const { me } = usePlatform();
  const { idUsuario } = useParams();
  const [moderator, setModerator] = useState(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    platformApi.getModerator(idUsuario).then(setModerator, (loadError) => setError(friendlyError(loadError)));
  }, [idUsuario]);

  return (
    <>
      <Link to=".." relative="path" className="back-link"><ArrowLeft size={16} aria-hidden="true" /> Moderadores del sistema</Link>
      <PageHeader title="Detalle del moderador" description="Datos administrativos de la cuenta y acciones disponibles." />
      {error && <Alert>{error}</Alert>}
      {notice && <Alert kind="success">{notice}</Alert>}
      {moderator && (
        <section className="panel" aria-labelledby="mod-datos">
          <div className="panel-head">
            <h2 id="mod-datos">{fullName(moderator)}</h2>
            {accessBadge(moderator)}
          </div>
          <dl className="data-list">
            <div><dt>Correo electrónico</dt><dd>{moderator.correoElectronico}</dd></div>
            <div><dt>Nombre de usuario</dt><dd className={moderator.usuario ? undefined : 'is-empty'}>{moderator.usuario ?? 'Todavía no lo eligió'}</dd></div>
            <div><dt>Rol</dt><dd>Moderador del sistema</dd></div>
            <div><dt>Verificación en dos pasos</dt><dd>{moderator.mfaHabilitado ? 'Activa' : 'Sin activar'}</dd></div>
            <div><dt>Inicio de sesión</dt><dd>{[moderator.tieneCredencialLocal && 'Contraseña', moderator.tieneGoogle && 'Google'].filter(Boolean).join(' y ') || 'Sin credenciales'}</dd></div>
            <div><dt>Alta</dt><dd>{formatInstant(moderator.fechaCreacion)}</dd></div>
            <div><dt>Último acceso</dt><dd className={moderator.ultimoAcceso ? undefined : 'is-empty'}>{moderator.ultimoAcceso ? formatInstant(moderator.ultimoAcceso) : 'Nunca'}</dd></div>
          </dl>
          <ModeratorActions moderator={moderator} me={me}
            onDone={(message, updated) => { setNotice(message); setModerator(updated); }} />
        </section>
      )}
    </>
  );
}

// --- Transferencia del control --------------------------------------------------------------------------------------


const TRANSFER_STATES = { PENDIENTE: 'Pendiente', ACEPTADA: 'Aceptada', RECHAZADA: 'Rechazada', CANCELADA: 'Cancelada' };
const TRANSFER_TONES = { PENDIENTE: 'warning', ACEPTADA: 'success', RECHAZADA: 'danger', CANCELADA: 'neutral' };

export function TransferPage() {
  const { me, reload } = usePlatform();
  const navigate = useNavigate();
  const [overview, setOverview] = useState(null);
  const [target, setTarget] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [mode, setMode] = useState(null); // 'start' | 'cancel' | 'accept' | 'reject'
  const isAdmin = me.rol === 'ADMINISTRADOR_PLATAFORMA';

  const load = useCallback(async () => {
    try {
      setOverview(await platformApi.getTransfer());
    } catch (loadError) {
      setError(friendlyError(loadError));
      setOverview({ pendiente: null, elegibles: [], historial: [] });
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const pending = overview?.pendiente;
  const run = async (reauthBody) => {
    if (mode === 'start') await platformApi.startTransfer(target, reauthBody);
    if (mode === 'cancel') await platformApi.cancelTransfer(reauthBody);
    if (mode === 'reject') await platformApi.rejectTransfer(reauthBody);
    if (mode === 'accept') {
      await platformApi.acceptTransfer(reauthBody);
      await reload(); // el rol cambió: el panel se reconstruye con los permisos nuevos
      navigate('/plataforma/dashboard', { replace: true });
      return;
    }
    setNotice({ start: 'Solicitamos la transferencia. Hasta que el moderador acepte no cambia ningún permiso.', cancel: 'Cancelaste la transferencia.', reject: 'Rechazaste la administración.' }[mode]);
    setMode(null);
    setTarget('');
    setConfirmed(false);
    await Promise.all([load(), reload()]);
  };

  return (
    <>
      <PageHeader title="Transferir administración"
        description="Pasá el control principal de GlucoLume a un moderador del sistema activo. El cambio rige recién cuando acepta." />
      {notice && <Alert kind="success">{notice}</Alert>}
      {error && <Alert>{error}</Alert>}
      {overview === null ? <p className="field-hint" role="status">Cargando…</p> : (
        <>
          {pending && (
            <section className="panel" aria-labelledby="tr-pendiente">
              <h2 id="tr-pendiente">Transferencia pendiente</h2>
              <p>
                {pending.esDestino
                  ? <><b>{pending.origenNombre}</b> te ofrece el control principal de GlucoLume. Si aceptás pasás a ser el administrador del sistema y quien te la ofrece queda como moderador.</>
                  : <>Esperando la respuesta de <b>{pending.destinoNombre}</b>. Solicitada el {formatInstant(pending.fechaSolicitud)}.</>}
              </p>
              {!mode && pending.esDestino && (
                <div className="form-actions">
                  <button type="button" className="btn btn-primary" onClick={() => setMode('accept')}>Aceptar</button>
                  <button type="button" className="btn btn-outline" onClick={() => setMode('reject')}>Rechazar</button>
                </div>
              )}
              {!mode && pending.esOrigen && (
                <div className="form-actions"><button type="button" className="btn btn-outline" onClick={() => setMode('cancel')}>Cancelar la solicitud</button></div>
              )}
            </section>
          )}
          {isAdmin && !pending && (
            <section className="panel" aria-labelledby="tr-nueva">
              <h2 id="tr-nueva">Elegir al nuevo administrador</h2>
              {overview.elegibles.length === 0 ? (
                <EmptyState variant="inline" icon={Users} headingLevel={0} title="No hay moderadores del sistema elegibles"
                  description="Tienen que estar activos y haber activado MFA." />
              ) : (
                <>
                  <SelectField label="Moderador del sistema" value={target} onChange={(event) => setTarget(event.target.value)}>
                    <option value="">Elegí un moderador</option>
                    {overview.elegibles.map((m) => <option key={m.idUsuario} value={m.idUsuario}>{fullName(m)}</option>)}
                  </SelectField>
                  <Alert kind="info">
                    Al aceptar, esa persona pasa a ser la única administradora del sistema y vos quedás como moderador del sistema. Las
                    instituciones, usuarios, dispositivos, matrices y la auditoría se conservan. No se transfiere la propiedad de datos de pacientes.
                  </Alert>
                  <CheckField label="Entiendo y quiero transferir la administración" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
                  {!mode && <div className="form-actions"><button type="button" className="btn btn-primary" disabled={!target || !confirmed} onClick={() => setMode('start')}>Continuar</button></div>}
                </>
              )}
            </section>
          )}
          {!isAdmin && !pending && <Alert kind="info">Solo el administrador del sistema puede transferir el control. Si te ofrecen la administración, la vas a ver acá.</Alert>}
          {mode && (
            <ActionPanel
              title={{ start: 'Confirmar la transferencia', cancel: 'Cancelar la transferencia', accept: 'Aceptar la administración', reject: 'Rechazar la administración' }[mode]}
              confirmLabel={{ start: 'Solicitar transferencia', cancel: 'Cancelar solicitud', accept: 'Aceptar', reject: 'Rechazar' }[mode]}
              me={me} onCancel={() => setMode(null)} onConfirm={run} />
          )}
          {isAdmin && overview.historial.length > 0 && (
            <section className="panel" aria-labelledby="tr-historial">
              <h2 id="tr-historial">Historial</h2>
              <ul className="member-list-items" aria-label="Historial de transferencias">
                {overview.historial.map((t) => (
                  <li key={t.idTransferenciaAdministracion} className="member-row">
                    <span><b>{t.origenNombre}</b> → <b>{t.destinoNombre}</b><small> · {formatInstant(t.fechaSolicitud)}</small></span>
                    <Badge tone={TRANSFER_TONES[t.estado] ?? 'neutral'}>{TRANSFER_STATES[t.estado]}</Badge>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </>
  );
}

// --- Suscripciones y pagos ------------------------------------------------------------------------------------------


export function SubscriptionsPage() {
  return (
    <>
      <PageHeader title="Suscripciones y pagos" description="Sección reservada para una próxima etapa." />
      <section className="panel" aria-labelledby="sub-prox">
        <div className="panel-title"><span className="panel-icon"><CreditCard size={22} aria-hidden="true" /></span><div><h2 id="sub-prox">Próximamente</h2></div></div>
        <p>
          Todavía no está disponible: no hay cobros, suscripciones, facturación ni integraciones con proveedores de pago. Cuando
          se incorpore, se va a gestionar desde acá.
        </p>
      </section>
    </>
  );
}

// --- Cuenta ---------------------------------------------------------------------------------------------------------------


export function PlatformProfilePage() {
  const { me } = usePlatform();
  return (
    <>
      <ProfilePage />
      <section className="panel" aria-labelledby="pl-rol">
        <h2 id="pl-rol">Tu rol en GlucoLume</h2>
        <dl className="data-list">
          <div><dt>Rol</dt><dd>{me.rolEtiqueta}</dd></div>
          <div><dt>Verificación en dos pasos</dt><dd>{me.mfaHabilitado ? 'Activa' : 'Sin activar'}</dd></div>
        </dl>
      </section>
    </>
  );
}

export function PlatformSecurityPage() {
  const { account } = useAuth();
  const location = useLocation();
  return (
    <>
      <PageHeader title="Seguridad y MFA" description="La administración exige verificación en dos pasos." />
      {location.state?.notice && <Alert kind="info">{location.state.notice}</Alert>}
      <p><Link to="/plataforma/cambiar-contrasena" className="btn btn-outline"><KeyRound size={16} aria-hidden="true" /> Cambiar contraseña</Link></p>
      <MfaSection account={account} />
      <LoginNoticeSection account={account} />
    </>
  );
}

export function PlatformPasswordPage() {
  const { me, reload } = usePlatform();
  const [created, setCreated] = useState(false);
  const rulesId = useId();
  const [form, setForm] = useState({ actual: '', nueva: '', confirmacion: '', codigo: '' });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState('');
  const [done, setDone] = useState('');
  const [busy, setBusy] = useState(false);
  const update = (field) => (event) => setForm((current) => ({ ...current, [field]: event.target.value }));

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    const next = {};
    if (me.tieneCredencialLocal && !form.actual) next.actual = 'Ingresá tu contraseña actual.';
    if (!passwordMeetsPolicy(form.nueva)) next.nueva = 'La contraseña no cumple todos los requisitos.';
    if (form.confirmacion !== form.nueva) next.confirmacion = 'Las contraseñas no coinciden.';
    if (!/^\d{6}$/.test(form.codigo.trim())) next.codigo = 'Ingresá el código de 6 dígitos.';
    setErrors(next);
    if (Object.keys(next).length) return;
    setBusy(true);
    setError('');
    try {
      const result = await platformApi.changePassword({
        ...(me.tieneCredencialLocal ? { passwordActual: form.actual } : {}), passwordNueva: form.nueva, confirmacion: form.confirmacion, codigo: form.codigo.trim(),
      });
      setDone(result.mensaje);
      setForm({ actual: '', nueva: '', confirmacion: '', codigo: '' });
    } catch (changeError) {
      setError(friendlyError(changeError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Cambiar contraseña" description="Cerramos tus otras sesiones al cambiarla." />
      {created && (
        <Alert kind="success">Contraseña creada con éxito. Te enviamos un correo para confirmarlo y ya podés ingresar también con tu correo o usuario.</Alert>
      )}
      {!me.tieneCredencialLocal ? (
        <section className="panel" aria-labelledby="pw-crear">
          <h2 id="pw-crear">Crear contraseña</h2>
          <p className="field-hint">
            Tu cuenta ingresa con Google. Podés crear una contraseña para ingresar también con tu correo o usuario.
            Para operar el panel seguirás necesitando la verificación en dos pasos (MFA).
          </p>
          <CreatePasswordForm onCreated={() => { setCreated(true); reload(); }} />
        </section>
      ) : (
        <form className="panel" onSubmit={submit} noValidate aria-labelledby="pw-titulo">
          <h2 id="pw-titulo">Nueva contraseña</h2>
          {done && <Alert kind="success">{done}</Alert>}
          {error && <Alert>{error}</Alert>}
          <TextField label="Contraseña actual" revealable autoComplete="current-password" maxLength={128} value={form.actual} onChange={update('actual')} error={errors.actual} />
          <TextField label="Contraseña nueva" revealable autoComplete="new-password" maxLength={128} value={form.nueva} onChange={update('nueva')} error={errors.nueva} aria-describedby={rulesId} />
          <PasswordRules value={form.nueva} id={rulesId} />
          <TextField label="Confirmar contraseña nueva" revealable autoComplete="new-password" maxLength={128} value={form.confirmacion} onChange={update('confirmacion')} error={errors.confirmacion} />
          <TextField label="Código de verificación (6 dígitos)" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={form.codigo}
            onChange={(event) => setForm((current) => ({ ...current, codigo: event.target.value.replace(/\D/g, '') }))} error={errors.codigo} />
          <div className="form-actions"><SubmitButton loading={busy} loadingLabel="Guardando…">Cambiar contraseña</SubmitButton></div>
        </form>
      )}
    </>
  );
}
