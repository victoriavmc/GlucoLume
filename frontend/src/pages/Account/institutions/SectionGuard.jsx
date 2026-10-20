// Guardia de una sección de la institución: si el rol no tiene el permiso, vuelve al panel. Ocultar el enlace no alcanza (la URL
// directa también se cubre acá), y FastAPI vuelve a validar cada consulta.

import { Navigate, Outlet, useOutletContext } from 'react-router-dom';

import { can } from './institutionFormat.js';

export function SectionGuard({ permission, children }) {
  const context = useOutletContext();
  const { institution } = context;
  if (!can(institution, permission)) return <Navigate to={`/app/instituciones/${institution.idInstitucion}`} replace />;
  return children ?? <Outlet context={context} />; // sin hijos directos, protege las rutas anidadas (y les pasa el contexto de la institución)
}
