// Conexión con el Arduino (backend/app/api/v1/acquisition.py). El puerto serie lo abre el BACKEND (pySerial) en el equipo
// que tiene el dispositivo; el navegador nunca accede al COM. Quién puede conectar y medir lo decide FastAPI.

import { getAccessToken } from '../auth/tokenStore.js';
import { apiUrl, refreshSession, request } from './client.js';
import { queryString } from './measurementsApi.js';

const post = (path, body) => request(`/acquisition${path}`, { method: 'POST', body, auth: true });

export const getStatus = () => request('/acquisition/status', { auth: true });
/** medio: USB | BLUETOOTH. baudios es opcional (USB 115200, HC-06 9600 por defecto). */
export const connect = ({ puerto, medio, baudios }) => post('/connect', { puerto, medio, ...(baudios ? { baudios } : {}) });
export const disconnect = () => post('/disconnect');
export const probe = () => post('/probe');
export const identify = () => post('/identify');
export const startAcquisition = (idMedicion) => post('/start', { idMedicion });
export const finishAcquisition = () => post('/finish');
export const cancelAcquisition = () => post('/cancel');

/**
 * Flujo SSE autenticado. `EventSource` no permite la cabecera Authorization, así que se lee el stream con fetch.
 * Devuelve una función que cierra la conexión. `onEvent` recibe cada evento ya parseado; `onError` los cortes.
 */
function openSse(path, { onEvent, onError }) {
  const controller = new AbortController();

  async function connectOnce(token) {
    return fetch(apiUrl(path), {
      headers: { Accept: 'text/event-stream', Authorization: `Bearer ${token}` }, signal: controller.signal,
    });
  }

  (async () => {
    try {
      let response = await connectOnce(getAccessToken() ?? (await refreshSession()).accessToken);
      if (response.status === 401) response = await connectOnce((await refreshSession()).accessToken);
      if (!response.ok || !response.body) throw new Error(`stream ${response.status}`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let boundary = buffer.indexOf('\n\n');
        while (boundary !== -1) {
          const block = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          const data = block.split('\n').filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trim()).join('');
          if (data) {
            try {
              onEvent(JSON.parse(data));
            } catch {
              // Línea ilegible: se ignora.
            }
          }
          boundary = buffer.indexOf('\n\n');
        }
      }
      onError?.(new Error('stream cerrado'));
    } catch (error) {
      if (!controller.signal.aborted) onError?.(error);
    }
  })();

  return () => controller.abort();
}

/** Avance en tiempo real de una adquisición con muestras crudas (flujo original). */
export const openStream = (handlers) => openSse('/acquisition/stream', handlers);

// --- Telemetría procesada del dispositivo (puente serie) ---------------------------------------------------------------
// El firmware envía BPM, SpO₂, glucosa experimental (o DEMO) e índice óptico ya calculados; el puente Windows los entrega
// al backend. React solo consulta el estado, abre una sesión y confirma «Guardar medición»: no genera ni calcula datos.

/**
 * { estado: SIN_PUENTE | PUERTO_DESCONECTADO | SIN_DATOS | CONECTADO, ocupado, controlPropio, edadUltimaLectura, puente, lectura, sesion, ... }.
 * `lectura` (valores en vivo) solo llega a la cuenta que tiene el control del dispositivo; las demás reciben `edadUltimaLectura`.
 */
export const getTelemetryStatus = () => request('/acquisition/telemetry/status', { auth: true });
/** «Usar dispositivo»: toma el control temporal del equipo compartido (DEC-01). Devuelve el estado actualizado. */
export const takeDeviceControl = () => post('/telemetry/control');
/** «Dejar de usar»: libera el control sin medición para que otra cuenta pueda usar el equipo. */
export const releaseDeviceControl = () => request('/acquisition/telemetry/control', { method: 'DELETE', auth: true });
/** Abre la sesión: { idPerfilMedicion, idDispositivo, condicionComida?, fechaHoraUltimaComida?, observacion? } -> medición. */
export const startDeviceSession = (data) => post('/telemetry/session', data);
export const saveDeviceSession = () => post('/telemetry/session/save');
export const cancelDeviceSession = () => post('/telemetry/session/cancel');
/** ¿Qué falta para medir? Pasos reales ordenados (puente, puerto, telemetría, sensor, registro, asociación) y `listo`. */
export const getDeviceReadiness = (idPerfilMedicion, idInstitucion) => request(
  `/acquisition/telemetry/readiness${queryString({ idPerfilMedicion, idInstitucion })}`, { auth: true });
/**
 * Operador, en la institución donde entró: «Registrar nuevo dispositivo» desde la primera conexión. El código, el sensor y el firmware
 * los informa el Arduino; solo se envía el nombre. Idempotente: si ya estaba registrado se devuelve el mismo (`creado: false`).
 */
export const registerConnectedDevice = ({ idInstitucion, nombre, confirmaIdentidad }) => post('/telemetry/device/register', {
  idInstitucion, ...(nombre ? { nombre } : {}), ...(confirmaIdentidad ? { confirmaIdentidad: true } : {}),
});
/**
 * Operador: vincula a su institución un dispositivo existente que no tiene institución. Exige la confirmación explícita (`confirmaVinculacion`);
 * con firmware sin ID propio también `confirmaIdentidad`. Pasa al inventario de la institución y conserva sus mediciones; con el uso restringido
 * deja de estar disponible para cuentas individuales, con el uso compartido (DEC-01) lo siguen usando todas las cuentas habilitadas.
 */
export const linkConnectedDevice = ({ idInstitucion, idDispositivo, nombre, confirmaVinculacion, confirmaIdentidad }) => post('/telemetry/device/link', {
  idInstitucion, idDispositivo, confirmaVinculacion: Boolean(confirmaVinculacion), ...(nombre ? { nombre } : {}), ...(confirmaIdentidad ? { confirmaIdentidad: true } : {}),
});
/** Operador: seleccionar y confirmar un dispositivo existente de la institución para la conexión actual (firmware sin ID propio). */
export const confirmConnectedDevice = ({ idInstitucion, idDispositivo }) => post('/telemetry/device/confirm', { idInstitucion, idDispositivo });
/**
 * Pide una orden acotada al puente (el backend la entrega al puente en su próximo latido; el navegador no toca ningún puerto):
 * { accion: CONFIGURAR | PAUSAR | REANUDAR | DETENER | REINICIAR, puerto?, medio? }. Devuelve el estado actualizado.
 */
export const sendBridgeCommand = (data) => post('/bridge/command', data);
/** Estado completo cada vez que llega una lectura o cambia la conexión (evento `estado`). */
export const openTelemetryStream = (handlers) => openSse('/acquisition/telemetry/stream', handlers);
