// Seguridad y accesos fallidos (solo la administración de la plataforma): patrones sospechosos y controles activados.
// Las señales las CALCULA el backend sobre los eventos que existen, con umbrales configurables; no son registros de auditoría y no se
// inventan: sin eventos que las originen, el panel dice que no hay nada. Un fallo aislado de acceso es un error operativo, no un ataque.
// Los umbrales de esta pantalla valen solo para la consulta; el valor permanente está en la configuración del servidor.

import { KeyRound, Network, ShieldAlert, ShieldCheck, UserX } from 'lucide-react';
import { useEffect, useState } from 'react';

import * as auditApi from '../../../api/auditApi.js';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Badge } from '../../../components/Badge.jsx';
import { EmptyState } from '../../../components/EmptyState.jsx';
import { Alert, SelectField, TextField } from '../../../components/FormControls.jsx';
import { Kpi, KpiGrid } from '../../../components/dashboard.jsx';
import { formatInstant } from '../../../utils/dateTime.js';
import './Audit.css';
import { AUDIT_CLASSIFICATIONS, CLASSIFICATION_HELP } from './auditLabels.js';

const PERIODS = [
  { value: '1', label: 'Ayer y hoy' },
  { value: '7', label: 'Últimos 7 días' },
  { value: '31', label: 'Últimos 31 días' },
];
const THRESHOLDS = [
  ['ventanaMinutos', 'Ventana (minutos)', 1, 1440],
  ['fallosPorCuenta', 'Fallos por cuenta', 2, 1000],
  ['cuentasPorOrigen', 'Cuentas por origen', 2, 1000],
  ['historialOrigenInusual', 'Historial mínimo (origen inusual)', 1, 1000],
];

const isoDay = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;

function periodParams(days) {
  const today = new Date();
  const since = new Date(today);
  since.setDate(today.getDate() - Number(days));
  return { desde: isoDay(since), hasta: isoDay(today) };
}

function Signal({ signal, onView }) {
  const confirmed = signal.clasificacion === 'CONFIRMADO';
  return (
    <li className={`audit-signal is-${confirmed ? 'confirmed' : 'suspicious'}`}>
      <div className="audit-signal-head">
        <Badge tone={confirmed ? 'danger' : 'warning'} title={CLASSIFICATION_HELP[signal.clasificacion]}>{AUDIT_CLASSIFICATIONS[signal.clasificacion]}</Badge>
        <h3>{signal.titulo}</h3>
      </div>
      <p>{signal.descripcion}</p>
      <dl className="audit-signal-facts">
        <div><dt>Cantidad</dt><dd>{signal.cantidad}{signal.umbral ? ` (umbral ${signal.umbral})` : ''}</dd></div>
        {signal.cuenta && <div><dt>Cuenta</dt><dd>{signal.cuenta}</dd></div>}
        {signal.ipOrigen && <div><dt>Origen</dt><dd>{signal.ipOrigen}</dd></div>}
        <div><dt>Período</dt><dd>{formatInstant(signal.desde)} – {formatInstant(signal.hasta)}</dd></div>
      </dl>
      <button type="button" className="btn btn-ghost" onClick={() => onView(signal.filtros)} aria-label={`Ver los eventos de: ${signal.titulo}`}>Ver eventos</button>
    </li>
  );
}

export function AuditSecurityPanel({ idInstitucion, onViewEvents, title = 'Seguridad y accesos fallidos' }) {
  const [period, setPeriod] = useState('1');
  const [overrides, setOverrides] = useState({});
  const [draft, setDraft] = useState({});
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const key = JSON.stringify({ period, overrides, idInstitucion });

  useEffect(() => {
    let active = true;
    setData(null);
    setError('');
    auditApi.getSecuritySignals({ ...periodParams(period), ...overrides, idInstitucion }).then(
      (result) => active && setData(result),
      (loadError) => active && setError(friendlyError(loadError)),
    );
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  function applyThresholds(event) {
    event.preventDefault();
    const next = {};
    for (const [name, , min, max] of THRESHOLDS) {
      const value = Number(draft[name]);
      if (draft[name] !== undefined && draft[name] !== '' && Number.isInteger(value) && value >= min && value <= max) next[name] = value;
    }
    setOverrides(next);
  }

  const thresholds = data?.umbrales;
  return (
    <section className="panel audit-security" aria-labelledby="auditoria-seguridad">
      <div className="panel-title">
        <span className="panel-icon is-lg"><ShieldCheck size={26} aria-hidden="true" /></span>
        <div>
          <h2 id="auditoria-seguridad">{title}</h2>
          <p>Patrones sobre los accesos fallidos auditados y controles que ya actuaron. Un fallo aislado es un error operativo, no un ataque.</p>
        </div>
      </div>
      <div className="audit-security-controls">
        <SelectField label="Período analizado" value={period} onChange={(event) => setPeriod(event.target.value)}>
          {PERIODS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </SelectField>
        <details className="audit-more-filters audit-thresholds">
          <summary>Umbrales de detección{thresholds ? ` (${thresholds.fallosPorCuenta} fallos por cuenta en ${thresholds.ventanaMinutos} min)` : ''}</summary>
          <form onSubmit={applyThresholds} aria-label="Umbrales de detección" className="audit-filters">
            {THRESHOLDS.map(([name, label, min, max]) => (
              <TextField key={name} label={label} type="number" min={min} max={max} inputMode="numeric"
                value={draft[name] ?? (thresholds ? thresholds[name] : '')} onChange={(event) => setDraft((current) => ({ ...current, [name]: event.target.value }))} />
            ))}
            <div className="audit-filter-extra">
              <button type="submit" className="btn btn-secondary">Aplicar a esta consulta</button>
              {Object.keys(overrides).length > 0 && (
                <button type="button" className="btn btn-ghost" onClick={() => { setOverrides({}); setDraft({}); }}>Volver a los valores configurados</button>
              )}
            </div>
            <p className="field-hint">Solo valen para esta consulta; los valores permanentes están en la configuración del servidor (AUDIT_ALERT_*).</p>
          </form>
        </details>
      </div>

      {error && <Alert>{error}</Alert>}
      {!error && !data && <p className="field-hint" role="status">Analizando los accesos del período…</p>}
      {data && (
        <>
          {!data.contextoDisponible && (
            <Alert kind="info">La base de datos instalada todavía no registra el origen de los eventos: sin IP ni motivo no se pueden
              detectar patrones por origen ni por motivo.</Alert>
          )}
          {data.truncado && (
            <Alert kind="info">Se analizaron los 5000 intentos más recientes del período. Hubo más: acotá el período para ver todos.</Alert>
          )}
          <KpiGrid label="Indicadores de seguridad del período" compact>
            <Kpi icon={KeyRound} tone="warn" label="Intentos fallidos" value={data.indicadores.intentosFallidos} />
            <Kpi icon={UserX} label="Cuentas o identificadores afectados" value={data.indicadores.cuentasAfectadas} />
            <Kpi icon={Network} label="Orígenes distintos" value={data.indicadores.origenesDistintos} />
            <Kpi icon={ShieldAlert} tone="danger" label="Bloqueos aplicados" value={data.indicadores.bloqueos} />
            <Kpi icon={ShieldAlert} tone="danger" label="Límites de solicitudes superados" value={data.indicadores.limitesExcedidos} />
            <Kpi icon={ShieldAlert} tone="warn" label="Ráfagas de rechazos" value={data.indicadores.rafagasRechazos} />
          </KpiGrid>
          {data.senales.length === 0 ? (
            <EmptyState variant="inline" icon={ShieldCheck} headingLevel={0}
              title="No se detectaron patrones sospechosos ni controles activados en el período."
              description="Eso no significa que no haya habido intentos fallidos: se ven de a uno en la lista de eventos (Tipo de evento: Accesos fallidos)." />
          ) : (
            <ul className="audit-signals" aria-label="Señales de seguridad">
              {data.senales.map((signal) => <Signal key={`${signal.tipo}-${signal.filtros?.idCuenta ?? signal.filtros?.ip ?? signal.filtros?.refIdentificador ?? signal.filtros?.accion}`}
                signal={signal} onView={onViewEvents} />)}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
