// Rutas del acceso administrativo (A-7, auditoría 2). /plataforma/login es la principal. /administracion/login es un alias que
// redirige a ella y sigue funcionando para marcadores y enlaces antiguos. Ninguna ruta da acceso por sí misma.
import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens } from '../../auth/tokenStore.js';
import { jsonResponse, mockApi } from '../../test/helpers.js';
import { renderAt } from '../../test/renderApp.jsx';

beforeEach(() => {
  clearTokens();
  mockApi({
    'GET /auth/me': jsonResponse(401, { codigo: 'NO_AUTENTICADO', detail: 'Sin sesión.' }),
    'POST /auth/refresh': jsonResponse(401, { codigo: 'NO_AUTENTICADO', detail: 'Sin sesión.' }),
    'GET /platform/me': jsonResponse(401, { codigo: 'NO_AUTENTICADO', detail: 'Sin sesión.' }),
  });
});

describe('acceso administrativo: rutas principales y alias', () => {
  it('/plataforma/login muestra el acceso administrativo', async () => {
    renderAt('/plataforma/login');
    expect(await screen.findByRole('heading', { name: 'Administración de GlucoLume' })).toBeInTheDocument();
  });

  it('/administracion/login (alias) lleva al mismo acceso administrativo', async () => {
    renderAt('/administracion/login');
    expect(await screen.findByRole('heading', { name: 'Administración de GlucoLume' })).toBeInTheDocument();
  });

  it('el acceso general /login no es el administrativo', async () => {
    renderAt('/login');
    expect(await screen.findByRole('heading', { name: 'Iniciar sesión' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Administración de GlucoLume' })).not.toBeInTheDocument();
  });

  it('la recuperación administrativa es la única ruta: /plataforma/recuperar', async () => {
    renderAt('/plataforma/login');
    expect(await screen.findByRole('link', { name: '¿Olvidaste tu contraseña?' })).toHaveAttribute('href', '/plataforma/recuperar');
  });
});

describe('enlaces internos del flujo administrativo', () => {
  it('la pantalla de activación vuelve al acceso administrativo principal (no al alias)', async () => {
    renderAt('/administracion/activar#codigo=codigo-de-prueba');
    const back = await screen.findByRole('link', { name: 'Volver al acceso administrativo' });
    expect(back).toHaveAttribute('href', '/plataforma/login');
  });
});
