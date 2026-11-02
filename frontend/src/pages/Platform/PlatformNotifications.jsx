// Notificaciones de la Administración de GlucoLume: la bandeja real de la cuenta (la misma de «Notificaciones» de la app, /api/v1/notificaciones)
// y un catálogo de ideas de avisos. Las ideas marcadas como «Activa» ya llegan a esta bandeja; las demás son propuestas.
// Ninguna notificación incluye datos de salud, nombres de pacientes ni valores de glucosa: solo referencias administrativas o técnicas.

import { Bell, Building2, CheckCheck, ClipboardList, Cpu, CreditCard, Server, ShieldCheck, UserCog } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import * as notificationsApi from '../../api/notificationsApi.js';
import { friendlyError } from '../../auth/errorMessages.js';
import { Badge } from '../../components/Badge.jsx';
import { EmptyState } from '../../components/EmptyState.jsx';
import { Alert } from '../../components/FormControls.jsx';
import { PageHeader } from '../../components/PageHeader.jsx';
import { formatInstant } from '../../utils/dateTime.js';

const INBOX_LIMIT = 20;

const PRIORITY = {
  critica: ['Crítica', 'danger'],
  alta: ['Alta', 'warning'],
  informativa: ['Informativa', 'info'],
};

// `eventos`: avisos del catálogo del backend que ya implementan esta idea. Sin eventos, la idea todavía es una propuesta.
const GROUPS = [
  { id: 'seguridad', title: 'Seguridad y acceso', icon: ShieldCheck, items: [
    { title: 'Inicio de sesión desde un dispositivo nuevo', priority: 'alta', channel: 'Correo y en la app', eventos: ['INICIO_SESION'],
      detail: 'Se registra un acceso desde un navegador o ubicación que la cuenta no usaba antes.',
      example: 'Se inició sesión en tu cuenta de administración desde un equipo nuevo. Si no fuiste vos, cambiá tu contraseña.' },
    { title: 'Cambio de contraseña', priority: 'critica', channel: 'Correo y en la app', eventos: ['CAMBIO_CONTRASENA'],
      detail: 'Se cambia la contraseña de una cuenta administrativa.',
      example: 'Se cambió la contraseña de tu cuenta. Si no fuiste vos, avisá de inmediato.' },
    { title: 'Cuenta bloqueada por intentos fallidos', priority: 'critica', channel: 'Correo y en la app', eventos: ['ACTIVIDAD_SOSPECHOSA'],
      detail: 'Se alcanza el umbral de intentos de contraseña o de código MFA incorrectos.',
      example: 'Se bloqueó temporalmente el acceso de una cuenta administrativa tras varios intentos fallidos.' },
    { title: 'Intento de ingreso rechazado', priority: 'alta', channel: 'En la app', eventos: ['INTENTO_INGRESO'],
      detail: 'Alguien intenta entrar con una contraseña o un código incorrectos.',
      example: 'Alguien intentó entrar a tu cuenta con datos incorrectos. Si no fuiste vos, revisá tu seguridad.' },
    { title: 'MFA desactivado', priority: 'critica', channel: 'Correo y en la app', eventos: ['CAMBIO_MFA'],
      detail: 'Cambia la verificación en dos pasos de una cuenta administrativa.',
      example: 'Se modificó la verificación en dos pasos de tu cuenta. Si no lo hiciste vos, revisá tu seguridad.' },
  ] },
  { id: 'moderadores', title: 'Moderadores y transferencias', icon: UserCog, items: [
    { title: 'Transferencia de administración', priority: 'critica', channel: 'En la app', eventos: ['PLATAFORMA_TRANSFERENCIA_SOLICITADA', 'PLATAFORMA_TRANSFERENCIA_RESPONDIDA'],
      detail: 'Se ofrece la administración a un moderador. Cuando responde, el administrador recibe el resultado.',
      example: 'Transferencia aceptada: el moderador aceptó la administración de GlucoLume.' },
    { title: 'Invitación de moderador aceptada', priority: 'informativa', channel: 'En la app', eventos: ['PLATAFORMA_MODERADOR_ACTIVO'],
      detail: 'Un moderador activa su cuenta con el enlace de invitación.',
      example: 'Un moderador activó su cuenta de moderación.' },
    { title: 'Invitación vencida sin activar', priority: 'informativa', channel: 'En la app',
      detail: 'Una invitación deja de ser válida sin usarse.',
      example: 'La invitación de un moderador venció sin activarse. Podés reenviarla desde Moderadores del sistema.' },
    { title: 'Moderador desvinculado o con permisos cambiados', priority: 'alta', channel: 'En la app',
      detail: 'Se quita un rol o se modifican permisos administrativos de una cuenta.',
      example: 'Se modificaron los permisos de un moderador del sistema.' },
  ] },
  { id: 'instituciones', title: 'Instituciones', icon: Building2, items: [
    { title: 'Nueva institución pendiente de revisión', priority: 'alta', channel: 'En la app',
      detail: 'Una institución se registra y necesita aprobación o datos de verificación.',
      example: 'Una nueva institución espera revisión para comenzar a operar.' },
    { title: 'Institución sin actividad', priority: 'informativa', channel: 'En la app',
      detail: 'Una institución activa no registra actividad durante un período definido.',
      example: 'La institución lleva 30 días sin actividad registrada.' },
    { title: 'Límite de licencias o de dispositivos alcanzado', priority: 'alta', channel: 'Correo y en la app',
      detail: 'Una institución llega al tope de su plan. Útil cuando existan suscripciones.',
      example: 'Una institución alcanzó el límite de dispositivos de su plan.' },
  ] },
  { id: 'dispositivos', title: 'Dispositivos y matrices', icon: Cpu, items: [
    { title: 'Dispositivo que dejó de sincronizar', priority: 'alta', channel: 'En la app',
      detail: 'Un dispositivo no envía datos dentro del tiempo esperado.',
      example: 'Un dispositivo no sincroniza desde hace 24 horas.' },
    { title: 'Dispositivo reportado con falla técnica', priority: 'alta', channel: 'En la app',
      detail: 'Se registra un error técnico o una falla de hardware en un dispositivo.',
      example: 'Se registró una falla técnica en un dispositivo global.' },
    { title: 'Matriz global publicada o modificada', priority: 'informativa', channel: 'En la app',
      detail: 'Una matriz cambia y puede afectar a las instituciones que la usan.',
      example: 'Se publicó una nueva versión de la matriz global de objetivos.' },
  ] },
  { id: 'auditoria', title: 'Auditoría y cumplimiento', icon: ClipboardList, items: [
    { title: 'Exportación de auditoría realizada', priority: 'alta', channel: 'Correo y en la app',
      detail: 'Alguien descarga un registro de auditoría o un listado con datos administrativos.',
      example: 'Se exportó el registro de auditoría global por una cuenta administrativa.' },
    { title: 'Acciones sensibles fuera de horario', priority: 'alta', channel: 'Correo',
      detail: 'Se ejecutan cambios de roles, transferencias o borrados en un horario inusual.',
      example: 'Se realizó un cambio sensible a las 03:12. Revisá la auditoría.' },
    { title: 'Retención de IP y política de privacidad', priority: 'informativa', channel: 'En la app',
      detail: 'Avisa cuando vence un plazo de retención técnica o cuando una nueva versión de la política requiere revisión.',
      example: 'La Política de privacidad cambió a una versión nueva. Revisala antes de continuar.' },
  ] },
  { id: 'sistema', title: 'Sistema y operación', icon: Server, items: [
    { title: 'Falla en un proceso programado', priority: 'critica', channel: 'Correo a administradores',
      detail: 'Fallan tareas automáticas como limpiezas, retenciones o envíos de correo.',
      example: 'La tarea de retención de datos técnicos terminó con error.' },
    { title: 'Respaldo de base de datos completado o fallido', priority: 'alta', channel: 'Correo',
      detail: 'Confirma que el respaldo se generó o avisa si no pudo completarse.',
      example: 'El respaldo nocturno no se completó. Revisá el servidor.' },
    { title: 'Pico anormal de errores o de llamadas', priority: 'alta', channel: 'Correo y en la app',
      detail: 'Aumentan de forma repentina los errores del servidor o las solicitudes a la API.',
      example: 'Los errores de la API superaron el umbral habitual durante 15 minutos.' },
  ] },
  { id: 'suscripciones', title: 'Suscripciones y pagos (próximamente)', icon: CreditCard, items: [
    { title: 'Pago rechazado', priority: 'critica', channel: 'Correo a la institución y al administrador',
      detail: 'Un cobro no se completa. Se incorpora cuando existan pagos.',
      example: 'El pago de la suscripción fue rechazado. Actualizá el medio de pago.' },
    { title: 'Suscripción próxima a vencer', priority: 'informativa', channel: 'Correo',
      detail: 'Avisa con anticipación antes de la renovación.',
      example: 'Tu suscripción se renueva en 7 días.' },
  ] },
];

function PriorityBadge({ priority }) {
  const [label, tone] = PRIORITY[priority] ?? PRIORITY.informativa;
  return <Badge tone={tone} size="sm">{label}</Badge>;
}

function StatusBadge({ live }) {
  return live ? <Badge tone="success" size="sm">Activa</Badge> : <Badge tone="neutral" size="sm">Próximamente</Badge>;
}

function Inbox() {
  const [state, setState] = useState({ status: 'loading', items: [], noLeidas: 0, error: '' });
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');

  const load = useCallback(async () => {
    try {
      const inbox = await notificationsApi.getNotifications({ limite: INBOX_LIMIT });
      setState({ status: 'ready', items: inbox.notificaciones, noLeidas: inbox.noLeidas, error: '' });
    } catch (error) {
      setState((current) => ({ ...current, status: 'error', error: friendlyError(error) }));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Cada acción vuelve a leer la bandeja: así el conteo y la lista salen del backend, no de una copia local.
  const run = async (action) => {
    setBusy(true);
    setActionError('');
    try {
      await action();
      await load();
    } catch (error) {
      setActionError(friendlyError(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel" aria-labelledby="not-bandeja">
      <div className="panel-title">
        <span className="panel-icon"><Bell size={22} aria-hidden="true" /></span>
        <div><h2 id="not-bandeja">Tu bandeja</h2>{state.status === 'ready' && <p className="field-hint">{state.noLeidas} sin leer</p>}</div>
      </div>
      {actionError && <Alert>{actionError}</Alert>}
      {state.status === 'loading' && <p className="field-hint" role="status">Cargando…</p>}
      {state.status === 'error' && <Alert>{state.error}</Alert>}
      {state.status === 'ready' && state.items.length === 0 && (
        <EmptyState variant="inline" icon={Bell} headingLevel={0} title="Todavía no llegó ningún aviso de la administración." />
      )}
      {state.status === 'ready' && state.items.length > 0 && (
        <>
          {state.noLeidas > 0 && (
            <p>
              <button type="button" className="btn btn-outline btn-sm" disabled={busy}
                onClick={() => run(notificationsApi.markAllNotificationsRead)}>
                <CheckCheck size={16} aria-hidden="true" /> Marcar todas como leídas
              </button>
            </p>
          )}
          <ul className="member-list-items" aria-label="Avisos de la administración">
            {state.items.map((aviso) => (
              <li key={aviso.idNotificacion} className="member-row">
                <span>
                  <b>{aviso.titulo}</b>{' '}
                  {aviso.leida ? <Badge size="sm">Leída</Badge> : <Badge tone="info" size="sm">Sin leer</Badge>}
                  <br />
                  <small>{aviso.mensaje}</small>
                  <br />
                  <small>{formatInstant(aviso.fechaCreacion)}</small>
                  {aviso.url && <><br /><Link to={aviso.url} className="text-link">Abrir</Link></>}
                </span>
                {!aviso.leida && (
                  <button type="button" className="btn btn-outline btn-sm" disabled={busy}
                    onClick={() => run(() => notificationsApi.markNotificationRead(aviso.idNotificacion))}>
                    Marcar como leída
                  </button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

export function PlatformNotificationsPage() {
  return (
    <>
      <PageHeader title="Notificaciones" description="Tus avisos de la administración y las ideas de lo que podría llegarte." />
      <Inbox />
      <section className="panel" aria-labelledby="not-reglas">
        <div className="panel-title"><span className="panel-icon"><Bell size={22} aria-hidden="true" /></span><div><h2 id="not-reglas">Cómo leer las ideas</h2></div></div>
        <ul>
          <li><PriorityBadge priority="critica" /> Requiere atención inmediata, por ejemplo un riesgo para una cuenta o un fallo de servicio.</li>
          <li><PriorityBadge priority="alta" /> Conviene revisarla en el día.</li>
          <li><PriorityBadge priority="informativa" /> Resumen o aviso de seguimiento, sin urgencia.</li>
          <li><StatusBadge live /> Ya llega a la bandeja de arriba.</li>
          <li><StatusBadge live={false} /> Propuesta: todavía no se envía.</li>
        </ul>
        <p className="field-hint">
          Ninguna notificación incluye datos de salud, nombres de pacientes ni valores de glucosa: solo referencias
          administrativas o técnicas.
        </p>
      </section>
      {GROUPS.map((group) => {
        const Icon = group.icon;
        return (
          <section key={group.id} className="panel" aria-labelledby={`not-${group.id}`}>
            <div className="panel-title"><span className="panel-icon"><Icon size={22} aria-hidden="true" /></span><div><h2 id={`not-${group.id}`}>{group.title}</h2></div></div>
            <ul className="member-list-items" aria-label={group.title}>
              {group.items.map((item) => (
                <li key={item.title} className="member-row">
                  <span>
                    <b>{item.title}</b> <PriorityBadge priority={item.priority} /> <StatusBadge live={Boolean(item.eventos)} />
                    <br />
                    <small>{item.detail}</small>
                    <br />
                    <small>Llega por: {item.channel}</small>
                    <br />
                    <small className="field-hint">Ejemplo: “{item.example}”</small>
                  </span>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </>
  );
}
