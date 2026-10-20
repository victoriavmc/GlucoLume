import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { clearTokens, getAccessToken, getRefreshToken, saveTokens } from './auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from './test/helpers.js';
import { renderAt } from './test/renderApp.jsx';

async function fillLogin(user, identificador = 'victoria@example.com', password = 'Clave#2026') {
  await user.type(screen.getByLabelText('Correo electrónico o usuario'), identificador);
  await user.type(screen.getByLabelText('Contraseña'), password);
}

beforeEach(() => clearTokens());

describe('Landing', () => {
  it('muestra el hero, el disclaimer y los CTA hacia login y registro', () => {
    mockApi({});
    renderAt('/');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Tecnología al servicio del bienestar');
    expect(screen.getByRole('complementary')).toHaveTextContent('GlucoLume no es un dispositivo médico.');
    const nav = screen.getByRole('banner');
    expect(within(nav).getByRole('link', { name: 'Iniciar sesión' })).toHaveAttribute('href', '/login');
    expect(within(nav).getByRole('link', { name: 'Registrarse' })).toHaveAttribute('href', '/registro');
    for (const label of ['Usuario individual', 'Grupo', 'Institución']) {
      expect(screen.getByRole('heading', { name: label })).toBeInTheDocument();
    }
    expect(within(nav).getByRole('button', { name: /menú/ })).toBeInTheDocument();
  });
});

describe('Login local', () => {
  it('valida los campos antes de llamar a la API', async () => {
    const { fetchMock } = mockApi({});
    const user = userEvent.setup();
    renderAt('/login');

    await user.click(screen.getByRole('button', { name: /^Iniciar sesión/ }));

    expect(screen.getByText('Ingresá tu correo electrónico o nombre de usuario.')).toBeInTheDocument();
    expect(screen.getByText('Ingresá tu contraseña.')).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('inicia sesión contra /auth/login, carga /auth/me y entra a /app', async () => {
    const { calls } = mockApi({
      'POST /auth/login': jsonResponse(200, { estado: 'AUTENTICADO', tokens: TOKENS, camposFaltantes: [] }),
      'GET /auth/me': jsonResponse(200, ACCOUNT),
    });
    const user = userEvent.setup();
    renderAt('/login');

    await fillLogin(user, '  victoria  ');
    await user.click(screen.getByRole('button', { name: /^Iniciar sesión/ }));

    expect(await screen.findByRole('heading', { name: 'Hola, Victoria' })).toBeInTheDocument();
    expect(calls[0].body).toEqual({ identificador: 'victoria', password: 'Clave#2026' });
    expect(calls[1].options.headers.Authorization).toBe('Bearer access-1');
    // Sin Recordarme: refresh token solo en sessionStorage.
    expect(window.sessionStorage.getItem('glucolume.refreshToken')).toBe('refresh-1');
    expect(window.localStorage.getItem('glucolume.refreshToken')).toBeNull();
  });

  it('con Recordarme guarda el refresh token en localStorage', async () => {
    mockApi({
      'POST /auth/login': jsonResponse(200, { estado: 'AUTENTICADO', tokens: TOKENS }),
      'GET /auth/me': jsonResponse(200, ACCOUNT),
    });
    const user = userEvent.setup();
    renderAt('/login');
    await fillLogin(user);
    await user.click(screen.getByRole('checkbox', { name: 'Recordarme' }));
    await user.click(screen.getByRole('button', { name: /^Iniciar sesión/ }));
    await screen.findByRole('heading', { name: 'Hola, Victoria' });
    expect(window.localStorage.getItem('glucolume.refreshToken')).toBe('refresh-1');
  });

  it('muestra un error amigable y limpia la contraseña si las credenciales son incorrectas', async () => {
    mockApi({
      'POST /auth/login': jsonResponse(401, { codigo: 'CREDENCIALES_INVALIDAS', detail: 'Credenciales inválidas.' }),
    });
    const user = userEvent.setup();
    renderAt('/login');
    await fillLogin(user);
    await user.click(screen.getByRole('button', { name: /^Iniciar sesión/ }));

    expect(await screen.findByRole('alert')).toHaveTextContent('El correo, el usuario o la contraseña no son correctos.');
    expect(screen.getByLabelText('Contraseña')).toHaveValue('');
    expect(getAccessToken()).toBeNull();
  });

  it('muestra el estado de carga mientras espera al backend', async () => {
    let release;
    mockApi({ 'POST /auth/login': () => new Promise((resolve) => (release = resolve)) });
    const user = userEvent.setup();
    renderAt('/login');
    await fillLogin(user);
    await user.click(screen.getByRole('button', { name: /^Iniciar sesión/ }));

    const button = screen.getByRole('button', { name: /Iniciando sesión/ });
    expect(button).toBeDisabled();
    release(jsonResponse(401, { codigo: 'CUENTA_BLOQUEADA', detail: 'x' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/bloqueamos el acceso/);
  });

  it('credenciales inválidas: mensaje genérico y la regla de bloqueo, sin intentos restantes por cuenta', async () => {
    mockApi({ 'POST /auth/login': jsonResponse(401, { codigo: 'CREDENCIALES_INVALIDAS', detail: 'x' }) });
    const user = userEvent.setup();
    renderAt('/login');
    await fillLogin(user);
    await user.click(screen.getByRole('button', { name: /^Iniciar sesión/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('El correo, el usuario o la contraseña no son correctos.');
    expect(screen.getByText(/después de 3 intentos fallidos seguidos/)).toBeInTheDocument();
    expect(screen.queryByText(/te quedan/i)).not.toBeInTheDocument();
  });

  it('bloqueo temporal: informa cuándo se puede volver a intentar según Retry-After del backend', async () => {
    mockApi({
      'POST /auth/login': jsonResponse(429, { codigo: 'CUENTA_BLOQUEADA', detail: 'x' }, { 'Retry-After': '540' }),
    });
    const user = userEvent.setup();
    renderAt('/login');
    await fillLogin(user);
    await user.click(screen.getByRole('button', { name: /^Iniciar sesión/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Podés volver a intentar en 9 minutos.');
    expect(screen.queryByText(/después de 3 intentos fallidos seguidos/)).not.toBeInTheDocument();
  });

  it('completa el segundo paso cuando el backend pide MFA', async () => {
    const { calls } = mockApi({
      'POST /auth/login': jsonResponse(200, { estado: 'MFA_REQUERIDO', challengeToken: 'desafio', challengeExpiresIn: 300 }),
      'POST /auth/mfa/verify': [
        jsonResponse(401, { codigo: 'CODIGO_INVALIDO', detail: 'Código inválido.' }),
        jsonResponse(200, { estado: 'AUTENTICADO', tokens: TOKENS }),
      ],
      'GET /auth/me': jsonResponse(200, ACCOUNT),
    });
    const user = userEvent.setup();
    renderAt('/login');
    await fillLogin(user);
    await user.click(screen.getByRole('button', { name: /^Iniciar sesión/ }));

    const code = await screen.findByLabelText('Código de verificación');
    await user.click(screen.getByRole('button', { name: 'Verificar' }));
    expect(screen.getByText('Ingresá el código de 6 dígitos.')).toBeInTheDocument();

    await user.type(code, '000000');
    await user.click(screen.getByRole('button', { name: 'Verificar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('El código no es correcto');

    await user.click(screen.getByRole('button', { name: 'Usar un código de recuperación' }));
    await user.type(screen.getByLabelText('Código de recuperación'), 'ABCD-EFGH');
    await user.click(screen.getByRole('button', { name: 'Verificar' }));

    await screen.findByRole('heading', { name: 'Hola, Victoria' });
    const verifies = calls.filter((c) => c.key === 'POST /auth/mfa/verify').map((c) => c.body);
    expect(verifies).toEqual([
      { challengeToken: 'desafio', codigo: '000000' },
      { challengeToken: 'desafio', codigoRecuperacion: 'ABCD-EFGH' },
    ]);
  });

  it('hay un único inicio de sesión para todos los tipos de cuenta (sin selector)', async () => {
    const { calls } = mockApi({
      'POST /auth/login': jsonResponse(401, { codigo: 'CREDENCIALES_INVALIDAS', detail: 'x' }),
    });
    const user = userEvent.setup();
    renderAt('/login');
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument();
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
    expect(screen.getByText('Una sola cuenta para todo')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /^Iniciar sesión/ })).toHaveLength(1);
    await fillLogin(user);
    await user.click(screen.getByRole('button', { name: /^Iniciar sesión/ }));
    await screen.findByRole('alert');
    expect(Object.keys(calls[0].body)).toEqual(['identificador', 'password']);
  });

  it('cuenta sin verificar: ofrece reenviar el correo de verificación', async () => {
    const { calls } = mockApi({
      'POST /auth/login': jsonResponse(403, { codigo: 'CORREO_NO_VERIFICADO', detail: 'x' }),
      'POST /auth/verify-email/resend': jsonResponse(202, { mensaje: 'ok' }),
    });
    const user = userEvent.setup();
    renderAt('/login');
    await fillLogin(user, 'victoria@example.com');
    await user.click(screen.getByRole('button', { name: /^Iniciar sesión/ }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Revisá tu bandeja de entrada o spam.');
    const resendEmail = screen.getByLabelText('Correo electrónico de tu cuenta');
    expect(resendEmail).toHaveValue('victoria@example.com');
    await user.click(screen.getByRole('button', { name: /Reenviar correo de verificación/ }));

    expect(await screen.findByText(/Te enviamos un nuevo correo de verificación/)).toBeInTheDocument();
    expect(calls.at(-1)).toMatchObject({
      key: 'POST /auth/verify-email/resend',
      body: { correoElectronico: 'victoria@example.com' },
    });
  });

  it('cuenta sin verificar con usuario: pide el correo antes de reenviar', async () => {
    const { calls } = mockApi({
      'POST /auth/login': jsonResponse(403, { codigo: 'CORREO_NO_VERIFICADO', detail: 'x' }),
      'POST /auth/verify-email/resend': jsonResponse(202, { mensaje: 'ok' }),
    });
    const user = userEvent.setup();
    renderAt('/login');
    await fillLogin(user, 'victoria');
    await user.click(screen.getByRole('button', { name: /^Iniciar sesión/ }));

    const resendEmail = await screen.findByLabelText('Correo electrónico de tu cuenta');
    expect(resendEmail).toHaveValue('');
    await user.click(screen.getByRole('button', { name: /Reenviar correo de verificación/ }));
    expect(screen.getByText('Ingresá el correo con el que te registraste.')).toBeInTheDocument();
    expect(calls.filter((c) => c.key === 'POST /auth/verify-email/resend')).toHaveLength(0);

    await user.type(resendEmail, 'victoria@example.com');
    await user.click(screen.getByRole('button', { name: /Reenviar correo de verificación/ }));
    expect(await screen.findByText(/Te enviamos un nuevo correo de verificación/)).toBeInTheDocument();
  });

  it('otros errores de login no muestran el reenvío', async () => {
    mockApi({ 'POST /auth/login': jsonResponse(401, { codigo: 'CREDENCIALES_INVALIDAS', detail: 'x' }) });
    const user = userEvent.setup();
    renderAt('/login');
    await fillLogin(user);
    await user.click(screen.getByRole('button', { name: /^Iniciar sesión/ }));
    await screen.findByRole('alert');
    expect(screen.queryByRole('button', { name: /Reenviar correo de verificación/ })).not.toBeInTheDocument();
  });

  it('«¿Olvidaste tu contraseña?» lleva a la recuperación y envía el enlace sin revelar si la cuenta existe', async () => {
    const { calls } = mockApi({
      'POST /auth/password/forgot': jsonResponse(202, { mensaje: 'Si el correo corresponde a una cuenta, te enviamos un enlace.' }),
    });
    const user = userEvent.setup();
    renderAt('/login');
    await user.click(screen.getByRole('link', { name: '¿Olvidaste tu contraseña?' }));
    await user.type(await screen.findByLabelText('Correo electrónico'), 'persona@example.com');
    await user.click(screen.getByRole('button', { name: /Enviar enlace/ }));
    expect(await screen.findByText(/Si el correo corresponde a una cuenta con contraseña/)).toBeInTheDocument();
    expect(calls.find((c) => c.key === 'POST /auth/password/forgot').body).toEqual({ correoElectronico: 'persona@example.com' });
  });

  it('restablecer: usa el token del enlace una sola vez, lo quita de la URL y avisa que cerró las sesiones', async () => {
    const { calls } = mockApi({ 'POST /auth/password/reset': jsonResponse(200, { mensaje: 'ok' }) });
    const user = userEvent.setup();
    renderAt('/restablecer-contrasena?token=abc123');
    await user.type(await screen.findByLabelText('Contraseña nueva'), 'Zorro#Lento-2027');
    await user.type(screen.getByLabelText('Repetir contraseña'), 'Zorro#Lento-2027');
    await user.click(screen.getByRole('button', { name: /Guardar contraseña/ }));
    expect(await screen.findByText(/Cerramos tus sesiones abiertas/)).toBeInTheDocument();
    expect(calls.find((c) => c.key === 'POST /auth/password/reset').body).toEqual({ token: 'abc123', password: 'Zorro#Lento-2027' });
    expect(window.location.search).toBe('');
  });

  it('restablecer sin token o con enlace vencido ofrece pedir uno nuevo', async () => {
    mockApi({});
    renderAt('/restablecer-contrasena');
    expect(await screen.findByText('El enlace de restablecimiento es inválido.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Pedir un enlace nuevo' })).toHaveAttribute('href', '/recuperar-contrasena');
  });

  it('mostrar/ocultar contraseña', async () => {
    mockApi({});
    const user = userEvent.setup();
    renderAt('/login');
    const password = screen.getByLabelText('Contraseña');
    expect(password).toHaveAttribute('type', 'password');
    await user.click(screen.getByRole('button', { name: 'Mostrar contraseña' }));
    expect(password).toHaveAttribute('type', 'text');
  });
});

describe('Google', () => {
  it('Continuar con Google navega al flujo OAuth del backend', async () => {
    mockApi({});
    const assign = vi.fn();
    vi.stubGlobal('location', { ...window.location, assign });
    const user = userEvent.setup();
    renderAt('/login');
    await user.click(screen.getByRole('checkbox', { name: 'Recordarme' }));
    await user.click(screen.getByRole('button', { name: 'Continuar con Google' }));
    expect(assign).toHaveBeenCalledWith('http://api.test/api/v1/auth/google/login?recordar=true');
    expect(window.sessionStorage.getItem('glucolume.googleRemember')).toBe('1');
  });

  it('iniciar sesión con una cuenta de Google no registrada ofrece registrarse', async () => {
    mockApi({});
    renderAt('/auth/google/callback#error=CUENTA_NO_REGISTRADA');
    expect(await screen.findByText(/Registrate primero/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Registrarme' })).toHaveAttribute('href', '/registro');
  });

  it('el callback canjea el código una sola vez, lo quita de la URL y entra a /app', async () => {
    const { calls } = mockApi({
      'POST /auth/google/exchange': jsonResponse(200, { estado: 'AUTENTICADO', tokens: TOKENS }),
      'GET /auth/me': jsonResponse(200, { ...ACCOUNT, tieneGoogle: true }),
    });
    window.sessionStorage.setItem('glucolume.googleRemember', '1');
    renderAt('/auth/google/callback#code=codigo-unico');

    await screen.findByRole('heading', { name: 'Hola, Victoria' });
    const exchanges = calls.filter((c) => c.key === 'POST /auth/google/exchange');
    expect(exchanges).toHaveLength(1);
    expect(exchanges[0].body).toEqual({ code: 'codigo-unico' });
    expect(window.location.hash).toBe('');
    expect(window.localStorage.getItem('glucolume.refreshToken')).toBe('refresh-1');
  });

  it('el callback con error muestra un mensaje amigable', async () => {
    const { fetchMock } = mockApi({});
    renderAt('/auth/google/callback#error=VINCULACION_RECHAZADA');
    expect(await screen.findByRole('alert')).toHaveTextContent(/No pudimos usar esa cuenta de Google/);
    expect(screen.getByRole('link', { name: /Volver a iniciar sesión/ })).toHaveAttribute('href', '/login');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('el callback pide MFA cuando corresponde', async () => {
    mockApi({
      'POST /auth/google/exchange': jsonResponse(200, { estado: 'MFA_REQUERIDO', challengeToken: 'desafio' }),
      'POST /auth/mfa/verify': jsonResponse(200, { estado: 'AUTENTICADO', tokens: TOKENS }),
      'GET /auth/me': jsonResponse(200, ACCOUNT),
    });
    const user = userEvent.setup();
    renderAt('/auth/google/callback#code=abc');
    await user.type(await screen.findByLabelText('Código de verificación'), '123456');
    await user.click(screen.getByRole('button', { name: 'Verificar' }));
    await screen.findByRole('heading', { name: 'Hola, Victoria' });
  });
});

describe('Google: tipo de cuenta', () => {
  it('error de servidor en el callback se muestra amigable', async () => {
    mockApi({});
    renderAt('/auth/google/callback#error=ERROR_SERVIDOR');
    expect(await screen.findByRole('alert')).toHaveTextContent('Tuvimos un problema al completar el acceso');
  });

  it('iniciar sesión con Google no envía intención de registro (el tipo de una cuenta existente no cambia)', async () => {
    mockApi({});
    const assign = vi.fn();
    vi.stubGlobal('location', { ...window.location, assign });
    const user = userEvent.setup();
    renderAt('/login');
    await user.click(screen.getByRole('button', { name: 'Continuar con Google' }));
    expect(assign).toHaveBeenCalledWith('http://api.test/api/v1/auth/google/login');
  });
});

describe('Sesión', () => {
  it('/app sin sesión redirige a /login', async () => {
    mockApi({});
    renderAt('/app');
    expect(await screen.findByRole('heading', { name: 'Iniciar sesión' })).toBeInTheDocument();
  });

  it('al recargar recupera la sesión con el refresh token guardado', async () => {
    window.localStorage.setItem('glucolume.refreshToken', 'guardado');
    const { calls } = mockApi({
      'POST /auth/refresh': jsonResponse(200, { ...TOKENS, refreshToken: 'rotado' }),
      'GET /auth/me': jsonResponse(200, ACCOUNT),
    });
    renderAt('/app');
    await screen.findByRole('heading', { name: 'Hola, Victoria' });
    expect(calls[0]).toMatchObject({ key: 'POST /auth/refresh', body: { refreshToken: 'guardado' } });
    expect(window.localStorage.getItem('glucolume.refreshToken')).toBe('rotado');
  });

  it('un refresh token revocado deja la sesión cerrada', async () => {
    window.sessionStorage.setItem('glucolume.refreshToken', 'revocado');
    mockApi({ 'POST /auth/refresh': jsonResponse(401, { codigo: 'TOKEN_INVALIDO', detail: 'Sesión inválida.' }) });
    renderAt('/app');
    expect(await screen.findByRole('heading', { name: 'Iniciar sesión' })).toBeInTheDocument();
    expect(getRefreshToken()).toBeNull();
  });

  it('con sesión, /login lleva directo a /app', async () => {
    window.sessionStorage.setItem('glucolume.refreshToken', 'r');
    mockApi({
      'POST /auth/refresh': jsonResponse(200, TOKENS),
      'GET /auth/me': jsonResponse(200, ACCOUNT),
    });
    renderAt('/login');
    expect(await screen.findByRole('heading', { name: 'Hola, Victoria' })).toBeInTheDocument();
  });

  it('cerrar sesión revoca la sesión en el backend y borra los tokens', async () => {
    saveTokens(TOKENS, true);
    const { calls } = mockApi({
      'GET /auth/me': jsonResponse(200, { ...ACCOUNT, requiereCompletarPerfil: true, camposFaltantes: ['fechaNacimiento'] }),
      'POST /auth/logout': { ok: true, status: 204, json: async () => null },
    });
    window.localStorage.setItem('glucolume.refreshToken', 'refresh-1');
    const user = userEvent.setup();
    renderAt('/app');
    // Recupera la sesión con /auth/me usando el access token en memoria.
    expect(await screen.findByRole('heading', { name: 'Hola, Victoria' })).toBeInTheDocument();
    expect(screen.queryByText(/Completá tu perfil/)).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Cerrar sesión' }));

    expect(await screen.findByRole('heading', { name: 'Iniciar sesión' })).toBeInTheDocument();
    const logout = calls.find((c) => c.key === 'POST /auth/logout');
    expect(logout.options.headers.Authorization).toBe('Bearer access-1');
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });

  it('si el backend no responde al cerrar sesión, igual se cierra localmente', async () => {
    saveTokens(TOKENS, false);
    mockApi({
      'GET /auth/me': jsonResponse(200, ACCOUNT),
      'POST /auth/logout': new TypeError('Failed to fetch'),
    });
    const user = userEvent.setup();
    renderAt('/app');
    await user.click(await screen.findByRole('button', { name: 'Cerrar sesión' }));
    await waitFor(() => expect(getRefreshToken()).toBeNull());
    expect(await screen.findByRole('heading', { name: 'Iniciar sesión' })).toBeInTheDocument();
  });
});
