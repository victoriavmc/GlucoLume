// Actividad de la institución: resumen administrativo y operativo (no el historial técnico). El panel muestra las últimas 5 y la página
// Actividad (`/actividad`) las últimas 20. Lo curado y filtrado por permisos lo decide el backend; no requiere ser propietario.
// La trazabilidad técnica vive en Auditoría, un módulo aparte.

import { Activity, ArrowRight, Building2, Cpu, FileText, HeartPulse, ShieldAlert, Stethoscope, Table2, UserRound, UsersRound } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import * as institutionsApi from '../../../api/institutionsApi.js';
import { Badge } from '../../../components/Badge.jsx';

// Ícono de cada categoría de actividad (el backend informa la categoría; acá solo se elige cómo se dibuja).
const CATEGORY_ICONS = {
  INSTITUCION: Building2, MODERADORES: UsersRound, OPERADORES: UserRound, PACIENTES: HeartPulse, MEDICIONES: Stethoscope, DISPOSITIVOS: Cpu, MATRICES: Table2, SEGURIDAD: ShieldAlert,
};

/** «Lunes 15/10/2026 — 16:15»: día, fecha y hora de la actividad. */
function activityWhen(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const weekday = date.toLocaleDateString('es-AR', { weekday: 'long' });
  const day = date.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' });
  const time = date.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hour12: false });
  return `${weekday.charAt(0).toUpperCase()}${weekday.slice(1)} ${day} — ${time}`;
}

/**
 * Actividad reciente: resumen administrativo y operativo (no el historial técnico). Lo curado y filtrado por permisos lo decide el
 * backend a partir de la auditoría; cada actividad enlaza a su pantalla cuando el rol puede abrirla. «Ver toda la actividad» lleva a la
 * página Actividad (no a Auditoría, que es la trazabilidad técnica y solo la consulta el propietario).
 */
export function InstitutionActivity({ institution, full = false }) {
  const own = institution.rolInstitucion === 'OPERADOR'; // el operador ve solo su propia actividad (el backend la filtra por su usuario)
  const [items, setItems] = useState(null);
  const [failed, setFailed] = useState(false);
  const base = `/app/instituciones/${institution.idInstitucion}`;

  useEffect(() => {
    let active = true;
    institutionsApi.getRecentActivity(institution.idInstitucion, full ? 20 : 5).then(
      (result) => active && setItems(result.items),
      () => active && setFailed(true),
    );
    return () => { active = false; };
  }, [institution.idInstitucion, full]);

  return (
    <section className="panel" aria-labelledby="inst-actividad">
      <div className="panel-head">
        <div className="panel-title">
          <span className="panel-icon is-lg" aria-hidden="true"><Activity size={26} /></span>
          <div>
            <h2 id="inst-actividad">{own ? (full ? 'Mi actividad' : 'Mi actividad reciente') : (full ? 'Actividad' : 'Actividad reciente')}</h2>
            <p>{own ? 'Lo que hiciste y lo que te asignaron en la institución: tus mediciones, tus pacientes y tus transferencias.'
              : full ? 'Lo último que pasó en la institución: resumen administrativo y operativo. El detalle técnico está en Auditoría.' : 'Lo último que pasó en la institución.'}</p>
          </div>
        </div>
        {!full && (
          <Link to="actividad" className="summary-link">
            Ver toda la actividad <ArrowRight size={16} aria-hidden="true" />
          </Link>
        )}
      </div>
      {failed ? (
        <p className="field-hint">No pudimos cargar la actividad ahora.</p>
      ) : items === null ? (
        <p className="field-hint" role="status">Cargando actividad…</p>
      ) : items.length === 0 ? (
        <p className="field-hint">{own ? 'Todavía no tenés actividad propia registrada.' : 'Todavía no hay actividad registrada.'}</p>
      ) : (
        <ul className="activity-list is-cards" aria-label="Actividad reciente">
          {items.map((item, index) => {
            const Icon = CATEGORY_ICONS[item.categoria] ?? FileText;
            const content = (
              <>
                <span className="panel-icon" aria-hidden="true"><Icon size={20} /></span>
                <span className="activity-text">
                  <b>{item.titulo}</b>
                  {item.entidad && <span className="activity-entity">{item.entidad}</span>}
                  <small>Realizado por {item.usuario ?? 'el sistema'}</small>
                </span>
                <span className="activity-meta">
                  <time className="activity-date" dateTime={item.fechaHora}>{activityWhen(item.fechaHora)}</time>
                  {item.rechazado && <Badge tone="danger">Rechazado</Badge>}
                  {item.critica && !item.rechazado && <Badge tone="warning">Crítica</Badge>}
                </span>
              </>
            );
            // Quien puede consultar la auditoría (el backend envía `idAuditoria` solo a él) abre el evento puntual; el resto, la pantalla relacionada.
            const target = item.idAuditoria ? `auditoria/${item.idAuditoria}` : item.ruta;
            return (
              <li key={`${item.idAuditoria ?? 'a'}-${index}`}>
                {target ? <Link to={`${base}/${target}`} className="activity-link">{content}</Link> : <div className="activity-link">{content}</div>}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

