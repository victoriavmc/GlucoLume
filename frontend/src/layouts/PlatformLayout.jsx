// Layout propio de la Administración de GlucoLume (/plataforma/*). Mismo proyecto, mismo estilo y mismo sidebar vertical
// que el resto de la app, pero con sus rutas, menú y permisos. El menú se arma con los permisos que informa
// GET /platform/me; el backend vuelve a comprobarlos en cada llamada (ocultar una opción no reemplaza la autorización).

import {
  Building2, ClipboardList, CreditCard, Cpu, Gauge, KeyRound, Layers, LogOut, Menu, ShieldCheck, UserCog, UserRound, Users, X,
} from 'lucide-react';
import { Suspense, createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Link, NavLink, Navigate, Outlet, useLocation } from 'react-router-dom';

import * as platformApi from '../api/platformApi.js';
import { useAuth } from '../auth/AuthContext.jsx';
import { friendlyError } from '../auth/errorMessages.js';
import { Alert } from '../components/FormControls.jsx';
import { FullPageLoader } from '../components/FullPageLoader.jsx';
import { Logo } from '../components/Logo.jsx';
import { SkipLink } from '../components/SkipLink.jsx';
import './AuthenticatedLayout.css';

const PlatformContext = createContext(null);
export const usePlatform = () => useContext(PlatformContext);

const NAV = [
  { heading: 'Inicio', items: [
    { to: '/plataforma/dashboard', label: 'Dashboard general', icon: Gauge },
    { to: '/plataforma/instituciones', label: 'Instituciones', icon: Building2, permission: 'SUPERVISAR_INSTITUCIONES' },
  ] },
  { heading: 'Administración', items: [
    { to: '/plataforma/moderadores', label: 'Moderadores del sistema', icon: Users, permission: 'GESTIONAR_MODERADORES' },
    { to: '/plataforma/transferencia', label: 'Transferir administración', icon: UserCog, permission: 'TRANSFERIR_ADMINISTRACION' },
  ] },
  { heading: 'Inventario', items: [
    { to: '/plataforma/dispositivos', label: 'Dispositivos globales', icon: Cpu, permission: 'CONSULTAR_DISPOSITIVOS_GLOBALES' },
  ] },
  { heading: 'Matrices', items: [
    { to: '/plataforma/matrices', label: 'Matrices globales', icon: Layers, permission: 'GESTIONAR_MATRICES_GLOBALES' },
  ] },
  { heading: 'Auditoría', items: [
    { to: '/plataforma/auditoria', label: 'Auditoría y seguridad', icon: ClipboardList, permission: 'CONSULTAR_AUDITORIA_GLOBAL' },
  ] },
  { heading: 'Suscripciones y pagos', items: [
    { to: '/plataforma/suscripciones', label: 'Próximamente', icon: CreditCard, permission: 'SUSCRIPCIONES_Y_PAGOS' },
  ] },
  { heading: 'Cuenta', items: [
    { to: '/plataforma/perfil', label: 'Mi perfil', icon: UserRound },
    { to: '/plataforma/seguridad', label: 'Seguridad y MFA', icon: ShieldCheck },
    { to: '/plataforma/cambiar-contrasena', label: 'Cambiar contraseña', icon: KeyRound },
  ] },
];

const CRUMBS = {
  dashboard: 'Dashboard general', instituciones: 'Instituciones', moderadores: 'Moderadores del sistema', transferencia: 'Transferir administración',
  dispositivos: 'Dispositivos globales', matrices: 'Matrices globales', auditoria: 'Auditoría general',
  suscripciones: 'Suscripciones y pagos', perfil: 'Mi perfil', seguridad: 'Seguridad y MFA', 'cambiar-contrasena': 'Cambiar contraseña',
};

function PlatformSidebar({ me, id, onClose }) {
  const { logout } = useAuth();
  const [leaving, setLeaving] = useState(false);
  return (
    <aside id={id} className="app-sidebar" aria-label="Menú de administración">
      <div className="app-sidebar-head">
        <Logo to="/plataforma/dashboard" />
        <button type="button" className="app-sidebar-close" aria-label="Cerrar menú" onClick={onClose}><X size={22} /></button>
      </div>
      <div className="app-user">
        <span className="app-avatar" aria-hidden="true">{(me.nombre?.[0] ?? '') + (me.apellido?.[0] ?? '')}</span>
        <span className="app-user-text">
          <b>{[me.nombre, me.apellido].filter(Boolean).join(' ')}</b>
          <small>{me.rolEtiqueta}</small>
        </span>
      </div>
      <nav className="app-nav" aria-label="Secciones de administración">
        {NAV.map((group) => {
          const items = group.items.filter((item) => !item.permission || me.permisos.includes(item.permission));
          if (items.length === 0) return null;
          return (
            <section key={group.heading} aria-label={group.heading}>
              <p className="app-nav-heading">{group.heading}</p>
              <ul>
                {items.map(({ to, label, icon: Icon }) => (
                  <li key={to}>
                    <NavLink to={to} className={({ isActive }) => `app-nav-link${isActive ? ' is-active' : ''}`}>
                      <Icon size={20} aria-hidden="true" /> {label}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </nav>
      <button type="button" className="app-logout" disabled={leaving} onClick={async () => { setLeaving(true); await logout(); }}>
        {leaving ? <span className="spinner" aria-hidden="true" /> : <LogOut size={20} aria-hidden="true" />}
        {leaving ? 'Cerrando sesión…' : 'Cerrar sesión'}
      </button>
    </aside>
  );
}

export function PlatformLayout() {
  const { status, account } = useAuth();
  const { pathname } = useLocation();
  const [state, setState] = useState({ phase: 'loading', me: null, error: '' });
  const [drawerOpen, setDrawerOpen] = useState(false);

  const reload = useCallback(async () => {
    try {
      setState({ phase: 'ready', me: await platformApi.getPlatformMe(), error: '' });
    } catch (error) {
      setState({ phase: error.status === 403 ? 'forbidden' : 'error', me: null, error: friendlyError(error) });
    }
  }, []);

  // El rol y la seguridad se vuelven a leer al abrir el panel y cuando cambia el MFA de la cuenta.
  useEffect(() => {
    if (status === 'authenticated') reload();
  }, [status, reload, account?.mfaHabilitado]);

  useEffect(() => {
    setDrawerOpen(false);
    window.scrollTo?.(0, 0);
  }, [pathname]);

  const value = useMemo(() => ({ me: state.me, reload }), [state.me, reload]);

  if (status === 'loading') return <FullPageLoader label="Recuperando tu sesión…" />;
  if (status !== 'authenticated') return <Navigate to="/plataforma/login" replace />;
  if (state.phase === 'loading') return <FullPageLoader label="Cargando la administración…" />;
  if (state.phase === 'forbidden') {
    return (
      <main className="app-content" id="contenido" tabIndex={-1}>
        <div className="page">
          <Alert>No tenés acceso a la administración de la plataforma.</Alert>
          <Link to="/app" className="btn btn-outline">Ir a mi espacio</Link>
        </div>
      </main>
    );
  }
  if (state.phase === 'error') {
    return <main className="app-content" id="contenido" tabIndex={-1}><div className="page"><Alert>{state.error}</Alert></div></main>;
  }

  const segment = pathname.split('/')[2] ?? 'dashboard';
  return (
    <PlatformContext.Provider value={value}>
      <div className={`app-shell${drawerOpen ? ' drawer-open' : ''}`}>
        <SkipLink />
        <header className="app-topbar">
          <button type="button" className="app-topbar-toggle" aria-label="Abrir menú" aria-expanded={drawerOpen}
            aria-controls="platform-sidebar" onClick={() => setDrawerOpen(true)}>
            <Menu size={24} />
          </button>
          <Logo to="/plataforma/dashboard" />
        </header>
        <PlatformSidebar me={state.me} id="platform-sidebar" onClose={() => setDrawerOpen(false)} />
        {drawerOpen && <div className="app-backdrop" aria-hidden="true" onClick={() => setDrawerOpen(false)} />}
        <main className="app-content" id="contenido" tabIndex={-1}>
          <div className="page platform-page">
            <nav className="breadcrumbs" aria-label="Ruta de navegación">
              <ol>
                <li><Link to="/plataforma/dashboard">Administración de GlucoLume</Link></li>
                <li aria-current="page">{CRUMBS[segment] ?? 'Panel'}</li>
              </ol>
            </nav>
            {state.me.requiereConfigurarMfa && segment !== 'seguridad' && (
              <Alert kind="info">
                Para usar las funciones administrativas activá la verificación en dos pasos (MFA).{' '}
                <Link to="/plataforma/seguridad">Configurar ahora</Link>
              </Alert>
            )}
            <Suspense fallback={<FullPageLoader />}><Outlet /></Suspense>
          </div>
        </main>
      </div>
    </PlatformContext.Provider>
  );
}

/** Rutas que operan datos: sin MFA habilitado no se muestran (el backend también las rechaza con 403). */
export function RequireMfa({ children }) {
  const { me } = usePlatform();
  if (me.requiereConfigurarMfa) return null;
  return children;
}

/** Rutas con un permiso: sin él se muestra el aviso (la autorización real está en FastAPI). */
export function RequirePermission({ permission, children }) {
  const { me } = usePlatform();
  if (me.requiereConfigurarMfa) return null;
  if (!me.permisos.includes(permission)) return <Alert>Tu rol no permite acceder a esta sección.</Alert>;
  return children;
}
