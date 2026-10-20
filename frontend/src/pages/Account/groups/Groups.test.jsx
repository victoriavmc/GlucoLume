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
    expect(screen.getByRole('link', { name: /Invitaciones/ })).toBeInTheDocument(); // acceso rápido del administrador
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
      expect(resumen.getByText(/integrantes/)).toBeInTheDocument();
      const tabs = within(screen.getByRole('navigation', { name: 'Secciones del grupo' }));
      expect(tabs.getAllByRole('link').map((link) => link.textContent)).toEqual(
        ['Panel', 'Integrantes', 'Mi privacidad', 'Datos compartidos', 'Configuración']); // las invitaciones viven dentro de Integrantes
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
  it('correo inexistente: explica y ofrece el registro individual', async () => {
    routes({
      [`GET ${BASE}`]: jsonResponse(200, group()),
      [`GET ${BASE}/members`]: jsonResponse(200, []),
      [`GET ${BASE}/invitations`]: jsonResponse(200, []),
      [`POST ${BASE}/invitations/lookup`]: jsonResponse(404, {
        codigo: 'USUARIO_NO_ENCONTRADO',
        detail: 'No existe una cuenta individual registrada con este correo. La persona deberá registrarse en GlucoLume antes de incorporarse.',
      }),
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${ID}/integrantes`);
    await user.type(await screen.findByLabelText('Correo electrónico de la cuenta individual'), 'nadie@example.com');
    await user.click(screen.getByRole('button', { name: /Buscar/ }));
    expect(await screen.findByText(/No existe una cuenta individual registrada con este correo/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Registro de cuentas individuales' })).toHaveAttribute('href', '/registro?tipo=usuario');
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

describe('Datos compartidos', () => {
  it('pide solo lo que la persona habilitó: la última medición no trae el historial', async () => {
    const { calls } = routes({
      [`GET ${BASE}`]: jsonResponse(200, group('MIEMBRO')),
      [`GET ${BASE}/shared`]: jsonResponse(200, [{ ...BETO, comparteUltimaMedicion: true }]),
      [`GET ${BASE}/shared/gu-beto/latest`]: jsonResponse(200, { medicion: {
        idMedicion: 'm-1', fechaHoraInicio: '2026-10-08T08:30:00', modoMedicion: 'OXIMETRIA', condicionComida: 'AYUNO',
        glucosaEstimada: null, spo2: '98.00', frecuenciaCardiaca: 70,
      } }),
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${ID}/compartidos`);
    await user.click(await screen.findByRole('button', { name: /Beto Ruiz/ }));
    expect(await screen.findByText('08/10/2026 08:30')).toBeInTheDocument();
    expect(screen.getByText(/SpO₂ 98 %/)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Historial de mediciones' })).not.toBeInTheDocument();
    const shared = calls.filter((call) => call.key.startsWith(`GET ${BASE}/shared/`)).map((call) => call.key);
    expect(shared).toEqual([`GET ${BASE}/shared/gu-beto/latest`]);
  });

  it('una medición de prueba (DEMO) se muestra identificada, con su valor de glucosa', async () => {
    routes({
      [`GET ${BASE}`]: jsonResponse(200, group('MIEMBRO')),
      [`GET ${BASE}/shared`]: jsonResponse(200, [{ ...BETO, comparteUltimaMedicion: true }]),
      [`GET ${BASE}/shared/gu-beto/latest`]: jsonResponse(200, { medicion: {
        idMedicion: 'm-2', fechaHoraInicio: '2026-10-14T18:49:56', modoMedicion: 'GLUCOSA_EXPERIMENTAL', condicionComida: 'AYUNO',
        glucosaEstimada: null, glucosa: '114.00', origenGlucosa: 'DEMO', esDemo: true, spo2: '98.00', frecuenciaCardiaca: 70,
      } }),
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${ID}/compartidos`);
    await user.click(await screen.findByRole('button', { name: /Beto Ruiz/ }));
    expect(await screen.findByText('14/10/2026 18:49')).toBeInTheDocument();
    expect(screen.getByText('DEMO — Medición de prueba')).toBeInTheDocument();
    expect(screen.getByText(/Glucosa DEMO \(simulada\) 114 mg\/dL/)).toBeInTheDocument();
    expect(screen.queryByText(/Todavía no tiene mediciones/)).not.toBeInTheDocument();
  });

  it('solo con el aviso habilitado se ve cuándo midió, sin valores ni otras secciones', async () => {
    const { calls } = routes({
      [`GET ${BASE}`]: jsonResponse(200, group('MIEMBRO')),
      [`GET ${BASE}/shared`]: jsonResponse(200, [{ ...BETO, notificaMedicion: true }]),
      [`GET ${BASE}/shared/gu-beto/notices`]: jsonResponse(200, {
        items: [{ fechaHoraInicio: '2026-10-14T18:35:10' }], total: 1,
      }),
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${ID}/compartidos`);
    await user.click(await screen.findByRole('button', { name: /Beto Ruiz/ }));
    expect(await screen.findByText('Beto Ruiz realizó una medición el 14/10/2026 a las 18:35')).toBeInTheDocument();
    expect(screen.queryByText(/SpO₂|Frecuencia cardíaca|Glucosa/)).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /Última medición|Historial de mediciones|Datos básicos/ })).not.toBeInTheDocument();
    expect(calls.filter((call) => call.key.startsWith(`GET ${BASE}/shared/`)).map((call) => call.key))
      .toEqual([`GET ${BASE}/shared/gu-beto/notices`]);
  });

  it('si la persona no comparte nada, se informa y no se consulta ningún dato', async () => {
    const { calls } = routes({
      [`GET ${BASE}`]: jsonResponse(200, group('MIEMBRO')),
      [`GET ${BASE}/shared`]: jsonResponse(200, [BETO]),
    });
    renderAt(`/app/grupo/${ID}/compartidos`);
    expect(await screen.findByText('No habilitó datos de medición para el grupo.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Beto Ruiz/ })).toBeDisabled();
    expect(calls.some((call) => call.key.startsWith(`GET ${BASE}/shared/`))).toBe(false);
  });

  it('una revocación en el backend cierra la sección y actualiza las tarjetas', async () => {
    routes({
      [`GET ${BASE}`]: jsonResponse(200, group('MIEMBRO')),
      [`GET ${BASE}/shared`]: [jsonResponse(200, [{ ...BETO, comparteHistorial: true }]), jsonResponse(200, [BETO])],
      [`GET ${BASE}/shared/gu-beto/history`]: jsonResponse(403, REVOKED),
      [`GET ${BASE}/shared/gu-beto/statistics`]: jsonResponse(403, REVOKED),
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${ID}/compartidos`);
    await user.click(await screen.findByRole('button', { name: /Beto Ruiz/ }));
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Historial de mediciones' })).not.toBeInTheDocument());
    expect(await screen.findByText('No habilitó datos de medición para el grupo.')).toBeInTheDocument();
  });

  it('compartir el historial muestra la cabecera de la persona, su historial y su evolución', async () => {
    routes({
      [`GET ${BASE}`]: jsonResponse(200, group('MIEMBRO')),
      [`GET ${BASE}/shared`]: jsonResponse(200, [{ ...BETO, comparteHistorial: true }]),
      [`GET ${BASE}/shared/gu-beto/history`]: jsonResponse(200, EMPTY_HISTORY),
      [`GET ${BASE}/shared/gu-beto/statistics`]: jsonResponse(200, STATS),
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${ID}/compartidos`);
    await user.click(await screen.findByRole('button', { name: /Beto Ruiz/ }));
    expect(await screen.findByRole('heading', { name: 'Evolución de Beto Ruiz' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Historial de mediciones' })).toBeInTheDocument();
    // Cabecera de la persona con el estado de sus cuatro permisos (solo el estado, no los datos).
    const perms = within(screen.getByRole('list', { name: 'Qué comparte Beto Ruiz' }));
    expect(perms.getByText('Historial de mediciones').closest('li')).toHaveTextContent('Compartido');
    expect(perms.getByText('Última medición').closest('li')).toHaveTextContent('No compartido');
    expect(screen.queryByRole('heading', { name: 'Gráficos y estadísticas' })).not.toBeInTheDocument();
  });

  it('sin historial no se piden ni se muestran gráficos', async () => {
    const { calls } = routes({
      [`GET ${BASE}`]: jsonResponse(200, group('MIEMBRO')),
      [`GET ${BASE}/shared`]: jsonResponse(200, [{ ...BETO, compartePerfil: true }]),
      [`GET ${BASE}/shared/gu-beto/profile`]: jsonResponse(200, { edad: 40, sexoModelo: 'MASCULINO' }),
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${ID}/compartidos`);
    await user.click(await screen.findByRole('button', { name: /Beto Ruiz/ }));
    expect(await screen.findByText('Masculino')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Gráficos y estadísticas' })).not.toBeInTheDocument();
    expect(calls.some((call) => call.key.endsWith('/statistics') || call.key.endsWith('/history'))).toBe(false);
  });

  it('llegar desde el listado de integrantes preselecciona a la persona', async () => {
    routes({
      [`GET ${BASE}`]: jsonResponse(200, group('MIEMBRO')),
      [`GET ${BASE}/shared`]: jsonResponse(200, [{ ...BETO, comparteHistorial: true }]),
      [`GET ${BASE}/shared/gu-beto/history`]: jsonResponse(200, EMPTY_HISTORY),
      [`GET ${BASE}/shared/gu-beto/statistics`]: jsonResponse(200, STATS),
    });
    renderAt(`/app/grupo/${ID}/compartidos?integrante=gu-beto`);
    expect(await screen.findByRole('heading', { name: 'Datos de Beto Ruiz' })).toBeInTheDocument();
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
    // Solo se ofrece ver datos de quien comparte algo (Beto); no de Pepe ni de uno mismo.
    expect(screen.getAllByRole('link', { name: /Ver datos compartidos/ })).toHaveLength(1);
    expect(screen.getByRole('link', { name: /Ver datos compartidos/ })).toHaveAttribute(
      'href', `/app/grupo/${ID}/integrantes/gu-beto`);
    expect(calls.some((call) => call.key.startsWith(`GET ${BASE}/shared`))).toBe(false);
  });
});

describe('Configuración', () => {
  it('el administrador con otros integrantes debe transferir antes de salir', async () => {
    routes({
      [`GET ${BASE}`]: jsonResponse(200, group('ADMINISTRADOR', { cantidadIntegrantes: 2 })),
      [`GET ${BASE}/members`]: jsonResponse(200, [
        { idGrupoUsuario: 'gu-me', nombre: 'Victoria', apellido: 'Cortés', rol: 'ADMINISTRADOR', estado: 'ACTIVO', fechaIncorporacion: '2026-10-01T10:00:00', esVos: true },
        { idGrupoUsuario: 'gu-beto', nombre: 'Beto', apellido: 'Ruiz', rol: 'MIEMBRO', estado: 'ACTIVO', fechaIncorporacion: '2026-10-02T10:00:00', esVos: false },
      ]),
    });
    renderAt(`/app/grupo/${ID}/configuracion`);
    expect(await screen.findByText('Para salir, primero designá a otro integrante como administrador.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Abandonar grupo' })).not.toBeInTheDocument();
    expect(await screen.findByRole('option', { name: 'Beto Ruiz' })).toBeInTheDocument();
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


describe('Mediciones compartidas: pruebas DEMO y vista ampliada', () => {
  const demo = {
    idMedicion: 'm-demo', fechaHoraInicio: '2026-10-08T08:30:00', modoMedicion: 'GLUCOSA_EXPERIMENTAL', estadoMedicion: 'COMPLETADA',
    condicionComida: 'AYUNO', glucosaEstimada: null, glucosaDispositivo: '114.00', unidadGlucosa: 'mg/dL', origenGlucosa: 'DEMO', esDemo: true,
    spo2: '99.00', frecuenciaCardiaca: 76,
  };
  const real = { ...demo, idMedicion: 'm-real', fechaHoraInicio: '2026-10-07T08:30:00', modoMedicion: 'OXIMETRIA', glucosaDispositivo: null,
    unidadGlucosa: null, origenGlucosa: 'SIN_CALIBRAR', esDemo: false, spo2: '97.00', frecuenciaCardiaca: 70 };

  it('la última medición DEMO se muestra rotulada como prueba, con su origen y un «Ver detalle» autorizado', async () => {
    routes({
      [`GET ${BASE}`]: jsonResponse(200, group('MIEMBRO')),
      [`GET ${BASE}/shared`]: jsonResponse(200, [{ ...BETO, comparteUltimaMedicion: true }]),
      [`GET ${BASE}/shared/gu-beto/latest`]: jsonResponse(200, { medicion: demo }),
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${ID}/compartidos`);
    await user.click(await screen.findByRole('button', { name: /Beto Ruiz/ }));
    expect(await screen.findByText('DEMO — Medición de prueba')).toBeInTheDocument();
    expect(screen.getByText(/Glucosa DEMO \(simulada\) 114 mg\/dL/)).toBeInTheDocument();
    expect(screen.getByText(/Origen: DEMO \(prueba\)/)).toBeInTheDocument();
    expect(screen.getByText(/Glucosa \(experimental\)/)).toBeInTheDocument(); // modo de medición
    expect(screen.getByRole('link', { name: 'Ver detalle' })).toHaveAttribute('href', `/app/grupo/${ID}/compartidos/gu-beto/mediciones/m-demo`);
    expect(screen.queryByRole('heading', { name: 'Historial de mediciones' })).not.toBeInTheDocument(); // «última» no abre el historial
  });

  it('el historial compartido lista reales y pruebas DEMO identificadas', async () => {
    routes({
      [`GET ${BASE}`]: jsonResponse(200, group('MIEMBRO')),
      [`GET ${BASE}/shared`]: jsonResponse(200, [{ ...BETO, comparteHistorial: true }]),
      [`GET ${BASE}/shared/gu-beto/history`]: jsonResponse(200, { items: [demo, real], total: 2, pagina: 1, tamanioPagina: 10 }),
      [`GET ${BASE}/shared/gu-beto/statistics`]: jsonResponse(200, { ...STATS, cantidadMediciones: 1, pruebasDemo: 1, puntosDemo: [] }),
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${ID}/compartidos`);
    await user.click(await screen.findByRole('button', { name: /Beto Ruiz/ }));
    const list = await screen.findByRole('list', { name: 'Historial compartido' });
    const [demoRow, realRow] = within(list).getAllByRole('listitem');
    expect(within(demoRow).getByText('DEMO — Medición de prueba')).toBeInTheDocument();
    expect(within(realRow).queryByText('DEMO — Medición de prueba')).not.toBeInTheDocument();
    expect(realRow).toHaveTextContent('Origen: Sin calibrar');
    expect(within(realRow).getByRole('link', { name: 'Ver detalle' })).toHaveAttribute('href', `/app/grupo/${ID}/compartidos/gu-beto/mediciones/m-real`);
  });

  it('con solo pruebas DEMO no dice que no hay mediciones: las grafica identificadas como DEMO en la evolución', async () => {
    routes({
      [`GET ${BASE}`]: jsonResponse(200, group('MIEMBRO')),
      [`GET ${BASE}/shared`]: jsonResponse(200, [{ ...BETO, comparteHistorial: true }]),
      [`GET ${BASE}/shared/gu-beto/history`]: jsonResponse(200, { items: [demo], total: 1, pagina: 1, tamanioPagina: 10 }),
      [`GET ${BASE}/shared/gu-beto/statistics`]: jsonResponse(200, {
        ...STATS, cantidadMediciones: 0, glucosa: { cantidad: 0, promedio: null, minimo: null, maximo: null },
        spo2: { cantidad: 0, promedio: null, minimo: null, maximo: null }, frecuenciaCardiaca: { cantidad: 0, promedio: null, minimo: null, maximo: null },
        serieDiaria: [], pruebasDemo: 2,
        puntosDemo: [
          { idMedicion: 'a', fecha: '2026-10-07T08:00:00', frecuenciaCardiaca: 72, spo2: 98, glucosa: 111 },
          { idMedicion: 'b', fecha: '2026-10-08T08:30:00', frecuenciaCardiaca: 76, spo2: 99, glucosa: 114 },
        ],
      }),
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${ID}/compartidos`);
    await user.click(await screen.findByRole('button', { name: /Beto Ruiz/ }));
    expect(await screen.findByRole('heading', { name: 'Evolución de Beto Ruiz' })).toBeInTheDocument();
    const legend = within(await screen.findByRole('list', { name: 'Series graficadas' }));
    expect(legend.getByText('Beto Ruiz · DEMO (prueba)')).toBeInTheDocument(); // solo pruebas, identificadas
    expect(legend.queryByText('Beto Ruiz')).not.toBeInTheDocument(); // ninguna serie experimental
    expect(screen.queryByText('No hay mediciones completadas en este período.')).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Pruebas DEMO compartidas' })).not.toBeInTheDocument();
  });

  it('la vista ampliada pide la medición a su endpoint autorizado y rotula la prueba DEMO', async () => {
    const { calls } = routes({
      [`GET ${BASE}`]: jsonResponse(200, group('MIEMBRO')),
      [`GET ${BASE}/shared/gu-beto/measurements/m-demo`]: jsonResponse(200, { ...demo, fechaHoraFin: '2026-10-08T08:31:00', indiceOptico: '2.4149',
        duracionMs: 60000, lecturasEstabilizadas: 8, esUltima: true }),
    });
    renderAt(`/app/grupo/${ID}/compartidos/gu-beto/mediciones/m-demo`);
    expect(await screen.findByRole('heading', { name: /Glucosa \(experimental\) · 08\/10\/2026 08:30/ })).toBeInTheDocument();
    expect(screen.getAllByText(/DEMO — Medición de prueba/).length).toBeGreaterThan(0);
    const results = within(screen.getByLabelText('Resultados compartidos'));
    expect(results.getByText('76 lpm')).toBeInTheDocument();
    expect(results.getByText('114 mg/dL')).toBeInTheDocument();
    expect(calls.map((call) => call.key)).toContain(`GET ${BASE}/shared/gu-beto/measurements/m-demo`);
    expect(screen.getByRole('link', { name: /Volver a los datos compartidos/ })).toHaveAttribute('href', `/app/grupo/${ID}/compartidos?integrante=gu-beto`);
  });

  it('si la persona revocó, la vista ampliada no muestra la medición', async () => {
    routes({
      [`GET ${BASE}`]: jsonResponse(200, group('MIEMBRO')),
      [`GET ${BASE}/shared/gu-beto/measurements/m-demo`]: jsonResponse(403, REVOKED),
    });
    renderAt(`/app/grupo/${ID}/compartidos/gu-beto/mediciones/m-demo`);
    expect(await screen.findByText(/no autorizó compartir esta información/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Resultados compartidos')).not.toBeInTheDocument();
  });
});
