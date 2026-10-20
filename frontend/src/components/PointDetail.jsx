// Detalle de UN punto seleccionado de un gráfico de evolución (dashboard personal y módulo Grupo), dentro de la misma vista: qué variable es,
// cuánto dio, cuándo (fecha y hora) y de qué origen (experimental o DEMO), con un resumen breve y, como opción secundaria, el detalle completo.
// El contenido lo arma quien lo usa con datos reales; acá solo se presenta, igual en todos los gráficos.

import { OriginBadge } from './Badge.jsx';

export function PointDetail({ member, color, variable, value, unit, date, time, demo, summary, others, children }) {
  return (
    <div className="point-detail" role="region" aria-label="Medición seleccionada">
      <div className="point-detail-head">
        <div className="point-detail-title">
          {member && (
            <span className="point-detail-member">{color && <i style={{ background: color }} aria-hidden="true" />}{member}</span>
          )}
          <span className="point-detail-variable">{variable}</span>
        </div>
        <div className="point-detail-main">
          <b className="point-detail-value">{value} {unit}</b>
          <OriginBadge origin={demo ? 'DEMO' : 'EXPERIMENTAL'}>{demo ? 'DEMO (prueba)' : 'Experimental'}</OriginBadge>
        </div>
      </div>
      <dl className="point-detail-facts">
        <div><dt>Fecha</dt><dd>{date}</dd></div>
        {time && <div><dt>Hora</dt><dd>{time}</dd></div>}
      </dl>
      {summary && <p className="point-detail-summary">{summary}</p>}
      {others && others.length > 0 && (
        <ul className="point-detail-others" aria-label="Otros valores de esta medición">
          {others.map((item) => <li key={item.label}><small>{item.label}</small><b>{item.value}</b></li>)}
        </ul>
      )}
      {children}
    </div>
  );
}
