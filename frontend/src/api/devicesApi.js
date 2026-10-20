// Inventario de dispositivos (backend/app/api/v1/devices.py). `devicesApi(idInstitucion)` apunta al inventario global
// (cuentas de plataforma) cuando no hay institución, o al de la institución indicada. Qué puede hacer cada cuenta lo
// decide FastAPI en cada llamada y lo informa en `permisos` de cada dispositivo; el inventario no informa conexión.

import { request } from './client.js';
import { queryString } from './measurementsApi.js';

export function devicesApi(idInstitucion) {
  const base = idInstitucion ? `/institutions/${idInstitucion}/devices` : '/devices';
  const post = (path, body) => request(`${base}${path}`, { method: 'POST', body, auth: true });
  return {
    /** Filtros: busqueda, estado (OPERATIVO, EN_MANTENIMIENTO, FUERA_DE_SERVICIO, BAJA), asignado, pagina, tamanioPagina. */
    list: (filters = {}) => request(`${base}${queryString(filters)}`, { auth: true }),
    summary: () => request(`${base}/summary`, { auth: true }),
    get: (id) => request(`${base}/${id}`, { auth: true }),
    register: (data) => post('', data),
    edit: (id, changes) => request(`${base}/${id}`, { method: 'PATCH', body: changes, auth: true }),
    setState: (id, estado, motivo) => post(`/${id}/state`, { estado, ...(motivo ? { motivo } : {}) }),
    setResponsible: (id, idInstitucionUsuarioResponsable) => post(`/${id}/responsible`, { idInstitucionUsuarioResponsable }),
    unassign: (id) => post(`/${id}/unassign`),
    decommission: (id) => post(`/${id}/decommission`),
    measurements: (id, pagina = 1) => request(`${base}/${id}/measurements${queryString({ pagina, tamanioPagina: 10 })}`, { auth: true }),
    /** Integrantes activos de la institución (propietario y moderador). */
    responsibles: () => request(`${base}/responsibles`, { auth: true }),
    // Solo administrador del sistema (inventario global).
    assign: (id, idInstitucion, idInstitucionUsuarioResponsable) => post(`/${id}/assign`, {
      idInstitucion, ...(idInstitucionUsuarioResponsable ? { idInstitucionUsuarioResponsable } : {}),
    }),
    institutionOptions: (busqueda = '') => request(`/devices/institutions${queryString({ busqueda })}`, { auth: true }),
    institutionResponsibles: (id) => request(`/devices/institutions/${id}/responsibles`, { auth: true }),
  };
}
