import { configure, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { clearTokens, saveTokens } from '../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../test/helpers.js';
import { renderAt } from '../../../test/renderApp.jsx';
import { DeviceMonitor } from '../measurements/DeviceMonitor.jsx';

// Sin Arduino ni stream real: solo se prueba lo que la pantalla de medición dice de la matriz.
vi.mock('../../../api/acquisitionApi.js', async (importOriginal) => ({
  ...(await importOriginal()),
  openStream: vi.fn(() => () => {}),
  openTelemetryStream: vi.fn(() => () => {}),
}));

// Con todos los archivos en paralelo, 1 s por defecto no siempre alcanza para que las pantallas carguen.
configure({ asyncUtilTimeout: 5000 });

const PLATFORM = { ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta: 'MODERADOR_PLATAFORMA' } };
const INSTITUTIONAL = { ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };
const ID = '9a000000-0000-4000-8000-000000000001';
const BASE = `/institutions/${ID}`;
const MID = 'mx-1';
const PERMISOS = {
  PROPIETARIO: ['CONSULTAR_INSTITUCION', 'MODIFICAR_INSTITUCION', 'GESTIONAR_MODERADORES', 'ADMINISTRAR_OPERADORES',
    'CONSULTAR_EQUIPO', 'ELIMINAR_INSTITUCION', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES', 'BAJA_PACIENTES',
    'GESTIONAR_MATRICES', 'CONSULTAR_MATRIZ'],
  MODERADOR: ['CONSULTAR_INSTITUCION', 'INCORPORAR_OPERADORES', 'ADMINISTRAR_OPERADORES', 'CONSULTAR_EQUIPO',
    'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES', 'BAJA_PACIENTES', 'GESTIONAR_MATRICES', 'CONSULTAR_MATRIZ'],
  OPERADOR: ['CONSULTAR_INSTITUCION', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES', 'CONSULTAR_MATRIZ'],
};

function institution(rol) {
  return {
    idInstitucion: ID, nombre: 'Centro Médico San José', tipoInstitucion: 'CLINICA', estado: 'ACTIVA', rolInstitucion: rol,
    estadoRelacion: 'ACTIVO', permisos: PERMISOS[rol], tipoIdentificadorLegal: 'CUIT', identificadorLegal: '30712345671',
    descripcion: null, fechaCreacion: '2026-10-01T10:00:00', fechaActualizacion: '2026-10-01T10:00:00',
    propietario: { nombre: 'Victoria', apellido: 'Cortés' }, cantidadModeradores: 1, cantidadOperadores: 1, cantidadPacientes: 0,
  };
}

const RULE = {
  idReglaMatriz: 'r-1', codigoRegla: 'R-001', sexoModelo: 'FEMENINO', edadDesde: 18, edadHasta: 60, condicionComida: 'AYUNO',
  minutosComidaMin: null, minutosComidaMax: null, glucosaMinReferencia: '70.00', glucosaMaxReferencia: '110.00',
};

function item(overrides = {}) {
  return {
    idMatriz: MID, nombre: 'Matriz GlucoLume', version: '1', ambito: 'GLOBAL', estado: 'BORRADOR', fechaVigenciaDesde: '2026-10-01',
    fechaVigenciaHasta: null, fechaCreacion: '2026-10-01T10:00:00', cantidadReglas: 1, medicionesRegistradas: 0,
    referenciaBase: 'Guía de referencia', urlReferencia: null, ...overrides,
  };
}

function detail(overrides = {}, permisos = {}) {
  return {
    ...item(), descripcion: null, idInstitucion: null, nombreInstitucion: null, reglas: [RULE],
    permisos: { puedeEditar: true, puedeActivar: true, puedeDesactivar: false, puedeArchivar: true, puedeCrearVersion: false,
      puedeVerAuditoria: true, ...permisos },
    creadaPor: { fecha: '2026-10-01T10:00:00', por: 'Moderación Plataforma' }, ultimaModificacion: null, ...overrides,
  };
}

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

function routes(account, extra = {}) {
  return mockApi({ 'GET /auth/me': jsonResponse(200, account), ...extra });
}

describe('Matrices globales (plataforma)', () => {
  it('aparece en el menú de la plataforma y muestra la matriz activa y las versiones', async () => {
    routes(PLATFORM, {
      'GET /matrices/global': jsonResponse(200, [
        item({ idMatriz: 'mx-2', version: '2', estado: 'ACTIVA', cantidadReglas: 3, medicionesRegistradas: 4 }),
        item({ version: '1', estado: 'INACTIVA' }),
      ]),
    });
    renderAt('/app/matrices');
    expect(await screen.findByRole('heading', { name: 'Administración de matrices globales' })).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Secciones de la cuenta' });
    expect(within(nav).getByRole('link', { name: 'Matrices globales' })).toHaveAttribute('href', '/app/matrices');
    const activePanel = within((await screen.findByRole('heading', { name: 'Matriz global activa' })).closest('section'));
    expect(await activePanel.findByText('Matriz GlucoLume · versión 2')).toBeInTheDocument();
    const list = within(screen.getByRole('list', { name: 'Versiones de matrices' }));
    expect(list.getAllByRole('listitem')).toHaveLength(2);
    expect(list.getByText('Activa')).toBeInTheDocument();
    expect(list.getByText('Inactiva')).toBeInTheDocument();
    expect(list.getByText(/usada en 4 mediciones/)).toBeInTheDocument();
  });

  it('sin una global activa lo avisa y permite crear la primera', async () => {
    const { calls } = routes(PLATFORM, {
      'GET /matrices/global': jsonResponse(200, []),
      'POST /matrices': jsonResponse(201, detail()),
      [`GET /matrices/${MID}`]: jsonResponse(200, detail()),
    });
    const user = userEvent.setup();
    renderAt('/app/matrices');
    expect(await screen.findByText(/No hay una matriz global activa/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Crear matriz global' }));
    const form = screen.getByRole('form', { name: 'Crear matriz' });
    await user.click(within(form).getByRole('button', { name: 'Crear matriz' }));
    expect(within(form).getByText('Ingresá el nombre de la matriz.')).toBeInTheDocument();
    expect(within(form).getByText('Indicá de dónde se tomaron los criterios: es obligatorio.')).toBeInTheDocument();
    await user.type(within(form).getByLabelText('Nombre'), 'Matriz GlucoLume');
    await user.type(within(form).getByLabelText('Referencia base (obligatoria)'), 'Guía de referencia');
    await user.click(within(form).getByRole('button', { name: 'Crear matriz' }));
    expect(await screen.findByRole('heading', { name: /Matriz GlucoLume · versión 1/ })).toBeInTheDocument();
    expect(calls.find((call) => call.key === 'POST /matrices').body).toEqual({ ambito: 'GLOBAL', nombre: 'Matriz GlucoLume', referenciaBase: 'Guía de referencia' });
  });

  it('una cuenta que no es de plataforma no accede a la administración global', async () => {
    const { calls } = routes(ACCOUNT, { 'GET /groups/mine': jsonResponse(200, { grupo: null }), 'GET /groups/invitations': jsonResponse(200, []) });
    renderAt('/app/matrices');
    await screen.findByRole('navigation', { name: 'Secciones de la cuenta' });
    expect(screen.queryByRole('heading', { name: 'Administración de matrices globales' })).not.toBeInTheDocument();
    expect(calls.some((call) => call.key === 'GET /matrices/global')).toBe(false);
    const nav = await screen.findByRole('navigation', { name: 'Secciones de la cuenta' });
    expect(within(nav).queryByRole('link', { name: 'Matrices globales' })).not.toBeInTheDocument();
  });
});

describe('Matrices institucionales', () => {
  const GLOBAL = { idMatriz: 'g', nombre: 'ADA 2026', version: '3', ambito: 'GLOBAL', estado: 'ACTIVA' };
  const OWN = { idMatriz: 'm2', nombre: 'Matriz San José', version: '2', ambito: 'INSTITUCION', estado: 'ACTIVA' };
  const GENERAL = { idReglaMatriz: 'g-3', codigoRegla: 'NI_N_U', sexoModelo: 'NO_INFORMADO', edadDesde: null, edadHasta: null, condicionComida: 'NO_INFORMADA',
    minutosComidaMin: null, minutosComidaMax: null, glucosaMinReferencia: '70.00', glucosaMaxReferencia: '180.00' };
  const POSTPRANDIAL = { ...RULE, idReglaMatriz: 'g-2', codigoRegla: 'F_P18', condicionComida: 'POSTPRANDIAL', minutosComidaMin: 60, minutosComidaMax: 120,
    glucosaMinReferencia: '70.00', glucosaMaxReferencia: '179.99' };
  const READ_ONLY = { puedeEditar: false, puedeActivar: false, puedeDesactivar: false, puedeArchivar: false, puedeCrearVersion: false, puedeVerAuditoria: false };
  const globalDetail = (extra = {}) => detail({ idMatriz: 'g', nombre: 'ADA 2026', version: '3', estado: 'ACTIVA', descripcion: 'Matriz orientativa para adultos no gestantes.',
    cantidadReglas: 3, reglas: [GENERAL, POSTPRANDIAL, { ...RULE, idReglaMatriz: 'g-1', codigoRegla: 'F_A18' }], permisos: READ_ONLY, creadaPor: null, ...extra });
  const ownDetail = (extra = {}) => detail({ idMatriz: 'm2', nombre: 'Matriz San José', version: '2', ambito: 'INSTITUCION', idInstitucion: ID, estado: 'ACTIVA',
    descripcion: 'Rangos del servicio de diabetes', permisos: { ...READ_ONLY, puedeDesactivar: true, puedeCrearVersion: true }, ...extra });
  const overviewGlobal = (versiones = []) => ({ institucionActiva: null, globalActiva: GLOBAL, efectiva: GLOBAL, versiones });
  const overviewOwn = (versiones) => ({ institucionActiva: OWN, globalActiva: GLOBAL, efectiva: OWN, versiones });
  const own = (overrides) => item({ nombre: 'Matriz San José', ambito: 'INSTITUCION', ...overrides });

  it('sin matriz propia muestra la global en uso, explica y ofrece crear la institucional', async () => {
    routes(INSTITUTIONAL, {
      [`GET ${BASE}`]: jsonResponse(200, institution('PROPIETARIO')),
      [`GET ${BASE}/matrices`]: jsonResponse(200, overviewGlobal()),
      'GET /matrices/g': jsonResponse(200, globalDetail()),
    });
    renderAt(`/app/instituciones/${ID}/matrices`);
    const card = within((await screen.findByText('Matriz de estimación actualmente utilizada')).closest('section'));
    expect(await card.findByText('ADA 2026 · versión 3')).toBeInTheDocument();
    expect(card.getByText('En uso')).toBeInTheDocument();
    expect(card.getAllByText('Global de GlucoLume').length).toBeGreaterThan(0);
    expect(card.getByText('Solo lectura')).toBeInTheDocument();
    expect(card.getByText('Esta institución utiliza actualmente la matriz global de GlucoLume. Podés consultar sus reglas o crear una matriz institucional propia.')).toBeInTheDocument();
    expect(await card.findByText('Matriz orientativa para adultos no gestantes.')).toBeInTheDocument();
    expect(card.getByText('Reglas', { selector: 'dt' }).nextSibling).toHaveTextContent('3');
    expect(screen.getByRole('button', { name: 'Crear matriz institucional' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Utilizar matriz global' })).not.toBeInTheDocument();
    expect(screen.getByText('Todavía no se crearon matrices institucionales. Actualmente se utiliza la matriz global de GlucoLume.')).toBeInTheDocument();
    expect(screen.getByText(/prototipo tecnológico experimental/)).toBeInTheDocument();
  });

  it('las reglas de la matriz global están contraídas y se despliegan todas, solo con los criterios que aplican, sin poder modificarlas', async () => {
    routes(INSTITUTIONAL, {
      [`GET ${BASE}`]: jsonResponse(200, institution('MODERADOR')),
      [`GET ${BASE}/matrices`]: jsonResponse(200, overviewGlobal()),
      'GET /matrices/g': jsonResponse(200, globalDetail()),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/matrices`);
    const toggle = await screen.findByRole('button', { name: 'Ver reglas de esta matriz' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('table', { name: /Reglas de ADA 2026/ })).not.toBeInTheDocument();
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const table = within(screen.getByRole('table', { name: 'Reglas de ADA 2026, versión 3' }));
    expect(table.getAllByRole('row')).toHaveLength(4); // encabezado + las 3 reglas
    expect(table.getByText('Regla general')).toBeInTheDocument(); // sexo, edad y comida sin informar
    expect(table.getByText('No especificada')).toBeInTheDocument();
    expect(table.getByText('Sin dato de comida')).toBeInTheDocument();
    expect(table.getByText('Después de comer (60 a 120 min)')).toBeInTheDocument();
    expect(table.getByText('70 – 180 mg/dL')).toBeInTheDocument();
    expect(table.getByText('70 – 179,99 mg/dL')).toBeInTheDocument();
    expect(screen.getByText(/La matriz global es de solo lectura/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Editar regla|Eliminar regla|Agregar regla/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/[{}]/)).not.toBeInTheDocument(); // sin estructuras JSON
    // Tabla responsive: cada celda lleva su rótulo para mostrarse como tarjeta.
    expect(screen.getByRole('table', { name: 'Reglas de ADA 2026, versión 3' }).querySelector('td[data-label="Criterios de aplicación"]')).not.toBeNull();
    await user.click(toggle);
    expect(screen.queryByRole('table', { name: 'Reglas de ADA 2026, versión 3' })).not.toBeInTheDocument();
  });

  it('las reglas distinguen el error al recuperarlas (con reintento) y la matriz sin reglas', async () => {
    let attempts = 0;
    routes(INSTITUTIONAL, {
      [`GET ${BASE}`]: jsonResponse(200, institution('PROPIETARIO')),
      [`GET ${BASE}/matrices`]: jsonResponse(200, overviewGlobal()),
      'GET /matrices/g': () => {
        attempts += 1;
        if (attempts <= 2) return jsonResponse(500, { codigo: 'ERROR_SERVIDOR', detail: 'x' }); // la carga inicial y el primer intento fallan
        return jsonResponse(200, globalDetail({ cantidadReglas: 0, reglas: [] }));
      },
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/matrices`);
    await user.click(await screen.findByRole('button', { name: 'Ver reglas de esta matriz' }));
    expect(await screen.findByText(/No pudimos recuperar las reglas de esta matriz/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Reintentar' }));
    expect(await screen.findByText('Esta matriz todavía no tiene reglas configuradas.')).toBeInTheDocument();
  });

  it('con matriz propia la destaca como «En uso», conserva la global de respaldo y lista las versiones', async () => {
    routes(INSTITUTIONAL, {
      [`GET ${BASE}`]: jsonResponse(200, institution('MODERADOR')),
      [`GET ${BASE}/matrices`]: jsonResponse(200, overviewOwn([
        own({ idMatriz: 'm2', version: '2', estado: 'ACTIVA', descripcion: 'Rangos del servicio', cantidadReglas: 4 }),
        own({ idMatriz: 'm1', version: '1', estado: 'INACTIVA', medicionesRegistradas: 2, cantidadReglas: 2 }),
        own({ idMatriz: 'm3', version: '3', estado: 'BORRADOR', cantidadReglas: 1 }),
      ])),
      'GET /matrices/m2': jsonResponse(200, ownDetail({ cantidadReglas: 4 })),
      'GET /matrices/g': jsonResponse(200, globalDetail()),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/matrices`);
    const card = within((await screen.findByText('Matriz de estimación actualmente utilizada')).closest('section'));
    expect(await card.findByText('Matriz San José · versión 2')).toBeInTheDocument();
    expect(card.getByText('En uso')).toBeInTheDocument();
    expect(card.getAllByText('Institucional').length).toBeGreaterThan(0);
    expect(screen.queryByText(/utiliza actualmente la matriz global/)).not.toBeInTheDocument();

    const backup = within(screen.getByRole('heading', { name: /Matriz global de GlucoLume \(respaldo\)/ }).closest('section'));
    expect(backup.getByText('ADA 2026 · versión 3')).toBeInTheDocument();
    await user.click(backup.getByRole('button', { name: 'Ver reglas de la matriz global' }));
    expect(await screen.findByRole('table', { name: 'Reglas de ADA 2026, versión 3' })).toBeInTheDocument();

    const versions = within(screen.getByRole('list', { name: 'Matrices institucionales' }));
    const rows = versions.getAllByRole('listitem');
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByText('En uso')).toBeInTheDocument();
    expect(within(rows[0]).getByText('Rangos del servicio')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Inactiva')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Usada en 2')).toBeInTheDocument();
    expect(within(rows[2]).getByText('Borrador')).toBeInTheDocument();
    expect(within(rows[2]).getByRole('link', { name: /Editar borrador/ })).toHaveAttribute('href', `/app/instituciones/${ID}/matrices/m3`);
    expect(within(rows[0]).queryByRole('button', { name: /Activar/ })).not.toBeInTheDocument(); // la activa no se activa de nuevo
    expect(within(rows[1]).getByRole('button', { name: /Activar Matriz San José versión 1/ })).toBeInTheDocument();
    expect(within(rows[0]).getByRole('link', { name: /Ver matriz Matriz San José versión 2/ })).toHaveAttribute('href', `/app/instituciones/${ID}/matrices/m2`);
  });

  it('activa una versión con confirmación y la anterior queda en el historial', async () => {
    const draft = own({ idMatriz: 'm1', version: '1', estado: 'BORRADOR', cantidadReglas: 2 });
    const activated = { ...OWN, idMatriz: 'm1', version: '1' };
    const { calls } = routes(INSTITUTIONAL, {
      [`GET ${BASE}`]: jsonResponse(200, institution('PROPIETARIO')),
      [`GET ${BASE}/matrices`]: [jsonResponse(200, overviewGlobal([draft])),
        jsonResponse(200, { institucionActiva: activated, globalActiva: GLOBAL, efectiva: activated, versiones: [{ ...draft, estado: 'ACTIVA' }] })],
      'GET /matrices/g': jsonResponse(200, globalDetail()),
      'GET /matrices/m1': jsonResponse(200, ownDetail({ idMatriz: 'm1', version: '1' })),
      'POST /matrices/m1/activate': jsonResponse(200, ownDetail({ idMatriz: 'm1', version: '1' })),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/matrices`);
    await user.click(await screen.findByRole('button', { name: /Activar Matriz San José versión 1/ }));
    expect(calls.some((call) => call.key.endsWith('/activate'))).toBe(false); // nada sin confirmar
    expect(screen.getByText(/la activa actual se conserva como versión histórica/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Confirmar activación' }));
    expect(await screen.findByText(/Activaste «Matriz San José» \(versión 1\)/)).toBeInTheDocument();
    const card = within((await screen.findByText('Matriz de estimación actualmente utilizada')).closest('section'));
    expect(await card.findByText('Matriz San José · versión 1')).toBeInTheDocument();
    expect(card.getByText('En uso')).toBeInTheDocument();
  });

  it('si el servidor rechaza la activación se informa el motivo y no cambia lo vigente', async () => {
    const draft = own({ idMatriz: 'm1', version: '1', estado: 'BORRADOR', cantidadReglas: 0 });
    routes(INSTITUTIONAL, {
      [`GET ${BASE}`]: jsonResponse(200, institution('MODERADOR')),
      [`GET ${BASE}/matrices`]: jsonResponse(200, overviewGlobal([draft])),
      'GET /matrices/g': jsonResponse(200, globalDetail()),
      'POST /matrices/m1/activate': jsonResponse(409, { codigo: 'SIN_REGLAS', detail: 'La matriz no se puede activar: La matriz no tiene reglas: agregá al menos una.' }),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/matrices`);
    await user.click(await screen.findByRole('button', { name: /Activar Matriz San José versión 1/ }));
    await user.click(screen.getByRole('button', { name: 'Confirmar activación' }));
    expect(await screen.findByText(/no tiene reglas/)).toBeInTheDocument();
    expect(screen.getByText('ADA 2026 · versión 3')).toBeInTheDocument();
  });

  it('«Utilizar matriz global» pide confirmación y desactiva la institucional sin borrar versiones', async () => {
    const versions = (estado) => [own({ idMatriz: 'm2', version: '2', estado })];
    const { calls } = routes(INSTITUTIONAL, {
      [`GET ${BASE}`]: jsonResponse(200, institution('PROPIETARIO')),
      [`GET ${BASE}/matrices`]: [jsonResponse(200, overviewOwn(versions('ACTIVA'))), jsonResponse(200, overviewGlobal(versions('INACTIVA')))],
      'GET /matrices/m2': jsonResponse(200, ownDetail()),
      'GET /matrices/g': jsonResponse(200, globalDetail()),
      'POST /matrices/m2/deactivate': jsonResponse(200, ownDetail({ estado: 'INACTIVA' })),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/matrices`);
    await user.click(await screen.findByRole('button', { name: 'Utilizar matriz global' }));
    expect(calls.some((call) => call.key === 'POST /matrices/m2/deactivate')).toBe(false); // nada sin confirmar
    expect(screen.getByText(/Tus matrices institucionales se conservan/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Confirmar' }));
    expect(await screen.findByText(/vuelve a utilizar la matriz global de GlucoLume/)).toBeInTheDocument();
    expect(await screen.findByText(/Esta institución utiliza actualmente la matriz global/)).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Matrices institucionales' })).getAllByRole('listitem')).toHaveLength(1); // se conserva
  });

  it('quien no puede desactivar la institucional no ve «Utilizar matriz global»', async () => {
    routes(INSTITUTIONAL, {
      [`GET ${BASE}`]: jsonResponse(200, institution('MODERADOR')),
      [`GET ${BASE}/matrices`]: jsonResponse(200, overviewOwn([])),
      'GET /matrices/m2': jsonResponse(200, ownDetail({ permisos: READ_ONLY })),
      'GET /matrices/g': jsonResponse(200, globalDetail()),
    });
    renderAt(`/app/instituciones/${ID}/matrices`);
    expect(await screen.findByRole('button', { name: 'Crear matriz institucional' })).toBeInTheDocument();
    await screen.findByText('Matriz San José · versión 2');
    expect(screen.queryByRole('button', { name: 'Utilizar matriz global' })).not.toBeInTheDocument();
  });

  it('crea una matriz con sus reglas: valida, revisa, guarda en borrador y no la activa', async () => {
    const created = detail({ idMatriz: 'new-1', nombre: 'Matriz San José', version: '1', ambito: 'INSTITUCION', idInstitucion: ID, estado: 'BORRADOR', cantidadReglas: 2,
      reglas: [RULE, { ...RULE, idReglaMatriz: 'r-2', codigoRegla: 'R-002', sexoModelo: 'MASCULINO' }] });
    const { calls } = routes(INSTITUTIONAL, {
      [`GET ${BASE}`]: jsonResponse(200, institution('PROPIETARIO')),
      [`GET ${BASE}/matrices`]: jsonResponse(200, overviewGlobal()),
      'GET /matrices/g': jsonResponse(200, globalDetail()),
      'POST /matrices/check-rules': jsonResponse(200, { valida: true, problemas: [], advertencias: [{ codigo: 'SIN_COBERTURA', mensaje: 'Sin regla para masculino, en ayunas: edades de 61 a 69 años.' }] }),
      'POST /matrices': jsonResponse(201, created),
      'GET /matrices/new-1': jsonResponse(200, created),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/matrices`);
    await user.click(await screen.findByRole('button', { name: 'Crear matriz institucional' }));
    const form = screen.getByRole('form', { name: 'Crear matriz institucional' });
    expect(within(form).getByText(/La versión la asigna GlucoLume automáticamente/)).toBeInTheDocument();

    // Sin nombre ni reglas no se guarda.
    await user.click(within(form).getByRole('button', { name: /Guardar matriz/ }));
    expect(within(form).getByText('Ingresá el nombre de la matriz.')).toBeInTheDocument();
    expect(within(form).getByText('Agregá al menos una regla.')).toBeInTheDocument();
    expect(calls.some((call) => call.key === 'POST /matrices')).toBe(false);

    await user.type(within(form).getByLabelText('Nombre'), 'Matriz San José');
    await user.type(within(form).getByLabelText('Descripción (opcional)'), 'Rangos del servicio');
    await user.type(within(form).getByLabelText('Referencia base (obligatoria)'), 'Guía del servicio');
    await user.type(within(form).getByLabelText('Enlace de la referencia (opcional)'), 'https://ejemplo.org/guia');

    async function fillRule(sex, from, to, min, max) {
      await user.click(within(form).getByRole('button', { name: 'Agregar regla' }));
      const editor = within(screen.getByRole('form', { name: 'Agregar regla' }));
      await user.selectOptions(editor.getByLabelText('Sexo del modelo'), sex);
      await user.type(editor.getByLabelText('Edad mínima'), from);
      await user.type(editor.getByLabelText('Edad máxima'), to);
      await user.type(editor.getByLabelText('Glucosa de referencia mínima (mg/dL)'), min);
      await user.type(editor.getByLabelText('Glucosa de referencia máxima (mg/dL)'), max);
      return editor;
    }
    let editor = await fillRule('FEMENINO', '18', '60', '70', '110');
    await user.click(editor.getByRole('button', { name: /Agregar regla/ }));
    // Una regla que se pisa con la anterior se rechaza al instante, sin llamar al servidor.
    editor = await fillRule('FEMENINO', '50', '70', '70', '120');
    await user.click(editor.getByRole('button', { name: /Agregar regla/ }));
    expect(await screen.findByText(/La regla se solapa con Regla 1/)).toBeInTheDocument();
    await user.click(editor.getByRole('button', { name: /Cancelar/ }));
    editor = await fillRule('MASCULINO', '18', '60', '70', '110');
    await user.click(editor.getByRole('button', { name: /Agregar regla/ }));
    const loaded = () => within(form).getByRole('table', { name: 'Reglas cargadas' });
    expect(loaded().querySelectorAll('tbody tr')).toHaveLength(2);

    // Quitar y volver a agregar antes de guardar.
    await user.click(within(loaded()).getByRole('button', { name: 'Quitar Regla 2' }));
    expect(loaded().querySelectorAll('tbody tr')).toHaveLength(1);
    editor = await fillRule('MASCULINO', '18', '60', '70', '110');
    await user.click(editor.getByRole('button', { name: /Agregar regla/ }));

    await user.click(within(form).getByRole('button', { name: 'Revisar configuración' }));
    expect(await within(form).findByText(/La configuración es válida/)).toBeInTheDocument();
    expect(within(form).getByText(/edades de 61 a 69 años/)).toBeInTheDocument();
    expect(calls.find((call) => call.key === 'POST /matrices/check-rules').body.reglas).toHaveLength(2);

    await user.click(within(form).getByRole('button', { name: /Guardar matriz/ }));
    expect(await screen.findByText(/Todavía no se usa: activala cuando quieras/)).toBeInTheDocument();
    const body = calls.find((call) => call.key === 'POST /matrices').body;
    expect(body).toMatchObject({ ambito: 'INSTITUCION', idInstitucion: ID, nombre: 'Matriz San José', descripcion: 'Rangos del servicio',
      referenciaBase: 'Guía del servicio', urlReferencia: 'https://ejemplo.org/guia' });
    const common = { edadDesde: 18, edadHasta: 60, condicionComida: 'AYUNO', minutosComidaMin: null, minutosComidaMax: null, glucosaMinReferencia: '70', glucosaMaxReferencia: '110' };
    expect(body.reglas).toEqual([{ sexoModelo: 'FEMENINO', ...common }, { sexoModelo: 'MASCULINO', ...common }]);
    expect(calls.some((call) => call.key.endsWith('/activate'))).toBe(false); // guardar no activa
  });

  it('el rechazo del servidor al guardar se informa y no navega', async () => {
    routes(INSTITUTIONAL, {
      [`GET ${BASE}`]: jsonResponse(200, institution('PROPIETARIO')),
      [`GET ${BASE}/matrices`]: jsonResponse(200, overviewGlobal()),
      'GET /matrices/g': jsonResponse(200, globalDetail()),
      'POST /matrices': jsonResponse(409, { codigo: 'REGLA_SOLAPADA', detail: 'Regla 2: La regla se solapa con Regla 1.' }),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/matrices`);
    await user.click(await screen.findByRole('button', { name: 'Crear matriz institucional' }));
    const form = screen.getByRole('form', { name: 'Crear matriz institucional' });
    await user.type(within(form).getByLabelText('Nombre'), 'Matriz');
    await user.type(within(form).getByLabelText('Referencia base (obligatoria)'), 'Guía del servicio');
    await user.click(within(form).getByRole('button', { name: 'Agregar regla' }));
    const editor = within(screen.getByRole('form', { name: 'Agregar regla' }));
    await user.type(editor.getByLabelText('Edad mínima'), '18');
    await user.type(editor.getByLabelText('Edad máxima'), '60');
    await user.type(editor.getByLabelText('Glucosa de referencia mínima (mg/dL)'), '70');
    await user.type(editor.getByLabelText('Glucosa de referencia máxima (mg/dL)'), '110');
    await user.click(editor.getByRole('button', { name: /Agregar regla/ }));
    await user.click(within(form).getByRole('button', { name: /Guardar matriz/ }));
    expect(await within(form).findByText(/se solapa con Regla 1/)).toBeInTheDocument();
  });

  it('una fecha inválida del servidor se marca bajo el campo de fecha, no como un problema del nombre', async () => {
    routes(INSTITUTIONAL, {
      [`GET ${BASE}`]: jsonResponse(200, institution('PROPIETARIO')),
      [`GET ${BASE}/matrices`]: jsonResponse(200, overviewGlobal()),
      'GET /matrices/g': jsonResponse(200, globalDetail()),
      'POST /matrices': jsonResponse(422, { detail: [{ type: 'date_from_datetime_parsing', loc: ['body', 'fechaVigenciaDesde'], msg: 'Input should be a valid date or datetime, invalid date' }] }),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/matrices`);
    await user.click(await screen.findByRole('button', { name: 'Crear matriz institucional' }));
    const form = screen.getByRole('form', { name: 'Crear matriz institucional' });
    await user.type(within(form).getByLabelText('Nombre'), 'Matriz');
    await user.type(within(form).getByLabelText('Referencia base (obligatoria)'), 'Guía del servicio');
    await user.click(within(form).getByRole('button', { name: 'Agregar regla' }));
    const editor = within(screen.getByRole('form', { name: 'Agregar regla' }));
    await user.type(editor.getByLabelText('Edad mínima'), '18');
    await user.type(editor.getByLabelText('Edad máxima'), '60');
    await user.type(editor.getByLabelText('Glucosa de referencia mínima (mg/dL)'), '70');
    await user.type(editor.getByLabelText('Glucosa de referencia máxima (mg/dL)'), '110');
    await user.click(editor.getByRole('button', { name: /Agregar regla/ }));
    await user.click(within(form).getByRole('button', { name: /Guardar matriz/ }));
    expect(await within(form).findByText('Ingresá una fecha válida (AAAA-MM-DD).')).toBeInTheDocument();
    expect(within(form).getByText('Revisá los campos marcados en el formulario.')).toBeInTheDocument();
    expect(within(form).queryByText(/Input should be/)).not.toBeInTheDocument();
    expect(within(form).getByLabelText('Nombre')).not.toHaveAttribute('aria-invalid', 'true');
  });

  it('el menú de la institución ofrece «Matrices» a propietario y moderador, no al operador', async () => {
    routes(INSTITUTIONAL, { [`GET ${BASE}`]: jsonResponse(200, institution('OPERADOR')) });
    renderAt(`/app/instituciones/${ID}`);
    const nav = await screen.findByRole('navigation', { name: 'Secciones de la institución' });
    expect(within(nav).queryByRole('link', { name: 'Matrices' })).not.toBeInTheDocument();
  });
});

describe('Detalle de una matriz y editor de reglas', () => {
  const open = (extra = {}, account = PLATFORM) => routes(account, extra);

  it('un borrador muestra la tabla de reglas y permite agregar una', async () => {
    const added = detail({ cantidadReglas: 2, reglas: [RULE, { ...RULE, idReglaMatriz: 'r-2', codigoRegla: 'R-002', sexoModelo: 'MASCULINO' }] });
    const { calls } = open({
      [`GET /matrices/${MID}`]: jsonResponse(200, detail()),
      [`POST /matrices/${MID}/rules`]: jsonResponse(201, added),
    });
    const user = userEvent.setup();
    renderAt(`/app/matrices/${MID}`);
    expect(await screen.findByRole('heading', { level: 1, name: /Matriz GlucoLume · versión 1/ })).toBeInTheDocument(); // matriz global: el título es el h1
    const table = within(await screen.findByRole('table', { name: 'Reglas de la matriz' }));
    expect(table.getByText('R-001')).toBeInTheDocument();
    expect(table.getByText('18 a 60 años')).toBeInTheDocument();
    expect(table.getByText('70 – 110 mg/dL')).toBeInTheDocument();
    expect(table.getByText(/En ayunas/)).toBeInTheDocument();
    expect(table.getByText('Femenino')).toBeInTheDocument();
    expect(screen.getByText(/no calcula ninguna glucosa/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Agregar regla' }));
    const form = screen.getByRole('form', { name: 'Agregar regla' });
    await user.selectOptions(within(form).getByLabelText('Sexo del modelo'), 'MASCULINO');
    await user.type(within(form).getByLabelText('Edad mínima'), '18');
    await user.type(within(form).getByLabelText('Edad máxima'), '60');
    await user.type(within(form).getByLabelText('Glucosa de referencia mínima (mg/dL)'), '70');
    await user.type(within(form).getByLabelText('Glucosa de referencia máxima (mg/dL)'), '110');
    await user.click(within(form).getByRole('button', { name: /Agregar regla/ }));
    expect(await screen.findByText('Agregamos la regla.')).toBeInTheDocument();
    expect(calls.find((call) => call.key === `POST /matrices/${MID}/rules`).body).toEqual({
      sexoModelo: 'MASCULINO', edadDesde: 18, edadHasta: 60, condicionComida: 'AYUNO', minutosComidaMin: null,
      minutosComidaMax: null, glucosaMinReferencia: '70', glucosaMaxReferencia: '110',
    });
    expect(screen.getByText('R-002')).toBeInTheDocument();
  });

  it('permite agregar una regla con sexo no informado y comida sin informar, y con la edad sin especificar', async () => {
    const added = detail({ cantidadReglas: 2, reglas: [RULE, { ...RULE, idReglaMatriz: 'r-2', codigoRegla: 'R-002', sexoModelo: 'NO_INFORMADO',
      condicionComida: 'NO_INFORMADA', edadDesde: null, edadHasta: null }] });
    const { calls } = open({
      [`GET /matrices/${MID}`]: jsonResponse(200, detail()),
      [`POST /matrices/${MID}/rules`]: jsonResponse(201, added),
    });
    const user = userEvent.setup();
    renderAt(`/app/matrices/${MID}`);
    await user.click(await screen.findByRole('button', { name: 'Agregar regla' }));
    const form = screen.getByRole('form', { name: 'Agregar regla' });
    await user.selectOptions(within(form).getByLabelText('Sexo del modelo'), 'NO_INFORMADO');
    await user.selectOptions(within(form).getByLabelText('Condición respecto de la última comida'), 'NO_INFORMADA');
    await user.type(within(form).getByLabelText('Glucosa de referencia mínima (mg/dL)'), '70');
    await user.type(within(form).getByLabelText('Glucosa de referencia máxima (mg/dL)'), '180');
    await user.click(within(form).getByRole('button', { name: /Agregar regla/ }));
    expect(await screen.findByText('Agregamos la regla.')).toBeInTheDocument();
    // Lo no informado viaja tal cual: ni un sexo ni una comida por defecto, ni una edad inventada.
    expect(calls.find((call) => call.key === `POST /matrices/${MID}/rules`).body).toEqual({
      sexoModelo: 'NO_INFORMADO', edadDesde: null, edadHasta: null, condicionComida: 'NO_INFORMADA', minutosComidaMin: null,
      minutosComidaMax: null, glucosaMinReferencia: '70', glucosaMaxReferencia: '180',
    });
  });

  it('una sola edad completa se rechaza antes de enviar (vacías las dos sí vale)', async () => {
    const { calls } = open({ [`GET /matrices/${MID}`]: jsonResponse(200, detail()) });
    const user = userEvent.setup();
    renderAt(`/app/matrices/${MID}`);
    await user.click(await screen.findByRole('button', { name: 'Agregar regla' }));
    const form = screen.getByRole('form', { name: 'Agregar regla' });
    await user.type(within(form).getByLabelText('Edad mínima'), '30');
    await user.type(within(form).getByLabelText('Glucosa de referencia mínima (mg/dL)'), '70');
    await user.type(within(form).getByLabelText('Glucosa de referencia máxima (mg/dL)'), '110');
    await user.click(within(form).getByRole('button', { name: /Agregar regla/ }));
    expect(within(form).getByText(/Ingresá una edad entre 0 y 130, o dejá ambas vacías/)).toBeInTheDocument();
    expect(calls.some((call) => call.key.startsWith('POST'))).toBe(false);
  });

  it('el editor valida rangos antes de enviar y muestra el rechazo del servidor por solapamiento', async () => {
    const { calls } = open({
      [`GET /matrices/${MID}`]: jsonResponse(200, detail()),
      [`POST /matrices/${MID}/rules`]: jsonResponse(409, { codigo: 'REGLA_SOLAPADA', detail: 'La regla se solapa con R-001: mismo sexo y condición con edades y tiempos desde la comida que se pisan.' }),
    });
    const user = userEvent.setup();
    renderAt(`/app/matrices/${MID}`);
    await user.click(await screen.findByRole('button', { name: 'Agregar regla' }));
    const form = screen.getByRole('form', { name: 'Agregar regla' });
    await user.type(within(form).getByLabelText('Edad mínima'), '50');
    await user.type(within(form).getByLabelText('Edad máxima'), '40');
    await user.type(within(form).getByLabelText('Glucosa de referencia mínima (mg/dL)'), '150');
    await user.type(within(form).getByLabelText('Glucosa de referencia máxima (mg/dL)'), '100');
    await user.click(within(form).getByRole('button', { name: /Agregar regla/ }));
    expect(within(form).getByText('La edad mínima no puede superar la máxima.')).toBeInTheDocument();
    expect(within(form).getByText('El límite mínimo no puede superar el máximo.')).toBeInTheDocument();
    expect(calls.some((call) => call.key.startsWith('POST'))).toBe(false);
    await user.clear(within(form).getByLabelText('Edad mínima'));
    await user.type(within(form).getByLabelText('Edad mínima'), '30');
    await user.clear(within(form).getByLabelText('Edad máxima'));
    await user.type(within(form).getByLabelText('Edad máxima'), '40');
    await user.clear(within(form).getByLabelText('Glucosa de referencia mínima (mg/dL)'));
    await user.type(within(form).getByLabelText('Glucosa de referencia mínima (mg/dL)'), '70');
    await user.click(within(form).getByRole('button', { name: /Agregar regla/ }));
    expect(await within(form).findByText(/La regla se solapa con R-001/)).toBeInTheDocument();
  });

  it('edita y elimina reglas de un borrador', async () => {
    const edited = detail({ reglas: [{ ...RULE, edadHasta: 65 }] });
    const { calls } = open({
      [`GET /matrices/${MID}`]: jsonResponse(200, detail()),
      [`PATCH /matrices/${MID}/rules/r-1`]: jsonResponse(200, edited),
      [`DELETE /matrices/${MID}/rules/r-1`]: jsonResponse(200, detail({ cantidadReglas: 0, reglas: [] })),
    });
    const user = userEvent.setup();
    renderAt(`/app/matrices/${MID}`);
    await user.click(await screen.findByRole('button', { name: 'Editar regla R-001' }));
    const form = screen.getByRole('form', { name: 'Editar regla R-001' });
    expect(within(form).getByLabelText('Edad máxima')).toHaveValue(60);
    await user.clear(within(form).getByLabelText('Edad máxima'));
    await user.type(within(form).getByLabelText('Edad máxima'), '65');
    await user.click(within(form).getByRole('button', { name: /Guardar regla/ }));
    expect(await screen.findByText('Guardamos la regla.')).toBeInTheDocument();
    expect(calls.find((call) => call.key.startsWith('PATCH')).body.edadHasta).toBe(65);
    expect(screen.getByText('18 a 65 años')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Eliminar regla R-001' }));
    expect(await screen.findByText('Esta matriz todavía no tiene reglas.')).toBeInTheDocument();
  });

  it('valida y activa con confirmación; el resultado queda activo y ya no se edita', async () => {
    const active = detail({ estado: 'ACTIVA' }, { puedeEditar: false, puedeActivar: false, puedeDesactivar: true, puedeArchivar: false, puedeCrearVersion: true });
    const { calls } = open({
      [`GET /matrices/${MID}`]: jsonResponse(200, detail()),
      [`POST /matrices/${MID}/validate`]: jsonResponse(200, { valida: true, problemas: [] }),
      [`POST /matrices/${MID}/activate`]: jsonResponse(200, active),
    });
    const user = userEvent.setup();
    renderAt(`/app/matrices/${MID}`);
    await user.click(await screen.findByRole('button', { name: /Validar reglas/ }));
    expect(await screen.findByText('La matriz es válida y se puede activar.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /^Activar$/ }));
    expect(screen.getByText(/La activa actual dejará de usarse/)).toBeInTheDocument();
    expect(calls.some((call) => call.key.endsWith('/activate'))).toBe(false);
    await user.click(screen.getByRole('button', { name: 'Confirmar' }));
    expect(await screen.findByText('La versión quedó activa.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Agregar regla' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Editar regla/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('form', { name: 'Datos del borrador' })).not.toBeInTheDocument();
    expect(screen.getByText(/Una versión activada no se edita/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Crear nueva versión/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Desactivar/ })).toBeInTheDocument();
  });

  it('una matriz inválida no se activa y se muestran los problemas', async () => {
    open({
      [`GET /matrices/${MID}`]: jsonResponse(200, detail()),
      [`POST /matrices/${MID}/validate`]: jsonResponse(200, {
        valida: false, problemas: [{ codigo: 'REGLA_SOLAPADA', codigoRegla: 'R-002', mensaje: 'La regla se solapa con R-001.' }],
      }),
      [`POST /matrices/${MID}/activate`]: jsonResponse(409, { codigo: 'REGLA_SOLAPADA', detail: 'La matriz no se puede activar: La regla se solapa con R-001.' }),
    });
    const user = userEvent.setup();
    renderAt(`/app/matrices/${MID}`);
    await user.click(await screen.findByRole('button', { name: /Validar reglas/ }));
    expect(await screen.findByText('La matriz no es válida:')).toBeInTheDocument();
    expect(screen.getByText('La regla se solapa con R-001.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /^Activar$/ }));
    await user.click(screen.getByRole('button', { name: 'Confirmar' }));
    expect(await screen.findByText(/La matriz no se puede activar/)).toBeInTheDocument();
  });

  it('una versión usada en mediciones se informa como historial y se versiona en vez de editarse', async () => {
    const inactive = detail({ estado: 'INACTIVA', medicionesRegistradas: 5 }, {
      puedeEditar: false, puedeActivar: true, puedeDesactivar: false, puedeArchivar: true, puedeCrearVersion: true,
    });
    const { calls } = open({
      [`GET /matrices/${MID}`]: jsonResponse(200, inactive),
      [`POST /matrices/${MID}/new-version`]: jsonResponse(201, detail({ idMatriz: 'mx-2', version: '2' })),
      'GET /matrices/mx-2': jsonResponse(200, detail({ idMatriz: 'mx-2', version: '2' })),
    });
    const user = userEvent.setup();
    renderAt(`/app/matrices/${MID}`);
    expect(await screen.findByText(/Esta versión se usó en 5 mediciones: forma parte del historial y no se modifica/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Agregar regla' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Crear nueva versión/ }));
    await user.click(screen.getByRole('button', { name: 'Confirmar' }));
    expect(await screen.findByRole('heading', { name: /versión 2/ })).toBeInTheDocument();
    expect(calls.some((call) => call.key === `POST /matrices/${MID}/new-version`)).toBe(true);
  });

  it('un moderador institucional administra la matriz pero no ve la auditoría ni quién la modificó', async () => {
    open({
      [`GET ${BASE}`]: jsonResponse(200, institution('MODERADOR')),
      [`GET /matrices/${MID}`]: jsonResponse(200, detail(
        { ambito: 'INSTITUCION', idInstitucion: ID, nombreInstitucion: 'Centro Médico San José', creadaPor: null },
        { puedeVerAuditoria: false })),
    }, INSTITUTIONAL);
    renderAt(`/app/instituciones/${ID}/matrices/${MID}`);
    expect(await screen.findByRole('button', { name: 'Agregar regla' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /auditoría/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/Moderación Plataforma/)).not.toBeInTheDocument();
  });

  it('el propietario consulta la auditoría de su institución', async () => {
    open({
      [`GET ${BASE}`]: jsonResponse(200, institution('PROPIETARIO')),
      [`GET /matrices/${MID}`]: jsonResponse(200, detail(
        { ambito: 'INSTITUCION', idInstitucion: ID, nombreInstitucion: 'Centro Médico San José' })),
      [`GET /matrices/${MID}/audit`]: jsonResponse(200, [
        { fechaHora: '2026-10-08T11:00:00', accion: 'ACTIVAR_MATRIZ', resultado: 'EXITO', usuario: 'Victoria Cortés' },
        { fechaHora: '2026-10-08T10:00:00', accion: 'CREAR_MATRIZ', resultado: 'EXITO', usuario: 'Victoria Cortés' },
      ]),
    }, INSTITUTIONAL);
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/matrices/${MID}`);
    await user.click(await screen.findByRole('button', { name: /Ver auditoría/ }));
    const list = within(await screen.findByRole('list', { name: 'Auditoría de la matriz' }));
    expect(list.getByText('Activó la versión')).toBeInTheDocument();
    expect(list.getAllByText(/Victoria Cortés/)).toHaveLength(2);
  });

  it('una matriz ajena o inexistente se informa sin datos', async () => {
    open({ [`GET /matrices/${MID}`]: jsonResponse(404, { codigo: 'MATRIZ_NO_ENCONTRADA', detail: 'No encontramos esa matriz.' }) });
    renderAt(`/app/matrices/${MID}`);
    expect(await screen.findByText('No encontramos esa matriz.')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });
});

describe('Medición: matriz aplicada', () => {
  const PROFILE = 'p-own';
  const DEVICE = { idDispositivo: 'd-1', codigoDispositivo: 'OXI-001', nombre: 'Oxímetro', modelo: 'HC-06', modeloSensor: 'MAX30102', versionFirmware: '1.0.0' };
  const OWN = {
    perfilDisponible: true, datosFaltantes: [], idPerfilMedicion: PROFILE, nombre: 'Victoria', apellido: 'Cortés',
    fechaNacimiento: '1990-05-17', edad: 36, sexoModelo: 'FEMENINO', fechaCreacion: '2026-10-01T10:00:00', fechaUltimaMedicion: null,
  };
  const base = (extra = {}) => ({
    'GET /auth/me': jsonResponse(200, ACCOUNT), 'GET /measurements/profile': jsonResponse(200, OWN),
    'GET /measurements/devices': jsonResponse(200, [DEVICE]),
    'GET /measurements': jsonResponse(200, { items: [], total: 0, pagina: 1, tamanioPagina: 10 }),
    'GET /acquisition/telemetry/status': jsonResponse(200, { estado: 'SIN_PUENTE', ocupado: false, puente: null, lectura: null, sesion: null }),
    'GET /measurements/statistics': jsonResponse(200, { dias: 30, cantidadMediciones: 0 }), ...extra,
  });

  // La pantalla unificada de medición (cuenta individual y paciente institucional) informa la matriz; se prueba directamente.
  function renderForm() {
    render(
      <MemoryRouter>
        <DeviceMonitor patient idPerfilMedicion={PROFILE} profileLabel="Paciente" profile={OWN} handleOperationError={(error) => error.message} />
      </MemoryRouter>,
    );
  }

  it('la pantalla informa la matriz que decidió el backend y no ofrece elegirla', async () => {
    const { calls } = mockApi(base({
      'GET /measurements/matrix': jsonResponse(200, { idMatriz: 'g', nombre: 'Matriz GlucoLume', version: '3', ambito: 'GLOBAL', estado: 'ACTIVA' }),
    }));
    const user = userEvent.setup();
    renderForm();
    const form = (await screen.findByRole('form', { name: 'Iniciar sesión de medición con el dispositivo' }));
    await user.selectOptions(await within(form).findByLabelText('Modo de medición'), 'GLUCOSA_EXPERIMENTAL');
    expect(await within(form).findByText(/Matriz GlucoLume, versión 3/)).toBeInTheDocument();
    expect(within(form).getByText(/Global de GlucoLume/)).toBeInTheDocument();
    expect(within(form).getByText(/no se puede cambiar/)).toBeInTheDocument();
    expect(within(form).queryByLabelText(/matriz/i)).not.toBeInTheDocument(); // sin selector
    expect(new URL(calls.find((call) => call.key === 'GET /measurements/matrix').url).searchParams.get('idPerfilMedicion')).toBe(PROFILE);
  });

  it('sin una matriz aplicable lo advierte; en oximetría no consulta ninguna', async () => {
    const { calls } = mockApi(base({ 'GET /measurements/matrix': jsonResponse(200, null) }));
    const user = userEvent.setup();
    renderForm();
    const form = (await screen.findByRole('form', { name: 'Iniciar sesión de medición con el dispositivo' }));
    await within(form).findByLabelText('Modo de medición');
    expect(calls.some((call) => call.key === 'GET /measurements/matrix')).toBe(false);
    await user.selectOptions(within(form).getByLabelText('Modo de medición'), 'GLUCOSA_EXPERIMENTAL');
    expect(await within(form).findByText(/no hay una matriz activa y vigente/)).toBeInTheDocument();
  });

  it('el detalle de una medición muestra el ámbito y la versión aplicados', async () => {
    mockApi({
      'GET /auth/me': jsonResponse(200, ACCOUNT),
      '/placeholder': jsonResponse(200, {}),
      'GET /measurements/m-1': jsonResponse(200, {
        idMedicion: 'm-1', idPerfilMedicion: PROFILE, modoMedicion: 'GLUCOSA_EXPERIMENTAL', estadoMedicion: 'INVALIDA',
        fechaHoraInicio: '2026-10-08T09:00:00', fechaHoraFin: '2026-10-08T09:01:00', fechaHoraUltimaComida: null,
        condicionComida: 'AYUNO', minutosDesdeUltimaComida: null, duracionMs: 60000, edadAlMomento: 36, sexoModelo: 'FEMENINO',
        versionFirmwareAlMomento: '1.0.0', modeloSensorAlMomento: 'MAX30102', versionAlgoritmo: null, calidadSenal: null,
        spo2: null, frecuenciaCardiaca: null, glucosaEstimada: null, observacion: null, dispositivo: DEVICE,
        matriz: { idMatriz: 'mx', nombre: 'Matriz San José', version: '2', ambito: 'INSTITUCION' }, cantidadMuestras: 1,
        referenciaCapilar: null, puedeOperar: false, aviso: 'Resultado experimental de GlucoLume.',
      }),
    });
    renderAt('/app/mediciones/m-1');
    expect(await screen.findByText('Matriz San José, versión 2 · Institucional')).toBeInTheDocument();
  });
});

// Exportar una matriz con sus reglas: lo puede ver quien la ve. El archivo lo devuelve la API y el frontend solo lo descarga.
const csvMatrix = () => ({
  ok: true, status: 200, headers: new Headers({ 'Content-Disposition': 'attachment; filename="matriz-prueba.csv"' }),
  blob: async () => new Blob(['csv'], { type: 'text/csv' }),
});

describe('Exportar una matriz con sus reglas', () => {
  const open = (extra = {}, account = PLATFORM) => routes(account, extra);

  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => 'blob:matriz');
    URL.revokeObjectURL = vi.fn();
  });

  it('la plataforma exporta la matriz global con sus reglas', async () => {
    const { calls } = open({
      [`GET /matrices/${MID}`]: jsonResponse(200, detail()),
      [`POST /matrices/${MID}/export`]: csvMatrix,
    }, PLATFORM);
    renderAt(`/app/matrices/${MID}`);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Exportar matriz y reglas' }));
    expect(await screen.findByText('Exportación lista: matriz-prueba.csv.')).toBeInTheDocument();
    expect(calls.some((call) => call.key === `POST /matrices/${MID}/export`)).toBe(true);
    expect(URL.createObjectURL).toHaveBeenCalled();
  });

  it('el propietario de una institución exporta su matriz', async () => {
    open({
      [`GET ${BASE}`]: jsonResponse(200, institution('PROPIETARIO')),
      [`GET /matrices/${MID}`]: jsonResponse(200, detail({ ambito: 'INSTITUCION', idInstitucion: ID, nombreInstitucion: 'Centro Médico San José', creadaPor: null })),
      [`POST /matrices/${MID}/export`]: csvMatrix,
    }, INSTITUTIONAL);
    renderAt(`/app/instituciones/${ID}/matrices/${MID}`);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Exportar matriz y reglas' }));
    expect(await screen.findByText('Exportación lista: matriz-prueba.csv.')).toBeInTheDocument();
  });

  it('si la API rechaza la exportación, se informa el motivo y no se descarga nada', async () => {
    open({
      [`GET /matrices/${MID}`]: jsonResponse(200, detail()),
      [`POST /matrices/${MID}/export`]: jsonResponse(404, { codigo: 'MATRIZ_NO_ENCONTRADA', detail: 'No encontramos esa matriz.' }),
    }, PLATFORM);
    renderAt(`/app/matrices/${MID}`);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Exportar matriz y reglas' }));
    expect(await screen.findByText('No encontramos esa matriz.')).toBeInTheDocument();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});
