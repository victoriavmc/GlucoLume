import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../test/helpers.js';
import { renderAt } from '../../../test/renderApp.jsx';

const INSTITUTIONAL = { ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };
const ID = '9a000000-0000-4000-8000-000000000001';
const BASE = `/institutions/${ID}`;
const PATIENTS = ['CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES', 'BAJA_PACIENTES'];
const PERMISOS = {
  PROPIETARIO: ['CONSULTAR_INSTITUCION', 'MODIFICAR_INSTITUCION', 'GESTIONAR_MODERADORES', 'ADMINISTRAR_OPERADORES',
    'CONSULTAR_EQUIPO', 'ELIMINAR_INSTITUCION', ...PATIENTS],
  MODERADOR: ['CONSULTAR_INSTITUCION', 'INCORPORAR_OPERADORES', 'ADMINISTRAR_OPERADORES', 'CONSULTAR_EQUIPO', ...PATIENTS],
  OPERADOR: ['CONSULTAR_INSTITUCION', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES'],
};

function summary(rol = 'PROPIETARIO', overrides = {}) {
  return {
    idInstitucion: ID, nombre: 'Centro Médico San José', tipoInstitucion: 'CLINICA', estado: 'ACTIVA',
    rolInstitucion: rol, estadoRelacion: 'ACTIVO', permisos: PERMISOS[rol], ...overrides,
  };
}

function detail(rol = 'PROPIETARIO', overrides = {}) {
  return {
    ...summary(rol), tipoIdentificadorLegal: 'CUIT', identificadorLegal: '30712345671', descripcion: null,
    fechaCreacion: '2026-10-01T10:00:00', fechaActualizacion: '2026-10-02T11:30:00',
    propietario: { nombre: 'Victoria', apellido: 'Cortés' },
    cantidadModeradores: 1, cantidadOperadores: 2, cantidadPacientes: 5, ...overrides,
  };
}

const MODERATOR = {
  idInstitucionUsuario: 'r-2', nombre: 'Pablo', apellido: 'Ríos', usuario: 'pablorios', rolInstitucion: 'MODERADOR',
  estadoRelacion: 'ACTIVO', fechaIncorporacion: '2026-10-02T09:00:00', invitacionVencida: false,
};
const PENDING = {
  idInstitucionUsuario: 'r-3', nombre: 'Lucía', apellido: 'Sosa', usuario: 'lsosa', rolInstitucion: 'MODERADOR',
  estadoRelacion: 'PENDIENTE', fechaInvitacion: '2026-10-05T09:00:00', fechaVencimientoInvitacion: '2026-10-12T09:00:00',
  invitacionVencida: false,
};

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

function routes(extra = {}, account = INSTITUTIONAL) {
  return mockApi({ 'GET /auth/me': jsonResponse(200, account), 'GET /institutions/invitations': jsonResponse(200, []), ...extra });
}

describe('Menú y acceso', () => {
  it('muestra "Instituciones" solo a cuentas USUARIO_INSTITUCIONAL', async () => {
    routes({ 'GET /institutions/mine': jsonResponse(200, []) });
    renderAt('/app/inicio');
    const nav = await screen.findByRole('navigation', { name: 'Secciones de la cuenta' });
    expect(within(nav).getByRole('link', { name: 'Instituciones' })).toHaveAttribute('href', '/app/instituciones');
  });

  it('una cuenta personal no ve la sección ni puede abrirla por URL', async () => {
    const { calls } = mockApi({ 'GET /auth/me': jsonResponse(200, ACCOUNT) });
    renderAt(`/app/instituciones/${ID}/moderadores`);
    expect(await screen.findByRole('heading', { name: 'Hola, Victoria' })).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Secciones de la cuenta' });
    expect(within(nav).queryByRole('link', { name: 'Instituciones' })).not.toBeInTheDocument();
    expect(calls.some((call) => call.key.includes('/institutions'))).toBe(false);
  });
});

describe('Inicio institucional', () => {
  it('sin instituciones ofrece crear una (sin inventar ninguna) y crea con rol de propietario', async () => {
    const { calls } = routes({
      'GET /institutions/mine': jsonResponse(200, []),
      'POST /institutions/legal-id/status': jsonResponse(200, { estado: 'DISPONIBLE', puedeReabrir: false }),
      'POST /institutions': jsonResponse(201, { ...detail(), operacion: 'CREADA' }),
      [`GET ${BASE}`]: jsonResponse(200, detail('PROPIETARIO', { cantidadModeradores: 0, cantidadOperadores: 0 })),
    });
    const user = userEvent.setup();
    renderAt('/app/instituciones');
    expect(await screen.findByText('Todavía no estás vinculado a ninguna institución.')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Tus instituciones' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Crear una institución/ }));
    await user.type(screen.getByLabelText('Nombre de la institución'), 'Centro Médico San José');
    await user.selectOptions(screen.getByLabelText('Tipo de institución'), 'CLINICA');
    // Solo los datos que almacena Institucion: no hay campos de contacto ni ubicación.
    expect(screen.queryByLabelText(/Correo electrónico de contacto|Teléfono|Provincia/)).not.toBeInTheDocument();
    // Aviso mínimo de privacidad y conservación antes de crear, con enlace a la política.
    expect(screen.getByText(/responsable de informar a sus pacientes y obtener su consentimiento/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Política de privacidad' })).toHaveAttribute('href', '/privacidad');
    await user.type(screen.getByLabelText('CUIT'), '30-7123456-71');
    await user.click(screen.getByRole('button', { name: 'Crear institución' }));
    expect(screen.getByText(/Ingresá un CUIT válido/)).toBeInTheDocument();

    await user.clear(screen.getByLabelText('CUIT'));
    await user.type(screen.getByLabelText('CUIT'), '30-71234567-1');
    await user.click(screen.getByRole('button', { name: 'Crear institución' }));

    expect(await screen.findByRole('heading', { name: 'Centro Médico San José', level: 1 })).toBeInTheDocument();
    expect(screen.getByText(/Ya podés designar moderadores/)).toBeInTheDocument();
    expect(calls.find((call) => call.key === 'POST /institutions').body).toEqual({
      nombre: 'Centro Médico San José', tipoInstitucion: 'CLINICA', tipoIdentificadorLegal: 'CUIT',
      identificadorLegal: '30712345671', descripcion: null,
    });
  });

  it('CUIT de una institución activa: se informa y se bloquea el registro', async () => {
    const { calls } = routes({
      'GET /institutions/mine': jsonResponse(200, []),
      'POST /institutions/legal-id/status': jsonResponse(200, {
        estado: 'ACTIVA', puedeReabrir: false, mensaje: 'Ya existe una institución activa registrada con este CUIT.',
      }),
    });
    const user = userEvent.setup();
    renderAt('/app/instituciones');
    await user.click(await screen.findByRole('button', { name: /Crear una institución/ }));
    await user.type(screen.getByLabelText('Nombre de la institución'), 'Centro Médico San José');
    await user.type(screen.getByLabelText('CUIT'), '30712345671');
    await user.tab();
    expect(await screen.findByText('Ya existe una institución activa registrada con este CUIT.')).toBeInTheDocument();
    expect(screen.getByLabelText('CUIT')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('button', { name: 'Crear institución' })).toBeDisabled();
    expect(calls.find((call) => call.key === 'POST /institutions/legal-id/status').body).toEqual({
      tipoIdentificadorLegal: 'CUIT', identificadorLegal: '30712345671',
    });
    expect(calls.some((call) => call.key === 'POST /institutions')).toBe(false);
  });

  it('CUIT de una institución cerrada ajena: se informa sin datos ni opción de reabrir', async () => {
    routes({
      'GET /institutions/mine': jsonResponse(200, []),
      'POST /institutions/legal-id/status': jsonResponse(200, {
        estado: 'CERRADA', puedeReabrir: false, institucion: null,
        mensaje: 'Hay una institución cerrada registrada con este CUIT. Solo quien fue su último propietario puede solicitar la reapertura.',
      }),
    });
    const user = userEvent.setup();
    renderAt('/app/instituciones');
    await user.click(await screen.findByRole('button', { name: /Crear una institución/ }));
    await user.type(screen.getByLabelText('CUIT'), '30712345671');
    await user.tab();
    expect(await screen.findByText(/Solo quien fue su último propietario/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Reabrir institución/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Crear institución' })).toBeDisabled();
  });

  it('CUIT de una institución cerrada propia: se reabre directamente desde el mismo formulario', async () => {
    const message = 'Esta institución se encuentra cerrada. Completá sus nuevos datos para reabrirla.';
    const { calls } = routes({
      'GET /institutions/mine': jsonResponse(200, []),
      'POST /institutions/legal-id/status': jsonResponse(200, {
        estado: 'CERRADA', puedeReabrir: true, mensaje: message,
        institucion: { nombre: 'Centro Médico San José', tipoInstitucion: 'CLINICA', descripcion: null, cantidadReaperturas: 1 },
      }),
      'POST /institutions/reopen': jsonResponse(200, {
        ...detail('PROPIETARIO', { nombre: 'San José Norte', cantidadReaperturas: 2 }), operacion: 'REABIERTA',
      }),
      [`GET ${BASE}`]: jsonResponse(200, detail('PROPIETARIO', { nombre: 'San José Norte', cantidadReaperturas: 2 })),
    });
    const user = userEvent.setup();
    renderAt('/app/instituciones');
    await user.click(await screen.findByRole('button', { name: /Crear una institución/ }));
    await user.type(screen.getByLabelText('CUIT'), '30-71234567-1');
    await user.tab();

    // Mismo formulario, precargado, con la acción directa de reapertura (sin pasos ni solicitudes intermedias).
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Reabrir institución' })).toBeInTheDocument();
    expect(screen.getByLabelText('Nombre de la institución')).toHaveValue('Centro Médico San José');
    expect(screen.getByText(/reapertura n\.º 2/)).toBeInTheDocument();
    await user.clear(screen.getByLabelText('Nombre de la institución'));
    await user.type(screen.getByLabelText('Nombre de la institución'), 'San José Norte');
    await user.click(screen.getByRole('button', { name: 'Reabrir institución' }));
    expect(screen.getByText('Ingresá tu contraseña actual.')).toBeInTheDocument();
    expect(calls.some((call) => call.key === 'POST /institutions/reopen')).toBe(false);

    await user.type(screen.getByLabelText('Contraseña actual'), 'Clave#2026');
    await user.click(screen.getByRole('button', { name: 'Reabrir institución' }));

    expect(await screen.findByText(/Reabriste «San José Norte» \(reapertura n\.º 2\)/)).toBeInTheDocument();
    expect(calls.find((call) => call.key === 'POST /institutions/reopen').body).toEqual({
      nombre: 'San José Norte', tipoInstitucion: 'CLINICA', descripcion: null, tipoIdentificadorLegal: 'CUIT',
      identificadorLegal: '30712345671', password: 'Clave#2026',
    });
    expect(calls.some((call) => call.key === 'POST /institutions')).toBe(false);
  });

  it('escribir el CUIT cerrado y tocar el botón enseguida activa el modo reapertura sin crear ni reabrir', async () => {
    const { calls } = routes({
      'GET /institutions/mine': jsonResponse(200, []),
      'POST /institutions/legal-id/status': jsonResponse(200, {
        estado: 'CERRADA', puedeReabrir: true, mensaje: 'Esta institución se encuentra cerrada. Completá sus nuevos datos para reabrirla.',
        institucion: { nombre: 'san cristo', tipoInstitucion: 'CONSULTORIO', descripcion: null, cantidadReaperturas: 0 },
      }),
    });
    const user = userEvent.setup();
    renderAt('/app/instituciones');
    await user.click(await screen.findByRole('button', { name: /Crear una institución/ }));
    await user.type(screen.getByLabelText('Nombre de la institución'), 'Otra');
    await user.type(screen.getByLabelText('CUIT'), '23439387904');
    await user.click(screen.getByRole('button', { name: /Crear institución|Reabrir institución/ }));

    expect(await screen.findByRole('heading', { name: 'Reabrir institución' })).toBeInTheDocument();
    expect(screen.getByText('Esta institución se encuentra cerrada. Completá sus nuevos datos para reabrirla.')).toBeInTheDocument();
    expect(screen.getByLabelText('CUIT')).toHaveAttribute('readonly');
    expect(screen.getByLabelText('Nombre de la institución')).toHaveValue('san cristo');
    expect(calls.some((call) => call.key === 'POST /institutions')).toBe(false);
    expect(calls.some((call) => call.key === 'POST /institutions/reopen')).toBe(false);
  });

  it('si la reapertura no está autorizada, se rechaza sin quedar nada pendiente', async () => {
    routes({
      'GET /institutions/mine': jsonResponse(200, []),
      'POST /institutions/legal-id/status': [
        jsonResponse(200, {
          estado: 'CERRADA', puedeReabrir: true, mensaje: 'Esta institución se encuentra cerrada. Completá sus nuevos datos para reabrirla.',
          institucion: { nombre: 'Centro Médico San José', tipoInstitucion: 'CLINICA', descripcion: null, cantidadReaperturas: 0 },
        }),
        jsonResponse(200, { estado: 'CERRADA', puedeReabrir: false, mensaje: 'Solo quien fue su último propietario puede reabrirla.' }),
      ],
      'POST /institutions/reopen': jsonResponse(403, {
        codigo: 'REPRESENTACION_NO_VERIFICADA', detail: 'Solo quien fue su último propietario puede reabrirla.',
      }),
    });
    const user = userEvent.setup();
    renderAt('/app/instituciones');
    await user.click(await screen.findByRole('button', { name: /Crear una institución/ }));
    await user.type(screen.getByLabelText('CUIT'), '30712345671');
    await user.tab();
    await user.type(await screen.findByLabelText('Contraseña actual'), 'Clave#2026');
    await user.click(screen.getByRole('button', { name: 'Reabrir institución' }));
    // Error explícito, una sola vez, y el formulario sale del modo reapertura: nada se da por reabierto.
    expect(await screen.findByRole('alert')).toHaveTextContent('Solo quien fue su último propietario puede reabrirla.');
    expect(screen.queryByRole('button', { name: 'Reabrir institución' })).not.toBeInTheDocument();
    expect(screen.queryByText(/Reabriste/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Crear institución' })).toBeDisabled();
  });

  it('acepta una invitación recibida y la institución aparece en la lista', async () => {
    const invitation = {
      idInstitucionUsuario: 'inv-1', idInstitucion: ID, nombreInstitucion: 'Centro Médico San José',
      tipoInstitucion: 'CLINICA', rolInstitucion: 'OPERADOR', nombreInvitante: 'Pablo Ríos',
      fechaInvitacion: '2026-10-05T09:00:00', fechaVencimiento: '2026-10-12T09:00:00', estado: 'PENDIENTE',
    };
    const { calls } = routes({
      'GET /institutions/invitations': [jsonResponse(200, [invitation]), jsonResponse(200, [])],
      'GET /institutions/mine': [jsonResponse(200, []), jsonResponse(200, [summary('OPERADOR')])],
      'POST /institutions/invitations/inv-1/accept': jsonResponse(200, summary('OPERADOR')),
    });
    const user = userEvent.setup();
    renderAt('/app/instituciones');
    expect(await screen.findByText(/Rol propuesto: Operador\/a/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Aceptar invitación de Centro Médico San José' }));
    expect(await screen.findByText(/Te sumaste a «Centro Médico San José» como operador\/a/)).toBeInTheDocument();
    const list = await screen.findByRole('list', { name: 'Tus instituciones' });
    expect(within(list).getByText('Operador/a')).toBeInTheDocument();
    expect(calls.some((call) => call.key === 'POST /institutions/invitations/inv-1/accept')).toBe(true);
  });

  it('una institución pausada por la plataforma se lista como no disponible, sin enlace, y pide las pausadas al backend', async () => {
    const { calls } = routes({
      'GET /institutions/mine': jsonResponse(200, [summary('PROPIETARIO', { estado: 'INACTIVA' }), summary('OPERADOR', { idInstitucion: 'i-9', nombre: 'Clínica Norte' })]),
    });
    renderAt('/app/instituciones');
    const list = await screen.findByRole('list', { name: 'Tus instituciones' });
    expect(new URL(calls.find((call) => call.key === 'GET /institutions/mine').url).searchParams.get('incluirPausadas')).toBe('true');
    const paused = within(list).getByLabelText(/Centro Médico San José: institución pausada/);
    expect(within(paused).getByText('Pausada')).toBeInTheDocument();
    expect(within(paused).getByText(/no podés operarla hasta que se reactive/)).toBeInTheDocument();
    expect(within(list).getAllByRole('link')).toHaveLength(1); // solo la institución activa se puede abrir
    expect(within(list).getByRole('link', { name: /Clínica Norte/ })).toBeInTheDocument();
  });
});

describe('Institución pausada: consulta al soporte', () => {
  it('el propietario escribe al soporte desde la tarjeta y el formulario envía solo asunto y mensaje', async () => {
    const { calls } = routes({
      'GET /institutions/mine': jsonResponse(200, [summary('PROPIETARIO', { estado: 'INACTIVA' })]),
      [`POST ${BASE}/support-request`]: jsonResponse(200, { mensaje: 'Enviamos tu consulta al soporte de GlucoLume.', confirmacionEnviada: true }),
    });
    const user = userEvent.setup();
    renderAt('/app/instituciones');
    await user.click(await screen.findByRole('button', { name: /Escribir al soporte por Centro Médico San José/ }));
    const dialog = within(screen.getByRole('dialog', { name: 'Escribir al soporte de GlucoLume' }));
    const send = dialog.getByRole('button', { name: 'Enviar consulta' });
    expect(send).toBeDisabled(); // sin mensaje no se envía
    await user.type(dialog.getByLabelText('Mensaje'), 'Ya resolvimos lo que pidieron, solicitamos la reactivación.');
    await user.click(send);
    expect(await screen.findByText(/Enviamos tu consulta al soporte de GlucoLume/)).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(calls.find((call) => call.key === `POST ${BASE}/support-request`).body).toEqual({
      asunto: 'Solicitud de reactivación', mensaje: 'Ya resolvimos lo que pidieron, solicitamos la reactivación.',
    });
  });

  it('quien no es propietario no ve el botón y se le indica que lo pida al propietario', async () => {
    routes({ 'GET /institutions/mine': jsonResponse(200, [summary('OPERADOR', { estado: 'INACTIVA' })]) });
    renderAt('/app/instituciones');
    expect(await screen.findByText(/Pedile al propietario de la institución que se comunique con el soporte/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Escribir al soporte/ })).not.toBeInTheDocument();
  });

  it('muestra el error del backend (por ejemplo el límite de consultas) sin cerrar el formulario', async () => {
    routes({
      'GET /institutions/mine': jsonResponse(200, [summary('PROPIETARIO', { estado: 'INACTIVA' })]),
      [`POST ${BASE}/support-request`]: jsonResponse(429, { codigo: 'DEMASIADAS_SOLICITUDES', detail: 'Enviaste varias consultas seguidas.' }),
    });
    const user = userEvent.setup();
    renderAt('/app/instituciones');
    await user.click(await screen.findByRole('button', { name: /Escribir al soporte/ }));
    const dialog = within(screen.getByRole('dialog'));
    await user.type(dialog.getByLabelText('Mensaje'), 'Necesitamos ayuda con la reactivación.');
    await user.click(dialog.getByRole('button', { name: 'Enviar consulta' }));
    expect(await dialog.findByText(/Enviaste varias consultas seguidas/)).toBeInTheDocument();
  });
});

const OPERATOR_PANEL = {
  periodo: { dias: 30, desde: null, hasta: null }, operador: { idInstitucionUsuario: 'op-1', nombre: 'Victoria', apellido: 'Corti', rolInstitucion: 'OPERADOR', activo: true },
  pacientesAsignados: 0, pacientes: [], medicionesRealizadas: 0, medicionesEnPeriodo: 0, medicionesPorEstado: {}, ultimaActividad: null, realizadas: [],
  ultimasDePacientes: [], transferencias: { recibidas: 0, recibidasPendientes: 0, enviadas: 0, enviadasPendientes: 0 }, dispositivosDisponibles: 0,
  dispositivos: [], esPropio: true,
};

describe('Panel según el rol', () => {
  it.each([
    ['PROPIETARIO', ['Panel', 'Personal', 'Pacientes', 'Administración']],
    ['MODERADOR', ['Panel', 'Personal', 'Pacientes', 'Administración']],
  ])('%s ve solo las secciones que su rol permite', async (rol, tabs) => {
    routes({ [`GET ${BASE}`]: jsonResponse(200, detail(rol)) });
    renderAt(`/app/instituciones/${ID}`);
    const nav = await screen.findByRole('navigation', { name: 'Secciones de la institución' });
    expect(within(nav).getAllByRole('link').map((link) => link.textContent)).toEqual(tabs);
    expect(await screen.findByRole('link', { name: 'Pacientes: 5 activos' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Operadores: 2 activos' })).toBeInTheDocument();
  });

  it('el operador tiene un panel de trabajo propio: sin menú de administración, inventario, estadísticas generales ni accesos que no puede usar', async () => {
    routes({ [`GET ${BASE}`]: jsonResponse(200, detail('OPERADOR')), [`GET ${BASE}/operators/me/dashboard`]: jsonResponse(200, OPERATOR_PANEL),
      [`GET ${BASE}/activity`]: jsonResponse(200, { items: [] }) });
    renderAt(`/app/instituciones/${ID}`);
    const nav = await screen.findByRole('navigation', { name: 'Secciones de la institución' });
    expect(within(nav).getAllByRole('link').map((link) => link.textContent)).toEqual(['Panel', 'Pacientes']);
    const quick = within(await screen.findByRole('region', { name: 'Accesos rápidos' }));
    expect(quick.getAllByRole('link').map((link) => link.textContent.trim())).toEqual(['Administrar mis pacientes', 'Nueva medición']);
    expect(quick.getByRole('link', { name: /Administrar mis pacientes/ })).toHaveAttribute('href', `/app/instituciones/${ID}/pacientes?mios=1`);
    expect(await screen.findByRole('heading', { name: 'Mi dashboard de trabajo' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Mi actividad reciente' })).toBeInTheDocument();
    for (const forbidden of [/Administrar personal/, /Administrar matrices/, /Ver inventario/, /Administrar moderadores/, /Auditoría/,
      /Administración institucional/, /Moderadores/, /Operadores/]) {
      expect(screen.queryByRole('link', { name: forbidden })).not.toBeInTheDocument();
    }
    expect(screen.queryByRole('region', { name: 'Resumen de la institución' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Administración institucional' })).not.toBeInTheDocument();
  });

  it('el operador que abre el inventario por la URL vuelve a su panel', async () => {
    const { calls } = routes({ [`GET ${BASE}`]: jsonResponse(200, detail('OPERADOR')), [`GET ${BASE}/operators/me/dashboard`]: jsonResponse(200, OPERATOR_PANEL),
      [`GET ${BASE}/activity`]: jsonResponse(200, { items: [] }) });
    renderAt(`/app/instituciones/${ID}/dispositivos`);
    expect(await screen.findByRole('heading', { name: 'Mi dashboard de trabajo' })).toBeInTheDocument();
    expect(calls.some((call) => call.key.includes('/devices'))).toBe(false);
  });

  it('el panel no repite los datos administrativos y el encabezado trae migas de pan', async () => {
    routes({ [`GET ${BASE}`]: jsonResponse(200, detail('PROPIETARIO')) });
    renderAt(`/app/instituciones/${ID}`);
    const crumbs = await screen.findByRole('navigation', { name: 'Ruta de navegación' });
    expect(within(crumbs).getByText('Panel')).toHaveAttribute('aria-current', 'page');
    expect(within(crumbs).getByRole('link', { name: 'Instituciones' })).toHaveAttribute('href', '/app/instituciones');
    expect(screen.getByRole('link', { name: 'Volver a instituciones' })).toBeInTheDocument();
    expect(screen.queryByText('30-71234567-1')).not.toBeInTheDocument(); // el CUIT vive en Administración → Datos
    expect(screen.queryByRole('navigation', { name: 'Secciones de pacientes' })).not.toBeInTheDocument();
  });

  it('las rutas anteriores redirigen a su sección y Personal agrupa moderadores y operadores', async () => {
    routes({ [`GET ${BASE}`]: jsonResponse(200, detail('PROPIETARIO')), [`GET ${BASE}/personnel`]: jsonResponse(200, { items: [], total: 0, pagina: 1, tamanioPagina: 15, resumen: { totalActivos: 0, moderadoresActivos: 0, operadoresActivos: 0, propietariosActivos: 0, bajas: 0, invitacionesPendientes: 0 } }) });
    renderAt(`/app/instituciones/${ID}/moderadores`);
    const tabs = await screen.findByRole('navigation', { name: 'Secciones del personal' });
    expect(within(tabs).getAllByRole('link').map((link) => link.textContent)).toEqual(['Todos', 'Moderadores', 'Operadores', 'Invitaciones']);
    expect(within(tabs).getByRole('link', { name: 'Moderadores' })).toHaveClass('is-active');
    const crumbs = screen.getByRole('navigation', { name: 'Ruta de navegación' });
    expect(within(crumbs).getByText('Moderadores')).toHaveAttribute('aria-current', 'page');
    expect(within(crumbs).getByRole('link', { name: 'Personal' })).toBeInTheDocument();
  });

  it('Datos institucionales es una página completa (sin pestañas) con su zona de riesgo; la ruta de Configuración lleva a ella', async () => {
    routes({ [`GET ${BASE}`]: jsonResponse(200, detail('PROPIETARIO')) });
    renderAt(`/app/instituciones/${ID}/configuracion`);
    expect(await screen.findByRole('heading', { name: 'Datos institucionales' })).toBeInTheDocument();
    const crumbs = screen.getByRole('navigation', { name: 'Ruta de navegación' });
    expect(within(crumbs).getByText('Datos institucionales')).toHaveAttribute('aria-current', 'page');
    expect(screen.queryByRole('navigation', { name: 'Secciones de administración' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Zona de riesgo' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Eliminar institución' })).toBeInTheDocument();
  });

  it('el botón de volver lleva al panel desde una sección y a la lista de instituciones solo desde el panel', async () => {
    routes({ [`GET ${BASE}`]: jsonResponse(200, detail('PROPIETARIO')) });
    renderAt(`/app/instituciones/${ID}/administracion/datos`);
    expect(await screen.findByRole('link', { name: 'Volver al panel' })).toHaveAttribute('href', `/app/instituciones/${ID}`);
    expect(screen.queryByRole('link', { name: 'Volver a instituciones' })).not.toBeInTheDocument();
  });

  it('una institución eliminada o ajena se informa sin datos', async () => {
    routes({ [`GET ${BASE}`]: jsonResponse(404, { codigo: 'INSTITUCION_NO_ENCONTRADA', detail: 'x' }) });
    renderAt(`/app/instituciones/${ID}`);
    expect(await screen.findByText(/no pertenecés a ella o fue eliminada/)).toBeInTheDocument();
  });

  it('el moderador consulta los datos institucionales en solo lectura', async () => {
    routes({ [`GET ${BASE}`]: jsonResponse(200, detail('MODERADOR')) });
    renderAt(`/app/instituciones/${ID}/datos`);
    expect(await screen.findByText('Solo el propietario de la institución puede modificar estos datos.')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Identificación legal' })).toHaveTextContent('30-71234567-1');
    expect(screen.queryByRole('button', { name: /Editar datos/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Zona de riesgo' })).not.toBeInTheDocument();
  });

  it.each([['/datos'], ['/configuracion'], ['/administracion/datos']])('el operador que abre %s por la URL vuelve a su panel', async (path) => {
    routes({ [`GET ${BASE}`]: jsonResponse(200, detail('OPERADOR')), [`GET ${BASE}/operators/me/dashboard`]: jsonResponse(200, OPERATOR_PANEL),
      [`GET ${BASE}/activity`]: jsonResponse(200, { items: [] }) });
    renderAt(`/app/instituciones/${ID}${path}`);
    expect(await screen.findByRole('heading', { name: 'Mi dashboard de trabajo' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Datos institucionales' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Zona de riesgo' })).not.toBeInTheDocument();
  });
});

// La gestión de moderadores y operadores se prueba en InstitutionStaff.test.jsx.

describe('Eliminación de la institución', () => {
  it('advierte las consecuencias y exige el nombre exacto y la contraseña', async () => {
    const { calls } = routes({
      [`GET ${BASE}`]: jsonResponse(200, detail()),
      [`POST ${BASE}/deletion`]: { ok: true, status: 204, json: async () => null },
      'GET /institutions/mine': jsonResponse(200, []),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/configuracion`);
    await user.click(await screen.findByRole('button', { name: 'Eliminar institución' }));

    const dialog = screen.getByRole('alertdialog', { name: /¿Eliminar «Centro Médico San José»\?/ });
    expect(dialog).toHaveTextContent(/pierden el acceso de inmediato/);
    expect(dialog).toHaveTextContent(/cuentas personales de los integrantes no se eliminan/);
    const submit = within(dialog).getByRole('button', { name: /Eliminar definitivamente/ });
    expect(submit).toBeDisabled();

    await user.type(within(dialog).getByLabelText(/Escribí «Centro Médico San José»/), 'Centro Médico San José');
    await user.type(within(dialog).getByLabelText('Contraseña actual'), 'Clave#2026');
    expect(submit).toBeEnabled();
    await user.click(submit);

    expect(await screen.findByText(/Eliminaste «Centro Médico San José»/)).toBeInTheDocument();
    expect(calls.find((call) => call.key === `POST ${BASE}/deletion`).body).toEqual({
      confirmacionNombre: 'Centro Médico San José', password: 'Clave#2026',
    });
  });

  it('una cuenta solo Google sin MFA no puede confirmar: se le indica activar la verificación en dos pasos', async () => {
    routes(
      { [`GET ${BASE}`]: jsonResponse(200, detail()) },
      { ...INSTITUTIONAL, tieneCredencialLocal: false, tieneGoogle: true, mfaHabilitado: false },
    );
    renderAt(`/app/instituciones/${ID}/configuracion`);
    expect(await screen.findByText(/Tu cuenta usa Google y no tiene contraseña/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Eliminar institución' })).not.toBeInTheDocument();
  });

  it('una cuenta solo Google con MFA confirma con el código, sin contraseña', async () => {
    routes(
      { [`GET ${BASE}`]: jsonResponse(200, detail()) },
      { ...INSTITUTIONAL, tieneCredencialLocal: false, tieneGoogle: true, mfaHabilitado: true },
    );
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/configuracion`);
    await user.click(await screen.findByRole('button', { name: 'Eliminar institución' }));
    expect(screen.getByLabelText('Código de verificación')).toBeInTheDocument();
    expect(screen.queryByLabelText('Contraseña actual')).not.toBeInTheDocument();
  });

  it('con MFA pide también el código', async () => {
    routes(
      { [`GET ${BASE}`]: jsonResponse(200, detail()) },
      { ...INSTITUTIONAL, mfaHabilitado: true },
    );
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/configuracion`);
    await user.click(await screen.findByRole('button', { name: 'Eliminar institución' }));
    expect(screen.getByLabelText('Código de verificación')).toBeInTheDocument();
  });
});
