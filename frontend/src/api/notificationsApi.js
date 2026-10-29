// Contratos reales de «Notificaciones» (backend/app/api/v1/userNotifications.py, prefijo /notificaciones).

import { request } from './client.js';

/** GET /notificaciones/preferencias -> { preferencias: [{ evento, categoria, enPagina, porCorreo, obligatoria }], recordatorio: { modo, intervaloHoras, horarios } } */
export function getNotificationSettings() {
  return request('/notificaciones/preferencias', { auth: true });
}

/** PUT /notificaciones/preferencias/{evento} con `enPagina` y/o `porCorreo` (los omitidos no cambian). Las alertas obligatorias responden 409. */
export function updateNotificationPreference(evento, changes) {
  return request(`/notificaciones/preferencias/${evento}`, { method: 'PUT', body: changes, auth: true });
}

/** PUT /notificaciones/recordatorio: { modo: NINGUNO | INTERVALO | HORARIOS, intervaloHoras?, horarios? }. `NINGUNO` elimina la programación. */
export function updateReminderSchedule(schedule) {
  return request('/notificaciones/recordatorio', { method: 'PUT', body: schedule, auth: true });
}

/**
 * GET /notificaciones -> { noLeidas, total, hayMas, notificaciones: [{ idNotificacion, evento, categoria, titulo, mensaje, url, fechaCreacion, leida }] }
 * Filtros: `categoria` (SEGURIDAD | GRUPO | RECORDATORIO), `soloNoLeidas`; paginación: `limite` y `desplazamiento`.
 */
export function getNotifications({ categoria, soloNoLeidas, limite, desplazamiento } = {}) {
  const query = new URLSearchParams();
  if (categoria) query.set('categoria', categoria);
  if (soloNoLeidas) query.set('soloNoLeidas', 'true');
  if (limite) query.set('limite', String(limite));
  if (desplazamiento) query.set('desplazamiento', String(desplazamiento));
  const suffix = query.toString();
  return request(`/notificaciones${suffix ? `?${suffix}` : ''}`, { auth: true });
}

/** POST /notificaciones/{idNotificacion}/leer -> { noLeidas, marcadas }. Un aviso ajeno responde 404. */
export function markNotificationRead(idNotificacion) {
  return request(`/notificaciones/${idNotificacion}/leer`, { method: 'POST', auth: true });
}

/** POST /notificaciones/leer-todas -> { noLeidas, marcadas }: solo los avisos de la cuenta autenticada. */
export function markAllNotificationsRead() {
  return request('/notificaciones/leer-todas', { method: 'POST', auth: true });
}
