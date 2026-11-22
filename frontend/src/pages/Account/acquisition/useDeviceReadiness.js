// Diagnóstico «¿qué falta para medir?» del backend. Se vuelve a pedir cuando cambia el estado en vivo (llega una lectura nueva,
// se abre o cierra el puerto) y cada pocos segundos. Es la única fuente de las comprobaciones: la página no las inventa.

import { useCallback, useEffect, useState } from 'react';

import { enSegundoPlano } from '../../../api/client.js';
import * as acquisitionApi from '../../../api/acquisitionApi.js';
import { friendlyError } from '../../../auth/errorMessages.js';
import { useBrowserLink } from '../../../utils/browserSerialLink.js';

const POLL_MS = 5000;

export function useDeviceReadiness(idPerfilMedicion, status, idInstitucion) {
  const [readiness, setReadiness] = useState(null);
  // El enlace del navegador cambia antes que el backend: al conectar o confirmar el Arduino, la disponibilidad se vuelve a pedir ya.
  const link = useBrowserLink();
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
    Boolean(status?.lectura) || status?.edadUltimaLectura != null, status?.ocupado, Boolean(status?.sesion),
    link.estado, link.verificado, link.puerto].join('|');

  useEffect(() => {
    refresh();
  }, [refresh, signature]);

  useEffect(() => {
    const timer = setInterval(() => enSegundoPlano(refresh), POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  return { readiness, error, refresh };
}
