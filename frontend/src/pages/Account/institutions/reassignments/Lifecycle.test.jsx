import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../../test/helpers.js';
import { renderAt } from '../../../../test/renderApp.jsx';

const INSTITUTIONAL = { ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };
const IN_GRACE = { ...INSTITUTIONAL, periodoGracia: { fechaInicio: '2026-10-01T10:00:00', fechaVencimiento: '2026-10-31T10:00:00', diasRestantes: 12 } };
const ID = '9a000000-0000-4000-8000-000000000001';
const BASE = `/institutions/${ID}`;
const PERMISOS = {
  MODERADOR: ['CONSULTAR_INSTITUCION', 'INCORPORAR_OPERADORES', 'ADMINISTRAR_OPERADORES', 'CONSULTAR_EQUIPO', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES'],
  OPERADOR: ['CONSULTAR_INSTITUCION', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES'],
};
const detail = (rol) => ({
  idInstitucion: ID, nombre: 'Prueba', tipoInstitucion: 'CLINICA', estado: 'ACTIVA', rolInstitucion: rol, estadoRelacion: 'ACTIVO', permisos: PERMISOS[rol],
  tipoIdentificadorLegal: 'CUIT', identificadorLegal: '30712345671', descripcion: null, fechaCreacion: '2026-10-01T10:00:00', fechaActualizacion: '2026-10-01T10:00:00',
  propietario: { nombre: 'Victoria', apellido: 'Cortés' }, cantidadModeradores: 1, cantidadOperadores: 1, cantidadPacientes: 0, cantidadReaperturas: 0, fechaUltimaReapertura: null,
});
const GROUP = {
  idOperadorAnterior: 'op-old', operadorAnterior: 'Laura Díaz', fechaDesvinculacion: '2026-10-10T09:30:00', pendientes: 2, completadas: 0, canceladas: 0, estado: 'PENDIENTE',
};
const OVERVIEW = { pendientes: 2, operadoresDisponibles: 1, grupos: [GROUP] };
const ITEMS = {
  total: 2,
  items: [
    { idReasignacionPaciente: 'r-1', idPerfilMedicion: 'p-1', identificadorPseudonimo: 'PAC-0001', nombre: 'Ana', apellido: 'Paz', idOperadorAnterior: 'op-old', operadorAnterior: 'Laura Díaz', estado: 'PENDIENTE', fechaCreacion: '2026-10-10T09:30:00' },
    { idReasignacionPaciente: 'r-2', idPerfilMedicion: 'p-2', identificadorPseudonimo: 'PAC-0002', nombre: 'Juan', apellido: 'Gil', idOperadorAnterior: 'op-old', operadorAnterior: 'Laura Díaz', estado: 'PENDIENTE', fechaCreacion: '2026-10-10T09:30:00' },
  ],
};

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

function routes(rol, extra = {}, account = INSTITUTIONAL) {
  return mockApi({
    'GET /auth/me': jsonResponse(200, account),
    [`GET ${BASE}`]: jsonResponse(200, detail(rol)),
    [`GET ${BASE}/quota`]: jsonResponse(500, { codigo: 'ERROR_SERVIDOR', detail: 'x' }),
    [`GET ${BASE}/dashboard`]: jsonResponse(500, { codigo: 'ERROR_SERVIDOR', detail: 'x' }),
    [`GET ${BASE}/activity`]: jsonResponse(200, { items: [] }),
    [`GET ${BASE}/operators/me/dashboard`]: jsonResponse(500, { codigo: 'ERROR_SERVIDOR', detail: 'x' }),
    [`GET ${BASE}/patients/assignable-operators`]: jsonResponse(200, [{ idInstitucionUsuario: 'op-new', nombre: 'Marta', apellido: 'Ríos' }]),
    ...extra,
  });
}

describe('Período de gracia de la cuenta', () => {
  it('una cuenta sin instituciones ve el vencimiento, los días restantes y las dos acciones', async () => {
    mockApi({
      'GET /auth/me': jsonResponse(200, IN_GRACE),
      '/institutions/mine': jsonResponse(200, []),
      'GET /institutions/mine': jsonResponse(200, []),
      'GET /institutions/invitations': jsonResponse(200, []),
    });
    renderAt('/app/instituciones');
    const notice = await screen.findByRole('status', { name: 'Período de gracia de la cuenta' });
    expect(within(notice).getByRole('heading', { name: 'Tu cuenta no está vinculada a ninguna institución' })).toBeInTheDocument();
    expect(notice).toHaveTextContent('31/10/2026');
    expect(notice).toHaveTextContent('quedan 12 días');
    expect(notice).toHaveTextContent('crear tu propia institución');
    expect(within(notice).getByRole('link', { name: 'Crear una institución o ver mis invitaciones' })).toHaveAttribute('href', '/app/instituciones');
    expect(within(notice).getByRole('link', { name: 'Eliminar mi cuenta' })).toHaveAttribute('href', '/app/seguridad#seguridad-baja');
  });

  it('sin plazo en curso no se muestra ningún aviso', async () => {
    mockApi({
      'GET /auth/me': jsonResponse(200, INSTITUTIONAL),
      'GET /institutions/mine': jsonResponse(200, []),
      'GET /institutions/invitations': jsonResponse(200, []),
    });
    renderAt('/app/instituciones');
    await screen.findByRole('heading', { name: 'Instituciones' });
    expect(screen.queryByRole('status', { name: 'Período de gracia de la cuenta' })).not.toBeInTheDocument();
  });
});

describe('Eliminar mi cuenta', () => {
  it('con instituciones activas explica el motivo, lleva a gestionar las vinculaciones y no ofrece eliminar', async () => {
    mockApi({
      'GET /auth/me': jsonResponse(200, INSTITUTIONAL),
      'GET /auth/account-deletion/preview': jsonResponse(200, {
        puedeEliminar: false, codigoBloqueo: 'VINCULO_INSTITUCIONAL_ACTIVO',
        mensajeBloqueo: 'Tu cuenta está vinculada a una o más instituciones. Para eliminarla, primero debés finalizar tus vinculaciones institucionales.',
        datosEliminados: [], datosConservados: [], invitacionesPendientes: 0, periodoGracia: null, reautenticacion: '',
      }),
    });
    renderAt('/app/seguridad');
    expect(await screen.findByText(/Tu cuenta está vinculada a una o más instituciones/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Gestionar mis instituciones' })).toHaveAttribute('href', '/app/instituciones');
    expect(screen.queryByRole('button', { name: 'Eliminar cuenta' })).not.toBeInTheDocument();
  });

  it('sin instituciones activas muestra las consecuencias antes de pedir el enlace de confirmación', async () => {
    const { calls } = mockApi({
      'GET /auth/me': jsonResponse(200, IN_GRACE),
      'GET /auth/account-deletion/preview': jsonResponse(200, {
        puedeEliminar: true, codigoBloqueo: null, mensajeBloqueo: null,
        datosEliminados: ['Nombre y apellido', 'Correo electrónico'],
        datosConservados: ['Las relaciones históricas con instituciones (rol, fechas)'],
        invitacionesPendientes: 1, periodoGracia: { fechaInicio: '2026-10-01T10:00:00', fechaVencimiento: '2026-10-31T10:00:00', diasRestantes: 12 },
        reautenticacion: 'x',
      }),
    });
    renderAt('/app/seguridad');
    await userEvent.click(await screen.findByRole('button', { name: 'Eliminar cuenta' }));
    expect(screen.getByText('Nombre y apellido')).toBeInTheDocument();
    expect(screen.getByText(/Las relaciones históricas con instituciones/)).toBeInTheDocument();
    expect(screen.getByText(/Tenés 1 invitación pendiente: se cancelará/)).toBeInTheDocument();
    expect(screen.getByText(/Podés eliminarla ahora sin esperar/)).toBeInTheDocument();
    expect(calls.some((call) => call.key === 'POST /auth/account-deletion/request')).toBe(false); // todavía no se pidió nada
  });
});

describe('Pacientes pendientes de reasignación', () => {
  it('el panel del moderador muestra la cantidad, las bajas y el acceso para gestionar', async () => {
    routes('MODERADOR', { [`GET ${BASE}/reassignments`]: jsonResponse(200, OVERVIEW) });
    renderAt(`/app/instituciones/${ID}`);
    const section = within((await screen.findByRole('heading', { name: 'Pacientes pendientes de reasignación' })).closest('section'));
    expect(section.getByText(/2 pacientes esperan un nuevo operador responsable/)).toBeInTheDocument();
    expect(section.getByText(/1 transferencia pendiente/)).toBeInTheDocument();
    expect(section.getByText('Laura Díaz')).toBeInTheDocument();
    expect(section.getByRole('link', { name: 'Gestionar transferencia' })).toHaveAttribute('href', `/app/instituciones/${ID}/pacientes/reasignaciones`);
  });

  it('sin pendientes el panel no muestra la sección', async () => {
    routes('MODERADOR', { [`GET ${BASE}/reassignments`]: jsonResponse(200, { pendientes: 0, operadoresDisponibles: 1, grupos: [] }) });
    renderAt(`/app/instituciones/${ID}`);
    await screen.findByRole('heading', { name: 'Prueba' });
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Pacientes pendientes de reasignación' })).not.toBeInTheDocument());
  });

  it('el moderador elige el operador, reasigna a varios pacientes juntos y ve el resultado', async () => {
    const { calls } = routes('MODERADOR', {
      [`GET ${BASE}/reassignments`]: [jsonResponse(200, OVERVIEW), jsonResponse(200, { pendientes: 0, operadoresDisponibles: 1, grupos: [{ ...GROUP, pendientes: 0, completadas: 2, estado: 'RESUELTA' }] })],
      [`GET ${BASE}/reassignments/items`]: jsonResponse(200, ITEMS),
      [`POST ${BASE}/reassignments/assign`]: jsonResponse(200, { reasignados: 2, resultados: [
        { idReasignacionPaciente: 'r-1', resultado: 'REASIGNADO' }, { idReasignacionPaciente: 'r-2', resultado: 'REASIGNADO' }] }),
    });
    renderAt(`/app/instituciones/${ID}/pacientes/reasignaciones`);
    expect(await screen.findByRole('link', { name: 'Pendientes de reasignación' })).toHaveAttribute('href', `/app/instituciones/${ID}/pacientes/reasignaciones`);
    expect(await screen.findByText('Laura Díaz')).toBeInTheDocument();
    expect(screen.getByText(/Desvinculado el 10\/10\/2026 09:30/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Gestionar transferencia' }));
    expect(await screen.findByText('Ana Paz')).toBeInTheDocument();
    // Sin elegir destinatario no se puede confirmar: el sistema no elige solo.
    const confirm = screen.getByRole('button', { name: /Confirmar transferencia \(2\)/ });
    expect(confirm).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText('Nuevo operador responsable'), 'op-new');
    fireEvent.change(screen.getByLabelText('Motivo (opcional)'), { target: { value: 'cobertura de licencia' } });
    await userEvent.click(confirm);
    expect(await screen.findByText(/Resultado de la transferencia: 2 reasignados/)).toBeInTheDocument();
    const post = calls.find((call) => call.key === `POST ${BASE}/reassignments/assign`);
    expect(post.body).toEqual({ idsReasignacion: ['r-1', 'r-2'], idOperadorNuevo: 'op-new', observacion: 'cobertura de licencia' });
    expect(await screen.findByText('Reasignación resuelta')).toBeInTheDocument();
  });

  it('la reasignación individual envía solo el paciente seleccionado', async () => {
    const { calls } = routes('MODERADOR', {
      [`GET ${BASE}/reassignments`]: [jsonResponse(200, OVERVIEW), jsonResponse(200, OVERVIEW)],
      [`GET ${BASE}/reassignments/items`]: jsonResponse(200, ITEMS),
      [`POST ${BASE}/reassignments/assign`]: jsonResponse(200, { reasignados: 1, resultados: [{ idReasignacionPaciente: 'r-2', resultado: 'REASIGNADO' }] }),
    });
    renderAt(`/app/instituciones/${ID}/pacientes/reasignaciones`);
    await userEvent.click(await screen.findByRole('button', { name: 'Gestionar transferencia' }));
    await screen.findByText('Ana Paz');
    await userEvent.click(screen.getByRole('checkbox', { name: 'Seleccionar PAC-0001' })); // la saca
    await userEvent.selectOptions(screen.getByLabelText('Nuevo operador responsable'), 'op-new');
    await userEvent.click(screen.getByRole('button', { name: /Confirmar transferencia \(1\)/ }));
    await screen.findByText(/1 reasignados/);
    expect(calls.find((call) => call.key === `POST ${BASE}/reassignments/assign`).body.idsReasignacion).toEqual(['r-2']);
  });

  it('sin operadores activos lo informa y la tarea queda pendiente', async () => {
    routes('MODERADOR', {
      [`GET ${BASE}/patients/assignable-operators`]: jsonResponse(200, []),
      [`GET ${BASE}/reassignments`]: jsonResponse(200, { ...OVERVIEW, operadoresDisponibles: 0 }),
      [`GET ${BASE}/reassignments/items`]: jsonResponse(200, ITEMS),
    });
    renderAt(`/app/instituciones/${ID}/pacientes/reasignaciones`);
    await userEvent.click(await screen.findByRole('button', { name: 'Gestionar transferencia' }));
    expect(await screen.findByText(/No hay operadores activos disponibles/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Confirmar transferencia/ })).toBeDisabled();
  });

  it('el operador no accede a la pantalla de reasignaciones', async () => {
    const { calls } = routes('OPERADOR');
    renderAt(`/app/instituciones/${ID}/pacientes/reasignaciones`);
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Pacientes pendientes de reasignación' })).not.toBeInTheDocument());
    expect(calls.some((call) => call.key.includes('/reassignments'))).toBe(false);
  });
});

describe('Asignaciones por regularizar (operadores desvinculados antes de la reasignación obligatoria)', () => {
  const ORPHANS = {
    pendientes: 0, operadoresDisponibles: 1, grupos: [], sinRegularizar: 3,
    gruposSinRegularizar: [{ idOperadorAnterior: 'op-old', operadorAnterior: 'Laura Díaz', fechaDesvinculacion: '2026-10-10T09:30:00', pacientes: 3 }],
  };

  it('informa cuántos pacientes necesitan responsable y regulariza solo a pedido, sin reasignar nada', async () => {
    const { calls } = routes('MODERADOR', {
      [`GET ${BASE}/reassignments`]: [jsonResponse(200, ORPHANS), jsonResponse(200, { ...OVERVIEW, pendientes: 3, grupos: [{ ...GROUP, pendientes: 3 }], sinRegularizar: 0, gruposSinRegularizar: [] })],
      [`POST ${BASE}/reassignments/regularize`]: jsonResponse(200, { pacientesPendientes: 3 }),
    });
    renderAt(`/app/instituciones/${ID}/pacientes/reasignaciones`);
    const section = within((await screen.findByRole('heading', { name: /Asignaciones por regularizar/ })).closest('section'));
    expect(section.getByText(/3 pacientes necesitan responsable/)).toBeInTheDocument();
    expect(section.getByText(/no se reasigna nada automáticamente/)).toBeInTheDocument();
    expect(calls.some((call) => call.key.includes('/regularize'))).toBe(false); // detectar no modifica nada
    await userEvent.click(section.getByRole('button', { name: 'Regularizar a Laura Díaz' }));
    await waitFor(() => expect(calls.find((call) => call.key === `POST ${BASE}/reassignments/regularize`).body).toEqual({ idOperadorAnterior: 'op-old' }));
    expect(await screen.findByText(/3 pacientes quedaron pendientes de reasignación/)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /Asignaciones por regularizar/ })).not.toBeInTheDocument();
    expect(calls.some((call) => call.key.includes('/reassignments/assign'))).toBe(false);
  });
});
