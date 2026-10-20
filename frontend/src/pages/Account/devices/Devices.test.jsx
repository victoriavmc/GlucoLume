import { configure, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../test/helpers.js';
import { renderAt } from '../../../test/renderApp.jsx';

// Con todos los archivos en paralelo, 1 s por defecto no siempre alcanza para que las pantallas carguen.
configure({ asyncUtilTimeout: 5000 });

const account = (tipoCuenta) => ({ ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta } });
const ADMIN = account('ADMINISTRADOR_PLATAFORMA');
const PLATFORM_MODERATOR = account('MODERADOR_PLATAFORMA');
const INSTITUTIONAL = account('USUARIO_INSTITUCIONAL');
const ID = '9a000000-0000-4000-8000-000000000001';
const BASE = `/institutions/${ID}/devices`;
const DID = 'd-1';
const BASE_PERMISOS = ['CONSULTAR_INSTITUCION', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES', 'CONSULTAR_DISPOSITIVOS'];
const PERMISOS = {
  PROPIETARIO: [...BASE_PERMISOS, 'GESTIONAR_DISPOSITIVOS', 'RETIRAR_DISPOSITIVOS', 'CONSULTAR_EQUIPO'],
  MODERADOR: [...BASE_PERMISOS, 'GESTIONAR_DISPOSITIVOS', 'CONSULTAR_EQUIPO'],
  OPERADOR: BASE_PERMISOS,
};

function institution(rol) {
  return {
    idInstitucion: ID, nombre: 'Centro Médico San José', tipoInstitucion: 'CLINICA', estado: 'ACTIVA', rolInstitucion: rol,
    estadoRelacion: 'ACTIVO', permisos: PERMISOS[rol], tipoIdentificadorLegal: 'CUIT', identificadorLegal: '30712345671',
    descripcion: null, fechaCreacion: '2026-10-01T10:00:00', fechaActualizacion: '2026-10-01T10:00:00',
    propietario: { nombre: 'Victoria', apellido: 'Cortés' }, cantidadModeradores: 1, cantidadOperadores: 1, cantidadPacientes: 0,
  };
}

const PERSON = { idInstitucionUsuario: 'r-1', nombre: 'Ana', apellido: 'Paz', activo: true };

function item(overrides = {}) {
  return {
    idDispositivo: DID, codigoDispositivo: 'GL-0001', nombre: 'Prototipo 1', modelo: 'UNO + HC-06', modeloSensor: 'MAX30102',
    versionFirmware: '1.0.0', estado: 'OPERATIVO', idInstitucionAsignada: null, nombreInstitucion: null, responsable: null,
    fechaRegistro: '2026-10-01T10:00:00', fechaAsignacionInstitucional: null, disponibleParaMedir: true, esMio: false, ...overrides,
  };
}

function detail(overrides = {}, permisos = {}) {
  return {
    ...item(), medicionesRegistradas: 2,
    permisos: { puedeEditar: true, puedeCambiarEstado: true, puedeAsignarInstitucion: true, puedeCambiarResponsable: false,
      puedeDesvincular: false, puedeDescomisionar: true, puedeVerMediciones: true, ...permisos },
    ...overrides,
  };
}

const COUNTS = {
  total: 7, operativos: 4, enMantenimiento: 1, fueraDeServicio: 1, descomisionados: 1, asignados: 2, sinAsignar: 5, conectividadDisponible: false,
};
const page = (items) => jsonResponse(200, { items, total: items.length, pagina: 1, tamanioPagina: 10 });
const EMPTY_PAGE = { items: [], total: 0, pagina: 1, tamanioPagina: 10 };

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

function routes(me, extra = {}) {
  return mockApi({ 'GET /auth/me': jsonResponse(200, me), ...extra });
}

describe('Inventario global (plataforma)', () => {
  it('muestra indicadores reales, el listado y no afirma conectividad', async () => {
    routes(ADMIN, {
      'GET /devices': page([
        item(), item({ idDispositivo: 'd-2', codigoDispositivo: 'GL-0002', modeloSensor: 'MAX30100', estado: 'EN_MANTENIMIENTO', disponibleParaMedir: false,
          idInstitucionAsignada: ID, nombreInstitucion: 'Centro Médico San José', responsable: PERSON, fechaAsignacionInstitucional: '2026-10-02T10:00:00' }),
        item({ idDispositivo: 'd-3', codigoDispositivo: 'GL-0003', estado: 'BAJA', disponibleParaMedir: false }),
      ]),
      'GET /devices/summary': jsonResponse(200, COUNTS),
    });
    renderAt('/app/dispositivos');
    expect(await screen.findByRole('heading', { name: 'Inventario de dispositivos', level: 1 })).toBeInTheDocument();
    const cards = within(await screen.findByRole('list', { name: 'Indicadores del inventario' }));
    for (const [label, value] of [['Total de dispositivos', '7'], ['Operativos', '4'], ['En mantenimiento', '1'], ['Fuera de servicio', '1'],
      ['Descomisionados', '1'], ['Asignados', '2'], ['Sin asignar', '5']]) {
      expect(cards.getByText(label).closest('li')).toHaveTextContent(value);
    }
    expect(screen.getByText(/no que esté conectado/)).toBeInTheDocument();
    expect(screen.queryByText(/Conectados|Desconectados/)).not.toBeInTheDocument();
    const table = within(await screen.findByRole('table', { name: 'Dispositivos' }));
    expect(table.getByText('GL-0002').closest('tr')).toHaveTextContent('Centro Médico San José');
    expect(table.getByText('GL-0002').closest('tr')).toHaveTextContent('Ana Paz');
    expect(table.getByText('GL-0002').closest('tr')).toHaveTextContent('En mantenimiento');
    expect(table.getByText('GL-0003').closest('tr')).toHaveTextContent('Descomisionado');
    expect(table.getByText('GL-0001').closest('tr')).toHaveTextContent('Sin asignar');
    expect(table.getByRole('link', { name: 'Ver detalle de GL-0001' })).toHaveAttribute('href', `/app/dispositivos/${DID}`);
  });

  it('el menú de plataforma ofrece Dispositivos y el resto de las cuentas no entra', async () => {
    routes(PLATFORM_MODERATOR, { 'GET /devices': page([]), 'GET /devices/summary': jsonResponse(200, COUNTS) });
    renderAt('/app/dispositivos');
    const nav = await screen.findByRole('navigation', { name: 'Secciones de la cuenta' });
    expect(within(nav).getByRole('link', { name: 'Dispositivos' })).toHaveAttribute('href', '/app/dispositivos');
    clearTokens();
    saveTokens(TOKENS, false);
    const { calls } = routes(ACCOUNT, { 'GET /groups/mine': jsonResponse(200, { grupo: null }), 'GET /groups/invitations': jsonResponse(200, []) });
    renderAt('/app/dispositivos');
    await screen.findAllByRole('navigation', { name: 'Secciones de la cuenta' });
    expect(calls.some((call) => call.key.startsWith('GET /devices'))).toBe(false);
  });

  it('registra un dispositivo con sensor MAX30100 o MAX30102 y refresca el listado', async () => {
    const { calls } = routes(ADMIN, {
      'GET /devices': [page([]), page([item({ modeloSensor: 'MAX30100' })])],
      'GET /devices/summary': jsonResponse(200, COUNTS),
      'GET /devices/institutions': jsonResponse(200, [{ idInstitucion: ID, nombre: 'Centro Médico San José' }]),
      'POST /devices': jsonResponse(201, detail({ modeloSensor: 'MAX30100' })),
    });
    const user = userEvent.setup();
    renderAt('/app/dispositivos');
    await user.click(await screen.findByRole('button', { name: /Registrar dispositivo/ }));
    const form = screen.getByRole('form', { name: /Registrar dispositivo/ }) ?? screen.getByRole('heading', { name: 'Registrar dispositivo' }).closest('form');
    const sensor = within(form).getByLabelText('Modelo del sensor');
    expect(within(sensor).getAllByRole('option').map((o) => o.textContent)).toEqual(['MAX30100', 'MAX30102']);
    expect(within(within(form).getByLabelText('Estado')).getAllByRole('option').map((o) => o.textContent))
      .toEqual(['Operativo', 'En mantenimiento', 'Fuera de servicio']); // el retiro no es un estado de alta
    await user.click(within(form).getByRole('button', { name: /Registrar dispositivo/ }));
    expect(within(form).getByText(/Ingresá el código único/)).toBeInTheDocument();
    expect(calls.some((call) => call.key === 'POST /devices')).toBe(false);
    await user.type(within(form).getByLabelText('Código único del dispositivo'), 'GL-0001');
    await user.type(within(form).getByLabelText('Nombre descriptivo'), 'Prototipo 1');
    await user.selectOptions(sensor, 'MAX30100');
    await user.type(within(form).getByLabelText('Versión de firmware'), '1.0.0');
    await user.click(within(form).getByRole('button', { name: /Registrar dispositivo/ }));
    expect(await screen.findByText('Registramos el dispositivo GL-0001.')).toBeInTheDocument();
    expect(calls.find((call) => call.key === 'POST /devices').body).toEqual({
      codigoDispositivo: 'GL-0001', nombre: 'Prototipo 1', modeloSensor: 'MAX30100', versionFirmware: '1.0.0', estado: 'OPERATIVO',
    });
    expect(await within(await screen.findByRole('table', { name: 'Dispositivos' })).findByText('GL-0001')).toBeInTheDocument();
  });

  it('un código duplicado se informa en el campo y no se pierde lo cargado', async () => {
    routes(ADMIN, {
      'GET /devices': page([]), 'GET /devices/summary': jsonResponse(200, COUNTS),
      'GET /devices/institutions': jsonResponse(200, []),
      'POST /devices': jsonResponse(409, { codigo: 'DISPOSITIVO_DUPLICADO', detail: 'Ya hay un dispositivo registrado con ese código.' }),
    });
    const user = userEvent.setup();
    renderAt('/app/dispositivos');
    await user.click(await screen.findByRole('button', { name: /Registrar dispositivo/ }));
    const form = screen.getByRole('heading', { name: 'Registrar dispositivo', level: 2 }).closest('form');
    await user.type(within(form).getByLabelText('Código único del dispositivo'), 'GL-0001');
    await user.click(within(form).getByRole('button', { name: /Registrar dispositivo/ }));
    expect(await within(form).findByText('Ya hay un dispositivo registrado con ese código.')).toBeInTheDocument();
    expect(within(form).getByLabelText('Código único del dispositivo')).toHaveValue('GL-0001');
  });

  it('el administrador asigna una institución en el alta; la moderación no ve ese campo', async () => {
    routes(ADMIN, {
      'GET /devices': page([]), 'GET /devices/summary': jsonResponse(200, COUNTS),
      'GET /devices/institutions': jsonResponse(200, [{ idInstitucion: ID, nombre: 'Centro Médico San José' }]),
      [`GET /devices/institutions/${ID}/responsibles`]: jsonResponse(200, [PERSON]),
    });
    const user = userEvent.setup();
    renderAt('/app/dispositivos');
    await user.click(await screen.findByRole('button', { name: /Registrar dispositivo/ }));
    const form = screen.getByRole('heading', { name: 'Registrar dispositivo', level: 2 }).closest('form');
    expect(within(form).queryByLabelText('Responsable (opcional)')).not.toBeInTheDocument();
    await user.selectOptions(await within(form).findByLabelText('Institución asignada (opcional)'), ID);
    expect(await within(form).findByRole('option', { name: 'Ana Paz' })).toBeInTheDocument();
  });

  it('los filtros y la búsqueda se envían al backend', async () => {
    const { calls } = routes(ADMIN, { 'GET /devices': () => page([]), 'GET /devices/summary': jsonResponse(200, COUNTS) });
    const user = userEvent.setup();
    renderAt('/app/dispositivos');
    await screen.findByText('Todavía no hay dispositivos en el inventario.');
    await user.type(screen.getByLabelText('Buscar'), 'GL-00');
    await user.selectOptions(screen.getByLabelText('Estado'), 'BAJA');
    await user.selectOptions(screen.getByLabelText('Asignación'), 'false');
    await waitFor(() => {
      const last = new URL(calls.filter((call) => call.key === 'GET /devices').at(-1).url);
      expect(Object.fromEntries(last.searchParams)).toEqual({ busqueda: 'GL-00', estado: 'BAJA', asignado: 'false', pagina: '1', tamanioPagina: '10' });
    }, { timeout: 5000 });
    expect(await screen.findByText('No hay dispositivos que coincidan con los filtros.')).toBeInTheDocument();
  });
});

describe('Detalle y acciones (global)', () => {
  const open = (extra = {}, me = ADMIN) => routes(me, extra);

  it('muestra todos los datos, el estado operativo y que la conexión no se verifica', async () => {
    open({
      [`GET /devices/${DID}`]: jsonResponse(200, detail({ idInstitucionAsignada: ID, nombreInstitucion: 'Centro Médico San José', responsable: PERSON,
        fechaAsignacionInstitucional: '2026-10-02T10:00:00' }, { puedeCambiarResponsable: true, puedeDesvincular: true })),
      [`GET /devices/${DID}/measurements`]: jsonResponse(200, EMPTY_PAGE),
      'GET /devices/institutions': jsonResponse(200, []),
      [`GET /devices/institutions/${ID}/responsibles`]: jsonResponse(200, [PERSON]),
    });
    renderAt(`/app/dispositivos/${DID}`);
    const data = within(await screen.findByRole('heading', { name: 'Prototipo 1', level: 1 }).then((h) => h.closest('section'))); // sin layout institucional: el título es el h1
    expect(data.getByText(DID)).toBeInTheDocument();
    expect(data.getByText('GL-0001')).toBeInTheDocument();
    expect(data.getByText('MAX30102')).toBeInTheDocument();
    expect(data.getByText('Centro Médico San José')).toBeInTheDocument();
    expect(data.getByText('Ana Paz')).toBeInTheDocument();
    expect(data.getByText(/No informado: el inventario no verifica la conexión/)).toBeInTheDocument();
    expect(data.getByText('Disponible para medir', { exact: false })).toBeInTheDocument();
    expect(await screen.findByText('Todavía no hay mediciones con este dispositivo.')).toBeInTheDocument();
  });

  it('modifica los datos con los valores precargados y confirma el guardado', async () => {
    const edited = detail({ nombre: 'Prototipo 1B', versionFirmware: '1.1.0' });
    const { calls } = open({
      [`GET /devices/${DID}`]: [jsonResponse(200, detail()), jsonResponse(200, edited)],
      [`PATCH /devices/${DID}`]: jsonResponse(200, edited),
      [`GET /devices/${DID}/measurements`]: jsonResponse(200, EMPTY_PAGE),
      'GET /devices/institutions': jsonResponse(200, []),
    });
    const user = userEvent.setup();
    renderAt(`/app/dispositivos/${DID}`);
    await user.click(await screen.findByRole('button', { name: /Modificar/ }));
    const form = screen.getByRole('heading', { name: 'Modificar dispositivo' }).closest('form');
    expect(within(form).getByLabelText('Nombre descriptivo')).toHaveValue('Prototipo 1');
    expect(within(form).getByLabelText('Versión de firmware')).toHaveValue('1.0.0');
    expect(within(form).queryByLabelText('Código único del dispositivo')).not.toBeInTheDocument(); // el código no cambia
    await user.clear(within(form).getByLabelText('Nombre descriptivo'));
    await user.type(within(form).getByLabelText('Nombre descriptivo'), 'Prototipo 1B');
    await user.clear(within(form).getByLabelText('Versión de firmware'));
    await user.type(within(form).getByLabelText('Versión de firmware'), '1.1.0');
    await user.click(within(form).getByRole('button', { name: 'Guardar cambios' }));
    expect(await screen.findByText('Guardamos los cambios del dispositivo.')).toBeInTheDocument();
    expect(calls.find((call) => call.key.startsWith('PATCH')).body).toEqual({
      nombre: 'Prototipo 1B', modelo: 'UNO + HC-06', modeloSensor: 'MAX30102', versionFirmware: '1.1.0',
    });
    expect(await screen.findByRole('heading', { name: 'Prototipo 1B' })).toBeInTheDocument();
  });

  it('cambia el estado a mantenimiento y se refleja como no disponible', async () => {
    const maintenance = detail({ estado: 'EN_MANTENIMIENTO', disponibleParaMedir: false });
    const { calls } = open({
      [`GET /devices/${DID}`]: jsonResponse(200, detail()),
      [`POST /devices/${DID}/state`]: jsonResponse(200, maintenance),
      [`GET /devices/${DID}/measurements`]: jsonResponse(200, EMPTY_PAGE),
      'GET /devices/institutions': jsonResponse(200, []),
    });
    const user = userEvent.setup();
    renderAt(`/app/dispositivos/${DID}`);
    const section = (await screen.findByRole('heading', { name: 'Cambiar estado' })).closest('section');
    expect(within(section).getByRole('button', { name: 'Cambiar estado' })).toBeDisabled();
    await user.selectOptions(within(section).getByLabelText('Nuevo estado'), 'EN_MANTENIMIENTO');
    await user.type(within(section).getByLabelText('Motivo (opcional)'), 'Limpieza');
    await user.click(within(section).getByRole('button', { name: 'Cambiar estado' }));
    expect(await screen.findByText('El dispositivo quedó en mantenimiento.')).toBeInTheDocument();
    expect(calls.find((call) => call.key.endsWith('/state')).body).toEqual({ estado: 'EN_MANTENIMIENTO', motivo: 'Limpieza' });
    expect(screen.getByText('No disponible para nuevas mediciones', { exact: false })).toBeInTheDocument();
  });

  it('el administrador asigna una institución con un responsable de esa institución', async () => {
    const assigned = detail({ idInstitucionAsignada: ID, nombreInstitucion: 'Centro Médico San José', responsable: PERSON });
    const { calls } = open({
      [`GET /devices/${DID}`]: [jsonResponse(200, detail()), jsonResponse(200, assigned)],
      [`GET /devices/${DID}/measurements`]: jsonResponse(200, EMPTY_PAGE),
      'GET /devices/institutions': jsonResponse(200, [{ idInstitucion: ID, nombre: 'Centro Médico San José' }]),
      [`GET /devices/institutions/${ID}/responsibles`]: jsonResponse(200, [PERSON]),
      [`POST /devices/${DID}/assign`]: jsonResponse(200, assigned),
    });
    const user = userEvent.setup();
    renderAt(`/app/dispositivos/${DID}`);
    const section = (await screen.findByRole('heading', { name: 'Asignar a una institución' })).closest('section');
    expect(within(section).getByRole('button', { name: 'Asignar dispositivo' })).toBeDisabled();
    await user.selectOptions(await within(section).findByLabelText('Institución'), ID);
    await user.selectOptions(await within(section).findByLabelText('Responsable (opcional)'), 'r-1');
    await user.click(within(section).getByRole('button', { name: 'Asignar dispositivo' }));
    expect(await screen.findByText('Asignamos el dispositivo.')).toBeInTheDocument();
    expect(calls.find((call) => call.key.endsWith('/assign')).body).toEqual({ idInstitucion: ID, idInstitucionUsuarioResponsable: 'r-1' });
  });

  it('descomisiona con confirmación y el dispositivo queda sin acciones', async () => {
    const retired = detail({ estado: 'BAJA', disponibleParaMedir: false }, {
      puedeEditar: false, puedeCambiarEstado: false, puedeAsignarInstitucion: false, puedeDescomisionar: false,
    });
    const { calls } = open({
      [`GET /devices/${DID}`]: jsonResponse(200, detail()),
      [`POST /devices/${DID}/decommission`]: jsonResponse(200, retired),
      [`GET /devices/${DID}/measurements`]: jsonResponse(200, EMPTY_PAGE),
      'GET /devices/institutions': jsonResponse(200, []),
    });
    const user = userEvent.setup();
    renderAt(`/app/dispositivos/${DID}`);
    await user.click(await screen.findByRole('button', { name: /Descomisionar/ }));
    expect(screen.getByText(/Descomisionar definitivamente/)).toBeInTheDocument();
    expect(calls.some((call) => call.key.endsWith('/decommission'))).toBe(false);
    await user.click(screen.getByRole('button', { name: 'Confirmar' }));
    expect(await screen.findByText('El dispositivo quedó descomisionado.')).toBeInTheDocument();
    expect(screen.getAllByText('Descomisionado').length).toBeGreaterThan(0);
    expect(screen.getByText(/ya no admite cambios ni mediciones nuevas/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Modificar|Descomisionar|Desvincular/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Cambiar estado' })).not.toBeInTheDocument();
  });

  it('un rechazo del backend (mediciones en curso) se muestra y el detalle se refresca', async () => {
    open({
      [`GET /devices/${DID}`]: jsonResponse(200, detail()),
      [`POST /devices/${DID}/decommission`]: jsonResponse(409, { codigo: 'DISPOSITIVO_EN_USO', detail: 'El dispositivo tiene mediciones en curso: finalizalas o cancelalas antes de continuar.' }),
      [`GET /devices/${DID}/measurements`]: jsonResponse(200, EMPTY_PAGE),
      'GET /devices/institutions': jsonResponse(200, []),
    });
    const user = userEvent.setup();
    renderAt(`/app/dispositivos/${DID}`);
    await user.click(await screen.findByRole('button', { name: /Descomisionar/ }));
    await user.click(screen.getByRole('button', { name: 'Confirmar' }));
    expect(await screen.findByText(/mediciones en curso/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Descomisionar/ })).toBeInTheDocument();
  });

  it('las mediciones relacionadas muestran el firmware de cada momento y ningún dato del paciente', async () => {
    open({
      [`GET /devices/${DID}`]: jsonResponse(200, detail({ versionFirmware: '1.1.0' })),
      [`GET /devices/${DID}/measurements`]: jsonResponse(200, {
        items: [{ idMedicion: 'm-1', fechaHoraInicio: '2026-10-05T10:00:00', modoMedicion: 'OXIMETRIA', estadoMedicion: 'COMPLETADA',
          versionFirmwareAlMomento: '1.0.0', modeloSensorAlMomento: 'MAX30100', nombreInstitucion: 'Centro Médico San José' }],
        total: 1, pagina: 1, tamanioPagina: 10,
      }),
      'GET /devices/institutions': jsonResponse(200, []),
    });
    renderAt(`/app/dispositivos/${DID}`);
    const row = within(await screen.findByRole('list', { name: 'Mediciones del dispositivo' })).getByRole('listitem');
    expect(row).toHaveTextContent('firmware 1.0.0'); // el actual es 1.1.0: la medición conserva el de ese momento
    expect(row).toHaveTextContent('MAX30100');
    expect(row).toHaveTextContent('Centro Médico San José');
    expect(row).toHaveTextContent('Completada');
  });
});

describe('Inventario institucional', () => {
  const inst = (rol, extra = {}) => routes(INSTITUTIONAL, { [`GET /institutions/${ID}`]: jsonResponse(200, institution(rol)), ...extra });

  it('la sección Dispositivos es de propietario y moderador: el operador no la ve ni la abre por la URL', async () => {
    const { calls } = inst('OPERADOR', { [`GET ${BASE}`]: page([]), [`GET ${BASE}/summary`]: jsonResponse(200, COUNTS) });
    renderAt(`/app/instituciones/${ID}/dispositivos`);
    const nav = await screen.findByRole('navigation', { name: 'Secciones de la institución' });
    expect(within(nav).queryByRole('link', { name: 'Dispositivos' })).not.toBeInTheDocument();
    expect(screen.queryByRole('table', { name: 'Dispositivos' })).not.toBeInTheDocument();
    expect(calls.some((call) => call.key === `GET ${BASE}`)).toBe(false); // no consulta el inventario
  });

  it('el propietario registra dentro de su institución y no elige responsable: se asigna a su propietario', async () => {
    const { calls } = inst('PROPIETARIO', {
      [`GET ${BASE}`]: [page([]), page([item({ idInstitucionAsignada: ID, responsable: PERSON })])],
      [`GET ${BASE}/summary`]: jsonResponse(200, COUNTS),
      [`POST ${BASE}`]: jsonResponse(201, detail({ idInstitucionAsignada: ID, responsable: PERSON })),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/dispositivos`);
    await user.click(await screen.findByRole('button', { name: /Registrar dispositivo/ }));
    const form = screen.getByRole('heading', { name: 'Registrar dispositivo', level: 2 }).closest('form');
    expect(within(form).queryByLabelText('Institución asignada (opcional)')).not.toBeInTheDocument(); // siempre la propia
    expect(within(form).queryByLabelText(/Responsable/)).not.toBeInTheDocument(); // no hay selector de responsable
    expect(within(form).getByText(/Se asigna automáticamente al propietario\/a de la institución/)).toBeInTheDocument();
    await user.type(within(form).getByLabelText('Código único del dispositivo'), 'GL-0001');
    await user.click(within(form).getByRole('button', { name: /Registrar dispositivo/ }));
    expect(await screen.findByText('Registramos el dispositivo GL-0001.')).toBeInTheDocument();
    const body = calls.find((call) => call.key === `POST ${BASE}`).body;
    expect(body).toMatchObject({ codigoDispositivo: 'GL-0001' });
    expect(body.idInstitucionAsignada).toBeUndefined();
    expect(body.idInstitucionUsuarioResponsable).toBeUndefined();
    expect(calls.some((call) => call.key === `GET ${BASE}/responsibles`)).toBe(false);
    const row = within(await screen.findByRole('table', { name: 'Dispositivos' })).getByText('GL-0001').closest('tr');
    expect(row).toHaveTextContent('Ana Paz');
    expect(row).toHaveTextContent('Centro Médico San José');
  });

  it('muestra cinco indicadores reales y el aviso sobre la asignación y el significado de operativo', async () => {
    inst('PROPIETARIO', {
      [`GET ${BASE}`]: page([item({ idInstitucionAsignada: ID, responsable: PERSON })]),
      [`GET ${BASE}/summary`]: jsonResponse(200, { ...COUNTS, total: 5, operativos: 3, enMantenimiento: 1, fueraDeServicio: 1, descomisionados: 0 }),
    });
    renderAt(`/app/instituciones/${ID}/dispositivos`);
    const cards = within(await screen.findByRole('list', { name: 'Indicadores del inventario' }));
    expect(cards.getAllByRole('listitem')).toHaveLength(5); // sin «Asignados» ni «Sin asignar» (eso es del inventario global)
    for (const [label, value] of [['Total de dispositivos', '5'], ['Operativos', '3'], ['En mantenimiento', '1'], ['Fuera de servicio', '1'], ['Descomisionados', '0']]) {
      expect(cards.getByText(label).closest('li')).toHaveTextContent(value);
    }
    const note = screen.getByRole('note');
    expect(note).toHaveTextContent('quedan a cargo del propietario/a de la institución');
    expect(note).toHaveTextContent('habilitado administrativamente');
    expect(note).toHaveTextContent('no necesariamente conectado en tiempo real');
  });

  it('sin dispositivos muestra el estado vacío con la acción de registrar, sin tabla', async () => {
    inst('PROPIETARIO', { [`GET ${BASE}`]: page([]), [`GET ${BASE}/summary`]: jsonResponse(200, { ...COUNTS, total: 0, operativos: 0, enMantenimiento: 0, fueraDeServicio: 0, descomisionados: 0 }) });
    renderAt(`/app/instituciones/${ID}/dispositivos`);
    expect(await screen.findByText('Todavía no hay dispositivos en el inventario.')).toBeInTheDocument();
    expect(screen.getByText(/Registrá el primer dispositivo para comenzar a gestionar el inventario de esta institución/)).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: 'Dispositivos' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Registrar dispositivo/ }).length).toBeGreaterThan(0);
  });

  it('el buscador y el filtro por estado se envían al backend', async () => {
    const { calls } = inst('PROPIETARIO', {
      [`GET ${BASE}`]: page([item({ idInstitucionAsignada: ID })]), [`GET ${BASE}/summary`]: jsonResponse(200, COUNTS),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/dispositivos`);
    await user.type(await screen.findByLabelText('Buscar'), 'gl-1');
    await user.selectOptions(screen.getByLabelText('Estado'), 'EN_MANTENIMIENTO');
    await waitFor(() => expect(calls.some((call) => call.url.includes('busqueda=gl-1') && call.url.includes('estado=EN_MANTENIMIENTO'))).toBe(true));
  });

  it('cambia el estado desde la lista con confirmación y actualiza lo que se ve', async () => {
    const { calls } = inst('PROPIETARIO', {
      [`GET ${BASE}`]: [page([item({ idInstitucionAsignada: ID })]), page([item({ idInstitucionAsignada: ID, estado: 'EN_MANTENIMIENTO', disponibleParaMedir: false })])],
      [`GET ${BASE}/summary`]: jsonResponse(200, COUNTS),
      [`POST ${BASE}/${DID}/state`]: jsonResponse(200, detail({ estado: 'EN_MANTENIMIENTO' })),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/dispositivos`);
    await user.click(await screen.findByRole('button', { name: 'Cambiar estado de GL-0001' }));
    const dialog = within(screen.getByRole('alertdialog', { name: 'Cambiar estado de GL-0001' }));
    expect(dialog.getByText(/no puede iniciar ni continuar mediciones/)).toBeInTheDocument();
    expect(within(dialog.getByLabelText('Nuevo estado')).getAllByRole('option').map((o) => o.textContent))
      .toEqual(['Operativo', 'En mantenimiento', 'Fuera de servicio']); // el retiro definitivo no se ofrece acá
    await user.selectOptions(dialog.getByLabelText('Nuevo estado'), 'EN_MANTENIMIENTO');
    await user.type(dialog.getByLabelText('Motivo (opcional)'), 'revisión');
    expect(calls.some((call) => call.key === `POST ${BASE}/${DID}/state`)).toBe(false); // nada se guarda sin confirmar
    await user.click(dialog.getByRole('button', { name: /Confirmar cambio/ }));
    expect(await screen.findByText('El dispositivo GL-0001 quedó en mantenimiento.')).toBeInTheDocument();
    expect(calls.find((call) => call.key === `POST ${BASE}/${DID}/state`).body).toEqual({ estado: 'EN_MANTENIMIENTO', motivo: 'revisión' });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(await within(screen.getByRole('table', { name: 'Dispositivos' })).findByText('En mantenimiento')).toBeInTheDocument();
  });

  it('un rechazo del backend al cambiar el estado se informa dentro del diálogo y no cambia nada', async () => {
    inst('MODERADOR', {
      [`GET ${BASE}`]: page([item({ idInstitucionAsignada: ID })]), [`GET ${BASE}/summary`]: jsonResponse(200, COUNTS),
      [`POST ${BASE}/${DID}/state`]: jsonResponse(403, { codigo: 'PERMISO_INSUFICIENTE', detail: 'No tenés permiso para realizar esta operación sobre los dispositivos.' }),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/dispositivos`);
    await user.click(await screen.findByRole('button', { name: 'Cambiar estado de GL-0001' }));
    const dialog = within(screen.getByRole('alertdialog'));
    await user.selectOptions(dialog.getByLabelText('Nuevo estado'), 'FUERA_DE_SERVICIO');
    await user.click(dialog.getByRole('button', { name: /Confirmar cambio/ }));
    expect(await dialog.findByText(/No tenés permiso/)).toBeInTheDocument();
  });

  it('el propietario ve el detalle sin cambiar responsable ni desvincular: solo estado y retiro', async () => {
    inst('PROPIETARIO', {
      [`GET ${BASE}/${DID}`]: jsonResponse(200, detail({ idInstitucionAsignada: ID, responsable: PERSON }, {
        puedeEditar: false, puedeAsignarInstitucion: false, puedeCambiarResponsable: false, puedeDesvincular: false })),
      [`GET ${BASE}/${DID}/measurements`]: jsonResponse(200, EMPTY_PAGE),
    });
    renderAt(`/app/instituciones/${ID}/dispositivos/${DID}`);
    expect(await screen.findByRole('heading', { name: 'Cambiar estado' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Retirar' })).toBeInTheDocument();
    expect(screen.getByText('Propietario asignado').closest('div')).toHaveTextContent('Ana Paz');
    for (const heading of ['Responsable', 'Asignar a una institución']) {
      expect(screen.queryByRole('heading', { name: heading })).not.toBeInTheDocument();
    }
    expect(screen.queryByRole('button', { name: /Modificar|Desvincular|Cambiar responsable/ })).not.toBeInTheDocument();
  });

  it('el moderador cambia estados pero no retira, edita ni reasigna', async () => {
    inst('MODERADOR', {
      [`GET ${BASE}/${DID}`]: jsonResponse(200, detail({ idInstitucionAsignada: ID }, {
        puedeEditar: false, puedeAsignarInstitucion: false, puedeCambiarResponsable: false, puedeDesvincular: false, puedeDescomisionar: false })),
      [`GET ${BASE}/${DID}/measurements`]: jsonResponse(200, EMPTY_PAGE),
    });
    renderAt(`/app/instituciones/${ID}/dispositivos/${DID}`);
    expect(await screen.findByRole('heading', { name: 'Cambiar estado' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Responsable' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Retirar' })).not.toBeInTheDocument();
  });

  it('un descomisionado sigue en el inventario como Descomisionado, cuenta en los indicadores y no ofrece acciones', async () => {
    const retired = item({ idDispositivo: 'd-9', codigoDispositivo: 'GL-0009', estado: 'BAJA', disponibleParaMedir: false, idInstitucionAsignada: ID, responsable: PERSON });
    inst('PROPIETARIO', {
      [`GET ${BASE}`]: page([item({ idInstitucionAsignada: ID, responsable: PERSON }), retired]),
      [`GET ${BASE}/summary`]: jsonResponse(200, { ...COUNTS, total: 2, operativos: 1, enMantenimiento: 0, fueraDeServicio: 0, descomisionados: 1 }),
      [`GET ${BASE}/d-9`]: jsonResponse(200, { ...detail({ ...retired }, {
        puedeEditar: false, puedeCambiarEstado: false, puedeAsignarInstitucion: false, puedeCambiarResponsable: false, puedeDesvincular: false, puedeDescomisionar: false }) }),
      [`GET ${BASE}/d-9/measurements`]: jsonResponse(200, EMPTY_PAGE),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/dispositivos`);
    const cards = within(await screen.findByRole('list', { name: 'Indicadores del inventario' }));
    expect(cards.getByText('Total de dispositivos').closest('li')).toHaveTextContent('2'); // el total incluye los descomisionados
    expect(cards.getByText('Descomisionados').closest('li')).toHaveTextContent('1');
    const table = within(await screen.findByRole('table', { name: 'Dispositivos' }));
    const row = table.getByText('GL-0009').closest('tr');
    expect(row).toHaveTextContent('Descomisionado');
    expect(row).toHaveTextContent('Ana Paz'); // conserva la referencia histórica del responsable
    expect(within(row).queryByRole('button', { name: /Cambiar estado/ })).not.toBeInTheDocument();
    expect(table.getByRole('button', { name: 'Cambiar estado de GL-0001' })).toBeInTheDocument(); // el operativo sí
    await user.click(within(row).getByRole('link', { name: 'Ver detalle de GL-0009' }));
    expect(await screen.findByText(/fue descomisionado/)).toBeInTheDocument();
    for (const heading of ['Cambiar estado', 'Retirar', 'Responsable']) {
      expect(screen.queryByRole('heading', { name: heading })).not.toBeInTheDocument();
    }
  });

  it('un dispositivo de otra institución se informa como inexistente', async () => {
    inst('PROPIETARIO', { [`GET ${BASE}/${DID}`]: jsonResponse(404, { codigo: 'DISPOSITIVO_NO_ENCONTRADO', detail: 'No encontramos ese dispositivo.' }) });
    renderAt(`/app/instituciones/${ID}/dispositivos/${DID}`);
    expect(await screen.findByText('No encontramos ese dispositivo.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Cambiar estado' })).not.toBeInTheDocument();
  });
});
