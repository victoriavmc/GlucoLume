// Una notificación de la bandeja: la tarjeta entera es el control. Al elegirla se marca como leída y, si tiene un destino válido, se abre.

import { ChevronRight } from 'lucide-react';

import { formatDateTime } from '../groups/groupFormat.js';
import { destinoSeguro, presentacion } from './notificationsCopy.js';

export function NotificationCard({ notificacion, onOpen }) {
  const { Icono, tono, categoria } = presentacion(notificacion);
  const destino = destinoSeguro(notificacion.url);
  const estado = notificacion.leida ? 'Leída' : 'Sin leer';
  return (
    <li>
      <button type="button" className={`notif-card is-${tono} ${notificacion.leida ? 'is-read' : 'is-unread'}`}
        onClick={() => onOpen(notificacion)}>
        <span className="notif-card-icon"><Icono size={22} aria-hidden="true" /></span>
        <span className="notif-card-body">
          <span className="notif-card-title">{notificacion.titulo}</span>
          <span className="notif-card-text">{notificacion.mensaje}</span>
        </span>
        <span className="notif-card-meta">
          <span className="notif-card-category">{categoria}</span>
          <time dateTime={notificacion.fechaCreacion}>{formatDateTime(notificacion.fechaCreacion)}</time>
          <span className="notif-card-state">{estado}</span>
        </span>
        {destino && <ChevronRight className="notif-card-go" size={20} aria-hidden="true" />}
      </button>
    </li>
  );
}
