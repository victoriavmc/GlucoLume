// Enlace «fui yo» del aviso de inicio bloqueado (/liberar-sesion?token=…): sin sesión, un solo envío, sin token no llama a la API.
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens } from '../../auth/tokenStore.js';
import { jsonResponse, mockApi } from '../../test/helpers.js';
import { renderAt } from '../../test/renderApp.jsx';

const LIBERAR = 'POST /auth/sesion-activa/liberar';

beforeEach(() => {
  clearTokens();
  window.sessionStorage.clear();
});

describe('enlace «fui yo» del aviso de inicio bloqueado', () => {
  it('envía el token del enlace, muestra el éxito y quita el token de la barra de direcciones', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({ [LIBERAR]: jsonResponse(200, { mensaje: 'Listo. Ya podés iniciar sesión.' }) });
    renderAt('/liberar-sesion?token=TOKEN_PRUEBA');

    await user.click(await screen.findByRole('button', { name: /Sí, fui yo/ }));

    expect(await screen.findByText(/Cerramos la sesión que estaba abierta/)).toBeInTheDocument();
    expect(calls.find((call) => call.key === LIBERAR).body).toEqual({ token: 'TOKEN_PRUEBA' });
    expect(window.location.search).toBe('');
    expect(screen.getByRole('link', { name: /Iniciar sesión/ })).toHaveAttribute('href', '/login');
  });

  it('un enlace vencido o ya usado muestra el error y no vuelve a intentarlo', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      [LIBERAR]: jsonResponse(400, { codigo: 'TOKEN_INVALIDO', detail: 'El enlace es inválido o ya fue usado.' }),
    });
    renderAt('/liberar-sesion?token=USADO');

    await user.click(await screen.findByRole('button', { name: /Sí, fui yo/ }));

    expect(await screen.findByRole('alert')).toHaveTextContent('ya fue usado');
    expect(screen.getByRole('link', { name: /Ir a iniciar sesión/ })).toHaveAttribute('href', '/login');
    expect(screen.queryByRole('button', { name: /Sí, fui yo/ })).not.toBeInTheDocument();
    await waitFor(() => expect(calls.filter((call) => call.key === LIBERAR)).toHaveLength(1));
  });

  it('sin token no llama a la API y explica qué hacer', async () => {
    const { calls } = mockApi({});
    renderAt('/liberar-sesion');

    expect(await screen.findByRole('alert')).toHaveTextContent('El enlace es inválido');
    expect(calls).toHaveLength(0);
  });
});
