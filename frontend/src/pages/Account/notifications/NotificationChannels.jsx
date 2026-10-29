// Qué avisos recibir y por qué canal: en la página, por correo o en ambos. Cada interruptor guarda al instante.

import { Bell } from 'lucide-react';

import { EVENTOS } from './notificationsCopy.js';

function ChannelSwitch({ canal, titulo, checked, onToggle }) {
  return (
    <div className="notif-switch">
      <span className="notif-switch-label" aria-hidden="true">{canal}</span>
      <button type="button" role="switch" className="switch" aria-checked={checked} aria-label={`${canal}: ${titulo}`}
        onClick={onToggle} />
    </div>
  );
}

export function NotificationChannels({ preferencias, visibles, onChange }) {
  const porEvento = Object.fromEntries(preferencias.map((preferencia) => [preferencia.evento, preferencia]));
  return (
    <section className="panel" aria-labelledby="notif-canales">
      <div className="panel-title">
        <span className="panel-icon">
          <Bell size={22} aria-hidden="true" />
        </span>
        <div>
          <h2 id="notif-canales">Qué avisos recibir</h2>
          <p>Elegí si cada aviso aparece en esta página, llega por correo o ambas cosas.</p>
        </div>
      </div>
      <ul className="notif-channels">
        {visibles.map((evento) => {
          const { titulo, descripcion } = EVENTOS[evento];
          const preferencia = porEvento[evento];
          return (
            <li key={evento} className="notif-channel">
              <div className="notif-channel-text">
                <b>{titulo}</b>
                <span>{descripcion}</span>
              </div>
              <div className="notif-channel-switches">
                <ChannelSwitch canal="En la página" titulo={titulo} checked={preferencia.enPagina}
                  onToggle={() => onChange(evento, { enPagina: !preferencia.enPagina })} />
                <ChannelSwitch canal="Por correo" titulo={titulo} checked={preferencia.porCorreo}
                  onToggle={() => onChange(evento, { porCorreo: !preferencia.porCorreo })} />
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
