import { configure, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../test/helpers.js';
import { renderAt } from '../../test/renderApp.jsx';

configure({ asyncUtilTimeout: 5000 });

const account = (tipoCuenta) => ({ ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta }, mfaHabilitado: true });
const ADMIN_ACCOUNT = account('ADMINISTRADOR_PLATAFORMA');
const MOD_ACCOUNT = account('MODERADOR_PLATAFORMA');
const NO_CONTENT = { ok: true, status: 204, json: async () => null };

const ADMIN_PERMS = ['DASHBOARD_GLOBAL', 'GESTIONAR_MODERADORES', 'TRANSFERIR_ADMINISTRACION', 'CONSULTAR_AUDITORIA_GLOBAL',
  'CONSULTAR_DISPOSITIVOS_GLOBALES', 'GESTIONAR_DISPOSITIVOS_GLOBALES', 'GESTIONAR_MATRICES_GLOBALES', 'CONSULTAR_ESTADO_SISTEMA', 'SUSCRIPCIONES_Y_PAGOS',
  'SUPERVISAR_INSTITUCIONES', 'AUDITAR_INSTITUCIONES', 'GESTIONAR_ESTADO_INSTITUCIONES', 'GESTIONAR_CUPOS_INSTITUCIONES', 'ELIMINAR_INSTITUCIONES'];
const MOD_PERMS = ['DASHBOARD_TECNICO', 'CONSULTAR_DISPOSITIVOS_GLOBALES', 'GESTIONAR_MATRICES_GLOBALES', 'CONSULTAR_ESTADO_SISTEMA',
  'SUPERVISAR_INSTITUCIONES', 'AUDITAR_INSTITUCIONES', 'GESTIONAR_ESTADO_INSTITUCIONES', 'GESTIONAR_CUPOS_INSTITUCIONES'];
const me = (overrides = {}) => ({
  idUsuario: 'u-1', nombre: 'Victoria', apellido: 'Cortés', correoElectronico: 'victoria@example.com', rol: 'ADMINISTRADOR_PLATAFORMA',
  rolEtiqueta: 'Administrador del sistema', permisos: ADMIN_PERMS, mfaHabilitado: true, mfaRequerida: true, requiereConfigurarMfa: false,
  tieneCredencialLocal: true, tieneGoogle: false, transferenciaPendiente: null, ...overrides,
});
const MOD_ME = me({ rol: 'MODERADOR_PLATAFORMA', rolEtiqueta: 'Moderador del sistema', permisos: MOD_PERMS });

const metric = { total: 0, operativos: 0, enMantenimiento: 0, fueraDeServicio: 0, descomisionados: 0, asignados: 0, sinAsignar: 0 };
const DASHBOARD = {
  alcance: 'ADMINISTRADOR', periodo: { dias: 30, desde: null, hasta: null },
  usuarios: { total: 12, individuales: 5, institucionales: 6, plataforma: 1, activas: 10, inactivas: 2, conVinculoInstitucional: 5, institucionalesSinVinculo: 1,
    registradasPeriodo: 4, registradas7Dias: 2 },
  instituciones: { total: 3, activas: 1, cerradas: 1, inactivas: 1, moderadores: 2, operadores: 5 },
  grupos: { total: 4, activos: 4, usuariosAgrupados: 9 },
  dispositivos: { ...metric, total: 7, operativos: 5, enMantenimiento: 1, fueraDeServicio: 1, asignados: 4, sinAsignar: 3, conLecturasInvalidasRecientes: 2,
    desconectados: null, conexionVerificable: false },
  mediciones: { total: 40, demo: 6, enPeriodo: 30, oximetria: 35, glucosaExperimental: 5, completadas: 33, canceladas: 4, invalidas: 3, erroresTecnicos: 5,
    motivosTecnicos: [{ clave: 'LECTURA_NO_VALIDA', total: 3 }, { clave: 'SESION_EXPIRADA', total: 2 }],
    porEstado: { COMPLETADA: 33, CANCELADA: 4, INVALIDA: 3 }, serie: [{ fecha: '2026-10-08', total: 6, completadas: 5 }] },
  actividadPorModulo: [{ modulo: 'MEDICIONES', total: 20, fallidos: 1 }],
  eventosRecientes: [{ idAuditoria: 'e-1', fechaHora: '2026-10-09T10:00:00-03:00', modulo: 'MEDICIONES', accion: 'FINALIZAR_MEDICION', resultado: 'EXITO' }],
  erroresRecientes: [], operacionesAdministrativas: [{ idAuditoria: 'e-2', fechaHora: '2026-10-09T10:05:00-03:00', modulo: 'PLATAFORMA', accion: 'INVITAR_MODERADOR_PLATAFORMA', resultado: 'EXITO' }],
  seguridad: { loginsFallidos: 7, loginsExitosos: 41,
    accesosPorTipo: { individual: { fallidos: 3, exitosos: 20 }, institucional: { fallidos: 2, exitosos: 15 }, plataforma: { fallidos: 1, exitosos: 5 },
      sinClasificar: { fallidos: 1, exitosos: 1 } },
    motivosFallo: [{ clave: 'Contraseña inválida', total: 6 }, { clave: 'Cuenta bloqueada', total: 1 }],
    cuentasBloqueadas: 1, bloqueosTemporales: 1, cuentasConFallosRepetidos: 1, eventosCriticos: 3, operacionesAdministrativas: 2, exportaciones: 0 },
  generadoEn: '2026-10-09T10:00:00',
};
const SYSTEM = { fecha: '2026-10-09T10:00:00', componentes: [
  { nombre: 'Base de datos', estado: 'OPERATIVO', detalle: null, verificacion: 'Consulta de prueba a SQL Server', latenciaMs: 4 },
  { nombre: 'Correo (SMTP)', estado: 'NO_DISPONIBLE', detalle: 'Falta SMTP_HOST.', verificacion: 'Servidor SMTP configurado', latenciaMs: null },
  { nombre: 'Acceso con Google', estado: 'DEGRADADO', detalle: 'No se alcanza accounts.google.com (TimeoutError).', verificacion: 'Credenciales y conexión TCP a Google', latenciaMs: null },
  { nombre: 'Adquisición por puerto serie (pySerial)', estado: 'DESCONOCIDO', detalle: 'No se pudieron listar los puertos.', verificacion: 'Módulo pySerial', latenciaMs: null },
] };
const row = (overrides = {}) => ({
  idInstitucion: 'i-1', nombre: 'Centro Médico San José', tipoInstitucion: 'CLINICA', estado: 'ACTIVA', fechaInicio: '2026-09-01T10:00:00', fechaFin: null,
  propietarios: 1, moderadores: 2, operadores: 5, cuentasInternas: 8, limiteCuentas: 1000, dispositivos: 3, ...overrides,
});
const INSTITUTIONS = { items: [row(), row({ idInstitucion: 'i-2', nombre: 'Clínica Sur', estado: 'CERRADA', fechaFin: '2026-10-01T10:00:00', limiteCuentas: null })], total: 2, pagina: 1, tamanioPagina: 8,
  porEstado: { ACTIVA: 1, CERRADA: 1 } };
const DETAIL = {
  fila: row(), identificador: '30712345671', tipoIdentificador: 'CUIT', reaperturas: 1, cupoUtilizado: 8, cuposDisponibles: 992, porcentajeUtilizacion: 0.8,
  invitacionesPendientes: 2, pacientesActivos: 12, pacientesRegistrados: 15,
  dispositivosAsignados: [{ idDispositivo: 'd-1', codigoDispositivo: 'DEV-001', nombre: 'Oxímetro', modelo: 'HC-06', modeloSensor: 'MAX30102', versionFirmware: '1.2.0',
    estado: 'OPERATIVO', fechaAsignacion: '2026-09-02T10:00:00', lecturasInvalidasRecientes: 1 },
  { idDispositivo: 'd-2', codigoDispositivo: 'DEV-002', nombre: null, modelo: null, modeloSensor: 'MAX30100', versionFirmware: null, estado: 'FUERA_DE_SERVICIO',
    fechaAsignacion: null, lecturasInvalidasRecientes: 0 }],
  medicionesTotal: 90, medicionesPeriodo: 30, completadas: 70, canceladas: 12, invalidas: 8, ultimaActividad: '2026-10-08T11:00:00',
};

const AUDIT = {
  items: [
    { idAuditoria: 'a-1', fechaHora: '2026-10-18T10:00:00', categoria: 'PAUSA', accion: 'PAUSAR_INSTITUCION', etiqueta: 'Pausa de institución', resultado: 'EXITO',
      actor: 'Administrador del sistema', motivo: 'Revisión de seguridad', estadoAnterior: 'ACTIVA', estadoNuevo: 'INACTIVA' },
    { idAuditoria: 'a-2', fechaHora: '2026-10-18T09:00:00', categoria: 'CUPOS', accion: 'MODIFICAR_CUPOS_INSTITUCION', etiqueta: 'Cambio de límite de cuentas', resultado: 'EXITO',
      actor: 'Moderador del sistema', limiteAnterior: 1000, limiteNuevo: 5, cuentasActivas: 8, excedente: 3 },
  ],
  total: 2, pagina: 1, tamanioPagina: 10, categorias: { PAUSA: 'Pausa y reactivación', CUPOS: 'Cupos' },
};

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

function panel(meBody, accountBody, extra = {}) {
  return mockApi({
    'GET /auth/me': jsonResponse(200, accountBody), 'GET /platform/me': jsonResponse(200, meBody),
    'GET /platform/dashboard': jsonResponse(200, DASHBOARD), 'GET /platform/system': jsonResponse(200, SYSTEM),
    'GET /platform/institutions': jsonResponse(200, INSTITUTIONS), ...extra,
  });
}

describe('Acceso administrativo', () => {
  it('el administrador inicia sesión con MFA y entra al dashboard', async () => {
    clearTokens();
    let loggedIn = false;
    const { calls } = mockApi({
      'POST /auth/login': jsonResponse(200, { estado: 'MFA_REQUERIDO', challengeToken: 'challenge-1', challengeExpiresIn: 300 }),
      'POST /auth/mfa/verify': () => { loggedIn = true; return jsonResponse(200, { estado: 'AUTENTICADO', tokens: TOKENS, camposFaltantes: [] }); },
      'GET /auth/me': () => (loggedIn ? jsonResponse(200, ADMIN_ACCOUNT) : jsonResponse(401, { codigo: 'TOKEN_INVALIDO', detail: 'x' })),
      'GET /platform/me': jsonResponse(200, me()), 'GET /platform/dashboard': jsonResponse(200, DASHBOARD), 'GET /platform/system': jsonResponse(200, SYSTEM),
    });
    const user = userEvent.setup();
    renderAt('/plataforma/login');
    expect(await screen.findByRole('heading', { level: 2, name: 'Administración de GlucoLume' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '¿Olvidaste tu contraseña?' })).toHaveAttribute('href', '/plataforma/recuperar');
    expect(screen.getByRole('button', { name: /Continuar con Google/ })).toBeInTheDocument();
    await user.type(screen.getByLabelText('Correo electrónico o usuario'), 'victoria');
    await user.type(screen.getByLabelText('Contraseña'), 'Clave#2026');
    await user.click(screen.getByRole('button', { name: /^Continuar$/ }));
    await user.type(await screen.findByLabelText(/Código/), '123456');
    await user.click(screen.getByRole('button', { name: /Verificar|Continuar|Ingresar/ }));
    expect(await screen.findByRole('heading', { name: 'Dashboard general' })).toBeInTheDocument();
    expect(calls.some((call) => call.key === 'GET /platform/me')).toBe(true);
    expect(calls.find((call) => call.key === 'POST /auth/login').body).toMatchObject({ acceso: 'PLATAFORMA' });
  });

  it('la dirección /administracion/login lleva al mismo acceso administrativo y no concede nada por conocerla', async () => {
    clearTokens();
    const { calls } = mockApi({ 'GET /auth/me': jsonResponse(401, { codigo: 'TOKEN_INVALIDO', detail: 'x' }) });
    renderAt('/administracion/login');
    expect(await screen.findByRole('heading', { level: 2, name: 'Administración de GlucoLume' })).toBeInTheDocument();
    expect(calls.some((call) => call.key.startsWith('GET /platform'))).toBe(false); // sin sesión no se pide nada del panel
  });

  it('un usuario común es rechazado (403) y su sesión se cierra', async () => {
    clearTokens();
    let loggedIn = false;
    const { calls } = mockApi({
      'POST /auth/login': () => { loggedIn = true; return jsonResponse(200, { estado: 'AUTENTICADO', tokens: TOKENS, camposFaltantes: [] }); },
      'GET /auth/me': () => (loggedIn ? jsonResponse(200, ACCOUNT) : jsonResponse(401, { codigo: 'TOKEN_INVALIDO', detail: 'x' })),
      'GET /platform/me': jsonResponse(403, { codigo: 'ACCESO_PLATAFORMA_DENEGADO', detail: 'No tenés acceso a la administración de la plataforma.' }),
      'POST /auth/logout': NO_CONTENT,
    });
    const user = userEvent.setup();
    renderAt('/plataforma/login');
    await user.type(await screen.findByLabelText('Correo electrónico o usuario'), 'persona');
    await user.type(screen.getByLabelText('Contraseña'), 'Clave#2026');
    await user.click(screen.getByRole('button', { name: /^Continuar$/ }));
    expect(await screen.findByText(/no tiene acceso a la administración/)).toBeInTheDocument();
    expect(calls.some((call) => call.key === 'POST /auth/logout')).toBe(true);
    expect(screen.queryByRole('heading', { name: 'Dashboard general' })).not.toBeInTheDocument();
  });

  it('abrir /plataforma a mano con una cuenta común muestra el rechazo y no consulta nada más', async () => {
    const { calls } = mockApi({
      'GET /auth/me': jsonResponse(200, ACCOUNT),
      'GET /platform/me': jsonResponse(403, { codigo: 'ACCESO_PLATAFORMA_DENEGADO', detail: 'x' }),
    });
    renderAt('/plataforma/dashboard');
    expect(await screen.findByText('No tenés acceso a la administración de la plataforma.')).toBeInTheDocument();
    expect(calls.some((call) => call.key === 'GET /platform/dashboard')).toBe(false);
  });

  it('sin sesión redirige al acceso administrativo', async () => {
    clearTokens();
    mockApi({});
    renderAt('/plataforma/dashboard');
    expect(await screen.findByRole('heading', { level: 2, name: 'Administración de GlucoLume' })).toBeInTheDocument();
  });
});

describe('Menú y permisos', () => {
  it('el administrador ve todas las secciones; las marcadas como futuras no simulan operaciones', async () => {
    panel(me(), ADMIN_ACCOUNT);
    renderAt('/plataforma/dashboard');
    const nav = within(await screen.findByRole('navigation', { name: 'Secciones de administración' }));
    for (const label of ['Dashboard general', 'Moderadores del sistema', 'Transferir administración', 'Dispositivos globales', 'Matrices globales',
      'Instituciones', 'Auditoría y seguridad', 'Próximamente', 'Mi perfil', 'Seguridad y MFA', 'Cambiar contraseña']) {
      expect(nav.getByRole('link', { name: label })).toBeInTheDocument();
    }
    expect(screen.getByRole('button', { name: 'Cerrar sesión' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Administración de GlucoLume' })).toHaveAttribute('href', '/plataforma/dashboard');
  });

  it('el moderador ve solo lo técnico y su dashboard es técnico', async () => {
    panel(MOD_ME, MOD_ACCOUNT, {
      'GET /platform/dashboard': jsonResponse(200, { ...DASHBOARD, alcance: 'TECNICO', usuarios: null, instituciones: null, grupos: null, eventosRecientes: [], actividadPorModulo: [] }),
    });
    renderAt('/plataforma/dashboard');
    const nav = within(await screen.findByRole('navigation', { name: 'Secciones de administración' }));
    expect(await screen.findByRole('heading', { name: 'Dashboard técnico' })).toBeInTheDocument();
    for (const label of ['Dispositivos globales', 'Matrices globales', 'Instituciones', 'Mi perfil']) expect(nav.getByRole('link', { name: label })).toBeInTheDocument();
    for (const label of ['Moderadores del sistema', 'Transferir administración', 'Auditoría y seguridad', 'Próximamente']) {
      expect(nav.queryByRole('link', { name: label })).not.toBeInTheDocument();
    }
    expect(screen.queryByRole('group', { name: 'Resumen de instituciones' })).not.toBeInTheDocument(); // sí lista instituciones, pero sin el resumen de cuentas
    expect(screen.queryByRole('region', { name: /Seguridad y actividad/ })).not.toBeInTheDocument(); // el moderador no ve cuentas ni seguridad
  });

  it('el moderador que abre una sección del administrador a mano ve el aviso', async () => {
    panel(MOD_ME, MOD_ACCOUNT);
    renderAt('/plataforma/moderadores');
    expect(await screen.findByText('Tu rol no permite acceder a esta sección.')).toBeInTheDocument();
  });

  it('sin MFA solo se puede configurar la seguridad; no se consultan los datos', async () => {
    const { calls } = panel(me({ requiereConfigurarMfa: true, mfaHabilitado: false }), { ...ADMIN_ACCOUNT, mfaHabilitado: false });
    renderAt('/plataforma/dashboard');
    expect(await screen.findByText(/activá la verificación en dos pasos \(MFA\)/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Configurar ahora' })).toHaveAttribute('href', '/plataforma/seguridad');
    expect(calls.some((call) => call.key === 'GET /platform/dashboard')).toBe(false);
  });
});

describe('Dashboard global', () => {
  it('muestra el estado real de los componentes con sus cuatro estados diferenciados', async () => {
    panel(me(), ADMIN_ACCOUNT);
    renderAt('/plataforma/dashboard');
    const components = within(await screen.findByRole('list', { name: 'Componentes de la plataforma' }));
    expect(components.getByText('Base de datos').closest('li')).toHaveTextContent('Operativo');
    expect(components.getByText('Correo (SMTP)').closest('li')).toHaveTextContent('No disponible');
    expect(components.getByText('Acceso con Google').closest('li')).toHaveTextContent('Degradado');
    expect(components.getByText(/Adquisición por puerto serie/).closest('li')).toHaveTextContent('Estado desconocido');
    expect(components.getByText('Base de datos').closest('li')).toHaveAttribute('title', expect.stringContaining('Consulta de prueba a SQL Server'));
    expect(screen.getByText(/3 componentes requieren atención/)).toBeInTheDocument();
  });

  it('prioriza cifras clave y separa cuentas, dispositivos, mediciones operativas y seguridad con datos del backend', async () => {
    panel(me(), ADMIN_ACCOUNT);
    renderAt('/plataforma/dashboard');
    const stats = within(await screen.findByRole('list', { name: 'Indicadores principales' }));
    expect(stats.getByText('Cuentas registradas').closest('li')).toHaveTextContent(/12.*10 activas · 2 inactivas/);
    expect(stats.getByText('Instituciones activas').closest('li')).toHaveTextContent(/1.*de 3 en total/);
    expect(stats.getByText('Dispositivos operativos').closest('li')).toHaveTextContent(/5.*de 7 registrados/);
    const access = within(screen.getByRole('list', { name: 'Accesos por tipo de cuenta' }));
    expect(access.getByText('Accesos individuales').closest('li')).toHaveTextContent(/3.*intentos fallidos.*20 ingresos correctos/);
    expect(access.getByText('Accesos institucionales').closest('li')).toHaveTextContent(/2.*intentos fallidos.*15 ingresos correctos/);
    expect(access.getByText('Accesos de sistema / plataforma').closest('li')).toHaveTextContent(/1.*intentos fallidos.*5 ingresos correctos/);
    expect(access.getByText('Accesos individuales').closest('li')).toHaveClass('is-warn'); // los fallidos conservan el color de advertencia
    expect(screen.queryByText('Accesos fallidos')).not.toBeInTheDocument(); // ya no hay una tarjeta agregada
    expect(screen.getByText(/Sin clasificar: 1 intento fallido · 1 ingreso correcto/)).toBeInTheDocument(); // aparte, sin repartirse
    const accounts = within(screen.getByRole('region', { name: /Cuentas y grupos/ }));
    expect(accounts.getByText('Institucionales').closest('div')).toHaveTextContent(/6.*5 con vínculo activo · 1 sin vínculo/);
    expect(accounts.getByText('Registradas en 7 días').closest('div')).toHaveTextContent('2');
    const devices = within(screen.getByRole('region', { name: /Dispositivos/ }));
    expect(devices.getByText('Con lecturas inválidas (7 días)').closest('div')).toHaveTextContent(/2.*no implica avería/);
    expect(devices.getByText('Desconectados').closest('div')).toHaveTextContent(/No disponible.*no registra la conexión/); // nada inventado
    const meas = within(screen.getByRole('region', { name: /Mediciones: volumen operativo/ }));
    expect(meas.getByText('Errores técnicos (período)').closest('div')).toHaveTextContent('5');
    expect(within(meas.getByRole('list', { name: 'Errores técnicos por motivo' })).getByText('Lectura no válida').closest('li')).toHaveTextContent('3');
    const security = within(screen.getByRole('region', { name: /Seguridad y actividad/ }));
    expect(security.getByText('Cuentas bloqueadas').closest('div')).toHaveTextContent(/1.*1 con bloqueo temporal vigente/);
    expect(security.getByText('Exportaciones de datos').closest('div')).toHaveTextContent(/0.*ninguna registrada/);
    expect(security.getByRole('link', { name: /Auditoría y seguridad/ })).toHaveAttribute('href', '/plataforma/auditoria');
    expect(security.getByText(/invitar moderador plataforma/)).toBeInTheDocument();
    expect(screen.queryByText(/glucemia|SpO₂|oxigenación/i)).not.toBeInTheDocument(); // sin valores clínicos
  });

  it('la tabla de instituciones muestra estado, fechas, personal y límite, y permite buscar y filtrar', async () => {
    const { calls } = panel(me(), ADMIN_ACCOUNT);
    const user = userEvent.setup();
    renderAt('/plataforma/dashboard');
    const table = within(await screen.findByRole('table', { name: 'Instituciones registradas en GlucoLume' }));
    expect(table.getByText('Centro Médico San José').closest('tr')).toHaveTextContent(/Activa.*01\/09\/2026.*2.*5.*8.*1\.000/);
    expect(table.getByText('Clínica Sur').closest('tr')).toHaveTextContent(/Cerrada.*01\/10\/2026.*Sin informar/);
    expect(table.getByRole('link', { name: 'Ver detalle de Centro Médico San José' })).toHaveAttribute('href', '/plataforma/instituciones/i-1');
    await user.type(screen.getByPlaceholderText('Buscar por nombre'), 'Sur');
    await waitFor(() => expect(new URL(calls.filter((call) => call.key === 'GET /platform/institutions').at(-1).url).searchParams.get('busqueda')).toBe('Sur'));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Estado' }), 'CERRADA');
    await waitFor(() => expect(new URL(calls.filter((call) => call.key === 'GET /platform/institutions').at(-1).url).searchParams.get('estado')).toBe('CERRADA'));
  });

  it('el detalle de una institución es un módulo aparte, administrativo y sin pacientes ni valores clínicos', async () => {
    panel(me(), ADMIN_ACCOUNT, { 'GET /platform/institutions/i-1': jsonResponse(200, DETAIL) });
    renderAt('/plataforma/instituciones/i-1');
    expect(await screen.findByRole('heading', { name: 'Centro Médico San José' })).toBeInTheDocument();
    expect(screen.getByText(/no incluye pacientes, personas ni resultados clínicos/)).toBeInTheDocument();
    expect(screen.getByText('Cuentas en uso').closest('div')).toHaveTextContent('8 de 1.000');
    expect(screen.getByText('Pacientes activos').closest('div')).toHaveTextContent(/12.*15 registrados \(solo cantidad\)/);
    const devices = within(screen.getByRole('table', { name: 'Dispositivos asignados a la institución' }));
    expect(devices.getByText('DEV-001').closest('tr')).toHaveTextContent(/Operativo.*1/);
    expect(devices.getByText('DEV-002').closest('tr')).toHaveTextContent(/Fuera de servicio/);
    expect(screen.getByText(/Una lectura cancelada no implica que el dispositivo esté averiado/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Volver a instituciones/ })).toHaveAttribute('href', '/plataforma/instituciones');
  });

  it('pausa una institución con motivo obligatorio y muestra el aviso con la evidencia que devuelve el backend', async () => {
    const paused = { ...DETAIL, fila: row({ estado: 'INACTIVA' }), suspension: { motivo: 'Revisión de seguridad en curso', fecha: '2026-10-18T10:00:00', rolActor: 'MODERADOR_PLATAFORMA' } };
    const { calls } = panel(MOD_ME, MOD_ACCOUNT, {
      'GET /platform/institutions/i-1': jsonResponse(200, DETAIL), 'GET /platform/institutions/i-1/audit': jsonResponse(200, AUDIT),
      'POST /platform/institutions/i-1/pause': jsonResponse(200, paused),
    });
    const user = userEvent.setup();
    renderAt('/plataforma/instituciones/i-1');
    await user.click(await screen.findByRole('button', { name: /Pausar institución/ }));
    const dialog = within(screen.getByRole('dialog', { name: 'Pausar institución' }));
    expect(dialog.getByRole('button', { name: 'Pausar institución' })).toBeDisabled(); // sin motivo no se puede confirmar
    await user.type(dialog.getByLabelText('Motivo'), 'corto');
    expect(dialog.getByRole('button', { name: 'Pausar institución' })).toBeDisabled();
    await user.type(dialog.getByLabelText('Motivo'), ' y suficiente');
    await user.click(dialog.getByRole('button', { name: 'Pausar institución' }));
    expect(await screen.findByText(/Institución pausada\./)).toBeInTheDocument();
    expect(screen.getByText(/Revisión de seguridad en curso/)).toBeInTheDocument();
    expect(calls.find((call) => call.key === 'POST /platform/institutions/i-1/pause').body).toEqual({ motivo: 'corto y suficiente' });
    expect(screen.getByRole('button', { name: /Reactivar institución/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Pausar institución/ })).not.toBeInTheDocument();
  });

  it('reducir el límite por debajo de las cuentas activas advierte que se conservan y que la institución queda excedida', async () => {
    const exceeded = { ...DETAIL, fila: row({ limiteCuentas: 5 }), excedente: 3, cuposDisponibles: 0 };
    const { calls } = panel(me(), ADMIN_ACCOUNT, {
      'GET /platform/institutions/i-1': jsonResponse(200, DETAIL), 'GET /platform/institutions/i-1/audit': jsonResponse(200, AUDIT),
      'PUT /platform/institutions/i-1/capacity': jsonResponse(200, exceeded),
    });
    const user = userEvent.setup();
    renderAt('/plataforma/instituciones/i-1');
    await user.click(await screen.findByRole('button', { name: /Modificar límite de cuentas/ }));
    const dialog = within(screen.getByRole('dialog', { name: 'Modificar límite de cuentas' }));
    const limit = dialog.getByLabelText('Nuevo límite de cuentas');
    await user.clear(limit);
    await user.type(limit, '5');
    expect(dialog.getByText(/se conservan todas, no se suspende ninguna/)).toBeInTheDocument();
    await user.type(dialog.getByLabelText('Motivo'), 'Ajuste del plan contratado');
    await user.click(dialog.getByRole('button', { name: 'Guardar límite' }));
    expect(await screen.findByText(/Institución excedida:/)).toBeInTheDocument();
    expect(calls.find((call) => call.key === 'PUT /platform/institutions/i-1/capacity').body).toEqual({ capacidadMaxima: 5, motivo: 'Ajuste del plan contratado' });
  });

  it('el límite se valida en pantalla antes de enviar (entero positivo y acotado)', async () => {
    panel(me(), ADMIN_ACCOUNT, { 'GET /platform/institutions/i-1': jsonResponse(200, DETAIL), 'GET /platform/institutions/i-1/audit': jsonResponse(200, AUDIT) });
    const user = userEvent.setup();
    renderAt('/plataforma/instituciones/i-1');
    await user.click(await screen.findByRole('button', { name: /Modificar límite de cuentas/ }));
    const dialog = within(screen.getByRole('dialog', { name: 'Modificar límite de cuentas' }));
    await user.type(dialog.getByLabelText('Motivo'), 'Ajuste del plan contratado');
    const limit = dialog.getByLabelText('Nuevo límite de cuentas');
    await user.clear(limit);
    await user.type(limit, '0');
    expect(dialog.getByRole('button', { name: 'Guardar límite' })).toBeDisabled();
    await user.clear(limit);
    await user.type(limit, '999999');
    expect(dialog.getByRole('button', { name: 'Guardar límite' })).toBeDisabled();
  });

  it('la auditoría de la institución muestra eventos administrativos y permite filtrar, sin datos personales', async () => {
    const { calls } = panel(me(), ADMIN_ACCOUNT, { 'GET /platform/institutions/i-1': jsonResponse(200, DETAIL), 'GET /platform/institutions/i-1/audit': jsonResponse(200, AUDIT) });
    const user = userEvent.setup();
    renderAt('/plataforma/instituciones/i-1');
    const table = within(await screen.findByRole('table', { name: 'Eventos de auditoría de la institución' }));
    expect(table.getByText('Pausa de institución').closest('tr')).toHaveTextContent(/Administrador del sistema.*Exitoso.*ACTIVA → INACTIVA.*Motivo: Revisión/);
    expect(table.getByText('Cambio de límite de cuentas').closest('tr')).toHaveTextContent(/Límite 1\.000 → 5 \(8 activas, 3 de más\)/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Resultado' }), 'FALLO');
    await waitFor(() => expect(new URL(calls.filter((call) => call.key === 'GET /platform/institutions/i-1/audit').at(-1).url).searchParams.get('resultado')).toBe('FALLO'));
  });

  it('el administrador elimina una institución con nombre exacto, motivo y reautenticación (contraseña y código)', async () => {
    const closed = { ...DETAIL, fila: row({ estado: 'CERRADA' }), cierreAdministrativo: { motivo: 'Cierre por incumplimiento', fecha: '2026-10-18T10:00:00', rolActor: 'ADMINISTRADOR_PLATAFORMA' } };
    const { calls } = panel(me(), ADMIN_ACCOUNT, {
      'GET /platform/institutions/i-1': jsonResponse(200, DETAIL), 'GET /platform/institutions/i-1/audit': jsonResponse(200, AUDIT),
      'POST /platform/institutions/i-1/delete': jsonResponse(200, closed),
    });
    const user = userEvent.setup();
    renderAt('/plataforma/instituciones/i-1');
    await user.click(await screen.findByRole('button', { name: /Eliminar institución/ }));
    const dialog = within(screen.getByRole('dialog', { name: 'Eliminar institución' }));
    const confirm = dialog.getByRole('button', { name: 'Eliminar institución' });
    expect(confirm).toBeDisabled();
    await user.type(dialog.getByLabelText(/Escribí el nombre exacto/), 'Otra institución');
    await user.type(dialog.getByLabelText('Motivo'), 'Cierre por incumplimiento');
    await user.type(dialog.getByLabelText('Tu contraseña'), 'Secreta-123');
    await user.type(dialog.getByLabelText(/Código de verificación/), '123456');
    expect(confirm).toBeDisabled(); // el nombre no coincide
    await user.clear(dialog.getByLabelText(/Escribí el nombre exacto/));
    await user.type(dialog.getByLabelText(/Escribí el nombre exacto/), 'centro médico san josé');
    expect(confirm).toBeEnabled();
    await user.click(confirm);
    expect(await screen.findByText(/Eliminada por la administración de GlucoLume/)).toBeInTheDocument();
    expect(calls.find((call) => call.key === 'POST /platform/institutions/i-1/delete').body).toEqual({
      motivo: 'Cierre por incumplimiento', confirmacionNombre: 'centro médico san josé', reautenticacion: { password: 'Secreta-123', codigo: '123456' },
    });
    expect(screen.queryByRole('button', { name: /Eliminar institución|Pausar institución|Modificar límite/ })).not.toBeInTheDocument(); // cerrada: sin acciones
  });

  it('el moderador del sistema no ve la eliminación y sin el cierre administrativo en la base el administrador la ve deshabilitada', async () => {
    panel(MOD_ME, MOD_ACCOUNT, { 'GET /platform/institutions/i-1': jsonResponse(200, DETAIL), 'GET /platform/institutions/i-1/audit': jsonResponse(200, AUDIT) });
    const { unmount } = renderAt('/plataforma/instituciones/i-1');
    expect(await screen.findByRole('button', { name: /Pausar institución/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Eliminar institución/ })).not.toBeInTheDocument();
    unmount();
    panel(me(), ADMIN_ACCOUNT, { 'GET /platform/institutions/i-1': jsonResponse(200, { ...DETAIL, eliminacionDisponible: false }), 'GET /platform/institutions/i-1/audit': jsonResponse(200, AUDIT) });
    renderAt('/plataforma/instituciones/i-1');
    expect(await screen.findByRole('button', { name: /Eliminar institución/ })).toBeDisabled();
    expect(screen.getByText(/no tiene el cierre administrativo del esquema vigente/)).toBeInTheDocument();
  });

  it('muestra errores de carga y la ausencia de instituciones sin inventar datos', async () => {
    panel(me(), ADMIN_ACCOUNT, { 'GET /platform/institutions': jsonResponse(200, { items: [], total: 0, pagina: 1, tamanioPagina: 8, porEstado: {} }) });
    renderAt('/plataforma/dashboard');
    expect(await screen.findByText('No hay instituciones con esos filtros.')).toBeInTheDocument();
  });

  it('si el estado de los componentes falla, avisa y el resto del dashboard sigue disponible', async () => {
    panel(me(), ADMIN_ACCOUNT, { 'GET /platform/system': jsonResponse(500, { codigo: 'ERROR_SERVIDOR', detail: 'x' }) });
    renderAt('/plataforma/dashboard');
    expect(await screen.findByText(/No pudimos consultar el estado de los componentes/)).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Indicadores principales' })).toBeInTheDocument();
  });

  it('cambiar el período vuelve a pedir los indicadores', async () => {
    const { calls } = panel(me(), ADMIN_ACCOUNT);
    const user = userEvent.setup();
    renderAt('/plataforma/dashboard');
    await screen.findByRole('list', { name: 'Indicadores principales' });
    await user.selectOptions(screen.getByLabelText('Período'), '7');
    await waitFor(() => expect(new URL(calls.filter((call) => call.key === 'GET /platform/dashboard').at(-1).url).searchParams.get('dias')).toBe('7'));
  });

  it('los accesos por tipo en cero no inventan nada: sin advertencia y sin línea de «sin clasificar»', async () => {
    const zero = { fallidos: 0, exitosos: 0 };
    panel(me(), ADMIN_ACCOUNT, {
      'GET /platform/dashboard': jsonResponse(200, { ...DASHBOARD, seguridad: { ...DASHBOARD.seguridad, loginsFallidos: 0, loginsExitosos: 0,
        accesosPorTipo: { individual: zero, institucional: zero, plataforma: zero, sinClasificar: zero } } }),
    });
    renderAt('/plataforma/dashboard');
    const stats = within(await screen.findByRole('list', { name: 'Accesos por tipo de cuenta' }));
    for (const label of ['Accesos individuales', 'Accesos institucionales', 'Accesos de sistema / plataforma']) {
      const card = stats.getByText(label).closest('li');
      expect(card).toHaveTextContent(/0.*intentos fallidos.*0 ingresos correctos/);
      expect(card).toHaveClass('is-ok');
    }
    expect(screen.queryByText(/Sin clasificar/)).not.toBeInTheDocument();
  });

  it('el moderador del sistema ve la parte técnica y el listado de instituciones, sin las métricas de cuentas ni seguridad', async () => {
    const { calls } = panel(MOD_ME, MOD_ACCOUNT, {
      'GET /platform/dashboard': jsonResponse(200, { ...DASHBOARD, alcance: 'TECNICO', usuarios: null, instituciones: null, grupos: null, seguridad: null,
        eventosRecientes: [], erroresRecientes: [], operacionesAdministrativas: [], actividadPorModulo: [] }),
    });
    renderAt('/plataforma/dashboard');
    expect(await screen.findByRole('list', { name: 'Indicadores principales' })).toBeInTheDocument();
    expect(screen.queryByText('Cuentas registradas')).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: /Seguridad y actividad/ })).not.toBeInTheDocument();
    expect(await screen.findByRole('table', { name: 'Instituciones registradas en GlucoLume' })).toBeInTheDocument(); // supervisa instituciones
    expect(screen.queryByRole('group', { name: 'Resumen de instituciones' })).not.toBeInTheDocument();
    expect(calls.some((call) => call.key === 'GET /platform/institutions')).toBe(true);
  });
});

const MODERATOR = {
  idUsuario: 'm-1', nombre: 'Luis', apellido: 'Gómez', correoElectronico: 'luis@example.com', usuario: 'luismod', estadoCuenta: 'ACTIVO',
  estadoAcceso: 'ACTIVO', mfaHabilitado: true, tieneCredencialLocal: true, tieneGoogle: false, fechaCreacion: '2026-10-01T10:00:00-03:00',
  ultimoAcceso: '2026-10-08T09:00:00-03:00', invitacionVence: null,
};

describe('Moderadores del sistema', () => {
  it('invita a un moderador pidiendo reautenticación y sin permitir elegir el rol', async () => {
    const { calls } = panel(me(), ADMIN_ACCOUNT, {
      'GET /platform/moderators': [jsonResponse(200, [MODERATOR]), jsonResponse(200, [MODERATOR, { ...MODERATOR, idUsuario: 'm-2', nombre: 'Ana', estadoAcceso: 'INVITADO', estadoCuenta: 'PENDIENTE', usuario: null, mfaHabilitado: false, invitacionVence: '2026-10-12T10:00:00-03:00' }])],
      'POST /platform/moderators': jsonResponse(201, { moderador: MODERATOR, correoEnviado: true, mensaje: 'Enviamos la invitación al correo indicado.' }),
    });
    const user = userEvent.setup();
    renderAt('/plataforma/moderadores');
    expect(await screen.findByRole('heading', { name: 'Moderadores del sistema' })).toBeInTheDocument();
    expect(within(await screen.findByRole('list', { name: 'Moderadores del sistema' })).getByText('Activo')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Agregar moderador/ }));
    const form = within(screen.getByRole('form', { name: /Agregar moderador del sistema/ }));
    expect(form.queryByLabelText(/Rol/)).not.toBeInTheDocument();
    await user.click(form.getByRole('button', { name: 'Enviar invitación' }));
    expect(screen.getByText('Ingresá el nombre.')).toBeInTheDocument();
    await user.type(form.getByLabelText('Nombre'), 'Ana');
    await user.type(form.getByLabelText('Apellido'), 'Paz');
    await user.type(form.getByLabelText('Correo electrónico'), 'ana@example.com');
    await user.type(form.getByLabelText('Tu contraseña'), 'Clave#2026');
    await user.type(form.getByLabelText(/Código de verificación/), '123456');
    await user.click(form.getByRole('button', { name: 'Enviar invitación' }));
    expect(await screen.findByText('Enviamos la invitación al correo indicado.')).toBeInTheDocument();
    expect(calls.find((call) => call.key === 'POST /platform/moderators').body).toEqual({
      nombre: 'Ana', apellido: 'Paz', correoElectronico: 'ana@example.com', reautenticacion: { password: 'Clave#2026', codigo: '123456' },
    });
    expect(await screen.findByText('Invitación enviada')).toBeInTheDocument();
  });

  it('una cuenta existente que no es de plataforma se informa sin convertirla', async () => {
    panel(me(), ADMIN_ACCOUNT, {
      'GET /platform/moderators': jsonResponse(200, []),
      'POST /platform/moderators': jsonResponse(409, { codigo: 'CUENTA_NO_CONVERTIBLE', detail: 'Ese correo ya pertenece a una cuenta de GlucoLume que no es de plataforma. Invitá otro correo.' }),
    });
    const user = userEvent.setup();
    renderAt('/plataforma/moderadores');
    await user.click(await screen.findByRole('button', { name: /Agregar moderador/ }));
    const form = within(screen.getByRole('form', { name: /Agregar moderador del sistema/ }));
    await user.type(form.getByLabelText('Nombre'), 'X');
    await user.type(form.getByLabelText('Apellido'), 'Y');
    await user.type(form.getByLabelText('Correo electrónico'), 'indiv@example.com');
    await user.type(form.getByLabelText('Tu contraseña'), 'Clave#2026');
    await user.type(form.getByLabelText(/Código de verificación/), '123456');
    await user.click(form.getByRole('button', { name: 'Enviar invitación' }));
    expect(await screen.findByText(/no es de plataforma/)).toBeInTheDocument();
  });

  it('revoca el acceso con reautenticación y restablece contraseñas sin mostrar credenciales', async () => {
    const { calls } = panel(me(), ADMIN_ACCOUNT, {
      'GET /platform/moderators': jsonResponse(200, [MODERATOR]),
      'POST /platform/moderators/m-1/revoke': jsonResponse(200, { ...MODERATOR, estadoAcceso: 'REVOCADO', estadoCuenta: 'BLOQUEADO' }),
      'POST /platform/moderators/m-1/password-reset': jsonResponse(200, { moderador: MODERATOR, correoEnviado: true, mensaje: 'Enviamos el enlace de restablecimiento al correo del moderador.' }),
    });
    const user = userEvent.setup();
    renderAt('/plataforma/moderadores');
    await user.click(await screen.findByRole('button', { name: /Restablecer la contraseña: Luis Gómez/ }));
    let panelForm = within(screen.getByRole('form', { name: /Restablecer la contraseña: Luis Gómez/ }));
    await user.type(panelForm.getByLabelText('Tu contraseña'), 'Clave#2026');
    await user.type(panelForm.getByLabelText(/Código de verificación/), '123456');
    await user.click(panelForm.getByRole('button', { name: 'Enviar enlace' }));
    expect(await screen.findByText(/Enviamos el enlace de restablecimiento al correo del moderador/)).toBeInTheDocument();
    expect(screen.queryByText(/Clave#2026/)).not.toBeInTheDocument();
    expect(calls.find((call) => call.key.endsWith('/password-reset')).body).toEqual({ reautenticacion: { password: 'Clave#2026', codigo: '123456' } });

    await user.click(screen.getByRole('button', { name: /Revocar el acceso: Luis Gómez/ }));
    panelForm = within(screen.getByRole('form', { name: /Revocar el acceso: Luis Gómez/ }));
    await user.click(panelForm.getByRole('button', { name: 'Revocar acceso' }));
    expect(screen.getByText(/Ingresá tu contraseña y el código/)).toBeInTheDocument(); // sin reautenticación no se envía
    expect(calls.some((call) => call.key.endsWith('/revoke'))).toBe(false);
  });

  it('el detalle de un moderador muestra sus datos administrativos', async () => {
    panel(me(), ADMIN_ACCOUNT, { 'GET /platform/moderators/m-1': jsonResponse(200, MODERATOR) });
    renderAt('/plataforma/moderadores/m-1');
    expect(await screen.findByRole('heading', { name: 'Luis Gómez' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Detalle del moderador' })).toBeInTheDocument(); // antes la pantalla no tenía h1
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByText('luis@example.com')).toBeInTheDocument();
    expect(screen.getByText('Moderador del sistema')).toBeInTheDocument();
  });
});

const PENDING = { idTransferenciaAdministracion: 't-1', estado: 'PENDIENTE', fechaSolicitud: '2026-10-09T10:00:00-03:00', fechaRespuesta: null,
  origenNombre: 'Victoria Cortés', destinoNombre: 'Luis Gómez', idUsuarioOrigen: 'u-1', idUsuarioDestino: 'm-1', esOrigen: true, esDestino: false };

describe('Transferir administración', () => {
  it('el administrador elige un moderador elegible, confirma y reautentica', async () => {
    const { calls } = panel(me(), ADMIN_ACCOUNT, {
      'GET /platform/transfer': [jsonResponse(200, { pendiente: null, elegibles: [{ idUsuario: 'm-1', nombre: 'Luis', apellido: 'Gómez' }], historial: [] }),
        jsonResponse(200, { pendiente: PENDING, elegibles: [], historial: [PENDING] })],
      'POST /platform/transfer': jsonResponse(201, PENDING),
    });
    const user = userEvent.setup();
    renderAt('/plataforma/transferencia');
    await user.selectOptions(await screen.findByLabelText('Moderador del sistema'), 'm-1');
    expect(screen.getByText(/pasa a ser la única administradora del sistema/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Continuar' })).toBeDisabled(); // falta confirmar la advertencia
    await user.click(screen.getByLabelText(/Entiendo y quiero transferir/));
    await user.click(screen.getByRole('button', { name: 'Continuar' }));
    const confirm = within(screen.getByRole('form', { name: 'Confirmar la transferencia' }));
    await user.type(confirm.getByLabelText('Tu contraseña'), 'Clave#2026');
    await user.type(confirm.getByLabelText(/Código de verificación/), '654321');
    await user.click(confirm.getByRole('button', { name: 'Solicitar transferencia' }));
    expect(await screen.findByText(/Hasta que el moderador acepte no cambia ningún permiso/)).toBeInTheDocument();
    expect(calls.find((call) => call.key === 'POST /platform/transfer').body).toEqual({
      idUsuarioDestino: 'm-1', reautenticacion: { password: 'Clave#2026', codigo: '654321' },
    });
    expect(await screen.findByRole('heading', { name: 'Transferencia pendiente' })).toBeInTheDocument();
  });

  it('el destinatario acepta: el panel se reconstruye con los permisos del administrador', async () => {
    const incoming = { ...PENDING, esOrigen: false, esDestino: true };
    let accepted = false;
    const { calls } = panel(MOD_ME, MOD_ACCOUNT, {
      'GET /platform/me': () => jsonResponse(200, accepted ? me() : { ...MOD_ME, transferenciaPendiente: incoming }),
      'GET /platform/transfer': jsonResponse(200, { pendiente: incoming, elegibles: [], historial: [] }),
      'POST /platform/transfer/accept': () => { accepted = true; return jsonResponse(200, { ...incoming, estado: 'ACEPTADA' }); },
    });
    const user = userEvent.setup();
    renderAt('/plataforma/transferencia');
    expect(await screen.findByText(/te ofrece el control principal de GlucoLume/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Moderador del sistema')).not.toBeInTheDocument(); // un moderador no inicia transferencias
    await user.click(screen.getByRole('button', { name: 'Aceptar' }));
    const confirm = within(screen.getByRole('form', { name: 'Aceptar la administración' }));
    await user.type(confirm.getByLabelText('Tu contraseña'), 'Clave#2026');
    await user.type(confirm.getByLabelText(/Código de verificación/), '111222');
    await user.click(confirm.getByRole('button', { name: 'Aceptar' }));
    expect(await screen.findByRole('link', { name: 'Auditoría y seguridad' })).toBeInTheDocument(); // ya tiene permisos de administrador
    expect(calls.some((call) => call.key === 'POST /platform/transfer/accept')).toBe(true);
  });

  it('el destinatario puede rechazar y el moderador sin transferencia ve el aviso', async () => {
    const incoming = { ...PENDING, esOrigen: false, esDestino: true };
    panel(MOD_ME, MOD_ACCOUNT, {
      'GET /platform/transfer': [jsonResponse(200, { pendiente: incoming, elegibles: [], historial: [] }), jsonResponse(200, { pendiente: null, elegibles: [], historial: [] })],
      'POST /platform/transfer/reject': jsonResponse(200, { ...incoming, estado: 'RECHAZADA' }),
    });
    const user = userEvent.setup();
    renderAt('/plataforma/transferencia');
    await user.click(await screen.findByRole('button', { name: 'Rechazar' }));
    const confirm = within(screen.getByRole('form', { name: 'Rechazar la administración' }));
    await user.type(confirm.getByLabelText('Tu contraseña'), 'Clave#2026');
    await user.type(confirm.getByLabelText(/Código de verificación/), '111222');
    await user.click(confirm.getByRole('button', { name: 'Rechazar' }));
    expect(await screen.findByText('Rechazaste la administración.')).toBeInTheDocument();
    expect(await screen.findByText(/Solo el administrador del sistema puede transferir el control/)).toBeInTheDocument();
  });
});

describe('Suscripciones y pagos', () => {
  it('figura como próximamente y no ofrece operaciones comerciales', async () => {
    panel(me(), ADMIN_ACCOUNT);
    renderAt('/plataforma/suscripciones');
    expect(await screen.findByRole('heading', { name: 'Próximamente' })).toBeInTheDocument();
    expect(screen.getByText(/no hay cobros, suscripciones, facturación ni integraciones/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Pagar|Suscribir|Contratar|Facturar/ })).not.toBeInTheDocument();
  });
});

describe('Activación y recuperación', () => {
  it('el enlace del correo (/administracion/activar#codigo=…) completa el código y lo quita de la barra', async () => {
    clearTokens();
    mockApi({});
    renderAt('/administracion/activar#codigo=codigo-del-correo-0123456789');
    await screen.findByLabelText('Código de activación');
    // La pantalla se carga de forma diferida: el efecto que lee el fragmento corre después de que aparece el campo.
    await waitFor(() => expect(screen.getByLabelText('Código de activación')).toHaveValue('codigo-del-correo-0123456789'));
    await waitFor(() => expect(window.location.hash).toBe('')); // el código no queda en la barra ni en el historial
  });

  it('los enlaces anteriores (/plataforma/activar?token=…) llevan a la misma pantalla de activación, sin otra lógica', async () => {
    clearTokens();
    const { calls } = mockApi({});
    renderAt('/plataforma/activar?token=codigo-viejo-0123456789012');
    expect(await screen.findByRole('heading', { name: 'Activar cuenta administrativa' })).toBeInTheDocument();
    expect(screen.getByLabelText('Código de activación')).toHaveValue('codigo-viejo-0123456789012');
    expect(window.location.search).toBe('');
    expect(calls.some((call) => call.key.includes('/activation/check') || call.key.includes('/activation/complete'))).toBe(false); // ya no hay camino sin identidad
  });

  it('el acceso administrativo ofrece «Activar cuenta» para quien tiene un código y lleva a una vista aparte', async () => {
    clearTokens();
    mockApi({ 'GET /auth/me': jsonResponse(401, { codigo: 'TOKEN_INVALIDO', detail: 'x' }) });
    const user = userEvent.setup();
    renderAt('/administracion/login');
    expect(await screen.findByText(/¿Tenés un código de activación administrativa\?/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Código de activación')).not.toBeInTheDocument(); // no se mezcla con el login
    await user.click(screen.getByRole('link', { name: 'Activar cuenta' }));
    expect(await screen.findByRole('heading', { name: 'Activar cuenta administrativa' })).toBeInTheDocument();
    expect(screen.getByLabelText('Código de activación')).toBeInTheDocument();
  });

  it('activa con el código de la invitación (sin volver a pedir nombre ni correo), sin enviar ningún rol, y lleva a configurar MFA', async () => {
    clearTokens();
    let loggedIn = false;
    const { calls } = mockApi({
      'POST /platform/activation/with-code': () => { loggedIn = true; return jsonResponse(200, { estado: 'AUTENTICADO', tokens: TOKENS, camposFaltantes: [] }); },
      'GET /auth/me': () => (loggedIn ? jsonResponse(200, { ...ADMIN_ACCOUNT, mfaHabilitado: false }) : jsonResponse(401, { codigo: 'TOKEN_INVALIDO', detail: 'x' })),
      'GET /platform/me': jsonResponse(200, { ...me(), mfaHabilitado: false, requiereConfigurarMfa: true }),
    });
    const user = userEvent.setup();
    renderAt('/administracion/activar');
    await user.type(await screen.findByLabelText('Código de activación'), 'codigo-de-un-solo-uso-0123456789');
    await user.type(screen.getByLabelText('Nombre de usuario'), 'anaadmin');
    await user.type(screen.getAllByLabelText(/^Contraseña/)[0], 'Zorro#Lento-2027');
    await user.type(screen.getByLabelText('Repetir contraseña'), 'Zorro#Lento-2027');
    await user.click(screen.getByRole('button', { name: /Activar cuenta/ }));
    expect(await screen.findByRole('heading', { name: 'Seguridad y MFA' })).toBeInTheDocument();
    expect(screen.getByText(/Activación completada. Falta configurar la verificación en dos pasos/)).toBeInTheDocument();
    const sent = calls.find((call) => call.key === 'POST /platform/activation/with-code').body;
    expect(sent).toEqual({ codigo: 'codigo-de-un-solo-uso-0123456789', usuario: 'anaadmin', password: 'Zorro#Lento-2027', confirmacion: 'Zorro#Lento-2027' });
    expect(Object.keys(sent)).not.toEqual(expect.arrayContaining(['rol']));
  });

  it('un código inválido, vencido o ya usado muestra siempre el mismo mensaje y no activa nada', async () => {
    clearTokens();
    const { calls } = mockApi({
      'POST /platform/activation/with-code': jsonResponse(400, { codigo: 'CODIGO_ACTIVACION_INVALIDO', detail: 'El código no es válido, venció o ya fue usado, o los datos no coinciden con los de la invitación.' }),
    });
    const user = userEvent.setup();
    renderAt('/administracion/activar?codigo=un-codigo-que-no-sirve-0123456789');
    expect(await screen.findByLabelText('Código de activación')).toHaveValue('un-codigo-que-no-sirve-0123456789'); // el enlace lo completa
    expect(window.location.search).toBe(''); // y no queda en la barra de direcciones
    await user.type(screen.getByLabelText('Nombre de usuario'), 'anaadmin');
    await user.type(screen.getAllByLabelText(/^Contraseña/)[0], 'Zorro#Lento-2027');
    await user.type(screen.getByLabelText('Repetir contraseña'), 'Zorro#Lento-2027');
    await user.click(screen.getByRole('button', { name: /Activar cuenta/ }));
    expect(await screen.findByText(/El código no es válido, venció o ya fue usado/)).toBeInTheDocument();
    expect(calls.filter((call) => call.key === 'POST /platform/activation/with-code')).toHaveLength(1);
    expect(screen.queryByRole('heading', { name: 'Seguridad y MFA' })).not.toBeInTheDocument();
  });

  it('valida en el navegador contraseña y confirmación antes de enviar (el servidor vuelve a validar)', async () => {
    clearTokens();
    const { calls } = mockApi({});
    const user = userEvent.setup();
    renderAt('/administracion/activar');
    await user.type(await screen.findByLabelText('Código de activación'), 'corto');
    await user.click(screen.getByRole('button', { name: /Activar cuenta/ }));
    expect(await screen.findByText('Ingresá el código de activación completo.')).toBeInTheDocument();
    expect(calls.some((call) => call.key.startsWith('POST'))).toBe(false);
  });

  it('recuperar la contraseña responde siempre igual y restablecer usa el enlace', async () => {
    clearTokens();
    const { calls } = mockApi({
      'POST /platform/password/forgot': NO_CONTENT,
      'POST /platform/password/reset': jsonResponse(200, { mensaje: 'Contraseña actualizada. Iniciá sesión con la nueva.' }),
    });
    const user = userEvent.setup();
    renderAt('/plataforma/recuperar');
    await user.type(await screen.findByLabelText('Correo electrónico'), 'nadie@example.com');
    await user.click(screen.getByRole('button', { name: /Enviar enlace/ }));
    expect(await screen.findByText(/Si el correo corresponde a una cuenta administrativa/)).toBeInTheDocument();
    expect(calls.find((call) => call.key === 'POST /platform/password/forgot').body).toEqual({ correoElectronico: 'nadie@example.com' });
  });

  it('restablecer pide una contraseña que cumpla la política y confirma el cierre de sesiones', async () => {
    clearTokens();
    const { calls } = mockApi({ 'POST /platform/password/reset': jsonResponse(200, { mensaje: 'ok' }) });
    const user = userEvent.setup();
    renderAt('/plataforma/restablecer?token=reset-9');
    await user.type(await screen.findByLabelText('Contraseña nueva'), 'corta');
    await user.type(screen.getByLabelText('Repetir contraseña'), 'corta');
    await user.click(screen.getByRole('button', { name: /Guardar contraseña/ }));
    expect(screen.getByText('La contraseña no cumple todos los requisitos.')).toBeInTheDocument();
    await user.clear(screen.getByLabelText('Contraseña nueva'));
    await user.clear(screen.getByLabelText('Repetir contraseña'));
    await user.type(screen.getByLabelText('Contraseña nueva'), 'Zorro#Lento-2027');
    await user.type(screen.getByLabelText('Repetir contraseña'), 'Zorro#Lento-2027');
    await user.click(screen.getByRole('button', { name: /Guardar contraseña/ }));
    expect(await screen.findByText(/Cerramos tus sesiones abiertas/)).toBeInTheDocument();
    expect(calls.find((call) => call.key === 'POST /platform/password/reset').body).toEqual({ token: 'reset-9', password: 'Zorro#Lento-2027' });
  });
});

describe('Cuenta', () => {
  it('cambia la propia contraseña con la actual, la confirmación y el código MFA', async () => {
    const { calls } = panel(me(), ADMIN_ACCOUNT, { 'POST /platform/password/change': jsonResponse(200, { mensaje: 'Cambiaste tu contraseña. Cerramos tus otras sesiones.' }) });
    const user = userEvent.setup();
    renderAt('/plataforma/cambiar-contrasena');
    await user.type(await screen.findByLabelText('Contraseña actual'), 'Clave#2026');
    await user.type(screen.getByLabelText('Contraseña nueva'), 'Zorro#Lento-2027');
    await user.type(screen.getByLabelText('Confirmar contraseña nueva'), 'Zorro#Lento-2027');
    await user.type(screen.getByLabelText(/Código de verificación/), '123456');
    await user.click(screen.getByRole('button', { name: 'Cambiar contraseña' }));
    expect(await screen.findByText('Cambiaste tu contraseña. Cerramos tus otras sesiones.')).toBeInTheDocument();
    expect(calls.find((call) => call.key === 'POST /platform/password/change').body).toEqual({
      passwordActual: 'Clave#2026', passwordNueva: 'Zorro#Lento-2027', confirmacion: 'Zorro#Lento-2027', codigo: '123456',
    });
  });

  it('una cuenta solo Google puede crear una contraseña local desde el panel', async () => {
    const google = me({ tieneCredencialLocal: false, tieneGoogle: true });
    const { calls } = panel(google, ADMIN_ACCOUNT, {
      'GET /platform/me': [jsonResponse(200, google), jsonResponse(200, me({ tieneCredencialLocal: true, tieneGoogle: true }))],
      'POST /auth/password': jsonResponse(201, { mensaje: 'Contraseña local agregada.' }),
    });
    const user = userEvent.setup();
    renderAt('/plataforma/cambiar-contrasena');
    expect(await screen.findByRole('heading', { name: 'Crear contraseña' })).toBeInTheDocument();
    await user.type(screen.getByLabelText('Nueva contraseña'), 'Zorro#Lento-2027');
    await user.type(screen.getByLabelText('Confirmar contraseña'), 'Zorro#Lento-2027');
    await user.click(screen.getByRole('button', { name: 'Crear contraseña' }));
    expect(await screen.findByText(/Contraseña creada con éxito/)).toBeInTheDocument();
    expect(calls.find((call) => call.key === 'POST /auth/password').body).toEqual({ password: 'Zorro#Lento-2027' });
    expect(await screen.findByLabelText('Contraseña actual')).toBeInTheDocument(); // ahora sí puede cambiarla
  });
});
