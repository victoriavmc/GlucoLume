import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../test/helpers.js';
import { renderAt } from '../test/renderApp.jsx';

const EVOLUTION = { origen: 'TODOS', desde: null, hasta: null, puntos: [], truncado: false, estadisticas: { experimental: null, demo: null } };

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

describe('Layout del espacio privado: accesibilidad base', () => {
  it('el primer Tab llega a «Saltar al contenido» y lleva el foco al contenido principal', async () => {
    mockApi({ 'GET /auth/me': jsonResponse(200, ACCOUNT), 'GET /measurements/evolution': jsonResponse(200, EVOLUTION) });
    const user = userEvent.setup();
    renderAt('/app/inicio');
    expect(await screen.findByRole('heading', { name: 'Hola, Victoria' })).toBeInTheDocument();
    await user.tab();
    expect(screen.getByRole('link', { name: 'Saltar al contenido' })).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(screen.getByRole('main')).toHaveFocus();
  });
});
