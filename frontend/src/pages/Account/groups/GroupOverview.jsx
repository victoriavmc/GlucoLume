// Panel y listado de integrantes del grupo. Nombre visible, rol, fecha, estado y qué permisos de compartición
// habilitó cada uno (Compartido / No compartido): nunca correos ni los datos en sí. Los datos se consultan desde
// «Datos compartidos», solo los autorizados. El administrador puede desvincular integrantes (con confirmación).

import { ArrowRight, ChevronRight, Eye, Settings, ShieldCheck, UserMinus, UserPlus, Users } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useOutletContext } from 'react-router-dom';

import * as groupsApi from '../../../api/groupsApi.js';
import { Badge } from '../../../components/Badge.jsx';
import { Alert } from '../../../components/FormControls.jsx';
import { Avatar, GroupDashboardSection, SharingBadges } from './GroupDashboard.jsx';
import { GroupInvitations } from './GroupInvitations.jsx';
import { ROLE_LABELS, formatDate, personName, sharesAnything } from './groupFormat.js';

function QuickAccess({ to, icon: Icon, title, subtitle, description, action }) {
  return (
    <Link to={to} className="gd-quick">
      <span className="gd-quick-icon"><Icon size={24} aria-hidden="true" /></span>
      <span className="gd-quick-body">
        <small>{title}</small>
        <b>{subtitle}</b>
        <span>{description}</span>
        <span className="gd-quick-action">{action} <ArrowRight size={16} aria-hidden="true" /></span>
      </span>
      <ChevronRight size={18} className="gd-quick-chevron" aria-hidden="true" />
    </Link>
  );
}

export function GroupOverview() {
  const { group, isAdmin } = useOutletContext();
  // Nombre, administrador, rol e integrantes ya están en el encabezado del grupo: no se repiten.
  return (
    <>
      <section className="gd-quick-grid" aria-label="Accesos del grupo">
        <QuickAccess to="privacidad" icon={ShieldCheck} title="Mi privacidad" subtitle="Elegí qué compartir"
          description="Decidí qué información de tus mediciones puede ver el grupo." action="Configurar" />
        <QuickAccess to="compartidos" icon={Eye} title="Datos compartidos" subtitle="Lo que otros te habilitaron"
          description="Revisá la información que comparten contigo." action="Ver" />
        {isAdmin ? (
          <QuickAccess to="integrantes" icon={UserPlus} title="Invitaciones" subtitle="Invitar personas"
            description="Sumá familiares o personas de confianza al grupo." action="Invitar" />
        ) : (
          <QuickAccess to="integrantes" icon={Users} title="Integrantes" subtitle={`${group.cantidadIntegrantes} en el grupo`}
            description="Mirá quiénes forman el grupo y qué comparte cada uno." action="Ver" />
        )}
      </section>
      <GroupDashboardSection />
    </>
  );
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
        {error && <Alert>{error}</Alert>}
        {notice && <Alert kind="success">{notice}</Alert>}
        {members === null ? (
          <p className="field-hint" role="status">Cargando…</p>
        ) : (
          <ul className="gd-members is-list" aria-label="Integrantes del grupo">
            {members.map((member) => (
              <li key={member.idGrupoUsuario} className="gd-member">
                <div className="gd-member-head">
                  <Avatar person={member} tone={member.rol === 'ADMINISTRADOR' ? 'rose' : 'violet'} />
                  <span className="gd-member-name">
                    <b>{personName(member)}{member.esVos && ' (vos)'}</b>
                    <Badge tone={member.rol === 'ADMINISTRADOR' ? 'brand' : 'info'}>{ROLE_LABELS[member.rol]}</Badge>
                  </span>
                </div>
                <p className="gd-member-since"><span className="gd-dot" aria-hidden="true" /> Activo · desde {formatDate(member.fechaIncorporacion)}</p>
                <SharingBadges member={member} columns />
                <div className="gd-member-actions">
                  {member.esVos ? (
                    <Link to="../privacidad" relative="path" className="btn btn-outline">
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
