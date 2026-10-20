import { configure, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../../test/helpers.js';
import { renderAt } from '../../../../test/renderApp.jsx';

const INSTITUTIONAL = { ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };
const ID = '9a000000-0000-4000-8000-000000000001';
const BASE = `/institutions/${ID}`;
const PERMISOS = {
  PROPIETARIO: ['CONSULTAR_INSTITUCION', 'MODIFICAR_INSTITUCION', 'GESTIONAR_MODERADORES', 'ADMINISTRAR_OPERADORES',
    'CONSULTAR_EQUIPO', 'ELIMINAR_INSTITUCION', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES', 'BAJA_PACIENTES'],
  OPERADOR: ['CONSULTAR_INSTITUCION', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES'],
};
const NO_STATS = { dias: 30, cantidadMediciones: 0 };
const EMPTY_PAGE = { items: [], total: 0, pagina: 1, tamanioPagina: 10 };

function detail(rol) {
  return {
    idInstitucion: ID, nombre: 'Centro Médico San José', tipoInstitucion: 'CLINICA', estado: 'ACTIVA', rolInstitucion: rol,
    estadoRelacion: 'ACTIVO', permisos: PERMISOS[rol], tipoIdentificadorLegal: 'CUIT', identificadorLegal: '30712345671',
    descripcion: null, fechaCreacion: '2026-10-01T10:00:00', fechaActualizacion: '2026-10-01T10:00:00',
    propietario: { nombre: 'Victoria', apellido: 'Cortés' }, cantidadModeradores: 1, cantidadOperadores: 2, cantidadPacientes: 1,
  };
}

const ANA = { idInstitucionUsuario: 'op-1', nombre: 'Ana', apellido: 'Paz', activo: true };
const BRUNO = { idInstitucionUsuario: 'op-2', nombre: 'Bruno', apellido: 'Ríos', activo: true };

function transfer(overrides = {}) {
  return {
    idTransferenciaPerfil: 't-1', estado: 'PENDIENTE', fechaPeticion: '2026-10-08T09:00:00', fechaTransferencia: null,
    observacion: 'Cambio de turno',
    paciente: { idPerfilMedicion: 'p-1', identificadorPseudonimo: 'PAC-ABC123', edad: 46, sexoModelo: 'MASCULINO' },
    origen: ANA, destino: BRUNO, esRecibida: true, esEnviada: false, puedeAceptar: true, puedeRechazar: true,
    puedeCancelar: false, ...overrides,
  };
}

const list = (items) => jsonResponse(200, { items, total: items.length, pagina: 1, tamanioPagina: 10 });

// Con todos los archivos en paralelo, 1 s por defecto no siempre alcanza para que las pantallas carguen.
configure({ asyncUtilTimeout: 5000 });

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

function routes(rol, extra = {}) {
  return mockApi({
    'GET /auth/me': jsonResponse(200, INSTITUTIONAL),
    [`GET ${BASE}`]: jsonResponse(200, detail(rol)),
    ...extra,
  });
}

describe('Solicitar la transferencia', () => {
  it('el operador responsable elige destinatario, confirma y la solicitud queda pendiente', async () => {
    const { calls } = routes('OPERADOR', {
      [`GET ${BASE}/patients/p-1`]: jsonResponse(200, {
        idPerfilMedicion: 'p-1', identificadorPseudonimo: 'PAC-ABC123', nombre: 'Juan', apellido: 'Pérez', dni: '20111222',
        fechaNacimiento: '1980-01-02', edad: 46, sexoModelo: 'MASCULINO', estado: 'ACTIVO',
        fechaCreacion: '2026-10-03T09:00:00', fechaUltimaMedicion: null, fechaExpiracionDatosPersonales: null,
        responsable: ANA, puedeModificar: true, esMio: true, medicionesAutorizadas: true,
      }),
      [`GET ${BASE}/patients/assignable-operators`]: jsonResponse(200, [ANA, BRUNO]),
      [`GET ${BASE}/patients/p-1/measurements`]: jsonResponse(200, EMPTY_PAGE),
      [`GET ${BASE}/patients/p-1/measurements/evolution`]: jsonResponse(200, { puntos: [], truncado: false, desde: null, hasta: null, estadisticas: { experimental: null, demo: null }, resumen: null }),
      [`POST ${BASE}/patients/p-1/transfers`]: jsonResponse(201, transfer({ esRecibida: false, esEnviada: true, puedeAceptar: false, puedeCancelar: true })),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/pacientes/p-1`);
    const section = (await screen.findByRole('heading', { name: 'Transferir paciente' })).closest('section');
    const select = await within(section).findByLabelText('Operador destinatario');
    // El operador no reasigna directamente: ese apartado es de propietario y moderador.
    expect(screen.queryByRole('heading', { name: 'Operador responsable' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cambiar responsable' })).not.toBeInTheDocument();
    // El responsable actual no figura como destino posible.
    expect(within(select).queryByRole('option', { name: 'Ana Paz' })).not.toBeInTheDocument();
    expect(within(section).getByRole('button', { name: 'Transferir paciente' })).toBeDisabled();
    await user.selectOptions(select, 'op-2');
    await user.type(within(section).getByLabelText('Observación (opcional)'), 'Cambio de turno');
    await user.click(within(section).getByRole('button', { name: 'Transferir paciente' }));
    expect(within(section).getByText(/Pedirle a Bruno Ríos que se haga cargo del paciente/)).toBeInTheDocument();
    expect(calls.some((call) => call.key.startsWith('POST'))).toBe(false); // nada se envía sin confirmar
    await user.click(within(section).getByRole('button', { name: 'Confirmar transferencia' }));
    expect(await within(section).findByText(/Enviamos la solicitud/)).toBeInTheDocument();
    expect(calls.find((call) => call.key === `POST ${BASE}/patients/p-1/transfers`).body).toEqual({
      idOperadorDestino: 'op-2', observacion: 'Cambio de turno',
    });
  });

  it('un moderador o propietario no puede transferir pacientes', async () => {
    routes('PROPIETARIO', {
      [`GET ${BASE}/patients/p-1`]: jsonResponse(200, {
        idPerfilMedicion: 'p-1', identificadorPseudonimo: 'PAC-ABC123', nombre: 'Juan', apellido: 'Pérez', dni: null,
        fechaNacimiento: '1980-01-02', edad: 46, sexoModelo: 'MASCULINO', estado: 'ACTIVO',
        fechaCreacion: '2026-10-03T09:00:00', fechaUltimaMedicion: null, fechaExpiracionDatosPersonales: null,
        responsable: ANA, puedeModificar: true, esMio: false, medicionesAutorizadas: false,
      }),
      [`GET ${BASE}/patients/assignable-operators`]: jsonResponse(200, [ANA, BRUNO]),
    });
    renderAt(`/app/instituciones/${ID}/pacientes/p-1`);
    expect(await screen.findByRole('heading', { name: 'Operador responsable' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Transferir paciente' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Nueva medición/ })).not.toBeInTheDocument();
  });

  it('si ya hay una solicitud pendiente se informa el motivo', async () => {
    routes('OPERADOR', {
      [`GET ${BASE}/patients/p-1`]: jsonResponse(200, {
        idPerfilMedicion: 'p-1', identificadorPseudonimo: 'PAC-ABC123', nombre: 'Juan', apellido: 'Pérez', dni: null,
        fechaNacimiento: '1980-01-02', edad: 46, sexoModelo: 'MASCULINO', estado: 'ACTIVO',
        fechaCreacion: '2026-10-03T09:00:00', fechaUltimaMedicion: null, fechaExpiracionDatosPersonales: null,
        responsable: ANA, puedeModificar: true, esMio: true, medicionesAutorizadas: true,
      }),
      [`GET ${BASE}/patients/assignable-operators`]: jsonResponse(200, [ANA, BRUNO]),
      [`GET ${BASE}/patients/p-1/measurements`]: jsonResponse(200, EMPTY_PAGE),
      [`GET ${BASE}/patients/p-1/measurements/evolution`]: jsonResponse(200, { puntos: [], truncado: false, desde: null, hasta: null, estadisticas: { experimental: null, demo: null }, resumen: null }),
      [`POST ${BASE}/patients/p-1/transfers`]: jsonResponse(409, {
        codigo: 'TRANSFERENCIA_PENDIENTE', detail: 'Este paciente ya tiene una transferencia pendiente de respuesta.',
      }),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/pacientes/p-1`);
    const section = (await screen.findByRole('heading', { name: 'Transferir paciente' })).closest('section');
    await user.selectOptions(await within(section).findByLabelText('Operador destinatario'), 'op-2');
    await user.click(within(section).getByRole('button', { name: 'Transferir paciente' }));
    await user.click(within(section).getByRole('button', { name: 'Confirmar transferencia' }));
    expect(await within(section).findByText(/ya tiene una transferencia pendiente/)).toBeInTheDocument();
  });
});

describe('Transferencias recibidas', () => {
  it('muestra la solicitud sin datos identificatorios y permite aceptarla con confirmación', async () => {
    const { calls } = routes('OPERADOR', {
      [`GET ${BASE}/transfers`]: [
        list([transfer(), transfer({ idTransferenciaPerfil: 't-0', estado: 'RECHAZADA', puedeAceptar: false, puedeRechazar: false })]),
        list([transfer({ estado: 'ACEPTADA', fechaTransferencia: '2026-10-08T10:00:00', puedeAceptar: false, puedeRechazar: false })]),
      ],
      [`POST ${BASE}/transfers/t-1/accept`]: jsonResponse(200, transfer({ estado: 'ACEPTADA' })),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/transferencias`);
    const pending = within(await screen.findByRole('list', { name: 'Transferencias pendientes' }));
    expect(pending.getByText('PAC-ABC123')).toBeInTheDocument();
    expect(pending.getByText(/Operador de origen: Ana Paz → Operador destinatario: Bruno Ríos/)).toBeInTheDocument();
    expect(pending.getByText(/Observación: Cambio de turno/)).toBeInTheDocument();
    expect(screen.queryByText(/Juan|Pérez|20111222/)).not.toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Transferencias respondidas' })).getByText('Rechazada')).toBeInTheDocument();

    await user.click(pending.getByRole('button', { name: /Aceptar transferencia de PAC-ABC123/ }));
    expect(screen.getByText(/pasan a tu cargo/)).toBeInTheDocument();
    expect(calls.some((call) => call.key.startsWith('POST'))).toBe(false);
    await user.click(screen.getByRole('button', { name: 'Confirmar' }));
    expect(await screen.findByText(/el paciente ya está a tu cargo/)).toBeInTheDocument();
    expect(calls.filter((call) => call.key === `GET ${BASE}/transfers`)).toHaveLength(2); // se recarga el listado
    expect(await screen.findByText('Aceptada')).toBeInTheDocument();
  });

  it('rechazar no cambia al responsable', async () => {
    const { calls } = routes('OPERADOR', {
      [`GET ${BASE}/transfers`]: [list([transfer()]), list([transfer({ estado: 'RECHAZADA', puedeAceptar: false, puedeRechazar: false })])],
      [`POST ${BASE}/transfers/t-1/reject`]: jsonResponse(200, transfer({ estado: 'RECHAZADA' })),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/transferencias`);
    await user.click(await screen.findByRole('button', { name: /Rechazar transferencia de PAC-ABC123/ }));
    await user.click(screen.getByRole('button', { name: 'Confirmar' }));
    expect(await screen.findByText(/El paciente sigue con quien lo transfería/)).toBeInTheDocument();
    expect(calls.some((call) => call.key.includes('/accept'))).toBe(false);
  });

  it('una solicitud que perdió vigencia se informa y no deja la pantalla desactualizada', async () => {
    const { calls } = routes('OPERADOR', {
      [`GET ${BASE}/transfers`]: [list([transfer()]), list([transfer({ estado: 'CANCELADA', puedeAceptar: false, puedeRechazar: false })])],
      [`POST ${BASE}/transfers/t-1/accept`]: jsonResponse(409, {
        codigo: 'TRANSFERENCIA_OBSOLETA', detail: 'El paciente ya no está a cargo de quien lo transfería, por lo que la solicitud perdió vigencia.',
      }),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/transferencias`);
    await user.click(await screen.findByRole('button', { name: /Aceptar transferencia de PAC-ABC123/ }));
    await user.click(screen.getByRole('button', { name: 'Confirmar' }));
    expect(await screen.findByText(/perdió vigencia/)).toBeInTheDocument();
    expect(await screen.findByText('Cancelada')).toBeInTheDocument();
    expect(calls.filter((call) => call.key === `GET ${BASE}/transfers`)).toHaveLength(2);
  });
});

describe('Transferencias enviadas e historial', () => {
  it('el solicitante cancela una pendiente', async () => {
    const sent = transfer({ esRecibida: false, esEnviada: true, puedeAceptar: false, puedeRechazar: false, puedeCancelar: true });
    const { calls } = routes('OPERADOR', {
      [`GET ${BASE}/transfers`]: [list([]), list([sent]), list([{ ...sent, estado: 'CANCELADA', puedeCancelar: false }])],
      [`POST ${BASE}/transfers/t-1/cancel`]: jsonResponse(200, { ...sent, estado: 'CANCELADA', puedeCancelar: false }),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/transferencias`);
    await screen.findByText('No hay transferencias en esta sección.');
    await user.click(screen.getByRole('tab', { name: 'Enviadas' }));
    expect(screen.getByRole('tab', { name: 'Enviadas' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel', { name: 'Enviadas' })).toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: /Cancelar transferencia de PAC-ABC123/ }));
    expect(screen.getByText('¿Cancelar la solicitud?')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Confirmar' }));
    expect(await screen.findByText('Cancelaste la solicitud de transferencia.')).toBeInTheDocument();
    expect(calls.some((call) => call.key === `POST ${BASE}/transfers/t-1/cancel`)).toBe(true);
    const sentCall = calls.filter((call) => call.key === `GET ${BASE}/transfers`)[1];
    expect(new URL(sentCall.url).searchParams.get('direccion')).toBe('enviadas');
  });

  it('el propietario ve el historial con operador anterior, nuevo y fechas, sin acciones', async () => {
    routes('PROPIETARIO', {
      [`GET ${BASE}/transfers`]: list([
        transfer({ estado: 'ACEPTADA', fechaTransferencia: '2026-10-08T10:30:00', esRecibida: false, puedeAceptar: false, puedeRechazar: false }),
      ]),
    });
    renderAt(`/app/instituciones/${ID}/transferencias`);
    const history = within(await screen.findByRole('list', { name: 'Historial de transferencias' }));
    expect(history.getByText(/Operador de origen: Ana Paz → Operador destinatario: Bruno Ríos/)).toBeInTheDocument();
    expect(history.getByText(/Solicitada: 08\/10\/2026 09:00 · Efectiva: 08\/10\/2026 10:30/)).toBeInTheDocument();
    expect(history.getByText('Aceptada')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Aceptar|Rechazar|Cancelar/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Recibidas' })).not.toBeInTheDocument(); // solo el historial
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Historial de transferencias' })).toBeInTheDocument());
  });
});
