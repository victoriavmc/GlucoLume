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

export const webSerialSupported = () => typeof navigator !== 'undefined' && 'serial' in navigator
  && (typeof window === 'undefined' || window.isSecureContext !== false);

const hex = (value) => value.toString(16).padStart(4, '0');

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
  let snapshot = { estado: STATES.IDLE, medio: null, puerto: null, error: null, lineasEnviadas: 0, ultimoEnvio: null };
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
            if (text.trim()) enqueue(current, text);
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
    emit({ ...next, puerto: null });
    try { await current.reader?.cancel(); } catch { /* ya estaba cerrado */ }
    // port.close() falla con el lector bloqueado: se espera a que el ciclo de lectura lo suelte (salvo que sea él quien está cerrando).
    if (!current.exiting) { try { await current.loop; } catch { /* sin lector que esperar */ } }
    try { await current.port.close(); } catch { /* el dispositivo ya no está */ }
    if (notify) {
      try { await send(body(current, [], { estadoEnlace: 'DESCONECTADO', detenido: true, error: (next.error ?? '').slice(0, 200) || undefined })); } catch { /* el backend lo da por caído solo */ }
    }
  }

  async function connect(medium) {
    if (run || snapshot.estado === STATES.CONNECTING) return;
    if (!BAUD[medium]) throw new Error('Medio inválido');
    const serial = getSerial();
    if (!serial) {
      emit({ estado: STATES.ERROR, error: 'Este navegador no puede leer puertos serie. Usá Chrome o Edge en una computadora.' });
      return;
    }
    emit({ estado: STATES.CONNECTING, medio: medium, error: null, lineasEnviadas: 0, ultimoEnvio: null });
    let port;
    try {
      port = await serial.requestPort();
    } catch (error) {
      const message = describeSerialError(error, 'pick');
      emit({ estado: message ? STATES.ERROR : STATES.IDLE, error: message });
      return;
    }
    try {
      await port.open({ baudRate: BAUD[medium] });
    } catch (error) {
      emit({ estado: STATES.ERROR, error: describeSerialError(error, 'open') });
      return;
    }
    const current = { id: newId(), port, medium, label: portLabel(port, medium), seq: 0, queue: [], timer: null, reader: null, closing: false,
      lastSent: Number.NEGATIVE_INFINITY, inFlight: false, onDisconnect: null, loop: null, exiting: false };
    current.onDisconnect = (event) => {
      if (event?.target === current.port || event?.port === current.port) {
        shutdown(current, { estado: STATES.ERROR, error: describeSerialError(null, 'read') }, true);
      }
    };
    run = current;
    serial.addEventListener?.('disconnect', current.onDisconnect);
    emit({ estado: STATES.CONNECTED, puerto: current.label, error: null });
    current.timer = setTimer(() => { flush(current); }, TICK_MS);
    current.loop = readLoop(current);
    flush(current);
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
