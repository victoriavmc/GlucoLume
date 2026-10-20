// Administración de la plataforma (backend/app/api/v1/platform.py). El rol y los permisos los decide FastAPI con los datos
// de SQL Server en cada llamada: lo que oculta o muestra React es solo presentación. La autenticación es la de siempre
// (/auth/login, /auth/google/*, /auth/mfa/*); aquí solo está lo propio de la administración.

import { request } from './client.js';
import { queryString } from './measurementsApi.js';

const post = (path, body, auth = true) => request(`/platform${path}`, { method: 'POST', body, auth });

export const getPlatformMe = () => request('/platform/me', { auth: true });

export function getPlatformDashboard(period = { dias: 30 }) {
  const params = period.desde || period.hasta ? { desde: period.desde, hasta: period.hasta } : { dias: period.dias ?? 30 };
  return request(`/platform/dashboard${queryString(params)}`, { auth: true });
}

export const getSystemStatus = () => request('/platform/system', { auth: true });

// Instituciones (administrador y moderador del sistema): listado filtrable, detalle administrativo (sin pacientes ni valores clínicos),
// pausa, reactivación, límite de cuentas y auditoría administrativa de la institución.
export const getInstitutions = (filters = {}) => request(`/platform/institutions${queryString(filters)}`, { auth: true });
export const getInstitution = (id) => request(`/platform/institutions/${id}`, { auth: true });
export const getInstitutionAudit = (id, filters = {}) => request(`/platform/institutions/${id}/audit${queryString(filters)}`, { auth: true });
export const pauseInstitution = (id, motivo) => post(`/institutions/${id}/pause`, { motivo });
export const reactivateInstitution = (id, motivo) => post(`/institutions/${id}/reactivate`, { motivo });
/** Eliminación administrativa (cierre lógico; solo el administrador). `reautenticacion`: { password?, codigo }. */
export const deleteInstitution = (id, { motivo, confirmacionNombre, reautenticacion }) => post(`/institutions/${id}/delete`, { motivo, confirmacionNombre, reautenticacion });
export const changeInstitutionCapacity = (id, capacidadMaxima, motivo) =>
  request(`/platform/institutions/${id}/capacity`, { method: 'PUT', body: { capacidadMaxima, motivo }, auth: true });

// Moderadores del sistema. `reautenticacion`: { password?, codigo }.
export const listModerators = () => request('/platform/moderators', { auth: true });
export const getModerator = (id) => request(`/platform/moderators/${id}`, { auth: true });
export const inviteModerator = (data) => post('/moderators', data);
export const resendInvitation = (id, reautenticacion) => post(`/moderators/${id}/resend-invitation`, { reautenticacion });
export const revokeModerator = (id, reautenticacion) => post(`/moderators/${id}/revoke`, { reautenticacion });
export const resetModeratorPassword = (id, reautenticacion) => post(`/moderators/${id}/password-reset`, { reautenticacion });

// Transferencia del control principal.
export const getTransfer = () => request('/platform/transfer', { auth: true });
export const startTransfer = (idUsuarioDestino, reautenticacion) => post('/transfer', { idUsuarioDestino, reautenticacion });
export const cancelTransfer = (reautenticacion) => post('/transfer/cancel', { reautenticacion });
export const acceptTransfer = (reautenticacion) => post('/transfer/accept', { reautenticacion });
export const rejectTransfer = (reautenticacion) => post('/transfer/reject', { reautenticacion });

// Contraseña propia.
export const changePassword = (data) => post('/password/change', data);

// Sin sesión: invitación y recuperación.
/** Activación con el código de un solo uso + los datos de la invitación. El rol NO viaja: lo fija la invitación en el servidor. */
export const activateWithCode = (data) => post('/activation/with-code', data, false);
export const forgotPassword = (correoElectronico) => post('/password/forgot', { correoElectronico }, false);
export const resetPassword = (token, password) => post('/password/reset', { token, password }, false);
