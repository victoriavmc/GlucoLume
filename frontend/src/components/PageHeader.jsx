// Encabezado de página: volver, título, descripción y acciones. Reutiliza las clases `.page-head` y `.back-link` del
// layout interno, así que se ve igual que los encabezados actuales.
//   as="h1" (por defecto): la pantalla no tiene otro título principal.
//   as="h2": la pantalla ya vive bajo un h1 de su layout (p. ej. el nombre de la institución): evita dos h1 en la vista.

import { ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';

export function PageHeader({ title, description, actions, actionsClassName = '', back, as = 'h1', id, className = '' }) {
  const Title = as === 'h2' ? 'h2' : 'h1';
  return (
    <header className={`page-head ui-page-head ${className}`.trim()}>
      {back && (
        <Link to={back.to} className="back-link">
          <ArrowLeft size={16} aria-hidden="true" /> {back.label}
        </Link>
      )}
      <div className="ui-page-head-row">
        <div className="ui-page-head-text">
          <Title id={id}>{title}</Title>
          {description && <p>{description}</p>}
        </div>
        {actions && <div className={`ui-page-head-actions ${actionsClassName}`.trim()}>{actions}</div>}
      </div>
    </header>
  );
}
