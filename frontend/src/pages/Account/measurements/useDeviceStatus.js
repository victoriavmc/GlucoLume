// Estado del dispositivo en tiempo real. El backend mantiene la telemetría que llega del puente serie (Arduino -> Bluetooth ->
// COM de Windows -> pySerial) y la expone por SSE; este hook solo la lee. Si el stream se corta, un sondeo cada pocos
// segundos mantiene la pantalla al día y el stream se reabre solo. No genera ni conserva datos del sensor.

import { useCallback, useEffect, useState } from 'react';

import * as acquisitionApi from '../../../api/acquisitionApi.js';
import { friendlyError } from '../../../auth/errorMessages.js';

const POLL_MS = 5000;
const RETRY_MS = 3000;

export function useDeviceStatus({ enabled = true } = {}) {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    try {
      setStatus(await acquisitionApi.getTelemetryStatus());
      setError('');
    } catch (loadError) {
      setError(friendlyError(loadError));
    }
  }, []);

  useEffect(() => {
    if (!enabled) return undefined;
    refresh();
    const timer = setInterval(refresh, POLL_MS);
    return () => clearInterval(timer);
  }, [enabled, refresh]);

  useEffect(() => {
    if (!enabled) return undefined;
    let close = null;
    let retry = null;
    let active = true;
    function connect() {
      close = acquisitionApi.openTelemetryStream({
        onEvent: (event) => {
          if (event.tipo !== 'estado') return;
          const { tipo, ...snapshot } = event; // eslint-disable-line no-unused-vars
          setStatus(snapshot);
          setError('');
        },
        onError: () => { if (active) retry = setTimeout(connect, RETRY_MS); },
      });
    }
    connect();
    return () => { active = false; clearTimeout(retry); close?.(); };
  }, [enabled]);

  return { status, error, refresh, setStatus };
}
