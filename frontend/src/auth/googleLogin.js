import { googleLoginUrl } from '../api/authApi.js';
import { setPendingGoogleRemember } from './tokenStore.js';

/**
 * Inicia OAuth con Google (navegación completa del navegador): el backend redirige a Google y luego a
 * /auth/google/callback. Es el mismo flujo para iniciar sesión y para registrarse: con `registro`
 * ('usuario' | 'institucion') el backend crea la cuenta nueva de ese tipo; una cuenta existente solo inicia sesión.
 */
export function startGoogleLogin(remember = false, registro = undefined, aceptaPolitica = false) {
  setPendingGoogleRemember(remember);
  // «Recordarme» viaja por el backend: el login puede estar en otro origen que la app (no comparten sessionStorage).
  window.location.assign(googleLoginUrl(registro, remember, aceptaPolitica));
}
