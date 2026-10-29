// Módulo de matrices de estimación (backend/app/api/v1/matrices.py y /institutions/{id}/matrices).
// Quién puede ver o modificar cada matriz lo decide el backend por ámbito y rol; las acciones disponibles llegan en
// `permisos` de cada detalle. El cliente nunca elige qué matriz se usa en una medición.

import { fileFrom, request } from './client.js';

/** POST /matrices/{id}/export -> { blob, filename }: la matriz con sus reglas en CSV. La API decide quién puede verla y audita la exportación. */
export async function exportMatrix(idMatriz) {
  return fileFrom(await request(`/matrices/${idMatriz}/export`, { method: 'POST', auth: true, file: true }), 'matriz.csv');
}

/** Todas las versiones globales (cuentas de plataforma). */
export function listGlobalMatrices() {
  return request('/matrices/global', { auth: true });
}

/** Resumen institucional: { institucionActiva, globalActiva, efectiva, versiones }. Propietario y moderador. */
export function getInstitutionMatrices(idInstitucion) {
  return request(`/institutions/${idInstitucion}/matrices`, { auth: true });
}

/** `referenciaBase` es obligatoria (de dónde se tomaron los criterios); `urlReferencia` es el enlace opcional a esa fuente. */
export function createMatrix({
  ambito, idInstitucion, nombre, descripcion, referenciaBase, urlReferencia, fechaVigenciaDesde, fechaVigenciaHasta, reglas,
}) {
  const body = { ambito, nombre, referenciaBase };
  if (idInstitucion) body.idInstitucion = idInstitucion;
  if (descripcion) body.descripcion = descripcion;
  if (urlReferencia) body.urlReferencia = urlReferencia;
  if (fechaVigenciaDesde) body.fechaVigenciaDesde = fechaVigenciaDesde;
  if (fechaVigenciaHasta) body.fechaVigenciaHasta = fechaVigenciaHasta;
  if (reglas?.length) body.reglas = reglas; // se guardan junto con la matriz (todo o nada)
  return request('/matrices', { method: 'POST', body, auth: true });
}

export function getMatrix(idMatriz) {
  return request(`/matrices/${idMatriz}`, { auth: true });
}

/** Solo un borrador: { nombre?, descripcion?, referenciaBase?, urlReferencia?, fechaVigenciaDesde?, fechaVigenciaHasta? }. */
export function updateDraft(idMatriz, changes) {
  return request(`/matrices/${idMatriz}`, { method: 'PATCH', body: changes, auth: true });
}

const action = (idMatriz, name) => request(`/matrices/${idMatriz}/${name}`, { method: 'POST', auth: true });

export const createVersion = (idMatriz) => action(idMatriz, 'new-version');
export const validateMatrix = (idMatriz) => action(idMatriz, 'validate');
export const activateMatrix = (idMatriz) => action(idMatriz, 'activate');
export const deactivateMatrix = (idMatriz) => action(idMatriz, 'deactivate');
export const archiveMatrix = (idMatriz) => action(idMatriz, 'archive');

/** Auditoría: global solo para plataforma; institucional solo para el propietario. */
export function getMatrixAudit(idMatriz) {
  return request(`/matrices/${idMatriz}/audit`, { auth: true });
}

export function addRule(idMatriz, rule) {
  return request(`/matrices/${idMatriz}/rules`, { method: 'POST', body: rule, auth: true });
}

export function updateRule(idMatriz, idReglaMatriz, changes) {
  return request(`/matrices/${idMatriz}/rules/${idReglaMatriz}`, { method: 'PATCH', body: changes, auth: true });
}

export function deleteRule(idMatriz, idReglaMatriz) {
  return request(`/matrices/${idMatriz}/rules/${idReglaMatriz}`, { method: 'DELETE', auth: true });
}

/** Revisión previa de reglas todavía sin guardar: { valida, problemas, advertencias }. No persiste nada. */
export function checkRules(reglas) {
  return request('/matrices/check-rules', { method: 'POST', body: { reglas }, auth: true });
}
