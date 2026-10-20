import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens } from '../../auth/tokenStore.js';
import { jsonResponse, mockApi } from '../../test/helpers.js';
import { renderAt } from '../../test/renderApp.jsx';

const CONFIRM = 'POST /institutions/result-email/confirm';

beforeEach(() => clearTokens());

describe('Confirmación del correo de resultados (GL-08)', () => {
  it('abrir el enlace no confirma: hace falta el botón; el token sale de la barra de direcciones', async () => {
    const { calls } = mockApi({ [CONFIRM]: jsonResponse(200, { confirmado: true, correoEnmascarado: 'pa***@example.com', correoGuardado: true, resultadoEnviado: false }) });
    const user = userEvent.setup();
    renderAt('/confirmar-correo-resultados#token=abc.def.ghi');

    const button = await screen.findByRole('button', { name: /Confirmar mi correo/ });
    expect(calls).toHaveLength(0);
    expect(window.location.hash).toBe('');
    await user.click(button);
    expect(await screen.findByText(/pa\*\*\*@example.com va a recibir tus resultados durante los próximos 12 meses/)).toBeInTheDocument();
    expect(calls).toHaveLength(1);
    expect(calls[0].body).toEqual({ token: 'abc.def.ghi' });
  });

  it('envío puntual: informa que el resultado se envió', async () => {
    mockApi({ [CONFIRM]: jsonResponse(200, { confirmado: true, correoEnmascarado: 'ro***@example.com', correoGuardado: false, resultadoEnviado: true }) });
    const user = userEvent.setup();
    renderAt('/confirmar-correo-resultados#token=uno');
    await user.click(await screen.findByRole('button', { name: /Confirmar mi correo/ }));
    expect(await screen.findByText(/enviamos tu resultado a ro\*\*\*@example.com/)).toBeInTheDocument();
  });

  it('sin token no ofrece confirmar', async () => {
    const { calls } = mockApi({});
    renderAt('/confirmar-correo-resultados');
    expect(await screen.findByText(/El enlace no es válido o venció/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Confirmar mi correo/ })).toBeDisabled();
    expect(calls).toHaveLength(0);
  });
});
