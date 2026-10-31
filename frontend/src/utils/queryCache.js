// Caché en memoria de lecturas de la API (stale-while-revalidate): al volver a una pantalla ya vista se dibuja lo último recibido en el mismo
// instante y la consulta se repite en segundo plano; cuando llega, reemplaza el dato. Vive solo en la pestaña (nunca en el almacenamiento del
// navegador) y se vacía al cerrar o vencer la sesión (clearTokens). Quien cambia datos de una clave la invalida con `invalidateQuery`.

import { useCallback, useEffect, useRef, useState } from 'react';

import { useLatestRequest } from './useLatestRequest.js';

const entries = new Map();

export function invalidateQuery(key) {
  entries.delete(key);
}

export function clearQueryCache() {
  entries.clear();
}

/**
 *   const { data, error, reload } = useCachedQuery('home:latest', () => api.get(), enabled);
 * `data` es undefined solo si la clave nunca se recibió en esta sesión (ni de caché ni de la red). `error` es el de la última consulta de la clave.
 */
export function useCachedQuery(key, loader, enabled = true) {
  const [, setRevision] = useState(0);
  const [failure, setFailure] = useState(null); // { key, error }
  const [reloads, setReloads] = useState(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const beginRequest = useLatestRequest();

  useEffect(() => {
    if (!enabled) return undefined;
    const isCurrent = beginRequest();
    loaderRef.current().then(
      (data) => {
        if (!isCurrent()) return;
        entries.set(key, data);
        setFailure(null);
        setRevision((value) => value + 1);
      },
      (error) => {
        if (!isCurrent()) return;
        setFailure({ key, error });
        setRevision((value) => value + 1);
      },
    );
    return undefined;
  }, [key, enabled, reloads, beginRequest]);

  const reload = useCallback(() => setReloads((count) => count + 1), []);

  return {
    data: entries.get(key),
    error: failure?.key === key ? failure.error : null,
    reload,
  };
}
