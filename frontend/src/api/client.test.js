import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, getAccessToken, getRefreshToken, saveTokens } from '../auth/tokenStore.js';
import { jsonResponse, mockApi } from '../test/helpers.js';
import { ApiError, NETWORK_ERROR, request } from './client.js';

describe('cliente HTTP', () => {
  beforeEach(() => clearTokens());

  it('usa VITE_API_BASE_URL y el prefijo /api/v1', async () => {
    const { calls } = mockApi({ 'POST /auth/login': jsonResponse(200, { estado: 'AUTENTICADO' }) });
    await request('/auth/login', { method: 'POST', body: { identificador: 'a', password: 'b' } });
    expect(calls[0].url).toBe('http://api.test/api/v1/auth/login');
    expect(calls[0].options.headers['Content-Type']).toBe('application/json');
    expect(calls[0].options.headers.Authorization).toBeUndefined();
  });

  it('convierte {codigo, detail} del backend en ApiError', async () => {
    mockApi({ 'POST /auth/login': jsonResponse(401, { codigo: 'CREDENCIALES_INVALIDAS', detail: 'Credenciales inválidas.' }) });
    const error = await request('/auth/login', { method: 'POST', body: {} }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 401, codigo: 'CREDENCIALES_INVALIDAS', message: 'Credenciales inválidas.' });
  });

  it('resume los errores de validación 422 sin exponer valores', async () => {
    mockApi({
      'POST /auth/login': jsonResponse(422, {
        detail: [{ type: 'string_too_short', loc: ['body', 'password'], msg: 'Debe tener al menos 1 carácter.' }],
      }),
    });
    const error = await request('/auth/login', { method: 'POST', body: {} }).catch((e) => e);
    expect(error.codigo).toBe('VALIDACION');
    expect(error.fields).toEqual([{ campo: 'password', ruta: 'password', mensaje: 'Debe tener al menos 1 carácter.' }]);
  });

  it('informa de forma amigable si el servidor no responde', async () => {
    mockApi({ 'GET /auth/me': new TypeError('Failed to fetch') });
    saveTokens({ accessToken: 'a', refreshToken: 'r' });
    const error = await request('/auth/me', { auth: true }).catch((e) => e);
    expect(error.codigo).toBe(NETWORK_ERROR);
    expect(error.message).toMatch(/No se pudo conectar con el servidor/);
  });

  it('envía Bearer y, ante un 401, renueva la sesión una vez y reintenta', async () => {
    saveTokens({ accessToken: 'vencido', refreshToken: 'refresh-viejo' });
    const { calls } = mockApi({
      'GET /auth/me': [jsonResponse(401, { codigo: 'TOKEN_INVALIDO', detail: 'Token inválido.' }), jsonResponse(200, { ok: true })],
      'POST /auth/refresh': jsonResponse(200, { accessToken: 'nuevo', refreshToken: 'refresh-nuevo' }),
    });

    await expect(request('/auth/me', { auth: true })).resolves.toEqual({ ok: true });

    expect(calls.map((c) => c.key)).toEqual(['GET /auth/me', 'POST /auth/refresh', 'GET /auth/me']);
    expect(calls[0].options.headers.Authorization).toBe('Bearer vencido');
    expect(calls[1].body).toEqual({ refreshToken: 'refresh-viejo' });
    expect(calls[2].options.headers.Authorization).toBe('Bearer nuevo');
    expect(getAccessToken()).toBe('nuevo');
    expect(getRefreshToken()).toBe('refresh-nuevo');
  });

  it('un 401 de negocio (CODIGO_INVALIDO) no renueva la sesión ni reintenta', async () => {
    saveTokens({ accessToken: 'vigente', refreshToken: 'r' });
    const { calls } = mockApi({
      'POST /auth/mfa/disable': jsonResponse(401, { codigo: 'CODIGO_INVALIDO', detail: 'Código inválido.' }),
    });
    await expect(request('/auth/mfa/disable', { method: 'POST', body: { codigo: '1' }, auth: true }))
      .rejects.toMatchObject({ codigo: 'CODIGO_INVALIDO' });
    expect(calls.map((c) => c.key)).toEqual(['POST /auth/mfa/disable']);
    expect(getRefreshToken()).toBe('r');
  });

  it('renueva una sola vez aunque haya varias llamadas simultáneas (el backend rota el refresh token)', async () => {
    saveTokens({ accessToken: null, refreshToken: 'refresh-1' });
    clearTokens();
    saveTokens({ accessToken: undefined, refreshToken: 'refresh-1' });
    const { calls } = mockApi({
      'POST /auth/refresh': jsonResponse(200, { accessToken: 'a2', refreshToken: 'refresh-2' }),
      'GET /auth/me': jsonResponse(200, { ok: true }),
    });

    await Promise.all([request('/auth/me', { auth: true }), request('/auth/me', { auth: true })]);

    expect(calls.filter((c) => c.key === 'POST /auth/refresh')).toHaveLength(1);
  });

  it('si el refresh es rechazado, borra la sesión local', async () => {
    saveTokens({ accessToken: 'vencido', refreshToken: 'revocado' });
    mockApi({
      'GET /auth/me': jsonResponse(401, { codigo: 'TOKEN_INVALIDO', detail: 'Token inválido.' }),
      'POST /auth/refresh': jsonResponse(401, { codigo: 'TOKEN_INVALIDO', detail: 'Sesión inválida.' }),
    });
    await expect(request('/auth/me', { auth: true })).rejects.toMatchObject({ codigo: 'TOKEN_INVALIDO' });
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });
});
