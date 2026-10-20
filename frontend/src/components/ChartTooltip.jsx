// Tooltip común de los gráficos de evolución (dashboard personal, evolución grupal y vista de un integrante). Siempre dice QUÉ se midió
// (variable), CUÁNTO dio (valor y unidad), CUÁNDO (fecha y hora) y el ORIGEN del dato (experimental o DEMO); en el gráfico grupal también
// A QUIÉN corresponde. Se ancla al punto, pero se abre hacia adentro del gráfico cuando está cerca de un borde, para no quedar cortado.

/** `left` y `top` son porcentajes (0-100) de la posición del punto dentro del gráfico. */
export function ChartTooltip({ left, top, member, variable, value, unit, date, time, demo, origin, note, color }) {
  const horizontal = left < 22 ? ' is-left' : left > 78 ? ' is-right' : '';
  const vertical = top < 34 ? ' is-below' : '';
  return (
    <div className={`chart-tooltip${horizontal}${vertical}`} role="tooltip" style={{ left: `${left}%`, top: `${top}%` }}>
      {member && (
        <span className="chart-tooltip-member">
          {color && <i style={{ background: color }} aria-hidden="true" />}{member}
        </span>
      )}
      <span className="chart-tooltip-variable">{variable}</span>
      <b className="chart-tooltip-value">{value} {unit}</b>
      <span className="chart-tooltip-when">{date}{time ? ` ${time}` : ''}</span>
      <span className={`chart-tooltip-origin${demo ? ' is-demo' : ''}`}>{origin ?? (demo ? 'DEMO (prueba)' : 'Experimental')}</span>
      {note && <span className="chart-tooltip-note">{note}</span>}
    </div>
  );
}
