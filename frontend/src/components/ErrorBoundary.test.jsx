import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ErrorBoundary } from './ErrorBoundary.jsx';

function Roto() {
  throw new Error('detalle-interno-que-no-debe-verse');
}

describe('ErrorBoundary', () => {
  afterEach(() => vi.restoreAllMocks());

  it('deja pasar a los hijos cuando no hay error', () => {
    render(<ErrorBoundary><p>Contenido</p></ErrorBoundary>);
    expect(screen.getByText('Contenido')).toBeInTheDocument();
  });

  it('ante un error de dibujado muestra un mensaje genérico con opciones de recuperación, sin el detalle del error', () => {
    const log = vi.spyOn(console, 'error').mockImplementation(() => {});
    render(<ErrorBoundary><Roto /></ErrorBoundary>);
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Algo salió mal' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Recargar' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ir al inicio' })).toHaveAttribute('href', '/');
    expect(document.body.textContent).not.toContain('detalle-interno-que-no-debe-verse');
    expect(log).toHaveBeenCalled();
  });
});
