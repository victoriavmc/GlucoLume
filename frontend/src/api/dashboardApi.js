// Dashboards por ámbito (personal, familiar, institucional). Todo se calcula en FastAPI sobre Medicion y cada llamada
// vuelve a evaluar permisos: el frontend solo muestra lo que llega. `period`: { dias } o { desde, hasta }.

import { request } from './client.js';
import { queryString } from './measurementsApi.js';

function periodParams(period = {}) {
  return period.desde || period.hasta ? { desde: period.desde, hasta: period.hasta } : { dias: period.dias ?? 30 };
}

export const getPersonalDashboard = (period) =>
  request(`/measurements/dashboard${queryString(periodParams(period))}`, { auth: true });

export const getGroupDashboard = (idGrupo, period) =>
  request(`/groups/${idGrupo}/dashboard${queryString(periodParams(period))}`, { auth: true });

/** `filters`: { operador, modo, estado, origen } (los vacíos no se envían). Con el origen «TODOS» se incluyen las DEMO, separadas de las experimentales. */
export const getInstitutionDashboard = (idInstitucion, period, filters = {}) =>
  request(`/institutions/${idInstitucion}/dashboard${queryString({ ...periodParams(period), ...filters })}`, { auth: true });

/** idOperador: vínculo del operador (InstitucionUsuario) o `me`. */
export const getOperatorDashboard = (idInstitucion, idOperador, period) =>
  request(`/institutions/${idInstitucion}/operators/${idOperador}/dashboard${queryString(periodParams(period))}`, { auth: true });

/**
 * Análisis del OPERADOR sobre sus pacientes activos (el backend fija el alcance; no hay parámetro para otro operador).
 * filtros: { dias | desde/hasta, idPerfilMedicion, sexo, edad, edadBase, alimentacion, modo, origen, estado, calidad, variable, granularidad,
 * compararMatriz, pagina, tamanioPagina }. Los vacíos no se envían.
 */
export const getPatientAnalytics = (idInstitucion, filters = {}) =>
  request(`/institutions/${idInstitucion}/analytics/patients${queryString(filters)}`, { auth: true });
