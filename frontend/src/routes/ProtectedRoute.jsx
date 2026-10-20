import { Navigate, useLocation } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext.jsx';
import { FullPageLoader } from '../components/FullPageLoader.jsx';

export function ProtectedRoute({ children }) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === 'loading') return <FullPageLoader label="Recuperando tu sesión…" />;
  if (status !== 'authenticated') return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return children;
}

/** Para /login: si ya hay sesión, ir directo a la app. */
export function GuestOnlyRoute({ children }) {
  const { status } = useAuth();
  if (status === 'loading') return <FullPageLoader label="Recuperando tu sesión…" />;
  if (status === 'authenticated') return <Navigate to="/app" replace />;
  return children;
}
