// Avisos que llegaron a la página (campana de la sección). Marcar como leído no borra nada.

import { BellRing } from 'lucide-react';
import { Link } from 'react-router-dom';

import { formatDateTime } from '../groups/groupFormat.js';

export function NotificationInbox({ inbox, onRead, onReadAll }) {
  const { noLeidas, notificaciones } = inbox;
  return (
    <section className="panel" aria-labelledby="notif-bandeja">
      <div className="panel-head">
        <div className="panel-title">
          <span className="panel-icon">
            <BellRing size={22} aria-hidden="true" />
          </span>
          <div>
            <h2 id="notif-bandeja">Tus avisos</h2>
            <p>{noLeidas > 0 ? `Tenés ${noLeidas} sin leer.` : 'No tenés avisos sin leer.'}</p>
          </div>
        </div>
        {noLeidas > 0 && (
          <button type="button" className="btn btn-ghost" onClick={onReadAll}>Marcar todos como leídos</button>
        )}
      </div>
      {notificaciones.length === 0 ? (
        <p className="notif-empty">Todavía no tenés avisos. Los que elijas recibir en la página aparecerán acá.</p>
      ) : (
        <ul className="notif-list">
          {notificaciones.map((notificacion) => (
            <li key={notificacion.idNotificacion} className={`notif-item${notificacion.leida ? '' : ' is-unread'}`}>
              <div className="notif-item-text">
                <b>{notificacion.titulo}</b>
                <span>{notificacion.mensaje}</span>
                <small>{formatDateTime(notificacion.fechaCreacion)}{notificacion.leida ? '' : ' · Nuevo'}</small>
              </div>
              <div className="notif-item-actions">
                {notificacion.url && <Link to={notificacion.url}>Ver</Link>}
                {!notificacion.leida && (
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => onRead(notificacion.idNotificacion)}>
                    Marcar como leído
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
