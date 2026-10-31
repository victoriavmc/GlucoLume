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

describe('Barra lateral: insignia de avisos sin leer', () => {
  it('muestra en Notificaciones la cantidad sin leer y no muestra nada si no hay', async () => {
    mockApi({
      'GET /auth/me': jsonResponse(200, ACCOUNT),
      'GET /measurements/evolution': jsonResponse(200, EVOLUTION),
      'GET /notificaciones': jsonResponse(200, { noLeidas: 3, total: 3, hayMas: false, notificaciones: [] }),
    });
    renderAt('/app/inicio');
    expect(await screen.findByRole('link', { name: 'Notificaciones 3' })).toBeInTheDocument();
  });

  it('sin avisos sin leer, Notificaciones no lleva insignia', async () => {
    mockApi({
      'GET /auth/me': jsonResponse(200, ACCOUNT),
      'GET /measurements/evolution': jsonResponse(200, EVOLUTION),
      'GET /notificaciones': jsonResponse(200, { noLeidas: 0, total: 0, hayMas: false, notificaciones: [] }),
    });
    renderAt('/app/inicio');
    expect(await screen.findByRole('link', { name: 'Notificaciones' })).toBeInTheDocument();
    expect(document.querySelector('.app-nav-badge')).toBeNull();
  });
});
