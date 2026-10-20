// Menú de una institución: se arma con los permisos que informa el backend para el rol vigente. Ocultar una opción
// no reemplaza la autorización de FastAPI, que se comprueba en cada llamada.

import { ShieldCheck } from 'lucide-react';
import { createContext, useContext } from 'react';

import { can } from './institutionFormat.js';

export const SECTION_LABELS = {
  panel: 'Panel', personal: 'Personal', pacientes: 'Pacientes', dispositivos: 'Dispositivos', matrices: 'Matrices',
  administracion: 'Administración', auditoria: 'Auditoría', actividad: 'Actividad', 'conectar-dispositivo': 'Conectar dispositivo',
};

/** Secciones visibles para el rol. `to` es relativo a /app/instituciones/:id. */
export function institutionSections(institution) {
  if (!institution) return [];
  const sections = [{ key: 'panel', to: '', label: SECTION_LABELS.panel, end: true }];
  if (can(institution, 'GESTIONAR_MODERADORES') || can(institution, 'ADMINISTRAR_OPERADORES')) {
    sections.push({ key: 'personal', to: 'personal', label: SECTION_LABELS.personal });
  }
  if (can(institution, 'CONSULTAR_PACIENTES')) sections.push({ key: 'pacientes', to: 'pacientes', label: SECTION_LABELS.pacientes });
  // El inventario lo administran propietario y moderador; el operador usa los dispositivos dentro del flujo de medición.
  if (can(institution, 'GESTIONAR_DISPOSITIVOS')) {
    sections.push({ key: 'dispositivos', to: 'dispositivos', label: SECTION_LABELS.dispositivos });
  }
  // El operador conecta y registra el Arduino dentro de su institución (queda en su inventario, a cargo del propietario).
  if (institution.rolInstitucion === 'OPERADOR') sections.push({ key: 'conectar-dispositivo', to: 'conectar-dispositivo', label: SECTION_LABELS['conectar-dispositivo'] });
  if (can(institution, 'GESTIONAR_MATRICES')) sections.push({ key: 'matrices', to: 'matrices', label: SECTION_LABELS.matrices });
  // Administración institucional: propietario y moderador (el operador no administra la institución).
  if (can(institution, 'CONSULTAR_EQUIPO')) sections.push({ key: 'administracion', to: 'administracion', label: SECTION_LABELS.administracion });
  // Auditoría: solo el propietario (permiso CONSULTAR_AUDITORIA); FastAPI lo exige en cada consulta.
  if (can(institution, 'CONSULTAR_AUDITORIA')) sections.push({ key: 'auditoria', to: 'auditoria', label: SECTION_LABELS.auditoria, icon: ShieldCheck });
  return sections;
}

/** Institución abierta: la registra InstitutionLayout y la lee el sidebar para mostrar el submenú. */
export const InstitutionNavContext = createContext({ current: null, setCurrent: () => {} });

export function useInstitutionNav() {
  return useContext(InstitutionNavContext);
}
