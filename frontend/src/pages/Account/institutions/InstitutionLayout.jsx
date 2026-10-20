// /app/instituciones/:idInstitucion: panel de una institución. Carga el detalle (rol y permisos vigentes) desde
// el backend y muestra solo las secciones que el rol permite. Cualquier 403/404 en una operación vuelve a
// cargar el detalle: si el rol cambió o la institución se eliminó, la interfaz no conserva permisos obsoletos.

import { ArrowLeft, Building2, Crown, Tag } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, Navigate, Outlet, useLocation, useParams } from 'react-router-dom';

import * as institutionsApi from '../../../api/institutionsApi.js';
import { useAuth } from '../../../auth/AuthContext.jsx';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Badge } from '../../../components/Badge.jsx';
import { Alert } from '../../../components/FormControls.jsx';
import { ROLE_LABELS, typeLabel } from './institutionFormat.js';
import { SECTION_LABELS, useInstitutionNav } from './institutionMenu.js';
import './InstitutionPanel.css';

const STATE_LABELS = { ACTIVA: 'Activa', INACTIVA: 'Inactiva', CERRADA: 'Cerrada' };

const SUB_LABELS = { moderadores: 'Moderadores', operadores: 'Operadores', invitaciones: 'Invitaciones', datos: 'Datos', configuracion: 'Configuración', transferencias: 'Transferencias' };

const DETAIL_LABELS = { transferencias: 'Detalle de la transferencia', operadores: 'Detalle del operador' };

/** Migas de la sección actual (sin la institución): «Administración / Auditoría / Detalle del evento». */
function breadcrumbs(pathname, idInstitucion) {
  const base = `/app/instituciones/${idInstitucion}`;
  const [section, sub, detail] = pathname.split(`/${idInstitucion}`)[1]?.split('/').filter(Boolean) ?? [];
  if (!section || section === 'panel') return [{ label: 'Panel' }];
  if (section === 'administracion' && (!sub || sub === 'datos')) return [{ label: 'Datos institucionales' }];
  const crumbs = [{ label: SECTION_LABELS[section] ?? section, to: `${base}/${section}` }];
  if (section === 'personal' && sub === 'perfil') return [...crumbs, { label: 'Perfil del trabajador' }];
  if (section === 'auditoria' && sub) return [...crumbs, { label: 'Detalle del evento' }]; // auditoria/:idEvento
  if (sub && SUB_LABELS[sub]) crumbs.push({ label: SUB_LABELS[sub], to: `${base}/${section}/${sub}` });
  if (detail) crumbs.push({ label: DETAIL_LABELS[sub] ?? 'Detalle' });
  else if (sub === 'nuevo') crumbs.push({ label: 'Nuevo paciente' });
  else if (sub && !SUB_LABELS[sub]) crumbs.push({ label: 'Detalle' }); // pacientes/:id, dispositivos/:id, matrices/:id...
  return crumbs;
}

export default function InstitutionLayout() {
  const { idInstitucion } = useParams();
  const { account } = useAuth();
  const location = useLocation();
  const { setCurrent } = useInstitutionNav();
  const [institution, setInstitution] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const institutional = account.usuario.tipoCuenta === 'USUARIO_INSTITUCIONAL';

  const reload = useCallback(async () => {
    try {
      setInstitution(await institutionsApi.getInstitution(idInstitucion));
      setLoadError(null);
    } catch (error) {
      setInstitution(null);
      setLoadError(error);
    }
  }, [idInstitucion]);

  useEffect(() => {
    setInstitution(null);
    setLoadError(null);
    if (institutional) reload();
  }, [institutional, reload]);

  /** Para las secciones: ante un rechazo de permisos o una institución inexistente, se refresca el rol. */
  const handleOperationError = useCallback(
    (error) => {
      if (error?.status === 403 || error?.status === 404) reload();
      return friendlyError(error);
    },
    [reload],
  );

  // El sidebar muestra el submenú de la institución abierta; al salir de ella se limpia.
  useEffect(() => {
    setCurrent(institution ? { idInstitucion: institution.idInstitucion, nombre: institution.nombre, permisos: institution.permisos } : null);
  }, [institution, setCurrent]);
  useEffect(() => () => setCurrent(null), [setCurrent]);

  if (!institutional) return <Navigate to="/app/inicio" replace />;

  if (loadError) {
    return (
      <div className="page institution-page">
        <Alert>
          {loadError.status === 404
            ? 'Esta institución no está disponible: no pertenecés a ella o fue eliminada.'
            : friendlyError(loadError)}
        </Alert>
        <Link to="/app/instituciones" className="btn btn-outline">
          <ArrowLeft size={18} aria-hidden="true" /> Volver a instituciones
        </Link>
      </div>
    );
  }

  if (!institution) {
    return (
      <div className="auth-status" role="status">
        <span className="spinner" aria-hidden="true" /> Cargando la institución…
      </div>
    );
  }

  const crumbs = breadcrumbs(location.pathname, idInstitucion);
  const onPanel = /^\/app\/instituciones\/[^/]+(\/panel)?\/?$/.test(location.pathname);

  return (
    <div className="page institution-page">
      <nav className="breadcrumbs" aria-label="Ruta de navegación">
        <ol>
          <li><Link to="/app/instituciones">Instituciones</Link></li>
          <li><Link to={`/app/instituciones/${idInstitucion}`}>{institution.nombre}</Link></li>
          {crumbs.map((crumb, index) => (
            <li key={crumb.label} aria-current={index === crumbs.length - 1 ? 'page' : undefined}>
              {index === crumbs.length - 1 || !crumb.to ? crumb.label : <Link to={crumb.to}>{crumb.label}</Link>}
            </li>
          ))}
        </ol>
      </nav>
      <header className="institution-head">
        {/* Dentro de una sección vuelve al panel de la institución (no la deja); solo desde el panel vuelve a la lista de instituciones. */}
        <Link to={onPanel ? '/app/instituciones' : `/app/instituciones/${idInstitucion}`} className="icon-button"
          aria-label={onPanel ? 'Volver a instituciones' : 'Volver al panel'}>
          <ArrowLeft size={18} aria-hidden="true" />
        </Link>
        <span className="panel-icon is-lg" aria-hidden="true"><Building2 size={28} /></span>
        <div className="institution-head-text">
          <h1 title={institution.nombre}>{institution.nombre}</h1>
          <p className="institution-chips">
            <Badge tone="neutral" size="sm" icon={Tag}>{typeLabel(institution.tipoInstitucion)}</Badge>
            <Badge tone="brand" size="sm" icon={Crown}>{ROLE_LABELS[institution.rolInstitucion]}</Badge>
            <Badge tone={institution.estado === 'ACTIVA' ? 'success' : 'warning'} size="sm" dot>{STATE_LABELS[institution.estado] ?? institution.estado}</Badge>
          </p>
        </div>
      </header>

      {location.state?.notice && <Alert kind="success">{location.state.notice}</Alert>}

      <Outlet context={{ institution, reload, handleOperationError }} />
    </div>
  );
}
