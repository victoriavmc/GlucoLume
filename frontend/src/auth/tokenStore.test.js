import { beforeEach, describe, expect, it } from 'vitest';

import {
  clearTokens,
  getAccessToken,
  hasSessionHint,
  isRemembered,
  saveTokens,
  setPendingGoogleRemember,
  takePendingGoogleRemember,
} from './tokenStore.js';

const HINT = 'glucolume.sessionHint';
const LEGACY = 'glucolume.refreshToken';

const everythingStored = () => JSON.stringify({ ...window.localStorage }) + JSON.stringify({ ...window.sessionStorage });

describe('tokenStore (H-09: el refresh token vive en una cookie HttpOnly)', () => {
  beforeEach(() => clearTokens());

  it('el access token vive solo en memoria', () => {
    saveTokens({ accessToken: 'access-secreto' }, true);
    expect(getAccessToken()).toBe('access-secreto');
    expect(everythingStored()).not.toContain('access-secreto');
  });

  it('NUNCA guarda un refresh token en Web Storage, aunque el backend lo enviara', () => {
    saveTokens({ accessToken: 'a', refreshToken: 'refresh-secreto' }, true);
    saveTokens({ accessToken: 'a', refreshToken: 'refresh-secreto' }, false);
    expect(everythingStored()).not.toContain('refresh-secreto');
    expect(window.localStorage.getItem(LEGACY)).toBeNull();
    expect(window.sessionStorage.getItem(LEGACY)).toBeNull();
  });

  it('sin Recordarme la marca de sesión va a sessionStorage', () => {
    saveTokens({ accessToken: 'a' }, false);
    expect(window.sessionStorage.getItem(HINT)).toBe('1');
    expect(window.localStorage.getItem(HINT)).toBeNull();
    expect(hasSessionHint()).toBe(true);
    expect(isRemembered()).toBe(false);
  });

  it('con Recordarme la marca va a localStorage', () => {
    saveTokens({ accessToken: 'a' }, true);
    expect(window.localStorage.getItem(HINT)).toBe('1');
    expect(window.sessionStorage.getItem(HINT)).toBeNull();
    expect(isRemembered()).toBe(true);
  });

  it('al rotar conserva la elección de Recordarme', () => {
    saveTokens({ accessToken: 'a' }, true);
    saveTokens({ accessToken: 'b' });
    expect(window.localStorage.getItem(HINT)).toBe('1');
    expect(getAccessToken()).toBe('b');
  });

  it('clearTokens borra el access token y la marca', () => {
    saveTokens({ accessToken: 'a' }, true);
    clearTokens();
    expect(getAccessToken()).toBeNull();
    expect(hasSessionHint()).toBe(false);
  });

  it('sin marca no hay sesión que recuperar', () => {
    expect(hasSessionHint()).toBe(false);
  });

  it('borra el refresh token que dejó el esquema anterior en un navegador ya usado', () => {
    window.localStorage.setItem(LEGACY, 'viejo-1');
    window.sessionStorage.setItem(LEGACY, 'viejo-2');
    expect(hasSessionHint()).toBe(false);  // un token viejo no cuenta como sesión
    expect(window.localStorage.getItem(LEGACY)).toBeNull();
    expect(window.sessionStorage.getItem(LEGACY)).toBeNull();
  });

  it('la preferencia elegida antes de ir a Google se lee una sola vez', () => {
    setPendingGoogleRemember(true);
    expect(takePendingGoogleRemember()).toBe(true);
    expect(takePendingGoogleRemember()).toBe(false);
  });
});
