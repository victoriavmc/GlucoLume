// Esqueletos de carga: muestran la ESTRUCTURA de lo que va a aparecer (encabezado, filas, tarjetas) mientras llegan los datos, en vez de una
// pantalla en blanco o un texto suelto. Son decorativos (aria-hidden); lo que se anuncia a los lectores de pantalla es el texto `label`,
// con role="status". No inventan datos: son solo formas grises.

export function SkeletonList({ rows = 5, label = 'Cargando…', className = '' }) {
  return (
    <div className={`skeleton-block ${className}`.trim()} aria-busy="true">
      <p className="sr-only" role="status">{label}</p>
      <ul className="skeleton-rows" aria-hidden="true">
        {Array.from({ length: rows }, (_, index) => (
          <li key={index} className="skeleton-row">
            <span className="skeleton skeleton-line skeleton-line--wide" />
            <span className="skeleton skeleton-line skeleton-line--short" />
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Esqueleto de una pantalla interna: título, una fila de tarjetas y un bloque principal. Reemplaza al spinner de pantalla completa en el
 * contenido (el menú y la barra superior siguen visibles mientras se descarga la pantalla). */
export function PageSkeleton({ label = 'Cargando…' }) {
  return (
    <div className="page is-wide skeleton-page" aria-busy="true">
      <p className="sr-only" role="status">{label}</p>
      <div aria-hidden="true">
        <span className="skeleton skeleton-title" />
        <span className="skeleton skeleton-line skeleton-line--short" />
        <div className="skeleton-cards">
          <span className="skeleton skeleton-card" />
          <span className="skeleton skeleton-card" />
          <span className="skeleton skeleton-card" />
        </div>
        <span className="skeleton skeleton-panel" />
      </div>
    </div>
  );
}
