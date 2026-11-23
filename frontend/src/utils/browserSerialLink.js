// Lectura del Arduino DESDE EL NAVEGADOR (Web Serial), sin instalar el puente.
//
// Hace lo mismo que el puente de Windows (backend/acquisition/bridge): abre el puerto en solo lectura, junta las líneas que escribe el firmware
// y se las entrega al backend (POST /acquisition/browser/ingest) con la sesión de la cuenta. No interpreta ni calcula nada: BPM, SpO₂, glucosa e
// identidad del Arduino los valida el backend. NUNCA escribe en el Arduino.
//
// Es un módulo único (no un hook por pantalla) para que la conexión siga viva al navegar dentro de GlucoLume, por ejemplo de «Conectar dispositivo»
// a «Mis mediciones». Si se cierra o recarga la pestaña, el puerto se cierra y el backend da el dispositivo por desconectado a los 10 s.
//
// Requisitos del navegador: Chrome o Edge de escritorio, en HTTPS (o localhost), y un gesto de la persona (el botón) para elegir el puerto.

import { useSyncExternalStore } from 'react';

import * as acquisitionApi from '../api/acquisitionApi.js';

export const BAUD = { USB: 115200, BLUETOOTH: 9600 };
export const STATES = { IDLE: 'INACTIVO', CONNECTING: 'CONECTANDO', CONNECTED: 'CONECTADO', ERROR: 'ERROR' };

const TICK_MS = 1000; // cada cuánto se revisa si hay algo para enviar
const HEARTBEAT_MS = 3000; // sin líneas, igual se avisa que el enlace sigue vivo (el backend lo da por caído a los 10 s)
const BATCH = 200; // tope del backend por pedido
const MAX_QUEUE = 1000; // sin servidor se conservan las últimas líneas; las más viejas se descartan
const MAX_LINE = 512;
const MAX_PARTIAL = 2048; // texto sin salto de línea: es ruido, no una línea del firmware
const MAX_AGE_MS = 86_400_000;
// Abrir el puerto NO prueba que haya un Arduino: el Bluetooth puede abrir aunque el equipo esté apagado. Solo cuenta una línea del firmware.
// El firmware informa GLUCOLUME,ID=… al arrancar y cada 10 s (ID_PERIOD_MS): la espera tiene que cubrir ese período, si no el puerto
// se cierra justo antes de la siguiente identificación (igual que PROBE_SECONDS = 12 s en el puente de Python).
const IDENTIFY_TIMEOUT_MS = 15000;
// Un enlace anterior (pestaña recién cerrada o recargada, o un puente que se detuvo) figura activo hasta 10 s sin latidos en el servidor. Durante
// esa ventana el 409 PUENTE_DUPLICADO no es definitivo: se reintenta solo, sin pedirle al cliente que toque nada de nuevo.
const TAKEOVER_WAIT_MS = 15000;
const DEVICE_PREFIXES = ['GLUCOLUME,', 'ST,', 'S,', 'ERR,', 'PONG']; // única evidencia de que el firmware de GlucoLume está hablando

function isDeviceLine(text) {
  return DEVICE_PREFIXES.some((prefix) => text.startsWith(prefix));
}

export const webSerialSupported = () => typeof navigator !== 'undefined' && 'serial' in navigator
  && (typeof window === 'undefined' || window.isSecureContext !== false);

// Filtros del selector del navegador: que solo aparezca el puerto que corresponde al medio elegido (sin COM1, COM4, etc.).
// Bluetooth: el puerto SPP («Serie estándar sobre Bluetooth») del HC-05/HC-06 emparejado. USB: adaptadores habituales del Arduino UNO
// (oficial 0x2341, clones con CH340 0x1A86, CP210x 0x10C4, FTDI 0x0403, Arduino.org 0x2A03).
const SERIAL_PORT_PROFILE = '00001101-0000-1000-8000-00805f9b34fb';
const PICKER_FILTERS = {
  BLUETOOTH: [{ bluetoothServiceClassId: SERIAL_PORT_PROFILE }],
  USB: [0x2341, 0x1a86, 0x10c4, 0x0403, 0x2a03].map((usbVendorId) => ({ usbVendorId })),
};
// Sin medio elegido de antemano: el selector muestra los dos tipos y el medio se reconoce del puerto que la persona elige.
const PICKER_FILTERS_ANY = [...PICKER_FILTERS.USB, ...PICKER_FILTERS.BLUETOOTH];

/** Reconoce el medio del puerto elegido: el USB informa su id de fabricante; el puerto SPP del Bluetooth no informa ids USB. */
export const detectMedium = (port) => (port?.getInfo?.()?.usbVendorId ? 'USB' : 'BLUETOOTH');

const hex = (value) => value.toString(16).padStart(4, '0');

// Reconexión automática: se recuerda solo el medio y los ids USB del último puerto elegido (nada del sensor ni de la persona).
// Con eso el navegador devuelve ese mismo puerto sin mostrar el selector, porque ya tiene permiso para él.
const REMEMBERED_KEY = 'glucolume.puertoSerie';

function rememberPort(port, medium) {
  try {
    const info = port?.getInfo?.() ?? {};
    localStorage.setItem(REMEMBERED_KEY, JSON.stringify({ medium, usbVendorId: info.usbVendorId, usbProductId: info.usbProductId }));
  } catch { /* sin almacenamiento: la próxima vez se pide el puerto */ }
}

function readRemembered() {
  try {
    const saved = JSON.parse(localStorage.getItem(REMEMBERED_KEY) ?? 'null');
    return saved && BAUD[saved.medium] ? saved : null;
  } catch {
    return null;
  }
}

function matchesRemembered(port, saved) {
  const info = port?.getInfo?.() ?? {};
  if (saved.medium === 'BLUETOOTH') return !info.usbVendorId; // el puerto SPP del Bluetooth no informa ids USB
  return info.usbVendorId === saved.usbVendorId && info.usbProductId === saved.usbProductId;
}

function portLabel(port, medium) {
  const info = port?.getInfo?.() ?? {};
  if (medium === 'BLUETOOTH') return 'Bluetooth (puerto emparejado)';
  return info.usbVendorId ? `USB ${hex(info.usbVendorId)}:${hex(info.usbProductId ?? 0)}` : 'USB';
}

/** Mensaje para quien no sabe qué es un NetworkError. `kind`: dónde falló. */
export function describeSerialError(error, kind = 'open') {
  const name = error?.name;
  if (name === 'NotFoundError') return null; // eligió «Cancelar» en el selector: no es un error
  if (name === 'SecurityError') return 'El navegador bloqueó el acceso a los puertos: usá Chrome o Edge en una página segura (HTTPS) y permití el acceso al dispositivo.';
  if (kind === 'open') {
    if (name === 'InvalidStateError') return 'Ese puerto ya está abierto en esta pestaña: desconectalo e intentá de nuevo.';
    return 'No se pudo abrir el puerto. Cerrá el Monitor Serie del Arduino IDE, PuTTY u otro programa que lo use, revisá el cable (de datos, no solo de carga) y probá de nuevo.';
  }
  return 'Se perdió la conexión con el Arduino. Revisá el cable USB o el Bluetooth y volvé a conectar.';
}

function describeSendError(error) {
  if (error?.codigo === 'PUENTE_DUPLICADO') {
    return 'Ya hay otro puente u otro navegador conectado al dispositivo. Cerralo (o esperá unos segundos) y volvé a conectar.';
  }
  return error?.message || 'No se pudo enviar al servidor.';
}

/**
 * `deps` se inyecta solo en las pruebas: serial (navigator.serial), send (POST al backend), now (ms), newId, setTimer/clearTimer.
 */
export function createBrowserLink(deps = {}) {
  const getSerial = deps.serial ?? (() => navigator.serial);
  const send = deps.send ?? ((body) => acquisitionApi.sendBrowserIngest(body));
  const now = deps.now ?? (() => Date.now());
  const newId = deps.newId ?? (() => crypto.randomUUID());
  const setTimer = deps.setTimer ?? ((fn, ms) => setInterval(fn, ms));
  const clearTimer = deps.clearTimer ?? ((handle) => clearInterval(handle));

  const listeners = new Set();
  let snapshot = { estado: STATES.IDLE, medio: null, puerto: null, error: null, verificado: false, lineasEnviadas: 0, ultimoEnvio: null };
  let run = null; // conexión en curso: { id, port, medium, label, seq, queue, timer, reader, loop, exiting, closing, lastSent, inFlight, onDisconnect }

  const emit = (changes) => {
    snapshot = { ...snapshot, ...changes };
    listeners.forEach((listener) => listener());
  };

  const body = (current, lines, extra = {}) => ({
    idEnlace: current.id, medio: current.medium, baudios: BAUD[current.medium], nombrePuerto: current.label,
    estadoEnlace: 'CONECTADO', lineas: lines, ...extra,
  });

  function enqueue(current, text) {
    current.queue.push({ seq: current.seq, text: text.slice(0, MAX_LINE), at: now() });
    current.seq += 1;
    if (current.queue.length > MAX_QUEUE) current.queue.splice(0, current.queue.length - MAX_QUEUE);
  }

  /** El firmware sí habló: recién ahora el enlace es «Arduino reconocido». */
  function markVerified(current) {
    current.verified = true;
    if (run === current) emit({ estado: STATES.CONNECTED, verificado: true, error: null });
  }

  /** Puerto abierto sin ninguna línea del firmware: no se da por reconocido y se cierra con una explicación. */
  function checkIdentity(current) {
    if (current.verified || current.closing || now() - current.openedAt < IDENTIFY_TIMEOUT_MS) return;
    shutdown(current, { estado: STATES.ERROR, error: 'El puerto se abrió, pero el Arduino no envió datos. Encendelo o pulsá su botón de reinicio (RESET) y verificá que tenga el firmware de GlucoLume y la velocidad correcta (9600 Bluetooth, 115200 USB).' }, true);
  }

  async function flush(current) {
    if (current.inFlight || current.closing) return;
    if (!current.queue.length && now() - current.lastSent < HEARTBEAT_MS) return;
    current.inFlight = true;
    const batch = current.queue.slice(0, BATCH);
    const at = now();
    try {
      await send(body(current, batch.map((line) => ({ seq: line.seq, edadMs: Math.min(MAX_AGE_MS, Math.max(0, Math.round(at - line.at))), texto: line.text }))));
      if (run !== current) return;
      current.queue.splice(0, batch.length); // solo se descarta lo confirmado: un reintento reenvía los mismos `seq` y el backend no duplica
      current.lastSent = now();
      emit({ lineasEnviadas: snapshot.lineasEnviadas + batch.length, ultimoEnvio: current.lastSent, error: null });
    } catch (error) {
      if (run !== current) return;
      if (error?.codigo === 'PUENTE_DUPLICADO' && now() - current.openedAt < TAKEOVER_WAIT_MS) {
        emit({ error: 'El enlace anterior de este equipo todavía se está cerrando: GlucoLume reintenta solo.' });
        return;
      }
      if (error?.codigo === 'PUENTE_DUPLICADO' || error?.status === 401 || error?.status === 403) {
        await shutdown(current, { estado: STATES.ERROR, error: describeSendError(error) }, false);
      } else {
        emit({ error: 'Sin comunicación con el servidor: se reintenta solo.' });
      }
    } finally {
      current.inFlight = false;
    }
  }

  async function readLoop(current) {
    const decoder = new TextDecoder();
    let partial = '';
    let fatal = null;
    while (current.port.readable && !current.closing) {
      const reader = current.port.readable.getReader();
      current.reader = reader;
      try {
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          partial += decoder.decode(value, { stream: true });
          let index = partial.indexOf('\n');
          while (index >= 0) {
            const text = partial.slice(0, index).replace(/\r$/, '');
            partial = partial.slice(index + 1);
            if (text.trim()) {
              if (!current.verified && isDeviceLine(text)) markVerified(current);
              enqueue(current, text);
            }
            index = partial.indexOf('\n');
          }
          if (partial.length > MAX_PARTIAL) partial = '';
        }
      } catch (error) {
        // Errores recuperables (ruido de línea): port.readable sigue vivo y el ciclo vuelve a leer. Un NetworkError lo deja en null: se corta.
        if (!current.closing && !current.port.readable) fatal = error;
      } finally {
        reader.releaseLock();
        current.reader = null;
      }
    }
    if (!current.closing && run === current) {
      current.exiting = true; // ya soltó el lector: shutdown no tiene que esperar a este mismo ciclo
      await shutdown(current, { estado: STATES.ERROR, error: describeSerialError(fatal, 'read') }, true);
    }
  }

  /** Cierra el puerto y deja el estado indicado. `notify`: avisa al backend que el enlace se cortó (si no, ya lo sabe o no se puede). */
  async function shutdown(current, next, notify) {
    if (current.closing) return;
    current.closing = true;
    clearTimer(current.timer);
    getSerial()?.removeEventListener?.('disconnect', current.onDisconnect);
    if (run === current) run = null;
    emit({ ...next, puerto: null, verificado: false });
    try { await current.reader?.cancel(); } catch { /* ya estaba cerrado */ }
    // port.close() falla con el lector bloqueado: se espera a que el ciclo de lectura lo suelte (salvo que sea él quien está cerrando).
    if (!current.exiting) { try { await current.loop; } catch { /* sin lector que esperar */ } }
    try { await current.port.close(); } catch { /* el dispositivo ya no está */ }
    if (notify) {
      try { await send(body(current, [], { estadoEnlace: 'DESCONECTADO', detenido: true, error: (next.error ?? '').slice(0, 200) || undefined })); } catch { /* el backend lo da por caído solo */ }
    }
  }

  /** Sin `medium` se muestran USB y Bluetooth en el selector y el medio se reconoce del puerto elegido. Con `medium` se limita a ese tipo. */
  async function connect(medium) {
    if (run || snapshot.estado === STATES.CONNECTING) return;
    if (medium !== undefined && !BAUD[medium]) throw new Error('Medio inválido');
    const serial = getSerial();
    if (!serial) {
      emit({ estado: STATES.ERROR, error: 'Este navegador no puede leer puertos serie. Usá Chrome o Edge en una computadora.' });
      return;
    }
    emit({ estado: STATES.CONNECTING, medio: medium ?? null, error: null, lineasEnviadas: 0, ultimoEnvio: null });
    let port;
    try {
      port = await serial.requestPort({
        filters: medium ? PICKER_FILTERS[medium] : PICKER_FILTERS_ANY,
        allowedBluetoothServiceClassIds: [SERIAL_PORT_PROFILE],
      });
    } catch (error) {
      const message = describeSerialError(error, 'pick');
      emit({ estado: message ? STATES.ERROR : STATES.IDLE, error: message });
      return;
    }
    await openAndRun(port, medium ?? detectMedium(port), false);
  }

  /** Abre el puerto ya elegido y arranca la lectura. `quiet`: en la reconexión automática un fallo no muestra error, queda inactiva. */
  async function openAndRun(port, medium, quiet) {
    try {
      await port.open({ baudRate: BAUD[medium] });
    } catch (error) {
      emit(quiet ? { estado: STATES.IDLE, error: null } : { estado: STATES.ERROR, error: describeSerialError(error, 'open') });
      return false;
    }
    rememberPort(port, medium);
    const current = { id: newId(), port, medium, label: portLabel(port, medium), seq: 0, queue: [], timer: null, reader: null, closing: false,
      lastSent: Number.NEGATIVE_INFINITY, inFlight: false, onDisconnect: null, loop: null, exiting: false };
    current.onDisconnect = (event) => {
      if (event?.target === current.port || event?.port === current.port) {
        shutdown(current, { estado: STATES.ERROR, error: describeSerialError(null, 'read') }, true);
      }
    };
    run = current;
    getSerial()?.addEventListener?.('disconnect', current.onDisconnect);
    current.verified = false;
    current.openedAt = now();
    emit({ estado: STATES.CONNECTING, medio: medium, puerto: current.label, error: null, verificado: false });
    current.timer = setTimer(() => { checkIdentity(current); flush(current); }, TICK_MS);
    current.loop = readLoop(current);
    flush(current);
    return true;
  }

  /** Reconecta sola al último puerto usado, sin selector. Solo funciona si el navegador ya tiene permiso para ese puerto. */
  async function autoConnect() {
    if (run || snapshot.estado === STATES.CONNECTING) return false;
    const serial = getSerial();
    const saved = readRemembered();
    if (!serial?.getPorts || !saved) return false;
    let ports;
    try {
      ports = await serial.getPorts();
    } catch {
      return false;
    }
    const port = ports.find((candidate) => matchesRemembered(candidate, saved));
    if (!port) return false;
    emit({ estado: STATES.CONNECTING, medio: saved.medium, error: null, lineasEnviadas: 0, ultimoEnvio: null });
    return openAndRun(port, saved.medium, true);
  }

  async function disconnect() {
    const current = run;
    if (!current) {
      if (snapshot.estado !== STATES.IDLE) emit({ estado: STATES.IDLE, error: null, puerto: null });
      return;
    }
    await shutdown(current, { estado: STATES.IDLE, error: null }, true);
  }

  return {
    connect,
    autoConnect,
    disconnect,
    subscribe: (listener) => { listeners.add(listener); return () => listeners.delete(listener); },
    getSnapshot: () => snapshot,
  };
}

export const browserLink = createBrowserLink();

/** Estado de la conexión del navegador y sus acciones (la conexión vive fuera de React: sobrevive al cambio de pantalla). */
export function useBrowserLink() {
  const snapshot = useSyncExternalStore(browserLink.subscribe, browserLink.getSnapshot);
  return { ...snapshot, supported: webSerialSupported(), connect: browserLink.connect, disconnect: browserLink.disconnect };
}
