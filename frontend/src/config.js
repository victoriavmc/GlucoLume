// URL base del backend FastAPI. Proviene de VITE_API_BASE_URL (pública: nunca secretos en VITE_*).
const DEV_FALLBACK = 'http://localhost:8000';

function resolveApiBaseUrl() {
  const configured = import.meta.env.VITE_API_BASE_URL;
  if (configured) return configured.replace(/\/+$/, '');
  if (import.meta.env.DEV) {
    console.warn(`VITE_API_BASE_URL no está definida; se usa ${DEV_FALLBACK} (solo en desarrollo).`);
    return DEV_FALLBACK;
  }
  throw new Error('Falta VITE_API_BASE_URL: configurala antes de compilar el frontend.');
}

export const API_BASE_URL = resolveApiBaseUrl();
export const API_PREFIX = '/api/v1';

// Orígenes separados para el login (VITE_LOGIN_ORIGIN, p. ej. http://localhost) y el resto de la aplicación
// (VITE_APP_ORIGIN, p. ej. http://glucolume.local). Google no admite dominios .local como redirección OAuth, así que
// el login vive en localhost y la sesión se transfiere a la aplicación. Sin ambos valores no hay separación.
const origin = (value) => (value ? value.replace(/\/+$/, '') : '');
export const LOGIN_ORIGIN = origin(import.meta.env.VITE_LOGIN_ORIGIN);
export const APP_ORIGIN = origin(import.meta.env.VITE_APP_ORIGIN);
