// Cupos de cuentas institucionales: capacidad máxima, cuentas activas, disponibles y utilización. TODO viene del backend (/quota), que
// cuenta las relaciones activas (propietario, moderadores y operadores; sin invitaciones pendientes ni bajas) de ESTA institución. Los
// estados visuales (disponible, próximo al límite desde el 80 %, completa) son solo informativos: el límite real lo aplica FastAPI al
// incorporar. Lo ven propietario y moderador; el operador no.

import { Gauge, TriangleAlert, UsersRound } from 'lucide-react';
import { useEffect, useState } from 'react';

import * as institutionsApi from '../../../api/institutionsApi.js';
import { Badge, toneFromClass } from '../../../components/Badge.jsx';
import { Alert } from '../../../components/FormControls.jsx';
import { Kpi, KpiGrid } from '../../../components/dashboard.jsx';
import './Quota.css';

export const QUOTA_STATES = {
  DISPONIBLE: { label: 'Disponible', tone: 'is-on' },
  PROXIMO_AL_LIMITE: { label: 'Próximo al límite', tone: 'is-warn' },
  COMPLETA: { label: 'Capacidad completa', tone: 'is-denied' },
  EXCEDIDA: { label: 'Límite excedido', tone: 'is-denied' },
};

const number = (value) => Number(value).toLocaleString('es-AR');
const percent = (value) => `${Number(value).toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 1 })} %`;

/** Cupos de la institución; se vuelve a pedir cuando cambia `refreshKey` (por ejemplo, después de una baja o una incorporación). */
export function useQuota(institution, refreshKey = 0) {
  const [quota, setQuota] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    institutionsApi.getQuota(institution.idInstitucion).then(
      (result) => active && (setQuota(result), setFailed(false)),
      () => active && setFailed(true),
    );
    return () => { active = false; };
  }, [institution.idInstitucion, refreshKey]);
  return { quota, failed };
}

export function QuotaBar({ quota }) {
  const state = QUOTA_STATES[quota.estado];
  return (
    <div className="quota-bar-wrap">
      <div className="quota-bar" role="progressbar" aria-label="Utilización de cupos" aria-valuemin={0} aria-valuemax={100}
        aria-valuenow={quota.porcentajeUtilizacion} aria-valuetext={`${percent(quota.porcentajeUtilizacion)} de utilización`}>
        <span className={`quota-fill ${state.tone}`} style={{ width: `${Math.min(100, quota.porcentajeUtilizacion)}%` }} />
      </div>
      <Badge tone={toneFromClass(state.tone)}>{state.label}</Badge>
    </div>
  );
}

/** Sección «Cupos institucionales» del dashboard (propietario y moderador). */
export function QuotaSection({ institution }) {
  const { quota, failed } = useQuota(institution);
  return (
    <section className="panel quota-panel" aria-labelledby="inst-cupos">
      <div className="panel-title">
        <span className="panel-icon is-lg" aria-hidden="true"><Gauge size={26} /></span>
        <div>
          <h2 id="inst-cupos">Cupos institucionales</h2>
          <p>Cuentas institucionales activas frente a la capacidad máxima de esta institución.</p>
        </div>
      </div>
      {failed && <Alert>No pudimos cargar los cupos ahora.</Alert>}
      {!quota && !failed && <p className="field-hint" role="status">Cargando cupos…</p>}
      {quota && (
        <>
          <KpiGrid label="Cupos institucionales" compact>
            <Kpi icon={Gauge} label="Capacidad máxima" value={number(quota.capacidadMaximaUsuarios)} />
            <Kpi icon={UsersRound} label="Cuentas activas" value={number(quota.usuariosActivos)} />
            <Kpi icon={UsersRound} tone="ok" label="Disponibles" value={number(quota.cuposDisponibles)} />
            <Kpi icon={Gauge} tone={quota.estado === 'DISPONIBLE' ? undefined : 'warn'} label="Utilización" value={percent(quota.porcentajeUtilizacion)} />
          </KpiGrid>
          <QuotaBar quota={quota} />
          {quota.estado === 'COMPLETA' && (
            <Alert kind="info">
              <TriangleAlert size={16} aria-hidden="true" /> La institución alcanzó su capacidad máxima de cuentas activas. Para incorporar a otra persona,
              es necesario liberar un cupo o ampliar la capacidad. Las invitaciones pendientes no consumen cupo y se podrán aceptar cuando haya disponibilidad.
            </Alert>
          )}
          {quota.estado === 'EXCEDIDA' && (
            <Alert kind="info">
              <TriangleAlert size={16} aria-hidden="true" /> La administración de GlucoLume redujo el límite de cuentas: hay {number(quota.excedente)}{' '}
              {quota.excedente === 1 ? 'cuenta activa' : 'cuentas activas'} por encima. Todas las cuentas se conservan, pero no se pueden incorporar nuevas
              personas hasta liberar cupos o que se amplíe el límite.
            </Alert>
          )}
          {quota.estado === 'PROXIMO_AL_LIMITE' && (
            <p className="field-hint">La institución está cerca de su capacidad: quedan {number(quota.cuposDisponibles)} cupos.</p>
          )}
        </>
      )}
    </section>
  );
}

/** Línea breve para Personal: «325 de 1.000 cuentas activas · 675 cupos disponibles». */
export function QuotaLine({ institution, refreshKey }) {
  const { quota } = useQuota(institution, refreshKey);
  if (!quota) return null;
  return (
    <div className="quota-line" aria-label="Cupos del personal institucional">
      <p>
        <b>{number(quota.usuariosActivos)} de {number(quota.capacidadMaximaUsuarios)} cuentas activas</b> · {number(quota.cuposDisponibles)}{' '}
        {quota.cuposDisponibles === 1 ? 'cupo disponible' : 'cupos disponibles'}
      </p>
      <QuotaBar quota={quota} />
      {quota.estado === 'EXCEDIDA' && (
        <small className="field-hint">Límite excedido en {number(quota.excedente)}: no se pueden incorporar más personas hasta regularizarlo.</small>
      )}
      {quota.estado === 'COMPLETA' && (
        <small className="field-hint">Capacidad completa: no se pueden incorporar más personas hasta liberar un cupo o ampliar la capacidad.</small>
      )}
    </div>
  );
}
