import { Activity, Building2, ClipboardList, Cpu, House, Layers, LogOut, PlugZap, ShieldCheck, UserRound, Users, X } from 'lucide-react';
import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext.jsx';
import { Logo } from '../components/Logo.jsx';
import { institutionSections, useInstitutionNav } from '../pages/Account/institutions/institutionMenu.js';

// Solo secciones realmente funcionales. "Instituciones" solo para cuentas USUARIO_INSTITUCIONAL y
// "Grupo" solo para cuentas individuales (CONSUMIDOR_FINAL).
const PLATFORM_ACCOUNTS = ['MODERADOR_PLATAFORMA', 'ADMINISTRADOR_PLATAFORMA'];
const NAV_ITEMS = [
  { to: '/app/inicio', label: 'Inicio', icon: House },
  { to: '/app/instituciones', label: 'Instituciones', icon: Building2, accountType: 'USUARIO_INSTITUCIONAL' },
  { to: '/app/dispositivos', label: 'Dispositivos', icon: Cpu, accountType: PLATFORM_ACCOUNTS },
  { to: '/app/auditoria', label: 'Auditoría', icon: ClipboardList, accountType: 'ADMINISTRADOR_PLATAFORMA' },
  { to: '/app/matrices', label: 'Matrices globales', icon: Layers, accountType: PLATFORM_ACCOUNTS },
  { to: '/app/mediciones', label: 'Mediciones', icon: Activity, accountType: 'CONSUMIDOR_FINAL' },
  { to: '/app/conectar-dispositivo', label: 'Conectar dispositivo', icon: PlugZap, accountType: 'CONSUMIDOR_FINAL' },
  { to: '/app/grupo', label: 'Grupo', icon: Users, accountType: 'CONSUMIDOR_FINAL' },
  { to: '/app/perfil', label: 'Perfil', icon: UserRound },
  { to: '/app/seguridad', label: 'Seguridad', icon: ShieldCheck },
];

export function displayName(user) {
  return [user?.nombre, user?.apellido].filter(Boolean).join(' ') || user?.usuario || user?.correoElectronico || '';
}

function initials(user) {
  const source = [user?.nombre, user?.apellido].filter(Boolean);
  const letters = source.length ? source.map((part) => part[0]) : [(user?.usuario || user?.correoElectronico || '?')[0]];
  return letters.join('').slice(0, 2).toUpperCase();
}

export function Sidebar({ id, onClose }) {
  const { account, logout } = useAuth();
  const navigate = useNavigate();
  const [leaving, setLeaving] = useState(false);
  const user = account?.usuario;
  const { current } = useInstitutionNav();

  async function handleLogout() {
    setLeaving(true);
    await logout();
    navigate('/login', { replace: true });
  }

  return (
    <aside id={id} className="app-sidebar" aria-label="Menú principal">
      <div className="app-sidebar-head">
        <Logo to="/app/inicio" />
        <button type="button" className="app-sidebar-close" aria-label="Cerrar menú" onClick={onClose}>
          <X size={22} />
        </button>
      </div>

      <div className="app-user">
        <span className="app-avatar" aria-hidden="true">
          {initials(user)}
        </span>
        <span className="app-user-text">
          <b>{displayName(user)}</b>
          {user?.usuario && <small>@{user.usuario}</small>}
        </span>
      </div>

      <nav className="app-nav" aria-label="Secciones de la cuenta">
        <ul>
          {NAV_ITEMS.filter((item) => !item.accountType || [].concat(item.accountType).includes(user?.tipoCuenta)).map(({ to, label, icon: Icon }) => (
            <li key={to}>
              <NavLink to={to} end={to === '/app/instituciones' && Boolean(current)}
                className={({ isActive }) => `app-nav-link${isActive || (current && to === '/app/instituciones') ? ' is-active' : ''}`}>
                <Icon size={20} aria-hidden="true" />
                {label}
              </NavLink>
              {current && to === '/app/instituciones' && (
                <nav aria-label="Secciones de la institución"><ul className="app-subnav">
                  {institutionSections(current).map(({ icon: SectionIcon, ...section }) => (
                    <li key={section.key}>
                      <NavLink to={`/app/instituciones/${current.idInstitucion}${section.to ? `/${section.to}` : ''}`} end={section.end}
                        className={({ isActive }) => `app-subnav-link${isActive ? ' is-active' : ''}`}>
                        {SectionIcon && <SectionIcon size={16} aria-hidden="true" />}
                        {section.label}
                      </NavLink>
                    </li>
                  ))}
                </ul></nav>
              )}
            </li>
          ))}
        </ul>
      </nav>

      <button type="button" className="app-logout" onClick={handleLogout} disabled={leaving}>
        {leaving ? <span className="spinner" aria-hidden="true" /> : <LogOut size={20} aria-hidden="true" />}
        {leaving ? 'Cerrando sesión…' : 'Cerrar sesión'}
      </button>
    </aside>
  );
}
