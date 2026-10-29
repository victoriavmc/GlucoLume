// Contratos reales de «Notificaciones» (backend/app/api/v1/userNotifications.py, prefijo /notificaciones).

import { request } from './client.js';

/** GET /notificaciones/preferencias -> { preferencias: [{ evento, enPagina, porCorreo }], recordatorio: { modo, intervaloHoras, horarios } } */
export function getNotificationSettings() {
  return request('/notificaciones/preferencias', { auth: true });
}

/** PUT /notificaciones/preferencias/{evento} con `enPagina` y/o `porCorreo` (los omitidos no cambian). */
export function updateNotificationPreference(evento, changes) {
  return request(`/notificaciones/preferencias/${evento}`, { method: 'PUT', body: changes, auth: true });
}

/** PUT /notificaciones/recordatorio: { modo: NINGUNO | INTERVALO | HORARIOS, intervaloHoras?, horarios? } */
export function updateReminderSchedule(schedule) {
  return request('/notificaciones/recordatorio', { method: 'PUT', body: schedule, auth: true });
}

/** GET /notificaciones -> { noLeidas, notificaciones: [{ idNotificacion, evento, titulo, mensaje, url, fechaCreacion, leida }] } */
export function getNotifications() {
  return request('/notificaciones', { auth: true });
}

/** POST /notificaciones/{idNotificacion}/leer -> bandeja actualizada */
export function markNotificationRead(idNotificacion) {
  return request(`/notificaciones/${idNotificacion}/leer`, { method: 'POST', auth: true });
}

/** POST /notificaciones/leer-todas -> bandeja actualizada */
export function markAllNotificationsRead() {
  return request('/notificaciones/leer-todas', { method: 'POST', auth: true });
}
