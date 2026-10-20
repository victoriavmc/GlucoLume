// Invitaciones enviadas por la institución: pendientes, aceptadas, rechazadas, canceladas y vencidas. Solo las aceptadas son personal
// (enlazan al perfil); el resto nunca se incorporó y por eso no figura en Personal. Desde acá se reenvía o se cancela una invitación
// sin responder (pendiente o vencida). Cancelar no es desvincular: no borra nada y la auditoría se conserva.

import { Filter, MailPlus, RotateCw, XCircle } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useLocation, useOutletContext } from 'react-router-dom';

import * as institutionsApi from '../../../api/institutionsApi.js';
import { Badge, toneFromClass } from '../../../components/Badge.jsx';
import { EmptyState } from '../../../components/EmptyState.jsx';
import { Alert, SelectField } from '../../../components/FormControls.jsx';
import { ROLE_LABELS } from './institutionFormat.js';
import { when } from './personnelFormat.js';
import './Personnel.css';

export const INVITATION_STATES = {
  PENDIENTE: { label: 'Pendiente', tone: 'is-warn' },
  ACEPTADA: { label: 'Aceptada', tone: 'is-on' },
  RECHAZADA: { label: 'Rechazada', tone: 'is-denied' },
  CANCELADA: { label: 'Cancelada', tone: 'is-off' },
  VENCIDA: { label: 'Vencida', tone: 'is-denied' },
};

export function PersonnelInvitationsPage() {
  const { institution, handleOperationError } = useOutletContext();
  const location = useLocation();
  const [state, setState] = useState('');
  const [page, setPage] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [confirming, setConfirming] = useState(null);
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);
  const base = `/app/instituciones/${institution.idInstitucion}`;

  useEffect(() => {
    let active = true;
    institutionsApi.listSentInvitations(institution.idInstitucion, state ? { estado: state } : {}).then(
      (result) => active && (setPage(result), setError('')),
      (loadError) => active && (setError(handleOperationError(loadError)), setPage({ items: [], total: 0, resumen: {} })),
    );
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [institution.idInstitucion, state, version]);

  async function act(kind, invitation) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      if (kind === 'resend') {
        await institutionsApi.resendInvitation(institution.idInstitucion, invitation.rolInstitucion, invitation.idInstitucionUsuario);
        setNotice(`Reenviamos la invitación a ${invitation.nombreCompleto}.`);
      } else {
        await institutionsApi.revokeMember(institution.idInstitucion, invitation.rolInstitucion, invitation.idInstitucionUsuario);
        setNotice(`Cancelaste la invitación de ${invitation.nombreCompleto}. No forma parte del personal.`);
      }
      setConfirming(null);
      setVersion((current) => current + 1);
    } catch (actionError) {
      setError(handleOperationError(actionError));
    } finally {
      setBusy(false);
    }
  }

  const summary = page?.resumen ?? {};
  return (
    <div className="personnel">
      <section className="panel" aria-labelledby="invitaciones-titulo">
        <div className="panel-head">
          <div className="panel-title">
            <span className="panel-icon is-lg" aria-hidden="true"><MailPlus size={26} /></span>
            <div>
              <h2 id="invitaciones-titulo">Invitaciones</h2>
              <p>Invitaciones enviadas por la institución. Solo quien acepta pasa a formar parte del personal.</p>
            </div>
          </div>
        </div>
        <ul className="invitation-counts" aria-label="Invitaciones por estado">
          {Object.entries(INVITATION_STATES).map(([key, info]) => (
            <li key={key}><Badge tone={toneFromClass(info.tone)}>{info.label}</Badge> <b>{summary[key] ?? 0}</b></li>
          ))}
        </ul>
      </section>

      {notice && <Alert kind="success">{notice}</Alert>}
      {error && <Alert>{error}</Alert>}

      <section className="panel" aria-labelledby="invitaciones-listado">
        <div className="panel-head"><h2 id="invitaciones-listado">Invitaciones enviadas</h2></div>
        <form className="personnel-filters" aria-label="Filtros de invitaciones" onSubmit={(event) => event.preventDefault()}>
          <SelectField label="Estado" value={state} onChange={(event) => { setPage(null); setState(event.target.value); }}>
            <option value="">Todos los estados</option>
            {Object.entries(INVITATION_STATES).map(([key, info]) => <option key={key} value={key}>{info.label}</option>)}
          </SelectField>
          {state && (
            <button type="button" className="btn btn-ghost" onClick={() => { setPage(null); setState(''); }}>
              <Filter size={16} aria-hidden="true" /> Limpiar filtros
            </button>
          )}
        </form>

        {page === null ? (
          <p className="field-hint" role="status">Cargando invitaciones…</p>
        ) : page.items.length === 0 ? (
          <EmptyState icon={MailPlus} headingLevel={0} title={state ? 'No hay invitaciones con ese estado.' : 'Todavía no se enviaron invitaciones.'} />
        ) : (
          <div className="table-scroll">
            <table className="data-table personnel-table" aria-label="Invitaciones de la institución">
              <thead>
                <tr>
                  <th scope="col">Persona</th><th scope="col">Rol</th><th scope="col">Estado</th><th scope="col">Enviada</th>
                  <th scope="col">Vencimiento o respuesta</th><th scope="col"><span className="sr-only">Acciones</span></th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((invitation) => {
                  const info = INVITATION_STATES[invitation.estado];
                  const response = invitation.fechaRespuesta ?? invitation.fechaVencimiento;
                  return (
                    <tr key={invitation.idInstitucionUsuario}>
                      <th scope="row" data-label="Persona">
                        <span className="person-cell"><b>{invitation.nombreCompleto}</b>{invitation.correoElectronico && <small>{invitation.correoElectronico}</small>}</span>
                      </th>
                      <td data-label="Rol"><Badge tone="brand">{ROLE_LABELS[invitation.rolInstitucion]}</Badge></td>
                      <td data-label="Estado">
                        <Badge tone={toneFromClass(info.tone)}>{info.label}</Badge>
                        {invitation.estado === 'PENDIENTE' && invitation.cuentaPendiente && <small className="person-before">Cuenta pendiente de activación</small>}
                      </td>
                      <td data-label="Enviada">{when(invitation.fechaInvitacion)}{invitation.invitadoPor && <small className="person-before">Por {invitation.invitadoPor}</small>}</td>
                      <td data-label="Vencimiento o respuesta" className={response ? undefined : 'is-empty'}>
                        {response ? `${invitation.fechaRespuesta ? '' : 'Vence: '}${when(response)}` : 'No disponible'}
                      </td>
                      <td className="audit-actions">
                        {confirming === invitation.idInstitucionUsuario ? (
                          <>
                            <span className="field-hint">¿Cancelar la invitación?</span>
                            <button type="button" className="btn btn-primary" disabled={busy} onClick={() => act('cancel', invitation)}>Confirmar</button>
                            <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => setConfirming(null)}>Volver</button>
                          </>
                        ) : (
                          <>
                            {invitation.idPersonal && (
                              <Link to={`${base}/personal/perfil/${invitation.idPersonal}`} state={{ from: location.pathname, search: location.search }}
                                className="btn btn-ghost" aria-label={`Ver perfil de ${invitation.nombreCompleto}`}>Ver perfil</Link>
                            )}
                            {invitation.puedeReenviar && (
                              <button type="button" className="btn btn-outline" disabled={busy} onClick={() => act('resend', invitation)}
                                aria-label={`Reenviar invitación a ${invitation.nombreCompleto}`}>
                                <RotateCw size={16} aria-hidden="true" /> Reenviar
                              </button>
                            )}
                            {invitation.puedeCancelar && (
                              <button type="button" className="btn btn-outline risk-button" onClick={() => setConfirming(invitation.idInstitucionUsuario)}
                                aria-label={`Cancelar invitación de ${invitation.nombreCompleto}`}>
                                <XCircle size={16} aria-hidden="true" /> Cancelar
                              </button>
                            )}
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
