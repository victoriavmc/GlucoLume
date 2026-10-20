// Formulario de contacto público (backend/app/api/v1/contact.py).

import { request } from './client.js';

/** POST /contact (200). Mismos nombres que ContactRequest; sitioWeb es el campo trampa (siempre vacío). */
export function sendContact({ nombre, email, tipoConsulta, asunto, mensaje, sitioWeb = '' }) {
  return request('/contact', { method: 'POST', body: { nombre, email, tipoConsulta, asunto, mensaje, sitioWeb } });
}
