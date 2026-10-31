// «Conectar dispositivo» (conexión guiada con el puente local).
//
// NO hay Arduino ni puente real: el backend se simula con el MISMO contenido que devuelven el estado en vivo y el diagnóstico
// (GET /acquisition/telemetry/status y /readiness). Estas pruebas verifican que la pantalla muestra lo que el backend informa,
// distingue emparejado / puerto abierto / telemetría / disponible, no ofrece acciones que el navegador no puede ejecutar y solo
// manda al backend órdenes acotadas. Las pruebas con hardware real se describen en docs/PUENTE.md.

import { configure, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { clearTokens, saveTokens } from '../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../test/helpers.js';
import { renderAt } from '../../../test/renderApp.jsx';
import { guideSteps, indicators, nextAction, pipeline } from './connectModel.js';

vi.mock('../../../api/acquisitionApi.js', async (importOriginal) => ({
  ...(await importOriginal()),
  openTelemetryStream: vi.fn(() => () => {}),
}));

configure({ asyncUtilTimeout: 5000 });

const PROFILE_ID = 'p-own';
const OWN_PROFILE = { perfilDisponible: true, datosFaltantes: [], idPerfilMedicion: PROFILE_ID, nombre: 'Victoria', apellido: 'Cortés' };
const BT_PORT = { puerto: 'COM4', descripcion: 'Serie estándar sobre el vínculo Bluetooth (COM4)', esBluetooth: true, esArduino: false, estadoWindows: 'OK' };
const BT_IN = { puerto: 'COM5', descripcion: 'Serie estándar sobre el vínculo Bluetooth (COM5)', esBluetooth: true, esArduino: false, estadoWindows: 'OK' };
const USB_PORT = { puerto: 'COM3', descripcion: 'USB-SERIAL CH340 (COM3)', esBluetooth: false, esArduino: true, estadoWindows: 'OK' };
const BRIDGE = {
  puerto: 'COM4', medio: 'BLUETOOTH', baudios: 9600, codigoDispositivo: 'GL-0001', estadoEnlace: 'CONECTADO', reintento: 0, ultimoError: null,
  codigoError: null, versionPuente: '1.2.0', puertosDisponibles: [BT_PORT, BT_IN, USB_PORT], comandoPendiente: null, ultimoComando: null,
};
const READING = {
  bpm: 76.4, spo2: 99.6, glucosa: 117, unidadGlucosa: 'mg/dL', origen: 'DEMO', esDemo: true, indiceOptico: 2.4, senalValida: true,
  dedo: true, muestras: 58, instante: '2026-10-13T09:00:00Z', edadSegundos: 0.4,
};
const status = (overrides = {}) => ({
  estado: 'CONECTADO', ocupado: false, controlPropio: true, edadUltimaLectura: 0.4, puente: BRIDGE, lectura: READING, avisoDispositivo: null,
  lineasInvalidas: 0, lecturasRecibidas: 30, sesion: null, ...overrides,
});
const STOPPED = status({ estado: 'SIN_PUENTE', puente: null, lectura: null });

const ok = (id, titulo, detalle) => ({ id, titulo, estado: 'OK', detalle, solucion: null });
const step = (id, titulo, estado, detalle, solucion = null) => ({ id, titulo, estado, detalle, solucion });
const READY = {
  listo: true, bloqueo: null, dispositivo: { idDispositivo: 'd-1', codigoDispositivo: 'GL-0001', nombre: 'Arduino', modeloSensor: 'MAX30100' },
  pasos: [ok('PUENTE', 'Servicio puente', 'El puente está ejecutándose (versión 1.2.0).'), ok('PUERTO', 'Puerto abierto', 'Puerto COM4 abierto a 9600 baudios (bluetooth).'),
    ok('TELEMETRIA', 'Telemetría reciente', 'Última lectura hace 0 s.'), ok('SENSOR', 'Sensor', 'El sensor responde.'),
    ok('REGISTRADO', 'Dispositivo registrado', '«GL-0001» figura en el inventario (MAX30100).'),
    ok('ASOCIADO', 'Dispositivo asociado al perfil', 'El perfil puede usar este dispositivo.'),
    ok('DISPONIBLE', 'Disponible para medir', 'Dispositivo listo para medir.')],
};
const readiness = (changes) => ({
  ...READY, listo: false, bloqueo: 'X', dispositivo: null,
  pasos: READY.pasos.map((item) => changes[item.id] ?? item),
});

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

function open(statusBody, readinessBody, extra = {}) {
  const api = mockApi({
    'GET /auth/me': jsonResponse(200, ACCOUNT), 'GET /measurements/profile': jsonResponse(200, OWN_PROFILE),
    'GET /acquisition/telemetry/status': jsonResponse(200, statusBody), 'GET /acquisition/telemetry/readiness': jsonResponse(200, readinessBody), ...extra,
  });
  renderAt('/app/conectar-dispositivo');
  return api;
}

describe('Conectar dispositivo: estado real', () => {
  it('con el puente detenido explica cómo iniciarlo y no ofrece acciones que el navegador no puede ejecutar', async () => {
    open(STOPPED, readiness({ PUENTE: step('PUENTE', 'Servicio puente', 'ERROR', 'El puente de GlucoLume no está ejecutándose.', 'Abrí «Puente GlucoLume».'),
      PUERTO: step('PUERTO', 'Puerto abierto', 'PENDIENTE', 'x'), TELEMETRIA: step('TELEMETRIA', 'Telemetría reciente', 'PENDIENTE', 'x'),
      SENSOR: step('SENSOR', 'Sensor', 'PENDIENTE', 'x') }));
    expect(await screen.findByRole('heading', { name: 'Conectar dispositivo' })).toBeInTheDocument();
    expect(await screen.findByText('El puente de GlucoLume no está ejecutándose')).toBeInTheDocument();
    expect(screen.getByText(/El navegador no puede iniciarlo/)).toBeInTheDocument();
    expect(screen.getAllByText('Instalar-Puente.bat', { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getByText('python acquisition\\bridge\\bridge_ctl.py start')).toBeInTheDocument();
    // Nada de botones de control ni de configurar puerto: no hay a quién dárselos.
    for (const name of [/Detener puente/, /Reiniciar puente/, /Pausar lectura/, /Aplicar puerto/]) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    }
    expect(screen.getByRole('button', { name: 'Medir todavía no está disponible' })).toBeDisabled();
  });

  it('distingue Bluetooth emparejado, puerto abierto, telemetría recibida y disponible; con todo bien, ofrece medir', async () => {
    open(status(), READY);
    expect(await screen.findByText('Dispositivo listo para medir', { selector: 'b' })).toBeInTheDocument();
    const stages = within(screen.getByRole('list', { name: 'Etapas de la conexión' }));
    for (const title of ['Bluetooth emparejado', 'Puerto abierto', 'Telemetría recibida', 'Disponible para medir']) {
      expect(stages.getByText(title)).toBeInTheDocument();
    }
    const grid = within(screen.getByLabelText('Indicadores de la conexión'));
    expect(grid.getByText('Ejecutándose (v1.2.0)')).toBeInTheDocument();
    expect(grid.getByText('9600 baudios')).toBeInTheDocument();
    expect(grid.getByText('COM4')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Ir a «Mis mediciones» para medir/ })).toHaveAttribute('href', '/app/mediciones');
  });

  it('con un dispositivo propio (contexto personal) las órdenes al puente están habilitadas, sin pedir ningún operador', async () => {
    open(status(), { ...READY, ordenesPuente: { contexto: 'PERSONAL', permitido: true, motivo: null } });
    expect(await screen.findByRole('button', { name: /Detener puente/ })).toBeEnabled();
    expect(screen.queryByText(/operador/i, { selector: '[role="status"]' })).not.toBeInTheDocument();
  });

  it('con un dispositivo de una institución ajena bloquea las órdenes y muestra el motivo que decide el backend', async () => {
    const motivo = 'El dispositivo conectado está registrado en una institución, y una cuenta individual no puede darle órdenes al puente.';
    open(status(), { ...READY, listo: false, ordenesPuente: { contexto: 'INSTITUCIONAL_AJENA', permitido: false, motivo } });
    expect(await screen.findByText(motivo)).toBeInTheDocument();
    for (const name of [/Detener puente/, /Reiniciar puente/, /Pausar lectura/, /Aplicar puerto/]) {
      expect(screen.getByRole('button', { name })).toBeDisabled();
    }
  });

  it('en modo automático sin dispositivo muestra la pantalla sin fallar y deja marcado el selector Automático', async () => {
    const searching = { ...BRIDGE, medio: 'AUTO', puerto: null, baudios: null, estadoEnlace: 'DISPOSITIVO_DESCONECTADO', puertosDisponibles: [USB_PORT] };
    open(status({ estado: 'PUERTO_DESCONECTADO', lectura: null, puente: searching }), readiness({}));
    expect(await screen.findByRole('radio', { name: /Automático/ })).toBeChecked();
    expect(screen.queryByText('Algo salió mal')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Guía: Bluetooth/ })).toBeInTheDocument();
  });

  it('elegir Automático desde el selector no rompe la guía y el botón aplica el modo sin puerto', async () => {
    const user = userEvent.setup();
    open(status(), READY);
    await user.click(await screen.findByRole('radio', { name: /Automático/ }));
    expect(screen.queryByText('Algo salió mal')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Guía: Bluetooth/ })).toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: 'Puerto COM' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Aplicar modo automático/ })).toBeEnabled();
  });

  it('un puerto abierto sin telemetría NO es dispositivo listo', async () => {
    open(status({ estado: 'SIN_DATOS', lectura: null }), readiness({
      TELEMETRIA: step('TELEMETRIA', 'Telemetría reciente', 'PENDIENTE', 'El puerto abrió pero todavía no llegan lecturas.', 'Verificá que el Arduino tenga cargado el firmware.'),
      SENSOR: step('SENSOR', 'Sensor', 'PENDIENTE', 'Se comprueba cuando llegue telemetría.'),
      DISPONIBLE: step('DISPONIBLE', 'Disponible para medir', 'PENDIENTE', 'Todavía no.'),
    }));
    expect(await screen.findByText('Telemetría reciente', { selector: 'b' })).toBeInTheDocument();
    expect(screen.getAllByText('El puerto abrió pero todavía no llegan lecturas.').length).toBeGreaterThan(0);
    const stages = within(screen.getByRole('list', { name: 'Etapas de la conexión' }));
    expect(stages.getByText('Puerto abierto').closest('li')).toHaveClass('is-ok');
    expect(stages.getByText('Telemetría recibida').closest('li')).toHaveClass('is-pending');
    expect(stages.getByText('Disponible para medir').closest('li')).not.toHaveClass('is-ok');
    expect(screen.queryByRole('link', { name: /Ir a «Mis mediciones»/ })).not.toBeInTheDocument();
  });

  it('puerto ocupado por otra aplicación: lo dice con el puerto y cómo resolverlo', async () => {
    const busy = status({ estado: 'PUERTO_DESCONECTADO', lectura: null, puente: { ...BRIDGE, estadoEnlace: 'REINTENTANDO', codigoError: 'PUERTO_OCUPADO', reintento: 2 } });
    open(busy, readiness({
      PUERTO: step('PUERTO', 'Puerto abierto', 'ERROR', 'Puerto COM4 ocupado por otra aplicación.', 'Cerrá el Monitor Serie del Arduino IDE, PuTTY o miniterm.'),
    }));
    expect(await screen.findByText('Puerto COM4 ocupado por otra aplicación', { selector: 'b' })).toBeInTheDocument();
    expect(screen.getByText(/Cerrá el Monitor Serie del Arduino IDE/, { selector: 'p' })).toBeInTheDocument();
  });

  it('Bluetooth no emparejado (el puerto configurado no existe): lo dice sin asumir ningún COM', async () => {
    const missing = status({ estado: 'PUERTO_DESCONECTADO', lectura: null,
      puente: { ...BRIDGE, puerto: 'COM9', estadoEnlace: 'REINTENTANDO', codigoError: 'PUERTO_INEXISTENTE' } });
    open(missing, readiness({
      PUERTO: step('PUERTO', 'Puerto abierto', 'ERROR', 'El puerto COM9 no existe en este equipo.', 'Conectá el Arduino (o emparejá el Bluetooth).'),
    }));
    expect(await screen.findByText('Bluetooth no emparejado', { selector: 'b' })).toBeInTheDocument();
  });

  it('dispositivo conectado pero no asociado a este perfil', async () => {
    open(status(), readiness({
      ASOCIADO: step('ASOCIADO', 'Dispositivo asociado al perfil', 'ERROR', 'El dispositivo está conectado, pero todavía no está asociado a este perfil: no está operativo.', 'Pedí a la administración que lo deje operativo.'),
    }));
    expect(await screen.findByText(/está conectado, pero todavía no está asociado a este perfil/, { selector: 'b' })).toBeInTheDocument();
    expect(screen.getByText('Pedí a la administración que lo deje operativo.', { exact: false })).toBeInTheDocument();
  });
});

describe('Conectar dispositivo: guías', () => {
  it('Bluetooth muestra 10 pasos a 9600 baudios y USB 9 pasos a 115200, sin fijar ningún puerto', async () => {
    const user = userEvent.setup();
    open(status({ estado: 'SIN_PUENTE', puente: null, lectura: null }), READY);
    await screen.findByRole('heading', { name: /Elegí cómo conectar/ });
    const bluetooth = screen.getByRole('list', { name: 'Pasos de la conexión por Bluetooth' });
    expect(within(bluetooth).getAllByRole('listitem')).toHaveLength(10);
    expect(within(bluetooth).getByText(/Usá 9600 baudios/)).toBeInTheDocument();
    await user.click(screen.getByRole('radio', { name: /Conexión por USB/ }));
    const usb = screen.getByRole('list', { name: 'Pasos de la conexión por USB' });
    expect(within(usb).getAllByRole('listitem')).toHaveLength(9);
    expect(within(usb).getByText(/Usá 115200 baudios/)).toBeInTheDocument();
    expect(within(usb).getByText(/Un cable solo de carga no funciona/)).toBeInTheDocument();
    expect(document.querySelector('.guide-steps')?.textContent).not.toMatch(/COM[0-9]/);
  });

  it('los pasos que solo hace la persona no llevan marca de comprobado', () => {
    const steps = guideSteps('BLUETOOTH', status(), READY);
    expect(steps[0].estado).toBe('MANUAL');
    expect(steps[1].estado).toBe('MANUAL');
    expect(steps.at(-1).estado).toBe('OK');
    expect(guideSteps('USB', STOPPED, null).filter((item) => item.estado === 'OK')).toHaveLength(0);
  });

  it('USB: avisa si Windows reporta el adaptador en estado Unknown (controlador)', () => {
    const unknown = status({ puente: { ...BRIDGE, medio: 'USB', puerto: 'COM3', baudios: 115200, puertosDisponibles: [{ ...USB_PORT, estadoWindows: 'Unknown' }] } });
    const steps = guideSteps('USB', unknown, READY);
    expect(steps[1].estado).toBe('ERROR');
    expect(steps[1].detalle).toMatch(/Windows informa el estado «Unknown» para COM3/);
  });

  it('la velocidad que no corresponde al medio se marca (Bluetooth a 115200)', () => {
    const wrong = status({ puente: { ...BRIDGE, baudios: 115200 } });
    expect(indicators(wrong, READY).find((row) => row.id === 'VELOCIDAD')).toMatchObject({ state: 'ERROR' });
    expect(indicators(status(), READY).find((row) => row.id === 'VELOCIDAD')).toMatchObject({ state: 'OK', value: '9600 baudios' });
  });

  it('muestra la guía «Cómo realizar una medición» con los 10 pasos y la guía del dedo', async () => {
    open(status(), READY);
    const guide = await screen.findByRole('list', { name: 'Pasos para medir' });
    expect(within(guide).getAllByRole('listitem')).toHaveLength(10);
    expect(within(guide).getByText(/Hacen falta 8 lecturas válidas consecutivas/)).toBeInTheDocument();
    expect(within(guide).getByText(/Identificá el origen del dato/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Cómo colocar el dedo en el MAX30100/ })).toBeInTheDocument();
    expect(screen.getByText(/DEMO son valores sintéticos/)).toBeInTheDocument();
  });
});

describe('Conectar dispositivo: configuración del puente (solo lo que el puente puede aplicar)', () => {
  it('elige un puerto entre los que el puente ve y pide CONFIGURAR con el medio; no hay campo libre de puerto', async () => {
    const user = userEvent.setup();
    const { calls } = open(status(), READY, { 'POST /acquisition/bridge/command': jsonResponse(200, status({ puente: { ...BRIDGE, comandoPendiente: 'CONFIGURAR' } })) });
    const select = await screen.findByLabelText('Puerto COM');
    expect(within(select).getAllByRole('option').map((option) => option.value)).toEqual(['', 'COM4', 'COM5', 'COM3']);
    expect(screen.queryByRole('textbox', { name: /Puerto/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole('radio', { name: /USB \(115200 baudios\)/ }));
    await user.selectOptions(select, 'COM3');
    await user.click(screen.getByRole('button', { name: /Aplicar puerto y medio/ }));
    expect(calls.find((call) => call.key === 'POST /acquisition/bridge/command').body).toEqual({ accion: 'CONFIGURAR', puerto: 'COM3', medio: 'USB' });
  });

  it('pausar, reanudar, reiniciar y detener piden solo su acción; detener y reiniciar piden confirmación', async () => {
    const user = userEvent.setup();
    const { calls } = open(status(), READY, { 'POST /acquisition/bridge/command': jsonResponse(200, status()) });
    await user.click(await screen.findByRole('button', { name: /Pausar lectura/ }));
    await user.click(screen.getByRole('button', { name: /Detener puente/ }));
    expect(calls.filter((call) => call.key === 'POST /acquisition/bridge/command').map((call) => call.body)).toEqual([{ accion: 'PAUSAR' }]);
    const dialog = screen.getByRole('alertdialog', { name: /Detener el puente/ });
    await user.click(within(dialog).getByRole('button', { name: 'Detener' }));
    expect(calls.filter((call) => call.key === 'POST /acquisition/bridge/command').map((call) => call.body)).toEqual([{ accion: 'PAUSAR' }, { accion: 'DETENER' }]);
  });

  it('en pausa ofrece reanudar', async () => {
    open(status({ puente: { ...BRIDGE, estadoEnlace: 'PAUSADO' }, estado: 'PUERTO_DESCONECTADO', lectura: null }), readiness({}));
    expect(await screen.findByRole('button', { name: /Reanudar lectura/ })).toBeEnabled();
    expect(screen.queryByRole('button', { name: /Pausar lectura/ })).not.toBeInTheDocument();
  });

  it('no deja tocar el puente durante una sesión de medición', async () => {
    open(status({ sesion: { idMedicion: 'm-1', iniciada: 'x', enlacePerdido: false, estabilidad: null } }), READY);
    expect(await screen.findByText(/Hay una sesión de medición en curso/)).toBeInTheDocument();
    for (const name of [/Aplicar puerto y medio/, /Detener puente/, /Reiniciar puente/, /Pausar lectura/]) {
      expect(screen.getByRole('button', { name })).toBeDisabled();
    }
  });

  it('muestra el resultado de la última orden que informó el puente', async () => {
    open(status({ puente: { ...BRIDGE, ultimoComando: { id: 'a', ok: true, mensaje: 'Ahora lee COM3 a 115200 baudios (usb).' } } }), READY);
    expect(await screen.findByText('Ahora lee COM3 a 115200 baudios (usb).')).toBeInTheDocument();
  });

  it('sin el control ofrece «Usar dispositivo», bloquea las órdenes y lo toma solo cuando la persona lo pide', async () => {
    const user = userEvent.setup();
    const { calls } = open(status({ controlPropio: false, lectura: null }), READY, { 'POST /acquisition/telemetry/control': jsonResponse(200, status()) });
    expect(await screen.findByText(/Tocá «Usar dispositivo» para darle órdenes al puente/)).toBeInTheDocument();
    for (const name of [/Aplicar puerto y medio/, /Detener puente/, /Reiniciar puente/, /Pausar lectura/]) {
      expect(screen.getByRole('button', { name })).toBeDisabled();
    }
    expect(calls.some((call) => call.key === 'POST /acquisition/telemetry/control')).toBe(false);
    await user.click(screen.getByRole('button', { name: 'Usar dispositivo' }));
    expect(calls.filter((call) => call.key === 'POST /acquisition/telemetry/control')).toHaveLength(1);
  });

  it('si otra cuenta lo está usando no ofrece tomarlo y explica por qué', async () => {
    open(status({ controlPropio: false, ocupado: true, lectura: null }), READY);
    expect(await screen.findByText(/Otra cuenta está usando el dispositivo/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Usar dispositivo' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Pausar lectura/ })).toBeDisabled();
  });

  it('con el control y sin medición permite dejar de usarlo', async () => {
    const user = userEvent.setup();
    const { calls } = open(status(), READY, { 'DELETE /acquisition/telemetry/control': jsonResponse(200, status({ controlPropio: false, lectura: null })) });
    await user.click(await screen.findByRole('button', { name: 'Dejar de usar' }));
    expect(calls.filter((call) => call.key === 'DELETE /acquisition/telemetry/control')).toHaveLength(1);
  });

  it('muestra el error del backend (p. ej. otra orden pendiente) sin ocultarlo', async () => {
    const user = userEvent.setup();
    open(status(), READY, { 'POST /acquisition/bridge/command': jsonResponse(409, { codigo: 'COMANDO_PENDIENTE', detail: 'Hay otra orden esperando al puente.' }) });
    await user.click(await screen.findByRole('button', { name: /Pausar lectura/ }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });
});

describe('Conectar dispositivo: modelo', () => {
  it('Windows reconoce el puerto Bluetooth solo si el seleccionado está entre los que informó el puente', () => {
    expect(pipeline(status(), READY, 'BLUETOOTH')[0]).toMatchObject({ title: 'Bluetooth emparejado', state: 'OK' });
    const absent = status({ puente: { ...BRIDGE, puerto: 'COM9' } });
    expect(pipeline(absent, READY, 'BLUETOOTH')[0].state).toBe('ERROR');
    expect(pipeline(STOPPED, null, 'BLUETOOTH')[0].state).toBe('PENDIENTE');
  });

  it('la acción siguiente prioriza el primer paso pendiente y nunca dice «listo» sin que el backend lo confirme', () => {
    expect(nextAction(STOPPED, null, 'USB').title).toBe('El puente de GlucoLume no está ejecutándose');
    expect(nextAction(status(), READY, 'BLUETOOTH').kind).toBe('success');
    const pending = readiness({ TELEMETRIA: step('TELEMETRIA', 'Telemetría reciente', 'PENDIENTE', 'Sin lecturas.') });
    expect(nextAction(status(), pending, 'BLUETOOTH')).toMatchObject({ kind: 'info', title: 'Telemetría reciente' });
  });
});
