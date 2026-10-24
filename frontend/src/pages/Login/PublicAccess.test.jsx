import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { mockApi } from '../../test/helpers.js';
import { renderAt } from '../../test/renderApp.jsx';

// Todas las pantallas públicas (landing, acceso, registro, recuperación y privacidad) empiezan con «Saltar al contenido».
describe('Pantallas públicas: saltar al contenido', () => {
  it.each(['/', '/login', '/registro', '/recuperar-contrasena', '/privacidad'])('%s: el primer Tab llega al enlace y Enter lleva el foco al contenido principal', async (path) => {
    mockApi({});
    const user = userEvent.setup();
    renderAt(path);
    await screen.findByRole('main'); // las pantallas públicas no iniciales se cargan de forma diferida
    await user.tab();
    const link = screen.getByRole('link', { name: 'Saltar al contenido' });
    expect(link).toHaveFocus();
    const before = window.location.href;
    await user.keyboard('{Enter}');
    expect(screen.getByRole('main')).toHaveFocus();
    expect(window.location.href).toBe(before);
  });

  it('el contenido principal es único y está identificado como destino del enlace', () => {
    mockApi({});
    renderAt('/login');
    expect(screen.getAllByRole('main')).toHaveLength(1);
    expect(screen.getByRole('main')).toHaveAttribute('id', 'contenido');
  });
});
