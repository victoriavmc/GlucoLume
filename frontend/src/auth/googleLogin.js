import { googleLoginUrl } from '../api/authApi.js';
import { setPendingGooglePlatform, setPendingGoogleRemember } from './tokenStore.js';

/**
 * Inicia OAuth con Google (navegación completa del navegador): el backend redirige a Google y luego a
 * /auth/google/callback. Es el mismo flujo para iniciar sesión y para registrarse: con `registro`
 * ('usuario' | 'institucion') el backend crea la cuenta nueva de ese tipo; una cuenta existente solo inicia sesión.
 */
export function startGoogleLogin(remember = false, registro = undefined, aceptaPolitica = false, acceso = undefined) {
  setPendingGoogleRemember(remember);
  // Cada inicio fija su propia marca de panel: una de un intento anterior que no volvió no puede llevar a /plataforma desde /login.
  setPendingGooglePlatform(acceso === 'PLATAFORMA');
  // «Recordarme» viaja por el backend: el login puede estar en otro origen que la app (no comparten sessionStorage).
  // `acceso` ('PLATAFORMA' desde /plataforma/login) decide qué tipo de cuenta admite el backend en el callback.
  window.location.assign(googleLoginUrl(registro, remember, aceptaPolitica, acceso));
}
