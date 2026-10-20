import { beforeEach, describe, expect, it } from 'vitest';

import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  isRemembered,
  saveTokens,
  setPendingGoogleRemember,
  takePendingGoogleRemember,
} from './tokenStore.js';

const KEY = 'glucolume.refreshToken';

describe('tokenStore', () => {
  beforeEach(() => clearTokens());

  it('el access token vive solo en memoria', () => {
    saveTokens({ accessToken: 'access', refreshToken: 'refresh' }, true);
    expect(getAccessToken()).toBe('access');
    const stored = JSON.stringify({ ...window.localStorage }) + JSON.stringify({ ...window.sessionStorage });
    expect(stored).not.toContain('access');
  });

  it('sin Recordarme el refresh token va a sessionStorage', () => {
    saveTokens({ accessToken: 'a', refreshToken: 'r' }, false);
    expect(window.sessionStorage.getItem(KEY)).toBe('r');
    expect(window.localStorage.getItem(KEY)).toBeNull();
    expect(isRemembered()).toBe(false);
  });

  it('con Recordarme el refresh token va a localStorage', () => {
    saveTokens({ accessToken: 'a', refreshToken: 'r' }, true);
    expect(window.localStorage.getItem(KEY)).toBe('r');
    expect(window.sessionStorage.getItem(KEY)).toBeNull();
  });

  it('al rotar conserva la elección de Recordarme', () => {
    saveTokens({ accessToken: 'a', refreshToken: 'r1' }, true);
    saveTokens({ accessToken: 'b', refreshToken: 'r2' });
    expect(window.localStorage.getItem(KEY)).toBe('r2');
    expect(getRefreshToken()).toBe('r2');
  });

  it('clearTokens borra todo', () => {
    saveTokens({ accessToken: 'a', refreshToken: 'r' }, true);
    clearTokens();
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });

  it('la preferencia elegida antes de ir a Google se lee una sola vez', () => {
    setPendingGoogleRemember(true);
    expect(takePendingGoogleRemember()).toBe(true);
    expect(takePendingGoogleRemember()).toBe(false);
  });
});
