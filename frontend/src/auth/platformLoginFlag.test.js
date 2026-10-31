import { beforeEach, describe, expect, it } from 'vitest';

import { setPendingGooglePlatform, takePendingGooglePlatform } from './tokenStore.js';

describe('marca del ingreso con Google desde /plataforma/login', () => {
  beforeEach(() => window.sessionStorage.clear());

  it('vuelve al panel solo si el inicio fue administrativo, y se consume al tomarla', () => {
    setPendingGooglePlatform(true);
    expect(takePendingGooglePlatform()).toBe(true);
    expect(takePendingGooglePlatform()).toBe(false);
  });

  it('un inicio general sobrescribe una marca vieja de un intento administrativo que no volvió', () => {
    setPendingGooglePlatform(true); // intento desde /plataforma/login cancelado en Google: nunca llegó al callback
    setPendingGooglePlatform(false); // después, ingreso normal desde /login
    expect(takePendingGooglePlatform()).toBe(false);
  });
});
