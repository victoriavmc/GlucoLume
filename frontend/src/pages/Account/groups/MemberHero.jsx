// Cabecera de la persona elegida en «Datos compartidos» y en la página de cada integrante: avatar, nombre, rol y el estado de sus cuatro permisos
// (verde «Compartido», gris «No compartido»). Solo muestra el estado de los permisos: nunca los datos.

import { Bell, CheckCircle2, Droplet, EyeOff, UserRound, BarChart3 } from 'lucide-react';

import { Badge } from '../../../components/Badge.jsx';
import { ROLE_LABELS, SHARING_OPTIONS, personName } from './groupFormat.js';

const ICONS = { compartePerfil: UserRound, comparteUltimaMedicion: Droplet, comparteHistorial: BarChart3, notificaMedicion: Bell };

export function MemberHero({ member }) {
  const name = personName(member);
  return (
    <section className="gm-hero" aria-labelledby="integrante-datos">
      <div className="gm-hero-top">
        <span className={`gd-avatar is-large ${member.rol === 'ADMINISTRADOR' ? 'is-rose' : 'is-violet'}`} aria-hidden="true">{name.charAt(0).toUpperCase()}</span>
        <div>
          <h2 id="integrante-datos">{name}</h2>
          <p>{ROLE_LABELS[member.rol]}</p>
        </div>
      </div>
      <ul className="gm-perms" aria-label={`Qué comparte ${name}`}>
        {SHARING_OPTIONS.map(({ field, label }) => {
          const Icon = ICONS[field];
          const on = Boolean(member[field]);
          return (
            <li key={field} className={`gm-perm${on ? ' is-on' : ''}`}>
              <span className="gm-perm-icon"><Icon size={22} aria-hidden="true" /></span>
              <span className="gm-perm-body">
                <small>{label}</small>
                <Badge tone={on ? 'success' : 'neutral'} icon={on ? CheckCircle2 : EyeOff}>
                  {on ? 'Compartido' : 'No compartido'}
                </Badge>
              </span>
            </li>
          );
        })}
      </ul>
      {!member.tienePerfil && <p className="field-hint">Todavía no tiene perfil de medición.</p>}
    </section>
  );
}
