// Cantidad de avisos sin leer de la cuenta, compartida entre la barra lateral (insignia roja) y la bandeja. La mantienen el sondeo de
// avisos nuevos y las acciones de la bandeja; cualquier cambio del backend se refleja aquí con la misma respuesta (`noLeidas`).

import { createContext, useContext } from 'react';

export const UnreadNotificationsContext = createContext({ unread: 0, setUnread: () => {} });

export function useUnreadNotifications() {
  return useContext(UnreadNotificationsContext);
}
