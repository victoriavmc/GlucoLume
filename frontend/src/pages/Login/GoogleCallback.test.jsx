// Callback de Google: el destino tras un error depende del acceso con el que se inició el flujo (A-8, auditoría 2).
// GENERAL -> /login. PLATAFORMA (iniciado desde /plataforma/login) -> /plataforma/login.
import { screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, setPendingGooglePlatform } from '../../auth/tokenStore.js';
import { TOKENS, jsonResponse, mockApi } from '../../test/helpers.js';
import { renderAt } from '../../test/renderApp.jsx';

beforeEach(() => {
  clearTokens();
  window.sessionStorage.clear();
});

function linkBack() {
  return screen.getByRole('link', { name: /Volver a iniciar sesión/ });
}

describe('callback de Google: error con el contexto de acceso', () => {
  it('contexto GENERAL: un error vuelve al login general', async () => {
    setPendingGooglePlatform(false);
    renderAt('/auth/google/callback#error=TOKEN_INVALIDO');
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(linkBack()).toHaveAttribute('href', '/login');
  });

  it('contexto PLATAFORMA: un error vuelve al acceso administrativo, no al general', async () => {
    setPendingGooglePlatform(true);
    renderAt('/auth/google/callback#error=TOKEN_INVALIDO');
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(linkBack()).toHaveAttribute('href', '/plataforma/login');
  });

  it('cancelación en Google (sin código) desde PLATAFORMA conserva el acceso administrativo', async () => {
    setPendingGooglePlatform(true);
    renderAt('/auth/google/callback#error=access_denied');
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(linkBack()).toHaveAttribute('href', '/plataforma/login');
  });

  it('sin marca (sesión sin contexto) el destino por omisión es el login general', async () => {
    renderAt('/auth/google/callback#error=TOKEN_INVALIDO');
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(linkBack()).toHaveAttribute('href', '/login');
  });

  it('el mensaje de error sigue siendo genérico y no muestra tokens ni detalles internos', async () => {
    setPendingGooglePlatform(true);
    renderAt('/auth/google/callback#error=TOKEN_INVALIDO');
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).not.toMatch(/token|Bearer|stack|sql|traceback/i);
  });

  it('cuenta que ya existe (registro) lleva a iniciar sesión por el mismo acceso', async () => {
    setPendingGooglePlatform(true);
    renderAt('/auth/google/callback#error=CUENTA_YA_EXISTE');
    expect(await screen.findByText('Te llevamos a iniciar sesión…')).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Administración de GlucoLume' }, { timeout: 6000 })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Iniciar sesión' })).not.toBeInTheDocument();
  }, 8000);
});

describe('callback de Google: éxito con el contexto de acceso (sin cambios)', () => {
  it('PLATAFORMA: canjea el código y entra al panel administrativo', async () => {
    const { calls } = mockApi({
      'POST /auth/google/exchange': jsonResponse(200, { estado: 'AUTENTICADO', tokens: TOKENS }),
      'GET /auth/me': jsonResponse(200, { idUsuario: 'x', tipoCuenta: 'ADMINISTRADOR_PLATAFORMA', nombre: 'Admin', estado: 'ACTIVO', mfaHabilitado: true }),
      'GET /platform/me': jsonResponse(200, { usuario: 'admin', nombre: 'Admin', estado: 'ACTIVO' }),
    });
    setPendingGooglePlatform(true);
    renderAt('/auth/google/callback#code=codigo-de-prueba');
    await waitFor(() => expect(calls.some((c) => c.url?.includes('/auth/google/exchange'))).toBe(true));
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Acceso con Google' })).not.toBeInTheDocument());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('GENERAL: canjea el código y no muestra error', async () => {
    const { calls } = mockApi({
      'POST /auth/google/exchange': jsonResponse(200, { estado: 'AUTENTICADO', tokens: TOKENS }),
      'GET /auth/me': jsonResponse(200, { idUsuario: 'x', tipoCuenta: 'CONSUMIDOR_FINAL', nombre: 'Ana', estado: 'ACTIVO', mfaHabilitado: false }),
    });
    setPendingGooglePlatform(false);
    renderAt('/auth/google/callback#code=codigo-de-prueba');
    await waitFor(() => expect(calls.some((c) => c.url?.includes('/auth/google/exchange'))).toBe(true));
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Acceso con Google' })).not.toBeInTheDocument());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
