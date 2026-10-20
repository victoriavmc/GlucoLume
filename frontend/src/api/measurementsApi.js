// Módulo Medición (backend/app/api/v1/measurements.py). Perfil propio o pacientes a cargo del operador: el backend
// decide en cada llamada qué perfil y qué mediciones corresponden a la cuenta. El navegador no guarda resultados.

import { request } from './client.js';

/** Filtros del historial: solo se envían los que tienen valor. */
export function queryString(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

/** Perfil de medición propio (cuenta individual): { perfilDisponible, datosFaltantes, idPerfilMedicion, ... }. */
export function getOwnProfile() {
  return request('/measurements/profile', { auth: true });
}

/** Dispositivos operativos que se pueden usar para medir ese perfil. */
export function listDevices(idPerfilMedicion) {
  return request(`/measurements/devices${queryString({ idPerfilMedicion })}`, { auth: true });
}

/** El cliente solo informa perfil, dispositivo, modo y contexto; el resto lo fija el servidor. */
export function startMeasurement(data) {
  return request('/measurements', { method: 'POST', body: data, auth: true });
}

/** Matriz que el backend aplicaría a una medición de glucosa de ese perfil (informativa): { ambito, nombre, version } o null. */
export function getMatrixPreview(idPerfilMedicion) {
  return request(`/measurements/matrix${queryString({ idPerfilMedicion })}`, { auth: true });
}

export function getMeasurement(idMedicion) {
  return request(`/measurements/${idMedicion}`, { auth: true });
}

export function cancelMeasurement(idMedicion) {
  return request(`/measurements/${idMedicion}/cancel`, { method: 'POST', auth: true });
}

/** Envía el resultado por correo. Cuenta individual: {} (va a su correo). Paciente: { correoDestino, pacienteAutoriza: true }. */
export function sendResult(idMedicion, data = {}) {
  return request(`/measurements/${idMedicion}/send-result`, { method: 'POST', body: data, auth: true });
}

export function registerCapillaryReference(idMedicion, data) {
  return request(`/measurements/${idMedicion}/capillary-reference`, { method: 'POST', body: data, auth: true });
}

/** Historial propio: { desde, hasta, modo, estado, origen (DEMO | REAL), orden, pagina, tamanioPagina }. */
export function getOwnHistory(filters = {}) {
  return request(`/measurements${queryString(filters)}`, { auth: true });
}

/**
 * Evolución histórica propia: cada medición completada es un punto. { dias (1, 7, 14, 30, 90) | desde, hasta, origen (EXPERIMENTAL | DEMO | TODOS) }.
 * Las estadísticas de DEMO y experimentales llegan por separado.
 */
export function getOwnEvolution({ dias, desde, hasta, origen = 'EXPERIMENTAL' } = {}) {
  return request(`/measurements/evolution${queryString(desde || hasta ? { desde, hasta, origen } : { dias, origen })}`, { auth: true });
}

/** Elimina UNA medición de prueba (DEMO) completada. Una medición real responde 409 DATO_NO_ELIMINABLE. */
export function deleteDemoMeasurement(idMedicion) {
  return request(`/measurements/${idMedicion}`, { method: 'DELETE', auth: true });
}

/** Elimina todas las mediciones de prueba (DEMO) del perfil propio. No toca las reales. { eliminadas } */
export function deleteOwnDemoMeasurements() {
  return request('/measurements/demo', { method: 'DELETE', auth: true });
}
