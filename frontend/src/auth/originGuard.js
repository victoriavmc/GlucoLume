// Separación de orígenes: el login (/login) vive en LOGIN_ORIGIN (localhost, el único host que Google admite como
// redirección OAuth) y todo lo demás en APP_ORIGIN (glucolume.local). Sin ambos valores configurados no hace nada.

import { APP_ORIGIN, LOGIN_ORIGIN } from '../config.js';

export const TRANSFER_PATH = '/auth/google/callback';

export function isSplitOrigins() {
  return Boolean(LOGIN_ORIGIN && APP_ORIGIN && LOGIN_ORIGIN !== APP_ORIGIN);
}

/** True si esta página es la de login servida desde LOGIN_ORIGIN (la sesión debe transferirse a APP_ORIGIN). */
export function isOnLoginOrigin() {
  return isSplitOrigins() && window.location.origin === LOGIN_ORIGIN;
}

/** URL a la que hay que mover esta página para respetar la separación, o null si ya está en el origen correcto. */
export function originRedirect({ origin, pathname, search, hash }) {
  if (!isSplitOrigins()) return null;
  const isLogin = pathname === '/login' || pathname === '/login/';
  if (isLogin && origin !== LOGIN_ORIGIN) return `${LOGIN_ORIGIN}/login${search}${hash}`;
  if (!isLogin && origin === LOGIN_ORIGIN) return `${APP_ORIGIN}${pathname}${search}${hash}`;
  return null;
}

/** Entrega la sesión (código de un solo uso) a la aplicación en APP_ORIGIN. */
export function goToApp(code, remember) {
  const fragment = new URLSearchParams({ code, ...(remember ? { recordar: '1' } : {}) });
  window.location.replace(`${APP_ORIGIN}${TRANSFER_PATH}#${fragment}`);
}
