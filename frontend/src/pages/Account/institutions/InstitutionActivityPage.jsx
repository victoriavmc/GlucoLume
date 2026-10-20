// /app/instituciones/:id/actividad: toda la actividad reciente (resumen administrativo y operativo). Es distinta de Auditoría.

import { useOutletContext } from 'react-router-dom';

import { InstitutionActivity } from './InstitutionActivity.jsx';

export function InstitutionActivityPage() {
  const { institution } = useOutletContext();
  return <InstitutionActivity institution={institution} full />;
}
