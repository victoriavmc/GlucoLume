// Inventario de dispositivos (backend/app/api/v1/devices.py). `devicesApi(idInstitucion)` apunta al inventario global
// (cuentas de plataforma) cuando no hay institución, o al de la institución indicada. Qué puede hacer cada cuenta lo
// decide FastAPI en cada llamada y lo informa en `permisos` de cada dispositivo; el inventario no informa conexión.

import { fileFrom, request } from './client.js';
import { queryString } from './measurementsApi.js';

export function devicesApi(idInstitucion) {
  const base = idInstitucion ? `/institutions/${idInstitucion}/devices` : '/devices';
  const post = (path, body) => request(`${base}${path}`, { method: 'POST', body, auth: true });
  // Exportaciones: el backend decide qué sale (permiso, alcance y filtros) y audita cada intento. `formato`: csv, xlsx o pdf.
  const exportFile = async (path, body, fallbackName, formato) => fileFrom(
    await request(`${path}?formato=${formato}`, { method: 'POST', body, auth: true, file: true }), `${fallbackName}.${formato}`);
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
    /** 25 por página; `estado` (PENDIENTE, ADQUIRIENDO, PROCESANDO, COMPLETADA, INVALIDA, CANCELADA) filtra por estado de medición. */
    measurements: (id, pagina = 1, estado = '') => request(`${base}/${id}/measurements${queryString({ pagina, tamanioPagina: 25, estado })}`,
      { auth: true }),
    /** Integrantes activos de la institución (propietario y moderador). */
    responsibles: () => request(`${base}/responsibles`, { auth: true }),
    // Solo administrador del sistema (inventario global).
    assign: (id, idInstitucion, idInstitucionUsuarioResponsable) => post(`/${id}/assign`, {
      idInstitucion, ...(idInstitucionUsuarioResponsable ? { idInstitucionUsuarioResponsable } : {}),
    }),
    institutionOptions: (busqueda = '') => request(`/devices/institutions${queryString({ busqueda })}`, { auth: true }),
    institutionResponsibles: (id) => request(`/devices/institutions/${id}/responsibles`, { auth: true }),
    /** Solo inventario global: cuentas individuales vinculadas a cada dispositivo (referencia corta, sin datos personales). */
    accountLinks: () => request('/devices/vinculos-cuentas', { auth: true }),
    /** Listado: `body` { alcance: 'SELECCION', idsDispositivo } o { alcance: 'TODOS', busqueda?, estado?, asignado?, uso? }. -> { blob, filename } */
    exportList: (body, formato = 'csv') => exportFile(`${base}/export`, body, 'dispositivos', formato),
    /** Datos de un dispositivo (mismo alcance que su detalle). -> { blob, filename } */
    exportOne: (id, formato = 'csv') => exportFile(`${base}/${id}/export`, undefined, 'dispositivo', formato),
  };
}
