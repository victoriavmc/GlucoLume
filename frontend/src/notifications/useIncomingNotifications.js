// Revisa cada tanto si llegaron avisos nuevos a la página y los entrega a `onArrive` (cartel + sonido). Pide solo los no leídos.
// `onCount` recibe la cantidad total sin leer (`noLeidas`) para la insignia de la barra lateral.
// La primera lectura solo fija el punto de partida: los avisos que ya estaban no se anuncian. Los errores (sin conexión, sección
// todavía no disponible en la instalación) se ignoran: la bandeja de la sección es la que informa.

import { useEffect, useRef } from 'react';

import { getNotifications } from '../api/notificationsApi.js';

export const POLL_INTERVAL_MS = 30000;

export function useIncomingNotifications(onArrive, onCount) {
  const callback = useRef(onArrive);
  callback.current = onArrive;
  const countCallback = useRef(onCount);
  countCallback.current = onCount;

  useEffect(() => {
    let active = true;
    let known = null;

    async function check() {
      if (document.visibilityState === 'hidden') return;
      try {
        const inbox = await getNotifications({ soloNoLeidas: true, limite: 20 });
        if (!active) return;
        if (typeof inbox?.noLeidas === 'number') countCallback.current?.(inbox.noLeidas);
        const unread = (inbox?.notificaciones ?? []).filter((item) => !item.leida);
        if (known === null) {
          known = new Set(unread.map((item) => item.idNotificacion));
          return;
        }
        const fresh = unread.filter((item) => !known.has(item.idNotificacion));
        fresh.forEach((item) => known.add(item.idNotificacion));
        if (fresh.length > 0) callback.current(fresh);
      } catch {
        // se reintenta en la próxima revisión
      }
    }

    check();
    const timer = window.setInterval(check, POLL_INTERVAL_MS);
    document.addEventListener('visibilitychange', check);
    return () => {
      active = false;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', check);
    };
  }, []);
}
