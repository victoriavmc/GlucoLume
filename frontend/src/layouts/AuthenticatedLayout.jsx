// Layout único del espacio privado: sidebar fijo en escritorio, drawer en pantallas angostas.
// Las páginas internas se renderizan en <Outlet /> (rutas anidadas bajo /app).

import { Menu } from 'lucide-react';
import { Suspense, useEffect, useMemo, useState } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext.jsx';
import { FullPageLoader } from '../components/FullPageLoader.jsx';
import { GracePeriodNotice } from '../components/GracePeriodNotice.jsx';
import { Logo } from '../components/Logo.jsx';
import { SkipLink } from '../components/SkipLink.jsx';
import { InstitutionNavContext } from '../pages/Account/institutions/institutionMenu.js';
import { Sidebar } from './Sidebar.jsx';
import './AuthenticatedLayout.css';

export function AuthenticatedLayout() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [currentInstitution, setCurrentInstitution] = useState(null);
  const institutionNav = useMemo(() => ({ current: currentInstitution, setCurrent: setCurrentInstitution }), [currentInstitution]);
  const { pathname } = useLocation();
  const { flash, setFlash, account } = useAuth();

  // Al navegar se cierra el drawer y el contenido arranca desde arriba.
  useEffect(() => {
    setDrawerOpen(false);
    window.scrollTo?.(0, 0);
    // El aviso pertenece a una pantalla: al ir a otra se descarta (/app solo redirige a /app/inicio).
    const isIndexRedirect = pathname.replace(/\/+$/, '') === '/app';
    if (flash && !isIndexRedirect && flash.path !== pathname) setFlash(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  useEffect(() => {
    if (!drawerOpen) return undefined;
    const onKey = (event) => event.key === 'Escape' && setDrawerOpen(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [drawerOpen]);

  // Las cuentas de plataforma tienen su propio panel: el inicio genérico las lleva allí.
  const isPlatform = ['ADMINISTRADOR_PLATAFORMA', 'MODERADOR_PLATAFORMA'].includes(account?.usuario?.tipoCuenta);
  if (isPlatform && ['/app', '/app/inicio'].includes(pathname.replace(/\/+$/, ''))) return <Navigate to="/plataforma/dashboard" replace />;

  return (
    <InstitutionNavContext.Provider value={institutionNav}>
    <div className={`app-shell${drawerOpen ? ' drawer-open' : ''}`}>
      <SkipLink />
      <header className="app-topbar">
        <button
          type="button"
          className="app-topbar-toggle"
          aria-label="Abrir menú"
          aria-expanded={drawerOpen}
          aria-controls="app-sidebar"
          onClick={() => setDrawerOpen(true)}
        >
          <Menu size={24} />
        </button>
        <Logo to="/app/inicio" />
      </header>

      <Sidebar id="app-sidebar" onClose={() => setDrawerOpen(false)} />
      {drawerOpen && <div className="app-backdrop" aria-hidden="true" onClick={() => setDrawerOpen(false)} />}

      <main className="app-content" id="contenido" tabIndex={-1}>
        <GracePeriodNotice grace={account?.periodoGracia} />
        <Suspense fallback={<FullPageLoader />}><Outlet /></Suspense>
      </main>
    </div>
    </InstitutionNavContext.Provider>
  );
}
