// Pestañas secundarias dentro de una sección institucional (Personal, Pacientes, Administración). Son pocas y se
// ajustan al ancho disponible; la navegación principal vive en el sidebar.

import { Navigate, Outlet, useLocation, useOutletContext, useParams } from 'react-router-dom';

import { NavTabs } from '../../../components/Tabs.jsx';
import { can } from './institutionFormat.js';

export function SubTabs({ label, tabs }) {
  return <NavTabs label={label} variant="soft" className="ui-tabs--ruled" items={tabs.map((tab) => ({ to: tab.to, label: tab.label, end: tab.end !== false }))} />;
}

/** Pacientes: Listado y Transferencias (mismas pantallas de siempre, agrupadas). */
export function PatientsTabs() {
  const base = `/app/instituciones/${useParams().idInstitucion}/pacientes`;
  const { institution } = useOutletContext();
  const tabs = [{ to: base, label: 'Listado de pacientes' }, { to: `${base}/transferencias`, label: 'Transferencias', end: false }];
  // El análisis de mediciones es del operador responsable (propietario y moderador no acceden a mediciones individuales por su rol).
  if (institution.rolInstitucion === 'OPERADOR' && can(institution, 'GESTIONAR_PACIENTES')) tabs.splice(1, 0, { to: `${base}/analisis`, label: 'Análisis', end: false });
  // La reasignación de pacientes de operadores desvinculados la gestionan el propietario y el moderador (CONSULTAR_EQUIPO).
  if (can(institution, 'CONSULTAR_EQUIPO')) tabs.push({ to: `${base}/reasignaciones`, label: 'Pendientes de reasignación', end: false });
  return <SubTabs label="Secciones de pacientes" tabs={tabs} />;
}

/** Personal: Todos, Moderadores, Operadores e Invitaciones (el equipo lo consultan el propietario y el moderador). Las pestañas no se muestran en el perfil.
 * Cada página las ubica después de su resumen (`personnelTabs` del contexto): primero el resumen, luego las pestañas y al final la tabla. */
export function PersonnelLayout() {
  const context = useOutletContext();
  const { institution } = context;
  const { pathname } = useLocation();
  if (!can(institution, 'CONSULTAR_EQUIPO')) return <Navigate to=".." replace />;
  const onProfile = /\/personal\/perfil\//.test(pathname);
  // Rutas absolutas: las pestañas se muestran dentro de cada página (rutas hijas), donde las relativas no apuntan al personal.
  const base = `/app/instituciones/${institution.idInstitucion}/personal`;
  const tabs = [
    { to: base, label: 'Todos', end: true },
    { to: `${base}/moderadores`, label: 'Moderadores', end: false },
    { to: `${base}/operadores`, label: 'Operadores', end: false },
    { to: `${base}/invitaciones`, label: 'Invitaciones', end: false },
  ];
  const personnelTabs = onProfile ? null : <SubTabs label="Secciones del personal" tabs={tabs} />;
  return <Outlet context={{ ...context, personnelTabs }} />;
}

