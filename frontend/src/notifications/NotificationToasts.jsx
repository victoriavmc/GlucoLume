// Carteles de avisos nuevos, arriba a la derecha. Se cierran solos a los 8 segundos o con la X; el aviso sigue en la bandeja.

import { BellRing, X } from 'lucide-react';
import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';

import { destinoSeguro } from '../pages/Account/notifications/notificationsCopy.js';
import { playNotificationSound } from './notificationSound.js';
import { useIncomingNotifications } from './useIncomingNotifications.js';
import './NotificationToasts.css';

const VISIBLE_MS = 8000;
const MAX_VISIBLE = 3;

export function NotificationToasts() {
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback((id) => setToasts((current) => current.filter((toast) => toast.idNotificacion !== id)), []);

  const arrive = useCallback((items) => {
    setToasts((current) => [...current, ...items].slice(-MAX_VISIBLE));
    items.forEach((item) => window.setTimeout(() => dismiss(item.idNotificacion), VISIBLE_MS));
    playNotificationSound();
  }, [dismiss]);

  useIncomingNotifications(arrive);

  return (
    <div className="notif-toasts" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.idNotificacion} className="notif-toast">
          <span className="notif-toast-icon"><BellRing size={20} aria-hidden="true" /></span>
          <div className="notif-toast-text">
            <b>{toast.titulo}</b>
            <span>{toast.mensaje}</span>
            {destinoSeguro(toast.url) && <Link to={destinoSeguro(toast.url)} onClick={() => dismiss(toast.idNotificacion)}>Ver</Link>}
          </div>
          <button type="button" className="notif-toast-close" aria-label="Cerrar aviso" onClick={() => dismiss(toast.idNotificacion)}>
            <X size={18} aria-hidden="true" />
          </button>
        </div>
      ))}
    </div>
  );
}
