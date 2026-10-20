// Acceso a una función de administración institucional (tarjeta con ícono, nombre, ayuda y flecha). Lo usan el panel y la
// configuración; quien lo renderiza decide si mostrarlo según los permisos del rol.

import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';

import './Administration.css';

export function AdminAction({ to, icon: Icon, title, text }) {
  return (
    <Link to={to} className="admin-action">
      <span className="panel-icon"><Icon size={22} aria-hidden="true" /></span>
      <span className="admin-action-text"><b>{title}</b><small>{text}</small></span>
      <ArrowRight size={18} aria-hidden="true" className="admin-action-arrow" />
    </Link>
  );
}
