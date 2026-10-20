// Diagnóstico «¿qué falta para medir?» del backend. Se vuelve a pedir cuando cambia el estado en vivo (llega una lectura nueva,
// se abre o cierra el puerto) y cada pocos segundos. Es la única fuente de las comprobaciones: la página no las inventa.

import { useCallback, useEffect, useState } from 'react';

import * as acquisitionApi from '../../../api/acquisitionApi.js';
import { friendlyError } from '../../../auth/errorMessages.js';

const POLL_MS = 5000;

export function useDeviceReadiness(idPerfilMedicion, status, idInstitucion) {
  const [readiness, setReadiness] = useState(null);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    try {
      setReadiness(await acquisitionApi.getDeviceReadiness(idPerfilMedicion, idInstitucion));
      setError('');
    } catch (loadError) {
      setError(friendlyError(loadError));
    }
  }, [idPerfilMedicion, idInstitucion]);

  // Cambios relevantes del estado en vivo (no cada lectura: solo cuando aparece/desaparece algo).
  const signature = [status?.estado, status?.puente?.estadoEnlace, status?.puente?.puerto, status?.puente?.codigoError,
    Boolean(status?.lectura) || status?.edadUltimaLectura != null, status?.ocupado, Boolean(status?.sesion)].join('|');

  useEffect(() => {
    refresh();
  }, [refresh, signature]);

  useEffect(() => {
    const timer = setInterval(refresh, POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  return { readiness, error, refresh };
}
