// Tokens de sesión (H-09).
//
//   - accessToken: solo en memoria (vence a los 30 minutos; se renueva con el refresh token).
//   - refreshToken: NO llega al JavaScript. El backend lo entrega en la cookie HttpOnly «glucolume_refresh» (Path /api/v1/auth,
//     SameSite=Strict, Secure en producción) y el navegador la manda sola a /auth/refresh. Un XSS no puede leerla ni llevársela,
//     y nada de esto toca localStorage/sessionStorage.
//   - Lo único que se guarda en Web Storage es una MARCA no secreta («hay una sesión que intentar recuperar»): sin ella una visita anónima
//     no gasta una llamada a /auth/refresh que sabemos que va a fallar. «Recordarme» => localStorage; si no => sessionStorage (por pestaña).
//     Borrarla o falsificarla solo cambia si se intenta la renovación: el servidor decide si la cookie vale.

const HINT_KEY = 'glucolume.sessionHint';
// Clave del esquema anterior (refresh token en Web Storage): se borra siempre para no dejar tokens viejos en navegadores ya usados.
const LEGACY_REFRESH_KEY = 'glucolume.refreshToken';

let accessToken = null;

function storages() {
  return [window.localStorage, window.sessionStorage];
}

function safely(action, fallback = null) {
  try {
    return action();
  } catch {
    // Storage bloqueado (modo privado, políticas del navegador): la sesión queda solo en memoria.
    return fallback;
  }
}

export function getAccessToken() {
  return accessToken;
}

/** ¿Hay una sesión que intentar recuperar al abrir la app? (marca no secreta; también limpia el refresh token del esquema anterior). */
export function hasSessionHint() {
  return safely(() => {
    storages().forEach((storage) => storage.removeItem(LEGACY_REFRESH_KEY));
    return window.localStorage.getItem(HINT_KEY) !== null || window.sessionStorage.getItem(HINT_KEY) !== null;
  }, false);
}

/** "Recordarme" activo: la marca vive en localStorage (la cookie del backend es persistente). */
export function isRemembered() {
  return safely(() => window.localStorage.getItem(HINT_KEY) !== null, false);
}

/** Guarda el access token (memoria) y la marca de sesión. El refresh token no se recibe ni se guarda: viaja en la cookie HttpOnly. */
export function saveTokens(tokens, remember = isRemembered()) {
  accessToken = tokens.accessToken;
  safely(() => {
    storages().forEach((storage) => {
      storage.removeItem(HINT_KEY);
      storage.removeItem(LEGACY_REFRESH_KEY);
    });
    (remember ? window.localStorage : window.sessionStorage).setItem(HINT_KEY, '1');
  });
}

export function clearTokens() {
  accessToken = null;
  safely(() => storages().forEach((storage) => {
    storage.removeItem(HINT_KEY);
    storage.removeItem(LEGACY_REFRESH_KEY);
  }));
}

// Preferencia "Recordarme" elegida antes de salir hacia Google (no es un secreto).
const GOOGLE_REMEMBER_KEY = 'glucolume.googleRemember';

export function setPendingGoogleRemember(remember) {
  safely(() => window.sessionStorage.setItem(GOOGLE_REMEMBER_KEY, remember ? '1' : '0'));
}

export function takePendingGoogleRemember() {
  return safely(() => {
    const value = window.sessionStorage.getItem(GOOGLE_REMEMBER_KEY);
    window.sessionStorage.removeItem(GOOGLE_REMEMBER_KEY);
    return value === '1';
  }, false);
}
