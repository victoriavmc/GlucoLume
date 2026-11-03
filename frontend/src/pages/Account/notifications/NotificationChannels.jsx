// Qué avisos recibir y por qué canal, de una categoría: en la aplicación, por correo o en ambos. Cada interruptor guarda al instante.

import { Bell, Building2, Clock, Droplet, ShieldCheck, Users } from 'lucide-react';

import { CATEGORIAS, EVENTOS } from './notificationsCopy.js';

const CATEGORY_ICONS = { SEGURIDAD: ShieldCheck, GRUPO: Users, RECORDATORIO: Clock, INSTITUCION: Building2, MEDICION: Droplet };
const CATEGORY_TEXT = {
  SEGURIDAD: 'Elegí qué alertas de seguridad recibir, en la aplicación, por correo o en ambos. Cada canal se configura por separado.',
  GRUPO: 'Los avisos de mediciones respetan lo que cada integrante decidió compartir.',
  RECORDATORIO: 'Elegí por dónde recibir el recordatorio y, más abajo, cuándo.',
  INSTITUCION: 'Avisos de la gestión de la institución. Llegan solo los que corresponden a tu rol. Podés recibirlos en la aplicación, por correo o en ambos.',
  MEDICION: 'Avisos sobre el envío del resultado de tus mediciones. Elegí si querés recibirlos en la aplicación, por correo o en ambos.',
};

function ChannelSwitch({ canal, titulo, checked, disabled, onToggle }) {
  return (
    <div className="notif-switch">
      <span className="notif-switch-label" aria-hidden="true">{canal}</span>
      <button type="button" role="switch" className="switch" aria-checked={checked} aria-label={`${canal}: ${titulo}`}
        disabled={disabled} onClick={onToggle} />
    </div>
  );
}

export function NotificationChannels({ categoria, preferencias, savingEvent, onChange }) {
  const Icon = CATEGORY_ICONS[categoria] ?? Bell;
  const headingId = `notif-categoria-${categoria}`;
  return (
    <section className="panel" aria-labelledby={headingId}>
      <div className="panel-title">
        <span className="panel-icon">
          <Icon size={22} aria-hidden="true" />
        </span>
        <div>
          <h2 id={headingId}>{CATEGORIAS[categoria].titulo}</h2>
          <p>{CATEGORY_TEXT[categoria]}</p>
        </div>
      </div>
      <ul className="notif-channels">
        {preferencias.map((preferencia) => {
          const { titulo, descripcion } = EVENTOS[preferencia.evento] ?? { titulo: preferencia.evento, descripcion: '' };
          const busy = savingEvent === preferencia.evento;
          return (
            <li key={preferencia.evento} className="notif-channel">
              <div className="notif-channel-text">
                <b>{titulo}</b>
                <span>{descripcion}</span>
              </div>
              <div className="notif-channel-switches">
                <ChannelSwitch canal="En la aplicación" titulo={titulo} checked={preferencia.enPagina}
                  disabled={busy}
                  onToggle={() => onChange(preferencia.evento, { enPagina: !preferencia.enPagina })} />
                {preferencia.correoDisponible !== false && (
                  <ChannelSwitch canal="Por correo" titulo={titulo} checked={preferencia.porCorreo}
                    disabled={busy}
                    onToggle={() => onChange(preferencia.evento, { porCorreo: !preferencia.porCorreo })} />
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
