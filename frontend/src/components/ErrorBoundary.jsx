import { Component } from 'react';

import { EmptyState } from './EmptyState.jsx';

// Captura los errores de dibujado de toda la aplicación (H-15): sin esto, un fallo al renderizar deja la pantalla en blanco hasta recargar.
// Muestra un mensaje genérico con la opción de recargar o volver al inicio. El detalle del error va solo a la consola del navegador: nunca
// se muestra ni se envía, porque el mensaje puede contener datos de la persona.

export class ErrorBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error) {
    console.error('Error de interfaz no controlado:', error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="error-boundary" role="alert">
        <EmptyState
          variant="framed"
          headingLevel={1}
          title="Algo salió mal"
          description="Ocurrió un error inesperado al mostrar esta pantalla. Tus datos no se modificaron. Recargá la página para continuar."
          action={(
            <>
              <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>Recargar</button>
              {' '}
              <a className="btn btn-outline" href="/">Ir al inicio</a>
            </>
          )}
        />
      </main>
    );
  }
}
