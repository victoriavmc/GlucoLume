// Perfil institucional de una persona del personal: encabezado, datos personales e institucionales, información profesional, fechas de
// vinculación (invitación, cuenta, incorporación, última modificación y baja: son hechos distintos) y el historial institucional, una
// línea de tiempo administrativa y laboral (no incluye mediciones). Todo viene de /personnel/{id}; las acciones dependen de los permisos
// que informa el backend y FastAPI las vuelve a validar. «Volver a Personal» regresa a la pestaña y los filtros de donde se llegó.

import {
  ArrowLeft, BadgeCheck, Briefcase, CalendarClock, History, Pencil, RotateCw, Trash2, UserMinus, UserRound,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useOutletContext, useParams } from 'react-router-dom';

import * as institutionsApi from '../../../api/institutionsApi.js';
import { Badge, toneFromClass } from '../../../components/Badge.jsx';
import { Alert } from '../../../components/FormControls.jsx';
import { Modal } from '../../../components/Modal.jsx';
import { OffboardOperator } from './OffboardOperator.jsx';
import { EditMemberForm, FUNCTION_LABELS } from './PersonnelForms.jsx';
import './Personnel.css';
import { ROLE_LABELS } from './institutionFormat.js';
import { RELATION_STATES, initials, stateInfo, when } from './personnelFormat.js';

function Row({ label, value, empty = 'Sin informar' }) {
  return <div><dt>{label}</dt><dd className={value ? undefined : 'is-empty'}>{value || empty}</dd></div>;
}

function Card({ id, icon: Icon, title, children }) {
  return (
    <section className="panel" aria-labelledby={id}>
      <div className="panel-title">
        <span className="panel-icon" aria-hidden="true"><Icon size={22} /></span>
        <h2 id={id}>{title}</h2>
      </div>
      {children}
    </section>
  );
}

export function PersonnelProfilePage() {
  const { institution, reload, handleOperationError } = useOutletContext();
  const { idPersona } = useParams();
  const location = useLocation();
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [confirmingErase, setConfirmingErase] = useState(false);
  const [offboarding, setOffboarding] = useState(null); // plan de reasignación (o true: lo consulta el propio diálogo) cuando el operador tiene pacientes
  const [busy, setBusy] = useState(false);
  const base = `/app/instituciones/${institution.idInstitucion}`;
  const back = (
    <Link to={{ pathname: location.state?.from ?? `${base}/personal`, search: location.state?.search ?? '' }} className="back-link">
      <ArrowLeft size={16} aria-hidden="true" /> Volver a Personal
    </Link>
  );

  const load = useCallback(async () => {
    try {
      setProfile(await institutionsApi.getPersonnelProfile(institution.idInstitucion, idPersona));
      setError('');
    } catch (loadError) {
      setError(handleOperationError(loadError));
    }
  }, [institution.idInstitucion, idPersona, handleOperationError]);

  useEffect(() => {
    setProfile(null);
    load();
  }, [load]);

  if (error && !profile) return <>{back}<Alert>{error}</Alert></>;
  if (!profile) return <>{back}<p className="field-hint" role="status">Cargando el perfil…</p></>;

  const info = stateInfo(profile);
  const rol = profile.rolInstitucion;
  const ended = profile.estadoRelacion === 'BAJA';
  const pending = profile.estadoRelacion === 'PENDIENTE';
  const actions = profile.acciones;

  // Un operador activo con pacientes a cargo no se desvincula directamente: antes hay que reasignarlos (el backend también lo exige).
  async function startRevoke() {
    setNotice('');
    if (pending || rol !== 'OPERADOR') {
      setConfirming(true);
      return;
    }
    setBusy(true);
    setError('');
    try {
      const plan = await institutionsApi.getOperatorOffboarding(institution.idInstitucion, profile.idInstitucionUsuario);
      if (plan.cantidadPacientes > 0) setOffboarding(plan); else setConfirming(true);
    } catch (planError) {
      setError(handleOperationError(planError));
    } finally {
      setBusy(false);
    }
  }

  async function act(kind) {
    setBusy(true);
    setError('');
    try {
      if (kind === 'resend') {
        await institutionsApi.resendInvitation(institution.idInstitucion, rol, profile.idInstitucionUsuario);
        setNotice(`Reenviamos la invitación a ${profile.nombreCompleto}.`);
      } else if (kind === 'erase') {
        await institutionsApi.erasePersonnelData(institution.idInstitucion, profile.idInstitucionUsuario);
        setNotice(`Eliminaste a ${profile.nombreCompleto} del personal. Queda registrado como eliminado, sin identificar a la persona.`);
        setConfirmingErase(false);
      } else {
        await institutionsApi.revokeMember(institution.idInstitucion, rol, profile.idInstitucionUsuario);
        setNotice(pending ? `Cancelaste la invitación de ${profile.nombreCompleto}.` : `${profile.nombreCompleto} ya no forma parte de la institución.`);
        setConfirming(false);
        await reload();
      }
      await load();
    } catch (actionError) {
      if (actionError?.codigo === 'PACIENTES_ASIGNADOS') { // llegó a tener pacientes mientras se confirmaba: se pasa a la reasignación
        setConfirming(false);
        setOffboarding(true);
      } else {
        setError(handleOperationError(actionError));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="personnel-profile">
      {back}
      {notice && <Alert kind="success">{notice}</Alert>}
      {error && <Alert>{error}</Alert>}

      <section className="panel person-head" aria-labelledby="persona-nombre">
        <span className="person-avatar" aria-hidden="true">{initials(profile)}</span>
        <div className="person-head-text">
          <h2 id="persona-nombre">{profile.nombreCompleto}</h2>
          <p className="person-badges">
            <Badge tone="brand">{ROLE_LABELS[rol]}</Badge>
            <Badge tone={toneFromClass(info.tone)}>{info.label}</Badge>
            {profile.rolesAnteriores.length > 0 && <small>Antes: {profile.rolesAnteriores.map((r) => ROLE_LABELS[r]).join(', ')}</small>}
          </p>
          <p className="field-hint">
            {ended ? `${profile.datosEliminados ? 'Eliminado. Dado de baja' : 'Dado de baja'} el ${when(profile.fechaBaja)}. No tiene accesos a la institución.`
              : pending ? 'Todavía no se incorporó: no tiene accesos a la institución.'
                : `Integra la institución desde el ${when(profile.fechaIncorporacion)}.`}
          </p>
        </div>
        {(actions.puedeEditar || actions.puedeDesvincular || actions.puedeReenviar || actions.puedeVerDashboard || actions.puedeEliminarDatos) && !editing && (
          <div className="person-actions">
            {confirming ? (
              <>
                <span className="field-hint">{pending ? '¿Cancelar la invitación?' : '¿Quitarle el acceso a la institución?'}</span>
                <button type="button" className="btn btn-primary" disabled={busy} onClick={() => act('revoke')}>
                  {busy && <span className="spinner" aria-hidden="true" />} Confirmar
                </button>
                <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => setConfirming(false)}>Volver</button>
              </>
            ) : (
              <>
                {actions.puedeVerDashboard && <Link to={`${base}/personal/operadores/${profile.idInstitucionUsuario}`} className="btn btn-outline">Ver dashboard</Link>}
                {actions.puedeEditar && (
                  <button type="button" className="btn btn-outline" onClick={() => { setNotice(''); setEditing(true); }} aria-label={`Editar datos de ${profile.nombreCompleto}`}>
                    <Pencil size={16} aria-hidden="true" /> Editar datos
                  </button>
                )}
                {actions.puedeReenviar && (
                  <button type="button" className="btn btn-outline" disabled={busy} onClick={() => act('resend')} aria-label={`Reenviar invitación a ${profile.nombreCompleto}`}>
                    <RotateCw size={16} aria-hidden="true" /> Reenviar invitación
                  </button>
                )}
                {actions.puedeDesvincular && (
                  <button type="button" className="btn btn-outline risk-button" disabled={busy} onClick={startRevoke}
                    aria-label={`${pending ? 'Cancelar invitación de' : 'Desvincular a'} ${profile.nombreCompleto}`}>
                    <UserMinus size={16} aria-hidden="true" /> {pending ? 'Cancelar invitación' : 'Desvincular'}
                  </button>
                )}
                {actions.puedeEliminarDatos && (
                  <button type="button" className="btn btn-outline risk-button" onClick={() => { setNotice(''); setConfirmingErase(true); }}
                    aria-label={`Eliminar a ${profile.nombreCompleto}`}>
                    <Trash2 size={16} aria-hidden="true" /> Eliminar
                  </button>
                )}
              </>
            )}
          </div>
        )}
      </section>

      {offboarding && (
        <OffboardOperator institution={institution} operatorId={profile.idInstitucionUsuario} operatorName={profile.nombreCompleto}
          initialPlan={offboarding === true ? null : offboarding} onClose={() => setOffboarding(null)}
          onDone={async (result) => {
            setOffboarding(null);
            setNotice(`Reasignamos ${result.reasignados === 1 ? '1 paciente' : `${result.reasignados} pacientes`} y ${profile.nombreCompleto} ya no forma parte de la institución.`);
            await reload();
            await load();
          }} />
      )}

      {confirmingErase && (
        <Modal title="¿Eliminar a esta persona?" onClose={busy ? () => {} : () => setConfirmingErase(false)}
          actions={(
            <>
              <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => setConfirmingErase(false)}>Cancelar</button>
              <button type="button" className="btn btn-primary risk-button" disabled={busy} aria-busy={busy || undefined} onClick={() => act('erase')}>
                {busy && <span className="spinner" aria-hidden="true" />} Aceptar y eliminar
              </button>
            </>
          )}>
          <p>
            ¿Estás seguro de que querés eliminar a <b>{profile.nombreCompleto}</b> del personal? Se borran su nombre profesional, legajo y matrícula y
            <b> no se puede deshacer</b>.
          </p>
          <p className="field-hint">
            Si cancelás, la persona sigue como «Dado de baja». Si aceptás, queda como «Eliminado»: se conservan su rol y sus fechas para la trazabilidad
            de las mediciones y de la auditoría, pero ya no se la identifica.
          </p>
        </Modal>
      )}

      {editing && (
        <EditMemberForm institution={institution} rol={rol} member={profile} handleOperationError={handleOperationError}
          onCancel={() => setEditing(false)}
          onSaved={() => { setEditing(false); setNotice(`Guardamos los datos de ${profile.nombreCompleto} en la institución.`); load(); }} />
      )}

      <div className="personnel-cards">
        <Card id="persona-datos" icon={UserRound} title="Información personal e institucional">
          <dl className="data-list">
            <Row label="Nombre" value={profile.nombre} />
            <Row label="Apellido" value={profile.apellido} />
            <Row label="Nombre completo" value={profile.nombreCompleto} />
            <Row label="Correo electrónico" value={profile.correoElectronico} empty="No disponible" />
            <Row label="Institución" value={profile.nombreInstitucion} />
            <Row label="Rol institucional actual" value={ROLE_LABELS[rol]} />
            <Row label="Estado de la relación" value={RELATION_STATES[profile.estadoRelacion] ?? profile.estadoRelacion} />
          </dl>
        </Card>

        <Card id="persona-profesional" icon={Briefcase} title="Información profesional">
          <dl className="data-list">
            <Row label="Legajo institucional" value={profile.legajoInstitucional} />
            <Row label="Matrícula profesional" value={profile.matriculaProfesional} />
            <Row label="Función profesional" value={FUNCTION_LABELS[profile.funcionProfesional]} />
            <Row label="Nombre profesional registrado" value={[profile.nombreProfesionalHistorico, profile.apellidoProfesionalHistorico].filter(Boolean).join(' ')} />
          </dl>
        </Card>

        <Card id="persona-fechas" icon={CalendarClock} title="Fechas de vinculación">
          <dl className="data-list">
            <Row label="Invitación enviada" value={profile.origenVinculo === 'CREACION_INSTITUCION' ? null : when(profile.fechaInvitacion)}
              empty={profile.origenVinculo === 'CREACION_INSTITUCION' ? 'No corresponde: creó la institución' : 'No disponible'} />
            <Row label="Invitada por" value={profile.invitadoPor} empty="No corresponde" />
            <Row label="Cuenta de GlucoLume creada" value={when(profile.fechaCuentaCreada)} empty="No disponible" />
            <Row label="Aceptación e incorporación" value={when(profile.fechaIncorporacion)} empty={pending ? 'Todavía no ocurrió' : 'No disponible'} />
            {pending && <Row label="La invitación vence" value={when(profile.fechaVencimientoInvitacion)} empty="No disponible" />}
            <Row label="Última modificación administrativa" value={when(profile.fechaUltimaModificacion)} empty="Todavía no se modificó" />
            {ended && <Row label="Fecha de baja" value={when(profile.fechaBaja)} empty="No disponible" />}
          </dl>
        </Card>

        {profile.periodosAnteriores.length > 0 && (
          <Card id="persona-periodos" icon={BadgeCheck} title="Períodos anteriores en la institución">
            <ul className="period-list" aria-label="Períodos anteriores">
              {profile.periodosAnteriores.map((period) => (
                <li key={period.idInstitucionUsuario}>
                  <b>{ROLE_LABELS[period.rolInstitucion]}</b>
                  <Badge tone={toneFromClass(stateInfo(period).tone)}>{RELATION_STATES[period.estadoRelacion] ?? period.estadoRelacion}</Badge>
                  <small>
                    Invitación: {when(period.fechaInvitacion)} · Incorporación: {when(period.fechaIncorporacion, 'Todavía no ocurrió')}
                    {period.fechaBaja && ` · Baja: ${when(period.fechaBaja)}`}
                  </small>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>

      <Card id="persona-historial" icon={History} title="Historial institucional">
        <p className="field-hint">Acontecimientos administrativos de la persona en la institución, del más reciente al más antiguo.</p>
        {profile.historial.length === 0 ? (
          <p className="field-hint">Todavía no hay acontecimientos registrados.</p>
        ) : (
          <ol className="timeline" aria-label="Historial institucional">
            {profile.historial.map((event, index) => (
              <li key={`${event.tipo}-${event.fechaHora}-${index}`}>
                <time className="timeline-date" dateTime={event.fechaHora}>{when(event.fechaHora)}</time>
                <b>{event.titulo}</b>
                {event.descripcion && <p>{event.descripcion}</p>}
                <small>
                  {event.realizadoPor ? `Realizada por: ${event.realizadoPor}` : 'Responsable no registrado'}
                  {' · '}<Badge tone={event.resultado === 'EXITO' ? 'success' : 'danger'}>{event.resultado === 'EXITO' ? 'Exitoso' : 'Fallido'}</Badge>
                  {event.origen === 'REGISTRO' && ' · según las fechas del vínculo'}
                </small>
              </li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
}
