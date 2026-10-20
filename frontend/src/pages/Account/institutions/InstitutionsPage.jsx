// /app/instituciones: inicio institucional de una cuenta USUARIO_INSTITUCIONAL.
// Invitaciones recibidas, instituciones en las que tiene un vínculo activo (0..N, con su rol) y creación.
// Una cuenta institucional sin instituciones no es un error: puede crear una o aceptar una invitación.

import { ArrowRight, Building2, Plus } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';

import * as institutionsApi from '../../../api/institutionsApi.js';
import { useAuth } from '../../../auth/AuthContext.jsx';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Badge } from '../../../components/Badge.jsx';
import { Alert } from '../../../components/FormControls.jsx';
import { PageHeader } from '../../../components/PageHeader.jsx';
import { CreateInstitutionForm } from './CreateInstitutionForm.jsx';
import { ROLE_LABELS, typeLabel } from './institutionFormat.js';
import { InvitationsSection } from './InvitationsSection.jsx';
import { PausedInstitutionNotice } from './PausedSupport.jsx';
import './InstitutionsList.css';

export default function InstitutionsPage() {
  const { account } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [items, setItems] = useState(null);
  const [error, setError] = useState('');
  const [creating, setCreating] = useState(false);
  const [sent, setSent] = useState('');
  const notice = location.state?.notice ?? '';
  const institutional = account.usuario.tipoCuenta === 'USUARIO_INSTITUCIONAL';

  const load = useCallback(async () => {
    setError('');
    try {
      setItems(await institutionsApi.getMyInstitutions({ includePaused: true })); // las pausadas se listan para explicar por qué no se pueden abrir
    } catch (loadError) {
      setError(friendlyError(loadError));
      setItems([]);
    }
  }, []);

  useEffect(() => {
    if (institutional) load();
  }, [institutional, load]);

  // Solo las cuentas institucionales trabajan con instituciones.
  if (!institutional) return <Navigate to="/app/inicio" replace />;

  function handleCreated(result) {
    const notice = result.operacion === 'REABIERTA'
      ? `Reabriste «${result.nombre}» (reapertura n.º ${result.cantidadReaperturas}). Designá moderadores para el nuevo período.`
      : `Creaste «${result.nombre}». Ya podés designar moderadores.`;
    navigate(`/app/instituciones/${result.idInstitucion}`, { state: { notice } });
  }

  function openCreate() {
    navigate('.', { replace: true, state: null });
    setCreating(true);
  }

  return (
    <div className="page institution-page">
      <PageHeader title="Instituciones" description="Las instituciones con las que trabajás y tu rol en cada una."
        actions={items !== null && items.length > 0 && !creating ? (
          <button type="button" className="btn btn-outline" onClick={openCreate}>
            <Plus size={18} aria-hidden="true" /> Crear otra institución
          </button>
        ) : undefined} />

      {error && <Alert>{error}</Alert>}
      {notice && <Alert kind="success">{notice}</Alert>}
      {sent && <Alert kind="success">{sent}</Alert>}

      <InvitationsSection onAccepted={load} />

      {items === null && (
        <div className="auth-status" role="status">
          <span className="spinner" aria-hidden="true" /> Cargando tus instituciones…
        </div>
      )}

      {items !== null && items.length === 0 && !creating && (
        <section className="panel" aria-labelledby="sin-instituciones">
          <div className="panel-title">
            <span className="panel-icon">
              <Building2 size={22} aria-hidden="true" />
            </span>
            <div>
              <h2 id="sin-instituciones">Cuenta institucional</h2>
              <p>Todavía no estás vinculado a ninguna institución.</p>
            </div>
          </div>
          <p className="mfa-text">
            Podés crear una institución y quedar como propietario/a, o esperar a que una institución te invite: la
            invitación llega a <b>{account.usuario.correoElectronico}</b> y aparece en esta pantalla para que la aceptes.
          </p>
          <div className="form-actions">
            <button type="button" className="btn btn-primary" onClick={openCreate}>
              <Plus size={18} aria-hidden="true" /> Crear una institución
            </button>
          </div>
        </section>
      )}

      {creating && <CreateInstitutionForm onCreated={handleCreated} onCancel={() => setCreating(false)} />}

      {items !== null && items.length > 0 && (
        <ul className="summary-grid institution-list institutions-grid" aria-label="Tus instituciones">
          {items.map((item) => item.estado === 'INACTIVA' ? (
            <li key={item.idInstitucion}>
              <div className="summary-card is-paused" aria-label={`${item.nombre}: institución pausada`}>
                <span className="panel-icon">
                  <Building2 size={22} aria-hidden="true" />
                </span>
                <small>{typeLabel(item.tipoInstitucion)}</small>
                <b>{item.nombre}</b>
                <Badge tone="warning">Pausada</Badge>
                <PausedInstitutionNotice institution={item}
                  onSent={() => setSent('Enviamos tu consulta al soporte de GlucoLume. Te respondemos al correo de tu cuenta.')} />
              </div>
            </li>
          ) : (
            <li key={item.idInstitucion}>
              <Link to={`/app/instituciones/${item.idInstitucion}`} className="summary-card">
                <span className="panel-icon">
                  <Building2 size={22} aria-hidden="true" />
                </span>
                <small>{typeLabel(item.tipoInstitucion)}</small>
                <b>{item.nombre}</b>
                <Badge tone="brand">{ROLE_LABELS[item.rolInstitucion]}</Badge>
                <span className="summary-link">
                  Abrir panel <ArrowRight size={16} aria-hidden="true" />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}

    </div>
  );
}
