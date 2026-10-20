// Tokens de sesión.
//
// El backend entrega accessToken y refreshToken en el body de /auth/login, /auth/mfa/verify,
// /auth/google/exchange y /auth/refresh (no usa cookies):
//   - accessToken: solo en memoria (vence a los 30 minutos; se renueva con el refresh token).
//   - refreshToken: sessionStorage (dura mientras la pestaña esté abierta) o, con "Recordarme",
//     localStorage. Permite recuperar la sesión al recargar. El backend lo rota en cada uso.

const REFRESH_KEY = 'glucolume.refreshToken';

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

export function getRefreshToken() {
  return safely(() => window.localStorage.getItem(REFRESH_KEY) ?? window.sessionStorage.getItem(REFRESH_KEY));
}

/** "Recordarme" activo: el refresh token vive en localStorage. */
export function isRemembered() {
  return safely(() => window.localStorage.getItem(REFRESH_KEY) !== null, false);
}

export function saveTokens(tokens, remember = isRemembered()) {
  accessToken = tokens.accessToken;
  safely(() => {
    storages().forEach((storage) => storage.removeItem(REFRESH_KEY));
    (remember ? window.localStorage : window.sessionStorage).setItem(REFRESH_KEY, tokens.refreshToken);
  });
}

export function clearTokens() {
  accessToken = null;
  safely(() => storages().forEach((storage) => storage.removeItem(REFRESH_KEY)));
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
