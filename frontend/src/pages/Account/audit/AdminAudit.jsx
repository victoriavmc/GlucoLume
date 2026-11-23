// Auditoría general de la administración de la plataforma (solo ADMINISTRADOR_PLATAFORMA; FastAPI lo exige en cada llamada): operaciones
// administrativas globales y eventos de seguridad, con el panel de accesos fallidos y actividad sospechosa. Los eventos se piden por
// página al backend: nunca se cargan en bloque. No se muestran mediciones, contraseñas, códigos MFA ni datos médicos.

import { useCallback, useState } from 'react';
import { Navigate } from 'react-router-dom';

import * as auditApi from '../../../api/auditApi.js';
import { useAuth } from '../../../auth/AuthContext.jsx';
import { friendlyError } from '../../../auth/errorMessages.js';
import { PageHeader } from '../../../components/PageHeader.jsx';
import './Audit.css';
import { CriticalSecurityEvents } from './AuditSecurity.jsx';
import { AuditView } from './AuditView.jsx';

export function AdminAuditPage() {
  const { account } = useAuth();
  const [preset, setPreset] = useState(null);
  const loadPage = useCallback((filters) => auditApi.listGlobalAudit(filters), []);
  const loadSummary = useCallback((filters) => auditApi.getGlobalAuditSummary(filters), []);
  if (account.usuario.tipoCuenta !== 'ADMINISTRADOR_PLATAFORMA') return <Navigate to="/app/inicio" replace />;

  const viewEvents = (filters) => setPreset({ id: Date.now(), filters });

  return (
    <div className="page audit">
      <PageHeader title="Auditoría general"
        description="Operaciones administrativas, accesos fallidos y eventos de seguridad de GlucoLume. Solo lectura: los registros no se editan ni se eliminan desde acá; su conservación la fija una política técnica." />
      <div className="audit-scope">
        <CriticalSecurityEvents onViewEvents={viewEvents} />
        <AuditView embedded global showSummary={false} loadPage={loadPage} loadSummary={loadSummary} handleOperationError={friendlyError}
          preset={preset} />
      </div>
    </div>
  );
}
