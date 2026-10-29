// Contratos reales del módulo Auth de FastAPI (backend/app/api/v1/auth.py).

import { apiUrl, request } from './client.js';

/**
 * POST /auth/login -> LoginResponse { estado: AUTENTICADO | MFA_REQUERIDO, tokens?, challengeToken? }
 * acceso: 'GENERAL' (login de todas las cuentas, por omisión) o 'PLATAFORMA' (administración de GlucoLume).
 */
export function login(identificador, password, remember = false, acceso = 'GENERAL') {
  return request('/auth/login', { method: 'POST', body: { identificador, password, acceso }, remember });
}

/** POST /auth/mfa/verify: exactamente uno de codigo o codigoRecuperacion. */
export function verifyMfa(challengeToken, { codigo, codigoRecuperacion }, remember = false) {
  const body = codigo ? { challengeToken, codigo } : { challengeToken, codigoRecuperacion };
  return request('/auth/mfa/verify', { method: 'POST', body, remember });
}

/** POST /auth/google/exchange: canjea el código de un solo uso del callback por LoginResponse. */
export function exchangeGoogleCode(code, remember = false) {
  return request('/auth/google/exchange', { method: 'POST', body: { code }, remember });
}

/** GET /auth/me -> AccountResponse */
export function getAccount() {
  return request('/auth/me', { auth: true });
}

/** POST /auth/logout (204): revoca la sesión actual en el servidor. */
export function logout() {
  return request('/auth/logout', { method: 'POST', auth: true });
}

/**
 * URL a la que el navegador navega para iniciar OAuth (redirección 302 a Google; no es un fetch).
 * registro: 'usuario' | 'institucion' solo al registrarse; decide el tipo si Google crea una cuenta nueva.
 * acceso: 'PLATAFORMA' solo desde /plataforma/login; sin él el backend usa el acceso general.
 */
export function googleLoginUrl(registro, recordar = false, acepta = false, acceso = undefined) {
  const params = new URLSearchParams();
  if (registro) params.set('registro', registro);
  if (recordar) params.set('recordar', 'true');
  // Confirmación de la Política de Privacidad: el backend la exige para crear o activar una cuenta con Google.
  if (acepta) params.set('acepta', 'true');
  if (acceso) params.set('acceso', acceso);
  const query = params.toString();
  return apiUrl(`/auth/google/login${query ? `?${query}` : ''}`);
}

/** POST /auth/session-transfer: código de un solo uso para continuar la sesión actual en otro origen. */
export function sessionTransfer() {
  return request('/auth/session-transfer', { method: 'POST', auth: true });
}

/** GET /auth/verify-email?token=: verifica el correo con el token del enlace. */
export function verifyEmail(token) {
  return request(`/auth/verify-email?token=${encodeURIComponent(token)}`);
}

/**
 * POST /auth/register (201) -> UserRead. La cuenta queda PENDIENTE hasta verificar el correo.
 * tipoCuenta: CONSUMIDOR_FINAL | USUARIO_INSTITUCIONAL; con USUARIO_INSTITUCIONAL se envía `institucion`.
 */
export function register(data) {
  return request('/auth/register', { method: 'POST', body: data });
}

/** POST /auth/verify-email/resend (202): nuevo correo de verificación (el plazo no se extiende). */
/** POST /auth/password/forgot (202): envía el enlace de recuperación. Misma respuesta exista o no la cuenta. */
export function forgotPassword(correoElectronico) {
  return request('/auth/password/forgot', { method: 'POST', body: { correoElectronico } });
}

/** POST /auth/password/reset: contraseña nueva con el token del enlace (un solo uso; cierra todas las sesiones). */
export function resetPassword(token, password) {
  return request('/auth/password/reset', { method: 'POST', body: { token, password } });
}

export function resendVerification(correoElectronico) {
  return request('/auth/verify-email/resend', { method: 'POST', body: { correoElectronico } });
}

// --- Cuenta del usuario autenticado ----------------------------------------------------------

/**
 * PATCH /auth/me/profile -> ProfileUpdateResponse (AccountResponse + actualizado + detail).
 * Campos editables: nombre, apellido, usuario, fechaNacimiento (AAAA-MM-DD), sexo (MASCULINO | FEMENINO).
 * El correo no se modifica por este endpoint. Los campos omitidos no cambian; ninguno admite null.
 */
export function updateProfile(changes) {
  return request('/auth/me/profile', { method: 'PATCH', body: changes, auth: true });
}

/** POST /auth/password/change: contraseña actual + nueva (+ codigo / codigoRecuperacion si la cuenta tiene MFA). */
export function changePassword(data) {
  return request('/auth/password/change', { method: 'POST', body: data, auth: true });
}

/** POST /auth/password (201): agrega una contraseña local a una cuenta creada solo con Google. */
export function setLocalPassword(password) {
  return request('/auth/password', { method: 'POST', body: { password }, auth: true });
}

/** PUT /auth/me/notifications/new-login -> AccountResponse (lo usa el aviso de inicio de sesión de la administración de GlucoLume) */
export function setNewLoginNotification(habilitada) {
  return request('/auth/me/notifications/new-login', { method: 'PUT', body: { habilitada }, auth: true });
}

// --- MFA (TOTP) --------------------------------------------------------------------------------

/** POST /auth/mfa/setup -> { secreto, otpauthUri }. No activa MFA: falta confirmar con un código. */
export function startMfaSetup() {
  return request('/auth/mfa/setup', { method: 'POST', auth: true });
}

/** POST /auth/mfa/enable { codigo } -> { codigosRecuperacion } (se muestran una sola vez). */
export function enableMfa(codigo) {
  return request('/auth/mfa/enable', { method: 'POST', body: { codigo }, auth: true });
}

/** POST /auth/mfa/disable: exactamente uno de codigo o codigoRecuperacion. */
export function disableMfa({ codigo, codigoRecuperacion }) {
  const body = codigo ? { codigo } : { codigoRecuperacion };
  return request('/auth/mfa/disable', { method: 'POST', body, auth: true });
}

// --- Eliminación de cuenta ---------------------------------------------------------------------

/** POST /auth/account-deletion/request (202, sin body): envía el enlace de confirmación por correo. */
export function requestAccountDeletion() {
  return request('/auth/account-deletion/request', { method: 'POST', auth: true });
}

/** POST /auth/account-deletion/confirm { token, password?, codigo? | codigoRecuperacion? } (sin sesión). */
export function confirmAccountDeletion({ token, password, codigo, codigoRecuperacion }) {
  const body = { token };
  if (password) body.password = password;
  if (codigo) body.codigo = codigo;
  else if (codigoRecuperacion) body.codigoRecuperacion = codigoRecuperacion;
  return request('/auth/account-deletion/confirm', { method: 'POST', body });
}

// --- Recuperación de MFA ("perdí mi aplicación autenticadora") ---------------------------------

/** POST /auth/mfa/recovery/start -> { recoveryToken, correoEnmascarado, vigenciaMinutos } */
export function startMfaRecovery(challengeToken, password) {
  const body = password ? { challengeToken, password } : { challengeToken };
  return request('/auth/mfa/recovery/start', { method: 'POST', body });
}

/** POST /auth/mfa/recovery/verify -> LoginResponse (AUTENTICADO, con MFA ya desactivado). */
export function verifyMfaRecovery(recoveryToken, codigo, remember = false) {
  return request('/auth/mfa/recovery/verify', { method: 'POST', body: { recoveryToken, codigo }, remember });
}

/** Seguridad (con sesión): perdió la aplicación y los códigos. POST /auth/me/mfa/recovery/start { password } */
export function startAccountMfaRecovery(password) {
  return request('/auth/me/mfa/recovery/start', { method: 'POST', body: { password }, auth: true });
}

/** POST /auth/me/mfa/recovery/verify { codigo } -> AccountResponse (MFA desvinculado). */
export function verifyAccountMfaRecovery(codigo) {
  return request('/auth/me/mfa/recovery/verify', { method: 'POST', body: { codigo }, auth: true });
}

// --- Activación de una cuenta creada por una invitación institucional -------------------------------

/** POST /auth/account-activation/check { token } -> { nombre, apellido, correoEnmascarado, invitaciones } */
export function checkAccountActivation(token) {
  return request('/auth/account-activation/check', { method: 'POST', body: { token } });
}

/** POST /auth/account-activation/complete { token, usuario, password } -> LoginResponse */
export function completeAccountActivation(token, usuario, password, aceptaPoliticaPrivacidad = false) {
  return request('/auth/account-activation/complete', {
    method: 'POST', body: { token, usuario, password, aceptaPoliticaPrivacidad },
  });
}

/** GET /auth/account-deletion/preview: si puede eliminarse, qué se elimina, qué se conserva y el período de gracia (solo consulta). */
export function getAccountDeletionPreview() {
  return request('/auth/account-deletion/preview', { auth: true });
}

/** GET /auth/consents: estado vigente de la política de privacidad y de la autorización de datos experimentales. */
export function getConsents() {
  return request('/auth/consents', { auth: true });
}

/** PUT /auth/consents/datos-experimentales: acepta (true) o revoca (false) el almacenamiento de mis mediciones. */
export function setExperimentalConsent(acepta) {
  return request('/auth/consents/datos-experimentales', { method: 'PUT', auth: true, body: { acepta } });
}
