// Eventos críticos de seguridad (solo la administración de la plataforma): las señales que requieren revisión o seguimiento.
// Las señales las CALCULA el backend sobre los eventos que existen; no son registros de auditoría y no se inventan. Sin señales que
// requieran revisión, la sección muestra 0. Un fallo aislado de acceso es un error operativo, no un ataque.

import { AlertTriangle, ShieldAlert, ShieldCheck } from 'lucide-react';
import { useEffect, useState } from 'react';

import * as auditApi from '../../../api/auditApi.js';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Alert } from '../../../components/FormControls.jsx';
import { formatInstant } from '../../../utils/dateTime.js';
import './Audit.css';
import { AUDIT_CHANGED } from './AuditReviewToggle.jsx';
import { AUDIT_CLASSIFICATIONS } from './auditLabels.js';

const isoDay = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
const DAYS_ANALYZED = 7;
const AUTO_REFRESH_MS = 15000;

/** Período analizado: los últimos siete días, hasta hoy. */
function recentPeriod() {
  const today = new Date();
  const since = new Date(today);
  since.setDate(today.getDate() - DAYS_ANALYZED);
  return { desde: isoDay(since), hasta: isoDay(today) };
}

function CriticalEvent({ signal, onView }) {
  const confirmed = signal.clasificacion === 'CONFIRMADO';
  const Icon = confirmed ? ShieldCheck : ShieldAlert;
  return (
    <li className={`audit-critical is-${confirmed ? 'confirmed' : 'suspicious'}`}>
      <div className="audit-critical-head">
        <span className="audit-critical-icon" aria-hidden="true"><Icon size={22} /></span>
        <span className={`audit-critical-badge is-${confirmed ? 'confirmed' : 'suspicious'}`}>{AUDIT_CLASSIFICATIONS[signal.clasificacion]}</span>
        {signal.analizada ? (
          <span className="audit-critical-status is-done">Analizado</span>
        ) : (
          <span className="audit-critical-status is-missing"><AlertTriangle size={14} aria-hidden="true" /> Falta analizar</span>
        )}
      </div>
      <h3>{signal.titulo}</h3>
      <p>{signal.descripcion}</p>
      <dl className="audit-critical-facts">
        <div><dt>Cantidad</dt><dd>{signal.cantidad}{signal.umbral ? ` (umbral ${signal.umbral})` : ''}</dd></div>
        {signal.cuenta && <div><dt>Cuenta</dt><dd>{signal.cuenta}</dd></div>}
        <div><dt>Período</dt><dd>{formatInstant(signal.desde)} – {formatInstant(signal.hasta)}</dd></div>
      </dl>
      <button type="button" className="btn btn-outline" onClick={() => onView(signal.filtros)} aria-label={`Ver evento: ${signal.titulo}`}>
        Ver evento
      </button>
    </li>
  );
}

/** Señales que requieren revisión o seguimiento en los últimos siete días. Sin ninguna, muestra 0. */
export function CriticalSecurityEvents({ onViewEvents }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    let active = true;
    auditApi.getSecuritySignals(recentPeriod()).then(
      (result) => active && setData(result),
      (loadError) => active && setError(friendlyError(loadError)),
    );
    return () => { active = false; };
  }, [refreshTick]);

  // Actualización inmediata al marcar un evento como analizado o al volver a la pestaña.
  useEffect(() => {
    const refresh = () => { if (document.visibilityState === 'visible') setRefreshTick((tick) => tick + 1); };
    window.addEventListener(AUDIT_CHANGED, refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      window.removeEventListener(AUDIT_CHANGED, refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, []);

  // Sincronización automática cada 15 s, solo con la pestaña visible.
  useEffect(() => {
    const timer = setInterval(() => { if (document.visibilityState === 'visible') setRefreshTick((tick) => tick + 1); }, AUTO_REFRESH_MS);
    return () => clearInterval(timer);
  }, []);

  const signals = data?.senales ?? [];
  return (
    <section className="audit-critical-panel" aria-labelledby="auditoria-criticos">
      <header className="audit-critical-title">
        <span className="audit-critical-title-icon" aria-hidden="true"><ShieldCheck size={26} /></span>
        <div>
          <h2 id="auditoria-criticos">Eventos críticos de seguridad <span className="audit-critical-count" aria-label={`${signals.length} eventos críticos`}>{signals.length}</span></h2>
          <p>Solo se muestran alertas que requieren revisión o seguimiento.</p>
        </div>
      </header>
      {error && <Alert>{error}</Alert>}
      {!error && !data && <p className="field-hint" role="status">Analizando los accesos…</p>}
      {data && signals.length === 0 && (
        <p className="audit-critical-empty">0 eventos críticos en los últimos {DAYS_ANALYZED} días.</p>
      )}
      {signals.length > 0 && (
        <ul className="audit-critical-list" aria-label="Eventos críticos de seguridad">
          {signals.map((signal) => (
            <CriticalEvent key={`${signal.tipo}-${signal.filtros?.idCuenta ?? signal.filtros?.ip ?? signal.filtros?.refIdentificador ?? signal.filtros?.accion}`}
              signal={signal} onView={onViewEvents} />
          ))}
        </ul>
      )}
    </section>
  );
}
