import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../test/helpers.js';
import { renderAt } from '../../../test/renderApp.jsx';

const ID = '7b000000-0000-4000-8000-000000000001';
const BASE = `/groups/${ID}`;
const NONE = { compartePerfil: false, comparteUltimaMedicion: false, comparteHistorial: false, notificaMedicion: false };

function group(miRol = 'ADMINISTRADOR', overrides = {}) {
  return {
    idGrupo: ID, nombre: 'Familia Pérez', descripcion: 'Nuestro grupo', estado: 'ACTIVO', fechaCreacion: '2026-10-01T10:00:00',
    administrador: 'Victoria Cortés', cantidadIntegrantes: 2, miRol, idGrupoUsuario: 'gu-me', fechaIncorporacion: '2026-10-01T10:00:00',
    ...overrides,
  };
}

const BETO = { idGrupoUsuario: 'gu-beto', nombre: 'Beto', apellido: 'Ruiz', rol: 'MIEMBRO', ...NONE, tienePerfil: true };
const NO_CONTENT = { ok: true, status: 204, json: async () => null };
const REVOKED = { codigo: 'DATOS_NO_COMPARTIDOS', detail: 'Esta persona no autorizó compartir esta información con el grupo.' };
const EMPTY_HISTORY = { items: [], total: 0, pagina: 1, tamanioPagina: 10 };
const STATS = {
  dias: 30, cantidadMediciones: 3,
  glucosa: { cantidad: 0, promedio: null, minimo: null, maximo: null },
  spo2: { cantidad: 3, promedio: 97, minimo: 96, maximo: 98 },
  frecuenciaCardiaca: { cantidad: 3, promedio: 70, minimo: 70, maximo: 70 },
  serieDiaria: [
    { fecha: '2026-10-06', mediciones: 1, glucosaPromedio: null, spo2Promedio: 96, frecuenciaPromedio: 70 },
    { fecha: '2026-10-08', mediciones: 2, glucosaPromedio: null, spo2Promedio: 97.5, frecuenciaPromedio: 70 },
  ],
};

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

function routes(extra = {}, account = ACCOUNT) {
  return mockApi({ 'GET /auth/me': jsonResponse(200, account), ...extra });
}

describe('Acceso', () => {
  it('"Grupo" aparece solo para cuentas individuales', async () => {
    const institutional = { ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };
    const { calls } = routes({}, institutional);
    renderAt('/app/grupo');
    const nav = await screen.findByRole('navigation', { name: 'Secciones de la cuenta' });
    expect(within(nav).queryByRole('link', { name: 'Grupo' })).not.toBeInTheDocument();
    expect(calls.some((call) => call.key.startsWith('GET /groups'))).toBe(false);
  });
});

describe('Inicio de grupos', () => {
  it('sin grupo: crea uno y entra al panel como administrador', async () => {
    const { calls } = routes({
      'GET /groups/mine': jsonResponse(200, { grupo: null }),
      'GET /groups/invitations': jsonResponse(200, []),
      'POST /groups': jsonResponse(201, group()),
      [`GET ${BASE}`]: jsonResponse(200, group('ADMINISTRADOR', { cantidadIntegrantes: 1 })),
    });
    const user = userEvent.setup();
    renderAt('/app/grupo');
    expect(await screen.findByText('Todavía no formás parte de un grupo')).toBeInTheDocument();
    expect(screen.getByText('No tenés invitaciones pendientes.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Crear grupo/ }));
    await user.click(screen.getByRole('button', { name: 'Crear grupo' }));
    expect(screen.getByText(/Ingresá el nombre del grupo/)).toBeInTheDocument();
    await user.type(screen.getByLabelText('Nombre del grupo'), 'Familia Pérez');
    await user.click(screen.getByRole('button', { name: 'Crear grupo' }));
    expect(await screen.findByText(/Creaste «Familia Pérez»/)).toBeInTheDocument();
    expect(calls.find((call) => call.key === 'POST /groups').body).toEqual({ nombre: 'Familia Pérez', descripcion: null });
  });

  it('sin grupo: ofrece crear uno o unirse con una invitación', async () => {
    routes({ 'GET /groups/mine': jsonResponse(200, { grupo: null }), 'GET /groups/invitations': jsonResponse(200, []) });
    renderAt('/app/grupo');
    expect(await screen.findByRole('heading', { name: 'Crear un grupo' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Unirme a un grupo' })).toBeInTheDocument();
    expect(screen.getByText('Sin invitaciones por ahora')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Crear grupo/ })).toBeInTheDocument();
  });

  it.each([['MIEMBRO', false], ['ADMINISTRADOR', true]])(
    'con grupo (%s): entra directo al panel, sin pantalla intermedia ni opción de crear otro', async (rol, isAdmin) => {
      const { calls } = routes({
        'GET /groups/mine': jsonResponse(200, { grupo: group(rol) }),
        [`GET ${BASE}`]: jsonResponse(200, group(rol)),
        [`GET ${BASE}/dashboard`]: jsonResponse(500, { detail: 'No disponible' }), // el detalle del dashboard no es el objeto de esta prueba
      });
      renderAt('/app/grupo');
      expect(await screen.findByRole('heading', { level: 1, name: 'Familia Pérez' })).toBeInTheDocument();
      const resumen = within(screen.getByRole('list', { name: 'Datos principales del grupo' }));
      expect(resumen.getByText(isAdmin ? 'Administrador/a' : 'Miembro')).toBeInTheDocument();
      const tabs = within(screen.getByRole('navigation', { name: 'Secciones del grupo' }));
      expect(tabs.getAllByRole('link').map((link) => link.textContent)).toEqual(
        ['Panel', 'Integrantes', 'Mi privacidad', 'Configuración']); // las invitaciones viven dentro de Integrantes
      expect(tabs.getByRole('link', { name: 'Panel' })).toHaveAttribute('aria-current', 'page'); // NavTabs anuncia la sección actual
      expect(tabs.getByRole('link', { name: 'Integrantes' })).not.toHaveAttribute('aria-current');
      expect(screen.queryByText('Abrir grupo')).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Crear grupo/ })).not.toBeInTheDocument();
      expect(screen.queryByText('Todavía no formás parte de un grupo')).not.toBeInTheDocument();
      // No se piden invitaciones ni se lista ningún grupo: solo la pertenencia y el detalle de ese grupo.
      expect(calls.some((call) => call.key === 'GET /groups/invitations')).toBe(false);
    },
  );

  it('mientras consulta la pertenencia muestra la carga y no la pantalla de crear grupo', async () => {
    let release;
    routes({
      'GET /groups/mine': () => new Promise((resolve) => { release = () => resolve(jsonResponse(200, { grupo: null })); }),
      'GET /groups/invitations': jsonResponse(200, []),
    });
    renderAt('/app/grupo');
    expect(await screen.findByText('Cargando tu grupo…')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Crear grupo/ })).not.toBeInTheDocument();
    expect(screen.queryByText('Todavía no formás parte de un grupo')).not.toBeInTheDocument();
    await waitFor(() => expect(release).toBeTypeOf('function')); // bajo carga, el pedido puede salir después del primer render
    release();
    expect(await screen.findByText('Todavía no formás parte de un grupo')).toBeInTheDocument();
  });

  it('si falla la consulta no ofrece crear un grupo: muestra el error y permite reintentar', async () => {
    routes({
      'GET /groups/mine': [jsonResponse(500, { detail: 'Error interno' }), jsonResponse(200, { grupo: group('MIEMBRO') })],
      [`GET ${BASE}`]: jsonResponse(200, group('MIEMBRO')),
    });
    const user = userEvent.setup();
    renderAt('/app/grupo');
    await user.click(await screen.findByRole('button', { name: 'Reintentar' }));
    expect(screen.queryByRole('button', { name: /Crear grupo/ })).not.toBeInTheDocument();
    expect(await screen.findByRole('heading', { level: 1, name: 'Familia Pérez' })).toBeInTheDocument();
  });

  it('aceptar una invitación avisa que no comparte mediciones y entra al grupo', async () => {
    const invitation = {
      idGrupoUsuario: 'inv-1', idGrupo: ID, nombreGrupo: 'Familia Pérez', nombreAdministrador: 'Ana Pérez',
      fechaInvitacion: '2026-10-05T09:00:00', fechaVencimiento: '2026-10-12T09:00:00', estado: 'PENDIENTE',
    };
    const { calls } = routes({
      'GET /groups/mine': jsonResponse(200, { grupo: null }),
      'GET /groups/invitations': jsonResponse(200, [invitation]),
      'POST /groups/invitations/inv-1/accept': jsonResponse(200, group('MIEMBRO')),
      [`GET ${BASE}`]: jsonResponse(200, group('MIEMBRO')),
    });
    const user = userEvent.setup();
    renderAt('/app/grupo');
    expect(await screen.findByText(/Invita Ana Pérez/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Aceptar invitación a Familia Pérez' }));
    expect(screen.getByRole('alertdialog')).toHaveTextContent(/no comparte tus mediciones/);
    expect(calls.some((call) => call.key.endsWith('/accept'))).toBe(false);
    await user.click(screen.getByRole('button', { name: /Confirmar y unirme/ }));
    expect(await screen.findByText(/Te uniste a «Familia Pérez»/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Invitaciones/ })).not.toBeInTheDocument(); // miembro
  });
});

describe('Invitaciones (administrador)', () => {
  it('Integrantes tiene un botón Invitar que lleva al formulario y deja el cursor en el correo', async () => {
    routes({
      [`GET ${BASE}`]: jsonResponse(200, group('ADMINISTRADOR')),
      [`GET ${BASE}/members`]: jsonResponse(200, []),
      [`GET ${BASE}/invitations`]: jsonResponse(200, []),
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${ID}/integrantes`);
    await user.click(await screen.findByRole('button', { name: /Invitar/ }));
    expect(screen.getByLabelText('Correo electrónico de la cuenta individual')).toHaveFocus();
  });

  it('un miembro no ve el botón Invitar', async () => {
    routes({
      [`GET ${BASE}`]: jsonResponse(200, group('MIEMBRO')),
      [`GET ${BASE}/members`]: jsonResponse(200, []),
    });
    renderAt(`/app/grupo/${ID}/integrantes`);
    await screen.findByRole('heading', { name: 'Integrantes' });
    expect(screen.queryByRole('button', { name: /Invitar/ })).not.toBeInTheDocument();
  });

  it('correo inexistente: explica y ofrece el registro individual', async () => {
    routes({
      [`GET ${BASE}`]: jsonResponse(200, group()),
      [`GET ${BASE}/members`]: jsonResponse(200, []),
      [`GET ${BASE}/invitations`]: jsonResponse(200, []),
      [`POST ${BASE}/invitations/lookup`]: jsonResponse(404, {
        codigo: 'USUARIO_NO_ENCONTRADO',
        detail: 'No hay una cuenta individual activa con este correo. Si la persona ya se registró, pedile que verifique su correo y volvé a intentar. Si todavía no tiene cuenta, podés enviarle una invitación por correo para que la cree y se sume al grupo.',
      }),
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${ID}/integrantes`);
    await user.type(await screen.findByLabelText('Correo electrónico de la cuenta individual'), 'nadie@example.com');
    await user.click(screen.getByRole('button', { name: /Buscar/ }));
    expect(await screen.findByText(/No hay una cuenta individual activa con este correo/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Registro de cuentas individuales' })).toHaveAttribute('href', '/registro?tipo=usuario');
  });

  it('correo sin cuenta: envía la invitación por correo solo con el correo, sin pedir nombre ni apellido', async () => {
    const { calls } = routes({
      [`GET ${BASE}`]: jsonResponse(200, group()),
      [`GET ${BASE}/members`]: jsonResponse(200, []),
      [`GET ${BASE}/invitations`]: jsonResponse(200, []),
      [`POST ${BASE}/invitations/lookup`]: jsonResponse(404, {
        codigo: 'USUARIO_NO_ENCONTRADO',
        detail: 'No hay una cuenta individual activa con este correo.',
      }),
      [`POST ${BASE}/invitations`]: jsonResponse(201, { idGrupoUsuario: 'gu-lucia', nombre: null, apellido: null,
        fechaInvitacion: '2026-10-08T10:00:00', fechaVencimiento: '2026-10-15T10:00:00', vencida: false }),
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${ID}/integrantes`);
    await user.type(await screen.findByLabelText('Correo electrónico de la cuenta individual'), 'nueva@example.com');
    await user.click(screen.getByRole('button', { name: /Buscar/ }));
    expect(screen.queryByLabelText('Nombre')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Apellido')).not.toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: /Enviar invitación por correo/ }));
    expect(await screen.findByText(/Enviamos a nueva@example.com un correo para que cree su cuenta/)).toBeInTheDocument();
    expect(calls.find((call) => call.key === `POST ${BASE}/invitations`).body).toEqual({ correoElectronico: 'nueva@example.com' });
  });

  it('invita, la invitación queda pendiente y se puede cancelar', async () => {
    const pending = { idGrupoUsuario: 'gu-carla', nombre: 'Carla', apellido: 'Gómez', fechaInvitacion: '2026-10-08T10:00:00',
      fechaVencimiento: '2026-10-15T10:00:00', vencida: false };
    const { calls } = routes({
      [`GET ${BASE}`]: jsonResponse(200, group()),
      [`GET ${BASE}/members`]: jsonResponse(200, []),
      [`GET ${BASE}/invitations`]: [jsonResponse(200, []), jsonResponse(200, [pending]), jsonResponse(200, [])],
      [`POST ${BASE}/invitations/lookup`]: jsonResponse(200, { nombre: 'Carla', apellido: 'Gómez' }),
      [`POST ${BASE}/invitations`]: jsonResponse(201, pending),
      [`DELETE ${BASE}/invitations/gu-carla`]: NO_CONTENT,
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${ID}/integrantes`);
    await user.type(await screen.findByLabelText('Correo electrónico de la cuenta individual'), 'carla@example.com');
    await user.click(screen.getByRole('button', { name: /Buscar/ }));
    await user.click(await screen.findByRole('button', { name: /Enviar invitación/ }));
    expect(await screen.findByText(/Invitación enviada a Carla Gómez/)).toBeInTheDocument();
    expect(await screen.findByText(/Pendiente · vence el 15\/10\/2026/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Cancelar invitación de Carla Gómez' }));
    expect(await screen.findByText('No hay invitaciones pendientes.')).toBeInTheDocument();
    expect(calls.find((call) => call.key === `POST ${BASE}/invitations`).body).toEqual({ correoElectronico: 'carla@example.com' });
  });

  it('reenvía una invitación pendiente sin crear otra y renueva el plazo', async () => {
    const pending = { idGrupoUsuario: 'gu-carla', nombre: 'Carla', apellido: 'Gómez', fechaInvitacion: '2026-10-08T10:00:00',
      fechaVencimiento: '2026-10-15T10:00:00', vencida: false };
    const resent = { ...pending, fechaInvitacion: '2026-10-20T10:00:00', fechaVencimiento: '2026-10-27T10:00:00' };
    const { calls } = routes({
      [`GET ${BASE}`]: jsonResponse(200, group()),
      [`GET ${BASE}/members`]: jsonResponse(200, []),
      [`GET ${BASE}/invitations`]: [jsonResponse(200, [pending]), jsonResponse(200, [resent])],
      [`POST ${BASE}/invitations/gu-carla/resend`]: jsonResponse(200, resent),
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${ID}/integrantes`);
    await user.click(await screen.findByRole('button', { name: 'Reenviar invitación de Carla Gómez' }));
    expect(await screen.findByText(/Reenviaste la invitación a Carla Gómez/)).toBeInTheDocument();
    expect(await screen.findByText(/Pendiente · vence el 27\/10\/2026/)).toBeInTheDocument();
    expect(calls.some((call) => call.key === `POST ${BASE}/invitations`)).toBe(false);
  });

  it('un miembro no ve ni puede abrir la gestión de invitaciones', async () => {
    const { calls } = routes({
      [`GET ${BASE}`]: jsonResponse(200, group('MIEMBRO')),
      [`GET ${BASE}/members`]: jsonResponse(200, []),
    });
    renderAt(`/app/grupo/${ID}/invitaciones`); // la ruta vieja lleva a Integrantes
    expect(await screen.findByRole('heading', { name: 'Integrantes' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Invitar a una persona' })).not.toBeInTheDocument();
    expect(calls.some((call) => call.key === `GET ${BASE}/invitations`)).toBe(false);
  });
});

describe('Mi privacidad', () => {
  it('arranca sin compartir y guarda solo los permisos elegidos', async () => {
    const { calls } = routes({
      [`GET ${BASE}`]: jsonResponse(200, group('MIEMBRO')),
      [`GET ${BASE}/sharing/me`]: jsonResponse(200, { ...NONE, idPerfilMedicion: 'p-1', perfilDisponible: true }),
      [`PUT ${BASE}/sharing/me`]: [
        jsonResponse(200, { ...NONE, comparteUltimaMedicion: true, idPerfilMedicion: 'p-1', perfilDisponible: true }),
        jsonResponse(200, { ...NONE, idPerfilMedicion: 'p-1', perfilDisponible: true }),
      ],
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${ID}/privacidad`);
    expect(await screen.findByText('No compartís ningún dato con el grupo.')).toBeInTheDocument();
    for (const checkbox of screen.getAllByRole('checkbox')) expect(checkbox).not.toBeChecked();
    expect(screen.getByRole('button', { name: /Guardar cambios/ })).toBeDisabled();

    await user.click(screen.getByRole('checkbox', { name: /Última medición/ }));
    await user.click(screen.getByRole('button', { name: /Guardar cambios/ }));
    expect(await screen.findByText(/Guardamos tus permisos/)).toBeInTheDocument();
    expect(calls.find((call) => call.key === `PUT ${BASE}/sharing/me`).body).toEqual({ ...NONE, comparteUltimaMedicion: true });
    // El aviso de medición se ofrece aparte y aclara que nunca incluye el valor.
    expect(screen.getByRole('checkbox', { name: /Aviso de medición/ })).not.toBeChecked();
    expect(screen.getByText(/nunca incluye el valor/)).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /Historial de mediciones/ })).not.toBeChecked();
    expect(screen.getAllByRole('checkbox')).toHaveLength(4);  // 3 de datos + el aviso de medición; sin permiso aparte de estadísticas
    expect(screen.queryByRole('checkbox', { name: /Gráficos y estadísticas/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Dejar de compartir todo/ }));
    expect(await screen.findByText('Dejaste de compartir todos tus datos con el grupo.')).toBeInTheDocument();
    expect(calls.filter((call) => call.key === `PUT ${BASE}/sharing/me`)[1].body).toEqual(NONE);
  });
});

describe('Integrantes y permisos', () => {
  const MEMBERS = [
    { idGrupoUsuario: 'gu-me', nombre: 'Juan', apellido: 'Pérez', rol: 'ADMINISTRADOR', estado: 'ACTIVO',
      fechaIncorporacion: '2026-10-01T10:00:00', esVos: true, ...NONE, comparteHistorial: true, tienePerfil: true },
    { idGrupoUsuario: 'gu-pepe', nombre: 'Pepe', apellido: 'Gómez', rol: 'MIEMBRO', estado: 'ACTIVO',
      fechaIncorporacion: '2026-10-02T10:00:00', esVos: false, ...NONE, tienePerfil: true },
    { idGrupoUsuario: 'gu-beto', nombre: 'Beto', apellido: 'Ruiz', rol: 'MIEMBRO', estado: 'ACTIVO',
      fechaIncorporacion: '2026-10-03T10:00:00', esVos: false, ...NONE, comparteUltimaMedicion: true, tienePerfil: true },
  ];

  it('un miembro ve qué comparte cada integrante, sin los datos', async () => {
    const { calls } = routes({
      [`GET ${BASE}`]: jsonResponse(200, group('MIEMBRO')),
      [`GET ${BASE}/members`]: jsonResponse(200, MEMBERS),
    });
    renderAt(`/app/grupo/${ID}/integrantes`);
    expect(screen.queryByRole('heading', { name: 'Invitar a una persona' })).not.toBeInTheDocument(); // miembro
    const juan = within(await screen.findByRole('list', { name: 'Qué comparte Juan Pérez' }));
    expect(juan.getByText(/Historial de mediciones/)).toHaveTextContent('Compartido');
    expect(juan.getByText(/Última medición/)).toHaveTextContent('No compartido');
    const pepe = within(screen.getByRole('list', { name: 'Qué comparte Pepe Gómez' }));
    expect(pepe.getAllByText('No compartido')).toHaveLength(4);
    expect(screen.queryByText(/Gráficos y estadísticas/)).not.toBeInTheDocument();
    // Ya no hay «Ver datos compartidos»: el grupo no abre datos de otros integrantes.
    expect(screen.queryByRole('link', { name: /Ver datos compartidos/ })).not.toBeInTheDocument();
    expect(calls.some((call) => call.key.startsWith(`GET ${BASE}/shared`))).toBe(false);
  });
});

describe('Configuración', () => {
  it('el administrador con otros integrantes debe transferir antes de salir', async () => {
    routes({
      [`GET ${BASE}`]: jsonResponse(200, group('ADMINISTRADOR', { cantidadIntegrantes: 2 })),
      [`GET ${BASE}/members`]: jsonResponse(200, [
        { idGrupoUsuario: 'gu-me', nombre: 'Victoria', apellido: 'Cortés', rol: 'ADMINISTRADOR', estado: 'ACTIVO', fechaIncorporacion: '2026-10-01T10:00:00', esVos: true },
        { idGrupoUsuario: 'gu-beto', nombre: 'Beto', apellido: 'Ruiz', usuario: 'beto', correoElectronico: 'beto@example.com', rol: 'MIEMBRO', estado: 'ACTIVO', fechaIncorporacion: '2026-10-02T10:00:00', esVos: false },
      ]),
    });
    renderAt(`/app/grupo/${ID}/configuracion`);
    expect(await screen.findByText('Para salir, primero designá a otro integrante como administrador.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Abandonar grupo' })).not.toBeInTheDocument();
    expect(await screen.findByRole('option', { name: 'Beto Ruiz (beto@example.com)' })).toBeInTheDocument();
  });

  it('al transferir la propiedad, quien deja de administrar ve el aviso con el nombre y correo del nuevo administrador', async () => {
    const me = { idGrupoUsuario: 'gu-me', nombre: 'Victoria', apellido: 'Cortés', rol: 'ADMINISTRADOR', estado: 'ACTIVO', fechaIncorporacion: '2026-10-01T10:00:00', esVos: true };
    const beto = { idGrupoUsuario: 'gu-beto', nombre: 'Beto', apellido: 'Ruiz', usuario: 'beto', correoElectronico: 'beto@example.com', rol: 'MIEMBRO', estado: 'ACTIVO', fechaIncorporacion: '2026-10-02T10:00:00', esVos: false };
    const { calls } = routes({
      // Primera carga como administrador; después de transferir, como miembro.
      [`GET ${BASE}`]: [
        jsonResponse(200, group('ADMINISTRADOR', { cantidadIntegrantes: 2 })),
        jsonResponse(200, group('MIEMBRO', { cantidadIntegrantes: 2 })),
        jsonResponse(200, group('MIEMBRO', { cantidadIntegrantes: 2 })),
      ],
      [`GET ${BASE}/members`]: jsonResponse(200, [me, beto]),
      [`POST ${BASE}/transfer`]: jsonResponse(200, group('MIEMBRO', { cantidadIntegrantes: 2 })),
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${ID}/configuracion`);
    await user.selectOptions(await screen.findByLabelText('Nuevo administrador/a'), 'gu-beto');
    await user.click(screen.getByRole('button', { name: 'Transferir administración' }));
    expect(await screen.findByText('Transferiste la propiedad de «Familia Pérez» a Beto Ruiz (beto@example.com). Ahora sos miembro.')).toBeInTheDocument();
    expect(calls.find((call) => call.key === `POST ${BASE}/transfer`).body).toEqual({ idGrupoUsuario: 'gu-beto' });
    expect(screen.queryByRole('button', { name: 'Transferir administración' })).not.toBeInTheDocument();
  });

  it('eliminar exige escribir el nombre exacto', async () => {
    const { calls } = routes({
      [`GET ${BASE}`]: jsonResponse(200, group('ADMINISTRADOR', { cantidadIntegrantes: 1 })),
      [`GET ${BASE}/members`]: jsonResponse(200, []),
      [`POST ${BASE}/deletion`]: NO_CONTENT,
      'GET /groups/mine': jsonResponse(200, { grupo: null }),
      'GET /groups/invitations': jsonResponse(200, []),
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${ID}/configuracion`);
    await user.click(await screen.findByRole('button', { name: 'Eliminar grupo' }));
    const confirm = screen.getByRole('button', { name: /Eliminar definitivamente/ });
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText(/Escribí «Familia Pérez»/), 'Familia Pérez');
    await user.click(confirm);
    expect(await screen.findByText(/Eliminaste «Familia Pérez»/)).toBeInTheDocument();
    expect(calls.find((call) => call.key === `POST ${BASE}/deletion`).body).toEqual({ confirmacionNombre: 'Familia Pérez' });
    expect(await screen.findByText('Todavía no formás parte de un grupo')).toBeInTheDocument(); // vuelve a crear o unirse
  });

  it('un miembro puede abandonar con confirmación', async () => {
    const { calls } = routes({
      [`GET ${BASE}`]: jsonResponse(200, group('MIEMBRO')),
      [`POST ${BASE}/leave`]: NO_CONTENT,
      'GET /groups/mine': jsonResponse(200, { grupo: null }),
      'GET /groups/invitations': jsonResponse(200, []),
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${ID}/configuracion`);
    await user.click(await screen.findByRole('button', { name: 'Abandonar grupo' }));
    expect(calls.some((call) => call.key === `POST ${BASE}/leave`)).toBe(false);
    await user.click(screen.getByRole('button', { name: /Confirmar salida/ }));
    expect(await screen.findByText(/Saliste de «Familia Pérez»/)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Eliminar grupo' })).not.toBeInTheDocument();
    expect(await screen.findByText('Todavía no formás parte de un grupo')).toBeInTheDocument(); // vuelve a crear o unirse
  });
});


