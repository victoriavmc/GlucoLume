import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, getAccessToken } from '../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../test/helpers.js';
import { renderAt } from '../../test/renderApp.jsx';

const STARTED = { recoveryToken: 'flujo-1', correoEnmascarado: 'vi******@example.com', vigenciaMinutos: 10 };

beforeEach(() => clearTokens());

async function reachMfaStep(user) {
  await user.type(screen.getByLabelText('Correo electrónico o usuario'), 'victoria');
  await user.type(screen.getByLabelText('Contraseña'), 'Clave#2026');
  await user.click(screen.getByRole('button', { name: /^Iniciar sesión/ }));
  await screen.findByLabelText('Código de verificación');
}

describe('Perdí acceso a mi aplicación autenticadora', () => {
  it('login local: contraseña + código del correo -> sesión con MFA desactivado', async () => {
    const { calls } = mockApi({
      'POST /auth/login': jsonResponse(200, { estado: 'MFA_REQUERIDO', challengeToken: 'desafio' }),
      'POST /auth/mfa/recovery/start': [
        jsonResponse(403, { codigo: 'PASSWORD_INCORRECTA', detail: 'La contraseña ingresada no es correcta.' }),
        jsonResponse(200, STARTED),
      ],
      'POST /auth/mfa/recovery/verify': [
        jsonResponse(401, { codigo: 'CODIGO_INVALIDO', detail: 'El código ingresado no es válido.' }),
        jsonResponse(200, { estado: 'AUTENTICADO', tokens: TOKENS }),
      ],
      'GET /auth/me': jsonResponse(200, ACCOUNT),
    });
    const user = userEvent.setup();
    renderAt('/login');
    await reachMfaStep(user);

    await user.click(screen.getByRole('button', { name: '¿Perdiste acceso a tu aplicación autenticadora?' }));
    expect(screen.getByText('Para proteger tu cuenta, confirmá tu contraseña.')).toBeInTheDocument();
    expect(screen.queryByLabelText(/correo/i, { selector: 'input[type="email"]' })).not.toBeInTheDocument();

    await user.type(screen.getByLabelText('Contraseña actual'), 'Mala#2026');
    await user.click(screen.getByRole('button', { name: 'Continuar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('La contraseña ingresada no es correcta.');

    await user.clear(screen.getByLabelText('Contraseña actual'));
    await user.type(screen.getByLabelText('Contraseña actual'), 'Clave#2026');
    await user.click(screen.getByRole('button', { name: 'Continuar' }));
    expect(await screen.findByText('vi******@example.com')).toBeInTheDocument();

    await user.type(screen.getByLabelText('Código enviado a tu correo'), '000000');
    await user.click(screen.getByRole('button', { name: 'Verificar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('El código ingresado no es válido.');
    expect(getAccessToken()).toBeNull();

    await user.type(screen.getByLabelText('Código enviado a tu correo'), '482913');
    await user.click(screen.getByRole('button', { name: 'Verificar' }));

    expect(await screen.findByRole('heading', { name: 'Hola, Victoria' })).toBeInTheDocument();
    expect(screen.getByText(/Acceso recuperado correctamente/)).toBeInTheDocument();
    expect(screen.getByText(/Podés volver a configurarla desde Seguridad/)).toBeInTheDocument();

    const starts = calls.filter((c) => c.key === 'POST /auth/mfa/recovery/start').map((c) => c.body);
    expect(starts).toEqual([
      { challengeToken: 'desafio', password: 'Mala#2026' },
      { challengeToken: 'desafio', password: 'Clave#2026' },
    ]);
    const verifies = calls.filter((c) => c.key === 'POST /auth/mfa/recovery/verify').map((c) => c.body);
    expect(verifies).toEqual([
      { recoveryToken: 'flujo-1', codigo: '000000' },
      { recoveryToken: 'flujo-1', codigo: '482913' },
    ]);
    // El destinatario nunca sale del formulario: no se envía ningún correo desde el frontend.
    for (const body of [...starts, ...verifies]) expect(Object.keys(body)).not.toContain('correoElectronico');
  });

  it('código vencido y reenvío de un código nuevo', async () => {
    const { calls } = mockApi({
      'POST /auth/login': jsonResponse(200, { estado: 'MFA_REQUERIDO', challengeToken: 'desafio' }),
      'POST /auth/mfa/recovery/start': [jsonResponse(200, STARTED), jsonResponse(200, { ...STARTED, recoveryToken: 'flujo-2' })],
      'POST /auth/mfa/recovery/verify': jsonResponse(410, {
        codigo: 'CODIGO_VENCIDO', detail: 'El código venció. Solicitá uno nuevo.',
      }),
    });
    const user = userEvent.setup();
    renderAt('/login');
    await reachMfaStep(user);
    await user.click(screen.getByRole('button', { name: '¿Perdiste acceso a tu aplicación autenticadora?' }));
    await user.type(screen.getByLabelText('Contraseña actual'), 'Clave#2026');
    await user.click(screen.getByRole('button', { name: 'Continuar' }));
    await user.type(await screen.findByLabelText('Código enviado a tu correo'), '111111');
    await user.click(screen.getByRole('button', { name: 'Verificar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('El código venció. Solicitá uno nuevo.');

    await user.click(screen.getByRole('button', { name: /Enviar un código nuevo/ }));
    expect(await screen.findByText(/Te enviamos un código nuevo/)).toBeInTheDocument();
    expect(calls.filter((c) => c.key === 'POST /auth/mfa/recovery/start')).toHaveLength(2);
  });

  it('valida el código antes de enviarlo y se puede volver al código de la aplicación', async () => {
    const { calls } = mockApi({
      'POST /auth/login': jsonResponse(200, { estado: 'MFA_REQUERIDO', challengeToken: 'desafio' }),
      'POST /auth/mfa/recovery/start': jsonResponse(200, STARTED),
    });
    const user = userEvent.setup();
    renderAt('/login');
    await reachMfaStep(user);
    await user.click(screen.getByRole('button', { name: '¿Perdiste acceso a tu aplicación autenticadora?' }));
    await user.click(screen.getByRole('button', { name: 'Continuar' }));
    expect(screen.getByText('Ingresá tu contraseña actual.')).toBeInTheDocument();
    expect(calls.some((c) => c.key === 'POST /auth/mfa/recovery/start')).toBe(false);

    await user.type(screen.getByLabelText('Contraseña actual'), 'Clave#2026');
    await user.click(screen.getByRole('button', { name: 'Continuar' }));
    await user.click(await screen.findByRole('button', { name: 'Verificar' }));
    expect(screen.getByText('Ingresá el código de 6 dígitos que te enviamos.')).toBeInTheDocument();
    expect(calls.some((c) => c.key === 'POST /auth/mfa/recovery/verify')).toBe(false);

    await user.click(screen.getByRole('button', { name: /Volver al código de la aplicación/ }));
    expect(screen.getByLabelText('Código de verificación')).toBeInTheDocument();
  });

  it('desafío vencido: pide volver a iniciar sesión', async () => {
    mockApi({
      'POST /auth/login': jsonResponse(200, { estado: 'MFA_REQUERIDO', challengeToken: 'desafio' }),
      'POST /auth/mfa/recovery/start': jsonResponse(401, { codigo: 'TOKEN_INVALIDO', detail: 'x' }),
    });
    const user = userEvent.setup();
    renderAt('/login');
    await reachMfaStep(user);
    await user.click(screen.getByRole('button', { name: '¿Perdiste acceso a tu aplicación autenticadora?' }));
    await user.type(screen.getByLabelText('Contraseña actual'), 'Clave#2026');
    await user.click(screen.getByRole('button', { name: 'Continuar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Volvé a iniciar sesión');
  });

  it('ingreso con Google: cuenta solo Google no pide contraseña', async () => {
    const { calls } = mockApi({
      'POST /auth/google/exchange': jsonResponse(200, { estado: 'MFA_REQUERIDO', challengeToken: 'desafio-g' }),
      'POST /auth/mfa/recovery/start': jsonResponse(200, STARTED),
      'POST /auth/mfa/recovery/verify': jsonResponse(200, { estado: 'AUTENTICADO', tokens: TOKENS }),
      'GET /auth/me': jsonResponse(200, ACCOUNT),
    });
    const user = userEvent.setup();
    renderAt('/auth/google/callback#code=abc');
    await user.click(await screen.findByRole('button', { name: '¿Perdiste acceso a tu aplicación autenticadora?' }));

    expect(await screen.findByText('vi******@example.com')).toBeInTheDocument();
    expect(screen.queryByLabelText('Contraseña actual')).not.toBeInTheDocument();
    expect(calls.find((c) => c.key === 'POST /auth/mfa/recovery/start').body).toEqual({ challengeToken: 'desafio-g' });

    await user.type(screen.getByLabelText('Código enviado a tu correo'), '482913');
    await user.click(screen.getByRole('button', { name: 'Verificar' }));
    expect(await screen.findByText(/Acceso recuperado correctamente/)).toBeInTheDocument();
  });

  it('ingreso con Google de una cuenta con contraseña: el backend la pide y se solicita', async () => {
    const { calls } = mockApi({
      'POST /auth/google/exchange': jsonResponse(200, { estado: 'MFA_REQUERIDO', challengeToken: 'desafio-g' }),
      'POST /auth/mfa/recovery/start': [
        jsonResponse(422, { codigo: 'PASSWORD_REQUERIDA', detail: 'x' }),
        jsonResponse(200, STARTED),
      ],
    });
    const user = userEvent.setup();
    renderAt('/auth/google/callback#code=abc');
    await user.click(await screen.findByRole('button', { name: '¿Perdiste acceso a tu aplicación autenticadora?' }));
    await user.type(await screen.findByLabelText('Contraseña actual'), 'Clave#2026');
    await user.click(screen.getByRole('button', { name: 'Continuar' }));
    expect(await screen.findByText('vi******@example.com')).toBeInTheDocument();
    expect(calls.filter((c) => c.key === 'POST /auth/mfa/recovery/start').map((c) => c.body)).toEqual([
      { challengeToken: 'desafio-g' },
      { challengeToken: 'desafio-g', password: 'Clave#2026' },
    ]);
  });

  it('la desactivación normal desde Seguridad sigue siendo un flujo distinto', async () => {
    // Con sesión, desactivar exige un código del autenticador o de recuperación (no el correo).
    const { saveTokens } = await import('../../auth/tokenStore.js');
    saveTokens(TOKENS, false);
    mockApi({ 'GET /auth/me': jsonResponse(200, { ...ACCOUNT, mfaHabilitado: true }) });
    const user = userEvent.setup();
    renderAt('/app/seguridad');
    const mfa = await screen.findByRole('region', { name: 'Verificación en dos pasos' });
    await user.click(within(mfa).getByRole('button', { name: 'Desactivar verificación' }));
    expect(within(mfa).getByLabelText('Código de verificación')).toBeInTheDocument();
    // La recuperación es una alternativa aparte, no el campo de código.
    expect(within(mfa).getByText(/Perdiste acceso a tu aplicación autenticadora y a tus códigos/)).toBeInTheDocument();
  });
});
