import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { SkipLink } from './SkipLink.jsx';

describe('SkipLink', () => {
  it('es el primer elemento enfocable y lleva el foco al contenido principal sin cambiar la URL', async () => {
    const user = userEvent.setup();
    render(
      <>
        <SkipLink />
        <button type="button">Menú</button>
        <main id="contenido" tabIndex={-1}>Contenido</main>
      </>,
    );
    await user.tab();
    const link = screen.getByRole('link', { name: 'Saltar al contenido' });
    expect(link).toHaveFocus();
    const before = window.location.href;
    await user.keyboard('{Enter}');
    expect(screen.getByRole('main')).toHaveFocus();
    expect(window.location.href).toBe(before);
  });

  it('si el destino no existe no hace nada', async () => {
    const user = userEvent.setup();
    render(<SkipLink targetId="inexistente" />);
    await user.click(screen.getByRole('link', { name: 'Saltar al contenido' }));
    expect(screen.getByRole('link')).toBeInTheDocument();
  });
});
