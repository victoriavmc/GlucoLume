// Conexión del Arduino desde el navegador (Web Serial). NO hay Arduino ni navegador real: `fakePort` entrega bytes como los del firmware y el
// backend se reemplaza por `send`. Se verifica lo que importa: velocidad por medio, armado de líneas, reenvío sin duplicar, cierre y errores.

import { describe, expect, it, vi } from 'vitest';

import { STATES, createBrowserLink, describeSerialError } from './browserSerialLink.js';

const encoder = new TextEncoder();

function fakePort() {
  const chunks = [];
  let waiting = null;
  let failure = null;
  const reader = {
    read: () => new Promise((resolve, reject) => {
      if (failure) return reject(failure);
      if (chunks.length) return resolve({ value: encoder.encode(chunks.shift()), done: false });
      waiting = { resolve, reject };
      return undefined;
    }),
    cancel: async () => { waiting?.resolve({ done: true }); waiting = null; },
    releaseLock: () => { port.locked = false; },
  };
  const port = {
    readable: null, closed: false, opened: null, locked: false,
    getInfo: () => ({ usbVendorId: 0x2341, usbProductId: 0x43 }),
    open: vi.fn(async (options) => { port.opened = options; port.readable = { getReader: () => { port.locked = true; return reader; } }; }),
    // Como el real: cerrar con el lector todavía bloqueado falla.
    close: vi.fn(async () => { if (port.locked) throw new TypeError('The readable stream is locked'); port.closed = true; port.readable = null; }),
    push(text) {
      if (waiting) { waiting.resolve({ value: encoder.encode(text), done: false }); waiting = null; } else chunks.push(text);
    },
    noise(error) { // error recuperable (FramingError...): el puerto sigue legible y el lector vuelve a leer
      if (waiting) { waiting.reject(error); waiting = null; }
    },
    lose(error = Object.assign(new Error('lost'), { name: 'NetworkError' })) {
      port.readable = null;
      if (waiting) { waiting.reject(error); waiting = null; } else failure = error;
    },
  };
  return port;
}

function setup({ port = fakePort(), send = vi.fn(async () => ({})), requestPort } = {}) {
  const clock = { now: 1_000_000 };
  let tick = () => {};
  const serial = { requestPort: requestPort ?? vi.fn(async () => port), addEventListener: vi.fn(), removeEventListener: vi.fn() };
  const link = createBrowserLink({
    serial: () => serial, send, now: () => clock.now, newId: () => 'link-1',
    setTimer: (fn) => { tick = fn; return 1; }, clearTimer: vi.fn(),
  });
  return { link, port, send, serial, clock, tick: () => tick() };
}

const sent = (send, index = 0) => send.mock.calls[index][0];
const settle = () => vi.waitFor(() => expect(true).toBe(true));

describe('abrir el puerto', () => {
  it('abre a 115200 por USB y a 9600 por Bluetooth, en solo lectura', async () => {
    for (const [medium, baud] of [['USB', 115200], ['BLUETOOTH', 9600]]) {
      const { link, port } = setup();
      await link.connect(medium);
      expect(port.opened).toEqual({ baudRate: baud });
      expect(link.getSnapshot().estado).toBe(STATES.CONNECTED);
      expect('write' in port || 'writable' in port).toBe(false); // nunca se le escribe al Arduino
      await link.disconnect();
    }
  });

  it('cancelar el selector no es un error', async () => {
    const { link } = setup({ requestPort: vi.fn(async () => { throw Object.assign(new Error('x'), { name: 'NotFoundError' }); }) });
    await link.connect('USB');
    expect(link.getSnapshot()).toMatchObject({ estado: STATES.IDLE, error: null });
  });

  it('un puerto ocupado se explica sin jerga', async () => {
    const port = fakePort();
    port.open = vi.fn(async () => { throw Object.assign(new Error('Failed to open'), { name: 'NetworkError' }); });
    const { link } = setup({ port });
    await link.connect('USB');
    expect(link.getSnapshot().estado).toBe(STATES.ERROR);
    expect(link.getSnapshot().error).toMatch(/Monitor Serie/);
  });

  it('rechaza un medio desconocido', async () => {
    const { link } = setup();
    await expect(link.connect('AUTO')).rejects.toThrow();
  });
});

describe('entrega al backend', () => {
  it('arma las líneas completas aunque lleguen partidas, con seq creciente y su antigüedad', async () => {
    const { link, port, send, clock, tick } = setup();
    await link.connect('USB');
    await vi.waitFor(() => expect(send).toHaveBeenCalledTimes(1)); // latido inicial sin líneas
    expect(sent(send)).toMatchObject({ idEnlace: 'link-1', medio: 'USB', baudios: 115200, estadoEnlace: 'CONECTADO', nombrePuerto: 'USB 2341:0043', lineas: [] });
    port.push('GLUCOLUME,ID=ARD-0');
    port.push('01,SENSOR=MAX30100\r\nBPM:72.00,SpO2:98.00\r\n\r\nSegunda');
    await vi.waitFor(() => expect(link.getSnapshot().estado).toBe(STATES.CONNECTED));
    await settle();
    clock.now += 400;
    tick();
    await vi.waitFor(() => expect(send).toHaveBeenCalledTimes(2));
    expect(sent(send, 1).lineas).toEqual([
      { seq: 0, edadMs: 400, texto: 'GLUCOLUME,ID=ARD-001,SENSOR=MAX30100' },
      { seq: 1, edadMs: 400, texto: 'BPM:72.00,SpO2:98.00' },
    ]); // «Segunda» sigue esperando su salto de línea
    await link.disconnect();
  });

  it('si el envío falla conserva las líneas y las reenvía con los mismos seq', async () => {
    const send = vi.fn()
      .mockResolvedValueOnce({}) // latido inicial
      .mockRejectedValueOnce(Object.assign(new Error('red'), { codigo: 'ERROR_DE_RED' }))
      .mockResolvedValue({});
    const { link, port, clock, tick } = setup({ send });
    await link.connect('USB');
    await vi.waitFor(() => expect(send).toHaveBeenCalledTimes(1));
    port.push('BPM:72.00\n');
    await settle();
    clock.now += 1000;
    tick();
    await vi.waitFor(() => expect(link.getSnapshot().error).toMatch(/Sin comunicación con el servidor/));
    clock.now += 1000;
    tick();
    await vi.waitFor(() => expect(send).toHaveBeenCalledTimes(3));
    expect(sent(send, 2).lineas.map((line) => line.seq)).toEqual([0]);
    await vi.waitFor(() => expect(link.getSnapshot().error).toBeNull());
    expect(link.getSnapshot().lineasEnviadas).toBe(1);
    await link.disconnect();
  });

  it('si otro puente o navegador ya atiende el dispositivo, cierra el puerto y lo explica', async () => {
    const send = vi.fn().mockRejectedValue(Object.assign(new Error('Ya hay otro puente serie activo para este dispositivo.'), { codigo: 'PUENTE_DUPLICADO', status: 409 }));
    const { link, port } = setup({ send });
    await link.connect('USB');
    await vi.waitFor(() => expect(link.getSnapshot().estado).toBe(STATES.ERROR));
    expect(link.getSnapshot().error).toMatch(/otro puente u otro navegador/);
    await vi.waitFor(() => expect(port.closed).toBe(true));
  });

  it('avisa que sigue vivo cada pocos segundos aunque no lleguen líneas', async () => {
    const { link, send, clock, tick } = setup();
    await link.connect('USB');
    await vi.waitFor(() => expect(send).toHaveBeenCalledTimes(1));
    clock.now += 1000;
    tick();
    await settle();
    expect(send).toHaveBeenCalledTimes(1); // todavía no toca
    clock.now += 2500;
    tick();
    await vi.waitFor(() => expect(send).toHaveBeenCalledTimes(2));
    await link.disconnect();
  });
});

describe('cerrar y perder la conexión', () => {
  it('desconectar libera el puerto y le avisa al backend para que no espere 10 s', async () => {
    const { link, port, send } = setup();
    await link.connect('USB');
    await vi.waitFor(() => expect(send).toHaveBeenCalledTimes(1));
    await link.disconnect();
    expect(port.closed).toBe(true); // se cerró de verdad: el lector ya estaba suelto
    expect(link.getSnapshot().estado).toBe(STATES.IDLE);
    expect(sent(send, send.mock.calls.length - 1)).toMatchObject({ detenido: true, estadoEnlace: 'DESCONECTADO' });
  });

  it('si se desenchufa el Arduino queda en error, cierra y avisa al backend', async () => {
    const { link, port, send } = setup();
    await link.connect('USB');
    await vi.waitFor(() => expect(send).toHaveBeenCalledTimes(1));
    port.lose();
    await vi.waitFor(() => expect(link.getSnapshot().estado).toBe(STATES.ERROR));
    expect(link.getSnapshot().error).toMatch(/Se perdió la conexión con el Arduino/);
    await vi.waitFor(() => expect(send.mock.calls.some(([body]) => body.estadoEnlace === 'DESCONECTADO')).toBe(true));
    expect(port.closed).toBe(true);
  });

  it('un error de ruido recuperable no corta la lectura', async () => {
    const { link, port } = setup();
    await link.connect('USB');
    await vi.waitFor(() => expect(link.getSnapshot().estado).toBe(STATES.CONNECTED));
    port.noise(Object.assign(new Error('framing'), { name: 'FramingError' }));
    await settle();
    port.push('BPM:72.00\n'); // después del ruido la lectura continúa
    await vi.waitFor(() => expect(link.getSnapshot().estado).toBe(STATES.CONNECTED));
    expect(port.closed).toBe(false);
    await link.disconnect();
  });
});

describe('mensajes', () => {
  it('no inventa un error cuando la persona cierra el selector', () => {
    expect(describeSerialError(Object.assign(new Error('x'), { name: 'NotFoundError' }), 'pick')).toBeNull();
    expect(describeSerialError(Object.assign(new Error('x'), { name: 'SecurityError' }))).toMatch(/Chrome o Edge/);
  });
});
