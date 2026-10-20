import { describe, expect, it, vi } from 'vitest';

vi.mock('../config.js', () => ({
  API_BASE_URL: '',
  API_PREFIX: '/api/v1',
  LOGIN_ORIGIN: 'http://localhost:8080',
  APP_ORIGIN: 'http://glucolume.local',
}));

const { originRedirect } = await import('./originGuard.js');

const at = (origin, pathname, search = '', hash = '') => originRedirect({ origin, pathname, search, hash });

describe('separación de orígenes login / aplicación', () => {
  it('/login en la aplicación se mueve a localhost', () => {
    expect(at('http://glucolume.local', '/login', '?x=1')).toBe('http://localhost:8080/login?x=1');
  });

  it('cualquier otra ruta en localhost se mueve a la aplicación', () => {
    expect(at('http://localhost:8080', '/app/inicio')).toBe('http://glucolume.local/app/inicio');
    expect(at('http://localhost:8080', '/', '', '#a')).toBe('http://glucolume.local/#a');
  });

  it('no redirige cuando ya está en el origen correcto', () => {
    expect(at('http://localhost:8080', '/login')).toBeNull();
    expect(at('http://glucolume.local', '/app/inicio')).toBeNull();
    expect(at('http://glucolume.local', '/auth/google/callback', '', '#code=abc')).toBeNull();
  });
});
