// Pantallas de auditoría:
//   - /app/auditoria                       auditoría general en tres ámbitos (solo el administrador del sistema; ver AdminAudit.jsx);
//   - /app/instituciones/:id/auditoria     auditoría de la institución (solo su propietario; FastAPI lo exige), con su detalle en
//     /app/instituciones/:id/auditoria/:idAuditoria. /administracion/auditoria[/:id] redirige acá.
// Ocultar la opción para los demás roles no reemplaza la autorización: FastAPI responde 403/404 igualmente.

import { useCallback } from 'react';
import { Navigate, useLocation, useOutletContext, useParams } from 'react-router-dom';

import * as auditApi from '../../../api/auditApi.js';
import { useAuth } from '../../../auth/AuthContext.jsx';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Alert } from '../../../components/FormControls.jsx';
import { can } from '../institutions/institutionFormat.js';
import { AuditEventPage } from './AuditDetail.jsx';
import { AuditView } from './AuditView.jsx';

// La auditoría general es la pantalla de tres ámbitos de la administración (AdminAudit.jsx): plataforma, instituciones y cuentas.
export { AdminAuditPage as GlobalAuditPage } from './AdminAudit.jsx';

export function GlobalAuditDetailPage({ basePath = '/app/auditoria' }) {
  const { account } = useAuth();
  const loadDetail = useCallback((id) => auditApi.getGlobalAuditEvent(id), []);
  if (account.usuario.tipoCuenta !== 'ADMINISTRADOR_PLATAFORMA') return <Navigate to="/app/inicio" replace />;
  return (
    <div className="page">
      <AuditEventPage titleAs="h1" loadDetail={loadDetail} backTo={basePath} handleOperationError={friendlyError} />
    </div>
  );
}

export function InstitutionAuditPage() {
  const { institution, handleOperationError } = useOutletContext();
  const id = institution.idInstitucion;
  const loadPage = useCallback((filters) => auditApi.listInstitutionAudit(id, filters), [id]);
  const loadSummary = useCallback((filters) => auditApi.getInstitutionAuditSummary(id, filters), [id]);
  if (!can(institution, 'CONSULTAR_AUDITORIA')) {
    return <Alert>Solo el propietario de la institución puede consultar la auditoría.</Alert>;
  }
  return (
    <AuditView embedded title="Auditoría institucional"
      lead="Operaciones realizadas en esta institución por su personal y por la administración de GlucoLume: altas y bajas de cuentas, accesos fallidos del personal, exportaciones, cambios administrativos, transferencias, mediciones, matrices y operaciones rechazadas. Solo lectura."
      loadPage={loadPage} loadSummary={loadSummary} handleOperationError={handleOperationError} />
  );
}

/** Detalle de un evento de la institución, en su propia página. Solo el propietario; FastAPI lo vuelve a comprobar. */
export function InstitutionAuditDetailPage() {
  const { institution, handleOperationError } = useOutletContext();
  const id = institution.idInstitucion;
  const loadDetail = useCallback((eventId) => auditApi.getInstitutionAuditEvent(id, eventId), [id]);
  if (!can(institution, 'CONSULTAR_AUDITORIA')) {
    return <Alert>Solo el propietario de la institución puede consultar la auditoría.</Alert>;
  }
  return (
    <AuditEventPage loadDetail={loadDetail} backTo={`/app/instituciones/${id}/auditoria`}
      handleOperationError={handleOperationError} />
  );
}

/** Ruta anterior (administracion/auditoria[/:id]): conserva el evento y los filtros al pasar a la ruta propia de Auditoría. */
export function AuditRedirect() {
  const { idInstitucion, idAuditoria } = useParams();
  const { search } = useLocation();
  return <Navigate to={`/app/instituciones/${idInstitucion}/auditoria${idAuditoria ? `/${idAuditoria}` : ''}${search}`} replace />;
}
