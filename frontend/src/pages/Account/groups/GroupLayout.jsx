// /app/grupo/:idGrupo: panel del grupo, al que /app/grupo redirige directo (no hay selector de grupos: cada cuenta
// pertenece como máximo a uno). Encabezado con nombre, rol y cantidad de integrantes, y pestañas debajo. Carga el
// detalle (rol vigente) desde el backend y muestra solo las secciones que corresponden. Ante un 403/404 en cualquier operación vuelve a cargar el detalle: si la persona dejó
// de pertenecer o el grupo se eliminó, la interfaz no conserva accesos obsoletos.

import { ArrowLeft, Database, Heart, Home, LayoutDashboard, Settings, ShieldCheck, User, Users } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, Navigate, Outlet, useLocation, useParams } from 'react-router-dom';

import * as groupsApi from '../../../api/groupsApi.js';
import { useAuth } from '../../../auth/AuthContext.jsx';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Badge } from '../../../components/Badge.jsx';
import { Alert } from '../../../components/FormControls.jsx';
import { NavTabs } from '../../../components/Tabs.jsx';
import { ROLE_LABELS } from './groupFormat.js';

const SECTIONS = [
  { to: '', label: 'Panel', end: true, icon: LayoutDashboard },
  { to: 'integrantes', label: 'Integrantes', icon: Users },
  { to: 'privacidad', label: 'Mi privacidad', icon: ShieldCheck },
  { to: 'compartidos', label: 'Datos compartidos', icon: Database },
  { to: 'configuracion', label: 'Configuración', icon: Settings },
];

export default function GroupLayout() {
  const { idGrupo } = useParams();
  const { account } = useAuth();
  const location = useLocation();
  const [group, setGroup] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const individual = account.usuario.tipoCuenta === 'CONSUMIDOR_FINAL';

  const reload = useCallback(async () => {
    try {
      setGroup(await groupsApi.getGroup(idGrupo));
      setLoadError(null);
    } catch (error) {
      setGroup(null);
      setLoadError(error);
    }
  }, [idGrupo]);

  useEffect(() => {
    setGroup(null);
    setLoadError(null);
    if (individual) reload();
  }, [individual, reload]);

  const handleOperationError = useCallback(
    (error) => {
      if (error?.status === 404 || (error?.status === 403 && error.codigo === 'PERMISO_INSUFICIENTE')) reload();
      return friendlyError(error);
    },
    [reload],
  );

  if (!individual) return <Navigate to="/app/inicio" replace />;

  if (loadError) {
    return (
      <div className="page institution-page">
        <Alert>
          {loadError.status === 404 ? 'Este grupo no está disponible: no formás parte de él o fue eliminado.' : friendlyError(loadError)}
        </Alert>
        {/* /app/grupo vuelve a consultar la pertenencia: lleva a su grupo actual o, si no tiene, a crear o unirse. */}
        <Link to="/app/grupo" className="btn btn-outline">
          <ArrowLeft size={18} aria-hidden="true" /> Ir a mi grupo
        </Link>
      </div>
    );
  }
  if (!group) {
    return (
      <div className="auth-status" role="status">
        <span className="spinner" aria-hidden="true" /> Cargando el grupo…
      </div>
    );
  }

  const isAdmin = group.miRol === 'ADMINISTRADOR';
  return (
    <div className="page institution-page">
      <header className="group-hero">
        <span className="panel-icon is-lg">
          <Users size={26} aria-hidden="true" />
        </span>
        <div className="group-hero-body">
          <h1>{group.nombre}</h1>
          {group.descripcion && <p className="group-hero-desc">{group.descripcion}</p>}
          <ul className="group-hero-meta" aria-label="Datos principales del grupo">
            <li><small>Tu rol</small> <Badge tone="brand">{ROLE_LABELS[group.miRol]}</Badge></li>
            <li><Users size={16} aria-hidden="true" /> <span><b>{group.cantidadIntegrantes}</b> integrante{group.cantidadIntegrantes === 1 ? '' : 's'}</span></li>
            {group.administrador && <li><User size={16} aria-hidden="true" /> <small>Administra</small> <b>{group.administrador}</b></li>}
          </ul>
        </div>
        <span className="group-hero-art" aria-hidden="true"><Home size={64} strokeWidth={1.4} /><Heart size={26} fill="currentColor" /></span>
      </header>
      {location.state?.notice && <Alert kind="success">{location.state.notice}</Alert>}
      <NavTabs label="Secciones del grupo" variant="underline"
        items={SECTIONS.filter((section) => !section.adminOnly || isAdmin).map((section) => ({ to: section.to, label: section.label, icon: section.icon, end: section.end ?? false }))} />
      <Outlet context={{ group, isAdmin, reload, handleOperationError }} />
    </div>
  );
}
