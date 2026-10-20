import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens } from '../../auth/tokenStore.js';
import { jsonResponse, mockApi } from '../../test/helpers.js';
import { renderAt } from '../../test/renderApp.jsx';

beforeEach(() => clearTokens());

describe('Verificación de correo', () => {
  it('verifica el token una sola vez, lo quita de la URL y ofrece iniciar sesión', async () => {
    const { calls } = mockApi({
      'GET /auth/verify-email': jsonResponse(200, { mensaje: 'Correo verificado. Ya podés iniciar sesión.' }),
    });
    renderAt('/verificar-correo?token=abc123');

    expect(await screen.findByRole('heading', { name: '¡Correo verificado!' })).toBeInTheDocument();
    expect(calls).toHaveLength(1);
    expect(new URL(calls[0].url).searchParams.get('token')).toBe('abc123');
    expect(window.location.search).toBe('');
    // El navbar también tiene "Iniciar sesión": se busca el botón de la tarjeta de resultado.
    const card = screen.getByRole('heading', { name: '¡Correo verificado!' }).closest('.auth-form');
    expect(within(card).getByRole('link', { name: /Iniciar sesión/ })).toHaveAttribute('href', '/login');
  });

  it('enlace inválido o ya usado: permite pedir uno nuevo', async () => {
    const { calls } = mockApi({
      'GET /auth/verify-email': jsonResponse(401, { codigo: 'TOKEN_INVALIDO', detail: 'x' }),
      'POST /auth/verify-email/resend': jsonResponse(202, { mensaje: 'ok' }),
    });
    const user = userEvent.setup();
    renderAt('/verificar-correo?token=usado');

    expect(await screen.findByText(/no es válido o ya fue utilizado/)).toBeInTheDocument();
    await user.type(screen.getByLabelText('Correo electrónico de tu cuenta'), 'laura@example.com');
    await user.click(screen.getByRole('button', { name: /Enviar un enlace nuevo/ }));
    expect(await screen.findByText(/Te enviamos un nuevo correo de verificación/)).toBeInTheDocument();
    expect(calls.at(-1).body).toEqual({ correoElectronico: 'laura@example.com' });
  });

  it('plazo vencido: lleva a registrarse de nuevo', async () => {
    mockApi({
      'GET /auth/verify-email': jsonResponse(410, { codigo: 'VERIFICACION_EXPIRADA', detail: 'x' }),
    });
    renderAt('/verificar-correo?token=viejo');
    expect(await screen.findByText(/plazo para verificar la cuenta venció/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Registrarme nuevamente/ })).toHaveAttribute('href', '/registro');
  });

  it('sin token no llama a la API', async () => {
    const { fetchMock } = mockApi({});
    renderAt('/verificar-correo');
    expect(await screen.findByText(/no es válido o ya fue utilizado/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
