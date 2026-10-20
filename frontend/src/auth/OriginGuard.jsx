// Mueve la página al origen que le corresponde (login en LOGIN_ORIGIN, el resto en APP_ORIGIN). Cubre tanto la carga
// directa como las navegaciones internas de React Router (p. ej. una ruta protegida que redirige a /login).

import { useLocation } from 'react-router-dom';

import { originRedirect } from './originGuard.js';

export function OriginGuard({ children }) {
  const { pathname, search, hash } = useLocation();
  const target = originRedirect({ origin: window.location.origin, pathname, search, hash });
  if (target) {
    window.location.replace(target);
    return null;
  }
  return children;
}
