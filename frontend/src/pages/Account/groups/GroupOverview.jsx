// Panel y listado de integrantes del grupo. Nombre visible, rol, fecha de ingreso y qué permisos de compartición habilitó cada
// uno (Compartido / No compartido): nunca correos ni los datos en sí. «Ver datos compartidos» abre solo las secciones
// de esa persona, las que autorizó. El administrador puede invitar y desvincular integrantes (con confirmación).

import { Eye, Settings, UserMinus, UserPlus, Users } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useOutletContext } from 'react-router-dom';

import * as groupsApi from '../../../api/groupsApi.js';
import { Badge } from '../../../components/Badge.jsx';
import { Alert } from '../../../components/FormControls.jsx';
import { Avatar, GroupDashboardSection, SharingBadges } from './GroupDashboard.jsx';
import { GroupInvitations } from './GroupInvitations.jsx';
import { ROLE_LABELS, formatDate, personName, sharesAnything } from './groupFormat.js';

export function GroupOverview() {
  // Nombre, administrador, rol e integrantes ya están en el encabezado del grupo: no se repiten.
  return <GroupDashboardSection />;
}

export function GroupMembers() {
  const { group, isAdmin, reload, handleOperationError } = useOutletContext();
  const [members, setMembers] = useState(null);
  const [confirmingId, setConfirmingId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    try {
      setMembers(await groupsApi.listMembers(group.idGrupo));
    } catch (loadError) {
      setError(handleOperationError(loadError));
      setMembers([]);
    }
  }, [group.idGrupo, handleOperationError]);

  useEffect(() => {
    load();
  }, [load]);

  // Lleva al formulario «Invitar a una persona» y deja el cursor en el correo.
  function goToInvite() {
    const section = document.getElementById('grupo-invitar')?.closest('section');
    section?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
    section?.querySelector('input')?.focus();
  }

  async function remove(member) {
    setBusy(true);
    setError('');
    try {
      await groupsApi.removeMember(group.idGrupo, member.idGrupoUsuario);
      setNotice(`${personName(member)} ya no forma parte del grupo.`);
      setConfirmingId(null);
      await Promise.all([load(), reload()]);
    } catch (removeError) {
      setError(handleOperationError(removeError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {isAdmin && <GroupInvitations />}
      <section className="panel" aria-labelledby="grupo-integrantes">
        <div className="panel-title">
          <span className="panel-icon">
            <Users size={22} aria-hidden="true" />
          </span>
          <div>
            <h2 id="grupo-integrantes">Integrantes</h2>
            <p>Personas activas del grupo.</p>
          </div>
        </div>
        {isAdmin && (
          <div className="form-actions">
            <button type="button" className="btn btn-primary" onClick={goToInvite}>
              <UserPlus size={16} aria-hidden="true" /> Invitar
            </button>
          </div>
        )}
        {error && <Alert>{error}</Alert>}
        {notice && <Alert kind="success">{notice}</Alert>}
        {members === null ? (
          <p className="field-hint" role="status">Cargando…</p>
        ) : (
          <ul className="gd-members" aria-label="Integrantes del grupo">
            {members.map((member) => (
              <li key={member.idGrupoUsuario} className="gd-member">
                <div className="gd-member-head">
                  <div className="gd-member-id">
                    <Avatar person={member} tone={member.rol === 'ADMINISTRADOR' ? 'rose' : 'violet'} />
                    <span className="gd-member-name">
                      <b>{personName(member)}{member.esVos && ' (vos)'}</b>
                      <Badge tone={member.rol === 'ADMINISTRADOR' ? 'brand' : 'info'}>{ROLE_LABELS[member.rol]}</Badge>
                    </span>
                  </div>
                  <span className="gd-member-status">En el grupo desde {formatDate(member.fechaIncorporacion)}</span>
                </div>
                <SharingBadges member={member} />
                <div className="gd-member-actions">
                  {member.esVos ? (
                    <Link to="../privacidad" relative="path" className="btn btn-outline gd-member-solo">
                      <Settings size={16} aria-hidden="true" /> Cambiar mi privacidad
                    </Link>
                  ) : (
                    <>
                      {member.tienePerfil && sharesAnything(member) && (
                        <Link to={member.idGrupoUsuario} className="text-link">
                          <Eye size={16} aria-hidden="true" /> Ver datos compartidos
                        </Link>
                      )}
                      {isAdmin && (confirmingId === member.idGrupoUsuario ? (
                        <span className="member-actions">
                          <span className="field-hint">¿Quitar a {personName(member)} del grupo?</span>
                          <button type="button" className="btn btn-primary" disabled={busy} onClick={() => remove(member)}>
                            {busy && <span className="spinner" aria-hidden="true" />} Confirmar
                          </button>
                          <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => setConfirmingId(null)}>
                            Volver
                          </button>
                        </span>
                      ) : (
                        <button type="button" className="btn btn-outline gd-remove" onClick={() => { setNotice(''); setConfirmingId(member.idGrupoUsuario); }}
                          aria-label={`Desvincular a ${personName(member)}`}>
                          <UserMinus size={16} aria-hidden="true" /> Desvincular
                        </button>
                      ))}
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
