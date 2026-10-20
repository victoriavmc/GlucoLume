// Pie de las páginas públicas: marca, leyenda experimental y enlace a la Política de Privacidad.

import { Link } from 'react-router-dom';

import { LogoMark } from './Logo.jsx';

export function SiteFooter() {
  return (
    <footer className="footer">
      <div className="container footer-inner">
        <span className="footer-brand">
          <LogoMark size={22} /> GlucoLume · Proyecto académico
        </span>
        <p>
          Prototipo tecnológico de monitoreo experimental. No es un dispositivo médico y no reemplaza la consulta
          profesional.
        </p>
        <nav className="footer-links" aria-label="Información legal">
          <Link to="/privacidad">Privacidad</Link>
        </nav>
      </div>
    </footer>
  );
}
