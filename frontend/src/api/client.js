// Cliente HTTP único del frontend: todas las llamadas a FastAPI pasan por aquí.
//
// - Errores del backend: {codigo, detail} (AuthError) o {detail: [...]} (validación 422) -> ApiError.
// - Peticiones autenticadas: agrega "Authorization: Bearer"; ante un 401 renueva la sesión una vez con
//   /auth/refresh y reintenta.
// - El refresh token vive en una cookie HttpOnly (H-09): las rutas /auth/* se piden con credentials:'include' y la cabecera
//   X-GlucoLume-CSRF (que un formulario de otro sitio no puede enviar); el JavaScript nunca lo ve.
// - La renovación se serializa (también entre pestañas con Web Locks): el backend rota el refresh token y
//   reutilizar uno ya rotado revoca todas las sesiones.

import { API_BASE_URL, API_PREFIX } from '../config.js';
import { clearTokens, getAccessToken, hasSessionHint, isRemembered, saveTokens } from '../auth/tokenStore.js';

export const NETWORK_ERROR = 'ERROR_DE_RED';

export class ApiError extends Error {
  constructor(status, codigo, message, fields = [], retryAfterSeconds = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.codigo = codigo;
    this.fields = fields;
    // Segundos hasta poder reintentar (cabecera Retry-After de un bloqueo temporal); lo decide el backend.
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

export function apiUrl(path) {
  return `${API_BASE_URL}${API_PREFIX}${path}`;
}

function retryAfter(response) {
  const seconds = Number.parseInt(response.headers?.get?.('Retry-After') ?? '', 10);
  return Number.isFinite(seconds) && seconds > 0 ? seconds : null;
}

async function parseError(response) {
  let body = null;
  try {
    body = await response.json();
  } catch {
    // Respuesta sin JSON (proxy, error del servidor).
  }
  if (body && typeof body.codigo === 'string') {
    return new ApiError(
      response.status, body.codigo, body.detail || 'No se pudo completar la operación.', [], retryAfter(response),
    );
  }
  if (body && Array.isArray(body.detail)) {
    // ruta: ubicación dentro del body (p. ej. "institucion.identificadorLegal"); "" si es un error del body completo.
    const fields = body.detail.map((item) => {
      const loc = (item.loc ?? []).filter((part) => part !== 'body');
      return { campo: loc.at(-1), ruta: loc.join('.'), mensaje: item.msg };
    });
    const message = fields.map((field) => field.mensaje).filter(Boolean).join(' ') || 'Revisá los datos ingresados.';
    return new ApiError(response.status, 'VALIDACION', message, fields);
  }
  if (response.status >= 500) {
    return new ApiError(response.status, 'ERROR_SERVIDOR', 'El servidor no pudo procesar la solicitud. Intentá más tarde.');
  }
  return new ApiError(response.status, 'ERROR_DESCONOCIDO', 'No se pudo completar la operación.');
}

export const CSRF_HEADER = 'X-GlucoLume-CSRF';
export const REMEMBER_HEADER = 'X-GlucoLume-Recordarme';

async function send(path, { method = 'GET', body, token, remember } = {}) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;
  // Solo /auth/* usa la cookie (Path=/api/v1/auth): el resto de la API se autentica con el access token y no recibe credenciales ambientales.
  const usesCookie = path.startsWith('/auth/') || path === '/platform/activation/with-code';  // esta última también abre sesión
  if (usesCookie) {
    headers[CSRF_HEADER] = '1';
    if (remember) headers[REMEMBER_HEADER] = '1';
  }
  let response;
  try {
    response = await fetch(apiUrl(path), {
      method,
      headers,
      credentials: usesCookie ? 'include' : 'same-origin',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, NETWORK_ERROR, 'No se pudo conectar con el servidor. Verificá tu conexión e intentá de nuevo.');
  }
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return null;
  return response.json();
}

let refreshInFlight = null;
let sessionExpiredHandler = null;

/** Lo registra AuthContext: se llama cuando el refresh token fue rechazado (sesión vencida o revocada). */
export function onSessionExpired(handler) {
  sessionExpiredHandler = handler;
}

async function refreshOnce() {
  // Sin marca de sesión no hay nada que renovar (la cookie es HttpOnly: no se puede mirar desde acá).
  if (!hasSessionHint()) throw new ApiError(401, 'TOKEN_INVALIDO', 'La sesión no es válida.');
  try {
    const tokens = await send('/auth/refresh', { method: 'POST' });  // sin cuerpo: el navegador manda la cookie
    saveTokens(tokens, isRemembered());
    return tokens;
  } catch (error) {
    if (error.status === 401) {
      clearTokens();
      sessionExpiredHandler?.();
    }
    throw error;
  }
}

/** Renueva la sesión con el refresh token guardado. Concurrente-seguro dentro de la pestaña y entre pestañas. */
export function refreshSession() {
  if (!refreshInFlight) {
    const run = () => refreshOnce();
    const locked = typeof navigator !== 'undefined' && navigator.locks?.request
      ? navigator.locks.request('glucolume-refresh', run)
      : run();
    refreshInFlight = locked.finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/**
 * Llamada a la API. `auth: true` envía el access token y, ante un 401, renueva la sesión una vez.
 */
export async function request(path, { method = 'GET', body, auth = false, remember = false } = {}) {
  if (!auth) return send(path, { method, body, remember });

  let token = getAccessToken();
  if (!token) token = (await refreshSession()).accessToken;
  try {
    return await send(path, { method, body, token });
  } catch (error) {
    // Solo un access token vencido o revocado (TOKEN_INVALIDO) justifica renovar y reintentar. Otros 401
    // (CODIGO_INVALIDO de MFA, credenciales) son respuestas de negocio: reintentar repetiría el intento.
    if (error.status !== 401 || error.codigo !== 'TOKEN_INVALIDO') throw error;
    const renewed = await refreshSession();
    return send(path, { method, body, token: renewed.accessToken });
  }
}
