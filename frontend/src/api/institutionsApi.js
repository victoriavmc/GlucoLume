// Módulo Institución (backend/app/api/v1/institutions.py). Requiere una cuenta USUARIO_INSTITUCIONAL.
// El rol y los permisos los decide el backend en cada llamada; el frontend solo los usa para presentar opciones.

import { request } from './client.js';
import { queryString } from './measurementsApi.js';

/** POST /institutions/{id}/support-request -> { mensaje, confirmacionEnviada }. Solo el propietario de una institución pausada. */
export function requestSupport(idInstitucion, { asunto, mensaje }) {
  return request(`/institutions/${idInstitucion}/support-request`, { method: 'POST', body: { asunto, mensaje }, auth: true });
}

/** GET /institutions/mine -> [{ idInstitucion, nombre, tipoInstitucion, estado, rolInstitucion, estadoRelacion, permisos }] */
export function getMyInstitutions({ includePaused = false } = {}) {
  return request(`/institutions/mine${includePaused ? '?incluirPausadas=true' : ''}`, { auth: true });
}

/** GET /institutions/invitations -> invitaciones pendientes recibidas. */
export function getInvitations() {
  return request('/institutions/invitations', { auth: true });
}

export function acceptInvitation(idInstitucionUsuario) {
  return request(`/institutions/invitations/${idInstitucionUsuario}/accept`, { method: 'POST', auth: true });
}

export function rejectInvitation(idInstitucionUsuario) {
  return request(`/institutions/invitations/${idInstitucionUsuario}/reject`, { method: 'POST', auth: true });
}

/** POST /institutions { nombre, tipoInstitucion, tipoIdentificadorLegal, identificadorLegal, descripcion? } */
export function createInstitution(data) {
  return request('/institutions', { method: 'POST', body: data, auth: true });
}

/** GET /institutions/{id} -> panel: datos, rol, permisos y cantidad de moderadores/operadores. */
export function getInstitution(idInstitucion) {
  return request(`/institutions/${idInstitucion}`, { auth: true });
}

/** PATCH /institutions/{id} { nombre?, tipoInstitucion?, descripcion? } (solo propietario). */
export function updateInstitution(idInstitucion, data) {
  return request(`/institutions/${idInstitucion}`, { method: 'PATCH', body: data, auth: true });
}

/** POST /institutions/{id}/deletion { confirmacionNombre, password?, codigo? | codigoRecuperacion? } (solo propietario). */
export function deleteInstitution(idInstitucion, data) {
  return request(`/institutions/${idInstitucion}/deletion`, { method: 'POST', body: data, auth: true });
}

// Moderadores ('moderators') y operadores ('operators') comparten el mismo contrato.
const MEMBER_PATHS = { MODERADOR: 'moderators', OPERADOR: 'operators' };

function membersPath(idInstitucion, rol) {
  return `/institutions/${idInstitucion}/${MEMBER_PATHS[rol]}`;
}

/** Activos e invitaciones pendientes; con `incluirBajas`, también el historial dado de baja. */
export function listMembers(idInstitucion, rol, { incluirBajas = false } = {}) {
  return request(`${membersPath(idInstitucion, rol)}${incluirBajas ? '?incluirBajas=true' : ''}`, { auth: true });
}

/** -> { nombre, apellido, rolPropuesto } solo si la cuenta se puede invitar; si no, un error con el motivo. */
export function lookupMember(idInstitucion, rol, correoElectronico) {
  return request(`${membersPath(idInstitucion, rol)}/lookup`, {
    method: 'POST', body: { correoElectronico }, auth: true,
  });
}

// Datos administrativos del vínculo InstitucionUsuario (iguales para moderadores y operadores).
export const MEMBER_ADMIN_FIELDS = [
  'matriculaProfesional', 'legajoInstitucional', 'funcionProfesional', 'nombreProfesionalHistorico',
  'apellidoProfesionalHistorico',
];

/**
 * Agrega personal (el rol lo fija la ruta): si el correo no tiene cuenta, `nombre` y `apellido` crean una cuenta
 * institucional pendiente de activación; si existe, se reutiliza (sus datos no cambian). Además registra los datos
 * administrativos del vínculo. El vínculo queda pendiente hasta la aceptación.
 */
export function inviteMember(idInstitucion, rol, { correoElectronico, nombre, apellido, ...admin }) {
  const body = { correoElectronico };
  if (nombre) body.nombre = nombre;
  if (apellido) body.apellido = apellido;
  for (const field of MEMBER_ADMIN_FIELDS) if (admin[field]) body[field] = admin[field];
  return request(membersPath(idInstitucion, rol), { method: 'POST', body, auth: true });
}

/** Modifica solo los datos administrativos enviados (un texto vacío los borra). No cambia el rol ni la cuenta. */
export function updateMemberAdmin(idInstitucion, rol, idInstitucionUsuario, changes) {
  return request(`${membersPath(idInstitucion, rol)}/${idInstitucionUsuario}`, {
    method: 'PATCH', body: changes, auth: true,
  });
}

/** Reenvía una invitación pendiente (renueva el vencimiento y, si hace falta, el enlace de activación). */
export function resendInvitation(idInstitucion, rol, idInstitucionUsuario) {
  return request(`${membersPath(idInstitucion, rol)}/${idInstitucionUsuario}/resend`, { method: 'POST', auth: true });
}

/** Revoca un vínculo activo o cancela una invitación pendiente. Un operador con pacientes a cargo responde 409 PACIENTES_ASIGNADOS. */
export function revokeMember(idInstitucion, rol, idInstitucionUsuario) {
  return request(`${membersPath(idInstitucion, rol)}/${idInstitucionUsuario}`, { method: 'DELETE', auth: true });
}

/** GET .../operators/{id}/offboarding -> { operador, cantidadPacientes, transferenciasPendientes, pacientes, destinos, bloqueo } */
export function getOperatorOffboarding(idInstitucion, idInstitucionUsuario) {
  return request(`${membersPath(idInstitucion, 'OPERADOR')}/${idInstitucionUsuario}/offboarding`, { auth: true });
}

/** POST .../operators/{id}/offboard { asignaciones: [{ idPerfilMedicion, idOperadorNuevo }], observacion? } -> reasigna y desvincula (una transacción). */
export function offboardOperator(idInstitucion, idInstitucionUsuario, body) {
  return request(`${membersPath(idInstitucion, 'OPERADOR')}/${idInstitucionUsuario}/offboard`, { method: 'POST', body, auth: true });
}

/** POST /institutions/{id}/reassignments/regularize { idOperadorAnterior } -> { pacientesPendientes } (crea las tareas; no reasigna). */
export function regularizeReassignments(idInstitucion, idOperadorAnterior) {
  return request(`/institutions/${idInstitucion}/reassignments/regularize`, { method: 'POST', body: { idOperadorAnterior }, auth: true });
}

// --- Pacientes institucionales (PerfilMedicion INSTITUCIONAL; no son cuentas de GlucoLume) ---------------

function patientsPath(idInstitucion) {
  return `/institutions/${idInstitucion}/patients`;
}

/** GET .../patients?busqueda&idResponsable&estado&soloMios&pagina&tamanioPagina -> { items, total, pagina, tamanioPagina } */
export function listPatients(idInstitucion, filters = {}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '' && value !== false) params.set(key, String(value));
  }
  const query = params.toString();
  return request(`${patientsPath(idInstitucion)}${query ? `?${query}` : ''}`, { auth: true });
}

export function getPatient(idInstitucion, idPerfilMedicion) {
  return request(`${patientsPath(idInstitucion)}/${idPerfilMedicion}`, { auth: true });
}

/** { nombre, apellido, dni, fechaNacimiento, sexoModelo, idInstitucionUsuarioResponsable? } */
export function createPatient(idInstitucion, data) {
  return request(patientsPath(idInstitucion), { method: 'POST', body: data, auth: true });
}

export function updatePatient(idInstitucion, idPerfilMedicion, data) {
  return request(`${patientsPath(idInstitucion)}/${idPerfilMedicion}`, { method: 'PATCH', body: data, auth: true });
}

export function assignPatientResponsible(idInstitucion, idPerfilMedicion, idInstitucionUsuarioResponsable) {
  return request(`${patientsPath(idInstitucion)}/${idPerfilMedicion}/responsible`, {
    method: 'PUT', body: { idInstitucionUsuarioResponsable }, auth: true,
  });
}

/** Correo del paciente para recibir sus resultados (vence a los 12 meses). { correo, pacienteAutoriza } -> paciente con correoResultados enmascarado. */
export function setPatientResultEmail(idInstitucion, idPerfilMedicion, data) {
  return request(`${patientsPath(idInstitucion)}/${idPerfilMedicion}/result-email`, { method: 'PUT', body: data, auth: true });
}

export function clearPatientResultEmail(idInstitucion, idPerfilMedicion) {
  return request(`${patientsPath(idInstitucion)}/${idPerfilMedicion}/result-email`, { method: 'DELETE', auth: true });
}

// Pública (sin sesión): el paciente confirma su correo desde el enlace que recibió (GL-08).
export function confirmResultEmail(token) {
  return request('/institutions/result-email/confirm', { method: 'POST', body: { token } });
}

export function dischargePatient(idInstitucion, idPerfilMedicion) {
  return request(`${patientsPath(idInstitucion)}/${idPerfilMedicion}/discharge`, { method: 'POST', auth: true });
}

/** Mediciones del paciente (Medicion.idPerfilMedicion). Filtros: { desde, hasta, modo, estado, orden, pagina, tamanioPagina }. */
export function getPatientMeasurements(idInstitucion, idPerfilMedicion, filters = {}) {
  return request(`${patientsPath(idInstitucion)}/${idPerfilMedicion}/measurements${queryString(filters)}`, { auth: true });
}

/** Promedios, mínimos, máximos y serie diaria del paciente (solo mediciones completadas): { dias } o { desde, hasta }. */
export function getPatientStatistics(idInstitucion, idPerfilMedicion, period = {}) {
  return request(`${patientsPath(idInstitucion)}/${idPerfilMedicion}/measurements/statistics${queryString(period)}`, {
    auth: true,
  });
}

/**
 * Evolución del paciente: cada medición completada (experimental o DEMO, de cualquier modo) es un punto con todos sus valores.
 * { dias (1, 7, 14, 30, 90) | desde, hasta, origen (TODOS | EXPERIMENTAL | DEMO), modo }. Las estadísticas DEMO y experimentales llegan separadas.
 */
export function getPatientEvolution(idInstitucion, idPerfilMedicion, { dias, desde, hasta, origen = 'TODOS', modo } = {}) {
  const period = desde || hasta ? { desde, hasta } : { dias };
  return request(`${patientsPath(idInstitucion)}/${idPerfilMedicion}/measurements/evolution${queryString({ ...period, origen, modo })}`, {
    auth: true,
  });
}

// --- Transferencia de pacientes entre operadores (RF32) ----------------------------------------------------

/** El paciente sigue a cargo del solicitante hasta que el destinatario acepte. */
export function requestTransfer(idInstitucion, idPerfilMedicion, { idOperadorDestino, observacion }) {
  const body = { idOperadorDestino };
  if (observacion) body.observacion = observacion;
  return request(`${patientsPath(idInstitucion)}/${idPerfilMedicion}/transfers`, { method: 'POST', body, auth: true });
}

/** direccion: recibidas | enviadas | todas; estado opcional. -> { items, total, pagina, tamanioPagina } */
export function listTransfers(idInstitucion, filters = {}) {
  return request(`/institutions/${idInstitucion}/transfers${queryString(filters)}`, { auth: true });
}

/** Detalle de una transferencia: paciente, origen, destino, solicitante, fechas con zona, historial y datos técnicos. */
export function getTransfer(idInstitucion, idTransferenciaPerfil) {
  return request(`/institutions/${idInstitucion}/transfers/${idTransferenciaPerfil}`, { auth: true });
}

function transferAction(idInstitucion, idTransferenciaPerfil, action) {
  return request(`/institutions/${idInstitucion}/transfers/${idTransferenciaPerfil}/${action}`, {
    method: 'POST', auth: true,
  });
}

export const acceptTransfer = (idInstitucion, id) => transferAction(idInstitucion, id, 'accept');
export const rejectTransfer = (idInstitucion, id) => transferAction(idInstitucion, id, 'reject');
export const cancelTransfer = (idInstitucion, id) => transferAction(idInstitucion, id, 'cancel');

// --- Pacientes pendientes de reasignación (propietario y moderador) ------------------------------

/** GET /institutions/{id}/reassignments -> { pendientes, operadoresDisponibles, grupos: [{ idOperadorAnterior, operadorAnterior, fechaDesvinculacion, pendientes, estado }] } */
export function getReassignments(idInstitucion) {
  return request(`/institutions/${idInstitucion}/reassignments`, { auth: true });
}

/** GET /institutions/{id}/reassignments/items?estado=&idOperadorAnterior= -> { items, total } (una fila por paciente). */
export function getReassignmentItems(idInstitucion, filters = {}) {
  return request(`/institutions/${idInstitucion}/reassignments/items${queryString(filters)}`, { auth: true });
}

/** POST /institutions/{id}/reassignments/assign { idsReasignacion, idOperadorNuevo, observacion? } -> { reasignados, resultados } */
export function assignReassignments(idInstitucion, body) {
  return request(`/institutions/${idInstitucion}/reassignments/assign`, { method: 'POST', body, auth: true });
}

/** Operadores activos (solo nombre y apellido) para elegir el responsable de un paciente. */
export function getAssignableOperators(idInstitucion) {
  return request(`${patientsPath(idInstitucion)}/assignable-operators`, { auth: true });
}

// --- Estado del CUIT y reapertura ---------------------------------------------------------------

/** POST /institutions/legal-id/status -> { estado: DISPONIBLE | ACTIVA | CERRADA, puedeReabrir, mensaje, institucion } */
export function checkLegalId(identificadorLegal) {
  return request('/institutions/legal-id/status', {
    method: 'POST', body: { tipoIdentificadorLegal: 'CUIT', identificadorLegal }, auth: true,
  });
}

/** POST /institutions/reopen { datos, identificadorLegal, password?, codigo? | codigoRecuperacion? } -> operacion REABIERTA */
export function reopenInstitution(data) {
  return request('/institutions/reopen', { method: 'POST', body: data, auth: true });
}

/** GET /institutions/{id}/activity?limite -> { items: [{ titulo, categoria, entidad, usuario, fechaHora, resultado, critica, rechazado, ruta, idAuditoria }] }
 * Resumen curado de la auditoría, filtrado por permisos en el backend; `ruta` es relativa a la institución (solo si se puede abrir). */
export function getRecentActivity(idInstitucion, limite = 5) {
  return request(`/institutions/${idInstitucion}/activity${queryString({ limite })}`, { auth: true });
}

/** GET /institutions/{id}/personnel?rol&estado&busqueda&pagina&tamanioPagina -> { items, total, pagina, tamanioPagina, resumen }
 * Todo el personal (también bajas), una fila por persona. Propietario y moderador. */
export function listPersonnel(idInstitucion, filters = {}) {
  return request(`/institutions/${idInstitucion}/personnel${queryString(filters)}`, { auth: true });
}

/** GET /institutions/{id}/personnel/{idInstitucionUsuario} -> perfil institucional con fechas, períodos anteriores e historial. */
export function getPersonnelProfile(idInstitucion, idInstitucionUsuario) {
  return request(`/institutions/${idInstitucion}/personnel/${idInstitucionUsuario}`, { auth: true });
}

/** DELETE /institutions/{id}/personnel/{idInstitucionUsuario}/personal-data -> 204
 * Suprime nombre profesional, legajo y matrícula de una persona ya desvinculada (no se puede deshacer). */
export function erasePersonnelData(idInstitucion, idInstitucionUsuario) {
  return request(`/institutions/${idInstitucion}/personnel/${idInstitucionUsuario}/personal-data`, { method: 'DELETE', auth: true });
}

/** GET /institutions/{id}/invitations?estado -> { items, total, pagina, tamanioPagina, resumen }
 * Invitaciones enviadas (pendientes, aceptadas, rechazadas, canceladas y vencidas). Solo las aceptadas son personal. */
export function listSentInvitations(idInstitucion, filters = {}) {
  return request(`/institutions/${idInstitucion}/invitations${queryString({ tamanioPagina: 100, ...filters })}`, { auth: true });
}

/** GET /institutions/{id}/quota -> { capacidadMaximaUsuarios, usuariosActivos, cuposDisponibles, porcentajeUtilizacion, estado }
 * Cupos de cuentas institucionales calculados por el backend con las relaciones activas. Propietario y moderador. */
export function getQuota(idInstitucion) {
  return request(`/institutions/${idInstitucion}/quota`, { auth: true });
}
