// Consulta de la auditoría (backend/app/api/v1/audit.py). Solo lectura: no hay llamadas para crear, modificar ni
// eliminar eventos. Quién puede consultar y de qué institución lo decide FastAPI en cada pedido (administrador del
// sistema: todo; propietario: solo su institución); ocultar la opción en el menú no reemplaza esa autorización.

import { request } from './client.js';
import { queryString } from './measurementsApi.js';

/**
 * Auditoría general (ADMINISTRADOR_PLATAFORMA). Cubre plataforma, instituciones (idInstitucion) y cuentas individuales (idCuenta).
 * Filtros: idInstitucion, idCuenta, usuario, modulo, accion, categoria, clasificacion, origenActor, motivo, resultado, desde, hasta, critica,
 * identificador, idCorrelacion, ip, refIdentificador, pagina, tamanioPagina.
 */
export function listGlobalAudit(filters = {}) {
  return request(`/audit${queryString(filters)}`, { auth: true });
}

export function getGlobalAuditSummary(filters = {}) {
  return request(`/audit/summary${queryString(filters)}`, { auth: true });
}

export function getGlobalAuditEvent(idAuditoria) {
  return request(`/audit/events/${idAuditoria}`, { auth: true });
}

/** Auditoría de una institución (su PROPIETARIO): el ámbito sale de la ruta, no hay filtro de institución. */
export function listInstitutionAudit(idInstitucion, filters = {}) {
  return request(`/institutions/${idInstitucion}/audit${queryString(filters)}`, { auth: true });
}

export function getInstitutionAuditSummary(idInstitucion, filters = {}) {
  return request(`/institutions/${idInstitucion}/audit/summary${queryString(filters)}`, { auth: true });
}

export function getInstitutionAuditEvent(idInstitucion, idAuditoria) {
  return request(`/institutions/${idInstitucion}/audit/events/${idAuditoria}`, { auth: true });
}

/** Señales de actividad sospechosa y controles activados (ADMINISTRADOR_PLATAFORMA). Se calculan al consultar; no son registros. */
export function getSecuritySignals(filters = {}) {
  return request(`/audit/security/signals${queryString(filters)}`, { auth: true });
}

/** Selector de instituciones de la auditoría (todas, tengan o no eventos). */
export function listAuditInstitutions(q = '') {
  return request(`/audit/institutions${queryString({ q })}`, { auth: true });
}

/** Busca cuentas por nombre, usuario o correo (mínimo 3 caracteres). El correo llega enmascarado. */
export function searchAuditAccounts(q) {
  return request(`/audit/accounts${queryString({ q })}`, { auth: true });
}

/** Ficha de una cuenta para su auditoría. Abrirla queda registrado en la auditoría. */
export function getAuditAccount(idUsuario) {
  return request(`/audit/accounts/${idUsuario}`, { auth: true });
}
