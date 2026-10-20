// Aviso del período de gracia: una cuenta institucional que perdió su última vinculación activa tiene 30 días corridos para incorporarse
// a otra institución antes de que se elimine sola. Todo (vencimiento y días restantes) lo calcula el backend (/auth/me, periodoGracia).
// Iniciar sesión no reinicia el plazo y una invitación pendiente tampoco lo cancela: solo aceptarla.

import { Hourglass } from 'lucide-react';
import { Link } from 'react-router-dom';

import { formatDate } from '../pages/Account/institutions/institutionFormat.js';

export function GracePeriodNotice({ grace }) {
  if (!grace) return null;
  const days = grace.diasRestantes;
  const urgent = days <= 7;
  return (
    <section className={`grace-notice${urgent ? ' is-urgent' : ''}`} role="status" aria-label="Período de gracia de la cuenta">
      <Hourglass size={22} aria-hidden="true" />
      <div>
        <h2>Tu cuenta no está vinculada a ninguna institución</h2>
        <p>
          Tenés hasta el <b>{formatDate(grace.fechaVencimiento)}</b> para crear tu propia institución (y ser su propietario/a) o
          incorporarte a una existente con una invitación: <b>{days === 1 ? 'queda 1 día' : `quedan ${days} días`}</b>. Si el plazo
          vence, tu cuenta se elimina automáticamente y tus datos personales se anonimizan. Crear una institución o aceptar una
          invitación cancela el vencimiento; iniciar sesión no lo reinicia.
        </p>
        <div className="grace-actions">
          <Link to="/app/instituciones" className="btn btn-primary">Crear una institución o ver mis invitaciones</Link>
          <Link to="/app/seguridad#seguridad-baja" className="btn btn-outline">Eliminar mi cuenta</Link>
        </div>
      </div>
    </section>
  );
}
