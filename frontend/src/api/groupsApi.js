// Módulo Grupo (backend/app/api/v1/groups.py). Solo cuentas individuales (CONSUMIDOR_FINAL).
// El rol y los permisos los decide el backend en cada llamada. Los datos compartidos se piden de a uno y solo si
// el integrante habilitó ese permiso: no se descargan en segundo plano ni se guardan en el navegador.

import { request } from './client.js';

export function getMyGroup() {
  return request('/groups/mine', { auth: true });
}

export function createGroup(data) {
  return request('/groups', { method: 'POST', body: data, auth: true });
}

export function getGroup(idGrupo) {
  return request(`/groups/${idGrupo}`, { auth: true });
}

export function updateGroup(idGrupo, data) {
  return request(`/groups/${idGrupo}`, { method: 'PATCH', body: data, auth: true });
}

export function deleteGroup(idGrupo, confirmacionNombre) {
  return request(`/groups/${idGrupo}/deletion`, { method: 'POST', body: { confirmacionNombre }, auth: true });
}

export function leaveGroup(idGrupo) {
  return request(`/groups/${idGrupo}/leave`, { method: 'POST', auth: true });
}

export function transferAdmin(idGrupo, idGrupoUsuario) {
  return request(`/groups/${idGrupo}/transfer`, { method: 'POST', body: { idGrupoUsuario }, auth: true });
}

export function listMembers(idGrupo) {
  return request(`/groups/${idGrupo}/members`, { auth: true });
}

export function removeMember(idGrupo, idGrupoUsuario) {
  return request(`/groups/${idGrupo}/members/${idGrupoUsuario}`, { method: 'DELETE', auth: true });
}

// --- Invitaciones ---------------------------------------------------------------------------------

export function getReceivedInvitations() {
  return request('/groups/invitations', { auth: true });
}

export function acceptInvitation(idGrupoUsuario) {
  return request(`/groups/invitations/${idGrupoUsuario}/accept`, { method: 'POST', auth: true });
}

export function rejectInvitation(idGrupoUsuario) {
  return request(`/groups/invitations/${idGrupoUsuario}/reject`, { method: 'POST', auth: true });
}

export function listSentInvitations(idGrupo) {
  return request(`/groups/${idGrupo}/invitations`, { auth: true });
}

export function lookupCandidate(idGrupo, correoElectronico) {
  return request(`/groups/${idGrupo}/invitations/lookup`, { method: 'POST', body: { correoElectronico }, auth: true });
}

export function invite(idGrupo, correoElectronico) {
  return request(`/groups/${idGrupo}/invitations`, { method: 'POST', body: { correoElectronico }, auth: true });
}

export function cancelInvitation(idGrupo, idGrupoUsuario) {
  return request(`/groups/${idGrupo}/invitations/${idGrupoUsuario}`, { method: 'DELETE', auth: true });
}

// --- Mis permisos y datos compartidos ------------------------------------------------------------

export function getMySharing(idGrupo) {
  return request(`/groups/${idGrupo}/sharing/me`, { auth: true });
}

/** { compartePerfil, comparteUltimaMedicion, comparteHistorial, notificaMedicion } (solo los propios; el historial habilita los gráficos). */
export function updateMySharing(idGrupo, settings) {
  return request(`/groups/${idGrupo}/sharing/me`, { method: 'PUT', body: settings, auth: true });
}

export function getSharedMembers(idGrupo) {
  return request(`/groups/${idGrupo}/shared`, { auth: true });
}

function sharedPath(idGrupo, idGrupoUsuario) {
  return `/groups/${idGrupo}/shared/${idGrupoUsuario}`;
}

export function getSharedProfile(idGrupo, idGrupoUsuario) {
  return request(`${sharedPath(idGrupo, idGrupoUsuario)}/profile`, { auth: true });
}

export function getSharedLatest(idGrupo, idGrupoUsuario) {
  return request(`${sharedPath(idGrupo, idGrupoUsuario)}/latest`, { auth: true });
}

export function getSharedHistory(idGrupo, idGrupoUsuario, pagina = 1, tamanioPagina = 10) {
  return request(`${sharedPath(idGrupo, idGrupoUsuario)}/history?pagina=${pagina}&tamanioPagina=${tamanioPagina}`, { auth: true });
}

/** Avisos de medición: solo { items: [{ fechaHoraInicio }], total }; los autoriza únicamente `notificaMedicion`. */
export function getSharedNotices(idGrupo, idGrupoUsuario, limite = 10, pagina = 1) {
  return request(`${sharedPath(idGrupo, idGrupoUsuario)}/notices?limite=${limite}&pagina=${pagina}`, { auth: true });
}

/** Vista ampliada de una medición compartida: el backend vuelve a verificar el permiso (historial, o última si solo compartió esa). */
export function getSharedMeasurement(idGrupo, idGrupoUsuario, idMedicion) {
  return request(`${sharedPath(idGrupo, idGrupoUsuario)}/measurements/${idMedicion}`, { auth: true });
}

export function getSharedStatistics(idGrupo, idGrupoUsuario, dias = 30) {
  return request(`${sharedPath(idGrupo, idGrupoUsuario)}/statistics?dias=${dias}`, { auth: true });
}
