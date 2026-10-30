// Una notificación de la bandeja. La tarjeta entera es el control principal: al elegirla se marca como leída y, si tiene un destino válido, se abre.
// El menú «Acciones» (⋮) separa lo de leer y abrir de lo de eliminar de la bandeja, sin sobrecargar la tarjeta.

import { ChevronRight, CircleCheck, ExternalLink, MoreVertical, Trash2 } from 'lucide-react';

import { formatDateTime } from '../groups/groupFormat.js';
import { ActionMenu } from './ActionMenu.jsx';
import { destinoSeguro, presentacion } from './notificationsCopy.js';

export function NotificationCard({ notificacion, onOpen, onRead, onDelete }) {
  const { Icono, tono, categoria } = presentacion(notificacion);
  const destino = destinoSeguro(notificacion.url);
  const estado = notificacion.leida ? 'Leída' : 'Sin leer';
  const acciones = [
    ...(destino ? [{ key: 'abrir', label: 'Abrir', icon: ExternalLink, onSelect: () => onOpen(notificacion) }] : []),
    ...(notificacion.leida ? [] : [{ key: 'leer', label: 'Marcar como leída', icon: CircleCheck, onSelect: () => onRead(notificacion) }]),
    { key: 'eliminar', label: 'Eliminar de la bandeja', icon: Trash2, danger: true, groupStart: !notificacion.leida || Boolean(destino), onSelect: () => onDelete(notificacion) },
  ];
  return (
    <li className="notif-item">
      <button type="button" className={`notif-card is-${tono} ${notificacion.leida ? 'is-read' : 'is-unread'}`} onClick={() => onOpen(notificacion)}>
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
      <ActionMenu className="notif-item-menu" label={`Acciones de «${notificacion.titulo}»: ${notificacion.mensaje.slice(0, 60)}`} trigger={<MoreVertical size={20} aria-hidden="true" />}
        items={acciones} />
    </li>
  );
}
