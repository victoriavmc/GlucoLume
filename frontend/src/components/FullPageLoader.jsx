export function FullPageLoader({ label = 'Cargando…' }) {
  return (
    <div className="full-page-loader" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
